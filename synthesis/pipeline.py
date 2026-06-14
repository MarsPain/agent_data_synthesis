from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    CandidateProcessingContext,
    CandidateProcessingOptions,
    PolicyGenerator,
    ToolProposalGenerator,
    _maybe_route_review,
    merge_candidate_outcomes,
    process_candidate_through_gates,
)
from synthesis.datasets import (
    assemble_generation_stage_rejection,
    assemble_pipeline_gate_rejection,
    assemble_source_policy_rejection,
    assemble_task_editor_rejection,
    assemble_task_suggestion_rejection,
    write_dataset_artifacts,
)
from synthesis.episode_quality import EPISODES_FILENAME, write_episode_logs as write_episode_log_jsonl
from synthesis.domain_pipeline import (
    DomainPipelineBundle,
    build_domain_pipeline_bundle,
    rebuild_domain_pipeline_bundle,
)
from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient
from synthesis.refinement import Refiner, RefinementAttempt, RefinementContext
from synthesis.refinement import generate_llm_backed_refinement
from synthesis.roles import RoleRegistry, default_role_registry
from synthesis.sandbox import build_deterministic_sandbox_fixture
from synthesis.seeds import foundation_seed
from synthesis.seeds import DomainSeed
from synthesis.seeds import deterministic_seed_transformations
from synthesis.sources import (
    SourceBundle,
    SourcePolicyError,
    build_fixture_source_bundle,
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
    episode_logs_path: Path | None
    accepted_count: int
    rejected_count: int


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
TaskExpansionGenerator = Callable[[DomainSeed], TaskExpansionResult]


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
    source_bundle: SourceBundle | None = None,
    enable_source_audit: bool = False,
    domain_environment_input: object | None = None,
    source_events: list[dict[str, object]] | None = None,
    enable_mcp_adapter: bool = False,
    enable_sandbox_fixture: bool = False,
    seed_override: DomainSeed | None = None,
    run_profile_metadata: dict[str, object] | None = None,
    write_episode_logs: bool = False,
) -> PipelineResult:
    seed = seed_override or foundation_seed()
    source_event_records: list[dict[str, object]] = list(source_events or [])
    selected_source_bundle = source_bundle or build_fixture_source_bundle()
    try:
        source_result = validate_source_bundle(selected_source_bundle)
    except SourcePolicyError as exc:
        if enable_source_audit:
            source_event_records.extend(exc.result.events)
        rejections = [
            assemble_source_policy_rejection(
                source_governance=exc.result.provenance,
                message=str(exc),
            )
        ]
        artifacts = write_dataset_artifacts(
            output_dir=output_dir,
            dataset_version=dataset_version,
            samples=[],
            rejections=rejections,
            parent_artifact_path=parent_artifact_path,
            review_records=[],
            tool_proposals=[],
            source_events=source_event_records,
            run_profile_metadata=run_profile_metadata,
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
            episode_logs_path=None,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )
    if enable_source_audit:
        source_event_records.extend(source_result.events)

    source_provenance = dict(source_result.provenance)
    if domain_environment_input is not None:
        source_provenance["environment_source_admission"] = "accepted"
        try:
            domain_bundle = build_domain_pipeline_bundle(
                seed,
                output_dir / "environment",
                source_provenance=source_provenance,
                domain_environment_input=domain_environment_input,
                enable_mcp_adapter=enable_mcp_adapter,
                include_branching=enable_branching,
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
            rejections = [
                assemble_source_policy_rejection(
                    source_governance=rejected_provenance,
                    message=f"environment source rejected: {type(exc).__name__}",
                )
            ]
            artifacts = write_dataset_artifacts(
                output_dir=output_dir,
                dataset_version=dataset_version,
                samples=[],
                rejections=rejections,
                parent_artifact_path=parent_artifact_path,
                review_records=[],
                tool_proposals=[],
                source_events=source_event_records,
                run_profile_metadata=run_profile_metadata,
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
                episode_logs_path=None,
                accepted_count=artifacts.accepted_count,
                rejected_count=artifacts.rejected_count,
            )
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
        domain_bundle = build_domain_pipeline_bundle(
            seed,
            output_dir / "environment",
            source_provenance=source_provenance,
            enable_mcp_adapter=enable_mcp_adapter,
            include_branching=enable_branching,
        )
    environment = domain_bundle.environment
    registry = domain_bundle.registry
    verifier = domain_bundle.verifier
    llm_config = LLMConfig.from_env()
    if candidate_generator is None:
        generate_candidates = domain_bundle.candidate_generator
    else:
        generate_candidates = candidate_generator
    generate_task_expansion = task_expansion_generator or generate_deterministic_task_expansion
    generate_policy = policy_generator or domain_bundle.policy_generator
    candidate_context = CandidateProcessingContext(
        dataset_version=dataset_version,
        environment=environment,
        registry=registry,
        adapter_shim=domain_bundle.adapter_shim,
        verifier=verifier,
        llm_config=llm_config,
        generate_policy=generate_policy,
    )
    candidate_options = CandidateProcessingOptions(
        route_reviewable_failures=route_reviewable_failures,
        refiner=refiner,
        tool_proposal_generator=tool_proposal_generator,
    )

    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    tool_proposal_records: list[dict[str, object]] = []
    episode_logs: list[dict[str, object]] = []
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]] = frozenset()
    try:
        _run_foundation_quality_gates(domain_bundle.domain_id, environment, registry)
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
            episode_logs_path=None,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )

    try:
        raw_tasks = generate_candidates(seed)
    except LLMProviderError as exc:
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
            episode_logs_path=None,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )

    base_outcomes = []
    for sequence_index, raw_task in enumerate(raw_tasks):
        request = CandidateExecutionRequest(
            sequence_index=sequence_index,
            raw_task=raw_task,
        )
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
        base_outcomes.append(outcome)

    base_merge = merge_candidate_outcomes(
        tuple(base_outcomes),
        route_reviewable_failures=route_reviewable_failures,
    )
    samples.extend(base_merge.samples)
    rejections.extend(base_merge.rejections)
    review_records.extend(base_merge.review_records)
    tool_proposal_records.extend(base_merge.tool_proposal_records)
    episode_logs.extend(base_merge.episode_logs)
    accepted_signatures = base_merge.accepted_signatures

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
        expanded_outcomes = []
        start_index = len(raw_tasks)
        for offset, expanded_task in enumerate(expansion.candidates):
            request = CandidateExecutionRequest(
                sequence_index=start_index + offset,
                raw_task=expanded_task,
            )
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
    )
    episode_logs_path = (
        write_episode_log_jsonl(output_dir / EPISODES_FILENAME, episode_logs)
        if write_episode_logs
        else None
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
        episode_logs_path=episode_logs_path,
        accepted_count=artifacts.accepted_count,
        rejected_count=artifacts.rejected_count,
    )


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
        if "local_file" in source_provenance.get("source_kinds", []):
            details.update(_redact_source_payload_values(details))
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
    environment: object,
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
