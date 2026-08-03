# Durable Chainlit Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Chainlit schema durable across `bundle deploy` by having the app service principal create (and thus own) its tables via an idempotent startup hook, eliminating the grant-wipe login break.

**Architecture:** A new `memory/schema.py` module exposes `ensure_schema()`, which connects as the app SP (reusing `create_sync_engine()` and `LakebaseCredentialProvider`) and runs idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` DDL. It is called once from `get_data_layer()` before the `SQLAlchemyDataLayer` is constructed. Because the app SP creates the tables, it owns them — no grants to wipe on redeploy.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, psycopg 3, Chainlit 2.11.1, Databricks SDK, pytest 8.4.

## Global Constraints

- Chainlit version floor: `>= 2.11` (schema targets Chainlit 2.11.1 `StepDict`).
- No `DROP` statements anywhere in runtime DDL — only `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- App connects as the app SP via `PGUSER`; credentials come from `LakebaseCredentialProvider` (never a PAT).
- Committed `app.yaml` stays de-branded (placeholders); live values injected at deploy only.
- Tests must run without a live database (mock the engine).
- Commit per task, in worktree only. Never push to origin without user OK.
- The `steps` table 2.11 columns are exactly: `autoCollapse` BOOLEAN, `modes` JSONB, `icon` TEXT.

---

### Task 1: `ensure_schema()` module with idempotent DDL

**Files:**
- Create: `src/app/memory/schema.py`
- Test: `src/app/tests/test_schema.py`

**Interfaces:**
- Consumes: `memory.lakebase.create_sync_engine()` (returns a SQLAlchemy `Engine` whose `do_connect` event injects the app-SP token).
- Produces:
  - `CHAINLIT_DDL: list[str]` — ordered list of DDL statements (5 `CREATE TABLE IF NOT EXISTS` + 3 `ALTER TABLE steps ADD COLUMN IF NOT EXISTS`).
  - `ensure_schema(engine=None) -> None` — runs `CHAINLIT_DDL` in one transaction against `engine` (defaults to `create_sync_engine()`); idempotent via module-level `_ensured` flag; logs and re-raises on failure.

- [ ] **Step 1: Write the failing test**

