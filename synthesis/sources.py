from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from synthesis.contracts import (
    ContractValidationError,
    validate_fetched_source_request_record,
    validate_fetched_source_result_record,
    validate_license_policy_decision,
    validate_network_policy_record,
    validate_sandbox_policy_record,
    validate_source_event_record,
    validate_source_record,
)
from synthesis.environments import (
    ContactFollowupRecord,
    ContactRecord,
    ContactsEnvironmentInput,
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


@dataclass(frozen=True)
class FetchedSourceRequest:
    url: str
    allowed_hosts: tuple[str, ...]
    request_budget: int
    timeout_seconds: float
    max_bytes: int
    expected_content_type: str
    license_label: str
    require_source_audit: bool

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "fetched_source_request_v1",
            "url": self.url,
            "allowed_hosts": list(self.allowed_hosts),
            "request_budget": self.request_budget,
            "timeout_seconds": self.timeout_seconds,
            "max_bytes": self.max_bytes,
            "expected_content_type": self.expected_content_type,
            "license_label": self.license_label,
            "require_source_audit": self.require_source_audit,
        }


@dataclass(frozen=True)
class FetchedSourceResult:
    source_id: str
    origin_alias: str
    retrieval_timestamp: str
    content_hash: str
    content_type: str
    byte_count: int
    policy_outcome: str

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "fetched_source_result_v1",
            "source_id": self.source_id,
            "origin_alias": self.origin_alias,
            "retrieval_timestamp": self.retrieval_timestamp,
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "byte_count": self.byte_count,
            "policy_outcome": self.policy_outcome,
        }


@dataclass(frozen=True)
class NetworkContactsSourceInput:
    source_bundle: SourceBundle
    fetch_result: FetchedSourceResult
    environment_input: ContactsEnvironmentInput
    events: list[dict[str, object]]


@dataclass(frozen=True)
class ProfileLocalContactsSourceRequest:
    source_id: str
    path: Path
    license_label: str
    max_bytes: int

    @classmethod
    def from_run_profile_source(cls, source: object) -> "ProfileLocalContactsSourceRequest":
        return cls(
            source_id=str(getattr(source, "source_id")),
            path=Path(getattr(source, "resolved_path")),
            license_label=str(getattr(source, "license_label")),
            max_bytes=int(getattr(source, "max_bytes")),
        )


@dataclass(frozen=True)
class ProfileLocalContactsSourceInput:
    source_bundle: SourceBundle
    environment_input: ContactsEnvironmentInput
    events: list[dict[str, object]]
    source_summary: dict[str, object]


@dataclass(frozen=True)
class ProfileLocalSourceAdmission:
    source_bundle: SourceBundle
    content: bytes
    events: list[dict[str, object]]
    source_summary: dict[str, object]


class HttpResponse(Protocol):
    status_code: int
    headers: dict[str, str]
    content: bytes


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float,
        follow_redirects: bool,
    ) -> HttpResponse:
        ...


class SourcePolicyError(RuntimeError):
    def __init__(self, result: SourceGovernanceResult) -> None:
        causes = ", ".join(result.rejection_causes) or "unknown"
        message_causes = causes.replace("_", " ")
        super().__init__(f"source policy rejected: {message_causes}")
        self.result = result


