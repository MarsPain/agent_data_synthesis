from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from synthesis.contacts_coverage import (
    build_contacts_coverage_capacity,
    contacts_coverage_catalog,
    resolve_contacts_coverage_profile,
)
from synthesis.coverage import (
    AdmittedCoverageCapacity,
    CoverageCatalog,
    CoveragePlanValidationError,
    CoverageProfile,
)
from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput


CoverageProfileResolver = Callable[[str, str], CoverageProfile]
CoverageCapacityResolver = Callable[[object | None], AdmittedCoverageCapacity]


@dataclass(frozen=True)
class DomainCoveragePlanningDefinition:
    catalog: CoverageCatalog
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


_CONTACTS_PLANNING = DomainCoveragePlanningDefinition(
    catalog=contacts_coverage_catalog(),
    resolve_profile=resolve_contacts_coverage_profile,
    resolve_capacity=_contacts_capacity,
)
_DOMAIN_COVERAGE_PLANNING = {
    "contacts": _CONTACTS_PLANNING,
    "contacts_fixture": _CONTACTS_PLANNING,
}
