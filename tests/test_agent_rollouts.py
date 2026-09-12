from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import httpx

from agent_synthesis import (
    AdapterRegistry,
    AgentRequest,
    AssessmentCheck,
    CompiledTask,
    DeterministicJsonModelAdapter,
    EpisodeAssessment,
    FrozenInitialState,
    JsonModelResponse,
    ModelCallError,
    OpenAICompatibleJsonAdapter,
    PublicTask,
    RunConfiguration,
    SynthesisEngine,
    TaskGenerationRequest,
    TaskSlot,
    TokenUsage,
    ToolDefinition,
    ToolExecutionResult,
)
from agent_synthesis.ledger import PrivateLedger


@dataclass(frozen=True)
class _LookupCase:
    public_task: PublicTask
    private_oracle: str


class _TwoTurnDomain:
    domain_id = "two_turn_test_domain"
    domain_version = "two_turn_test_domain_v1"

    def __init__(self) -> None:
        self.last_run: _TwoTurnRun | None = None

    def open_run(self, configuration: RunConfiguration) -> _TwoTurnRun:
        run = _TwoTurnRun()
        self.last_run = run
        return run


class _DuplicateSlotDomain(_TwoTurnDomain):
    domain_id = "duplicate_slot_test_domain"

    def open_run(self, configuration: RunConfiguration) -> _DuplicateSlotRun:
        return _DuplicateSlotRun()


class _UnauthorizedDomain(_TwoTurnDomain):
    domain_id = "unauthorized_test_domain"

    def __init__(self) -> None:
        self.changed_state: list[str] = []

    def open_run(self, configuration: RunConfiguration) -> _UnauthorizedRun:
        return _UnauthorizedRun(self)


class _DriftingReplayDomain(_TwoTurnDomain):
    domain_id = "drifting_replay_test_domain"

    def __init__(self) -> None:
        self.replay_email = "ada@example.test"

    def open_run(self, configuration: RunConfiguration) -> _DriftingReplayRun:
        return _DriftingReplayRun(self)


class _TwoTurnRun:
    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        return (
            TaskSlot(
                slot_id="lookup-ada-001",
                proposal_prompt="Propose the public Ada lookup task.",
            ),
        )[:limit]

    def freeze_initial_state(self) -> FrozenInitialState:
        contents = b'{"contacts":{"Ada":{"email":"ada@example.test"}}}'
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(contents).hexdigest(),
            contents=contents,
        )

    def compile(self, slot: TaskSlot, proposal: object) -> CompiledTask:
        self.assert_proposal(slot, proposal)
        task = PublicTask(
            instruction="Find Ada's email address.",
            tools=(
                ToolDefinition(
                    name="lookup_email",
                    description="Look up one contact email address.",
                    input_schema={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                    output_schema={
                        "type": "object",
                        "properties": {"email": {"type": "string"}},
                        "required": ["email"],
                    },
                ),
            ),
        )
        return CompiledTask(
            public_task=task,
            semantic_key="lookup-email:ada",
            private_case_bytes=b'{"oracle":"Ada is ada@example.test"}',
            domain_case=_LookupCase(
                public_task=task,
                private_oracle="Ada is ada@example.test",
            ),
        )

    def assert_proposal(self, slot: TaskSlot, proposal: object) -> None:
        self._proposal_slot_id = slot.slot_id
        self._proposal = proposal

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> _TwoTurnEpisode:
        assert isinstance(task.domain_case, _LookupCase)
        self.execution_frozen_state = frozen_initial_state.contents
        return _TwoTurnEpisode(task.domain_case)

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        assert semantic_key == "lookup-email:ada"
        return CompiledTask(
            public_task=public_task,
            semantic_key=semantic_key,
            private_case_bytes=private_case_bytes,
            domain_case=_LookupCase(
                public_task=public_task,
                private_oracle="Ada is ada@example.test",
            ),
        )

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> _TwoTurnEpisode:
        self.replay_state = frozen_initial_state.contents
        return self.open_episode(task, frozen_initial_state)


class _DuplicateSlotRun(_TwoTurnRun):
    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        return (
            TaskSlot(
                slot_id="lookup-ada-001",
                proposal_prompt="Propose the first public Ada lookup task.",
            ),
            TaskSlot(
                slot_id="lookup-ada-002",
                proposal_prompt="Propose the second public Ada lookup task.",
            ),
        )[:limit]


class _TwoTurnEpisode:
    def __init__(self, case: _LookupCase) -> None:
        self._case = case

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        if tool_name != "lookup_email" or arguments != {"name": "Ada"}:
            return ToolExecutionResult(
                result_type="tool_failure",
                error_code="lookup_not_found",
            )
        return ToolExecutionResult(
            result_type="observation",
            observation={"email": "ada@example.test"},
        )

    def assess(self, trace: object) -> EpisodeAssessment:
        return EpisodeAssessment(
            passed=True,
            checks=(AssessmentCheck(name="email_returned", passed=True),),
            reason_codes=(),
            coverage_tags=("lookup",),
            structural_key="lookup_email",
        )


class _UnauthorizedRun(_TwoTurnRun):
    def __init__(self, domain: _UnauthorizedDomain) -> None:
        self._domain = domain

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> _UnauthorizedEpisode:
        assert isinstance(task.domain_case, _LookupCase)
        self.execution_frozen_state = frozen_initial_state.contents
        return _UnauthorizedEpisode(task.domain_case, self._domain)


class _UnauthorizedEpisode(_TwoTurnEpisode):
    def __init__(self, case: _LookupCase, domain: _UnauthorizedDomain) -> None:
        super().__init__(case)
        self._domain = domain

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            result_type="unauthorized_mutation",
            error_code="mutation_not_authorized",
        )


