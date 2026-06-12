from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FoundationCliTest(unittest.TestCase):
    def test_default_output_directory_is_outside_docs(self) -> None:
        from main import parse_args

        with patch.object(sys, "argv", ["main.py"]):
            args = parse_args()

        self.assertEqual(args.output_dir, Path("artifacts/foundation"))
        self.assertFalse(args.enable_refinement)
        self.assertFalse(args.enable_branching)
        self.assertFalse(args.enable_mcp_adapter)
        self.assertFalse(args.enable_sandbox_fixture)

    def test_main_writes_requested_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"
            env = {
                **os.environ,
                "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                "AGENT_DATA_API_KEY": "secret-test-key",
                "AGENT_DATA_LLM_MODEL": "test-generator",
            }

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_test",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "manifest.json").exists(), result.stdout)
            self.assertFalse((output_dir / "dataset_release_report.json").exists())
            self.assertFalse((output_dir / "dataset_release_pack.json").exists())
            self.assertFalse((output_dir / "release_quality_audit.json").exists())
            self.assertFalse((output_dir / "dataset_release_card.md").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_test")
            self.assertNotIn("dataset_release_report", manifest["artifacts"])
            self.assertNotIn("dataset_release_pack", manifest["artifacts"])
            self.assertNotIn("release_quality_audit", manifest["artifacts"])
            self.assertNotIn("dataset_release_card", manifest["artifacts"])
            self.assertIn("accepted=2", result.stdout)
            self.assertNotIn("secret-test-key", result.stdout)

    def test_main_can_enable_deterministic_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-refinement",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_refinement_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_count"], 3)
            self.assertEqual(manifest["rejected_count"], 0)
            self.assertEqual(report["counts"]["refined_accepted"], 1)
            self.assertIn("accepted=3", result.stdout)

    def test_main_can_enable_deterministic_branching_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-branching",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_branching_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["branch_attempts"], 2)
            self.assertEqual(report["counts"]["branch_selected"], 1)
            self.assertIn("accepted=3", result.stdout)

    def test_main_can_enable_local_mcp_adapter_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-mcp-adapter",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_adapter_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            sample = json.loads((output_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()[0])
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(sample["lineage"]["adapter"][0]["adapter_id"], "contacts_local_mcp_adapter")
            self.assertIn("contacts_local_mcp_adapter", report["slices"]["adapter_id"])
            self.assertIn("accepted=2", result.stdout)

    def test_main_can_enable_sandbox_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-sandbox-fixture",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_sandbox_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "sandbox_audits.jsonl").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["sandbox_audits"], "sandbox_audits.jsonl")
            self.assertIn("accepted", report["slices"]["sandbox_admission_outcome"])
            self.assertIn("rejected", report["slices"]["sandbox_admission_outcome"])
            self.assertNotIn("def ", (output_dir / "sandbox_audits.jsonl").read_text(encoding="utf-8"))
            self.assertIn("accepted=2", result.stdout)

    def test_main_can_enable_no_network_source_governance_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-source-governance-fixture",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_source_governance_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "source_events.jsonl").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["source_events"], "source_events.jsonl")
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertIn("external", report["slices"]["source_kind"])
            self.assertIn("accepted=2", result.stdout)

    def test_network_source_requires_allowlisted_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-network-source",
                    "--source-url",
                    "https://allowed.example.test/contacts.json",
                    "--source-license-label",
                    "cc-by-4.0",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--allowed-source-host", result.stderr)

    def test_main_can_enable_mocked_network_contacts_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_fixture = Path(tmpdir) / "contacts.json"
            source_fixture.write_text(
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
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--enable-network-source",
                    "--source-url",
                    "https://allowed.example.test/contacts.json",
                    "--source-license-label",
                    "cc-by-4.0",
                    "--allowed-source-host",
                    "allowed.example.test",
                    "--mock-source-fixture",
                    str(source_fixture),
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_network_source_test",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "source_events.jsonl").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_network_source_test")
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertIn("external", report["slices"]["source_kind"])
            self.assertIn("accepted", report["slices"]["environment_source_admission"])
            self.assertNotIn("Alice Zhang", (output_dir / "source_events.jsonl").read_text(encoding="utf-8"))
            self.assertIn("accepted=2", result.stdout)

    def test_main_can_run_foundation_fixture_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-fixture.json",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_foundation_profile_v1")
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["rejected_count"], 1)
            self.assertEqual(manifest["run_profile"]["profile_id"], "foundation_fixture_profile")
            self.assertEqual(manifest["run_profile"]["generation_mode"], "foundation_fixture")
            self.assertIn("accepted=2", result.stdout)

    def test_main_dataset_version_overrides_profile_dataset_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-fixture.json",
                    "--dataset-version",
                    "dataset_cli_profile_override",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_profile_override")
            self.assertEqual(manifest["run_profile"]["profile_id"], "foundation_fixture_profile")

    def test_main_rejects_invalid_profile_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/missing.json",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("run profile", result.stderr)

    def test_main_rejects_invalid_profile_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "bad-profile.json"
            profile_path.write_text('{"schema_version": "run_profile_v3"}', encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    str(profile_path),
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("schema_version", result.stderr)

    def test_main_can_run_profile_local_contacts_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-profile-local"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-contacts.json",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "source_events.jsonl").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_profile"]["schema_version"], "run_profile_v2")
            self.assertEqual(
                manifest["run_profile"]["source"]["source_id"],
                "source_profile_contacts_v1",
            )
            self.assertEqual(manifest["run_profile"]["source"]["kind"], "local_contacts_json")
            self.assertIn("source_policy_hash", manifest["run_profile"]["source"])
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertIn("local_file", report["slices"]["source_kind"])
            self.assertIn("foundation_profile_local_contacts", report["slices"]["run_profile_id"])
            samples = [
                json.loads(line)
                for line in (output_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            rejections = [
                json.loads(line)
                for line in (output_dir / "rejections.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                all(
                    sample["lineage"]["run_profile"]["schema_version"]
                    == "run_profile_attribution_v1"
                    for sample in samples
                )
            )
            self.assertTrue(
                all(
                    rejection["details"]["run_profile"]["source"]["source_id"]
                    == "source_profile_contacts_v1"
                    for rejection in rejections
                )
            )
            exported_audit = (
                (output_dir / "manifest.json").read_text(encoding="utf-8")
                + (output_dir / "source_events.jsonl").read_text(encoding="utf-8")
                + (output_dir / "quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "rejections.jsonl").read_text(encoding="utf-8")
            )
            self.assertNotIn("contacts-profile.json", exported_audit)
            self.assertNotIn("Alice Zhang", (output_dir / "source_events.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("alice.zhang@example.test", exported_audit)
            self.assertNotIn("ben.carter@example.test", exported_audit)
            self.assertNotIn(str(Path.cwd()), exported_audit)
            self.assertNotIn("target_candidate_count", (output_dir / "samples.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("enabled_features", (output_dir / "samples.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("contacts-profile.json", (output_dir / "samples.jsonl").read_text(encoding="utf-8"))
            self.assertIn("accepted=2", result.stdout)

    def test_main_rejects_profile_local_source_conflicting_with_network_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-contacts.json",
                    "--enable-network-source",
                    "--source-url",
                    "https://allowed.example.test/contacts.json",
                    "--source-license-label",
                    "cc-by-4.0",
                    "--allowed-source-host",
                    "allowed.example.test",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("profile source", result.stderr)
            self.assertIn("--enable-network-source", result.stderr)

    def test_main_rejects_profile_local_source_bad_license_and_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_license = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-contacts-bad-license.json",
                    "--output-dir",
                    str(Path(tmpdir) / "bad-license"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            missing_file = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-contacts-missing-file.json",
                    "--output-dir",
                    str(Path(tmpdir) / "missing-file"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(bad_license.returncode, 2)
            self.assertIn("license_label", bad_license.stderr)
            self.assertEqual(missing_file.returncode, 1)
            self.assertIn("local source rejected", missing_file.stderr)
            self.assertFalse((Path(tmpdir) / "missing-file" / "manifest.json").exists())

    def test_main_rejects_use_llm_with_non_llm_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-fixture.json",
                    "--use-llm",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--use-llm", result.stderr)
            self.assertIn("generation.mode", result.stderr)

    def test_main_can_run_deterministic_scale_probe_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_foundation_scale_probe_25")
            self.assertEqual(manifest["run_profile"]["target_candidate_count"], 25)
            self.assertRegex(manifest["run_profile"]["config_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(report["counts"]["total"], 25)
            self.assertEqual(report["rejection_causes"]["quality_duplicate"], 3)
            self.assertEqual(report["rejection_causes"]["solution_logic_error"], 4)
            self.assertNotIn("profile_decision_report", manifest["artifacts"])
            self.assertNotIn("evaluation_report", manifest["artifacts"])
            self.assertFalse((output_dir / "profile_decision_report.json").exists())
            self.assertFalse((output_dir / "evaluation_report.json").exists())
            self.assertIn("accepted=14", result.stdout)

    def test_main_can_write_evaluation_report_for_scale_probe_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-evaluation-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_path = output_dir / "evaluation_report.json"
            self.assertTrue(report_path.exists(), result.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "evaluation_report_v1")
            self.assertEqual(report["counts"]["passed"], 5)
            self.assertEqual(report["capability_slices"]["missing_contact"]["pass_rate"], 1.0)
            self.assertEqual(report["decision"]["status"], "passed")
            self.assertEqual(manifest["artifacts"]["evaluation_report"], "evaluation_report.json")
            self.assertIn("evaluation_report=", result.stdout)

    def test_main_can_write_profile_decision_report_for_scale_probe_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-profile-decision-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_path = output_dir / "profile_decision_report.json"
            self.assertTrue(report_path.exists(), result.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(report["decisions"]["async_orchestration"]["status"], "defer")
            self.assertEqual(
                report["decisions"]["semantic_duplicate_detection"]["status"],
                "defer",
            )
            self.assertEqual(report["decisions"]["mvp_quality_floor"]["status"], "passed")
            self.assertEqual(
                report["decisions"]["profile_promotion"]["status"],
                "insufficient_evidence",
            )
            self.assertEqual(
                manifest["artifacts"]["profile_decision_report"],
                "profile_decision_report.json",
            )
            self.assertIn("profile_decision_report=", result.stdout)

    def test_main_can_write_evaluation_and_profile_decision_reports_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            decision_report = json.loads(
                (output_dir / "profile_decision_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifacts"]["evaluation_report"], "evaluation_report.json")
            self.assertEqual(
                manifest["artifacts"]["profile_decision_report"],
                "profile_decision_report.json",
            )
            self.assertEqual(
                decision_report["inputs"]["evaluation_report_path"],
                "evaluation_report.json",
            )
            self.assertEqual(decision_report["evaluation"]["decision_status"], "passed")
            self.assertEqual(
                decision_report["decisions"]["profile_promotion"]["status"],
                "passed",
            )

    def test_main_can_write_dataset_release_report_for_scale_probe_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["decisions"]["dataset_release"]["status"], "ineligible")
            self.assertEqual(report["profile"]["profile_purpose"], "diagnostic_probe")

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["artifacts"]["dataset_release_report"],
                "dataset_release_report.json",
            )
            self.assertIn("dataset_release_report=", result.stdout)

    def test_smoke_release_candidate_profile_has_insufficient_release_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-release-smoke"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-fixture.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                report["decisions"]["dataset_release"]["status"],
                "insufficient_evidence",
            )
            self.assertEqual(
                report["release_completeness"]["decision"]["status"],
                "insufficient_evidence",
            )

    def test_release_candidate_profile_can_pass_dataset_release_admission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-release-candidate"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
            )
            completeness = report["release_completeness"]
            self.assertEqual(report["decisions"]["dataset_release"]["status"], "passed")
            self.assertEqual(completeness["decision"]["status"], "passed")
            self.assertGreaterEqual(completeness["observed"]["accepted"], 5)
            self.assertLessEqual(completeness["observed"]["rejection_rate"], 0.2)
            self.assertEqual(
                set(completeness["thresholds"]["required_task_types"]),
                set(completeness["observed"]["task_types"]),
            )

    def test_release_pack_requires_dataset_release_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-dataset-release-pack",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation-release-candidate"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--write-dataset-release-pack", result.stderr)
            self.assertIn("--write-dataset-release-report", result.stderr)

    def test_release_pack_is_not_attached_when_release_report_does_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("dataset_release", result.stderr)
            self.assertFalse((output_dir / "dataset_release_pack.json").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("dataset_release_pack", manifest["artifacts"])

    def test_release_candidate_profile_can_write_and_verify_release_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-release-candidate"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            pack_path = output_dir / "dataset_release_pack.json"
            self.assertTrue(pack_path.exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["artifacts"]["dataset_release_pack"],
                "dataset_release_pack.json",
            )
            self.assertEqual(pack["verification"]["status"], "passed")
            self.assertEqual(
                pack["artifacts"]["manifest"]["path"],
                "manifest.json",
            )
            self.assertIn("dataset_release_pack=", result.stdout)

            verification = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify_dataset_release.py",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(verification.returncode, 0, verification.stdout + verification.stderr)
            verified = json.loads(verification.stdout)
            self.assertEqual(verified["verification"]["status"], "passed")

            (output_dir / "samples.jsonl").write_text('{"drift": true}\n', encoding="utf-8")
            drifted = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify_dataset_release.py",
                    "--release-pack",
                    str(pack_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(drifted.returncode, 1)
            drift_result = json.loads(drifted.stdout)
            self.assertEqual(drift_result["verification"]["status"], "failed")

    def test_release_candidate_profile_can_write_quality_audit_and_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-release-candidate-quality-audit"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-release-quality-audit",
                    "--write-dataset-release-card",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            audit_path = output_dir / "release_quality_audit.json"
            card_path = output_dir / "dataset_release_card.md"
            self.assertTrue(audit_path.exists(), result.stdout)
            self.assertTrue(card_path.exists(), result.stdout)

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            card = card_path.read_text(encoding="utf-8")
            self.assertEqual(
                manifest["artifacts"]["release_quality_audit"],
                "release_quality_audit.json",
            )
            self.assertEqual(
                manifest["artifacts"]["dataset_release_card"],
                "dataset_release_card.md",
            )
            self.assertIn(audit["decision"]["status"], {"clear", "watch"})
            self.assertNotEqual(audit["decision"]["status"], "blocked")
            self.assertIn("## Non-Claims", card)
            self.assertIn("release_quality_audit_status:", card)
            self.assertIn("release_quality_audit=", result.stdout)
            self.assertIn("dataset_release_card=", result.stdout)

    def test_release_quality_audit_requires_dataset_release_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-release-quality-audit",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation-release-candidate"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--write-release-quality-audit", result.stderr)
            self.assertIn("--write-dataset-release-report", result.stderr)

    def test_dataset_release_card_requires_dataset_release_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-release-candidate.json",
                    "--write-dataset-release-card",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation-release-candidate"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--write-dataset-release-card", result.stderr)
            self.assertIn("--write-dataset-release-report", result.stderr)

    def test_dataset_release_report_requires_profile_decision_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-scale-probe"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json",
                    "--write-evaluation-report",
                    "--write-dataset-release-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--write-dataset-release-report", result.stderr)
            self.assertIn("--write-profile-decision-report", result.stderr)

    def test_evaluation_report_for_profile_local_source_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-profile-local"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-contacts.json",
                    "--write-evaluation-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            exported = (output_dir / "evaluation_report.json").read_text(encoding="utf-8")
            self.assertNotIn("contacts-profile.json", exported)
            self.assertNotIn(str(Path.cwd()), exported)
            self.assertNotIn("alice.zhang@example.test", exported)
            self.assertNotIn("ben.carter@example.test", exported)

    def test_use_llm_requires_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("AGENT_DATA_LLM_BASE_URL", None)
            env.pop("AGENT_DATA_API_KEY", None)
            env.pop("AGENT_DATA_LLM_MODEL", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--use-llm",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "AGENT_DATA_LLM_BASE_URL, AGENT_DATA_API_KEY, and AGENT_DATA_LLM_MODEL",
                result.stderr,
            )
            self.assertNotIn("Authorization", result.stderr)


if __name__ == "__main__":
    unittest.main()
