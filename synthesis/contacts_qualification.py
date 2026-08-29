"""Contacts-owned release evidence and qualification adapter.

The cumulative qualification state machine is shared framework machinery, but
the evidence that feeds it is not.  This module is deliberately Contacts
specific: it resolves the current Contacts Pack, validates Contacts samples,
coverage, held-out evaluation, mutation admission, and release thresholds, and
only then constructs the shared qualification envelope.

It is read-only with respect to release artifacts.  A later acceptance-proof
ticket may use this adapter as its production seam; this module does not freeze
provider material or make provider calls.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from synthesis.contacts_domain_pack import build_contacts_domain_pack
from synthesis.contacts_evidence import (
    canonical_capability_references,
    contacts_task_contract_hash,
)
from synthesis.coverage_evidence import verify_coverage_evidence
from synthesis.coverage_registry import resolve_domain_coverage_planning
from synthesis.domain_pack import (
    AdmittedSource,
    DomainAssessment,
    DomainAssessmentEvidence,
    DomainEvidenceReference,
    DomainPlan,
    DomainPackContractError,
    canonical_domain_pack_hash,
)
from synthesis.evaluation import contacts_heldout_suite
from synthesis.mutation_admission import canonical_hash
from synthesis.runtime_registry import release_completeness_threshold_record
from synthesis.tasks import CandidateTask


CONTACTS_RELEASE_CANDIDATE_PROFILE_ID = "contacts_release_candidate"
CONTACTS_RELEASE_CANDIDATE_PROFILE_VERSION = "contacts_release_candidate_v1"
CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION = (
    "dataset_contacts_release_candidate_v1"
)
CONTACTS_RELEASE_COVERAGE_PROFILE_ID = "contacts_representative"
CONTACTS_RELEASE_COVERAGE_PROFILE_VERSION = "contacts_representative_v1"
CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES = 5
CONTACTS_RELEASE_TARGET_CANDIDATES = 10
CONTACTS_RELEASE_PROFILE_SCHEMA_VERSION = "contacts_release_candidate_profile_v1"
CONTACTS_RELEASE_CANDIDATE_PROFILE_SCHEMA_VERSION = (
    CONTACTS_RELEASE_PROFILE_SCHEMA_VERSION
)

_CONTACTS_DOMAIN_IDS = frozenset({"contacts", "contacts_fixture"})
_CONTACTS_GENERATION_MODES = frozenset({"foundation_fixture", "llm"})
_CONTACTS_RELEASE_SAMPLE_SCHEMA = "contacts_evidence_binding_v1"
_CONTACTS_RELEASE_REQUIRED_TASK_TYPES = frozenset(
    {"contact_lookup", "contact_followup"}
)
_CONTACTS_RELEASE_REQUIRED_TOOLS = {
    "contact_lookup": ("lookup_contact_email",),
    "contact_followup": (
        "lookup_contact_email",
        "record_contact_followup",
    ),
}
_CONTACTS_RELEASE_CAPABILITY_KEYS = frozenset(
    {"contact_lookup", "followup_recording", "contact_lookup_recovery"}
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContactsQualificationInsufficiency(ValueError):
    """A bounded Contacts release-evidence failure."""

    def __init__(self, reason_code: str, reason: str) -> None:
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason


ContactsReleaseEvidenceError = ContactsQualificationInsufficiency


def contacts_release_candidate_profile() -> dict[str, object]:
    """Return the immutable Contacts release-contract selection.

    The profile names the exact domain-owned contracts used by qualification.
    Source identity remains run-scoped and therefore belongs to the Domain
    plan, not this source-independent profile record.
    """

    pack = build_contacts_domain_pack()
    descriptor = pack.descriptor
    planning = resolve_domain_coverage_planning("contacts_fixture")
    coverage = planning.resolve_profile(
        CONTACTS_RELEASE_COVERAGE_PROFILE_ID,
        CONTACTS_RELEASE_COVERAGE_PROFILE_VERSION,
    )
    suite = contacts_heldout_suite()
    threshold = release_completeness_threshold_record(
        "contacts_release_candidate"
    )
    if threshold is None:
        raise ContactsQualificationInsufficiency(
            "contacts_release_profile_ineligible",
            "Contacts release completeness contract is unavailable",
        )
    return {
        "schema_version": CONTACTS_RELEASE_PROFILE_SCHEMA_VERSION,
        "profile_id": CONTACTS_RELEASE_CANDIDATE_PROFILE_ID,
        "profile_version": CONTACTS_RELEASE_CANDIDATE_PROFILE_VERSION,
        "domain_pack_reference": descriptor.reference().to_record(),
        "runtime_contract": descriptor.runtime_contracts[0].to_record(),
        "capability_references": canonical_capability_references(
            tuple(descriptor.capability_references)
        ),
        "coverage": {
            "catalog_id": coverage.catalog_id,
            "catalog_version": coverage.catalog_version,
            "catalog_hash": canonical_coverage_hash(
                planning.resolve_catalog(coverage.catalog_version).canonical()
            ),
            "profile_id": coverage.profile_id,
            "profile_version": coverage.version,
            "profile_hash": canonical_coverage_hash(coverage.canonical()),
        },
        "held_out": {
            "suite_id": suite.suite_id,
            "suite_version": suite.suite_version,
            "domain_id": suite.domain_id,
            "capability_references": canonical_capability_references(
                tuple(suite.capability_references)
            ),
            "thresholds": {
                "mvp_min_heldout_pass_rate": 0.8,
                "max_regression_count": 0,
                "min_capability_pass_rates": {
                    reference.capability_key: 1.0
                    for reference in suite.capability_references
                },
            },
        },
        "mutation": {
            "mode": "enforce",
            "component": next(
                component.to_record()
                for component in descriptor.component_contracts
                if component.component_kind == "mutation_admission_mode"
            ),
        },
        "completeness": dict(threshold),
        "machine_gates": {
            "schema_version": "qualification_machine_gate_v1",
            "names": list(_qualification_machine_gate_names()),
        },
    }


# The long name is useful to callers that prefer an explicit builder.
build_contacts_release_candidate_profile = contacts_release_candidate_profile


def build_contacts_release_candidate_evidence(**kwargs: object) -> dict[str, object]:
    """Build shared qualification evidence through a Contacts-named seam."""

    from synthesis.qualification import build_release_candidate_evidence

    return build_release_candidate_evidence(**kwargs)  # type: ignore[arg-type]


def qualify_contacts_release_candidate(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    release_quality_audit_path: Path | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Sequence[str] = (),
) -> dict[str, object]:
    """Evaluate one exact current Contacts artifact subject.

    All file and contract errors become a validated, non-claiming report.  A
    successful report still means only Release Candidate; higher cumulative
    levels require their own evidence through the shared evaluator.
    """

    try:
        inputs = _load_contacts_release_inputs(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            release_quality_audit_path=release_quality_audit_path,
        )
    except ContactsQualificationInsufficiency as exc:
        return _contacts_insufficient_report(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            reason_code=exc.reason_code,
            reason=exc.reason,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _contacts_insufficient_report(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            reason_code="contacts_evidence_malformed",
            reason=(
                "Contacts release evidence is unreadable or malformed: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    from synthesis.qualification import evaluate_cumulative_qualification

    try:
        return evaluate_cumulative_qualification(
            subject=inputs["binding"],
            evidence=inputs["evidence"],
            history=history,
            invalidated_evidence=invalidated_evidence,
        )  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _contacts_insufficient_report(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            reason_code="contacts_evidence_malformed",
            reason="Contacts qualification evidence could not be evaluated",
        )


evaluate_contacts_release_candidate = qualify_contacts_release_candidate


def write_contacts_release_candidate_qualification(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    output_path: Path,
    release_quality_audit_path: Path | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Sequence[str] = (),
) -> Path:
    from synthesis.qualification import write_qualification_report

    report = qualify_contacts_release_candidate(
        manifest_path=manifest_path,
        release_pack_path=release_pack_path,
        release_quality_audit_path=release_quality_audit_path,
        history=history,
        invalidated_evidence=invalidated_evidence,
    )
    return write_qualification_report(output_path, report)


def _load_contacts_release_inputs(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    release_quality_audit_path: Path | None,
) -> dict[str, object]:
    from synthesis.contracts import (
        ContractValidationError,
        validate_coverage_evidence_record,
        validate_dataset_release_pack_record,
        validate_dataset_release_report_record,
        validate_evaluation_report_record,
        validate_manifest_record,
        validate_profile_decision_report_record,
        validate_release_quality_audit_record,
        validate_rejection_record,
        validate_sample_record,
    )
    from synthesis.datasets import build_artifact_hash_record
    from synthesis.release_pack import verify_dataset_release_pack

    try:
        manifest = _load_json_mapping(manifest_path)
        validate_manifest_record(manifest)
        pack = _load_json_mapping(release_pack_path)
        validate_dataset_release_pack_record(pack)
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            f"Contacts release evidence is unreadable or malformed: {type(exc).__name__}",
        ) from None

    _validate_contacts_profile_identity(manifest)
    _validate_pack_manifest_identity(
        manifest=manifest,
        pack=pack,
        manifest_path=manifest_path,
        release_pack_path=release_pack_path,
        release_quality_audit_path=release_quality_audit_path,
    )

    pack_verification = verify_dataset_release_pack(release_pack_path)
    verification = _mapping(pack_verification.get("verification"))
    verification_status = verification.get("status")
    if verification_status not in {"passed", "failed", "insufficient_evidence"}:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "standalone Contacts release-pack verification has no bounded status",
        )

    artifacts = _mapping(pack.get("artifacts"))
    try:
        samples = _load_jsonl_artifact(release_pack_path.parent, artifacts, "samples")
        rejections = _load_jsonl_artifact(
            release_pack_path.parent,
            artifacts,
            "rejections",
        )
        for sample in samples:
            validate_sample_record(sample)
        for rejection in rejections:
            validate_rejection_record(rejection)
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            f"Contacts samples or rejections are unreadable or malformed: {type(exc).__name__}",
        ) from None
    if not samples:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts release pack contains no accepted current samples",
        )

    pack_profile = _mapping(pack.get("profile"))
    run_profile = _mapping(manifest.get("run_profile"))
    _validate_dataset_versions(
        manifest=manifest,
        pack=pack,
        pack_artifacts=artifacts,
        base_dir=release_pack_path.parent,
    )

    first_binding = _contacts_binding(samples[0])
    plan_record = _mapping(_mapping(first_binding.get("plan")).get("plan_record"))
    pack_adapter = build_contacts_domain_pack()
    try:
        plan = DomainPlan.from_record(
            plan_record,
            descriptor=pack_adapter.descriptor,
        )
    except (DomainPackContractError, TypeError, ValueError):
        raise ContactsQualificationInsufficiency(
            "contacts_plan_evidence_missing",
            "Contacts samples do not retain a valid current Domain plan",
        ) from None

    _validate_contacts_plan_against_profile(plan)
    recovery_count = _validate_contacts_samples(samples, plan)
    _validate_contacts_manifest_evidence(manifest, plan, samples, recovery_count)

    release_report = _load_pack_json(
        release_pack_path.parent,
        artifacts,
        "dataset_release_report",
    )
    evaluation_report = _load_pack_json(
        release_pack_path.parent,
        artifacts,
        "evaluation_report",
    )
    profile_decision_report = _load_pack_json(
        release_pack_path.parent,
        artifacts,
        "profile_decision_report",
    )
    quality_report = _load_pack_json(
        release_pack_path.parent,
        artifacts,
        "quality_report",
    )
    validate_dataset_release_report_record(release_report)
    validate_evaluation_report_record(evaluation_report)
    validate_profile_decision_report_record(profile_decision_report)
    _validate_contacts_quality_report(quality_report, manifest, samples, rejections)
    _report_dataset_version(
        release_report,
        manifest,
        "dataset_release_report",
    )
    _report_dataset_version(
        evaluation_report,
        manifest,
        "evaluation_report",
    )
    _report_dataset_version(
        profile_decision_report,
        manifest,
        "profile_decision_report",
    )
    _report_dataset_version(quality_report, manifest, "quality_report")
    _validate_contacts_release_completeness(release_report)
    _validate_contacts_evaluation(evaluation_report, plan)
    _validate_contacts_profile_decision_alignment(
        profile_decision_report,
        quality_report=quality_report,
        manifest=manifest,
    )

    manifest_artifacts = _mapping(manifest.get("artifacts"))
    coverage_plan = _load_manifest_json(
        release_pack_path.parent,
        manifest_artifacts,
        "coverage_plan",
    )
    coverage_evidence = _load_manifest_json(
        release_pack_path.parent,
        manifest_artifacts,
        "coverage_evidence",
    )
    try:
        validate_coverage_evidence_record(coverage_evidence)
        verify_coverage_evidence(
            coverage_evidence,
            plan=coverage_plan,
            run_profile=run_profile,
            samples=samples,
            rejections=rejections,
        )
    except (ContractValidationError, TypeError, ValueError):
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            "Contacts coverage evidence is missing, stale, or inconsistent",
        ) from None
    _validate_contacts_coverage_contract(
        coverage_plan=coverage_plan,
        coverage_evidence=coverage_evidence,
        run_profile=run_profile,
    )

    audit_path = release_quality_audit_path
    if audit_path is None:
        audit_name = manifest_artifacts.get("release_quality_audit")
        if isinstance(audit_name, str):
            audit_path = release_pack_path.parent / audit_name
    if audit_path is None or not audit_path.exists():
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_missing",
            "Contacts release-quality audit is unavailable",
        )
    try:
        audit = _load_json_mapping(audit_path)
        validate_release_quality_audit_record(audit)
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            f"Contacts release-quality audit is unreadable or malformed: {type(exc).__name__}",
        ) from None
    _report_dataset_version(audit, manifest, "release_quality_audit")

    release_pack_artifact = build_artifact_hash_record(release_pack_path)
    release_pack_hash = release_pack_artifact.sha256
    release_pack_byte_count = release_pack_artifact.byte_count
    graph = _contacts_evidence_graph(
        base_dir=release_pack_path.parent,
        artifacts=artifacts,
        manifest=manifest,
        audit_path=audit_path,
        release_pack_hash=release_pack_hash,
        release_pack_byte_count=release_pack_byte_count,
    )
    from synthesis.qualification import QualificationBinding

    binding = QualificationBinding.from_plan(
        plan,
        release_pack_hash=release_pack_hash,
        release_pack_byte_count=release_pack_byte_count,
        profile=_qualification_profile(run_profile),
        evidence_graph=graph,
    )

    profile_reasons = _contacts_release_profile_reasons(
        manifest=manifest,
        run_profile=run_profile,
        coverage_plan=coverage_plan,
        pack_profile=pack_profile,
        plan=plan,
    )
    machine_gates = _contacts_machine_gates(
        manifest=manifest,
        samples=samples,
        quality_report=quality_report,
        evaluation_report=evaluation_report,
        profile_decision_report=profile_decision_report,
        release_report=release_report,
        coverage_evidence=coverage_evidence,
        pack_verification=verification,
        profile_reasons=profile_reasons,
    )
    evidence_references = tuple(
        DomainEvidenceReference(
            evidence_id=_safe_evidence_id(str(node["artifact_id"])),
            evidence_schema_version=str(node["artifact_schema_version"]),
            evidence_hash=str(node["content_hash"]),
        )
        for node in graph
    )
    evaluation_references = tuple(
        reference
        for reference in evidence_references
        if reference.evidence_schema_version == "evaluation_report_v1"
    )
    release_references = tuple(
        reference
        for reference in evidence_references
        if reference not in evaluation_references
    )
    assessment = pack_adapter.assess(
        plan,
        DomainAssessmentEvidence(
            evidence_references=evidence_references,
            evaluation_evidence_references=evaluation_references,
            release_evidence_references=release_references,
            established_capability_references=tuple(plan.capability_references),
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
        ),
    )
    if not isinstance(assessment, DomainAssessment):
        raise ContactsQualificationInsufficiency(
            "contacts_assessment_incomplete",
            "Contacts Domain assessment could not establish the exact evidence graph",
        )

    evidence = build_contacts_release_candidate_evidence(
        binding=binding,
        machine_gates=machine_gates,
        domain_assessment=assessment,
        release_completeness={
            "schema_version": "qualification_release_completeness_v1",
            **dict(_mapping(release_report.get("release_completeness"))),
        },
        release_quality_audit=audit,
        release_pack_verification={
            "schema_version": "qualification_release_pack_verification_v1",
            "verification": dict(verification),
            "release_pack_hash": release_pack_hash,
        },
        evidence_class=(
            "real_machine"
            if _profile_generation_mode(run_profile) == "llm"
            else "machine"
        ),
    )
    return {"binding": binding, "evidence": evidence}


def _validate_contacts_profile_identity(manifest: Mapping[str, object]) -> None:
    profile = _mapping(manifest.get("run_profile"))
    reasons = _contacts_profile_shape_reasons(profile)
    if reasons:
        raise ContactsQualificationInsufficiency(
            "contacts_release_profile_ineligible",
            "; ".join(reasons),
        )


def _contacts_profile_shape_reasons(profile: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    if profile.get("schema_version") != "run_profile_v4":
        reasons.append("Contacts Release Candidate requires run_profile_v4")
    if profile.get("profile_id") != CONTACTS_RELEASE_CANDIDATE_PROFILE_ID:
        reasons.append("profile is not the versioned Contacts release profile")
    if profile.get("profile_purpose") != "release_candidate":
        reasons.append("profile purpose is not release_candidate")
    if _profile_generation_mode(profile) not in _CONTACTS_GENERATION_MODES:
        reasons.append("Contacts release profile has unsupported generation mode")
    if _profile_generation_target(profile) != CONTACTS_RELEASE_TARGET_CANDIDATES:
        reasons.append("Contacts release profile candidate target is not 10")
    seed = _mapping(profile.get("seed"))
    if seed.get("domain") not in _CONTACTS_DOMAIN_IDS:
        reasons.append("profile seed domain is not Contacts")
    if "enable_branching" not in _profile_enabled_features(profile):
        reasons.append("Contacts release profile requires branching coverage")
    mutation = _mapping(profile.get("mutation_admission"))
    if mutation.get("mode") != "enforce":
        reasons.append("Contacts release profile requires enforced mutation admission")
    judge = mutation.get("judge")
    if not isinstance(judge, Mapping) or not isinstance(judge.get("model"), str):
        reasons.append("Contacts release profile requires a mutation judge identity")
    coverage = _mapping(profile.get("coverage_profile"))
    if (
        coverage.get("profile_id") != CONTACTS_RELEASE_COVERAGE_PROFILE_ID
        or coverage.get("version") != CONTACTS_RELEASE_COVERAGE_PROFILE_VERSION
        or coverage.get("target_accepted_sample_count")
        != CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES
    ):
        reasons.append("Contacts release profile selects the wrong coverage contract")
    return reasons


def _validate_pack_manifest_identity(
    *,
    manifest: Mapping[str, object],
    pack: Mapping[str, object],
    manifest_path: Path,
    release_pack_path: Path,
    release_quality_audit_path: Path | None,
) -> None:
    if pack.get("schema_version") != "dataset_release_pack_v2":
        raise ContactsQualificationInsufficiency(
            "contacts_mutation_admission_incomplete",
            "Contacts Release Candidate requires a mutation-safe v2 release pack",
        )
    if pack.get("dataset_version") != manifest.get("dataset_version"):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts release pack and manifest dataset versions differ",
        )
    pack_artifacts = _mapping(pack.get("artifacts"))
    manifest_artifact = _mapping(pack_artifacts.get("manifest"))
    manifest_digest = _hash_file_if_readable(manifest_path)
    if (
        manifest_artifact.get("path") != manifest_path.name
        or manifest_digest is None
        or manifest_artifact.get("sha256") != manifest_digest[0]
        or manifest_artifact.get("byte_count") != manifest_digest[1]
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Supplied Contacts manifest does not match the release-pack artifact",
        )
    inputs = _mapping(pack.get("inputs"))
    if (
        inputs.get("manifest_path") != manifest_path.name
        or inputs.get("dataset_release_report_path")
        != _mapping(manifest.get("artifacts")).get("dataset_release_report")
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts release pack input bindings do not match the manifest",
        )
    manifest_artifacts = _mapping(manifest.get("artifacts"))
    if manifest_artifacts.get("dataset_release_pack") != release_pack_path.name:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Manifest does not identify the supplied Contacts release pack",
        )
    audit_name = manifest_artifacts.get("release_quality_audit")
    if not isinstance(audit_name, str) or not audit_name:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_missing",
            "Manifest does not identify the Contacts release-quality audit",
        )
    if (
        release_quality_audit_path is not None
        and (
            release_quality_audit_path.parent != release_pack_path.parent
            or release_quality_audit_path.name != audit_name
        )
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Supplied Contacts release-quality audit is not the manifest artifact",
        )
    if manifest.get("schema_version") != "dataset_manifest_v2":
        raise ContactsQualificationInsufficiency(
            "contacts_mutation_admission_incomplete",
            "Contacts Release Candidate requires dataset_manifest_v2",
        )


def _validate_dataset_versions(
    *,
    manifest: Mapping[str, object],
    pack: Mapping[str, object],
    pack_artifacts: Mapping[str, object],
    base_dir: Path,
) -> None:
    dataset_version = manifest.get("dataset_version")
    if pack.get("dataset_version") != dataset_version:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts release pack dataset version does not match the manifest",
        )
    for key in (
        "quality_report",
        "evaluation_report",
        "profile_decision_report",
        "dataset_release_report",
    ):
        record = _load_pack_json(base_dir, pack_artifacts, key)
        if record.get("dataset_version") != dataset_version:
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                f"Contacts {key} dataset version does not match the release subject",
            )


def _validate_contacts_plan_against_profile(plan: DomainPlan) -> None:
    profile = contacts_release_candidate_profile()
    if plan.domain_pack_reference.to_record() != profile["domain_pack_reference"]:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts plan does not select the current Contacts Pack",
        )
    if plan.runtime_contract.to_record() != profile["runtime_contract"]:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts plan does not select the current Contacts runtime",
        )
    if canonical_capability_references(tuple(plan.capability_references)) != profile[
        "capability_references"
    ]:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts plan does not carry the complete canonical capability catalog",
        )


def _validate_contacts_samples(
    samples: Sequence[Mapping[str, object]],
    plan: DomainPlan,
) -> int:
    if len(samples) < CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts Release Candidate requires at least five accepted samples",
        )
    expected_pack = plan.domain_pack_reference.to_record()
    expected_runtime = plan.runtime_contract.to_record()
    expected_capabilities = canonical_capability_references(
        tuple(plan.capability_references)
    )
    expected_components = [
        component.to_record() for component in plan.component_contracts
    ]
    recovery_count = 0
    plan_identities: set[tuple[object, object]] = set()
    for sample in samples:
        binding = _contacts_binding(sample)
        if binding.get("schema_version") != _CONTACTS_RELEASE_SAMPLE_SCHEMA:
            raise ContactsQualificationInsufficiency(
                "contacts_capability_evidence_incomplete",
                "Contacts sample evidence binding has an unsupported schema",
            )
        if (
            binding.get("domain_pack_reference") != expected_pack
            or binding.get("runtime_contract") != expected_runtime
            or binding.get("capability_references") != expected_capabilities
            or binding.get("component_contracts") != expected_components
            or binding.get("source") != plan.admitted_source.to_record()
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                "Contacts sample is bound to a different Pack, runtime, source, "
                "or capability catalog",
            )
        plan_binding = _mapping(binding.get("plan"))
        plan_identities.add((plan_binding.get("plan_id"), plan_binding.get("plan_hash")))
        if (
            plan_binding.get("plan_id") != plan.plan_id
            or plan_binding.get("plan_hash") != plan.plan_hash
            or plan_binding.get("plan_record") != plan.to_record()
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                "Contacts sample does not retain the exact Domain plan",
            )
        _validate_contacts_sample_semantics(sample, binding, plan)
        task_refs = binding.get("task_capability_references")
        assignment_refs = binding.get("assignment_capability_references")
        if not isinstance(task_refs, list) or not task_refs:
            raise ContactsQualificationInsufficiency(
                "contacts_capability_evidence_incomplete",
                "Contacts sample task capability references are missing",
            )
        if task_refs != assignment_refs:
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                "Contacts task and assignment capability references differ",
            )
        task_keys = {
            str(item.get("capability_key"))
            for item in task_refs
            if isinstance(item, Mapping)
        }
        if not task_keys.issubset(_CONTACTS_RELEASE_CAPABILITY_KEYS):
            raise ContactsQualificationInsufficiency(
                "contacts_capability_evidence_incomplete",
                "Contacts sample contains an unknown capability projection",
            )
        recovery = _mapping(binding.get("recovery"))
        if "contact_lookup_recovery" in task_keys:
            if (
                recovery.get("declared") is not True
                or recovery.get("verified") is not True
                or not _is_hash(recovery.get("initial_action_hash"))
                or not _is_hash(recovery.get("fallback_action_hash"))
                or not _is_hash(recovery.get("fallback_observation_hash"))
            ):
                raise ContactsQualificationInsufficiency(
                    "contacts_capability_evidence_incomplete",
                    "Contacts recovery evidence is not independently verified",
                )
            recovery_count += 1
        elif recovery.get("declared") is not False or recovery.get("verified") is not False:
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                "Contacts non-recovery sample carries recovery evidence",
            )
        _validate_contacts_assignment(binding, sample, plan)
        _validate_contacts_mutation(sample, plan)
    if len(plan_identities) != 1:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts accepted samples contain more than one plan identity",
        )
    if recovery_count < 1:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts release evidence contains no verified lookup recovery",
        )
    return recovery_count


def _validate_contacts_sample_semantics(
    sample: Mapping[str, object],
    binding: Mapping[str, object],
    plan: DomainPlan,
) -> None:
    task = _mapping(sample.get("task"))
    constraints = _mapping(task.get("constraints"))
    task_type = constraints.get("task_type")
    if task_type not in _CONTACTS_RELEASE_REQUIRED_TASK_TYPES:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts release samples must use canonical task projections",
        )
    required_tools = constraints.get("required_tools")
    expected_tools = _CONTACTS_RELEASE_REQUIRED_TOOLS[str(task_type)]
    if tuple(required_tools or ()) != expected_tools:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts sample required tools do not match its canonical task projection",
        )
    if task.get("domain") not in {None, "contacts_fixture", "contacts"}:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts sample declares a foreign domain",
        )
    declared_tools = {
        str(tool.get("name"))
        for tool in _records(sample.get("tools"))
        if isinstance(tool.get("name"), str)
    }
    if not set(expected_tools).issubset(declared_tools):
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts sample does not declare all required tools",
        )
    trajectory = sample.get("trajectory")
    if not isinstance(trajectory, Sequence) or isinstance(trajectory, (str, bytes)):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts sample trajectory is malformed",
        )
    actions = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "action"
    ]
    observations = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "observation"
    ]
    if not actions or not observations:
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts sample lacks executable action and observation evidence",
        )
    if any(event.get("tool") not in declared_tools for event in (*actions, *observations)):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts trajectory references an undeclared tool",
        )
    if any(event.get("tool") not in expected_tools for event in actions):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts trajectory tool sequence does not match its task projection",
        )
    final_events = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "final_response"
    ]
    if len(final_events) != 1 or final_events[0].get("content") != sample.get(
        "final_response"
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts sample final response evidence is incomplete",
        )
    verification = _mapping(sample.get("verification"))
    binding_verification = _mapping(binding.get("verification"))
    if (
        verification.get("passed") is not True
        or dict(verification) != dict(binding_verification)
        or binding.get("verification_hash") != canonical_domain_pack_hash(dict(verification))
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_non_passing",
            "Contacts sample verification is missing or does not match its binding",
        )
    verifier = _mapping(sample.get("verifier"))
    bound_verifier = _mapping(binding.get("verifier"))
    if (
        verifier.get("id") != bound_verifier.get("id")
        or verifier.get("version") != bound_verifier.get("version")
        or verification.get("verifier_id") != verifier.get("id")
        or verification.get("version") != verifier.get("version")
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts verifier evidence does not match the binding",
        )
    observed_values = _contacts_observed_values(observations)
    final_response = sample.get("final_response")
    expected_answer_hash = _mapping(binding.get("grounding")).get(
        "expected_answer_hash"
    )
    if (
        not isinstance(final_response, str)
        or not observed_values
        or not any(value in final_response for value in observed_values)
        or not _is_hash(expected_answer_hash)
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts final answer is not grounded in an observed contact value",
        )
    difficulty = _mapping(task.get("difficulty"))
    state_changes = difficulty.get("state_changes")
    if not isinstance(state_changes, int) or isinstance(state_changes, bool):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts sample state-change difficulty is malformed",
        )
    state_change_events = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "state_change"
    ]
    if state_changes != len(state_change_events):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts state-change count does not match the trajectory",
        )
    final_state = _mapping(binding.get("final_state"))
    grounding = _mapping(binding.get("grounding"))
    if (
        final_state.get("expected_state_hash") != grounding.get("expected_state_hash")
        or not _is_hash(final_state.get("verification_hash"))
        or final_state.get("verification_passed") is not True
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts final-state binding is incomplete",
        )
    if task_type == "contact_followup" and state_changes != 1:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts follow-up projection must contain one state change",
        )
    if task_type == "contact_lookup" and state_changes != 0:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts lookup projection must be read-only",
        )
    reconstructed_candidate = _reconstruct_contacts_candidate(sample, binding)
    task_contract = _mapping(binding.get("task_contract"))
    if task_contract.get("contract_hash") != contacts_task_contract_hash(
        reconstructed_candidate
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts task-contract hash does not match retained execution evidence",
        )
    contract = reconstructed_candidate.contract()
    expected_state = [
        {
            "check_type": state_check.check_type,
            "expected": dict(state_check.expected),
        }
        for state_check in contract.expected_state
    ]
    expected_grounding = {
        "primary_arguments_hash": canonical_domain_pack_hash(
            dict(contract.policy_hint.primary_arguments)
        ),
        "expected_state_hash": canonical_domain_pack_hash(expected_state),
        "expected_answer_hash": canonical_domain_pack_hash(
            contract.expected_outcome.final_answer_contains
        ),
    }
    if binding.get("grounding") != expected_grounding:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts grounding hashes do not match the retained task contract",
        )


def _reconstruct_contacts_candidate(
    sample: Mapping[str, object],
    binding: Mapping[str, object],
) -> CandidateTask:
    from synthesis.contact_mutations import prepare_contact_candidate
    from synthesis.domain_pack import DomainCapabilityReference
    task = _mapping(sample.get("task"))
    constraints = dict(_mapping(task.get("constraints")))
    difficulty = dict(_mapping(task.get("difficulty")))
    trajectory = _records(sample.get("trajectory"))
    first_action = next(
        (
            event
            for event in trajectory
            if event.get("type") == "action"
        ),
        None,
    )
    if not isinstance(first_action, Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts task-contract reconstruction lacks a primary action",
        )
    arguments = _mapping(first_action.get("arguments"))
    verification = _mapping(sample.get("verification"))
    checks = _records(verification.get("checks"))
    answer_check = next(
        (
            check
            for check in checks
            if check.get("name") == "final_response_contains_expected_answer"
        ),
        None,
    )
    expected_answer = answer_check.get("expected") if isinstance(answer_check, Mapping) else None
    if not isinstance(expected_answer, str) or not expected_answer:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts task-contract reconstruction lacks the expected answer",
        )
    expected_state: dict[str, object] = {}
    for check in checks:
        if check.get("name") == "contact_followup_state_matches_expected":
            expected = check.get("expected")
            if isinstance(expected, Mapping):
                expected_state["contact_followup"] = dict(expected)
    lineage = _mapping(sample.get("lineage"))
    seed_ids = lineage.get("seed_ids")
    if not isinstance(seed_ids, list) or any(
        not isinstance(seed_id, str) or not seed_id for seed_id in seed_ids
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts task-contract reconstruction lacks seed identity",
        )
    task_refs = _records(binding.get("task_capability_references"))
    try:
        capability_references = tuple(
            DomainCapabilityReference.from_record(reference)
            for reference in task_refs
        )
    except (DomainPackContractError, TypeError, ValueError):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts task-contract capability references are malformed",
        ) from None
    branch_plan = task.get("branch_plan")
    if not isinstance(branch_plan, Mapping):
        branch_plan = _contacts_branch_plan_from_assignment(binding)
    candidate = CandidateTask(
        candidate_id=_text(_mapping(binding.get("task_contract")).get("candidate_id")),
        instruction=_text(task.get("instruction")),
        constraints=constraints,
        difficulty=difficulty,
        tool_name=_text(first_action.get("tool")),
        arguments=dict(arguments),
        expected_answer=expected_answer,
        seed_ids=tuple(seed_ids),
        expected_state=expected_state or None,
        branch_plan=dict(branch_plan) if isinstance(branch_plan, Mapping) else None,
        capability_references=capability_references,
    )
    return prepare_contact_candidate(candidate)


def _contacts_branch_plan_from_assignment(
    binding: Mapping[str, object],
) -> Mapping[str, object] | None:
    assignment = _mapping_or_empty(binding.get("assignment"))
    catalog_record = _mapping(assignment.get("catalog"))
    dimensions = catalog_record
    cell_id = assignment.get("cell_id")
    catalog_version = dimensions.get("version")
    if not isinstance(cell_id, str) or not isinstance(catalog_version, str):
        return None
    try:
        catalog = resolve_domain_coverage_planning("contacts_fixture").resolve_catalog(
            catalog_version
        )
        cell = next(item for item in catalog.cells if item.cell_id == cell_id)
    except (StopIteration, TypeError, ValueError):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts recovery assignment does not select a known coverage cell",
        ) from None
    if cell.branch_plan is None:
        return None
    if catalog_record.get("branch_plan_hash") != canonical_coverage_hash(
        cell.branch_plan
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts recovery assignment branch plan has drifted",
        )
    return cell.branch_plan


def _validate_contacts_assignment(
    binding: Mapping[str, object],
    sample: Mapping[str, object],
    plan: DomainPlan,
) -> None:
    assignment = binding.get("assignment")
    if not isinstance(assignment, Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            "Contacts accepted sample has no coverage assignment",
        )
    if (
        assignment.get("schema_version") != "coverage_assignment_lineage_v1"
        or not isinstance(assignment.get("plan_id"), str)
        or not assignment.get("plan_id", "").startswith("coverage_plan_")
        or not _is_hash(assignment.get("plan_hash"))
        or not _is_hash(assignment.get("assignment_hash"))
        or assignment.get("assignment_id")
        != "coverage_assignment_"
        + str(assignment.get("assignment_hash", "")).removeprefix("sha256:")[:16]
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            "Contacts coverage assignment is malformed or bound to another plan",
        )
    catalog = _mapping(assignment.get("catalog"))
    assignment_refs = binding.get("assignment_capability_references")
    if catalog.get("capability_references") != assignment_refs:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts assignment capability membership is inconsistent",
        )
    grounding_scope = _mapping(assignment.get("grounding_scope"))
    scheduler = _mapping(assignment.get("scheduler"))
    if (
        scheduler.get("schema_version") != "coverage_scheduler_v1"
        or not isinstance(grounding_scope.get("context_key"), str)
        or not isinstance(grounding_scope.get("unit_index"), int)
        or isinstance(grounding_scope.get("unit_index"), bool)
        or not _is_hash(grounding_scope.get("grounding_hash"))
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            "Contacts assignment grounding scope is incomplete",
        )
    lineage = _mapping(_mapping(sample.get("lineage")).get("generator"))
    if lineage.get("coverage_assignment") != dict(assignment):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts sample assignment lineage differs from its evidence binding",
        )


def _validate_contacts_mutation(
    sample: Mapping[str, object],
    plan: DomainPlan,
) -> None:
    manifest_mutation = _mapping(plan.to_record()).get("plan_requirements")
    if not manifest_mutation:
        raise ContactsQualificationInsufficiency(
            "contacts_mutation_admission_incomplete",
            "Contacts plan does not retain mutation contract requirements",
        )
    task = _mapping(sample.get("task"))
    difficulty = _mapping(task.get("difficulty"))
    state_changes = difficulty.get("state_changes", 0)
    mutation = sample.get("mutation_admission")
    if state_changes:
        mutation_record = _mapping(mutation)
        if (
            mutation_record.get("mode") != "enforce"
            or mutation_record.get("admission_outcome") != "judge_supported"
            or mutation_record.get("model_independence") != "independent"
            or mutation_record.get("diagnostic_only") is not False
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_mutation_admission_incomplete",
                "Contacts state-changing sample was not independently admitted in enforce mode",
            )


def _validate_contacts_manifest_evidence(
    manifest: Mapping[str, object],
    plan: DomainPlan,
    samples: Sequence[Mapping[str, object]],
    recovery_count: int,
) -> None:
    raw = manifest.get("domain_capability_evidence")
    if not isinstance(raw, Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts manifest capability evidence is missing",
        )
    plan_binding = _mapping(raw.get("plan"))
    if (
        plan_binding.get("plan_id") != plan.plan_id
        or plan_binding.get("plan_hash") != plan.plan_hash
        or plan_binding.get("plan_record") != plan.to_record()
        or raw.get("domain_pack_reference") != plan.domain_pack_reference.to_record()
        or raw.get("runtime_contract") != plan.runtime_contract.to_record()
        or raw.get("capability_references")
        != canonical_capability_references(tuple(plan.capability_references))
        or raw.get("verified_recovery_samples") != recovery_count
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts manifest capability evidence is not bound to the exact samples",
        )
    counts = raw.get("accepted_capability_counts")
    if not isinstance(counts, Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts manifest capability counts are missing",
        )
    observed: dict[str, int] = {}
    for sample in samples:
        for reference in _records(_contacts_binding(sample).get("task_capability_references")):
            key = reference.get("capability_key")
            if isinstance(key, str):
                observed[key] = observed.get(key, 0) + 1
    if dict(sorted((str(key), int(value)) for key, value in counts.items())) != dict(
        sorted(observed.items())
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts manifest capability counts do not match accepted samples",
        )
    source_policy_hashes = manifest.get("source_policy_hashes")
    if source_policy_hashes != [plan.admitted_source.admission_policy_hash]:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts manifest source policy does not match the admitted plan source",
        )
    for sample in samples:
        environment = _mapping(sample.get("environment"))
        provenance = _mapping(environment.get("source_provenance"))
        if (
            provenance.get("source_bundle_id") != plan.admitted_source.source_id
            or provenance.get("source_policy_hash")
            != plan.admitted_source.admission_policy_hash
            or provenance.get("policy_outcome") != "allowed"
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_identity_mismatch",
                "Contacts sample source provenance does not match the admitted plan source",
            )


def _validate_contacts_quality_report(
    quality_report: Mapping[str, object],
    manifest: Mapping[str, object],
    samples: Sequence[Mapping[str, object]],
    rejections: Sequence[Mapping[str, object]],
) -> None:
    if quality_report.get("schema_version") != "quality_report_v1":
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_unknown_version",
            "Contacts quality report schema is unsupported",
        )
    counts = _mapping(quality_report.get("counts"))
    total = counts.get("total")
    accepted = counts.get("accepted")
    rejected = counts.get("rejected")
    executable = counts.get("executable")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in (total, accepted, rejected, executable)
    ) or accepted + rejected != total:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts quality report counts are malformed",
        )
    if (
        accepted != len(samples)
        or rejected != len(rejections)
        or accepted != manifest.get("accepted_count")
        or rejected != manifest.get("rejected_count")
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts quality report counts do not match the manifest",
        )
    rates = _mapping(quality_report.get("rates"))
    expected_success = accepted / executable if executable else 0.0
    expected_executable = executable / total if total else 0.0
    if not _close_number(rates.get("success_rate"), expected_success) or not _close_number(
        rates.get("executable_rate"), expected_executable
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts quality report rates do not match its counts",
        )
    if not isinstance(quality_report.get("slices"), Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_malformed",
            "Contacts quality report slices are unavailable",
        )


def _validate_contacts_release_completeness(
    release_report: Mapping[str, object],
) -> None:
    completeness = _mapping(release_report.get("release_completeness"))
    expected = contacts_release_candidate_profile()["completeness"]
    if completeness.get("thresholds") != expected:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts release completeness uses a non-Contacts threshold contract",
        )
    if _mapping(completeness.get("decision")).get("status") != "passed":
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_non_passing",
            "Contacts release completeness did not pass its exact threshold contract",
        )


def _validate_contacts_profile_decision_alignment(
    profile_decision_report: Mapping[str, object],
    *,
    quality_report: Mapping[str, object],
    manifest: Mapping[str, object],
) -> None:
    observed = _mapping(profile_decision_report.get("observed"))
    counts = _mapping(quality_report.get("counts"))
    rates = _mapping(quality_report.get("rates"))
    if (
        observed.get("total_candidates") != counts.get("total")
        or observed.get("accepted") != counts.get("accepted")
        or observed.get("rejected") != counts.get("rejected")
        or not _close_number(observed.get("success_rate"), rates.get("success_rate"))
        or not _close_number(observed.get("executable_rate"), rates.get("executable_rate"))
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts profile-decision evidence is not aligned with quality evidence",
        )
    if profile_decision_report.get("dataset_version") != manifest.get("dataset_version"):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts profile-decision dataset version is stale",
        )


def _validate_contacts_evaluation(
    evaluation_report: Mapping[str, object],
    plan: DomainPlan,
) -> None:
    suite = _mapping(evaluation_report.get("suite"))
    expected_suite = contacts_heldout_suite()
    if (
        suite.get("suite_id") != expected_suite.suite_id
        or suite.get("suite_version") != expected_suite.suite_version
        or suite.get("domain_id") != expected_suite.domain_id
        or suite.get("task_count") != len(expected_suite.tasks)
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts held-out suite identity does not match the current contract",
        )
    if evaluation_report.get("capability_references") != canonical_capability_references(
        tuple(plan.held_out_capability_references)
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_capability_evidence_incomplete",
            "Contacts held-out evaluation uses the wrong capability catalog",
        )
    plan_binding = _mapping(evaluation_report.get("plan_binding"))
    if (
        plan_binding.get("domain_pack_reference") != plan.domain_pack_reference.to_record()
        or plan_binding.get("runtime_contract") != plan.runtime_contract.to_record()
        or _mapping(plan_binding.get("plan")).get("plan_id") != plan.plan_id
        or _mapping(plan_binding.get("plan")).get("plan_hash") != plan.plan_hash
        or plan_binding.get("capability_references")
        != canonical_capability_references(tuple(plan.held_out_capability_references))
    ):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts held-out evaluation is not bound to the exact Domain plan",
        )
    expected_thresholds = {
        "mvp_min_heldout_pass_rate": 0.8,
        "max_regression_count": 0,
        "min_capability_pass_rates": {
            reference.capability_key: 1.0
            for reference in expected_suite.capability_references
        },
    }
    if evaluation_report.get("thresholds") != expected_thresholds:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts held-out thresholds do not match the Contacts contract",
        )
    if _mapping(evaluation_report.get("decision")).get("status") != "passed":
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_non_passing",
            "Contacts held-out evaluation did not pass",
        )
    results = {
        str(item.get("task_id")): item
        for item in _records(evaluation_report.get("task_results"))
    }
    if set(results) != {task.task_id for task in expected_suite.tasks}:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts held-out task result set is incomplete",
        )
    for task in expected_suite.tasks:
        result = results[task.task_id]
        expected_refs = canonical_capability_references(tuple(task.capability_references))
        if (
            result.get("status") != "passed"
            or result.get("capability_references") != expected_refs
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_non_passing",
                f"Contacts held-out task {task.task_id} did not pass its capability contract",
            )
        if task.expected_outcome == "controlled_failure" and (
            result.get("observed_failure_cause") != "verification_failed"
            or result.get("expected_outcome") != "controlled_failure"
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_non_passing",
                "Contacts missing-contact safe-failure evidence is not established",
            )


def _validate_contacts_coverage_contract(
    *,
    coverage_plan: Mapping[str, object],
    coverage_evidence: Mapping[str, object],
    run_profile: Mapping[str, object],
) -> None:
    planning = resolve_domain_coverage_planning("contacts_fixture")
    expected_profile = planning.resolve_profile(
        CONTACTS_RELEASE_COVERAGE_PROFILE_ID,
        CONTACTS_RELEASE_COVERAGE_PROFILE_VERSION,
    )
    expected_catalog = planning.resolve_catalog(expected_profile.catalog_version)
    plan_catalog = _mapping(coverage_plan.get("catalog"))
    plan_profile = _mapping(coverage_plan.get("coverage_profile"))
    if (
        coverage_plan.get("schema_version") != "coverage_plan_v1"
        or coverage_plan.get("domain_id") != "contacts_fixture"
        or plan_catalog.get("catalog_id") != expected_catalog.catalog_id
        or plan_catalog.get("version") != expected_catalog.version
        or plan_catalog.get("catalog_hash")
        != canonical_coverage_hash(expected_catalog.canonical())
        or plan_profile.get("profile_id") != expected_profile.profile_id
        or plan_profile.get("version") != expected_profile.version
        or plan_profile.get("profile_hash")
        != canonical_coverage_hash(expected_profile.canonical())
        or coverage_plan.get("target_accepted_sample_count")
        != CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES
        or coverage_plan.get("target_candidate_count")
        != CONTACTS_RELEASE_TARGET_CANDIDATES
        or "enable_branching" not in _profile_enabled_features(run_profile)
    ):
        feature_ok = "enable_branching" in _profile_enabled_features(run_profile)
        if not feature_ok or (
            plan_profile.get("profile_id") != expected_profile.profile_id
            or plan_profile.get("version") != expected_profile.version
        ):
            raise ContactsQualificationInsufficiency(
                "contacts_coverage_evidence_incomplete",
                "Contacts coverage plan does not select the exact release contract",
            )
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            "Contacts coverage plan identity or target has drifted",
        )
    fulfillment = _mapping(coverage_evidence.get("fulfillment"))
    if fulfillment.get("status") != "fulfilled" or fulfillment.get(
        "mandatory_fulfilled"
    ) is not True or fulfillment.get("target_fulfilled") is not True:
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            "Contacts coverage fulfillment is incomplete",
        )


def _contacts_release_profile_reasons(
    *,
    manifest: Mapping[str, object],
    run_profile: Mapping[str, object],
    coverage_plan: Mapping[str, object],
    pack_profile: Mapping[str, object],
    plan: DomainPlan,
) -> list[str]:
    reasons = _contacts_profile_shape_reasons(run_profile)
    selected_profile = _mapping(run_profile.get("coverage_profile"))
    if selected_profile.get("profile_id") != CONTACTS_RELEASE_COVERAGE_PROFILE_ID:
        reasons.append("coverage profile id is not the Contacts release selection")
    if pack_profile.get("profile_id") not in {None, CONTACTS_RELEASE_CANDIDATE_PROFILE_ID}:
        reasons.append("release pack profile is not the Contacts release selection")
    if coverage_plan.get("domain_id") != "contacts_fixture":
        reasons.append("coverage plan is not a Contacts plan")
    if plan.domain_pack_reference.domain_pack_id != "contacts":
        reasons.append("Domain plan is not owned by Contacts")
    if manifest.get("dataset_version") != CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION:
        reasons.append("dataset version is not the versioned Contacts release subject")
    return reasons


def _contacts_machine_gates(
    *,
    manifest: Mapping[str, object],
    samples: Sequence[Mapping[str, object]],
    quality_report: Mapping[str, object],
    evaluation_report: Mapping[str, object],
    profile_decision_report: Mapping[str, object],
    release_report: Mapping[str, object],
    coverage_evidence: Mapping[str, object],
    pack_verification: Mapping[str, object],
    profile_reasons: Sequence[str],
) -> dict[str, object]:
    decisions = _mapping(profile_decision_report.get("decisions"))
    release_decisions = _mapping(release_report.get("decisions"))
    quality_decision = _mapping(decisions.get("mvp_quality_floor"))
    promotion = _mapping(decisions.get("profile_promotion"))
    release_decision = _mapping(release_decisions.get("dataset_release"))
    evaluation_decision = _mapping(evaluation_report.get("decision"))
    source_ok = _contacts_source_is_valid(manifest)
    mutation_ok = _contacts_manifest_mutation_is_valid(manifest, samples)
    coverage_ok = (
        _mapping(coverage_evidence.get("fulfillment")).get("status")
        == "fulfilled"
    )
    return {
        "contract": _machine_gate(
            "insufficient_evidence" if profile_reasons else "passed",
            reasons=list(profile_reasons) or [
                "exact Contacts release profile, Pack, runtime, and plan selected"
            ],
        ),
        "execution": _machine_gate("passed" if samples else "insufficient_evidence"),
        "verification": _machine_gate(
            "passed"
            if all(
                _mapping(sample.get("verification")).get("passed") is True
                for sample in samples
            )
            else "insufficient_evidence"
        ),
        "grounding": _machine_gate(
            "passed"
            if all(
                _is_hash(_mapping(_contacts_binding(sample).get("grounding")).get(field))
                for sample in samples
                for field in (
                    "primary_arguments_hash",
                    "expected_state_hash",
                    "expected_answer_hash",
                )
            )
            else "insufficient_evidence"
        ),
        "quality": _machine_gate(
            _status_from_record(quality_decision) or "insufficient_evidence"
        ),
        "provenance": _machine_gate(
            "passed"
            if all(
                _contacts_binding(sample).get("domain_pack_reference")
                for sample in samples
            )
            else "insufficient_evidence"
        ),
        "source": _machine_gate(
            "passed" if source_ok else "insufficient_evidence"
        ),
        "mutation": _machine_gate(
            "passed" if mutation_ok else "insufficient_evidence"
        ),
        "coverage": _machine_gate(
            "passed" if coverage_ok else "insufficient_evidence"
        ),
        "held_out": _machine_gate(
            _status_from_record(evaluation_decision) or "insufficient_evidence"
        ),
        "profile_promotion": _machine_gate(
            _status_from_record(promotion) or "insufficient_evidence"
        ),
        "dataset_release": _machine_gate(
            _status_from_record(release_decision) or "insufficient_evidence"
        ),
        "artifact_integrity": _machine_gate(
            _status_from_record(pack_verification) or "insufficient_evidence"
        ),
    }


def _contacts_manifest_mutation_is_valid(
    manifest: Mapping[str, object],
    samples: Sequence[Mapping[str, object]],
) -> bool:
    if manifest.get("schema_version") != "dataset_manifest_v2":
        return False
    profile = _mapping(manifest.get("run_profile"))
    mutation = _mapping(profile.get("mutation_admission"))
    if mutation.get("mode") != "enforce":
        return False
    artifacts = _mapping(manifest.get("artifacts"))
    if not isinstance(artifacts.get("mutation_admission_report"), str):
        return False
    for sample in samples:
        difficulty = _mapping(_mapping(sample.get("task")).get("difficulty"))
        if difficulty.get("state_changes"):
            evidence = _mapping(sample.get("mutation_admission"))
            if (
                evidence.get("mode") != "enforce"
                or evidence.get("admission_outcome") != "judge_supported"
                or evidence.get("model_independence") != "independent"
            ):
                return False
    return True


def _contacts_source_is_valid(manifest: Mapping[str, object]) -> bool:
    hashes = manifest.get("source_policy_hashes")
    if not isinstance(hashes, list) or not hashes or not all(_is_hash(value) for value in hashes):
        return False
    orchestration = manifest.get("orchestration")
    if orchestration is None:
        return True
    record = _mapping(orchestration)
    return (
        record.get("status") == "completed"
        and record.get("completeness") == "complete"
        and record.get("release_eligible") is not False
    )


def _contacts_evidence_graph(
    *,
    base_dir: Path,
    artifacts: Mapping[str, object],
    manifest: Mapping[str, object],
    audit_path: Path,
    release_pack_hash: str,
    release_pack_byte_count: int,
) -> tuple[dict[str, object], ...]:
    nodes: list[dict[str, object]] = [
        {
            "artifact_id": "release_pack",
            "artifact_schema_version": "dataset_release_pack_v2",
            "content_hash": release_pack_hash,
            "byte_count": release_pack_byte_count,
            "status": "active",
        }
    ]
    for key, raw in sorted(artifacts.items()):
        if not isinstance(raw, Mapping):
            continue
        path_value = raw.get("path")
        if not isinstance(path_value, str):
            continue
        path = base_dir / path_value
        digest = _hash_file_if_readable(path)
        if digest is None:
            raise ContactsQualificationInsufficiency(
                "contacts_evidence_missing",
                f"Contacts release artifact is missing: {key}",
            )
        if digest[1] == 0:
            continue
        nodes.append(
            {
                "artifact_id": "release_" + _safe_evidence_id(key),
                "artifact_schema_version": _schema_from_artifact(path, key),
                "content_hash": digest[0],
                "byte_count": digest[1],
                "status": "active",
            }
        )
    audit_digest = _hash_file_if_readable(audit_path)
    if audit_digest is None:
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_missing",
            "Contacts release-quality audit is missing",
        )
    nodes.append(
        {
            "artifact_id": "release_quality_audit",
            "artifact_schema_version": "release_quality_audit_v1",
            "content_hash": audit_digest[0],
            "byte_count": audit_digest[1],
            "status": "active",
        }
    )
    manifest_artifacts = _mapping(manifest.get("artifacts"))
    for key in ("coverage_plan", "coverage_evidence"):
        raw_path = manifest_artifacts.get(key)
        if not isinstance(raw_path, str):
            raise ContactsQualificationInsufficiency(
                "contacts_coverage_evidence_incomplete",
                f"Contacts manifest does not reference {key}",
            )
        path = base_dir / raw_path
        digest = _hash_file_if_readable(path)
        if digest is None:
            raise ContactsQualificationInsufficiency(
                "contacts_coverage_evidence_incomplete",
                f"Contacts coverage artifact is missing: {key}",
            )
        nodes.append(
            {
                "artifact_id": "release_" + key,
                "artifact_schema_version": _schema_from_artifact(path, key),
                "content_hash": digest[0],
                "byte_count": digest[1],
                "status": "active",
            }
        )
    return tuple(nodes)


def _contacts_binding(sample: Mapping[str, object]) -> Mapping[str, object]:
    binding = sample.get("contacts_evidence")
    if not isinstance(binding, Mapping):
        binding = sample.get("domain_evidence")
    if not isinstance(binding, Mapping):
        raise ContactsQualificationInsufficiency(
            "contacts_plan_evidence_missing",
            "Contacts sample does not contain canonical evidence binding",
        )
    return binding


def _contacts_observed_values(observations: Sequence[object]) -> set[str]:
    values: set[str] = set()
    for event in observations:
        observation = event.get("observation") if isinstance(event, Mapping) else None
        _collect_observed_values(observation, values)
    return values


def _collect_observed_values(value: object, values: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"email", "name"} and isinstance(child, str):
                values.add(child)
            _collect_observed_values(child, values)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _collect_observed_values(child, values)


def _qualification_machine_gate_names() -> tuple[str, ...]:
    from synthesis.qualification import RELEASE_CANDIDATE_MACHINE_GATES

    return tuple(RELEASE_CANDIDATE_MACHINE_GATES)


def _machine_gate(status: str, **fields: object) -> dict[str, object]:
    return {
        "schema_version": "qualification_machine_gate_v1",
        "status": status,
        **fields,
    }


def _status_from_record(record: Mapping[str, object]) -> str | None:
    for value in (
        record.get("status"),
        _mapping_or_empty(record.get("decision")).get("status"),
        _mapping_or_empty(record.get("verification")).get("status"),
        _mapping_or_empty(record.get("result")).get("status"),
    ):
        if isinstance(value, str):
            return value
    return None


def _qualification_profile(profile: Mapping[str, object]) -> dict[str, object]:
    fields = (
        "schema_version",
        "profile_id",
        "generation_mode",
        "profile_purpose",
        "target_candidate_count",
        "config_hash",
        "coverage_profile",
        "mutation_admission",
    )
    return {field: profile[field] for field in fields if field in profile}


def _profile_generation_mode(profile: Mapping[str, object]) -> object:
    if "generation_mode" in profile:
        return profile.get("generation_mode")
    return _mapping(profile.get("generation")).get("mode")


def _profile_generation_target(profile: Mapping[str, object]) -> object:
    if "target_candidate_count" in profile:
        return profile.get("target_candidate_count")
    return _mapping(profile.get("generation")).get("target_candidate_count")


def _profile_enabled_features(profile: Mapping[str, object]) -> set[str]:
    enabled = profile.get("enabled_features")
    if isinstance(enabled, list):
        return {str(item) for item in enabled if isinstance(item, str)}
    raw_features = profile.get("features")
    if not isinstance(raw_features, Mapping):
        return set()
    return {
        str(key)
        for key, value in raw_features.items()
        if isinstance(key, str) and value is True
    }


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value)


def _load_pack_json(
    base_dir: Path,
    artifacts: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    raw = _mapping(artifacts.get(key))
    return _load_json_mapping(base_dir / _text(raw.get("path")))


def _load_manifest_json(
    base_dir: Path,
    artifacts: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    raw_path = artifacts.get(key)
    if not isinstance(raw_path, str):
        raise ContactsQualificationInsufficiency(
            "contacts_coverage_evidence_incomplete",
            f"Contacts manifest artifact reference is missing: {key}",
        )
    return _load_json_mapping(base_dir / raw_path)


def _load_jsonl_artifact(
    base_dir: Path,
    artifacts: Mapping[str, object],
    key: str,
) -> list[Mapping[str, object]]:
    raw = _mapping(artifacts.get(key))
    path = base_dir / _text(raw.get("path"))
    records: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            records.append(_mapping(json.loads(line)))
    return records


def _schema_from_artifact(path: Path, key: str) -> str:
    if path.suffix == ".json":
        try:
            schema = _load_json_mapping(path).get("schema_version")
        except (OSError, json.JSONDecodeError, ValueError):
            schema = None
        if isinstance(schema, str) and schema:
            return schema
    return "release_" + _safe_evidence_id(key) + "_v1"


def _hash_file_if_readable(path: Path) -> tuple[str, int] | None:
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return "sha256:" + hashlib.sha256(content).hexdigest(), len(content)


def _report_dataset_version(
    record: Mapping[str, object],
    manifest: Mapping[str, object],
    label: str,
) -> None:
    if record.get("dataset_version") != manifest.get("dataset_version"):
        raise ContactsQualificationInsufficiency(
            "contacts_evidence_identity_mismatch",
            f"{label} dataset version is stale or foreign",
        )


def _contacts_insufficient_report(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    reason_code: str,
    reason: str,
) -> dict[str, object]:
    from synthesis.qualification import (
        QualificationBinding,
        _decision_entry,
        _report,
    )
    try:
        pack = build_contacts_domain_pack()
        source = AdmittedSource(
            source_id="contacts_qualification_unavailable_source",
            source_schema_version="source_bundle_v1",
            source_content_hash=canonical_domain_pack_hash(
                {"manifest": manifest_path.name}
            ),
            admission_policy_id="source_governance_v1",
            admission_policy_hash=canonical_domain_pack_hash(
                {"policy": "unavailable"}
            ),
        )
        plan = pack.plan(
            # Import lazily to keep this failure path independent of runtime
            # construction.
            _contacts_planning_intent(pack),
            source,
        )
        if not isinstance(plan, DomainPlan):
            raise ValueError("Contacts fallback plan is unavailable")
        digest = _hash_file_if_readable(release_pack_path)
        pack_hash = digest[0] if digest is not None else "sha256:" + "0" * 64
        byte_count = max(digest[1], 1) if digest is not None else 1
        binding = QualificationBinding.from_plan(
            plan,
            release_pack_hash=pack_hash,
            release_pack_byte_count=byte_count,
            profile={
                "schema_version": "run_profile_v4",
                "profile_id": CONTACTS_RELEASE_CANDIDATE_PROFILE_ID,
                "profile_purpose": "release_candidate",
                "generation_mode": "unknown",
            },
        )
        entry = _decision_entry(
            binding=binding,
            attempted_qualification="release_candidate",
            status="insufficient_evidence",
            effective_qualification="unqualified",
            reason_codes=(reason_code,),
            reasons=(reason,),
            evidence={},
        )
        return _report(
            binding=binding,
            historical_decisions=[],
            attempted_qualification="release_candidate",
            status="insufficient_evidence",
            effective_qualification="unqualified",
            reason_codes=(reason_code,),
            reasons=(reason,),
            invalidated=set(),
            appended_entry=entry,
        )
    except Exception:
        # The fallback itself must remain a bounded, validated report.  A
        # current Contacts plan is deterministic, so this branch is only a
        # defensive guard for unexpected contract drift.
        raise


def _contacts_planning_intent(pack: object) -> object:
    from synthesis.contacts_domain_pack import contacts_planning_intent

    return contacts_planning_intent(pack)  # type: ignore[arg-type]


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected record sequence")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError("record sequence contains a non-object")
    return list(value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("expected non-empty text")
    return value


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _safe_evidence_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.:-]+", "_", value.lower()).strip("_")
    return normalized or "evidence"


def _close_number(actual: object, expected: object) -> bool:
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return False
    if not isinstance(expected, (int, float)) or isinstance(expected, bool):
        return False
    return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)


def canonical_coverage_hash(value: object) -> str:
    from synthesis.coverage import canonical_coverage_hash as coverage_hash

    return coverage_hash(value)


if __name__ == "__main__":
    raise SystemExit("synthesis.contacts_qualification is a library module")
