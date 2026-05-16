from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from synthesis.contracts import validate_candidate_task, validate_refinement_attempt
from synthesis.execution import (
    SolutionPolicy,
    ToolStep,
    validate_solution_policy,
)
from synthesis.llm import LLMProviderError
from synthesis.roles import CRITIC_REFINEMENT_ROLE, RoleRegistry, default_role_registry
from synthesis.tasks import CandidateTask, candidate_from_mapping


REPAIRABLE_FAILURE_CAUSES = {
    "verification_failed",
    "solution_logic_error",
}


@dataclass(frozen=True)
class RefinementContext:
    task: CandidateTask
    source_failure_cause: str
    source_failure_details: dict[str, object]
    attempt_number: int = 1
    source_policy: SolutionPolicy | None = None


@dataclass(frozen=True)
class RefinementAttempt:
    original_candidate_id: str
    attempt_number: int
    source_failure_cause: str
    source_failure_details: dict[str, object]
    critic_diagnosis: str
    repair_decision: str
    lineage: dict[str, object]
    revised_candidate: CandidateTask | None = None
    revised_policy: SolutionPolicy | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "original_candidate_id": self.original_candidate_id,
            "attempt_number": self.attempt_number,
            "source_failure_cause": self.source_failure_cause,
            "source_failure_details": self.source_failure_details,
            "critic_diagnosis": self.critic_diagnosis,
            "repair_decision": self.repair_decision,
            "lineage": dict(self.lineage),
        }
        if self.revised_candidate is not None:
            record["revised_candidate"] = _candidate_payload(self.revised_candidate)
        if self.revised_policy is not None:
            record["revised_policy"] = _policy_payload(self.revised_policy)
        validate_refinement_attempt(record)
        return record

    def sample_lineage(self) -> dict[str, object]:
        lineage = dict(self.lineage)
        lineage.update(
            {
                "original_candidate_id": self.original_candidate_id,
                "attempt_number": self.attempt_number,
                "source_failure_cause": self.source_failure_cause,
                "critic_diagnosis": self.critic_diagnosis,
                "repair_decision": self.repair_decision,
            }
        )
        return lineage

    def rejection_metadata(self, *, outcome: str) -> dict[str, object]:
        return {
            "outcome": outcome,
            "original_candidate_id": self.original_candidate_id,
            "attempt_number": self.attempt_number,
            "source_failure_cause": self.source_failure_cause,
            "source_failure_details": self.source_failure_details,
            "critic_diagnosis": self.critic_diagnosis,
            "repair_decision": self.repair_decision,
            "lineage": dict(self.lineage),
        }


Refiner = Callable[[RefinementContext], RefinementAttempt | None]


def repairable(cause: str) -> bool:
    return cause in REPAIRABLE_FAILURE_CAUSES


def deterministic_fixture_refiner(context: RefinementContext) -> RefinementAttempt | None:
    if context.attempt_number != 1 or not repairable(context.source_failure_cause):
        return None
    if _is_ben_wrong_expectation(context):
        revised = replace(
            context.task,
            candidate_id=f"{context.task.candidate_id}_refined_1",
            expected_answer="ben.carter@example.test",
        )
        return _candidate_attempt(
            context,
            diagnosis="Expected answer used ben@example.test instead of the fixture email.",
            revised_candidate=revised,
        )
    if _is_missing_followup_mutation(context):
        name = str(context.task.arguments.get("name", ""))
        note = f"Send follow-up email to {context.task.expected_answer}."
        policy = SolutionPolicy(
            policy_id=f"policy_{context.task.candidate_id}_refined_1",
            role="local_critic_refinement",
            steps=(
                ToolStep(tool_name="lookup_contact_email", arguments={"name": name}),
                ToolStep(
                    tool_name="record_contact_followup",
                    arguments={"name": name, "note": note},
                ),
            ),
            final_response_template="{name}'s email is {email}. Follow-up recorded.",
            lineage=_local_lineage(),
        )
        return _policy_attempt(
            context,
            diagnosis="Stateful contact-followup task skipped the required mutation tool.",
            revised_policy=policy,
        )
    return None


