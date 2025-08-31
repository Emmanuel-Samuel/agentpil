#!/usr/bin/env python3
"""
Post-deployment script to generate Prisma client in Azure Web Apps environment.
This runs after deployment but before the main app starts.
"""

import subprocess
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_prisma_client():
    """Generate Prisma client in Azure environment"""
    try:
        logger.info("=== Post-Deployment Prisma Setup ===")
        
        # Check if DATABASE_URL is available
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return False
            
        logger.info(f"DATABASE_URL configured: {database_url[:30]}...")
        
        # Generate Python Prisma client
        logger.info("Generating Python Prisma client...")
        result = subprocess.run(
            [sys.executable, "-m", "prisma", "generate"],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy()
        )
        
        logger.info("Prisma generate stdout:")
        logger.info(result.stdout)
        
        # Verify the client was generated
        try:
            from prisma import Prisma
            logger.info("✓ Python Prisma client generated and importable")
            return True
        except ImportError as e:
            logger.error(f"Prisma client import failed: {e}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Prisma generation failed: {e}")
        logger.error(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = generate_prisma_client()
    if not success:
        logger.error("Prisma client generation failed")
        sys.exit(1)
    logger.info("Prisma client generation completed successfully")
