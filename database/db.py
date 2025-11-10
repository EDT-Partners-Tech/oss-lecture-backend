# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
import os
import time
import asyncio
import inspect
import logging
from functools import wraps
from sqlalchemy import create_engine, orm
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from utility.aws_clients import secrets_client
from utility.parameter_store import ParameterStore

logger = logging.getLogger(__name__)

# Initialize parameter store and load parameters
parameter_store = ParameterStore()
parameter_store.load_parameters()  # Cargar los parámetros antes de usarlos
AWS_REGION_NAME = parameter_store.get_parameter('AWS_REGION_NAME')
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

DATABASE_SECRET = os.getenv("DATABASE_SECRET")
if not DATABASE_SECRET:
    raise ValueError("DATABASE_SECRET environment variable not set")

def get_database_url_from_secret(secret_arn: str, region_name: str, sync_pg: bool = False) -> str:
    if not secret_arn:
        raise ValueError("Secret ARN cannot be empty")
    response = secrets_client.get_secret_value(SecretId=secret_arn)

    if "SecretString" not in response:
        raise ValueError("SecretString not found in Secrets Manager response")

    secret = json.loads(response["SecretString"])

    # JSON Secret contains: username, password, host, port, dbname
    db_url = (
        f"postgresql+psycopg2://{secret['username']}:{secret['password']}"
        f"@{secret['host']}:{secret['port']}/{secret['dbname']}"
    )
    # replace the DB password with the stars
    logger.info(db_url.replace(secret['password'], "********"))
    return db_url

# Fetch and build the DATABASE_URL from Secrets Manager using the ARN
DATABASE_URL = get_database_url_from_secret(DATABASE_SECRET, AWS_REGION_NAME) if ENVIRONMENT == "production" else os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Failed to retrieve DATABASE_URL from Secrets Manager")

Base = orm.declarative_base()

_ENGINE = None
_ASYNC_ENGINE = None
_SESSION_LOCAL = None
_ASYNC_SESSION_LOCAL = None

def retry_on_disconnect(max_retries=3, initial_delay=1, max_delay=10):
    def decorator(func):
        is_generator = inspect.isgeneratorfunction(func)
        is_async_generator = inspect.isasyncgenfunction(func)

        if is_generator:
            @wraps(func)
            def generator_wrapper(*args, **kwargs):
                delay = initial_delay
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        yield from func(*args, **kwargs)
                        return
                    except (OperationalError, SQLAlchemyError) as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            time.sleep(delay)
                            delay = min(delay * 2, max_delay)
                            logger.info(f"Retrying connection to the database (attempt {attempt + 1}/{max_retries})")
                        else:
                            raise last_exception

        if is_async_generator:
            @wraps(func)
            async def async_generator_wrapper(*args, **kwargs):
                delay = initial_delay
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        async for item in func(*args, **kwargs):
                            yield item
                        return
                    except (OperationalError, SQLAlchemyError) as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            time.sleep(delay)
                            delay = min(delay * 2, max_delay)
                            logger.info(f"Retrying connection to the database (attempt {attempt + 1}/{max_retries})")
                        else:
                            raise last_exception

            return async_generator_wrapper
        elif is_generator:
            return generator_wrapper

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (OperationalError, SQLAlchemyError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay = min(delay * 2, max_delay)
                        logger.info(f"Retrying connection to the database (attempt {attempt + 1}/{max_retries})")
                    else:
                        raise last_exception
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, SQLAlchemyError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay = min(delay * 2, max_delay)
                        logger.info(f"Retrying connection to the database (attempt {attempt + 1}/{max_retries})")
                    else:
                        raise last_exception
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            DATABASE_URL, 
            echo=False,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_use_lifo=True
        )
    return _ENGINE

def get_async_engine():
    global _ASYNC_ENGINE
    if _ASYNC_ENGINE is None:
        _ASYNC_ENGINE = create_async_engine(
            DATABASE_URL, 
            echo=False,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_use_lifo=True
        )
    return _ASYNC_ENGINE

def get_session_local():
    global _SESSION_LOCAL
    if _SESSION_LOCAL is None:
        _SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SESSION_LOCAL

# Export SessionLocal directly for easier use
SessionLocal = get_session_local()

def get_async_session_local():
    global _ASYNC_SESSION_LOCAL
    if _ASYNC_SESSION_LOCAL is None:
        _ASYNC_SESSION_LOCAL = sessionmaker(
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            bind=get_async_engine()
        )
    return _ASYNC_SESSION_LOCAL

@retry_on_disconnect()
def get_db():
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@retry_on_disconnect()
async def get_async_db():
    AsyncSessionLocal = get_async_session_local()
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()

def init_db():
    get_engine()
