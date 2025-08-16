import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import HttpResponseError
from pathlib import Path
from ..config import settings

logger = logging.getLogger(__name__)

class AIAgentService:
    """Service for managing AI agents using Azure AI Foundry."""
    
    def __init__(self):
        try:
            self.credential = DefaultAzureCredential()
            
            # Initialize the Agents client
            self.agents_client = AgentsClient(
                endpoint=settings.AZURE_AI_FOUNDRY_ENDPOINT,
                credential=self.credential
            )
            
            # Store agent IDs (not instances, as agents are deployed separately)
            self.agent_ids: Dict[str, str] = {}
            self.threads: Dict[str, str] = {}  # user_id -> thread_id mapping
            
            # Use deployment model name from settings
            self.deployment_model_name = settings.AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME
            
            logger.info("AIAgentService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AIAgentService: {str(e)}")
            raise

    async def create_or_get_agent(self, agent_name: str, instructions: str, model: Optional[str] = None) -> str:
        """Get agent ID from environment or create new agent."""
        try:
            # Check if agent ID is already cached
            if agent_name in self.agent_ids:
                logger.info(f"Using cached agent ID for: {agent_name}")
                return self.agent_ids[agent_name]
            
            # Try to get agent ID from environment variables
            agent_id_env_var = f"{agent_name.upper()}_ID"
            if hasattr(settings, agent_id_env_var):
                agent_id = getattr(settings, agent_id_env_var)
                if agent_id:
                    self.agent_ids[agent_name] = agent_id
                    logger.info(f"Using deployed agent ID for: {agent_name}")
                    return agent_id
            
            # If not found in environment, create new agent
            logger.info(f"Creating new agent: {agent_name}")
            try:
                agent = self.agents_client.create_agent(
                    name=agent_name,
                    instructions=instructions,
                    model=model or self.deployment_model_name,
                    tools=[]  # Tools will be added in Phase 3
                )
                
                self.agent_ids[agent_name] = agent.id
                logger.info(f"Created agent {agent_name} with ID: {agent.id}")
                return agent.id
                
            except HttpResponseError as http_error:
                logger.error(f"HTTP error creating agent {agent_name}: {http_error}")
                raise
            except Exception as e:
                logger.error(f"Error creating agent {agent_name}: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error in create_or_get_agent for {agent_name}: {str(e)}")
            raise

    async def get_or_create_thread(self, user_id: str) -> str:
        """Get or create a thread for a user."""
        try:
            if user_id in self.threads:
                thread_id = self.threads[user_id]
                logger.debug(f"Using existing thread {thread_id} for user {user_id}")
                return thread_id
            
            # Create new thread
            thread = self.agents_client.threads.create()
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
        """Get a response from an AI agent."""
        try:
            # Get agent ID
            agent_id = await self.create_or_get_agent(agent_name, "")
            thread_id = await self.get_or_create_thread(user_id)
            
            # Add user message to thread
            message = self.agents_client.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_message
            )
            logger.debug(f"Created message {message.id} in thread {thread_id}")
            
            # Create and run the agent
            run = self.agents_client.runs.create(
                thread_id=thread_id,
                agent_id=agent_id
            )
            logger.debug(f"Created run {run.id} for agent {agent_id}")
            
            # Poll for completion
            max_attempts = 60  # 60 seconds timeout
            attempt = 0
            
            while run.status in ["queued", "in_progress", "requires_action"] and attempt < max_attempts:
                await asyncio.sleep(1)
                run = self.agents_client.runs.get(thread_id=thread_id, run_id=run.id)
                attempt += 1
                
                if attempt % 10 == 0:  # Log every 10 seconds
                    logger.debug(f"Run {run.id} still in progress, status: {run.status}")
            
            if run.status == "completed":
                # Get the latest messages from the thread, newest first
                messages = self.agents_client.messages.list(thread_id=thread_id, order="desc")
                
                # Find the first assistant message in the list (which will be the latest)
                for message in messages:
                    if message.role == "assistant":
                        response_text = None
                        # Get the content from the message
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
                logger.warning(f"Agent run {run.id} timed out with status: {run.status}")
                return "I'm sorry, your request is taking longer than expected. Please try again."
                
        except Exception as e:
            logger.error(f"Error getting agent response: {str(e)}", exc_info=True)
            return "I'm sorry, I encountered an error while processing your request. Please try again."

    async def cleanup_thread(self, user_id: str):
        """Clean up a user's thread."""
        if user_id in self.threads:
            del self.threads[user_id]
            logger.info(f"Cleaned up thread for user {user_id}")

    def close(self):
        """Close the credential connection."""
        try:
            self.credential.close()
            logger.info("AIAgentService credentials closed")
        except Exception as e:
            logger.error(f"Error closing credentials: {str(e)}")
