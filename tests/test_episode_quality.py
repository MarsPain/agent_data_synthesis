from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.domain_pipeline import build_domain_pipeline_bundle
from synthesis.episodes import build_episode_log
from synthesis.execution import execute_candidate
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


class EpisodeQualityTest(unittest.TestCase):
    def test_builds_passed_report_from_valid_contacts_episodes(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report

        episodes = (
            _episode("candidate_contacts_alice"),
            _episode("candidate_contacts_alice_followup"),
        )

        report = build_episode_quality_report(
            dataset_version="dataset_contacts_quality_test",
            episodes=episodes,
        )

        self.assertEqual(report["schema_version"], "episode_quality_report_v1")
        self.assertEqual(report["observed"]["episode_count"], 2)
        self.assertEqual(report["observed"]["runtime_counts"]["contacts_fixture"], 2)
        self.assertEqual(report["decision"]["status"], "passed")
        for summary in report["episode_summaries"]:
            for forbidden in (
                "arguments",
                "observation",
                "content",
                "instruction",
                "expected_answer",
                "expected_state",
                "final_response",
            ):
                self.assertNotIn(forbidden, summary)

    def test_episode_quality_summaries_omit_raw_task_and_transition_content(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report

        report = build_episode_quality_report(
            dataset_version="dataset_quality_sanitized_summary",
            episodes=(
                _episode("candidate_contacts_alice_followup"),
                _episode("candidate_mobile_maya_reminder"),
            ),
        )

        forbidden = {
            "instruction",
            "expected_answer",
            "expected_state",
            "arguments",
            "observation",
            "content",
        }
        for summary in report["episode_summaries"]:
            self.assertTrue(forbidden.isdisjoint(summary))

    def test_mobile_state_change_episode_passes_state_change_support(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report

        report = build_episode_quality_report(
            dataset_version="dataset_mobile_quality_test",
            episodes=(_episode("candidate_mobile_maya_reminder"),),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "mobile_messages_fixture")
        self.assertEqual(summary["state_change_count"], 1)
        self.assertEqual(summary["failed_checks"], [])
        self.assertEqual(report["decision"]["status"], "passed")

    def test_workspace_state_change_episode_uses_descriptor_state_changing_tools(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report

        report = build_episode_quality_report(
            dataset_version="dataset_workspace_quality_test",
            episodes=(_episode("candidate_workspace_launch_checklist_task"),),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(summary["state_change_count"], 1)
        self.assertEqual(summary["failed_checks"], [])
        self.assertEqual(report["decision"]["status"], "passed")

    def test_fake_runtime_descriptor_is_accepted_without_consumer_allowlist(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.runtime import RuntimeCapabilityDescriptor, RuntimeRegistry

        episode = _with_runtime_and_tool(
            _episode("candidate_contacts_alice"),
            runtime_id="fake_quality_runtime",
            runtime_version="runtime_fake_quality_v1",
            tool_name="fake_read",
        )
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_quality_runtime",
                    runtime_version="runtime_fake_quality_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=False,
                    supports_local_adapter=False,
                    state_changing_tools=(),
                    task_taxonomy=("fake_lookup",),
                ),
            )
        )

        report = build_episode_quality_report(
            dataset_version="dataset_fake_quality_runtime",
            episodes=(episode,),
            runtime_registry=registry,
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "fake_quality_runtime")
        self.assertEqual(summary["failed_checks"], [])
        self.assertEqual(report["decision"]["status"], "passed")

    def test_state_changing_tools_are_derived_from_runtime_descriptor(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.runtime import RuntimeCapabilityDescriptor, RuntimeRegistry

        episode = _with_runtime_and_tool(
            _episode("candidate_contacts_alice"),
            runtime_id="fake_quality_runtime",
            runtime_version="runtime_fake_quality_v1",
            tool_name="fake_write",
        )
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_quality_runtime",
                    runtime_version="runtime_fake_quality_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=False,
                    supports_local_adapter=False,
                    state_changing_tools=("fake_write",),
                    task_taxonomy=("fake_lookup",),
                ),
            )
        )

        report = build_episode_quality_report(
            dataset_version="dataset_fake_quality_state_tools",
            episodes=(episode,),
            runtime_registry=registry,
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["failed_checks"], ["state_change_supported"])
        self.assertEqual(report["decision"]["status"], "watch")

    def test_unknown_runtime_is_unsupported_not_malformed_evidence(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.runtime import RuntimeRegistry

        episode = _with_runtime_and_tool(
            _episode("candidate_contacts_alice"),
            runtime_id="missing_quality_runtime",
            runtime_version="runtime_missing_quality_v1",
            tool_name="fake_read",
        )

        report = build_episode_quality_report(
            dataset_version="dataset_missing_quality_runtime",
            episodes=(episode,),
            runtime_registry=RuntimeRegistry(()),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "missing_quality_runtime")
        self.assertEqual(summary["failed_checks"], ["runtime_known"])
        self.assertNotIn("contract_valid", summary["failed_checks"])
        self.assertEqual(report["decision"]["status"], "watch")

    def test_missing_episodes_returns_insufficient_evidence(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report

        report = build_episode_quality_report(
            dataset_version="dataset_empty",
            episodes=(),
        )

        self.assertEqual(report["decision"]["status"], "insufficient_evidence")
        self.assertEqual(report["observed"]["episode_count"], 0)

    def test_report_contract_rejects_sensitive_content_and_absolute_paths(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_episode_quality_report_record,
        )
        from synthesis.episode_quality import build_episode_quality_report

        report = build_episode_quality_report(
            dataset_version="dataset_contacts_quality_test",
            episodes=(_episode("candidate_contacts_alice"),),
        )
        validate_episode_quality_report_record(report)

        with_absolute_path = {
            **report,
            "inputs": {
                **report["inputs"],
                "episodes_path": "/tmp/episodes.jsonl",
            },
        }
        with self.assertRaises(ContractValidationError):
            validate_episode_quality_report_record(with_absolute_path)

        with_sensitive_summary = {
            **report,
            "episode_summaries": [
                {
                    **report["episode_summaries"][0],
                    "content": "secret-test-key",
                }
            ],
        }
        with self.assertRaises(ContractValidationError):
            validate_episode_quality_report_record(with_sensitive_summary)

    def test_episode_log_jsonl_round_trips_valid_records(self) -> None:
        from synthesis.episode_quality import read_episode_logs, write_episode_logs

        episodes = (
            _episode("candidate_contacts_alice"),
            _episode("candidate_contacts_alice_followup"),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_episode_logs(Path(tmpdir) / "episodes.jsonl", episodes)
            text = path.read_text(encoding="utf-8")

            self.assertTrue(text.endswith("\n"))
            self.assertEqual(read_episode_logs(path), episodes)

    def test_episode_log_jsonl_rejects_non_object_lines(self) -> None:
        from synthesis.episode_quality import read_episode_logs

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "episodes.jsonl"
            path.write_text("[]\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "line 1"):
                read_episode_logs(path)


def _episode(candidate_id: str) -> dict[str, object]:
    if candidate_id.startswith("candidate_mobile_"):
        seed = mobile_seed()
        candidates = generate_mobile_fixture_candidates(seed)
    elif candidate_id.startswith("candidate_workspace_"):
        seed = workspace_seed()
        candidates = generate_workspace_fixture_candidates(seed)
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


def _with_runtime_and_tool(
    episode: dict[str, object],
    *,
    runtime_id: str,
    runtime_version: str,
    tool_name: str,
) -> dict[str, object]:
    transitions = []
    for transition in episode["transitions"]:
        assert isinstance(transition, dict)
        copied = dict(transition)
        if copied.get("tool_name") is not None:
            copied["tool_name"] = tool_name
        transitions.append(copied)
    runtime = dict(episode["runtime"])
    runtime["runtime_id"] = runtime_id
    runtime["runtime_version"] = runtime_version
    return {
        **episode,
        "runtime": runtime,
        "transitions": transitions,
    }


if __name__ == "__main__":
    unittest.main()
