from fastapi import FastAPI, HTTPException, BackgroundTasks, APIRouter, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager
import time
from typing import Any, Dict, Optional
import json
from pydantic import BaseModel, Field, HttpUrl, EmailStr, conint, confloat
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from .config.config import settings
from .services.database import (
    create_claim as save_claim_data,
    get_user_claims,
    update_claim as update_claim_data,
    search_legal_knowledge as search_legal_database,
    get_user_by_id as get_user_profile,
    update_user as update_user_profile,
    get_claim_by_id,
    execute_single
)
from .services.ai_agent_service import ai_agent_service
from .services.database import initialize_db, close_db, init_database_schema, log_agent_activity

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Set third-party library log levels to WARNING to reduce noise
logging.getLogger('azure').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncpg').setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting FastAPI application...")
    
    # Initialize database connection and schema
    await initialize_db()
    schema_initialized = await init_database_schema()
    if schema_initialized:
        logger.info("Database schema initialized")
    else:
        logger.warning("Database schema initialization failed")
    
    # Initialize AI agent service
    await ai_agent_service.initialize()
    
    logger.info("Application started - OpenAPI docs at /docs")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await ai_agent_service.close()
    await close_db()
    logger.info("Shutdown complete")

# Create FastAPI app with comprehensive OpenAPI schema for Azure AI Foundry
app = FastAPI(
    title="AI Legal Claims Assistant",
    description="""FastAPI application with Azure AI Foundry Connected Agents integration.
    
    This API provides tools for Azure AI Foundry agents to interact with:
    - Legal claims database (PostgreSQL)
    - User profile management
    - Legal knowledge search
    - Claim lifecycle management
    
    **Current Workflow**: 
    - User → /chat/initial or /chat/portal → Orchestrator Agent (Connected Agents) → Specialized Agents → FastAPI Tools → PostgreSQL → Response
    
    **Connected Agents Architecture**: Azure AI Foundry handles intelligent routing, context management, and agent orchestration automatically.
    
    **Agent Tool Discovery**: Azure AI Foundry agents automatically discover available tools via OpenAPI schema.
    """,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "chat",
            "description": "Chat endpoints for Azure AI Foundry agents"
        },
        {
            "name": "agent-tools",
            "description": "Tool endpoints for Azure AI Foundry agents to call via OpenAPI"
        },
        {
            "name": "orchestrator-tools",
            "description": "Specialized tools for the orchestrator agent"
        },
        {
            "name": "claim-tools",
            "description": "Tools for claim creation, retrieval, and management"
        },
        {
            "name": "user-tools",
            "description": "Tools for user profile and preference management"
        },
        {
            "name": "legal-tools",
            "description": "Tools for legal knowledge search and research"
        },
        {
            "name": "system",
            "description": "System health and status endpoints"
        }
    ]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Enums for request models
class ClaimStatus(str, Enum):
    PENDING_INFORMATION = "PENDING_INFORMATION"
    UNDER_REVIEW = "UNDER_REVIEW"
    PENDING_DOCUMENTS = "PENDING_DOCUMENTS"
    INVESTIGATION = "INVESTIGATION"
    PRE_SUIT = "PRE_SUIT"
    PRE_LITIGATION = "PRE_LITIGATION"
    LITIGATION = "LITIGATION"
    RESOLVED_AND_CLOSED = "RESOLVED_AND_CLOSED"

class LegalDocumentCategory(str, Enum):
    CASE_LAW = "CASE_LAW"
    STATUTE = "STATUTE"
    REGULATION = "REGULATION"
    LEGAL_COMMENTARY = "LEGAL_COMMENTARY"
    LEGAL_FORM = "LEGAL_FORM"

# Add Relationship enum
class Relationship(str, Enum):
    SELF = "Self"
    PARENT = "Parent"
    CHILD = "Child"
    SIBILING = "Sibiling"
    FRIEND = "Friend"
    REPRESENTATIVE = "Representative"
    OTHER = "Other"

