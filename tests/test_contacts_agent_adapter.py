from __future__ import annotations

import json
import tempfile
import unittest
import hashlib
from pathlib import Path

from pydantic import ValidationError

from agent_synthesis import (
    AdapterRegistry,
    CompilationRejection,
    EpisodeEvent,
    ExecutionTrace,
    JsonModelResponse,
    RunConfiguration,
    SynthesisEngine,
    TaskProposal,
)
from agent_synthesis.contacts import (
    ContactsDomainAdapter,
    ContactsPilotConfiguration,
    rehearse_contacts_pilot,
    write_contacts_pilot_rehearsal,
)
from agent_synthesis.ledger import PrivateLedger
from tests.agent_first_compliance import assert_agent_episode_compliance


class _DirectLookupModel:
    """One deterministic provider mock at the public model seam."""

    model_id = "contacts_direct_lookup_model"
    model_version = "contacts_direct_lookup_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        if request.role == "task_generation":
            slot = request.slots[0]
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": json.dumps(
                                {
                                    "action": "lookup_email",
                                    "contact": "Alice Zhang",
                                    "route": "direct",
                                },
                                sort_keys=True,
                            ),
                        }
                    ]
                }
            )
        if not request.observable_history:
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "lookup_contact",
                    "arguments": {"name": "Alice Zhang"},
                }
            )
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": "Alice Zhang's email is alice.zhang@example.test.",
            }
        )


class _LookupRouteModel:
    """Provider mock that chooses only from the public task and event history."""

    model_id = "contacts_lookup_route_model"
    model_version = "contacts_lookup_route_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": slot.proposal_prompt.removeprefix(
                                "Return exactly this JSON proposal: "
                            ),
                        }
                        for slot in request.slots
                    ]
                }
            )
        instruction = request.task.instruction
        history = request.observable_history
        if "stale contact label" in instruction:
            return _recovery_lookup_decision(history)
        if "contact directory" in instruction:
            return _directory_lookup_decision(history)
        return _direct_lookup_decision(history)


class _ContactsOfflinePolicyModel:
    """A deterministic offline Agent policy consuming only public contexts."""

    model_id = "contacts_offline_policy_model"
    model_version = "contacts_offline_policy_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": slot.proposal_prompt.removeprefix(
                                "Return exactly this JSON proposal: "
                            ),
                        }
                        for slot in request.slots
                    ]
                }
            )
        return _contacts_policy_decision(request.task, request.observable_history)


class _WrongContactFollowupModel(_ContactsOfflinePolicyModel):
    model_id = "contacts_wrong_contact_model"
    model_version = "contacts_wrong_contact_model_v1"

    def complete(self, request: object) -> JsonModelResponse:
        response = super().complete(request)
        if (
            request.role == "agent"
            and response.content.get("type") == "tool_call"
            and response.content.get("tool_name") == "record_followup"
        ):
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "record_followup",
                    "arguments": {
                        "name": "Ben Carter",
                        "note": "Please send the proposal.",
                    },
                }
            )
        return response


