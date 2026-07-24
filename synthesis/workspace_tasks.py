from __future__ import annotations

import re
from dataclasses import replace

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.mutation_admission import (
    DeterministicSemanticMutationJudge,
    MutationActionPolicy,
    MutationArgumentPolicy,
    SEMANTIC_VERDICT_VERSION,
    SemanticJudgeRequest,
    canonical_hash,
    instruction_span,
    normalized_instruction,
    policy_hash,
)
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, local_task_generation_lineage, order_candidates_by_curriculum


def build_workspace_generation_spec(environment: object, registry: object):
    from synthesis.domain_generation import (
        DOMAIN_GENERATION_SPEC_VERSION,
        SYNTHETIC_CONTEXT_POLICY,
        DomainGenerationSpec,
        DomainTaskTypeSpec,
        validate_domain_generation_spec,
    )

    if getattr(environment, "source_input", None) is not None:
        raise ValueError("source_backed_remote_context_not_allowed")
    item_arguments = [
        {"query": "Alpha Launch", "kind": "project"},
        {"query": "launch plan", "kind": "task"},
        {"query": "metrics dashboard", "kind": "task"},
    ]
    items = [
        {
            "primary_arguments": arguments,
            "observation": environment.search_workspace_items(**arguments),
        }
        for arguments in item_arguments
    ]
    spec = DomainGenerationSpec(
        schema_version=DOMAIN_GENERATION_SPEC_VERSION,
        domain_id="workspace_tasks_fixture",
        task_types=(
            DomainTaskTypeSpec(
                "workspace_item_search",
                ("search_workspace_items",),
                required_capabilities=("workspace_search",),
                final_answer_fields=("item_id", "summary"),
            ),
            DomainTaskTypeSpec(
                "workspace_task_creation",
                ("search_workspace_items", "create_workspace_task"),
                ("workspace_task",),
                required_capabilities=("workspace_search", "workspace_task_creation"),
                expected_state_tool="create_workspace_task",
                final_answer_source="state_tool_observation",
                final_answer_fields=("task_id",),
                final_answer_derivation="task_{title|stable_id}",
            ),
            DomainTaskTypeSpec(
                "workspace_comment_update",
                ("search_workspace_items", "add_workspace_comment"),
                ("workspace_comment",),
                required_capabilities=("workspace_search", "workspace_comment_update"),
                expected_state_tool="add_workspace_comment",
                final_answer_source="state_tool_observation",
                final_answer_fields=("comment_id",),
                final_answer_derivation="comment_{task_id}_{comment|stable_id}",
                expected_state_reference_fields=(("task_id", "item_id"),),
            ),
        ),
        tools=tuple(registry.export()),
        grounding_context={"workspace_items": items},
        context_policy=SYNTHETIC_CONTEXT_POLICY,
        max_candidates_per_call=2,
        grounding_window_size=2,
    )
    validate_domain_generation_spec(spec)
    return spec


def workspace_mutation_policies() -> tuple[MutationActionPolicy, ...]:
    return (
        MutationActionPolicy(
            schema_version="workspace_comment_mutation_policy_v1",
            domain_id="workspace_tasks_fixture",
            task_type="workspace_comment_update",
            action_type="workspace_comment_add",
            tool_name="add_workspace_comment",
            arguments=(
                MutationArgumentPolicy(
                    name="comment",
                    requester_controlled=True,
                    allowed_origins=("instruction",),
                ),
                MutationArgumentPolicy(
                    name="task_id",
                    requester_controlled=False,
                    allowed_origins=("tool_observation",),
                    observation_tool="search_workspace_items",
                    observation_field="item_id",
                    observation_bindings=(
                        (
                            canonical_hash(
                                {"query": "launch plan", "kind": "task"}
                            ),
                            canonical_hash("task_launch_plan"),
                        ),
                    ),
                    binding_argument_names=("query", "kind"),
                ),
            ),
        ),
    )


