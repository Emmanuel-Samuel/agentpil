import json
from typing import Optional
import logging

# This will be populated by the application startup logic
db_service = None

def initialize_tools(db_service_instance):
    """Initializes the tools with a database service instance."""
    global db_service
    db_service = db_service_instance

# Set up logging
logger = logging.getLogger(__name__)

async def get_claim_by_contact_info(email: Optional[str] = None, phone: Optional[str] = None) -> str:
    """
    Get claim details by providing either an email or a phone number.
    Uses Redis cache to avoid repeated queries when available.
    """
    if not db_service:
        logger.error("Database service not initialized.")
        return json.dumps({"status": "error", "message": "Database service not initialized."})

    try:
        # Validate input and derive cache key
        cache_key = email or phone
        if not cache_key:
            logger.error("Either email or phone must be provided.")
            return json.dumps({"status": "error", "message": "Either email or phone must be provided."})

        # Check if Redis cache is available on the db_service
        has_cache = hasattr(db_service, "redis") and \
                    hasattr(db_service.redis, "get_claim_info") and \
                    hasattr(db_service.redis, "save_claim_info")

        # Try cache first
        if has_cache:
            try:
                claim_info = await db_service.redis.get_claim_info(cache_key)
                if claim_info:
                    logger.info(f"Retrieved claim info from cache for {cache_key}")
                    return json.dumps({"status": "found", "claim": claim_info, "source": "cache"})
            except Exception as cache_err:
                logger.warning(f"Cache retrieval failed for {cache_key}: {cache_err}")

        # Not in cache or cache unavailable; query the database
        if email:
            query = "SELECT * FROM c WHERE c.email = @email"
            parameters = [{"name": "@email", "value": email}]
            logger.info(f"Executing query for email: {email}")
        else:  # phone is not None here due to earlier check
            query = "SELECT * FROM c WHERE c.phoneNumber = @phone"
            parameters = [{"name": "@phone", "value": phone}]
            logger.info(f"Executing query for phone: {phone}")

        items = await db_service.query_items(query, parameters)
        logger.info(f"Query returned {len(items)} items.")
        
        if items:
            claim = items[0]
            # Save to cache if available
            if has_cache:
                try:
                    await db_service.redis.save_claim_info(cache_key, claim)
                    logger.info(f"Saved claim info to cache for {cache_key}")
                except Exception as cache_save_err:
                    logger.warning(f"Cache save failed for {cache_key}: {cache_save_err}")
            return json.dumps({"status": "found", "claim": claim, "source": "database"})
        else:
            logger.info("No claim found.")
            return json.dumps({"status": "not_found", "message": "No claim found with the provided contact information."})
            
    except Exception as e:
        logger.error(f"Failed to get claim: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to get claim: {str(e)}"})

async def initiate_new_claim(user_id: str, claim_data: dict) -> str:
    """
    Initiate a new claim for a user with the provided claim data.
    """
    if not db_service:
        return json.dumps({"status": "error", "message": "Database service not initialized."})
    
    try:
        new_claim = {
            "user_id": user_id,
            "claimType": claim_data.get("claimType", "new_claim_initiation"),
            "status": "initiated",
            **claim_data
        }
        
        created_claim = await db_service.create_item(new_claim)
        claim_id = created_claim["id"]
        
        logger.info(f"New claim initiated with ID: {claim_id} for user {user_id}")
        
        return json.dumps({
            "status": "success", 
            "message": f"New claim initiated for user {user_id}.",
            "claim_id": claim_id
        })
        
    except Exception as e:
        logger.error(f"Failed to initiate new claim: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to initiate new claim: {str(e)}"})

async def transition_claim_type(claim_id: str, new_claim_type: str) -> str:
    """
    Updates an existing claim with a new claim type.
    """
    if not db_service:
        return json.dumps({"status": "error", "message": "Database service not initialized."})
    
    try:
        updates = {"claimType": new_claim_type}
        await db_service.update_item(claim_id, updates)
        
        logger.info(f"Claim {claim_id} transitioned to {new_claim_type}")
        
        return json.dumps({
            "status": "success", 
            "message": f"Claim {claim_id} has been transitioned to {new_claim_type}."
        })
        
    except Exception as e:
        logger.error(f"Failed to transition claim: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to transition claim: {str(e)}"})

async def update_claim_data(claim_id: str, updates: dict) -> str:
    """
    Update the data for an existing claim.
    """
    if not db_service:
        return json.dumps({"status": "error", "message": "Database service not initialized."})
    
    try:
        await db_service.update_item(claim_id, updates)
        logger.info(f"Claim {claim_id} updated.")
        
        return json.dumps({
            "status": "success", 
            "message": f"Claim {claim_id} updated."
        })
        
    except Exception as e:
        logger.error(f"Failed to update claim: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to update claim: {str(e)}"})
