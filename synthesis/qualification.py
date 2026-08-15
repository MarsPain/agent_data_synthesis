"""Pure, cumulative release qualification over exact evidence subjects.

Qualification is deliberately a framework-owned consumer of already-produced
evidence.  This module validates identity and evidence records, derives the
current state from append-only decisions, and never repairs artifacts or
changes any external state.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthesis.domain_pack import (
    DomainAssessment,
    DomainAssessmentEvidence,
    DomainCapabilityReference,
    DomainComponentContractReference,
    DomainEvidenceReference,
    DomainPackContractError,
    DomainPackReference,
    DomainPlan,
    DomainRuntimeContractReference,
    QualificationArtifactReference,
    QualificationSubject,
    canonical_domain_pack_json,
    canonical_domain_pack_hash as _strict_canonical_domain_pack_hash,
)


QUALIFICATION_BINDING_SCHEMA_VERSION = "qualification_binding_v1"
QUALIFICATION_EVIDENCE_SCHEMA_VERSION = "qualification_evidence_v1"
QUALIFICATION_DECISION_SCHEMA_VERSION = "qualification_decision_v1"
QUALIFICATION_REPORT_SCHEMA_VERSION = "qualification_report_v1"
QUALIFICATION_REPORT_FILENAME = "qualification_report.json"

QUALIFICATION_LEVELS = (
    "unqualified",
    "release_candidate",
    "publishable",
    "training_recommended",
)
QUALIFICATION_DECISION_STATUSES = {
    "passed",
    "denied",
    "insufficient_evidence",
}
QUALIFICATION_EVIDENCE_CLASSES = {
    "machine",
    "real_machine",
    "real",
    "conformance_fixture",
    "fixture",
    "synthetic_fixture",
}
NON_QUALIFYING_EVIDENCE_CLASSES = {
    "conformance_fixture",
    "fixture",
    "synthetic_fixture",
}


def canonical_domain_pack_hash(value: object) -> str:
    """Hash qualification evidence, including finite audit metrics safely."""

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
            raise QualificationContractError("evidence_malformed")
        return {"__finite_float__": repr(value)}
    if isinstance(value, Mapping):
        return {key: _normalize_float_values(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalize_float_values(child) for child in value]
    return value

RELEASE_CANDIDATE_MACHINE_GATES = (
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
_MACHINE_GATE_SCHEMA_VERSION = "qualification_machine_gate_v1"
_GATE_IDENTITY_FIELDS = (
    "subject_id",
    "subject_hash",
    "binding_hash",
    "release_pack_hash",
)
_GATE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "release_completeness": ("decision",),
    "release_quality_audit": ("decision",),
    "release_pack_verification": ("verification",),
    # Higher-level evidence remains explicit and content-bound; a bare status
    # cannot advance cumulative qualification state.
    "publishability": (
        "evidence_ids",
        "verification",
        "governance",
        "review",
        "authority",
    ),
    "training_recommendation": (
        "evidence_ids",
        "verification",
        "protocol",
        "experiment",
        "leakage",
    ),
}
_GATE_SCHEMA_VERSIONS: dict[str, frozenset[str]] = {
    **{
        name: frozenset({_MACHINE_GATE_SCHEMA_VERSION})
        for name in RELEASE_CANDIDATE_MACHINE_GATES
    },
    "domain_assessment": frozenset({"domain_assessment_v1"}),
    "release_completeness": frozenset({"qualification_release_completeness_v1"}),
    "release_quality_audit": frozenset({"release_quality_audit_v1"}),
    "release_pack_verification": frozenset(
        {"qualification_release_pack_verification_v1"}
    ),
    "publishability": frozenset({"qualification_publishability_v1"}),
    "training_recommendation": frozenset(
        {"qualification_training_recommendation_v1"}
    ),
}

RELEASE_CANDIDATE_REQUIRED_EVIDENCE = (
    "machine_gates",
    "domain_assessment",
    "release_completeness",
    "release_quality_audit",
    "release_pack_verification",
)
HIGHER_LEVEL_REQUIRED_EVIDENCE = {
    "publishable": "publishability",
    "training_recommended": "training_recommendation",
}

QUALIFICATION_REASON_CODES = frozenset(
    {
        "qualification_passed",
        "qualification_preserved",
        "qualification_level_skip",
        "qualification_subject_mismatch",
        "qualification_binding_malformed",
        "evidence_missing",
        "evidence_malformed",
        "evidence_unknown_version",
        "evidence_identity_mismatch",
        "evidence_hash_mismatch",
        "evidence_stale",
        "evidence_revoked",
        "evidence_expired",
        "evidence_cancelled",
        "evidence_incomplete",
        "evidence_non_passing",
        "evidence_unknown_status",
        "non_qualifying_evidence_class",
        "qualification_dependency_invalidated",
        "foreign_subject_evidence",
        "historical_dataset_status_only",
        "workspace_release_profile_ineligible",
        "workspace_capability_evidence_incomplete",
        "workspace_coverage_evidence_incomplete",
        "workspace_mutation_admission_incomplete",
        "workspace_plan_evidence_missing",
    }
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")

_PASS_STATUSES = {"passed"}
_AUDIT_PASS_STATUSES = {"clear", "watch"}
_DOMAIN_ASSESSMENT_PASS_STATUSES = {"established"}
_DENIED_STATUSES = {
    "failed",
    "blocked",
    "denied",
    "rejected",
    "ineligible",
    "unsupported",
    "non_passing",
}
_INSUFFICIENT_STATUSES = {
    "insufficient_evidence",
    "unknown",
    "stale",
    "revoked",
    "expired",
    "cancelled",
    "incomplete",
    "malformed",
}
_SUPPORTED_SCHEMA_VERSIONS = frozenset(
    {
        "qualification_binding_v1",
        "qualification_decision_v1",
        "qualification_evidence_v1",
        "qualification_report_v1",
        "domain_assessment_v1",
        "domain_evidence_reference_v1",
        "dataset_manifest_v1",
        "dataset_manifest_v2",
        "dataset_release_pack_v1",
        "dataset_release_pack_v2",
        "dataset_release_report_v1",
        "dataset_sample_v1",
        "dataset_sample_v2",
        "evaluation_report_v1",
        "profile_decision_report_v1",
        "quality_report_v1",
        "coverage_evidence_v1",
        "coverage_plan_v1",
        "coverage_quality_summary_v1",
        "coverage_manifest_binding_v1",
        "release_quality_audit_v1",
        "release_samples_v1",
        "release_rejections_v1",
        "workspace_evidence_binding_v1",
        "mutation_admission_report_v1",
        "qualification_machine_gate_v1",
        "qualification_release_completeness_v1",
        "qualification_release_pack_verification_v1",
        "qualification_publishability_v1",
        "qualification_training_recommendation_v1",
    }
)


class QualificationContractError(ValueError):
    """A bounded qualification-contract failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class QualificationBinding:
    """Exact identity graph shared by every cumulative qualification level."""

    artifact_subject: QualificationSubject
    release_pack_hash: str
    release_pack_byte_count: int
    domain_pack_reference: DomainPackReference
    plan_id: str
    plan_hash: str
    runtime_contract: DomainRuntimeContractReference
    capability_references: tuple[DomainCapabilityReference, ...]
    component_contracts: tuple[DomainComponentContractReference, ...]
    profile: Mapping[str, object]
    evidence_graph: tuple[Mapping[str, object], ...]
    binding_id: str
    binding_hash: str
    schema_version: str = QUALIFICATION_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != QUALIFICATION_BINDING_SCHEMA_VERSION:
            raise QualificationContractError("qualification_binding_malformed")
        if not isinstance(self.artifact_subject, QualificationSubject):
            raise QualificationContractError("qualification_binding_malformed")
        if self.artifact_subject.domain_pack_reference != self.domain_pack_reference:
            raise QualificationContractError("qualification_subject_mismatch")
        _require_hash(self.release_pack_hash, "release_pack_hash")
        if (
            not isinstance(self.release_pack_byte_count, int)
            or isinstance(self.release_pack_byte_count, bool)
            or self.release_pack_byte_count <= 0
        ):
            raise QualificationContractError("qualification_binding_malformed")
        _require_identifier(self.plan_id, "plan_id")
        _require_hash(self.plan_hash, "plan_hash")
        if not isinstance(self.runtime_contract, DomainRuntimeContractReference):
            raise QualificationContractError("qualification_binding_malformed")
        if (
            not isinstance(self.capability_references, tuple)
            or not isinstance(self.component_contracts, tuple)
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.capability_references
            )
            or any(
                not isinstance(item, DomainComponentContractReference)
                for item in self.component_contracts
            )
            or len(set(self.capability_references)) != len(self.capability_references)
            or len(set(self.component_contracts)) != len(self.component_contracts)
        ):
            raise QualificationContractError("qualification_binding_malformed")
        if not isinstance(self.profile, Mapping):
            raise QualificationContractError("qualification_binding_malformed")
        if not isinstance(self.evidence_graph, tuple) or not self.evidence_graph:
            raise QualificationContractError("qualification_binding_malformed")
        if any(not isinstance(node, Mapping) for node in self.evidence_graph):
            raise QualificationContractError("qualification_binding_malformed")
        artifact_ids = [node.get("artifact_id") for node in self.evidence_graph]
        if any(not isinstance(artifact_id, str) for artifact_id in artifact_ids):
            raise QualificationContractError("qualification_binding_malformed")
        if len(set(artifact_ids)) != len(artifact_ids):
            raise QualificationContractError("qualification_binding_malformed")
        for node in self.evidence_graph:
            _validate_evidence_graph_node(node)
        _require_identifier(self.binding_id, "binding_id")
        _require_hash(self.binding_hash, "binding_hash")
        expected_hash = canonical_domain_pack_hash(self._content_record())
        if self.binding_hash != expected_hash:
            raise QualificationContractError("qualification_binding_malformed")
        expected_id = "qualification_binding_" + expected_hash.removeprefix(
            "sha256:"
        )[:16]
        if self.binding_id != expected_id:
            raise QualificationContractError("qualification_binding_malformed")
        graph_pack_hashes = {
            str(node["content_hash"])
            for node in self.evidence_graph
            if node.get("artifact_id") == "release_pack"
        }
        if graph_pack_hashes != {self.release_pack_hash}:
            raise QualificationContractError("qualification_binding_malformed")
        subject_pack_references = tuple(
            reference
            for reference in self.artifact_subject.artifact_references
            if reference.artifact_id == "release_pack"
        )
        if len(subject_pack_references) != 1:
            raise QualificationContractError("qualification_binding_malformed")
        if (
            subject_pack_references[0].content_hash != self.release_pack_hash
            or subject_pack_references[0].byte_count != self.release_pack_byte_count
        ):
            raise QualificationContractError("qualification_binding_malformed")

    @classmethod
    def from_plan(
        cls,
        plan: DomainPlan,
        *,
        release_pack_hash: str,
        release_pack_byte_count: int,
        profile: Mapping[str, object],
        evidence_graph: Sequence[Mapping[str, object]] | None = None,
    ) -> "QualificationBinding":
        if not isinstance(plan, DomainPlan):
            raise QualificationContractError("qualification_binding_malformed")
        _require_hash(release_pack_hash, "release_pack_hash")
        if (
            not isinstance(release_pack_byte_count, int)
            or isinstance(release_pack_byte_count, bool)
            or release_pack_byte_count <= 0
        ):
            raise QualificationContractError("qualification_binding_malformed")
        if evidence_graph is not None and any(
            not isinstance(node, Mapping) for node in evidence_graph
        ):
            raise QualificationContractError("qualification_binding_malformed")
        graph = tuple(
            dict(node)
            for node in (
                evidence_graph
                or (
                    {
                        "artifact_id": "release_pack",
                        "artifact_schema_version": "dataset_release_pack_v1",
                        "content_hash": release_pack_hash,
                        "byte_count": release_pack_byte_count,
                        "status": "active",
                    },
                )
            )
        )
        release_pack_nodes = tuple(
            node for node in graph if node.get("artifact_id") == "release_pack"
        )
        if not release_pack_nodes:
            graph = (
                *graph,
                {
                    "artifact_id": "release_pack",
                    "artifact_schema_version": "dataset_release_pack_v2",
                    "content_hash": release_pack_hash,
                    "byte_count": release_pack_byte_count,
                    "status": "active",
                },
            )
        elif any(
            node.get("content_hash") != release_pack_hash
            or node.get("byte_count") != release_pack_byte_count
            for node in release_pack_nodes
        ):
            raise QualificationContractError("qualification_binding_malformed")
        subject_refs = _artifact_references_for_subject(graph)
        if not any(item.artifact_id == "release_pack" for item in subject_refs):
            subject_refs = (
                *subject_refs,
                QualificationArtifactReference(
                    artifact_id="release_pack",
                    artifact_schema_version="dataset_release_pack_v1",
                    content_hash=release_pack_hash,
                    byte_count=release_pack_byte_count,
                ),
            )
        subject = QualificationSubject.create(
            domain_pack_reference=plan.domain_pack_reference,
            artifact_references=tuple(subject_refs),
        )
        content = _binding_content_record(
            artifact_subject=subject,
            release_pack_hash=release_pack_hash,
            release_pack_byte_count=release_pack_byte_count,
            domain_pack_reference=plan.domain_pack_reference,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            runtime_contract=plan.runtime_contract,
            capability_references=tuple(plan.capability_references),
            component_contracts=tuple(plan.component_contracts),
            profile=profile,
            evidence_graph=graph,
        )
        binding_hash = canonical_domain_pack_hash(content)
        return cls(
            artifact_subject=subject,
            release_pack_hash=release_pack_hash,
            release_pack_byte_count=release_pack_byte_count,
            domain_pack_reference=plan.domain_pack_reference,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            runtime_contract=plan.runtime_contract,
            capability_references=tuple(plan.capability_references),
            component_contracts=tuple(plan.component_contracts),
            profile=dict(profile),
            evidence_graph=graph,
            binding_id="qualification_binding_" + binding_hash.removeprefix(
                "sha256:"
            )[:16],
            binding_hash=binding_hash,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "QualificationBinding":
        try:
            canonical_domain_pack_json(record)
            artifact_subject = QualificationSubject.from_record(
                _mapping(record.get("artifact_subject"), "artifact_subject")
            )
            domain_pack_reference = DomainPackReference.from_record(
                _mapping(record.get("domain_pack_reference"), "domain_pack_reference")
            )
            runtime_contract = DomainRuntimeContractReference.from_record(
                _mapping(record.get("runtime_contract"), "runtime_contract")
            )
            capability_references = tuple(
                DomainCapabilityReference.from_record(item)
                for item in _records(record.get("capability_references"))
            )
            component_contracts = tuple(
                DomainComponentContractReference.from_record(item)
                for item in _records(record.get("component_contracts"))
            )
            graph = tuple(
                dict(item) for item in _records(record.get("evidence_graph"))
            )
            return cls(
                schema_version=_text(record.get("schema_version")),
                artifact_subject=artifact_subject,
                release_pack_hash=_text(record.get("release_pack_hash")),
                release_pack_byte_count=_int(record.get("release_pack_byte_count")),
                domain_pack_reference=domain_pack_reference,
                plan_id=_text(record.get("plan_id")),
                plan_hash=_text(record.get("plan_hash")),
                runtime_contract=runtime_contract,
                capability_references=capability_references,
                component_contracts=component_contracts,
                profile=_mapping(record.get("profile"), "profile"),
                evidence_graph=graph,
                binding_id=_text(record.get("binding_id")),
                binding_hash=_text(record.get("binding_hash")),
            )
        except (DomainPackContractError, QualificationContractError, TypeError, ValueError):
            raise QualificationContractError("qualification_binding_malformed") from None

    def _content_record(self) -> dict[str, object]:
        return _binding_content_record(
            artifact_subject=self.artifact_subject,
            release_pack_hash=self.release_pack_hash,
            release_pack_byte_count=self.release_pack_byte_count,
            domain_pack_reference=self.domain_pack_reference,
            plan_id=self.plan_id,
            plan_hash=self.plan_hash,
            runtime_contract=self.runtime_contract,
            capability_references=self.capability_references,
            component_contracts=self.component_contracts,
            profile=self.profile,
            evidence_graph=self.evidence_graph,
        )

    def to_record(self) -> dict[str, object]:
        return {
            **self._content_record(),
            "binding_id": self.binding_id,
            "binding_hash": self.binding_hash,
        }

    @property
    def subject_id(self) -> str:
        return self.artifact_subject.subject_id

    @property
    def subject_hash(self) -> str:
        return self.artifact_subject.subject_hash


def build_release_candidate_evidence(
    *,
    binding: QualificationBinding,
    machine_gates: Mapping[str, object],
    domain_assessment: Mapping[str, object] | DomainAssessment,
    release_completeness: Mapping[str, object],
    release_quality_audit: Mapping[str, object],
    release_pack_verification: Mapping[str, object],
    evidence_class: str = "real_machine",
) -> dict[str, object]:
    """Assemble the exact evidence boundary consumed by the pure evaluator."""

    _require_binding(binding)
    if not isinstance(machine_gates, Mapping):
        raise QualificationContractError("evidence_malformed")
    if (
        not isinstance(evidence_class, str)
        or evidence_class not in QUALIFICATION_EVIDENCE_CLASSES
    ):
        raise QualificationContractError("evidence_malformed")
    assessment = _record_or_to_record(domain_assessment)
    machine_gate_records = {
        str(key): _bind_gate_identity(binding, _record_or_to_record(value))
        for key, value in machine_gates.items()
    }
    return {
        "schema_version": QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
        "qualification": "release_candidate",
        "evidence_class": evidence_class,
        "binding": binding.to_record(),
        "gates": {
            "machine_gates": machine_gate_records,
            "domain_assessment": _bind_gate_identity(binding, assessment),
            "release_completeness": _bind_gate_identity(
                binding,
                _record_or_to_record(release_completeness),
            ),
            "release_quality_audit": _bind_gate_identity(
                binding,
                _record_or_to_record(release_quality_audit),
            ),
            "release_pack_verification": _bind_gate_identity(
                binding,
                _record_or_to_record(release_pack_verification),
            ),
        },
        "evidence_graph": [dict(node) for node in binding.evidence_graph],
    }


def evaluate_cumulative_qualification(
    *,
    subject: QualificationBinding | Mapping[str, object],
    evidence: Mapping[str, object] | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    attempted_qualification: str | None = None,
    invalidated_evidence: Iterable[str] = (),
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
) -> dict[str, object]:
    """Derive one current cumulative state without mutating prior decisions."""

    if publishability_trusted_policy_hashes is not None:
        try:
            publishability_trusted_policy_hashes = tuple(
                publishability_trusted_policy_hashes
            )
        except TypeError:
            publishability_trusted_policy_hashes = ()
    if publishability_trusted_bundle_content_hashes is not None:
        try:
            publishability_trusted_bundle_content_hashes = tuple(
                publishability_trusted_bundle_content_hashes
            )
        except TypeError:
            publishability_trusted_bundle_content_hashes = ()
    if publishability_trusted_release_pack_verification_hashes is not None:
        try:
            publishability_trusted_release_pack_verification_hashes = tuple(
                publishability_trusted_release_pack_verification_hashes
            )
        except TypeError:
            publishability_trusted_release_pack_verification_hashes = ()
    binding = _coerce_binding(subject)
    evidence_malformed = evidence is not None and not isinstance(evidence, Mapping)
    if evidence is None:
        evidence_record: dict[str, object] = {}
    elif isinstance(evidence, Mapping):
        evidence_record = dict(evidence)
    else:
        evidence_record = {"evidence_malformed": True}
    historical, history_error = _normalize_history(
        history,
        binding,
        publishability_trusted_keys=publishability_trusted_keys,
        publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
        publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
        publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
        publishability_now=publishability_now,
    )
    if history_error is not None:
        history_requested = attempted_qualification
        if history_requested is None and isinstance(
            evidence_record.get("qualification"), str
        ):
            history_requested = str(evidence_record["qualification"])
        return _report(
            binding=binding,
            historical_decisions=[],
            attempted_qualification=history_requested,
            status="insufficient_evidence",
            effective_qualification="unqualified",
            reason_codes=("evidence_malformed",),
            reasons=(history_error,),
            invalidated=set(),
            append_decision=True,
        )
    invalidated = {
        str(item)
        for item in invalidated_evidence
        if isinstance(item, str) and item
    }
    for key in ("invalidated_evidence", "revoked_evidence", "stale_evidence"):
        raw = evidence_record.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            invalidated.update(str(item) for item in raw if isinstance(item, str))
    graph_invalidated, graph_reason_codes = _binding_invalidations(binding)
    invalidated.update(graph_invalidated)
    bound_evidence_ids = {
        str(node.get("artifact_id"))
        for node in binding.evidence_graph
        if isinstance(node.get("artifact_id"), str)
    }
    bound_evidence_ids.add(binding.binding_hash)
    explicitly_invalidated = invalidated.intersection(bound_evidence_ids)

    current, dependency_invalidated = _effective_state(
        binding=binding,
        history=historical,
        invalidated=invalidated,
    )
    dependency_invalidated = dependency_invalidated or bool(
        graph_invalidated or explicitly_invalidated
    )
    current_index = QUALIFICATION_LEVELS.index(current)
    if evidence_malformed:
        return _report(
            binding=binding,
            historical_decisions=historical,
            attempted_qualification=None,
            status="insufficient_evidence",
            effective_qualification=current,
            reason_codes=("evidence_malformed",),
            reasons=("qualification evidence must be an object",),
            invalidated=invalidated,
        )
    requested: object = (
        attempted_qualification
        if attempted_qualification is not None
        else evidence_record.get("qualification")
    )
    if requested is None:
        decision_status = (
            "insufficient_evidence" if dependency_invalidated else "passed"
        )
        reason_codes = (
            ("qualification_dependency_invalidated",)
            if dependency_invalidated
            else ("qualification_preserved",)
        )
        reasons = (
            ("a lower-level evidence dependency is stale, revoked, or mismatched",)
            if dependency_invalidated
            else ("no new qualification transition was requested",)
        )
        return _report(
            binding=binding,
            historical_decisions=historical,
            attempted_qualification=None,
            status=decision_status,
            effective_qualification=current,
            reason_codes=reason_codes,
            reasons=reasons,
            invalidated=invalidated,
        )

    if not isinstance(requested, str) or requested not in QUALIFICATION_LEVELS[1:]:
        return _report(
            binding=binding,
            historical_decisions=historical,
            attempted_qualification=str(requested),
            status="denied",
            effective_qualification=current,
            reason_codes=("qualification_level_skip",),
            reasons=("requested qualification level is unsupported",),
            invalidated=invalidated,
            append_decision=True,
        )

    requested_index = QUALIFICATION_LEVELS.index(requested)
    if graph_invalidated or explicitly_invalidated:
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="insufficient_evidence",
            reason_codes=tuple(
                graph_reason_codes or ("qualification_dependency_invalidated",)
            ),
            reasons=(
                "one or more bound evidence artifacts are stale, revoked, expired, cancelled, or incomplete",
            ),
            invalidated=invalidated,
        )

    if requested_index > current_index + 1:
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="denied",
            reason_codes=("qualification_level_skip",),
            reasons=(
                "cumulative qualifications must advance one level at a time",
            ),
            invalidated=invalidated,
        )

    evidence_class = evidence_record.get("evidence_class", "machine")
    if (
        not isinstance(evidence_class, str)
        or evidence_class not in QUALIFICATION_EVIDENCE_CLASSES
    ):
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="insufficient_evidence",
            reason_codes=("evidence_malformed",),
            reasons=("evidence class is unsupported",),
            invalidated=invalidated,
        )
    if evidence_class in NON_QUALIFYING_EVIDENCE_CLASSES:
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="denied",
            reason_codes=("non_qualifying_evidence_class",),
            reasons=(
                "conformance or fixture evidence cannot establish an effective qualification",
            ),
            invalidated=invalidated,
        )

    gates = _mapping_or_empty(evidence_record.get("gates"))
    required: list[str] = list(RELEASE_CANDIDATE_REQUIRED_EVIDENCE)
    extra_gate = HIGHER_LEVEL_REQUIRED_EVIDENCE.get(requested)
    if extra_gate is not None:
        required.append(extra_gate)
    gate_status, gate_reason_codes, gate_reasons = _evaluate_required_gates(
        binding=binding,
        gates=gates,
        required=tuple(required),
        publishability_trusted_keys=publishability_trusted_keys,
        publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
        publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
        publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
        publishability_now=publishability_now,
        verify_publishability_authority=True,
    )
    if gate_status != "passed":
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status=gate_status,
            reason_codes=tuple(gate_reason_codes),
            reasons=tuple(gate_reasons),
            invalidated=invalidated,
        )

    evidence_schema = evidence_record.get("schema_version")
    if evidence_schema != QUALIFICATION_EVIDENCE_SCHEMA_VERSION:
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="insufficient_evidence",
            reason_codes=(
                "evidence_missing"
                if evidence_schema is None
                else "evidence_unknown_version",
            ),
            reasons=("qualification evidence schema is missing or unsupported",),
            invalidated=invalidated,
        )
    if evidence_record.get("qualification") != requested:
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="insufficient_evidence",
            reason_codes=("evidence_identity_mismatch",),
            reasons=("qualification evidence level does not match the requested transition",),
            invalidated=invalidated,
        )

    if _evidence_subject_mismatch(evidence_record, binding):
        return _failed_transition_report(
            binding=binding,
            historical_decisions=historical,
            requested=requested,
            current=current,
            status="insufficient_evidence",
            reason_codes=("qualification_subject_mismatch",),
            reasons=(
                "qualification evidence is missing or belongs to another exact subject",
            ),
            invalidated=invalidated,
        )

    new_effective = (
        requested if requested_index > current_index else current
    )
    entry = _decision_entry(
        binding=binding,
        attempted_qualification=requested,
        status="passed",
        effective_qualification=new_effective,
        reason_codes=("qualification_passed",),
        reasons=(
            "all applicable evidence gates passed for the exact artifact subject",
        ),
        evidence=evidence_record,
    )
    return _report(
        binding=binding,
        historical_decisions=historical,
        attempted_qualification=requested,
        status="passed",
        effective_qualification=new_effective,
        reason_codes=("qualification_passed",),
        reasons=(
            "all applicable evidence gates passed for the exact artifact subject",
        ),
        invalidated=invalidated,
        appended_entry=entry,
    )


