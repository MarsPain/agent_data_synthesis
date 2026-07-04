from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from awm_runtime.runtime import (
    RuntimeActionRequest,
    RuntimeCapabilityDescriptor,
    RuntimeSession,
)
from synthesis.contracts import (
    validate_adapter_call_request_record,
    validate_adapter_call_result_record,
    validate_adapter_lineage_record,
    validate_adapter_manifest_record,
)
from synthesis.environments import ContactEnvironment, EnvironmentMetadata
from synthesis.runtime_registry import runtime_descriptor
from synthesis.tools import ToolRegistry


ADAPTER_ID = "contacts_local_mcp_adapter"
ADAPTER_VERSION = "adapter_contacts_local_v1"
PROTOCOL_LABEL = "mcp-compatible-local-shim"
REQUEST_SCHEMA_VERSION = "mcp_tool_call_request_v1"
RESULT_SCHEMA_VERSION = "mcp_tool_call_result_v1"
LINEAGE_SCHEMA_VERSION = "adapter_lineage_v1"
MANIFEST_SCHEMA_VERSION = "mcp_adapter_manifest_v1"
TOOL_CALL_OPERATION = "tool.call"
LOCAL_FIXTURE_SOURCE_POLICY_HASH = "sha256:" + "0" * 64


@dataclass(frozen=True)
class AdapterManifest:
    adapter_id: str
    protocol_label: str
    adapter_version: str
    environment: EnvironmentMetadata | Mapping[str, object]
    source_policy_hash: str
    tools: list[dict[str, object]]

    def export(self) -> dict[str, object]:
        tool_records = [_tool_manifest_record(tool) for tool in self.tools]
        record = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "protocol_label": self.protocol_label,
            "adapter_version": self.adapter_version,
            "environment": _adapter_environment_record(self.environment),
            "source_policy_hash": self.source_policy_hash,
            "supported_operations": [TOOL_CALL_OPERATION],
            "capabilities": {"reset": True, "checkpoint": True},
            "tools": tool_records,
            "side_effect_classes": sorted(
                {str(tool.get("side_effects", "unknown")) for tool in tool_records}
            ),
            "verifier_implications": [
                "adapter observations preserve local trajectory semantics",
                "state-mutating tools surface state_change observations",
            ],
        }
        validate_adapter_manifest_record(record)
        return record


@dataclass(frozen=True)
class ToolCallRequest:
    call_id: str
    adapter_id: str
    tool_name: str
    arguments: dict[str, object]
    operation: str = TOOL_CALL_OPERATION

    def export(self) -> dict[str, object]:
        arguments = _sanitize_adapter_value(self.arguments)
        assert isinstance(arguments, dict)
        record = {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "call_id": self.call_id,
            "adapter_id": self.adapter_id,
            "operation": self.operation,
            "tool_name": self.tool_name,
            "arguments": arguments,
        }
        validate_adapter_call_request_record(record)
        return record


@dataclass(frozen=True)
class ToolCallResult:
    call_id: str
    adapter_id: str
    tool_name: str
    execution_status: str
    observation: dict[str, object]
    side_effect_summary: dict[str, object]
    error: dict[str, object] | None = None
    runtime_action: dict[str, object] | None = None

    def export(self) -> dict[str, object]:
        observation = _sanitize_adapter_value(self.observation)
        side_effect_summary = _sanitize_adapter_value(self.side_effect_summary)
        error = _sanitize_adapter_value(self.error) if self.error is not None else None
        assert isinstance(observation, dict)
        assert isinstance(side_effect_summary, dict)
        assert error is None or isinstance(error, dict)
        record = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "call_id": self.call_id,
            "adapter_id": self.adapter_id,
            "tool_name": self.tool_name,
            "execution_status": self.execution_status,
            "observation": observation,
            "side_effect_summary": side_effect_summary,
            "error": error,
        }
        validate_adapter_call_result_record(record)
        return record

    def lineage(self, manifest: AdapterManifest) -> dict[str, object]:
        rejection_cause = None
        if self.error is not None:
            rejection_cause = self.error.get("cause")
        record = {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "protocol_label": manifest.protocol_label,
            "adapter_version": manifest.adapter_version,
            "operation": TOOL_CALL_OPERATION,
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "execution_status": self.execution_status,
            "rejection_cause": rejection_cause,
        }
        validate_adapter_lineage_record(record)
        return record


class AdapterExecutionError(RuntimeError):
    def __init__(self, result: ToolCallResult) -> None:
        message = "adapter execution failed"
        if result.error is not None:
            message = str(result.error.get("message", message))
        super().__init__(message)
        self.result = result


