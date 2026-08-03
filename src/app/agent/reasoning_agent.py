from __future__ import annotations
from typing import AsyncIterator
from agent.genie_mcp import GenieMCP
from config import settings
from utils.logging import logger


class ReasoningAgent:
    """Hosts the reasoning loop in-app. Genie MCP is a tool.

    Emits RAW events shaped for services.mas_normalizer.normalize:
      - {"type":"response.output_text.delta","item_id","delta"}
      - {"type":"response.output_item.done","item_id","item":{...}}
      - {"type":"response.error","error"}
    """

    def __init__(self, space_id: str | None = None) -> None:
        self._genie = GenieMCP(space_id)

    async def stream(self, identity, messages: list[dict]) -> AsyncIterator[dict]:
        try:
            async for ev in self._run_stream(identity, messages):
                yield ev
        except Exception as e:  # surface as a terminal error event
            logger.error(f"ReasoningAgent error: {e}")
            yield {"type": "response.error", "error": str(e)}

    async def _run_stream(self, identity, messages: list[dict]) -> AsyncIterator[dict]:
        """Drive the OpenAI Agents SDK with Genie MCP; translate its stream
        events into normalizer-compatible raw events.

        Uses databricks_openai.agents (Agent, Runner) + McpServer from GenieMCP.
        Tool start -> response.output_item.done(item.type=function_call);
        tool result -> function_call_output; assistant text -> output_text.delta
        then a final message-done. Model = settings.reasoning_model.
        """
        from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI

        bearer = identity.token_source.bearer_token()
        if not bearer:
            raise RuntimeError("Missing bearer token for reasoning model")

        # The Agents SDK defaults to api.openai.com + OPENAI_API_KEY. Point it at
        # the Databricks Foundation Model API instead: a custom AsyncOpenAI client
        # against {host}/serving-endpoints authenticated with the OBO bearer, wrapped
        # in OpenAIChatCompletionsModel. Also disable the SDK's default tracing
        # exporter, which would otherwise try to upload traces to OpenAI (and demand
        # an OpenAI key we don't have).
        set_tracing_disabled(True)
        oai_client = AsyncOpenAI(api_key=bearer, base_url=settings.agent_base_url)
        model = OpenAIChatCompletionsModel(
            model=settings.reasoning_model, openai_client=oai_client
        )

        user_text = messages[-1]["content"] if messages else ""
        async with self._genie.server(identity) as genie_server:
            agent = Agent(
                name="BI reasoning agent",
                instructions=(
                    "You are a BI analyst. Use the Genie tool to query governed "
                    "data and answer clearly. Prefer concise, well-formatted answers."
                ),
                model=model,
                mcp_servers=[genie_server],
            )
            result = Runner.run_streamed(agent, user_text)
            async for event in result.stream_events():
                for raw in _translate(event):
                    yield raw


def _message_text(item) -> str:
    """Extract assistant text from a MessageOutputItem.

    Prefer the SDK's ItemHelpers.text_message_output (concatenates the
    ResponseOutputText parts of raw_item.content). Fall back to walking
    raw_item.content, then to str(), so a helper/shape change degrades to
    best-effort text rather than stringifying an object.
    """
    try:
        from agents import ItemHelpers  # lazy: only available on the app runtime
        return ItemHelpers.text_message_output(item)
    except Exception:
        pass
    raw = getattr(item, "raw_item", None)
    content = getattr(raw, "content", None)
    if content:
        parts = []
        for c in content:
            t = getattr(c, "text", None)
            if t:
                parts.append(t)
        if parts:
            return "".join(parts)
    return str(raw) if raw is not None else ""


def _translate(event) -> list[dict]:
    """Map OpenAI Agents SDK (>=0.18) stream events -> normalizer raw events.

    Verified against openai-agents 0.18.3 event/item shapes:
      - RawResponsesStreamEvent (type "raw_response_event"): data is a
        ResponseStreamEvent; text deltas have data.type
        "response.output_text.delta" with data.delta.
      - RunItemStreamEvent (type "run_item_stream_event"): item is a RunItem
        whose .type discriminates; ToolCallItem exposes .tool_name/.call_id,
        ToolCallOutputItem exposes .output/.call_id, MessageOutputItem's text
        comes from ItemHelpers.text_message_output (NOT str(raw_item)).

    Pure function so it stays unit-testable without network or the SDK.
    """
    etype = getattr(event, "type", None)
    out: list[dict] = []
    if etype == "raw_response_event":
        data = getattr(event, "data", None)
        # Only forward genuine text deltas; other raw events also carry a
        # .delta with a different data.type and must not be treated as text.
        if getattr(data, "type", None) == "response.output_text.delta":
            delta = getattr(data, "delta", None)
            if delta:
                out.append({"type": "response.output_text.delta", "item_id": "msg", "delta": delta})
    elif etype == "run_item_stream_event":
        item = getattr(event, "item", None)
        itype = getattr(item, "type", None)
        if itype == "tool_call_item":
            out.append({"type": "response.output_item.done", "item_id": "tool",
                        "item": {"type": "function_call",
                                 "name": getattr(item, "tool_name", None) or "genie",
                                 "arguments": str(getattr(item, "arguments", "") or "")}})
        elif itype == "tool_call_output_item":
            out.append({"type": "response.output_item.done", "item_id": "tool",
                        "item": {"type": "function_call_output",
                                 "call_id": getattr(item, "call_id", None) or "genie",
                                 "output": str(getattr(item, "output", "") or "")}})
        elif itype == "message_output_item":
            out.append({"type": "response.output_item.done", "item_id": "msg",
                        "item": {"type": "message",
                                 "content": [{"text": _message_text(item)}]}})
    return out