def evaluate_qualification(**kwargs: object) -> dict[str, object]:
    """Compatibility alias for callers that use the shorter evaluator name."""

    return evaluate_cumulative_qualification(**kwargs)  # type: ignore[arg-type]


def evaluate_release_candidate(
    *,
    subject: QualificationBinding | Mapping[str, object],
    evidence: Mapping[str, object],
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Iterable[str] = (),
) -> dict[str, object]:
    """Evaluate only the Release Candidate transition."""

    return evaluate_cumulative_qualification(
        subject=subject,
        evidence={**dict(evidence), "qualification": "release_candidate"},
        history=history,
        invalidated_evidence=invalidated_evidence,
    )


def write_qualification_report(
    output_path: Path,
    report: Mapping[str, object],
) -> Path:
    """Write a validated standalone qualification report."""

    validate_qualification_report_record(report)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def validate_qualification_report_record(record: Mapping[str, object]) -> None:
    """Validate the public report and recompute its effective state."""

    if not isinstance(record, Mapping):
        raise QualificationContractError("qualification_binding_malformed")
    expected_report_keys = {
        "schema_version",
        "subject",
        "qualification_binding",
        "attempted_qualification",
        "status",
        "effective_qualification",
        "decision",
        "historical_decisions",
        "invalidated_evidence",
        "claims",
    }
    if set(record) != expected_report_keys:
        raise QualificationContractError("qualification_binding_malformed")
    if record.get("schema_version") != QUALIFICATION_REPORT_SCHEMA_VERSION:
        raise QualificationContractError("evidence_unknown_version")
    binding = QualificationBinding.from_record(
        _mapping(record.get("qualification_binding"), "qualification_binding")
    )
    if record.get("subject") != binding.artifact_subject.to_record():
        raise QualificationContractError("qualification_subject_mismatch")
    effective = record.get("effective_qualification")
    if effective not in QUALIFICATION_LEVELS:
        raise QualificationContractError("qualification_binding_malformed")
    status = record.get("status")
    if status not in QUALIFICATION_DECISION_STATUSES:
        raise QualificationContractError("qualification_binding_malformed")
    decision = _mapping(record.get("decision"), "decision")
    if set(decision) != {"status", "reason_codes", "reasons"}:
        raise QualificationContractError("qualification_binding_malformed")
    if decision.get("status") != status:
        raise QualificationContractError("qualification_binding_malformed")
    reason_codes = decision.get("reason_codes")
    reasons = decision.get("reasons")
    if (
        not isinstance(reason_codes, list)
        or not reason_codes
        or any(code not in QUALIFICATION_REASON_CODES for code in reason_codes)
        or not isinstance(reasons, list)
        or not reasons
        or any(not isinstance(reason, str) or not reason for reason in reasons)
    ):
        raise QualificationContractError("qualification_binding_malformed")
    historical = record.get("historical_decisions")
    if not isinstance(historical, list):
        raise QualificationContractError("qualification_binding_malformed")
    for item in historical:
        if not isinstance(item, Mapping):
            raise QualificationContractError("qualification_binding_malformed")
        _validate_decision_entry(item, None)
    attempted = record.get("attempted_qualification")
    if attempted is not None and (
        not isinstance(attempted, str) or not attempted
    ):
        raise QualificationContractError("qualification_binding_malformed")
    if status == "passed" and attempted is not None:
        if attempted not in QUALIFICATION_LEVELS[1:]:
            raise QualificationContractError("qualification_binding_malformed")
        if QUALIFICATION_LEVELS.index(effective) < QUALIFICATION_LEVELS.index(
            attempted
        ):
            raise QualificationContractError("qualification_binding_malformed")
    _validate_history_sequence(historical, binding)
    invalidated = record.get("invalidated_evidence")
    if not isinstance(invalidated, list) or any(
        not isinstance(item, str) or not item for item in invalidated
    ) or invalidated != sorted(set(invalidated)):
        raise QualificationContractError("qualification_binding_malformed")
    effective_from_history, _ = _effective_state(
        binding=binding,
        history=historical,
        invalidated=set(invalidated),
    )
    if effective_from_history != effective:
        raise QualificationContractError("qualification_binding_malformed")
    if attempted is not None:
        if not historical:
            raise QualificationContractError("qualification_binding_malformed")
        latest = historical[-1]
        if (
            not _history_subject_matches(latest, binding)
            or latest.get("attempted_qualification") != attempted
            or latest.get("status") != status
            or latest.get("effective_qualification") != effective
            or latest.get("reason_codes") != reason_codes
            or latest.get("reasons") != reasons
        ):
            raise QualificationContractError("qualification_binding_malformed")
    elif status == "passed" and reason_codes != ["qualification_preserved"]:
        raise QualificationContractError("qualification_binding_malformed")
    claims = _mapping(record.get("claims"), "claims")
    expected_claims = {
        "release_candidate": effective in QUALIFICATION_LEVELS[1:],
        "eligible_for_human_publication_review": effective in QUALIFICATION_LEVELS[1:],
        "publishable": effective in {"publishable", "training_recommended"},
        "training_recommended": effective == "training_recommended",
    }
    if set(claims) != set(expected_claims) or any(
        not isinstance(claims.get(key), bool)
        or claims.get(key) != value
        for key, value in expected_claims.items()
    ):
        raise QualificationContractError("qualification_binding_malformed")


