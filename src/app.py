import asyncio
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


from .config import settings
from .services.redis_service import RedisService
from .services.cosmosdb_service import CosmosDBService
from .services.ai_agent_service import AIAgentService

from .services import tools as tools_service

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Reduce Azure SDK HTTP logging verbosity
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global service instances
redis_service: Optional[RedisService] = None
cosmosdb_service: Optional[CosmosDBService] = None
ai_agent_service: Optional[AIAgentService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    global redis_service, cosmosdb_service, ai_agent_service
    
    try:
        # Initialize services
        logger.info("Initializing services...")
        
        logger.info("Initializing RedisService...")
        redis_service = RedisService()
        logger.info("RedisService initialized.")
        
        logger.info("Initializing CosmosDBService...")
        if settings.COSMOS_DB_URL and settings.COSMOS_DB_KEY and settings.COSMOS_DB_DATABASE_NAME and settings.COSMOS_DB_CONTAINER_NAME:
            cosmosdb_service = CosmosDBService(
                url=settings.COSMOS_DB_URL,
                key=settings.COSMOS_DB_KEY,
                database_name=settings.COSMOS_DB_DATABASE_NAME,
                container_name=settings.COSMOS_DB_CONTAINER_NAME
            )
            await cosmosdb_service.initialize()
        else:
            logger.warning("CosmosDB credentials not found, skipping initialization.")
        
        logger.info("Initializing tools service...")
        tools_service.initialize_tools(cosmosdb_service)
        logger.info("Tools service initialized.")
        
        logger.info("Initializing AIAgentService...")
        if redis_service:
            ai_agent_service = AIAgentService(redis_client=redis_service.redis)
            logger.info("AIAgentService initialized.")
        else:
            logger.warning("Redis service not available, skipping AIAgentService initialization.")
        
        # Initialize AI agents using pre-deployed agent IDs
        logger.info("Initializing agents...")
        await initialize_agents()
        logger.info("Agents initialized.")
        
        logger.info("Application startup complete")
        yield
        
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        raise
    finally:
        # Cleanup
        logger.info("Application shutdown - cleaning up services...")
        if ai_agent_service:
            ai_agent_service.close()

async def initialize_agents():
    """Initialize AI agents using pre-deployed agent IDs."""
    if not ai_agent_service:
        logger.warning("Skipping agent initialization due to missing AI agent service.")
        return
    try:
        # Initialize agents using pre-deployed agent IDs from environment
        # Agents must be deployed first using deploy_agents.py
        if settings.INITIAL_INTAKE_AGENT_ID:
            await ai_agent_service.create_or_get_agent(
                agent_name="initial_intake_agent",
                agent_id=settings.INITIAL_INTAKE_AGENT_ID
            )
            logger.info("Initialized initial_intake_agent using pre-deployed agent ID")
        else:
            logger.error("INITIAL_INTAKE_AGENT_ID not found in environment variables. Please run deploy_agents.py first.")
        
        if settings.PORTAL_AGENT_ID:
            await ai_agent_service.create_or_get_agent(
                agent_name="portal_claim_agent",
                agent_id=settings.PORTAL_AGENT_ID
            )
            logger.info("Initialized portal_claim_agent using pre-deployed agent ID")
        else:
            logger.error("PORTAL_AGENT_ID not found in environment variables. Please run deploy_agents.py first.")
        
    except Exception as e:
        logger.error(f"Error initializing agents: {str(e)}")
        raise

# Create FastAPI app with lifespan management
app = FastAPI(
    title="AI Chatbot for Law Firm",
    description="A sophisticated AI chatbot system for personal injury law firm",
    version="1.0.0",
    lifespan=lifespan
)

# Pydantic models
class ChatMessage(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    history: list

@app.post("/chat/initial", response_model=ChatResponse)
async def chat_initial_endpoint(chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """Handle initial intake agent conversations."""
    if not redis_service or not ai_agent_service:
        raise HTTPException(status_code=503, detail="Services not available")
    try:
        user_id = chat_message.user_id
        user_message = chat_message.message
        
        logger.info(f"Initial chat request from user {user_id}: {user_message}")
        
        # Get conversation history from Redis
        history = await redis_service.get_chat_history(user_id)
        
        # Get response from Initial Intake Agent using the new method
        ai_response_content = await ai_agent_service.get_agent_response(
            agent_name="initial_intake_agent",
            user_id=user_id,
            user_message=user_message,
            chat_history=history
        )
        
        # Add messages to Redis history (short-term)
        await redis_service.add_message_to_history(user_id, {"role": "user", "content": user_message})
        await redis_service.add_message_to_history(user_id, {"role": "assistant", "content": ai_response_content})
        
        # Get updated history for response
        updated_history = await redis_service.get_chat_history(user_id)
        
        # Save to Cosmos DB in background (long-term)
        if cosmosdb_service:
            background_tasks.add_task(
                cosmosdb_service.save_conversation, 
                user_id, 
                updated_history
            )
        
        logger.info(f"Successfully processed initial chat for user {user_id}")
        
        return ChatResponse(
            response=ai_response_content,
            history=updated_history
        )
        
    except Exception as e:
        logger.error(f"Error in initial chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/chat/portal", response_model=ChatResponse)
async def chat_portal_endpoint(chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """Handle portal agent conversations for authenticated users."""
    if not redis_service or not ai_agent_service:
        raise HTTPException(status_code=503, detail="Services not available")
    try:
        user_id = chat_message.user_id
        user_message = chat_message.message
        
        logger.info(f"Portal chat request from user {user_id}: {user_message}")
        
        # Get conversation history from Redis
        history = await redis_service.get_chat_history(user_id)
        
        # Get response from Portal Claim Agent using the Azure-style method
        ai_response_content = await ai_agent_service.get_agent_response(
            agent_name="portal_claim_agent",
            user_id=user_id,
            user_message=user_message,
            chat_history=history
        )
        
        # Add messages to Redis history (short-term)
        await redis_service.add_message_to_history(user_id, {"role": "user", "content": user_message})
        await redis_service.add_message_to_history(user_id, {"role": "assistant", "content": ai_response_content})
        
        # Get updated history for response
        updated_history = await redis_service.get_chat_history(user_id)
        
        # Save to Cosmos DB in background (long-term)
        if cosmosdb_service:
            background_tasks.add_task(
                cosmosdb_service.save_conversation, 
                user_id, 
                updated_history
            )
        
        logger.info(f"Successfully processed portal chat for user {user_id}")
        
        return ChatResponse(
            response=ai_response_content,
            history=updated_history
        )
        
    except Exception as e:
        logger.error(f"Error in portal chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "agents_initialized": len(ai_agent_service.agent_ids) if ai_agent_service else 0
    }

@app.get("/agents/status")
async def agents_status():
    """Get status of initialized agents."""
    if not ai_agent_service:
        return {"error": "AI Agent Service not initialized"}
    
    return {
        "initialized_agents": list(ai_agent_service.agent_ids.keys()),
        "agent_ids": {
            "initial_intake_agent": settings.INITIAL_INTAKE_AGENT_ID,
            "portal_claim_agent": settings.PORTAL_AGENT_ID
        }
    }

@app.get("/chat/{user_id}/thread_status")
async def get_thread_status(user_id: str):
    """
    Get the current thread status for a user.
    """
    if not ai_agent_service:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        thread_id = await ai_agent_service.get_thread_status(user_id)
        return {
            "user_id": user_id,
            "thread_id": thread_id,
            "has_active_thread": thread_id is not None
        }
    except Exception as e:
        logger.error(f"Error getting thread status for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get thread status")
    
@app.post("/chat/{user_id}/clear_claim_cache")
async def clear_claim_cache(user_id: str):
    """
    Clear the claim cache for a specific user.
    """
    if not redis_service:
        raise HTTPException(status_code=503, detail="Redis service not available")
    
    try:
        # Clear claim info from Redis cache
        await redis_service.redis.delete(f"claim_info:{user_id}")
        return {"message": f"Claim cache for user {user_id} cleared."}
    except Exception as e:
        logger.error(f"Error clearing claim cache for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear claim cache")

@app.delete("/chat/{user_id}/history")
async def clear_chat_history(user_id: str):
    """
    Clear chat history for a specific user.
    """
    if not redis_service:
        raise HTTPException(status_code=503, detail="Redis service not available")
    await redis_service.redis.delete(f"chat_history:{user_id}")
    return {"message": f"Chat history for user {user_id} cleared."}

@app.post("/chat/{user_id}/clear_thread")
async def clear_chat_thread(user_id: str):
    """
    Clear the chat thread and cancel any active runs for a specific user.
    """
    if not ai_agent_service:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        await ai_agent_service.clear_thread(user_id)
        # Also clear Redis chat history for a fresh start
        if redis_service:
            await redis_service.redis.delete(f"chat_history:{user_id}")
        return {"message": f"Chat thread, runs, and history for user {user_id} cleared."}
    except Exception as e:
        logger.error(f"Error clearing thread for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear thread")

@app.post("/chat/{user_id}/force_new_thread")
async def force_new_chat_thread(user_id: str):
    """
    Force create a new thread for a user, clearing any existing one.
    """
    if not ai_agent_service:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        thread_id = await ai_agent_service.force_new_thread(user_id)
        # Also clear Redis chat history for a fresh start
        if redis_service:
            await redis_service.redis.delete(f"chat_history:{user_id}")
        return {
            "message": f"New thread created for user {user_id}",
            "thread_id": thread_id
        }
    except Exception as e:
        logger.error(f"Error creating new thread for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create new thread")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)
