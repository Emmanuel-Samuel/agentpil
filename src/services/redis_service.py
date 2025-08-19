import redis.asyncio as redis
import json
import logging
from typing import Optional, Any
from ..config import settings

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        # Configure Redis connection based on settings
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_USE_SSL,
            decode_responses=False  # We'll handle JSON encoding manually
        )
        
    async def get_chat_history(self, user_id: str) -> list[dict]:
        """Get chat history for a user with TTL handling."""
        try:
            history_str = await self.redis.get(f"chat_history:{user_id}")
            if history_str:
                return json.loads(history_str)
            return []
        except Exception as e:
            logger.error(f"Error getting chat history for user {user_id}: {e}")
            return []
    
    async def add_message_to_history(self, user_id: str, message: dict):
        """Add message to chat history with TTL and length limits."""
        try:
            history = await self.get_chat_history(user_id)
            history.append(message)
            
            # Keep only the last N messages
            max_length = int(settings.REDIS_MAX_HISTORY_LENGTH)
            if len(history) > max_length:
                history = history[-max_length:]
            
            # Set with TTL
            ttl_seconds = int(settings.REDIS_HISTORY_TTL_HOURS) * 3600
            await self.redis.setex(
                f"chat_history:{user_id}",
                ttl_seconds,
                json.dumps(history)
            )
            
            logger.debug(f"Added message to history for user {user_id}, total messages: {len(history)}")
            
        except Exception as e:
            logger.error(f"Error adding message to history for user {user_id}: {e}")
    
    async def set_chat_history(self, user_id: str, history: list[dict]):
        """Set complete chat history for a user."""
        try:
            ttl_seconds = int(settings.REDIS_HISTORY_TTL_HOURS) * 3600
            await self.redis.setex(
                f"chat_history:{user_id}",
                ttl_seconds,
                json.dumps(history)
            )
            logger.debug(f"Set chat history for user {user_id} with {len(history)} messages")
        except Exception as e:
            logger.error(f"Error setting chat history for user {user_id}: {e}")
    
    async def clear_chat_history(self, user_id: str):
        """Clear chat history for a user."""
        try:
            await self.redis.delete(f"chat_history:{user_id}")
            logger.info(f"Cleared chat history for user {user_id}")
        except Exception as e:
            logger.error(f"Error clearing chat history for user {user_id}: {e}")
    
    async def save_claim_info(self, user_id: str, claim_info: dict):
        """Save claim information to Redis."""
        try:
            claim_key = f"claim_info:{user_id}"
            await self.redis.set(claim_key, json.dumps(claim_info))
            logger.info(f"Saved claim info for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving claim info for user {user_id}: {str(e)}")

    async def get_claim_info(self, user_id: str) -> Optional[dict]:
        """Get claim information from Redis."""
        try:
            claim_key = f"claim_info:{user_id}"
            claim_data = await self.redis.get(claim_key)
            if claim_data:
                logger.info(f"Retrieved claim info from Redis for user {user_id}")
                return json.loads(claim_data)
            return None
        except Exception as e:
            logger.error(f"Error getting claim info for user {user_id}: {str(e)}")
            return None
    
    async def cleanup_old_history(self, user_id: str, keep_messages: Optional[int] = None):
        """Clean up old history, keeping only recent messages."""
        try:
            if keep_messages is None:
                keep_messages = settings.REDIS_MAX_HISTORY_LENGTH
            
            history = await self.get_chat_history(user_id)
            if len(history) > keep_messages:
                history = history[-keep_messages:]
                await self.set_chat_history(user_id, history)
                logger.info(f"Cleaned up history for user {user_id}, kept {len(history)} messages")
        except Exception as e:
            logger.error(f"Error cleaning up history for user {user_id}: {e}")
    
    async def close(self):
        """Close Redis connection."""
        try:
            await self.redis.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
