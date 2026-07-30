from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.mutation_admission import (
    DeterministicSemanticMutationJudge,
    MutationActionPolicy,
    MutationArgumentPolicy,
    SEMANTIC_VERDICT_VERSION,
    SemanticJudgeRequest,
    canonical_hash,
    normalized_instruction,
    policy_hash,
)
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, local_task_generation_lineage, order_candidates_by_curriculum

if TYPE_CHECKING:
    from synthesis.task_contracts import TaskContract


class WorkspaceGenerationEnvironment(Protocol):
    @property
    def source_input(self) -> object | None: ...

    def search_workspace_items(
        self,
        *,
        query: str,
        kind: str | None = None,
    ) -> dict[str, object]: ...


class WorkspaceToolExporter(Protocol):
    def export(self) -> list[dict[str, object]]: ...


class WorkspaceMutationPolicyEnvironment(Protocol):
    def project_search_bindings(
        self,
    ) -> tuple[tuple[dict[str, object], str], ...]: ...

    def search_workspace_items(
        self,
        *,
        query: str,
        kind: str | None = None,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class WorkspaceActionSemantics:
    entity_tokens: frozenset[str]
    authorization_verbs: frozenset[str]
    negation_target_pattern: str


@dataclass(frozen=True)
class WorkspaceProjectMention:
    query_matches: bool
    is_destination: bool
    is_lookup_subject: bool
    is_negated: bool


_WORKSPACE_ACTION_SEMANTICS = {
    "workspace_task_create": WorkspaceActionSemantics(
        entity_tokens=frozenset({"task", "item"}),
        authorization_verbs=frozenset({"add", "create", "make", "prepare"}),
        negation_target_pattern=r"(?:task|item)",
    ),
    "workspace_comment_add": WorkspaceActionSemantics(
        entity_tokens=frozenset({"comment"}),
        authorization_verbs=frozenset({"add", "create", "leave", "post", "write"}),
        negation_target_pattern=r"comment",
    ),
}

WORKSPACE_ITEM_GROUNDING_ARGUMENTS = (
    {"query": "Alpha Launch", "kind": "project"},
    {"query": "launch plan", "kind": "task"},
    {"query": "metrics dashboard", "kind": "task"},
    {"query": "launch"},
    {"query": "Beta Research", "kind": "project"},
    {"query": "research notes", "kind": "task"},
    {"query": "checklist owner", "kind": "comment"},
)


def build_workspace_generation_spec(
    environment: WorkspaceGenerationEnvironment,
    registry: WorkspaceToolExporter,
):
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
        dict(arguments)
        for arguments in WORKSPACE_ITEM_GROUNDING_ARGUMENTS
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


def workspace_mutation_policies(
    environment: WorkspaceMutationPolicyEnvironment | None = None,
) -> tuple[MutationActionPolicy, ...]:
    project_bindings = _workspace_project_observation_bindings(environment)
    task_bindings = _workspace_task_observation_bindings(environment)
    return (
        MutationActionPolicy(
            schema_version="workspace_task_mutation_policy_v1",
            domain_id="workspace_tasks_fixture",
            task_type="workspace_task_creation",
            action_type="workspace_task_create",
            tool_name="create_workspace_task",
            arguments=(
                MutationArgumentPolicy(
                    name="title",
                    requester_controlled=True,
                    allowed_origins=("instruction",),
                ),
                MutationArgumentPolicy(
                    name="priority",
                    requester_controlled=True,
                    allowed_origins=("instruction",),
                ),
                MutationArgumentPolicy(
                    name="due_label",
                    requester_controlled=True,
                    allowed_origins=("instruction",),
                ),
                MutationArgumentPolicy(
                    name="project_id",
                    requester_controlled=False,
                    allowed_origins=("tool_observation",),
                    observation_tool="search_workspace_items",
                    observation_field="project_id",
                    observation_bindings=project_bindings,
                    binding_argument_names=("query", "kind"),
                    binding_token_aliases=(("task", "tasks"),),
                ),
            ),
            operational_defaults=(
                ("created_at", "workspace_task_created_at_default_v1"),
            ),
            deterministic_derivations=(
                ("task_id", "workspace_task_id_from_title_v1"),
            ),
        ),
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
                    observation_bindings=task_bindings,
                    binding_argument_names=("query", "kind"),
                    binding_token_aliases=(("task", "tasks"),),
                ),
            ),
            operational_defaults=(
                ("created_at", "workspace_comment_created_at_default_v1"),
            ),
            deterministic_derivations=(
                (
                    "comment_id",
                    "workspace_comment_id_from_task_and_body_v1",
                ),
            ),
        ),
    )


