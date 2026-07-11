from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class DatasetReleasePackTest(unittest.TestCase):
    def test_build_release_pack_records_hashes_and_release_evidence(self) -> None:
        from synthesis.release_pack import build_dataset_release_pack

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = _write_release_artifacts(output_dir)

            pack = build_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )

            self.assertEqual(pack["schema_version"], "dataset_release_pack_v1")
            self.assertEqual(pack["dataset_version"], "dataset_release")
            self.assertTrue(
                str(pack["release_id"]).startswith("dataset_release:sha256:")
            )
            self.assertEqual(pack["profile"]["profile_id"], "release_profile")
            self.assertEqual(pack["profile"]["profile_purpose"], "release_candidate")
            self.assertEqual(pack["evidence"]["accepted"], 6)
            self.assertEqual(pack["evidence"]["dataset_release_status"], "passed")
            self.assertEqual(pack["verification"]["status"], "passed")
            self.assertEqual(
                sorted(pack["artifacts"]),
                [
                    "dataset_release_report",
                    "evaluation_report",
                    "manifest",
                    "profile_decision_report",
                    "quality_report",
                    "rejections",
                    "samples",
                ],
            )
            for artifact in pack["artifacts"].values():
                self.assertRegex(artifact["sha256"], r"^sha256:[0-9a-f]{64}$")
                self.assertGreaterEqual(artifact["byte_count"], 0)
                self.assertTrue(artifact["path"])

            second_pack = build_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )
            self.assertEqual(pack["release_id"], second_pack["release_id"])

    def test_build_and_write_release_pack_reject_noncanonical_manifest_bytes(
        self,
    ) -> None:
        from synthesis.release_pack import (
            build_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            for operation in ("build", "write"):
                with self.subTest(operation=operation):
                    output_dir = base_dir / operation
                    output_dir.mkdir()
                    paths = _write_release_artifacts(output_dir)
                    manifest = json.loads(
                        paths["manifest"].read_text(encoding="utf-8")
                    )
                    paths["manifest"].write_text(
                        json.dumps(manifest),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        ValueError,
                        "canonical dataset manifest serialization",
                    ):
                        if operation == "build":
                            build_dataset_release_pack(
                                manifest_path=paths["manifest"],
                                dataset_release_report_path=paths[
                                    "dataset_release_report"
                                ],
                            )
                        else:
                            write_dataset_release_pack(
                                manifest_path=paths["manifest"],
                                dataset_release_report_path=paths[
                                    "dataset_release_report"
                                ],
                            )

    def test_release_pack_contract_rejects_malformed_records(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_dataset_release_pack_record,
        )

        valid = _valid_release_pack_record()
        invalid_records = (
            ("verification.status", {"verification": {"status": "maybe"}}),
            (
                "artifacts.samples.sha256",
                {"artifacts": {"samples": {"sha256": "not-a-hash"}}},
            ),
            (
                "artifacts.samples.byte_count",
                {"artifacts": {"samples": {"byte_count": -1}}},
            ),
            ("artifacts.samples.path", {"artifacts": {"samples": {"path": ""}}}),
            ("evidence", {"evidence": []}),
        )
        for expected_message, override in invalid_records:
            with self.subTest(expected_message=expected_message):
                record = _deep_merge(valid, override)

                with self.assertRaisesRegex(
                    ContractValidationError,
                    expected_message,
                ):
                    validate_dataset_release_pack_record(record)

    def test_verify_release_pack_passes_then_detects_artifact_drift(self) -> None:
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = _write_release_artifacts(output_dir)
            pack_path = write_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )

            passed = verify_dataset_release_pack(pack_path)
            self.assertEqual(passed["verification"]["status"], "passed")

            paths["samples"].write_text('{"changed": true}\n', encoding="utf-8")

            failed = verify_dataset_release_pack(pack_path)
            self.assertEqual(failed["verification"]["status"], "failed")
            self.assertIn("hash mismatch", " ".join(failed["verification"]["reasons"]))

    def test_verify_release_pack_allows_post_pack_review_resolution_attachment(
        self,
    ) -> None:
        from synthesis.datasets import attach_review_resolution_report_to_manifest
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = _write_release_artifacts(output_dir)
            pack_path = write_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )
            pack_bytes = pack_path.read_bytes()
            report_path = output_dir / "review_resolution_report.json"
            _write_json(report_path, _review_resolution_report())

            attach_review_resolution_report_to_manifest(
                manifest_path=paths["manifest"],
                report_path=report_path,
            )
            result = verify_dataset_release_pack(pack_path)

            self.assertEqual(result["verification"]["status"], "passed")
            self.assertIn(
                "controlled post-pack review resolution attachment",
                " ".join(result["verification"]["reasons"]),
            )
            self.assertNotIn(
                "all referenced artifacts match recorded hashes",
                result["verification"]["reasons"],
            )
            self.assertEqual(pack_path.read_bytes(), pack_bytes)

    def test_verify_release_pack_rejects_uncontrolled_manifest_drift_after_pack(
        self,
    ) -> None:
        from synthesis.datasets import attach_review_resolution_report_to_manifest
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            cases = {
                "missing": "invalid_review_report",
                "malformed": "invalid_review_report",
                "deeply_nested": "invalid_review_report",
                "dataset_mismatch": "review_dataset_mismatch",
                "other_drift": "uncontrolled_manifest_drift",
            }
            for case_name, expected_reason in cases.items():
                with self.subTest(case_name=case_name):
                    output_dir = base_dir / case_name
                    output_dir.mkdir()
                    paths = _write_release_artifacts(output_dir)
                    pack_path = write_dataset_release_pack(
                        manifest_path=paths["manifest"],
                        dataset_release_report_path=paths["dataset_release_report"],
                    )
                    report_path = output_dir / "review_resolution_report.json"
                    if case_name == "malformed":
                        report_path.write_text("{bad json", encoding="utf-8")
                    elif case_name == "deeply_nested":
                        report_path.write_text(
                            '{"nested":' * 2000 + "null" + "}" * 2000,
                            encoding="utf-8",
                        )
                    elif case_name != "missing":
                        report = _review_resolution_report()
                        if case_name == "dataset_mismatch":
                            report["dataset_version"] = "dataset_other_release"
                        _write_json(report_path, report)
                    attach_review_resolution_report_to_manifest(
                        manifest_path=paths["manifest"],
                        report_path=report_path,
                    )
                    if case_name == "other_drift":
                        manifest = json.loads(
                            paths["manifest"].read_text(encoding="utf-8")
                        )
                        manifest["accepted_count"] = 7
                        _write_json(paths["manifest"], manifest)

                    result = verify_dataset_release_pack(pack_path)

                    self.assertEqual(result["verification"]["status"], "failed")
                    self.assertIn(
                        expected_reason,
                        result["verification"]["reasons"],
                    )

    def test_verify_release_pack_detects_dataset_version_mismatch(self) -> None:
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = _write_release_artifacts(output_dir)
            pack_path = write_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["dataset_version"] = "dataset_changed"
            paths["manifest"].write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            result = verify_dataset_release_pack(pack_path)

            self.assertEqual(result["verification"]["status"], "failed")
            self.assertIn(
                "dataset version mismatch",
                " ".join(result["verification"]["reasons"]),
            )

    def test_verify_release_pack_detects_non_passed_release_evidence(self) -> None:
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = _write_release_artifacts(output_dir)
            pack_path = write_dataset_release_pack(
                manifest_path=paths["manifest"],
                dataset_release_report_path=paths["dataset_release_report"],
            )
            release_report = json.loads(
                paths["dataset_release_report"].read_text(encoding="utf-8")
            )
            release_report["decisions"]["dataset_release"]["status"] = "failed"
            paths["dataset_release_report"].write_text(
                json.dumps(release_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            result = verify_dataset_release_pack(pack_path)

            self.assertEqual(result["verification"]["status"], "failed")
            self.assertIn(
                "dataset release status is not passed",
                " ".join(result["verification"]["reasons"]),
            )

    def test_verify_release_pack_reports_insufficient_evidence_for_malformed_pack(
        self,
    ) -> None:
        from synthesis.release_pack import verify_dataset_release_pack

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir) / "dataset_release_pack.json"
            pack_path.write_text("{bad json", encoding="utf-8")

            result = verify_dataset_release_pack(pack_path)

            self.assertEqual(
                result["verification"]["status"],
                "insufficient_evidence",
            )


def _write_release_artifacts(output_dir: Path) -> dict[str, Path]:
    artifacts = {
        "samples": output_dir / "samples.jsonl",
        "rejections": output_dir / "rejections.jsonl",
        "manifest": output_dir / "manifest.json",
        "quality_report": output_dir / "quality_report.json",
        "evaluation_report": output_dir / "evaluation_report.json",
        "profile_decision_report": output_dir / "profile_decision_report.json",
        "dataset_release_report": output_dir / "dataset_release_report.json",
    }
    artifacts["samples"].write_text('{"sample_id": "sample_1"}\n', encoding="utf-8")
    artifacts["rejections"].write_text('{"candidate_id": "rejected_1"}\n', encoding="utf-8")
    _write_json(artifacts["manifest"], _manifest())
    _write_json(artifacts["quality_report"], _quality_report())
    _write_json(artifacts["evaluation_report"], _evaluation_report())
    _write_json(artifacts["profile_decision_report"], _profile_decision_report())
    _write_json(artifacts["dataset_release_report"], _dataset_release_report())
    return artifacts


def _write_json(path: Path, record: dict[str, object]) -> None:
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_release",
        "parent_dataset_version": None,
        "accepted_count": 6,
        "rejected_count": 1,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
            "evaluation_report": "evaluation_report.json",
            "profile_decision_report": "profile_decision_report.json",
            "dataset_release_report": "dataset_release_report.json",
        },
        "quality": {"success_rate": 1.0, "executable_rate": 1.0},
        "environment_versions": ["contacts_fixture_v1"],
        "tool_versions": ["contacts_tools_v1"],
        "verifier_versions": ["exact_answer_v1"],
        "generator_config_hashes": ["sha256:" + "b" * 64],
        "rejection_causes": {},
        "run_profile": {**_profile(), "enabled_features": []},
    }


