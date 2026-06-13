from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthesis.domain_pipeline import build_domain_pipeline_bundle
from synthesis.episodes import build_episode_log
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


class EpisodeReplayTest(unittest.TestCase):
    def test_builds_passed_replay_report_for_contacts_lookup(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_contacts_replay_test",
            episodes=(_episode("candidate_contacts_alice"),),
        )

        self.assertEqual(report["schema_version"], "episode_replay_report_v1")
        self.assertEqual(report["observed"]["episode_count"], 1)
        self.assertEqual(report["observed"]["replayed"], 1)
        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "contacts_fixture")
        self.assertEqual(summary["replayed_action_count"], 1)
        self.assertEqual(summary["observation_mismatch_count"], 0)
        self.assertEqual(report["decision"]["status"], "passed")

    def test_mobile_state_change_replay_matches_state_change_evidence(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_mobile_replay_test",
            episodes=(_episode("candidate_mobile_maya_reminder"),),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "mobile_messages_fixture")
        self.assertEqual(summary["state_change_match_count"], 1)
        self.assertEqual(summary["state_change_mismatch_count"], 0)
        self.assertEqual(report["decision"]["status"], "passed")

    def test_missing_episodes_returns_insufficient_evidence(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_empty",
            episodes=(),
        )

        self.assertEqual(report["decision"]["status"], "insufficient_evidence")

    def test_replay_report_contract_rejects_raw_content_and_absolute_paths(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_episode_replay_report_record,
        )
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_contacts_replay_test",
            episodes=(_episode("candidate_contacts_alice"),),
        )
        validate_episode_replay_report_record(report)

        with_absolute_path = {
            **report,
            "inputs": {
                **report["inputs"],
                "episodes_path": "/tmp/episodes.jsonl",
            },
        }
        with self.assertRaises(ContractValidationError):
            validate_episode_replay_report_record(with_absolute_path)

        with_raw_arguments = {
            **report,
            "episode_summaries": [
                {
                    **report["episode_summaries"][0],
                    "arguments": {"name": "Alice Zhang"},
                }
            ],
        }
        with self.assertRaises(ContractValidationError):
            validate_episode_replay_report_record(with_raw_arguments)


def _episode(candidate_id: str) -> dict[str, object]:
    if candidate_id.startswith("candidate_mobile_"):
        seed = mobile_seed()
        candidates = generate_mobile_fixture_candidates(seed)
    else:
        seed = foundation_seed()
        candidates = generate_foundation_candidates(seed)
    task = next(candidate for candidate in candidates if candidate.candidate_id == candidate_id)
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle = build_domain_pipeline_bundle(seed, Path(tmpdir))
        policy = bundle.policy_generator(task)
        execution = execute_candidate(task, bundle.registry, policy=policy)
        return build_episode_log(
            candidate_id=task.candidate_id,
            runtime_metadata=bundle.environment.runtime_metadata(),
            policy=policy,
            verifier=bundle.verifier,
            trajectory=execution.trajectory,
            outcome_status="accepted",
        ).export()


if __name__ == "__main__":
    unittest.main()
