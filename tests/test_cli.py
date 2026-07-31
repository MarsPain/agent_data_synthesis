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
    def _run_release_review_pipeline(
        self,
        output_dir: Path,
        *,
        profile_path: str = "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
        write_release_pack: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            "main.py",
            "--run-profile",
            profile_path,
            "--write-evaluation-report",
            "--write-profile-decision-report",
            "--write-dataset-release-report",
            "--write-release-quality-audit",
            "--write-release-review-queue",
        ]
        if write_release_pack:
            command.append("--write-dataset-release-pack")
        command.extend(["--output-dir", str(output_dir)])
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "AGENT_DATA_API_KEY": "release-review-credential-sentinel",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def _snapshot_output_artifacts(self, output_dir: Path) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in output_dir.iterdir()
            if path.is_file() and path.name != "manifest.json"
        }

    def _assert_release_artifact_set(self, output_dir: Path) -> None:
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        for artifact_name in (
            "evaluation_report",
            "profile_decision_report",
            "dataset_release_report",
            "dataset_release_pack",
            "release_quality_audit",
            "dataset_release_card",
        ):
            self.assertIn(artifact_name, manifest["artifacts"])
            self.assertTrue((output_dir / manifest["artifacts"][artifact_name]).exists())

        release_report = json.loads(
            (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(release_report["decisions"]["dataset_release"]["status"], "passed")
        self.assertEqual(
            release_report["release_completeness"]["decision"]["status"],
            "passed",
        )
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
        self.assertEqual(
            verification.returncode,
            0,
            verification.stdout + verification.stderr,
        )

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
            self.assertFalse((output_dir / "episodes.jsonl").exists())
            self.assertFalse((output_dir / "episode_quality_report.json").exists())
            self.assertFalse((output_dir / "episode_replay_report.json").exists())
            self.assertFalse((output_dir / "reward_labels.jsonl").exists())
            self.assertFalse((output_dir / "reward_label_report.json").exists())
            self.assertFalse((output_dir / "dataset_release_report.json").exists())
            self.assertFalse((output_dir / "dataset_release_pack.json").exists())
            self.assertFalse((output_dir / "release_quality_audit.json").exists())
            self.assertFalse((output_dir / "dataset_release_card.md").exists())
            self.assertFalse((output_dir / "release_review_queue.jsonl").exists())
            self.assertFalse((output_dir / "review_resolution_report.json").exists())
            self.assertFalse((output_dir / "representative_scale_evidence.json").exists())
            self.assertFalse((output_dir / "downstream_benchmark_bundle.json").exists())
            self.assertFalse((output_dir / "downstream_benchmark_result.json").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_test")
            self.assertNotIn("episodes", manifest["artifacts"])
            self.assertNotIn("episode_quality_report", manifest["artifacts"])
            self.assertNotIn("episode_replay_report", manifest["artifacts"])
            self.assertNotIn("reward_labels", manifest["artifacts"])
            self.assertNotIn("reward_label_report", manifest["artifacts"])
            self.assertNotIn("dataset_release_report", manifest["artifacts"])
            self.assertNotIn("dataset_release_pack", manifest["artifacts"])
            self.assertNotIn("release_quality_audit", manifest["artifacts"])
            self.assertNotIn("dataset_release_card", manifest["artifacts"])
            self.assertNotIn("release_review_queue", manifest["artifacts"])
            self.assertNotIn("review_resolution_report", manifest["artifacts"])
            self.assertIn("accepted=2", result.stdout)
            self.assertNotIn("reward_label_report=", result.stdout)
            self.assertNotIn("secret-test-key", result.stdout)

    def test_main_can_write_episode_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--write-episode-quality-report",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_episode_quality",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "episodes.jsonl").exists(), result.stdout)
            report_path = output_dir / "episode_quality_report.json"
            self.assertTrue(report_path.exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["episodes"], "episodes.jsonl")
            self.assertEqual(
                manifest["artifacts"]["episode_quality_report"],
                "episode_quality_report.json",
            )
            self.assertEqual(report["decision"]["status"], "passed")
            self.assertGreater(report["observed"]["runtime_counts"]["contacts_fixture"], 0)
            self.assertIn("episode_quality_report=", result.stdout)

    def test_main_can_write_episode_replay_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--write-episode-replay-report",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_episode_replay",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "episodes.jsonl").exists(), result.stdout)
            report_path = output_dir / "episode_replay_report.json"
            self.assertTrue(report_path.exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["episodes"], "episodes.jsonl")
            self.assertEqual(
                manifest["artifacts"]["episode_replay_report"],
                "episode_replay_report.json",
            )
            self.assertEqual(report["decision"]["status"], "passed")
            self.assertGreater(report["observed"]["runtime_counts"]["contacts_fixture"], 0)
            self.assertIn("episode_replay_report=", result.stdout)

    def test_main_can_write_reward_label_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--write-reward-label-report",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_reward_labels",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "episodes.jsonl").exists(), result.stdout)
            labels_path = output_dir / "reward_labels.jsonl"
            report_path = output_dir / "reward_label_report.json"
            self.assertTrue(labels_path.exists(), result.stdout)
            self.assertTrue(report_path.exists(), result.stdout)
            self.assertFalse((output_dir / "episode_quality_report.json").exists())
            self.assertFalse((output_dir / "episode_replay_report.json").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            labels = [
                json.loads(line)
                for line in labels_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(manifest["artifacts"]["episodes"], "episodes.jsonl")
            self.assertEqual(manifest["artifacts"]["reward_labels"], "reward_labels.jsonl")
            self.assertEqual(
                manifest["artifacts"]["reward_label_report"],
                "reward_label_report.json",
            )
            self.assertNotIn("episode_quality_report", manifest["artifacts"])
            self.assertNotIn("episode_replay_report", manifest["artifacts"])
            self.assertEqual(report["decision"]["status"], "passed")
            self.assertGreater(report["observed"]["runtime_counts"]["contacts_fixture"], 0)
            self.assertTrue(all(label["label_status"] == "usable" for label in labels))
            self.assertIn("reward_label_report=", result.stdout)

    def test_mobile_profile_can_write_episode_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--write-episode-quality-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(
                report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            self.assertEqual(report["decision"]["status"], "passed")

    def test_mobile_profile_can_write_episode_replay_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--write-episode-replay-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(
                report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            self.assertEqual(report["decision"]["status"], "passed")

    def test_mobile_profile_can_write_reward_label_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--write-reward-label-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            labels = [
                json.loads(line)
                for line in (output_dir / "reward_labels.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertGreater(
                report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            self.assertTrue(
                any(label["runtime_id"] == "mobile_messages_fixture" for label in labels)
            )
            self.assertEqual(report["decision"]["status"], "passed")

    def test_workspace_profile_can_write_replay_and_reward_label_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "workspace-tasks-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/workspace-tasks-fixture.json",
                    "--write-episode-replay-report",
                    "--write-reward-label-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            replay_report = json.loads(
                (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
            )
            reward_report = json.loads(
                (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            labels = [
                json.loads(line)
                for line in (output_dir / "reward_labels.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]

            self.assertEqual(manifest["run_profile"]["seed"]["domain"], "workspace_tasks_fixture")
            self.assertEqual(manifest["artifacts"]["episodes"], "episodes.jsonl")
            self.assertEqual(
                manifest["artifacts"]["episode_replay_report"],
                "episode_replay_report.json",
            )
            self.assertEqual(manifest["artifacts"]["reward_labels"], "reward_labels.jsonl")
            self.assertEqual(
                manifest["artifacts"]["reward_label_report"],
                "reward_label_report.json",
            )
            self.assertEqual(
                replay_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                5,
            )
            self.assertEqual(
                reward_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                5,
            )
            self.assertTrue(
                all(label["runtime_id"] == "workspace_tasks_fixture" for label in labels)
            )
            self.assertTrue(all(label["label_status"] == "usable" for label in labels))

    def test_main_can_run_profile_local_workspace_tasks_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "workspace-profile-local"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-workspace-tasks.json",
                    "--write-episode-quality-report",
                    "--write-episode-replay-report",
                    "--write-reward-label-report",
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
            self.assertEqual(manifest["accepted_count"], 5)
            self.assertEqual(
                manifest["run_profile"]["source"]["kind"],
                "local_workspace_tasks_json",
            )
            self.assertEqual(
                manifest["run_profile"]["source"]["source_id"],
                "source_profile_workspace_tasks_v1",
            )
            quality_report = json.loads(
                (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
            )
            replay_report = json.loads(
                (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
            )
            reward_report = json.loads(
                (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(
                quality_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            self.assertGreater(
                replay_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            self.assertGreater(
                reward_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            exported_metadata = (
                (output_dir / "manifest.json").read_text(encoding="utf-8")
                + (output_dir / "source_events.jsonl").read_text(encoding="utf-8")
                + (output_dir / "quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
                + (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("workspace-tasks-profile.json", exported_metadata)
            self.assertNotIn("Launch owners, target dates", exported_metadata)
            self.assertIn("accepted=5", result.stdout)

    def test_mobile_profile_can_write_domain_aware_evaluation_and_profile_decision_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
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
            evaluation_report = json.loads(
                (output_dir / "evaluation_report.json").read_text(encoding="utf-8")
            )
            decision_report = json.loads(
                (output_dir / "profile_decision_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["run_profile"]["seed"]["domain"],
                "mobile_messages_fixture",
            )
            self.assertEqual(
                evaluation_report["suite"]["suite_id"],
                "mobile_messages_heldout_v1",
            )
            self.assertEqual(
                evaluation_report["domain"]["domain_id"],
                "mobile_messages_fixture",
            )
            self.assertEqual(
                decision_report["evaluation"]["domain_id"],
                "mobile_messages_fixture",
            )
            self.assertEqual(
                decision_report["decisions"]["profile_promotion"]["status"],
                "passed",
            )

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

    def test_main_can_run_mobile_fixture_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for artifact_name in (
                "samples.jsonl",
                "rejections.jsonl",
                "manifest.json",
                "quality_report.json",
            ):
                self.assertTrue((output_dir / artifact_name).exists(), artifact_name)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_mobile_agent_fixture")
            self.assertEqual(manifest["accepted_count"], 5)
            self.assertEqual(manifest["rejected_count"], 0)
            self.assertEqual(manifest["run_profile"]["generation_mode"], "mobile_fixture")
            samples = [
                json.loads(line)
                for line in (output_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                all(sample["environment"]["id"] == "mobile_messages_fixture" for sample in samples)
            )
            tool_names = {tool["name"] for tool in samples[0]["tools"]}
            self.assertIn("search_phone_messages", tool_names)
            self.assertIn("create_phone_reminder", tool_names)
            self.assertIn("draft_message_reply", tool_names)
            self.assertIn("accepted=5", result.stdout)

    def test_default_main_output_remains_contacts_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation-default"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_default_contacts_only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            samples_text = (output_dir / "samples.jsonl").read_text(encoding="utf-8")
            self.assertIn("contacts_fixture", samples_text)
            self.assertIn("lookup_contact_email", samples_text)
            self.assertNotIn("mobile_messages_fixture", samples_text)
            self.assertNotIn("search_phone_messages", samples_text)

    def test_main_can_enable_mobile_profile_with_local_mcp_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-agent-fixture"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--enable-mcp-adapter",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            sample = json.loads(
                (output_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                sample["lineage"]["adapter"][0]["adapter_id"],
                "mobile_messages_local_mcp_adapter",
            )
            self.assertIn("mobile_messages_local_mcp_adapter", report["slices"]["adapter_id"])

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
            profile_path.write_text('{"schema_version": "run_profile_v5"}', encoding="utf-8")

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

    def test_main_can_preview_and_write_a_coverage_plan_without_running_candidates(self) -> None:
        profile_path = "tests/fixtures/run_profiles/contacts-coverage-smoke.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            preview_output = Path(tmpdir) / "preview-output"
            preview = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    profile_path,
                    "--preview-coverage-plan",
                    "--output-dir",
                    str(preview_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            previewed_plan = json.loads(preview.stdout)
            self.assertEqual(previewed_plan["schema_version"], "coverage_plan_v1")
            self.assertEqual(previewed_plan["target_accepted_sample_count"], 6)
            self.assertFalse(preview_output.exists())

            write_output = Path(tmpdir) / "write-output"
            written = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    profile_path,
                    "--write-coverage-plan",
                    "--output-dir",
                    str(write_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            plan_path = write_output / "coverage_plan.json"
            self.assertTrue(plan_path.exists())
            self.assertEqual(json.loads(plan_path.read_text(encoding="utf-8")), previewed_plan)
            self.assertEqual(
                {path.name for path in write_output.iterdir()},
                {"coverage_plan.json"},
            )
            self.assertFalse((write_output / "samples.jsonl").exists())
            self.assertFalse((write_output / "manifest.json").exists())

    def test_llm_campaign_plan_preview_does_not_require_provider_opt_in(
        self,
    ) -> None:
        profile_path = (
            "tests/fixtures/run_profiles/contacts-coverage-campaign-30.json"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "preview-output"
            preview = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    profile_path,
                    "--preview-coverage-plan",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key
                    not in {
                        "AGENT_DATA_LLM_BASE_URL",
                        "AGENT_DATA_API_KEY",
                        "AGENT_DATA_LLM_MODEL",
                    }
                },
            )

            self.assertEqual(
                preview.returncode,
                0,
                preview.stdout + preview.stderr,
            )
            plan = json.loads(preview.stdout)
            self.assertEqual(plan["target_accepted_sample_count"], 30)
            self.assertEqual(plan["attempt_ceiling"], 60)
            self.assertEqual(
                plan["catalog"]["version"],
                "contacts_coverage_v2",
            )
            self.assertFalse(output_dir.exists())

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

    def test_main_can_run_profile_local_mobile_messages_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-profile-local"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-mobile-messages.json",
                    "--write-episode-quality-report",
                    "--write-episode-replay-report",
                    "--write-reward-label-report",
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
            self.assertEqual(manifest["accepted_count"], 5)
            self.assertEqual(
                manifest["run_profile"]["source"]["kind"],
                "local_mobile_messages_json",
            )
            self.assertEqual(
                manifest["run_profile"]["source"]["source_id"],
                "source_profile_mobile_messages_v1",
            )
            quality_report = json.loads(
                (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
            )
            replay_report = json.loads(
                (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
            )
            reward_report = json.loads(
                (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(
                quality_report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            self.assertGreater(
                replay_report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            self.assertGreater(
                reward_report["observed"]["runtime_counts"]["mobile_messages_fixture"],
                0,
            )
            exported_metadata = (
                (output_dir / "manifest.json").read_text(encoding="utf-8")
                + (output_dir / "source_events.jsonl").read_text(encoding="utf-8")
                + (output_dir / "quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
                + (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("mobile-messages-profile.json", exported_metadata)
            self.assertNotIn("project update tomorrow", exported_metadata)
            self.assertNotIn("4821", exported_metadata)
            self.assertIn("accepted=5", result.stdout)

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

    def test_main_rejects_mobile_profile_with_network_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-agent-fixture.json",
                    "--enable-network-source",
                    "--source-url",
                    "https://allowed.example.test/contacts.json",
                    "--source-license-label",
                    "cc-by-4.0",
                    "--allowed-source-host",
                    "allowed.example.test",
                    "--output-dir",
                    str(Path(tmpdir) / "mobile-agent-fixture"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--enable-network-source", result.stderr)
            self.assertIn("contacts", result.stderr)

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

    def test_mobile_release_candidate_profile_can_write_release_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-release"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
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
            self._assert_release_artifact_set(output_dir)

    def test_mobile_release_candidate_can_write_release_review_queue(self) -> None:
        from synthesis.contracts import validate_release_review_item_record

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-release-review"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-release-quality-audit",
                    "--write-release-review-queue",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            audit = json.loads(
                (output_dir / "release_quality_audit.json").read_text(encoding="utf-8")
            )
            self.assertEqual(audit["decision"]["status"], "watch")
            queue_path = output_dir / "release_review_queue.jsonl"
            self.assertTrue(queue_path.exists(), result.stdout)
            queue = [
                json.loads(line)
                for line in queue_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertGreater(len(queue), 0)
            for item in queue:
                validate_release_review_item_record(item)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["artifacts"]["release_review_queue"],
                "release_review_queue.jsonl",
            )
            self.assertIn("release_review_queue=", result.stdout)

    def test_clear_release_quality_audit_does_not_write_review_queue(self) -> None:
        from main import _write_release_review_queue_for_audit
        from synthesis.release_quality import (
            ReleaseQualityThresholds,
            build_release_quality_audit,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "clear-release-review"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-release-quality-audit",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest_path = output_dir / "manifest.json"
            audit_path = output_dir / "release_quality_audit.json"
            audit = build_release_quality_audit(
                manifest_path=manifest_path,
                thresholds=ReleaseQualityThresholds(
                    small_release_watch_accepted_samples=1,
                    max_largest_task_type_share=1.0,
                    max_largest_tool_combination_share=1.0,
                    max_exact_duplicate_rate=1.0,
                    max_duplicate_family_size=100,
                ),
            )
            self.assertEqual(audit["decision"]["status"], "clear")
            for status in ("clear", "blocked", "insufficient_evidence"):
                with self.subTest(status=status):
                    non_watch_audit = json.loads(json.dumps(audit))
                    non_watch_audit["decision"] = {
                        "status": status,
                        "reasons": ["no release review work is required"],
                        "triggered_by": [],
                    }
                    audit_path.write_text(
                        json.dumps(
                            non_watch_audit,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    queue_path = _write_release_review_queue_for_audit(
                        manifest_path=manifest_path,
                        audit_path=audit_path,
                    )

                    self.assertIsNone(queue_path)
                    self.assertFalse(
                        (output_dir / "release_review_queue.jsonl").exists()
                    )
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    self.assertNotIn("release_review_queue", manifest["artifacts"])

    def test_offline_review_resolution_writes_sanitized_insufficient_report_for_malformed_decisions(
        self,
    ) -> None:
        from synthesis.contracts import validate_review_resolution_report_record

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "malformed-review-resolution"
            self._run_release_review_pipeline(output_dir)
            artifacts_before = self._snapshot_output_artifacts(output_dir)
            decisions_path = output_dir / "review_decisions.jsonl"
            decisions_path.write_text("{raw-secret-decision\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_review_resolution.py",
                    "--output-dir",
                    str(output_dir),
                    "--decisions-path",
                    str(decisions_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_path = output_dir / "review_resolution_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            validate_review_resolution_report_record(report)
            self.assertEqual(report["decision"]["status"], "insufficient_evidence")
            exported = report_path.read_text(encoding="utf-8")
            self.assertNotIn("raw-secret-decision", exported)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["artifacts"]["review_resolution_report"],
                "review_resolution_report.json",
            )
            for artifact_name, content in artifacts_before.items():
                self.assertEqual((output_dir / artifact_name).read_bytes(), content)
            self.assertIn("review_resolution_report=", result.stdout)

    def test_offline_review_resolution_requires_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            cases = (("absent", None), ("malformed", "{raw-manifest\n"))
            for case_name, manifest_content in cases:
                with self.subTest(case_name=case_name):
                    output_dir = base_dir / case_name
                    output_dir.mkdir()
                    if manifest_content is not None:
                        (output_dir / "manifest.json").write_text(
                            manifest_content,
                            encoding="utf-8",
                        )

                    result = subprocess.run(
                        [
                            sys.executable,
                            "scripts/write_review_resolution.py",
                            "--output-dir",
                            str(output_dir),
                            "--decisions-path",
                            str(output_dir / "review_decisions.jsonl"),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertIn("manifest is absent or malformed", result.stderr)
                    self.assertNotIn("raw-manifest", result.stderr)
                    self.assertFalse(
                        (output_dir / "review_resolution_report.json").exists()
                    )

    def test_offline_review_resolution_reports_pending_decisions(self) -> None:
        from synthesis.contracts import validate_review_resolution_report_record

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "pending-review-resolution"
            self._run_release_review_pipeline(
                output_dir,
                profile_path=(
                    "tests/fixtures/run_profiles/foundation-scale-probe-25.json"
                ),
            )
            queue = [
                json.loads(line)
                for line in (output_dir / "release_review_queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertGreaterEqual(len(queue), 2)
            decisions_path = output_dir / "review_decisions.jsonl"
            decision = {
                "schema_version": "review_decision_v1",
                "review_item_id": queue[0]["review_item_id"],
                "outcome": "accepted_risk",
                "reason_code": "sufficient_context",
                "review_minutes": 3,
                "reviewer_alias": "quality_reviewer_1",
                "decided_at": "1970-01-01T00:00:00Z",
            }
            decisions_path.write_text(
                json.dumps(decision, ensure_ascii=True, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_review_resolution.py",
                    "--output-dir",
                    str(output_dir),
                    "--decisions-path",
                    str(decisions_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "review_resolution_report.json").read_text(
                    encoding="utf-8"
                )
            )
            validate_review_resolution_report_record(report)
            self.assertEqual(report["decision"]["status"], "pending_review")
            self.assertEqual(report["counts"]["queued"], len(queue))
            self.assertEqual(report["counts"]["resolved"], 1)
            self.assertEqual(report["counts"]["pending"], len(queue) - 1)
            self.assertEqual(report["counts"]["accepted_risk"], 1)
            self.assertEqual(report["counts"]["review_minutes"], 3)

    def test_offline_review_resolution_reports_completed_decisions(self) -> None:
        from synthesis.contracts import validate_review_resolution_report_record

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "completed-review-resolution"
            self._run_release_review_pipeline(output_dir)
            queue = [
                json.loads(line)
                for line in (output_dir / "release_review_queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            artifacts_before = self._snapshot_output_artifacts(output_dir)
            decisions = [
                {
                    "schema_version": "review_decision_v1",
                    "review_item_id": item["review_item_id"],
                    "outcome": "confirmed_issue",
                    "reason_code": "insufficient_diversity",
                    "review_minutes": 2,
                    "reviewer_alias": "quality_reviewer_1",
                    "decided_at": "1970-01-01T00:00:00Z",
                }
                for item in queue
            ]
            decisions_path = output_dir / "review_decisions.jsonl"
            decisions_path.write_text(
                "".join(
                    json.dumps(decision, ensure_ascii=True, sort_keys=True) + "\n"
                    for decision in decisions
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_review_resolution.py",
                    "--output-dir",
                    str(output_dir),
                    "--decisions-path",
                    str(decisions_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_path = output_dir / "review_resolution_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            validate_review_resolution_report_record(report)
            self.assertEqual(report["decision"]["status"], "reviewed")
            self.assertEqual(report["counts"]["queued"], len(queue))
            self.assertEqual(report["counts"]["resolved"], len(queue))
            self.assertEqual(report["counts"]["pending"], 0)
            self.assertEqual(report["counts"]["confirmed_issue"], len(queue))
            self.assertEqual(report["counts"]["review_minutes"], 2 * len(queue))
            self.assertNotIn("quality_reviewer_1", report_path.read_text(encoding="utf-8"))
            for artifact_name, content in artifacts_before.items():
                self.assertEqual((output_dir / artifact_name).read_bytes(), content)

    def test_three_domain_review_resolution_preserves_release_evidence(self) -> None:
        from synthesis.contracts import (
            validate_release_review_item_record,
            validate_review_resolution_report_record,
        )

        profiles = {
            "contacts": "tests/fixtures/run_profiles/foundation-release-candidate.json",
            "mobile": "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
            "workspace": "tests/fixtures/run_profiles/workspace-tasks-release-candidate.json",
        }
        outcome_evidence = (
            ("accepted_risk", "sufficient_context"),
            ("confirmed_issue", "insufficient_diversity"),
            ("needs_follow_up", "requires_more_data"),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            for domain, profile_path in profiles.items():
                with self.subTest(domain=domain):
                    output_dir = Path(tmpdir) / domain
                    self._run_release_review_pipeline(
                        output_dir,
                        profile_path=profile_path,
                        write_release_pack=True,
                    )
                    audit = json.loads(
                        (output_dir / "release_quality_audit.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(audit["decision"]["status"], "watch")
                    queue_path = output_dir / "release_review_queue.jsonl"
                    queue_text = queue_path.read_text(encoding="utf-8")
                    queue = [json.loads(line) for line in queue_text.splitlines()]
                    self.assertGreater(len(queue), 0)
                    for item in queue:
                        validate_release_review_item_record(item)

                    samples = [
                        json.loads(line)
                        for line in (output_dir / "samples.jsonl")
                        .read_text(encoding="utf-8")
                        .splitlines()
                    ]
                    self.assertGreater(len(samples), 0)
                    for sample in samples:
                        self.assertNotIn(sample["task"]["instruction"], queue_text)
                    for sentinel in (
                        profile_path,
                        str(Path(profile_path).resolve()),
                        "release-review-credential-sentinel",
                    ):
                        self.assertNotIn(sentinel, queue_text)

                    artifacts_before = self._snapshot_output_artifacts(output_dir)
                    release_report_before = json.loads(
                        artifacts_before["dataset_release_report.json"]
                    )
                    profile_decisions_before = json.loads(
                        artifacts_before["profile_decision_report.json"]
                    )["decisions"]
                    decisions_path = output_dir / "review_decisions.jsonl"
                    decisions = []
                    for index, item in enumerate(queue):
                        outcome, reason_code = outcome_evidence[
                            index % len(outcome_evidence)
                        ]
                        decisions.append(
                            {
                                "schema_version": "review_decision_v1",
                                "review_item_id": item["review_item_id"],
                                "outcome": outcome,
                                "reason_code": reason_code,
                                "review_minutes": index + 1,
                                "reviewer_alias": "quality_reviewer_1",
                                "decided_at": "1970-01-01T00:00:00Z",
                            }
                        )
                    decisions_path.write_text(
                        "".join(
                            json.dumps(decision, ensure_ascii=True, sort_keys=True)
                            + "\n"
                            for decision in decisions
                        ),
                        encoding="utf-8",
                    )

                    resolution = subprocess.run(
                        [
                            sys.executable,
                            "scripts/write_review_resolution.py",
                            "--output-dir",
                            str(output_dir),
                            "--decisions-path",
                            str(decisions_path),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        resolution.returncode,
                        0,
                        resolution.stdout + resolution.stderr,
                    )
                    report = json.loads(
                        (output_dir / "review_resolution_report.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    validate_review_resolution_report_record(report)
                    self.assertEqual(report["decision"]["status"], "reviewed")
                    self.assertEqual(report["counts"]["resolved"], len(queue))
                    self.assertEqual(report["counts"]["pending"], 0)

                    for artifact_name, content in artifacts_before.items():
                        self.assertEqual(
                            (output_dir / artifact_name).read_bytes(),
                            content,
                            artifact_name,
                        )
                    release_report_after = json.loads(
                        (output_dir / "dataset_release_report.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(release_report_after, release_report_before)
                    self.assertEqual(
                        release_report_after["decisions"]["dataset_release"]["status"],
                        "passed",
                    )
                    profile_decisions_after = json.loads(
                        (output_dir / "profile_decision_report.json").read_text(
                            encoding="utf-8"
                        )
                    )["decisions"]
                    for decision_name in (
                        "semantic_duplicate_detection",
                        "async_orchestration",
                    ):
                        self.assertEqual(
                            profile_decisions_after[decision_name],
                            profile_decisions_before[decision_name],
                        )

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
                    self.assertEqual(
                        verification.returncode,
                        0,
                        verification.stdout + verification.stderr,
                    )
                    self.assertEqual(
                        json.loads(verification.stdout)["verification"]["status"],
                        "passed",
                    )

    def test_offline_review_resolution_rejects_queue_from_another_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mismatched-review-resolution"
            self._run_release_review_pipeline(output_dir)
            queue = [
                json.loads(line)
                for line in (output_dir / "release_review_queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            manifest_path = output_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_version"] = "dataset_another_release"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            decisions_path = output_dir / "review_decisions.jsonl"
            decisions_path.write_text(
                "".join(
                    json.dumps(
                        {
                            "schema_version": "review_decision_v1",
                            "review_item_id": item["review_item_id"],
                            "outcome": "accepted_risk",
                            "reason_code": "sufficient_context",
                            "review_minutes": 1,
                            "reviewer_alias": "quality_reviewer_1",
                            "decided_at": "1970-01-01T00:00:00Z",
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                    + "\n"
                    for item in queue
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_review_resolution.py",
                    "--output-dir",
                    str(output_dir),
                    "--decisions-path",
                    str(decisions_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (output_dir / "review_resolution_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["dataset_version"], "dataset_another_release")
            self.assertEqual(report["decision"]["status"], "insufficient_evidence")
            self.assertIn(
                "queue_dataset_version_mismatch",
                report["decision"]["reasons"],
            )

    def test_offline_review_resolution_requires_manifest_queue_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "missing-queue-artifact"
            self._run_release_review_pipeline(output_dir)
            queue = [
                json.loads(line)
                for line in (output_dir / "release_review_queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            decisions_path = output_dir / "review_decisions.jsonl"
            decisions_path.write_text(
                "".join(
                    json.dumps(
                        {
                            "schema_version": "review_decision_v1",
                            "review_item_id": item["review_item_id"],
                            "outcome": "accepted_risk",
                            "reason_code": "sufficient_context",
                            "review_minutes": 1,
                            "reviewer_alias": "quality_reviewer_1",
                            "decided_at": "1970-01-01T00:00:00Z",
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                    + "\n"
                    for item in queue
                ),
                encoding="utf-8",
            )
            manifest_path = output_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["artifacts"]["release_review_queue"]
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest_before = manifest_path.read_bytes()

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_review_resolution.py",
                    "--output-dir",
                    str(output_dir),
                    "--decisions-path",
                    str(decisions_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "manifest is missing release_review_queue artifact",
                result.stderr,
            )
            self.assertNotIn(str(output_dir), result.stderr)
            self.assertFalse((output_dir / "review_resolution_report.json").exists())
            self.assertEqual(manifest_path.read_bytes(), manifest_before)

    def test_workspace_release_candidate_profile_can_write_release_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "workspace-release"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/workspace-tasks-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
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
            self._assert_release_artifact_set(output_dir)

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

    def test_release_review_queue_requires_release_quality_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--write-release-review-queue",
                    "--output-dir",
                    str(Path(tmpdir) / "release-review"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "--write-release-review-queue requires --write-release-quality-audit",
                result.stderr,
            )

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

    def test_llm_schema_failure_completes_sanitized_reporting_chain(self) -> None:
        from main import main
        from synthesis.llm import LLMGenerationResult

        raw_response_marker = "RAW_PROVIDER_RESPONSE_MARKER"
        api_key_marker = "provider-probe-api-key-marker"

        def invalid_generation(self, prompt: str, *, role: str) -> LLMGenerationResult:
            payload = json.loads(prompt)
            prefix = payload["batch_context"]["candidate_id_prefix"]
            count = payload["requested_candidate_count"]
            records = [
                {
                    "candidate_id": f"{prefix}task_{index:02d}",
                    "instruction": "Find Alice Zhang's email address.",
                    "task_type": "contact_lookup",
                    "difficulty": {
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    "required_capabilities": ["contact_lookup"],
                    "required_tools": ["lookup_contact_email"],
                    "primary_tool": "lookup_contact_email",
                    "primary_arguments": {"name": "Alice Zhang"},
                    "final_answer_contains": "alice.zhang@example.test",
                    "expected_state": [],
                }
                for index in range(count)
            ]
            records[0]["expected_state"] = [
                {
                    "check_type": raw_response_marker,
                    "expected": {"provider_value": raw_response_marker},
                }
            ]
            return LLMGenerationResult(
                content={"task_contracts": records},
                lineage={
                    "role": role,
                    "provider_host": "llm.example.test",
                    "retry_count": 0,
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "schema-failure"
            profile_path = root / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": "run_profile_v3",
                        "profile_id": "contacts_schema_failure_test",
                        "dataset_version": "dataset_contacts_schema_failure_test",
                        "profile_purpose": "benchmark",
                        "seed": {
                            "seed_id": "seed_contacts_schema_failure_test",
                            "domain": "contacts_fixture",
                            "description": "Generate grounded executable contacts tasks.",
                            "task_taxonomy": ["contact_lookup", "contact_followup"],
                        },
                        "generation": {
                            "mode": "llm",
                            "target_candidate_count": 2,
                            "context_policy": "synthetic_fixture",
                        },
                        "features": {},
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "main.py",
                "--run-profile",
                str(profile_path),
                "--use-llm",
                "--write-evaluation-report",
                "--write-profile-decision-report",
                "--write-dataset-release-report",
                "--write-release-quality-audit",
                "--output-dir",
                str(output_dir),
            ]
            env = {
                "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                "AGENT_DATA_API_KEY": api_key_marker,
                "AGENT_DATA_LLM_MODEL": "test-generator",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(sys, "argv", argv),
                patch(
                    "synthesis.llm.OpenAICompatibleClient.generate_json",
                    new=invalid_generation,
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            artifact_names = (
                "samples.jsonl",
                "rejections.jsonl",
                "manifest.json",
                "quality_report.json",
                "evaluation_report.json",
                "profile_decision_report.json",
                "dataset_release_report.json",
                "release_quality_audit.json",
            )
            for artifact_name in artifact_names:
                self.assertTrue((output_dir / artifact_name).exists(), artifact_name)

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_count"], 0)
            self.assertEqual(manifest["rejected_count"], 1)
            rejection = json.loads(
                (output_dir / "rejections.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(rejection["cause"], "llm_response_schema_error")
            self.assertEqual(
                rejection["details"]["schema_reason"],
                "invalid_expected_state",
            )
            self.assertEqual(
                rejection["details"]["schema_detail"],
                "expected_state_check_type_invalid",
            )
            self.assertEqual(rejection["details"]["lineage"]["batch_index"], 1)
            self.assertEqual(
                rejection["details"]["lineage"]["requested_candidate_count"],
                2,
            )
            release_report = json.loads(
                (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(
                release_report["release_completeness"]["decision"]["status"],
                "passed",
            )
            self.assertEqual(
                release_report["decisions"]["dataset_release"]["status"],
                "ineligible",
            )

            persisted = "\n".join(
                (output_dir / artifact_name).read_text(encoding="utf-8")
                for artifact_name in artifact_names
            )
            forbidden_values = (
                raw_response_marker,
                "Generate exactly the requested number of executable task contracts",
                "Alice Zhang",
                "alice.zhang@example.test",
                "Authorization",
                "Bearer ",
                api_key_marker,
                str(Path.cwd()),
                "provider task contract must contain exact supported keys",
            )
            for value in forbidden_values:
                with self.subTest(forbidden=value):
                    self.assertNotIn(value, persisted)

    def test_llm_success_path_uses_focused_grounded_prompt_contract(self) -> None:
        from main import main
        from synthesis.llm import LLMGenerationResult

        api_key_marker = "provider-success-api-key-marker"
        prompts: list[str] = []

        def grounded_generation(self, prompt: str, *, role: str) -> LLMGenerationResult:
            prompts.append(prompt)
            payload = json.loads(prompt)
            prefix = payload["batch_context"]["candidate_id_prefix"]
            count = payload["requested_candidate_count"]
            task_type = payload["task_types"][0]
            entries = payload["grounding_context"]["contacts"]
            records = []
            for index in range(count):
                entry = entries[index % len(entries)]
                records.append(
                    {
                        "candidate_id": f"{prefix}task_{index:02d}",
                        "instruction": (
                            "Find the email address for "
                            f"{entry['primary_arguments']['name']}."
                        ),
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
                        "final_answer_contains": entry["observation"]["email"],
                        "expected_state": [],
                    }
                )
            return LLMGenerationResult(
                content={"task_contracts": records},
                lineage={
                    "role": role,
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "test-config-hash",
                    "retry_count": 0,
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "llm-success"
            profile_path = root / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": "run_profile_v3",
                        "profile_id": "contacts_llm_success_test",
                        "dataset_version": "dataset_contacts_llm_success_test",
                        "profile_purpose": "benchmark",
                        "seed": {
                            "seed_id": "seed_contacts_llm_success_test",
                            "domain": "contacts_fixture",
                            "description": "Generate grounded executable contacts tasks.",
                            "task_taxonomy": ["contact_lookup", "contact_followup"],
                        },
                        "generation": {
                            "mode": "llm",
                            "target_candidate_count": 2,
                            "context_policy": "synthetic_fixture",
                        },
                        "features": {},
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "main.py",
                "--run-profile",
                str(profile_path),
                "--use-llm",
                "--write-evaluation-report",
                "--write-profile-decision-report",
                "--write-dataset-release-report",
                "--write-release-quality-audit",
                "--output-dir",
                str(output_dir),
            ]
            env = {
                "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                "AGENT_DATA_API_KEY": api_key_marker,
                "AGENT_DATA_LLM_MODEL": "test-generator",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(sys, "argv", argv),
                patch(
                    "synthesis.llm.OpenAICompatibleClient.generate_json",
                    new=grounded_generation,
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["rejected_count"], 0)

            self.assertEqual(len(prompts), 1)
            payload = json.loads(prompts[0])
            self.assertEqual(
                [item["task_type"] for item in payload["task_types"]],
                ["contact_lookup"],
            )
            self.assertEqual(
                [
                    item["task_type"]
                    for item in payload["output_contract"]["task_type_contracts"]
                ],
                ["contact_lookup"],
            )
            self.assertEqual(len(payload["grounding_context"]["contacts"]), 2)
            diversity = payload["diversity_contract"]
            self.assertEqual(diversity["excluded_instructions"], [])
            self.assertIn("do not repeat or paraphrase", diversity["rule"])

            samples = [
                json.loads(line)
                for line in (output_dir / "samples.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(samples), 2)
            for sample in samples:
                self.assertTrue(
                    sample["sample_id"].startswith("sample_contacts_b001_"),
                    sample["sample_id"],
                )
                generator_lineage = sample["lineage"]["generator"]
                self.assertEqual(generator_lineage["excluded_instruction_count"], 0)
                self.assertNotIn("excluded_instructions", generator_lineage)

            persisted = "\n".join(
                (output_dir / artifact_name).read_text(encoding="utf-8")
                for artifact_name in (
                    "samples.jsonl",
                    "rejections.jsonl",
                    "manifest.json",
                    "quality_report.json",
                    "evaluation_report.json",
                    "profile_decision_report.json",
                    "dataset_release_report.json",
                    "release_quality_audit.json",
                )
            )
            for forbidden in (
                api_key_marker,
                "Bearer ",
                "Authorization",
                "Generate exactly the requested number",
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, persisted)


if __name__ == "__main__":
    unittest.main()
