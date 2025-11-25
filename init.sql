-- 
--  Copyright 2025 EDT&Partners
--
--  Licensed under the Apache License, Version 2.0 (the "License");
--  you may not use this file except in compliance with the License.
--  You may obtain a copy of the License at
--
--      http://www.apache.org/licenses/LICENSE-2.0
--
--  Unless required by applicable law or agreed to in writing, software
--  distributed under the License is distributed on an "AS IS" BASIS,
--  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
--  See the License for the specific language governing permissions and
--  limitations under the License.
--

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
