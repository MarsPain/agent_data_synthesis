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


WORKSPACE_COVERAGE_CATALOG_ID = "workspace_tasks_coverage"
WORKSPACE_COVERAGE_CATALOG_VERSION = "workspace_tasks_coverage_v1"
WORKSPACE_COVERAGE_CATALOG_VERSION_V2 = "workspace_tasks_coverage_v2"
WORKSPACE_COVERAGE_CATALOG_VERSION_V3 = "workspace_tasks_coverage_v3"
WORKSPACE_SMOKE_PROFILE_ID = "workspace_tasks_smoke"
WORKSPACE_SMOKE_PROFILE_VERSION = "workspace_tasks_smoke_v1"
WORKSPACE_REPRESENTATIVE_PROFILE_ID = "workspace_tasks_representative"
WORKSPACE_REPRESENTATIVE_PROFILE_VERSION = "workspace_tasks_representative_v1"
WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V2 = "workspace_tasks_representative_v2"
WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V3 = "workspace_tasks_representative_v3"

_EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS = (
    "project_alpha",
    "task_launch_plan",
    "task_metrics_review",
    "doc_launch_brief",
    "project_beta",
    "task_research_notes",
    "comment_task_launch_plan_owner",
    "project_gamma",
    "project_delta",
    "project_epsilon",
    "project_zeta",
    "task_migration_checklist",
    "task_compliance_audit",
    "task_hiring_scorecard",
    "task_security_review",
    "doc_vendor_plan",
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


def workspace_coverage_catalog() -> CoverageCatalog:
    return CoverageCatalog(
        schema_version=COVERAGE_CATALOG_VERSION,
        catalog_id=WORKSPACE_COVERAGE_CATALOG_ID,
        version=WORKSPACE_COVERAGE_CATALOG_VERSION,
        domain_id="workspace_tasks_fixture",
        dimensions=_DIMENSIONS,
        grounding_context_sizes={"workspace_items": 7},
        cells=(
            CoverageCell(
                cell_id="workspace.search_exact_kind",
                dimensions={
                    "task_type": "workspace_item_search",
                    "required_tools": ("search_workspace_items",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "query_and_item_kind",
                    "constraint_profile": "single_workspace_item",
                    "difficulty": "basic",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="workspace_items",
                grounding_unit_indices=(0, 1, 2, 4, 5, 6),
                grounding_unit_ids=(
                    "project_alpha",
                    "task_launch_plan",
                    "task_metrics_review",
                    "project_beta",
                    "task_research_notes",
                    "comment_task_launch_plan_owner",
                ),
            ),
            CoverageCell(
                cell_id="workspace.search_deterministic_multi_kind",
                dimensions={
                    "task_type": "workspace_item_search",
                    "required_tools": ("search_workspace_items",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "query_only_multi_kind",
                    "constraint_profile": "deterministic_kind_order",
                    "difficulty": "constrained",
                    "ambiguity": "deterministic_multi_result",
                    "recovery": "none",
                },
                grounding_capacity_key="workspace_items",
                grounding_unit_indices=(3,),
                grounding_unit_ids=("doc_launch_brief",),
                max_accepted_samples=1,
            ),
            CoverageCell(
                cell_id="workspace.create_task_in_project",
                dimensions={
                    "task_type": "workspace_task_creation",
                    "required_tools": (
                        "search_workspace_items",
                        "create_workspace_task",
                    ),
                    "state_behavior": "state_changing",
                    "grounding_pattern": "project_to_new_task",
                    "constraint_profile": "project_priority_due_binding",
                    "difficulty": "intermediate",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="workspace_items",
                grounding_unit_indices=(0, 4),
                grounding_unit_ids=("project_alpha", "project_beta"),
            ),
            CoverageCell(
                cell_id="workspace.comment_on_task",
                dimensions={
                    "task_type": "workspace_comment_update",
                    "required_tools": (
                        "search_workspace_items",
                        "add_workspace_comment",
                    ),
                    "state_behavior": "state_changing",
                    "grounding_pattern": "task_to_comment",
                    "constraint_profile": "task_and_comment_binding",
                    "difficulty": "intermediate",
                    "ambiguity": "none",
                    "recovery": "none",
                },
                grounding_capacity_key="workspace_items",
                grounding_unit_indices=(1, 2, 5),
                grounding_unit_ids=(
                    "task_launch_plan",
                    "task_metrics_review",
                    "task_research_notes",
                ),
            ),
            CoverageCell(
                cell_id="workspace.search_with_kind_fallback",
                dimensions={
                    "task_type": "workspace_item_search",
                    "required_tools": ("search_workspace_items",),
                    "state_behavior": "read_only",
                    "grounding_pattern": "wrong_kind_then_comment",
                    "constraint_profile": "ordered_fallback",
                    "difficulty": "recovery",
                    "ambiguity": "missing_direct_task",
                    "recovery": "comment_search",
                },
                grounding_capacity_key="workspace_items",
                grounding_unit_indices=(6,),
                grounding_unit_ids=("comment_task_launch_plan_owner",),
                required_features=("enable_branching",),
                branch_plan={
                    "schema_version": "branch_plan_v1",
                    "plan_id": "branch_plan_workspace_coverage_kind_fallback",
                    "max_depth": 2,
                    "branches": [
                        {
                            "branch_id": "direct_task_search",
                            "node_type": "attempt",
                            "parent_id": None,
                            "condition": "Try the direct task title first.",
                            "steps": [
                                {
                                    "tool_name": "search_workspace_items",
                                    "arguments": {
                                        "query": "checklist owner",
                                        "kind": "task",
                                    },
                                }
                            ],
                            "final_response_template": "Workspace task found: {item_id}",
                            "terminal_outcome": "fallback_on_failure",
                        },
                        {
                            "branch_id": "comment_search",
                            "node_type": "fallback",
                            "parent_id": "direct_task_search",
                            "condition": "Search comments after the task lookup fails.",
                            "steps": [
                                {
                                    "tool_name": "search_workspace_items",
                                    "arguments": {
                                        "query": "checklist owner",
                                        "kind": "comment",
                                    },
                                }
                            ],
                            "final_response_template": "Workspace comment found: {item_id}",
                            "terminal_outcome": "accept_on_success",
                        },
                    ],
                },
            ),
        ),
        compatibility_constraints=(
            CoverageCompatibilityConstraint(
                task_type="workspace_item_search",
                required_tools=("search_workspace_items",),
                state_behavior="read_only",
                grounding_pattern="query_and_item_kind",
                constraint_profile="single_workspace_item",
                difficulty="basic",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="workspace_item_search",
                required_tools=("search_workspace_items",),
                state_behavior="read_only",
                grounding_pattern="query_only_multi_kind",
                constraint_profile="deterministic_kind_order",
                difficulty="constrained",
                ambiguity="deterministic_multi_result",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="workspace_task_creation",
                required_tools=(
                    "search_workspace_items",
                    "create_workspace_task",
                ),
                state_behavior="state_changing",
                grounding_pattern="project_to_new_task",
                constraint_profile="project_priority_due_binding",
                difficulty="intermediate",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="workspace_comment_update",
                required_tools=(
                    "search_workspace_items",
                    "add_workspace_comment",
                ),
                state_behavior="state_changing",
                grounding_pattern="task_to_comment",
                constraint_profile="task_and_comment_binding",
                difficulty="intermediate",
                ambiguity="none",
                recovery="none",
            ),
            CoverageCompatibilityConstraint(
                task_type="workspace_item_search",
                required_tools=("search_workspace_items",),
                state_behavior="read_only",
                grounding_pattern="wrong_kind_then_comment",
                constraint_profile="ordered_fallback",
                difficulty="recovery",
                ambiguity="missing_direct_task",
                recovery="comment_search",
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
            CoverageDifficultySemantics("intermediate", 2, 3, 1, "none", 0),
            CoverageDifficultySemantics(
                "recovery",
                1,
                2,
                0,
                "missing_direct_task",
                1,
            ),
        ),
    )


def workspace_representative_coverage_catalog() -> CoverageCatalog:
    base = workspace_coverage_catalog()
    exact, multi_result, create_task, add_comment, recovery = base.cells
    expanded_exact_indices = (
        *exact.grounding_unit_indices,
        *range(7, len(_EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS)),
    )
    expanded_project_indices = (*create_task.grounding_unit_indices, 7, 8, 9, 10)
    expanded_task_indices = (*add_comment.grounding_unit_indices, 11, 12, 13, 14)
    return replace(
        base,
        version=WORKSPACE_COVERAGE_CATALOG_VERSION_V2,
        grounding_context_sizes={
            "workspace_items": len(_EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS)
        },
        cells=(
            replace(
                exact,
                grounding_unit_indices=expanded_exact_indices,
                grounding_unit_ids=tuple(
                    _EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS[index]
                    for index in expanded_exact_indices
                ),
            ),
            multi_result,
            replace(
                create_task,
                grounding_unit_indices=expanded_project_indices,
                grounding_unit_ids=tuple(
                    _EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS[index]
                    for index in expanded_project_indices
                ),
            ),
            replace(
                add_comment,
                grounding_unit_indices=expanded_task_indices,
                grounding_unit_ids=tuple(
                    _EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS[index]
                    for index in expanded_task_indices
                ),
            ),
            recovery,
        ),
    )


def workspace_structural_coverage_catalog() -> CoverageCatalog:
    base = workspace_representative_coverage_catalog()
    scenarios = (
        (7, "correct_item_kind"),
        (8, "correct_query"),
        (9, "replace_item_id_query"),
        (10, "remove_extra_query_term"),
        (11, "restore_query_token_order"),
        (12, "remove_literal_quotes"),
        (13, "correct_kind_and_query"),
        (15, "restore_document_kind"),
    )
    recovery_cells = tuple(
        _workspace_recovery_cell(
            grounding_index=index,
            scenario=scenario,
        )
        for index, scenario in scenarios
    )
    return replace(
        base,
        version=WORKSPACE_COVERAGE_CATALOG_VERSION_V3,
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
                "invalid_workspace_selector",
                1,
            ),
        ),
        validate_grounding_identities=True,
    )


def _workspace_recovery_cell(
    *,
    grounding_index: int,
    scenario: str,
) -> CoverageCell:
    from synthesis.workspace_tasks import (
        WORKSPACE_REPRESENTATIVE_ITEM_GROUNDING_ARGUMENTS,
    )

    fallback_arguments: dict[str, object] = dict(
        WORKSPACE_REPRESENTATIVE_ITEM_GROUNDING_ARGUMENTS[grounding_index]
    )
    grounding_unit_id = _EXPANDED_WORKSPACE_GROUNDING_UNIT_IDS[grounding_index]
    direct_arguments = _invalid_workspace_selector(
        fallback_arguments,
        grounding_unit_id,
        scenario,
    )
    return CoverageCell(
        cell_id=f"workspace.recover_{scenario}",
        dimensions={
            "task_type": "workspace_item_search",
            "required_tools": ("search_workspace_items",),
            "state_behavior": "read_only",
            "grounding_pattern": f"{scenario}_then_observed_selector",
            "constraint_profile": "observed_failure_then_exact_selector",
            "difficulty": "selector_recovery",
            "ambiguity": "invalid_workspace_selector",
            "recovery": scenario,
        },
        grounding_capacity_key="workspace_items",
        grounding_unit_indices=(grounding_index,),
        grounding_unit_ids=(grounding_unit_id,),
        required_features=("enable_branching",),
        branch_plan={
            "schema_version": "branch_plan_v1",
            "plan_id": f"branch_plan_workspace_{scenario}",
            "max_depth": 2,
            "branches": [
                {
                    "branch_id": "invalid_selector",
                    "node_type": "attempt",
                    "parent_id": None,
                    "condition": f"Try the {scenario} selector first.",
                    "steps": [
                        {
                            "tool_name": "search_workspace_items",
                            "arguments": direct_arguments,
                        }
                    ],
                    "final_response_template": (
                        "Workspace item {item_id}: {summary}"
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
                            "tool_name": "search_workspace_items",
                            "arguments": fallback_arguments,
                        }
                    ],
                    "final_response_template": (
                        "Workspace item {item_id}: {summary}"
                    ),
                    "terminal_outcome": "accept_on_success",
                },
            ],
        },
    )


def _invalid_workspace_selector(
    fallback: Mapping[str, object],
    grounding_unit_id: str,
    scenario: str,
) -> dict[str, object]:
    query = str(fallback["query"])
    kind = str(fallback["kind"])
    wrong_kind = "task" if kind != "task" else "document"
    selectors: dict[str, dict[str, object]] = {
        "correct_item_kind": {"query": query, "kind": wrong_kind},
        "correct_query": {"query": "missing workspace phrase", "kind": kind},
        "replace_item_id_query": {"query": grounding_unit_id, "kind": kind},
        "remove_extra_query_term": {
            "query": query + " nonexistent",
            "kind": kind,
        },
        "restore_query_token_order": {
            "query": " ".join(reversed(query.split())),
            "kind": kind,
        },
        "remove_literal_quotes": {"query": f'"{query}"', "kind": kind},
        "correct_kind_and_query": {
            "query": "missing workspace phrase",
            "kind": wrong_kind,
        },
        "restore_document_kind": {"query": query, "kind": "task"},
    }
    return selectors[scenario]


def workspace_coverage_version_registry() -> CoverageVersionRegistry:
    return CoverageVersionRegistry(
        schema_version=COVERAGE_VERSION_REGISTRY_VERSION,
        catalog_versions=(
            (WORKSPACE_COVERAGE_CATALOG_ID, WORKSPACE_COVERAGE_CATALOG_VERSION),
            (
                WORKSPACE_COVERAGE_CATALOG_ID,
                WORKSPACE_COVERAGE_CATALOG_VERSION_V2,
            ),
            (
                WORKSPACE_COVERAGE_CATALOG_ID,
                WORKSPACE_COVERAGE_CATALOG_VERSION_V3,
            ),
        ),
        profile_versions=(
            (WORKSPACE_SMOKE_PROFILE_ID, WORKSPACE_SMOKE_PROFILE_VERSION),
            (
                WORKSPACE_REPRESENTATIVE_PROFILE_ID,
                WORKSPACE_REPRESENTATIVE_PROFILE_VERSION,
            ),
            (
                WORKSPACE_REPRESENTATIVE_PROFILE_ID,
                WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V2,
            ),
            (
                WORKSPACE_REPRESENTATIVE_PROFILE_ID,
                WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V3,
            ),
        ),
    )


def resolve_workspace_coverage_profile(
    profile_id: str,
    version: str,
) -> CoverageProfile:
    common = {
        "workspace.search_exact_kind": 1,
        "workspace.search_deterministic_multi_kind": 1,
        "workspace.create_task_in_project": 1,
        "workspace.comment_on_task": 1,
        "workspace.search_with_kind_fallback": 1,
    }
    profiles = {
        (
            WORKSPACE_SMOKE_PROFILE_ID,
            WORKSPACE_SMOKE_PROFILE_VERSION,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=WORKSPACE_SMOKE_PROFILE_ID,
            version=WORKSPACE_SMOKE_PROFILE_VERSION,
            catalog_id=WORKSPACE_COVERAGE_CATALOG_ID,
            catalog_version=WORKSPACE_COVERAGE_CATALOG_VERSION,
            mandatory_floors={
                "workspace.search_exact_kind": 1,
                "workspace.create_task_in_project": 1,
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
            WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            WORKSPACE_REPRESENTATIVE_PROFILE_VERSION,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            version=WORKSPACE_REPRESENTATIVE_PROFILE_VERSION,
            catalog_id=WORKSPACE_COVERAGE_CATALOG_ID,
            catalog_version=WORKSPACE_COVERAGE_CATALOG_VERSION,
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
            WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V2,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            version=WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V2,
            catalog_id=WORKSPACE_COVERAGE_CATALOG_ID,
            catalog_version=WORKSPACE_COVERAGE_CATALOG_VERSION_V2,
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
            WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V3,
        ): CoverageProfile(
            schema_version=COVERAGE_PROFILE_SCHEMA_VERSION,
            profile_id=WORKSPACE_REPRESENTATIVE_PROFILE_ID,
            version=WORKSPACE_REPRESENTATIVE_PROFILE_VERSION_V3,
            catalog_id=WORKSPACE_COVERAGE_CATALOG_ID,
            catalog_version=WORKSPACE_COVERAGE_CATALOG_VERSION_V3,
            mandatory_floors={
                "workspace.search_exact_kind": 1,
                "workspace.search_deterministic_multi_kind": 1,
                "workspace.create_task_in_project": 1,
                "workspace.comment_on_task": 1,
                "workspace.search_with_kind_fallback": 1,
            },
            balance_weights={
                cell.cell_id: 1
                for cell in workspace_structural_coverage_catalog().cells
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
            f"unknown workspace coverage profile: {profile_id}@{version}"
        ) from exc


def build_workspace_coverage_capacity(
    *,
    workspace_item_count: int,
) -> AdmittedCoverageCapacity:
    if (
        not isinstance(workspace_item_count, int)
        or isinstance(workspace_item_count, bool)
        or workspace_item_count < 0
    ):
        raise CoveragePlanValidationError(
            "workspace admitted capacity must be a non-negative integer"
        )
    return AdmittedCoverageCapacity(
        schema_version=COVERAGE_CAPACITY_VERSION,
        domain_id="workspace_tasks_fixture",
        grounding_units={"workspace_items": workspace_item_count},
    )
