# Genie MCP Reasoning, Visualization, Chainlit Upgrade & Cookbook Contribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `bi-hub-app` to Chainlit 2.11.1, add an in-app reasoning agent that calls the managed Genie MCP server directly as a tool, render Genie visualizations, and contribute a de-branded copy as the Lakebase Cookbook's `ai_memory/` example — PR by Monday 2026-08-03.

**Architecture:** The app hosts its own LLM tool-calling loop (Foundation Model API) with the managed Genie MCP server registered as a tool. **MAS and Genie One are first-class, user-selectable peer agents** — the existing agent-selector dropdown gains a per-entry `kind` (`"mas"` → `MASChatClient`, `"genie_one"` → in-app `ReasoningAgent`), and `on_message` dispatches on the selected agent's kind. The reasoning loop emits the existing normalized event contract (`text.delta/done`, `tool.call/output`), so `mas_normalizer`, the renderer, and the Lakebase/auth layers are reused unchanged. Genie visualizations (Beta) are fetched and rendered as Chainlit elements, with pipe-table rendering as fallback.

**Tech Stack:** Chainlit 2.11.1, Databricks SDK, `databricks-openai` (McpServer + OpenAI Agents SDK), Foundation Model API (`databricks-claude-sonnet-4-5`), SQLAlchemy + psycopg (Lakebase), Plotly, uv + ruff, Databricks Asset Bundles (DABs), Astro (cookbook site).

## Global Constraints

- Chainlit version floor: **2.11.1** (currently 2.7.2). Same 2.x line.
- App uses the built-in `SQLAlchemyDataLayer` (no custom `BaseDataLayer` subclass) — the 2.8.2 `async close()` breaking change does NOT apply to app code.
- Genie MCP server URL (space-scoped): `https://{host}/api/2.0/mcp/genie/{genie_space_id}`. OBO auth requires the `genie` OAuth scope.
- Genie viz download endpoint: `GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/download-visualization`. Start conversation with `enable_visualization: true`. **Beta.** Not supported on Private Link workspaces or certain Azure regions.
- Reasoning-agent LLM defaults to `databricks-claude-sonnet-4-5` (a DAB variable, overridable).
- Reuse existing `Identity`/OBO/PAT auth. No auth rewrite.
- Preserve the normalized event contract exactly:
  - `{"type":"text.delta","item_id":str,"delta":str}`
  - `{"type":"text.done","item_id":str,"text":str}`
  - `{"type":"tool.call","item_id":str,"name":str,"args":str}`
  - `{"type":"tool.output","item_id":str,"name":str,"output":str}`
- Branch from a clean `main` as `feature/genie-mcp-reasoning`. Leave `feature/enhance-ux` uncommitted work untouched.
- **No commits or pushes without explicit user approval.** (Overrides the per-task "Commit" steps below — stage/prepare, but ask before committing.)
- Cookbook rules: `uv` (`pyproject.toml`, not pip), `ruff` clean, DABs, no secrets (`.env.example` placeholders only), every workspace-specific value is a DAB variable with a default, small/cheap compute, no emojis in doc pages, `make build` must pass.
- MAS and Genie One are **peer, user-selectable agents** (not fallback). Each agent-selector entry has a `kind`: `"mas"` or `"genie_one"`. A deployment may expose one or both.
- De-scope ladder (shed in order if time-constrained; cookbook PR is the floor):
  1. Drop Genie viz (Beta) → document as v2 fast-follow, keep table rendering.
  2. Drop the Genie One agent → selector lists MAS entries only; no code path removed (degrades cleanly to MAS-only).
  3. Never drop: Chainlit upgrade + restructure + de-brand + cookbook PR with clean-checkout deploy.

---

## File Structure

**`bi-hub-app` (source of truth), `src/app/`:**
- `agent/genie_mcp.py` — CREATE. Managed Genie MCP client (URL build, OBO auth, `McpServer` context).
- `agent/reasoning_agent.py` — CREATE. LLM tool-calling loop; yields normalized events.
- `agent/__init__.py` — CREATE.
- `services/viz.py` — CREATE. Fetch + build Chainlit element from a Genie viz attachment.
- `services/renderer.py` — MODIFY. Add viz element handling; verify `cl.Dataframe` arg name for 2.11.
- `services/mas_client.py` — KEEP (fallback path).
- `services/mas_normalizer.py` — REUSE unchanged (agent emits same shapes).
- `memory/{layer,lakebase,credentials}.py` — RENAME from `data/`; update imports.
- `routes.py` — MODIFY. Route to reasoning agent (with MAS fallback toggle).
- `config.py` — MODIFY. Add Genie space/MCP/viz/agent-model settings.
- `requirements.txt` → `pyproject.toml` (cookbook copy uses uv; bi-hub-app keeps requirements.txt + bumps pins).

