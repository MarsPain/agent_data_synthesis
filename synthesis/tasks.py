from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from synthesis.llm import LLMProviderError
from synthesis.roles import (
    RoleRegistry,
    TASK_EDITOR_ROLE,
    TASK_GENERATION_ROLE,
    TASK_SUGGESTER_ROLE,
    default_role_registry,
)
from synthesis.seeds import DomainSeed, deterministic_seed_transformations

if TYPE_CHECKING:
    from synthesis.domain_pack import DomainCapabilityReference


@dataclass(frozen=True)
class TaskSuggestion:
    suggestion_id: str
    transformation_id: str
    target_taxonomy_node: str
    intent: str
    required_capabilities: tuple[str, ...]
    target_tools: tuple[str, ...]
    constraints: dict[str, object]
    expected_verification: str
    outcome: str
    lineage: dict[str, object]
    rejection_reason: str | None = None
    seed_transformation: dict[str, object] | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": "task_suggestion_v1",
            "suggestion_id": self.suggestion_id,
            "transformation_id": self.transformation_id,
            "target_taxonomy_node": self.target_taxonomy_node,
            "intent": self.intent,
            "required_capabilities": list(self.required_capabilities),
            "target_tools": list(self.target_tools),
            "constraints": self.constraints,
            "expected_verification": self.expected_verification,
            "outcome": self.outcome,
            "lineage": dict(self.lineage),
        }
        if self.rejection_reason is not None:
            record["rejection_reason"] = self.rejection_reason
        return record


@dataclass(frozen=True)
class EditedTask:
    suggestion_id: str
    editor_action: str
    lineage: dict[str, object]
    candidate: CandidateTask | None = None
    rejection: dict[str, object] | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": "edited_task_v1",
            "suggestion_id": self.suggestion_id,
            "editor_action": self.editor_action,
            "lineage": dict(self.lineage),
        }
        if self.candidate is not None:
            record["candidate"] = _candidate_mapping(self.candidate)
        if self.rejection is not None:
            record["rejection"] = dict(self.rejection)
        return record


@dataclass(frozen=True)
class TaskExpansionResult:
    candidates: list[CandidateTask]
    rejected_suggestions: list[TaskSuggestion]
    rejected_edits: list[EditedTask] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateTask:
    candidate_id: str
    instruction: str
    constraints: dict[str, object]
    difficulty: dict[str, object]
    tool_name: str
    arguments: dict[str, object]
    expected_answer: str
    seed_ids: tuple[str, ...]
    generation_lineage: dict[str, object] | None = None
    expected_state: dict[str, object] | None = None
    branch_plan: dict[str, object] | None = None
    seed_transformation: dict[str, object] | None = None
    task_suggester_lineage: dict[str, object] | None = None
    task_editor_lineage: dict[str, object] | None = None
    editor_action: str | None = None
    mutation_authorization: dict[str, object] | None = None
    capability_references: tuple["DomainCapabilityReference", ...] = ()

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "candidate_id": self.candidate_id,
            "instruction": self.instruction,
            "constraints": self.constraints,
            "difficulty": self.difficulty,
        }
        if self.branch_plan is not None:
            record["branch_plan"] = self.branch_plan
        return record

    def contract(self) -> "TaskContract":
        from synthesis.task_contracts import TaskContract, task_contract_from_candidate

        return task_contract_from_candidate(self)