def _validate_history_sequence(
    historical: Sequence[Mapping[str, object]],
    binding: QualificationBinding,
) -> None:
    current = "unqualified"
    for entry in historical:
        if not _history_subject_matches(entry, binding) or entry.get("status") != "passed":
            continue
        attempted = entry.get("attempted_qualification")
        effective = entry.get("effective_qualification")
        if attempted not in QUALIFICATION_LEVELS[1:] or effective not in QUALIFICATION_LEVELS:
            raise QualificationContractError("qualification_binding_malformed")
        attempted_index = QUALIFICATION_LEVELS.index(attempted)
        current_index = QUALIFICATION_LEVELS.index(current)
        if attempted_index > current_index + 1:
            raise QualificationContractError("qualification_level_skip")
        if QUALIFICATION_LEVELS.index(effective) < attempted_index:
            raise QualificationContractError("qualification_binding_malformed")
        if attempted_index == current_index + 1:
            current = attempted


def _normalize_history(
    history: Sequence[Mapping[str, object]] | Mapping[str, object],
    binding: QualificationBinding,
    *,
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    if isinstance(history, Mapping):
        raw_history = history.get("historical_decisions")
        if not isinstance(raw_history, Sequence) or isinstance(
            raw_history, (str, bytes)
        ):
            return [], "historical decisions are missing or not a sequence"
    elif isinstance(history, Sequence) and not isinstance(history, (str, bytes)):
        raw_history = history
    else:
        return [], "historical decisions are not a sequence"
    normalized: list[dict[str, object]] = []
    for item in raw_history:
        if not isinstance(item, Mapping):
            return [], "historical decision is not an object"
        try:
            _validate_decision_entry(
                item,
                None,
                publishability_trusted_keys=publishability_trusted_keys,
                publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
                publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
                publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
                publishability_now=publishability_now,
                verify_publishability_authority=True,
            )
        except QualificationContractError as exc:
            return [], f"historical decision is invalid: {exc.reason_code}"
        normalized.append(dict(item))
    return normalized, None


def _validate_decision_entry(
    entry: Mapping[str, object],
    binding: QualificationBinding | None,
    *,
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
    verify_publishability_authority: bool = False,
) -> None:
    expected_keys = {
        "schema_version",
        "subject_id",
        "subject_hash",
        "binding_hash",
        "attempted_qualification",
        "status",
        "effective_qualification",
        "reason_codes",
        "reasons",
        "evidence_ids",
        "evidence_class",
        "evidence",
        "decision_id",
    }
    if set(entry) != expected_keys:
        raise QualificationContractError("qualification_binding_malformed")
    if entry.get("schema_version") != QUALIFICATION_DECISION_SCHEMA_VERSION:
        raise QualificationContractError("evidence_unknown_version")
    if (
        not isinstance(entry.get("subject_id"), str)
        or not isinstance(entry.get("subject_hash"), str)
        or not isinstance(entry.get("binding_hash"), str)
    ):
        raise QualificationContractError("qualification_binding_malformed")
    try:
        _require_identifier(str(entry["subject_id"]), "subject_id")
        _require_hash(str(entry["subject_hash"]), "subject_hash")
        _require_hash(str(entry["binding_hash"]), "binding_hash")
    except QualificationContractError:
        raise
    if binding is not None and (
        entry.get("subject_id") != binding.subject_id
        or entry.get("subject_hash") != binding.subject_hash
        or entry.get("binding_hash") != binding.binding_hash
    ):
        raise QualificationContractError("qualification_subject_mismatch")
    attempted = entry.get("attempted_qualification")
    if not isinstance(attempted, str) or not attempted:
        raise QualificationContractError("qualification_binding_malformed")
    status = entry.get("status")
    if status not in QUALIFICATION_DECISION_STATUSES:
        raise QualificationContractError("qualification_binding_malformed")
    effective = entry.get("effective_qualification")
    if effective not in QUALIFICATION_LEVELS:
        raise QualificationContractError("qualification_binding_malformed")
    reason_codes = entry.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes or any(
        code not in QUALIFICATION_REASON_CODES for code in reason_codes
    ):
        raise QualificationContractError("qualification_binding_malformed")
    reasons = entry.get("reasons")
    if not isinstance(reasons, list) or not reasons or any(
        not isinstance(reason, str) or not reason for reason in reasons
    ):
        raise QualificationContractError("qualification_binding_malformed")
    evidence_ids = entry.get("evidence_ids")
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) or not item for item in evidence_ids
    ) or evidence_ids != sorted(set(evidence_ids)):
        raise QualificationContractError("qualification_binding_malformed")
    evidence_class = entry.get("evidence_class")
    if evidence_class not in QUALIFICATION_EVIDENCE_CLASSES:
        raise QualificationContractError("qualification_binding_malformed")
    evidence = entry.get("evidence")
    if not isinstance(evidence, Mapping):
        raise QualificationContractError("qualification_binding_malformed")
    content = {key: entry[key] for key in expected_keys if key != "decision_id"}
    expected_hash = canonical_domain_pack_hash(content)
    expected_id = "qualification_decision_" + expected_hash.removeprefix(
        "sha256:"
    )[:16]
    if entry.get("decision_id") != expected_id:
        raise QualificationContractError("qualification_binding_malformed")
    if status == "passed":
        if attempted not in QUALIFICATION_LEVELS[1:]:
            raise QualificationContractError("qualification_binding_malformed")
        if QUALIFICATION_LEVELS.index(effective) < QUALIFICATION_LEVELS.index(attempted):
            raise QualificationContractError("qualification_binding_malformed")
        if evidence_class in NON_QUALIFYING_EVIDENCE_CLASSES:
            raise QualificationContractError("non_qualifying_evidence_class")
        if evidence.get("schema_version") != QUALIFICATION_EVIDENCE_SCHEMA_VERSION:
            raise QualificationContractError("evidence_unknown_version")
        if evidence.get("qualification") != attempted:
            raise QualificationContractError("evidence_identity_mismatch")
        raw_evidence_binding = evidence.get("binding")
        if not isinstance(raw_evidence_binding, Mapping):
            raise QualificationContractError("qualification_subject_mismatch")
        try:
            evidence_binding = QualificationBinding.from_record(raw_evidence_binding)
        except QualificationContractError:
            raise QualificationContractError("qualification_subject_mismatch") from None
        if (
            entry.get("subject_id") != evidence_binding.subject_id
            or entry.get("subject_hash") != evidence_binding.subject_hash
            or entry.get("binding_hash") != evidence_binding.binding_hash
            or _evidence_subject_mismatch(evidence, evidence_binding)
        ):
            raise QualificationContractError("qualification_subject_mismatch")
        gates = _mapping_or_empty(evidence.get("gates"))
        required = list(RELEASE_CANDIDATE_REQUIRED_EVIDENCE)
        extra_gate = HIGHER_LEVEL_REQUIRED_EVIDENCE.get(attempted)
        if extra_gate is not None:
            required.append(extra_gate)
        gate_status, _, _ = _evaluate_required_gates(
            binding=evidence_binding,
            gates=gates,
            required=tuple(required),
            publishability_trusted_keys=publishability_trusted_keys,
            publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
            publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
            publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
            publishability_now=publishability_now,
            verify_publishability_authority=verify_publishability_authority,
        )
        if gate_status != "passed":
            raise QualificationContractError("evidence_non_passing")
    if evidence_class != evidence.get("evidence_class", "machine"):
        raise QualificationContractError("qualification_binding_malformed")
    if status == "passed":
        if evidence_ids != _decision_evidence_ids(evidence_binding, evidence):
            raise QualificationContractError("qualification_binding_malformed")
    elif not evidence_ids:
        raise QualificationContractError("qualification_binding_malformed")


def build_workspace_release_candidate_evidence(
    *,
    binding: QualificationBinding,
    machine_gates: Mapping[str, object],
    domain_assessment: Mapping[str, object] | DomainAssessment,
    release_completeness: Mapping[str, object],
    release_quality_audit: Mapping[str, object],
    release_pack_verification: Mapping[str, object],
    evidence_class: str = "real_machine",
) -> dict[str, object]:
    """Named Workspace-facing constructor for the shared evidence boundary."""

    return build_release_candidate_evidence(
        binding=binding,
        machine_gates=machine_gates,
        domain_assessment=domain_assessment,
        release_completeness=release_completeness,
        release_quality_audit=release_quality_audit,
        release_pack_verification=release_pack_verification,
        evidence_class=evidence_class,
    )


