# tests/test_viz.py
"""Network-free unit tests for services/viz.py element building."""
import pytest


@pytest.fixture(autouse=True)
def _chainlit_ctx():
    """Inject a minimal Chainlit context so Element constructors can resolve thread_id."""
    from chainlit.context import context_var

    class _Session:
        thread_id = "test-thread"

    class _MockCtx:
        session = _Session()

    token = context_var.set(_MockCtx())
    yield
    context_var.reset(token)


def test_to_element_plotly_from_figure_json():
    from services.viz import to_element
    fig_json = '{"data":[{"type":"bar","y":[1,2,3]}],"layout":{}}'
    el = to_element({"kind": "plotly", "figure_json": fig_json})
    assert el.__class__.__name__ == "Plotly"


def test_to_element_image_from_bytes():
    from services.viz import to_element
    el = to_element({"kind": "image", "content": b"\x89PNG..."})
    assert el.__class__.__name__ == "Image"