def build_contacts_generation_spec(
    environment: object,
    registry: object,
    *,
    domain_plan: object | None = None,
):
    from synthesis.domain_generation import (
        DOMAIN_GENERATION_SPEC_VERSION,
        MAX_CANDIDATES_PER_CALL,
        SYNTHETIC_CONTEXT_POLICY,
        DomainGenerationSpec,
        DomainTaskTypeSpec,
        ExpectedStateGroundingBinding,
        validate_domain_generation_spec,
    )
    from synthesis.domain_pack import DomainPlan, initial_domain_pack_registry

    if domain_plan is not None and not isinstance(domain_plan, DomainPlan):
        raise ValueError("domain_plan must be a DomainPlan")
    if getattr(environment, "source_input", None) is not None:
        raise ValueError("source_backed_remote_context_not_allowed")
    descriptor = initial_domain_pack_registry().descriptor_for("contacts")
    projections = {
        projection.task_type_key: projection
        for projection in descriptor.task_capability_projections
    }
    contacts_capabilities = tuple(
        sorted(
            descriptor.capability_references,
            key=lambda reference: reference.capability_key,
        )
    )
    plan_bound = domain_plan is not None
    names = str(environment.list_contact_names()["contacts"]).split(", ")
    contacts = [
        {
            "primary_arguments": {"name": name},
            "observation": environment.lookup_email(name),
        }
        for name in names
    ]
    spec = DomainGenerationSpec(
        schema_version=DOMAIN_GENERATION_SPEC_VERSION,
        domain_id="contacts_fixture",
        task_types=(
            DomainTaskTypeSpec(
                "contact_lookup",
                ("lookup_contact_email",),
                required_capabilities=("contact_lookup",),
                capability_references=(
                    projections["contact_lookup"].capability_references
                    if plan_bound
                    else ()
                ),
                final_answer_fields=("email",),
            ),
            DomainTaskTypeSpec(
                "contact_followup",
                ("lookup_contact_email", "record_contact_followup"),
                ("contact_followup",),
                required_capabilities=(
                    ("contact_lookup", "followup_recording")
                    if plan_bound
                    else ("contact_lookup", "contact_followup")
                ),
                capability_references=(
                    projections["contact_followup"].capability_references
                    if plan_bound
                    else ()
                ),
                expected_state_tool="record_contact_followup",
                final_answer_fields=("email",),
                expected_state_grounding_bindings=(
                    ExpectedStateGroundingBinding("name", "name", "exact"),
                    ExpectedStateGroundingBinding("note", "email", "contains"),
                ),
            ),
        ),
        tools=tuple(registry.export()),
        grounding_context={"contacts": contacts},
        context_policy=SYNTHETIC_CONTEXT_POLICY,
        max_candidates_per_call=MAX_CANDIDATES_PER_CALL,
        grounding_window_size=2,
        domain_pack_reference=(
            domain_plan.domain_pack_reference if plan_bound else None
        ),
        plan_id=domain_plan.plan_id if plan_bound else None,
        plan_hash=domain_plan.plan_hash if plan_bound else None,
        capability_references=contacts_capabilities if plan_bound else (),
        held_out_capability_references=(
            tuple(domain_plan.held_out_capability_references)
            if plan_bound
            else ()
        ),
        recovery_capability_references=(
            tuple(
                reference
                for reference in contacts_capabilities
                if reference.capability_key == "contact_lookup_recovery"
            )
            if plan_bound
            else ()
        ),
    )
    validate_domain_generation_spec(spec)
    return spec


def generate_foundation_candidates(
    seed: DomainSeed,
    *,
    include_branching: bool = False,
) -> list[CandidateTask]:
    common_difficulty = {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }
    candidates = [
        CandidateTask(
            candidate_id="candidate_contacts_alice",
            instruction="Find Alice Zhang's email address using the contact database.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=common_difficulty,
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_contacts_ben_bad_expectation",
            instruction="Find Ben Carter's email address using the contact database.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=common_difficulty,
            tool_name="lookup_contact_email",
            arguments={"name": "Ben Carter"},
            expected_answer="ben@example.test",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_contacts_alice_followup",
            instruction=(
                "Find Alice Zhang's email address and record that a follow-up "
                "email should be sent."
            ),
            constraints={
                "task_type": "contact_followup",
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
            },
            difficulty={
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
            expected_state={
                "contact_followup": {
                    "name": "Alice Zhang",
                    "note": "Send follow-up email to alice.zhang@example.test.",
                }
            },
        ),
    ]
    if include_branching:
        candidates.append(_branching_contact_candidate(seed))
    return order_candidates_by_curriculum(
        _attach_contact_followup_authorizations(
            _attach_local_generation_lineage(candidates)
        )
    )


def generate_scale_probe_candidates(
    seed: DomainSeed,
    target_candidate_count: int,
) -> list[CandidateTask]:
    if target_candidate_count <= 0:
        raise ValueError("target_candidate_count must be positive")

    candidates = [
        _scale_probe_candidate(seed, index)
        for index in range(1, target_candidate_count + 1)
    ]
    return order_candidates_by_curriculum(
        _attach_contact_followup_authorizations(candidates)
    )


def generate_llm_backed_candidates(
    seed: DomainSeed,
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> list[CandidateTask]:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        TASK_GENERATION_ROLE,
        client,
        _candidate_generation_prompt(seed),
    )
    raw_candidates = result.content.get("candidates")
    if not isinstance(raw_candidates, list):
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class="TypeError",
            retryable=False,
            retry_count=_lineage_retry_count(result.lineage),
            lineage=result.lineage,
        )

    candidates: list[CandidateTask] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="TypeError",
                retryable=False,
                retry_count=_lineage_retry_count(result.lineage),
                lineage=result.lineage,
            )
        candidates.append(_candidate_from_mapping(seed, raw_candidate, result.lineage))
    return candidates


