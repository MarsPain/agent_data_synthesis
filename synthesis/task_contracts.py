from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from synthesis.contracts import ContractValidationError, validate_branch_plan_record
from synthesis.tasks import CandidateTask


SUPPORTED_TASK_CONTRACT_DOMAINS = (
    "contacts_fixture",
    "mobile_messages_fixture",
    "workspace_tasks_fixture",
)
SUPPORTED_EXPECTED_STATE_CHECKS = (
    "contact_followup",
    "mobile_reminder",
    "mobile_draft_reply",
    "workspace_task",
    "workspace_comment",
)

_UNSAFE_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "credential",
    "provider_payload",
    "provider_prompt",
    "raw_payload",
    "raw_source",
    "source_payload",
    "profile_path",
    "host_path",
)
_UNSAFE_STRING_FRAGMENTS = (
    "authorization:",
    "credential",
    "provider payload",
    "provider prompt",
    "raw payload",
    "raw source",
    "source payload",
    "profile path",
    "host path",
    "/users/",
    "/private/",
    "/tmp/",
    "sk-live",
    "sk-test",
    "secret-test-key",
)


@dataclass(frozen=True)
class TaskIntent:
    candidate_id: str
    instruction: str
    domain_id: str
    task_type: str
    difficulty: Mapping[str, object]
    required_capabilities: tuple[str, ...] = ()
    seed_ids: tuple[str, ...] = ()
    lineage: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyHint:
    required_tools: tuple[str, ...]
    primary_tool: str | None = None
    primary_arguments: Mapping[str, object] = field(default_factory=dict)
    branch_plan: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ExpectedOutcome:
    final_answer_contains: str


@dataclass(frozen=True)
class ExpectedStateCheck:
    check_type: str
    expected: Mapping[str, object]


@dataclass(frozen=True)
class TaskContract:
    intent: TaskIntent
    policy_hint: PolicyHint
    expected_outcome: ExpectedOutcome
    expected_state: tuple[ExpectedStateCheck, ...] = ()
    compatibility: Mapping[str, object] = field(default_factory=dict)


def task_contract_from_candidate(candidate: CandidateTask) -> TaskContract:
    domain_id = _domain_id(candidate)
    required_tools = _required_tools(candidate)
    branch_plan = _copy_mapping(candidate.branch_plan) if candidate.branch_plan is not None else None
    contract = TaskContract(
        intent=TaskIntent(
            candidate_id=candidate.candidate_id,
            instruction=candidate.instruction,
            domain_id=domain_id,
            task_type=_task_type(candidate, domain_id),
            difficulty=_copy_mapping(candidate.difficulty),
            required_capabilities=_string_tuple(
                candidate.constraints.get("required_capabilities")
            ),
            seed_ids=tuple(candidate.seed_ids),
            lineage=_candidate_lineage(candidate),
        ),
        policy_hint=PolicyHint(
            required_tools=required_tools,
            primary_tool=candidate.tool_name,
            primary_arguments=_copy_mapping(candidate.arguments),
            branch_plan=branch_plan,
        ),
        expected_outcome=ExpectedOutcome(
            final_answer_contains=candidate.expected_answer,
        ),
        expected_state=_expected_state_checks(candidate),
        compatibility=_candidate_compatibility(candidate),
    )
    return validate_task_contract(contract)


def validate_task_contract(contract: TaskContract) -> TaskContract:
    if not isinstance(contract, TaskContract):
        raise ContractValidationError("task_contract must be a TaskContract")
    _validate_intent(contract.intent)
    _validate_policy_hint(contract.policy_hint)
    _validate_expected_outcome(contract.expected_outcome)
    for index, state_check in enumerate(contract.expected_state):
        _validate_expected_state_check(state_check, index)
    if not isinstance(contract.compatibility, Mapping):
        raise ContractValidationError("compatibility must be an object")
    _reject_unsafe(contract.compatibility, "compatibility")
    return contract


