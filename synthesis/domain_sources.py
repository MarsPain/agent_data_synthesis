from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from synthesis.environments import ContactsEnvironmentInput
from synthesis.mobile_sources import MobileMessagesSourceImporter
from synthesis.sources import (
    ControlledSourceFetchError,
    SourceBundle,
    admit_profile_local_json_source,
    contacts_environment_input_from_payload,
    source_environment_admission_event,
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