def _workspace_project_observation_bindings(
    environment: WorkspaceMutationPolicyEnvironment | None,
) -> tuple[tuple[str, str], ...]:
    if environment is not None:
        raw_bindings = list(environment.project_search_bindings())
        for arguments in WORKSPACE_ITEM_GROUNDING_ARGUMENTS:
            try:
                observation = environment.search_workspace_items(**arguments)
            except KeyError:
                continue
            project_id = observation.get("project_id")
            if isinstance(project_id, str):
                raw_bindings.append((dict(arguments), project_id))
    else:
        raw_bindings = [
            (
                {"query": "Alpha Launch", "kind": "project"},
                "project_alpha",
            ),
            (
                {"query": "Beta Research", "kind": "project"},
                "project_beta",
            ),
            (
                {"query": "launch plan", "kind": "task"},
                "project_alpha",
            ),
            (
                {"query": "metrics dashboard", "kind": "task"},
                "project_alpha",
            ),
            (
                {"query": "research notes", "kind": "task"},
                "project_beta",
            ),
        ]
    bindings = {
        (canonical_hash(arguments), canonical_hash(project_id))
        for arguments, project_id in raw_bindings
    }
    return tuple(sorted(bindings))


def _workspace_task_observation_bindings(
    environment: WorkspaceMutationPolicyEnvironment | None,
) -> tuple[tuple[str, str], ...]:
    if environment is not None:
        raw_bindings: list[tuple[dict[str, object], str]] = []
        for arguments in WORKSPACE_ITEM_GROUNDING_ARGUMENTS:
            if arguments.get("kind") != "task":
                continue
            try:
                observation = environment.search_workspace_items(**arguments)
            except KeyError:
                continue
            item_id = observation.get("item_id")
            if isinstance(item_id, str):
                raw_bindings.append((dict(arguments), item_id))
    else:
        raw_bindings = [
            (
                {"query": "launch plan", "kind": "task"},
                "task_launch_plan",
            ),
            (
                {"query": "metrics dashboard", "kind": "task"},
                "task_metrics_review",
            ),
            (
                {"query": "research notes", "kind": "task"},
                "task_research_notes",
            ),
        ]
    bindings = {
        (canonical_hash(arguments), canonical_hash(item_id))
        for arguments, item_id in raw_bindings
    }
    return tuple(sorted(bindings))


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
    elif _workspace_action_is_negated(request, instruction):
        action_reason = "action_negated"
        action_outcome = "unsupported"
    elif any(
        phrase in instruction
        for phrase in (
            "if appropriate",
            "if needed",
            "maybe add",
            "maybe create",
            "consider adding",
            "consider creating",
        )
    ):
        action_reason = "conditional_authorization_ambiguous"
        action_outcome = "uncertain"
    elif not _workspace_action_is_supported(request):
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
            if _workspace_observation_is_semantically_supported(request, name):
                outcome = "supported"
                reason = "observation_reference_supported"
            else:
                outcome = "unsupported"
                reason = "provenance_mismatch"
        elif origin == "instruction":
            value = str(request.argument_values.get(name, ""))
            evidence_text = str(request.argument_evidence.get(name, ""))
            if value.lower() in instruction and _literal_argument_is_supported(
                value,
                instruction,
            ):
                outcome = "supported"
                reason = "argument_literal_supported"
            elif value.lower() in instruction:
                outcome = "unsupported"
                reason = "argument_not_supported"
            elif _workspace_argument_is_semantically_supported(
                request,
                name=name,
                value=value,
                evidence_text=evidence_text,
            ):
                outcome = "supported"
                reason = "argument_semantic_supported"
            else:
                overlap = _semantic_token_overlap(value, evidence_text)
                if (
                    request.action_type == "workspace_comment_add"
                    and overlap >= 2
                ):
                    outcome = "supported"
                    reason = "argument_semantic_supported"
                elif (
                    request.action_type == "workspace_comment_add"
                    and overlap == 1
                ):
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
    model="deterministic_workspace_mutation_judge_v1",
)


