"""Run one expressly authorized Agent-first three-Domain acceptance campaign."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.contacts import ContactsDomainAdapter
from agent_synthesis.engine import SynthesisEngine
from agent_synthesis.episode import PublicEpisode
from agent_synthesis.mobile_messages import MobileMessagesDomainAdapter
from agent_synthesis.model import OpenAICompatibleJsonAdapter
from agent_synthesis.quality import ReviewQueueConfiguration
from agent_synthesis.registry import AdapterRegistry
from agent_synthesis.workspace_tasks import WorkspaceTasksDomainAdapter
from scripts.rehearse_agent_first_acceptance import build_rehearsal

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def load_verified_plan(path: Path, expected_fingerprint: str) -> dict[str, object]:
    """Reject edits, changed sources, settings, or slot order before any calls."""

    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("plan_fingerprint") != expected_fingerprint:
        raise ValueError("acceptance_plan_identity_mismatch")
    roles = plan["provider_role_settings"]
    model_id = roles["agent"]["model_id"]
    host = roles["agent"]["provider_host"]
    expected = build_rehearsal(model_id, plan["campaign_id"], host)
    if plan != expected:
        raise ValueError("acceptance_plan_or_source_drift")
    return plan


def _domain_adapter(domain_id: str, source_path: Path):
    if domain_id == "contacts":
        return ContactsDomainAdapter.from_local_file(source_path)
    if domain_id == "mobile_messages":
        return MobileMessagesDomainAdapter.from_local_file(source_path)
    return WorkspaceTasksDomainAdapter.from_local_file(source_path, target_scope="all_unique")


def _episodes(path: Path) -> tuple[PublicEpisode, ...]:
    return tuple(
        PublicEpisode.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _domain_result(result, replay, cohort, elapsed_seconds: float, target: int) -> dict[str, object]:
    demonstrations = sorted(_episodes(result.demonstrations_path), key=lambda episode: episode.sequence)
    negatives = _episodes(result.negatives_path)
    selected = demonstrations[:target]
    families = Counter(
        episode.verification.structural_key
        for episode in selected
        if episode.verification is not None
    )
    usage = json.loads(result.provider_usage_path.read_text(encoding="utf-8"))
    quality = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
    total_tokens = sum(
        record.get("known_total_tokens") or 0
        for record in usage["roles"].values()
    )
    unknown_usage = sum(
        record["unknown_usage_count"] for record in usage["roles"].values()
    )
    no_agent_rollout_count = sum(
        not any(
            role.role == "agent" and role.physical_request_count > 0
            for role in episode.lineage.roles
        )
        for episode in selected
    )
    return {
        "run_status": result.status,
        "partial_reason": result.partial_reason,
        "task_attempt_count": result.task_attempt_count,
        "terminal_outcome_count": result.terminal_outcome_count,
        "demonstration_count": len(demonstrations),
        "negative_count": len(negatives),
        "selected_episode_ids": [episode.episode_id for episode in selected],
        "cohort_membership_hash": cohort.membership_hash if cohort is not None else None,
        "all_selected_agent_rollouts": no_agent_rollout_count == 0 and len(selected) == target,
        "selected_without_agent_rollout_count": no_agent_rollout_count,
        "all_selected_deterministic_gates_pass": all(
            episode.admission.status == "admitted" and episode.admission.gates.passed
            for episode in selected
        ) and len(selected) == target,
        "selected_unauthorized_mutation_count": sum(
            episode.mutation_authorization == "rejected" for episode in selected
        ),
        "family_distribution": dict(sorted(families.items())),
        "family_count": len(families),
        "largest_family_share": max(families.values(), default=0) / len(selected) if selected else None,
        "replay_aligned": replay.aligned,
        "yield": quality["yield"],
        "rejection_causes": dict(sorted(Counter(
            episode.outcome.reason_code or "unspecified" for episode in negatives
        ).items())),
        "duplicate_semantic_task_count": quality["duplicates"]["duplicate_semantic_task_count"],
        "recovery": quality["recovery"],
        "provider_usage": usage,
        "known_total_tokens": total_tokens,
        "unknown_usage_request_count": unknown_usage,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "elapsed_seconds_per_deterministic_episode": round(elapsed_seconds / len(demonstrations), 3) if demonstrations else None,
        "known_tokens_per_deterministic_episode": round(total_tokens / len(demonstrations), 3) if demonstrations and not unknown_usage else None,
        "price_status": "unavailable",
        "downstream_benefit_status": "unclaimed",
    }


def run_campaign(
    *,
    plan_path: Path,
    expected_fingerprint: str,
    authorization_id: str,
    base_url: str,
    api_key: str,
) -> dict[str, object]:
    """Execute a frozen plan once; a failed Domain leaves its evidence inspectable."""

    if not _SAFE_ID.fullmatch(authorization_id):
        raise ValueError("bounded_nonsecret_authorization_id_required")
    plan = load_verified_plan(plan_path, expected_fingerprint)
    roles = plan["provider_role_settings"]
    model_id = roles["agent"]["model_id"]
    if (
        not base_url
        or not api_key
        or urlparse(base_url).hostname != roles["agent"]["provider_host"]
        or roles["task_generation"] != roles["agent"]
    ):
        raise ValueError("live_provider_configuration_does_not_match_plan")
    output = plan_path.parent
    for domain_id in plan["domains"]:
        if (output / domain_id).exists():
            raise ValueError("acceptance_run_directory_already_exists")
    model = OpenAICompatibleJsonAdapter(
        model_id=model_id,
        model_version=roles["agent"]["model_version"],
        base_url=base_url,
        api_key=api_key,
        remote_model=model_id,
        thinking_mode=roles["agent"]["thinking_mode"],
    )
    report: dict[str, object] = {
        "schema_version": "agent_first_three_domain_acceptance_run_v1",
        "campaign_id": plan["campaign_id"],
        "plan_fingerprint": expected_fingerprint,
        "authorization_id": authorization_id,
        "status": "in_progress",
        "dataset_acceptance": "incomplete_pending_blind_human_review",
        "engineering_readiness": "pending_independent_checks",
        "semantic_enforcement_eligibility": "shadow_only_not_evaluated",
        "domains": {},
    }
    report_path = output / "campaign_run_report.json"
    for domain_id, domain_plan in plan["domains"].items():
        source_path = ROOT / domain_plan["source_path"]
        adapter = _domain_adapter(domain_id, source_path)
        config = RunConfiguration.model_validate(domain_plan["configuration"])
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        started = time.perf_counter()
        try:
            result = engine.run(config, output / domain_id)
            replay = engine.replay(result.run_directory)
            demos = sorted(_episodes(result.demonstrations_path), key=lambda e: e.sequence)
            cohort = None
            target = config.accepted_target
            assert target is not None
            if result.status == "completed" and len(demos) >= target:
                cohort = engine.create_review_queue(
                    result.run_directory,
                    ReviewQueueConfiguration(
                        cohort_id=f"{plan['campaign_id']}-{domain_id}-human",
                        purpose="held-out-evaluation",
                        candidate_episode_ids=tuple(episode.episode_id for episode in demos[:target]),
                        campaign_id=plan["campaign_id"],
                    ),
                ).cohort
            domain_report = _domain_result(result, replay, cohort, time.perf_counter() - started, target)
            report["domains"][domain_id] = domain_report
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if result.status != "completed" or len(demos) < target or cohort is None:
                report["status"] = "failed_incomplete_domain"
                break
        except Exception:
            report["status"] = "failed_domain_exception"
            report["domains"][domain_id] = {"status": "failed", "reason_code": "bounded_run_exception", "run_directory": domain_id}
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise
    else:
        report["status"] = "awaiting_human_labels"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-fingerprint", required=True)
    parser.add_argument("--authorize-live-provider", action="store_true", required=True)
    parser.add_argument("--authorization-id", required=True)
    args = parser.parse_args()
    try:
        report = run_campaign(
            plan_path=args.plan,
            expected_fingerprint=args.plan_fingerprint,
            authorization_id=args.authorization_id,
            base_url=os.environ.get("AGENT_DATA_LLM_BASE_URL", ""),
            api_key=os.environ.get("AGENT_DATA_API_KEY", ""),
        )
    except Exception as error:
        reason = str(error)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason):
            reason = "acceptance_run_failed"
        print(json.dumps({"status": "failed", "reason_code": reason}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.plan.parent / "campaign_run_report.json")}, sort_keys=True))
    return 0 if report["status"] == "awaiting_human_labels" else 1


if __name__ == "__main__":
    raise SystemExit(main())
