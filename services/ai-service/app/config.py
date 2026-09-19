"""COGNIFY ai-service — LLM configuration from environment (Step 7).

All secrets come from environment variables. No API key is hard-coded
anywhere in this service; ``get_llm_config`` reads only the process
environment and raises when a keyed provider is configured without a key.

Supported variables (see ``services/ai-service/.env.example``):

- LLM_PROVIDER: "" (disabled/fallback-only) | "openai" | "mock"
- LLM_API_KEY: secret key for the provider (required unless disabled/mock)
- LLM_MODEL: model name (e.g. "gpt-4o-mini"); has a safe default
- LLM_BASE_URL: optional override for OpenAI-compatible endpoints
- LLM_TIMEOUT_SECONDS: HTTP timeout (float, default 30.0)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL: str = "gpt-4o-mini"
DEFAULT_BASE_URL: str = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS: float = 30.0

SUPPORTED_PROVIDERS: tuple[str, ...] = ("", "openai", "mock")


@dataclass(frozen=True)
class LLMConfig:
    provider: str  # "" | "openai" | "mock"
    api_key: str  # "" when provider is "" or "mock"
    model: str
    base_url: str
    timeout_seconds: float

    @property
    def enabled(self) -> bool:
        return self.provider not in ("",)


def _read_env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    if not isinstance(value, str):
        return default
    return value.strip()


def get_llm_config(env: dict[str, str] | None = None) -> LLMConfig:
    """Read LLM configuration from the environment (or a mapping).

    Args:
        env: optional mapping to read instead of ``os.environ``
            (used by unit tests; production passes None).

    Raises:
        ValueError: on unknown provider, bad timeout, or a keyed
            provider without ``LLM_API_KEY``.
    """
    source = env if env is not None else os.environ
    provider = str(source.get("LLM_PROVIDER", "") or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER {provider!r}. Use one of {list(SUPPORTED_PROVIDERS)}."
        )
    api_key = str(source.get("LLM_API_KEY", "") or "").strip()
    model = str(source.get("LLM_MODEL", "") or "").strip() or DEFAULT_MODEL
    base_url = str(source.get("LLM_BASE_URL", "") or "").strip() or DEFAULT_BASE_URL
    raw_timeout = str(source.get("LLM_TIMEOUT_SECONDS", "") or "").strip()
    timeout = DEFAULT_TIMEOUT_SECONDS
    if raw_timeout:
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError(
                f"LLM_TIMEOUT_SECONDS must be a number, got {raw_timeout!r}."
            ) from exc
        if not 1.0 <= timeout <= 120.0:
            raise ValueError(
                f"LLM_TIMEOUT_SECONDS must be in [1.0, 120.0], got {timeout!r}."
            )
    if provider == "openai" and not api_key:
        raise ValueError("LLM_API_KEY is required when LLM_PROVIDER='openai'.")
    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout,
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "LLMConfig",
    "SUPPORTED_PROVIDERS",
    "get_llm_config",
]