def _workspace_action_is_supported(request: SemanticJudgeRequest) -> bool:
    tokens = _semantic_tokens(request.action_evidence_text)
    semantics = _WORKSPACE_ACTION_SEMANTICS.get(request.action_type)
    return bool(
        semantics
        and tokens & semantics.entity_tokens
        and tokens & semantics.authorization_verbs
    )


def _workspace_action_is_negated(
    request: SemanticJudgeRequest,
    instruction: str,
) -> bool:
    semantics = _WORKSPACE_ACTION_SEMANTICS.get(request.action_type)
    if semantics is None:
        return False
    return re.search(
        (
            rf"\b(?:do not|don't|without)\b[^.]{{0,80}}"
            rf"\b{semantics.negation_target_pattern}\b"
        ),
        instruction,
    ) is not None


def _literal_argument_is_supported(value: str, instruction: str) -> bool:
    start = instruction.index(value.lower())
    sentence_start = max(
        instruction.rfind(".", 0, start),
        instruction.rfind(";", 0, start),
        start - 48,
    )
    prefix = instruction[sentence_start + 1:start]
    return re.search(
        r"\b(?:do\s+not|don't|not\s+to|without)\b[^.]{0,40}$",
        prefix,
    ) is None


def _workspace_argument_is_semantically_supported(
    request: SemanticJudgeRequest,
    *,
    name: str,
    value: str,
    evidence_text: str,
) -> bool:
    value_tokens = _semantic_tokens(value)
    if request.action_type == "workspace_task_create" and name == "title":
        value_tokens -= {"add", "create", "item", "make", "new", "prepare", "task"}
    evidence_tokens = _semantic_tokens(evidence_text)
    return bool(value_tokens) and value_tokens.issubset(evidence_tokens)


def _workspace_observation_is_semantically_supported(
    request: SemanticJudgeRequest,
    name: str,
) -> bool:
    if request.action_type != "workspace_task_create" or name != "project_id":
        return True
    evidence = request.argument_evidence.get(name)
    if not isinstance(evidence, Mapping):
        return False
    source_arguments = evidence.get("source_arguments")
    if not isinstance(source_arguments, Mapping):
        return False
    project_id = request.argument_values.get(name)
    if not isinstance(project_id, str) or not project_id.strip():
        return False
    expected_tokens = _semantic_tokens(project_id) - {"project"}
    if not expected_tokens:
        return False
    mentions: list[WorkspaceProjectMention] = []
    for clause in re.split(r"[.,;]", request.instruction.lower()):
        token_sequence = re.findall(r"[a-z0-9]+", clause)
        project_indexes = [
            index
            for index, token in enumerate(token_sequence)
            if token == "project"
        ]
        is_negated = re.search(
            r"\b(?:avoid|do\s+not|don't|instead\s+of|without)\b",
            clause,
        ) is not None
        is_lookup_subject = re.search(
            r"\b(?:find|locate|look\s+up|retrieve|search)\b",
            clause,
        ) is not None
        action_tokens = _WORKSPACE_ACTION_SEMANTICS[
            "workspace_task_create"
        ].authorization_verbs
        has_creation_action = bool(set(token_sequence) & action_tokens)
        for project_index in project_indexes:
            project_phrase_tokens = set(
                token_sequence[max(0, project_index - 4):project_index]
                + token_sequence[project_index + 1:project_index + 5]
            )
            query_matches = all(
                _project_binding_token_supported(
                    token,
                    project_phrase_tokens,
                )
                for token in expected_tokens
            )
            preceding_tokens = set(
                token_sequence[max(0, project_index - 8):project_index]
            )
            mentions.append(
                WorkspaceProjectMention(
                    query_matches=query_matches,
                    is_destination=(
                        has_creation_action
                        and bool(preceding_tokens & {"for", "in", "under"})
                    ),
                    is_lookup_subject=is_lookup_subject,
                    is_negated=is_negated,
                )
            )
    destinations = [
        mention
        for mention in mentions
        if mention.is_destination and not mention.is_negated
    ]
    if destinations:
        return any(mention.query_matches for mention in destinations)
    return any(
        mention.query_matches
        and mention.is_lookup_subject
        and not mention.is_negated
        for mention in mentions
    )


