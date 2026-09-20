from __future__ import annotations

import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from agent_synthesis import (
    AdapterRegistry,
    AssessmentCheck,
    CancellationSignal,
    CompiledTask,
    EpisodeAssessment,
    FrozenInitialState,
    FrozenInputError,
    JsonModelResponse,
    PublicTask,
    RunConfiguration,
    RunLockedError,
    SynthesisEngine,
    TaskProposal,
    TaskSlot,
    ToolDefinition,
)
from agent_synthesis.ledger import PrivateLedger


@dataclass(frozen=True)
class _ResumeCase:
    public_task: PublicTask
    source_value: str
    slot_id: str


class _ResumeDomain:
    domain_id = "resume_scale_test_domain"
    domain_version = "resume_scale_test_domain_v1"

    def __init__(
        self,
        *,
        slot_count: int = 1,
        known_capacity: bool = True,
        duplicate_semantic_keys: bool = False,
        cancel_during_first_restore: CancellationSignal | None = None,
    ) -> None:
        self.source_value = "original source"
        self.slot_count = slot_count
        self.known_capacity = known_capacity
        self.duplicate_semantic_keys = duplicate_semantic_keys
        self.cancel_during_first_restore = cancel_during_first_restore
        self.open_run_calls = 0
        self.resume_sources: list[str] = []
        self.last_run: _ResumeDomainRun | None = None

    def open_run(self, configuration: RunConfiguration) -> "_ResumeDomainRun":
        del configuration
        self.open_run_calls += 1
        run = _ResumeDomainRun(
            self.source_value,
            slot_count=self.slot_count,
            known_capacity=self.known_capacity,
            duplicate_semantic_keys=self.duplicate_semantic_keys,
            cancel_during_first_restore=self.cancel_during_first_restore,
        )
        self.last_run = run
        return run

    def open_run_from_frozen_state(
        self,
        configuration: RunConfiguration,
        frozen_initial_state: FrozenInitialState,
    ) -> "_ResumeDomainRun":
        del configuration
        source_value = json.loads(frozen_initial_state.contents)["source_value"]
        self.resume_sources.append(source_value)
        run = _ResumeDomainRun(
            source_value,
            slot_count=self.slot_count,
            known_capacity=self.known_capacity,
            duplicate_semantic_keys=self.duplicate_semantic_keys,
            cancel_during_first_restore=self.cancel_during_first_restore,
        )
        self.last_run = run
        return run


