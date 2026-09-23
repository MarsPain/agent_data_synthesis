"""Public Episode persistence models and export sanitization."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_serializer,
    model_validator,
)


class ToolDefinition(BaseModel):
    """One public tool and its bounded input/output fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2_000)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] = Field(default_factory=dict)


class PublicTask(BaseModel):
    """The public view of a compiled task; it intentionally has no oracle data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instruction: str = Field(min_length=1, max_length=8_000)
    tools: tuple[ToolDefinition, ...] = Field(min_length=1)


_EVENT_ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    "action": frozenset({"tool_name", "arguments"}),
    "observation": frozenset({"tool_name", "observation"}),
    "state_change": frozenset({"tool_name", "change"}),
    "final_response": frozenset({"content"}),
    "error": frozenset({"tool_name", "error_code"}),
}
_EVENT_PAYLOAD_FIELD_SCOPES = {
    "arguments": "input",
    "observation": "output",
    "change": "output",
}


class EpisodeEvent(BaseModel):
    """A bounded observable event emitted by a Domain-owned Episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["action", "observation", "state_change", "final_response", "error"]
    tool_name: str | None = Field(default=None, min_length=1, max_length=128)
    arguments: dict[str, JsonValue] | None = None
    observation: dict[str, JsonValue] | None = None
    change: dict[str, JsonValue] | None = None
    content: str | None = Field(default=None, max_length=8_000)
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    @model_validator(mode="after")
    def _allow_only_the_payload_for_each_event_type(self) -> EpisodeEvent:
        allowed_fields = _EVENT_ALLOWED_FIELDS[self.event_type]
        if any(
            getattr(self, field_name) is not None
            for field_name in _event_data_field_names()
            if field_name not in allowed_fields
        ):
            raise ValueError(f"{self.event_type} event has an unsupported payload field")
        if self.event_type == "final_response" and self.content is None:
            raise ValueError("final_response event requires content")
        if self.event_type == "error" and self.error_code is None:
            raise ValueError("error event requires error_code")
        return self


class ExecutionTrace(BaseModel):
    """Observable execution returned by a Domain-owned Episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mutation_authorization: Literal["not_applicable", "authorized", "rejected"]
    events: tuple[EpisodeEvent, ...]


class AssessmentCheck(BaseModel):
    """One bounded deterministic assessment result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    passed: bool


class EpisodeAssessment(BaseModel):
    """Domain-owned deterministic assessment exposed in an Episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: tuple[AssessmentCheck, ...]
    reason_codes: tuple[str, ...]
    coverage_tags: tuple[str, ...]
    structural_key: str = Field(min_length=1, max_length=512)
    state_change_evidence: str | None = Field(default=None, max_length=512)


class EpisodeOutcome(BaseModel):
    """Collection placement and bounded terminal outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection: Literal["demonstrations", "negatives"]
    status: Literal["succeeded", "rejected_before_execution", "rejected_after_execution"]
    reason_code: str | None = Field(default=None, max_length=128)


class DeterministicAdmissionGates(BaseModel):
    """The fixed hard gates required before an Episode enters demonstrations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution: bool
    mutation_authorization: bool
    assessment: bool
    final_grounding: bool
    unsafe_material: bool
    semantic_key: bool

    @property
    def passed(self) -> bool:
        """Return whether every deterministic gate has passed."""

        return all(
            (
                self.execution,
                self.mutation_authorization,
                self.assessment,
                self.final_grounding,
                self.unsafe_material,
                self.semantic_key,
            )
        )


class AdmissionRecord(BaseModel):
    """Admission is explicit and never implies human approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["deterministic", "enforced"]
    status: Literal["admitted", "rejected"]
    gates: DeterministicAdmissionGates
    human_review_status: Literal["unreviewed"] = "unreviewed"
    semantic_judgment: Literal[
        "not_requested", "pass", "fail", "uncertain", "unavailable"
    ] = "not_requested"
    semantic_policy_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )

    @model_validator(mode="after")
    def _require_all_deterministic_gates_for_admission(self) -> "AdmissionRecord":
        if self.status == "admitted" and not self.gates.passed:
            raise ValueError("admitted Episodes must pass every deterministic gate")
        if self.mode == "deterministic":
            if self.semantic_judgment != "not_requested" or self.semantic_policy_id is not None:
                raise ValueError("deterministic admission cannot claim semantic enforcement")
        else:
            if self.semantic_policy_id is None:
                raise ValueError("enforced admission requires a semantic policy identity")
            if self.semantic_judgment == "not_requested":
                raise ValueError("enforced admission requires an explicit judge result")
            if self.status == "admitted" and self.semantic_judgment != "pass":
                raise ValueError("enforced admission requires a judge pass")
        return self

    @model_serializer(mode="wrap")
    def _serialize_without_enforcement_fields_for_shadow_runs(
        self,
        handler: object,
    ) -> dict[str, object]:
        """Keep established deterministic Episode exports byte-shape compatible."""

        serialized = handler(self)
        assert isinstance(serialized, dict)
        if self.mode == "deterministic":
            serialized.pop("semantic_judgment", None)
            serialized.pop("semantic_policy_id", None)
        return serialized


