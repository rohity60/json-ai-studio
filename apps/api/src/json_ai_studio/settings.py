"""Application settings loaded from environment variables / .env file.

Central config seam (ADR-0015). All Auth0 + database + quota knobs live
here. `auth_enabled` gates the optional-login feature: when Auth0 or the
database is not configured, the API still serves anonymous traffic and
bearer-token requests get a 503.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shared anonymous quota pool key (formerly hardcoded "dev-default-key").
    general_api_key: str = "dev-default-key"

    # postgresql+asyncpg://user:pass@host:5432/dbname — None disables login.
    database_url: str | None = None

    # Auth0 tenant, e.g. "dev-xxxx.us.auth0.com" (no scheme).
    auth0_domain: str | None = None
    # Auth0 API identifier (audience). Must match an API configured in the
    # Auth0 dashboard or access tokens come back opaque and fail validation.
    auth0_audience: str | None = None

    # LLM deployment registry (config/deployments.yaml). Provider API keys:
    # a missing/empty key auto-disables that deployment at load time.
    google_ai_studio_api_key: str | None = None
    nvidia_nim_api_key: str | None = None
    openrouter_api_key: str | None = None
    # Ollama endpoint (env: OLLAMA_BASE_URL), e.g. http://localhost:11434
    # or a tunnel/hosted URL. Unset disables the ollama deployment.
    ollama_base_url: str | None = None

    # Max output tokens per LLM call (env: LLM_MAX_TOKENS). Generic across
    # providers (litellm normalizes the param). Prevents silent truncation
    # of large diff payloads — a truncated JSON diff is unparseable and used
    # to leak raw model output at the user. Large enough to hold a full diff
    # whose new_value embeds a pasted document.
    llm_max_tokens: int = 16_384

    # Max serialized chars of the working JSON inlined verbatim into the
    # system prompt (env: LLM_MAX_INLINE_CHARS). Above this, the prompt
    # sends a typed skeleton (nested keys + sample values) instead of the
    # full document. The old 60k cap was tuned for local Ollama freezes;
    # hosted models tolerate more, so more docs get full-fidelity values.
    llm_max_inline_chars: int = 120_000

    # Anonymous (shared pool) quota defaults — match pre-login behavior.
    # Token limit sized for large-JSON editing: one inline doc at the
    # llm_max_inline_chars cap costs ~49k prompt tokens (~2.7 chars/token);
    # 150k allows a few such turns while staying under the provider free-tier
    # TPM (Google AI Studio free ≈ 250k TPM on the shared key). NOTE: this is
    # a single GLOBAL pool across all anonymous users, and the real free-tier
    # ceiling is requests/min + requests/day (Google free ≈ 10-15 RPM), not
    # tokens — see anon_requests_per_minute.
    anon_monthly_credit_limit: int = 10_000
    anon_per_minute_token_limit: int = 150_000
    anon_requests_per_minute: int = 10

    # Logged-in free-tier defaults (per user). Per-user token window (not a
    # shared pool): 100k lets one user iterate on a large inline doc a few
    # times per minute, still under the provider TPM.
    user_monthly_credit_limit: int = 2_000
    user_per_minute_token_limit: int = 100_000
    user_requests_per_minute: int = 30

    # Workspace limits (ADR-0018). Writes past the limit are blocked with
    # 409, never evicted.
    workspace_max_jsons: int = 5
    json_max_versions: int = 5

    # Templates hub (ADR-0020). Max serialized size of template JSON accepted
    # by POST /api/sessions/from-template. Guards memory; templates are small.
    max_template_json_bytes: int = 262_144  # 256 KiB

    # Logging (ADR-0017). Env-driven so level/dir/rotation are tunable without
    # code changes. Applies to root, the json_ai_studio namespace, and (when
    # log_capture_uvicorn) uvicorn's own loggers.
    log_level: str = "INFO"  # DEBUG|INFO|WARNING|ERROR|CRITICAL
    # Relative dir resolves against CWD: apps/api/logs locally, /app/logs in
    # the container (see docker-compose bind mount).
    log_dir: str = "logs"
    log_file_name: str = "app.log"
    log_to_file: bool = True
    log_to_console: bool = True  # keep stderr so `docker logs` still works
    log_max_bytes: int = 10_485_760  # 10 MiB per file before rollover
    log_backup_count: int = 5  # keep app.log.1 .. app.log.5
    log_capture_uvicorn: bool = True  # route uvicorn/access logs to same sinks

    @field_validator(
        "google_ai_studio_api_key",
        "nvidia_nim_api_key",
        "openrouter_api_key",
        "ollama_base_url",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v: str | None) -> str | None:
        # docker-compose passthrough of an unset var arrives as "".
        return v or None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, v: str | None) -> str:
        # Accept lowercase / whitespace; empty (compose passthrough) -> INFO.
        if not v or not str(v).strip():
            return "INFO"
        return str(v).strip().upper()

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth0_domain and self.auth0_audience and self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
