
import asyncio
import json
import logging
import hashlib
from typing import Dict, Optional, Any, List
from concurrent.futures import ThreadPoolExecutor
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from config import settings
import httpx
from . import tools as tools_service

logger = logging.getLogger(__name__)

# Shared executor for running blocking SDK calls without blocking the event loop
_EXECUTOR = ThreadPoolExecutor(max_workers=10)

TOOL_FUNCTIONS = {
    "update_claim_data": tools_service.update_claim_data,
    "get_claim_by_contact_info": tools_service.get_claim_by_contact_info,
    "initiate_new_claim": tools_service.initiate_new_claim,
    "transition_claim_type": tools_service.transition_claim_type,
    "get_question_by_fieldname": tools_service.get_question_by_fieldname,
    "search_knowledge_base": tools_service.search_knowledge_base,
}

def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode('utf-8'))
    return h.hexdigest()

class AIAgentService:
    """Service for managing AI agents using Azure AI Foundry."""
    def __init__(self, redis_client=None):
        try:
            self.credential = DefaultAzureCredential()
            self.agents_client = AgentsClient(
                endpoint=settings.AZURE_AI_FOUNDRY_ENDPOINT,
                credential=self.credential
            )
            # Shared executor for blocking SDK calls
            self.executor = _EXECUTOR
            self.agent_ids: Dict[str, str] = {}
            self.threads: Dict[str, str] = {}
            self.deployment_model_name = settings.AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME
            self.redis = redis_client
            self._initialize_callable_tools()
            self._load_agent_ids()
            logger.info("AIAgentService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AIAgentService: {str(e)}")
            raise

    def _initialize_callable_tools(self):
        self.callable_tools = {
            "get_claim_by_contact_info": tools_service.get_claim_by_contact_info,
            "initiate_new_claim": tools_service.initiate_new_claim,
            "transition_claim_type": tools_service.transition_claim_type,
            "update_claim_data": tools_service.update_claim_data,
            "get_question_by_fieldname": tools_service.get_question_by_fieldname,
        }

    def _load_agent_ids(self):
        if getattr(settings, "INITIAL_INTAKE_AGENT_ID", None):
            self.agent_ids["initial_intake_agent"] = settings.INITIAL_INTAKE_AGENT_ID
            logger.info("Loaded initial_intake_agent ID.")
        if getattr(settings, "PORTAL_AGENT_ID", None):
            self.agent_ids["portal_claim_agent"] = settings.PORTAL_AGENT_ID
            logger.info("Loaded portal_claim_agent ID.")

    async def create_or_get_agent(self, agent_name: str, instructions: str = "", model: Optional[str] = None) -> str:
        try:
            if agent_name in self.agent_ids:
                logger.info(f"Using configured agent ID for: {agent_name}")
                # Log the agent details to see what it has
                try:
                    agent = await asyncio.to_thread(
                        self.agents_client.get_agent,
                        agent_id=self.agent_ids[agent_name]
                    )
                    logger.info(f"Agent {agent_name} has instructions: {getattr(agent, 'instructions', 'None')[:200]}...")
                    logger.info(f"Agent {agent_name} has tools: {getattr(agent, 'tools', 'None')}")
                    logger.info(f"Agent {agent_name} model: {getattr(agent, 'model', 'None')}")
                except Exception as e:
                    logger.warning(f"Could not retrieve agent details: {e}")
                return self.agent_ids[agent_name]
            else:
                # Create the agent if not configured
                resolved_model = model or self.deployment_model_name
                if not resolved_model:
                    raise ValueError("Model deployment name is required to create agent")
                logger.info(f"Creating agent '{agent_name}' with model '{resolved_model}'")
                logger.info(f"Creating agent with instructions: {instructions[:200]}...")
                agent = await asyncio.to_thread(
                    self.agents_client.create_agent,
                    name=agent_name,
                    instructions=instructions or "",
                    model=resolved_model
                )
                self.agent_ids[agent_name] = agent.id
                logger.info(f"Created agent '{agent_name}' with ID {agent.id}")
                return agent.id
        except Exception as e:
            logger.error(f"Error in create_or_get_agent for {agent_name}: {str(e)}")
            raise

    async def get_or_create_thread(self, user_id: str) -> str:
        try:
            if user_id in self.threads:
                thread_id = self.threads[user_id]
                logger.debug(f"Using existing thread {thread_id} for user {user_id}")
                return thread_id
            thread = await asyncio.to_thread(self.agents_client.threads.create)
            self.threads[user_id] = thread.id
            logger.info(f"Created new thread {thread.id} for user {user_id}")
            return thread.id
        except Exception as e:
            logger.error(f"Error getting/creating thread for user {user_id}: {str(e)}")
            raise

    async def get_agent_response(
        self,
        agent_name: str,
        user_id: str,
        user_message: str,
        chat_history: Optional[List[Dict]] = None
    ) -> str:
        try:
            agent_id = await self.create_or_get_agent(agent_name, "")
            thread_id = await self.get_or_create_thread(user_id)
            
            # If we have chat history, add it to the thread first
            if chat_history and len(chat_history) > 0:
                logger.info(f"Adding {len(chat_history)} previous messages to thread {thread_id}")
                for hist_msg in chat_history:
                    if hist_msg.get("role") in ["user", "assistant"]:
                        try:
                            await asyncio.to_thread(
                                self.agents_client.messages.create,
                                thread_id=thread_id,
                                role=hist_msg["role"],
                                content=[{"type": "text", "text": hist_msg["content"]}]
                            )
                        except Exception as hist_e:
                            logger.warning(f"Failed to add history message: {hist_e}")
            
            # Add current user message to thread
            message = await asyncio.to_thread(
                self.agents_client.messages.create,
                thread_id=thread_id,
                role="user",
                content=[{"type": "text", "text": user_message}]
            )
            logger.debug(f"Created message {message.id} in thread {thread_id}")
            
            # Create a run and process tool calls if required
            try:
                logger.info(f"Creating run for agent {agent_id} in thread {thread_id}")
                logger.info(f"Current thread has messages: {len(await asyncio.to_thread(lambda: list(self.agents_client.messages.list(thread_id=thread_id)))}")
                
                run = await asyncio.to_thread(
                    self.agents_client.runs.create,
                    thread_id=thread_id,
                    agent_id=agent_id
                )
                logger.debug(f"Created run {run.id} for agent {agent_id}")
                logger.info(f"Starting run processing for run {run.id}")
            except Exception as run_create_error:
                logger.error(f"Failed to create run: {run_create_error}")
                return "I'm sorry, I encountered an error while starting the conversation. Please try again."
                
            run = await self._process_run_until_complete(thread_id=thread_id, run_id=run.id)
            logger.debug(f"Processed run {run.id} to terminal status: {getattr(run, 'status', None)}")
            
            # Check run status and fetch assistant message
            if run.status == "completed":
                # Ensure we have a concrete list for safe reverse iteration
                messages = await asyncio.to_thread(lambda: list(self.agents_client.messages.list(thread_id=thread_id)))
                for message in reversed(messages):
                    if getattr(message, "role", None) == "assistant":
                        response_text = None
                        if hasattr(message, 'content') and message.content:
                            if isinstance(message.content, list) and len(message.content) > 0:
                                content_item = message.content[0]
                                if hasattr(content_item, 'text') and hasattr(content_item.text, 'value'):
                                    response_text = content_item.text.value
                                elif hasattr(content_item, 'value'):
                                    response_text = content_item.value
                            elif isinstance(message.content, str):
                                response_text = message.content
                        if response_text:
                            logger.info(f"Agent {agent_name} responded to user {user_id}")
                            return response_text
                logger.warning(f"No assistant message found in completed run {run.id}")
                return "I'm sorry, I couldn't process your request at this time."
            elif run.status == "failed":
                error_msg = getattr(run, 'last_error', 'Unknown error')
                logger.error(f"Agent run {run.id} failed: {error_msg}")
                return "I'm sorry, there was an error processing your request. Please try again."
            else:
                logger.warning(f"Agent run {run.id} ended with status: {run.status}")
                return "I'm sorry, your request is taking longer than expected. Please try again."
        except Exception as e:
            logger.error(f"Error getting agent response: {str(e)}", exc_info=True)
            return "I'm sorry, I encountered an error while processing your request. Please try again."

    async def cleanup_thread(self, user_id: str):
        if user_id in self.threads:
            del self.threads[user_id]
            logger.info(f"Cleaned up thread for user {user_id}")

    def close(self):
        try:
            self.credential.close()
            logger.info("AIAgentService credentials closed")
        except Exception as e:
            logger.error(f"Error closing credentials: {str(e)}")

    # Shared async HTTP client for all external HTTP calls
    _shared_async_client: httpx.AsyncClient = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=5, max_connections=10))

    @classmethod
    async def close_shared_client(cls):
        await cls._shared_async_client.aclose()

    # Example usage for external HTTP calls:
    # async def fetch_external_data(self, url):
    #     response = await self._shared_async_client.get(url)
    #     return response.json()

    async def stream_agent_response(self, agent_name, user_id, user_message, chat_history=None):
        """
        Stream agent response tokens using Azure Agents SDK's streaming feature.
        Yields partial tokens as they arrive.
        """
        agent_id = await self.create_or_get_agent(agent_name)
        thread_id = await self.get_or_create_thread(user_id)

        # Check for active run before adding a new message
        if await self._has_active_run(thread_id):
            yield "Please wait until your previous request is processed."
            return

        await self._create_message(thread_id=thread_id, role="user", content=user_message)

        # Use a queue to push tokens from blocking stream (thread) to async generator
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _producer():
            try:
                from azure.ai.agents.models import MessageDeltaChunk, AgentStreamEvent
                # Use create_and_stream to start and stream the run in one call
                with self.agents_client.runs.create_and_stream(thread_id=thread_id, agent_id=agent_id) as stream:
                    for event in stream:
                        try:
                            # Prefer explicit event types when available
                            if hasattr(event, "event") and event.event == AgentStreamEvent.MESSAGE_DELTA:
                                data = getattr(event, "data", None)
                                if isinstance(data, MessageDeltaChunk):
                                    text = getattr(data, "text", None)
                                    if text:
                                        token_queue.put_nowait(text)
                            elif hasattr(event, "event") and event.event == AgentStreamEvent.ERROR:
                                token_queue.put_nowait("[ERROR]")
                            else:
                                # Fallback: try to read text directly from event-like tuples
                                data = getattr(event, "data", None)
                                if isinstance(data, MessageDeltaChunk):
                                    text = getattr(data, "text", None)
                                    if text:
                                        token_queue.put_nowait(text)
                        except Exception:
                            # Ignore malformed events
                            pass
            except Exception as e:
                logger.error(f"Streaming producer error: {e}")
            finally:
                # Signal completion
                token_queue.put_nowait(None)

        # Start producer in a background thread
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, _producer)

        # Consume tokens as they arrive
        while True:
            token = await token_queue.get()
            if token is None:
                break
            yield token


    async def _has_active_run(self, thread_id: str) -> bool:
        """Check if there is an active run for a thread to prevent overlapping runs."""
        try:
            runs = await asyncio.to_thread(lambda: list(self.agents_client.runs.list(thread_id=thread_id)))
            for run in runs:
                status_obj = getattr(run, "status", "")
                status_str = str(status_obj)
                # Normalize enum-like values such as 'RunStatus.completed' or 'runstatus.completed'
                if "." in status_str:
                    status_str = status_str.split(".")[-1]
                status = status_str.strip().lower()
                if status in {"queued", "in_progress", "requires_action"}:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Failed to list runs for thread {thread_id}: {e}")
            return False

    async def _create_message(self, thread_id: str, role: str, content: str):
        """Create a message in a thread using the expected content structure."""
        return await asyncio.to_thread(
            self.agents_client.messages.create,
            thread_id=thread_id,
            role=role,
            content=[{"type": "text", "text": content}]
        )

    async def _start_run(self, agent_id: str, thread_id: str):
        """Start and process a run for a thread/agent pair."""
        return await asyncio.to_thread(
            self.agents_client.runs.create_and_process,
            thread_id=thread_id,
            agent_id=agent_id
        )

    async def _process_run_until_complete(self, thread_id: str, run_id: str):
        """Poll a run until it reaches a terminal state, handling required tool actions."""
        try:
            logger.info(f"Processing run {run_id} until completion...")
            start_time = asyncio.get_event_loop().time()
            max_wait_time = 60  # 60 seconds timeout
            
            while True:
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > max_wait_time:
                    logger.error(f"Run {run_id} processing timed out after {max_wait_time} seconds")
                    break
                    
                run = await asyncio.to_thread(
                    self.agents_client.runs.get,
                    thread_id=thread_id,
                    run_id=run_id
                )
                status_obj = getattr(run, "status", "")
                status_str = str(status_obj)
                # Normalize enum-like values such as 'RunStatus.completed' or 'runstatus.completed'
                if "." in status_str:
                    status_str = status_str.split(".")[-1]
                status = status_str.strip().lower()
                logger.info(f"Run {run_id} status: {status}")
                
                # Log more details about the run
                logger.info(f"Run {run_id} details: {getattr(run, 'required_action', 'None')}")
                logger.info(f"Run {run_id} last_error: {getattr(run, 'last_error', 'None')}")
                logger.info(f"Run {run_id} tool_calls: {getattr(run, 'tool_calls', 'None')}")
                
                # Check if there are any tool-related fields we're missing
                run_attrs = [attr for attr in dir(run) if not attr.startswith('_') and 'tool' in attr.lower()]
                if run_attrs:
                    logger.info(f"Run {run_id} has tool-related attributes: {run_attrs}")
                
                if status == "requires_action":
                    logger.info(f"Run {run_id} requires action, processing tool calls...")
                    required = getattr(run, "required_action", None)
                    if not required:
                        logger.warning(f"Run {run_id} requires_action but no required_action found")
                        # Defensive: break to avoid infinite loop
                        break
                    
                    # Extract tool calls from required_action
                    tool_calls = []
                    if hasattr(required, "submit_tool_outputs"):
                        submit = getattr(required, "submit_tool_outputs")
                        if hasattr(submit, "tool_calls"):
                            tool_calls = getattr(submit, "tool_calls", [])
                    elif hasattr(required, "tool_calls"):
                        tool_calls = getattr(required, "tool_calls", [])
                    
                    logger.info(f"Run {run_id} has {len(tool_calls)} tool calls to process")
                    
                    if not tool_calls:
                        logger.warning(f"Run {run_id} requires_action but no tool_calls found")
                        # Try to get tool calls from the run object directly
                        tool_calls = getattr(run, "tool_calls", [])
                        logger.info(f"Found {len(tool_calls)} tool calls from run object")
                    
                    tool_outputs = []
                    for tc in tool_calls:
                        try:
                            # Extract tool name and arguments defensively
                            func_container = getattr(tc, "function", None)
                            tool_name = None
                            raw_args = None
                            if func_container is not None:
                                tool_name = getattr(func_container, "name", None)
                                raw_args = getattr(func_container, "arguments", None)
                            else:
                                tool_name = getattr(tc, "name", None)
                                raw_args = getattr(tc, "arguments", None)

                            logger.info(f"Processing tool call: {tool_name} with args: {raw_args}")
                            
                            # Parse arguments
                            if raw_args and isinstance(raw_args, str):
                                try:
                                    tool_args = json.loads(raw_args)
                                except Exception:
                                    tool_args = {}
                            elif isinstance(raw_args, dict):
                                tool_args = raw_args
                            else:
                                tool_args = {}

                            # Execute the tool
                            output_str = ""
                            if tool_name in self.callable_tools:
                                tool_fn = self.callable_tools[tool_name]
                                if asyncio.iscoroutinefunction(tool_fn):
                                    output_str = await tool_fn(**tool_args)
                                else:
                                    output_str = await asyncio.to_thread(tool_fn, **tool_args)
                                logger.info(f"Tool {tool_name} returned: {output_str}")
                            else:
                                logger.warning(f"Unknown tool: {tool_name}")
                                output_str = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

                            # Get tool call ID
                            tool_call_id = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None)
                            if not tool_call_id:
                                logger.warning(f"No tool_call_id found for tool {tool_name}")
                                continue

                            tool_outputs.append({
                                "tool_call_id": tool_call_id,
                                "output": output_str or ""
                            })
                        except Exception as tool_exc:
                            logger.error(f"Error executing tool call: {tool_exc}")
                    
                    if tool_outputs:
                        # Submit outputs and continue
                        logger.info(f"Submitting {len(tool_outputs)} tool outputs for run {run_id}")
                        try:
                            await asyncio.to_thread(
                                self.agents_client.runs.submit_tool_outputs,
                                thread_id=thread_id,
                                run_id=run_id,
                                tool_outputs=tool_outputs
                            )
                            logger.info(f"Successfully submitted tool outputs for run {run_id}")
                            # Loop to re-poll status after tool execution
                            await asyncio.sleep(0.5)
                            continue
                        except Exception as submit_error:
                            logger.error(f"Failed to submit tool outputs: {submit_error}")
                            break
                    else:
                        logger.warning(f"No tool outputs were produced for run {run_id}")
                        break
                elif status in {"completed", "failed", "cancelled"}:
                    logger.info(f"Run {run_id} reached terminal status: {status}")
                    return run
                else:
                    logger.debug(f"Run {run_id} status: {status}, waiting...")
                    await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Error processing run {run_id}: {e}")
            logger.error(f"Run {run_id} processing failed, returning last known state")
        # Fallback return last known run state
        try:
            return await asyncio.to_thread(
                self.agents_client.runs.get,
                thread_id=thread_id,
                run_id=run_id
            )
        except Exception as fallback_e:
            logger.error(f"Failed to get fallback run state: {fallback_e}")
            # Return a mock run object with failed status
            class MockRun:
                def __init__(self):
                    self.status = "failed"
                    self.last_error = "Failed to retrieve run state"
            return MockRun()