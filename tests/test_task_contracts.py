from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from synthesis.contracts import ContractValidationError
from synthesis.execution import ExecutionResult, scripted_solution_policy
from synthesis.mobile_environment import MobileMessagesEnvironment
from synthesis.mobile_tasks import (
    generate_mobile_fixture_candidates,
    scripted_mobile_solution_policy,
)
from synthesis.seeds import DomainSeed, foundation_seed
from synthesis.tasks import generate_foundation_candidates


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


def foundation_candidate(candidate_id: str):
    return next(
        candidate
        for candidate in generate_foundation_candidates(foundation_seed(), include_branching=True)
        if candidate.candidate_id == candidate_id
    )


def mobile_candidate(candidate_id: str):
    return next(
        candidate
        for candidate in generate_mobile_fixture_candidates(mobile_seed())
        if candidate.candidate_id == candidate_id
    )


class TaskContractConversionTest(unittest.TestCase):
    def test_contacts_candidate_converts_to_task_contract(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate

        contract = task_contract_from_candidate(foundation_candidate("candidate_contacts_alice"))

        self.assertEqual(contract.intent.domain_id, "contacts_fixture")
        self.assertEqual(contract.intent.task_type, "contact_lookup")
        self.assertEqual(contract.policy_hint.primary_tool, "lookup_contact_email")
        self.assertEqual(contract.policy_hint.primary_arguments, {"name": "Alice Zhang"})
        self.assertEqual(
            contract.expected_outcome.final_answer_contains,
            "alice.zhang@example.test",
        )
        self.assertEqual(contract.expected_state, ())

    def test_contacts_followup_preserves_state_check(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate

        contract = task_contract_from_candidate(
            foundation_candidate("candidate_contacts_alice_followup")
        )

        self.assertEqual(len(contract.expected_state), 1)
        state_check = contract.expected_state[0]
        self.assertEqual(state_check.check_type, "contact_followup")
        self.assertEqual(
            state_check.expected,
            {
                "name": "Alice Zhang",
                "note": "Send follow-up email to alice.zhang@example.test.",
            },
        )

    def test_mobile_candidates_convert_to_domain_specific_contracts(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate

        reminder = task_contract_from_candidate(
            mobile_candidate("candidate_mobile_maya_reminder")
        )
        draft = task_contract_from_candidate(
            mobile_candidate("candidate_mobile_alex_draft_reply")
        )

        self.assertEqual(reminder.intent.domain_id, "mobile_messages_fixture")
        self.assertEqual(draft.intent.domain_id, "mobile_messages_fixture")
        self.assertEqual(reminder.expected_state[0].check_type, "mobile_reminder")
        self.assertEqual(draft.expected_state[0].check_type, "mobile_draft_reply")
        self.assertEqual(
            reminder.policy_hint.required_tools,
            ("search_phone_messages", "create_phone_reminder"),
        )
        self.assertEqual(
            draft.policy_hint.required_tools,
            ("search_phone_messages", "draft_message_reply"),
        )

    def test_branch_plan_policy_hint_validates_existing_branch_contract(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate, validate_task_contract

        contract = task_contract_from_candidate(
            mobile_candidate("candidate_mobile_delivery_branch_fallback")
        )
        validate_task_contract(contract)

        bad_branch_plan = dict(contract.policy_hint.branch_plan or {})
        bad_branch_plan["schema_version"] = "branch_plan_v999"
        invalid_contract = replace(
            contract,
            policy_hint=replace(contract.policy_hint, branch_plan=bad_branch_plan),
        )

        with self.assertRaises(ContractValidationError):
            validate_task_contract(invalid_contract)

    def test_task_contract_rejects_unsafe_values(self) -> None:
        from synthesis.task_contracts import (
            ExpectedOutcome,
            PolicyHint,
            TaskContract,
            TaskIntent,
            validate_task_contract,
        )

        contract = TaskContract(
            intent=TaskIntent(
                candidate_id="candidate_unsafe",
                instruction="Find Alice Zhang's email.",
                domain_id="contacts_fixture",
                task_type="contact_lookup",
                difficulty={"level": "easy"},
            ),
            policy_hint=PolicyHint(
                required_tools=("lookup_contact_email",),
                primary_tool="lookup_contact_email",
                primary_arguments={"api_key": "secret-test-key"},
            ),
            expected_outcome=ExpectedOutcome(
                final_answer_contains="alice.zhang@example.test"
            ),
        )

        with self.assertRaises(ContractValidationError):
            validate_task_contract(contract)

    def test_candidate_task_contract_method_matches_converter(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate

        candidate = foundation_candidate("candidate_contacts_alice")

        self.assertEqual(candidate.contract(), task_contract_from_candidate(candidate))


class TaskContractPolicyTest(unittest.TestCase):
    def test_contacts_policy_from_contract_matches_existing_lookup_policy(self) -> None:
        from synthesis.execution import scripted_solution_policy_from_contract

        candidate = foundation_candidate("candidate_contacts_alice")

        self.assertEqual(
            scripted_solution_policy_from_contract(candidate.contract()),
            scripted_solution_policy(candidate),
        )

    def test_contacts_followup_policy_from_contract_keeps_state_change_step(self) -> None:
        from synthesis.execution import scripted_solution_policy_from_contract

        candidate = foundation_candidate("candidate_contacts_alice_followup")
        policy = scripted_solution_policy_from_contract(candidate.contract())

        self.assertEqual(
            [step.tool_name for step in policy.steps],
            ["lookup_contact_email", "record_contact_followup"],
        )
        self.assertEqual(
            policy.steps[1].arguments,
            {
                "name": "Alice Zhang",
                "note": "Send follow-up email to alice.zhang@example.test.",
            },
        )

    def test_mobile_reminder_policy_from_contract_keeps_two_steps(self) -> None:
        from synthesis.mobile_tasks import scripted_mobile_solution_policy_from_contract

        candidate = mobile_candidate("candidate_mobile_maya_reminder")
        policy = scripted_mobile_solution_policy_from_contract(candidate.contract())

        self.assertEqual(
            [step.tool_name for step in policy.steps],
            ["search_phone_messages", "create_phone_reminder"],
        )
        self.assertEqual(
            policy.steps[1].arguments,
            {
                "title": "Send the project update",
                "due_at": "tomorrow 9 AM",
                "source_message_id": "msg_maya_project_update",
            },
        )

    def test_mobile_draft_policy_from_contract_keeps_draft_step(self) -> None:
        from synthesis.mobile_tasks import scripted_mobile_solution_policy_from_contract

        candidate = mobile_candidate("candidate_mobile_alex_draft_reply")
        policy = scripted_mobile_solution_policy_from_contract(candidate.contract())

        self.assertEqual(
            [step.tool_name for step in policy.steps],
            ["search_phone_messages", "draft_message_reply"],
        )
        self.assertEqual(
            policy.steps[1].arguments,
            {"thread_id": "thread_alex", "body": "I will be five minutes late."},
        )

    def test_mobile_branch_policy_from_contract_keeps_branch_plan(self) -> None:
        from synthesis.mobile_tasks import scripted_mobile_solution_policy_from_contract

        candidate = mobile_candidate("candidate_mobile_delivery_branch_fallback")

        self.assertEqual(
            scripted_mobile_solution_policy_from_contract(candidate.contract()),
            scripted_mobile_solution_policy(candidate),
        )


class TaskContractVerifierTest(unittest.TestCase):
    def test_verifier_uses_expected_outcome_from_contract(self) -> None:
        from synthesis.task_contracts import task_contract_from_candidate
        from synthesis.verification import verify_contract

        contract = task_contract_from_candidate(foundation_candidate("candidate_contacts_alice"))
        execution = ExecutionResult(
            trajectory=[],
            final_response="Alice Zhang can be reached at alice.zhang@example.test.",
        )

        verification = verify_contract(contract, execution)

        self.assertTrue(verification.passed)
        self.assertEqual(
            verification.checks[0]["name"],
            "final_response_contains_expected_answer",
        )

    def test_verifier_uses_mobile_state_check_from_contract(self) -> None:
        from synthesis.verification import verify_contract

        candidate = mobile_candidate("candidate_mobile_maya_reminder")
        execution = ExecutionResult(
            trajectory=[],
            final_response="Reminder created from msg_maya_project_update.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))
            failed = verify_contract(candidate.contract(), execution, environment=environment)
            environment.create_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )
            passed = verify_contract(candidate.contract(), execution, environment=environment)

        self.assertFalse(failed.passed)
        self.assertEqual(
            failed.checks[-1]["name"],
            "mobile_reminder_state_matches_expected",
        )
        self.assertTrue(passed.passed)

    def test_verifier_rejects_unsupported_state_check(self) -> None:
        from synthesis.task_contracts import ExpectedStateCheck
        from synthesis.verification import verify_contract

        contract = replace(
            mobile_candidate("candidate_mobile_maya_reminder").contract(),
            expected_state=(
                ExpectedStateCheck(check_type="unsupported_check", expected={}),
            ),
        )
        execution = ExecutionResult(
            trajectory=[],
            final_response="Reminder created from msg_maya_project_update.",
        )

        with self.assertRaises(ContractValidationError):
            verify_contract(contract, execution)


if __name__ == "__main__":
    unittest.main()
