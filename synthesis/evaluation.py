from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from synthesis.contracts import (
    validate_evaluation_report_record,
    validate_manifest_record,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import execute_candidate
from synthesis.tasks import CandidateTask
from synthesis.tools import build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


EVALUATION_REPORT_SCHEMA_VERSION = "evaluation_report_v1"
CONTACTS_HELDOUT_SUITE_ID = "contacts_heldout_v1"


@dataclass(frozen=True)
class HeldoutTask:
    task_id: str
    candidate: CandidateTask
    capability_tags: tuple[str, ...]


@dataclass(frozen=True)
class HeldoutSuite:
    suite_id: str
    suite_version: str
    tasks: tuple[HeldoutTask, ...]


@dataclass(frozen=True)
class HeldoutTaskResult:
    task_id: str
    capability_tags: tuple[str, ...]
    status: str
    failure_cause: str | None

    def export(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "capability_tags": list(self.capability_tags),
            "status": self.status,
            "failure_cause": self.failure_cause,
        }


@dataclass(frozen=True)
class EvaluationThresholds:
    mvp_min_heldout_pass_rate: float = 0.8
    max_regression_count: int = 0


def contacts_heldout_suite() -> HeldoutSuite:
    seed_ids = ("heldout_contacts_seed_v1",)
    common_difficulty = {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }
    tasks = (
        HeldoutTask(
            task_id="heldout_contacts_lookup_alice",
            capability_tags=("contact_lookup",),
            candidate=CandidateTask(
                candidate_id="heldout_contacts_lookup_alice",
                instruction="Held-out lookup: find Alice Zhang's contact email.",
                constraints={"must_use_tool": "lookup_contact_email", "heldout": True},
                difficulty=dict(common_difficulty),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_contacts_lookup_ben",
            capability_tags=("contact_lookup",),
            candidate=CandidateTask(
                candidate_id="heldout_contacts_lookup_ben",
                instruction="Held-out lookup: find Ben Carter's contact email.",
                constraints={"must_use_tool": "lookup_contact_email", "heldout": True},
                difficulty=dict(common_difficulty),
                tool_name="lookup_contact_email",
                arguments={"name": "Ben Carter"},
                expected_answer="ben.carter@example.test",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_contacts_followup_ben",
            capability_tags=("state_change",),
            candidate=CandidateTask(
                candidate_id="heldout_contacts_followup_ben",
                instruction="Held-out state change: find Ben Carter and record a follow-up.",
                constraints={
                    "task_type": "contact_followup",
                    "required_tools": ["lookup_contact_email", "record_contact_followup"],
                    "heldout": True,
                },
                difficulty={
                    "level": "medium",
                    "tool_count": 2,
                    "constraint_count": 2,
                    "state_changes": 1,
                    "ambiguity": "none",
                    "recovery_paths": 0,
                },
                tool_name="lookup_contact_email",
                arguments={"name": "Ben Carter"},
                expected_answer="ben.carter@example.test",
                seed_ids=seed_ids,
                expected_state={
                    "contact_followup": {
                        "name": "Ben Carter",
                        "note": "Send follow-up email to ben.carter@example.test.",
                    }
                },
            ),
        ),
        HeldoutTask(
            task_id="heldout_contacts_branch_fallback_alice",
            capability_tags=("branching",),
            candidate=_heldout_branching_candidate(seed_ids),
        ),
        HeldoutTask(
            task_id="heldout_contacts_missing_contact",
            capability_tags=("missing_contact",),
            candidate=CandidateTask(
                candidate_id="heldout_contacts_missing_contact",
                instruction="Held-out negative case: verify an unknown contact fails safely.",
                constraints={"must_use_tool": "lookup_contact_email", "heldout": True},
                difficulty={
                    "level": "easy",
                    "tool_count": 1,
                    "constraint_count": 1,
                    "state_changes": 0,
                    "ambiguity": "missing_contact",
                    "recovery_paths": 0,
                },
                tool_name="lookup_contact_email",
                arguments={"name": "Casey Missing"},
                expected_answer="casey.missing@example.test",
                seed_ids=seed_ids,
            ),
        ),
    )
    return HeldoutSuite(
        suite_id=CONTACTS_HELDOUT_SUITE_ID,
        suite_version=CONTACTS_HELDOUT_SUITE_ID,
        tasks=tasks,
    )


def build_evaluation_report(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    parent_evaluation_report_path: Path | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> dict[str, object]:
    thresholds = thresholds or EvaluationThresholds()
    manifest = _load_mapping(manifest_path, "manifest")
    validate_manifest_record(manifest)
    quality_report = _load_mapping(quality_report_path, "quality_report")
    dataset_version = _string_value(manifest.get("dataset_version"), "manifest.dataset_version")
    _ensure_quality_report_matches_dataset(quality_report, dataset_version)

    suite = contacts_heldout_suite()
    task_results = _run_suite(suite)
    counts = _counts(task_results)
    parent_comparison = _compare_parent(
        task_results,
        parent_evaluation_report_path=parent_evaluation_report_path,
    )
    counts.update(
        {
            "regressed": parent_comparison["regressed"],
            "improved": parent_comparison["improved"],
            "unchanged": parent_comparison["unchanged"],
        }
    )
    report: dict[str, object] = {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "suite": {
            "suite_id": suite.suite_id,
            "suite_version": suite.suite_version,
            "task_count": len(suite.tasks),
        },
        "profile": _profile_summary(manifest),
        "inputs": {
            "manifest_path": manifest_path.name,
            "quality_report_path": quality_report_path.name,
            "parent_evaluation_report_path": (
                parent_evaluation_report_path.name
                if parent_evaluation_report_path is not None
                else None
            ),
        },
        "counts": counts,
        "rates": {"pass_rate": _rate(counts["passed"], counts["total"])},
        "capability_slices": _capability_slices(task_results),
        "task_results": [result.export() for result in task_results],
        "thresholds": asdict(thresholds),
        "parent_comparison": parent_comparison,
        "decision": _decision(counts, thresholds),
    }
    validate_evaluation_report_record(report)
    return report


def write_evaluation_report(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    parent_evaluation_report_path: Path | None = None,
    output_path: Path | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> Path:
    report = build_evaluation_report(
        manifest_path=manifest_path,
        quality_report_path=quality_report_path,
        parent_evaluation_report_path=parent_evaluation_report_path,
        thresholds=thresholds,
    )
    destination = output_path or manifest_path.parent / "evaluation_report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _run_suite(suite: HeldoutSuite) -> list[HeldoutTaskResult]:
    results: list[HeldoutTaskResult] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        environment = ContactEnvironment.create_fixture(Path(tmpdir) / "evaluation")
        registry = build_contact_tool_registry(environment)
        verifier = ExactAnswerVerifier()
        for task in suite.tasks:
            try:
                execution = execute_candidate(task.candidate, registry)
                verification = verifier.verify(
                    task.candidate,
                    execution,
                    environment=environment,
                )
            except Exception as exc:
                results.append(
                    HeldoutTaskResult(
                        task_id=task.task_id,
                        capability_tags=task.capability_tags,
                        status="failed",
                        failure_cause=_failure_cause(exc),
                    )
                )
                continue
            failed_check = next(
                (check for check in verification.checks if not check.get("passed")),
                None,
            )
            results.append(
                HeldoutTaskResult(
                    task_id=task.task_id,
                    capability_tags=task.capability_tags,
                    status="passed" if verification.passed else "failed",
                    failure_cause=(
                        None
                        if verification.passed
                        else str(failed_check.get("cause") or "verification_failed")
                    ),
                )
            )
    return results


def _heldout_branching_candidate(seed_ids: tuple[str, ...]) -> CandidateTask:
    return CandidateTask(
        candidate_id="heldout_contacts_branch_fallback_alice",
        instruction="Held-out branch: try Alice, then fall back to Alice Zhang.",
        constraints={
            "task_type": "contact_branch_fallback",
            "required_tools": ["lookup_contact_email"],
            "expected_branch": "fallback_full_name",
            "heldout": True,
        },
        difficulty={
            "level": "medium",
            "tool_count": 1,
            "constraint_count": 2,
            "state_changes": 0,
            "ambiguity": "recoverable_short_name",
            "recovery_paths": 1,
            "branch_depth": 2,
            "fallback_count": 1,
        },
        tool_name="lookup_contact_email",
        arguments={"name": "Alice"},
        expected_answer="alice.zhang@example.test",
        seed_ids=seed_ids,
        branch_plan={
            "schema_version": "branch_plan_v1",
            "plan_id": "branch_plan_heldout_contacts_alice_fallback",
            "max_depth": 2,
            "branches": [
                {
                    "branch_id": "direct_short_name",
                    "node_type": "attempt",
                    "parent_id": None,
                    "condition": "Try the abbreviated name first.",
                    "steps": [{"tool_name": "lookup_contact_email", "arguments": {"name": "Alice"}}],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "fallback_on_failure",
                },
                {
                    "branch_id": "fallback_full_name",
                    "node_type": "fallback",
                    "parent_id": "direct_short_name",
                    "condition": "Use the full name after the abbreviated lookup fails.",
                    "steps": [
                        {
                            "tool_name": "lookup_contact_email",
                            "arguments": {"name": "Alice Zhang"},
                        }
                    ],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "accept_on_success",
                },
            ],
        },
    )


def _counts(task_results: list[HeldoutTaskResult]) -> dict[str, int]:
    passed = sum(1 for result in task_results if result.status == "passed")
    failed = len(task_results) - passed
    return {
        "total": len(task_results),
        "passed": passed,
        "failed": failed,
        "regressed": 0,
        "improved": 0,
        "unchanged": len(task_results),
    }


def _capability_slices(task_results: list[HeldoutTaskResult]) -> dict[str, dict[str, object]]:
    slices: dict[str, dict[str, int]] = {}
    for result in task_results:
        for tag in result.capability_tags:
            current = slices.setdefault(tag, {"total": 0, "passed": 0, "failed": 0})
            current["total"] += 1
            current[result.status] += 1
    return {
        tag: {
            "total": counts["total"],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "pass_rate": _rate(counts["passed"], counts["total"]),
        }
        for tag, counts in sorted(slices.items())
    }


def _compare_parent(
    task_results: list[HeldoutTaskResult],
    *,
    parent_evaluation_report_path: Path | None,
) -> dict[str, object]:
    if parent_evaluation_report_path is None:
        return {
            "supplied": False,
            "regressed": 0,
            "improved": 0,
            "unchanged": len(task_results),
            "missing_parent_task_ids": [],
            "task_changes": [],
        }
    parent = _load_mapping(parent_evaluation_report_path, "parent_evaluation_report")
    parent_results = {
        str(result.get("task_id")): str(result.get("status"))
        for result in _sequence_value(parent.get("task_results"), "parent.task_results")
        if isinstance(result, Mapping)
    }
    regressed = 0
    improved = 0
    unchanged = 0
    missing: list[str] = []
    task_changes: list[dict[str, object]] = []
    for result in task_results:
        parent_status = parent_results.get(result.task_id)
        if parent_status is None:
            missing.append(result.task_id)
            continue
        if parent_status == result.status:
            unchanged += 1
            change = "unchanged"
        elif parent_status == "passed" and result.status == "failed":
            regressed += 1
            change = "regressed"
        elif parent_status == "failed" and result.status == "passed":
            improved += 1
            change = "improved"
        else:
            change = "changed"
        task_changes.append(
            {
                "task_id": result.task_id,
                "parent_status": parent_status,
                "current_status": result.status,
                "change": change,
            }
        )
    return {
        "supplied": True,
        "regressed": regressed,
        "improved": improved,
        "unchanged": unchanged,
        "missing_parent_task_ids": missing,
        "task_changes": task_changes,
    }


def _decision(
    counts: Mapping[str, int],
    thresholds: EvaluationThresholds,
) -> dict[str, object]:
    total = counts["total"]
    if total <= 0:
        return {
            "status": "insufficient_evidence",
            "reasons": ["counts.total is unavailable or malformed"],
            "triggered_by": [],
        }
    pass_rate = _rate(counts["passed"], total)
    regressed = counts["regressed"]
    reasons: list[str] = []
    triggered_by: list[str] = []
    failed = False
    if pass_rate >= thresholds.mvp_min_heldout_pass_rate:
        triggered_by.append("pass_rate")
        reasons.append(
            f"pass_rate {pass_rate} is at or above "
            f"mvp_min_heldout_pass_rate {thresholds.mvp_min_heldout_pass_rate}"
        )
    else:
        failed = True
        reasons.append(
            f"pass_rate {pass_rate} is below "
            f"mvp_min_heldout_pass_rate {thresholds.mvp_min_heldout_pass_rate}"
        )
    if regressed <= thresholds.max_regression_count:
        triggered_by.append("regressed")
        reasons.append(
            f"regressed {regressed} is at or below "
            f"max_regression_count {thresholds.max_regression_count}"
        )
    else:
        failed = True
        reasons.append(
            f"regressed {regressed} is above "
            f"max_regression_count {thresholds.max_regression_count}"
        )
    return {
        "status": "failed" if failed else "passed",
        "reasons": reasons,
        "triggered_by": [] if failed else triggered_by,
    }


def _profile_summary(manifest: Mapping[str, Any]) -> dict[str, object] | None:
    raw_profile = manifest.get("run_profile")
    if not isinstance(raw_profile, Mapping):
        return None
    return {
        key: raw_profile[key]
        for key in (
            "schema_version",
            "profile_id",
            "generation_mode",
            "target_candidate_count",
            "config_hash",
        )
        if key in raw_profile
    }


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return loaded


def _ensure_quality_report_matches_dataset(
    quality_report: Mapping[str, Any],
    dataset_version: str,
) -> None:
    if quality_report.get("schema_version") != "quality_report_v1":
        raise ValueError("quality_report.schema_version is unsupported")
    if quality_report.get("dataset_version") != dataset_version:
        raise ValueError("quality_report.dataset_version must match manifest.dataset_version")


def _failure_cause(exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return "tool_runtime_error"
    return "verification_failed"


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _string_value(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return raw


def _sequence_value(raw: object, path: str) -> list[object]:
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a list")
    return raw
