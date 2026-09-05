from __future__ import annotations

import copy
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
                            evidence_id="contacts_evaluation_report",
                            evidence_schema_version="evaluation_report_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                        DomainEvidenceReference(
                            evidence_id="contacts_release_evidence",
                            evidence_schema_version="dataset_release_report_v1",
                            evidence_hash=second.evidence_hash,
                        ),
                    ),
                    evaluation_evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="contacts_evaluation_report",
                            evidence_schema_version="evaluation_report_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                    ),
                    release_evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="contacts_release_evidence",
                            evidence_schema_version="dataset_release_report_v1",
                            evidence_hash=second.evidence_hash,
                        ),
                    ),
                    established_capability_references=tuple(plan.capability_references),
                    plan_id=plan.plan_id,
                    plan_hash=plan.plan_hash,
                ),
            )
            self.assertIsInstance(assessment, DomainAssessment)
            assert isinstance(assessment, DomainAssessment)
            self.assertEqual(assessment.status, "established")

            insufficient = pack.assess(
                plan,
                DomainAssessmentEvidence(
                    evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="contacts_evaluation_report",
                            evidence_schema_version="evaluation_report_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                    ),
                    evaluation_evidence_references=(
                        DomainEvidenceReference(
                            evidence_id="contacts_evaluation_report",
                            evidence_schema_version="evaluation_report_v1",
                            evidence_hash=attempt.evidence_hash,
                        ),
                    ),
                    plan_id=plan.plan_id,
                    plan_hash=plan.plan_hash,
                ),
            )
            self.assertIsInstance(insufficient, DomainAssessment)
            assert isinstance(insufficient, DomainAssessment)
            self.assertEqual(insufficient.status, "insufficient_evidence")
            self.assertEqual(insufficient.reason_code, "evidence_missing")

    def test_contacts_membership_distinguishes_primary_grounding_mismatch(self) -> None:
        from synthesis.domain_generation import task_contract_from_provider_record
        from synthesis.seeds import foundation_seed
        from synthesis.task_contracts import candidate_from_task_contract

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            spec = run.generation_spec
            assert spec is not None
            task_spec = next(
                item for item in spec.task_types if item.task_type == "contact_lookup"
            )
            grounding = next(iter(spec.grounding_context.values()))[0]
            observation = grounding["observation"]
            contract = task_contract_from_provider_record(
                {
                    "candidate_id": "generated_grounding_mismatch",
                    "instruction": "Find the contact email.",
                    "task_type": "contact_lookup",
                    "difficulty": {"state_changes": 0, "recovery_paths": 0},
                    "required_capabilities": list(task_spec.required_capabilities),
                    "required_tools": list(task_spec.required_tools),
                    "primary_tool": task_spec.required_tools[0],
                    "primary_arguments": {"name": "Unknown Person"},
                    "final_answer_contains": observation["email"],
                    "expected_state": [],
                },
                seed=foundation_seed(),
                spec=spec,
                candidate_id_prefix="generated_",
                generation_lineage={},
            )
            candidate = candidate_from_task_contract(contract)

        self.assertEqual(
            run._membership_reason(candidate),
            "grounding_primary_arguments_mismatch",
        )

    def test_contacts_membership_distinguishes_followup_state_mismatch(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            task_contract_from_provider_record,
        )
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            spec = run.generation_spec
            assert spec is not None
            task_spec = next(
                item for item in spec.task_types if item.task_type == "contact_followup"
            )
            grounding = next(iter(spec.grounding_context.values()))[0]
            observation = grounding["observation"]
            with self.assertRaisesRegex(
                DomainGenerationValidationError,
                "invalid_expected_state",
            ):
                task_contract_from_provider_record(
                    {
                        "candidate_id": "generated_followup_state_mismatch",
                        "instruction": "Record a follow-up.",
                        "task_type": "contact_followup",
                        "difficulty": {"state_changes": 1, "recovery_paths": 0},
                        "required_capabilities": list(task_spec.required_capabilities),
                        "required_tools": list(task_spec.required_tools),
                        "primary_tool": task_spec.required_tools[0],
                        "primary_arguments": grounding["primary_arguments"],
                        "final_answer_contains": observation["email"],
                        "expected_state": [
                            {
                                "check_type": "contact_followup",
                                "expected": {
                                    "name": observation["name"],
                                    "note": "Follow up later.",
                                },
                            }
                        ],
                    },
                    seed=foundation_seed(),
                    spec=spec,
                    candidate_id_prefix="generated_",
                    generation_lineage={},
                )

    def test_contacts_followup_grounding_bindings_require_one_observation(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            task_contract_from_provider_record,
        )
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            spec = run.generation_spec
            assert spec is not None
            task_spec = next(
                item for item in spec.task_types if item.task_type == "contact_followup"
            )
            grounding_entries = next(iter(spec.grounding_context.values()))
            first = grounding_entries[0]
            second = grounding_entries[1]

            with self.assertRaisesRegex(
                DomainGenerationValidationError,
                "invalid_expected_state",
            ):
                task_contract_from_provider_record(
                    {
                        "candidate_id": "generated_cross_grounding_mismatch",
                        "instruction": "Record a follow-up.",
                        "task_type": "contact_followup",
                        "difficulty": {"state_changes": 1, "recovery_paths": 0},
                        "required_capabilities": list(task_spec.required_capabilities),
                        "required_tools": list(task_spec.required_tools),
                        "primary_tool": task_spec.required_tools[0],
                        "primary_arguments": first["primary_arguments"],
                        "final_answer_contains": first["observation"]["email"],
                        "expected_state": [
                            {
                                "check_type": "contact_followup",
                                "expected": {
                                    "name": first["observation"]["name"],
                                    "note": (
                                        "Send follow-up email to "
                                        f"{second['observation']['email']}."
                                    ),
                                },
                            }
                        ],
                    },
                    seed=foundation_seed(),
                    spec=spec,
                    candidate_id_prefix="generated_",
                    generation_lineage={},
                )

    def test_contacts_followup_prompt_declares_grounding_bindings(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            spec = run.generation_spec
            assert spec is not None
            prompt = json.loads(
                build_domain_generation_prompt(
                    spec,
                    requested_candidate_count=1,
                    batch_context=build_generation_batch_context(spec, batch_index=2),
                )
            )

        expected_state = prompt["output_contract"]["task_type_contracts"][0][
            "expected_state"
        ]
        self.assertEqual(
            expected_state["grounding_bindings"],
            [
                {
                    "state_field": "name",
                    "observation_field": "name",
                    "match": "exact",
                },
                {
                    "state_field": "note",
                    "observation_field": "email",
                    "match": "contains",
                },
            ],
        )

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

    def test_contacts_recovery_credit_requires_executed_and_verified_fallback(self) -> None:
        from synthesis.contacts_evidence import contacts_recovery_evidence
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            candidate = next(
                item
                for item in run.generate(foundation_seed())
                if item.candidate_id == "candidate_contacts_alice_branch_fallback"
            )
            attempt = run.attempt(
                CandidateExecutionRequest(sequence_index=0, raw_task=candidate),
                dataset_version="dataset_contacts_recovery_evidence",
            )
            assert attempt.outcome.sample is not None
            sample = attempt.outcome.sample
            self.assertTrue(sample["contacts_evidence"]["recovery"]["verified"])

            status_drift = copy.deepcopy(sample)
            outcomes = status_drift["lineage"]["branching"]["branch_outcomes"]
            selected = next(outcome for outcome in outcomes if outcome["selected"])
            selected["outcome"] = "rejected"
            self.assertFalse(contacts_recovery_evidence(candidate, status_drift)["verified"])

            verifier_drift = copy.deepcopy(sample)
            verifier_drift["verification"]["passed"] = False
            self.assertFalse(
                contacts_recovery_evidence(candidate, verifier_drift)["verified"]
            )

    def test_contacts_unverified_recovery_cannot_become_an_accepted_sample(self) -> None:
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.execution import scripted_solution_policy
        from synthesis.seeds import foundation_seed

        def direct_success_policy(candidate):
            policy = scripted_solution_policy(candidate)
            if candidate.candidate_id != "candidate_contacts_alice_branch_fallback":
                return policy
            return replace(
                policy,
                branch_plan={
                    "schema_version": "branch_plan_v1",
                    "plan_id": "branch_plan_contacts_direct_success_only",
                    "max_depth": 1,
                    "branches": [
                        {
                            "branch_id": "direct_success",
                            "node_type": "attempt",
                            "parent_id": None,
                            "condition": "Use the full contact name directly.",
                            "steps": [
                                {
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice Zhang"},
                                }
                            ],
                            "final_response_template": "{name}'s email is {email}.",
                            "terminal_outcome": "accept_on_success",
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, _plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            candidate = next(
                item
                for item in run.generate(foundation_seed())
                if item.candidate_id == "candidate_contacts_alice_branch_fallback"
            )
            attempt = run.attempt(
                CandidateExecutionRequest(sequence_index=0, raw_task=candidate),
                dataset_version="dataset_contacts_recovery_evidence",
                policy_generator=direct_success_policy,
            )

        self.assertIsNone(attempt.outcome.sample)
        self.assertEqual(
            attempt.outcome.rejection["details"]["membership_reason"],
            "recovery_evidence_missing",
        )

    def test_contacts_replay_rejects_bound_plan_and_mutation_evidence_drift(self) -> None:
        from awm_runtime.episodes import deterministic_content_hash
        from synthesis.candidate_processing import CandidateExecutionRequest
        from synthesis.domain_pack import DomainCandidateScope, canonical_domain_pack_hash
        from synthesis.mutation_admission import canonical_hash
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            _pack, plan, run, _source_bundle, _source_result, _admitted_source = (
                self._planned_contacts_run(tmpdir)
            )
            assert run is not None
            candidate = next(
                item
                for item in run.generate(foundation_seed())
                if item.candidate_id == "candidate_contacts_alice_followup"
            )
            attempt = run.fork(
                DomainCandidateScope.for_plan(
                    plan,
                    candidate_id=candidate.candidate_id,
                    sequence_index=0,
                )
            ).attempt(
                candidate,
                dataset_version="dataset_contacts_evidence_drift",
            )
            assert attempt.replay_subject is not None

            for field_name, value in (
                ("mutation", {"evidence_hash": "sha256:" + "0" * 64}),
                (
                    "plan",
                    {
                        **attempt.replay_subject.episode["contacts_evidence"]["plan"],
                        "plan_record": {"changed": True},
                    },
                ),
            ):
                with self.subTest(field=field_name):
                    episode = copy.deepcopy(attempt.replay_subject.episode)
                    episode["contacts_evidence"][field_name] = value
                    drifted = replace(
                        attempt.replay_subject,
                        episode=episode,
                        episode_hash=deterministic_content_hash(episode),
                    )
                    self.assertEqual(
                        run.replay(drifted).reason_code,
                        "replay_evidence_mismatch",
                    )

            episode = copy.deepcopy(attempt.replay_subject.episode)
            binding = episode["contacts_evidence"]
            verification = binding["verification"]
            verification["checks"][0]["actual"] = "tampered"
            binding["verification_hash"] = canonical_domain_pack_hash(verification)
            binding["final_state"]["verification_hash"] = canonical_hash(verification)
            drifted = replace(
                attempt.replay_subject,
                episode=episode,
                episode_hash=deterministic_content_hash(episode),
            )
            self.assertEqual(
                run.replay(drifted).reason_code,
                "replay_verification_failed",
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
