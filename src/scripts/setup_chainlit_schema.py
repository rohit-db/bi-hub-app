#!/usr/bin/env python3
"""
Script to set up the official Chainlit SQLAlchemy schema
Based on: https://docs.chainlit.io/data-layers/sqlalchemy
Uses Databricks Lakebase (managed PostgreSQL) connection
"""

import uuid
from sqlalchemy import create_engine, text, event
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Databricks workspace client
w = WorkspaceClient()

def get_credential():
    """Get credential for Lakebase PostgreSQL connection"""
    try:
        request_id = str(uuid.uuid4())
        cred = w.database.generate_database_credential(
            request_id=request_id, instance_names=[settings.pg_database_instance])
    except Exception as e:
        logger.info(f"❌ Token generation failed: {e}")
        cred = w.token_management.get.token()
        return cred
    return cred

def create_sync_engine():
    """Create SQLAlchemy engine for Lakebase PostgreSQL with OAuth token"""
    postgres_pool = create_engine(settings.pg_connection_string)

    @event.listens_for(postgres_pool, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        credential = get_credential()
        cparams["password"] = credential.token

    return postgres_pool

def check_table_exists(engine, table_name):
    """Check if a table exists in the database"""
    query = text("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = :table_name
    );
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"table_name": table_name})
        return result.scalar()

def get_existing_tables(engine):
    """Get list of existing Chainlit tables"""
    query = text("""
    SELECT table_name
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('users', 'threads', 'steps', 'elements', 'feedbacks', 'chat_sessions')
    ORDER BY table_name;
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query)
        return [row[0] for row in result.fetchall()]

def setup_chainlit_schema():
    """Set up the official Chainlit SQLAlchemy schema"""
    try:
        # Create database engine
        print(f"🔧 Using database: {settings.pg_host}:{settings.pg_port}")
        
        # Create engine
        print("🔌 Creating database engine...")
        engine = create_sync_engine()
        
        # Test connection
        print("🔍 Testing database connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.scalar()
            print(f"✅ Connected to PostgreSQL: {version}")
        
        # Check existing tables
        print("🔍 Checking existing tables...")
        existing_tables = get_existing_tables(engine)
            
        if existing_tables:
            print(f"📋 Found existing tables: {', '.join(existing_tables)}")
            print("⚠️  Tables already exist. Skipping table creation.")
            print("✅ Schema setup complete (tables already exist)!")
            return
        
        print("📝 No existing tables found. Proceeding with table creation...")
        
        # Drop existing tables (safety measure)
        # print("🗑️ Dropping any existing tables...")
        # with engine.connect() as conn:
        #     conn.execute(text('DROP TABLE IF EXISTS feedbacks CASCADE;'))
        #     conn.execute(text('DROP TABLE IF EXISTS elements CASCADE;'))
        #     conn.execute(text('DROP TABLE IF EXISTS steps CASCADE;'))
        #     conn.execute(text('DROP TABLE IF EXISTS threads CASCADE;'))
        #     conn.execute(text('DROP TABLE IF EXISTS users CASCADE;'))
        #     conn.execute(text('DROP TABLE IF EXISTS chat_sessions CASCADE;'))
        #     conn.commit()
        # print("✅ Cleaned up any existing tables")
        
        # Create official Chainlit schema (shared source of truth: app/memory/schema.py)
        print("🔨 Creating official Chainlit schema...")
        from app.memory.schema import CHAINLIT_DDL
        with engine.begin() as conn:
            for stmt in CHAINLIT_DDL:
                conn.execute(text(stmt))
        print("✅ Created official Chainlit schema")
        
        # Verify tables were created successfully
        print("🔍 Verifying table creation...")
        created_tables = get_existing_tables(engine)
            
        if created_tables:
            print(f"✅ Successfully verified tables: {', '.join(created_tables)}")
        else:
            print("⚠️  Warning: No tables found after creation")
        
        print("✅ Schema setup complete!")
        
    except Exception as e:
        print(f"❌ Error setting up schema: {e}")
        import traceback
        traceback.print_exc()

# NOTE: Schema-level grants (GRANT USAGE, GRANT CREATE ON SCHEMA "public" to app SP)
# are issued by the setup job notebook (src/scripts/setup_chainlit_lakebase.ipynb),
# which runs as the deploying human who owns the schema. This script handles table
# creation only and does not manage grants.

if __name__ == "__main__":
    setup_chainlit_schema()
