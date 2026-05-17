from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from synthesis.environments import ContactEnvironment
from synthesis.llm import LLMProviderError
from synthesis.quality import retry_eligible
from synthesis.roles import TOOL_GENERATION_ROLE, RoleRegistry, default_role_registry


ToolHandler = Callable[[dict[str, object]], dict[str, object]]


class ToolRegistryError(RuntimeError):
    pass


class ToolMissingError(ToolRegistryError):
    def __init__(self, tool_name: str, *, available_tools: list[str]) -> None:
        super().__init__(f"Unknown tool: {tool_name}")
        self.tool_name = tool_name
        self.available_tools = available_tools


class ToolSchemaError(ToolRegistryError):
    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        schema_details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.schema_details = schema_details or {}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    schema: dict[str, object]
    side_effects: str

    def export(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "schema": self.schema,
            "side_effects": self.side_effects,
        }


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


@dataclass(frozen=True)
class CapabilityGap:
    candidate_id: str
    policy_id: str
    gap_type: str
    tool_name: str
    cause: str
    message: str
    schema_details: dict[str, object]
    retry_eligible: bool
    source_role_lineage: dict[str, object]

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "capability_gap_v1",
            "candidate_id": self.candidate_id,
            "policy_id": self.policy_id,
            "gap_type": self.gap_type,
            "tool_name": self.tool_name,
            "cause": self.cause,
            "message": self.message,
            "schema_details": self.schema_details,
            "retry_eligible": self.retry_eligible,
            "source_role_lineage": self.source_role_lineage,
        }


@dataclass(frozen=True)
class ToolProposal:
    tool_name: str
    description: str
    schema: dict[str, object]
    side_effects: str
    required_environment: dict[str, object]
    verifier_implications: list[str]
    safety_notes: list[str]
    lineage: dict[str, object]

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "tool_proposal_v1",
            "tool_name": self.tool_name,
            "description": self.description,
            "schema": self.schema,
            "side_effects": self.side_effects,
            "required_environment": self.required_environment,
            "verifier_implications": self.verifier_implications,
            "safety_notes": self.safety_notes,
            "lineage": self.lineage,
        }


@dataclass(frozen=True)
class ToolAdmissionResult:
    tool_name: str
    outcome: str
    accepted: bool
    reason: str
    tool_version: str | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": "tool_admission_v1",
            "tool_name": self.tool_name,
            "outcome": self.outcome,
            "accepted": self.accepted,
            "reason": self.reason,
        }
        if self.tool_version:
            record["tool_version"] = self.tool_version
        return record


class ToolRegistry:
    def __init__(
        self,
        *,
        checkpoint_state: Callable[[], object] | None = None,
        restore_state: Callable[[object], None] | None = None,
    ) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._checkpoint_state = checkpoint_state
        self._restore_state = restore_state

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._tools[definition.name] = RegisteredTool(definition, handler)

    def execute(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name not in self._tools:
            raise ToolMissingError(name, available_tools=sorted(self._tools))
        tool = self._tools[name]
        _validate_arguments(tool.definition, arguments)
        return tool.handler(arguments)

    def export(self) -> list[dict[str, object]]:
        return [tool.definition.export() for tool in self._tools.values()]

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def checkpoint_state(self) -> object | None:
        if self._checkpoint_state is None:
            return None
        return self._checkpoint_state()

    def restore_state(self, checkpoint: object | None) -> None:
        if checkpoint is None or self._restore_state is None:
            return
        self._restore_state(checkpoint)


def build_contact_tool_registry(environment: ContactEnvironment) -> ToolRegistry:
    registry = ToolRegistry(
        checkpoint_state=environment.checkpoint,
        restore_state=environment.restore_checkpoint,
    )

    def lookup_contact_email(arguments: dict[str, object]) -> dict[str, object]:
        name = arguments.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("lookup_contact_email requires a non-empty string name")
        return environment.lookup_email(name)

    registry.register(
        ToolDefinition(
            name="lookup_contact_email",
            version="tool_lookup_contact_email_v1",
            schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full contact name to look up.",
                    }
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            side_effects="read_only",
        ),
        lookup_contact_email,
    )

    def record_contact_followup(arguments: dict[str, object]) -> dict[str, object]:
        name = arguments.get("name")
        note = arguments.get("note")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("record_contact_followup requires a non-empty string name")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("record_contact_followup requires a non-empty string note")
        return environment.record_followup(name, note)

    registry.register(
        ToolDefinition(
            name="record_contact_followup",
            version="tool_record_contact_followup_v1",
            schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full contact name receiving a follow-up note.",
                    },
                    "note": {
                        "type": "string",
                        "description": "Follow-up note to persist for the contact.",
                    },
                },
                "required": ["name", "note"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        record_contact_followup,
    )
    return registry


