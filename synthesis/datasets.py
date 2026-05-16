from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from synthesis.contracts import (
    validate_manifest_record,
    validate_rejection_record,
    validate_review_record,
    validate_sample_record,
)
from synthesis.environments import EnvironmentMetadata
from synthesis.execution import ExecutionResult
from synthesis.llm import LLMConfig
from synthesis.quality import build_parent_comparison, build_quality_report, retry_eligible
from synthesis.tasks import CandidateTask
from synthesis.verification import VerificationResult


@dataclass(frozen=True)
class DatasetArtifacts:
    samples_path: Path
    manifest_path: Path
    rejections_path: Path
    quality_report_path: Path
    parent_comparison_path: Path | None
    review_queue_path: Path | None
    accepted_count: int
    rejected_count: int


def assemble_sample(
    *,
    dataset_version: str,
    environment: EnvironmentMetadata,
    tools: list[dict[str, object]],
    task: CandidateTask,
    execution: ExecutionResult,
    verification: VerificationResult,
    llm_config: LLMConfig,
) -> dict[str, object]:
    return {
        "sample_id": f"sample_{task.candidate_id}",
        "dataset_version": dataset_version,
        "environment": {
            "id": environment.environment_id,
            "version": environment.version,
            "reset_recipe": environment.reset_recipe,
        },
        "tools": tools,
        "task": {
            "instruction": task.instruction,
            "constraints": task.constraints,
            "difficulty": task.difficulty,
        },
        "trajectory": execution.trajectory,
        "final_response": execution.final_response,
        "verifier": {
            "id": verification.verifier_id,
            "version": verification.version,
            "checks": [check["name"] for check in verification.checks],
        },
        "verification": verification.export(),
        "quality": {
            "scores": {
                "executable": 1.0,
                "verified": 1.0,
                "instruction_clarity": 1.0,
            },
            "tags": ["foundation", "sqlite_fixture", "single_tool"],
            "review_status": "auto_accepted",
        },
        "lineage": {
            "seed_ids": list(task.seed_ids),
            "generator": llm_config.lineage("task_generation"),
            "verifier": {
                "id": verification.verifier_id,
                "version": verification.version,
            },
        },
    }


def assemble_rejection(
    *,
    task: CandidateTask,
    verification: VerificationResult,
) -> dict[str, object]:
    failed_check = next(
        (check for check in verification.checks if not check.get("passed")),
        {"name": "unknown", "expected": None, "actual": None},
    )
    return {
        "candidate_id": task.candidate_id,
        "cause": "verification_failed",
        "task": task.export(),
        "details": {
            "check": failed_check.get("name"),
            "expected": failed_check.get("expected"),
            "actual": failed_check.get("actual"),
            "retry_eligible": retry_eligible("verification_failed"),
        },
    }


