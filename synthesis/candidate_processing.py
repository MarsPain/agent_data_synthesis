from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

from synthesis.contracts import ContractValidationError, validate_candidate_task
from synthesis.datasets import (
    assemble_candidate_schema_rejection,
    assemble_execution_rejection,
    assemble_quality_gate_rejection,
    assemble_rejection,
    assemble_sample,
    attach_refinement_to_rejection,
)
from synthesis.execution import (
    BranchExecutionError,
    ExecutionResult,
    PolicyValidationError,
    SolutionPolicy,
    execute_candidate,
)
from synthesis.episodes import build_episode_log
from synthesis.llm import LLMConfig, LLMProviderError
from synthesis.mcp import (
    ADAPTER_VERSION,
    PROTOCOL_LABEL,
    AdapterExecutionError,
)
from synthesis.quality import (
    build_review_record,
    candidate_duplicate_signature,
    final_answer_is_logically_supported,
    retry_eligible,
    reviewable,
)
from synthesis.refinement import Refiner, RefinementAttempt, RefinementContext, repairable
from synthesis.tasks import CandidateTask, local_task_generation_lineage
from synthesis.tools import (
    CapabilityGap,
    ToolMissingError,
    ToolProposal,
    ToolRegistry,
    ToolSchemaError,
    admit_curated_tool,
    build_capability_gap,
    build_tool_proposal_record,
)
from synthesis.verification import ExactAnswerVerifier


PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
ToolProposalGenerator = Callable[[CapabilityGap], ToolProposal]


@dataclass(frozen=True)
class CandidateProcessingContext:
    dataset_version: str
    environment: Any
    registry: ToolRegistry
    adapter_shim: Any | None
    verifier: ExactAnswerVerifier
    llm_config: LLMConfig
    generate_policy: PolicyGenerator


@dataclass(frozen=True)
class CandidateProcessingOptions:
    route_reviewable_failures: bool = False
    refiner: Refiner | None = None
    tool_proposal_generator: ToolProposalGenerator | None = None


@dataclass(frozen=True)
class CandidateExecutionRequest:
    sequence_index: int
    raw_task: CandidateTask


@dataclass(frozen=True)
class ProvisionalCandidateOutcome:
    sequence_index: int = 0
    candidate_id: str = "unknown_candidate"
    sample: dict[str, object] | None = None
    rejection: dict[str, object] | None = None
    review_records: tuple[dict[str, object], ...] = ()
    tool_proposal_records: tuple[dict[str, object], ...] = ()
    duplicate_signature: tuple[str, tuple[str, ...]] | None = None
    environment_isolation: dict[str, object] = field(default_factory=dict)
    registry_mutations: tuple[dict[str, object], ...] = ()
    task_record: dict[str, object] | None = None
    episode_log: dict[str, object] | None = None

    @property
    def accepted_signature(self) -> tuple[str, tuple[str, ...]] | None:
        return self.duplicate_signature


CandidateProcessingOutcome = ProvisionalCandidateOutcome


@dataclass(frozen=True)
class CandidateMergeResult:
    samples: tuple[dict[str, object], ...]
    rejections: tuple[dict[str, object], ...]
    review_records: tuple[dict[str, object], ...]
    tool_proposal_records: tuple[dict[str, object], ...]
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]]
    episode_logs: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class _CandidateAttemptResult:
    sample: dict[str, object] | None
    rejection: dict[str, object] | None
    signature: tuple[str, tuple[str, ...]] | None
    policy: SolutionPolicy | None
    capability_gap: CapabilityGap | None = None
    episode_log: dict[str, object] | None = None


