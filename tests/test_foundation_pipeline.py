from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.samples_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.rejections_path.exists())

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
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
            self.assertNotIn("secret-test-key", json.dumps(sample))

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_test")
            self.assertEqual(manifest["accepted_count"], 1)
            self.assertEqual(manifest["rejected_count"], 1)
            self.assertEqual(manifest["quality"]["success_rate"], 0.5)

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertIn("expected", rejection["details"])

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


if __name__ == "__main__":
    unittest.main()