**Cookbook (`lakebase-cookbook/ai_memory/`):** de-branded copy + `README.md`, `databricks.yml`, `resources/*.yml`, `pyproject.toml`, `.gitignore`, `.env.example`; plus `site/src/content/docs/examples/ai-memory.mdx`, edits to `site/src/data/examples.ts` and `site/src/content/docs/intro.md`.

---

## Phase 0 — Branch & baseline

### Task 0: Create working branch and confirm baseline runs

**Files:** none (git + local run).

- [ ] **Step 1: Confirm clean main and stash safety**

```bash
cd /Users/rohit.bhagwat/Documents/github/bi-hub-app/bi-hub-app
git stash list            # note: feature/enhance-ux has uncommitted work — do NOT touch it
git status -s             # confirm which branch we're on
```
Expected: aware of uncommitted changes on `feature/enhance-ux`.

- [ ] **Step 2: Branch from a clean main**

```bash
git fetch origin
git checkout -b feature/genie-mcp-reasoning origin/main
```
Expected: new branch off `main`; the `feature/enhance-ux` uncommitted work remains on its own branch, untouched.

- [ ] **Step 3: Baseline smoke (optional, if env available)**

Run: `cd src/app && chainlit run app.py -w`
Expected: app starts on 2.7.2 (documents the pre-upgrade baseline).

- [ ] **Step 4: STOP — ask user before any commit.** (Per Global Constraints.)

---

## Phase 1 — Chainlit upgrade (never-drop)

### Task 1: Bump Chainlit to 2.11.1 and verify the data layer + rendering API

**Files:**
- Modify: `src/app/requirements.txt:1`
- Test: `src/app/tests/test_data_layer_smoke.py` (create)

**Interfaces:**
- Consumes: `memory.lakebase.create_chainlit_data_layer()` (renamed in Task 2; for this task it is still `data.lakebase.create_chainlit_data_layer()`).
- Produces: confirmed-working `SQLAlchemyDataLayer` + `do_connect` OAuth hook on 2.11.1.

- [ ] **Step 1: Write a failing smoke test for the data layer construction**

```python
# src/app/tests/test_data_layer_smoke.py
import chainlit  # noqa: F401

def test_chainlit_version_floor():
    from importlib.metadata import version
    assert tuple(int(x) for x in version("chainlit").split(".")[:2]) >= (2, 11)

def test_sqlalchemy_data_layer_importable():
    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer  # noqa: F401
    assert hasattr(SQLAlchemyDataLayer, "close")  # 2.8.2+ base API
```

- [ ] **Step 2: Run to verify it fails on 2.7.2**

Run: `cd src/app && python -m pytest tests/test_data_layer_smoke.py -v`
Expected: `test_chainlit_version_floor` FAILS (2.7 < 2.11).

- [ ] **Step 3: Bump the pin**

Edit `src/app/requirements.txt` line 1: `chainlit==2.7.2` → `chainlit==2.11.1`.

- [ ] **Step 4: Reinstall and run the tests**

