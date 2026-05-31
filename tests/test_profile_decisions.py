from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from synthesis.pipeline import run_foundation_pipeline
from synthesis.run_profiles import load_run_profile
from synthesis.tasks import generate_scale_probe_candidates


class ProfileDecisionReportTest(unittest.TestCase):
    def test_scale_probe_decision_report_defers_async_and_semantic_duplicates(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        manifest, quality_report = _scale_probe_artifacts()

        report = build_profile_decision_report(
            manifest=manifest,
            quality_report=quality_report,
            manifest_path=Path("manifest.json"),
            quality_report_path=Path("quality_report.json"),
        )

        self.assertEqual(report["schema_version"], "profile_decision_report_v1")
        self.assertEqual(report["observed"]["total_candidates"], 25)
        self.assertEqual(report["observed"]["accepted"], 14)
        self.assertEqual(report["observed"]["rejected"], 11)
        self.assertEqual(report["observed"]["exact_duplicate_count"], 3)
        self.assertEqual(report["decisions"]["async_orchestration"]["status"], "defer")
        self.assertEqual(report["decisions"]["semantic_duplicate_detection"]["status"], "defer")
        self.assertEqual(report["decisions"]["mvp_quality_floor"]["status"], "passed")

    def test_async_activates_at_candidate_threshold(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        report = build_profile_decision_report(**_report_inputs(total=100, accepted=50, rejected=50))

        decision = report["decisions"]["async_orchestration"]
        self.assertEqual(decision["status"], "activate")
        self.assertIn("total_candidates", decision["triggered_by"])

    def test_async_activates_at_runtime_threshold(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        report = build_profile_decision_report(
            **_report_inputs(total=25, accepted=14, rejected=11),
            runtime_seconds=600.0,
        )

        decision = report["decisions"]["async_orchestration"]
        self.assertEqual(decision["status"], "activate")
        self.assertIn("runtime_seconds", decision["triggered_by"])

    def test_semantic_duplicate_detection_activates_only_when_volume_and_rate_meet_thresholds(
        self,
    ) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        activated = build_profile_decision_report(
            **_report_inputs(
                total=100,
                accepted=80,
                rejected=20,
                quality_duplicates=10,
            )
        )
        deferred_low_volume = build_profile_decision_report(
            **_report_inputs(
                total=25,
                accepted=10,
                rejected=15,
                quality_duplicates=10,
            )
        )

        self.assertEqual(
            activated["decisions"]["semantic_duplicate_detection"]["status"],
            "activate",
        )
        self.assertEqual(
            deferred_low_volume["decisions"]["semantic_duplicate_detection"]["status"],
            "defer",
        )

    def test_mvp_quality_floor_fails_when_thresholds_are_missed(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        cases = (
            _report_inputs(total=10, accepted=4, rejected=6, success_rate=0.4),
            _report_inputs(total=10, accepted=4, rejected=6, executable_rate=0.7),
            _report_inputs(
                total=10,
                accepted=5,
                rejected=5,
                rejection_causes={"infrastructure_error": 1},
            ),
            _report_inputs(
                total=10,
                accepted=5,
                rejected=5,
                rejection_causes={"source_policy_rejected": 1},
            ),
        )
        for inputs in cases:
            with self.subTest(inputs=inputs):
                report = build_profile_decision_report(**inputs)

                self.assertEqual(report["decisions"]["mvp_quality_floor"]["status"], "failed")

    def test_mvp_quality_floor_is_insufficient_when_required_rate_is_missing(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        inputs = _report_inputs(total=10, accepted=5, rejected=5)
        inputs["quality_report"]["rates"].pop("success_rate")

        report = build_profile_decision_report(**inputs)

        self.assertEqual(
            report["decisions"]["mvp_quality_floor"]["status"],
            "insufficient_evidence",
        )

    def test_evaluation_passed_report_keeps_mvp_quality_floor_passed(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        report = build_profile_decision_report(
            **_report_inputs(total=10, accepted=5, rejected=5),
            evaluation_report=_evaluation_report(status="passed"),
            evaluation_report_path=Path("evaluation_report.json"),
        )

        self.assertEqual(report["evaluation"]["decision_status"], "passed")
        self.assertEqual(report["evaluation"]["heldout_pass_rate"], 0.8)
        self.assertEqual(report["evaluation"]["regression_count"], 0)
        self.assertEqual(report["decisions"]["mvp_quality_floor"]["status"], "passed")
        self.assertEqual(report["inputs"]["evaluation_report_path"], "evaluation_report.json")

    def test_evaluation_failed_report_fails_mvp_quality_floor(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        report = build_profile_decision_report(
            **_report_inputs(total=10, accepted=5, rejected=5),
            evaluation_report=_evaluation_report(status="failed", pass_rate=0.6),
            evaluation_report_path=Path("evaluation_report.json"),
        )

        self.assertEqual(report["evaluation"]["decision_status"], "failed")
        self.assertEqual(report["decisions"]["mvp_quality_floor"]["status"], "failed")
        self.assertIn(
            "held-out evaluation decision failed",
            report["decisions"]["mvp_quality_floor"]["reasons"],
        )

    def test_malformed_evaluation_report_produces_insufficient_evidence(self) -> None:
        from synthesis.profile_decisions import build_profile_decision_report

        evaluation_report = _evaluation_report(status="passed")
        evaluation_report["rates"].pop("pass_rate")

        report = build_profile_decision_report(
            **_report_inputs(total=10, accepted=5, rejected=5),
            evaluation_report=evaluation_report,
            evaluation_report_path=Path("evaluation_report.json"),
        )

        self.assertEqual(report["evaluation"]["decision_status"], "insufficient_evidence")
        self.assertEqual(
            report["decisions"]["mvp_quality_floor"]["status"],
            "insufficient_evidence",
        )

    def test_cli_writes_sanitized_profile_decision_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            inputs = _report_inputs(total=10, accepted=5, rejected=5)
            inputs["manifest"]["run_profile"]["source"] = {
                "kind": "local_contacts_json",
                "source_id": "source_profile_contacts_v1",
                "content_hash": "sha256:" + "2" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "3" * 64,
            }
            manifest_path = tmp_path / "manifest.json"
            quality_report_path = tmp_path / "quality_report.json"
            output_path = tmp_path / "decision.json"
            manifest_path.write_text(
                json.dumps(inputs["manifest"], ensure_ascii=False),
                encoding="utf-8",
            )
            quality_report_path.write_text(
                json.dumps(inputs["quality_report"], ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/profile_decision_report.py",
                    "--manifest",
                    str(manifest_path),
                    "--quality-report",
                    str(quality_report_path),
                    "--output",
                    str(output_path),
                    "--runtime-seconds",
                    "12.5",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            exported = output_path.read_text(encoding="utf-8")
            self.assertNotIn("contacts-profile.json", exported)
            self.assertNotIn("alice.zhang@example.test", exported)
            self.assertNotIn("AGENT_DATA_API_KEY", exported)
            self.assertNotIn("Authorization", exported)
            report = json.loads(exported)
            self.assertEqual(report["observed"]["runtime_seconds"], 12.5)

    def test_cli_accepts_optional_evaluation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            inputs = _report_inputs(total=10, accepted=5, rejected=5)
            manifest_path = tmp_path / "manifest.json"
            quality_report_path = tmp_path / "quality_report.json"
            evaluation_report_path = tmp_path / "evaluation_report.json"
            output_path = tmp_path / "decision.json"
            manifest_path.write_text(json.dumps(inputs["manifest"]), encoding="utf-8")
            quality_report_path.write_text(json.dumps(inputs["quality_report"]), encoding="utf-8")
            evaluation_report_path.write_text(
                json.dumps(_evaluation_report(status="passed")),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/profile_decision_report.py",
                    "--manifest",
                    str(manifest_path),
                    "--quality-report",
                    str(quality_report_path),
                    "--evaluation-report",
                    str(evaluation_report_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["inputs"]["evaluation_report_path"], "evaluation_report.json")
            self.assertEqual(report["evaluation"]["decision_status"], "passed")


def _scale_probe_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    profile = load_run_profile(Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json"))
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "foundation-scale-probe"
        run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            candidate_generator=lambda seed: generate_scale_probe_candidates(
                seed,
                profile.generation.target_candidate_count or 25,
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
        )
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        quality_report = json.loads(
            (output_dir / "quality_report.json").read_text(encoding="utf-8")
        )
    return manifest, quality_report


def _report_inputs(
    *,
    total: int,
    accepted: int,
    rejected: int,
    success_rate: float = 0.5,
    executable_rate: float = 1.0,
    quality_duplicates: int = 0,
    rejection_causes: dict[str, int] | None = None,
) -> dict[str, object]:
    causes = {"quality_duplicate": quality_duplicates} if quality_duplicates else {}
    if rejection_causes:
        causes.update(rejection_causes)
    return {
        "manifest": {
            "schema_version": "dataset_manifest_v1",
            "dataset_version": "dataset_test",
            "parent_dataset_version": None,
            "accepted_count": accepted,
            "rejected_count": rejected,
            "artifacts": {
                "samples": "samples.jsonl",
                "rejections": "rejections.jsonl",
                "quality_report": "quality_report.json",
            },
            "quality": {
                "success_rate": success_rate,
                "executable_rate": executable_rate,
            },
            "environment_versions": ["env_contacts_v1"],
            "tool_versions": ["tool_lookup_contact_email_v1"],
            "verifier_versions": ["verifier_exact_answer_v1"],
            "generator_config_hashes": ["scripted_task_generation_v1"],
            "rejection_causes": causes,
            "run_profile": {
                "schema_version": "run_profile_v1",
                "profile_id": "foundation_scale_probe_25",
                "generation_mode": "deterministic_scale_probe",
                "target_candidate_count": total,
                "config_hash": "sha256:" + "1" * 64,
                "enabled_features": [],
            },
        },
        "quality_report": {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_test",
            "counts": {
                "total": total,
                "accepted": accepted,
                "rejected": rejected,
                "executable": total,
            },
            "rates": {
                "success_rate": success_rate,
                "executable_rate": executable_rate,
            },
            "rejection_causes": causes,
            "slices": {
                "run_profile_id": {"foundation_scale_probe_25": {}},
                "generation_mode": {"deterministic_scale_probe": {}},
                "run_profile_schema_version": {"run_profile_v1": {}},
            },
        },
        "manifest_path": Path("manifest.json"),
        "quality_report_path": Path("quality_report.json"),
    }


def _evaluation_report(
    *,
    status: str,
    pass_rate: float = 0.8,
    regressed: int = 0,
) -> dict[str, object]:
    passed = int(pass_rate * 5)
    failed = 5 - passed
    return {
        "schema_version": "evaluation_report_v1",
        "dataset_version": "dataset_test",
        "suite": {
            "suite_id": "contacts_heldout_v1",
            "suite_version": "contacts_heldout_v1",
            "task_count": 5,
        },
        "profile": None,
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "parent_evaluation_report_path": None,
        },
        "counts": {
            "total": 5,
            "passed": passed,
            "failed": failed,
            "regressed": regressed,
            "improved": 0,
            "unchanged": 5 - regressed,
        },
        "rates": {"pass_rate": pass_rate},
        "capability_slices": {
            "contact_lookup": {
                "total": 5,
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
            }
        },
        "task_results": [
            {
                "task_id": f"heldout_task_{index}",
                "capability_tags": ["contact_lookup"],
                "status": "passed" if index <= passed else "failed",
                "failure_cause": None if index <= passed else "verification_failed",
            }
            for index in range(1, 6)
        ],
        "thresholds": {"mvp_min_heldout_pass_rate": 0.8, "max_regression_count": 0},
        "decision": {"status": status, "reasons": ["evaluation"], "triggered_by": []},
    }


if __name__ == "__main__":
    unittest.main()