# Request/Response models for agent tools
class Address(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postalCode: Optional[str] = None
    country: Optional[str] = None

class UserPreferences(BaseModel):
    notificationsEnabled: bool = True
    language: Optional[str] = "en-US"
    timezone: Optional[str] = "UTC"

class IncidentDetails(BaseModel):
    datetime: datetime
    location: str
    description: str
    witnesses: Optional[List[Dict[str, str]]] = []
    policeReportNumber: Optional[str] = None
    injuries: Optional[List[str]] = []
    workRelated: Optional[bool] = False

class SaveClaimRequest(BaseModel):
    title: str
    description: str
    incident: IncidentDetails
    status: ClaimStatus = ClaimStatus.PENDING_INFORMATION
    assignedCaseManager: Optional[str] = None
    injured: bool = True
    healthInsurance: Optional[bool] = None
    user_id: str
    relationship: Optional[Relationship] = None
    otherRelationship: Optional[str] = None 
    healthInsuranceNumber: Optional[str] = None  
    isOver65: Optional[bool] = None  
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Motor Vehicle Accident Claim",
                "description": "Rear-end collision at Main St and 5th Ave",
                "incident": {
                    "datetime": "2024-01-15T14:30:00Z",
                    "location": "Main St and 5th Ave, Anytown, USA",
                    "description": "Rear-ended by another vehicle while stopped at red light",
                    "witnesses": [{"name": "John Doe", "phone": "555-123-4567"}],
                    "policeReportNumber": "PR12345678",
                    "injuries": ["Whiplash", "Back pain"],
                    "workRelated": False
                },
                "status": "PENDING_INFORMATION",
                "assignedCaseManager": "cm_12345",
                "injured": True,
                "healthInsurance": True
            }
        }
    }

class UpdateClaimRequest(BaseModel):
    title: Optional[str] = Field(None, description="Brief title for the claim")
    description: Optional[str] = Field(None, description="Detailed description of the claim")
    status: Optional[ClaimStatus] = Field(None, description="Current status of the claim")
    assignedCaseManager: Optional[str] = Field(None, description="ID of the assigned case manager")
    injured: Optional[bool] = Field(None, description="Whether the user was injured")
    healthInsurance: Optional[bool] = Field(None, description="Whether the user has health insurance")
    relationship: Optional[Relationship] = Field(None, description="Relationship to the injured party")
    otherRelationship: Optional[str] = Field(None, description="Specify if relationship is 'Other'")
    healthInsuranceNumber: Optional[str] = Field(None, description="Health insurance number if applicable")
    isOver65: Optional[bool] = Field(None, description="Whether the user is over 65 years old")
    incident_workRelated: Optional[bool] = Field(None, description="Whether the incident was work related")
    
    # Incident fields as individual options
    incident_datetime: Optional[datetime] = Field(None, description="When the incident occurred")
    incident_location: Optional[str] = Field(None, description="Where the incident occurred")
    incident_description: Optional[str] = Field(None, description="Detailed description of the incident")
    incident_witnesses: Optional[List[Dict[str, str]]] = Field(None, description="List of witnesses")
    incident_policeReportNumber: Optional[str] = Field(None, description="Police report number if available")
    incident_injuries: Optional[List[str]] = Field(None, description="List of injuries sustained")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "Updated claim title",
                    "description": "Example of updating just the title"
                },
                {
                    "incident_location": "123 Main St, Anytown",
                    "description": "Example of updating just the incident location"
                },
                {
                    "status": "UNDER_REVIEW",
                    "assignedCaseManager": "cm_12345",
                    "description": "Example of updating multiple fields"
                }
            ]
        }
    }

# Enhanced model for more detailed incident updates
class IncidentUpdateRequest(BaseModel):
    incident_datetime: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    witnesses: Optional[List[Dict[str, str]]] = None
    policeReportNumber: Optional[str] = None
    injuries: Optional[List[str]] = None

