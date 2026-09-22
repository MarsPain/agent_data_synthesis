from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from agent_synthesis import (
    AdapterRegistry,
    AssessmentCheck,
    CompilationRejection,
    CompiledTask,
    EpisodeAssessment,
    EpisodeEvent,
    ExecutionTrace,
    FrozenInitialState,
    JsonModelResponse,
    PublicTask,
    RunConfiguration,
    SynthesisEngine,
    TaskProposal,
    TaskSlot,
    ToolDefinition,
    ToolExecutionResult,
)
from agent_synthesis.ledger import PrivateLedger
from agent_synthesis.manifest import RunManifest


@dataclass(frozen=True)
class _NoteCase:
    public_task: PublicTask
    target: str
    note: str
    private_oracle: str
    attempted_target: str | None = None


class _DeterministicProposalModel:
    model_id = "deterministic_note_model"
    model_version = "deterministic_note_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self._episode_starts = 0

    def complete(self, request: object) -> JsonModelResponse:
        role = request.role
        if role == "task_generation":
            slots = request.slots
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": (
                                "require the private exact note for Ada"
                                if slot.slot_id == "hidden-exact-note-001"
                                else "record a friendly note for Ada: Thanks for your help."
                            ),
                        }
                        for slot in slots
                    ]
                }
            )
        history = request.observable_history
        if not history:
            target = "Bea" if self._episode_starts else "Ada"
            self._episode_starts += 1
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "record_note",
                    "arguments": {
                        "target": target,
                        "note": "Thanks for your help.",
                    },
                }
            )
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": "I added a thank-you note for Ada.",
            }
        )


class _NoteDomain:
    domain_id = "note_test_domain"
    domain_version = "note_test_domain_v1"

    def __init__(
        self,
        *,
        include_hidden_exact_slot: bool = False,
        include_unauthorized_mutation_slot: bool = False,
        include_unauthorized_execution_slot: bool = False,
        include_unsafe_public_material: bool = False,
        private_ledger_path: Path | None = None,
    ) -> None:
        self.initial_state = {
            "contacts": {"Ada": {"notes": []}},
            "source_path": "/Users/agent/private-fixture.json",
            "secret": "secret-test-key",
        }
        self.opened_states: list[dict[str, object]] = []
        self.include_hidden_exact_slot = include_hidden_exact_slot
        self.include_unauthorized_mutation_slot = include_unauthorized_mutation_slot
        self.include_unauthorized_execution_slot = include_unauthorized_execution_slot
        self.include_unsafe_public_material = include_unsafe_public_material
        self.private_ledger_path = private_ledger_path
        self.ledger_was_populated_before_open = False

    def open_run(self, configuration: RunConfiguration) -> _NoteDomainRun:
        return _NoteDomainRun(self, configuration)


