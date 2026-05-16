from __future__ import annotations

from dataclasses import dataclass

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
    version = "verifier_exact_answer_v1"

    def verify(self, task: CandidateTask, execution: ExecutionResult) -> VerificationResult:
        passed = task.expected_answer in execution.final_response
        check = {
            "name": "final_response_contains_expected_answer",
            "passed": passed,
            "expected": task.expected_answer,
            "actual": execution.final_response,
        }
        return VerificationResult(
            verifier_id=self.verifier_id,
            version=self.version,
            passed=passed,
            checks=[check],
        )
