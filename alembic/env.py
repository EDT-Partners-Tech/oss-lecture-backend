# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from database.models import Base
from database.db import ENVIRONMENT, get_database_url_from_secret

# Get DATABASE_SECRET from environment
DATABASE_SECRET = os.getenv("DATABASE_SECRET")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "us-east-1")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if not DATABASE_SECRET:
    raise ValueError("DATABASE_SECRET environment variable not set")

DATABASE_URL = get_database_url_from_secret(DATABASE_SECRET, AWS_REGION_NAME, True) if ENVIRONMENT == "production" else os.getenv("DATABASE_URL")
# Dynamically set sqlalchemy.url using the same function as db.py
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Use SQLAlchemy models metadata as source of truth
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,  # Use the reflected metadata
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