class _NoteDomainRun:
    def __init__(self, domain: _NoteDomain, configuration: RunConfiguration) -> None:
        self._domain = domain
        self._configuration = configuration

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        slots = (
            TaskSlot(
                slot_id="note-ada-001",
                proposal_prompt="Write a proposal for the public request.",
            ),
        )
        if self._domain.include_hidden_exact_slot:
            slots += (
                TaskSlot(
                    slot_id="hidden-exact-note-001",
                    proposal_prompt="Write a proposal for the public request.",
                ),
            )
        if self._domain.include_unauthorized_mutation_slot:
            slots += (
                TaskSlot(
                    slot_id="unauthorized-mutation-001",
                    proposal_prompt="Write a proposal for the public lookup request.",
                ),
            )
        if self._domain.include_unauthorized_execution_slot:
            slots += (
                TaskSlot(
                    slot_id="unauthorized-execution-001",
                    proposal_prompt="Write a proposal for the public note request.",
                ),
            )
        return slots[:limit]

    def freeze_initial_state(self) -> FrozenInitialState:
        payload = json.dumps(self._domain.initial_state, sort_keys=True).encode("utf-8")
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(payload).hexdigest(),
            contents=payload,
        )

    def compile(self, slot: TaskSlot, proposal: TaskProposal) -> CompiledTask | CompilationRejection:
        self._configuration.model_dump(mode="json")
        output_properties: dict[str, object] = {
            "target": {"type": "string"},
            "note_count": {"type": "integer"},
        }
        if self._domain.include_unsafe_public_material:
            output_properties.update(
                {
                    "ground_truth": {"type": "string"},
                    "auth": {"type": "string"},
                    "http_body": {"type": "string"},
                    "thought": {"type": "string"},
                }
            )
        public_task = PublicTask(
            instruction="Add a brief thank-you note for Ada.",
            tools=(
                ToolDefinition(
                    name="record_note",
                    description="Store a follow-up note for a contact.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["target", "note"],
                    },
                    output_schema={
                        "type": "object",
                        "properties": output_properties,
                    },
                ),
            ),
        )
        if slot.slot_id == "hidden-exact-note-001":
            return CompilationRejection(
                public_task=public_task,
                reason_code="hidden_exact_outcome_not_supported_by_public_task",
            )
        if slot.slot_id == "unauthorized-mutation-001":
            return CompilationRejection(
                public_task=PublicTask(
                    instruction="Look up Ada's existing notes.",
                    tools=public_task.tools,
                ),
                reason_code="mutation_not_authorized_by_public_task",
            )
        if slot.slot_id not in {"note-ada-001", "unauthorized-execution-001"}:
            raise AssertionError("the deterministic proposal must bind the deterministic slot")
        prefix = "record a friendly note for Ada: "
        if not proposal.content.startswith(prefix):
            raise AssertionError("the deterministic proposal must bind the deterministic slot")
        note = proposal.content.removeprefix(prefix)
        allowed_notes = {"Thanks for your help.", "Thank you for your help."}
        if note not in allowed_notes:
            return CompilationRejection(
                public_task=public_task,
                reason_code="open_note_outcome_not_allowed_by_domain",
            )
        case = _NoteCase(
            public_task=public_task,
            target="Ada",
            note=note,
            private_oracle="The stored note must be a permitted thank-you.",
            attempted_target=(
                "Bea" if slot.slot_id == "unauthorized-execution-001" else None
            ),
        )
        return CompiledTask(
            public_task=public_task,
            semantic_key=(
                "record-note:ada:unauthorized-execution"
                if slot.slot_id == "unauthorized-execution-001"
                else "record-note:ada:thank-you"
            ),
            private_case_bytes=json.dumps(
                {
                    "target": case.target,
                    "note": case.note,
                    "private_oracle": case.private_oracle,
                    "attempted_target": case.attempted_target,
                },
                sort_keys=True,
            ).encode("utf-8"),
            domain_case=case,
        )

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> _NoteEpisode:
        case = task.domain_case
        assert isinstance(case, _NoteCase)
        if self._domain.private_ledger_path is not None:
            ledger = PrivateLedger.open(self._domain.private_ledger_path)
            try:
                self._domain.ledger_was_populated_before_open = (
                    ledger.initial_state().contents
                    == json.dumps(self._domain.initial_state, sort_keys=True).encode("utf-8")
                    and len(ledger.task_cases()) == 1
                )
            finally:
                ledger.close()
        isolated_state = json.loads(frozen_initial_state.contents)
        self._domain.opened_states.append(isolated_state)
        return _NoteEpisode(
            case,
            isolated_state,
            unsafe_public_material=self._domain.include_unsafe_public_material,
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        private_case = json.loads(private_case_bytes)
        case = _NoteCase(
            public_task=public_task,
            target=private_case["target"],
            note=private_case["note"],
            private_oracle=private_case["private_oracle"],
            attempted_target=private_case["attempted_target"],
        )
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
    ) -> _NoteEpisode:
        case = task.domain_case
        assert isinstance(case, _NoteCase)
        state = json.loads(frozen_initial_state.contents)
        return _NoteEpisode(
            case,
            state,
            unsafe_public_material=self._domain.include_unsafe_public_material,
        )