class SearchLegalRequest(BaseModel):
    q: str = Field(..., description="Search query for legal knowledge")
    category: Optional[LegalDocumentCategory] = None
    jurisdiction: Optional[str] = None
    minDate: Optional[date] = None
    maxDate: Optional[date] = None
    limit: conint(ge=1, le=100) = 10
    offset: conint(ge=0) = 0
    sortBy: str = "relevance"
    sortOrder: str = "desc"

class UpdateProfileRequest(BaseModel):
    firstName: Optional[str] = Field(None, description="User's first name")
    lastName: Optional[str] = Field(None, description="User's last name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    phoneNumber: Optional[str] = Field(None, description="User's phone number")
    dateOfBirth: Optional[date] = Field(None, description="User's date of birth")
    
    # Address fields as individual options
    address_street: Optional[str] = Field(None, description="Street address")
    address_city: Optional[str] = Field(None, description="City")
    address_state: Optional[str] = Field(None, description="State")
    address_postalCode: Optional[str] = Field(None, description="Postal code")
    address_country: Optional[str] = Field(None, description="Country")
    
    # Preference fields as individual options
    preferences_notificationsEnabled: Optional[bool] = Field(None, description="Whether notifications are enabled")
    preferences_language: Optional[str] = Field(None, description="Preferred language")
    preferences_timezone: Optional[str] = Field(None, description="Preferred timezone")
    preferences: Optional[UserPreferences] = Field(None, description="User preferences object")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "firstName": "John",
                    "description": "Example of updating just the first name"
                },
                {
                    "address_city": "New York",
                    "description": "Example of updating just the city"
                },
                {
                    "phoneNumber": "+1234567890",
                    "preferences_language": "es-ES",
                    "description": "Example of updating multiple fields"
                }
            ]
        }
    }

# Chat request/response models
class ChatMessage(BaseModel):
    message: str
    user_id: str
    claim_id: Optional[str] = Field(None, description="Optional claim ID for claim-specific conversations")
    thread_id: Optional[str] = Field(None, description="Thread ID for continuing conversations")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for tracking conversations")

class ChatResponse(BaseModel):
    message: str
    success: bool
    thread_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: str
    timestamp: float
    agent_type: Optional[str] = None
    error: Optional[str] = None

# ============================================================================
# CONNECTED AGENTS CHAT ENDPOINTS
# ============================================================================

@app.post("/chat/initial", 
          response_model=ChatResponse,
          tags=["chat"],
          summary="Initial Chat Interaction",
          description="""Handle the initial chat interaction with a user.
          
          This endpoint processes the first message from a user and routes it to the
          appropriate agent based on the message content and user context.
          
          **Flow**:
          1. User sends initial message
          2. System determines appropriate agent
          3. Agent processes message and responds
          4. Conversation thread is created
          """)
async def chat_initial_endpoint(
    chat_message: ChatMessage, 
    background_tasks: BackgroundTasks
):
    """Initial intake chat endpoint using Connected Agents architecture"""
    try:
        # Log the incoming message
        logger.info(f"Initial chat message from user {chat_message.user_id}, claim_id: {chat_message.claim_id}")
        
        # Process the message with the AI agent service
        response = await ai_agent_service.process_message(
            message=chat_message.message,
            user_id=chat_message.user_id,
            thread_id=None,  # New conversation
            claim_id=chat_message.claim_id
        )
        
        # Log the response in the background
        background_tasks.add_task(
            log_agent_activity,
            "chat_tool",
            "initial_chat_response",
            user_id=chat_message.user_id,
            tool_parameters={
                "message_length": len(chat_message.message),
                "response_length": len(response.get("message", "")),
                "claim_id": chat_message.claim_id,
                "thread_id": response.get("thread_id"),
                "agent_type": response.get("agent_type")
            }
        )
        
        return ChatResponse(
            message=response.get("message", "No response"),
            success=True,
            thread_id=response.get("thread_id"),
            conversation_id=response.get("conversation_id"),
            user_id=chat_message.user_id,
            timestamp=time.time(),
            agent_type=response.get("agent_type")
        )
        
    except Exception as e:
        logger.error(f"Error in initial chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to process chat message",
                "details": str(e)
            }
        )

