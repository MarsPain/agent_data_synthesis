from __future__ import annotations

from synthesis.coverage import (
    COVERAGE_CAPACITY_VERSION,
    COVERAGE_CATALOG_VERSION,
    COVERAGE_PROFILE_SCHEMA_VERSION,
    AdmittedCoverageCapacity,
    CoverageAttemptPolicy,
    CoverageCatalog,
    CoverageCell,
    CoveragePlanValidationError,
    CoverageProfile,
)


CONTACTS_COVERAGE_CATALOG_ID = "contacts_coverage"
CONTACTS_COVERAGE_CATALOG_VERSION = "contacts_coverage_v1"


def contacts_coverage_catalog() -> CoverageCatalog:
    dimensions = (
        "task_type",
        "required_tools",
        "state_behavior",
        "grounding_pattern",
        "constraint_profile",
        "difficulty",
        "ambiguity",
        "recovery",
    )
    return CoverageCatalog(
        schema_version=COVERAGE_CATALOG_VERSION,
        catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
        version=CONTACTS_COVERAGE_CATALOG_VERSION,
        domain_id="contacts_fixture",
        dimensions=dimensions,
        cells=(
            CoverageCell(
                cell_id="contacts.lookup_by_name",
                dimensions={
                    "task_type": "contact_lookup",
                    "required_tools": ("lookup_contact_email",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "exact_contact_name",
                    "constraint_profile": "single_entity",
                    "difficulty": "basic",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="contacts",
            ),
            CoverageCell(
                cell_id="contacts.followup_after_lookup",
                dimensions={
                    "task_type": "contact_followup",
                    "required_tools": (
                        "lookup_contact_email",
                        "record_contact_followup",
                    ),
                    "state_behavior": "state_changing",
                    "grounding_pattern": "lookup_bound_followup",
                    "constraint_profile": "cross_step_binding",
                    "difficulty": "intermediate",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="contacts",
            ),
        ),
    )


def resolve_contacts_coverage_profile(
    profile_id: str,
    version: str,
) -> CoverageProfile:
    profiles = {
        ("contacts_smoke", "contacts_smoke_v1"): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id="contacts_smoke",
            version="contacts_smoke_v1",
            catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
            catalog_version=CONTACTS_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
            },
            balance_weights={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
            },
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                policy_version="bounded_attempt_ratio_v1",
                multiplier_numerator=3,
                multiplier_denominator=2,
            ),
            max_balance_weight_override=4,
        ),
        ("contacts_representative", "contacts_representative_v1"): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id="contacts_representative",
            version="contacts_representative_v1",
            catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
            catalog_version=CONTACTS_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "contacts.lookup_by_name": 2,
                "contacts.followup_after_lookup": 2,
            },
            balance_weights={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
            },
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                policy_version="bounded_attempt_ratio_v1",
                multiplier_numerator=2,
                multiplier_denominator=1,
            ),
            max_balance_weight_override=4,
        ),
    }
    try:
        return profiles[(profile_id, version)]
    except KeyError as exc:
        raise CoveragePlanValidationError(
            f"unknown contacts coverage profile: {profile_id}@{version}"
        ) from exc


def build_contacts_coverage_capacity(
    *,
    contact_count: int,
) -> AdmittedCoverageCapacity:
    if (
        not isinstance(contact_count, int)
        or isinstance(contact_count, bool)
        or contact_count < 0
    ):
        raise CoveragePlanValidationError(
            "contacts admitted capacity must be a non-negative integer"
        )
    return AdmittedCoverageCapacity(
        schema_version=COVERAGE_CAPACITY_VERSION,
        domain_id="contacts_fixture",
        grounding_units={"contacts": contact_count},
    )
