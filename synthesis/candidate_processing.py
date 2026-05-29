from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from synthesis.contracts import ContractValidationError, validate_candidate_task
from synthesis.datasets import (
    assemble_candidate_schema_rejection,
    assemble_execution_rejection,
    assemble_quality_gate_rejection,
    assemble_rejection,
    assemble_sample,
    attach_refinement_to_rejection,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import (
    BranchExecutionError,
    PolicyValidationError,
    SolutionPolicy,
    execute_candidate,
)
from synthesis.llm import LLMConfig, LLMProviderError
from synthesis.mcp import (
    ADAPTER_VERSION,
    PROTOCOL_LABEL,
    AdapterExecutionError,
    LocalContactsAdapterShim,
)
from synthesis.quality import (
    build_review_record,
    candidate_duplicate_signature,
    final_answer_is_logically_supported,
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
    environment: ContactEnvironment
    registry: ToolRegistry
    adapter_shim: LocalContactsAdapterShim | None
    verifier: ExactAnswerVerifier
    llm_config: LLMConfig
    generate_policy: PolicyGenerator


@dataclass(frozen=True)
class CandidateProcessingOptions:
    route_reviewable_failures: bool = False
    refiner: Refiner | None = None
    tool_proposal_generator: ToolProposalGenerator | None = None


@dataclass(frozen=True)
class CandidateProcessingOutcome:
    sample: dict[str, object] | None
    rejection: dict[str, object] | None
    review_records: tuple[dict[str, object], ...] = ()
    tool_proposal_records: tuple[dict[str, object], ...] = ()
    accepted_signature: tuple[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class _CandidateAttemptResult:
    sample: dict[str, object] | None
    rejection: dict[str, object] | None
    signature: tuple[str, tuple[str, ...]] | None
    policy: SolutionPolicy | None
    capability_gap: CapabilityGap | None = None


def process_candidate_through_gates(
    *,
    raw_task: CandidateTask,
    context: CandidateProcessingContext,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
    options: CandidateProcessingOptions,
) -> CandidateProcessingOutcome:
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    try:
        task = validate_candidate_task(raw_task)
    except ContractValidationError as exc:
        return CandidateProcessingOutcome(
            sample=None,
            rejection=assemble_candidate_schema_rejection(error=exc),
        )
    task = _ensure_generation_lineage(task, context.llm_config)

    attempt_result = _run_candidate_attempt(
        task=task,
        context=context,
        accepted_signatures=accepted_signatures,
    )
    sample_outcome = _sample_outcome_if_present(
        attempt_result,
        review_records=review_records,
        tool_proposal_records=tool_proposal_records,
    )
    if sample_outcome is not None:
        return sample_outcome

    assert attempt_result.rejection is not None
    tool_expanded = _maybe_expand_tool_and_rerun(
        attempt_result=attempt_result,
        task=task,
        context=context,
        accepted_signatures=accepted_signatures,
        tool_proposal_generator=options.tool_proposal_generator,
        tool_proposal_records=tool_proposal_records,
    )
    if tool_expanded is not None:
        sample_outcome = _sample_outcome_if_present(
            tool_expanded,
            review_records=review_records,
            tool_proposal_records=tool_proposal_records,
        )
        if sample_outcome is not None:
            return sample_outcome
        assert tool_expanded.rejection is not None
        _maybe_route_review(
            review_records,
            tool_expanded.rejection,
            route_reviewable_failures=options.route_reviewable_failures,
        )
        return CandidateProcessingOutcome(
            sample=None,
            rejection=tool_expanded.rejection,
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
        )

    try:
        refinement_attempt = _maybe_refine(
            refiner=options.refiner,
            task=task,
            rejection=attempt_result.rejection,
            source_policy=attempt_result.policy,
        )
    except LLMProviderError as exc:
        return CandidateProcessingOutcome(
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
        )
    if refinement_attempt is None:
        _maybe_route_review(
            review_records,
            attempt_result.rejection,
            route_reviewable_failures=options.route_reviewable_failures,
        )
        return CandidateProcessingOutcome(
            sample=None,
            rejection=attempt_result.rejection,
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
        )

    refined_task = refinement_attempt.revised_candidate or task
    refined_result = _run_candidate_attempt(
        task=refined_task,
        context=context,
        accepted_signatures=accepted_signatures,
        policy_override=refinement_attempt.revised_policy,
        refinement_attempt=refinement_attempt,
    )
    sample_outcome = _sample_outcome_if_present(
        refined_result,
        review_records=review_records,
        tool_proposal_records=tool_proposal_records,
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
    return CandidateProcessingOutcome(
        sample=None,
        rejection=rejection,
        review_records=tuple(review_records),
        tool_proposal_records=tuple(tool_proposal_records),
    )


def _sample_outcome_if_present(
    attempt_result: _CandidateAttemptResult,
    *,
    review_records: list[dict[str, object]],
    tool_proposal_records: list[dict[str, object]],
) -> CandidateProcessingOutcome | None:
    if attempt_result.sample is None:
        return None
    assert attempt_result.signature is not None
    return CandidateProcessingOutcome(
        sample=attempt_result.sample,
        rejection=None,
        review_records=tuple(review_records),
        tool_proposal_records=tuple(tool_proposal_records),
        accepted_signature=attempt_result.signature,
    )


def _run_candidate_attempt(
    *,
    task: CandidateTask,
    context: CandidateProcessingContext,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
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
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_rejection(task=task, verification=verification, policy=policy),
            signature=None,
            policy=policy,
            capability_gap=None,
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
    if signature in accepted_signatures:
        return _CandidateAttemptResult(
            sample=None,
            rejection=assemble_quality_gate_rejection(
                task=task,
                cause="quality_duplicate",
                message="Accepted candidate duplicates a prior task instruction and tool sequence.",
                details={"signature": list(signature)},
                policy=policy,
            ),
            signature=None,
            policy=policy,
            capability_gap=None,
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
        )
    return _CandidateAttemptResult(
        sample=sample,
        rejection=None,
        signature=signature,
        policy=policy,
        capability_gap=None,
    )


def _maybe_expand_tool_and_rerun(
    *,
    attempt_result: _CandidateAttemptResult,
    task: CandidateTask,
    context: CandidateProcessingContext,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
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
        )

    rerun = _run_candidate_attempt(
        task=task,
        context=context,
        accepted_signatures=accepted_signatures,
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
