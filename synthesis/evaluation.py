from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from synthesis.contracts import (
    validate_evaluation_report_record,
    validate_manifest_record,
)
from synthesis.domain_pipeline import build_domain_pipeline_bundle
from synthesis.execution import execute_candidate
from synthesis.mobile_tasks import generate_mobile_fixture_candidates
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask


EVALUATION_REPORT_SCHEMA_VERSION = "evaluation_report_v1"
CONTACTS_HELDOUT_SUITE_ID = "contacts_heldout_v1"


@dataclass(frozen=True)
class HeldoutTask:
    task_id: str
    candidate: CandidateTask
    capability_tags: tuple[str, ...]
    expected_outcome: str = "passed"
    expected_failure_cause: str | None = None


@dataclass(frozen=True)
class HeldoutSuite:
    suite_id: str
    suite_version: str
    domain_id: str
    tasks: tuple[HeldoutTask, ...]


@dataclass(frozen=True)
class HeldoutTaskResult:
    task_id: str
    capability_tags: tuple[str, ...]
    status: str
    failure_cause: str | None
    expected_outcome: str
    observed_failure_cause: str | None

    def export(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "capability_tags": list(self.capability_tags),
            "status": self.status,
            "failure_cause": self.failure_cause,
            "expected_outcome": self.expected_outcome,
            "observed_failure_cause": self.observed_failure_cause,
        }


@dataclass(frozen=True)
class EvaluationThresholds:
    mvp_min_heldout_pass_rate: float = 0.8
    max_regression_count: int = 0
    min_capability_pass_rates: Mapping[str, float] = field(
        default_factory=lambda: {
            "contact_lookup": 1.0,
            "state_change": 1.0,
            "branching": 1.0,
            "missing_contact": 1.0,
        }
    )


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
            expected_outcome="controlled_failure",
            expected_failure_cause="verification_failed",
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
        domain_id="contacts_fixture",
        tasks=tasks,
    )