def generate_llm_backed_refinement(
    *,
    task: CandidateTask,
    source_failure_cause: str,
    source_failure_details: dict[str, object],
    attempt_number: int,
    client: Any,
    source_policy: SolutionPolicy | None = None,
    role_registry: RoleRegistry | None = None,
) -> RefinementAttempt:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        CRITIC_REFINEMENT_ROLE,
        client,
        _refinement_prompt(
            task=task,
            source_failure_cause=source_failure_cause,
            source_failure_details=source_failure_details,
            source_policy=source_policy,
        ),
    )
    try:
        return _attempt_from_remote_content(
            task=task,
            source_failure_cause=source_failure_cause,
            source_failure_details=source_failure_details,
            attempt_number=attempt_number,
            content=result.content,
            lineage=result.lineage,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class=type(exc).__name__,
            retryable=False,
            retry_count=_lineage_retry_count(result.lineage),
            lineage=result.lineage,
        ) from exc


def _attempt_from_remote_content(
    *,
    task: CandidateTask,
    source_failure_cause: str,
    source_failure_details: dict[str, object],
    attempt_number: int,
    content: dict[str, Any],
    lineage: dict[str, object],
) -> RefinementAttempt:
    decision = str(content["repair_decision"])
    diagnosis = str(content["critic_diagnosis"])
    if decision == "not_repairable":
        attempt = RefinementAttempt(
            original_candidate_id=task.candidate_id,
            attempt_number=attempt_number,
            source_failure_cause=source_failure_cause,
            source_failure_details=source_failure_details,
            critic_diagnosis=diagnosis,
            repair_decision=decision,
            lineage=dict(lineage),
        )
    elif decision == "repair_candidate":
        raw_candidate = content["candidate"]
        if not isinstance(raw_candidate, dict):
            raise TypeError("candidate must be an object")
        candidate = candidate_from_mapping(
            raw_candidate,
            seed_ids=task.seed_ids,
            generation_lineage=task.generation_lineage,
        )
        validate_candidate_task(candidate)
        attempt = RefinementAttempt(
            original_candidate_id=task.candidate_id,
            attempt_number=attempt_number,
            source_failure_cause=source_failure_cause,
            source_failure_details=source_failure_details,
            critic_diagnosis=diagnosis,
            repair_decision=decision,
            lineage=dict(lineage),
            revised_candidate=candidate,
        )
    elif decision == "repair_policy":
        raw_policy = content["policy"]
        if not isinstance(raw_policy, dict):
            raise TypeError("policy must be an object")
        policy = _policy_from_mapping(raw_policy, lineage=dict(lineage))
        attempt = RefinementAttempt(
            original_candidate_id=task.candidate_id,
            attempt_number=attempt_number,
            source_failure_cause=source_failure_cause,
            source_failure_details=source_failure_details,
            critic_diagnosis=diagnosis,
            repair_decision=decision,
            lineage=dict(lineage),
            revised_policy=policy,
        )
    else:
        raise ValueError("unsupported repair decision")
    attempt.export()
    return attempt


def _policy_from_mapping(raw_policy: dict[str, Any], *, lineage: dict[str, object]) -> SolutionPolicy:
    raw_steps = raw_policy["steps"]
    if not isinstance(raw_steps, list):
        raise TypeError("policy steps must be a list")
    policy = SolutionPolicy(
        policy_id=str(raw_policy["policy_id"]),
        role=CRITIC_REFINEMENT_ROLE,
        steps=tuple(_tool_step_from_mapping(step) for step in raw_steps),
        final_response_template=str(raw_policy["final_response_template"]),
        lineage=lineage,
    )
    validate_solution_policy(policy)
    return policy


def _tool_step_from_mapping(raw: object) -> ToolStep:
    if not isinstance(raw, dict):
        raise TypeError("policy step must be an object")
    arguments = raw.get("arguments")
    if not isinstance(arguments, dict):
        raise TypeError("policy step arguments must be an object")
    return ToolStep(tool_name=str(raw["tool_name"]), arguments=arguments)


