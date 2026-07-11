from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def write_verified_release_pack(root: Path) -> Path:
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
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return root / "dataset_release_pack.json"


class DownstreamBenchmarkTest(unittest.TestCase):
    def test_bundle_and_import_clis_preserve_release_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pack_path = write_verified_release_pack(root)
            before = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
            bundle_path = root / "downstream_benchmark_bundle.json"
            bundle_run = subprocess.run(
                [sys.executable, "scripts/write_downstream_benchmark_bundle.py", "--release-pack", str(pack_path), "--benchmark-suite-id", "external_agent_tasks_v1", "--benchmark-suite-version", "external_agent_tasks_v1", "--output", str(bundle_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(bundle_run.returncode, 0, bundle_run.stdout + bundle_run.stderr)
            self.assertEqual(bundle_run.stdout, f"downstream_benchmark_bundle={bundle_path}\n")
            bundle = json.loads(bundle_path.read_text())
            observation_path = root / "observation.json"
            observation_path.write_text(json.dumps(_observation(bundle)), encoding="utf-8")
            result_path = root / "downstream_benchmark_result.json"

            import_run = subprocess.run(
                [sys.executable, "scripts/import_downstream_benchmark_result.py", "--bundle", str(bundle_path), "--observation", str(observation_path), "--output", str(result_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(import_run.returncode, 0, import_run.stdout + import_run.stderr)
            self.assertEqual(import_run.stdout, f"downstream_benchmark_result={result_path}\n")
            self.assertEqual(json.loads(result_path.read_text())["decision"]["status"], "improved")
            for name, content in before.items():
                self.assertEqual((root / name).read_bytes(), content)

    def test_import_cli_exits_one_for_insufficient_evidence_without_traceback(self) -> None:
        from synthesis.downstream_benchmark import BenchmarkMetric, BenchmarkProtocol, build_downstream_benchmark_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bundle = build_downstream_benchmark_bundle(
                release_pack_path=write_verified_release_pack(root),
                protocol=_protocol(BenchmarkMetric, BenchmarkProtocol),
            )
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            observation_path = root / "bad.json"
            observation_path.write_text('{"credentials":"secret"}', encoding="utf-8")
            output_path = root / "result.json"

            result = subprocess.run(
                [sys.executable, "scripts/import_downstream_benchmark_result.py", "--bundle", str(bundle_path), "--observation", str(observation_path), "--output", str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, f"downstream_benchmark_result={output_path}\n")
            self.assertNotIn("secret", output_path.read_text())

    def test_build_bundle_requires_verified_pack_and_is_deterministic(self) -> None:
        from synthesis.contracts import validate_downstream_benchmark_bundle_record
        from synthesis.downstream_benchmark import (
            BenchmarkMetric,
            BenchmarkProtocol,
            build_downstream_benchmark_bundle,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pack_path = write_verified_release_pack(root)
            protocol = _protocol(BenchmarkMetric, BenchmarkProtocol)

            first = build_downstream_benchmark_bundle(release_pack_path=pack_path, protocol=protocol)
            second = build_downstream_benchmark_bundle(release_pack_path=pack_path, protocol=protocol)

            validate_downstream_benchmark_bundle_record(first)
            self.assertEqual(first, second)
            self.assertEqual(first["release"]["pack_path"], "dataset_release_pack.json")
            self.assertNotIn(str(root), json.dumps(first))
            (root / "samples.jsonl").write_text('{"drift":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verification must pass"):
                build_downstream_benchmark_bundle(release_pack_path=pack_path, protocol=protocol)

    def test_result_calculates_improved_equal_regressed_and_zero_baseline(self) -> None:
        from synthesis.downstream_benchmark import (
            BenchmarkMetric,
            BenchmarkProtocol,
            build_downstream_benchmark_bundle,
            build_downstream_benchmark_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_downstream_benchmark_bundle(
                release_pack_path=write_verified_release_pack(Path(tmpdir)),
                protocol=_protocol(BenchmarkMetric, BenchmarkProtocol),
            )
            cases = (
                (0.61, 0.67, "improved", 0.06 / 0.61),
                (0.61, 0.61, "no_detected_improvement", 0.0),
                (0.67, 0.61, "no_detected_improvement", -0.06 / 0.67),
                (0.0, 0.1, "improved", None),
            )
            for baseline, treatment, status, relative in cases:
                with self.subTest(baseline=baseline, treatment=treatment):
                    result = build_downstream_benchmark_result(
                        bundle=bundle,
                        observation=_observation(bundle, baseline, treatment),
                    )
                    self.assertAlmostEqual(result["comparison"]["absolute_delta"], treatment - baseline)
                    if relative is None:
                        self.assertIsNone(result["comparison"]["relative_delta"])
                    else:
                        self.assertAlmostEqual(result["comparison"]["relative_delta"], relative)
                    self.assertEqual(result["decision"]["status"], status)

    def test_invalid_observations_are_sanitized_with_fixed_reason(self) -> None:
        from synthesis.contracts import validate_downstream_benchmark_result_record
        from synthesis.downstream_benchmark import (
            BenchmarkMetric,
            BenchmarkProtocol,
            build_downstream_benchmark_bundle,
            build_downstream_benchmark_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_downstream_benchmark_bundle(
                release_pack_path=write_verified_release_pack(Path(tmpdir)),
                protocol=_protocol(BenchmarkMetric, BenchmarkProtocol),
            )
            cases = (
                ({**_observation(bundle), "benchmark_id": "downstream_benchmark:sha256:" + "0" * 64}, "benchmark_identity_mismatch"),
                ({**_observation(bundle), "evaluation_seed_ids": ["seed_01", "seed_01"]}, "evaluation_identity_invalid"),
                ({**_observation(bundle), "arms": {"baseline": {"model_alias": "baseline", "metrics": {"task_success_rate": 2.0}}, "treatment": {"model_alias": "treatment", "metrics": {"task_success_rate": 0.7}}}}, "metric_contract_invalid"),
                ({**_observation(bundle), "credentials": {"token": "secret"}}, "observation_unreadable_or_malformed"),
            )
            for observation, reason in cases:
                with self.subTest(reason=reason):
                    result = build_downstream_benchmark_result(bundle=bundle, observation=observation)
                    validate_downstream_benchmark_result_record(result)
                    self.assertEqual(result["decision"], {"status": "insufficient_evidence", "reasons": [reason]})
                    self.assertIsNone(result["arms"])
                    self.assertNotIn("secret", json.dumps(result))

    def test_import_malformed_json_writes_sanitized_result(self) -> None:
        from synthesis.downstream_benchmark import (
            BenchmarkMetric,
            BenchmarkProtocol,
            build_downstream_benchmark_bundle,
            import_downstream_benchmark_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bundle = build_downstream_benchmark_bundle(
                release_pack_path=write_verified_release_pack(root),
                protocol=_protocol(BenchmarkMetric, BenchmarkProtocol),
            )
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            observation_path = root / "observation.json"
            observation_path.write_text("{bad", encoding="utf-8")
            output_path = root / "result.json"

            import_downstream_benchmark_result(
                bundle_path=bundle_path,
                observation_path=observation_path,
                output_path=output_path,
            )

            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"]["reasons"], ["observation_unreadable_or_malformed"])


def _protocol(metric_type, protocol_type):
    return protocol_type(
        protocol_version="external_agent_benchmark_v1",
        benchmark_suite_id="external_agent_tasks_v1",
        benchmark_suite_version="external_agent_tasks_v1",
        primary_metric="task_success_rate",
        metrics=(metric_type("task_success_rate", "higher_is_better", 0.0, 1.0),),
    )


def _observation(bundle: dict[str, object], baseline: float = 0.61, treatment: float = 0.67) -> dict[str, object]:
    release = bundle["release"]
    protocol = bundle["protocol"]
    return {
        "schema_version": "downstream_benchmark_observation_v1",
        "benchmark_id": bundle["benchmark_id"],
        "dataset_version": bundle["dataset_version"],
        "release_id": release["release_id"],
        "release_pack_sha256": release["pack_sha256"],
        "benchmark_suite_id": protocol["benchmark_suite_id"],
        "benchmark_suite_version": protocol["benchmark_suite_version"],
        "evaluation_seed_ids": ["seed_01", "seed_02"],
        "evaluation_sample_count": 200,
        "arms": {
            "baseline": {"model_alias": "baseline_model_a", "metrics": {"task_success_rate": baseline}},
            "treatment": {"model_alias": "treatment_model_a", "metrics": {"task_success_rate": treatment}},
        },
    }


if __name__ == "__main__":
    unittest.main()
