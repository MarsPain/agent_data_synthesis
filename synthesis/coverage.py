from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping


COVERAGE_CATALOG_VERSION = "coverage_catalog_v1"
COVERAGE_PROFILE_SCHEMA_VERSION = "coverage_profile_v1"
COVERAGE_CAPACITY_VERSION = "coverage_capacity_v1"
COVERAGE_PLAN_VERSION = "coverage_plan_v1"
COVERAGE_VERSION_REGISTRY_VERSION = "coverage_version_registry_v1"
SUPPORTED_COVERAGE_DIMENSIONS = frozenset(
    {
        "task_type",
        "required_tools",
        "state_behavior",
        "grounding_pattern",
        "constraint_profile",
        "difficulty",
        "ambiguity",
        "recovery",
    }
)


class CoveragePlanValidationError(ValueError):
    pass


CoverageDimensionValue = str | tuple[str, ...]


@dataclass(frozen=True)
class CoverageVersionRegistry:
    schema_version: str
    catalog_versions: tuple[tuple[str, str], ...]
    profile_versions: tuple[tuple[str, str], ...]

    def canonical(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "catalog_versions": [
                {"catalog_id": catalog_id, "version": version}
                for catalog_id, version in sorted(self.catalog_versions)
            ],
            "profile_versions": [
                {"profile_id": profile_id, "version": version}
                for profile_id, version in sorted(self.profile_versions)
            ],
        }


@dataclass(frozen=True)
class CoverageCell:
    cell_id: str
    dimensions: Mapping[str, CoverageDimensionValue]
    grounding_capacity_key: str
    grounding_unit_indices: tuple[int, ...]
    grounding_unit_ids: tuple[str, ...]
    required_features: tuple[str, ...] = ()
    max_accepted_samples: int | None = None
    branch_plan: Mapping[str, object] | None = None

    def canonical(self) -> dict[str, object]:
        dimensions: dict[str, object] = {}
        for key, value in sorted(self.dimensions.items()):
            dimensions[key] = list(value) if isinstance(value, tuple) else value
        record: dict[str, object] = {
            "cell_id": self.cell_id,
            "dimensions": dimensions,
            "grounding_capacity_key": self.grounding_capacity_key,
            "grounding_unit_indices": list(self.grounding_unit_indices),
            "grounding_unit_ids": list(self.grounding_unit_ids),
            "required_features": sorted(self.required_features),
        }
        if self.max_accepted_samples is not None:
            record["max_accepted_samples"] = self.max_accepted_samples
        if self.branch_plan is not None:
            record["branch_plan"] = dict(self.branch_plan)
        return record


@dataclass(frozen=True)
class CoverageCompatibilityConstraint:
    task_type: str
    required_tools: tuple[str, ...]
    state_behavior: str
    grounding_pattern: str
    constraint_profile: str
    difficulty: str
    ambiguity: str
    recovery: str

    def canonical(self) -> dict[str, object]:
        return {
            "task_type": self.task_type,
            "required_tools": list(self.required_tools),
            "state_behavior": self.state_behavior,
            "grounding_pattern": self.grounding_pattern,
            "constraint_profile": self.constraint_profile,
            "difficulty": self.difficulty,
            "ambiguity": self.ambiguity,
            "recovery": self.recovery,
        }


def compatibility_constraint_for_cell(
    cell: CoverageCell,
) -> CoverageCompatibilityConstraint:
    required_tools = cell.dimensions["required_tools"]
    if not isinstance(required_tools, tuple):
        raise CoveragePlanValidationError(
            f"coverage cell {cell.cell_id} required tools must be a tuple"
        )
    return CoverageCompatibilityConstraint(
        task_type=str(cell.dimensions["task_type"]),
        required_tools=required_tools,
        state_behavior=str(cell.dimensions["state_behavior"]),
        grounding_pattern=str(cell.dimensions["grounding_pattern"]),
        constraint_profile=str(cell.dimensions["constraint_profile"]),
        difficulty=str(cell.dimensions["difficulty"]),
        ambiguity=str(cell.dimensions["ambiguity"]),
        recovery=str(cell.dimensions["recovery"]),
    )


@dataclass(frozen=True)
class CoverageDifficultySemantics:
    difficulty: str
    tool_count: int
    constraint_count: int
    state_changes: int
    ambiguity: str
    recovery_paths: int

    def canonical(self) -> dict[str, object]:
        return {
            "difficulty": self.difficulty,
            "tool_count": self.tool_count,
            "constraint_count": self.constraint_count,
            "state_changes": self.state_changes,
            "ambiguity": self.ambiguity,
            "recovery_paths": self.recovery_paths,
        }


@dataclass(frozen=True)
class CoverageCatalog:
    schema_version: str
    catalog_id: str
    version: str
    domain_id: str
    dimensions: tuple[str, ...]
    grounding_context_sizes: Mapping[str, int]
    cells: tuple[CoverageCell, ...]
    compatibility_constraints: tuple[CoverageCompatibilityConstraint, ...]
    difficulty_semantics: tuple[CoverageDifficultySemantics, ...]
    validate_grounding_identities: bool = False

    def canonical(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": self.schema_version,
            "catalog_id": self.catalog_id,
            "version": self.version,
            "domain_id": self.domain_id,
            "dimensions": sorted(self.dimensions),
            "grounding_context_sizes": dict(
                sorted(self.grounding_context_sizes.items())
            ),
            "compatibility_constraints": [
                constraint.canonical()
                for constraint in sorted(
                    self.compatibility_constraints,
                    key=lambda item: (
                        item.task_type,
                        item.grounding_pattern,
                        item.constraint_profile,
                        item.difficulty,
                        item.ambiguity,
                        item.recovery,
                    ),
                )
            ],
            "difficulty_semantics": [
                semantics.canonical()
                for semantics in sorted(
                    self.difficulty_semantics,
                    key=lambda item: item.difficulty,
                )
            ],
            "cells": [
                cell.canonical()
                for cell in sorted(self.cells, key=lambda item: item.cell_id)
            ],
        }
        if self.validate_grounding_identities:
            record["validate_grounding_identities"] = True
        return record


