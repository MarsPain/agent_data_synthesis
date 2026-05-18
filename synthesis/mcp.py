from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from synthesis.contracts import (
    validate_adapter_call_request_record,
    validate_adapter_call_result_record,
    validate_adapter_lineage_record,
    validate_adapter_manifest_record,
)
from synthesis.environments import ContactEnvironment, EnvironmentMetadata
from synthesis.tools import ToolMissingError, ToolRegistry, ToolSchemaError


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
    environment: EnvironmentMetadata
    source_policy_hash: str
    tools: list[dict[str, object]]

    def export(self) -> dict[str, object]:
        tool_records = [_tool_manifest_record(tool) for tool in self.tools]
        record = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "protocol_label": self.protocol_label,
            "adapter_version": self.adapter_version,
            "environment": {
                "id": self.environment.environment_id,
                "version": self.environment.version,
                "reset_recipe": self.environment.reset_recipe,
            },
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
        record = {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "call_id": self.call_id,
            "adapter_id": self.adapter_id,
            "operation": self.operation,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
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

    def export(self) -> dict[str, object]:
        record = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "call_id": self.call_id,
            "adapter_id": self.adapter_id,
            "tool_name": self.tool_name,
            "execution_status": self.execution_status,
            "observation": self.observation,
            "side_effect_summary": self.side_effect_summary,
            "error": self.error,
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


class LocalContactsAdapterShim:
    def __init__(self, *, environment: ContactEnvironment, registry: ToolRegistry) -> None:
        self.environment = environment
        self.registry = registry
        metadata = environment.metadata()
        source_policy_hash = LOCAL_FIXTURE_SOURCE_POLICY_HASH
        if isinstance(metadata.source_provenance, Mapping):
            source_policy_hash = str(
                metadata.source_provenance.get(
                    "source_policy_hash",
                    LOCAL_FIXTURE_SOURCE_POLICY_HASH,
                )
            )
        self.manifest = AdapterManifest(
            adapter_id=ADAPTER_ID,
            protocol_label=PROTOCOL_LABEL,
            adapter_version=ADAPTER_VERSION,
            environment=metadata,
            source_policy_hash=source_policy_hash,
            tools=registry.export(),
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
        try:
            observation = self.registry.execute(request.tool_name, request.arguments)
        except ToolMissingError as exc:
            return self._rejected_result(
                request,
                cause="tool_missing",
                message=str(exc),
                details={"available_tools": exc.available_tools},
            )
        except ToolSchemaError as exc:
            return self._rejected_result(
                request,
                cause="tool_schema_error",
                message=str(exc),
                details=exc.schema_details,
            )
        except Exception as exc:
            return self._failed_result(
                request,
                cause="tool_runtime_error",
                message=str(exc),
                details={"error_class": type(exc).__name__},
            )

        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="succeeded",
            observation=observation,
            side_effect_summary=_side_effect_summary(self.registry.export(), request.tool_name),
        )

    def _rejected_result(
        self,
        request: ToolCallRequest,
        *,
        cause: str,
        message: str,
        details: dict[str, object],
    ) -> ToolCallResult:
        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="rejected",
            observation={},
            side_effect_summary={"class": "none"},
            error={"cause": cause, "message": message, "details": details},
        )

    def _failed_result(
        self,
        request: ToolCallRequest,
        *,
        cause: str,
        message: str,
        details: dict[str, object],
    ) -> ToolCallResult:
        return ToolCallResult(
            call_id=request.call_id,
            adapter_id=request.adapter_id,
            tool_name=request.tool_name,
            execution_status="failed",
            observation={},
            side_effect_summary=_side_effect_summary(self.registry.export(), request.tool_name),
            error={"cause": cause, "message": message, "details": details},
        )


def _tool_manifest_record(tool: dict[str, object]) -> dict[str, object]:
    record = dict(tool)
    record["verifier_implications"] = [
        "observation payload is available to exact-answer verification",
    ]
    return record


def _side_effect_summary(
    tools: list[dict[str, object]],
    tool_name: str,
) -> dict[str, object]:
    side_effect_class = next(
        (str(tool.get("side_effects")) for tool in tools if tool.get("name") == tool_name),
        "unknown",
    )
    return {"class": side_effect_class}
