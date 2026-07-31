from __future__ import annotations

from dataclasses import replace

from synthesis.coverage import (
    COVERAGE_CAPACITY_VERSION,
    COVERAGE_CATALOG_VERSION,
    COVERAGE_PROFILE_SCHEMA_VERSION,
    COVERAGE_VERSION_REGISTRY_VERSION,
    AdmittedCoverageCapacity,
    CoverageAttemptPolicy,
    CoverageCatalog,
    CoverageCell,
    CoverageCompatibilityConstraint,
    CoverageDifficultySemantics,
    CoveragePlanValidationError,
    CoverageProfile,
    CoverageVersionRegistry,
)


CONTACTS_COVERAGE_CATALOG_ID = "contacts_coverage"
CONTACTS_COVERAGE_CATALOG_VERSION = "contacts_coverage_v1"
CONTACTS_COVERAGE_CATALOG_VERSION_V2 = "contacts_coverage_v2"
CONTACTS_SMOKE_PROFILE_ID = "contacts_smoke"
CONTACTS_SMOKE_PROFILE_VERSION = "contacts_smoke_v1"
CONTACTS_REPRESENTATIVE_PROFILE_ID = "contacts_representative"
CONTACTS_REPRESENTATIVE_PROFILE_VERSION = "contacts_representative_v1"
CONTACTS_REPRESENTATIVE_PROFILE_VERSION_V2 = "contacts_representative_v2"

_EXPANDED_CONTACT_GROUNDING_UNIT_IDS = (
    "alice_zhang",
    "ben_carter",
    "carla_diaz",
    "david_kim",
    "elena_petrova",
    "frank_osei",
    "grace_liu",
    "hassan_rahman",
    "ingrid_novak",
    "jamal_thompson",
    "keiko_sato",
    "luis_moreno",
    "nadia_ahmed",
    "owen_brooks",
    "priyanka_shah",
)


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
        grounding_context_sizes={"contacts": 6},
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
                grounding_unit_indices=(0, 1, 2, 3, 4, 5),
                grounding_unit_ids=(
                    "alice_zhang",
                    "ben_carter",
                    "carla_diaz",
                    "david_kim",
                    "elena_petrova",
                    "frank_osei",
                ),
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
                grounding_unit_indices=(0, 1, 2, 3, 4, 5),
                grounding_unit_ids=(
                    "alice_zhang",
                    "ben_carter",
                    "carla_diaz",
                    "david_kim",
                    "elena_petrova",
                    "frank_osei",
                ),
            ),
            CoverageCell(
                cell_id="contacts.lookup_with_recovery",
                dimensions={
                    "task_type": "contact_lookup",
                    "required_tools": ("lookup_contact_email",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "abbreviated_then_full_name",
                    "constraint_profile": "ordered_fallback",
                    "difficulty": "recovery",
                    "ambiguity": "recoverable_short_name",
                    "recovery": "fallback_full_name",
                },
                grounding_capacity_key="contacts",
                grounding_unit_indices=(0,),
                grounding_unit_ids=("alice_zhang",),
                required_features=("enable_branching",),
                branch_plan={
                    "schema_version": "branch_plan_v1",
                    "plan_id": "branch_plan_contacts_coverage_recovery",
                    "max_depth": 2,
                    "branches": [
                        {
                            "branch_id": "direct_short_name",
                            "node_type": "attempt",
                            "parent_id": None,
                            "condition": "Try the abbreviated name first.",
                            "steps": [
                                {
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice"},
                                }
                            ],
                            "final_response_template": "{name}'s email is {email}.",
                            "terminal_outcome": "fallback_on_failure",
                        },
                        {
                            "branch_id": "fallback_full_name",
                            "node_type": "fallback",
                            "parent_id": "direct_short_name",
                            "condition": "Use the full name after the abbreviated lookup fails.",
                            "steps": [
                                {
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice Zhang"},
                                }
                            ],
                            "final_response_template": "{name}'s email is {email}.",
                            "terminal_outcome": "accept_on_success",
                        },
                    ],
                },
            ),
        ),
        compatibility_constraints=(
            CoverageCompatibilityConstraint(
                task_type="contact_lookup",
                required_tools=("lookup_contact_email",),
                state_behavior="read_only",
                grounding_pattern="exact_contact_name",
                constraint_profile="single_entity",
                difficulty="basic",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="contact_followup",
                required_tools=(
                    "lookup_contact_email",
                    "record_contact_followup",
                ),
                state_behavior="state_changing",
                grounding_pattern="lookup_bound_followup",
                constraint_profile="cross_step_binding",
                difficulty="intermediate",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="contact_lookup",
                required_tools=("lookup_contact_email",),
                state_behavior="read_only",
                grounding_pattern="abbreviated_then_full_name",
                constraint_profile="ordered_fallback",
                difficulty="recovery",
                ambiguity="recoverable_short_name",
                recovery="fallback_full_name",
            ),
        ),
        difficulty_semantics=(
            CoverageDifficultySemantics(
                difficulty="basic",
                tool_count=1,
                constraint_count=1,
                state_changes=0,
                ambiguity="none",
                recovery_paths=0,
            ),
            CoverageDifficultySemantics(
                difficulty="intermediate",
                tool_count=2,
                constraint_count=1,
                state_changes=1,
                ambiguity="none",
                recovery_paths=0,
            ),
            CoverageDifficultySemantics(
                difficulty="recovery",
                tool_count=1,
                constraint_count=2,
                state_changes=0,
                ambiguity="recoverable_short_name",
                recovery_paths=1,
            ),
        ),
    )


