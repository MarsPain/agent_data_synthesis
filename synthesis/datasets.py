from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from synthesis.contracts import (
    validate_capability_gap_record,
    validate_edited_task_record,
    validate_manifest_record,
    validate_rejection_record,
    validate_review_record,
    validate_sample_record,
    validate_generated_code_scan_result_record,
    validate_generated_executable_artifact_record,
    validate_sandbox_admission_result_record,
    validate_sandbox_execution_result_record,
    validate_source_event_record,
    validate_seed_transformation_record,
    validate_task_suggestion_record,
    validate_tool_proposal_record,
)
from synthesis.environments import EnvironmentMetadata
from synthesis.execution import ExecutionResult, SolutionPolicy
from synthesis.llm import LLMConfig, LLMProviderError
from synthesis.mutation_admission import (
    ADMISSION_EVIDENCE_VERSION,
    AUTHORIZATION_RECORD_VERSION,
    SEMANTIC_VERDICT_VERSION,
)
from synthesis.mutation_admission_reporting import (
    MUTATION_ADMISSION_REPORT_FILENAME,
    MUTATION_ADMISSION_REPORT_SCHEMA_VERSION,
    write_mutation_admission_report,
)
from synthesis.quality import build_parent_comparison, build_quality_report, retry_eligible
from synthesis.refinement import RefinementAttempt
from synthesis.tasks import CandidateTask, EditedTask, local_task_generation_lineage
from synthesis.tasks import TaskSuggestion
from synthesis.verification import VerificationResult


@dataclass(frozen=True)
class DatasetArtifacts:
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
    accepted_count: int
    rejected_count: int


@dataclass(frozen=True)
class ArtifactHashRecord:
    path: str
    sha256: str
    byte_count: int

    def export(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
        }


def build_artifact_hash_record(path: Path) -> ArtifactHashRecord:
    content = path.read_bytes()
    return ArtifactHashRecord(
        path=path.name,
        sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
    )


def serialize_dataset_manifest(manifest: Mapping[str, object]) -> str:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def attach_profile_decision_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="profile_decision_report",
        artifact_path=report_path,
    )


def attach_evaluation_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="evaluation_report",
        artifact_path=report_path,
    )


def attach_episodes_to_manifest(
    *,
    manifest_path: Path,
    episodes_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episodes",
        artifact_path=episodes_path,
    )


def attach_episode_quality_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episode_quality_report",
        artifact_path=report_path,
    )


def attach_episode_replay_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episode_replay_report",
        artifact_path=report_path,
    )


def attach_reward_labels_to_manifest(
    *,
    manifest_path: Path,
    labels_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="reward_labels",
        artifact_path=labels_path,
    )


def attach_reward_label_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="reward_label_report",
        artifact_path=report_path,
    )


def attach_dataset_release_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="dataset_release_report",
        artifact_path=report_path,
    )


def attach_dataset_release_pack_to_manifest(
    *,
    manifest_path: Path,
    pack_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="dataset_release_pack",
        artifact_path=pack_path,
    )


def attach_release_quality_audit_to_manifest(
    *,
    manifest_path: Path,
    audit_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="release_quality_audit",
        artifact_path=audit_path,
    )


def attach_release_review_queue_to_manifest(
    *,
    manifest_path: Path,
    queue_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="release_review_queue",
        artifact_path=queue_path,
    )


def attach_review_resolution_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="review_resolution_report",
        artifact_path=report_path,
    )


def attach_dataset_release_card_to_manifest(
    *,
    manifest_path: Path,
    card_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="dataset_release_card",
        artifact_path=card_path,
    )