def mobile_messages_heldout_suite() -> HeldoutSuite:
    seed_ids = ("heldout_mobile_messages_seed_v1",)
    generated = {
        str(candidate.constraints.get("task_type")): candidate
        for candidate in generate_mobile_fixture_candidates(_mobile_heldout_seed())
    }
    tasks = (
        HeldoutTask(
            task_id="heldout_mobile_lookup_maya",
            capability_tags=("mobile_message_lookup",),
            candidate=_heldout_mobile_candidate(
                generated["mobile_message_lookup"],
                candidate_id="heldout_mobile_lookup_maya",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_mobile_reminder_maya",
            capability_tags=("mobile_message_to_reminder",),
            candidate=_heldout_mobile_candidate(
                generated["mobile_message_to_reminder"],
                candidate_id="heldout_mobile_reminder_maya",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_mobile_draft_reply_alex",
            capability_tags=("mobile_draft_reply",),
            candidate=_heldout_mobile_candidate(
                generated["mobile_draft_reply"],
                candidate_id="heldout_mobile_draft_reply_alex",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_mobile_branch_fallback_delivery",
            capability_tags=("mobile_branching",),
            candidate=_heldout_mobile_candidate(
                generated["mobile_branch_fallback"],
                candidate_id="heldout_mobile_branch_fallback_delivery",
                seed_ids=seed_ids,
            ),
        ),
        HeldoutTask(
            task_id="heldout_mobile_missing_message",
            capability_tags=("mobile_missing_message",),
            expected_outcome="controlled_failure",
            expected_failure_cause="verification_failed",
            candidate=CandidateTask(
                candidate_id="heldout_mobile_missing_message",
                instruction="Held-out negative case: verify a missing phone message fails safely.",
                constraints={
                    "domain": "mobile_messages_fixture",
                    "task_type": "mobile_missing_message",
                    "required_tools": ["search_phone_messages"],
                    "heldout": True,
                },
                difficulty={
                    "level": "easy",
                    "tool_count": 1,
                    "constraint_count": 2,
                    "state_changes": 0,
                    "ambiguity": "missing_message",
                    "recovery_paths": 0,
                },
                tool_name="search_phone_messages",
                arguments={"query": "nonexistent invoice", "participant": "Maya"},
                expected_answer="msg_missing_invoice",
                seed_ids=seed_ids,
            ),
        ),
    )
    return HeldoutSuite(
        suite_id="mobile_messages_heldout_v1",
        suite_version="mobile_messages_heldout_v1",
        domain_id="mobile_messages_fixture",
        tasks=tasks,
    )


def resolve_heldout_suite(domain_id: str) -> HeldoutSuite:
    normalized = "contacts_fixture" if domain_id == "contacts" else domain_id
    if normalized == "contacts_fixture":
        return contacts_heldout_suite()
    if normalized == "mobile_messages_fixture":
        return mobile_messages_heldout_suite()
    raise ValueError(f"unsupported held-out evaluation domain: {domain_id}")


def _default_thresholds_for_domain(domain_id: str) -> EvaluationThresholds:
    if domain_id == "mobile_messages_fixture":
        return EvaluationThresholds(
            min_capability_pass_rates={
                "mobile_branching": 1.0,
                "mobile_draft_reply": 1.0,
                "mobile_message_lookup": 1.0,
                "mobile_message_to_reminder": 1.0,
                "mobile_missing_message": 1.0,
            }
        )
    return EvaluationThresholds()


def build_evaluation_report(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    parent_evaluation_report_path: Path | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> dict[str, object]:
    manifest = _load_mapping(manifest_path, "manifest")
    validate_manifest_record(manifest)
    quality_report = _load_mapping(quality_report_path, "quality_report")
    dataset_version = _string_value(manifest.get("dataset_version"), "manifest.dataset_version")
    _ensure_quality_report_matches_dataset(quality_report, dataset_version)

    domain_id = _manifest_domain_id(manifest)
    suite = resolve_heldout_suite(domain_id)
    thresholds = thresholds or _default_thresholds_for_domain(suite.domain_id)
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
    capability_slices = _capability_slices(task_results)
    report: dict[str, object] = {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "suite": {
            "suite_id": suite.suite_id,
            "suite_version": suite.suite_version,
            "domain_id": suite.domain_id,
            "task_count": len(suite.tasks),
        },
        "profile": _profile_summary(manifest),
        "domain": {
            "domain_id": suite.domain_id,
            "source": "manifest.run_profile.seed.domain",
        },
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
        "capability_slices": capability_slices,
        "task_results": [result.export() for result in task_results],
        "thresholds": asdict(thresholds),
        "parent_comparison": parent_comparison,
        "decision": _decision(counts, capability_slices, thresholds),
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
        bundle = build_domain_pipeline_bundle(
            _suite_seed(suite),
            Path(tmpdir) / "evaluation",
            include_branching=True,
        )
        for task in suite.tasks:
            observed_failure_cause: str | None = None
            observed_passed = False
            try:
                execution = execute_candidate(
                    task.candidate,
                    bundle.registry,
                    policy=bundle.policy_generator(task.candidate),
                    adapter_shim=bundle.adapter_shim,
                )
                verification = bundle.verifier.verify(
                    task.candidate,
                    execution,
                    environment=bundle.environment,
                )
            except Exception as exc:
                observed_failure_cause = _failure_cause(exc, task)
                results.append(_task_result(task, observed_passed, observed_failure_cause))
                continue
            failed_check = next(
                (check for check in verification.checks if not check.get("passed")),
                None,
            )
            observed_passed = verification.passed
            observed_failure_cause = (
                None
                if verification.passed
                else str(failed_check.get("cause") or "verification_failed")
            )
            results.append(_task_result(task, observed_passed, observed_failure_cause))
    return results


def _task_result(
    task: HeldoutTask,
    observed_passed: bool,
    observed_failure_cause: str | None,
) -> HeldoutTaskResult:
    if task.expected_outcome == "passed":
        status = "passed" if observed_passed else "failed"
    elif task.expected_outcome == "controlled_failure":
        status = (
            "passed"
            if (
                not observed_passed
                and observed_failure_cause == task.expected_failure_cause
            )
            else "failed"
        )
    else:
        status = "failed"

    return HeldoutTaskResult(
        task_id=task.task_id,
        capability_tags=task.capability_tags,
        status=status,
        failure_cause=None if status == "passed" else observed_failure_cause,
        expected_outcome=task.expected_outcome,
        observed_failure_cause=observed_failure_cause,
    )


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


def _mobile_heldout_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="heldout_mobile_messages_seed_v1",
        domain="mobile_messages_fixture",
        description="Held-out synthetic phone messages evaluation seed.",
        task_taxonomy=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
            "mobile_missing_message",
        ),
    )


def _suite_seed(suite: HeldoutSuite) -> DomainSeed:
    if suite.domain_id == "contacts_fixture":
        return DomainSeed(
            seed_id="heldout_contacts_seed_v1",
            domain="contacts_fixture",
            description="Held-out contacts evaluation seed.",
            task_taxonomy=(
                "single_tool_lookup",
                "contact_followup",
                "branch_fallback",
                "missing_contact",
            ),
        )
    if suite.domain_id == "mobile_messages_fixture":
        return _mobile_heldout_seed()
    raise ValueError(f"unsupported held-out evaluation domain: {suite.domain_id}")


def _heldout_mobile_candidate(
    candidate: CandidateTask,
    *,
    candidate_id: str,
    seed_ids: tuple[str, ...],
) -> CandidateTask:
    constraints = dict(candidate.constraints)
    constraints["heldout"] = True
    return replace(
        candidate,
        candidate_id=candidate_id,
        constraints=constraints,
        seed_ids=seed_ids,
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
    capability_slices: Mapping[str, Mapping[str, object]],
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
    for capability, minimum in sorted(thresholds.min_capability_pass_rates.items()):
        capability_slice = capability_slices.get(capability)
        if capability_slice is None:
            reasons.append(f"capability {capability} slice is unavailable")
            return {
                "status": "insufficient_evidence",
                "reasons": reasons,
                "triggered_by": [],
            }
        pass_rate = float(capability_slice.get("pass_rate", 0.0))
        if pass_rate >= minimum:
            triggered_by.append(f"capability:{capability}")
            reasons.append(
                f"capability {capability} pass_rate {pass_rate} "
                f"is at or above minimum {minimum}"
            )
        else:
            failed = True
            reasons.append(
                f"capability {capability} pass_rate {pass_rate} "
                f"is below minimum {minimum}"
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
    summary = {
        key: raw_profile[key]
        for key in (
            "schema_version",
            "profile_id",
            "profile_purpose",
            "generation_mode",
            "target_candidate_count",
            "config_hash",
        )
        if key in raw_profile
    }
    domain_id = _run_profile_domain_id(raw_profile)
    if domain_id is not None:
        summary["domain"] = domain_id
    return summary


def _manifest_domain_id(manifest: Mapping[str, Any]) -> str:
    raw_profile = manifest.get("run_profile")
    if isinstance(raw_profile, Mapping):
        domain_id = _run_profile_domain_id(raw_profile)
        if domain_id is not None:
            return domain_id
    return "contacts_fixture"


def _run_profile_domain_id(raw_profile: Mapping[str, Any]) -> str | None:
    seed = raw_profile.get("seed")
    if not isinstance(seed, Mapping):
        return None
    domain = seed.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        return None
    return "contacts_fixture" if domain == "contacts" else domain


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


def _failure_cause(exc: Exception, task: HeldoutTask) -> str:
    if task.expected_outcome == "controlled_failure" and task.expected_failure_cause:
        return task.expected_failure_cause
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