def _project_binding_token_supported(
    expected: str,
    observed: set[str],
) -> bool:
    return expected in observed


def _semantic_token_overlap(left: str, right: str) -> int:
    stopwords = {"a", "an", "and", "the", "to", "for", "of", "add", "added"}
    left_tokens = _semantic_tokens(left) - stopwords
    right_tokens = _semantic_tokens(right) - stopwords
    return len(left_tokens & right_tokens)


def _semantic_tokens(value: str) -> set[str]:
    aliases = {
        "check": "review",
        "checking": "review",
        "current": "this",
        "urgent": "high",
    }
    return {
        aliases.get(token, token)
        for token in re.findall(r"[a-z0-9]+", value.lower().replace("_", " "))
    }


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
                "Find the Alpha Launch project and create a high-priority "
                "launch checklist task due this week."
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
        prepare_workspace_candidate(candidate)
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
    source_index, source_step = _policy_step(policy, "search_workspace_items")
    mutation_index, mutation_step = _policy_step(policy, "add_workspace_comment")
    return _with_workspace_authorization(
        candidate,
        policy=policy,
        instruction=instruction,
        action_type="workspace_comment_add",
        mutation_index=mutation_index,
        action_evidence=_instruction_regex_evidence(
            instruction,
            (
                r"\b(?:add|write|create|leave|post)\b"
                r"[^.]{0,180}\bcomment\b[^.]*"
            ),
            reference_id="instruction.action",
        ),
        arguments=[
            {
                "name": "comment",
                "origin": "instruction",
                "support": "semantic",
                "evidence": _instruction_regex_evidence(
                    instruction,
                    (
                        r"\b(?:add|write|create|leave|post)\b"
                        r"[^.]{0,180}\bcomment\b[^.]*"
                    ),
                    reference_id="instruction.comment",
                ),
            },
            _observation_argument(
                name="task_id",
                source_index=source_index,
                source_step=source_step,
                source_field="item_id",
                mutation_value=mutation_step.arguments.get("task_id"),
                reference_id="observation.selected_task",
                binding_evidence=_source_binding_evidence(
                    instruction,
                    source_step=source_step,
                    fallback_pattern=r"[^.]{0,180}\b(?:task|item)\b[^.]*",
                    reference_id="instruction.selected_task",
                ),
            ),
        ],
    )


def prepare_workspace_candidate(candidate: CandidateTask) -> CandidateTask:
    task_type = candidate.constraints.get("task_type")
    if task_type == "workspace_task_creation":
        return propose_workspace_task_authorization(candidate)
    if task_type == "workspace_comment_update":
        return propose_workspace_comment_authorization(candidate)
    return candidate


def propose_workspace_task_authorization(candidate: CandidateTask) -> CandidateTask:
    policy = scripted_workspace_solution_policy(candidate)
    instruction = normalized_instruction(candidate.instruction)
    source_index, source_step = _policy_step(policy, "search_workspace_items")
    mutation_index, mutation_step = _policy_step(policy, "create_workspace_task")
    return _with_workspace_authorization(
        candidate,
        policy=policy,
        instruction=instruction,
        action_type="workspace_task_create",
        mutation_index=mutation_index,
        action_evidence=_instruction_regex_evidence(
            instruction,
            (
                r"\b(?:create|make|add|prepare)\b"
                r"[^.]{0,180}\b(?:task|item)\b[^.]*"
            ),
            reference_id="instruction.action",
        ),
        arguments=[
            _instruction_argument(
                instruction,
                name="title",
                value=mutation_step.arguments.get("title"),
                fallback_pattern=(
                    r"\b(?:create|make|add|prepare)\b"
                    r"[^.]{0,180}\b(?:task|item)\b[^.]*"
                ),
            ),
            _instruction_argument(
                instruction,
                name="priority",
                value=mutation_step.arguments.get("priority"),
                fallback_pattern=r"\b(?:low|medium|high|urgent)\b[^.]*",
            ),
            _instruction_argument(
                instruction,
                name="due_label",
                value=mutation_step.arguments.get("due_label"),
                fallback_pattern=(
                    r"\b(?:due|deadline|today|tomorrow|this|next)\b[^.]*"
                ),
            ),
            _observation_argument(
                name="project_id",
                source_index=source_index,
                source_step=source_step,
                source_field="project_id",
                mutation_value=mutation_step.arguments.get("project_id"),
                reference_id="observation.selected_project",
                binding_evidence=_source_binding_evidence(
                    instruction,
                    source_step=source_step,
                    fallback_pattern=r"[^.]{0,180}\bproject\b[^.]*",
                    reference_id="instruction.selected_project",
                ),
            ),
        ],
    )


