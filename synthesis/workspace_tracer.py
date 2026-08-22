"""Content-addressed offline proof for the Workspace outcome contract.

The tracer is deliberately an artifact boundary.  The builder assembles a
deterministic, provider-free rehearsal from the production Workspace pipeline;
the verifier starts at one root report and follows only its declared relative
edges.  It never calls a provider, consults a default registry, or repairs a
changed artifact.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import re
import shutil
from typing import Any


WORKSPACE_TRACER_PROOF_SCHEMA_VERSION = "workspace_tracer_proof_v1"
WORKSPACE_TRACER_PROOF_FILENAME = "workspace_tracer_proof.json"
WORKSPACE_TRACER_VERIFICATION_SCHEMA_VERSION = (
    "workspace_tracer_verification_v1"
)
WORKSPACE_TRACER_ARTIFACT_REFERENCE_SCHEMA_VERSION = (
    "workspace_tracer_artifact_reference_v1"
)
WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION = "workspace_tracer_proof_case_v1"

SUMMARY = {
    "effective_qualification": "release_candidate",
    "publishable": False,
    "training_recommended": False,
    "publishable_conformance": "passed",
    "training_recommended_conformance": "passed",
}

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SAFE_RELATIVE_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

REQUIRED_ARTIFACT_KINDS = frozenset(
    {
        "domain_pack",
        "plan",
        "source",
        "runtime",
        "provider",
        "assignment",
        "sample",
        "rejection",
        "episode",
        "replay",
        "report",
        "release_pack",
        "assessment",
        "qualification",
        "compatibility",
        "conformance",
        "proof_case",
    }
)

PROOF_CASE_EXPECTATIONS: dict[str, tuple[str, str]] = {
    "plan_identity": ("insufficient_evidence", "evidence_identity_mismatch"),
    "provider_contract": ("rejected", "provider_contract_rejected"),
    "mutation_safety": ("rejected", "mutation_admission_failed"),
    "execution_evidence": ("insufficient_evidence", "evidence_identity_mismatch"),
    "coverage_evaluation": (
        "insufficient_evidence",
        "workspace_coverage_evidence_incomplete",
    ),
    "run_completeness": ("insufficient_evidence", "evidence_incomplete"),
    "artifact_integrity": ("failed", "artifact_integrity"),
    "publishability": ("denied", "publishability_scope_mismatch"),
    "fixture_isolation": ("denied", "non_qualifying_evidence_class"),
    "training_arms": ("invalid_experiment", "record_count_tolerance_exceeded"),
    "evaluation_leakage": ("invalid_experiment", "leakage_overlap_unresolved"),
    "meaningful_gain": (
        "no_detected_meaningful_gain",
        "no_detected_meaningful_gain",
    ),
    "cumulative_dependency": (
        "insufficient_evidence",
        "qualification_dependency_invalidated",
    ),
}


class WorkspaceTracerProofError(ValueError):
    """A bounded proof assembly or verification failure."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


