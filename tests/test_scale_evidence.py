from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROFILE_BY_DOMAIN = {
    "contacts_fixture": "tests/fixtures/run_profiles/foundation-release-candidate.json",
    "mobile_messages_fixture": "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
    "workspace_tasks_fixture": "tests/fixtures/run_profiles/workspace-tasks-release-candidate.json",
}


def write_domain_artifacts(
    root: Path,
    *,
    domain_id: str,
    dataset_version: str,
    generation_mode: str,
    total_candidates: int,
    async_status: str = "defer",
    semantic_status: str = "defer",
) -> Path:
    """Write contract-valid existing artifacts and return their directory."""
    output_dir = root / domain_id
    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--run-profile",
            PROFILE_BY_DOMAIN[domain_id],
            "--dataset-version",
            dataset_version,
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
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)

    generation_contract = {
        "spec_version": "domain_generation_spec_v1",
        "context_policy": "synthetic_fixture",
        "target_candidate_count": total_candidates,
        "generated_candidate_count": total_candidates,
        "target_fulfilled": True,
        "representative_eligible": True,
        "reason_codes": [],
        "grounding_context_hash": "sha256:" + "0" * 64,
    }
    for name in (
        "manifest.json",
        "evaluation_report.json",
        "profile_decision_report.json",
        "dataset_release_report.json",
        "release_quality_audit.json",
    ):
        path = output_dir / name
        record = json.loads(path.read_text(encoding="utf-8"))
        profile_key = "run_profile" if name == "manifest.json" else "profile"
        if record.get(profile_key) is not None:
            record[profile_key]["generation_mode"] = generation_mode
            if generation_mode == "llm":
                record[profile_key]["schema_version"] = "run_profile_v3"
                record[profile_key]["profile_purpose"] = "benchmark"
                record[profile_key]["target_candidate_count"] = total_candidates
                record[profile_key]["generation_contract"] = generation_contract
        if name == "manifest.json":
            record["accepted_count"] = total_candidates
            record["rejected_count"] = 0
        if name == "profile_decision_report.json":
            record["observed"].update(
                total_candidates=total_candidates,
                accepted=total_candidates,
                rejected=0,
            )
            record["decisions"]["async_orchestration"]["status"] = async_status
            record["decisions"]["semantic_duplicate_detection"]["status"] = semantic_status
        if name == "dataset_release_report.json" and generation_mode == "llm":
            record["decisions"]["dataset_release"]["status"] = "insufficient_evidence"
        if name in {"dataset_release_report.json", "release_quality_audit.json"}:
            record["observed"].update(accepted=total_candidates, rejected=0)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_dir


