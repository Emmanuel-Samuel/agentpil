"""
Prisma Database Client for Legal Claims System

This module provides database connectivity using Prisma ORM,
providing a type-safe and schema-first approach to database access.

Features:
- Type-safe database operations
- Automatic connection pooling
- Schema validation
- Async/await support
- External ID to UUID mapping for compatibility
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator
from prisma import Prisma
from prisma.models import User, Claim, ClaimList, Incident
from prisma.enums import ClaimStatus, UserRole, WereYouInjured

# Handle dotenv import gracefully
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Skip dotenv loading if not available (e.g., in Azure App Service)
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
        # Check if the client is connected
        if hasattr(prisma, '_engine') and prisma._engine is not None:
            # Execute a simple query to check database connection
            result = await prisma.query_raw('SELECT 1')
            return {
                'status': 'connected' if result else 'unknown',
                'database': 'PostgreSQL'
            }
        else:
            return {
                'status': 'disconnected',
                'database': 'PostgreSQL'
            }
    except Exception as e:
        logger.error(f"Database status check failed: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }

# Register the Prisma client for dependency injection
async def get_prisma() -> AsyncGenerator[Prisma, None]:
    """Dependency for FastAPI to get Prisma client"""
    prisma = await get_db()
    try:
        yield prisma
    finally:
        # Connection is managed globally, don't close it here
        pass

# Initialize Prisma client when module is imported
async def init_database() -> Prisma:
    """Initialize the database connection"""
    try:
        prisma = await get_db()
        logger.info("Database connection established")
        return prisma
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

# Remove the automatic initialization on import to prevent conflicts
# The database will be initialized through the FastAPI lifespan events

# Database helper functions using Prisma
async def execute_query(query: str, *args) -> List[Dict[str, Any]]:
    """Execute a raw SQL query and return results as list of dicts"""
    try:
        prisma = await get_db()
        result = await prisma.query_raw(query, *args)
        return result
    except Exception as e:
        logger.error(f"Query execution failed: {str(e)}")
        return []

async def execute_single(query: str, *args) -> Optional[Dict[str, Any]]:
    """Execute a raw SQL query and return single result as dict"""
    try:
        prisma = await get_db()
        result = await prisma.query_raw(query, *args)
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Single query execution failed: {str(e)}")
        return None

async def execute_command(query: str, *args) -> bool:
    """Execute raw SQL command (INSERT/UPDATE/DELETE) and return success status"""
    try:
        prisma = await get_db()
        await prisma.execute_raw(query, *args)
        return True
    except Exception as e:
        logger.error(f"Command execution failed: {str(e)}")
        return False

async def execute_returning(query: str, *args) -> Optional[Dict[str, Any]]:
    """Execute raw SQL with RETURNING clause"""
    try:
        prisma = await get_db()
        result = await prisma.query_raw(query, *args)
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Returning query execution failed: {str(e)}")
        return None

# Application lifecycle functions
async def initialize_db() -> Prisma:
    """Initialize database connection"""
    return await get_db()

async def close_pool():
    """Close database connection pool"""
    await close_db()

# ============================================================================
# ID RESOLUTION FUNCTIONS - Map External IDs to Internal UUIDs
# ============================================================================

async def resolve_user_uuid(external_user_id: str) -> Optional[str]:
    """Resolve external user_id to internal UUID - agents send user_id, we find the UUID"""
    if not external_user_id:
        return None
        
    # First check if external_user_id is already a valid UUID
    try:
        import uuid
        uuid.UUID(external_user_id)
        return external_user_id
    except ValueError:
        pass
    
    # If not a UUID, try to find by email or phone
    try:
        prisma = await get_db()
        user = await prisma.user.find_first(
            where={
                "OR": [
                    {"email": external_user_id},
                    {"phone": external_user_id}
                ]
            }
        )
        return str(user.id) if user else None
    except Exception as e:
        logger.error(f"Error resolving user UUID: {str(e)}")
        return None

async def resolve_claim_uuid(external_claim_id: str) -> Optional[str]:
    """Resolve external claim_id to internal UUID - agents send claim_id, we find the UUID"""
    if not external_claim_id:
        return None
        
    # First check if external_claim_id is already a valid UUID
    try:
        import uuid
        uuid.UUID(external_claim_id)
        
        # Verify the UUID exists in the database
        prisma = await get_db()
        claim = await prisma.claim.find_unique(
            where={"id": external_claim_id}
        )
        if claim:
            logger.debug(f"External claim_id '{external_claim_id}' is a valid UUID")
            return external_claim_id
    except (ValueError, TypeError):
        pass
    
    # Not a UUID or not found by UUID, try to find by claimNumber
    try:
        prisma = await get_db()
        claim = await prisma.claim.find_first(
            where={
                "claimNumber": external_claim_id
            }
        )
        
        if claim:
            logger.debug(f"Resolved external claim_id '{external_claim_id}' to UUID: {claim.id}")
            return str(claim.id)
    except Exception as e:
        logger.error(f"Error resolving claim UUID: {str(e)}")
    
    logger.warning(f"Could not resolve external claim_id '{external_claim_id}' to any UUID")
    return None

# USER CRUD OPERATIONS - With External ID Mapping
# ============================================================================

async def get_user_by_id(external_user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by external user_id using Prisma Client"""
    if not external_user_id:
        return None
        
    prisma = await get_db()
    
    try:
        # Build the include clause for related data
        include = {
            "claimlist": True,
            "projectsOwned": {"take": 10},  # Limit to prevent over-fetching
            "tasksCreated": {"take": 10},   # Limit to prevent over-fetching
            "projectAssignments": {
                "include": {
                    "project": True
                },
                "take": 10  # Limit to prevent over-fetching
            }
        }
        
        # Try to find by ID first (in case external_user_id is a UUID)
        try:
            import uuid
            uuid.UUID(external_user_id)
            user = await prisma.user.find_unique(
                where={"id": external_user_id},
                include=include
            )
            if user:
                return _format_user_response(user)
        except (ValueError, TypeError):
            pass
            
        # If not found by ID or not a UUID, try email or phone
        user = await prisma.user.find_first(
            where={
                "OR": [
                    {"email": external_user_id},
                    {"phone": external_user_id}
                ]
            },
            include=include
        )
        
        if user:
            return _format_user_response(user)
            
        logger.warning(f"User not found with identifier: {external_user_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}", exc_info=True)
        return None