class _NoteEpisode:
    def __init__(
        self,
        case: _NoteCase,
        state: dict[str, object],
        *,
        unsafe_public_material: bool,
    ) -> None:
        self._case = case
        self._state = state
        self._unsafe_public_material = unsafe_public_material

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        if (
            tool_name != "record_note"
            or arguments.get("target") != self._case.target
            or arguments.get("note") != self._case.note
        ):
            return ToolExecutionResult(
                result_type="unauthorized_mutation",
                error_code="mutation_not_authorized",
            )
        contacts = self._state["contacts"]
        assert isinstance(contacts, dict)
        ada = contacts[self._case.target]
        assert isinstance(ada, dict)
        notes = ada["notes"]
        assert isinstance(notes, list)
        notes.append(self._case.note)
        change: dict[str, object] = {
            "target": self._case.target,
            "note_count": len(notes),
        }
        if self._unsafe_public_material:
            change.update(
                {
                    "private_oracle": self._case.private_oracle,
                    "provider_payload": {"secret": "secret-test-key"},
                    "reasoning": "private chain-of-thought material",
                    "source_path": "/Users/agent/private-fixture.json",
                    "access_token": "access-token-value",
                    "password": "password-value",
                    "response": {"raw": "unrestricted-provider-response"},
                    "source_hint": "source at /opt/private-source.json",
                    "expected_value": "private expected result",
                    "passwd": "passwd-value",
                    "completion": "raw provider completion",
                    "analysis": "hidden model analysis",
                    "ground_truth": "hidden exact answer",
                    "auth": "ghp_private_auth_value",
                    "http_body": "unrestricted HTTP provider material",
                    "thought": "hidden internal rationale",
                }
            )
        return ToolExecutionResult(result_type="state_change", change=change)

    def assess(self, trace: ExecutionTrace) -> EpisodeAssessment:
        authorized = trace.mutation_authorization == "authorized"
        return EpisodeAssessment(
            passed=authorized,
            checks=(
                AssessmentCheck(name="authorized_mutation", passed=authorized),
                AssessmentCheck(name="requested_note_recorded", passed=authorized),
                AssessmentCheck(name="final_response_grounded", passed=authorized),
            ),
            reason_codes=() if authorized else ("unauthorized_tool_arguments",),
            coverage_tags=("mutation", "open_note"),
            structural_key="record_note",
            state_change_evidence="record_note:ada",
        )


