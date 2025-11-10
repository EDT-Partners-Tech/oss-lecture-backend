-- © [2025] EDT&Partners. Licensed under CC BY 4.0.

-- PostgreSQL initialization script
-- This script runs when the PostgreSQL container starts for the first time

-- Create the main database (if not already created by POSTGRES_DB)
-- The database 'lecture_db' is already created by the POSTGRES_DB environment variable

-- Create any additional databases if needed
-- CREATE DATABASE lecture_test_db;

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- You can add any initial tables, users, or other setup here
-- Example:
-- CREATE USER app_user WITH PASSWORD 'app_password';
-- GRANT ALL PRIVILEGES ON DATABASE lecture_db TO app_user;

ECHO 'PostgreSQL initialization completed';