def _format_user_response(user) -> Dict[str, Any]:
    """Format Prisma User model to API response format"""
    if not user:
        return {}
        
    # Format basic user info
    user_data = {
        "id": user.id,
        "first_name": user.firstName,
        "middle_name": user.middleName,
        "last_name": user.lastName,
        "email": user.email,
        "phone": user.phone,
        "phone2": user.phone2,
        "gender": user.gender,
        "date_of_birth": user.dateOfBirth.isoformat() if user.dateOfBirth else None,
        "is_under_18": user.isUnder18,
        "father_first_name": user.fatherFirstName,
        "father_last_name": user.fatherLastName,
        "mother_first_name": user.motherFirstName,
        "mother_last_name": user.motherLastName,
        "mailing_address": {
            "address1": user.mailingAddress1,
            "address2": user.mailingAddress2,
            "city": user.mailingCity,
            "state": user.mailingState,
            "zip_code": user.mailingZipCode
        },
        "physical_address": {
            "address1": user.physicalAddress1,
            "address2": user.physicalAddress2,
            "city": user.physicalCity,
            "state": user.physicalState,
            "zip_code": user.physicalZipCode
        } if user.isPOBoxOrDifferentAddress else None,
        "marital_status": user.maritalStatus,
        "spouse_first_name": user.spouseFirstName,
        "spouse_last_name": user.spouseLastName,
        "spouse_phone": user.spousePhone,
        "employment_status": user.employmentStatus,
        "employer_name": user.employerName,
        "employer_title": user.employerTitle,
        "employment_type": user.employmentType,
        "pay": user.pay,
        "school_name": user.schoolName,
        "expected_graduation_year": user.expectedGraduationYear,
        "role": user.role,  # Already a string from Prisma schema
        "is_verified": user.isVerified,
        "created_at": user.createdAt.isoformat() if user.createdAt else None,
        "updated_at": user.updatedAt.isoformat() if user.updatedAt else None
    }
    
    # Add related data if included
    if hasattr(user, 'claimlist'):
        # Handle both object and tuple cases for claimlist items
        claimlist_data = []
        if user.claimlist:
            for claim in user.claimlist:
                if isinstance(claim, tuple):
                    # Handle tuple case - assume first element has the needed attributes
                    claim_obj = claim[0] if claim else None
                    if claim_obj and hasattr(claim_obj, 'id') and hasattr(claim_obj, 'name'):
                        claimlist_data.append({
                            "id": claim_obj.id,
                            "name": claim_obj.name
                        })
                elif hasattr(claim, 'id') and hasattr(claim, 'name'):
                    # Handle object case
                    claimlist_data.append({
                        "id": claim.id,
                        "name": claim.name
                    })
        user_data["claimlist"] = claimlist_data
        
    if hasattr(user, 'projectsOwned'):
        # Handle both object and tuple cases for projectsOwned items
        projects_data = []
        if user.projectsOwned:
            for project in user.projectsOwned:
                if isinstance(project, tuple):
                    # Handle tuple case - assume first element has the needed attributes
                    project_obj = project[0] if project else None
                    if project_obj and hasattr(project_obj, 'id') and hasattr(project_obj, 'name'):
                        projects_data.append({
                            "id": project_obj.id,
                            "name": project_obj.name,
                            "description": getattr(project_obj, 'description', None)
                        })
                elif hasattr(project, 'id') and hasattr(project, 'name'):
                    # Handle object case
                    projects_data.append({
                        "id": project.id,
                        "name": project.name,
                        "description": getattr(project, 'description', None)
                    })
        user_data["projects_owned"] = projects_data
        
    if hasattr(user, 'tasksCreated'):
        # Handle both object and tuple cases for tasksCreated items
        tasks_data = []
        if user.tasksCreated:
            for task in user.tasksCreated:
                if isinstance(task, tuple):
                    # Handle tuple case - assume first element has the needed attributes
                    task_obj = task[0] if task else None
                    if task_obj and hasattr(task_obj, 'id') and hasattr(task_obj, 'title'):
                        tasks_data.append({
                            "id": task_obj.id,
                            "title": task_obj.title,
                            "status": getattr(task_obj, 'status', None)
                        })
                elif hasattr(task, 'id') and hasattr(task, 'title'):
                    # Handle object case
                    tasks_data.append({
                        "id": task.id,
                        "title": task.title,
                        "status": getattr(task, 'status', None)
                    })
        user_data["tasks_created"] = tasks_data
        
    if hasattr(user, 'projectAssignments'):
        # Handle both object and tuple cases for projectAssignments items
        assignments_data = []
        if user.projectAssignments:
            for assignment in user.projectAssignments:
                if isinstance(assignment, tuple):
                    # Handle tuple case - assume first element has the needed attributes
                    assignment_obj = assignment[0] if assignment else None
                    if assignment_obj and hasattr(assignment_obj, 'id') and hasattr(assignment_obj, 'projectId'):
                        assignments_data.append({
                            "id": assignment_obj.id,
                            "project_id": assignment_obj.projectId,
                            "project_name": getattr(assignment_obj, 'project', None) and getattr(assignment_obj.project, 'name', None) if hasattr(assignment_obj, 'project') else None,
                            "role": getattr(assignment_obj, 'role', None)
                        })
                elif hasattr(assignment, 'id') and hasattr(assignment, 'projectId'):
                    # Handle object case
                    assignments_data.append({
                        "id": assignment.id,
                        "project_id": assignment.projectId,
                        "project_name": getattr(assignment, 'project', None) and getattr(assignment.project, 'name', None) if hasattr(assignment, 'project') else None,
                        "role": getattr(assignment, 'role', None)
                    })
        user_data["project_assignments"] = assignments_data
        
    return user_data

