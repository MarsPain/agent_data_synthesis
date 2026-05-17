from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import httpx

from synthesis.contracts import ContractValidationError, validate_candidate_task
from synthesis.datasets import (
    assemble_candidate_schema_rejection,
    assemble_execution_rejection,
    assemble_generation_stage_rejection,
    assemble_pipeline_gate_rejection,
    assemble_quality_gate_rejection,
    assemble_rejection,
    assemble_task_editor_rejection,
    assemble_sample,
    assemble_task_suggestion_rejection,
    attach_refinement_to_rejection,
    write_dataset_artifacts,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import (
    BranchExecutionError,
    PolicyValidationError,
    SolutionPolicy,
    execute_candidate,
    scripted_solution_policy,
)
from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient
from synthesis.quality import (
    build_review_record,
    candidate_duplicate_signature,
    final_answer_is_logically_supported,
    reviewable,
)
from synthesis.refinement import Refiner, RefinementAttempt, RefinementContext, repairable
from synthesis.refinement import generate_llm_backed_refinement
from synthesis.roles import RoleRegistry, default_role_registry
from synthesis.seeds import foundation_seed
from synthesis.seeds import DomainSeed
from synthesis.seeds import deterministic_seed_transformations
from synthesis.tasks import (
    CandidateTask,
    TaskExpansionResult,
    generate_deterministic_task_expansion,
    generate_llm_backed_edited_task,
    generate_foundation_candidates,
    generate_llm_backed_candidates,
    generate_llm_backed_task_suggestions,
    local_task_generation_lineage,
)
from synthesis.tools import (
    CapabilityGap,
    ToolProposal,
    ToolMissingError,
    ToolRegistry,
    ToolSchemaError,
    admit_curated_tool,
    build_capability_gap,
    build_contact_tool_registry,
    build_tool_proposal_record,
)
from synthesis.verification import ExactAnswerVerifier


@dataclass(frozen=True)
class PipelineResult:
    samples_path: Path
    manifest_path: Path
    rejections_path: Path
    quality_report_path: Path
    tool_proposals_path: Path | None
    parent_comparison_path: Path | None
    review_queue_path: Path | None
    accepted_count: int
    rejected_count: int


@dataclass(frozen=True)
class CandidateAttemptResult:
    sample: dict[str, object] | None
    rejection: dict[str, object] | None
    signature: tuple[str, tuple[str, ...]] | None
    policy: SolutionPolicy | None
    capability_gap: CapabilityGap | None = None


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
TaskExpansionGenerator = Callable[[DomainSeed], TaskExpansionResult]
PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
ToolProposalGenerator = Callable[[CapabilityGap], ToolProposal]


class FoundationGateError(RuntimeError):
    pass


def build_llm_candidate_generator(
    http_client: httpx.Client | None = None,
    *,
    role_registry: RoleRegistry | None = None,
) -> CandidateGenerator:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    registry = role_registry or default_role_registry()
    return lambda seed: generate_llm_backed_candidates(seed, client, role_registry=registry)


def build_llm_refiner(
    http_client: httpx.Client | None = None,
    *,
    role_registry: RoleRegistry | None = None,
) -> Refiner:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    registry = role_registry or default_role_registry()

    def refine(context: RefinementContext) -> RefinementAttempt | None:
        return generate_llm_backed_refinement(
            task=context.task,
            source_failure_cause=context.source_failure_cause,
            source_failure_details=context.source_failure_details,
            attempt_number=context.attempt_number,
            client=client,
            source_policy=context.source_policy,
            role_registry=registry,
        )

    return refine


def build_llm_task_expansion_generator(
    http_client: httpx.Client | None = None,
    *,
    role_registry: RoleRegistry | None = None,
) -> TaskExpansionGenerator:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    registry = role_registry or default_role_registry()

    def expand(seed: DomainSeed) -> TaskExpansionResult:
        candidates: list[CandidateTask] = []
        rejected_suggestions = []
        rejected_edits = []
        for seed_transformation in deterministic_seed_transformations(seed):
            transformation = seed_transformation.export()
            suggestions = generate_llm_backed_task_suggestions(
                seed,
                transformation,
                client,
                role_registry=registry,
            )
            for suggestion in suggestions:
                if suggestion.outcome == "rejected":
                    rejected_suggestions.append(suggestion)
                    continue
                edited = generate_llm_backed_edited_task(
                    seed,
                    transformation,
                    suggestion,
                    client,
                    role_registry=registry,
                )
                if edited.candidate is not None:
                    candidates.append(edited.candidate)
                elif edited.rejection is not None:
                    rejected_edits.append(edited)
        return TaskExpansionResult(
            candidates=candidates,
            rejected_suggestions=rejected_suggestions,
            rejected_edits=rejected_edits,
        )

    return expand


def run_foundation_pipeline(
    output_dir: Path,
    *,
    dataset_version: str = "dataset_foundation_v1",
    candidate_generator: CandidateGenerator | None = None,
    policy_generator: PolicyGenerator | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
    refiner: Refiner | None = None,
    tool_proposal_generator: ToolProposalGenerator | None = None,
    enable_branching: bool = False,
    enable_task_expansion: bool = False,
    task_expansion_generator: TaskExpansionGenerator | None = None,
) -> PipelineResult:
    seed = foundation_seed()
    environment = ContactEnvironment.create_fixture(output_dir / "environment")
    registry = build_contact_tool_registry(environment)
    verifier = ExactAnswerVerifier()
    llm_config = LLMConfig.from_env()
    if candidate_generator is None:
        generate_candidates = lambda current_seed: generate_foundation_candidates(
            current_seed,
            include_branching=enable_branching,
        )
    else:
        generate_candidates = candidate_generator
    generate_task_expansion = task_expansion_generator or generate_deterministic_task_expansion
    generate_policy = policy_generator or scripted_solution_policy

    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    accepted_signatures: set[tuple[str, tuple[str, ...]]] = set()
    try:
        _run_foundation_quality_gates(environment, registry)
    except FoundationGateError as exc:
        rejections.append(assemble_pipeline_gate_rejection(error=exc))
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=samples,
            rejections=rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=review_records,
            tool_proposals=tool_proposal_records,
        )
        return PipelineResult(
            samples_path=artifacts.samples_path,
            manifest_path=artifacts.manifest_path,
            rejections_path=artifacts.rejections_path,
            quality_report_path=artifacts.quality_report_path,
            tool_proposals_path=artifacts.tool_proposals_path,
            parent_comparison_path=artifacts.parent_comparison_path,
            review_queue_path=artifacts.review_queue_path,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )

    try:
        raw_tasks = generate_candidates(seed)
    except LLMProviderError as exc:
        rejections.append(assemble_generation_stage_rejection(error=exc))
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=samples,
            rejections=rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=review_records,
            tool_proposals=tool_proposal_records,
        )
        return PipelineResult(
            samples_path=artifacts.samples_path,
            manifest_path=artifacts.manifest_path,
            rejections_path=artifacts.rejections_path,
            quality_report_path=artifacts.quality_report_path,
            tool_proposals_path=artifacts.tool_proposals_path,
            parent_comparison_path=artifacts.parent_comparison_path,
            review_queue_path=artifacts.review_queue_path,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )

    for raw_task in raw_tasks:
        _process_candidate_through_gates(
            raw_task=raw_task,
            dataset_version=dataset_version,
            environment=environment,
            registry=registry,
            verifier=verifier,
            llm_config=llm_config,
            generate_policy=generate_policy,
            accepted_signatures=accepted_signatures,
            samples=samples,
            rejections=rejections,
            review_records=review_records,
            tool_proposal_records=tool_proposal_records,
            route_reviewable_failures=route_reviewable_failures,
            refiner=refiner,
            tool_proposal_generator=tool_proposal_generator,
        )

    if enable_task_expansion:
        expansion = generate_task_expansion(seed)
        for rejected_suggestion in expansion.rejected_suggestions:
            rejection = assemble_task_suggestion_rejection(suggestion=rejected_suggestion)
            rejections.append(rejection)
            _maybe_route_review(
                review_records,
                rejection,
                route_reviewable_failures=route_reviewable_failures,
            )
        for rejected_edit in expansion.rejected_edits:
            rejection = assemble_task_editor_rejection(edited_task=rejected_edit)
            rejections.append(rejection)
            _maybe_route_review(
                review_records,
                rejection,
                route_reviewable_failures=route_reviewable_failures,
            )
        for expanded_task in expansion.candidates:
            _process_candidate_through_gates(
                raw_task=expanded_task,
                dataset_version=dataset_version,
                environment=environment,
                registry=registry,
                verifier=verifier,
                llm_config=llm_config,
                generate_policy=generate_policy,
                accepted_signatures=accepted_signatures,
                samples=samples,
                rejections=rejections,
                review_records=review_records,
                tool_proposal_records=tool_proposal_records,
                route_reviewable_failures=route_reviewable_failures,
                refiner=refiner,
                tool_proposal_generator=tool_proposal_generator,
            )

    artifacts = write_dataset_artifacts(
        output_dir=output_dir,
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
        parent_artifact_path=parent_artifact_path,
        review_records=review_records,
        tool_proposals=tool_proposal_records,
    )
    return PipelineResult(
        samples_path=artifacts.samples_path,
        manifest_path=artifacts.manifest_path,
        rejections_path=artifacts.rejections_path,
        quality_report_path=artifacts.quality_report_path,
        tool_proposals_path=artifacts.tool_proposals_path,
        parent_comparison_path=artifacts.parent_comparison_path,
        review_queue_path=artifacts.review_queue_path,
        accepted_count=artifacts.accepted_count,
        rejected_count=artifacts.rejected_count,
    )


