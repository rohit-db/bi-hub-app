# services/viz.py
"""Genie visualization attachment support (Beta, drop-first).

Gated by settings.enable_visualization (default False).
Download endpoint path per Beta API spec:
  /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}
  /messages/{message_id}/attachments/{attachment_id}/download-visualization
"""
from __future__ import annotations

import httpx
import plotly.io as pio
import chainlit as cl
from config import settings
from utils.logging import logger

_VIZ_PATH = (
    "/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}"
    "/messages/{message_id}/attachments/{attachment_id}/download-visualization"
)


def enabled() -> bool:
    return bool(settings.enable_visualization)


async def fetch_visualization(
    identity,
    space_id: str,
    conversation_id: str,
    message_id: str,
    attachment_id: str,
) -> dict:
    """Download a Genie viz attachment (Beta).

    Returns a normalized payload dict:
      {"kind": "plotly", "figure_json": <text>}   if content-type is JSON
      {"kind": "image",  "content": <bytes>}       otherwise
    """
    bearer = identity.token_source.bearer_token()
    host = settings.databricks_host or ""
    base = host if host.startswith("https://") else f"https://{host}"
    url = base + _VIZ_PATH.format(
        space_id=space_id,
        conversation_id=conversation_id,
        message_id=message_id,
        attachment_id=attachment_id,
    )
    logger.debug("fetch_visualization GET %s", url)
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(url, headers={"Authorization": f"Bearer {bearer}"})
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "json" in ctype:
            return {"kind": "plotly", "figure_json": r.text}
        return {"kind": "image", "content": r.content}


def to_element(viz_payload: dict):
    """Convert a viz payload dict into a Chainlit element.

    kind "plotly" -> cl.Plotly  (uses plotly.io.from_json)
    anything else -> cl.Image
    """
    if viz_payload.get("kind") == "plotly":
        fig = pio.from_json(viz_payload["figure_json"])
        return cl.Plotly(name="Chart", figure=fig, display="inline")
    return cl.Image(name="Chart", content=viz_payload["content"], display="inline")