Run: `cd src/app && pip install -r requirements.txt && python -m pytest tests/test_data_layer_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the `cl.Dataframe` argument name (breaking-change check)**

Run: `cd src/app && python -c "import chainlit as cl, inspect; print(inspect.signature(cl.Dataframe.__init__))"`
Expected: note whether the arg is `data=` (current docs) vs `df=` (used in `renderer.py:106`). If it changed, record it — fixed in Task 6.

- [ ] **Step 6: Manual smoke (if env available)**

Run: `chainlit run app.py -w` → send a message → confirm streaming works, a thread is created in Lakebase, and refresh/resume (`@cl.on_chat_resume`) restores history.
Expected: persistence + resume intact on 2.11.1.

- [ ] **Step 7: Prepare commit (ASK FIRST).**

```bash
git add src/app/requirements.txt src/app/tests/test_data_layer_smoke.py
# git commit -m "chore: upgrade chainlit 2.7.2 -> 2.11.1; add data-layer smoke tests"
```

---

## Phase 2 — Restructure (never-drop)

### Task 2: Rename `data/` → `memory/` and update imports

**Files:**
- Rename: `src/app/data/` → `src/app/memory/` (`layer.py`, `lakebase.py`, `credentials.py`, `__init__.py`; drop `lakebase_example.py` from the cookbook copy later)
- Modify: any file importing `from data.` — currently `src/app/memory/layer.py` (`from .lakebase`), `src/app/memory/lakebase.py` (`from data.credentials import LakebaseCredentialProvider` → `from memory.credentials`), and any `app.py`/`routes.py` references.
- Test: `src/app/tests/test_imports.py` (create)

**Interfaces:**
- Produces: `memory.lakebase.create_chainlit_data_layer()`, `memory.credentials.LakebaseCredentialProvider`, `memory.layer.get_data_layer` (module import registers `@cl.data_layer`).

- [ ] **Step 1: Write a failing import test**

```python
# src/app/tests/test_imports.py
def test_memory_module_imports():
    from memory.lakebase import create_chainlit_data_layer  # noqa: F401
    from memory.credentials import LakebaseCredentialProvider  # noqa: F401
    import memory.layer  # noqa: F401
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd src/app && python -m pytest tests/test_imports.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'memory'`).

- [ ] **Step 3: Rename the directory and fix internal imports**

```bash
cd src/app && git mv data memory
```
Then edit `memory/lakebase.py`: `from data.credentials import LakebaseCredentialProvider` → `from memory.credentials import LakebaseCredentialProvider`. Grep for other `data.` / `from data` references and update:
Run: `grep -rn "from data" src/app --include=*.py; grep -rn "import data" src/app --include=*.py`

- [ ] **Step 4: Run the import test**

Run: `cd src/app && python -m pytest tests/test_imports.py -v`
Expected: PASS.

- [ ] **Step 5: Confirm the app still boots (import-time only)**

Run: `cd src/app && python -c "import routes"` (imports config, memory.layer, services — surfaces any missed rename).
Expected: no ImportError.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

```bash
git add -A src/app
# git commit -m "refactor: rename data/ -> memory/ to headline the Lakebase agent-memory story"
```

---

## Phase 3 — Config for Genie MCP + viz + agent model (never-drop scaffolding)

### Task 3: Add settings for Genie space, MCP, visualization, and agent model

**Files:**
- Modify: `src/app/config.py` (add fields ~line 42; add env wiring ~line 90)
- Test: `src/app/tests/test_config.py` (create)

**Interfaces:**
- Produces on `settings`: `genie_space_id: Optional[str]`, `reasoning_model: str` (default `"databricks-claude-sonnet-4-5"`), `enable_visualization: bool` (default `False`), and a property `genie_mcp_url -> str` = `f"{host}/api/2.0/mcp/genie/{genie_space_id}"` using the same host normalization as `agent_base_url`.
- Extends `available_agents` entries with an optional `kind` key: `"mas"` (default when absent) or `"genie_one"`. Each entry is `{"name", "kind", "endpoint"?, "genie_space_id"?}`. MAS entries carry `endpoint`; Genie One entries carry `genie_space_id`. This makes MAS and Genie One peer, user-selectable agents.

- [ ] **Step 1: Write failing config tests**

```python
# src/app/tests/test_config.py
import os

def _fresh_settings(**env):
    for k, v in env.items():
        os.environ[k] = v
    import importlib, config
    importlib.reload(config)
    return config.settings

def test_genie_mcp_url_built():
    s = _fresh_settings(
        DATABRICKS_HOST="myws.cloud.databricks.com",
        GENIE_SPACE_ID="01efabc",
        ENABLE_PASSWORD_AUTH="true",
    )
    assert s.genie_mcp_url == "https://myws.cloud.databricks.com/api/2.0/mcp/genie/01efabc"

def test_reasoning_defaults():
    s = _fresh_settings(DATABRICKS_HOST="h", ENABLE_PASSWORD_AUTH="true")
    assert s.reasoning_model == "databricks-claude-sonnet-4-5"
    assert s.enable_visualization is False

def test_available_agents_support_kind():
    s = _fresh_settings(
        DATABRICKS_HOST="h", ENABLE_PASSWORD_AUTH="true",
        AVAILABLE_AGENTS='[{"name":"MAS","kind":"mas","endpoint":"ep1"},'
                         '{"name":"Genie One","kind":"genie_one","genie_space_id":"sp1"}]',
    )
    kinds = {a["name"]: a.get("kind", "mas") for a in s.available_agents}
    assert kinds == {"MAS": "mas", "Genie One": "genie_one"}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_config.py -v`
Expected: FAIL (attributes/property missing).

- [ ] **Step 3: Add the fields and property to `Settings`**

In `config.py`, inside `Settings` (after the serving-endpoint block):

```python
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
```

Note: `available_agents` already exists as `List[Dict[str, str]]`; entries now
optionally carry `kind`/`genie_space_id`. No type change required (values stay
strings). Absent `kind` defaults to `"mas"` at read time.

- [ ] **Step 4: Wire env vars**

In the `env_vars` dict:

```python
    'genie_space_id': os.getenv("GENIE_SPACE_ID"),
    'reasoning_model': os.getenv("REASONING_MODEL"),
    'enable_visualization': os.getenv("ENABLE_VISUALIZATION"),