def _workspace_semantic_mutation_verdict(
    request: SemanticJudgeRequest,
) -> dict[str, object]:
    instruction = request.instruction.lower()
    action_reference = request.evidence_references["action"]
    action_reason = "action_authorized"
    action_outcome = "supported"
    if "ignore previous" in instruction or "ignore all previous" in instruction:
        action_reason = "instruction_prompt_injection"
        action_outcome = "unsupported"
    elif re.search(r"\b(?:do not|don't|without)\b[^.]{0,80}\bcomment\b", instruction):
        action_reason = "action_negated"
        action_outcome = "unsupported"
    elif any(
        phrase in instruction
        for phrase in ("if appropriate", "if needed", "maybe add", "consider adding")
    ):
        action_reason = "conditional_authorization_ambiguous"
        action_outcome = "uncertain"
    elif "comment" not in request.action_evidence_text.lower():
        action_reason = "action_not_authorized"
        action_outcome = "unsupported"

    action_findings = [
        {
            "action_type": request.action_type,
            "outcome": action_outcome,
            "reason_code": action_reason,
            "evidence_references": [action_reference],
        }
    ]
    argument_findings: list[dict[str, object]] = []
    outcomes = [action_outcome]
    reason_codes = [action_reason]
    all_references = [action_reference]
    for name, origin in request.argument_origins.items():
        reference = request.evidence_references[name]
        if origin == "tool_observation":
            outcome = "supported"
            reason = "observation_reference_supported"
        elif origin == "instruction":
            value = str(request.argument_values.get(name, ""))
            evidence_text = str(request.argument_evidence.get(name, ""))
            if value.lower() in instruction:
                outcome = "supported"
                reason = "argument_literal_supported"
            else:
                overlap = _semantic_token_overlap(value, evidence_text)
                if overlap >= 2:
                    outcome = "supported"
                    reason = "argument_semantic_supported"
                elif overlap == 1:
                    outcome = "uncertain"
                    reason = "evidence_ambiguous"
                else:
                    outcome = "unsupported"
                    reason = "argument_not_supported"
        elif origin == "declared_default":
            outcome = "supported"
            reason = "declared_default_supported"
        else:
            outcome = "supported"
            reason = "deterministic_derivation_supported"
        argument_findings.append(
            {
                "argument": name,
                "outcome": outcome,
                "reason_code": reason,
                "evidence_references": [reference],
            }
        )
        outcomes.append(outcome)
        reason_codes.append(reason)
        all_references.append(reference)

    verdict = (
        "unsupported"
        if "unsupported" in outcomes
        else "uncertain"
        if "uncertain" in outcomes
        else "supported"
    )
    return {
        "schema_version": SEMANTIC_VERDICT_VERSION,
        "verdict": verdict,
        "action_findings": action_findings,
        "argument_findings": argument_findings,
        "reason_codes": _unique(reason_codes),
        "evidence_references": _unique(all_references),
        "input_hash": request.input_hash(),
    }


workspace_semantic_mutation_judge = DeterministicSemanticMutationJudge(
    evaluate=_workspace_semantic_mutation_verdict,
    model="deterministic_workspace_comment_judge_v1",
)


def _semantic_token_overlap(left: str, right: str) -> int:
    stopwords = {"a", "an", "and", "the", "to", "for", "of", "add", "added"}
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower())) - stopwords
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower())) - stopwords
    return len(left_tokens & right_tokens)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


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
            candidate_id="candidate_workspace_metrics_review_lookup",
            instruction="Find the workspace task about the launch metrics dashboard.",
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_item_lookup",
                "required_tools": ["search_workspace_items"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_workspace_items",
            arguments={"query": "metrics dashboard", "kind": "task"},
            expected_answer="task_metrics_review",
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
    candidates = _attach_workspace_generation_lineage(candidates)
    candidates = [
        propose_workspace_comment_authorization(candidate)
        if candidate.constraints.get("task_type") == "workspace_comment_update"
        else candidate
        for candidate in candidates
    ]
    return order_candidates_by_curriculum(candidates)


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


def propose_workspace_comment_authorization(candidate: CandidateTask) -> CandidateTask:
    policy = scripted_workspace_solution_policy(candidate)
    instruction = normalized_instruction(candidate.instruction)
    action_evidence = instruction_span(
        instruction,
        "add a comment assigning the checklist owner",
        reference_id="instruction.action",
    )
    comment_evidence = instruction_span(
        instruction,
        "assigning the checklist owner",
        reference_id="instruction.comment",
    )
    task_evidence = instruction_span(
        instruction,
        "launch plan task",
        reference_id="instruction.selected_task",
    )
    mutation_step = policy.steps[1]
    source_step = policy.steps[0]
    record: dict[str, object] = {
        "schema_version": "mutation_authorization_record_v1",
        "instruction_hash": canonical_hash(instruction),
        "policy_hash": policy_hash(policy),
        "actions": [
            {
                "action_ref": "policy.steps.1",
                "action_type": "workspace_comment_add",
                "instruction_evidence": action_evidence,
                "arguments": [
                    {
                        "name": "comment",
                        "origin": "instruction",
                        "support": "semantic",
                        "evidence": comment_evidence,
                    },
                    {
                        "name": "task_id",
                        "origin": "tool_observation",
                        "evidence": {
                            "reference_id": "observation.selected_task",
                            "kind": "tool_observation",
                            "source_action_ref": "policy.steps.0",
                            "source_field": "item_id",
                            "source_arguments_hash": canonical_hash(source_step.arguments),
                            "value_hash": canonical_hash(
                                mutation_step.arguments.get("task_id")
                            ),
                            "binding_instruction_evidence": task_evidence,
                        },
                    },
                ],
            }
        ],
    }
    return replace(candidate, mutation_authorization=record)
