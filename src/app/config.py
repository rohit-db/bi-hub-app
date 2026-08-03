from pydantic_settings import BaseSettings
from utils.logging import logger
from dotenv import load_dotenv
from typing import Optional, List, Dict

import os
import json
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

    # Genie MCP + reasoning agent
    genie_space_id: Optional[str] = None
    reasoning_model: str = "databricks-claude-sonnet-4-5"
    enable_visualization: bool = False

    @property
    def genie_mcp_url(self) -> str:
        host = self.databricks_host or ""
        base = host if host.startswith("https://") else f"https://{host}"
        return f"{base}/api/2.0/mcp/genie/{self.genie_space_id}"

    def genie_mcp_url_for(self, space_id: str) -> str:
        host = self.databricks_host or ""
        base = host if host.startswith("https://") else f"https://{host}"
        return f"{base}/api/2.0/mcp/genie/{space_id}"

    # Available agents (MAS or Genie One) — deployed via AVAILABLE_AGENTS env / DAB var.
    # Empty by default; a deployer supplies agents for their workspace.
    available_agents: List[Dict[str, str]] = []

    # Chat
    history_max_turns: int = 10
    history_max_chars: int = 120000

    chat_starter_messages: List[Dict[str, str]] = [
        {"label": "Key Metrics", "message": "Summarize key metrics for the last quarter"},
        {"label": "Top Revenue Items", "message": "Show top 10 items by revenue"},
        {"label": "Category Breakdown", "message": "Break down results by category"},
        {"label": "Monthly Trend", "message": "Show month-over-month trend"},
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
    'genie_space_id': os.getenv("GENIE_SPACE_ID"),
    'reasoning_model': os.getenv("REASONING_MODEL"),
    'enable_visualization': os.getenv("ENABLE_VISUALIZATION"),
    'available_agents': json.loads(os.getenv("AVAILABLE_AGENTS")) if os.getenv("AVAILABLE_AGENTS") else None,
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