class AgentFirstCoreTracerTest(unittest.TestCase):
    def test_non_final_events_cannot_carry_unbounded_content(self) -> None:
        with self.assertRaises(ValidationError):
            EpisodeEvent(
                event_type="error",
                tool_name="record_note",
                error_code="tool_failure",
                content="opaque upstream body: 7f3a9c",
            )

    def test_engine_exports_a_deterministically_admitted_episode(self) -> None:
        domain = _NoteDomain()
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_DeterministicProposalModel(),),
            )
        )
        configuration = RunConfiguration(
            run_id="note-tracer",
            domain_id=domain.domain_id,
            model_id="deterministic_note_model",
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(
                Path(temporary_directory) / "demonstrations.jsonl"
            )
            negatives = _read_json_lines(Path(temporary_directory) / "negatives.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(len(demonstrations), 1)
        self.assertEqual(negatives, [])
        self.assertEqual(demonstrations[0]["task"]["instruction"], "Add a brief thank-you note for Ada.")
        self.assertEqual(demonstrations[0]["admission"], {
            "gates": {
                "assessment": True,
                "execution": True,
                "final_grounding": True,
                "mutation_authorization": True,
                "semantic_key": True,
                "unsafe_material": True,
            },
            "human_review_status": "unreviewed",
            "mode": "deterministic",
            "status": "admitted",
        })
        self.assertEqual(demonstrations[0]["verification"]["structural_key"], "record_note")
        self.assertEqual(domain.initial_state["contacts"]["Ada"]["notes"], [])
        self.assertEqual(domain.opened_states[0]["contacts"]["Ada"]["notes"], ["Thanks for your help."])

    def test_domain_accepts_open_outcomes_but_rejects_a_hidden_exact_requirement(self) -> None:
        domain = _NoteDomain(include_hidden_exact_slot=True)
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_DeterministicProposalModel(),),
            )
        )
        configuration = RunConfiguration(
            run_id="note-open-outcome",
            domain_id=domain.domain_id,
            model_id="deterministic_note_model",
            slot_limit=2,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(
                Path(temporary_directory) / "demonstrations.jsonl"
            )
            negatives = _read_json_lines(Path(temporary_directory) / "negatives.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(
            demonstrations[0]["events"][0]["arguments"]["note"],
            "Thanks for your help.",
        )
        self.assertEqual(
            negatives[0]["outcome"]["reason_code"],
            "hidden_exact_outcome_not_supported_by_public_task",
        )
        self.assertEqual(negatives[0]["outcome"]["status"], "rejected_before_execution")
        self.assertEqual(negatives[0]["admission"]["human_review_status"], "unreviewed")

    def test_unsafe_public_material_is_rejected_while_public_artifacts_stay_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            private_ledger_path = output_directory / ".private" / "ledger.sqlite3"
            domain = _NoteDomain(
                private_ledger_path=private_ledger_path,
                include_unsafe_public_material=True,
            )
            engine = SynthesisEngine(
                AdapterRegistry(
                    domains=(domain,),
                    models=(_DeterministicProposalModel(),),
                )
            )
            configuration = RunConfiguration(
                run_id="note-sanitized",
                domain_id=domain.domain_id,
                model_id="deterministic_note_model",
                slot_limit=1,
            )

            result = engine.run(configuration, output_directory)
            public_text = (output_directory / "negatives.jsonl").read_text(
                encoding="utf-8"
            )
            manifest_record = json.loads(
                (output_directory / "manifest.json").read_text(encoding="utf-8")
            )
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                frozen_state = ledger.initial_state()
                task_cases = ledger.task_cases()
            finally:
                ledger.close()

            self.assertTrue(domain.ledger_was_populated_before_open)
            self.assertEqual(
                frozen_state.contents,
                json.dumps(domain.initial_state, sort_keys=True).encode("utf-8"),
            )
            self.assertEqual(len(task_cases), 1)
            self.assertIn(b"private_oracle", task_cases[0].private_case_bytes())
            for forbidden in (
                "private_oracle",
                "secret-test-key",
                "/Users/agent/private-fixture.json",
                "provider_payload",
                "reasoning",
                "access-token-value",
                "password-value",
                "unrestricted-provider-response",
                "/opt/private-source.json",
                "private expected result",
                "passwd-value",
                "raw provider completion",
                "hidden model analysis",
                "hidden exact answer",
                "ghp_private_auth_value",
                "unrestricted HTTP provider material",
                "hidden internal rationale",
                '"ground_truth"',
                '"auth"',
                '"http_body"',
                '"thought"',
            ):
                self.assertNotIn(forbidden, public_text)
            public_episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            self.assertEqual(public_episode["outcome"]["reason_code"], "unsafe_public_material")
            self.assertEqual(
                public_episode["events"][1]["change"],
                {"target": "Ada", "note_count": 1},
            )

            manifest = RunManifest.model_validate(manifest_record)
            self.assertEqual(manifest.configuration, configuration.model_dump(mode="json"))
            self.assertEqual(
                {item.path for item in manifest.files},
                {
                    "demonstrations.jsonl",
                    "negatives.jsonl",
                    "provider_usage.json",
                    "quality_report.json",
                    "run_report.json",
                    "shadow_quality_judgments.jsonl",
                },
            )
            self.assertNotIn("evidence_graph", manifest_record)
            self.assertNotIn("object_hash", manifest_record)
            for item in manifest.files:
                contents = (output_directory / item.path).read_bytes()
                self.assertEqual(
                    item.sha256,
                    "sha256:" + hashlib.sha256(contents).hexdigest(),
                )

    def test_domain_rejects_an_unauthorized_mutation_before_opening_an_episode(self) -> None:
        domain = _NoteDomain(include_unauthorized_mutation_slot=True)
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_DeterministicProposalModel(),),
            )
        )
        configuration = RunConfiguration(
            run_id="note-authorization",
            domain_id=domain.domain_id,
            model_id="deterministic_note_model",
            slot_limit=2,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negatives = _read_json_lines(Path(temporary_directory) / "negatives.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(len(domain.opened_states), 1)
        self.assertEqual(domain.initial_state["contacts"]["Ada"]["notes"], [])
        self.assertEqual(
            negatives[0]["outcome"]["reason_code"],
            "mutation_not_authorized_by_public_task",
        )

    def test_domain_rejects_unauthorized_actual_tool_arguments_before_state_changes(self) -> None:
        domain = _NoteDomain(include_unauthorized_execution_slot=True)
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_DeterministicProposalModel(),),
            )
        )
        configuration = RunConfiguration(
            run_id="note-execution-authorization",
            domain_id=domain.domain_id,
            model_id="deterministic_note_model",
            slot_limit=2,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negatives = _read_json_lines(Path(temporary_directory) / "negatives.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(len(domain.opened_states), 2)
        self.assertEqual(domain.opened_states[1]["contacts"]["Ada"]["notes"], [])
        self.assertEqual(domain.initial_state["contacts"]["Ada"]["notes"], [])
        self.assertEqual(
            negatives[0]["events"][0]["arguments"]["target"],
            "Bea",
        )
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "unauthorized_mutation")


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