class ModelLineage(BaseModel):
    """Sanitized model identity only; raw provider data is deliberately absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    roles: tuple[RoleLineage, ...] = ()


class RoleLineage(BaseModel):
    """Bounded per-role request evidence without provider payloads or credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["task_generation", "agent", "quality_judge"]
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    physical_request_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    response_hashes: tuple[str, ...] = Field(
        default=(),
        max_length=128,
    )
    known_input_tokens: int | None = Field(default=None, ge=0)
    known_output_tokens: int | None = Field(default=None, ge=0)
    known_total_tokens: int | None = Field(default=None, ge=0)
    unknown_usage_count: int = Field(ge=0)


class PublicEpisode(BaseModel):
    """The complete public artifact for one terminal synthesis attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_episode_v1"] = "agent_episode_v1"
    episode_id: str = Field(min_length=1, max_length=256)
    candidate_id: str = Field(min_length=1, max_length=256)
    sequence: int = Field(ge=1)
    domain_id: str = Field(min_length=1, max_length=128)
    domain_version: str = Field(min_length=1, max_length=128)
    task: PublicTask
    events: tuple[EpisodeEvent, ...]
    mutation_authorization: Literal["not_applicable", "authorized", "rejected"] = (
        "not_applicable"
    )
    outcome: EpisodeOutcome
    verification: EpisodeAssessment | None = None
    admission: AdmissionRecord
    lineage: ModelLineage


_FORBIDDEN_KEY_PARTS = (
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "analysis",
    "cookie",
    "completion",
    "credential",
    "expected",
    "ground_truth",
    "hidden_reasoning",
    "http_body",
    "oracle",
    "passwd",
    "password",
    "private",
    "provider",
    "provider_payload",
    "raw_payload",
    "raw",
    "reasoning",
    "response",
    "secret",
    "session",
    "source_path",
    "thought",
    "token",
)
_SAFE_LINEAGE_KEYS = frozenset(
    {
        "provider_id",
        "response_hashes",
        "known_input_tokens",
        "known_output_tokens",
        "known_total_tokens",
        "unknown_usage_count",
        "physical_request_count",
        "retry_count",
        "repair_request_count",
        "mutation_authorization",
    }
)
_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_ABSOLUTE_PATH_IN_TEXT = re.compile(
    r"(?<![:/A-Za-z0-9_.-])/(?!/)"
    r"|(?<![A-Za-z0-9_.-])[A-Za-z]:[\\/]"
    r"|(?:^|\s)~[\\/]"
)


def sanitized_episode_record(episode: PublicEpisode) -> dict[str, object]:
    """Serialize an Episode after stripping material prohibited from export."""

    record = _sanitize_value(episode.model_dump(mode="json"))
    assert isinstance(record, dict)
    _limit_event_payloads(record, episode.task.tools)
    return PublicEpisode.model_validate(record).model_dump(mode="json")


def has_unsafe_public_material(value: object) -> bool:
    """Detect data that the public sanitizer would redact before admission uses it.

    Detection is deliberately separate from redaction: public exports remain
    safe, while a detected secret/oracle/provider-shaped value is still a hard
    deterministic admission failure rather than a silently cleaned success.
    """

    if isinstance(value, BaseModel):
        return has_unsafe_public_material(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return any(
            _forbidden_key(key) or has_unsafe_public_material(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(has_unsafe_public_material(item) for item in value)
    return isinstance(value, str) and _forbidden_text(value)


def sanitized_public_task(task: PublicTask) -> PublicTask:
    """Return the part of a Domain task safe to expose to an Agent model."""

    record = _sanitize_value(task.model_dump(mode="json"))
    assert isinstance(record, dict)
    return PublicTask.model_validate(record)


def bounded_event_for_public_tools(
    event: EpisodeEvent,
    tools: tuple[ToolDefinition, ...],
) -> EpisodeEvent:
    """Strip undeclared, secret-shaped, and unbounded payload data before reuse."""

    record = _sanitize_value(event.model_dump(mode="json", exclude_none=True))
    assert isinstance(record, dict)
    wrapper: dict[str, object] = {"events": [record]}
    _limit_event_payloads(wrapper, tools)
    return EpisodeEvent.model_validate(record)


def _sanitize_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _sanitize_value(nested)
            for key, nested in value.items()
            if not _forbidden_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and _forbidden_text(value):
        return "[redacted]"
    return value


def _forbidden_key(key: object) -> bool:
    lowered = str(key).lower()
    if lowered in _SAFE_LINEAGE_KEYS:
        return False
    return any(part in lowered for part in _FORBIDDEN_KEY_PARTS)


def _forbidden_text(value: str) -> bool:
    lowered = value.lower()
    return (
        value.startswith(("/", "~"))
        or bool(_ABSOLUTE_PATH.match(value))
        or bool(_ABSOLUTE_PATH_IN_TEXT.search(value))
        or "/users/" in lowered
        or "/private/" in lowered
        or "/tmp/" in lowered
        or "file://" in lowered
        or "authorization:" in lowered
        or lowered.startswith(("sk-", "bearer "))
        or any(
            marker in lowered
            for marker in (
                "api_key",
                "credential",
                "passwd",
                "password",
                "secret",
                "access_token",
            )
        )
    )


def _limit_event_payloads(
    record: dict[str, object],
    tools: tuple[ToolDefinition, ...],
) -> None:
    """Retain only Domain-declared observable fields in event payloads."""

    tool_fields = {
        tool.name: (
            _schema_property_names(tool.input_schema),
            _schema_property_names(tool.output_schema),
        )
        for tool in tools
    }
    events = record.get("events")
    if not isinstance(events, list):
        return
    for event in events:
        if not isinstance(event, dict):
            continue
        tool_name = event.get("tool_name")
        input_fields, output_fields = tool_fields.get(
            tool_name if isinstance(tool_name, str) else "",
            (frozenset(), frozenset()),
        )
        event_type = event.get("event_type")
        allowed_fields = _EVENT_ALLOWED_FIELDS.get(
            event_type if isinstance(event_type, str) else "",
            frozenset(),
        )
        for payload_name, field_scope in _EVENT_PAYLOAD_FIELD_SCOPES.items():
            if payload_name not in allowed_fields:
                continue
            allowed_payload_fields = (
                input_fields if field_scope == "input" else output_fields
            )
            _allow_payload_fields(event, payload_name, allowed_payload_fields)


def _schema_property_names(schema: dict[str, JsonValue]) -> frozenset[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return frozenset()
    return frozenset(str(name) for name in properties)


def _allow_payload_fields(
    event: dict[str, object],
    payload_name: str,
    allowed_fields: frozenset[str],
) -> None:
    payload = event.get(payload_name)
    if not isinstance(payload, dict):
        return
    event[payload_name] = {
        field_name: value
        for field_name, value in payload.items()
        if field_name in allowed_fields
    }


def _event_data_field_names() -> tuple[str, ...]:
    return (
        "tool_name",
        "arguments",
        "observation",
        "change",
        "content",
        "error_code",
    )
