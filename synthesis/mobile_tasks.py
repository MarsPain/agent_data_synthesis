from __future__ import annotations

from dataclasses import replace

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, local_task_generation_lineage, order_candidates_by_curriculum


def build_mobile_generation_spec(environment: object, registry: object):
    from synthesis.domain_generation import (
        DOMAIN_GENERATION_SPEC_VERSION,
        MAX_CANDIDATES_PER_CALL,
        SYNTHETIC_CONTEXT_POLICY,
        DomainGenerationSpec,
        DomainTaskTypeSpec,
        validate_domain_generation_spec,
    )

    if getattr(environment, "source_input", None) is not None:
        raise ValueError("source_backed_remote_context_not_allowed")
    messages = [
        environment.search_messages(query="project update", participant="Maya"),
        environment.search_messages(query="five minutes late", participant="Alex"),
        environment.search_messages(query="pickup code", participant="Delivery"),
    ]
    spec = DomainGenerationSpec(
        schema_version=DOMAIN_GENERATION_SPEC_VERSION,
        domain_id="mobile_messages_fixture",
        task_types=(
            DomainTaskTypeSpec("mobile_message_search", ("search_phone_messages",)),
            DomainTaskTypeSpec(
                "mobile_reminder_creation",
                ("search_phone_messages", "create_phone_reminder"),
                ("mobile_reminder",),
            ),
            DomainTaskTypeSpec(
                "mobile_draft_reply",
                ("search_phone_messages", "draft_message_reply"),
                ("mobile_draft_reply",),
            ),
        ),
        tools=tuple(registry.export()),
        grounding_context={"messages": messages},
        context_policy=SYNTHETIC_CONTEXT_POLICY,
        max_candidates_per_call=MAX_CANDIDATES_PER_CALL,
    )
    validate_domain_generation_spec(spec)
    return spec


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
            candidate_id="candidate_mobile_delivery_code_lookup",
            instruction="Find the delivery pickup code in the phone inbox.",
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_lookup",
                "required_tools": ["search_phone_messages"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_phone_messages",
            arguments={"query": "pickup code", "participant": "Delivery"},
            expected_answer="4821",
            seed_ids=(seed.seed_id,),
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
    return scripted_mobile_solution_policy_from_contract(task.contract())


def scripted_mobile_solution_policy_from_contract(contract: "TaskContract") -> SolutionPolicy:
    from synthesis.task_contracts import validate_task_contract

    contract = validate_task_contract(contract)
    task_type = contract.intent.task_type
    if contract.policy_hint.branch_plan is not None:
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            lineage=_mobile_policy_lineage(),
            branch_plan=dict(contract.policy_hint.branch_plan),
        )

    if task_type in {"mobile_message_to_reminder", "mobile_reminder_creation"}:
        reminder_arguments = {
            key: value
            for key, value in {
                "title": _state_value(contract, "mobile_reminder", "title"),
                "due_at": _state_value(contract, "mobile_reminder", "due_at"),
                "source_message_id": _state_value(
                    contract,
                    "mobile_reminder",
                    "source_message_id",
                ),
            }.items()
            if value is not None
        }
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(
                _primary_tool_step(contract),
                ToolStep(
                    tool_name="create_phone_reminder",
                    arguments=reminder_arguments,
                ),
            ),
            final_response_template="Reminder created from {source_message_id}.",
            lineage=_mobile_policy_lineage(),
        )

    if task_type == "mobile_draft_reply":
        return SolutionPolicy(
            policy_id=f"policy_{contract.intent.candidate_id}",
            role="scripted_mobile_solution_policy",
            steps=(
                _primary_tool_step(contract),
                ToolStep(
                    tool_name="draft_message_reply",
                    arguments={
                        "thread_id": _state_value(
                            contract,
                            "mobile_draft_reply",
                            "thread_id",
                        ),
                        "body": _state_value(contract, "mobile_draft_reply", "body"),
                    },
                ),
            ),
            final_response_template="Draft reply ready: {body}",
            lineage=_mobile_policy_lineage(),
        )

    return SolutionPolicy(
        policy_id=f"policy_{contract.intent.candidate_id}",
        role="scripted_mobile_solution_policy",
        steps=(_primary_tool_step(contract),),
        final_response_template="Message found: {message_id}. {snippet}",
        lineage=_mobile_policy_lineage(),
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
