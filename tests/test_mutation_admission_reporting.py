from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class MutationAdmissionReportingTest(unittest.TestCase):
    def test_v4_run_writes_deterministic_report_and_hash_bound_manifest(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/workspace-comments-shadow.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_foundation_pipeline(
                root / "first",
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
            )
            second = run_foundation_pipeline(
                root / "second",
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
            )

            assert first.mutation_admission_report_path is not None
            assert second.mutation_admission_report_path is not None
            report_bytes = first.mutation_admission_report_path.read_bytes()
            self.assertEqual(
                report_bytes,
                second.mutation_admission_report_path.read_bytes(),
            )
            report = json.loads(report_bytes)
            self.assertEqual(
                report["schema_version"],
                "mutation_admission_report_v1",
            )
            self.assertEqual(report["dataset_version"], profile.dataset_version)
            self.assertEqual(
                set(report["dimensions"]),
                {
                    "action",
                    "domain",
                    "model_independence",
                    "provenance",
                    "provider_outcome",
                    "reason",
                    "task_type",
                    "verdict",
                },
            )
            self.assertEqual(
                sum(row["count"] for row in report["dimensions"]["domain"]),
                report["counts"]["evidence_records"],
            )
            self.assertEqual(report["counts"]["missing_evidence"], 0)
            self.assertIn(
                "workspace_comment_add",
                {
                    row["value"]
                    for row in report["dimensions"]["action"]
                },
            )
            self.assertIn(
                "instruction",
                {
                    row["value"]
                    for row in report["dimensions"]["provenance"]
                },
            )
            self.assertNotIn(
                "not_available",
                {
                    row["value"]
                    for row in report["dimensions"]["action"]
                },
            )
            self.assertTrue(
                {
                    row["value"]
                    for row in report["dimensions"]["provenance"]
                }
                <= {
                    "instruction",
                    "tool_observation",
                    "declared_default",
                    "deterministic_derivation",
                    "not_applicable",
                    "not_available",
                }
            )
            self.assertNotIn(
                "not_available",
                {
                    row["value"]
                    for row in report["dimensions"]["provenance"]
                },
            )

            samples = self._read_jsonl(first.samples_path)
            rejections = self._read_jsonl(first.rejections_path)
            for sample in samples:
                evidence = sample["mutation_admission"]
                if evidence["classification"] == "read_only":
                    self.assertNotIn("semantic_verdict", evidence)
                else:
                    self.assertIn("semantic_verdict", evidence)
            for rejection in rejections:
                if (
                    rejection["task"]["difficulty"].get("state_changes", 0)
                    > 0
                ):
                    self.assertIn(
                        "mutation_admission",
                        rejection["details"],
                    )

            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "dataset_manifest_v2")
            self.assertEqual(
                manifest["sample_contract_versions"],
                ["dataset_sample_v2"],
            )
            self.assertEqual(
                manifest["admission_contract_versions"]["evidence"],
                ["mutation_admission_evidence_v2"],
            )
            self.assertEqual(
                manifest["admission_contract_versions"]["authorization"],
                ["mutation_authorization_record_v1"],
            )
            self.assertEqual(
                manifest["admission_contract_versions"]["semantic_verdict"],
                ["semantic_mutation_verdict_v1"],
            )
            self.assertEqual(
                manifest["artifacts"]["mutation_admission_report"],
                "mutation_admission_report.json",
            )
            for key, path in (
                ("samples", first.samples_path),
                ("rejections", first.rejections_path),
                (
                    "mutation_admission_report",
                    first.mutation_admission_report_path,
                ),
            ):
                binding = manifest["admission_artifacts"][key]
                content = path.read_bytes()
                self.assertEqual(binding["path"], path.name)
                self.assertEqual(binding["byte_count"], len(content))
                self.assertEqual(
                    binding["sha256"],
                    "sha256:" + hashlib.sha256(content).hexdigest(),
                )

    def test_historical_profile_keeps_readable_v1_manifest_without_admission_report(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/profile-local-workspace-tasks.json")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "dataset_manifest_v1")
            self.assertIsNone(result.mutation_admission_report_path)
            self.assertNotIn("admission_artifacts", manifest)
            self.assertNotIn("admission_contract_versions", manifest)

    def test_offline_validation_passes_independent_enforce_artifacts(self) -> None:
        from synthesis.mutation_admission_release import (
            verify_mutation_safe_manifest,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_enforce_profile(Path(tmpdir))

            verification = verify_mutation_safe_manifest(result.manifest_path)

            self.assertEqual(verification["status"], "passed")
            self.assertEqual(verification["reasons"], [])

    def test_offline_validation_rejects_controlled_evidence_failures(self) -> None:
        from synthesis.mutation_admission_release import (
            verify_mutation_safe_manifest,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = self._run_enforce_profile(root / "original")
            cases = {
                "shadow": "enforce mode",
                "disabled": "enforce mode",
                "diagnostic_only": "diagnostic-only",
                "missing": "missing mutation admission evidence",
                "invalid": "invalid mutation admission evidence",
                "legacy_contract": "unsupported evidence contract",
                "misclassified": "state-changing sample is classified read-only",
                "raw_material": "prohibited retained material",
                "unreferenced_observation": "prohibited retained material",
                "unreferenced_observation_event": "prohibited retained material",
                "tampered": "admission artifact hash mismatch",
                "tampered_report": "report content mismatch",
            }
            for case_name, expected_reason in cases.items():
                with self.subTest(case_name=case_name):
                    case_dir = root / case_name
                    shutil.copytree(original.manifest_path.parent, case_dir)
                    manifest_path = case_dir / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    if case_name in {"shadow", "disabled"}:
                        manifest["run_profile"]["mutation_admission"]["mode"] = (
                            case_name
                        )
                        if case_name == "disabled":
                            manifest["run_profile"]["mutation_admission"].pop(
                                "judge"
                            )
                        self._write_json(manifest_path, manifest)
                    elif case_name == "tampered_report":
                        report_path = (
                            case_dir / "mutation_admission_report.json"
                        )
                        report = json.loads(
                            report_path.read_text(encoding="utf-8")
                        )
                        report["dimensions"]["domain"][0]["value"] = (
                            "fabricated_domain"
                        )
                        self._write_json(report_path, report)
                        content = report_path.read_bytes()
                        binding = manifest["admission_artifacts"][
                            "mutation_admission_report"
                        ]
                        binding["sha256"] = (
                            "sha256:" + hashlib.sha256(content).hexdigest()
                        )
                        binding["byte_count"] = len(content)
                        self._write_json(manifest_path, manifest)
                    else:
                        samples_path = case_dir / "samples.jsonl"
                        samples = self._read_jsonl(samples_path)
                        mutation_index = next(
                            index
                            for index, sample in enumerate(samples)
                            if sample["mutation_admission"]["classification"]
                            == "state_changing"
                        )
                        evidence = samples[mutation_index]["mutation_admission"]
                        if case_name == "diagnostic_only":
                            evidence["diagnostic_only"] = True
                        elif case_name == "missing":
                            samples[mutation_index].pop("mutation_admission")
                        elif case_name == "invalid":
                            evidence["semantic_verdict"]["verdict"] = "approved"
                        elif case_name == "legacy_contract":
                            evidence["schema_version"] = (
                                "mutation_admission_evidence_v1"
                            )
                            evidence.pop("admission_outcome")
                            evidence.pop("judge_call")
                            evidence.pop("model_independence")
                        elif case_name == "misclassified":
                            read_only = next(
                                sample
                                for sample in samples
                                if sample["mutation_admission"][
                                    "classification"
                                ]
                                == "read_only"
                            )
                            samples[mutation_index]["mutation_admission"] = (
                                read_only["mutation_admission"]
                            )
                        elif case_name == "raw_material":
                            samples[mutation_index]["raw_prompt"] = (
                                "retained judge prompt"
                            )
                        elif case_name == "unreferenced_observation":
                            samples[mutation_index]["observation"] = {
                                "unreferenced": "payload"
                            }
                        elif case_name == "unreferenced_observation_event":
                            samples[mutation_index]["trajectory"].append(
                                {
                                    "type": "observation",
                                    "tool": "unreferenced_tool",
                                    "observation": {
                                        "unreferenced": "payload"
                                    },
                                }
                            )
                        elif case_name == "tampered":
                            evidence["hashes"]["policy"] = "sha256:" + "f" * 64
                        self._write_jsonl(samples_path, samples)
                        if case_name != "tampered":
                            content = samples_path.read_bytes()
                            binding = manifest["admission_artifacts"]["samples"]
                            binding["sha256"] = (
                                "sha256:" + hashlib.sha256(content).hexdigest()
                            )
                            binding["byte_count"] = len(content)
                            self._write_json(manifest_path, manifest)

                    verification = verify_mutation_safe_manifest(manifest_path)

                    self.assertEqual(verification["status"], "failed")
                    self.assertIn(
                        expected_reason,
                        " ".join(verification["reasons"]),
                    )

    def test_historical_30_v5_is_not_rewritten_or_grandfathered(self) -> None:
        from synthesis.mutation_admission_release import (
            verify_mutation_safe_manifest,
        )

        campaign = Path("artifacts/representative-campaign-30-v5")
        manifest_path = campaign / "workspace" / "manifest.json"
        before = self._tree_hash(campaign)

        verification = verify_mutation_safe_manifest(manifest_path)

        self.assertEqual(verification["status"], "failed")
        self.assertIn(
            "historical dataset_manifest_v1 cannot certify mutation safety",
            verification["reasons"],
        )
        self.assertEqual(self._tree_hash(campaign), before)

    def test_retained_material_scan_rejects_each_prohibited_material_class(
        self,
    ) -> None:
        from synthesis.mutation_admission_reporting import (
            validate_retained_admission_material,
        )

        prohibited = (
            {"raw_prompt": "judge input"},
            {"raw_response": "judge output"},
            {"chain_of_thought": "private reasoning"},
            {"credentials": {"token": "value"}},
            {"headers": {"x-request-id": "value"}},
            {"observation": {"unreferenced": "value"}},
            {"metadata": "Authorization: bearer value"},
        )
        for material in prohibited:
            with self.subTest(material=material):
                with self.assertRaisesRegex(ValueError, "prohibited"):
                    validate_retained_admission_material(material)

    @staticmethod
    def _run_enforce_profile(output_dir: Path):
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import (
            RunProfileMutationAdmission,
            load_run_profile,
        )

        shadow = load_run_profile(
            Path("tests/fixtures/run_profiles/workspace-comments-shadow.json")
        )
        profile = replace(
            shadow,
            profile_purpose="release_candidate",
            mutation_admission=RunProfileMutationAdmission(mode="enforce"),
        )
        metadata = profile.sanitized_metadata()
        metadata["mutation_admission"]["judge"] = {
            "role": "mutation_admission_judge",
            "provider": "openai_compatible",
            "model": "independent-release-judge",
            "timeout_seconds": 5.0,
            "max_retries": 1,
        }
        return run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            seed_override=profile.seed,
            run_profile=profile,
            run_profile_metadata=metadata,
        )

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    @staticmethod
    def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_json(path: Path, record: dict[str, object]) -> None:
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _tree_hash(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