```

- [ ] **Step 5: Run the config tests**

Run: `cd src/app && python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 4 — Genie MCP client (drop-2 boundary: enables 1b)

### Task 4: Genie MCP client wrapper

**Files:**
- Create: `src/app/agent/genie_mcp.py`, `src/app/agent/__init__.py`
- Test: `src/app/tests/test_genie_mcp.py`

**Interfaces:**
- Consumes: `config.settings.genie_mcp_url_for(space_id)`, `config.settings.genie_space_id`, `auth.identity.Identity` (has `token_source.bearer_token()`).
- Produces: `class GenieMCP` constructed as `GenieMCP(space_id: Optional[str] = None)` (falls back to `settings.genie_space_id`), with `def url(self) -> str`, `def is_configured(self) -> bool`, and an async context manager `async def server(self, identity)` yielding a `databricks_openai.agents.McpServer` bound to the OBO/PAT bearer. Per-selection `space_id` lets multiple Genie One entries point at different spaces.

- [ ] **Step 1: Write a failing unit test (no network — test URL + config guard)**

```python
# src/app/tests/test_genie_mcp.py
def test_is_configured_false_without_space(monkeypatch):
    import config, importlib
    monkeypatch.delenv("GENIE_SPACE_ID", raising=False)
    importlib.reload(config)
    from agent.genie_mcp import GenieMCP
    assert GenieMCP().is_configured() is False

def test_url_uses_settings(monkeypatch):
    import config, importlib
    monkeypatch.setenv("DATABRICKS_HOST", "h.databricks.com")
    monkeypatch.setenv("GENIE_SPACE_ID", "sp1")
    monkeypatch.setenv("ENABLE_PASSWORD_AUTH", "true")
    importlib.reload(config)
    from agent.genie_mcp import GenieMCP
    assert GenieMCP().url().endswith("/api/2.0/mcp/genie/sp1")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_genie_mcp.py -v`
Expected: FAIL (`No module named 'agent'`).

- [ ] **Step 3: Implement the client**

```python
# src/app/agent/genie_mcp.py
from __future__ import annotations
from contextlib import asynccontextmanager
from config import settings
from utils.logging import logger


class GenieMCP:
    """Wraps the managed Genie MCP server as an agent tool source.

    URL: https://{host}/api/2.0/mcp/genie/{space_id}
    Auth: OBO/PAT bearer via Identity; OBO requires the `genie` scope.
    space_id defaults to settings.genie_space_id but can be passed per selection
    so multiple Genie One agents can target different spaces.
    """

    def __init__(self, space_id: str | None = None) -> None:
        self._space_id = space_id or settings.genie_space_id

    def url(self) -> str:
        return settings.genie_mcp_url_for(self._space_id)

    def is_configured(self) -> bool:
        return bool(self._space_id)

    @asynccontextmanager
    async def server(self, identity):
        from databricks.sdk import WorkspaceClient
        from databricks_openai.agents import McpServer

        bearer = identity.token_source.bearer_token()
        if not bearer:
            raise RuntimeError("Missing bearer token for Genie MCP")
        wc = WorkspaceClient(host=settings.databricks_host, token=bearer)
        logger.info(f"Opening Genie MCP server at {self.url()}")
        async with McpServer(url=self.url(), name="genie-space", workspace_client=wc) as srv:
            yield srv
```

- [ ] **Step 4: Run the tests**

Run: `cd src/app && python -m pytest tests/test_genie_mcp.py -v`
Expected: PASS. (Network-dependent `server()` is covered by the live smoke test in Task 9, not unit tests.)

- [ ] **Step 5: Prepare commit (ASK FIRST).**

---

## Phase 5 — Reasoning agent loop (drop-2 boundary: the core of 1b)

### Task 5: In-app reasoning agent that emits normalized events

**Files:**
- Create: `src/app/agent/reasoning_agent.py`
- Test: `src/app/tests/test_reasoning_agent.py`

**Interfaces:**
- Consumes: `agent.genie_mcp.GenieMCP`, `config.settings.reasoning_model`, `auth.identity.Identity`.
- Produces: `class ReasoningAgent` constructed as `ReasoningAgent(space_id: Optional[str] = None)` (passed to `GenieMCP`), with
  `async def stream(self, identity, messages: list[dict]) -> AsyncIterator[dict]`
  yielding RAW events shaped like the OpenAI/MAS SDK events that `mas_normalizer.normalize` already consumes (`response.output_text.delta`, `response.output_item.done` with `item.type in {message, function_call, function_call_output}`, `response.error`). This lets `routes.py` keep calling `normalize(...)` unchanged.

