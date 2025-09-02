import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from prisma import Prisma
from prisma.models import User, Claim, ClaimList, Incident

# Handle dotenv import gracefully
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Global Prisma client
_prisma: Optional[Prisma] = None

async def get_db() -> Prisma:
    """Get Prisma client instance"""
    global _prisma
    if _prisma is None:
        _prisma = Prisma()
        await _prisma.connect()
    return _prisma

async def close_db() -> None:
    """Close Prisma client connection"""
    global _prisma
    if _prisma is not None:
        try:
            await _prisma.disconnect()
            _prisma = None
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {str(e)}")

async def get_db_status() -> Dict[str, Any]:
    """Get database connection status"""
    try:
        prisma = await get_db()
        result = await prisma.query_raw('SELECT 1')
        return {
            'status': 'connected' if result else 'unknown',
            'database': 'PostgreSQL'
        }
    except Exception as e:
        logger.error(f"Database status check failed: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID using Prisma"""
    try:
        prisma = await get_db()
        
        # Try UUID first, then email/phone
        try:
            import uuid
            uuid.UUID(user_id)
            user = await prisma.user.find_unique(
                where={"id": user_id},
                include={"claimlist": True}
            )
        except ValueError:
            user = await prisma.user.find_first(
                where={
                    "OR": [
                        {"email": user_id},
                        {"phone": user_id}
                    ]
                },
                include={"claimlist": True}
            )
        
        return user.model_dump() if user else None
        
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        return None

async def create_user(user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create new user with claimlist"""
    try:
        prisma = await get_db()
        import uuid
        
        user = await prisma.user.create(
            data={
                "id": str(uuid.uuid4()),
                "email": user_data.get("email"),
                "firstName": user_data.get("firstName", ""),
                "lastName": user_data.get("lastName", ""),
                "phone": user_data.get("phone", ""),
                "password": user_data.get("password", ""),
                "role": user_data.get("role", "USER"),
                "isVerified": user_data.get("isVerified", False),
                "claimlist": {
                    "create": {
                        "name": f"Claims for {user_data.get('firstName', '')} {user_data.get('lastName', '')}",
                        "enable": True
                    }
                }
            },
            include={"claimlist": True}
        )
        
        return user.model_dump()
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return None


async def create_claim(claim_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create claim with incident data"""
    try:
        prisma = await get_db()
        
        # Get user ID
        user_id = claim_data.get('userId') or claim_data.get('user_id')
        if not user_id:
            return {"success": False, "message": "userId is required"}
        
        # Get user to ensure exists and get claimlistId
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={"claimlist": True}
        )
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        # First create the incident if provided
        incident_id = None
        if 'incident' in claim_data:
            incident_data = claim_data['incident'].copy()
            
            # Map API fields to Prisma schema fields
            incident_create_data = {
                "datetime": incident_data.get('datetime'),
                "location": incident_data.get('location'),
                "description": incident_data.get('description'),
                "workRelated": incident_data.get('workRelated', False),
                "reportCompleted": incident_data.get('reportCompleted', False),
                "policeReportCompleted": incident_data.get('policeReportCompleted', False),
                "supportingDocument": incident_data.get('supportingDocument', False),
                "witness": incident_data.get('witness', False),
                "priorRepresentation": incident_data.get('priorRepresentation', False),
                "lostEarning": incident_data.get('lostEarning', ''),
                "reportNumber": incident_data.get('reportNumber', '')
            }
            
            # Create incident first
            incident = await prisma.incident.create(data=incident_create_data)
            incident_id = incident.id
        
        # Prepare claim data with proper relationships
        claim_create_data = {
            "status": "PENDING_INFORMATION",
            "user": {"connect": {"id": user.id}},
            "claimlist": {"connect": {"id": user.claimlistId}},
            "injured": claim_data.get('injured', True),
            "healthInsurance": claim_data.get('healthInsurance'),
            "relationship": claim_data.get('relationship'),
            "otherRelationship": claim_data.get('otherRelationship'),
            "healthInsuranceNumber": claim_data.get('healthInsuranceNumber'),
            "isOver65": claim_data.get('isOver65')
        }
        
        # Connect incident if created
        if incident_id:
            claim_create_data["incident"] = {"connect": {"id": incident_id}}
        
        # Create claim
        claim = await prisma.claim.create(
            data=claim_create_data,
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            }
        )
        
        return {
            "success": True,
            "message": "Claim created successfully",
            "claim_id": claim.id,
            "status": claim.status,
            "created_at": claim.createdAt.isoformat(),
            "user_id": user.id
        }
        
    except Exception as e:
        logger.error(f"Error creating claim: {str(e)}")
        return {"success": False, "message": f"Failed to create claim: {str(e)}"}

