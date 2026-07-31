from __future__ import annotations

from dataclasses import replace
from typing import Mapping

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
    compatibility_constraint_for_cell,
)


MOBILE_COVERAGE_CATALOG_ID = "mobile_messages_coverage"
MOBILE_COVERAGE_CATALOG_VERSION = "mobile_messages_coverage_v1"
MOBILE_COVERAGE_CATALOG_VERSION_V2 = "mobile_messages_coverage_v2"
MOBILE_COVERAGE_CATALOG_VERSION_V3 = "mobile_messages_coverage_v3"
MOBILE_SMOKE_PROFILE_ID = "mobile_messages_smoke"
MOBILE_SMOKE_PROFILE_VERSION = "mobile_messages_smoke_v1"
MOBILE_REPRESENTATIVE_PROFILE_ID = "mobile_messages_representative"
MOBILE_REPRESENTATIVE_PROFILE_VERSION = "mobile_messages_representative_v1"
MOBILE_REPRESENTATIVE_PROFILE_VERSION_V2 = "mobile_messages_representative_v2"
MOBILE_REPRESENTATIVE_PROFILE_VERSION_V3 = "mobile_messages_representative_v3"

_EXPANDED_MESSAGE_GROUNDING_UNIT_IDS = (
    "msg_maya_project_update",
    "msg_alex_late_reply",
    "msg_delivery_pickup_code",
    "msg_maya_project_update",
    "msg_priya_design_review",
    "msg_morgan_finance_review",
    "msg_jordan_quarterly_planning",
    "msg_riley_budget_approval",
    "msg_sam_customer_interview",
    "msg_taylor_incident_review",
    "msg_uma_travel_itinerary",
    "msg_victor_contract_renewal",
    "msg_wendy_hiring_plan",
    "msg_xavier_security_audit",
    "msg_yasmin_launch_checklist",
    "msg_zoe_team_offsite",
)

_DIMENSIONS = (
    "task_type",
    "required_tools",
    "state_behavior",
    "grounding_pattern",
    "constraint_profile",
    "difficulty",
    "ambiguity",
    "recovery",
)


