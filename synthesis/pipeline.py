from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Protocol

import httpx

from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    CandidateMergeResult,
    CandidateProcessingContext,
    CandidateProcessingOptions,
    PolicyGenerator,
    ProvisionalCandidateOutcome,
    ToolProposalGenerator,
    _maybe_route_review,
    merge_candidate_outcomes,
    process_candidate_through_gates,
)
from synthesis.coverage import CoveragePlan, compile_coverage_plan, write_coverage_plan
from synthesis.coverage_assignments import (
    CoverageAssignmentScheduler,
    CoverageAssignmentSchedulerFactory,
    CoverageAssignmentRecovery,
)
from synthesis.coverage_registry import (
    DomainCoveragePlanningVariant,
    resolve_domain_coverage_planning,
)
from synthesis.concurrency import validate_concurrency
from synthesis.datasets import (
    DatasetArtifacts,
    attach_coverage_plan_to_manifest,
    assemble_generation_stage_rejection,
    assemble_pipeline_gate_rejection,
    assemble_source_policy_rejection,
    assemble_task_editor_rejection,
    assemble_task_suggestion_rejection,
    write_dataset_artifacts,
)
from synthesis.episode_quality import (
    EPISODES_FILENAME,
    write_episode_logs as write_episode_log_jsonl,
)
from synthesis.domain_pipeline import (
    DomainGenerationBoundary,
    DomainLifecycleRun,
    DomainPipelineBundle,
    build_domain_pipeline_bundle,
    open_domain_run,
    rebuild_domain_pipeline_bundle,
)
from synthesis.environments import EnvironmentMetadata
from synthesis.domain_sources import build_domain_fixture_source_bundle
from synthesis.domain_generation import (
    DomainGenerationRequest,
    DomainGenerationResult,
    build_generation_contract_evidence,
)
from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient
from synthesis.mutation_admission import (
    CandidateAdmissionEvaluator,
    SemanticJudgeAttemptObserver,
    build_local_candidate_admission_evaluator,
    build_openai_compatible_semantic_mutation_judge,
    permit_candidate_execution,
)
from synthesis.refinement import Refiner, RefinementAttempt, RefinementContext
from synthesis.refinement import generate_llm_backed_refinement
from synthesis.roles import RoleRegistry, default_role_registry
from synthesis.run_profiles import RunProfile
from synthesis.sandbox import build_deterministic_sandbox_fixture
from synthesis.seeds import foundation_seed
from synthesis.seeds import DomainSeed
from synthesis.seeds import deterministic_seed_transformations
from synthesis.sources import (
    SourceBundle,
    SourcePolicyError,
    source_environment_admission_event,
    validate_source_bundle,
)
from synthesis.tasks import (
    CandidateTask,
    TaskExpansionResult,
    generate_deterministic_task_expansion,
    generate_llm_backed_edited_task,
    generate_llm_backed_candidates,
    generate_llm_backed_task_suggestions,
)
from synthesis.tools import (
    ToolRegistry,
)


# Cooperative cancellation must never turn executor shutdown into an implicit
# unbounded wait. Work that does not finish within this grace period is left
# explicitly interrupted and is eligible for the normal resume path.
CANCELLATION_DRAIN_TIMEOUT_SECONDS = 1.0
CANCELLATION_POLL_INTERVAL_SECONDS = 0.1


@dataclass(frozen=True)
class PipelineResult:
    samples_path: Path
    manifest_path: Path
    rejections_path: Path
    quality_report_path: Path
    tool_proposals_path: Path | None
    source_events_path: Path | None
    sandbox_audits_path: Path | None
    parent_comparison_path: Path | None
    review_queue_path: Path | None
    mutation_admission_report_path: Path | None
    episode_logs_path: Path | None
    accepted_count: int
    rejected_count: int
    coverage_plan_path: Path | None
    coverage_evidence_path: Path | None
    coverage_reconciliation: Mapping[str, object] | None


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask] | DomainGenerationResult]
CandidateGeneratorFactory = Callable[[DomainGenerationBoundary], CandidateGenerator]
TaskExpansionGenerator = Callable[[DomainSeed], TaskExpansionResult]
CandidateSetCallback = Callable[[tuple[CandidateTask, ...]], None]
CandidateStartCallback = Callable[[CandidateExecutionRequest], None]
CandidateOutcomeCallback = Callable[
    [CandidateExecutionRequest, ProvisionalCandidateOutcome], None
]
CandidateAttemptRunner = Callable[
    [CandidateExecutionRequest, CandidateProcessingOptions],
    ProvisionalCandidateOutcome,
]


class PipelineCancellation(RuntimeError):
    """Internal signal used to stop pickup while draining in-flight work."""

    def __init__(self, merge: CandidateMergeResult | None = None) -> None:
        super().__init__("pipeline cancellation requested")
        self.merge = merge


@dataclass(frozen=True)
class _CandidateWaveHooks:
    start: CandidateStartCallback | None = None
    outcome: CandidateOutcomeCallback | None = None
    precomputed: Mapping[int, ProvisionalCandidateOutcome] | None = None
    should_stop: Callable[[], bool] | None = None


class FoundationGateError(RuntimeError):
    pass


class FoundationEnvironment(Protocol):
    def metadata(self) -> EnvironmentMetadata: ...


def preview_coverage_plan(
    run_profile: RunProfile,
    *,
    admitted_environment_input: object | None = None,
    output_path: Path | None = None,
) -> CoveragePlan:
    coverage_reference = run_profile.coverage_profile
    if coverage_reference is None:
        raise ValueError("run profile does not select a coverage profile")
    target_candidate_count = run_profile.generation.target_candidate_count
    if target_candidate_count is None:
        raise ValueError(
            "run profile target candidate count is required for coverage planning"
        )
    planning = resolve_domain_coverage_planning(run_profile.seed.domain)
    coverage_profile = planning.resolve_profile(
        coverage_reference.profile_id,
        coverage_reference.version,
    )
    catalog = planning.resolve_catalog(coverage_profile.catalog_version)
    plan = compile_coverage_plan(
        catalog=catalog,
        coverage_profile=coverage_profile,
        version_registry=planning.version_registry,
        selected_features=tuple(run_profile.features.enabled_feature_names()),
        target_accepted_sample_count=(
            coverage_reference.target_accepted_sample_count
        ),
        target_candidate_count=target_candidate_count,
        admitted_capacity=planning.resolve_capacity_for_catalog(
            catalog,
            admitted_environment_input,
        ),
        balance_weight_overrides=coverage_reference.balance_weight_overrides,
    )
    if output_path is not None:
        write_coverage_plan(output_path, plan)
    return plan


