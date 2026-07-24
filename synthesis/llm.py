from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


LLM_BASE_URL_ENV = "AGENT_DATA_LLM_BASE_URL"
LLM_API_KEY_ENV = "AGENT_DATA_API_KEY"
LLM_MODEL_ENV = "AGENT_DATA_LLM_MODEL"
LLM_TEMPERATURE_ENV = "AGENT_DATA_LLM_TEMPERATURE"
REQUIRED_LLM_ENV_MESSAGE = (
    f"{LLM_BASE_URL_ENV}, {LLM_API_KEY_ENV}, and {LLM_MODEL_ENV} "
    "are required for remote generation"
)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str | None
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    temperature: float | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.environ.get(LLM_BASE_URL_ENV),
            api_key=os.environ.get(LLM_API_KEY_ENV),
            model=os.environ.get(LLM_MODEL_ENV),
            temperature=_temperature_from_env(os.environ.get(LLM_TEMPERATURE_ENV)),
        )

    @property
    def effective_temperature(self) -> float:
        return self.temperature if self.temperature is not None else 0.0

    @property
    def provider_host(self) -> str:
        if not self.base_url:
            return "unconfigured"
        parsed = urlparse(self.base_url)
        return parsed.netloc or parsed.path or "unconfigured"

    @property
    def api_key_present(self) -> bool:
        return bool(self.api_key)

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key_present and self.model)

    def lineage(self, role: str) -> dict[str, object]:
        config_fingerprint = "|".join(
            [
                self.provider_host,
                self.model or "unconfigured",
                "api_key_present" if self.api_key_present else "api_key_missing",
            ]
        )
        config_hash = hashlib.sha256(config_fingerprint.encode("utf-8")).hexdigest()
        return {
            "role": role,
            "provider_host": self.provider_host,
            "model": self.model or "unconfigured",
            "config_hash": config_hash,
            "configured": self.configured,
            "temperature": self.effective_temperature,
        }


def _temperature_from_env(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise LLMConfigurationError(
            f"{LLM_TEMPERATURE_ENV} must be a finite float in [0.0, 1.0]"
        ) from exc
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise LLMConfigurationError(
            f"{LLM_TEMPERATURE_ENV} must be a finite float in [0.0, 1.0]"
        )
    return value


@dataclass(frozen=True)
class LLMGenerationResult:
    content: dict[str, Any]
    lineage: dict[str, object]


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        *,
        cause: str = "llm_provider_error",
        error_class: str = "LLMProviderError",
        retryable: bool = False,
        retry_count: int = 0,
        lineage: dict[str, object] | None = None,
        schema_reason: str | None = None,
        schema_detail: str | None = None,
    ) -> None:
        super().__init__(f"Remote LLM generation failed: {error_class}")
        self.cause = cause
        self.error_class = error_class
        self.retryable = retryable
        self.retry_count = retry_count
        self.lineage = dict(lineage) if lineage else {}
        self.schema_reason = schema_reason
        self.schema_detail = schema_detail


class OpenAICompatibleClient:
    def __init__(
        self,
        config: LLMConfig,
        *,
        http_client: httpx.Client | None = None,
        max_retries: int = 2,
        sleeper: Callable[[float], None] | None = None,
        retry_delay_seconds: float = 0.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self._http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self._max_retries = max(0, max_retries)
        self._sleeper = sleeper or time.sleep
        self._retry_delay_seconds = retry_delay_seconds
        self._timeout_seconds = timeout_seconds

    def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
        if not self.config.configured:
            raise LLMConfigurationError(REQUIRED_LLM_ENV_MESSAGE)

        for attempt in range(self._max_retries + 1):
            try:
                response = self._http_client.post(
                    self._chat_completions_url(),
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json={
                        "model": self.config.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Return strict JSON only.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": self.config.effective_temperature,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                content = _parse_chat_completion_json_content(payload)
                lineage = self.config.lineage(role)
                lineage["tokens"] = payload.get("usage", {})
                lineage["retry_count"] = attempt
                lineage["error_class"] = None
                lineage["prompt_hash"] = _hash_text(prompt)
                return LLMGenerationResult(content=content, lineage=lineage)
            except httpx.HTTPStatusError as exc:
                retryable = _retryable_status(exc.response.status_code)
                if retryable and attempt < self._max_retries:
                    self._sleep_before_retry()
                    continue
                raise LLMProviderError(
                    cause="llm_provider_error",
                    error_class=type(exc).__name__,
                    retryable=retryable,
                    retry_count=attempt,
                    lineage=self._error_lineage(
                        role=role,
                        prompt=prompt,
                        error_class=type(exc).__name__,
                        retry_count=attempt,
                    ),
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self._max_retries:
                    self._sleep_before_retry()
                    continue
                raise LLMProviderError(
                    cause="llm_provider_error",
                    error_class=type(exc).__name__,
                    retryable=True,
                    retry_count=attempt,
                    lineage=self._error_lineage(
                        role=role,
                        prompt=prompt,
                        error_class=type(exc).__name__,
                        retry_count=attempt,
                    ),
                ) from exc
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise LLMProviderError(
                    cause="llm_response_schema_error",
                    error_class=type(exc).__name__,
                    retryable=False,
                    retry_count=attempt,
                    lineage=self._error_lineage(
                        role=role,
                        prompt=prompt,
                        error_class=type(exc).__name__,
                        retry_count=attempt,
                    ),
                ) from exc

        raise LLMProviderError()

    def _chat_completions_url(self) -> str:
        assert self.config.base_url is not None
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    def _sleep_before_retry(self) -> None:
        if self._retry_delay_seconds <= 0:
            return
        self._sleeper(self._retry_delay_seconds)

    def _error_lineage(
        self,
        *,
        role: str,
        prompt: str,
        error_class: str,
        retry_count: int,
    ) -> dict[str, object]:
        lineage = self.config.lineage(role)
        lineage["tokens"] = {}
        lineage["retry_count"] = retry_count
        lineage["error_class"] = error_class
        lineage["prompt_hash"] = _hash_text(prompt)
        return lineage


def _parse_chat_completion_json_content(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise TypeError("chat completion content must be a JSON string")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("chat completion JSON content must be an object")
    return parsed


def _retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