@dataclass(frozen=True)
class CoverageAttemptPolicy:
    policy_version: str
    multiplier_numerator: int
    multiplier_denominator: int

    def canonical(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "multiplier_numerator": self.multiplier_numerator,
            "multiplier_denominator": self.multiplier_denominator,
        }


@dataclass(frozen=True)
class CoverageProfile:
    schema_version: str
    profile_id: str
    version: str
    catalog_id: str
    catalog_version: str
    mandatory_floors: Mapping[str, int]
    balance_weights: Mapping[str, int]
    max_accepted_samples_per_grounding_unit: int
    attempt_policy: CoverageAttemptPolicy
    max_balance_weight_override: int

    def canonical(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "version": self.version,
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "mandatory_floors": dict(sorted(self.mandatory_floors.items())),
            "balance_weights": dict(sorted(self.balance_weights.items())),
            "grounding_reuse": {
                "policy_version": "grounding_reuse_v1",
                "max_accepted_samples_per_grounding_unit": (
                    self.max_accepted_samples_per_grounding_unit
                ),
            },
            "attempt_policy": self.attempt_policy.canonical(),
            "override_policy": {
                "allowed_keys": ["balance_weights"],
                "max_balance_weight": self.max_balance_weight_override,
            },
        }


@dataclass(frozen=True)
class AdmittedCoverageCapacity:
    schema_version: str
    domain_id: str
    grounding_units: Mapping[str, int]

    def canonical(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain_id": self.domain_id,
            "grounding_units": [
                {"capacity_key": key, "unit_count": value}
                for key, value in sorted(self.grounding_units.items())
            ],
        }


@dataclass(frozen=True)
class CoveragePlan:
    schema_version: str
    plan_id: str
    plan_hash: str
    domain_id: str
    catalog: Mapping[str, object]
    coverage_profile: Mapping[str, object]
    selected_features: tuple[str, ...]
    target_accepted_sample_count: int
    target_candidate_count: int
    target_distribution: tuple[Mapping[str, object], ...]
    attempt_ceiling: int
    policies: Mapping[str, object]
    cell_requirements: tuple[Mapping[str, object], ...]
    overrides: Mapping[str, object]
    admitted_capacity: Mapping[str, object]

    def canonical(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "domain_id": self.domain_id,
            "catalog": dict(self.catalog),
            "coverage_profile": dict(self.coverage_profile),
            "selected_features": list(self.selected_features),
            "target_accepted_sample_count": self.target_accepted_sample_count,
            "target_candidate_count": self.target_candidate_count,
            "target_distribution": [
                dict(item) for item in self.target_distribution
            ],
            "attempt_ceiling": self.attempt_ceiling,
            "policies": dict(self.policies),
            "cell_requirements": [
                dict(item) for item in self.cell_requirements
            ],
            "overrides": dict(self.overrides),
            "admitted_capacity": dict(self.admitted_capacity),
        }

    def to_bytes(self) -> bytes:
        return (canonical_coverage_json(self.canonical()) + "\n").encode("utf-8")


def write_coverage_plan(path: Path, plan: CoveragePlan) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plan.to_bytes())
    return output_path


