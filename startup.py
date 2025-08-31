import os
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_prisma_client():
    """Generate Prisma client before app starts"""
    try:
        logger.info("=== Generating Prisma Client ===")
        
        # Check DATABASE_URL
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found in environment")
            return False
            
        logger.info(f"DATABASE_URL configured: {database_url[:30]}...")
        
        # Generate Prisma client
        result = subprocess.run(
            [sys.executable, "-m", "prisma", "generate"],
            check=True,
            capture_output=True,
            text=True,
            cwd="/home/site/wwwroot"
        )
        
        logger.info("Prisma generation output:")
        logger.info(result.stdout)
        
        # Test import
        from prisma import Prisma
        logger.info("✓ Prisma client generated and importable")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Prisma generation failed: {e}")
        logger.error(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

if __name__ == "__main__":
    # Generate Prisma client first
    if not ensure_prisma_client():
        logger.error("Failed to generate Prisma client, exiting...")
        sys.exit(1)
    
    # Start the FastAPI application with gunicorn
    logger.info("Starting FastAPI application with gunicorn...")
    os.chdir("/home/site/wwwroot")
    os.system("python3 -m gunicorn src.app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000")
