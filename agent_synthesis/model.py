"""Provider-neutral strict-JSON model contracts and adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from agent_synthesis.domain import TaskSlot
from agent_synthesis.episode import EpisodeEvent, PublicTask

type ModelRole = Literal["task_generation", "agent"]
_SAFE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class TokenUsage(BaseModel):
    """Provider-reported token counts, deliberately allowing unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class TaskGenerationRequest(BaseModel):
    """One bounded batch of Domain-issued slots sent to a JSON model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["task_generation"] = "task_generation"
    slots: tuple[TaskSlot, ...] = Field(min_length=1, max_length=64)
    timeout_seconds: float = Field(gt=0, le=300)
    max_response_bytes: int = Field(ge=256, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=32_768)

    def model_context(self) -> dict[str, JsonValue]:
        """Return the only generation data serialized into the provider prompt."""

        return {"slots": [slot.model_dump(mode="json") for slot in self.slots]}

    def response_contract(self) -> dict[str, JsonValue]:
        """Return the strict, role-owned output shape supplied to the model."""

        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["proposals"],
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["slot_id", "content"],
                        "properties": {
                            "slot_id": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                }
            },
        }


class AgentRequest(BaseModel):
    """The complete, bounded context exposed to an Agent model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["agent"] = "agent"
    task: PublicTask
    observable_history: tuple[EpisodeEvent, ...]
    remaining_step_budget: int = Field(ge=1, le=64)
    timeout_seconds: float = Field(gt=0, le=300)
    max_response_bytes: int = Field(ge=256, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=32_768)

    def model_context(self) -> dict[str, JsonValue]:
        """Return exactly the public Agent context, excluding dispatch controls."""

        return {
            "task": self.task.model_dump(mode="json"),
            "observable_history": [
                event.model_dump(mode="json", exclude_none=True)
                for event in self.observable_history
            ],
            "remaining_step_budget": self.remaining_step_budget,
        }

    def response_contract(self) -> dict[str, JsonValue]:
        """Return the one-decision JSON union enforced for Agent responses."""

        return {
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "tool_name", "arguments"],
                    "properties": {
                        "type": {"const": "tool_call"},
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "content"],
                    "properties": {
                        "type": {"const": "final_response"},
                        "content": {"type": "string"},
                    },
                },
            ]
        }


type JsonModelRequest = TaskGenerationRequest | AgentRequest


class JsonModelResponse(BaseModel):
    """Sanitized JSON output and optional provider usage from one physical call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: dict[str, JsonValue]
    usage: TokenUsage | None = None
    response_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def effective_response_hash(self) -> str:
        """Return the supplied hash or a deterministic hash of the JSON content."""

        if self.response_hash is not None:
            return self.response_hash
        serialized = json.dumps(
            self.content,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(serialized).hexdigest()


class GeneratedProposal(BaseModel):
    """One untrusted proposal assigned only to a persisted Domain slot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=16_000)


class GenerationResponse(BaseModel):
    """The strict JSON shape expected from a task-generation batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposals: tuple[GeneratedProposal, ...] = Field(min_length=1, max_length=64)


class ToolCallDecision(BaseModel):
    """One Agent decision to invoke exactly one declared tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tool_call"]
    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, JsonValue]


class FinalResponseDecision(BaseModel):
    """One Agent decision to finish an Episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["final_response"]
    content: str = Field(min_length=1, max_length=8_000)


type AgentDecision = ToolCallDecision | FinalResponseDecision


def parse_agent_decision(content: dict[str, JsonValue]) -> AgentDecision:
    """Parse one strict decision without admitting rationale or extra keys."""

    decision_type = content.get("type")
    if decision_type == "tool_call":
        return ToolCallDecision.model_validate(content)
    if decision_type == "final_response":
        return FinalResponseDecision.model_validate(content)
    raise ValueError("agent decision type must be tool_call or final_response")


@runtime_checkable
class JsonModelAdapter(Protocol):
    """One physical request through the shared provider-neutral JSON contract."""

    model_id: str
    model_version: str
    provider_id: str

    def complete(self, request: JsonModelRequest) -> JsonModelResponse: ...


class ModelCallError(RuntimeError):
    """A bounded provider failure that never retains raw payload material."""

    def __init__(
        self,
        error_code: str,
        *,
        retryable: bool,
        response_hash: str | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        self.error_code = (
            error_code if _SAFE_ERROR_CODE.fullmatch(error_code) else "provider_failure"
        )
        super().__init__(self.error_code)
        self.retryable = retryable
        self.response_hash = response_hash
        self.usage = usage


class DeterministicJsonModelAdapter:
    """Scripted fake sharing the production adapter's exact JSON interface."""

    provider_id = "deterministic_fake"

    def __init__(
        self,
        *,
        model_id: str,
        model_version: str,
        responses: Iterable[JsonModelResponse | dict[str, JsonValue] | Exception],
    ) -> None:
        self.model_id = model_id
        self.model_version = model_version
        self._responses = iter(responses)
        self.requests: list[JsonModelRequest] = []

    def complete(self, request: JsonModelRequest) -> JsonModelResponse:
        self.requests.append(request)
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, JsonModelResponse):
            return response
        return JsonModelResponse(content=response)


