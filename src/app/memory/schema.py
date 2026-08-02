"""Idempotent Chainlit schema bootstrap, run by the app service principal.

The app's Lakebase database binding is CAN_CONNECT_AND_CREATE, so the app SP
can create its own tables. Because it *creates* them, it *owns* them — there
are no grants to wipe when `bundle deploy` recreates the SP's Postgres role.
This replaces the fragile owner=human + hand-made GRANT model.
"""
from sqlalchemy import text
from utils.logging import logger
from memory.lakebase import create_sync_engine

# Chainlit 2.11.1 schema. CREATE ... IF NOT EXISTS is a no-op when tables
# already exist (never touches existing data). The trailing ALTERs self-heal
# a pre-existing older `steps` table missing the 2.11 columns.
CHAINLIT_DDL = [
    '''CREATE TABLE IF NOT EXISTS users (
        "id" UUID PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" JSONB NOT NULL,
        "createdAt" TEXT
    );''',
    '''CREATE TABLE IF NOT EXISTS threads (
        "id" UUID PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" UUID,
        "userIdentifier" TEXT,
        "tags" TEXT[],
        "metadata" JSONB,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    );''',
    '''CREATE TABLE IF NOT EXISTS steps (
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
        "autoCollapse" BOOLEAN,
        "modes" JSONB,
        "icon" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );''',
    '''CREATE TABLE IF NOT EXISTS elements (
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
    );''',
    '''CREATE TABLE IF NOT EXISTS feedbacks (
        "id" UUID PRIMARY KEY,
        "forId" UUID NOT NULL,
        "threadId" UUID NOT NULL,
        "value" INT NOT NULL,
        "comment" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );''',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "autoCollapse" BOOLEAN;',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "modes" JSONB;',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "icon" TEXT;',
]

_ensured = False


def ensure_schema(engine=None) -> None:
    """Create/upgrade the Chainlit schema as the app SP. Idempotent per process."""
    global _ensured
    if _ensured:
        return
    created_here = engine is None
    engine = engine or create_sync_engine()
    try:
        with engine.begin() as conn:
            for stmt in CHAINLIT_DDL:
                conn.execute(text(stmt))
        _ensured = True
        logger.info("Chainlit schema ensured (app SP owns tables)")
    except Exception as e:
        logger.error(f"ensure_schema failed: {e}")
        raise
    finally:
        if created_here:
            engine.dispose()
