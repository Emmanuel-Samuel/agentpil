from fastapi import FastAPI, HTTPException, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager
import time
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from .config.config import settings
from .services.database import (
    get_user_by_id, 
    get_user_claims, 
    create_claim, 
    get_claim_by_id, 
    update_claim,
    update_user,
    initialize_db,
    close_db
)
from .services.ai_agent_service import ai_agent_service

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("Starting FastAPI application...")
    
    # Initialize database and AI service
    await initialize_db()
    await ai_agent_service.initialize()
    
    logger.info("Application started - OpenAPI docs at /docs")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await ai_agent_service.close()
    await close_db()
    logger.info("Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="AI Legal Claims Assistant",
    description="Simplified FastAPI application with Azure AI Foundry integration",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Enums
class ClaimStatus(str, Enum):
    PENDING_INFORMATION = "PENDING_INFORMATION"
    UNDER_REVIEW = "UNDER_REVIEW"
    PENDING_DOCUMENTS = "PENDING_DOCUMENTS"
    INVESTIGATION = "INVESTIGATION"
    PRE_SUIT = "PRE_SUIT"
    PRE_LITIGATION = "PRE_LITIGATION"
    LITIGATION = "LITIGATION"
    RESOLVED_AND_CLOSED = "RESOLVED_AND_CLOSED"

class Relationship(str, Enum):
    SELF = "Self"
    PARENT = "Parent"
    CHILD = "Child"
    SIBLING = "Sibling"
    FRIEND = "Friend"
    REPRESENTATIVE = "Representative"
    OTHER = "Other"

# Simplified Models
class WitnessInfo(BaseModel):
    name: str
    phone: Optional[str] = None

class IncidentDetails(BaseModel):
    datetime: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    workRelated: Optional[bool] = None
    reportCompleted: Optional[bool] = None
    policeReportCompleted: Optional[bool] = None
    supportingDocument: Optional[bool] = None
    witness: Optional[bool] = None
    priorRepresentation: Optional[bool] = None
    lostEarning: Optional[str] = None
    reportNumber: Optional[str] = None
    vehicleRole: Optional[str] = None
    vehicleCount: Optional[int] = None
    busOrVehicle: Optional[str] = None
    transportType: Optional[str] = None
    rideShareCompany: Optional[str] = None
    rideShareOtherName: Optional[str] = None
    propertyType: Optional[str] = None
    amountLoss: Optional[str] = None
    timeLoss: Optional[str] = None
    priorRepresentationReason: Optional[str] = None
    # Relationship IDs
    policeStationId: Optional[str] = None
    policeOfficerId: Optional[str] = None
    lawfirmId: Optional[str] = None
    attorneyId: Optional[str] = None

class SaveClaimRequest(BaseModel):
    title: str
    description: str
    incident: IncidentDetails
    status: Optional[ClaimStatus] = ClaimStatus.PENDING_INFORMATION
    injured: Optional[bool] = True
    healthInsurance: Optional[bool] = None
    userId: str
    relationship: Optional[Relationship] = None
    otherRelationship: Optional[str] = None
    healthInsuranceNumber: Optional[str] = None
    isOver65: Optional[bool] = None

class UpdateClaimRequest(BaseModel):
    """Request model for updating claim data"""
    status: Optional[ClaimStatus] = None
    injured: Optional[bool] = None
    relationship: Optional[Relationship] = None
    otherRelationship: Optional[str] = None
    healthInsurance: Optional[bool] = None
    healthInsuranceNumber: Optional[str] = None
    isOver65: Optional[bool] = None
    receiveMedicare: Optional[List[str]] = Field(None, alias="receiveMedicare")
    assignedCaseManager: Optional[str] = None
    # Relationship IDs
    clientRoleId: Optional[str] = None
    injuredPartyRoleId: Optional[str] = None
    healthInsuranceProviderId: Optional[str] = None
    incident: Optional[IncidentDetails] = None

class UpdateUserRequest(BaseModel):
    """Request model for updating user profile"""
    firstName: Optional[str] = None
    middleName: Optional[str] = None
    lastName: Optional[str] = None
    injured: Optional[str] = None  # WereYouInjured enum as string
    email: Optional[str] = None
    phone: Optional[str] = None
    phoneNumber: Optional[str] = None  # Alias for phone
    phone2: Optional[str] = None
    gender: Optional[str] = None
    dateOfBirth: Optional[str] = None
    isUnder18: Optional[bool] = None
    # Parent info
    fatherFirstName: Optional[str] = None
    fatherLastName: Optional[str] = None
    motherFirstName: Optional[str] = None
    motherLastName: Optional[str] = None
    # Mailing address
    mailingAddress1: Optional[str] = None
    mailingAddress2: Optional[str] = None
    mailingCity: Optional[str] = None
    mailingState: Optional[str] = None
    mailingZipCode: Optional[str] = None
    # Address aliases for backward compatibility
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    address_postalCode: Optional[str] = None
    # Physical address
    isPOBoxOrDifferentAddress: Optional[bool] = None
    physicalAddress1: Optional[str] = None
    physicalAddress2: Optional[str] = None
    physicalCity: Optional[str] = None
    physicalState: Optional[str] = None
    physicalZipCode: Optional[str] = None
    # Personal info
    maritalStatus: Optional[str] = None
    spouseFirstName: Optional[str] = None
    spouseLastName: Optional[str] = None
    spousePhone: Optional[str] = None
    # Employment
    employmentStatus: Optional[str] = None
    employerName: Optional[str] = None
    employerTitle: Optional[str] = None
    employmentType: Optional[str] = None
    pay: Optional[str] = None
    # Education
    schoolName: Optional[str] = None
    expectedGraduationYear: Optional[str] = None
    # System fields
    role: Optional[str] = None
    isVerified: Optional[bool] = None
    verificationCode: Optional[str] = None
    sourceId: Optional[str] = None
    accountSync: Optional[str] = None

class ChatMessage(BaseModel):
    message: str
    user_id: str
    claim_id: Optional[str] = None
    thread_id: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    success: bool
    thread_id: Optional[str] = None
    user_id: str
    timestamp: float
    error: Optional[str] = None

@app.post("/chat/initial", response_model=ChatResponse, tags=["chat"])
async def chat_initial_endpoint(chat_message: ChatMessage):
    """Initial chat interaction - routes to initial intake agent"""
    try:
        if not chat_message.user_id.strip():
            raise HTTPException(status_code=400, detail="Invalid user_id")
        
        logger.info(f"Initial chat from user {chat_message.user_id}")
        
        # Process with AI agent service
        response = await ai_agent_service.chat(
            message=chat_message.message,
            user_id=chat_message.user_id,
            thread_id=None,  # New conversation
            claim_id=chat_message.claim_id
        )
        
        return ChatResponse(
            message=response.get("message", "No response"),
            success=response.get("success", True),
            thread_id=response.get("thread_id"),
            user_id=chat_message.user_id,
            timestamp=time.time(),
            error=response.get("error")
        )
        
    except Exception as e:
        logger.error(f"Error in initial chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/portal", response_model=ChatResponse, tags=["chat"])
async def chat_portal_endpoint(chat_message: ChatMessage):
    """Portal chat interaction - routes to portal agent"""
    try:
        logger.info(f"Portal chat from user {chat_message.user_id}")
        
        # Process with AI agent service
        response = await ai_agent_service.chat(
            message=chat_message.message,
            user_id=chat_message.user_id,
            thread_id=chat_message.thread_id,
            claim_id=chat_message.claim_id
        )
        
        return ChatResponse(
            message=response.get("message", "No response"),
            success=response.get("success", True),
            thread_id=response.get("thread_id"),
            user_id=chat_message.user_id,
            timestamp=time.time(),
            error=response.get("error")
        )
        
    except Exception as e:
        logger.error(f"Error in portal chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/threads/{thread_id}", tags=["chat"])
async def delete_thread_endpoint(thread_id: str = Path(...)):
    """Delete a conversation thread"""
    try:
        success = await ai_agent_service.delete_thread(thread_id)
        
        return {
            "success": success,
            "message": "Thread deleted successfully" if success else "Failed to delete thread",
            "thread_id": thread_id
        }
        
    except Exception as e:
        logger.error(f"Error deleting thread: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "message": "Error occurred while deleting thread",
                "thread_id": thread_id
            }
        )