def build_capability_gap(
    *,
    task: Any,
    policy: Any,
    error: Exception,
    cause: str,
    registry: ToolRegistry,
) -> CapabilityGap:
    if isinstance(error, ToolMissingError):
        gap_type = "unknown_tool"
        tool_name = error.tool_name
        schema_details = {"available_tools": error.available_tools}
    elif isinstance(error, ToolSchemaError):
        gap_type = "incompatible_arguments"
        tool_name = error.tool_name or _first_policy_tool_name(policy) or getattr(task, "tool_name", "unknown")
        schema_details = dict(error.schema_details)
        schema_details.setdefault("available_tools", registry.tool_names())
    else:
        gap_type = "environment_dependency_mismatch"
        tool_name = _first_policy_tool_name(policy) or getattr(task, "tool_name", "unknown")
        schema_details = {"available_tools": registry.tool_names()}

    return CapabilityGap(
        candidate_id=str(getattr(task, "candidate_id", "unknown_candidate") or "unknown_candidate"),
        policy_id=str(getattr(policy, "policy_id", "unknown_policy") or "unknown_policy"),
        gap_type=gap_type,
        tool_name=str(tool_name),
        cause=cause,
        message=str(error),
        schema_details=schema_details,
        retry_eligible=retry_eligible(cause),
        source_role_lineage=_source_role_lineage(task=task, policy=policy),
    )


def parse_tool_proposal(raw: Mapping[str, Any], *, lineage: dict[str, object]) -> ToolProposal:
    try:
        proposal = raw["proposal"]
        if not isinstance(proposal, Mapping):
            raise TypeError("proposal must be an object")
        forbidden = {"python_code", "code", "handler", "implementation", "package"}
        present_forbidden = sorted(forbidden & set(proposal))
        if present_forbidden:
            raise ValueError(f"tool proposal includes executable fields: {present_forbidden}")
        schema = proposal["schema"]
        if not isinstance(schema, dict):
            raise TypeError("proposal.schema must be an object")
        required_environment = proposal["required_environment"]
        if not isinstance(required_environment, dict):
            raise TypeError("proposal.required_environment must be an object")
        return ToolProposal(
            tool_name=str(proposal["tool_name"]),
            description=str(proposal["description"]),
            schema=schema,
            side_effects=str(proposal["side_effects"]),
            required_environment=required_environment,
            verifier_implications=_string_list(
                proposal["verifier_implications"],
                "verifier_implications",
            ),
            safety_notes=_string_list(proposal["safety_notes"], "safety_notes"),
            lineage=dict(lineage),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class=type(exc).__name__,
            retryable=False,
            retry_count=_lineage_retry_count(lineage),
            lineage=lineage,
        ) from exc


def generate_llm_backed_tool_proposal(
    gap: CapabilityGap,
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> ToolProposal:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        TOOL_GENERATION_ROLE,
        client,
        _tool_proposal_prompt(gap),
    )
    return parse_tool_proposal(result.content, lineage=result.lineage)


def admit_curated_tool(
    proposal: ToolProposal,
    registry: ToolRegistry,
    environment: ContactEnvironment,
) -> ToolAdmissionResult:
    if proposal.tool_name != "list_contact_names":
        return ToolAdmissionResult(
            tool_name=proposal.tool_name,
            outcome="rejected",
            accepted=False,
            reason="No curated implementation exists for proposed tool.",
        )
    definition = _list_contact_names_definition()
    if proposal.side_effects != definition.side_effects:
        return ToolAdmissionResult(
            tool_name=proposal.tool_name,
            outcome="rejected",
            accepted=False,
            reason="Proposal side effects do not match curated implementation.",
        )
    if proposal.schema != definition.schema:
        return ToolAdmissionResult(
            tool_name=proposal.tool_name,
            outcome="rejected",
            accepted=False,
            reason="Proposal schema does not match curated implementation.",
        )
    if proposal.required_environment.get("environment_id") != environment.environment_id:
        return ToolAdmissionResult(
            tool_name=proposal.tool_name,
            outcome="rejected",
            accepted=False,
            reason="Proposal environment does not match active environment.",
        )
    registry.register(definition, lambda arguments: environment.list_contact_names())
    return ToolAdmissionResult(
        tool_name=proposal.tool_name,
        outcome="accepted",
        accepted=True,
        reason="Matched curated contacts fixture implementation.",
        tool_version=definition.version,
    )


