"""
Startup script to ensure Prisma client is available before FastAPI starts
This addresses Azure deployment issues where Prisma client may not be generated
"""

import subprocess
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_prisma_client():
    """Ensure Prisma client is generated and available"""
    try:
        # Check if Prisma client exists
        client_path = "node_modules/.prisma/client"
        if not os.path.exists(client_path):
            logger.info("Prisma client not found, generating...")
            
            # Install Node.js dependencies if needed
            if not os.path.exists("node_modules"):
                logger.info("Installing Node.js dependencies...")
                subprocess.run(["npm", "install"], check=True)
            
            # Generate Prisma client
            logger.info("Generating Prisma client...")
            subprocess.run(["npx", "prisma", "generate"], check=True)
            
            if os.path.exists(client_path):
                logger.info("✓ Prisma client generated successfully")
            else:
                raise Exception("Prisma client generation failed")
        else:
            logger.info("✓ Prisma client already exists")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during Prisma setup: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    ensure_prisma_client()
    
    # Start the FastAPI application
    logger.info("Starting FastAPI application...")
    os.system("python -m uvicorn src.app:app --host 0.0.0.0 --port 8000")
