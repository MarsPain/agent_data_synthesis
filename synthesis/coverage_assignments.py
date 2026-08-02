from __future__ import annotations

import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Callable, Mapping, cast

from synthesis.candidate_processing import ProvisionalCandidateOutcome
from synthesis.concurrency import validate_concurrency
from synthesis.coverage import (
    CoverageCatalog,
    CoverageCell,
    CoveragePlan,
    allocate_coverage_grounding_indices,
    canonical_coverage_hash,
    canonical_coverage_json,
    validate_coverage_catalog_reachability,
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
COVERAGE_RECONCILIATION_VERSION = "coverage_reconciliation_v1"

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
    grounding_unit_id: str | None
    difficulty_semantics: Mapping[str, object]
    branch_plan: Mapping[str, object] | None

    def durable_record(self) -> dict[str, object]:
        """Return the locally issued assignment without grounding payloads."""

        return {
            "schema_version": COVERAGE_ASSIGNMENT_VERSION,
            "assignment_id": self.assignment_id,
            "assignment_hash": self.assignment_hash,
            "assignment_ordinal": self.assignment_ordinal,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "cell_id": self.cell_id,
            "dimensions": dict(self.dimensions),
            "catalog": dict(self.catalog),
            "coverage_profile": dict(self.coverage_profile),
            "grounding_context_key": self.grounding_context_key,
            "grounding_unit_index": self.grounding_unit_index,
            "grounding_unit_hash": self.grounding_unit_hash,
            "grounding_unit_id": self.grounding_unit_id,
            "difficulty_semantics": dict(self.difficulty_semantics),
            "branch_plan": (
                dict(self.branch_plan)
                if self.branch_plan is not None
                else None
            ),
        }

    @classmethod
    def from_durable_record(
        cls,
        record: Mapping[str, object],
    ) -> "CoverageAssignment":
        expected_keys = {
            "schema_version",
            "assignment_id",
            "assignment_hash",
            "assignment_ordinal",
            "plan_id",
            "plan_hash",
            "cell_id",
            "dimensions",
            "catalog",
            "coverage_profile",
            "grounding_context_key",
            "grounding_unit_index",
            "grounding_unit_hash",
            "grounding_unit_id",
            "difficulty_semantics",
            "branch_plan",
        }
        if set(record) != expected_keys:
            raise ValueError("coverage assignment durable record keys mismatch")
        if record["schema_version"] != COVERAGE_ASSIGNMENT_VERSION:
            raise ValueError("coverage assignment durable schema is unsupported")
        assignment_ordinal = record["assignment_ordinal"]
        grounding_unit_index = record["grounding_unit_index"]
        if (
            not isinstance(assignment_ordinal, int)
            or isinstance(assignment_ordinal, bool)
            or assignment_ordinal < 0
            or not isinstance(grounding_unit_index, int)
            or isinstance(grounding_unit_index, bool)
            or grounding_unit_index < 0
        ):
            raise ValueError("coverage assignment ordinal or grounding index is invalid")

        def mapping(field_name: str) -> Mapping[str, object]:
            value = record[field_name]
            if not isinstance(value, Mapping):
                raise ValueError(
                    f"coverage assignment {field_name} must be an object"
                )
            return value

        for field_name in (
            "assignment_id",
            "assignment_hash",
            "plan_id",
            "plan_hash",
            "cell_id",
            "grounding_context_key",
            "grounding_unit_hash",
        ):
            if not isinstance(record[field_name], str) or not record[field_name]:
                raise ValueError(
                    f"coverage assignment {field_name} must be non-empty"
                )
        dimensions = _canonical_dimensions(mapping("dimensions"))
        catalog = dict(mapping("catalog"))
        coverage_profile = dict(mapping("coverage_profile"))
        difficulty_semantics = dict(mapping("difficulty_semantics"))
        branch_plan = record["branch_plan"]
        if branch_plan is not None and not isinstance(branch_plan, Mapping):
            raise ValueError("coverage assignment branch plan must be an object or null")
        grounding_unit_id = record["grounding_unit_id"]
        if grounding_unit_id is not None and not isinstance(grounding_unit_id, str):
            raise ValueError("coverage assignment grounding unit id is invalid")
        assignment = cls(
            assignment_id=str(record["assignment_id"]),
            assignment_hash=str(record["assignment_hash"]),
            assignment_ordinal=assignment_ordinal,
            plan_id=str(record["plan_id"]),
            plan_hash=str(record["plan_hash"]),
            cell_id=str(record["cell_id"]),
            dimensions=dimensions,
            catalog=catalog,
            coverage_profile=coverage_profile,
            grounding_context_key=str(record["grounding_context_key"]),
            grounding_unit_index=grounding_unit_index,
            grounding_unit_hash=str(record["grounding_unit_hash"]),
            grounding_unit_id=grounding_unit_id,
            difficulty_semantics=difficulty_semantics,
            branch_plan=dict(branch_plan) if isinstance(branch_plan, Mapping) else None,
        )
        if assignment.assignment_id != (
            "coverage_assignment_"
            + assignment.assignment_hash.removeprefix("sha256:")[:16]
        ):
            raise ValueError("coverage assignment id is not locally derived")
        return assignment

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
        grounding_scope: dict[str, object] = {
            "context_key": self.grounding_context_key,
            "unit_index": self.grounding_unit_index,
            "grounding_hash": self.grounding_unit_hash,
        }
        if self.grounding_unit_id is not None:
            grounding_scope["unit_id"] = self.grounding_unit_id
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
            "grounding_scope": grounding_scope,
        }


