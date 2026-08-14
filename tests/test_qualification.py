from __future__ import annotations

import unittest


class CumulativeQualificationTest(unittest.TestCase):
    def test_release_candidate_requires_the_complete_machine_boundary(self) -> None:
        from synthesis.qualification import (
            QualificationBinding,
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit={
                **_release_quality_audit("watch"),
                "subject_hash": binding.subject_hash,
            },
            release_pack_verification={
                **_release_pack_verification(),
                "release_pack_hash": binding.release_pack_hash,
            },
        )

        result = evaluate_cumulative_qualification(
            subject=binding,
            evidence=evidence,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["effective_qualification"], "release_candidate")
        self.assertEqual(result["decision"]["status"], "passed")
        from synthesis.contracts import validate_qualification_report_record

        validate_qualification_report_record(result)

    def test_profile_purpose_alone_and_level_skips_cannot_qualify(self) -> None:
        from synthesis.qualification import evaluate_cumulative_qualification

        binding = _binding()
        profile_only = evaluate_cumulative_qualification(
            subject=binding,
            evidence={
                "qualification": "release_candidate",
                "profile": {"profile_purpose": "release_candidate"},
            },
        )
        self.assertEqual(profile_only["status"], "insufficient_evidence")
        self.assertEqual(profile_only["effective_qualification"], "unqualified")

        skipped = evaluate_cumulative_qualification(
            subject=binding,
            evidence={
                "qualification": "publishable",
                "gates": {
                    "release_candidate": {"status": "passed"},
                    "publishability": {"status": "passed"},
                },
            },
        )
        self.assertEqual(skipped["status"], "denied")
        self.assertEqual(skipped["effective_qualification"], "unqualified")
        self.assertIn("qualification_level_skip", skipped["decision"]["reason_codes"])

    def test_passing_gates_without_the_exact_evidence_envelope_are_insufficient(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        evidence.pop("binding")
        evidence.pop("evidence_graph")

        result = evaluate_cumulative_qualification(subject=binding, evidence=evidence)

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("qualification_subject_mismatch", result["decision"]["reason_codes"])

    def test_active_machine_status_and_schema_only_higher_gate_do_not_pass(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        machine_gates = evidence["gates"]["machine_gates"]
        machine_gates["quality"] = {
            "schema_version": "qualification_machine_gate_v1",
            "status": "active",
            **_gate_identity(binding),
        }
        active = evaluate_cumulative_qualification(subject=binding, evidence=evidence)
        self.assertEqual(active["status"], "insufficient_evidence")

        evidence["qualification"] = "publishable"
        evidence["gates"]["publishability"] = {
            "schema_version": "qualification_publishability_v1",
            "status": "passed",
            **_gate_identity(binding),
        }
        placeholder = evaluate_cumulative_qualification(
            subject=binding,
            evidence=evidence,
        )
        self.assertEqual(placeholder["status"], "denied")

    def test_malformed_evidence_is_bounded_and_report_validation_recomputes_state(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_qualification_report_record,
        )
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        malformed = dict(evidence)
        malformed["evidence_class"] = []
        result = evaluate_cumulative_qualification(
            subject=binding,
            evidence=malformed,
        )
        self.assertEqual(result["status"], "insufficient_evidence")

        forged = dict(result)
        forged["status"] = "passed"
        forged["effective_qualification"] = "release_candidate"
        forged["attempted_qualification"] = "release_candidate"
        forged["decision"] = {
            "status": "passed",
            "reason_codes": ["qualification_passed"],
            "reasons": ["forged"],
        }
        forged["claims"] = {
            "release_candidate": True,
            "eligible_for_human_publication_review": True,
            "publishable": False,
            "training_recommended": False,
        }
        with self.assertRaises(ContractValidationError):
            validate_qualification_report_record(forged)

    def test_machine_gate_subsets_and_unknown_gate_names_fail_closed(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        gates = evidence["gates"]
        assert isinstance(gates, dict)
        gates["machine_gates"] = {
            "quality": {"status": "passed"},
            "invented_gate": {"status": "passed"},
        }

        result = evaluate_cumulative_qualification(subject=binding, evidence=evidence)

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("evidence_missing", result["decision"]["reason_codes"])
        self.assertIn("evidence_malformed", result["decision"]["reason_codes"])

    def test_forged_minimal_history_cannot_establish_a_higher_level(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        release_candidate = evaluate_cumulative_qualification(
            subject=binding,
            evidence=build_release_candidate_evidence(
                binding=binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )
        forged = dict(release_candidate["historical_decisions"][0])
        forged.pop("evidence")

        result = evaluate_cumulative_qualification(
            subject=binding,
            history=[forged],
            evidence={
                "qualification": "publishable",
                "gates": {"publishability": {"status": "passed"}},
            },
        )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["effective_qualification"], "unqualified")
        self.assertIn("evidence_malformed", result["decision"]["reason_codes"])

    def test_failed_higher_attempt_preserves_lower_state_and_history(self) -> None:
        from synthesis.qualification import (
            QualificationBinding,
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        release_candidate = evaluate_cumulative_qualification(
            subject=binding,
            evidence=build_release_candidate_evidence(
                binding=binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )

        publishable_failure = evaluate_cumulative_qualification(
            subject=binding,
            history=release_candidate["historical_decisions"],
            evidence={
                "qualification": "publishable",
                "gates": {
                    "publishability": {"status": "failed"},
                },
            },
        )

        self.assertEqual(publishable_failure["status"], "denied")
        self.assertEqual(
            publishable_failure["effective_qualification"],
            "release_candidate",
        )
        self.assertEqual(len(publishable_failure["historical_decisions"]), 2)

        publishable_evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        publishable_evidence["qualification"] = "publishable"
        publishable_evidence["gates"]["publishability"] = {
            "schema_version": "qualification_publishability_v1",
            "status": "passed",
            **_gate_identity(binding),
            "evidence_ids": ["publication_governance"],
            "verification": {"status": "passed"},
            "governance": {"status": "verified"},
            "review": {"status": "verified"},
            "authority": {"status": "verified"},
        }
        publishable = evaluate_cumulative_qualification(
            subject=binding,
            history=release_candidate["historical_decisions"],
            evidence=publishable_evidence,
        )
        self.assertEqual(publishable["effective_qualification"], "publishable")

        training_failure = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        training_failure["qualification"] = "training_recommended"
        training_failure["gates"]["training_recommendation"] = {
            "schema_version": "qualification_training_recommendation_v1",
            "status": "failed",
            **_gate_identity(binding),
        }
        training_result = evaluate_cumulative_qualification(
            subject=binding,
            history=publishable["historical_decisions"],
            evidence=training_failure,
        )
        self.assertEqual(training_result["status"], "denied")
        self.assertEqual(
            training_result["effective_qualification"],
            "publishable",
        )

    def test_invalidating_lower_evidence_removes_dependents_without_rewriting_history(
        self,
    ) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        release_candidate = evaluate_cumulative_qualification(
            subject=binding,
            evidence=build_release_candidate_evidence(
                binding=binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )
        publishable = evaluate_cumulative_qualification(
            subject=binding,
            history=release_candidate["historical_decisions"],
            evidence={
                "qualification": "publishable",
                "gates": {"publishability": {"status": "passed"}},
            },
        )
        historical = list(publishable["historical_decisions"])

        invalidated = evaluate_cumulative_qualification(
            subject=binding,
            history=historical,
            invalidated_evidence=("release_pack",),
        )

        self.assertEqual(invalidated["effective_qualification"], "unqualified")
        self.assertEqual(invalidated["historical_decisions"], historical)
        self.assertIn(
            "qualification_dependency_invalidated",
            invalidated["decision"]["reason_codes"],
        )

    def test_new_artifact_subject_does_not_borrow_old_release_state(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        old_binding = _binding()
        old_result = evaluate_cumulative_qualification(
            subject=old_binding,
            evidence=build_release_candidate_evidence(
                binding=old_binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(old_binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )
        # The public factory creates a new content-addressed subject for the
        # repack; it is not an in-place mutation of the old binding.
        new_binding = _binding(release_pack_hash="sha256:" + "b" * 64)

        result = evaluate_cumulative_qualification(
            subject=new_binding,
            history=old_result["historical_decisions"],
            evidence={
                "qualification": "publishable",
                "gates": {"publishability": {"status": "passed"}},
            },
        )

        self.assertEqual(result["effective_qualification"], "unqualified")
        self.assertIn("qualification_level_skip", result["decision"]["reason_codes"])

    def test_binding_round_trip_retains_the_exact_identity_graph(self) -> None:
        from synthesis.qualification import QualificationBinding

        binding = _binding()
        restored = QualificationBinding.from_record(binding.to_record())

        self.assertEqual(restored.to_record(), binding.to_record())
        self.assertEqual(
            restored.evidence_graph[0]["content_hash"],
            binding.release_pack_hash,
        )
        self.assertEqual(
            restored.artifact_subject.artifact_references[0].content_hash,
            binding.release_pack_hash,
        )

    def test_non_passing_and_invalid_lifecycle_evidence_fail_closed(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        for status, expected_status in (
            ("failed", "denied"),
            ("blocked", "denied"),
            ("revoked", "insufficient_evidence"),
            ("cancelled", "insufficient_evidence"),
            ("incomplete", "insufficient_evidence"),
        ):
            with self.subTest(status=status):
                binding = _binding()
                evidence = build_release_candidate_evidence(
                    binding=binding,
                    machine_gates=_passing_machine_gates(),
                    domain_assessment=_passing_domain_assessment(binding),
                    release_completeness=_release_completeness(),
                    release_quality_audit=_release_quality_audit(),
                    release_pack_verification=_release_pack_verification(),
                )
                gates = evidence["gates"]
                assert isinstance(gates, dict)
                machine_gates = gates["machine_gates"]
                assert isinstance(machine_gates, dict)
                machine_gates["quality"] = {"status": status}

                result = evaluate_cumulative_qualification(
                    subject=binding,
                    evidence=evidence,
                )

                self.assertEqual(result["status"], expected_status)

    def test_unknown_versions_fixtures_and_legacy_statuses_do_not_qualify(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding()
        unknown = build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=_release_quality_audit(),
            release_pack_verification=_release_pack_verification(),
        )
        gates = unknown["gates"]
        assert isinstance(gates, dict)
        machine_gates = gates["machine_gates"]
        assert isinstance(machine_gates, dict)
        machine_gates["quality"] = {
            "schema_version": "quality_report_v99",
            "status": "passed",
        }
        unknown_result = evaluate_cumulative_qualification(
            subject=binding,
            evidence=unknown,
        )
        self.assertEqual(unknown_result["status"], "insufficient_evidence")
        self.assertIn(
            "evidence_unknown_version",
            unknown_result["decision"]["reason_codes"],
        )
        machine_gates["quality"]["schema_version"] = "quality_arbitrary_v1"
        arbitrary_result = evaluate_cumulative_qualification(
            subject=binding,
            evidence=unknown,
        )
        self.assertEqual(arbitrary_result["status"], "insufficient_evidence")
        self.assertIn(
            "evidence_unknown_version",
            arbitrary_result["decision"]["reason_codes"],
        )

        fixture = evaluate_cumulative_qualification(
            subject=binding,
            evidence={
                "qualification": "release_candidate",
                "evidence_class": "conformance_fixture",
                "gates": {"machine_gates": {"status": "passed"}},
            },
        )
        self.assertEqual(fixture["status"], "denied")

        legacy_only = evaluate_cumulative_qualification(
            subject=binding,
            evidence={
                "qualification": "release_candidate",
                "dataset_release": {"status": "passed"},
                "profile": {"profile_purpose": "release_candidate"},
            },
        )
        self.assertEqual(legacy_only["status"], "insufficient_evidence")

    def test_stale_bound_graph_evidence_invalidates_the_current_claim(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )

        binding = _binding(release_pack_status="stale")
        result = evaluate_cumulative_qualification(
            subject=binding,
            evidence=build_release_candidate_evidence(
                binding=binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["effective_qualification"], "unqualified")
        self.assertIn("evidence_stale", result["decision"]["reason_codes"])


def _binding(
    *,
    release_pack_hash: str = "sha256:" + "a" * 64,
    release_pack_status: str = "active",
):
    from synthesis.domain_pack import (
        AdmittedSource,
        DomainPack,
        DomainPlan,
        canonical_domain_pack_hash,
    )
    from synthesis.workspace_domain_pack import (
        build_workspace_domain_pack,
        workspace_planning_intent,
    )
    from synthesis.qualification import QualificationBinding

    pack = build_workspace_domain_pack()
    plan = pack.plan(
        workspace_planning_intent(pack),
        AdmittedSource(
            source_id="workspace_source_v1",
            source_schema_version="workspace_source_v1",
            source_content_hash=canonical_domain_pack_hash({"source": "workspace"}),
            admission_policy_id="workspace_source_policy_v1",
            admission_policy_hash=canonical_domain_pack_hash({"policy": "allowed"}),
        ),
    )
    assert isinstance(plan, DomainPlan)
    return QualificationBinding.from_plan(
        plan,
        release_pack_hash=release_pack_hash,
        release_pack_byte_count=1024,
        profile={
            "profile_id": "workspace_release_candidate",
            "profile_purpose": "release_candidate",
            "generation_mode": "llm",
            "config_hash": "sha256:" + "c" * 64,
        },
        evidence_graph=(
            {
                "artifact_id": "release_pack",
                "artifact_schema_version": "dataset_release_pack_v1",
                "content_hash": release_pack_hash,
                "byte_count": 1024,
                "status": release_pack_status,
            },
        ),
    )


def _passing_machine_gates() -> dict[str, object]:
    return {
        gate: {
            "schema_version": "qualification_machine_gate_v1",
            "status": "passed",
        }
        for gate in (
            "contract",
            "execution",
            "verification",
            "grounding",
            "quality",
            "provenance",
            "source",
            "mutation",
            "coverage",
            "held_out",
            "profile_promotion",
            "dataset_release",
            "artifact_integrity",
        )
    }


def _release_completeness(status: str = "passed") -> dict[str, object]:
    return {
        "schema_version": "qualification_release_completeness_v1",
        "decision": {"status": status},
    }


def _release_quality_audit(status: str = "clear") -> dict[str, object]:
    return {
        "schema_version": "release_quality_audit_v1",
        "decision": {"status": status},
    }


def _release_pack_verification(status: str = "passed") -> dict[str, object]:
    return {
        "schema_version": "qualification_release_pack_verification_v1",
        "verification": {"status": status},
    }


def _gate_identity(binding) -> dict[str, object]:
    return {
        "subject_id": binding.subject_id,
        "subject_hash": binding.subject_hash,
        "binding_hash": binding.binding_hash,
        "release_pack_hash": binding.release_pack_hash,
    }


def _passing_domain_assessment(binding) -> dict[str, object]:
    record = {
        "schema_version": "domain_assessment_v1",
        "domain_pack_reference": binding.domain_pack_reference.to_record(),
        "plan_id": binding.plan_id,
        "plan_hash": binding.plan_hash,
        "evidence_references": [
            {
                "schema_version": "domain_evidence_reference_v1",
                "evidence_id": "release_pack",
                "evidence_schema_version": binding.evidence_graph[0][
                    "artifact_schema_version"
                ],
                "evidence_hash": binding.release_pack_hash,
            }
        ],
        "established_capability_references": [
            reference.to_record() for reference in binding.capability_references
        ],
        "status": "established",
        "reason_code": "exact_evidence_established",
    }
    from synthesis.domain_pack import canonical_domain_pack_hash

    assessment_hash = canonical_domain_pack_hash(record)
    return {
        **record,
        "assessment_id": "domain_assessment_" + assessment_hash.removeprefix(
            "sha256:"
        )[:16],
        "assessment_hash": assessment_hash,
    }


if __name__ == "__main__":
    unittest.main()
