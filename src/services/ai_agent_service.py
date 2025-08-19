import asyncio
import json
import logging
import hashlib
from typing import Dict, Optional, Any, List
from concurrent.futures import ThreadPoolExecutor
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    AsyncFunctionTool,
    AsyncToolSet,
    RequiredFunctionToolCall,
    SubmitToolOutputsAction,
    ToolOutput,
    MessageDeltaChunk,
    AgentStreamEvent,
)
from azure.identity import DefaultAzureCredential
from ..config import settings
import httpx
from . import tools as tools_service

logger = logging.getLogger(__name__)

# Shared executor for running blocking SDK calls without blocking the event loop
_EXECUTOR = ThreadPoolExecutor(max_workers=10)

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
        """Initialize function tools for agent integration"""
        # Define the tool functions that will be available to the agent (metadata functions)
        self.tool_functions = [
            tools_service.get_claim_by_contact_info,
            tools_service.initiate_new_claim,
            tools_service.transition_claim_type,
            tools_service.update_claim_data,
        ]
        
        # Create FunctionTool definitions for the agent
        self.function_tools = AsyncFunctionTool(functions=self.tool_functions)
        
        # Initialize AsyncToolSet with the function tools
        self.toolset = AsyncToolSet()
        self.toolset.add(self.function_tools)
        
        # Store the actual implementations for direct execution when needed
        self.tool_implementations = {
            "get_claim_by_contact_info": tools_service.get_claim_by_contact_info,
            "initiate_new_claim": tools_service.initiate_new_claim,
            "transition_claim_type": tools_service.transition_claim_type,
            "update_claim_data": tools_service.update_claim_data,
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
                
                # Create agent with function tools
                agent = await asyncio.to_thread(
                    self.agents_client.create_agent,
                    name=agent_name,
                    instructions=instructions or "",
                    model=resolved_model,
                    tools=self.function_tools.definitions  # Add function tool definitions
                )
                self.agent_ids[agent_name] = agent.id
                logger.info(f"Created agent '{agent_name}' with ID {agent.id}")
                return agent.id
        except Exception as e:
            logger.error(f"Error in create_or_get_agent for {agent_name}: {str(e)}")
            raise

            
    async def get_or_create_thread(self, user_id: str) -> str:
        """Get existing thread_id from Redis or create a new one for the user."""
        if not self.redis:
            raise ConnectionError("Redis client is not initialized.")
        
        try:
            thread_id_key = f"thread_id:{user_id}"
            
            # Try to get existing thread from Redis
            thread_id_bytes = await self.redis.get(thread_id_key)
            if thread_id_bytes:
                thread_id = thread_id_bytes.decode() if isinstance(thread_id_bytes, bytes) else thread_id_bytes
                
                # Validate that the thread still exists on Azure
                try:
                    await asyncio.to_thread(
                        self.agents_client.threads.get,
                        thread_id=thread_id
                    )
                    
                    # Check for active runs before reusing the thread
                    has_active_run = await self._has_active_run(thread_id)
                    if has_active_run:
                        logger.warning(f"Thread {thread_id} has active runs, waiting...")
                        # Wait a bit and check again
                        await asyncio.sleep(2)
                        has_active_run = await self._has_active_run(thread_id)
                        if has_active_run:
                            logger.error(f"Thread {thread_id} still has active runs, creating new thread")
                            await self.redis.delete(thread_id_key)
                            # Fall through to create new thread
                        else:
                            logger.info(f"Using existing thread {thread_id} for user {user_id}")
                            return thread_id
                    else:
                        logger.info(f"Using existing thread {thread_id} for user {user_id}")
                        return thread_id
                        
                except Exception as e:
                    logger.warning(f"Thread {thread_id} validation failed, creating new one: {e}")
                    # Thread doesn't exist anymore, delete from cache and create new
                    await self.redis.delete(thread_id_key)
            
            # Create new thread
            thread = await asyncio.to_thread(self.agents_client.threads.create)
            
            # Store in Redis with TTL (optional - adjust TTL as needed)
            ttl_seconds = 24 * 60 * 60  # 24 hours
            await self.redis.setex(thread_id_key, ttl_seconds, thread.id)
            
            logger.info(f"Created new thread {thread.id} for user {user_id} and saved to Redis")
            return thread.id
            
        except Exception as e:
            logger.error(f"Error getting/creating thread for user {user_id}: {str(e)}")
            raise    
        
        # """Create a new thread for the user."""
        # try:
        #     thread = await asyncio.to_thread(self.agents_client.threads.create)
        #     logger.info(f"Created new thread {thread.id} for user {user_id}")
        #     return thread.id
        # except Exception as e:
        #     logger.error(f"Error creating thread for user {user_id}: {str(e)}")
        #     raise

    async def get_agent_response(
        self,
        agent_name: str,
        user_id: str,
        user_message: str,
        chat_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Get a response from the agent using thread reuse for conversation context.
        Simplified approach based on working reference.
        """
        logger.info(f"get_agent_response called with agent_name={agent_name}, user_id={user_id}")
        try:
            agent_id = await self.create_or_get_agent(agent_name)
            
            # Get or create thread ID from cache
            thread_id_key = f"thread_id:{user_id}"
            thread_id = None
            
            if self.redis:
                thread_id_bytes = await self.redis.get(thread_id_key)
                if thread_id_bytes:
                    thread_id = thread_id_bytes.decode() if isinstance(thread_id_bytes, bytes) else thread_id_bytes
                    logger.info(f"Using existing thread {thread_id} for user {user_id}")
            
            if not thread_id:
                logger.info(f"No existing thread found, creating a new one for user {user_id}")
                
                # Prepare initial messages including chat history and current message
                initial_messages = []
                if chat_history:
                    # Add historical messages (excluding system messages)
                    for msg in chat_history:
                        if msg.get("role") in ["user", "assistant"]:
                            initial_messages.append({
                                "role": msg["role"],
                                "content": msg["content"]
                            })
                
                # Add the current user message
                initial_messages.append({"role": "user", "content": user_message})
                
                # Create thread with initial messages using synchronous call wrapped in executor
                def create_thread_with_messages():
                    return self.agents_client.threads.create(messages=initial_messages)
                
                new_thread = await asyncio.to_thread(create_thread_with_messages)
                thread_id = new_thread.id
                
                # Cache the thread ID
                if self.redis:
                    ttl_seconds = 24 * 60 * 60  # 24 hours
                    await self.redis.setex(thread_id_key, ttl_seconds, thread_id)
                
                logger.info(f"Created new thread {thread_id} for user {user_id} and saved to Redis")
            else:
                # Add the new user message to the existing thread
                try:
                    def add_message_to_thread():
                        return self.agents_client.messages.create(
                            thread_id=thread_id,
                            content=user_message,
                            role="user"
                        )
                    
                    await asyncio.to_thread(add_message_to_thread)
                    logger.info(f"Added user message to existing thread {thread_id}")
                except Exception as e:
                    logger.error(f"Error adding message to thread {thread_id}: {e}")
                    return "I'm sorry, I couldn't add your message to the conversation. Please try again."
            
            logger.info(f"Sending request to agent {agent_name} for thread {thread_id}")
            
            try:
                # Create and run the agent using synchronous calls
                def create_and_run():
                    return self.agents_client.runs.create(
                        thread_id=thread_id,
                        agent_id=agent_id
                    )
                
                run = await asyncio.to_thread(create_and_run)
                run_id = run.id
                logger.info(f"Created run {run_id} for thread {thread_id}")
                
                # Poll the run until completion
                max_wait_time = 60  # 60 seconds timeout
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    if asyncio.get_event_loop().time() - start_time > max_wait_time:
                        logger.error(f"Run {run_id} processing timed out after {max_wait_time} seconds")
                        return "I'm sorry, the request took too long to process. Please try again."
                    
                    def get_run_status():
                        return self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
                    
                    run = await asyncio.to_thread(get_run_status)
                    status_obj = getattr(run, "status", "")
                    status_str = str(status_obj)
                    if "." in status_str:
                        status_str = status_str.split(".")[-1]
                    status = status_str.strip().lower()
                    
                    logger.info(f"Run {run_id} status: {status}")
                    
                    if status == "requires_action":
                        required_action = getattr(run, "required_action", None)
                        if required_action and hasattr(required_action, "submit_tool_outputs"):
                            tool_calls = required_action.submit_tool_outputs.tool_calls
                            if not tool_calls:
                                logger.warning("No tool calls provided - cancelling run")
                                break
                            
                            # Execute tool calls
                            tool_outputs = await self.toolset.execute_tool_calls(tool_calls)
                            logger.info(f"Tool outputs: {tool_outputs}")
                            
                            if tool_outputs:
                                def submit_tool_outputs():
                                    return self.agents_client.runs.submit_tool_outputs(
                                        thread_id=thread_id,
                                        run_id=run_id,
                                        tool_outputs=tool_outputs
                                    )
                                
                                await asyncio.to_thread(submit_tool_outputs)
                                logger.info(f"Submitted tool outputs for run {run_id}")
                    elif status in {"completed", "failed", "cancelled"}:
                        logger.info(f"Run {run_id} reached terminal status: {status}")
                        break
                    
                    # Wait before next poll
                    await asyncio.sleep(1)
                
                if status == "failed":
                    error_info = getattr(run, "last_error", "Unknown error")
                    logger.error(f"Run {run_id} failed: {error_info}")
                    return "I'm sorry, I encountered an error processing your request."
                
                # Get the latest messages from the thread
                def get_messages():
                    return list(self.agents_client.messages.list(thread_id=thread_id, limit=5))
                
                messages = await asyncio.to_thread(get_messages)
                logger.info(f"Retrieved {len(messages)} messages from thread {thread_id}")
                
                # Find the most recent assistant message
                for message in messages:
                    if getattr(message, "role", None) == "assistant":
                        content_items = getattr(message, 'content', [])
                        for content_item in content_items:
                            if hasattr(content_item, 'text') and hasattr(content_item.text, 'value'):
                                response_text = content_item.text.value
                                if response_text and response_text.strip():
                                    logger.info(f"Agent {agent_name} responded to user {user_id} with: {response_text[:200]}...")
                                    return response_text
                
                logger.warning(f"No assistant message found in completed run {run_id}")
                return "I'm sorry, I couldn't process your request at this time."
                
            except Exception as e:
                logger.error(f"Error in agent execution: {e}", exc_info=True)
                return "I apologize, but I encountered an error. Please try again."
                
        except Exception as e:
            logger.error(f"Error getting agent response: {str(e)}", exc_info=True)
            return "I'm sorry, I encountered an error. Please try again."
            
    # async def get_agent_response(
    #     self,
    #     agent_name: str,
    #     user_id: str,
    #     user_message: str,
    #     chat_history: Optional[List[Dict]] = None
    # ) -> str:
    #     """
    #     Get a response from the agent using a single API call.
    #     """
    #     logger.info(f"get_agent_response_single_call called with agent_name={agent_name}, user_id={user_id}, user_message={user_message}")
    #     try:
    #         agent_id = await self.create_or_get_agent(agent_name)
    #         thread_id = await self.get_or_create_thread(user_id)
            
    #         # Add the user message to the thread
    #         await asyncio.to_thread(
    #             self.agents_client.messages.create,
    #             thread_id=thread_id,
    #             role="user",
    #             content=user_message
    #         )
            
    #         # Create a run
    #         run = await asyncio.to_thread(
    #             self.agents_client.runs.create,
    #             thread_id=thread_id,
    #             agent_id=agent_id
    #         )
            
    #         # Poll the run as long as run status is queued or in progress
    #         while run.status in {"queued", "in_progress", "requires_action"}:
    #             await asyncio.sleep(1)
    #             run = await asyncio.to_thread(
    #                 self.agents_client.runs.get,
    #                 thread_id=thread_id,
    #                 run_id=run.id
    #             )
    #             logger.info(f"Run status: {run.status}")
                
    #             if run.status == "requires_action":
    #                 required_action = getattr(run, "required_action", None)
    #                 if required_action and hasattr(required_action, "submit_tool_outputs"):
    #                     tool_calls = required_action.submit_tool_outputs.tool_calls
    #                     if not tool_calls:
    #                         logger.warning("No tool calls provided - cancelling run")
    #                         await asyncio.to_thread(
    #                             self.agents_client.runs.cancel,
    #                             thread_id=thread_id,
    #                             run_id=run.id
    #                         )
    #                         break
                        
    #                     # Use the AsyncToolSet to execute tool calls
    #                     tool_outputs = await self.toolset.execute_tool_calls(tool_calls)
    #                     logger.info(f"Tool outputs: {tool_outputs}")
                        
    #                     if tool_outputs:
    #                         await asyncio.to_thread(
    #                             self.agents_client.runs.submit_tool_outputs,
    #                             thread_id=thread_id,
    #                             run_id=run.id,
    #                             tool_outputs=tool_outputs
    #                         )
            
    #         if run.status == "failed":
    #             logger.error(f"Run error: {run.last_error}")
    #             return "I'm sorry, I encountered an error processing your request."
            
    #         # Get the messages from the thread
    #         messages = await asyncio.to_thread(
    #             lambda: list(self.agents_client.messages.list(thread_id=thread_id))
    #         )
            
    #         # Find the last assistant message
    #         for message in reversed(messages):
    #             if getattr(message, "role", None) == "assistant":
    #                 response_text = next((c.text.value for c in message.content if hasattr(c, 'text')), None)
    #                 if response_text:
    #                     logger.info(f"Agent {agent_name} responded to user {user_id} with: {response_text}")
    #                     return response_text
            
    #         logger.warning(f"No assistant message found in completed run {run.id}")
    #         return "I'm sorry, I couldn't process your request at this time."
            
    #     except Exception as e:
    #         logger.error(f"Error getting agent response: {str(e)}", exc_info=True)
    #         return "I'm sorry, I encountered an error. Please try again."
    
  
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
                    logger.info(f"Found active run {run.id} with status {status} for thread {thread_id}")
                    return True
            return False
        except Exception as e:
            logger.warning(f"Failed to list runs for thread {thread_id}: {e}")
            return False

    async def clear_thread(self, user_id: str):
        """Clear the thread for a specific user."""
        if not self.redis:
            logger.warning("Redis not available for thread cleanup")
            return
        
        try:
            thread_id_key = f"thread_id:{user_id}"
            thread_id_bytes = await self.redis.get(thread_id_key)
            
            if thread_id_bytes:
                thread_id = thread_id_bytes.decode() if isinstance(thread_id_bytes, bytes) else thread_id_bytes
                logger.info(f"Clearing thread {thread_id} for user {user_id}")
                
                # Try to cancel any active runs before clearing
                try:
                    def list_and_cancel_runs():
                        runs = list(self.agents_client.runs.list(thread_id=thread_id))
                        for run in runs:
                            status_obj = getattr(run, "status", "")
                            status_str = str(status_obj)
                            if "." in status_str:
                                status_str = status_str.split(".")[-1]
                            status = status_str.strip().lower()
                            
                            if status in {"queued", "in_progress", "requires_action"}:
                                logger.info(f"Cancelling active run {run.id}")
                                self.agents_client.runs.cancel(thread_id=thread_id, run_id=run.id)
                    
                    await asyncio.to_thread(list_and_cancel_runs)
                except Exception as cancel_error:
                    logger.warning(f"Error cancelling runs for thread {thread_id}: {cancel_error}")
            
            # Remove from Redis
            await self.redis.delete(thread_id_key)
            logger.info(f"Cleared thread for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error clearing thread for user {user_id}: {str(e)}")

    async def get_thread_status(self, user_id: str) -> Optional[str]:
        """Get the current thread ID for a user if it exists."""
        if not self.redis:
            return None
        
        try:
            thread_id_key = f"thread_id:{user_id}"
            thread_id_bytes = await self.redis.get(thread_id_key)
            if thread_id_bytes:
                return thread_id_bytes.decode() if isinstance(thread_id_bytes, bytes) else thread_id_bytes
            return None
        except Exception as e:
            logger.error(f"Error getting thread status for user {user_id}: {str(e)}")
            return None

    async def force_new_thread(self, user_id: str):
        """Force create a new thread for a user, clearing any existing one."""
        try:
            # Clear existing thread and runs
            await self.clear_thread(user_id)
            
            # Create new thread
            thread = await asyncio.to_thread(self.agents_client.threads.create)
            
            # Store in Redis
            thread_id_key = f"thread_id:{user_id}"
            ttl_seconds = 24 * 60 * 60  # 24 hours
            await self.redis.setex(thread_id_key, ttl_seconds, thread.id)
            
            logger.info(f"Force created new thread {thread.id} for user {user_id}")
            return thread.id
            
        except Exception as e:
            logger.error(f"Error force creating thread for user {user_id}: {str(e)}")
            raise