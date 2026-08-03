def test_memory_module_imports():
    from memory.lakebase import create_chainlit_data_layer  # noqa: F401
    from memory.credentials import LakebaseCredentialProvider  # noqa: F401
    import memory.layer  # noqa: F401