def qualify_workspace_release_candidate(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    release_quality_audit_path: Path | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Iterable[str] = (),
) -> dict[str, object]:
    """Build exact Workspace machine evidence from files and evaluate it.

    The adapter is intentionally strict: it accepts only the coverage-driven
    LLM path with enforced mutation admission and complete canonical Workspace
    bindings.  Older fixture releases remain readable but return bounded
    insufficient evidence.
    """

    try:
        inputs = _load_workspace_release_inputs(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            release_quality_audit_path=release_quality_audit_path,
        )
    except _WorkspaceQualificationInsufficiency as exc:
        return _workspace_insufficient_report(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            reason_code=exc.reason_code,
            reason=exc.reason,
        )
    binding = inputs.get("binding")
    evidence = inputs.get("evidence")
    if not isinstance(binding, QualificationBinding) or not isinstance(evidence, Mapping):
        return _workspace_insufficient_report(
            manifest_path=manifest_path,
            release_pack_path=release_pack_path,
            reason_code="evidence_malformed",
            reason="Workspace release adapter produced malformed qualification inputs",
        )
    return evaluate_cumulative_qualification(
        subject=binding,
        evidence=evidence,
        history=history,
        invalidated_evidence=invalidated_evidence,
    )


evaluate_workspace_release_candidate = qualify_workspace_release_candidate


def write_workspace_release_candidate_qualification(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    output_path: Path,
    release_quality_audit_path: Path | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Iterable[str] = (),
) -> Path:
    report = qualify_workspace_release_candidate(
        manifest_path=manifest_path,
        release_pack_path=release_pack_path,
        release_quality_audit_path=release_quality_audit_path,
        history=history,
        invalidated_evidence=invalidated_evidence,
    )
    return write_qualification_report(output_path, report)


def write_release_candidate_qualification(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    output_path: Path,
    release_quality_audit_path: Path | None = None,
    history: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    invalidated_evidence: Iterable[str] = (),
) -> Path:
    """Write the current release-candidate decision for the local adapter."""

    return write_workspace_release_candidate_qualification(
        manifest_path=manifest_path,
        release_pack_path=release_pack_path,
        output_path=output_path,
        release_quality_audit_path=release_quality_audit_path,
        history=history,
        invalidated_evidence=invalidated_evidence,
    )


def _evaluate_required_gates(
    *,
    binding: QualificationBinding,
    gates: Mapping[str, object],
    required: tuple[str, ...],
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
    verify_publishability_authority: bool = False,
) -> tuple[str, list[str], list[str]]:
    reason_codes: list[str] = []
    reasons: list[str] = []
    saw_denial = False
    for gate_name in required:
        if gate_name not in gates:
            reason_codes.append("evidence_missing")
            reasons.append(f"required evidence gate is missing: {gate_name}")
            continue
        raw_gate = gates[gate_name]
        if gate_name == "machine_gates":
            state, gate_codes, gate_reasons = _evaluate_machine_gates(
                binding=binding,
                raw_gate=raw_gate,
            )
        else:
            if gate_name == "release_quality_audit":
                allowed = _AUDIT_PASS_STATUSES
            elif gate_name == "domain_assessment":
                allowed = _DOMAIN_ASSESSMENT_PASS_STATUSES
            else:
                allowed = _PASS_STATUSES
            state, gate_codes, gate_reasons = _evaluate_gate(
                binding=binding,
                raw_gate=raw_gate,
                allowed_pass_statuses=allowed,
                gate_name=gate_name,
                publishability_trusted_keys=publishability_trusted_keys,
                publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
                publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
                publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
                publishability_now=publishability_now,
                verify_publishability_authority=verify_publishability_authority,
            )
        reason_codes.extend(gate_codes)
        reasons.extend(f"{gate_name}: {reason}" for reason in gate_reasons)
        saw_denial = saw_denial or state == "denied"
    if saw_denial:
        return "denied", _unique(reason_codes), _unique(reasons)
    if reason_codes:
        return "insufficient_evidence", _unique(reason_codes), _unique(reasons)
    return "passed", ["qualification_passed"], [
        "all required qualification evidence gates are present and passing"
    ]


def _evaluate_machine_gates(
    *,
    binding: QualificationBinding,
    raw_gate: object,
) -> tuple[str, list[str], list[str]]:
    if not isinstance(raw_gate, Mapping) or not raw_gate:
        return (
            "insufficient_evidence",
            ["evidence_malformed"],
            ["machine gate evidence must be a non-empty object"],
        )
    states: list[str] = []
    codes: list[str] = []
    reasons: list[str] = []
    expected = set(RELEASE_CANDIDATE_MACHINE_GATES)
    unknown = sorted(str(name) for name in raw_gate if name not in expected)
    for name in unknown:
        codes.append("evidence_malformed")
        reasons.append(f"unknown machine gate is not applicable: {name}")
        states.append("insufficient_evidence")
    for name in RELEASE_CANDIDATE_MACHINE_GATES:
        if name not in raw_gate:
            codes.append("evidence_missing")
            reasons.append(f"required machine gate is missing: {name}")
            states.append("insufficient_evidence")
            continue
        state, gate_codes, gate_reasons = _evaluate_gate(
            binding=binding,
            raw_gate=raw_gate[name],
            allowed_pass_statuses=_PASS_STATUSES,
            gate_name=name,
        )
        states.append(state)
        codes.extend(gate_codes)
        reasons.extend(f"{name}: {reason}" for reason in gate_reasons)
    if "denied" in states:
        return "denied", _unique(codes), _unique(reasons)
    if "insufficient_evidence" in states:
        return "insufficient_evidence", _unique(codes), _unique(reasons)
    return "passed", [], []


def _evaluate_gate(
    *,
    binding: QualificationBinding,
    raw_gate: object,
    allowed_pass_statuses: set[str],
    gate_name: str | None = None,
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
    verify_publishability_authority: bool = False,
) -> tuple[str, list[str], list[str]]:
    if not isinstance(raw_gate, Mapping):
        return "insufficient_evidence", ["evidence_malformed"], [
            "gate is not an object"
        ]
    status = _status_from_record(raw_gate)
    if status in _DENIED_STATUSES:
        return "denied", ["evidence_non_passing"], [
            f"gate status {status} is not passing"
        ]
    schema_reason = _gate_schema_reason(
        raw_gate.get("schema_version"),
        gate_name=gate_name,
    )
    if schema_reason is not None:
        return "insufficient_evidence", [schema_reason], [
            "gate schema version is unknown or unsupported"
        ]
    shape_reason = _gate_shape_reason(
        raw_gate,
        gate_name=gate_name,
        publishability_trusted_keys=publishability_trusted_keys,
        publishability_trusted_policy_hashes=publishability_trusted_policy_hashes,
        publishability_trusted_bundle_content_hashes=publishability_trusted_bundle_content_hashes,
        publishability_trusted_release_pack_verification_hashes=publishability_trusted_release_pack_verification_hashes,
        publishability_now=publishability_now,
        verify_publishability_authority=verify_publishability_authority,
    )
    if shape_reason is not None:
        return "insufficient_evidence", [shape_reason], [
            "gate evidence is missing required identity or verification fields"
        ]
    identity_reason = _identity_reason(raw_gate, binding)
    if identity_reason is not None:
        return "insufficient_evidence", [identity_reason], [
            "gate identity does not match the exact qualification subject"
        ]
    if gate_name == "domain_assessment":
        assessment_reason = _domain_assessment_identity_reason(raw_gate, binding)
        if assessment_reason is not None:
            return "insufficient_evidence", [assessment_reason], [
                "Domain assessment does not establish the exact plan capability catalog"
            ]
    lifecycle = _string_or_none(
        raw_gate.get("lifecycle") or raw_gate.get("validity")
    )
    if lifecycle in {"stale", "invalid"}:
        return "insufficient_evidence", ["evidence_stale"], [
            "gate evidence is stale or invalid"
        ]
    if lifecycle == "revoked":
        return "insufficient_evidence", ["evidence_revoked"], [
            "gate evidence has been revoked"
        ]
    if lifecycle == "expired":
        return "insufficient_evidence", ["evidence_expired"], [
            "gate evidence has expired"
        ]
    if lifecycle == "cancelled":
        return "insufficient_evidence", ["evidence_cancelled"], [
            "gate evidence belongs to a cancelled run"
        ]
    if lifecycle == "incomplete":
        return "insufficient_evidence", ["evidence_incomplete"], [
            "gate evidence is incomplete"
        ]
    if status in allowed_pass_statuses:
        return "passed", [], []
    if status in _INSUFFICIENT_STATUSES:
        reason = {
            "stale": "evidence_stale",
            "revoked": "evidence_revoked",
            "expired": "evidence_expired",
            "cancelled": "evidence_cancelled",
            "incomplete": "evidence_incomplete",
        }.get(status, "evidence_missing")
        return "insufficient_evidence", [reason], [
            f"gate status {status or 'missing'} is not sufficient"
        ]
    if status is None:
        return "insufficient_evidence", ["evidence_missing"], [
            "gate has no bounded status"
        ]
    return "insufficient_evidence", ["evidence_unknown_status"], [
        f"gate status {status} is unknown"
    ]


def _effective_state(
    *,
    binding: QualificationBinding,
    history: Sequence[Mapping[str, object]],
    invalidated: set[str],
) -> tuple[str, bool]:
    current = "unqualified"
    dependency_invalidated = False
    for level in QUALIFICATION_LEVELS[1:]:
        candidates = [
            entry
            for entry in history
            if entry.get("attempted_qualification") == level
            and entry.get("status") == "passed"
            and _history_subject_matches(entry, binding)
        ]
        if not candidates:
            continue
        candidate = candidates[-1]
        if _entry_invalidated(candidate, invalidated):
            dependency_invalidated = True
            continue
        prerequisite = QUALIFICATION_LEVELS[QUALIFICATION_LEVELS.index(level) - 1]
        if prerequisite != "unqualified" and current != prerequisite:
            dependency_invalidated = True
            continue
        current = level
    if current == "unqualified" and any(
        entry.get("status") == "passed"
        and entry.get("attempted_qualification") in QUALIFICATION_LEVELS[1:]
        and not _history_subject_matches(entry, binding)
        for entry in history
    ):
        dependency_invalidated = True
    return current, dependency_invalidated


def _entry_invalidated(entry: Mapping[str, object], invalidated: set[str]) -> bool:
    if entry.get("invalidated") is True:
        return True
    evidence_ids = entry.get("evidence_ids")
    if isinstance(evidence_ids, Sequence) and not isinstance(evidence_ids, (str, bytes)):
        if invalidated.intersection(str(item) for item in evidence_ids):
            return True
    return bool(
        isinstance(entry.get("binding_hash"), str)
        and entry.get("binding_hash") in invalidated
    )


def _history_subject_matches(
    entry: Mapping[str, object],
    binding: QualificationBinding,
) -> bool:
    return entry.get("binding_hash") == binding.binding_hash


