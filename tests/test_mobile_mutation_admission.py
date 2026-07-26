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
from synthesis.llm import LLMConfig
from synthesis.mobile_environment import MobileMessagesEnvironment
from synthesis.mobile_mutations import (
    mobile_semantic_mutation_judge,
    mobile_mutation_policies,
    prepare_mobile_candidate,
)
from synthesis.mobile_tasks import (
    generate_mobile_fixture_candidates,
    scripted_mobile_solution_policy,
)
from synthesis.mobile_tools import build_mobile_tool_registry
from synthesis.mutation_admission import build_local_candidate_admission_evaluator
from synthesis.mutation_admission import policy_hash
from synthesis.verification import ExactAnswerVerifier
from tests.test_mobile_pipeline import mobile_seed


class MobileMutationAuthorizationGenerationTest(unittest.TestCase):
    def test_mobile_mutations_propose_complete_requester_provenance(self) -> None:
        candidates = {
            candidate.candidate_id: candidate
            for candidate in generate_mobile_fixture_candidates(mobile_seed())
        }

        expected_arguments = {
            "candidate_mobile_maya_reminder": {
                "title": "instruction",
                "due_at": "instruction",
                "source_message_id": "tool_observation",
            },
            "candidate_mobile_alex_draft_reply": {
                "body": "instruction",
                "thread_id": "tool_observation",
            },
        }
        for candidate_id, expected_origins in expected_arguments.items():
            with self.subTest(candidate_id=candidate_id):
                candidate = candidates[candidate_id]
                record = candidate.contract().mutation_authorization

                self.assertIsNotNone(record)
                assert record is not None
                self.assertEqual(
                    record["schema_version"],
                    "mutation_authorization_record_v1",
                )
                self.assertEqual(
                    record["policy_hash"],
                    policy_hash(scripted_mobile_solution_policy(candidate)),
                )
                action = record["actions"][0]
                provenance = {
                    argument["name"]: argument["origin"]
                    for argument in action["arguments"]
                }
                self.assertEqual(provenance, expected_origins)