@dataclass(frozen=True)
class CoverageAssignmentGenerationResult:
    candidates: tuple[CandidateTask, ...]
    rejections: tuple[dict[str, object], ...]
    issued_assignment_count: int
    assignments: tuple[CoverageAssignment, ...]
    candidate_assignment_ids: Mapping[str, str]
    rejected_assignment_ids: tuple[str, ...]


@dataclass(frozen=True)
class _CoverageAssignmentGenerationOutcome:
    assignment: CoverageAssignment
    candidate: CandidateTask | None
    rejection: dict[str, object] | None
    rejected: bool


@dataclass(frozen=True)
class CoverageAssignmentRecovery:
    """Durable coverage state supplied to a resumed pipeline."""

    assignment: CoverageAssignment
    wave: int
    candidate: CandidateTask | None
    generation_rejection: Mapping[str, object] | None
    outcome: ProvisionalCandidateOutcome | None


CoverageAssignmentWaveCallback = Callable[
    [tuple[CoverageAssignment, ...], int],
    None,
]
CoverageAssignmentAttemptObserverFactory = Callable[[CoverageAssignment], object]
CoverageGenerationRejectionCallback = Callable[
    [CoverageAssignment, Mapping[str, object]],
    None,
]


CoverageAssignmentSchedulerFactory = Callable[
    [DomainPipelineBundle, CoveragePlan, CoverageCatalog],
    "CoverageAssignmentScheduler",
]


