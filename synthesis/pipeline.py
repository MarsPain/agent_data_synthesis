from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from synthesis.contracts import ContractValidationError, validate_candidate_task
from synthesis.datasets import (
    assemble_candidate_schema_rejection,
    assemble_execution_rejection,
    assemble_pipeline_gate_rejection,
    assemble_quality_gate_rejection,
    assemble_rejection,
    assemble_sample,
    write_dataset_artifacts,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import execute_candidate
from synthesis.llm import LLMConfig, OpenAICompatibleClient
from synthesis.quality import (
    build_review_record,
    candidate_duplicate_signature,
    final_answer_is_logically_supported,
    reviewable,
)
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


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]


class FoundationGateError(RuntimeError):
    pass


def build_llm_candidate_generator(http_client: httpx.Client | None = None) -> CandidateGenerator:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    return lambda seed: generate_llm_backed_candidates(seed, client)


def run_foundation_pipeline(
    output_dir: Path,
    *,
    dataset_version: str = "dataset_foundation_v1",
    candidate_generator: CandidateGenerator | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
) -> PipelineResult:
    seed = foundation_seed()
    environment = ContactEnvironment.create_fixture(output_dir / "environment")
    registry = build_contact_tool_registry(environment)
    verifier = ExactAnswerVerifier()
    llm_config = LLMConfig.from_env()
    generate_candidates = candidate_generator or generate_foundation_candidates

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

    for raw_task in generate_candidates(seed):
        try:
            task = validate_candidate_task(raw_task)
        except ContractValidationError as exc:
            rejections.append(assemble_candidate_schema_rejection(error=exc))
            continue
        try:
            execution = execute_candidate(task, registry)
        except ToolMissingError as exc:
            rejections.append(
                assemble_execution_rejection(task=task, error=exc, cause="tool_missing")
            )
            continue
        except ToolSchemaError as exc:
            rejections.append(
                assemble_execution_rejection(task=task, error=exc, cause="tool_schema_error")
            )
            continue
        except Exception as exc:
            rejections.append(assemble_execution_rejection(task=task, error=exc))
            continue
        verification = verifier.verify(task, execution)
        if verification.passed:
            sample = assemble_sample(
                dataset_version=dataset_version,
                environment=environment.metadata(),
                tools=registry.export(),
                task=task,
                execution=execution,
                verification=verification,
                llm_config=llm_config,
            )
            signature = candidate_duplicate_signature(
                instruction=task.instruction,
                trajectory=execution.trajectory,
            )
            if signature in accepted_signatures:
                rejection = assemble_quality_gate_rejection(
                    task=task,
                    cause="quality_duplicate",
                    message="Accepted candidate duplicates a prior task instruction and tool sequence.",
                    details={"signature": list(signature)},
                )
                rejections.append(rejection)
                _maybe_route_review(
                    review_records,
                    rejection,
                    route_reviewable_failures=route_reviewable_failures,
                )
                continue
            if not final_answer_is_logically_supported(sample):
                rejection = assemble_quality_gate_rejection(
                    task=task,
                    cause="solution_logic_error",
                    message="Final answer is not supported by observations and verifier expectation.",
                )
                rejections.append(rejection)
                _maybe_route_review(
                    review_records,
                    rejection,
                    route_reviewable_failures=route_reviewable_failures,
                )
                continue

            accepted_signatures.add(signature)
            samples.append(sample)
            continue

        rejections.append(assemble_rejection(task=task, verification=verification))

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
