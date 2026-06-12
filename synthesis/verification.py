from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synthesis.execution import ExecutionResult
from synthesis.tasks import CandidateTask


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
        checks: list[dict[str, object]] = []
        answer_passed = task.expected_answer in execution.final_response
        checks.append({
            "name": "final_response_contains_expected_answer",
            "passed": answer_passed,
            "expected": task.expected_answer,
            "actual": execution.final_response,
        })
        checks.extend(_state_checks(task, environment))
        return VerificationResult(
            verifier_id=self.verifier_id,
            version=self.version,
            passed=all(bool(check.get("passed")) for check in checks),
            checks=checks,
        )


def _state_checks(
    task: CandidateTask,
    environment: Any | None,
) -> list[dict[str, object]]:
    if not task.expected_state:
        return []
    expected_followup = task.expected_state.get("contact_followup")
    if isinstance(expected_followup, dict):
        return [_contact_followup_check(expected_followup, environment)]

    expected_reminder = task.expected_state.get("mobile_reminder")
    if isinstance(expected_reminder, dict):
        return [_mobile_reminder_check(expected_reminder, environment)]

    expected_draft = task.expected_state.get("mobile_draft_reply")
    if isinstance(expected_draft, dict):
        return [_mobile_draft_reply_check(expected_draft, environment)]

    return []


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