def _decision_entry(
    *,
    binding: QualificationBinding,
    attempted_qualification: str,
    status: str,
    effective_qualification: str,
    reason_codes: Sequence[str],
    reasons: Sequence[str],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    evidence_record = dict(evidence)
    evidence_ids = _decision_evidence_ids(binding, evidence_record)
    content = {
        "schema_version": QUALIFICATION_DECISION_SCHEMA_VERSION,
        "subject_id": binding.subject_id,
        "subject_hash": binding.subject_hash,
        "binding_hash": binding.binding_hash,
        "attempted_qualification": attempted_qualification,
        "status": status,
        "effective_qualification": effective_qualification,
        "reason_codes": list(reason_codes),
        "reasons": list(reasons),
        "evidence_ids": evidence_ids,
        "evidence_class": evidence_record.get("evidence_class", "machine"),
        "evidence": evidence_record,
    }
    decision_hash = canonical_domain_pack_hash(content)
    return {
        **content,
        "decision_id": "qualification_decision_"
        + decision_hash.removeprefix("sha256:")[:16],
    }


def _decision_evidence_ids(
    binding: QualificationBinding,
    evidence: Mapping[str, object],
) -> list[str]:
    evidence_id_values = {
        str(node.get("artifact_id"))
        for node in binding.evidence_graph
        if isinstance(node.get("artifact_id"), str)
    }
    gates = evidence.get("gates")
    if isinstance(gates, Mapping):
        evidence_id_values.update(
            str(key) for key in gates if isinstance(key, str) and key
        )
    return sorted(evidence_id_values)


def _failed_transition_report(
    *,
    binding: QualificationBinding,
    historical_decisions: list[dict[str, object]],
    requested: str,
    current: str,
    status: str,
    reason_codes: Sequence[str],
    reasons: Sequence[str],
    invalidated: set[str],
) -> dict[str, object]:
    entry = _decision_entry(
        binding=binding,
        attempted_qualification=requested,
        status=status,
        effective_qualification=current,
        reason_codes=reason_codes,
        reasons=reasons,
        evidence={},
    )
    return _report(
        binding=binding,
        historical_decisions=historical_decisions,
        attempted_qualification=requested,
        status=status,
        effective_qualification=current,
        reason_codes=reason_codes,
        reasons=reasons,
        invalidated=invalidated,
        appended_entry=entry,
    )


def _report(
    *,
    binding: QualificationBinding,
    historical_decisions: list[dict[str, object]],
    attempted_qualification: str | None,
    status: str,
    effective_qualification: str,
    reason_codes: Sequence[str],
    reasons: Sequence[str],
    invalidated: set[str],
    appended_entry: Mapping[str, object] | None = None,
    append_decision: bool = False,
) -> dict[str, object]:
    decisions = [dict(item) for item in historical_decisions]
    if appended_entry is not None or append_decision:
        if appended_entry is None:
            appended_entry = _decision_entry(
                binding=binding,
                attempted_qualification=attempted_qualification or "unqualified",
                status=status,
                effective_qualification=effective_qualification,
                reason_codes=reason_codes,
                reasons=reasons,
                evidence={},
            )
        decisions.append(dict(appended_entry))
    report: dict[str, object] = {
        "schema_version": QUALIFICATION_REPORT_SCHEMA_VERSION,
        "subject": binding.artifact_subject.to_record(),
        "qualification_binding": binding.to_record(),
        "attempted_qualification": attempted_qualification,
        "status": status,
        "effective_qualification": effective_qualification,
        "decision": {
            "status": status,
            "reason_codes": _unique(reason_codes),
            "reasons": _unique(reasons),
        },
        "historical_decisions": decisions,
        "invalidated_evidence": sorted(invalidated),
        "claims": {
            "release_candidate": effective_qualification in QUALIFICATION_LEVELS[1:],
            "eligible_for_human_publication_review": effective_qualification
            in QUALIFICATION_LEVELS[1:],
            "publishable": effective_qualification in {"publishable", "training_recommended"},
            "training_recommended": effective_qualification == "training_recommended",
        },
    }
    validate_qualification_report_record(report)
    return report


def _evidence_subject_mismatch(
    evidence: Mapping[str, object],
    binding: QualificationBinding,
) -> bool:
    raw_binding = evidence.get("binding")
    if not isinstance(raw_binding, Mapping):
        return True
    try:
        supplied = QualificationBinding.from_record(raw_binding)
    except QualificationContractError:
        return True
    if supplied.binding_hash != binding.binding_hash:
        return True
    for field, expected in (
        ("subject_id", binding.subject_id),
        ("subject_hash", binding.subject_hash),
        ("binding_hash", binding.binding_hash),
        ("release_pack_hash", binding.release_pack_hash),
    ):
        if field in evidence and evidence[field] != expected:
            return True
    raw_graph = evidence.get("evidence_graph")
    if not isinstance(raw_graph, Sequence) or isinstance(raw_graph, (str, bytes)):
        return True
    if [dict(item) for item in raw_graph if isinstance(item, Mapping)] != [
        dict(item) for item in binding.evidence_graph
    ]:
        return True
    if any(not isinstance(item, Mapping) for item in raw_graph):
        return True
    return False


def _coerce_binding(
    subject: QualificationBinding | Mapping[str, object],
) -> QualificationBinding:
    if isinstance(subject, QualificationBinding):
        return subject
    try:
        return QualificationBinding.from_record(subject)
    except (QualificationContractError, TypeError, ValueError):
        raise QualificationContractError("qualification_binding_malformed") from None


def _require_binding(binding: object) -> None:
    if not isinstance(binding, QualificationBinding):
        raise QualificationContractError("qualification_binding_malformed")


def _binding_content_record(
    *,
    artifact_subject: QualificationSubject,
    release_pack_hash: str,
    release_pack_byte_count: int,
    domain_pack_reference: DomainPackReference,
    plan_id: str,
    plan_hash: str,
    runtime_contract: DomainRuntimeContractReference,
    capability_references: tuple[DomainCapabilityReference, ...],
    component_contracts: tuple[DomainComponentContractReference, ...],
    profile: Mapping[str, object],
    evidence_graph: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    return {
        "schema_version": QUALIFICATION_BINDING_SCHEMA_VERSION,
        "artifact_subject": artifact_subject.to_record(),
        "release_pack_hash": release_pack_hash,
        "release_pack_byte_count": release_pack_byte_count,
        "domain_pack_reference": domain_pack_reference.to_record(),
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "runtime_contract": runtime_contract.to_record(),
        "capability_references": [
            item.to_record()
            for item in sorted(capability_references, key=_capability_sort_key)
        ],
        "component_contracts": [
            item.to_record()
            for item in sorted(component_contracts, key=lambda item: item.component_kind)
        ],
        "profile": dict(profile),
        "evidence_graph": [dict(node) for node in evidence_graph],
    }


def _artifact_references_for_subject(
    graph: Sequence[Mapping[str, object]],
) -> tuple[QualificationArtifactReference, ...]:
    references: list[QualificationArtifactReference] = []
    for node in graph:
        byte_count = node.get("byte_count")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0:
            continue
        try:
            references.append(
                QualificationArtifactReference(
                    artifact_id=_text(node.get("artifact_id")),
                    artifact_schema_version=_text(node.get("artifact_schema_version")),
                    content_hash=_text(node.get("content_hash")),
                    byte_count=byte_count,
                )
            )
        except (DomainPackContractError, TypeError, ValueError):
            continue
    unique: dict[str, QualificationArtifactReference] = {}
    for reference in references:
        unique[reference.artifact_id] = reference
    return tuple(unique.values())


def _validate_evidence_graph_node(node: Mapping[str, object]) -> None:
    if not isinstance(node, Mapping):
        raise QualificationContractError("qualification_binding_malformed")
    _require_identifier(_text(node.get("artifact_id")), "artifact_id")
    _require_identifier(
        _text(node.get("artifact_schema_version")),
        "artifact_schema_version",
    )
    _require_hash(_text(node.get("content_hash")), "content_hash")
    byte_count = node.get("byte_count")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0:
        raise QualificationContractError("qualification_binding_malformed")
    status = node.get("status", "active")
    if status not in {"active", "stale", "revoked", "expired", "cancelled", "incomplete"}:
        raise QualificationContractError("qualification_binding_malformed")
    schema_reason = _schema_reason(node.get("artifact_schema_version"))
    if schema_reason is not None:
        raise QualificationContractError(schema_reason)


def _binding_invalidations(
    binding: QualificationBinding,
) -> tuple[set[str], tuple[str, ...]]:
    reason_by_status = {
        "stale": "evidence_stale",
        "revoked": "evidence_revoked",
        "expired": "evidence_expired",
        "cancelled": "evidence_cancelled",
        "incomplete": "evidence_incomplete",
    }
    invalidated: set[str] = set()
    reason_codes: list[str] = []
    for node in binding.evidence_graph:
        status = node.get("status", "active")
        if status == "active":
            continue
        artifact_id = node.get("artifact_id")
        if isinstance(artifact_id, str):
            invalidated.add(artifact_id)
        reason_code = reason_by_status.get(str(status), "evidence_malformed")
        reason_codes.append(reason_code)
    return invalidated, tuple(_unique(reason_codes))


def _identity_reason(raw: Mapping[str, object], binding: QualificationBinding) -> str | None:
    for field, expected in (
        ("subject_id", binding.subject_id),
        ("subject_hash", binding.subject_hash),
        ("binding_hash", binding.binding_hash),
        ("plan_id", binding.plan_id),
        ("plan_hash", binding.plan_hash),
        ("release_pack_hash", binding.release_pack_hash),
        ("release_pack_sha256", binding.release_pack_hash),
        ("pack_sha256", binding.release_pack_hash),
    ):
        if field in raw and raw[field] != expected:
            return "evidence_identity_mismatch"
    if (
        "domain_pack_reference" in raw
        and raw["domain_pack_reference"] != binding.domain_pack_reference.to_record()
    ):
        return "evidence_identity_mismatch"
    if (
        "runtime_contract" in raw
        and raw["runtime_contract"] != binding.runtime_contract.to_record()
    ):
        return "evidence_identity_mismatch"
    return None


def _bind_gate_identity(
    binding: QualificationBinding,
    raw_gate: Mapping[str, object],
) -> dict[str, object]:
    """Carry the exact subject identity into a constructed gate record.

    The evaluator still checks these fields rather than trusting the
    constructor.  Keeping the identity on each gate makes independently
    serialized gate evidence auditable and prevents a status-only record from
    being mistaken for evidence for the current subject.
    """

    record = dict(raw_gate)
    identity = {
        "subject_id": binding.subject_id,
        "subject_hash": binding.subject_hash,
        "binding_hash": binding.binding_hash,
        "release_pack_hash": binding.release_pack_hash,
    }
    for field, value in identity.items():
        record.setdefault(field, value)
    return record


def _gate_shape_reason(
    raw_gate: Mapping[str, object],
    *,
    gate_name: str | None,
    publishability_trusted_keys: Mapping[str, str | bytes] | None = None,
    publishability_trusted_policy_hashes: Iterable[str] | None = None,
    publishability_trusted_bundle_content_hashes: Iterable[str] | None = None,
    publishability_trusted_release_pack_verification_hashes: Iterable[str] | None = None,
    publishability_now: str | None = None,
    verify_publishability_authority: bool = False,
) -> str | None:
    required = set(_GATE_IDENTITY_FIELDS)
    if gate_name is not None:
        required.update(_GATE_REQUIRED_FIELDS.get(gate_name, ()))
    missing = sorted(field for field in required if field not in raw_gate)
    if missing:
        return "evidence_missing"
    if gate_name == "publishability":
        if "bundle" not in raw_gate or "decision" not in raw_gate:
            return "evidence_incomplete"
        if (
            verify_publishability_authority
            and (
                publishability_trusted_keys is None
                or publishability_trusted_policy_hashes is None
                or publishability_trusted_bundle_content_hashes is None
                or publishability_trusted_release_pack_verification_hashes is None
                or publishability_now is None
            )
        ):
            return "evidence_incomplete"
        try:
            from synthesis.publishability import _validate_publishability_gate_record

            _validate_publishability_gate_record(
                raw_gate,
                trusted_keys=(
                    publishability_trusted_keys
                    if verify_publishability_authority
                    else None
                ),
                trusted_policy_hashes=(
                    publishability_trusted_policy_hashes
                    if verify_publishability_authority
                    else None
                ),
                trusted_bundle_content_hashes=(
                    publishability_trusted_bundle_content_hashes
                    if verify_publishability_authority
                    else None
                ),
                trusted_release_pack_verification_hashes=(
                    publishability_trusted_release_pack_verification_hashes
                    if verify_publishability_authority
                    else None
                ),
                now=publishability_now if verify_publishability_authority else None,
                structural_only=not verify_publishability_authority,
            )
        except Exception:
            return "evidence_incomplete"
        return None
    higher_gate = (
        gate_name
        if isinstance(gate_name, str)
        and gate_name in HIGHER_LEVEL_REQUIRED_EVIDENCE.values()
        else None
    )
    if higher_gate is not None:
        evidence_ids = raw_gate.get("evidence_ids")
        verification = raw_gate.get("verification")
        if (
            not isinstance(evidence_ids, Sequence)
            or isinstance(evidence_ids, (str, bytes))
            or not evidence_ids
            or any(not isinstance(item, str) or not item for item in evidence_ids)
            or not isinstance(verification, Mapping)
            or _status_from_record(verification) != "passed"
            or any(
                not isinstance(raw_gate.get(field), Mapping)
                or _status_from_record(_mapping_or_empty(raw_gate.get(field)))
                not in {"passed", "verified"}
                for field in _GATE_REQUIRED_FIELDS[higher_gate]
                if field not in {"evidence_ids", "verification"}
            )
        ):
            return "evidence_incomplete"
    return None


def _domain_assessment_identity_reason(
    raw: Mapping[str, object],
    binding: QualificationBinding,
) -> str | None:
    required_fields = (
        "domain_pack_reference",
        "plan_id",
        "plan_hash",
        "established_capability_references",
    )
    if any(field not in raw for field in required_fields):
        return "evidence_missing"
    raw_references = raw.get("established_capability_references")
    if not isinstance(raw_references, Sequence) or isinstance(
        raw_references, (str, bytes)
    ):
        return "evidence_malformed"
    try:
        actual = sorted(
            canonical_domain_pack_json(item)
            for item in raw_references
            if isinstance(item, Mapping)
        )
        expected = sorted(
            canonical_domain_pack_json(reference.to_record())
            for reference in binding.capability_references
        )
    except (TypeError, ValueError):
        return "evidence_malformed"
    if len(actual) != len(raw_references) or actual != expected:
        return "evidence_identity_mismatch"
    if raw.get("schema_version") == "domain_assessment_v1":
        if raw.get("status") != "established" or raw.get(
            "reason_code"
        ) != "exact_evidence_established":
            return "evidence_non_passing"
        evidence_references = raw.get("evidence_references")
        if not isinstance(evidence_references, Sequence) or isinstance(
            evidence_references, (str, bytes)
        ) or not evidence_references:
            return "evidence_missing"
        try:
            normalized_evidence_references = [
                DomainEvidenceReference.from_record(item)
                for item in evidence_references
                if isinstance(item, Mapping)
            ]
            if len(normalized_evidence_references) != len(evidence_references):
                return "evidence_malformed"
        except (DomainPackContractError, TypeError, ValueError):
            return "evidence_malformed"
        expected_evidence_references = {
            (
                _safe_evidence_id(str(node["artifact_id"])),
                str(node["artifact_schema_version"]),
                str(node["content_hash"]),
            )
            for node in binding.evidence_graph
        }
        actual_evidence_references = {
            (
                reference.evidence_id,
                reference.evidence_schema_version,
                reference.evidence_hash,
            )
            for reference in normalized_evidence_references
        }
        if actual_evidence_references != expected_evidence_references:
            return "evidence_identity_mismatch"
        if not isinstance(raw.get("assessment_hash"), str) or not isinstance(
            raw.get("assessment_id"), str
        ):
            return "evidence_malformed"
        content = {
            "schema_version": raw["schema_version"],
            "domain_pack_reference": raw["domain_pack_reference"],
            "plan_id": raw["plan_id"],
            "plan_hash": raw["plan_hash"],
            "evidence_references": sorted(
                (item.to_record() for item in normalized_evidence_references),
                key=lambda item: (
                    str(item.get("evidence_id")),
                    str(item.get("evidence_schema_version")),
                    str(item.get("evidence_hash")),
                ),
            ),
            "established_capability_references": sorted(
                (
                    item
                    for item in raw_references
                    if isinstance(item, Mapping)
                ),
                key=lambda item: (
                    str(item.get("domain_pack_id")),
                    str(item.get("capability_key")),
                    str(item.get("capability_contract_version")),
                ),
            ),
            "status": raw["status"],
            "reason_code": raw["reason_code"],
        }
        expected_hash = canonical_domain_pack_hash(content)
        if raw["assessment_hash"] != expected_hash:
            return "evidence_hash_mismatch"
        if raw["assessment_id"] != "domain_assessment_" + expected_hash.removeprefix(
            "sha256:"
        )[:16]:
            return "evidence_malformed"
    return None


def _schema_reason(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        return "evidence_malformed"
    if raw not in _SUPPORTED_SCHEMA_VERSIONS:
        return "evidence_unknown_version"
    return None


def _gate_schema_reason(raw: object, *, gate_name: str | None) -> str | None:
    if raw is None:
        return "evidence_missing"
    reason = _schema_reason(raw)
    if reason is not None:
        return reason
    expected = _GATE_SCHEMA_VERSIONS.get(gate_name or "")
    if expected is not None and raw not in expected:
        return "evidence_identity_mismatch"
    return None


def _status_from_record(raw: Mapping[str, object]) -> str | None:
    for value in (
        raw.get("status"),
        _mapping_or_empty(raw.get("decision")).get("status"),
        _mapping_or_empty(raw.get("verification")).get("status"),
        _mapping_or_empty(raw.get("assessment")).get("status"),
        _mapping_or_empty(raw.get("result")).get("status"),
    ):
        if isinstance(value, str):
            return value
    if raw.get("passed") is True:
        return "passed"
    return None


def _workspace_insufficient_report(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    reason_code: str,
    reason: str,
) -> dict[str, object]:
    """Return a bounded report even when no exact Workspace subject is readable."""

    digest = _hash_file_if_readable(release_pack_path)
    fallback_hash = digest[0] if digest is not None else "sha256:" + "0" * 64
    fallback_bytes = max(digest[1], 1) if digest is not None else 1
    from synthesis.workspace_domain_pack import build_workspace_domain_pack, workspace_planning_intent
    from synthesis.domain_pack import AdmittedSource

    pack = build_workspace_domain_pack()
    plan = pack.plan(
        workspace_planning_intent(pack),
        AdmittedSource(
            source_id="workspace_qualification_unavailable_source",
            source_schema_version="workspace_source_v1",
            source_content_hash=canonical_domain_pack_hash({"path": manifest_path.name}),
            admission_policy_id="workspace_source_policy_v1",
            admission_policy_hash=canonical_domain_pack_hash({"policy": "unavailable"}),
        ),
    )
    assert isinstance(plan, DomainPlan)
    binding = QualificationBinding.from_plan(
        plan,
        release_pack_hash=fallback_hash,
        release_pack_byte_count=fallback_bytes,
        profile={
            "profile_id": "workspace_release_candidate_unavailable",
            "profile_purpose": "release_candidate",
            "generation_mode": "unknown",
        },
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
        appended_entry=_decision_entry(
            binding=binding,
            attempted_qualification="release_candidate",
            status="insufficient_evidence",
            effective_qualification="unqualified",
            reason_codes=(reason_code,),
            reasons=(reason,),
            evidence={},
        ),
    )


class _WorkspaceQualificationInsufficiency(Exception):
    def __init__(self, reason_code: str, reason: str) -> None:
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason


def _load_workspace_release_inputs(
    *,
    manifest_path: Path,
    release_pack_path: Path,
    release_quality_audit_path: Path | None,
) -> dict[str, object]:
    from synthesis.contracts import (
        ContractValidationError,
        validate_coverage_evidence_record,
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
    from synthesis.workspace_domain_pack import build_workspace_domain_pack

    try:
        manifest = _load_json_mapping(manifest_path)
        validate_manifest_record(manifest)
        pack = _load_json_mapping(release_pack_path)
        verification = verify_dataset_release_pack(release_pack_path)
        pack_verification = _mapping_or_empty(verification.get("verification"))
        if pack_verification.get("status") not in {"passed", "failed", "insufficient_evidence"}:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_malformed",
                "standalone release-pack verification has no bounded status",
            )
        artifacts = _mapping_or_empty(pack.get("artifacts"))
        samples_artifact = _mapping_or_empty(artifacts.get("samples"))
        samples_path = release_pack_path.parent / _text(samples_artifact.get("path"))
        samples = _load_jsonl(samples_path)
        rejections_artifact = _mapping_or_empty(artifacts.get("rejections"))
        rejections_path = release_pack_path.parent / _text(
            rejections_artifact.get("path")
        )
        rejections = _load_jsonl(rejections_path)
        for sample in samples:
            validate_sample_record(sample)
        for rejection in rejections:
            validate_rejection_record(rejection)
        if not samples:
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace release pack contains no accepted samples",
            )
        first_binding = _mapping_or_empty(samples[0].get("workspace_evidence"))
        if not first_binding:
            raise _WorkspaceQualificationInsufficiency(
                "workspace_plan_evidence_missing",
                "accepted Workspace samples do not contain canonical evidence bindings",
            )
        plan_record = _mapping_or_empty(
            _mapping_or_empty(first_binding.get("plan")).get("plan_record")
        )
        if not plan_record:
            raise _WorkspaceQualificationInsufficiency(
                "workspace_plan_evidence_missing",
                "Workspace evidence does not retain the exact Domain plan record",
            )
        pack_adapter = build_workspace_domain_pack()
        plan = DomainPlan.from_record(
            plan_record,
            descriptor=pack_adapter.descriptor,
        )
        _validate_workspace_samples(samples, plan)

        run_profile = _mapping_or_empty(manifest.get("run_profile"))
        profile = _qualification_profile(run_profile)
        profile_reasons = _workspace_profile_reasons(manifest, run_profile)

        release_report = _load_pack_artifact_json(
            release_pack_path.parent,
            artifacts,
            "dataset_release_report",
        )
        validate_dataset_release_report_record(release_report)
        evaluation_report = _load_pack_artifact_json(
            release_pack_path.parent,
            artifacts,
            "evaluation_report",
        )
        validate_evaluation_report_record(evaluation_report)
        _validate_workspace_evaluation_report(evaluation_report, plan=plan)
        profile_decision_report = _load_pack_artifact_json(
            release_pack_path.parent,
            artifacts,
            "profile_decision_report",
        )
        validate_profile_decision_report_record(profile_decision_report)
        quality_report = _load_pack_artifact_json(
            release_pack_path.parent,
            artifacts,
            "quality_report",
        )
        _validate_workspace_quality_report(quality_report, manifest=manifest)
        _validate_workspace_profile_decision_alignment(
            profile_decision_report,
            quality_report=quality_report,
        )
        manifest_artifacts = _mapping_or_empty(manifest.get("artifacts"))
        coverage_plan = _load_manifest_artifact_json(
            release_pack_path.parent,
            manifest_artifacts,
            "coverage_plan",
        )
        coverage_evidence = _load_manifest_artifact_json(
            release_pack_path.parent,
            manifest_artifacts,
            "coverage_evidence",
        )
        validate_coverage_evidence_record(coverage_evidence)
        from synthesis.coverage_evidence import verify_coverage_evidence

        verify_coverage_evidence(
            coverage_evidence,
            plan=coverage_plan,
            run_profile=_mapping_or_empty(manifest.get("run_profile")),
            samples=samples,
            rejections=rejections,
        )
        audit_path = release_quality_audit_path
        if audit_path is None:
            audit_name = manifest.get("artifacts", {})
            audit_path = (
                release_pack_path.parent / _text(audit_name.get("release_quality_audit"))
                if isinstance(audit_name, Mapping)
                and audit_name.get("release_quality_audit")
                else None
            )
        if audit_path is None or not audit_path.exists():
            raise _WorkspaceQualificationInsufficiency(
                "evidence_missing",
                "release-quality audit is unavailable",
            )
        audit = _load_json_mapping(audit_path)
        validate_release_quality_audit_record(audit)

        release_pack_artifact = build_artifact_hash_record(release_pack_path)
        release_pack_hash = release_pack_artifact.sha256
        release_pack_byte_count = release_pack_artifact.byte_count
        graph = _workspace_evidence_graph(
            base_dir=release_pack_path.parent,
            artifacts=artifacts,
            manifest=manifest,
            audit_path=audit_path,
        )
        binding = QualificationBinding.from_plan(
            plan,
            release_pack_hash=release_pack_hash,
            release_pack_byte_count=release_pack_byte_count,
            profile=profile,
            evidence_graph=graph,
        )

        machine_gates = _workspace_machine_gates(
            manifest=manifest,
            samples=samples,
            quality_report=quality_report,
            evaluation_report=evaluation_report,
            profile_decision_report=profile_decision_report,
            release_report=release_report,
            coverage_evidence=coverage_evidence,
            pack_verification=pack_verification,
            profile_reasons=profile_reasons,
        )
        assessment = pack_adapter.assess(
            plan,
            DomainAssessmentEvidence(
                evidence_references=tuple(
                    DomainEvidenceReference(
                        evidence_id=_safe_evidence_id(str(node["artifact_id"])),
                        evidence_schema_version=str(node["artifact_schema_version"]),
                        evidence_hash=str(node["content_hash"]),
                    )
                    for node in graph
                ),
                established_capability_references=tuple(plan.capability_references),
            ),
        )
        if not isinstance(assessment, DomainAssessment):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace Domain assessment could not bind the exact plan",
            )
        evidence = build_release_candidate_evidence(
            binding=binding,
            machine_gates=machine_gates,
            domain_assessment=assessment,
            release_completeness={
                "schema_version": "qualification_release_completeness_v1",
                **dict(_mapping_or_empty(release_report.get("release_completeness"))),
            },
            release_quality_audit=audit,
            release_pack_verification={
                "schema_version": "qualification_release_pack_verification_v1",
                **dict(verification),
                "release_pack_hash": release_pack_hash,
            },
            evidence_class=(
                "real_machine"
                if not profile_reasons
                else "machine"
            ),
        )
        return {"binding": binding, "evidence": evidence}
    except _WorkspaceQualificationInsufficiency:
        raise
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ContractValidationError) as exc:
        raise _WorkspaceQualificationInsufficiency(
            "evidence_malformed",
            f"Workspace release evidence is unreadable or malformed: {type(exc).__name__}",
        ) from None