class OpenAICompatibleJsonAdapter:
    """One-request OpenAI-compatible chat adapter; retry policy stays in the engine."""

    provider_id = "openai_compatible"

    def __init__(
        self,
        *,
        model_id: str,
        model_version: str,
        base_url: str,
        api_key: str,
        remote_model: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")
        if not api_key:
            raise ValueError("api_key must not be empty")
        if not remote_model:
            raise ValueError("remote_model must not be empty")
        self.model_id = model_id
        self.model_version = model_version
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._remote_model = remote_model
        self._http_client = http_client or httpx.Client()

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleJsonAdapter("
            f"model_id={self.model_id!r}, model_version={self.model_version!r})"
        )

    def complete(self, request: JsonModelRequest) -> JsonModelResponse:
        response_contract = json.dumps(
            request.response_contract(),
            sort_keys=True,
            separators=(",", ":"),
        )
        request_body = {
            "model": self._remote_model,
            "messages": (
                {
                    "role": "system",
                    "content": (
                        "Return one strict JSON object and no commentary. "
                        "Your response must satisfy this contract exactly: "
                        f"{response_contract}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        request.model_context(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ),
            "response_format": {"type": "json_object"},
            "max_tokens": request.max_output_tokens,
        }
        response: httpx.Response | None = None
        transport_failure: ModelCallError | None = None
        try:
            response = self._http_client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request_body,
                timeout=request.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            transport_failure = ModelCallError("provider_timeout", retryable=True)
        except httpx.TransportError:
            transport_failure = ModelCallError(
                "provider_transport_failure",
                retryable=True,
            )
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            transport_failure = ModelCallError(
                "provider_http_failure",
                retryable=status_code == 429 or 500 <= status_code <= 599,
            )
        if transport_failure is not None:
            raise transport_failure
        assert response is not None

        raw_body = response.content
        response_hash = "sha256:" + hashlib.sha256(raw_body).hexdigest()
        if len(raw_body) > request.max_response_bytes:
            raise ModelCallError(
                "response_bytes_exceeded",
                retryable=False,
                response_hash=response_hash,
            )
        parsed: dict[str, JsonValue] | None = None
        usage: TokenUsage | None = None
        malformed_response = False
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("chat completion response must be an object")
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("chat completion content must be a string")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise TypeError("chat completion JSON must be an object")
            usage = _token_usage(payload.get("usage"))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            malformed_response = True
        if malformed_response:
            raise ModelCallError(
                "provider_response_malformed",
                retryable=False,
                response_hash=response_hash,
            )
        assert parsed is not None
        if (
            usage is not None
            and usage.output_tokens is not None
            and usage.output_tokens > request.max_output_tokens
        ):
            raise ModelCallError(
                "response_tokens_exceeded",
                retryable=False,
                response_hash=response_hash,
                usage=usage,
            )
        validated_response: JsonModelResponse | None = None
        validation_failed = False
        try:
            validated_response = JsonModelResponse(
                content=parsed,
                usage=usage,
                response_hash=response_hash,
            )
        except ValidationError:
            validation_failed = True
        if validation_failed:
            raise ModelCallError(
                "provider_response_malformed",
                retryable=False,
                response_hash=response_hash,
                usage=usage,
            )
        assert validated_response is not None
        return validated_response


def _token_usage(value: object) -> TokenUsage | None:
    if not isinstance(value, dict):
        return None
    input_tokens = value.get("prompt_tokens")
    output_tokens = value.get("completion_tokens")
    total_tokens = value.get("total_tokens")
    if not all(
        item is None or (isinstance(item, int) and item >= 0)
        for item in (input_tokens, output_tokens, total_tokens)
    ):
        return None
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
