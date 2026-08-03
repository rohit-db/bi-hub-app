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
