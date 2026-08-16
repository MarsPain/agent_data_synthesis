"""Pure publication-governance and external-authority verification.

This module is deliberately a verifier, not a publication service.  It turns a
content-addressed evidence bundle into a bounded decision and never copies a
release, changes access, mutates review state, or talks to an external system.
Authority records contain opaque principal and key identifiers only.  The
verifier receives trusted key material out of band and retains no credentials
in the evidence it returns.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import base64
import zlib
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    validate_release_quality_audit_record,
    validate_release_review_item_record,
    validate_review_resolution_report_record,
)
from synthesis.domain_pack import (
    DomainPackContractError,
    canonical_domain_pack_hash as _strict_canonical_domain_pack_hash,
    canonical_domain_pack_json,
)


PUBLICATION_GOVERNANCE_SCHEMA_VERSION = "publication_governance_v1"
AUTHORITY_POLICY_SCHEMA_VERSION = "authority_policy_v1"
AUTHORITY_ATTESTATION_SCHEMA_VERSION = "authority_attestation_v1"
RISK_ACCEPTANCE_SCHEMA_VERSION = "risk_acceptance_v1"
PUBLICATION_APPROVAL_SCHEMA_VERSION = "publication_approval_v1"
REVOCATION_EVIDENCE_SCHEMA_VERSION = "revocation_evidence_v1"
PUBLISHABILITY_BUNDLE_SCHEMA_VERSION = "publishability_bundle_v1"
PUBLISHABILITY_DECISION_SCHEMA_VERSION = "publishability_decision_v1"
PUBLISHABILITY_GATE_SCHEMA_VERSION = "qualification_publishability_v1"
PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION = "publishability_review_item_v1"
PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE = 2048
PUBLISHABILITY_GATE_BUNDLE_MAX_CHUNKS = 128
PUBLISHABILITY_GATE_BUNDLE_MAX_ENCODED_BYTES = 262144
PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES = 2_000_000
RELEASE_CANDIDATE_REFERENCE_SCHEMA_VERSION = "release_candidate_reference_v1"
RELEASE_CANDIDATE_INLINE_MAX_BYTES = 32768
PUBLICATION_GOVERNANCE_FILENAME = "publication_governance.json"
AUTHORITY_POLICY_FILENAME = "authority_policy.json"
REVOCATION_EVIDENCE_FILENAME = "revocation_evidence.json"
PUBLISHABILITY_BUNDLE_FILENAME = "publishability_bundle.json"
PUBLISHABILITY_REPORT_FILENAME = "publishability_decision.json"

PUBLISHABILITY_STATUSES = {"passed", "denied", "insufficient_evidence"}
PUBLISHABILITY_EVIDENCE_CLASSES = {
    "real",
    "real_machine",
    "machine",
    "conformance_fixture",
    "fixture",
    "synthetic_fixture",
}
NON_QUALIFYING_EVIDENCE_CLASSES = {
    "conformance_fixture",
    "fixture",
    "synthetic_fixture",
}

GOVERNANCE_CHECKS = (
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
HARD_GOVERNANCE_CHECKS = frozenset(GOVERNANCE_CHECKS)
GOVERNANCE_CHECK_STATUSES = {
    "passed",
    "not_applicable",
    "watch",
    "failed",
    "blocked",
    "insufficient_evidence",
    "unknown",
}
AUTHORITY_ROLES = {"risk_owner", "publication_approver", "revocation_authority"}
RISK_SEVERITIES = {"low", "medium", "high", "critical"}
REVIEW_CLEAR_OUTCOMES = {"cleared", "cleared_inapplicable", "not_applicable"}
REVIEW_BLOCKING_OUTCOMES = {"confirmed_issue", "needs_follow_up"}
REDISTRIBUTION_LEVELS = {
    "none": 0,
    "same_audience": 1,
    "same_scope": 2,
    "unrestricted": 3,
}
ACCESS_LEVELS = {
    "private": 0,
    "restricted": 1,
    "internal": 2,
    "external": 3,
    "public": 4,
}

PUBLISHABILITY_REASON_CODES = frozenset(
    {
        "publishability_passed",
        "evidence_malformed",
        "evidence_missing",
        "evidence_incomplete",
        "evidence_unknown_version",
        "evidence_identity_mismatch",
        "evidence_hash_mismatch",
        "evidence_origin_untrusted",
        "evidence_expired",
        "evidence_revoked",
        "release_candidate_missing",
        "release_candidate_non_passing",
        "release_pack_unverified",
        "release_pack_verification_untrusted",
        "governance_missing",
        "governance_hard_gate_failed",
        "governance_incomplete",
        "audit_missing",
        "audit_not_clear",
        "review_missing",
        "review_pending",
        "review_blocked",
        "review_confirmed_issue",
        "review_follow_up_required",
        "review_insufficient_evidence",
        "review_finding_uncovered",
        "review_identity_mismatch",
        "risk_acceptance_missing",
        "risk_acceptance_invalid",
        "risk_acceptance_expired",
        "risk_acceptance_revoked",
        "risk_acceptance_scope_mismatch",
        "risk_acceptance_hard_gate",
        "approval_missing",
        "approval_invalid",
        "approval_expired",
        "approval_revoked",
        "authority_policy_missing",
        "authority_policy_invalid",
        "authority_policy_expired",
        "authority_principal_unknown",
        "authority_role_mismatch",
        "authority_key_mismatch",
        "authority_policy_mismatch",
        "authority_policy_untrusted",
        "authority_signature_invalid",
        "authority_attestation_missing",
        "authority_revoked",
        "authority_grant_expired",
        "revocation_evidence_missing",
        "revocation_evidence_invalid",
        "scope_invalid",
        "scope_mismatch",
        "bundle_hash_mismatch",
        "bundle_subject_mismatch",
        "bundle_approval_mismatch",
        "hard_gate_not_waivable",
        "separation_of_duties_violation",
        "validity_missing",
        "validity_expired",
        "non_qualifying_evidence_class",
        "authority_grant_not_yet_valid",
    }
)

AUDIT_RISK_FACTS: dict[str, tuple[str, str]] = {
    "small_release_size": ("medium", "bounded_small_release"),
    "exact_duplicate_rate": ("medium", "bounded_exact_duplicate"),
    "task_type_concentration": ("medium", "bounded_task_type_concentration"),
    "tool_combination_concentration": (
        "medium",
        "bounded_tool_combination_concentration",
    ),
    "duplicate_family": ("medium", "bounded_duplicate_family"),
}

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}$")
class PublishabilityContractError(ValueError):
    """A bounded, non-sensitive publishability contract failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def canonical_domain_pack_hash(value: object) -> str:
    """Hash publishability evidence while preserving the shared safety checks.

    Existing release audit records legitimately contain finite rate floats,
    while the Domain Pack canonical writer intentionally accepts only the
    smaller integer/string contract.  Floats are converted to an explicit,
    lossless tagged string only for this evidence namespace; unsafe values and
    non-finite numbers still fail closed through the shared canonical writer.
    """

    try:
        return _strict_canonical_domain_pack_hash(value)
    except DomainPackContractError:
        if not _contains_finite_float(value):
            raise
        return _strict_canonical_domain_pack_hash(_normalize_float_values(value))