def _candidate_attempt(
    context: RefinementContext,
    *,
    diagnosis: str,
    revised_candidate: CandidateTask,
) -> RefinementAttempt:
    attempt = RefinementAttempt(
        original_candidate_id=context.task.candidate_id,
        attempt_number=context.attempt_number,
        source_failure_cause=context.source_failure_cause,
        source_failure_details=context.source_failure_details,
        critic_diagnosis=diagnosis,
        repair_decision="repair_candidate",
        lineage=_local_lineage(),
        revised_candidate=revised_candidate,
    )
    attempt.export()
    return attempt


def _policy_attempt(
    context: RefinementContext,
    *,
    diagnosis: str,
    revised_policy: SolutionPolicy,
) -> RefinementAttempt:
    attempt = RefinementAttempt(
        original_candidate_id=context.task.candidate_id,
        attempt_number=context.attempt_number,
        source_failure_cause=context.source_failure_cause,
        source_failure_details=context.source_failure_details,
        critic_diagnosis=diagnosis,
        repair_decision="repair_policy",
        lineage=_local_lineage(),
        revised_policy=revised_policy,
    )
    attempt.export()
    return attempt


def _is_ben_wrong_expectation(context: RefinementContext) -> bool:
    return (
        context.source_failure_cause == "verification_failed"
        and context.task.arguments.get("name") == "Ben Carter"
        and context.task.expected_answer == "ben@example.test"
    )


def _is_missing_followup_mutation(context: RefinementContext) -> bool:
    return (
        context.source_failure_cause == "solution_logic_error"
        and context.task.constraints.get("task_type") == "contact_followup"
        and context.task.expected_state is not None
    )


def _local_lineage() -> dict[str, object]:
    return {
        "role": "local_critic_refinement",
        "role_version": "role_local_critic_refinement_v1",
        "output_type": "refinement_attempt",
        "owner_module": "synthesis.refinement",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "deterministic",
        "config_hash": "deterministic_refinement_v1",
        "configured": True,
    }


def _candidate_payload(task: CandidateTask) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": task.candidate_id,
        "instruction": task.instruction,
        "constraints": task.constraints,
        "difficulty": task.difficulty,
        "tool_name": task.tool_name,
        "arguments": task.arguments,
        "expected_answer": task.expected_answer,
    }
    if task.expected_state is not None:
        payload["expected_state"] = task.expected_state
    return payload


def _policy_payload(policy: SolutionPolicy) -> dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "steps": [
            {"tool_name": step.tool_name, "arguments": step.arguments}
            for step in policy.steps
        ],
        "final_response_template": policy.final_response_template,
    }


def _refinement_prompt(
    *,
    task: CandidateTask,
    source_failure_cause: str,
    source_failure_details: dict[str, object],
    source_policy: SolutionPolicy | None,
) -> str:
    return (
        "Diagnose one failed Agent data synthesis candidate and return one bounded repair.\n"
        f"Candidate id: {task.candidate_id}\n"
        f"Instruction: {task.instruction}\n"
        f"Constraints: {task.constraints}\n"
        f"Tool name: {task.tool_name}\n"
        f"Arguments: {task.arguments}\n"
        f"Expected answer: {task.expected_answer}\n"
        f"Expected state: {task.expected_state}\n"
        f"Source failure cause: {source_failure_cause}\n"
        f"Source failure details: {source_failure_details}\n"
        f"Source policy: {_policy_payload(source_policy) if source_policy else None}\n"
        "Return JSON with repair_decision and critic_diagnosis. "
        "Use repair_candidate with a candidate object for wrong expectations, "
        "repair_policy with a policy object for missing tool mutations, or "
        "not_repairable when no bounded repair is available."
    )


def _lineage_retry_count(lineage: dict[str, object]) -> int:
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        return retry_count
    return 0