class ScaleEvidenceTest(unittest.TestCase):
    def test_scale_evidence_cli_prints_one_path_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for domain in PROFILE_BY_DOMAIN:
                write_domain_artifacts(
                    root,
                    domain_id=domain,
                    dataset_version=f"dataset_{domain}",
                    generation_mode="deterministic_scale_probe",
                    total_candidates=100,
                    async_status="activate",
                )
            campaign_path = root / "campaign.json"
            campaign_path.write_text(json.dumps(_campaign_record()), encoding="utf-8")
            output_path = root / "representative_scale_evidence.json"

            result = subprocess.run(
                [sys.executable, "scripts/write_representative_scale_evidence.py", "--campaign", str(campaign_path), "--output", str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, f"representative_scale_evidence={output_path}\n")
            self.assertEqual(json.loads(output_path.read_text())["decision"]["recommendation"], "expand_representative_evidence")

    def test_load_campaign_resolves_relative_paths_and_rejects_duplicates(self) -> None:
        from synthesis.contracts import ContractValidationError
        from synthesis.scale_evidence import load_scale_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            campaign_path = root / "campaign.json"
            campaign = _campaign_record()
            campaign_path.write_text(json.dumps(campaign), encoding="utf-8")

            loaded = load_scale_campaign(campaign_path)

            self.assertEqual(loaded.runs[0].artifact_dir, root / "contacts_fixture")
            campaign["runs"][1]["domain_id"] = "contacts_fixture"
            campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                load_scale_campaign(campaign_path)

    def test_fixture_modes_are_diagnostic_even_at_scale(self) -> None:
        from synthesis.scale_evidence import DIAGNOSTIC_GENERATION_MODES, classify_run

        for mode in DIAGNOSTIC_GENERATION_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(classify_run({"valid": True, "generation_mode": mode}), "diagnostic_only")
        self.assertEqual(classify_run({"valid": True, "generation_mode": "llm"}), "insufficient_evidence")
        generation_contract = {
            "spec_version": "domain_generation_spec_v1",
            "context_policy": "synthetic_fixture",
            "target_candidate_count": 100,
            "generated_candidate_count": 100,
            "target_fulfilled": True,
            "representative_eligible": True,
            "reason_codes": [],
            "grounding_context_hash": "sha256:" + "0" * 64,
        }
        self.assertEqual(
            classify_run({
                "valid": True,
                "generation_mode": "llm",
                "generation_contract": generation_contract,
                "schema_version": "run_profile_v3",
                "profile_purpose": "benchmark",
                "target_candidate_count": 100,
            }),
            "representative",
        )
        self.assertEqual(
            classify_run(
                {
                    "valid": True,
                    "generation_mode": "llm",
                    "generation_contract": generation_contract,
                    "schema_version": "run_profile_v3",
                    "profile_purpose": "benchmark",
                    "target_candidate_count": 100,
                    "coverage_selected": True,
                    "coverage_fulfillment_status": "insufficient_evidence",
                }
            ),
            "insufficient_evidence",
        )
        self.assertEqual(
            classify_run(
                {
                    "valid": True,
                    "generation_mode": "llm",
                    "generation_contract": generation_contract,
                    "schema_version": "run_profile_v3",
                    "profile_purpose": "benchmark",
                    "target_candidate_count": 100,
                    "coverage_selected": True,
                    "coverage_fulfillment_status": "passed",
                }
            ),
            "representative",
        )
        self.assertEqual(
            classify_run(
                {
                    "valid": True,
                    "generation_mode": "llm",
                    "generation_contract": generation_contract,
                    "schema_version": "run_profile_v4",
                    "profile_purpose": "benchmark",
                    "target_candidate_count": 100,
                    "mutation_admission": {
                        "mode": "enforce",
                        "judge": {
                            "role": "mutation_admission_judge",
                            "provider": "openai_compatible",
                            "model": "independent-judge-model",
                            "timeout_seconds": 30.0,
                            "max_retries": 1,
                        },
                    },
                }
            ),
            "representative",
        )
        self.assertEqual(
            classify_run(
                {
                    "valid": True,
                    "generation_mode": "llm",
                    "generation_contract": generation_contract,
                    "schema_version": "run_profile_v4",
                    "profile_purpose": "benchmark",
                    "target_candidate_count": 100,
                    "mutation_admission": {"mode": "shadow"},
                }
            ),
            "insufficient_evidence",
        )
        for key in ("target_fulfilled", "representative_eligible"):
            invalid = dict(generation_contract)
            invalid[key] = False
            self.assertEqual(
                classify_run({"valid": True, "generation_mode": "llm", "generation_contract": invalid, "schema_version": "run_profile_v3", "profile_purpose": "benchmark", "target_candidate_count": 100}),
                "insufficient_evidence",
            )
        self.assertEqual(
            classify_run({"valid": True, "generation_mode": "llm", "generation_contract": generation_contract, "schema_version": "run_profile_v1", "profile_purpose": "benchmark", "target_candidate_count": 100}),
            "insufficient_evidence",
        )
        self.assertEqual(classify_run({"valid": False, "generation_mode": "llm"}), "insufficient_evidence")

    def test_builds_stable_diagnostic_report_without_persisting_input_paths(self) -> None:
        from synthesis.contracts import validate_representative_scale_evidence_record
        from synthesis.scale_evidence import load_scale_campaign, build_representative_scale_evidence

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for domain in PROFILE_BY_DOMAIN:
                write_domain_artifacts(
                    root,
                    domain_id=domain,
                    dataset_version=f"dataset_{domain}",
                    generation_mode="deterministic_scale_probe",
                    total_candidates=100,
                    async_status="activate",
                    semantic_status="activate",
                )
            campaign_path = root / "campaign.json"
            campaign_path.write_text(json.dumps(_campaign_record()), encoding="utf-8")

            first = build_representative_scale_evidence(load_scale_campaign(campaign_path))
            second = build_representative_scale_evidence(load_scale_campaign(campaign_path))

            validate_representative_scale_evidence_record(first)
            self.assertEqual(first, second)
            self.assertEqual(first["decision"]["recommendation"], "expand_representative_evidence")
            self.assertEqual(first["triggered_signals"], ["async_orchestration", "semantic_duplicate_detection"])
            serialized = json.dumps(first)
            self.assertNotIn(str(root), serialized)
            self.assertTrue(all(domain["classification"] == "diagnostic_only" for domain in first["domains"]))

    def test_representative_semantic_signal_outranks_async(self) -> None:
        from synthesis.scale_evidence import build_representative_scale_evidence, load_scale_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for domain in PROFILE_BY_DOMAIN:
                write_domain_artifacts(
                    root,
                    domain_id=domain,
                    dataset_version=f"dataset_{domain}",
                    generation_mode="llm",
                    total_candidates=100,
                    async_status="activate",
                    semantic_status="activate" if domain == "contacts_fixture" else "defer",
                )
            campaign_path = root / "campaign.json"
            campaign_path.write_text(json.dumps(_campaign_record()), encoding="utf-8")

            evidence = build_representative_scale_evidence(load_scale_campaign(campaign_path))

            self.assertEqual(evidence["decision"]["recommendation"], "activate_semantic_duplicate_detection")

    def test_quality_and_confirmed_review_issues_outrank_activation(self) -> None:
        from synthesis.scale_evidence import select_recommendation

        base = {
            "classification": "representative",
            "observed": {
                "heldout_status": "passed",
                "mvp_quality_floor_status": "passed",
            },
            "signals": ["async_orchestration", "semantic_duplicate_detection"],
            "_confirmed_issue_count": 0,
        }
        for override in (
            {"observed": {"heldout_status": "failed", "mvp_quality_floor_status": "passed"}},
            {"_confirmed_issue_count": 1},
        ):
            with self.subTest(override=override):
                summary = {**base, **override}
                decision = select_recommendation([summary])
                self.assertEqual(decision["recommendation"], "improve_generation_or_verification")

    def test_missing_required_artifact_becomes_insufficient_evidence(self) -> None:
        from synthesis.scale_evidence import build_representative_scale_evidence, load_scale_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for domain in PROFILE_BY_DOMAIN:
                directory = write_domain_artifacts(
                    root,
                    domain_id=domain,
                    dataset_version=f"dataset_{domain}",
                    generation_mode="llm",
                    total_candidates=10,
                )
                if domain == "contacts_fixture":
                    (directory / "evaluation_report.json").unlink()
            campaign_path = root / "campaign.json"
            campaign_path.write_text(json.dumps(_campaign_record()), encoding="utf-8")

            evidence = build_representative_scale_evidence(load_scale_campaign(campaign_path))

            self.assertEqual(evidence["domains"][0]["classification"], "insufficient_evidence")
            self.assertEqual(evidence["decision"]["recommendation"], "expand_representative_evidence")

    def test_selected_coverage_requires_bound_evidence_artifacts(self) -> None:
        from synthesis.scale_evidence import (
            build_representative_scale_evidence,
            load_scale_campaign,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for domain in PROFILE_BY_DOMAIN:
                directory = write_domain_artifacts(
                    root,
                    domain_id=domain,
                    dataset_version=f"dataset_{domain}",
                    generation_mode="llm",
                    total_candidates=10,
                )
                if domain == "contacts_fixture":
                    manifest_path = directory / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    manifest["run_profile"]["coverage_profile"] = {
                        "profile_id": "contacts_smoke",
                        "version": "contacts_smoke_v1",
                        "target_accepted_sample_count": 10,
                    }
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    summary = _fulfilled_coverage_summary()
                    quality_path = directory / "quality_report.json"
                    quality = json.loads(
                        quality_path.read_text(encoding="utf-8")
                    )
                    quality["coverage"] = summary
                    quality_path.write_text(
                        json.dumps(quality, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    profile_path = directory / "profile_decision_report.json"
                    profile = json.loads(
                        profile_path.read_text(encoding="utf-8")
                    )
                    profile["coverage"] = summary
                    profile["decisions"]["coverage_fulfillment"] = {
                        "status": "passed",
                        "reasons": [
                            "mandatory coverage fulfillment passed"
                        ],
                        "triggered_by": ["coverage_fulfillment"],
                    }
                    profile_path.write_text(
                        json.dumps(profile, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
            campaign_path = root / "campaign.json"
            campaign_path.write_text(
                json.dumps(_campaign_record()),
                encoding="utf-8",
            )

            evidence = build_representative_scale_evidence(
                load_scale_campaign(campaign_path)
            )

            self.assertEqual(
                evidence["domains"][0]["classification"],
                "insufficient_evidence",
            )
            self.assertEqual(
                evidence["decision"]["recommendation"],
                "expand_representative_evidence",
            )


def _campaign_record() -> dict[str, object]:
    return {
        "schema_version": "representative_scale_campaign_v1",
        "campaign_label": "three_domain_scale",
        "runs": [
            {"domain_id": "contacts_fixture", "artifact_dir": "contacts_fixture"},
            {"domain_id": "mobile_messages_fixture", "artifact_dir": "mobile_messages_fixture"},
            {"domain_id": "workspace_tasks_fixture", "artifact_dir": "workspace_tasks_fixture"},
        ],
    }


def _fulfilled_coverage_summary() -> dict[str, object]:
    evidence_hash = "sha256:" + "a" * 64
    return {
        "schema_version": "coverage_quality_summary_v1",
        "evidence_id": "coverage_evidence_" + "a" * 16,
        "evidence_hash": evidence_hash,
        "counts": {
            "target_accepted": 10,
            "attempt_ceiling": 10,
            "attempted": 10,
            "generated": 10,
            "accepted": 10,
            "rejected": 0,
            "remaining": 0,
            "unassigned_accepted": 0,
            "unassigned_rejected": 0,
        },
        "distributions": {
            "structural_families": {
                "distinct_count": 1,
                "largest_family_count": 10,
                "largest_family_share": 1.0,
                "accepted_by_cell": {"contacts.lookup_by_name": 10},
            },
            "grounding_reuse": {
                "distinct_grounding_count": 1,
                "max_accepted_per_grounding": 10,
                "reuse_count_distribution": {"10": 1},
            },
            "difficulty": {
                "accepted_by_level": {"medium": 10},
            },
            "exact_duplicates": {"count": 0, "rate": 0.0},
        },
        "fulfillment": {
            "status": "fulfilled",
            "mandatory_fulfilled": True,
            "target_fulfilled": True,
            "reasons": [],
        },
    }


if __name__ == "__main__":
    unittest.main()