class MobileMutationAdmissionCandidateProcessingTest(unittest.TestCase):
    def _candidate(self, candidate_id: str):
        return next(
            candidate
            for candidate in generate_mobile_fixture_candidates(mobile_seed())
            if candidate.candidate_id == candidate_id
        )

    def _process(self, candidate, *, mode: str = "shadow"):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = MobileMessagesEnvironment.create_fixture(
            Path(temporary_directory.name)
        )
        evaluator = build_local_candidate_admission_evaluator(
            mode=mode,
            policies=mobile_mutation_policies(environment),
            state_changing_tools=(
                "create_phone_reminder",
                "draft_message_reply",
            ),
            judge=mobile_semantic_mutation_judge,
        )
        outcome = process_candidate_through_gates(
            raw_task=candidate,
            context=CandidateProcessingContext(
                dataset_version="dataset_mobile_mutation_admission_test",
                environment=environment,
                registry=build_mobile_tool_registry(environment),
                adapter_shim=None,
                verifier=ExactAnswerVerifier(),
                llm_config=LLMConfig(base_url=None),
                generate_policy=scripted_mobile_solution_policy,
                admission_evaluator=evaluator,
            ),
            options=CandidateProcessingOptions(),
        )
        return outcome, environment

    def test_supported_mobile_mutations_execute_in_enforce_mode(self) -> None:
        cases = (
            (
                "candidate_mobile_maya_reminder",
                lambda environment: environment.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                ),
            ),
            (
                "candidate_mobile_alex_draft_reply",
                lambda environment: environment.has_draft_reply(
                    thread_id="thread_alex",
                    body="I will be five minutes late.",
                ),
            ),
        )
        for candidate_id, state_check in cases:
            with self.subTest(candidate_id=candidate_id):
                outcome, environment = self._process(
                    self._candidate(candidate_id),
                    mode="enforce",
                )

                self.assertTrue(state_check(environment))
                assert outcome.sample is not None
                evidence = outcome.sample["mutation_admission"]
                self.assertEqual(evidence["mode"], "enforce")
                self.assertEqual(
                    evidence["admission_outcome"],
                    "judge_supported",
                )
                self.assertEqual(
                    evidence["model_independence"],
                    "independent",
                )

    def test_supported_mobile_mutations_execute_and_retain_shadow_evidence(
        self,
    ) -> None:
        cases = (
            (
                "candidate_mobile_maya_reminder",
                "mobile_reminder_create",
                lambda environment: environment.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                ),
            ),
            (
                "candidate_mobile_alex_draft_reply",
                "mobile_draft_reply_create",
                lambda environment: environment.has_draft_reply(
                    thread_id="thread_alex",
                    body="I will be five minutes late.",
                ),
            ),
        )
        for candidate_id, action_type, state_check in cases:
            with self.subTest(candidate_id=candidate_id):
                outcome, environment = self._process(self._candidate(candidate_id))

                self.assertIsNotNone(outcome.sample)
                assert outcome.sample is not None
                self.assertTrue(state_check(environment))
                evidence = outcome.sample["mutation_admission"]
                self.assertEqual(
                    evidence["deterministic_validation"]["status"],
                    "passed",
                )
                self.assertEqual(
                    evidence["semantic_verdict"]["verdict"],
                    "supported",
                )
                self.assertIn(
                    "argument_literal_supported",
                    evidence["semantic_verdict"]["reason_codes"],
                )
                self.assertIn(
                    "observation_reference_supported",
                    evidence["semantic_verdict"]["reason_codes"],
                )
                self.assertEqual(
                    evidence["semantic_verdict"]["action_findings"][0][
                        "action_type"
                    ],
                    action_type,
                )

    def test_generated_retrieve_wording_preserves_message_binding(self) -> None:
        base = self._candidate("candidate_mobile_maya_reminder")
        candidate = prepare_mobile_candidate(
            replace(
                base,
                instruction=(
                    "Retrieve the message from Maya about the project update "
                    "and set a reminder."
                ),
                constraints={
                    **base.constraints,
                    "task_type": "mobile_reminder_creation",
                },
                expected_state={
                    "mobile_reminder": {
                        "title": "Project Update",
                        "source_message_id": "msg_maya_project_update",
                    }
                },
            )
        )

        outcome, _ = self._process(candidate)

        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(
            evidence["semantic_verdict"]["verdict"],
            "supported",
        )

    def test_reminder_without_due_time_is_supported_without_a_default(self) -> None:
        candidate = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                instruction=(
                    "Find Maya's project update message and create the reminder "
                    '"Send the project update".'
                ),
                expected_state={
                    "mobile_reminder": {
                        "title": "Send the project update",
                        "source_message_id": "msg_maya_project_update",
                    }
                },
            )
        )

        outcome, environment = self._process(candidate)

        self.assertTrue(
            environment.has_reminder(
                title="Send the project update",
                due_at=None,
                source_message_id="msg_maya_project_update",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        argument_names = {
            finding["argument"]
            for finding in evidence["semantic_verdict"]["argument_findings"]
        }
        self.assertEqual(argument_names, {"title", "source_message_id"})

    def test_generation_task_type_reminder_is_shadow_admitted(self) -> None:
        base = self._candidate("candidate_mobile_maya_reminder")
        candidate = prepare_mobile_candidate(
            replace(
                base,
                constraints={
                    **base.constraints,
                    "task_type": "mobile_reminder_creation",
                },
            )
        )

        outcome, environment = self._process(candidate)

        self.assertTrue(
            environment.has_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(evidence["admission_outcome"], "judge_supported")

    def test_invalid_mobile_arguments_produce_bounded_shadow_findings(self) -> None:
        missing_body = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_alex_draft_reply"),
                expected_state={
                    "mobile_draft_reply": {
                        "thread_id": "thread_alex",
                        "body": "",
                    }
                },
            )
        )
        unsupported_schedule = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                expected_state={
                    "mobile_reminder": {
                        "title": "Send the project update",
                        "due_at": "next Friday at noon",
                        "source_message_id": "msg_maya_project_update",
                    }
                },
            )
        )
        false_binding = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                expected_state={
                    "mobile_reminder": {
                        "title": "Send the project update",
                        "due_at": "tomorrow 9 AM",
                        "source_message_id": "msg_delivery_code",
                    }
                },
            )
        )
        false_thread_binding = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_alex_draft_reply"),
                expected_state={
                    "mobile_draft_reply": {
                        "thread_id": "thread_delivery",
                        "body": "I will be five minutes late.",
                    }
                },
            )
        )
        smuggled_record = copy.deepcopy(
            self._candidate(
                "candidate_mobile_alex_draft_reply"
            ).mutation_authorization
        )
        assert smuggled_record is not None
        smuggled_record["actions"][0]["arguments"].append(
            {
                "name": "admin_override",
                "origin": "instruction",
                "support": "literal",
                "evidence": smuggled_record["actions"][0][
                    "instruction_evidence"
                ],
            }
        )
        smuggled = replace(
            self._candidate("candidate_mobile_alex_draft_reply"),
            mutation_authorization=smuggled_record,
        )

        body_outcome, _ = self._process(missing_body)
        schedule_outcome, _ = self._process(unsupported_schedule)
        binding_outcome, _ = self._process(false_binding)
        thread_binding_outcome, _ = self._process(false_thread_binding)
        smuggling_outcome, _ = self._process(smuggled)

        assert body_outcome.rejection is not None
        self.assertEqual(body_outcome.rejection["cause"], "tool_runtime_error")
        body_evidence = body_outcome.rejection["details"]["mutation_admission"]
        self.assertEqual(
            body_evidence["semantic_verdict"]["verdict"],
            "unsupported",
        )
        self.assertIn(
            "argument_not_supported",
            body_evidence["semantic_verdict"]["reason_codes"],
        )
        assert schedule_outcome.sample is not None
        schedule_evidence = schedule_outcome.sample["mutation_admission"]
        self.assertEqual(
            schedule_evidence["semantic_verdict"]["verdict"],
            "unsupported",
        )
        self.assertIn(
            "argument_not_supported",
            schedule_evidence["semantic_verdict"]["reason_codes"],
        )
        for outcome in (
            binding_outcome,
            thread_binding_outcome,
            smuggling_outcome,
        ):
            assert outcome.sample is not None
            evidence = outcome.sample["mutation_admission"]
            self.assertEqual(
                evidence["deterministic_validation"]["status"],
                "failed",
            )
            self.assertNotIn("semantic_verdict", evidence)
        self.assertIn(
            "observation_reference_invalid",
            binding_outcome.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        self.assertIn(
            "observation_reference_invalid",
            thread_binding_outcome.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        self.assertIn(
            "authorization_action_mismatch",
            smuggling_outcome.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        self.assertNotIn(
            "admin_override",
            repr(smuggling_outcome.sample["mutation_admission"]),
        )

    def test_semantic_mobile_requests_and_conditional_request_are_auditable(
        self,
    ) -> None:
        semantic_reminder = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                instruction=(
                    "Find Maya's project update message and create a reminder to "
                    "send the project status."
                ),
                expected_state={
                    "mobile_reminder": {
                        "title": "Share the project status",
                        "source_message_id": "msg_maya_project_update",
                    }
                },
            )
        )
        semantic_reply = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_alex_draft_reply"),
                instruction=(
                    "Find Alex's message about being five minutes late and draft "
                    "a reply thanking him for telling you about the delay."
                ),
                expected_state={
                    "mobile_draft_reply": {
                        "thread_id": "thread_alex",
                        "body": "Thanks for telling me about the delay.",
                    }
                },
            )
        )
        conditional = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                instruction=(
                    "If needed, find Maya's project update message and create a "
                    "reminder to send the project update tomorrow at 9 AM."
                ),
            )
        )

        for candidate in (semantic_reminder, semantic_reply):
            with self.subTest(candidate_id=candidate.candidate_id):
                outcome, _ = self._process(candidate)

                assert outcome.sample is not None
                verdict = outcome.sample["mutation_admission"][
                    "semantic_verdict"
                ]
                self.assertEqual(verdict["verdict"], "supported")
                self.assertIn(
                    "argument_semantic_supported",
                    verdict["reason_codes"],
                )

        conditional_outcome, _ = self._process(conditional)
        assert conditional_outcome.sample is not None
        conditional_verdict = conditional_outcome.sample[
            "mutation_admission"
        ]["semantic_verdict"]
        self.assertEqual(conditional_verdict["verdict"], "uncertain")
        self.assertIn(
            "conditional_authorization_ambiguous",
            conditional_verdict["reason_codes"],
        )

    def test_semantic_selection_action_and_time_paraphrases_are_supported(
        self,
    ) -> None:
        reminder = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                instruction=(
                    "Locate Maya's status note and schedule the reminder "
                    '"Send the project update" at 09:00 tomorrow.'
                ),
            )
        )
        reply = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_alex_draft_reply"),
                instruction=(
                    "Locate Alex's message about a five minute delay and write "
                    'a response saying "I will be five minutes late."'
                ),
            )
        )

        for candidate in (reminder, reply):
            with self.subTest(candidate_id=candidate.candidate_id):
                outcome, _ = self._process(candidate)

                assert outcome.sample is not None
                evidence = outcome.sample["mutation_admission"]
                self.assertEqual(
                    evidence["deterministic_validation"]["status"],
                    "passed",
                )
                self.assertEqual(
                    evidence["semantic_verdict"]["verdict"],
                    "supported",
                )
                self.assertIn(
                    "observation_reference_supported",
                    evidence["semantic_verdict"]["reason_codes"],
                )

    def test_partial_overlap_and_negation_cannot_support_requester_content(
        self,
    ) -> None:
        conflicting_title = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_maya_reminder"),
                instruction=(
                    "Find Maya's project update message and create a reminder "
                    "to approve the project status."
                ),
                expected_state={
                    "mobile_reminder": {
                        "title": "Reject the project status",
                        "source_message_id": "msg_maya_project_update",
                    }
                },
            )
        )
        negated_body = prepare_mobile_candidate(
            replace(
                self._candidate("candidate_mobile_alex_draft_reply"),
                instruction=(
                    "Find Alex's message about being five minutes late and draft "
                    "a reply saying not to approve the delay."
                ),
                expected_state={
                    "mobile_draft_reply": {
                        "thread_id": "thread_alex",
                        "body": "Approve the delay.",
                    }
                },
            )
        )

        for candidate in (conflicting_title, negated_body):
            with self.subTest(candidate_id=candidate.candidate_id):
                outcome, _ = self._process(candidate)

                assert outcome.sample is not None
                verdict = outcome.sample["mutation_admission"][
                    "semantic_verdict"
                ]
                self.assertEqual(verdict["verdict"], "unsupported")
                self.assertIn(
                    "argument_not_supported",
                    verdict["reason_codes"],
                )

    def test_shared_admission_kernel_has_no_mobile_domain_branches(self) -> None:
        source = inspect.getsource(synthesis.mutation_admission)

        for domain_owned_name in (
            "mobile_messages_fixture",
            "create_phone_reminder",
            "draft_message_reply",
        ):
            self.assertNotIn(domain_owned_name, source)


