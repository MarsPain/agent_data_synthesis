"""Workspace Tasks implementation of the provisional Agent-first Domain seam.

The adapter owns its fixture format, task compilation, isolated state, and
assessment. The shared Agent-first core sees only the generic Domain protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import JsonValue

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.domain import (
    CompilationRejection,
    CompiledTask,
    FrozenInitialState,
    TaskProposal,
    TaskSlot,
    ToolExecutionResult,
)
from agent_synthesis.episode import (
    AssessmentCheck,
    EpisodeAssessment,
    EpisodeEvent,
    ExecutionTrace,
    PublicTask,
    ReviewStratification,
    ToolDefinition,
)


_FIXTURE_SOURCE = {
    "projects": [
        {"project_id": "project-alpha-001", "name": "Alpha Launch"},
        {"project_id": "project-beta-002", "name": "Beta Research"},
    ],
    "tasks": [
        {
            "task_id": "task-launch-plan-001",
            "project_id": "project-alpha-001",
            "title": "Finalize launch plan",
        },
        {
            "task_id": "task-research-notes-002",
            "project_id": "project-beta-002",
            "title": "Summarize research notes",
        },
        {
            "task_id": "task-metrics-review-003",
            "project_id": "project-alpha-001",
            "title": "Review metrics dashboard",
        },
    ],
    "documents": [
        {
            "document_id": "document-launch-brief-001",
            "project_id": "project-alpha-001",
            "title": "Launch Brief",
            "body": "Launch owners and rollout criteria.",
        }
    ],
    "comments": [],
}


type _WorkspaceAction = Literal[
    "search_workspace_items",
    "create_workspace_task",
    "add_workspace_comment",
]
type _Route = Literal["direct", "directory", "recovery", "missing", "verify"]
type _TaskConstraint = Literal["none", "open", "exact"]
type _CommentConstraint = Literal["none", "open", "exact"]

_WORKSPACE_ACTIONS = frozenset(
    {"search_workspace_items", "create_workspace_task", "add_workspace_comment"}
)
_ROUTES = frozenset({"direct", "directory", "recovery", "missing", "verify"})
_TASK_CONSTRAINTS = frozenset({"none", "open", "exact"})
_COMMENT_CONSTRAINTS = frozenset({"none", "open", "exact"})


@dataclass(frozen=True)
class _WorkspaceItem:
    item_id: str
    kind: str
    query: str
    summary: str
    project_id: str | None = None


@dataclass(frozen=True)
class _InitialState:
    items: dict[str, _WorkspaceItem]


@dataclass(frozen=True)
class _WorkspaceCase:
    target: _WorkspaceItem | None
    action: _WorkspaceAction
    route: _Route
    missing_query: str | None = None
    missing_kind: str | None = None
    title: str | None = None
    priority: str | None = None
    due_label: str | None = None
    task_constraint: _TaskConstraint = "none"
    comment_constraint: _CommentConstraint = "none"
    exact_comment: str | None = None


@dataclass(frozen=True)
class _TaskSpec:
    slot_kind: str
    action: _WorkspaceAction
    route: _Route
    target_kind: str | None = None
    fallback_to_any_item: bool = False
    target_index: int = 0
    comment_constraint: _CommentConstraint = "none"
    task_constraint: _TaskConstraint = "none"


@dataclass(frozen=True)
class WorkspaceTasksStructuralExample:
    """A reviewed equivalence or distinction for the Workspace taxonomy."""

    example_id: str
    expected_structural_key: str
    variation: str


@dataclass(frozen=True)
class WorkspaceTasksSlotCapacity:
    """Finite deterministic task-space capacity for one frozen source."""

    known_task_capacity: int
    requested_limit: int
    emitted_slot_count: int
    exhausted: bool


_TASK_SPECS = (
    _TaskSpec(
        "search-direct",
        "search_workspace_items",
        "direct",
        target_kind="document",
        fallback_to_any_item=True,
    ),
    _TaskSpec(
        "search-directory",
        "search_workspace_items",
        "directory",
        target_kind="project",
    ),
    _TaskSpec(
        "search-recovery",
        "search_workspace_items",
        "recovery",
        target_kind="task",
        fallback_to_any_item=True,
    ),
    _TaskSpec("search-missing", "search_workspace_items", "missing"),
    _TaskSpec(
        "task-direct",
        "create_workspace_task",
        "direct",
        target_kind="project",
        task_constraint="exact",
    ),
    _TaskSpec(
        "task-verified",
        "create_workspace_task",
        "verify",
        target_kind="project",
        target_index=1,
        task_constraint="open",
    ),
    _TaskSpec(
        "comment-direct",
        "add_workspace_comment",
        "direct",
        target_kind="task",
        comment_constraint="open",
    ),
    _TaskSpec(
        "comment-recovery",
        "add_workspace_comment",
        "recovery",
        target_kind="task",
        target_index=2,
        comment_constraint="exact",
    ),
    _TaskSpec(
        "comment-verified",
        "add_workspace_comment",
        "verify",
        target_kind="task",
        target_index=1,
        comment_constraint="open",
    ),
)


_REVIEWED_STRUCTURAL_EXAMPLES = (
    WorkspaceTasksStructuralExample("search_direct", "workspace_tasks.search.direct", "baseline"),
    WorkspaceTasksStructuralExample("search_directory", "workspace_tasks.search.directory", "baseline"),
    WorkspaceTasksStructuralExample("search_recovery", "workspace_tasks.search.recovery", "baseline"),
    WorkspaceTasksStructuralExample("search_missing", "workspace_tasks.search.missing", "baseline"),
    WorkspaceTasksStructuralExample("task_direct", "workspace_tasks.task.direct", "baseline"),
    WorkspaceTasksStructuralExample("task_verified", "workspace_tasks.task.verified", "baseline"),
    WorkspaceTasksStructuralExample("comment_direct", "workspace_tasks.comment.direct", "baseline"),
    WorkspaceTasksStructuralExample("comment_recovery", "workspace_tasks.comment.recovery", "baseline"),
    WorkspaceTasksStructuralExample("comment_verified", "workspace_tasks.comment.verified", "baseline"),
    WorkspaceTasksStructuralExample(
        "search_direct_paraphrase", "workspace_tasks.search.direct", "paraphrase"
    ),
    WorkspaceTasksStructuralExample(
        "search_direct_entity_swap", "workspace_tasks.search.direct", "entity_substitution"
    ),
    WorkspaceTasksStructuralExample(
        "search_direct_padded_tools", "workspace_tasks.search.direct", "padded_tool_sequence"
    ),
)


class WorkspaceTasksDomainAdapter:
    """A fixture-backed Workspace Tasks adapter with no shared-core schema leak."""

    domain_id = "workspace_tasks"
    domain_version = "workspace_tasks_agent_adapter_v1"

    def __init__(self, source_contents: bytes) -> None:
        if not isinstance(source_contents, bytes) or not source_contents:
            raise ValueError("Workspace Tasks adapter requires non-empty source bytes")
        self._source_contents = bytes(source_contents)

    @classmethod
    def fixture(cls) -> "WorkspaceTasksDomainAdapter":
        return cls(_canonical_json_bytes(_FIXTURE_SOURCE))

    @classmethod
    def from_local_file(cls, path: Path | str) -> "WorkspaceTasksDomainAdapter":
        return cls(Path(path).read_bytes())

    def open_run(self, configuration: RunConfiguration) -> "WorkspaceTasksDomainRun":
        del configuration
        return WorkspaceTasksDomainRun(_parse_source(self._source_contents))

    def open_run_from_frozen_state(
        self,
        configuration: RunConfiguration,
        frozen_initial_state: FrozenInitialState,
    ) -> "WorkspaceTasksDomainRun":
        """Resume from persisted normalized bytes rather than a mutable source path."""

        del configuration
        return WorkspaceTasksDomainRun(_initial_state_from_frozen_state(frozen_initial_state))

    @property
    def reviewed_structural_examples(self) -> tuple[WorkspaceTasksStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES


class WorkspaceTasksDomainRun:
    """Run-scoped Workspace slot issuance and public request compilation."""

    def __init__(self, initial_state: _InitialState) -> None:
        self._initial_state = _copy_initial_state(initial_state)
        self._items = dict(initial_state.items)
        self._missing_query = _missing_document_query_for(self._items)
        self._normalized_state = _canonical_json_bytes(
            {"items": [_item_record(item) for item in _sorted_items(self._items)]}
        )

    @property
    def known_task_capacity(self) -> int:
        return len(self._available_specs())

    @property
    def reviewed_structural_examples(self) -> tuple[WorkspaceTasksStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES

    def slot_capacity(self, limit: int) -> WorkspaceTasksSlotCapacity:
        if limit < 0:
            raise ValueError("slot capacity limit must not be negative")
        capacity = self.known_task_capacity
        return WorkspaceTasksSlotCapacity(
            known_task_capacity=capacity,
            requested_limit=limit,
            emitted_slot_count=min(limit, capacity),
            exhausted=limit >= capacity,
        )

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        if limit < 0:
            raise ValueError("slot limit must not be negative")
        return tuple(
            TaskSlot(
                slot_id=self._slot_id(spec, target, missing_query=self._missing_query),
                proposal_prompt=(
                    "Return exactly this JSON proposal: "
                    + json.dumps(
                        _proposal_payload(
                            _case_for_spec(
                                spec,
                                target,
                                missing_query=self._missing_query,
                            )
                        ),
                        sort_keys=True,
                    )
                ),
            )
            for spec, target in self._available_specs()
        )[:limit]

    def freeze_initial_state(self) -> FrozenInitialState:
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(self._normalized_state).hexdigest(),
            contents=self._normalized_state,
        )

    def compile(
        self,
        slot: TaskSlot,
        proposal: TaskProposal,
    ) -> CompiledTask | CompilationRejection:
        slot_spec = self._slot_spec(slot.slot_id)
        if slot_spec is None:
            return _compilation_rejection("unsupported_task_slot")
        spec, target = slot_spec
        if target is not None and not _item_query_is_unique(target, self._items):
            return _compilation_rejection("unresolved_target_ambiguity")
        try:
            payload = json.loads(proposal.content)
        except json.JSONDecodeError:
            if _text_requests_negation(proposal.content):
                return _compilation_rejection("negated_action")
            return _compilation_rejection("proposal_not_json")
        if not isinstance(payload, dict):
            return _compilation_rejection("proposal_not_object")
        action = payload.get("action")
        if (
            payload.get("negated") is True
            or isinstance(action, str) and _action_is_negated(action)
        ):
            return _compilation_rejection("negated_action")
        if any(
            name in payload
            for name in (
                "item_id",
                "project_id",
                "task_id",
                "document_id",
                "comment_id",
                "target_item_id",
            )
        ):
            return _compilation_rejection("unsupported_private_exact_target")
        if not isinstance(action, str) or action != spec.action:
            return _compilation_rejection("unsupported_requested_action")
        if payload.get("route") != spec.route:
            return _compilation_rejection("uncheckable_condition")
        expected = _case_for_spec(spec, target, missing_query=self._missing_query)
        if spec.action == "search_workspace_items":
            if payload != _proposal_payload(expected):
                return _compilation_rejection("unsupported_requested_action")
            case = expected
        elif spec.action == "create_workspace_task":
            case = self._compile_task_creation(expected, payload)
        else:
            case = self._compile_comment_addition(expected, payload)
        if isinstance(case, CompilationRejection):
            return case
        return CompiledTask(
            public_task=_public_task(case),
            semantic_key=_semantic_key(case),
            private_case_bytes=_private_case_bytes(case),
            domain_case=case,
        )

    def _compile_task_creation(
        self,
        expected: _WorkspaceCase,
        payload: dict[str, object],
    ) -> _WorkspaceCase | CompilationRejection:
        if "condition" not in payload:
            return _compilation_rejection("missing_mutation_authority")
        if payload.get("condition") != "after_item_match":
            return _compilation_rejection("uncheckable_condition")
        assert expected.target is not None
        if (
            payload.get("project_query") != expected.target.query
            or payload.get("project_kind") != expected.target.kind
        ):
            return _compilation_rejection("wrong_item_binding")
        if any(not isinstance(payload.get(name), str) for name in ("priority", "due_label")):
            return _compilation_rejection("missing_mutation_argument")
        if (
            payload.get("priority") != expected.priority
            or payload.get("due_label") != expected.due_label
        ):
            return _compilation_rejection("unauthorized_task_argument")
        if expected.task_constraint == "exact":
            if not isinstance(payload.get("title"), str):
                return _compilation_rejection("missing_mutation_argument")
            if payload.get("title") != expected.title:
                return _compilation_rejection("unauthorized_task_argument")
        elif (
            payload.get("task_constraint") != "open"
            or "title" in payload
        ):
            return _compilation_rejection("unsupported_task_title")
        if set(payload) != set(_proposal_payload(expected)):
            return _compilation_rejection("unsupported_requested_action")
        return expected

    def _compile_comment_addition(
        self,
        expected: _WorkspaceCase,
        payload: dict[str, object],
    ) -> _WorkspaceCase | CompilationRejection:
        if "condition" not in payload:
            return _compilation_rejection("missing_mutation_authority")
        if payload.get("condition") != "after_item_match":
            return _compilation_rejection("uncheckable_condition")
        assert expected.target is not None
        if (
            payload.get("task_query") != expected.target.query
            or payload.get("task_kind") != expected.target.kind
        ):
            return _compilation_rejection("wrong_item_binding")
        if payload.get("comment_constraint") != expected.comment_constraint:
            return _compilation_rejection("unsupported_comment")
        comment = payload.get("comment")
        if expected.comment_constraint == "exact":
            if not isinstance(comment, str) or comment != expected.exact_comment:
                return _compilation_rejection("unauthorized_comment_argument")
        elif comment is not None:
            return _compilation_rejection("unsupported_comment")
        if set(payload) != set(_proposal_payload(expected)):
            return _compilation_rejection("unsupported_requested_action")
        return expected

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "WorkspaceTasksEpisode":
        return self._open_episode_from_frozen_state(task, frozen_initial_state)

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        case = _case_from_private_bytes(private_case_bytes)
        if not _case_has_supported_shape(case):
            raise ValueError("invalid private Workspace Tasks task case")
        if semantic_key != _semantic_key(case):
            raise ValueError("private Workspace Tasks semantic key does not match task case")
        return CompiledTask(
            public_task=public_task,
            semantic_key=semantic_key,
            private_case_bytes=private_case_bytes,
            domain_case=case,
        )

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "WorkspaceTasksEpisode":
        return self._open_episode_from_frozen_state(task, frozen_initial_state)

    def _open_episode_from_frozen_state(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "WorkspaceTasksEpisode":
        case = _case_from_task(task)
        initial_state = _initial_state_from_frozen_state(frozen_initial_state)
        if not _case_is_bound_to_frozen_state(case, initial_state):
            raise ValueError("task case is not bound to the frozen Workspace Tasks state")
        return WorkspaceTasksEpisode(case, initial_state)

    def _available_specs(self) -> tuple[tuple[_TaskSpec, _WorkspaceItem | None], ...]:
        return _available_specs_for_items(self._items)

    def _resolved_target_for_spec(
        self,
        spec: _TaskSpec,
    ) -> tuple[bool, _WorkspaceItem | None]:
        return _resolved_target_for_spec(self._items, spec)

    def _slot_spec(self, slot_id: str) -> tuple[_TaskSpec, _WorkspaceItem | None] | None:
        for spec in _TASK_SPECS:
            if spec.route == "missing":
                if slot_id == self._slot_id(spec, None, missing_query=self._missing_query):
                    return spec, None
                continue
            for target in self._candidate_targets_for_spec(spec):
                if (
                    slot_id == self._slot_id(spec, target)
                ):
                    return spec, target
        return None

    def _candidate_targets_for_spec(self, spec: _TaskSpec) -> tuple[_WorkspaceItem, ...]:
        return _candidate_targets_for_spec(self._items, spec)

    def _slot_id(
        self,
        spec: _TaskSpec,
        target: _WorkspaceItem | None,
        *,
        missing_query: str | None = None,
    ) -> str:
        component = (
            _item_record(target)
            if target is not None
            else {"kind": "document", "query": missing_query or self._missing_query}
        )
        digest = hashlib.sha256(_canonical_json_bytes(component)).hexdigest()[:24]
        return f"workspace-{spec.slot_kind}-item-{digest}"


class WorkspaceTasksEpisode:
    """One isolated Workspace episode reconstructed from frozen state."""

    def __init__(self, case: _WorkspaceCase, initial_state: _InitialState) -> None:
        self._case = case
        self._items = dict(initial_state.items)
        self._created_tasks: dict[str, dict[str, str]] = {}
        self._created_comments: dict[str, dict[str, str]] = {}
        self._target_observed = False
        self._recovery_probe_failed = False
        self._directory_seen = False
        self._mutation_committed = False

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        if tool_name == "search_workspace_items":
            return self._search_workspace_items(arguments)
        if tool_name == "list_workspace_projects":
            self._directory_seen = True
            return ToolExecutionResult(
                result_type="observation",
                observation={
                    "projects": [
                        {"project_id": item.item_id, "name": item.summary}
                        for item in _sorted_items(self._items)
                        if item.kind == "project"
                    ]
                },
            )
        if tool_name == "create_workspace_task":
            return self._create_workspace_task(arguments)
        if tool_name == "get_workspace_task":
            return self._get_workspace_task(arguments)
        if tool_name == "add_workspace_comment":
            return self._add_workspace_comment(arguments)
        if tool_name == "get_workspace_comment":
            return self._get_workspace_comment(arguments)
        return ToolExecutionResult(result_type="tool_failure", error_code="unknown_tool")

    def _search_workspace_items(
        self,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        query = arguments.get("query")
        kind = arguments.get("kind")
        if not isinstance(query, str) or not isinstance(kind, str):
            return ToolExecutionResult(
                result_type="tool_failure", error_code="invalid_search_query"
            )
        target = self._case.target
        if (
            target is not None
            and query == _recovery_probe(target.query)
            and kind == target.kind
        ):
            self._recovery_probe_failed = True
            return ToolExecutionResult(result_type="tool_failure", error_code="item_not_found")
        if target is None or query != target.query or kind != target.kind:
            return ToolExecutionResult(result_type="tool_failure", error_code="item_not_found")
        item = self._items.get(target.item_id)
        if item is None:
            return ToolExecutionResult(result_type="tool_failure", error_code="item_not_found")
        self._target_observed = True
        return ToolExecutionResult(result_type="observation", observation=_item_observation(item))

    def _create_workspace_task(
        self,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        target = self._case.target
        project_id = arguments.get("project_id")
        title = arguments.get("title")
        priority = arguments.get("priority")
        due_label = arguments.get("due_label")
        if (
            self._case.action != "create_workspace_task"
            or target is None
            or project_id != target.item_id
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="mutation_not_authorized"
            )
        if self._mutation_committed:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        if not self._mutation_condition_observed():
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_condition_not_observed",
            )
        if (
            not all(isinstance(value, str) for value in (title, priority, due_label))
            or priority != self._case.priority
            or due_label != self._case.due_label
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="task_not_authorized"
            )
        assert isinstance(title, str)
        if (
            self._case.task_constraint == "exact" and title != self._case.title
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="task_not_authorized"
            )
        if self._case.task_constraint == "open" and not _task_title_is_allowed(title):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unsupported_task_title"
            )
        assert isinstance(project_id, str)
        assert isinstance(priority, str)
        assert isinstance(due_label, str)
        task_id = _created_task_id(project_id, title)
        if task_id in self._items or task_id in self._created_tasks:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        change = {
            "task_id": task_id,
            "project_id": project_id,
            "title": title,
            "priority": priority,
            "due_label": due_label,
        }
        self._created_tasks[task_id] = change
        self._items[task_id] = _WorkspaceItem(
            item_id=task_id,
            kind="task",
            query=_query_for("task", title),
            summary=title,
            project_id=project_id,
        )
        self._mutation_committed = True
        return ToolExecutionResult(result_type="state_change", change=change)

    def _get_workspace_task(
        self,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        task_id = arguments.get("task_id")
        if not isinstance(task_id, str) or task_id not in self._created_tasks:
            return ToolExecutionResult(result_type="tool_failure", error_code="task_not_found")
        return ToolExecutionResult(
            result_type="observation", observation=self._created_tasks[task_id]
        )

    def _add_workspace_comment(
        self,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        target = self._case.target
        task_id = arguments.get("task_id")
        comment = arguments.get("comment")
        if (
            self._case.action != "add_workspace_comment"
            or target is None
            or task_id != target.item_id
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="mutation_not_authorized"
            )
        if self._mutation_committed:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        if not self._mutation_condition_observed():
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_condition_not_observed",
            )
        if not isinstance(comment, str) or not _comment_is_allowed(comment):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unsupported_comment"
            )
        if self._case.comment_constraint == "exact" and comment != self._case.exact_comment:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="comment_not_authorized"
            )
        assert isinstance(task_id, str)
        comment_id = _created_comment_id(task_id, comment)
        if comment_id in self._items or comment_id in self._created_comments:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        change = {"comment_id": comment_id, "task_id": task_id, "comment": comment}
        self._created_comments[comment_id] = change
        self._mutation_committed = True
        return ToolExecutionResult(result_type="state_change", change=change)

    def _get_workspace_comment(
        self,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        comment_id = arguments.get("comment_id")
        if not isinstance(comment_id, str) or comment_id not in self._created_comments:
            return ToolExecutionResult(result_type="tool_failure", error_code="comment_not_found")
        return ToolExecutionResult(
            result_type="observation", observation=self._created_comments[comment_id]
        )

    def _mutation_condition_observed(self) -> bool:
        if not self._target_observed:
            return False
        return self._case.route != "recovery" or self._recovery_probe_failed

    def assess(self, trace: ExecutionTrace) -> EpisodeAssessment:
        if self._case.action == "create_workspace_task":
            return self._assess_task(trace)
        if self._case.action == "add_workspace_comment":
            return self._assess_comment(trace)
        return self._assess_search(trace)

    def _assess_search(self, trace: ExecutionTrace) -> EpisodeAssessment:
        if self._case.route == "missing":
            return self._assess_missing_search(trace)
        target = self._case.target
        observed = target is not None and _target_item_observed(trace.events, self._case)
        route_completed = _route_completed(trace.events, self._case)
        final_response = _final_response(trace.events)
        grounded = (
            target is not None
            and isinstance(final_response, str)
            and target.query.casefold() in final_response.casefold()
            and target.kind.casefold() in final_response.casefold()
        )
        no_unintended_state_changes = not any(
            event.event_type == "state_change" for event in trace.events
        )
        checks = (
            AssessmentCheck(
                name="requested_item_observed", passed=observed and route_completed
            ),
            AssessmentCheck(
                name="no_unintended_state_changes", passed=no_unintended_state_changes
            ),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("requested_item_not_observed", observed and route_completed),
                    ("unintended_state_change", no_unintended_state_changes),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("item_search", self._case.route),
            structural_key=f"workspace_tasks.search.{self._case.route}",
            review_stratification=ReviewStratification(
                task_type=self._case.action,
                difficulty=self._case.route,
            ),
        )

    def _assess_missing_search(self, trace: ExecutionTrace) -> EpisodeAssessment:
        assert self._case.missing_query is not None and self._case.missing_kind is not None
        expected_arguments = {
            "query": self._case.missing_query,
            "kind": self._case.missing_kind,
        }
        actions = [
            index
            for index, event in enumerate(trace.events)
            if event.event_type == "action"
            and event.tool_name == "search_workspace_items"
            and event.arguments == expected_arguments
        ]
        failures = [
            index
            for index, event in enumerate(trace.events)
            if event.event_type == "error"
            and event.tool_name == "search_workspace_items"
            and event.error_code == "item_not_found"
        ]
        missing_observed = any(action < failure for action in actions for failure in failures)
        final_response = _final_response(trace.events)
        grounded = (
            isinstance(final_response, str)
            and self._case.missing_query.casefold() in final_response.casefold()
            and self._case.missing_kind.casefold() in final_response.casefold()
            and any(
                phrase in final_response.casefold()
                for phrase in ("not found", "unavailable", "no matching")
            )
        )
        no_unintended_state_changes = not any(
            event.event_type == "state_change" for event in trace.events
        )
        checks = (
            AssessmentCheck(name="missing_item_observed", passed=missing_observed),
            AssessmentCheck(
                name="no_unintended_state_changes", passed=no_unintended_state_changes
            ),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("missing_item_not_observed", missing_observed),
                    ("unintended_state_change", no_unintended_state_changes),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("missing_item_safe_failure",),
            structural_key="workspace_tasks.search.missing",
            review_stratification=ReviewStratification(
                task_type=self._case.action,
                difficulty=self._case.route,
            ),
        )

    def _assess_task(self, trace: ExecutionTrace) -> EpisodeAssessment:
        target = self._case.target
        assert target is not None
        assert self._case.priority is not None
        assert self._case.due_label is not None
        item_observed = _target_item_observed(trace.events, self._case)
        route_completed = _route_completed(trace.events, self._case)
        all_state_changes = [
            event for event in trace.events if event.event_type == "state_change"
        ]
        changes = [
            event.change
            for event in all_state_changes
            if event.tool_name == "create_workspace_task"
        ]
        requested_change = changes[0] if len(changes) == 1 else None
        recorded_title = (
            requested_change.get("title") if isinstance(requested_change, dict) else None
        )
        expected_task_id = (
            _created_task_id(target.item_id, recorded_title)
            if isinstance(recorded_title, str)
            else None
        )
        requested_effect = (
            isinstance(requested_change, dict)
            and isinstance(recorded_title, str)
            and requested_change.get("task_id") == expected_task_id
            and requested_change.get("project_id") == target.item_id
            and requested_change.get("priority") == self._case.priority
            and requested_change.get("due_label") == self._case.due_label
            and (
                recorded_title == self._case.title
                if self._case.task_constraint == "exact"
                else _task_title_is_allowed(recorded_title)
            )
        )
        no_unintended_changes = len(all_state_changes) == 1 and len(changes) == 1
        authorized = trace.mutation_authorization == "authorized"
        verified = (
            self._case.route != "verify"
            or any(
                event.event_type == "observation"
                and event.tool_name == "get_workspace_task"
                and event.observation == requested_change
                for event in trace.events
            )
        )
        final_response = _final_response(trace.events)
        grounded = (
            isinstance(final_response, str)
            and target.query.casefold() in final_response.casefold()
            and isinstance(recorded_title, str)
            and recorded_title.casefold() in final_response.casefold()
            and self._case.priority.casefold() in final_response.casefold()
            and self._case.due_label.casefold() in final_response.casefold()
            and isinstance(expected_task_id, str)
            and expected_task_id.casefold() in final_response.casefold()
        )
        checks = (
            AssessmentCheck(
                name="project_condition_observed", passed=item_observed and route_completed
            ),
            AssessmentCheck(name="authorized_mutation", passed=authorized),
            AssessmentCheck(name="requested_task_created", passed=requested_effect),
            AssessmentCheck(name="no_unintended_state_changes", passed=no_unintended_changes),
            AssessmentCheck(name="saved_task_observed", passed=verified),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("project_condition_not_observed", item_observed and route_completed),
                    ("mutation_not_authorized", authorized),
                    ("requested_task_not_created", requested_effect),
                    ("unintended_state_change", no_unintended_changes),
                    ("saved_task_not_observed", verified),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("task_creation", self._case.route, self._case.task_constraint),
            structural_key=(
                "workspace_tasks.task.verified"
                if self._case.route == "verify"
                else f"workspace_tasks.task.{self._case.route}"
            ),
            state_change_evidence=(
                _state_change_evidence("task", target)
                if requested_effect and item_observed and route_completed
                else None
            ),
            review_stratification=ReviewStratification(
                task_type=self._case.action,
                difficulty=self._case.route,
            ),
        )

    def _assess_comment(self, trace: ExecutionTrace) -> EpisodeAssessment:
        target = self._case.target
        assert target is not None
        item_observed = _target_item_observed(trace.events, self._case)
        route_completed = _route_completed(trace.events, self._case)
        all_state_changes = [
            event for event in trace.events if event.event_type == "state_change"
        ]
        changes = [
            event.change
            for event in all_state_changes
            if event.tool_name == "add_workspace_comment"
        ]
        requested_change = changes[0] if len(changes) == 1 else None
        comment = (
            requested_change.get("comment")
            if isinstance(requested_change, dict)
            else None
        )
        requested_effect = (
            isinstance(requested_change, dict)
            and requested_change.get("task_id") == target.item_id
            and isinstance(comment, str)
            and requested_change.get("comment_id") == _created_comment_id(target.item_id, comment)
            and (
                comment == self._case.exact_comment
                if self._case.comment_constraint == "exact"
                else _comment_is_allowed(comment)
            )
        )
        no_unintended_changes = len(all_state_changes) == 1 and len(changes) == 1
        authorized = trace.mutation_authorization == "authorized"
        verified = (
            self._case.route != "verify"
            or any(
                event.event_type == "observation"
                and event.tool_name == "get_workspace_comment"
                and event.observation == requested_change
                for event in trace.events
            )
        )
        final_response = _final_response(trace.events)
        grounded = (
            isinstance(final_response, str)
            and target.query.casefold() in final_response.casefold()
            and isinstance(comment, str)
            and comment.casefold() in final_response.casefold()
        )
        checks = (
            AssessmentCheck(
                name="task_condition_observed", passed=item_observed and route_completed
            ),
            AssessmentCheck(name="authorized_mutation", passed=authorized),
            AssessmentCheck(name="requested_comment_added", passed=requested_effect),
            AssessmentCheck(name="no_unintended_state_changes", passed=no_unintended_changes),
            AssessmentCheck(name="saved_comment_observed", passed=verified),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("task_condition_not_observed", item_observed and route_completed),
                    ("mutation_not_authorized", authorized),
                    ("requested_comment_not_added", requested_effect),
                    ("unintended_state_change", no_unintended_changes),
                    ("saved_comment_not_observed", verified),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("comment_addition", self._case.route, self._case.comment_constraint),
            structural_key=(
                "workspace_tasks.comment.verified"
                if self._case.route == "verify"
                else f"workspace_tasks.comment.{self._case.route}"
            ),
            state_change_evidence=(
                _state_change_evidence("comment", target)
                if requested_effect and item_observed and route_completed
                else None
            ),
            review_stratification=ReviewStratification(
                task_type=self._case.action,
                difficulty=self._case.route,
            ),
        )


def _case_for_spec(
    spec: _TaskSpec,
    target: _WorkspaceItem | None,
    *,
    missing_query: str | None = None,
) -> _WorkspaceCase:
    if spec.route == "missing":
        return _WorkspaceCase(
            target=None,
            action=spec.action,
            route=spec.route,
            missing_query=missing_query or "archived roadmap",
            missing_kind="document",
        )
    assert target is not None
    if spec.action == "create_workspace_task":
        title, priority, due_label = _task_arguments_for(target, route=spec.route)
        return _WorkspaceCase(
            target=target,
            action=spec.action,
            route=spec.route,
            title=title if spec.task_constraint == "exact" else None,
            priority=priority,
            due_label=due_label,
            task_constraint=spec.task_constraint,
        )
    if spec.action == "add_workspace_comment":
        return _WorkspaceCase(
            target=target,
            action=spec.action,
            route=spec.route,
            comment_constraint=spec.comment_constraint,
            exact_comment=(
                _exact_comment_for(target) if spec.comment_constraint == "exact" else None
            ),
        )
    return _WorkspaceCase(target=target, action=spec.action, route=spec.route)


def _public_task(case: _WorkspaceCase) -> PublicTask:
    if case.action == "create_workspace_task":
        return _task_public_task(case)
    if case.action == "add_workspace_comment":
        return _comment_public_task(case)
    return _search_public_task(case)


def _search_public_task(case: _WorkspaceCase) -> PublicTask:
    if case.route == "missing":
        assert case.missing_query is not None and case.missing_kind is not None
        instruction = (
            f'Search for the workspace {case.missing_kind} that matches "{case.missing_query}". '
            "If it is not found, report that safely and make no changes."
        )
    else:
        assert case.target is not None
        if case.route == "directory":
            instruction = (
                f"Use the project directory to identify {case.target.summary}, then find the "
                f'workspace {case.target.kind} that matches "{case.target.query}".'
            )
        elif case.route == "recovery":
            instruction = (
                f'A stale workspace query may fail. First search for "{_recovery_probe(case.target.query)}". '
                f'If it reports no item, find the workspace {case.target.kind} that matches '
                f'"{case.target.query}".'
            )
        else:
            instruction = f'Find the workspace {case.target.kind} that matches "{case.target.query}".'
    tools: list[ToolDefinition] = [_search_tool()]
    if case.route == "directory":
        tools.append(_project_directory_tool())
    return PublicTask(instruction=instruction, tools=tuple(tools))


def _task_public_task(case: _WorkspaceCase) -> PublicTask:
    assert case.target is not None
    assert case.priority is not None and case.due_label is not None
    search_task = _search_public_task(
        _WorkspaceCase(
            target=case.target,
            action="search_workspace_items",
            route="direct",
        )
    )
    tools = [*search_task.tools, _create_task_tool()]
    verification_request = ""
    if case.route == "verify":
        tools.append(_get_task_tool())
        verification_request = " Then retrieve the saved task and report its details."
    task_request = (
        f'create a task titled "{case.title}"'
        if case.task_constraint == "exact"
        else "create a concise planning task"
    )
    return PublicTask(
        instruction=(
            f"{search_task.instruction} After finding the selected project, {task_request} "
            f"with {case.priority} priority and due {case.due_label}."
            f"{verification_request}"
        ),
        tools=tuple(tools),
    )


def _comment_public_task(case: _WorkspaceCase) -> PublicTask:
    assert case.target is not None
    search_task = _search_public_task(
        _WorkspaceCase(
            target=case.target,
            action="search_workspace_items",
            route="recovery" if case.route == "recovery" else "direct",
        )
    )
    comment_request = (
        f'Add exactly this comment: "{case.exact_comment}".'
        if case.comment_constraint == "exact"
        else "Add a concise status comment."
    )
    tools = [*search_task.tools, _add_comment_tool()]
    verification_request = ""
    if case.route == "verify":
        tools.append(_get_comment_tool())
        verification_request = " Then retrieve the saved comment and report its text."
    return PublicTask(
        instruction=(
            f"{search_task.instruction} After finding the selected task, {comment_request}"
            f"{verification_request}"
        ),
        tools=tuple(tools),
    )


def _search_tool() -> ToolDefinition:
    return ToolDefinition(
        name="search_workspace_items",
        description="Find one workspace item by a public query and kind.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "kind": {"type": "string"}},
            "required": ["query", "kind"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "kind": {"type": "string"},
                "summary": {"type": "string"},
            },
        },
    )


def _project_directory_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_workspace_projects",
        description="List projects represented in this isolated workspace.",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"projects": {"type": "array"}}},
    )


def _create_task_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_workspace_task",
        description="Create one task in a project observed in this Episode.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "priority": {"type": "string"},
                "due_label": {"type": "string"},
            },
            "required": ["project_id", "title", "priority", "due_label"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "priority": {"type": "string"},
                "due_label": {"type": "string"},
            },
        },
    )


def _get_task_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_workspace_task",
        description="Retrieve a task created in this Episode.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        output_schema=_create_task_tool().output_schema,
    )


def _add_comment_tool() -> ToolDefinition:
    return ToolDefinition(
        name="add_workspace_comment",
        description="Add one comment to a task observed in this Episode.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "comment": {"type": "string"}},
            "required": ["task_id", "comment"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "comment_id": {"type": "string"},
                "task_id": {"type": "string"},
                "comment": {"type": "string"},
            },
        },
    )


def _get_comment_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_workspace_comment",
        description="Retrieve a comment created in this Episode.",
        input_schema={
            "type": "object",
            "properties": {"comment_id": {"type": "string"}},
            "required": ["comment_id"],
        },
        output_schema=_add_comment_tool().output_schema,
    )


def _proposal_payload(case: _WorkspaceCase) -> dict[str, str]:
    if case.action == "search_workspace_items":
        if case.route == "missing":
            assert case.missing_query is not None and case.missing_kind is not None
            return {
                "action": case.action,
                "kind": case.missing_kind,
                "query": case.missing_query,
                "route": case.route,
            }
        assert case.target is not None
        return {
            "action": case.action,
            "kind": case.target.kind,
            "query": case.target.query,
            "route": case.route,
        }
    assert case.target is not None
    if case.action == "create_workspace_task":
        assert case.priority is not None and case.due_label is not None
        payload = {
            "action": case.action,
            "condition": "after_item_match",
            "due_label": case.due_label,
            "priority": case.priority,
            "project_kind": case.target.kind,
            "project_query": case.target.query,
            "route": case.route,
        }
        if case.task_constraint == "exact":
            assert case.title is not None
            payload["title"] = case.title
        else:
            payload["task_constraint"] = case.task_constraint
        return payload
    payload = {
        "action": case.action,
        "comment_constraint": case.comment_constraint,
        "condition": "after_item_match",
        "route": case.route,
        "task_kind": case.target.kind,
        "task_query": case.target.query,
    }
    if case.comment_constraint == "exact":
        assert case.exact_comment is not None
        payload["comment"] = case.exact_comment
    return payload


def _private_case_bytes(case: _WorkspaceCase) -> bytes:
    return _canonical_json_bytes(
        {
            "action": case.action,
            "comment_constraint": case.comment_constraint,
            "due_label": case.due_label,
            "exact_comment": case.exact_comment,
            "missing_kind": case.missing_kind,
            "missing_query": case.missing_query,
            "priority": case.priority,
            "route": case.route,
            "task_constraint": case.task_constraint,
            "target": _item_record(case.target) if case.target is not None else None,
            "title": case.title,
        }
    )


def _case_from_private_bytes(private_case_bytes: bytes) -> _WorkspaceCase:
    payload = _json_object(private_case_bytes)
    action = payload.get("action")
    route = payload.get("route")
    task_constraint = payload.get("task_constraint")
    comment_constraint = payload.get("comment_constraint")
    target_payload = payload.get("target")
    target = _item_from_record(target_payload) if isinstance(target_payload, dict) else None
    optional_values = {
        name: payload.get(name)
        for name in ("missing_query", "missing_kind", "title", "priority", "due_label", "exact_comment")
    }
    if (
        not isinstance(action, str)
        or action not in _WORKSPACE_ACTIONS
        or not isinstance(route, str)
        or route not in _ROUTES
        or not isinstance(task_constraint, str)
        or task_constraint not in _TASK_CONSTRAINTS
        or not isinstance(comment_constraint, str)
        or comment_constraint not in _COMMENT_CONSTRAINTS
        or any(value is not None and not isinstance(value, str) for value in optional_values.values())
    ):
        raise ValueError("invalid private Workspace Tasks task case")
    if (
        (action == "search_workspace_items" and target is None and route != "missing")
        or (action == "search_workspace_items" and route == "missing" and target is not None)
        or (action != "search_workspace_items" and target is None)
        or (action == "create_workspace_task" and (
            comment_constraint != "none"
            or task_constraint not in {"open", "exact"}
            or not all(isinstance(optional_values[name], str) for name in ("priority", "due_label"))
            or (task_constraint == "exact" and not isinstance(optional_values["title"], str))
            or (task_constraint == "open" and optional_values["title"] is not None)
        ))
        or (action != "create_workspace_task" and task_constraint != "none")
        or (action == "add_workspace_comment" and comment_constraint not in {"open", "exact"})
        or (comment_constraint == "exact" and not isinstance(optional_values["exact_comment"], str))
        or (comment_constraint != "exact" and optional_values["exact_comment"] is not None)
        or (route == "missing" and not all(isinstance(optional_values[name], str) for name in ("missing_query", "missing_kind")))
        or (route != "missing" and any(optional_values[name] is not None for name in ("missing_query", "missing_kind")))
    ):
        raise ValueError("invalid private Workspace Tasks task case")
    return _WorkspaceCase(
        target=target,
        action=cast(_WorkspaceAction, action),
        route=cast(_Route, route),
        missing_query=cast(str | None, optional_values["missing_query"]),
        missing_kind=cast(str | None, optional_values["missing_kind"]),
        title=cast(str | None, optional_values["title"]),
        priority=cast(str | None, optional_values["priority"]),
        due_label=cast(str | None, optional_values["due_label"]),
        task_constraint=cast(_TaskConstraint, task_constraint),
        comment_constraint=cast(_CommentConstraint, comment_constraint),
        exact_comment=cast(str | None, optional_values["exact_comment"]),
    )


def _case_has_supported_shape(case: _WorkspaceCase) -> bool:
    for spec in _TASK_SPECS:
        if case.action != spec.action or case.route != spec.route:
            continue
        if case.route == "missing":
            if (
                case.missing_query is not None
                and case == _case_for_spec(spec, None, missing_query=case.missing_query)
            ):
                return True
            continue
        target = case.target
        if target is None or not _target_kind_is_supported_by_spec(target, spec):
            continue
        if case == _case_for_spec(spec, target):
            return True
    return False


def _target_kind_is_supported_by_spec(target: _WorkspaceItem, spec: _TaskSpec) -> bool:
    return spec.target_kind is None or target.kind == spec.target_kind or spec.fallback_to_any_item


def _case_is_bound_to_frozen_state(case: _WorkspaceCase, state: _InitialState) -> bool:
    expected_cases = {
        _case_for_spec(
            spec,
            target,
            missing_query=_missing_document_query_for(state.items),
        )
        for spec, target in _available_specs_for_items(state.items)
    }
    return case in expected_cases


def _available_specs_for_items(
    items: dict[str, _WorkspaceItem],
) -> tuple[tuple[_TaskSpec, _WorkspaceItem | None], ...]:
    result: list[tuple[_TaskSpec, _WorkspaceItem | None]] = []
    for spec in _TASK_SPECS:
        available, target = _resolved_target_for_spec(items, spec)
        if available:
            result.append((spec, target))
    return tuple(result)


def _resolved_target_for_spec(
    items: dict[str, _WorkspaceItem],
    spec: _TaskSpec,
) -> tuple[bool, _WorkspaceItem | None]:
    if spec.route == "missing":
        return True, None
    candidates = [
        item
        for item in _candidate_targets_for_spec(items, spec)
        if _item_query_is_unique(item, items)
    ]
    if not candidates:
        return False, None
    return True, candidates[min(spec.target_index, len(candidates) - 1)]


def _candidate_targets_for_spec(
    items: dict[str, _WorkspaceItem],
    spec: _TaskSpec,
) -> tuple[_WorkspaceItem, ...]:
    if spec.route == "missing":
        return ()
    if spec.target_kind is None:
        return _sorted_items_by_search_preference(items)
    candidates = tuple(item for item in _sorted_items(items) if item.kind == spec.target_kind)
    if candidates or not spec.fallback_to_any_item:
        return candidates
    return _sorted_items_by_search_preference(items)


def _semantic_key(case: _WorkspaceCase) -> str:
    digest = hashlib.sha256(_private_case_bytes(case)).hexdigest()
    return f"workspace_tasks:semantic:sha256:{digest}"


def _item_record(item: _WorkspaceItem) -> dict[str, str | None]:
    return {
        "item_id": item.item_id,
        "kind": item.kind,
        "project_id": item.project_id,
        "query": item.query,
        "summary": item.summary,
    }


def _item_observation(item: _WorkspaceItem) -> dict[str, str]:
    return {"item_id": item.item_id, "kind": item.kind, "summary": item.summary}


def _item_from_record(record: object) -> _WorkspaceItem:
    if not isinstance(record, dict):
        raise ValueError("invalid private Workspace Tasks task case")
    item_id = record.get("item_id")
    kind = record.get("kind")
    query = record.get("query")
    summary = record.get("summary")
    project_id = record.get("project_id")
    if (
        not all(isinstance(value, str) and value for value in (item_id, kind, query, summary))
        or project_id is not None and not isinstance(project_id, str)
    ):
        raise ValueError("invalid private Workspace Tasks task case")
    assert isinstance(item_id, str)
    assert isinstance(kind, str)
    assert isinstance(query, str)
    assert isinstance(summary, str)
    return _WorkspaceItem(item_id, kind, query, summary, cast(str | None, project_id))


def _compilation_rejection(reason_code: str) -> CompilationRejection:
    return CompilationRejection(
        public_task=PublicTask(
            instruction="The Workspace Tasks request could not be compiled.",
            tools=(_search_tool(),),
        ),
        reason_code=reason_code,
    )


def _case_from_task(task: CompiledTask) -> _WorkspaceCase:
    if not isinstance(task.domain_case, _WorkspaceCase):
        raise ValueError("invalid Workspace Tasks task case")
    return task.domain_case


def _initial_state_from_frozen_state(state: FrozenInitialState) -> _InitialState:
    return _parse_normalized_state(state.contents)


def _parse_source(contents: bytes) -> _InitialState:
    payload = _json_object(contents)
    items: dict[str, _WorkspaceItem] = {}
    projects = payload.get("projects")
    tasks = payload.get("tasks")
    documents = payload.get("documents")
    comments = payload.get("comments", [])
    if not all(isinstance(records, list) for records in (projects, tasks, documents, comments)):
        raise ValueError("Workspace Tasks source collections must be lists")
    assert isinstance(projects, list) and isinstance(tasks, list) and isinstance(documents, list)
    for record in projects:
        _add_source_item(items, record, kind="project", id_name="project_id", summary_name="name")
    project_ids = {item.item_id for item in items.values() if item.kind == "project"}
    for record in tasks:
        _require_source_reference(record, "project_id", project_ids, "project")
        _add_source_item(items, record, kind="task", id_name="task_id", summary_name="title")
    task_ids = {item.item_id for item in items.values() if item.kind == "task"}
    for record in documents:
        _require_source_reference(record, "project_id", project_ids, "project")
        _add_source_item(items, record, kind="document", id_name="document_id", summary_name="title")
    for record in comments:
        _require_source_reference(record, "task_id", task_ids, "task")
        _add_source_item(items, record, kind="comment", id_name="comment_id", summary_name="body")
    if not items:
        raise ValueError("Workspace Tasks source requires at least one item")
    return _InitialState(items=items)


def _add_source_item(
    items: dict[str, _WorkspaceItem],
    record: object,
    *,
    kind: str,
    id_name: str,
    summary_name: str,
) -> None:
    if not isinstance(record, dict):
        raise ValueError("Workspace Tasks source item must be an object")
    item_id = record.get(id_name)
    summary = record.get(summary_name)
    project_id = record.get("project_id")
    if (
        not isinstance(item_id, str)
        or not isinstance(summary, str)
        or not item_id.strip()
        or not summary.strip()
        or item_id in items
        or project_id is not None and not isinstance(project_id, str)
    ):
        raise ValueError("Workspace Tasks source item is invalid")
    if any(len(value) > 1_000 for value in (item_id, summary)):
        raise ValueError("Workspace Tasks source item fields exceed bounded length")
    items[item_id] = _WorkspaceItem(
        item_id=item_id,
        kind=kind,
        query=_query_for(kind, summary),
        summary=summary,
        project_id=cast(str | None, project_id),
    )


def _require_source_reference(
    record: object,
    field_name: str,
    known_ids: set[str],
    relationship_name: str,
) -> None:
    value = record.get(field_name) if isinstance(record, dict) else None
    if not isinstance(value, str) or value not in known_ids:
        raise ValueError(
            f"Workspace Tasks source item references unknown {relationship_name}"
        )


def _parse_normalized_state(contents: bytes) -> _InitialState:
    payload = _json_object(contents)
    records = payload.get("items")
    if not isinstance(records, list) or not records:
        raise ValueError("invalid frozen Workspace Tasks state")
    items: dict[str, _WorkspaceItem] = {}
    for record in records:
        item = _item_from_record(record)
        if item.item_id in items:
            raise ValueError("invalid frozen Workspace Tasks state")
        items[item.item_id] = item
    return _InitialState(items=items)


def _copy_initial_state(initial_state: _InitialState) -> _InitialState:
    return _InitialState(items=dict(initial_state.items))


def _task_arguments_for(
    target: _WorkspaceItem,
    *,
    route: _Route,
) -> tuple[str, str, str]:
    if route == "direct":
        return f"Prepare {target.summary} retrospective", "high", "next_week"
    return f"Prepare {target.summary} review", "medium", "later"


def _exact_comment_for(target: _WorkspaceItem) -> str:
    return f"Status: {target.query} is ready for review."


def _task_title_is_allowed(title: str) -> bool:
    return (
        title == title.strip()
        and 12 <= len(title) <= 120
        and "\n" not in title
        and "\r" not in title
        and title.casefold().startswith(("prepare ", "review ", "create "))
    )


def _comment_is_allowed(comment: str) -> bool:
    return (
        comment == comment.strip()
        and 12 <= len(comment) <= 240
        and "\n" not in comment
        and "\r" not in comment
        and comment.casefold().startswith("status:")
    )


def _created_task_id(project_id: str, title: str) -> str:
    digest = hashlib.sha256(_canonical_json_bytes([project_id, title])).hexdigest()[:24]
    return f"workspace-task-{digest}"


def _created_comment_id(task_id: str, comment: str) -> str:
    digest = hashlib.sha256(_canonical_json_bytes([task_id, comment])).hexdigest()[:24]
    return f"workspace-comment-{digest}"


def _target_item_observed(
    events: tuple[EpisodeEvent, ...],
    case: _WorkspaceCase,
) -> bool:
    return case.target is not None and any(
        event.event_type == "observation"
        and event.tool_name == "search_workspace_items"
        and event.observation == _item_observation(case.target)
        for event in events
    )


def _route_completed(events: tuple[EpisodeEvent, ...], case: _WorkspaceCase) -> bool:
    if case.target is None:
        return False
    target_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "observation"
        and event.tool_name == "search_workspace_items"
        and event.observation == _item_observation(case.target)
    ]
    if not target_indexes:
        return False
    target_index = target_indexes[0]
    if case.route in {"direct", "verify"}:
        return True
    if case.route == "directory":
        return any(
            index < target_index
            for index, event in enumerate(events)
            if event.event_type == "observation"
            and event.tool_name == "list_workspace_projects"
        )
    stale_action_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "action"
        and event.tool_name == "search_workspace_items"
        and event.arguments
        == {"query": _recovery_probe(case.target.query), "kind": case.target.kind}
    ]
    stale_failure_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "error"
        and event.tool_name == "search_workspace_items"
        and event.error_code == "item_not_found"
    ]
    return any(
        stale_action < stale_failure < target_index
        for stale_action in stale_action_indexes
        for stale_failure in stale_failure_indexes
    )


def _state_change_evidence(kind: str, target: _WorkspaceItem) -> str:
    digest = hashlib.sha256(_canonical_json_bytes(_item_record(target))).hexdigest()
    return f"{kind}:sha256:{digest}"


def _item_query_is_unique(target: _WorkspaceItem, items: dict[str, _WorkspaceItem]) -> bool:
    return sum(
        candidate.kind == target.kind and candidate.query == target.query
        for candidate in items.values()
    ) == 1


def _query_for(kind: str, summary: str) -> str:
    normalized = summary.casefold()
    if kind == "task":
        return re.sub(
            r"^(?:complete|finalize|prepare|review|schedule|summarize)\s+",
            "",
            normalized,
        )
    return normalized


def _missing_document_query_for(items: dict[str, _WorkspaceItem]) -> str:
    occupied_queries = {
        item.query for item in items.values() if item.kind == "document"
    }
    base_query = "archived roadmap"
    candidate = base_query
    suffix = 1
    while candidate in occupied_queries:
        candidate = f"{base_query} unavailable {suffix}"
        suffix += 1
    return candidate


def _recovery_probe(query: str) -> str:
    return f"{query} (stale)"


def _action_is_negated(action: str) -> bool:
    normalized = action.casefold().replace("-", "_")
    return (
        normalized.startswith(("do_not_", "dont_", "never_", "not_", "without_"))
        or "_not_" in normalized
        or normalized.endswith("_not")
    )


def _text_requests_negation(content: str) -> bool:
    return bool(
        re.search(r"\b(?:do\s+not|don't|never|without)\b", content, flags=re.IGNORECASE)
    )


def _final_response(events: tuple[EpisodeEvent, ...]) -> str | None:
    return next(
        (
            event.content
            for event in reversed(events)
            if event.event_type == "final_response"
        ),
        None,
    )


def _sorted_items(items: dict[str, _WorkspaceItem]) -> tuple[_WorkspaceItem, ...]:
    return tuple(item for _, item in sorted(items.items()))


def _sorted_items_by_search_preference(
    items: dict[str, _WorkspaceItem],
) -> tuple[_WorkspaceItem, ...]:
    kind_order = {"document": 0, "project": 1, "task": 2, "comment": 3}
    return tuple(
        sorted(
            items.values(),
            key=lambda item: (kind_order.get(item.kind, len(kind_order)), item.item_id),
        )
    )


def _json_object(contents: bytes) -> dict[str, object]:
    try:
        payload = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Workspace Tasks source must be valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Workspace Tasks source must be a JSON object")
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
