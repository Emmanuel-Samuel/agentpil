import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    COSMOS_DB_DATABASE_NAME = os.getenv("COSMOS_DB_DATABASE_NAME")
    COSMOS_DB_CONTAINER_NAME = os.getenv("COSMOS_DB_CONTAINER_NAME")
    COSMOS_DB_URL = os.getenv("COSMOS_DB_URL")
    COSMOS_DB_KEY = os.getenv("COSMOS_DB_KEY")
    
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_USE_SSL = os.getenv("REDIS_USE_SSL", "true").lower() == "true"
    
    # Redis caching settings
    REDIS_HISTORY_TTL_HOURS = int(os.getenv("REDIS_HISTORY_TTL_HOURS", "24"))
    REDIS_MAX_HISTORY_LENGTH = int(os.getenv("REDIS_MAX_HISTORY_LENGTH", "10"))
    
    AZURE_AI_FOUNDRY_ENDPOINT = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME")
    
    AZURE_AI_FOUNDRY_API_KEY = os.getenv("AZURE_AI_FOUNDRY_API_KEY")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT = os.getenv("ENVIRONMENT")
    PROMPTS_DIRECTORY = os.getenv("PROMPTS_DIRECTORY")
    
    INITIAL_INTAKE_AGENT_ID = os.getenv("INITIAL_INTAKE_AGENT_ID")
    PORTAL_AGENT_ID = os.getenv("PORTAL_AGENT_ID")
    
    def __init__(self):
        """Validate required settings on initialization."""
        self._validate_settings()
    
    def _validate_settings(self):
        """Validate that required environment variables are set."""
        # Check Azure AI Foundry configuration
        if not self.AZURE_AI_FOUNDRY_ENDPOINT:
            raise ValueError("AZURE_AI_FOUNDRY_ENDPOINT is required")
        if not self.AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME:
            raise ValueError("AZURE_AI_FOUNDRY_DEPLOYMENT_MODEL_NAME is required")
        
        # Check Redis configuration
        if not self.REDIS_HOST:
            raise ValueError("REDIS_HOST is required")
        if not self.REDIS_PASSWORD:
            raise ValueError("REDIS_PASSWORD is required")
    
    @property
    def REDIS_URL(self) -> str:
        """Get Redis connection URL."""
        return f"{self.REDIS_HOST}:{self.REDIS_PORT}"
    
    @property
    def REDIS_CONNECTION_STRING(self) -> str:
        """Get Redis connection string for redis-py."""
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_URL}"

# Create a global settings instance
settings = Settings()