def build_llm_candidate_generator(
    http_client: httpx.Client | None = None,
    *,
    role_registry: RoleRegistry | None = None,
) -> CandidateGenerator:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    registry = role_registry or default_role_registry()
    return lambda seed: generate_llm_backed_candidates(seed, client, role_registry=registry)


def build_domain_llm_candidate_generator_factory(
    target_candidate_count: int,
    http_client: httpx.Client | None = None,
    *,
    role_registry: RoleRegistry | None = None,
) -> CandidateGeneratorFactory:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    registry = role_registry or default_role_registry()

    def factory(boundary: DomainGenerationBoundary) -> CandidateGenerator:
        if boundary.generation_spec is None:
            raise ValueError("source_backed_remote_context_not_allowed")
        return lambda seed: boundary.generate(
            DomainGenerationRequest(
                seed=seed,
                target_candidate_count=target_candidate_count,
                role_registry=registry,
            ),
            provider_adapter=client,
        )

    return factory


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
    candidate_set_callback: CandidateSetCallback | None = None,
    candidate_start_callback: CandidateStartCallback | None = None,
    candidate_outcome_callback: CandidateOutcomeCallback | None = None,
    precomputed_candidate_outcomes: (
        Mapping[int, ProvisionalCandidateOutcome] | None
    ) = None,
    candidate_generator_factory: CandidateGeneratorFactory | None = None,
    coverage_scheduler_factory: (
        CoverageAssignmentSchedulerFactory | None
    ) = None,
    coverage_recovery: tuple[CoverageAssignmentRecovery, ...] | None = None,
    policy_generator: PolicyGenerator | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
    refiner: Refiner | None = None,
    tool_proposal_generator: ToolProposalGenerator | None = None,
    admission_evaluator: CandidateAdmissionEvaluator = permit_candidate_execution,
    enable_branching: bool = False,
    enable_task_expansion: bool = False,
    task_expansion_generator: TaskExpansionGenerator | None = None,
    source_bundle: SourceBundle | None = None,
    enable_source_audit: bool = False,
    domain_environment_input: object | None = None,
    source_events: list[dict[str, object]] | None = None,
    enable_mcp_adapter: bool = False,
    enable_sandbox_fixture: bool = False,
    seed_override: DomainSeed | None = None,
    run_profile_metadata: dict[str, object] | None = None,
    run_profile: object | None = None,
    write_episode_logs: bool = False,
    mutation_judge_http_client: httpx.Client | None = None,
    mutation_judge_attempt_observer: SemanticJudgeAttemptObserver | None = None,
    max_concurrency: int = 1,
    cancellation_check: Callable[[], bool] | None = None,
) -> PipelineResult:
    max_concurrency = validate_concurrency(max_concurrency)

    def cancelled_artifact_status() -> str | None:
        if cancellation_check is not None and cancellation_check():
            return "cancelled"
        return None

    candidate_wave_hooks = _CandidateWaveHooks(
        start=candidate_start_callback,
        outcome=candidate_outcome_callback,
        precomputed=precomputed_candidate_outcomes,
        should_stop=cancellation_check,
    )
    run_profile_metadata = _authoritative_run_profile_metadata(
        run_profile,
        run_profile_metadata,
    )
    configured_generator_count = sum(
        item is not None
        for item in (
            candidate_generator,
            candidate_generator_factory,
            coverage_scheduler_factory,
        )
    )
    if configured_generator_count > 1:
        raise ValueError("candidate generator configurations are mutually exclusive")
    seed = seed_override or foundation_seed()
    coverage_variant = _selected_coverage_planning_variant(run_profile)
    representative_fixture = (
        domain_environment_input is None
        and coverage_variant is not None
        and coverage_variant.use_representative_fixture
    )
    source_event_records: list[dict[str, object]] = list(source_events or [])
    selected_source_bundle = source_bundle or build_domain_fixture_source_bundle(seed.domain)
    try:
        source_result = validate_source_bundle(selected_source_bundle)
    except SourcePolicyError as exc:
        if enable_source_audit:
            source_event_records.extend(exc.result.events)
        source_rejections = [
            assemble_source_policy_rejection(
                source_governance=exc.result.provenance,
                message=str(exc),
            )
        ]
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=[],
            rejections=source_rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=[],
            tool_proposals=[],
            source_events=source_event_records,
            run_profile_metadata=run_profile_metadata,
            orchestration_status=cancelled_artifact_status(),
        )
        return _pipeline_result(artifacts)
    if enable_source_audit:
        source_event_records.extend(source_result.events)

    source_provenance = dict(source_result.provenance)
    domain_bundle: DomainPipelineBundle | None = None
    domain_run: DomainLifecycleRun | None = None
    if domain_environment_input is not None:
        source_provenance["environment_source_admission"] = "accepted"
        try:
            domain_run = open_domain_run(
                seed,
                output_dir,
                source_bundle=selected_source_bundle,
                source_result=source_result,
                source_provenance=source_provenance,
                domain_environment_input=domain_environment_input,
                enable_mcp_adapter=enable_mcp_adapter,
                representative_fixture=representative_fixture,
            )
            if domain_run is None:
                domain_bundle = build_domain_pipeline_bundle(
                    seed,
                    output_dir / "environment",
                    source_provenance=source_provenance,
                    domain_environment_input=domain_environment_input,
                    enable_mcp_adapter=enable_mcp_adapter,
                    include_branching=enable_branching,
                    representative_fixture=representative_fixture,
                )
        except Exception as exc:
            rejected_provenance = dict(source_result.provenance)
            rejected_provenance["policy_outcome"] = "rejected"
            rejected_provenance["environment_source_admission"] = "rejected"
            rejected_provenance["rejection_causes"] = ["environment_source_rejected"]
            if enable_source_audit:
                source_event_records.append(
                    source_environment_admission_event(
                        event_type="environment_source_rejected",
                        source_bundle=selected_source_bundle,
                        source_policy_hash=source_result.source_policy_hash,
                        rejection_causes=["environment_source_rejected"],
                    )
                )
            source_rejections = [
                assemble_source_policy_rejection(
                    source_governance=rejected_provenance,
                    message=f"environment source rejected: {type(exc).__name__}",
                )
            ]
            artifacts = write_dataset_artifacts(
                output_dir=output_dir,
                dataset_version=dataset_version,
                samples=[],
                rejections=source_rejections,
                parent_artifact_path=parent_artifact_path,
                review_records=[],
                tool_proposals=[],
                source_events=source_event_records,
                run_profile_metadata=run_profile_metadata,
                orchestration_status=cancelled_artifact_status(),
            )
            return _pipeline_result(artifacts)
        if enable_source_audit:
            source_event_records.append(
                source_environment_admission_event(
                    event_type="environment_source_admitted",
                    source_bundle=selected_source_bundle,
                    source_policy_hash=source_result.source_policy_hash,
                    rejection_causes=[],
                )
            )
    else:
        domain_run = open_domain_run(
            seed,
            output_dir,
            source_bundle=selected_source_bundle,
            source_result=source_result,
            source_provenance=source_provenance,
            enable_mcp_adapter=enable_mcp_adapter,
            representative_fixture=representative_fixture,
        )
        if domain_run is None:
            domain_bundle = build_domain_pipeline_bundle(
                seed,
                output_dir / "environment",
                source_provenance=source_provenance,
                enable_mcp_adapter=enable_mcp_adapter,
                include_branching=enable_branching,
                representative_fixture=representative_fixture,
            )
    if domain_run is not None:
        generation_boundary: DomainGenerationBoundary = domain_run
    else:
        assert domain_bundle is not None
        generation_boundary = domain_bundle
    coverage_plan: CoveragePlan | None = None
    coverage_plan_path: Path | None = None
    coverage_scheduler: CoverageAssignmentScheduler | None = None
    coverage_reference = getattr(run_profile, "coverage_profile", None)
    generate_candidates: Callable[
        [DomainSeed],
        (
            list[CandidateTask]
            | DomainGenerationResult
        ),
    ] | None = None
    if coverage_reference is not None:
        if coverage_scheduler_factory is None:
            raise ValueError(
                "coverage-enabled execution requires a coverage assignment generator"
            )
        assert isinstance(run_profile, RunProfile)
        coverage_plan = preview_coverage_plan(
            run_profile,
            admitted_environment_input=domain_environment_input,
        )
        coverage_plan_path = write_coverage_plan(
            output_dir / "coverage_plan.json",
            coverage_plan,
        )
        planning = resolve_domain_coverage_planning(run_profile.seed.domain)
        catalog = planning.resolve_catalog(
            str(coverage_plan.catalog["version"])
        )
        coverage_scheduler = coverage_scheduler_factory(
            generation_boundary,
            coverage_plan,
            catalog,
        )
        if coverage_recovery is not None:
            coverage_scheduler.restore_assignments(coverage_recovery)
    elif candidate_generator_factory is not None:
        generate_candidates = candidate_generator_factory(generation_boundary)
    elif candidate_generator is None:
        if domain_run is not None:
            generate_candidates = domain_run.generate
        else:
            assert domain_bundle is not None
            generate_candidates = domain_bundle.candidate_generator
    else:
        generate_candidates = candidate_generator
    llm_config = LLMConfig.from_env()
    generate_task_expansion = task_expansion_generator or generate_deterministic_task_expansion
    generate_policy: PolicyGenerator | None
    if policy_generator is not None:
        generate_policy = policy_generator
    elif domain_bundle is not None:
        generate_policy = domain_bundle.policy_generator
    else:
        generate_policy = None
    selected_admission_evaluator = admission_evaluator
    if (
        admission_evaluator is permit_candidate_execution
        and getattr(run_profile, "schema_version", None) == "run_profile_v4"
    ):
        mutation_admission = getattr(run_profile, "mutation_admission", None)
        mode = getattr(mutation_admission, "mode", "disabled")
        if domain_run is not None:
            judge = domain_run.default_mutation_judge()
        else:
            assert domain_bundle is not None
            judge = domain_bundle.mutation_judge
        judge_config = getattr(mutation_admission, "judge", None)
        if judge_config is not None:
            provider_config = LLMConfig.from_env()
            judge = build_openai_compatible_semantic_mutation_judge(
                config=LLMConfig(
                    base_url=provider_config.base_url,
                    api_key=provider_config.api_key,
                    model=str(getattr(judge_config, "model")),
                    temperature=0.0,
                ),
                http_client=mutation_judge_http_client,
                timeout_seconds=float(
                    getattr(judge_config, "timeout_seconds")
                ),
                max_retries=int(getattr(judge_config, "max_retries")),
                attempt_observer=mutation_judge_attempt_observer,
            )
        if domain_run is not None:
            selected_admission_evaluator = domain_run.build_admission_evaluator(
                mode=mode,
                judge=judge,
            )
        else:
            assert domain_bundle is not None
            state_changing_tools = tuple(
                str(tool["name"])
                for tool in domain_bundle.registry.export()
                if tool.get("side_effects") == "state_mutating"
            )
            selected_admission_evaluator = build_local_candidate_admission_evaluator(
                mode=mode,
                policies=domain_bundle.mutation_policies,
                state_changing_tools=state_changing_tools,
                judge=judge,
            )
    candidate_context: CandidateProcessingContext | None = None
    if domain_bundle is not None:
        assert generate_policy is not None
        candidate_context = CandidateProcessingContext(
            dataset_version=dataset_version,
            environment=domain_bundle.environment,
            registry=domain_bundle.registry,
            adapter_shim=domain_bundle.adapter_shim,
            verifier=domain_bundle.verifier,
            llm_config=llm_config,
            generate_policy=generate_policy,
            admission_evaluator=selected_admission_evaluator,
        )
    candidate_options = CandidateProcessingOptions(
        route_reviewable_failures=route_reviewable_failures,
        refiner=refiner,
        tool_proposal_generator=tool_proposal_generator,
    )

    candidate_attempt_runner: CandidateAttemptRunner | None = None
    if domain_run is not None:
        def run_candidate_attempt(
            request: CandidateExecutionRequest,
            options: CandidateProcessingOptions,
        ) -> ProvisionalCandidateOutcome:
            return domain_run.attempt(
                request,
                dataset_version=dataset_version,
                llm_config=llm_config,
                policy_generator=generate_policy,
                admission_evaluator=selected_admission_evaluator,
                options=options,
            ).outcome

        candidate_attempt_runner = run_candidate_attempt

    def prepare_candidate_for_attempt(raw_task: CandidateTask) -> CandidateTask:
        if domain_run is not None:
            return raw_task
        assert domain_bundle is not None
        return domain_bundle.candidate_preparer(raw_task)

    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    episode_logs: list[dict[str, object]] = []
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]] = frozenset()
    coverage_reconciliation: Mapping[str, object] | None = None
    try:
        if domain_run is not None:
            gate_failure = domain_run.foundation_gate_failure()
            if gate_failure is not None:
                raise FoundationGateError(gate_failure)
        else:
            assert domain_bundle is not None
            _run_foundation_quality_gates(
                domain_bundle.domain_id,
                domain_bundle.environment,
                domain_bundle.registry,
            )
    except FoundationGateError as exc:
        rejections.append(assemble_pipeline_gate_rejection(error=exc))
        _attach_source_governance_to_rejections(rejections, source_provenance)
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=samples,
            rejections=rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=review_records,
            tool_proposals=tool_proposal_records,
            source_events=source_event_records,
            run_profile_metadata=run_profile_metadata,
            orchestration_status=cancelled_artifact_status(),
        )
        return _pipeline_result(artifacts)

    def finalize_pipeline(
        *,
        reconciliation: Mapping[str, object] | None = None,
        orchestration_status: str | None = None,
    ) -> PipelineResult:
        if orchestration_status is None:
            orchestration_status = cancelled_artifact_status()
        if reconciliation is None:
            reconciliation = coverage_reconciliation
        _attach_source_governance_to_rejections(rejections, source_provenance)
        sandbox_audits = (
            build_deterministic_sandbox_fixture(output_dir)
            if enable_sandbox_fixture
            else []
        )
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=samples,
            rejections=rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=review_records,
            tool_proposals=tool_proposal_records,
            source_events=source_event_records,
            sandbox_audits=sandbox_audits,
            run_profile_metadata=run_profile_metadata,
            coverage_plan=coverage_plan,
            coverage_reconciliation=reconciliation,
            orchestration_status=orchestration_status,
        )
        episode_logs_path = (
            write_episode_log_jsonl(output_dir / EPISODES_FILENAME, episode_logs)
            if write_episode_logs
            else None
        )
        return _pipeline_result(
            artifacts,
            episode_logs_path=episode_logs_path,
            coverage_plan_path=coverage_plan_path,
            coverage_reconciliation=reconciliation,
        )

    def partial_coverage_reconciliation(
        scheduler: CoverageAssignmentScheduler,
    ) -> Mapping[str, object]:
        reconciliation = dict(scheduler.reconciliation())
        raw_cells = reconciliation.get("cells")
        terminal_attempts = 0
        if isinstance(raw_cells, list):
            terminal_attempts = sum(
                int(isinstance(cell, Mapping))
                * (
                    int(cell.get("accepted", 0))
                    + int(cell.get("rejected", 0))
                )
                for cell in raw_cells
            )
        attempts = reconciliation.get("attempts")
        if isinstance(attempts, Mapping):
            normalized_attempts = dict(attempts)
            normalized_attempts["issued"] = terminal_attempts
            normalized_attempts["remaining"] = (
                int(normalized_attempts["ceiling"]) - terminal_attempts
            )
            reconciliation["attempts"] = normalized_attempts
        return reconciliation

    processed_candidate_count = 0
    if coverage_scheduler is not None:
        if cancellation_check is not None and cancellation_check():
            return finalize_pipeline(
                reconciliation=partial_coverage_reconciliation(coverage_scheduler),
                orchestration_status="cancelled",
            )
        if coverage_recovery is not None:
            for wave in sorted(
                {
                    recovery.wave
                    for recovery in coverage_recovery
                }
            ):
                try:
                    coverage_wave = coverage_scheduler.recover_wave(seed, wave)
                except PipelineCancellation:
                    return finalize_pipeline(
                        reconciliation=partial_coverage_reconciliation(
                            coverage_scheduler
                        ),
                        orchestration_status="cancelled",
                    )
                rejections.extend(coverage_wave.rejections)
                wave_tasks = [
                    prepare_candidate_for_attempt(raw_task)
                    for raw_task in coverage_wave.candidates
                ]
                assignments_by_id = {
                    assignment.assignment_id: assignment
                    for assignment in coverage_wave.assignments
                }
                wave_requests = [
                    CandidateExecutionRequest(
                        sequence_index=assignments_by_id[
                            coverage_wave.candidate_assignment_ids[
                                raw_task.candidate_id
                            ]
                        ].assignment_ordinal,
                        raw_task=task,
                    )
                    for raw_task, task in zip(
                        coverage_wave.candidates,
                        wave_tasks,
                        strict=True,
                    )
                ]
                try:
                    base_merge = _process_candidate_requests(
                        requests=wave_requests,
                        domain_bundle=domain_bundle,
                        candidate_context=candidate_context,
                        candidate_attempt_runner=candidate_attempt_runner,
                        candidate_options=candidate_options,
                        output_dir=output_dir,
                        enable_mcp_adapter=enable_mcp_adapter,
                        accepted_signatures=accepted_signatures,
                        route_reviewable_failures=route_reviewable_failures,
                        coverage_scheduler=coverage_scheduler,
                        max_concurrency=max_concurrency,
                        hooks=candidate_wave_hooks,
                    )
                except PipelineCancellation as exc:
                    if exc.merge is not None:
                        samples.extend(exc.merge.samples)
                        rejections.extend(exc.merge.rejections)
                        review_records.extend(exc.merge.review_records)
                        tool_proposal_records.extend(exc.merge.tool_proposal_records)
                        episode_logs.extend(exc.merge.episode_logs)
                        request_by_sequence = {
                            request.sequence_index: request
                            for request in wave_requests
                        }
                        coverage_scheduler.reconcile_wave(
                            coverage_wave,
                            accepted_candidate_ids={
                                request_by_sequence[index].raw_task.candidate_id
                                for index in exc.merge.accepted_sequence_indices
                            },
                            rejected_candidate_ids={
                                request_by_sequence[index].raw_task.candidate_id
                                for index in exc.merge.rejected_sequence_indices
                            },
                        )
                    return finalize_pipeline(
                        reconciliation=partial_coverage_reconciliation(
                            coverage_scheduler
                        ),
                        orchestration_status="cancelled",
                    )
                samples.extend(base_merge.samples)
                rejections.extend(base_merge.rejections)
                review_records.extend(base_merge.review_records)
                tool_proposal_records.extend(base_merge.tool_proposal_records)
                episode_logs.extend(base_merge.episode_logs)
                accepted_signatures = base_merge.accepted_signatures
                request_by_sequence = {
                    request.sequence_index: request
                    for request in wave_requests
                }
                coverage_scheduler.reconcile_wave(
                    coverage_wave,
                    accepted_candidate_ids={
                        request_by_sequence[index].raw_task.candidate_id
                        for index in base_merge.accepted_sequence_indices
                    },
                    rejected_candidate_ids={
                        request_by_sequence[index].raw_task.candidate_id
                        for index in base_merge.rejected_sequence_indices
                    },
                )
                processed_candidate_count = coverage_scheduler.issued_count
        while coverage_scheduler.can_schedule:
            if cancellation_check is not None and cancellation_check():
                return finalize_pipeline(
                    reconciliation=partial_coverage_reconciliation(
                        coverage_scheduler
                    ),
                    orchestration_status="cancelled",
                )
            try:
                coverage_wave = coverage_scheduler.generate_wave(seed)
            except PipelineCancellation:
                return finalize_pipeline(
                    reconciliation=partial_coverage_reconciliation(
                        coverage_scheduler
                    ),
                    orchestration_status="cancelled",
                )
            rejections.extend(coverage_wave.rejections)
            wave_tasks = [
                prepare_candidate_for_attempt(raw_task)
                for raw_task in coverage_wave.candidates
            ]
            assignments_by_id = {
                assignment.assignment_id: assignment
                for assignment in coverage_wave.assignments
            }
            wave_requests = [
                CandidateExecutionRequest(
                    sequence_index=assignments_by_id[
                        coverage_wave.candidate_assignment_ids[
                            raw_task.candidate_id
                        ]
                    ].assignment_ordinal,
                    raw_task=task,
                )
                for raw_task, task in zip(
                    coverage_wave.candidates,
                    wave_tasks,
                    strict=True,
                )
            ]
            try:
                base_merge = _process_candidate_requests(
                    requests=wave_requests,
                    domain_bundle=domain_bundle,
                    candidate_context=candidate_context,
                    candidate_attempt_runner=candidate_attempt_runner,
                    candidate_options=candidate_options,
                    output_dir=output_dir,
                    enable_mcp_adapter=enable_mcp_adapter,
                    accepted_signatures=accepted_signatures,
                    route_reviewable_failures=route_reviewable_failures,
                    coverage_scheduler=coverage_scheduler,
                    max_concurrency=max_concurrency,
                    hooks=candidate_wave_hooks,
                )
            except PipelineCancellation as exc:
                if exc.merge is not None:
                    samples.extend(exc.merge.samples)
                    rejections.extend(exc.merge.rejections)
                    review_records.extend(exc.merge.review_records)
                    tool_proposal_records.extend(exc.merge.tool_proposal_records)
                    episode_logs.extend(exc.merge.episode_logs)
                    request_by_sequence = {
                        request.sequence_index: request
                        for request in wave_requests
                    }
                    coverage_scheduler.reconcile_wave(
                        coverage_wave,
                        accepted_candidate_ids={
                            request_by_sequence[index].raw_task.candidate_id
                            for index in exc.merge.accepted_sequence_indices
                        },
                        rejected_candidate_ids={
                            request_by_sequence[index].raw_task.candidate_id
                            for index in exc.merge.rejected_sequence_indices
                        },
                    )
                return finalize_pipeline(
                    reconciliation=partial_coverage_reconciliation(
                        coverage_scheduler
                    ),
                    orchestration_status="cancelled",
                )
            samples.extend(base_merge.samples)
            rejections.extend(base_merge.rejections)
            review_records.extend(base_merge.review_records)
            tool_proposal_records.extend(base_merge.tool_proposal_records)
            episode_logs.extend(base_merge.episode_logs)
            accepted_signatures = base_merge.accepted_signatures
            request_by_sequence = {
                request.sequence_index: request
                for request in wave_requests
            }
            coverage_scheduler.reconcile_wave(
                coverage_wave,
                accepted_candidate_ids={
                    request_by_sequence[index].raw_task.candidate_id
                    for index in base_merge.accepted_sequence_indices
                },
                rejected_candidate_ids={
                    request_by_sequence[index].raw_task.candidate_id
                    for index in base_merge.rejected_sequence_indices
                },
            )
            processed_candidate_count = coverage_scheduler.issued_count
        coverage_reconciliation = coverage_scheduler.reconciliation()
    else:
        assert generate_candidates is not None
        try:
            if cancellation_check is not None and cancellation_check():
                return finalize_pipeline(orchestration_status="cancelled")
            generation_result = generate_candidates(seed)
            if isinstance(generation_result, DomainGenerationResult):
                base_tasks = list(generation_result.candidates)
                run_profile_metadata = dict(run_profile_metadata or {})
                run_profile_metadata["generation_contract"] = build_generation_contract_evidence(
                    profile=run_profile,
                    spec_metadata=generation_result.spec_metadata,
                    target_candidate_count=generation_result.target_candidate_count,
                    generated_candidate_count=generation_result.generated_candidate_count,
                )
            else:
                base_tasks = generation_result
            if candidate_set_callback is not None:
                candidate_set_callback(tuple(base_tasks))
            if cancellation_check is not None and cancellation_check():
                return finalize_pipeline(orchestration_status="cancelled")
            base_tasks = [
                prepare_candidate_for_attempt(raw_task)
                for raw_task in base_tasks
            ]
        except PipelineCancellation:
            return finalize_pipeline(orchestration_status="cancelled")
        except LLMProviderError as exc:
            if getattr(exc, "ambiguous", False):
                raise
            rejections.append(assemble_generation_stage_rejection(error=exc))
            _attach_source_governance_to_rejections(rejections, source_provenance)
            artifacts = write_dataset_artifacts(
                output_dir=output_dir,
                dataset_version=dataset_version,
                samples=samples,
                rejections=rejections,
                parent_artifact_path=parent_artifact_path,
                review_records=review_records,
                tool_proposals=tool_proposal_records,
                source_events=source_event_records,
                run_profile_metadata=run_profile_metadata,
                orchestration_status=cancelled_artifact_status(),
            )
            return _pipeline_result(artifacts)

        try:
            base_merge = _process_candidate_wave(
                raw_tasks=base_tasks,
                start_index=0,
                domain_bundle=domain_bundle,
                candidate_context=candidate_context,
                candidate_attempt_runner=candidate_attempt_runner,
                candidate_options=candidate_options,
                output_dir=output_dir,
                enable_mcp_adapter=enable_mcp_adapter,
                accepted_signatures=accepted_signatures,
                route_reviewable_failures=route_reviewable_failures,
                max_concurrency=max_concurrency,
                hooks=candidate_wave_hooks,
            )
        except PipelineCancellation as exc:
            if exc.merge is not None:
                samples.extend(exc.merge.samples)
                rejections.extend(exc.merge.rejections)
                review_records.extend(exc.merge.review_records)
                tool_proposal_records.extend(exc.merge.tool_proposal_records)
                episode_logs.extend(exc.merge.episode_logs)
            return finalize_pipeline(orchestration_status="cancelled")
        samples.extend(base_merge.samples)
        rejections.extend(base_merge.rejections)
        review_records.extend(base_merge.review_records)
        tool_proposal_records.extend(base_merge.tool_proposal_records)
        episode_logs.extend(base_merge.episode_logs)
        accepted_signatures = base_merge.accepted_signatures
        processed_candidate_count = len(base_tasks)

    if enable_task_expansion:
        if cancellation_check is not None and cancellation_check():
            return finalize_pipeline(orchestration_status="cancelled")
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
        expanded_outcomes = []
        start_index = processed_candidate_count
        for offset, expanded_task in enumerate(expansion.candidates):
            expanded_task = prepare_candidate_for_attempt(expanded_task)
            request = CandidateExecutionRequest(
                sequence_index=start_index + offset,
                raw_task=expanded_task,
            )
            if candidate_attempt_runner is not None:
                outcome = candidate_attempt_runner(request, candidate_options)
            else:
                assert domain_bundle is not None
                assert candidate_context is not None
                outcome = process_candidate_through_gates(
                    request=request,
                    context=_candidate_context_for_request(
                        base_bundle=domain_bundle,
                        base_context=candidate_context,
                        output_dir=output_dir,
                        request=request,
                        enable_mcp_adapter=enable_mcp_adapter,
                    ),
                    options=candidate_options,
                )
            expanded_outcomes.append(outcome)
        expanded_merge = merge_candidate_outcomes(
            tuple(expanded_outcomes),
            initial_accepted_signatures=accepted_signatures,
            route_reviewable_failures=route_reviewable_failures,
        )
        samples.extend(expanded_merge.samples)
        rejections.extend(expanded_merge.rejections)
        review_records.extend(expanded_merge.review_records)
        tool_proposal_records.extend(expanded_merge.tool_proposal_records)
        episode_logs.extend(expanded_merge.episode_logs)
        accepted_signatures = expanded_merge.accepted_signatures

    if cancellation_check is not None and cancellation_check():
        return finalize_pipeline(orchestration_status="cancelled")
    return finalize_pipeline()