def _workspace_profile_reasons(
    manifest: Mapping[str, object],
    run_profile: Mapping[str, object],
) -> list[str]:
    reasons: list[str] = []
    if run_profile.get("profile_purpose") != "release_candidate":
        reasons.append("profile purpose is not release_candidate")
    if run_profile.get("generation_mode") != "llm":
        reasons.append("Workspace Release Candidate requires coverage-driven LLM generation")
    artifacts = _mapping_or_empty(manifest.get("artifacts"))
    if not artifacts.get("coverage_plan") or not artifacts.get("coverage_evidence"):
        reasons.append("coverage plan and coverage evidence are required")
    mutation = _mapping_or_empty(run_profile.get("mutation_admission"))
    if mutation.get("mode") != "enforce":
        reasons.append("Workspace Release Candidate requires enforced mutation admission")
    return reasons


def _validate_workspace_quality_report(
    quality_report: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> None:
    if quality_report.get("schema_version") != "quality_report_v1":
        raise QualificationContractError("evidence_unknown_version")
    if quality_report.get("dataset_version") != manifest.get("dataset_version"):
        raise QualificationContractError("evidence_identity_mismatch")
    counts = quality_report.get("counts")
    rates = quality_report.get("rates")
    if not isinstance(counts, Mapping) or not isinstance(rates, Mapping):
        raise QualificationContractError("evidence_malformed")
    required_counts = ("total", "accepted", "rejected", "executable")
    for key in required_counts:
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise QualificationContractError("evidence_malformed")
    if counts["accepted"] + counts["rejected"] != counts["total"]:
        raise QualificationContractError("evidence_identity_mismatch")
    if (
        counts["accepted"] != manifest.get("accepted_count")
        or counts["rejected"] != manifest.get("rejected_count")
    ):
        raise QualificationContractError("evidence_identity_mismatch")
    expected_rates = {
        "success_rate": _safe_rate(counts["accepted"], counts["executable"]),
        "executable_rate": _safe_rate(counts["executable"], counts["total"]),
    }
    for key, expected in expected_rates.items():
        actual = _number_or_none(rates.get(key))
        if actual is None or not math.isfinite(actual) or not 0.0 <= actual <= 1.0:
            raise QualificationContractError("evidence_malformed")
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
            raise QualificationContractError("evidence_identity_mismatch")
    if not isinstance(quality_report.get("rejection_causes"), Mapping):
        raise QualificationContractError("evidence_malformed")


def _validate_workspace_profile_decision_alignment(
    profile_decision_report: Mapping[str, object],
    *,
    quality_report: Mapping[str, object],
) -> None:
    observed = profile_decision_report.get("observed")
    counts = quality_report.get("counts")
    rates = quality_report.get("rates")
    if not isinstance(observed, Mapping) or not isinstance(counts, Mapping) or not isinstance(rates, Mapping):
        raise QualificationContractError("evidence_malformed")
    for field in ("total_candidates", "accepted", "rejected"):
        quality_field = {
            "total_candidates": "total",
            "accepted": "accepted",
            "rejected": "rejected",
        }[field]
        if observed.get(field) != counts.get(quality_field):
            raise QualificationContractError("evidence_identity_mismatch")
    for field in ("success_rate", "executable_rate"):
        actual = _number_or_none(observed.get(field))
        expected = _number_or_none(rates.get(field))
        if actual is None or expected is None or not math.isclose(
            actual,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise QualificationContractError("evidence_identity_mismatch")


def _validate_workspace_evaluation_report(
    evaluation_report: Mapping[str, object],
    *,
    plan: DomainPlan,
) -> None:
    suite = _mapping_or_empty(evaluation_report.get("suite"))
    if (
        suite.get("suite_id") != "workspace_tasks_heldout_v1"
        or suite.get("suite_version") != "workspace_tasks_heldout_v1"
        or suite.get("domain_id") != "workspace_tasks_fixture"
        or suite.get("task_count") != 5
    ):
        raise QualificationContractError("evidence_identity_mismatch")
    domain = _mapping_or_empty(evaluation_report.get("domain"))
    if domain.get("domain_id") != "workspace_tasks_fixture":
        raise QualificationContractError("evidence_identity_mismatch")
    expected_capabilities = {
        canonical_domain_pack_json(reference.to_record())
        for reference in plan.held_out_capability_references
    }
    actual_capabilities = evaluation_report.get("capability_references")
    if not isinstance(actual_capabilities, list) or {
        canonical_domain_pack_json(item)
        for item in actual_capabilities
        if isinstance(item, Mapping)
    } != expected_capabilities or any(
        not isinstance(item, Mapping) for item in actual_capabilities
    ):
        raise QualificationContractError("evidence_identity_mismatch")
    thresholds = _mapping_or_empty(evaluation_report.get("thresholds"))
    capability_thresholds = _mapping_or_empty(
        thresholds.get("min_capability_pass_rates")
    )
    slices = _mapping_or_empty(evaluation_report.get("capability_slices"))
    for reference in plan.held_out_capability_references:
        key = reference.capability_key
        threshold = _number_or_none(capability_thresholds.get(key))
        capability_slice = _mapping_or_empty(slices.get(key))
        slice_total = capability_slice.get("total")
        slice_passed = capability_slice.get("passed")
        slice_rate = capability_slice.get("pass_rate")
        if (
            threshold != 1.0
            or not capability_slice
            or not isinstance(slice_total, int)
            or isinstance(slice_total, bool)
            or slice_total <= 0
            or slice_passed != slice_total
            or slice_rate != 1.0
        ):
            raise QualificationContractError("evidence_non_passing")
    decision = _mapping_or_empty(evaluation_report.get("decision"))
    if decision.get("status") != "passed":
        raise QualificationContractError("evidence_non_passing")
    from synthesis.evaluation import workspace_tasks_heldout_suite

    expected_tasks = {
        task.task_id: {
            canonical_domain_pack_json(reference.to_record())
            for reference in task.capability_references
        }
        for task in workspace_tasks_heldout_suite().tasks
    }
    task_results = evaluation_report.get("task_results")
    if not isinstance(task_results, list) or {
        item.get("task_id") for item in task_results if isinstance(item, Mapping)
    } != set(expected_tasks) or any(
        not isinstance(item, Mapping) or item.get("status") != "passed"
        or {
            canonical_domain_pack_json(reference)
            for reference in item.get("capability_references", [])
            if isinstance(reference, Mapping)
        }
        != expected_tasks.get(item.get("task_id"), set())
        for item in task_results
    ):
        raise QualificationContractError("evidence_non_passing")


def _machine_gate(status: str, **fields: object) -> dict[str, object]:
    return {
        "schema_version": _MACHINE_GATE_SCHEMA_VERSION,
        "status": status,
        **fields,
    }


def _workspace_sample_binding_is_structurally_valid(
    sample: Mapping[str, object],
    binding: Mapping[str, object],
    *,
    plan: DomainPlan,
) -> bool:
    task_contract = _mapping_or_empty(binding.get("task_contract"))
    if (
        not isinstance(task_contract.get("candidate_id"), str)
        or not isinstance(task_contract.get("task_type"), str)
        or not _is_hash(task_contract.get("contract_hash"))
    ):
        return False
    grounding = _mapping_or_empty(binding.get("grounding"))
    if not all(
        _is_hash(grounding.get(field))
        for field in (
            "primary_arguments_hash",
            "expected_state_hash",
            "expected_answer_hash",
        )
    ):
        return False
    final_state = _mapping_or_empty(binding.get("final_state"))
    if (
        not _is_hash(final_state.get("expected_state_hash"))
        or not _is_hash(final_state.get("verification_hash"))
        or final_state.get("expected_state_hash")
        != grounding.get("expected_state_hash")
        or final_state.get("verification_passed") is not True
    ):
        return False
    verifier = _mapping_or_empty(binding.get("verifier"))
    if not isinstance(verifier.get("id"), str) or not isinstance(
        verifier.get("version"), str
    ):
        return False
    verification = sample.get("verification")
    if not isinstance(verification, Mapping) or verification.get("passed") is not True:
        return False
    if binding.get("verification_hash") != canonical_domain_pack_hash(verification):
        return False
    try:
        from synthesis.mutation_admission import canonical_hash

        expected_verification_hash = canonical_hash(verification)
    except (TypeError, ValueError):
        return False
    if final_state.get("verification_hash") != expected_verification_hash:
        return False
    assignment = binding.get("assignment")
    assignment_refs = binding.get("assignment_capability_references")
    if not isinstance(assignment, Mapping) or not isinstance(assignment_refs, list):
        return False
    if (
        assignment.get("schema_version") != "coverage_assignment_lineage_v1"
        or assignment.get("assignment_id")
        != "coverage_assignment_"
        + str(assignment.get("assignment_hash", "")).removeprefix("sha256:")[:16]
        or not _is_hash(assignment.get("assignment_hash"))
        or assignment.get("plan_id") != plan.plan_id
        or assignment.get("plan_hash") != plan.plan_hash
    ):
        return False
    catalog = _mapping_or_empty(assignment.get("catalog"))
    if catalog.get("capability_references") != assignment_refs:
        return False
    scheduler = _mapping_or_empty(assignment.get("scheduler"))
    grounding_scope = _mapping_or_empty(assignment.get("grounding_scope"))
    grounding_unit_index = grounding_scope.get("unit_index")
    if (
        scheduler.get("schema_version") != "coverage_scheduler_v1"
        or not isinstance(scheduler.get("selection_policy"), str)
        or not isinstance(scheduler.get("tie_break"), str)
        or not isinstance(grounding_scope.get("context_key"), str)
        or not isinstance(grounding_unit_index, int)
        or isinstance(grounding_unit_index, bool)
        or grounding_unit_index < 0
        or not _is_hash(grounding_scope.get("grounding_hash"))
    ):
        return False
    if not _workspace_recovery_is_valid(binding):
        return False
    episode = binding.get("episode")
    if episode is not None:
        episode_mapping = _mapping_or_empty(episode)
        if (
            not isinstance(episode_mapping.get("episode_id"), str)
            or not _is_hash(episode_mapping.get("episode_hash"))
            or not _is_hash(episode_mapping.get("core_episode_hash"))
        ):
            return False
    return True


def _workspace_sample_semantics_are_valid(
    sample: Mapping[str, object],
    binding: Mapping[str, object],
) -> bool:
    """Check the accepted sample's observable execution against its contract.

    The release adapter does not rerun a provider.  It does, however, require
    the serialized task, tool trajectory, verifier, state-change count, and
    final response to agree with one another before any gate can pass.
    """

    task = _mapping_or_empty(sample.get("task"))
    constraints = _mapping_or_empty(task.get("constraints"))
    difficulty = _mapping_or_empty(task.get("difficulty"))
    task_contract = _mapping_or_empty(binding.get("task_contract"))
    task_type = task_contract.get("task_type")
    if not isinstance(task_type, str) or not task_type:
        return False
    if (
        task.get("candidate_id") is not None
        and task.get("candidate_id") != task_contract.get("candidate_id")
    ):
        return False
    if constraints.get("task_type") not in {None, task_type}:
        return False
    required_tools = constraints.get("required_tools")
    if (
        not isinstance(required_tools, list)
        or not required_tools
        or any(not isinstance(tool, str) or not tool for tool in required_tools)
    ):
        return False
    expected_tools = {
        "workspace_item_search": ["search_workspace_items"],
        "workspace_task_creation": [
            "search_workspace_items",
            "create_workspace_task",
        ],
        "workspace_comment_update": [
            "search_workspace_items",
            "add_workspace_comment",
        ],
        # These names are retained only for historical fixture readability.
        "workspace_item_lookup": ["search_workspace_items"],
        "workspace_branch_fallback": ["search_workspace_items"],
    }.get(task_type)
    if expected_tools is not None and required_tools != expected_tools:
        return False
    declared_tools = {
        str(tool.get("name"))
        for tool in _records(sample.get("tools"))
        if isinstance(tool.get("name"), str)
    }
    if not set(required_tools).issubset(declared_tools):
        return False
    trajectory = sample.get("trajectory")
    if not isinstance(trajectory, Sequence) or isinstance(trajectory, (str, bytes)):
        return False
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
        return False
    if any(event.get("tool") not in declared_tools for event in (*actions, *observations)):
        return False
    if any(event.get("tool") not in required_tools for event in actions):
        return False
    final_events = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "final_response"
    ]
    if (
        len(final_events) != 1
        or final_events[0].get("content") != sample.get("final_response")
    ):
        return False
    verifier = _mapping_or_empty(sample.get("verifier"))
    verification = _mapping_or_empty(sample.get("verification"))
    binding_verifier = _mapping_or_empty(binding.get("verifier"))
    if (
        verifier.get("id") != binding_verifier.get("id")
        or verifier.get("version") != binding_verifier.get("version")
        or verification.get("verifier_id") != verifier.get("id")
        or verification.get("version") != verifier.get("version")
        or verification.get("passed") is not True
    ):
        return False
    checks = verification.get("checks")
    if (
        not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(check, Mapping) or check.get("passed") is not True
            for check in checks
        )
    ):
        return False
    state_change_events = [
        event
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "state_change"
    ]
    state_changes = difficulty.get("state_changes")
    if not isinstance(state_changes, int) or isinstance(state_changes, bool):
        return False
    if state_changes != len(state_change_events):
        return False
    if state_changes > 0:
        mutation = _mapping_or_empty(sample.get("mutation_admission"))
        if (
            mutation.get("mode") != "enforce"
            or _status_from_record(mutation) not in _PASS_STATUSES
        ):
            return False
    observed_values = _workspace_observed_strings(observations)
    final_response = sample.get("final_response")
    return (
        isinstance(final_response, str)
        and bool(observed_values)
        and any(value in final_response for value in observed_values)
    )