@app.post("/chat/portal", 
          response_model=ChatResponse,
          tags=["chat"],
          summary="Portal Chat Interaction",
          description="""Handle chat interactions from Azure AI Foundry Portal.
          
          This endpoint processes messages from users interacting through the Azure AI Foundry Portal
          and routes them to the appropriate agent based on the message content and user context.
          
          **Flow**:
          1. User sends message through Azure AI Foundry Portal
          2. System determines appropriate agent
          3. Agent processes message and responds
          4. Conversation thread is managed by Azure AI Foundry
          """)
async def chat_portal_endpoint(
    chat_message: ChatMessage, 
    background_tasks: BackgroundTasks
):
    """Portal chat endpoint using Connected Agents architecture"""
    try:
        # Log the incoming message
        logger.info(f"Portal chat message from user {chat_message.user_id}, claim_id: {chat_message.claim_id}")
        
        # Process the message with the AI agent service
        response = await ai_agent_service.process_message(
            message=chat_message.message,
            user_id=chat_message.user_id,
            thread_id=chat_message.thread_id,
            claim_id=chat_message.claim_id
        )
        
        # Log the response in the background
        background_tasks.add_task(
            log_agent_activity,
            "chat_tool",
            "portal_chat_response",
            user_id=chat_message.user_id,
            tool_parameters={
                "message_length": len(chat_message.message),
                "response_length": len(response.get("message", "")),
                "claim_id": chat_message.claim_id,
                "thread_id": response.get("thread_id"),
                "conversation_id": response.get("conversation_id"),
                "agent_type": response.get("agent_type")
            }
        )
        
        return ChatResponse(
            message=response.get("message", "No response"),
            success=True,
            thread_id=response.get("thread_id"),
            conversation_id=response.get("conversation_id"),
            user_id=chat_message.user_id,
            timestamp=time.time(),
            agent_type=response.get("agent_type")
        )
        
    except Exception as e:
        logger.error(f"Error in portal chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to process chat message",
                "details": str(e)
            }
        )

@app.post("/api/chat/continue", 
          response_model=ChatResponse,
          tags=["chat"],
          summary="Continue Chat Conversation",
          description="""Continue an existing chat conversation.
          
          This endpoint processes follow-up messages in an ongoing conversation,
          maintaining context and conversation history.
          
          **Flow**:
          1. User sends message in existing thread
          2. System retrieves conversation history
          3. Current agent processes message with context
          4. System returns response and updates conversation
          """)
async def chat_continue_endpoint(
    chat_message: ChatMessage, 
    background_tasks: BackgroundTasks
):
    """Continue an existing chat conversation"""
    try:
        if not chat_message.thread_id and not chat_message.conversation_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Either thread_id or conversation_id is required"
                }
            )
            
        # Log the incoming message
        logger.info(
            f"Continuing chat for user {chat_message.user_id} "
            f"in thread {chat_message.thread_id or 'new'}, claim_id: {chat_message.claim_id}"
        )
        
        # Process the message with the AI agent service
        response = await ai_agent_service.process_message(
            message=chat_message.message,
            user_id=chat_message.user_id,
            thread_id=chat_message.thread_id,
            claim_id=chat_message.claim_id
        )
        
        # Log the response in the background
        background_tasks.add_task(
            log_agent_activity,
            "chat_tool",
            "chat_continued",
            user_id=chat_message.user_id,
            tool_parameters={
                "message_length": len(chat_message.message),
                "response_length": len(response.get("message", "")),
                "claim_id": chat_message.claim_id,
                "thread_id": response.get("thread_id"),
                "conversation_id": response.get("conversation_id"),
                "agent_type": response.get("agent_type")
            }
        )
        
        return ChatResponse(
            message=response.get("message", "No response"),
            success=True,
            thread_id=response.get("thread_id"),
            conversation_id=response.get("conversation_id"),
            user_id=chat_message.user_id,
            timestamp=time.time(),
            agent_type=response.get("agent_type")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat continuation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to process chat message",
                "details": str(e)
            }
        )