async def get_claim_by_id(claim_id: str) -> Optional[Dict[str, Any]]:
    """Get claim by ID"""
    try:
        prisma = await get_db()
        
        claim = await prisma.claim.find_unique(
            where={"id": claim_id},
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            }
        )
        
        return claim.model_dump() if claim else None
        
    except Exception as e:
        logger.error(f"Error getting claim: {str(e)}")
        return None

async def get_user_claims(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all claims for a user"""
    try:
        prisma = await get_db()
        
        where_clause = {"userId": user_id}
        if status:
            where_clause["status"] = status.upper()
        
        claims = await prisma.claim.find_many(
            where=where_clause,
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            },
            order={"createdAt": "desc"}
        )
        
        return [claim.model_dump() for claim in claims]
        
    except Exception as e:
        logger.error(f"Error getting user claims: {str(e)}")
        return []

async def update_claim(claim_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update claim"""
    try:
        prisma = await get_db()
        
        # All updatable fields match Prisma schema directly
        valid_fields = {
            'status', 'injured', 'relationship', 'otherRelationship', 
            'healthInsurance', 'healthInsuranceNumber', 'isOver65', 
            'receiveMedicare', 'assignedCaseManager'
        }
        
        # Filter updates to only include valid schema fields
        mapped_updates = {k: v for k, v in updates.items() if k in valid_fields}
        
        if not mapped_updates:
            logger.warning(f"No valid fields to update for claim {claim_id}")
            return None
        
        claim = await prisma.claim.update(
            where={"id": claim_id},
            data=mapped_updates,
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            }
        )
        
        return claim.model_dump()
        
    except Exception as e:
        logger.error(f"Error updating claim: {str(e)}")
        return None

async def update_user(user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update user profile"""
    try:
        prisma = await get_db()
        
        # Map flattened address fields to nested structure if needed
        update_data = updates.copy()
        
        # Handle address fields
        address_fields = {}
        for key in list(update_data.keys()):
            if key.startswith('address_'):
                field_name = key.replace('address_', '')
                if field_name == 'street':
                    address_fields['mailingAddress1'] = update_data.pop(key)
                elif field_name == 'city':
                    address_fields['mailingCity'] = update_data.pop(key)
                elif field_name == 'state':
                    address_fields['mailingState'] = update_data.pop(key)
                elif field_name == 'postalCode':
                    address_fields['mailingZipCode'] = update_data.pop(key)
        
        # Handle preference fields
        for key in list(update_data.keys()):
            if key.startswith('preferences_'):
                # For now, skip preferences - would need separate preferences table
                update_data.pop(key)
        
        # Map common fields
        field_mapping = {
            'firstName': 'firstName',
            'lastName': 'lastName', 
            'email': 'email',
            'phoneNumber': 'phone',
            'dateOfBirth': 'dateOfBirth'
        }
        
        mapped_data = {}
        for api_field, db_field in field_mapping.items():
            if api_field in update_data:
                mapped_data[db_field] = update_data[api_field]
        
        # Add address fields
        mapped_data.update(address_fields)
        
        if not mapped_data:
            return None
        
        user = await prisma.user.update(
            where={"id": user_id},
            data=mapped_data,
            include={"claimlist": True}
        )
        
        return user.model_dump()
        
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return None


async def initialize_db() -> Prisma:
    """Initialize database connection"""
    return await get_db()

async def close_pool():
    """Close database connection pool"""
    await close_db()