def generate_deterministic_task_expansion(seed: DomainSeed) -> TaskExpansionResult:
    candidates: list[CandidateTask] = []
    rejected_suggestions: list[TaskSuggestion] = []
    for transformation in deterministic_seed_transformations(seed):
        transformation_record = transformation.export()
        suggestion = _deterministic_suggestion_for_transformation(transformation_record)
        if suggestion.outcome == "rejected":
            rejected_suggestions.append(suggestion)
            continue
        edited = _deterministic_edit_suggestion(seed, transformation_record, suggestion)
        if edited.candidate is not None:
            candidates.append(edited.candidate)
    return TaskExpansionResult(
        candidates=order_candidates_by_curriculum(candidates),
        rejected_suggestions=rejected_suggestions,
    )


def generate_llm_backed_task_suggestions(
    seed: DomainSeed,
    transformation: dict[str, object],
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> list[TaskSuggestion]:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        TASK_SUGGESTER_ROLE,
        client,
        _task_suggestion_prompt(seed, transformation),
    )
    raw_suggestions = result.content.get("suggestions")
    if not isinstance(raw_suggestions, list):
        raise _llm_schema_error(result.lineage, TypeError("suggestions must be a list"))
    try:
        return [
            _suggestion_from_mapping(transformation, raw_suggestion, result.lineage)
            for raw_suggestion in raw_suggestions
        ]
    except (TypeError, ValueError, KeyError) as exc:
        raise _llm_schema_error(result.lineage, exc) from exc