# Agent status endpoint
@app.get("/agents/status",
         tags=["system"],
         summary="Agent Status",
         description="""Get the status of configured Azure AI Foundry agents.
         
         This endpoint provides information about the deployed agents,
         their configuration, and current operational status.
         
         **Returns**: Agent configuration and health status
         **Use Cases**: Monitoring, debugging, system verification
         """)
async def get_agents_status():
    """Get the status of configured Azure AI agents"""
    try:
        status = await ai_agent_service.get_agent_status()
        return status
    except Exception as e:
        logger.error(f"Error getting agent status: {str(e)}")
        raise HTTPException()

@app.delete("/chat/threads/{thread_id}",
            tags=["chat"],
            summary="Delete Azure AI Thread",
            description="""Delete a conversation thread from Azure AI Foundry.
            
            This endpoint is called by the Next.js app after a conversation ends
            to clean up the thread from Azure's infrastructure.
            """)
async def delete_thread_endpoint(
    thread_id: str = Path(...),
    request: Request = None,
    background_tasks: BackgroundTasks = None
):
    """Delete a conversation thread from Azure AI Foundry"""
    # Log what the agent is sending
    logger.info("delete_thread called. thread_id=%s type=%s query=%s", thread_id, type(thread_id).__name__, dict(request.query_params) if request else {})
    
    try:
        # Delete the thread using the AI agent service
        success = await ai_agent_service.delete_thread(thread_id)
        
        if not success:
            # Log the failed deletion in the background
            background_tasks.add_task(
                log_agent_activity,
                "chat_tool",
                "thread_deleted",
                user_id=None,
                tool_parameters={
                    "thread_id": thread_id,
                    "status": "failed"
                }
            )
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "Failed to delete thread. It may have already been deleted.",
                    "thread_id": thread_id
                }
            )
        
        # Log the successful deletion in the background
        background_tasks.add_task(
            log_agent_activity,
            "chat_tool",
            "thread_deleted",
            user_id=None,
            tool_parameters={
                "thread_id": thread_id,
                "status": "success"
            }
        )
        
        return {
            "success": True,
            "message": "Thread deleted successfully",
            "thread_id": thread_id
        }
    except Exception as e:
        logger.error(f"Error in delete thread endpoint: {str(e)}", exc_info=True)
        
        # Log the error in the background
        background_tasks.add_task(
            log_agent_activity,
            "chat_tool",
            "thread_deleted",
            user_id=None,
            tool_parameters={
                "thread_id": thread_id,
                "status": "error",
                "error_message": str(e)
            }
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "message": "An error occurred while deleting the thread",
                "thread_id": thread_id
            }
        )

# ============================================================================
# CLAIM MANAGEMENT TOOLS
# ============================================================================

@app.post("/api/claims",
          tags=["claims-tools"],
          summary="Create New Claim",
          status_code=201,
          response_model=dict,
          description="""Create a new claim in the system.
          
          This endpoint allows agents to create new claims with detailed incident information.
          
          **Agent Usage**: Claim creation agent
          **Database**: PostgreSQL claims table
          """)
async def create_claim_endpoint(
    request: SaveClaimRequest,
    background_tasks: BackgroundTasks
):
    """Create a new claim with the provided details"""
    try:
        logger.info(f"Creating claim for user {request.user_id}")
        claim_data = request.dict()
        # Call the database service to save the claim
        result = await save_claim_data(claim_data)
        
        # Log the claim creation in background
        background_tasks.add_task(
            log_agent_activity,
            "claim_tool",
            "claim_created",
            user_id=request.user_id,
            tool_parameters={"claim_id": result.get("id")}
        )
        
        logger.info(f"Claim created successfully: {result.get('id')}")
        return {
            "success": True,
            "message": "Claim created successfully",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error creating claim: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "Failed to create claim",
                "details": str(e)
            }
        )

