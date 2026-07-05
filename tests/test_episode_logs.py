from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.domain_pipeline import build_domain_pipeline_bundle
from synthesis.execution import execute_candidate
from synthesis.mobile_tasks import generate_mobile_fixture_candidates
from synthesis.seeds import DomainSeed, foundation_seed
from synthesis.tasks import generate_foundation_candidates


def mobile_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_mobile_messages_v1",
        domain="mobile_messages_fixture",
        description="Synthetic phone messages, reminders, and draft replies.",
        task_taxonomy=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
    )


class EpisodeLogTest(unittest.TestCase):
    def test_builds_valid_episode_log_from_contacts_trajectory(self) -> None:
        from awm_runtime import build_episode_log, summarize_episode_for_quality
        from synthesis.contracts import validate_episode_log_record

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            task = generate_foundation_candidates(foundation_seed())[0]
            policy = bundle.policy_generator(task)
            execution = execute_candidate(task, bundle.registry, policy=policy)
            episode = build_episode_log(
                candidate_id=task.candidate_id,
                runtime_metadata=bundle.environment.runtime_metadata(),
                policy=policy,
                verifier=bundle.verifier,
                trajectory=execution.trajectory,
                outcome_status="accepted",
            ).export()

        validate_episode_log_record(episode)
        self.assertEqual(episode["schema_version"], "episode_log_v1")
        self.assertEqual(episode["candidate_id"], "candidate_contacts_alice")
        self.assertEqual(episode["runtime"]["runtime_id"], "contacts_fixture")
        self.assertEqual(episode["policy"]["policy_id"], "policy_candidate_contacts_alice")
        self.assertEqual(episode["outcome"], {"status": "accepted", "failure_cause": None})
        self.assertEqual(
            [transition["event_type"] for transition in episode["transitions"]],
            ["action", "observation", "final_response"],
        )
        action = episode["transitions"][0]
        self.assertEqual(action["tool_name"], "lookup_contact_email")
        self.assertEqual(action["arguments"], {"name": "Alice Zhang"})
        self.assertTrue(str(action["arguments_hash"]).startswith("sha256:"))

        summary = summarize_episode_for_quality(episode)
        self.assertEqual(summary["runtime_id"], "contacts_fixture")
        self.assertEqual(summary["outcome_status"], "accepted")
        self.assertEqual(summary["action_count"], 1)
        self.assertEqual(summary["observation_count"], 1)
        self.assertEqual(summary["final_response_count"], 1)
        self.assertEqual(summary["tool_names"], ["lookup_contact_email"])

    def test_builds_mobile_state_change_episode_log(self) -> None:
        from awm_runtime import build_episode_log, summarize_episode_for_quality
        from synthesis.contracts import validate_episode_log_record

        with tempfile.TemporaryDirectory() as tmpdir:
            seed = mobile_seed()
            bundle = build_domain_pipeline_bundle(seed, Path(tmpdir))
            task = next(
                candidate
                for candidate in generate_mobile_fixture_candidates(seed)
                if candidate.candidate_id == "candidate_mobile_maya_reminder"
            )
            policy = bundle.policy_generator(task)
            execution = execute_candidate(task, bundle.registry, policy=policy)
            episode = build_episode_log(
                candidate_id=task.candidate_id,
                runtime_metadata=bundle.environment.runtime_metadata(),
                policy=policy,
                verifier=bundle.verifier,
                trajectory=execution.trajectory,
                outcome_status="accepted",
            ).export()

        validate_episode_log_record(episode)
        self.assertEqual(episode["runtime"]["runtime_id"], "mobile_messages_fixture")
        self.assertIn(
            "state_change",
            [transition["event_type"] for transition in episode["transitions"]],
        )
        summary = summarize_episode_for_quality(episode)
        self.assertEqual(summary["state_change_count"], 1)
        self.assertEqual(
            summary["tool_names"],
            ["search_phone_messages", "create_phone_reminder"],
        )

    def test_episode_hashes_are_deterministic_over_sorted_sanitized_json(self) -> None:
        from awm_runtime import deterministic_content_hash

        left = {"b": 2, "a": {"nested": True}}
        right = {"a": {"nested": True}, "b": 2}

        self.assertEqual(
            deterministic_content_hash(left),
            deterministic_content_hash(right),
        )
        self.assertTrue(deterministic_content_hash(left).startswith("sha256:"))

    def test_episode_contract_rejects_unsupported_status_event_and_bad_hash(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_episode_log_record

        valid = _valid_episode_log()
        invalid_records = (
            {**valid, "outcome": {"status": "deferred", "failure_cause": None}},
            {
                **valid,
                "transitions": [
                    {**valid["transitions"][0], "event_type": "tool_call"},
                ],
            },
            {
                **valid,
                "transitions": [
                    {**valid["transitions"][0], "arguments_hash": "not-a-hash"},
                ],
            },
        )
        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(ContractValidationError):
                    validate_episode_log_record(record)

    def test_episode_contract_accepts_toolless_error_and_redacted_final_response(self) -> None:
        from awm_runtime import RuntimeMetadata, build_episode_log
        from synthesis.contracts import validate_episode_log_record
        from synthesis.execution import SolutionPolicy, ToolStep
        from synthesis.verification import ExactAnswerVerifier

        runtime = RuntimeMetadata(
            runtime_id="contacts_fixture",
            runtime_version="env_contacts_v2",
            environment_id="contacts_fixture",
            environment_version="env_contacts_v2",
            reset_recipe="sqlite_fixture:contacts",
            state_backend="sqlite",
            checkpoint_strategy="sqlite_backup",
        )
        policy = SolutionPolicy(
            policy_id="policy_candidate_error",
            role="scripted_solution_policy",
            steps=(ToolStep(tool_name="lookup_contact_email", arguments={}),),
            final_response_template="ok",
        )
        episode = build_episode_log(
            candidate_id="candidate_error",
            runtime_metadata=runtime,
            policy=policy,
            verifier=ExactAnswerVerifier(),
            trajectory=[
                {"type": "unknown", "message": "adapter failed"},
                {"type": "final_response", "content": "secret-test-key"},
            ],
            outcome_status="failed",
            failure_cause="infrastructure_error",
        ).export()

        validate_episode_log_record(episode)
        self.assertEqual(episode["transitions"][0]["event_type"], "error")
        self.assertNotIn("tool_name", episode["transitions"][0])
        self.assertEqual(episode["transitions"][1]["content"], "[redacted]")

    def test_episode_redaction_excludes_paths_prompts_headers_keys_payloads_and_env(self) -> None:
        from awm_runtime import RuntimeMetadata, build_episode_log
        from synthesis.execution import SolutionPolicy, ToolStep
        from synthesis.verification import ExactAnswerVerifier

        runtime = RuntimeMetadata(
            runtime_id="contacts_fixture",
            runtime_version="env_contacts_v2",
            environment_id="contacts_fixture",
            environment_version="env_contacts_v2",
            reset_recipe="sqlite_fixture:contacts",
            state_backend="sqlite",
            checkpoint_strategy="sqlite_backup",
        )
        policy = SolutionPolicy(
            policy_id="policy_candidate_redaction",
            role="scripted_solution_policy",
            steps=(ToolStep(tool_name="lookup_contact_email", arguments={}),),
            final_response_template="ok",
        )
        trajectory = [
            {
                "type": "action",
                "tool": "lookup_contact_email",
                "arguments": {
                    "name": "Alice Zhang",
                    "profile_path": "/Users/H/profile.json",
                    "headers": {"authorization": "Bearer secret-test-key"},
                    "provider_prompt": "Generate private data",
                },
            },
            {
                "type": "observation",
                "tool": "lookup_contact_email",
                "observation": {
                    "email": "alice.zhang@example.test",
                    "provider_payload": {"raw": True},
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "source_path": "/tmp/source.json",
                },
            },
            {"type": "final_response", "content": "ok"},
        ]

        episode = build_episode_log(
            candidate_id="candidate_redaction",
            runtime_metadata=runtime,
            policy=policy,
            verifier=ExactAnswerVerifier(),
            trajectory=trajectory,
            outcome_status="accepted",
        ).export()

        serialized = json.dumps(episode, sort_keys=True)
        self.assertIn("Alice Zhang", serialized)
        self.assertIn("alice.zhang@example.test", serialized)
        self.assertNotIn("/Users/H", serialized)
        self.assertNotIn("/tmp/source.json", serialized)
        self.assertNotIn("provider_prompt", serialized)
        self.assertNotIn("provider_payload", serialized)
        self.assertNotIn("authorization", serialized.lower())
        self.assertNotIn("secret-test-key", serialized)
        self.assertNotIn("AGENT_DATA_API_KEY", serialized)


def _valid_episode_log() -> dict[str, object]:
    return {
        "schema_version": "episode_log_v1",
        "episode_id": "episode_sample_candidate_contacts_alice",
        "candidate_id": "candidate_contacts_alice",
        "runtime": {
            "schema_version": "runtime_metadata_v1",
            "runtime_id": "contacts_fixture",
            "runtime_version": "env_contacts_v2",
        },
        "policy": {
            "policy_id": "policy_candidate_contacts_alice",
            "role": "scripted_solution_policy",
        },
        "verifier": {
            "id": "exact_answer_verifier",
            "version": "verifier_exact_answer_state_v2",
        },
        "transitions": [
            {
                "transition_index": 1,
                "event_type": "action",
                "tool_name": "lookup_contact_email",
                "arguments_hash": "sha256:" + "1" * 64,
                "arguments": {"name": "Alice Zhang"},
            }
        ],
        "outcome": {"status": "accepted", "failure_cause": None},
    }


if __name__ == "__main__":
    unittest.main()