def _with_workspace_authorization(
    candidate: CandidateTask,
    *,
    policy: SolutionPolicy,
    instruction: str,
    action_type: str,
    mutation_index: int,
    action_evidence: dict[str, object],
    arguments: list[dict[str, object]],
) -> CandidateTask:
    record: dict[str, object] = {
        "schema_version": "mutation_authorization_record_v1",
        "instruction_hash": canonical_hash(instruction),
        "policy_hash": policy_hash(policy),
        "actions": [
            {
                "action_ref": f"policy.steps.{mutation_index}",
                "action_type": action_type,
                "instruction_evidence": action_evidence,
                "arguments": arguments,
            }
        ],
    }
    return replace(candidate, mutation_authorization=record)


def _observation_argument(
    *,
    name: str,
    source_index: int,
    source_step: ToolStep,
    source_field: str,
    mutation_value: object,
    reference_id: str,
    binding_evidence: dict[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "origin": "tool_observation",
        "evidence": {
            "reference_id": reference_id,
            "kind": "tool_observation",
            "source_action_ref": f"policy.steps.{source_index}",
            "source_field": source_field,
            "source_arguments_hash": canonical_hash(source_step.arguments),
            "value_hash": canonical_hash(mutation_value),
            "binding_instruction_evidence": binding_evidence,
        },
    }


def _policy_step(policy: SolutionPolicy, tool_name: str) -> tuple[int, ToolStep]:
    for index, step in enumerate(policy.steps):
        if step.tool_name == tool_name:
            return index, step
    raise ValueError(f"workspace mutation policy requires {tool_name}")


def _instruction_argument(
    instruction: str,
    *,
    name: str,
    value: object,
    fallback_pattern: str,
) -> dict[str, object]:
    literal = str(value) if isinstance(value, str) else ""
    literal_match = bool(literal and literal.lower() in instruction.lower())
    return {
        "name": name,
        "origin": "instruction",
        "support": "literal" if literal_match else "semantic",
        "evidence": (
            _instruction_literal_evidence(
                instruction,
                literal,
                reference_id=f"instruction.{name}",
            )
            if literal_match
            else _instruction_regex_evidence(
                instruction,
                fallback_pattern,
                reference_id=f"instruction.{name}",
            )
        ),
    }


def _source_binding_evidence(
    instruction: str,
    *,
    source_step: ToolStep,
    fallback_pattern: str,
    reference_id: str,
) -> dict[str, object]:
    spans: list[tuple[int, int]] = []
    lowered = instruction.lower()
    for value in source_step.arguments.values():
        literal = value if isinstance(value, str) else ""
        if not literal or literal.lower() not in lowered:
            return _instruction_regex_evidence(
                instruction,
                fallback_pattern,
                reference_id=reference_id,
            )
        start = lowered.index(literal.lower())
        spans.append((start, start + len(literal)))
    if not spans:
        return _instruction_regex_evidence(
            instruction,
            fallback_pattern,
            reference_id=reference_id,
        )
    return _instruction_evidence(
        instruction,
        min(start for start, _ in spans),
        max(end for _, end in spans),
        reference_id=reference_id,
    )


def _instruction_regex_evidence(
    instruction: str,
    pattern: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    match = re.search(pattern, instruction, re.IGNORECASE)
    start, end = match.span() if match is not None else (0, min(1, len(instruction)))
    return _instruction_evidence(
        instruction,
        start,
        end,
        reference_id=reference_id,
    )


def _instruction_literal_evidence(
    instruction: str,
    text: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    start = instruction.lower().index(text.lower())
    return _instruction_evidence(
        instruction,
        start,
        start + len(text),
        reference_id=reference_id,
    )


def _instruction_evidence(
    instruction: str,
    start: int,
    end: int,
    *,
    reference_id: str,
) -> dict[str, object]:
    text = instruction[start:end]
    return {
        "reference_id": reference_id,
        "kind": "instruction_span",
        "start": start,
        "end": end,
        "evidence_hash": canonical_hash(text),
    }
