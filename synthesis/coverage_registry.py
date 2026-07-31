from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from synthesis.contacts_coverage import (
    build_contacts_coverage_capacity,
    contacts_coverage_catalog,
    contacts_representative_coverage_catalog,
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
from synthesis.environments import (
    CONTACT_FIXTURE_ROWS,
    CONTACT_REPRESENTATIVE_FIXTURE_ROWS,
    ContactsEnvironmentInput,
)
from synthesis.mobile_coverage import (
    build_mobile_coverage_capacity,
    mobile_coverage_catalog,
    mobile_representative_coverage_catalog,
    mobile_coverage_version_registry,
    resolve_mobile_coverage_profile,
)
from synthesis.mobile_environment import MobileMessagesEnvironmentInput
from synthesis.mobile_tasks import (
    MOBILE_MESSAGE_GROUNDING_ARGUMENTS,
    MOBILE_REPRESENTATIVE_GROUNDING_ARGUMENTS,
)
from synthesis.workspace_coverage import (
    build_workspace_coverage_capacity,
    resolve_workspace_coverage_profile,
    workspace_coverage_catalog,
    workspace_representative_coverage_catalog,
    workspace_coverage_version_registry,
)
from synthesis.workspace_environment import WorkspaceEnvironmentInput
from synthesis.workspace_tasks import (
    WORKSPACE_ITEM_GROUNDING_ARGUMENTS,
    WORKSPACE_REPRESENTATIVE_ITEM_GROUNDING_ARGUMENTS,
)


CoverageProfileResolver = Callable[[str, str], CoverageProfile]
CoverageCapacityResolver = Callable[[object | None], AdmittedCoverageCapacity]


@dataclass(frozen=True)
class DomainCoveragePlanningVariant:
    catalog: CoverageCatalog
    synthetic_capacity: AdmittedCoverageCapacity
    use_representative_fixture: bool


@dataclass(frozen=True)
class DomainCoveragePlanningDefinition:
    default_variant: DomainCoveragePlanningVariant
    version_registry: CoverageVersionRegistry
    resolve_profile: CoverageProfileResolver
    _resolve_capacity: CoverageCapacityResolver
    additional_variants: tuple[DomainCoveragePlanningVariant, ...] = ()

    @property
    def catalog(self) -> CoverageCatalog:
        return self.default_variant.catalog

    def resolve_variant(self, version: str) -> DomainCoveragePlanningVariant:
        for variant in (self.default_variant, *self.additional_variants):
            if variant.catalog.version == version:
                return variant
        raise CoveragePlanValidationError(
            f"unknown coverage catalog version: {version}"
        )

    def resolve_catalog(self, version: str) -> CoverageCatalog:
        return self.resolve_variant(version).catalog

    def resolve_capacity(
        self,
        admitted_environment_input: object | None,
    ) -> AdmittedCoverageCapacity:
        return self.resolve_capacity_for_catalog(
            self.catalog,
            admitted_environment_input,
        )

    def resolve_capacity_for_catalog(
        self,
        catalog: CoverageCatalog,
        admitted_environment_input: object | None,
    ) -> AdmittedCoverageCapacity:
        variant = self.resolve_variant(catalog.version)
        if admitted_environment_input is None:
            return variant.synthetic_capacity
        capacity = self._resolve_capacity(admitted_environment_input)
        return AdmittedCoverageCapacity(
            schema_version=capacity.schema_version,
            domain_id=capacity.domain_id,
            grounding_units={
                key: min(
                    count,
                    catalog.grounding_context_sizes[key],
                )
                for key, count in capacity.grounding_units.items()
            },
        )


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
    if isinstance(admitted_environment_input, ContactsEnvironmentInput):
        contact_count = len(admitted_environment_input.contacts)
    else:
        raise CoveragePlanValidationError(
            "contacts coverage capacity requires admitted contacts environment input"
        )
    return build_contacts_coverage_capacity(contact_count=contact_count)


def _mobile_capacity(
    admitted_environment_input: object | None,
) -> AdmittedCoverageCapacity:
    if isinstance(admitted_environment_input, MobileMessagesEnvironmentInput):
        message_count = len(admitted_environment_input.messages)
    else:
        raise CoveragePlanValidationError(
            "mobile coverage capacity requires admitted mobile environment input"
        )
    return build_mobile_coverage_capacity(message_count=message_count)


def _workspace_capacity(
    admitted_environment_input: object | None,
) -> AdmittedCoverageCapacity:
    if isinstance(admitted_environment_input, WorkspaceEnvironmentInput):
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
    default_variant=DomainCoveragePlanningVariant(
        catalog=contacts_coverage_catalog(),
        synthetic_capacity=build_contacts_coverage_capacity(
            contact_count=len(CONTACT_FIXTURE_ROWS)
        ),
        use_representative_fixture=False,
    ),
    version_registry=contacts_coverage_version_registry(),
    resolve_profile=resolve_contacts_coverage_profile,
    _resolve_capacity=_contacts_capacity,
    additional_variants=(
        DomainCoveragePlanningVariant(
            catalog=contacts_representative_coverage_catalog(),
            synthetic_capacity=build_contacts_coverage_capacity(
                contact_count=len(CONTACT_REPRESENTATIVE_FIXTURE_ROWS)
            ),
            use_representative_fixture=True,
        ),
    ),
)
_MOBILE_PLANNING = DomainCoveragePlanningDefinition(
    default_variant=DomainCoveragePlanningVariant(
        catalog=mobile_coverage_catalog(),
        synthetic_capacity=build_mobile_coverage_capacity(
            message_count=len(MOBILE_MESSAGE_GROUNDING_ARGUMENTS)
        ),
        use_representative_fixture=False,
    ),
    version_registry=mobile_coverage_version_registry(),
    resolve_profile=resolve_mobile_coverage_profile,
    _resolve_capacity=_mobile_capacity,
    additional_variants=(
        DomainCoveragePlanningVariant(
            catalog=mobile_representative_coverage_catalog(),
            synthetic_capacity=build_mobile_coverage_capacity(
                message_count=len(MOBILE_REPRESENTATIVE_GROUNDING_ARGUMENTS)
            ),
            use_representative_fixture=True,
        ),
    ),
)
_WORKSPACE_PLANNING = DomainCoveragePlanningDefinition(
    default_variant=DomainCoveragePlanningVariant(
        catalog=workspace_coverage_catalog(),
        synthetic_capacity=build_workspace_coverage_capacity(
            workspace_item_count=len(WORKSPACE_ITEM_GROUNDING_ARGUMENTS)
        ),
        use_representative_fixture=False,
    ),
    version_registry=workspace_coverage_version_registry(),
    resolve_profile=resolve_workspace_coverage_profile,
    _resolve_capacity=_workspace_capacity,
    additional_variants=(
        DomainCoveragePlanningVariant(
            catalog=workspace_representative_coverage_catalog(),
            synthetic_capacity=build_workspace_coverage_capacity(
                workspace_item_count=len(
                    WORKSPACE_REPRESENTATIVE_ITEM_GROUNDING_ARGUMENTS
                )
            ),
            use_representative_fixture=True,
        ),
    ),
)
_DOMAIN_COVERAGE_PLANNING = {
    "contacts": _CONTACTS_PLANNING,
    "contacts_fixture": _CONTACTS_PLANNING,
    "mobile_messages_fixture": _MOBILE_PLANNING,
    "workspace_tasks_fixture": _WORKSPACE_PLANNING,
}
