from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Mapping


COVERAGE_CATALOG_VERSION = "coverage_catalog_v1"
COVERAGE_PROFILE_SCHEMA_VERSION = "coverage_profile_v1"
COVERAGE_CAPACITY_VERSION = "coverage_capacity_v1"
COVERAGE_PLAN_VERSION = "coverage_plan_v1"
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
class CoverageCell:
    cell_id: str
    dimensions: Mapping[str, CoverageDimensionValue]
    grounding_capacity_key: str
    required_features: tuple[str, ...] = ()
    max_accepted_samples: int | None = None

    def canonical(self) -> dict[str, object]:
        dimensions: dict[str, object] = {}
        for key, value in sorted(self.dimensions.items()):
            dimensions[key] = list(value) if isinstance(value, tuple) else value
        record: dict[str, object] = {
            "cell_id": self.cell_id,
            "dimensions": dimensions,
            "grounding_capacity_key": self.grounding_capacity_key,
            "required_features": sorted(self.required_features),
        }
        if self.max_accepted_samples is not None:
            record["max_accepted_samples"] = self.max_accepted_samples
        return record


@dataclass(frozen=True)
class CoverageCatalog:
    schema_version: str
    catalog_id: str
    version: str
    domain_id: str
    dimensions: tuple[str, ...]
    cells: tuple[CoverageCell, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "catalog_id": self.catalog_id,
            "version": self.version,
            "domain_id": self.domain_id,
            "dimensions": sorted(self.dimensions),
            "cells": [
                cell.canonical()
                for cell in sorted(self.cells, key=lambda item: item.cell_id)
            ],
        }


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
        return (_canonical_json(self.canonical()) + "\n").encode("utf-8")


def write_coverage_plan(path: Path, plan: CoveragePlan) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plan.to_bytes())
    return output_path


def compile_coverage_plan(
    *,
    catalog: CoverageCatalog,
    coverage_profile: CoverageProfile,
    selected_features: tuple[str, ...],
    target_accepted_sample_count: int,
    admitted_capacity: AdmittedCoverageCapacity,
    balance_weight_overrides: Mapping[str, int] | None = None,
) -> CoveragePlan:
    _validate_compilation_inputs(
        catalog=catalog,
        coverage_profile=coverage_profile,
        selected_features=selected_features,
        target_accepted_sample_count=target_accepted_sample_count,
        admitted_capacity=admitted_capacity,
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
    for cell_id in weights:
        unavailable = sorted(
            set(cells[cell_id].required_features) - selected_feature_set
        )
        if unavailable:
            raise CoveragePlanValidationError(
                f"coverage cell {cell_id} requires unavailable features: "
                + ", ".join(unavailable)
            )

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

    attempt_policy = coverage_profile.attempt_policy
    attempt_ceiling = (
        target_accepted_sample_count * attempt_policy.multiplier_numerator
        + attempt_policy.multiplier_denominator
        - 1
    ) // attempt_policy.multiplier_denominator
    catalog_hash = _canonical_hash(catalog.canonical())
    profile_hash = _canonical_hash(coverage_profile.canonical())
    capacity_hash = _canonical_hash(admitted_capacity.canonical())
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
    plan_hash = _canonical_hash(payload)
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
    selected_features: tuple[str, ...],
    target_accepted_sample_count: int,
    admitted_capacity: AdmittedCoverageCapacity,
) -> None:
    if catalog.schema_version != COVERAGE_CATALOG_VERSION:
        raise CoveragePlanValidationError("unknown coverage catalog schema version")
    if coverage_profile.schema_version != COVERAGE_PROFILE_SCHEMA_VERSION:
        raise CoveragePlanValidationError("unknown coverage profile schema version")
    if admitted_capacity.schema_version != COVERAGE_CAPACITY_VERSION:
        raise CoveragePlanValidationError("unknown coverage capacity schema version")
    _require_non_empty_string(catalog.catalog_id, "coverage catalog id")
    _require_non_empty_string(catalog.version, "coverage catalog version")
    _require_non_empty_string(catalog.domain_id, "coverage catalog domain")
    if catalog.version != f"{catalog.catalog_id}_v1":
        raise CoveragePlanValidationError(
            f"unknown coverage catalog version: {catalog.version}"
        )
    _require_non_empty_string(coverage_profile.profile_id, "coverage profile id")
    _require_non_empty_string(coverage_profile.version, "coverage profile version")
    if coverage_profile.version != f"{coverage_profile.profile_id}_v1":
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
    cell_ids: set[str] = set()
    cell_signatures: set[str] = set()
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
        signature = _canonical_json(cell.canonical()["dimensions"])
        if signature in cell_signatures:
            raise CoveragePlanValidationError(
                f"duplicate coverage cell dimensions: {cell.cell_id}"
            )
        cell_signatures.add(signature)
        if cell.grounding_capacity_key not in admitted_capacity.grounding_units:
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} has no admitted capacity"
            )
        if cell.max_accepted_samples is not None and (
            not isinstance(cell.max_accepted_samples, int)
            or isinstance(cell.max_accepted_samples, bool)
            or cell.max_accepted_samples <= 0
        ):
            raise CoveragePlanValidationError(
                f"coverage cell {cell.cell_id} max accepted samples must be positive"
            )
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
        if cell.max_accepted_samples is not None and count > cell.max_accepted_samples:
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
    if cell.max_accepted_samples is not None and next_count > cell.max_accepted_samples:
        return False
    capacity_key = cell.grounding_capacity_key
    current_for_key = sum(
        count
        for counted_cell_id, count in counts.items()
        if cells[counted_cell_id].grounding_capacity_key == capacity_key
    )
    return (
        current_for_key + 1
        <= admitted_capacity.grounding_units[capacity_key] * reuse_limit
    )


def _canonical_hash(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _canonical_json(value: object) -> str:
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