def _process_candidate_through_gates(
    *,
    raw_task: CandidateTask,
    dataset_version: str,
    environment: ContactEnvironment,
    registry: ToolRegistry,
    verifier: ExactAnswerVerifier,
    llm_config: LLMConfig,
    generate_policy: PolicyGenerator,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
    review_records: list[dict[str, object]],
    tool_proposal_records: list[dict[str, object]],
    route_reviewable_failures: bool,
    refiner: Refiner | None,
    tool_proposal_generator: ToolProposalGenerator | None,
) -> None:
    try:
        task = validate_candidate_task(raw_task)
    except ContractValidationError as exc:
        rejections.append(assemble_candidate_schema_rejection(error=exc))
        return
    task = _ensure_generation_lineage(task, llm_config)

    attempt_result = _run_candidate_attempt(
        task=task,
        dataset_version=dataset_version,
        environment=environment,
        registry=registry,
        verifier=verifier,
        llm_config=llm_config,
        generate_policy=generate_policy,
        accepted_signatures=accepted_signatures,
    )
    if _record_sample_if_present(attempt_result, samples, accepted_signatures):
        return

    assert attempt_result.rejection is not None
    tool_expanded = _maybe_expand_tool_and_rerun(
        attempt_result=attempt_result,
        task=task,
        dataset_version=dataset_version,
        environment=environment,
        registry=registry,
        verifier=verifier,
        llm_config=llm_config,
        generate_policy=generate_policy,
        accepted_signatures=accepted_signatures,
        tool_proposal_generator=tool_proposal_generator,
        tool_proposal_records=tool_proposal_records,
    )
    if tool_expanded is not None:
        if _record_sample_if_present(tool_expanded, samples, accepted_signatures):
            return
        assert tool_expanded.rejection is not None
        rejections.append(tool_expanded.rejection)
        _maybe_route_review(
            review_records,
            tool_expanded.rejection,
            route_reviewable_failures=route_reviewable_failures,
        )
        return

    try:
        refinement_attempt = _maybe_refine(
            refiner=refiner,
            task=task,
            rejection=attempt_result.rejection,
            source_policy=attempt_result.policy,
        )
    except LLMProviderError as exc:
        rejections.append(
            assemble_quality_gate_rejection(
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
            )
        )
        return
    if refinement_attempt is None:
        rejections.append(attempt_result.rejection)
        _maybe_route_review(
            review_records,
            attempt_result.rejection,
            route_reviewable_failures=route_reviewable_failures,
        )
        return

    refined_task = refinement_attempt.revised_candidate or task
    refined_result = _run_candidate_attempt(
        task=refined_task,
        dataset_version=dataset_version,
        environment=environment,
        registry=registry,
        verifier=verifier,
        llm_config=llm_config,
        generate_policy=generate_policy,
        accepted_signatures=accepted_signatures,
        policy_override=refinement_attempt.revised_policy,
        refinement_attempt=refinement_attempt,
    )
    if _record_sample_if_present(refined_result, samples, accepted_signatures):
        return

    assert refined_result.rejection is not None
    rejection = attach_refinement_to_rejection(
        refined_result.rejection,
        refinement_attempt,
    )
    rejections.append(rejection)
    _maybe_route_review(
        review_records,
        rejection,
        route_reviewable_failures=route_reviewable_failures,
    )