def mobile_coverage_catalog() -> CoverageCatalog:
    return CoverageCatalog(
        schema_version=COVERAGE_CATALOG_VERSION,
        catalog_id=MOBILE_COVERAGE_CATALOG_ID,
        version=MOBILE_COVERAGE_CATALOG_VERSION,
        domain_id="mobile_messages_fixture",
        dimensions=_DIMENSIONS,
        grounding_context_sizes={"messages": 7},
        cells=(
            CoverageCell(
                cell_id="mobile.search_exact_participant",
                dimensions={
                    "task_type": "mobile_message_search",
                    "required_tools": ("search_phone_messages",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "query_and_participant",
                    "constraint_profile": "single_message",
                    "difficulty": "basic",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="messages",
                grounding_unit_indices=(0, 1, 2, 4, 5, 6),
                grounding_unit_ids=(
                    "msg_maya_project_update",
                    "msg_alex_late_reply",
                    "msg_delivery_pickup_code",
                    "msg_priya_design_review",
                    "msg_morgan_finance_review",
                    "msg_jordan_quarterly_planning",
                ),
            ),
            CoverageCell(
                cell_id="mobile.search_deterministic_multi_result",
                dimensions={
                    "task_type": "mobile_message_search",
                    "required_tools": ("search_phone_messages",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "query_only_multi_result",
                    "constraint_profile": "deterministic_first_match",
                    "difficulty": "constrained",
                    "ambiguity": "deterministic_multi_result",
                    "recovery": "none",
                },
                grounding_capacity_key="messages",
                grounding_unit_indices=(3,),
                grounding_unit_ids=("msg_maya_project_update",),
                max_accepted_samples=1,
            ),
            CoverageCell(
                cell_id="mobile.reminder_from_message",
                dimensions={
                    "task_type": "mobile_reminder_creation",
                    "required_tools": (
                        "search_phone_messages",
                        "create_phone_reminder",
                    ),
                    "state_behavior": "state_changing",
                    "grounding_pattern": "message_to_reminder",
                    "constraint_profile": "source_message_binding",
                    "difficulty": "intermediate",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="messages",
                grounding_unit_indices=(0, 2, 4, 5, 6),
                grounding_unit_ids=(
                    "msg_maya_project_update",
                    "msg_delivery_pickup_code",
                    "msg_priya_design_review",
                    "msg_morgan_finance_review",
                    "msg_jordan_quarterly_planning",
                ),
            ),
            CoverageCell(
                cell_id="mobile.draft_reply_to_thread",
                dimensions={
                    "task_type": "mobile_draft_reply",
                    "required_tools": (
                        "search_phone_messages",
                        "draft_message_reply",
                    ),
                    "state_behavior": "state_changing",
                    "grounding_pattern": "message_to_thread_reply",
                    "constraint_profile": "thread_and_body_binding",
                    "difficulty": "intermediate",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="messages",
                grounding_unit_indices=(0, 1, 2, 4, 5, 6),
                grounding_unit_ids=(
                    "msg_maya_project_update",
                    "msg_alex_late_reply",
                    "msg_delivery_pickup_code",
                    "msg_priya_design_review",
                    "msg_morgan_finance_review",
                    "msg_jordan_quarterly_planning",
                ),
            ),
            CoverageCell(
                cell_id="mobile.search_with_sender_fallback",
                dimensions={
                    "task_type": "mobile_message_search",
                    "required_tools": ("search_phone_messages",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "wrong_sender_then_broad_query",
                    "constraint_profile": "ordered_fallback",
                    "difficulty": "recovery",
                    "ambiguity": "missing_sender_label",
                    "recovery": "broader_thread_search",
                },
                grounding_capacity_key="messages",
                grounding_unit_indices=(2,),
                grounding_unit_ids=("msg_delivery_pickup_code",),
                required_features=("enable_branching",),
                branch_plan={
                    "schema_version": "branch_plan_v1",
                    "plan_id": "branch_plan_mobile_coverage_sender_fallback",
                    "max_depth": 2,
                    "branches": [
                        {
                            "branch_id": "direct_sender_search",
                            "node_type": "attempt",
                            "parent_id": None,
                            "condition": "Try the direct sender label first.",
                            "steps": [
                                {
                                    "tool_name": "search_phone_messages",
                                    "arguments": {
                                        "query": "pickup code",
                                        "participant": "Courier",
                                    },
                                }
                            ],
                            "final_response_template": (
                                "Pickup message {message_id}: {snippet}"
                            ),
                            "terminal_outcome": "fallback_on_failure",
                        },
                        {
                            "branch_id": "broader_thread_search",
                            "node_type": "fallback",
                            "parent_id": "direct_sender_search",
                            "condition": "Search all threads after the sender lookup fails.",
                            "steps": [
                                {
                                    "tool_name": "search_phone_messages",
                                    "arguments": {"query": "pickup code"},
                                }
                            ],
                            "final_response_template": (
                                "Pickup message {message_id}: {snippet}"
                            ),
                            "terminal_outcome": "accept_on_success",
                        },
                    ],
                },
            ),
        ),
        compatibility_constraints=(
            CoverageCompatibilityConstraint(
                task_type="mobile_message_search",
                required_tools=("search_phone_messages",),
                state_behavior="read_only",
                grounding_pattern="query_and_participant",
                constraint_profile="single_message",
                difficulty="basic",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="mobile_message_search",
                required_tools=("search_phone_messages",),
                state_behavior="read_only",
                grounding_pattern="query_only_multi_result",
                constraint_profile="deterministic_first_match",
                difficulty="constrained",
                ambiguity="deterministic_multi_result",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="mobile_reminder_creation",
                required_tools=(
                    "search_phone_messages",
                    "create_phone_reminder",
                ),
                state_behavior="state_changing",
                grounding_pattern="message_to_reminder",
                constraint_profile="source_message_binding",
                difficulty="intermediate",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="mobile_draft_reply",
                required_tools=(
                    "search_phone_messages",
                    "draft_message_reply",
                ),
                state_behavior="state_changing",
                grounding_pattern="message_to_thread_reply",
                constraint_profile="thread_and_body_binding",
                difficulty="intermediate",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="mobile_message_search",
                required_tools=("search_phone_messages",),
                state_behavior="read_only",
                grounding_pattern="wrong_sender_then_broad_query",
                constraint_profile="ordered_fallback",
                difficulty="recovery",
                ambiguity="missing_sender_label",
                recovery="broader_thread_search",
            ),
        ),
        difficulty_semantics=(
            CoverageDifficultySemantics("basic", 1, 1, 0, "none", 0),
            CoverageDifficultySemantics(
                "constrained",
                1,
                2,
                0,
                "deterministic_multi_result",
                0,
            ),
            CoverageDifficultySemantics("intermediate", 2, 2, 1, "none", 0),
            CoverageDifficultySemantics(
                "recovery",
                1,
                2,
                0,
                "missing_sender_label",
                1,
            ),
        ),
    )


def mobile_representative_coverage_catalog() -> CoverageCatalog:
    base = mobile_coverage_catalog()
    exact, multi_result, reminder, draft_reply, recovery = base.cells
    expanded_indices = tuple(
        index
        for index in range(len(_EXPANDED_MESSAGE_GROUNDING_UNIT_IDS))
        if index != 3
    )
    expanded_ids = tuple(
        _EXPANDED_MESSAGE_GROUNDING_UNIT_IDS[index]
        for index in expanded_indices
    )
    reminder_indices = tuple(
        index
        for index in expanded_indices
        if index != 1
    )
    return replace(
        base,
        version=MOBILE_COVERAGE_CATALOG_VERSION_V2,
        grounding_context_sizes={
            "messages": len(_EXPANDED_MESSAGE_GROUNDING_UNIT_IDS)
        },
        cells=(
            replace(
                exact,
                grounding_unit_indices=expanded_indices,
                grounding_unit_ids=expanded_ids,
            ),
            multi_result,
            replace(
                reminder,
                grounding_unit_indices=reminder_indices,
                grounding_unit_ids=tuple(
                    _EXPANDED_MESSAGE_GROUNDING_UNIT_IDS[index]
                    for index in reminder_indices
                ),
            ),
            replace(
                draft_reply,
                grounding_unit_indices=expanded_indices,
                grounding_unit_ids=expanded_ids,
            ),
            recovery,
        ),
    )


def mobile_structural_coverage_catalog() -> CoverageCatalog:
    base = mobile_representative_coverage_catalog()
    scenarios = (
        (4, "drop_incorrect_participant"),
        (5, "correct_participant"),
        (6, "correct_query"),
        (7, "remove_extra_query_term"),
        (8, "remove_sender_from_query"),
        (9, "replace_message_id_query"),
        (10, "remove_literal_quotes"),
        (11, "restore_query_token_order"),
    )
    recovery_cells = tuple(
        _mobile_recovery_cell(
            grounding_index=index,
            scenario=scenario,
        )
        for index, scenario in scenarios
    )
    return replace(
        base,
        version=MOBILE_COVERAGE_CATALOG_VERSION_V3,
        cells=(*base.cells, *recovery_cells),
        compatibility_constraints=(
            *base.compatibility_constraints,
            *(compatibility_constraint_for_cell(cell) for cell in recovery_cells),
        ),
        difficulty_semantics=(
            *base.difficulty_semantics,
            CoverageDifficultySemantics(
                "selector_recovery",
                1,
                2,
                0,
                "invalid_message_selector",
                1,
            ),
        ),
        validate_grounding_identities=True,
    )


def _mobile_recovery_cell(
    *,
    grounding_index: int,
    scenario: str,
) -> CoverageCell:
    from synthesis.mobile_tasks import MOBILE_REPRESENTATIVE_GROUNDING_ARGUMENTS

    fallback_arguments: dict[str, object] = dict(
        MOBILE_REPRESENTATIVE_GROUNDING_ARGUMENTS[grounding_index]
    )
    direct_arguments = _invalid_message_selector(
        fallback_arguments,
        _EXPANDED_MESSAGE_GROUNDING_UNIT_IDS[grounding_index],
        scenario,
    )
    return CoverageCell(
        cell_id=f"mobile.recover_{scenario}",
        dimensions={
            "task_type": "mobile_message_search",
            "required_tools": ("search_phone_messages",),
            "state_behavior": "read_only",
            "grounding_pattern": f"{scenario}_then_observed_selector",
            "constraint_profile": "observed_failure_then_exact_selector",
            "difficulty": "selector_recovery",
            "ambiguity": "invalid_message_selector",
            "recovery": scenario,
        },
        grounding_capacity_key="messages",
        grounding_unit_indices=(grounding_index,),
        grounding_unit_ids=(
            _EXPANDED_MESSAGE_GROUNDING_UNIT_IDS[grounding_index],
        ),
        required_features=("enable_branching",),
        branch_plan={
            "schema_version": "branch_plan_v1",
            "plan_id": f"branch_plan_mobile_{scenario}",
            "max_depth": 2,
            "branches": [
                {
                    "branch_id": "invalid_selector",
                    "node_type": "attempt",
                    "parent_id": None,
                    "condition": f"Try the {scenario} selector first.",
                    "steps": [
                        {
                            "tool_name": "search_phone_messages",
                            "arguments": direct_arguments,
                        }
                    ],
                    "final_response_template": (
                        "Message {message_id}: {snippet}"
                    ),
                    "terminal_outcome": "fallback_on_failure",
                },
                {
                    "branch_id": "observed_selector",
                    "node_type": "fallback",
                    "parent_id": "invalid_selector",
                    "condition": "Use the observed selector after failure.",
                    "steps": [
                        {
                            "tool_name": "search_phone_messages",
                            "arguments": fallback_arguments,
                        }
                    ],
                    "final_response_template": (
                        "Message {message_id}: {snippet}"
                    ),
                    "terminal_outcome": "accept_on_success",
                },
            ],
        },
    )


def _invalid_message_selector(
    fallback: Mapping[str, object],
    message_id: str,
    scenario: str,
) -> dict[str, object]:
    query = str(fallback["query"])
    participant = str(fallback["participant"])
    selectors: dict[str, dict[str, object]] = {
        "drop_incorrect_participant": {
            "query": query,
            "participant": "Unknown Sender",
        },
        "correct_participant": {
            "query": query,
            "participant": participant + "x",
        },
        "correct_query": {
            "query": "missing phrase",
            "participant": participant,
        },
        "remove_extra_query_term": {
            "query": query + " nonexistent",
            "participant": participant,
        },
        "remove_sender_from_query": {
            "query": f"{participant} {query}",
            "participant": participant,
        },
        "replace_message_id_query": {
            "query": message_id,
            "participant": participant,
        },
        "remove_literal_quotes": {
            "query": f'"{query}"',
            "participant": participant,
        },
        "restore_query_token_order": {
            "query": " ".join(reversed(query.split())),
            "participant": participant,
        },
    }
    return selectors[scenario]


def mobile_coverage_version_registry() -> CoverageVersionRegistry:
    return CoverageVersionRegistry(
        schema_version=COVERAGE_VERSION_REGISTRY_VERSION,
        catalog_versions=(
            (MOBILE_COVERAGE_CATALOG_ID, MOBILE_COVERAGE_CATALOG_VERSION),
            (
                MOBILE_COVERAGE_CATALOG_ID,
                MOBILE_COVERAGE_CATALOG_VERSION_V2,
            ),
            (
                MOBILE_COVERAGE_CATALOG_ID,
                MOBILE_COVERAGE_CATALOG_VERSION_V3,
            ),
        ),
        profile_versions=(
            (MOBILE_SMOKE_PROFILE_ID, MOBILE_SMOKE_PROFILE_VERSION),
            (
                MOBILE_REPRESENTATIVE_PROFILE_ID,
                MOBILE_REPRESENTATIVE_PROFILE_VERSION,
            ),
            (
                MOBILE_REPRESENTATIVE_PROFILE_ID,
                MOBILE_REPRESENTATIVE_PROFILE_VERSION_V2,
            ),
            (
                MOBILE_REPRESENTATIVE_PROFILE_ID,
                MOBILE_REPRESENTATIVE_PROFILE_VERSION_V3,
            ),
        ),
    )


def resolve_mobile_coverage_profile(
    profile_id: str,
    version: str,
) -> CoverageProfile:
    common = {
        "mobile.search_exact_participant": 1,
        "mobile.search_deterministic_multi_result": 1,
        "mobile.reminder_from_message": 1,
        "mobile.draft_reply_to_thread": 1,
        "mobile.search_with_sender_fallback": 1,
    }
    profiles = {
        (MOBILE_SMOKE_PROFILE_ID, MOBILE_SMOKE_PROFILE_VERSION): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=MOBILE_SMOKE_PROFILE_ID,
            version=MOBILE_SMOKE_PROFILE_VERSION,
            catalog_id=MOBILE_COVERAGE_CATALOG_ID,
            catalog_version=MOBILE_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "mobile.search_exact_participant": 1,
                "mobile.reminder_from_message": 1,
            },
            balance_weights=common,
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                "bounded_attempt_ratio_v1",
                3,
                2,
            ),
            max_balance_weight_override=4,
        ),
        (
            MOBILE_REPRESENTATIVE_PROFILE_ID,
            MOBILE_REPRESENTATIVE_PROFILE_VERSION,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=MOBILE_REPRESENTATIVE_PROFILE_ID,
            version=MOBILE_REPRESENTATIVE_PROFILE_VERSION,
            catalog_id=MOBILE_COVERAGE_CATALOG_ID,
            catalog_version=MOBILE_COVERAGE_CATALOG_VERSION,
            mandatory_floors=common,
            balance_weights=common,
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                "bounded_attempt_ratio_v1",
                2,
                1,
            ),
            max_balance_weight_override=4,
        ),
        (
            MOBILE_REPRESENTATIVE_PROFILE_ID,
            MOBILE_REPRESENTATIVE_PROFILE_VERSION_V2,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=MOBILE_REPRESENTATIVE_PROFILE_ID,
            version=MOBILE_REPRESENTATIVE_PROFILE_VERSION_V2,
            catalog_id=MOBILE_COVERAGE_CATALOG_ID,
            catalog_version=MOBILE_COVERAGE_CATALOG_VERSION_V2,
            mandatory_floors=common,
            balance_weights=common,
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                "bounded_attempt_ratio_v1",
                2,
                1,
            ),
            max_balance_weight_override=4,
        ),
        (
            MOBILE_REPRESENTATIVE_PROFILE_ID,
            MOBILE_REPRESENTATIVE_PROFILE_VERSION_V3,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=MOBILE_REPRESENTATIVE_PROFILE_ID,
            version=MOBILE_REPRESENTATIVE_PROFILE_VERSION_V3,
            catalog_id=MOBILE_COVERAGE_CATALOG_ID,
            catalog_version=MOBILE_COVERAGE_CATALOG_VERSION_V3,
            mandatory_floors={
                "mobile.search_exact_participant": 1,
                "mobile.search_deterministic_multi_result": 1,
                "mobile.reminder_from_message": 1,
                "mobile.draft_reply_to_thread": 1,
                "mobile.search_with_sender_fallback": 1,
            },
            balance_weights={
                cell.cell_id: 1
                for cell in mobile_structural_coverage_catalog().cells
            },
            max_accepted_samples_per_grounding_unit=2,
            attempt_policy=CoverageAttemptPolicy(
                "bounded_attempt_ratio_v1",
                2,
                1,
            ),
            max_balance_weight_override=4,
        ),
    }
    try:
        return profiles[(profile_id, version)]
    except KeyError as exc:
        raise CoveragePlanValidationError(
            f"unknown mobile coverage profile: {profile_id}@{version}"
        ) from exc


def build_mobile_coverage_capacity(*, message_count: int) -> AdmittedCoverageCapacity:
    if (
        not isinstance(message_count, int)
        or isinstance(message_count, bool)
        or message_count < 0
    ):
        raise CoveragePlanValidationError(
            "mobile admitted capacity must be a non-negative integer"
        )
    return AdmittedCoverageCapacity(
        schema_version=COVERAGE_CAPACITY_VERSION,
        domain_id="mobile_messages_fixture",
        grounding_units={"messages": message_count},
    )
