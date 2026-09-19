from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

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
from agent_synthesis.mobile_messages import MobileMessagesDomainAdapter
from agent_synthesis.ledger import PrivateLedger
from tests.agent_first_compliance import assert_agent_episode_compliance


class _DirectMessageSearchModel:
    """One deterministic provider mock at the public model seam."""

    model_id = "mobile_direct_search_model"
    model_version = "mobile_direct_search_model_v1"
    provider_id = "deterministic_fake"

    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "task_generation":
            slot = request.slots[0]
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": json.dumps(
                                {
                                    "action": "search_messages",
                                    "query": "launch checklist",
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
                    "tool_name": "search_messages",
                    "arguments": {"query": "launch checklist"},
                }
            )
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": (
                    "Alex Kim's message says: Please review the launch checklist "
                    "before Friday."
                ),
            }
        )


class _MobileOfflinePolicyModel:
    """A deterministic Agent policy consuming only public model contexts."""

    model_id = "mobile_offline_policy_model"
    model_version = "mobile_offline_policy_model_v1"
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
        return _mobile_policy_decision(request.task, request.observable_history)


class _WrongMobileMutationModel(_MobileOfflinePolicyModel):
    model_id = "mobile_wrong_mutation_model"
    model_version = "mobile_wrong_mutation_model_v1"

    def complete(self, request: object) -> JsonModelResponse:
        response = super().complete(request)
        if (
            request.role == "agent"
            and response.content.get("type") == "tool_call"
            and response.content.get("tool_name") in {"create_reminder", "create_draft_reply"}
        ):
            arguments = dict(response.content["arguments"])
            arguments["message_id"] = "message-invoice-002"
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": response.content["tool_name"],
                    "arguments": arguments,
                }
            )
        return response


