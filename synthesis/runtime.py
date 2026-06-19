from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from synthesis.contracts import (
    ContractValidationError,
    validate_runtime_action_request_record,
    validate_runtime_action_result_record,
)
from synthesis.seeds import DomainSeed, foundation_seed


RUNTIME_CAPABILITY_STATUSES = frozenset(
    {
        "supported",
        "unsupported",
        "insufficient_evidence",
        "malformed",
    }
)
RUNTIME_CAPABILITY_FIELDS = frozenset(
    {
        "supports_rebuild",
        "supports_checkpoint_restore",
        "supports_episode_replay",
        "supports_reward_labels",
        "supports_local_adapter",
    }
)


@dataclass(frozen=True)
class RuntimeCapabilityDescriptor:
    runtime_id: str
    runtime_version: str
    domain_id: str
    supports_rebuild: bool
    supports_checkpoint_restore: bool
    supports_episode_replay: bool
    supports_reward_labels: bool
    supports_local_adapter: bool
    state_changing_tools: tuple[str, ...]
    task_taxonomy: tuple[str, ...]
    rebuild_seed: DomainSeed | None = None
    descriptor_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_descriptor_string(self.runtime_id, "runtime_id")
        _require_descriptor_string(self.runtime_version, "runtime_version")
        _require_descriptor_string(self.domain_id, "domain_id")
        _validate_string_tuple(self.state_changing_tools, "state_changing_tools")
        _validate_string_tuple(self.task_taxonomy, "task_taxonomy")
        if self.supports_episode_replay and not self.supports_rebuild:
            raise ContractValidationError(
                "runtime descriptor replay support requires rebuild support"
            )
        if self.supports_episode_replay and self.rebuild_seed is None:
            raise ContractValidationError(
                "runtime descriptor replay support requires a rebuild seed"
            )
        validate_runtime_descriptor_safety(self.descriptor_metadata)
        object.__setattr__(self, "state_changing_tools", tuple(self.state_changing_tools))
        object.__setattr__(self, "task_taxonomy", tuple(self.task_taxonomy))
        object.__setattr__(
            self,
            "descriptor_metadata",
            MappingProxyType(dict(self.descriptor_metadata)),
        )


class RuntimeRegistry:
    def __init__(
        self,
        descriptors: Sequence[RuntimeCapabilityDescriptor],
    ) -> None:
        by_runtime_id: dict[str, RuntimeCapabilityDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.runtime_id in by_runtime_id:
                raise ContractValidationError(
                    f"runtime descriptor is duplicated: {descriptor.runtime_id}"
                )
            by_runtime_id[descriptor.runtime_id] = descriptor
        self._descriptors = MappingProxyType(by_runtime_id)

    def registered_runtime_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptor(self, runtime_id: str) -> RuntimeCapabilityDescriptor:
        try:
            return self._descriptors[runtime_id]
        except KeyError:
            raise KeyError(f"unknown runtime descriptor: {runtime_id}") from None

    def register(self, descriptor: RuntimeCapabilityDescriptor) -> "RuntimeRegistry":
        if descriptor.runtime_id in self._descriptors:
            raise ContractValidationError(
                f"runtime descriptor is duplicated: {descriptor.runtime_id}"
            )
        return RuntimeRegistry(tuple(self._descriptors.values()) + (descriptor,))


@dataclass(frozen=True)
class RuntimeMetadata:
    runtime_id: str
    runtime_version: str
    environment_id: str
    environment_version: str
    reset_recipe: str
    state_backend: str
    checkpoint_strategy: str
    source_provenance: Mapping[str, object] = field(default_factory=dict)
    sandbox_policy: Mapping[str, object] = field(default_factory=dict)
    adapter: Mapping[str, object] = field(default_factory=dict)

    schema_version: str = "runtime_metadata_v1"

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": self.schema_version,
            "runtime_id": self.runtime_id,
            "runtime_version": self.runtime_version,
            "environment_id": self.environment_id,
            "environment_version": self.environment_version,
            "reset_recipe": self.reset_recipe,
            "state_backend": self.state_backend,
            "checkpoint_strategy": self.checkpoint_strategy,
            "source_provenance": dict(self.source_provenance),
            "sandbox_policy": dict(self.sandbox_policy),
            "adapter": dict(self.adapter),
        }
        validate_runtime_metadata_safety(record)
        return record


