import uuid
from datetime import datetime

class CosmosDBService:
    def __init__(self, container):
        self.container = container

    async def save_conversation(self, user_id: str, conversation: list[dict]):
        """
        Save the complete conversation history to Cosmos DB, organized by date.
        """
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        item_id = f"{user_id}_{date_str}_{uuid.uuid4()}"

        self.container.upsert_item({
            "id": item_id,
            "user_id": user_id,
            "date": date_str,
            "timestamp": datetime.utcnow().isoformat(),
            "messages": conversation,
            "message_count": len(conversation)
        })