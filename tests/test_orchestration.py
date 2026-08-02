from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from synthesis.execution import scripted_solution_policy
from synthesis.pipeline import run_foundation_pipeline
from synthesis.run_profiles import load_run_profile
from synthesis.tasks import CandidateTask, generate_foundation_candidates


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
