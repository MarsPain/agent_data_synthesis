from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from awm_runtime.runtime import RuntimeMetadata
from synthesis.contracts import validate_episode_log_record


@dataclass(frozen=True)
class EpisodeTransition:
    transition_index: int
    event_type: str
    tool_name: str | None = None
    arguments: Mapping[str, object] | None = None
    observation: Mapping[str, object] | None = None
    change: Mapping[str, object] | None = None
    content: str | None = None
    error: Mapping[str, object] | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "transition_index": self.transition_index,
            "event_type": self.event_type,
        }
        if self.tool_name is not None:
            record["tool_name"] = self.tool_name
        if self.arguments is not None:
            arguments = sanitize_episode_value(dict(self.arguments))
            record["arguments_hash"] = deterministic_content_hash(arguments)
            record["arguments"] = arguments
        if self.observation is not None:
            observation = sanitize_episode_value(dict(self.observation))
            record["observation_hash"] = deterministic_content_hash(observation)
            record["observation"] = observation
        if self.change is not None:
            change = sanitize_episode_value(dict(self.change))
            record["change_hash"] = deterministic_content_hash(change)
            record["change"] = change
        if self.content is not None:
            content = _exportable_sanitized_value(self.content)
            record["content_hash"] = deterministic_content_hash(content)
            record["content"] = content
        if self.error is not None:
            error = sanitize_episode_value(dict(self.error))
            record["error_hash"] = deterministic_content_hash(error)
            record["error"] = error
        return record


@dataclass(frozen=True)
class EpisodeLog:
    episode_id: str
    candidate_id: str
    runtime: RuntimeMetadata
    policy: Any
    verifier: Any
    transitions: tuple[EpisodeTransition, ...]
    outcome_status: str
    failure_cause: str | None = None

    def export(self) -> dict[str, object]:
        runtime_record = self.runtime.export()
        record: dict[str, object] = {
            "schema_version": "episode_log_v1",
            "episode_id": self.episode_id,
            "candidate_id": self.candidate_id,
            "runtime": {
                "schema_version": runtime_record["schema_version"],
                "runtime_id": runtime_record["runtime_id"],
                "runtime_version": runtime_record["runtime_version"],
            },
            "policy": {
                "policy_id": self.policy.policy_id,
                "role": self.policy.role,
            },
            "verifier": {
                "id": getattr(self.verifier, "verifier_id", "unknown_verifier"),
                "version": getattr(self.verifier, "version", "unknown_verifier_version"),
            },
            "transitions": [transition.export() for transition in self.transitions],
            "outcome": {
                "status": self.outcome_status,
                "failure_cause": self.failure_cause,
            },
        }
        validate_episode_log_record(record)
        return record


def build_episode_log(
    *,
    candidate_id: str,
    runtime_metadata: RuntimeMetadata,
    policy: Any,
    verifier: Any,
    trajectory: Sequence[Mapping[str, object]],
    outcome_status: str,
    failure_cause: str | None = None,
) -> EpisodeLog:
    transitions = tuple(
        _transition_from_event(index, event)
        for index, event in enumerate(trajectory, start=1)
    )
    return EpisodeLog(
        episode_id=f"episode_sample_{candidate_id}",
        candidate_id=candidate_id,
        runtime=runtime_metadata,
        policy=policy,
        verifier=verifier,
        transitions=transitions,
        outcome_status=outcome_status,
        failure_cause=failure_cause,
    )


def deterministic_content_hash(value: object) -> str:
    sanitized = _exportable_sanitized_value(value)
    payload = json.dumps(
        sanitized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sanitize_episode_value(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested in sorted(value.items(), key=lambda item: str(item[0])):
            key = str(raw_key)
            if _is_forbidden_key(key):
                continue
            nested_value = sanitize_episode_value(nested)
            if nested_value is _REDACTED:
                continue
            sanitized[key] = nested_value
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [
            nested_value
            for item in value
            if (nested_value := sanitize_episode_value(item)) is not _REDACTED
        ]
    if isinstance(value, str):
        return _REDACTED if _is_forbidden_string(value) else value
    return value


def summarize_episode_for_quality(record: Mapping[str, object]) -> dict[str, object]:
    validate_episode_log_record(record)
    transitions = record["transitions"]
    assert isinstance(transitions, Sequence)
    runtime = record["runtime"]
    outcome = record["outcome"]
    assert isinstance(runtime, Mapping)
    assert isinstance(outcome, Mapping)
    tool_names: list[str] = []
    for transition in transitions:
        if not isinstance(transition, Mapping) or transition.get("tool_name") is None:
            continue
        tool_name = str(transition.get("tool_name"))
        if tool_name not in tool_names:
            tool_names.append(tool_name)
    return {
        "runtime_id": str(runtime["runtime_id"]),
        "outcome_status": str(outcome["status"]),
        "action_count": _transition_count(transitions, "action"),
        "observation_count": _transition_count(transitions, "observation"),
        "state_change_count": _transition_count(transitions, "state_change"),
        "final_response_count": _transition_count(transitions, "final_response"),
        "tool_names": tool_names,
    }


def _transition_from_event(index: int, event: Mapping[str, object]) -> EpisodeTransition:
    event_type = str(event.get("type", ""))
    tool_name = str(event["tool"]) if "tool" in event else None
    if event_type == "action":
        arguments = event.get("arguments")
        return EpisodeTransition(
            transition_index=index,
            event_type="action",
            tool_name=tool_name,
            arguments=arguments if isinstance(arguments, Mapping) else {},
        )
    if event_type == "observation":
        observation = event.get("observation")
        return EpisodeTransition(
            transition_index=index,
            event_type="observation",
            tool_name=tool_name,
            observation=observation if isinstance(observation, Mapping) else {},
        )
    if event_type == "state_change":
        change = event.get("change")
        return EpisodeTransition(
            transition_index=index,
            event_type="state_change",
            tool_name=tool_name,
            change=change if isinstance(change, Mapping) else {},
        )
    if event_type == "final_response":
        return EpisodeTransition(
            transition_index=index,
            event_type="final_response",
            content=str(event.get("content", "")),
        )
    return EpisodeTransition(
        transition_index=index,
        event_type="error",
        tool_name=tool_name,
        error={
            "source_event_type": event_type or "unknown",
            "message": str(event.get("message", "Unsupported trajectory event")),
        },
    )


def _transition_count(transitions: Sequence[object], event_type: str) -> int:
    return sum(
        1
        for transition in transitions
        if isinstance(transition, Mapping) and transition.get("event_type") == event_type
    )


def _exportable_sanitized_value(value: object) -> object:
    sanitized = sanitize_episode_value(value)
    if sanitized is _REDACTED:
        return "[redacted]"
    return sanitized


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        fragment in lowered
        for fragment in (
            "api_key",
            "authorization",
            "credential",
            "environment_variable",
            "header",
            "path",
            "profile",
            "provider_payload",
            "provider_prompt",
            "raw_payload",
            "secret",
        )
    )


def _is_forbidden_string(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("/")
        or lowered.startswith("~")
        or ":\\" in lowered
        or "/users/" in lowered
        or "/private/" in lowered
        or "/tmp/" in lowered
        or "agent_data_api_key" in lowered
        or "authorization:" in lowered
        or "secret-test-key" in lowered
        or "sk-live" in lowered
        or "sk-test" in lowered
    )


class _Redacted:
    pass


_REDACTED = _Redacted()