@app.get("/api/users/{user_id}/claims",
          tags=["claims-tools"],
          summary="Get User Claims",
          response_model=dict,
          description="""Retrieve all claims for a specific user with filtering and pagination.
          
          This endpoint allows agents to access a user's claim history with various filters.
          
          **Agent Usage**: All agents for user context
          **Database**: PostgreSQL claims table
          """)
async def get_claims_endpoint(
    user_id: str = Path(...),
    status: Optional[ClaimStatus] = None,
    limit: int = 10,
    offset: int = 0,
    sort_by: str = "createdAt",
    sort_order: str = "desc",
    request: Request = None
):
    """Get paginated list of claims for a user with optional filtering"""
    # Log what the agent is sending
    logger.info("get_user_claims called. user_id=%s type=%s query=%s", user_id, type(user_id).__name__, dict(request.query_params) if request else {})
    
    try:
        # Validate limit
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 100"
            )
            
        # Get claims from database
        claims = await get_user_claims(
            external_user_id=user_id,
            status=status.value if status else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Get total count for pagination
        total_count = len(claims)
        
        return {
            "success": True,
            "data": claims,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "hasMore": (offset + limit) < total_count
            }
        }
    except Exception as e:
        logger.error(f"Error retrieving claims: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to retrieve claims",
                "details": str(e)
            }
        )

@app.get("/api/claims/{claim_id}",
          tags=["claims-tools"],
          summary="Get Claim Details",
          response_model=dict,
          description="""Retrieve details for a specific claim by ID.
          
          This endpoint allows agents to access detailed information about a specific claim.
          
          **Agent Usage**: Claim continuation agents for context awareness
          **Database**: PostgreSQL claims table
          """)
async def get_claim_endpoint(claim_id: str = Path(...), request: Request = None):
    """Get detailed information for a specific claim"""
    # Log what the agent is sending
    logger.info("get_claim called. claim_id=%s type=%s query=%s", claim_id, type(claim_id).__name__, dict(request.query_params) if request else {})
    
    try:
        # Get claim from database
        claim = await get_claim_by_id(claim_id)
        
        if not claim:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Claim not found"
                }
            )
            
        return {
            "success": True,
            "data": claim
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving claim: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to retrieve claim",
                "details": str(e)
            }
        )

@app.patch("/api/claims/{claim_id}",
          tags=["claims-tools"],
          summary="Update Claim (Incremental or Bulk)",
          response_model=dict,
          description="""Update an existing claim with one or more fields.
          
          Supports both incremental updates (single field) and bulk updates (multiple fields).
          Only provided fields will be updated. All fields are optional.
          
          **Agent Usage**: Claim management agents
          **Database**: PostgreSQL claims table
          **Validation**: Ensures claim exists and belongs to user
          """)
