"""Mobile Messages implementation of the provisional Agent-first Domain seam.

This module owns Mobile fixture semantics, compilation, isolated state, and
assessment.  The shared Agent-first core sees only the generic adapter protocol.
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
    ToolDefinition,
)


_FIXTURE_SOURCE = {
    "messages": [
        {
            "message_id": "message-aurora-001",
            "sender": "Alex Kim",
            "body": "Please review the launch checklist before Friday.",
        },
        {
            "message_id": "message-invoice-002",
            "sender": "Bella Chen",
            "body": "Could you check the invoice before Monday?",
        },
    ],
    "reminders": [],
    "drafts": [],
}


type _MobileAction = Literal[
    "search_messages",
    "create_reminder",
    "create_draft_reply",
]
type _Route = Literal["direct", "directory", "recovery", "verify"]
type _ReplyConstraint = Literal["none", "open", "exact"]

_MOBILE_ACTIONS = frozenset({"search_messages", "create_reminder", "create_draft_reply"})
_ROUTES = frozenset({"direct", "directory", "recovery", "verify"})
_REPLY_CONSTRAINTS = frozenset({"none", "open", "exact"})


@dataclass(frozen=True)
class _Message:
    message_id: str
    sender: str
    body: str


@dataclass(frozen=True)
class _Reminder:
    message_id: str
    reminder_text: str
    remind_at: str


@dataclass(frozen=True)
class _InitialState:
    messages: dict[str, _Message]
    reminders: dict[str, _Reminder]
    drafts: dict[str, str]


@dataclass(frozen=True)
class _MobileCase:
    target: _Message
    action: _MobileAction = "search_messages"
    route: _Route = "direct"
    reminder_text: str | None = None
    remind_at: str | None = None
    reply_constraint: _ReplyConstraint = "none"
    exact_reply: str | None = None


@dataclass(frozen=True)
class _TaskSpec:
    slot_kind: str
    action: _MobileAction
    route: _Route
    reply_constraint: _ReplyConstraint = "none"


@dataclass(frozen=True)
class MobileMessagesStructuralExample:
    """A reviewed equivalence or distinction for the Mobile Messages taxonomy."""

    example_id: str
    expected_structural_key: str
    variation: str


@dataclass(frozen=True)
class MobileMessagesSlotCapacity:
    """Finite deterministic task-space capacity for one frozen message source."""

    known_task_capacity: int
    requested_limit: int
    emitted_slot_count: int
    exhausted: bool


_TASK_SPECS = (
    _TaskSpec("search-direct", "search_messages", "direct"),
    _TaskSpec("search-directory", "search_messages", "directory"),
    _TaskSpec("search-recovery", "search_messages", "recovery"),
    _TaskSpec("reminder-direct", "create_reminder", "direct"),
    _TaskSpec("reminder-directory", "create_reminder", "directory"),
    _TaskSpec("reminder-recovery", "create_reminder", "recovery"),
    _TaskSpec("reminder-verified", "create_reminder", "verify"),
    _TaskSpec("draft-direct", "create_draft_reply", "direct", "open"),
    _TaskSpec("draft-directory", "create_draft_reply", "directory", "open"),
    _TaskSpec("draft-recovery", "create_draft_reply", "recovery", "open"),
    _TaskSpec("draft-exact", "create_draft_reply", "direct", "exact"),
    _TaskSpec("draft-verified", "create_draft_reply", "verify", "open"),
)


_REVIEWED_STRUCTURAL_EXAMPLES = (
    MobileMessagesStructuralExample(
        "search_direct", "mobile_messages.search.direct", "baseline"
    ),
    MobileMessagesStructuralExample(
        "search_directory", "mobile_messages.search.directory", "baseline"
    ),
    MobileMessagesStructuralExample(
        "search_recovery", "mobile_messages.search.recovery", "baseline"
    ),
    MobileMessagesStructuralExample(
        "reminder_direct", "mobile_messages.reminder.direct", "baseline"
    ),
    MobileMessagesStructuralExample(
        "reminder_directory", "mobile_messages.reminder.directory", "baseline"
    ),
    MobileMessagesStructuralExample(
        "reminder_recovery", "mobile_messages.reminder.recovery", "baseline"
    ),
    MobileMessagesStructuralExample(
        "reminder_verified", "mobile_messages.reminder.verified", "baseline"
    ),
    MobileMessagesStructuralExample(
        "draft_direct", "mobile_messages.draft.direct", "baseline"
    ),
    MobileMessagesStructuralExample(
        "draft_directory", "mobile_messages.draft.directory", "baseline"
    ),
    MobileMessagesStructuralExample(
        "draft_recovery", "mobile_messages.draft.recovery", "baseline"
    ),
    MobileMessagesStructuralExample(
        "draft_exact", "mobile_messages.draft.exact", "baseline"
    ),
    MobileMessagesStructuralExample(
        "draft_verified", "mobile_messages.draft.verified", "baseline"
    ),
    MobileMessagesStructuralExample(
        "search_direct_paraphrase", "mobile_messages.search.direct", "paraphrase"
    ),
    MobileMessagesStructuralExample(
        "search_direct_entity_swap",
        "mobile_messages.search.direct",
        "entity_substitution",
    ),
    MobileMessagesStructuralExample(
        "search_direct_padded_tools",
        "mobile_messages.search.direct",
        "padded_tool_sequence",
    ),
)


def _task_specs_for_message(
    message: _Message,
    initial_state: _InitialState,
) -> tuple[_TaskSpec, ...]:
    """Keep safe read slots while omitting mutations that would overwrite state."""

    return tuple(
        spec
        for spec in _TASK_SPECS
        if not (
            spec.action == "create_reminder" and message.message_id in initial_state.reminders
        )
        and not (
            spec.action == "create_draft_reply" and message.message_id in initial_state.drafts
        )
    )


class MobileMessagesDomainAdapter:
    """A fixture-backed Mobile Messages adapter with no shared-core schema leak."""

    domain_id = "mobile_messages"
    domain_version = "mobile_messages_agent_adapter_v1"

    def __init__(self, source_contents: bytes) -> None:
        if not isinstance(source_contents, bytes) or not source_contents:
            raise ValueError("Mobile Messages adapter requires non-empty source bytes")
        self._source_contents = bytes(source_contents)

    @classmethod
    def fixture(cls) -> "MobileMessagesDomainAdapter":
        return cls(_canonical_json_bytes(_FIXTURE_SOURCE))

    @classmethod
    def from_local_file(cls, path: Path | str) -> "MobileMessagesDomainAdapter":
        return cls(Path(path).read_bytes())

    def open_run(self, configuration: RunConfiguration) -> "MobileMessagesDomainRun":
        del configuration
        return MobileMessagesDomainRun(_parse_source(self._source_contents))

    @property
    def reviewed_structural_examples(self) -> tuple[MobileMessagesStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES


class MobileMessagesDomainRun:
    """Run-scoped Mobile Messages planning and source normalization."""

    def __init__(self, initial_state: _InitialState) -> None:
        self._initial_state = _copy_initial_state(initial_state)
        self._messages = dict(initial_state.messages)
        self._normalized_state = _canonical_json_bytes(
            {
                "messages": [
                    _message_record(message) for message in _sorted_messages(self._messages)
                ],
                "reminders": [
                    _reminder_record(reminder)
                    for _, reminder in sorted(initial_state.reminders.items())
                ],
                "drafts": [
                    {"message_id": message_id, "content": content}
                    for message_id, content in sorted(initial_state.drafts.items())
                ],
            }
        )

    @property
    def known_task_capacity(self) -> int:
        return sum(
            len(_task_specs_for_message(message, self._initial_state))
            for message in self._messages.values()
        )

    @property
    def reviewed_structural_examples(self) -> tuple[MobileMessagesStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES

    def slot_capacity(self, limit: int) -> MobileMessagesSlotCapacity:
        if limit < 0:
            raise ValueError("slot capacity limit must not be negative")
        capacity = self.known_task_capacity
        return MobileMessagesSlotCapacity(
            known_task_capacity=capacity,
            requested_limit=limit,
            emitted_slot_count=min(limit, capacity),
            exhausted=limit >= capacity,
        )

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        if limit < 0:
            raise ValueError("slot limit must not be negative")
        slots = tuple(
            TaskSlot(
                slot_id=self._slot_id(spec, message),
                proposal_prompt=(
                    "Return exactly this JSON proposal: "
                    + json.dumps(_proposal_payload(spec, message), sort_keys=True)
                ),
            )
            for message in _sorted_messages(self._messages)
            for spec in _task_specs_for_message(message, self._initial_state)
        )
        return slots[:limit]

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
        try:
            payload = json.loads(proposal.content)
        except json.JSONDecodeError:
            if _text_requests_negation(proposal.content):
                return _compilation_rejection("negated_action")
            return _compilation_rejection("proposal_not_json")
        if not isinstance(payload, dict):
            return _compilation_rejection("proposal_not_object")
        spec, target = slot_spec
        action = payload.get("action")
        if not isinstance(action, str):
            return _compilation_rejection("unsupported_requested_action")
        if payload.get("negated") is True or _action_is_negated(action):
            return _compilation_rejection("negated_action")
        if any(name in payload for name in ("message_id", "target_message_id")):
            return _compilation_rejection("unsupported_private_exact_target")
        if action != spec.action:
            return _compilation_rejection("unsupported_requested_action")
        if payload.get("route") != spec.route:
            return _compilation_rejection("uncheckable_condition")
        if spec.action == "search_messages":
            if payload != _proposal_payload(spec, target):
                return _compilation_rejection("unsupported_requested_action")
            case = _MobileCase(target=target, action=spec.action, route=spec.route)
        else:
            if payload.get("message_query") != _query_for(target):
                return _compilation_rejection("wrong_message_binding")
            if spec.action == "create_reminder":
                compiled = self._compile_reminder(spec, target, payload)
            else:
                compiled = self._compile_draft(spec, target, payload)
            if isinstance(compiled, CompilationRejection):
                return compiled
            case = compiled
        return CompiledTask(
            public_task=_public_task(case),
            semantic_key=_semantic_key(case),
            private_case_bytes=_private_case_bytes(case),
            domain_case=case,
        )

    def _compile_reminder(
        self,
        spec: _TaskSpec,
        target: _Message,
        payload: dict[str, object],
    ) -> _MobileCase | CompilationRejection:
        if "condition" not in payload:
            return _compilation_rejection("missing_mutation_authority")
        if payload.get("condition") != "after_message_match":
            return _compilation_rejection("uncheckable_condition")
        reminder_text = payload.get("reminder_text")
        remind_at = payload.get("remind_at")
        if not isinstance(reminder_text, str) or not isinstance(remind_at, str):
            return _compilation_rejection("missing_mutation_argument")
        if reminder_text != _reminder_text_for(target) or remind_at != _remind_at_for(target):
            return _compilation_rejection("unauthorized_reminder_argument")
        if set(payload) != {
            "action",
            "condition",
            "message_query",
            "remind_at",
            "reminder_text",
            "route",
        }:
            return _compilation_rejection("unsupported_requested_action")
        return _MobileCase(
            target=target,
            action=spec.action,
            route=spec.route,
            reminder_text=reminder_text,
            remind_at=remind_at,
        )

    def _compile_draft(
        self,
        spec: _TaskSpec,
        target: _Message,
        payload: dict[str, object],
    ) -> _MobileCase | CompilationRejection:
        if "condition" not in payload:
            return _compilation_rejection("missing_mutation_authority")
        if payload.get("condition") != "after_message_match":
            return _compilation_rejection("uncheckable_condition")
        if payload.get("reply_constraint") != spec.reply_constraint:
            return _compilation_rejection("unsupported_reply")
        exact_reply: str | None = None
        allowed_fields = {
            "action",
            "condition",
            "message_query",
            "reply_constraint",
            "route",
        }
        if spec.reply_constraint == "exact":
            reply = payload.get("reply")
            if not isinstance(reply, str) or not _reply_is_allowed(reply):
                return _compilation_rejection("unsupported_reply")
            exact_reply = reply
            allowed_fields.add("reply")
        elif "reply" in payload:
            return _compilation_rejection("unsupported_reply")
        if set(payload) != allowed_fields:
            return _compilation_rejection("unsupported_requested_action")
        return _MobileCase(
            target=target,
            action=spec.action,
            route=spec.route,
            reply_constraint=spec.reply_constraint,
            exact_reply=exact_reply,
        )

    def _slot_spec(self, slot_id: str) -> tuple[_TaskSpec, _Message] | None:
        for message in _sorted_messages(self._messages):
            for spec in _task_specs_for_message(message, self._initial_state):
                if slot_id == self._slot_id(spec, message):
                    return spec, message
        return None

    @staticmethod
    def _slot_id(spec: _TaskSpec, message: _Message) -> str:
        return f"mobile-{spec.slot_kind}-{_slot_slug(message.message_id)}"

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "MobileMessagesEpisode":
        return MobileMessagesEpisode(
            _case_from_task(task), _initial_state_from_frozen_state(frozen_initial_state)
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        case = _case_from_private_bytes(private_case_bytes)
        if semantic_key != _semantic_key(case):
            raise ValueError("private Mobile Messages semantic key does not match task case")
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
    ) -> "MobileMessagesEpisode":
        return self.open_episode(task, frozen_initial_state)


class MobileMessagesEpisode:
    """Candidate-local Mobile Messages state rebuilt from frozen source bytes."""

    def __init__(self, case: _MobileCase, initial_state: _InitialState) -> None:
        self._case = case
        self._messages = dict(initial_state.messages)
        self._reminders = dict(initial_state.reminders)
        self._drafts = dict(initial_state.drafts)
        self._target_observed = False
        self._directory_seen = False
        self._target_after_directory = False
        self._recovery_probe_failed = False

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        if tool_name == "search_messages":
            return self._search_messages(arguments)
        if tool_name == "list_message_senders":
            self._directory_seen = True
            return ToolExecutionResult(
                result_type="observation",
                observation={"senders": sorted({message.sender for message in self._messages.values()})},
            )
        if tool_name == "create_reminder":
            return self._create_reminder(arguments)
        if tool_name == "get_reminder":
            return self._get_reminder(arguments)
        if tool_name == "create_draft_reply":
            return self._create_draft_reply(arguments)
        if tool_name == "get_draft_reply":
            return self._get_draft_reply(arguments)
        return ToolExecutionResult(result_type="tool_failure", error_code="unknown_tool")

    def _search_messages(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        query = arguments.get("query")
        if not isinstance(query, str):
            return ToolExecutionResult(
                result_type="tool_failure", error_code="invalid_search_query"
            )
        if query == _recovery_probe(_query_for(self._case.target)):
            self._recovery_probe_failed = True
            return ToolExecutionResult(result_type="tool_failure", error_code="message_not_found")
        matches = [
            message
            for message in self._messages.values()
            if query.casefold() in message.body.casefold()
        ]
        if len(matches) != 1:
            return ToolExecutionResult(result_type="tool_failure", error_code="message_not_found")
        message = matches[0]
        if message.message_id == self._case.target.message_id:
            self._target_observed = True
            self._target_after_directory = self._directory_seen
        return ToolExecutionResult(result_type="observation", observation=_message_record(message))

    def _create_reminder(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        message_id = arguments.get("message_id")
        reminder_text = arguments.get("reminder_text")
        remind_at = arguments.get("remind_at")
        if self._case.action != "create_reminder" or message_id != self._case.target.message_id:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="mutation_not_authorized"
            )
        if not self._route_authorized_for_mutation():
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_condition_not_observed",
            )
        if (
            not isinstance(reminder_text, str)
            or not isinstance(remind_at, str)
            or reminder_text != self._case.reminder_text
            or remind_at != self._case.remind_at
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="reminder_not_authorized"
            )
        assert isinstance(message_id, str)
        if message_id in self._reminders:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        reminder = _Reminder(message_id, reminder_text, remind_at)
        self._reminders[message_id] = reminder
        return ToolExecutionResult(
            result_type="state_change", change=_reminder_record(reminder)
        )

    def _get_reminder(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        message_id = arguments.get("message_id")
        if not isinstance(message_id, str) or message_id not in self._reminders:
            return ToolExecutionResult(result_type="tool_failure", error_code="reminder_not_found")
        return ToolExecutionResult(
            result_type="observation", observation=_reminder_record(self._reminders[message_id])
        )

    def _create_draft_reply(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        message_id = arguments.get("message_id")
        content = arguments.get("content")
        if self._case.action != "create_draft_reply" or message_id != self._case.target.message_id:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="mutation_not_authorized"
            )
        if not self._route_authorized_for_mutation():
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_condition_not_observed",
            )
        if not isinstance(content, str) or not _reply_is_allowed(content):
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unsupported_reply"
            )
        if self._case.reply_constraint == "exact" and content != self._case.exact_reply:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="reply_not_authorized"
            )
        assert isinstance(message_id, str)
        if message_id in self._drafts:
            return ToolExecutionResult(
                result_type="unauthorized_mutation", error_code="unintended_state_change"
            )
        self._drafts[message_id] = content
        return ToolExecutionResult(
            result_type="state_change",
            change={"message_id": message_id, "content": content},
        )

    def _get_draft_reply(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        message_id = arguments.get("message_id")
        if not isinstance(message_id, str) or message_id not in self._drafts:
            return ToolExecutionResult(result_type="tool_failure", error_code="draft_not_found")
        return ToolExecutionResult(
            result_type="observation",
            observation={"message_id": message_id, "content": self._drafts[message_id]},
        )

    def _route_authorized_for_mutation(self) -> bool:
        if not self._target_observed:
            return False
        if self._case.route == "directory":
            return self._target_after_directory
        if self._case.route == "recovery":
            return self._recovery_probe_failed and self._target_after_directory
        return True

    def assess(self, trace: ExecutionTrace) -> EpisodeAssessment:
        if self._case.action == "create_reminder":
            return self._assess_reminder(trace)
        if self._case.action == "create_draft_reply":
            return self._assess_draft(trace)
        return self._assess_search(trace)

    def _assess_search(self, trace: ExecutionTrace) -> EpisodeAssessment:
        observed = _target_message_observed(trace.events, self._case)
        route_completed = _route_completed(trace.events, self._case)
        final_content = _final_response(trace.events)
        grounded = (
            isinstance(final_content, str)
            and self._case.target.sender.casefold() in final_content.casefold()
            and _query_for(self._case.target).casefold() in final_content.casefold()
        )
        no_unintended_state_changes = not any(
            event.event_type == "state_change" for event in trace.events
        )
        checks = (
            AssessmentCheck(
                name="requested_message_observed", passed=observed and route_completed
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
                    ("requested_message_not_observed", observed and route_completed),
                    ("unintended_state_change", no_unintended_state_changes),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("search", self._case.route),
            structural_key=f"mobile_messages.search.{self._case.route}",
        )

    def _assess_reminder(self, trace: ExecutionTrace) -> EpisodeAssessment:
        lookup_completed = _target_message_observed(trace.events, self._case) and _route_completed(
            trace.events, self._case
        )
        state_changes = [event for event in trace.events if event.event_type == "state_change"]
        changes = [event.change for event in state_changes if event.tool_name == "create_reminder"]
        requested_change = changes[0] if len(changes) == 1 else None
        expected_change = _reminder_record(
            _Reminder(
                self._case.target.message_id,
                self._case.reminder_text or "",
                self._case.remind_at or "",
            )
        )
        requested_effect = requested_change == expected_change
        no_unintended_changes = len(state_changes) == 1 and len(changes) == 1
        authorized = trace.mutation_authorization == "authorized"
        verified = (
            self._case.route != "verify"
            or any(
                event.event_type == "observation"
                and event.tool_name == "get_reminder"
                and event.observation == requested_change
                for event in trace.events
            )
        )
        grounded = _final_response_is_grounded(
            trace.events,
            self._case,
            required_values=(self._case.reminder_text or "", self._case.remind_at or ""),
        )
        checks = (
            AssessmentCheck(name="message_condition_observed", passed=lookup_completed),
            AssessmentCheck(name="authorized_mutation", passed=authorized),
            AssessmentCheck(name="requested_reminder_recorded", passed=requested_effect),
            AssessmentCheck(name="no_unintended_state_changes", passed=no_unintended_changes),
            AssessmentCheck(name="saved_reminder_observed", passed=verified),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("message_condition_not_observed", lookup_completed),
                    ("mutation_not_authorized", authorized),
                    ("requested_reminder_not_recorded", requested_effect),
                    ("unintended_state_change", no_unintended_changes),
                    ("saved_reminder_not_observed", verified),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("reminder", self._case.route),
            structural_key=(
                "mobile_messages.reminder.verified"
                if self._case.route == "verify"
                else f"mobile_messages.reminder.{self._case.route}"
            ),
            state_change_evidence=f"reminder:{self._case.target.message_id}",
        )

    def _assess_draft(self, trace: ExecutionTrace) -> EpisodeAssessment:
        lookup_completed = _target_message_observed(trace.events, self._case) and _route_completed(
            trace.events, self._case
        )
        state_changes = [event for event in trace.events if event.event_type == "state_change"]
        changes = [event.change for event in state_changes if event.tool_name == "create_draft_reply"]
        requested_change = changes[0] if len(changes) == 1 else None
        content = requested_change.get("content") if isinstance(requested_change, dict) else None
        requested_effect = (
            isinstance(requested_change, dict)
            and requested_change.get("message_id") == self._case.target.message_id
            and isinstance(content, str)
            and (
                content == self._case.exact_reply
                if self._case.reply_constraint == "exact"
                else _reply_is_allowed(content)
            )
        )
        no_unintended_changes = len(state_changes) == 1 and len(changes) == 1
        authorized = trace.mutation_authorization == "authorized"
        verified = (
            self._case.route != "verify"
            or any(
                event.event_type == "observation"
                and event.tool_name == "get_draft_reply"
                and event.observation == requested_change
                for event in trace.events
            )
        )
        grounded = _final_response_is_grounded(
            trace.events,
            self._case,
            required_values=(content,) if isinstance(content, str) else (),
        )
        checks = (
            AssessmentCheck(name="message_condition_observed", passed=lookup_completed),
            AssessmentCheck(name="authorized_mutation", passed=authorized),
            AssessmentCheck(name="requested_draft_recorded", passed=requested_effect),
            AssessmentCheck(name="no_unintended_state_changes", passed=no_unintended_changes),
            AssessmentCheck(name="saved_draft_observed", passed=verified),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("message_condition_not_observed", lookup_completed),
                    ("mutation_not_authorized", authorized),
                    ("requested_draft_not_recorded", requested_effect),
                    ("unintended_state_change", no_unintended_changes),
                    ("saved_draft_not_observed", verified),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("draft", self._case.route, self._case.reply_constraint),
            structural_key=(
                "mobile_messages.draft.verified"
                if self._case.route == "verify"
                else (
                    "mobile_messages.draft.exact"
                    if self._case.reply_constraint == "exact"
                    else f"mobile_messages.draft.{self._case.route}"
                )
            ),
            state_change_evidence=f"draft:{self._case.target.message_id}",
        )


def _public_task(case: _MobileCase) -> PublicTask:
    if case.action == "search_messages":
        return _search_public_task(case)
    if case.action == "create_reminder":
        return _reminder_public_task(case)
    return _draft_public_task(case)


def _search_public_task(case: _MobileCase) -> PublicTask:
    query = _query_for(case.target)
    if case.route == "directory":
        instruction = (
            f'Use the sender list to identify {case.target.sender}, then find the message '
            f'that mentions "{query}".'
        )
    elif case.route == "recovery":
        instruction = (
            f'A stale message query may fail. First search for "{_recovery_probe(query)}". '
            f'If it reports no message, use the sender list to identify {case.target.sender}, '
            f'then find the message that mentions "{query}".'
        )
    else:
        instruction = f'Find the message from {case.target.sender} that mentions "{query}".'
    tools: list[ToolDefinition] = [_search_tool()]
    if case.route in {"directory", "recovery"}:
        tools.append(_sender_list_tool())
    return PublicTask(instruction=instruction, tools=tuple(tools))


def _reminder_public_task(case: _MobileCase) -> PublicTask:
    assert case.reminder_text is not None
    assert case.remind_at is not None
    search_task = _search_public_task(
        _MobileCase(
            target=case.target,
            route="direct" if case.route == "verify" else case.route,
        )
    )
    tools = [*search_task.tools, _create_reminder_tool()]
    if case.route == "verify":
        tools.append(_get_reminder_tool())
    verification_request = (
        " Then retrieve the saved reminder and report its text and time."
        if case.route == "verify"
        else ""
    )
    return PublicTask(
        instruction=(
            f"{search_task.instruction} After finding the selected message, create a reminder "
            f'for {case.remind_at} that says "{case.reminder_text}".{verification_request}'
        ),
        tools=tuple(tools),
    )


def _draft_public_task(case: _MobileCase) -> PublicTask:
    search_task = _search_public_task(
        _MobileCase(
            target=case.target,
            route="direct" if case.route == "verify" else case.route,
        )
    )
    reply_request = (
        f'Draft exactly this reply: "{case.exact_reply}".'
        if case.reply_constraint == "exact"
        else "Draft a brief courteous reply."
    )
    tools = [*search_task.tools, _create_draft_reply_tool()]
    if case.route == "verify":
        tools.append(_get_draft_reply_tool())
    verification_request = (
        " Then retrieve the saved draft and report its content."
        if case.route == "verify"
        else ""
    )
    return PublicTask(
        instruction=(
            f"{search_task.instruction} After finding the selected message, {reply_request}"
            f"{verification_request}"
        ),
        tools=tuple(tools),
    )


def _search_tool() -> ToolDefinition:
    return ToolDefinition(
        name="search_messages",
        description="Find one message by a public text query.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "sender": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    )


def _sender_list_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_message_senders",
        description="List senders represented in the local message collection.",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"senders": {"type": "array"}}},
    )


def _create_reminder_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_reminder",
        description="Create one reminder for a message observed in this Episode.",
        input_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "reminder_text": {"type": "string"},
                "remind_at": {"type": "string"},
            },
            "required": ["message_id", "reminder_text", "remind_at"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "reminder_text": {"type": "string"},
                "remind_at": {"type": "string"},
            },
        },
    )


def _get_reminder_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_reminder",
        description="Retrieve the saved reminder for one message.",
        input_schema={
            "type": "object",
            "properties": {"message_id": {"type": "string"}},
            "required": ["message_id"],
        },
        output_schema=_create_reminder_tool().output_schema,
    )


def _create_draft_reply_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_draft_reply",
        description="Create one reply draft for a message observed in this Episode.",
        input_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["message_id", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "content": {"type": "string"},
            },
        },
    )


def _get_draft_reply_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_draft_reply",
        description="Retrieve the saved reply draft for one message.",
        input_schema={
            "type": "object",
            "properties": {"message_id": {"type": "string"}},
            "required": ["message_id"],
        },
        output_schema=_create_draft_reply_tool().output_schema,
    )


def _proposal_payload(spec: _TaskSpec, target: _Message) -> dict[str, str]:
    if spec.action == "search_messages":
        return {
            "action": spec.action,
            "query": _query_for(target),
            "route": spec.route,
        }
    payload = {
        "action": spec.action,
        "condition": "after_message_match",
        "message_query": _query_for(target),
        "route": spec.route,
    }
    if spec.action == "create_reminder":
        payload["reminder_text"] = _reminder_text_for(target)
        payload["remind_at"] = _remind_at_for(target)
    else:
        payload["reply_constraint"] = spec.reply_constraint
        if spec.reply_constraint == "exact":
            payload["reply"] = _exact_reply_for(target)
    return payload


def _private_case_bytes(case: _MobileCase) -> bytes:
    return _canonical_json_bytes(
        {
            "action": case.action,
            "body": case.target.body,
            "exact_reply": case.exact_reply,
            "message_id": case.target.message_id,
            "remind_at": case.remind_at,
            "reminder_text": case.reminder_text,
            "reply_constraint": case.reply_constraint,
            "route": case.route,
            "sender": case.target.sender,
        }
    )


def _case_from_private_bytes(private_case_bytes: bytes) -> _MobileCase:
    payload = _json_object(private_case_bytes)
    message_id = payload.get("message_id")
    sender = payload.get("sender")
    body = payload.get("body")
    action = payload.get("action")
    route = payload.get("route")
    reply_constraint = payload.get("reply_constraint")
    reminder_text = payload.get("reminder_text")
    remind_at = payload.get("remind_at")
    exact_reply = payload.get("exact_reply")
    if (
        not isinstance(message_id, str)
        or not isinstance(sender, str)
        or not isinstance(body, str)
        or not isinstance(action, str)
        or not isinstance(route, str)
        or not isinstance(reply_constraint, str)
        or (reminder_text is not None and not isinstance(reminder_text, str))
        or (remind_at is not None and not isinstance(remind_at, str))
        or (exact_reply is not None and not isinstance(exact_reply, str))
        or action not in _MOBILE_ACTIONS
        or route not in _ROUTES
        or reply_constraint not in _REPLY_CONSTRAINTS
    ):
        raise ValueError("invalid private Mobile Messages task case")
    if (
        (action == "search_messages" and (reply_constraint != "none" or any(value is not None for value in (reminder_text, remind_at, exact_reply))))
        or (action == "create_reminder" and (reply_constraint != "none" or not isinstance(reminder_text, str) or not isinstance(remind_at, str) or exact_reply is not None))
        or (action == "create_draft_reply" and (reply_constraint not in {"open", "exact"} or reminder_text is not None or remind_at is not None))
        or (reply_constraint == "exact" and (not isinstance(exact_reply, str) or not _reply_is_allowed(exact_reply)))
        or (reply_constraint != "exact" and exact_reply is not None)
    ):
        raise ValueError("invalid private Mobile Messages task case")
    return _MobileCase(
        target=_Message(message_id=message_id, sender=sender, body=body),
        action=cast(_MobileAction, action),
        route=cast(_Route, route),
        reminder_text=reminder_text,
        remind_at=remind_at,
        reply_constraint=cast(_ReplyConstraint, reply_constraint),
        exact_reply=exact_reply,
    )


def _semantic_key(case: _MobileCase) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "action": case.action,
                "body": case.target.body,
                "exact_reply": case.exact_reply if case.reply_constraint == "exact" else None,
                "message_id": case.target.message_id,
                "remind_at": case.remind_at,
                "reminder_text": case.reminder_text,
                "reply_constraint": case.reply_constraint,
                "route": case.route,
                "sender": case.target.sender,
            }
        )
    ).hexdigest()
    return f"mobile_messages:semantic:sha256:{digest}"


def _message_record(message: _Message) -> dict[str, str]:
    return {
        "message_id": message.message_id,
        "sender": message.sender,
        "body": message.body,
    }


def _reminder_record(reminder: _Reminder) -> dict[str, str]:
    return {
        "message_id": reminder.message_id,
        "reminder_text": reminder.reminder_text,
        "remind_at": reminder.remind_at,
    }


def _target_message_observed(events: tuple[EpisodeEvent, ...], case: _MobileCase) -> bool:
    return any(
        event.event_type == "observation"
        and event.tool_name == "search_messages"
        and event.observation == _message_record(case.target)
        for event in events
    )


def _route_completed(events: tuple[EpisodeEvent, ...], case: _MobileCase) -> bool:
    target_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "observation"
        and event.tool_name == "search_messages"
        and event.observation == _message_record(case.target)
    ]
    if not target_indexes:
        return False
    target_index = target_indexes[0]
    if case.route in {"direct", "verify"}:
        return True
    directory_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "observation"
        and event.tool_name == "list_message_senders"
        and isinstance(event.observation, dict)
        and case.target.sender in event.observation.get("senders", [])
    ]
    if case.route == "directory":
        return any(index < target_index for index in directory_indexes)
    stale_actions = [
        index
        for index, event in enumerate(events)
        if event.event_type == "action"
        and event.tool_name == "search_messages"
        and event.arguments == {"query": _recovery_probe(_query_for(case.target))}
    ]
    stale_failures = [
        index
        for index, event in enumerate(events)
        if event.event_type == "error"
        and event.tool_name == "search_messages"
        and event.error_code == "message_not_found"
    ]
    return any(
        stale_action < stale_failure < directory < target_index
        for stale_action in stale_actions
        for stale_failure in stale_failures
        for directory in directory_indexes
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


def _final_response_is_grounded(
    events: tuple[EpisodeEvent, ...],
    case: _MobileCase,
    *,
    required_values: tuple[str, ...],
) -> bool:
    final_content = _final_response(events)
    return (
        isinstance(final_content, str)
        and case.target.sender.casefold() in final_content.casefold()
        and _query_for(case.target).casefold() in final_content.casefold()
        and all(value.casefold() in final_content.casefold() for value in required_values)
    )


def _compilation_rejection(reason_code: str) -> CompilationRejection:
    return CompilationRejection(
        public_task=PublicTask(
            instruction="The Mobile Messages request could not be compiled.",
            tools=(_search_tool(),),
        ),
        reason_code=reason_code,
    )


def _case_from_task(task: CompiledTask) -> _MobileCase:
    case = task.domain_case
    if not isinstance(case, _MobileCase):
        raise ValueError("invalid Mobile Messages task case")
    return case


def _initial_state_from_frozen_state(state: FrozenInitialState) -> _InitialState:
    return _parse_source(state.contents)


def _parse_source(contents: bytes) -> _InitialState:
    payload = _json_object(contents)
    message_records = payload.get("messages")
    if not isinstance(message_records, list) or not message_records:
        raise ValueError("Mobile Messages source requires non-empty messages")
    messages: dict[str, _Message] = {}
    for record in message_records:
        if not isinstance(record, dict):
            raise ValueError("Mobile Messages source message must be an object")
        message_id = record.get("message_id")
        sender = record.get("sender")
        body = record.get("body")
        if not all(isinstance(value, str) and value.strip() for value in (message_id, sender, body)):
            raise ValueError("Mobile Messages source message requires id, sender, and body")
        assert isinstance(message_id, str)
        assert isinstance(sender, str)
        assert isinstance(body, str)
        if any(len(value) > 1_000 for value in (message_id, sender, body)):
            raise ValueError("Mobile Messages source message fields exceed bounded length")
        if message_id in messages:
            raise ValueError("Mobile Messages source message ids must be unique")
        messages[message_id] = _Message(message_id=message_id, sender=sender, body=body)
    reminders = _parse_reminders(payload.get("reminders", []), messages)
    drafts = _parse_drafts(payload.get("drafts", []), messages)
    return _InitialState(messages=messages, reminders=reminders, drafts=drafts)


def _parse_reminders(
    records: object,
    messages: dict[str, _Message],
) -> dict[str, _Reminder]:
    if not isinstance(records, list):
        raise ValueError("Mobile Messages source reminders must be a list")
    reminders: dict[str, _Reminder] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Mobile Messages source reminder must be an object")
        message_id = record.get("message_id")
        reminder_text = record.get("reminder_text")
        remind_at = record.get("remind_at")
        if (
            not isinstance(message_id, str)
            or message_id not in messages
            or not isinstance(reminder_text, str)
            or not isinstance(remind_at, str)
            or not reminder_text.strip()
            or not remind_at.strip()
            or message_id in reminders
        ):
            raise ValueError("Mobile Messages source reminder is invalid")
        reminders[message_id] = _Reminder(message_id, reminder_text, remind_at)
    return reminders


def _parse_drafts(records: object, messages: dict[str, _Message]) -> dict[str, str]:
    if not isinstance(records, list):
        raise ValueError("Mobile Messages source drafts must be a list")
    drafts: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Mobile Messages source draft must be an object")
        message_id = record.get("message_id")
        content = record.get("content")
        if (
            not isinstance(message_id, str)
            or message_id not in messages
            or not isinstance(content, str)
            or not _reply_is_allowed(content)
            or message_id in drafts
        ):
            raise ValueError("Mobile Messages source draft is invalid")
        drafts[message_id] = content
    return drafts


def _copy_initial_state(initial_state: _InitialState) -> _InitialState:
    return _InitialState(
        messages=dict(initial_state.messages),
        reminders=dict(initial_state.reminders),
        drafts=dict(initial_state.drafts),
    )


def _json_object(contents: bytes) -> dict[str, object]:
    try:
        payload = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Mobile Messages source must be valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Mobile Messages source must be a JSON object")
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _query_for(message: _Message) -> str:
    if "launch checklist" in message.body.casefold():
        return "launch checklist"
    if "invoice" in message.body.casefold():
        return "invoice"
    return message.body


def _reminder_text_for(message: _Message) -> str:
    return f"Review the {_query_for(message)}."


def _remind_at_for(message: _Message) -> str:
    return "2026-10-04T09:00:00Z"


def _exact_reply_for(message: _Message) -> str:
    return f"Thanks, I will review the {_query_for(message)}."


def _reply_is_allowed(reply: str) -> bool:
    normalized = reply.strip()
    courtesy_prefixes = ("thanks", "thank you", "hello", "hi ")
    return (
        normalized == reply
        and 3 <= len(reply) <= 240
        and "\n" not in reply
        and "\r" not in reply
        and reply.casefold().startswith(courtesy_prefixes)
    )


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


def _recovery_probe(query: str) -> str:
    return f"{query} (stale)"


def _slot_slug(value: str) -> str:
    return "-".join(
        part
        for part in "".join(char if char.isalnum() else " " for char in value).casefold().split()
    )


def _sorted_messages(messages: dict[str, _Message]) -> tuple[_Message, ...]:
    return tuple(message for _, message in sorted(messages.items()))
