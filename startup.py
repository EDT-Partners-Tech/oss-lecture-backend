# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os

from sqlalchemy.orm import Session
from database.crud import get_region_by_name, create_region, update_ai_models_region, update_region_s3_bucket
from logging_config import setup_logging
import alembic.config
import alembic.command

logger = setup_logging(module_name='startup')
async def run_database_migrations() -> None:
    """Run database migrations using Alembic."""
    logger.info("Starting database migrations...")
    try:
        alembic_cfg = alembic.config.Config("alembic.ini")
        logger.debug("Alembic configuration loaded successfully")
        
        alembic.command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.error(f"Error executing database migrations: {str(e)}")
        logger.error(f"Migration error type: {type(e).__name__}")
        import traceback
        logger.error(f"Migration error traceback: {traceback.format_exc()}")
        raise

async def manage_region(db: Session) -> None:
    """Manage region configuration in the database."""
    logger = setup_logging(module_name='manage_region')
    logger.info("Starting region management...")
    
    try:
        aws_region = os.getenv("AWS_REGION_NAME")
        logger.info(f"AWS_REGION_NAME: {aws_region}")
        s3_bucket_name = os.getenv("AWS_S3_CONTENT_BUCKET_NAME")
        logger.info(f"AWS_S3_CONTENT_BUCKET_NAME: {s3_bucket_name}")

        if not aws_region or not s3_bucket_name:
            logger.warning("AWS_REGION_NAME or AWS_S3_CONTENT_BUCKET_NAME not set in environment variables")
            return
        
        logger.info("Starting region management...")


        # Check if region already exists
        existing_region = get_region_by_name(db, aws_region)
        logger.info(f"existing_region: {existing_region}")
        region_suffix = aws_region.split('-')[0]
        logger.info(f"region_suffix: {region_suffix}")


        if existing_region:
            # Only update s3_bucket if it's different
            if existing_region.s3_bucket != s3_bucket_name:
                logger.info(f"Updating s3_bucket for region {aws_region} to {s3_bucket_name}")
                update_region_s3_bucket(db, existing_region, s3_bucket_name)
                logger.info(f"Updated s3_bucket for region {aws_region} to {s3_bucket_name}")
            else:
                logger.debug(f"Region {aws_region} already exists with correct s3_bucket configuration")
        else:
            # Create new region
            logger.info(f"Creating new region {aws_region} with s3_bucket {s3_bucket_name}")
            create_region(db, aws_region, region_suffix, s3_bucket_name)
            logger.info(f"Created new region {aws_region} with s3_bucket {s3_bucket_name}")
    except Exception as e:
        logger.error(f"Error during region management: {str(e)}")
        raise

async def set_ai_models_region(db: Session):
    """Set the region for all AI models in the database."""
    logger = setup_logging(module_name='set_ai_models_region')
    logger.info("Starting AI models region management...")
    
    try:
        # Get region id where region.name = os.getenv("AWS_REGION_NAME")
        aws_region = os.getenv("AWS_REGION_NAME")
        logger.debug(f"Looking up region: {aws_region}")
        
        region = get_region_by_name(db, aws_region)
        if not region:
            logger.error(f"Region {aws_region} not found in database")
            raise ValueError(f"Region {aws_region} not found in database")
        
        region_id = region.id
        logger.debug(f"Found region ID: {region_id}")
        
        # update models.region_id = region_id
        logger.info(f"Updating AI models to use region ID: {region_id}")
        update_ai_models_region(db, region_id)
        logger.info("AI models region management completed successfully")
        
    except Exception as e:
        logger.error(f"Error in AI models region management: {str(e)}")
        logger.error(f"AI models region error type: {type(e).__name__}")
        import traceback
        logger.error(f"AI models region error traceback: {traceback.format_exc()}")
        raise
        

async def run_startup_tasks(db: Session):
    logger.info("Starting application startup tasks...")
    
    try:
        # Run database migrations first
        logger.info("Step 1/3: Running database migrations...")
        await run_database_migrations()
        logger.info("✓ Database migrations completed")
        
        # Then manage region configuration
        logger.info("Step 2/3: Managing region configuration...")
        await manage_region(db)
        logger.info("✓ Region configuration completed")
        
        # Then set the region for all AI models
        logger.info("Step 3/3: Setting AI models region...")
        await set_ai_models_region(db)
        logger.info("✓ AI models region setup completed")
        
        logger.info("✓ All application startup tasks completed successfully")
        
    except Exception as e:
        logger.error(f"Error during startup tasks: {str(e)}")
        logger.error(f"Startup error type: {type(e).__name__}")
        import traceback
        logger.error(f"Startup error traceback: {traceback.format_exc()}")
        raise
