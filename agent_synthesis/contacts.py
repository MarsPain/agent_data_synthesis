"""Contacts implementation of the provisional Agent-first Domain seam.

The module deliberately owns the Contacts source format, task meaning, and
isolated mutable state.  The shared synthesis engine only sees the generic
``DomainAdapter``/``DomainRun`` protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

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
    "contacts": [
        {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
        {"name": "Ben Carter", "email": "ben.carter@example.test"},
    ],
    "followups": [],
}


type _ContactsAction = Literal["lookup_email", "record_followup"]
type _ContactsRoute = Literal["direct", "directory", "recovery", "verify"]
type _NoteConstraint = Literal["none", "open", "exact"]

_CONTACTS_ACTIONS = frozenset({"lookup_email", "record_followup"})
_CONTACTS_ROUTES = frozenset({"direct", "directory", "recovery", "verify"})
_NOTE_CONSTRAINTS = frozenset({"none", "open", "exact"})


@dataclass(frozen=True)
class _ContactsCase:
    target: str
    expected_email: str
    action: _ContactsAction = "lookup_email"
    route: _ContactsRoute = "direct"
    note_constraint: _NoteConstraint = "none"
    exact_note: str | None = None


@dataclass(frozen=True)
class _ContactsInitialState:
    contacts: dict[str, str]
    followups: dict[str, str]


@dataclass(frozen=True)
class _TaskSpec:
    slot_kind: str
    action: _ContactsAction
    route: _ContactsRoute
    note_constraint: _NoteConstraint = "none"


@dataclass(frozen=True)
class ContactsStructuralExample:
    """A reviewed equivalence or distinction for the Contacts taxonomy."""

    example_id: str
    expected_structural_key: str
    variation: str


@dataclass(frozen=True)
class ContactsSlotCapacity:
    """The Contacts Domain's finite deterministic task-space disclosure."""

    known_task_capacity: int
    requested_limit: int
    emitted_slot_count: int
    exhausted: bool


class ContactsPilotConfiguration(BaseModel):
    """The separately reviewable, provider-free plan for early feasibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pilot_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    target_demonstrations: Literal[8] = 8
    task_attempt_limit: Literal[16] = 16
    total_physical_request_limit: int = Field(ge=1, le=10_000)
    generation_request_limit: int = Field(ge=1, le=10_000)
    agent_request_limit: int = Field(ge=1, le=10_000)
    thinking_mode: Literal["enabled", "disabled"] | None = None
    transport_retry_limit: int = Field(default=2, ge=0, le=2)
    max_output_tokens: int = Field(default=1_024, ge=1, le=32_768)
    max_response_bytes: int = Field(default=64_000, ge=256, le=1_000_000)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @field_validator("pilot_id", "model_id", "model_version")
    @classmethod
    def _reject_secret_shaped_identifiers(cls, value: str) -> str:
        lowered = value.casefold()
        if lowered.startswith(("sk-", "bearer-")) or any(
            marker in lowered
            for marker in (
                "api_key",
                "credential",
                "passwd",
                "password",
                "secret",
                "access_token",
            )
        ):
            raise ValueError("pilot identifiers cannot contain credentials")
        return value

    @model_validator(mode="after")
    def _require_minimum_pilot_request_budget(self) -> "ContactsPilotConfiguration":
        minimum_physical_requests = 1 + self.target_demonstrations
        if self.total_physical_request_limit < minimum_physical_requests:
            raise ValueError("pilot request limit cannot cover generation plus each target")
        if self.agent_request_limit < self.target_demonstrations:
            raise ValueError("pilot agent request limit cannot cover each target")
        return self

    def rehearsal_run_configuration(self) -> RunConfiguration:
        """Build the no-provider rehearsal configuration for the eight target tasks."""

        return self._run_configuration(
            run_id_suffix="offline",
            slot_limit=self.target_demonstrations,
        )

    def attempt_ceiling_run_configuration(self) -> RunConfiguration:
        """Build the capped configuration a separately authorized pilot must use."""

        return self._run_configuration(
            run_id_suffix="attempt-ceiling",
            slot_limit=self.task_attempt_limit,
        )

    def _run_configuration(self, *, run_id_suffix: str, slot_limit: int) -> RunConfiguration:
        return RunConfiguration(
            run_id=f"{self.pilot_id}-{run_id_suffix}",
            domain_id=ContactsDomainAdapter.domain_id,
            model_id=self.model_id,
            slot_limit=slot_limit,
            generation_batch_size=self.target_demonstrations,
            total_request_limit=self.total_physical_request_limit,
            generation_request_limit=self.generation_request_limit,
            agent_request_limit=self.agent_request_limit,
            transport_retry_limit=self.transport_retry_limit,
            max_output_tokens=self.max_output_tokens,
            max_response_bytes=self.max_response_bytes,
            timeout_seconds=self.timeout_seconds,
        )

    def review_record(self) -> dict[str, JsonValue]:
        record = self.model_dump(mode="json")
        record["authorization_status"] = "authorization_required"
        record["collection_purpose"] = "diagnostic_only"
        return record


class ContactsPilotRehearsal(BaseModel):
    """Sanitized offline evidence that a pilot plan can be reviewed first."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["contacts_pilot_rehearsal_v1"] = "contacts_pilot_rehearsal_v1"
    configuration: dict[str, JsonValue]
    source_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_demonstrations: Literal[8]
    task_attempt_limit: Literal[16]
    known_task_capacity: int = Field(ge=0)
    capacity_status: Literal["sufficient", "insufficient"]
    attempt_ceiling_configuration: dict[str, JsonValue]
    authorization_status: Literal["authorization_required"] = "authorization_required"
    collection_purpose: Literal["diagnostic_only"] = "diagnostic_only"
    diagnostic_semantic_groups: tuple[str, ...]
    diagnostic_grounding_groups: tuple[str, ...]


