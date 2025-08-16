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
poml_service = POMLService(prompts_directory="src/prompts")

async def deploy_agent(agent_name, poml_file, description):
    print(f"--- Deploying {agent_name} ---")
    try:
        # Get agent instructions using POMLService
        instructions = poml_service.get_agent_instructions(agent_name=poml_file)

        # Initialize the client with DefaultAzureCredential
        agent_client = AgentsClient(endpoint=project_endpoint, credential=DefaultAzureCredential())

        # Deploy the agent
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

    try:
        # Deploy Initial Intake Agent
        initial_agent_id = await deploy_agent(
            agent_name="InitialIntakeAgent",
            poml_file="initial_agent",
            description="Handles initial client intake and basic queries."
        )
        os.environ["INITIAL_INTAKE_AGENT_ID"] = initial_agent_id

        # Deploy Portal Agent
        portal_agent_id = await deploy_agent(
            agent_name="PortalAgent",
            poml_file="portal_agent",
            description="Assists with portal-related tasks and client interactions."
        )
        os.environ["PORTAL_AGENT_ID"] = portal_agent_id

        print("\nAll agents deployed successfully!")

    except Exception as e:
        print("\nDeployment process encountered errors.")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())