def generate_llm_backed_edited_task(
    seed: DomainSeed,
    transformation: dict[str, object],
    suggestion: TaskSuggestion,
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> EditedTask:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        TASK_EDITOR_ROLE,
        client,
        _task_editor_prompt(seed, transformation, suggestion),
    )
    raw_edited = result.content.get("edited_task")
    if not isinstance(raw_edited, dict):
        raise _llm_schema_error(result.lineage, TypeError("edited_task must be an object"))
    try:
        return _edited_task_from_mapping(
            seed=seed,
            transformation=transformation,
            suggestion=suggestion,
            raw=raw_edited,
            lineage=result.lineage,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise _llm_schema_error(result.lineage, exc) from exc


def candidate_from_mapping(
    raw: dict[str, Any],
    *,
    seed_ids: tuple[str, ...],
    generation_lineage: dict[str, object] | None = None,
    seed_transformation: dict[str, object] | None = None,
    task_suggester_lineage: dict[str, object] | None = None,
    task_editor_lineage: dict[str, object] | None = None,
    editor_action: str | None = None,
) -> CandidateTask:
    difficulty = _normalize_difficulty(raw["difficulty"])
    constraints = _normalize_constraints(raw["constraints"])
    arguments = raw["arguments"]
    if not isinstance(arguments, dict):
        raise TypeError("candidate arguments must be an object")
    expected_state = raw.get("expected_state")
    if expected_state is not None and not isinstance(expected_state, dict):
        raise TypeError("candidate expected_state must be an object")
    branch_plan = raw.get("branch_plan")
    if branch_plan is not None and not isinstance(branch_plan, dict):
        raise TypeError("candidate branch_plan must be an object")

    candidate = CandidateTask(
        candidate_id=str(raw["candidate_id"]),
        instruction=str(raw["instruction"]),
        constraints=constraints,
        difficulty=difficulty,
        tool_name=_normalize_tool_name(str(raw["tool_name"])),
        arguments=arguments,
        expected_answer=str(raw["expected_answer"]),
        seed_ids=seed_ids,
        generation_lineage=dict(generation_lineage) if generation_lineage else None,
        expected_state=expected_state,
        branch_plan=branch_plan,
        seed_transformation=dict(seed_transformation) if seed_transformation else None,
        task_suggester_lineage=(
            dict(task_suggester_lineage) if task_suggester_lineage else None
        ),
        task_editor_lineage=dict(task_editor_lineage) if task_editor_lineage else None,
        editor_action=editor_action,
    )
    return _attach_contact_followup_authorization(candidate)


def _deterministic_suggestion_for_transformation(
    transformation: dict[str, object],
) -> TaskSuggestion:
    target = str(transformation["target_taxonomy_node"])
    lineage = local_task_suggester_lineage()
    if target == "contact_followup":
        return TaskSuggestion(
            suggestion_id="suggestion_contact_followup_ben",
            transformation_id=str(transformation["transformation_id"]),
            target_taxonomy_node=target,
            intent="Find Ben Carter's email and record a follow-up.",
            required_capabilities=("lookup_contact_email", "record_contact_followup"),
            target_tools=("lookup_contact_email", "record_contact_followup"),
            constraints={"task_type": "contact_followup"},
            expected_verification="exact_answer_and_state_change",
            outcome="accepted",
            lineage=lineage,
            seed_transformation=transformation,
        )
    return TaskSuggestion(
        suggestion_id="suggestion_contacts_unsupported_network",
        transformation_id=str(transformation["transformation_id"]),
        target_taxonomy_node=target,
        intent="Research a missing contact from the network.",
        required_capabilities=("network_contact_research",),
        target_tools=("network_search",),
        constraints={"task_type": "network_contact_research"},
        expected_verification="not_supported_by_contacts_fixture",
        outcome="rejected",
        lineage=lineage,
        rejection_reason="unsupported_taxonomy_node",
        seed_transformation=transformation,
    )


def _deterministic_edit_suggestion(
    seed: DomainSeed,
    transformation: dict[str, object],
    suggestion: TaskSuggestion,
) -> EditedTask:
    lineage = local_task_editor_lineage(editor_action="created_candidate")
    raw_candidate = {
        "candidate_id": "candidate_expanded_ben_followup",
        "instruction": "Find Ben Carter's email address and record a follow-up note.",
        "constraints": {
            "task_type": "contact_followup",
            "required_tools": ["lookup_contact_email", "record_contact_followup"],
            "taxonomy_node": suggestion.target_taxonomy_node,
            "source": "task_expansion",
        },
        "difficulty": {
            "level": "medium",
            "tool_count": 2,
            "constraint_count": 2,
            "state_changes": 1,
            "ambiguity": "none",
            "recovery_paths": 0,
        },
        "tool_name": "lookup_contact_email",
        "arguments": {"name": "Ben Carter"},
        "expected_answer": "ben.carter@example.test",
        "expected_state": {
            "contact_followup": {
                "name": "Ben Carter",
                "note": "Send follow-up email to ben.carter@example.test.",
            }
        },
    }
    candidate = candidate_from_mapping(
        raw_candidate,
        seed_ids=(seed.seed_id,),
        generation_lineage=local_task_generation_lineage(),
        seed_transformation=transformation,
        task_suggester_lineage=suggestion.lineage,
        task_editor_lineage=lineage,
        editor_action="created_candidate",
    )
    return EditedTask(
        suggestion_id=suggestion.suggestion_id,
        editor_action="created_candidate",
        lineage=lineage,
        candidate=candidate,
    )


def _branching_contact_candidate(seed: DomainSeed) -> CandidateTask:
    return CandidateTask(
        candidate_id="candidate_contacts_alice_branch_fallback",
        instruction=(
            "Find Alice Zhang's email address. If an abbreviated lookup fails, "
            "fall back to the full contact name."
        ),
        constraints={
            "task_type": "contact_branch_fallback",
            "required_tools": ["lookup_contact_email"],
            "expected_branch": "fallback_full_name",
        },
        difficulty={
            "level": "medium",
            "tool_count": 1,
            "constraint_count": 2,
            "state_changes": 0,
            "ambiguity": "recoverable_short_name",
            "recovery_paths": 1,
            "branch_depth": 2,
            "fallback_count": 1,
        },
        tool_name="lookup_contact_email",
        arguments={"name": "Alice"},
        expected_answer="alice.zhang@example.test",
        seed_ids=(seed.seed_id,),
        branch_plan={
            "schema_version": "branch_plan_v1",
            "plan_id": "branch_plan_candidate_contacts_alice_fallback",
            "max_depth": 2,
            "branches": [
                {
                    "branch_id": "direct_short_name",
                    "node_type": "attempt",
                    "parent_id": None,
                    "condition": "Try the abbreviated name first.",
                    "steps": [
                        {
                            "tool_name": "lookup_contact_email",
                            "arguments": {"name": "Alice"},
                        }
                    ],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "fallback_on_failure",
                },
                {
                    "branch_id": "fallback_full_name",
                    "node_type": "fallback",
                    "parent_id": "direct_short_name",
                    "condition": "Use the full name after the abbreviated lookup fails.",
                    "steps": [
                        {
                            "tool_name": "lookup_contact_email",
                            "arguments": {"name": "Alice Zhang"},
                        }
                    ],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "accept_on_success",
                },
            ],
        },
    )


def _scale_probe_candidate(seed: DomainSeed, index: int) -> CandidateTask:
    candidate_id = f"candidate_scale_probe_{index:04d}"
    probe_case = (index - 1) % 6
    lineage = local_scale_probe_generation_lineage()
    if probe_case == 0:
        return CandidateTask(
            candidate_id=candidate_id,
            instruction=f"Find Alice Zhang's email address for scale probe item {index}.",
            constraints={
                "task_type": "contact_lookup",
                "probe_case": "single_step_lookup",
                "must_use_tool": "lookup_contact_email",
            },
            difficulty={
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 1,
                "state_changes": 0,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
            generation_lineage=lineage,
        )
    if probe_case == 1:
        return CandidateTask(
            candidate_id=candidate_id,
            instruction=f"Find Ben Carter's email address for scale probe item {index}.",
            constraints={
                "task_type": "contact_lookup",
                "probe_case": "verification_failure",
                "must_use_tool": "lookup_contact_email",
            },
            difficulty={
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 1,
                "state_changes": 0,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Ben Carter"},
            expected_answer="ben@example.test",
            seed_ids=(seed.seed_id,),
            generation_lineage=lineage,
        )
    if probe_case == 2:
        return CandidateTask(
            candidate_id=candidate_id,
            instruction=(
                f"Find Alice Zhang's email address and record a follow-up "
                f"for scale probe item {index}."
            ),
            constraints={
                "task_type": "contact_followup",
                "probe_case": "multi_step_followup",
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
            },
            difficulty={
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
            generation_lineage=lineage,
            expected_state={
                "contact_followup": {
                    "name": "Alice Zhang",
                    "note": "Send follow-up email to alice.zhang@example.test.",
                }
            },
        )
    if probe_case == 3:
        return CandidateTask(
            candidate_id=candidate_id,
            instruction="Find Alice Zhang's email address for scale probe duplicate.",
            constraints={
                "task_type": "contact_lookup",
                "probe_case": "duplicate_lookup",
                "must_use_tool": "lookup_contact_email",
            },
            difficulty={
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 1,
                "state_changes": 0,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
            generation_lineage=lineage,
        )
    if probe_case == 4:
        return CandidateTask(
            candidate_id=candidate_id,
            instruction=(
                f"Return a supervisor-only contact answer after looking up "
                f"Alice Zhang for scale probe item {index}."
            ),
            constraints={
                "task_type": "contact_lookup",
                "probe_case": "logical_support_failure",
                "must_use_tool": "lookup_contact_email",
            },
            difficulty={
                "level": "medium",
                "tool_count": 1,
                "constraint_count": 2,
                "state_changes": 0,
                "ambiguity": "unsupported_final_answer",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="escalation-needed@example.test",
            seed_ids=(seed.seed_id,),
            generation_lineage=lineage,
        )
    return CandidateTask(
        candidate_id=candidate_id,
        instruction=f"Find Ben Carter's email address and record a follow-up for probe item {index}.",
        constraints={
            "task_type": "contact_followup",
            "probe_case": "stateful_followup",
            "required_tools": ["lookup_contact_email", "record_contact_followup"],
        },
        difficulty={
            "level": "medium",
            "tool_count": 2,
            "constraint_count": 2,
            "state_changes": 1,
            "ambiguity": "none",
            "recovery_paths": 0,
        },
        tool_name="lookup_contact_email",
        arguments={"name": "Ben Carter"},
        expected_answer="ben.carter@example.test",
        seed_ids=(seed.seed_id,),
        generation_lineage=lineage,
        expected_state={
            "contact_followup": {
                "name": "Ben Carter",
                "note": "Send follow-up email to ben.carter@example.test.",
            }
        },
    )


def _candidate_generation_prompt(seed: DomainSeed) -> str:
    taxonomy = ", ".join(seed.task_taxonomy)
    return (
        "Generate candidate Agent data synthesis tasks for a small executable domain.\n"
        f"Domain: {seed.domain}\n"
        f"Description: {seed.description}\n"
        f"Task taxonomy: {taxonomy}\n"
        "Available tools: lookup_contact_email(name: string) -> contact email.\n"
        "Available contacts and expected emails: "
        "Alice Zhang -> alice.zhang@example.test; "
        "Ben Carter -> ben.carter@example.test.\n"
        "Return JSON with a candidates array. Each candidate must include "
        "candidate_id, instruction, constraints, difficulty, tool_name, "
        "arguments, and expected_answer. difficulty must be an object with "
        "level, tool_count, constraint_count, state_changes, ambiguity, "
        "and recovery_paths. "
        "constraints and arguments must be JSON objects. tool_name must be "
        "lookup_contact_email. arguments.name must be one of the full contact "
        "names above. expected_answer must be the exact matching email above."
    )


def _candidate_from_mapping(
    seed: DomainSeed,
    raw: dict[str, Any],
    generation_lineage: dict[str, object],
) -> CandidateTask:
    try:
        return candidate_from_mapping(
            raw,
            seed_ids=(seed.seed_id,),
            generation_lineage=generation_lineage,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class=type(exc).__name__,
            retryable=False,
            retry_count=_lineage_retry_count(generation_lineage),
            lineage=generation_lineage,
        ) from exc


def _normalize_difficulty(raw_difficulty: Any) -> dict[str, object]:
    if isinstance(raw_difficulty, dict):
        difficulty = dict(raw_difficulty)
        difficulty.setdefault("level", "unspecified")
        difficulty.setdefault("tool_count", 1)
        difficulty.setdefault("constraint_count", 0)
        difficulty.setdefault("state_changes", 0)
        difficulty.setdefault("ambiguity", "unspecified")
        difficulty.setdefault("recovery_paths", 0)
        return difficulty
    if isinstance(raw_difficulty, str):
        return {
            "level": raw_difficulty,
            "tool_count": 1,
            "constraint_count": 0,
            "state_changes": 0,
            "ambiguity": "unspecified",
            "recovery_paths": 0,
        }
    raise ValueError("candidate difficulty must be an object")


def order_candidates_by_curriculum(candidates: list[CandidateTask]) -> list[CandidateTask]:
    return sorted(candidates, key=_curriculum_sort_key)


def _curriculum_sort_key(candidate: CandidateTask) -> tuple[int, int, int, int, int, str]:
    difficulty = candidate.difficulty
    level_rank = {"easy": 0, "medium": 1, "hard": 2}.get(str(difficulty.get("level")), 99)
    return (
        level_rank,
        _int_difficulty(difficulty.get("tool_count")),
        _int_difficulty(difficulty.get("constraint_count")),
        _int_difficulty(difficulty.get("state_changes")),
        _int_difficulty(difficulty.get("recovery_paths")),
        candidate.candidate_id,
    )


def _int_difficulty(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _normalize_constraints(raw_constraints: Any) -> dict[str, object]:
    if isinstance(raw_constraints, dict):
        return raw_constraints
    if isinstance(raw_constraints, str):
        return {"description": raw_constraints}
    raise ValueError("candidate constraints must be an object")


def _normalize_tool_name(raw_tool_name: str) -> str:
    aliases = {
        "lookup_contact": "lookup_contact_email",
        "lookup_email": "lookup_contact_email",
        "contact_lookup": "lookup_contact_email",
    }
    return aliases.get(raw_tool_name, raw_tool_name)


def _attach_local_generation_lineage(candidates: list[CandidateTask]) -> list[CandidateTask]:
    lineage = local_task_generation_lineage()
    return [
        candidate if candidate.generation_lineage else replace(candidate, generation_lineage=lineage)
        for candidate in candidates
    ]


def _attach_contact_followup_authorizations(
    candidates: list[CandidateTask],
) -> list[CandidateTask]:
    return [
        _attach_contact_followup_authorization(candidate)
        for candidate in candidates
    ]


def _attach_contact_followup_authorization(
    candidate: CandidateTask,
) -> CandidateTask:
    from synthesis.contact_mutations import prepare_contact_candidate

    return prepare_contact_candidate(candidate)


def local_task_generation_lineage() -> dict[str, object]:
    return {
        "role": "scripted_task_generation",
        "role_version": "role_scripted_task_generation_v1",
        "output_type": "candidate_tasks",
        "owner_module": "synthesis.tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted",
        "config_hash": "scripted_task_generation_v1",
        "configured": True,
    }


def local_scale_probe_generation_lineage() -> dict[str, object]:
    return {
        "role": "scripted_task_generation",
        "role_version": "role_scripted_task_generation_v1",
        "output_type": "candidate_tasks",
        "owner_module": "synthesis.tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted_scale_probe",
        "config_hash": "scale-probe-local-v1",
        "configured": True,
    }


def local_task_suggester_lineage() -> dict[str, object]:
    return {
        "role": "task_suggester",
        "role_version": "role_task_suggester_v1",
        "output_type": "task_suggestion",
        "owner_module": "synthesis.tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted",
        "config_hash": "task_suggester_local_v1",
        "configured": False,
    }


def local_task_editor_lineage(*, editor_action: str) -> dict[str, object]:
    return {
        "role": "task_editor",
        "role_version": "role_task_editor_v1",
        "output_type": "edited_task",
        "owner_module": "synthesis.tasks",
        "retry_policy": "local_deterministic",
        "provider_host": "local",
        "model": "scripted",
        "config_hash": "task_editor_local_v1",
        "configured": False,
        "editor_action": editor_action,
    }


def _suggestion_from_mapping(
    transformation: dict[str, object],
    raw: Any,
    lineage: dict[str, object],
) -> TaskSuggestion:
    if not isinstance(raw, dict):
        raise TypeError("suggestion must be an object")
    return TaskSuggestion(
        suggestion_id=str(raw["suggestion_id"]),
        transformation_id=str(raw.get("transformation_id", transformation["transformation_id"])),
        target_taxonomy_node=str(
            raw.get("target_taxonomy_node", transformation["target_taxonomy_node"])
        ),
        intent=str(raw["intent"]),
        required_capabilities=_string_tuple(raw["required_capabilities"]),
        target_tools=_string_tuple(raw["target_tools"]),
        constraints=_normalize_constraints(raw["constraints"]),
        expected_verification=str(raw["expected_verification"]),
        outcome=str(raw.get("outcome", "accepted")),
        lineage=dict(lineage),
        rejection_reason=(
            str(raw["rejection_reason"]) if raw.get("rejection_reason") is not None else None
        ),
        seed_transformation=dict(transformation),
    )


def _edited_task_from_mapping(
    *,
    seed: DomainSeed,
    transformation: dict[str, object],
    suggestion: TaskSuggestion,
    raw: dict[str, Any],
    lineage: dict[str, object],
) -> EditedTask:
    editor_action = str(raw["editor_action"])
    if "candidate" in raw and "rejection" in raw:
        raise ValueError("edited_task cannot contain both candidate and rejection")
    if "candidate" in raw:
        candidate = candidate_from_mapping(
            raw["candidate"],
            seed_ids=(seed.seed_id,),
            generation_lineage=local_task_generation_lineage(),
            seed_transformation=transformation,
            task_suggester_lineage=suggestion.lineage,
            task_editor_lineage=lineage,
            editor_action=editor_action,
        )
        return EditedTask(
            suggestion_id=str(raw.get("suggestion_id", suggestion.suggestion_id)),
            editor_action=editor_action,
            lineage=dict(lineage),
            candidate=candidate,
        )
    if "rejection" in raw:
        rejection = raw["rejection"]
        if not isinstance(rejection, dict):
            raise TypeError("edited_task rejection must be an object")
        return EditedTask(
            suggestion_id=str(raw.get("suggestion_id", suggestion.suggestion_id)),
            editor_action=editor_action,
            lineage=dict(lineage),
            rejection=dict(rejection),
        )
    raise ValueError("edited_task must contain a candidate or rejection")


def _candidate_mapping(candidate: CandidateTask) -> dict[str, object]:
    record = candidate.export()
    record.update(
        {
            "tool_name": candidate.tool_name,
            "arguments": candidate.arguments,
            "expected_answer": candidate.expected_answer,
        }
    )
    if candidate.expected_state is not None:
        record["expected_state"] = candidate.expected_state
    return record


def _string_tuple(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str) or not isinstance(raw, list):
        raise TypeError("expected a list of strings")
    values = tuple(str(value) for value in raw)
    if not values or any(not value.strip() for value in values):
        raise ValueError("expected at least one non-empty string")
    return values


def _task_suggestion_prompt(seed: DomainSeed, transformation: dict[str, object]) -> str:
    return (
        "Suggest executable task intents for a seed transformation.\n"
        f"Domain: {seed.domain}\n"
        f"Seed: {seed.seed_id}\n"
        f"Transformation: {transformation}\n"
        "Return JSON with a suggestions array. Each suggestion must include "
        "suggestion_id, intent, required_capabilities, target_tools, constraints, "
        "expected_verification, and outcome."
    )


def _task_editor_prompt(
    seed: DomainSeed,
    transformation: dict[str, object],
    suggestion: TaskSuggestion,
) -> str:
    return (
        "Edit a task suggestion into an executable CandidateTask mapping.\n"
        f"Domain: {seed.domain}\n"
        f"Transformation: {transformation}\n"
        f"Suggestion: {suggestion.export()}\n"
        "Return JSON with edited_task. A successful edit must include "
        "suggestion_id, editor_action, and candidate with candidate_id, instruction, "
        "constraints, difficulty, tool_name, arguments, and expected_answer. "
        "Use only lookup_contact_email and record_contact_followup."
    )


def _llm_schema_error(
    lineage: dict[str, object],
    exc: Exception,
) -> LLMProviderError:
    return LLMProviderError(
        cause="llm_response_schema_error",
        error_class=type(exc).__name__,
        retryable=False,
        retry_count=_lineage_retry_count(lineage),
        lineage=lineage,
    )


def _lineage_retry_count(lineage: dict[str, object]) -> int:
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        return retry_count
    return 0