def compile_coverage_plan(
    *,
    catalog: CoverageCatalog,
    coverage_profile: CoverageProfile,
    version_registry: CoverageVersionRegistry,
    selected_features: tuple[str, ...],
    target_accepted_sample_count: int,
    target_candidate_count: int,
    admitted_capacity: AdmittedCoverageCapacity,
    balance_weight_overrides: Mapping[str, int] | None = None,
) -> CoveragePlan:
    _validate_compilation_inputs(
        catalog=catalog,
        coverage_profile=coverage_profile,
        version_registry=version_registry,
        selected_features=selected_features,
        target_accepted_sample_count=target_accepted_sample_count,
        target_candidate_count=target_candidate_count,
        admitted_capacity=admitted_capacity,
    )
    attempt_policy = coverage_profile.attempt_policy
    attempt_ceiling = (
        target_accepted_sample_count * attempt_policy.multiplier_numerator
        + attempt_policy.multiplier_denominator
        - 1
    ) // attempt_policy.multiplier_denominator
    if target_candidate_count != attempt_ceiling:
        raise CoveragePlanValidationError(
            "target candidate count must equal the profile-derived attempt ceiling"
        )
    cells = {cell.cell_id: cell for cell in catalog.cells}
    weights = dict(coverage_profile.balance_weights)
    overrides = dict(balance_weight_overrides or {})
    for cell_id, weight in overrides.items():
        if cell_id not in weights:
            raise CoveragePlanValidationError(
                f"unknown balance-weight override cell: {cell_id}"
            )
        if (
            not isinstance(weight, int)
            or isinstance(weight, bool)
            or weight <= 0
            or weight > coverage_profile.max_balance_weight_override
        ):
            raise CoveragePlanValidationError(
                f"balance-weight override for {cell_id} must be between 1 and "
                f"{coverage_profile.max_balance_weight_override}"
            )
        weights[cell_id] = weight

    selected_feature_set = set(selected_features)
    for cell_id in tuple(weights):
        unavailable = sorted(
            set(cells[cell_id].required_features) - selected_feature_set
        )
        if unavailable:
            if (
                coverage_profile.mandatory_floors.get(cell_id, 0) > 0
                or cell_id in overrides
            ):
                raise CoveragePlanValidationError(
                    f"coverage cell {cell_id} requires unavailable features: "
                    + ", ".join(unavailable)
                )
            del weights[cell_id]

    target_counts = dict(coverage_profile.mandatory_floors)
    floor_total = sum(target_counts.values())
    if floor_total > target_accepted_sample_count:
        raise CoveragePlanValidationError(
            "mandatory floors exceed target accepted-sample count"
        )
    _validate_counts_fit_capacity(
        target_counts,
        cells=cells,
        admitted_capacity=admitted_capacity,
        reuse_limit=coverage_profile.max_accepted_samples_per_grounding_unit,
        label="mandatory floors",
    )
    for _ in range(target_accepted_sample_count - floor_total):
        eligible = [
            cell_id
            for cell_id in sorted(weights)
            if _can_increment(
                cell_id,
                target_counts,
                cells=cells,
                admitted_capacity=admitted_capacity,
                reuse_limit=coverage_profile.max_accepted_samples_per_grounding_unit,
            )
        ]
        if not eligible:
            raise CoveragePlanValidationError(
                "admitted environment capacity is insufficient for the target "
                "accepted-sample count"
            )
        selected_cell_id = min(
            eligible,
            key=lambda cell_id: (
                Fraction(target_counts.get(cell_id, 0), weights[cell_id]),
                cell_id,
            ),
        )
        target_counts[selected_cell_id] = target_counts.get(selected_cell_id, 0) + 1

    catalog_hash = canonical_coverage_hash(catalog.canonical())
    profile_hash = canonical_coverage_hash(coverage_profile.canonical())
    capacity_hash = canonical_coverage_hash(admitted_capacity.canonical())
    payload: dict[str, object] = {
        "schema_version": COVERAGE_PLAN_VERSION,
        "domain_id": catalog.domain_id,
        "catalog": {
            "schema_version": catalog.schema_version,
            "catalog_id": catalog.catalog_id,
            "version": catalog.version,
            "catalog_hash": catalog_hash,
        },
        "coverage_profile": {
            "schema_version": coverage_profile.schema_version,
            "profile_id": coverage_profile.profile_id,
            "version": coverage_profile.version,
            "profile_hash": profile_hash,
        },
        "selected_features": sorted(selected_features),
        "target_accepted_sample_count": target_accepted_sample_count,
        "target_candidate_count": target_candidate_count,
        "target_distribution": [
            {
                "cell_id": cell_id,
                "mandatory_floor": coverage_profile.mandatory_floors.get(cell_id, 0),
                "balance_weight": weights[cell_id],
                "target_count": target_counts.get(cell_id, 0),
            }
            for cell_id in sorted(weights)
        ],
        "attempt_ceiling": attempt_ceiling,
        "policies": {
            "mandatory_floors": {
                "policy_version": "mandatory_floors_v1",
                "total_floor": floor_total,
            },
            "balancing": {
                "policy_version": "weighted_lowest_saturation_v1",
                "tie_break": "cell_id_ascending",
            },
            "grounding_reuse": {
                "policy_version": "grounding_reuse_v1",
                "max_accepted_samples_per_grounding_unit": (
                    coverage_profile.max_accepted_samples_per_grounding_unit
                ),
            },
            "attempts": attempt_policy.canonical(),
        },
        "cell_requirements": [
            {
                "cell_id": cell_id,
                "required_features": sorted(cells[cell_id].required_features),
            }
            for cell_id in sorted(weights)
        ],
        "overrides": {
            "balance_weights": dict(sorted(overrides.items())),
        },
        "admitted_capacity": {
            "schema_version": admitted_capacity.schema_version,
            "capacity_hash": capacity_hash,
            "grounding_units": admitted_capacity.canonical()["grounding_units"],
        },
    }
    plan_hash = canonical_coverage_hash(payload)
    catalog_record = payload["catalog"]
    profile_record = payload["coverage_profile"]
    target_distribution = payload["target_distribution"]
    policies = payload["policies"]
    cell_requirements = payload["cell_requirements"]
    overrides_record = payload["overrides"]
    capacity_record = payload["admitted_capacity"]
    assert isinstance(catalog_record, Mapping)
    assert isinstance(profile_record, Mapping)
    assert isinstance(target_distribution, list)
    assert isinstance(policies, Mapping)
    assert isinstance(cell_requirements, list)
    assert isinstance(overrides_record, Mapping)
    assert isinstance(capacity_record, Mapping)
    return CoveragePlan(
        schema_version=COVERAGE_PLAN_VERSION,
        plan_id=f"coverage_plan_{plan_hash.removeprefix('sha256:')[:16]}",
        plan_hash=plan_hash,
        domain_id=catalog.domain_id,
        catalog=catalog_record,
        coverage_profile=profile_record,
        selected_features=tuple(sorted(selected_features)),
        target_accepted_sample_count=target_accepted_sample_count,
        target_candidate_count=target_candidate_count,
        target_distribution=tuple(target_distribution),
        attempt_ceiling=attempt_ceiling,
        policies=policies,
        cell_requirements=tuple(cell_requirements),
        overrides=overrides_record,
        admitted_capacity=capacity_record,
    )


