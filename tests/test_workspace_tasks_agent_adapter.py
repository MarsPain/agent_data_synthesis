from __future__ import annotations

import json
import hashlib
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
from agent_synthesis.workspace_tasks import WorkspaceTasksDomainAdapter
from agent_synthesis.ledger import PrivateLedger
from tests.agent_first_compliance import assert_agent_episode_compliance


class _DirectWorkspaceSearchModel:
    """A deterministic provider mock that uses only the public episode context."""

    model_id = "workspace_direct_search_model"
    model_version = "workspace_direct_search_model_v1"
    provider_id = "deterministic_fake"

    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "task_generation":
            slot = request.slots[0]
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": slot.proposal_prompt.removeprefix(
                                "Return exactly this JSON proposal: "
                            ),
                        }
                    ]
                }
            )
        if not request.observable_history:
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "search_workspace_items",
                    "arguments": {"query": "launch brief", "kind": "document"},
                }
            )
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": "The Launch Brief document is available in the workspace.",
            }
        )


class _WorkspaceOfflinePolicyModel:
    """A deterministic Agent policy consuming only public task and event data."""

    model_id = "workspace_offline_policy_model"
    model_version = "workspace_offline_policy_model_v1"
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
        tool_names = {tool.name for tool in request.task.tools}
        last_event = history[-1] if history else None
        search_arguments = _public_search_arguments(instruction)

        if "create_workspace_task" in tool_names:
            observation = _last_search_observation(history)
            if observation is None:
                return JsonModelResponse(
                    content={
                        "type": "tool_call",
                        "tool_name": "search_workspace_items",
                        "arguments": search_arguments,
                    }
                )
            if last_event is not None and last_event.event_type == "state_change":
                if "get_workspace_task" in tool_names:
                    return JsonModelResponse(
                        content={
                            "type": "tool_call",
                            "tool_name": "get_workspace_task",
                            "arguments": {"task_id": last_event.change["task_id"]},
                        }
                    )
                return _workspace_final_response(instruction, history)
            if last_event is not None and last_event.tool_name == "get_workspace_task":
                return _workspace_final_response(instruction, history)
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "create_workspace_task",
                    "arguments": {
                        "project_id": observation["item_id"],
                        "title": (
                            _quoted_value(instruction, "create a task titled")
                            if "create a task titled" in instruction
                            else _open_task_title(instruction)
                        ),
                        "priority": _task_priority(instruction),
                        "due_label": _task_due_label(instruction),
                    },
                }
            )

        if "add_workspace_comment" in tool_names:
            observation = _last_search_observation(history)
            if observation is None:
                if not history and "stale workspace query" in instruction:
                    return JsonModelResponse(
                        content={
                            "type": "tool_call",
                            "tool_name": "search_workspace_items",
                            "arguments": _public_search_arguments(instruction, stale=True),
                        }
                    )
                return JsonModelResponse(
                    content={
                        "type": "tool_call",
                        "tool_name": "search_workspace_items",
                        "arguments": search_arguments,
                    }
                )
            if last_event is not None and last_event.event_type == "state_change":
                if "get_workspace_comment" in tool_names:
                    return JsonModelResponse(
                        content={
                            "type": "tool_call",
                            "tool_name": "get_workspace_comment",
                            "arguments": {"comment_id": last_event.change["comment_id"]},
                        }
                    )
                return _workspace_final_response(instruction, history)
            if last_event is not None and last_event.tool_name == "get_workspace_comment":
                return _workspace_final_response(instruction, history)
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "add_workspace_comment",
                    "arguments": {
                        "task_id": observation["item_id"],
                        "comment": _public_comment(instruction),
                    },
                }
            )

        if "list_workspace_projects" in tool_names and not history:
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "list_workspace_projects",
                    "arguments": {},
                }
            )
        if "stale workspace query" in instruction and not history:
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "search_workspace_items",
                    "arguments": _public_search_arguments(instruction, stale=True),
                }
            )
        if _last_search_observation(history) is None and not _has_search_failure(history):
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "search_workspace_items",
                    "arguments": search_arguments,
                }
            )
        if (
            _last_search_observation(history) is None
            and _has_search_failure(history)
            and "stale workspace query" in instruction
        ):
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "search_workspace_items",
                    "arguments": search_arguments,
                }
            )
        return _workspace_final_response(instruction, history)


class _WrongWorkspaceMutationModel(_WorkspaceOfflinePolicyModel):
    model_id = "workspace_wrong_mutation_model"
    model_version = "workspace_wrong_mutation_model_v1"

    def complete(self, request: object) -> JsonModelResponse:
        if (
            request.role == "agent"
            and not request.observable_history
            and any(tool.name == "create_workspace_task" for tool in request.task.tools)
        ):
            self.requests.append(request)
            return JsonModelResponse(
                content={
                    "type": "tool_call",
                    "tool_name": "create_workspace_task",
                    "arguments": {
                        "project_id": "unobserved-project-id",
                        "title": "Prepare Alpha Launch retrospective",
                        "priority": "high",
                        "due_label": "next_week",
                    },
                }
            )
        return super().complete(request)


