from __future__ import annotations

import json
import unittest

from tests.test_mutation_activation import (
    _case_indexes,
    _evaluate_predictions,
    _prediction_matrix,
    _reviewed_corpus,
)


class RepresentativeActivationGateTest(unittest.TestCase):
    def test_passing_evidence_activates_framework_but_not_dataset_release(self) -> None:
        from synthesis.representative_activation_gate import (
            build_representative_activation_gate,
            validate_representative_activation_gate,
        )

        report = build_representative_activation_gate(
            activation_report=_passing_activation_report(),
            representative_evidence=_representative_evidence(),
            representative_lineage=_representative_lineage(),
            mutation_verifications=_passing_mutation_verifications(),
            protected_baseline_hash="sha256:" + "a" * 64,
            protected_current_hash="sha256:" + "a" * 64,
            artifact_hashes=_artifact_hashes(),
            costs={
                "activation_judge_usd": 12.5,
                "representative_pipeline_usd": 18.75,
            },
            limitations=[
                "Framework activation does not establish dataset release readiness."
            ],
        )

        validate_representative_activation_gate(report)
        self.assertEqual(report["decision"], "activate")
        self.assertEqual(report["decision_reasons"], [])
        self.assertEqual(
            report["readiness"],
            {
                "framework_activation": "activated",
                "dataset_release": "not_established",
            },
        )
        self.assertEqual(report["operations"]["failures"], 0)
        self.assertEqual(report["operations"]["costs_usd"]["total"], 31.25)
        self.assertEqual(
            set(report["model_lineage"]),
            {"generator_model_hash", "judge_configuration"},
        )

    def test_any_failed_gate_is_no_go_and_cannot_claim_mutation_readiness(self) -> None:
        from synthesis.representative_activation_gate import (
            build_representative_activation_gate,
        )

        corpus = _reviewed_corpus()
        predictions = _prediction_matrix(corpus)
        for case_index in _case_indexes(corpus, ground_truth="supported"):
            for run in predictions:
                run[case_index] = "unsupported"
        activation = _evaluate_predictions(corpus, predictions)
        verifications = _passing_mutation_verifications()
        verifications["workspace_tasks_fixture"] = {
            "status": "failed",
            "reasons": ["mutation admission report content mismatch"],
        }

        report = build_representative_activation_gate(
            activation_report=activation,
            representative_evidence=_representative_evidence(),
            representative_lineage=_representative_lineage(),
            mutation_verifications=verifications,
            protected_baseline_hash="sha256:" + "a" * 64,
            protected_current_hash="sha256:" + "b" * 64,
            artifact_hashes=_artifact_hashes(),
            costs={
                "activation_judge_usd": 0.0,
                "representative_pipeline_usd": 0.0,
            },
            limitations=["Independent provider evidence remains incomplete."],
        )

        self.assertEqual(report["decision"], "no_go")
        self.assertEqual(report["readiness"]["framework_activation"], "not_activated")
        self.assertEqual(report["readiness"]["dataset_release"], "not_established")
        self.assertIn("activation_evaluation_no_go", report["decision_reasons"])
        self.assertIn(
            "representative_mutation_verification_failed",
            report["decision_reasons"],
        )
        self.assertIn(
            "protected_baseline_changed",
            report["decision_reasons"],
        )

    def test_offline_validation_rejects_controlled_tampered_variants(self) -> None:
        from synthesis.representative_activation_gate import (
            build_representative_activation_gate,
            validate_representative_activation_gate,
            verify_representative_activation_gate,
        )

        report = build_representative_activation_gate(
            activation_report=_passing_activation_report(),
            representative_evidence=_representative_evidence(),
            representative_lineage=_representative_lineage(),
            mutation_verifications=_passing_mutation_verifications(),
            protected_baseline_hash="sha256:" + "a" * 64,
            protected_current_hash="sha256:" + "a" * 64,
            artifact_hashes=_artifact_hashes(),
            costs={
                "activation_judge_usd": 1.0,
                "representative_pipeline_usd": 2.0,
            },
            limitations=["Dataset release still requires its own release pack."],
        )

        for path, value in (
            (("decision",), "no_go"),
            (("activation", "thresholds", "supported_precision_min"), 0.5),
            (("protected_baseline", "current_hash"), "sha256:" + "b" * 64),
            (("artifacts", "activation_report"), "sha256:" + "c" * 64),
        ):
            with self.subTest(path=path):
                tampered = json.loads(json.dumps(report))
                target = tampered
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    validate_representative_activation_gate(tampered)

        verification = verify_representative_activation_gate(
            report=report,
            activation_report=_passing_activation_report(),
            representative_evidence=_representative_evidence(),
            representative_lineage=_representative_lineage(),
            mutation_verifications=_passing_mutation_verifications(),
            protected_current_hash="sha256:" + "a" * 64,
            artifact_hashes=_artifact_hashes(),
        )
        self.assertEqual(verification["status"], "passed")

        tampered_evidence = _representative_evidence()
        tampered_evidence["domains"][0]["observed"][
            "heldout_status"
        ] = "failed"
        rejected = verify_representative_activation_gate(
            report=report,
            activation_report=_passing_activation_report(),
            representative_evidence=tampered_evidence,
            representative_lineage=_representative_lineage(),
            mutation_verifications=_passing_mutation_verifications(),
            protected_current_hash="sha256:" + "a" * 64,
            artifact_hashes=_artifact_hashes(),
        )
        self.assertEqual(rejected["status"], "failed")