def _validate_compilation_inputs(
    *,
    catalog: CoverageCatalog,
    coverage_profile: CoverageProfile,
    version_registry: CoverageVersionRegistry,
    selected_features: tuple[str, ...],
    target_accepted_sample_count: int,
    target_candidate_count: int,
    admitted_capacity: AdmittedCoverageCapacity,
) -> None:
    if catalog.schema_version != COVERAGE_CATALOG_VERSION:
        raise CoveragePlanValidationError("unknown coverage catalog schema version")
    if coverage_profile.schema_version != COVERAGE_PROFILE_SCHEMA_VERSION:
        raise CoveragePlanValidationError("unknown coverage profile schema version")
    if admitted_capacity.schema_version != COVERAGE_CAPACITY_VERSION:
        raise CoveragePlanValidationError("unknown coverage capacity schema version")
    if version_registry.schema_version != COVERAGE_VERSION_REGISTRY_VERSION:
        raise CoveragePlanValidationError(
            "unknown coverage version registry schema version"
        )
    _validate_version_registry(version_registry)
    _require_non_empty_string(catalog.catalog_id, "coverage catalog id")
    _require_non_empty_string(catalog.version, "coverage catalog version")
    _require_non_empty_string(catalog.domain_id, "coverage catalog domain")
    if (catalog.catalog_id, catalog.version) not in set(
        version_registry.catalog_versions
    ):
        raise CoveragePlanValidationError(
            f"unknown coverage catalog version: {catalog.version}"
        )
    _require_non_empty_string(coverage_profile.profile_id, "coverage profile id")
    _require_non_empty_string(coverage_profile.version, "coverage profile version")
    if (coverage_profile.profile_id, coverage_profile.version) not in set(
        version_registry.profile_versions
    ):
        raise CoveragePlanValidationError(
            f"unknown coverage profile version: {coverage_profile.version}"
        )
    if catalog.domain_id != admitted_capacity.domain_id:
        raise CoveragePlanValidationError("coverage capacity domain does not match catalog")
    if (
        coverage_profile.catalog_id != catalog.catalog_id
        or coverage_profile.catalog_version != catalog.version
    ):
        raise CoveragePlanValidationError(
            "coverage profile catalog identity does not match the selected catalog"
        )
    unknown_dimensions = sorted(set(catalog.dimensions) - SUPPORTED_COVERAGE_DIMENSIONS)
    if unknown_dimensions:
        raise CoveragePlanValidationError(
            "unknown coverage dimensions: " + ", ".join(unknown_dimensions)
        )
    if len(catalog.dimensions) != len(set(catalog.dimensions)):
        raise CoveragePlanValidationError("coverage catalog dimensions must be unique")
    if not catalog.cells:
        raise CoveragePlanValidationError("coverage catalog cells must not be empty")
    capacity_keys = {
        cell.grounding_capacity_key
        for cell in catalog.cells
    }
    if set(catalog.grounding_context_sizes) != capacity_keys:
        raise CoveragePlanValidationError(
            "coverage catalog grounding context sizes do not match capacity keys"
        )
    if any(
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        for size in catalog.grounding_context_sizes.values()
    ):
        raise CoveragePlanValidationError(
            "coverage catalog grounding context sizes must be positive integers"
        )
    cell_ids: set[str] = set()
    cell_signatures: set[str] = set()
    grounding_ids_by_index: dict[tuple[str, int], str] = {}
    for cell in catalog.cells:
        _require_non_empty_string(cell.cell_id, "coverage cell id")
        _require_non_empty_string(
            cell.grounding_capacity_key,
            f"coverage cell {cell.cell_id} capacity key",
        )
        if cell.cell_id in cell_ids:
            raise CoveragePlanValidationError(
                f"duplicate coverage cell id: {cell.cell_id}"
            )
        cell_ids.add(cell.cell_id)
        if set(cell.dimensions) != set(catalog.dimensions):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} dimensions do not match the catalog"
            )
        for dimension, value in cell.dimensions.items():
            _validate_dimension_value(
                value,
                field_name=f"coverage cell {cell.cell_id} dimension {dimension}",
            )
        if len(cell.required_features) != len(set(cell.required_features)):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} required features must be unique"
            )
        for feature in cell.required_features:
            _require_non_empty_string(
                feature,
                f"coverage cell {cell.cell_id} required feature",
            )
        signature = canonical_coverage_json(cell.canonical()["dimensions"])
        if signature in cell_signatures:
            raise CoveragePlanValidationError(
                f"duplicate coverage cell dimensions: {cell.cell_id}"
            )
        cell_signatures.add(signature)
        if cell.grounding_capacity_key not in admitted_capacity.grounding_units:
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} has no admitted capacity"
            )
        if (
            not isinstance(cell.grounding_unit_indices, tuple)
            or not cell.grounding_unit_indices
            or len(cell.grounding_unit_indices)
            != len(set(cell.grounding_unit_indices))
            or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
                for index in cell.grounding_unit_indices
            )
        ):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} grounding unit indices are invalid"
            )
        if (
            not isinstance(cell.grounding_unit_ids, tuple)
            or len(cell.grounding_unit_ids) != len(cell.grounding_unit_indices)
            or any(
                not isinstance(unit_id, str) or not unit_id
                for unit_id in cell.grounding_unit_ids
            )
        ):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} grounding unit ids are invalid"
            )
        grounding_context_size = catalog.grounding_context_sizes[
            cell.grounding_capacity_key
        ]
        for grounding_index, grounding_unit_id in zip(
            cell.grounding_unit_indices,
            cell.grounding_unit_ids,
        ):
            if grounding_index >= grounding_context_size:
                raise CoveragePlanValidationError(
                    f"coverage cell {cell.cell_id} grounding unit index "
                    "exceeds declared grounding context size"
                )
            identity_key = (
                cell.grounding_capacity_key,
                grounding_index,
            )
            known_unit_id = grounding_ids_by_index.setdefault(
                identity_key,
                grounding_unit_id,
            )
            if known_unit_id != grounding_unit_id:
                raise CoveragePlanValidationError(
                    "coverage grounding index has conflicting stable unit ids"
                )
        if cell.max_accepted_samples is not None and (
            not isinstance(cell.max_accepted_samples, int)
            or isinstance(cell.max_accepted_samples, bool)
            or cell.max_accepted_samples <= 0
        ):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} max accepted samples must be positive"
            )
    _validate_catalog_semantics(catalog)
    profile_cells = set(coverage_profile.balance_weights)
    if not profile_cells or not profile_cells <= cell_ids:
        raise CoveragePlanValidationError(
            "coverage profile balance weights contain unknown or no cells"
        )
    if not set(coverage_profile.mandatory_floors) <= profile_cells:
        raise CoveragePlanValidationError(
            "mandatory floors must reference balanced coverage cells"
        )
    for label, values, allow_zero in (
        ("mandatory floor", coverage_profile.mandatory_floors, True),
        ("balance weight", coverage_profile.balance_weights, False),
    ):
        for cell_id, policy_value in values.items():
            if (
                not isinstance(policy_value, int)
                or isinstance(policy_value, bool)
                or policy_value < (0 if allow_zero else 1)
            ):
                raise CoveragePlanValidationError(
                    f"{label} for {cell_id} is invalid"
                )
    if (
        not isinstance(target_accepted_sample_count, int)
        or isinstance(target_accepted_sample_count, bool)
        or target_accepted_sample_count <= 0
    ):
        raise CoveragePlanValidationError(
            "target accepted-sample count must be a positive integer"
        )
    if (
        not isinstance(target_candidate_count, int)
        or isinstance(target_candidate_count, bool)
        or target_candidate_count <= 0
    ):
        raise CoveragePlanValidationError(
            "target candidate count must be a positive integer"
        )
    if len(selected_features) != len(set(selected_features)):
        raise CoveragePlanValidationError("selected features must be unique")
    if any(not isinstance(feature, str) or not feature for feature in selected_features):
        raise CoveragePlanValidationError(
            "selected features must be non-empty strings"
        )
    if not _is_positive_int(
        coverage_profile.max_accepted_samples_per_grounding_unit
    ):
        raise CoveragePlanValidationError(
            "grounding reuse limit must be a positive integer"
        )
    if not _is_positive_int(coverage_profile.max_balance_weight_override):
        raise CoveragePlanValidationError(
            "balance-weight override limit must be a positive integer"
        )
    attempt_policy = coverage_profile.attempt_policy
    if not (
        _is_positive_int(attempt_policy.multiplier_numerator)
        and _is_positive_int(attempt_policy.multiplier_denominator)
    ):
        raise CoveragePlanValidationError(
            "attempt policy multipliers must be positive integers"
        )
    if (
        attempt_policy.policy_version != "bounded_attempt_ratio_v1"
        or attempt_policy.multiplier_numerator < attempt_policy.multiplier_denominator
    ):
        raise CoveragePlanValidationError(
            "attempt policy contradicts the accepted-sample target"
        )
    for key, capacity_value in admitted_capacity.grounding_units.items():
        if not isinstance(key, str) or not key:
            raise CoveragePlanValidationError("capacity keys must be non-empty strings")
        if (
            not isinstance(capacity_value, int)
            or isinstance(capacity_value, bool)
            or capacity_value < 0
        ):
            raise CoveragePlanValidationError(
                f"admitted capacity for {key} must be a non-negative integer"
            )