def process_candidate_through_gates(
    *,
    raw_task: CandidateTask | None = None,
    request: CandidateExecutionRequest | None = None,
    context: CandidateProcessingContext,
    accepted_signatures: set[tuple[str, tuple[str, ...]]] | None = None,
    options: CandidateProcessingOptions,
) -> ProvisionalCandidateOutcome:
    # Kept for compatibility with callers from the pre-merge-boundary API.
    _ = accepted_signatures
    if request is None:
        if raw_task is None:
            raise ValueError("raw_task or request is required")
        request = CandidateExecutionRequest(sequence_index=0, raw_task=raw_task)
    sequence_index = request.sequence_index
    raw_task = request.raw_task
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    try:
        task = validate_candidate_task(raw_task)
    except ContractValidationError as exc:
        return ProvisionalCandidateOutcome(
            sequence_index=sequence_index,
            candidate_id="unknown_candidate",
            sample=None,
            rejection=assemble_candidate_schema_rejection(error=exc),
            environment_isolation=_environment_isolation_record(context),
        )
    task = _ensure_generation_lineage(task, context.llm_config)

    attempt_result = _run_candidate_attempt(
        task=task,
        context=context,
    )
    sample_outcome = _sample_outcome_if_present(
        attempt_result,
        sequence_index=sequence_index,
        candidate_id=task.candidate_id,
        task_record=task.export(),
        environment_isolation=_environment_isolation_record(context),
        review_records=review_records,
        tool_proposal_records=tool_proposal_records,
        episode_log=attempt_result.episode_log,
    )
    if sample_outcome is not None:
        return sample_outcome

    assert attempt_result.rejection is not None
    tool_expanded = _maybe_expand_tool_and_rerun(
        attempt_result=attempt_result,
        task=task,
        context=context,
        tool_proposal_generator=options.tool_proposal_generator,
        tool_proposal_records=tool_proposal_records,
    )
    if tool_expanded is not None:
        sample_outcome = _sample_outcome_if_present(
            tool_expanded,
            sequence_index=sequence_index,
            candidate_id=task.candidate_id,
            task_record=task.export(),
            environment_isolation=_environment_isolation_record(context),
            review_records=review_records,
            tool_proposal_records=tool_proposal_records,
            episode_log=tool_expanded.episode_log,
        )
        if sample_outcome is not None:
            return sample_outcome
        assert tool_expanded.rejection is not None
        _maybe_route_review(
            review_records,
            tool_expanded.rejection,
            route_reviewable_failures=options.route_reviewable_failures,
        )
        return ProvisionalCandidateOutcome(
            sequence_index=sequence_index,
            candidate_id=task.candidate_id,
            sample=None,
            rejection=tool_expanded.rejection,
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
            environment_isolation=_environment_isolation_record(context),
            task_record=task.export(),
            episode_log=tool_expanded.episode_log,
        )

    try:
        refinement_attempt = _maybe_refine(
            refiner=options.refiner,
            task=task,
            rejection=attempt_result.rejection,
            source_policy=attempt_result.policy,
        )
    except LLMProviderError as exc:
        return ProvisionalCandidateOutcome(
            sequence_index=sequence_index,
            candidate_id=task.candidate_id,
            sample=None,
            rejection=assemble_quality_gate_rejection(
                task=task,
                cause=exc.cause,
                message="Remote critic/refinement failed before rerun.",
                details={
                    "error_class": exc.error_class,
                    "retry_count": exc.retry_count,
                    "lineage": dict(exc.lineage) if exc.lineage else {},
                    "source_failure": {
                        "cause": attempt_result.rejection.get("cause"),
                        "details": attempt_result.rejection.get("details", {}),
                    },
                },
                policy=attempt_result.policy,
            ),
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
            environment_isolation=_environment_isolation_record(context),
            task_record=task.export(),
            episode_log=attempt_result.episode_log,
        )
    if refinement_attempt is None:
        _maybe_route_review(
            review_records,
            attempt_result.rejection,
            route_reviewable_failures=options.route_reviewable_failures,
        )
        return ProvisionalCandidateOutcome(
            sequence_index=sequence_index,
            candidate_id=task.candidate_id,
            sample=None,
            rejection=attempt_result.rejection,
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
            environment_isolation=_environment_isolation_record(context),
            task_record=task.export(),
            episode_log=attempt_result.episode_log,
        )

    refined_task = refinement_attempt.revised_candidate or task
    refined_result = _run_candidate_attempt(
        task=refined_task,
        context=context,
        policy_override=refinement_attempt.revised_policy,
        refinement_attempt=refinement_attempt,
    )
    sample_outcome = _sample_outcome_if_present(
        refined_result,
        sequence_index=sequence_index,
        candidate_id=refined_task.candidate_id,
        task_record=refined_task.export(),
        environment_isolation=_environment_isolation_record(context),
        review_records=review_records,
        tool_proposal_records=tool_proposal_records,
        episode_log=refined_result.episode_log,
    )
    if sample_outcome is not None:
        return sample_outcome

    assert refined_result.rejection is not None
    rejection = attach_refinement_to_rejection(
        refined_result.rejection,
        refinement_attempt,
    )
    _maybe_route_review(
        review_records,
        rejection,
        route_reviewable_failures=options.route_reviewable_failures,
    )
    return ProvisionalCandidateOutcome(
        sequence_index=sequence_index,
        candidate_id=refined_task.candidate_id,
        sample=None,
        rejection=rejection,
        review_records=tuple(review_records),
        tool_proposal_records=tuple(tool_proposal_records),
        environment_isolation=_environment_isolation_record(context),
        task_record=refined_task.export(),
        episode_log=refined_result.episode_log,
    )


