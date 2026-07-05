from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class HeldoutEvaluationTest(unittest.TestCase):
    def test_contacts_suite_has_stable_ids_and_capability_tags(self) -> None:
        from synthesis.evaluation import contacts_heldout_suite

        suite = contacts_heldout_suite()

        self.assertEqual(suite.suite_id, "contacts_heldout_v1")
        self.assertEqual(
            [task.task_id for task in suite.tasks],
            [
                "heldout_contacts_lookup_alice",
                "heldout_contacts_lookup_ben",
                "heldout_contacts_followup_ben",
                "heldout_contacts_branch_fallback_alice",
                "heldout_contacts_missing_contact",
            ],
        )
        self.assertTrue(all(task.capability_tags for task in suite.tasks))

    def test_contacts_suite_has_domain_identity(self) -> None:
        from synthesis.evaluation import contacts_heldout_suite, resolve_heldout_suite

        suite = contacts_heldout_suite()

        self.assertEqual(suite.domain_id, "contacts_fixture")
        self.assertEqual(resolve_heldout_suite("contacts").suite_id, "contacts_heldout_v1")
        self.assertEqual(
            resolve_heldout_suite("contacts_fixture").domain_id,
            "contacts_fixture",
        )

    def test_mobile_suite_has_stable_ids_and_capability_tags(self) -> None:
        from synthesis.evaluation import mobile_messages_heldout_suite

        suite = mobile_messages_heldout_suite()

        self.assertEqual(suite.suite_id, "mobile_messages_heldout_v1")
        self.assertEqual(suite.domain_id, "mobile_messages_fixture")
        self.assertEqual(
            [task.task_id for task in suite.tasks],
            [
                "heldout_mobile_lookup_maya",
                "heldout_mobile_reminder_maya",
                "heldout_mobile_draft_reply_alex",
                "heldout_mobile_branch_fallback_delivery",
                "heldout_mobile_missing_message",
            ],
        )
        observed_tags = sorted({tag for task in suite.tasks for tag in task.capability_tags})
        self.assertEqual(
            observed_tags,
            [
                "mobile_branching",
                "mobile_draft_reply",
                "mobile_message_lookup",
                "mobile_message_to_reminder",
                "mobile_missing_message",
            ],
        )

    def test_workspace_suite_has_stable_ids_and_capability_tags(self) -> None:
        from synthesis.evaluation import workspace_tasks_heldout_suite

        suite = workspace_tasks_heldout_suite()

        self.assertEqual(suite.suite_id, "workspace_tasks_heldout_v1")
        self.assertEqual(suite.domain_id, "workspace_tasks_fixture")
        self.assertEqual(
            [task.task_id for task in suite.tasks],
            [
                "heldout_workspace_lookup_launch",
                "heldout_workspace_task_creation_launch",
                "heldout_workspace_comment_update_launch",
                "heldout_workspace_branch_fallback_launch",
                "heldout_workspace_missing_item",
            ],
        )
        observed_tags = sorted({tag for task in suite.tasks for tag in task.capability_tags})
        self.assertEqual(
            observed_tags,
            [
                "workspace_branching",
                "workspace_comment_update",
                "workspace_item_lookup",
                "workspace_missing_item",
                "workspace_task_creation",
            ],
        )

    def test_resolve_heldout_suite_rejects_unsupported_domain(self) -> None:
        from synthesis.evaluation import resolve_heldout_suite

        with self.assertRaisesRegex(ValueError, "unsupported held-out evaluation domain"):
            resolve_heldout_suite("calendar_fixture")

    def test_generated_report_counts_slices_and_validates(self) -> None:
        from synthesis.contracts import validate_evaluation_report_record
        from synthesis.evaluation import build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path, quality_report_path = _write_inputs(Path(tmpdir))

            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
            )

        self.assertEqual(report["suite"]["task_count"], 5)
        self.assertEqual(report["counts"]["total"], 5)
        self.assertEqual(report["counts"]["passed"], 5)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["rates"]["pass_rate"], 1.0)
        self.assertEqual(
            report["capability_slices"]["contact_lookup"],
            {"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0},
        )
        self.assertEqual(report["capability_slices"]["missing_contact"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["missing_contact"]["failed"], 0)
        task_result = {
            result["task_id"]: result for result in report["task_results"]
        }["heldout_contacts_missing_contact"]
        self.assertEqual(task_result["status"], "passed")
        self.assertEqual(task_result["expected_outcome"], "controlled_failure")
        self.assertEqual(task_result["observed_failure_cause"], "verification_failed")
        self.assertEqual(report["decision"]["status"], "passed")
        validate_evaluation_report_record(report)

    def test_mobile_report_counts_slices_and_validates(self) -> None:
        from synthesis.contracts import validate_evaluation_report_record
        from synthesis.evaluation import build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path, quality_report_path = _write_mobile_inputs(Path(tmpdir))

            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
            )

        self.assertEqual(report["suite"]["suite_id"], "mobile_messages_heldout_v1")
        self.assertEqual(report["suite"]["domain_id"], "mobile_messages_fixture")
        self.assertEqual(report["domain"]["domain_id"], "mobile_messages_fixture")
        self.assertEqual(report["counts"]["total"], 5)
        self.assertEqual(report["counts"]["passed"], 5)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["capability_slices"]["mobile_message_lookup"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["mobile_message_to_reminder"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["mobile_draft_reply"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["mobile_missing_message"]["passed"], 1)
        self.assertEqual(report["decision"]["status"], "passed")
        validate_evaluation_report_record(report)

    def test_workspace_report_counts_slices_and_validates(self) -> None:
        from synthesis.contracts import validate_evaluation_report_record
        from synthesis.evaluation import build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path, quality_report_path = _write_workspace_inputs(Path(tmpdir))

            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
            )

        self.assertEqual(report["suite"]["suite_id"], "workspace_tasks_heldout_v1")
        self.assertEqual(report["suite"]["domain_id"], "workspace_tasks_fixture")
        self.assertEqual(report["domain"]["domain_id"], "workspace_tasks_fixture")
        self.assertEqual(report["counts"]["total"], 5)
        self.assertEqual(report["counts"]["passed"], 5)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["capability_slices"]["workspace_item_lookup"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["workspace_task_creation"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["workspace_comment_update"]["passed"], 1)
        self.assertEqual(report["capability_slices"]["workspace_missing_item"]["passed"], 1)
        self.assertEqual(report["decision"]["status"], "passed")
        validate_evaluation_report_record(report)

    def test_parent_comparison_counts_regressions_improvements_and_missing_parent_tasks(self) -> None:
        from synthesis.evaluation import build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest_path, quality_report_path = _write_inputs(tmp_path)
            parent_path = tmp_path / "parent_evaluation_report.json"
            parent = _parent_report_with_statuses(
                {
                    "heldout_contacts_lookup_alice": "passed",
                    "heldout_contacts_lookup_ben": "failed",
                    "heldout_contacts_followup_ben": "passed",
                    "heldout_contacts_branch_fallback_alice": "passed",
                }
            )
            parent_path.write_text(json.dumps(parent), encoding="utf-8")

            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
                parent_evaluation_report_path=parent_path,
            )

        self.assertEqual(report["counts"]["regressed"], 0)
        self.assertEqual(report["counts"]["improved"], 1)
        self.assertEqual(report["counts"]["unchanged"], 3)
        self.assertEqual(
            report["parent_comparison"]["missing_parent_task_ids"],
            ["heldout_contacts_missing_contact"],
        )

    def test_capability_threshold_miss_fails_decision(self) -> None:
        from synthesis.evaluation import EvaluationThresholds, build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path, quality_report_path = _write_inputs(Path(tmpdir))
            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
                thresholds=EvaluationThresholds(
                    min_capability_pass_rates={"missing_contact": 1.01}
                ),
            )

        self.assertEqual(report["decision"]["status"], "failed")
        self.assertIn(
            "capability missing_contact pass_rate 1.0 is below minimum 1.01",
            report["decision"]["reasons"],
        )

    def test_parent_comparison_treats_controlled_failure_status_as_passed(self) -> None:
        from synthesis.evaluation import build_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest_path, quality_report_path = _write_inputs(tmp_path)
            parent_path = tmp_path / "parent_evaluation_report.json"
            parent = _parent_report_with_statuses(
                {
                    "heldout_contacts_lookup_alice": "passed",
                    "heldout_contacts_lookup_ben": "passed",
                    "heldout_contacts_followup_ben": "passed",
                    "heldout_contacts_branch_fallback_alice": "passed",
                    "heldout_contacts_missing_contact": "passed",
                }
            )
            parent_path.write_text(json.dumps(parent), encoding="utf-8")

            report = build_evaluation_report(
                manifest_path=manifest_path,
                quality_report_path=quality_report_path,
                parent_evaluation_report_path=parent_path,
            )

        self.assertEqual(report["counts"]["regressed"], 0)
        self.assertEqual(report["decision"]["status"], "passed")

    def test_cli_writes_valid_report_next_to_manifest_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path, quality_report_path = _write_inputs(Path(tmpdir))

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation_report.py",
                    "--manifest",
                    str(manifest_path),
                    "--quality-report",
                    str(quality_report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            output_path = manifest_path.parent / "evaluation_report.json"
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["inputs"]["manifest_path"], "manifest.json")
            self.assertNotIn(str(manifest_path.parent), output_path.read_text(encoding="utf-8"))

    def test_cli_rejects_malformed_input_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            quality_report_path = Path(tmpdir) / "quality_report.json"
            quality_report_path.write_text("{}", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation_report.py",
                    "--manifest",
                    str(Path(tmpdir) / "missing_manifest.json"),
                    "--quality-report",
                    str(quality_report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("manifest", result.stderr)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    manifest = {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_test",
        "parent_dataset_version": None,
        "accepted_count": 4,
        "rejected_count": 1,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
        },
        "quality": {"success_rate": 0.8, "executable_rate": 1.0},
        "environment_versions": ["env_contacts_v2"],
        "tool_versions": ["tool_lookup_contact_email_v1", "tool_record_contact_followup_v1"],
        "verifier_versions": ["verifier_exact_answer_state_v2"],
        "generator_config_hashes": ["scripted_task_generation_v1"],
        "rejection_causes": {},
        "run_profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "foundation_scale_probe_25",
            "generation_mode": "deterministic_scale_probe",
            "target_candidate_count": 25,
            "config_hash": "sha256:" + "1" * 64,
            "enabled_features": [],
        },
    }
    quality_report = {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_test",
        "counts": {"total": 5, "accepted": 4, "rejected": 1, "executable": 5},
        "rates": {"success_rate": 0.8, "executable_rate": 1.0},
        "rejection_causes": {},
        "slices": {},
    }
    manifest_path = tmp_path / "manifest.json"
    quality_report_path = tmp_path / "quality_report.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    quality_report_path.write_text(json.dumps(quality_report), encoding="utf-8")
    return manifest_path, quality_report_path


def _write_mobile_inputs(tmp_path: Path) -> tuple[Path, Path]:
    manifest = {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_mobile_test",
        "parent_dataset_version": None,
        "accepted_count": 4,
        "rejected_count": 0,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
        },
        "quality": {"success_rate": 1.0, "executable_rate": 1.0},
        "environment_versions": ["mobile_messages_fixture_v1"],
        "tool_versions": [
            "tool_search_phone_messages_v1",
            "tool_create_phone_reminder_v1",
            "tool_draft_message_reply_v1",
        ],
        "verifier_versions": ["verifier_exact_answer_state_v2"],
        "generator_config_hashes": ["mobile-fixture-task-generation-v1"],
        "rejection_causes": {},
        "run_profile": {
            "schema_version": "run_profile_v2",
            "profile_id": "profile_local_mobile_messages",
            "profile_purpose": "diagnostic_probe",
            "generation_mode": "mobile_fixture",
            "target_candidate_count": 4,
            "config_hash": "sha256:" + "2" * 64,
            "enabled_features": [],
            "seed": {"domain": "mobile_messages_fixture"},
            "source": {
                "kind": "local_mobile_messages_json",
                "source_id": "source_profile_mobile_messages_v1",
                "content_hash": "sha256:" + "3" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "4" * 64,
            },
        },
    }
    quality_report = {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_mobile_test",
        "counts": {"total": 4, "accepted": 4, "rejected": 0, "executable": 4},
        "rates": {"success_rate": 1.0, "executable_rate": 1.0},
        "rejection_causes": {},
        "slices": {},
    }
    manifest_path = tmp_path / "manifest.json"
    quality_report_path = tmp_path / "quality_report.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    quality_report_path.write_text(json.dumps(quality_report), encoding="utf-8")
    return manifest_path, quality_report_path


