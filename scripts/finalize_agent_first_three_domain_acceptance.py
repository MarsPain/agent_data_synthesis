"""Summarize frozen Agent-first acceptance evidence after direct-human label import."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis.quality import HumanReviewLabel, ReviewCohort
from scripts.run_agent_first_three_domain_acceptance import _episodes, load_verified_plan


REQUIRED_ENGINEERING_CHECKS = frozenset({
    "core_domain_model_behavior",
    "locality",
    "replay",
    "request_budget_recovery",
    "architecture",
    "docs",
    "clean_installation",
    "accepted_engine_scale",
})


def _engineering_readiness(root: Path, plan_fingerprint: str) -> dict[str, object]:
    path = root / "engineering_readiness.json"
    if not path.exists():
        return {"status": "pending", "missing_checks": sorted(REQUIRED_ENGINEERING_CHECKS)}
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = record.get("checks") if isinstance(record, dict) else None
    if not isinstance(checks, dict) or record.get("plan_fingerprint") != plan_fingerprint:
        return {"status": "incomplete", "missing_checks": sorted(REQUIRED_ENGINEERING_CHECKS)}
    missing = sorted(REQUIRED_ENGINEERING_CHECKS - set(checks))
    invalid = sorted(
        name for name in REQUIRED_ENGINEERING_CHECKS & set(checks)
        if not isinstance(checks[name], dict)
        or checks[name].get("status") != "passed"
        or not isinstance(checks[name].get("evidence"), str)
        or not checks[name]["evidence"]
    )
    return {
        "status": "passed" if not missing and not invalid else "failed" if invalid else "incomplete",
        "missing_checks": missing,
        "failed_or_unverified_checks": invalid,
        "checks": checks,
    }


def _read_jsonl(path: Path, model_type: type) -> tuple:
    if not path.exists():
        return ()
    return tuple(
        model_type.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def summarize_campaign(plan_path: Path, expected_fingerprint: str) -> dict[str, object]:
    plan = load_verified_plan(plan_path, expected_fingerprint)
    root = plan_path.parent
    run_report_path = root / "campaign_run_report.json"
    run_report = json.loads(run_report_path.read_text(encoding="utf-8")) if run_report_path.exists() else {"domains": {}}
    target_total = sum(
        domain["configuration"]["accepted_target"]
        for domain in plan["domains"].values()
    )
    minimum_pass_rate = plan["review"]["minimum_human_pass_rate"]
    domains: dict[str, object] = {}
    all_pass = 0
    all_critical = 0
    all_reviewed = 0
    all_selected = 0
    total_known_tokens = 0
    any_unknown_usage = False
    all_domain_pass = True
    for domain_id, domain_plan in plan["domains"].items():
        run = run_report.get("domains", {}).get(domain_id)
        if run is None or "selected_episode_ids" not in run:
            domains[domain_id] = {"status": "not_run", "human_review_status": "not_started"}
            all_domain_pass = False
            continue
        expected_ids = tuple(run["selected_episode_ids"])
        target = domain_plan["configuration"]["accepted_target"]
        attempt_limit = domain_plan["configuration"]["slot_limit"]
        demonstrations_path = root / domain_id / "demonstrations.jsonl"
        demonstrations = (
            sorted(_episodes(demonstrations_path), key=lambda episode: episode.sequence)
            if demonstrations_path.exists() else []
        )
        actual_selected_ids = tuple(episode.episode_id for episode in demonstrations[:target])
        selected = demonstrations[:target]
        actual_families = Counter(
            episode.verification.structural_key
            for episode in selected
            if episode.verification is not None
        )
        episode_evidence_ok = (
            len(selected) == target
            and all(
                episode.admission.status == "admitted"
                and episode.admission.gates.passed
                and episode.mutation_authorization != "rejected"
                and any(
                    role.role == "agent" and role.physical_request_count > 0
                    for role in episode.lineage.roles
                )
                for episode in selected
            )
            and dict(sorted(actual_families.items())) == run["family_distribution"]
        )
        cohorts_path = root / domain_id / "review_cohorts.json"
        cohorts_record = json.loads(cohorts_path.read_text(encoding="utf-8")) if cohorts_path.exists() else {"cohorts": []}
        cohorts = tuple(ReviewCohort.model_validate(item) for item in cohorts_record["cohorts"])
        cohort = next((item for item in cohorts if item.campaign_id == plan["campaign_id"] and item.purpose == "held-out-evaluation"), None)
        if cohort is not None and tuple(cohort.episode_ids) != expected_ids:
            raise ValueError(f"{domain_id} frozen cohort membership differs from the selected forty")
        labels = _read_jsonl(root / domain_id / "human_review_labels.jsonl", HumanReviewLabel)
        import_report_path = root / domain_id / "review_label_import_report.json"
        import_report = (
            json.loads(import_report_path.read_text(encoding="utf-8"))
            if import_report_path.exists() else {}
        )
        foreign_or_duplicate = len({label.episode_id for label in labels}) != len(labels)
        if cohort is None:
            foreign_or_duplicate |= bool(labels)
        else:
            foreign_or_duplicate |= any(
                label.cohort_id != cohort.cohort_id
                or label.purpose != "held-out-evaluation"
                or label.episode_id not in expected_ids
                for label in labels
            )
        if foreign_or_duplicate:
            raise ValueError(f"{domain_id} has duplicate or foreign human labels")
        reviewed = len(labels)
        passed = sum(label.aggregate_verdict == "pass" for label in labels)
        failed = sum(label.aggregate_verdict == "fail" for label in labels)
        uncertain = sum(label.aggregate_verdict == "uncertain" for label in labels)
        critical = sum(
            "critical_safety_failure" in dimension.reason_codes
            for label in labels
            for dimension in label.dimensions
            if dimension.dimension == "safety"
        )
        family_floor = domain_plan["required_family_floor"]
        deterministic_ok = (
            run["run_status"] == "completed"
            and run["task_attempt_count"] <= attempt_limit
            and len(expected_ids) == target
            and actual_selected_ids == expected_ids
            and len({episode.episode_id for episode in demonstrations}) == len(demonstrations)
            and episode_evidence_ok
            and cohort is not None
            and run["cohort_membership_hash"] == cohort.membership_hash
            and run["all_selected_agent_rollouts"]
            and run["all_selected_deterministic_gates_pass"]
            and run["selected_unauthorized_mutation_count"] == 0
            and run["duplicate_semantic_task_count"] == 0
            and run["replay_aligned"]
            and run["family_count"] >= family_floor
            and run["largest_family_share"] <= plan["review"]["maximum_largest_family_share"]
        )
        review_complete = False
        if cohort is not None:
            review_complete = (
                reviewed == target
                and len(expected_ids) == target
                and import_report.get("schema_version") == "agent_review_label_import_report_v1"
                and import_report.get("complete") is True
                and any(
                    item.get("cohort_id") == cohort.cohort_id
                    and item.get("membership_hash") == cohort.membership_hash
                    and item.get("imported_label_count") == target
                    for item in import_report.get("cohorts", [])
                )
            )
        human_ok = review_complete and passed >= math.ceil(target * minimum_pass_rate) and critical == 0
        accepted = deterministic_ok and human_ok
        domains[domain_id] = {
            "status": "passed" if accepted else "incomplete" if not review_complete else "failed",
            "deterministic_gates_pass": deterministic_ok,
            "human_review_status": "complete" if review_complete else "incomplete",
            "frozen_membership_hash": cohort.membership_hash if cohort else None,
            "denominator": target,
            "reviewed_count": reviewed,
            "human_pass_count": passed,
            "human_fail_count": failed,
            "human_uncertain_count": uncertain,
            "missing_label_count": max(0, target - reviewed),
            "critical_safety_failure_count": critical,
            "human_pass_rate": passed / target,
            "required_family_floor": family_floor,
            "observed_family_count": run["family_count"],
            "largest_family_share": run["largest_family_share"],
            "known_tokens_per_human_passed_episode": (
                round(run["known_total_tokens"] / passed, 3)
                if passed and run["unknown_usage_request_count"] == 0 else None
            ),
            "elapsed_seconds_per_human_passed_episode": round(run["elapsed_seconds"] / passed, 3) if passed else None,
        }
        all_domain_pass &= accepted
        all_pass += passed
        all_critical += critical
        all_reviewed += reviewed
        all_selected += len(expected_ids)
        total_known_tokens += run["known_total_tokens"]
        any_unknown_usage |= run["unknown_usage_request_count"] > 0
    complete = all_selected == target_total and all_reviewed == target_total
    campaign_failed = str(run_report.get("status", "")).startswith("failed")
    dataset_status = (
        "failed" if campaign_failed
        else "passed" if complete and all_domain_pass and all_pass >= math.ceil(target_total * minimum_pass_rate) and all_critical == 0
        else "incomplete" if not complete
        else "failed"
    )
    engineering = _engineering_readiness(root, expected_fingerprint)
    engineering_status = engineering.get("status", "pending")
    return {
        "schema_version": "agent_first_three_domain_acceptance_decision_v1",
        "campaign_id": plan["campaign_id"],
        "plan_fingerprint": expected_fingerprint,
        "engineering_readiness": engineering,
        "dataset_acceptance": {
            "status": dataset_status,
            "denominator": target_total,
            "reviewed_count": all_reviewed,
            "human_pass_count": all_pass,
            "human_pass_rate": all_pass / target_total,
            "critical_safety_failure_count": all_critical,
            "known_tokens_per_human_passed_episode": round(total_known_tokens / all_pass, 3) if all_pass and not any_unknown_usage else None,
            "price_status": "unavailable",
            "downstream_benefit_status": "unclaimed",
            "domains": domains,
        },
        "semantic_enforcement_eligibility": {"status": "shadow_only_not_evaluated"},
        "core_cutover_status": "ready" if engineering_status == "passed" and dataset_status == "passed" else "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-fingerprint", required=True)
    args = parser.parse_args()
    report = summarize_campaign(args.plan, args.plan_fingerprint)
    path = args.plan.parent / "campaign_decision.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "core_cutover_status": report["core_cutover_status"]}, sort_keys=True))
    return 0 if report["core_cutover_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
