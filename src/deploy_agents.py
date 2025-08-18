import os
import asyncio
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

        # Deploy the agent (create agent)
        agent = agent_client.create_agent(
            name=agent_name,
            instructions=instructions,
            description=description,
            model=model_name,
            tools=tools
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

    # Manually define tools for the Portal Agent
    portal_agent_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_claim_by_contact_info",
                "description": "Get claim details by providing either an email or a phone number",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "Client's email address"},
                        "phone": {"type": "string", "description": "Client's phone number"}
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "initiate_new_claim",
                "description": "Initiate a new claim for a user with the provided claim data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Unique identifier for the user"},
                        "claim_data": {"type": "object", "description": "Initial claim data including claim type"}
                    },
                    "required": ["user_id", "claim_data"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "transition_claim_type",
                "description": "Transition an existing claim to a new type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "description": "Unique identifier for the claim"},
                        "new_claim_type": {"type": "string", "description": "The new claim type to transition to"}
                    },
                    "required": ["claim_id", "new_claim_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_claim_data",
                "description": "Update the data for an existing claim",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "description": "Unique identifier for the claim"},
                        "updates": {"type": "object", "description": "Data fields to be updated"}
                    },
                    "required": ["claim_id", "updates"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_question_by_fieldname",
                "description": "Get the appropriate question text for a specific field based on claim type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field_name": {"type": "string", "description": "The name of the field needing information"},
                        "claim_type": {"type": "string", "description": "The type of claim being processed"}
                    },
                    "required": ["field_name", "claim_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Search the Azure Search knowledge base for relevant information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for the knowledge base"},
                        "claim_type": {"type": "string", "description": "Filter by specific claim type"}
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    try:
        # Deploy Initial Intake Agent (no tools)
        initial_agent_id = await deploy_agent(
            agent_name="initial_intake_agent",
            poml_file="initial_agent",
            description="Handles initial client intake and basic queries."
        )
        os.environ["INITIAL_INTAKE_AGENT_ID"] = initial_agent_id

        # Deploy Portal Agent
        portal_agent_id = await deploy_agent(
            agent_name="portal_claim_agent",
            poml_file="portal_agent",
            description="Assists with portal-related tasks and client interactions.",
            tools=portal_agent_tools
        )
        os.environ["PORTAL_AGENT_ID"] = portal_agent_id

        print("\nAll agents deployed successfully!")

    except Exception as e:
        print("\nDeployment process encountered errors.")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
