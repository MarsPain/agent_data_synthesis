from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.tasks import CandidateTask


class RefinementContractTest(unittest.TestCase):
    def test_refinement_attempt_rejects_invalid_attempt_number(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_refinement_attempt

        attempt = _valid_candidate_refinement_attempt()
        attempt["attempt_number"] = 0

        with self.assertRaisesRegex(ContractValidationError, "attempt_number"):
            validate_refinement_attempt(attempt)

    def test_refinement_attempt_rejects_empty_diagnosis(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_refinement_attempt

        attempt = _valid_candidate_refinement_attempt()
        attempt["critic_diagnosis"] = " "

        with self.assertRaisesRegex(ContractValidationError, "critic_diagnosis"):
            validate_refinement_attempt(attempt)

    def test_refinement_attempt_rejects_missing_revised_payload(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_refinement_attempt

        attempt = _valid_candidate_refinement_attempt()
        attempt.pop("revised_candidate")

        with self.assertRaisesRegex(ContractValidationError, "revised_candidate"):
            validate_refinement_attempt(attempt)

    def test_refinement_attempt_rejects_unsupported_decision(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_refinement_attempt

        attempt = _valid_candidate_refinement_attempt()
        attempt["repair_decision"] = "rewrite_everything"

        with self.assertRaisesRegex(ContractValidationError, "repair_decision"):
            validate_refinement_attempt(attempt)


class DeterministicRefinementPipelineTest(unittest.TestCase):
    def test_default_pipeline_keeps_refinement_disabled_counts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_no_refine")

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["refined_attempted"], 0)
            self.assertEqual(report["counts"]["refined_accepted"], 0)
            self.assertEqual(report["counts"]["refined_rejected"], 0)

    def test_deterministic_refinement_repairs_ben_carter_expectation(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.refinement import deterministic_fixture_refiner

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_refine_ben",
                refiner=deterministic_fixture_refiner,
            )

            self.assertEqual(result.accepted_count, 3)
            self.assertEqual(result.rejected_count, 0)
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            ben_sample = next(
                sample for sample in samples if "Ben Carter" in sample["task"]["instruction"]
            )
            self.assertEqual(ben_sample["verification"]["checks"][0]["expected"], "ben.carter@example.test")
            self.assertEqual(
                ben_sample["lineage"]["refinement"]["source_failure_cause"],
                "verification_failed",
            )
            self.assertEqual(ben_sample["lineage"]["refinement"]["attempt_number"], 1)

            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["refined_attempted"], 1)
            self.assertEqual(report["counts"]["refined_accepted"], 1)
            self.assertEqual(report["counts"]["refined_rejected"], 0)
            self.assertIn("refined_accepted", report["slices"]["refinement_status"])

    def test_deterministic_refinement_repairs_missing_state_mutation_policy(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.refinement import deterministic_fixture_refiner

        def stateful_candidate_generator(seed) -> list[CandidateTask]:
            return [_stateful_followup_task(seed.seed_id)]

        def skipping_policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_skip_mutation",
                role="scripted_solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": "Alice Zhang"},
                    ),
                ),
                final_response_template="{name}'s email is {email}. Follow-up recorded.",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_refine_stateful",
                candidate_generator=stateful_candidate_generator,
                policy_generator=skipping_policy_generator,
                refiner=deterministic_fixture_refiner,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                [event["tool"] for event in sample["trajectory"] if event["type"] == "action"],
                ["lookup_contact_email", "record_contact_followup"],
            )
            self.assertEqual(sample["lineage"]["refinement"]["repair_decision"], "repair_policy")

    def test_refined_attempt_duplicate_is_rejected_with_original_failure_visible(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.refinement import deterministic_fixture_refiner

        def duplicate_after_refinement(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_ben_good",
                    instruction="Find Ben Carter's email address using the contact database.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty=_difficulty(),
                    tool_name="lookup_contact_email",
                    arguments={"name": "Ben Carter"},
                    expected_answer="ben.carter@example.test",
                    seed_ids=(seed.seed_id,),
                ),
                CandidateTask(
                    candidate_id="candidate_contacts_ben_bad_expectation",
                    instruction="Find Ben Carter's email address using the contact database.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty=_difficulty(),
                    tool_name="lookup_contact_email",
                    arguments={"name": "Ben Carter"},
                    expected_answer="ben@example.test",
                    seed_ids=(seed.seed_id,),
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_refine_duplicate",
                candidate_generator=duplicate_after_refinement,
                refiner=deterministic_fixture_refiner,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "quality_duplicate")
            self.assertEqual(
                rejection["details"]["refinement"]["source_failure_cause"],
                "verification_failed",
            )
            self.assertEqual(rejection["details"]["refinement"]["outcome"], "rejected")

    def test_refiner_provider_error_becomes_inspectable_candidate_rejection(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def failing_refiner(context):
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="TypeError",
                retryable=False,
                retry_count=0,
            )

        def repairable_candidate(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_contacts_ben_bad_expectation",
                    instruction="Find Ben Carter's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty=_difficulty(),
                    tool_name="lookup_contact_email",
                    arguments={"name": "Ben Carter"},
                    expected_answer="ben@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_refiner_error",
                candidate_generator=repairable_candidate,
                refiner=failing_refiner,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "llm_response_schema_error")
            self.assertEqual(
                rejection["details"]["source_failure"]["cause"],
                "verification_failed",
            )
            self.assertEqual(rejection["details"]["retry_count"], 0)


class RemoteRefinementTest(unittest.TestCase):
    def test_remote_refinement_parses_candidate_and_records_sanitized_lineage(self) -> None:
        from synthesis.refinement import generate_llm_backed_refinement

        task = CandidateTask(
            candidate_id="candidate_contacts_ben_bad_expectation",
            instruction="Find Ben Carter's email address.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=_difficulty(),
            tool_name="lookup_contact_email",
            arguments={"name": "Ben Carter"},
            expected_answer="ben@example.test",
            seed_ids=("seed_contacts_v1",),
        )

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                self.prompt = prompt
                self.role = role
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "repair_decision": "repair_candidate",
                            "critic_diagnosis": "The expected answer used an outdated alias.",
                            "candidate": {
                                "candidate_id": "candidate_contacts_ben_bad_expectation_refined_1",
                                "instruction": "Find Ben Carter's email address.",
                                "constraints": {"must_use_tool": "lookup_contact_email"},
                                "difficulty": _difficulty(),
                                "tool_name": "lookup_contact_email",
                                "arguments": {"name": "Ben Carter"},
                                "expected_answer": "ben.carter@example.test",
                            },
                        },
                        "lineage": {
                            "role": "critic_refinement",
                            "provider_host": "llm.example.test",
                            "model": "test-generator",
                            "config_hash": "abc123",
                            "prompt_hash": "prompt123",
                            "retry_count": 1,
                            "tokens": {"total_tokens": 25},
                        },
                    },
                )()

        fake_client = FakeClient()
        attempt = generate_llm_backed_refinement(
            task=task,
            source_failure_cause="verification_failed",
            source_failure_details={"expected": "ben@example.test", "actual": "ben.carter@example.test"},
            attempt_number=1,
            client=fake_client,
        )

        self.assertEqual(fake_client.role, "critic_refinement")
        self.assertIn("candidate_contacts_ben_bad_expectation", fake_client.prompt)
        self.assertNotIn("secret-test-key", json.dumps(attempt.export()))
        self.assertEqual(attempt.revised_candidate.expected_answer, "ben.carter@example.test")
        self.assertEqual(attempt.lineage["provider_host"], "llm.example.test")
        self.assertEqual(attempt.lineage["retry_count"], 1)
        self.assertEqual(attempt.lineage["tokens"]["total_tokens"], 25)


