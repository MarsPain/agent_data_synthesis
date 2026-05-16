from __future__ import annotations

from dataclasses import dataclass

from synthesis.environments import ContactEnvironment
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
        environment: ContactEnvironment | None = None,
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
    environment: ContactEnvironment | None,
) -> list[dict[str, object]]:
    if not task.expected_state:
        return []
    expected_followup = task.expected_state.get("contact_followup")
    if not isinstance(expected_followup, dict):
        return []

    name = expected_followup.get("name")
    note = expected_followup.get("note")
    if not isinstance(name, str) or not isinstance(note, str):
        return [
            {
                "name": "contact_followup_state_matches_expected",
                "passed": False,
                "expected": expected_followup,
                "actual": None,
                "cause": "solution_logic_error",
            }
        ]
    actual = environment.has_followup(name, note) if environment else False
    return [
        {
            "name": "contact_followup_state_matches_expected",
            "passed": actual,
            "expected": {"name": name, "note": note},
            "actual": {"exists": actual},
            "cause": "solution_logic_error",
        }
    ]
