# tests/test_routes_dispatch.py
"""Dispatch tests for _raw_events_for — network-free."""


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
    it = routes._raw_events_for({"name": "MAS", "kind": "mas", "endpoint": "ep1"}, _Id(), [])
    assert hasattr(it, "__aiter__")  # async iterator returned


def test_dispatch_genie_one(monkeypatch):
    routes = _reload(monkeypatch,
        '[{"name":"Genie One","kind":"genie_one","genie_space_id":"sp1"}]')
    it = routes._raw_events_for(
        {"name": "Genie One", "kind": "genie_one", "genie_space_id": "sp1"}, _Id(), [])
    assert hasattr(it, "__aiter__")


def test_unknown_kind_defaults_to_mas(monkeypatch):
    routes = _reload(monkeypatch, '[{"name":"Legacy","endpoint":"ep2"}]')
    # no "kind" key -> treated as mas, must not raise
    routes._raw_events_for({"name": "Legacy", "endpoint": "ep2"}, _Id(), [])
