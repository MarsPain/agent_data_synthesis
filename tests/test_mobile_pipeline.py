from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.execution import ExecutionResult
from synthesis.seeds import DomainSeed, foundation_seed
from synthesis.tasks import CandidateTask


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


class MobilePipelineTest(unittest.TestCase):
    def test_mobile_fixture_candidates_cover_expected_task_shapes(self) -> None:
        from synthesis.mobile_tasks import generate_mobile_fixture_candidates

        candidates = generate_mobile_fixture_candidates(mobile_seed())

        task_types = {candidate.constraints.get("task_type") for candidate in candidates}
        self.assertGreaterEqual(len(candidates), 4)
        self.assertIn("mobile_message_lookup", task_types)
        self.assertIn("mobile_message_to_reminder", task_types)
        self.assertIn("mobile_draft_reply", task_types)
        self.assertIn("mobile_branch_fallback", task_types)
        for candidate in candidates:
            self.assertEqual(candidate.constraints["domain"], "mobile_messages_fixture")
            self.assertIn("task_type", candidate.constraints)

    def test_scripted_mobile_policy_covers_lookup_reminder_draft_and_branch(self) -> None:
        from synthesis.mobile_tasks import (
            generate_mobile_fixture_candidates,
            scripted_mobile_solution_policy,
        )

        candidates = generate_mobile_fixture_candidates(mobile_seed())
        policies = {
            str(candidate.constraints["task_type"]): scripted_mobile_solution_policy(candidate)
            for candidate in candidates
        }

        self.assertEqual(
            [step.tool_name for step in policies["mobile_message_lookup"].steps],
            ["search_phone_messages"],
        )
        self.assertEqual(
            [step.tool_name for step in policies["mobile_message_to_reminder"].steps],
            ["search_phone_messages", "create_phone_reminder"],
        )
        self.assertEqual(
            [step.tool_name for step in policies["mobile_draft_reply"].steps],
            ["search_phone_messages", "draft_message_reply"],
        )
        self.assertIsNotNone(policies["mobile_branch_fallback"].branch_plan)

    def test_domain_bundle_can_build_contacts_and_mobile(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mobile_tasks import generate_mobile_fixture_candidates
        from synthesis.tasks import generate_foundation_candidates

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            contacts = build_domain_pipeline_bundle(foundation_seed(), root / "contacts")
            mobile = build_domain_pipeline_bundle(mobile_seed(), root / "mobile")

            self.assertEqual(contacts.domain_id, "contacts_fixture")
            self.assertEqual(contacts.registry.tool_names()[0], "lookup_contact_email")
            self.assertEqual(contacts.candidate_generator, generate_foundation_candidates)
            self.assertEqual(mobile.domain_id, "mobile_messages_fixture")
            self.assertIn("search_phone_messages", mobile.registry.tool_names())
            self.assertEqual(mobile.candidate_generator, generate_mobile_fixture_candidates)

    def test_mobile_domain_bundle_rejects_mcp_adapter(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "MCP adapter"):
                build_domain_pipeline_bundle(
                    mobile_seed(),
                    Path(tmpdir),
                    enable_mcp_adapter=True,
                )

    def test_mobile_expected_state_verification_checks_environment(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment
        from synthesis.verification import ExactAnswerVerifier

        task = CandidateTask(
            candidate_id="candidate_mobile_state_check",
            instruction="Create a project update reminder from Maya's message.",
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_to_reminder",
            },
            difficulty={"level": "medium"},
            tool_name="create_phone_reminder",
            arguments={"title": "Send the project update"},
            expected_answer="msg_maya_project_update",
            seed_ids=("seed_mobile_messages_v1",),
            expected_state={
                "mobile_reminder": {
                    "title": "Send the project update",
                    "due_at": "tomorrow 9 AM",
                    "source_message_id": "msg_maya_project_update",
                }
            },
        )
        execution = ExecutionResult(
            trajectory=[],
            final_response="Reminder created from msg_maya_project_update.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))
            failed = ExactAnswerVerifier().verify(task, execution, environment=environment)
            environment.create_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )
            passed = ExactAnswerVerifier().verify(task, execution, environment=environment)

        self.assertFalse(failed.passed)
        self.assertEqual(failed.checks[-1]["cause"], "solution_logic_error")
        self.assertTrue(passed.passed)

    def test_mobile_seed_runs_through_foundation_pipeline(self) -> None:
        from synthesis.contracts import validate_sample_record
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_mobile_test",
                seed_override=mobile_seed(),
            )

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            quality_report = json.loads(
                result.quality_report_path.read_text(encoding="utf-8")
            )

        self.assertEqual(result.accepted_count, 4)
        self.assertEqual(result.rejected_count, 0)
        for sample in samples:
            validate_sample_record(sample)
            self.assertEqual(sample["environment"]["id"], "mobile_messages_fixture")
        tool_names = {tool["name"] for tool in samples[0]["tools"]}
        self.assertEqual(
            tool_names,
            {
                "search_phone_messages",
                "create_phone_reminder",
                "draft_message_reply",
            },
        )
        self.assertIn(
            "mobile_message_to_reminder",
            quality_report["slices"]["task_type"],
        )
        self.assertIn(
            "search_phone_messages > draft_message_reply",
            quality_report["slices"]["tool_combination"],
        )

    def test_mobile_pipeline_can_write_episode_logs_with_state_changes(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_mobile_episode_logs",
                seed_override=mobile_seed(),
                write_episode_logs=True,
            )

            self.assertIsNotNone(result.episode_logs_path)
            assert result.episode_logs_path is not None
            episodes = [
                json.loads(line)
                for line in result.episode_logs_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(episodes), 4)
        self.assertTrue(
            any(
                episode["runtime"]["runtime_id"] == "mobile_messages_fixture"
                for episode in episodes
            )
        )
        stateful_episodes = [
            episode
            for episode in episodes
            if any(
                transition.get("tool_name") in {"create_phone_reminder", "draft_message_reply"}
                for transition in episode["transitions"]
            )
        ]
        self.assertTrue(stateful_episodes)
        self.assertTrue(
            all(
                any(transition["event_type"] == "state_change" for transition in episode["transitions"])
                for episode in stateful_episodes
            )
        )

    def test_mobile_episode_logs_can_build_passed_replay_report(self) -> None:
        from synthesis.episode_quality import read_episode_logs
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_mobile_episode_replay",
                seed_override=mobile_seed(),
                write_episode_logs=True,
            )

            assert result.episode_logs_path is not None
            report = build_episode_replay_report(
                dataset_version="dataset_mobile_episode_replay",
                episodes=read_episode_logs(result.episode_logs_path),
                manifest_path=result.manifest_path,
                episodes_path=result.episode_logs_path,
            )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertGreater(
            report["observed"]["runtime_counts"]["mobile_messages_fixture"],
            0,
        )
        self.assertIn("create_phone_reminder", report["observed"]["tool_names"])
        self.assertTrue(
            any(
                summary["state_change_match_count"] > 0
                for summary in report["episode_summaries"]
            )
        )

    def test_mobile_candidate_carries_internal_episode_log_without_public_sample_field(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingContext,
            CandidateProcessingOptions,
            process_candidate_through_gates,
        )
        from synthesis.contracts import validate_episode_log_record
        from synthesis.llm import LLMConfig
        from synthesis.mobile_environment import MobileMessagesEnvironment
        from synthesis.mobile_tasks import scripted_mobile_solution_policy
        from synthesis.mobile_tools import build_mobile_tool_registry
        from synthesis.verification import ExactAnswerVerifier

        seed = mobile_seed()
        task = next(
            candidate
            for candidate in __import__(
                "synthesis.mobile_tasks",
                fromlist=["generate_mobile_fixture_candidates"],
            ).generate_mobile_fixture_candidates(seed)
            if candidate.candidate_id == "candidate_mobile_maya_reminder"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))
            outcome = process_candidate_through_gates(
                raw_task=task,
                context=CandidateProcessingContext(
                    dataset_version="dataset_mobile_episode_test",
                    environment=environment,
                    registry=build_mobile_tool_registry(environment),
                    adapter_shim=None,
                    verifier=ExactAnswerVerifier(),
                    llm_config=LLMConfig(base_url=None),
                    generate_policy=scripted_mobile_solution_policy,
                ),
                accepted_signatures=set(),
                options=CandidateProcessingOptions(),
            )

        self.assertIsNotNone(outcome.sample)
        self.assertIsNotNone(outcome.episode_log)
        assert outcome.episode_log is not None
        validate_episode_log_record(outcome.episode_log)
        self.assertEqual(
            outcome.episode_log["runtime"]["runtime_id"],
            "mobile_messages_fixture",
        )
        self.assertTrue(
            any(
                transition["event_type"] == "state_change"
                for transition in outcome.episode_log["transitions"]
            )
        )
        assert outcome.sample is not None
        self.assertNotIn("episode_log", outcome.sample)


if __name__ == "__main__":
    unittest.main()