def _contains_finite_float(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_finite_float(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_finite_float(child) for child in value)
    return False


def _normalize_float_values(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PublishabilityContractError("evidence_malformed")
        return {"__finite_float__": repr(value)}
    if isinstance(value, Mapping):
        return {key: _normalize_float_values(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalize_float_values(child) for child in value]
    return value


def fingerprint_for_key(key: str | bytes) -> str:
    """Return the content fingerprint for out-of-band authority key material."""

    raw = key.encode("utf-8") if isinstance(key, str) else key
    if not isinstance(raw, bytes) or not raw:
        raise PublishabilityContractError("authority_key_mismatch")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def normalize_distribution_scope(scope: Mapping[str, object]) -> dict[str, object]:
    """Normalize the five-dimensional distribution scope used by all records."""

    if not isinstance(scope, Mapping):
        raise PublishabilityContractError("scope_invalid")
    if set(scope) != {"audience", "purpose", "access", "retention", "redistribution"}:
        raise PublishabilityContractError("scope_invalid")
    audience = _string_list(scope.get("audience"), "scope_invalid")
    purpose = _string_list(scope.get("purpose"), "scope_invalid")
    if not audience or not purpose:
        raise PublishabilityContractError("scope_invalid")
    access = scope.get("access")
    if not isinstance(access, str) or access not in ACCESS_LEVELS:
        raise PublishabilityContractError("scope_invalid")
    retention = _normalize_retention(scope.get("retention"))
    redistribution = scope.get("redistribution")
    if not isinstance(redistribution, str) or redistribution not in REDISTRIBUTION_LEVELS:
        raise PublishabilityContractError("scope_invalid")
    return {
        "audience": sorted(set(audience)),
        "purpose": sorted(set(purpose)),
        "access": access,
        "retention": retention,
        "redistribution": redistribution,
    }


def scope_is_subset(
    requested_scope: Mapping[str, object],
    approved_scope: Mapping[str, object],
) -> bool:
    """Return whether a requested use is no broader than an approved scope."""

    try:
        requested = normalize_distribution_scope(requested_scope)
        approved = normalize_distribution_scope(approved_scope)
    except PublishabilityContractError:
        return False
    requested_audience = set(requested["audience"])
    approved_audience = set(approved["audience"])
    requested_purpose = set(requested["purpose"])
    approved_purpose = set(approved["purpose"])
    if not requested_audience <= approved_audience:
        return False
    if not requested_purpose <= approved_purpose:
        return False
    if ACCESS_LEVELS[str(requested["access"])] > ACCESS_LEVELS[str(approved["access"])]:
        return False
    requested_retention = requested["retention"]
    approved_retention = approved["retention"]
    assert isinstance(requested_retention, Mapping)
    assert isinstance(approved_retention, Mapping)
    if int(requested_retention["max_days"]) > int(approved_retention["max_days"]):
        return False
    return REDISTRIBUTION_LEVELS[str(requested["redistribution"])] <= REDISTRIBUTION_LEVELS[
        str(approved["redistribution"])
    ]


is_scope_subset = scope_is_subset


def publishability_subject_from_release_candidate(
    release_candidate: Mapping[str, object],
    *,
    release_pack: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Extract the exact immutable subject from a validated RC report."""

    _validate_release_candidate_report(release_candidate)
    binding = _mapping(release_candidate.get("qualification_binding"), "evidence_malformed")
    subject = _mapping(release_candidate.get("subject"), "evidence_malformed")
    domain_pack_reference = _mapping(
        binding.get("domain_pack_reference"),
        "evidence_malformed",
    )
    release_pack_hash = _hash_value(binding.get("release_pack_hash"))
    byte_count = _positive_int(binding.get("release_pack_byte_count"))
    profile = _mapping(binding.get("profile"), "evidence_malformed")
    declared_dataset_version = profile.get("dataset_version")
    if not isinstance(declared_dataset_version, str):
        supplied_dataset_version = (
            release_pack.get("dataset_version")
            if isinstance(release_pack, Mapping)
            else None
        )
        declared_dataset_version = (
            supplied_dataset_version
            if isinstance(supplied_dataset_version, str)
            else "unknown_dataset"
        )
    pack_reference = _release_pack_reference(
        release_pack,
        release_pack_hash=release_pack_hash,
        byte_count=byte_count,
        dataset_version=declared_dataset_version,
    )
    subject_record = {
        "subject_id": _identifier(subject.get("subject_id")),
        "subject_hash": _hash_value(subject.get("subject_hash")),
        "release_id": str(pack_reference["release_id"]),
        "release_pack_hash": release_pack_hash,
        "release_pack_byte_count": byte_count,
        "dataset_version": str(pack_reference["dataset_version"]),
        "domain_pack_reference": domain_pack_reference,
        "plan_id": _identifier(binding.get("plan_id")),
        "plan_hash": _hash_value(binding.get("plan_hash")),
    }
    return _normalize_subject(subject_record)


def build_publication_governance_report(
    *,
    subject: Mapping[str, object],
    proposed_scope: Mapping[str, object],
    checks: Mapping[str, Mapping[str, object]],
    findings: Sequence[Mapping[str, object]] = (),
    known_limitations: Sequence[str] = (),
    status: str | None = None,
) -> dict[str, object]:
    normalized_subject = _normalize_subject(subject)
    normalized_scope = normalize_distribution_scope(proposed_scope)
    normalized_checks = _normalize_governance_checks(checks)
    normalized_findings = _normalize_findings(findings)
    derived_status = _governance_status(normalized_checks, normalized_findings)
    if status is not None and status not in {
        "clear",
        "watch",
        "blocked",
        "insufficient_evidence",
    }:
        raise PublishabilityContractError("governance_incomplete")
    record: dict[str, object] = {
        "schema_version": PUBLICATION_GOVERNANCE_SCHEMA_VERSION,
        "subject": normalized_subject,
        "proposed_scope": normalized_scope,
        "checks": normalized_checks,
        "findings": normalized_findings,
        "known_limitations": _bounded_string_list(known_limitations),
        "status": status or derived_status,
    }
    return _with_content_identity(
        record,
        id_field="governance_id",
        hash_field="governance_hash",
        prefix="publication_governance_",
    )


build_publication_governance = build_publication_governance_report


def build_publishability_review_item(
    finding: Mapping[str, object],
) -> dict[str, object]:
    """Create a versioned review item for one governance finding."""

    normalized = _normalize_findings([finding])
    if len(normalized) != 1:
        raise PublishabilityContractError("review_insufficient_evidence")
    content = {
        "schema_version": PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION,
        "finding_id": normalized[0]["finding_id"],
        "category": normalized[0]["category"],
        "severity": normalized[0]["severity"],
        "reason_code": normalized[0]["reason_code"],
        "source": "publication_governance",
    }
    digest = canonical_domain_pack_hash(content)
    return {
        **content,
        "review_item_id": "publication_review_item_" + digest.removeprefix("sha256:")[:16],
    }


build_publishability_review_item_record = build_publishability_review_item


def build_authority_policy(
    *,
    policy_id: str,
    policy_version: str,
    trust_root: Mapping[str, object],
    grants: Sequence[Mapping[str, object]],
    separation_of_duties: Mapping[str, object],
    valid_from: str,
    expires_at: str,
) -> dict[str, object]:
    normalized_root = _normalize_trust_root(trust_root)
    normalized_grants = _normalize_grants(grants)
    _ensure_grant_keys(normalized_root, normalized_grants)
    record: dict[str, object] = {
        "schema_version": AUTHORITY_POLICY_SCHEMA_VERSION,
        "policy_id": _identifier(policy_id),
        "policy_version": _version(policy_version),
        "trust_root": normalized_root,
        "grants": normalized_grants,
        "separation_of_duties": _normalize_separation_policy(separation_of_duties),
        "valid_from": _timestamp(valid_from),
        "expires_at": _timestamp(expires_at),
    }
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["valid_from"]):
        raise PublishabilityContractError("authority_policy_invalid")
    return _with_content_identity(
        record,
        id_field="policy_id",
        hash_field="policy_hash",
        prefix="authority_policy_",
        preserve_id=True,
    )


def build_authenticated_attestation(
    payload: Mapping[str, object],
    *,
    principal_id: str,
    key_id: str,
    signing_key: str | bytes,
) -> dict[str, object]:
    """Create the local testable equivalent-attestation envelope.

    The key is an input to the signer/verifier boundary and is never copied to
    the resulting evidence.  Production integrations may replace this helper
    with an external verifier while keeping the same attestation fields.
    """

    payload_hash = canonical_domain_pack_hash(dict(payload))
    signing_payload = {
        "schema_version": AUTHORITY_ATTESTATION_SCHEMA_VERSION,
        "algorithm": "hmac-sha256",
        "principal_id": _identifier(principal_id),
        "key_id": _identifier(key_id),
        "payload_hash": payload_hash,
    }
    signature = _hmac_signature(signing_payload, signing_key)
    return {
        **signing_payload,
        "signature": signature,
    }


def build_risk_acceptance(
    *,
    subject: Mapping[str, object],
    findings: Sequence[Mapping[str, object]],
    permitted_scope: Mapping[str, object],
    authority_policy: Mapping[str, object],
    principal_id: str,
    key_id: str,
    issued_at: str,
    expires_at: str,
    signing_key: str | bytes,
) -> dict[str, object]:
    normalized_findings = _normalize_risk_findings(findings)
    if not normalized_findings:
        raise PublishabilityContractError("risk_acceptance_invalid")
    policy = _validate_authority_policy(authority_policy)
    record: dict[str, object] = {
        "schema_version": RISK_ACCEPTANCE_SCHEMA_VERSION,
        "subject": _normalize_subject(subject),
        "finding_ids": sorted(str(item["finding_id"]) for item in normalized_findings),
        "findings": normalized_findings,
        "permitted_scope": normalize_distribution_scope(permitted_scope),
        "authority_policy_id": policy["policy_id"],
        "authority_policy_version": policy["policy_version"],
        "authority_policy_hash": policy["policy_hash"],
        "principal_id": _identifier(principal_id),
        "role": "risk_owner",
        "key_id": _identifier(key_id),
        "issued_at": _timestamp(issued_at),
        "expires_at": _timestamp(expires_at),
        "decision": "accepted",
    }
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"]):
        raise PublishabilityContractError("risk_acceptance_invalid")
    return _with_attested_identity(record, signing_key=signing_key)


build_risk_acceptance_record = build_risk_acceptance


def build_publication_approval(
    *,
    subject: Mapping[str, object],
    bundle_hash: str,
    approved_scope: Mapping[str, object],
    authority_policy: Mapping[str, object],
    principal_id: str,
    key_id: str,
    issued_at: str,
    expires_at: str,
    known_limitations: Sequence[str],
    signing_key: str | bytes,
    evidence_class: str = "conformance_fixture",
) -> dict[str, object]:
    if evidence_class not in PUBLISHABILITY_EVIDENCE_CLASSES:
        raise PublishabilityContractError("evidence_malformed")
    policy = _validate_authority_policy(authority_policy)
    limitations = _bounded_string_list(known_limitations)
    record: dict[str, object] = {
        "schema_version": PUBLICATION_APPROVAL_SCHEMA_VERSION,
        "subject": _normalize_subject(subject),
        "bundle_hash": _hash_value(bundle_hash),
        "approved_scope": normalize_distribution_scope(approved_scope),
        "known_limitations": limitations,
        "known_limitations_hash": canonical_domain_pack_hash(limitations),
        "evidence_class": evidence_class,
        "authority_policy_id": policy["policy_id"],
        "authority_policy_version": policy["policy_version"],
        "authority_policy_hash": policy["policy_hash"],
        "principal_id": _identifier(principal_id),
        "role": "publication_approver",
        "key_id": _identifier(key_id),
        "issued_at": _timestamp(issued_at),
        "expires_at": _timestamp(expires_at),
        "decision": "approved",
    }
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"]):
        raise PublishabilityContractError("approval_invalid")
    return _with_attested_identity(record, signing_key=signing_key)


build_publication_approval_record = build_publication_approval


def build_revocation_evidence(
    *,
    authority_policy: Mapping[str, object],
    checked_at: str,
    principal_id: str,
    key_id: str,
    expires_at: str,
    signing_key: str | bytes,
    revoked_ids: Sequence[str] = (),
    revoked_hashes: Sequence[str] = (),
    revoked_principals: Sequence[str] = (),
    revoked_keys: Sequence[str] = (),
    revoked_policy_hashes: Sequence[str] = (),
) -> dict[str, object]:
    policy = _validate_authority_policy(authority_policy)
    record: dict[str, object] = {
        "schema_version": REVOCATION_EVIDENCE_SCHEMA_VERSION,
        "authority_policy_id": policy["policy_id"],
        "authority_policy_version": policy["policy_version"],
        "authority_policy_hash": policy["policy_hash"],
        "checked_at": _timestamp(checked_at),
        "source_id": "authority-revocation-registry",
        "status": "current",
        "principal_id": _identifier(principal_id),
        "role": "revocation_authority",
        "key_id": _identifier(key_id),
        "issued_at": _timestamp(checked_at),
        "expires_at": _timestamp(expires_at),
        "revoked_ids": _bounded_identifier_list(revoked_ids),
        "revoked_hashes": [_hash_value(value) for value in revoked_hashes],
        "revoked_principals": _bounded_identifier_list(revoked_principals),
        "revoked_keys": _bounded_identifier_list(revoked_keys),
        "revoked_policy_hashes": [_hash_value(value) for value in revoked_policy_hashes],
    }
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"]):
        raise PublishabilityContractError("revocation_evidence_invalid")
    return _with_attested_identity(record, signing_key=signing_key)


build_revocation_record = build_revocation_evidence


def compute_publishability_evidence_hash(
    *,
    release_candidate: Mapping[str, object],
    release_pack: Mapping[str, object],
    release_pack_verification: Mapping[str, object],
    governance: Mapping[str, object],
    audit: Mapping[str, object],
    review: Mapping[str, object],
    risk_acceptances: Sequence[Mapping[str, object]],
    authority_policy: Mapping[str, object],
    revocation: Mapping[str, object],
    requested_scope: Mapping[str, object],
    validity: Mapping[str, object],
) -> str:
    core = _bundle_core(
        release_candidate=release_candidate,
        release_pack=release_pack,
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=audit,
        review=review,
        risk_acceptances=risk_acceptances,
        authority_policy=authority_policy,
        revocation=revocation,
        requested_scope=requested_scope,
        validity=validity,
    )
    return canonical_domain_pack_hash(core)


def _encode_release_candidate_record(
    record: Mapping[str, object],
) -> dict[str, object]:
    """Keep large validated qualification reports bounded in bundle records."""

    payload = json.dumps(
        dict(record), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) <= RELEASE_CANDIDATE_INLINE_MAX_BYTES:
        return dict(record)
    encoded = base64.b64encode(zlib.compress(payload, 9)).decode("ascii")
    chunks = [
        encoded[index : index + PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE]
        for index in range(0, len(encoded), PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE)
    ]
    if (
        not chunks
        or len(chunks) > PUBLISHABILITY_GATE_BUNDLE_MAX_CHUNKS
        or len(encoded) > PUBLISHABILITY_GATE_BUNDLE_MAX_ENCODED_BYTES
    ):
        raise PublishabilityContractError("evidence_malformed")
    return {
        "schema_version": RELEASE_CANDIDATE_REFERENCE_SCHEMA_VERSION,
        "record_hash": canonical_domain_pack_hash(dict(record)),
        "chunks": chunks,
    }


def _decode_release_candidate_record(raw: object) -> dict[str, object]:
    record = _mapping(raw, "evidence_malformed")
    if record.get("schema_version") != RELEASE_CANDIDATE_REFERENCE_SCHEMA_VERSION:
        return record
    if set(record) != {"schema_version", "record_hash", "chunks"}:
        raise PublishabilityContractError("evidence_malformed")
    expected_hash = record.get("record_hash")
    if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash):
        raise PublishabilityContractError("evidence_malformed")
    chunks = record.get("chunks")
    if (
        not isinstance(chunks, list)
        or not chunks
        or len(chunks) > PUBLISHABILITY_GATE_BUNDLE_MAX_CHUNKS
        or any(not isinstance(chunk, str) or not chunk for chunk in chunks)
    ):
        raise PublishabilityContractError("evidence_malformed")
    encoded = "".join(chunks)
    if len(encoded) > PUBLISHABILITY_GATE_BUNDLE_MAX_ENCODED_BYTES:
        raise PublishabilityContractError("evidence_malformed")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        decompressor = zlib.decompressobj()
        payload = decompressor.decompress(
            compressed,
            PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES + 1,
        )
        if (
            len(payload) > PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES
            or decompressor.unconsumed_tail
            or not decompressor.eof
        ):
            raise PublishabilityContractError("evidence_malformed")
        payload += decompressor.flush()
        decoded = _mapping(json.loads(payload.decode("utf-8")), "evidence_malformed")
    except PublishabilityContractError:
        raise
    except (ValueError, UnicodeError, zlib.error, json.JSONDecodeError) as exc:
        raise PublishabilityContractError("evidence_malformed") from exc
    if canonical_domain_pack_hash(decoded) != expected_hash:
        raise PublishabilityContractError("evidence_hash_mismatch")
    return decoded


def build_publishability_bundle(
    *,
    release_candidate: Mapping[str, object],
    release_pack: Mapping[str, object],
    release_pack_verification: Mapping[str, object],
    governance: Mapping[str, object],
    audit: Mapping[str, object],
    review: Mapping[str, object],
    risk_acceptances: Sequence[Mapping[str, object]],
    publication_approval: Mapping[str, object] | None,
    authority_policy: Mapping[str, object],
    revocation: Mapping[str, object],
    requested_scope: Mapping[str, object],
    validity: Mapping[str, object],
    evidence_class: str = "conformance_fixture",
) -> dict[str, object]:
    if evidence_class not in PUBLISHABILITY_EVIDENCE_CLASSES:
        raise PublishabilityContractError("evidence_malformed")
    core = _bundle_core(
        release_candidate=release_candidate,
        release_pack=release_pack,
        release_pack_verification=release_pack_verification,
        governance=governance,
        audit=audit,
        review=review,
        risk_acceptances=risk_acceptances,
        authority_policy=authority_policy,
        revocation=revocation,
        requested_scope=requested_scope,
        validity=validity,
    )
    bundle_hash = canonical_domain_pack_hash(core)
    if publication_approval is not None:
        approval = _validate_publication_approval(publication_approval)
        if approval["bundle_hash"] != bundle_hash:
            raise PublishabilityContractError("bundle_approval_mismatch")
        if _normalize_subject(approval["subject"]) != core["subject"]:
            raise PublishabilityContractError("bundle_subject_mismatch")
        if (
            approval["authority_policy_id"] != core["authority_policy"]["policy_id"]
            or approval["authority_policy_version"]
            != core["authority_policy"]["policy_version"]
            or approval["authority_policy_hash"]
            != core["authority_policy"]["policy_hash"]
        ):
            raise PublishabilityContractError("authority_policy_mismatch")
        if approval["evidence_class"] != evidence_class:
            raise PublishabilityContractError("evidence_identity_mismatch")
    else:
        approval = None
    content = {
        **core,
        "publication_approval": approval,
        "evidence_class": evidence_class,
    }
    full_hash = canonical_domain_pack_hash(content)
    return {
        **content,
        "bundle_hash": bundle_hash,
        "bundle_content_hash": full_hash,
        "bundle_id": "publishability_bundle_" + full_hash.removeprefix("sha256:")[:16],
    }


build_publishability_evidence_bundle = build_publishability_bundle


def validate_publishability_bundle_record(record: Mapping[str, object]) -> None:
    """Validate identity, hashes, nested contracts, and approval binding."""

    if not isinstance(record, Mapping):
        raise PublishabilityContractError("evidence_malformed")
    required = {
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
        "bundle_hash",
        "bundle_content_hash",
        "bundle_id",
    }
    if set(record) != required:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("schema_version") != PUBLISHABILITY_BUNDLE_SCHEMA_VERSION:
        raise PublishabilityContractError("evidence_unknown_version")
    evidence_class = record.get("evidence_class")
    if evidence_class not in PUBLISHABILITY_EVIDENCE_CLASSES:
        raise PublishabilityContractError("evidence_malformed")
    core = _bundle_core(
        release_candidate=_decode_release_candidate_record(
            _record_field(_record_field(record, "release_candidate"), "record")
        ),
        release_pack=_record_field(record, "release_pack"),
        release_pack_verification=_record_field(record, "release_pack_verification"),
        governance=_record_field(record, "governance"),
        audit=_record_field(_record_field(record, "audit"), "record"),
        review=_record_field(record, "review"),
        risk_acceptances=_record_list_field(record, "risk_acceptances"),
        authority_policy=_record_field(record, "authority_policy"),
        revocation=_record_field(record, "revocation"),
        requested_scope=_record_field(record, "requested_scope"),
        validity=_record_field(record, "validity"),
    )
    expected_bundle_hash = canonical_domain_pack_hash(core)
    if record.get("bundle_hash") != expected_bundle_hash:
        raise PublishabilityContractError("bundle_hash_mismatch")
    content = {key: record[key] for key in core} | {
        "publication_approval": record.get("publication_approval"),
        "evidence_class": evidence_class,
    }
    expected_content_hash = canonical_domain_pack_hash(content)
    if record.get("bundle_content_hash") != expected_content_hash:
        raise PublishabilityContractError("bundle_hash_mismatch")
    expected_id = "publishability_bundle_" + expected_content_hash.removeprefix(
        "sha256:"
    )[:16]
    if record.get("bundle_id") != expected_id:
        raise PublishabilityContractError("evidence_malformed")
    _validate_bundle_nested_records(record)


def evaluate_publishability(
    *,
    bundle: Mapping[str, object],
    trusted_keys: Mapping[str, str | bytes] | None = None,
    trusted_policy_hashes: Iterable[str] | None = None,
    trusted_bundle_content_hashes: Iterable[str] | None = None,
    trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    now: str | None = None,
    release_pack_path: Path | None = None,
) -> dict[str, object]:
    """Evaluate one exact bundle without performing any publication side effect."""

    trusted = trusted_keys or {}
    requested = bundle.get("requested_scope") if isinstance(bundle, Mapping) else None
    requested_scope: dict[str, object] | None = None
    try:
        requested_scope = normalize_distribution_scope(_mapping(requested, "scope_invalid"))
        validate_publishability_bundle_record(bundle)
    except Exception as exc:
        reason_code = _contract_reason_code(exc)
        return _decision(
            bundle=bundle if isinstance(bundle, Mapping) else {},
            status="insufficient_evidence",
            effective_qualification="unqualified",
            reason_codes=(reason_code,),
            reasons=("publishability evidence is malformed, stale, or hash-mismatched",),
            conformance_status="insufficient_evidence",
            requested_scope=requested_scope,
        )

    if now is None and (
        bundle.get("publication_approval") is not None
        or bool(bundle.get("risk_acceptances"))
    ):
        return _decision(
            bundle=bundle,
            status="insufficient_evidence",
            effective_qualification="release_candidate",
            reason_codes=("evidence_incomplete",),
            reasons=("publishability authority requires an explicit evaluation time",),
            conformance_status="insufficient_evidence",
            requested_scope=requested_scope,
        )

    try:
        checked_at = _evaluation_time(bundle, now)
        checks: list[tuple[str, str, str]] = []
        checks.extend(
            _evaluate_bundle_origin(
                bundle,
                trusted_bundle_content_hashes,
            )
        )
        checks.extend(_evaluate_release_candidate(bundle))
        checks.extend(
            _evaluate_release_pack(
                bundle,
                trusted_release_pack_verification_hashes,
            )
        )
        if release_pack_path is not None:
            checks.extend(_evaluate_release_pack_path(bundle, release_pack_path))
        checks.extend(_evaluate_governance(bundle))
        checks.extend(_evaluate_audit_and_review(bundle))
        checks.extend(_evaluate_risk_acceptances(bundle, checked_at, trusted))
        checks.extend(
            _evaluate_authority_policy(
                bundle,
                checked_at,
                trusted_policy_hashes,
            )
        )
        checks.extend(_evaluate_approval(bundle, checked_at, trusted))
        checks.extend(_evaluate_revocation(bundle, checked_at, trusted))
        checks.extend(_evaluate_validity(bundle, checked_at))
        checks.extend(_evaluate_scope(bundle))
        checks.extend(_evaluate_separation_of_duties(bundle))
    except Exception as exc:
        checks = [
            (
                "insufficient_evidence",
                _contract_reason_code(exc),
                "publishability evidence is invalid",
            )
        ]

    denied_codes = [code for status, code, _ in checks if status == "denied"]
    insufficient_codes = [code for status, code, _ in checks if status == "insufficient_evidence"]
    reason_codes = _unique(denied_codes + insufficient_codes)
    reasons = _unique(reason for _, _, reason in checks if reason)
    substantive_status = (
        "denied"
        if denied_codes
        else "insufficient_evidence"
        if insufficient_codes
        else "passed"
    )
    evidence_class = str(bundle.get("evidence_class"))
    conformance_status = substantive_status
    if substantive_status == "passed" and evidence_class in NON_QUALIFYING_EVIDENCE_CLASSES:
        status = "denied"
        reason_codes = _unique([*reason_codes, "non_qualifying_evidence_class"])
        reasons = _unique(
            [*reasons, "fixture authority can exercise conformance but cannot establish Publishable"]
        )
    else:
        status = substantive_status
    if status == "passed":
        reason_codes = ["publishability_passed"]
        reasons = ["all publication governance, authority, scope, and revocation checks passed"]
    return _decision(
        bundle=bundle,
        status=status,
        effective_qualification="publishable" if status == "passed" else "release_candidate",
        reason_codes=reason_codes or ["evidence_missing"],
        reasons=reasons or ["publishability evidence is insufficient"],
        conformance_status=conformance_status,
        requested_scope=requested_scope,
    )


verify_publishability = evaluate_publishability


def build_publishability_gate(
    *,
    bundle: Mapping[str, object],
    decision: Mapping[str, object] | None = None,
    trusted_keys: Mapping[str, str | bytes] | None = None,
    trusted_policy_hashes: Iterable[str] | None = None,
    trusted_bundle_content_hashes: Iterable[str] | None = None,
    trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    now: str | None = None,
    release_pack_path: Path | None = None,
) -> dict[str, object]:
    """Adapt a publishability decision to the cumulative qualification gate."""

    validate_publishability_bundle_record(bundle)
    evaluated = evaluate_publishability(
        bundle=bundle,
        trusted_keys=trusted_keys,
        trusted_policy_hashes=trusted_policy_hashes,
        trusted_bundle_content_hashes=trusted_bundle_content_hashes,
        trusted_release_pack_verification_hashes=trusted_release_pack_verification_hashes,
        now=now,
        release_pack_path=release_pack_path,
    )
    if decision is not None:
        validate_publishability_decision_record(decision)
        if dict(decision) != evaluated:
            raise PublishabilityContractError("evidence_identity_mismatch")
    validate_publishability_decision_record(evaluated)
    governance = _mapping(bundle.get("governance"), "evidence_malformed")
    review = _mapping(bundle.get("review"), "evidence_malformed")
    policy = _mapping(bundle.get("authority_policy"), "evidence_malformed")
    rc_binding = _decode_release_candidate_record(
        _mapping(bundle.get("release_candidate"), "evidence_malformed").get("record")
    )
    rc_binding = _mapping(rc_binding.get("qualification_binding"), "evidence_malformed")
    return {
        "schema_version": PUBLISHABILITY_GATE_SCHEMA_VERSION,
        "status": evaluated["status"],
        "subject_id": _subject_field(bundle, "subject_id"),
        "subject_hash": _subject_field(bundle, "subject_hash"),
        "binding_hash": rc_binding["binding_hash"],
        "release_pack_hash": _subject_field(bundle, "release_pack_hash"),
        "evidence_ids": _bundle_evidence_ids(bundle),
        "verification": {"status": evaluated["status"], "bundle_hash": bundle["bundle_hash"]},
        "governance": {"status": governance["status"]},
        "review": {"status": review["status"]},
        "authority": {"status": "verified" if evaluated["status"] == "passed" else evaluated["status"], "policy_hash": policy["policy_hash"]},
        "decision": dict(evaluated),
        "bundle_hash": bundle["bundle_hash"],
        # Carry the validated bundle through the qualification boundary as
        # bounded deterministic compressed chunks.  A hash-only reference
        # would let a caller manufacture a self-consistent passed gate without
        # exposing the evidence the boundary is meant to validate; chunks keep
        # the existing qualification canonicalizer's per-string limit intact.
        "bundle": _encode_gate_bundle(bundle),
    }


def build_publishable_qualification_evidence(
    *,
    binding: Mapping[str, object] | Any,
    release_candidate_evidence: Mapping[str, object],
    bundle: Mapping[str, object],
    decision: Mapping[str, object] | None = None,
    trusted_keys: Mapping[str, str | bytes] | None = None,
    trusted_policy_hashes: Iterable[str] | None = None,
    trusted_bundle_content_hashes: Iterable[str] | None = None,
    trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    now: str | None = None,
    release_pack_path: Path | None = None,
    evidence_class: str = "conformance_fixture",
) -> dict[str, object]:
    """Create the existing qualification envelope for a Publishable transition."""

    from synthesis.qualification import QUALIFICATION_EVIDENCE_SCHEMA_VERSION

    gate = build_publishability_gate(
        bundle=bundle,
        decision=decision,
        trusted_keys=trusted_keys,
        trusted_policy_hashes=trusted_policy_hashes,
        trusted_bundle_content_hashes=trusted_bundle_content_hashes,
        trusted_release_pack_verification_hashes=trusted_release_pack_verification_hashes,
        now=now,
        release_pack_path=release_pack_path,
    )
    binding_record = binding.to_record() if hasattr(binding, "to_record") else dict(binding)
    return {
        "schema_version": QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
        "qualification": "publishable",
        "evidence_class": evidence_class,
        "binding": binding_record,
        "gates": {
            **dict(_mapping(release_candidate_evidence.get("gates"), "evidence_malformed")),
            "publishability": gate,
        },
        "evidence_graph": list(release_candidate_evidence.get("evidence_graph", [])),
    }


build_publishability_qualification_evidence = build_publishable_qualification_evidence


def _validate_publishability_gate_record(
    record: Mapping[str, object],
    *,
    trusted_keys: Mapping[str, str | bytes] | None = None,
    trusted_policy_hashes: Iterable[str] | None = None,
    trusted_bundle_content_hashes: Iterable[str] | None = None,
    trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    now: str | None = None,
    structural_only: bool = False,
) -> None:
    """Validate the cumulative adapter and optionally re-evaluate authority."""

    if not isinstance(record, Mapping):
        raise PublishabilityContractError("evidence_malformed")
    required = {
        "schema_version",
        "status",
        "subject_id",
        "subject_hash",
        "binding_hash",
        "release_pack_hash",
        "evidence_ids",
        "verification",
        "governance",
        "review",
        "authority",
        "decision",
        "bundle_hash",
        "bundle",
    }
    if set(record) != required or record.get("schema_version") != PUBLISHABILITY_GATE_SCHEMA_VERSION:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("status") not in PUBLISHABILITY_STATUSES:
        raise PublishabilityContractError("evidence_malformed")
    _identifier(record.get("subject_id"))
    _hash_value(record.get("subject_hash"))
    _hash_value(record.get("binding_hash"))
    _hash_value(record.get("release_pack_hash"))
    evidence_ids = record.get("evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or not evidence_ids
        or any(not isinstance(item, str) or not item for item in evidence_ids)
    ):
        raise PublishabilityContractError("evidence_missing")
    for field in ("verification", "governance", "review", "authority"):
        _mapping(record.get(field), "evidence_incomplete")
    _hash_value(record.get("bundle_hash"))
    bundle = _decode_gate_bundle(record.get("bundle"))
    validate_publishability_bundle_record(bundle)
    bundle_evidence_class = bundle.get("evidence_class")
    if (
        record.get("status") == "passed"
        and bundle_evidence_class in NON_QUALIFYING_EVIDENCE_CLASSES
    ):
        raise PublishabilityContractError("non_qualifying_evidence_class")
    if record.get("bundle_hash") != bundle.get("bundle_hash"):
        raise PublishabilityContractError("evidence_identity_mismatch")
    decision = _mapping(record.get("decision"), "evidence_malformed")
    validate_publishability_decision_record(decision)
    if (
        decision.get("status") == "passed"
        and decision.get("evidence_class") in NON_QUALIFYING_EVIDENCE_CLASSES
    ):
        raise PublishabilityContractError("non_qualifying_evidence_class")
    if decision.get("evidence_class") != bundle_evidence_class:
        raise PublishabilityContractError("evidence_identity_mismatch")
    if record.get("status") != decision.get("status") or decision.get("bundle_hash") != bundle.get("bundle_hash"):
        raise PublishabilityContractError("evidence_identity_mismatch")
    subject = _mapping(bundle.get("subject"), "evidence_malformed")
    if any(record.get(field) != subject.get(field) for field in ("subject_id", "subject_hash", "release_pack_hash")):
        raise PublishabilityContractError("evidence_identity_mismatch")
    if record.get("status") == "passed" and decision.get("conformance", {}).get("status") != "passed":
        raise PublishabilityContractError("evidence_non_passing")
    if record.get("status") == "passed":
        if structural_only:
            return
        if (
            trusted_keys is None
            or trusted_policy_hashes is None
            or trusted_bundle_content_hashes is None
            or trusted_release_pack_verification_hashes is None
            or now is None
        ):
            raise PublishabilityContractError("evidence_incomplete")
        evaluated = evaluate_publishability(
            bundle=bundle,
            trusted_keys=trusted_keys,
            trusted_policy_hashes=trusted_policy_hashes,
            trusted_bundle_content_hashes=trusted_bundle_content_hashes,
            trusted_release_pack_verification_hashes=trusted_release_pack_verification_hashes,
            now=now,
        )
        if dict(decision) != evaluated:
            raise PublishabilityContractError("evidence_identity_mismatch")


def validate_publishability_gate_record(
    record: Mapping[str, object],
    *,
    trusted_keys: Mapping[str, str | bytes] | None = None,
    trusted_policy_hashes: Iterable[str] | None = None,
    trusted_bundle_content_hashes: Iterable[str] | None = None,
    trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    now: str | None = None,
) -> None:
    """Validate a gate and re-evaluate every passed authority claim."""

    _validate_publishability_gate_record(
        record,
        trusted_keys=trusted_keys,
        trusted_policy_hashes=trusted_policy_hashes,
        trusted_bundle_content_hashes=trusted_bundle_content_hashes,
        trusted_release_pack_verification_hashes=trusted_release_pack_verification_hashes,
        now=now,
    )



def validate_publishability_decision_record(record: Mapping[str, object]) -> None:
    required = {
        "schema_version",
        "bundle_hash",
        "bundle_id",
        "subject",
        "requested_scope",
        "status",
        "effective_qualification",
        "reason_codes",
        "reasons",
        "evidence_class",
        "conformance",
        "decision_id",
    }
    if not isinstance(record, Mapping) or set(record) != required:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("schema_version") != PUBLISHABILITY_DECISION_SCHEMA_VERSION:
        raise PublishabilityContractError("evidence_unknown_version")
    if record.get("status") not in PUBLISHABILITY_STATUSES:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("effective_qualification") not in {
        "unqualified",
        "release_candidate",
        "publishable",
    }:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("bundle_hash") is not None:
        _hash_value(record.get("bundle_hash"))
    if record.get("bundle_id") is not None:
        _identifier(record.get("bundle_id"))
    _normalize_subject(_mapping(record.get("subject"), "evidence_malformed"))
    normalize_distribution_scope(_mapping(record.get("requested_scope"), "scope_invalid"))
    codes = record.get("reason_codes")
    reasons = record.get("reasons")
    if not isinstance(codes, list) or not codes or any(code not in PUBLISHABILITY_REASON_CODES for code in codes):
        raise PublishabilityContractError("evidence_malformed")
    if not isinstance(reasons, list) or not reasons or any(not isinstance(reason, str) or not reason for reason in reasons):
        raise PublishabilityContractError("evidence_malformed")
    evidence_class = record.get("evidence_class")
    if evidence_class not in PUBLISHABILITY_EVIDENCE_CLASSES | {"unknown"}:
        raise PublishabilityContractError("evidence_malformed")
    conformance = _mapping(record.get("conformance"), "evidence_malformed")
    if conformance.get("status") not in PUBLISHABILITY_STATUSES:
        raise PublishabilityContractError("evidence_malformed")
    if record.get("status") == "passed":
        if (
            record.get("effective_qualification") != "publishable"
            or conformance.get("status") != "passed"
            or conformance.get("effective_qualification") != "publishable"
            or record.get("reason_codes") != ["publishability_passed"]
        ):
            raise PublishabilityContractError("evidence_non_passing")
    elif record.get("effective_qualification") == "publishable":
        raise PublishabilityContractError("evidence_non_passing")
    content = {key: record[key] for key in required if key != "decision_id"}
    expected = canonical_domain_pack_hash(content)
    if record.get("decision_id") != "publishability_decision_" + expected.removeprefix("sha256:")[:16]:
        raise PublishabilityContractError("evidence_hash_mismatch")


def write_publishability_decision(output_path: Path, decision: Mapping[str, object]) -> Path:
    validate_publishability_decision_record(decision)
    output_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_publishability_bundle(output_path: Path, bundle: Mapping[str, object]) -> Path:
    """Write one validated evidence bundle without performing publication."""

    validate_publishability_bundle_record(bundle)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_publishability_bundle(input_path: Path) -> dict[str, object]:
    """Load and validate a local bundle, exposing only bounded contract errors."""

    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublishabilityContractError("evidence_malformed") from exc
    if not isinstance(raw, Mapping):
        raise PublishabilityContractError("evidence_malformed")
    bundle = dict(raw)
    try:
        validate_publishability_bundle_record(bundle)
    except Exception as exc:
        if isinstance(exc, PublishabilityContractError):
            raise
        raise PublishabilityContractError("evidence_malformed") from exc
    return bundle


def _normalize_release_pack_verification(
    record: Mapping[str, object],
    *,
    pack_reference: Mapping[str, object],
    release_candidate_verification: Mapping[str, object],
) -> dict[str, object]:
    normalized = dict(_mapping(record, "evidence_malformed"))
    required = {
        "schema_version",
        "verification",
        "release_pack_hash",
        "release_pack_byte_count",
        "subject_id",
        "subject_hash",
        "binding_hash",
    }
    if not (
        set(normalized) == required
        or set(normalized) == required | {"verification_hash"}
    ):
        raise PublishabilityContractError("evidence_malformed")
    supplied_verification_hash = normalized.pop("verification_hash", None)
    if normalized.get("schema_version") != "qualification_release_pack_verification_v1":
        raise PublishabilityContractError("evidence_unknown_version")
    verification = normalized.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "passed":
        raise PublishabilityContractError("release_pack_unverified")
    if dict(normalized) != dict(release_candidate_verification):
        raise PublishabilityContractError("evidence_identity_mismatch")
    if (
        normalized.get("release_pack_hash") != pack_reference["content_hash"]
        or normalized.get("release_pack_byte_count") != pack_reference["byte_count"]
    ):
        raise PublishabilityContractError("evidence_identity_mismatch")
    verification_hash = canonical_domain_pack_hash(
        {key: value for key, value in normalized.items() if key != "verification_hash"}
    )
    if supplied_verification_hash is not None and supplied_verification_hash != verification_hash:
        raise PublishabilityContractError("evidence_hash_mismatch")
    normalized["verification_hash"] = verification_hash
    return normalized


def _bundle_core(
    *,
    release_candidate: Mapping[str, object],
    release_pack: Mapping[str, object],
    release_pack_verification: Mapping[str, object],
    governance: Mapping[str, object],
    audit: Mapping[str, object],
    review: Mapping[str, object],
    risk_acceptances: Sequence[Mapping[str, object]],
    authority_policy: Mapping[str, object],
    revocation: Mapping[str, object],
    requested_scope: Mapping[str, object],
    validity: Mapping[str, object],
) -> dict[str, object]:
    subject = publishability_subject_from_release_candidate(
        release_candidate,
        release_pack=release_pack,
    )
    pack_reference = _release_pack_reference(
        release_pack,
        release_pack_hash=str(subject["release_pack_hash"]),
        byte_count=int(subject["release_pack_byte_count"]),
        dataset_version=str(subject["dataset_version"]),
    )
    release_candidate_verification = _release_candidate_pack_verification(
        release_candidate
    )
    release_candidate_verification["release_pack_byte_count"] = pack_reference[
        "byte_count"
    ]
    verification = _normalize_release_pack_verification(
        release_pack_verification,
        pack_reference=pack_reference,
        release_candidate_verification=release_candidate_verification,
    )
    governance_record = _validate_governance(governance)
    if _normalize_subject(governance_record["subject"]) != subject:
        raise PublishabilityContractError("bundle_subject_mismatch")
    policy = _validate_authority_policy(authority_policy)
    revocation_record = _validate_revocation(revocation)
    if revocation_record["authority_policy_hash"] != policy["policy_hash"]:
        raise PublishabilityContractError("authority_policy_mismatch")
    audit_record = _validate_audit(audit)
    _validate_release_candidate_audit_binding(release_candidate, audit_record)
    normalized_review = _normalize_review(review)
    risks = [_validate_risk_acceptance(item) for item in risk_acceptances]
    scope = normalize_distribution_scope(requested_scope)
    if normalize_distribution_scope(
        _mapping(governance_record["proposed_scope"], "scope_invalid")
    ) != scope:
        raise PublishabilityContractError("scope_mismatch")
    for risk in risks:
        if _normalize_subject(risk["subject"]) != subject:
            raise PublishabilityContractError("bundle_subject_mismatch")
        if (
            risk["authority_policy_id"] != policy["policy_id"]
            or risk["authority_policy_version"] != policy["policy_version"]
            or risk["authority_policy_hash"] != policy["policy_hash"]
        ):
            raise PublishabilityContractError("authority_policy_mismatch")
    normalized_validity = _normalize_validity(validity)
    rc_reference = {
        "record": _encode_release_candidate_record(release_candidate),
        "record_hash": canonical_domain_pack_hash(dict(release_candidate)),
        "subject_id": subject["subject_id"],
        "subject_hash": subject["subject_hash"],
        "status": release_candidate["status"],
        "effective_qualification": release_candidate["effective_qualification"],
    }
    return {
        "schema_version": PUBLISHABILITY_BUNDLE_SCHEMA_VERSION,
        "subject": subject,
        "release_candidate": rc_reference,
        "release_pack": pack_reference,
        "release_pack_verification": verification,
        "governance": governance_record,
        "audit": {
            "record": audit_record,
            "record_hash": canonical_domain_pack_hash(audit_record),
        },
        "review": normalized_review,
        "risk_acceptances": risks,
        "authority_policy": policy,
        "revocation": revocation_record,
        "requested_scope": scope,
        "validity": normalized_validity,
    }


def _validate_bundle_nested_records(bundle: Mapping[str, object]) -> None:
    subject = _normalize_subject(_mapping(bundle.get("subject"), "evidence_malformed"))
    rc_ref = _mapping(bundle.get("release_candidate"), "evidence_malformed")
    rc = _decode_release_candidate_record(
        _mapping(rc_ref.get("record"), "evidence_malformed")
    )
    if rc_ref.get("record_hash") != canonical_domain_pack_hash(rc):
        raise PublishabilityContractError("evidence_hash_mismatch")
    if rc_ref.get("subject_hash") != subject["subject_hash"] or rc_ref.get("subject_id") != subject["subject_id"]:
        raise PublishabilityContractError("bundle_subject_mismatch")
    if rc_ref.get("status") != rc.get("status") or rc_ref.get("effective_qualification") != rc.get("effective_qualification"):
        raise PublishabilityContractError("evidence_identity_mismatch")
    extracted = publishability_subject_from_release_candidate(
        rc,
        release_pack=_mapping(bundle.get("release_pack"), "evidence_malformed"),
    )
    if extracted != subject:
        raise PublishabilityContractError("bundle_subject_mismatch")
    _validate_governance(_mapping(bundle.get("governance"), "evidence_malformed"))
    governance = _mapping(bundle.get("governance"), "evidence_malformed")
    if _normalize_subject(governance["subject"]) != subject:
        raise PublishabilityContractError("bundle_subject_mismatch")
    audit_envelope = _mapping(bundle.get("audit"), "evidence_malformed")
    audit = _mapping(audit_envelope.get("record"), "evidence_malformed")
    if audit_envelope.get("record_hash") != canonical_domain_pack_hash(audit):
        raise PublishabilityContractError("evidence_hash_mismatch")
    _validate_audit(audit)
    _normalize_review(_mapping(bundle.get("review"), "evidence_malformed"))
    policy = _validate_authority_policy(_mapping(bundle.get("authority_policy"), "evidence_malformed"))
    revocation = _validate_revocation(
        _mapping(bundle.get("revocation"), "evidence_malformed")
    )
    if (
        revocation["authority_policy_id"] != policy["policy_id"]
        or revocation["authority_policy_version"] != policy["policy_version"]
        or revocation["authority_policy_hash"] != policy["policy_hash"]
    ):
        raise PublishabilityContractError("authority_policy_mismatch")
    risks = bundle.get("risk_acceptances")
    if not isinstance(risks, Sequence) or isinstance(risks, (str, bytes)):
        raise PublishabilityContractError("evidence_malformed")
    for risk in risks:
        risk_record = _validate_risk_acceptance(
            _mapping(risk, "evidence_malformed")
        )
        if _normalize_subject(risk_record["subject"]) != subject:
            raise PublishabilityContractError("bundle_subject_mismatch")
        if (
            risk_record["authority_policy_id"] != policy["policy_id"]
            or risk_record["authority_policy_version"] != policy["policy_version"]
            or risk_record["authority_policy_hash"] != policy["policy_hash"]
        ):
            raise PublishabilityContractError("authority_policy_mismatch")
    approval = bundle.get("publication_approval")
    if approval is not None:
        approval_record = _validate_publication_approval(_mapping(approval, "evidence_malformed"))
        if approval_record["bundle_hash"] != bundle["bundle_hash"]:
            raise PublishabilityContractError("bundle_approval_mismatch")
        if _normalize_subject(approval_record["subject"]) != subject:
            raise PublishabilityContractError("bundle_subject_mismatch")
        if (
            approval_record["authority_policy_id"] != policy["policy_id"]
            or approval_record["authority_policy_version"] != policy["policy_version"]
            or approval_record["authority_policy_hash"] != policy["policy_hash"]
        ):
            raise PublishabilityContractError("authority_policy_mismatch")
        if approval_record["evidence_class"] != bundle["evidence_class"]:
            raise PublishabilityContractError("evidence_identity_mismatch")
    normalize_distribution_scope(_mapping(bundle.get("requested_scope"), "scope_invalid"))
    _normalize_validity(_mapping(bundle.get("validity"), "validity_missing"))


def _release_candidate_pack_verification(
    release_candidate: Mapping[str, object],
) -> dict[str, object]:
    history = _sequence(
        release_candidate.get("historical_decisions"),
        "release_pack_unverified",
    )
    for decision in reversed(history):
        if not isinstance(decision, Mapping):
            continue
        evidence = decision.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        gates = evidence.get("gates")
        if not isinstance(gates, Mapping):
            continue
        verification = gates.get("release_pack_verification")
        if isinstance(verification, Mapping):
            normalized = dict(verification)
            if set(normalized) == {
                "schema_version",
                "verification",
                "release_pack_hash",
                "subject_id",
                "subject_hash",
                "binding_hash",
            }:
                return normalized
    raise PublishabilityContractError("release_pack_unverified")


def _release_candidate_gate(
    release_candidate: Mapping[str, object],
    gate_name: str,
) -> Mapping[str, object]:
    history = _sequence(
        release_candidate.get("historical_decisions"),
        "release_candidate_missing",
    )
    for decision in reversed(history):
        if not isinstance(decision, Mapping):
            continue
        evidence = decision.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        gates = evidence.get("gates")
        if not isinstance(gates, Mapping):
            continue
        gate = gates.get(gate_name)
        if isinstance(gate, Mapping):
            return gate
    raise PublishabilityContractError("release_candidate_missing")


def _validate_release_candidate_audit_binding(
    release_candidate: Mapping[str, object],
    audit: Mapping[str, object],
) -> None:
    candidate_gate = _release_candidate_gate(release_candidate, "release_quality_audit")
    candidate_decision = _mapping(candidate_gate.get("decision"), "audit_missing")
    supplied_decision = _mapping(audit.get("decision"), "audit_missing")
    if supplied_decision.get("status") != candidate_decision.get("status"):
        raise PublishabilityContractError("evidence_identity_mismatch")
    candidate_record = candidate_gate.get("record")
    if isinstance(candidate_record, Mapping):
        candidate_record = _validate_audit(candidate_record)
        if canonical_domain_pack_hash(dict(candidate_record)) != canonical_domain_pack_hash(
            dict(audit)
        ):
            raise PublishabilityContractError("evidence_identity_mismatch")
    else:
        candidate_payload = {
            key: value
            for key, value in candidate_gate.items()
            if key
            not in {
                "subject_id",
                "subject_hash",
                "binding_hash",
                "release_pack_hash",
                "record_hash",
            }
        }
        if set(candidate_payload) > {"schema_version", "decision"}:
            candidate_record = _validate_audit(candidate_payload)
            if canonical_domain_pack_hash(dict(candidate_record)) != canonical_domain_pack_hash(
                dict(audit)
            ):
                raise PublishabilityContractError("evidence_identity_mismatch")
    candidate_record_hash = candidate_gate.get("record_hash")
    if isinstance(candidate_record_hash, str):
        if candidate_record_hash != canonical_domain_pack_hash(dict(audit)):
            raise PublishabilityContractError("evidence_identity_mismatch")
    elif not isinstance(candidate_record, Mapping):
        raise PublishabilityContractError("evidence_identity_mismatch")


def _evaluate_release_candidate(bundle: Mapping[str, object]) -> list[tuple[str, str, str]]:
    rc_ref = _mapping(bundle["release_candidate"], "evidence_malformed")
    record = _decode_release_candidate_record(
        _mapping(rc_ref, "evidence_malformed").get("record")
    )
    if record.get("status") != "passed" or record.get("effective_qualification") not in {
        "release_candidate",
        "publishable",
        "training_recommended",
    }:
        return [("denied", "release_candidate_non_passing", "the exact Release Candidate decision is not passing")]
    return []


def _evaluate_bundle_origin(
    bundle: Mapping[str, object],
    trusted_bundle_content_hashes: Iterable[str] | None,
) -> list[tuple[str, str, str]]:
    if bundle.get("evidence_class") in NON_QUALIFYING_EVIDENCE_CLASSES:
        return []
    trusted_hashes = {
        value
        for value in (trusted_bundle_content_hashes or ())
        if isinstance(value, str) and _HASH_RE.fullmatch(value)
    }
    if bundle.get("bundle_content_hash") not in trusted_hashes:
        return [
            (
                "insufficient_evidence",
                "evidence_origin_untrusted",
                "publishability bundle origin is not trusted out of band",
            )
        ]
    return []


def _evaluate_release_pack(
    bundle: Mapping[str, object],
    trusted_verification_hashes: Iterable[str] | None,
) -> list[tuple[str, str, str]]:
    verification = _mapping(bundle["release_pack_verification"], "evidence_malformed")
    nested = verification.get("verification")
    pack = _mapping(bundle["release_pack"], "evidence_malformed")
    verification_hash = verification.get("verification_hash")
    expected_verification_hash = canonical_domain_pack_hash(
        {
            key: value
            for key, value in verification.items()
            if key != "verification_hash"
        }
    )
    if (
        verification.get("schema_version")
        != "qualification_release_pack_verification_v1"
        or not isinstance(nested, Mapping)
        or nested.get("status") != "passed"
        or verification.get("release_pack_hash") != pack.get("content_hash")
        or verification.get("release_pack_byte_count") != pack.get("byte_count")
        or verification_hash != expected_verification_hash
    ):
        return [("denied", "release_pack_unverified", "the exact release pack was not independently verified")]
    trusted_hashes = {
        value
        for value in (trusted_verification_hashes or ())
        if isinstance(value, str) and _HASH_RE.fullmatch(value)
    }
    if verification_hash not in trusted_hashes:
        return [
            (
                "insufficient_evidence",
                "release_pack_verification_untrusted",
                "release-pack verification is not trusted out of band",
            )
        ]
    return []


def _evaluate_release_pack_path(
    bundle: Mapping[str, object],
    release_pack_path: Path,
) -> list[tuple[str, str, str]]:
    from synthesis.datasets import build_artifact_hash_record
    from synthesis.release_pack import verify_dataset_release_pack

    verification = verify_dataset_release_pack(release_pack_path)
    nested_verification = verification.get("verification")
    status = (
        nested_verification.get("status")
        if isinstance(nested_verification, Mapping)
        else verification.get("status")
    )
    if status != "passed":
        decision_status = "denied" if status == "failed" else "insufficient_evidence"
        return [
            (
                decision_status,
                "release_pack_unverified",
                "the supplied release-pack path did not independently verify",
            )
        ]
    artifact = build_artifact_hash_record(release_pack_path)
    pack = _mapping(bundle["release_pack"], "evidence_malformed")
    if (
        artifact.sha256 != pack.get("content_hash")
        or artifact.byte_count != pack.get("byte_count")
    ):
        return [
            (
                "denied",
                "evidence_identity_mismatch",
                "the supplied release-pack bytes do not match the bound pack",
            )
        ]
    return []


def _evaluate_governance(bundle: Mapping[str, object]) -> list[tuple[str, str, str]]:
    governance = _mapping(bundle["governance"], "evidence_malformed")
    results: list[tuple[str, str, str]] = []
    if governance.get("status") == "insufficient_evidence":
        results.append(("insufficient_evidence", "governance_incomplete", "publication governance evidence is insufficient"))
    elif governance.get("status") == "blocked":
        results.append(("denied", "governance_hard_gate_failed", "publication governance is blocked"))
    checks = _mapping(governance.get("checks"), "governance_incomplete")
    for check in GOVERNANCE_CHECKS:
        item = _mapping(checks.get(check), "governance_incomplete")
        status = item.get("status")
        if status in {"failed", "blocked", "watch"}:
            results.append(("denied", "governance_hard_gate_failed", f"publication governance hard gate failed: {check}"))
        elif status in {"unknown", "insufficient_evidence"}:
            results.append(("insufficient_evidence", "governance_incomplete", f"publication governance check is insufficient: {check}"))
    return results


def _evaluate_audit_and_review(bundle: Mapping[str, object]) -> list[tuple[str, str, str]]:
    audit = _mapping(_mapping(bundle["audit"], "audit_missing").get("record"), "audit_missing")
    decision = _mapping(audit.get("decision"), "audit_missing")
    status = decision.get("status")
    governance = _mapping(bundle.get("governance"), "governance_missing")
    results: list[tuple[str, str, str]] = []
    if status == "blocked":
        results.append(("denied", "audit_not_clear", "release-quality audit is blocked"))
    elif status == "insufficient_evidence":
        results.append(("insufficient_evidence", "audit_not_clear", "release-quality audit is insufficient"))
    elif status not in {"clear", "watch"}:
        results.append(("insufficient_evidence", "audit_missing", "release-quality audit status is unknown"))
    review = _mapping(bundle["review"], "review_missing")
    review_status = review.get("status")
    queue_ids = _review_finding_ids(review)
    risk_ids = {
        finding_id
        for risk in _sequence(bundle.get("risk_acceptances"), "risk_acceptance_missing")
        for finding_id in _string_list(
            _mapping(risk, "risk_acceptance_invalid").get("finding_ids"),
            "risk_acceptance_invalid",
        )
    }
    clear_ids: set[str] = set()
    accepted_risk_ids: set[str] = set()
    clearance_evidence_hashes = _review_clearance_evidence_hashes(bundle, review)
    if review_status in {"pending_review", "pending"}:
        results.append(("denied", "review_pending", "release review has pending findings"))
    elif review_status == "blocked":
        results.append(("denied", "review_blocked", "release review is blocked"))
    elif review_status in {"insufficient_evidence", "unknown", None}:
        results.append(("insufficient_evidence", "review_insufficient_evidence", "release review evidence is insufficient"))
    elif review_status not in {"not_required", "reviewed", "cleared"}:
        results.append(("insufficient_evidence", "review_insufficient_evidence", "review evidence is not complete"))

    resolution = review.get("resolution")
    if isinstance(resolution, Mapping):
        counts = resolution.get("counts")
        resolution_decision = resolution.get("decision")
        if isinstance(counts, Mapping):
            if int(counts.get("pending", 0)) > 0:
                results.append(("denied", "review_pending", "release review has pending findings"))
            if int(counts.get("confirmed_issue", 0)) > 0:
                results.append(("denied", "review_confirmed_issue", "release review contains a confirmed issue"))
            if int(counts.get("needs_follow_up", 0)) > 0:
                results.append(("denied", "review_follow_up_required", "release review requires follow-up"))
        if isinstance(resolution_decision, Mapping):
            resolution_status = resolution_decision.get("status")
            if resolution_status == "insufficient_evidence":
                results.append(("insufficient_evidence", "review_insufficient_evidence", "review resolution evidence is insufficient"))
            elif resolution_status in {"pending_review", "pending"}:
                results.append(("denied", "review_pending", "release review has pending findings"))

    for disposition in _review_dispositions(review):
        outcome = disposition.get("outcome")
        finding_id = disposition.get("finding_id")
        if not isinstance(finding_id, str):
            results.append(("insufficient_evidence", "review_insufficient_evidence", "review disposition has no finding identity"))
            continue
        if outcome in REVIEW_BLOCKING_OUTCOMES:
            code = "review_confirmed_issue" if outcome == "confirmed_issue" else "review_follow_up_required"
            results.append(("denied", code, "release review contains an unresolved finding"))
        elif outcome in REVIEW_CLEAR_OUTCOMES:
            if not _bounded_disposition_evidence(
                disposition,
                clearance_evidence_hashes,
            ):
                results.append(("insufficient_evidence", "review_insufficient_evidence", "cleared review finding lacks bounded evidence"))
            else:
                clear_ids.add(finding_id)
        elif outcome == "accepted_risk":
            accepted_risk_ids.add(finding_id)
        elif outcome is not None:
            results.append(("denied", "review_confirmed_issue", "release review contains an unsupported disposition"))

    if review_status == "not_required" and queue_ids:
        results.append(("insufficient_evidence", "review_insufficient_evidence", "review is marked not required despite queued findings"))
    needs_review = (
        status == "watch"
        or governance.get("status") == "watch"
        or bool(_sequence(governance.get("findings"), "governance_incomplete"))
    )
    try:
        expected_finding_facts = _expected_review_finding_facts(
            audit=audit,
            governance=governance,
        )
        expected_queue_ids = set(expected_finding_facts)
    except PublishabilityContractError:
        expected_queue_ids = set()
        results.append(
            (
                "insufficient_evidence",
                "review_insufficient_evidence",
                "review queue cannot be derived from bound findings",
            )
        )
    if queue_ids != expected_queue_ids:
        if queue_ids or expected_queue_ids:
            results.append(
                (
                    "insufficient_evidence",
                    "review_identity_mismatch",
                    "review queue does not exactly cover bound findings",
                )
            )
    risk_records = [
        _mapping(risk, "risk_acceptance_invalid")
        for risk in _sequence(bundle.get("risk_acceptances"), "risk_acceptance_missing")
    ]
    for risk in risk_records:
        for finding in _sequence(risk.get("findings"), "risk_acceptance_invalid"):
            finding_record = _mapping(finding, "risk_acceptance_invalid")
            expected_facts = expected_finding_facts.get(str(finding_record.get("finding_id")))
            if expected_facts is None:
                results.append(
                    (
                        "insufficient_evidence",
                        "review_identity_mismatch",
                        "risk acceptance names a finding outside the bound review evidence",
                    )
                )
                continue
            for field in ("category", "severity", "reason_code"):
                expected_value = expected_facts.get(field)
                if expected_value is not None and finding_record.get(field) != expected_value:
                    results.append(
                        (
                            "insufficient_evidence",
                            "review_identity_mismatch",
                            "risk acceptance facts do not match the bound review finding",
                        )
                    )
                    break
    if needs_review:
        if not queue_ids:
            results.append(("insufficient_evidence", "review_missing", "watch audit findings have no review queue"))
        uncovered = queue_ids - clear_ids - risk_ids
        if accepted_risk_ids - risk_ids:
            results.append(("insufficient_evidence", "risk_acceptance_missing", "an accepted-risk disposition has no matching risk record"))
        if uncovered:
            results.append(("insufficient_evidence", "review_finding_uncovered", "a watch finding has no bounded clearance or risk record"))
    elif queue_ids and not (queue_ids <= clear_ids | risk_ids):
        results.append(("insufficient_evidence", "review_finding_uncovered", "a review finding has no bounded clearance or risk record"))
    return results


def _evaluate_risk_acceptances(
    bundle: Mapping[str, object],
    now: datetime,
    trusted_keys: Mapping[str, str | bytes],
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    requested_scope = _mapping(bundle["requested_scope"], "scope_invalid")
    policy = _mapping(bundle["authority_policy"], "authority_policy_invalid")
    revocation = _mapping(bundle["revocation"], "revocation_evidence_invalid")
    for raw in _sequence(bundle.get("risk_acceptances"), "risk_acceptance_missing"):
        risk = _mapping(raw, "risk_acceptance_invalid")
        if not scope_is_subset(requested_scope, _mapping(risk.get("permitted_scope"), "risk_acceptance_scope_mismatch")):
            results.append(("denied", "risk_acceptance_scope_mismatch", "requested scope exceeds accepted residual-risk scope"))
        if _timestamp_value(risk["expires_at"]) <= now:
            results.append(("insufficient_evidence", "risk_acceptance_expired", "risk acceptance is expired"))
        results.extend(_verify_attested_record(risk, policy, "risk_owner", now, trusted_keys, revocation))
    return results


def _evaluate_authority_policy(
    bundle: Mapping[str, object],
    now: datetime,
    trusted_policy_hashes: Iterable[str] | None,
) -> list[tuple[str, str, str]]:
    policy = _mapping(bundle["authority_policy"], "authority_policy_missing")
    trusted_hashes = {
        value
        for value in (trusted_policy_hashes or ())
        if isinstance(value, str) and _HASH_RE.fullmatch(value)
    }
    if policy.get("policy_hash") not in trusted_hashes:
        return [
            (
                "insufficient_evidence",
                "authority_policy_untrusted",
                "authority policy hash is not trusted out of band",
            )
        ]
    if _timestamp_value(policy["valid_from"]) > now:
        return [("insufficient_evidence", "evidence_expired", "authority policy is not yet valid")]
    if _timestamp_value(policy["expires_at"]) <= now:
        return [("insufficient_evidence", "authority_policy_expired", "authority policy is expired")]
    return []


def _evaluate_approval(
    bundle: Mapping[str, object],
    now: datetime,
    trusted_keys: Mapping[str, str | bytes],
) -> list[tuple[str, str, str]]:
    approval_raw = bundle.get("publication_approval")
    if approval_raw is None:
        return [("insufficient_evidence", "approval_missing", "publication approval is missing")]
    approval = _mapping(approval_raw, "approval_invalid")
    policy = _mapping(bundle["authority_policy"], "authority_policy_invalid")
    revocation = _mapping(bundle["revocation"], "revocation_evidence_invalid")
    results: list[tuple[str, str, str]] = []
    if _timestamp_value(approval["expires_at"]) <= now:
        results.append(("insufficient_evidence", "approval_expired", "publication approval is expired"))
    results.extend(_verify_attested_record(approval, policy, "publication_approver", now, trusted_keys, revocation))
    if not scope_is_subset(_mapping(bundle["requested_scope"], "scope_invalid"), _mapping(approval["approved_scope"], "scope_mismatch")):
        results.append(("denied", "scope_mismatch", "requested distribution scope exceeds publication approval"))
    if approval["known_limitations_hash"] != canonical_domain_pack_hash(_mapping(bundle["governance"], "governance_missing")["known_limitations"]):
        results.append(("insufficient_evidence", "evidence_identity_mismatch", "known limitations do not match approved governance evidence"))
    return results


def _evaluate_revocation(
    bundle: Mapping[str, object],
    now: datetime,
    trusted_keys: Mapping[str, str | bytes],
) -> list[tuple[str, str, str]]:
    revocation = _mapping(bundle["revocation"], "revocation_evidence_missing")
    if revocation.get("status") != "current":
        return [("insufficient_evidence", "revocation_evidence_invalid", "revocation evidence is not current")]
    if _timestamp_value(revocation["checked_at"]) > now:
        return [("insufficient_evidence", "revocation_evidence_invalid", "revocation evidence is from the future")]
    checked_at = _timestamp_value(revocation["checked_at"])
    policy = _mapping(bundle["authority_policy"], "authority_policy_missing")
    if checked_at < _timestamp_value(policy["valid_from"]):
        return [
            (
                "insufficient_evidence",
                "revocation_evidence_invalid",
                "revocation evidence predates the bound authority policy",
            )
        ]
    results = _verify_attested_record(
        revocation,
        policy,
        "revocation_authority",
        now,
        trusted_keys,
        revocation,
        check_scope=False,
    )
    if _timestamp_value(revocation["issued_at"]) != checked_at:
        results.append(
            (
                "insufficient_evidence",
                "revocation_evidence_invalid",
                "revocation issuance time does not match its checked time",
            )
        )
    authority_records: list[Mapping[str, object]] = []
    approval = bundle.get("publication_approval")
    if isinstance(approval, Mapping):
        authority_records.append(approval)
    authority_records.extend(
        _mapping(risk, "risk_acceptance_invalid")
        for risk in _sequence(bundle.get("risk_acceptances"), "risk_acceptance_invalid")
    )
    if any(_timestamp_value(record["issued_at"]) > checked_at for record in authority_records):
        return [
            *results,
            (
                "insufficient_evidence",
                "revocation_evidence_invalid",
                "revocation evidence predates a bound authority record",
            )
        ]
    targets = {
        str(bundle["bundle_id"]),
        str(bundle["bundle_hash"]),
        str(policy.get("policy_id")),
        str(policy.get("policy_hash")),
        str(revocation.get("revocation_id")),
        str(revocation.get("revocation_hash")),
    }
    if isinstance(approval, Mapping):
        targets.add(str(approval.get("approval_id")))
        targets.add(str(approval.get("approval_hash")))
    for risk in _sequence(bundle.get("risk_acceptances"), "risk_acceptance_invalid"):
        risk_record = _mapping(risk, "risk_acceptance_invalid")
        targets.update({str(risk_record.get("risk_acceptance_id")), str(risk_record.get("risk_acceptance_hash"))})
    revoked = set(_string_list(revocation.get("revoked_ids"), "revocation_evidence_invalid")) | set(
        _string_list(revocation.get("revoked_hashes"), "revocation_evidence_invalid")
    )
    if targets & revoked:
        return [
            *results,
            ("insufficient_evidence", "authority_revoked", "a bound authority or approval record is revoked"),
        ]
    if set(_string_list(revocation.get("revoked_policy_hashes"), "revocation_evidence_invalid")) & {
        str(policy["policy_hash"])
    }:
        return [
            *results,
            ("insufficient_evidence", "authority_revoked", "the bound authority policy is revoked"),
        ]
    return results


def _evaluate_validity(bundle: Mapping[str, object], now: datetime) -> list[tuple[str, str, str]]:
    validity = _mapping(bundle.get("validity"), "validity_missing")
    checked_at = _timestamp_value(validity["checked_at"])
    if checked_at > now:
        return [("insufficient_evidence", "evidence_expired", "publishability evidence is from the future")]
    expires_at = validity.get("expires_at")
    if expires_at is not None and _timestamp_value(expires_at) <= now:
        return [("insufficient_evidence", "validity_expired", "publishability evidence is expired")]
    return []


def _evaluate_separation_of_duties(
    bundle: Mapping[str, object],
) -> list[tuple[str, str, str]]:
    risks = [
        _mapping(item, "risk_acceptance_invalid")
        for item in _sequence(bundle.get("risk_acceptances", []), "risk_acceptance_invalid")
    ]
    if not risks:
        return []
    approval = bundle.get("publication_approval")
    if not isinstance(approval, Mapping):
        return []
    risk_principals = {str(item.get("principal_id")) for item in risks}
    approval_principal = str(approval.get("principal_id"))
    requested = normalize_distribution_scope(
        _mapping(bundle.get("requested_scope"), "scope_invalid")
    )
    policy = _validate_authority_policy(
        _mapping(bundle.get("authority_policy"), "authority_policy_invalid")
    )
    separation = _mapping(policy["separation_of_duties"], "authority_policy_invalid")
    external = requested["access"] in {"external", "public"} or bool(
        set(requested["audience"]) & {"external", "public"}
    )
    if external and separation["external_residual_risk_requires_distinct_principals"] and approval_principal in risk_principals:
        return [("denied", "separation_of_duties_violation", "external residual risk requires distinct authority principals")]
    risk_keys = {str(item.get("key_id")) for item in risks}
    if (
        external
        and separation["external_residual_risk_requires_distinct_principals"]
        and str(approval.get("key_id")) in risk_keys
    ):
        return [
            (
                "denied",
                "separation_of_duties_violation",
                "external residual risk requires distinct cryptographic authority keys",
            )
        ]
    if not external and approval_principal in risk_principals:
        if not separation["internal_role_combination_allowed"]:
            return [("denied", "separation_of_duties_violation", "internal role combination is not permitted by policy")]
        grant = _grant_for(policy, approval_principal)
        roles = set(_string_list(grant.get("roles"), "authority_role_mismatch")) if grant else set()
        if not {"risk_owner", "publication_approver"} <= roles:
            return [("denied", "separation_of_duties_violation", "combined internal authority lacks both policy roles")]
    return []


def _evaluate_scope(bundle: Mapping[str, object]) -> list[tuple[str, str, str]]:
    try:
        requested = normalize_distribution_scope(_mapping(bundle["requested_scope"], "scope_invalid"))
        approval = _mapping(bundle.get("publication_approval"), "approval_missing")
        approved = normalize_distribution_scope(_mapping(approval["approved_scope"], "scope_invalid"))
    except PublishabilityContractError as exc:
        return [("insufficient_evidence", exc.reason_code, "distribution scope is invalid")]
    if not scope_is_subset(requested, approved):
        return [("denied", "scope_mismatch", "requested distribution scope is broader than approved scope")]
    return []


def _verify_attested_record(
    record: Mapping[str, object],
    policy: Mapping[str, object],
    expected_role: str,
    now: datetime,
    trusted_keys: Mapping[str, str | bytes],
    revocation: Mapping[str, object],
    *,
    check_scope: bool = True,
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    if (
        record.get("authority_policy_hash") != policy.get("policy_hash")
        or record.get("authority_policy_id") != policy.get("policy_id")
        or record.get("authority_policy_version") != policy.get("policy_version")
    ):
        results.append(("insufficient_evidence", "authority_policy_mismatch", "authority record is bound to another policy"))
    if record.get("role") != expected_role:
        results.append(("insufficient_evidence", "authority_role_mismatch", "authority record role is not authorized for this decision"))
    principal_id = record.get("principal_id")
    key_id = record.get("key_id")
    grant = _grant_for(policy, principal_id)
    if grant is None:
        results.append(("insufficient_evidence", "authority_principal_unknown", "authority principal is not granted by policy"))
    else:
        if grant.get("key_id") != key_id:
            results.append(("insufficient_evidence", "authority_key_mismatch", "authority principal is bound to another key"))
        if expected_role not in _string_list(grant.get("roles"), "authority_role_mismatch"):
            results.append(("insufficient_evidence", "authority_role_mismatch", "authority principal lacks the required role"))
        if check_scope and not scope_is_subset(
            _mapping(record.get("approved_scope", record.get("permitted_scope")), "scope_invalid"),
            _mapping(grant.get("scope"), "scope_invalid"),
        ):
            results.append(("denied", "scope_mismatch", "authority grant does not cover the record scope"))
        if _timestamp_value(grant["expires_at"]) <= now:
            results.append(("insufficient_evidence", "authority_grant_expired", "authority grant is expired"))
        if _timestamp_value(record["expires_at"]) > _timestamp_value(grant["expires_at"]):
            results.append(
                (
                    "insufficient_evidence",
                    "authority_grant_expired",
                    "authority record outlives its authority grant",
                )
            )
        if _timestamp_value(grant["valid_from"]) > _timestamp_value(record["issued_at"]):
            results.append(
                (
                    "insufficient_evidence",
                    "authority_grant_not_yet_valid",
                    "authority record predates its authority grant",
                )
            )
        key_record = _policy_key(policy, key_id)
        supplied_key = trusted_keys.get(str(key_id))
        if key_record is None or supplied_key is None:
            results.append(("insufficient_evidence", "authority_key_mismatch", "authority key is not in the bound trust root"))
        elif key_record.get("fingerprint") != fingerprint_for_key(supplied_key):
            results.append(("insufficient_evidence", "authority_key_mismatch", "authority key does not match the bound trust root"))
    if _timestamp_value(record["issued_at"]) > now or _timestamp_value(record["expires_at"]) <= now:
        results.append(("insufficient_evidence", "evidence_expired", "authority record is outside its validity interval"))
    if _timestamp_value(record["expires_at"]) > _timestamp_value(policy["expires_at"]):
        results.append(
            (
                "insufficient_evidence",
                "authority_policy_expired",
                "authority record outlives its authority policy",
            )
        )
    attestation = record.get("attestation")
    if not isinstance(attestation, Mapping):
        results.append(("insufficient_evidence", "authority_attestation_missing", "authority record is unsigned"))
    else:
        key = trusted_keys.get(str(key_id))
        if key is None:
            results.append(("insufficient_evidence", "authority_signature_invalid", "authority key material is unavailable"))
        else:
            try:
                expected = build_authenticated_attestation(
                    _attestable_content(record),
                    principal_id=_identifier(principal_id),
                    key_id=_identifier(key_id),
                    signing_key=key,
                )
                if dict(attestation) != expected:
                    results.append(("insufficient_evidence", "authority_signature_invalid", "authority attestation does not verify"))
            except PublishabilityContractError:
                results.append(("insufficient_evidence", "authority_signature_invalid", "authority attestation does not verify"))
    record_targets = {
        str(record.get("risk_acceptance_id")),
        str(record.get("approval_id")),
        str(record.get("risk_acceptance_hash")),
        str(record.get("approval_hash")),
        str(record.get("revocation_id")),
        str(record.get("revocation_hash")),
    }
    revoked = set(_string_list(revocation.get("revoked_ids"), "revocation_evidence_invalid")) | set(_string_list(revocation.get("revoked_hashes"), "revocation_evidence_invalid"))
    if record_targets & revoked or str(principal_id) in set(_string_list(revocation.get("revoked_principals"), "revocation_evidence_invalid")) or str(key_id) in set(_string_list(revocation.get("revoked_keys"), "revocation_evidence_invalid")):
        results.append(("insufficient_evidence", "authority_revoked", "authority record or principal is revoked"))
    return results


def _policy_key(policy: Mapping[str, object], key_id: object) -> Mapping[str, object] | None:
    root = _mapping(policy.get("trust_root"), "authority_policy_invalid")
    for raw in _sequence(root.get("keys"), "authority_policy_invalid"):
        if isinstance(raw, Mapping) and raw.get("key_id") == key_id:
            return raw
    return None


def _decision(
    *,
    bundle: Mapping[str, object],
    status: str,
    effective_qualification: str,
    reason_codes: Sequence[str],
    reasons: Sequence[str],
    conformance_status: str,
    requested_scope: Mapping[str, object] | None,
) -> dict[str, object]:
    raw_subject = bundle.get("subject") if isinstance(bundle.get("subject"), Mapping) else None
    try:
        subject = _normalize_subject(raw_subject) if raw_subject is not None else _empty_subject()
    except Exception:
        subject = _empty_subject()
    scope = requested_scope or _empty_scope()
    raw_bundle_hash = bundle.get("bundle_hash")
    bundle_hash = raw_bundle_hash if isinstance(raw_bundle_hash, str) and _HASH_RE.fullmatch(raw_bundle_hash) else None
    raw_bundle_id = bundle.get("bundle_id")
    bundle_id = raw_bundle_id if isinstance(raw_bundle_id, str) and _IDENTIFIER_RE.fullmatch(raw_bundle_id) else None
    content: dict[str, object] = {
        "schema_version": PUBLISHABILITY_DECISION_SCHEMA_VERSION,
        "bundle_hash": bundle_hash,
        "bundle_id": bundle_id,
        "subject": dict(subject),
        "requested_scope": dict(scope),
        "status": status,
        "effective_qualification": effective_qualification,
        "reason_codes": _unique(reason_codes),
        "reasons": _unique(reasons),
        "evidence_class": (
            bundle.get("evidence_class")
            if bundle.get("evidence_class") in PUBLISHABILITY_EVIDENCE_CLASSES
            else "unknown"
        ),
        "conformance": {
            "status": conformance_status,
            "effective_qualification": "publishable" if conformance_status == "passed" else "release_candidate",
        },
    }
    digest = canonical_domain_pack_hash(content)
    return {**content, "decision_id": "publishability_decision_" + digest.removeprefix("sha256:")[:16]}


def _with_content_identity(
    record: Mapping[str, object],
    *,
    id_field: str,
    hash_field: str,
    prefix: str,
    preserve_id: bool = False,
) -> dict[str, object]:
    content = dict(record)
    original_id = content.get(id_field)
    if not preserve_id:
        content.pop(id_field, None)
    content.pop(hash_field, None)
    digest = canonical_domain_pack_hash(content)
    result = {**content, hash_field: digest}
    result[id_field] = original_id if preserve_id else prefix + digest.removeprefix("sha256:")[:16]
    if not isinstance(result[id_field], str):
        raise PublishabilityContractError("evidence_malformed")
    return result


def _with_attested_identity(record: Mapping[str, object], *, signing_key: str | bytes) -> dict[str, object]:
    content = dict(record)
    attestation = build_authenticated_attestation(
        content,
        principal_id=_identifier(content["principal_id"]),
        key_id=_identifier(content["key_id"]),
        signing_key=signing_key,
    )
    with_attestation = {**content, "attestation": attestation}
    digest = canonical_domain_pack_hash(with_attestation)
    if content["schema_version"] == RISK_ACCEPTANCE_SCHEMA_VERSION:
        id_field, hash_field, prefix = "risk_acceptance_id", "risk_acceptance_hash", "risk_acceptance_"
    elif content["schema_version"] == PUBLICATION_APPROVAL_SCHEMA_VERSION:
        id_field, hash_field, prefix = "approval_id", "approval_hash", "publication_approval_"
    else:
        id_field, hash_field, prefix = "revocation_id", "revocation_hash", "revocation_evidence_"
    return {
        **with_attestation,
        hash_field: digest,
        id_field: prefix + digest.removeprefix("sha256:")[:16],
    }


def _validate_governance(record: Mapping[str, object]) -> dict[str, object]:
    required = {"schema_version", "subject", "proposed_scope", "checks", "findings", "known_limitations", "status", "governance_hash", "governance_id"}
    if set(record) != required or record.get("schema_version") != PUBLICATION_GOVERNANCE_SCHEMA_VERSION:
        raise PublishabilityContractError("evidence_unknown_version" if record.get("schema_version") not in {PUBLICATION_GOVERNANCE_SCHEMA_VERSION} else "evidence_malformed")
    _normalize_subject(_mapping(record.get("subject"), "evidence_malformed"))
    normalize_distribution_scope(_mapping(record.get("proposed_scope"), "scope_invalid"))
    checks = _normalize_governance_checks(_mapping(record.get("checks"), "governance_incomplete"))
    findings = _normalize_findings(_sequence(record.get("findings"), "governance_incomplete"))
    if record.get("status") not in {"clear", "watch", "blocked", "insufficient_evidence"}:
        raise PublishabilityContractError("governance_incomplete")
    if record.get("status") != _governance_status(checks, findings):
        raise PublishabilityContractError("governance_incomplete")
    if record.get("governance_hash") != canonical_domain_pack_hash({key: record[key] for key in required if key not in {"governance_hash", "governance_id"}}):
        raise PublishabilityContractError("evidence_hash_mismatch")
    expected_id = "publication_governance_" + str(record["governance_hash"]).removeprefix("sha256:")[:16]
    if record.get("governance_id") != expected_id:
        raise PublishabilityContractError("evidence_malformed")
    return dict(record) | {"checks": checks, "findings": findings}


def validate_publication_governance_record(record: Mapping[str, object]) -> None:
    _validate_governance(record)


def _validate_authority_policy(record: Mapping[str, object]) -> dict[str, object]:
    required = {"schema_version", "policy_id", "policy_version", "trust_root", "grants", "separation_of_duties", "valid_from", "expires_at", "policy_hash"}
    if set(record) != required or record.get("schema_version") != AUTHORITY_POLICY_SCHEMA_VERSION:
        raise PublishabilityContractError("authority_policy_invalid")
    _identifier(record.get("policy_id"))
    _version(record.get("policy_version"))
    normalized_root = _normalize_trust_root(_mapping(record.get("trust_root"), "authority_policy_invalid"))
    normalized_grants = _normalize_grants(_sequence(record.get("grants"), "authority_policy_invalid"))
    _ensure_grant_keys(normalized_root, normalized_grants)
    _normalize_separation_policy(_mapping(record.get("separation_of_duties"), "authority_policy_invalid"))
    _timestamp(record.get("valid_from"))
    _timestamp(record.get("expires_at"))
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["valid_from"]):
        raise PublishabilityContractError("authority_policy_invalid")
    content = {key: record[key] for key in required if key != "policy_hash"}
    if record.get("policy_hash") != canonical_domain_pack_hash(content):
        raise PublishabilityContractError("evidence_hash_mismatch")
    return dict(record)


def validate_authority_policy_record(record: Mapping[str, object]) -> None:
    _validate_authority_policy(record)


def _validate_risk_acceptance(record: Mapping[str, object]) -> dict[str, object]:
    required = {"schema_version", "subject", "finding_ids", "findings", "permitted_scope", "authority_policy_id", "authority_policy_version", "authority_policy_hash", "principal_id", "role", "key_id", "issued_at", "expires_at", "decision", "attestation", "risk_acceptance_hash", "risk_acceptance_id"}
    if set(record) != required or record.get("schema_version") != RISK_ACCEPTANCE_SCHEMA_VERSION:
        raise PublishabilityContractError("risk_acceptance_invalid")
    _normalize_subject(_mapping(record.get("subject"), "risk_acceptance_invalid"))
    findings = _normalize_risk_findings(_sequence(record.get("findings"), "risk_acceptance_invalid"))
    ids = _string_list(record.get("finding_ids"), "risk_acceptance_invalid")
    if ids != sorted(set(ids)) or ids != sorted(str(item["finding_id"]) for item in findings):
        raise PublishabilityContractError("risk_acceptance_invalid")
    normalize_distribution_scope(_mapping(record.get("permitted_scope"), "risk_acceptance_invalid"))
    if record.get("role") != "risk_owner" or record.get("decision") != "accepted":
        raise PublishabilityContractError("risk_acceptance_invalid")
    _identifier(record.get("principal_id")); _identifier(record.get("key_id"))
    _timestamp(record.get("issued_at")); _timestamp(record.get("expires_at"))
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"]):
        raise PublishabilityContractError("risk_acceptance_invalid")
    _validate_attestation_shape(_mapping(record.get("attestation"), "authority_attestation_missing"))
    content = {key: record[key] for key in required if key not in {"risk_acceptance_hash", "risk_acceptance_id"}}
    digest = canonical_domain_pack_hash(content)
    if record.get("risk_acceptance_hash") != digest or record.get("risk_acceptance_id") != "risk_acceptance_" + digest.removeprefix("sha256:")[:16]:
        raise PublishabilityContractError("evidence_hash_mismatch")
    for finding in findings:
        if finding["category"] in HARD_GOVERNANCE_CHECKS or finding.get("waives_hard_gate") is True:
            raise PublishabilityContractError("risk_acceptance_hard_gate")
    return dict(record)


def validate_risk_acceptance_record(record: Mapping[str, object]) -> None:
    _validate_risk_acceptance(record)


def _validate_publication_approval(record: Mapping[str, object]) -> dict[str, object]:
    required = {"schema_version", "subject", "bundle_hash", "approved_scope", "known_limitations", "known_limitations_hash", "evidence_class", "authority_policy_id", "authority_policy_version", "authority_policy_hash", "principal_id", "role", "key_id", "issued_at", "expires_at", "decision", "attestation", "approval_hash", "approval_id"}
    if set(record) != required or record.get("schema_version") != PUBLICATION_APPROVAL_SCHEMA_VERSION:
        raise PublishabilityContractError("approval_invalid")
    _normalize_subject(_mapping(record.get("subject"), "approval_invalid"))
    _hash_value(record.get("bundle_hash")); normalize_distribution_scope(_mapping(record.get("approved_scope"), "approval_invalid"))
    if record.get("evidence_class") not in PUBLISHABILITY_EVIDENCE_CLASSES:
        raise PublishabilityContractError("approval_invalid")
    limitations = _bounded_string_list(record.get("known_limitations"))
    if record.get("known_limitations_hash") != canonical_domain_pack_hash(limitations):
        raise PublishabilityContractError("evidence_identity_mismatch")
    if record.get("role") != "publication_approver" or record.get("decision") != "approved":
        raise PublishabilityContractError("approval_invalid")
    _identifier(record.get("principal_id")); _identifier(record.get("key_id"))
    _timestamp(record.get("issued_at")); _timestamp(record.get("expires_at"))
    if _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"]):
        raise PublishabilityContractError("approval_invalid")
    _validate_attestation_shape(_mapping(record.get("attestation"), "authority_attestation_missing"))
    content = {key: record[key] for key in required if key not in {"approval_hash", "approval_id"}}
    digest = canonical_domain_pack_hash(content)
    if record.get("approval_hash") != digest or record.get("approval_id") != "publication_approval_" + digest.removeprefix("sha256:")[:16]:
        raise PublishabilityContractError("evidence_hash_mismatch")
    return dict(record)


def validate_publication_approval_record(record: Mapping[str, object]) -> None:
    _validate_publication_approval(record)


def _validate_revocation(record: Mapping[str, object]) -> dict[str, object]:
    required = {"schema_version", "authority_policy_id", "authority_policy_version", "authority_policy_hash", "checked_at", "source_id", "status", "principal_id", "role", "key_id", "issued_at", "expires_at", "revoked_ids", "revoked_hashes", "revoked_principals", "revoked_keys", "revoked_policy_hashes", "attestation", "revocation_hash", "revocation_id"}
    if set(record) != required or record.get("schema_version") != REVOCATION_EVIDENCE_SCHEMA_VERSION:
        raise PublishabilityContractError("revocation_evidence_invalid")
    _identifier(record.get("authority_policy_id")); _version(record.get("authority_policy_version")); _hash_value(record.get("authority_policy_hash")); _timestamp(record.get("checked_at")); _identifier(record.get("source_id")); _identifier(record.get("principal_id")); _identifier(record.get("key_id")); _timestamp(record.get("issued_at")); _timestamp(record.get("expires_at"))
    if (
        record.get("role") != "revocation_authority"
        or record.get("issued_at") != record.get("checked_at")
        or _timestamp_value(record["expires_at"]) <= _timestamp_value(record["issued_at"])
    ):
        raise PublishabilityContractError("revocation_evidence_invalid")
    _validate_attestation_shape(_mapping(record.get("attestation"), "authority_attestation_missing"))
    if record.get("status") not in {"current", "stale", "revoked", "unknown"}:
        raise PublishabilityContractError("revocation_evidence_invalid")
    _bounded_identifier_list(record.get("revoked_ids")); [_hash_value(value) for value in _sequence(record.get("revoked_hashes"), "revocation_evidence_invalid")]
    _bounded_identifier_list(record.get("revoked_principals")); _bounded_identifier_list(record.get("revoked_keys")); [_hash_value(value) for value in _sequence(record.get("revoked_policy_hashes"), "revocation_evidence_invalid")]
    content = {key: record[key] for key in required if key not in {"revocation_hash", "revocation_id"}}
    digest = canonical_domain_pack_hash(content)
    if record.get("revocation_hash") != digest or record.get("revocation_id") != "revocation_evidence_" + digest.removeprefix("sha256:")[:16]:
        raise PublishabilityContractError("evidence_hash_mismatch")
    return dict(record)


def validate_revocation_evidence_record(record: Mapping[str, object]) -> None:
    _validate_revocation(record)


def _validate_audit(record: Mapping[str, object]) -> dict[str, object]:
    try:
        validate_release_quality_audit_record(record)
    except (ContractValidationError, TypeError, ValueError, RecursionError) as exc:
        raise PublishabilityContractError("audit_missing") from exc
    return dict(record)


def _normalize_review(review: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(review, Mapping):
        raise PublishabilityContractError("review_missing")
    status = review.get("status")
    queue_raw = review.get("queue", [])
    queue = list(_sequence(queue_raw, "review_missing"))
    for item in queue:
        if not isinstance(item, Mapping):
            raise PublishabilityContractError("review_insufficient_evidence")
        if item.get("schema_version") == "release_review_item_v1":
            try:
                validate_release_review_item_record(item)
            except (ContractValidationError, TypeError, ValueError, RecursionError) as exc:
                raise PublishabilityContractError("review_insufficient_evidence") from exc
        elif item.get("schema_version") == PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION:
            _validate_publishability_review_item(item)
        else:
            raise PublishabilityContractError("review_insufficient_evidence")
    resolution = review.get("resolution")
    if isinstance(resolution, Mapping) and resolution.get("schema_version") == "review_resolution_report_v1":
        try:
            validate_review_resolution_report_record(resolution)
        except (ContractValidationError, TypeError, ValueError, RecursionError) as exc:
            raise PublishabilityContractError("review_insufficient_evidence") from exc
    elif resolution is not None:
        raise PublishabilityContractError("review_insufficient_evidence")
    if status not in {"not_required", "reviewed", "cleared", "pending_review", "blocked", "insufficient_evidence", "unknown"}:
        raise PublishabilityContractError("review_insufficient_evidence")
    dispositions = list(_sequence(review.get("dispositions", []), "review_insufficient_evidence"))
    for disposition in dispositions:
        if not isinstance(disposition, Mapping) or not isinstance(disposition.get("finding_id"), str):
            raise PublishabilityContractError("review_insufficient_evidence")
    return {
        "status": status,
        "queue": [dict(item) for item in queue],
        "resolution": dict(resolution) if isinstance(resolution, Mapping) else None,
        "dispositions": [dict(item) for item in dispositions],
        "queue_hash": canonical_domain_pack_hash([dict(item) for item in queue]),
        "resolution_hash": canonical_domain_pack_hash(dict(resolution)) if isinstance(resolution, Mapping) else None,
    }


def _validate_publishability_review_item(
    record: Mapping[str, object],
) -> None:
    required = {
        "schema_version",
        "review_item_id",
        "finding_id",
        "category",
        "severity",
        "reason_code",
        "source",
    }
    if set(record) != required or record.get("schema_version") != PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION:
        raise PublishabilityContractError("review_insufficient_evidence")
    finding_id = _identifier(record.get("finding_id"))
    category = _identifier(record.get("category"))
    severity = record.get("severity")
    reason_code = record.get("reason_code")
    if severity not in RISK_SEVERITIES or not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
        raise PublishabilityContractError("review_insufficient_evidence")
    if record.get("source") != "publication_governance":
        raise PublishabilityContractError("review_insufficient_evidence")
    review_item_id = _identifier(record.get("review_item_id"))
    content = {
        "schema_version": PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION,
        "finding_id": finding_id,
        "category": category,
        "severity": severity,
        "reason_code": reason_code,
        "source": "publication_governance",
    }
    digest = canonical_domain_pack_hash(content)
    if review_item_id != "publication_review_item_" + digest.removeprefix("sha256:")[:16]:
        raise PublishabilityContractError("review_insufficient_evidence")


def _validate_attestation_shape(attestation: Mapping[str, object]) -> None:
    required = {"schema_version", "algorithm", "principal_id", "key_id", "payload_hash", "signature"}
    if set(attestation) != required or attestation.get("schema_version") != AUTHORITY_ATTESTATION_SCHEMA_VERSION or attestation.get("algorithm") != "hmac-sha256":
        raise PublishabilityContractError("authority_attestation_missing")
    _identifier(attestation.get("principal_id")); _identifier(attestation.get("key_id")); _hash_value(attestation.get("payload_hash")); _hash_value(attestation.get("signature"))


def validate_authority_attestation_record(record: Mapping[str, object]) -> None:
    _validate_attestation_shape(record)


def _attestable_content(record: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in record.items()
        if key
        not in {
            "attestation",
            "risk_acceptance_id",
            "risk_acceptance_hash",
            "approval_id",
            "approval_hash",
            "revocation_id",
            "revocation_hash",
        }
    }


def _hmac_signature(payload: Mapping[str, object], key: str | bytes) -> str:
    raw_key = key.encode("utf-8") if isinstance(key, str) else key
    if not isinstance(raw_key, bytes) or not raw_key:
        raise PublishabilityContractError("authority_signature_invalid")
    digest = hmac.new(raw_key, canonical_domain_pack_json(dict(payload)).encode("utf-8"), hashlib.sha256).hexdigest()
    return "sha256:" + digest


def _normalize_subject(subject: Mapping[str, object]) -> dict[str, object]:
    required = {"subject_id", "subject_hash", "release_id", "release_pack_hash", "release_pack_byte_count", "dataset_version", "domain_pack_reference", "plan_id", "plan_hash"}
    if not isinstance(subject, Mapping) or set(subject) != required:
        raise PublishabilityContractError("evidence_malformed")
    result = dict(subject)
    _identifier(result["subject_id"]); _hash_value(result["subject_hash"]); _identifier(result["release_id"]); _hash_value(result["release_pack_hash"]); _positive_int(result["release_pack_byte_count"]); _identifier(result["dataset_version"]); _identifier(result["plan_id"]); _hash_value(result["plan_hash"])
    domain = _mapping(result["domain_pack_reference"], "evidence_malformed")
    if set(domain) != {"schema_version", "domain_pack_id", "pack_version", "pack_hash"}:
        raise PublishabilityContractError("evidence_malformed")
    if domain.get("schema_version") != "domain_pack_reference_v1":
        raise PublishabilityContractError("evidence_unknown_version")
    _identifier(domain["domain_pack_id"]); _identifier(domain["pack_version"]); _hash_value(domain["pack_hash"])
    return result


def _normalize_governance_checks(checks: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    if not isinstance(checks, Mapping) or set(checks) != set(GOVERNANCE_CHECKS):
        raise PublishabilityContractError("governance_incomplete")
    normalized: dict[str, object] = {}
    for check in GOVERNANCE_CHECKS:
        raw = checks.get(check)
        if not isinstance(raw, Mapping) or set(raw) - {"status", "evidence_id", "evidence_hash", "reason_code"}:
            raise PublishabilityContractError("governance_incomplete")
        status = raw.get("status")
        if status not in GOVERNANCE_CHECK_STATUSES:
            raise PublishabilityContractError("governance_incomplete")
        if status == "not_applicable" and not isinstance(raw.get("reason_code"), str):
            raise PublishabilityContractError("governance_incomplete")
        if status in {"passed", "not_applicable"} and not isinstance(
            raw.get("evidence_id", raw.get("reason_code")), str
        ):
            raise PublishabilityContractError("governance_incomplete")
        if status in {"passed", "not_applicable"} and not isinstance(
            raw.get("evidence_hash"), str
        ):
            raise PublishabilityContractError("governance_incomplete")
        item = {"status": status}
        for key in ("evidence_id", "evidence_hash", "reason_code"):
            if key in raw:
                item[key] = raw[key]
        if "evidence_id" in item:
            _identifier(item["evidence_id"])
        if "evidence_hash" in item:
            _hash_value(item["evidence_hash"])
        if "reason_code" in item:
            if not isinstance(item["reason_code"], str) or not _REASON_RE.fullmatch(item["reason_code"]):
                raise PublishabilityContractError("governance_incomplete")
        normalized[check] = item
    return normalized


def _normalize_findings(findings: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if isinstance(findings, (str, bytes)) or not isinstance(findings, Sequence):
        raise PublishabilityContractError("governance_incomplete")
    for raw in findings:
        if not isinstance(raw, Mapping):
            raise PublishabilityContractError("governance_incomplete")
        finding_id = raw.get("finding_id")
        category = raw.get("category")
        severity = raw.get("severity")
        reason_code = raw.get("reason_code")
        if not isinstance(finding_id, str) or not _IDENTIFIER_RE.fullmatch(finding_id) or not isinstance(category, str) or not _IDENTIFIER_RE.fullmatch(category) or severity not in RISK_SEVERITIES or not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
            raise PublishabilityContractError("governance_incomplete")
        result.append({
            "finding_id": finding_id,
            "category": category,
            "severity": severity,
            "reason_code": reason_code,
            "status": raw.get("status", "open"),
        })
    ids = [str(item["finding_id"]) for item in result]
    if ids != sorted(set(ids)):
        raise PublishabilityContractError("governance_incomplete")
    return result


def _normalize_risk_findings(findings: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in _sequence(findings, "risk_acceptance_invalid"):
        if not isinstance(raw, Mapping):
            raise PublishabilityContractError("risk_acceptance_invalid")
        finding_id = raw.get("finding_id")
        category = raw.get("category")
        severity = raw.get("severity")
        reason_code = raw.get("reason_code")
        controls = raw.get("controls")
        waives_hard_gate = raw.get("waives_hard_gate", False)
        if not isinstance(finding_id, str) or not _IDENTIFIER_RE.fullmatch(finding_id) or not isinstance(category, str) or not _IDENTIFIER_RE.fullmatch(category) or severity not in RISK_SEVERITIES or not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code) or not isinstance(controls, Sequence) or isinstance(controls, (str, bytes)):
            raise PublishabilityContractError("risk_acceptance_invalid")
        if not isinstance(waives_hard_gate, bool):
            raise PublishabilityContractError("risk_acceptance_invalid")
        normalized_controls = _bounded_identifier_list(controls)
        if not normalized_controls:
            raise PublishabilityContractError("risk_acceptance_invalid")
        result.append({
            "finding_id": finding_id,
            "category": category,
            "severity": severity,
            "reason_code": reason_code,
            "controls": normalized_controls,
            "waives_hard_gate": waives_hard_gate,
        })
    ids = [str(item["finding_id"]) for item in result]
    if ids != sorted(set(ids)):
        raise PublishabilityContractError("risk_acceptance_invalid")
    return result


def _normalize_trust_root(root: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(root, Mapping) or set(root) != {"root_id", "keys"}:
        raise PublishabilityContractError("authority_policy_invalid")
    _identifier(root.get("root_id"))
    keys = _sequence(root.get("keys"), "authority_policy_invalid")
    normalized: list[dict[str, object]] = []
    for raw in keys:
        item = _mapping(raw, "authority_policy_invalid")
        if set(item) != {"key_id", "fingerprint"}:
            raise PublishabilityContractError("authority_policy_invalid")
        normalized.append({"key_id": _identifier(item["key_id"]), "fingerprint": _hash_value(item["fingerprint"])})
    if not normalized or len({str(item["key_id"]) for item in normalized}) != len(normalized):
        raise PublishabilityContractError("authority_policy_invalid")
    return {"root_id": root["root_id"], "keys": sorted(normalized, key=lambda item: str(item["key_id"]))}


def _normalize_grants(grants: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in _sequence(grants, "authority_policy_invalid"):
        item = _mapping(raw, "authority_policy_invalid")
        required = {"principal_id", "key_id", "roles", "scope", "valid_from", "expires_at"}
        if set(item) != required:
            raise PublishabilityContractError("authority_policy_invalid")
        roles = _string_list(item.get("roles"), "authority_policy_invalid")
        if not roles or not set(roles) <= AUTHORITY_ROLES:
            raise PublishabilityContractError("authority_policy_invalid")
        result.append({
            "principal_id": _identifier(item["principal_id"]),
            "key_id": _identifier(item["key_id"]),
            "roles": sorted(set(roles)),
            "scope": normalize_distribution_scope(_mapping(item["scope"], "authority_policy_invalid")),
            "valid_from": _timestamp(item["valid_from"]),
            "expires_at": _timestamp(item["expires_at"]),
        })
        if _timestamp_value(result[-1]["expires_at"]) <= _timestamp_value(result[-1]["valid_from"]):
            raise PublishabilityContractError("authority_policy_invalid")
    if len({str(item["principal_id"]) for item in result}) != len(result):
        raise PublishabilityContractError("authority_policy_invalid")
    return sorted(result, key=lambda item: str(item["principal_id"]))


def _ensure_grant_keys(
    trust_root: Mapping[str, object],
    grants: Sequence[Mapping[str, object]],
) -> None:
    keys = {
        str(_mapping(item, "authority_policy_invalid")["key_id"])
        for item in _sequence(trust_root.get("keys"), "authority_policy_invalid")
    }
    if any(str(grant.get("key_id")) not in keys for grant in grants):
        raise PublishabilityContractError("authority_key_mismatch")


def _normalize_separation_policy(policy: Mapping[str, object]) -> dict[str, object]:
    required = {"external_residual_risk_requires_distinct_principals", "internal_role_combination_allowed"}
    if not isinstance(policy, Mapping) or set(policy) != required or any(not isinstance(policy[key], bool) for key in required):
        raise PublishabilityContractError("authority_policy_invalid")
    return dict(policy)


def _normalize_validity(validity: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(validity, Mapping) or set(validity) - {"checked_at", "expires_at"} or "checked_at" not in validity:
        raise PublishabilityContractError("validity_missing")
    result = {"checked_at": _timestamp(validity["checked_at"])}
    if "expires_at" in validity:
        result["expires_at"] = _timestamp(validity["expires_at"])
    return result


def _release_pack_reference(
    release_pack: Mapping[str, object] | None,
    *,
    release_pack_hash: str,
    byte_count: int,
    dataset_version: str,
) -> dict[str, object]:
    supplied = dict(release_pack or {})
    supplied_hash = supplied.get("content_hash", supplied.get("release_pack_hash", supplied.get("sha256")))
    if supplied_hash is not None and supplied_hash != release_pack_hash:
        raise PublishabilityContractError("evidence_identity_mismatch")
    release_id = supplied.get("release_id", dataset_version)
    if not isinstance(release_id, str) or not release_id:
        raise PublishabilityContractError("evidence_malformed")
    supplied_dataset = supplied.get("dataset_version")
    if supplied_dataset is not None and supplied_dataset != dataset_version:
        raise PublishabilityContractError("evidence_identity_mismatch")
    supplied_bytes = supplied.get("byte_count", supplied.get("release_pack_byte_count", byte_count))
    if supplied_bytes != byte_count:
        raise PublishabilityContractError("evidence_identity_mismatch")
    resolved_dataset = supplied.get("dataset_version", dataset_version)
    supplied_record_hash = supplied.get("record_hash")
    record_payload = {
        key: value for key, value in supplied.items() if key != "record_hash"
    }
    record_hash = (
        canonical_domain_pack_hash(record_payload)
        if supplied
        else release_pack_hash
    )
    if supplied_record_hash is not None and supplied_record_hash != record_hash:
        raise PublishabilityContractError("evidence_hash_mismatch")
    _hash_value(record_hash)
    return {
        "release_id": _identifier(str(release_id)),
        "dataset_version": _identifier(str(resolved_dataset)),
        "content_hash": release_pack_hash,
        "byte_count": byte_count,
        "record_hash": record_hash,
    }


def _governance_status(checks: Mapping[str, object], findings: Sequence[Mapping[str, object]]) -> str:
    statuses = [str(_mapping(checks[key], "governance_incomplete")["status"]) for key in GOVERNANCE_CHECKS]
    if any(status in {"unknown", "insufficient_evidence"} for status in statuses):
        return "insufficient_evidence"
    if any(status in {"failed", "blocked"} for status in statuses):
        return "blocked"
    if any(status == "watch" for status in statuses) or findings:
        return "watch"
    return "clear"


def _review_dispositions(review: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = review.get("dispositions", [])
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _review_finding_ids(review: Mapping[str, object]) -> set[str]:
    ids: set[str] = set()
    for item in _sequence(review.get("queue", []), "review_missing"):
        if isinstance(item, Mapping):
            value = item.get("finding_id", item.get("review_item_id"))
            if isinstance(value, str):
                ids.add(value)
    return ids


def _expected_review_finding_facts(
    *,
    audit: Mapping[str, object],
    governance: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    expected = {
        str(_mapping(finding, "governance_incomplete")["finding_id"]): {
            field: _mapping(finding, "governance_incomplete").get(field)
            for field in ("category", "severity", "reason_code")
        }
        for finding in _sequence(governance.get("findings"), "governance_incomplete")
    }
    audit_decision = _mapping(audit.get("decision"), "audit_missing")
    if audit_decision.get("status") == "watch":
        from synthesis.release_review import build_release_review_items

        for item in build_release_review_items(audit):
            risk = _mapping(item["risk"], "review_insufficient_evidence")
            risk_kind = risk.get("kind")
            if not isinstance(risk_kind, str) or risk_kind not in AUDIT_RISK_FACTS:
                raise PublishabilityContractError("review_insufficient_evidence")
            severity, reason_code = AUDIT_RISK_FACTS[risk_kind]
            expected[str(item["review_item_id"])] = {
                "category": risk_kind,
                "severity": severity,
                "reason_code": reason_code,
            }
    return expected


def _bounded_disposition_evidence(
    disposition: Mapping[str, object],
    evidence_hashes: Mapping[str, str],
) -> bool:
    evidence_id = disposition.get("evidence_id")
    evidence_hash = disposition.get("evidence_hash")
    return (
        isinstance(evidence_id, str)
        and bool(_IDENTIFIER_RE.fullmatch(evidence_id))
        and isinstance(evidence_hash, str)
        and bool(_HASH_RE.fullmatch(evidence_hash))
        and evidence_hashes.get(evidence_id) == evidence_hash
    )


def _review_clearance_evidence_hashes(
    bundle: Mapping[str, object],
    review: Mapping[str, object],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for item in _sequence(review.get("queue"), "review_missing"):
        if isinstance(item, Mapping) and isinstance(item.get("review_item_id"), str):
            item_hash = canonical_domain_pack_hash(dict(item))
            hashes[str(item["review_item_id"])] = item_hash
            if isinstance(item.get("finding_id"), str):
                hashes.setdefault(str(item["finding_id"]), item_hash)
    return hashes


def _evaluation_time(bundle: Mapping[str, object], now: str | None) -> datetime:
    if now is not None:
        return _timestamp_value(_timestamp(now))
    validity = _mapping(bundle.get("validity"), "validity_missing")
    return _timestamp_value(_timestamp(validity.get("checked_at")))


def _grant_for(policy: Mapping[str, object], principal_id: object) -> Mapping[str, object] | None:
    for grant in _sequence(policy.get("grants"), "authority_policy_invalid"):
        if isinstance(grant, Mapping) and grant.get("principal_id") == principal_id:
            return grant
    return None


def _bundle_evidence_ids(bundle: Mapping[str, object]) -> list[str]:
    ids = {
        "release_candidate",
        "release_pack",
        "publication_governance",
        "release_quality_audit",
        "review",
        "authority_policy",
        "revocation",
    }
    ids.update(str(item.get("risk_acceptance_id")) for item in _sequence(bundle.get("risk_acceptances", []), "evidence_malformed") if isinstance(item, Mapping))
    approval = bundle.get("publication_approval")
    if isinstance(approval, Mapping):
        ids.add(str(approval.get("approval_id")))
    return sorted(item for item in ids if item and item != "None")


def _encode_gate_bundle(bundle: Mapping[str, object]) -> list[str]:
    payload = json.dumps(
        dict(bundle), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    encoded = base64.b64encode(zlib.compress(payload, 9)).decode("ascii")
    return [
        encoded[index : index + PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE]
        for index in range(0, len(encoded), PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE)
    ]


def _decode_gate_bundle(raw: object) -> dict[str, object]:
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) > PUBLISHABILITY_GATE_BUNDLE_MAX_CHUNKS
        or any(not isinstance(chunk, str) or not chunk for chunk in raw)
    ):
        raise PublishabilityContractError("evidence_malformed")
    encoded = "".join(raw)
    if len(encoded) > PUBLISHABILITY_GATE_BUNDLE_MAX_ENCODED_BYTES:
        raise PublishabilityContractError("evidence_malformed")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        decompressor = zlib.decompressobj()
        payload = decompressor.decompress(
            compressed,
            PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES + 1,
        )
        if (
            len(payload) > PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES
            or decompressor.unconsumed_tail
            or not decompressor.eof
        ):
            raise PublishabilityContractError("evidence_malformed")
        payload += decompressor.flush()
        if len(payload) > PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES:
            raise PublishabilityContractError("evidence_malformed")
        return _mapping(json.loads(payload.decode("utf-8")), "evidence_malformed")
    except PublishabilityContractError:
        raise
    except (ValueError, UnicodeError, zlib.error, json.JSONDecodeError) as exc:
        raise PublishabilityContractError("evidence_malformed") from exc


def _subject_field(bundle: Mapping[str, object], field: str) -> object:
    subject = _mapping(bundle.get("subject"), "evidence_malformed")
    if field == "release_pack_hash":
        return subject[field]
    return subject[field]


def _empty_subject() -> dict[str, object]:
    return {
        "subject_id": "unknown_subject",
        "subject_hash": "sha256:" + "0" * 64,
        "release_id": "unknown_release",
        "release_pack_hash": "sha256:" + "0" * 64,
        "release_pack_byte_count": 1,
        "dataset_version": "unknown_dataset",
        "domain_pack_reference": {
            "schema_version": "domain_pack_reference_v1",
            "domain_pack_id": "unknown_pack",
            "pack_version": "unknown",
            "pack_hash": "sha256:" + "0" * 64,
        },
        "plan_id": "unknown_plan",
        "plan_hash": "sha256:" + "0" * 64,
    }


def _empty_scope() -> dict[str, object]:
    return {
        "audience": ["unknown"],
        "purpose": ["unknown"],
        "access": "private",
        "retention": {"max_days": 1},
        "redistribution": "none",
    }


def _validate_release_candidate_report(record: Mapping[str, object]) -> None:
    try:
        from synthesis.qualification import validate_qualification_report_record

        validate_qualification_report_record(record)
    except Exception as exc:
        if isinstance(exc, PublishabilityContractError):
            raise
        raise PublishabilityContractError("release_candidate_missing") from exc


def _normalize_retention(raw: object) -> dict[str, int]:
    if isinstance(raw, int) and not isinstance(raw, bool):
        days = raw
    elif isinstance(raw, Mapping):
        days = raw.get("max_days", raw.get("days"))
    else:
        days = None
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0 or days > 36500:
        raise PublishabilityContractError("scope_invalid")
    return {"max_days": days}


def _timestamp(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise PublishabilityContractError("evidence_malformed")
    value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PublishabilityContractError("evidence_malformed") from exc
    if parsed.tzinfo is None:
        raise PublishabilityContractError("evidence_malformed")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_value(raw: object) -> datetime:
    normalized = _timestamp(raw)
    return datetime.fromisoformat(normalized[:-1] + "+00:00")


def _identifier(raw: object) -> str:
    if not isinstance(raw, str) or not _IDENTIFIER_RE.fullmatch(raw):
        raise PublishabilityContractError("evidence_malformed")
    return raw


def _version(raw: object) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", raw):
        raise PublishabilityContractError("evidence_malformed")
    return raw


def _hash_value(raw: object) -> str:
    if not isinstance(raw, str) or not _HASH_RE.fullmatch(raw):
        raise PublishabilityContractError("evidence_malformed")
    return raw


def _positive_int(raw: object) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        raise PublishabilityContractError("evidence_malformed")
    return raw


def _mapping(raw: object, reason: str) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise PublishabilityContractError(reason)
    return dict(raw)


def _record_field(record: Mapping[str, object], field: str) -> dict[str, object]:
    return _mapping(record.get(field), "evidence_malformed")


def _record_list_field(record: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    return [
        _mapping(item, "evidence_malformed")
        for item in _sequence(record.get(field), "evidence_malformed")
    ]


def _sequence(raw: object, reason: str) -> list[object]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise PublishabilityContractError(reason)
    return list(raw)


def _string_list(raw: object, reason: str) -> list[str]:
    values = _sequence(raw, reason)
    if any(not isinstance(item, str) or not item for item in values):
        raise PublishabilityContractError(reason)
    return [str(item) for item in values]


def _bounded_string_list(raw: object) -> list[str]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise PublishabilityContractError("evidence_malformed")
    values = [item for item in raw]
    if any(not isinstance(item, str) or not item or len(item) > 256 for item in values):
        raise PublishabilityContractError("evidence_malformed")
    return sorted(set(values))


def _bounded_identifier_list(raw: object) -> list[str]:
    values = _string_list(raw, "evidence_malformed")
    normalized = [_identifier(value) for value in values]
    return sorted(set(normalized))


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _contract_reason_code(error: BaseException) -> str:
    candidate = getattr(error, "reason_code", None)
    if isinstance(candidate, str) and candidate in PUBLISHABILITY_REASON_CODES:
        return candidate
    return "evidence_malformed"


__all__ = [
    "AUTHORITY_ATTESTATION_SCHEMA_VERSION",
    "AUTHORITY_POLICY_FILENAME",
    "AUTHORITY_POLICY_SCHEMA_VERSION",
    "GOVERNANCE_CHECKS",
    "HARD_GOVERNANCE_CHECKS",
    "NON_QUALIFYING_EVIDENCE_CLASSES",
    "PUBLICATION_APPROVAL_SCHEMA_VERSION",
    "PUBLICATION_GOVERNANCE_FILENAME",
    "PUBLICATION_GOVERNANCE_SCHEMA_VERSION",
    "PUBLISHABILITY_BUNDLE_FILENAME",
    "PUBLISHABILITY_BUNDLE_SCHEMA_VERSION",
    "PUBLISHABILITY_DECISION_SCHEMA_VERSION",
    "PUBLISHABILITY_GATE_BUNDLE_CHUNK_SIZE",
    "PUBLISHABILITY_GATE_BUNDLE_MAX_CHUNKS",
    "PUBLISHABILITY_GATE_BUNDLE_MAX_DECOMPRESSED_BYTES",
    "PUBLISHABILITY_GATE_BUNDLE_MAX_ENCODED_BYTES",
    "PUBLISHABILITY_GATE_SCHEMA_VERSION",
    "PUBLISHABILITY_REVIEW_ITEM_SCHEMA_VERSION",
    "PUBLISHABILITY_REPORT_FILENAME",
    "PublishabilityContractError",
    "build_authenticated_attestation",
    "build_authority_policy",
    "build_publication_approval",
    "build_publication_approval_record",
    "build_publication_governance",
    "build_publication_governance_report",
    "build_publishability_bundle",
    "build_publishability_evidence_bundle",
    "build_publishability_gate",
    "build_publishability_qualification_evidence",
    "build_publishability_review_item",
    "build_publishability_review_item_record",
    "build_revocation_evidence",
    "build_revocation_record",
    "build_risk_acceptance",
    "build_risk_acceptance_record",
    "compute_publishability_evidence_hash",
    "evaluate_publishability",
    "fingerprint_for_key",
    "is_scope_subset",
    "load_publishability_bundle",
    "normalize_distribution_scope",
    "publishability_subject_from_release_candidate",
    "REVOCATION_EVIDENCE_FILENAME",
    "scope_is_subset",
    "validate_authority_policy_record",
    "validate_authority_attestation_record",
    "validate_publication_governance_record",
    "validate_publication_approval_record",
    "validate_publishability_bundle_record",
    "validate_publishability_decision_record",
    "validate_publishability_gate_record",
    "validate_revocation_evidence_record",
    "validate_risk_acceptance_record",
    "verify_publishability",
    "write_publishability_decision",
    "write_publishability_bundle",
]
