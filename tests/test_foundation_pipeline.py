from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.tasks import CandidateTask


class FoundationPipelineTest(unittest.TestCase):
    def test_generates_verified_sample_and_manifest(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_test")

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.samples_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.rejections_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            sample = samples[0]
            self.assertEqual(sample["dataset_version"], "dataset_test")
            self.assertEqual(sample["environment"]["id"], "contacts_fixture")
            self.assertEqual(sample["tools"][0]["name"], "lookup_contact_email")
            self.assertEqual(sample["task"]["difficulty"]["tool_count"], 1)
            self.assertEqual(sample["trajectory"][-1]["type"], "final_response")
            self.assertIn("verifier", sample)
            self.assertEqual(sample["verifier"]["id"], "exact_answer_verifier")
            self.assertTrue(sample["verification"]["passed"])
            self.assertIn("provider_host", sample["lineage"]["generator"])
            self.assertEqual(sample["lineage"]["generator"]["model"], "test-generator")
            self.assertEqual(sample["lineage"]["generator"]["role_version"], "role_task_generation_v1")
            self.assertEqual(sample["lineage"]["generator"]["output_type"], "candidate_tasks")
            self.assertNotIn("secret-test-key", json.dumps(sample))

            stateful_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("task_type") == "contact_followup"
            )
            action_tools = [
                event["tool"]
                for event in stateful_sample["trajectory"]
                if event["type"] == "action"
            ]
            self.assertEqual(
                action_tools,
                ["lookup_contact_email", "record_contact_followup"],
            )
            self.assertTrue(
                any(event["type"] == "state_change" for event in stateful_sample["trajectory"])
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role"],
                "scripted_solution_policy",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role_version"],
                "role_scripted_solution_policy_v1",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["output_type"],
                "solution_policy",
            )
            self.assertEqual(stateful_sample["quality"]["tags"], ["foundation", "sqlite_fixture", "multi_step", "stateful"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_test")
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["rejected_count"], 1)
            self.assertEqual(manifest["quality"]["success_rate"], 2 / 3)
            self.assertEqual(manifest["schema_version"], "dataset_manifest_v1")
            self.assertIsNone(manifest["parent_dataset_version"])
            self.assertEqual(manifest["artifacts"]["quality_report"], "quality_report.json")
            self.assertEqual(manifest["environment_versions"], ["env_contacts_v2"])
            self.assertEqual(
                manifest["tool_versions"],
                ["tool_lookup_contact_email_v1", "tool_record_contact_followup_v1"],
            )
            self.assertEqual(manifest["verifier_versions"], ["verifier_exact_answer_state_v2"])
            self.assertEqual(manifest["rejection_causes"], {"verification_failed": 1})

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertIn("expected", rejection["details"])

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["schema_version"], "quality_report_v1")
            self.assertEqual(quality_report["counts"]["accepted"], 2)
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertIn("difficulty_level", quality_report["slices"])
            self.assertIn(
                "lookup_contact_email > record_contact_followup",
                quality_report["slices"]["tool_combination"],
            )

    def test_execution_rejects_malformed_solution_policy_before_tool_call(self) -> None:
        from synthesis.execution import PolicyValidationError, execute_candidate
        from synthesis.environments import ContactEnvironment
        from synthesis.tools import build_contact_tool_registry

        task = CandidateTask(
            candidate_id="candidate_bad_policy",
            instruction="Find Alice Zhang's email address.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={"level": "easy", "tool_count": 1},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )
        policy = SolutionPolicy(
            policy_id="policy_bad",
            role="scripted_solution_policy",
            steps=(ToolStep(tool_name="", arguments={"name": "Alice Zhang"}),),
            final_response_template="{email}",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)

            with self.assertRaisesRegex(PolicyValidationError, "steps.0.tool_name"):
                execute_candidate(task, registry, policy=policy)

    def test_stateful_task_rejects_policy_that_skips_required_mutation(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def stateful_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
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
                    seed_ids=(seed.seed_id,),
                    expected_state={
                        "contact_followup": {
                            "name": "Alice Zhang",
                            "note": "Send follow-up email to alice.zhang@example.test.",
                        }
                    },
                )
            ]

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
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
                dataset_version="dataset_state_verifier_test",
                candidate_generator=stateful_candidate_generator,
                policy_generator=policy_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "solution_logic_error")
            self.assertEqual(rejection["details"]["check"], "contact_followup_state_matches_expected")

    def test_rejects_candidate_when_tool_execution_fails(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_contact_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_unknown_contact",
                    instruction="Find John Doe's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "John Doe"},
                    expected_answer="john.doe@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_tool_error_test",
                    candidate_generator=invalid_contact_generator,
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_runtime_error")
            self.assertEqual(rejection["details"]["error_class"], "KeyError")
            self.assertIn("John Doe", rejection["details"]["message"])

    def test_rejects_candidate_when_tool_arguments_violate_schema(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_arguments_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool_argument",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_schema_error_test",
                candidate_generator=invalid_arguments_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ToolSchemaError")
            self.assertIn("name", rejection["details"]["message"])

    def test_rejects_candidate_when_required_tool_is_missing(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def missing_tool_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="missing_tool",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_missing_test",
                candidate_generator=missing_tool_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_missing")
            self.assertEqual(rejection["details"]["error_class"], "ToolMissingError")

    def test_rejects_candidate_when_candidate_shape_is_invalid(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_candidate_schema_error_test",
                candidate_generator=invalid_candidate_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "unknown_candidate")
            self.assertEqual(rejection["cause"], "candidate_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ContractValidationError")

    def test_registered_tool_smoke_gate_classifies_empty_registry(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("synthesis.pipeline.build_contact_tool_registry", return_value=ToolRegistry()):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_smoke_gate_test",
                    candidate_generator=lambda seed: [],
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "foundation_gate")
            self.assertEqual(rejection["cause"], "infrastructure_error")
            self.assertEqual(rejection["details"]["error_class"], "FoundationGateError")

    def test_generation_stage_provider_failure_writes_inspectable_artifacts(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def failing_generator(seed) -> list[CandidateTask]:
            raise LLMProviderError(
                cause="llm_provider_error",
                error_class="HTTPStatusError",
                retryable=True,
                retry_count=2,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_generation_failure_test",
                candidate_generator=failing_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "generation_stage")
            self.assertEqual(rejection["cause"], "llm_provider_error")
            self.assertEqual(rejection["details"]["error_class"], "HTTPStatusError")
            self.assertEqual(rejection["details"]["retry_count"], 2)
            self.assertTrue(rejection["details"]["retry_eligible"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rejection_causes"], {"llm_provider_error": 1})

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertEqual(quality_report["rejection_causes"], {"llm_provider_error": 1})


if __name__ == "__main__":
    unittest.main()