class MobileMessagesAgentAdapterTest(unittest.TestCase):
    def test_fixture_message_search_runs_through_the_engine_with_private_source_state(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        model = _DirectMessageSearchModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="mobile-direct-search",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
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
        self.assertEqual(
            demonstrations[0]["task"]["instruction"],
            'Find the message from Alex Kim that mentions "launch checklist".',
        )
        self.assertEqual(
            demonstrations[0]["events"][1]["observation"],
            {
                "body": "Please review the launch checklist before Friday.",
                "message_id": "message-aurora-001",
                "sender": "Alex Kim",
            },
        )
        self.assertEqual(
            demonstrations[0]["verification"]["structural_key"],
            "mobile_messages.search.direct",
        )
        self.assertNotIn('"messages":[', public_artifacts)

    def test_slots_disclose_capacity_and_compile_a_bound_reminder_request(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slots = run.slots(100)
        reminder_slot = next(
            slot
            for slot in slots
            if slot.slot_id == "mobile-reminder-direct-message-aurora-001"
        )

        compilation = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_reminder",
                        "condition": "after_message_match",
                        "message_query": "launch checklist",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    },
                    sort_keys=True,
                )
            ),
        )
        wrong_message = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_reminder",
                        "condition": "after_message_match",
                        "message_query": "invoice",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    },
                    sort_keys=True,
                )
            ),
        )

        self.assertEqual(run.known_task_capacity, 22)
        self.assertEqual(len(slots), 22)
        self.assertEqual(run.slot_capacity(100).known_task_capacity, 22)
        self.assertTrue(run.slot_capacity(100).exhausted)
        self.assertFalse(run.slot_capacity(3).exhausted)
        self.assertIn(
            "mobile-search-recovery-message-aurora-001",
            {slot.slot_id for slot in slots},
        )
        self.assertNotIsInstance(compilation, CompilationRejection)
        assert not isinstance(compilation, CompilationRejection)
        self.assertIn("create a reminder", compilation.public_task.instruction)
        self.assertIn("Review the launch checklist.", compilation.public_task.instruction)
        self.assertRegex(
            compilation.semantic_key,
            r"^mobile_messages:semantic:sha256:[0-9a-f]{64}$",
        )
        self.assertIsInstance(wrong_message, CompilationRejection)
        assert isinstance(wrong_message, CompilationRejection)
        self.assertEqual(wrong_message.reason_code, "wrong_message_binding")

    def test_mutations_require_an_observed_message_and_distinguish_open_from_exact_drafts(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        frozen = run.freeze_initial_state()
        slots = {slot.slot_id: slot for slot in run.slots(100)}
        reminder_task = _compiled_task(
            run,
            slots["mobile-reminder-direct-message-aurora-001"],
            {
                "action": "create_reminder",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "remind_at": "2026-10-04T09:00:00Z",
                "reminder_text": "Review the launch checklist.",
                "route": "direct",
            },
        )
        open_draft_task = _compiled_task(
            run,
            slots["mobile-draft-direct-message-aurora-001"],
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply_constraint": "open",
                "route": "direct",
            },
        )
        exact_draft_task = _compiled_task(
            run,
            slots["mobile-draft-exact-message-aurora-001"],
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply": "Thanks, I will review the launch checklist.",
                "reply_constraint": "exact",
                "route": "direct",
            },
        )

        ungrounded_episode = run.open_episode(reminder_task, frozen)
        ungrounded_mutation = ungrounded_episode.execute_tool_call(
            "create_reminder",
            {
                "message_id": "message-aurora-001",
                "reminder_text": "Review the launch checklist.",
                "remind_at": "2026-10-04T09:00:00Z",
            },
        )
        reminder_episode = run.open_episode(reminder_task, frozen)
        reminder_episode.execute_tool_call(
            "search_messages", {"query": "launch checklist"}
        )
        reminder_mutation = reminder_episode.execute_tool_call(
            "create_reminder",
            {
                "message_id": "message-aurora-001",
                "reminder_text": "Review the launch checklist.",
                "remind_at": "2026-10-04T09:00:00Z",
            },
        )
        open_draft_episode = run.open_episode(open_draft_task, frozen)
        open_draft_episode.execute_tool_call(
            "search_messages", {"query": "launch checklist"}
        )
        open_draft_mutation = open_draft_episode.execute_tool_call(
            "create_draft_reply",
            {
                "message_id": "message-aurora-001",
                "content": "Thanks, I will review it today.",
            },
        )
        exact_draft_episode = run.open_episode(exact_draft_task, frozen)
        exact_draft_episode.execute_tool_call(
            "search_messages", {"query": "launch checklist"}
        )
        wrong_exact_reply = exact_draft_episode.execute_tool_call(
            "create_draft_reply",
            {
                "message_id": "message-aurora-001",
                "content": "Thanks, I will review it today.",
            },
        )

        self.assertEqual(ungrounded_mutation.result_type, "unauthorized_mutation")
        self.assertEqual(ungrounded_mutation.error_code, "mutation_condition_not_observed")
        self.assertEqual(reminder_mutation.result_type, "state_change")
        self.assertEqual(
            reminder_mutation.change,
            {
                "message_id": "message-aurora-001",
                "reminder_text": "Review the launch checklist.",
                "remind_at": "2026-10-04T09:00:00Z",
            },
        )
        self.assertEqual(open_draft_mutation.result_type, "state_change")
        self.assertEqual(
            open_draft_mutation.change,
            {
                "message_id": "message-aurora-001",
                "content": "Thanks, I will review it today.",
            },
        )
        self.assertEqual(wrong_exact_reply.result_type, "unauthorized_mutation")
        self.assertEqual(wrong_exact_reply.error_code, "reply_not_authorized")

    def test_draft_assessment_requires_grounded_response_and_intended_state_only(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slot = next(
            item
            for item in run.slots(100)
            if item.slot_id == "mobile-draft-direct-message-aurora-001"
        )
        task = _compiled_task(
            run,
            slot,
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply_constraint": "open",
                "route": "direct",
            },
        )
        trace = ExecutionTrace(
            mutation_authorization="authorized",
            events=(
                EpisodeEvent(
                    event_type="action",
                    tool_name="search_messages",
                    arguments={"query": "launch checklist"},
                ),
                EpisodeEvent(
                    event_type="observation",
                    tool_name="search_messages",
                    observation={
                        "message_id": "message-aurora-001",
                        "sender": "Alex Kim",
                        "body": "Please review the launch checklist before Friday.",
                    },
                ),
                EpisodeEvent(
                    event_type="action",
                    tool_name="create_draft_reply",
                    arguments={
                        "message_id": "message-aurora-001",
                        "content": "Thanks, I will review it today.",
                    },
                ),
                EpisodeEvent(
                    event_type="state_change",
                    tool_name="create_draft_reply",
                    change={
                        "message_id": "message-aurora-001",
                        "content": "Thanks, I will review it today.",
                    },
                ),
                EpisodeEvent(
                    event_type="final_response",
                    content=(
                        "For Alex Kim's launch checklist message, I drafted: "
                        "Thanks, I will review it today."
                    ),
                ),
            ),
        )
        ungrounded_trace = trace.model_copy(
            update={
                "events": (
                    *trace.events[:-1],
                    EpisodeEvent(
                        event_type="final_response",
                        content="The draft is ready.",
                    ),
                )
            }
        )

        assessment = run.open_episode(task, run.freeze_initial_state()).assess(trace)
        ungrounded = run.open_episode(task, run.freeze_initial_state()).assess(
            ungrounded_trace
        )

        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.structural_key, "mobile_messages.draft.direct")
        self.assertFalse(ungrounded.passed)
        self.assertIn("final_response_not_grounded", ungrounded.reason_codes)

    def test_provider_mock_exercises_all_initial_mobile_behaviors_and_replay(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        model = _MobileOfflinePolicyModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="mobile-offline-behaviors",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=11,
            generation_batch_size=11,
            total_request_limit=128,
            generation_request_limit=8,
            agent_request_limit=120,
            max_output_tokens=128,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(result.demonstrations_path)
            negatives = _read_json_lines(result.negatives_path)
            replay = engine.replay(result.run_directory)

        self.assertEqual(result.demonstration_count, 11)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(negatives, [])
        self.assertEqual(
            {item["verification"]["structural_key"] for item in demonstrations},
            {
                "mobile_messages.search.direct",
                "mobile_messages.search.directory",
                "mobile_messages.search.recovery",
                "mobile_messages.reminder.direct",
                "mobile_messages.reminder.directory",
                "mobile_messages.reminder.recovery",
                "mobile_messages.reminder.verified",
                "mobile_messages.draft.direct",
                "mobile_messages.draft.directory",
                "mobile_messages.draft.recovery",
                "mobile_messages.draft.exact",
            },
        )
        recovery = next(
            item
            for item in demonstrations
            if item["verification"]["structural_key"] == "mobile_messages.search.recovery"
        )
        self.assertEqual(recovery["events"][1]["error_code"], "message_not_found")
        self.assertTrue(replay.aligned)
        public_episode_text = json.dumps([*demonstrations, *negatives])
        for private_field in ("exact_reply", "private_case_bytes", "expected_state"):
            self.assertNotIn(private_field, public_episode_text)
        assert_agent_episode_compliance(
            self,
            demonstrations=demonstrations,
            negatives=negatives,
            replay_aligned=replay.aligned,
        )

    def test_unauthorized_mutation_is_rejected_before_a_state_change(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        model = _WrongMobileMutationModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="mobile-unauthorized-reminder",
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
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "unauthorized_mutation")
        self.assertEqual(negatives[0]["mutation_authorization"], "rejected")
        self.assertFalse(
            any(event["event_type"] == "state_change" for event in negatives[0]["events"])
        )

    def test_compilation_rejects_missing_authority_negation_and_private_targets(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slots = {slot.slot_id: slot for slot in run.slots(100)}
        reminder_slot = slots["mobile-reminder-direct-message-aurora-001"]
        exact_draft_slot = slots["mobile-draft-exact-message-aurora-001"]

        missing_authority = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_reminder",
                        "message_query": "launch checklist",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    }
                )
            ),
        )
        negated = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "do_not_create_reminder",
                        "condition": "after_message_match",
                        "message_query": "launch checklist",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    }
                )
            ),
        )
        uncheckable_condition = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_reminder",
                        "condition": "after_a_good_feeling",
                        "message_query": "launch checklist",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    }
                )
            ),
        )
        private_target = run.compile(
            reminder_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_reminder",
                        "condition": "after_message_match",
                        "message_id": "message-aurora-001",
                        "message_query": "launch checklist",
                        "remind_at": "2026-10-04T09:00:00Z",
                        "reminder_text": "Review the launch checklist.",
                        "route": "direct",
                    }
                )
            ),
        )
        unsupported_exact_reply = run.compile(
            exact_draft_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_draft_reply",
                        "condition": "after_message_match",
                        "message_query": "launch checklist",
                        "reply": "A different but valid reply.",
                        "reply_constraint": "exact",
                        "route": "direct",
                    }
                )
            ),
        )

        self.assertEqual(_rejection_code(missing_authority), "missing_mutation_authority")
        self.assertEqual(_rejection_code(negated), "negated_action")
        self.assertEqual(_rejection_code(uncheckable_condition), "uncheckable_condition")
        self.assertEqual(_rejection_code(private_target), "unsupported_private_exact_target")
        self.assertEqual(
            _rejection_code(unsupported_exact_reply), "unsupported_private_exact_target"
        )

    def test_local_source_is_frozen_before_model_work_and_replay_ignores_later_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "messages.json"
            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {
                                "message_id": "message-aurora-001",
                                "sender": "Alex Kim",
                                "body": "Please review the launch checklist before Friday.",
                            }
                        ],
                        "reminders": [],
                        "drafts": [],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            model = _MobileOfflinePolicyModel()
            engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
            configuration = RunConfiguration(
                run_id="mobile-local-replay",
                domain_id=adapter.domain_id,
                model_id=model.model_id,
                slot_limit=1,
            )
            result = engine.run(configuration, root / "run")
            request_count_before_replay = len(model.requests)
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                frozen = ledger.initial_state()
            finally:
                ledger.close()

            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {
                                "message_id": "message-aurora-001",
                                "sender": "Alex Kim",
                                "body": "Changed after admission.",
                            }
                        ],
                        "reminders": [],
                        "drafts": [],
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
        self.assertIn(b"launch checklist", frozen.contents)
        self.assertTrue(replay.aligned)
        self.assertEqual(len(model.requests), request_count_before_replay)

    def test_existing_reminders_and_drafts_exhaust_only_unsafe_mutation_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "messages-with-state.json"
            source_path.write_text(
                json.dumps(
                    {
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
                        "reminders": [
                            {
                                "message_id": "message-aurora-001",
                                "reminder_text": "Already scheduled.",
                                "remind_at": "2026-10-01T09:00:00Z",
                            }
                        ],
                        "drafts": [
                            {
                                "message_id": "message-aurora-001",
                                "content": "Already drafted.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_mobile_configuration(adapter))
            frozen_payload = json.loads(run.freeze_initial_state().contents)
            slot_ids = {slot.slot_id for slot in run.slots(100)}

        self.assertEqual(run.known_task_capacity, 14)
        self.assertEqual(frozen_payload["reminders"][0]["reminder_text"], "Already scheduled.")
        self.assertEqual(frozen_payload["drafts"][0]["content"], "Already drafted.")
        self.assertIn("mobile-search-direct-message-aurora-001", slot_ids)
        self.assertNotIn("mobile-reminder-direct-message-aurora-001", slot_ids)
        self.assertNotIn("mobile-draft-direct-message-aurora-001", slot_ids)


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _mobile_configuration(adapter: MobileMessagesDomainAdapter) -> RunConfiguration:
    return RunConfiguration(
        run_id="mobile-domain-seam",
        domain_id=adapter.domain_id,
        model_id="mobile_direct_search_model",
        slot_limit=22,
    )


def _compiled_task(run: object, slot: object, payload: dict[str, str]) -> object:
    compilation = run.compile(
        slot,
        TaskProposal(content=json.dumps(payload, sort_keys=True)),
    )
    assert not isinstance(compilation, CompilationRejection)
    return compilation


def _rejection_code(compilation: object) -> str:
    assert isinstance(compilation, CompilationRejection)
    return compilation.reason_code


def _mobile_policy_decision(
    task: object,
    history: tuple[EpisodeEvent, ...],
) -> JsonModelResponse:
    instruction = task.instruction
    tool_names = {tool.name for tool in task.tools}

    def has_action(name: str) -> bool:
        return any(
            event.event_type == "action" and event.tool_name == name for event in history
        )

    def tool_call(name: str, arguments: dict[str, object]) -> JsonModelResponse:
        return JsonModelResponse(
            content={"type": "tool_call", "tool_name": name, "arguments": arguments}
        )

    target_query = _requested_query(instruction)
    message = next(
        (
            event.observation
            for event in reversed(history)
            if event.event_type == "observation"
            and event.tool_name == "search_messages"
            and isinstance(event.observation, dict)
        ),
        None,
    )
    if "stale message query" in instruction and not history:
        return tool_call("search_messages", {"query": f"{target_query} (stale)"})
    if "stale message query" in instruction and not has_action("list_message_senders"):
        return tool_call("list_message_senders", {})
    if "sender list" in instruction and not has_action("list_message_senders"):
        return tool_call("list_message_senders", {})
    if not isinstance(message, dict):
        return tool_call("search_messages", {"query": target_query})
    message_id = message["message_id"]
    sender = message["sender"]
    if "create_reminder" in tool_names and not has_action("create_reminder"):
        reminder = re.search(
            r'create a reminder for (?P<remind_at>[^ ]+) that says "(?P<text>[^"]+)"',
            instruction,
        )
        assert reminder is not None
        return tool_call(
            "create_reminder",
            {
                "message_id": message_id,
                "reminder_text": reminder.group("text"),
                "remind_at": reminder.group("remind_at"),
            },
        )
    if "create_draft_reply" in tool_names and not has_action("create_draft_reply"):
        exact = re.search(r'Draft exactly this reply: "(?P<reply>[^"]+)"', instruction)
        content = exact.group("reply") if exact is not None else "Thanks, I will review it today."
        return tool_call(
            "create_draft_reply",
            {"message_id": message_id, "content": content},
        )
    if "get_reminder" in tool_names and not has_action("get_reminder"):
        return tool_call("get_reminder", {"message_id": message_id})
    if "create_reminder" in tool_names:
        reminder = re.search(
            r'create a reminder for (?P<remind_at>[^ ]+) that says "(?P<text>[^"]+)"',
            instruction,
        )
        assert reminder is not None
        content = (
            f"For {sender}'s {target_query} message, I saved reminder "
            f"{reminder.group('text')} at {reminder.group('remind_at')}."
        )
    elif "create_draft_reply" in tool_names:
        exact = re.search(r'Draft exactly this reply: "(?P<reply>[^"]+)"', instruction)
        reply = exact.group("reply") if exact is not None else "Thanks, I will review it today."
        content = f"For {sender}'s {target_query} message, I drafted: {reply}"
    else:
        content = f"I found {sender}'s {target_query} message."
    return JsonModelResponse(content={"type": "final_response", "content": content})


def _requested_query(instruction: str) -> str:
    matches = re.findall(r'mentions "([^"]+)"', instruction)
    assert matches
    return matches[-1]


if __name__ == "__main__":
    unittest.main()
