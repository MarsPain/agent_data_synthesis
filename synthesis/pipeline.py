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
    assemble_sample,
    attach_refinement_to_rejection,
    write_dataset_artifacts,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import PolicyValidationError, SolutionPolicy, execute_candidate, scripted_solution_policy
from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient
from synthesis.quality import (
    build_review_record,
    candidate_duplicate_signature,
    final_answer_is_logically_supported,
    reviewable,
)
from synthesis.refinement import Refiner, RefinementAttempt, RefinementContext, repairable
from synthesis.refinement import generate_llm_backed_refinement
from synthesis.roles import TASK_GENERATION_ROLE, RoleRegistry, default_role_registry
from synthesis.seeds import foundation_seed
from synthesis.seeds import DomainSeed
from synthesis.tasks import (
    CandidateTask,
    generate_foundation_candidates,
    generate_llm_backed_candidates,
)
from synthesis.tools import (
    ToolMissingError,
    ToolRegistry,
    ToolSchemaError,
    build_contact_tool_registry,
)
from synthesis.verification import ExactAnswerVerifier


@dataclass(frozen=True)
class PipelineResult:
    samples_path: Path
    manifest_path: Path
    rejections_path: Path
    quality_report_path: Path
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


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]


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


def run_foundation_pipeline(
    output_dir: Path,
    *,
    dataset_version: str = "dataset_foundation_v1",
    candidate_generator: CandidateGenerator | None = None,
    policy_generator: PolicyGenerator | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
    refiner: Refiner | None = None,
) -> PipelineResult:
    seed = foundation_seed()
    environment = ContactEnvironment.create_fixture(output_dir / "environment")
    registry = build_contact_tool_registry(environment)
    verifier = ExactAnswerVerifier()
    llm_config = LLMConfig.from_env()
    generate_candidates = candidate_generator or generate_foundation_candidates
    generate_policy = policy_generator or scripted_solution_policy

    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
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
        )
        return PipelineResult(
            samples_path=artifacts.samples_path,
            manifest_path=artifacts.manifest_path,
            rejections_path=artifacts.rejections_path,
            quality_report_path=artifacts.quality_report_path,
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
        )
        return PipelineResult(
            samples_path=artifacts.samples_path,
            manifest_path=artifacts.manifest_path,
            rejections_path=artifacts.rejections_path,
            quality_report_path=artifacts.quality_report_path,
            parent_comparison_path=artifacts.parent_comparison_path,
            review_queue_path=artifacts.review_queue_path,
            accepted_count=artifacts.accepted_count,
            rejected_count=artifacts.rejected_count,
        )

    for raw_task in raw_tasks:
        try:
            task = validate_candidate_task(raw_task)
        except ContractValidationError as exc:
            rejections.append(assemble_candidate_schema_rejection(error=exc))
            continue
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
        if attempt_result.sample is not None:
            assert attempt_result.signature is not None
            accepted_signatures.add(attempt_result.signature)
            samples.append(attempt_result.sample)
            continue

        assert attempt_result.rejection is not None
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
            continue
        if refinement_attempt is None:
            rejections.append(attempt_result.rejection)
            _maybe_route_review(
                review_records,
                attempt_result.rejection,
                route_reviewable_failures=route_reviewable_failures,
            )
            continue

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
        if refined_result.sample is not None:
            assert refined_result.signature is not None
            accepted_signatures.add(refined_result.signature)
            samples.append(refined_result.sample)
            continue

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

    artifacts = write_dataset_artifacts(
        output_dir=output_dir,
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
        parent_artifact_path=parent_artifact_path,
        review_records=review_records,
    )
    return PipelineResult(
        samples_path=artifacts.samples_path,
        manifest_path=artifacts.manifest_path,
        rejections_path=artifacts.rejections_path,
        quality_report_path=artifacts.quality_report_path,
        parent_comparison_path=artifacts.parent_comparison_path,
        review_queue_path=artifacts.review_queue_path,
        accepted_count=artifacts.accepted_count,
        rejected_count=artifacts.rejected_count,
    )


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
            )
    try:
        execution = execute_candidate(task, registry, policy=policy)
    except ToolMissingError as exc:
        return CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(
                task=task,
                error=exc,
                cause="tool_missing",
                policy=policy,
            ),
            signature=None,
            policy=policy,
        )
    except ToolSchemaError as exc:
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
        )
    except Exception as exc:
        return CandidateAttemptResult(
            sample=None,
            rejection=assemble_execution_rejection(task=task, error=exc, policy=policy),
            signature=None,
            policy=policy,
        )

    verification = verifier.verify(task, execution, environment=environment)
    if not verification.passed:
        return CandidateAttemptResult(
            sample=None,
            rejection=assemble_rejection(task=task, verification=verification, policy=policy),
            signature=None,
            policy=policy,
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
        )
    return CandidateAttemptResult(
        sample=sample,
        rejection=None,
        signature=signature,
        policy=policy,
    )


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


def _ensure_generation_lineage(task: CandidateTask, llm_config: LLMConfig) -> CandidateTask:
    if task.generation_lineage:
        return task
    lineage = llm_config.lineage(TASK_GENERATION_ROLE)
    lineage.update(default_role_registry().require_enabled(TASK_GENERATION_ROLE).lineage_metadata())
    return replace(task, generation_lineage=lineage)


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