class _DriftingReplayRun(_TwoTurnRun):
    def __init__(self, domain: _DriftingReplayDomain) -> None:
        self._domain = domain

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> _DriftingReplayEpisode:
        assert isinstance(task.domain_case, _LookupCase)
        return _DriftingReplayEpisode(task.domain_case, self._domain.replay_email)


class _DriftingReplayEpisode(_TwoTurnEpisode):
    def __init__(self, case: _LookupCase, email: str) -> None:
        super().__init__(case)
        self._email = email

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            result_type="observation",
            observation={"email": self._email},
        )


class _ScriptedJsonAdapter:
    model_id = "scripted_json_model"
    model_version = "scripted_json_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self, responses: tuple[object, ...] | None = None) -> None:
        self.requests: list[object] = []
        self._responses = iter(
            responses
            or (
                {
                    "proposals": [
                        {
                            "slot_id": "lookup-ada-001",
                            "content": "Find Ada's email address.",
                        }
                    ]
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "final_response",
                    "content": "Ada's email is ada@example.test.",
                },
            )
        )

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, JsonModelResponse):
            return response
        assert isinstance(response, dict)
        return JsonModelResponse(content=response)


class _ReservationInspectingAdapter(_ScriptedJsonAdapter):
    def __init__(self, ledger_path: Path) -> None:
        super().__init__()
        self._ledger_path = ledger_path
        self.reservations_seen_at_dispatch: list[tuple[int, str]] = []

    def complete(self, request: object) -> JsonModelResponse:
        ledger = PrivateLedger.open(self._ledger_path)
        try:
            reservations = ledger.provider_requests()
        finally:
            ledger.close()
        self.reservations_seen_at_dispatch.append(
            (len(reservations), reservations[-1].status)
        )
        return super().complete(request)


