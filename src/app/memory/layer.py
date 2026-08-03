import chainlit as cl
from .lakebase import create_chainlit_data_layer
from .schema import ensure_schema


@cl.data_layer
def get_data_layer():
    ensure_schema()  # app SP creates/owns tables before Chainlit queries them
    data_layer = create_chainlit_data_layer()
    return data_layer