def _quality_report() -> dict[str, object]:
    return {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_release",
        "counts": {"total": 7, "accepted": 6, "rejected": 1},
        "rates": {"success_rate": 1.0, "executable_rate": 1.0},
        "rejection_causes": {},
        "slices": {},
    }


def _evaluation_report() -> dict[str, object]:
    return {
        "schema_version": "evaluation_report_v1",
        "dataset_version": "dataset_release",
        "profile": _profile(),
        "decision": {
            "status": "passed",
            "reasons": ["held-out evaluation passed"],
            "triggered_by": ["pass_rate"],
        },
    }


def _profile_decision_report() -> dict[str, object]:
    return {
        "schema_version": "profile_decision_report_v1",
        "dataset_version": "dataset_release",
        "profile": _profile(),
        "decisions": {
            "async_orchestration": {
                "status": "defer",
                "reasons": ["small synchronous run"],
                "triggered_by": [],
            },
            "semantic_duplicate_detection": {
                "status": "defer",
                "reasons": ["below volume threshold"],
                "triggered_by": [],
            },
            "profile_promotion": {
                "status": "passed",
                "reasons": ["profile promotion passed"],
                "triggered_by": ["mvp_quality_floor"],
            },
        },
    }


def _dataset_release_report() -> dict[str, object]:
    return {
        "schema_version": "dataset_release_report_v1",
        "dataset_version": "dataset_release",
        "profile": _profile(),
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "evaluation_report_path": "evaluation_report.json",
            "profile_decision_report_path": "profile_decision_report.json",
        },
        "observed": {
            "accepted": 6,
            "rejected": 1,
            "success_rate": 1.0,
            "executable_rate": 1.0,
            "source_policy_rejection_rate": 0.0,
            "heldout_status": "passed",
            "profile_promotion_status": "passed",
            "async_orchestration_status": "defer",
            "semantic_duplicate_detection_status": "defer",
        },
        "release_completeness": {
            "thresholds": {
                "min_accepted_samples": 5,
                "max_rejection_rate": 0.2,
                "required_task_types": [
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ],
                "required_tool_combinations": [
                    "lookup_contact_email",
                    "lookup_contact_email+record_contact_followup",
                ],
            },
            "observed": {
                "accepted": 6,
                "rejected": 1,
                "rejection_rate": 1 / 7,
                "task_types": [
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ],
                "tool_combinations": [
                    "lookup_contact_email",
                    "lookup_contact_email+record_contact_followup",
                ],
            },
            "decision": {
                "status": "passed",
                "reasons": ["release completeness passed"],
                "triggered_by": [
                    "accepted",
                    "rejection_rate",
                    "task_type_coverage",
                    "tool_combination_coverage",
                ],
            },
        },
        "decisions": {
            "dataset_release": {
                "status": "passed",
                "reasons": ["release admission passed"],
                "triggered_by": [
                    "profile_promotion",
                    "heldout_evaluation",
                    "source_policy",
                ],
            }
        },
        "release_artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
            "evaluation_report": "evaluation_report.json",
            "profile_decision_report": "profile_decision_report.json",
        },
    }