@dataclass(frozen=True)
class RuntimeActionRequest:
    runtime_id: str
    tool_name: str
    arguments: Mapping[str, object]
    action_id: str | None = None

    def __post_init__(self) -> None:
        _require_descriptor_string(self.runtime_id, "runtime_action.runtime_id")
        _require_descriptor_string(self.tool_name, "runtime_action.tool_name")
        if not isinstance(self.arguments, Mapping):
            raise ContractValidationError("runtime action arguments must be an object")
        if self.action_id is not None:
            _require_descriptor_string(self.action_id, "runtime_action.action_id")
        object.__setattr__(
            self,
            "arguments",
            MappingProxyType(dict(self.arguments)),
        )

    def export(self) -> dict[str, object]:
        arguments = _sanitize_runtime_action_value(dict(self.arguments))
        assert isinstance(arguments, dict)
        record: dict[str, object] = {
            "schema_version": "runtime_action_request_v1",
            "runtime_id": self.runtime_id,
            "tool_name": self.tool_name,
            "arguments": arguments,
            "arguments_hash": _runtime_content_hash(arguments),
        }
        if self.action_id is not None:
            record["action_id"] = self.action_id
        validate_runtime_action_request_record(record)
        return record


@dataclass(frozen=True)
class RuntimeActionResult:
    runtime_id: str
    tool_name: str
    status: str
    observation: Mapping[str, object]
    state_change: Mapping[str, object] | None = None
    error_class: str | None = None
    action_id: str | None = None

    def __post_init__(self) -> None:
        _require_descriptor_string(self.runtime_id, "runtime_action_result.runtime_id")
        _require_descriptor_string(self.tool_name, "runtime_action_result.tool_name")
        if self.status not in {"succeeded", "failed"}:
            raise ContractValidationError("runtime action result status is unsupported")
        if not isinstance(self.observation, Mapping):
            raise ContractValidationError("runtime action result observation must be an object")
        if self.state_change is not None and not isinstance(self.state_change, Mapping):
            raise ContractValidationError("runtime action result state_change must be an object")
        if self.status == "failed" and not self.error_class:
            raise ContractValidationError("runtime action failure requires error_class")
        if self.action_id is not None:
            _require_descriptor_string(self.action_id, "runtime_action_result.action_id")
        object.__setattr__(self, "observation", MappingProxyType(dict(self.observation)))
        if self.state_change is not None:
            object.__setattr__(
                self,
                "state_change",
                MappingProxyType(dict(self.state_change)),
            )

    @classmethod
    def succeeded(
        cls,
        *,
        runtime_id: str,
        tool_name: str,
        observation: Mapping[str, object],
        action_id: str | None = None,
    ) -> "RuntimeActionResult":
        state_change = observation.get("state_change")
        return cls(
            runtime_id=runtime_id,
            tool_name=tool_name,
            status="succeeded",
            observation=observation,
            state_change=state_change if isinstance(state_change, Mapping) else None,
            action_id=action_id,
        )

    @classmethod
    def failed(
        cls,
        *,
        runtime_id: str,
        tool_name: str,
        error_class: str,
        message: str,
        action_id: str | None = None,
    ) -> "RuntimeActionResult":
        return cls(
            runtime_id=runtime_id,
            tool_name=tool_name,
            status="failed",
            observation={"error_class": error_class, "message": message},
            error_class=error_class,
            action_id=action_id,
        )

    def export(self) -> dict[str, object]:
        observation = _sanitize_runtime_action_value(dict(self.observation))
        assert isinstance(observation, dict)
        state_change = (
            _sanitize_runtime_action_value(dict(self.state_change))
            if self.state_change is not None
            else None
        )
        assert state_change is None or isinstance(state_change, dict)
        record: dict[str, object] = {
            "schema_version": "runtime_action_result_v1",
            "runtime_id": self.runtime_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "observation": observation,
            "observation_hash": _runtime_content_hash(observation),
            "state_change_hash": _runtime_content_hash(state_change or {}),
            "error_class": self.error_class,
            "side_effect_summary": {"state_changed": state_change is not None},
        }
        if state_change is not None:
            record["state_change"] = state_change
        if self.action_id is not None:
            record["action_id"] = self.action_id
        validate_runtime_action_result_record(record)
        return record


