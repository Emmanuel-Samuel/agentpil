
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
                return self.agent_ids[agent_name]
            else:
                error_message = f"Agent ID for '{agent_name}' not found in configuration."
                logger.error(error_message)
                raise ValueError(error_message)
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
            # Add user message to thread
            message = await asyncio.to_thread(
                self.agents_client.messages.create,
                thread_id=thread_id,
                role="user",
                content=user_message
            )
            logger.debug(f"Created message {message.id} in thread {thread_id}")
            # Create and run the agent (SDK handles polling and tool calls)
            run = await asyncio.to_thread(
                self.agents_client.runs.create_and_process,
                thread_id=thread_id,
                agent_id=agent_id
            )
            logger.debug(f"Created and processed run {run.id} for agent {agent_id}")
            # Check run status and fetch assistant message
            if run.status == "completed":
                messages = await asyncio.to_thread(self.agents_client.messages.list, thread_id=thread_id)
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
        run = await self._start_run(agent_id=agent_id, thread_id=thread_id)

        # Use a queue to push tokens from blocking stream (thread) to async generator
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _producer():
            try:
                from azure.ai.agents.models import MessageDeltaChunk, AgentStreamEvent
                with self.agents_client.runs.stream(thread_id=thread_id, agent_id=agent_id) as stream:
                    for event_type, event_data, _ in stream:
                        if isinstance(event_data, MessageDeltaChunk):
                            text = getattr(event_data, "text", None)
                            if text:
                                token_queue.put_nowait(text)
                        elif event_type == AgentStreamEvent.ERROR:
                            token_queue.put_nowait("[ERROR]")
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
