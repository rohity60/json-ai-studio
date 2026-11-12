import pytest

from jstudio import anna_llm, tools, wiring
from jstudio.aps_store import ApsSessionStore
from json_ai_studio.db.session_store import set_store
from json_ai_studio.services import credit_service

from fake_host import FakeHost


@pytest.fixture
def anna(monkeypatch) -> FakeHost:
    """The engine wired to an in-memory Anna host."""
    fake = FakeHost()
    store = ApsSessionStore(fake, transport=fake.transport())
    set_store(store)
    monkeypatch.setattr(wiring, "_store", store)
    monkeypatch.setattr(tools, "host", fake)
    anna_llm.register(fake)
    for deployment in wiring.DeploymentRegistry.list_deployments():
        deployment.enabled = deployment.name == "anna"
    credit_service._anon_credits.clear()
    credit_service._per_minute_tokens.clear()
    return fake
