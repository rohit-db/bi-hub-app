import chainlit as cl
from .lakebase import create_chainlit_data_layer

@cl.data_layer
def get_data_layer():
    data_layer = create_chainlit_data_layer()
    return data_layer