```python
# src/app/tests/test_schema.py
from unittest.mock import MagicMock
import memory.schema as schema


def _reset():
    schema._ensured = False


def test_ddl_covers_all_tables_and_new_columns():
    _reset()
    joined = "\n".join(schema.CHAINLIT_DDL)
    for table in ("users", "threads", "steps", "elements", "feedbacks"):
        assert f'CREATE TABLE IF NOT EXISTS {table}' in joined
    # Self-healing ALTERs for the Chainlit 2.11 steps columns
    for col in ("autoCollapse", "modes", "icon"):
        assert f'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "{col}"' in joined
    # No destructive DDL
    assert "DROP TABLE" not in joined.upper()


def test_ensure_schema_executes_every_statement_in_transaction():
    _reset()
    engine = MagicMock()
    conn = engine.begin.return_value.__enter__.return_value
    schema.ensure_schema(engine=engine)
    # begin() opens a transaction that auto-commits on exit
    engine.begin.assert_called_once()
    assert conn.execute.call_count == len(schema.CHAINLIT_DDL)


def test_ensure_schema_is_idempotent_within_process():
    _reset()
    engine = MagicMock()
    schema.ensure_schema(engine=engine)
    schema.ensure_schema(engine=engine)  # second call is a no-op
    engine.begin.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memory.schema'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/memory/schema.py
"""Idempotent Chainlit schema bootstrap, run by the app service principal.

The app's Lakebase database binding is CAN_CONNECT_AND_CREATE, so the app SP
can create its own tables. Because it *creates* them, it *owns* them — there
are no grants to wipe when `bundle deploy` recreates the SP's Postgres role.
This replaces the fragile owner=human + hand-made GRANT model.
"""
from sqlalchemy import text
from utils.logging import logger
from memory.lakebase import create_sync_engine

# Chainlit 2.11.1 schema. CREATE ... IF NOT EXISTS is a no-op when tables
# already exist (never touches existing data). The trailing ALTERs self-heal
# a pre-existing older `steps` table missing the 2.11 columns.
CHAINLIT_DDL = [
    '''CREATE TABLE IF NOT EXISTS users (
        "id" UUID PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" JSONB NOT NULL,
        "createdAt" TEXT
    );''',
    '''CREATE TABLE IF NOT EXISTS threads (
        "id" UUID PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" UUID,
        "userIdentifier" TEXT,
        "tags" TEXT[],
        "metadata" JSONB,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    );''',
    '''CREATE TABLE IF NOT EXISTS steps (
        "id" UUID PRIMARY KEY,
        "name" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "threadId" UUID NOT NULL,
        "parentId" UUID,
        "streaming" BOOLEAN NOT NULL,
        "waitForAnswer" BOOLEAN,
        "isError" BOOLEAN,
        "metadata" JSONB,
        "tags" TEXT[],
        "input" TEXT,
        "output" TEXT,
        "createdAt" TEXT,
        "command" TEXT,
        "start" TEXT,
        "end" TEXT,
        "generation" JSONB,
        "showInput" TEXT,
        "language" TEXT,
        "indent" INT,
        "defaultOpen" BOOLEAN,
        "autoCollapse" BOOLEAN,
        "modes" JSONB,
        "icon" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );''',
    '''CREATE TABLE IF NOT EXISTS elements (
        "id" UUID PRIMARY KEY,
        "threadId" UUID,
        "type" TEXT,
        "url" TEXT,
        "chainlitKey" TEXT,
        "name" TEXT NOT NULL,
        "display" TEXT,
        "objectKey" TEXT,
        "size" TEXT,
        "page" INT,
        "language" TEXT,
        "forId" UUID,
        "mime" TEXT,
        "props" JSONB,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );''',
    '''CREATE TABLE IF NOT EXISTS feedbacks (
        "id" UUID PRIMARY KEY,
        "forId" UUID NOT NULL,
        "threadId" UUID NOT NULL,
        "value" INT NOT NULL,
        "comment" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );''',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "autoCollapse" BOOLEAN;',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "modes" JSONB;',
    'ALTER TABLE steps ADD COLUMN IF NOT EXISTS "icon" TEXT;',
]

_ensured = False


def ensure_schema(engine=None) -> None:
    """Create/upgrade the Chainlit schema as the app SP. Idempotent per process."""
    global _ensured
    if _ensured:
        return
    engine = engine or create_sync_engine()
    try:
        with engine.begin() as conn:
            for stmt in CHAINLIT_DDL:
                conn.execute(text(stmt))
        _ensured = True
        logger.info("Chainlit schema ensured (app SP owns tables)")
    except Exception as e:
        logger.error(f"ensure_schema failed: {e}")
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/memory/schema.py src/app/tests/test_schema.py
git commit -m "feat(lakebase): app-SP-owned idempotent Chainlit schema bootstrap"
```

---

### Task 2: Wire `ensure_schema()` into data-layer startup

**Files:**
- Modify: `src/app/memory/layer.py`
- Test: `src/app/tests/test_schema.py` (add one test)

**Interfaces:**
- Consumes: `memory.schema.ensure_schema` (from Task 1), `memory.lakebase.create_chainlit_data_layer`.
- Produces: `get_data_layer()` calls `ensure_schema()` before constructing the data layer.

- [ ] **Step 1: Write the failing test**

