from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from .config.config import Settings
from .services.redis_service import RedisService
from .services.cosmosdb_service import CosmosDBService
import asyncio
import sys


app = FastAPI()

redis_service = RedisService(host=Settings.REDIS_URL, password=Settings.REDIS_PASSWORD)
cosmosdb_service = CosmosDBService(
    url=Settings.COSMOS_DB_URL,
    key=Settings.COSMOS_DB_KEY,
    database_name=Settings.COSMOS_DB_DATABASE_NAME,
    container_name=Settings.COSMOS_DB_CONTAINER_NAME
)

class ChatMessage(BaseModel):
    user_id: str
    message: str
    
@app.post("/chat")
async def chat_endpoint(chat_message: ChatMessage):
    user_id = chat_message.user_id
    user_message = chat_message.message
    
    # Get history from redis
    history = await redis_service.get_chat_history(user_id)
    history.append({"role": "user", "content": user_message})
    
    # Simulate a response
    response_content = f"Echo: {user_message}"
    history.append({"role": "assistant", "content": response_content})
    
    # Save to Redis
    await redis_service.add_message_to_history(user_id, {"role": "user", "content": user_message})
    await redis_service.add_message_to_history(user_id, {"role": "assistant", "content": response_content})
    
    # Save conversation to CosmosDB
    asyncio.create_task(cosmosdb_service.save_conversation(user_id, history))
    
    return {"response": response_content, "history": history}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)