class CoverageAssignmentMismatch(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _CoverageCellState:
    cell_id: str
    planned: int
    mandatory_floor: int
    in_flight: int = 0
    accepted: int = 0
    rejected: int = 0

    @property
    def remaining(self) -> int:
        return max(self.planned - self.accepted, 0)

    def canonical(self) -> dict[str, object]:
        if self.remaining == 0:
            deficit_reason = None
        elif self.accepted < self.mandatory_floor:
            deficit_reason = "mandatory_deficit"
        else:
            deficit_reason = "target_deficit"
        return {
            "cell_id": self.cell_id,
            "planned": self.planned,
            "in_flight": self.in_flight,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "remaining": self.remaining,
            "deficit_reason": deficit_reason,
        }


@dataclass
class _CoverageWaveState:
    wave: int
    issued: int
    in_flight_after_generation: int
    generation_rejected: int
    accepted: int = 0
    rejected: int = 0


@dataclass(frozen=True)
class _CoverageDeficit:
    cell_id: str
    planned: int
    mandatory_floor: int
    reserved: int


class CoverageAssignmentScheduler:
    def __init__(
        self,
        *,
        client: object,
        spec: DomainGenerationSpec,
        plan: CoveragePlan,
        catalog: CoverageCatalog,
        role_registry: RoleRegistry,
        execute_tool: Callable[
            [str, dict[str, object]],
            dict[str, object],
        ],
        assignment_wave_callback: CoverageAssignmentWaveCallback | None = None,
        attempt_observer_factory: (
            CoverageAssignmentAttemptObserverFactory | None
        ) = None,
        generation_rejection_callback: (
            CoverageGenerationRejectionCallback | None
        ) = None,
        max_concurrency: int = 1,
    ) -> None:
        validate_domain_generation_spec(spec)
        max_concurrency = validate_concurrency(max_concurrency)
        validate_coverage_catalog_reachability(
            catalog,
            spec,
            execute_tool=execute_tool,
        )
        if plan.domain_id != catalog.domain_id or plan.domain_id != spec.domain_id:
            raise ValueError("coverage assignment domains do not match")
        self._client = client
        self._spec = spec
        self._plan = plan
        self._catalog = catalog
        self._role_registry = role_registry
        self._assignment_wave_callback = assignment_wave_callback
        self._attempt_observer_factory = attempt_observer_factory
        self._generation_rejection_callback = generation_rejection_callback
        self._max_concurrency = max_concurrency
        self._cells = {cell.cell_id: cell for cell in catalog.cells}
        self._cell_states = {
            str(item["cell_id"]): _CoverageCellState(
                cell_id=str(item["cell_id"]),
                planned=_required_int(item["target_count"], "target_count"),
                mandatory_floor=_required_int(
                    item["mandatory_floor"],
                    "mandatory_floor",
                ),
            )
            for item in plan.target_distribution
        }
        reuse_limit = _plan_grounding_reuse_limit(plan)
        grounding_targets = allocate_coverage_grounding_indices(
            {
                cell_id: state.planned
                for cell_id, state in self._cell_states.items()
            },
            cells=self._cells,
            reuse_limit=reuse_limit,
        )
        if grounding_targets is None:
            raise ValueError("coverage plan exceeds usable grounding capacity")
        self._grounding_targets = grounding_targets
        self._accepted_grounding: Counter[tuple[str, int]] = Counter()
        self._inflight_grounding: Counter[tuple[str, int]] = Counter()
        selected_features = set(plan.selected_features)
        for cell_id in self._cell_states:
            if cell_id not in self._cells:
                raise ValueError("coverage plan references an unknown catalog cell")
            unavailable_features = (
                set(self._cells[cell_id].required_features) - selected_features
            )
            if unavailable_features:
                raise ValueError(
                    "coverage plan references a cell with unavailable features"
                )
        self._issued_count = 0
        self._wave_states: list[_CoverageWaveState] = []
        self._wave_results: dict[int, CoverageAssignmentGenerationResult] = {}
        self._candidate_assignments: dict[str, CoverageAssignment] = {}
        self._generated_candidates: dict[str, CandidateTask] = {}
        self._recovered_waves: dict[int, tuple[CoverageAssignmentRecovery, ...]] = {}
        self._reconciled_assignment_ids: set[str] = set()

    @property
    def can_schedule(self) -> bool:
        return (
            self._issued_count < self._plan.attempt_ceiling
            and any(state.remaining > 0 for state in self._cell_states.values())
            and not any(
                state.in_flight > 0 for state in self._cell_states.values()
            )
        )

    @property
    def issued_count(self) -> int:
        return self._issued_count

    def generate_wave(
        self,
        seed: DomainSeed,
    ) -> CoverageAssignmentGenerationResult:
        if not self.can_schedule:
            raise ValueError("coverage scheduler has no schedulable deficit")
        wave_number = len(self._wave_states) + 1
        wave_limit = (
            self._plan.target_accepted_sample_count
            if wave_number == 1
            else sum(state.remaining for state in self._cell_states.values())
        )
        assignments: list[CoverageAssignment] = []
        while (
            len(assignments) < wave_limit
            and self._issued_count < self._plan.attempt_ceiling
        ):
            cell_id = _select_next_deficit(
                tuple(
                    _CoverageDeficit(
                        cell_id=state.cell_id,
                        planned=state.planned,
                        mandatory_floor=state.mandatory_floor,
                        reserved=state.accepted + state.in_flight,
                    )
                    for state in self._cell_states.values()
                )
            )
            if cell_id is None:
                break
            state = self._cell_states[cell_id]
            grounding_index = self._next_grounding_index(cell_id)
            assignment = _build_coverage_assignment(
                plan=self._plan,
                catalog=self._catalog,
                cell=self._cells[cell_id],
                assignment_ordinal=self._issued_count,
                grounding_index=grounding_index,
                spec=self._spec,
            )
            assignments.append(assignment)
            state.in_flight += 1
            self._inflight_grounding[(cell_id, grounding_index)] += 1
            self._issued_count += 1
        if self._assignment_wave_callback is not None:
            self._assignment_wave_callback(tuple(assignments), wave_number)
        generated = _generate_coverage_assignments(
            seed=seed,
            client=self._client,
            spec=self._spec,
            assignments=tuple(assignments),
            role_registry=self._role_registry,
            attempt_observer_factory=self._attempt_observer_factory,
            max_concurrency=self._max_concurrency,
        )
        rejected_assignment_ids = set(generated.rejected_assignment_ids)
        assignments_by_id = {
            assignment.assignment_id: assignment
            for assignment in generated.assignments
        }
        candidates_by_id = {
            candidate.candidate_id: candidate
            for candidate in generated.candidates
        }
        for candidate_id, assignment_id in generated.candidate_assignment_ids.items():
            self._candidate_assignments[candidate_id] = assignments_by_id[
                assignment_id
            ]
            self._generated_candidates[candidate_id] = candidates_by_id[
                candidate_id
            ]
        for assignment in assignments:
            if assignment.assignment_id in rejected_assignment_ids:
                state = self._cell_states[assignment.cell_id]
                state.in_flight -= 1
                self._release_inflight_grounding(assignment)
                state.rejected += 1
                if self._generation_rejection_callback is not None:
                    rejection = next(
                        rejection
                        for rejection in generated.rejections
                        if _rejection_assignment_id(rejection)
                        == assignment.assignment_id
                    )
                    self._generation_rejection_callback(assignment, rejection)
        wave_state = _CoverageWaveState(
            wave=wave_number,
            issued=len(assignments),
            in_flight_after_generation=sum(
                state.in_flight for state in self._cell_states.values()
            ),
            generation_rejected=len(generated.rejections),
        )
        self._wave_states.append(wave_state)
        self._wave_results[wave_number] = generated
        return generated

    def restore_assignments(
        self,
        recoveries: tuple[CoverageAssignmentRecovery, ...],
    ) -> None:
        """Replay durable assignment intent before any new assignment is issued."""

        if not recoveries:
            return
        ordered = tuple(
            sorted(
                recoveries,
                key=lambda item: (item.wave, item.assignment.assignment_ordinal),
            )
        )
        if ordered != recoveries:
            raise ValueError("coverage recovery assignments must be in stable order")
        grouped: dict[int, list[CoverageAssignmentRecovery]] = {}
        for recovery in recoveries:
            grouped.setdefault(recovery.wave, []).append(recovery)
        expected_wave = 1
        for wave, wave_recoveries in grouped.items():
            if wave != expected_wave:
                raise ValueError("coverage recovery waves are not contiguous")
            expected_wave += 1
            for recovery in wave_recoveries:
                assignment = recovery.assignment
                if assignment.assignment_ordinal != self._issued_count:
                    raise ValueError("coverage recovery assignment ordinal is not contiguous")
                cell_id = _select_next_deficit(
                    tuple(
                        _CoverageDeficit(
                            cell_id=state.cell_id,
                            planned=state.planned,
                            mandatory_floor=state.mandatory_floor,
                            reserved=state.accepted + state.in_flight,
                        )
                        for state in self._cell_states.values()
                    )
                )
                if cell_id is None:
                    raise ValueError("coverage recovery contains an unschedulable assignment")
                state = self._cell_states[cell_id]
                expected = _build_coverage_assignment(
                    plan=self._plan,
                    catalog=self._catalog,
                    cell=self._cells[cell_id],
                    assignment_ordinal=self._issued_count,
                    grounding_index=self._next_grounding_index(cell_id),
                    spec=self._spec,
                )
                if assignment != expected:
                    raise ValueError("durable coverage assignment does not match the local plan")
                state.in_flight += 1
                self._inflight_grounding[(cell_id, assignment.grounding_unit_index)] += 1
                self._issued_count += 1
                if recovery.candidate is not None:
                    self._validate_recovered_candidate(
                        assignment,
                        recovery.candidate,
                    )
                    self._candidate_assignments[recovery.candidate.candidate_id] = assignment
                    self._generated_candidates[recovery.candidate.candidate_id] = recovery.candidate
            for recovery in wave_recoveries:
                assignment = recovery.assignment
                if recovery.generation_rejection is not None:
                    if recovery.outcome is None:
                        raise ValueError(
                            "coverage generation rejection has no durable outcome"
                        )
                    self._release_inflight_grounding(assignment)
                    state = self._cell_states[assignment.cell_id]
                    state.in_flight -= 1
                    state.rejected += 1
                    continue
                if recovery.outcome is None:
                    continue
                candidate = recovery.candidate
                if candidate is None:
                    raise ValueError(
                        "coverage terminal outcome has no durable candidate"
                    )
                if (
                    recovery.outcome.candidate_id != candidate.candidate_id
                    or recovery.outcome.sequence_index != assignment.assignment_ordinal
                ):
                    raise ValueError(
                        "coverage terminal outcome does not match its assignment"
                    )
                self._release_inflight_grounding(assignment)
                state = self._cell_states[assignment.cell_id]
                state.in_flight -= 1
                if recovery.outcome.sample is not None:
                    state.accepted += 1
                    self._accepted_grounding[
                        (assignment.cell_id, assignment.grounding_unit_index)
                    ] += 1
                else:
                    state.rejected += 1
                self._reconciled_assignment_ids.add(assignment.assignment_id)
            self._recovered_waves[wave] = tuple(wave_recoveries)
            self._wave_states.append(
                _CoverageWaveState(
                    wave=wave,
                    issued=len(wave_recoveries),
                    in_flight_after_generation=sum(
                        recovery.candidate is not None
                        for recovery in wave_recoveries
                    ),
                    generation_rejected=sum(
                        recovery.generation_rejection is not None
                        for recovery in wave_recoveries
                    ),
                )
            )

    def _validate_recovered_candidate(
        self,
        assignment: CoverageAssignment,
        candidate: CandidateTask,
    ) -> None:
        try:
            contract = candidate.contract()
            assignment_spec = _assignment_generation_spec(
                self._spec,
                assignment,
            )
            _validate_contract_assignment_membership(
                contract=contract,
                assignment=assignment,
                assignment_spec=assignment_spec,
            )
            if canonical_coverage_hash(candidate.difficulty) != (
                canonical_coverage_hash(_assignment_difficulty(assignment))
            ):
                raise CoverageAssignmentMismatch("difficulty_mismatch")
            lineage = candidate.generation_lineage
            lineage_assignment = (
                lineage.get("coverage_assignment")
                if isinstance(lineage, Mapping)
                else None
            )
            if (
                not isinstance(lineage_assignment, Mapping)
                or lineage_assignment.get("assignment_id")
                != assignment.assignment_id
            ):
                raise CoverageAssignmentMismatch("assignment_lineage_mismatch")
        except (CoverageAssignmentMismatch, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "durable coverage candidate does not satisfy its assignment"
            ) from exc

    def recover_wave(
        self,
        seed: DomainSeed,
        wave: int,
    ) -> CoverageAssignmentGenerationResult:
        """Regenerate only an interrupted assignment, never issue a new one."""

        recoveries = self._recovered_waves.get(wave)
        if recoveries is None:
            raise ValueError("coverage recovery wave is unknown")
        unresolved = tuple(
            recovery.assignment
            for recovery in recoveries
            if recovery.candidate is None
            and recovery.generation_rejection is None
        )
        if unresolved:
            generated = _generate_coverage_assignments(
                seed=seed,
                client=self._client,
                spec=self._spec,
                assignments=unresolved,
                role_registry=self._role_registry,
                attempt_observer_factory=self._attempt_observer_factory,
                max_concurrency=self._max_concurrency,
            )
            for candidate_id, assignment_id in generated.candidate_assignment_ids.items():
                assignment = next(
                    item for item in unresolved if item.assignment_id == assignment_id
                )
                self._candidate_assignments[candidate_id] = assignment
                self._generated_candidates[candidate_id] = next(
                    candidate
                    for candidate in generated.candidates
                    if candidate.candidate_id == candidate_id
                )
            updated_recoveries: list[CoverageAssignmentRecovery] = []
            generated_by_assignment: dict[str, str] = {
                assignment_id: candidate_id
                for candidate_id, assignment_id in generated.candidate_assignment_ids.items()
            }
            rejection_by_assignment: dict[str, dict[str, object]] = {
                assignment_id: rejection
                for rejection in generated.rejections
                for assignment_id in [_rejection_assignment_id(rejection)]
                if assignment_id is not None
            }
            for recovery in recoveries:
                assignment = recovery.assignment
                generated_candidate_id = generated_by_assignment.get(
                    assignment.assignment_id
                )
                if generated_candidate_id is not None:
                    candidate = next(
                        candidate
                        for candidate in generated.candidates
                        if candidate.candidate_id == generated_candidate_id
                    )
                    updated_recoveries.append(
                        replace(recovery, candidate=candidate)
                    )
                elif assignment.assignment_id in rejection_by_assignment:
                    updated_recoveries.append(
                        replace(
                            recovery,
                            generation_rejection=rejection_by_assignment[
                                assignment.assignment_id
                            ],
                        )
                    )
                else:
                    updated_recoveries.append(recovery)
            recoveries = tuple(updated_recoveries)
            self._recovered_waves[wave] = recoveries
            for assignment in unresolved:
                if assignment.assignment_id in set(generated.rejected_assignment_ids):
                    state = self._cell_states[assignment.cell_id]
                    self._release_inflight_grounding(assignment)
                    state.in_flight -= 1
                    state.rejected += 1
                    if self._generation_rejection_callback is not None:
                        rejection = next(
                            rejection
                            for rejection in generated.rejections
                            if _rejection_assignment_id(rejection)
                            == assignment.assignment_id
                        )
                        self._generation_rejection_callback(assignment, rejection)
        combined = self.recovered_wave_result(wave)
        wave_state = self._wave_states[wave - 1]
        wave_state.in_flight_after_generation = len(combined.candidates)
        wave_state.generation_rejected = len(combined.rejections)
        self._wave_results[wave] = combined
        return combined

    def recovered_wave_result(self, wave: int) -> CoverageAssignmentGenerationResult:
        recoveries = self._recovered_waves.get(wave)
        if recoveries is None:
            raise ValueError("coverage recovery wave is unknown")
        assignments = tuple(recovery.assignment for recovery in recoveries)
        candidates: list[CandidateTask] = []
        candidate_assignment_ids: dict[str, str] = {}
        rejections: list[dict[str, object]] = []
        rejected_assignment_ids: list[str] = []
        for recovery in recoveries:
            candidate = recovery.candidate
            if candidate is not None:
                current = self._generated_candidates.get(
                    candidate.candidate_id,
                    candidate,
                )
                candidates.append(current)
                candidate_assignment_ids[current.candidate_id] = (
                    recovery.assignment.assignment_id
                )
            if recovery.generation_rejection is not None:
                rejections.append(dict(recovery.generation_rejection))
                rejected_assignment_ids.append(recovery.assignment.assignment_id)
        return CoverageAssignmentGenerationResult(
            candidates=tuple(candidates),
            rejections=tuple(rejections),
            issued_assignment_count=len(assignments),
            assignments=assignments,
            candidate_assignment_ids=candidate_assignment_ids,
            rejected_assignment_ids=tuple(rejected_assignment_ids),
        )

    def validate_refined_candidate(
        self,
        original_candidate_id: str,
        candidate: CandidateTask,
    ) -> dict[str, object] | None:
        assignment = self._candidate_assignments[original_candidate_id]
        original_candidate = self._generated_candidates[original_candidate_id]
        try:
            contract = candidate.contract()
            assignment_spec = _assignment_generation_spec(
                self._spec,
                assignment,
            )
            _validate_contract_assignment_membership(
                contract=contract,
                assignment=assignment,
                assignment_spec=assignment_spec,
            )
            if canonical_coverage_hash(candidate.difficulty) != (
                canonical_coverage_hash(_assignment_difficulty(assignment))
            ):
                raise CoverageAssignmentMismatch("difficulty_mismatch")
            if candidate.expected_answer != original_candidate.expected_answer:
                raise CoverageAssignmentMismatch("grounding_scope_mismatch")
            if canonical_coverage_hash(candidate.constraints) != (
                canonical_coverage_hash(original_candidate.constraints)
            ):
                raise CoverageAssignmentMismatch("constraint_profile_mismatch")
            recovery = assignment.dimensions["recovery"]
            if (candidate.branch_plan is None) != (recovery == "none"):
                raise CoverageAssignmentMismatch("recovery_mismatch")
            if canonical_coverage_hash(candidate.branch_plan) != (
                canonical_coverage_hash(assignment.branch_plan)
            ):
                raise CoverageAssignmentMismatch("recovery_mismatch")
            lineage = candidate.generation_lineage
            lineage_assignment = (
                lineage.get("coverage_assignment")
                if isinstance(lineage, Mapping)
                else None
            )
            if (
                not isinstance(lineage_assignment, Mapping)
                or lineage_assignment.get("assignment_id")
                != assignment.assignment_id
            ):
                raise CoverageAssignmentMismatch("assignment_lineage_mismatch")
        except CoverageAssignmentMismatch as exc:
            return _assignment_mismatch_rejection(
                assignment=assignment,
                raw_record=candidate.export(),
                reason=exc.reason,
            )
        except (TypeError, ValueError, KeyError):
            return _assignment_mismatch_rejection(
                assignment=assignment,
                raw_record=candidate.export(),
                reason="refined_candidate_mismatch",
            )
        return None

    def reconcile_wave(
        self,
        generated: CoverageAssignmentGenerationResult,
        *,
        accepted_candidate_ids: set[str],
        rejected_candidate_ids: set[str],
    ) -> None:
        candidate_ids = set(generated.candidate_assignment_ids)
        if accepted_candidate_ids & rejected_candidate_ids:
            raise ValueError("coverage candidate cannot be accepted and rejected")
        reported_candidate_ids = accepted_candidate_ids | rejected_candidate_ids
        if not reported_candidate_ids <= candidate_ids:
            raise ValueError("coverage wave outcomes do not match generated candidates")
        assignments = {
            assignment.assignment_id: assignment
            for assignment in generated.assignments
        }
        for candidate_id, assignment_id in generated.candidate_assignment_ids.items():
            if candidate_id not in reported_candidate_ids:
                continue
            assignment = assignments[assignment_id]
            if assignment_id in self._reconciled_assignment_ids:
                continue
            state = self._cell_states[assignment.cell_id]
            if state.in_flight < 1:
                raise ValueError("coverage assignment is not in flight")
            state.in_flight -= 1
            self._release_inflight_grounding(assignment)
            if candidate_id in accepted_candidate_ids:
                state.accepted += 1
                self._accepted_grounding[
                    (assignment.cell_id, assignment.grounding_unit_index)
                ] += 1
            else:
                state.rejected += 1
            self._reconciled_assignment_ids.add(assignment_id)
        wave_number = next(
            wave
            for wave, result in self._wave_results.items()
            if result is generated
        )
        wave_state = self._wave_states[wave_number - 1]
        wave_state.accepted = len(accepted_candidate_ids)
        wave_state.rejected = (
            wave_state.generation_rejected + len(rejected_candidate_ids)
        )

    def reconciliation(self) -> dict[str, object]:
        status = (
            "complete"
            if all(state.remaining == 0 for state in self._cell_states.values())
            else "incomplete"
        )
        waves: list[dict[str, object]] = []
        for wave_state in self._wave_states:
            waves.append(
                {
                    "wave": wave_state.wave,
                    "issued": wave_state.issued,
                    "in_flight_after_generation": (
                        wave_state.in_flight_after_generation
                    ),
                    "accepted": wave_state.accepted,
                    "rejected": wave_state.rejected,
                }
            )
        return {
            "schema_version": COVERAGE_RECONCILIATION_VERSION,
            "status": status,
            "attempts": {
                "ceiling": self._plan.attempt_ceiling,
                "issued": self._issued_count,
                "remaining": self._plan.attempt_ceiling - self._issued_count,
            },
            "cells": [
                self._cell_states[cell_id].canonical()
                for cell_id in sorted(self._cell_states)
            ],
            "waves": waves,
        }

    def _next_grounding_index(self, cell_id: str) -> int:
        target_counts = Counter(self._grounding_targets[cell_id])
        for grounding_index in self._grounding_targets[cell_id]:
            key = (cell_id, grounding_index)
            if (
                self._accepted_grounding[key] + self._inflight_grounding[key]
                < target_counts[grounding_index]
            ):
                return grounding_index
        raise ValueError("coverage cell has no remaining grounding allocation")

    def _release_inflight_grounding(
        self,
        assignment: CoverageAssignment,
    ) -> None:
        key = (assignment.cell_id, assignment.grounding_unit_index)
        if self._inflight_grounding[key] < 1:
            raise ValueError("coverage grounding assignment is not in flight")
        self._inflight_grounding[key] -= 1


def build_coverage_assignment_scheduler_factory(
    client: object,
    *,
    role_registry: RoleRegistry | None = None,
    assignment_wave_callback: CoverageAssignmentWaveCallback | None = None,
    attempt_observer_factory: (
        CoverageAssignmentAttemptObserverFactory | None
    ) = None,
    generation_rejection_callback: (
        CoverageGenerationRejectionCallback | None
    ) = None,
    max_concurrency: int = 1,
) -> CoverageAssignmentSchedulerFactory:
    registry = role_registry or default_role_registry()
    max_concurrency = validate_concurrency(max_concurrency)

    def factory(
        bundle: DomainPipelineBundle,
        plan: CoveragePlan,
        catalog: CoverageCatalog,
    ) -> CoverageAssignmentScheduler:
        if bundle.generation_spec is None:
            raise ValueError("source_backed_remote_context_not_allowed")
        return CoverageAssignmentScheduler(
            client=client,
            spec=bundle.generation_spec,
            plan=plan,
            catalog=catalog,
            role_registry=registry,
            execute_tool=bundle.registry.execute,
            assignment_wave_callback=assignment_wave_callback,
            attempt_observer_factory=attempt_observer_factory,
            generation_rejection_callback=generation_rejection_callback,
            max_concurrency=max_concurrency,
        )

    return factory


def issue_initial_coverage_assignments(
    *,
    plan: CoveragePlan,
    catalog: CoverageCatalog,
    spec: DomainGenerationSpec,
) -> tuple[CoverageAssignment, ...]:
    validate_domain_generation_spec(spec)
    validate_coverage_catalog_reachability(
        catalog,
        spec,
        require_executable_recovery=False,
    )
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
    grounding_targets = allocate_coverage_grounding_indices(
        {
            cell_id: target["target_count"]
            for cell_id, target in targets.items()
        },
        cells=cells,
        reuse_limit=_plan_grounding_reuse_limit(plan),
    )
    if grounding_targets is None:
        raise ValueError("coverage plan exceeds usable grounding capacity")
    assignments: list[CoverageAssignment] = []
    while len(assignments) < plan.target_accepted_sample_count:
        selected_cell_id = _select_next_deficit(
            tuple(
                _CoverageDeficit(
                    cell_id=cell_id,
                    planned=target["target_count"],
                    mandatory_floor=target["mandatory_floor"],
                    reserved=assigned[cell_id],
                )
                for cell_id, target in targets.items()
            )
        )
        if selected_cell_id is None:
            raise ValueError("coverage plan has no remaining assignment deficit")
        cell_ordinal = assigned[selected_cell_id]
        assignments.append(
            _build_coverage_assignment(
                plan=plan,
                catalog=catalog,
                cell=cells[selected_cell_id],
                assignment_ordinal=len(assignments),
                grounding_index=grounding_targets[selected_cell_id][cell_ordinal],
                spec=spec,
            )
        )
        assigned[selected_cell_id] += 1
    return tuple(assignments)


def _build_coverage_assignment(
    *,
    plan: CoveragePlan,
    catalog: CoverageCatalog,
    cell: CoverageCell,
    assignment_ordinal: int,
    grounding_index: int,
    spec: DomainGenerationSpec,
) -> CoverageAssignment:
    grounding_key, grounding_units = _single_grounding_collection(spec)
    grounding_hash = canonical_coverage_hash(grounding_units[grounding_index])
    grounding_unit_id = (
        _grounding_unit_id(cell, grounding_index)
        if catalog.validate_grounding_identities
        else None
    )
    grounding_scope: dict[str, object] = {
        "context_key": grounding_key,
        "unit_index": grounding_index,
        "grounding_hash": grounding_hash,
    }
    if grounding_unit_id is not None:
        grounding_scope["unit_id"] = grounding_unit_id
    difficulty_semantics = next(
        semantics.canonical()
        for semantics in catalog.difficulty_semantics
        if semantics.difficulty == cell.dimensions["difficulty"]
    )
    assignment_payload = {
        "schema_version": COVERAGE_ASSIGNMENT_VERSION,
        "assignment_ordinal": assignment_ordinal,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "cell_id": cell.cell_id,
        "dimensions": _canonical_dimensions(cell.dimensions),
        "difficulty_semantics": difficulty_semantics,
        "branch_plan": (
            dict(cell.branch_plan)
            if cell.branch_plan is not None
            else None
        ),
        "grounding_scope": grounding_scope,
    }
    assignment_hash = canonical_coverage_hash(assignment_payload)
    return CoverageAssignment(
        assignment_id=(
            "coverage_assignment_"
            + assignment_hash.removeprefix("sha256:")[:16]
        ),
        assignment_hash=assignment_hash,
        assignment_ordinal=assignment_ordinal,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        cell_id=cell.cell_id,
        dimensions=_canonical_dimensions(cell.dimensions),
        catalog=dict(plan.catalog),
        coverage_profile=dict(plan.coverage_profile),
        grounding_context_key=grounding_key,
        grounding_unit_index=grounding_index,
        grounding_unit_hash=grounding_hash,
        grounding_unit_id=grounding_unit_id,
        difficulty_semantics=difficulty_semantics,
        branch_plan=(
            dict(cell.branch_plan)
            if cell.branch_plan is not None
            else None
        ),
    )


def _grounding_unit_id(
    cell: CoverageCell,
    grounding_index: int,
) -> str:
    return next(
        unit_id
        for index, unit_id in zip(
            cell.grounding_unit_indices,
            cell.grounding_unit_ids,
            strict=True,
        )
        if index == grounding_index
    )


def generate_initial_coverage_assignments(
    *,
    seed: DomainSeed,
    client: object,
    spec: DomainGenerationSpec,
    plan: CoveragePlan,
    catalog: CoverageCatalog,
    role_registry: RoleRegistry | None = None,
    max_concurrency: int = 1,
) -> CoverageAssignmentGenerationResult:
    registry = role_registry or default_role_registry()
    assignments = issue_initial_coverage_assignments(
        plan=plan,
        catalog=catalog,
        spec=spec,
    )
    return _generate_coverage_assignments(
        seed=seed,
        client=client,
        spec=spec,
        assignments=assignments,
        role_registry=registry,
        max_concurrency=max_concurrency,
    )


def _generate_coverage_assignments(
    *,
    seed: DomainSeed,
    client: object,
    spec: DomainGenerationSpec,
    assignments: tuple[CoverageAssignment, ...],
    role_registry: RoleRegistry,
    attempt_observer_factory: (
        CoverageAssignmentAttemptObserverFactory | None
    ) = None,
    max_concurrency: int = 1,
) -> CoverageAssignmentGenerationResult:
    max_concurrency = validate_concurrency(max_concurrency)

    def generate_assignment(
        assignment: CoverageAssignment,
    ) -> _CoverageAssignmentGenerationOutcome:
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
        attempt_observer = (
            attempt_observer_factory(assignment)
            if attempt_observer_factory is not None
            else None
        )
        try:
            if attempt_observer is not None:
                _invoke_observer(
                    attempt_observer,
                    "before_provider_call",
                    assignment=assignment,
                    batch_context=batch_context,
                    requested_candidate_count=1,
                    prompt_hash=hashlib.sha256(
                        prompt.encode("utf-8")
                    ).hexdigest(),
                )
            result = role_registry.invoke_json(
                TASK_GENERATION_ROLE,
                client,
                prompt,
            )
            if attempt_observer is not None:
                _invoke_observer(
                    attempt_observer,
                    "provider_response_received",
                    assignment=assignment,
                    batch_context=batch_context,
                    requested_candidate_count=1,
                    lineage=result.lineage,
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
            if attempt_observer is not None:
                _invoke_observer(
                    attempt_observer,
                    "validated_contracts_checkpointed",
                    assignment=assignment,
                    batch_context=batch_context,
                    requested_candidate_count=1,
                    contracts=(contract,),
                    lineage=generation_lineage,
                )
            candidate = candidate_from_task_contract(contract)
            return _CoverageAssignmentGenerationOutcome(
                assignment=assignment,
                candidate=candidate,
                rejection=None,
                rejected=False,
            )
        except CoverageAssignmentMismatch as exc:
            return _CoverageAssignmentGenerationOutcome(
                assignment=assignment,
                candidate=None,
                rejection=_assignment_mismatch_rejection(
                    assignment=assignment,
                    raw_record=raw_record,
                    reason=exc.reason,
                ),
                rejected=True,
            )
        except DomainGenerationValidationError as exc:
            return _CoverageAssignmentGenerationOutcome(
                assignment=assignment,
                candidate=None,
                rejection=_assignment_generation_rejection(
                    assignment=assignment,
                    reason=exc.reason,
                    detail=exc.detail,
                ),
                rejected=True,
            )
        except LLMProviderError as exc:
            if attempt_observer is not None:
                _invoke_observer(
                    attempt_observer,
                    "provider_attempt_failed",
                    assignment=assignment,
                    batch_context=batch_context,
                    requested_candidate_count=1,
                    error=exc,
                )
            if getattr(exc, "ambiguous", False):
                raise
            rejection = assemble_generation_stage_rejection(error=exc)
            raw_details = rejection.get("details")
            details = (
                dict(raw_details)
                if isinstance(raw_details, Mapping)
                else {}
            )
            details["coverage_assignment"] = assignment.lineage()
            rejection["details"] = details
            return _CoverageAssignmentGenerationOutcome(
                assignment=assignment,
                candidate=None,
                rejection=rejection,
                rejected=True,
            )

    if max_concurrency == 1:
        outcomes = tuple(generate_assignment(assignment) for assignment in assignments)
    else:
        with ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="synthesis-coverage",
        ) as executor:
            outcomes = tuple(executor.map(generate_assignment, assignments))

    candidates: list[CandidateTask] = []
    rejections: list[dict[str, object]] = []
    candidate_assignment_ids: dict[str, str] = {}
    rejected_assignment_ids: list[str] = []
    for outcome in outcomes:
        if outcome.candidate is not None:
            candidates.append(outcome.candidate)
            candidate_assignment_ids[outcome.candidate.candidate_id] = (
                outcome.assignment.assignment_id
            )
        if outcome.rejected:
            rejected_assignment_ids.append(outcome.assignment.assignment_id)
        if outcome.rejection is not None:
            rejections.append(outcome.rejection)
    return CoverageAssignmentGenerationResult(
        candidates=tuple(candidates),
        rejections=tuple(rejections),
        issued_assignment_count=len(assignments),
        assignments=assignments,
        candidate_assignment_ids=candidate_assignment_ids,
        rejected_assignment_ids=tuple(rejected_assignment_ids),
    )


def _invoke_observer(
    observer: object,
    method_name: str,
    **kwargs: object,
) -> None:
    method = getattr(observer, method_name, None)
    if not callable(method):
        raise TypeError(
            f"coverage assignment attempt observer lacks {method_name}"
        )
    method(**kwargs)


def _rejection_assignment_id(rejection: Mapping[str, object]) -> str | None:
    details = rejection.get("details")
    if not isinstance(details, Mapping):
        return None
    assignment = details.get("coverage_assignment")
    if not isinstance(assignment, Mapping):
        return None
    assignment_id = assignment.get("assignment_id")
    return assignment_id if isinstance(assignment_id, str) else None


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
    _validate_contract_assignment_membership(
        contract=contract,
        assignment=assignment,
        assignment_spec=assignment_spec,
    )
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


def _validate_contract_assignment_membership(
    *,
    contract: TaskContract,
    assignment: CoverageAssignment,
    assignment_spec: DomainGenerationSpec,
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


def _with_locally_derived_difficulty(
    contract: TaskContract,
    assignment: CoverageAssignment,
) -> TaskContract:
    return replace(
        contract,
        intent=replace(
            contract.intent,
            difficulty=_assignment_difficulty(assignment),
        ),
        policy_hint=replace(
            contract.policy_hint,
            branch_plan=(
                dict(assignment.branch_plan)
                if assignment.branch_plan is not None
                else None
            ),
        ),
    )


def _assignment_difficulty(
    assignment: CoverageAssignment,
) -> dict[str, object]:
    return {
        "level": str(assignment.difficulty_semantics["difficulty"]),
        "tool_count": _required_int(
            assignment.difficulty_semantics["tool_count"],
            "difficulty tool_count",
        ),
        "constraint_count": _required_int(
            assignment.difficulty_semantics["constraint_count"],
            "difficulty constraint_count",
        ),
        "state_changes": _required_int(
            assignment.difficulty_semantics["state_changes"],
            "difficulty state_changes",
        ),
        "ambiguity": str(assignment.difficulty_semantics["ambiguity"]),
        "recovery_paths": _required_int(
            assignment.difficulty_semantics["recovery_paths"],
            "difficulty recovery_paths",
        ),
    }


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


def _select_next_deficit(
    deficits: tuple[_CoverageDeficit, ...],
) -> str | None:
    available = [
        deficit
        for deficit in deficits
        if deficit.reserved < deficit.planned
    ]
    if not available:
        return None
    mandatory = [
        deficit
        for deficit in available
        if deficit.reserved < deficit.mandatory_floor
    ]
    if mandatory:
        return min(
            mandatory,
            key=lambda deficit: (
                -(deficit.mandatory_floor - deficit.reserved),
                deficit.cell_id,
            ),
        ).cell_id
    return min(
        available,
        key=lambda deficit: (
            -(
                (deficit.planned - deficit.reserved)
                / deficit.planned
            ),
            deficit.cell_id,
        ),
    ).cell_id


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


def _plan_grounding_reuse_limit(plan: CoveragePlan) -> int:
    grounding_reuse = plan.policies.get("grounding_reuse")
    if not isinstance(grounding_reuse, Mapping):
        raise ValueError("coverage plan grounding reuse policy is missing")
    reuse_limit = grounding_reuse.get(
        "max_accepted_samples_per_grounding_unit"
    )
    reuse_value = _required_int(reuse_limit, "grounding reuse limit")
    if reuse_value < 1:
        raise ValueError("coverage plan grounding reuse limit must be positive")
    return reuse_value


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