def _validate_counts_fit_capacity(
    counts: Mapping[str, int],
    *,
    cells: Mapping[str, CoverageCell],
    admitted_capacity: AdmittedCoverageCapacity,
    reuse_limit: int,
    label: str,
) -> None:
    counts_by_capacity_key: dict[str, int] = {}
    for cell_id, count in counts.items():
        cell = cells[cell_id]
        cell_capacity = _cell_usable_capacity(cell, reuse_limit)
        if count > cell_capacity:
            raise CoveragePlanValidationError(
                f"{label} exceed the maximum for coverage cell {cell_id}"
            )
        counts_by_capacity_key[cell.grounding_capacity_key] = (
            counts_by_capacity_key.get(cell.grounding_capacity_key, 0) + count
        )
    for capacity_key, count in counts_by_capacity_key.items():
        available = admitted_capacity.grounding_units[capacity_key] * reuse_limit
        if count > available:
            raise CoveragePlanValidationError(
                f"{label} exceed admitted capacity for {capacity_key}"
            )
    if allocate_coverage_grounding_indices(
        counts,
        cells=cells,
        reuse_limit=reuse_limit,
    ) is None:
        raise CoveragePlanValidationError(
            f"{label} exceed declared usable grounding capacity"
        )


def _can_increment(
    cell_id: str,
    counts: Mapping[str, int],
    *,
    cells: Mapping[str, CoverageCell],
    admitted_capacity: AdmittedCoverageCapacity,
    reuse_limit: int,
) -> bool:
    cell = cells[cell_id]
    next_count = counts.get(cell_id, 0) + 1
    if next_count > _cell_usable_capacity(cell, reuse_limit):
        return False
    capacity_key = cell.grounding_capacity_key
    current_for_key = sum(
        count
        for counted_cell_id, count in counts.items()
        if cells[counted_cell_id].grounding_capacity_key == capacity_key
    )
    if (
        current_for_key + 1
        > admitted_capacity.grounding_units[capacity_key] * reuse_limit
    ):
        return False
    proposed_counts = dict(counts)
    proposed_counts[cell_id] = next_count
    return (
        allocate_coverage_grounding_indices(
            proposed_counts,
            cells=cells,
            reuse_limit=reuse_limit,
        )
        is not None
    )


