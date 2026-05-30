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
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_test")
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
            profile_path.write_text('{"schema_version": "run_profile_v2"}', encoding="utf-8")

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
            self.assertIn("accepted=14", result.stdout)

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
