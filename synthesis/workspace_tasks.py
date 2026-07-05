from __future__ import annotations

from dataclasses import replace

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, local_task_generation_lineage, order_candidates_by_curriculum


def generate_workspace_fixture_candidates(seed: DomainSeed) -> list[CandidateTask]:
    candidates = [
        CandidateTask(
            candidate_id="candidate_workspace_launch_lookup",
            instruction="Find the workspace task about the launch plan.",
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_item_lookup",
                "required_tools": ["search_workspace_items"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_workspace_items",
            arguments={"query": "launch", "kind": "task"},
            expected_answer="task_launch_plan",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_workspace_launch_checklist_task",
            instruction=(
                "Find the launch project and create a high-priority launch checklist "
                "task due this week."
            ),
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_task_creation",
                "required_tools": ["search_workspace_items", "create_workspace_task"],
            },
            difficulty=_difficulty(tool_count=2, state_changes=1),
            tool_name="search_workspace_items",
            arguments={"query": "Alpha Launch", "kind": "project"},
            expected_answer="task_prepare_launch_checklist",
            seed_ids=(seed.seed_id,),
            expected_state={
                "workspace_task": {
                    "project_id": "project_alpha",
                    "title": "Prepare launch checklist",
                    "priority": "high",
                    "due_label": "this_week",
                }
            },
        ),
        CandidateTask(
            candidate_id="candidate_workspace_launch_comment",
            instruction="Find the launch plan task and add a comment assigning the checklist owner.",
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_comment_update",
                "required_tools": ["search_workspace_items", "add_workspace_comment"],
            },
            difficulty=_difficulty(tool_count=2, state_changes=1),
            tool_name="search_workspace_items",
            arguments={"query": "launch plan", "kind": "task"},
            expected_answer="task_launch_plan",
            seed_ids=(seed.seed_id,),
            expected_state={
                "workspace_comment": {
                    "task_id": "task_launch_plan",
                    "comment": "Added launch checklist owner.",
                }
            },
        ),
        CandidateTask(
            candidate_id="candidate_workspace_launch_branch_fallback",
            instruction=(
                "Find the launch checklist owner note. If no direct task title match "
                "exists, fall back to searching comments."
            ),
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_branch_fallback",
                "required_tools": ["search_workspace_items"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0, recovery_paths=1),
            tool_name="search_workspace_items",
            arguments={"query": "checklist owner", "kind": "task"},
            expected_answer="task_launch_plan",
            seed_ids=(seed.seed_id,),
            branch_plan={
                "schema_version": "branch_plan_v1",
                "plan_id": "branch_plan_candidate_workspace_launch_fallback",
                "max_depth": 2,
                "branches": [
                    {
                        "branch_id": "direct_task_search",
                        "node_type": "attempt",
                        "parent_id": None,
                        "condition": "Try the direct task title first.",
                        "steps": [
                            {
                                "tool_name": "search_workspace_items",
                                "arguments": {
                                    "query": "checklist owner",
                                    "kind": "task",
                                },
                            }
                        ],
                        "final_response_template": "Workspace task found: {item_id}",
                        "terminal_outcome": "fallback_on_failure",
                    },
                    {
                        "branch_id": "comment_search",
                        "node_type": "fallback",
                        "parent_id": "direct_task_search",
                        "condition": "Search comments after direct task lookup fails.",
                        "steps": [
                            {
                                "tool_name": "search_workspace_items",
                                "arguments": {
                                    "query": "checklist owner",
                                    "kind": "comment",
                                },
                            }
                        ],
                        "final_response_template": "Workspace comment found: {item_id}",
                        "terminal_outcome": "accept_on_success",
                    },
                ],
            },
        ),
    ]
    return order_candidates_by_curriculum(_attach_workspace_generation_lineage(candidates))


def scripted_workspace_solution_policy(task: CandidateTask) -> SolutionPolicy:
    return scripted_workspace_solution_policy_from_contract(task.contract())


def scripted_workspace_solution_policy_from_contract(contract: "TaskContract") -> SolutionPolicy:
    from synthesis.task_contracts import validate_task_contract

    contract = validate_task_contract(contract)
    if contract.policy_hint.branch_plan is not None:
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_workspace_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            lineage=_workspace_policy_lineage(),
            branch_plan=dict(contract.policy_hint.branch_plan),
        )

    if contract.intent.task_type == "workspace_task_creation":
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_workspace_solution_policy",
            steps=(
                _primary_tool_step(contract),
                ToolStep(
                    tool_name="create_workspace_task",
                    arguments={
                        "project_id": _state_value(contract, "workspace_task", "project_id"),
                        "title": _state_value(contract, "workspace_task", "title"),
                        "priority": _state_value(contract, "workspace_task", "priority"),
                        "due_label": _state_value(contract, "workspace_task", "due_label"),
                    },
                ),
            ),
            final_response_template="Workspace task created: {task_id}.",
            lineage=_workspace_policy_lineage(),
        )

    if contract.intent.task_type == "workspace_comment_update":
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_workspace_solution_policy",
            steps=(
                _primary_tool_step(contract),
                ToolStep(
                    tool_name="add_workspace_comment",
                    arguments={
                        "task_id": _state_value(contract, "workspace_comment", "task_id"),
                        "comment": _state_value(contract, "workspace_comment", "comment"),
                    },
                ),
            ),
            final_response_template="Workspace comment added: {comment_id}.",
            lineage=_workspace_policy_lineage(),
        )

    return SolutionPolicy(
        policy_id=f"policy_{contract.intent.candidate_id}",
        role="scripted_workspace_solution_policy",
        steps=(_primary_tool_step(contract),),
        final_response_template="Workspace item found: {item_id}. {summary}",
        lineage=_workspace_policy_lineage(),
    )


def _primary_tool_step(contract: "TaskContract") -> ToolStep:
    assert contract.policy_hint.primary_tool is not None
    return ToolStep(
        tool_name=contract.policy_hint.primary_tool,
        arguments=dict(contract.policy_hint.primary_arguments),
    )


def _state_value(contract: "TaskContract", check_type: str, key: str) -> object:
    for state_check in contract.expected_state:
        if state_check.check_type == check_type:
            return state_check.expected.get(key)
    return None


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


def _attach_workspace_generation_lineage(candidates: list[CandidateTask]) -> list[CandidateTask]:
    lineage = dict(local_task_generation_lineage())
    lineage["owner_module"] = "synthesis.workspace_tasks"
    lineage["config_hash"] = "workspace-fixture-task-generation-v1"
    return [replace(candidate, generation_lineage=lineage) for candidate in candidates]


def _workspace_policy_lineage() -> dict[str, object]:
    return {
        "role": "scripted_workspace_solution_policy",
        "role_version": "role_scripted_workspace_solution_policy_v1",
        "output_type": "solution_policy",
        "owner_module": "synthesis.workspace_tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted_workspace_fixture",
        "config_hash": "workspace-fixture-policy-v1",
        "configured": True,
    }