- [ ] **Step 1: Write a failing test with a fake runner (no network)**

```python
# src/app/tests/test_reasoning_agent.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_reasoning_agent.py -v`
Expected: FAIL (module missing). Ensure `pytest-asyncio` is available (add to a dev section of requirements if needed).

- [ ] **Step 3: Implement the agent**

```python
# src/app/agent/reasoning_agent.py
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
        from agents import Agent, Runner  # OpenAI Agents SDK

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
```

- [ ] **Step 4: Run the tests**

Run: `cd src/app && python -m pytest tests/test_reasoning_agent.py -v`
Expected: PASS (fake `_run_stream` bypasses network; error path verified).

- [ ] **Step 5: Add a unit test for `_translate`**

```python
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
```

Run: `cd src/app && python -m pytest tests/test_reasoning_agent.py::test_translate_tool_call_and_message -v`
Expected: PASS.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 6 — Wire agent selection into routes: MAS + Genie One as peers (drop-2 boundary)

### Task 6: Dispatch on the selected agent's `kind`; verify renderer on 2.11

**Files:**
- Modify: `src/app/routes.py` — `on_chat_start` (~89-112), `on_settings_update` (~114-123), `on_message` (~126-154)
- Modify: `src/app/services/renderer.py:106` (if `cl.Dataframe` arg changed per Task 1 Step 5)
- Test: `src/app/tests/test_routes_dispatch.py`

**Interfaces:**
- Consumes: `agent.reasoning_agent.ReasoningAgent.stream`, `services.mas_client.MASChatClient.stream_raw`, `services.mas_normalizer.normalize`, `config.settings.available_agents` (each with `kind`).
- Produces: a module-level `_raw_events_for(agent_cfg, identity, messages)` that returns the raw-event iterator for the selected agent — `MASChatClient.stream_raw(...)` when `kind == "mas"`, `ReasoningAgent(space_id).stream(...)` when `kind == "genie_one"`. Both feed `normalize(...)` → renderer unchanged. The session stores the full selected agent dict (`cl.user_session["agent"]`), not just an endpoint string.

- [ ] **Step 1: Write a failing dispatch test**

```python
# src/app/tests/test_routes_dispatch.py
def _reload(monkeypatch, agents_json):
    import importlib, config
    monkeypatch.setenv("ENABLE_PASSWORD_AUTH", "true")
    monkeypatch.setenv("DATABRICKS_HOST", "h")
    monkeypatch.setenv("AVAILABLE_AGENTS", agents_json)
    importlib.reload(config)
    import routes, importlib as il; il.reload(routes)
    return routes

class _Id:
    class _TS:
        def bearer_token(self): return "tok"
    token_source = _TS(); auth_type = "pat"

def test_dispatch_mas(monkeypatch):
    routes = _reload(monkeypatch, '[{"name":"MAS","kind":"mas","endpoint":"ep1"}]')
    it = routes._raw_events_for({"name":"MAS","kind":"mas","endpoint":"ep1"}, _Id(), [])
    assert hasattr(it, "__aiter__")  # async iterator returned

def test_dispatch_genie_one(monkeypatch):
    routes = _reload(monkeypatch,
        '[{"name":"Genie One","kind":"genie_one","genie_space_id":"sp1"}]')
    it = routes._raw_events_for(
        {"name":"Genie One","kind":"genie_one","genie_space_id":"sp1"}, _Id(), [])
    assert hasattr(it, "__aiter__")

def test_unknown_kind_defaults_to_mas(monkeypatch):
    routes = _reload(monkeypatch, '[{"name":"Legacy","endpoint":"ep2"}]')
    # no "kind" key -> treated as mas, must not raise
    routes._raw_events_for({"name":"Legacy","endpoint":"ep2"}, _Id(), [])
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_routes_dispatch.py -v`
Expected: FAIL (`_raw_events_for` undefined).

- [ ] **Step 3: Add the dispatcher and store the selected agent**

At module scope in `routes.py`:

```python
from agent.reasoning_agent import ReasoningAgent

def _raw_events_for(agent_cfg: dict, identity, messages: list[dict]):
    """Return the raw-event async iterator for the selected agent.
    kind 'genie_one' -> in-app ReasoningAgent + Genie MCP; else MAS."""
    kind = (agent_cfg or {}).get("kind", "mas")
    if kind == "genie_one":
        return ReasoningAgent(agent_cfg.get("genie_space_id")).stream(identity, messages)
    return mas_client.stream_raw(identity, messages, endpoint=agent_cfg.get("endpoint"))
```

In `on_chat_start`, store the whole first agent dict (not just its endpoint):

