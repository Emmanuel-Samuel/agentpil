# src/config.py
import os
from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    
    # Azure AI Foundry Configuration
    azure_ai_foundry_endpoint: str
    azure_ai_foundry_project_name: str
    azure_ai_foundry_api_key: str
    azure_ai_foundry_deployment_model_name: str = "gpt-4o-mini"
    azure_use_managed_identity: bool = False
    
    # API Configuration
    api_secret_key: Optional[str] = None
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Azure Function App (if used)
    azure_function_app_url: Optional[str] = None
    
    # Agent IDs (if using multiple agents)
    initial_intake_agent_id: Optional[str] = None
    main_orchestrator_agent_id: Optional[str] = None
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()

# Create settings instance
settings = get_settings()