# BI Hub App — Genie MCP Reasoning, Visualization, Chainlit Upgrade & Lakebase Cookbook Contribution

**Date:** 2026-07-31
**Author:** Rohit Bhagwat
**Status:** Draft for review
**Hard deadline:** PR to `databricks-solutions/lakebase-cookbook` by Monday 2026-08-03 (Grant Doyle presents to the manufacturing org Wednesday 2026-08-05).

---

## 1. Background & motivation

The `bi-hub-app` is a Databricks App built with Chainlit that provides a chat
interface for BI analytics. Today it integrates with a Multi-Agent Supervisor
(MAS) serving endpoint for reasoning and uses Lakebase (PostgreSQL) via the
Chainlit data layer for session state and chat history.

Grant Doyle (FE Innovation Program) wants to feature the app in the
[Lakebase Cookbook](https://lakebase-cookbook.com) as a reference pattern for
**agentic / conversation memory**. The cookbook already advertises an
`ai_memory/` example with `status: 'soon'` and a `# todo` README — this work
fills that slot.

Alongside the contribution, we are upgrading the real `bi-hub-app` repo and
adding two new capabilities that are now supported:

- **Genie visualization via the Conversation API** (Beta, announced 2026-07-02):
  retrieve chart/visualization results, not just tabular data.
- **Genie Managed MCP Server** ("Genie One", GA 2026-05-28): call Genie directly
  as a tool from a reasoning agent for grounded NL→data.

## 2. Goals

1. Upgrade `bi-hub-app` to Chainlit 2.11.1 (from 2.7.2) and restructure for
   clarity/modularity.
2. Add a reasoning agent **hosted in the app** that calls the managed Genie MCP
   server directly as a tool — offered as a **first-class, user-selectable
   agent alongside MAS** (both supported; the user picks per session via the
   existing agent selector). Not a fallback: MAS and Genie One are peers.
3. Render Genie visualizations (Beta) in the Chainlit UI, with table rendering
   as fallback.
4. Contribute a de-branded copy as the cookbook's `ai_memory/` example, with a
   working DAB deploy verified from a clean checkout, plus the required site
   doc page — PR by Monday.

## 3. Non-goals (YAGNI)

- No auth rewrite — reuse existing `Identity`/OBO/PAT plumbing.
- No changes to the original repo's customer branches (qvc, lce, ferguson, etc.).
- No new persistence features beyond what the Lakebase data layer already does.
- The cookbook copy does not include synthetic-data generators or customer
  branding.

## 4. Verified ground truth (as of 2026-07-31)

| Item | Finding |
|------|---------|
| Chainlit latest | **2.11.1** — same 2.x line as current 2.7.2 (minor bump, not a major migration). |
| Chainlit 2.8.2 breaking change | Custom `BaseDataLayer`/`BaseStorageClient` subclasses must implement `async close()`. **App uses the built-in `SQLAlchemyDataLayer` directly (no subclass)** — handled upstream, does not touch our code. |
| Genie visualization API | **Beta** (2026-07-02). Set `enable_visualization: true`; response gains a `viz` attachment (`GenieVizAttachment`: title + `query_attachment_id`); download via `.../attachments/{id}/query-result/visualization`. |
| Genie Managed MCP Server | **GA** (2026-05-28). Managed MCP server any agent can call as a tool for grounded NL→data over Genie + Unity Catalog. |

## 5. Current architecture (as-is)

```
Chainlit (routes.py)
  → MASChatClient.stream_raw(identity, messages)      # SSE to /invocations (OBO) or OpenAI client (PAT)
  → normalize(raw_events)                             # → text.delta/done, tool.call/output
  → ChainlitStream renderer                           # status block + streamed answer + pipe-tables
Lakebase (SQLAlchemyDataLayer + do_connect OAuth hook)  # threads/history persistence, resumable
```

Key insight: `routes.py`, `normalize`, and the renderer consume a **normalized
event stream**, not MAS specifics. This seam is what makes the 1b swap safe.

## 6. Target architecture (1b)

The app hosts its own reasoning loop. Genie MCP is a tool. The loop emits the
**same normalized events** (`text.delta/done`, `tool.call/output`) so the
renderer, normalizer, and Lakebase/auth layers are largely unchanged.

**Both MAS and Genie One are first-class, user-selectable agents.** The existing
agent selector (`@cl.set_starters` + `cl.ChatSettings` Select in `routes.py`)
already lets a user choose an endpoint per session. We extend that dropdown so
each entry declares a **kind** — `"mas"` (routes to `MASChatClient`) or
`"genie_one"` (routes to the in-app `ReasoningAgent` + Genie MCP). `on_message`
dispatches on the selected agent's kind. Neither is a fallback for the other;
they are peers, and a deployment can expose one or both.

```
src/app/
├── app.py, config.py, app.yaml
├── agent/                    # NEW — reasoning loop (1b)
│   ├── reasoning_agent.py    # LLM tool-calling loop (Foundation Model API); emits normalized events
│   └── genie_mcp.py          # managed Genie MCP client (tool transport + auth via Identity)
├── services/
│   ├── mas_client.py         # KEPT, de-emphasized (fallback / optional)
│   ├── mas_normalizer.py     # REUSED — agent emits the same event shapes
│   ├── renderer.py           # + viz rendering (Chainlit chart/image element)
│   ├── viz.py                # NEW — fetch + render Genie viz attachments
│   └── table_parser.py       # unchanged
├── memory/                   # RENAMED from data/ — headlines the Lakebase agent-memory story
│   ├── layer.py              # @cl.data_layer registration
│   ├── lakebase.py           # SQLAlchemyDataLayer + do_connect OAuth token injection
│   └── credentials.py        # ephemeral Lakebase credential provider
└── auth/                     # unchanged (OBO/SSO + local password auth)
```

### 6.1 Genie MCP as a tool (GA)
- `agent/genie_mcp.py` wraps the managed Genie MCP server (tool transport, auth
  reusing the existing `Identity`/OBO bearer).
- `agent/reasoning_agent.py` runs an LLM tool-calling loop (Foundation Model
  API) with Genie MCP registered as a tool.
- Each tool invocation/result maps onto existing `tool.call` / `tool.output`
  normalized events → renderer shows them in the status block unchanged.

### 6.2 Genie visualization (Beta)
- Request with `enable_visualization: true`.
- When a `viz` attachment appears, `services/viz.py` downloads it via the
  visualization endpoint; renderer emits it as a Chainlit chart/image element.
- Pipe-table rendering remains the fallback when no viz is present.

### 6.3 Chainlit upgrade (2.7.2 → 2.11.1)
- Bump pin (uv). No custom data-layer subclass → 2.8.2 `async close()` change
  does not apply.
- Verify: `do_connect` OAuth token injection, thread persistence, resumable
  threads (`@cl.on_chat_resume`).

## 7. Repo & branch strategy

- Upgrade `bi-hub-app` as the **single source of truth** on a fresh branch off
  `main`: `feature/genie-mcp-reasoning`.
- Existing uncommitted work on `feature/enhance-ux` is left **untouched**;
  branch from a clean `main`.
- After verifying in `bi-hub-app`, de-brand a copy into the cookbook
  `ai_memory/` folder.
- **No commits or pushes without explicit user approval.**

## 8. Cookbook contribution requirements (from CONTRIBUTING.md)

Two required deliverables: the example folder **and** the site doc page.

- **§0:** Open an issue or draft PR first; fork; feature branch `example/ai-memory`.
- **§1–§3:** Top-level `ai_memory/` folder; standard tooling — **`uv`**
  (`pyproject.toml`, not pip), **`ruff`**, **DABs**. Model structure on
  `genie_caching/`. Required files: `README.md`, `databricks.yml`,
  `resources/*.yml`, `pyproject.toml`, `.gitignore`, `.env.example`.
- **Hard rules:** No secrets ever (`.env.example` with placeholders only). Every
  workspace-specific value (Lakebase database path, Genie space ID, MAS/serving
  endpoint, catalog/schema, warehouse) is a **DAB variable with a default**,
  never a constant. Keep DB/compute small (scale-to-zero, smallest warehouse).
- **§4:** Add `site/src/content/docs/examples/ai-memory.mdx` (styled mirror of
  README, `<Callout>` source link, **no emojis**). Flip the `examples.ts` entry
  from `status: 'soon'` to `'ready'`; add the `intro.md` table row. `make build`
  must pass.
- **§5:** `uv run ruff check .` and `uv run ruff format .` clean.
- **§6:** PR description states what it demonstrates, confirms clean-checkout
  deploy, confirms `make build` passes, lists prerequisites.

The repo ships skills (`contribute-/scaffold-/document-/verify-lakebase-example`)
that implement these steps; we lean on them, but CONTRIBUTING.md wins on conflict.

## 9. De-brand pass

Strip customer names/logos (QVC/LCE/Ferguson), `theme.json`, `as-logo.png`,
synthetic-data generators; replace with neutral branding and a generic sample.
Convert `.env` → `.env.example` with placeholders. All workspace IDs → DAB
variables.

## 10. De-scope ladder (protects the Monday deadline)

Shed scope in this order if time runs short. **The cookbook PR always ships.**

1. **Drop first:** Genie visualization (Beta) → document as "v2 fast-follow";
   keep table rendering. (Beta also cuts against the cookbook's
   "deployable by anyone" rule.)
2. **Drop second:** the Genie One reasoning-agent path → ship with only the
   MAS agent(s) selectable (the selector simply lists no `genie_one` entry).
   The peer-agent framing means dropping Genie One degrades cleanly to
   MAS-only with no code path removed.
3. **Never drop:** Chainlit upgrade + restructure + de-brand + cookbook PR with a
   clean-checkout deploy.

## 11. Verification plan

- **Local:** `chainlit run app.py -w`; smoke-test a query end to end.
- **Deploy (guide §3 gate):** from a clean checkout,
  `databricks bundle validate -t demo` and `databricks bundle deploy -t demo`
  against the user's workspace (MAS + Lakebase ready).
- **Live smoke test:** send a query → confirm streaming, a Genie MCP tool call in
  the status block, a rendered result (viz or table), and that the thread
  **persists and resumes** from Lakebase.
- **Cookbook site:** `make install` (once), `make dev` to eyeball the page +
  sidebar, `make build` must succeed, `ruff` clean.

## 12. Risks

| Risk | Mitigation |
|------|------------|
| Weekend timeline for four tracks. | De-scope ladder (§10); cookbook PR is the floor. |
| Genie viz is Beta (API may shift; "surprise" risk for cookbook users). | First item on the de-scope ladder; gated behind a config flag; table fallback. |
| 1b reasoning loop is an architecture change to the core reasoning path. | Preserve the normalized-event seam; reuse `normalize`/renderer; keep MAS as fallback. |
| Clean-checkout deploy is the guide's gate and needs live MAS + Lakebase. | User's workspace is ready; verify early, not at the end. |
| Divergence between `bi-hub-app` and the cookbook copy. | Single source of truth: upgrade `bi-hub-app` first, copy after verification. |

## 13. Deliverables checklist

- [ ] `feature/genie-mcp-reasoning` branch off clean `main` in `bi-hub-app`.
- [ ] Chainlit 2.11.1 upgrade verified (data layer + resume intact).
- [ ] `agent/` reasoning loop calling Genie MCP; normalized events intact.
- [ ] Genie viz rendering (flag-gated) with table fallback.
- [ ] `data/` → `memory/` rename with import updates.
- [ ] De-branded copy in cookbook `ai_memory/` (uv, ruff, DABs, no secrets).
- [ ] All workspace-specific values are DAB variables.
- [ ] Clean-checkout `bundle deploy -t demo` verified against workspace.
- [ ] `ai_memory/README.md` (§2 structure).
- [ ] `site/src/content/docs/examples/ai-memory.mdx`; `examples.ts` → `ready`;
      `intro.md` row.
- [ ] `make build` passes; `ruff` clean.
- [ ] Draft PR opened (guide §0) → finalized by Monday.
