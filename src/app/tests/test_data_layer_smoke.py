import chainlit  # noqa: F401


def test_chainlit_version_floor():
    from importlib.metadata import version
    assert tuple(int(x) for x in version("chainlit").split(".")[:2]) >= (2, 11)


def test_sqlalchemy_data_layer_importable():
    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer  # noqa: F401
    assert hasattr(SQLAlchemyDataLayer, "close")  # 2.8.2+ base API
