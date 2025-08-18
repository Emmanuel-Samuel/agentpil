from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

class CosmosDBService:
    def __init__(self, url: str, key: str, database_name: str, container_name: str):
        self.client = CosmosClient(url, credential=key)
        self.database_name = database_name
        self.container_name = container_name
        self.database = None
        self.container = None

    async def initialize(self):
        """Initializes the database and container."""
        self.database = await self.client.create_database_if_not_exists(id=self.database_name)
        self.container = await self.database.create_container_if_not_exists(
            id=self.container_name,
            partition_key=PartitionKey(path="/id"),
            offer_throughput=400
        )
        logger.info(f"CosmosDB initialized with database: {self.database_name}, container: {self.container_name}")
        
    async def save_conversation(self, user_id: str, conversation: list[dict]):
        """Save conversation history to CosmosDB."""
        item_id = str(uuid.uuid4())
        try:
            await self.container.upsert_item({
                "id": item_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "messages": conversation
            })
            logger.info(f"Conversation saved for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving conversation for user {user_id}: {str(e)}")
            raise

    async def get_item(self, item_id: str):
        """Gets an item from the container by its ID."""
        try:
            return await self.container.read_item(item=item_id, partition_key=item_id)
        except Exception as e:
            logger.error(f"Error getting item {item_id}: {str(e)}")
            raise

    async def update_item(self, item_id: str, updates: dict):
        """Updates an item in the container."""
        try:
            item = await self.get_item(item_id)
            
            # Create a new dictionary with the updated values
            updated_item = item.copy()
            updated_item.update(updates)
            
            await self.container.replace_item(item=item['id'], body=updated_item)
            logger.info(f"Item {item_id} updated successfully")
            
        except Exception as e:
            logger.error(f"Error updating item {item_id}: {str(e)}")
            raise

    async def query_items(self, query: str, parameters: list = None):
        """Queries for items in the container."""
        if parameters is None:
            parameters = []
            
        try:
            items = []
            # Remove enable_cross_partition_query parameter as it's causing issues with the SDK version
            query_iterable = self.container.query_items(
                query=query,
                parameters=parameters
            )
            
            # Iterate through the results
            async for item in query_iterable:
                items.append(item)
                
            logger.info(f"Query executed successfully, returned {len(items)} items")
            return items
            
        except Exception as e:
            logger.error(f"Error executing query: {query}, parameters: {parameters}, error: {str(e)}")
            raise
    
    async def create_item(self, item: dict):
        """Creates a new item in the container."""
        try:
            # Ensure the item has an ID
            if 'id' not in item:
                item['id'] = str(uuid.uuid4())
            
            created_item = await self.container.create_item(body=item)
            logger.info(f"Item created with ID: {created_item['id']}")
            return created_item
            
        except Exception as e:
            logger.error(f"Error creating item: {str(e)}")
            raise
    
    async def upsert_item(self, item: dict):
        """Creates or updates an item in the container."""
        try:
            # Ensure the item has an ID
            if 'id' not in item:
                item['id'] = str(uuid.uuid4())
            
            upserted_item = await self.container.upsert_item(body=item)
            logger.info(f"Item upserted with ID: {upserted_item['id']}")
            return upserted_item
            
        except Exception as e:
            logger.error(f"Error upserting item: {str(e)}")
            raise
    
    async def delete_item(self, item_id: str):
        """Deletes an item from the container."""
        try:
            await self.container.delete_item(item=item_id, partition_key=item_id)
            logger.info(f"Item {item_id} deleted successfully")
            
        except Exception as e:
            logger.error(f"Error deleting item {item_id}: {str(e)}")
            raise

    async def close(self):
        """Close the CosmosDB client connection."""
        try:
            await self.client.close()
            logger.info("CosmosDB client connection closed")
        except Exception as e:
            logger.error(f"Error closing CosmosDB client: {str(e)}")