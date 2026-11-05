"""Keep per-process admission budgets independent between test cases.

No solver or provider results are replaced. Limits remain active within a test.
"""
import pytest
@pytest.fixture(autouse=True)
def reset_release_budgets():
    from app.main import app
    from app.release import ReleaseLimits
    layer=app.middleware_stack
    while layer is not None:
        if isinstance(layer,ReleaseLimits):
            with layer.lock:layer.events.clear();layer.ai_events.clear()
        layer=getattr(layer,'app',None)
