from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthesis.domain_pipeline import build_domain_pipeline_bundle
from synthesis.mobile_tasks import generate_mobile_fixture_candidates
from synthesis.seeds import DomainSeed, foundation_seed
from synthesis.tasks import generate_foundation_candidates
from synthesis.workspace_tasks import generate_workspace_fixture_candidates


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


def workspace_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_workspace_tasks_v1",
        domain="workspace_tasks_fixture",
        description="Synthetic workspace projects, tasks, documents, and comments.",
        task_taxonomy=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
    )


class RuntimeRolloutTest(unittest.TestCase):
    def test_contacts_rollout_exports_replayable_reward_compatible_episode(self) -> None:
        from synthesis.contracts import validate_episode_log_record
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels
        from synthesis.rollouts import collect_diagnostic_rollout_episodes

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            task = generate_foundation_candidates(foundation_seed())[0]

            episodes = collect_diagnostic_rollout_episodes(
                bundle=bundle,
                tasks=(task,),
                max_steps=3,
            )

        self.assertEqual(len(episodes), 1)
        episode = episodes[0]
        validate_episode_log_record(episode)
        self.assertEqual(episode["runtime"]["runtime_id"], "contacts_fixture")
        self.assertEqual(episode["outcome"], {"status": "accepted", "failure_cause": None})
        self.assertEqual(
            [transition["event_type"] for transition in episode["transitions"]],
            ["action", "observation", "final_response"],
        )

        quality_report = build_episode_quality_report(
            dataset_version="dataset_rollout_contacts",
            episodes=episodes,
        )
        replay_report = build_episode_replay_report(
            dataset_version="dataset_rollout_contacts",
            episodes=episodes,
        )
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=quality_report,
            episode_replay_report=replay_report,
        )
        self.assertEqual(labels[0]["label_status"], "usable")

    def test_mobile_rollout_exports_state_change_episode(self) -> None:
        from synthesis.contracts import validate_episode_log_record
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels
        from synthesis.rollouts import collect_diagnostic_rollout_episodes

        seed = mobile_seed()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(seed, Path(tmpdir))
            task = next(
                candidate
                for candidate in generate_mobile_fixture_candidates(seed)
                if candidate.candidate_id == "candidate_mobile_maya_reminder"
            )

            episodes = collect_diagnostic_rollout_episodes(
                bundle=bundle,
                tasks=(task,),
                max_steps=3,
            )

        episode = episodes[0]
        validate_episode_log_record(episode)
        self.assertEqual(episode["runtime"]["runtime_id"], "mobile_messages_fixture")
        self.assertIn(
            "state_change",
            [transition["event_type"] for transition in episode["transitions"]],
        )
        replay_report = build_episode_replay_report(
            dataset_version="dataset_rollout_mobile",
            episodes=episodes,
        )
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_rollout_mobile",
                episodes=episodes,
            ),
            episode_replay_report=replay_report,
        )
        self.assertEqual(labels[0]["label_status"], "usable")

    def test_workspace_rollout_exports_state_change_episode(self) -> None:
        from synthesis.contracts import validate_episode_log_record
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels
        from synthesis.rollouts import collect_diagnostic_rollout_episodes

        seed = workspace_seed()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(seed, Path(tmpdir))
            task = next(
                candidate
                for candidate in generate_workspace_fixture_candidates(seed)
                if candidate.candidate_id == "candidate_workspace_launch_checklist_task"
            )

            episodes = collect_diagnostic_rollout_episodes(
                bundle=bundle,
                tasks=(task,),
                max_steps=3,
            )

        episode = episodes[0]
        validate_episode_log_record(episode)
        self.assertEqual(episode["runtime"]["runtime_id"], "workspace_tasks_fixture")
        self.assertIn(
            "state_change",
            [transition["event_type"] for transition in episode["transitions"]],
        )
        replay_report = build_episode_replay_report(
            dataset_version="dataset_rollout_workspace",
            episodes=episodes,
        )
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_rollout_workspace",
                episodes=episodes,
            ),
            episode_replay_report=replay_report,
        )
        self.assertEqual(labels[0]["label_status"], "usable")

    def test_rollout_max_step_enforcement_exports_failed_episode(self) -> None:
        from synthesis.rollouts import collect_diagnostic_rollout_episodes

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            task = next(
                candidate
                for candidate in generate_foundation_candidates(foundation_seed())
                if candidate.candidate_id == "candidate_contacts_alice_followup"
            )

            episodes = collect_diagnostic_rollout_episodes(
                bundle=bundle,
                tasks=(task,),
                max_steps=1,
            )

        self.assertEqual(episodes[0]["outcome"]["status"], "failed")
        self.assertEqual(episodes[0]["outcome"]["failure_cause"], "max_steps_exceeded")
        self.assertEqual(episodes[0]["transitions"][0]["event_type"], "error")


if __name__ == "__main__":
    unittest.main()