def _cell_usable_capacity(cell: CoverageCell, reuse_limit: int) -> int:
    grounding_capacity = len(set(cell.grounding_unit_ids)) * reuse_limit
    if cell.max_accepted_samples is None:
        return grounding_capacity
    return min(grounding_capacity, cell.max_accepted_samples)


def allocate_coverage_grounding_indices(
    counts: Mapping[str, int],
    *,
    cells: Mapping[str, CoverageCell],
    reuse_limit: int,
) -> dict[str, tuple[int, ...]] | None:
    tokens = [
        (cell_id, ordinal)
        for cell_id, count in counts.items()
        for ordinal in range(count)
    ]
    tokens.sort(
        key=lambda token: (
            len(set(cells[token[0]].grounding_unit_ids)),
            token[0],
            token[1],
        )
    )
    slot_owner: dict[tuple[str, str, int], tuple[str, int]] = {}
    token_slot: dict[tuple[str, int], tuple[str, str, int]] = {}
    token_index_by_slot: dict[
        tuple[tuple[str, int], tuple[str, str, int]],
        int,
    ] = {}

    def assign(
        token: tuple[str, int],
        seen_slots: set[tuple[str, str, int]],
    ) -> bool:
        cell = cells[token[0]]
        options = sorted(
            zip(cell.grounding_unit_ids, cell.grounding_unit_indices),
            key=lambda item: (item[0], item[1]),
        )
        for unit_id, grounding_index in options:
            for reuse_ordinal in range(reuse_limit):
                slot = (
                    cell.grounding_capacity_key,
                    unit_id,
                    reuse_ordinal,
                )
                if slot in seen_slots:
                    continue
                seen_slots.add(slot)
                owner = slot_owner.get(slot)
                if owner is None or assign(owner, seen_slots):
                    slot_owner[slot] = token
                    token_slot[token] = slot
                    token_index_by_slot[(token, slot)] = grounding_index
                    return True
        return False

    for token in tokens:
        if not assign(token, set()):
            return None

    allocation: dict[str, list[int]] = {
        cell_id: []
        for cell_id in counts
    }
    for cell_id, count in counts.items():
        for ordinal in range(count):
            token = (cell_id, ordinal)
            slot = token_slot[token]
            allocation[cell_id].append(token_index_by_slot[(token, slot)])
    return {
        cell_id: tuple(indices)
        for cell_id, indices in allocation.items()
    }


def _validate_catalog_semantics(catalog: CoverageCatalog) -> None:
    if not catalog.compatibility_constraints:
        raise CoveragePlanValidationError(
            "coverage catalog compatibility constraints must not be empty"
        )
    constraint_signatures: set[str] = set()
    for declared_constraint in catalog.compatibility_constraints:
        _require_non_empty_string(
            declared_constraint.task_type,
            "coverage compatibility task type",
        )
        signature = canonical_coverage_json(declared_constraint.canonical())
        if signature in constraint_signatures:
            raise CoveragePlanValidationError(
                "coverage compatibility constraints must be unique"
            )
        constraint_signatures.add(signature)
        if (
            not isinstance(declared_constraint.required_tools, tuple)
            or not declared_constraint.required_tools
            or len(declared_constraint.required_tools)
            != len(set(declared_constraint.required_tools))
        ):
            raise CoveragePlanValidationError(
                "coverage compatibility required tools must contain unique values"
            )
        for tool_name in declared_constraint.required_tools:
            _require_non_empty_string(
                tool_name,
                "coverage compatibility required tool",
            )
        for label, value in (
            ("grounding pattern", declared_constraint.grounding_pattern),
            ("constraint profile", declared_constraint.constraint_profile),
            ("difficulty", declared_constraint.difficulty),
            ("ambiguity", declared_constraint.ambiguity),
            ("recovery", declared_constraint.recovery),
        ):
            _require_non_empty_string(
                value,
                f"coverage compatibility {label}",
            )
        if declared_constraint.state_behavior not in {
            "read_only",
            "state_changing",
        }:
            raise CoveragePlanValidationError(
                "coverage compatibility state behavior is invalid"
            )

    if not catalog.difficulty_semantics:
        raise CoveragePlanValidationError(
            "coverage catalog difficulty semantics must not be empty"
        )
    difficulty_by_name: dict[str, CoverageDifficultySemantics] = {}
    for declared_semantics in catalog.difficulty_semantics:
        _require_non_empty_string(
            declared_semantics.difficulty,
            "coverage difficulty name",
        )
        if declared_semantics.difficulty in difficulty_by_name:
            raise CoveragePlanValidationError(
                "coverage difficulty names must be unique"
            )
        difficulty_by_name[declared_semantics.difficulty] = declared_semantics
        if (
            not _is_positive_int(declared_semantics.tool_count)
            or not _is_positive_int(declared_semantics.constraint_count)
            or declared_semantics.state_changes not in {0, 1}
            or not isinstance(declared_semantics.recovery_paths, int)
            or isinstance(declared_semantics.recovery_paths, bool)
            or declared_semantics.recovery_paths < 0
        ):
            raise CoveragePlanValidationError(
                "coverage difficulty semantics are invalid: "
                f"{declared_semantics.difficulty}"
            )
        _require_non_empty_string(
            declared_semantics.ambiguity,
            f"coverage difficulty {declared_semantics.difficulty} ambiguity",
        )

    for cell in catalog.cells:
        matching_constraints = [
            constraint
            for constraint in catalog.compatibility_constraints
            if _cell_matches_constraint(cell, constraint)
        ]
        if len(matching_constraints) != 1:
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} violates compatibility constraints"
            )
        difficulty = str(cell.dimensions["difficulty"])
        semantics = difficulty_by_name.get(difficulty)
        if semantics is None:
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} has undeclared difficulty semantics"
            )
        if (
            semantics.tool_count != len(_dimension_tools(cell))
            or semantics.state_changes
            != int(cell.dimensions["state_behavior"] == "state_changing")
            or semantics.ambiguity != cell.dimensions["ambiguity"]
            or semantics.recovery_paths
            != int(cell.dimensions["recovery"] != "none")
        ):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} contradicts difficulty semantics"
            )
        has_recovery = cell.dimensions["recovery"] != "none"
        if has_recovery != (cell.branch_plan is not None):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} recovery declaration is incomplete"
            )
        if has_recovery and "enable_branching" not in cell.required_features:
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} recovery requires enable_branching"
            )
    matched_constraint_signatures = {
        canonical_coverage_json(constraint.canonical())
        for cell in catalog.cells
        for constraint in catalog.compatibility_constraints
        if _cell_matches_constraint(cell, constraint)
    }
    if matched_constraint_signatures != constraint_signatures:
        raise CoveragePlanValidationError(
            "coverage compatibility constraints include unreachable combinations"
        )