class _ResumeDomainRun:
    def __init__(
        self,
        source_value: str,
        *,
        slot_count: int,
        known_capacity: bool,
        duplicate_semantic_keys: bool,
        cancel_during_first_restore: CancellationSignal | None,
    ) -> None:
        self._source_value = source_value
        self._slot_count = slot_count
        self._known_capacity = known_capacity
        self._duplicate_semantic_keys = duplicate_semantic_keys
        self._cancel_during_first_restore = cancel_during_first_restore
        self.restore_calls: list[str] = []

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        slots = tuple(
            TaskSlot(
                slot_id=f"resume-slot-{index:03d}",
                proposal_prompt="Return the fixed test task.",
            )
            for index in range(1, self._slot_count + 1)
        )
        return slots[:limit]

    @property
    def known_task_capacity(self) -> int:
        if not self._known_capacity:
            raise AttributeError("capacity is intentionally unknown")
        return self._slot_count

    def freeze_initial_state(self) -> FrozenInitialState:
        contents = json.dumps({"source_value": self._source_value}, sort_keys=True).encode()
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(contents).hexdigest(),
            contents=contents,
        )

    def compile(self, slot: TaskSlot, proposal: TaskProposal) -> CompiledTask:
        assert slot.slot_id.startswith("resume-slot-")
        assert proposal.content == "fixed task"
        task = PublicTask(
            instruction=f"Confirm the frozen source value for {slot.slot_id}.",
            tools=(
                ToolDefinition(
                    name="read_source",
                    description="Read the frozen source value.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": {}},
                ),
            ),
        )
        return CompiledTask(
            public_task=task,
            semantic_key=(
                f"resume:{self._source_value}:duplicate"
                if self._duplicate_semantic_keys
                else f"resume:{self._source_value}:{slot.slot_id}"
            ),
            private_case_bytes=json.dumps(
                {"source_value": self._source_value, "slot_id": slot.slot_id}
            ).encode(),
            domain_case=_ResumeCase(task, self._source_value, slot.slot_id),
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        source_value = json.loads(private_case_bytes)["source_value"]
        slot_id = json.loads(private_case_bytes)["slot_id"]
        self.restore_calls.append(slot_id)
        if slot_id == "resume-slot-001" and self._cancel_during_first_restore is not None:
            self._cancel_during_first_restore.cancel()
        expected_semantic_key = (
            f"resume:{source_value}:duplicate"
            if self._duplicate_semantic_keys
            else f"resume:{source_value}:{slot_id}"
        )
        assert semantic_key == expected_semantic_key
        return CompiledTask(
            public_task=public_task,
            semantic_key=semantic_key,
            private_case_bytes=private_case_bytes,
            domain_case=_ResumeCase(public_task, source_value, slot_id),
        )

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_ResumeEpisode":
        assert isinstance(task.domain_case, _ResumeCase)
        assert json.loads(frozen_initial_state.contents)["source_value"] == task.domain_case.source_value
        return _ResumeEpisode()

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_ResumeEpisode":
        return self.open_episode(task, frozen_initial_state)


class _ResumeEpisode:
    def execute_tool_call(self, tool_name: str, arguments: dict[str, object]) -> object:
        raise AssertionError(f"unexpected tool call: {tool_name} {arguments}")

    def assess(self, trace: object) -> EpisodeAssessment:
        del trace
        return EpisodeAssessment(
            passed=True,
            checks=(AssessmentCheck(name="source_confirmed", passed=True),),
            reason_codes=(),
            coverage_tags=("resume",),
            structural_key="resume.final",
        )


class _FinalResponseModel:
    model_id = "resume_scale_test_model"
    model_version = "resume_scale_test_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {"slot_id": slot.slot_id, "content": "fixed task"}
                        for slot in request.slots
                    ]
                }
            )
        return JsonModelResponse(content={"type": "final_response", "content": "Done."})


class _CancellingFinalResponseModel(_FinalResponseModel):
    def __init__(self, signal: CancellationSignal) -> None:
        super().__init__()
        self._signal = signal
        self._agent_calls = 0

    def complete(self, request: object) -> JsonModelResponse:
        response = super().complete(request)
        if request.role == "agent":
            self._agent_calls += 1
            if self._agent_calls == 1:
                self._signal.cancel()
        return response


class _DelayedFinalResponseModel(_FinalResponseModel):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._active_agent_calls = 0
        self.max_active_agent_calls = 0

    def complete(self, request: object) -> JsonModelResponse:
        if request.role != "agent":
            return super().complete(request)
        with self._lock:
            self._active_agent_calls += 1
            self.max_active_agent_calls = max(
                self.max_active_agent_calls,
                self._active_agent_calls,
            )
        try:
            task_instruction = request.task.instruction
            if task_instruction.endswith("001."):
                time.sleep(0.05)
            else:
                time.sleep(0.005)
            return super().complete(request)
        finally:
            with self._lock:
                self._active_agent_calls -= 1


class _EarlyRejectionModel(_DelayedFinalResponseModel):
    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "agent" and request.task.instruction.endswith("001."):
            self.requests.append(request)
            return JsonModelResponse(content={"type": "unsupported", "content": "bad"})
        return super().complete(request)


class _BlockingFinalResponseModel(_FinalResponseModel):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "task_generation":
            self.started.set()
            self.release.wait(timeout=5)
        return super().complete(request)


class AgentFirstResumeAndScaleConfigurationTest(unittest.TestCase):
    def test_concurrency_defaults_to_four_and_is_bounded(self) -> None:
        configuration = RunConfiguration(
            run_id="resume-scale-config",
            domain_id="resume_scale_test_domain",
            model_id="resume_scale_test_model",
            slot_limit=4,
            accepted_target=2,
        )

        self.assertEqual(configuration.max_concurrency, 4)
        self.assertEqual(configuration.accepted_target, 2)

        for invalid in (0, 17):
            with self.subTest(max_concurrency=invalid):
                with self.assertRaises(ValidationError):
                    RunConfiguration(
                        run_id="resume-scale-config",
                        domain_id="resume_scale_test_domain",
                        model_id="resume_scale_test_model",
                        slot_limit=4,
                        max_concurrency=invalid,
                    )

    def test_accepted_target_cannot_exceed_the_attempt_ceiling(self) -> None:
        with self.assertRaises(ValidationError):
            RunConfiguration(
                run_id="impossible-target",
                domain_id="resume_scale_test_domain",
                model_id="resume_scale_test_model",
                slot_limit=2,
                accepted_target=3,
            )

    def test_attempt_limit_aliases_normalize_to_the_stable_slot_limit(self) -> None:
        configuration = RunConfiguration(
            run_id="attempt-alias",
            domain_id="resume_scale_test_domain",
            model_id="resume_scale_test_model",
            task_attempt_limit=4,
        )

        self.assertEqual(configuration.slot_limit, 4)
        self.assertEqual(configuration.attempt_limit, 4)
        self.assertNotIn("task_attempt_limit", configuration.model_dump(mode="json"))