_TASK_SPECS = (
    _TaskSpec("lookup-direct", "lookup_email", "direct"),
    _TaskSpec("lookup-directory", "lookup_email", "directory"),
    _TaskSpec("lookup-recovery", "lookup_email", "recovery"),
    _TaskSpec("followup-open", "record_followup", "direct", "open"),
    _TaskSpec("followup-exact", "record_followup", "direct", "exact"),
    _TaskSpec("followup-directory", "record_followup", "directory", "open"),
    _TaskSpec("followup-recovery", "record_followup", "recovery", "open"),
    _TaskSpec("followup-verified", "record_followup", "verify", "open"),
)


def _task_specs_for_contact(
    target: str,
    existing_followups: dict[str, str],
) -> tuple[_TaskSpec, ...]:
    if target not in existing_followups:
        return _TASK_SPECS
    return tuple(spec for spec in _TASK_SPECS if spec.action == "lookup_email")


_REVIEWED_STRUCTURAL_EXAMPLES = (
    ContactsStructuralExample("lookup_direct", "contacts.lookup.direct", "baseline"),
    ContactsStructuralExample("lookup_directory", "contacts.lookup.directory", "baseline"),
    ContactsStructuralExample("lookup_recovery", "contacts.lookup.recovery", "baseline"),
    ContactsStructuralExample("followup_direct", "contacts.followup.direct", "baseline"),
    ContactsStructuralExample(
        "followup_directory", "contacts.followup.directory", "baseline"
    ),
    ContactsStructuralExample(
        "followup_recovery", "contacts.followup.recovery", "baseline"
    ),
    ContactsStructuralExample(
        "followup_verified", "contacts.followup.verified", "baseline"
    ),
    ContactsStructuralExample(
        "lookup_direct_paraphrase", "contacts.lookup.direct", "paraphrase"
    ),
    ContactsStructuralExample(
        "lookup_direct_entity_swap",
        "contacts.lookup.direct",
        "entity_substitution",
    ),
    ContactsStructuralExample(
        "lookup_direct_redundant_read",
        "contacts.lookup.direct",
        "redundant_read_only_call",
    ),
)


