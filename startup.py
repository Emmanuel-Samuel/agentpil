#!/usr/bin/env python3
"""
Azure Web App Startup Script
Generates Prisma client and starts the FastAPI application
"""

import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def start_application():
    """Start the FastAPI application with gunicorn"""
    try:
        logger.info("=== Starting FastAPI Application ===")
        
        # Verify Prisma client is available
        try:
            from prisma import Prisma
            logger.info(" Prisma client is available")
        except ImportError as e:
            logger.error(" Prisma client not found. Make sure it was generated during build.")
            sys.exit(1)
            
        # Get port from environment variable (Azure Web Apps) or default to 8000
        port = int(os.environ.get("PORT", 8000))
        
        # Start the application
        cmd = [
            "gunicorn",
            "src.app:app",
            "--worker-class", "uvicorn.workers.UvicornWorker",
            "--workers", "1",
            "--bind", f"0.0.0.0:{port}"
        ]

        logger.info(f"Starting application with command: {' '.join(cmd)}")
        os.execvp(cmd[0], cmd)

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("=== Starting Application ===")
    start_application()