class AgentFirstResumeAndScaleEngineTest(unittest.TestCase):
    def test_resume_uses_the_saved_case_and_frozen_snapshot_after_a_crash(self) -> None:
        domain = _ResumeDomain()
        first_model = _FinalResponseModel()
        configuration = RunConfiguration(
            run_id="resume-saved-case",
            domain_id=domain.domain_id,
            model_id=first_model.model_id,
            slot_limit=1,
            max_concurrency=1,
        )

        def crash_after_case(phase: str) -> None:
            if phase == "after_task_case_persistence":
                raise RuntimeError("injected crash")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            first_engine = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(first_model,))
            )
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                first_engine.run(
                    configuration,
                    output_directory,
                    failure_injector=crash_after_case,
                )

            ledger = PrivateLedger.open(output_directory / ".private" / "ledger.sqlite3")
            try:
                self.assertEqual(len(ledger.task_cases()), 1)
                self.assertEqual(ledger.terminal_outcomes(), ())
            finally:
                ledger.close()
            self.assertTrue((output_directory / ".private" / "frozen_state.json").exists())

            domain.source_value = "mutated source"
            resumed_model = _FinalResponseModel()
            resumed = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(resumed_model,))
            ).resume(configuration, output_directory)

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed.demonstration_count, 1)
            self.assertEqual([request.role for request in resumed_model.requests], ["agent"])
            self.assertEqual(domain.resume_sources, ["original source"])

    def test_crash_after_request_dispatch_keeps_unknown_charge_across_resume(self) -> None:
        domain = _ResumeDomain()
        first_model = _FinalResponseModel()
        configuration = RunConfiguration(
            run_id="resume-unknown-request",
            domain_id=domain.domain_id,
            model_id=first_model.model_id,
            slot_limit=1,
            max_concurrency=1,
        )

        def crash_after_dispatch(phase: str) -> None:
            if phase == "after_request_dispatch":
                raise RuntimeError("injected dispatch crash")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            first_engine = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(first_model,))
            )
            with self.assertRaisesRegex(RuntimeError, "injected dispatch crash"):
                first_engine.run(
                    configuration,
                    output_directory,
                    failure_injector=crash_after_dispatch,
                )

            ledger = PrivateLedger.open(output_directory / ".private" / "ledger.sqlite3")
            try:
                initial_requests = ledger.provider_requests()
                self.assertEqual(len(initial_requests), 1)
                self.assertEqual(initial_requests[0].status, "reserved")
            finally:
                ledger.close()

            resumed_model = _FinalResponseModel()
            resumed = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(resumed_model,))
            ).resume(output_directory, configuration)

            ledger = PrivateLedger.open(resumed.private_ledger_path)
            try:
                resumed_requests = ledger.provider_requests()
                outcomes = ledger.terminal_outcomes()
            finally:
                ledger.close()
            usage = json.loads(resumed.provider_usage_path.read_text(encoding="utf-8"))

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(resumed_requests), 3)
        self.assertEqual(resumed_requests[0].status, "reserved")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(usage["total_physical_requests"], 3)
        self.assertEqual(usage["reserved_request_count"], 1)

    def test_resume_skips_a_terminal_episode_committed_before_a_crash(self) -> None:
        domain = _ResumeDomain()
        first_model = _FinalResponseModel()
        configuration = RunConfiguration(
            run_id="resume-terminal-skip",
            domain_id=domain.domain_id,
            model_id=first_model.model_id,
            slot_limit=1,
            max_concurrency=1,
        )

        def crash_after_terminal_commit(phase: str) -> None:
            if phase == "after_terminal_commit":
                raise RuntimeError("injected terminal crash")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            with self.assertRaisesRegex(RuntimeError, "injected terminal crash"):
                SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(first_model,))
                ).run(
                    configuration,
                    output_directory,
                    failure_injector=crash_after_terminal_commit,
                )

            resumed_model = _FinalResponseModel()
            resumed = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(resumed_model,))
            ).resume(configuration, output_directory)

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.demonstration_count, 1)
        self.assertEqual(resumed_model.requests, [])

    def test_every_durable_checkpoint_leaves_a_resumable_run(self) -> None:
        checkpoints = (
            "before_task_case_persistence",
            "after_task_case_persistence",
            "before_request_dispatch",
            "after_request_dispatch",
            "before_response_persistence",
            "after_response_persistence",
            "before_terminal_commit",
            "after_terminal_commit",
        )
        for index, checkpoint in enumerate(checkpoints, start=1):
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as temporary_directory:
                domain = _ResumeDomain()
                first_model = _FinalResponseModel()
                configuration = RunConfiguration(
                    run_id=f"checkpoint-{index}",
                    domain_id=domain.domain_id,
                    model_id=first_model.model_id,
                    slot_limit=1,
                    max_concurrency=1,
                )

                def crash_at(phase: str, *, target: str = checkpoint) -> None:
                    if phase == target:
                        raise RuntimeError(target)

                output_directory = Path(temporary_directory)
                with self.assertRaisesRegex(RuntimeError, checkpoint):
                    SynthesisEngine(
                        AdapterRegistry(domains=(domain,), models=(first_model,))
                    ).run(
                        configuration,
                        output_directory,
                        failure_injector=crash_at,
                    )

                resumed_model = _FinalResponseModel()
                resumed = SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(resumed_model,))
                ).resume(configuration, output_directory)
                ledger = PrivateLedger.open(resumed.private_ledger_path)
                try:
                    outcomes = ledger.terminal_outcomes()
                finally:
                    ledger.close()

                self.assertEqual(resumed.status, "completed")
                self.assertEqual(len(outcomes), 1)

    def test_multiple_consecutive_crashes_preserve_the_same_charged_slot(self) -> None:
        domain = _ResumeDomain()
        configuration = RunConfiguration(
            run_id="consecutive-crashes",
            domain_id=domain.domain_id,
            model_id=_FinalResponseModel.model_id,
            slot_limit=1,
            max_concurrency=1,
        )

        def crash_after_case(phase: str) -> None:
            if phase == "after_task_case_persistence":
                raise RuntimeError("first crash")

        def crash_after_dispatch(phase: str) -> None:
            if phase == "after_request_dispatch":
                raise RuntimeError("second crash")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            with self.assertRaisesRegex(RuntimeError, "first crash"):
                SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(_FinalResponseModel(),))
                ).run(
                    configuration,
                    output_directory,
                    failure_injector=crash_after_case,
                )
            with self.assertRaisesRegex(RuntimeError, "second crash"):
                SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(_FinalResponseModel(),))
                ).resume(
                    configuration,
                    output_directory,
                    failure_injector=crash_after_dispatch,
                )
            completed = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(_FinalResponseModel(),))
            ).resume(configuration, output_directory)
            ledger = PrivateLedger.open(completed.private_ledger_path)
            try:
                work = ledger.work_items()
                requests = ledger.provider_requests()
                outcomes = ledger.terminal_outcomes()
            finally:
                ledger.close()

        self.assertEqual(completed.status, "completed")
        self.assertEqual([item.sequence for item in work], [1])
        self.assertEqual(work[0].status, "terminal")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual([request.status for request in requests], ["completed", "reserved", "completed"])

    def test_cancellation_preserves_completed_work_and_resumes_pending_slots(self) -> None:
        domain = _ResumeDomain(slot_count=3)
        signal = CancellationSignal()
        cancelled_model = _CancellingFinalResponseModel(signal)
        configuration = RunConfiguration(
            run_id="cooperative-cancel",
            domain_id=domain.domain_id,
            model_id=cancelled_model.model_id,
            slot_limit=3,
            generation_batch_size=1,
            max_concurrency=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            cancelled = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(cancelled_model,))
            ).run(
                configuration,
                output_directory,
                cancellation_signal=signal,
            )
            ledger = PrivateLedger.open(cancelled.private_ledger_path)
            try:
                work_after_cancellation = ledger.work_items()
            finally:
                ledger.close()

            resumed_model = _FinalResponseModel()
            resumed = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(resumed_model,))
            ).resume(configuration, output_directory)

        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.partial_reason, "operator_cancelled")
        self.assertEqual(cancelled.task_attempt_count, 3)
        self.assertEqual(cancelled.terminal_outcome_count, 1)
        self.assertEqual([item.status for item in work_after_cancellation], ["terminal", "pending", "pending"])
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.demonstration_count, 3)
        self.assertEqual(
            [request.role for request in resumed_model.requests],
            ["task_generation", "agent", "task_generation", "agent"],
        )

    def test_concurrent_reverse_completion_exports_stable_sequences_and_duplicate_winner(self) -> None:
        domain = _ResumeDomain(slot_count=2)
        model = _DelayedFinalResponseModel()
        configuration = RunConfiguration(
            run_id="reverse-completion",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=2,
            generation_batch_size=2,
            max_concurrency=2,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            result = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(model,))
            ).run(configuration, output_directory)
            sequences = [
                json.loads(line)["sequence"]
                for line in (output_directory / "demonstrations.jsonl").read_text().splitlines()
            ]

        self.assertEqual(result.status, "completed")
        self.assertEqual(sequences, [1, 2])
        self.assertEqual(model.max_active_agent_calls, 2)

        duplicate_domain = _ResumeDomain(slot_count=2, duplicate_semantic_keys=True)
        duplicate_model = _DelayedFinalResponseModel()
        duplicate_configuration = RunConfiguration(
            run_id="stable-duplicate-winner",
            domain_id=duplicate_domain.domain_id,
            model_id=duplicate_model.model_id,
            slot_limit=2,
            generation_batch_size=2,
            max_concurrency=2,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            duplicate_directory = Path(temporary_directory)
            duplicate_result = SynthesisEngine(
                AdapterRegistry(domains=(duplicate_domain,), models=(duplicate_model,))
            ).run(duplicate_configuration, duplicate_directory)
            demonstrations = [
                json.loads(line)
                for line in (duplicate_directory / "demonstrations.jsonl").read_text().splitlines()
            ]
            negatives = [
                json.loads(line)
                for line in (duplicate_directory / "negatives.jsonl").read_text().splitlines()
            ]

        self.assertEqual(duplicate_result.demonstration_count, 1)
        self.assertEqual(demonstrations[0]["sequence"], 1)
        self.assertEqual(negatives[0]["sequence"], 2)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "duplicate_semantic_task")

    def test_known_impossible_target_fails_before_provider_work(self) -> None:
        domain = _ResumeDomain(slot_count=1)
        model = _FinalResponseModel()
        configuration = RunConfiguration(
            run_id="known-impossible-target",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=2,
            accepted_target=2,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(model,))
            ).run(configuration, Path(temporary_directory))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.partial_reason, "known_task_capacity_insufficient")
        self.assertEqual(model.requests, [])

    def test_target_and_capacity_shortfalls_report_distinct_bounded_reasons(self) -> None:
        cases = (
            (
                "domain-slot-exhausted",
                _ResumeDomain(slot_count=1, known_capacity=False),
                "domain_slot_exhausted",
            ),
            (
                "bounded-replacement",
                _ResumeDomain(slot_count=2, duplicate_semantic_keys=True),
                "bounded_replacement_exhausted",
            ),
            (
                "unknown-capacity",
                _ResumeDomain(
                    slot_count=2,
                    known_capacity=False,
                    duplicate_semantic_keys=True,
                ),
                "unknown_task_capacity",
            ),
        )
        for run_id, domain, expected_reason in cases:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as temporary_directory:
                model = _FinalResponseModel()
                configuration = RunConfiguration(
                    run_id=run_id,
                    domain_id=domain.domain_id,
                    model_id=model.model_id,
                    slot_limit=2,
                    accepted_target=2,
                    generation_batch_size=2,
                    max_concurrency=2,
                )
                result = SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(model,))
                ).run(configuration, Path(temporary_directory))

                self.assertEqual(result.status, "partial")
                self.assertEqual(result.partial_reason, expected_reason)

    def test_accepted_target_limits_dispatched_episodes_and_report_counts(self) -> None:
        domain = _ResumeDomain(slot_count=3)
        model = _FinalResponseModel()
        configuration = RunConfiguration(
            run_id="accepted-target",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=3,
            accepted_target=1,
            generation_batch_size=3,
            max_concurrency=3,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(model,))
            ).run(configuration, Path(temporary_directory))
            report = json.loads(result.run_report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual([request.role for request in model.requests], ["task_generation", "agent"])
        self.assertEqual(report["targets"], {"accepted_target": 1, "task_attempt_limit": 3})
        self.assertEqual(report["outcomes"]["task_attempt_count"], 3)
        self.assertEqual(report["outcomes"]["terminal_outcome_count"], 1)
        self.assertEqual(report["provider_usage"]["total_physical_requests"], 2)

    def test_in_flight_candidates_count_against_the_accepted_target(self) -> None:
        domain = _ResumeDomain(slot_count=4)
        model = _EarlyRejectionModel()
        configuration = RunConfiguration(
            run_id="in-flight-target-bound",
            domain_id=domain.domain_id,
            model_id=model.model_id,
            slot_limit=4,
            accepted_target=2,
            generation_batch_size=4,
            max_concurrency=4,
            decision_repair_limit=0,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = SynthesisEngine(
                AdapterRegistry(domains=(domain,), models=(model,))
            ).run(configuration, Path(temporary_directory))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.demonstration_count, 2)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(result.terminal_outcome_count, 3)
        agent_requests = [request for request in model.requests if request.role == "agent"]
        self.assertEqual(len(agent_requests), 3)

    def test_missing_or_corrupt_snapshot_fails_closed_before_provider_work(self) -> None:
        for replacement in (None, "not valid snapshot"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary_directory:
                domain = _ResumeDomain()
                first_model = _FinalResponseModel()
                configuration = RunConfiguration(
                    run_id="snapshot-failure",
                    domain_id=domain.domain_id,
                    model_id=first_model.model_id,
                    slot_limit=1,
                    max_concurrency=1,
                )

                def crash_after_case(phase: str) -> None:
                    if phase == "after_task_case_persistence":
                        raise RuntimeError("injected crash")

                output_directory = Path(temporary_directory)
                with self.assertRaisesRegex(RuntimeError, "injected crash"):
                    SynthesisEngine(
                        AdapterRegistry(domains=(domain,), models=(first_model,))
                    ).run(
                        configuration,
                        output_directory,
                        failure_injector=crash_after_case,
                    )
                snapshot = output_directory / ".private" / "frozen_state.json"
                if replacement is None:
                    snapshot.unlink()
                else:
                    snapshot.write_text(replacement, encoding="utf-8")

                resumed_model = _FinalResponseModel()
                with self.assertRaises(FrozenInputError):
                    SynthesisEngine(
                        AdapterRegistry(domains=(domain,), models=(resumed_model,))
                    ).resume(configuration, output_directory)
                self.assertEqual(resumed_model.requests, [])

    def test_configuration_and_domain_version_drift_fail_before_provider_work(self) -> None:
        cases = ("configuration", "domain_version")
        for drift in cases:
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary_directory:
                domain = _ResumeDomain()
                first_model = _FinalResponseModel()
                configuration = RunConfiguration(
                    run_id=f"drift-{drift}",
                    domain_id=domain.domain_id,
                    model_id=first_model.model_id,
                    slot_limit=1,
                    max_concurrency=1,
                )

                def crash_after_case(phase: str) -> None:
                    if phase == "after_task_case_persistence":
                        raise RuntimeError("injected crash")

                output_directory = Path(temporary_directory)
                with self.assertRaisesRegex(RuntimeError, "injected crash"):
                    SynthesisEngine(
                        AdapterRegistry(domains=(domain,), models=(first_model,))
                    ).run(
                        configuration,
                        output_directory,
                        failure_injector=crash_after_case,
                    )

                resumed_model = _FinalResponseModel()
                engine = SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(resumed_model,))
                )
                if drift == "configuration":
                    changed_configuration = configuration.model_copy(
                        update={"max_concurrency": 2}
                    )
                    with self.assertRaisesRegex(ValueError, "configuration"):
                        engine.resume(changed_configuration, output_directory)
                else:
                    domain.domain_version = "resume_scale_test_domain_v2"
                    with self.assertRaisesRegex(ValueError, "Domain version"):
                        engine.resume(configuration, output_directory)
                self.assertEqual(resumed_model.requests, [])

    def test_only_one_live_writer_can_own_a_run_directory(self) -> None:
        domain = _ResumeDomain()
        blocking_model = _BlockingFinalResponseModel()
        configuration = RunConfiguration(
            run_id="writer-lock",
            domain_id=domain.domain_id,
            model_id=blocking_model.model_id,
            slot_limit=1,
            max_concurrency=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            first_result: list[object] = []

            def run_first_writer() -> None:
                try:
                    first_result.append(
                        SynthesisEngine(
                            AdapterRegistry(domains=(domain,), models=(blocking_model,))
                        ).run(configuration, output_directory)
                    )
                except Exception as error:  # noqa: BLE001 - test surfaces worker errors below.
                    first_result.append(error)

            first_writer = threading.Thread(target=run_first_writer)
            first_writer.start()
            self.assertTrue(blocking_model.started.wait(timeout=2))
            with self.assertRaises(RunLockedError):
                SynthesisEngine(
                    AdapterRegistry(domains=(domain,), models=(blocking_model,))
                ).run(configuration, output_directory)
            blocking_model.release.set()
            first_writer.join(timeout=5)

        self.assertFalse(first_writer.is_alive())
        self.assertEqual(len(first_result), 1)
        self.assertFalse(isinstance(first_result[0], Exception), first_result[0])

    def test_thin_cli_resume_matches_the_library_terminal_artifacts(self) -> None:
        from agent_synthesis.cli import run_cli

        configuration = RunConfiguration(
            run_id="cli-resume-equivalence",
            domain_id=_ResumeDomain.domain_id,
            model_id=_FinalResponseModel.model_id,
            slot_limit=1,
            max_concurrency=1,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            direct_directory = root / "library"
            cli_directory = root / "cli"
            config_path = root / "configuration.json"
            config_path.write_text(
                json.dumps(configuration.model_dump(mode="json")),
                encoding="utf-8",
            )

            direct_domain = _ResumeDomain()
            direct_model = _FinalResponseModel()
            direct = SynthesisEngine(
                AdapterRegistry(domains=(direct_domain,), models=(direct_model,))
            ).run(configuration, direct_directory)

            cli_domain = _ResumeDomain()
            first_cli_model = _FinalResponseModel()

            def crash_after_case(phase: str) -> None:
                if phase == "after_task_case_persistence":
                    raise RuntimeError("injected crash")

            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                SynthesisEngine(
                    AdapterRegistry(domains=(cli_domain,), models=(first_cli_model,))
                ).run(
                    configuration,
                    cli_directory,
                    failure_injector=crash_after_case,
                )

            resumed_cli_model = _FinalResponseModel()
            stdout = io.StringIO()
            cli_result = run_cli(
                SynthesisEngine(
                    AdapterRegistry(domains=(cli_domain,), models=(resumed_cli_model,))
                ),
                [
                    "--configuration",
                    str(config_path),
                    "--output-directory",
                    str(cli_directory),
                    "--resume",
                ],
                stdout=stdout,
            )

            direct_artifacts = {
                path.name: path.read_bytes()
                for path in (
                    direct.demonstrations_path,
                    direct.negatives_path,
                    direct.provider_usage_path,
                    direct.manifest_path,
                )
            }
            cli_artifacts = {
                path.name: path.read_bytes()
                for path in (
                    cli_result.demonstrations_path,
                    cli_result.negatives_path,
                    cli_result.provider_usage_path,
                    cli_result.manifest_path,
                )
            }

        self.assertEqual(cli_result.status, "completed")
        self.assertEqual(cli_artifacts, direct_artifacts)
        self.assertIn('"status": "completed"', stdout.getvalue())

    def test_scale_benchmark_reports_engine_capacity_without_production_claims(self) -> None:
        from scripts.run_agent_first_scale_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = run_benchmark(
                output_directory=Path(temporary_directory),
                attempts=32,
                max_concurrency=4,
            )

        self.assertEqual(payload["benchmark_scope"], "test_domain_engine_capacity_only")
        self.assertEqual(payload["production_domain_capacity_claim"], "none")
        self.assertEqual(payload["task_attempt_count"], 32)
        self.assertEqual(payload["unique_accepted_count"], 32)
        self.assertEqual(payload["resume_provider_call_count"], 0)