class ContactsDomainAdapter:
    """A fixture-backed Contacts adapter with no dependency on legacy code."""

    domain_id = "contacts"
    domain_version = "contacts_agent_adapter_v1"

    def __init__(self, source_contents: bytes) -> None:
        if not isinstance(source_contents, bytes) or not source_contents:
            raise ValueError("Contacts adapter requires non-empty source bytes")
        self._source_contents = bytes(source_contents)

    @classmethod
    def fixture(cls) -> "ContactsDomainAdapter":
        """Build the deterministic fixture source used for provider-free tests."""

        return cls(_canonical_json_bytes(_FIXTURE_SOURCE))

    @classmethod
    def from_local_file(cls, path: Path | str) -> "ContactsDomainAdapter":
        """Admit local source bytes before a run can dispatch model work."""

        return cls(Path(path).read_bytes())

    def open_run(self, configuration: RunConfiguration) -> "ContactsDomainRun":
        del configuration
        return ContactsDomainRun(_parse_contacts_source(self._source_contents))

    def open_run_from_frozen_state(
        self,
        configuration: RunConfiguration,
        frozen_initial_state: FrozenInitialState,
    ) -> "ContactsDomainRun":
        """Resume from persisted normalized bytes rather than a mutable source path."""

        del configuration
        return ContactsDomainRun(_initial_state_from_frozen_state(frozen_initial_state))

    @property
    def reviewed_structural_examples(self) -> tuple[ContactsStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES


class ContactsDomainRun:
    """Run-scoped Contacts behavior, including private source normalization."""

    def __init__(self, initial_state: _ContactsInitialState) -> None:
        self._contacts = dict(initial_state.contacts)
        self._initial_followups = dict(initial_state.followups)
        self._normalized_state = _canonical_json_bytes(
            {
                "contacts": [
                    {"name": name, "email": email}
                    for name, email in sorted(self._contacts.items())
                ],
                "followups": [
                    {"name": name, "note": note}
                    for name, note in sorted(self._initial_followups.items())
                ],
            }
        )

    @property
    def known_task_capacity(self) -> int:
        """Return the finite number of deterministic task slots for this source."""

        return sum(
            len(_task_specs_for_contact(name, self._initial_followups))
            for name in self._contacts
        )

    @property
    def reviewed_structural_examples(self) -> tuple[ContactsStructuralExample, ...]:
        return _REVIEWED_STRUCTURAL_EXAMPLES

    def slot_capacity(self, limit: int) -> ContactsSlotCapacity:
        """Disclose whether a requested allocation reaches source task exhaustion."""

        if limit < 0:
            raise ValueError("slot capacity limit must not be negative")
        capacity = self.known_task_capacity
        return ContactsSlotCapacity(
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
                slot_id=self._slot_id(spec, name),
                proposal_prompt=(
                    "Return exactly this JSON proposal: "
                    + json.dumps(_proposal_payload(spec, name), sort_keys=True)
                ),
            )
            for name in sorted(self._contacts)
            for spec in _task_specs_for_contact(name, self._initial_followups)
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
        spec, slot_target = slot_spec
        action = payload.get("action")
        if not isinstance(action, str):
            return _compilation_rejection("unsupported_requested_action")
        if payload.get("negated") is True or _action_is_negated(action):
            return _compilation_rejection("negated_action")
        if payload.get("contact") != slot_target:
            return _compilation_rejection("wrong_contact_binding")
        if action != spec.action:
            return _compilation_rejection("unsupported_requested_action")
        if payload.get("route") != spec.route:
            return _compilation_rejection("uncheckable_condition")
        exact_note: str | None = None
        if spec.action == "record_followup":
            if payload.get("condition") != "after_lookup_match":
                return _compilation_rejection("uncheckable_condition")
            if payload.get("note_constraint") != spec.note_constraint:
                return _compilation_rejection("unsupported_note")
            allowed_fields = {
                "action",
                "condition",
                "contact",
                "note_constraint",
                "route",
            }
            if spec.note_constraint == "exact":
                note = payload.get("note")
                if not isinstance(note, str) or not _note_is_allowed(note):
                    return _compilation_rejection("unsupported_note")
                exact_note = note
                allowed_fields.add("note")
            elif "note" in payload:
                return _compilation_rejection("unsupported_note")
            if set(payload) != allowed_fields:
                return _compilation_rejection("unsupported_requested_action")
        elif set(payload) != {"action", "contact", "route"}:
            return _compilation_rejection("unsupported_requested_action")
        case = _ContactsCase(
            target=slot_target,
            expected_email=self._contacts[slot_target],
            action=spec.action,
            route=spec.route,
            note_constraint=spec.note_constraint,
            exact_note=exact_note,
        )
        public_task = (
            _lookup_public_task(case)
            if spec.action == "lookup_email"
            else _followup_public_task(case)
        )
        return CompiledTask(
            public_task=public_task,
            semantic_key=_semantic_key(case),
            private_case_bytes=_canonical_json_bytes(
                {
                    "action": case.action,
                    "expected_email": case.expected_email,
                    "exact_note": case.exact_note,
                    "note_constraint": case.note_constraint,
                    "route": case.route,
                    "target": case.target,
                }
            ),
            domain_case=case,
        )

    def _slot_spec(self, slot_id: str) -> tuple[_TaskSpec, str] | None:
        for target in sorted(self._contacts):
            for spec in _task_specs_for_contact(target, self._initial_followups):
                if slot_id == self._slot_id(spec, target):
                    return spec, target
        return None

    def _slot_id(self, spec: _TaskSpec, target: str) -> str:
        return f"contacts-{spec.slot_kind}-{self._target_slot_component(target)}"

    def _target_slot_component(self, target: str) -> str:
        base = _slot_slug(target)
        if sum(_slot_slug(name) == base for name in self._contacts) == 1:
            return base
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()[:12]
        return f"{base}-{digest}"

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "ContactsEpisode":
        return ContactsEpisode(
            _case_from_task(task), _initial_state_from_frozen_state(frozen_initial_state)
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        payload = _json_object(private_case_bytes)
        target = payload.get("target")
        expected_email = payload.get("expected_email")
        if not isinstance(target, str) or not isinstance(expected_email, str):
            raise ValueError("invalid private Contacts task case")
        action = payload.get("action", "lookup_email")
        route = payload.get("route", "direct")
        note_constraint = payload.get("note_constraint", "none")
        exact_note = payload.get("exact_note")
        if (
            not isinstance(action, str)
            or not isinstance(route, str)
            or not isinstance(note_constraint, str)
            or (exact_note is not None and not isinstance(exact_note, str))
            or action not in _CONTACTS_ACTIONS
            or route not in _CONTACTS_ROUTES
            or note_constraint not in _NOTE_CONSTRAINTS
        ):
            raise ValueError("invalid private Contacts task case")
        if (
            (action == "lookup_email" and (note_constraint != "none" or exact_note is not None))
            or (action == "record_followup" and note_constraint == "none")
            or (note_constraint == "exact" and not _note_is_allowed(exact_note or ""))
            or (note_constraint != "exact" and exact_note is not None)
            or not any(
                spec.action == action
                and spec.route == route
                and spec.note_constraint == note_constraint
                for spec in _TASK_SPECS
            )
        ):
            raise ValueError("invalid private Contacts task case")
        case = _ContactsCase(
            target=target,
            expected_email=expected_email,
            action=cast(_ContactsAction, action),
            route=cast(_ContactsRoute, route),
            note_constraint=cast(_NoteConstraint, note_constraint),
            exact_note=exact_note,
        )
        if semantic_key != _semantic_key(case):
            raise ValueError("private Contacts semantic key does not match task case")
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
    ) -> "ContactsEpisode":
        return self.open_episode(task, frozen_initial_state)


def rehearse_contacts_pilot(
    adapter: ContactsDomainAdapter,
    configuration: ContactsPilotConfiguration,
) -> ContactsPilotRehearsal:
    """Inspect pilot capacity and exclusion groups without model dispatch."""

    if adapter.domain_id != ContactsDomainAdapter.domain_id:
        raise ValueError("Contacts pilot requires the Contacts adapter")
    run = adapter.open_run(configuration.rehearsal_run_configuration())
    frozen_state = run.freeze_initial_state()
    slots = run.slots(configuration.task_attempt_limit)
    semantic_groups = tuple(
        _diagnostic_group_id("semantic", frozen_state.fingerprint, slot.slot_id)
        for slot in slots
    )
    grounding_groups = tuple(
        sorted(
            {
                _diagnostic_group_id("grounding", frozen_state.fingerprint, target)
                for slot in slots
                for slot_spec in (run._slot_spec(slot.slot_id),)
                if slot_spec is not None
                for target in (slot_spec[1],)
            }
        )
    )
    capacity_status: Literal["sufficient", "insufficient"] = (
        "sufficient"
        if run.known_task_capacity >= configuration.target_demonstrations
        else "insufficient"
    )
    return ContactsPilotRehearsal(
        configuration=configuration.review_record(),
        source_fingerprint=frozen_state.fingerprint,
        target_demonstrations=configuration.target_demonstrations,
        task_attempt_limit=configuration.task_attempt_limit,
        known_task_capacity=run.known_task_capacity,
        capacity_status=capacity_status,
        attempt_ceiling_configuration=configuration.attempt_ceiling_run_configuration().model_dump(
            mode="json"
        ),
        diagnostic_semantic_groups=semantic_groups,
        diagnostic_grounding_groups=grounding_groups,
    )


def write_contacts_pilot_rehearsal(
    rehearsal: ContactsPilotRehearsal,
    output_path: Path,
) -> Path:
    """Write only the sanitized, pre-authorization pilot review record."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rehearsal.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


class ContactsEpisode:
    """A candidate-local Contacts environment reconstructed from frozen bytes."""

    def __init__(self, case: _ContactsCase, initial_state: _ContactsInitialState) -> None:
        self._case = case
        self._contacts = dict(initial_state.contacts)
        self._followups = dict(initial_state.followups)
        self._confirmed_target = False
        self._directory_seen = False
        self._target_lookup_after_directory = False
        self._recovery_probe_failed = False

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult:
        if tool_name == "lookup_contact":
            name = arguments.get("name")
            if not isinstance(name, str) or name not in self._contacts:
                if name == _recovery_probe(self._case.target):
                    self._recovery_probe_failed = True
                return ToolExecutionResult(
                    result_type="tool_failure",
                    error_code="contact_not_found",
                )
            if name == self._case.target:
                self._confirmed_target = True
                self._target_lookup_after_directory = self._directory_seen
            return ToolExecutionResult(
                result_type="observation",
                observation={"name": name, "email": self._contacts[name]},
            )
        if tool_name == "list_contacts":
            self._directory_seen = True
            return ToolExecutionResult(
                result_type="observation",
                observation={"contacts": sorted(self._contacts)},
            )
        if tool_name == "record_followup":
            return self._record_followup(arguments)
        if tool_name == "get_followup":
            return self._get_followup(arguments)
        return ToolExecutionResult(result_type="tool_failure", error_code="unknown_tool")

    def _record_followup(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        name = arguments.get("name")
        note = arguments.get("note")
        if self._case.action != "record_followup" or name != self._case.target:
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_not_authorized",
            )
        if not self._route_authorized_for_followup():
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_condition_not_observed",
            )
        if not isinstance(note, str) or not _note_is_allowed(note):
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="unsupported_note",
            )
        if self._case.note_constraint == "exact" and note != self._case.exact_note:
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="note_not_authorized",
            )
        if self._case.target in self._followups:
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="unintended_state_change",
            )
        self._followups[self._case.target] = note
        return ToolExecutionResult(
            result_type="state_change",
            change={"name": self._case.target, "note": note},
        )

    def _get_followup(self, arguments: dict[str, JsonValue]) -> ToolExecutionResult:
        name = arguments.get("name")
        if not isinstance(name, str) or name not in self._followups:
            return ToolExecutionResult(result_type="tool_failure", error_code="followup_not_found")
        return ToolExecutionResult(
            result_type="observation",
            observation={"name": name, "note": self._followups[name]},
        )

    def _route_authorized_for_followup(self) -> bool:
        if not self._confirmed_target:
            return False
        if self._case.route == "directory":
            return self._target_lookup_after_directory
        if self._case.route == "recovery":
            return self._recovery_probe_failed and self._target_lookup_after_directory
        return True

    def assess(self, trace: ExecutionTrace) -> EpisodeAssessment:
        if self._case.action == "record_followup":
            return self._assess_followup(trace)
        observed = any(
            event.event_type == "observation"
            and event.tool_name == "lookup_contact"
            and event.observation == {
                "name": self._case.target,
                "email": self._case.expected_email,
            }
            for event in trace.events
        )
        final_content = next(
            (
                event.content
                for event in reversed(trace.events)
                if event.event_type == "final_response"
            ),
            None,
        )
        grounded = (
            isinstance(final_content, str)
            and self._case.target.casefold() in final_content.casefold()
            and self._case.expected_email.casefold() in final_content.casefold()
        )
        route_completed = _route_completed(trace.events, self._case)
        lookup_completed = observed and route_completed
        no_unintended_state_changes = not any(
            event.event_type == "state_change" for event in trace.events
        )
        checks = (
            AssessmentCheck(name="requested_lookup_observed", passed=lookup_completed),
            AssessmentCheck(
                name="no_unintended_state_changes",
                passed=no_unintended_state_changes,
            ),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("requested_lookup_not_observed", lookup_completed),
                    ("unintended_state_change", no_unintended_state_changes),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("lookup", self._case.route),
            structural_key=f"contacts.lookup.{self._case.route}",
            review_stratification=_review_stratification(
                self._case.action,
                self._case.route,
            ),
        )

    def _assess_followup(self, trace: ExecutionTrace) -> EpisodeAssessment:
        lookup_observed = any(
            event.event_type == "observation"
            and event.tool_name == "lookup_contact"
            and event.observation == {
                "name": self._case.target,
                "email": self._case.expected_email,
            }
            for event in trace.events
        )
        all_state_changes = [
            event
            for event in trace.events
            if event.event_type == "state_change"
        ]
        changes = [
            event.change
            for event in all_state_changes
            if event.tool_name == "record_followup"
        ]
        requested_change = changes[0] if len(changes) == 1 else None
        recorded_note = (
            requested_change.get("note")
            if isinstance(requested_change, dict)
            else None
        )
        requested_effect = (
            isinstance(requested_change, dict)
            and requested_change.get("name") == self._case.target
            and isinstance(recorded_note, str)
            and (
                recorded_note == self._case.exact_note
                if self._case.note_constraint == "exact"
                else _note_is_allowed(recorded_note)
            )
        )
        no_unintended_changes = len(all_state_changes) == 1 and len(changes) == 1
        final_content = next(
            (
                event.content
                for event in reversed(trace.events)
                if event.event_type == "final_response"
            ),
            None,
        )
        grounded = (
            isinstance(final_content, str)
            and self._case.target.casefold() in final_content.casefold()
            and isinstance(recorded_note, str)
            and recorded_note.casefold() in final_content.casefold()
        )
        authorized = trace.mutation_authorization == "authorized"
        route_completed = _route_completed(trace.events, self._case)
        lookup_completed = lookup_observed and route_completed
        verification_observed = (
            self._case.route != "verify"
            or any(
                event.event_type == "observation"
                and event.tool_name == "get_followup"
                and isinstance(event.observation, dict)
                and event.observation.get("name") == self._case.target
                and event.observation.get("note") == recorded_note
                for event in trace.events
            )
        )
        checks = (
            AssessmentCheck(name="lookup_condition_observed", passed=lookup_completed),
            AssessmentCheck(name="authorized_mutation", passed=authorized),
            AssessmentCheck(name="requested_followup_recorded", passed=requested_effect),
            AssessmentCheck(
                name="no_unintended_state_changes", passed=no_unintended_changes
            ),
            AssessmentCheck(name="saved_followup_observed", passed=verification_observed),
            AssessmentCheck(name="final_response_grounded", passed=grounded),
        )
        return EpisodeAssessment(
            passed=all(check.passed for check in checks),
            checks=checks,
            reason_codes=tuple(
                reason
                for reason, passed in (
                    ("lookup_condition_not_observed", lookup_completed),
                    ("mutation_not_authorized", authorized),
                    ("requested_followup_not_recorded", requested_effect),
                    ("unintended_state_change", no_unintended_changes),
                    ("saved_followup_not_observed", verification_observed),
                    ("final_response_not_grounded", grounded),
                )
                if not passed
            ),
            coverage_tags=("followup", self._case.route, self._case.note_constraint),
            structural_key=(
                "contacts.followup.verified"
                if self._case.route == "verify"
                else f"contacts.followup.{self._case.route}"
            ),
            state_change_evidence=f"followup:{_semantic_slug(self._case.target)}",
            review_stratification=_review_stratification(
                self._case.action,
                self._case.route,
            ),
        )


def _review_stratification(
    action: _ContactsAction,
    route: _ContactsRoute,
) -> ReviewStratification:
    return ReviewStratification(
        task_type=action,
        difficulty={
            "direct": "standard",
            "directory": "grounded",
            "recovery": "recovery",
            "verify": "verified_mutation",
        }[route],
    )


def _lookup_public_task(case: _ContactsCase) -> PublicTask:
    target = case.target
    if case.route == "directory":
        instruction = (
            f"Use the contact directory to identify {target}, then find the email address "
            f"for {target}."
        )
    elif case.route == "recovery":
        instruction = (
            f"A stale contact label may fail. First look up '{_recovery_probe(target)}'. "
            f"If it reports no contact, use the contact directory to identify {target}, "
            f"then find the email address for {target}."
        )
    else:
        instruction = f"Find the email address for {target}."
    tools: list[ToolDefinition] = [_lookup_tool()]
    if case.route in {"directory", "recovery"}:
        tools.append(_directory_tool())
    return PublicTask(
        instruction=instruction,
        tools=tuple(tools),
    )


def _followup_public_task(case: _ContactsCase) -> PublicTask:
    if case.note_constraint == "exact":
        assert case.exact_note is not None
        note_request = f'Record exactly this follow-up note: "{case.exact_note}".'
    else:
        note_request = "Record a brief follow-up note."
    lookup_task = _lookup_public_task(
        _ContactsCase(
            target=case.target,
            expected_email=case.expected_email,
            route="direct" if case.route == "verify" else case.route,
        )
    )
    verification_request = (
        " Then retrieve the saved follow-up and report the recorded note."
        if case.route == "verify"
        else ""
    )
    tools = [*lookup_task.tools, _record_followup_tool()]
    if case.route == "verify":
        tools.append(_get_followup_tool())
    return PublicTask(
        instruction=(
            f"{lookup_task.instruction} After the lookup confirms {case.target}, "
            f"{note_request}{verification_request}"
        ),
        tools=tuple(tools),
    )


def _lookup_tool() -> ToolDefinition:
    return ToolDefinition(
        name="lookup_contact",
        description="Look up one contact's email address by name.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
        },
    )


def _directory_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_contacts",
        description="List the available contact names.",
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {"contacts": {"type": "array"}},
        },
    )


def _record_followup_tool() -> ToolDefinition:
    return ToolDefinition(
        name="record_followup",
        description="Record one follow-up note for a confirmed contact.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["name", "note"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
        },
    )


def _get_followup_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_followup",
        description="Retrieve the saved follow-up note for one contact.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
        },
    )


def _proposal_payload(spec: _TaskSpec, target: str) -> dict[str, str]:
    payload = {
        "action": spec.action,
        "contact": target,
        "route": spec.route,
    }
    if spec.action == "record_followup":
        payload["condition"] = "after_lookup_match"
        payload["note_constraint"] = spec.note_constraint
        if spec.note_constraint == "exact":
            payload["note"] = "Please follow up by email."
    return payload


def _semantic_key(case: _ContactsCase) -> str:
    record = {
        "action": case.action,
        "exact_note": case.exact_note if case.note_constraint == "exact" else None,
        "grounding_email": case.expected_email,
        "note_constraint": case.note_constraint,
        "route": case.route,
        "target": case.target,
    }
    digest = hashlib.sha256(_canonical_json_bytes(record)).hexdigest()
    return f"contacts:semantic:sha256:{digest}"


def _note_is_allowed(note: str) -> bool:
    """The public open-note predicate; no private exact note participates."""

    normalized = note.strip()
    return (
        normalized == note
        and 3 <= len(normalized) <= 160
        and "\n" not in normalized
        and "\r" not in normalized
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


def _recovery_probe(target: str) -> str:
    return f"{target} (stale)"


def _route_completed(events: tuple[EpisodeEvent, ...], case: _ContactsCase) -> bool:
    target_observation_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "observation"
        and event.tool_name == "lookup_contact"
        and event.observation == {"name": case.target, "email": case.expected_email}
    ]
    if not target_observation_indexes:
        return False
    target_index = target_observation_indexes[0]
    if case.route in {"direct", "verify"}:
        return True
    directory_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "observation"
        and event.tool_name == "list_contacts"
        and isinstance(event.observation, dict)
        and case.target in event.observation.get("contacts", [])
    ]
    if case.route == "directory":
        return any(index < target_index for index in directory_indexes)
    if case.route != "recovery":
        return False
    stale_action_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "action"
        and event.tool_name == "lookup_contact"
        and event.arguments == {"name": _recovery_probe(case.target)}
    ]
    stale_failure_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "error"
        and event.tool_name == "lookup_contact"
        and event.error_code == "contact_not_found"
    ]
    return any(
        stale_action < stale_failure < directory < target_index
        for stale_action in stale_action_indexes
        for stale_failure in stale_failure_indexes
        for directory in directory_indexes
    )


def _compilation_rejection(reason_code: str) -> CompilationRejection:
    return CompilationRejection(
        public_task=PublicTask(
            instruction="The Contacts request could not be compiled.",
            tools=_lookup_public_task(
                _ContactsCase(target="a contact", expected_email="")
            ).tools,
        ),
        reason_code=reason_code,
    )


def _parse_contacts_source(contents: bytes) -> _ContactsInitialState:
    payload = _json_object(contents)
    records = payload.get("contacts")
    if not isinstance(records, list) or not records:
        raise ValueError("Contacts source requires non-empty contacts")
    contacts: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Contacts source contact must be an object")
        name = record.get("name")
        email = record.get("email")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(email, str)
            or not email.strip()
        ):
            raise ValueError("Contacts source contact requires name and email")
        normalized_name = name.strip()
        normalized_email = email.strip()
        if len(normalized_name) > 160 or len(normalized_email) > 320:
            raise ValueError("Contacts source contact fields exceed bounded length")
        if normalized_name in contacts:
            raise ValueError("Contacts source contact names must be unique")
        contacts[normalized_name] = normalized_email
    followup_records = payload.get("followups", [])
    if not isinstance(followup_records, list):
        raise ValueError("Contacts source followups must be a list")
    followups: dict[str, str] = {}
    for record in followup_records:
        if not isinstance(record, dict):
            raise ValueError("Contacts source followup must be an object")
        name = record.get("name")
        note = record.get("note")
        normalized_name = name.strip() if isinstance(name, str) else ""
        if (
            not normalized_name
            or normalized_name not in contacts
            or not isinstance(note, str)
            or not _note_is_allowed(note)
        ):
            raise ValueError("Contacts source followup requires a known contact and note")
        if normalized_name in followups:
            raise ValueError("Contacts source followups must be unique by contact")
        followups[normalized_name] = note
    return _ContactsInitialState(contacts=contacts, followups=followups)


def _initial_state_from_frozen_state(state: FrozenInitialState) -> _ContactsInitialState:
    return _parse_contacts_source(state.contents)


def _case_from_task(task: CompiledTask) -> _ContactsCase:
    if not isinstance(task.domain_case, _ContactsCase):
        raise ValueError("invalid Contacts task case")
    return task.domain_case


def _json_object(contents: bytes) -> dict[str, object]:
    try:
        payload = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Contacts source JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Contacts source must be a JSON object")
    return cast(dict[str, object], payload)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _diagnostic_group_id(kind: str, fingerprint: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}:{fingerprint}:{value}".encode("utf-8")).hexdigest()
    return f"{kind}:sha256:{digest}"


def _slot_slug(value: str) -> str:
    return value.casefold().replace(" ", "-")


def _semantic_slug(value: str) -> str:
    return value.casefold().replace(" ", "_")
