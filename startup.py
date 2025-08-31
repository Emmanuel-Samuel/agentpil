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
        
        # Always try to generate Python Prisma client in Azure environment
        logger.info("Generating Python Prisma client...")
        subprocess.run([sys.executable, "-m", "prisma", "generate"], check=True, cwd="/home/site/wwwroot")
        
        # Verify Python Prisma client generation
        try:
            from prisma import Prisma
            logger.info("✓ Python Prisma client generated successfully")
        except ImportError as e:
            logger.warning(f"Python Prisma client import failed: {e}")
            
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