def _workspace_observed_strings(
    observations: Sequence[object],
) -> set[str]:
    values: set[str] = set()
    for event in observations:
        observation = event.get("observation") if isinstance(event, Mapping) else None
        _collect_workspace_observed_strings(observation, values)
    return values


def _collect_workspace_observed_strings(value: object, output: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"item_id", "summary", "task_id", "comment_id"} and isinstance(
                item, str
            ):
                output.add(item)
            _collect_workspace_observed_strings(item, output)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _collect_workspace_observed_strings(item, output)


def _workspace_sample_grounding_is_valid(sample: Mapping[str, object]) -> bool:
    binding = _mapping_or_empty(sample.get("workspace_evidence"))
    return _workspace_sample_binding_hashes_are_valid(binding)


def _workspace_sample_binding_hashes_are_valid(binding: Mapping[str, object]) -> bool:
    grounding = _mapping_or_empty(binding.get("grounding"))
    final_state = _mapping_or_empty(binding.get("final_state"))
    return (
        all(
            _is_hash(grounding.get(field))
            for field in (
                "primary_arguments_hash",
                "expected_state_hash",
                "expected_answer_hash",
            )
        )
        and _is_hash(final_state.get("expected_state_hash"))
        and _is_hash(final_state.get("verification_hash"))
        and final_state.get("expected_state_hash")
        == grounding.get("expected_state_hash")
        and final_state.get("verification_passed") is True
    )


