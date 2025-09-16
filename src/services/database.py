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
        
        # Always create an incident (even if minimal data)
        incident_data = claim_data.get('incident', {}).copy()
        
        # Log the incident data for debugging
        logger.info(f"Incident data: {incident_data}")
              
        # Map API fields to Prisma schema fields with default values
        incident_create_data = {

            "datetime": datetime.fromisoformat(incident_data['datetime']) if incident_data.get('datetime') else None,
            "location": incident_data.get('location', ''),
            "description": incident_data.get('description', ''),
            "workRelated": incident_data.get('workRelated', False),
            "reportCompleted": incident_data.get('reportCompleted', False),
            "policeReportCompleted": incident_data.get('policeReportCompleted', False),
            "supportingDocument": incident_data.get('supportingDocument', False),
            "witness": incident_data.get('witness', False),
            "priorRepresentation": incident_data.get('priorRepresentation', False),
            "lostEarning": incident_data.get('lostEarning', ''),
            "reportNumber": incident_data.get('reportNumber', ''),
            "vehicleRole": incident_data.get('vehicleRole'),
            "vehicleCount": incident_data.get('vehicleCount'),
            "busOrVehicle": incident_data.get('busOrVehicle')
        }
        
        # Remove None values from incident_create_data
        incident_create_data = {k: v for k, v in incident_create_data.items() if v is not None}
        
        # Log the incident create data for debugging
        logger.info(f"Incident create data: {incident_create_data}")
        
        # Create incident
        incident = await prisma.incident.create(data=incident_create_data)
        
        # Prepare claim data with proper relationships
        claim_create_data = {
            "status": claim_data.get('status', 'PENDING_INFORMATION'),
            "user": {"connect": {"id": user.id}},
            "claimlist": {"connect": {"id": user.claimlistId}},
            "incident": {"connect": {"id": incident.id}},  # Always connect the incident
            "injured": claim_data.get('injured', True),
            "healthInsurance": claim_data.get('healthInsurance'),
            "relationship": claim_data.get('relationship'),
            "otherRelationship": claim_data.get('otherRelationship'),
            "healthInsuranceNumber": claim_data.get('healthInsuranceNumber'),
            "isOver65": claim_data.get('isOver65')
        }
        
        # Remove None values from claim_create_data
        claim_create_data = {k: v for k, v in claim_create_data.items() if v is not None}
        
        # Log the claim create data for debugging
        logger.info(f"Claim create data: {claim_create_data}")
        
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
        logger.exception("Full traceback:")
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
        
        logger.info(f"Searching claims with where_clause: {where_clause}")
        claims = await prisma.claim.find_many(
            where=where_clause,
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            },
            order={"createdAt": "desc"}
        )
        
        # Convert claims to dict and handle null incidents
        result = []
        for claim in claims:
            claim_dict = claim.model_dump()
            # Ensure incident is not None and handle potential null incidentId
            if claim_dict["incident"] is None or claim_dict["incident"]["id"] is None:
                claim_dict["incident"] = {
                    "id": "",
                    "datetime": None,
                    "location": "",
                    "description": "",
                    "workRelated": False,
                    "reportCompleted": False,
                    "policeReportCompleted": False,
                    "supportingDocument": False,
                    "witness": False,
                    "priorRepresentation": False,
                    "lostEarning": "",
                    "reportNumber": "",
                    "vehicleRole": None,
                    "vehicleCount": None,
                    "busOrVehicle": None
                }
            result.append(claim_dict)
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting user claims: {str(e)}")
        return []

