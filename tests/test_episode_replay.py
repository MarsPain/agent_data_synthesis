from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from awm_runtime import RuntimeActionRequest, RuntimeSession, build_episode_log
from synthesis.domain_pipeline import build_domain_pipeline_bundle
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

    def test_episode_replay_summaries_omit_raw_task_and_transition_content(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_replay_sanitized_summary",
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

    def test_workspace_state_change_replay_matches_state_change_evidence(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_workspace_replay_test",
            episodes=(_episode("candidate_workspace_launch_checklist_task"),),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(summary["state_change_match_count"], 1)
        self.assertEqual(summary["state_change_mismatch_count"], 0)
        self.assertEqual(report["decision"]["status"], "passed")

    def test_source_backed_workspace_replay_uses_descriptor_boundary(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        episodes = (_source_backed_workspace_episode("candidate_workspace_launch_checklist_task"),)

        report = build_episode_replay_report(
            dataset_version="dataset_source_backed_workspace_replay",
            episodes=episodes,
        )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertEqual(
            report["observed"]["runtime_counts"],
            {"workspace_tasks_fixture": 1},
        )

    def test_supported_replay_executes_contacts_actions_through_runtime_session(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        calls: list[RuntimeActionRequest] = []
        original_execute_action = RuntimeSession.execute_action

        def spy_execute_action(
            session: RuntimeSession,
            request: RuntimeActionRequest,
        ):
            calls.append(request)
            return original_execute_action(session, request)

        with patch.object(RuntimeSession, "execute_action", spy_execute_action):
            report = build_episode_replay_report(
                dataset_version="dataset_contacts_replay_session_boundary",
                episodes=(_episode("candidate_contacts_alice_followup"),),
            )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertEqual(
            report["runtime_boundary_evidence"]["runtime_methods_used"],
            ["rebuild", "runtime_metadata", "execute_action"],
        )
        self.assertEqual(report["runtime_boundary_evidence"]["registry_methods_used"], [])
        self.assertEqual(
            [request.runtime_id for request in calls],
            ["contacts_fixture", "contacts_fixture"],
        )
        self.assertEqual(
            [request.tool_name for request in calls],
            ["lookup_contact_email", "record_contact_followup"],
        )

    def test_supported_replay_executes_mobile_actions_through_runtime_session(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        calls: list[RuntimeActionRequest] = []
        original_execute_action = RuntimeSession.execute_action

        def spy_execute_action(
            session: RuntimeSession,
            request: RuntimeActionRequest,
        ):
            calls.append(request)
            return original_execute_action(session, request)

        with patch.object(RuntimeSession, "execute_action", spy_execute_action):
            report = build_episode_replay_report(
                dataset_version="dataset_mobile_replay_session_boundary",
                episodes=(_episode("candidate_mobile_maya_reminder"),),
            )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertEqual(
            report["runtime_boundary_evidence"]["runtime_methods_used"],
            ["rebuild", "runtime_metadata", "execute_action"],
        )
        self.assertEqual(report["runtime_boundary_evidence"]["registry_methods_used"], [])
        self.assertEqual(
            [request.runtime_id for request in calls],
            ["mobile_messages_fixture", "mobile_messages_fixture"],
        )
        self.assertEqual(
            [request.tool_name for request in calls],
            ["search_phone_messages", "create_phone_reminder"],
        )

    def test_supported_replay_executes_workspace_actions_through_runtime_session(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        calls: list[RuntimeActionRequest] = []
        original_execute_action = RuntimeSession.execute_action

        def spy_execute_action(
            session: RuntimeSession,
            request: RuntimeActionRequest,
        ):
            calls.append(request)
            return original_execute_action(session, request)

        with patch.object(RuntimeSession, "execute_action", spy_execute_action):
            report = build_episode_replay_report(
                dataset_version="dataset_workspace_replay_session_boundary",
                episodes=(_episode("candidate_workspace_launch_checklist_task"),),
            )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertEqual(
            report["runtime_boundary_evidence"]["runtime_methods_used"],
            ["rebuild", "runtime_metadata", "execute_action"],
        )
        self.assertEqual(report["runtime_boundary_evidence"]["registry_methods_used"], [])
        self.assertEqual(
            [request.runtime_id for request in calls],
            ["workspace_tasks_fixture", "workspace_tasks_fixture"],
        )
        self.assertEqual(
            [request.tool_name for request in calls],
            ["search_workspace_items", "create_workspace_task"],
        )

    def test_replay_support_is_read_from_runtime_registry(self) -> None:
        from awm_runtime import RuntimeRegistry
        from synthesis.episode_replay import build_episode_replay_report

        report = build_episode_replay_report(
            dataset_version="dataset_contacts_replay_registry_override",
            episodes=(_episode("candidate_contacts_alice"),),
            runtime_registry=RuntimeRegistry(()),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "contacts_fixture")
        self.assertEqual(summary["replayed_action_count"], 0)
        self.assertEqual(summary["failed_checks"], ["runtime_supported"])
        self.assertEqual(report["decision"]["status"], "failed")

    def test_malformed_episode_evidence_is_not_reported_as_unsupported_runtime(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        episode = {
            **_episode("candidate_contacts_alice"),
            "transitions": [],
        }

        report = build_episode_replay_report(
            dataset_version="dataset_replay_malformed_episode",
            episodes=(episode,),
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["failed_checks"], ["contract_valid"])
        self.assertNotIn("runtime_supported", summary["failed_checks"])
        self.assertEqual(report["decision"]["status"], "failed")

    def test_replay_threshold_defaults_are_descriptor_derived(self) -> None:
        from synthesis.episode_replay import EpisodeReplayThresholds

        thresholds = EpisodeReplayThresholds()

        self.assertEqual(
            thresholds.supported_runtimes,
            frozenset(
                {
                    "contacts_fixture",
                    "mobile_messages_fixture",
                    "workspace_tasks_fixture",
                }
            ),
        )
        self.assertEqual(
            thresholds.state_changing_tools,
            frozenset(
                {
                    "record_contact_followup",
                    "create_phone_reminder",
                    "draft_message_reply",
                    "create_workspace_task",
                    "add_workspace_comment",
                }
            ),
        )

    def test_fake_runtime_without_replay_support_reports_unsupported(self) -> None:
        from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
        from synthesis.episode_replay import build_episode_replay_report

        episode = _episode("candidate_contacts_alice")
        episode = {
            **episode,
            "runtime": {
                **episode["runtime"],
                "runtime_id": "fake_reward_only_runtime",
                "runtime_version": "runtime_fake_v1",
            },
        }
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_reward_only_runtime",
                    runtime_version="runtime_fake_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=True,
                    supports_local_adapter=False,
                    state_changing_tools=("fake_write",),
                    task_taxonomy=("fake_lookup",),
                ),
            )
        )

        report = build_episode_replay_report(
            dataset_version="dataset_fake_runtime_replay",
            episodes=(episode,),
            runtime_registry=registry,
        )

        summary = report["episode_summaries"][0]
        self.assertEqual(summary["runtime_id"], "fake_reward_only_runtime")
        self.assertEqual(summary["failed_checks"], ["runtime_supported"])
        self.assertEqual(report["decision"]["status"], "failed")

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


def _source_backed_workspace_episode(candidate_id: str) -> dict[str, object]:
    from synthesis.domain_sources import (
        ProfileLocalDomainSourceRequest,
        build_profile_local_domain_source_input,
        resolve_domain_source_importer,
    )

    seed = workspace_seed()
    task = next(
        candidate
        for candidate in generate_workspace_fixture_candidates(seed)
        if candidate.candidate_id == candidate_id
    )
    importer = resolve_domain_source_importer(
        "workspace_tasks_fixture",
        "local_workspace_tasks_json",
    )
    source_input = build_profile_local_domain_source_input(
        ProfileLocalDomainSourceRequest(
            domain_id="workspace_tasks_fixture",
            kind="local_workspace_tasks_json",
            source_id="source_profile_workspace_tasks_v1",
            path=Path("tests/fixtures/run_profiles/workspace-tasks-profile.json"),
            license_label="cc-by-4.0",
            max_bytes=65536,
        ),
        importer=importer,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle = build_domain_pipeline_bundle(
            seed,
            Path(tmpdir),
            source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
            domain_environment_input=source_input.environment_input,
        )
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
