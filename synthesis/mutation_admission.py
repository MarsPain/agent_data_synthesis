from __future__ import annotations

from typing import Protocol

from synthesis.execution import SolutionPolicy
from synthesis.task_contracts import TaskContract


class CandidateAdmissionEvaluator(Protocol):
    def __call__(
        self,
        task_contract: TaskContract,
        solution_policy: SolutionPolicy,
    ) -> None: ...


def permit_candidate_execution(
    task_contract: TaskContract,
    solution_policy: SolutionPolicy,
) -> None:
    """Preserve execution while admission policy is not configured."""
    _ = task_contract, solution_policy