def _workspace_recovery_is_valid(binding: Mapping[str, object]) -> bool:
    recovery = _mapping_or_empty(binding.get("recovery"))
    if recovery.get("declared") is not True:
        return recovery.get("verified") is False
    if recovery.get("verified") is not True:
        return False
    return (
        isinstance(recovery.get("initial_failure_branch_id"), str)
        and isinstance(recovery.get("fallback_branch_id"), str)
        and recovery.get("initial_failure_branch_id")
        != recovery.get("fallback_branch_id")
        and recovery.get("initial_failure_cause")
        in {"tool_runtime_error", "tool_schema_error"}
        and _is_hash(recovery.get("initial_action_hash"))
        and _is_hash(recovery.get("fallback_action_hash"))
        and _is_hash(recovery.get("fallback_observation_hash"))
    )


def _workspace_source_is_valid(manifest: Mapping[str, object]) -> bool:
    orchestration = manifest.get("orchestration")
    source_policy_hashes = manifest.get("source_policy_hashes")
    if (
        not isinstance(source_policy_hashes, list)
        or not source_policy_hashes
        or not all(_is_hash(value) for value in source_policy_hashes)
    ):
        return False
    # Synchronous runs have no orchestration status; their complete manifest
    # and content-addressed source policy hashes are the source gate.  When an
    # orchestration record is present it must independently prove completion.
    if orchestration is None:
        return True
    return (
        isinstance(orchestration, Mapping)
        and orchestration.get("status") == "completed"
        and orchestration.get("completeness") == "complete"
        and orchestration.get("release_eligible") is not False
    )


def _workspace_mutation_is_valid(
    manifest: Mapping[str, object],
    samples: Sequence[Mapping[str, object]],
) -> bool:
    run_profile = _mapping_or_empty(manifest.get("run_profile"))
    if _mapping_or_empty(run_profile.get("mutation_admission")).get("mode") != "enforce":
        return False
    for sample in samples:
        task = _mapping_or_empty(sample.get("task"))
        difficulty = _mapping_or_empty(task.get("difficulty"))
        state_changes = difficulty.get("state_changes", 0)
        mutation = sample.get("mutation_admission")
        if state_changes:
            if not isinstance(mutation, Mapping) or mutation.get("mode") != "enforce":
                return False
            if _status_from_record(mutation) not in _PASS_STATUSES:
                return False
    return True


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _workspace_machine_gates(
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
    evaluation_status = _status_from_record(
        _mapping_or_empty(evaluation_report.get("decision"))
    )
    promotion_status = _mapping_or_empty(profile_decision_report.get("decisions"))
    promotion = _mapping_or_empty(promotion_status.get("profile_promotion"))
    quality_decision = _mapping_or_empty(
        promotion_status.get("mvp_quality_floor")
    )
    release_decision = _mapping_or_empty(release_report.get("decisions")).get(
        "dataset_release"
    )
    release_status = _status_from_record(_mapping_or_empty(release_decision))
    reasons = list(profile_reasons)
    return {
        "contract": _machine_gate(
            "insufficient_evidence" if reasons else "passed",
            reasons=reasons or ["exact Workspace profile and plan contract selected"],
        ),
        "execution": _machine_gate(
            "passed" if samples else "insufficient_evidence"
        ),
        "verification": _machine_gate(
            "passed"
            if all(
                _status_from_record(_mapping_or_empty(sample.get("verification")))
                == "passed"
                for sample in samples
            )
            else "insufficient_evidence"
        ),
        "grounding": _machine_gate(
            "passed"
            if all(
                _workspace_sample_grounding_is_valid(sample)
                for sample in samples
            )
            else "insufficient_evidence"
        ),
        "quality": _machine_gate(
            _status_from_record(quality_decision) or "insufficient_evidence"
        ),
        "provenance": _machine_gate(
            "passed"
            if all(
                _mapping_or_empty(sample.get("workspace_evidence")).get(
                    "domain_pack_reference"
                )
                for sample in samples
            )
            else "insufficient_evidence"
        ),
        "source": _machine_gate(
            "passed"
            if _workspace_source_is_valid(manifest)
            else "insufficient_evidence"
        ),
        "mutation": _machine_gate(
            "passed"
            if _workspace_mutation_is_valid(manifest, samples)
            else "insufficient_evidence"
        ),
        "coverage": _machine_gate(
            "passed"
            if _mapping_or_empty(manifest.get("artifacts")).get("coverage_plan")
            and _mapping_or_empty(manifest.get("artifacts")).get(
                "coverage_evidence"
            )
            and _mapping_or_empty(coverage_evidence.get("fulfillment")).get(
                "status"
            )
            == "fulfilled"
            else "insufficient_evidence"
        ),
        "held_out": _machine_gate(evaluation_status or "insufficient_evidence"),
        "profile_promotion": _machine_gate(
            _status_from_record(promotion) or "insufficient_evidence"
        ),
        "dataset_release": _machine_gate(
            release_status or "insufficient_evidence"
        ),
        "artifact_integrity": _machine_gate(
            _status_from_record(pack_verification) or "insufficient_evidence"
        ),
    }


def _validate_workspace_samples(
    samples: Sequence[Mapping[str, object]],
    plan: DomainPlan,
) -> None:
    if len(samples) < 5:
        raise _WorkspaceQualificationInsufficiency(
            "workspace_capability_evidence_incomplete",
            "Workspace Release Candidate requires at least five accepted samples",
        )
    expected_pack = plan.domain_pack_reference.to_record()
    expected_runtime = plan.runtime_contract.to_record()
    expected_capability_records = {
        canonical_domain_pack_json(reference.to_record())
        for reference in plan.capability_references
    }
    plan_ids: set[tuple[object, object]] = set()
    recovery_count = 0
    for sample in samples:
        binding = _mapping_or_empty(sample.get("workspace_evidence"))
        if binding.get("schema_version") != "workspace_evidence_binding_v1":
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace sample evidence binding has an unsupported schema",
            )
        if binding.get("domain_pack_reference") != expected_pack:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_identity_mismatch",
                "Workspace sample Domain Pack reference does not match the plan",
            )
        if binding.get("runtime_contract") != expected_runtime:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_identity_mismatch",
                "Workspace sample runtime contract does not match the plan",
            )
        plan_binding = _mapping_or_empty(binding.get("plan"))
        plan_ids.add((plan_binding.get("plan_id"), plan_binding.get("plan_hash")))
        if not plan_binding or plan_binding.get("plan_id") != plan.plan_id or plan_binding.get("plan_hash") != plan.plan_hash:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_identity_mismatch",
                "Workspace sample plan binding does not match the exact plan",
            )
        capability_refs = binding.get("capability_references")
        expected_capability_records_sorted = sorted(
            canonical_domain_pack_json(reference.to_record())
            for reference in plan.capability_references
        )
        if (
            not isinstance(capability_refs, list)
            or any(not isinstance(item, Mapping) for item in capability_refs)
            or sorted(canonical_domain_pack_json(item) for item in capability_refs)
            != expected_capability_records_sorted
        ):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace samples do not carry the complete canonical capability catalog",
            )
        component_contracts = binding.get("component_contracts")
        expected_component_records = sorted(
            canonical_domain_pack_json(contract.to_record())
            for contract in plan.component_contracts
        )
        if (
            not isinstance(component_contracts, list)
            or any(not isinstance(item, Mapping) for item in component_contracts)
            or sorted(canonical_domain_pack_json(item) for item in component_contracts)
            != expected_component_records
        ):
            raise _WorkspaceQualificationInsufficiency(
                "evidence_identity_mismatch",
                "Workspace samples do not carry the exact component contract set",
            )
        if not _workspace_sample_semantics_are_valid(sample, binding):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace accepted sample execution does not match its bound task and verifier contract",
            )
        task_refs = binding.get("task_capability_references")
        assignment_refs = binding.get("assignment_capability_references")
        if (
            not isinstance(task_refs, list)
            or not task_refs
            or task_refs != assignment_refs
            or any(not isinstance(item, Mapping) for item in task_refs)
            or not set(canonical_domain_pack_json(item) for item in task_refs).issubset(
                expected_capability_records
            )
        ):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace assignment capability references are missing or mismatched",
            )
        if not _workspace_sample_binding_is_structurally_valid(
            sample,
            binding,
            plan=plan,
        ):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_capability_evidence_incomplete",
                "Workspace sample task, assignment, grounding, verification, or recovery bindings are incomplete",
            )
        recovery = _mapping_or_empty(binding.get("recovery"))
        if recovery.get("verified") is True:
            recovery_count += 1
        mutation = _mapping_or_empty(sample.get("mutation_admission"))
        state_changes = _mapping_or_empty(
            _mapping_or_empty(sample.get("task")).get("difficulty")
        ).get("state_changes", 0)
        if state_changes and (
            mutation.get("mode") != "enforce"
            or _status_from_record(mutation) not in _PASS_STATUSES
        ):
            raise _WorkspaceQualificationInsufficiency(
                "workspace_mutation_admission_incomplete",
                "Workspace state-changing evidence was not admitted and passed in enforce mode",
            )
    if len(plan_ids) != 1:
        raise _WorkspaceQualificationInsufficiency(
            "evidence_identity_mismatch",
            "Workspace accepted samples contain more than one plan identity",
        )
    if recovery_count < 1:
        raise _WorkspaceQualificationInsufficiency(
            "workspace_capability_evidence_incomplete",
            "Workspace release evidence contains no independently verified recovery",
        )


def _workspace_evidence_graph(
    *,
    base_dir: Path,
    artifacts: Mapping[str, object],
    manifest: Mapping[str, object],
    audit_path: Path,
) -> tuple[dict[str, object], ...]:
    nodes: list[dict[str, object]] = []
    for key, raw in sorted(artifacts.items()):
        if not isinstance(raw, Mapping):
            continue
        path_value = raw.get("path")
        if not isinstance(path_value, str):
            continue
        path = base_dir / path_value
        if not path.exists():
            raise _WorkspaceQualificationInsufficiency(
                "evidence_missing",
                f"release-pack artifact is missing: {key}",
            )
        digest = _hash_file_if_readable(path)
        if digest is None:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_malformed",
                f"release-pack artifact is unreadable: {key}",
            )
        schema = _schema_from_artifact(path, key)
        nodes.append(
            {
                "artifact_id": "release_" + _safe_evidence_id(key),
                "artifact_schema_version": schema,
                "content_hash": digest[0],
                "byte_count": digest[1],
                "status": "active",
            }
        )
    audit_digest = _hash_file_if_readable(audit_path)
    if audit_digest is None:
        raise _WorkspaceQualificationInsufficiency(
            "evidence_malformed",
            "release-quality audit is unreadable",
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
    manifest_artifacts = _mapping_or_empty(manifest.get("artifacts"))
    for key in ("coverage_plan", "coverage_evidence"):
        raw_path = manifest_artifacts.get(key)
        if not isinstance(raw_path, str):
            continue
        path = base_dir / raw_path
        digest = _hash_file_if_readable(path)
        if digest is None:
            raise _WorkspaceQualificationInsufficiency(
                "evidence_missing",
                f"Workspace coverage artifact is missing: {key}",
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


def _load_pack_artifact_json(
    base_dir: Path,
    artifacts: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    raw = _mapping_or_empty(artifacts.get(key))
    path = base_dir / _text(raw.get("path"))
    return _load_json_mapping(path)


def _load_manifest_artifact_json(
    base_dir: Path,
    artifacts: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    raw_path = artifacts.get(key)
    if not isinstance(raw_path, str):
        return {}
    return _load_json_mapping(base_dir / raw_path)


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("JSON artifact must contain an object")
    return value


def _load_jsonl(path: Path) -> list[Mapping[str, object]]:
    records: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError("JSONL artifact contains a non-object record")
        records.append(value)
    return records


def _schema_from_artifact(path: Path, key: str) -> str:
    if path.suffix == ".json":
        try:
            value = _load_json_mapping(path)
            schema = value.get("schema_version")
            if isinstance(schema, str) and schema:
                return schema
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return "release_" + _safe_evidence_id(key) + "_v1"


def _hash_file_if_readable(path: Path) -> tuple[str, int] | None:
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return "sha256:" + hashlib.sha256(content).hexdigest(), len(content)


def _workspace_profile(run_profile: Mapping[str, object]) -> dict[str, object]:
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
    return {key: run_profile[key] for key in fields if key in run_profile}


def _qualification_profile(run_profile: Mapping[str, object]) -> dict[str, object]:
    return _workspace_profile(run_profile)


def _safe_evidence_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.:-]+", "_", value.lower()).strip("_")
    return normalized or "evidence"


def _record_or_to_record(value: object) -> dict[str, object]:
    if hasattr(value, "to_record"):
        result = value.to_record()
        if isinstance(result, Mapping):
            return dict(result)
    if isinstance(value, Mapping):
        return dict(value)
    raise QualificationContractError("evidence_malformed")


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise QualificationContractError("qualification_binding_malformed")
    return value


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise QualificationContractError("qualification_binding_malformed")
    if any(not isinstance(item, Mapping) for item in value):
        raise QualificationContractError("qualification_binding_malformed")
    return list(value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise QualificationContractError("qualification_binding_malformed")
    return value


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise QualificationContractError("qualification_binding_malformed")
    return value


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise QualificationContractError("qualification_binding_malformed")


def _require_hash(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise QualificationContractError("qualification_binding_malformed")


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _number_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _capability_sort_key(item: DomainCapabilityReference) -> tuple[str, str, str]:
    return (
        item.domain_pack_id,
        item.capability_key,
        item.capability_contract_version,
    )


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


if __name__ == "__main__":
    raise SystemExit("synthesis.qualification is a library module")
