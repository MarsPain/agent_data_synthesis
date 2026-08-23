from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class ContactsDomainLifecycleTest(unittest.TestCase):
    def _planned_contacts_run(self, tmpdir: str):
        from synthesis.contacts_domain_pack import (
            ContactsRuntimeScope,
            admitted_contacts_source,
            build_contacts_domain_pack,
            contacts_planning_intent,
        )
        from synthesis.domain_pack import DomainPlan
        from synthesis.domain_sources import build_domain_fixture_source_bundle
        from synthesis.sources import validate_source_bundle

        source_bundle = build_domain_fixture_source_bundle("contacts_fixture")
        source_result = validate_source_bundle(source_bundle)
        admitted_source = admitted_contacts_source(source_bundle, source_result)
        pack = build_contacts_domain_pack()
        plan = pack.plan(contacts_planning_intent(pack), admitted_source)
        self.assertIsInstance(plan, DomainPlan)
        assert isinstance(plan, DomainPlan)
        run = pack.open(
            plan,
            ContactsRuntimeScope(
                runtime_contract=plan.runtime_contract,
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=Path(tmpdir),
                include_branching=True,
            ),
        )
        return pack, plan, run, source_bundle, source_result, admitted_source

    def test_contacts_plan_open_attempt_replay_and_assessment_use_public_lifecycle(self) -> None:
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.domain_pack import (
            DomainAssessment,
            DomainAssessmentEvidence,
            DomainCandidateScope,
            DomainEvidenceReference,
        )
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            pack, plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(plan.domain_pack_reference.domain_pack_id, "contacts")
            self.assertEqual(plan.runtime_contract.runtime_id, "contacts_fixture")
            self.assertEqual(
                {reference.capability_key for reference in plan.capability_references},
                {
                    "contact_lookup",
                    "followup_recording",
                    "contact_lookup_recovery",
                    "missing_contact_safe_failure",
                },
            )
            spec = run.generation_spec
            self.assertIsNotNone(spec)
            assert spec is not None
            self.assertEqual(spec.domain_pack_reference, plan.domain_pack_reference)
            self.assertEqual(spec.plan_id, plan.plan_id)
            self.assertEqual(spec.plan_hash, plan.plan_hash)
            self.assertEqual(
                {
                    reference.capability_key
                    for reference in spec.capability_references
                },
                {
                    "contact_lookup",
                    "followup_recording",
                    "contact_lookup_recovery",
                    "missing_contact_safe_failure",
                },
            )
            followup_spec = next(
                item for item in spec.task_types if item.task_type == "contact_followup"
            )
            self.assertEqual(
                followup_spec.required_capabilities,
                ("contact_lookup", "followup_recording"),
            )

            from synthesis.domain_generation import DomainGenerationGroundingRequest

            with self.assertRaisesRegex(
                ValueError,
                "generation_grounding_tool_not_read_only",
            ):
                run.resolve_generation_grounding(
                    DomainGenerationGroundingRequest(
                        tool_name="record_contact_followup",
                        arguments={"name": "Alice Zhang", "note": "x"},
                    )
                )

            generated = run.generate(foundation_seed())
            task = next(
                item
                for item in generated
                if item.candidate_id == "candidate_contacts_alice_followup"
            )
            candidate_run = run.fork(
                DomainCandidateScope.for_plan(
                    plan,
                    candidate_id=task.candidate_id,
                    sequence_index=2,
                )
            )
            self.assertIsNotNone(candidate_run)
            assert candidate_run is not None
            attempt = candidate_run.attempt(
                task,
                dataset_version="dataset_contacts_domain_lifecycle",
            )
            self.assertIsNotNone(attempt.outcome.sample)
            self.assertIsNotNone(attempt.replay_subject)
            assert attempt.replay_subject is not None
            self.assertIn("contacts_evidence", attempt.outcome.sample or {})
            self.assertEqual(run.replay(attempt.replay_subject).reason_code, "replay_verified")

            second = run.attempt(
                CandidateExecutionRequest(
                    sequence_index=3,
                    raw_task=next(
                        item
                        for item in generated
                        if item.candidate_id == "candidate_contacts_alice"
                    ),
                ),
                dataset_version="dataset_contacts_domain_lifecycle",
            )
            self.assertIsNotNone(second.outcome.sample)
            self.assertNotEqual(attempt.evidence_hash, second.evidence_hash)

            unbound = run.attempt(
                CandidateExecutionRequest(
                    sequence_index=4,
                    raw_task=replace(
                        next(
                            item
                            for item in generated
                            if item.candidate_id == "candidate_contacts_alice"
                        ),
                        candidate_id="candidate_contacts_unbound",
                    ),
                ),
                dataset_version="dataset_contacts_domain_lifecycle",
            )
            self.assertEqual(
                unbound.outcome.rejection["details"]["membership_reason"],
                "capability_membership_mismatch",
            )

            assessment = pack.assess(
                plan,
                DomainAssessmentEvidence(
                    evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="contacts_lifecycle_attempt_v1",
                            evidence_schema_version="contacts_lifecycle_attempt_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                    ),
                    established_capability_references=(
                        next(
                            reference
                            for reference in plan.capability_references
                            if reference.capability_key == "followup_recording"
                        ),
                    ),
                ),
            )
            self.assertIsInstance(assessment, DomainAssessment)
            assert isinstance(assessment, DomainAssessment)
            self.assertEqual(assessment.status, "established")

    def test_contacts_open_and_replay_fail_closed_on_binding_drift(self) -> None:
        from synthesis.contacts_domain_pack import ContactsRuntimeScope
        from synthesis.domain_pack import DomainCandidateScope, DomainPlan, OpenFailure
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            pack, plan, run, source_bundle, source_result, admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            scope = ContactsRuntimeScope(
                runtime_contract=plan.runtime_contract,
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=Path(tmpdir) / "drift",
            )
            failed_runtime = pack.open(
                plan,
                replace(
                    scope,
                    runtime_contract=replace(
                        scope.runtime_contract,
                        runtime_contract_hash="sha256:" + "0" * 64,
                    ),
                ),
            )
            self.assertIsInstance(failed_runtime, OpenFailure)
            assert isinstance(failed_runtime, OpenFailure)
            self.assertEqual(failed_runtime.reason_code, "runtime_contract_drift")

            failed_source = pack.open(
                plan,
                replace(
                    scope,
                    source_result=replace(source_result, policy_outcome="rejected"),
                ),
            )
            self.assertIsInstance(failed_source, OpenFailure)
            assert isinstance(failed_source, OpenFailure)
            self.assertEqual(failed_source.reason_code, "source_drift")

            task = next(
                item
                for item in run.generate(foundation_seed())
                if item.candidate_id == "candidate_contacts_alice"
            )
            attempt = run.fork(
                DomainCandidateScope.for_plan(
                    plan,
                    candidate_id=task.candidate_id,
                    sequence_index=0,
                )
            ).attempt(task, dataset_version="dataset_contacts_domain_lifecycle")
            assert attempt.replay_subject is not None
            subject = attempt.replay_subject
            self.assertEqual(
                run.replay(
                    replace(
                        subject,
                        runtime_contract=replace(
                            subject.runtime_contract,
                            runtime_contract_hash="sha256:" + "1" * 64,
                        ),
                    )
                ).reason_code,
                "runtime_contract_drift",
            )
            self.assertEqual(
                run.replay(
                    replace(
                        subject,
                        admitted_source=replace(
                            subject.admitted_source,
                            source_content_hash="sha256:" + "2" * 64,
                        ),
                    )
                ).reason_code,
                "source_drift",
            )
            self.assertEqual(
                run.replay(
                    replace(
                        subject,
                        candidate_scope=replace(
                            subject.candidate_scope,
                            sequence_index=99,
                        ),
                    )
                ).reason_code,
                "candidate_scope_drift",
            )
            self.assertEqual(
                run.replay(replace(subject, verifier_version="different_v1")).reason_code,
                "verifier_drift",
            )
            self.assertEqual(
                run.replay(
                    replace(
                        subject,
                        candidate=replace(
                            subject.candidate,
                            expected_answer="not-the-grounded-answer",
                        ),
                    )
                ).reason_code,
                "candidate_contract_drift",
            )

    def test_fixture_and_governed_local_contacts_pipeline_use_domain_binding(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixture = run_foundation_pipeline(
                root / "fixture",
                dataset_version="dataset_contacts_domain_fixture",
                seed_override=foundation_seed(),
                write_episode_logs=True,
            )
            fixture_samples = [
                json.loads(line)
                for line in fixture.samples_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            fixture_episodes = [
                json.loads(line)
                for line in fixture.episode_logs_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual((fixture.accepted_count, fixture.rejected_count), (2, 1))
            self.assertEqual(len(fixture_episodes), 3)
            self.assertTrue(
                all(sample["domain_evidence"]["domain_pack_reference"]["domain_pack_id"] == "contacts"
                    for sample in fixture_samples)
            )

            importer = resolve_domain_source_importer(
                "contacts_fixture",
                "local_contacts_json",
            )
            source_input = build_profile_local_domain_source_input(
                ProfileLocalDomainSourceRequest(
                    domain_id="contacts_fixture",
                    kind="local_contacts_json",
                    source_id="source_profile_contacts_lifecycle_v1",
                    path=Path("tests/fixtures/run_profiles/contacts-profile.json"),
                    license_label="cc-by-4.0",
                    max_bytes=65536,
                ),
                importer=importer,
            )
            local = run_foundation_pipeline(
                root / "local",
                dataset_version="dataset_contacts_domain_local",
                seed_override=foundation_seed(),
                source_bundle=source_input.source_bundle,
                domain_environment_input=source_input.environment_input,
                source_events=source_input.events,
                enable_source_audit=True,
                write_episode_logs=True,
            )
            self.assertEqual((local.accepted_count, local.rejected_count), (2, 1))
            local_sample = json.loads(
                local.samples_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(
                local_sample["domain_evidence"]["runtime_contract"]["runtime_id"],
                "contacts_fixture",
            )
            self.assertEqual(
                local_sample["environment"]["reset_recipe"]["source_bundle_id"],
                source_input.environment_input.source_bundle_id,
            )


if __name__ == "__main__":
    unittest.main()
