from __future__ import annotations

import tempfile
import unittest
import copy
from dataclasses import replace
from pathlib import Path

from synthesis.candidate_processing import (
    CandidateProcessingContext,
    CandidateProcessingOptions,
    process_candidate_through_gates,
)
from synthesis.llm import LLMConfig
from synthesis.mutation_admission import build_local_candidate_admission_evaluator
from synthesis.tasks import CandidateTask
from synthesis.verification import ExactAnswerVerifier
from synthesis.workspace_environment import WorkspaceTasksEnvironment
from synthesis.workspace_tasks import (
    generate_workspace_fixture_candidates,
    propose_workspace_comment_authorization,
    scripted_workspace_solution_policy,
    workspace_mutation_policies,
    workspace_semantic_mutation_judge,
)
from synthesis.workspace_tools import build_workspace_tool_registry
from tests.test_workspace_pipeline import workspace_seed


class MutationAdmissionCandidateProcessingTest(unittest.TestCase):
    def _candidate(self, candidate_id: str = "candidate_workspace_launch_comment") -> CandidateTask:
        return next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id == candidate_id
        )

    def _process(
        self,
        candidate: CandidateTask,
        *,
        mode: str = "shadow",
        judge: object | None = None,
    ):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = WorkspaceTasksEnvironment.create_fixture(
            Path(temporary_directory.name)
        )
        evaluator = build_local_candidate_admission_evaluator(
            mode=mode,
            policies=workspace_mutation_policies(),
            state_changing_tools=("create_workspace_task", "add_workspace_comment"),
            judge=judge or workspace_semantic_mutation_judge,
        )
        outcome = process_candidate_through_gates(
            raw_task=candidate,
            context=CandidateProcessingContext(
                dataset_version="dataset_workspace_mutation_admission_test",
                environment=environment,
                registry=build_workspace_tool_registry(environment),
                adapter_shim=None,
                verifier=ExactAnswerVerifier(),
                llm_config=LLMConfig(base_url=None),
                generate_policy=scripted_workspace_solution_policy,
                admission_evaluator=evaluator,
            ),
            options=CandidateProcessingOptions(),
        )
        return outcome, environment

    def test_supported_workspace_comment_executes_and_retains_sanitized_shadow_evidence(
        self,
    ) -> None:
        outcome, environment = self._process(self._candidate())

        self.assertIsNotNone(outcome.sample)
        assert outcome.sample is not None
        self.assertTrue(
            environment.has_workspace_comment(
                task_id="task_launch_plan",
                comment="Added launch checklist owner.",
            )
        )
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(evidence["schema_version"], "mutation_admission_evidence_v1")
        self.assertEqual(evidence["classification"], "state_changing")
        self.assertEqual(evidence["mode"], "shadow")
        self.assertEqual(evidence["deterministic_validation"]["status"], "passed")
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertIn(
            "argument_semantic_supported",
            evidence["semantic_verdict"]["reason_codes"],
        )
        self.assertEqual(
            evidence["contract_versions"],
            {
                "authorization": "mutation_authorization_record_v1",
                "domain_policy": "workspace_comment_mutation_policy_v1",
                "semantic_verdict": "semantic_mutation_verdict_v1",
            },
        )
        self.assertTrue(evidence["diagnostic_only"])
        self.assertEqual(
            evidence["lineage"]["generator"]["role"],
            "scripted_task_generation",
        )
        for value in evidence["hashes"].values():
            self.assertRegex(str(value), r"^sha256:[0-9a-f]{64}$")
        retained = repr(evidence).lower()
        self.assertNotIn("added launch checklist owner", retained)
        self.assertNotIn("find the launch plan", retained)

    def test_deterministic_failures_are_bounded_and_do_not_change_shadow_execution(
        self,
    ) -> None:
        base = self._candidate()
        assert base.mutation_authorization is not None

        def changed_record(change) -> CandidateTask:
            record = copy.deepcopy(base.mutation_authorization)
            change(record)
            return replace(base, mutation_authorization=record)

        def invalidate_span(record: dict[str, object]) -> None:
            record["actions"][0]["instruction_evidence"]["end"] = 10_000

        def remove_comment(record: dict[str, object]) -> None:
            arguments = record["actions"][0]["arguments"]
            record["actions"][0]["arguments"] = [
                argument for argument in arguments if argument["name"] != "comment"
            ]

        def invalidate_origin(record: dict[str, object]) -> None:
            record["actions"][0]["arguments"][0]["origin"] = "reasonable_guess"

        def falsify_task_binding(record: dict[str, object]) -> None:
            record["actions"][0]["arguments"][1]["evidence"]["value_hash"] = (
                "sha256:" + "0" * 64
            )

        def repoint_task_selection(record: dict[str, object]) -> None:
            action = record["actions"][0]
            action["arguments"][1]["evidence"]["binding_instruction_evidence"] = (
                copy.deepcopy(action["instruction_evidence"])
            )

        cases = (
            (
                "authorization_record_missing",
                replace(base, mutation_authorization=None),
            ),
            ("instruction_span_invalid", changed_record(invalidate_span)),
            (
                "requester_argument_provenance_missing",
                changed_record(remove_comment),
            ),
            ("provenance_origin_invalid", changed_record(invalidate_origin)),
            ("observation_reference_invalid", changed_record(falsify_task_binding)),
            ("observation_reference_invalid", changed_record(repoint_task_selection)),
        )
        for expected_code, candidate in cases:
            with self.subTest(expected_code=expected_code):
                outcome, environment = self._process(candidate)

                self.assertIsNotNone(outcome.sample)
                assert outcome.sample is not None
                self.assertTrue(
                    environment.has_workspace_comment(
                        task_id="task_launch_plan",
                        comment="Added launch checklist owner.",
                    )
                )
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
                    self.assertNotIn("Added launch", repr(finding))

    def test_local_judge_produces_each_strict_verdict_without_changing_acceptance(
        self,
    ) -> None:
        supported = self._candidate()
        unsupported = propose_workspace_comment_authorization(
            replace(
                supported,
                expected_state={
                    "workspace_comment": {
                        "task_id": "task_launch_plan",
                        "comment": "Schedule quarterly planning.",
                    }
                },
            )
        )
        uncertain = propose_workspace_comment_authorization(
            replace(
                supported,
                instruction=(
                    "If appropriate, find the launch plan task and add a comment "
                    "assigning the checklist owner."
                ),
            )
        )

        for expected_verdict, expected_reason, candidate in (
            ("supported", "argument_semantic_supported", supported),
            ("unsupported", "argument_not_supported", unsupported),
            ("uncertain", "conditional_authorization_ambiguous", uncertain),
        ):
            with self.subTest(expected_verdict=expected_verdict):
                outcome, _ = self._process(candidate)

                self.assertIsNotNone(outcome.sample)
                assert outcome.sample is not None
                verdict = outcome.sample["mutation_admission"]["semantic_verdict"]
                self.assertEqual(verdict["verdict"], expected_verdict)
                self.assertIn(expected_reason, verdict["reason_codes"])
                self.assertRegex(str(verdict["input_hash"]), r"^sha256:[0-9a-f]{64}$")
                self.assertNotIn("confidence", verdict)
                self.assertNotIn("rationale", verdict)

    def test_read_only_candidates_bypass_judgment_and_disabled_preserves_execution(
        self,
    ) -> None:
        class FailingJudge:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, request):
                self.calls += 1
                raise AssertionError("read-only candidate must not call the judge")

        judge = FailingJudge()
        read_only_outcome, _ = self._process(
            self._candidate("candidate_workspace_launch_lookup"),
            judge=judge,
        )
        disabled_outcome, environment = self._process(
            self._candidate(),
            mode="disabled",
        )

        self.assertEqual(judge.calls, 0)
        assert read_only_outcome.sample is not None
        read_only_evidence = read_only_outcome.sample["mutation_admission"]
        self.assertEqual(read_only_evidence["classification"], "read_only")
        self.assertEqual(
            read_only_evidence["deterministic_validation"]["status"],
            "bypassed",
        )
        self.assertNotIn("semantic_verdict", read_only_evidence)
        assert disabled_outcome.sample is not None
        disabled_evidence = disabled_outcome.sample["mutation_admission"]
        self.assertEqual(disabled_evidence["mode"], "disabled")
        self.assertEqual(
            disabled_evidence["deterministic_validation"]["status"],
            "not_evaluated",
        )
        self.assertNotIn("semantic_verdict", disabled_evidence)
        self.assertTrue(
            environment.has_workspace_comment(
                task_id="task_launch_plan",
                comment="Added launch checklist owner.",
            )
        )

    def test_other_rejection_causes_retain_shadow_evidence_without_being_replaced(
        self,
    ) -> None:
        candidate = propose_workspace_comment_authorization(
            replace(self._candidate(), expected_answer="missing_expected_answer")
        )

        outcome, environment = self._process(candidate)

        self.assertIsNone(outcome.sample)
        self.assertIsNotNone(outcome.rejection)
        assert outcome.rejection is not None
        self.assertEqual(outcome.rejection["cause"], "verification_failed")
        evidence = outcome.rejection["details"]["mutation_admission"]
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertTrue(
            environment.has_workspace_comment(
                task_id="task_launch_plan",
                comment="Added launch checklist owner.",
            )
        )

    def test_false_observation_binding_is_reported_without_replacing_runtime_failure(
        self,
    ) -> None:
        candidate = propose_workspace_comment_authorization(
            replace(
                self._candidate(),
                expected_state={
                    "workspace_comment": {
                        "task_id": "task_invented_reference",
                        "comment": "Added launch checklist owner.",
                    }
                },
            )
        )

        shadow_outcome, _ = self._process(candidate, mode="shadow")
        disabled_outcome, _ = self._process(candidate, mode="disabled")

        assert shadow_outcome.rejection is not None
        assert disabled_outcome.rejection is not None
        self.assertEqual(shadow_outcome.rejection["cause"], "tool_runtime_error")
        self.assertEqual(
            shadow_outcome.rejection["cause"],
            disabled_outcome.rejection["cause"],
        )
        evidence = shadow_outcome.rejection["details"]["mutation_admission"]
        self.assertIn(
            "observation_reference_invalid",
            evidence["deterministic_validation"]["reason_codes"],
        )
        self.assertNotIn("semantic_verdict", evidence)

    def test_retained_admission_contract_rejects_unknown_verdicts_reasons_and_hashes(
        self,
    ) -> None:
        from synthesis.contracts import ContractValidationError, validate_sample_record

        outcome, _ = self._process(self._candidate())
        assert outcome.sample is not None

        def unknown_verdict(sample: dict[str, object]) -> None:
            sample["mutation_admission"]["semantic_verdict"]["verdict"] = "approved"

        def unknown_reason(sample: dict[str, object]) -> None:
            sample["mutation_admission"]["semantic_verdict"]["reason_codes"] = [
                "free_form_reason"
            ]

        def invalid_hash(sample: dict[str, object]) -> None:
            sample["mutation_admission"]["hashes"]["verdict"] = "sha256:not-a-hash"

        for tamper in (unknown_verdict, unknown_reason, invalid_hash):
            with self.subTest(tamper=tamper.__name__):
                sample = copy.deepcopy(outcome.sample)
                tamper(sample)
                with self.assertRaises(ContractValidationError):
                    validate_sample_record(sample)

    def test_duplicate_rejection_retains_evaluated_shadow_evidence(self) -> None:
        from synthesis.candidate_processing import merge_candidate_outcomes

        first, _ = self._process(self._candidate())
        duplicate, _ = self._process(self._candidate())

        result = merge_candidate_outcomes(
            (
                replace(first, sequence_index=0),
                replace(duplicate, sequence_index=1),
            )
        )

        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.rejections), 1)
        self.assertEqual(result.rejections[0]["cause"], "quality_duplicate")
        retained = result.rejections[0]["details"]["mutation_admission"]
        self.assertEqual(retained["semantic_verdict"]["verdict"], "supported")


if __name__ == "__main__":
    unittest.main()