def _record_sample_if_present(
    attempt_result: CandidateAttemptResult,
    samples: list[dict[str, object]],
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
) -> bool:
    if attempt_result.sample is None:
        return False
    assert attempt_result.signature is not None
    accepted_signatures.add(attempt_result.signature)
    samples.append(attempt_result.sample)
    return True


def _run_candidate_attempt(
    *,
    task: CandidateTask,
    dataset_version: str,
    environment: ContactEnvironment,
    registry: ToolRegistry,
    verifier: ExactAnswerVerifier,
    llm_config: LLMConfig,
    generate_policy: PolicyGenerator,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
    policy_override: SolutionPolicy | None = None,
    refinement_attempt: RefinementAttempt | None = None,
    tool_expansion: dict[str, object] | None = None,
) -> CandidateAttemptResult:
    policy: SolutionPolicy | None = policy_override
    if policy is None:
        try:
            policy = generate_policy(task)
        except LLMProviderError as exc:
            return CandidateAttemptResult(
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
        execution = execute_candidate(task, registry, policy=policy)
    except ToolMissingError as exc:
        gap = build_capability_gap(
            task=task,
            policy=policy,
            error=exc,
            cause="tool_missing",
            registry=registry,
        )
        return CandidateAttemptResult(
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
            registry=registry,
        )
        return CandidateAttemptResult(
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
        return CandidateAttemptResult(
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
        return CandidateAttemptResult(
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
        return CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(task=task, error=exc, policy=policy),
            signature=None,
            policy=policy,
            capability_gap=None,
        )

    verification = verifier.verify(task, execution, environment=environment)
    if not verification.passed:
        return CandidateAttemptResult(
            sample=None,
            rejection=assemble_rejection(task=task, verification=verification, policy=policy),
            signature=None,
            policy=policy,
            capability_gap=None,
        )

    sample = assemble_sample(
        dataset_version=dataset_version,
        environment=environment.metadata(),
        tools=registry.export(),
        task=task,
        execution=execution,
        verification=verification,
        llm_config=llm_config,
        refinement_attempt=refinement_attempt,
        tool_expansion=tool_expansion,
    )
    signature = candidate_duplicate_signature(
        instruction=task.instruction,
        trajectory=execution.trajectory,
    )
    if signature in accepted_signatures:
        return CandidateAttemptResult(
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
        return CandidateAttemptResult(
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
    return CandidateAttemptResult(
        sample=sample,
        rejection=None,
        signature=signature,
        policy=policy,
        capability_gap=None,
    )


def _maybe_expand_tool_and_rerun(
    *,
    attempt_result: CandidateAttemptResult,
    task: CandidateTask,
    dataset_version: str,
    environment: ContactEnvironment,
    registry: ToolRegistry,
    verifier: ExactAnswerVerifier,
    llm_config: LLMConfig,
    generate_policy: PolicyGenerator,
    accepted_signatures: set[tuple[str, tuple[str, ...]]],
    tool_proposal_generator: ToolProposalGenerator | None,
    tool_proposal_records: list[dict[str, object]],
) -> CandidateAttemptResult | None:
    if tool_proposal_generator is None or attempt_result.capability_gap is None:
        return None

    gap = attempt_result.capability_gap
    try:
        proposal = tool_proposal_generator(gap)
    except LLMProviderError as exc:
        return CandidateAttemptResult(
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

    admission = admit_curated_tool(proposal, registry, environment)
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
        return CandidateAttemptResult(
            sample=None,
            rejection=rejection,
            signature=None,
            policy=attempt_result.policy,
            capability_gap=gap,
        )

    rerun = _run_candidate_attempt(
        task=task,
        dataset_version=dataset_version,
        environment=environment,
        registry=registry,
        verifier=verifier,
        llm_config=llm_config,
        generate_policy=generate_policy,
        accepted_signatures=accepted_signatures,
        policy_override=attempt_result.policy,
        tool_expansion=proposal_record,
    )
    if rerun.rejection is not None:
        rerun = CandidateAttemptResult(
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


def _run_foundation_quality_gates(
    environment: ContactEnvironment,
    registry: ToolRegistry,
) -> None:
    metadata = environment.metadata()
    if not metadata.environment_id or not metadata.version or not metadata.reset_recipe:
        raise FoundationGateError("environment reset metadata is incomplete")

    tools = registry.export()
    if not tools:
        raise FoundationGateError("registered tool smoke check found no tools")
    names = {str(tool.get("name")) for tool in tools}
    if "lookup_contact_email" not in names:
        raise FoundationGateError("lookup_contact_email is not registered")

    try:
        result = registry.execute("lookup_contact_email", {"name": "Alice Zhang"})
    except Exception as exc:
        raise FoundationGateError(f"lookup_contact_email smoke check failed: {exc}") from exc
    if result.get("email") != "alice.zhang@example.test":
        raise FoundationGateError("lookup_contact_email smoke check returned unexpected data")