class RuntimeSession:
    def __init__(
        self,
        *,
        environment: EnvironmentRuntime,
        registry: Any,
        registry_builder: Callable[[EnvironmentRuntime], Any] | None = None,
    ) -> None:
        self._environment = environment
        self._registry = registry
        self._registry_builder = registry_builder

    def runtime_metadata(self) -> RuntimeMetadata:
        return self._environment.runtime_metadata()

    def checkpoint(self) -> object:
        return self._environment.checkpoint()

    def restore_checkpoint(self, checkpoint: object) -> None:
        self._environment.restore_checkpoint(checkpoint)

    def rebuild(self, output_dir: Path) -> "RuntimeSession":
        if self._registry_builder is None:
            raise ContractValidationError("runtime session rebuild requires a registry builder")
        environment = self._environment.rebuild(output_dir)
        return RuntimeSession(
            environment=environment,
            registry=self._registry_builder(environment),
            registry_builder=self._registry_builder,
        )

    def list_tools(self) -> list[dict[str, object]]:
        return self._registry.export()

    def execute_action(self, request: RuntimeActionRequest) -> RuntimeActionResult:
        runtime_id = self.runtime_metadata().runtime_id
        if request.runtime_id != runtime_id:
            return RuntimeActionResult.failed(
                runtime_id=runtime_id,
                tool_name=request.tool_name,
                error_class="runtime_mismatch",
                message=f"request runtime {request.runtime_id} does not match session {runtime_id}",
                action_id=request.action_id,
            )
        checkpoint = self.checkpoint()
        try:
            observation = self._registry.execute(request.tool_name, dict(request.arguments))
        except Exception as exc:
            self.restore_checkpoint(checkpoint)
            return RuntimeActionResult.failed(
                runtime_id=runtime_id,
                tool_name=request.tool_name,
                error_class=type(exc).__name__,
                message=str(exc),
                action_id=request.action_id,
            )
        return RuntimeActionResult.succeeded(
            runtime_id=runtime_id,
            tool_name=request.tool_name,
            observation=observation,
            action_id=request.action_id,
        )


@runtime_checkable
class EnvironmentRuntime(Protocol):
    database_path: Path

    def metadata(self) -> Any: ...

    def runtime_metadata(self) -> RuntimeMetadata: ...

    def checkpoint(self) -> object: ...

    def restore_checkpoint(self, checkpoint: object) -> None: ...

    def rebuild(self, output_dir: Path) -> "EnvironmentRuntime": ...


def runtime_metadata_from_environment(
    environment_metadata: Any,
    *,
    state_backend: str = "sqlite",
    checkpoint_strategy: str = "sqlite_backup",
    source_provenance: Mapping[str, object] | None = None,
    sandbox_policy: Mapping[str, object] | None = None,
    adapter: Mapping[str, object] | None = None,
) -> RuntimeMetadata:
    provenance = (
        dict(source_provenance)
        if source_provenance is not None
        else dict(environment_metadata.source_provenance or {})
    )
    return RuntimeMetadata(
        runtime_id=str(environment_metadata.environment_id),
        runtime_version=str(environment_metadata.version),
        environment_id=str(environment_metadata.environment_id),
        environment_version=str(environment_metadata.version),
        reset_recipe=_runtime_reset_recipe(environment_metadata.reset_recipe),
        state_backend=state_backend,
        checkpoint_strategy=checkpoint_strategy,
        source_provenance=provenance,
        sandbox_policy=dict(sandbox_policy or {}),
        adapter=dict(adapter or {}),
    )


def validate_runtime_metadata_safety(record: Mapping[str, object]) -> None:
    _validate_safety_value(record, path="runtime_metadata")


def validate_runtime_descriptor_safety(record: Mapping[str, object]) -> None:
    _validate_safety_value(record, path="runtime_descriptor")


def registered_runtime_ids(registry: RuntimeRegistry | None = None) -> tuple[str, ...]:
    return _registry(registry).registered_runtime_ids()


def runtime_descriptor(
    runtime_id: str,
    registry: RuntimeRegistry | None = None,
) -> RuntimeCapabilityDescriptor:
    return _registry(registry).descriptor(runtime_id)


def runtime_capability_status(
    runtime_id: object,
    capability_name: str,
    registry: RuntimeRegistry | None = None,
) -> str:
    if runtime_id is None:
        return "insufficient_evidence"
    if not isinstance(runtime_id, str) or not runtime_id.strip():
        return "malformed"
    if capability_name not in RUNTIME_CAPABILITY_FIELDS:
        raise ContractValidationError(f"runtime capability is unsupported: {capability_name}")
    try:
        descriptor = runtime_descriptor(runtime_id, registry)
    except KeyError:
        return "unsupported"
    return "supported" if bool(getattr(descriptor, capability_name)) else "unsupported"


def runtime_registry_with(
    *descriptors: RuntimeCapabilityDescriptor,
    base: RuntimeRegistry | None = None,
) -> RuntimeRegistry:
    registry = _registry(base)
    for descriptor in descriptors:
        registry = registry.register(descriptor)
    return registry


