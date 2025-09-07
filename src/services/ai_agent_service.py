import json
import logging
import time
import asyncio
from typing import Dict, Any, Optional
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import MessageRole, ListSortOrder

from ..config.config import settings

logger = logging.getLogger(__name__)

class AIAgentService:
    """Simplified Azure AI Foundry agent service"""
    
    def __init__(self):
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
                
                logger.info("Azure AI Agent Service initialized")
                
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
    
    async def chat(
        self,
        message: str,
        user_id: str,
        thread_id: Optional[str] = None,
        claim_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified chat method - handles all agent interactions
        
        Args:
            message: User message
            user_id: User identifier
            thread_id: Optional existing thread ID for conversation continuity
            claim_id: Optional claim ID for context
            
        Returns:
            Response with agent message and thread info
        """
        try:
            if not self._connected:
                await self.initialize()
            
            if not settings.main_orchestrator_agent_id:
                raise ValueError("MAIN_ORCHESTRATOR_AGENT_ID not configured")
            
            # Create or use existing thread
            if thread_id:
                thread = await self.agents_client.threads.get(thread_id=thread_id)
            else:
                thread = await self.agents_client.threads.create()
                thread_id = thread.id
            
            # Create structured message with context
            structured_message = {
                "user_id": user_id,
                "message": message
            }
            
            # Only include claim_id if it's a valid, non-null value
            if claim_id and isinstance(claim_id, str) and claim_id.strip() and claim_id.lower() != "null":
                structured_message["claim_id"] = claim_id
            
            # Debug: Log what we're actually sending to the agent
            message_content = json.dumps(structured_message)
            logger.info(f"Sending to AI agent: {message_content}")
            
            # Add message to thread
            await self.agents_client.messages.create(
                thread_id=thread_id,
                role=MessageRole.USER,
                content=message_content
            )
            
            # Create and process run
            run = await self.agents_client.runs.create_and_process(
                thread_id=thread_id,
                agent_id=settings.main_orchestrator_agent_id
            )
            
            # Wait for completion and get response
            response = await self._get_agent_response(thread_id, run.id)
            
            return {
                **response,
                "thread_id": thread_id,
                "user_id": user_id,
                "timestamp": time.time()
            }
                
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "I'm sorry, I encountered an error. Please try again later.",
                "thread_id": thread_id
            }
    
    async def _get_agent_response(self, thread_id: str, run_id: str) -> Dict[str, Any]:
        """Wait for run completion and extract agent response"""
        try:
            # Wait for completion
            run = await self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
            while run.status in ["queued", "in_progress"]:
                await asyncio.sleep(1)
                run = await self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
            
            if run.status == "failed":
                logger.error(f"Run failed: {run.last_error}")
                return {
                    "success": False,
                    "message": "I encountered an error processing your request."
                }
            
            # Get latest agent message
            messages = self.agents_client.messages.list(
                thread_id=thread_id, 
                order=ListSortOrder.DESCENDING
            )
            
            async for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    return {
                        "success": True,
                        "message": msg.text_messages[-1].text.value
                    }
            
            return {
                "success": False,
                "message": "No response generated"
            }
            
        except Exception as e:
            logger.error(f"Error getting agent response: {str(e)}")
            return {
                "success": False,
                "message": "I encountered an error processing your request."
            }
    
    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread"""
        try:
            if not self._connected:
                await self.initialize()
            
            await self.agents_client.threads.delete(thread_id=thread_id)
            logger.info(f"Deleted thread {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {str(e)}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        try:
            if not self._connected:
                await self.initialize()
            
            return {
                "connected": self._connected,
                "endpoint": settings.azure_ai_foundry_endpoint,
                "agent_id": settings.main_orchestrator_agent_id,
                "status": "operational" if self._connected else "disconnected"
            }
            
        except Exception as e:
            logger.error(f"Error getting status: {str(e)}")
            return {
                "connected": False,
                "error": str(e),
                "status": "error"
            }

# Global service instance
ai_agent_service = AIAgentService()
