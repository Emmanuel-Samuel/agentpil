#!/usr/bin/env python3
"""
Azure Web App Startup Script
Generates Prisma client and starts the FastAPI application
"""

import os
import sys
import subprocess
import logging

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

        # The root of your application in Azure Web Apps
        working_dir = "/home/site/wwwroot"
        schema_path = os.path.join(working_dir, "schema.prisma")

        logger.info(f"Working directory: {working_dir}")
        logger.info(f"Expected schema path: {schema_path}")

        # Check if schema.prisma exists
        if not os.path.exists(schema_path):
            logger.error(f"schema.prisma not found at {schema_path}")
            logger.error("Please ensure your deployment process copies schema.prisma to the root of your application.")
            return False

        # Check DATABASE_URL
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found in environment variables")
            return False

        logger.info(f"DATABASE_URL configured: {database_url[:50]}...")

        # Generate Prisma client, explicitly providing the schema path
        logger.info("Generating Prisma client...")
        result = subprocess.run(
            [sys.executable, "-m", "prisma", "generate", f"--schema={schema_path}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=working_dir
        )

        logger.info("Prisma generation completed successfully")
        if result.stdout:
            logger.info(f"Generation output: {result.stdout}")

        return True

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

        os.chdir("/home/site/wwwroot")

        cmd = [
            sys.executable, "-m", "gunicorn",
            "src.app:app",
            "-k", "uvicorn.workers.UvicornWorker",
            "--bind", "0.0.0.0:8000"
        ]

        logger.info(f"Starting application with command: {' '.join(cmd)}")
        os.execvp(sys.executable, cmd)

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("=== Azure Web App Startup Script ===")

    if not ensure_prisma_client():
        logger.error("Failed to generate Prisma client. Application cannot start.")
        sys.exit(1)

    start_application()
