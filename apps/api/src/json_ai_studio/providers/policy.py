"""Per-deployment provider policy config (PRD B B-19, hotfix 2026-11-11).

Fixed provider facts and safety caps that differ between providers and
tiers (Google free tier vs local Ollama vs a paid key): budget headroom,
window margin, and retry limits. Loaded from a `policy:` block per
deployment in config/deployments.yaml; any field left out falls back to
the matching Settings default, so env overrides keep working.

Learned values (5xx rate, latency) and the behavioural ProviderPolicy
(classify / retry_decision / record) build on this later (PRD B B-20,
B-27..B-29); they read the same config.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from ..settings import Settings, get_settings


@dataclass(frozen=True)
class DeploymentPolicy:
    # Fraction of tpm_input_limit turns are planned and gated against.
    budget_headroom: float
    # Seconds a call keeps counting past 60 s after it finishes (skew).
    window_margin_s: float
    # A 5xx that returns within this many seconds is a transient hiccup.
    transient_fast_s: float
    # Transient 5xx retries: per call, per turn, base wait (× attempt).
    transient_retry_attempts: int
    transient_retry_turn_max: int
    transient_retry_wait_s: float
    # Explicit waits before retry 1, 2, 3… (last one repeats). Empty =
    # transient_retry_wait_s × attempt. Spread them out where the provider
    # fails in bursts (Google: minutes), so retries can outlast a burst.
    transient_retry_schedule_s: tuple[float, ...]
    # 429 retries: only with a provider hint no longer than max_wait_s.
    rate_limit_retry_attempts: int
    rate_limit_retry_max_wait_s: float

    @classmethod
    def defaults(cls, settings: Settings | None = None) -> "DeploymentPolicy":
        s = settings or get_settings()
        return cls(
            budget_headroom=s.deployment_budget_headroom,
            window_margin_s=s.deployment_window_margin_s,
            transient_fast_s=s.chat_transient_fast_s,
            transient_retry_attempts=s.chat_transient_retry_attempts,
            transient_retry_turn_max=s.chat_transient_retry_turn_max,
            transient_retry_wait_s=s.chat_transient_retry_wait_s,
            transient_retry_schedule_s=(),
            rate_limit_retry_attempts=s.chat_tool_retry_attempts,
            rate_limit_retry_max_wait_s=s.chat_tool_retry_max_wait_s,
        )

    @classmethod
    def from_config(
        cls, cfg: dict[str, Any] | None, settings: Settings | None = None
    ) -> "DeploymentPolicy":
        """Settings defaults overridden by a deployment's `policy:` block."""
        base = cls.defaults(settings)
        cfg = cfg or {}
        known = {f.name: f.type for f in fields(cls)}
        unknown = set(cfg) - set(known)
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        values = {f.name: getattr(base, f.name) for f in fields(cls)}
        for key, raw in cfg.items():
            if isinstance(values[key], tuple):
                if not isinstance(raw, (list, tuple)) or not raw:
                    raise ValueError(f"policy.{key} must be a non-empty list")
                values[key] = tuple(float(x) for x in raw)
            else:
                values[key] = int(raw) if isinstance(values[key], int) else float(raw)
        policy = cls(**values)
        if not 0 < policy.budget_headroom <= 1:
            raise ValueError("policy.budget_headroom must be in (0, 1]")
        return policy


def transient_wait(policy: DeploymentPolicy, attempt: int) -> float:
    """Seconds to back off before fast-5xx retry `attempt` (1-based)."""
    schedule = policy.transient_retry_schedule_s
    if schedule:
        return schedule[min(attempt, len(schedule)) - 1]
    return policy.transient_retry_wait_s * attempt


def policy_of(deployment: Any) -> DeploymentPolicy:
    """The deployment's policy, or the Settings defaults (test doubles)."""
    policy = getattr(deployment, "policy", None)
    return (
        policy if isinstance(policy, DeploymentPolicy) else DeploymentPolicy.defaults()
    )