def _selected_coverage_planning_variant(
    run_profile: object | None,
) -> DomainCoveragePlanningVariant | None:
    if not isinstance(run_profile, RunProfile):
        return None
    coverage_reference = run_profile.coverage_profile
    if coverage_reference is None:
        return None
    planning = resolve_domain_coverage_planning(run_profile.seed.domain)
    coverage_profile = planning.resolve_profile(
        coverage_reference.profile_id,
        coverage_reference.version,
    )
    return planning.resolve_variant(coverage_profile.catalog_version)


def _authoritative_run_profile_metadata(
    run_profile: object | None,
    supplied_metadata: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(run_profile, RunProfile):
        return supplied_metadata
    if run_profile.coverage_profile is None:
        return supplied_metadata
    authoritative = run_profile.sanitized_metadata()
    if supplied_metadata is None:
        return authoritative
    for key, expected in authoritative.items():
        supplied = supplied_metadata.get(key)
        if (
            key == "mutation_admission"
            and isinstance(expected, Mapping)
            and isinstance(supplied, Mapping)
        ):
            matches = all(
                supplied.get(field) == value
                for field, value in expected.items()
            )
        else:
            matches = supplied == expected
        if not matches:
            raise ValueError(
                "run_profile_metadata must match the authoritative run profile"
            )
    unexpected = set(supplied_metadata) - set(authoritative) - {"source"}
    if unexpected:
        raise ValueError(
            "run_profile_metadata contains unsupported attribution fields"
        )
    return dict(supplied_metadata)


def _pipeline_result(
    artifacts: DatasetArtifacts,
    *,
    episode_logs_path: Path | None = None,
    coverage_plan_path: Path | None = None,
    coverage_reconciliation: Mapping[str, object] | None = None,
) -> PipelineResult:
    if coverage_plan_path is not None:
        attach_coverage_plan_to_manifest(
            manifest_path=artifacts.manifest_path,
            plan_path=coverage_plan_path,
        )
    return PipelineResult(
        samples_path=artifacts.samples_path,
        manifest_path=artifacts.manifest_path,
        rejections_path=artifacts.rejections_path,
        quality_report_path=artifacts.quality_report_path,
        tool_proposals_path=artifacts.tool_proposals_path,
        source_events_path=artifacts.source_events_path,
        sandbox_audits_path=artifacts.sandbox_audits_path,
        parent_comparison_path=artifacts.parent_comparison_path,
        review_queue_path=artifacts.review_queue_path,
        mutation_admission_report_path=artifacts.mutation_admission_report_path,
        coverage_evidence_path=artifacts.coverage_evidence_path,
        episode_logs_path=episode_logs_path,
        accepted_count=artifacts.accepted_count,
        rejected_count=artifacts.rejected_count,
        coverage_plan_path=coverage_plan_path,
        coverage_reconciliation=coverage_reconciliation,
    )


def _process_candidate_wave(
    *,
    raw_tasks: list[CandidateTask],
    start_index: int,
    domain_bundle: DomainPipelineBundle | None,
    candidate_context: CandidateProcessingContext | None,
    candidate_attempt_runner: CandidateAttemptRunner | None,
    candidate_options: CandidateProcessingOptions,
    output_dir: Path,
    enable_mcp_adapter: bool,
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]],
    route_reviewable_failures: bool,
    coverage_scheduler: CoverageAssignmentScheduler | None = None,
    max_concurrency: int = 1,
    hooks: _CandidateWaveHooks | None = None,
) -> CandidateMergeResult:
    requests = [
        CandidateExecutionRequest(
            sequence_index=start_index + offset,
            raw_task=raw_task,
        )
        for offset, raw_task in enumerate(raw_tasks)
    ]
    return _process_candidate_requests(
        requests=requests,
        domain_bundle=domain_bundle,
        candidate_context=candidate_context,
        candidate_attempt_runner=candidate_attempt_runner,
        candidate_options=candidate_options,
        output_dir=output_dir,
        enable_mcp_adapter=enable_mcp_adapter,
        accepted_signatures=accepted_signatures,
        route_reviewable_failures=route_reviewable_failures,
        coverage_scheduler=coverage_scheduler,
        max_concurrency=max_concurrency,
        hooks=hooks,
    )