@app.post("/api/claims", 
          status_code=201,
          operation_id="create_claim_tool",
          tags=["claims"])
async def create_claim_endpoint(request: SaveClaimRequest):
    """Create a new claim"""
    try:
        if not request.userId.strip():
            raise HTTPException(status_code=400, detail="Invalid userId")
        
        logger.info(f"Creating claim for user {request.userId}")
        
        # Create claim using database service
        result = await create_claim(request.model_dump())
        
        if not result or not result.get("success"):
            raise HTTPException(
                status_code=500, 
                detail=result.get("message", "Failed to create claim")
            )
        
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Claim created successfully",
                "data": result
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating claim: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}/claims", tags=["claims"])
async def get_claims_endpoint(
    user_id: str = Path(...),
    status: Optional[ClaimStatus] = None,
    limit: int = 10,
    offset: int = 0
):
    """Get claims for a user"""
    try:
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        
        claims = await get_user_claims(
            user_id=user_id,
            status=status.value if status else None
        )
        
        # Apply pagination
        paginated_claims = claims[offset:offset + limit]
        
        return {
            "success": True,
            "data": paginated_claims,
            "pagination": {
                "total": len(claims),
                "limit": limit,
                "offset": offset,
                "hasMore": (offset + limit) < len(claims)
            }
        }
        
    except Exception as e:
        logger.error(f"Error retrieving claims: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/claims/{claim_id}", 
         operation_id="get_claim_tool",
         tags=["claims"])
