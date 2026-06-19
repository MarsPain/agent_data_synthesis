from __future__ import annotations

from collections.abc import Mapping, Sequence
from string import Formatter

from synthesis.domain_pipeline import DomainPipelineBundle
from synthesis.episodes import build_episode_log
from synthesis.execution import (
    PolicyValidationError,
    SolutionPolicy,
    ToolStep,
    validate_solution_policy,
)
from synthesis.runtime import RuntimeActionRequest, RuntimeSession
from synthesis.tasks import CandidateTask


def collect_diagnostic_rollout_episodes(
    *,
    bundle: DomainPipelineBundle,
    tasks: Sequence[CandidateTask],
    max_steps: int,
) -> list[dict[str, object]]:
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    session = bundle.runtime_session()
    baseline = session.checkpoint()
    episodes: list[dict[str, object]] = []
    for task in tasks:
        session.restore_checkpoint(baseline)
        policy = bundle.policy_generator(task)
        episode = _collect_task_episode(
            task=task,
            policy=policy,
            bundle=bundle,
            session=session,
            max_steps=max_steps,
        )
        episodes.append(episode)
        session.restore_checkpoint(baseline)
    return episodes


def _collect_task_episode(
    *,
    task: CandidateTask,
    policy: SolutionPolicy,
    bundle: DomainPipelineBundle,
    session: RuntimeSession,
    max_steps: int,
) -> dict[str, object]:
    try:
        validate_solution_policy(policy)
    except PolicyValidationError as exc:
        return _failed_episode(
            task=task,
            policy=policy,
            bundle=bundle,
            trajectory=[{"type": "error", "message": str(exc)}],
            failure_cause="policy_validation_failed",
        )
    if policy.branch_plan is not None:
        return _failed_episode(
            task=task,
            policy=policy,
            bundle=bundle,
            trajectory=[{"type": "error", "message": "branch policies are not rollout-supported"}],
            failure_cause="unsupported_policy",
        )
    if len(policy.steps) > max_steps:
        return _failed_episode(
            task=task,
            policy=policy,
            bundle=bundle,
            trajectory=[
                {
                    "type": "error",
                    "message": f"policy has {len(policy.steps)} steps; max_steps is {max_steps}",
                }
            ],
            failure_cause="max_steps_exceeded",
        )

    trajectory: list[dict[str, object]] = []
    response_context: dict[str, object] = {}
    for index, step in enumerate(policy.steps, start=1):
        request = RuntimeActionRequest(
            runtime_id=bundle.environment.runtime_metadata().runtime_id,
            tool_name=step.tool_name,
            arguments=step.arguments,
            action_id=f"action_{task.candidate_id}_{index}",
        )
        trajectory.append(_action_event(step))
        result = session.execute_action(request)
        if result.status != "succeeded":
            trajectory.append(
                {
                    "type": "error",
                    "tool": step.tool_name,
                    "message": str(result.observation.get("message", "runtime action failed")),
                }
            )
            return _failed_episode(
                task=task,
                policy=policy,
                bundle=bundle,
                trajectory=trajectory,
                failure_cause="tool_runtime_error",
            )
        observation = dict(result.observation)
        trajectory.append(
            {
                "type": "observation",
                "tool": step.tool_name,
                "observation": observation,
            }
        )
        response_context.update(_scalar_observation_values(observation))
        if result.state_change is not None:
            trajectory.append(
                {
                    "type": "state_change",
                    "tool": step.tool_name,
                    "change": dict(result.state_change),
                }
            )

    try:
        final_response = _render_final_response(policy, response_context)
    except PolicyValidationError as exc:
        trajectory.append({"type": "error", "message": str(exc)})
        return _failed_episode(
            task=task,
            policy=policy,
            bundle=bundle,
            trajectory=trajectory,
            failure_cause="solution_logic_error",
        )
    trajectory.append({"type": "final_response", "content": final_response})
    return build_episode_log(
        candidate_id=task.candidate_id,
        runtime_metadata=bundle.environment.runtime_metadata(),
        policy=policy,
        verifier=bundle.verifier,
        trajectory=trajectory,
        outcome_status="accepted",
    ).export()


def _failed_episode(
    *,
    task: CandidateTask,
    policy: SolutionPolicy,
    bundle: DomainPipelineBundle,
    trajectory: Sequence[Mapping[str, object]],
    failure_cause: str,
) -> dict[str, object]:
    return build_episode_log(
        candidate_id=task.candidate_id,
        runtime_metadata=bundle.environment.runtime_metadata(),
        policy=policy,
        verifier=bundle.verifier,
        trajectory=trajectory,
        outcome_status="failed",
        failure_cause=failure_cause,
    ).export()


def _action_event(step: ToolStep) -> dict[str, object]:
    return {
        "type": "action",
        "tool": step.tool_name,
        "arguments": dict(step.arguments),
    }


def _render_final_response(policy: SolutionPolicy, context: Mapping[str, object]) -> str:
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


def _scalar_observation_values(observation: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in observation.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
