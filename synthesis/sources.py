from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlparse

from synthesis.contracts import (
    validate_license_policy_decision,
    validate_network_policy_record,
    validate_sandbox_policy_record,
    validate_source_event_record,
    validate_source_record,
)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_kind: str
    origin_reference: str
    content_hash: str
    license_label: str
    retention_eligible: bool
    export_eligible: bool
    retrieval_timestamp: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "source_record_v1",
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "origin_reference": self.origin_reference,
            "retrieval_timestamp": self.retrieval_timestamp,
            "content_hash": self.content_hash,
            "license_label": self.license_label,
            "retention_eligible": self.retention_eligible,
            "export_eligible": self.export_eligible,
        }


@dataclass(frozen=True)
class LicensePolicyDecision:
    source_id: str
    license_label: str
    outcome: str
    cause: str | None = None
    reviewed_by: str = "local_source_policy"

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": "license_policy_decision_v1",
            "source_id": self.source_id,
            "license_label": self.license_label,
            "outcome": self.outcome,
            "reviewed_by": self.reviewed_by,
        }
        if self.cause is not None:
            record["cause"] = self.cause
        return record


@dataclass(frozen=True)
class NetworkPolicy:
    enabled: bool
    allowed_hosts: tuple[str, ...]
    request_budget: int
    require_source_events: bool

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "network_policy_v1",
            "enabled": self.enabled,
            "allowed_hosts": list(self.allowed_hosts),
            "request_budget": self.request_budget,
            "require_source_events": self.require_source_events,
        }


@dataclass(frozen=True)
class SandboxPolicy:
    policy_id: str
    filesystem_isolation: str
    generated_code_allowed: bool
    secret_redaction: bool

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "sandbox_policy_v1",
            "policy_id": self.policy_id,
            "filesystem_isolation": self.filesystem_isolation,
            "generated_code_allowed": self.generated_code_allowed,
            "secret_redaction": self.secret_redaction,
        }


@dataclass(frozen=True)
class SourceBundle:
    bundle_id: str
    sources: tuple[SourceRecord, ...]
    license_decisions: tuple[LicensePolicyDecision, ...]
    network_policy: NetworkPolicy
    sandbox_policy: SandboxPolicy

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "source_bundle_v1",
            "bundle_id": self.bundle_id,
            "sources": [source.export() for source in self.sources],
            "license_decisions": [decision.export() for decision in self.license_decisions],
            "network_policy": self.network_policy.export(),
            "sandbox_policy": self.sandbox_policy.export(),
        }


@dataclass(frozen=True)
class SourceGovernanceResult:
    source_bundle_id: str
    source_policy_hash: str
    policy_outcome: str
    provenance: dict[str, object]
    events: list[dict[str, object]]
    rejection_causes: tuple[str, ...] = ()


class SourcePolicyError(RuntimeError):
    def __init__(self, result: SourceGovernanceResult) -> None:
        causes = ", ".join(result.rejection_causes) or "unknown"
        message_causes = causes.replace("_", " ")
        super().__init__(f"source policy rejected: {message_causes}")
        self.result = result


def build_fixture_source_bundle() -> SourceBundle:
    source = SourceRecord(
        source_id="source_fixture_contacts",
        source_kind="fixture",
        origin_reference="fixture://contacts",
        content_hash=_content_hash("contacts fixture v2"),
        license_label="fixture_internal",
        retention_eligible=True,
        export_eligible=True,
    )
    return SourceBundle(
        bundle_id="bundle_contacts_fixture",
        sources=(source,),
        license_decisions=(
            LicensePolicyDecision(
                source_id=source.source_id,
                license_label=source.license_label,
                outcome="allowed",
            ),
        ),
        network_policy=NetworkPolicy(
            enabled=False,
            allowed_hosts=(),
            request_budget=0,
            require_source_events=False,
        ),
        sandbox_policy=SandboxPolicy(
            policy_id="sandbox_fixture_local",
            filesystem_isolation="artifact_subdir",
            generated_code_allowed=False,
            secret_redaction=True,
        ),
    )


def build_external_fixture_source_bundle(*, network_enabled: bool) -> SourceBundle:
    source = SourceRecord(
        source_id="source_external_contacts",
        source_kind="external",
        origin_reference="https://allowed.example.test/contact-fixture.json",
        retrieval_timestamp="1970-01-01T00:00:00Z",
        content_hash=_content_hash("external contacts fixture"),
        license_label="cc-by-4.0",
        retention_eligible=True,
        export_eligible=True,
    )
    return SourceBundle(
        bundle_id=(
            "bundle_allowed_external_fixture"
            if network_enabled
            else "bundle_rejected_external_fixture"
        ),
        sources=(source,),
        license_decisions=(
            LicensePolicyDecision(
                source_id=source.source_id,
                license_label=source.license_label,
                outcome="allowed",
            ),
        ),
        network_policy=NetworkPolicy(
            enabled=network_enabled,
            allowed_hosts=("allowed.example.test",),
            request_budget=1 if network_enabled else 0,
            require_source_events=True,
        ),
        sandbox_policy=SandboxPolicy(
            policy_id="sandbox_external_fixture",
            filesystem_isolation="artifact_subdir",
            generated_code_allowed=False,
            secret_redaction=True,
        ),
    )


