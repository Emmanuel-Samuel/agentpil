#!/usr/bin/env python3
"""
Azure Web App Startup Script
Generates Prisma client and starts the FastAPI application
"""

import os
import sys
import subprocess
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def ensure_prisma_client():
    """Generate Prisma client before app starts"""
    try:
        logger.info("=== Starting Prisma Client Generation ===")
        
        # Check if we're in Azure environment
        if os.path.exists("/home/site/wwwroot"):
            working_dir = "/home/site/wwwroot"
            logger.info("Running in Azure Web Apps environment")
        else:
            working_dir = os.getcwd()
            logger.info(f"Running in local environment: {working_dir}")
        
        # Check DATABASE_URL
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found in environment variables")
            logger.info("Available environment variables:")
            for key in sorted(os.environ.keys()):
                if 'DATABASE' in key.upper() or 'DB' in key.upper():
                    logger.info(f"  {key}={os.environ[key][:50]}...")
            return False
            
        logger.info(f"DATABASE_URL configured: {database_url[:50]}...")
        
        # Check if Prisma is installed
        try:
            result = subprocess.run(
                [sys.executable, "-m", "prisma", "--version"],
                capture_output=True,
                text=True,
                cwd=working_dir
            )
            logger.info(f"Prisma version: {result.stdout.strip()}")
        except Exception as e:
            logger.error(f"Prisma CLI not available: {e}")
            return False
        
        # Generate Prisma client
        logger.info("Generating Prisma client...")
        env = os.environ.copy()
        
        result = subprocess.run(
            [sys.executable, "-m", "prisma", "generate"],
            check=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
            env=env
        )
        
        logger.info("Prisma generation completed successfully")
        if result.stdout:
            logger.info(f"Generation output: {result.stdout}")
        
        # Verify the client was generated
        logger.info("Verifying Prisma client import...")
        try:
            # Add a small delay to ensure files are written
            time.sleep(2)
            
            # Try to import Prisma
            from prisma import Prisma
            logger.info("✓ Prisma client successfully generated and importable")
            
            # Test client instantiation
            client = Prisma()
            logger.info("✓ Prisma client can be instantiated")
            
            return True
            
        except ImportError as e:
            logger.error(f"Prisma client import failed: {e}")
            return False
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Prisma generation failed with exit code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        if e.stdout:
            logger.error(f"Standard output: {e.stdout}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during Prisma generation: {e}")
        return False

def start_application():
    """Start the FastAPI application with gunicorn"""
    try:
        logger.info("=== Starting FastAPI Application ===")
        
        # Determine working directory
        if os.path.exists("/home/site/wwwroot"):
            os.chdir("/home/site/wwwroot")
            logger.info("Changed to Azure working directory: /home/site/wwwroot")
        
        # Start gunicorn
        cmd = [
            sys.executable, "-m", "gunicorn",
            "src.app:app",
            "-k", "uvicorn.workers.UvicornWorker",
            "--bind", "0.0.0.0:8000",
            "--workers", "1",
            "--timeout", "120",
            "--log-level", "info"
        ]
        
        logger.info(f"Starting application with command: {' '.join(cmd)}")
        
        # Use exec to replace the current process
        os.execvp(sys.executable, cmd)
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("=== Azure Web App Startup Script ===")
    
    # Step 1: Generate Prisma client
    if not ensure_prisma_client():
        logger.error("Failed to generate Prisma client. Application cannot start.")
        sys.exit(1)
    
    # Step 2: Start the application
    start_application()
