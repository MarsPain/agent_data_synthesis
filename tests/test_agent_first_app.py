from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from agent_synthesis.app import main


class AgentFirstAppTest(unittest.TestCase):
    def test_fixture_run_and_replay_use_the_public_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = root / "configuration.json"
            responses = root / "responses.jsonl"
            output = root / "run"
            configuration.write_text(json.dumps({
                "run_id": "app-smoke",
                "domain_id": "contacts",
                "model_id": "fixture-smoke",
                "slot_limit": 1,
                "accepted_target": 1,
                "generation_batch_size": 1,
                "max_concurrency": 1,
                "total_request_limit": 3,
                "generation_request_limit": 1,
                "agent_request_limit": 2,
                "transport_retry_limit": 0,
                "decision_repair_limit": 0,
            }), encoding="utf-8")
            responses.write_text("\n".join(json.dumps(response) for response in (
                {"proposals": [{
                    "slot_id": "contacts-lookup-direct-alice-zhang",
                    "content": '{"action":"lookup_email","contact":"Alice Zhang","route":"direct"}',
                }]},
                {"type": "tool_call", "tool_name": "lookup_contact", "arguments": {"name": "Alice Zhang"}},
                {"type": "final_response", "content": "Alice Zhang's email address is alice.zhang@example.test."},
            )) + "\n", encoding="utf-8")

            self.assertEqual(main([
                "run", "--configuration", str(configuration),
                "--output-directory", str(output),
                "--fixture-responses", str(responses),
            ]), 0)
            self.assertEqual(len((output / "demonstrations.jsonl").read_text().splitlines()), 1)
            self.assertTrue((output / "manifest.json").is_file())
            self.assertEqual(main(["replay", "--output-directory", str(output)]), 0)
            self.assertEqual(main([
                "create-review-queue", "--output-directory", str(output),
                "--cohort-id", "app-smoke-review", "--purpose", "held-out-evaluation",
            ]), 0)
            queue = json.loads((output / "blind_review_queue.jsonl").read_text().splitlines()[0])
            label_path = root / "synthetic-test-labels.jsonl"
            label_path.write_text(json.dumps({
                "schema_version": "agent_human_review_label_v1",
                "episode_id": queue["episode_id"],
                "cohort_id": queue["cohort_id"],
                "purpose": queue["purpose"],
                "dimensions": [{
                    "dimension": dimension,
                    "verdict": "pass",
                    "reason_codes": [],
                    "event_references": [{"event_index": 0}],
                } for dimension in (
                    "instruction_fidelity", "action_efficiency", "observation_grounding",
                    "final_response_quality", "safety",
                )],
                "reviewer_provenance": {
                    "reviewer_id": "synthetic-test-reviewer",
                    "review_method": "human_direct_review",
                    "human_review_attestation": (
                        "I directly reviewed this Episode and did not use generated or "
                        "judge-produced labels as human ground truth."
                    ),
                },
            }) + "\n", encoding="utf-8")
            self.assertEqual(main([
                "import-review-labels", "--output-directory", str(output),
                "--labels", str(label_path),
            ]), 0)

    def test_live_path_requires_separate_authorization_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = root / "configuration.json"
            configuration.write_text(json.dumps({
                "run_id": "app-live-preflight",
                "domain_id": "contacts",
                "model_id": "remote-model",
                "slot_limit": 1,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "authorization ID"):
                main([
                    "run", "--configuration", str(configuration),
                    "--output-directory", str(root / "run"),
                    "--authorize-live-provider",
                ])
            self.assertFalse((root / "run").exists())


if __name__ == "__main__":
    unittest.main()