def candidate_from_task_contract(contract: TaskContract) -> CandidateTask:
    validate_task_contract(contract)
    compatibility = contract.compatibility
    constraints = _copy_mapping(compatibility.get("constraints", {}))
    expected_state = {
        state_check.check_type: _copy_mapping(state_check.expected)
        for state_check in contract.expected_state
    }
    return CandidateTask(
        candidate_id=contract.intent.candidate_id,
        instruction=contract.intent.instruction,
        constraints=constraints,
        difficulty=_copy_mapping(contract.intent.difficulty),
        tool_name=contract.policy_hint.primary_tool or "",
        arguments=_copy_mapping(contract.policy_hint.primary_arguments),
        expected_answer=contract.expected_outcome.final_answer_contains,
        seed_ids=tuple(contract.intent.seed_ids),
        generation_lineage=_optional_mapping(compatibility.get("generation_lineage")),
        expected_state=expected_state or None,
        branch_plan=(
            _copy_mapping(contract.policy_hint.branch_plan)
            if contract.policy_hint.branch_plan is not None
            else None
        ),
        seed_transformation=_optional_mapping(compatibility.get("seed_transformation")),
        task_suggester_lineage=_optional_mapping(
            compatibility.get("task_suggester_lineage")
        ),
        task_editor_lineage=_optional_mapping(compatibility.get("task_editor_lineage")),
        editor_action=_optional_string(compatibility.get("editor_action")),
    )


def _validate_intent(intent: TaskIntent) -> None:
    if not isinstance(intent, TaskIntent):
        raise ContractValidationError("intent must be a TaskIntent")
    for field_name in ("candidate_id", "instruction", "domain_id", "task_type"):
        _require_non_empty_string(getattr(intent, field_name), f"intent.{field_name}")
    if intent.domain_id not in SUPPORTED_TASK_CONTRACT_DOMAINS:
        raise ContractValidationError(f"unsupported task contract domain: {intent.domain_id}")
    if not isinstance(intent.difficulty, Mapping):
        raise ContractValidationError("intent.difficulty must be an object")
    _validate_string_tuple(intent.required_capabilities, "intent.required_capabilities")
    _validate_string_tuple(intent.seed_ids, "intent.seed_ids")
    if not isinstance(intent.lineage, Mapping):
        raise ContractValidationError("intent.lineage must be an object")
    _reject_unsafe(intent.difficulty, "intent.difficulty")
    _reject_unsafe(intent.required_capabilities, "intent.required_capabilities")
    _reject_unsafe(intent.seed_ids, "intent.seed_ids")
    _reject_unsafe(intent.lineage, "intent.lineage")


def _validate_policy_hint(policy_hint: PolicyHint) -> None:
    if not isinstance(policy_hint, PolicyHint):
        raise ContractValidationError("policy_hint must be a PolicyHint")
    _validate_string_tuple(policy_hint.required_tools, "policy_hint.required_tools")
    if policy_hint.primary_tool is not None:
        _require_non_empty_string(policy_hint.primary_tool, "policy_hint.primary_tool")
        if policy_hint.primary_tool not in policy_hint.required_tools:
            raise ContractValidationError(
                "policy_hint.primary_tool must be one of policy_hint.required_tools"
            )
    if not isinstance(policy_hint.primary_arguments, Mapping):
        raise ContractValidationError("policy_hint.primary_arguments must be an object")
    _reject_unsafe(policy_hint.required_tools, "policy_hint.required_tools")
    _reject_unsafe(policy_hint.primary_arguments, "policy_hint.primary_arguments")
    if policy_hint.branch_plan is not None:
        if not isinstance(policy_hint.branch_plan, Mapping):
            raise ContractValidationError("policy_hint.branch_plan must be an object")
        validate_branch_plan_record(policy_hint.branch_plan)
        if policy_hint.branch_plan.get("schema_version") != "branch_plan_v1":
            raise ContractValidationError(
                "policy_hint.branch_plan.schema_version must be branch_plan_v1"
            )
        _reject_unsafe(policy_hint.branch_plan, "policy_hint.branch_plan")


def _validate_expected_outcome(expected_outcome: ExpectedOutcome) -> None:
    if not isinstance(expected_outcome, ExpectedOutcome):
        raise ContractValidationError("expected_outcome must be an ExpectedOutcome")
    _require_non_empty_string(
        expected_outcome.final_answer_contains,
        "expected_outcome.final_answer_contains",
    )
    _reject_unsafe(
        expected_outcome.final_answer_contains,
        "expected_outcome.final_answer_contains",
    )


def _validate_expected_state_check(
    state_check: ExpectedStateCheck,
    index: int,
) -> None:
    if not isinstance(state_check, ExpectedStateCheck):
        raise ContractValidationError(f"expected_state.{index} must be an ExpectedStateCheck")
    _require_non_empty_string(state_check.check_type, f"expected_state.{index}.check_type")
    if state_check.check_type not in SUPPORTED_EXPECTED_STATE_CHECKS:
        raise ContractValidationError(f"unsupported expected state check: {state_check.check_type}")
    if not isinstance(state_check.expected, Mapping):
        raise ContractValidationError(f"expected_state.{index}.expected must be an object")
    _reject_unsafe(state_check.expected, f"expected_state.{index}.expected")