def _sample_outcome_if_present(
    attempt_result: _CandidateAttemptResult,
    *,
    sequence_index: int,
    candidate_id: str,
    task_record: dict[str, object],
    environment_isolation: dict[str, object],
    review_records: list[dict[str, object]],
    tool_proposal_records: list[dict[str, object]],
    episode_log: dict[str, object] | None,
) -> ProvisionalCandidateOutcome | None:
    if attempt_result.sample is None:
        return None
    assert attempt_result.signature is not None
    return ProvisionalCandidateOutcome(
        sequence_index=sequence_index,
        candidate_id=candidate_id,
        sample=attempt_result.sample,
        rejection=None,
        review_records=tuple(review_records),
        tool_proposal_records=tuple(tool_proposal_records),
        duplicate_signature=attempt_result.signature,
        environment_isolation=environment_isolation,
        registry_mutations=_registry_mutations_from_tool_proposals(tool_proposal_records),
        task_record=task_record,
        episode_log=episode_log,
    )


def _run_candidate_attempt(
    *,
    task: CandidateTask,
    context: CandidateProcessingContext,
    policy_override: SolutionPolicy | None = None,
    refinement_attempt: RefinementAttempt | None = None,
    tool_expansion: dict[str, object] | None = None,
) -> _CandidateAttemptResult:
    policy: SolutionPolicy | None = policy_override
    if policy is None:
        try:
            policy = context.generate_policy(task)
        except LLMProviderError as exc:
            return _CandidateAttemptResult(
                sample=None,
                rejection=assemble_quality_gate_rejection(
                    task=task,
                    cause=exc.cause,
                    message="Remote solution-policy generation failed before execution.",
                    details={
                        "error_class": exc.error_class,
                        "retry_count": exc.retry_count,
                        "lineage": dict(exc.lineage) if exc.lineage else {},
                    },
                ),
                signature=None,
                policy=None,
                capability_gap=None,
            )
    try:
        execution = execute_candidate(
            task,
            context.registry,
            policy=policy,
            adapter_shim=context.adapter_shim,
        )
    except AdapterExecutionError as exc:
        adapter_rejection = _adapter_rejection_record(exc)
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="adapter_contract_rejected",
                policy=policy,
                adapter_rejection=adapter_rejection,
            ),
            signature=None,
            policy=policy,
            capability_gap=None,
        )
    except ToolMissingError as exc:
        gap = build_capability_gap(
            task=task,
            policy=policy,
            error=exc,
            cause="tool_missing",
            registry=context.registry,
        )
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="tool_missing",
                policy=policy,
                capability_gap=gap.export(),
            ),
            signature=None,
            policy=policy,
            capability_gap=gap,
        )
    except ToolSchemaError as exc:
        gap = build_capability_gap(
            task=task,
            policy=policy,
            error=exc,
            cause="tool_schema_error",
            registry=context.registry,
        )
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="tool_schema_error",
                policy=policy,
                capability_gap=gap.export(),
            ),
            signature=None,
            policy=policy,
            capability_gap=gap,
        )
    except PolicyValidationError as exc:
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="tool_schema_error",
                policy=policy,
            ),
            signature=None,
            policy=policy,
            capability_gap=None,
        )
    except BranchExecutionError as exc:
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="solution_logic_error",
                policy=policy,
                branch_outcomes=exc.branch_outcomes,
            ),
            signature=None,
            policy=policy,
            capability_gap=None,
        )
    except Exception as exc:
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(task=task, error=exc, policy=policy),
            signature=None,
            policy=policy,
            capability_gap=None,
        )

    verification = context.verifier.verify(
        task,
        execution,
        environment=context.environment,
    )
    if not verification.passed:
        failure_cause = _verification_failure_cause(verification.export())
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_rejection(task=task, verification=verification, policy=policy),
            signature=None,
            policy=policy,
            capability_gap=None,
            episode_log=_build_attempt_episode_log(
                task=task,
                context=context,
                policy=policy,
                execution=execution,
                outcome_status="rejected",
                failure_cause=failure_cause,
            ),
        )

    sample = assemble_sample(
        dataset_version=context.dataset_version,
        environment=context.environment.metadata(),
        tools=context.registry.export(),
        task=task,
        execution=execution,
        verification=verification,
        llm_config=context.llm_config,
        refinement_attempt=refinement_attempt,
        tool_expansion=tool_expansion,
    )
    signature = candidate_duplicate_signature(
        instruction=task.instruction,
        trajectory=execution.trajectory,
    )
    if not final_answer_is_logically_supported(sample):
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_quality_gate_rejection(
                task=task,
                cause="solution_logic_error",
                message="Final answer is not supported by observations and verifier expectation.",
                policy=policy,
            ),
            signature=None,
            policy=policy,
            capability_gap=None,
            episode_log=_build_attempt_episode_log(
                task=task,
                context=context,
                policy=policy,
                execution=execution,
                outcome_status="rejected",
                failure_cause="solution_logic_error",
            ),
        )
    return _CandidateAttemptResult(
        sample=sample,
        rejection=None,
        signature=signature,
        policy=policy,
        capability_gap=None,
        episode_log=_build_attempt_episode_log(
            task=task,
            context=context,
            policy=policy,
            execution=execution,
            outcome_status="accepted",
            failure_cause=None,
        ),
    )


