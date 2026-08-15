from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _hashes(prefix: str, count: int) -> list[str]:
    return [f"{prefix}_{index:03d}" for index in range(count)]


def _publishable_release(binding=None) -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    result = {
        "qualification": "publishable",
        "subject_id": "workspace_subject_v1",
        "subject_hash": digest,
        "release_id": "workspace_release_v1",
        "release_pack_hash": "sha256:" + "b" * 64,
        "publishability_bundle_hash": "sha256:" + "c" * 64,
        "publishability_decision_hash": "sha256:" + "d" * 64,
        "domain_pack_reference": {
            "schema_version": "domain_pack_reference_v1",
            "domain_pack_id": "workspace_tasks",
            "pack_version": "workspace_tasks_pack_v1",
            "pack_hash": "sha256:" + "9" * 64,
        },
    }
    if binding is not None:
        record = binding.to_record()
        subject = record["artifact_subject"]
        result.update(
            {
                "subject_id": subject["subject_id"],
                "subject_hash": subject["subject_hash"],
                "release_pack_hash": record["release_pack_hash"],
                "domain_pack_reference": record["domain_pack_reference"],
            }
        )
    return result


def _protocol_and_inputs(
    *,
    evidence_class: str = "external_experiment",
    publishable_release: dict[str, object] | None = None,
) -> dict[str, object]:
    from synthesis.training_recommendation import (
        build_training_recommendation_protocol,
    )

    control = _hashes("control", 20)
    release = _hashes("release", 20)
    return build_training_recommendation_protocol(
        publishable_release=(
            _publishable_release()
            if publishable_release is None
            else publishable_release
        ),
        model={"model_id": "external_model_v1", "revision": "rev_a"},
        tokenizer={"tokenizer_id": "external_tokenizer_v1", "revision": "tok_a"},
        training_system={"system_id": "external_trainer_v1"},
        training_code={"code_hash": "sha256:" + "e" * 64},
        environment={"environment_id": "external_cpu_env_v1"},
        hyperparameters={"learning_rate": "declared"},
        seed="paired-bootstrap-seed-v1",
        schedule={"schedule_id": "schedule_v1"},
        stopping_rules={"rule_id": "fixed_schedule_v1"},
        exclusion_rules={"rule_id": "predeclared_exclusions_v1"},
        common_inputs={"input_set_hash": "sha256:" + "f" * 64},
        control_manifest={"manifest_id": "control_v1", "record_hashes": control},
        release_manifest={"manifest_id": "release_v1", "record_hashes": release},
        benchmark={"suite_id": "workspace_tasks_v1", "suite_version": "1"},
        sealed_split={"split_id": "workspace_test_v1", "split_hash": "sha256:" + "1" * 64},
        ordered_task_ids=[f"task_{index:03d}" for index in range(20)],
        scoring={"scoring_code_hash": "sha256:" + "2" * 64},
        leakage_method={"method_id": "declared_external_overlap_v1", "method_hash": "sha256:" + "3" * 64},
        registration={
            "registered_at": "2026-08-15T00:00:00Z",
            "registered_before_training": True,
            "post_registration_change": False,
        },
        selection_rule={"rule_id": "registered_external_rule_v1"},
        bootstrap_seed="paired-bootstrap-seed-v1-bootstrap",
        evidence_class=evidence_class,
    )


def _evidence(
    *,
    evidence_class: str = "external_experiment",
    publishable_release: dict[str, object] | None = None,
) -> dict[str, object]:
    from synthesis.training_recommendation import (
        build_training_recommendation_arm_manifest,
        build_training_recommendation_evaluation_manifest,
        build_training_recommendation_leakage_report,
        build_training_recommendation_paired_results,
        evaluate_training_recommendation,
    )

    protocol = _protocol_and_inputs(
        evidence_class=evidence_class,
        publishable_release=publishable_release,
    )
    control = _hashes("control", 20)
    release = _hashes("release", 20)
    removed = control[:10]
    inserted = release[:10]
    baseline = build_training_recommendation_arm_manifest(
        protocol=protocol,
        arm="baseline",
        training_record_hashes=control,
        removed_control_record_hashes=removed,
        inserted_release_record_hashes=(),
    )
    treatment = build_training_recommendation_arm_manifest(
        protocol=protocol,
        arm="treatment",
        training_record_hashes=control[10:] + inserted,
        removed_control_record_hashes=removed,
        inserted_release_record_hashes=inserted,
    )
    evaluation = build_training_recommendation_evaluation_manifest(protocol=protocol)
    paired = build_training_recommendation_paired_results(
        protocol=protocol,
        evaluation=evaluation,
        baseline_successes=[0] * 10 + [1] * 10,
        treatment_successes=[1] * 20,
    )
    leakage = build_training_recommendation_leakage_report(
        protocol=protocol,
        evaluation=evaluation,
    )
    result = evaluate_training_recommendation(
        protocol=protocol,
        baseline=baseline,
        treatment=treatment,
        evaluation=evaluation,
        paired_results=paired,
        leakage=leakage,
    )
    return {
        "protocol": protocol,
        "baseline": baseline,
        "treatment": treatment,
        "evaluation": evaluation,
        "paired": paired,
        "leakage": leakage,
        "result": result,
    }