def _write_workspace_inputs(tmp_path: Path) -> tuple[Path, Path]:
    manifest = {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_workspace_test",
        "parent_dataset_version": None,
        "accepted_count": 4,
        "rejected_count": 0,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
        },
        "quality": {"success_rate": 1.0, "executable_rate": 1.0},
        "environment_versions": ["env_workspace_tasks_v1"],
        "tool_versions": [
            "tool_search_workspace_items_v1",
            "tool_create_workspace_task_v1",
            "tool_add_workspace_comment_v1",
        ],
        "verifier_versions": ["verifier_exact_answer_state_v2"],
        "generator_config_hashes": ["workspace-fixture-task-generation-v1"],
        "rejection_causes": {},
        "run_profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "workspace_tasks_fixture",
            "profile_purpose": "diagnostic_probe",
            "generation_mode": "workspace_fixture",
            "target_candidate_count": 4,
            "config_hash": "sha256:" + "5" * 64,
            "enabled_features": [],
            "seed": {"domain": "workspace_tasks_fixture"},
        },
    }
    quality_report = {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_workspace_test",
        "counts": {"total": 4, "accepted": 4, "rejected": 0, "executable": 4},
        "rates": {"success_rate": 1.0, "executable_rate": 1.0},
        "rejection_causes": {},
        "slices": {},
    }
    manifest_path = tmp_path / "manifest.json"
    quality_report_path = tmp_path / "quality_report.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    quality_report_path.write_text(json.dumps(quality_report), encoding="utf-8")
    return manifest_path, quality_report_path