async def get_claim_endpoint(claim_id: str = Path(...)):
    """Get claim details"""
    try:
        if not claim_id.strip():
            raise HTTPException(status_code=400, detail="Invalid claim_id")
        
        claim = await get_claim_by_id(claim_id)
        
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        return {
            "success": True,
            "data": claim
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving claim: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/claims/{claim_id}", 
         operation_id="update_claim_data_tool",
         tags=["claims"])
async def update_claim_endpoint(
    request: UpdateClaimRequest,
    claim_id: str = Path(...)
):
    """Update claim data"""
    try:
        # Log the incoming request for debugging
        logger.info(f"Update claim request for claim_id: {claim_id}")
        logger.info(f"Request data: {request.model_dump()}")
        
        # Convert request to dict, excluding None values
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        
        logger.info(f"Filtered updates: {updates}")
        
        if not updates:
            logger.warning("No valid fields to update")
            raise HTTPException(status_code=400, detail="No valid fields to update. Please provide at least one field to update.")
        
        result = await update_claim(claim_id, updates)
        
        if not result:
            logger.warning(f"Claim not found or update failed for claim_id: {claim_id}")
            raise HTTPException(status_code=404, detail="Claim not found or update failed")
        
        logger.info(f"Successfully updated claim {claim_id}")
        return {
            "success": True,
            "message": "Claim updated successfully",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating claim {claim_id}: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.patch("/api/users/{user_id}", 
          operation_id="update_user_profile_tool",
          tags=["users"])
async def update_user_profile_endpoint(
    request: UpdateUserRequest,
    user_id: str = Path(...)
):
    """Update user profile"""
    try:
        # Convert request to dict, excluding None values
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        result = await update_user(user_id, updates)
        
        if not result:
            raise HTTPException(status_code=404, detail="User not found or update failed")
        
        return {
            "success": True,
            "message": "User profile updated successfully",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/users/{user_id}", 
         operation_id="get_user_profile_tool",
         tags=["users"])
async def get_user_endpoint(user_id: str = Path(...)):
    """Get user profile"""
    try:
        if not user_id.strip():
            raise HTTPException(status_code=400, detail="Invalid user_id")
        
        user = await get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "success": True,
            "data": user
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/status", tags=["system"])
async def get_agents_status():
    """Get agent service status"""
    try:
        return await ai_agent_service.get_status()
    except Exception as e:
        logger.error(f"Error getting agent status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/", tags=["system"])
async def root():
    """Root endpoint"""
    return {
        "message": "AI Legal Claims Assistant API", 
        "status": "healthy", 
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",  # Listen on localhost only
        port=8000,
        reload=False,  # Set to False when running as module
        log_level="info"
    )
