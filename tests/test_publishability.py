from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path


AUTHORITY_SECRET = "publishability-test-authority-key"
RISK_SECRET = "publishability-test-risk-key"
CHECKED_AT = "2026-08-15T00:00:00Z"
EXPIRES_AT = "2026-09-15T00:00:00Z"


class PublishabilityContractTest(unittest.TestCase):
    def test_scope_subset_is_strict_across_all_distribution_dimensions(self) -> None:
        from synthesis.publishability import scope_is_subset

        approved = _scope(
            audience=["internal", "reviewer"],
            purpose=["evaluation", "research"],
            access="restricted",
            retention_days=30,
            redistribution="same_scope",
        )
        self.assertTrue(
            scope_is_subset(
                _scope(
                    audience=["reviewer"],
                    purpose=["evaluation"],
                    access="restricted",
                    retention_days=7,
                    redistribution="none",
                ),
                approved,
            )
        )
        self.assertFalse(
            scope_is_subset(
                _scope(
                    audience=["external"],
                    purpose=["evaluation"],
                    access="restricted",
                    retention_days=7,
                    redistribution="none",
                ),
                approved,
            )
        )
        self.assertFalse(
            scope_is_subset(
                _scope(
                    audience=["reviewer"],
                    purpose=["evaluation"],
                    access="restricted",
                    retention_days=31,
                    redistribution="none",
                ),
                approved,
            )
        )

    def test_clear_governance_and_authenticated_approval_pass(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "passed")
        self.assertEqual(decision["effective_qualification"], "publishable")
        self.assertEqual(decision["conformance"]["status"], "passed")
        self.assertEqual(decision["requested_scope"], fixture["scope"])

    def test_policy_hash_is_an_out_of_band_authority_anchor(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            trusted_keys=_authority_inputs(fixture)["trusted_keys"],
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("authority_policy_untrusted", decision["reason_codes"])

    def test_authority_evaluation_requires_explicit_time(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("evidence_incomplete", decision["reason_codes"])

    def test_real_evidence_requires_an_out_of_band_bundle_allowlist(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        inputs = _authority_inputs(fixture)
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            trusted_keys=inputs["trusted_keys"],
            trusted_policy_hashes=inputs["trusted_policy_hashes"],
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("evidence_origin_untrusted", decision["reason_codes"])

    def test_review_completion_without_approval_does_not_establish_publishable(
        self,
    ) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        bundle = copy.deepcopy(fixture["bundle"])
        bundle["publication_approval"] = None

        decision = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertNotIn("publishability_passed", decision["reason_codes"])

    def test_hard_governance_gate_cannot_be_waived_by_approval(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture(privacy_status="failed")
        bundle = fixture["bundle"]

        decision = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "denied")
        self.assertIn("governance_hard_gate_failed", decision["reason_codes"])

    def test_tampering_with_content_bound_governance_is_insufficient_evidence(
        self,
    ) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        bundle = copy.deepcopy(fixture["bundle"])
        bundle["governance"]["known_limitations"] = ["changed-after-approval"]

        decision = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertTrue(
            set(decision["reason_codes"]) & {
                "bundle_hash_mismatch",
                "evidence_hash_mismatch",
            }
        )

    def test_fixture_authority_only_reports_conformance(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _publishability_fixture(evidence_class="conformance_fixture")
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "denied")
        self.assertEqual(decision["conformance"]["status"], "passed")
        self.assertIn("non_qualifying_evidence_class", decision["reason_codes"])

    def test_approval_binds_evidence_class_against_fixture_relabeling(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        bundle = copy.deepcopy(fixture["bundle"])
        bundle["evidence_class"] = "conformance_fixture"
        _rehash_bundle_content(bundle)

        decision = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("evidence_identity_mismatch", decision["reason_codes"])

    def test_invalid_signature_and_revocation_fail_closed(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        bundle = copy.deepcopy(fixture["bundle"])
        bundle["publication_approval"]["attestation"]["signature"] = (
            "sha256:" + "0" * 64
        )
        approval = bundle["publication_approval"]
        approval_content = {
            key: approval[key]
            for key in approval
            if key not in {"approval_id", "approval_hash"}
        }
        approval_hash = _hash_record(approval_content)
        approval["approval_hash"] = approval_hash
        approval["approval_id"] = "publication_approval_" + approval_hash.removeprefix(
            "sha256:"
        )[:16]
        bundle = _rehash_bundle_content(bundle)
        invalid_signature = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(invalid_signature["status"], "insufficient_evidence")
        self.assertIn("authority_signature_invalid", invalid_signature["reason_codes"])

        revoked = _real_publishability_fixture(revoked_principal="publication-principal")
        revoked_decision = evaluate_publishability(
            bundle=revoked["bundle"],
            **_authority_inputs(revoked),
            now=CHECKED_AT,
        )
        self.assertEqual(revoked_decision["status"], "insufficient_evidence")
        self.assertIn("authority_revoked", revoked_decision["reason_codes"])

    def test_watch_finding_requires_bounded_clearance_or_authenticated_risk(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture(watch=True)
        accepted = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(accepted["status"], "passed")

        uncovered = _real_publishability_fixture(watch=True, include_risk=False)
        denied = evaluate_publishability(
            bundle=uncovered["bundle"],
            **_authority_inputs(uncovered),
            now=CHECKED_AT,
        )
        self.assertEqual(denied["status"], "insufficient_evidence")
        self.assertIn("review_finding_uncovered", denied["reason_codes"])

        mismatched = _real_publishability_fixture(
            watch=True,
            review_finding_id_override="review_item:sha256:" + "0" * 64,
        )
        mismatch_decision = evaluate_publishability(
            bundle=mismatched["bundle"],
            **_authority_inputs(mismatched),
            now=CHECKED_AT,
        )
        self.assertEqual(mismatch_decision["status"], "insufficient_evidence")
        self.assertIn("review_identity_mismatch", mismatch_decision["reason_codes"])

    def test_governance_finding_uses_versioned_clearance_evidence(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture(
            governance_findings=[
                {
                    "finding_id": "consent_gap",
                    "category": "consent_gap",
                    "severity": "medium",
                    "reason_code": "bounded_consent_review",
                }
            ]
        )
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        self.assertEqual(decision["status"], "passed")

    def test_external_residual_risk_requires_distinct_principals(self) -> None:
        from synthesis.publishability import evaluate_publishability

        separated = _real_publishability_fixture(watch=True, external=True)
        separated_decision = evaluate_publishability(
            bundle=separated["bundle"],
            **_authority_inputs(separated),
            now=CHECKED_AT,
        )
        self.assertEqual(separated_decision["status"], "passed")

        fixture = _real_publishability_fixture(
            watch=True,
            external=True,
            combine_roles=True,
        )
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(decision["status"], "denied")
        self.assertIn("separation_of_duties_violation", decision["reason_codes"])

        same_key = _real_publishability_fixture(
            watch=True,
            external=True,
            risk_key_override=True,
        )
        same_key_decision = evaluate_publishability(
            bundle=same_key["bundle"],
            **_authority_inputs(same_key),
            now=CHECKED_AT,
        )
        self.assertEqual(same_key_decision["status"], "denied")
        self.assertIn(
            "separation_of_duties_violation",
            same_key_decision["reason_codes"],
        )

    def test_requested_scope_must_be_subset_of_approved_scope(self) -> None:
        from synthesis.publishability import evaluate_publishability

        requested = _scope(
            audience=["internal", "reviewer"],
            purpose=["evaluation"],
            access="internal",
            retention_days=30,
            redistribution="same_scope",
        )
        approved = _scope(
            audience=["internal"],
            purpose=["evaluation"],
            access="restricted",
            retention_days=7,
            redistribution="none",
        )
        fixture = _real_publishability_fixture(
            requested_scope=requested,
            approved_scope=approved,
        )
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(decision["status"], "denied")
        self.assertIn("scope_mismatch", decision["reason_codes"])

    def test_pending_review_denies_even_with_approval(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture(watch=True, review_status="pending_review")
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(decision["status"], "denied")
        self.assertIn("review_pending", decision["reason_codes"])

    def test_internal_role_combination_requires_explicit_policy(self) -> None:
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture(
            watch=True,
            combine_roles=True,
            allow_internal_combination=True,
        )
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        self.assertEqual(decision["status"], "passed")

    def test_bundle_and_decision_round_trip_through_validated_files(self) -> None:
        from synthesis.publishability import (
            evaluate_publishability,
            load_publishability_bundle,
            write_publishability_bundle,
            write_publishability_decision,
        )

        fixture = _real_publishability_fixture()
        decision = evaluate_publishability(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "publishability_bundle.json"
            decision_path = Path(directory) / "publishability_decision.json"
            write_publishability_bundle(bundle_path, fixture["bundle"])
            write_publishability_decision(decision_path, decision)
            self.assertEqual(load_publishability_bundle(bundle_path), fixture["bundle"])
            serialized_decision = decision_path.read_text(encoding="utf-8")
            self.assertIn(str(decision["decision_id"]), serialized_decision)
            self.assertNotIn(AUTHORITY_SECRET, serialized_decision)

    def test_malformed_input_still_returns_a_bounded_decision(self) -> None:
        from synthesis.publishability import (
            evaluate_publishability,
            validate_publishability_decision_record,
        )

        decision = evaluate_publishability(bundle={})
        validate_publishability_decision_record(decision)
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertEqual(decision["evidence_class"], "unknown")

    def test_malformed_identity_fields_cannot_escape_bounded_decision(self) -> None:
        from synthesis.publishability import (
            evaluate_publishability,
            validate_publishability_decision_record,
        )

        decision = evaluate_publishability(
            bundle={
                "subject": {"subject_id": "not-a-complete-subject"},
                "bundle_hash": "not-a-sha256",
                "bundle_id": "not a safe id",
            }
        )
        validate_publishability_decision_record(decision)
        self.assertEqual(decision["status"], "insufficient_evidence")

    def test_publishability_records_use_the_shared_contract_boundary(self) -> None:
        from synthesis.contracts import (
            validate_authority_policy_record,
            validate_publication_approval_record,
            validate_publication_governance_record,
            validate_publishability_bundle_record,
            validate_publishability_decision_record,
            validate_revocation_evidence_record,
        )
        from synthesis.publishability import evaluate_publishability

        fixture = _real_publishability_fixture()
        bundle = fixture["bundle"]
        decision = evaluate_publishability(
            bundle=bundle,
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        validate_publication_governance_record(bundle["governance"])
        validate_authority_policy_record(bundle["authority_policy"])
        validate_revocation_evidence_record(bundle["revocation"])
        validate_publication_approval_record(bundle["publication_approval"])
        validate_publishability_bundle_record(bundle)
        validate_publishability_decision_record(decision)

    def test_qualification_gate_recomputes_caller_supplied_decision(self) -> None:
        from synthesis.publishability import (
            PublishabilityContractError,
            build_publishability_gate,
            canonical_domain_pack_hash,
            evaluate_publishability,
        )

        fixture = _real_publishability_fixture()
        forged = evaluate_publishability(bundle=fixture["bundle"])
        forged = {
            **forged,
            "status": "passed",
            "effective_qualification": "publishable",
            "reason_codes": ["publishability_passed"],
            "reasons": ["forged caller-supplied decision"],
            "conformance": {
                "status": "passed",
                "effective_qualification": "publishable",
            },
        }
        forged_content = {
            key: forged[key] for key in forged if key != "decision_id"
        }
        forged["decision_id"] = "publishability_decision_" + canonical_domain_pack_hash(
            forged_content
        ).removeprefix("sha256:")[:16]
        with self.assertRaises(PublishabilityContractError):
            build_publishability_gate(
                bundle=fixture["bundle"],
                decision=forged,
                **_authority_inputs(fixture),
                now=CHECKED_AT,
            )

    def test_passed_gate_requires_out_of_band_authority_inputs(self) -> None:
        from synthesis.publishability import (
            PublishabilityContractError,
            build_publishability_gate,
            validate_publishability_gate_record,
        )

        fixture = _real_publishability_fixture()
        gate = build_publishability_gate(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )

        with self.assertRaises(PublishabilityContractError):
            validate_publishability_gate_record(gate)

    def test_supplied_audit_must_match_the_release_candidate_audit(self) -> None:
        from synthesis.publishability import (
            PublishabilityContractError,
            build_publishability_bundle,
        )
        from tests.test_release_review import _watch_audit

        fixture = _real_publishability_fixture()
        bundle = fixture["bundle"]
        watch_audit = _watch_audit(
            triggers=["small_release_size"],
            reasons=["accepted samples are below the configured watch threshold"],
        )

        with self.assertRaises(PublishabilityContractError):
            build_publishability_bundle(
                release_candidate=fixture["release_candidate"],
                release_pack=bundle["release_pack"],
                release_pack_verification=bundle["release_pack_verification"],
                governance=bundle["governance"],
                audit=watch_audit,
                review=bundle["review"],
                risk_acceptances=bundle["risk_acceptances"],
                publication_approval=None,
                authority_policy=bundle["authority_policy"],
                revocation=bundle["revocation"],
                requested_scope=bundle["requested_scope"],
                validity=bundle["validity"],
                evidence_class="real",
            )

    def test_passed_gate_recomputes_a_forged_embedded_decision(self) -> None:
        from synthesis.publishability import (
            PublishabilityContractError,
            build_publishability_gate,
            canonical_domain_pack_hash,
            validate_publishability_gate_record,
        )

        fixture = _real_publishability_fixture()
        gate = build_publishability_gate(
            bundle=fixture["bundle"],
            **_authority_inputs(fixture),
            now=CHECKED_AT,
        )
        forged = copy.deepcopy(gate)
        forged_decision = dict(forged["decision"])
        forged_decision["reasons"] = ["forged caller-supplied decision"]
        forged_decision["decision_id"] = "publishability_decision_" + canonical_domain_pack_hash(
            {
                key: forged_decision[key]
                for key in forged_decision
                if key != "decision_id"
            }
        ).removeprefix("sha256:")[:16]
        forged["decision"] = forged_decision

        with self.assertRaises(PublishabilityContractError):
            validate_publishability_gate_record(
                forged,
                **_authority_inputs(fixture),
                now=CHECKED_AT,
            )


def _authority_inputs(fixture: dict[str, object]) -> dict[str, object]:
    bundle = fixture["bundle"]
    assert isinstance(bundle, dict)
    policy = bundle["authority_policy"]
    assert isinstance(policy, dict)
    return {
        "trusted_keys": {
            "approval-key": AUTHORITY_SECRET,
            "risk-key": RISK_SECRET,
        },
        "trusted_policy_hashes": [policy["policy_hash"]],
        "trusted_bundle_content_hashes": [bundle["bundle_content_hash"]],
        "trusted_release_pack_verification_hashes": [
            bundle["release_pack_verification"]["verification_hash"]
        ],
    }


def _publishability_fixture(
    *,
    evidence_class: str = "conformance_fixture",
    privacy_status: str = "passed",
    revoked_principal: str | None = None,
    watch: bool = False,
    include_risk: bool = True,
    external: bool = False,
    combine_roles: bool = False,
    risk_key_override: bool = False,
    allow_internal_combination: bool = False,
    requested_scope: dict[str, object] | None = None,
    approved_scope: dict[str, object] | None = None,
    review_status: str = "reviewed",
    review_finding_id_override: str | None = None,
    governance_findings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    from synthesis.publishability import (
        build_authority_policy,
        build_publication_approval,
        build_publication_governance_report,
        build_publishability_bundle,
        build_publishability_review_item,
        build_revocation_evidence,
        canonical_domain_pack_hash,
        compute_publishability_evidence_hash,
        fingerprint_for_key,
        publishability_subject_from_release_candidate,
    )

    release_candidate = _release_candidate_report(
        audit_status="watch" if watch else "clear"
    )
    release_pack = {
        "release_id": "workspace-release:sha256:" + "d" * 64,
        "content_hash": "sha256:" + "a" * 64,
        "byte_count": 1024,
        "dataset_version": "dataset_workspace_release_candidate",
    }
    scope = _scope(
        audience=["external"] if external else ["internal"],
        purpose=["publication"] if external else ["evaluation"],
        access="external" if external else "restricted",
        retention_days=30,
        redistribution="same_audience" if external else "none",
    )
    requested = requested_scope or scope
    approved = approved_scope or requested
    subject = publishability_subject_from_release_candidate(
        release_candidate,
        release_pack=release_pack,
    )
    checks = {
        check: {
            "status": "passed",
            "evidence_id": f"check-{check}",
            "evidence_hash": canonical_domain_pack_hash({"check": check}),
        }
        for check in (
            "artifact_integrity",
            "identity_binding",
            "source",
            "license",
            "export",
            "retention",
            "privacy",
            "sensitive_material",
            "consent",
            "access",
            "redistribution",
            "limitations",
            "mutation_safety",
        )
    }
    checks["privacy"]["status"] = privacy_status
    governance = build_publication_governance_report(
        subject=subject,
        proposed_scope=requested,
        checks=checks,
        findings=governance_findings or [],
        known_limitations=["fixture-only-authority-path"],
    )
    if watch:
        from tests.test_release_review import _watch_audit
        from synthesis.release_review import build_release_review_items

        audit = _watch_audit(
            triggers=["small_release_size"],
            reasons=["accepted samples are below the configured watch threshold"],
        )
        review_item = build_release_review_items(audit)[0]
        review_finding_id = review_finding_id_override or str(
            review_item["review_item_id"]
        )
        review = {
            "status": review_status,
            "queue": [review_item],
            "resolution": None,
            "dispositions": [
                {"finding_id": review_finding_id, "outcome": "accepted_risk"}
            ],
        }
    elif governance_findings:
        review_items = [
            build_publishability_review_item(finding)
            for finding in governance_findings
        ]
        from synthesis.publishability import canonical_domain_pack_hash

        review = {
            "status": "cleared",
            "queue": review_items,
            "resolution": None,
            "dispositions": [
                {
                    "finding_id": finding["finding_id"],
                    "outcome": "cleared",
                    "evidence_id": finding["finding_id"],
                    "evidence_hash": canonical_domain_pack_hash(item),
                }
                for finding, item in zip(governance_findings, review_items, strict=True)
            ],
        }
        audit = _clear_audit()
    else:
        audit = _clear_audit()
        review = {"status": "not_required", "queue": [], "resolution": None}
    approval_principal = "publication-principal"
    risk_principal = approval_principal if combine_roles else "risk-principal"
    roles = ["publication_approver", "revocation_authority"]
    if combine_roles:
        roles.append("risk_owner")
    policy = build_authority_policy(
        policy_id="authority_policy_workspace_v1",
        policy_version="1",
        trust_root={
            "root_id": "trust-root-workspace",
            "keys": [
                {
                    "key_id": "approval-key",
                    "fingerprint": fingerprint_for_key(AUTHORITY_SECRET),
                },
                {
                    "key_id": "risk-key",
                    "fingerprint": fingerprint_for_key(RISK_SECRET),
                },
            ],
        },
        grants=[
            {
                "principal_id": approval_principal,
                "key_id": "approval-key",
                "roles": roles,
                "scope": approved,
                "valid_from": CHECKED_AT,
                "expires_at": EXPIRES_AT,
            },
            *(
                []
                if combine_roles or not watch
                else [
                    {
                        "principal_id": risk_principal,
                        "key_id": "approval-key" if risk_key_override else "risk-key",
                        "roles": ["risk_owner"],
                        "scope": approved,
                        "valid_from": CHECKED_AT,
                        "expires_at": EXPIRES_AT,
                    }
                ]
            ),
        ],
        separation_of_duties={
            "external_residual_risk_requires_distinct_principals": True,
            "internal_role_combination_allowed": allow_internal_combination,
        },
        valid_from=CHECKED_AT,
        expires_at=EXPIRES_AT,
    )
    revocation = build_revocation_evidence(
        authority_policy=policy,
        checked_at=CHECKED_AT,
        principal_id=approval_principal,
        key_id="approval-key",
        expires_at=EXPIRES_AT,
        signing_key=AUTHORITY_SECRET,
        revoked_principals=(
            [revoked_principal] if revoked_principal is not None else []
        ),
    )
    release_pack_verification = dict(
        release_candidate["historical_decisions"][-1]["evidence"]["gates"][
            "release_pack_verification"
        ]
    )
    release_pack_verification["release_pack_byte_count"] = release_pack["byte_count"]
    risk_acceptances: list[dict[str, object]] = []
    if watch and include_risk:
        from synthesis.publishability import build_risk_acceptance

        risk_key = (
            "approval-key"
            if combine_roles or risk_key_override
            else "risk-key"
        )
        risk_secret = AUTHORITY_SECRET if risk_key == "approval-key" else RISK_SECRET
        risk_acceptances.append(
            build_risk_acceptance(
                subject=subject,
                findings=[
                    {
                        "finding_id": review_finding_id,
                        "category": "small_release_size",
                        "severity": "medium",
                        "reason_code": "bounded_small_release",
                        "controls": ["manual_review"],
                    }
                ],
                permitted_scope=approved,
                authority_policy=policy,
                principal_id=risk_principal,
                key_id=risk_key,
                issued_at=CHECKED_AT,
                expires_at=EXPIRES_AT,
                signing_key=risk_secret,
            )
        )
    evidence_hash = compute_publishability_evidence_hash(
        release_candidate=release_candidate,
        release_pack=release_pack,
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=audit,
        review=review,
        risk_acceptances=risk_acceptances,
        authority_policy=policy,
        revocation=revocation,
        requested_scope=requested,
        validity={"checked_at": CHECKED_AT},
    )
    approval = build_publication_approval(
        subject=subject,
        bundle_hash=evidence_hash,
        approved_scope=approved,
        authority_policy=policy,
        principal_id=approval_principal,
        key_id="approval-key",
        issued_at=CHECKED_AT,
        expires_at=EXPIRES_AT,
        known_limitations=governance["known_limitations"],
        signing_key=AUTHORITY_SECRET,
        evidence_class=evidence_class,
    )
    bundle = build_publishability_bundle(
        release_candidate=release_candidate,
        release_pack=release_pack,
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=audit,
        review=review,
        risk_acceptances=risk_acceptances,
        publication_approval=approval,
        authority_policy=policy,
        revocation=revocation,
        requested_scope=requested,
        validity={"checked_at": CHECKED_AT},
        evidence_class=evidence_class,
    )
    return {
        "bundle": bundle,
        "scope": requested,
        "approved_scope": approved,
        "subject": subject,
        "release_candidate": release_candidate,
    }


def _real_publishability_fixture(**kwargs: object) -> dict[str, object]:
    return _publishability_fixture(evidence_class="real", **kwargs)


def _release_candidate_report(audit_status: str = "clear") -> dict[str, object]:
    from synthesis.qualification import (
        build_release_candidate_evidence,
        evaluate_cumulative_qualification,
    )
    from tests.test_qualification import (
        _binding,
        _passing_domain_assessment,
        _passing_machine_gates,
        _release_completeness,
        _release_pack_verification,
    )
    if audit_status == "clear":
        audit = _clear_audit()
    else:
        from tests.test_release_review import _watch_audit

        audit = _watch_audit(
            triggers=["small_release_size"],
            reasons=["accepted samples are below the configured watch threshold"],
        )
        audit["decision"]["status"] = audit_status  # type: ignore[index]

    binding = _binding()
    report = evaluate_cumulative_qualification(
        subject=binding,
        evidence=build_release_candidate_evidence(
            binding=binding,
            machine_gates=_passing_machine_gates(),
            domain_assessment=_passing_domain_assessment(binding),
            release_completeness=_release_completeness(),
            release_quality_audit=audit,
            release_pack_verification=_release_pack_verification(),
        ),
    )
    return report


def _clear_audit() -> dict[str, object]:
    from tests.test_release_review import _watch_audit

    audit = _watch_audit(
        triggers=[],
        reasons=["no configured release quality audit thresholds triggered"],
    )
    audit["decision"]["status"] = "clear"  # type: ignore[index]
    return audit


def _scope(
    *,
    audience: list[str],
    purpose: list[str],
    access: str,
    retention_days: int,
    redistribution: str,
) -> dict[str, object]:
    return {
        "audience": audience,
        "purpose": purpose,
        "access": access,
        "retention": {"max_days": retention_days},
        "redistribution": redistribution,
    }


def _rehash_bundle_content(bundle: dict[str, object]) -> dict[str, object]:
    from synthesis.publishability import canonical_domain_pack_hash

    content = {
        key: bundle[key]
        for key in (
            "schema_version",
            "subject",
            "release_candidate",
            "release_pack",
            "release_pack_verification",
            "governance",
            "audit",
            "review",
            "risk_acceptances",
            "authority_policy",
            "revocation",
            "requested_scope",
            "validity",
            "publication_approval",
            "evidence_class",
        )
    }
    full_hash = canonical_domain_pack_hash(content)
    bundle["bundle_content_hash"] = full_hash
    bundle["bundle_id"] = "publishability_bundle_" + full_hash.removeprefix(
        "sha256:"
    )[:16]
    return bundle


def _hash_record(record: dict[str, object]) -> str:
    from synthesis.publishability import canonical_domain_pack_hash

    return canonical_domain_pack_hash(record)


if __name__ == "__main__":
    unittest.main()