class MobileMutationAdmissionPipelineTest(unittest.TestCase):
    def test_shadow_profile_retains_mobile_evidence_without_changing_outcomes(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        base_profile = {
            "schema_version": "run_profile_v4",
            "profile_id": "mobile_mutation_admission",
            "dataset_version": "dataset_mobile_mutation_admission",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_mobile_mutation_admission",
                "domain": "mobile_messages_fixture",
                "description": "Shadow-admit mobile mutations.",
                "task_taxonomy": [
                    "mobile_message_lookup",
                    "mobile_message_to_reminder",
                    "mobile_draft_reply",
                ],
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
                    for candidate in generate_mobile_fixture_candidates(seed)
                ]

            for mode in ("disabled", "shadow"):
                profile_path = root / f"{mode}.json"
                profile_path.write_text(
                    json.dumps(
                        {
                            **base_profile,
                            "profile_id": f"mobile_{mode}",
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
        shadow_by_id = {
            sample["sample_id"]: sample
            for sample in samples["shadow"]
        }
        for candidate_id in (
            "candidate_mobile_maya_reminder",
            "candidate_mobile_alex_draft_reply",
        ):
            evidence = shadow_by_id[f"sample_{candidate_id}"][
                "mutation_admission"
            ]
            self.assertEqual(evidence["admission_outcome"], "judge_supported")
            self.assertEqual(
                evidence["semantic_verdict"]["verdict"],
                "supported",
            )
        read_only = shadow_by_id["sample_candidate_mobile_maya_lookup"][
            "mutation_admission"
        ]
        self.assertEqual(read_only["classification"], "read_only")
        self.assertNotIn("semantic_verdict", read_only)


if __name__ == "__main__":
    unittest.main()
