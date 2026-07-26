from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Mapping

from synthesis.contracts import LLM_RESPONSE_SCHEMA_DETAILS, LLM_RESPONSE_SCHEMA_REASONS
from synthesis.llm import LLMProviderError
from synthesis.profile_contracts import (
    REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS,
)
from synthesis.roles import TASK_GENERATION_ROLE, RoleRegistry, default_role_registry
from synthesis.seeds import DomainSeed
from synthesis.stable_ids import stable_id
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
from synthesis.tools import ToolSchemaError, validate_arguments_against_tool_definition


DOMAIN_GENERATION_SPEC_VERSION = "domain_generation_spec_v1"
SYNTHETIC_CONTEXT_POLICY = "synthetic_fixture"
MAX_CANDIDATES_PER_CALL = 5
MAX_EXCLUDED_INSTRUCTIONS = 20
FINAL_ANSWER_SOURCES = {
    "primary_observation",
    "state_tool_observation",
}
DERIVED_FINAL_ANSWER_SENTINEL = "$derived_from_expected_state$"
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
    required_capabilities: tuple[str, ...] = ()
    expected_state_tool: str | None = None
    final_answer_source: str = "primary_observation"
    final_answer_fields: tuple[str, ...] = ()
    final_answer_derivation: str | None = None
    expected_state_reference_fields: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DomainGenerationSpec:
    schema_version: str
    domain_id: str
    task_types: tuple[DomainTaskTypeSpec, ...]
    tools: tuple[Mapping[str, object], ...]
    grounding_context: Mapping[str, object]
    context_policy: str
    max_candidates_per_call: int
    grounding_window_size: int | None = None


@dataclass(frozen=True)
class DomainGenerationResult:
    candidates: tuple[CandidateTask, ...]
    target_candidate_count: int
    generated_candidate_count: int
    provider_call_count: int
    spec_metadata: Mapping[str, object]


@dataclass(frozen=True)
class DomainGenerationBatchContext:
    batch_index: int
    candidate_id_prefix: str


_PROVIDER_RECORD_KEYS = {
    "candidate_id", "instruction", "task_type", "difficulty",
    "required_capabilities", "required_tools", "primary_tool",
    "primary_arguments", "final_answer_contains", "expected_state",
}

_DERIVATION_PLACEHOLDER_RE = re.compile(
    r"\{([A-Za-z_][A-Za-z0-9_]*)(?:\|(stable_id))?\}"
)


class DomainGenerationValidationError(ValueError):
    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        if reason not in LLM_RESPONSE_SCHEMA_REASONS:
            raise ValueError("unsupported domain generation schema reason")
        if detail is not None and detail not in LLM_RESPONSE_SCHEMA_DETAILS.get(reason, set()):
            raise ValueError("unsupported domain generation schema detail")
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def build_generation_batch_context(
    spec: DomainGenerationSpec,
    *,
    batch_index: int,
) -> DomainGenerationBatchContext:
    validate_domain_generation_spec(spec)
    if (
        not isinstance(batch_index, int)
        or isinstance(batch_index, bool)
        or batch_index <= 0
    ):
        raise ValueError("batch_index must be a positive integer")
    safe_domain = spec.domain_id.removesuffix("_fixture")
    return DomainGenerationBatchContext(
        batch_index=batch_index,
        candidate_id_prefix=f"{safe_domain}_b{batch_index:03d}_",
    )