def contacts_representative_coverage_catalog() -> CoverageCatalog:
    base = contacts_coverage_catalog()
    lookup, followup, recovery = base.cells
    expanded_indices = tuple(range(len(_EXPANDED_CONTACT_GROUNDING_UNIT_IDS)))
    return replace(
        base,
        version=CONTACTS_COVERAGE_CATALOG_VERSION_V2,
        grounding_context_sizes={
            "contacts": len(_EXPANDED_CONTACT_GROUNDING_UNIT_IDS)
        },
        cells=(
            replace(
                lookup,
                grounding_unit_indices=expanded_indices,
                grounding_unit_ids=_EXPANDED_CONTACT_GROUNDING_UNIT_IDS,
            ),
            replace(
                followup,
                grounding_unit_indices=expanded_indices,
                grounding_unit_ids=_EXPANDED_CONTACT_GROUNDING_UNIT_IDS,
            ),
            recovery,
        ),
    )


def contacts_coverage_version_registry() -> CoverageVersionRegistry:
    return CoverageVersionRegistry(
        schema_version=COVERAGE_VERSION_REGISTRY_VERSION,
        catalog_versions=(
            (
                CONTACTS_COVERAGE_CATALOG_ID,
                CONTACTS_COVERAGE_CATALOG_VERSION,
            ),
            (
                CONTACTS_COVERAGE_CATALOG_ID,
                CONTACTS_COVERAGE_CATALOG_VERSION_V2,
            ),
        ),
        profile_versions=(
            (CONTACTS_SMOKE_PROFILE_ID, CONTACTS_SMOKE_PROFILE_VERSION),
            (
                CONTACTS_REPRESENTATIVE_PROFILE_ID,
                CONTACTS_REPRESENTATIVE_PROFILE_VERSION,
            ),
            (
                CONTACTS_REPRESENTATIVE_PROFILE_ID,
                CONTACTS_REPRESENTATIVE_PROFILE_VERSION_V2,
            ),
        ),
    )


def resolve_contacts_coverage_profile(
    profile_id: str,
    version: str,
) -> CoverageProfile:
    profiles = {
        (CONTACTS_SMOKE_PROFILE_ID, CONTACTS_SMOKE_PROFILE_VERSION): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=CONTACTS_SMOKE_PROFILE_ID,
            version=CONTACTS_SMOKE_PROFILE_VERSION,
            catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
            catalog_version=CONTACTS_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
            },
            balance_weights={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
                "contacts.lookup_with_recovery": 1,
            },
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                policy_version="bounded_attempt_ratio_v1",
                multiplier_numerator=3,
                multiplier_denominator=2,
            ),
            max_balance_weight_override=4,
        ),
        (
            CONTACTS_REPRESENTATIVE_PROFILE_ID,
            CONTACTS_REPRESENTATIVE_PROFILE_VERSION,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=CONTACTS_REPRESENTATIVE_PROFILE_ID,
            version=CONTACTS_REPRESENTATIVE_PROFILE_VERSION,
            catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
            catalog_version=CONTACTS_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "contacts.lookup_by_name": 2,
                "contacts.followup_after_lookup": 2,
                "contacts.lookup_with_recovery": 1,
            },
            balance_weights={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
                "contacts.lookup_with_recovery": 1,
            },
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                policy_version="bounded_attempt_ratio_v1",
                multiplier_numerator=2,
                multiplier_denominator=1,
            ),
            max_balance_weight_override=4,
        ),
        (
            CONTACTS_REPRESENTATIVE_PROFILE_ID,
            CONTACTS_REPRESENTATIVE_PROFILE_VERSION_V2,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=CONTACTS_REPRESENTATIVE_PROFILE_ID,
            version=CONTACTS_REPRESENTATIVE_PROFILE_VERSION_V2,
            catalog_id=CONTACTS_COVERAGE_CATALOG_ID,
            catalog_version=CONTACTS_COVERAGE_CATALOG_VERSION_V2,
            mandatory_floors={
                "contacts.lookup_by_name": 2,
                "contacts.followup_after_lookup": 2,
                "contacts.lookup_with_recovery": 1,
            },
            balance_weights={
                "contacts.lookup_by_name": 1,
                "contacts.followup_after_lookup": 1,
                "contacts.lookup_with_recovery": 1,
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