def _valid_candidate_refinement_attempt() -> dict[str, object]:
    return {
        "original_candidate_id": "candidate_contacts_ben_bad_expectation",
        "attempt_number": 1,
        "source_failure_cause": "verification_failed",
        "source_failure_details": {"expected": "ben@example.test"},
        "critic_diagnosis": "Expected answer does not match fixture contact email.",
        "repair_decision": "repair_candidate",
        "lineage": {
            "role": "local_critic_refinement",
            "provider_host": "local",
            "model": "deterministic",
            "config_hash": "deterministic_refinement_v1",
            "configured": True,
        },
        "revised_candidate": {
            "candidate_id": "candidate_contacts_ben_bad_expectation_refined_1",
            "instruction": "Find Ben Carter's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": _difficulty(),
        },
    }


def _stateful_followup_task(seed_id: str) -> CandidateTask:
    return CandidateTask(
        candidate_id="candidate_contacts_alice_followup",
        instruction="Find Alice Zhang's email and record a follow-up note.",
        constraints={
            "task_type": "contact_followup",
            "required_tools": ["lookup_contact_email", "record_contact_followup"],
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
        arguments={"name": "Alice Zhang"},
        expected_answer="alice.zhang@example.test",
        seed_ids=(seed_id,),
        expected_state={
            "contact_followup": {
                "name": "Alice Zhang",
                "note": "Send follow-up email to alice.zhang@example.test.",
            }
        },
    )


def _difficulty() -> dict[str, object]:
    return {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }


if __name__ == "__main__":
    unittest.main()
