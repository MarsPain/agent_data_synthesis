from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx


LLM_BASE_URL_ENV = "AGENT_DATA_LLM_BASE_URL"
LLM_API_KEY_ENV = "AGENT_DATA_API_KEY"
LLM_MODEL_ENV = "AGENT_DATA_LLM_MODEL"
REQUIRED_LLM_ENV_MESSAGE = (
    f"{LLM_BASE_URL_ENV}, {LLM_API_KEY_ENV}, and {LLM_MODEL_ENV} "
    "are required for remote generation"
)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str | None
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.environ.get(LLM_BASE_URL_ENV),
            api_key=os.environ.get(LLM_API_KEY_ENV),
            model=os.environ.get(LLM_MODEL_ENV),
        )

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
        }


@dataclass(frozen=True)
class LLMGenerationResult:
    content: dict[str, Any]
    lineage: dict[str, object]


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(
        self,
        config: LLMConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._http_client = http_client or httpx.Client(timeout=30.0)

    def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
        if not self.config.configured:
            raise LLMConfigurationError(REQUIRED_LLM_ENV_MESSAGE)

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
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()
            content = _parse_chat_completion_json_content(payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"Remote LLM generation failed: {type(exc).__name__}") from exc

        lineage = self.config.lineage(role)
        lineage["tokens"] = payload.get("usage", {})
        lineage["retry_count"] = 0
        lineage["error_class"] = None
        return LLMGenerationResult(content=content, lineage=lineage)

    def _chat_completions_url(self) -> str:
        assert self.config.base_url is not None
        return f"{self.config.base_url.rstrip('/')}/chat/completions"


def _parse_chat_completion_json_content(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise TypeError("chat completion content must be a JSON string")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("chat completion JSON content must be an object")
    return parsed
