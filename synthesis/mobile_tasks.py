from __future__ import annotations

from dataclasses import replace

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, local_task_generation_lineage, order_candidates_by_curriculum


def generate_mobile_fixture_candidates(seed: DomainSeed) -> list[CandidateTask]:
    candidates = [
        CandidateTask(
            candidate_id="candidate_mobile_maya_lookup",
            instruction="Find Maya's message about the project update in the phone inbox.",
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_lookup",
                "required_tools": ["search_phone_messages"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_phone_messages",
            arguments={"query": "project update", "participant": "Maya"},
            expected_answer="msg_maya_project_update",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_mobile_maya_reminder",
            instruction=(
                "Find Maya's message and create a reminder to send the project "
                "update tomorrow at 9 AM."
            ),
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_to_reminder",
                "required_tools": ["search_phone_messages", "create_phone_reminder"],
            },
            difficulty=_difficulty(tool_count=2, state_changes=1),
            tool_name="search_phone_messages",
            arguments={"query": "project update", "participant": "Maya"},
            expected_answer="msg_maya_project_update",
            seed_ids=(seed.seed_id,),
            expected_state={
                "mobile_reminder": {
                    "title": "Send the project update",
                    "due_at": "tomorrow 9 AM",
                    "source_message_id": "msg_maya_project_update",
                }
            },
        ),
        CandidateTask(
            candidate_id="candidate_mobile_alex_draft_reply",
            instruction="Find Alex's late-arrival message and draft the requested reply.",
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_draft_reply",
                "required_tools": ["search_phone_messages", "draft_message_reply"],
            },
            difficulty=_difficulty(tool_count=2, state_changes=1),
            tool_name="search_phone_messages",
            arguments={"query": "five minutes late", "participant": "Alex"},
            expected_answer="I will be five minutes late.",
            seed_ids=(seed.seed_id,),
            expected_state={
                "mobile_draft_reply": {
                    "thread_id": "thread_alex",
                    "body": "I will be five minutes late.",
                }
            },
        ),
        CandidateTask(
            candidate_id="candidate_mobile_delivery_branch_fallback",
            instruction=(
                "Find the delivery pickup code. If no direct sender match exists, "
                "fall back to a broader thread search."
            ),
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_branch_fallback",
                "required_tools": ["search_phone_messages"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0, recovery_paths=1),
            tool_name="search_phone_messages",
            arguments={"query": "pickup code", "participant": "Courier"},
            expected_answer="4821",
            seed_ids=(seed.seed_id,),
            branch_plan={
                "schema_version": "branch_plan_v1",
                "plan_id": "branch_plan_candidate_mobile_delivery_fallback",
                "max_depth": 2,
                "branches": [
                    {
                        "branch_id": "direct_sender_search",
                        "node_type": "attempt",
                        "parent_id": None,
                        "condition": "Try the direct sender label first.",
                        "steps": [
                            {
                                "tool_name": "search_phone_messages",
                                "arguments": {
                                    "query": "pickup code",
                                    "participant": "Courier",
                                },
                            }
                        ],
                        "final_response_template": "Pickup code found: {snippet}",
                        "terminal_outcome": "fallback_on_failure",
                    },
                    {
                        "branch_id": "broader_thread_search",
                        "node_type": "fallback",
                        "parent_id": "direct_sender_search",
                        "condition": "Search across threads after direct sender lookup fails.",
                        "steps": [
                            {
                                "tool_name": "search_phone_messages",
                                "arguments": {"query": "pickup code"},
                            }
                        ],
                        "final_response_template": "Pickup code found: {snippet}",
                        "terminal_outcome": "accept_on_success",
                    },
                ],
            },
        ),
    ]
    return order_candidates_by_curriculum(_attach_mobile_generation_lineage(candidates))


def scripted_mobile_solution_policy(task: CandidateTask) -> SolutionPolicy:
    task_type = task.constraints.get("task_type")
    if task.branch_plan is not None:
        return SolutionPolicy(
            policy_id=f"policy_{task.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            lineage=_mobile_policy_lineage(),
            branch_plan=task.branch_plan,
        )

    if task_type == "mobile_message_to_reminder":
        return SolutionPolicy(
            policy_id=f"policy_{task.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(
                ToolStep(tool_name="search_phone_messages", arguments=task.arguments),
                ToolStep(
                    tool_name="create_phone_reminder",
                    arguments={
                        "title": "Send the project update",
                        "due_at": "tomorrow 9 AM",
                        "source_message_id": "msg_maya_project_update",
                    },
                ),
            ),
            final_response_template="Reminder created from {source_message_id}.",
            lineage=_mobile_policy_lineage(),
        )

    if task_type == "mobile_draft_reply":
        return SolutionPolicy(
            policy_id=f"policy_{task.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(
                ToolStep(tool_name="search_phone_messages", arguments=task.arguments),
                ToolStep(
                    tool_name="draft_message_reply",
                    arguments={
                        "thread_id": "thread_alex",
                        "body": "I will be five minutes late.",
                    },
                ),
            ),
            final_response_template="Draft reply ready: {body}",
            lineage=_mobile_policy_lineage(),
        )

    return SolutionPolicy(
        policy_id=f"policy_{task.candidate_id}",
        role="scripted_mobile_solution_policy",
        steps=(ToolStep(tool_name=task.tool_name, arguments=task.arguments),),
        final_response_template="Message found: {message_id}. {snippet}",
        lineage=_mobile_policy_lineage(),
    )


def _difficulty(
    *,
    tool_count: int,
    state_changes: int,
    recovery_paths: int = 0,
) -> dict[str, object]:
    return {
        "level": "medium" if state_changes else "easy",
        "tool_count": tool_count,
        "constraint_count": 2,
        "state_changes": state_changes,
        "ambiguity": "none",
        "recovery_paths": recovery_paths,
    }


def _attach_mobile_generation_lineage(candidates: list[CandidateTask]) -> list[CandidateTask]:
    lineage = dict(local_task_generation_lineage())
    lineage["owner_module"] = "synthesis.mobile_tasks"
    lineage["config_hash"] = "mobile-fixture-task-generation-v1"
    return [replace(candidate, generation_lineage=lineage) for candidate in candidates]


def _mobile_policy_lineage() -> dict[str, object]:
    return {
        "role": "scripted_mobile_solution_policy",
        "role_version": "role_scripted_mobile_solution_policy_v1",
        "output_type": "solution_policy",
        "owner_module": "synthesis.mobile_tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted_mobile_fixture",
        "config_hash": "mobile-fixture-policy-v1",
        "configured": True,
    }
