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
    """
    if not db_service:
        logger.error("Database service not initialized.")
        return json.dumps({"status": "error", "message": "Database service not initialized."})

    try:
        if email:
            # Simple query without cross-partition requirements
            query = "SELECT * FROM c WHERE c.email = @email"
            parameters = [{"name": "@email", "value": email}]
            logger.info(f"Executing query for email: {email}")
        elif phone:
            # Simple query for phone - try exact match first, then partial match
            query = "SELECT * FROM c WHERE c.phoneNumber = @phone"
            parameters = [{"name": "@phone", "value": phone}]
            logger.info(f"Executing query for phone: {phone}")
        else:
            logger.error("Either email or phone must be provided.")
            return json.dumps({"status": "error", "message": "Either email or phone must be provided."})

        items = await db_service.query_items(query, parameters)
        logger.info(f"Query returned {len(items)} items.")
        
        # If no exact phone match found, try a more flexible search
        if not items and phone:
            # Clean phone number and try again
            clean_phone = ''.join(filter(str.isdigit, phone))
            if len(clean_phone) >= 10:  # Only if we have enough digits
                # Try with different formats
                formatted_phones = [
                    f"{clean_phone[:3]}-{clean_phone[3:6]}-{clean_phone[6:10]}",
                    f"({clean_phone[:3]}) {clean_phone[3:6]}-{clean_phone[6:10]}",
                    clean_phone
                ]
                
                for formatted_phone in formatted_phones:
                    query = "SELECT * FROM c WHERE c.phoneNumber = @phone"
                    parameters = [{"name": "@phone", "value": formatted_phone}]
                    items = await db_service.query_items(query, parameters)
                    if items:
                        break
        
        if items:
            claim = items[0]
            claim_type = claim.get("claimType", "")
            logger.info(f"Found claim with ID: {claim.get('id')}, claimType: {claim_type}")
            
            # Define the expected fields for each claim type
            car_accident_fields = [
                "dateOfAccident", "locationOfAccident", "descriptionOfAccident", 
                "injuriesSustained", "policeReportNumber", "otherPartyInsurance",
                "vehicleDamage", "medicalTreatment", "witnesses", "trafficViolations",
                "roleInVehicle", "numberOfVehicles", "incidentDate", "incidentLocation",
                "incidentDescription", "policeCalled", "picturesTaken", "takenToHospital",
                "isCurrentlyTreated", "hasHealthInsurance"
            ]
            
            # Add more claim types as needed
            claim_type_fields = {
                "car_accident": car_accident_fields,
                # Add other claim types here
                # "motorcycle_accident": motorcycle_accident_fields,
                # "pedestrian_accident": pedestrian_accident_fields,
            }
            
            # Determine what fields to check based on claim type
            if claim_type == "new_claim_initiation":
                # For new claim initiation, check basic fields
                basic_fields = ["Client_First_Name", "Client_Last_Name", "email", "phoneNumber"]
                first_null_field = None
                for field in basic_fields:
                    if claim.get(field) is None or claim.get(field) == "":
                        first_null_field = field
                        break
                
                if first_null_field:
                    status = "incomplete"
                else:
                    status = "ready_for_transition"  # Ready to transition to specific claim type
                    
            elif claim_type in claim_type_fields:
                # For specific claim types, check all relevant fields
                expected_fields = claim_type_fields[claim_type]
                first_null_field = None
                for field in expected_fields:
                    if claim.get(field) is None or claim.get(field) == "":
                        first_null_field = field
                        break
                
                status = "incomplete" if first_null_field else "complete"
                
            else:
                # For unknown claim types or basic claims, check for basic info first
                basic_fields = ["Client_First_Name", "Client_Last_Name", "email", "phoneNumber"]
                first_null_field = None
                for field in basic_fields:
                    if claim.get(field) is None or claim.get(field) == "":
                        first_null_field = field
                        break
                
                if not first_null_field:
                    # Basic info complete, but claim type might need to be more specific
                    if claim_type in ["car_accident", "motorcycle_accident", "pedestrian_accident"]:
                        # Check specific fields for this claim type
                        if claim_type in claim_type_fields:
                            expected_fields = claim_type_fields[claim_type]
                            for field in expected_fields:
                                if claim.get(field) is None or claim.get(field) == "":
                                    first_null_field = field
                                    break
                        status = "incomplete" if first_null_field else "complete"
                    else:
                        status = "ready_for_transition"
                else:
                    status = "incomplete"
            
            logger.info(f"Claim status: {status}, first_null_field: {first_null_field}")
            
            return json.dumps({
                "status": status,
                "claim_id": claim.get("id"),
                "claimType": claim_type,
                "first_null_field": first_null_field
            })
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
        # Create a new claim with initial data
        new_claim = {
            "user_id": user_id,
            "claimType": claim_data.get("claimType", "new_claim_initiation"),
            "status": "initiated",
            "created_at": "utcnow",
            # Add other initial fields as needed
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
        # Get the existing claim
        claim_item = await db_service.get_item(claim_id)
        
        # Update the claim type
        updates = {"claimType": new_claim_type}
        await db_service.update_item(claim_id, updates)
        
        logger.info(f"Claim {claim_id} transitioned to {new_claim_type}")
        
        # Define the expected fields for the new claim type
        car_accident_fields = [
            "dateOfAccident", "locationOfAccident", "descriptionOfAccident", 
            "injuriesSustained", "policeReportNumber", "otherPartyInsurance",
            "vehicleDamage", "medicalTreatment", "witnesses", "trafficViolations",
            "roleInVehicle", "numberOfVehicles", "incidentDate", "incidentLocation",
            "incidentDescription", "policeCalled", "picturesTaken", "takenToHospital",
            "isCurrentlyTreated", "hasHealthInsurance"
        ]
        
        claim_type_fields = {
            "car_accident": car_accident_fields,
            # Add other claim types here
        }
        
        # Find the first null field after transition
        first_null_field = None
        if new_claim_type in claim_type_fields:
            expected_fields = claim_type_fields[new_claim_type]
            for field in expected_fields:
                if claim_item.get(field) is None or claim_item.get(field) == "":
                    first_null_field = field
                    break
        else:
            # For unknown claim types, check basic fields
            basic_fields = ["Client_First_Name", "Client_Last_Name", "email", "phoneNumber"]
            for field in basic_fields:
                if claim_item.get(field) is None or claim_item.get(field) == "":
                    first_null_field = field
                    break
        
        return json.dumps({
            "status": "success", 
            "message": f"Claim {claim_id} has been transitioned to {new_claim_type}.",
            "first_null_field": first_null_field
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
        # Get the current claim to check for remaining null fields
        current_claim = await db_service.get_item(claim_id)
        claim_type = current_claim.get("claimType", "")
        
        # Update the claim
        await db_service.update_item(claim_id, updates)
        
        # Check for the next null field after the update
        updated_claim = {**current_claim, **updates}
        
        # Define expected fields based on claim type
        car_accident_fields = [
            "dateOfAccident", "locationOfAccident", "descriptionOfAccident", 
            "injuriesSustained", "policeReportNumber", "otherPartyInsurance",
            "vehicleDamage", "medicalTreatment", "witnesses", "trafficViolations",
            "roleInVehicle", "numberOfVehicles", "incidentDate", "incidentLocation",
            "incidentDescription", "policeCalled", "picturesTaken", "takenToHospital",
            "isCurrentlyTreated", "hasHealthInsurance"
        ]
        
        claim_type_fields = {
            "car_accident": car_accident_fields,
            # Add other claim types here
        }
        
        first_null_field = None
        if claim_type in claim_type_fields:
            expected_fields = claim_type_fields[claim_type]
            for field in expected_fields:
                if updated_claim.get(field) is None or updated_claim.get(field) == "":
                    first_null_field = field
                    break
        else:
            # For unknown claim types, check basic system fields
            basic_fields = ["Client_First_Name", "Client_Last_Name", "email", "phoneNumber"]
            for field in basic_fields:
                if updated_claim.get(field) is None or updated_claim.get(field) == "":
                    first_null_field = field
                    break
        
        status = "incomplete" if first_null_field else "complete"
        
        logger.info(f"Claim {claim_id} updated. Status: {status}")
        
        return json.dumps({
            "status": status, 
            "message": f"Claim {claim_id} updated.",
            "first_null_field": first_null_field
        })
        
    except Exception as e:
        logger.error(f"Failed to update claim: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to update claim: {str(e)}"})

async def get_question_by_fieldname(field_name: str, claim_type: str) -> str:
    """
    Get the appropriate question text for a specific field based on claim type.
    """
    try:
        with open("src/knowledge_base.json", "r") as f:
            knowledge_base = json.load(f)
        
        for question in knowledge_base["questions"]:
            if question["claimType"] == claim_type and question["fieldName"] == field_name:
                return json.dumps({"status": "success", "questionText": question["questionText"]})
        
        # If no specific question found, provide a generic one
        generic_question = f"Could you please provide information for {field_name.replace('_', ' ').title()}?"
        
        return json.dumps({
            "status": "success", 
            "questionText": generic_question,
            "note": "Generic question used - specific question not found in knowledge base"
        })
        
    except FileNotFoundError:
        logger.warning("Knowledge base file not found, using generic question")
        generic_question = f"Could you please provide information for {field_name.replace('_', ' ').title()}?"
        return json.dumps({"status": "success", "questionText": generic_question})
        
    except Exception as e:
        logger.error(f"Failed to get question: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to get question: {str(e)}"})

async def search_knowledge_base(query: str, claim_type: Optional[str] = None) -> str:
    """
    Naive knowledge base search over src/knowledge_base.json.
    Searches question texts and optionally filters by claim type.
    Returns a small list of matched entries.
    """
    try:
        normalized_query = (query or "").strip().lower()
        if not normalized_query:
            return json.dumps({"status": "error", "message": "Query text is required"})

        with open("src/knowledge_base.json", "r") as f:
            kb = json.load(f)

        results = []
        for item in kb.get("questions", []):
            item_claim_type = item.get("claimType")
            if claim_type and item_claim_type != claim_type:
                continue
            text = (item.get("questionText") or "").lower()
            field_name = (item.get("fieldName") or "").lower()
            if normalized_query in text or normalized_query in field_name:
                results.append({
                    "claimType": item_claim_type,
                    "fieldName": item.get("fieldName"),
                    "questionText": item.get("questionText")
                })
            if len(results) >= 5:
                break

        if not results:
            return json.dumps({
                "status": "not_found",
                "message": "No relevant entries found in knowledge base."
            })

        return json.dumps({
            "status": "success",
            "results": results
        })

    except FileNotFoundError:
        logger.warning("Knowledge base file not found for search")
        return json.dumps({
            "status": "error",
            "message": "Knowledge base file not found"
        })
    except Exception as e:
        logger.error(f"Failed to search knowledge base: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "message": f"Failed to search knowledge base: {str(e)}"})