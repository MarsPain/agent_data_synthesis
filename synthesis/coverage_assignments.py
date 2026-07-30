from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Callable, Mapping, cast

from synthesis.coverage import (
    CoverageCatalog,
    CoveragePlan,
    canonical_coverage_hash,
    canonical_coverage_json,
)
from synthesis.datasets import assemble_generation_stage_rejection
from synthesis.domain_generation import (
    DomainGenerationBatchContext,
    DomainGenerationSpec,
    DomainGenerationValidationError,
    build_domain_generation_prompt,
    build_generation_batch_context,
    task_contract_from_provider_record,
    validate_domain_generation_spec,
)
from synthesis.domain_pipeline import DomainPipelineBundle
from synthesis.llm import LLMProviderError
from synthesis.roles import TASK_GENERATION_ROLE, RoleRegistry, default_role_registry
from synthesis.seeds import DomainSeed
from synthesis.task_contracts import candidate_from_task_contract
from synthesis.task_contracts import TaskContract
from synthesis.tasks import CandidateTask


COVERAGE_ASSIGNMENT_VERSION = "coverage_assignment_v1"
COVERAGE_ASSIGNMENT_LINEAGE_VERSION = "coverage_assignment_lineage_v1"
COVERAGE_SCHEDULER_VERSION = "coverage_scheduler_v1"

_FORBIDDEN_PROVIDER_FIELDS = {
    "assignment_id",
    "assignment_hash",
    "cell_id",
    "coverage_score",
    "fulfillment",
    "lineage",
    "plan_id",
    "plan_hash",
}


@dataclass(frozen=True)
class CoverageAssignment:
    assignment_id: str
    assignment_hash: str
    assignment_ordinal: int
    plan_id: str
    plan_hash: str
    cell_id: str
    dimensions: Mapping[str, object]
    catalog: Mapping[str, object]
    coverage_profile: Mapping[str, object]
    grounding_context_key: str
    grounding_unit_index: int
    grounding_unit_hash: str

    def provider_contract(self) -> dict[str, object]:
        required_tools = _required_tools_dimension(self.dimensions)
        return {
            "schema_version": COVERAGE_ASSIGNMENT_VERSION,
            "assignment_id": self.assignment_id,
            "assignment_hash": self.assignment_hash,
            "assignment_ordinal": self.assignment_ordinal,
            "cell_id": self.cell_id,
            "task_type": self.dimensions["task_type"],
            "required_tools": list(required_tools),
            "state_behavior": self.dimensions["state_behavior"],
            "grounding_pattern": self.dimensions["grounding_pattern"],
            "constraint_profile": self.dimensions["constraint_profile"],
            "difficulty": self.dimensions["difficulty"],
            "ambiguity": self.dimensions["ambiguity"],
            "recovery": self.dimensions["recovery"],
            "grounding_scope": {
                "context_key": self.grounding_context_key,
                "unit_index": self.grounding_unit_index,
                "grounding_hash": self.grounding_unit_hash,
            },
        }

    def lineage(self) -> dict[str, object]:
        return {
            "schema_version": COVERAGE_ASSIGNMENT_LINEAGE_VERSION,
            "assignment_id": self.assignment_id,
            "assignment_hash": self.assignment_hash,
            "assignment_ordinal": self.assignment_ordinal,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "cell_id": self.cell_id,
            "catalog": dict(self.catalog),
            "coverage_profile": dict(self.coverage_profile),
            "scheduler": {
                "schema_version": COVERAGE_SCHEDULER_VERSION,
                "selection_policy": "mandatory_then_largest_normalized_deficit_v1",
                "tie_break": "cell_id_ascending",
            },
            "grounding_scope": {
                "context_key": self.grounding_context_key,
                "unit_index": self.grounding_unit_index,
                "grounding_hash": self.grounding_unit_hash,
            },
        }