def _build_attempt_episode_log(
    *,
    task: CandidateTask,
    context: CandidateProcessingContext,
    policy: SolutionPolicy,
    execution: ExecutionResult,
    outcome_status: str,
    failure_cause: str | None,
) -> dict[str, object] | None:
    if not hasattr(context.environment, "runtime_metadata"):
        return None
    return build_episode_log(
        candidate_id=task.candidate_id,
        runtime_metadata=context.environment.runtime_metadata(),
        policy=policy,
        verifier=context.verifier,
        trajectory=execution.trajectory,
        outcome_status=outcome_status,
        failure_cause=failure_cause,
    ).export()


def _verification_failure_cause(verification: dict[str, object]) -> str:
    checks = verification.get("checks")
    if not isinstance(checks, list):
        return "verification_failed"
    failed_check = next(
        (check for check in checks if isinstance(check, dict) and not check.get("passed")),
        {},
    )
    cause = failed_check.get("cause") if isinstance(failed_check, dict) else None
    return str(cause or "verification_failed")


def _maybe_expand_tool_and_rerun(
    *,
    attempt_result: _CandidateAttemptResult,
    task: CandidateTask,
    context: CandidateProcessingContext,
    tool_proposal_generator: ToolProposalGenerator | None,
    tool_proposal_records: list[dict[str, object]],
) -> _CandidateAttemptResult | None:
    if tool_proposal_generator is None or attempt_result.capability_gap is None:
        return None

    gap = attempt_result.capability_gap
    try:
        proposal = tool_proposal_generator(gap)
    except LLMProviderError as exc:
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_quality_gate_rejection(
                task=task,
                cause=exc.cause,
                message="Remote tool proposal generation failed before admission.",
                details={
                    "error_class": exc.error_class,
                    "retry_count": exc.retry_count,
                    "lineage": dict(exc.lineage) if exc.lineage else {},
                    "capability_gap": gap.export(),
                },
                policy=attempt_result.policy,
            ),
            signature=None,
            policy=attempt_result.policy,
            capability_gap=gap,
        )

    admission = admit_curated_tool(proposal, context.registry, context.environment)
    proposal_record = build_tool_proposal_record(
        candidate_id=task.candidate_id,
        gap=gap,
        proposal=proposal,
        admission=admission,
    )
    tool_proposal_records.append(proposal_record)
    if not admission.accepted:
        assert attempt_result.rejection is not None
        rejection = _attach_tool_proposal_to_rejection(
            attempt_result.rejection,
            proposal_record,
        )
        return _CandidateAttemptResult(
            sample=None,
            rejection=rejection,
            signature=None,
            policy=attempt_result.policy,
            capability_gap=gap,
            episode_log=attempt_result.episode_log,
        )

    rerun = _run_candidate_attempt(
        task=task,
        context=context,
        policy_override=attempt_result.policy,
        tool_expansion=proposal_record,
    )
    if rerun.rejection is not None:
        rerun = _CandidateAttemptResult(
            sample=None,
            rejection=_attach_tool_proposal_to_rejection(rerun.rejection, proposal_record),
            signature=None,
            policy=rerun.policy,
            capability_gap=rerun.capability_gap,
            episode_log=rerun.episode_log,
        )
    return rerun