async def update_user(external_user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update user record using external user_id"""
    if not external_user_id or not updates:
        return None
        
    prisma = await get_db()
    
    try:
        # First resolve the external user_id to internal UUID
        user_uuid = await resolve_user_uuid(external_user_id)
        if not user_uuid:
            logger.warning(f"Could not resolve user_id: {external_user_id}")
            return None
            
        # Prepare the update data
        update_data = {}
        
        # Map fields from updates to Prisma model fields
        field_mapping = {
            'firstName': 'firstName',
            'middleName': 'middleName',
            'lastName': 'lastName',
            'email': 'email',
            'phone': 'phone',
            'phone2': 'phone2',
            'gender': 'gender',
            'dateOfBirth': 'dateOfBirth',
            'isUnder18': 'isUnder18',
            'fatherFirstName': 'fatherFirstName',
            'fatherLastName': 'fatherLastName',
            'motherFirstName': 'motherFirstName',
            'motherLastName': 'motherLastName',
            'maritalStatus': 'maritalStatus',
            'spouseFirstName': 'spouseFirstName',
            'spouseLastName': 'spouseLastName',
            'spousePhone': 'spousePhone',
            'employmentStatus': 'employmentStatus',
            'employerName': 'employerName',
            'employerTitle': 'employerTitle',
            'employmentType': 'employmentType',
            'pay': 'pay',
            'schoolName': 'schoolName',
            'expectedGraduationYear': 'expectedGraduationYear',
            'isVerified': 'isVerified',
            'role': 'role'
        }
        
        # Map address fields
        if 'mailing_address' in updates:
            addr = updates.pop('mailing_address')
            update_data.update({
                'mailingAddress1': addr.get('address1'),
                'mailingAddress2': addr.get('address2'),
                'mailingCity': addr.get('city'),
                'mailingState': addr.get('state'),
                'mailingZipCode': addr.get('zip_code')
            })
            
        if 'physical_address' in updates:
            addr = updates.pop('physical_address')
            update_data.update({
                'isPOBoxOrDifferentAddress': True,
                'physicalAddress1': addr.get('address1'),
                'physicalAddress2': addr.get('address2'),
                'physicalCity': addr.get('city'),
                'physicalState': addr.get('state'),
                'physicalZipCode': addr.get('zip_code')
            })
        
        # Map remaining fields
        for api_field, db_field in field_mapping.items():
            if api_field in updates:
                update_data[db_field] = updates[api_field]
        
        if not update_data:
            logger.warning(f"No valid fields to update for user_id: {external_user_id}")
            return None
            
        # Update the user
        updated_user = await prisma.user.update(
            where={"id": user_uuid},
            data=update_data,
            include={
                "claimlist": True,
                "projectsOwned": {"take": 10},
                "tasksCreated": {"take": 10},
                "projectAssignments": {
                    "include": {"project": True},
                    "take": 10
                }
            }
        )
        
        return _format_user_response(updated_user)
        
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}", exc_info=True)
        return None

async def ensure_user_exists(external_user_id: str, user_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Ensure a user exists, creating if needed
    
    Args:
        external_user_id: The external user ID to check/create
        user_data: Optional user data to use when creating a new user
    
    Returns:
        The user data if found or created, None otherwise
    """
    # First try to get existing user
    user = await get_user_by_id(external_user_id)
    if user:
        return user
    
    # If we don't have user data to create with, return None
    if not user_data:
        logger.warning(f"No user data provided to create user with ID: {external_user_id}")
        return None
        
    prisma = await get_db()
    
    try:
        import uuid
        
        # Create a new user with the provided data
        new_user = await prisma.user.create(
            data={
                "id": str(uuid.uuid4()),
                "email": user_data.get("email") or f"user-{external_user_id}@example.com",
                "firstName": user_data.get("first_name") or "",
                "lastName": user_data.get("last_name") or "",
                "phone": user_data.get("phone") or "",
                "password": user_data.get("password") or "",  # Should be hashed in production
                "role": user_data.get("role") or "USER",
                "isVerified": user_data.get("is_verified", False),
                "claimlist": {
                    "create": {
                        "name": f"Claim list for {user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                        "enable": True
                    }
                }
            },
            include={
                "claimlist": True
            }
        )
        
        logger.info(f"Created new user with ID: {new_user.id}")
        return _format_user_response(new_user)
        
    except Exception as e:
        logger.error(f"Error ensuring user exists: {str(e)}", exc_info=True)
        return None

# ============================================================================
# ============================================================================

async def create_claim(claim_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create claim with proper Prisma relationships and external ID handling
    
    Args:
        claim_data: Dictionary containing claim data including 'user_id' and optional 'claim_id'
        
    Returns:
        Dictionary with claim data if successful, None otherwise
    """
    external_user_id = claim_data.get('user_id')
    external_claim_id = claim_data.get('claim_id')  # Agent might provide this
    
    if not external_user_id:
        return {"success": False, "message": "user_id is required"}
    
    prisma = await get_db()
    
    try:
        # Resolve user ID first
        user_uuid = await resolve_user_uuid(external_user_id)
        if not user_uuid:
            return {"success": False, "message": "User not found", "user_id": external_user_id}
        
        # Get user details for claim
        user = await prisma.user.find_unique(
            where={"id": user_uuid},
            include={"claimlist": True}
        )
        
        if not user:
            return {"success": False, "message": "User not found", "user_id": external_user_id}
            
        # Create claim data with proper relationships
        claim_create_data = {
            "status": "PENDING_INFORMATION",  # Using string value that matches Prisma enum
            "user": {
                "connect": {"id": user.id}
            },
            "claimlist": {
                "connect": {"id": user.claimlistId}
            }
        }
        
        # Add incident if provided
        if 'incident' in claim_data:
            incident_data = claim_data['incident']
            # Ensure required workRelated field has a default value if not provided
            if 'workRelated' not in incident_data:
                incident_data['workRelated'] = False
            
            claim_create_data["incident"] = {
                "create": incident_data
            }
        
        # Create the claim with Prisma
        claim = await prisma.claim.create(
            data=claim_create_data,
            include={
                "user": True,  # Include the full user object instead of using select
                "incident": True,
                "claimlist": True
            }
        )
        
        # Return the created claim with external IDs
        return {
            "success": True,
            "message": "Claim created successfully",
            "claim_id": claim.id,  # Return the UUID directly for now
            "internal_uuid": claim.id,
            "status": claim.status,  # Already a string from Prisma
            "created_at": claim.createdAt.isoformat(),
            "user_id": user.id,
            "claim": {
                "id": claim.id,
                "status": claim.status,  # Already a string from Prisma
                "created_at": claim.createdAt.isoformat(),
                "updated_at": claim.updatedAt.isoformat() if claim.updatedAt else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error creating claim: {str(e)}")
        return {"success": False, "message": f"Failed to create claim: {str(e)}"}
    # Removed the finally block that was disconnecting the global client

async def get_claim_by_id(external_claim_id: str) -> Optional[Dict[str, Any]]:
    """Get a single claim by external claim_id using Prisma Client
    
    Args:
        external_claim_id: Claim ID (UUID or claim number)
        
    Returns:
        Claim dictionary with related data, or None if not found
    """
    prisma = await get_db()
    
    try:
        # First resolve the claim ID
        claim_uuid = await resolve_claim_uuid(external_claim_id)
        if not claim_uuid:
            logger.warning(f"Could not resolve claim_id: {external_claim_id}")
            return None
        
        # Query the claim with related data
        claim = await prisma.claim.find_unique(
            where={"id": claim_uuid},
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            }
        )
        
        if not claim:
            logger.warning(f"Claim not found: {external_claim_id}")
            return None
        
        # Format the response
        result = {
            "id": claim.id,
            "status": claim.status,
            "created_at": claim.createdAt.isoformat(),
            "updated_at": claim.updatedAt.isoformat() if claim.updatedAt else None,
            "assigned_case_manager": claim.assignedCaseManager,
            "injured": claim.injured,
            "health_insurance": claim.healthInsurance,
            "relationship": claim.relationship,
            "other_relationship": claim.otherRelationship,
            "health_insurance_number": claim.healthInsuranceNumber,
            "is_over_65": claim.isOver65,
            "receive_medicare": claim.receiveMedicare,
            "user": {
                "id": claim.user.id,
                "name": f"{claim.user.firstName} {claim.user.lastName}",
                "email": claim.user.email,
                "phone": claim.user.phone
            } if claim.user else None,
            "incident": claim.incident.dict() if claim.incident else None,
            "claimlist_id": claim.claimlistId
        }
        
        # Add title and description from incident if available
        if claim.incident:
            result["title"] = claim.incident.location or "Untitled Claim"
            result["description"] = claim.incident.description or ""
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting claim: {str(e)}", exc_info=True)
        return None

async def get_user_claims(external_user_id: str, status: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None, sort_by: Optional[str] = None, sort_order: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get claims for external user_id using Prisma Client
    
    Args:
        external_user_id: User ID, email, or phone number
        status: Optional status filter (e.g., 'PENDING', 'APPROVED')
        limit: Optional limit for pagination
        offset: Optional offset for pagination
        sort_by: Optional field to sort by
        sort_order: Optional sort order ('asc' or 'desc')
        
    Returns:
        List of claim dictionaries with related data
    """
    prisma = await get_db()
    
    try:
        # First resolve the user ID
        user_uuid = await resolve_user_uuid(external_user_id)
        if not user_uuid:
            logger.warning(f"Could not resolve user_id: {external_user_id}")
            return []
        
        # Build the where clause
        where_clause = {
            "userId": user_uuid
        }
        
        # Add status filter if provided
        if status:
            where_clause["status"] = status.upper()
        
        # Query claims with related data
        claims = await prisma.claim.find_many(
            where=where_clause,
            include={
                "user": True,  # Include the full user object instead of using select
                "incident": True,
                "claimlist": True
            }
            # Removed order_by as it's not a valid parameter for find_many in Prisma Python client
        )
        
        # Sort the claims manually after fetching
        if sort_by == "createdAt":
            reverse = sort_order != "asc"
            claims = sorted(claims, key=lambda x: x.createdAt, reverse=reverse)
        else:
            # Default sorting by createdAt descending
            claims = sorted(claims, key=lambda x: x.createdAt, reverse=True)
        
        # Apply pagination if limit is specified
        if limit is not None:
            start = offset if offset is not None else 0
            end = start + limit
            claims = claims[start:end]
        elif offset is not None:
            claims = claims[offset:]
        
        # Format the response
        result = []
        for claim in claims:
            claim_data = {
                "id": claim.id,
                "status": claim.status,
                "created_at": claim.createdAt.isoformat(),
                "updated_at": claim.updatedAt.isoformat() if claim.updatedAt else None,
                "user": {
                    "id": claim.user.id,
                    "name": f"{claim.user.firstName} {claim.user.lastName}",
                    "email": claim.user.email,
                    "phone": claim.user.phone
                } if claim.user else None,
                "incident": claim.incident.dict() if claim.incident else None,
                "claimlist_id": claim.claimlistId
            }
            
            # Add title from incident if available
            if claim.incident:
                claim_data["title"] = claim.incident.location or "Untitled Claim"
                
            result.append(claim_data)
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting user claims: {str(e)}", exc_info=True)
        return []

# Update the todo list to mark relationship handling as completed
todo_list = [
    {"id": "1", "content": "Analyze database operations in database.py and map them to Prisma schema", "status": "completed", "priority": "high"},
    {"id": "2", "content": "Update user-related database operations to match Prisma User model", "status": "completed", "priority": "high"},
    {"id": "3", "content": "Update claim-related database operations to match Prisma Claim model", "status": "completed", "priority": "high"},
    {"id": "4", "content": "Update relationship handling between models", "status": "completed", "priority": "high"},
    {"id": "5", "content": "Update search and utility functions", "status": "in_progress", "priority": "medium"}
]

async def update_claim(external_claim_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update claim using Prisma Client"""
    # Use the global Prisma client instead of creating a new instance
    prisma = await get_db()
    
    try:
        # Check if claim exists
        existing_claim = await prisma.claim.find_unique(
            where={"id": external_claim_id},
            include={"incident": True}
        )
        
        if not existing_claim:
            return {
                "success": False,
                "message": "Claim not found",
                "claim_id": external_claim_id
            }
        
        # Prepare update data
        update_data = {}
        updated_fields = []
        
        # Map and validate updates - corrected field mappings based on Prisma schema
        field_mapping = {
            'status': ('status', str),  # Status is already a string in Prisma schema
            'injured': ('injured', bool),  # Were you injured? field
            'relationship': ('relationship', str),  # Relationship field
            'other_relationship': ('otherRelationship', str),  # Other Relationship field
            'health_insurance': ('healthInsurance', bool),  # Do you have health insurance? field
            'health_insurance_number': ('healthInsuranceNumber', str),  # Health Insurance Number field
            'is_over_65': ('isOver65', bool),  # Are you 65 years old or older? field
            'receive_medicare': ('receiveMedicare', list),  # Do you currently receive? field (array)
            'assigned_case_manager': ('assignedCaseManager', str),  # Assigned Claim Specialist field
        }
        
        for key, value in updates.items():
            if key in field_mapping and value is not None:
                db_field, converter = field_mapping[key]
                try:
                    # Special handling for enum fields
                    if key == 'relationship' and value:
                        # Validate relationship value against Prisma enum
                        valid_relationships = ['Self', 'Parent', 'Child', 'Sibiling', 'Friend', 'Representative', 'Other']
                        if value in valid_relationships:
                            update_data[db_field] = value
                            updated_fields.append(key)
                        else:
                            logger.warning(f"Invalid relationship value: {value}")
                    elif key == 'status' and value:
                        # Validate status value against Prisma enum
                        valid_statuses = [
                            'PENDING_INFORMATION', 'UNDER_REVIEW', 'PENDING_DOCUMENTS', 
                            'INVESTIGATION', 'PRE_SUIT', 'PRE_LITIGATION', 
                            'LITIGATION', 'RESOLVED_AND_CLOSED'
                        ]
                        if value in valid_statuses:
                            update_data[db_field] = value
                            updated_fields.append(key)
                        else:
                            logger.warning(f"Invalid status value: {value}")
                    elif key == 'receive_medicare' and value:
                        # Handle array field
                        if isinstance(value, list):
                            update_data[db_field] = value
                            updated_fields.append(key)
                        elif isinstance(value, str):
                            # Convert comma-separated string to list
                            update_data[db_field] = [item.strip() for item in value.split(',')]
                            updated_fields.append(key)
                    else:
                        update_data[db_field] = converter(value)
                        updated_fields.append(key)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Invalid value for {key}: {str(e)}")
        
        # Handle incident updates separately
        incident_updates = {}
        if 'incident' in updates and updates['incident']:
            incident_data = updates['incident']
            # Map incident fields
            incident_field_mapping = {
                'datetime': 'datetime',
                'location': 'location',
                'description': 'description',
                'policeReportNumber': 'policeReportNumber',
                'injuries': 'injuries',
                'workRelated': 'workRelated'  # Add workRelated field
            }
            
            for key, value in incident_data.items():
                if key in incident_field_mapping and value is not None:
                    incident_updates[incident_field_mapping[key]] = value
                    updated_fields.append(f"incident.{key}")
            
            # Handle witnesses separately
            if 'witnesses' in incident_data and incident_data['witnesses']:
                # For now, we'll store witnesses as a JSON string in the incident description
                # In a full implementation, we would create separate witness records
                incident_updates['witnesses'] = incident_data['witnesses']
                updated_fields.append("incident.witnesses")
        
        if not update_data and not incident_updates:
            # No valid updates to process
            return {
                "success": True,
                "message": "No valid fields to update",
                "claim_id": external_claim_id,
                "updated_fields": []
            }
        
        # Update the claim
        if update_data:
            updated_claim = await prisma.claim.update(
                where={"id": external_claim_id},
                data=update_data,
                include={
                    "user": True,
                    "incident": True,
                    "claimlist": True
                }
            )
        
        # Update incident if there are incident updates
        if incident_updates and existing_claim.incident:
            await prisma.incident.update(
                where={"id": existing_claim.incident.id},
                data=incident_updates
            )
        elif incident_updates and not existing_claim.incident:
            # Create a new incident record if one doesn't exist
            # Ensure required workRelated field has a default value if not provided
            if 'workRelated' not in incident_updates:
                incident_updates['workRelated'] = False
            
            await prisma.incident.create(
                data={
                    **incident_updates,
                    "claim": {
                        "connect": {"id": external_claim_id}
                    }
                }
            )
        
        # Fetch the updated claim with all relations
        final_updated_claim = await prisma.claim.find_unique(
            where={"id": external_claim_id},
            include={
                "user": True,
                "incident": True,
                "claimlist": True
            }
        )
        
        return {
            "success": True,
            "message": "Claim updated successfully",
            "claim_id": external_claim_id,
            "updated_fields": updated_fields,
            "status": final_updated_claim.status,
            "updated_at": final_updated_claim.updatedAt.isoformat() if final_updated_claim.updatedAt else None
        }
        
    except Exception as e:
        logger.error(f"Error updating claim: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to update claim: {str(e)}",
            "claim_id": external_claim_id
        }

# ============================================================================
# LEGAL KNOWLEDGE OPERATIONS
# ============================================================================

async def search_legal_knowledge(query_text: str, category: Optional[str] = None, 
                                jurisdiction: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Search legal knowledge with fallback for demo"""
    # Return mock legal knowledge for demo purposes
    mock_results = [
        {
            "id": "legal_001",
            "title": "Personal Injury Statute of Limitations",
            "content": f"Information about {query_text} - In most states, personal injury claims must be filed within 2-3 years of the incident date.",
            "category": category or "law",
            "jurisdiction": jurisdiction or "general",
            "relevance_score": 0.95,
            "created_at": datetime.now(),
            "is_active": True
        },
        {
            "id": "legal_002",
            "title": "Evidence Collection Guidelines",
            "content": f"Guidelines for {query_text} - Proper documentation and evidence collection is crucial for successful claims.",
            "category": category or "procedure",
            "jurisdiction": jurisdiction or "general",
            "relevance_score": 0.85,
            "created_at": datetime.now(),
            "is_active": True
        }
    ]
    
    return mock_results[:limit]

# ============================================================================
# AGENT ACTIVITY LOGGING
# ============================================================================

async def log_agent_activity(agent_type: str, action: str, user_id: Optional[str] = None,
                           conversation_id: Optional[str] = None, tool_name: Optional[str] = None,
                           tool_parameters: Optional[Dict] = None, response_data: Optional[Dict] = None,
                           execution_time_ms: Optional[int] = None, status: str = 'success',
                           error_message: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Log agent activity for monitoring and debugging"""
    try:
        # Simple logging since agent_activity table may not exist in Prisma schema
        logger.info(f"Agent Activity: {agent_type} - {action} - {status}")
        return {"logged": True, "agent_type": agent_type, "action": action, "status": status}
    except Exception as e:
        logger.error(f"Error logging agent activity: {str(e)}")
        return None

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

async def init_database_schema():
    """Initialize database schema - placeholder for Prisma migration"""
    logger.info("Database schema initialization - use 'npx prisma db push' for actual schema creation")
    return True