async def update_claim(claim_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update claim with support for incident updates"""
    try:
        prisma = await get_db()
        
        # All updatable fields match Prisma schema directly
        valid_fields = {
            'status', 'injured', 'relationship', 'otherRelationship', 
            'healthInsurance', 'healthInsuranceNumber', 'isOver65', 
            'receiveMedicare', 'assignedCaseManager',
            'policeReportCompleted', 'supportingDocument', 'workRelated',
            'witness', 'priorRepresentation'
        }
        
        # Filter updates to only include valid schema fields
        claim_updates = {k: v for k, v in updates.items() if k in valid_fields}
        
        # Handle incident updates if provided
        incident_updates = None
        if 'incident' in updates and isinstance(updates['incident'], dict):
            incident_data = updates['incident']
            
            # Map API fields to Prisma schema fields
            incident_updates = {}
            if incident_data.get('datetime'):
                incident_updates["datetime"] = datetime.fromisoformat(incident_data['datetime'])
            if incident_data.get('location') is not None:
                incident_updates["location"] = incident_data.get('location')
            if incident_data.get('description') is not None:
                incident_updates["description"] = incident_data.get('description')
            if incident_data.get('workRelated') is not None:
                incident_updates["workRelated"] = incident_data.get('workRelated')
            if incident_data.get('reportCompleted') is not None:
                incident_updates["reportCompleted"] = incident_data.get('reportCompleted')
            if incident_data.get('policeReportCompleted') is not None:
                incident_updates["policeReportCompleted"] = incident_data.get('policeReportCompleted')
            if incident_data.get('supportingDocument') is not None:
                incident_updates["supportingDocument"] = incident_data.get('supportingDocument')
            if incident_data.get('witness') is not None:
                incident_updates["witness"] = incident_data.get('witness')
            if incident_data.get('priorRepresentation') is not None:
                incident_updates["priorRepresentation"] = incident_data.get('priorRepresentation')
            if incident_data.get('lostEarning') is not None:
                incident_updates["lostEarning"] = incident_data.get('lostEarning')
            if incident_data.get('reportNumber') is not None:
                incident_updates["reportNumber"] = incident_data.get('reportNumber')
            if incident_data.get('vehicleRole') is not None:
                incident_updates["vehicleRole"] = incident_data.get('vehicleRole')
            if incident_data.get('vehicleCount') is not None:
                incident_updates["vehicleCount"] = incident_data.get('vehicleCount')
            if incident_data.get('busOrVehicle') is not None:
                incident_updates["busOrVehicle"] = incident_data.get('busOrVehicle')
            
            # Remove None values
            incident_updates = {k: v for k, v in incident_updates.items() if v is not None}
        
        # Log the updates for debugging
        logger.info(f"Claim updates: {claim_updates}")
        logger.info(f"Incident updates: {incident_updates}")
        
        if not claim_updates and not incident_updates:
            logger.warning(f"No valid fields to update for claim {claim_id}")
            return None
        
        # First check if claim exists
        claim = await prisma.claim.find_unique(
            where={"id": claim_id},
            include={"incident": True}
        )
        
        if not claim:
            logger.warning(f"Claim {claim_id} not found")
            return None
            
        # Update incident if needed
        if incident_updates:
            if claim.incident:
                # Update existing incident
                await prisma.incident.update(
                    where={"id": claim.incident.id},
                    data=incident_updates
                )
            else:
                # Create new incident and connect to claim
                incident = await prisma.incident.create(data=incident_updates)
                claim_updates["incident"] = {"connect": {"id": incident.id}}
        
        # Then update claim if needed
        if claim_updates:
            updated_claim = await prisma.claim.update(
                where={"id": claim_id},
                data=claim_updates,
                include={
                    "user": True,
                    "incident": True,
                    "claimlist": True
                }
            )
            return updated_claim.model_dump() if updated_claim else None
        else:
            # If only incident was updated, return the updated claim
            updated_claim = await prisma.claim.find_unique(
                where={"id": claim_id},
                include={
                    "user": True,
                    "incident": True,
                    "claimlist": True
                }
            )
            return updated_claim.model_dump() if updated_claim else None
        
    except Exception as e:
        logger.error(f"Error updating claim {claim_id}: {str(e)}")
        logger.exception("Full traceback:")
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