def _attach_tool_proposal_to_rejection(
    rejection: dict[str, object],
    proposal_record: dict[str, object],
) -> dict[str, object]:
    updated = dict(rejection)
    details = dict(updated.get("details", {}))
    details["tool_proposal"] = proposal_record
    updated["details"] = details
    return updated


def _adapter_rejection_record(error: AdapterExecutionError) -> dict[str, object]:
    result = error.result
    adapter_error = result.error or {}
    cause = str(adapter_error.get("cause", "adapter_error"))
    record = {
        "schema_version": "adapter_lineage_v1",
        "adapter_id": result.adapter_id,
        "protocol_label": PROTOCOL_LABEL,
        "adapter_version": ADAPTER_VERSION,
        "operation": "tool.call",
        "tool_name": result.tool_name,
        "call_id": result.call_id,
        "execution_status": result.execution_status,
        "rejection_cause": cause,
    }
    record["result"] = result.export()
    return record


def _maybe_refine(
    *,
    refiner: Refiner | None,
    task: CandidateTask,
    rejection: dict[str, object],
    source_policy: SolutionPolicy | None,
) -> RefinementAttempt | None:
    if refiner is None:
        return None
    cause = str(rejection.get("cause", ""))
    if not repairable(cause):
        return None
    details = rejection.get("details")
    if not isinstance(details, dict):
        details = {}
    refinement_attempt = refiner(
        RefinementContext(
            task=task,
            source_failure_cause=cause,
            source_failure_details=dict(details),
            attempt_number=1,
            source_policy=source_policy,
        )
    )
    if refinement_attempt is None or refinement_attempt.repair_decision == "not_repairable":
        return None
    return refinement_attempt


def _ensure_generation_lineage(task: CandidateTask, _llm_config: LLMConfig) -> CandidateTask:
    if task.generation_lineage:
        return task
    return replace(task, generation_lineage=local_task_generation_lineage())


def _maybe_route_review(
    review_records: list[dict[str, object]],
    rejection: dict[str, object],
    *,
    route_reviewable_failures: bool,
) -> None:
    cause = str(rejection.get("cause", ""))
    if not route_reviewable_failures or not reviewable(cause):
        return
    review_records.append(
        build_review_record(
            candidate_id=str(rejection.get("candidate_id", "unknown_candidate")),
            cause=cause,
            task=rejection.get("task", {}),
            uncertainty_reason=str(rejection.get("details", {}).get("message", cause)),
            source_artifact="rejections.jsonl",
        )
    )


def merge_candidate_outcomes(
    outcomes: tuple[ProvisionalCandidateOutcome, ...] | list[ProvisionalCandidateOutcome],
    *,
    initial_accepted_signatures: set[tuple[str, tuple[str, ...]]] | frozenset[tuple[str, tuple[str, ...]]] | None = None,
    route_reviewable_failures: bool = False,
) -> CandidateMergeResult:
    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    episode_logs: list[dict[str, object]] = []
    accepted_signatures: set[tuple[str, tuple[str, ...]]] = set(initial_accepted_signatures or set())

    for outcome in sorted(outcomes, key=lambda item: item.sequence_index):
        _validate_provisional_outcome(outcome)
        if outcome.sample is not None:
            signature = outcome.duplicate_signature
            if signature is not None and signature in accepted_signatures:
                duplicate_rejection = _duplicate_rejection_from_outcome(outcome, signature)
                rejections.append(duplicate_rejection)
                _maybe_route_review(
                    review_records,
                    duplicate_rejection,
                    route_reviewable_failures=route_reviewable_failures,
                )
            else:
                samples.append(outcome.sample)
                if outcome.episode_log is not None:
                    episode_logs.append(outcome.episode_log)
                if signature is not None:
                    accepted_signatures.add(signature)
        else:
            assert outcome.rejection is not None
            rejections.append(outcome.rejection)
            if outcome.episode_log is not None:
                episode_logs.append(outcome.episode_log)
        review_records.extend(outcome.review_records)
        tool_proposal_records.extend(outcome.tool_proposal_records)

    return CandidateMergeResult(
        samples=tuple(samples),
        rejections=tuple(rejections),
        review_records=tuple(review_records),
        tool_proposal_records=tuple(tool_proposal_records),
        accepted_signatures=frozenset(accepted_signatures),
        episode_logs=tuple(episode_logs),
    )