@dataclass(frozen=True)
class _Artifact:
    artifact_id: str
    artifact_kind: str
    artifact_schema_version: str
    path: str
    sha256: str
    byte_count: int
    identity: Mapping[str, object]
    dependencies: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": WORKSPACE_TRACER_ARTIFACT_REFERENCE_SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "artifact_schema_version": self.artifact_schema_version,
            "path": self.path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "identity": dict(self.identity),
            "dependencies": list(self.dependencies),
        }


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            .encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise WorkspaceTracerProofError("proof_record_malformed") from exc


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_value(value: object) -> str:
    return _hash_bytes(_canonical_bytes(value))


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceTracerProofError("proof_artifact_unreadable") from exc
    if not isinstance(value, Mapping):
        raise WorkspaceTracerProofError("proof_artifact_malformed")
    return value


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise WorkspaceTracerProofError("unsafe_artifact_path")
    path = Path(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise WorkspaceTracerProofError("unsafe_artifact_path")
    if any(_SAFE_RELATIVE_PART_RE.fullmatch(part) is None for part in path.parts):
        raise WorkspaceTracerProofError("unsafe_artifact_path")
    return path.as_posix()


def _artifact_path(root_dir: Path, relative_path: object) -> Path:
    relative = _safe_relative_path(relative_path)
    path = root_dir / relative
    if path.is_symlink():
        raise WorkspaceTracerProofError("unsafe_artifact_path")
    try:
        path.resolve().relative_to(root_dir.resolve())
    except ValueError as exc:
        raise WorkspaceTracerProofError("unsafe_artifact_path") from exc
    return path


def _file_digest(path: Path) -> tuple[str, int]:
    try:
        content = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise WorkspaceTracerProofError("proof_artifact_unreadable") from exc
    return _hash_bytes(content), len(content)


def _schema_for_path(path: Path, fallback: str) -> str:
    if path.suffix == ".json":
        try:
            value = _read_json(path)
        except WorkspaceTracerProofError:
            return fallback
        schema = value.get("schema_version")
        if isinstance(schema, str) and schema:
            return schema
    return fallback


def _artifact_identity(path: Path) -> dict[str, object]:
    if path.suffix == ".json":
        try:
            value = _read_json(path)
        except WorkspaceTracerProofError:
            return {}
        identity: dict[str, object] = {}
        for key in (
            "proof_id",
            "proof_hash",
            "plan_id",
            "plan_hash",
            "release_id",
            "release_pack_hash",
            "subject_id",
            "subject_hash",
            "bundle_id",
            "bundle_hash",
            "protocol_id",
            "content_hash",
            "evidence_id",
            "evidence_hash",
            "case_id",
        ):
            if key in value and isinstance(value[key], (str, int)):
                identity[key] = value[key]
        return identity
    return {}


def _new_artifact(
    root_dir: Path,
    *,
    artifact_id: str,
    artifact_kind: str,
    relative_path: str,
    artifact_schema_version: str | None = None,
    dependencies: Sequence[str] = (),
) -> _Artifact:
    if not _ID_RE.fullmatch(artifact_id):
        raise WorkspaceTracerProofError("proof_artifact_malformed")
    if artifact_kind not in REQUIRED_ARTIFACT_KINDS and not artifact_kind.startswith(
        "proof_case_"
    ):
        raise WorkspaceTracerProofError("proof_artifact_kind_unknown")
    path = _artifact_path(root_dir, relative_path)
    digest, byte_count = _file_digest(path)
    return _Artifact(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        artifact_schema_version=artifact_schema_version
        or _schema_for_path(path, f"{artifact_kind}_v1"),
        path=_safe_relative_path(relative_path),
        sha256=digest,
        byte_count=byte_count,
        identity=_artifact_identity(path),
        dependencies=tuple(sorted(set(dependencies))),
    )


def _proof_identity(record: Mapping[str, object]) -> str:
    content = {
        key: value
        for key, value in record.items()
        if key not in {"proof_id", "proof_hash"}
    }
    return _hash_value(content)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise WorkspaceTracerProofError("compatibility_corpus_missing")
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        target = destination / relative
        if source_path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
        else:
            raise WorkspaceTracerProofError("unsafe_compatibility_corpus")


def _record_difference(left: object, right: object, prefix: str = "") -> list[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[str] = []
        for key in sorted(set(left) | set(right), key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_record_difference(left[key], right[key], child))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        paths = []
        for index in range(max(len(left), len(right))):
            child = f"{prefix}[{index}]"
            if index >= len(left) or index >= len(right):
                paths.append(child)
            else:
                paths.extend(_record_difference(left[index], right[index], child))
        return paths
    return [] if left == right else [prefix]


def _load_jsonl(path: Path) -> list[Mapping[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise WorkspaceTracerProofError("proof_artifact_unreadable") from exc
    records: list[Mapping[str, object]] = []
    for line in lines:
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkspaceTracerProofError("proof_artifact_malformed") from exc
        if not isinstance(value, Mapping):
            raise WorkspaceTracerProofError("proof_artifact_malformed")
        records.append(value)
    return records


def _require_mapping(value: object, reason: str = "proof_record_malformed") -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WorkspaceTracerProofError(reason)
    return value


def _require_text(value: object, reason: str = "proof_record_malformed") -> str:
    if not isinstance(value, str) or not value:
        raise WorkspaceTracerProofError(reason)
    return value


def _require_hash(value: object, reason: str = "proof_record_malformed") -> str:
    value = _require_text(value, reason)
    if _HASH_RE.fullmatch(value) is None:
        raise WorkspaceTracerProofError(reason)
    return value


def _bounded_result(
    *,
    status: str,
    reason_codes: Sequence[str],
    proof_identity: str | None = None,
    summary: Mapping[str, object] | None = None,
    artifacts: Sequence[Mapping[str, object]] = (),
    proof_cases: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": WORKSPACE_TRACER_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "proof_identity": proof_identity,
        "summary": dict(summary or {}),
        "artifacts": [dict(item) for item in artifacts],
        "proof_cases": [dict(item) for item in proof_cases],
    }
    return result


class _OfflineWorkspaceProvider:
    """Deterministic provider adapter used only by the proof builder.

    The production coverage scheduler still owns assignment issuance, parser
    validation, and membership checks.  This adapter supplies the same narrow
    JSON boundary as a provider, but derives every response from the prompt's
    already-admitted grounding unit and records hashes instead of raw payloads.
    """

    provider_id = "workspace_tracer_offline_provider"
    provider_version = "workspace_tracer_offline_provider_v1"
    model = "offline_workspace_fixture_v1"
    parser_version = "domain_generation_parser_v1"

    def __init__(self) -> None:
        self.attempts: list[dict[str, object]] = []

    def generate_json(self, prompt: str, *, role: str) -> Any:
        if role != "task_generation":
            raise RuntimeError("offline Workspace provider received an unsupported role")
        try:
            payload = json.loads(prompt)
            assignment = _require_mapping(payload.get("coverage_assignment"))
            task_spec = _require_mapping(
                _require_sequence(payload.get("task_types"), "provider_contract")[0]
            )
            grounding = _require_mapping(payload.get("grounding_context"))
            units = _require_sequence(grounding.get("workspace_items"), "provider_contract")
            unit = _require_mapping(units[0])
            primary_arguments = dict(
                _require_mapping(unit.get("primary_arguments"), "provider_contract")
            )
            observation = _require_mapping(unit.get("observation"), "provider_contract")
            batch_context = _require_mapping(payload.get("batch_context"))
            candidate_prefix = _require_text(
                batch_context.get("candidate_id_prefix"), "provider_contract"
            )
            task_type = _require_text(task_spec.get("task_type"), "provider_contract")
            required_tools = [
                str(item)
                for item in _require_sequence(task_spec.get("required_tools"), "provider_contract")
            ]
            capabilities = [
                str(item)
                for item in _require_sequence(
                    task_spec.get("required_capabilities"), "provider_contract"
                )
            ]
            candidate_id = candidate_prefix + "offline_candidate"
            assignment_ordinal = int(assignment.get("assignment_ordinal", 0))
            sample_label = f"coverage sample {assignment_ordinal:02d}"
            expected_state: list[dict[str, object]] = []
            if task_type == "workspace_task_creation":
                project_id = _require_text(observation.get("project_id"), "provider_contract")
                project_name = _require_text(
                    str(observation.get("summary", "")).split(" (", 1)[0],
                    "provider_contract",
                )
                task_title = f"Prepare launch checklist {assignment_ordinal:02d}"
                instruction = (
                    f"Find the {project_name} project and create a high-priority task "
                    f"titled {task_title} due this week ({sample_label})."
                )
                expected_state.append(
                    {
                        "check_type": "workspace_task",
                        "expected": {
                            "project_id": project_id,
                            "title": task_title,
                            "priority": "high",
                            "due_label": "this_week",
                        },
                    }
                )
                final_answer = "$derived_from_expected_state$"
            elif task_type == "workspace_comment_update":
                task_id = _require_text(observation.get("item_id"), "provider_contract")
                summary = _require_text(observation.get("summary"), "provider_contract")
                comment = f"Added launch checklist owner ({sample_label})."
                instruction = (
                    f"Find the {summary} task and add a comment assigning the "
                    f"checklist owner ({sample_label})."
                )
                expected_state.append(
                    {
                        "check_type": "workspace_comment",
                        "expected": {
                            "task_id": task_id,
                            "comment": comment,
                        },
                    }
                )
                final_answer = "$derived_from_expected_state$"
            else:
                summary = _require_text(observation.get("summary"), "provider_contract")
                if str(assignment.get("recovery")) != "none":
                    instruction = (
                        "Find the checklist owner note in workspace comments after "
                        f"the direct task lookup fails ({sample_label})."
                    )
                else:
                    instruction = (
                        f"Find the workspace item described as {summary} "
                        f"({sample_label})."
                    )
                final_answer = _require_text(observation.get("item_id"), "provider_contract")

            response: dict[str, object] = {
                "task_contracts": [
                    {
                        "candidate_id": candidate_id,
                        "instruction": instruction,
                        "task_type": task_type,
                        "difficulty": {},
                        "required_capabilities": capabilities,
                        "required_tools": required_tools,
                        "primary_tool": required_tools[0],
                        "primary_arguments": primary_arguments,
                        "final_answer_contains": final_answer,
                        "expected_state": expected_state,
                    }
                ]
            }
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("offline Workspace provider contract construction failed") from exc

        request_hash = _hash_bytes(prompt.encode("utf-8"))
        response_hash = _hash_value(response)
        assignment_id = _require_text(assignment.get("assignment_id"), "provider_contract")
        self.attempts.append(
            {
                "assignment_id": assignment_id,
                "assignment": dict(assignment),
                "response": response,
                "request_hash": request_hash,
                "response_hash": response_hash,
                "provider_id": self.provider_id,
                "provider_version": self.provider_version,
                "model": self.model,
                "config_hash": _hash_value(
                    {
                        "provider_id": self.provider_id,
                        "provider_version": self.provider_version,
                        "model": self.model,
                        "parser_version": self.parser_version,
                    }
                ),
                "parser_version": self.parser_version,
                "attempt_index": 0,
                "outcome": "parsed_and_membership_checked",
            }
        )
        return _GenerationResult(
            content=response,
            lineage={
                "provider_id": self.provider_id,
                "provider_version": self.provider_version,
                "model": self.model,
                "parser_version": self.parser_version,
                "role": "task_generation",
                "role_version": "role_task_generation_v1",
                "output_type": "candidate_tasks",
                "owner_module": "synthesis.tasks",
                "retry_policy": "provider_default",
                "requires_sandbox_admission": False,
                "provider_host": "offline_workspace_tracer",
                "config_hash": _hash_value(
                    {
                        "provider_id": self.provider_id,
                        "provider_version": self.provider_version,
                        "model": self.model,
                        "parser_version": self.parser_version,
                    }
                ),
                "request_hash": request_hash,
                "response_hash": response_hash,
                "retry_count": 0,
            },
        )


@dataclass(frozen=True)
class _GenerationResult:
    content: dict[str, object]
    lineage: dict[str, object]


def _require_sequence(value: object, reason: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise WorkspaceTracerProofError(reason)
    return value


def _offline_workspace_profile(output_dir: Path) -> object:
    from synthesis.mutation_admission_config import (
        MUTATION_ADMISSION_JUDGE_PROVIDER,
        MUTATION_ADMISSION_JUDGE_ROLE,
        MutationAdmissionJudgeConfiguration,
    )
    from synthesis.run_profiles import RunProfileMutationAdmission, load_run_profile

    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "run_profiles"
        / "workspace-tasks-coverage-pilot-12.json"
    )
    profile = load_run_profile(fixture_path)
    profile = replace(
        profile,
        profile_id="workspace_tracer_offline",
        dataset_version="dataset_workspace_tracer_offline_v1",
        profile_purpose="release_candidate",
        mutation_admission=RunProfileMutationAdmission(
            mode="enforce",
            judge=MutationAdmissionJudgeConfiguration(
                role=MUTATION_ADMISSION_JUDGE_ROLE,
                provider=MUTATION_ADMISSION_JUDGE_PROVIDER,
                model="deterministic_workspace_mutation_judge_v1",
                timeout_seconds=1.0,
                max_retries=0,
            ),
        ),
    )
    profile = profile.with_dataset_version(profile.dataset_version)
    _write_json(output_dir / "run_profile.json", profile.canonical())
    return profile


def replay_provider_attempts(
    *,
    root_dir: Path,
    artifacts: Mapping[str, Mapping[str, object]],
    anchors: Mapping[str, object],
    plan: object,
    seed: object,
    provider: Mapping[str, object],
    assignment_evidence: Mapping[str, object] | None = None,
) -> int:
    """Run the production provider parser and assignment membership checks."""

    from synthesis.coverage_assignments import (
        CoverageAssignment,
        _assignment_generation_spec,
        _validate_assignment_membership,
    )
    from synthesis.domain_generation import (
        build_generation_batch_context,
        parse_domain_task_contracts,
    )
    from synthesis.domain_pack import DomainCapabilityReference
    from synthesis.workspace_environment import WorkspaceTasksEnvironment
    from synthesis.workspace_tasks import build_workspace_generation_spec
    from synthesis.workspace_tools import build_workspace_tool_registry

    environment_path = _anchor_path(root_dir, artifacts, anchors, "workspace_environment")
    environment = WorkspaceTasksEnvironment(
        environment_path, representative_fixture=False
    )
    registry = build_workspace_tool_registry(environment)
    generation_spec = build_workspace_generation_spec(
        environment,
        registry,
        representative=False,
        domain_plan=plan,
    )
    assignment_evidence = assignment_evidence or _read_json(
        _anchor_path(root_dir, artifacts, anchors, "assignments")
    )
    anchored_assignments = _require_sequence(
        assignment_evidence.get("assignments"), "provider_contract"
    )
    anchored_assignment_by_id = {
        _require_text(
            _require_mapping(item, "provider_contract").get("assignment_id"),
            "provider_contract",
        ): _require_mapping(item, "provider_contract")
        for item in anchored_assignments
    }
    anchored_contracts = _require_sequence(
        assignment_evidence.get("assignment_contracts"), "provider_contract"
    )
    anchored_contract_by_id = {
        _require_text(
            _require_mapping(item, "provider_contract").get("assignment_id"),
            "provider_contract",
        ): _require_mapping(item, "provider_contract")
        for item in anchored_contracts
    }
    attempts = provider.get("replay_attempts", provider.get("attempts"))
    if not isinstance(attempts, list) or not attempts:
        raise WorkspaceTracerProofError("provider_contract")
    for raw_attempt in attempts:
        attempt = _require_mapping(raw_attempt, "provider_contract")
        assignment_record = _require_mapping(
            attempt.get("assignment"), "provider_contract"
        )
        response = _require_mapping(attempt.get("response"), "provider_contract")
        if _hash_value(response) != attempt.get("response_hash"):
            raise WorkspaceTracerProofError("provider_contract")
        if attempt.get("assignment_id") != assignment_record.get("assignment_id"):
            raise WorkspaceTracerProofError("provider_contract")
        assignment_lineage = _require_mapping(
            attempt.get("assignment_lineage"), "provider_contract"
        )
        if dict(assignment_lineage) != dict(
            anchored_assignment_by_id.get(str(attempt.get("assignment_id")), {})
        ):
            raise WorkspaceTracerProofError("provider_contract")
        if dict(assignment_record) != dict(
            anchored_contract_by_id.get(str(attempt.get("assignment_id")), {})
        ):
            raise WorkspaceTracerProofError("provider_contract")
        grounding_scope = _require_mapping(
            assignment_record.get("grounding_scope"), "provider_contract"
        )
        dimensions = {
            "task_type": assignment_record.get("task_type"),
            "required_tools": tuple(assignment_record.get("required_tools", ())),
            "state_behavior": assignment_record.get("state_behavior"),
            "grounding_pattern": assignment_record.get("grounding_pattern"),
            "constraint_profile": assignment_record.get("constraint_profile"),
            "difficulty": assignment_record.get("difficulty"),
            "ambiguity": assignment_record.get("ambiguity"),
            "recovery": assignment_record.get("recovery"),
        }
        if any(
            not isinstance(value, (str, tuple)) or not value
            for value in dimensions.values()
        ):
            raise WorkspaceTracerProofError("provider_contract")
        capability_references = tuple(
            DomainCapabilityReference.from_record(item)
            for item in _require_sequence(
                assignment_record.get("capability_references"), "provider_contract"
            )
        )
        recovery = dimensions["recovery"]
        assignment = CoverageAssignment(
            assignment_id=_require_text(
                assignment_record.get("assignment_id"), "provider_contract"
            ),
            assignment_hash=_require_hash(
                assignment_record.get("assignment_hash"), "provider_contract"
            ),
            assignment_ordinal=int(
                assignment_record.get("assignment_ordinal", -1)
            ),
            plan_id=_require_text(assignment_lineage.get("plan_id"), "provider_contract"),
            plan_hash=_require_hash(assignment_lineage.get("plan_hash"), "provider_contract"),
            cell_id=_require_text(assignment_record.get("cell_id"), "provider_contract"),
            dimensions=dimensions,
            catalog={},
            coverage_profile={},
            grounding_context_key=_require_text(
                grounding_scope.get("context_key"), "provider_contract"
            ),
            grounding_unit_index=int(
                grounding_scope.get("unit_index", -1)
            ),
            grounding_unit_hash=_require_hash(
                grounding_scope.get("grounding_hash"), "provider_contract"
            ),
            grounding_unit_id=None,
            difficulty_semantics={},
            branch_plan={} if recovery != "none" else None,
            capability_references=capability_references,
        )
        assignment_spec = _assignment_generation_spec(generation_spec, assignment)
        batch_context = build_generation_batch_context(
            assignment_spec,
            batch_index=assignment.assignment_ordinal + 1,
        )
        contracts = parse_domain_task_contracts(
            response,
            seed=seed,
            spec=assignment_spec,
            batch_context=batch_context,
            generation_lineage={"coverage_assignment": assignment.lineage()},
        )
        if len(contracts) != 1:
            raise WorkspaceTracerProofError("provider_contract")
        _validate_assignment_membership(
            raw_record=_require_mapping(
                _require_sequence(response.get("task_contracts"), "provider_contract")[0],
                "provider_contract",
            ),
            contract=contracts[0],
            assignment=assignment,
            assignment_spec=assignment_spec,
            seed=seed,
            batch_context=batch_context,
            generation_lineage={"coverage_assignment": assignment.lineage()},
        )
    return len(attempts)


def _build_publishability_conformance(
    *,
    root_dir: Path,
    qualification: Mapping[str, object],
    release_pack: Mapping[str, object],
    release_pack_path: Path,
    release_quality_audit: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    from synthesis.publishability import (
        AUDIT_RISK_FACTS,
        GOVERNANCE_CHECKS,
        build_authority_policy,
        build_publication_approval,
        build_publication_governance_report,
        build_publishability_bundle,
        build_revocation_evidence,
        build_risk_acceptance,
        compute_publishability_evidence_hash,
        evaluate_publishability,
        fingerprint_for_key,
        publishability_subject_from_release_candidate,
    )
    from synthesis.release_review import build_release_review_items

    approval_key = "workspace-tracer-approval-key"
    risk_key = "workspace-tracer-risk-key"
    checked_at = "2026-08-15T00:00:00Z"
    expires_at = "2026-09-15T00:00:00Z"
    pack_hash, pack_bytes = _file_digest(release_pack_path)
    subject = publishability_subject_from_release_candidate(
        qualification,
        release_pack={
            "release_id": release_pack["release_id"],
            "dataset_version": release_pack["dataset_version"],
            "content_hash": pack_hash,
            "byte_count": pack_bytes,
        },
    )
    scope = {
        "audience": ["internal"],
        "purpose": ["evaluation"],
        "access": "restricted",
        "retention": {"max_days": 30},
        "redistribution": "none",
    }
    checks = {
        check: {
            "status": "passed",
            "evidence_id": f"workspace-tracer-check-{check}",
            "evidence_hash": _hash_value({"check": check}),
        }
        for check in GOVERNANCE_CHECKS
    }
    governance = build_publication_governance_report(
        subject=subject,
        proposed_scope=scope,
        checks=checks,
        known_limitations=["fixture-authority-conformance-only"],
    )
    review_items = build_release_review_items(release_quality_audit)
    risk_acceptances: list[dict[str, object]] = []
    if review_items:
        review = {
            "status": "reviewed",
            "queue": review_items,
            "resolution": None,
            "dispositions": [
                {
                    "finding_id": item["review_item_id"],
                    "outcome": "accepted_risk",
                }
                for item in review_items
            ],
        }
    else:
        review = {
            "status": "not_required",
            "queue": [],
            "resolution": None,
        }

    policy = build_authority_policy(
        policy_id="authority_policy_workspace_tracer_v1",
        policy_version="1",
        trust_root={
            "root_id": "trust_root_workspace_tracer",
            "keys": [
                {
                    "key_id": "approval-key",
                    "fingerprint": fingerprint_for_key(approval_key),
                },
                {
                    "key_id": "risk-key",
                    "fingerprint": fingerprint_for_key(risk_key),
                },
            ],
        },
        grants=[
            {
                "principal_id": "workspace-tracer-publication",
                "key_id": "approval-key",
                "roles": ["publication_approver", "revocation_authority"],
                "scope": scope,
                "valid_from": checked_at,
                "expires_at": expires_at,
            },
            *(
                [
                    {
                        "principal_id": "workspace-tracer-risk",
                        "key_id": "risk-key",
                        "roles": ["risk_owner"],
                        "scope": scope,
                        "valid_from": checked_at,
                        "expires_at": expires_at,
                    }
                ]
                if review_items
                else []
            ),
        ],
        separation_of_duties={
            "external_residual_risk_requires_distinct_principals": True,
            "internal_role_combination_allowed": False,
        },
        valid_from=checked_at,
        expires_at=expires_at,
    )
    if review_items:
        for item in review_items:
            risk_kind = str(_require_mapping(item["risk"], "review")["kind"])
            risk_severity, risk_reason_code = AUDIT_RISK_FACTS[risk_kind]
            risk_acceptances.append(
                build_risk_acceptance(
                    subject=subject,
                    findings=[
                        {
                            "finding_id": item["review_item_id"],
                            "category": risk_kind,
                            "severity": risk_severity,
                            "reason_code": risk_reason_code,
                            "controls": ["bounded_fixture_review"],
                        }
                    ],
                    permitted_scope=scope,
                    authority_policy=policy,
                    principal_id="workspace-tracer-risk",
                    key_id="risk-key",
                    issued_at=checked_at,
                    expires_at=expires_at,
                    signing_key=risk_key,
                )
            )
    revocation = build_revocation_evidence(
        authority_policy=policy,
        checked_at=checked_at,
        principal_id="workspace-tracer-publication",
        key_id="approval-key",
        expires_at=expires_at,
        signing_key=approval_key,
    )
    historical_decisions = _require_sequence(
        qualification.get("historical_decisions"), "qualification"
    )
    latest_decision = _require_mapping(historical_decisions[-1], "qualification")
    qualification_evidence = _require_mapping(
        latest_decision.get("evidence"), "qualification"
    )
    gate_records = _require_mapping(qualification_evidence.get("gates"), "qualification")
    release_pack_verification = dict(
        _require_mapping(gate_records.get("release_pack_verification"), "qualification")
    )
    release_pack_verification["release_pack_hash"] = pack_hash
    release_pack_verification["release_pack_byte_count"] = pack_bytes
    evidence_hash = compute_publishability_evidence_hash(
        release_candidate=qualification,
        release_pack={
            "release_id": release_pack["release_id"],
            "dataset_version": release_pack["dataset_version"],
            "content_hash": pack_hash,
            "byte_count": pack_bytes,
        },
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=release_quality_audit,
        review=review,
        risk_acceptances=risk_acceptances,
        authority_policy=policy,
        revocation=revocation,
        requested_scope=scope,
        validity={"checked_at": checked_at},
    )
    approval = build_publication_approval(
        subject=subject,
        bundle_hash=evidence_hash,
        approved_scope=scope,
        authority_policy=policy,
        principal_id="workspace-tracer-publication",
        key_id="approval-key",
        issued_at=checked_at,
        expires_at=expires_at,
        known_limitations=governance["known_limitations"],
        signing_key=approval_key,
        evidence_class="conformance_fixture",
    )
    bundle = build_publishability_bundle(
        release_candidate=qualification,
        release_pack={
            "release_id": release_pack["release_id"],
            "dataset_version": release_pack["dataset_version"],
            "content_hash": pack_hash,
            "byte_count": pack_bytes,
        },
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=release_quality_audit,
        review=review,
        risk_acceptances=risk_acceptances,
        publication_approval=approval,
        authority_policy=policy,
        revocation=revocation,
        requested_scope=scope,
        validity={"checked_at": checked_at},
        evidence_class="conformance_fixture",
    )
    trusted_keys = {"approval-key": approval_key, "risk-key": risk_key}
    decision = evaluate_publishability(
        bundle=bundle,
        trusted_keys=trusted_keys,
        trusted_policy_hashes=[policy["policy_hash"]],
        trusted_bundle_content_hashes=[bundle["bundle_content_hash"]],
        trusted_release_pack_verification_hashes=[
            bundle["release_pack_verification"]["verification_hash"]
        ],
        now=checked_at,
        release_pack_path=release_pack_path,
    )
    _write_json(root_dir / "conformance" / "publishability_bundle.json", bundle)
    _write_json(root_dir / "conformance" / "publishability_decision.json", decision)
    return bundle, decision


def _build_training_conformance(
    *,
    root_dir: Path,
    release_pack: Mapping[str, object],
    publishability_bundle: Mapping[str, object],
) -> dict[str, object]:
    from synthesis.training_recommendation import (
        build_training_recommendation_arm_manifest,
        build_training_recommendation_evaluation_manifest,
        build_training_recommendation_leakage_report,
        build_training_recommendation_paired_results,
        build_training_recommendation_protocol,
        evaluate_training_recommendation,
    )

    control = [f"control_{index:03d}" for index in range(20)]
    release = [f"release_{index:03d}" for index in range(20)]
    release_subject = _require_mapping(publishability_bundle.get("subject"), "training")
    protocol = build_training_recommendation_protocol(
        publishable_release={
            "qualification": "publishable",
            "subject_id": release_subject["subject_id"],
            "subject_hash": release_subject["subject_hash"],
            "release_id": release_pack["release_id"],
            "release_pack_hash": release_subject["release_pack_hash"],
            "publishability_bundle_hash": publishability_bundle["bundle_hash"],
            "publishability_decision_hash": _hash_value(
                publishability_bundle["bundle_content_hash"]
            ),
            "domain_pack_reference": release_subject["domain_pack_reference"],
        },
        model={"model_id": "workspace_tracer_fixture_model_v1", "revision": "offline"},
        tokenizer={"tokenizer_id": "workspace_tracer_fixture_tokenizer_v1", "revision": "offline"},
        training_system={"system_id": "workspace_tracer_fixture_trainer_v1"},
        training_code={"code_hash": _hash_value("workspace_tracer_training_code_v1")},
        environment={"environment_id": "workspace_tracer_cpu_fixture_v1"},
        hyperparameters={"learning_rate": "declared"},
        seed="workspace-tracer-bootstrap-v1",
        schedule={"schedule_id": "fixed_schedule_v1"},
        stopping_rules={"rule_id": "fixed_schedule_v1"},
        exclusion_rules={"rule_id": "predeclared_exclusions_v1"},
        common_inputs={"input_set_hash": _hash_value("workspace_tracer_inputs_v1")},
        control_manifest={"manifest_id": "control_v1", "record_hashes": control},
        release_manifest={"manifest_id": "release_v1", "record_hashes": release},
        benchmark={"suite_id": "workspace_tasks_conformance_v1", "suite_version": "1"},
        sealed_split={
            "split_id": "workspace_tracer_test_v1",
            "split_hash": _hash_value("workspace_tracer_sealed_split_v1"),
        },
        ordered_task_ids=[f"task_{index:03d}" for index in range(20)],
        scoring={"scoring_code_hash": _hash_value("workspace_tracer_scoring_v1")},
        leakage_method={
            "method_id": "workspace_tracer_leakage_v1",
            "method_hash": _hash_value("workspace_tracer_leakage_method_v1"),
        },
        registration={
            "registered_at": "2026-08-15T00:00:00Z",
            "registered_before_training": True,
            "post_registration_change": False,
        },
        selection_rule={"rule_id": "workspace_tracer_replacement_v1"},
        bootstrap_seed="workspace-tracer-bootstrap-v1-replicates",
        evidence_class="conformance_fixture",
    )
    removed = control[:10]
    inserted = release[:10]
    baseline = build_training_recommendation_arm_manifest(
        protocol=protocol,
        arm="baseline",
        training_record_hashes=control,
        removed_control_record_hashes=removed,
    )
    treatment = build_training_recommendation_arm_manifest(
        protocol=protocol,
        arm="treatment",
        training_record_hashes=control[10:] + inserted,
        removed_control_record_hashes=removed,
        inserted_release_record_hashes=inserted,
    )
    evaluation = build_training_recommendation_evaluation_manifest(protocol=protocol)
    paired = build_training_recommendation_paired_results(
        protocol=protocol,
        evaluation=evaluation,
        baseline_successes=[0] * 10 + [1] * 10,
        treatment_successes=[1] * 20,
    )
    leakage = build_training_recommendation_leakage_report(
        protocol=protocol,
        evaluation=evaluation,
    )
    result = evaluate_training_recommendation(
        protocol=protocol,
        baseline=baseline,
        treatment=treatment,
        evaluation=evaluation,
        paired_results=paired,
        leakage=leakage,
        expected_evidence_class="conformance_fixture",
    )
    for name, record in (
        ("training_protocol", protocol),
        ("training_baseline", baseline),
        ("training_treatment", treatment),
        ("training_evaluation", evaluation),
        ("training_paired", paired),
        ("training_leakage", leakage),
        ("training_result", result),
    ):
        _write_json(root_dir / "conformance" / f"{name}.json", record)
    return result


def _set_record_path(record: object, path: str, value: object) -> None:
    tokens: list[str | int] = []
    for match in re.finditer(r"([^\.\[\]]+)|\[(\d+)\]", path):
        token = match.group(1)
        tokens.append(token if token is not None else int(match.group(2)))
    if not tokens:
        raise WorkspaceTracerProofError("proof_case_mutation_scope")
    current = record
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list):
                raise WorkspaceTracerProofError("proof_case_mutation_scope")
            current = current[token]
        else:
            if not isinstance(current, Mapping):
                raise WorkspaceTracerProofError("proof_case_mutation_scope")
            current = current[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(current, list):
            raise WorkspaceTracerProofError("proof_case_mutation_scope")
        current[last] = value
    else:
        if not isinstance(current, dict):
            raise WorkspaceTracerProofError("proof_case_mutation_scope")
        current[last] = value


def _artifact_kind_for_path(relative_path: str) -> str:
    name = Path(relative_path).name
    if relative_path.startswith("conformance/"):
        return "conformance"
    if relative_path.startswith("compatibility/"):
        return "compatibility"
    if relative_path.startswith("proof_cases/"):
        return "proof_case"
    if name == "dataset_release_pack.json":
        return "release_pack"
    if name == "qualification_report.json":
        return "qualification"
    if name == "episode_replay_report.json":
        return "replay"
    if name == "episodes.jsonl":
        return "episode"
    if name == "samples.jsonl":
        return "sample"
    if name == "rejections.jsonl":
        return "rejection"
    if name == "workspace_tasks.sqlite3":
        return "runtime"
    if name == "domain_pack.json":
        return "domain_pack"
    if name == "plan.json":
        return "plan"
    if name == "source.json":
        return "source"
    if name == "runtime.json":
        return "runtime"
    if name == "provider.json":
        return "provider"
    if name == "assignments.json":
        return "assignment"
    if name == "assessment.json":
        return "assessment"
    if name == "qualification.json":
        return "qualification"
    return "report"


def _artifact_id_for_path(relative_path: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", relative_path).strip("_").lower()
    return "artifact_" + stem[:112]


def _collect_artifacts(root_dir: Path) -> dict[str, _Artifact]:
    artifacts: dict[str, _Artifact] = {}
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root_dir).as_posix()
        if relative == WORKSPACE_TRACER_PROOF_FILENAME:
            continue
        artifact_id = _artifact_id_for_path(relative)
        if artifact_id in artifacts:
            raise WorkspaceTracerProofError("proof_artifact_identity_mismatch")
        artifacts[artifact_id] = _new_artifact(
            root_dir,
            artifact_id=artifact_id,
            artifact_kind=_artifact_kind_for_path(relative),
            relative_path=relative,
        )
    return artifacts


def _artifact_id_for_exact_path(
    artifacts: Mapping[str, _Artifact],
    root_dir: Path,
    path: Path,
) -> str:
    relative = path.relative_to(root_dir).as_posix()
    artifact_id = _artifact_id_for_path(relative)
    if artifact_id not in artifacts:
        raise WorkspaceTracerProofError("proof_anchor_missing")
    return artifact_id


def _build_proof_cases(
    *,
    root_dir: Path,
    artifacts: Mapping[str, _Artifact],
    target_paths: Mapping[str, Path],
) -> tuple[list[_Artifact], list[dict[str, object]]]:
    mutations = {
        "plan_identity": ("plan_id", "domain_plan_identity_mutated"),
        "provider_contract": (
            "attempts[0].response_hash",
            "invalid_response_hash",
        ),
        "mutation_safety": (
            "hashes.authorization",
            "invalid_authorization_hash",
        ),
        "execution_evidence": ("decision.status", "failed"),
        "coverage_evaluation": ("fulfillment.status", "incomplete"),
        "run_completeness": ("accepted_count", 0),
        "artifact_integrity": ("release_id", "release_id_mutated"),
        "publishability": ("requested_scope.access", "public"),
        "fixture_isolation": ("evidence_class", "real"),
        "training_arms": ("replacement", None),
        "evaluation_leakage": ("unresolved_overlap_count", 1),
        "meaningful_gain": ("bootstrap.relative_lower_bound", 0.0),
        "cumulative_dependency": ("status", "insufficient_evidence"),
    }
    extra_artifacts: list[_Artifact] = []
    cases: list[dict[str, object]] = []
    base_artifacts = dict(artifacts)
    for case_id in sorted(PROOF_CASE_EXPECTATIONS):
        target_path = target_paths[case_id]
        target_id = _artifact_id_for_exact_path(base_artifacts, root_dir, target_path)
        positive_relative = f"proof_cases/{case_id}/positive.json"
        mutated_relative = f"proof_cases/{case_id}/mutated.json"
        case_relative = f"proof_cases/{case_id}/case.json"
        positive_path = _artifact_path(root_dir, positive_relative)
        mutated_path = _artifact_path(root_dir, mutated_relative)
        case_path = _artifact_path(root_dir, case_relative)
        positive_path.parent.mkdir(parents=True, exist_ok=True)
        positive_bytes = target_path.read_bytes()
        positive_path.write_bytes(positive_bytes)
        try:
            positive_value = json.loads(positive_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WorkspaceTracerProofError("proof_case_mutation_unreadable") from exc
        mutated_value = copy.deepcopy(positive_value)
        mutation_path, mutation_value = mutations[case_id]
        if case_id == "training_arms":
            replacement = dict(
                _require_mapping(positive_value.get("replacement"), "proof_case_mutation")
            )
            inserted = list(
                _require_sequence(
                    replacement.get("inserted_release_record_hashes"),
                    "proof_case_mutation",
                )
            )
            replacement["inserted_release_record_hashes"] = inserted + [
                f"release_{index:03d}" for index in range(len(inserted), len(inserted) * 2)
            ]
            replacement["inserted_record_count"] = len(
                replacement["inserted_release_record_hashes"]
            )
            mutation_value = replacement
        _set_record_path(mutated_value, mutation_path, mutation_value)
        mutated_path.write_text(
            json.dumps(mutated_value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        unrelated = sorted(
            (artifact_id for artifact_id in base_artifacts if artifact_id != target_id),
            key=str,
        )
        case_record = {
            "schema_version": WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION,
            "case_id": case_id,
            "target_artifact_id": target_id,
            "mutation_path": mutation_path,
            "expected_status": PROOF_CASE_EXPECTATIONS[case_id][0],
            "expected_reason_code": PROOF_CASE_EXPECTATIONS[case_id][1],
            "positive_sha256": _hash_bytes(positive_bytes),
            "positive_byte_count": len(positive_bytes),
            "mutated_sha256": _hash_bytes(mutated_path.read_bytes()),
            "mutated_byte_count": len(mutated_path.read_bytes()),
            "unrelated_artifact_ids": unrelated,
            "unrelated_artifact_hashes": {
                artifact_id: base_artifacts[artifact_id].sha256
                for artifact_id in unrelated
            },
        }
        _write_json(case_path, case_record)
        case_artifact = _new_artifact(
            root_dir,
            artifact_id=_artifact_id_for_path(case_relative),
            artifact_kind="proof_case",
            relative_path=case_relative,
            artifact_schema_version=WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION,
            dependencies=(target_id,),
        )
        positive_artifact = _new_artifact(
            root_dir,
            artifact_id=_artifact_id_for_path(positive_relative),
            artifact_kind="proof_case_positive",
            relative_path=positive_relative,
            dependencies=(target_id,),
        )
        mutated_artifact = _new_artifact(
            root_dir,
            artifact_id=_artifact_id_for_path(mutated_relative),
            artifact_kind="proof_case_mutated",
            relative_path=mutated_relative,
            dependencies=(target_id,),
        )
        extra_artifacts.extend((case_artifact, positive_artifact, mutated_artifact))
        cases.append(
            {
                "schema_version": WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION,
                "case_id": case_id,
                "path": case_relative,
                "positive_path": positive_relative,
                "mutated_path": mutated_relative,
                "target_artifact_id": target_id,
                "expected_status": PROOF_CASE_EXPECTATIONS[case_id][0],
                "expected_reason_code": PROOF_CASE_EXPECTATIONS[case_id][1],
            }
        )
    return extra_artifacts, cases


def build_workspace_tracer_proof(proof_root: Path) -> Path:
    """Build the deterministic Workspace proof and return its sole root file."""

    proof_root = Path(proof_root)
    if proof_root.exists() and any(proof_root.iterdir()):
        raise WorkspaceTracerProofError("proof_output_not_empty")
    proof_root.mkdir(parents=True, exist_ok=True)
    positive = proof_root / "positive"
    profile = _offline_workspace_profile(positive)

    from synthesis.coverage_assignments import build_coverage_assignment_scheduler_factory
    from synthesis.datasets import (
        attach_dataset_release_pack_to_manifest,
        attach_dataset_release_report_to_manifest,
        attach_episode_replay_report_to_manifest,
        attach_evaluation_report_to_manifest,
        attach_profile_decision_report_to_manifest,
        attach_release_quality_audit_to_manifest,
    )
    from synthesis.episode_quality import read_episode_logs
    from synthesis.episode_replay import write_episode_replay_report
    from synthesis.evaluation import write_evaluation_report
    from synthesis.pipeline import run_foundation_pipeline
    from synthesis.profile_decisions import write_profile_decision_report
    from synthesis.qualification import (
        write_workspace_release_candidate_qualification,
    )
    from synthesis.release_pack import write_dataset_release_pack
    from synthesis.release_quality import write_release_quality_audit
    from synthesis.dataset_release import write_dataset_release_report
    from synthesis.mutation_admission import build_local_candidate_admission_evaluator
    from synthesis.workspace_environment import WorkspaceTasksEnvironment
    from synthesis.workspace_tasks import (
        workspace_mutation_policies,
        workspace_semantic_mutation_judge,
    )

    provider = _OfflineWorkspaceProvider()
    admission_environment = WorkspaceTasksEnvironment.create_fixture(
        positive / "admission_environment",
        representative=True,
    )
    admission_evaluator = build_local_candidate_admission_evaluator(
        mode="enforce",
        policies=workspace_mutation_policies(admission_environment),
        state_changing_tools=("create_workspace_task", "add_workspace_comment"),
        judge=workspace_semantic_mutation_judge,
    )
    try:
        result = run_foundation_pipeline(
            positive,
            dataset_version=profile.dataset_version,
            coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                provider
            ),
            admission_evaluator=admission_evaluator,
            enable_branching=bool(profile.features.enable_branching),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
            write_episode_logs=True,
            max_concurrency=1,
        )
    except Exception as exc:
        raise WorkspaceTracerProofError("offline_pipeline_failed") from exc
    if result.episode_logs_path is None or result.coverage_evidence_path is None:
        raise WorkspaceTracerProofError("run_completeness")
    if result.accepted_count < 5:
        raise WorkspaceTracerProofError("workspace_coverage_evidence_incomplete")

    episodes = read_episode_logs(result.episode_logs_path)
    replay_path = write_episode_replay_report(
        positive / "episode_replay_report.json",
        dataset_version=profile.dataset_version,
        episodes=episodes,
        manifest_path=result.manifest_path,
        episodes_path=result.episode_logs_path,
    )
    attach_episode_replay_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=replay_path,
    )
    evaluation_path = write_evaluation_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
    )
    attach_evaluation_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=evaluation_path,
    )
    profile_decision_path = write_profile_decision_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        runtime_seconds=1.0,
    )
    attach_profile_decision_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=profile_decision_path,
    )
    dataset_release_report_path = write_dataset_release_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        profile_decision_report_path=profile_decision_path,
    )
    attach_dataset_release_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=dataset_release_report_path,
    )
    audit_path = write_release_quality_audit(
        manifest_path=result.manifest_path,
        output_path=positive / "release_quality_audit.json",
    )
    attach_release_quality_audit_to_manifest(
        manifest_path=result.manifest_path,
        audit_path=audit_path,
    )
    pack_path = positive / "dataset_release_pack.json"
    attach_dataset_release_pack_to_manifest(
        manifest_path=result.manifest_path,
        pack_path=pack_path,
    )
    write_dataset_release_pack(
        manifest_path=result.manifest_path,
        dataset_release_report_path=dataset_release_report_path,
        output_path=pack_path,
    )
    from synthesis.release_pack import verify_dataset_release_pack

    pack_verification = verify_dataset_release_pack(pack_path)
    if _require_mapping(
        pack_verification.get("verification"), "release_pack_verification"
    ).get("status") != "passed":
        raise WorkspaceTracerProofError("release_pack_verification")
    _write_json(positive / "release_pack_verification.json", pack_verification)
    qualification_path = positive / "qualification_report.json"
    write_workspace_release_candidate_qualification(
        manifest_path=result.manifest_path,
        release_pack_path=pack_path,
        release_quality_audit_path=audit_path,
        output_path=qualification_path,
    )

    samples = _load_jsonl(result.samples_path)
    if not samples:
        raise WorkspaceTracerProofError("workspace_capability_evidence_incomplete")
    assignment_lineage_by_id = {
        _require_text(
            _require_mapping(sample["workspace_evidence"], "assignment")["assignment"].get(
                "assignment_id"
            ),
            "assignment",
        ): dict(
            _require_mapping(sample["workspace_evidence"], "assignment")["assignment"]
        )
        for sample in samples
        if isinstance(sample.get("workspace_evidence"), Mapping)
    }
    assignment_contract_by_id: dict[str, dict[str, object]] = {}
    for attempt in provider.attempts:
        assignment_id = _require_text(attempt.get("assignment_id"), "provider_contract")
        if assignment_id not in assignment_lineage_by_id:
            raise WorkspaceTracerProofError("provider_contract")
        assignment_contract = _require_mapping(
            attempt.get("assignment"), "provider_contract"
        )
        assignment_contract_by_id[assignment_id] = dict(assignment_contract)
        attempt["assignment_lineage"] = assignment_lineage_by_id[assignment_id]
    first_binding = _require_mapping(samples[0].get("workspace_evidence"), "workspace_capability_evidence_incomplete")
    plan_record = _require_mapping(
        _require_mapping(first_binding.get("plan"), "plan_identity").get("plan_record"),
        "plan_identity",
    )
    from synthesis.compatibility import verify_compatibility_corpus
    from synthesis.domain_pack import DomainPlan
    from synthesis.workspace_domain_pack import build_workspace_domain_pack

    domain_pack = build_workspace_domain_pack()
    plan = DomainPlan.from_record(plan_record, descriptor=domain_pack.descriptor)
    trace = positive / "trace"
    _write_json(trace / "domain_pack.json", domain_pack.descriptor.to_record())
    _write_json(trace / "plan.json", plan.to_record())
    _write_json(trace / "source.json", plan.admitted_source.to_record())
    _write_json(trace / "runtime.json", plan.runtime_contract.to_record())
    _write_json(
        trace / "provider.json",
        {
            "schema_version": "workspace_tracer_provider_evidence_v1",
            "evidence_class": "deterministic_offline",
            "provider_id": _OfflineWorkspaceProvider.provider_id,
            "provider_version": _OfflineWorkspaceProvider.provider_version,
            "model": _OfflineWorkspaceProvider.model,
            "parser_version": _OfflineWorkspaceProvider.parser_version,
            "attempts": provider.attempts,
        },
    )
    _write_json(
        trace / "assignments.json",
        {
            "schema_version": "workspace_tracer_assignment_evidence_v1",
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "assignments": [
                dict(_require_mapping(sample["workspace_evidence"]).get("assignment"))
                for sample in samples
                if isinstance(sample.get("workspace_evidence"), Mapping)
            ],
            "assignment_contracts": list(assignment_contract_by_id.values()),
        },
    )
    mutation_sample = next(
        (
            _require_mapping(sample.get("mutation_admission"), "mutation_admission")
            for sample in samples
            if isinstance(sample.get("mutation_admission"), Mapping)
            and _require_mapping(sample["mutation_admission"], "mutation_admission").get(
                "classification"
            )
            == "state_changing"
        ),
        None,
    )
    if mutation_sample is None:
        raise WorkspaceTracerProofError("mutation_admission_report")
    _write_json(trace / "mutation_admission.json", mutation_sample)
    qualification = _read_json(qualification_path)
    release_pack = _read_json(pack_path)
    audit = _read_json(audit_path)
    publishability_bundle, publishability_decision = _build_publishability_conformance(
        root_dir=proof_root,
        qualification=qualification,
        release_pack=release_pack,
        release_pack_path=pack_path,
        release_quality_audit=audit,
    )
    training_result = _build_training_conformance(
        root_dir=proof_root,
        release_pack=release_pack,
        publishability_bundle=publishability_bundle,
    )
    from synthesis.domain_pack import DomainAssessment

    history = _require_sequence(qualification.get("historical_decisions"), "qualification")
    last_evidence = _require_mapping(history[-1], "qualification").get("evidence")
    gates = _require_mapping(last_evidence, "qualification").get("gates")
    raw_assessment = _require_mapping(
        _require_mapping(gates, "qualification").get("domain_assessment"),
        "assessment",
    )
    assessment_keys = {
        "schema_version",
        "domain_pack_reference",
        "plan_id",
        "plan_hash",
        "evidence_references",
        "established_capability_references",
        "status",
        "reason_code",
        "assessment_id",
        "assessment_hash",
    }
    assessment = DomainAssessment.from_record(
        {key: raw_assessment[key] for key in assessment_keys},
        plan=plan,
    )
    _write_json(trace / "assessment.json", assessment.to_record())
    _write_json(trace / "qualification.json", qualification)
    _copy_tree(
        Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "compatibility",
        proof_root / "compatibility" / "corpus",
    )
    compatibility_manifest = proof_root / "compatibility" / "corpus" / "corpus_manifest.json"
    compatibility_result_obj = verify_compatibility_corpus(compatibility_manifest.parent)
    _write_json(
        proof_root / "compatibility" / "compatibility_result.json",
        compatibility_result_obj.to_record(),
    )

    artifacts = _collect_artifacts(proof_root)
    anchor_paths = {
        "domain_pack": trace / "domain_pack.json",
        "plan": trace / "plan.json",
        "source": trace / "source.json",
        "runtime": trace / "runtime.json",
        "provider": trace / "provider.json",
        "assignments": trace / "assignments.json",
        "mutation_admission_sample": trace / "mutation_admission.json",
        "manifest": result.manifest_path,
        "run_profile": positive / "run_profile.json",
        "workspace_environment": positive / "environment" / "workspace_tasks.sqlite3",
        "coverage_plan": result.coverage_plan_path or positive / "coverage_plan.json",
        "coverage_evidence": result.coverage_evidence_path,
        "samples": result.samples_path,
        "rejections": result.rejections_path,
        "episodes": result.episode_logs_path,
        "replay_report": replay_path,
        "evaluation_report": evaluation_path,
        "profile_decision_report": profile_decision_path,
        "dataset_release_report": dataset_release_report_path,
        "release_quality_audit": audit_path,
        "mutation_admission_report": positive / "mutation_admission_report.json",
        "release_pack_verification": positive / "release_pack_verification.json",
        "release_pack": pack_path,
        "qualification": trace / "qualification.json",
        "assessment": trace / "assessment.json",
        "compatibility_result": proof_root / "compatibility" / "compatibility_result.json",
        "compatibility_manifest": compatibility_manifest,
        "publishability_bundle": proof_root / "conformance" / "publishability_bundle.json",
        "publishability_decision": proof_root / "conformance" / "publishability_decision.json",
        "training_protocol": proof_root / "conformance" / "training_protocol.json",
        "training_baseline": proof_root / "conformance" / "training_baseline.json",
        "training_treatment": proof_root / "conformance" / "training_treatment.json",
        "training_evaluation": proof_root / "conformance" / "training_evaluation.json",
        "training_paired": proof_root / "conformance" / "training_paired.json",
        "training_leakage": proof_root / "conformance" / "training_leakage.json",
        "training_result": proof_root / "conformance" / "training_result.json",
    }
    for name, path in anchor_paths.items():
        if path is None:
            raise WorkspaceTracerProofError("proof_anchor_missing")
        _artifact_id_for_exact_path(artifacts, proof_root, path)
    target_paths = {
        "plan_identity": anchor_paths["plan"],
        "provider_contract": anchor_paths["provider"],
        "mutation_safety": anchor_paths["mutation_admission_sample"],
        "execution_evidence": anchor_paths["replay_report"],
        "coverage_evaluation": anchor_paths["coverage_evidence"],
        "run_completeness": anchor_paths["manifest"],
        "artifact_integrity": anchor_paths["release_pack"],
        "publishability": anchor_paths["publishability_bundle"],
        "fixture_isolation": anchor_paths["publishability_bundle"],
        "training_arms": anchor_paths["training_treatment"],
        "evaluation_leakage": anchor_paths["training_leakage"],
        "meaningful_gain": anchor_paths["training_result"],
        "cumulative_dependency": anchor_paths["qualification"],
    }
    case_artifacts, proof_cases = _build_proof_cases(
        root_dir=proof_root,
        artifacts=artifacts,
        target_paths=target_paths,
    )
    artifacts.update({item.artifact_id: item for item in case_artifacts})
    artifact_records = [artifacts[key].to_record() for key in sorted(artifacts)]
    anchors = {
        name: _artifact_id_for_exact_path(artifacts, proof_root, path)
        for name, path in anchor_paths.items()
    }
    dependencies = [
        {"from": anchors["plan"], "to": anchors["domain_pack"], "relation": "plan_binds_domain_pack"},
        {"from": anchors["plan"], "to": anchors["source"], "relation": "plan_binds_source"},
        {"from": anchors["plan"], "to": anchors["runtime"], "relation": "plan_binds_runtime"},
        {"from": anchors["runtime"], "to": anchors["workspace_environment"], "relation": "runtime_binds_environment"},
        {"from": anchors["provider"], "to": anchors["assignments"], "relation": "provider_answers_assignments"},
        {"from": anchors["samples"], "to": anchors["mutation_admission_sample"], "relation": "samples_bind_mutation_admission"},
        {"from": anchors["samples"], "to": anchors["assignments"], "relation": "samples_bind_assignments"},
        {"from": anchors["samples"], "to": anchors["plan"], "relation": "samples_bind_plan"},
        {"from": anchors["release_pack"], "to": anchors["manifest"], "relation": "pack_binds_manifest"},
        {"from": anchors["qualification"], "to": anchors["release_pack"], "relation": "qualification_binds_pack"},
        {"from": anchors["assessment"], "to": anchors["plan"], "relation": "assessment_binds_plan"},
        {"from": anchors["compatibility_result"], "to": anchors["compatibility_manifest"], "relation": "compatibility_binds_corpus"},
        {"from": anchors["publishability_decision"], "to": anchors["publishability_bundle"], "relation": "decision_binds_fixture_bundle"},
        {"from": anchors["training_result"], "to": anchors["training_protocol"], "relation": "training_binds_protocol"},
        {"from": anchors["release_pack_verification"], "to": anchors["release_pack"], "relation": "verification_binds_release_pack"},
        {"from": anchors["release_pack"], "to": anchors["mutation_admission_report"], "relation": "pack_binds_mutation_admission_report"},
    ]
    subject = {
        "domain_pack_reference": plan.domain_pack_reference.to_record(),
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "release_id": release_pack["release_id"],
        "release_pack_hash": _file_digest(pack_path)[0],
        "evidence_class": "deterministic_offline",
    }
    root: dict[str, object] = {
        "schema_version": WORKSPACE_TRACER_PROOF_SCHEMA_VERSION,
        "proof_id": "",
        "proof_hash": "",
        "root_type": WORKSPACE_TRACER_PROOF_SCHEMA_VERSION,
        "summary": SUMMARY,
        "subject": subject,
        "anchors": anchors,
        "artifacts": artifact_records,
        "proof_cases": proof_cases,
        "dependencies": dependencies,
    }
    proof_hash = _proof_identity(root)
    root["proof_hash"] = proof_hash
    root["proof_id"] = "workspace_tracer_proof_" + proof_hash.removeprefix("sha256:")[:16]
    proof_path = proof_root / WORKSPACE_TRACER_PROOF_FILENAME
    _write_json(proof_path, root)
    return proof_path


