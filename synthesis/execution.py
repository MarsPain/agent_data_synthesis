from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any

from synthesis.contracts import validate_branch_plan_record, validate_branch_outcomes
from synthesis.llm import LLMProviderError
from synthesis.roles import RoleRegistry, SOLUTION_POLICY_ROLE, default_role_registry
from synthesis.tasks import CandidateTask
from synthesis.tools import ToolRegistry, ToolRegistryError


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
    branch_plan: dict[str, object] | None = None


@dataclass(frozen=True)
class ExecutionResult:
    trajectory: list[dict[str, object]]
    final_response: str
    policy: SolutionPolicy | None = None
    branch_plan: dict[str, object] | None = None
    branch_outcomes: list[dict[str, object]] | None = None


class PolicyValidationError(ValueError):
    pass


class BranchExecutionError(RuntimeError):
    def __init__(self, message: str, *, branch_outcomes: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.branch_outcomes = branch_outcomes


class StepExecutionError(RuntimeError):
    def __init__(
        self,
        cause: Exception,
        *,
        trajectory: list[dict[str, object]],
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.trajectory = trajectory


def execute_candidate(
    task: CandidateTask,
    registry: ToolRegistry,
    *,
    policy: SolutionPolicy | None = None,
) -> ExecutionResult:
    selected_policy = policy or scripted_solution_policy(task)
    validate_solution_policy(selected_policy)
    if selected_policy.branch_plan is not None:
        return _execute_branching_policy(selected_policy, registry)

    trajectory, final_response = _execute_steps(
        selected_policy.steps,
        selected_policy.final_response_template,
        registry,
    )
    return ExecutionResult(
        trajectory=trajectory,
        final_response=final_response,
        policy=selected_policy,
    )


def scripted_solution_policy(task: CandidateTask) -> SolutionPolicy:
    if task.branch_plan is not None:
        return SolutionPolicy(
            policy_id=f"policy_{task.candidate_id}",
            role="scripted_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            lineage=_local_policy_lineage(),
            branch_plan=task.branch_plan,
        )

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
    if policy.branch_plan is not None:
        validate_branch_plan_record(policy.branch_plan)
    if not policy.steps and policy.branch_plan is None:
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


def _execute_branching_policy(
    policy: SolutionPolicy,
    registry: ToolRegistry,
) -> ExecutionResult:
    assert policy.branch_plan is not None
    validate_branch_plan_record(policy.branch_plan)
    baseline = registry.checkpoint_state()
    outcomes: list[dict[str, object]] = []
    branches = policy.branch_plan["branches"]
    assert isinstance(branches, list)

    for depth, raw_branch in enumerate(branches, start=1):
        assert isinstance(raw_branch, dict)
        registry.restore_state(baseline)
        branch_id = str(raw_branch["branch_id"])
        steps = tuple(_tool_step_from_mapping(step) for step in raw_branch["steps"])
        template = str(raw_branch["final_response_template"])
        try:
            trajectory, final_response = _execute_steps(
                steps,
                template,
                registry,
                capture_failures=True,
            )
        except StepExecutionError as exc:
            outcomes.append(
                _branch_outcome(
                    branch_id=branch_id,
                    selected=False,
                    outcome="rejected",
                    failure_cause=_branch_failure_cause(exc.cause),
                    message=str(exc.cause),
                    depth=depth,
                    trajectory=exc.trajectory,
                )
            )
            continue
        except Exception as exc:
            outcomes.append(
                _branch_outcome(
                    branch_id=branch_id,
                    selected=False,
                    outcome="rejected",
                    failure_cause=_branch_failure_cause(exc),
                    message=str(exc),
                    depth=depth,
                    trajectory=[],
                )
            )
            continue

        outcomes.append(
            _branch_outcome(
                branch_id=branch_id,
                selected=True,
                outcome="accepted",
                failure_cause=None,
                message="accepted",
                depth=depth,
                trajectory=trajectory,
            )
        )
        validate_branch_outcomes(outcomes)
        return ExecutionResult(
            trajectory=trajectory,
            final_response=final_response,
            policy=policy,
            branch_plan=dict(policy.branch_plan),
            branch_outcomes=outcomes,
        )

    registry.restore_state(baseline)
    validate_branch_outcomes(outcomes, require_selected_terminal=False)
    raise BranchExecutionError(
        "branch_plan produced no selected terminal branch",
        branch_outcomes=outcomes,
    )


def _execute_steps(
    steps: tuple[ToolStep, ...],
    final_response_template: str,
    registry: ToolRegistry,
    *,
    capture_failures: bool = False,
) -> tuple[list[dict[str, object]], str]:
    trajectory: list[dict[str, object]] = []
    response_context: dict[str, object] = {}
    for step in steps:
        trajectory.append(
            {
                "type": "action",
                "tool": step.tool_name,
                "arguments": step.arguments,
            }
        )
        try:
            observation = registry.execute(step.tool_name, step.arguments)
        except Exception as exc:
            if capture_failures:
                raise StepExecutionError(exc, trajectory=trajectory) from exc
            raise
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

    branch_policy = SolutionPolicy(
        policy_id="render_only",
        role="scripted_solution_policy",
        steps=steps,
        final_response_template=final_response_template,
    )
    try:
        final_response = _render_final_response(branch_policy, response_context)
    except Exception as exc:
        if capture_failures:
            raise StepExecutionError(exc, trajectory=trajectory) from exc
        raise
    trajectory.append(
        {
            "type": "final_response",
            "content": final_response,
        }
    )
    return trajectory, final_response


def _branch_outcome(
    *,
    branch_id: str,
    selected: bool,
    outcome: str,
    failure_cause: str | None,
    message: str,
    depth: int,
    trajectory: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "branch_outcome_v1",
        "branch_id": branch_id,
        "attempted": True,
        "selected": selected,
        "outcome": outcome,
        "failure_cause": failure_cause,
        "retry_eligible": _branch_retry_eligible(failure_cause),
        "refinement_eligible": _branch_refinement_eligible(failure_cause),
        "message": message,
        "depth": depth,
        "trajectory": trajectory,
    }


def _branch_failure_cause(exc: Exception) -> str:
    if isinstance(exc, (KeyError, ToolRegistryError)):
        return "tool_runtime_error"
    if isinstance(exc, PolicyValidationError):
        return "solution_logic_error"
    return "infrastructure_error"


def _branch_retry_eligible(failure_cause: str | None) -> bool:
    return failure_cause in {"tool_runtime_error", "infrastructure_error", "llm_provider_error"}


def _branch_refinement_eligible(failure_cause: str | None) -> bool:
    return failure_cause in {"verification_failed", "solution_logic_error"}


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