def _cell_matches_constraint(
    cell: CoverageCell,
    constraint: CoverageCompatibilityConstraint,
) -> bool:
    return (
        cell.dimensions["task_type"] == constraint.task_type
        and _dimension_tools(cell) == constraint.required_tools
        and cell.dimensions["state_behavior"] == constraint.state_behavior
        and cell.dimensions["grounding_pattern"] == constraint.grounding_pattern
        and cell.dimensions["constraint_profile"]
        == constraint.constraint_profile
        and cell.dimensions["difficulty"] == constraint.difficulty
        and cell.dimensions["ambiguity"] == constraint.ambiguity
        and cell.dimensions["recovery"] == constraint.recovery
    )


def _dimension_tools(cell: CoverageCell) -> tuple[str, ...]:
    tools = cell.dimensions["required_tools"]
    if not isinstance(tools, tuple):
        raise CoveragePlanValidationError(
            f"coverage cell {cell.cell_id} required tools must be a tuple"
        )
    return tools


def validate_coverage_catalog_reachability(
    catalog: CoverageCatalog,
    generation_spec: object,
    *,
    execute_tool: Callable[
        [str, dict[str, object]],
        dict[str, object],
    ] | None = None,
    require_executable_recovery: bool = True,
) -> None:
    from synthesis.contracts import validate_branch_plan_record
    from synthesis.domain_generation import (
        DomainGenerationSpec,
        validate_domain_generation_spec,
    )

    if not isinstance(generation_spec, DomainGenerationSpec):
        raise CoveragePlanValidationError(
            "coverage reachability requires a domain generation specification"
        )
    validate_domain_generation_spec(generation_spec)
    if catalog.domain_id != generation_spec.domain_id:
        raise CoveragePlanValidationError(
            "coverage catalog domain does not match generation specification"
        )
    task_types = {
        task_type.task_type: task_type
        for task_type in generation_spec.task_types
    }
    tools = {
        str(tool["name"]): tool
        for tool in generation_spec.tools
    }
    if len(generation_spec.grounding_context) != 1:
        raise CoveragePlanValidationError(
            "coverage catalog requires one grounding collection"
        )
    grounding_units = next(iter(generation_spec.grounding_context.values()))
    if not isinstance(grounding_units, list):
        raise CoveragePlanValidationError(
            "coverage catalog grounding collection must be a list"
        )
    if catalog.validate_grounding_identities:
        validate_coverage_catalog_grounding_identities(
            catalog,
            generation_spec,
        )
    for cell in catalog.cells:
        task_type = task_types.get(str(cell.dimensions["task_type"]))
        required_tools = _dimension_tools(cell)
        expected_state_behavior = (
            "state_changing"
            if any(
                tools.get(tool_name, {}).get("side_effects")
                == "state_mutating"
                for tool_name in required_tools
            )
            else "read_only"
        )
        unreachable = (
            task_type is None
            or task_type.required_tools != required_tools
            or any(tool_name not in tools for tool_name in required_tools)
            or cell.dimensions["state_behavior"] != expected_state_behavior
            or any(index >= len(grounding_units) for index in cell.grounding_unit_indices)
        )
        if cell.branch_plan is not None:
            try:
                validate_branch_plan_record(cell.branch_plan)
            except (TypeError, ValueError):
                unreachable = True
            if not _branch_plan_tools(cell.branch_plan) <= set(required_tools):
                unreachable = True
            if any(
                tools.get(tool_name, {}).get("side_effects") == "state_mutating"
                for tool_name in _branch_plan_tools(cell.branch_plan)
            ):
                unreachable = True
            if execute_tool is None:
                if require_executable_recovery:
                    raise CoveragePlanValidationError(
                        "coverage recovery reachability requires a tool executor"
                    )
            elif not _recovery_plan_is_executable(
                cell=cell,
                task_type=task_type,
                grounding_units=grounding_units,
                execute_tool=execute_tool,
            ):
                unreachable = True
        if unreachable:
            raise CoveragePlanValidationError(
                f"unreachable coverage cell {cell.cell_id}"
            )