class ContactsAgentAdapterTest(unittest.TestCase):
    def test_fixture_direct_lookup_runs_through_the_engine_with_private_source_state(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(adapter,), models=(_DirectLookupModel(),))
        )
        configuration = RunConfiguration(
            run_id="contacts-direct-lookup",
            domain_id=adapter.domain_id,
            model_id="contacts_direct_lookup_model",
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            result = engine.run(configuration, output_directory)
            demonstrations = _read_json_lines(output_directory / "demonstrations.jsonl")
            public_artifacts = "".join(
                path.read_text(encoding="utf-8")
                for path in (
                    output_directory / "demonstrations.jsonl",
                    output_directory / "negatives.jsonl",
                    output_directory / "provider_usage.json",
                    output_directory / "manifest.json",
                )
            )

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(demonstrations[0]["task"]["instruction"], "Find the email address for Alice Zhang.")
        self.assertEqual(
            demonstrations[0]["events"][1]["observation"],
            {"email": "alice.zhang@example.test", "name": "Alice Zhang"},
        )
        self.assertEqual(demonstrations[0]["verification"]["structural_key"], "contacts.lookup.direct")
        self.assertNotIn("source_schema_version", public_artifacts)
        self.assertNotIn('"contacts":[', public_artifacts)

    def test_local_source_is_frozen_before_model_work_and_replay_ignores_later_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "contacts.json"
            source_path.write_text(
                json.dumps(
                    {
                        "contacts": [
                            {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
                            {"name": "Ben Carter", "email": "ben.carter@example.test"},
                        ],
                        "followups": [],
                    }
                ),
                encoding="utf-8",
            )
            adapter = ContactsDomainAdapter.from_local_file(source_path)
            model = _DirectLookupModel()
            engine = SynthesisEngine(
                AdapterRegistry(domains=(adapter,), models=(model,))
            )
            configuration = RunConfiguration(
                run_id="contacts-local-replay",
                domain_id=adapter.domain_id,
                model_id=model.model_id,
                slot_limit=1,
            )
            result = engine.run(configuration, root / "run")
            calls_before_replay = len(model.requests)
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                frozen = ledger.initial_state()
            finally:
                ledger.close()

            source_path.write_text(
                json.dumps(
                    {
                        "contacts": [
                            {"name": "Alice Zhang", "email": "changed@example.test"},
                        ],
                        "followups": [],
                    }
                ),
                encoding="utf-8",
            )
            replay = engine.replay(result.run_directory)

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(
            frozen.fingerprint,
            "sha256:" + hashlib.sha256(frozen.contents).hexdigest(),
        )
        self.assertIn(b"alice.zhang@example.test", frozen.contents)
        self.assertTrue(replay.aligned)
        self.assertEqual(len(model.requests), calls_before_replay)

    def test_slots_disclose_known_capacity_and_compile_a_bound_open_followup(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        run = adapter.open_run(_contacts_configuration(adapter))
        slots = run.slots(100)
        followup_slot = next(
            slot for slot in slots if slot.slot_id == "contacts-followup-open-alice-zhang"
        )

        compilation = run.compile(
            followup_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "record_followup",
                        "condition": "after_lookup_match",
                        "contact": "Alice Zhang",
                        "note_constraint": "open",
                        "route": "direct",
                    },
                    sort_keys=True,
                )
            ),
        )
        wrong_contact = run.compile(
            followup_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "record_followup",
                        "condition": "after_lookup_match",
                        "contact": "Ben Carter",
                        "note_constraint": "open",
                        "route": "direct",
                    },
                    sort_keys=True,
                )
            ),
        )

        self.assertEqual(run.known_task_capacity, 16)
        self.assertEqual(len(slots), 16)
        self.assertEqual(run.slot_capacity(100).known_task_capacity, 16)
        self.assertTrue(run.slot_capacity(100).exhausted)
        self.assertFalse(run.slot_capacity(3).exhausted)
        self.assertIn("contacts-lookup-recovery-alice-zhang", {slot.slot_id for slot in slots})
        self.assertNotIsInstance(compilation, CompilationRejection)
        assert not isinstance(compilation, CompilationRejection)
        self.assertIn("brief follow-up note", compilation.public_task.instruction)
        self.assertNotIn("exactly", compilation.public_task.instruction)
        self.assertRegex(compilation.semantic_key, r"^contacts:semantic:sha256:[0-9a-f]{64}$")
        self.assertIsInstance(wrong_contact, CompilationRejection)
        assert isinstance(wrong_contact, CompilationRejection)
        self.assertEqual(wrong_contact.reason_code, "wrong_contact_binding")

        with self.assertRaisesRegex(ValueError, "invalid private Contacts task case"):
            run.restore_task_case(
                public_task=compilation.public_task,
                semantic_key=compilation.semantic_key,
                private_case_bytes=json.dumps(
                    {
                        "action": "invent_followup",
                        "expected_email": "alice.zhang@example.test",
                        "exact_note": None,
                        "note_constraint": "open",
                        "route": "direct",
                        "target": "Alice Zhang",
                    }
                ).encode("utf-8"),
            )

    def test_followup_requires_observed_authorization_and_distinguishes_open_from_exact_notes(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        run = adapter.open_run(_contacts_configuration(adapter))
        frozen = run.freeze_initial_state()
        slots = {slot.slot_id: slot for slot in run.slots(100)}
        open_task = _compiled_task(
            run,
            slots["contacts-followup-open-alice-zhang"],
            {
                "action": "record_followup",
                "condition": "after_lookup_match",
                "contact": "Alice Zhang",
                "note_constraint": "open",
                "route": "direct",
            },
        )
        exact_task = _compiled_task(
            run,
            slots["contacts-followup-exact-alice-zhang"],
            {
                "action": "record_followup",
                "condition": "after_lookup_match",
                "contact": "Alice Zhang",
                "note": "Please follow up by email.",
                "note_constraint": "exact",
                "route": "direct",
            },
        )

        ungrounded_episode = run.open_episode(open_task, frozen)
        ungrounded_mutation = ungrounded_episode.execute_tool_call(
            "record_followup",
            {"name": "Alice Zhang", "note": "Please send the proposal."},
        )
        open_episode = run.open_episode(open_task, frozen)
        lookup = open_episode.execute_tool_call(
            "lookup_contact", {"name": "Alice Zhang"}
        )
        open_mutation = open_episode.execute_tool_call(
            "record_followup",
            {"name": "Alice Zhang", "note": "Please send the proposal."},
        )
        exact_episode = run.open_episode(exact_task, frozen)
        exact_episode.execute_tool_call("lookup_contact", {"name": "Alice Zhang"})
        wrong_exact_note = exact_episode.execute_tool_call(
            "record_followup",
            {"name": "Alice Zhang", "note": "Please send the proposal."},
        )

        self.assertEqual(ungrounded_mutation.result_type, "unauthorized_mutation")
        self.assertEqual(ungrounded_mutation.error_code, "mutation_condition_not_observed")
        self.assertEqual(open_mutation.result_type, "state_change")
        self.assertEqual(open_mutation.change, {
            "name": "Alice Zhang",
            "note": "Please send the proposal.",
        })
        self.assertEqual(wrong_exact_note.result_type, "unauthorized_mutation")
        self.assertEqual(wrong_exact_note.error_code, "note_not_authorized")

        assessment = open_episode.assess(
            ExecutionTrace(
                mutation_authorization="authorized",
                events=(
                    EpisodeEvent(
                        event_type="action",
                        tool_name="lookup_contact",
                        arguments={"name": "Alice Zhang"},
                    ),
                    EpisodeEvent(
                        event_type="observation",
                        tool_name="lookup_contact",
                        observation={
                            "name": "Alice Zhang",
                            "email": "alice.zhang@example.test",
                        },
                    ),
                    EpisodeEvent(
                        event_type="action",
                        tool_name="record_followup",
                        arguments={
                            "name": "Alice Zhang",
                            "note": "Please send the proposal.",
                        },
                    ),
                    EpisodeEvent(
                        event_type="state_change",
                        tool_name="record_followup",
                        change={
                            "name": "Alice Zhang",
                            "note": "Please send the proposal.",
                        },
                    ),
                    EpisodeEvent(
                        event_type="final_response",
                        content="Recorded 'Please send the proposal.' for Alice Zhang.",
                    ),
                ),
            )
        )
        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.structural_key, "contacts.followup.direct")

    def test_provider_mock_produces_a_successful_lookup_recovery_and_replay(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        model = _LookupRouteModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="contacts-lookup-routes",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=3,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(result.demonstrations_path)
            replay = engine.replay(result.run_directory)

        self.assertEqual(result.demonstration_count, 3)
        self.assertEqual(result.negative_count, 0)
        recovery = demonstrations[2]
        self.assertEqual(recovery["verification"]["structural_key"], "contacts.lookup.recovery")
        self.assertEqual(recovery["events"][1]["error_code"], "contact_not_found")
        self.assertEqual(recovery["events"][3]["tool_name"], "list_contacts")
        self.assertTrue(replay.aligned)

    def test_compilation_rejects_negation_uncheckable_conditions_and_unsupported_notes(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        run = adapter.open_run(_contacts_configuration(adapter))
        slots = {slot.slot_id: slot for slot in run.slots(100)}
        open_slot = slots["contacts-followup-open-alice-zhang"]
        exact_slot = slots["contacts-followup-exact-alice-zhang"]

        negated = run.compile(
            open_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "do_not_record_followup",
                        "condition": "after_lookup_match",
                        "contact": "Alice Zhang",
                        "note_constraint": "open",
                        "route": "direct",
                    }
                )
            ),
        )
        uncheckable = run.compile(
            open_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "record_followup",
                        "condition": "after_a_positive_vibe",
                        "contact": "Alice Zhang",
                        "note_constraint": "open",
                        "route": "direct",
                    }
                )
            ),
        )
        unsupported_note = run.compile(
            exact_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "record_followup",
                        "condition": "after_lookup_match",
                        "contact": "Alice Zhang",
                        "note": "two\nlines",
                        "note_constraint": "exact",
                        "route": "direct",
                    }
                )
            ),
        )
        free_form_negation = run.compile(
            open_slot,
            TaskProposal(content="Do not record a follow-up for Alice Zhang."),
        )

        self.assertIsInstance(negated, CompilationRejection)
        self.assertIsInstance(uncheckable, CompilationRejection)
        self.assertIsInstance(unsupported_note, CompilationRejection)
        self.assertIsInstance(free_form_negation, CompilationRejection)
        assert isinstance(negated, CompilationRejection)
        assert isinstance(uncheckable, CompilationRejection)
        assert isinstance(unsupported_note, CompilationRejection)
        assert isinstance(free_form_negation, CompilationRejection)
        self.assertEqual(negated.reason_code, "negated_action")
        self.assertEqual(uncheckable.reason_code, "uncheckable_condition")
        self.assertEqual(unsupported_note.reason_code, "unsupported_note")
        self.assertEqual(free_form_negation.reason_code, "negated_action")

    def test_offline_agent_policy_produces_all_contacts_behaviors_in_seven_structural_families(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        model = _ContactsOfflinePolicyModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        pilot = ContactsPilotConfiguration(
            pilot_id="contacts-offline-behaviors",
            model_id=model.model_id,
            model_version=model.model_version,
            total_physical_request_limit=64,
            generation_request_limit=8,
            agent_request_limit=56,
            max_output_tokens=128,
        )
        configuration = pilot.rehearsal_run_configuration()

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(result.demonstrations_path)
            negatives = _read_json_lines(result.negatives_path)
            replay = engine.replay(result.run_directory)

        self.assertEqual(result.demonstration_count, 8)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(negatives, [])
        self.assertEqual(
            {item["verification"]["structural_key"] for item in demonstrations},
            {
                "contacts.lookup.direct",
                "contacts.lookup.directory",
                "contacts.lookup.recovery",
                "contacts.followup.direct",
                "contacts.followup.directory",
                "contacts.followup.recovery",
                "contacts.followup.verified",
            },
        )
        self.assertTrue(replay.aligned)
        public_episode_text = json.dumps([*demonstrations, *negatives])
        for private_field in ("expected_email", "exact_note", "private_case_bytes"):
            self.assertNotIn(private_field, public_episode_text)
        assert_agent_episode_compliance(
            self,
            demonstrations=demonstrations,
            negatives=negatives,
            replay_aligned=replay.aligned,
        )

    def test_unauthorized_followup_is_a_negative_without_a_state_change(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        model = _WrongContactFollowupModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="contacts-unauthorized-followup",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=4,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(result.demonstrations_path)
            negatives = _read_json_lines(result.negatives_path)

        self.assertEqual(result.demonstration_count, 3)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(len(demonstrations), 3)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "unauthorized_mutation")
        self.assertEqual(negatives[0]["mutation_authorization"], "rejected")
        self.assertFalse(
            any(event["event_type"] == "state_change" for event in negatives[0]["events"])
        )

    def test_semantic_keys_and_reviewed_structural_examples_preserve_real_differences_only(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        run = adapter.open_run(_contacts_configuration(adapter))
        slots = {slot.slot_id: slot for slot in run.slots(100)}
        direct_alice = _compiled_task(
            run,
            slots["contacts-lookup-direct-alice-zhang"],
            {"action": "lookup_email", "contact": "Alice Zhang", "route": "direct"},
        )
        direct_ben = _compiled_task(
            run,
            slots["contacts-lookup-direct-ben-carter"],
            {"action": "lookup_email", "contact": "Ben Carter", "route": "direct"},
        )
        directory_alice = _compiled_task(
            run,
            slots["contacts-lookup-directory-alice-zhang"],
            {"action": "lookup_email", "contact": "Alice Zhang", "route": "directory"},
        )
        exact_one = _compiled_task(
            run,
            slots["contacts-followup-exact-alice-zhang"],
            {
                "action": "record_followup",
                "condition": "after_lookup_match",
                "contact": "Alice Zhang",
                "note": "Please follow up by email.",
                "note_constraint": "exact",
                "route": "direct",
            },
        )
        exact_two = _compiled_task(
            run,
            slots["contacts-followup-exact-alice-zhang"],
            {
                "action": "record_followup",
                "condition": "after_lookup_match",
                "contact": "Alice Zhang",
                "note": "Please follow up tomorrow.",
                "note_constraint": "exact",
                "route": "direct",
            },
        )
        paraphrased = run.restore_task_case(
            public_task=direct_alice.public_task.model_copy(
                update={"instruction": "Could you locate Alice Zhang's email address?"}
            ),
            semantic_key=direct_alice.semantic_key,
            private_case_bytes=direct_alice.private_case_bytes,
        )
        direct_episode = run.open_episode(direct_alice, run.freeze_initial_state())
        redundant_assessment = direct_episode.assess(_direct_lookup_trace(redundant=True))
        ben_assessment = run.open_episode(direct_ben, run.freeze_initial_state()).assess(
            _direct_lookup_trace(
                redundant=False,
                target="Ben Carter",
                email="ben.carter@example.test",
            )
        )
        unexpected_mutation_trace = _direct_lookup_trace(redundant=False).model_copy(
            update={
                "events": (
                    *_direct_lookup_trace(redundant=False).events[:-1],
                    EpisodeEvent(
                        event_type="state_change",
                        tool_name="record_followup",
                        change={"name": "Alice Zhang", "note": "Unexpected."},
                    ),
                    _direct_lookup_trace(redundant=False).events[-1],
                )
            }
        )
        unintended_assessment = direct_episode.assess(unexpected_mutation_trace)

        self.assertEqual(paraphrased.semantic_key, direct_alice.semantic_key)
        self.assertNotEqual(direct_alice.semantic_key, direct_ben.semantic_key)
        self.assertNotEqual(direct_alice.semantic_key, directory_alice.semantic_key)
        self.assertNotEqual(exact_one.semantic_key, exact_two.semantic_key)
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "semantic-key-collision.json"
            source_path.write_text(
                json.dumps(
                    {
                        "contacts": [
                            {"name": "Ada Bee", "email": "ada.bee@example.test"},
                            {"name": "Ada_Bee", "email": "ada_bee@example.test"},
                            {"name": "Ada-Bee", "email": "ada-hyphen@example.test"},
                        ],
                        "followups": [],
                    }
                ),
                encoding="utf-8",
            )
            collision_adapter = ContactsDomainAdapter.from_local_file(source_path)
            collision_run = collision_adapter.open_run(
                _contacts_configuration(collision_adapter)
            )
            collision_slots = {slot.slot_id: slot for slot in collision_run.slots(100)}
            spaced_name = _compiled_task(
                collision_run,
                _slot_for_contact(collision_slots.values(), "Ada Bee"),
                {"action": "lookup_email", "contact": "Ada Bee", "route": "direct"},
            )
            underscored_name = _compiled_task(
                collision_run,
                _slot_for_contact(collision_slots.values(), "Ada_Bee"),
                {"action": "lookup_email", "contact": "Ada_Bee", "route": "direct"},
            )
        self.assertEqual(
            len(
                {
                    slot.slot_id
                    for slot in collision_slots.values()
                    if slot.slot_id.startswith("contacts-lookup-direct-")
                }
            ),
            3,
        )
        self.assertNotEqual(spaced_name.semantic_key, underscored_name.semantic_key)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_source = root / "first-grounding.json"
            second_source = root / "second-grounding.json"
            for path, email in (
                (first_source, "alice.one@example.test"),
                (second_source, "alice.two@example.test"),
            ):
                path.write_text(
                    json.dumps(
                        {
                            "contacts": [{"name": "Alice Zhang", "email": email}],
                            "followups": [],
                        }
                    ),
                    encoding="utf-8",
                )
            first_adapter = ContactsDomainAdapter.from_local_file(first_source)
            second_adapter = ContactsDomainAdapter.from_local_file(second_source)
            first_run = first_adapter.open_run(_contacts_configuration(first_adapter))
            second_run = second_adapter.open_run(_contacts_configuration(second_adapter))
            first_task = _compiled_task(
                first_run,
                _slot_for_contact(first_run.slots(100), "Alice Zhang"),
                {"action": "lookup_email", "contact": "Alice Zhang", "route": "direct"},
            )
            second_task = _compiled_task(
                second_run,
                _slot_for_contact(second_run.slots(100), "Alice Zhang"),
                {"action": "lookup_email", "contact": "Alice Zhang", "route": "direct"},
            )
        self.assertNotEqual(first_task.semantic_key, second_task.semantic_key)
        self.assertTrue(redundant_assessment.passed)
        self.assertEqual(redundant_assessment.structural_key, "contacts.lookup.direct")
        self.assertTrue(ben_assessment.passed)
        self.assertEqual(ben_assessment.structural_key, "contacts.lookup.direct")
        self.assertFalse(unintended_assessment.passed)
        self.assertIn("unintended_state_change", unintended_assessment.reason_codes)
        self.assertEqual(
            {example.expected_structural_key for example in run.reviewed_structural_examples},
            {
                "contacts.lookup.direct",
                "contacts.lookup.directory",
                "contacts.lookup.recovery",
                "contacts.followup.direct",
                "contacts.followup.directory",
                "contacts.followup.recovery",
                "contacts.followup.verified",
            },
        )
        self.assertTrue(
            {
                "paraphrase",
                "entity_substitution",
                "redundant_read_only_call",
            }.issubset({example.variation for example in run.reviewed_structural_examples})
        )

    def test_offline_pilot_rehearsal_is_reviewable_and_requires_separate_authorization(self) -> None:
        adapter = ContactsDomainAdapter.fixture()
        pilot = ContactsPilotConfiguration(
            pilot_id="contacts-early-feasibility",
            model_id="reviewed-pilot-model",
            model_version="reviewed-pilot-model-v1",
            total_physical_request_limit=48,
            generation_request_limit=8,
            agent_request_limit=40,
            transport_retry_limit=1,
            max_output_tokens=128,
        )
        rehearsal = rehearse_contacts_pilot(adapter, pilot)

        with tempfile.TemporaryDirectory() as temporary_directory:
            review_path = write_contacts_pilot_rehearsal(
                rehearsal,
                Path(temporary_directory) / "contacts-pilot-rehearsal.json",
            )
            review_record = json.loads(review_path.read_text(encoding="utf-8"))

        self.assertEqual(rehearsal.target_demonstrations, 8)
        self.assertEqual(rehearsal.task_attempt_limit, 16)
        self.assertEqual(rehearsal.known_task_capacity, 16)
        self.assertEqual(rehearsal.authorization_status, "authorization_required")
        self.assertEqual(rehearsal.configuration["model_id"], "reviewed-pilot-model")
        self.assertEqual(rehearsal.configuration["transport_retry_limit"], 1)
        self.assertEqual(rehearsal.configuration["max_output_tokens"], 128)
        self.assertEqual(
            rehearsal.attempt_ceiling_configuration["slot_limit"],
            rehearsal.task_attempt_limit,
        )
        self.assertEqual(pilot.attempt_ceiling_run_configuration().slot_limit, 16)
        self.assertEqual(len(rehearsal.diagnostic_semantic_groups), 16)
        self.assertEqual(len(rehearsal.diagnostic_grounding_groups), 2)
        self.assertEqual(review_record["authorization_status"], "authorization_required")
        self.assertEqual(review_record["attempt_ceiling_configuration"]["slot_limit"], 16)
        self.assertNotIn("alice.zhang@example.test", json.dumps(review_record))

        with self.assertRaises(ValidationError):
            ContactsPilotConfiguration(
                pilot_id="contacts-early-feasibility",
                model_id="sk-live-credential",
                model_version="reviewed-pilot-model-v1",
                total_physical_request_limit=48,
                generation_request_limit=8,
                agent_request_limit=40,
            )

    def test_normalized_local_state_preserves_existing_followups_and_exhausts_unsafe_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "contacts-with-followup.json"
            source_path.write_text(
                json.dumps(
                    {
                        "contacts": [
                            {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
                            {"name": "Ben Carter", "email": "ben.carter@example.test"},
                        ],
                        "followups": [
                            {"name": "Ben Carter", "note": "Already contacted."}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            adapter = ContactsDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_contacts_configuration(adapter))
            frozen_payload = json.loads(run.freeze_initial_state().contents)
            slot_ids = {slot.slot_id for slot in run.slots(100)}

        self.assertEqual(frozen_payload["followups"], [{"name": "Ben Carter", "note": "Already contacted."}])
        self.assertEqual(run.known_task_capacity, 11)
        self.assertNotIn("contacts-followup-open-ben-carter", slot_ids)
        self.assertIn("contacts-lookup-direct-ben-carter", slot_ids)

    def test_invalid_local_source_stops_before_any_model_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "invalid-contacts.json"
            source_path.write_text('{"contacts": [], "followups": []}', encoding="utf-8")
            adapter = ContactsDomainAdapter.from_local_file(source_path)
            model = _DirectLookupModel()
            engine = SynthesisEngine(
                AdapterRegistry(domains=(adapter,), models=(model,))
            )
            configuration = RunConfiguration(
                run_id="contacts-invalid-source",
                domain_id=adapter.domain_id,
                model_id=model.model_id,
                slot_limit=1,
            )

            with self.assertRaisesRegex(ValueError, "non-empty contacts"):
                engine.run(configuration, root / "run")

        self.assertEqual(model.requests, [])


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _contacts_configuration(adapter: ContactsDomainAdapter) -> RunConfiguration:
    return RunConfiguration(
        run_id="contacts-domain-seam",
        domain_id=adapter.domain_id,
        model_id="contacts_direct_lookup_model",
        slot_limit=16,
    )


def _compiled_task(run: object, slot: object, payload: dict[str, str]) -> object:
    compilation = run.compile(
        slot,
        TaskProposal(content=json.dumps(payload, sort_keys=True)),
    )
    assert not isinstance(compilation, CompilationRejection)
    return compilation


def _slot_for_contact(slots: object, contact: str) -> object:
    return next(
        slot
        for slot in slots
        if slot.slot_id.startswith("contacts-lookup-direct-")
        and f'"contact": "{contact}"' in slot.proposal_prompt
    )


def _direct_lookup_decision(history: tuple[EpisodeEvent, ...]) -> JsonModelResponse:
    if not history:
        return _tool_decision("lookup_contact", {"name": "Alice Zhang"})
    return _final_lookup_response()


def _directory_lookup_decision(history: tuple[EpisodeEvent, ...]) -> JsonModelResponse:
    if not history:
        return _tool_decision("list_contacts", {})
    if not any(
        event.event_type == "action"
        and event.tool_name == "lookup_contact"
        and event.arguments == {"name": "Alice Zhang"}
        for event in history
    ):
        return _tool_decision("lookup_contact", {"name": "Alice Zhang"})
    return _final_lookup_response()


def _recovery_lookup_decision(history: tuple[EpisodeEvent, ...]) -> JsonModelResponse:
    if not history:
        return _tool_decision("lookup_contact", {"name": "Alice Zhang (stale)"})
    if not any(event.tool_name == "list_contacts" for event in history):
        return _tool_decision("list_contacts", {})
    if not any(
        event.event_type == "action"
        and event.tool_name == "lookup_contact"
        and event.arguments == {"name": "Alice Zhang"}
        for event in history
    ):
        return _tool_decision("lookup_contact", {"name": "Alice Zhang"})
    return _final_lookup_response()


def _tool_decision(name: str, arguments: dict[str, object]) -> JsonModelResponse:
    return JsonModelResponse(
        content={"type": "tool_call", "tool_name": name, "arguments": arguments}
    )


def _final_lookup_response() -> JsonModelResponse:
    return JsonModelResponse(
        content={
            "type": "final_response",
            "content": "Alice Zhang's email is alice.zhang@example.test.",
        }
    )


def _contacts_policy_decision(
    task: object,
    history: tuple[EpisodeEvent, ...],
) -> JsonModelResponse:
    tool_names = {tool.name for tool in task.tools}
    instruction = task.instruction
    has_action = lambda name: any(
        event.event_type == "action" and event.tool_name == name for event in history
    )
    has_target_lookup = any(
        event.event_type == "action"
        and event.tool_name == "lookup_contact"
        and event.arguments == {"name": "Alice Zhang"}
        for event in history
    )
    if "stale contact label" in instruction and not history:
        return _tool_decision("lookup_contact", {"name": "Alice Zhang (stale)"})
    if "stale contact label" in instruction and not has_action("list_contacts"):
        return _tool_decision("list_contacts", {})
    if "contact directory" in instruction and not has_action("list_contacts"):
        return _tool_decision("list_contacts", {})
    if not has_target_lookup:
        return _tool_decision("lookup_contact", {"name": "Alice Zhang"})
    if "record_followup" in tool_names and not has_action("record_followup"):
        return _tool_decision(
            "record_followup",
            {"name": "Alice Zhang", "note": _requested_note(instruction)},
        )
    if "get_followup" in tool_names and not has_action("get_followup"):
        return _tool_decision("get_followup", {"name": "Alice Zhang"})
    if "record_followup" in tool_names:
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": (
                    f"Recorded '{_requested_note(instruction)}' for Alice Zhang."
                ),
            }
        )
    return _final_lookup_response()


def _requested_note(instruction: str) -> str:
    marker = 'Record exactly this follow-up note: "'
    if marker not in instruction:
        return "Please send the proposal."
    return instruction.split(marker, maxsplit=1)[1].split('".', maxsplit=1)[0]


def _direct_lookup_trace(
    *,
    redundant: bool,
    target: str = "Alice Zhang",
    email: str = "alice.zhang@example.test",
) -> ExecutionTrace:
    lookup_events = (
        EpisodeEvent(
            event_type="action",
            tool_name="lookup_contact",
            arguments={"name": target},
        ),
        EpisodeEvent(
            event_type="observation",
            tool_name="lookup_contact",
            observation={"name": target, "email": email},
        ),
    )
    return ExecutionTrace(
        mutation_authorization="not_applicable",
        events=(
            *lookup_events,
            *(lookup_events if redundant else ()),
            EpisodeEvent(
                event_type="final_response",
                content=f"{target}'s email is {email}.",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
