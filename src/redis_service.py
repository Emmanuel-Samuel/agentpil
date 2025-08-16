import json
import redis

class RedisService:
    def __init__(self, host, port, password):
        self.redis = redis.StrictRedis(
            host=host,
            port=port,
            password=password,
            ssl=True
        )

    async def add_message_to_history(self, user_id: str, message: dict, ttl_hours: int = 24):
        """
        Add a message to the user's chat history in Redis with a 24-hour TTL.
        """
        key = f"chat_history:{user_id}"
        history = await self.get_chat_history(user_id)
        history.append(message)

        # Keep only the last 10 messages
        max_history_length = 10
        if len(history) > max_history_length:
            history = history[-max_history_length:]

        # Save history with TTL
        await self.redis.setex(
            key,
            ttl_hours * 3600,  # Convert hours to seconds
            json.dumps(history)
        )

    async def get_chat_history(self, user_id: str):
        """
        Retrieve the user's chat history from Redis.
        """
        key = f"chat_history:{user_id}"
        history = await self.redis.get(key)
        return json.loads(history) if history else []

    async def cleanup_old_history(self, user_id: str, keep_messages: int = 10):
        """
        Ensure only the last `keep_messages` are stored in Redis.
        """
        key = f"chat_history:{user_id}"
        history = await self.get_chat_history(user_id)
        if len(history) > keep_messages:
            history = history[-keep_messages:]
            await self.redis.set(key, json.dumps(history))