async def update_claim_endpoint(
    claim_id: str = Path(...),
    user_id: str = None,
    updates: UpdateClaimRequest = None,
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Update an existing claim with the provided updates"""
    # Log what the agent is sending
    logger.info("update_claim called. claim_id=%s type=%s query=%s", claim_id, type(claim_id).__name__, dict(request.query_params) if request else {})
    
    try:
        # Extract user_id from query parameters as per OpenAPI spec
        if request and request.query_params:
            user_id = request.query_params.get('user_id')
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "user_id is required as a query parameter"
                }
            )
        
        # Check if updates were provided
        if updates is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "No fields provided for update"
                }
            )
        
        # Convert Pydantic model to dict and remove None values
        update_data = updates.model_dump(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "No fields provided for update"
                }
            )
        
        # Handle incident fields - group them into an incident object
        incident_fields = {}
        for field in list(update_data.keys()):
            if field.startswith('incident_'):
                incident_fields[field.replace('incident_', '')] = update_data.pop(field)
        
        if incident_fields:
            update_data['incident'] = incident_fields
        
        # Update claim in database
        updated_claim = await update_claim_data(
            external_claim_id=claim_id,
            updates=update_data
        )
        
        if not updated_claim:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Claim not found or access denied"
                }
            )
        
        # Log the update in background
        background_tasks.add_task(
            log_agent_activity,
            "claim_tool",
            "claim_updated",
            user_id=user_id,
            tool_parameters={
                "claim_id": claim_id,
                "updated_fields": list(update_data.keys())
            }
        )
        
        return {
            "success": True,
            "message": "Claim updated successfully",
            "data": updated_claim,
            "updated_fields": list(update_data.keys())
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating claim {claim_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to update claim",
                "details": str(e)
            }
        )

# Legal Knowledge Tools
@app.get("/api/legal/search",
          tags=["legal-tools"],
          summary="Search Legal Knowledge",
          response_model=dict,
          description="""Search legal knowledge database with advanced filtering.
          
          This endpoint provides access to legal precedents, statutes, regulations, 
          and guidance documents with full-text search capabilities.
          
          **Agent Usage**: Legal research agents
          **Database**: Legal knowledge base
          **Features**: Full-text search, filtering, sorting, pagination
          """)
async def search_legal_endpoint(
    q: str,
    category: Optional[LegalDocumentCategory] = None,
    jurisdiction: Optional[str] = None,
    min_date: Optional[date] = None,
    max_date: Optional[date] = None,
    limit: int = 10,
    offset: int = 0,
    sort_by: str = "relevance",
    sort_order: str = "desc",
    user_id: Optional[str] = None
):
    """Search legal documents with advanced filtering and pagination"""
    try:
        # Validate parameters
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Limit must be between 1 and 100"
                }
            )
            
        if sort_by not in ["relevance", "date", "title"]:
            sort_by = "relevance"
            
        if sort_order not in ["asc", "desc"]:
            sort_order = "desc"
        
        # Log the search query for analytics
        logger.info(f"Legal search: {q[:100]}...")
        
        # Perform the search
        results = await search_legal_database(
            query_text=q,
            category=category,
            jurisdiction=jurisdiction,
            limit=limit
        )
        
        # Format response
        return {
            "success": True,
            "data": results,
            "pagination": {
                "total": len(results),  # Note: This should be total count, not just results length
                "limit": limit,
                "offset": offset,
                "hasMore": len(results) >= limit
            },
            "queryInfo": {
                "originalQuery": q,
                "searchTimeMs": 0  # Would be populated by the search function
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in legal search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to perform legal search",
                "details": str(e)
            }
        )

# User Profile Tools
@app.get("/api/users/{user_id}",
          tags=["users-tools"],
          summary="Get User Profile",
          response_model=dict,
          description="""Retrieve a user's profile information.
          
          This endpoint provides access to user profile data for personalization
          and context-aware assistance.
          
          **Agent Usage**: All agents for user context
          **Database**: PostgreSQL users table
          **Sensitive Data**: Handled securely with appropriate access controls
          """)
async def get_profile_endpoint(user_id: str = Path(...), request: Request = None):
    """Get a user's profile information"""
    # Log what the agent is sending
    logger.info("get_profile called. user_id=%s type=%s query=%s", user_id, type(user_id).__name__, dict(request.query_params) if request else {})
    
    try:
        logger.info(f"Fetching profile for user {user_id}")
        
        # Get user profile from database
        profile = await get_user_profile(user_id)
        
        if not profile:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found"
                }
            )
            
        return {
            "success": True,
            "data": profile
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to retrieve user profile",
                "details": str(e)
            }
        )

@app.patch("/api/users/{user_id}",
          tags=["users-tools"],
          summary="Update User Profile (Incremental or Bulk)",
          response_model=dict,
          operation_id="update_user_profile_tool",
          description="""Update a user's profile with one or more fields.
          
          Supports both incremental updates (single field) and bulk updates (multiple fields).
          Only provided fields will be updated. All fields are optional.
          
          **Agent Usage**: Profile management agents
          **Database**: PostgreSQL users table
          **Validation**: Comprehensive data validation
          """)
