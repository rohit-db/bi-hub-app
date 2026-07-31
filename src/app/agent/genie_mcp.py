from __future__ import annotations
from contextlib import asynccontextmanager
import config as _config
from utils.logging import logger


class GenieMCP:
    """Wraps the managed Genie MCP server as an agent tool source.

    URL: https://{host}/api/2.0/mcp/genie/{space_id}
    Auth: OBO/PAT bearer via Identity; OBO requires the `genie` scope.
    space_id defaults to settings.genie_space_id but can be passed per selection
    so multiple Genie One agents can target different spaces.
    """

    def __init__(self, space_id: str | None = None) -> None:
        self._space_id = space_id or _config.settings.genie_space_id

    def url(self) -> str:
        return _config.settings.genie_mcp_url_for(self._space_id)

    def is_configured(self) -> bool:
        return bool(self._space_id)

    @asynccontextmanager
    async def server(self, identity):
        from databricks.sdk import WorkspaceClient
        from databricks_openai.agents import McpServer

        bearer = identity.token_source.bearer_token()
        if not bearer:
            raise RuntimeError("Missing bearer token for Genie MCP")
        wc = WorkspaceClient(host=_config.settings.databricks_host, token=bearer)
        logger.info(f"Opening Genie MCP server at {self.url()}")
        async with McpServer(url=self.url(), name="genie-space", workspace_client=wc) as srv:
            yield srv
