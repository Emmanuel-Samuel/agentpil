import json
import logging
import time
import asyncio
from typing import Dict, Any, Optional
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import (
    MessageRole,
    ListSortOrder
)

from ..config.config import settings

logger = logging.getLogger(__name__)

class AIAgentService:
    """Simplified Azure AI Foundry agent service following Connected Agents architecture"""
    
    def __init__(self):
        """Initialize the AI Agent Service"""
        self.credential = DefaultAzureCredential()
        self.project_client = None
        self.agents_client = None
        self._connected = False
    
    async def initialize(self):
        """Initialize the Azure AI Project client"""
        try:
            if not self._connected:
                self.project_client = AIProjectClient(
                    endpoint=settings.azure_ai_foundry_endpoint,
                    credential=self.credential,
                )
                
                await self.project_client.__aenter__()
                self.agents_client = self.project_client.agents
                self._connected = True
                
                logger.info("Azure AI Agent Service initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize Azure AI Agent Service: {str(e)}")
            raise
    
    async def close(self):
        """Close the Azure AI Project client"""
        try:
            if self._connected and self.project_client:
                await self.project_client.__aexit__(None, None, None)
                self._connected = False
                logger.info("Azure AI Agent Service closed")
        except Exception as e:
            logger.error(f"Error closing Azure AI Agent Service: {str(e)}")
    
    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread from Azure AI Foundry"""
        try:
            if not self._connected:
                await self.initialize()
            
            # Delete the thread using Azure AI SDK
            await self.agents_client.threads.delete(thread_id=thread_id)
            logger.info(f"Successfully deleted thread {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {str(e)}")
            return False
    
    async def _create_structured_message(self, message: str, user_id: str, claim_id: Optional[str] = None) -> str:
        """Create a structured message with user_id and claim_id"""
        structured_message = {
            "user_id": user_id,
            "claim_id": claim_id if claim_id else None,
            "message": message
        }
        return json.dumps(structured_message)
    
    async def _process_run_and_get_response(self, thread_id: str, run_id: str) -> Dict[str, Any]:
        """Wait for run completion and get the agent's response"""
        try:
            # Wait for completion if needed
            run = await self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
            while run.status in ["queued", "in_progress"]:
                await asyncio.sleep(1)
                run = await self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
            
            if run.status == "failed":
                logger.error(f"Run failed: {run.last_error}")
                return {
                    "success": False,
                    "message": "I'm sorry, I encountered an error processing your request.",
                    "agent_type": "error_handler"
                }
            
            # Get messages
            messages = self.agents_client.messages.list(thread_id=thread_id, order=ListSortOrder.DESCENDING)
            
            async for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    response_text = msg.text_messages[-1].text.value
                    
                    return {
                        "success": True,
                        "message": response_text,
                        "agent_type": "assistant"
                    }
            
            return {
                "success": False,
                "message": "No response generated",
                "agent_type": "assistant"
            }
        except Exception as e:
            logger.error(f"Error processing run: {str(e)}")
            return {
                "success": False,
                "message": "I'm sorry, I encountered an error processing your request.",
                "agent_type": "error_handler"
            }
    
    async def process_message(
        self,
        message: str,
        user_id: str,
        thread_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        claim_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a message with the AI agent"""
        try:
            # Create or get thread
            if thread_id:
                # Get existing thread
                thread = await self.agents_client.threads.get(thread_id=thread_id)
            else:
                # Create new thread
                thread = await self.agents_client.threads.create()
                thread_id = thread.id
            
            # Create a structured message with explicit user_id and claim_id
            structured_message_content = await self._create_structured_message(message, user_id, claim_id)
            
            # Add message to thread
            await self.agents_client.messages.create(
                thread_id=thread_id,
                role=MessageRole.USER,
                content=structured_message_content
            )
            
            # Create and process run
            run = await self.agents_client.runs.create_and_process(
                thread_id=thread_id,
                agent_id=settings.main_orchestrator_agent_id
            )
            
            # Get the response
            response = await self._process_run_and_get_response(thread_id, run.id)
            
            return {
                **response,
                "thread_id": thread_id,
                "conversation_id": conversation_id or f"conv_{user_id}_{int(time.time())}",
            }
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {
                "success": False,
                "message": "I'm sorry, I encountered an error processing your request.",
                "thread_id": thread_id,
                "conversation_id": conversation_id,
                "agent_type": "error_handler"
            }
    
    async def chat_with_orchestrator(self, message: str, user_id: str, 
                                   conversation_id: Optional[str] = None,
                                   claim_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to the orchestrator agent - the single entry point"""
        try:
            if not self._connected:
                await self.initialize()
            
            if not settings.main_orchestrator_agent_id:
                raise ValueError("MAIN_ORCHESTRATOR_AGENT_ID not configured")
            
            # Create new thread for each conversation (Azure AI handles context natively)
            thread = await self.agents_client.threads.create()
            
            # Create a structured message with explicit user_id and claim_id
            structured_message_content = await self._create_structured_message(message, user_id, claim_id)
            
            # Add message to thread
            await self.agents_client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=structured_message_content
            )
            
            # Let orchestrator agent handle routing to specialized agents via Connected Agents
            run = await self.agents_client.runs.create_and_process(
                thread_id=thread.id,
                agent_id=settings.main_orchestrator_agent_id
            )
            
            # Get the response
            response = await self._process_run_and_get_response(thread.id, run.id)
            
            return {
                **response,
                "thread_id": thread.id,
                "conversation_id": conversation_id or f"conv_{user_id}_{int(time.time())}",
                "user_id": user_id,
                "timestamp": time.time(),
            }
                
        except Exception as e:
            logger.error(f"Error in chat_with_orchestrator: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "I'm sorry, I encountered an error. Please try again later."
            }
    
    async def continue_chat_with_orchestrator(self, message: str, user_id: str, thread_id: str,
                                            conversation_id: Optional[str] = None,
                                            claim_id: Optional[str] = None) -> Dict[str, Any]:
        """Continue a conversation with the orchestrator agent using an existing thread"""
        try:
            if not self._connected:
                await self.initialize()
            
            if not settings.main_orchestrator_agent_id:
                raise ValueError("MAIN_ORCHESTRATOR_AGENT_ID not configured")
            
            # Create a structured message with explicit user_id and claim_id
            structured_message_content = await self._create_structured_message(message, user_id, claim_id)
            
            # Add message to existing thread
            await self.agents_client.messages.create(
                thread_id=thread_id,
                role=MessageRole.USER,
                content=structured_message_content
            )
            
            # Let orchestrator agent handle routing to specialized agents via Connected Agents
            run = await self.agents_client.runs.create_and_process(
                thread_id=thread_id,
                agent_id=settings.main_orchestrator_agent_id
            )
            
            # Get the response
            response = await self._process_run_and_get_response(thread_id, run.id)
            
            return {
                **response,
                "thread_id": thread_id,
                "conversation_id": conversation_id or f"conv_{user_id}_{int(time.time())}",
                "user_id": user_id,
                "timestamp": time.time(),
            }
                
        except Exception as e:
            logger.error(f"Error in continue_chat_with_orchestrator: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "I'm sorry, I encountered an error. Please try again later."
            }
    
    async def chat_with_initial_agent(self, message: str, user_id: str, claim_id: Optional[str] = None) -> Dict[str, Any]:
        """Initial intake endpoint - routes to orchestrator via Connected Agents architecture"""
        logger.info("Initial intake request routing to orchestrator (Connected Agents architecture)")
        return await self.chat_with_orchestrator(message, user_id, claim_id=claim_id)
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get basic agent service status"""
        try:
            if not self._connected:
                await self.initialize()
            
            return {
                "connected": self._connected,
                "project_endpoint": settings.azure_ai_foundry_endpoint,
                "model_deployment": settings.azure_ai_foundry_deployment_model_name,
                "orchestrator_agent_id": settings.main_orchestrator_agent_id,
                "architecture": "Azure Connected Agents",
                "status": "operational" if self._connected else "disconnected"
            }
            
        except Exception as e:
            logger.error(f"Error getting agent status: {str(e)}")
            return {
                "connected": False,
                "error": str(e),
                "status": "error"
            }

# Global service instance
ai_agent_service = AIAgentService()