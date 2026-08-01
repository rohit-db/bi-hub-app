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


def test_translate_tool_call_and_message():
    from agent.reasoning_agent import _translate
    class E:  # minimal stand-ins
        def __init__(self, **k): self.__dict__.update(k)
    tool = E(type="run_item_stream_event",
             item=E(type="tool_call_item", name="genie", arguments="{}"))
    msg = E(type="run_item_stream_event",
            item=E(type="message_output_item", raw_item="hi"))
    assert _translate(tool)[0]["item"]["type"] == "function_call"
    assert _translate(msg)[0]["item"]["type"] == "message"
