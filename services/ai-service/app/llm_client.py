"""COGNIFY ai-service — LLM client abstraction (Step 7).

The diagnosis service never gives the LLM database access: callers pass
only the rendered ``{system, user}`` prompt built from an EvidencePack
(see ``prompt.py``). This module defines:

- ``LLMError`` / ``LLMUnavailableError`` — failure signals that trigger
  the deterministic fallback classifier (never a retry storm).
- ``BaseLLMClient`` — minimal interface: ``complete(system, user) -> str``
  returning the model's RAW text (expected to be a single JSON object).
- ``MockLLMClient`` — scripted fake for unit tests (no network).
- ``UnavailableLLMClient`` — always raises (simulates outage / no key).
- ``OpenAICompatibleLLMClient`` — thin ``httpx`` wrapper for an
  OpenAI-compatible ``/chat/completions`` endpoint. API key and model come
  from :mod:`config` (environment variables); nothing is hard-coded.

NOT implemented here: diagnosis validation, mastery, hints, adaptive
decisions, database access.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMError(RuntimeError):
    """Base LLM failure (transport, auth, malformed response envelope)."""


class LLMUnavailableError(LLMError):
    """The LLM cannot be reached or is not configured (use fallback)."""


class BaseLLMClient(ABC):
    """Minimal LLM interface for diagnosis (prompt in, raw text out)."""

    @abstractmethod
    def complete(self, *, system: str, user: str) -> str:
        """Return the model's raw text for the ``{system, user}`` prompt."""
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        return "unknown"


class MockLLMClient(BaseLLMClient):
    """Scripted fake: returns canned text or raises a canned error."""

    def __init__(
        self,
        text: str = "",
        *,
        error: BaseException | None = None,
        model: str = "mock",
    ) -> None:
        self._text = text
        self._error = error
        self._model = model
        self.calls: list[dict[str, str]] = []

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if self._error is not None:
            raise self._error
        return self._text


class UnavailableLLMClient(BaseLLMClient):
    """Always-unavailable client (outage / missing key simulation)."""

    def __init__(self, message: str = "LLM is not configured.", *, model: str = "none") -> None:
        self._message = message
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, *, system: str, user: str) -> str:
        raise LLMUnavailableError(self._message)


class OpenAICompatibleLLMClient(BaseLLMClient):
    """Thin httpx client for OpenAI-compatible chat completions.

    Args:
        api_key: bearer token (from ``LLM_API_KEY`` env — never hard-code).
        model: model name (from ``LLM_MODEL`` env).
        base_url: e.g. ``https://api.openai.com/v1`` (from ``LLM_BASE_URL``).
        timeout_seconds: HTTP timeout.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string (from LLM_API_KEY).")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string (from LLM_MODEL).")
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_seconds)

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, *, system: str, user: str) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise LLMUnavailableError("httpx is not installed.") from exc
        url = f"{self._base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        except Exception as exc:
            raise LLMUnavailableError(f"LLM request failed: {exc}.") from exc
        if response.status_code in (401, 403):
            raise LLMUnavailableError(f"LLM auth failed (HTTP {response.status_code}).")
        if response.status_code == 429:
            raise LLMUnavailableError("LLM rate-limited (HTTP 429).")
        if response.status_code >= 400:
            raise LLMError(f"LLM request failed (HTTP {response.status_code}).")
        try:
            body = response.json()
            return str(body["choices"][0]["message"]["content"])
        except Exception as exc:
            raise LLMError(f"LLM returned an unreadable envelope: {exc}.") from exc


__all__ = [
    "BaseLLMClient",
    "LLMError",
    "LLMUnavailableError",
    "MockLLMClient",
    "OpenAICompatibleLLMClient",
    "UnavailableLLMClient",
]