def _review_resolution_report() -> dict[str, object]:
    return {
        "schema_version": "review_resolution_report_v1",
        "dataset_version": "dataset_release",
        "inputs": {
            "release_review_queue_path": "release_review_queue.jsonl",
            "review_decisions_path": "review_decisions.jsonl",
        },
        "counts": {
            "queued": 1,
            "resolved": 1,
            "pending": 0,
            "accepted_risk": 1,
            "confirmed_issue": 0,
            "needs_follow_up": 0,
            "review_minutes": 2,
        },
        "decision": {
            "status": "reviewed",
            "reasons": ["all queued review items have decisions"],
            "triggered_by": ["review_decisions"],
        },
    }


def _profile() -> dict[str, object]:
    return {
        "schema_version": "run_profile_v1",
        "profile_id": "release_profile",
        "generation_mode": "foundation_fixture",
        "profile_purpose": "release_candidate",
        "target_candidate_count": None,
        "config_hash": "sha256:" + "a" * 64,
    }


def _valid_release_pack_record() -> dict[str, object]:
    artifact = {
        "path": "samples.jsonl",
        "sha256": "sha256:" + "1" * 64,
        "byte_count": 1,
    }
    return {
        "schema_version": "dataset_release_pack_v1",
        "dataset_version": "dataset_release",
        "release_id": "dataset_release:sha256:" + "2" * 64,
        "profile": _profile(),
        "inputs": {
            "manifest_path": "manifest.json",
            "dataset_release_report_path": "dataset_release_report.json",
        },
        "artifacts": {
            key: dict(artifact, path=f"{key}.json")
            for key in (
                "manifest",
                "samples",
                "rejections",
                "quality_report",
                "evaluation_report",
                "profile_decision_report",
                "dataset_release_report",
            )
        },
        "evidence": {
            "accepted": 6,
            "rejected": 1,
            "heldout_status": "passed",
            "profile_promotion_status": "passed",
            "dataset_release_status": "passed",
            "release_completeness_status": "passed",
            "async_orchestration_status": "defer",
            "semantic_duplicate_detection_status": "defer",
        },
        "verification": {
            "status": "passed",
            "reasons": ["all required artifacts are present"],
        },
    }


def _deep_merge(
    base: dict[str, object],
    override: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


if __name__ == "__main__":
    unittest.main()
