from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from synthesis.execution import scripted_solution_policy
from synthesis.pipeline import run_foundation_pipeline
from synthesis.run_profiles import load_run_profile
from synthesis.tasks import CandidateTask, generate_foundation_candidates


class ResumableFakeProvider:
    def __init__(self, *, ambiguous_on_call: int | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.ambiguous_on_call = ambiguous_on_call

    def generate_json(self, prompt: str, *, role: str):
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL
        from synthesis.llm import LLMGenerationResult

        payload = json.loads(prompt)
        self.calls.append(
            {
                "batch_index": payload["batch_context"]["batch_index"],
                "requested_candidate_count": payload["requested_candidate_count"],
            }
        )
        if self.ambiguous_on_call == len(self.calls):
            from synthesis.llm import LLMProviderAmbiguousError

            raise LLMProviderAmbiguousError()
        count = payload["requested_candidate_count"]
        prefix = payload["batch_context"]["candidate_id_prefix"]
        task_type = payload["task_types"][0]
        answer_contract = task_type["final_answer"]
        state_contract = payload["output_contract"]["task_type_contracts"][0][
            "expected_state"
        ]
        entries = next(iter(payload["grounding_context"].values()))
        records = []
        for index in range(count):
            candidate_id = f"{prefix}task_{index:02d}"
            entry = entries[index % len(entries)]
            if answer_contract.get("value_contract") == "sentinel":
                final_answer = DERIVED_FINAL_ANSWER_SENTINEL
            else:
                final_answer = entry["observation"][answer_contract["allowed_fields"][0]]
            expected_state = []
            if state_contract["mode"] == "required":
                reference_fields = state_contract.get("reference_fields", {})
                for item in state_contract["exact_items"]:
                    expected = {}
                    for field_name in item["expected_schema"]["properties"]:
                        if field_name in reference_fields:
                            expected[field_name] = entry["observation"][
                                reference_fields[field_name]
                            ]
                        else:
                            expected[field_name] = f"{field_name}_{candidate_id}"
                    expected_state.append(
                        {
                            "check_type": item["check_type"],
                            "expected": expected,
                        }
                    )
            records.append(
                {
                    "candidate_id": candidate_id,
                    "instruction": f"Execute grounded task {candidate_id}.",
                    "task_type": task_type["task_type"],
                    "difficulty": {
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    "required_capabilities": task_type["required_capabilities"],
                    "required_tools": task_type["required_tools"],
                    "primary_tool": task_type["required_tools"][0],
                    "primary_arguments": dict(entry["primary_arguments"]),
                    "final_answer_contains": final_answer,
                    "expected_state": expected_state,
                }
            )
        return LLMGenerationResult(
            content={"task_contracts": records},
            lineage={
                "role": role,
                "provider_host": "fake.example.test",
                "model": "fake-model",
                "config_hash": "fake-config-hash",
                "prompt_hash": "fake-prompt-hash",
                "retry_count": 0,
                "tokens": {"total_tokens": 17},
                "raw_prompt": "RAW_PROMPT_MARKER",
                "raw_response": "RAW_RESPONSE_MARKER",
                "provider_error_body": "RAW_ERROR_BODY_MARKER",
            },
        )


class SerialOrchestrationTest(unittest.TestCase):
    PROFILE_PATH = Path("tests/fixtures/run_profiles/foundation-fixture.json")

    def _read_json(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        text = path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()] if text else []

    def _core_artifacts(self, output_dir: Path) -> dict[str, bytes]:
        return {
            name: (output_dir / name).read_bytes()
            for name in (
                "samples.jsonl",
                "rejections.jsonl",
                "manifest.json",
                "quality_report.json",
            )
        }

    def _llm_profile(self, root: Path, *, target: int) -> object:
        raw = json.loads(
            Path("tests/fixtures/run_profiles/contacts-representative-llm-100.json")
            .read_text(encoding="utf-8")
        )
        raw["schema_version"] = "run_profile_v3"
        raw.pop("mutation_admission", None)
        raw["generation"]["target_candidate_count"] = target
        profile_path = root / "llm-profile.json"
        profile_path.write_text(json.dumps(raw), encoding="utf-8")
        return load_run_profile(profile_path)

    def test_serial_job_persists_intent_and_returns_terminal_result(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_serial_job(
                Path(tmpdir),
                job_id="foundation-contract",
                run_profile=profile,
            )

            self.assertEqual(result.status, "completed")
            self.assertIsNotNone(result.pipeline_result)
            self.assertEqual(result.job_record["schema_version"], "orchestration_job_v1")
            self.assertEqual(result.job_record["status"], "completed")
            self.assertEqual(result.job_record["target_candidate_count"], 3)

            work_items = self._read_jsonl(result.work_items_path)
            self.assertEqual(len(work_items), 3)
            self.assertTrue(
                all(item["schema_version"] == "orchestration_work_item_v1" for item in work_items)
            )
            self.assertTrue(all(item["status"] == "completed" for item in work_items))
            self.assertTrue(
                all(item["result_kind"] in {"accepted", "rejected"} for item in work_items)
            )

            events = self._read_jsonl(result.events_path)
            self.assertTrue(
                all(event["schema_version"] == "orchestration_event_v1" for event in events)
            )
            intent_sequences = [
                event["sequence"]
                for event in events
                if event["event_type"] == "work_item_created"
            ]
            start_sequences = [
                event["sequence"]
                for event in events
                if event["event_type"] == "work_item_started"
            ]
            self.assertEqual(len(intent_sequences), 3)
            self.assertEqual(len(start_sequences), 3)
            self.assertLess(max(intent_sequences), min(start_sequences))
            self.assertEqual(events[-1]["event_type"], "job_completed")
            self.assertNotIn(
                str(Path(tmpdir)),
                result.job_path.read_text() + result.events_path.read_text(),
            )
            self.assertNotIn(str(Path(tmpdir)), result.work_items_path.read_text())

    def test_cancellation_drains_in_flight_work_and_resumes_to_uninterrupted_artifacts(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cancelled_dir = root / "cancelled"
            signal = CancellationSignal()
            policy_calls: list[str] = []
            started_sequences: list[int] = []

            def recording_policy(task: CandidateTask):
                policy_calls.append(task.candidate_id)
                time.sleep(0.02)
                return scripted_solution_policy(task)

            def cancel_after_first_completion(event):
                if event.get("event_type") == "work_item_started":
                    sequence_index = event.get("sequence_index")
                    if isinstance(sequence_index, int):
                        started_sequences.append(sequence_index)
                if event.get("event_type") == "work_item_completed":
                    signal.cancel()
                    signal.cancel()

            cancelled = run_serial_job(
                cancelled_dir,
                job_id="cooperative-cancel",
                run_profile=profile,
                policy_generator=recording_policy,
                interruption_hook=cancel_after_first_completion,
                cancellation_signal=signal,
                max_concurrency=2,
            )

            self.assertEqual(cancelled.status, "cancelled")
            self.assertTrue(cancelled.terminal)
            self.assertIsNotNone(cancelled.pipeline_result)
            self.assertLessEqual(len(policy_calls), 2)
            self.assertNotIn(2, started_sequences)
            self.assertTrue(
                all(
                    item["status"] in {"pending", "cancelled", "completed"}
                    for item in cancelled.work_items
                )
            )
            manifest = self._read_json(cancelled_dir / "manifest.json")
            self.assertEqual(manifest["orchestration"]["status"], "cancelled")
            self.assertEqual(manifest["orchestration"]["completeness"], "incomplete")

            events = self._read_jsonl(cancelled.events_path)
            self.assertEqual(
                [
                    event["event_type"]
                    for event in events
                    if event["event_type"] in {"job_cancelling", "job_cancelled"}
                ],
                ["job_cancelling", "job_cancelled"],
            )
            interrupted = [
                event
                for event in events
                if event["event_type"] == "work_item_interrupted"
            ]
            interrupted_items = [
                item
                for item in cancelled.work_items
                if item["status"] == "cancelled"
            ]
            self.assertEqual(len(interrupted), len(interrupted_items))
            self.assertTrue(
                all(event["payload"]["reason"] == "operator_cancelled" for event in interrupted)
            )

            resumed = run_serial_job(
                cancelled_dir,
                job_id="cooperative-cancel",
                run_profile=profile,
                policy_generator=recording_policy,
                resume=True,
            )
            self.assertEqual(resumed.status, "completed")

            uninterrupted_dir = root / "uninterrupted"
            run_serial_job(
                uninterrupted_dir,
                job_id="uninterrupted",
                run_profile=profile,
            )
            self.assertEqual(
                self._core_artifacts(cancelled_dir),
                self._core_artifacts(uninterrupted_dir),
            )

    def test_cancellation_after_last_item_still_marks_partial_artifacts(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signal = CancellationSignal()

            def cancel_after_last_completion(event):
                if (
                    event.get("event_type") == "work_item_completed"
                    and event.get("sequence_index") == 2
                ):
                    signal.cancel()

            result = run_serial_job(
                root,
                job_id="cancel-after-last-item",
                run_profile=profile,
                interruption_hook=cancel_after_last_completion,
                cancellation_signal=signal,
            )

            self.assertEqual(result.status, "cancelled")
            manifest = self._read_json(root / "manifest.json")
            self.assertEqual(manifest["orchestration"]["status"], "cancelled")
            self.assertFalse(manifest["orchestration"]["release_eligible"])

    def test_resume_recovers_a_crash_after_job_cancelling(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signal = CancellationSignal()
            signal.cancel()
            cancelled = run_serial_job(
                root,
                job_id="cancelling-crash-recovery",
                run_profile=profile,
                cancellation_signal=signal,
            )
            events = self._read_jsonl(cancelled.events_path)
            self.assertEqual(events[-1]["event_type"], "job_cancelled")
            cancelled.events_path.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events[:-1]),
                encoding="utf-8",
            )

            resumed = run_serial_job(
                root,
                job_id="cancelling-crash-recovery",
                run_profile=profile,
                resume=True,
            )
            self.assertEqual(resumed.status, "completed")
            self.assertIn(
                "job_resumed",
                [event["event_type"] for event in self._read_jsonl(resumed.events_path)],
            )

    def test_cancellation_is_observed_while_inflight_work_is_blocked(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signal = CancellationSignal()
            release = threading.Event()
            timer = threading.Timer(1.5, release.set)

            def blocking_policy(task: CandidateTask):
                self.assertTrue(release.wait(3))
                return scripted_solution_policy(task)

            def cancel_after_start(event):
                if event.get("event_type") == "work_item_started":
                    signal.cancel()

            timer.start()
            started_at = time.monotonic()
            result = run_serial_job(
                root,
                job_id="blocked-inflight-cancel",
                run_profile=profile,
                policy_generator=blocking_policy,
                interruption_hook=cancel_after_start,
                cancellation_signal=signal,
                max_concurrency=2,
            )
            elapsed = time.monotonic() - started_at
            release.set()
            timer.join(3)

            self.assertEqual(result.status, "cancelled")
            self.assertLess(elapsed, 1.45)
            self.assertTrue(
                any(
                    event["event_type"] == "work_item_interrupted"
                    for event in self._read_jsonl(result.events_path)
                )
            )

    def test_serial_and_concurrent_cancellation_resume_have_same_core_artifacts(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for name, max_concurrency in (("serial", 1), ("concurrent", 2)):
                signal = CancellationSignal()

                def cancel_after_first_completion(event, signal=signal):
                    if (
                        event.get("event_type") == "work_item_completed"
                        and event.get("sequence_index") == 0
                    ):
                        signal.cancel()

                output_dir = root / name
                cancelled = run_serial_job(
                    output_dir,
                    job_id=f"cancel-equivalence-{name}",
                    run_profile=profile,
                    interruption_hook=cancel_after_first_completion,
                    cancellation_signal=signal,
                    max_concurrency=max_concurrency,
                )
                self.assertEqual(cancelled.status, "cancelled")
                resumed = run_serial_job(
                    output_dir,
                    job_id=f"cancel-equivalence-{name}",
                    run_profile=profile,
                    resume=True,
                    max_concurrency=max_concurrency,
                )
                self.assertEqual(resumed.status, "completed")

            self.assertEqual(
                self._core_artifacts(root / "serial"),
                self._core_artifacts(root / "concurrent"),
            )

    def test_cancelled_coverage_job_retains_assignments_and_resumes(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cancelled_dir = root / "cancelled-coverage"
            signal = CancellationSignal()

            def cancel_after_first_bound(event):
                if event.get("event_type") == "coverage_candidate_bound":
                    signal.cancel()

            cancelled = run_serial_job(
                cancelled_dir,
                job_id="cancelled-coverage",
                run_profile=profile,
                provider=AssignmentAwareFakeProvider(),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 6},
                interruption_hook=cancel_after_first_bound,
                cancellation_signal=signal,
                max_concurrency=2,
            )
            self.assertEqual(cancelled.status, "cancelled")
            self.assertIsNotNone(cancelled.pipeline_result)
            partial_manifest = self._read_json(cancelled_dir / "manifest.json")
            self.assertEqual(
                partial_manifest["coverage"]["evidence_artifact"]["path"],
                "coverage_evidence.json",
            )
            evidence = self._read_json(cancelled_dir / "coverage_evidence.json")
            self.assertEqual(evidence["fulfillment"]["status"], "incomplete")

            resumed = run_serial_job(
                cancelled_dir,
                job_id="cancelled-coverage",
                run_profile=profile,
                provider=AssignmentAwareFakeProvider(),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 6},
                resume=True,
                max_concurrency=2,
            )
            self.assertEqual(resumed.status, "completed")
            self.assertIsNotNone(resumed.pipeline_result)
            assert resumed.pipeline_result is not None
            self.assertEqual(
                resumed.pipeline_result.coverage_reconciliation["status"],
                "complete",
            )

    def test_cancellation_before_candidate_binding_resumes_from_profile(self) -> None:
        from synthesis.orchestration import CancellationSignal, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cancelled_dir = root / "cancelled-before-binding"
            signal = CancellationSignal()
            signal.cancel()

            cancelled = run_serial_job(
                cancelled_dir,
                job_id="cancelled-before-binding",
                run_profile=profile,
                cancellation_signal=signal,
            )
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(cancelled.job_record["work_item_count"], 0)
            self.assertTrue(
                all(
                    event["event_type"] not in {"candidate_set_bound", "work_item_started"}
                    for event in self._read_jsonl(cancelled.events_path)
                )
            )

            resumed = run_serial_job(
                cancelled_dir,
                job_id="cancelled-before-binding",
                run_profile=profile,
                resume=True,
            )
            self.assertEqual(resumed.status, "completed")

            uninterrupted_dir = root / "uninterrupted"
            run_serial_job(
                uninterrupted_dir,
                job_id="uninterrupted",
                run_profile=profile,
            )
            self.assertEqual(
                self._core_artifacts(cancelled_dir),
                self._core_artifacts(uninterrupted_dir),
            )

    def test_cancelled_provider_job_makes_no_call_and_validates_budget_on_resume(self) -> None:
        from synthesis.orchestration import (
            CancellationSignal,
            JobConfigurationError,
            run_serial_job,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=3)
            signal = CancellationSignal()
            signal.cancel()
            provider = ResumableFakeProvider()
            constructed: list[bool] = []

            def provider_factory():
                constructed.append(True)
                return provider

            cancelled = run_serial_job(
                root / "cancelled-provider",
                job_id="cancelled-provider",
                run_profile=profile,
                provider_factory=provider_factory,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 2},
                cancellation_signal=signal,
            )
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(constructed, [])
            self.assertEqual(provider.calls, [])

            with self.assertRaises(JobConfigurationError):
                run_serial_job(
                    root / "cancelled-provider",
                    job_id="cancelled-provider",
                    run_profile=profile,
                    resume=True,
                    provider_factory=provider_factory,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                )
            self.assertEqual(constructed, [])
            self.assertEqual(provider.calls, [])

    def test_concurrency_defaults_to_one_and_invalid_values_fail_before_work(self) -> None:
        from synthesis.orchestration import JobConfigurationError, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_serial_job(
                root,
                job_id="default-concurrency",
                run_profile=profile,
            )
            self.assertEqual(result.job_record["max_concurrency"], 1)

        for invalid in (None, 0, -1, 1.5, True, "2", 10**100):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                candidate_calls: list[str] = []

                def should_not_generate(seed):
                    candidate_calls.append(seed.seed_id)
                    raise AssertionError("invalid concurrency must fail before work")

                with self.assertRaises(JobConfigurationError):
                    run_serial_job(
                        root,
                        job_id="invalid-concurrency",
                        run_profile=profile,
                        candidate_generator=should_not_generate,
                        max_concurrency=invalid,
                    )
                self.assertEqual(candidate_calls, [])
                self.assertFalse((root / "orchestration").exists())

    def test_reverse_completion_merges_by_stable_sequence_and_matches_serial(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            serial_dir = root / "serial"
            concurrent_dir = root / "concurrent"
            completion_order: list[int] = []
            second_completed = threading.Event()

            def reverse_policy(task: CandidateTask):
                if task.candidate_id == "candidate_contacts_alice":
                    self.assertTrue(second_completed.wait(5))
                else:
                    time.sleep(0.01)
                return scripted_solution_policy(task)

            def observe(event):
                if event.get("event_type") != "work_item_completed":
                    return
                sequence_index = event.get("sequence_index")
                assert isinstance(sequence_index, int)
                completion_order.append(sequence_index)
                if sequence_index == 1:
                    second_completed.set()

            serial = run_serial_job(
                serial_dir,
                job_id="serial-equivalent",
                run_profile=profile,
            )
            concurrent = run_serial_job(
                concurrent_dir,
                job_id="reverse-completion",
                run_profile=profile,
                policy_generator=reverse_policy,
                interruption_hook=observe,
                max_concurrency=2,
            )

            self.assertEqual(concurrent.status, "completed")
            self.assertEqual(completion_order[:2], [1, 0])
            self.assertEqual(
                self._core_artifacts(serial_dir),
                self._core_artifacts(concurrent_dir),
            )
            self.assertEqual(
                [item["sequence_index"] for item in concurrent.work_items],
                [0, 1, 2],
            )

    def test_configured_bound_limits_candidate_pickup_and_resume_keeps_original_bound(self) -> None:
        from synthesis.orchestration import (
            JobConfigurationError,
            JobInterruption,
            run_serial_job,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        active = 0
        observed_max = 0
        active_lock = threading.Lock()
        interrupted = False

        def bounded_policy(task: CandidateTask):
            nonlocal active, observed_max
            with active_lock:
                active += 1
                observed_max = max(observed_max, active)
            try:
                time.sleep(0.02)
                return scripted_solution_policy(task)
            finally:
                with active_lock:
                    active -= 1

        def interrupt_once(event):
            nonlocal interrupted
            if event.get("event_type") == "work_item_completed" and not interrupted:
                interrupted = True
                raise JobInterruption("bounded-resume")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="bounded-resume",
                    run_profile=profile,
                    policy_generator=bounded_policy,
                    interruption_hook=interrupt_once,
                    max_concurrency=2,
                )

            with self.assertRaises(JobConfigurationError):
                run_serial_job(
                    root,
                    job_id="bounded-resume",
                    run_profile=profile,
                    policy_generator=bounded_policy,
                    resume=True,
                    max_concurrency=3,
                )

            resumed = run_serial_job(
                root,
                job_id="bounded-resume",
                run_profile=profile,
                policy_generator=bounded_policy,
                resume=True,
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed.max_concurrency, 2)
            self.assertLessEqual(observed_max, 2)
            self.assertGreaterEqual(observed_max, 2)
            self.assertEqual(
                [item["sequence_index"] for item in resumed.work_items],
                [0, 1, 2],
            )

    def test_concurrent_duplicate_admission_matches_serial_order(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)

        def duplicate_candidates(seed):
            candidates = generate_foundation_candidates(seed)
            return [
                candidates[0],
                replace(candidates[0], candidate_id="candidate_contacts_alice_copy"),
                candidates[2],
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            serial_dir = root / "serial-duplicates"
            concurrent_dir = root / "concurrent-duplicates"
            run_serial_job(
                serial_dir,
                job_id="serial-duplicates",
                run_profile=profile,
                candidate_generator=duplicate_candidates,
            )
            concurrent = run_serial_job(
                concurrent_dir,
                job_id="concurrent-duplicates",
                run_profile=profile,
                candidate_generator=duplicate_candidates,
                max_concurrency=2,
            )

            self.assertEqual(concurrent.status, "completed")
            self.assertEqual(
                self._core_artifacts(serial_dir),
                self._core_artifacts(concurrent_dir),
            )
            rejections = self._read_jsonl(concurrent_dir / "rejections.jsonl")
            duplicate_rejections = [
                rejection
                for rejection in rejections
                if rejection.get("cause") == "quality_duplicate"
            ]
            self.assertEqual(
                [rejection["candidate_id"] for rejection in duplicate_rejections],
                ["candidate_contacts_alice_copy"],
            )

    def test_interrupted_concurrent_job_resumes_only_pending_work(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        policy_calls: list[str] = []
        policy_lock = threading.Lock()
        interrupted = False

        def recording_policy(task: CandidateTask):
            with policy_lock:
                policy_calls.append(task.candidate_id)
            time.sleep(0.01)
            return scripted_solution_policy(task)

        def interrupt_after_one_completion(event):
            nonlocal interrupted
            if event.get("event_type") == "work_item_completed" and not interrupted:
                interrupted = True
                raise JobInterruption("concurrent-interruption")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="concurrent-interruption",
                    run_profile=profile,
                    policy_generator=recording_policy,
                    interruption_hook=interrupt_after_one_completion,
                    max_concurrency=2,
                )

            resumed = run_serial_job(
                root,
                job_id="concurrent-interruption",
                run_profile=profile,
                policy_generator=recording_policy,
                resume=True,
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed.max_concurrency, 2)
            self.assertEqual(
                sorted(policy_calls),
                sorted(
                    item["candidate_id"]
                    for item in resumed.work_items
                    if item["candidate_id"] != "candidate_contacts_alice_copy"
                ),
            )
            self.assertEqual(len(policy_calls), len(set(policy_calls)))
            self.assertEqual(
                len(
                    [
                        event
                        for event in self._read_jsonl(resumed.events_path)
                        if event["event_type"] == "work_item_completed"
                    ]
                ),
                3,
            )

    def test_concurrent_coverage_matches_serial_core_artifacts(self) -> None:
        from synthesis.orchestration import run_serial_job

        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        active = 0
        observed_max = 0
        active_lock = threading.Lock()

        class BoundedCoverageProvider(AssignmentAwareFakeProvider):
            def generate_json(self, prompt: str, *, role: str):
                nonlocal active, observed_max
                with active_lock:
                    active += 1
                    observed_max = max(observed_max, active)
                try:
                    time.sleep(0.02)
                    return super().generate_json(prompt, role=role)
                finally:
                    with active_lock:
                        active -= 1

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            serial_dir = root / "serial-coverage"
            concurrent_dir = root / "concurrent-coverage"
            concurrent_provider = BoundedCoverageProvider()
            serial = run_serial_job(
                serial_dir,
                job_id="serial-coverage",
                run_profile=profile,
                provider=AssignmentAwareFakeProvider(),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
                max_concurrency=1,
            )
            concurrent = run_serial_job(
                concurrent_dir,
                job_id="concurrent-coverage",
                run_profile=profile,
                provider=concurrent_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
                max_concurrency=2,
            )

            self.assertEqual(serial.status, "completed")
            self.assertEqual(concurrent.status, "completed")
            self.assertLessEqual(observed_max, 2)
            self.assertGreaterEqual(observed_max, 2)
            artifact_names = (
                "samples.jsonl",
                "rejections.jsonl",
                "manifest.json",
                "quality_report.json",
                "coverage_plan.json",
                "coverage_evidence.json",
            )
            self.assertEqual(
                {
                    name: (serial_dir / name).read_bytes()
                    for name in artifact_names
                },
                {
                    name: (concurrent_dir / name).read_bytes()
                    for name in artifact_names
                },
            )
            self.assertEqual(
                concurrent.pipeline_result.coverage_reconciliation,
                serial.pipeline_result.coverage_reconciliation,
            )

    def test_interrupted_concurrent_coverage_resumes_with_cumulative_budget(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job

        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        interruption_lock = threading.Lock()
        interrupted = False

        def interrupt_once(event):
            nonlocal interrupted
            if event.get("event_type") != "provider_attempt_issued":
                return
            with interruption_lock:
                if interrupted:
                    return
                interrupted = True
            raise JobInterruption("concurrent-coverage-interruption")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="concurrent-coverage-resume",
                    run_profile=profile,
                    provider=AssignmentAwareFakeProvider(),
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 6},
                    interruption_hook=interrupt_once,
                    max_concurrency=2,
                )

            resumed = run_serial_job(
                root,
                job_id="concurrent-coverage-resume",
                run_profile=profile,
                provider=AssignmentAwareFakeProvider(),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 6},
                interruption_hook=interrupt_once,
                resume=True,
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed.max_concurrency, 2)
            self.assertLessEqual(
                resumed.provider_usage["issued_logical_calls"],
                6,
            )
            completed_events = [
                event
                for event in self._read_jsonl(resumed.events_path)
                if event["event_type"] == "work_item_completed"
            ]
            self.assertEqual(
                len({event["work_item_id"] for event in completed_events}),
                len(resumed.work_items),
            )

    def test_provider_checkpoint_resume_only_calls_remaining_generation_batch(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=7)
            interrupted_provider = ResumableFakeProvider()

            def interrupt_after_first_checkpoint(event):
                if (
                    event.get("event_type") == "provider_contract_checkpointed"
                    and event.get("batch_index") == 1
                ):
                    raise JobInterruption("provider-checkpoint")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="provider-checkpoint",
                    run_profile=profile,
                    provider=interrupted_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                    interruption_hook=interrupt_after_first_checkpoint,
                )

            self.assertEqual(
                [call["batch_index"] for call in interrupted_provider.calls],
                [1],
            )
            state_dir = root / "orchestration" / "provider-checkpoint"
            events = self._read_jsonl(state_dir / "events.jsonl")
            checkpoints = [
                event
                for event in events
                if event["event_type"] == "provider_contract_checkpointed"
            ]
            self.assertEqual(len(checkpoints), 1)
            self.assertNotIn("raw_prompt", json.dumps(events).lower())
            self.assertNotIn("raw_response", json.dumps(events).lower())

            resumed_provider = ResumableFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="provider-checkpoint",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 2},
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(
                [call["batch_index"] for call in resumed_provider.calls],
                [2],
            )
            self.assertEqual(resumed.job_record["work_item_count"], 7)
            events = self._read_jsonl(resumed.events_path)
            self.assertEqual(
                len(
                    [
                        event
                        for event in events
                        if event["event_type"] == "provider_contract_checkpointed"
                    ]
                ),
                2,
            )
            for path in root.rglob("*"):
                if path.is_file():
                    serialized = path.read_bytes()
                    for marker in (
                        b"RAW_PROMPT_MARKER",
                        b"RAW_RESPONSE_MARKER",
                        b"RAW_ERROR_BODY_MARKER",
                    ):
                        self.assertNotIn(marker, serialized)

            uninterrupted_root = root / "uninterrupted"
            uninterrupted_root.mkdir()
            uninterrupted_profile = self._llm_profile(uninterrupted_root, target=7)
            uninterrupted = run_serial_job(
                uninterrupted_root,
                job_id="provider-checkpoint-full",
                run_profile=uninterrupted_profile,
                provider=ResumableFakeProvider(),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 2},
            )
            self.assertEqual(uninterrupted.status, "completed")
            self.assertEqual(self._core_artifacts(root), self._core_artifacts(uninterrupted_root))

    def test_provider_phase_interruptions_resume_from_the_earliest_incomplete_phase(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job

        phases = {
            "before-provider": "provider_attempt_intent",
            "during-candidate": "work_item_started",
            "after-terminal-outcome": "work_item_completed",
        }
        for phase, event_type in phases.items():
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                profile = self._llm_profile(root, target=3)
                first_provider = ResumableFakeProvider()
                seen = 0

                def interrupt(event):
                    nonlocal seen
                    if event.get("event_type") != event_type:
                        return
                    seen += 1
                    if seen == 1:
                        raise JobInterruption(phase)

                with self.assertRaises(JobInterruption):
                    run_serial_job(
                        root,
                        job_id=f"provider-{phase}",
                        run_profile=profile,
                        provider=first_provider,
                        provider_alias="fake-provider",
                        model_alias="fake-model",
                        authorization_limits={"logical_call_budget": 2},
                        interruption_hook=interrupt,
                    )

                resumed_provider = ResumableFakeProvider()
                resumed = run_serial_job(
                    root,
                    job_id=f"provider-{phase}",
                    run_profile=profile,
                    resume=True,
                    provider=resumed_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                )
                self.assertEqual(resumed.status, "completed")
                self.assertEqual(
                    len(resumed_provider.calls),
                    1 if phase == "before-provider" else 0,
                )
                self.assertEqual(len(resumed.work_items), 3)
                self.assertEqual(
                    len(
                        {
                            item["candidate_id"] for item in resumed.work_items
                        }
                    ),
                    3,
                )

    def test_unresolved_issued_provider_attempt_is_recovered_as_ambiguous(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=3)
            first_provider = ResumableFakeProvider()

            def interrupt_after_issue(event):
                if event.get("event_type") == "provider_attempt_issued":
                    raise JobInterruption("provider-issued")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="provider-issued-recovery",
                    run_profile=profile,
                    provider=first_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                    interruption_hook=interrupt_after_issue,
                )

            self.assertEqual(first_provider.calls, [])
            resumed_provider = ResumableFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="provider-issued-recovery",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 2},
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed_provider.calls), 1)
            self.assertEqual(resumed.provider_usage["issued_logical_calls"], 2)
            self.assertEqual(resumed.provider_usage["ambiguous_attempts"], 1)
            events = self._read_jsonl(
                root / "orchestration" / "provider-issued-recovery" / "events.jsonl"
            )
            self.assertEqual(
                len(
                    [
                        event
                        for event in events
                        if event["event_type"] == "provider_attempt_ambiguous"
                    ]
                ),
                1,
            )

    def test_ambiguous_provider_attempt_is_explicit_and_resumes_with_cumulative_budget(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.orchestration import run_serial_job

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=3)
            lost_response_provider = ResumableFakeProvider(ambiguous_on_call=1)

            with self.assertRaises(LLMProviderError) as raised:
                run_serial_job(
                    root,
                    job_id="provider-ambiguity",
                    run_profile=profile,
                    provider=lost_response_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                )
            self.assertTrue(raised.exception.ambiguous)

            state_dir = root / "orchestration" / "provider-ambiguity"
            events = self._read_jsonl(state_dir / "events.jsonl")
            ambiguous = [
                event
                for event in events
                if event["event_type"] == "provider_attempt_ambiguous"
            ]
            self.assertEqual(len(ambiguous), 1)
            self.assertEqual(
                json.loads((state_dir / "provider_usage.json").read_text())[
                    "ambiguous_attempts"
                ],
                1,
            )

            resumed_provider = ResumableFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="provider-ambiguity",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 2},
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed_provider.calls), 1)
            self.assertEqual(resumed.provider_usage["issued_logical_calls"], 2)
            self.assertEqual(resumed.provider_usage["ambiguous_attempts"], 1)

    def test_budget_exhaustion_stops_before_a_second_provider_action(self) -> None:
        from synthesis.orchestration import (
            JobInterruption,
            LogicalCallBudgetExceeded,
            run_serial_job,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=7)

            def interrupt_after_first_checkpoint(event):
                if (
                    event.get("event_type") == "provider_contract_checkpointed"
                    and event.get("batch_index") == 1
                ):
                    raise JobInterruption("budget")

            first_provider = ResumableFakeProvider()
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="provider-budget",
                    run_profile=profile,
                    provider=first_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 1},
                    interruption_hook=interrupt_after_first_checkpoint,
                )

            second_provider = ResumableFakeProvider()
            with self.assertRaises(LogicalCallBudgetExceeded):
                run_serial_job(
                    root,
                    job_id="provider-budget",
                    run_profile=profile,
                    resume=True,
                    provider=second_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 1},
                )
            self.assertEqual(second_provider.calls, [])
            events = self._read_jsonl(
                root / "orchestration" / "provider-budget" / "events.jsonl"
            )
            self.assertEqual(
                len(
                    [
                        event
                        for event in events
                        if event["event_type"] == "provider_attempt_issued"
                    ]
                ),
                1,
            )

    def test_provider_alias_mismatch_is_rejected_before_lazy_provider_construction(self) -> None:
        from synthesis.orchestration import JobConfigurationError, JobInterruption, run_serial_job

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = self._llm_profile(root, target=3)

            def interrupt_on_intent(event):
                if event.get("event_type") == "provider_attempt_intent":
                    raise JobInterruption("alias")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="provider-alias",
                    run_profile=profile,
                    provider=ResumableFakeProvider(),
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                    interruption_hook=interrupt_on_intent,
                )

            constructed = []

            def factory():
                constructed.append(True)
                return ResumableFakeProvider()

            with self.assertRaises(JobConfigurationError):
                run_serial_job(
                    root,
                    job_id="provider-alias",
                    run_profile=profile,
                    resume=True,
                    provider_factory=factory,
                    provider_alias="different-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 2},
                )
            self.assertEqual(constructed, [])

    def test_coverage_job_persists_the_initial_wave_before_provider_work(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import JobInterruption, run_serial_job

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            provider = AssignmentAwareFakeProvider()

            def interrupt_after_wave_intent(event):
                if event.get("event_type") == "coverage_wave_issued":
                    raise JobInterruption("coverage-initial-wave")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="coverage-initial-wave",
                    run_profile=profile,
                    provider=provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                    interruption_hook=interrupt_after_wave_intent,
                )

            self.assertEqual(provider.payloads, [])
            state_dir = root / "orchestration" / "coverage-initial-wave"
            work_items = self._read_jsonl(state_dir / "work_items.jsonl")
            self.assertEqual(len(work_items), 2)
            self.assertEqual(
                [item["coverage_wave"] for item in work_items],
                [1, 1],
            )
            self.assertEqual(
                [
                    item["coverage_assignment"]["assignment_ordinal"]
                    for item in work_items
                ],
                [0, 1],
            )
            self.assertTrue(
                all(
                    item["coverage_assignment"]["plan_hash"].startswith("sha256:")
                    for item in work_items
                )
            )

            resumed_provider = AssignmentAwareFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="coverage-initial-wave",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed_provider.payloads), 2)
            self.assertEqual(
                [
                    payload["coverage_assignment"]["assignment_ordinal"]
                    for payload in resumed_provider.payloads
                ],
                [0, 1],
            )
            self.assertTrue(
                all(item["status"] == "completed" for item in resumed.work_items)
            )

    def test_coverage_backfill_resume_reconciles_from_terminal_outcomes(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import JobInterruption, run_serial_job
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            interrupted_provider = AssignmentAwareFakeProvider(
                mismatch_first_assignment=True
            )
            seen_backfill_wave = False

            def interrupt_on_backfill(event):
                nonlocal seen_backfill_wave
                if event.get("event_type") == "coverage_wave_issued":
                    if event.get("coverage_wave") == 2:
                        seen_backfill_wave = True
                        raise JobInterruption("coverage-backfill")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="coverage-backfill",
                    run_profile=profile,
                    provider=interrupted_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                    interruption_hook=interrupt_on_backfill,
                )

            self.assertTrue(seen_backfill_wave)
            self.assertEqual(len(interrupted_provider.payloads), 2)
            state_dir = root / "orchestration" / "coverage-backfill"
            partial_items = self._read_jsonl(state_dir / "work_items.jsonl")
            self.assertEqual(
                [item["status"] for item in partial_items],
                ["completed", "completed", "pending"],
            )
            self.assertEqual(
                [item["result_kind"] for item in partial_items[:2]],
                ["rejected", "accepted"],
            )

            resumed_provider = AssignmentAwareFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="coverage-backfill",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed_provider.payloads), 1)
            self.assertEqual(
                resumed_provider.payloads[0]["coverage_assignment"]["assignment_ordinal"],
                2,
            )
            assert resumed.pipeline_result is not None
            assert resumed.pipeline_result.coverage_reconciliation is not None
            self.assertEqual(
                resumed.pipeline_result.coverage_reconciliation["status"],
                "complete",
            )

            sync_dir = root / "sync"
            sync_provider = AssignmentAwareFakeProvider(
                mismatch_first_assignment=True
            )
            sync = run_foundation_pipeline(
                sync_dir,
                dataset_version=profile.dataset_version,
                coverage_scheduler_factory=(
                    build_coverage_assignment_scheduler_factory(sync_provider)
                ),
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
                run_profile=profile,
            )
            self.assertEqual(
                self._core_artifacts(root),
                self._core_artifacts(sync_dir),
            )
            self.assertEqual(
                resumed.pipeline_result.coverage_reconciliation,
                sync.coverage_reconciliation,
            )

    def test_coverage_resume_applies_terminal_rejections_before_backfill(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import JobInterruption, run_serial_job
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            saw_backfill_wave = False

            def policy_generator_factory():
                rejected_first_followup = False

                def policy_generator(candidate):
                    nonlocal rejected_first_followup
                    policy = scripted_solution_policy(candidate)
                    if (
                        candidate.constraints["task_type"] == "contact_followup"
                        and not rejected_first_followup
                    ):
                        rejected_first_followup = True
                        return replace(
                            policy,
                            final_response_template="No matching email was found.",
                        )
                    return policy

                return policy_generator

            policy_generator = policy_generator_factory()

            def interrupt_on_backfill(event):
                nonlocal saw_backfill_wave
                if event.get("event_type") == "coverage_wave_issued":
                    if event.get("coverage_wave") == 2:
                        saw_backfill_wave = True
                        raise JobInterruption("coverage-terminal-rejection-backfill")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="coverage-terminal-rejection-backfill",
                    run_profile=profile,
                    provider=AssignmentAwareFakeProvider(),
                    policy_generator=policy_generator,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                    interruption_hook=interrupt_on_backfill,
                )

            self.assertTrue(saw_backfill_wave)
            partial_items = self._read_jsonl(
                root
                / "orchestration"
                / "coverage-terminal-rejection-backfill"
                / "work_items.jsonl"
            )
            self.assertTrue(
                any(
                    item["status"] == "completed"
                    and item["result_kind"] == "rejected"
                    for item in partial_items
                )
            )

            resumed = run_serial_job(
                root,
                job_id="coverage-terminal-rejection-backfill",
                run_profile=profile,
                resume=True,
                provider=AssignmentAwareFakeProvider(),
                policy_generator=policy_generator,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
            )

            sync_dir = root / "sync"
            sync = run_foundation_pipeline(
                sync_dir,
                dataset_version=profile.dataset_version,
                coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                    AssignmentAwareFakeProvider()
                ),
                policy_generator=policy_generator_factory(),
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
                run_profile=profile,
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(self._core_artifacts(root), self._core_artifacts(sync_dir))
            assert resumed.pipeline_result is not None
            self.assertEqual(
                resumed.pipeline_result.coverage_reconciliation,
                sync.coverage_reconciliation,
            )

    def test_journal_sanitizer_allows_only_semantic_authorization_metadata(self) -> None:
        from synthesis.orchestration import (
            JobConfigurationError,
            _assert_safe_orchestration_value,
        )

        _assert_safe_orchestration_value(
            {
                "mutation_admission": {
                    "contract_versions": {
                        "authorization": "mutation_authorization_record_v1"
                    },
                    "hashes": {
                        "authorization": "sha256:" + "a" * 64,
                    },
                }
            }
        )
        for value in (
            {"authorization": "opaque-token"},
            {"nested": {"authorization": {"token": "opaque-token"}}},
            {
                "mutation_admission": {
                    "hashes": {"authorization": "opaque-token"}
                }
            },
        ):
            with self.assertRaises(JobConfigurationError):
                _assert_safe_orchestration_value(value)

    def test_coverage_attempt_ceiling_leaves_incomplete_diagnostic_evidence(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-backfill.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_serial_job(
                Path(tmpdir),
                job_id="coverage-attempt-ceiling",
                run_profile=profile,
                provider=AssignmentAwareFakeProvider(
                    duplicate_followup_instruction=True
                ),
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 5},
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.job_record["work_item_count"], 5)
            assert result.pipeline_result is not None
            assert result.pipeline_result.coverage_reconciliation is not None
            self.assertEqual(
                result.pipeline_result.coverage_reconciliation["status"],
                "incomplete",
            )
            assert result.pipeline_result.coverage_evidence_path is not None
            evidence = self._read_json(result.pipeline_result.coverage_evidence_path)
            self.assertEqual(evidence["fulfillment"]["status"], "incomplete")
            self.assertIn(
                "attempt_ceiling_exhausted",
                evidence["fulfillment"]["reasons"],
            )

    def test_coverage_resume_after_terminal_outcome_does_not_repeat_generation(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import JobInterruption, run_serial_job

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_provider = AssignmentAwareFakeProvider()
            seen_completion = False

            def interrupt_after_first_completion(event):
                nonlocal seen_completion
                if (
                    event.get("event_type") == "work_item_completed"
                    and not seen_completion
                ):
                    seen_completion = True
                    raise JobInterruption("coverage-terminal-outcome")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="coverage-terminal-outcome",
                    run_profile=profile,
                    provider=first_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                    interruption_hook=interrupt_after_first_completion,
                )

            self.assertEqual(len(first_provider.payloads), 2)
            resumed_provider = AssignmentAwareFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="coverage-terminal-outcome",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed_provider.payloads, [])
            self.assertEqual(
                resumed.provider_usage["issued_logical_calls"],
                2,
            )

    def test_coverage_checkpoint_resume_reuses_validated_assignment_contract(self) -> None:
        from tests.test_coverage_assignment_pipeline import AssignmentAwareFakeProvider

        from synthesis.orchestration import JobInterruption, run_serial_job

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_provider = AssignmentAwareFakeProvider()

            def interrupt_after_checkpoint(event):
                if event.get("event_type") == "provider_contract_checkpointed":
                    raise JobInterruption("coverage-contract-checkpoint")

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="coverage-contract-checkpoint",
                    run_profile=profile,
                    provider=first_provider,
                    provider_alias="fake-provider",
                    model_alias="fake-model",
                    authorization_limits={"logical_call_budget": 3},
                    interruption_hook=interrupt_after_checkpoint,
                )

            self.assertEqual(len(first_provider.payloads), 1)
            resumed_provider = AssignmentAwareFakeProvider()
            resumed = run_serial_job(
                root,
                job_id="coverage-contract-checkpoint",
                run_profile=profile,
                resume=True,
                provider=resumed_provider,
                provider_alias="fake-provider",
                model_alias="fake-model",
                authorization_limits={"logical_call_budget": 3},
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed_provider.payloads), 1)
            self.assertEqual(
                resumed_provider.payloads[0]["coverage_assignment"][
                    "assignment_ordinal"
                ],
                1,
            )
            self.assertEqual(resumed.provider_usage["issued_logical_calls"], 2)

    def test_interrupted_serial_job_resumes_without_reprocessing_completed_work(self) -> None:
        from synthesis.orchestration import (
            JobConfigurationError,
            JobInterruption,
            run_serial_job,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        policy_calls: list[str] = []

        def recording_policy(task: CandidateTask):
            policy_calls.append(task.candidate_id)
            return scripted_solution_policy(task)

        def alternate_policy(task: CandidateTask):
            return scripted_solution_policy(task)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="foundation-resume",
                    run_profile=profile,
                    policy_generator=recording_policy,
                    candidate_generator=generate_foundation_candidates,
                    interrupt_after=1,
                )

            state_dir = root / "orchestration" / "foundation-resume"
            with (state_dir / "events.jsonl").open("ab") as handle:
                handle.write(b'{"schema_version":"orchestration_event_v1"')
            interrupted_items = self._read_jsonl(state_dir / "work_items.jsonl")
            self.assertEqual(
                [item["status"] for item in interrupted_items],
                ["completed", "pending", "pending"],
            )
            self.assertEqual(len(policy_calls), 1)
            with self.assertRaises(JobConfigurationError):
                run_serial_job(
                    root,
                    job_id="foundation-resume",
                    run_profile=profile,
                    policy_generator=alternate_policy,
                    resume=True,
                )
            self.assertEqual(len(policy_calls), 1)

            resumed = run_serial_job(
                root,
                job_id="foundation-resume",
                run_profile=profile,
                policy_generator=recording_policy,
                resume=True,
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(policy_calls), 3)

            events = self._read_jsonl(resumed.events_path)
            starts = [
                event["work_item_id"]
                for event in events
                if event["event_type"] == "work_item_started"
            ]
            self.assertEqual(len(starts), 3)
            self.assertEqual(len(starts), len(set(starts)))
            self.assertTrue(
                any(event["event_type"] == "job_resumed" for event in events)
            )
            self.assertTrue(
                any(event["event_type"] == "journal_tail_recovered" for event in events)
            )

            sync_dir = root / "sync-equivalent"
            run_foundation_pipeline(
                sync_dir,
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
                policy_generator=scripted_solution_policy,
            )
            self.assertEqual(
                self._core_artifacts(root),
                self._core_artifacts(sync_dir),
            )

            idempotent_calls = len(policy_calls)
            completed_again = run_serial_job(
                root,
                job_id="foundation-resume",
                run_profile=profile,
                policy_generator=recording_policy,
                resume=True,
            )
            self.assertEqual(completed_again.status, "completed")
            self.assertEqual(len(policy_calls), idempotent_calls)

    def test_complete_malformed_final_event_is_not_treated_as_a_truncated_append(self) -> None:
        from synthesis.orchestration import (
            JobInterruption,
            JournalCorruptionError,
            run_serial_job,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="malformed-final-event",
                    run_profile=profile,
                    interrupt_after=1,
                )
            events_path = root / "orchestration" / "malformed-final-event" / "events.jsonl"
            with events_path.open("ab") as handle:
                handle.write(b'{"not_an_event": true}\n')

            with self.assertRaises(JournalCorruptionError):
                run_serial_job(
                    root,
                    job_id="malformed-final-event",
                    run_profile=profile,
                    resume=True,
                )

    def test_completed_serial_job_matches_synchronous_core_artifacts(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sync_dir = root / "sync"
            async_dir = root / "serial"
            sync_result = run_foundation_pipeline(
                sync_dir,
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
            )
            serial_result = run_serial_job(
                async_dir,
                job_id="foundation-equivalence",
                run_profile=profile,
            )

            self.assertEqual(serial_result.status, "completed")
            self.assertEqual(
                self._core_artifacts(sync_dir),
                self._core_artifacts(async_dir),
            )
            self.assertEqual(
                serial_result.pipeline_result.accepted_count,
                sync_result.accepted_count,
            )
            self.assertEqual(
                serial_result.pipeline_result.rejected_count,
                sync_result.rejected_count,
            )

    def test_deterministic_scale_probe_binds_the_validated_candidate_target(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_serial_job(
                Path(tmpdir),
                job_id="scale-probe-contract",
                run_profile=profile,
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.job_record["target_candidate_count"], 25)
            self.assertEqual(len(result.work_items), 25)
            self.assertEqual(result.pipeline_result.accepted_count, 14)
            self.assertEqual(result.pipeline_result.rejected_count, 11)

    def test_schema_rejected_candidate_still_has_a_durable_work_item_outcome(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)

        def invalid_candidate_generator(seed):
            return [replace(generate_foundation_candidates(seed)[0], candidate_id="")]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_serial_job(
                Path(tmpdir),
                job_id="schema-rejection",
                run_profile=profile,
                candidate_generator=invalid_candidate_generator,
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.work_items[0]["result_kind"], "rejected")
            self.assertEqual(result.pipeline_result.rejected_count, 1)

    def test_default_synchronous_path_does_not_create_orchestration_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "sync-only"
            run_foundation_pipeline(output_dir)
            self.assertFalse((output_dir / "orchestration").exists())

    def test_resume_rejects_copied_output_before_candidate_processing(self) -> None:
        from synthesis.orchestration import (
            JobConfigurationError,
            JobInterruption,
            run_serial_job,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        candidate_calls: list[str] = []

        def should_not_generate(seed):
            candidate_calls.append("generated")
            raise AssertionError("resume must use durable intent before candidate generation")

        with tempfile.TemporaryDirectory() as tmpdir:
            original = Path(tmpdir) / "original"
            copied = Path(tmpdir) / "copied"
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    original,
                    job_id="output-owner",
                    run_profile=profile,
                    interrupt_after=1,
                )
            shutil.copytree(original / "orchestration", copied / "orchestration")

            with self.assertRaises(JobConfigurationError):
                run_serial_job(
                    copied,
                    job_id="output-owner",
                    run_profile=profile,
                    resume=True,
                    candidate_generator=should_not_generate,
                )
            self.assertEqual(candidate_calls, [])

    def test_resume_rejects_snapshot_corruption_before_candidate_processing(self) -> None:
        from synthesis.orchestration import (
            JobInterruption,
            JournalCorruptionError,
            run_serial_job,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        policy_calls: list[str] = []

        def recording_policy(task: CandidateTask):
            policy_calls.append(task.candidate_id)
            return scripted_solution_policy(task)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="snapshot-corruption",
                    run_profile=profile,
                    policy_generator=recording_policy,
                    interrupt_after=1,
                )
            job_path = root / "orchestration" / "snapshot-corruption" / "job.json"
            job = self._read_json(job_path)
            assert isinstance(job, dict)
            job["status"] = "corrupted_status"
            job_path.write_text(json.dumps(job, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(JournalCorruptionError):
                run_serial_job(
                    root,
                    job_id="snapshot-corruption",
                    run_profile=profile,
                    policy_generator=recording_policy,
                    resume=True,
                )
            self.assertEqual(len(policy_calls), 1)

    def test_live_job_lock_rejects_second_writer_without_changing_journal(self) -> None:
        from synthesis.orchestration import JobLockError, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        started = threading.Event()
        release = threading.Event()
        thread_errors: list[BaseException] = []

        def block_before_candidate_processing(item):
            started.set()
            self.assertTrue(release.wait(5))

        def run_first_writer(root: Path) -> None:
            try:
                run_serial_job(
                    root,
                    job_id="exclusive-writer",
                    run_profile=profile,
                    interruption_hook=block_before_candidate_processing,
                )
            except BaseException as exc:  # pragma: no cover - assertion below reports it
                thread_errors.append(exc)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worker = threading.Thread(target=run_first_writer, args=(root,))
            worker.start()
            self.assertTrue(started.wait(5))
            events_path = root / "orchestration" / "exclusive-writer" / "events.jsonl"
            before = events_path.read_bytes()

            with self.assertRaises(JobLockError):
                run_serial_job(
                    root,
                    job_id="exclusive-writer",
                    run_profile=profile,
                    resume=True,
                )
            self.assertEqual(events_path.read_bytes(), before)

            release.set()
            worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(thread_errors, [])

    def test_stale_lock_requires_explicit_recovery_and_validates_state(self) -> None:
        from synthesis.orchestration import (
            JobInterruption,
            JournalCorruptionError,
            StaleJobLockError,
            JobLockError,
            run_serial_job,
            serial_job_lock_path,
        )

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="stale-lock",
                    run_profile=profile,
                    interrupt_after=1,
                )
            lock_path = serial_job_lock_path(root, "stale-lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "schema_version": "orchestration_lock_v1",
                        "pid": 999999999,
                        "token": "stale-token",
                        "acquired_at": "2026-08-02T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            events_path = root / "orchestration" / "stale-lock" / "events.jsonl"
            before = events_path.read_bytes()

            with self.assertRaises(StaleJobLockError):
                run_serial_job(
                    root,
                    job_id="stale-lock",
                    run_profile=profile,
                    resume=True,
                )
            self.assertEqual(events_path.read_bytes(), before)

            # An explicit recovery still fails closed if the durable journal is bad.
            events_path.write_bytes(before[:-1] + b"not-json\n")
            with self.assertRaises((JournalCorruptionError, JobLockError)):
                run_serial_job(
                    root,
                    job_id="stale-lock",
                    run_profile=profile,
                    resume=True,
                    recover_stale_lock=True,
                )

    def test_explicit_stale_lock_recovery_resumes_valid_state_and_records_marker(self) -> None:
        from synthesis.orchestration import JobInterruption, run_serial_job, serial_job_lock_path

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="recoverable-stale-lock",
                    run_profile=profile,
                    interrupt_after=1,
                )
            serial_job_lock_path(root, "recoverable-stale-lock").write_text(
                json.dumps(
                    {
                        "schema_version": "orchestration_lock_v1",
                        "pid": 999999999,
                        "token": "stale-token",
                        "acquired_at": "2026-08-02T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_serial_job(
                root,
                job_id="recoverable-stale-lock",
                run_profile=profile,
                resume=True,
                recover_stale_lock=True,
            )
            events = self._read_jsonl(result.events_path)
            self.assertEqual(result.status, "completed")
            self.assertTrue(
                any(event["event_type"] == "job_lock_recovered" for event in events)
            )

    def test_duplicate_and_mid_journal_corruption_fail_closed(self) -> None:
        from synthesis.orchestration import JobInterruption, JournalCorruptionError, run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="duplicate-event",
                    run_profile=profile,
                    interrupt_after=1,
                )
            duplicate_events = root / "orchestration" / "duplicate-event" / "events.jsonl"
            duplicate_events.write_bytes(
                duplicate_events.read_bytes()
                + duplicate_events.read_bytes().splitlines(keepends=True)[-1]
            )
            with self.assertRaises(JournalCorruptionError):
                run_serial_job(
                    root,
                    job_id="duplicate-event",
                    run_profile=profile,
                    resume=True,
                )

            with self.assertRaises(JobInterruption):
                run_serial_job(
                    root,
                    job_id="mid-journal-corruption",
                    run_profile=profile,
                    interrupt_after=1,
                )
            mid_journal = root / "orchestration" / "mid-journal-corruption" / "events.jsonl"
            lines = mid_journal.read_bytes().splitlines(keepends=True)
            lines[2] = b"not-json\n"
            mid_journal.write_bytes(b"".join(lines))
            with self.assertRaises(JournalCorruptionError):
                run_serial_job(
                    root,
                    job_id="mid-journal-corruption",
                    run_profile=profile,
                    resume=True,
                )

    def test_normalized_configuration_identity_has_no_path_or_credential_material(self) -> None:
        from synthesis.orchestration import run_serial_job

        profile = load_run_profile(self.PROFILE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_serial_job(
                root,
                job_id="normalized-identity",
                run_profile=profile,
                authorization_limits={"logical_call_budget": 3},
            )
            serialized = result.job_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("api_key", serialized.lower())
            self.assertEqual(
                result.job_record["authorization_limits"],
                {"logical_call_budget": 3},
            )
            identity = result.job_record["configuration_identity"]
            assert isinstance(identity, dict)
            self.assertEqual(identity["domain"], "contacts")
            self.assertEqual(identity["generation"]["mode"], "foundation_fixture")
            self.assertEqual(identity["authorization_limits"], {"logical_call_budget": 3})

    def test_work_item_validator_rejects_impossible_lifecycle_shape(self) -> None:
        from synthesis.orchestration import validate_work_item_record

        record = {
            "schema_version": "orchestration_work_item_v1",
            "job_id": "invalid-shape",
            "item_id": "invalid-shape:work:000000",
            "sequence_index": 0,
            "candidate_id": "candidate-0",
            "status": "pending",
            "candidate": {
                "schema_version": "orchestration_invalid_candidate_v1",
                "candidate_id": "candidate-0",
            },
            "task_contract": None,
            "attempt_count": 0,
            "created_at": "2026-08-02T00:00:00Z",
            "started_at": "2026-08-02T00:00:01Z",
            "completed_at": None,
            "result_kind": None,
            "outcome": None,
        }
        with self.assertRaises(ValueError):
            validate_work_item_record(record)