```python
# append to src/app/tests/test_schema.py
from unittest.mock import patch


def test_get_data_layer_ensures_schema_before_datalayer():
    _reset()
    calls = []
    with patch("memory.layer.ensure_schema", side_effect=lambda: calls.append("ensure")) as es, \
         patch("memory.layer.create_chainlit_data_layer",
               side_effect=lambda: calls.append("datalayer") or MagicMock()) as dl:
        import memory.layer as layer
        layer.get_data_layer()
        es.assert_called_once()
        dl.assert_called_once()
        assert calls == ["ensure", "datalayer"]  # ordering: schema first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_schema.py::test_get_data_layer_ensures_schema_before_datalayer -v`
Expected: FAIL — `AttributeError: <module 'memory.layer'> does not have the attribute 'ensure_schema'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/memory/layer.py
import chainlit as cl
from .lakebase import create_chainlit_data_layer
from .schema import ensure_schema


@cl.data_layer
def get_data_layer():
    ensure_schema()  # app SP creates/owns tables before Chainlit queries them
    data_layer = create_chainlit_data_layer()
    return data_layer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_schema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full unit suite (no regressions)**

Run: `cd src/app && python -m pytest -q`
Expected: PASS (previous count + new schema tests; nothing broken)

- [ ] **Step 6: Commit**

```bash
git add src/app/memory/layer.py src/app/tests/test_schema.py
git commit -m "feat(lakebase): ensure schema at data-layer startup"
```

---

### Task 3: Point setup script at the shared DDL (single source of truth)

**Files:**
- Modify: `src/scripts/setup_chainlit_schema.py`

**Interfaces:**
- Consumes: `memory.schema.CHAINLIT_DDL` (from Task 1).
- Produces: no new interface; removes the duplicated inline `schema_sql` string so the `.py` setup script and the app share one DDL definition.

**Note:** This task removes DDL duplication in the standalone Python setup script only. The `.ipynb` embeds its own DDL (it cannot import app modules at notebook runtime) and the `.sql` file is a hand-run artifact; both are left as-is and already carry the 2.11 columns. Add a comment in each pointing at `memory/schema.py` as canonical. No behavior change to the running app — this is a maintainability cleanup, tested by the existing suite still passing.

- [ ] **Step 1: Replace the inline `schema_sql` block**

In `src/scripts/setup_chainlit_schema.py`, replace the hardcoded `schema_sql = text('''...''')` (lines ~114-185) and its single `conn.execute(schema_sql)` with iteration over the shared DDL:

```python
        # Create official Chainlit schema (shared source of truth: app/memory/schema.py)
        print("🔨 Creating official Chainlit schema...")
        from app.memory.schema import CHAINLIT_DDL
        with engine.begin() as conn:
            for stmt in CHAINLIT_DDL:
                conn.execute(text(stmt))
        print("✅ Created official Chainlit schema")
```

- [ ] **Step 2: Add canonical-source pointer comments**

Add a one-line comment at the top of `src/scripts/chainlit_schema.sql` (after line 3) and in the notebook's schema cell markdown:

```
-- CANONICAL DDL lives in src/app/memory/schema.py (CHAINLIT_DDL). Keep in sync.
```

- [ ] **Step 3: Verify the app suite still passes (no regression)**

Run: `cd src/app && python -m pytest -q`
Expected: PASS (unchanged count)

- [ ] **Step 4: Commit**

```bash
git add src/scripts/setup_chainlit_schema.py src/scripts/chainlit_schema.sql src/scripts/setup_chainlit_lakebase.ipynb
git commit -m "refactor(scripts): share Chainlit DDL from memory/schema.py"
```

---

### Task 4: One-time live ownership migration (existing instance)

**Files:** none (live operation against `bi-agent-chat-session`, documented in progress ledger).

**Note:** This is a live, one-time operation on the existing FEVM-stable instance whose tables are currently owned by `rohit.bhagwat@databricks.com`. Fresh cookbook deploys skip this entirely. Requires user confirmation (changes ownership of existing threads' tables — data-safe, ownership-only).

- [ ] **Step 1: Generate a Lakebase credential (write token to file, do not inline)**

```bash
databricks database generate-database-credential -p fevm-stable-71zsua \
  --json '{"instance_names":["bi-agent-chat-session"],"request_id":"mf1-migrate"}' \
  --output json > /tmp/lb_cred.json