def validate_coverage_catalog_grounding_identities(
    catalog: CoverageCatalog,
    generation_spec: object,
) -> None:
    from synthesis.domain_generation import DomainGenerationSpec

    if not isinstance(generation_spec, DomainGenerationSpec):
        raise CoveragePlanValidationError(
            "coverage grounding identity validation requires a domain "
            "generation specification"
        )
    if catalog.domain_id != generation_spec.domain_id:
        raise CoveragePlanValidationError(
            "coverage catalog domain does not match generation specification"
        )
    if len(generation_spec.grounding_context) != 1:
        raise CoveragePlanValidationError(
            "coverage catalog requires one grounding collection"
        )
    grounding_units = next(iter(generation_spec.grounding_context.values()))
    if not isinstance(grounding_units, list):
        raise CoveragePlanValidationError(
            "coverage catalog grounding collection must be a list"
        )

    for cell in catalog.cells:
        for grounding_index, declared_identity in zip(
            cell.grounding_unit_indices,
            cell.grounding_unit_ids,
            strict=True,
        ):
            if grounding_index >= len(grounding_units):
                raise CoveragePlanValidationError(
                    f"grounding identity mismatch for {cell.cell_id}"
                )
            grounding_unit = grounding_units[grounding_index]
            observation = (
                grounding_unit.get("observation")
                if isinstance(grounding_unit, Mapping)
                else None
            )
            observed_identity = _observed_grounding_identity(observation)
            if observed_identity != declared_identity:
                raise CoveragePlanValidationError(
                    f"grounding identity mismatch for {cell.cell_id}"
                )


def _observed_grounding_identity(observation: object) -> str | None:
    if not isinstance(observation, Mapping):
        return None
    for field_name in ("message_id", "item_id"):
        value = observation.get(field_name)
        if isinstance(value, str) and value:
            return value
    name = observation.get("name")
    if not isinstance(name, str) or not name:
        return None
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def _branch_plan_tools(branch_plan: Mapping[str, object]) -> set[str]:
    raw_branches = branch_plan.get("branches")
    if not isinstance(raw_branches, list):
        return set()
    tool_names: set[str] = set()
    for branch in raw_branches:
        if not isinstance(branch, Mapping):
            continue
        raw_steps = branch.get("steps")
        if not isinstance(raw_steps, list):
            continue
        for step in raw_steps:
            if isinstance(step, Mapping) and isinstance(step.get("tool_name"), str):
                tool_names.add(str(step["tool_name"]))
    return tool_names


def _recovery_plan_is_executable(
    *,
    cell: CoverageCell,
    task_type: object,
    grounding_units: list[object],
    execute_tool: Callable[
        [str, dict[str, object]],
        dict[str, object],
    ],
) -> bool:
    from synthesis.domain_generation import DomainTaskTypeSpec

    if (
        not isinstance(task_type, DomainTaskTypeSpec)
        or cell.branch_plan is None
        or len(cell.grounding_unit_indices) != 1
    ):
        return False
    grounding_record = grounding_units[cell.grounding_unit_indices[0]]
    if not isinstance(grounding_record, Mapping):
        return False
    expected_observation = grounding_record.get("observation")
    if not isinstance(expected_observation, Mapping):
        return False
    raw_branches = cell.branch_plan.get("branches")
    if not isinstance(raw_branches, list):
        return False

    observed_failure = False
    observed_success = False
    for raw_branch in raw_branches:
        if not isinstance(raw_branch, Mapping):
            return False
        outcome = raw_branch.get("terminal_outcome")
        raw_steps = raw_branch.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return False
        final_observation: Mapping[str, object] | None = None
        failed = False
        for raw_step in raw_steps:
            if not isinstance(raw_step, Mapping):
                return False
            tool_name = raw_step.get("tool_name")
            arguments = raw_step.get("arguments")
            if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
                return False
            if not all(isinstance(key, str) for key in arguments):
                return False
            try:
                final_observation = execute_tool(
                    tool_name,
                    {str(key): value for key, value in arguments.items()},
                )
            except KeyError:
                failed = True
                break
        if outcome == "fallback_on_failure":
            observed_failure = observed_failure or failed
            continue
        if outcome != "accept_on_success" or failed:
            return False
        if final_observation is None:
            return False
        if not all(
            field in final_observation
            and field in expected_observation
            and canonical_coverage_hash(final_observation[field])
            == canonical_coverage_hash(expected_observation[field])
            for field in task_type.final_answer_fields
        ):
            return False
        observed_success = True
    return observed_failure and observed_success


def canonical_coverage_hash(value: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(canonical_coverage_json(value).encode("utf-8")).hexdigest()
    )


def canonical_coverage_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CoveragePlanValidationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _validate_dimension_value(
    value: object,
    *,
    field_name: str,
) -> None:
    if isinstance(value, str):
        _require_non_empty_string(value, field_name)
        return
    if (
        isinstance(value, tuple)
        and value
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    ):
        return
    raise CoveragePlanValidationError(
        f"{field_name} must be a non-empty string or tuple of unique strings"
    )


def _validate_version_registry(
    version_registry: CoverageVersionRegistry,
) -> None:
    for label, entries in (
        ("catalog", version_registry.catalog_versions),
        ("profile", version_registry.profile_versions),
    ):
        if not isinstance(entries, tuple) or not entries:
            raise CoveragePlanValidationError(
                f"coverage {label} version registry must not be empty"
            )
        if any(
            not isinstance(entry, tuple)
            or len(entry) != 2
            or any(
                not isinstance(value, str) or not value
                for value in entry
            )
            for entry in entries
        ):
            raise CoveragePlanValidationError(
                f"coverage {label} version registry entries are invalid"
            )
        if len(entries) != len(set(entries)):
            raise CoveragePlanValidationError(
                f"coverage {label} version registry entries must be unique"
            )
