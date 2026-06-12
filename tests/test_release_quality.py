from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class ReleaseQualityAuditTest(unittest.TestCase):
    def test_builds_watch_audit_from_release_artifacts(self) -> None:
        from synthesis.contracts import validate_release_quality_audit_record
        from synthesis.release_quality import build_release_quality_audit

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            _write_release_artifacts(base_dir)

            audit = build_release_quality_audit(
                manifest_path=base_dir / "manifest.json",
            )

        validate_release_quality_audit_record(audit)
        self.assertEqual(audit["schema_version"], "release_quality_audit_v1")
        self.assertEqual(audit["dataset_version"], "dataset_release")
        self.assertEqual(
            audit["profile"],
            {
                "schema_version": "run_profile_v1",
                "profile_id": "release_profile",
                "generation_mode": "foundation_fixture",
                "profile_purpose": "release_candidate",
                "config_hash": "sha256:" + "a" * 64,
            },
        )
        self.assertEqual(audit["inputs"]["manifest_path"], "manifest.json")
        self.assertEqual(audit["inputs"]["samples_path"], "samples.jsonl")
        self.assertEqual(audit["observed"]["accepted"], 6)
        self.assertEqual(audit["observed"]["rejected"], 1)
        self.assertEqual(audit["observed"]["exact_duplicate_count"], 0)
        self.assertEqual(audit["observed"]["task_type_count"], 3)
        self.assertEqual(audit["observed"]["tool_combination_count"], 2)
        self.assertEqual(audit["observed"]["largest_task_type_share"], 0.5)
        self.assertEqual(audit["observed"]["largest_tool_combination_share"], 0.5)
        self.assertEqual(audit["observed"]["release_completeness_status"], "passed")
        self.assertEqual(audit["observed"]["semantic_duplicate_detection_status"], "defer")
        self.assertEqual(
            audit["thresholds"]["small_release_watch_accepted_samples"],
            8,
        )
        self.assertEqual(audit["decision"]["status"], "watch")
        self.assertIn("small_release_size", audit["decision"]["triggered_by"])
        self.assertIn("duplicate_family_risk", audit["decision"]["triggered_by"])

        risks = audit["duplicate_family_risks"]
        self.assertEqual(len(risks), 1)
        self.assertRegex(risks[0]["family_key"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            risks[0]["sample_ids"],
            ["sample_lookup_1", "sample_lookup_2", "sample_lookup_3"],
        )
        self.assertEqual(risks[0]["sample_count"], 3)
        self.assertEqual(
            risks[0]["risk_kind"],
            "same_task_type_and_tool_combination",
        )

    def test_build_returns_insufficient_evidence_when_required_artifact_missing(self) -> None:
        from synthesis.release_quality import build_release_quality_audit

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            _write_release_artifacts(base_dir)
            (base_dir / "samples.jsonl").unlink()

            audit = build_release_quality_audit(
                manifest_path=base_dir / "manifest.json",
            )

        self.assertEqual(audit["decision"]["status"], "insufficient_evidence")
        self.assertIn("samples.jsonl is missing", audit["decision"]["reasons"])

    def test_build_blocks_when_semantic_duplicate_detection_is_activated(self) -> None:
        from synthesis.release_quality import build_release_quality_audit

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            _write_release_artifacts(base_dir)
            report_path = base_dir / "profile_decision_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["decisions"]["semantic_duplicate_detection"]["status"] = "activate"
            report_path.write_text(json.dumps(report), encoding="utf-8")

            audit = build_release_quality_audit(
                manifest_path=base_dir / "manifest.json",
            )

        self.assertEqual(audit["decision"]["status"], "blocked")
        self.assertEqual(
            audit["decision"]["triggered_by"],
            ["semantic_duplicate_detection"],
        )

    def test_release_quality_audit_contract_rejects_malformed_records(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_release_quality_audit_record,
        )

        malformed_records = (
            ("decision.status", {"decision": {"status": "maybe"}}),
            ("family_key", {"duplicate_family_risks": [{"family_key": "not-a-hash"}]}),
            ("observed.accepted", {"observed": {"accepted": -1}}),
            (
                "sample_ids",
                {"duplicate_family_risks": [{"sample_ids": "sample_lookup_1"}]},
            ),
            ("inputs.samples_path", {"inputs": {"samples_path": None}}),
            ("raw secret", {"profile": {"api_key": "secret-test-key"}}),
        )
        for expected_error, override in malformed_records:
            with self.subTest(expected_error=expected_error):
                audit = _valid_release_quality_audit()
                _deep_update(audit, override)

                with self.assertRaisesRegex(ContractValidationError, expected_error):
                    validate_release_quality_audit_record(audit)

    def test_release_quality_audit_does_not_export_raw_sensitive_content(self) -> None:
        from synthesis.release_quality import build_release_quality_audit

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            _write_release_artifacts(base_dir)
            sample_path = base_dir / "samples.jsonl"
            samples = [
                json.loads(line)
                for line in sample_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            samples[0]["task"]["instruction"] = "Find Alice secret prompt"
            samples[0]["trajectory"][0]["arguments"] = {
                "name": "Alice",
                "api_key": "secret-test-key",
            }
            samples[0]["lineage"]["source_provenance"] = {
                "source_path": "/Users/H/private/contacts.json"
            }
            sample_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )

            audit = build_release_quality_audit(
                manifest_path=base_dir / "manifest.json",
            )

        exported = json.dumps(audit, sort_keys=True)
        self.assertNotIn("Find Alice secret prompt", exported)
        self.assertNotIn("secret-test-key", exported)
        self.assertNotIn("/Users/H/private/contacts.json", exported)
        self.assertNotIn("api_key", exported)
        self.assertNotIn("source_path", exported)

    def test_dataset_release_card_has_stable_headings_and_non_claims(self) -> None:
        from synthesis.release_quality import (
            build_release_quality_audit,
            render_dataset_release_card,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            _write_release_artifacts(base_dir)
            audit = build_release_quality_audit(
                manifest_path=base_dir / "manifest.json",
            )
            card = render_dataset_release_card(
                manifest_path=base_dir / "manifest.json",
                release_quality_audit=audit,
            )

        for heading in (
            "# Dataset Release Card",
            "## Identity",
            "## Release Decision",
            "## Artifact Integrity",
            "## Quality Evidence",
            "## Coverage and Diversity",
            "## Known Limitations",
            "## Non-Claims",
        ):
            self.assertIn(heading, card)
        self.assertIn("dataset_release_status: passed", card)
        self.assertIn("release_quality_audit_status: watch", card)
        self.assertIn("release pack: not generated", card)
        self.assertIn("does not prove downstream model quality", card)
        self.assertNotIn("Find Alice", card)
        self.assertNotIn(str(Path.home()), card)


def _write_release_artifacts(base_dir: Path) -> None:
    samples = [
        _sample("sample_lookup_1", "lookup_contact_email", ["lookup_contact_email"], "email_exact"),
        _sample("sample_lookup_2", "lookup_contact_email", ["lookup_contact_email"], "email_exact"),
        _sample("sample_lookup_3", "lookup_contact_email", ["lookup_contact_email"], "email_exact"),
        _sample(
            "sample_followup_1",
            "contact_followup",
            ["lookup_contact_email", "record_contact_followup"],
            "followup_created",
        ),
        _sample(
            "sample_followup_2",
            "contact_followup",
            ["lookup_contact_email", "record_contact_followup"],
            "followup_created",
        ),
        _sample(
            "sample_branch_1",
            "contact_branch_fallback",
            ["lookup_contact_email"],
            "branch_selected",
        ),
    ]
    (base_dir / "samples.jsonl").write_text(
        "\n".join(json.dumps(sample) for sample in samples) + "\n",
        encoding="utf-8",
    )
    (base_dir / "rejections.jsonl").write_text(
        json.dumps(
            {
                "candidate_id": "candidate_rejected",
                "cause": "verification_failed",
                "task": {
                    "instruction": "Rejected task text",
                    "constraints": {"task_type": "lookup_contact_email"},
                    "difficulty": {"level": "easy"},
                },
                "details": {"message": "sanitized"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for filename, payload in {
        "manifest.json": _manifest(),
        "quality_report.json": _quality_report(),
        "evaluation_report.json": _evaluation_report(),
        "profile_decision_report.json": _profile_decision_report(),
        "dataset_release_report.json": _dataset_release_report(),
    }.items():
        (base_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _sample(
    sample_id: str,
    task_type: str,
    tools: list[str],
    verifier_id: str,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "dataset_version": "dataset_release",
        "tools": [{"name": tool, "version": "v1"} for tool in tools],
        "task": {
            "instruction": f"Find Alice for {sample_id}",
            "constraints": {"task_type": task_type},
            "difficulty": {"level": "easy"},
        },
        "trajectory": [
            {"type": "action", "tool": tool, "arguments": {"name": "Alice"}}
            for tool in tools
        ],
        "verifier": {"id": verifier_id, "version": "v1", "checks": []},
        "lineage": {},
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_release",
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
        "environment_versions": [],
        "tool_versions": [],
        "verifier_versions": [],
        "generator_config_hashes": [],
        "rejection_causes": {},
        "run_profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "release_profile",
            "generation_mode": "foundation_fixture",
            "profile_purpose": "release_candidate",
            "config_hash": "sha256:" + "a" * 64,
            "raw_path": "/Users/H/private/profile.json",
        },
    }


def _quality_report() -> dict[str, object]:
    return {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_release",
        "counts": {"accepted": 6, "rejected": 1},
        "rates": {"success_rate": 1.0, "executable_rate": 1.0},
        "rejection_causes": {},
        "slices": {
            "task_type": {
                "lookup_contact_email": {"accepted": 3, "rejected": 0},
                "contact_followup": {"accepted": 2, "rejected": 0},
                "contact_branch_fallback": {"accepted": 1, "rejected": 0},
            },
            "tool_combination": {
                "lookup_contact_email": {"accepted": 3, "rejected": 0},
                "lookup_contact_email > record_contact_followup": {
                    "accepted": 2,
                    "rejected": 0,
                },
            },
        },
    }


def _evaluation_report() -> dict[str, object]:
    return {
        "schema_version": "evaluation_report_v1",
        "dataset_version": "dataset_release",
        "decision": {"status": "passed", "reasons": ["ok"], "triggered_by": []},
    }


def _profile_decision_report() -> dict[str, object]:
    return {
        "schema_version": "profile_decision_report_v1",
        "dataset_version": "dataset_release",
        "profile": None,
        "observed": {
            "exact_duplicate_count": 0,
            "exact_duplicate_rate": 0.0,
        },
        "decisions": {
            "semantic_duplicate_detection": {
                "status": "defer",
                "reasons": ["below threshold"],
                "triggered_by": [],
            },
            "profile_promotion": {
                "status": "passed",
                "reasons": ["ok"],
                "triggered_by": [],
            },
        },
    }


def _dataset_release_report() -> dict[str, object]:
    return {
        "schema_version": "dataset_release_report_v1",
        "dataset_version": "dataset_release",
        "profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "release_profile",
            "generation_mode": "foundation_fixture",
            "profile_purpose": "release_candidate",
            "config_hash": "sha256:" + "a" * 64,
        },
        "observed": {
            "accepted": 6,
            "rejected": 1,
            "heldout_status": "passed",
            "profile_promotion_status": "passed",
            "semantic_duplicate_detection_status": "defer",
        },
        "release_completeness": {
            "decision": {
                "status": "passed",
                "reasons": ["required task types are covered"],
                "triggered_by": [],
            }
        },
        "decisions": {
            "dataset_release": {
                "status": "passed",
                "reasons": ["release admission passed"],
                "triggered_by": [],
            }
        },
    }


def _valid_release_quality_audit() -> dict[str, object]:
    return {
        "schema_version": "release_quality_audit_v1",
        "dataset_version": "dataset_release",
        "profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "release_profile",
            "generation_mode": "foundation_fixture",
            "profile_purpose": "release_candidate",
            "config_hash": "sha256:" + "a" * 64,
        },
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "evaluation_report_path": "evaluation_report.json",
            "profile_decision_report_path": "profile_decision_report.json",
            "dataset_release_report_path": "dataset_release_report.json",
            "samples_path": "samples.jsonl",
            "rejections_path": "rejections.jsonl",
        },
        "observed": {
            "accepted": 6,
            "rejected": 1,
            "exact_duplicate_count": 0,
            "exact_duplicate_rate": 0.0,
            "task_type_count": 3,
            "tool_combination_count": 2,
            "largest_task_type_share": 0.5,
            "largest_tool_combination_share": 0.5,
            "release_completeness_status": "passed",
            "semantic_duplicate_detection_status": "defer",
        },
        "thresholds": {
            "small_release_watch_accepted_samples": 8,
            "max_largest_task_type_share": 0.75,
            "max_largest_tool_combination_share": 0.8,
            "max_exact_duplicate_rate": 0.0,
            "max_duplicate_family_size": 2,
        },
        "duplicate_family_risks": [
            {
                "family_key": "sha256:" + "b" * 64,
                "risk_kind": "same_task_type_and_tool_combination",
                "risk_level": "watch",
                "sample_ids": ["sample_lookup_1", "sample_lookup_2", "sample_lookup_3"],
                "sample_count": 3,
                "reason": (
                    "3 accepted samples share the same task type and tool combination"
                ),
            }
        ],
        "decision": {
            "status": "watch",
            "reasons": ["duplicate family risk groups require review"],
            "triggered_by": ["duplicate_family_risk"],
        },
    }


def _deep_update(target: dict[str, object], override: dict[str, object]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)  # type: ignore[arg-type]
        elif (
            key == "duplicate_family_risks"
            and isinstance(value, list)
            and isinstance(target.get(key), list)
        ):
            risks = target[key]  # type: ignore[index]
            if value and isinstance(value[0], dict) and risks and isinstance(risks[0], dict):
                _deep_update(risks[0], value[0])
            else:
                target[key] = value
        else:
            target[key] = value
