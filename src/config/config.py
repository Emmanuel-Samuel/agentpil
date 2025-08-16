import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    COSMOS_DB_DATABASE_NAME: str = os.getenv("COSMOS_DB_DATABASE_NAME", "paininjurylawdb")
    COSMOS_DB_CONTAINER_NAME: str = os.getenv("COSMOS_DB_CONTAINER_NAME", "LegalClaimsdb")
    COSMOS_DB_URL: str = os.getenv("COSMOS_DB_URL", "https://paininjurylawdb.documents.azure.com:443/")
    COSMOS_DB_KEY: str = os.getenv("COSMOS_DB_KEY", "s3epLPKwlcfN8h0UhF2uNvGbQGULwmVuWsxEFhoo8EAa05mnlGWtiYlXXnZ7I3K6ybOas9q6lnFAACDbJMsmLg==")
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "2nX7eK2ETMq2TE5qKLTYxmQds8Jdde914AzCaHfcsBM=")
    REDIS_URL: str = os.getenv("REDIS_URL", "agentpil.redis.cache.windows.net")
    
settings = Settings()