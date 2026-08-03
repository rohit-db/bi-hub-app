# services/mas_client.py
from __future__ import annotations

import json
from typing import AsyncIterator, Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from auth.identity import Identity
from config import settings
from utils.logging import logger


class MASChatClient:
    """
    Transport-only client for Databricks MAS.

    - PAT (auth_type == "pat"): use OpenAI-compatible client for streaming.
    - OBO (auth_type == "obo"): use raw REST SSE to /invocations for streaming.

    Public:
      - stream_raw(identity, messages) -> async iterator of raw events (dicts or SDK objects)
      - create_once(identity, messages) -> one-shot non-streaming response (dict)
    """

    def __init__(self) -> None:
        self._base_url: str = settings.agent_base_url.rstrip("/")
        self._endpoint: str = settings.agent_endpoint
        self._timeout_s: int = getattr(settings, "http_timeout_s", 180)

    # ---------- Public API ----------

    async def stream_raw(
        self,
        identity: Identity,
        messages: List[Dict[str, Any]],
        endpoint: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """
        Yield raw streaming events. Choose transport based on identity.auth_type.
        `messages` must be OpenAI-style: [{"role":"user","content":"..."}] (+ history if desired).
        `endpoint` overrides the instance-level endpoint for per-agent routing.
        """
        bearer = identity.token_source.bearer_token()
        if not bearer:
            raise RuntimeError("Missing bearer token")

        effective_endpoint = endpoint or self._endpoint

        if identity.auth_type == "pat":
            async for ev in self._stream_rest_sse(bearer, messages, effective_endpoint):
                yield ev
            # async for ev in self._stream_openai(bearer, messages): Commented out for now as it is causing issues with out of order events
            #     yield ev
        else:
            # Default to OBO path
            async for ev in self._stream_rest_sse(bearer, messages, effective_endpoint):
                yield ev

    async def create_once(
        self, identity: Identity, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Non-streaming call. Returns parsed JSON response (dict).
        """
        bearer = identity.token_source.bearer_token()
        if not bearer:
            raise RuntimeError("Missing bearer token")

        if identity.auth_type == "pat":
            client = self._client_openai(bearer)
            resp = await client.responses.create(
                model=self._endpoint,
                input=messages,
                stream=False,
            )
            # Convert SDK object to dict (best-effort)
            return json.loads(json.dumps(resp, default=lambda o: getattr(o, "__dict__", str(o))))
        else:
            url = f"{self._base_url}/{self._endpoint}/invocations"
            async with httpx.AsyncClient(timeout=self._timeout_s) as http:
                r = await http.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {bearer}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"input": messages, "stream": False},
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"MAS HTTP {r.status_code}: {r.text}")
                return r.json()

    # ---------- PAT path (OpenAI client) ----------

    def _client_openai(self, bearer: str) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=bearer, base_url=self._base_url, timeout=self._timeout_s)

    async def _stream_openai(
        self, bearer: str, messages: List[Dict[str, Any]]
    ) -> AsyncIterator[Any]:
        """
        Streaming via OpenAI-compatible SDK (works well with PAT).
        Yields SDK event objects (your normalizer already handles getattr/ dict).
        """
        logger.info(f"[DEBUG] _stream_openai called with bearer: {bearer}")
        logger.info(f"[DEBUG] token length: {len(bearer)}")
        client = self._client_openai(bearer)
        async with client.responses.stream(
            model=self._endpoint,
            input=messages,
        ) as stream:
            async for event in stream:
                logger.info(f"[DEBUG] OpenAI stream event: {event}")
                yield event
            # If you want the final consolidated response:
            # final = await stream.get_final_response()
            # yield {"type": "final.response", "payload": json.loads(...)}  # optional

    # ---------- OBO path (direct REST SSE) ----------

    async def _stream_rest_sse(
        self, bearer: str, messages: List[Dict[str, Any]], endpoint: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streaming via raw SSE from /invocations (needed for OBO).
        Yields dicts shaped like OpenAI events (with a 'type' key) so your normalizer works unchanged.
        """
        logger.info(f"[DEBUG] _stream_rest_sse called with bearer: {bearer}")
        logger.info(f"[DEBUG] token length: {len(bearer)}")
        effective = endpoint or self._endpoint
        url = f"{self._base_url}/{effective}/invocations"
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {"input": messages, "stream": True}

        async with httpx.AsyncClient(timeout=self._timeout_s) as http:
            async with http.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(f"MAS HTTP {resp.status_code}: {body.decode('utf-8', errors='ignore')}")

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    # SSE lines can be comments (':keepalive') or 'data: {...}'
                    if line.startswith(":"):
                        continue
                    if line.lower().startswith("data:"):
                        data = line[5:].strip()
                    else:
                        # Some servers omit "data:" prefix; handle anyway
                        data = line.strip()

                    if not data or data == "[DONE]":
                        continue

                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        # Log and continue; optionally yield as text error event
                        logger.warning(f"SSE parse warning: {data[:200]}")
                        continue

                    # Expect MAS to send objects with "type" keys similar to OpenAI events
                    # Example types: response.output_text.delta, response.output_item.done, response.error
                    yield obj
