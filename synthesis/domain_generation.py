from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Mapping

from synthesis.llm import LLMProviderError
from synthesis.roles import TASK_GENERATION_ROLE, RoleRegistry, default_role_registry
from synthesis.seeds import DomainSeed
from synthesis.task_contracts import (
    SUPPORTED_EXPECTED_STATE_CHECKS,
    ExpectedOutcome,
    ExpectedStateCheck,
    PolicyHint,
    TaskContract,
    TaskIntent,
    candidate_from_task_contract,
    validate_task_contract,
)
from synthesis.tasks import CandidateTask, order_candidates_by_curriculum
from synthesis.tools import validate_arguments_against_tool_definition


DOMAIN_GENERATION_SPEC_VERSION = "domain_generation_spec_v1"
SYNTHETIC_CONTEXT_POLICY = "synthetic_fixture"
MAX_CANDIDATES_PER_CALL = 20
GENERATION_INELIGIBILITY_REASON_CODES = (
    "profile_contract_not_representative",
    "generation_spec_missing_or_mismatched",
    "context_policy_not_allowed",
    "source_backed_remote_context_not_allowed",
    "target_candidate_count_unfulfilled",
    "generation_evidence_missing",
)

_UNSAFE_KEYS = {
    "api_key", "authorization", "credential", "credentials", "headers",
    "host_path", "password", "profile_path", "provider_payload", "provider_prompt",
    "raw_payload", "raw_source", "secret", "source_path", "source_payload", "token",
}
_UNSAFE_STRING_PATTERNS = (
    re.compile(r"authorization\s*:", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(?:^|\s)/(?:Users|home|private|var|tmp)/"),
    re.compile(r"[A-Za-z]:\\"),
)


@dataclass(frozen=True)
class DomainTaskTypeSpec:
    task_type: str
    required_tools: tuple[str, ...]
    allowed_expected_state_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainGenerationSpec:
    schema_version: str
    domain_id: str
    task_types: tuple[DomainTaskTypeSpec, ...]
    tools: tuple[Mapping[str, object], ...]
    grounding_context: Mapping[str, object]
    context_policy: str
    max_candidates_per_call: int


@dataclass(frozen=True)
class DomainGenerationResult:
    candidates: tuple[CandidateTask, ...]
    target_candidate_count: int
    generated_candidate_count: int
    provider_call_count: int
    spec_metadata: Mapping[str, object]


_PROVIDER_RECORD_KEYS = {
    "candidate_id", "instruction", "task_type", "difficulty",
    "required_capabilities", "required_tools", "primary_tool",
    "primary_arguments", "final_answer_contains", "expected_state",
}


def validate_domain_generation_spec(spec: DomainGenerationSpec) -> None:
    if spec.schema_version != DOMAIN_GENERATION_SPEC_VERSION:
        raise ValueError("generation_spec_missing_or_mismatched")
    _required_text(spec.domain_id, "domain_id")
    _validate_safe_value(spec.domain_id, path="domain_id")
    if spec.context_policy != SYNTHETIC_CONTEXT_POLICY:
        raise ValueError("context_policy_not_allowed")
    if not 1 <= spec.max_candidates_per_call <= MAX_CANDIDATES_PER_CALL:
        raise ValueError("max_candidates_per_call must be between 1 and 20")
    if not spec.tools:
        raise ValueError("tools must not be empty")
    tool_names: set[str] = set()
    for index, tool in enumerate(spec.tools):
        if set(tool) != {"name", "version", "schema", "side_effects"}:
            raise ValueError(f"tools.{index} has unsupported keys")
        name = _required_text(tool.get("name"), f"tools.{index}.name")
        if name in tool_names:
            raise ValueError("tool names must be unique")
        tool_names.add(name)
        _required_text(tool.get("version"), f"tools.{index}.version")
        if not isinstance(tool.get("schema"), Mapping):
            raise ValueError(f"tools.{index}.schema must be an object")
        _required_text(tool.get("side_effects"), f"tools.{index}.side_effects")
        _validate_safe_value(tool, path=f"tools.{index}")
    if not spec.task_types:
        raise ValueError("task_types must not be empty")
    task_type_names: set[str] = set()
    declared_state_checks: set[str] = set()
    for item in spec.task_types:
        task_type = _required_text(item.task_type, "task_type")
        _validate_safe_value(task_type, path="task_type")
        if task_type in task_type_names:
            raise ValueError("task types must be unique")
        task_type_names.add(task_type)
        if not item.required_tools or not set(item.required_tools) <= tool_names:
            raise ValueError(f"task type {task_type} references unregistered tools")
        _validate_safe_value(item.required_tools, path=f"task_types.{task_type}.required_tools")
        for check in item.allowed_expected_state_checks:
            check_name = _required_text(check, "allowed_expected_state_checks")
            if check_name not in SUPPORTED_EXPECTED_STATE_CHECKS:
                raise ValueError("unsupported expected-state check name")
            declared_state_checks.add(check_name)
        _validate_safe_value(
            item.allowed_expected_state_checks,
            path=f"task_types.{task_type}.allowed_expected_state_checks",
        )
    if not spec.grounding_context:
        raise ValueError("grounding_context must not be empty")
    _validate_safe_value(spec.grounding_context, path="grounding_context")


def grounding_context_hash(spec: DomainGenerationSpec) -> str:
    validate_domain_generation_spec(spec)
    encoded = _canonical_json(spec.grounding_context).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def sanitized_generation_spec_metadata(spec: DomainGenerationSpec) -> dict[str, object]:
    validate_domain_generation_spec(spec)
    return {
        "spec_version": spec.schema_version,
        "domain_id": spec.domain_id,
        "task_types": [item.task_type for item in spec.task_types],
        "tools": [
            {
                "name": str(tool["name"]),
                "version": str(tool["version"]),
                "schema_hash": _sha256_mapping(tool["schema"]),
            }
            for tool in spec.tools
        ],
        "context_policy": spec.context_policy,
        "grounding_context_hash": grounding_context_hash(spec),
        "max_candidates_per_call": spec.max_candidates_per_call,
    }


def build_domain_generation_prompt(
    spec: DomainGenerationSpec,
    *,
    requested_candidate_count: int,
) -> str:
    validate_domain_generation_spec(spec)
    if not 1 <= requested_candidate_count <= spec.max_candidates_per_call:
        raise ValueError("requested_candidate_count exceeds the domain batch limit")
    payload = {
        "instructions": (
            "Generate exactly the requested number of executable task contracts. "
            "Return one JSON object with only task_contracts; each item must use exactly "
            "the declared output keys. Do not return lineage, source, domain, provider, "
            "branch-plan, path, credential, prompt, or compatibility fields."
        ),
        "domain_id": spec.domain_id,
        "requested_candidate_count": requested_candidate_count,
        "task_types": [
            {
                "task_type": item.task_type,
                "required_tools": list(item.required_tools),
                "allowed_expected_state_checks": list(item.allowed_expected_state_checks),
            }
            for item in spec.task_types
        ],
        "tools": list(spec.tools),
        "grounding_context": spec.grounding_context,
        "output_item_keys": sorted(_PROVIDER_RECORD_KEYS),
    }
    return _canonical_json(payload)


def build_generation_contract_evidence(
    *,
    profile: object | None,
    spec_metadata: Mapping[str, object] | None,
    target_candidate_count: int | None,
    generated_candidate_count: int | None,
) -> dict[str, object]:
    reasons: list[str] = []
    generation = getattr(profile, "generation", None)
    seed = getattr(profile, "seed", None)
    profile_representative = (
        getattr(profile, "schema_version", None) == "run_profile_v3"
        and getattr(profile, "profile_purpose", None) == "benchmark"
        and getattr(generation, "mode", None) == "llm"
    )
    if not profile_representative:
        reasons.append("profile_contract_not_representative")
    expected_domain = getattr(seed, "domain", None)
    if expected_domain == "contacts":
        expected_domain = "contacts_fixture"
    spec_valid = (
        spec_metadata is not None
        and spec_metadata.get("spec_version") == DOMAIN_GENERATION_SPEC_VERSION
        and spec_metadata.get("domain_id") == expected_domain
    )
    if not spec_valid:
        reasons.append("generation_spec_missing_or_mismatched")
    context_policy = spec_metadata.get("context_policy") if spec_metadata else None
    if context_policy != SYNTHETIC_CONTEXT_POLICY:
        reasons.append("context_policy_not_allowed")
    if getattr(profile, "source", None) is not None:
        reasons.append("source_backed_remote_context_not_allowed")
    target_fulfilled = (
        isinstance(target_candidate_count, int)
        and not isinstance(target_candidate_count, bool)
        and target_candidate_count > 0
        and generated_candidate_count == target_candidate_count
        and getattr(generation, "target_candidate_count", None) == target_candidate_count
    )
    if not target_fulfilled:
        reasons.append("target_candidate_count_unfulfilled")
    if spec_metadata is None or target_candidate_count is None or generated_candidate_count is None:
        reasons.append("generation_evidence_missing")
    evidence = {
        "spec_version": (
            spec_metadata.get("spec_version")
            if spec_metadata is not None
            else DOMAIN_GENERATION_SPEC_VERSION
        ),
        "context_policy": context_policy,
        "target_candidate_count": target_candidate_count,
        "generated_candidate_count": generated_candidate_count,
        "target_fulfilled": target_fulfilled,
        "representative_eligible": not reasons,
        "reason_codes": reasons,
        "grounding_context_hash": (
            spec_metadata.get("grounding_context_hash") if spec_metadata else None
        ),
    }
    return evidence


def task_contract_from_provider_record(
    raw: Mapping[str, object],
    *,
    seed: DomainSeed,
    spec: DomainGenerationSpec,
    generation_lineage: Mapping[str, object],
) -> TaskContract:
    validate_domain_generation_spec(spec)
    if not isinstance(raw, Mapping) or set(raw) != _PROVIDER_RECORD_KEYS:
        raise ValueError("provider task contract must contain exact supported keys")
    _validate_safe_value(raw, path="provider_task_contract")
    task_type = _required_text(raw.get("task_type"), "task_type")
    task_specs = {item.task_type: item for item in spec.task_types}
    if task_type not in task_specs:
        raise ValueError("provider task type is not declared by the domain")
    task_spec = task_specs[task_type]
    required_tools = _string_tuple(raw.get("required_tools"), "required_tools")
    registered_tools = {str(tool["name"]): tool for tool in spec.tools}
    if required_tools != task_spec.required_tools:
        raise ValueError("provider required_tools must exactly match the domain task type")
    if not set(required_tools) <= set(registered_tools):
        raise ValueError("provider task references an unregistered tool")
    primary_tool = _required_text(raw.get("primary_tool"), "primary_tool")
    if primary_tool != task_spec.required_tools[0]:
        raise ValueError("primary_tool must match the domain task type's first tool")
    primary_arguments = raw.get("primary_arguments")
    if not isinstance(primary_arguments, dict):
        raise ValueError("primary_arguments must be an object")
    validate_arguments_against_tool_definition(
        registered_tools[primary_tool],
        primary_arguments,
    )
    difficulty = raw.get("difficulty")
    if not isinstance(difficulty, Mapping):
        raise ValueError("difficulty must be an object")
    expected_state_raw = raw.get("expected_state")
    if not isinstance(expected_state_raw, list):
        raise ValueError("expected_state must be a list")
    expected_state: list[ExpectedStateCheck] = []
    mutating_tools = [
        registered_tools[name]
        for name in task_spec.required_tools
        if registered_tools[name].get("side_effects") == "state_mutating"
    ]
    if task_spec.allowed_expected_state_checks and len(mutating_tools) != 1:
        raise ValueError("state-mutating task type must declare exactly one mutating tool")
    seen_checks: set[str] = set()
    for index, state in enumerate(expected_state_raw):
        if not isinstance(state, Mapping) or set(state) != {"check_type", "expected"}:
            raise ValueError(f"expected_state.{index} must contain exact keys")
        check_type = _required_text(state.get("check_type"), f"expected_state.{index}.check_type")
        if check_type not in task_spec.allowed_expected_state_checks or check_type in seen_checks:
            raise ValueError("provider expected-state check is unsupported or duplicated")
        expected = state.get("expected")
        if not isinstance(expected, Mapping) or not expected:
            raise ValueError("expected-state expected value must be a non-empty object")
        validate_arguments_against_tool_definition(mutating_tools[0], dict(expected))
        seen_checks.add(check_type)
        expected_state.append(ExpectedStateCheck(check_type, dict(expected)))
    if task_spec.allowed_expected_state_checks and not expected_state:
        raise ValueError("state-mutating task type requires expected-state evidence")
    capabilities = _string_tuple(raw.get("required_capabilities"), "required_capabilities")
    contract = TaskContract(
        intent=TaskIntent(
            candidate_id=_required_text(raw.get("candidate_id"), "candidate_id"),
            instruction=_required_text(raw.get("instruction"), "instruction"),
            domain_id=spec.domain_id,
            task_type=task_type,
            difficulty=dict(difficulty),
            required_capabilities=capabilities,
            seed_ids=(seed.seed_id,),
            lineage={"generation": dict(generation_lineage)},
        ),
        policy_hint=PolicyHint(
            required_tools=required_tools,
            primary_tool=primary_tool,
            primary_arguments=dict(primary_arguments),
        ),
        expected_outcome=ExpectedOutcome(
            _required_text(raw.get("final_answer_contains"), "final_answer_contains")
        ),
        expected_state=tuple(expected_state),
        compatibility={
            "constraints": {
                "domain": spec.domain_id,
                "task_type": task_type,
                "required_capabilities": list(capabilities),
                "required_tools": list(required_tools),
            },
            "generation_lineage": dict(generation_lineage),
        },
    )
    return validate_task_contract(contract)


def parse_domain_task_contracts(
    content: Mapping[str, object],
    *,
    seed: DomainSeed,
    spec: DomainGenerationSpec,
    generation_lineage: Mapping[str, object],
) -> list[TaskContract]:
    if not isinstance(content, Mapping) or set(content) != {"task_contracts"}:
        raise ValueError("provider response must contain only task_contracts")
    records = content.get("task_contracts")
    if not isinstance(records, list):
        raise ValueError("task_contracts must be a list")
    contracts = [
        task_contract_from_provider_record(
            record,
            seed=seed,
            spec=spec,
            generation_lineage=generation_lineage,
        )
        for record in records
    ]
    ids = [contract.intent.candidate_id for contract in contracts]
    if len(ids) != len(set(ids)):
        raise ValueError("provider response contains duplicate candidate ids")
    return contracts


def generate_domain_llm_candidates(
    seed: DomainSeed,
    client: object,
    *,
    spec: DomainGenerationSpec,
    target_candidate_count: int,
    role_registry: RoleRegistry | None = None,
) -> DomainGenerationResult:
    validate_domain_generation_spec(spec)
    if (
        not isinstance(target_candidate_count, int)
        or isinstance(target_candidate_count, bool)
        or target_candidate_count <= 0
    ):
        raise ValueError("target_candidate_count must be positive")
    registry = role_registry or default_role_registry()
    candidates: list[CandidateTask] = []
    candidate_ids: set[str] = set()
    provider_call_count = 0
    while len(candidates) < target_candidate_count:
        requested = min(spec.max_candidates_per_call, target_candidate_count - len(candidates))
        result = registry.invoke_json(
            TASK_GENERATION_ROLE,
            client,
            build_domain_generation_prompt(spec, requested_candidate_count=requested),
        )
        provider_call_count += 1
        try:
            contracts = parse_domain_task_contracts(
                result.content,
                seed=seed,
                spec=spec,
                generation_lineage=result.lineage,
            )
            if len(contracts) != requested:
                raise ValueError("provider batch did not exactly fulfill requested count")
            batch_ids = {contract.intent.candidate_id for contract in contracts}
            if candidate_ids & batch_ids:
                raise ValueError("provider batches contain duplicate candidate ids")
        except (TypeError, ValueError, KeyError) as exc:
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class=type(exc).__name__,
                retryable=False,
                retry_count=_retry_count(result.lineage),
                lineage=result.lineage,
            ) from exc
        candidate_ids.update(batch_ids)
        candidates.extend(candidate_from_task_contract(contract) for contract in contracts)
    ordered = order_candidates_by_curriculum(candidates)
    return DomainGenerationResult(
        candidates=tuple(ordered),
        target_candidate_count=target_candidate_count,
        generated_candidate_count=len(ordered),
        provider_call_count=provider_call_count,
        spec_metadata=sanitized_generation_spec_metadata(spec),
    )


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    values = tuple(_required_text(item, f"{path}.{index}") for index, item in enumerate(value))
    if not values or len(values) != len(set(values)):
        raise ValueError(f"{path} must contain unique strings")
    return values


def _retry_count(lineage: Mapping[str, object]) -> int:
    value = lineage.get("retry_count", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _sha256_mapping(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _required_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _validate_safe_value(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _required_text(raw_key, path).lower()
            if key in _UNSAFE_KEYS or any(part in _UNSAFE_KEYS for part in key.split("_")):
                raise ValueError(f"{path}.{key} is unsafe")
            _validate_safe_value(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_safe_value(child, path=f"{path}.{index}")
        return
    if isinstance(value, str):
        if PurePath(value).is_absolute() or any(pattern.search(value) for pattern in _UNSAFE_STRING_PATTERNS):
            raise ValueError(f"{path} contains an unsafe string")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError(f"{path} contains an unsupported value")
