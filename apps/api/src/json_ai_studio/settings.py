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
    # Context window requested from Ollama per call (env: OLLAMA_NUM_CTX).
    # Ollama's own default is small and silently truncates long prompts.
    ollama_num_ctx: int = 32_768

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

    # Chat history (multi-turn context). Prior user/assistant turns are
    # replayed to the LLM with per-diff status so follow-ups ("do it for all
    # such elements") resolve. Bounded by pairs and tokens; oldest pairs are
    # dropped first. Disabled → single-turn [system, user] calls.
    chat_history_enabled: bool = True
    chat_history_max_turns: int = 10  # user/assistant pairs replayed
    chat_history_max_tokens: int = 8_000
    chat_history_value_max_chars: int = 300  # per new_value in replay
    chat_history_max_diffs_per_turn: int = 20
    chat_history_max_stored_turns: int = 200  # pruned from the session

    # Lookup tools (ADR-0024): read-only search/read offered to the model when
    # the document is too large to inline and the deployment supports_tools.
    chat_tools_enabled: bool = True
    chat_tool_max_rounds: int = 4  # tool rounds before a forced final answer
    chat_tool_result_max_chars: int = 4_000  # per tool result
    chat_tool_turn_timeout_s: float = 150.0  # whole tool loop wall clock
    # Retries per LLM call (tool round or single call). Default 0: pacing and
    # the token gate keep load down, and every retry adds to the provider's
    # per-minute count (ADR-0025). If raised, only a 429 with a short
    # provider hint is retried; 5xx never are.
    chat_tool_retry_attempts: int = 0
    chat_tool_retry_max_wait_s: float = 10.0  # longer provider retry hints → fail

    # Deployment token budget (ADR-0025). Prompts are planned, and every call
    # is gated, against this fraction of a deployment's tpm_input_limit
    # (estimate error; Google fails with 500s near its stated limit). Any call — first or a later tool round — that would overflow
    # the minute waits up to max_wait_s for capacity (countdown streamed),
    # else the turn ends with a model-scope rate_limit. 60 s = one window.
    deployment_budget_headroom: float = 0.8
    deployment_budget_max_wait_s: float = 60.0

    # Bulk edits: the model may emit a pattern op ("/records/*/field" + where)
    # that the server expands against the full JSON (bulk_edits.py). Caps
    # matches per op so a bad pattern can't rewrite a whole huge document.
    bulk_max_matches: int = 5_000

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
