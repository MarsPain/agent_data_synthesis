from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthesis.tasks import CandidateTask


class QualityReportingTest(unittest.TestCase):
    def test_builds_dataset_report_with_counts_rates_slices_and_rejection_causes(self) -> None:
        from synthesis.quality import build_quality_report

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[_sample()],
            rejections=[_rejection()],
        )

        self.assertEqual(report["schema_version"], "quality_report_v1")
        self.assertEqual(report["counts"]["total"], 2)
        self.assertEqual(report["counts"]["accepted"], 1)
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertEqual(report["counts"]["executable"], 2)
        self.assertEqual(report["rates"]["success_rate"], 0.5)
        self.assertEqual(report["rates"]["executable_rate"], 1.0)
        self.assertEqual(report["rejection_causes"], {"verification_failed": 1})
        self.assertIn("dataset_test", report["slices"]["dataset_version"])
        self.assertIn("easy", report["slices"]["difficulty_level"])
        self.assertIn("lookup_contact_email", report["slices"]["tool_combination"])
        self.assertIn("task_generation", report["slices"]["generator_role"])
        self.assertIn("exact_answer_verifier", report["slices"]["verifier_type"])
        self.assertIn("verification_failed", report["slices"]["rejection_cause"])

    def test_duplicate_signature_uses_normalized_instruction_and_ordered_actions(self) -> None:
        from synthesis.quality import duplicate_signature

        sample = _sample()
        sample["task"]["instruction"] = "  Find Alice Zhang's   email address. "

        self.assertEqual(
            duplicate_signature(sample),
            ("find alice zhang's email address.", ("lookup_contact_email",)),
        )

    def test_parent_comparison_reports_count_rate_slice_and_cause_deltas(self) -> None:
        from synthesis.quality import build_parent_comparison

        parent = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_parent",
            "counts": {"accepted": 1, "rejected": 2},
            "rates": {"success_rate": 0.25, "executable_rate": 0.75},
            "slices": {"difficulty_level": {"easy": {}, "medium": {}}},
            "rejection_causes": {"verification_failed": 2},
        }
        current = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_current",
            "counts": {"accepted": 3, "rejected": 1},
            "rates": {"success_rate": 0.75, "executable_rate": 1.0},
            "slices": {"difficulty_level": {"easy": {}, "hard": {}}},
            "rejection_causes": {"quality_duplicate": 1},
        }

        comparison = build_parent_comparison(current=current, parent=parent)

        self.assertEqual(comparison["accepted_count_delta"], 2)
        self.assertEqual(comparison["rejected_count_delta"], -1)
        self.assertEqual(comparison["success_rate_delta"], 0.5)
        self.assertEqual(comparison["executable_rate_delta"], 0.25)
        self.assertEqual(comparison["new_slice_keys"], {"difficulty_level": ["hard"]})
        self.assertEqual(comparison["removed_slice_keys"], {"difficulty_level": ["medium"]})
        self.assertEqual(
            comparison["rejection_cause_deltas"],
            {"quality_duplicate": 1, "verification_failed": -2},
        )

    def test_review_record_has_stable_shape(self) -> None:
        from synthesis.quality import build_review_record

        record = build_review_record(
            candidate_id="candidate_duplicate",
            cause="quality_duplicate",
            task={"instruction": "Find Alice Zhang's email address."},
            uncertainty_reason="Exact duplicate requires human policy review.",
            source_artifact="rejections.jsonl",
        )

        self.assertEqual(record["schema_version"], "human_review_record_v1")
        self.assertEqual(record["candidate_id"], "candidate_duplicate")
        self.assertEqual(record["cause"], "quality_duplicate")
        self.assertEqual(record["source_artifact"], "rejections.jsonl")
        self.assertEqual(record["created_at"], "1970-01-01T00:00:00Z")

    def test_curriculum_order_sorts_fixture_candidates_by_difficulty(self) -> None:
        from synthesis.tasks import CandidateTask, order_candidates_by_curriculum

        hard = CandidateTask(
            candidate_id="candidate_hard",
            instruction="Hard task.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={**_difficulty(), "level": "hard", "tool_count": 2},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )
        easy = CandidateTask(
            candidate_id="candidate_easy",
            instruction="Easy task.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=_difficulty(),
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )

        ordered = order_candidates_by_curriculum([hard, easy])

        self.assertEqual([candidate.candidate_id for candidate in ordered], ["candidate_easy", "candidate_hard"])


class QualityPipelineTest(unittest.TestCase):
    def test_writes_quality_report_and_manifest_reference(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_test")

            self.assertTrue(result.quality_report_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["quality_report"], "quality_report.json")

            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["accepted"], 2)
            self.assertEqual(report["counts"]["rejected"], 1)

    def test_rejects_later_duplicate_accepted_candidate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def duplicate_generator(seed) -> list[CandidateTask]:
            task = CandidateTask(
                candidate_id="candidate_contacts_alice",
                instruction="Find Alice Zhang's email address using the contact database.",
                constraints={"must_use_tool": "lookup_contact_email"},
                difficulty=_difficulty(),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=(seed.seed_id,),
            )
            return [
                task,
                CandidateTask(
                    candidate_id="candidate_contacts_alice_duplicate",
                    instruction="  find alice zhang's email address using the contact database. ",
                    constraints=task.constraints,
                    difficulty=task.difficulty,
                    tool_name=task.tool_name,
                    arguments=task.arguments,
                    expected_answer=task.expected_answer,
                    seed_ids=task.seed_ids,
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_duplicate_test",
                candidate_generator=duplicate_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "quality_duplicate")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rejection_causes"], {"quality_duplicate": 1})

    def test_rejects_final_answer_not_supported_by_observation(self) -> None:
        from synthesis.execution import ExecutionResult
        from synthesis.pipeline import run_foundation_pipeline

        def generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_unsupported_answer",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty=_difficulty(),
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        unsupported_execution = ExecutionResult(
            trajectory=[
                {"type": "action", "tool": "lookup_contact_email", "arguments": {"name": "Alice Zhang"}},
                {
                    "type": "observation",
                    "tool": "lookup_contact_email",
                    "observation": {"name": "Alice Zhang", "email": "wrong@example.test"},
                },
                {
                    "type": "final_response",
                    "content": "Alice Zhang's email is alice.zhang@example.test.",
                },
            ],
            final_response="Alice Zhang's email is alice.zhang@example.test.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("synthesis.pipeline.execute_candidate", return_value=unsupported_execution):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_logic_test",
                    candidate_generator=generator,
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "solution_logic_error")

    def test_writes_parent_comparison_when_parent_artifact_is_provided(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            parent_path = tmp_path / "parent_quality_report.json"
            parent_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality_report_v1",
                        "dataset_version": "dataset_parent",
                        "counts": {"accepted": 0, "rejected": 1},
                        "rates": {"success_rate": 0.0, "executable_rate": 1.0},
                        "slices": {"rejection_cause": {"verification_failed": {}}},
                        "rejection_causes": {"verification_failed": 1},
                    }
                ),
                encoding="utf-8",
            )

            result = run_foundation_pipeline(
                tmp_path / "current",
                dataset_version="dataset_current",
                parent_artifact_path=parent_path,
            )

            self.assertIsNotNone(result.parent_comparison_path)
            comparison = json.loads(result.parent_comparison_path.read_text(encoding="utf-8"))
            self.assertEqual(comparison["parent_dataset_version"], "dataset_parent")
            self.assertEqual(comparison["current_dataset_version"], "dataset_current")

    def test_review_queue_is_disabled_by_default_and_enabled_by_policy(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def duplicates(seed) -> list[CandidateTask]:
            base = CandidateTask(
                candidate_id="candidate_a",
                instruction="Find Alice Zhang's email address.",
                constraints={"must_use_tool": "lookup_contact_email"},
                difficulty=_difficulty(),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=(seed.seed_id,),
            )
            return [
                base,
                CandidateTask(
                    candidate_id="candidate_b",
                    instruction=base.instruction,
                    constraints=base.constraints,
                    difficulty=base.difficulty,
                    tool_name=base.tool_name,
                    arguments=base.arguments,
                    expected_answer=base.expected_answer,
                    seed_ids=base.seed_ids,
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            disabled = run_foundation_pipeline(
                Path(tmpdir) / "disabled",
                dataset_version="dataset_review_disabled",
                candidate_generator=duplicates,
            )
            enabled = run_foundation_pipeline(
                Path(tmpdir) / "enabled",
                dataset_version="dataset_review_enabled",
                candidate_generator=duplicates,
                route_reviewable_failures=True,
            )

            self.assertIsNone(disabled.review_queue_path)
            self.assertIsNotNone(enabled.review_queue_path)
            record = json.loads(enabled.review_queue_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["cause"], "quality_duplicate")


def _difficulty() -> dict[str, object]:
    return {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }


def _sample() -> dict[str, object]:
    return {
        "sample_id": "sample_candidate_contacts_alice",
        "dataset_version": "dataset_test",
        "environment": {"id": "contacts_fixture", "version": "env_contacts_v1"},
        "tools": [{"name": "lookup_contact_email", "version": "tool_lookup_contact_email_v1"}],
        "task": {
            "instruction": "Find Alice Zhang's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": _difficulty(),
        },
        "trajectory": [
            {"type": "action", "tool": "lookup_contact_email", "arguments": {"name": "Alice Zhang"}},
            {
                "type": "observation",
                "tool": "lookup_contact_email",
                "observation": {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
            },
            {"type": "final_response", "content": "Alice Zhang's email is alice.zhang@example.test."},
        ],
        "final_response": "Alice Zhang's email is alice.zhang@example.test.",
        "verifier": {"id": "exact_answer_verifier", "version": "verifier_exact_answer_v1"},
        "verification": {
            "passed": True,
            "checks": [
                {
                    "name": "final_response_contains_expected_answer",
                    "passed": True,
                    "expected": "alice.zhang@example.test",
                    "actual": "Alice Zhang's email is alice.zhang@example.test.",
                }
            ],
        },
        "quality": {"scores": {"executable": 1.0}, "tags": ["foundation"]},
        "lineage": {"generator": {"role": "task_generation"}, "verifier": {"id": "exact_answer_verifier"}},
    }


def _rejection() -> dict[str, object]:
    return {
        "candidate_id": "candidate_contacts_ben_bad_expectation",
        "cause": "verification_failed",
        "task": {
            "candidate_id": "candidate_contacts_ben_bad_expectation",
            "instruction": "Find Ben Carter's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": _difficulty(),
        },
        "details": {"check": "final_response_contains_expected_answer"},
    }


if __name__ == "__main__":
    unittest.main()