def _attach_artifact_to_manifest(
    *,
    manifest_path: Path,
    artifact_key: str,
    artifact_path: Path,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = dict(manifest.get("artifacts", {}))
    artifacts[artifact_key] = artifact_path.name
    manifest["artifacts"] = artifacts
    validate_manifest_record(manifest)
    manifest_path.write_text(
        serialize_dataset_manifest(manifest),
        encoding="utf-8",
    )


def assemble_sample(
    *,
    dataset_version: str,
    environment: EnvironmentMetadata,
    tools: list[dict[str, object]],
    task: CandidateTask,
    execution: ExecutionResult,
    verification: VerificationResult,
    llm_config: LLMConfig,
    refinement_attempt: RefinementAttempt | None = None,
    tool_expansion: dict[str, object] | None = None,
    mutation_admission: dict[str, object] | None = None,
) -> dict[str, object]:
    action_count = sum(1 for event in execution.trajectory if event.get("type") == "action")
    stateful = any(event.get("type") == "state_change" for event in execution.trajectory)
    lineage: dict[str, object] = {
        "seed_ids": list(task.seed_ids),
        "generator": task.generation_lineage or local_task_generation_lineage(),
        "verifier": {
            "id": verification.verifier_id,
            "version": verification.version,
        },
    }
    if execution.policy and execution.policy.lineage:
        lineage["solution_policy"] = execution.policy.lineage
    if refinement_attempt is not None:
        lineage["refinement"] = refinement_attempt.sample_lineage()
    if tool_expansion is not None:
        lineage["tool_expansion"] = _tool_expansion_lineage(tool_expansion)
    if execution.branch_outcomes:
        lineage["branching"] = _branching_lineage(execution)
    if execution.adapter_lineage:
        lineage["adapter"] = [dict(record) for record in execution.adapter_lineage]
    if environment.source_provenance is not None:
        lineage["source_provenance"] = dict(environment.source_provenance)
    if task.seed_transformation is not None:
        lineage["seed_transformation"] = dict(task.seed_transformation)
    if task.task_suggester_lineage is not None:
        lineage["task_suggester"] = dict(task.task_suggester_lineage)
    if task.task_editor_lineage is not None:
        editor_lineage = dict(task.task_editor_lineage)
        if task.editor_action is not None:
            editor_lineage.setdefault("editor_action", task.editor_action)
        lineage["task_editor"] = editor_lineage

    environment_record: dict[str, object] = {
        "id": environment.environment_id,
        "version": environment.version,
        "reset_recipe": environment.reset_recipe,
    }
    if environment.source_provenance is not None:
        environment_record["source_provenance"] = dict(environment.source_provenance)

    sample: dict[str, object] = {
        "sample_id": f"sample_{task.candidate_id}",
        "dataset_version": dataset_version,
        "environment": environment_record,
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
            "tags": _quality_tags(
                action_count=action_count,
                stateful=stateful,
                branching=bool(execution.branch_outcomes),
            ),
            "review_status": "auto_accepted",
        },
        "lineage": lineage,
    }
    if mutation_admission is not None:
        sample["schema_version"] = "dataset_sample_v2"
        sample["mutation_admission"] = dict(mutation_admission)
    return sample


def assemble_rejection(
    *,
    task: CandidateTask,
    verification: VerificationResult,
    policy: SolutionPolicy | None = None,
) -> dict[str, object]:
    failed_check = next(
        (check for check in verification.checks if not check.get("passed")),
        {"name": "unknown", "expected": None, "actual": None},
    )
    cause = str(failed_check.get("cause") or "verification_failed")
    details: dict[str, object] = {
        "check": failed_check.get("name"),
        "expected": failed_check.get("expected"),
        "actual": failed_check.get("actual"),
        "retry_eligible": retry_eligible(cause),
    }
    _attach_role_lineages(details, task=task, policy=policy)
    return {
        "candidate_id": task.candidate_id,
        "cause": cause,
        "task": task.export(),
        "details": details,
    }