def validate_domain_generation_spec(spec: DomainGenerationSpec) -> None:
    if spec.schema_version != DOMAIN_GENERATION_SPEC_VERSION:
        raise ValueError("generation_spec_missing_or_mismatched")
    _required_text(spec.domain_id, "domain_id")
    _validate_safe_value(spec.domain_id, path="domain_id")
    if spec.context_policy != SYNTHETIC_CONTEXT_POLICY:
        raise ValueError("context_policy_not_allowed")
    if not 1 <= spec.max_candidates_per_call <= MAX_CANDIDATES_PER_CALL:
        raise ValueError("max_candidates_per_call must be between 1 and 5")
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
        if (
            not item.required_capabilities
            or len(item.required_capabilities) != len(set(item.required_capabilities))
        ):
            raise ValueError("required capabilities must contain unique strings")
        for capability in item.required_capabilities:
            _required_text(capability, "required_capabilities")
        _validate_safe_value(
            item.required_capabilities,
            path=f"task_types.{task_type}.required_capabilities",
        )
        mutating_tools = tuple(
            tool_name
            for tool_name in item.required_tools
            if next(tool for tool in spec.tools if tool["name"] == tool_name)[
                "side_effects"
            ] == "state_mutating"
        )
        if mutating_tools:
            if len(mutating_tools) != 1:
                raise ValueError(
                    f"task type {task_type} must declare exactly one state-mutating tool"
                )
            if item.expected_state_tool != mutating_tools[0]:
                raise ValueError(
                    f"task type {task_type} must own its state-mutating tool"
                )
            if not item.allowed_expected_state_checks:
                raise ValueError(
                    f"task type {task_type} must declare expected-state checks"
                )
        elif item.expected_state_tool is not None:
            raise ValueError(
                f"read-only task type {task_type} must not declare an expected-state tool"
            )
        if item.final_answer_source not in FINAL_ANSWER_SOURCES:
            raise ValueError("unsupported final-answer source")
        if (
            item.final_answer_source == "state_tool_observation"
            and item.expected_state_tool is None
        ):
            raise ValueError("state-tool final answers require an expected-state tool")
        if item.final_answer_derivation is not None:
            if item.final_answer_source != "state_tool_observation":
                raise ValueError(
                    "final-answer derivation requires state-tool observation answers"
                )
            derivation = _required_text(
                item.final_answer_derivation,
                "final_answer_derivation",
            )
            _validate_safe_value(
                derivation,
                path=f"task_types.{task_type}.final_answer_derivation",
            )
            mutating_tool = next(
                tool for tool in spec.tools if tool["name"] == item.expected_state_tool
            )
            schema = mutating_tool["schema"]
            properties = (
                schema.get("properties", {}) if isinstance(schema, Mapping) else {}
            )
            for field_name, _transform in _parse_derivation_template(derivation):
                if field_name not in properties:
                    raise ValueError(
                        "final-answer derivation placeholders must reference "
                        "mutating-tool schema fields"
                    )
        if item.expected_state_reference_fields:
            if item.expected_state_tool is None:
                raise ValueError(
                    "expected-state reference fields require an expected-state tool"
                )
            reference_pairs: set[tuple[str, str]] = set()
            mutating_tool = next(
                tool for tool in spec.tools if tool["name"] == item.expected_state_tool
            )
            schema = mutating_tool["schema"]
            properties = (
                schema.get("properties", {}) if isinstance(schema, Mapping) else {}
            )
            for pair in item.expected_state_reference_fields:
                if (
                    not isinstance(pair, tuple)
                    or len(pair) != 2
                    or any(
                        not isinstance(name, str)
                        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                        for name in pair
                    )
                ):
                    raise ValueError(
                        "expected-state reference fields must be safe identifier pairs"
                    )
                if pair in reference_pairs:
                    raise ValueError(
                        "expected-state reference fields must not repeat pairs"
                    )
                reference_pairs.add(pair)
                if pair[0] not in properties:
                    raise ValueError(
                        "expected-state reference fields must reference "
                        "mutating-tool schema fields"
                    )
            _validate_safe_value(
                [list(pair) for pair in item.expected_state_reference_fields],
                path=f"task_types.{task_type}.expected_state_reference_fields",
            )
        if (
            not item.final_answer_fields
            or len(item.final_answer_fields) != len(set(item.final_answer_fields))
        ):
            raise ValueError("final-answer fields must contain unique safe identifiers")
        for field in item.final_answer_fields:
            if not isinstance(field, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field) is None:
                raise ValueError("final-answer fields must contain unique safe identifiers")
        _validate_safe_value(
            item.final_answer_fields,
            path=f"task_types.{task_type}.final_answer_fields",
        )
    if not spec.grounding_context:
        raise ValueError("grounding_context must not be empty")
    _validate_safe_value(spec.grounding_context, path="grounding_context")
    if spec.grounding_window_size is not None:
        if (
            not isinstance(spec.grounding_window_size, int)
            or isinstance(spec.grounding_window_size, bool)
            or spec.grounding_window_size < 1
        ):
            raise ValueError("grounding_window_size must be a positive integer")
        if len(spec.grounding_context) == 1:
            only_value = next(iter(spec.grounding_context.values()))
            if isinstance(only_value, list) and spec.grounding_window_size > len(only_value):
                raise ValueError("grounding_window_size exceeds the grounding entry count")


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
    batch_context: DomainGenerationBatchContext,
    excluded_instructions: tuple[str, ...] = (),
) -> str:
    validate_domain_generation_spec(spec)
    if not 1 <= requested_candidate_count <= spec.max_candidates_per_call:
        raise ValueError("requested_candidate_count exceeds the domain batch limit")
    exclusions = _bounded_exclusions(excluded_instructions)
    focused_task_type = spec.task_types[
        (batch_context.batch_index - 1) % len(spec.task_types)
    ]
    rendered_grounding = _rendered_grounding_context(spec, batch_context.batch_index)
    payload = {
        "instructions": (
            "Generate exactly the requested number of executable task contracts. "
            "Return one JSON object with only task_contracts; each item must use exactly "
            "the declared output keys. For each record, copy task_type, required_tools, "
            "and primary_tool exactly from one task_type_contract; primary_tool is always "
            "required_tools[0], including tasks that mutate state through a later tool. "
            "For primary-observation task types, final_answer_contains must be a "
            "substring copied from the observation value of one grounding_context "
            "entry using one of the declared allowed_fields; copying the field name "
            "itself is forbidden. For state-tool-observation task types, "
            "final_answer_contains must equal the sentinel in the task type's "
            "final_answer block; do not predict the minted identifier. "
            "Copy primary_arguments exactly from one grounding_context entry; do not "
            "invent alternate search terms, filters, names, or identifiers. "
            "For expected_state entries, each declared reference field value must be "
            "copied from the referenced grounding_context observation field; invented "
            "references are forbidden. "
            "Do not return lineage, source, domain, provider, branch-plan, path, "
            "credential, prompt, or compatibility fields."
        ),
        "domain_id": spec.domain_id,
        "requested_candidate_count": requested_candidate_count,
        "batch_context": {
            "batch_index": batch_context.batch_index,
            "candidate_id_prefix": batch_context.candidate_id_prefix,
        },
        "task_types": [
            {
                "task_type": focused_task_type.task_type,
                "required_tools": list(focused_task_type.required_tools),
                "required_capabilities": list(focused_task_type.required_capabilities),
                "allowed_expected_state_checks": list(
                    focused_task_type.allowed_expected_state_checks
                ),
                "expected_state_tool": focused_task_type.expected_state_tool,
                "final_answer": _final_answer_prompt_contract(
                    focused_task_type,
                    rendered_grounding,
                ),
            }
        ],
        "tools": list(spec.tools),
        "grounding_context": rendered_grounding,
        "diversity_contract": {
            "excluded_instructions": list(exclusions),
            "rule": "do not repeat or paraphrase these instructions",
        },
        "output_contract": _provider_output_contract(
            spec,
            requested_candidate_count=requested_candidate_count,
            batch_context=batch_context,
            focused_task_type=focused_task_type,
            rendered_grounding=rendered_grounding,
        ),
    }
    return _canonical_json(payload)


