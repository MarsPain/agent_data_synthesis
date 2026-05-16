from __future__ import annotations

from dataclasses import dataclass

from synthesis.tasks import CandidateTask
from synthesis.tools import ToolRegistry


@dataclass(frozen=True)
class ExecutionResult:
    trajectory: list[dict[str, object]]
    final_response: str


def execute_candidate(task: CandidateTask, registry: ToolRegistry) -> ExecutionResult:
    trajectory: list[dict[str, object]] = [
        {
            "type": "action",
            "tool": task.tool_name,
            "arguments": task.arguments,
        }
    ]
    observation = registry.execute(task.tool_name, task.arguments)
    trajectory.append(
        {
            "type": "observation",
            "tool": task.tool_name,
            "observation": observation,
        }
    )
    final_response = f"{observation['name']}'s email is {observation['email']}."
    trajectory.append(
        {
            "type": "final_response",
            "content": final_response,
        }
    )
    return ExecutionResult(trajectory=trajectory, final_response=final_response)