```

- [ ] **Step 2: Capture pre-migration ownership + a sentinel**

Connect via psycopg as `rohit.bhagwat@databricks.com` (host `ep-late-dawn-d83w5s4t.database.us-east-2.cloud.databricks.com`, db `databricks_postgres`, sslmode require, password = token from `/tmp/lb_cred.json`). Record:

```sql
SELECT tablename, tableowner FROM pg_tables
WHERE schemaname='public' AND tablename IN ('users','threads','steps','elements','feedbacks');
SELECT count(*) FROM threads;  -- sentinel row count for later comparison
```

- [ ] **Step 3: Reassign ownership to the app SP**

```sql
REASSIGN OWNED BY "rohit.bhagwat@databricks.com" TO "207b66ae-730d-492c-bd41-5b41f3478802";
```

(If `REASSIGN OWNED` is rejected for cross-role reasons, fall back to per-table
`ALTER TABLE public."<t>" OWNER TO "207b66ae-730d-492c-bd41-5b41f3478802";` for each of the 5 tables + their sequences.)

- [ ] **Step 4: Verify ownership changed and data intact**

```sql
SELECT tablename, tableowner FROM pg_tables
WHERE schemaname='public' AND tablename IN ('users','threads','steps','elements','feedbacks');
-- all 5 owned by 207b66ae-...
SELECT count(*) FROM threads;  -- must equal Step 2 count
```

- [ ] **Step 5: Record result in progress ledger**

Append the before/after ownership and row counts to `.superpowers/sdd/2026-07-31-genie-mcp-reasoning-and-cookbook/progress.md`.

---

### Task 5: Redeploy safety live verification (the guarantee)

**Files:** none (live deploy against FEVM stable, documented in progress ledger).

**Note:** This proves the fix. Requires a real `bundle deploy` + `apps deploy` — the same cycle that twice wiped grants before. Requires user confirmation before deploying to the live app.

- [ ] **Step 1: Insert a sentinel test row (or note an existing thread id)**

Via psycopg as the migrated owner, note the current max thread `createdAt` and total `threads` count as the sentinel.

- [ ] **Step 2: Deploy**

```bash
databricks bundle deploy -p fevm-stable-71zsua \
  --var serving_endpoint=mas-594e06e9-endpoint \
  --var user_name=rohit.bhagwat@databricks.com
databricks apps deploy bi-agent \
  --source-code-path /Workspace/Users/rohit.bhagwat@databricks.com/.bundle/bi-hub-app/dev/files/src/app \
  -p fevm-stable-71zsua