def _process_candidate_requests(
    *,
    requests: list[CandidateExecutionRequest],
    domain_bundle: DomainPipelineBundle | None,
    candidate_context: CandidateProcessingContext | None,
    candidate_attempt_runner: CandidateAttemptRunner | None,
    candidate_options: CandidateProcessingOptions,
    output_dir: Path,
    enable_mcp_adapter: bool,
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]],
    route_reviewable_failures: bool,
    coverage_scheduler: CoverageAssignmentScheduler | None = None,
    max_concurrency: int = 1,
    hooks: _CandidateWaveHooks | None = None,
) -> CandidateMergeResult:
    max_concurrency = validate_concurrency(max_concurrency)
    hooks = hooks or _CandidateWaveHooks()
    precomputed = hooks.precomputed or {}
    outcomes: list[ProvisionalCandidateOutcome] = []

    def process_request(request: CandidateExecutionRequest) -> ProvisionalCandidateOutcome:
        outcome = precomputed.get(request.sequence_index)
        if outcome is None:
            if hooks.should_stop is not None and hooks.should_stop():
                raise PipelineCancellation()
            if hooks.start is not None:
                hooks.start(request)
            request_options = candidate_options
            if coverage_scheduler is not None:
                request_options = replace(
                    candidate_options,
                    refined_candidate_validator=_coverage_refined_candidate_validator(
                        coverage_scheduler,
                        request.raw_task.candidate_id,
                    ),
                )
            if candidate_attempt_runner is not None:
                outcome = candidate_attempt_runner(request, request_options)
            else:
                assert domain_bundle is not None
                assert candidate_context is not None
                outcome = process_candidate_through_gates(
                    request=request,
                    context=_candidate_context_for_request(
                        base_bundle=domain_bundle,
                        base_context=candidate_context,
                        output_dir=output_dir,
                        request=request,
                        enable_mcp_adapter=enable_mcp_adapter,
                    ),
                    options=request_options,
                )
            if hooks.outcome is not None:
                if hooks.should_stop is None or not hooks.should_stop():
                    hooks.outcome(request, outcome)
            if hooks.should_stop is not None and hooks.should_stop():
                raise PipelineCancellation()
        return outcome

    cancellation_requested = False
    if max_concurrency == 1:
        for request in requests:
            try:
                outcomes.append(process_request(request))
            except PipelineCancellation:
                cancellation_requested = True
                break
    else:
        pending: dict[
            Future[ProvisionalCandidateOutcome], CandidateExecutionRequest
        ] = {}
        request_iterator = iter(requests)

        def submit_next() -> bool:
            try:
                request = next(request_iterator)
            except StopIteration:
                return False
            pending[executor.submit(process_request, request)] = request
            return True

        failure: BaseException | None = None

        def collect(future: Future[ProvisionalCandidateOutcome]) -> None:
            nonlocal cancellation_requested, failure
            try:
                outcomes.append(future.result())
            except PipelineCancellation:
                cancellation_requested = True
            except BaseException as exc:
                if cancellation_requested or (
                    hooks.should_stop is not None and hooks.should_stop()
                ):
                    cancellation_requested = True
                else:
                    failure = exc

        executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="synthesis-candidate",
        )
        try:
            if hooks.should_stop is not None and hooks.should_stop():
                cancellation_requested = True
            else:
                for _ in range(min(max_concurrency, len(requests))):
                    submit_next()
            while pending and failure is None:
                done, _ = wait(
                    tuple(pending),
                    timeout=CANCELLATION_POLL_INTERVAL_SECONDS,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    if hooks.should_stop is not None and hooks.should_stop():
                        cancellation_requested = True
                    else:
                        continue
                for future in done:
                    pending.pop(future)
                    collect(future)
                    if failure is not None or cancellation_requested:
                        break
                    if hooks.should_stop is not None and hooks.should_stop():
                        cancellation_requested = True
                        break
                    submit_next()
                if failure is not None or cancellation_requested:
                    for future in pending:
                        future.cancel()
                    if pending:
                        done, _ = wait(
                            tuple(pending),
                            timeout=CANCELLATION_DRAIN_TIMEOUT_SECONDS,
                        )
                        for future in done:
                            pending.pop(future)
                            if future.cancelled():
                                continue
                            collect(future)
                    break
            if failure is not None:
                raise failure
        finally:
            if cancellation_requested:
                # Do not wait for a provider or user callback that ignored the
                # cooperative signal. Its orchestration callbacks check the
                # same signal before recording any late result; the durable
                # runner records unfinished items as interrupted.
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

    merged = merge_candidate_outcomes(
        tuple(outcomes),
        initial_accepted_signatures=accepted_signatures,
        route_reviewable_failures=route_reviewable_failures,
    )
    if cancellation_requested:
        raise PipelineCancellation(merged)
    return merged


def _original_candidate_ids_for_indices(
    tasks: list[CandidateTask],
    *,
    start_index: int,
    sequence_indices: tuple[int, ...],
) -> set[str]:
    return {
        tasks[sequence_index - start_index].candidate_id
        for sequence_index in sequence_indices
    }


def _coverage_refined_candidate_validator(
    scheduler: CoverageAssignmentScheduler,
    original_candidate_id: str,
) -> Callable[[CandidateTask], dict[str, object] | None]:
    def validate(candidate: CandidateTask) -> dict[str, object] | None:
        return scheduler.validate_refined_candidate(
            original_candidate_id,
            candidate,
        )

    return validate


def _candidate_context_for_request(
    *,
    base_bundle: DomainPipelineBundle,
    base_context: CandidateProcessingContext,
    output_dir: Path,
    request: CandidateExecutionRequest,
    enable_mcp_adapter: bool,
) -> CandidateProcessingContext:
    candidate_id = getattr(request.raw_task, "candidate_id", "unknown_candidate")
    candidate_bundle = rebuild_domain_pipeline_bundle(
        base_bundle,
        output_dir
        / "candidate-environments"
        / f"{request.sequence_index:04d}-{_path_safe_candidate_id(str(candidate_id))}",
        enable_mcp_adapter=enable_mcp_adapter,
    )
    return CandidateProcessingContext(
        dataset_version=base_context.dataset_version,
        environment=candidate_bundle.environment,
        registry=candidate_bundle.registry,
        adapter_shim=candidate_bundle.adapter_shim,
        verifier=base_context.verifier,
        llm_config=base_context.llm_config,
        generate_policy=base_context.generate_policy,
        admission_evaluator=base_context.admission_evaluator,
        membership_validator=base_context.membership_validator,
    )


def _path_safe_candidate_id(candidate_id: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in candidate_id
    )[:80] or "unknown_candidate"


def _attach_source_governance_to_rejections(
    rejections: list[dict[str, object]],
    source_provenance: dict[str, object],
) -> None:
    for rejection in rejections:
        details = rejection.get("details")
        if not isinstance(details, dict):
            continue
        source_kinds = source_provenance.get("source_kinds")
        if isinstance(source_kinds, list) and "local_file" in source_kinds:
            redacted_details = _redact_source_payload_values(details)
            if isinstance(redacted_details, dict):
                details.update(redacted_details)
        details.setdefault("source_governance", dict(source_provenance))


def _redact_source_payload_values(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _redact_source_payload_values(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_source_payload_values(item) for item in value]
    if isinstance(value, str) and "@" in value:
        return "<redacted_source_payload_value>"
    return value


def _run_foundation_quality_gates(
    domain_id: str,
    environment: FoundationEnvironment,
    registry: ToolRegistry,
) -> None:
    metadata = environment.metadata()
    if not metadata.environment_id or not metadata.version or not metadata.reset_recipe:
        raise FoundationGateError("environment reset metadata is incomplete")

    tools = registry.export()
    if not tools:
        raise FoundationGateError("registered tool smoke check found no tools")
    names = {str(tool.get("name")) for tool in tools}
    if domain_id == "contacts_fixture":
        if "lookup_contact_email" not in names:
            raise FoundationGateError("lookup_contact_email is not registered")
        try:
            result = registry.execute("lookup_contact_email", {"name": "Alice Zhang"})
        except Exception as exc:
            raise FoundationGateError(f"lookup_contact_email smoke check failed: {exc}") from exc
        if result.get("email") != "alice.zhang@example.test":
            raise FoundationGateError("lookup_contact_email smoke check returned unexpected data")
        return
    if domain_id == "mobile_messages_fixture":
        if "search_phone_messages" not in names:
            raise FoundationGateError("search_phone_messages is not registered")
        try:
            result = registry.execute(
                "search_phone_messages",
                {"query": "project update", "participant": "Maya"},
            )
        except Exception as exc:
            raise FoundationGateError(f"search_phone_messages smoke check failed: {exc}") from exc
        if result.get("message_id") != "msg_maya_project_update":
            raise FoundationGateError("search_phone_messages smoke check returned unexpected data")
        return
    raise FoundationGateError(f"unsupported pipeline domain: {domain_id}")
