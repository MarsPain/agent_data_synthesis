from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from synthesis.contacts_coverage import (
    build_contacts_coverage_capacity,
    contacts_coverage_catalog,
    contacts_coverage_version_registry,
    resolve_contacts_coverage_profile,
)
from synthesis.coverage import (
    AdmittedCoverageCapacity,
    CoverageCatalog,
    CoveragePlanValidationError,
    CoverageProfile,
    CoverageVersionRegistry,
)
from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput
from synthesis.mobile_coverage import (
    build_mobile_coverage_capacity,
    mobile_coverage_catalog,
    mobile_coverage_version_registry,
    resolve_mobile_coverage_profile,
)
from synthesis.mobile_environment import (
    MobileMessagesEnvironment,
    MobileMessagesEnvironmentInput,
)
from synthesis.workspace_coverage import (
    build_workspace_coverage_capacity,
    resolve_workspace_coverage_profile,
    workspace_coverage_catalog,
    workspace_coverage_version_registry,
)
from synthesis.workspace_environment import WorkspaceEnvironmentInput
from synthesis.workspace_tasks import WORKSPACE_ITEM_GROUNDING_ARGUMENTS


CoverageProfileResolver = Callable[[str, str], CoverageProfile]
CoverageCapacityResolver = Callable[[object | None], AdmittedCoverageCapacity]


@dataclass(frozen=True)
class DomainCoveragePlanningDefinition:
    catalog: CoverageCatalog
    version_registry: CoverageVersionRegistry
    resolve_profile: CoverageProfileResolver
    resolve_capacity: CoverageCapacityResolver


def resolve_domain_coverage_planning(
    domain_id: str,
) -> DomainCoveragePlanningDefinition:
    try:
        return _DOMAIN_COVERAGE_PLANNING[domain_id]
    except KeyError as exc:
        raise CoveragePlanValidationError(
            f"coverage planning is not available for domain: {domain_id}"
        ) from exc


def _contacts_capacity(
    admitted_environment_input: object | None,
) -> AdmittedCoverageCapacity:
    if admitted_environment_input is None:
        contact_count = len(ContactEnvironment.fixture_contact_names())
    elif isinstance(admitted_environment_input, ContactsEnvironmentInput):
        contact_count = len(admitted_environment_input.contacts)
    else:
        raise CoveragePlanValidationError(
            "contacts coverage capacity requires admitted contacts environment input"
        )
    return build_contacts_coverage_capacity(contact_count=contact_count)


def _mobile_capacity(
    admitted_environment_input: object | None,
) -> AdmittedCoverageCapacity:
    if admitted_environment_input is None:
        message_count = len(
            MobileMessagesEnvironment.fixture_message_binding_values(
                "message_id"
            )
        )
    elif isinstance(admitted_environment_input, MobileMessagesEnvironmentInput):
        message_count = len(admitted_environment_input.messages)
    else:
        raise CoveragePlanValidationError(
            "mobile coverage capacity requires admitted mobile environment input"
        )
    return build_mobile_coverage_capacity(message_count=message_count)


def _workspace_capacity(
    admitted_environment_input: object | None,
) -> AdmittedCoverageCapacity:
    if admitted_environment_input is None:
        workspace_item_count = len(WORKSPACE_ITEM_GROUNDING_ARGUMENTS)
    elif isinstance(admitted_environment_input, WorkspaceEnvironmentInput):
        workspace_item_count = sum(
            (
                len(admitted_environment_input.projects),
                len(admitted_environment_input.tasks),
                len(admitted_environment_input.documents),
                len(admitted_environment_input.comments),
            )
        )
    else:
        raise CoveragePlanValidationError(
            "workspace coverage capacity requires admitted workspace environment input"
        )
    return build_workspace_coverage_capacity(
        workspace_item_count=workspace_item_count
    )


_CONTACTS_PLANNING = DomainCoveragePlanningDefinition(
    catalog=contacts_coverage_catalog(),
    version_registry=contacts_coverage_version_registry(),
    resolve_profile=resolve_contacts_coverage_profile,
    resolve_capacity=_contacts_capacity,
)
_MOBILE_PLANNING = DomainCoveragePlanningDefinition(
    catalog=mobile_coverage_catalog(),
    version_registry=mobile_coverage_version_registry(),
    resolve_profile=resolve_mobile_coverage_profile,
    resolve_capacity=_mobile_capacity,
)
_WORKSPACE_PLANNING = DomainCoveragePlanningDefinition(
    catalog=workspace_coverage_catalog(),
    version_registry=workspace_coverage_version_registry(),
    resolve_profile=resolve_workspace_coverage_profile,
    resolve_capacity=_workspace_capacity,
)
_DOMAIN_COVERAGE_PLANNING = {
    "contacts": _CONTACTS_PLANNING,
    "contacts_fixture": _CONTACTS_PLANNING,
    "mobile_messages_fixture": _MOBILE_PLANNING,
    "workspace_tasks_fixture": _WORKSPACE_PLANNING,
}