def _validate_provisional_outcome(outcome: ProvisionalCandidateOutcome) -> None:
    has_sample = outcome.sample is not None
    has_rejection = outcome.rejection is not None
    if has_sample == has_rejection:
        raise ValueError("Provisional candidate outcome must contain exactly one sample or rejection.")


def _duplicate_rejection_from_outcome(
    outcome: ProvisionalCandidateOutcome,
    signature: tuple[str, tuple[str, ...]],
) -> dict[str, object]:
    sample = outcome.sample or {}
    details: dict[str, object] = {
        "message": "Accepted candidate duplicates a prior task instruction and tool sequence.",
        "retry_eligible": retry_eligible("quality_duplicate"),
        "signature": [signature[0], list(signature[1])],
    }
    lineage = sample.get("lineage", {})
    if isinstance(lineage, dict):
        role_lineages = _role_lineages_from_sample_lineage(lineage)
        if role_lineages:
            details["role_lineages"] = role_lineages
        refinement = _refinement_rejection_metadata_from_sample_lineage(lineage)
        if refinement:
            details["refinement"] = refinement
    return {
        "candidate_id": outcome.candidate_id,
        "cause": "quality_duplicate",
        "task": outcome.task_record or sample.get("task", {}),
        "details": details,
    }


def _role_lineages_from_sample_lineage(lineage: dict[str, object]) -> dict[str, object]:
    role_lineages: dict[str, object] = {}
    for key in ("generator", "solution_policy"):
        value = lineage.get(key)
        if isinstance(value, dict):
            role_lineages[key] = dict(value)
    return role_lineages


def _refinement_rejection_metadata_from_sample_lineage(
    lineage: dict[str, object],
) -> dict[str, object] | None:
    refinement = lineage.get("refinement")
    if not isinstance(refinement, dict):
        return None
    return {
        "outcome": "rejected",
        "original_candidate_id": refinement.get("original_candidate_id"),
        "attempt_number": refinement.get("attempt_number"),
        "source_failure_cause": refinement.get("source_failure_cause"),
        "critic_diagnosis": refinement.get("critic_diagnosis"),
        "repair_decision": refinement.get("repair_decision"),
        "lineage": {
            key: value
            for key, value in refinement.items()
            if key
            in {
                "role",
                "role_version",
                "output_type",
                "provider_host",
                "model",
                "config_hash",
            }
        },
    }


def _environment_isolation_record(
    context: CandidateProcessingContext,
) -> dict[str, object]:
    metadata = context.environment.metadata()
    return {
        "schema_version": "candidate_environment_isolation_v1",
        "environment_id": metadata.environment_id,
        "environment_version": metadata.version,
        "reset_recipe": dict(metadata.reset_recipe),
        "adapter_rebuilt": context.adapter_shim is not None,
        "registry_tools": context.registry.tool_names(),
    }


def _registry_mutations_from_tool_proposals(
    tool_proposal_records: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    mutations: list[dict[str, object]] = []
    for record in tool_proposal_records:
        admission = record.get("admission")
        if not isinstance(admission, dict) or admission.get("outcome") != "accepted":
            continue
        mutation: dict[str, object] = {
            "schema_version": "candidate_registry_mutation_v1",
            "candidate_id": str(record.get("candidate_id", "unknown_candidate")),
            "mutation_type": "curated_tool_admission",
            "tool_name": str(admission.get("tool_name", record.get("tool_name", "unknown_tool"))),
            "outcome": str(admission.get("outcome")),
        }
        tool_version = admission.get("tool_version")
        if tool_version:
            mutation["tool_version"] = str(tool_version)
        mutations.append(mutation)
    return tuple(mutations)
