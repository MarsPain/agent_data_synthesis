from __future__ import annotations

import copy
import inspect
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import synthesis.mutation_admission
from synthesis.candidate_processing import (
    CandidateProcessingContext,
    CandidateProcessingOptions,
    process_candidate_through_gates,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import scripted_solution_policy
from synthesis.llm import LLMConfig
from synthesis.mutation_admission import policy_hash
from synthesis.seeds import foundation_seed
from synthesis.tasks import (
    generate_deterministic_task_expansion,
    generate_foundation_candidates,
)
from synthesis.tools import build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


class ContactMutationAuthorizationGenerationTest(unittest.TestCase):
    def test_contact_followup_proposes_selected_contact_and_note_provenance(
        self,
    ) -> None:
        candidate = next(
            candidate
            for candidate in generate_foundation_candidates(foundation_seed())
            if candidate.candidate_id == "candidate_contacts_alice_followup"
        )
        record = candidate.contract().mutation_authorization

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(
            record["schema_version"],
            "mutation_authorization_record_v1",
        )
        self.assertRegex(str(record["instruction_hash"]), r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            record["policy_hash"],
            policy_hash(scripted_solution_policy(candidate)),
        )
        action = record["actions"][0]
        self.assertEqual(action["action_type"], "contact_followup_record")
        self.assertEqual(action["action_ref"], "policy.steps.1")
        provenance = {
            argument["name"]: argument
            for argument in action["arguments"]
        }
        self.assertEqual(provenance["name"]["origin"], "tool_observation")
        self.assertEqual(
            provenance["name"]["evidence"]["source_action_ref"],
            "policy.steps.0",
        )
        self.assertEqual(provenance["note"]["origin"], "instruction")
        self.assertIn(provenance["note"]["support"], {"literal", "semantic"})
        self.assertNotIn(
            provenance["note"]["origin"],
            {"declared_default", "deterministic_derivation", "model_inferred"},
        )
        instruction = candidate.instruction
        evidence_text = {
            name: instruction[
                argument["evidence"]["start"]:argument["evidence"]["end"]
            ]
            for name, argument in provenance.items()
            if argument["origin"] == "instruction"
        }
        selected_contact = provenance["name"]["evidence"][
            "binding_instruction_evidence"
        ]
        self.assertEqual(
            instruction[selected_contact["start"]:selected_contact["end"]],
            "Alice Zhang",
        )
        self.assertEqual(evidence_text["note"], "follow-up email should be sent")
        self.assertLess(
            action["instruction_evidence"]["end"]
            - action["instruction_evidence"]["start"],
            len(instruction),
        )

    def test_expanded_contact_followup_also_proposes_authorization(self) -> None:
        expansion = generate_deterministic_task_expansion(foundation_seed())
        candidate = next(
            candidate
            for candidate in expansion.candidates
            if candidate.constraints.get("task_type") == "contact_followup"
        )

        self.assertIsNotNone(candidate.mutation_authorization)
        assert candidate.mutation_authorization is not None
        self.assertEqual(
            candidate.mutation_authorization["policy_hash"],
            policy_hash(scripted_solution_policy(candidate)),
        )


class ContactMutationAdmissionCandidateProcessingTest(unittest.TestCase):
    def _candidate(self, candidate_id: str = "candidate_contacts_alice_followup"):
        return next(
            candidate
            for candidate in generate_foundation_candidates(foundation_seed())
            if candidate.candidate_id == candidate_id
        )

    def _process(self, candidate, *, mode: str = "shadow", judge=None):
        from synthesis.contact_mutations import (
            build_contact_followup_semantic_mutation_judge,
            contact_followup_mutation_policies,
        )
        from synthesis.mutation_admission import (
            build_local_candidate_admission_evaluator,
        )

        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = ContactEnvironment.create_fixture(
            Path(temporary_directory.name)
        )
        evaluator = build_local_candidate_admission_evaluator(
            mode=mode,
            policies=contact_followup_mutation_policies(environment),
            state_changing_tools=("record_contact_followup",),
            judge=judge or build_contact_followup_semantic_mutation_judge(environment),
        )
        outcome = process_candidate_through_gates(
            raw_task=candidate,
            context=CandidateProcessingContext(
                dataset_version="dataset_contact_mutation_admission_test",
                environment=environment,
                registry=build_contact_tool_registry(environment),
                adapter_shim=None,
                verifier=ExactAnswerVerifier(),
                llm_config=LLMConfig(base_url=None),
                generate_policy=scripted_solution_policy,
                admission_evaluator=evaluator,
            ),
            options=CandidateProcessingOptions(),
        )
        return outcome, environment

    def test_supported_contact_followup_executes_and_retains_shadow_evidence(
        self,
    ) -> None:
        outcome, environment = self._process(self._candidate())

        self.assertTrue(
            environment.has_followup(
                "Alice Zhang",
                "Send follow-up email to alice.zhang@example.test.",
            )
        )
        self.assertIsNotNone(outcome.sample)
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(evidence["classification"], "state_changing")
        self.assertEqual(evidence["mode"], "shadow")
        self.assertEqual(evidence["deterministic_validation"]["status"], "passed")
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertEqual(
            evidence["contract_versions"]["domain_policy"],
            "contact_followup_mutation_policy_v1",
        )
        retained = repr(evidence).lower()
        self.assertNotIn("alice zhang", retained)
        self.assertNotIn("send follow-up email", retained)

    def test_supported_contact_followup_executes_in_enforce_mode(self) -> None:
        outcome, environment = self._process(
            self._candidate(),
            mode="enforce",
        )

        self.assertTrue(
            environment.has_followup(
                "Alice Zhang",
                "Send follow-up email to alice.zhang@example.test.",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(evidence["mode"], "enforce")
        self.assertEqual(evidence["admission_outcome"], "judge_supported")
        self.assertEqual(evidence["model_independence"], "independent")

    def test_deterministic_contact_failures_are_bounded_without_blocking_shadow(
        self,
    ) -> None:
        from synthesis.contact_mutations import propose_contact_followup_authorization

        base = self._candidate()
        assert base.mutation_authorization is not None

        def changed_record(change):
            record = copy.deepcopy(base.mutation_authorization)
            change(record)
            return replace(base, mutation_authorization=record)

        def remove_note(record):
            arguments = record["actions"][0]["arguments"]
            record["actions"][0]["arguments"] = [
                argument for argument in arguments if argument["name"] != "note"
            ]

        def use_unsupported_origin(record):
            note = next(
                argument
                for argument in record["actions"][0]["arguments"]
                if argument["name"] == "note"
            )
            note["origin"] = "model_inferred"

        false_binding = propose_contact_followup_authorization(
            replace(
                base,
                arguments={"name": "Ben Carter"},
                expected_answer="ben.carter@example.test",
                expected_state={
                    "contact_followup": {
                        "name": "Ben Carter",
                        "note": "Send follow-up email to alice.zhang@example.test.",
                    }
                },
            )
        )
        cases = (
            (
                "authorization_record_missing",
                replace(base, mutation_authorization=None),
            ),
            (
                "requester_argument_provenance_missing",
                changed_record(remove_note),
            ),
            (
                "provenance_origin_invalid",
                changed_record(use_unsupported_origin),
            ),
            ("observation_reference_invalid", false_binding),
        )

        for expected_code, candidate in cases:
            with self.subTest(expected_code=expected_code):
                outcome, environment = self._process(candidate)

                self.assertTrue(
                    environment.has_followup(
                        candidate.expected_state["contact_followup"]["name"],
                        candidate.expected_state["contact_followup"]["note"],
                    )
                )
                assert outcome.sample is not None
                evidence = outcome.sample["mutation_admission"]
                self.assertEqual(
                    evidence["deterministic_validation"]["status"],
                    "failed",
                )
                self.assertIn(
                    expected_code,
                    evidence["deterministic_validation"]["reason_codes"],
                )
                self.assertNotIn("semantic_verdict", evidence)
                for finding in evidence["deterministic_validation"]["findings"]:
                    self.assertEqual(
                        finding["failure_class"],
                        "mutation_admission_failed",
                    )
                    self.assertNotIn("Alice Zhang", repr(finding))

    def test_contact_judge_produces_literal_semantic_unsupported_and_uncertain(
        self,
    ) -> None:
        from synthesis.contact_mutations import propose_contact_followup_authorization

        base = self._candidate()
        literal_note = "Send follow-up email to alice.zhang@example.test."
        literal = propose_contact_followup_authorization(
            replace(
                base,
                instruction=(
                    "Find Alice Zhang's email address and record the follow-up note "
                    f'"{literal_note}"'
                ),
            )
        )
        unsupported = propose_contact_followup_authorization(
            replace(
                base,
                expected_state={
                    "contact_followup": {
                        "name": "Alice Zhang",
                        "note": "Schedule quarterly planning.",
                    }
                },
            )
        )
        uncertain = propose_contact_followup_authorization(
            replace(
                base,
                instruction=(
                    "If needed, find Alice Zhang's email address and record that "
                    "a follow-up email should be sent."
                ),
            )
        )

        for expected_verdict, expected_reason, candidate in (
            ("supported", "argument_literal_supported", literal),
            ("supported", "argument_semantic_supported", base),
            ("unsupported", "argument_not_supported", unsupported),
            ("uncertain", "conditional_authorization_ambiguous", uncertain),
        ):
            with self.subTest(expected_verdict=expected_verdict, reason=expected_reason):
                outcome, _ = self._process(candidate)

                assert outcome.sample is not None
                verdict = outcome.sample["mutation_admission"]["semantic_verdict"]
                self.assertEqual(verdict["verdict"], expected_verdict)
                self.assertIn(expected_reason, verdict["reason_codes"])
                self.assertNotIn("confidence", verdict)
                self.assertNotIn("rationale", verdict)

    def test_distractor_contact_and_partially_overlapping_invented_note_fail(
        self,
    ) -> None:
        from synthesis.contact_mutations import propose_contact_followup_authorization

        base = self._candidate()
        distractor_binding = propose_contact_followup_authorization(
            replace(
                base,
                instruction=(
                    "Do not contact Ben Carter. Find Alice Zhang's email address "
                    "and record that a follow-up email should be sent."
                ),
                arguments={"name": "Ben Carter"},
                expected_answer="ben.carter@example.test",
                expected_state={
                    "contact_followup": {
                        "name": "Ben Carter",
                        "note": "Send follow-up email to ben.carter@example.test.",
                    }
                },
            )
        )
        invented_note = propose_contact_followup_authorization(
            replace(
                base,
                expected_state={
                    "contact_followup": {
                        "name": "Alice Zhang",
                        "note": "Send confidential salary report by follow-up email.",
                    }
                },
            )
        )

        binding_outcome, _ = self._process(distractor_binding)
        note_outcome, _ = self._process(invented_note)

        assert binding_outcome.sample is not None
        binding_evidence = binding_outcome.sample["mutation_admission"]
        self.assertIn(
            "observation_reference_invalid",
            binding_evidence["deterministic_validation"]["reason_codes"],
        )
        self.assertNotIn("semantic_verdict", binding_evidence)
        assert note_outcome.sample is not None
        note_verdict = note_outcome.sample["mutation_admission"]["semantic_verdict"]
        self.assertEqual(note_verdict["verdict"], "unsupported")
        self.assertIn("argument_not_supported", note_verdict["reason_codes"])

    def test_read_only_and_disabled_modes_preserve_contact_behavior(self) -> None:
        class FailingJudge:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, request):
                self.calls += 1
                raise AssertionError("read-only contacts must bypass the judge")

        judge = FailingJudge()
        read_only, _ = self._process(
            self._candidate("candidate_contacts_alice"),
            judge=judge,
        )
        disabled, environment = self._process(
            self._candidate(),
            mode="disabled",
        )

        self.assertEqual(judge.calls, 0)
        assert read_only.sample is not None
        self.assertEqual(
            read_only.sample["mutation_admission"]["classification"],
            "read_only",
        )
        assert disabled.sample is not None
        self.assertNotIn(
            "semantic_verdict",
            disabled.sample["mutation_admission"],
        )
        self.assertTrue(
            environment.has_followup(
                "Alice Zhang",
                "Send follow-up email to alice.zhang@example.test.",
            )
        )

    def test_other_rejection_retains_contact_shadow_evidence(self) -> None:
        candidate = replace(
            self._candidate(),
            expected_answer="missing_expected_answer",
        )

        outcome, environment = self._process(candidate)

        self.assertIsNone(outcome.sample)
        assert outcome.rejection is not None
        self.assertEqual(outcome.rejection["cause"], "verification_failed")
        evidence = outcome.rejection["details"]["mutation_admission"]
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertTrue(
            environment.has_followup(
                "Alice Zhang",
                "Send follow-up email to alice.zhang@example.test.",
            )
        )

    def test_shared_admission_kernel_has_no_contact_domain_branches(self) -> None:
        source = inspect.getsource(synthesis.mutation_admission)

        for domain_owned_name in (
            "contacts_fixture",
            "contact_followup",
            "record_contact_followup",
        ):
            self.assertNotIn(domain_owned_name, source)


class ContactMutationAdmissionPipelineTest(unittest.TestCase):
    def test_shadow_profile_retains_contact_evidence_without_changing_outcomes(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        base_profile = {
            "schema_version": "run_profile_v4",
            "profile_id": "contacts_mutation_admission",
            "dataset_version": "dataset_contacts_mutation_admission",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_contacts_mutation_admission",
                "domain": "contacts_fixture",
                "description": "Shadow-admit contact follow-ups.",
                "task_taxonomy": ["contact_lookup", "contact_followup"],
            },
            "generation": {"mode": "foundation_fixture"},
            "features": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {}
            samples = {}

            def generated_without_authorization(seed):
                return [
                    replace(candidate, mutation_authorization=None)
                    for candidate in generate_foundation_candidates(seed)
                ]

            for mode in ("disabled", "shadow"):
                profile_path = root / f"{mode}.json"
                profile_path.write_text(
                    json.dumps(
                        {
                            **base_profile,
                            "profile_id": f"contacts_{mode}",
                            "mutation_admission": {"mode": mode},
                        }
                    ),
                    encoding="utf-8",
                )
                profile = load_run_profile(profile_path)
                results[mode] = run_foundation_pipeline(
                    root / f"output-{mode}",
                    dataset_version=profile.dataset_version,
                    seed_override=profile.seed,
                    run_profile=profile,
                    run_profile_metadata=profile.sanitized_metadata(),
                    candidate_generator=generated_without_authorization,
                )
                samples[mode] = [
                    json.loads(line)
                    for line in results[mode].samples_path.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line
                ]

        self.assertEqual(
            (
                results["disabled"].accepted_count,
                results["disabled"].rejected_count,
            ),
            (
                results["shadow"].accepted_count,
                results["shadow"].rejected_count,
            ),
        )
        followup = next(
            sample
            for sample in samples["shadow"]
            if sample["sample_id"] == "sample_candidate_contacts_alice_followup"
        )
        evidence = followup["mutation_admission"]
        self.assertEqual(evidence["admission_outcome"], "judge_supported")
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")


if __name__ == "__main__":
    unittest.main()