def validate_source_bundle(bundle: SourceBundle) -> SourceGovernanceResult:
    if not bundle.sources:
        raise ValueError("source bundle must contain at least one source")
    for source in bundle.sources:
        validate_source_record(source.export())
    for decision in bundle.license_decisions:
        validate_license_policy_decision(decision.export())
    validate_network_policy_record(bundle.network_policy.export())
    validate_sandbox_policy_record(bundle.sandbox_policy.export())

    decisions = {decision.source_id: decision for decision in bundle.license_decisions}
    rejection_causes: list[str] = []
    for source in bundle.sources:
        decision = decisions.get(source.source_id)
        if source.source_kind == "external" and decision is None:
            rejection_causes.append("license_decision_missing")
            continue
        if decision is None:
            continue
        if decision.outcome != "allowed":
            rejection_causes.append(decision.cause or f"license_{decision.outcome}")
        if decision.license_label != source.license_label:
            rejection_causes.append("license_label_mismatch")
        if not source.retention_eligible:
            rejection_causes.append("retention_not_allowed")
        if not source.export_eligible:
            rejection_causes.append("export_not_allowed")

    external_sources = [source for source in bundle.sources if source.source_kind == "external"]
    if external_sources:
        rejection_causes.extend(_network_rejection_causes(bundle, external_sources))
        rejection_causes.extend(_sandbox_rejection_causes(bundle))

    policy_hash = source_policy_hash(bundle)
    outcome = "rejected" if rejection_causes else "allowed"
    provenance = _provenance(bundle, policy_hash, outcome, rejection_causes)
    events = [
        _source_event(
            source=source,
            bundle=bundle,
            policy_hash=policy_hash,
            outcome=outcome,
            rejection_causes=rejection_causes,
        )
        for source in bundle.sources
    ]
    for event in events:
        validate_source_event_record(event)
    result = SourceGovernanceResult(
        source_bundle_id=bundle.bundle_id,
        source_policy_hash=policy_hash,
        policy_outcome=outcome,
        provenance=provenance,
        events=events,
        rejection_causes=tuple(dict.fromkeys(rejection_causes)),
    )
    if rejection_causes:
        raise SourcePolicyError(result)
    return result


def source_policy_hash(bundle: SourceBundle) -> str:
    canonical = json.dumps(bundle.export(), sort_keys=True, separators=(",", ":"))
    return _content_hash(canonical)


def _network_rejection_causes(
    bundle: SourceBundle,
    external_sources: list[SourceRecord],
) -> list[str]:
    policy = bundle.network_policy
    causes: list[str] = []
    if not policy.enabled:
        causes.append("network_disabled")
    if policy.require_source_events is False:
        causes.append("source_events_required")
    if policy.request_budget < len(external_sources):
        causes.append("request_budget_exceeded")
    allowed_hosts = set(policy.allowed_hosts)
    for source in external_sources:
        host = _origin_alias(source.origin_reference)
        if host not in allowed_hosts:
            causes.append("host_not_allowlisted")
    return causes


def _sandbox_rejection_causes(bundle: SourceBundle) -> list[str]:
    policy = bundle.sandbox_policy
    causes: list[str] = []
    if policy.generated_code_allowed:
        causes.append("generated_code_not_allowed")
    if not policy.secret_redaction:
        causes.append("secret_redaction_required")
    if policy.filesystem_isolation != "artifact_subdir":
        causes.append("filesystem_isolation_required")
    return causes


def _provenance(
    bundle: SourceBundle,
    policy_hash: str,
    outcome: str,
    rejection_causes: list[str],
) -> dict[str, object]:
    license_outcomes = {
        decision.source_id: decision.outcome for decision in bundle.license_decisions
    }
    source_kinds = _unique(source.source_kind for source in bundle.sources)
    external = "external" in source_kinds
    record: dict[str, object] = {
        "source_bundle_id": bundle.bundle_id,
        "source_policy_hash": policy_hash,
        "source_ids": [source.source_id for source in bundle.sources],
        "source_kinds": source_kinds,
        "license_labels": _unique(source.license_label for source in bundle.sources),
        "license_outcomes": _unique(
            license_outcomes.get(source.source_id, "missing")
            for source in bundle.sources
        ),
        "external_source_eligible": bool(external and outcome == "allowed"),
        "retention_eligible": all(source.retention_eligible for source in bundle.sources),
        "export_eligible": all(source.export_eligible for source in bundle.sources),
        "policy_outcome": outcome,
    }
    if rejection_causes:
        record["rejection_causes"] = list(dict.fromkeys(rejection_causes))
    return record


def _source_event(
    *,
    source: SourceRecord,
    bundle: SourceBundle,
    policy_hash: str,
    outcome: str,
    rejection_causes: list[str],
) -> dict[str, object]:
    decision = next(
        (decision for decision in bundle.license_decisions if decision.source_id == source.source_id),
        None,
    )
    event: dict[str, object] = {
        "schema_version": "source_event_v1",
        "event_type": "source_rejected" if outcome == "rejected" else "source_accepted",
        "source_id": source.source_id,
        "source_kind": source.source_kind,
        "policy_outcome": outcome,
        "origin_alias": _origin_alias(source.origin_reference),
        "content_hash": source.content_hash,
        "license_label": source.license_label,
        "license_outcome": decision.outcome if decision else "missing",
        "source_policy_hash": policy_hash,
        "rejection_causes": list(dict.fromkeys(rejection_causes)),
    }
    return event


def _origin_alias(origin_reference: str) -> str:
    parsed = urlparse(origin_reference)
    if parsed.netloc:
        return parsed.netloc
    if parsed.scheme:
        return parsed.scheme
    return "local"


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unique(values) -> list[str]:
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text not in unique:
            unique.append(text)
    return unique