def _parent_report_with_statuses(statuses: dict[str, str]) -> dict[str, object]:
    task_results = [
        {
            "task_id": task_id,
            "capability_tags": ["parent"],
            "status": status,
            "failure_cause": None if status == "passed" else "verification_failed",
        }
        for task_id, status in statuses.items()
    ]
    passed = sum(1 for status in statuses.values() if status == "passed")
    failed = len(statuses) - passed
    return {
        "schema_version": "evaluation_report_v1",
        "dataset_version": "dataset_parent",
        "suite": {
            "suite_id": "contacts_heldout_v1",
            "suite_version": "contacts_heldout_v1",
            "task_count": len(task_results),
        },
        "profile": None,
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "parent_evaluation_report_path": None,
        },
        "counts": {
            "total": len(task_results),
            "passed": passed,
            "failed": failed,
            "regressed": 0,
            "improved": 0,
            "unchanged": len(task_results),
        },
        "rates": {"pass_rate": passed / len(task_results)},
        "capability_slices": {
            "parent": {
                "total": len(task_results),
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / len(task_results),
            }
        },
        "task_results": task_results,
        "thresholds": {"mvp_min_heldout_pass_rate": 0.8, "max_regression_count": 0},
        "decision": {"status": "passed", "reasons": ["parent"], "triggered_by": []},
    }


if __name__ == "__main__":
    unittest.main()