def assemble_quality_gate_rejection(
    *,
    task: CandidateTask,
    cause: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    rejection_details = {
        "message": message,
        "retry_eligible": retry_eligible(cause),
    }
    if details:
        rejection_details.update(details)
    return {
        "candidate_id": task.candidate_id,
        "cause": cause,
        "task": task.export(),
        "details": rejection_details,
    }


def assemble_execution_rejection(
    *,
    task: CandidateTask,
    error: Exception,
    cause: str = "tool_runtime_error",
) -> dict[str, object]:
    return {
        "candidate_id": task.candidate_id or "unknown_candidate",
        "cause": cause,
        "task": task.export(),
        "details": {
            "error_class": type(error).__name__,
            "message": str(error),
            "retry_eligible": retry_eligible(cause),
        },
    }


def assemble_candidate_schema_rejection(*, error: Exception) -> dict[str, object]:
    return {
        "candidate_id": "unknown_candidate",
        "cause": "candidate_schema_error",
        "task": {
            "candidate_id": "unknown_candidate",
            "instruction": "Rejected before execution because candidate shape is invalid.",
            "constraints": {},
            "difficulty": {},
        },
        "details": {
            "error_class": type(error).__name__,
            "message": str(error),
            "retry_eligible": retry_eligible("candidate_schema_error"),
        },
    }


def assemble_pipeline_gate_rejection(*, error: Exception) -> dict[str, object]:
    return {
        "candidate_id": "foundation_gate",
        "cause": "infrastructure_error",
        "task": {
            "candidate_id": "foundation_gate",
            "instruction": "Foundation pipeline quality gate failed before candidate execution.",
            "constraints": {},
            "difficulty": {},
        },
        "details": {
            "error_class": type(error).__name__,
            "message": str(error),
            "retry_eligible": retry_eligible("infrastructure_error"),
        },
    }


def write_dataset_artifacts(
    *,
    output_dir: Path,
    dataset_version: str,
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
    parent_artifact_path: Path | None = None,
    review_records: list[dict[str, object]] | None = None,
) -> DatasetArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.jsonl"
    manifest_path = output_dir / "manifest.json"
    rejections_path = output_dir / "rejections.jsonl"
    quality_report_path = output_dir / "quality_report.json"
    parent_comparison_path = output_dir / "parent_comparison.json" if parent_artifact_path else None
    review_queue_path = output_dir / "review_queue.jsonl" if review_records else None

    for sample in samples:
        validate_sample_record(sample)
    for rejection in rejections:
        validate_rejection_record(rejection)
    for review_record in review_records or []:
        validate_review_record(review_record)

    _write_jsonl(samples_path, samples)
    _write_jsonl(rejections_path, rejections)
    if review_records:
        _write_jsonl(output_dir / "review_queue.jsonl", review_records)

    quality_report = build_quality_report(
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
    )
    quality_report_path.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    parent_comparison: dict[str, object] | None = None
    if parent_artifact_path:
        parent_report = json.loads(parent_artifact_path.read_text(encoding="utf-8"))
        parent_comparison = build_parent_comparison(
            current=quality_report,
            parent=parent_report,
        )
        assert parent_comparison_path is not None
        parent_comparison_path.write_text(
            json.dumps(parent_comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    artifacts: dict[str, object] = {
        "samples": samples_path.name,
        "rejections": rejections_path.name,
        "quality_report": quality_report_path.name,
    }
    if parent_comparison_path:
        artifacts["parent_comparison"] = parent_comparison_path.name
    if review_queue_path:
        artifacts["review_queue"] = review_queue_path.name

    manifest = {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": dataset_version,
        "parent_dataset_version": (
            parent_comparison["parent_dataset_version"] if parent_comparison else None
        ),
        "accepted_count": len(samples),
        "rejected_count": len(rejections),
        "artifacts": artifacts,
        "quality": {
            "success_rate": quality_report["rates"]["success_rate"],
            "executable_rate": quality_report["rates"]["executable_rate"],
        },
        "environment_versions": _unique_values(
            sample["environment"]["version"] for sample in samples
        ),
        "tool_versions": _unique_values(
            tool["version"] for sample in samples for tool in sample["tools"]
        ),
        "verifier_versions": _unique_values(
            sample["verifier"]["version"] for sample in samples
        ),
        "generator_config_hashes": _unique_values(
            sample["lineage"]["generator"]["config_hash"] for sample in samples
        ),
        "rejection_causes": quality_report["rejection_causes"],
    }
    validate_manifest_record(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return DatasetArtifacts(
        samples_path=samples_path,
        manifest_path=manifest_path,
        rejections_path=rejections_path,
        quality_report_path=quality_report_path,
        parent_comparison_path=parent_comparison_path,
        review_queue_path=review_queue_path,
        accepted_count=len(samples),
        rejected_count=len(rejections),
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(content, encoding="utf-8")


def _unique_values(values: Iterable[object]) -> list[object]:
    unique: list[object] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
