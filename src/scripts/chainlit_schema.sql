-- Chainlit SQLAlchemy Schema for Lakebase
-- Based on: https://docs.chainlit.io/data-layers/sqlalchemy
-- Run this in your Lakebase SQL editor
-- CANONICAL DDL lives in src/app/memory/schema.py (CHAINLIT_DDL). Keep in sync.

-- ==============================================
-- DATABASE AND SCHEMA SETUP
-- ==============================================

-- Ensure we're using the correct database
-- Replace <DATABASE_NAME> with your actual database name (e.g., 'lakebase_demo', 'databricks_postgres')
\c <DATABASE_NAME>;

-- Create schema if it doesn't exist (using public schema by default)
-- If you want a custom schema, uncomment and modify the line below:
-- CREATE SCHEMA IF NOT EXISTS chainlit;

-- Set search path to ensure we're working in the right schema
SET search_path TO public;

-- ==============================================
-- CLEAN SLATE - DROP EXISTING TABLES
-- ==============================================

-- Drop existing tables in correct order (respecting foreign key constraints)
DROP TABLE IF EXISTS feedbacks CASCADE;
DROP TABLE IF EXISTS elements CASCADE;
DROP TABLE IF EXISTS steps CASCADE;
DROP TABLE IF EXISTS threads CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;

-- ==============================================
-- CREATE CHAINLIT TABLES
-- ==============================================

-- Create the users table
CREATE TABLE users (
    "id" UUID PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" JSONB NOT NULL,
    "createdAt" TEXT
);

-- Create the threads table
CREATE TABLE threads (
    "id" UUID PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" UUID,
    "userIdentifier" TEXT,
    "tags" TEXT[],
    "metadata" JSONB,
    FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
);

-- Create the steps table
CREATE TABLE steps (
    "id" UUID PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "threadId" UUID NOT NULL,
    "parentId" UUID,
    "streaming" BOOLEAN NOT NULL,
    "waitForAnswer" BOOLEAN,
    "isError" BOOLEAN,
    "metadata" JSONB,
    "tags" TEXT[],
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "command" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" JSONB,
    "showInput" TEXT,
    "language" TEXT,
    "indent" INT,
    "defaultOpen" BOOLEAN,
    -- Added for Chainlit 2.11.1 data layer (StepDict fields not present in the
    -- older 2.7.x schema). Missing any of these causes psycopg UndefinedColumn
    -- errors on every step write, breaking chat-history persistence.
    "autoCollapse" BOOLEAN,
    "modes" JSONB,
    "icon" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

-- Create the elements table
CREATE TABLE elements (
    "id" UUID PRIMARY KEY,
    "threadId" UUID,
    "type" TEXT,
    "url" TEXT,
    "chainlitKey" TEXT,
    "name" TEXT NOT NULL,
    "display" TEXT,
    "objectKey" TEXT,
    "size" TEXT,
    "page" INT,
    "language" TEXT,
    "forId" UUID,
    "mime" TEXT,
    "props" JSONB,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

-- Create the feedbacks table
CREATE TABLE feedbacks (
    "id" UUID PRIMARY KEY,
    "forId" UUID NOT NULL,
    "threadId" UUID NOT NULL,
    "value" INT NOT NULL,
    "comment" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

-- ==============================================
-- VERIFICATION AND PERMISSIONS
-- ==============================================

-- Verify tables were created successfully
SELECT 
    table_name,
    table_type,
    table_schema
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('users', 'threads', 'steps', 'elements', 'feedbacks')
ORDER BY table_name;

-- Show table structure for verification
\d users;
\d threads;
\d steps;
\d elements;
\d feedbacks;

-- ==============================================
-- GRANT PERMISSIONS TO APP CLIENT ID
-- ==============================================

-- Grant schema usage permissions
-- Replace <CLIENT_ID> with your actual app client ID from the Environment tab
-- Replace <DATABASE_NAME> with your actual database name
GRANT USAGE ON SCHEMA public TO "<CLIENT_ID>";

-- Grant table-level permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "<DATABASE_NAME>"."public"."elements" TO "<CLIENT_ID>";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "<DATABASE_NAME>"."public"."feedbacks" TO "<CLIENT_ID>";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "<DATABASE_NAME>"."public"."steps" TO "<CLIENT_ID>";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "<DATABASE_NAME>"."public"."threads" TO "<CLIENT_ID>";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "<DATABASE_NAME>"."public"."users" TO "<CLIENT_ID>";

-- Grant sequence permissions (for auto-incrementing IDs if needed)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<CLIENT_ID>";

-- ==============================================
-- FINAL VERIFICATION
-- ==============================================

-- Verify permissions were granted
SELECT 
    grantee,
    table_name,
    privilege_type
FROM information_schema.table_privileges 
WHERE grantee = '<CLIENT_ID>'
AND table_name IN ('users', 'threads', 'steps', 'elements', 'feedbacks')
ORDER BY table_name, privilege_type;

-- Test connection with a simple query
SELECT 'Chainlit schema setup complete!' as status, 
       COUNT(*) as table_count
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('users', 'threads', 'steps', 'elements', 'feedbacks');
