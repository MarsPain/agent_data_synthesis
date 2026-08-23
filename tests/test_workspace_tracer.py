from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkspaceTracerProofTest(unittest.TestCase):
    def test_mutation_admission_accounting_allows_pre_admission_rejection(
        self,
    ) -> None:
        from synthesis.mutation_admission_reporting import (
            build_mutation_admission_report,
        )
        from synthesis.workspace_tracer import (
            WorkspaceTracerProofError,
            _validate_mutation_admission_terminal_accounting,
            build_workspace_tracer_proof,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = build_workspace_tracer_proof(Path(tmpdir) / "proof")
            positive = proof_path.parent / "positive"
            sample = json.loads(
                next(
                    line
                    for line in (positive / "samples.jsonl").read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line
                )
            )
            rejection = {
                "candidate_id": "workspace_tasks_pre_admission_rejection",
                "cause": "domain_plan_membership_rejected",
                "details": {},
            }
            report = build_mutation_admission_report(
                dataset_version="workspace_tracer_test_dataset",
                samples=[sample],
                rejections=[rejection],
            )

        _validate_mutation_admission_terminal_accounting(
            report=report,
            dataset_version="workspace_tracer_test_dataset",
            samples=[sample],
            rejections=[rejection],
        )
        report["counts"]["missing_evidence"] = 0
        with self.assertRaisesRegex(WorkspaceTracerProofError, "mutation_admission_report"):
            _validate_mutation_admission_terminal_accounting(
                report=report,
                dataset_version="workspace_tracer_test_dataset",
                samples=[sample],
                rejections=[rejection],
            )

    def test_live_terminal_assignment_lineage_binds_validated_rejection(self) -> None:
        from synthesis.workspace_tracer import (
            WorkspaceTracerProofError,
            _live_terminal_assignment_lineage_by_id,
        )

        accepted_assignment = {
            "assignment_id": "coverage_assignment_accepted",
            "plan_id": "workspace_plan",
        }
        rejected_assignment = {
            "assignment_id": "coverage_assignment_rejected",
            "plan_id": "workspace_plan",
        }
        samples = [
            {"workspace_evidence": {"assignment": accepted_assignment}},
        ]
        rejections = [
            {
                "details": {
                    "workspace_evidence": {"assignment": rejected_assignment}
                }
            }
        ]
        validated_attempts = [
            {
                "assignment_id": "coverage_assignment_accepted",
                "assignment_lineage": accepted_assignment,
                "outcome": "validated",
            },
            {
                "assignment_id": "coverage_assignment_rejected",
                "assignment_lineage": rejected_assignment,
                "outcome": "validated",
            },
        ]

        bindings = _live_terminal_assignment_lineage_by_id(
            samples=samples,
            rejections=rejections,
            provider_attempts=validated_attempts,
        )

        self.assertEqual(
            bindings,
            {
                "coverage_assignment_accepted": accepted_assignment,
                "coverage_assignment_rejected": rejected_assignment,
            },
        )
        with self.assertRaisesRegex(WorkspaceTracerProofError, "provider_contract"):
            _live_terminal_assignment_lineage_by_id(
                samples=samples,
                rejections=[],
                provider_attempts=validated_attempts,
            )

    def test_offline_proof_builds_and_verifies_from_root_only(self) -> None:
        from synthesis.workspace_tracer import (
            build_workspace_tracer_proof,
            verify_workspace_tracer_proof,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_root = build_workspace_tracer_proof(Path(tmpdir) / "proof")

            first = verify_workspace_tracer_proof(proof_root)
            second = verify_workspace_tracer_proof(proof_root)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "passed")
        self.assertEqual(
            first["summary"],
            {
                "effective_qualification": "release_candidate",
                "publishable": False,
                "training_recommended": False,
                "publishable_conformance": "passed",
                "training_recommended_conformance": "passed",
            },
        )
        self.assertTrue(first["proof_identity"].startswith("sha256:"))

    def test_declared_artifact_mutation_fails_closed_without_default_repair(self) -> None:
        from synthesis.workspace_tracer import (
            build_workspace_tracer_proof,
            verify_workspace_tracer_proof,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_root = build_workspace_tracer_proof(Path(tmpdir) / "proof")
            root = json.loads(proof_root.read_text(encoding="utf-8"))
            artifact = next(
                item for item in root["artifacts"] if item["artifact_kind"] == "plan"
            )
            artifact_path = proof_root.parent / artifact["path"]
            original = artifact_path.read_bytes()
            artifact_path.write_bytes(original + b"\n")

            result = verify_workspace_tracer_proof(proof_root)

        self.assertEqual(result["status"], "failed")
        self.assertIn("artifact_integrity", result["reason_codes"])

    def test_negative_case_mutates_one_fact_and_preserves_positive_bytes(self) -> None:
        from synthesis.workspace_tracer import (
            build_workspace_tracer_proof,
            verify_workspace_tracer_proof,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_root = build_workspace_tracer_proof(Path(tmpdir) / "proof")
            root = json.loads(proof_root.read_text(encoding="utf-8"))
            case = next(
                item
                for item in root["proof_cases"]
                if item["case_id"] == "plan_identity"
            )
            case_path = proof_root.parent / case["path"]
            positive_path = proof_root.parent / case["positive_path"]
            positive_before = positive_path.read_bytes()
            case_before = json.loads(case_path.read_text(encoding="utf-8"))

            result = verify_workspace_tracer_proof(proof_root)

            self.assertEqual(positive_path.read_bytes(), positive_before)
            self.assertEqual(
                json.loads(case_path.read_text(encoding="utf-8")),
                case_before,
            )

        self.assertEqual(result["status"], "passed")
        expected_cases = {
            "plan_identity": ("insufficient_evidence", "evidence_identity_mismatch"),
            "provider_contract": ("rejected", "provider_contract_rejected"),
            "mutation_safety": ("rejected", "mutation_admission_failed"),
            "execution_evidence": ("insufficient_evidence", "evidence_identity_mismatch"),
            "coverage_evaluation": (
                "insufficient_evidence",
                "workspace_coverage_evidence_incomplete",
            ),
            "run_completeness": ("insufficient_evidence", "evidence_incomplete"),
            "artifact_integrity": ("failed", "artifact_integrity"),
            "publishability": ("denied", "publishability_scope_mismatch"),
            "fixture_isolation": ("denied", "non_qualifying_evidence_class"),
            "training_arms": ("invalid_experiment", "record_count_tolerance_exceeded"),
            "evaluation_leakage": ("invalid_experiment", "leakage_overlap_unresolved"),
            "meaningful_gain": ("no_detected_meaningful_gain", "no_detected_meaningful_gain"),
            "cumulative_dependency": (
                "insufficient_evidence",
                "qualification_dependency_invalidated",
            ),
        }
        self.assertEqual(
            {
                case["case_id"]: (case["observed_status"], case["reason_code"])
                for case in result["proof_cases"]
            },
            expected_cases,
        )
        self.assertTrue(
            all(case_result["status"] == "passed" for case_result in result["proof_cases"])
        )

    def test_verifier_cli_uses_the_proof_root_as_its_only_input(self) -> None:
        from synthesis.workspace_tracer import build_workspace_tracer_proof

        script = Path(__file__).resolve().parents[1] / "scripts" / "verify_workspace_tracer_proof.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_root = build_workspace_tracer_proof(Path(tmpdir) / "proof")
            completed = subprocess.run(
                [sys.executable, str(script), str(proof_root.parent)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["summary"]["effective_qualification"], "release_candidate")


if __name__ == "__main__":
    unittest.main()
