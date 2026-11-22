"""Fixtures for live model/prompt evals.

Reuses the test fixtures (auth disabled, isolated settings, and
``pinned_deployment``, which enables exactly one deployment from
LIVE_DEPLOYMENT and paces calls with LIVE_CALL_SPACING_S).
"""

from tests.conftest import *  # noqa: F401,F403
