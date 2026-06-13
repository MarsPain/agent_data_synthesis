from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from synthesis.contracts import ContractValidationError


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