```python
        cl.user_session.set("agent", settings.available_agents[0])
```

In `on_settings_update`, look up the selected agent dict by name and store it:

```python
        by_name = {a["name"]: a for a in settings.available_agents}
        selected = by_name.get(settings_dict["Agent"])
        if selected:
            cl.user_session.set("agent", selected)
            await cl.Message(content=f"Switched to **{selected['name']}**").send()
```

In `on_message`, replace the source line with:

```python
    agent_cfg = cl.user_session.get("agent") or (
        settings.available_agents[0] if settings.available_agents else {"kind": "mas"}
    )
    raw_events = _raw_events_for(agent_cfg, identity, messages)
    async for event in normalize(raw_events):
        ...  # unchanged event handling
```

- [ ] **Step 4: Fix `cl.Dataframe` arg if needed**

If Task 1 Step 5 showed the arg is `data=`, change `renderer.py:106` from `cl.Dataframe(df=df, name="Results")` to `cl.Dataframe(data=df, name="Results")`.

- [ ] **Step 5: Run the dispatch tests**

Run: `cd src/app && python -m pytest tests/test_routes_dispatch.py -v`
Expected: PASS (all three: mas, genie_one, unknown-kind-defaults-to-mas).

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 7 — Genie visualization (DROP-FIRST; flag-gated)

### Task 7: Fetch and render Genie viz attachments

**Files:**
- Create: `src/app/services/viz.py`
- Modify: `src/app/services/renderer.py` (emit viz element when present)
- Test: `src/app/tests/test_viz.py`

**Interfaces:**
- Consumes: `config.settings.enable_visualization`, `auth.identity.Identity`.
- Produces: `async def fetch_visualization(identity, space_id, conversation_id, message_id, attachment_id) -> bytes | dict` and `def to_element(viz_payload) -> cl.Plotly | cl.Image`. Gated by `settings.enable_visualization`.

- [ ] **Step 1: Write failing tests (element building, no network)**

```python
# src/app/tests/test_viz.py
def test_to_element_plotly_from_figure_json():
    from services.viz import to_element
    fig_json = '{"data":[{"type":"bar","y":[1,2,3]}],"layout":{}}'
    el = to_element({"kind": "plotly", "figure_json": fig_json})
    assert el.__class__.__name__ == "Plotly"

def test_to_element_image_from_bytes():
    from services.viz import to_element
    el = to_element({"kind": "image", "content": b"\x89PNG..."})
    assert el.__class__.__name__ == "Image"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_viz.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `viz.py`**

```python
# src/app/services/viz.py
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

async def fetch_visualization(identity, space_id, conversation_id, message_id, attachment_id) -> dict:
    """Download a Genie viz attachment (Beta). Returns a normalized payload
    dict: {"kind":"plotly","figure_json":...} or {"kind":"image","content":bytes}."""
    bearer = identity.token_source.bearer_token()
    host = settings.databricks_host
    base = host if host.startswith("https://") else f"https://{host}"
    url = base + _VIZ_PATH.format(space_id=space_id, conversation_id=conversation_id,
                                  message_id=message_id, attachment_id=attachment_id)
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(url, headers={"Authorization": f"Bearer {bearer}"})
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "json" in ctype:
            return {"kind": "plotly", "figure_json": r.text}
        return {"kind": "image", "content": r.content}

def to_element(viz_payload: dict):
    if viz_payload.get("kind") == "plotly":
        fig = pio.from_json(viz_payload["figure_json"])
        return cl.Plotly(name="Chart", figure=fig, display="inline")
    return cl.Image(name="Chart", content=viz_payload["content"], display="inline")
```

- [ ] **Step 4: Add a renderer hook to attach a viz element**

In `ChainlitStream`, add:

```python
    async def on_visualization(self, element):
        if self.text_msg is None:
            self.text_msg = cl.Message(content=" ")
            await self.text_msg.send()
        self.text_msg.elements = [element]
        await self.text_msg.update()