def assemble_quality_gate_rejection(
    *,
    task: CandidateTask,
    cause: str,
    message: str,
    details: dict[str, object] | None = None,
    policy: SolutionPolicy | None = None,
) -> dict[str, object]:
    rejection_details = {
        "message": message,
        "retry_eligible": retry_eligible(cause),
    }
    if details:
        rejection_details.update(details)
    _attach_role_lineages(rejection_details, task=task, policy=policy)
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
    policy: SolutionPolicy | None = None,
    capability_gap: dict[str, object] | None = None,
    branch_outcomes: list[dict[str, object]] | None = None,
    adapter_rejection: dict[str, object] | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "error_class": type(error).__name__,
        "message": str(error),
        "retry_eligible": retry_eligible(cause),
    }
    if capability_gap is not None:
        details["capability_gap"] = capability_gap
    if branch_outcomes is not None:
        details["branch_outcomes"] = branch_outcomes
    if adapter_rejection is not None:
        details["adapter_rejection"] = adapter_rejection
    _attach_role_lineages(details, task=task, policy=policy)
    return {
        "candidate_id": task.candidate_id or "unknown_candidate",
        "cause": cause,
        "task": task.export(),
        "details": details,
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


def assemble_source_policy_rejection(
    *,
    source_governance: dict[str, object],
    message: str,
) -> dict[str, object]:
    return {
        "candidate_id": "source_policy_gate",
        "cause": "source_policy_rejected",
        "task": {
            "candidate_id": "source_policy_gate",
            "instruction": "Source governance gate rejected material before environment construction.",
            "constraints": {},
            "difficulty": {},
        },
        "details": {
            "message": message,
            "retry_eligible": retry_eligible("source_policy_rejected"),
            "source_governance": dict(source_governance),
        },
    }


def assemble_generation_stage_rejection(*, error: LLMProviderError) -> dict[str, object]:
    details: dict[str, object] = {
        "error_class": error.error_class,
        "message": str(error),
        "retry_count": error.retry_count,
        "retry_eligible": retry_eligible(error.cause),
    }
    if error.lineage:
        details["lineage"] = dict(error.lineage)
    if error.schema_reason is not None:
        details["schema_reason"] = error.schema_reason
    if error.schema_detail is not None:
        details["schema_detail"] = error.schema_detail
    return {
        "candidate_id": "generation_stage",
        "cause": error.cause,
        "task": {
            "candidate_id": "generation_stage",
            "instruction": "Remote LLM candidate generation failed before execution.",
            "constraints": {},
            "difficulty": {},
        },
        "details": details,
    }


def assemble_task_suggestion_rejection(
    *,
    suggestion: TaskSuggestion,
) -> dict[str, object]:
    details: dict[str, object] = {
        "message": suggestion.rejection_reason or "Task suggestion was rejected.",
        "retry_eligible": retry_eligible("task_suggestion_rejected"),
        "task_suggestion": suggestion.export(),
        "role_lineages": {"task_suggester": dict(suggestion.lineage)},
    }
    if suggestion.seed_transformation is not None:
        details["seed_transformation"] = dict(suggestion.seed_transformation)
    return {
        "candidate_id": suggestion.suggestion_id,
        "cause": "task_suggestion_rejected",
        "task": {
            "candidate_id": suggestion.suggestion_id,
            "instruction": suggestion.intent,
            "constraints": suggestion.constraints,
            "difficulty": {
                "level": "unspecified",
                "taxonomy_node": suggestion.target_taxonomy_node,
            },
        },
        "details": details,
    }


def assemble_task_editor_rejection(
    *,
    edited_task: EditedTask,
) -> dict[str, object]:
    rejection = dict(edited_task.rejection or {})
    message = str(rejection.get("message", "Task editor rejected the suggestion."))
    details: dict[str, object] = {
        "message": message,
        "retry_eligible": retry_eligible("task_editor_rejected"),
        "task_editor": edited_task.export(),
        "role_lineages": {"task_editor": dict(edited_task.lineage)},
    }
    return {
        "candidate_id": edited_task.suggestion_id,
        "cause": "task_editor_rejected",
        "task": {
            "candidate_id": edited_task.suggestion_id,
            "instruction": message,
            "constraints": {},
            "difficulty": {"level": "unspecified"},
        },
        "details": details,
    }


def attach_refinement_to_rejection(
    rejection: dict[str, object],
    refinement_attempt: RefinementAttempt,
) -> dict[str, object]:
    refined = dict(rejection)
    details = dict(refined.get("details", {}))
    details["refinement"] = refinement_attempt.rejection_metadata(outcome="rejected")
    refined["details"] = details
    return refined


def write_dataset_artifacts(
    *,
    output_dir: Path,
    dataset_version: str,
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
    parent_artifact_path: Path | None = None,
    review_records: list[dict[str, object]] | None = None,
    tool_proposals: list[dict[str, object]] | None = None,
    source_events: list[dict[str, object]] | None = None,
    sandbox_audits: list[dict[str, object]] | None = None,
    run_profile_metadata: dict[str, object] | None = None,
) -> DatasetArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.jsonl"
    manifest_path = output_dir / "manifest.json"
    rejections_path = output_dir / "rejections.jsonl"
    quality_report_path = output_dir / "quality_report.json"
    optional_tool_proposals_path = output_dir / "tool_proposals.jsonl"
    optional_source_events_path = output_dir / "source_events.jsonl"
    optional_sandbox_audits_path = output_dir / "sandbox_audits.jsonl"
    optional_parent_comparison_path = output_dir / "parent_comparison.json"
    optional_review_queue_path = output_dir / "review_queue.jsonl"
    optional_mutation_admission_report_path = (
        output_dir / MUTATION_ADMISSION_REPORT_FILENAME
    )
    tool_proposals_path = optional_tool_proposals_path if tool_proposals else None
    source_events_path = optional_source_events_path if source_events else None
    sandbox_audits_path = optional_sandbox_audits_path if sandbox_audits else None
    parent_comparison_path = optional_parent_comparison_path if parent_artifact_path else None
    review_queue_path = optional_review_queue_path if review_records else None
    run_profile_attribution = _run_profile_attribution(run_profile_metadata)
    samples = _samples_with_run_profile_attribution(samples, run_profile_attribution)
    rejections = _rejections_with_run_profile_attribution(
        rejections,
        run_profile_attribution,
    )

    for sample in samples:
        validate_sample_record(sample)
    for rejection in rejections:
        validate_rejection_record(rejection)
        _validate_rejection_nested_records(rejection)
    for review_record in review_records or []:
        validate_review_record(review_record)
    for proposal_record in tool_proposals or []:
        _validate_tool_proposal_event(proposal_record)
    for source_event in source_events or []:
        validate_source_event_record(source_event)
    for sandbox_audit in sandbox_audits or []:
        _validate_sandbox_audit_record(sandbox_audit)

    _write_jsonl(samples_path, samples)
    _write_jsonl(rejections_path, rejections)
    admission_run = (
        isinstance(run_profile_metadata, Mapping)
        and run_profile_metadata.get("schema_version") == "run_profile_v4"
    )
    mutation_admission_report_path = (
        write_mutation_admission_report(
            dataset_version=dataset_version,
            samples=samples,
            rejections=rejections,
            output_path=optional_mutation_admission_report_path,
        )
        if admission_run
        else None
    )
    if not admission_run:
        _remove_if_exists(optional_mutation_admission_report_path)
    if review_records:
        _write_jsonl(optional_review_queue_path, review_records)
    else:
        _remove_if_exists(optional_review_queue_path)
    if tool_proposals:
        _write_jsonl(optional_tool_proposals_path, tool_proposals)
    else:
        _remove_if_exists(optional_tool_proposals_path)
    if source_events:
        _write_jsonl(optional_source_events_path, source_events)
    else:
        _remove_if_exists(optional_source_events_path)
    if sandbox_audits:
        _write_jsonl(optional_sandbox_audits_path, sandbox_audits)
    else:
        _remove_if_exists(optional_sandbox_audits_path)

    quality_report = build_quality_report(
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
        sandbox_audits=sandbox_audits,
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
    else:
        _remove_if_exists(optional_parent_comparison_path)

    artifacts: dict[str, object] = {
        "samples": samples_path.name,
        "rejections": rejections_path.name,
        "quality_report": quality_report_path.name,
    }
    if parent_comparison_path:
        artifacts["parent_comparison"] = parent_comparison_path.name
    if review_queue_path:
        artifacts["review_queue"] = review_queue_path.name
    if tool_proposals_path:
        artifacts["tool_proposals"] = tool_proposals_path.name
    if source_events_path:
        artifacts["source_events"] = source_events_path.name
    if sandbox_audits_path:
        artifacts["sandbox_audits"] = sandbox_audits_path.name
    if mutation_admission_report_path:
        artifacts["mutation_admission_report"] = (
            mutation_admission_report_path.name
        )

    source_policy_hashes = _source_policy_hashes(samples, rejections)

    manifest: dict[str, object] = {
        "schema_version": (
            "dataset_manifest_v2" if admission_run else "dataset_manifest_v1"
        ),
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
        "generator_config_hashes": _lineage_config_hashes(samples),
        "rejection_causes": quality_report["rejection_causes"],
    }
    if run_profile_metadata is not None:
        manifest["run_profile"] = dict(run_profile_metadata)
    if source_policy_hashes:
        manifest["source_policy_hashes"] = source_policy_hashes
    sample_contract_versions = _unique_values(
        str(sample.get("schema_version", "dataset_sample_v1"))
        for sample in samples
    )
    if admission_run:
        manifest["sample_contract_versions"] = (
            sample_contract_versions or ["dataset_sample_v2"]
        )
        manifest["admission_contract_versions"] = (
            _admission_contract_versions(samples, rejections)
        )
        assert mutation_admission_report_path is not None
        manifest["admission_artifacts"] = {
            key: build_artifact_hash_record(path).export()
            for key, path in (
                ("samples", samples_path),
                ("rejections", rejections_path),
                (
                    "mutation_admission_report",
                    mutation_admission_report_path,
                ),
            )
        }
    elif "dataset_sample_v2" in sample_contract_versions:
        manifest["sample_contract_versions"] = sample_contract_versions
    validate_manifest_record(manifest)
    manifest_path.write_text(
        serialize_dataset_manifest(manifest),
        encoding="utf-8",
    )

    return DatasetArtifacts(
        samples_path=samples_path,
        manifest_path=manifest_path,
        rejections_path=rejections_path,
        quality_report_path=quality_report_path,
        tool_proposals_path=tool_proposals_path,
        source_events_path=source_events_path,
        sandbox_audits_path=sandbox_audits_path,
        parent_comparison_path=parent_comparison_path,
        review_queue_path=review_queue_path,
        mutation_admission_report_path=mutation_admission_report_path,
        accepted_count=len(samples),
        rejected_count=len(rejections),
    )


def _admission_contract_versions(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, object]:
    evidence_records: list[Mapping[str, object]] = []
    for sample in samples:
        evidence = sample.get("mutation_admission")
        if isinstance(evidence, Mapping):
            evidence_records.append(evidence)
    for rejection in rejections:
        details = rejection.get("details")
        evidence = (
            details.get("mutation_admission")
            if isinstance(details, Mapping)
            else None
        )
        if isinstance(evidence, Mapping):
            evidence_records.append(evidence)

    def contract_values(key: str, default: str) -> list[str]:
        values = []
        for evidence in evidence_records:
            contracts = evidence.get("contract_versions")
            value = contracts.get(key) if isinstance(contracts, Mapping) else None
            if isinstance(value, str) and value not in values:
                values.append(value)
        return sorted(values) or [default]

    evidence_versions = sorted(
        {
            str(evidence.get("schema_version"))
            for evidence in evidence_records
            if isinstance(evidence.get("schema_version"), str)
        }
    ) or [ADMISSION_EVIDENCE_VERSION]
    return {
        "evidence": evidence_versions,
        "authorization": contract_values(
            "authorization",
            AUTHORIZATION_RECORD_VERSION,
        ),
        "domain_policy": contract_values("domain_policy", "unconfigured"),
        "semantic_verdict": contract_values(
            "semantic_verdict",
            SEMANTIC_VERDICT_VERSION,
        ),
        "report": [MUTATION_ADMISSION_REPORT_SCHEMA_VERSION],
    }


def _run_profile_attribution(
    run_profile_metadata: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if run_profile_metadata is None:
        return None

    attribution: dict[str, object] = {
        "schema_version": "run_profile_attribution_v1",
        "profile_schema_version": run_profile_metadata.get("schema_version"),
        "profile_id": run_profile_metadata.get("profile_id"),
        "generation_mode": run_profile_metadata.get("generation_mode"),
        "config_hash": run_profile_metadata.get("config_hash"),
    }
    mutation_admission = run_profile_metadata.get("mutation_admission")
    if isinstance(mutation_admission, Mapping):
        attribution["mutation_admission"] = {
            "mode": mutation_admission.get("mode"),
        }
    if "profile_purpose" in run_profile_metadata:
        attribution["profile_purpose"] = run_profile_metadata["profile_purpose"]
    source = run_profile_metadata.get("source")
    if isinstance(source, Mapping):
        attribution["source"] = {
            "kind": source.get("kind"),
            "source_id": source.get("source_id"),
            "content_hash": source.get("content_hash"),
            "license_label": source.get("license_label"),
            "source_policy_hash": source.get("source_policy_hash"),
        }
    return attribution


def _samples_with_run_profile_attribution(
    samples: list[dict[str, object]],
    attribution: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if attribution is None:
        return samples
    attributed_samples: list[dict[str, object]] = []
    for sample in samples:
        attributed_sample = dict(sample)
        lineage = dict(attributed_sample.get("lineage", {}))
        lineage["run_profile"] = _copy_run_profile_attribution(attribution)
        attributed_sample["lineage"] = lineage
        attributed_samples.append(attributed_sample)
    return attributed_samples


def _rejections_with_run_profile_attribution(
    rejections: list[dict[str, object]],
    attribution: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if attribution is None:
        return rejections
    attributed_rejections: list[dict[str, object]] = []
    for rejection in rejections:
        attributed_rejection = dict(rejection)
        details = attributed_rejection.get("details")
        if isinstance(details, Mapping):
            attributed_details = dict(details)
            attributed_details["run_profile"] = _copy_run_profile_attribution(attribution)
            attributed_rejection["details"] = attributed_details
        attributed_rejections.append(attributed_rejection)
    return attributed_rejections


def _copy_run_profile_attribution(attribution: Mapping[str, object]) -> dict[str, object]:
    copied = dict(attribution)
    source = copied.get("source")
    if isinstance(source, Mapping):
        copied["source"] = dict(source)
    mutation_admission = copied.get("mutation_admission")
    if isinstance(mutation_admission, Mapping):
        copied["mutation_admission"] = dict(mutation_admission)
    return copied


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(content, encoding="utf-8")


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _validate_tool_proposal_event(record: Mapping[str, object]) -> None:
    gap = record.get("gap")
    proposal = record.get("proposal")
    if isinstance(gap, Mapping):
        validate_capability_gap_record(gap)
    else:
        raise ValueError("tool proposal event gap must be an object")
    if isinstance(proposal, Mapping):
        validate_tool_proposal_record(proposal)
    else:
        raise ValueError("tool proposal event proposal must be an object")
    if not isinstance(record.get("admission"), Mapping):
        raise ValueError("tool proposal event admission must be an object")


def _validate_rejection_nested_records(record: Mapping[str, object]) -> None:
    details = record.get("details")
    if not isinstance(details, Mapping):
        return
    seed_transformation = details.get("seed_transformation")
    if isinstance(seed_transformation, Mapping):
        validate_seed_transformation_record(seed_transformation)
    task_suggestion = details.get("task_suggestion")
    if isinstance(task_suggestion, Mapping):
        validate_task_suggestion_record(task_suggestion)
    task_editor = details.get("task_editor")
    if isinstance(task_editor, Mapping):
        validate_edited_task_record(task_editor)


def _validate_sandbox_audit_record(record: Mapping[str, object]) -> None:
    if record.get("schema_version") != "sandbox_audit_v1":
        raise ValueError("sandbox audit schema_version must be sandbox_audit_v1")
    artifact = record.get("artifact")
    if isinstance(artifact, Mapping):
        validate_generated_executable_artifact_record(artifact)
    else:
        raise ValueError("sandbox audit artifact must be an object")
    scan = record.get("scan")
    if isinstance(scan, Mapping):
        validate_generated_code_scan_result_record(scan)
    else:
        raise ValueError("sandbox audit scan must be an object")
    admission = record.get("admission")
    if isinstance(admission, Mapping):
        validate_sandbox_admission_result_record(admission)
    else:
        raise ValueError("sandbox audit admission must be an object")
    execution = record.get("execution")
    if execution is not None:
        if isinstance(execution, Mapping):
            validate_sandbox_execution_result_record(execution)
        else:
            raise ValueError("sandbox audit execution must be an object or null")


def _tool_expansion_lineage(record: Mapping[str, object]) -> dict[str, object]:
    gap = record.get("gap") if isinstance(record.get("gap"), Mapping) else {}
    proposal = record.get("proposal") if isinstance(record.get("proposal"), Mapping) else {}
    admission = record.get("admission") if isinstance(record.get("admission"), Mapping) else {}
    return {
        "gap": dict(gap),
        "proposal": dict(proposal),
        "admission": dict(admission),
    }


def _unique_values(values: Iterable[object]) -> list[object]:
    unique: list[object] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _quality_tags(*, action_count: int, stateful: bool, branching: bool = False) -> list[str]:
    tags = ["foundation", "sqlite_fixture"]
    tags.append("multi_step" if action_count > 1 else "single_tool")
    if stateful:
        tags.append("stateful")
    if branching:
        tags.append("branching")
    return tags


def _lineage_config_hashes(samples: list[dict[str, object]]) -> list[object]:
    values: list[object] = []
    for sample in samples:
        lineage = sample["lineage"]
        if not isinstance(lineage, dict):
            continue
        generator = lineage.get("generator")
        if isinstance(generator, dict):
            values.append(generator.get("config_hash"))
        solution_policy = lineage.get("solution_policy")
        if isinstance(solution_policy, dict):
            values.append(solution_policy.get("config_hash"))
        refinement = lineage.get("refinement")
        if isinstance(refinement, dict):
            values.append(refinement.get("config_hash"))
    return _unique_values(value for value in values if value)


def _source_policy_hashes(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> list[object]:
    values: list[object] = []
    for sample in samples:
        lineage = sample.get("lineage")
        if isinstance(lineage, Mapping):
            provenance = lineage.get("source_provenance")
            if isinstance(provenance, Mapping):
                values.append(provenance.get("source_policy_hash"))
    for rejection in rejections:
        details = rejection.get("details")
        if isinstance(details, Mapping):
            governance = details.get("source_governance")
            if isinstance(governance, Mapping):
                values.append(governance.get("source_policy_hash"))
    return _unique_values(value for value in values if value)


def _branching_lineage(execution: ExecutionResult) -> dict[str, object]:
    outcomes = execution.branch_outcomes or []
    selected = next(
        (outcome for outcome in outcomes if outcome.get("selected")),
        {},
    )
    plan = execution.branch_plan or {}
    selected_depth = selected.get("depth", 0)
    branch_depth = selected_depth if isinstance(selected_depth, int) else 0
    fallback_count = sum(1 for outcome in outcomes if not outcome.get("selected"))
    return {
        "schema_version": "branch_lineage_v1",
        "plan_id": str(plan.get("plan_id", "unknown_branch_plan")),
        "selected_branch_id": str(selected.get("branch_id", "unknown_branch")),
        "branch_depth": branch_depth,
        "fallback_count": fallback_count,
        "branch_outcomes": outcomes,
    }


def _attach_role_lineages(
    details: dict[str, object],
    *,
    task: CandidateTask,
    policy: SolutionPolicy | None = None,
) -> None:
    role_lineages = _candidate_role_lineages(task=task, policy=policy)
    if not role_lineages:
        return
    existing = details.get("role_lineages")
    merged: dict[str, object] = {}
    if isinstance(existing, Mapping):
        merged.update({str(key): value for key, value in existing.items()})
    merged.update(role_lineages)
    details["role_lineages"] = merged


def _candidate_role_lineages(
    *,
    task: CandidateTask,
    policy: SolutionPolicy | None,
) -> dict[str, object]:
    lineages: dict[str, object] = {}
    if task.generation_lineage:
        lineages["generator"] = dict(task.generation_lineage)
    if task.task_suggester_lineage:
        lineages["task_suggester"] = dict(task.task_suggester_lineage)
    if task.task_editor_lineage:
        lineages["task_editor"] = dict(task.task_editor_lineage)
    if policy is not None and policy.lineage:
        lineages["solution_policy"] = dict(policy.lineage)
    return lineages