def build_workspace_tracer_proof_from_live_acceptance(
    proof_root: Path,
    acceptance_root: Path,
) -> Path:
    """Assemble the standard tracer proof from a frozen live acceptance.

    The acceptance directory is copied into the proof as an immutable positive
    leg.  All conformance fixtures and negative cases are then generated by
    the same proof machinery as the deterministic tracer; the provider class
    remains ``real_live`` and its frozen responses are verified by the normal
    production parser and assignment-membership gate.
    """

    proof_root = Path(proof_root)
    acceptance_root = Path(acceptance_root)
    if proof_root.exists() and any(proof_root.iterdir()):
        raise WorkspaceTracerProofError("proof_output_not_empty")
    if not acceptance_root.is_dir() or acceptance_root.is_symlink():
        raise WorkspaceTracerProofError("live_acceptance_missing")
    proof_root.mkdir(parents=True, exist_ok=True)
    positive = proof_root / "positive"
    _copy_tree(acceptance_root, positive)

    acceptance = _read_json(positive / "acceptance.json")
    if acceptance.get("status") != "accepted":
        raise WorkspaceTracerProofError("live_acceptance_not_accepted")
    provider_path = positive / "trace" / "provider.json"
    provider = _read_json(provider_path)
    from synthesis.workspace_live_acceptance import validate_live_provider_evidence

    try:
        validate_live_provider_evidence(provider)
    except Exception:
        raise WorkspaceTracerProofError("provider_contract") from None

    authorization_record = _read_json(positive / "authorization.json")
    if authorization_record.get("status") != "authorized":
        raise WorkspaceTracerProofError("live_authorization_missing")
    if (
        authorization_record.get("authorization") != provider.get("authorization")
        or authorization_record.get("generator") != provider.get("provider")
        or authorization_record.get("mutation_judge")
        != provider.get("mutation_judge")
    ):
        raise WorkspaceTracerProofError("live_identity_binding_mismatch")

    samples_path = positive / "samples.jsonl"
    samples = _load_jsonl(samples_path)
    if len(samples) < 5:
        raise WorkspaceTracerProofError("workspace_coverage_evidence_incomplete")
    assignment_lineage_by_id: dict[str, Mapping[str, object]] = {}
    for sample in samples:
        workspace_evidence = _require_mapping(
            sample.get("workspace_evidence"),
            "workspace_capability_evidence_incomplete",
        )
        assignment = _require_mapping(
            workspace_evidence.get("assignment"), "provider_contract"
        )
        assignment_id = _require_text(assignment.get("assignment_id"), "provider_contract")
        assignment_lineage_by_id[assignment_id] = assignment
    for raw_attempt in _require_sequence(provider.get("attempts"), "provider_contract"):
        attempt = _require_mapping(raw_attempt, "provider_contract")
        assignment_id = _require_text(attempt.get("assignment_id"), "provider_contract")
        assignment_lineage = _require_mapping(
            attempt.get("assignment_lineage"), "provider_contract"
        )
        if assignment_lineage.get("assignment_id") != assignment_id:
            raise WorkspaceTracerProofError("provider_contract")
        if attempt.get("outcome") == "validated" and assignment_id not in assignment_lineage_by_id:
            raise WorkspaceTracerProofError("provider_contract")
    assignment_contract_by_id = {
        _require_text(
            _require_mapping(attempt, "provider_contract").get("assignment_id"),
            "provider_contract",
        ): dict(
            _require_mapping(attempt, "provider_contract").get("assignment")
        )
        for attempt in _require_sequence(
            provider.get("replay_attempts"), "provider_contract"
        )
    }

    first_binding = _require_mapping(
        samples[0].get("workspace_evidence"),
        "workspace_capability_evidence_incomplete",
    )
    plan_record = _require_mapping(
        _require_mapping(first_binding.get("plan"), "plan_identity").get("plan_record"),
        "plan_identity",
    )
    from synthesis.compatibility import verify_compatibility_corpus
    from synthesis.domain_pack import DomainAssessment, DomainPlan
    from synthesis.workspace_domain_pack import build_workspace_domain_pack

    domain_pack = build_workspace_domain_pack()
    plan = DomainPlan.from_record(plan_record, descriptor=domain_pack.descriptor)
    profile_record = _read_json(positive / "run_profile.json")
    run_binding = _require_mapping(provider.get("run_binding"), "live_run_binding_malformed")
    if (
        run_binding.get("profile_id") != profile_record.get("profile_id")
        or run_binding.get("dataset_version") != profile_record.get("dataset_version")
        or run_binding.get("seed_id")
        != _require_mapping(profile_record.get("seed"), "run_profile").get("seed_id")
        or run_binding.get("seed_domain")
        != _require_mapping(profile_record.get("seed"), "run_profile").get("domain")
        or run_binding.get("plan_id") != plan.plan_id
        or run_binding.get("plan_hash") != plan.plan_hash
    ):
        raise WorkspaceTracerProofError("live_run_binding_mismatch")
    coverage_plan = _read_json(positive / "coverage_plan.json")
    if (
        run_binding.get("coverage_plan_id") != coverage_plan.get("plan_id")
        or run_binding.get("coverage_plan_hash") != coverage_plan.get("plan_hash")
    ):
        raise WorkspaceTracerProofError("live_run_binding_mismatch")
    authorized_plan = _require_mapping(
        authorization_record.get("domain_plan"), "live_authorization_missing"
    )
    authorized_coverage = _require_mapping(
        authorization_record.get("coverage_plan"), "live_authorization_missing"
    )
    if (
        authorized_plan.get("plan_id") != plan.plan_id
        or authorized_plan.get("plan_hash") != plan.plan_hash
        or authorized_coverage.get("plan_id") != coverage_plan.get("plan_id")
        or authorized_coverage.get("plan_hash") != coverage_plan.get("plan_hash")
        or authorization_record.get("source_policy_hash")
        != run_binding.get("source_policy_hash")
    ):
        raise WorkspaceTracerProofError("live_authorization_binding_mismatch")
    trace = positive / "trace"
    _write_json(trace / "domain_pack.json", domain_pack.descriptor.to_record())
    _write_json(trace / "plan.json", plan.to_record())
    _write_json(trace / "source.json", plan.admitted_source.to_record())
    _write_json(trace / "runtime.json", plan.runtime_contract.to_record())
    _write_json(
        trace / "assignments.json",
        {
            "schema_version": "workspace_tracer_assignment_evidence_v1",
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "assignments": [dict(assignment) for assignment in assignment_lineage_by_id.values()],
            "assignment_contracts": list(assignment_contract_by_id.values()),
        },
    )
    mutation_sample = next(
        (
            _require_mapping(sample.get("mutation_admission"), "mutation_admission")
            for sample in samples
            if isinstance(sample.get("mutation_admission"), Mapping)
            and _require_mapping(sample["mutation_admission"], "mutation_admission").get(
                "classification"
            )
            == "state_changing"
        ),
        None,
    )
    if mutation_sample is None:
        raise WorkspaceTracerProofError("mutation_admission_report")
    _write_json(trace / "mutation_admission.json", mutation_sample)

    qualification_path = positive / "qualification_report.json"
    pack_path = positive / "dataset_release_pack.json"
    audit_path = positive / "release_quality_audit.json"
    qualification = _read_json(qualification_path)
    release_pack = _read_json(pack_path)
    audit = _read_json(audit_path)
    from synthesis.release_pack import verify_dataset_release_pack

    pack_verification = verify_dataset_release_pack(pack_path)
    recorded_pack_verification = _read_json(positive / "release_pack_verification.json")
    if recorded_pack_verification != pack_verification or _require_mapping(
        pack_verification.get("verification"), "release_pack_verification"
    ).get("status") != "passed":
        raise WorkspaceTracerProofError("release_pack_verification")
    if (
        qualification.get("status") != "passed"
        or qualification.get("effective_qualification") != "release_candidate"
        or not isinstance(qualification.get("claims"), Mapping)
        or qualification["claims"].get("publishable") is not False
        or qualification["claims"].get("training_recommended") is not False
    ):
        raise WorkspaceTracerProofError("qualification_non_passing")

    publishability_bundle, publishability_decision = _build_publishability_conformance(
        root_dir=proof_root,
        qualification=qualification,
        release_pack=release_pack,
        release_pack_path=pack_path,
        release_quality_audit=audit,
    )
    training_result = _build_training_conformance(
        root_dir=proof_root,
        release_pack=release_pack,
        publishability_bundle=publishability_bundle,
    )

    history = _require_sequence(qualification.get("historical_decisions"), "qualification")
    last_evidence = _require_mapping(
        _require_mapping(history[-1], "qualification").get("evidence"),
        "qualification",
    )
    gates = _require_mapping(last_evidence.get("gates"), "qualification")
    raw_assessment = _require_mapping(
        _require_mapping(gates.get("domain_assessment"), "assessment"),
        "assessment",
    )
    assessment_keys = {
        "schema_version",
        "domain_pack_reference",
        "plan_id",
        "plan_hash",
        "evidence_references",
        "established_capability_references",
        "status",
        "reason_code",
        "assessment_id",
        "assessment_hash",
    }
    assessment = DomainAssessment.from_record(
        {key: raw_assessment[key] for key in assessment_keys},
        plan=plan,
    )
    _write_json(trace / "assessment.json", assessment.to_record())
    _write_json(trace / "qualification.json", qualification)

    _copy_tree(
        Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "compatibility",
        proof_root / "compatibility" / "corpus",
    )
    compatibility_manifest = proof_root / "compatibility" / "corpus" / "corpus_manifest.json"
    compatibility_result_obj = verify_compatibility_corpus(compatibility_manifest.parent)
    _write_json(
        proof_root / "compatibility" / "compatibility_result.json",
        compatibility_result_obj.to_record(),
    )

    artifacts = _collect_artifacts(proof_root)
    anchor_paths = {
        "domain_pack": trace / "domain_pack.json",
        "plan": trace / "plan.json",
        "source": trace / "source.json",
        "runtime": trace / "runtime.json",
        "provider": provider_path,
        "assignments": trace / "assignments.json",
        "mutation_admission_sample": trace / "mutation_admission.json",
        "manifest": positive / "manifest.json",
        "run_profile": positive / "run_profile.json",
        "workspace_environment": positive / "environment" / "workspace_tasks.sqlite3",
        "coverage_plan": positive / "coverage_plan.json",
        "coverage_evidence": positive / "coverage_evidence.json",
        "samples": samples_path,
        "rejections": positive / "rejections.jsonl",
        "episodes": positive / "episodes.jsonl",
        "replay_report": positive / "episode_replay_report.json",
        "evaluation_report": positive / "evaluation_report.json",
        "profile_decision_report": positive / "profile_decision_report.json",
        "dataset_release_report": positive / "dataset_release_report.json",
        "release_quality_audit": audit_path,
        "mutation_admission_report": positive / "mutation_admission_report.json",
        "release_pack_verification": positive / "release_pack_verification.json",
        "release_pack": pack_path,
        "qualification": trace / "qualification.json",
        "assessment": trace / "assessment.json",
        "compatibility_result": proof_root / "compatibility" / "compatibility_result.json",
        "compatibility_manifest": compatibility_manifest,
        "publishability_bundle": proof_root / "conformance" / "publishability_bundle.json",
        "publishability_decision": proof_root / "conformance" / "publishability_decision.json",
        "training_protocol": proof_root / "conformance" / "training_protocol.json",
        "training_baseline": proof_root / "conformance" / "training_baseline.json",
        "training_treatment": proof_root / "conformance" / "training_treatment.json",
        "training_evaluation": proof_root / "conformance" / "training_evaluation.json",
        "training_paired": proof_root / "conformance" / "training_paired.json",
        "training_leakage": proof_root / "conformance" / "training_leakage.json",
        "training_result": proof_root / "conformance" / "training_result.json",
    }
    for path in anchor_paths.values():
        _artifact_id_for_exact_path(artifacts, proof_root, path)
    target_paths = {
        "plan_identity": anchor_paths["plan"],
        "provider_contract": anchor_paths["provider"],
        "mutation_safety": anchor_paths["mutation_admission_sample"],
        "execution_evidence": anchor_paths["replay_report"],
        "coverage_evaluation": anchor_paths["coverage_evidence"],
        "run_completeness": anchor_paths["manifest"],
        "artifact_integrity": anchor_paths["release_pack"],
        "publishability": anchor_paths["publishability_bundle"],
        "fixture_isolation": anchor_paths["publishability_bundle"],
        "training_arms": anchor_paths["training_treatment"],
        "evaluation_leakage": anchor_paths["training_leakage"],
        "meaningful_gain": anchor_paths["training_result"],
        "cumulative_dependency": anchor_paths["qualification"],
    }
    case_artifacts, proof_cases = _build_proof_cases(
        root_dir=proof_root,
        artifacts=artifacts,
        target_paths=target_paths,
    )
    artifacts.update({item.artifact_id: item for item in case_artifacts})
    anchors = {
        name: _artifact_id_for_exact_path(artifacts, proof_root, path)
        for name, path in anchor_paths.items()
    }
    dependencies = [
        {"from": anchors["plan"], "to": anchors["domain_pack"], "relation": "plan_binds_domain_pack"},
        {"from": anchors["plan"], "to": anchors["source"], "relation": "plan_binds_source"},
        {"from": anchors["plan"], "to": anchors["runtime"], "relation": "plan_binds_runtime"},
        {"from": anchors["runtime"], "to": anchors["workspace_environment"], "relation": "runtime_binds_environment"},
        {"from": anchors["provider"], "to": anchors["assignments"], "relation": "provider_answers_assignments"},
        {"from": anchors["samples"], "to": anchors["mutation_admission_sample"], "relation": "samples_bind_mutation_admission"},
        {"from": anchors["samples"], "to": anchors["assignments"], "relation": "samples_bind_assignments"},
        {"from": anchors["samples"], "to": anchors["plan"], "relation": "samples_bind_plan"},
        {"from": anchors["release_pack"], "to": anchors["manifest"], "relation": "pack_binds_manifest"},
        {"from": anchors["qualification"], "to": anchors["release_pack"], "relation": "qualification_binds_pack"},
        {"from": anchors["assessment"], "to": anchors["plan"], "relation": "assessment_binds_plan"},
        {"from": anchors["compatibility_result"], "to": anchors["compatibility_manifest"], "relation": "compatibility_binds_corpus"},
        {"from": anchors["publishability_decision"], "to": anchors["publishability_bundle"], "relation": "decision_binds_fixture_bundle"},
        {"from": anchors["training_result"], "to": anchors["training_protocol"], "relation": "training_binds_protocol"},
        {"from": anchors["release_pack_verification"], "to": anchors["release_pack"], "relation": "verification_binds_release_pack"},
        {"from": anchors["release_pack"], "to": anchors["mutation_admission_report"], "relation": "pack_binds_mutation_admission_report"},
    ]
    subject = {
        "domain_pack_reference": plan.domain_pack_reference.to_record(),
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "release_id": release_pack["release_id"],
        "release_pack_hash": _file_digest(pack_path)[0],
        "evidence_class": "real_live",
    }
    root: dict[str, object] = {
        "schema_version": WORKSPACE_TRACER_PROOF_SCHEMA_VERSION,
        "proof_id": "",
        "proof_hash": "",
        "root_type": WORKSPACE_TRACER_PROOF_SCHEMA_VERSION,
        "summary": SUMMARY,
        "subject": subject,
        "anchors": anchors,
        "artifacts": [artifacts[key].to_record() for key in sorted(artifacts)],
        "proof_cases": proof_cases,
        "dependencies": dependencies,
    }
    proof_hash = _proof_identity(root)
    root["proof_hash"] = proof_hash
    root["proof_id"] = "workspace_tracer_proof_" + proof_hash.removeprefix("sha256:")[:16]
    proof_path = proof_root / WORKSPACE_TRACER_PROOF_FILENAME
    _write_json(proof_path, root)
    return proof_path


