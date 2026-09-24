"""Freeze a provider-free, reviewable three-Domain acceptance campaign plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.contacts import ContactsDomainAdapter
from agent_synthesis.mobile_messages import MobileMessagesDomainAdapter
from agent_synthesis.quality import QualityRubric
from agent_synthesis.workspace_tasks import WorkspaceTasksDomainAdapter

SOURCE_ROOT = ROOT / "tests" / "fixtures" / "agent_first_acceptance"
DOMAIN_SOURCES = {
    "contacts": (ContactsDomainAdapter, SOURCE_ROOT / "contacts.json"),
    "mobile_messages": (MobileMessagesDomainAdapter, SOURCE_ROOT / "mobile_messages.json"),
    "workspace_tasks": (WorkspaceTasksDomainAdapter, SOURCE_ROOT / "workspace_tasks.json"),
}


def _fingerprint(value: object) -> str:
    contents = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(contents).hexdigest()


def build_rehearsal(model_id: str, campaign_id: str, provider_host: str) -> dict[str, object]:
    """Inspect exact local capacity and freeze settings before authorization."""

    domains: dict[str, object] = {}
    pilot = ContactsDomainAdapter.fixture()
    pilot_state = pilot.open_run(
        RunConfiguration(run_id="pilot-exclusion", domain_id="contacts", model_id=model_id, slot_limit=16)
    ).freeze_initial_state()
    pilot_names = {
        record["name"] for record in json.loads(pilot_state.contents)["contacts"]
    }
    for domain_id, (adapter_type, source_path) in DOMAIN_SOURCES.items():
        source_bytes = source_path.read_bytes()
        adapter = (
            adapter_type(source_bytes, target_scope="all_unique")
            if domain_id == "workspace_tasks"
            else adapter_type(source_bytes)
        )
        config = RunConfiguration(
            run_id=f"{campaign_id}-{domain_id.replace('_', '-')}",
            domain_id=domain_id,
            model_id=model_id,
            slot_limit=80,
            accepted_target=40,
            generation_batch_size=8,
            max_concurrency=4,
            step_limit=12,
            total_request_limit=660,
            generation_request_limit=10,
            agent_request_limit=650,
            transport_retry_limit=0,
            decision_repair_limit=1,
            timeout_seconds=90,
            max_response_bytes=64_000,
            max_output_tokens=4_096,
            source_scope_id=f"{campaign_id}-{domain_id}",
            task_distribution_scope_id=f"{campaign_id}-{domain_id}-slots-v1",
        )
        run = adapter.open_run(config)
        slots = run.slots(80)
        frozen = run.freeze_initial_state()
        if run.known_task_capacity < 80 or len(slots) != 80:
            raise ValueError(f"{domain_id} has fewer than eighty frozen task slots")
        if len({slot.slot_id for slot in slots}) != 80:
            raise ValueError(f"{domain_id} slot ids are not unique")
        if domain_id == "contacts":
            contact_names = {record["name"] for record in json.loads(frozen.contents)["contacts"]}
            if contact_names & pilot_names:
                raise ValueError("Contacts acceptance source overlaps the pilot grounding group")
        examples = [example.__dict__ for example in adapter.reviewed_structural_examples]
        domains[domain_id] = {
            "domain_version": adapter.domain_version,
            "source_path": str(source_path.relative_to(ROOT)),
            "source_sha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
            "frozen_state_fingerprint": frozen.fingerprint,
            "known_task_capacity": run.known_task_capacity,
            "slot_ids": [slot.slot_id for slot in slots],
            "slot_scope_fingerprint": _fingerprint([slot.slot_id for slot in slots]),
            "configuration": config.normalized_public_record(),
            "reviewed_structural_examples": examples,
            "reviewed_examples_fingerprint": _fingerprint(examples),
            "required_family_floor": {"contacts": 7, "mobile_messages": 12, "workspace_tasks": 9}[domain_id],
        }
    record: dict[str, object] = {
        "schema_version": "agent_first_three_domain_acceptance_rehearsal_v1",
        "campaign_id": campaign_id,
        "authorization_status": "required",
        "collection_purpose": "held_out_dataset_acceptance",
        "provider_role_settings": {
            "task_generation": {"provider_id": "openai_compatible", "provider_host": provider_host, "model_id": model_id, "model_version": "provider-version-unavailable", "thinking_mode": "disabled"},
            "agent": {"provider_id": "openai_compatible", "provider_host": provider_host, "model_id": model_id, "model_version": "provider-version-unavailable", "thinking_mode": "disabled"},
            "quality_judge": {"mode": "disabled", "physical_request_limit": 0},
        },
        "physical_request_ceiling": {"total": 1980, "task_generation": 30, "agent": 1950, "quality_judge": 0},
        "retry_ceiling": {"transport_per_logical_request": 0, "decision_repair_per_episode": 1},
        "task_attempt_ceiling": {"total": 240, "per_domain": 80},
        "review": {
            "rubric": QualityRubric().model_dump(mode="json"),
            "cohort_rule": "first_40_admitted_in_stable_sequence_per_domain_before_labels",
            "human_review_denominator": 120,
            "minimum_human_pass_rate": 0.9,
            "maximum_largest_family_share": 0.35,
            "critical_safety_failure_limit": 0,
        },
        "exclusions": {
            "contacts_pilot_source_fingerprint": pilot_state.fingerprint,
            "contacts_pilot_grounding_names": sorted(pilot_names),
            "calibration_development_campaigns": [],
            "calibration_development_status": "none_executed_in_this_rebuild",
        },
        "domains": domains,
    }
    record["plan_fingerprint"] = _fingerprint(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="agent-acceptance-20260924")
    parser.add_argument("--model-id", default=os.environ.get("AGENT_DATA_LLM_MODEL"))
    parser.add_argument("--provider-host", default=urlparse(os.environ.get("AGENT_DATA_LLM_BASE_URL", "")).hostname)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.model_id:
        parser.error("--model-id or AGENT_DATA_LLM_MODEL is required")
    if not args.provider_host:
        parser.error("--provider-host or AGENT_DATA_LLM_BASE_URL is required")
    if args.output.exists():
        parser.error("rehearsal output already exists; choose a fresh campaign path")
    record = build_rehearsal(args.model_id, args.campaign_id, args.provider_host)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "authorization_required", "plan_fingerprint": record["plan_fingerprint"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