def _passing_activation_report() -> dict[str, object]:
    corpus = _reviewed_corpus()
    return _evaluate_predictions(corpus, _prediction_matrix(corpus))


def _representative_evidence() -> dict[str, object]:
    return {
        "schema_version": "representative_scale_evidence_v1",
        "campaign_id": "scale_campaign:sha256:" + "1" * 64,
        "domains": [
            {
                "domain_id": domain,
                "classification": "representative",
                "artifacts": {
                    key: {
                        "path": filename,
                        "sha256": str(index + 1) * 64,
                    }
                    for index, (key, filename) in enumerate(
                        {
                            "manifest": "manifest.json",
                            "quality_report": "quality_report.json",
                            "evaluation_report": "evaluation_report.json",
                            "profile_decision_report": (
                                "profile_decision_report.json"
                            ),
                            "dataset_release_report": (
                                "dataset_release_report.json"
                            ),
                            "release_quality_audit": (
                                "release_quality_audit.json"
                            ),
                        }.items()
                    )
                },
                "observed": {
                    "heldout_status": "passed",
                    "mvp_quality_floor_status": "passed",
                    "dataset_release_status": "ineligible",
                },
            }
            for domain in (
                "contacts_fixture",
                "mobile_messages_fixture",
                "workspace_tasks_fixture",
            )
        ],
    }


def _passing_mutation_verifications() -> dict[str, object]:
    return {
        domain: {"status": "passed", "reasons": []}
        for domain in (
            "contacts_fixture",
            "mobile_messages_fixture",
            "workspace_tasks_fixture",
        )
    }


def _representative_lineage() -> dict[str, object]:
    return {
        domain: {
            "profile_id": f"{domain}_representative_enforce",
            "dataset_version": f"dataset_{domain}_representative_enforce",
            "profile_config_hash": "sha256:" + "7" * 64,
            "generator_model_hash": "sha256:" + "8" * 64,
            "judge_model_hash": "sha256:" + "9" * 64,
            "judge_configuration_hash": "sha256:" + "a" * 64,
            "model_independence": "independent",
        }
        for domain in (
            "contacts_fixture",
            "mobile_messages_fixture",
            "workspace_tasks_fixture",
        )
    }


def _artifact_hashes() -> dict[str, str]:
    return {
        "activation_report": "sha256:" + "2" * 64,
        "campaign": "sha256:" + "3" * 64,
        "contacts_fixture_manifest": "sha256:" + "4" * 64,
        "mobile_messages_fixture_manifest": "sha256:" + "5" * 64,
        "workspace_tasks_fixture_manifest": "sha256:" + "6" * 64,
    }


if __name__ == "__main__":
    unittest.main()
