from pydantic_settings import BaseSettings
from utils.logging import logger
from dotenv import load_dotenv
from typing import Optional, List, Dict

import os
load_dotenv()


class Settings(BaseSettings):
    enable_header_auth: bool = False
    enable_password_auth: bool = True

    # Lakebase
    pg_database_instance: Optional[str] = None
    pg_host: Optional[str] = None
    pg_port: int = 5432
    pg_user: Optional[str] = None
    pg_database: Optional[str] = None
    pg_sslmode: Optional[str] = "require"

    @property
    def pg_connection_string(self) -> str:
        return f"postgresql+psycopg://{self.pg_user}:@{self.pg_host}:{self.pg_port}/{self.pg_database}?sslmode={self.pg_sslmode}"

    logger.info(f"Database Instance: {pg_database_instance}") 

    # Workspace
    databricks_host: Optional[str] = None

    # Serving Endopints
    agent_endpoint: Optional[str] = None
    @property
    def agent_base_url(self) -> str:
        if self.databricks_host.startswith("https://"):
            return f"{self.databricks_host}/serving-endpoints"
        else:
            return f"https://{self.databricks_host}/serving-endpoints"
        return f"{self.databricks_host}/serving-endpoints"

    # Chat 
    history_max_turns: int = 10
    history_max_chars: int = 120000

    chat_starter_messages: List[Dict[str, str]] = [
        {"label": "Revenue Analytics", "message": "Analyze monthly revenue in the last 12 months"}, 
        {"label": "Hot and Ready Performance", "message": "Analyze the performance of Hot and Ready products in the last 12 months"}
    ]

    # Local Only
    pat: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        if self.enable_header_auth and self.enable_password_auth:
            logger.error(
                "Both header and password auth cannot be enabled simultaneously")
            return False
        if not self.enable_header_auth and not self.enable_password_auth:
            logger.error("At least one auth method must be enabled")
            return False
        return True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.is_valid:
            raise ValueError(
                "Invalid auth configuration: Either enable_header_auth or enable_password_auth must be enabled, but not both"
            )


# Create settings instance with environment variables
env_vars = {
    'enable_header_auth': os.getenv("ENABLE_HEADER_AUTH"),
    'enable_password_auth': os.getenv("ENABLE_PASSWORD_AUTH"),
    'pg_database_instance': os.getenv("DATABASE_INSTANCE"),
    'pg_host': os.getenv("PGHOST"),
    'pg_port': int(os.getenv("PGPORT", 5432)),
    'pg_user': os.getenv("PGUSER"),
    'pg_database': os.getenv("PGDATABASE"),
    'pg_sslmode': os.getenv("PGSSLMODE", "require"),
    'databricks_host': os.getenv("DATABRICKS_HOST"),
    'agent_endpoint': os.getenv("SERVING_ENDPOINT"),
    # Local Only
    'pat': os.getenv("DATABRICKS_TOKEN"),
}

print(f"Environment Variables: {env_vars}")

# Filter out None values to use defaults
filtered_vars = {k: v for k, v in env_vars.items() if v is not None}

settings = Settings(
    **filtered_vars
)

logger.info(f"Settings: {settings}")