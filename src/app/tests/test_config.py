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