def _bounded_exclusions(excluded_instructions: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(excluded_instructions, tuple) or any(
        not isinstance(item, str) or not item.strip()
        for item in excluded_instructions
    ):
        raise ValueError("excluded_instructions must be a tuple of non-empty strings")
    return excluded_instructions[-MAX_EXCLUDED_INSTRUCTIONS:]


def _rendered_grounding_context(
    spec: DomainGenerationSpec,
    batch_index: int,
) -> Mapping[str, object]:
    if spec.grounding_window_size is None or len(spec.grounding_context) != 1:
        return spec.grounding_context
    key = next(iter(spec.grounding_context))
    entries = spec.grounding_context[key]
    if not isinstance(entries, list) or not entries:
        return spec.grounding_context
    entry_count = len(entries)
    window_size = min(spec.grounding_window_size, entry_count)
    start = ((batch_index - 1) * spec.grounding_window_size) % entry_count
    return {
        key: [
            entries[(start + offset) % entry_count]
            for offset in range(window_size)
        ]
    }


def _provider_output_contract(
    spec: DomainGenerationSpec,
    *,
    requested_candidate_count: int,
    batch_context: DomainGenerationBatchContext,
    focused_task_type: DomainTaskTypeSpec,
    rendered_grounding: Mapping[str, object],
) -> dict[str, object]:
    return {
        "json_only": True,
        "markdown_allowed": False,
        "commentary_allowed": False,
        "response": {
            "type": "object",
            "exact_keys": ["task_contracts"],
            "task_contracts": {
                "type": "array",
                "exact_count": requested_candidate_count,
                "unique_by": "candidate_id",
                "items": _provider_record_contract(batch_context=batch_context),
            },
        },
        "task_type_contracts": [
            {
                "task_type": focused_task_type.task_type,
                "required_tools": list(focused_task_type.required_tools),
                "primary_tool": focused_task_type.required_tools[0],
                "exact_record_values": {
                    "task_type": focused_task_type.task_type,
                    "required_capabilities": list(focused_task_type.required_capabilities),
                    "required_tools": list(focused_task_type.required_tools),
                    "primary_tool": focused_task_type.required_tools[0],
                },
                "expected_state": _expected_state_output_contract(
                    focused_task_type,
                    spec.tools,
                ),
                "expected_state_tool": focused_task_type.expected_state_tool,
                "final_answer": _final_answer_prompt_contract(
                    focused_task_type,
                    rendered_grounding,
                ),
            }
        ],
        "critical_rules": {
            "candidate_id": {
                "must_start_with": batch_context.candidate_id_prefix,
                "alternative_prefixes_allowed": False,
            },
            "primary_tool": {
                "must_equal": "required_tools[0]",
                "must_equal_selected_task_type_contract": True,
                "alternatives_allowed": False,
            },
            "primary_arguments": {
                "must_match_curated_tool_schema_for": "primary_tool",
                "must_copy_exact_from": "grounding_context.*.primary_arguments",
                "invented_arguments_allowed": False,
            },
        },
        "forbidden_fields": sorted(
            _UNSAFE_KEYS
            | {
                "branch_plan",
                "compatibility",
                "domain",
                "domain_id",
                "lineage",
                "provider",
                "source",
            }
        ),
    }


def _final_answer_prompt_contract(
    task_type: DomainTaskTypeSpec,
    grounding_context: Mapping[str, object],
) -> dict[str, object]:
    contract: dict[str, object] = {
        "source": task_type.final_answer_source,
        "allowed_fields": list(task_type.final_answer_fields),
        "invented_text_allowed": False,
    }
    if task_type.final_answer_derivation is not None:
        contract["value_contract"] = "sentinel"
        contract["sentinel"] = DERIVED_FINAL_ANSWER_SENTINEL
        return contract
    example = _final_answer_example(task_type, grounding_context)
    if example is not None:
        contract["example"] = example
    return contract


def _final_answer_example(
    task_type: DomainTaskTypeSpec,
    grounding_context: Mapping[str, object],
) -> dict[str, str] | None:
    for top_level in grounding_context.values():
        if not isinstance(top_level, list):
            continue
        for entry in top_level:
            if not isinstance(entry, Mapping):
                continue
            observation = entry.get("observation")
            if not isinstance(observation, Mapping):
                continue
            for field in task_type.final_answer_fields:
                value = observation.get(field)
                if isinstance(value, str) and value:
                    return {"field": field, "value": value}
    return None


def _expected_state_output_contract(
    task_type: DomainTaskTypeSpec,
    tools: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    if not task_type.allowed_expected_state_checks:
        return {"mode": "empty"}
    mutating_tool = next(
        tool for tool in tools if tool.get("name") == task_type.expected_state_tool
    )
    contract: dict[str, object] = {
        "mode": "required",
        "exact_count": len(task_type.allowed_expected_state_checks),
        "allowed_check_types": list(task_type.allowed_expected_state_checks),
        "exact_items": [
            {
                "check_type": check_type,
                "expected_must_match_tool_schema": mutating_tool["name"],
                "expected_schema": mutating_tool["schema"],
            }
            for check_type in task_type.allowed_expected_state_checks
        ],
    }
    if task_type.expected_state_reference_fields:
        contract["reference_fields"] = {
            state_field: observation_field
            for state_field, observation_field in task_type.expected_state_reference_fields
        }
    return contract


def _provider_record_contract(
    *,
    batch_context: DomainGenerationBatchContext,
) -> dict[str, object]:
    non_empty_string = {"type": "string", "non_empty": True}
    non_empty_unique_strings = {
        "type": "array",
        "non_empty": True,
        "unique_items": True,
        "items": non_empty_string,
    }
    return {
        "type": "object",
        "exact_keys": sorted(_PROVIDER_RECORD_KEYS),
        "fields": {
            "candidate_id": {
                **non_empty_string,
                "unique": True,
                "starts_with": batch_context.candidate_id_prefix,
            },
            "instruction": non_empty_string,
            "task_type": non_empty_string,
            "difficulty": {"type": "object"},
            "required_capabilities": non_empty_unique_strings,
            "required_tools": non_empty_unique_strings,
            "primary_tool": non_empty_string,
            "primary_arguments": {"type": "object"},
            "final_answer_contains": non_empty_string,
            "expected_state": {
                "type": "array",
                "items": {
                    "type": "object",
                    "exact_keys": ["check_type", "expected"],
                    "fields": {
                        "check_type": non_empty_string,
                        "expected": {"type": "object", "non_empty": True},
                    },
                },
            },
        },
    }


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
        getattr(profile, "schema_version", None)
        in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS
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
    candidate_id_prefix: str,
    generation_lineage: Mapping[str, object],
) -> TaskContract:
    validate_domain_generation_spec(spec)
    _validate_provider_record_shape(raw)
    try:
        _validate_safe_value(raw, path="provider_task_contract")
    except (TypeError, ValueError, KeyError) as exc:
        raise DomainGenerationValidationError("unsafe_provider_value") from exc
    task_type = _provider_text(raw.get("task_type"), "invalid_task_type")
    task_specs = {item.task_type: item for item in spec.task_types}
    if task_type not in task_specs:
        raise DomainGenerationValidationError("invalid_task_type")
    task_spec = task_specs[task_type]
    candidate_id = _required_text(raw.get("candidate_id"), "candidate_id")
    if not candidate_id.startswith(candidate_id_prefix):
        raise DomainGenerationValidationError(
            "invalid_candidate_id",
            detail="batch_prefix_mismatch",
        )
    registered_tools = {str(tool["name"]): tool for tool in spec.tools}
    required_tools = _provider_required_tools(
        raw.get("required_tools"),
        expected=task_spec.required_tools,
        registered=set(registered_tools),
    )
    primary_tool = _provider_primary_tool(
        raw.get("primary_tool"),
        expected=task_spec.required_tools[0],
    )
    primary_arguments = _provider_tool_arguments(
        raw.get("primary_arguments"),
        tool=registered_tools[primary_tool],
    )
    difficulty = _provider_difficulty(raw.get("difficulty"))
    expected_state = _provider_expected_state(
        raw.get("expected_state"),
        task_spec=task_spec,
        registered_tools=registered_tools,
        grounding_context=spec.grounding_context,
    )
    capabilities = _provider_capabilities(
        raw.get("required_capabilities"),
        expected=task_spec.required_capabilities,
    )
    final_answer = _provider_final_answer(
        raw.get("final_answer_contains"),
        task_spec=task_spec,
        expected_state=expected_state,
        grounding_context=spec.grounding_context,
    )
    try:
        contract = TaskContract(
            intent=TaskIntent(
                candidate_id=candidate_id,
                instruction=_required_text(raw.get("instruction"), "instruction"),
                domain_id=spec.domain_id,
                task_type=task_type,
                difficulty=difficulty,
                required_capabilities=capabilities,
                seed_ids=(seed.seed_id,),
                lineage={"generation": dict(generation_lineage)},
            ),
            policy_hint=PolicyHint(
                required_tools=required_tools,
                primary_tool=primary_tool,
                primary_arguments=primary_arguments,
            ),
            expected_outcome=ExpectedOutcome(final_answer),
            expected_state=expected_state,
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
    except (TypeError, ValueError, KeyError) as exc:
        raise DomainGenerationValidationError("unsafe_provider_value") from exc


def _validate_provider_record_shape(raw: object) -> None:
    if not isinstance(raw, Mapping) or set(raw) != _PROVIDER_RECORD_KEYS:
        raise DomainGenerationValidationError("provider_record_keys_mismatch")


def _provider_text(value: object, reason: str) -> str:
    try:
        return _required_text(value, "provider_field")
    except (TypeError, ValueError) as exc:
        raise DomainGenerationValidationError(reason) from exc


def _provider_required_tools(
    value: object,
    *,
    expected: tuple[str, ...],
    registered: set[str],
) -> tuple[str, ...]:
    try:
        required_tools = _string_tuple(value, "required_tools")
    except (TypeError, ValueError) as exc:
        raise DomainGenerationValidationError("invalid_required_tools") from exc
    if required_tools != expected or not set(required_tools) <= registered:
        raise DomainGenerationValidationError("invalid_required_tools")
    return required_tools


def _provider_primary_tool(value: object, *, expected: str) -> str:
    primary_tool = _provider_text(value, "invalid_primary_tool")
    if primary_tool != expected:
        raise DomainGenerationValidationError("invalid_primary_tool")
    return primary_tool


def _provider_tool_arguments(
    value: object,
    *,
    tool: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainGenerationValidationError("invalid_tool_arguments")
    try:
        validate_arguments_against_tool_definition(tool, value)
    except (ToolSchemaError, TypeError, ValueError, KeyError) as exc:
        raise DomainGenerationValidationError("invalid_tool_arguments") from exc
    return dict(value)


def _provider_difficulty(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise DomainGenerationValidationError("invalid_difficulty")
    return dict(value)


def _provider_expected_state(
    value: object,
    *,
    task_spec: DomainTaskTypeSpec,
    registered_tools: Mapping[str, Mapping[str, object]],
    grounding_context: Mapping[str, object],
) -> tuple[ExpectedStateCheck, ...]:
    if not isinstance(value, list):
        raise DomainGenerationValidationError(
            "invalid_expected_state",
            detail="expected_state_not_list",
        )
    mutating_tool = (
        registered_tools.get(task_spec.expected_state_tool)
        if task_spec.expected_state_tool is not None
        else None
    )
    if task_spec.allowed_expected_state_checks and mutating_tool is None:
        raise DomainGenerationValidationError(
            "invalid_expected_state",
            detail="expected_state_missing",
        )
    expected_state: list[ExpectedStateCheck] = []
    seen_checks: set[str] = set()
    for state in value:
        if not isinstance(state, Mapping) or set(state) != {"check_type", "expected"}:
            raise DomainGenerationValidationError(
                "invalid_expected_state",
                detail="expected_state_item_keys_mismatch",
            )
        check_type = state.get("check_type")
        if (
            not isinstance(check_type, str)
            or not check_type.strip()
            or check_type not in task_spec.allowed_expected_state_checks
        ):
            raise DomainGenerationValidationError(
                "invalid_expected_state",
                detail="expected_state_check_type_invalid",
            )
        if check_type in seen_checks:
            raise DomainGenerationValidationError(
                "invalid_expected_state",
                detail="expected_state_check_duplicate",
            )
        expected = state.get("expected")
        if not isinstance(expected, Mapping) or not expected:
            raise DomainGenerationValidationError(
                "invalid_expected_state",
                detail="expected_state_expected_not_object",
            )
        try:
            validate_arguments_against_tool_definition(mutating_tool, dict(expected))
        except (ToolSchemaError, TypeError, ValueError, KeyError) as exc:
            raise DomainGenerationValidationError(
                "invalid_expected_state",
                detail="expected_state_arguments_invalid",
            ) from exc
        for state_field, observation_field in task_spec.expected_state_reference_fields:
            if state_field not in expected:
                continue
            reference = expected[state_field]
            grounded_references = _grounding_observation_values(
                grounding_context,
                (observation_field,),
            )
            if not isinstance(reference, str) or reference not in grounded_references:
                raise DomainGenerationValidationError(
                    "invalid_expected_state",
                    detail="expected_state_reference_not_grounded",
                )
        seen_checks.add(check_type)
        expected_state.append(ExpectedStateCheck(check_type, dict(expected)))
    if task_spec.allowed_expected_state_checks and not expected_state:
        raise DomainGenerationValidationError(
            "invalid_expected_state",
            detail="expected_state_missing",
        )
    if not task_spec.allowed_expected_state_checks and expected_state:
        raise DomainGenerationValidationError(
            "invalid_expected_state",
            detail="expected_state_check_type_invalid",
        )
    return tuple(expected_state)


def _provider_final_answer(
    value: object,
    *,
    task_spec: DomainTaskTypeSpec,
    expected_state: tuple[ExpectedStateCheck, ...],
    grounding_context: Mapping[str, object],
) -> str:
    answer = _provider_text(value, "invalid_final_answer")
    if task_spec.final_answer_derivation is not None:
        if answer != DERIVED_FINAL_ANSWER_SENTINEL:
            raise DomainGenerationValidationError(
                "invalid_final_answer",
                detail="final_answer_sentinel_mismatch",
            )
        return _derive_final_answer(task_spec.final_answer_derivation, expected_state)
    if answer in task_spec.final_answer_fields:
        raise DomainGenerationValidationError(
            "invalid_final_answer",
            detail="final_answer_field_name_literal",
        )
    grounded_values = _grounding_observation_values(
        grounding_context,
        task_spec.final_answer_fields,
    )
    if not any(answer in grounded for grounded in grounded_values):
        raise DomainGenerationValidationError(
            "invalid_final_answer",
            detail="final_answer_not_grounded",
        )
    return answer


def _grounding_observation_values(
    grounding_context: Mapping[str, object],
    fields: tuple[str, ...],
) -> list[str]:
    values: list[str] = []
    for top_level in grounding_context.values():
        if not isinstance(top_level, list):
            continue
        for entry in top_level:
            if not isinstance(entry, Mapping):
                continue
            observation = entry.get("observation")
            if not isinstance(observation, Mapping):
                continue
            for field in fields:
                field_value = observation.get(field)
                if isinstance(field_value, str):
                    values.append(field_value)
    return values


def _parse_derivation_template(template: str) -> list[tuple[str, str | None]]:
    placeholders: list[tuple[str, str | None]] = []
    position = 0
    for match in _DERIVATION_PLACEHOLDER_RE.finditer(template):
        literal = template[position:match.start()]
        if "{" in literal or "}" in literal:
            raise ValueError("malformed final-answer derivation template")
        placeholders.append((match.group(1), match.group(2)))
        position = match.end()
    if "{" in template[position:] or "}" in template[position:]:
        raise ValueError("malformed final-answer derivation template")
    if not placeholders:
        raise ValueError("final-answer derivation template must contain a placeholder")
    return placeholders


def _derive_final_answer(
    template: str,
    expected_state: tuple[ExpectedStateCheck, ...],
) -> str:
    parts: list[str] = []
    position = 0
    for match in _DERIVATION_PLACEHOLDER_RE.finditer(template):
        parts.append(template[position:match.start()])
        field_name = match.group(1)
        value: object = None
        for state_check in expected_state:
            if field_name in state_check.expected:
                value = state_check.expected[field_name]
                break
        if not isinstance(value, str) or not value.strip():
            raise DomainGenerationValidationError(
                "invalid_final_answer",
                detail="final_answer_derivation_failed",
            )
        parts.append(stable_id(value) if match.group(2) == "stable_id" else value)
        position = match.end()
    parts.append(template[position:])
    derived = "".join(parts)
    if not derived.strip():
        raise DomainGenerationValidationError(
            "invalid_final_answer",
            detail="final_answer_derivation_failed",
        )
    return derived


def _provider_capabilities(
    value: object,
    *,
    expected: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DomainGenerationValidationError(
            "invalid_required_capabilities",
            detail="required_capabilities_not_list",
        )
    if not value:
        raise DomainGenerationValidationError(
            "invalid_required_capabilities",
            detail="required_capabilities_empty",
        )
    try:
        capabilities = tuple(
            _required_text(item, f"required_capabilities.{index}")
            for index, item in enumerate(value)
        )
    except (TypeError, ValueError) as exc:
        raise DomainGenerationValidationError(
            "invalid_required_capabilities",
            detail="required_capabilities_contract_mismatch",
        ) from exc
    if len(capabilities) != len(set(capabilities)):
        raise DomainGenerationValidationError(
            "invalid_required_capabilities",
            detail="required_capabilities_duplicate",
        )
    if capabilities != expected:
        raise DomainGenerationValidationError(
            "invalid_required_capabilities",
            detail="required_capabilities_contract_mismatch",
        )
    return capabilities


def parse_domain_task_contracts(
    content: Mapping[str, object],
    *,
    seed: DomainSeed,
    spec: DomainGenerationSpec,
    batch_context: DomainGenerationBatchContext,
    generation_lineage: Mapping[str, object],
) -> list[TaskContract]:
    if not isinstance(content, Mapping) or set(content) != {"task_contracts"}:
        raise DomainGenerationValidationError("response_shape_mismatch")
    records = content.get("task_contracts")
    if not isinstance(records, list):
        raise DomainGenerationValidationError("response_shape_mismatch")
    contracts = [
        task_contract_from_provider_record(
            record,
            seed=seed,
            spec=spec,
            candidate_id_prefix=batch_context.candidate_id_prefix,
            generation_lineage=generation_lineage,
        )
        for record in records
    ]
    ids = [contract.intent.candidate_id for contract in contracts]
    if len(ids) != len(set(ids)):
        raise DomainGenerationValidationError(
            "duplicate_candidate_id",
            detail="within_batch",
        )
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
        batch_context = build_generation_batch_context(
            spec,
            batch_index=provider_call_count + 1,
        )
        excluded_instructions = tuple(
            candidate.instruction
            for candidate in candidates[-MAX_EXCLUDED_INSTRUCTIONS:]
        )
        try:
            result = registry.invoke_json(
                TASK_GENERATION_ROLE,
                client,
                build_domain_generation_prompt(
                    spec,
                    requested_candidate_count=requested,
                    batch_context=batch_context,
                    excluded_instructions=excluded_instructions,
                ),
            )
        except LLMProviderError as exc:
            raise LLMProviderError(
                cause=exc.cause,
                error_class=exc.error_class,
                retryable=exc.retryable,
                retry_count=exc.retry_count,
                lineage={
                    **exc.lineage,
                    "batch_index": batch_context.batch_index,
                    "requested_candidate_count": requested,
                },
                schema_reason=exc.schema_reason,
                schema_detail=exc.schema_detail,
            ) from exc
        provider_call_count += 1
        try:
            raw_records = (
                result.content.get("task_contracts")
                if isinstance(result.content, Mapping)
                else None
            )
            if isinstance(raw_records, list):
                raw_ids = {
                    record.get("candidate_id")
                    for record in raw_records
                    if isinstance(record, Mapping)
                    and isinstance(record.get("candidate_id"), str)
                }
                if candidate_ids & raw_ids:
                    raise DomainGenerationValidationError(
                        "duplicate_candidate_id",
                        detail="across_batch",
                    )
            contracts = parse_domain_task_contracts(
                result.content,
                seed=seed,
                spec=spec,
                batch_context=batch_context,
                generation_lineage={
                    **result.lineage,
                    "excluded_instruction_count": len(excluded_instructions),
                },
            )
            if len(contracts) != requested:
                raise DomainGenerationValidationError("batch_count_mismatch")
            batch_ids = {contract.intent.candidate_id for contract in contracts}
        except DomainGenerationValidationError as exc:
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="DomainGenerationValidationError",
                retryable=False,
                retry_count=_retry_count(result.lineage),
                lineage={
                    **result.lineage,
                    "batch_index": batch_context.batch_index,
                    "requested_candidate_count": requested,
                },
                schema_reason=exc.reason,
                schema_detail=exc.detail,
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