class WorkspaceTasksAgentAdapterTest(unittest.TestCase):
    def test_fixture_item_search_runs_through_the_engine_with_private_source_state(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        model = _DirectWorkspaceSearchModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="workspace-direct-search",
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
            'Find the workspace document that matches "launch brief".',
        )
        self.assertEqual(
            demonstrations[0]["events"][1]["observation"],
            {
                "item_id": "document-launch-brief-001",
                "kind": "document",
                "summary": "Launch Brief",
            },
        )
        self.assertEqual(
            demonstrations[0]["verification"]["structural_key"],
            "workspace_tasks.search.direct",
        )
        self.assertNotIn('"projects"', public_artifacts)

    def test_slots_disclose_capacity_and_compile_a_bound_task_request(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        slots = run.slots(100)
        task_slot = _slot_for(
            slots,
            action="create_workspace_task",
            query="alpha launch",
            route="direct",
        )

        compilation = run.compile(
            task_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_workspace_task",
                        "condition": "after_item_match",
                        "due_label": "next_week",
                        "priority": "high",
                        "project_kind": "project",
                        "project_query": "alpha launch",
                        "route": "direct",
                        "title": "Prepare Alpha Launch retrospective",
                    },
                    sort_keys=True,
                )
            ),
        )
        wrong_project = run.compile(
            task_slot,
            TaskProposal(
                content=json.dumps(
                    {
                        "action": "create_workspace_task",
                        "condition": "after_item_match",
                        "due_label": "next_week",
                        "priority": "high",
                        "project_kind": "project",
                        "project_query": "beta research",
                        "route": "direct",
                        "title": "Prepare Alpha Launch retrospective",
                    },
                    sort_keys=True,
                )
            ),
        )

        self.assertEqual(run.known_task_capacity, 9)
        self.assertEqual(len(slots), 9)
        self.assertEqual(run.slot_capacity(100).known_task_capacity, 9)
        self.assertTrue(run.slot_capacity(100).exhausted)
        self.assertFalse(run.slot_capacity(3).exhausted)
        self.assertNotIsInstance(compilation, CompilationRejection)
        assert not isinstance(compilation, CompilationRejection)
        self.assertIn("create a task", compilation.public_task.instruction)
        self.assertIn("Prepare Alpha Launch retrospective", compilation.public_task.instruction)
        self.assertRegex(
            compilation.semantic_key,
            r"^workspace_tasks:semantic:sha256:[0-9a-f]{64}$",
        )
        self.assertIsInstance(wrong_project, CompilationRejection)
        assert isinstance(wrong_project, CompilationRejection)
        self.assertEqual(wrong_project.reason_code, "wrong_item_binding")

    def test_all_unique_target_scope_exposes_multiple_targets_per_family(self) -> None:
        source = {
            "projects": [
                {"project_id": f"project-{index}", "name": f"Project {index}"}
                for index in range(4)
            ],
            "tasks": [
                {
                    "task_id": f"task-{index}",
                    "project_id": f"project-{index}",
                    "title": f"Task {index}",
                }
                for index in range(4)
            ],
            "documents": [
                {
                    "document_id": f"document-{index}",
                    "project_id": f"project-{index}",
                    "title": f"Document {index}",
                    "body": f"Body {index}",
                }
                for index in range(4)
            ],
            "comments": [],
        }
        adapter = WorkspaceTasksDomainAdapter(
            json.dumps(source).encode("utf-8"), target_scope="all_unique"
        )
        run = adapter.open_run(_workspace_configuration(adapter))
        slots = run.slots(100)
        payloads = [
            json.loads(slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: "))
            for slot in slots
        ]

        self.assertEqual(run.known_task_capacity, 33)
        self.assertEqual(len(slots), 33)
        self.assertEqual(len({slot.slot_id for slot in slots}), 33)
        self.assertEqual(
            len({(payload["action"], payload["route"]) for payload in payloads[:9]}),
            9,
        )
        self.assertNotEqual(adapter.domain_version, WorkspaceTasksDomainAdapter.domain_version)

    def test_mutations_require_an_observed_item_and_distinguish_open_from_exact_comments(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        frozen = run.freeze_initial_state()
        slots = run.slots(100)
        task = _compiled_task(
            run,
            _slot_for(
                slots,
                action="create_workspace_task",
                query="alpha launch",
                route="direct",
            ),
            {
                "action": "create_workspace_task",
                "condition": "after_item_match",
                "due_label": "next_week",
                "priority": "high",
                "project_kind": "project",
                "project_query": "alpha launch",
                "route": "direct",
                "title": "Prepare Alpha Launch retrospective",
            },
        )
        open_comment = _compiled_task(
            run,
            _slot_for(
                slots,
                action="add_workspace_comment",
                query="launch plan",
                route="direct",
            ),
            {
                "action": "add_workspace_comment",
                "comment_constraint": "open",
                "condition": "after_item_match",
                "route": "direct",
                "task_kind": "task",
                "task_query": "launch plan",
            },
        )
        exact_recovery_comment = _compiled_task(
            run,
            _slot_for(
                slots,
                action="add_workspace_comment",
                query="research notes",
                route="recovery",
            ),
            {
                "action": "add_workspace_comment",
                "comment": "Status: research notes is ready for review.",
                "comment_constraint": "exact",
                "condition": "after_item_match",
                "route": "recovery",
                "task_kind": "task",
                "task_query": "research notes",
            },
        )

        ungrounded_task = run.open_episode(task, frozen).execute_tool_call(
            "create_workspace_task",
            {
                "project_id": "project-alpha-001",
                "title": "Prepare Alpha Launch retrospective",
                "priority": "high",
                "due_label": "next_week",
            },
        )
        task_episode = run.open_episode(task, frozen)
        task_episode.execute_tool_call(
            "search_workspace_items", {"query": "alpha launch", "kind": "project"}
        )
        created_task = task_episode.execute_tool_call(
            "create_workspace_task",
            {
                "project_id": "project-alpha-001",
                "title": "Prepare Alpha Launch retrospective",
                "priority": "high",
                "due_label": "next_week",
            },
        )
        open_comment_episode = run.open_episode(open_comment, frozen)
        open_comment_episode.execute_tool_call(
            "search_workspace_items", {"query": "launch plan", "kind": "task"}
        )
        added_open_comment = open_comment_episode.execute_tool_call(
            "add_workspace_comment",
            {"task_id": "task-launch-plan-001", "comment": "Status: ready for review."},
        )
        repeated_open_comment = open_comment_episode.execute_tool_call(
            "add_workspace_comment",
            {
                "task_id": "task-launch-plan-001",
                "comment": "Status: follow-up review is ready.",
            },
        )
        invalid_comment_episode = run.open_episode(open_comment, frozen)
        invalid_comment_episode.execute_tool_call(
            "search_workspace_items", {"query": "launch plan", "kind": "task"}
        )
        invalid_comment = invalid_comment_episode.execute_tool_call(
            "add_workspace_comment",
            {"task_id": "task-launch-plan-001", "comment": "No."},
        )
        exact_comment_episode = run.open_episode(exact_recovery_comment, frozen)
        exact_comment_episode.execute_tool_call(
            "search_workspace_items", {"query": "research notes (stale)", "kind": "task"}
        )
        exact_comment_episode.execute_tool_call(
            "search_workspace_items", {"query": "research notes", "kind": "task"}
        )
        wrong_exact_comment = exact_comment_episode.execute_tool_call(
            "add_workspace_comment",
            {
                "task_id": "task-research-notes-002",
                "comment": "Status: ready for review.",
            },
        )

        self.assertEqual(ungrounded_task.result_type, "unauthorized_mutation")
        self.assertEqual(ungrounded_task.error_code, "mutation_condition_not_observed")
        self.assertEqual(created_task.result_type, "state_change")
        assert isinstance(created_task.change, dict)
        self.assertEqual(created_task.change["project_id"], "project-alpha-001")
        self.assertEqual(created_task.change["title"], "Prepare Alpha Launch retrospective")
        self.assertEqual(added_open_comment.result_type, "state_change")
        self.assertEqual(
            added_open_comment.change,
            {
                "comment_id": added_open_comment.change["comment_id"],
                "task_id": "task-launch-plan-001",
                "comment": "Status: ready for review.",
            },
        )
        self.assertEqual(repeated_open_comment.result_type, "unauthorized_mutation")
        self.assertEqual(repeated_open_comment.error_code, "unintended_state_change")
        self.assertEqual(invalid_comment.result_type, "unauthorized_mutation")
        self.assertEqual(invalid_comment.error_code, "unsupported_comment")
        self.assertEqual(wrong_exact_comment.result_type, "unauthorized_mutation")
        self.assertEqual(wrong_exact_comment.error_code, "comment_not_authorized")

    def test_comment_assessment_requires_grounded_response_and_intended_state_only(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        task = _compiled_task(
            run,
            _slot_for(
                run.slots(100),
                action="add_workspace_comment",
                query="launch plan",
                route="direct",
            ),
            {
                "action": "add_workspace_comment",
                "comment_constraint": "open",
                "condition": "after_item_match",
                "route": "direct",
                "task_kind": "task",
                "task_query": "launch plan",
            },
        )
        episode = run.open_episode(task, run.freeze_initial_state())
        episode.execute_tool_call(
            "search_workspace_items", {"query": "launch plan", "kind": "task"}
        )
        added = episode.execute_tool_call(
            "add_workspace_comment",
            {"task_id": "task-launch-plan-001", "comment": "Status: ready for review."},
        )
        assert isinstance(added.change, dict)
        trace = ExecutionTrace(
            mutation_authorization="authorized",
            events=(
                EpisodeEvent(
                    event_type="action",
                    tool_name="search_workspace_items",
                    arguments={"query": "launch plan", "kind": "task"},
                ),
                EpisodeEvent(
                    event_type="observation",
                    tool_name="search_workspace_items",
                    observation={
                        "item_id": "task-launch-plan-001",
                        "kind": "task",
                        "summary": "Finalize launch plan",
                    },
                ),
                EpisodeEvent(
                    event_type="action",
                    tool_name="add_workspace_comment",
                    arguments={
                        "task_id": "task-launch-plan-001",
                        "comment": "Status: ready for review.",
                    },
                ),
                EpisodeEvent(
                    event_type="state_change",
                    tool_name="add_workspace_comment",
                    change=added.change,
                ),
                EpisodeEvent(
                    event_type="final_response",
                    content=(
                        "I added Status: ready for review. to the launch plan task."
                    ),
                ),
            ),
        )
        ungrounded_trace = trace.model_copy(
            update={
                "events": (
                    *trace.events[:-1],
                    EpisodeEvent(event_type="final_response", content="The comment is ready."),
                )
            }
        )

        assessment = run.open_episode(task, run.freeze_initial_state()).assess(trace)
        ungrounded = run.open_episode(task, run.freeze_initial_state()).assess(
            ungrounded_trace
        )

        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.structural_key, "workspace_tasks.comment.direct")
        self.assertIsNotNone(assessment.state_change_evidence)
        self.assertFalse(ungrounded.passed)
        self.assertIn("final_response_not_grounded", ungrounded.reason_codes)

    def test_open_task_title_uses_a_domain_predicate_without_hidden_exact_content(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        task = _compiled_task(
            run,
            _slot_for(
                run.slots(100),
                action="create_workspace_task",
                query="beta research",
                route="verify",
            ),
            {
                "action": "create_workspace_task",
                "condition": "after_item_match",
                "due_label": "later",
                "priority": "medium",
                "project_kind": "project",
                "project_query": "beta research",
                "route": "verify",
                "task_constraint": "open",
            },
        )
        episode = run.open_episode(task, run.freeze_initial_state())
        episode.execute_tool_call(
            "search_workspace_items", {"query": "beta research", "kind": "project"}
        )
        accepted = episode.execute_tool_call(
            "create_workspace_task",
            {
                "project_id": "project-beta-002",
                "title": "Prepare review agenda",
                "priority": "medium",
                "due_label": "later",
            },
        )
        repeated = episode.execute_tool_call(
            "create_workspace_task",
            {
                "project_id": "project-beta-002",
                "title": "Review alternate agenda",
                "priority": "medium",
                "due_label": "later",
            },
        )
        invalid_episode = run.open_episode(task, run.freeze_initial_state())
        invalid_episode.execute_tool_call(
            "search_workspace_items", {"query": "beta research", "kind": "project"}
        )
        rejected = invalid_episode.execute_tool_call(
            "create_workspace_task",
            {
                "project_id": "project-beta-002",
                "title": "No.",
                "priority": "medium",
                "due_label": "later",
            },
        )

        self.assertIn("concise planning task", task.public_task.instruction)
        self.assertNotIn("Prepare Beta Research review", task.public_task.instruction)
        self.assertEqual(accepted.result_type, "state_change")
        self.assertEqual(repeated.result_type, "unauthorized_mutation")
        self.assertEqual(repeated.error_code, "unintended_state_change")
        self.assertEqual(rejected.result_type, "unauthorized_mutation")
        self.assertEqual(rejected.error_code, "unsupported_task_title")

    def test_provider_mock_exercises_all_workspace_behaviors_and_replay(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        model = _WorkspaceOfflinePolicyModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="workspace-offline-behaviors",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=9,
            generation_batch_size=9,
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

        self.assertEqual(
            result.demonstration_count,
            9,
            json.dumps(
                [
                    (item["outcome"]["reason_code"], item["task"]["instruction"])
                    for item in negatives
                ],
                sort_keys=True,
            ),
        )
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(negatives, [])
        self.assertEqual(
            {item["verification"]["structural_key"] for item in demonstrations},
            {
                "workspace_tasks.search.direct",
                "workspace_tasks.search.directory",
                "workspace_tasks.search.recovery",
                "workspace_tasks.search.missing",
                "workspace_tasks.task.direct",
                "workspace_tasks.task.verified",
                "workspace_tasks.comment.direct",
                "workspace_tasks.comment.recovery",
                "workspace_tasks.comment.verified",
            },
        )
        recovery = next(
            item
            for item in demonstrations
            if item["verification"]["structural_key"]
            == "workspace_tasks.search.recovery"
        )
        self.assertEqual(recovery["events"][1]["error_code"], "item_not_found")
        self.assertTrue(replay.aligned)
        public_episode_text = json.dumps([*demonstrations, *negatives])
        for private_field in ("private_case_bytes", "expected_state", "missing_kind"):
            self.assertNotIn(private_field, public_episode_text)
        generation_context = json.dumps(
            [
                request.model_context()
                for request in model.requests
                if request.role == "task_generation"
            ]
        )
        self.assertNotIn("project-alpha-001", generation_context)
        self.assertNotIn("task-launch-plan-001", generation_context)
        assert_agent_episode_compliance(
            self,
            demonstrations=demonstrations,
            negatives=negatives,
            replay_aligned=replay.aligned,
        )

    def test_compilation_rejects_negation_unmet_conditions_private_targets_and_ambiguity(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        task_slot = _slot_for(
            run.slots(100),
            action="create_workspace_task",
            query="alpha launch",
            route="direct",
        )
        base = {
            "action": "create_workspace_task",
            "condition": "after_item_match",
            "due_label": "next_week",
            "priority": "high",
            "project_kind": "project",
            "project_query": "alpha launch",
            "route": "direct",
            "title": "Prepare Alpha Launch retrospective",
        }
        negated = run.compile(
            task_slot,
            TaskProposal(content=json.dumps({**base, "negated": True}, sort_keys=True)),
        )
        unmet_condition = run.compile(
            task_slot,
            TaskProposal(
                content=json.dumps(
                    {**base, "condition": "if_project_is_empty"}, sort_keys=True
                )
            ),
        )
        private_target = run.compile(
            task_slot,
            TaskProposal(
                content=json.dumps(
                    {**base, "project_id": "project-alpha-001"}, sort_keys=True
                )
            ),
        )
        ambiguous_adapter = WorkspaceTasksDomainAdapter(
            json.dumps(
                {
                    "projects": [
                        {"project_id": "project-alpha-001", "name": "Alpha Launch"},
                        {"project_id": "project-alpha-duplicate", "name": "Alpha Launch"},
                    ],
                    "tasks": [],
                    "documents": [],
                    "comments": [],
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        ambiguous_run = ambiguous_adapter.open_run(_workspace_configuration(ambiguous_adapter))
        ambiguous = ambiguous_run.compile(
            task_slot,
            TaskProposal(content=json.dumps(base, sort_keys=True)),
        )

        self.assertEqual(_rejection_code(negated), "negated_action")
        self.assertEqual(_rejection_code(unmet_condition), "uncheckable_condition")
        self.assertEqual(
            _rejection_code(private_target), "unsupported_private_exact_target"
        )
        self.assertEqual(_rejection_code(ambiguous), "unresolved_target_ambiguity")

    def test_unauthorized_mutation_is_rejected_before_a_state_change(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        model = _WrongWorkspaceMutationModel()
        engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
        configuration = RunConfiguration(
            run_id="workspace-unauthorized-task",
            domain_id=adapter.domain_id,
            model_id=model.model_id,
            slot_limit=5,
            generation_batch_size=5,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstrations = _read_json_lines(result.demonstrations_path)
            negatives = _read_json_lines(result.negatives_path)

        self.assertEqual(result.demonstration_count, 4)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(len(demonstrations), 4)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "unauthorized_mutation")
        self.assertEqual(negatives[0]["mutation_authorization"], "rejected")
        self.assertFalse(
            any(event["event_type"] == "state_change" for event in negatives[0]["events"])
        )
        self.assertNotIn("project-alpha-001", json.dumps(negatives[0]))
        self.assertIn("unobserved-project-id", json.dumps(negatives[0]))

    def test_local_source_is_frozen_before_model_work_and_replay_ignores_later_changes(self) -> None:
        source = {
            "projects": [{"project_id": "project-alpha-001", "name": "Alpha Launch"}],
            "tasks": [],
            "documents": [
                {
                    "document_id": "document-launch-brief-001",
                    "project_id": "project-alpha-001",
                    "title": "Launch Brief",
                    "body": "Original source content.",
                }
            ],
            "comments": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "run"
            source_path = Path(temporary_directory) / "workspace.json"
            source_path.write_text(json.dumps(source, sort_keys=True), encoding="utf-8")
            adapter = WorkspaceTasksDomainAdapter.from_local_file(source_path)
            model = _DirectWorkspaceSearchModel()
            engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
            result = engine.run(
                RunConfiguration(
                    run_id="workspace-local-source",
                    domain_id=adapter.domain_id,
                    model_id=model.model_id,
                    slot_limit=1,
                ),
                output_directory,
            )
            source["documents"][0]["title"] = "Changed after admission"
            source_path.write_text(json.dumps(source, sort_keys=True), encoding="utf-8")
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                frozen_state = ledger.initial_state()
            finally:
                ledger.close()
            replay_engine = SynthesisEngine(
                AdapterRegistry(
                    domains=(WorkspaceTasksDomainAdapter.from_local_file(source_path),),
                    models=(),
                )
            )
            replay = replay_engine.replay(result.run_directory)

        self.assertIn(b"Launch Brief", frozen_state.contents)
        self.assertNotIn(b"Changed after admission", frozen_state.contents)
        self.assertTrue(replay.aligned)

    def test_local_source_slots_cover_supported_workspace_behaviors(self) -> None:
        adapter = WorkspaceTasksDomainAdapter(
            json.dumps(
                {
                    "projects": [
                        {"project_id": "project-gamma-001", "name": "Gamma Migration"}
                    ],
                    "tasks": [
                        {
                            "task_id": "task-gamma-001",
                            "project_id": "project-gamma-001",
                            "title": "Complete migration checklist",
                        }
                    ],
                    "documents": [
                        {
                            "document_id": "document-gamma-001",
                            "project_id": "project-gamma-001",
                            "title": "Gamma Brief",
                            "body": "Migration milestones.",
                        }
                    ],
                    "comments": [],
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        run = adapter.open_run(_workspace_configuration(adapter))
        payloads = [
            json.loads(slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: "))
            for slot in run.slots(100)
        ]

        self.assertEqual(run.known_task_capacity, 9)
        self.assertTrue(run.slot_capacity(100).exhausted)
        self.assertEqual(
            {payload["action"] for payload in payloads},
            {
                "search_workspace_items",
                "create_workspace_task",
                "add_workspace_comment",
            },
        )
        self.assertTrue(
            any(
                payload.get("project_query") == "gamma migration"
                for payload in payloads
            )
        )
        self.assertTrue(
            any(
                payload.get("task_query") == "migration checklist"
                for payload in payloads
            )
        )

    def test_semantic_and_structural_examples_preserve_behavioral_meaning(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        slots = run.slots(100)
        direct = _compiled_task(
            run,
            _slot_for(
                slots,
                action="search_workspace_items",
                query="launch brief",
                route="direct",
            ),
            {
                "action": "search_workspace_items",
                "kind": "document",
                "query": "launch brief",
                "route": "direct",
            },
        )
        open_comment = _compiled_task(
            run,
            _slot_for(
                slots,
                action="add_workspace_comment",
                query="launch plan",
                route="direct",
            ),
            {
                "action": "add_workspace_comment",
                "comment_constraint": "open",
                "condition": "after_item_match",
                "route": "direct",
                "task_kind": "task",
                "task_query": "launch plan",
            },
        )
        exact_comment = _compiled_task(
            run,
            _slot_for(
                slots,
                action="add_workspace_comment",
                query="research notes",
                route="recovery",
            ),
            {
                "action": "add_workspace_comment",
                "comment": "Status: research notes is ready for review.",
                "comment_constraint": "exact",
                "condition": "after_item_match",
                "route": "recovery",
                "task_kind": "task",
                "task_query": "research notes",
            },
        )
        paraphrased = run.restore_task_case(
            public_task=direct.public_task.model_copy(
                update={"instruction": "Locate the launch brief document."}
            ),
            semantic_key=direct.semantic_key,
            private_case_bytes=direct.private_case_bytes,
        )
        repeated_trace = ExecutionTrace(
            mutation_authorization="not_applicable",
            events=(
                EpisodeEvent(
                    event_type="action",
                    tool_name="search_workspace_items",
                    arguments={"query": "launch brief", "kind": "document"},
                ),
                EpisodeEvent(
                    event_type="observation",
                    tool_name="search_workspace_items",
                    observation={
                        "item_id": "document-launch-brief-001",
                        "kind": "document",
                        "summary": "Launch Brief",
                    },
                ),
                EpisodeEvent(
                    event_type="action",
                    tool_name="search_workspace_items",
                    arguments={"query": "launch brief", "kind": "document"},
                ),
                EpisodeEvent(
                    event_type="observation",
                    tool_name="search_workspace_items",
                    observation={
                        "item_id": "document-launch-brief-001",
                        "kind": "document",
                        "summary": "Launch Brief",
                    },
                ),
                EpisodeEvent(
                    event_type="final_response",
                    content="The launch brief document is available.",
                ),
            ),
        )
        assessment = run.open_episode(direct, run.freeze_initial_state()).assess(
            repeated_trace
        )
        baseline = {
            example.expected_structural_key
            for example in adapter.reviewed_structural_examples
            if example.variation == "baseline"
        }

        self.assertEqual(direct.semantic_key, paraphrased.semantic_key)
        self.assertNotEqual(open_comment.semantic_key, exact_comment.semantic_key)
        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.structural_key, "workspace_tasks.search.direct")
        self.assertEqual(
            baseline,
            {
                "workspace_tasks.search.direct",
                "workspace_tasks.search.directory",
                "workspace_tasks.search.recovery",
                "workspace_tasks.search.missing",
                "workspace_tasks.task.direct",
                "workspace_tasks.task.verified",
                "workspace_tasks.comment.direct",
                "workspace_tasks.comment.recovery",
                "workspace_tasks.comment.verified",
            },
        )
        self.assertEqual(len(baseline), 9)
        self.assertTrue(
            all(
                example.expected_structural_key == "workspace_tasks.search.direct"
                for example in adapter.reviewed_structural_examples
                if example.variation in {"paraphrase", "entity_substitution", "padded_tool_sequence"}
            )
        )

    def test_restore_task_case_rejects_a_shape_the_compiler_never_emits(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        task = _compiled_task(
            run,
            _slot_for(
                run.slots(100),
                action="search_workspace_items",
                query="launch brief",
                route="direct",
            ),
            {
                "action": "search_workspace_items",
                "kind": "document",
                "query": "launch brief",
                "route": "direct",
            },
        )
        private_case = json.loads(task.private_case_bytes)
        private_case["route"] = "verify"
        semantic_key = "workspace_tasks:semantic:sha256:" + hashlib.sha256(
            json.dumps(private_case, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        with self.assertRaisesRegex(ValueError, "invalid private Workspace Tasks task case"):
            run.restore_task_case(
                public_task=task.public_task,
                semantic_key=semantic_key,
                private_case_bytes=json.dumps(
                    private_case, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
            )

    def test_source_admission_rejects_items_with_unknown_workspace_relationships(self) -> None:
        adapter = WorkspaceTasksDomainAdapter(
            json.dumps(
                {
                    "projects": [{"project_id": "project-alpha-001", "name": "Alpha Launch"}],
                    "tasks": [
                        {
                            "task_id": "task-orphan-001",
                            "project_id": "project-missing-001",
                            "title": "Orphan task",
                        }
                    ],
                    "documents": [],
                    "comments": [],
                },
                sort_keys=True,
            ).encode("utf-8")
        )

        with self.assertRaisesRegex(ValueError, "unknown project"):
            adapter.open_run(_workspace_configuration(adapter))

    def test_replay_rejects_a_restored_case_not_bound_to_the_frozen_source(self) -> None:
        adapter = WorkspaceTasksDomainAdapter.fixture()
        run = adapter.open_run(_workspace_configuration(adapter))
        task = _compiled_task(
            run,
            _slot_for(
                run.slots(100),
                action="create_workspace_task",
                query="alpha launch",
                route="direct",
            ),
            {
                "action": "create_workspace_task",
                "condition": "after_item_match",
                "due_label": "next_week",
                "priority": "high",
                "project_kind": "project",
                "project_query": "alpha launch",
                "route": "direct",
                "title": "Prepare Alpha Launch retrospective",
            },
        )
        private_case = json.loads(task.private_case_bytes)
        target = private_case["target"]
        assert isinstance(target, dict)
        target.update(
            {
                "item_id": "project-forged-001",
                "query": "forged project",
                "summary": "Forged Project",
            }
        )
        private_case["title"] = "Prepare Forged Project retrospective"
        private_case_bytes = json.dumps(
            private_case, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        forged = run.restore_task_case(
            public_task=task.public_task,
            semantic_key="workspace_tasks:semantic:sha256:"
            + hashlib.sha256(private_case_bytes).hexdigest(),
            private_case_bytes=private_case_bytes,
        )

        with self.assertRaisesRegex(ValueError, "frozen Workspace Tasks state"):
            run.open_replay_episode(forged, run.freeze_initial_state())

    def test_missing_item_slot_uses_a_selector_absent_from_the_admitted_source(self) -> None:
        adapter = WorkspaceTasksDomainAdapter(
            json.dumps(
                {
                    "projects": [
                        {"project_id": "project-alpha-001", "name": "Alpha Launch"}
                    ],
                    "tasks": [],
                    "documents": [
                        {
                            "document_id": "document-archived-roadmap-001",
                            "project_id": "project-alpha-001",
                            "title": "Archived Roadmap",
                            "body": "An existing archival plan.",
                        }
                    ],
                    "comments": [],
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        run = adapter.open_run(_workspace_configuration(adapter))
        missing_slot = _slot_for(
            run.slots(100),
            action="search_workspace_items",
            query=_missing_slot_query(run.slots(100)),
            route="missing",
        )
        proposal = json.loads(
            missing_slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: ")
        )

        self.assertNotEqual(proposal["query"], "archived roadmap")
        self.assertEqual(proposal["kind"], "document")


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _workspace_configuration(adapter: WorkspaceTasksDomainAdapter) -> RunConfiguration:
    return RunConfiguration(
        run_id="workspace-adapter-unit",
        domain_id=adapter.domain_id,
        model_id="workspace-adapter-unit-model",
        slot_limit=1,
    )


def _slot_for(
    slots: tuple[TaskSlot, ...],
    *,
    action: str,
    query: str,
    route: str,
) -> TaskSlot:
    for slot in slots:
        payload = json.loads(
            slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: ")
        )
        if (
            payload["action"] == action
            and (
                payload.get("project_query")
                or payload.get("task_query")
                or payload.get("query")
            )
            == query
            and payload["route"] == route
        ):
            return slot
    raise AssertionError(f"no slot for {action=} {query=} {route=}")


def _missing_slot_query(slots: tuple[TaskSlot, ...]) -> str:
    for slot in slots:
        payload = json.loads(
            slot.proposal_prompt.removeprefix("Return exactly this JSON proposal: ")
        )
        if payload["action"] == "search_workspace_items" and payload["route"] == "missing":
            query = payload.get("query")
            if isinstance(query, str):
                return query
    raise AssertionError("no missing-item slot")


def _compiled_task(
    run: object,
    slot: TaskSlot,
    payload: dict[str, str],
) -> object:
    compilation = run.compile(slot, TaskProposal(content=json.dumps(payload, sort_keys=True)))
    if isinstance(compilation, CompilationRejection):
        raise AssertionError(f"unexpected compilation rejection: {compilation.reason_code}")
    return compilation


def _rejection_code(compilation: object) -> str:
    if not isinstance(compilation, CompilationRejection):
        raise AssertionError("expected compilation rejection")
    return compilation.reason_code


def _public_search_arguments(instruction: str, *, stale: bool = False) -> dict[str, str]:
    match = re.search(r'workspace (project|task|document|comment) that matches "([^"]+)"', instruction)
    if match is None:
        raise AssertionError(f"no public workspace search target in {instruction!r}")
    kind, query = match.groups()
    if stale:
        stale_match = re.search(r'First search for "([^"]+)"', instruction)
        if stale_match is None:
            raise AssertionError(f"no public stale selector in {instruction!r}")
        query = stale_match.group(1)
    return {"query": query, "kind": kind}


def _last_search_observation(history: tuple[object, ...]) -> dict[str, str] | None:
    for event in reversed(history):
        if event.event_type == "observation" and event.tool_name == "search_workspace_items":
            observation = event.observation
            if isinstance(observation, dict):
                return observation
    return None


def _has_search_failure(history: tuple[object, ...]) -> bool:
    return any(
        event.event_type == "error"
        and event.tool_name == "search_workspace_items"
        and event.error_code == "item_not_found"
        for event in history
    )


def _quoted_value(instruction: str, prefix: str) -> str:
    match = re.search(rf'{re.escape(prefix)} "([^"]+)"', instruction)
    if match is None:
        raise AssertionError(f"no quoted value after {prefix!r}")
    return match.group(1)


def _task_priority(instruction: str) -> str:
    match = re.search(r"with ([a-z]+) priority", instruction)
    if match is None:
        raise AssertionError("no public task priority")
    return match.group(1)


def _task_due_label(instruction: str) -> str:
    match = re.search(r"due ([a-z_]+)", instruction)
    if match is None:
        raise AssertionError("no public task due label")
    return match.group(1)


def _open_task_title(instruction: str) -> str:
    target = _public_search_arguments(instruction)
    return f'Prepare {target["query"].title()} review'


def _public_comment(instruction: str) -> str:
    exact = re.search(r'Add exactly this comment: "([^"]+)"', instruction)
    return exact.group(1) if exact is not None else "Status: ready for review."


def _workspace_final_response(
    instruction: str,
    history: tuple[object, ...],
) -> JsonModelResponse:
    for event in reversed(history):
        if event.event_type == "state_change" and event.tool_name == "create_workspace_task":
            change = event.change
            arguments = _public_search_arguments(instruction)
            return JsonModelResponse(
                content={
                    "type": "final_response",
                    "content": (
                        f'For the {arguments["query"]} project, created {change["title"]} with '
                        f'{change["priority"]} priority due {change["due_label"]}: '
                        f'{change["task_id"]}.'
                    ),
                }
            )
        if event.event_type == "state_change" and event.tool_name == "add_workspace_comment":
            change = event.change
            arguments = _public_search_arguments(instruction)
            return JsonModelResponse(
                content={
                    "type": "final_response",
                    "content": (
                        f'For the {arguments["query"]} task, added {change["comment"]} to '
                        f'the workspace task '
                        f'{change["task_id"]}.'
                    ),
                }
            )
    arguments = _public_search_arguments(instruction)
    if _has_search_failure(history) and "make no changes" in instruction:
        content = f'The {arguments["query"]} {arguments["kind"]} was not found.'
    else:
        content = f'The {arguments["query"]} {arguments["kind"]} is available.'
    return JsonModelResponse(content={"type": "final_response", "content": content})


if __name__ == "__main__":
    unittest.main()