_FORBIDDEN_KEY_FRAGMENTS = {
    "api_key",
    "authorization",
    "credential",
    "database_path",
    "dataset_release",
    "dataset_version",
    "environment_variable",
    "header",
    "local_path",
    "profile_decision",
    "profile_path",
    "profile_promotion",
    "profile_purpose",
    "provider_payload",
    "provider_prompt",
    "raw_payload",
    "raw_source",
    "secret",
}


def _registry(registry: RuntimeRegistry | None) -> RuntimeRegistry:
    return DEFAULT_RUNTIME_REGISTRY if registry is None else registry


def _require_descriptor_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"runtime descriptor {field_name} must be non-empty")


def _validate_string_tuple(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ContractValidationError(f"runtime descriptor {field_name} must be a tuple")
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise ContractValidationError(
                f"runtime descriptor {field_name}.{index} must be non-empty"
            )


def _mobile_messages_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_mobile_messages_v1",
        domain="mobile_messages_fixture",
        description="Synthetic phone messages, reminders, and draft replies.",
        task_taxonomy=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
    )


def _contacts_descriptor() -> RuntimeCapabilityDescriptor:
    seed = foundation_seed()
    return RuntimeCapabilityDescriptor(
        runtime_id="contacts_fixture",
        runtime_version="contacts_fixture_v1",
        domain_id="contacts_fixture",
        supports_rebuild=True,
        supports_checkpoint_restore=True,
        supports_episode_replay=True,
        supports_reward_labels=True,
        supports_local_adapter=True,
        state_changing_tools=("record_contact_followup",),
        task_taxonomy=seed.task_taxonomy,
        rebuild_seed=seed,
        descriptor_metadata={"adapter_support": "local_contacts_adapter"},
    )


def _mobile_descriptor() -> RuntimeCapabilityDescriptor:
    seed = _mobile_messages_seed()
    return RuntimeCapabilityDescriptor(
        runtime_id="mobile_messages_fixture",
        runtime_version="mobile_messages_fixture_v1",
        domain_id="mobile_messages_fixture",
        supports_rebuild=True,
        supports_checkpoint_restore=True,
        supports_episode_replay=True,
        supports_reward_labels=True,
        supports_local_adapter=False,
        state_changing_tools=("create_phone_reminder", "draft_message_reply"),
        task_taxonomy=seed.task_taxonomy,
        rebuild_seed=seed,
        descriptor_metadata={"adapter_support": "none"},
    )


def _runtime_reset_recipe(reset_recipe: object) -> str:
    if not isinstance(reset_recipe, Mapping):
        raise ContractValidationError("runtime_metadata reset recipe must be an object")
    recipe_type = str(reset_recipe.get("type", "")).strip()
    fixture = str(reset_recipe.get("fixture", "")).strip()
    if not recipe_type or not fixture:
        raise ContractValidationError("runtime_metadata reset recipe is incomplete")
    return f"{recipe_type}:{fixture}"


def _validate_safety_value(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            lowered_key = key.lower()
            if any(fragment in lowered_key for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise ContractValidationError(f"{path}.{key} is forbidden in runtime metadata")
            _validate_safety_value(nested, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, str):
        for index, nested in enumerate(value):
            _validate_safety_value(nested, path=f"{path}.{index}")
        return
    if isinstance(value, str):
        lowered = value.lower()
        if (
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
        ):
            raise ContractValidationError(f"{path} contains unsafe runtime metadata")


def _sanitize_runtime_action_value(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested in sorted(value.items(), key=lambda item: str(item[0])):
            key = str(raw_key)
            if _is_forbidden_runtime_action_key(key):
                continue
            nested_value = _sanitize_runtime_action_value(nested)
            if nested_value is _REDACTED:
                continue
            sanitized[key] = nested_value
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [
            nested_value
            for item in value
            if (nested_value := _sanitize_runtime_action_value(item)) is not _REDACTED
        ]
    if isinstance(value, str):
        return _REDACTED if _is_forbidden_runtime_action_string(value) else value
    return value


def _runtime_content_hash(value: object) -> str:
    import hashlib
    import json

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_forbidden_runtime_action_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS) or any(
        fragment in lowered
        for fragment in (
            "path",
            "profile",
            "prompt",
            "raw_source",
        )
    )


def _is_forbidden_runtime_action_string(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("/")
        or lowered.startswith("~")
        or ":\\" in lowered
        or "/users/" in lowered
        or "/private/" in lowered
        or "/tmp/" in lowered
        or "authorization:" in lowered
        or "secret-test-key" in lowered
        or "sk-live" in lowered
        or "sk-test" in lowered
    )


_REDACTED = object()


DEFAULT_RUNTIME_REGISTRY = RuntimeRegistry(
    (
        _contacts_descriptor(),
        _mobile_descriptor(),
    )
)
