import os
import asyncio
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.append(str(Path(__file__).parent))

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from services.poml_service import POMLService

# Load environment variables
load_dotenv()

# Get configuration from environment variables
project_endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
model_name = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME")

if not project_endpoint or not model_name:
    raise ValueError("Please set AZURE_AI_FOUNDRY_ENDPOINT and AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME in your .env file.")

# Initialize POMLService
poml_service = POMLService(prompts_directory="prompts")

async def deploy_agent(agent_name, poml_file, description, tools=None):
    print(f"--- Deploying {agent_name} ---")
    try:
        # Get agent instructions using POMLService
        instructions = poml_service.get_agent_instructions(agent_name=poml_file)

        # Initialize the client with DefaultAzureCredential
        agent_client = AgentsClient(endpoint=project_endpoint, credential=DefaultAzureCredential())

        # Deploy the agent
        if tools:
            # Create agent with tools
            agent = agent_client.create_agent(
                name=agent_name,
                instructions=instructions,
                description=description,
                model=model_name,
                tools=tools
            )
        else:
            # Create agent without tools
            agent = agent_client.create_agent(
                name=agent_name,
                instructions=instructions,
                description=description,
                model=model_name
            )

        print(f"\n--- {agent_name} Deployment Successful ---")
        print(f"Agent Name: {agent.name}")
        print(f"Agent ID: {agent.id}")
        return agent.id

    except Exception as e:
        print(f"\n--- {agent_name} Deployment Failed ---")
        print(f"An error occurred: {e}")
        raise

async def main():
    print("🚀 Starting Agent Deployment Process")
    print(f"Project: {os.getenv('AZURE_AI_FOUNDRY_PROJECT_NAME')}")
    print(f"Endpoint: {project_endpoint}")
    print("=" * 50)

    # Import the actual tool definitions from your tools service
    from services import tools as tools_service
    
    # Format tools properly for Azure AI Agents API
    portal_agent_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_claim_by_contact_info",
                "description": "Get claim details by providing either an email or a phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "The email address associated with the claim"
                        },
                        "phone": {
                            "type": "string",
                            "description": "The phone number associated with the claim"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function", 
            "function": {
                "name": "initiate_new_claim",
                "description": "Initiate a new claim for a user with the provided claim data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "The user ID initiating the claim"
                        },
                        "claim_data": {
                            "type": "object",
                            "description": "The claim data to initialize"
                        }
                    },
                    "required": ["user_id", "claim_data"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "transition_claim_type",
                "description": "Updates an existing claim with a new claim type.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {
                            "type": "string",
                            "description": "The ID of the claim to update"
                        },
                        "new_claim_type": {
                            "type": "string",
                            "description": "The new claim type to set"
                        }
                    },
                    "required": ["claim_id", "new_claim_type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_claim_data",
                "description": "Update the data for an existing claim.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {
                            "type": "string",
                            "description": "The ID of the claim to update"
                        },
                        "updates": {
                            "type": "object",
                            "description": "The updates to apply to the claim"
                        }
                    },
                    "required": ["claim_id", "updates"]
                }
            }
        }
    ]
    
    try:
        # Deploy Initial Intake Agent (no tools)
        initial_agent_id = await deploy_agent(
            agent_name="initial_intake_agent",
            poml_file="initial_agent",
            description="Handles initial client intake and basic queries."
        )
        print(f"Set INITIAL_INTAKE_AGENT_ID={initial_agent_id} in your .env file")

        # Deploy Portal Agent
        portal_agent_id = await deploy_agent(
            agent_name="portal_claim_agent",
            poml_file="portal_agent",
            description="Assists with portal-related tasks and client interactions.",
            tools=portal_agent_tools
        )
        print(f"Set PORTAL_AGENT_ID={portal_agent_id} in your .env file")

        print("\n✅ All agents deployed successfully!")
        print("\n📝 Next steps:")
        print("1. Add these environment variables to your .env file:")
        print(f"   INITIAL_INTAKE_AGENT_ID={initial_agent_id}")
        print(f"   PORTAL_AGENT_ID={portal_agent_id}")
        print("2. Restart your application to use the pre-deployed agents")

    except Exception as e:
        print("\n❌ Deployment process encountered errors.")
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())