```

- [ ] **Step 3: Verify data survived + no manual grant needed**

```sql
SELECT count(*) FROM threads;  -- equals sentinel count from Step 1
SELECT tablename, tableowner FROM pg_tables
WHERE schemaname='public' AND tablename IN ('users','threads','steps','elements','feedbacks');
```
Then have the user reload the app and confirm **login works with no manual grant applied**.

- [ ] **Step 4: Inspect post-deploy ownership / role behavior**

Confirm whether the platform preserved the app SP role or reassigned ownership. If ownership/role behavior is destructive to owned objects, STOP and report — this escalates into MF2 rather than being patched here.

- [ ] **Step 5: Record the verification outcome in the progress ledger**

Mark MF1 complete only if: data intact + login works + no manual grant. Otherwise document the failure mode for MF2.

---

### Task 6: Bootstrap grant — app SP needs CREATE ON SCHEMA public (added after live verification)

**Why (discovered live in Tasks 4-5):** Despite the app's `CAN_CONNECT_AND_CREATE` database binding, the app SP has only `USAGE` (not `CREATE`) on schema `public` and no database-level `CREATE`. So `ensure_schema()` running as the app SP would FAIL to create tables on a genuinely fresh database. The one-time fix, proven live, is `GRANT CREATE ON SCHEMA public TO "<app-sp-client-id>"`. The app SP cannot grant this to itself (it lacks the privilege); it must be issued by the setup job/notebook, which runs as the deploying human (who owns/can-grant on the schema). This makes a clean cookbook deploy work end-to-end.

**Files:**
- Modify: `src/scripts/setup_chainlit_lakebase.ipynb` (the job's notebook — cell that grants schema perms, cell-8).
- Modify: `src/scripts/setup_chainlit_schema.py` (the standalone Python setup script's grant section, if present) — keep parity.

**Interfaces:**
- Consumes: `app_id = w.apps.get(name=app_name).id` (already computed in cell-8).
- Produces: the setup job additionally runs `GRANT CREATE ON SCHEMA public TO "<app_id>"` idempotently, before/alongside the existing `GRANT USAGE ON SCHEMA` and table grants.

- [ ] **Step 1: Add the CREATE-on-schema grant to the notebook's grant_schema_permissions**

In `src/scripts/setup_chainlit_lakebase.ipynb` cell-8, extend `grant_schema_permissions` so it grants BOTH usage and create (create is what lets the app SP create — and thus own — the Chainlit tables at first startup):

```python
        schema_permission_sql = text(f'''
        GRANT USAGE ON SCHEMA "public" TO "{app_id}";
        GRANT CREATE ON SCHEMA "public" TO "{app_id}";
        ''')
```

- [ ] **Step 2: Mirror the grant in the standalone Python setup script (parity)**

If `src/scripts/setup_chainlit_schema.py` has a grant section, add the same `GRANT CREATE ON SCHEMA public` line. If it has no grant section, add a short comment there pointing to the notebook as the canonical grant location. (No functional grant path is required in both — parity/comment is enough.)

- [ ] **Step 3: Validate notebook JSON + python syntax (no live run needed)**

Run: `python -c "import json; json.load(open('src/scripts/setup_chainlit_lakebase.ipynb'))"` and `python -c "import ast; ast.parse(open('src/scripts/setup_chainlit_schema.py').read())"`
Expected: both succeed (valid JSON, valid python).

- [ ] **Step 4: Confirm app unit suite still passes (no regression)**

Run: `cd src/app && python -m pytest -q`
Expected: PASS (24 tests, unchanged — this task touches only scripts).

- [ ] **Step 5: Commit**

```bash
git add src/scripts/setup_chainlit_lakebase.ipynb src/scripts/setup_chainlit_schema.py
git commit -m "feat(lakebase): grant CREATE on public to app SP so it can own its schema"
```

**Note:** The grant was already applied LIVE on the bi-agent-chat-session instance during Task 4 (that's how fresh-create was proven). This task bakes it into the setup job so a stranger's clean cookbook deploy works without a manual step.

---

## Self-Review

**Spec coverage:**
- Spec §1 (root cause / pivot) → Tasks 1-2 (app-SP-owned tables).
- Spec §2 (startup hook, call site) → Task 2.
- Spec §3 (idempotent DDL, single source of truth, self-heal ALTERs) → Task 1 (DDL) + Task 3 (dedup).
- Spec §4 (one-time live ownership migration) → Task 4.
- Spec §5 (redeploy safety + live verification) → Task 5.
- Testing (mocked-engine unit test) → Task 1 Step 1 + Task 2 Step 1.
- Data-safety guarantee (no DROP; data in separate resource) → enforced by Global Constraints + Task 1 DDL test asserting no `DROP TABLE`.

**Placeholder scan:** No TBD/TODO; all code and SQL is concrete. Live-operation tasks (4, 5) give exact commands with real host/instance/SP values from the ledger.

**Type consistency:** `ensure_schema(engine=None)`, `CHAINLIT_DDL`, and `_ensured` names are used identically across Tasks 1-3. `get_data_layer()` signature unchanged.
