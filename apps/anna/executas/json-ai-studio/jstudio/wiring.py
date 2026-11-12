"""Configure the shared engine for the Anna runtime. Import this first.

Settings are read when ``json_ai_studio`` is first imported (the
deployment registry loads at import), so the environment is set here,
before any engine import.
"""

from __future__ import annotations

import os

# Only the `anna` deployment may serve calls; nothing here has provider keys.
os.environ["ANNA_ENABLED"] = "1"
# Anna caps output at 8,192 tokens per sampling call.
os.environ["LLM_MAX_TOKENS"] = "8192"
# Usage is metered and billed by Anna (the user's compute units), not by
# our credit pools: lift our own limits out of the way.
os.environ["ANON_MONTHLY_CREDIT_LIMIT"] = str(10**12)
os.environ["ANON_PER_MINUTE_TOKEN_LIMIT"] = str(10**12)
os.environ["ANON_REQUESTS_PER_MINUTE"] = str(10**9)
# No login, no database inside the Executa.
for _name in ("AUTH0_DOMAIN", "AUTH0_AUDIENCE", "DATABASE_URL"):
    os.environ[_name] = ""

from json_ai_studio.auth import Principal  # noqa: E402
from json_ai_studio.db.session_store import set_store  # noqa: E402
from json_ai_studio.deployment import DeploymentRegistry  # noqa: E402

from . import anna_llm  # noqa: E402
from .aps_store import ApsSessionStore  # noqa: E402
from .rpc import HostRpc, host  # noqa: E402

# One Anna user per storage bucket and per sampling token: the host knows
# who the caller is, so a single fixed principal is enough on our side.
PRINCIPAL = Principal(kind="anonymous", quota_key="anna", rate_key="anna")

_store: ApsSessionStore | None = None


def install(rpc: HostRpc | None = None) -> ApsSessionStore:
    """Point the engine at Anna: storage, LLM transport, deployments."""
    global _store
    rpc = rpc or host
    _store = ApsSessionStore(rpc)
    set_store(_store)
    anna_llm.register(rpc)
    for deployment in DeploymentRegistry.list_deployments():
        deployment.enabled = deployment.name == "anna"
    if not any(d.enabled for d in DeploymentRegistry.list_deployments()):
        raise RuntimeError("anna deployment is not available")
    return _store


def store() -> ApsSessionStore:
    if _store is None:
        raise RuntimeError("wiring.install() has not run")
    return _store