def _proof_path(value: Path) -> Path:
    if value.is_dir():
        value = value / WORKSPACE_TRACER_PROOF_FILENAME
    if not value.is_file() or value.is_symlink():
        raise WorkspaceTracerProofError("proof_root_missing")
    return value


def _validate_proof_root(
    root: Mapping[str, object],
) -> tuple[str, dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    expected_keys = {
        "schema_version",
        "proof_id",
        "proof_hash",
        "root_type",
        "summary",
        "subject",
        "anchors",
        "artifacts",
        "proof_cases",
        "dependencies",
    }
    if set(root) != expected_keys:
        raise WorkspaceTracerProofError("proof_root_malformed")
    if root.get("schema_version") != WORKSPACE_TRACER_PROOF_SCHEMA_VERSION:
        raise WorkspaceTracerProofError("proof_root_unknown_version")
    if root.get("root_type") != WORKSPACE_TRACER_PROOF_SCHEMA_VERSION:
        raise WorkspaceTracerProofError("proof_root_malformed")
    proof_hash = _require_hash(root.get("proof_hash"), "proof_identity_mismatch")
    proof_id = _require_text(root.get("proof_id"), "proof_identity_mismatch")
    if proof_id != "workspace_tracer_proof_" + proof_hash.removeprefix("sha256:")[:16]:
        raise WorkspaceTracerProofError("proof_identity_mismatch")
    if _proof_identity(root) != proof_hash:
        raise WorkspaceTracerProofError("proof_identity_mismatch")
    summary = _require_mapping(root.get("summary"), "proof_summary_malformed")
    if dict(summary) != SUMMARY:
        raise WorkspaceTracerProofError("qualification_summary_mismatch")
    subject = _require_mapping(root.get("subject"), "proof_subject_malformed")
    for field in (
        "domain_pack_reference",
        "plan_id",
        "plan_hash",
        "release_id",
        "release_pack_hash",
        "evidence_class",
    ):
        if field not in subject:
            raise WorkspaceTracerProofError("proof_subject_malformed")
    _require_hash(subject["plan_hash"], "proof_subject_malformed")
    _require_hash(subject["release_pack_hash"], "proof_subject_malformed")
    if subject.get("evidence_class") not in {"deterministic_offline", "real_live"}:
        raise WorkspaceTracerProofError("provider_evidence_class_mismatch")
    anchors = _require_mapping(root.get("anchors"), "proof_anchors_malformed")
    if not anchors or any(
        not isinstance(key, str) or not _ID_RE.fullmatch(key) or not isinstance(value, str)
        for key, value in anchors.items()
    ):
        raise WorkspaceTracerProofError("proof_anchors_malformed")
    required_anchor_names = {
        "domain_pack",
        "plan",
        "source",
        "runtime",
        "provider",
        "assignments",
        "mutation_admission_sample",
        "manifest",
        "run_profile",
        "workspace_environment",
        "coverage_plan",
        "coverage_evidence",
        "samples",
        "rejections",
        "episodes",
        "replay_report",
        "evaluation_report",
        "profile_decision_report",
        "dataset_release_report",
        "release_quality_audit",
        "mutation_admission_report",
        "release_pack_verification",
        "release_pack",
        "qualification",
        "assessment",
        "compatibility_result",
        "compatibility_manifest",
        "publishability_bundle",
        "publishability_decision",
        "training_protocol",
        "training_baseline",
        "training_treatment",
        "training_evaluation",
        "training_paired",
        "training_leakage",
        "training_result",
    }
    if not required_anchor_names <= set(anchors):
        raise WorkspaceTracerProofError("proof_anchor_missing")
    raw_artifacts = root.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise WorkspaceTracerProofError("proof_artifact_manifest_missing")
    artifacts: dict[str, Mapping[str, object]] = {}
    artifact_paths: set[str] = set()
    for raw in raw_artifacts:
        record = _require_mapping(raw, "proof_artifact_malformed")
        required = {
            "schema_version",
            "artifact_id",
            "artifact_kind",
            "artifact_schema_version",
            "path",
            "sha256",
            "byte_count",
            "identity",
            "dependencies",
        }
        if set(record) != required:
            raise WorkspaceTracerProofError("proof_artifact_malformed")
        if record.get("schema_version") != WORKSPACE_TRACER_ARTIFACT_REFERENCE_SCHEMA_VERSION:
            raise WorkspaceTracerProofError("proof_artifact_unknown_version")
        artifact_id = _require_text(record.get("artifact_id"), "proof_artifact_malformed")
        if _ID_RE.fullmatch(artifact_id) is None or artifact_id in artifacts:
            raise WorkspaceTracerProofError("proof_artifact_identity_mismatch")
        artifact_kind = _require_text(record.get("artifact_kind"), "proof_artifact_malformed")
        if artifact_kind not in REQUIRED_ARTIFACT_KINDS and not artifact_kind.startswith(
            "proof_case_"
        ):
            raise WorkspaceTracerProofError("proof_artifact_kind_unknown")
        _require_text(record.get("artifact_schema_version"), "proof_artifact_malformed")
        artifact_path = _safe_relative_path(record.get("path"))
        if artifact_path in artifact_paths:
            raise WorkspaceTracerProofError("proof_artifact_identity_mismatch")
        artifact_paths.add(artifact_path)
        _require_hash(record.get("sha256"), "proof_artifact_malformed")
        byte_count = record.get("byte_count")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise WorkspaceTracerProofError("proof_artifact_malformed")
        if not isinstance(record.get("identity"), Mapping):
            raise WorkspaceTracerProofError("proof_artifact_malformed")
        dependencies = record.get("dependencies")
        if not isinstance(dependencies, list) or dependencies != sorted(set(dependencies)):
            raise WorkspaceTracerProofError("proof_dependency_malformed")
        if any(not isinstance(item, str) or not item for item in dependencies):
            raise WorkspaceTracerProofError("proof_dependency_malformed")
        artifacts[artifact_id] = record
    if not REQUIRED_ARTIFACT_KINDS <= {
        str(record["artifact_kind"]) for record in artifacts.values()
    }:
        raise WorkspaceTracerProofError("proof_artifact_set_incomplete")
    for record in artifacts.values():
        if any(item not in artifacts for item in record["dependencies"]):
            raise WorkspaceTracerProofError("proof_dependency_missing")
    for anchor_id in anchors.values():
        if anchor_id not in artifacts:
            raise WorkspaceTracerProofError("proof_anchor_missing")
    raw_cases = root.get("proof_cases")
    if not isinstance(raw_cases, list):
        raise WorkspaceTracerProofError("proof_case_manifest_missing")
    cases: dict[str, Mapping[str, object]] = {}
    for raw in raw_cases:
        case = _require_mapping(raw, "proof_case_malformed")
        required = {
            "schema_version",
            "case_id",
            "path",
            "positive_path",
            "mutated_path",
            "target_artifact_id",
            "expected_status",
            "expected_reason_code",
        }
        if set(case) != required:
            raise WorkspaceTracerProofError("proof_case_malformed")
        if case.get("schema_version") != WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION:
            raise WorkspaceTracerProofError("proof_case_unknown_version")
        case_id = _require_text(case.get("case_id"), "proof_case_malformed")
        if case_id not in PROOF_CASE_EXPECTATIONS or case_id in cases:
            raise WorkspaceTracerProofError("proof_case_set_invalid")
        expected = PROOF_CASE_EXPECTATIONS[case_id]
        if (case.get("expected_status"), case.get("expected_reason_code")) != expected:
            raise WorkspaceTracerProofError("proof_case_expectation_mismatch")
        _safe_relative_path(case.get("path"))
        _safe_relative_path(case.get("positive_path"))
        _safe_relative_path(case.get("mutated_path"))
        target = _require_text(case.get("target_artifact_id"), "proof_case_malformed")
        if target not in artifacts:
            raise WorkspaceTracerProofError("proof_case_target_missing")
        for path_field in ("path", "positive_path", "mutated_path"):
            case_artifact_id = _artifact_id_for_path(
                _safe_relative_path(case.get(path_field))
            )
            if case_artifact_id not in artifacts:
                raise WorkspaceTracerProofError("proof_case_artifact_missing")
            if artifacts[case_artifact_id].get("path") != case.get(path_field):
                raise WorkspaceTracerProofError("proof_case_artifact_mismatch")
        cases[case_id] = case
    if set(cases) != set(PROOF_CASE_EXPECTATIONS):
        raise WorkspaceTracerProofError("proof_case_set_incomplete")
    dependencies = root.get("dependencies")
    if not isinstance(dependencies, list):
        raise WorkspaceTracerProofError("proof_dependency_malformed")
    for edge in dependencies:
        edge_record = _require_mapping(edge, "proof_dependency_malformed")
        if set(edge_record) != {"from", "to", "relation"}:
            raise WorkspaceTracerProofError("proof_dependency_malformed")
        if edge_record["from"] not in artifacts or edge_record["to"] not in artifacts:
            raise WorkspaceTracerProofError("proof_dependency_missing")
        if not isinstance(edge_record["relation"], str) or not edge_record["relation"]:
            raise WorkspaceTracerProofError("proof_dependency_malformed")
    expected_edges = {
        (anchors["plan"], anchors["domain_pack"], "plan_binds_domain_pack"),
        (anchors["plan"], anchors["source"], "plan_binds_source"),
        (anchors["plan"], anchors["runtime"], "plan_binds_runtime"),
        (anchors["runtime"], anchors["workspace_environment"], "runtime_binds_environment"),
        (anchors["provider"], anchors["assignments"], "provider_answers_assignments"),
        (anchors["samples"], anchors["mutation_admission_sample"], "samples_bind_mutation_admission"),
        (anchors["samples"], anchors["assignments"], "samples_bind_assignments"),
        (anchors["samples"], anchors["plan"], "samples_bind_plan"),
        (anchors["release_pack"], anchors["manifest"], "pack_binds_manifest"),
        (anchors["qualification"], anchors["release_pack"], "qualification_binds_pack"),
        (anchors["assessment"], anchors["plan"], "assessment_binds_plan"),
        (
            anchors["compatibility_result"],
            anchors["compatibility_manifest"],
            "compatibility_binds_corpus",
        ),
        (
            anchors["publishability_decision"],
            anchors["publishability_bundle"],
            "decision_binds_fixture_bundle",
        ),
        (anchors["training_result"], anchors["training_protocol"], "training_binds_protocol"),
        (
            anchors["release_pack_verification"],
            anchors["release_pack"],
            "verification_binds_release_pack",
        ),
        (
            anchors["release_pack"],
            anchors["mutation_admission_report"],
            "pack_binds_mutation_admission_report",
        ),
    }
    observed_edges = {
        (edge["from"], edge["to"], edge["relation"])
        for edge in dependencies
    }
    if observed_edges != expected_edges or len(dependencies) != len(expected_edges):
        raise WorkspaceTracerProofError("proof_dependency_mismatch")
    return proof_hash, artifacts, cases


def _verify_artifact_bytes(root_dir: Path, artifacts: Mapping[str, Mapping[str, object]]) -> None:
    for record in artifacts.values():
        path = _artifact_path(root_dir, record["path"])
        if not path.exists() or not path.is_file():
            raise WorkspaceTracerProofError("artifact_integrity")
        digest, byte_count = _file_digest(path)
        if digest != record["sha256"] or byte_count != record["byte_count"]:
            raise WorkspaceTracerProofError("artifact_integrity")
        if record["artifact_schema_version"] != _schema_for_path(
            path, str(record["artifact_kind"]) + "_v1"
        ):
            raise WorkspaceTracerProofError("artifact_schema_mismatch")
        if dict(record["identity"]) != _artifact_identity(path):
            raise WorkspaceTracerProofError("artifact_identity_mismatch")


def _anchor_path(
    root_dir: Path,
    artifacts: Mapping[str, Mapping[str, object]],
    anchors: Mapping[str, object],
    name: str,
) -> Path:
    artifact_id = anchors.get(name)
    if not isinstance(artifact_id, str) or artifact_id not in artifacts:
        raise WorkspaceTracerProofError("proof_anchor_missing")
    return _artifact_path(root_dir, artifacts[artifact_id]["path"])


def _verify_positive_chain(
    *,
    root_dir: Path,
    root: Mapping[str, object],
    artifacts: Mapping[str, Mapping[str, object]],
) -> tuple[list[str], dict[str, object]]:
    """Verify the production artifacts that make the real RC leg."""

    from synthesis.compatibility import verify_compatibility_corpus
    from synthesis.contracts import (
        ContractValidationError,
        validate_episode_replay_report_record,
        validate_coverage_evidence_record,
        validate_dataset_release_report_record,
        validate_evaluation_report_record,
        validate_manifest_record,
        validate_profile_decision_report_record,
        validate_release_quality_audit_record,
    )
    from synthesis.domain_pack import DomainAssessment, DomainPackDescriptor, DomainPlan
    from synthesis.episode_quality import read_episode_logs
    from synthesis.episode_replay import build_episode_replay_report
    from synthesis.qualification import (
        QUALIFICATION_REPORT_SCHEMA_VERSION,
        validate_qualification_report_record,
    )
    from synthesis.release_pack import verify_dataset_release_pack
    from synthesis.mutation_admission_reporting import validate_mutation_admission_report
    from synthesis.mutation_admission import validate_mutation_admission_evidence
    from synthesis.seeds import DomainSeed

    anchors = _require_mapping(root.get("anchors"), "proof_anchors_malformed")
    plan_path = _anchor_path(root_dir, artifacts, anchors, "plan")
    descriptor_path = _anchor_path(root_dir, artifacts, anchors, "domain_pack")
    source_path = _anchor_path(root_dir, artifacts, anchors, "source")
    runtime_path = _anchor_path(root_dir, artifacts, anchors, "runtime")
    descriptor = DomainPackDescriptor.from_record(_read_json(descriptor_path))
    plan = DomainPlan.from_record(_read_json(plan_path), descriptor=descriptor)
    subject = _require_mapping(root.get("subject"), "proof_subject_malformed")
    if plan.domain_pack_reference.to_record() != subject.get("domain_pack_reference"):
        raise WorkspaceTracerProofError("plan_identity")
    if plan.plan_id != subject.get("plan_id") or plan.plan_hash != subject.get("plan_hash"):
        raise WorkspaceTracerProofError("plan_identity")
    if _read_json(source_path) != plan.admitted_source.to_record():
        raise WorkspaceTracerProofError("source_identity_mismatch")
    if _read_json(runtime_path) != plan.runtime_contract.to_record():
        raise WorkspaceTracerProofError("runtime_identity_mismatch")

    pack_path = _anchor_path(root_dir, artifacts, anchors, "release_pack")
    pack_verification = verify_dataset_release_pack(pack_path)
    verification = _require_mapping(pack_verification.get("verification"), "release_pack_verification")
    if verification.get("status") != "passed":
        raise WorkspaceTracerProofError("release_pack_verification")
    recorded_pack_verification = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "release_pack_verification")
    )
    if recorded_pack_verification != pack_verification:
        raise WorkspaceTracerProofError("release_pack_verification")
    pack = _read_json(pack_path)
    pack_hash, pack_bytes = _file_digest(pack_path)
    if pack_hash != subject.get("release_pack_hash"):
        raise WorkspaceTracerProofError("release_pack_identity_mismatch")
    if pack.get("release_id") != subject.get("release_id"):
        raise WorkspaceTracerProofError("release_pack_identity_mismatch")

    manifest = _read_json(_anchor_path(root_dir, artifacts, anchors, "manifest"))
    validate_manifest_record(manifest)
    run_profile = _read_json(_anchor_path(root_dir, artifacts, anchors, "run_profile"))
    profile_mutation_admission = _require_mapping(
        run_profile.get("mutation_admission"), "run_profile"
    )
    if (
        run_profile.get("schema_version") != "run_profile_v4"
        or run_profile.get("profile_purpose") != "release_candidate"
        or profile_mutation_admission.get("mode") != "enforce"
    ):
        raise WorkspaceTracerProofError("run_profile_incomplete")
    seed_record = _require_mapping(run_profile.get("seed"), "run_profile")
    seed = DomainSeed(
        seed_id=_require_text(seed_record.get("seed_id"), "run_profile"),
        domain=_require_text(seed_record.get("domain"), "run_profile"),
        description=_require_text(seed_record.get("description"), "run_profile"),
        task_taxonomy=tuple(
            _require_text(item, "run_profile")
            for item in _require_sequence(seed_record.get("task_taxonomy"), "run_profile")
        ),
    )
    release_report = _read_json(_anchor_path(root_dir, artifacts, anchors, "dataset_release_report"))
    validate_dataset_release_report_record(release_report)
    evaluation = _read_json(_anchor_path(root_dir, artifacts, anchors, "evaluation_report"))
    validate_evaluation_report_record(evaluation)
    profile_decision = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "profile_decision_report")
    )
    validate_profile_decision_report_record(profile_decision)
    audit = _read_json(_anchor_path(root_dir, artifacts, anchors, "release_quality_audit"))
    validate_release_quality_audit_record(audit)
    mutation_report = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "mutation_admission_report")
    )
    try:
        validate_mutation_admission_report(mutation_report)
    except (TypeError, ValueError):
        raise WorkspaceTracerProofError("mutation_admission_report") from None
    mutation_sample = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "mutation_admission_sample")
    )
    try:
        validate_mutation_admission_evidence(mutation_sample)
    except (TypeError, ValueError):
        raise WorkspaceTracerProofError("mutation_admission") from None
    if (
        mutation_sample.get("mode") != "enforce"
        or mutation_sample.get("admission_outcome") != "judge_supported"
    ):
        raise WorkspaceTracerProofError("mutation_admission")
    coverage = _read_json(_anchor_path(root_dir, artifacts, anchors, "coverage_evidence"))
    validate_coverage_evidence_record(coverage)
    coverage_plan = _read_json(_anchor_path(root_dir, artifacts, anchors, "coverage_plan"))
    coverage_plan_id = _require_text(coverage_plan.get("plan_id"), "coverage_plan")
    coverage_plan_hash = _require_hash(coverage_plan.get("plan_hash"), "coverage_plan")
    coverage_identity = _require_mapping(coverage.get("identities"), "coverage_evidence")
    coverage_plan_identity = _require_mapping(
        coverage_identity.get("plan"), "coverage_evidence"
    )
    if (
        coverage_plan_identity.get("plan_id") != coverage_plan_id
        or coverage_plan_identity.get("identity_hash") != coverage_plan_hash
    ):
        raise WorkspaceTracerProofError("coverage_plan_identity_mismatch")
    samples = _load_jsonl(_anchor_path(root_dir, artifacts, anchors, "samples"))
    rejections = _load_jsonl(_anchor_path(root_dir, artifacts, anchors, "rejections"))
    if len(samples) < 5 or coverage.get("fulfillment", {}).get("status") != "fulfilled":
        raise WorkspaceTracerProofError("workspace_coverage_evidence_incomplete")
    if any(
        not isinstance(sample.get("workspace_evidence"), Mapping)
        for sample in samples
    ):
        raise WorkspaceTracerProofError("workspace_capability_evidence_incomplete")
    if any(
        _require_mapping(sample.get("verification"), "execution_evidence").get("passed") is not True
        for sample in samples
    ):
        raise WorkspaceTracerProofError("execution_evidence")
    if rejections and not all(isinstance(item, Mapping) for item in rejections):
        raise WorkspaceTracerProofError("run_completeness")

    replay = _read_json(_anchor_path(root_dir, artifacts, anchors, "replay_report"))
    validate_episode_replay_report_record(replay)
    if replay.get("decision", {}).get("status") != "passed":
        raise WorkspaceTracerProofError("replay_evidence")
    replay_episodes = read_episode_logs(_anchor_path(root_dir, artifacts, anchors, "episodes"))
    replay_recomputed = build_episode_replay_report(
        dataset_version=str(pack.get("dataset_version")),
        episodes=replay_episodes,
        manifest_path=_anchor_path(root_dir, artifacts, anchors, "manifest"),
        episodes_path=_anchor_path(root_dir, artifacts, anchors, "episodes"),
    )
    if replay_recomputed != replay:
        raise WorkspaceTracerProofError("replay_identity_mismatch")
    provider = _read_json(_anchor_path(root_dir, artifacts, anchors, "provider"))
    evidence_class = provider.get("evidence_class")
    if evidence_class not in {"deterministic_offline", "real_live"}:
        raise WorkspaceTracerProofError("provider_evidence_class_mismatch")
    if evidence_class == "real_live":
        from synthesis.workspace_live_acceptance import validate_live_provider_evidence

        try:
            validate_live_provider_evidence(provider)
        except Exception:
            raise WorkspaceTracerProofError("provider_contract") from None
    replay_attempts = provider.get("replay_attempts", provider.get("attempts"))
    if not provider.get("attempts") or not isinstance(replay_attempts, list) or any(
        not isinstance(attempt, Mapping)
        or not isinstance(attempt.get("assignment_id"), str)
        or not _HASH_RE.fullmatch(str(attempt.get("request_hash", "")))
        or not _HASH_RE.fullmatch(str(attempt.get("response_hash", "")))
        for attempt in replay_attempts
    ):
        raise WorkspaceTracerProofError("provider_contract")
    try:
        replayed_attempt_count = replay_provider_attempts(
            root_dir=root_dir,
            artifacts=artifacts,
            anchors=anchors,
            plan=plan,
            seed=seed,
            provider=provider,
        )
    except WorkspaceTracerProofError:
        raise
    except Exception:
        raise WorkspaceTracerProofError("provider_contract") from None
    if replayed_attempt_count != len(replay_attempts):
        raise WorkspaceTracerProofError("provider_contract")

    counts = _require_mapping(mutation_report.get("counts"), "mutation_admission_report")
    if (
        counts.get("accepted") != len(samples)
        or counts.get("rejected") != len(rejections)
        or counts.get("evidence_records") != len(samples) + len(rejections)
    ):
        raise WorkspaceTracerProofError("mutation_admission_report")

    qualification = _read_json(_anchor_path(root_dir, artifacts, anchors, "qualification"))
    validate_qualification_report_record(qualification)
    if qualification.get("schema_version") != QUALIFICATION_REPORT_SCHEMA_VERSION:
        raise WorkspaceTracerProofError("qualification_unknown_version")
    if qualification.get("status") != "passed" or qualification.get("effective_qualification") != "release_candidate":
        raise WorkspaceTracerProofError("qualification_non_passing")
    if qualification.get("claims", {}).get("publishable") is not False or qualification.get("claims", {}).get("training_recommended") is not False:
        raise WorkspaceTracerProofError("qualification_summary_mismatch")
    binding = _require_mapping(qualification.get("qualification_binding"), "qualification_binding")
    if binding.get("release_pack_hash") != pack_hash or binding.get("release_pack_byte_count") != pack_bytes:
        raise WorkspaceTracerProofError("qualification_identity_mismatch")

    assessment = _read_json(_anchor_path(root_dir, artifacts, anchors, "assessment"))
    try:
        assessment_object = DomainAssessment.from_record(assessment, plan=plan)
    except (ContractValidationError, KeyError, TypeError, ValueError):
        raise WorkspaceTracerProofError("domain_assessment") from None
    if assessment_object.status != "established":
        raise WorkspaceTracerProofError("domain_assessment")
    compatibility_result = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "compatibility_result")
    )
    if compatibility_result.get("status") != "passed":
        raise WorkspaceTracerProofError("compatibility")
    compatibility_manifest_path = _anchor_path(
        root_dir, artifacts, anchors, "compatibility_manifest"
    )
    compatibility_result_obj = verify_compatibility_corpus(
        compatibility_manifest_path.parent
    )
    if (
        compatibility_result_obj.status != "passed"
        or compatibility_result_obj.to_record() != compatibility_result
    ):
        raise WorkspaceTracerProofError("compatibility")

    return [
        "artifact_integrity",
        "domain_pack",
        "plan",
        "source",
        "runtime",
        "provider",
        "assignment",
        "sample",
        "rejection",
        "episode",
        "replay",
        "report",
        "release_pack",
        "assessment",
        "qualification",
        "compatibility",
    ], {
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "release_pack_hash": pack_hash,
        "release_id": str(pack.get("release_id")),
        "sample_count": len(samples),
        "rejection_count": len(rejections),
    }


