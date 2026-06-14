from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synthesis.execution import ExecutionResult
from synthesis.tasks import CandidateTask
from synthesis.task_contracts import TaskContract, validate_task_contract


@dataclass(frozen=True)
class VerificationResult:
    verifier_id: str
    version: str
    passed: bool
    checks: list[dict[str, object]]

    def export(self) -> dict[str, object]:
        return {
            "verifier_id": self.verifier_id,
            "version": self.version,
            "passed": self.passed,
            "checks": self.checks,
        }


class ExactAnswerVerifier:
    verifier_id = "exact_answer_verifier"
    version = "verifier_exact_answer_state_v2"

    def verify(
        self,
        task: CandidateTask,
        execution: ExecutionResult,
        *,
        environment: Any | None = None,
    ) -> VerificationResult:
        return verify_contract(task.contract(), execution, environment=environment)


def verify_contract(
    contract: TaskContract,
    execution: ExecutionResult,
    *,
    environment: Any | None = None,
) -> VerificationResult:
    contract = validate_task_contract(contract)
    checks: list[dict[str, object]] = []
    expected_answer = contract.expected_outcome.final_answer_contains
    answer_passed = expected_answer in execution.final_response
    checks.append({
        "name": "final_response_contains_expected_answer",
        "passed": answer_passed,
        "expected": expected_answer,
        "actual": execution.final_response,
    })
    checks.extend(_state_checks(contract, environment))
    return VerificationResult(
        verifier_id=ExactAnswerVerifier.verifier_id,
        version=ExactAnswerVerifier.version,
        passed=all(bool(check.get("passed")) for check in checks),
        checks=checks,
    )


def _state_checks(
    contract: TaskContract,
    environment: Any | None,
) -> list[dict[str, object]]:
    if not contract.expected_state:
        return []
    checks: list[dict[str, object]] = []
    for state_check in contract.expected_state:
        expected = dict(state_check.expected)
        if state_check.check_type == "contact_followup":
            checks.append(_contact_followup_check(expected, environment))
        elif state_check.check_type == "mobile_reminder":
            checks.append(_mobile_reminder_check(expected, environment))
        elif state_check.check_type == "mobile_draft_reply":
            checks.append(_mobile_draft_reply_check(expected, environment))
    return checks


def _contact_followup_check(
    expected_followup: dict[str, object],
    environment: Any | None,
) -> dict[str, object]:
    name = expected_followup.get("name")
    note = expected_followup.get("note")
    if not isinstance(name, str) or not isinstance(note, str):
        return {
            "name": "contact_followup_state_matches_expected",
            "passed": False,
            "expected": expected_followup,
            "actual": None,
            "cause": "solution_logic_error",
        }
    actual = (
        environment.has_followup(name, note)
        if environment is not None and hasattr(environment, "has_followup")
        else False
    )
    return {
        "name": "contact_followup_state_matches_expected",
        "passed": actual,
        "expected": {"name": name, "note": note},
        "actual": {"exists": actual},
        "cause": "solution_logic_error",
    }


def _mobile_reminder_check(
    expected_reminder: dict[str, object],
    environment: Any | None,
) -> dict[str, object]:
    title = expected_reminder.get("title")
    due_at = expected_reminder.get("due_at")
    source_message_id = expected_reminder.get("source_message_id")
    if not isinstance(title, str):
        return {
            "name": "mobile_reminder_state_matches_expected",
            "passed": False,
            "expected": expected_reminder,
            "actual": None,
            "cause": "solution_logic_error",
        }
    if due_at is not None and not isinstance(due_at, str):
        return {
            "name": "mobile_reminder_state_matches_expected",
            "passed": False,
            "expected": expected_reminder,
            "actual": None,
            "cause": "solution_logic_error",
        }
    if source_message_id is not None and not isinstance(source_message_id, str):
        return {
            "name": "mobile_reminder_state_matches_expected",
            "passed": False,
            "expected": expected_reminder,
            "actual": None,
            "cause": "solution_logic_error",
        }
    actual = (
        environment.has_reminder(
            title=title,
            due_at=due_at,
            source_message_id=source_message_id,
        )
        if environment is not None and hasattr(environment, "has_reminder")
        else False
    )
    return {
        "name": "mobile_reminder_state_matches_expected",
        "passed": actual,
        "expected": {
            "title": title,
            "due_at": due_at,
            "source_message_id": source_message_id,
        },
        "actual": {"exists": actual},
        "cause": "solution_logic_error",
    }


def _mobile_draft_reply_check(
    expected_draft: dict[str, object],
    environment: Any | None,
) -> dict[str, object]:
    thread_id = expected_draft.get("thread_id")
    body = expected_draft.get("body")
    if not isinstance(thread_id, str) or not isinstance(body, str):
        return {
            "name": "mobile_draft_reply_state_matches_expected",
            "passed": False,
            "expected": expected_draft,
            "actual": None,
            "cause": "solution_logic_error",
        }
    actual = (
        environment.has_draft_reply(thread_id=thread_id, body=body)
        if environment is not None and hasattr(environment, "has_draft_reply")
        else False
    )
    return {
        "name": "mobile_draft_reply_state_matches_expected",
        "passed": actual,
        "expected": {"thread_id": thread_id, "body": body},
        "actual": {"exists": actual},
        "cause": "solution_logic_error",
    }
