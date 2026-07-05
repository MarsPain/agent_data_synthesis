from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from awm_runtime import build_episode_log
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


class RewardLabelsTest(unittest.TestCase):
    def test_builds_usable_label_for_passed_contacts_episode(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_contacts_alice"),)
        quality_report = build_episode_quality_report(
            dataset_version="dataset_reward_contacts",
            episodes=episodes,
        )
        replay_report = build_episode_replay_report(
            dataset_version="dataset_reward_contacts",
            episodes=episodes,
        )

        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=quality_report,
            episode_replay_report=replay_report,
        )

        label = labels[0]
        self.assertEqual(label["schema_version"], "reward_label_v1")
        self.assertEqual(label["candidate_id"], "candidate_contacts_alice")
        self.assertEqual(label["runtime_id"], "contacts_fixture")
        self.assertEqual(label["label_status"], "usable")
        self.assertEqual(label["scalar_reward"], 1.0)
        self.assertIn("accepted_episode", label["reasons"])
        self.assertIn("quality_checks_passed", label["reasons"])
        self.assertIn("replay_checks_passed", label["reasons"])

    def test_mobile_state_change_label_uses_state_support(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_mobile_maya_reminder"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_mobile",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_reward_mobile",
                episodes=episodes,
            ),
        )

        label = labels[0]
        self.assertEqual(label["runtime_id"], "mobile_messages_fixture")
        self.assertEqual(label["components"]["state_support"], 1.0)
        self.assertEqual(label["label_status"], "usable")

    def test_workspace_state_change_label_uses_descriptor_preference_group(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_workspace_launch_checklist_task"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_workspace",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_reward_workspace",
                episodes=episodes,
            ),
        )

        label = labels[0]
        self.assertEqual(label["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(label["label_status"], "usable")
        self.assertEqual(label["components"]["state_support"], 1.0)
        self.assertEqual(
            label["preference_group"]["group_id"],
            "pref_workspace_tasks_fixture_workspace_task_creation",
        )

    def test_source_backed_workspace_reward_labels_remain_usable(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_source_backed_workspace_episode("candidate_workspace_launch_checklist_task"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_source_backed_workspace_reward",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_source_backed_workspace_reward",
                episodes=episodes,
            ),
        )

        self.assertEqual(labels[0]["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(labels[0]["label_status"], "usable")

    def test_reward_runtime_support_is_read_from_runtime_registry(self) -> None:
        from awm_runtime import RuntimeRegistry
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_contacts_alice"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_registry_override",
                episodes=episodes,
            ),
            episode_replay_report=None,
            runtime_registry=RuntimeRegistry(()),
        )

        label = labels[0]
        self.assertEqual(label["runtime_id"], "contacts_fixture")
        self.assertEqual(label["label_status"], "excluded")
        self.assertIn("runtime_unsupported", label["reasons"])

    def test_reward_state_changing_tools_are_descriptor_derived(self) -> None:
        from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_contacts_alice_followup"),)
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="contacts_fixture",
                    runtime_version="contacts_fixture_v1",
                    domain_id="contacts_fixture",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=True,
                    supports_local_adapter=False,
                    state_changing_tools=(),
                    task_taxonomy=("contact_followup",),
                ),
            )
        )

        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=None,
            episode_replay_report=None,
            runtime_registry=registry,
        )

        label = labels[0]
        self.assertEqual(label["components"]["state_support"], 1.0)
        self.assertNotIn("state_change_support_missing", label["reasons"])

    def test_fake_runtime_reward_capability_status_is_descriptor_derived(self) -> None:
        from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
        from synthesis.reward_labels import reward_label_runtime_capability_status

        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_reward_only_runtime",
                    runtime_version="runtime_fake_reward_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=True,
                    supports_local_adapter=False,
                    state_changing_tools=("fake_write",),
                    task_taxonomy=("fake_lookup",),
                ),
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_no_reward_runtime",
                    runtime_version="runtime_fake_none_v1",
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

        self.assertEqual(
            reward_label_runtime_capability_status(
                "fake_reward_only_runtime",
                runtime_registry=registry,
            ),
            "supported",
        )
        self.assertEqual(
            reward_label_runtime_capability_status(
                "fake_no_reward_runtime",
                runtime_registry=registry,
            ),
            "unsupported",
        )
        self.assertEqual(
            reward_label_runtime_capability_status(
                "missing_runtime",
                runtime_registry=registry,
            ),
            "unsupported",
        )
        self.assertEqual(
            reward_label_runtime_capability_status(
                None,
                runtime_registry=registry,
            ),
            "insufficient_evidence",
        )

    def test_fake_reward_runtime_labels_and_report_validate_without_contract_allowlist(
        self,
    ) -> None:
        from synthesis.contracts import (
            validate_reward_label_record,
            validate_reward_label_report_record,
        )
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.reward_labels import build_reward_label_report, build_reward_labels
        from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry

        episode = _with_runtime_and_tool(
            _episode("candidate_contacts_alice"),
            runtime_id="fake_reward_runtime",
            runtime_version="runtime_fake_reward_v1",
            tool_name="fake_lookup",
        )
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_reward_runtime",
                    runtime_version="runtime_fake_reward_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=True,
                    supports_local_adapter=False,
                    state_changing_tools=(),
                    task_taxonomy=("fake_lookup",),
                    reward_preference_groups={"fake_lookup": "fake_lookup"},
                ),
            )
        )
        quality_report = build_episode_quality_report(
            dataset_version="dataset_fake_reward_runtime",
            episodes=(episode,),
            runtime_registry=registry,
        )

        labels = build_reward_labels(
            episodes=(episode,),
            episode_quality_report=quality_report,
            episode_replay_report=None,
            runtime_registry=registry,
        )
        report = build_reward_label_report(
            dataset_version="dataset_fake_reward_runtime",
            episodes=(episode,),
            labels=labels,
        )

        self.assertEqual(labels[0]["runtime_id"], "fake_reward_runtime")
        self.assertEqual(labels[0]["preference_group"]["group_id"], "pref_fake_reward_runtime_fake_lookup")
        validate_reward_label_record(labels[0])
        validate_reward_label_report_record(report)

    def test_preference_grouping_is_descriptor_owned_for_fake_runtime(self) -> None:
        from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.reward_labels import build_reward_labels

        episode = _with_runtime_and_tool(
            _episode("candidate_contacts_alice"),
            runtime_id="fake_group_runtime",
            runtime_version="runtime_fake_group_v1",
            tool_name="fake_search_records",
        )
        registry = RuntimeRegistry(
            (
                RuntimeCapabilityDescriptor(
                    runtime_id="fake_group_runtime",
                    runtime_version="runtime_fake_group_v1",
                    domain_id="fake_domain",
                    supports_rebuild=False,
                    supports_checkpoint_restore=False,
                    supports_episode_replay=False,
                    supports_reward_labels=True,
                    supports_local_adapter=False,
                    state_changing_tools=(),
                    task_taxonomy=("fake_lookup",),
                    reward_preference_groups={"fake_search_records": "fake_declared_lookup"},
                ),
            )
        )
        quality_report = build_episode_quality_report(
            dataset_version="dataset_fake_group_runtime",
            episodes=(episode,),
            runtime_registry=registry,
        )

        label = build_reward_labels(
            episodes=(episode,),
            episode_quality_report=quality_report,
            episode_replay_report=None,
            runtime_registry=registry,
        )[0]

        self.assertEqual(
            label["preference_group"]["group_id"],
            "pref_fake_group_runtime_fake_declared_lookup",
        )

    def test_contacts_mobile_and_workspace_flow_through_quality_replay_and_reward_consumers(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_label_report, build_reward_labels

        episodes = (
            _episode("candidate_contacts_alice"),
            _episode("candidate_mobile_maya_reminder"),
            _episode("candidate_workspace_launch_checklist_task"),
        )
        quality_report = build_episode_quality_report(
            dataset_version="dataset_cross_consumer_regression",
            episodes=episodes,
        )
        replay_report = build_episode_replay_report(
            dataset_version="dataset_cross_consumer_regression",
            episodes=episodes,
        )
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=quality_report,
            episode_replay_report=replay_report,
        )
        reward_report = build_reward_label_report(
            dataset_version="dataset_cross_consumer_regression",
            episodes=episodes,
            labels=labels,
        )

        self.assertEqual(quality_report["decision"]["status"], "passed")
        self.assertEqual(replay_report["decision"]["status"], "passed")
        self.assertEqual(reward_report["decision"]["status"], "passed")
        self.assertEqual(
            quality_report["observed"]["runtime_counts"],
            {
                "contacts_fixture": 1,
                "mobile_messages_fixture": 1,
                "workspace_tasks_fixture": 1,
            },
        )
        self.assertEqual(
            reward_report["observed"]["runtime_counts"],
            {
                "contacts_fixture": 1,
                "mobile_messages_fixture": 1,
                "workspace_tasks_fixture": 1,
            },
        )
        self.assertEqual({label["label_status"] for label in labels}, {"usable"})

    def test_missing_replay_evidence_creates_watchable_usable_label(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.reward_labels import build_reward_label_report, build_reward_labels

        episodes = (_episode("candidate_contacts_alice"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_no_replay",
                episodes=episodes,
            ),
            episode_replay_report=None,
        )
        report = build_reward_label_report(
            dataset_version="dataset_reward_no_replay",
            episodes=episodes,
            labels=labels,
        )

        self.assertEqual(labels[0]["components"]["replay_consistency"], 0.5)
        self.assertIn("replay_evidence_absent", labels[0]["reasons"])
        self.assertEqual(report["decision"]["status"], "watch")

    def test_empty_episodes_returns_insufficient_evidence_report(self) -> None:
        from synthesis.reward_labels import build_reward_label_report

        report = build_reward_label_report(
            dataset_version="dataset_empty",
            episodes=(),
            labels=(),
        )

        self.assertEqual(report["decision"]["status"], "insufficient_evidence")
        self.assertEqual(report["observed"]["label_count"], 0)

    def test_reward_label_contract_rejects_raw_content_and_absolute_paths(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_reward_label_record,
        )
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_episode("candidate_contacts_alice"),)
        label = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_contract",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_reward_contract",
                episodes=episodes,
            ),
        )[0]
        validate_reward_label_record(label)

        with_absolute_path = {
            **label,
            "label_source": {
                **label["label_source"],
                "artifact_path": "/tmp/reward.jsonl",
            },
        }
        with self.assertRaises(ContractValidationError):
            validate_reward_label_record(with_absolute_path)

        with_raw_preference = {
            **label,
            "preference_group": {
                **label["preference_group"],
                "instruction": "Find Alice",
            },
        }
        with self.assertRaises(ContractValidationError):
            validate_reward_label_record(with_raw_preference)

    def test_reward_label_report_rejects_sensitive_summary_content(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_reward_label_report_record,
        )
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_label_report, build_reward_labels

        episodes = (_episode("candidate_contacts_alice"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_reward_report_contract",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_reward_report_contract",
                episodes=episodes,
            ),
        )
        report = build_reward_label_report(
            dataset_version="dataset_reward_report_contract",
            episodes=episodes,
            labels=labels,
        )
        validate_reward_label_report_record(report)

        with_sensitive_summary = {
            **report,
            "label_summaries": [
                {
                    **report["label_summaries"][0],
                    "observation": {"email": "alice.zhang@example.test"},
                }
            ],
        }
        with self.assertRaises(ContractValidationError):
            validate_reward_label_report_record(with_sensitive_summary)


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