def _domain_id(candidate: CandidateTask) -> str:
    raw_domain = candidate.constraints.get("domain")
    if raw_domain == "mobile_messages_fixture":
        return "mobile_messages_fixture"
    if raw_domain == "workspace_tasks_fixture":
        return "workspace_tasks_fixture"
    if raw_domain in {"contacts", "contacts_fixture"}:
        return "contacts_fixture"
    if raw_domain is not None:
        return str(raw_domain)
    if any(str(seed_id).startswith("seed_mobile") for seed_id in candidate.seed_ids):
        return "mobile_messages_fixture"
    if any(str(seed_id).startswith("seed_workspace") for seed_id in candidate.seed_ids):
        return "workspace_tasks_fixture"
    return "contacts_fixture"


def _task_type(candidate: CandidateTask, domain_id: str) -> str:
    raw_task_type = candidate.constraints.get("task_type")
    if isinstance(raw_task_type, str) and raw_task_type.strip():
        return raw_task_type
    if domain_id == "contacts_fixture" and candidate.tool_name == "lookup_contact_email":
        return "contact_lookup"
    if domain_id == "mobile_messages_fixture":
        return "mobile_message_lookup"
    if domain_id == "workspace_tasks_fixture":
        return "workspace_item_lookup"
    return "unknown_task"


def _required_tools(candidate: CandidateTask) -> tuple[str, ...]:
    configured = _string_tuple(candidate.constraints.get("required_tools"))
    if configured:
        return configured
    if candidate.tool_name.strip():
        return (candidate.tool_name,)
    return ()


def _expected_state_checks(candidate: CandidateTask) -> tuple[ExpectedStateCheck, ...]:
    if not candidate.expected_state:
        return ()
    checks: list[ExpectedStateCheck] = []
    for check_type in SUPPORTED_EXPECTED_STATE_CHECKS:
        expected = candidate.expected_state.get(check_type)
        if isinstance(expected, Mapping):
            checks.append(
                ExpectedStateCheck(
                    check_type=check_type,
                    expected=_copy_mapping(expected),
                )
            )
    return tuple(checks)


def _candidate_lineage(candidate: CandidateTask) -> Mapping[str, object]:
    lineage: dict[str, object] = {}
    if candidate.generation_lineage is not None:
        lineage["generation"] = _copy_mapping(candidate.generation_lineage)
    if candidate.seed_transformation is not None:
        lineage["seed_transformation"] = _copy_mapping(candidate.seed_transformation)
    if candidate.task_suggester_lineage is not None:
        lineage["task_suggester"] = _copy_mapping(candidate.task_suggester_lineage)
    if candidate.task_editor_lineage is not None:
        lineage["task_editor"] = _copy_mapping(candidate.task_editor_lineage)
    return lineage


def _candidate_compatibility(candidate: CandidateTask) -> Mapping[str, object]:
    compatibility: dict[str, object] = {
        "constraints": _copy_mapping(candidate.constraints),
    }
    optional_mappings = {
        "generation_lineage": candidate.generation_lineage,
        "seed_transformation": candidate.seed_transformation,
        "task_suggester_lineage": candidate.task_suggester_lineage,
        "task_editor_lineage": candidate.task_editor_lineage,
    }
    for key, value in optional_mappings.items():
        if value is not None:
            compatibility[key] = _copy_mapping(value)
    if candidate.editor_action is not None:
        compatibility["editor_action"] = candidate.editor_action
    return compatibility


def _reject_unsafe(value: object, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            normalized_key = key.lower()
            if any(fragment in normalized_key for fragment in _UNSAFE_KEY_FRAGMENTS):
                raise ContractValidationError(f"{path}.{key} contains unsafe key")
            _reject_unsafe(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_unsafe(nested, f"{path}.{index}")
        return
    if isinstance(value, str):
        normalized = value.lower()
        if value.startswith("/"):
            raise ContractValidationError(f"{path} contains an unsafe absolute path")
        if any(fragment in normalized for fragment in _UNSAFE_STRING_FRAGMENTS):
            raise ContractValidationError(f"{path} contains unsafe value")


def _validate_string_tuple(value: object, path: str) -> None:
    if not isinstance(value, tuple):
        raise ContractValidationError(f"{path} must be a tuple")
    for index, item in enumerate(value):
        _require_non_empty_string(item, f"{path}.{index}")


def _require_non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{path} must be a non-empty string")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item.strip())


def _copy_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _copy_value(nested) for key, nested in value.items()}


def _copy_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _copy_mapping(value)
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(item) for item in value)
    return value


def _optional_mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return _copy_mapping(value)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
