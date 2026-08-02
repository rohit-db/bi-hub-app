# Design — Durable Chainlit schema (app owns its schema)

Date: 2026-08-02
Branch: feature/genie-mcp-reasoning
Scope: MF1 (grant durability). MF2 (bundle "Role not found" / binding provisioning ordering) is
explicitly OUT of scope here and only *noted* where the two overlap.

## Problem

`bundle deploy` re-provisions the app's `CAN_CONNECT_AND_CREATE` Lakebase database binding, which
recreates the app service principal's PostgreSQL role. Today the Chainlit tables are **owned by the
deploying human** (`rohit.bhagwat@databricks.com`, created via the `setup_lakebase` job), and the app
SP reaches them only through hand-made `GRANT`s. Recreating the role drops those grants, so Chainlit's
`authenticate_user` fails with `permission denied for table users` and **login breaks**. The grants
live only in the notebook's final cell, which runs only when the job is manually triggered — so every
`bundle deploy` re-breaks login until grants are re-applied by hand. This has been hit twice and
hand-fixed twice.

App SP (live instance): `207b66ae-730d-492c-bd41-5b41f3478802`.
Live Lakebase: instance `bi-agent-chat-session`, database `databricks_postgres`.

## Pivot / core idea

If the app SP **creates** the tables, it **owns** them. Ownership is intrinsic to the role — there
are no grants to wipe. As a secondary effect, PostgreSQL refuses to `DROP` a role that owns objects,
which should also blunt the destructive role-recreation itself (this overlaps MF2 — noted, not fixed
here).

The app already has everything needed to do this:
- `memory/credentials.py::LakebaseCredentialProvider` mints a Lakebase token **as the app SP**.
- `memory/lakebase.py::create_sync_engine()` connects as `PGUSER` (the app SP) using that token.

## Data-safety guarantee (redeploy behavior)

A redeploy does **not** drop tables or lose data:

1. The startup hook only ever runs `CREATE TABLE IF NOT EXISTS` (+ `ALTER TABLE ... ADD COLUMN IF NOT
   EXISTS`). No `DROP` anywhere. If tables exist, the DDL is a no-op on existing data.
2. Data lives in the **Lakebase database** resource (`database_instances.lakebase_postgres`), which has
   its own lifecycle. Redeploying the **app** does not touch the **database** — rows persist.
3. The prior breakage was loss of *access* (grants), never loss of *data*. Tables and rows were always
   present; login failed only because the app could not read them.

**Honest caveat (crux of deferred MF2):** once the app SP *owns* the tables, PostgreSQL refuses to
`DROP` that role while it owns objects. That is a data-protective failure, but it means the platform's
binding-provisioning behavior must be verified live:
- Best case: role persists across redeploy → grants never wiped → solved.
- Watch: if the platform runs `REASSIGN OWNED` (safe — owner change only) vs. a blind `DROP OWNED`
  (would drop objects). No evidence Databricks does the destructive form; not asserted without live
  verification (see Section 5).

## Components

### 1. `src/app/memory/schema.py` (new) — `ensure_schema()`
- Builds an engine via existing `create_sync_engine()` (connects as app SP `PGUSER`, token from
  `LakebaseCredentialProvider`).
- Runs the idempotent DDL (below) in a single transaction.
- Logs actions; on failure **logs and re-raises** so a broken DB surfaces loudly at boot rather than as
  a later mystery login error.
- Module-level `_ensured` flag so repeated calls are cheap no-ops.

### 2. Call site — `src/app/memory/layer.py`
- Call `ensure_schema()` inside `get_data_layer()` **before** `create_chainlit_data_layer()` constructs
  the `SQLAlchemyDataLayer`. Chainlit invokes `@cl.data_layer` once at startup before any request, so
  tables and ownership are guaranteed in place before Chainlit's first query.

### 3. DDL — single source of truth
- Full Chainlit 2.11 schema as `CREATE TABLE IF NOT EXISTS` for all 5 tables (`users`, `threads`,
  `steps`, `elements`, `feedbacks`), with `steps` including the 2.11 columns `autoCollapse` (BOOLEAN),
  `modes` (JSONB), `icon` (TEXT).
- Plus self-healing `ALTER TABLE steps ADD COLUMN IF NOT EXISTS` for those three columns, so a
  pre-existing old table is upgraded in place (the exact BUG1 situation). Safe whether the DB is
  brand-new or already has old tables.
- No `DROP`, ever.
- This module becomes the single source of truth. `setup_chainlit_schema.py` will import/point at this
  same DDL. The `.sql` file and `.ipynb` remain as documented artifacts; any drift is flagged. The
  separate setup job/notebook is no longer required for correctness — noted as optional for the cookbook,
  not deleted in this task.

### 4. One-time live migration (existing instance only)
- Live tables are currently owned by `rohit.bhagwat@...`. `CREATE TABLE IF NOT EXISTS` does not change
  ownership of existing tables, so on the current instance the app SP would still rely on grants until
  re-homed. One-time, against the live instance: `REASSIGN OWNED BY rohit.bhagwat@... TO "<app-sp>"`
  (or per-table `ALTER TABLE ... OWNER TO`). Data-safe (ownership change only). After this, grants are
  irrelevant. Fresh cookbook deploys skip this — the app SP creates and owns from the start.

## Testing

- Unit test (mocked engine, no live DB, matching `tests/test_data_layer_smoke.py` style): assert
  `ensure_schema()` issues `CREATE TABLE IF NOT EXISTS` for all 5 tables and the 3
  `ALTER TABLE steps ADD COLUMN IF NOT EXISTS` statements.

## Section 5 — Redeploy safety + live verification (the guarantee)

Before MF1 is called done, against the live instance:
1. Insert a **sentinel test row** (or record an existing thread id).
2. Run a real `bundle deploy` + `apps deploy` cycle.
3. Confirm the sentinel row **still exists** and login/read works with **no manual grant**.
4. Inspect table ownership after the deploy (did the platform preserve the role or reassign ownership?).

"Redeploy-safe" is not asserted until a redeploy is observed to preserve the row. If step 3/4 reveals
the platform does something destructive to owned objects, that escalates into MF2 — stop and report
rather than paper over it.

## Out of scope
- MF2 (bundle "Role not found" / app↔db binding provisioning ordering).
- Deleting the setup job/notebook (cookbook de-brand work, Tasks 10-12).
- MAS/Genie visualization work.
