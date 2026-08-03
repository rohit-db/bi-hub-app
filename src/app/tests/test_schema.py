from unittest.mock import MagicMock, patch
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
