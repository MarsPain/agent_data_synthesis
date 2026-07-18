from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from synthesis.environments import ContactsEnvironmentInput
from synthesis.mobile_sources import MobileMessagesSourceImporter
from synthesis.sources import (
    CONTACTS_FIXTURE_SOURCE_IDENTITY,
    ControlledSourceFetchError,
    FixtureSourceIdentity,
    SourceBundle,
    admit_profile_local_json_source,
    contacts_environment_input_from_payload,
    source_environment_admission_event,
    build_fixture_source_bundle,
)
from synthesis.workspace_sources import WorkspaceTasksSourceImporter


@dataclass(frozen=True)
class ProfileLocalDomainSourceRequest:
    domain_id: str
    kind: str
    source_id: str
    path: Path
    license_label: str
    max_bytes: int


@dataclass(frozen=True)
class DomainSourceImport:
    domain_id: str
    source_kind: str
    source_bundle: SourceBundle
    environment_input: object
    events: list[dict[str, object]]
    source_summary: dict[str, object]


class DomainSourceImporter(Protocol):
    domain_id: str
    source_kind: str

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> object:
        ...


class ContactsSourceImporter:
    domain_id = "contacts_fixture"
    source_kind = "local_contacts_json"

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> ContactsEnvironmentInput:
        return contacts_environment_input_from_payload(
            content,
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
        )


def build_domain_fixture_source_bundle(domain_id: str) -> SourceBundle:
    normalized_domain = "contacts_fixture" if domain_id == "contacts" else domain_id
    identities = {
        "contacts_fixture": CONTACTS_FIXTURE_SOURCE_IDENTITY,
        "mobile_messages_fixture": FixtureSourceIdentity(
            source_id="source_fixture_mobile_messages",
            bundle_id="bundle_mobile_messages_fixture",
            origin_reference="fixture://mobile_messages",
            content_identity="mobile messages fixture v1",
        ),
        "workspace_tasks_fixture": FixtureSourceIdentity(
            source_id="source_fixture_workspace_tasks",
            bundle_id="bundle_workspace_tasks_fixture",
            origin_reference="fixture://workspace_tasks",
            content_identity="workspace tasks fixture v1",
        ),
    }
    identity = identities.get(normalized_domain)
    if identity is None:
        raise ValueError("unsupported fixture source domain")
    return build_fixture_source_bundle(identity)


def resolve_domain_source_importer(
    domain_id: str,
    source_kind: str,
) -> DomainSourceImporter:
    normalized_domain = "contacts_fixture" if domain_id == "contacts" else domain_id
    importers: dict[tuple[str, str], DomainSourceImporter] = {
        ("contacts_fixture", "local_contacts_json"): ContactsSourceImporter(),
        (
            "mobile_messages_fixture",
            "local_mobile_messages_json",
        ): MobileMessagesSourceImporter(),
        (
            "workspace_tasks_fixture",
            "local_workspace_tasks_json",
        ): WorkspaceTasksSourceImporter(),
    }
    importer = importers.get((normalized_domain, source_kind))
    if importer is None:
        raise ValueError(
            f"source kind {source_kind!r} is not supported for domain {domain_id!r}"
        )
    return importer


def build_profile_local_domain_source_input(
    request: ProfileLocalDomainSourceRequest,
    *,
    importer: DomainSourceImporter,
) -> DomainSourceImport:
    request_domain = (
        "contacts_fixture" if request.domain_id == "contacts" else request.domain_id
    )
    if request_domain != importer.domain_id or request.kind != importer.source_kind:
        raise ValueError(
            f"source kind {request.kind!r} is not supported for domain {request.domain_id!r}"
        )
    admission = admit_profile_local_json_source(
        source_id=request.source_id,
        path=request.path,
        license_label=request.license_label,
        max_bytes=request.max_bytes,
        source_summary_kind=request.kind,
    )
    source_policy_hash = str(admission.source_summary["source_policy_hash"])
    try:
        environment_input = importer.build_environment_input(
            admission.content,
            source_bundle_id=admission.source_bundle.bundle_id,
            source_policy_hash=source_policy_hash,
        )
    except Exception as exc:
        events = list(admission.events)
        events.append(
            source_environment_admission_event(
                event_type="environment_source_rejected",
                source_bundle=admission.source_bundle,
                source_policy_hash=source_policy_hash,
                rejection_causes=["environment_source_rejected"],
            )
        )
        raise ControlledSourceFetchError(
            "environment source rejected",
            events=events,
        ) from exc
    return DomainSourceImport(
        domain_id=importer.domain_id,
        source_kind=importer.source_kind,
        source_bundle=admission.source_bundle,
        environment_input=environment_input,
        events=admission.events,
        source_summary=admission.source_summary,
    )