async def update_profile_endpoint(
    user_id: str = Path(...),
    updates: UpdateProfileRequest = None,
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Update a user's profile with the provided updates"""
    # Log what the agent is sending
    logger.info("update_profile called. user_id=%s type=%s query=%s", user_id, type(user_id).__name__, dict(request.query_params) if request else {})
    
    try:
        logger.info(f"Updating profile for user {user_id}")
        
        # Convert Pydantic model to dict and remove None values
        update_data = updates.model_dump(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "No fields provided for update"
                }
            )
        
        # Handle address fields - group them into a mailing_address object
        address_fields = {}
        for field in list(update_data.keys()):
            if field.startswith('address_'):
                address_fields[field.replace('address_', '')] = update_data.pop(field)
        
        if address_fields:
            # Map the address fields to the expected mailing_address structure
            mailing_address = {}
            field_mapping = {
                'street': 'address1',
                'city': 'city',
                'state': 'state',
                'postalCode': 'zip_code',
                'country': 'country'
            }
            
            for api_field, db_field in field_mapping.items():
                if api_field in address_fields:
                    mailing_address[db_field] = address_fields[api_field]
            
            if mailing_address:
                update_data['mailing_address'] = mailing_address
        
        # Handle preference fields - group them into a preferences object
        preference_fields = {}
        for field in list(update_data.keys()):
            if field.startswith('preferences_'):
                preference_fields[field.replace('preferences_', '')] = update_data.pop(field)
        
        
        # Ensure user exists before updating
        from .services.database import ensure_user_exists
        user_exists = await ensure_user_exists(user_id)
        if not user_exists:
            logger.warning(f"User not found and could not be created: {user_id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found"
                }
            )
        
        # Update profile in database
        updated_profile = await update_user_profile(
            external_user_id=user_id,
            updates=update_data
        )
        
        if not updated_profile:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found or update failed"
                }
            )
        
        # Log the update in background
        background_tasks.add_task(
            log_agent_activity,
            "user_tool",
            "profile_updated",
            user_id=user_id,
            tool_parameters={
                "updated_fields": list(update_data.keys())
            }
        )
        
        return {
            "success": True,
            "message": "Profile updated successfully",
            "data": updated_profile,
            "updated_fields": list(update_data.keys())
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to update profile",
                "details": str(e)
            }
        )

# ============================================================================
# SYSTEM ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Legal Claims Assistant API",
        "version": "2.0.0",
        "status": "operational",
        "architecture": "Azure Connected Agents",
        "workflow": "User → /chat/initial or /chat/portal → Orchestrator → Specialized Agents → Tools → PostgreSQL",
        "endpoints": {
            "chat_initial": "/chat/initial",
            "chat_portal": "/chat/portal",
            "agents_status": "/agents/status",
            "tools": "/tools/*",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    from .services.database import get_db_status
    
    db_status = await get_db_status()
    
    return {
        "status": "healthy" if db_status.get("connected", False) else "degraded",
        "timestamp": time.time(),
        "architecture": "Azure AI Foundry + FastAPI + PostgreSQL",
        "workflow": "User → /chat/initial or /chat/portal → Orchestrator → Specialized Agents → Tools → PostgreSQL",
        "database": db_status,
        "components": {
            "fastapi": "operational",
            "database": "connected" if db_status.get("connected", False) else "disconnected",
            "agents": "configured"
        },
        "endpoints": {
            "openapi_schema": "/openapi.json",
            "swagger_ui": "/docs",
            "redoc": "/redoc"
        }
    }

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"message": "Endpoint not found", "path": str(request.url.path)}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "type": "server_error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",  # Listen on localhost only
        port=8000,
        reload=False,  # Set to False when running as module
        log_level="info"
    )