import os
import asyncio
import logging
import os
import json
import requests
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import ConnectedAgentTool, MessageRole

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(levelname)s: %(message)s'
)

# Set third-party library log levels to WARNING to reduce noise
logging.getLogger('azure').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class FastAPILegalAgentDeployer:
    """Deploys Azure AI Foundry Agents with FastAPI OpenAPI tool integration for Legal Claims Processing"""
    
    def __init__(self):
        # Get configuration from environment variables
        self.project_endpoint = os.getenv("PROJECT_ENDPOINT") or os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
        model_deployment_name = os.getenv("MODEL_DEPLOYMENT_NAME") or os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME")
        self.fastapi_base_url = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
        
        if not self.project_endpoint:
            raise ValueError("Please set PROJECT_ENDPOINT (or AZURE_AI_FOUNDRY_ENDPOINT) in your .env file.")
        if not model_deployment_name:
            raise ValueError("Please set MODEL_DEPLOYMENT_NAME (or AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME) in your .env file.")
        
        # Ensure model_deployment_name is a string for type safety
        self.model_deployment_name: str = str(model_deployment_name)
        
        # Initialize the AI Project Client
        self.project_client = AIProjectClient(
            endpoint=self.project_endpoint,
            credential=DefaultAzureCredential(),
        )
        logger.info(f"AI Project Client initialized: {self.project_endpoint}")
        logger.info(f"FastAPI URL: {self.fastapi_base_url}")
        
        # Load OpenAPI schema for tool discovery
        self.openapi_schema = self._load_openapi_schema()
    
    def _load_openapi_schema(self) -> Optional[Dict[str, Any]]:
        """Load OpenAPI schema from FastAPI application or generate fallback"""
        try:
            response = requests.get(f"{self.fastapi_base_url}/openapi.json", timeout=10)
            response.raise_for_status()
            schema = response.json()
            logger.info(f"OpenAPI schema loaded: {len(schema.get('paths', {}))} endpoints")
            return schema
        except Exception as e:
            logger.warning(f"OpenAPI schema unavailable: {str(e)}")
            logger.info("Generating Azure-compatible OpenAPI schema")
            return self._generate_azure_openapi_schema()
    
    def _generate_azure_openapi_schema(self) -> Dict[str, Any]:
        """Generate Azure AI Foundry compatible OpenAPI 3.1.0 schema with complete definitions"""
        return {
            "name": "AI Legal Claims Assistant API",
            "openapi": "3.1.0",
            "info": {
                "title": "AI Legal Claims Assistant API",
                "description": "FastAPI application with Azure AI Foundry Connected Agents integration for legal claims processing. Provides tools for Azure AI Foundry agents to interact with PostgreSQL database for legal claims management.",
                "version": "2.0.0"
            },
            "servers": [
                {"url": self.fastapi_base_url}
            ],
            "auth": [],
            "paths": {
                "/tools/save_claim_data": {
                    "post": {
                        "description": "Save new claim data to PostgreSQL database after extracting information from user message",
                        "operationId": "save_claim_data",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "claim_data": {
                                                "type": "object",
                                                "description": "Complete claim information including type, description, dates, and other details",
                                                "properties": {
                                                    "claim_id": {
                                                        "type": "string",
                                                        "description": "Unique identifier for the claim"
                                                    },
                                                    "claim_type": {
                                                        "type": "string",
                                                        "description": "Type of claim (personal_injury, employment, etc.)"
                                                    },
                                                    "title": {
                                                        "type": "string",
                                                        "description": "Brief summary of the claim"
                                                    },
                                                    "description": {
                                                        "type": "string",
                                                        "description": "Detailed incident description"
                                                    },
                                                    "incident_date": {
                                                        "type": "string",
                                                        "description": "Date when incident occurred"
                                                    },
                                                    "estimated_value": {
                                                        "type": "number",
                                                        "description": "Estimated claim value"
                                                    },
                                                    "priority": {
                                                        "type": "string",
                                                        "description": "Priority level (low, medium, high)"
                                                    }
                                                },
                                                "required": ["claim_id", "claim_type", "title", "description"]
                                            },
                                            "user_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the user creating the claim"
                                            }
                                        },
                                        "required": ["claim_data", "user_id"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "success": {"type": "boolean"},
                                                "message": {"type": "string"},
                                                "claim_id": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/get_user_claims": {
                    "post": {
                        "description": "Retrieve user's existing claims from PostgreSQL database",
                        "operationId": "get_user_claims",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "user_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the user"
                                            },
                                            "status": {
                                                "type": "string",
                                                "description": "Optional status filter (draft, submitted, approved, etc.)"
                                            }
                                        },
                                        "required": ["user_id"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "claim_id": {"type": "string"},
                                                    "claim_type": {"type": "string"},
                                                    "title": {"type": "string"},
                                                    "status": {"type": "string"},
                                                    "created_at": {"type": "string"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/get_claim": {
                    "post": {
                        "description": "Retrieve detailed information about a specific claim to identify missing fields",
                        "operationId": "get_claim",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "claim_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the claim to retrieve"
                                            },
                                            "user_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the user"
                                            }
                                        },
                                        "required": ["claim_id"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "claim_id": {"type": "string"},
                                                "claim_type": {"type": "string"},
                                                "title": {"type": "string"},
                                                "description": {"type": "string"},
                                                "incident_date": {"type": "string"},
                                                "estimated_value": {"type": "number"},
                                                "priority": {"type": "string"},
                                                "status": {"type": "string"},
                                                "created_at": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/update_claim_data": {
                    "post": {
                        "description": "Update existing claim with new information from user message",
                        "operationId": "update_claim_data",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "claim_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the claim to update"
                                            },
                                            "updates": {
                                                "type": "object",
                                                "description": "Fields to update with their new values"
                                            }
                                        },
                                        "required": ["claim_id", "updates"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "success": {"type": "boolean"},
                                                "message": {"type": "string"},
                                                "updated_fields": {"type": "array", "items": {"type": "string"}}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/search_legal_database": {
                    "post": {
                        "description": "Search legal knowledge database using full-text search",
                        "operationId": "search_legal_database",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "query": {
                                                "type": "string",
                                                "description": "Search query for legal knowledge"
                                            },
                                            "user_id": {
                                                "type": "string",
                                                "description": "User ID for activity logging"
                                            },
                                            "category": {
                                                "type": "string",
                                                "description": "Optional category filter (law, precedent, procedure)"
                                            },
                                            "jurisdiction": {
                                                "type": "string",
                                                "description": "Optional jurisdiction filter (federal, state)"
                                            }
                                        },
                                        "required": ["query", "user_id"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "title": {"type": "string"},
                                                    "content": {"type": "string"},
                                                    "category": {"type": "string"},
                                                    "jurisdiction": {"type": "string"},
                                                    "relevance_score": {"type": "number"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/get_user_profile": {
                    "post": {
                        "description": "Retrieve user profile information from PostgreSQL database",
                        "operationId": "get_user_profile",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "user_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the user"
                                            }
                                        },
                                        "required": ["user_id"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "user_id": {"type": "string"},
                                                "full_name": {"type": "string"},
                                                "email": {"type": "string"},
                                                "phone": {"type": "string"},
                                                "address": {"type": "object"},
                                                "preferences": {"type": "object"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/tools/update_user_profile": {
                    "post": {
                        "description": "Update user profile information in PostgreSQL database",
                        "operationId": "update_user_profile",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "user_id": {
                                                "type": "string",
                                                "description": "Unique identifier for the user"
                                            },
                                            "updates": {
                                                "type": "object",
                                                "description": "Profile fields to update"
                                            }
                                        },
                                        "required": ["user_id", "updates"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "success": {"type": "boolean"},
                                                "message": {"type": "string"},
                                                "updated_profile": {"type": "object"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "ClaimData": {
                        "type": "object",
                        "properties": {
                            "claim_id": {"type": "string"},
                            "claim_type": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "incident_date": {"type": "string"},
                            "estimated_value": {"type": "number"},
                            "priority": {"type": "string"}
                        }
                    },
                    "UserProfile": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "full_name": {"type": "string"},
                            "email": {"type": "string"},
                            "phone": {"type": "string"},
                            "address": {"type": "object"},
                            "preferences": {"type": "object"}
                        }
                    }
                }
            }
        }
    
    def export_azure_openapi_schema(self, file_path: Optional[str] = None) -> str:
        """Export the Azure-compatible OpenAPI schema to a JSON file"""
        if file_path is None:
            file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "azure_openapi_schema.json")
        
        schema = self.openapi_schema or self._generate_azure_openapi_schema()
        
        # Ensure Azure Portal required fields are present
        if "name" not in schema:
            schema["name"] = schema.get("info", {}).get("title", "AI Legal Claims Assistant API")
        
        # Update server URL to use current fastapi_base_url
        if "servers" in schema:
            schema["servers"] = [{"url": self.fastapi_base_url}]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Azure OpenAPI schema exported to: {file_path}")
        return file_path
    
    def create_fastapi_http_tool(self, endpoint_path: str, fallback_name: Optional[str] = None, fallback_description: Optional[str] = None, fallback_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create an OpenAPI tool that Azure AI Foundry can call via HTTP"""
        base_url = self.fastapi_base_url.rstrip('/')
        full_url = f"{base_url}{endpoint_path}"
        
        if self.openapi_schema and endpoint_path in self.openapi_schema.get('paths', {}):
            # Extract tool definition from OpenAPI schema
            endpoint_info = self.openapi_schema['paths'][endpoint_path]
            post_info = endpoint_info.get('post', {})
            
            # Get tool name from operationId or endpoint path
            tool_name = post_info.get('operationId') or endpoint_path.split('/')[-1]
            
            # Get description
            description = post_info.get('description', post_info.get('summary', fallback_description or f"Call {tool_name} endpoint"))
            
            # Create OpenAPI tool definition that Azure AI Foundry can call via HTTP
            return {
                "type": "openapi",
                "openapi": {
                    "openapi": "3.1.0",
                    "info": {
                        "title": f"{tool_name} Tool",
                        "version": "1.0.0"
                    },
                    "servers": [
                        {"url": base_url}
                    ],
                    "paths": {
                        endpoint_path: {
                            "post": {
                                "operationId": tool_name,
                                "summary": description,
                                "description": description,
                                "requestBody": post_info.get('requestBody', {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": fallback_parameters or {"type": "object"}
                                        }
                                    }
                                }),
                                "responses": post_info.get('responses', {
                                    "200": {
                                        "description": "Success",
                                        "content": {
                                            "application/json": {
                                                "schema": {"type": "object"}
                                            }
                                        }
                                    }
                                })
                            }
                        }
                    }
                }
            }
        else:
            # Use fallback OpenAPI tool definition
            tool_name = fallback_name or endpoint_path.split('/')[-1]
            description = fallback_description or f"Call {endpoint_path} endpoint"
            parameters = fallback_parameters or {"type": "object", "properties": {}, "required": []}
            
            return {
                "type": "openapi",
                "openapi": {
                    "openapi": "3.1.0",
                    "info": {
                        "title": f"{tool_name} Tool",
                        "version": "1.0.0"
                    },
                    "servers": [
                        {"url": base_url}
                    ],
                    "paths": {
                        endpoint_path: {
                            "post": {
                                "operationId": tool_name,
                                "summary": description,
                                "description": description,
                                "requestBody": {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": parameters
                                        }
                                    }
                                },
                                "responses": {
                                    "200": {
                                        "description": "Success",
                                        "content": {
                                            "application/json": {
                                                "schema": {"type": "object"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

    def get_claim_creation_tools(self) -> List[Dict[str, Any]]:
        """Get HTTP tools for claim creation agent (callable from Azure AI Foundry portal)"""
        return [
            self.create_fastapi_http_tool(
                "/tools/save_claim_data",
                fallback_name="save_claim_data",
                fallback_description="Save new claim data to database after extracting information from user message",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "claim_data": {
                            "type": "object", 
                            "description": "Complete claim information including type, description, dates, and other details"
                        },
                        "user_id": {
                            "type": "string", 
                            "description": "Unique identifier for the user creating the claim"
                        }
                    },
                    "required": ["claim_data", "user_id"]
                }
            )
        ]
    
    def get_claim_continuation_tools(self) -> List[Dict[str, Any]]:
        """Get HTTP tools for claim continuation agent (callable from Azure AI Foundry portal)"""
        return [
            self.create_fastapi_http_tool(
                "/tools/get_user_claims",
                fallback_name="get_user_claims",
                fallback_description="Retrieve user's existing claims from database",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Unique identifier for the user"},
                        "status": {"type": "string", "description": "Optional status filter for claims"}
                    },
                    "required": ["user_id"]
                }
            ),
            self.create_fastapi_http_tool(
                "/tools/get_claim",
                fallback_name="get_claim",
                fallback_description="Retrieve detailed information about a specific claim to identify missing fields",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "description": "Unique identifier for the claim to retrieve"}
                    },
                    "required": ["claim_id"]
                }
            ),
            self.create_fastapi_http_tool(
                "/tools/update_claim_data",
                fallback_name="update_claim_data",
                fallback_description="Update existing claim with new information from user message",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "description": "Unique identifier for the claim to update"},
                        "updates": {"type": "object", "description": "Fields to update with their new values"}
                    },
                    "required": ["claim_id", "updates"]
                }
            )
        ]
    
    def get_legal_knowledge_tools(self) -> List[Dict[str, Any]]:
        """Get HTTP tools for legal knowledge agent (callable from Azure AI Foundry portal)"""
        return [
            self.create_fastapi_http_tool(
                "/tools/search_legal_database",
                fallback_name="search_legal_database",
                fallback_description="Search legal knowledge database using full-text search",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for legal knowledge"},
                        "user_id": {"type": "string", "description": "User ID for activity logging"},
                        "category": {"type": "string", "description": "Optional category filter"},
                        "jurisdiction": {"type": "string", "description": "Optional jurisdiction filter"}
                    },
                    "required": ["query", "user_id"]
                }
            )
        ]
    
    def get_user_profile_tools(self) -> List[Dict[str, Any]]:
        """Get HTTP tools for user profile agent (callable from Azure AI Foundry portal)"""
        return [
            self.create_fastapi_http_tool(
                "/tools/get_user_profile",
                fallback_name="get_user_profile",
                fallback_description="Retrieve user profile information from database",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Unique identifier for the user"}
                    },
                    "required": ["user_id"]
                }
            ),
            self.create_fastapi_http_tool(
                "/tools/update_user_profile",
                fallback_name="update_user_profile",
                fallback_description="Update user profile information in database",
                fallback_parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Unique identifier for the user"},
                        "updates": {"type": "object", "description": "Profile fields to update"}
                    },
                    "required": ["user_id", "updates"]
                }
            )
        ]
    
    async def deploy_claim_creation_agent(self) -> str:
        """Deploy the claim creation agent with HTTP tools for portal integration"""
        logger.info("--- Deploying Claim Creation Agent with HTTP Tools ---")
        
        tools = self.get_claim_creation_tools()
        
        agent = self.project_client.agents.create_agent(
            model=self.model_deployment_name,
            name="claim_creation_agent",
            instructions="""You are a Claim Creation Agent for a personal injury law firm.
            Your role is to help users create new claims by extracting relevant information from their descriptions.
            
            **CRITICAL: User Context Handling**
            - The user_id is provided by the orchestrator agent in the conversation context
            - ALWAYS extract and use this user_id for ALL tool calls - NEVER ask the user for their ID
            - When the orchestrator routes a request to you, the user_id is already included in the context
            - Users should never need to provide their ID since you receive it from the orchestrator
            
            **Your HTTP Tools:**
            - save_claim_data: HTTP POST to FastAPI to save extracted claim information to PostgreSQL database
            
            **Workflow:**
            1. Listen carefully to the user's incident description
            2. Extract ALL relevant claim information including:
               - claim_type (personal_injury, employment, contract, etc.)
               - title (brief summary)
               - description (detailed incident description)
               - incident_date (when it happened)
               - estimated_value (if mentioned)
               - priority (based on severity)
            3. Extract the user_id from the conversation context (provided by orchestrator)
            4. Use save_claim_data tool to store the claim in the database via HTTP
            5. Provide the user with their claim ID and next steps
            
            **Important Notes:**
            - Always be empathetic and professional when dealing with injury claims
            - Extract as much detail as possible from the user's description
            - Generate a unique claim_id in the format "claim_[random12chars]"
            - Set appropriate claim_type based on the incident
            - Provide clear guidance on next steps
            - All tool calls go through HTTP to the FastAPI application
            - NEVER ask "What is your user ID?" - you already have it from the orchestrator context
            """,
            tools=tools
        )
        
        logger.info(f"Claim Creation Agent created: {agent.id}")
        return agent.id

    async def deploy_claim_continuation_agent(self) -> str:
        """Deploy the claim continuation agent with HTTP tools for portal integration"""
        logger.info("--- Deploying Claim Continuation Agent with HTTP Tools ---")
        
        tools = self.get_claim_continuation_tools()
        
        agent = self.project_client.agents.create_agent(
            model=self.model_deployment_name,
            name="claim_continuation_agent",
            instructions="""You are a Claim Continuation Agent for a personal injury law firm.
            Your role is to help users update and continue existing claims with new information.
            
            **CRITICAL: User Context Handling**
            - The user_id is provided by the orchestrator agent in the conversation context
            - ALWAYS extract and use this user_id for ALL tool calls - NEVER ask the user for their ID
            - When the orchestrator routes a request to you, the user_id is already included in the context
            - Users should never need to provide their ID since you receive it from the orchestrator
            
            **Your HTTP Tools:**
            - get_user_claims: HTTP GET to FastAPI to retrieve user's existing claims from PostgreSQL database
            - get_claim: HTTP GET to FastAPI to retrieve detailed information about a specific claim to identify missing fields
            - update_claim_data: HTTP POST to FastAPI to update existing claim with new information
            
            **Workflow:**
            1. When a user wants to update a claim:
               a. Extract the user_id from the conversation context (provided by orchestrator)
               b. Use get_user_claims to retrieve their existing claims via HTTP
               c. Help them identify which claim to update
               d. Once a claim is selected, use get_claim to fetch detailed information about that claim
               e. Analyze the claim details to identify what information is missing
               f. Guide the conversation to collect the missing information without displaying the full claim details to the user
               g. Extract new information from their message
               h. Use update_claim_data to update the claim via HTTP
            
            2. When providing claim updates:
               - Always confirm which claim is being updated
               - Summarize the changes being made
               - Provide updated status and next steps
            
            **Important Notes:**
            - Always maintain continuity and context from previous interactions
            - Be thorough in extracting updates from user messages
            - Confirm changes with the user before applying them
            - Provide clear guidance on claim progression
            - All tool calls go through HTTP to the FastAPI application
            - NEVER ask "What is your user ID?" - you already have it from the orchestrator context
            - When using get_claim, do NOT display the full claim details to the user, instead use the information to guide the conversation
            """,
            tools=tools
        )
        
        logger.info(f"Claim Continuation Agent created: {agent.id}")
        return agent.id

    async def deploy_legal_knowledge_agent(self) -> str:
        """Deploy the legal knowledge agent with HTTP tools for portal integration"""
        logger.info("--- Deploying Legal Knowledge Agent with HTTP Tools ---")
        
        tools = self.get_legal_knowledge_tools()
        
        agent = self.project_client.agents.create_agent(
            model=self.model_deployment_name,
            name="legal_knowledge_agent",
            instructions="""You are a Legal Knowledge Agent for a personal injury law firm.
            Your role is to provide legal information and guidance to users by searching a comprehensive legal database.
            
            **CRITICAL: User Context Handling**
            - The user_id is provided by the orchestrator agent in the conversation context
            - ALWAYS extract and use this user_id for ALL tool calls - NEVER ask the user for their ID
            - When the orchestrator routes a request to you, the user_id is already included in the context
            - Users should never need to provide their ID since you receive it from the orchestrator
            
            **Your HTTP Tools:**
            - search_legal_database: HTTP POST to FastAPI to search PostgreSQL legal knowledge base with full-text search
            
            **Workflow:**
            1. When users ask legal questions:
               a. Analyze their question to extract key legal concepts
               b. Extract the user_id from the conversation context (provided by orchestrator)
               c. Use search_legal_database with appropriate query terms via HTTP
               d. Optionally filter by category and jurisdiction
               e. Provide clear, educational answers based on results
            
            **Search Categories:**
            - law: Statutes and regulations
            - precedent: Case law and court decisions
            - procedure: Legal processes and requirements
            - form: Legal documents and templates
            
            **Important Guidelines:**
            - Always provide clear, educational answers
            - Include disclaimers about legal advice vs. information
            - Cite sources when possible
            - Recommend consulting with an attorney for specific cases
            - Use plain language to explain complex legal concepts
            - All tool calls go through HTTP to the FastAPI application
            - NEVER ask "What is your user ID?" - you already have it from the orchestrator context
            
            **Response Format:**
            Always end responses with: "This is general information only and not legal advice. Consult with a qualified attorney for your specific situation."
            """,
            tools=tools
        )
        
        logger.info(f"Legal Knowledge Agent created: {agent.id}")
        return agent.id

    async def deploy_user_profile_agent(self) -> str:
        """Deploy the user profile agent with HTTP tools for portal integration"""
        logger.info("--- Deploying User Profile Agent with HTTP Tools ---")
        
        tools = self.get_user_profile_tools()
        
        agent = self.project_client.agents.create_agent(
            model=self.model_deployment_name,
            name="user_profile_agent",
            instructions="""You are a User Profile Agent for a personal injury law firm.
            Your role is to help users manage their profile information for better service personalization.
            
            **CRITICAL: User Context Handling**
            - The user_id is provided by the orchestrator agent in the conversation context
            - ALWAYS extract and use this user_id for ALL tool calls - NEVER ask the user for their ID
            - When the orchestrator routes a request to you, the user_id is already included in the context
            - Users should never need to provide their ID since you receive it from the orchestrator
            
            **Your HTTP Tools:**
            - get_user_profile: HTTP POST to FastAPI to retrieve user profile from PostgreSQL database
            - update_user_profile: HTTP POST to FastAPI to update user profile information
            
            **Profile Information Managed:**
            - full_name: User's complete legal name
            - email: Primary contact email
            - phone: Primary contact phone number
            - address: Complete address information (stored as JSON)
            - preferences: User communication and service preferences
            
            **Workflow:**
            1. When users want to view their profile:
               - Extract the user_id from the conversation context (provided by orchestrator)
               - Use get_user_profile to retrieve current information via HTTP
               - Present information clearly and ask what they'd like to update
            
            2. When users want to update their profile:
               - Extract the specific fields they want to change
               - Use update_user_profile to save changes via HTTP
               - Confirm updates and summarize changes made
            
            **Important Guidelines:**
            - Always prioritize data privacy and accuracy
            - Confirm sensitive information changes with the user
            - Validate email and phone formats when provided
            - Maintain professional communication standards
            - Explain how profile information is used to improve service
            - All tool calls go through HTTP to the FastAPI application
            - NEVER ask "What is your user ID?" - you already have it from the orchestrator context
            """,
            tools=tools
        )
        
        logger.info(f"User Profile Agent created: {agent.id}")
        return agent.id

    async def deploy_orchestrator_agent(self, deployed_agents: Dict[str, str]) -> str:
        """Deploy the orchestrator agent with Connected Agents architecture"""
        logger.info("--- Deploying Orchestrator Agent with Connected Agents Architecture ---")
        
        # Create Connected Agent tools for each specialist agent
        connected_agents = [
            ConnectedAgentTool(
                id=deployed_agents['CLAIM_CREATION_AGENT_ID'],
                name="claim_creation_agent", 
                description="Creates new legal claims from user descriptions and incident reports"
            ),
            ConnectedAgentTool(
                id=deployed_agents['CLAIM_CONTINUATION_AGENT_ID'],
                name="claim_continuation_agent",
                description="Updates and manages existing claims with new information"
            ),
            ConnectedAgentTool(
                id=deployed_agents['LEGAL_KNOWLEDGE_AGENT_ID'],
                name="legal_knowledge_agent", 
                description="Provides legal research, statutes, precedents, and guidance"
            ),
            ConnectedAgentTool(
                id=deployed_agents['USER_PROFILE_AGENT_ID'],
                name="user_profile_agent",
                description="Manages user profile information and preferences"
            )
        ]
        
        # Get tools from connected agents
        tools = []
        for connected_agent in connected_agents:
            tools.extend(connected_agent.definitions)
        
        agent = self.project_client.agents.create_agent(
            model=self.model_deployment_name,
            name="orchestrator_agent",
            instructions="""You are the Main Orchestrator Agent for a personal injury law firm's AI system.
            Your role is to intelligently route user requests to specialized Connected Agents based on natural language understanding.
            
            **CRITICAL: User Context Handling**
            - The user_id is automatically provided in the conversation context as "User ID: {user_id}"
            - ALWAYS extract and use this user_id for ALL tool calls - NEVER ask the user for their ID
            - When checking claims, profiles, or any user-specific data, use the provided user_id automatically
            - The user should never need to provide their ID since you already have it from the context
            
            **Your Connected Agents:**
            - claim_creation_agent: For new claims, incident descriptions, and initial intake
            - claim_continuation_agent: For updating existing claims, status checks, and modifications
            - legal_knowledge_agent: For legal questions, research, statutes, and precedents
            - user_profile_agent: For profile management, contact updates, and preferences
            
            **Azure AI Foundry Routing:**
            Azure AI Foundry handles intelligent routing automatically based on user intent.
            You should use natural language understanding to determine which agent can best help.
            
            **Routing Guidelines:**
            - **New Incidents/Claims**: "I was in an accident" → claim_creation_agent
            - **Existing Claims**: "Update my claim" or "Check claim status" → claim_continuation_agent  
            - **Legal Questions**: "What are my rights?" or "Statute of limitations" → legal_knowledge_agent
            - **Profile Updates**: "Change my address" or "Update phone" → user_profile_agent
            - **General Help**: Provide overview and ask clarifying questions
            
            **Tool Usage Guidelines:**
            - When user asks about "my claims" → automatically use claim_continuation_agent with the user_id from context
            - When user asks about "my profile" → automatically use user_profile_agent with the user_id from context
            - When creating new claims → automatically use claim_creation_agent with the user_id from context
            - NEVER ask for user_id - it's always available in the conversation context
            
            **Communication Style:**
            - Be empathetic and professional, especially with injury-related matters
            - Provide clear guidance on what will happen next
            - Explain which specialist will help them and why
            - Ask clarifying questions when intent is unclear, but NEVER ask for user identification
            
            **Important Notes:**
            - Trust Azure AI Foundry's native routing capabilities
            - Focus on understanding user intent rather than implementing custom logic
            - Each connected agent has specialized HTTP tools for database operations via FastAPI
            - Ensure smooth handoffs between agents when multiple steps are needed
            - All tool integrations work through Azure AI Foundry Portal
            - REMEMBER: You already know who the user is - use their user_id from context automatically
            
            Remember: You are the intelligent front door to our legal AI system. Your job is to ensure every user 
            gets connected to the right specialist agent for the best possible assistance without asking for information you already have.
            """,
            tools=tools
        )
        
        logger.info(f"Orchestrator Agent created with {len(connected_agents)} Connected Agents: {agent.id}")
        return agent.id
        



    async def deploy_all_agents(self) -> Dict[str, str]:
        """Deploy all agents for the legal claim management system with FastAPI integration"""
        logger.info("Starting FastAPI Legal Agents Deployment Process")
        logger.info(f"Project Endpoint: {self.project_endpoint}")
        logger.info(f"Model: {self.model_deployment_name}")
        logger.info(f"FastAPI Base URL: {self.fastapi_base_url}")
        logger.info("=" * 80)
        
        deployed_agents = {}
        
        try:
            # Export OpenAPI schema for manual Azure Portal configuration
            schema_file_path = self.export_azure_openapi_schema()
            logger.info(f"OpenAPI schema exported for Azure Portal: {schema_file_path}")
            
            # Validate FastAPI connection and OpenAPI schema
            if self.openapi_schema:
                tool_endpoints = len([path for path in self.openapi_schema.get('paths', {}) if path.startswith('/tools/')])
                logger.info(f"FastAPI connected with {tool_endpoints} tool endpoints available")
                
                # Log each available tool endpoint
                for path in sorted(self.openapi_schema.get('paths', {})):
                    if path.startswith('/tools/'):
                        endpoint_info = self.openapi_schema['paths'][path].get('post', {})
                        operation_id = endpoint_info.get('operationId', path.split('/')[-1])
                        description = endpoint_info.get('description', 'No description')
                        logger.info(f"   • {operation_id}: {description}")
            else:
                logger.warning("FastAPI OpenAPI schema not available - using fallback tool definitions")
            
            # Deploy individual specialist agents first
            logger.info("\nDeploying Specialist Agents with HTTP Tools...")
            deployed_agents['CLAIM_CREATION_AGENT_ID'] = await self.deploy_claim_creation_agent()
            deployed_agents['CLAIM_CONTINUATION_AGENT_ID'] = await self.deploy_claim_continuation_agent()
            deployed_agents['LEGAL_KNOWLEDGE_AGENT_ID'] = await self.deploy_legal_knowledge_agent()
            deployed_agents['USER_PROFILE_AGENT_ID'] = await self.deploy_user_profile_agent()
            
            # Deploy orchestrator agent with Connected Agents
            logger.info("\nDeploying Orchestrator Agent with Connected Agents Architecture...")
            deployed_agents['MAIN_ORCHESTRATOR_AGENT_ID'] = await self.deploy_orchestrator_agent(deployed_agents)
            
            logger.info("\n" + "="*80)
            logger.info("FASTAPI AGENTS DEPLOYMENT COMPLETE!")
            logger.info("="*80)
            
            logger.info("\nEnvironment Variables - Add these to your .env file:")
            for env_var, agent_id in deployed_agents.items():
                logger.info(f"   {env_var}={agent_id}")
            
            logger.info(f"\nArchitecture Summary:")
            logger.info(f"   Specialist Agents: 4 deployed (Claim Creation, Continuation, Legal Knowledge, User Profile)")
            logger.info(f"   Orchestrator Agent: 1 deployed (with Connected Agents architecture)")
            logger.info(f"   HTTP Tools: Each agent equipped with FastAPI endpoint tools")
            logger.info(f"   OpenAPI Schema: Exported to {schema_file_path}")
            logger.info(f"   PostgreSQL Database: Comprehensive schema with full-text search")
            logger.info(f"   Total Agents: 5 deployed with Connected Agents architecture")
            
            logger.info(f"\nWorkflow Summary:")
            logger.info(f"   User Message → Azure AI Foundry Portal → Orchestrator Agent")
            logger.info(f"   Orchestrator → Natural Language Routing → Connected Specialist Agent")
            logger.info(f"   Specialist Agent → HTTP Tools → FastAPI Endpoints → PostgreSQL Database")
            logger.info(f"   Database Response → Agent Processing → Portal Response")
            logger.info(f"   Architecture: Azure Connected Agents with HTTP tool integration")
            
            logger.info(f"\nAvailable FastAPI Tools:")
            if self.openapi_schema:
                tool_paths = [path for path in self.openapi_schema.get('paths', {}) if path.startswith('/tools/')]
                for path in sorted(tool_paths):
                    endpoint_info = self.openapi_schema['paths'][path].get('post', {})
                    operation_id = endpoint_info.get('operationId', path.split('/')[-1])
                    summary = endpoint_info.get('description', operation_id)
                    logger.info(f"   • {operation_id} ({path}) - {summary}")
            
            logger.info(f"\nNext Steps:")
            logger.info(f"   1. Add the environment variables above to your .env file")
            logger.info(f"   2. Ensure DATABASE_URL is configured for PostgreSQL")
            logger.info(f"   3. Start your FastAPI server: python -m src.app")
            logger.info(f"   4. Test via Azure AI Foundry Portal or /chat/portal endpoint")
            logger.info(f"   5. View OpenAPI docs: {self.fastapi_base_url}/docs")
            logger.info(f"   6. Use Azure AI Foundry Portal for natural language interactions")
            logger.info(f"   7. Import OpenAPI schema from {schema_file_path} to Azure Portal for manual tool setup")
            
            logger.info("\n" + "="*80)
            logger.info("Connected Agents deployed! Ready for Azure AI Foundry Portal integration!")
            logger.info("="*80)
            
            return deployed_agents
            
        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")
            
            # Cleanup any partially created agents
            logger.info("Cleaning up partially deployed agents...")
            for agent_id in deployed_agents.values():
                try:
                    self.project_client.agents.delete_agent(agent_id)
                    logger.info(f"Deleted agent: {agent_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not delete agent {agent_id}: {cleanup_error}")
            
            raise

async def main():
    """Main deployment function for FastAPI Legal Agents"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy Azure AI Foundry Agents with FastAPI integration for Legal Claims Processing")
    parser.add_argument("--cleanup", action="store_true", help="Clean up existing agents before deployment")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for failed deployments")
    parser.add_argument("--fastapi-url", type=str, help="FastAPI base URL (overrides FASTAPI_BASE_URL env var)")
    
    args = parser.parse_args()
    
    # Override FastAPI URL if provided
    if args.fastapi_url:
        os.environ["FASTAPI_BASE_URL"] = args.fastapi_url
    
    # Validate required environment variables
    required_vars = [
        ("PROJECT_ENDPOINT", "AZURE_AI_FOUNDRY_ENDPOINT"),
        ("MODEL_DEPLOYMENT_NAME", "AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME")
    ]
    
    missing_vars = []
    for primary, fallback in required_vars:
        if not os.getenv(primary) and not os.getenv(fallback):
            missing_vars.append(f"{primary} (or {fallback})")
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    # Check FastAPI availability
    fastapi_url = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
    try:
        response = requests.get(f"{fastapi_url}/health", timeout=5)
        logger.info(f"FastAPI health check passed: {fastapi_url}")
    except Exception as e:
        logger.warning(f"FastAPI not reachable at {fastapi_url}: {str(e)}")
        logger.warning("Agents will be deployed with fallback tool definitions")
    
    # Validate Azure credentials
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://management.azure.com/.default")
        logger.info("Azure credentials validated successfully")
    except Exception as e:
        logger.error(f"Azure credential validation failed: {str(e)}")
        logger.info("Please run 'az login' or check your Azure credentials")
        return
    
    # Deploy with retry logic
    for attempt in range(args.retry_attempts):
        try:
            logger.info(f"\nDeployment attempt {attempt + 1}/{args.retry_attempts}")
            deployer = FastAPILegalAgentDeployer()
            
            # Deploy all agents
            deployed_agents = await deployer.deploy_all_agents()
                
            logger.info("\nDeployment completed successfully!")
            return deployed_agents
            
        except Exception as e:
            if attempt < args.retry_attempts - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Deployment attempt {attempt + 1} failed: {str(e)}")
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Deployment failed after {args.retry_attempts} attempts: {str(e)}")
                raise

if __name__ == "__main__":
    asyncio.run(main())