from config import settings
from utils.logging import logger
from sqlalchemy import create_engine, text, event
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
import uuid


def get_credential():
    '''
    This function gets a credential for the PostgreSQL on Lakebase with OAuth token.
    '''
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
    '''
    This function creates a SQLAlchemy pool for the PostgreSQL on Lakebase with OAuth token.
    '''
    postgres_pool = create_engine(settings.pg_connection_string)

    @event.listens_for(postgres_pool, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        credential = get_credential()
        cparams["password"] = credential.token

    return postgres_pool


def create_chainlit_data_layer():
    '''
    This function creates a data layer for Chainlit using Lakebase with OAuth token using SQLAlchemy.
    '''
    data_layer = SQLAlchemyDataLayer(settings.pg_connection_string)

    engine = data_layer.engine
    # For async engines, we need to use the sync engine for event listeners
    if hasattr(engine, 'sync_engine'):
        sync_engine = engine.sync_engine
    else:
        sync_engine = engine

    @event.listens_for(sync_engine, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        credential = get_credential()
        cparams["password"] = credential.token

    return data_layer


def test_database_connection():
    engine = create_sync_engine()
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            version = result.scalar()
        logger.info(f"Connection successful - PostgreSQL Version: {version}")
    except Exception as e:
        logger.info(f"Connection failed: {e}")


if __name__ == "__main__":
    # Test the regular data layer
    test_database_connection()