class TrainingRecommendationTest(unittest.TestCase):
    def test_valid_external_evidence_recomputes_success_and_bootstrap(self) -> None:
        evidence = _evidence()
        result = evidence["result"]
        self.assertEqual(result["decision"]["status"], "training_recommended")
        self.assertEqual(result["evaluation"]["baseline_success_rate"], 0.5)
        self.assertEqual(result["evaluation"]["treatment_success_rate"], 1.0)
        self.assertEqual(result["bootstrap"]["replicate_count"], 10_000)
        self.assertEqual(result["bootstrap"]["lower_rank"], 250)
        self.assertEqual(result["bootstrap"]["upper_rank"], 9_750)
        self.assertGreater(result["bootstrap"]["relative_lower_bound"], 0.01)

    def test_task_order_and_binary_membership_fail_as_invalid_experiment(self) -> None:
        from synthesis.training_recommendation import evaluate_training_recommendation

        evidence = _evidence()
        paired = dict(evidence["paired"])
        paired["results"] = list(paired["results"])
        paired["results"][0], paired["results"][1] = (
            paired["results"][1],
            paired["results"][0],
        )
        result = evaluate_training_recommendation(
            protocol=evidence["protocol"],
            baseline=evidence["baseline"],
            treatment=evidence["treatment"],
            evaluation=evidence["evaluation"],
            paired_results=paired,
            leakage=evidence["leakage"],
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("task_ids_reordered", result["decision"]["reason_codes"])

    def test_registered_leakage_method_is_bound_and_fixture_marker_cannot_relabel(self) -> None:
        from synthesis.training_recommendation import evaluate_training_recommendation

        evidence = _evidence()
        leakage = dict(evidence["leakage"])
        leakage["leakage_method"] = {
            "method_id": "different_leakage_method_v1",
            "method_hash": "sha256:" + "8" * 64,
        }
        result = evaluate_training_recommendation(
            protocol=evidence["protocol"],
            baseline=evidence["baseline"],
            treatment=evidence["treatment"],
            evaluation=evidence["evaluation"],
            paired_results=evidence["paired"],
            leakage=leakage,
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("leakage_identity_mismatch", result["decision"]["reason_codes"])

        fixture = _evidence(evidence_class="conformance_fixture")
        relabeled_protocol = dict(fixture["protocol"])
        relabeled_protocol["evidence_class"] = "external_experiment"
        relabeled_protocol["evidence_origin"] = "external_submitter"
        result = evaluate_training_recommendation(
            protocol=relabeled_protocol,
            baseline=fixture["baseline"],
            treatment=fixture["treatment"],
            evaluation=fixture["evaluation"],
            paired_results=fixture["paired"],
            leakage=fixture["leakage"],
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("evidence_class_mismatch", result["decision"]["reason_codes"])

    def test_count_tolerance_and_zero_baseline_are_non_qualifying(self) -> None:
        from synthesis.training_recommendation import evaluate_training_recommendation

        evidence = _evidence()
        treatment = dict(evidence["treatment"])
        treatment["replacement"] = dict(treatment["replacement"])
        treatment["replacement"]["inserted_release_record_hashes"] = _hashes("release", 20)
        treatment["replacement"]["inserted_record_count"] = 20
        result = evaluate_training_recommendation(
            protocol=evidence["protocol"],
            baseline=evidence["baseline"],
            treatment=treatment,
            evaluation=evidence["evaluation"],
            paired_results=evidence["paired"],
            leakage=evidence["leakage"],
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("record_count_tolerance_exceeded", result["decision"]["reason_codes"])

        zero = _evidence()
        paired = dict(zero["paired"])
        paired["results"] = [
            {**row, "baseline_success": 0}
            for row in paired["results"]
        ]
        result = evaluate_training_recommendation(
            protocol=zero["protocol"],
            baseline=zero["baseline"],
            treatment=zero["treatment"],
            evaluation=zero["evaluation"],
            paired_results=paired,
            leakage=zero["leakage"],
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("baseline_rate_not_positive", result["decision"]["reason_codes"])

    def test_import_reads_only_json_and_writes_sanitized_result(self) -> None:
        from synthesis.training_recommendation import (
            import_training_recommendation_evidence,
        )

        evidence = _evidence()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = {}
            for name, key in (
                ("protocol.json", "protocol"),
                ("baseline.json", "baseline"),
                ("treatment.json", "treatment"),
                ("evaluation.json", "evaluation"),
                ("paired.json", "paired"),
                ("leakage.json", "leakage"),
            ):
                path = root / name
                path.write_text(json.dumps(evidence[key]), encoding="utf-8")
                paths[key] = path
            output = root / "result.json"
            result = import_training_recommendation_evidence(
                protocol_path=paths["protocol"],
                baseline_path=paths["baseline"],
                treatment_path=paths["treatment"],
                evaluation_path=paths["evaluation"],
                paired_results_path=paths["paired"],
                leakage_path=paths["leakage"],
                output_path=output,
            )
            self.assertEqual(result["decision"]["status"], "training_recommended")
            self.assertEqual(json.loads(output.read_text())["decision"]["status"], "training_recommended")
            self.assertNotIn(str(root), output.read_text())

    def test_conformance_fixture_isolated_from_real_qualification(self) -> None:
        from tests.test_qualification import _binding

        binding = _binding()
        evidence = _evidence(
            evidence_class="conformance_fixture",
            publishable_release=_publishable_release(binding=binding),
        )
        result = evidence["result"]
        self.assertEqual(result["decision"]["status"], "protocol_conformance_passed")
        self.assertEqual(result["conformance"]["status"], "passed")
        self.assertNotEqual(result["decision"]["status"], "training_recommended")

        from synthesis.training_recommendation import build_training_recommendation_gate
        gate = build_training_recommendation_gate(binding=binding, result=result)
        self.assertEqual(gate["status"], "failed")

    def test_contract_boundary_and_qualification_gate_are_content_bound(self) -> None:
        from synthesis.contracts import (
            validate_training_experiment_evidence_manifest_record,
            validate_training_recommendation_arm_record,
            validate_training_recommendation_evaluation_record,
            validate_training_recommendation_leakage_record,
            validate_training_recommendation_paired_results_record,
            validate_training_recommendation_protocol_record,
            validate_training_recommendation_result_record,
        )
        from synthesis.training_recommendation import (
            build_training_experiment_evidence_manifest,
            build_training_recommendation_gate,
            validate_training_recommendation_gate_record,
        )
        from tests.test_qualification import _binding

        binding = _binding()
        evidence = _evidence(
            publishable_release=_publishable_release(binding=binding)
        )
        validate_training_recommendation_protocol_record(evidence["protocol"])
        validate_training_recommendation_arm_record(evidence["baseline"])
        validate_training_recommendation_arm_record(evidence["treatment"])
        validate_training_recommendation_evaluation_record(evidence["evaluation"])
        validate_training_recommendation_paired_results_record(evidence["paired"])
        validate_training_recommendation_leakage_record(evidence["leakage"])
        validate_training_recommendation_result_record(evidence["result"])

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = {}
            for name, key in (
                ("protocol.json", "protocol"),
                ("baseline.json", "baseline"),
                ("treatment.json", "treatment"),
                ("evaluation.json", "evaluation"),
                ("paired.json", "paired"),
                ("leakage.json", "leakage"),
            ):
                path = root / name
                path.write_text(json.dumps(evidence[key]), encoding="utf-8")
                paths[key] = path
            manifest = build_training_experiment_evidence_manifest(
                protocol_path=paths["protocol"],
                baseline_path=paths["baseline"],
                treatment_path=paths["treatment"],
                evaluation_path=paths["evaluation"],
                paired_results_path=paths["paired"],
                leakage_path=paths["leakage"],
            )
            validate_training_experiment_evidence_manifest_record(manifest)

        gate = build_training_recommendation_gate(
            binding=binding, result=evidence["result"]
        )
        validate_training_recommendation_gate_record(gate)
        self.assertEqual(gate["status"], "passed")

    def test_qualification_adapter_binds_publishable_release_to_current_subject(self) -> None:
        from synthesis.training_recommendation import (
            TrainingRecommendationContractError,
            build_training_recommendation_qualification_evidence,
        )
        from tests.test_qualification import _binding

        binding = _binding()
        publishability_gate = {
            "status": "passed",
            "subject_id": binding.subject_id,
            "subject_hash": binding.subject_hash,
            "binding_hash": binding.binding_hash,
            "release_pack_hash": binding.release_pack_hash,
        }
        matching = _evidence(
            publishable_release=_publishable_release(binding=binding)
        )
        composed = build_training_recommendation_qualification_evidence(
            binding=binding,
            release_candidate_evidence={"gates": {}, "evidence_graph": []},
            publishability_gate=publishability_gate,
            result=matching["result"],
        )
        self.assertEqual(composed["qualification"], "training_recommended")

        with self.assertRaises(TrainingRecommendationContractError):
            build_training_recommendation_qualification_evidence(
                binding=binding,
                release_candidate_evidence={"gates": {}, "evidence_graph": []},
                publishability_gate=publishability_gate,
                result=_evidence()["result"],
            )

    def test_post_registration_change_is_invalid_and_bootstrap_rule_is_exact(self) -> None:
        from synthesis.training_recommendation import (
            evaluate_training_recommendation,
            paired_percentile_bootstrap,
        )

        bootstrap = paired_percentile_bootstrap([1], [0], seed="known-seed")
        self.assertEqual(bootstrap["lower_bound"], -1.0)
        self.assertEqual(bootstrap["upper_bound"], -1.0)
        self.assertEqual(bootstrap["lower_rank"], 250)
        self.assertEqual(bootstrap["upper_rank"], 9_750)

        evidence = _evidence()
        protocol = dict(evidence["protocol"])
        protocol["registration"] = dict(protocol["registration"])
        protocol["registration"]["post_registration_change"] = True
        result = evaluate_training_recommendation(
            protocol=protocol,
            baseline=evidence["baseline"],
            treatment=evidence["treatment"],
            evaluation=evidence["evaluation"],
            paired_results=evidence["paired"],
            leakage=evidence["leakage"],
        )
        self.assertEqual(result["decision"]["status"], "invalid_experiment")
        self.assertIn("post_registration_change", result["decision"]["reason_codes"])

    def test_invalid_experiment_preserves_publishable_qualification(self) -> None:
        from synthesis.publishability import (
            build_publishable_qualification_evidence,
            evaluate_publishability,
        )
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )
        from synthesis.training_recommendation import build_training_recommendation_gate
        from tests.test_publishability import (
            _authority_inputs,
            _real_publishability_fixture,
        )
        from tests.test_qualification import (
            _binding,
            _passing_domain_assessment,
            _passing_machine_gates,
            _release_completeness,
            _release_pack_verification,
            _release_quality_audit,
        )

        binding = _binding()
        release_candidate_evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        release_candidate = evaluate_cumulative_qualification(
            subject=binding, evidence=release_candidate_evidence
        )
        fixture = _real_publishability_fixture()
        authority = _authority_inputs(fixture)
        publishability_decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **authority,
            now="2026-08-15T00:00:00Z",
        )
        publishable_evidence = build_publishable_qualification_evidence(
            binding=binding,
            release_candidate_evidence=release_candidate_evidence,
            bundle=fixture["bundle"],
            decision=publishability_decision,
            **authority,
            now="2026-08-15T00:00:00Z",
            evidence_class="real",
        )
        publishable = evaluate_cumulative_qualification(
            subject=binding,
            history=release_candidate["historical_decisions"],
            evidence=publishable_evidence,
            publishability_trusted_keys=authority["trusted_keys"],
            publishability_trusted_policy_hashes=authority["trusted_policy_hashes"],
            publishability_trusted_bundle_content_hashes=authority[
                "trusted_bundle_content_hashes"
            ],
            publishability_trusted_release_pack_verification_hashes=authority[
                "trusted_release_pack_verification_hashes"
            ],
            publishability_now="2026-08-15T00:00:00Z",
        )
        self.assertEqual(publishable["effective_qualification"], "publishable")

        evidence = _evidence(
            publishable_release=_publishable_release(binding=binding)
        )
        paired = dict(evidence["paired"])
        paired["results"] = [
            {**row, "baseline_success": 0}
            for row in paired["results"]
        ]
        from synthesis.training_recommendation import evaluate_training_recommendation

        invalid_result = evaluate_training_recommendation(
            protocol=evidence["protocol"],
            baseline=evidence["baseline"],
            treatment=evidence["treatment"],
            evaluation=evidence["evaluation"],
            paired_results=paired,
            leakage=evidence["leakage"],
        )
        training_gate = build_training_recommendation_gate(
            binding=binding, result=invalid_result
        )
        training_evidence = dict(release_candidate_evidence)
        training_evidence["qualification"] = "training_recommended"
        training_evidence["evidence_class"] = "real"
        training_evidence["gates"] = dict(release_candidate_evidence["gates"])
        training_evidence["gates"]["publishability"] = publishable_evidence["gates"][
            "publishability"
        ]
        training_evidence["gates"]["training_recommendation"] = training_gate
        result = evaluate_cumulative_qualification(
            subject=binding,
            history=publishable["historical_decisions"],
            evidence=training_evidence,
            publishability_trusted_keys=authority["trusted_keys"],
            publishability_trusted_policy_hashes=authority["trusted_policy_hashes"],
            publishability_trusted_bundle_content_hashes=authority[
                "trusted_bundle_content_hashes"
            ],
            publishability_trusted_release_pack_verification_hashes=authority[
                "trusted_release_pack_verification_hashes"
            ],
            publishability_now="2026-08-15T00:00:00Z",
        )
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["effective_qualification"], "publishable")


if __name__ == "__main__":
    unittest.main()
