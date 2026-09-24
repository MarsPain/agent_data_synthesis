"""Provider-free checks at the campaign rehearsal and decision interfaces."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.finalize_agent_first_three_domain_acceptance import summarize_campaign
from scripts.rehearse_agent_first_acceptance import build_rehearsal
from scripts.run_agent_first_three_domain_acceptance import load_verified_plan, run_campaign


class AgentFirstAcceptanceCampaignTest(unittest.TestCase):
    def test_rehearsal_freezes_eighty_slots_and_reviewed_family_floors(self) -> None:
        plan = build_rehearsal("example-model", "test-acceptance", "example.test")

        self.assertEqual(plan["physical_request_ceiling"], {
            "total": 1980, "task_generation": 30, "agent": 1950, "quality_judge": 0,
        })
        self.assertEqual(plan["task_attempt_ceiling"], {"total": 240, "per_domain": 80})
        self.assertEqual(plan["review"]["human_review_denominator"], 120)
        self.assertEqual(plan["domains"]["contacts"]["known_task_capacity"], 80)
        self.assertEqual(plan["domains"]["mobile_messages"]["known_task_capacity"], 96)
        self.assertEqual(plan["domains"]["workspace_tasks"]["known_task_capacity"], 97)
        for domain_id, floor in (("contacts", 7), ("mobile_messages", 12), ("workspace_tasks", 9)):
            domain = plan["domains"][domain_id]
            self.assertEqual(len(domain["slot_ids"]), 80)
            self.assertEqual(len(set(domain["slot_ids"])), 80)
            self.assertEqual(domain["required_family_floor"], floor)
            self.assertEqual(len({example["expected_structural_key"] for example in domain["reviewed_structural_examples"]}), floor)

    def test_changed_plan_cannot_be_authorized_by_old_fingerprint(self) -> None:
        plan = build_rehearsal("example-model", "test-acceptance", "example.test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rehearsal.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(load_verified_plan(path, plan["plan_fingerprint"]), plan)
            plan["domains"]["contacts"]["configuration"]["agent_request_limit"] = 651
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "acceptance_plan_or_source_drift"):
                load_verified_plan(path, plan["plan_fingerprint"])

    def test_without_authorization_or_labels_campaign_stays_blocked(self) -> None:
        plan = build_rehearsal("example-model", "test-acceptance", "example.test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rehearsal.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "authorization_id_required"):
                run_campaign(
                    plan_path=path,
                    expected_fingerprint=plan["plan_fingerprint"],
                    authorization_id="",
                    base_url="https://example.test",
                    api_key="unused",
                )
            self.assertFalse((Path(directory) / "contacts").exists())
            decision = summarize_campaign(path, plan["plan_fingerprint"])
            self.assertEqual(decision["dataset_acceptance"]["status"], "incomplete")
            self.assertEqual(decision["engineering_readiness"]["status"], "pending")
            self.assertEqual(decision["semantic_enforcement_eligibility"]["status"], "shadow_only_not_evaluated")
            self.assertEqual(decision["core_cutover_status"], "blocked")

    def test_bare_engineering_pass_claim_cannot_establish_readiness(self) -> None:
        plan = build_rehearsal("example-model", "test-acceptance", "example.test")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "rehearsal.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            (root / "engineering_readiness.json").write_text(
                json.dumps({"status": "passed"}), encoding="utf-8"
            )

            decision = summarize_campaign(path, plan["plan_fingerprint"])

            self.assertEqual(decision["engineering_readiness"]["status"], "incomplete")
            self.assertIn("accepted_engine_scale", decision["engineering_readiness"]["missing_checks"])
            self.assertEqual(decision["core_cutover_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
