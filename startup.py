import subprocess
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_prisma_client():
    """Ensure Prisma client is generated and available"""
    try:
        logger.info("=== Prisma Client Setup ===")
        
        # Always try to generate Prisma client in Azure environment
        logger.info("Installing Node.js dependencies...")
        subprocess.run(["npm", "install"], check=True, cwd="/home/site/wwwroot")
        
        logger.info("Generating Prisma client...")
        subprocess.run(["npx", "prisma", "generate"], check=True, cwd="/home/site/wwwroot")
        
        # Verify generation
        client_path = "/home/site/wwwroot/node_modules/.prisma/client"
        if os.path.exists(client_path):
            logger.info("✓ Prisma client generated successfully")
        else:
            logger.warning("Prisma client path not found, but generation completed")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during Prisma setup: {e}")
        # Continue anyway - let the app try to start
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        # Continue anyway - let the app try to start

if __name__ == "__main__":
    ensure_prisma_client()
    
    # Start the FastAPI application with gunicorn
    logger.info("Starting FastAPI application with gunicorn...")
    os.chdir("/home/site/wwwroot")
    os.system("python3 -m gunicorn src.app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000")