class LocalRuntimeAdapterShim:
    def __init__(
        self,
        *,
        descriptor: RuntimeCapabilityDescriptor,
        session: RuntimeSession,
    ) -> None:
        self.descriptor = descriptor
        self.session = session
        runtime_metadata = session.runtime_metadata()
        self.manifest = AdapterManifest(
            adapter_id=_adapter_id_for_runtime(descriptor.runtime_id),
            protocol_label=PROTOCOL_LABEL,
            adapter_version=_adapter_version_for_runtime(descriptor.runtime_id),
            environment={
                "id": descriptor.runtime_id,
                "version": descriptor.runtime_version,
                "reset_recipe": {
                    "type": "runtime_metadata_reset",
                    "recipe": runtime_metadata.reset_recipe,
                },
            },
            source_policy_hash=_source_policy_hash(runtime_metadata.source_provenance),
            tools=session.list_tools(),
        )

    def call_tool(self, request: ToolCallRequest) -> ToolCallResult:
        request_record = request.export()
        if request_record["adapter_id"] != self.manifest.adapter_id:
            return self._rejected_result(
                request,
                cause="adapter_id_mismatch",
                message="request adapter_id does not match local adapter",
                details={"expected_adapter_id": self.manifest.adapter_id},
            )
        if request_record["operation"] != TOOL_CALL_OPERATION:
            return self._rejected_result(
                request,
                cause="unsupported_operation",
                message="adapter only supports tool.call",
                details={"supported_operations": [TOOL_CALL_OPERATION]},
            )
        if not self.descriptor.supports_local_adapter:
            return self._rejected_result(
                request,
                cause="unsupported_runtime_adapter",
                message="runtime descriptor does not support local adapter execution",
                details={
                    "runtime_id": self.descriptor.runtime_id,
                    "supported_operations": [],
                },
            )

        action_request = RuntimeActionRequest(
            runtime_id=self.descriptor.runtime_id,
            tool_name=request.tool_name,
            arguments=request_record["arguments"],
            action_id=request.call_id,
        )
        runtime_result = self.session.execute_action(action_request)
        runtime_record = runtime_result.export()
        if runtime_record["status"] != "succeeded":
            return self._runtime_error_result(request, runtime_record)
        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="succeeded",
            observation=runtime_record["observation"],
            side_effect_summary=_side_effect_summary(self.manifest.tools, request.tool_name),
            runtime_action=runtime_record,
        )

    def _rejected_result(
        self,
        request: ToolCallRequest,
        *,
        cause: str,
        message: str,
        details: dict[str, object],
        runtime_action: dict[str, object] | None = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="rejected",
            observation={},
            side_effect_summary={"class": "none"},
            error={"cause": cause, "message": message, "details": details},
            runtime_action=runtime_action,
        )

    def _runtime_error_result(
        self,
        request: ToolCallRequest,
        runtime_record: dict[str, object],
    ) -> ToolCallResult:
        observation = runtime_record.get("observation", {})
        if not isinstance(observation, Mapping):
            observation = {}
        error_class = str(runtime_record.get("error_class") or "RuntimeActionError")
        message = str(observation.get("message", "runtime action failed"))
        if error_class == "ToolMissingError":
            return self._rejected_result(
                request,
                cause="tool_missing",
                message=message,
                details={"available_tools": _tool_names(self.manifest.tools)},
                runtime_action=runtime_record,
            )
        if error_class == "ToolSchemaError":
            return self._rejected_result(
                request,
                cause="tool_schema_error",
                message=message,
                details={"schema_details": observation.get("schema_details", {})},
                runtime_action=runtime_record,
            )
        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="failed",
            observation={},
            side_effect_summary=_side_effect_summary(self.manifest.tools, request.tool_name),
            error={
                "cause": "tool_runtime_error",
                "message": message,
                "details": {"error_class": error_class},
            },
            runtime_action=runtime_record,
        )


class LocalContactsAdapterShim(LocalRuntimeAdapterShim):
    def __init__(self, *, environment: ContactEnvironment, registry: ToolRegistry) -> None:
        super().__init__(
            descriptor=runtime_descriptor("contacts_fixture"),
            session=RuntimeSession(environment=environment, registry=registry),
        )


def _tool_manifest_record(tool: dict[str, object]) -> dict[str, object]:
    record = dict(tool)
    record["verifier_implications"] = [
        "observation payload is available to exact-answer verification",
    ]
    return record


def _adapter_environment_record(
    environment: EnvironmentMetadata | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(environment, EnvironmentMetadata):
        return {
            "id": environment.environment_id,
            "version": environment.version,
            "reset_recipe": environment.reset_recipe,
        }
    return {
        "id": str(environment["id"]),
        "version": str(environment["version"]),
        "reset_recipe": dict(environment["reset_recipe"]),
    }


def _adapter_id_for_runtime(runtime_id: str) -> str:
    if runtime_id == "contacts_fixture":
        return ADAPTER_ID
    if runtime_id == "mobile_messages_fixture":
        return "mobile_messages_local_mcp_adapter"
    return f"{runtime_id}_local_mcp_adapter"


def _adapter_version_for_runtime(runtime_id: str) -> str:
    if runtime_id == "contacts_fixture":
        return ADAPTER_VERSION
    if runtime_id == "mobile_messages_fixture":
        return "adapter_mobile_messages_local_v1"
    return f"adapter_{runtime_id}_local_v1"


def _source_policy_hash(source_provenance: Mapping[str, object]) -> str:
    return str(
        source_provenance.get(
            "source_policy_hash",
            LOCAL_FIXTURE_SOURCE_POLICY_HASH,
        )
    )


def _tool_names(tools: list[dict[str, object]]) -> list[str]:
    return sorted(str(tool.get("name")) for tool in tools if tool.get("name"))


def _side_effect_summary(
    tools: list[dict[str, object]],
    tool_name: str,
) -> dict[str, object]:
    side_effect_class = next(
        (str(tool.get("side_effects")) for tool in tools if tool.get("name") == tool_name),
        "unknown",
    )
    return {"class": side_effect_class}


_UNSAFE_KEY_FRAGMENTS = {
    "api_key",
    "authorization",
    "credential",
    "database_path",
    "generated_code",
    "headers",
    "password",
    "profile_path",
    "provider_payload",
    "provider_prompt",
    "raw_source",
    "secret",
    "source_payload",
    "token",
}


def _sanitize_adapter_value(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(fragment in lowered for fragment in _UNSAFE_KEY_FRAGMENTS):
                continue
            sanitized[key] = _sanitize_adapter_value(nested)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_adapter_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_adapter_value(item) for item in value]
    return value