class ControlledSourceFetchError(RuntimeError):
    def __init__(self, message: str, *, events: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.events = events


class _HttpxClientAdapter:
    def get(
        self,
        url: str,
        *,
        timeout: float,
        follow_redirects: bool,
    ) -> HttpResponse:
        import httpx

        with httpx.Client(follow_redirects=follow_redirects, timeout=timeout) as client:
            return client.get(url)


def build_network_contacts_source_input(
    request: FetchedSourceRequest,
    *,
    http_client: HttpClient | None = None,
    retrieval_timestamp: str = "1970-01-01T00:00:00Z",
) -> NetworkContactsSourceInput:
    try:
        validate_fetched_source_request_record(request.export())
    except ContractValidationError as exc:
        raise ControlledSourceFetchError(
            f"fetch request rejected: {exc}",
            events=[],
        ) from exc

    source_id = _external_source_id(request.url)
    origin_alias = _origin_alias(request.url)
    no_payload_hash = _bytes_content_hash(b"")
    events: list[dict[str, object]] = []

    if request.request_budget < 1:
        bundle = _network_source_bundle(
            request=request,
            source_id=source_id,
            content_hash=no_payload_hash,
            retrieval_timestamp=retrieval_timestamp,
            license_outcome="rejected",
            license_cause="request_budget_exceeded",
        )
        policy_hash = source_policy_hash(bundle)
        events.append(
            _sanitized_source_event(
                event_type="fetch_rejected",
                source_id=source_id,
                source_kind="external",
                origin_alias=origin_alias,
                content_hash=no_payload_hash,
                license_label=request.license_label,
                license_outcome="rejected",
                source_policy_hash=policy_hash,
                policy_outcome="rejected",
                rejection_causes=["request_budget_exceeded"],
            )
        )
        raise ControlledSourceFetchError("fetch rejected: request budget exceeded", events=events)

    provisional_bundle = _network_source_bundle(
        request=request,
        source_id=source_id,
        content_hash=no_payload_hash,
        retrieval_timestamp=retrieval_timestamp,
        license_outcome="allowed",
    )
    provisional_policy_hash = source_policy_hash(provisional_bundle)
    events.append(
        _sanitized_source_event(
            event_type="fetch_attempt",
            source_id=source_id,
            source_kind="external",
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            license_label=request.license_label,
            license_outcome="allowed",
            source_policy_hash=provisional_policy_hash,
            policy_outcome="rejected",
            rejection_causes=[],
        )
    )

    client = http_client or _HttpxClientAdapter()
    try:
        response = client.get(
            request.url,
            timeout=request.timeout_seconds,
            follow_redirects=False,
        )
    except Exception as exc:
        _append_fetch_rejection_event(
            events,
            request=request,
            source_id=source_id,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="network_request_failed",
            retrieval_timestamp=retrieval_timestamp,
        )
        raise ControlledSourceFetchError("fetch rejected: network request failed", events=events) from exc

    if 300 <= int(response.status_code) < 400:
        _append_fetch_rejection_event(
            events,
            request=request,
            source_id=source_id,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="redirect_rejected",
            retrieval_timestamp=retrieval_timestamp,
        )
        raise ControlledSourceFetchError("fetch rejected: redirect rejected", events=events)
    if int(response.status_code) != 200:
        _append_fetch_rejection_event(
            events,
            request=request,
            source_id=source_id,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="http_status_rejected",
            retrieval_timestamp=retrieval_timestamp,
        )
        raise ControlledSourceFetchError("fetch rejected: http status rejected", events=events)

    content = bytes(response.content)
    if len(content) > request.max_bytes:
        _append_fetch_rejection_event(
            events,
            request=request,
            source_id=source_id,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="payload_too_large",
            retrieval_timestamp=retrieval_timestamp,
        )
        raise ControlledSourceFetchError("fetch rejected: payload too large", events=events)

    content_type = _normalized_content_type(response.headers.get("content-type", ""))
    if content_type != request.expected_content_type:
        _append_fetch_rejection_event(
            events,
            request=request,
            source_id=source_id,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="unsupported_content_type",
            retrieval_timestamp=retrieval_timestamp,
        )
        raise ControlledSourceFetchError("fetch rejected: unsupported content type", events=events)

    content_hash = _bytes_content_hash(content)
    source_bundle = _network_source_bundle(
        request=request,
        source_id=source_id,
        content_hash=content_hash,
        retrieval_timestamp=retrieval_timestamp,
        license_outcome="allowed",
    )
    policy_hash = source_policy_hash(source_bundle)
    fetch_result = FetchedSourceResult(
        source_id=source_id,
        origin_alias=origin_alias,
        retrieval_timestamp=retrieval_timestamp,
        content_hash=content_hash,
        content_type=content_type,
        byte_count=len(content),
        policy_outcome="allowed",
    )
    validate_fetched_source_result_record(fetch_result.export())
    environment_input = contacts_environment_input_from_payload(
        content,
        source_bundle_id=source_bundle.bundle_id,
        source_policy_hash=policy_hash,
    )
    events.append(
        _sanitized_source_event(
            event_type="fetch_accepted",
            source_id=source_id,
            source_kind="external",
            origin_alias=origin_alias,
            content_hash=content_hash,
            license_label=request.license_label,
            license_outcome="allowed",
            source_policy_hash=policy_hash,
            policy_outcome="allowed",
            rejection_causes=[],
        )
    )
    return NetworkContactsSourceInput(
        source_bundle=source_bundle,
        fetch_result=fetch_result,
        environment_input=environment_input,
        events=events,
    )


def build_profile_local_contacts_source_input(
    request: ProfileLocalContactsSourceRequest,
) -> ProfileLocalContactsSourceInput:
    admission = admit_profile_local_json_source(
        source_id=request.source_id,
        path=request.path,
        license_label=request.license_label,
        max_bytes=request.max_bytes,
        source_summary_kind="local_contacts_json",
    )
    environment_input = contacts_environment_input_from_payload(
        admission.content,
        source_bundle_id=admission.source_bundle.bundle_id,
        source_policy_hash=str(admission.source_summary["source_policy_hash"]),
    )
    return ProfileLocalContactsSourceInput(
        source_bundle=admission.source_bundle,
        environment_input=environment_input,
        events=admission.events,
        source_summary=admission.source_summary,
    )


def admit_profile_local_json_source(
    *,
    source_id: str,
    path: Path,
    license_label: str,
    max_bytes: int,
    source_summary_kind: str,
) -> ProfileLocalSourceAdmission:
    request = ProfileLocalContactsSourceRequest(
        source_id=source_id,
        path=path,
        license_label=license_label,
        max_bytes=max_bytes,
    )
    source_id = request.source_id
    origin_reference = _profile_local_origin_reference(source_id)
    origin_alias = _origin_alias(origin_reference)
    no_payload_hash = _bytes_content_hash(b"")
    events: list[dict[str, object]] = []

    try:
        with request.path.open("rb") as source_file:
            content = source_file.read(request.max_bytes + 1)
    except FileNotFoundError:
        _append_local_file_rejection_event(
            events,
            request=request,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="file_not_found",
        )
        raise ControlledSourceFetchError(
            "local source rejected: file not found",
            events=events,
        ) from None

    if len(content) > request.max_bytes:
        _append_local_file_rejection_event(
            events,
            request=request,
            origin_alias=origin_alias,
            content_hash=no_payload_hash,
            cause="payload_too_large",
        )
        raise ControlledSourceFetchError(
            "local source rejected: payload too large",
            events=events,
        )

    content_hash = _bytes_content_hash(content)
    source_bundle = _local_file_source_bundle(
        request=request,
        content_hash=content_hash,
        license_outcome="allowed",
    )
    source_result = validate_source_bundle(source_bundle)
    events.append(
        _sanitized_source_event(
            event_type="fetch_accepted",
            source_id=source_id,
            source_kind="local_file",
            origin_alias=origin_alias,
            content_hash=content_hash,
            license_label=request.license_label,
            license_outcome="allowed",
            source_policy_hash=source_result.source_policy_hash,
            policy_outcome="allowed",
            rejection_causes=[],
        )
    )
    return ProfileLocalSourceAdmission(
        source_bundle=source_bundle,
        content=content,
        events=events,
        source_summary={
            "kind": source_summary_kind,
            "source_id": source_id,
            "content_hash": content_hash,
            "license_label": request.license_label,
            "source_policy_hash": source_result.source_policy_hash,
        },
    )


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


def _network_source_bundle(
    *,
    request: FetchedSourceRequest,
    source_id: str,
    content_hash: str,
    retrieval_timestamp: str,
    license_outcome: str,
    license_cause: str | None = None,
) -> SourceBundle:
    source = SourceRecord(
        source_id=source_id,
        source_kind="external",
        origin_reference=request.url,
        retrieval_timestamp=retrieval_timestamp,
        content_hash=content_hash,
        license_label=request.license_label,
        retention_eligible=license_outcome == "allowed",
        export_eligible=license_outcome == "allowed",
    )
    return SourceBundle(
        bundle_id=f"bundle_{source_id}",
        sources=(source,),
        license_decisions=(
            LicensePolicyDecision(
                source_id=source.source_id,
                license_label=source.license_label,
                outcome=license_outcome,
                cause=license_cause,
            ),
        ),
        network_policy=NetworkPolicy(
            enabled=True,
            allowed_hosts=request.allowed_hosts,
            request_budget=request.request_budget,
            require_source_events=request.require_source_audit,
        ),
        sandbox_policy=SandboxPolicy(
            policy_id="sandbox_network_contacts",
            filesystem_isolation="artifact_subdir",
            generated_code_allowed=False,
            secret_redaction=True,
        ),
    )


def _local_file_source_bundle(
    *,
    request: ProfileLocalContactsSourceRequest,
    content_hash: str,
    license_outcome: str,
    license_cause: str | None = None,
) -> SourceBundle:
    source = SourceRecord(
        source_id=request.source_id,
        source_kind="local_file",
        origin_reference=_profile_local_origin_reference(request.source_id),
        content_hash=content_hash,
        license_label=request.license_label,
        retention_eligible=license_outcome == "allowed",
        export_eligible=license_outcome == "allowed",
    )
    return SourceBundle(
        bundle_id=f"bundle_{request.source_id}",
        sources=(source,),
        license_decisions=(
            LicensePolicyDecision(
                source_id=source.source_id,
                license_label=source.license_label,
                outcome=license_outcome,
                cause=license_cause,
            ),
        ),
        network_policy=NetworkPolicy(
            enabled=False,
            allowed_hosts=(),
            request_budget=0,
            require_source_events=True,
        ),
        sandbox_policy=SandboxPolicy(
            policy_id="sandbox_profile_local_contacts",
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
        if source.source_kind in {"external", "local_file"} and decision is None:
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
    governed_file_sources = [
        source for source in bundle.sources if source.source_kind in {"external", "local_file"}
    ]
    if governed_file_sources:
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


def _append_fetch_rejection_event(
    events: list[dict[str, object]],
    *,
    request: FetchedSourceRequest,
    source_id: str,
    origin_alias: str,
    content_hash: str,
    cause: str,
    retrieval_timestamp: str,
) -> None:
    bundle = _network_source_bundle(
        request=request,
        source_id=source_id,
        content_hash=content_hash,
        retrieval_timestamp=retrieval_timestamp,
        license_outcome="rejected",
        license_cause=cause,
    )
    events.append(
        _sanitized_source_event(
            event_type="fetch_rejected",
            source_id=source_id,
            source_kind="external",
            origin_alias=origin_alias,
            content_hash=content_hash,
            license_label=request.license_label,
            license_outcome="rejected",
            source_policy_hash=source_policy_hash(bundle),
            policy_outcome="rejected",
            rejection_causes=[cause],
        )
    )


def _append_local_file_rejection_event(
    events: list[dict[str, object]],
    *,
    request: ProfileLocalContactsSourceRequest,
    origin_alias: str,
    content_hash: str,
    cause: str,
) -> None:
    bundle = _local_file_source_bundle(
        request=request,
        content_hash=content_hash,
        license_outcome="rejected",
        license_cause=cause,
    )
    events.append(
        _sanitized_source_event(
            event_type="fetch_rejected",
            source_id=request.source_id,
            source_kind="local_file",
            origin_alias=origin_alias,
            content_hash=content_hash,
            license_label=request.license_label,
            license_outcome="rejected",
            source_policy_hash=source_policy_hash(bundle),
            policy_outcome="rejected",
            rejection_causes=[cause],
        )
    )


def source_environment_admission_event(
    *,
    event_type: str,
    source_bundle: SourceBundle,
    source_policy_hash: str,
    rejection_causes: list[str],
) -> dict[str, object]:
    source = source_bundle.sources[0]
    decision = source_bundle.license_decisions[0]
    return _sanitized_source_event(
        event_type=event_type,
        source_id=source.source_id,
        source_kind=source.source_kind,
        origin_alias=_origin_alias(source.origin_reference),
        content_hash=source.content_hash,
        license_label=source.license_label,
        license_outcome=decision.outcome,
        source_policy_hash=source_policy_hash,
        policy_outcome="rejected" if rejection_causes else "allowed",
        rejection_causes=rejection_causes,
    )


def _sanitized_source_event(
    *,
    event_type: str,
    source_id: str,
    source_kind: str,
    origin_alias: str,
    content_hash: str,
    license_label: str,
    license_outcome: str,
    source_policy_hash: str,
    policy_outcome: str,
    rejection_causes: list[str],
) -> dict[str, object]:
    event = {
        "schema_version": "source_event_v1",
        "event_type": event_type,
        "source_id": source_id,
        "source_kind": source_kind,
        "policy_outcome": policy_outcome,
        "origin_alias": origin_alias,
        "content_hash": content_hash,
        "license_label": license_label,
        "license_outcome": license_outcome,
        "source_policy_hash": source_policy_hash,
        "rejection_causes": list(dict.fromkeys(rejection_causes)),
    }
    validate_source_event_record(event)
    return event


def contacts_environment_input_from_payload(
    payload: bytes,
    *,
    source_bundle_id: str,
    source_policy_hash: str,
) -> ContactsEnvironmentInput:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ContactsEnvironmentInput(
            contacts=(),
            followups=(),
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
            validation_errors=(f"payload_json_invalid:{type(exc).__name__}",),
        )

    if not isinstance(document, dict):
        return ContactsEnvironmentInput(
            contacts=(),
            followups=(),
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
            validation_errors=("payload_must_be_object",),
        )

    contacts = tuple(
        ContactRecord(
            name=str(contact.get("name", "")) if isinstance(contact, dict) else "",
            email=str(contact.get("email", "")) if isinstance(contact, dict) else "",
        )
        for contact in _list_or_empty(document.get("contacts"))
    )
    followups = tuple(
        ContactFollowupRecord(
            name=str(followup.get("name", "")) if isinstance(followup, dict) else "",
            note=str(followup.get("note", "")) if isinstance(followup, dict) else "",
            created_at=(
                str(followup.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(followup, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for followup in _list_or_empty(document.get("followups"))
    )
    validation_errors = []
    if "contacts" not in document:
        validation_errors.append("contacts_missing")
    elif not isinstance(document.get("contacts"), list):
        validation_errors.append("contacts_not_list")
    if "followups" in document and not isinstance(document.get("followups"), list):
        validation_errors.append("followups_not_list")

    return ContactsEnvironmentInput(
        contacts=contacts,
        followups=followups,
        source_bundle_id=source_bundle_id,
        source_policy_hash=source_policy_hash,
        validation_errors=tuple(validation_errors),
    )


def _list_or_empty(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _origin_alias(origin_reference: str) -> str:
    parsed = urlparse(origin_reference)
    if parsed.hostname:
        return parsed.hostname
    if parsed.netloc:
        return parsed.netloc
    if parsed.scheme:
        return parsed.scheme
    return "local"


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _bytes_content_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _external_source_id(url: str) -> str:
    return "source_external_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _profile_local_origin_reference(source_id: str) -> str:
    return f"profile_local_file:{source_id}"


def _normalized_content_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _unique(values) -> list[str]:
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text not in unique:
            unique.append(text)
    return unique
