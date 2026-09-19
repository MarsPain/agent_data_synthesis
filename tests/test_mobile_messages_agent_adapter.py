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
    TaskSlot,
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


class _V1MobileMessagesDomainAdapter(MobileMessagesDomainAdapter):
    """Frozen pre-locality adapter identity used to prove replay drift rejection."""

    domain_version = "mobile_messages_agent_adapter_v1"


class _UngroundedMobileMutationModel(_MobileOfflinePolicyModel):
    model_id = "mobile_ungrounded_mutation_model"
    model_version = "mobile_ungrounded_mutation_model_v1"

    def complete(self, request: object) -> JsonModelResponse:
        if (
            request.role == "agent"
            and not request.observable_history
            and any(tool.name == "create_reminder" for tool in request.task.tools)
        ):
            self.requests.append(request)
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "create_reminder",
                    "arguments": {
                        "message_id": "unobserved-message-id",
                        "reminder_text": "Review the launch checklist.",
                        "remind_at": "2026-10-04T09:00:00Z",
                    },
                }
            )
        return super().complete(request)


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
        reminder_slot = _slot_for(
            slots,
            action="create_reminder",
            query="launch checklist",
            route="direct",
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

        self.assertEqual(run.known_task_capacity, 24)
        self.assertEqual(len(slots), 24)
        self.assertEqual(run.slot_capacity(100).known_task_capacity, 24)
        self.assertTrue(run.slot_capacity(100).exhausted)
        self.assertFalse(run.slot_capacity(3).exhausted)
        self.assertIsInstance(
            _slot_for(
                slots,
                action="search_messages",
                query="launch checklist",
                route="recovery",
            ),
            TaskSlot,
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
        slots = run.slots(100)
        reminder_task = _compiled_task(
            run,
            _slot_for(
                slots,
                action="create_reminder",
                query="launch checklist",
                route="direct",
            ),
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
            _slot_for(
                slots,
                action="create_draft_reply",
                query="launch checklist",
                route="direct",
                reply_constraint="open",
            ),
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
            _slot_for(
                slots,
                action="create_draft_reply",
                query="launch checklist",
                route="direct",
                reply_constraint="exact",
            ),
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
        impolite_draft_episode = run.open_episode(open_draft_task, frozen)
        impolite_draft_episode.execute_tool_call(
            "search_messages", {"query": "launch checklist"}
        )
        impolite_draft = impolite_draft_episode.execute_tool_call(
            "create_draft_reply",
            {
                "message_id": "message-aurora-001",
                "content": "No.",
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
        self.assertEqual(impolite_draft.result_type, "unauthorized_mutation")
        self.assertEqual(impolite_draft.error_code, "unsupported_reply")
        self.assertEqual(wrong_exact_reply.result_type, "unauthorized_mutation")
        self.assertEqual(wrong_exact_reply.error_code, "reply_not_authorized")

    def test_draft_assessment_requires_grounded_response_and_intended_state_only(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slot = _slot_for(
            run.slots(100),
            action="create_draft_reply",
            query="launch checklist",
            route="direct",
            reply_constraint="open",
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

    def test_verified_draft_requires_an_observed_saved_draft(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slot = _slot_for(
            run.slots(100),
            action="create_draft_reply",
            query="launch checklist",
            route="verify",
            reply_constraint="open",
        )
        task = _compiled_task(
            run,
            slot,
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply_constraint": "open",
                "route": "verify",
            },
        )
        base_events = (
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
        )
        without_verification = ExecutionTrace(
            mutation_authorization="authorized",
            events=(
                *base_events,
                EpisodeEvent(
                    event_type="final_response",
                    content=(
                        "For Alex Kim's launch checklist message, I drafted: "
                        "Thanks, I will review it today."
                    ),
                ),
            ),
        )
        verified_trace = without_verification.model_copy(
            update={
                "events": (
                    *base_events,
                    EpisodeEvent(
                        event_type="action",
                        tool_name="get_draft_reply",
                        arguments={"message_id": "message-aurora-001"},
                    ),
                    EpisodeEvent(
                        event_type="observation",
                        tool_name="get_draft_reply",
                        observation={
                            "message_id": "message-aurora-001",
                            "content": "Thanks, I will review it today.",
                        },
                    ),
                    without_verification.events[-1],
                )
            }
        )

        unverified = run.open_episode(task, run.freeze_initial_state()).assess(
            without_verification
        )
        verified = run.open_episode(task, run.freeze_initial_state()).assess(verified_trace)

        self.assertEqual({tool.name for tool in task.public_task.tools}, {
            "search_messages",
            "create_draft_reply",
            "get_draft_reply",
        })
        self.assertFalse(unverified.passed)
        self.assertIn("saved_draft_not_observed", unverified.reason_codes)
        self.assertTrue(verified.passed)
        self.assertEqual(verified.structural_key, "mobile_messages.draft.verified")

    def test_provider_mock_exercises_all_initial_mobile_behaviors_and_replay(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        model = _MobileOfflinePolicyModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="mobile-offline-behaviors",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=12,
            generation_batch_size=12,
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

        self.assertEqual(result.demonstration_count, 12)
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
                "mobile_messages.draft.verified",
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
        generation_context = json.dumps(
            [
                request.model_context()
                for request in model.requests
                if request.role == "task_generation"
            ]
        )
        self.assertNotIn("message-aurora-001", generation_context)
        self.assertNotIn("message-invoice-002", generation_context)
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

    def test_ungrounded_mutation_rejection_does_not_export_the_private_target_id(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        model = _UngroundedMobileMutationModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="mobile-ungrounded-mutation",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=4,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negatives = _read_json_lines(result.negatives_path)

        self.assertEqual(result.negative_count, 1)
        public_negative = json.dumps(negatives[0])
        self.assertNotIn("message-aurora-001", public_negative)
        self.assertIn("unobserved-message-id", public_negative)
        self.assertIsNone(negatives[0]["verification"]["state_change_evidence"])

    def test_compilation_rejects_missing_authority_negation_and_private_targets(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slots = run.slots(100)
        reminder_slot = _slot_for(
            slots,
            action="create_reminder",
            query="launch checklist",
            route="direct",
        )
        exact_draft_slot = _slot_for(
            slots,
            action="create_draft_reply",
            query="launch checklist",
            route="direct",
            reply_constraint="exact",
        )

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
        unsupported_reply = run.compile(
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
        self.assertEqual(_rejection_code(unsupported_reply), "unsupported_reply")

    def test_semantic_keys_and_reviewed_structural_examples_preserve_real_differences_only(self) -> None:
        adapter = MobileMessagesDomainAdapter.fixture()
        run = adapter.open_run(_mobile_configuration(adapter))
        slots = run.slots(100)
        direct_alex = _compiled_task(
            run,
            _slot_for(
                slots,
                action="search_messages",
                query="launch checklist",
                route="direct",
            ),
            {"action": "search_messages", "query": "launch checklist", "route": "direct"},
        )
        direct_bella = _compiled_task(
            run,
            _slot_for(
                slots,
                action="search_messages",
                query="invoice",
                route="direct",
            ),
            {"action": "search_messages", "query": "invoice", "route": "direct"},
        )
        directory_alex = _compiled_task(
            run,
            _slot_for(
                slots,
                action="search_messages",
                query="launch checklist",
                route="directory",
            ),
            {"action": "search_messages", "query": "launch checklist", "route": "directory"},
        )
        open_draft = _compiled_task(
            run,
            _slot_for(
                slots,
                action="create_draft_reply",
                query="launch checklist",
                route="direct",
                reply_constraint="open",
            ),
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply_constraint": "open",
                "route": "direct",
            },
        )
        exact_draft = _compiled_task(
            run,
            _slot_for(
                slots,
                action="create_draft_reply",
                query="launch checklist",
                route="direct",
                reply_constraint="exact",
            ),
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply": "Thanks, I will review the launch checklist.",
                "reply_constraint": "exact",
                "route": "direct",
            },
        )
        other_exact_draft = _compiled_task(
            run,
            _slot_for(
                slots,
                action="create_draft_reply",
                query="launch checklist",
                route="direct",
                reply_constraint="exact",
            ),
            {
                "action": "create_draft_reply",
                "condition": "after_message_match",
                "message_query": "launch checklist",
                "reply": "Thanks, a different but valid reply.",
                "reply_constraint": "exact",
                "route": "direct",
            },
        )
        paraphrased = run.restore_task_case(
            public_task=direct_alex.public_task.model_copy(
                update={"instruction": "Could you locate Alex Kim's launch checklist message?"}
            ),
            semantic_key=direct_alex.semantic_key,
            private_case_bytes=direct_alex.private_case_bytes,
        )
        redundant_assessment = run.open_episode(
            direct_alex, run.freeze_initial_state()
        ).assess(_direct_search_trace(redundant=True))
        bella_assessment = run.open_episode(
            direct_bella, run.freeze_initial_state()
        ).assess(
            _direct_search_trace(
                redundant=False,
                message_id="message-invoice-002",
                sender="Bella Chen",
                body="Could you check the invoice before Monday?",
                query="invoice",
            )
        )

        self.assertEqual(paraphrased.semantic_key, direct_alex.semantic_key)
        self.assertNotEqual(direct_alex.semantic_key, direct_bella.semantic_key)
        self.assertNotEqual(direct_alex.semantic_key, directory_alex.semantic_key)
        self.assertNotEqual(open_draft.semantic_key, exact_draft.semantic_key)
        self.assertNotEqual(exact_draft.semantic_key, other_exact_draft.semantic_key)
        self.assertTrue(redundant_assessment.passed)
        self.assertEqual(
            redundant_assessment.structural_key, "mobile_messages.search.direct"
        )
        self.assertTrue(bella_assessment.passed)
        self.assertEqual(bella_assessment.structural_key, "mobile_messages.search.direct")
        self.assertEqual(
            {example.expected_structural_key for example in run.reviewed_structural_examples},
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
                "mobile_messages.draft.verified",
            },
        )
        self.assertTrue(
            {"paraphrase", "entity_substitution", "padded_tool_sequence"}.issubset(
                {example.variation for example in run.reviewed_structural_examples}
            )
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
                                "content": "Thanks, already drafted.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_mobile_configuration(adapter))
            frozen_payload = json.loads(run.freeze_initial_state().contents)
            slots = run.slots(100)

        self.assertEqual(run.known_task_capacity, 15)
        self.assertEqual(frozen_payload["reminders"][0]["reminder_text"], "Already scheduled.")
        self.assertEqual(
            frozen_payload["drafts"][0]["content"], "Thanks, already drafted."
        )
        self.assertIsInstance(
            _slot_for(
                slots,
                action="search_messages",
                query="launch checklist",
                route="direct",
            ),
            TaskSlot,
        )
        self.assertFalse(
            any(
                _slot_payload(slot).get("action")
                in {"create_reminder", "create_draft_reply"}
                and _slot_payload(slot).get("message_query") == "launch checklist"
                for slot in slots
            )
        )

    def test_invalid_local_source_stops_before_any_model_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "invalid-messages.json"
            source_path.write_text('{"messages": [], "reminders": [], "drafts": []}', encoding="utf-8")
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            model = _MobileOfflinePolicyModel()
            engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
            configuration = RunConfiguration(
                run_id="mobile-invalid-source",
                domain_id=adapter.domain_id,
                model_id=model.model_id,
                slot_limit=1,
            )

            with self.assertRaisesRegex(ValueError, "non-empty messages"):
                engine.run(configuration, root / "run")

        self.assertEqual(model.requests, [])

    def test_replay_rejects_a_pre_locality_domain_version(self) -> None:
        old_adapter = _V1MobileMessagesDomainAdapter.fixture()
        model = _MobileOfflinePolicyModel()
        old_engine = SynthesisEngine(
            AdapterRegistry(domains=(old_adapter,), models=(model,))
        )
        configuration = RunConfiguration(
            run_id="mobile-pre-locality-version",
            domain_id=old_adapter.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            run = old_engine.run(configuration, Path(temporary_directory))
            current_engine = SynthesisEngine(
                AdapterRegistry(domains=(MobileMessagesDomainAdapter.fixture(),), models=())
            )
            with self.assertRaisesRegex(ValueError, "Domain version does not match"):
                current_engine.replay(run.run_directory)

        self.assertEqual(
            MobileMessagesDomainAdapter.domain_version,
            "mobile_messages_agent_adapter_v2",
        )

    def test_capacity_omits_exact_draft_slots_that_cannot_form_an_allowed_default_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "long-message.json"
            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {
                                "message_id": "message-long-001",
                                "sender": "Long Sender",
                                "body": "x" * 250,
                            }
                        ],
                        "reminders": [],
                        "drafts": [],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_mobile_configuration(adapter))
            slots = run.slots(100)
            compilations = [
                run.compile(
                    slot,
                    TaskProposal(
                        content=slot.proposal_prompt.removeprefix(
                            "Return exactly this JSON proposal: "
                        )
                    ),
                )
                for slot in slots
            ]

        self.assertEqual(run.known_task_capacity, 11)
        self.assertFalse(
            any(
                _slot_payload(slot).get("reply_constraint") == "exact"
                for slot in slots
            )
        )
        self.assertFalse(any(isinstance(item, CompilationRejection) for item in compilations))

    def test_ambiguous_message_selectors_are_excluded_and_rejected_before_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "ambiguous-messages.json"
            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {
                                "message_id": "message-alpha-001",
                                "sender": "Alex Kim",
                                "body": "alpha",
                            },
                            {
                                "message_id": "message-alpha-002",
                                "sender": "Bella Chen",
                                "body": "today alpha tomorrow",
                            },
                        ],
                        "reminders": [],
                        "drafts": [],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_mobile_configuration(adapter))
            slots = run.slots(100)
            ambiguous_compilation = run.compile(
                TaskSlot(
                    slot_id=_opaque_slot_id(
                        slot_kind="search-direct",
                        message_id="message-alpha-001",
                        sender="Alex Kim",
                        body="alpha",
                    ),
                    proposal_prompt="test-only ambiguous slot",
                ),
                TaskProposal(
                    content=json.dumps(
                        {
                            "action": "search_messages",
                            "query": "alpha",
                            "route": "direct",
                        }
                    )
                ),
            )

        self.assertEqual(run.known_task_capacity, 12)
        self.assertFalse(any("message-alpha-001" in slot.slot_id for slot in slots))
        self.assertEqual(
            _rejection_code(ambiguous_compilation), "unresolved_target_ambiguity"
        )

    def test_slot_components_are_bounded_and_collision_safe_for_admitted_source_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "slot-component-collisions.json"
            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {"message_id": "m-1", "sender": "One", "body": "first"},
                            {"message_id": "m_1", "sender": "Two", "body": "second"},
                            {
                                "message_id": "z" * 1_000,
                                "sender": "Three",
                                "body": "third",
                            },
                        ],
                        "reminders": [],
                        "drafts": [],
                    }
                ),
                encoding="utf-8",
            )
            adapter = MobileMessagesDomainAdapter.from_local_file(source_path)
            run = adapter.open_run(_mobile_configuration(adapter))
            slots = run.slots(100)
            compilations = [
                run.compile(
                    slot,
                    TaskProposal(
                        content=slot.proposal_prompt.removeprefix(
                            "Return exactly this JSON proposal: "
                        )
                    ),
                )
                for slot in slots
            ]

        self.assertEqual(run.known_task_capacity, 36)
        self.assertEqual(len(slots), 36)
        self.assertEqual(len({slot.slot_id for slot in slots}), 36)
        self.assertTrue(all(len(slot.slot_id) <= 256 for slot in slots))
        self.assertFalse(any(isinstance(item, CompilationRejection) for item in compilations))


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _mobile_configuration(adapter: MobileMessagesDomainAdapter) -> RunConfiguration:
    return RunConfiguration(
        run_id="mobile-domain-seam",
        domain_id=adapter.domain_id,
        model_id="mobile_direct_search_model",
        slot_limit=24,
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


def _slot_for(
    slots: object,
    *,
    action: str,
    query: str,
    route: str,
    reply_constraint: str | None = None,
) -> TaskSlot:
    for slot in slots:
        payload = _slot_payload(slot)
        if (
            payload.get("action") == action
            and payload.get("query", payload.get("message_query")) == query
            and payload.get("route") == route
            and (
                reply_constraint is None
                or payload.get("reply_constraint") == reply_constraint
            )
        ):
            return slot
    raise AssertionError("expected deterministic Mobile Messages slot was not emitted")


def _slot_payload(slot: TaskSlot) -> dict[str, str]:
    return json.loads(
        slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: ")
    )


def _opaque_slot_id(
    *,
    slot_kind: str,
    message_id: str,
    sender: str,
    body: str,
) -> str:
    identity = json.dumps(
        {"message_id": message_id, "sender": sender, "body": body},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:24]
    return f"mobile-{slot_kind}-message-{digest}"


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
    if "get_draft_reply" in tool_names and not has_action("get_draft_reply"):
        return tool_call("get_draft_reply", {"message_id": message_id})
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


def _direct_search_trace(
    *,
    redundant: bool,
    message_id: str = "message-aurora-001",
    sender: str = "Alex Kim",
    body: str = "Please review the launch checklist before Friday.",
    query: str = "launch checklist",
) -> ExecutionTrace:
    search_events = (
        EpisodeEvent(
            event_type="action",
            tool_name="search_messages",
            arguments={"query": query},
        ),
        EpisodeEvent(
            event_type="observation",
            tool_name="search_messages",
            observation={"message_id": message_id, "sender": sender, "body": body},
        ),
    )
    return ExecutionTrace(
        mutation_authorization="not_applicable",
        events=(
            *search_events,
            *(search_events if redundant else ()),
            EpisodeEvent(
                event_type="final_response",
                content=f"I found {sender}'s {query} message.",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
