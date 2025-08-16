import redis.asyncio as redis
import json
from typing import Optional, Any

class RedisService:
    def __init__(self, host: str, password: str):
        self.redis = redis.Redis(
            host=host,
            port=6380,
            password=password,
            ssl=True
        )
        
    async def get_chat_history(self, user_id: str) -> list[dict]:
        history_str = await self.redis.get(f"chat_history:{user_id}")
        return json.loads(history_str) if history_str else []
    
    async def add_message_to_history(self, user_id: str, message: dict):
        history = await self.get_chat_history(user_id)
        history.append(message)
        # Keep only the last 10 messages
        max_history_length = 10
        if len(history) > max_history_length:
            history = history[-max_history_length:]
        await self.redis.set(f"chat_history:{user_id}", json.dumps(history))