from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class WorkspaceDomainLifecycleTest(unittest.TestCase):
    def test_workspace_plan_open_attempt_replay_and_assessment_stay_at_public_seam(
        self,
    ) -> None:
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.domain_pack import (
            DomainAssessment,
            DomainAssessmentEvidence,
            DomainCandidateScope,
            DomainEvidenceReference,
            DomainPlan,
            DomainPlanningIntent,
        )
        from synthesis.domain_sources import build_domain_fixture_source_bundle
        from synthesis.sources import validate_source_bundle
        from synthesis.workspace_domain_pack import (
            WorkspaceCandidateRun,
            WorkspaceDomainRun,
            WorkspaceRuntimeScope,
            admitted_workspace_source,
            build_workspace_domain_pack,
        )
        from tests.test_workspace_pipeline import workspace_seed

        source_bundle = build_domain_fixture_source_bundle("workspace_tasks_fixture")
        source_result = validate_source_bundle(source_bundle)
        admitted_source = admitted_workspace_source(source_bundle, source_result)
        pack = build_workspace_domain_pack()
        descriptor = pack.descriptor
        capabilities = {
            item.capability_key: item
            for item in descriptor.capability_references
        }
        plan = pack.plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=(
                    "workspace_item_search",
                    "workspace_task_creation",
                    "workspace_comment_update",
                ),
                capability_references=(
                    capabilities["item_search"],
                    capabilities["task_creation"],
                    capabilities["comment_addition"],
                ),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            admitted_source,
        )
        self.assertIsInstance(plan, DomainPlan)
        assert isinstance(plan, DomainPlan)

        with tempfile.TemporaryDirectory() as tmpdir:
            scope = WorkspaceRuntimeScope(
                runtime_contract=descriptor.runtime_contracts[0],
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=Path(tmpdir),
            )
            run = pack.open(plan, scope)
            self.assertIsInstance(run, WorkspaceDomainRun)
            assert isinstance(run, WorkspaceDomainRun)
            self.assertFalse(hasattr(run, "environment"))
            self.assertFalse(hasattr(run, "registry"))
            self.assertFalse(hasattr(run, "verifier"))
            self.assertFalse(hasattr(run, "candidate_preparer"))
            self.assertFalse(hasattr(run, "execute_generation_tool"))

            from synthesis.domain_generation import DomainGenerationGroundingRequest

            with self.assertRaisesRegex(
                ValueError,
                "generation_grounding_tool_not_read_only",
            ):
                run.resolve_generation_grounding(
                    DomainGenerationGroundingRequest(
                        tool_name="create_workspace_task",
                        arguments={},
                    )
                )

            generated = run.generate(workspace_seed())
            task = next(
                item
                for item in generated
                if item.candidate_id == "candidate_workspace_launch_checklist_task"
            )
            candidate_run = run.fork(
                DomainCandidateScope.for_plan(
                    plan,
                    candidate_id=task.candidate_id,
                    sequence_index=3,
                )
            )
            self.assertIsInstance(candidate_run, WorkspaceCandidateRun)
            assert isinstance(candidate_run, WorkspaceCandidateRun)
            attempt = candidate_run.attempt(
                task,
                dataset_version="dataset_workspace_domain_lifecycle",
            )
            self.assertIsNotNone(attempt.outcome.sample)
            self.assertIsNotNone(attempt.replay_subject)
            assert attempt.replay_subject is not None

            replay = run.replay(attempt.replay_subject)
            self.assertEqual(replay.status, "passed")
            self.assertEqual(replay.reason_code, "replay_verified")

            legacy_fallback = next(
                item
                for item in generated
                if item.candidate_id == "candidate_workspace_launch_branch_fallback"
            )
            unplanned_attempt = run.attempt(
                CandidateExecutionRequest(
                    sequence_index=4,
                    raw_task=replace(
                        legacy_fallback,
                        candidate_id="candidate_workspace_unplanned_fallback",
                    ),
                ),
                dataset_version="dataset_workspace_domain_lifecycle",
            )
            self.assertEqual(
                unplanned_attempt.outcome.rejection["cause"],
                "domain_plan_membership_rejected",
            )

            unplanned_capability_attempt = run.attempt(
                CandidateExecutionRequest(
                    sequence_index=5,
                    raw_task=replace(
                        task,
                        constraints={
                            **task.constraints,
                            "required_capabilities": ["unplanned_capability"],
                        },
                    ),
                ),
                dataset_version="dataset_workspace_domain_lifecycle",
            )
            self.assertEqual(
                unplanned_capability_attempt.outcome.rejection["cause"],
                "domain_plan_membership_rejected",
            )
            self.assertEqual(
                unplanned_capability_attempt.outcome.rejection["details"][
                    "membership_reason"
                ],
                "legacy_fixture_membership_mismatch",
            )

            assessment = pack.assess(
                plan,
                DomainAssessmentEvidence(
                    evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="workspace_lifecycle_attempt_v1",
                            evidence_schema_version="workspace_lifecycle_attempt_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                    ),
                    established_capability_references=(capabilities["task_creation"],),
                ),
            )
            self.assertIsInstance(assessment, DomainAssessment)
            assert isinstance(assessment, DomainAssessment)
            self.assertEqual(assessment.status, "established")

    def test_open_and_replay_reject_exact_contract_drift_with_bounded_reasons(
        self,
    ) -> None:
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.domain_pack import (
            DomainCandidateScope,
            DomainPlan,
            DomainPlanningIntent,
            OpenFailure,
            canonical_domain_pack_hash,
        )
        from synthesis.domain_sources import build_domain_fixture_source_bundle
        from synthesis.sources import validate_source_bundle
        from synthesis.workspace_domain_pack import (
            WorkspaceRuntimeScope,
            admitted_workspace_source,
            build_workspace_domain_pack,
        )
        from synthesis.workspace_sources import WorkspaceTasksSourceImporter
        from tests.test_workspace_pipeline import workspace_seed

        source_bundle = build_domain_fixture_source_bundle("workspace_tasks_fixture")
        source_result = validate_source_bundle(source_bundle)
        admitted_source = admitted_workspace_source(source_bundle, source_result)
        pack = build_workspace_domain_pack()
        descriptor = pack.descriptor
        capabilities = {
            item.capability_key: item
            for item in descriptor.capability_references
        }
        plan = pack.plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=("workspace_item_search",),
                capability_references=(capabilities["item_search"],),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            admitted_source,
        )
        self.assertIsInstance(plan, DomainPlan)
        assert isinstance(plan, DomainPlan)

        with tempfile.TemporaryDirectory() as tmpdir:
            scope = WorkspaceRuntimeScope(
                runtime_contract=descriptor.runtime_contracts[0],
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=Path(tmpdir),
            )
            changed_runtime_scope = replace(
                scope,
                runtime_contract=replace(
                    scope.runtime_contract,
                    runtime_contract_hash="sha256:" + "0" * 64,
                ),
            )
            failed_open = pack.open(plan, changed_runtime_scope)
            self.assertIsInstance(failed_open, OpenFailure)
            assert isinstance(failed_open, OpenFailure)
            self.assertEqual(failed_open.reason_code, "runtime_contract_drift")

            failed_source_open = pack.open(
                plan,
                replace(
                    scope,
                    source_result=replace(source_result, policy_outcome="rejected"),
                ),
            )
            self.assertIsInstance(failed_source_open, OpenFailure)
            assert isinstance(failed_source_open, OpenFailure)
            self.assertEqual(failed_source_open.reason_code, "source_drift")

            source_input = WorkspaceTasksSourceImporter().build_environment_input(
                Path(
                    "tests/fixtures/run_profiles/workspace-tasks-profile.json"
                ).read_bytes(),
                source_bundle_id=source_bundle.bundle_id,
                source_policy_hash=source_result.source_policy_hash,
            )
            failed_input_binding = pack.open(
                plan,
                replace(
                    scope,
                    domain_environment_input=replace(
                        source_input,
                        source_bundle_id="other_bundle",
                    ),
                ),
            )
            self.assertIsInstance(failed_input_binding, OpenFailure)
            assert isinstance(failed_input_binding, OpenFailure)
            self.assertEqual(failed_input_binding.reason_code, "source_drift")
            failed_policy_binding = pack.open(
                plan,
                replace(
                    scope,
                    domain_environment_input=replace(
                        source_input,
                        source_policy_hash="sha256:" + "3" * 64,
                    ),
                ),
            )
            self.assertIsInstance(failed_policy_binding, OpenFailure)
            assert isinstance(failed_policy_binding, OpenFailure)
            self.assertEqual(failed_policy_binding.reason_code, "source_drift")

            run = pack.open(plan, scope)
            legacy_task_creation = next(
                item
                for item in run.generate(workspace_seed())
                if item.candidate_id == "candidate_workspace_launch_checklist_task"
            )
            rejected_legacy_attempt = run.attempt(
                CandidateExecutionRequest(
                    sequence_index=9,
                    raw_task=legacy_task_creation,
                ),
                dataset_version="dataset_workspace_domain_lifecycle",
            )
            self.assertEqual(
                rejected_legacy_attempt.outcome.rejection["cause"],
                "domain_plan_membership_rejected",
            )
            self.assertEqual(
                rejected_legacy_attempt.outcome.rejection["details"][
                    "membership_reason"
                ],
                "legacy_task_not_in_plan",
            )
            task = next(
                item
                for item in run.generate(workspace_seed())
                if item.candidate_id == "candidate_workspace_launch_lookup"
            )
            attempt = run.fork(
                DomainCandidateScope.for_plan(
                    plan,
                    candidate_id=task.candidate_id,
                    sequence_index=0,
                )
            ).attempt(
                task,
                dataset_version="dataset_workspace_domain_lifecycle",
            )
            assert attempt.replay_subject is not None
            checks = {
                "runtime_contract_drift": replace(
                    attempt.replay_subject,
                    runtime_contract=replace(
                        attempt.replay_subject.runtime_contract,
                        runtime_contract_hash="sha256:" + "1" * 64,
                    ),
                ),
                "source_drift": replace(
                    attempt.replay_subject,
                    admitted_source=replace(
                        attempt.replay_subject.admitted_source,
                        source_content_hash="sha256:" + "2" * 64,
                    ),
                ),
                "episode_drift": replace(
                    attempt.replay_subject,
                    episode={"changed": "episode"},
                ),
                "verifier_drift": replace(
                    attempt.replay_subject,
                    verifier_version="different_verifier_v1",
                ),
                "capability_contract_drift": replace(
                    attempt.replay_subject,
                    capability_references=(capabilities["task_creation"],),
                ),
            }
            for expected_reason, subject in checks.items():
                with self.subTest(reason=expected_reason):
                    self.assertEqual(run.replay(subject).reason_code, expected_reason)

            drifted_episode = {
                **attempt.replay_subject.episode,
                "candidate_id": "candidate_workspace_drifted_episode",
            }
            self.assertEqual(
                run.replay(
                    replace(
                        attempt.replay_subject,
                        episode=drifted_episode,
                        episode_hash=canonical_domain_pack_hash(drifted_episode),
                    )
                ).reason_code,
                "episode_drift",
            )
            drifted_episode_id = {
                **attempt.replay_subject.episode,
                "episode_id": "episode_sample_candidate_workspace_rewritten",
            }
            self.assertEqual(
                run.replay(
                    replace(
                        attempt.replay_subject,
                        episode=drifted_episode_id,
                        episode_hash=canonical_domain_pack_hash(drifted_episode_id),
                    )
                ).reason_code,
                "episode_drift",
            )
            self.assertEqual(
                run.replay(
                    replace(
                        attempt.replay_subject,
                        candidate=replace(
                            attempt.replay_subject.candidate,
                            expected_answer="different_workspace_answer",
                        ),
                    )
                ).reason_code,
                "candidate_contract_drift",
            )

    def test_workspace_fixture_pipeline_preserves_existing_outputs_through_lifecycle(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from tests.test_workspace_pipeline import workspace_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_workspace_lifecycle_fixture",
                seed_override=workspace_seed(),
                write_episode_logs=True,
            )
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            episodes = [
                json.loads(line)
                for line in result.episode_logs_path.read_text(encoding="utf-8").splitlines()
                if line
            ]

        self.assertEqual((result.accepted_count, result.rejected_count), (5, 0))
        self.assertEqual(
            {sample["sample_id"] for sample in samples},
            {
                "sample_candidate_workspace_launch_lookup",
                "sample_candidate_workspace_metrics_review_lookup",
                "sample_candidate_workspace_launch_checklist_task",
                "sample_candidate_workspace_launch_comment",
                "sample_candidate_workspace_launch_branch_fallback",
            },
        )
        self.assertEqual(len(episodes), 5)
        self.assertTrue(all(episode["schema_version"] == "episode_log_v1" for episode in episodes))
        self.assertTrue(all("domain_plan" not in sample for sample in samples))

    def test_shared_pipeline_does_not_name_workspace_or_domain_run_internals(self) -> None:
        forbidden = (
            "workspace_tasks_fixture",
            "search_workspace_items",
            "create_workspace_task",
            "add_workspace_comment",
            "workspace_domain_run",
            "workspacecandidaterun",
        )
        for path in (
            Path("synthesis/pipeline.py"),
            Path("synthesis/candidate_processing.py"),
            Path("synthesis/coverage_assignments.py"),
        ):
            source = path.read_text(encoding="utf-8").lower()
            for marker in forbidden:
                with self.subTest(path=str(path), marker=marker):
                    self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
