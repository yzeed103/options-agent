"""Environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MARKET_CACHE_TTL = 30


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{key} must be positive, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings resolved once at startup."""

    database_path: Path
    legacy_data_file: Path
    anthropic_api_key: str | None
    anthropic_model: str
    anthropic_max_tokens: int
    market_cache_ttl: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        api_key = (env.get("ANTHROPIC_API_KEY") or "").strip() or None
        return cls(
            database_path=Path(env.get("OPTIONS_DB_PATH", "contracts.db")),
            legacy_data_file=Path(env.get("OPTIONS_LEGACY_JSON", "contracts.json")),
            anthropic_api_key=api_key,
            anthropic_model=env.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
            anthropic_max_tokens=_env_int(env, "ANTHROPIC_MAX_TOKENS", DEFAULT_MAX_TOKENS),
            market_cache_ttl=_env_int(env, "MARKET_CACHE_TTL", DEFAULT_MARKET_CACHE_TTL),
        )