```

- [ ] **Step 5: Run the tests**

Run: `cd src/app && python -m pytest tests/test_viz.py -v`
Expected: PASS.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

> **De-scope note:** if the Beta viz path is unstable during Task 9 live smoke, set `enable_visualization=false` (default) and document viz as a v2 fast-follow. Table rendering remains the default.

---

## Phase 8 — DAB variables + de-brand (never-drop)

### Task 8: Parameterize workspace-specific values and strip branding (bi-hub-app)

**Files:**
- Modify: `databricks.yml`, `src/app/app.yaml`, `src/app/.chainlit/config.toml`
- Modify/remove: `config.py` hardcoded `available_agents` default (Alaska/`mas-3a71922a-endpoint`), `chat_starter_messages` (airline-specific)
- Test: `src/app/tests/test_no_hardcoded_ids.py`

**Interfaces:**
- Produces: no workspace-specific constants in code; all via env/DAB variables.

- [ ] **Step 1: Write a failing guard test**

```python
# src/app/tests/test_no_hardcoded_ids.py
import pathlib, re
def test_no_hardcoded_endpoint_or_space():
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = re.compile(r"mas-[0-9a-f]{8}-endpoint|01ef[0-9a-f]{6,}")
    hits = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts: continue
        if bad.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(str(p))
    assert not hits, f"hardcoded ids in: {hits}"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/app && python -m pytest tests/test_no_hardcoded_ids.py -v`
Expected: FAIL (`config.py` has `mas-3a71922a-endpoint`).

- [ ] **Step 3: Move defaults to env; neutralize starters and agents**

In `config.py`, change the `available_agents` default to `[]` and make starters generic (non-airline). Ensure all IDs come from env (`SERVING_ENDPOINT`, `GENIE_SPACE_ID`, etc.).

- [ ] **Step 4: Parameterize `databricks.yml`**

Add `variables:` for `lakebase_database`, `genie_space_id`, `serving_endpoint`, `reasoning_model`, `catalog`, `schema`, `warehouse_id`, each with a sensible default; reference them in `resources/*.yml`. (Cookbook §3.)

- [ ] **Step 5: Run the guard test**

Run: `cd src/app && python -m pytest tests/test_no_hardcoded_ids.py -v`
Expected: PASS.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 9 — Verify in bi-hub-app (never-drop; the guide's gate)

### Task 9: Live deploy + smoke test against the user's workspace

**Files:** none (deploy + manual verification). **Requires the user's workspace (MAS + Lakebase + a Genie space).**

- [ ] **Step 1: Validate the bundle**

Run: `databricks bundle validate -t <target> --profile <profile>`
Expected: valid.

- [ ] **Step 2: Deploy from clean checkout**

Run: `databricks bundle deploy -t <target> --profile <profile>` then `databricks bundle run <app> -t <target>`.
Expected: app deploys and starts.

- [ ] **Step 3: Live smoke test — both agents**

- With a **MAS** agent selected: send a BI question → confirm streaming text and existing behavior unchanged.
- Switch to the **Genie One** agent via the selector → send a BI question → confirm a Genie MCP `tool.call` / `tool.output` appears in the status block and an answer streams.
- If `enable_visualization=true`: confirm a chart renders; else confirm table rendering.
- Refresh → confirm the thread persists and resumes from Lakebase (for both agent kinds).

- [ ] **Step 4: Adjust `_translate` attribute reads if SDK event shapes differ.** Re-run `tests/test_reasoning_agent.py`.

- [ ] **Step 5: Decide de-scope.** If viz is unstable, set `enable_visualization=false` and document viz as v2. If the Genie One path is unstable, ship with only MAS entries in `available_agents` (no `genie_one` entry) — no code removed. Cookbook PR proceeds regardless.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 10 — Cookbook example folder (never-drop)

### Task 10: Create the de-branded `ai_memory/` example (uv + DABs + no secrets)

**Files (in `lakebase-cookbook/`):**
- Create: `ai_memory/README.md`, `ai_memory/databricks.yml`, `ai_memory/resources/chatbot.app.yml`, `ai_memory/pyproject.toml`, `ai_memory/.gitignore`, `ai_memory/.env.example`, `ai_memory/src/app/**` (copied + de-branded from bi-hub-app).
- Reference: `lakebase-cookbook/CONTRIBUTING.md`, `lakebase-cookbook/genie_caching/` (structure), the repo's `.claude/skills/scaffold-lakebase-example`.

- [ ] **Step 1: Open the draft PR / issue first (guide §0).**

```bash
cd /Users/rohit.bhagwat/Documents/github/lakebase-cookbook
gh repo fork --remote  # if not already forked
git checkout -b example/ai-memory
# open a draft PR describing the example so a maintainer can confirm fit (ASK before pushing)
```

- [ ] **Step 2: Invoke the repo's scaffold skill.**

Use the cookbook's `scaffold-lakebase-example` skill (or copy `genie_caching/`'s file shapes) to create `ai_memory/` with the required files.

- [ ] **Step 3: Copy + de-brand the app.**

Copy `bi-hub-app/src/app/**` (post-restructure) into `ai_memory/src/app/`, dropping `memory/lakebase_example.py`, synthetic-data generators, and customer branding assets. Replace `requirements.txt` with a `pyproject.toml` (uv) pinning `chainlit==2.11.1` and deps.

- [ ] **Step 4: Parameterize everything as DAB variables** (Lakebase path, genie_space_id, serving/reasoning model, catalog, schema, warehouse). Provide `.env.example` with placeholder keys only; ensure real `.env`/`.databricks` are gitignored.

- [ ] **Step 5: Lint.**

Run: `cd ai_memory && uv run ruff check . && uv run ruff format .`
Expected: clean.

- [ ] **Step 6: Verify deploy from clean checkout** (guide §3) against the workspace — same smoke test as Task 9, from the cookbook copy.

- [ ] **Step 7: Prepare commit (ASK FIRST).**

---

## Phase 11 — Cookbook docs + site (never-drop)

### Task 11: README, doc page, and site wiring

**Files (in `lakebase-cookbook/`):**
- Create: `ai_memory/README.md` (§2 structure).
- Create: `site/src/content/docs/examples/ai-memory.mdx`.
- Modify: `site/src/data/examples.ts` (AI Memory entry `status: 'soon'` → `'ready'`).
- Modify: `site/src/content/docs/intro.md` (add table row).

- [ ] **Step 1: Write `ai_memory/README.md`** with: title + one-paragraph summary; features table; ASCII architecture + data flow (who talks to Lakebase); copy-pasteable DAB deploy; configuration table (every variable); local dev.

- [ ] **Step 2: Write `ai-memory.mdx`** — styled mirror; frontmatter (`title`, `sidebar_label`, `sidebar_position` slotting near the other agent examples, `description`); import `Callout`; **no emojis**; end with a Source `<Callout>` linking to `ai_memory/`.

- [ ] **Step 3: Flip the landing/index entry.** In `site/src/data/examples.ts`, change the `AI Memory` card `status: 'soon'` → `'ready'` and update `bracket`/`description` to reflect Chainlit + Genie MCP + Lakebase memory.

- [ ] **Step 4: Add the `intro.md` table row.**

- [ ] **Step 5: Build the site (the gate).**

```bash
cd /Users/rohit.bhagwat/Documents/github/lakebase-cookbook
make install   # one-time
make dev       # eyeball page + sidebar at localhost:3000
make build     # MUST succeed
```
Expected: `make build` passes with no errors.

- [ ] **Step 6: Prepare commit (ASK FIRST).**

---

## Phase 12 — Finalize PR (never-drop)

### Task 12: PR description + checklist

**Files:** PR on `databricks-solutions/lakebase-cookbook`.

- [ ] **Step 1: Assemble the PR description** — what the example demonstrates and the Lakebase capability (durable agent/conversation memory); confirmation of clean-checkout deploy; confirmation `make build` passes; prerequisites (Apps, a Genie space, a Lakebase project, MAS optional).

- [ ] **Step 2: Complete the guide's PR checklist** (§6) — all boxes.

- [ ] **Step 3: Isaac Review reminder.** These changes haven't been reviewed with Isaac Review yet — offer `/review` before pushing/finalizing the PR.

- [ ] **Step 4: STOP — ask the user before pushing or converting draft → ready.**

---

## Self-Review

**Spec coverage:** Chainlit upgrade → Task 1; restructure/rename → Task 2; config (incl. `kind`-tagged agents) → Task 3; Genie MCP tool → Tasks 4–5; MAS + Genie One peer routing → Task 6; viz (Beta, drop-first) → Task 7; DAB variables + de-brand → Task 8; clean-checkout deploy gate → Tasks 9 & 10.6; cookbook folder → Task 10; docs/site → Task 11; PR → Task 12. De-scope ladder is encoded via phase ordering + the drop notes in Tasks 6/7 and Task 9 Step 5. All spec sections map to tasks.

**Placeholder scan:** No "TBD/TODO/handle edge cases". The one deliberately deferred detail — exact OpenAI Agents SDK stream-event attribute names in `_translate` — is isolated in a pure, unit-tested function with an explicit Task 9 Step 4 verification, rather than a vague "handle events" instruction.

**Type consistency:** `GenieMCP(space_id).url()/is_configured()/server()` used consistently in Tasks 4–6. `ReasoningAgent(space_id).stream()` emits the exact raw event shapes `normalize()` consumes (verified against `mas_normalizer.py`). `settings.genie_mcp_url`/`genie_mcp_url_for`, `enable_visualization`, `reasoning_model` defined in Task 3 and consumed in Tasks 4/6/7. Agent dispatch is by `agent_cfg["kind"]` (default `"mas"`) — consistent across `config.available_agents` (Task 3), `_raw_events_for` (Task 6), and the live smoke test (Task 9). `to_element()`/`fetch_visualization()` consistent within Task 7. Note: the boolean `use_reasoning_agent` was removed in favor of the peer-agent `kind` model per the mid-flight requirement change.
