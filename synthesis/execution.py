from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any

from synthesis.llm import LLMProviderError
from synthesis.roles import RoleRegistry, SOLUTION_POLICY_ROLE, default_role_registry
from synthesis.tasks import CandidateTask
from synthesis.tools import ToolRegistry


@dataclass(frozen=True)
class ToolStep:
    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class SolutionPolicy:
    policy_id: str
    role: str
    steps: tuple[ToolStep, ...]
    final_response_template: str
    lineage: dict[str, object] | None = None


@dataclass(frozen=True)
class ExecutionResult:
    trajectory: list[dict[str, object]]
    final_response: str
    policy: SolutionPolicy | None = None


class PolicyValidationError(ValueError):
    pass


def execute_candidate(
    task: CandidateTask,
    registry: ToolRegistry,
    *,
    policy: SolutionPolicy | None = None,
) -> ExecutionResult:
    selected_policy = policy or scripted_solution_policy(task)
    validate_solution_policy(selected_policy)

    trajectory: list[dict[str, object]] = []
    response_context: dict[str, object] = {}
    for step in selected_policy.steps:
        trajectory.append(
            {
                "type": "action",
                "tool": step.tool_name,
                "arguments": step.arguments,
            }
        )
        observation = registry.execute(step.tool_name, step.arguments)
        trajectory.append(
            {
                "type": "observation",
                "tool": step.tool_name,
                "observation": observation,
            }
        )
        response_context.update(_scalar_observation_values(observation))
        state_change = observation.get("state_change")
        if isinstance(state_change, dict):
            trajectory.append(
                {
                    "type": "state_change",
                    "tool": step.tool_name,
                    "change": state_change,
                }
            )

    final_response = _render_final_response(selected_policy, response_context)
    trajectory.append(
        {
            "type": "final_response",
            "content": final_response,
        }
    )
    return ExecutionResult(
        trajectory=trajectory,
        final_response=final_response,
        policy=selected_policy,
    )


def scripted_solution_policy(task: CandidateTask) -> SolutionPolicy:
    if task.constraints.get("task_type") == "contact_followup":
        name = str(task.arguments.get("name", ""))
        note = f"Send follow-up email to {task.expected_answer}."
        return SolutionPolicy(
            policy_id=f"policy_{task.candidate_id}",
            role="scripted_solution_policy",
            steps=(
                ToolStep(tool_name="lookup_contact_email", arguments={"name": name}),
                ToolStep(
                    tool_name="record_contact_followup",
                    arguments={"name": name, "note": note},
                ),
            ),
            final_response_template="{name}'s email is {email}. Follow-up recorded.",
            lineage=_local_policy_lineage(),
        )

    return SolutionPolicy(
        policy_id=f"policy_{task.candidate_id}",
        role="scripted_solution_policy",
        steps=(ToolStep(tool_name=task.tool_name, arguments=task.arguments),),
        final_response_template="{name}'s email is {email}.",
        lineage=_local_policy_lineage(),
    )


def generate_llm_backed_solution_policy(
    task: CandidateTask,
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> SolutionPolicy:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        SOLUTION_POLICY_ROLE,
        client,
        _solution_policy_prompt(task),
    )
    raw_policy = result.content.get("policy")
    if not isinstance(raw_policy, dict):
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class="TypeError",
            retryable=False,
            retry_count=_lineage_retry_count(result.lineage),
            lineage=result.lineage,
        )
    try:
        raw_steps = raw_policy["steps"]
        if not isinstance(raw_steps, list):
            raise TypeError("policy steps must be a list")
        steps = tuple(_tool_step_from_mapping(raw_step) for raw_step in raw_steps)
        policy = SolutionPolicy(
            policy_id=str(raw_policy["policy_id"]),
            role="solution_policy",
            steps=steps,
            final_response_template=str(raw_policy["final_response_template"]),
            lineage=dict(result.lineage),
        )
        validate_solution_policy(policy)
        return policy
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class=type(exc).__name__,
            retryable=False,
            retry_count=_lineage_retry_count(result.lineage),
            lineage=result.lineage,
        ) from exc


def validate_solution_policy(policy: SolutionPolicy) -> None:
    if not isinstance(policy, SolutionPolicy):
        raise PolicyValidationError("policy must be a SolutionPolicy")
    if not policy.policy_id.strip():
        raise PolicyValidationError("policy_id must be a non-empty string")
    if not policy.role.strip():
        raise PolicyValidationError("role must be a non-empty string")
    if not policy.steps:
        raise PolicyValidationError("steps must contain at least one step")
    for index, step in enumerate(policy.steps):
        if not isinstance(step, ToolStep):
            raise PolicyValidationError(f"steps.{index} must be a ToolStep")
        if not step.tool_name.strip():
            raise PolicyValidationError(f"steps.{index}.tool_name must be a non-empty string")
        if not isinstance(step.arguments, dict):
            raise PolicyValidationError(f"steps.{index}.arguments must be an object")
    if not policy.final_response_template.strip():
        raise PolicyValidationError("final_response_template must be a non-empty string")


def _tool_step_from_mapping(raw: object) -> ToolStep:
    if not isinstance(raw, dict):
        raise TypeError("policy step must be an object")
    arguments = raw.get("arguments")
    if not isinstance(arguments, dict):
        raise TypeError("policy step arguments must be an object")
    return ToolStep(tool_name=str(raw["tool_name"]), arguments=arguments)


def _solution_policy_prompt(task: CandidateTask) -> str:
    return (
        "Generate an executable solution policy for one Agent data synthesis task.\n"
        f"Candidate id: {task.candidate_id}\n"
        f"Instruction: {task.instruction}\n"
        f"Constraints: {task.constraints}\n"
        "Available tools: lookup_contact_email(name), "
        "record_contact_followup(name, note).\n"
        "Return JSON with a policy object containing policy_id, steps, and "
        "final_response_template. Each step must include tool_name and arguments."
    )


def _render_final_response(policy: SolutionPolicy, context: dict[str, object]) -> str:
    required_fields = [
        field_name
        for _, field_name, _, _ in Formatter().parse(policy.final_response_template)
        if field_name
    ]
    missing_fields = [field_name for field_name in required_fields if field_name not in context]
    if missing_fields:
        names = ", ".join(sorted(missing_fields))
        raise PolicyValidationError(f"final_response_template missing context fields: {names}")
    return policy.final_response_template.format_map(context)


def _scalar_observation_values(observation: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in observation.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }


def _local_policy_lineage() -> dict[str, object]:
    return {
        "role": "scripted_solution_policy",
        "role_version": "role_scripted_solution_policy_v1",
        "output_type": "solution_policy",
        "owner_module": "synthesis.execution",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted",
        "config_hash": "scripted_solution_policy_v1",
        "configured": True,
    }


def _lineage_retry_count(lineage: dict[str, object]) -> int:
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        return retry_count
    return 0