@dataclass(frozen=True)
class CoverageAssignmentGenerationResult:
    candidates: tuple[CandidateTask, ...]
    rejections: tuple[dict[str, object], ...]
    issued_assignment_count: int


CoverageAssignmentCandidateGenerator = Callable[
    [DomainSeed],
    CoverageAssignmentGenerationResult,
]
CoverageAssignmentCandidateGeneratorFactory = Callable[
    [DomainPipelineBundle, CoveragePlan, CoverageCatalog],
    CoverageAssignmentCandidateGenerator,
]


class CoverageAssignmentMismatch(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def build_coverage_assignment_candidate_generator_factory(
    client: object,
    *,
    role_registry: RoleRegistry | None = None,
) -> CoverageAssignmentCandidateGeneratorFactory:
    registry = role_registry or default_role_registry()

    def factory(
        bundle: DomainPipelineBundle,
        plan: CoveragePlan,
        catalog: CoverageCatalog,
    ) -> CoverageAssignmentCandidateGenerator:
        if bundle.generation_spec is None:
            raise ValueError("source_backed_remote_context_not_allowed")
        generation_spec = bundle.generation_spec

        def generate(seed: DomainSeed) -> CoverageAssignmentGenerationResult:
            return generate_initial_coverage_assignments(
                seed=seed,
                client=client,
                spec=generation_spec,
                plan=plan,
                catalog=catalog,
                role_registry=registry,
            )

        return generate

    return factory


def issue_initial_coverage_assignments(
    *,
    plan: CoveragePlan,
    catalog: CoverageCatalog,
    spec: DomainGenerationSpec,
) -> tuple[CoverageAssignment, ...]:
    validate_domain_generation_spec(spec)
    if plan.domain_id != catalog.domain_id or plan.domain_id != spec.domain_id:
        raise ValueError("coverage assignment domains do not match")
    cells = {cell.cell_id: cell for cell in catalog.cells}
    targets: dict[str, dict[str, int]] = {}
    for item in plan.target_distribution:
        cell_id = str(item["cell_id"])
        targets[cell_id] = {
            "mandatory_floor": _required_int(
                item["mandatory_floor"],
                "mandatory_floor",
            ),
            "target_count": _required_int(
                item["target_count"],
                "target_count",
            ),
        }
    assigned = {cell_id: 0 for cell_id in targets}
    grounding_key, grounding_units = _single_grounding_collection(spec)
    assignments: list[CoverageAssignment] = []
    while len(assignments) < plan.target_accepted_sample_count:
        cell_id = _select_next_cell(targets, assigned)
        cell = cells[cell_id]
        cell_ordinal = assigned[cell_id]
        grounding_index = cell_ordinal % len(grounding_units)
        grounding_hash = canonical_coverage_hash(grounding_units[grounding_index])
        assignment_payload = {
            "schema_version": COVERAGE_ASSIGNMENT_VERSION,
            "assignment_ordinal": len(assignments),
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "cell_id": cell_id,
            "dimensions": _canonical_dimensions(cell.dimensions),
            "grounding_scope": {
                "context_key": grounding_key,
                "unit_index": grounding_index,
                "grounding_hash": grounding_hash,
            },
        }
        assignment_hash = canonical_coverage_hash(assignment_payload)
        assignments.append(
            CoverageAssignment(
                assignment_id=(
                    "coverage_assignment_"
                    + assignment_hash.removeprefix("sha256:")[:16]
                ),
                assignment_hash=assignment_hash,
                assignment_ordinal=len(assignments),
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                cell_id=cell_id,
                dimensions=_canonical_dimensions(cell.dimensions),
                catalog=dict(plan.catalog),
                coverage_profile=dict(plan.coverage_profile),
                grounding_context_key=grounding_key,
                grounding_unit_index=grounding_index,
                grounding_unit_hash=grounding_hash,
            )
        )
        assigned[cell_id] += 1
    return tuple(assignments)


def generate_initial_coverage_assignments(
    *,
    seed: DomainSeed,
    client: object,
    spec: DomainGenerationSpec,
    plan: CoveragePlan,
    catalog: CoverageCatalog,
    role_registry: RoleRegistry | None = None,
) -> CoverageAssignmentGenerationResult:
    registry = role_registry or default_role_registry()
    assignments = issue_initial_coverage_assignments(
        plan=plan,
        catalog=catalog,
        spec=spec,
    )
    candidates: list[CandidateTask] = []
    rejections: list[dict[str, object]] = []
    for assignment in assignments:
        raw_record: Mapping[str, object] | None = None
        assignment_spec = _assignment_generation_spec(spec, assignment)
        batch_context = build_generation_batch_context(
            assignment_spec,
            batch_index=assignment.assignment_ordinal + 1,
        )
        prompt = build_coverage_assignment_prompt(
            assignment_spec,
            assignment=assignment,
            batch_context=batch_context,
        )
        try:
            result = registry.invoke_json(
                TASK_GENERATION_ROLE,
                client,
                prompt,
            )
            raw_record = _single_provider_record(result.content)
            generation_lineage = {
                **result.lineage,
                "coverage_assignment": assignment.lineage(),
            }
            contract = task_contract_from_provider_record(
                raw_record,
                seed=seed,
                spec=spec,
                candidate_id_prefix=batch_context.candidate_id_prefix,
                generation_lineage=generation_lineage,
            )
            _validate_assignment_membership(
                raw_record=raw_record,
                contract=contract,
                assignment=assignment,
                assignment_spec=assignment_spec,
                seed=seed,
                batch_context=batch_context,
                generation_lineage=generation_lineage,
            )
            contract = _with_locally_derived_difficulty(
                contract,
                assignment,
            )
            candidates.append(candidate_from_task_contract(contract))
        except CoverageAssignmentMismatch as exc:
            rejections.append(
                _assignment_mismatch_rejection(
                    assignment=assignment,
                    raw_record=raw_record,
                    reason=exc.reason,
                )
            )
        except DomainGenerationValidationError as exc:
            rejections.append(
                _assignment_generation_rejection(
                    assignment=assignment,
                    reason=exc.reason,
                    detail=exc.detail,
                )
            )
        except LLMProviderError as exc:
            rejection = assemble_generation_stage_rejection(error=exc)
            raw_details = rejection.get("details")
            details = (
                dict(raw_details)
                if isinstance(raw_details, Mapping)
                else {}
            )
            details["coverage_assignment"] = assignment.lineage()
            rejection["details"] = details
            rejections.append(rejection)
    return CoverageAssignmentGenerationResult(
        candidates=tuple(candidates),
        rejections=tuple(rejections),
        issued_assignment_count=len(assignments),
    )


def build_coverage_assignment_prompt(
    spec: DomainGenerationSpec,
    *,
    assignment: CoverageAssignment,
    batch_context: DomainGenerationBatchContext,
) -> str:
    payload = json.loads(
        build_domain_generation_prompt(
            spec,
            requested_candidate_count=1,
            batch_context=batch_context,
        )
    )
    payload["instructions"] = (
        str(payload["instructions"])
        + " Satisfy exactly the supplied coverage_assignment. Do not return any "
        "assignment, plan, cell, fulfillment, lineage, or coverage-score field."
    )
    payload["coverage_assignment"] = assignment.provider_contract()
    output_contract = cast(dict[str, object], payload["output_contract"])
    forbidden_fields = cast(list[str], output_contract["forbidden_fields"])
    forbidden = set(forbidden_fields)
    output_contract["forbidden_fields"] = sorted(
        forbidden | _FORBIDDEN_PROVIDER_FIELDS
    )
    return canonical_coverage_json(payload)


def _assignment_generation_spec(
    spec: DomainGenerationSpec,
    assignment: CoverageAssignment,
) -> DomainGenerationSpec:
    task_type = str(assignment.dimensions["task_type"])
    task_types = tuple(
        item for item in spec.task_types if item.task_type == task_type
    )
    required_tools = _required_tools_dimension(assignment.dimensions)
    tools = tuple(
        tool for tool in spec.tools if tool.get("name") in required_tools
    )
    grounding_key, grounding_units = _single_grounding_collection(spec)
    return replace(
        spec,
        task_types=task_types,
        tools=tools,
        grounding_context={
            grounding_key: [
                grounding_units[assignment.grounding_unit_index]
            ]
        },
        max_candidates_per_call=1,
        grounding_window_size=None,
    )


def _validate_assignment_membership(
    *,
    raw_record: Mapping[str, object],
    contract: TaskContract,
    assignment: CoverageAssignment,
    assignment_spec: DomainGenerationSpec,
    seed: DomainSeed,
    batch_context: DomainGenerationBatchContext,
    generation_lineage: Mapping[str, object],
) -> None:
    if contract.intent.task_type != assignment.dimensions["task_type"]:
        raise CoverageAssignmentMismatch("task_type_mismatch")
    if contract.policy_hint.required_tools != _required_tools_dimension(
        assignment.dimensions
    ):
        raise CoverageAssignmentMismatch("required_tools_mismatch")
    tools_by_name = {
        str(tool["name"]): tool
        for tool in assignment_spec.tools
    }
    state_behavior = (
        "state_changing"
        if any(
            tools_by_name[name].get("side_effects") == "state_mutating"
            for name in contract.policy_hint.required_tools
        )
        else "read_only"
    )
    if state_behavior != assignment.dimensions["state_behavior"]:
        raise CoverageAssignmentMismatch("state_behavior_mismatch")
    _, grounding_units = _single_grounding_collection(assignment_spec)
    grounding_unit = grounding_units[0]
    assigned_primary_arguments = (
        grounding_unit.get("primary_arguments")
        if isinstance(grounding_unit, Mapping)
        else None
    )
    if (
        not isinstance(assigned_primary_arguments, Mapping)
        or canonical_coverage_hash(contract.policy_hint.primary_arguments)
        != canonical_coverage_hash(assigned_primary_arguments)
    ):
        raise CoverageAssignmentMismatch("grounding_scope_mismatch")
    assigned_observation = (
        grounding_unit.get("observation")
        if isinstance(grounding_unit, Mapping)
        else None
    )
    if not isinstance(assigned_observation, Mapping):
        raise CoverageAssignmentMismatch("grounding_scope_mismatch")
    binding_values = {
        **assigned_observation,
        **assigned_primary_arguments,
    }
    for state_check in contract.expected_state:
        for field_name, assigned_value in binding_values.items():
            if (
                field_name in state_check.expected
                and canonical_coverage_hash(state_check.expected[field_name])
                != canonical_coverage_hash(assigned_value)
            ):
                raise CoverageAssignmentMismatch("grounding_scope_mismatch")
    try:
        task_contract_from_provider_record(
            raw_record,
            seed=seed,
            spec=assignment_spec,
            candidate_id_prefix=batch_context.candidate_id_prefix,
            generation_lineage=generation_lineage,
        )
    except DomainGenerationValidationError as exc:
        raise CoverageAssignmentMismatch("grounding_scope_mismatch") from exc


def _with_locally_derived_difficulty(
    contract: TaskContract,
    assignment: CoverageAssignment,
) -> TaskContract:
    required_tools = _required_tools_dimension(assignment.dimensions)
    state_behavior = assignment.dimensions["state_behavior"]
    recovery = assignment.dimensions["recovery"]
    difficulty = {
        "level": str(assignment.dimensions["difficulty"]),
        "tool_count": len(required_tools),
        "constraint_count": 1,
        "state_changes": int(state_behavior == "state_changing"),
        "ambiguity": str(assignment.dimensions["ambiguity"]),
        "recovery_paths": int(recovery != "none"),
    }
    return replace(
        contract,
        intent=replace(contract.intent, difficulty=difficulty),
    )


def _single_provider_record(content: object) -> Mapping[str, object]:
    if not isinstance(content, Mapping) or set(content) != {"task_contracts"}:
        raise DomainGenerationValidationError("response_shape_mismatch")
    records = content.get("task_contracts")
    if not isinstance(records, list) or len(records) != 1:
        raise DomainGenerationValidationError("batch_count_mismatch")
    record = records[0]
    if not isinstance(record, Mapping):
        raise DomainGenerationValidationError("provider_record_keys_mismatch")
    return record


def _assignment_mismatch_rejection(
    *,
    assignment: CoverageAssignment,
    raw_record: object,
    reason: str,
) -> dict[str, object]:
    candidate_id = (
        str(raw_record.get("candidate_id"))
        if isinstance(raw_record, Mapping)
        and isinstance(raw_record.get("candidate_id"), str)
        else assignment.assignment_id
    )
    return {
        "candidate_id": candidate_id,
        "cause": "coverage_assignment_mismatch",
        "task": {
            "candidate_id": candidate_id,
            "instruction": "Rejected before candidate processing.",
            "constraints": {},
            "difficulty": {},
        },
        "details": {
            "message": "Provider task contract did not satisfy its coverage assignment.",
            "retry_eligible": True,
            "mismatch_reason": reason,
            "coverage_assignment": assignment.lineage(),
        },
    }


def _assignment_generation_rejection(
    *,
    assignment: CoverageAssignment,
    reason: str,
    detail: str | None,
) -> dict[str, object]:
    error = LLMProviderError(
        cause="llm_response_schema_error",
        error_class="DomainGenerationValidationError",
        retryable=False,
        retry_count=0,
        schema_reason=reason,
        schema_detail=detail,
    )
    rejection = assemble_generation_stage_rejection(error=error)
    details = cast(dict[str, object], rejection["details"])
    details["coverage_assignment"] = assignment.lineage()
    return rejection


def _select_next_cell(
    targets: Mapping[str, Mapping[str, int]],
    assigned: Mapping[str, int],
) -> str:
    available = [
        cell_id
        for cell_id in sorted(targets)
        if assigned[cell_id] < targets[cell_id]["target_count"]
    ]
    if not available:
        raise ValueError("coverage plan has no remaining assignment deficit")
    mandatory = [
        cell_id
        for cell_id in available
        if assigned[cell_id] < targets[cell_id]["mandatory_floor"]
    ]
    if mandatory:
        return min(
            mandatory,
            key=lambda cell_id: (
                -(
                    targets[cell_id]["mandatory_floor"]
                    - assigned[cell_id]
                ),
                cell_id,
            ),
        )
    return min(
        available,
        key=lambda cell_id: (
            -(
                (
                    targets[cell_id]["target_count"]
                    - assigned[cell_id]
                )
                / targets[cell_id]["target_count"]
            ),
            cell_id,
        ),
    )


def _single_grounding_collection(
    spec: DomainGenerationSpec,
) -> tuple[str, list[object]]:
    if len(spec.grounding_context) != 1:
        raise ValueError("coverage assignment generation requires one grounding collection")
    key = next(iter(spec.grounding_context))
    units = spec.grounding_context[key]
    if not isinstance(units, list) or not units:
        raise ValueError("coverage assignment grounding collection must not be empty")
    return key, units


def _canonical_dimensions(
    dimensions: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: (
            tuple(value)
            if key == "required_tools" and isinstance(value, (list, tuple))
            else value
        )
        for key, value in sorted(dimensions.items())
    }


def _required_tools_dimension(
    dimensions: Mapping[str, object],
) -> tuple[str, ...]:
    value = dimensions.get("required_tools")
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item
        for item in value
    ):
        raise ValueError("coverage assignment required_tools dimension is invalid")
    return tuple(value)


def _required_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"coverage assignment {field_name} must be an integer")
    return value
