import asyncio
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Add the src directory to the Python path
sys.path.append(str(Path(__file__).parent))
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


from .config import settings
from .services.redis_service import RedisService
from .services.cosmosdb_service import CosmosDBService
from .services.ai_agent_service import AIAgentService
from .services.poml_service import POMLService
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
poml_service: Optional[POMLService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    global redis_service, cosmosdb_service, ai_agent_service, poml_service
    
    try:
        # Initialize services
        logger.info("Initializing services...")
        
        logger.info("Initializing RedisService...")
        redis_service = RedisService()
        logger.info("RedisService initialized.")
        
        logger.info("Initializing CosmosDBService...")
        cosmosdb_service = CosmosDBService(
            url=settings.COSMOS_DB_URL,
            key=settings.COSMOS_DB_KEY,
            database_name=settings.COSMOS_DB_DATABASE_NAME,
            container_name=settings.COSMOS_DB_CONTAINER_NAME
        )
        await cosmosdb_service.initialize()
        logger.info("CosmosDBService initialized.")

        logger.info("Initializing tools service...")
        tools_service.initialize_tools(cosmosdb_service)
        logger.info("Tools service initialized.")
        
        logger.info("Initializing AIAgentService...")
        ai_agent_service = AIAgentService(redis_client=redis_service.redis)
        logger.info("AIAgentService initialized.")
        
        logger.info("Initializing POMLService...")
        poml_service = POMLService(prompts_directory=settings.PROMPTS_DIRECTORY)
        logger.info("POMLService initialized.")
        
        # Initialize AI agents with POML templates
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
    """Initialize AI agents with their POML-defined instructions."""
    try:
        # Initialize Initial Intake Agent
        initial_instructions = poml_service.get_agent_instructions("initial_agent")
        await ai_agent_service.create_or_get_agent(
            agent_name="initial_intake_agent",
            instructions=initial_instructions
        )
        logger.info("Initialized initial_intake_agent")
        
        # Initialize Portal Agent (for future use)
        portal_instructions = poml_service.get_agent_instructions("portal_agent")
        logger.info(f"Portal agent instructions loaded: {portal_instructions[:200]}...")
        await ai_agent_service.create_or_get_agent(
            agent_name="portal_claim_agent", 
            instructions=portal_instructions
        )
        logger.info("Initialized portal_claim_agent")
        
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
    try:
        user_id = chat_message.user_id
        user_message = chat_message.message
        
        logger.info(f"Initial chat request from user {user_id}: {user_message}")
        
        # Get conversation history from Redis
        history = await redis_service.get_chat_history(user_id)
        
        # Get POML context for the agent
        poml_context = {
            'user_message': user_message,
            'user_id': user_id,
        }
        
        # Get response from Initial Intake Agent
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
    try:
        user_id = chat_message.user_id
        user_message = chat_message.message
        
        logger.info(f"Portal chat request from user {user_id}: {user_message}")
        
        # Get conversation history from Redis
        history = await redis_service.get_chat_history(user_id)
        
        # Get POML context for the agent
        poml_context = {
            'user_message': user_message,
            'user_id': user_id,
        }
        
        # Get response from Portal Claim Agent
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

@app.post("/chat/stream")
async def chat_stream_endpoint(chat_message: ChatMessage):
    """Stream agent response tokens for real-time UX."""
    async def token_generator():
        async for token in ai_agent_service.stream_agent_response(
            agent_name="portal_claim_agent",  # or make this dynamic
            user_id=chat_message.user_id,
            user_message=chat_message.message
        ):
            yield token
    return StreamingResponse(token_generator(), media_type="text/plain")

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
        "active_threads": len(ai_agent_service.threads),
        "available_templates": poml_service.list_templates() if poml_service else []
    }

@app.delete("/chat/{user_id}/history")
async def clear_chat_history(user_id: str):
    """
    Clear chat history for a specific user.
    """
    await redis_service.redis.delete(f"chat_history:{user_id}")
    return {"message": f"Chat history for user {user_id} cleared."}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
