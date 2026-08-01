import pytest

class _FakeIdentity:
    class _TS:
        def bearer_token(self): return "tok"
    token_source = _TS()
    auth_type = "pat"

@pytest.mark.asyncio
async def test_stream_emits_normalizer_compatible_events(monkeypatch):
    from agent.reasoning_agent import ReasoningAgent
    agent = ReasoningAgent()

    # Inject a fake token stream: one text delta then a message-done.
    async def fake_run_stream(identity, messages):
        yield {"type": "response.output_text.delta", "item_id": "1", "delta": "Hello"}
        yield {"type": "response.output_item.done", "item_id": "1",
               "item": {"type": "message", "content": [{"text": "Hello world"}]}}
    monkeypatch.setattr(agent, "_run_stream", fake_run_stream)

    seen = [ev async for ev in agent.stream(_FakeIdentity(), [{"role": "user", "content": "hi"}])]
    types = [e["type"] for e in seen]
    assert "response.output_text.delta" in types
    assert any(e["type"] == "response.output_item.done" for e in seen)

@pytest.mark.asyncio
async def test_stream_surfaces_errors_as_response_error(monkeypatch):
    from agent.reasoning_agent import ReasoningAgent
    agent = ReasoningAgent()
    async def boom(identity, messages):
        raise RuntimeError("kaboom")
        yield  # pragma: no cover
    monkeypatch.setattr(agent, "_run_stream", boom)
    seen = [ev async for ev in agent.stream(_FakeIdentity(), [])]
    assert seen and seen[-1]["type"] == "response.error"


class _E:  # minimal attribute stand-in for SDK events/items
    def __init__(self, **k): self.__dict__.update(k)


def test_translate_tool_call_reads_tool_name_and_arguments():
    from agent.reasoning_agent import _translate
    # openai-agents 0.18.x ToolCallItem exposes .tool_name (property), .arguments
    ev = _E(type="run_item_stream_event",
            item=_E(type="tool_call_item", tool_name="query_genie", arguments='{"q":"revenue"}'))
    out = _translate(ev)
    assert out[0]["item"]["type"] == "function_call"
    assert out[0]["item"]["name"] == "query_genie"
    assert out[0]["item"]["arguments"] == '{"q":"revenue"}'


def test_translate_tool_output_reads_call_id_and_output():
    from agent.reasoning_agent import _translate
    ev = _E(type="run_item_stream_event",
            item=_E(type="tool_call_output_item", call_id="call_123", output="42 rows"))
    out = _translate(ev)
    assert out[0]["item"]["type"] == "function_call_output"
    assert out[0]["item"]["call_id"] == "call_123"
    assert out[0]["item"]["output"] == "42 rows"


def test_translate_message_uses_content_text_fallback():
    from agent.reasoning_agent import _translate
    # No `agents` SDK installed here, so ItemHelpers import fails and we fall
    # back to walking raw_item.content -> concatenated .text parts.
    raw = _E(content=[_E(text="Hello "), _E(text="world")])
    ev = _E(type="run_item_stream_event", item=_E(type="message_output_item", raw_item=raw))
    out = _translate(ev)
    assert out[0]["item"]["type"] == "message"
    assert out[0]["item"]["content"][0]["text"] == "Hello world"


def test_translate_text_delta_guards_on_data_type():
    from agent.reasoning_agent import _translate
    # A real text delta is forwarded...
    good = _E(type="raw_response_event",
              data=_E(type="response.output_text.delta", delta="hi"))
    assert _translate(good)[0]["type"] == "response.output_text.delta"
    # ...but a non-text raw event carrying an unrelated .delta is NOT.
    other = _E(type="raw_response_event",
               data=_E(type="response.function_call_arguments.delta", delta="{"))
    assert _translate(other) == []