class AgentRolloutTest(unittest.TestCase):
    def test_openai_mock_transport_and_fake_share_the_strict_json_contract(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers["authorization"]
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(_generation_response()),
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 3,
                        "total_tokens": 7,
                    },
                },
            )

        request = TaskGenerationRequest(
            slots=(
                TaskSlot(
                    slot_id="lookup-ada-001",
                    proposal_prompt="Propose the public Ada lookup task.",
                ),
            ),
            timeout_seconds=30,
            max_response_bytes=4_096,
            max_output_tokens=32,
        )
        production = OpenAICompatibleJsonAdapter(
            model_id="production_json_model",
            model_version="production_json_model_v1",
            base_url="https://provider.example.test/v1",
            api_key="secret-test-key",
            remote_model="remote-test-model",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        fake = DeterministicJsonModelAdapter(
            model_id="fake_json_model",
            model_version="fake_json_model_v1",
            responses=(_generation_response(),),
        )

        production_response = production.complete(request)
        fake_response = fake.complete(request)

        self.assertIsInstance(production_response, JsonModelResponse)
        self.assertIsInstance(fake_response, JsonModelResponse)
        self.assertEqual(production_response.content, fake_response.content)
        self.assertEqual(production_response.usage.total_tokens, 7)
        self.assertEqual(captured["authorization"], "Bearer secret-test-key")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(
            set(json.loads(captured["body"]["messages"][1]["content"])),
            {"slots"},
        )
        self.assertIn('"proposals"', captured["body"]["messages"][0]["content"])
        self.assertNotIn("secret-test-key", repr(production))
        self.assertNotIn("secret-test-key", production_response.model_dump_json())

    def test_openai_adapter_drops_raw_transport_exception_causes(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                content=b'{"raw_provider_body":"secret-test-key"}',
                request=request,
            )

        adapter = OpenAICompatibleJsonAdapter(
            model_id="production_json_model",
            model_version="production_json_model_v1",
            base_url="https://provider.example.test/v1",
            api_key="secret-test-key",
            remote_model="remote-test-model",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        request = TaskGenerationRequest(
            slots=(
                TaskSlot(
                    slot_id="lookup-ada-001",
                    proposal_prompt="Propose the public Ada lookup task.",
                ),
            ),
            timeout_seconds=30,
            max_response_bytes=4_096,
            max_output_tokens=32,
        )

        with self.assertRaises(ModelCallError) as raised:
            adapter.complete(request)

        error = raised.exception
        self.assertEqual(str(error), "provider_http_failure")
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)

    def test_openai_adapter_sends_the_agent_one_decision_contract(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"type": "final_response", "content": "Done."}
                                )
                            }
                        }
                    ]
                },
            )

        task = PublicTask(
            instruction="Find Ada's email address.",
            tools=(
                ToolDefinition(
                    name="lookup_email",
                    description="Look up one contact email address.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": {}},
                ),
            ),
        )
        request = AgentRequest(
            task=task,
            observable_history=(),
            remaining_step_budget=3,
            timeout_seconds=30,
            max_response_bytes=4_096,
            max_output_tokens=32,
        )
        adapter = OpenAICompatibleJsonAdapter(
            model_id="production_json_model",
            model_version="production_json_model_v1",
            base_url="https://provider.example.test/v1",
            api_key="secret-test-key",
            remote_model="remote-test-model",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        adapter.complete(request)

        system_prompt = captured["body"]["messages"][0]["content"]
        agent_context = json.loads(captured["body"]["messages"][1]["content"])
        self.assertIn('"tool_call"', system_prompt)
        self.assertIn('"final_response"', system_prompt)
        self.assertEqual(
            set(agent_context),
            {"task", "observable_history", "remaining_step_budget"},
        )

    def test_each_physical_request_is_reserved_in_sqlite_before_dispatch(self) -> None:
        domain = _TwoTurnDomain()
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            model = _ReservationInspectingAdapter(
                output_directory / ".private" / "ledger.sqlite3"
            )
            engine = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(model,))
            )
            configuration = RunConfiguration(
                run_id="reserved-before-dispatch",
                domain_id=domain.domain_id,
                model_id=model.model_id,
                slot_limit=1,
            )
            engine.run(configuration, output_directory)

        self.assertEqual(
            model.reservations_seen_at_dispatch,
            [(1, "reserved"), (2, "reserved"), (3, "reserved")],
        )

    def test_engine_runs_a_bounded_multi_turn_agent_episode_through_json(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter()
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-agent",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episodes = _read_json_lines(output_directory / "demonstrations.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(
            [event["event_type"] for event in episodes[0]["events"]],
            ["action", "observation", "final_response"],
        )
        self.assertEqual(episodes[0]["events"][1]["observation"], {"email": "ada@example.test"})
        self.assertEqual(
            [entry["role"] for entry in episodes[0]["lineage"]["roles"]],
            ["task_generation", "agent"],
        )
        self.assertTrue(
            all(
                response_hash.startswith("sha256:")
                for entry in episodes[0]["lineage"]["roles"]
                for response_hash in entry["response_hashes"]
            )
        )
        self.assertEqual([request.role for request in model.requests], ["task_generation", "agent", "agent"])
        agent_context = json.dumps(model.requests[1].model_dump(mode="json"))
        agent_model_context = model.requests[1].model_context()
        self.assertNotIn("private_oracle", agent_context)
        self.assertNotIn("Ada is ada@example.test", agent_context)
        self.assertIn("Find Ada's email address.", agent_context)
        self.assertIn("lookup_email", agent_context)
        self.assertIn("ada@example.test", json.dumps(model.requests[2].model_dump(mode="json")))
        self.assertEqual(
            set(agent_model_context),
            {"task", "observable_history", "remaining_step_budget"},
        )
        assert domain.last_run is not None
        self.assertEqual(
            domain.last_run.execution_frozen_state,
            b'{"contacts":{"Ada":{"email":"ada@example.test"}}}',
        )

    def test_replay_uses_the_saved_case_and_fixture_without_a_model_call(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter()
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-replay",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            engine.run(configuration, output_directory)
            requests_before_replay = len(model.requests)
            replay = engine.replay(output_directory)

        self.assertEqual(len(model.requests), requests_before_replay)
        self.assertTrue(replay.aligned)
        self.assertEqual(replay.episode_results[0].status, "aligned")
        assert domain.last_run is not None
        self.assertEqual(
            domain.last_run.replay_state,
            b'{"contacts":{"Ada":{"email":"ada@example.test"}}}',
        )

    def test_agent_recovers_from_unknown_invalid_and_ordinary_tool_failures(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter(
            (
                _generation_response(),
                {
                    "type": "tool_call",
                    "tool_name": "unknown_lookup",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": 7},
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Bea"},
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "final_response",
                    "content": "Ada's email is ada@example.test.",
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-recovery",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "demonstrations.jsonl")[0]

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(
            [event["error_code"] for event in episode["events"] if event["event_type"] == "error"],
            ["unknown_tool", "invalid_tool_arguments", "lookup_not_found"],
        )
        self.assertEqual(episode["events"][-2]["event_type"], "observation")
        self.assertEqual(episode["events"][-1]["event_type"], "final_response")

    def test_agent_repairs_one_malformed_decision_but_rejects_a_second_one(self) -> None:
        domain = _TwoTurnDomain()
        malformed = {
            "type": "tool_call",
            "tool_name": "lookup_email",
            "arguments": {"name": "Ada"},
            "reasoning": "this key is forbidden",
        }
        unsupported_type = {"type": "parallel_tool_calls", "calls": []}
        model = _ScriptedJsonAdapter(
            (_generation_response(), malformed, unsupported_type)
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-malformed",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            usage = json.loads((output_directory / "provider_usage.json").read_text())

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "malformed_agent_decision")
        self.assertEqual(
            [event["error_code"] for event in episode["events"]],
            ["malformed_agent_decision", "malformed_agent_decision"],
        )
        self.assertEqual(usage["roles"]["agent"]["repair_request_count"], 1)

    def test_agent_can_recover_once_from_malformed_json_and_finish(self) -> None:
        domain = _TwoTurnDomain()
        malformed = {"type": "final_response", "content": "done", "reasoning": "hidden"}
        model = _ScriptedJsonAdapter(
            (
                _generation_response(),
                malformed,
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "final_response",
                    "content": "Ada's email is ada@example.test.",
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="one-repair-success",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "demonstrations.jsonl")[0]

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(episode["events"][0]["error_code"], "malformed_agent_decision")
        self.assertEqual(episode["events"][-1]["event_type"], "final_response")

    def test_transport_timeouts_retain_all_three_physical_charges(self) -> None:
        domain = _TwoTurnDomain()
        timeout = ModelCallError("provider_timeout", retryable=True)
        model = _ScriptedJsonAdapter((_generation_response(), timeout, timeout, timeout))
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-timeout",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
            transport_retry_limit=2,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            usage = json.loads((output_directory / "provider_usage.json").read_text())
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                requests = ledger.provider_requests()
                allocated = ledger.allocated_slots()
            finally:
                ledger.close()

        self.assertEqual(episode["outcome"]["reason_code"], "provider_timeout")
        self.assertEqual(len(requests), 4)
        self.assertEqual(len(allocated), 1)
        self.assertEqual([request.status for request in requests[-3:]], ["failed"] * 3)
        self.assertEqual(usage["roles"]["agent"]["physical_request_count"], 3)
        self.assertEqual(usage["roles"]["agent"]["retry_count"], 2)
        self.assertEqual(usage["roles"]["agent"]["unknown_usage_count"], 3)

    def test_provider_request_and_response_token_limits_end_the_episode_boundedly(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter(
            (
                JsonModelResponse(
                    content=_generation_response(),
                    usage=TokenUsage(output_tokens=9, total_tokens=9),
                ),
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-token-bound",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
            max_output_tokens=8,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "response_tokens_exceeded")

    def test_response_byte_limit_rejects_without_exporting_the_provider_body(self) -> None:
        domain = _TwoTurnDomain()
        raw_marker = "provider-body-marker-" * 40
        model = _ScriptedJsonAdapter(
            (
                {
                    "proposals": [
                        {
                            "slot_id": "lookup-ada-001",
                            "content": raw_marker,
                        }
                    ]
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="response-byte-bound",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
            max_response_bytes=256,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            text = (output_directory / "negatives.jsonl").read_text()
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "response_bytes_exceeded")
        self.assertNotIn(raw_marker, text)

    def test_malformed_generation_still_consumes_the_persisted_slot(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter(({"not_proposals": []},))
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="malformed-generation",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                allocated = ledger.allocated_slots()
                task_cases = ledger.task_cases()
            finally:
                ledger.close()

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "generation_malformed_output")
        self.assertEqual(len(allocated), 1)
        self.assertEqual(task_cases, ())
        self.assertEqual(len(model.requests), 1)

    def test_generator_cannot_assign_provider_selected_slot_identity(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter(
            (
                {
                    "proposals": [
                        {
                            "slot_id": "provider-selected-identity",
                            "content": "Find Ada's email address.",
                        }
                    ]
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="provider-identity-rejected",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                task_cases = ledger.task_cases()
            finally:
                ledger.close()

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "generation_slot_mismatch")
        self.assertEqual(task_cases, ())

    def test_agent_request_ceiling_stops_before_a_second_dispatch(self) -> None:
        domain = _TwoTurnDomain()
        model = _ScriptedJsonAdapter(
            (
                _generation_response(),
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="two-turn-request-ceiling",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
            agent_request_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                requests = ledger.provider_requests()
            finally:
                ledger.close()

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "provider_request_budget_exhausted")
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(len(requests), 2)

    def test_step_ceiling_rejects_an_episode_without_a_final_response(self) -> None:
        domain = _TwoTurnDomain()
        tool_call = {
            "type": "tool_call",
            "tool_name": "lookup_email",
            "arguments": {"name": "Ada"},
        }
        model = _ScriptedJsonAdapter((_generation_response(), tool_call, tool_call))
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="step-ceiling",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
            step_limit=2,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["outcome"]["reason_code"], "step_budget_exhausted")
        self.assertEqual(episode["events"][-1]["error_code"], "step_budget_exhausted")
        self.assertEqual(len(model.requests), 3)

    def test_allocated_slots_are_persisted_in_one_bounded_batch_and_duplicates_stay_charged(self) -> None:
        domain = _DuplicateSlotDomain()
        model = _ScriptedJsonAdapter(
            (
                {
                    "proposals": [
                        {
                            "slot_id": "lookup-ada-001",
                            "content": "Find Ada's email address.",
                        },
                        {
                            "slot_id": "lookup-ada-002",
                            "content": "Find Ada's email address.",
                        },
                    ]
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "final_response",
                    "content": "Ada's email is ada@example.test.",
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="duplicate-slots",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=2,
            generation_batch_size=8,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            negatives = _read_json_lines(output_directory / "negatives.jsonl")
            ledger = PrivateLedger.open(result.private_ledger_path)
            try:
                allocated = ledger.allocated_slots()
                cases = ledger.task_cases()
            finally:
                ledger.close()

        self.assertEqual(len(model.requests[0].slots), 2)
        self.assertEqual([record.slot_id for record in allocated], ["lookup-ada-001", "lookup-ada-002"])
        self.assertEqual(len(cases), 2)
        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "duplicate_semantic_task")

    def test_a_later_same_semantic_slot_can_run_after_the_first_is_not_admitted(self) -> None:
        domain = _DuplicateSlotDomain()
        malformed = {"type": "parallel_tool_calls", "calls": []}
        model = _ScriptedJsonAdapter(
            (
                {
                    "proposals": [
                        {
                            "slot_id": "lookup-ada-001",
                            "content": "Find Ada's email address.",
                        },
                        {
                            "slot_id": "lookup-ada-002",
                            "content": "Find Ada's email address.",
                        },
                    ]
                },
                malformed,
                malformed,
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
                {
                    "type": "final_response",
                    "content": "Ada's email is ada@example.test.",
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="failed-duplicate-retry",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=2,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            demonstrations = _read_json_lines(output_directory / "demonstrations.jsonl")
            negatives = _read_json_lines(output_directory / "negatives.jsonl")

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(demonstrations[0]["sequence"], 2)
        self.assertEqual(negatives[0]["sequence"], 1)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "malformed_agent_decision")

    def test_unauthorized_mutation_terminates_before_any_further_model_dispatch(self) -> None:
        domain = _UnauthorizedDomain()
        model = _ScriptedJsonAdapter(
            (
                _generation_response(),
                {
                    "type": "tool_call",
                    "tool_name": "lookup_email",
                    "arguments": {"name": "Ada"},
                },
            )
        )
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="unauthorized-stop",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            result = engine.run(configuration, output_directory)
            episode = _read_json_lines(output_directory / "negatives.jsonl")[0]

        self.assertEqual(result.negative_count, 1)
        self.assertEqual(episode["mutation_authorization"], "rejected")
        self.assertEqual(episode["outcome"]["reason_code"], "unauthorized_mutation")
        self.assertEqual(domain.changed_state, [])
        self.assertEqual(len(model.requests), 2)

    def test_replay_reports_observation_drift_without_contacting_the_model(self) -> None:
        domain = _DriftingReplayDomain()
        model = _ScriptedJsonAdapter()
        engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
        configuration = RunConfiguration(
            run_id="replay-drift",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            engine.run(configuration, output_directory)
            request_count = len(model.requests)
            domain.replay_email = "drifted@example.test"
            replay = engine.replay(output_directory)
            report = json.loads(replay.report_path.read_text())

        self.assertEqual(len(model.requests), request_count)
        self.assertFalse(replay.aligned)
        self.assertEqual(replay.episode_results[0].status, "observation_drift")
        self.assertTrue(report["episodes"][0]["observation_drift"])


def _generation_response() -> dict[str, object]:
    return {
        "proposals": [
            {
                "slot_id": "lookup-ada-001",
                "content": "Find Ada's email address.",
            }
        ]
    }


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
