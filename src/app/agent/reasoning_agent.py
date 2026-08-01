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
        from agents import Agent, Runner  # OpenAI Agents SDK — lazy import

        user_text = messages[-1]["content"] if messages else ""
        async with self._genie.server(identity) as genie_server:
            agent = Agent(
                name="BI reasoning agent",
                instructions=(
                    "You are a BI analyst. Use the Genie tool to query governed "
                    "data and answer clearly. Prefer concise, well-formatted answers."
                ),
                model=settings.reasoning_model,
                mcp_servers=[genie_server],
            )
            result = Runner.run_streamed(agent, user_text)
            async for event in result.stream_events():
                for raw in _translate(event):
                    yield raw


def _translate(event) -> list[dict]:
    """Map OpenAI Agents SDK stream events -> normalizer raw events.

    Kept as a pure function so it is unit-testable without network. The exact
    SDK event attribute names are confirmed against databricks_openai during
    Task 9 live smoke; adjust the attribute reads here if they differ.
    """
    etype = getattr(event, "type", None)
    out: list[dict] = []
    if etype == "raw_response_event":
        data = getattr(event, "data", None)
        delta = getattr(data, "delta", None)
        if delta:
            out.append({"type": "response.output_text.delta", "item_id": "msg", "delta": delta})
    elif etype == "run_item_stream_event":
        item = getattr(event, "item", None)
        itype = getattr(item, "type", None)
        if itype == "tool_call_item":
            out.append({"type": "response.output_item.done", "item_id": "tool",
                        "item": {"type": "function_call",
                                 "name": getattr(item, "name", "genie"),
                                 "arguments": str(getattr(item, "arguments", ""))}})
        elif itype == "tool_call_output_item":
            out.append({"type": "response.output_item.done", "item_id": "tool",
                        "item": {"type": "function_call_output",
                                 "call_id": getattr(item, "name", "genie"),
                                 "output": str(getattr(item, "output", ""))}})
        elif itype == "message_output_item":
            text = getattr(item, "raw_item", None)
            out.append({"type": "response.output_item.done", "item_id": "msg",
                        "item": {"type": "message",
                                 "content": [{"text": str(text) if text else ""}]}})
    return out
