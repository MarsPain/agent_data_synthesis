from __future__ import annotations

import json
import tempfile
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
