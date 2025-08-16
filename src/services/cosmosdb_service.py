from azure.cosmos import CosmosClient, PartitionKey
from datetime import datetime
import uuid

class CosmosDBService:
    def __init__(self, url: str, key:str, database_name: str, container_name: str):
        self.client = CosmosClient(url, credential=key)
        self.database = self.client.create_database_if_not_exists(id=database_name)
        self.container = self.database.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path="/id"),
            offer_throughput=400
        )
        
    async def save_conversation(self, user_id: str, conversation: list[dict]):
        item_id = str(uuid.uuid4())
        self.container.upsert_item({
            "id": item_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "messages": conversation
        })