def build_tool_proposal_record(
    *,
    candidate_id: str,
    gap: CapabilityGap,
    proposal: ToolProposal,
    admission: ToolAdmissionResult,
) -> dict[str, object]:
    return {
        "schema_version": "tool_proposal_event_v1",
        "candidate_id": candidate_id,
        "gap": gap.export(),
        "proposal": proposal.export(),
        "admission": admission.export(),
    }


def _validate_arguments(definition: ToolDefinition, arguments: dict[str, object]) -> None:
    schema = definition.schema
    if schema.get("type") != "object":
        raise ToolSchemaError(
            f"{definition.name} schema must be an object schema",
            tool_name=definition.name,
        )
    if not isinstance(arguments, dict):
        raise ToolSchemaError(
            f"{definition.name} arguments must be an object",
            tool_name=definition.name,
        )

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ToolSchemaError(
            f"{definition.name} schema properties must be an object",
            tool_name=definition.name,
        )

    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ToolSchemaError(
            f"{definition.name} schema required must be a list",
            tool_name=definition.name,
        )
    for field_name in required:
        if not isinstance(field_name, str):
            raise ToolSchemaError(
                f"{definition.name} schema required entries must be strings",
                tool_name=definition.name,
            )
        if field_name not in arguments:
            raise ToolSchemaError(
                f"{definition.name} missing required argument: {field_name}",
                tool_name=definition.name,
                schema_details={"missing_required": field_name, "schema": definition.schema},
            )

    if schema.get("additionalProperties") is False:
        allowed = set(properties)
        extra = set(arguments) - allowed
        if extra:
            names = ", ".join(sorted(extra))
            raise ToolSchemaError(
                f"{definition.name} has unexpected arguments: {names}",
                tool_name=definition.name,
                schema_details={"unexpected_arguments": sorted(extra), "schema": definition.schema},
            )

    for field_name, raw_property_schema in properties.items():
        if field_name not in arguments:
            continue
        if not isinstance(raw_property_schema, dict):
            raise ToolSchemaError(
                f"{definition.name}.{field_name} schema must be an object",
                tool_name=definition.name,
            )
        expected_type = raw_property_schema.get("type")
        value = arguments[field_name]
        if expected_type == "string" and not isinstance(value, str):
            raise ToolSchemaError(
                f"{definition.name}.{field_name} must be a string",
                tool_name=definition.name,
                schema_details={
                    "field": field_name,
                    "expected_type": "string",
                    "schema": definition.schema,
                },
            )


def _list_contact_names_definition() -> ToolDefinition:
    return ToolDefinition(
        name="list_contact_names",
        version="tool_list_contact_names_v1",
        schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        side_effects="read_only",
    )


def _source_role_lineage(*, task: Any, policy: Any) -> dict[str, object]:
    lineages: dict[str, object] = {}
    generation_lineage = getattr(task, "generation_lineage", None)
    if isinstance(generation_lineage, dict):
        lineages["generator"] = dict(generation_lineage)
    policy_lineage = getattr(policy, "lineage", None)
    if isinstance(policy_lineage, dict):
        lineages["solution_policy"] = dict(policy_lineage)
    return lineages


def _first_policy_tool_name(policy: Any) -> str | None:
    steps = getattr(policy, "steps", None)
    if not steps:
        return None
    tool_name = getattr(steps[0], "tool_name", None)
    return str(tool_name) if tool_name else None


def _string_list(raw: object, label: str) -> list[str]:
    if not isinstance(raw, list):
        raise TypeError(f"proposal.{label} must be a list")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise TypeError(f"proposal.{label} entries must be non-empty strings")
        values.append(item)
    if not values:
        raise ValueError(f"proposal.{label} must not be empty")
    return values


def _tool_proposal_prompt(gap: CapabilityGap) -> str:
    return (
        "Propose a tool contract for a missing Agent capability. "
        "Return JSON with a proposal object only; do not include executable code.\n"
        f"Capability gap: {gap.export()}"
    )


def _lineage_retry_count(lineage: dict[str, object]) -> int:
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        return retry_count
    return 0