def _verify_conformance(
    *,
    root_dir: Path,
    root: Mapping[str, object],
    artifacts: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Verify fixture paths while keeping them outside effective state."""

    from synthesis.publishability import (
        evaluate_publishability,
        validate_publishability_bundle_record,
        validate_publishability_decision_record,
    )
    from synthesis.training_recommendation import (
        CONFORMANCE_FIXTURE_EVIDENCE_CLASS,
        evaluate_training_recommendation,
        validate_training_recommendation_result_record,
    )

    anchors = _require_mapping(root.get("anchors"), "proof_anchors_malformed")
    bundle = _read_json(_anchor_path(root_dir, artifacts, anchors, "publishability_bundle"))
    decision = _read_json(
        _anchor_path(root_dir, artifacts, anchors, "publishability_decision")
    )
    validate_publishability_bundle_record(bundle)
    validate_publishability_decision_record(decision)
    if bundle.get("evidence_class") != "conformance_fixture":
        raise WorkspaceTracerProofError("fixture_isolation")
    if decision.get("evidence_class") != "conformance_fixture":
        raise WorkspaceTracerProofError("fixture_isolation")
    if decision.get("status") != "denied" or decision.get("effective_qualification") != "release_candidate":
        raise WorkspaceTracerProofError("publishability_conformance")
    if decision.get("conformance", {}).get("status") != "passed":
        raise WorkspaceTracerProofError("publishability_conformance")
    policy = _require_mapping(bundle.get("authority_policy"), "publishability")
    release_pack_verification = _require_mapping(
        bundle.get("release_pack_verification"), "publishability"
    )
    validity = _require_mapping(bundle.get("validity"), "publishability")
    recomputed_decision = evaluate_publishability(
        bundle=bundle,
        trusted_keys={
            "approval-key": "workspace-tracer-approval-key",
            "risk-key": "workspace-tracer-risk-key",
        },
        trusted_policy_hashes=[str(policy["policy_hash"])],
        trusted_bundle_content_hashes=[str(bundle["bundle_content_hash"])],
        trusted_release_pack_verification_hashes=[
            str(release_pack_verification["verification_hash"])
        ],
        now=str(validity["checked_at"]),
        release_pack_path=_anchor_path(root_dir, artifacts, anchors, "release_pack"),
    )
    if recomputed_decision != decision:
        raise WorkspaceTracerProofError("publishability_conformance")

    protocol = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_protocol"))
    baseline = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_baseline"))
    treatment = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_treatment"))
    evaluation = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_evaluation"))
    paired = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_paired"))
    leakage = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_leakage"))
    training_result = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_result"))
    if protocol.get("evidence_class") != CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        raise WorkspaceTracerProofError("fixture_isolation")
    validate_training_recommendation_result_record(training_result)
    if training_result.get("evidence_class") != CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        raise WorkspaceTracerProofError("fixture_isolation")
    recomputed = evaluate_training_recommendation(
        protocol=protocol,
        baseline=baseline,
        treatment=treatment,
        evaluation=evaluation,
        paired_results=paired,
        leakage=leakage,
        expected_evidence_class=CONFORMANCE_FIXTURE_EVIDENCE_CLASS,
    )
    if recomputed != training_result:
        raise WorkspaceTracerProofError("training_conformance")
    if training_result.get("decision", {}).get("status") != "protocol_conformance_passed":
        raise WorkspaceTracerProofError("training_conformance")
    if training_result.get("conformance", {}).get("status") != "passed":
        raise WorkspaceTracerProofError("training_conformance")
    return (
        {
            "status": "passed",
            "effective_qualification": "release_candidate",
            "decision_id": decision.get("decision_id"),
        },
        {
            "status": "passed",
            "effective_qualification": "release_candidate",
            "result_id": training_result.get("result_id"),
        },
    )


def _verify_mutated_case_behavior(
    *,
    root_dir: Path,
    root: Mapping[str, object],
    case: Mapping[str, object],
    positive_value: object,
    mutated_value: object,
    artifacts: Mapping[str, Mapping[str, object]],
) -> tuple[str, str]:
    """Exercise the bounded contract selected by one negative case."""

    case_id = str(case["case_id"])
    expected_status, expected_reason = PROOF_CASE_EXPECTATIONS[case_id]
    anchors = _require_mapping(root.get("anchors"), "proof_anchors_malformed")

    def expected_if(condition: bool) -> tuple[str, str]:
        if not condition:
            raise WorkspaceTracerProofError("proof_case_expectation_mismatch")
        return expected_status, expected_reason

    if case_id == "plan_identity":
        from synthesis.domain_pack import DomainPackDescriptor, DomainPlan

        descriptor = DomainPackDescriptor.from_record(
            _read_json(_anchor_path(root_dir, artifacts, anchors, "domain_pack"))
        )
        try:
            mutated_plan = DomainPlan.from_record(
                _require_mapping(mutated_value, "proof_case_mutation"),
                descriptor=descriptor,
            )
        except (KeyError, TypeError, ValueError):
            return expected_status, expected_reason
        return expected_if(
            mutated_plan.plan_id
            != _require_mapping(positive_value, "proof_case_positive").get("plan_id")
        )

    if case_id == "provider_contract":
        attempts = _require_sequence(
            _require_mapping(mutated_value, "proof_case_mutation").get("attempts"),
            "proof_case_mutation",
        )
        first_attempt = _require_mapping(attempts[0], "proof_case_mutation")
        return expected_if(
            _HASH_RE.fullmatch(str(first_attempt.get("response_hash", ""))) is None
        )

    if case_id == "mutation_safety":
        from synthesis.mutation_admission import validate_mutation_admission_evidence

        try:
            validate_mutation_admission_evidence(mutated_value)
        except (TypeError, ValueError):
            return expected_status, expected_reason
        raise WorkspaceTracerProofError("proof_case_expectation_mismatch")

    if case_id == "execution_evidence":
        mutated_decision = _require_mapping(mutated_value, "proof_case_mutation").get(
            "decision"
        )
        return expected_if(
            _require_mapping(mutated_decision, "proof_case_mutation").get("status")
            != "passed"
        )

    if case_id == "coverage_evaluation":
        fulfillment = _require_mapping(
            _require_mapping(mutated_value, "proof_case_mutation").get("fulfillment"),
            "proof_case_mutation",
        )
        return expected_if(fulfillment.get("status") == "incomplete")

    if case_id == "run_completeness":
        positive_manifest = _require_mapping(positive_value, "proof_case_positive")
        mutated_manifest = _require_mapping(mutated_value, "proof_case_mutation")
        return expected_if(
            mutated_manifest.get("accepted_count") != positive_manifest.get("accepted_count")
            and mutated_manifest.get("accepted_count") == 0
        )

    if case_id == "artifact_integrity":
        from synthesis.release_pack import verify_dataset_release_pack

        mutated_path = _artifact_path(root_dir, case["mutated_path"])
        try:
            verification = verify_dataset_release_pack(mutated_path)
        except Exception:
            return expected_status, expected_reason
        nested = verification.get("verification")
        return expected_if(
            not isinstance(nested, Mapping) or nested.get("status") != "passed"
        )

    if case_id == "publishability":
        from synthesis.publishability import evaluate_publishability

        bundle = _require_mapping(mutated_value, "proof_case_mutation")
        scope = _require_mapping(bundle.get("requested_scope"), "proof_case_mutation")
        policy = _require_mapping(bundle.get("authority_policy"), "proof_case_mutation")
        pack_verification = _require_mapping(
            bundle.get("release_pack_verification"), "proof_case_mutation"
        )
        validity = _require_mapping(bundle.get("validity"), "proof_case_mutation")
        decision = evaluate_publishability(
            bundle=bundle,
            trusted_keys={
                "approval-key": "workspace-tracer-approval-key",
                "risk-key": "workspace-tracer-risk-key",
            },
            trusted_policy_hashes=[str(policy["policy_hash"])],
            trusted_bundle_content_hashes=[str(bundle["bundle_content_hash"])],
            trusted_release_pack_verification_hashes=[
                str(pack_verification["verification_hash"])
            ],
            now=str(validity["checked_at"]),
            release_pack_path=_anchor_path(root_dir, artifacts, anchors, "release_pack"),
        )
        return expected_if(
            scope.get("access") == "public"
            and any(
                code in {"scope_mismatch", "evidence_malformed"}
                for code in decision.get("reason_codes", ())
            )
        )

    if case_id == "fixture_isolation":
        return expected_if(
            _require_mapping(mutated_value, "proof_case_mutation").get("evidence_class")
            == "real"
        )

    if case_id in {"training_arms", "evaluation_leakage"}:
        from synthesis.training_recommendation import evaluate_training_recommendation

        protocol = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_protocol"))
        baseline = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_baseline"))
        treatment = (
            mutated_value
            if case_id == "training_arms"
            else _read_json(_anchor_path(root_dir, artifacts, anchors, "training_treatment"))
        )
        evaluation = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_evaluation"))
        paired = _read_json(_anchor_path(root_dir, artifacts, anchors, "training_paired"))
        leakage = (
            _read_json(_anchor_path(root_dir, artifacts, anchors, "training_leakage"))
            if case_id == "training_arms"
            else mutated_value
        )
        result = evaluate_training_recommendation(
            protocol=protocol,
            baseline=baseline,
            treatment=treatment,
            evaluation=evaluation,
            paired_results=paired,
            leakage=leakage,
            expected_evidence_class="conformance_fixture",
        )
        reason_codes = _require_mapping(result.get("decision"), "proof_case_mutation").get(
            "reason_codes", ()
        )
        return expected_if(
            result.get("status") == expected_status and expected_reason in reason_codes
        )

    if case_id == "meaningful_gain":
        bootstrap = _require_mapping(
            _require_mapping(mutated_value, "proof_case_mutation").get("bootstrap"),
            "proof_case_mutation",
        )
        lower_bound = bootstrap.get("relative_lower_bound")
        return expected_if(
            isinstance(lower_bound, (int, float))
            and not isinstance(lower_bound, bool)
            and lower_bound <= 0.01
        )

    if case_id == "cumulative_dependency":
        return expected_if(
            _require_mapping(mutated_value, "proof_case_mutation").get("status")
            == "insufficient_evidence"
        )

    raise WorkspaceTracerProofError("proof_case_set_invalid")


def _verify_proof_case(
    *,
    root_dir: Path,
    root: Mapping[str, object],
    case: Mapping[str, object],
    artifacts: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    expected_status = str(case["expected_status"])
    expected_reason = str(case["expected_reason_code"])
    target_artifact = artifacts[str(case["target_artifact_id"])]
    positive_path = _artifact_path(root_dir, case["positive_path"])
    mutated_path = _artifact_path(root_dir, case["mutated_path"])
    case_path = _artifact_path(root_dir, case["path"])
    case_record = _read_json(case_path)
    if set(case_record) != {
        "schema_version",
        "case_id",
        "target_artifact_id",
        "mutation_path",
        "expected_status",
        "expected_reason_code",
        "positive_sha256",
        "positive_byte_count",
        "mutated_sha256",
        "mutated_byte_count",
        "unrelated_artifact_ids",
        "unrelated_artifact_hashes",
    }:
        raise WorkspaceTracerProofError("proof_case_malformed")
    if case_record.get("schema_version") != WORKSPACE_TRACER_PROOF_CASE_SCHEMA_VERSION:
        raise WorkspaceTracerProofError("proof_case_unknown_version")
    if case_record.get("case_id") != case.get("case_id"):
        raise WorkspaceTracerProofError("proof_case_identity_mismatch")
    if (case_record.get("expected_status"), case_record.get("expected_reason_code")) != (
        expected_status,
        expected_reason,
    ):
        raise WorkspaceTracerProofError("proof_case_expectation_mismatch")
    positive_bytes = positive_path.read_bytes()
    mutated_bytes = mutated_path.read_bytes()
    target_path = _artifact_path(root_dir, target_artifact["path"])
    if positive_bytes != target_path.read_bytes():
        raise WorkspaceTracerProofError("proof_case_positive_copy_mismatch")
    if positive_bytes == mutated_bytes:
        raise WorkspaceTracerProofError("proof_case_not_mutated")
    if case_record.get("positive_sha256") != _hash_bytes(positive_bytes) or case_record.get("positive_byte_count") != len(positive_bytes):
        raise WorkspaceTracerProofError("proof_case_integrity")
    if case_record.get("mutated_sha256") != _hash_bytes(mutated_bytes) or case_record.get("mutated_byte_count") != len(mutated_bytes):
        raise WorkspaceTracerProofError("proof_case_integrity")
    try:
        positive_value = json.loads(positive_bytes.decode("utf-8"))
        mutated_value = json.loads(mutated_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise WorkspaceTracerProofError("proof_case_mutation_unreadable") from None
    differences = _record_difference(positive_value, mutated_value)
    mutation_path = str(case_record.get("mutation_path"))
    if differences != [mutation_path] and not (
        mutation_path == "replacement"
        and differences
        and all(
            difference == mutation_path
            or difference.startswith(mutation_path + ".")
            or difference.startswith(mutation_path + "[")
            for difference in differences
        )
    ):
        raise WorkspaceTracerProofError("proof_case_mutation_scope")
    observed_status, observed_reason = _verify_mutated_case_behavior(
        root_dir=root_dir,
        root=root,
        case=case,
        positive_value=positive_value,
        mutated_value=mutated_value,
        artifacts=artifacts,
    )
    if (observed_status, observed_reason) != (expected_status, expected_reason):
        raise WorkspaceTracerProofError("proof_case_expectation_mismatch")
    unrelated_ids = case_record.get("unrelated_artifact_ids")
    unrelated_hashes = case_record.get("unrelated_artifact_hashes")
    if not isinstance(unrelated_ids, list) or not isinstance(unrelated_hashes, Mapping):
        raise WorkspaceTracerProofError("proof_case_independence_missing")
    if set(unrelated_ids) != set(unrelated_hashes):
        raise WorkspaceTracerProofError("proof_case_independence_malformed")
    for artifact_id in unrelated_ids:
        if artifact_id not in artifacts or unrelated_hashes[artifact_id] != artifacts[artifact_id]["sha256"]:
            raise WorkspaceTracerProofError("proof_case_independence_changed")
    return {
        "case_id": case["case_id"],
        "status": "passed",
        "reason_code": expected_reason,
        "observed_status": expected_status,
        "mutation_path": case_record["mutation_path"],
    }


def verify_workspace_tracer_proof(proof_path: Path) -> dict[str, object]:
    """Verify one proof root without provider calls or mutable defaults."""

    try:
        root_path = _proof_path(proof_path)
        root = _read_json(root_path)
        proof_hash, artifacts, cases = _validate_proof_root(root)
        root_dir = root_path.parent
        _verify_artifact_bytes(root_dir, artifacts)
        _, chain = _verify_positive_chain(
            root_dir=root_dir,
            root=root,
            artifacts=artifacts,
        )
        publishability, training = _verify_conformance(
            root_dir=root_dir,
            root=root,
            artifacts=artifacts,
        )
        case_results = [
            _verify_proof_case(
                root_dir=root_dir,
                root=root,
                case=cases[case_id],
                artifacts=artifacts,
            )
            for case_id in sorted(cases)
        ]
        result = _bounded_result(
            status="passed",
            reason_codes=("workspace_tracer_proof_passed",),
            proof_identity=proof_hash,
            summary=SUMMARY,
            artifacts=[artifacts[key] for key in sorted(artifacts)],
            proof_cases=case_results,
        )
        result["chain"] = chain
        result["conformance"] = {
            "publishable": publishability,
            "training_recommended": training,
        }
        return result
    except WorkspaceTracerProofError as exc:
        reason = {
            "artifact_integrity": "artifact_integrity",
            "artifact_hash_mismatch": "artifact_integrity",
            "proof_artifact_unreadable": "artifact_integrity",
            "proof_artifact_malformed": "proof_artifact_malformed",
            "provider_contract": "provider_contract_rejected",
            "fixture_isolation": "non_qualifying_evidence_class",
            "publishability_conformance": "publishability_conformance",
            "training_conformance": "training_conformance",
        }.get(exc.reason_code, exc.reason_code)
        return _bounded_result(
            status="failed",
            reason_codes=(reason,),
        )
    except Exception:
        return _bounded_result(
            status="failed",
            reason_codes=("proof_verification_failed",),
        )
