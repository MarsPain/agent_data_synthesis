"""Strict, hash-bound contracts for logical Domain Packs.

This module deliberately has no dependency on the active runtime pipeline.  It
defines the immutable semantic records that later lifecycle work can select
without changing today's fixture execution path.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


DOMAIN_PACK_REFERENCE_SCHEMA_VERSION = "domain_pack_reference_v1"
DOMAIN_CAPABILITY_REFERENCE_SCHEMA_VERSION = "domain_capability_reference_v1"
DOMAIN_COMPONENT_CONTRACT_REFERENCE_SCHEMA_VERSION = (
    "domain_component_contract_reference_v1"
)
DOMAIN_RUNTIME_CONTRACT_REFERENCE_SCHEMA_VERSION = (
    "domain_runtime_contract_reference_v1"
)
DOMAIN_PACK_DESCRIPTOR_SCHEMA_VERSION = "domain_pack_descriptor_v1"
ADMITTED_SOURCE_SCHEMA_VERSION = "admitted_domain_source_v1"
DOMAIN_PLANNING_INTENT_SCHEMA_VERSION = "domain_planning_intent_v1"
DOMAIN_PLAN_SCHEMA_VERSION = "domain_plan_v1"
PLAN_FAILURE_SCHEMA_VERSION = "domain_plan_failure_v1"
LEGACY_PROJECTION_SCHEMA_VERSION = "legacy_domain_projection_v1"
COMPATIBILITY_MAPPING_SCHEMA_VERSION = "domain_compatibility_mapping_v1"
COMPATIBILITY_MAPPING_SET_SCHEMA_VERSION = "domain_compatibility_mapping_set_v1"
COMPATIBILITY_RESOLUTION_FAILURE_SCHEMA_VERSION = (
    "domain_compatibility_resolution_failure_v1"
)
DOMAIN_EVIDENCE_REFERENCE_SCHEMA_VERSION = "domain_evidence_reference_v1"
DOMAIN_ASSESSMENT_SCHEMA_VERSION = "domain_assessment_v1"
QUALIFICATION_ARTIFACT_REFERENCE_SCHEMA_VERSION = (
    "qualification_artifact_reference_v1"
)
QUALIFICATION_SUBJECT_SCHEMA_VERSION = "qualification_subject_v1"
DOMAIN_OPEN_FAILURE_SCHEMA_VERSION = "domain_open_failure_v1"
DOMAIN_CANDIDATE_SCOPE_SCHEMA_VERSION = "domain_candidate_scope_v1"
DOMAIN_ASSESSMENT_EVIDENCE_SCHEMA_VERSION = "domain_assessment_evidence_v1"
DOMAIN_ASSESSMENT_FAILURE_SCHEMA_VERSION = "domain_assessment_failure_v1"

MAX_DOMAIN_PACK_RECORD_BYTES = 64 * 1024
MAX_DOMAIN_PACK_RECORD_DEPTH = 16
MAX_DOMAIN_PACK_RECORD_ITEMS = 2_048
MAX_DOMAIN_PACK_TEXT_BYTES = 4 * 1024

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNSAFE_KEY_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "headers",
        "password",
        "private_key",
        "provider_payload",
        "provider_prompt",
        "raw_prompt",
        "raw_response",
        "raw_source",
        "secret",
        "source_path",
        "token",
    }
)
_UNSAFE_KEY_PARTS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
    }
)
_UNSAFE_STRING_PATTERNS = (
    re.compile(r"authorization\s*:", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:sk|rk|pk)_[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"secret[-_ ]?(?:test-?)?key", re.IGNORECASE),
    re.compile(r"(?:^|\s)/(?:Users|home|private|var|tmp)(?:/|$)"),
    re.compile(r"[A-Za-z]:\\"),
)

PLAN_COMPONENT_REQUIREMENT_KINDS = (
    "task_taxonomy",
    "generation",
    "capability_evidence_floors",
    "coverage_catalog",
    "coverage_profile",
    "compiled_coverage_plan",
    "assignment_policy",
    "parser_contract",
    "grounding_contract",
    "expected_state_contract",
    "membership_contract",
    "held_out_suite",
    "held_out_tasks",
    "held_out_thresholds",
    "mutation_policy",
    "mutation_admission_mode",
    "release_completeness",
    "release_machine_gates",
    "compatibility_mapping_set",
    "plan_schema",
    "assessment_schema",
)
REQUIRED_PLAN_COMPONENT_KINDS = frozenset(PLAN_COMPONENT_REQUIREMENT_KINDS)
REQUIRED_COMPONENT_KINDS = REQUIRED_PLAN_COMPONENT_KINDS

PLAN_FAILURE_REASON_CODES = frozenset(
    {
        "invalid_planning_intent",
        "unknown_domain_pack",
        "unsupported_pack_version",
        "domain_pack_hash_mismatch",
        "cross_pack_domain_reference",
        "admitted_source_not_admitted",
        "missing_task_type_projection",
        "duplicate_task_type_projection",
        "unknown_task_type_projection",
        "missing_capability_reference",
        "duplicate_capability_reference",
        "cross_pack_capability_reference",
        "unknown_capability_reference",
        "unsupported_capability_contract_version",
        "capability_projection_mismatch",
        "unsupported_runtime_contract",
        "unknown_compatibility_mapping",
        "ambiguous_compatibility_mapping",
        "compatibility_mapping_target_mismatch",
        "internally_inconsistent_descriptor",
    }
)

COMPATIBILITY_PROJECTION_KINDS = frozenset(
    {
        "semantic_domain",
        "capability",
        "held_out_capability",
        "task_type",
        "tool",
        "coverage_cell",
        "mutation_policy",
        "runtime",
    }
)
COMPATIBILITY_RESOLUTION_FAILURE_REASONS = frozenset(
    {
        "invalid_compatibility_lookup",
        "unknown_compatibility_mapping",
        "ambiguous_compatibility_mapping",
    }
)

DOMAIN_ASSESSMENT_INSUFFICIENCY_REASONS = frozenset(
    {
        "evidence_missing",
        "evidence_identity_mismatch",
        "capability_evidence_incomplete",
        "plan_identity_mismatch",
    }
)

OPEN_FAILURE_REASON_CODES = frozenset(
    {
        "invalid_domain_plan",
        "plan_contract_drift",
        "domain_pack_drift",
        "runtime_contract_drift",
        "source_drift",
        "invalid_runtime_scope",
        "runtime_scope_unavailable",
        "runtime_construction_failed",
    }
)

ASSESSMENT_FAILURE_REASON_CODES = frozenset(
    {
        "invalid_domain_plan",
        "plan_contract_drift",
        "domain_pack_drift",
        "invalid_assessment_evidence",
        "assessment_plan_drift",
    }
)


class DomainPackContractError(ValueError):
    """A deterministic, safe contract-validation failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def canonical_domain_pack_json(value: object) -> str:
    """Return bounded canonical JSON suitable for identity-bearing records."""

    _validate_safe_record_value(value, path="record")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_DOMAIN_PACK_RECORD_BYTES:
        raise DomainPackContractError("record_too_large")
    return encoded.decode("utf-8")


def canonical_domain_pack_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        canonical_domain_pack_json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DomainPackReference:
    domain_pack_id: str
    pack_version: str
    pack_hash: str
    schema_version: str = DOMAIN_PACK_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_PACK_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_pack_reference_schema")
        _require_identifier(self.domain_pack_id, "domain_pack_id")
        _require_identifier(self.pack_version, "pack_version")
        _require_hash(self.pack_hash, "pack_hash")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain_pack_id": self.domain_pack_id,
            "pack_version": self.pack_version,
            "pack_hash": self.pack_hash,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "DomainPackReference":
        _require_exact_keys(
            record,
            {"schema_version", "domain_pack_id", "pack_version", "pack_hash"},
            "domain_pack_reference",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_id=_require_text(record["domain_pack_id"], "domain_pack_id"),
            pack_version=_require_text(record["pack_version"], "pack_version"),
            pack_hash=_require_text(record["pack_hash"], "pack_hash"),
        )


@dataclass(frozen=True)
class DomainCapabilityReference:
    domain_pack_id: str
    capability_key: str
    capability_contract_version: str
    schema_version: str = DOMAIN_CAPABILITY_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_CAPABILITY_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_capability_reference_schema")
        _require_identifier(self.domain_pack_id, "domain_pack_id")
        _require_identifier(self.capability_key, "capability_key")
        _require_identifier(
            self.capability_contract_version,
            "capability_contract_version",
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain_pack_id": self.domain_pack_id,
            "capability_key": self.capability_key,
            "capability_contract_version": self.capability_contract_version,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainCapabilityReference":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "domain_pack_id",
                "capability_key",
                "capability_contract_version",
            },
            "domain_capability_reference",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_id=_require_text(record["domain_pack_id"], "domain_pack_id"),
            capability_key=_require_text(record["capability_key"], "capability_key"),
            capability_contract_version=_require_text(
                record["capability_contract_version"],
                "capability_contract_version",
            ),
        )


@dataclass(frozen=True)
class DomainComponentContractReference:
    component_kind: str
    component_id: str
    component_version: str
    component_hash: str
    schema_version: str = DOMAIN_COMPONENT_CONTRACT_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_COMPONENT_CONTRACT_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_component_reference_schema")
        _require_identifier(self.component_kind, "component_kind")
        _require_identifier(self.component_id, "component_id")
        _require_identifier(self.component_version, "component_version")
        _require_hash(self.component_hash, "component_hash")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "component_kind": self.component_kind,
            "component_id": self.component_id,
            "component_version": self.component_version,
            "component_hash": self.component_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainComponentContractReference":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "component_kind",
                "component_id",
                "component_version",
                "component_hash",
            },
            "domain_component_contract_reference",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            component_kind=_require_text(record["component_kind"], "component_kind"),
            component_id=_require_text(record["component_id"], "component_id"),
            component_version=_require_text(
                record["component_version"],
                "component_version",
            ),
            component_hash=_require_text(record["component_hash"], "component_hash"),
        )


@dataclass(frozen=True)
class DomainRuntimeContractReference:
    runtime_id: str
    runtime_version: str
    runtime_contract_version: str
    runtime_implementation_hash: str
    runtime_contract_hash: str
    schema_version: str = DOMAIN_RUNTIME_CONTRACT_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_RUNTIME_CONTRACT_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_runtime_reference_schema")
        _require_identifier(self.runtime_id, "runtime_id")
        _require_identifier(self.runtime_version, "runtime_version")
        _require_identifier(self.runtime_contract_version, "runtime_contract_version")
        _require_hash(self.runtime_implementation_hash, "runtime_implementation_hash")
        _require_hash(self.runtime_contract_hash, "runtime_contract_hash")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "runtime_id": self.runtime_id,
            "runtime_version": self.runtime_version,
            "runtime_contract_version": self.runtime_contract_version,
            "runtime_implementation_hash": self.runtime_implementation_hash,
            "runtime_contract_hash": self.runtime_contract_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainRuntimeContractReference":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "runtime_id",
                "runtime_version",
                "runtime_contract_version",
                "runtime_implementation_hash",
                "runtime_contract_hash",
            },
            "domain_runtime_contract_reference",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            runtime_id=_require_text(record["runtime_id"], "runtime_id"),
            runtime_version=_require_text(record["runtime_version"], "runtime_version"),
            runtime_contract_version=_require_text(
                record["runtime_contract_version"],
                "runtime_contract_version",
            ),
            runtime_implementation_hash=_require_text(
                record["runtime_implementation_hash"],
                "runtime_implementation_hash",
            ),
            runtime_contract_hash=_require_text(
                record["runtime_contract_hash"],
                "runtime_contract_hash",
            ),
        )


@dataclass(frozen=True)
class DomainPlanRequirements:
    """The fixed, exact contract selections required by every Domain plan."""

    task_taxonomy: DomainComponentContractReference
    generation: DomainComponentContractReference
    capability_evidence_floors: DomainComponentContractReference
    coverage_catalog: DomainComponentContractReference
    coverage_profile: DomainComponentContractReference
    compiled_coverage_plan: DomainComponentContractReference
    assignment_policy: DomainComponentContractReference
    parser_contract: DomainComponentContractReference
    grounding_contract: DomainComponentContractReference
    expected_state_contract: DomainComponentContractReference
    membership_contract: DomainComponentContractReference
    held_out_suite: DomainComponentContractReference
    held_out_tasks: DomainComponentContractReference
    held_out_thresholds: DomainComponentContractReference
    mutation_policy: DomainComponentContractReference
    mutation_admission_mode: DomainComponentContractReference
    release_completeness: DomainComponentContractReference
    release_machine_gates: DomainComponentContractReference
    compatibility_mapping_set: DomainComponentContractReference
    plan_schema: DomainComponentContractReference
    assessment_schema: DomainComponentContractReference

    def __post_init__(self) -> None:
        for component_kind in PLAN_COMPONENT_REQUIREMENT_KINDS:
            component = getattr(self, component_kind)
            if (
                not isinstance(component, DomainComponentContractReference)
                or component.component_kind != component_kind
            ):
                raise DomainPackContractError("invalid_domain_plan_requirement")
        if len(set(self.component_contracts())) != len(PLAN_COMPONENT_REQUIREMENT_KINDS):
            raise DomainPackContractError("duplicate_domain_plan_requirement")

    @classmethod
    def from_component_contracts(
        cls,
        component_contracts: object,
    ) -> "DomainPlanRequirements":
        if (
            not isinstance(component_contracts, tuple)
            or any(
                not isinstance(item, DomainComponentContractReference)
                for item in component_contracts
            )
        ):
            raise DomainPackContractError("invalid_domain_plan_requirement")
        components_by_kind = {
            item.component_kind: item for item in component_contracts
        }
        if (
            len(components_by_kind) != len(component_contracts)
            or set(components_by_kind) != REQUIRED_PLAN_COMPONENT_KINDS
        ):
            raise DomainPackContractError("incomplete_component_contracts")
        return cls(
            **{
                component_kind: components_by_kind[component_kind]
                for component_kind in PLAN_COMPONENT_REQUIREMENT_KINDS
            }
        )

    def component_contracts(self) -> tuple[DomainComponentContractReference, ...]:
        return tuple(
            sorted(
                (
                    getattr(self, component_kind)
                    for component_kind in PLAN_COMPONENT_REQUIREMENT_KINDS
                ),
                key=lambda item: item.component_kind,
            )
        )

    def to_record(self) -> dict[str, object]:
        return {
            component_kind: getattr(self, component_kind).to_record()
            for component_kind in PLAN_COMPONENT_REQUIREMENT_KINDS
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainPlanRequirements":
        _require_exact_keys(
            record,
            set(PLAN_COMPONENT_REQUIREMENT_KINDS),
            "domain_plan_requirements",
        )
        return cls(
            **{
                component_kind: DomainComponentContractReference.from_record(
                    _require_mapping(record[component_kind], component_kind)
                )
                for component_kind in PLAN_COMPONENT_REQUIREMENT_KINDS
            }
        )


@dataclass(frozen=True)
class TaskCapabilityProjection:
    task_type_key: str
    capability_references: tuple[DomainCapabilityReference, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.task_type_key, "task_type_key")
        if (
            not isinstance(self.capability_references, tuple)
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.capability_references
            )
        ):
            raise DomainPackContractError("invalid_task_capability_projection")
        if not self.capability_references:
            raise DomainPackContractError("missing_projection_capability")
        if len(set(self.capability_references)) != len(self.capability_references):
            raise DomainPackContractError("duplicate_projection_capability")

    def to_record(self) -> dict[str, object]:
        return {
            "task_type_key": self.task_type_key,
            "capability_references": [
                item.to_record()
                for item in sorted(
                    self.capability_references,
                    key=_capability_sort_key,
                )
            ],
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "TaskCapabilityProjection":
        _require_exact_keys(
            record,
            {"task_type_key", "capability_references"},
            "task_capability_projection",
        )
        return cls(
            task_type_key=_require_text(record["task_type_key"], "task_type_key"),
            capability_references=tuple(
                sorted(
                    (
                        DomainCapabilityReference.from_record(item)
                        for item in _require_record_sequence(
                            record["capability_references"],
                            "capability_references",
                        )
                    ),
                    key=_capability_sort_key,
                )
            ),
        )


@dataclass(frozen=True)
class DomainPackDescriptor:
    domain_pack_id: str
    pack_version: str
    capability_references: tuple[DomainCapabilityReference, ...]
    component_contracts: tuple[DomainComponentContractReference, ...]
    runtime_contracts: tuple[DomainRuntimeContractReference, ...]
    task_capability_projections: tuple[TaskCapabilityProjection, ...]
    held_out_capability_references: tuple[DomainCapabilityReference, ...]
    schema_version: str = DOMAIN_PACK_DESCRIPTOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_PACK_DESCRIPTOR_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_pack_descriptor_schema")
        _require_identifier(self.domain_pack_id, "domain_pack_id")
        _require_identifier(self.pack_version, "pack_version")
        if (
            not isinstance(self.capability_references, tuple)
            or not isinstance(self.component_contracts, tuple)
            or not isinstance(self.runtime_contracts, tuple)
            or not isinstance(self.task_capability_projections, tuple)
            or not isinstance(self.held_out_capability_references, tuple)
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.capability_references
            )
            or any(
                not isinstance(item, DomainComponentContractReference)
                for item in self.component_contracts
            )
            or any(
                not isinstance(item, DomainRuntimeContractReference)
                for item in self.runtime_contracts
            )
            or any(
                not isinstance(item, TaskCapabilityProjection)
                for item in self.task_capability_projections
            )
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.held_out_capability_references
            )
        ):
            raise DomainPackContractError("invalid_domain_pack_descriptor")
        if not self.capability_references:
            raise DomainPackContractError("missing_capability_catalog")
        if len(set(self.capability_references)) != len(self.capability_references):
            raise DomainPackContractError("duplicate_capability_reference")
        if any(
            item.domain_pack_id != self.domain_pack_id
            for item in self.capability_references
        ):
            raise DomainPackContractError("cross_pack_capability_reference")
        capability_keys = [item.capability_key for item in self.capability_references]
        if len(set(capability_keys)) != len(capability_keys):
            raise DomainPackContractError("duplicate_capability_key")
        if {item.component_kind for item in self.component_contracts} != REQUIRED_COMPONENT_KINDS:
            raise DomainPackContractError("incomplete_component_contracts")
        if len({item.component_kind for item in self.component_contracts}) != len(
            self.component_contracts
        ):
            raise DomainPackContractError("duplicate_component_contract")
        if not self.runtime_contracts:
            raise DomainPackContractError("missing_runtime_contract")
        runtime_keys = {
            (item.runtime_id, item.runtime_version, item.runtime_contract_version)
            for item in self.runtime_contracts
        }
        if len(runtime_keys) != len(self.runtime_contracts):
            raise DomainPackContractError("duplicate_runtime_contract")
        if not self.task_capability_projections:
            raise DomainPackContractError("missing_task_capability_projection")
        task_keys = [item.task_type_key for item in self.task_capability_projections]
        if len(set(task_keys)) != len(task_keys):
            raise DomainPackContractError("duplicate_task_capability_projection")
        declared_capabilities = set(self.capability_references)
        for projection in self.task_capability_projections:
            if not set(projection.capability_references) <= declared_capabilities:
                raise DomainPackContractError("unknown_projection_capability")
        if not self.held_out_capability_references:
            raise DomainPackContractError("missing_held_out_capability_projection")
        if len(set(self.held_out_capability_references)) != len(
            self.held_out_capability_references
        ):
            raise DomainPackContractError("duplicate_held_out_capability_reference")
        if not set(self.held_out_capability_references) <= declared_capabilities:
            raise DomainPackContractError("unknown_held_out_capability")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain_pack_id": self.domain_pack_id,
            "pack_version": self.pack_version,
            "capability_references": [
                item.to_record()
                for item in sorted(self.capability_references, key=_capability_sort_key)
            ],
            "component_contracts": [
                item.to_record()
                for item in sorted(
                    self.component_contracts,
                    key=lambda item: (
                        item.component_kind,
                        item.component_id,
                        item.component_version,
                    ),
                )
            ],
            "runtime_contracts": [
                item.to_record()
                for item in sorted(
                    self.runtime_contracts,
                    key=lambda item: (
                        item.runtime_id,
                        item.runtime_version,
                        item.runtime_contract_version,
                    ),
                )
            ],
            "task_capability_projections": [
                item.to_record()
                for item in sorted(
                    self.task_capability_projections,
                    key=lambda item: item.task_type_key,
                )
            ],
            "held_out_capability_references": [
                item.to_record()
                for item in sorted(
                    self.held_out_capability_references,
                    key=_capability_sort_key,
                )
            ],
        }

    def to_record(self) -> dict[str, object]:
        return self.canonical_record()

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainPackDescriptor":
        canonical_domain_pack_json(record)
        _require_exact_keys(
            record,
            {
                "schema_version",
                "domain_pack_id",
                "pack_version",
                "capability_references",
                "component_contracts",
                "runtime_contracts",
                "task_capability_projections",
                "held_out_capability_references",
            },
            "domain_pack_descriptor",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_id=_require_text(record["domain_pack_id"], "domain_pack_id"),
            pack_version=_require_text(record["pack_version"], "pack_version"),
            capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["capability_references"],
                    "capability_references",
                )
            ),
            component_contracts=tuple(
                DomainComponentContractReference.from_record(item)
                for item in _require_record_sequence(
                    record["component_contracts"],
                    "component_contracts",
                )
            ),
            runtime_contracts=tuple(
                DomainRuntimeContractReference.from_record(item)
                for item in _require_record_sequence(
                    record["runtime_contracts"],
                    "runtime_contracts",
                )
            ),
            task_capability_projections=tuple(
                TaskCapabilityProjection.from_record(item)
                for item in _require_record_sequence(
                    record["task_capability_projections"],
                    "task_capability_projections",
                )
            ),
            held_out_capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["held_out_capability_references"],
                    "held_out_capability_references",
                )
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_domain_pack_json(self.canonical_record()).encode("utf-8")

    def pack_hash(self) -> str:
        return canonical_domain_pack_hash(self.canonical_record())

    def reference(self) -> DomainPackReference:
        return DomainPackReference(
            domain_pack_id=self.domain_pack_id,
            pack_version=self.pack_version,
            pack_hash=self.pack_hash(),
        )

    def plan_requirements(self) -> DomainPlanRequirements:
        return DomainPlanRequirements.from_component_contracts(
            self.component_contracts
        )


@dataclass(frozen=True)
class AdmittedSource:
    """Sanitized source facts that planning may bind without reading source bytes."""

    source_id: str
    source_schema_version: str
    source_content_hash: str
    admission_policy_id: str
    admission_policy_hash: str
    admission_status: str = "admitted"
    schema_version: str = ADMITTED_SOURCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ADMITTED_SOURCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_admitted_source_schema")
        _require_identifier(self.source_id, "source_id")
        _require_identifier(self.source_schema_version, "source_schema_version")
        _require_hash(self.source_content_hash, "source_content_hash")
        _require_identifier(self.admission_policy_id, "admission_policy_id")
        _require_hash(self.admission_policy_hash, "admission_policy_hash")
        if self.admission_status not in {"admitted", "rejected"}:
            raise DomainPackContractError("admission_status_invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_schema_version": self.source_schema_version,
            "source_content_hash": self.source_content_hash,
            "admission_policy_id": self.admission_policy_id,
            "admission_policy_hash": self.admission_policy_hash,
            "admission_status": self.admission_status,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "AdmittedSource":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "source_id",
                "source_schema_version",
                "source_content_hash",
                "admission_policy_id",
                "admission_policy_hash",
                "admission_status",
            },
            "admitted_source",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            source_id=_require_text(record["source_id"], "source_id"),
            source_schema_version=_require_text(
                record["source_schema_version"],
                "source_schema_version",
            ),
            source_content_hash=_require_text(
                record["source_content_hash"],
                "source_content_hash",
            ),
            admission_policy_id=_require_text(
                record["admission_policy_id"],
                "admission_policy_id",
            ),
            admission_policy_hash=_require_text(
                record["admission_policy_hash"],
                "admission_policy_hash",
            ),
            admission_status=_require_text(
                record["admission_status"],
                "admission_status",
            ),
        )


@dataclass(frozen=True)
class LegacyProjection:
    """A legacy value plus the namespace in which it was written."""

    source_schema_version: str
    projection_kind: str
    legacy_value: str
    schema_version: str = LEGACY_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LEGACY_PROJECTION_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_legacy_projection_schema")
        _require_identifier(self.source_schema_version, "source_schema_version")
        if self.projection_kind not in COMPATIBILITY_PROJECTION_KINDS:
            raise DomainPackContractError("unsupported_compatibility_projection_kind")
        _require_identifier(self.legacy_value, "legacy_value")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_schema_version": self.source_schema_version,
            "projection_kind": self.projection_kind,
            "legacy_value": self.legacy_value,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "LegacyProjection":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "source_schema_version",
                "projection_kind",
                "legacy_value",
            },
            "legacy_projection",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            source_schema_version=_require_text(
                record["source_schema_version"],
                "source_schema_version",
            ),
            projection_kind=_require_text(
                record["projection_kind"],
                "projection_kind",
            ),
            legacy_value=_require_text(record["legacy_value"], "legacy_value"),
        )


@dataclass(frozen=True)
class DomainPlanningIntent:
    """The already-admitted, provider-free input to pure Domain Pack planning."""

    domain_pack_reference: object
    task_type_keys: object
    capability_references: object
    runtime_contract: object
    legacy_projection: object | None = None
    schema_version: str = DOMAIN_PLANNING_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_PLANNING_INTENT_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_planning_intent_schema")

    def to_record(self) -> dict[str, object]:
        if (
            not isinstance(self.domain_pack_reference, DomainPackReference)
            or not isinstance(self.runtime_contract, DomainRuntimeContractReference)
            or not isinstance(self.task_type_keys, tuple)
            or not isinstance(self.capability_references, tuple)
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.capability_references
            )
            or (
                self.legacy_projection is not None
                and not isinstance(self.legacy_projection, LegacyProjection)
            )
        ):
            raise DomainPackContractError("invalid_planning_intent")
        record: dict[str, object] = {
            "schema_version": self.schema_version,
            "domain_pack_reference": self.domain_pack_reference.to_record(),
            "task_type_keys": list(self.task_type_keys),
            "capability_references": [
                item.to_record() for item in self.capability_references
            ],
            "runtime_contract": self.runtime_contract.to_record(),
        }
        if self.legacy_projection is not None:
            record["legacy_projection"] = self.legacy_projection.to_record()
        canonical_domain_pack_json(record)
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "DomainPlanningIntent":
        canonical_domain_pack_json(record)
        expected_keys = {
            "schema_version",
            "domain_pack_reference",
            "task_type_keys",
            "capability_references",
            "runtime_contract",
        }
        if "legacy_projection" in record:
            expected_keys.add("legacy_projection")
        _require_exact_keys(record, expected_keys, "domain_planning_intent")
        task_type_keys = record["task_type_keys"]
        if (
            not isinstance(task_type_keys, Sequence)
            or isinstance(task_type_keys, (str, bytes, bytearray))
            or any(not isinstance(item, str) for item in task_type_keys)
        ):
            raise DomainPackContractError("task_type_keys_invalid")
        legacy_projection_value = record.get("legacy_projection")
        if "legacy_projection" in record and legacy_projection_value is None:
            raise DomainPackContractError("legacy_projection_invalid")
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_reference=DomainPackReference.from_record(
                _require_mapping(
                    record["domain_pack_reference"],
                    "domain_pack_reference",
                )
            ),
            task_type_keys=tuple(task_type_keys),
            capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["capability_references"],
                    "capability_references",
                )
            ),
            runtime_contract=DomainRuntimeContractReference.from_record(
                _require_mapping(record["runtime_contract"], "runtime_contract")
            ),
            legacy_projection=(
                None
                if legacy_projection_value is None
                else LegacyProjection.from_record(
                    _require_mapping(legacy_projection_value, "legacy_projection")
                )
            ),
        )


@dataclass(frozen=True)
class DomainPlan:
    """A canonical, hash-bound plan compiled before runtime or provider activity."""

    domain_pack_reference: DomainPackReference
    admitted_source: AdmittedSource
    runtime_contract: DomainRuntimeContractReference
    task_capability_projections: tuple[TaskCapabilityProjection, ...]
    capability_references: tuple[DomainCapabilityReference, ...]
    plan_requirements: DomainPlanRequirements
    held_out_capability_references: tuple[DomainCapabilityReference, ...]
    compatibility_mapping: CompatibilityMapping | None
    plan_id: str
    plan_hash: str
    schema_version: str = DOMAIN_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_PLAN_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_plan_schema")
        if (
            not isinstance(self.domain_pack_reference, DomainPackReference)
            or not isinstance(self.admitted_source, AdmittedSource)
            or not isinstance(self.runtime_contract, DomainRuntimeContractReference)
            or not isinstance(self.task_capability_projections, tuple)
            or not isinstance(self.capability_references, tuple)
            or not isinstance(self.plan_requirements, DomainPlanRequirements)
            or not isinstance(self.held_out_capability_references, tuple)
            or any(
                not isinstance(item, TaskCapabilityProjection)
                for item in self.task_capability_projections
            )
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in (
                    *self.capability_references,
                    *self.held_out_capability_references,
                )
            )
            or (
                self.compatibility_mapping is not None
                and not isinstance(self.compatibility_mapping, CompatibilityMapping)
            )
        ):
            raise DomainPackContractError("invalid_domain_plan")
        if self.admitted_source.admission_status != "admitted":
            raise DomainPackContractError("domain_plan_source_not_admitted")
        _require_identifier(self.plan_id, "plan_id")
        _require_hash(self.plan_hash, "plan_hash")
        expected_hash = canonical_domain_pack_hash(self._content_record())
        if self.plan_hash != expected_hash:
            raise DomainPackContractError("domain_plan_hash_mismatch")
        expected_id = "domain_plan_" + expected_hash.removeprefix("sha256:")[:16]
        if self.plan_id != expected_id:
            raise DomainPackContractError("domain_plan_id_mismatch")

    @classmethod
    def create(
        cls,
        *,
        descriptor: DomainPackDescriptor,
        domain_pack_reference: DomainPackReference,
        admitted_source: AdmittedSource,
        runtime_contract: DomainRuntimeContractReference,
        task_capability_projections: tuple[TaskCapabilityProjection, ...],
        capability_references: tuple[DomainCapabilityReference, ...],
        plan_requirements: DomainPlanRequirements,
        held_out_capability_references: tuple[DomainCapabilityReference, ...],
        compatibility_mapping: CompatibilityMapping | None,
        compatibility_mapping_set: CompatibilityMappingSet | None = None,
    ) -> "DomainPlan":
        plan = cls._create_unchecked(
            domain_pack_reference=domain_pack_reference,
            admitted_source=admitted_source,
            runtime_contract=runtime_contract,
            task_capability_projections=task_capability_projections,
            capability_references=capability_references,
            plan_requirements=plan_requirements,
            held_out_capability_references=held_out_capability_references,
            compatibility_mapping=compatibility_mapping,
        )
        plan.validate_against_descriptor(
            descriptor,
            compatibility_mapping_set=compatibility_mapping_set,
        )
        return plan

    @classmethod
    def _create_unchecked(
        cls,
        *,
        domain_pack_reference: DomainPackReference,
        admitted_source: AdmittedSource,
        runtime_contract: DomainRuntimeContractReference,
        task_capability_projections: tuple[TaskCapabilityProjection, ...],
        capability_references: tuple[DomainCapabilityReference, ...],
        plan_requirements: DomainPlanRequirements,
        held_out_capability_references: tuple[DomainCapabilityReference, ...],
        compatibility_mapping: CompatibilityMapping | None,
    ) -> "DomainPlan":
        content = _domain_plan_content_record(
            schema_version=DOMAIN_PLAN_SCHEMA_VERSION,
            domain_pack_reference=domain_pack_reference,
            admitted_source=admitted_source,
            runtime_contract=runtime_contract,
            task_capability_projections=task_capability_projections,
            capability_references=capability_references,
            plan_requirements=plan_requirements,
            held_out_capability_references=held_out_capability_references,
            compatibility_mapping=compatibility_mapping,
        )
        plan_hash = canonical_domain_pack_hash(content)
        return cls(
            domain_pack_reference=domain_pack_reference,
            admitted_source=admitted_source,
            runtime_contract=runtime_contract,
            task_capability_projections=task_capability_projections,
            capability_references=capability_references,
            plan_requirements=plan_requirements,
            held_out_capability_references=held_out_capability_references,
            compatibility_mapping=compatibility_mapping,
            plan_id="domain_plan_" + plan_hash.removeprefix("sha256:")[:16],
            plan_hash=plan_hash,
        )

    def _content_record(self) -> dict[str, object]:
        return _domain_plan_content_record(
            schema_version=self.schema_version,
            domain_pack_reference=self.domain_pack_reference,
            admitted_source=self.admitted_source,
            runtime_contract=self.runtime_contract,
            task_capability_projections=self.task_capability_projections,
            capability_references=self.capability_references,
            plan_requirements=self.plan_requirements,
            held_out_capability_references=self.held_out_capability_references,
            compatibility_mapping=self.compatibility_mapping,
        )

    @property
    def component_contracts(self) -> tuple[DomainComponentContractReference, ...]:
        """Exact component references retained for consumers needing the full set."""

        return self.plan_requirements.component_contracts()

    def validate_against_descriptor(
        self,
        descriptor: DomainPackDescriptor,
        *,
        compatibility_mapping_set: CompatibilityMappingSet | None = None,
    ) -> None:
        """Verify every plan selection against its immutable descriptor."""

        _, selected_capabilities, _ = _normalize_plan_selection_against_descriptor(
            descriptor,
            domain_pack_reference=self.domain_pack_reference,
            task_type_keys=tuple(
                item.task_type_key for item in self.task_capability_projections
            ),
            task_capability_projections=self.task_capability_projections,
            capability_references=self.capability_references,
            runtime_contract=self.runtime_contract,
            plan_requirements=self.plan_requirements,
            held_out_capability_references=self.held_out_capability_references,
        )
        if self.compatibility_mapping is not None:
            _validate_stored_compatibility_mapping(
                mapping=self.compatibility_mapping,
                compatibility_mapping_set=compatibility_mapping_set,
                descriptor=descriptor,
                capability_references=selected_capabilities,
                runtime_contract=self.runtime_contract,
            )

    def to_record(self) -> dict[str, object]:
        return {
            **self._content_record(),
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
        *,
        descriptor: DomainPackDescriptor,
        compatibility_mapping_set: CompatibilityMappingSet | None = None,
    ) -> "DomainPlan":
        canonical_domain_pack_json(record)
        expected_keys = {
            "schema_version",
            "domain_pack_reference",
            "admitted_source",
            "runtime_contract",
            "task_capability_projections",
            "capability_references",
            "plan_requirements",
            "held_out_capability_references",
            "plan_id",
            "plan_hash",
        }
        if "compatibility_mapping" in record:
            expected_keys.add("compatibility_mapping")
        _require_exact_keys(record, expected_keys, "domain_plan")
        compatibility_mapping_value = record.get("compatibility_mapping")
        if "compatibility_mapping" in record and compatibility_mapping_value is None:
            raise DomainPackContractError("compatibility_mapping_invalid")
        plan = cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_reference=DomainPackReference.from_record(
                _require_mapping(
                    record["domain_pack_reference"],
                    "domain_pack_reference",
                )
            ),
            admitted_source=AdmittedSource.from_record(
                _require_mapping(record["admitted_source"], "admitted_source")
            ),
            runtime_contract=DomainRuntimeContractReference.from_record(
                _require_mapping(record["runtime_contract"], "runtime_contract")
            ),
            task_capability_projections=tuple(
                TaskCapabilityProjection.from_record(item)
                for item in _require_record_sequence(
                    record["task_capability_projections"],
                    "task_capability_projections",
                )
            ),
            capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["capability_references"],
                    "capability_references",
                )
            ),
            plan_requirements=DomainPlanRequirements.from_record(
                _require_mapping(
                    record["plan_requirements"],
                    "plan_requirements",
                )
            ),
            held_out_capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["held_out_capability_references"],
                    "held_out_capability_references",
                )
            ),
            compatibility_mapping=(
                None
                if compatibility_mapping_value is None
                else CompatibilityMapping.from_record(
                    _require_mapping(
                        compatibility_mapping_value,
                        "compatibility_mapping",
                    )
                )
            ),
            plan_id=_require_text(record["plan_id"], "plan_id"),
            plan_hash=_require_text(record["plan_hash"], "plan_hash"),
        )
        plan.validate_against_descriptor(
            descriptor,
            compatibility_mapping_set=compatibility_mapping_set,
        )
        return plan

    def canonical_bytes(self) -> bytes:
        return canonical_domain_pack_json(self.to_record()).encode("utf-8")


@dataclass(frozen=True)
class PlanFailure:
    """A bounded planning result that contains no raw rejected input."""

    reason_code: str
    schema_version: str = PLAN_FAILURE_SCHEMA_VERSION
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.schema_version != PLAN_FAILURE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_plan_failure_schema")
        if self.status != "rejected" or self.reason_code not in PLAN_FAILURE_REASON_CODES:
            raise DomainPackContractError("invalid_plan_failure")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "PlanFailure":
        _require_exact_keys(
            record,
            {"schema_version", "status", "reason_code"},
            "domain_plan_failure",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            status=_require_text(record["status"], "status"),
            reason_code=_require_text(record["reason_code"], "reason_code"),
        )


CompatibilityTarget = (
    DomainPackReference
    | DomainCapabilityReference
    | DomainRuntimeContractReference
    | DomainComponentContractReference
)


@dataclass(frozen=True)
class CompatibilityMapping:
    """One explicit, versioned legacy projection mapping.

    The lookup key deliberately includes source schema and projection kind.  A
    semantic-domain value and a runtime value that happen to have the same
    spelling are therefore distinct mappings.
    """

    source_schema_version: str
    projection_kind: str
    legacy_value: str
    mapping_version: str
    target: CompatibilityTarget
    mapping_id: str
    mapping_hash: str
    schema_version: str = COMPATIBILITY_MAPPING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COMPATIBILITY_MAPPING_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_compatibility_mapping_schema")
        _require_identifier(self.source_schema_version, "source_schema_version")
        if self.projection_kind not in COMPATIBILITY_PROJECTION_KINDS:
            raise DomainPackContractError("unsupported_compatibility_projection_kind")
        _require_identifier(self.legacy_value, "legacy_value")
        _require_identifier(self.mapping_version, "mapping_version")
        _validate_compatibility_mapping_target(self.projection_kind, self.target)
        _require_identifier(self.mapping_id, "mapping_id")
        _require_hash(self.mapping_hash, "mapping_hash")
        expected_hash = canonical_domain_pack_hash(self._content_record())
        if self.mapping_hash != expected_hash:
            raise DomainPackContractError("compatibility_mapping_hash_mismatch")
        if self.mapping_id != (
            "compatibility_mapping_" + expected_hash.removeprefix("sha256:")[:16]
        ):
            raise DomainPackContractError("compatibility_mapping_id_mismatch")

    @classmethod
    def create(
        cls,
        *,
        source_schema_version: str,
        projection_kind: str,
        legacy_value: str,
        mapping_version: str,
        target: CompatibilityTarget,
    ) -> "CompatibilityMapping":
        content = _compatibility_mapping_content_record(
            schema_version=COMPATIBILITY_MAPPING_SCHEMA_VERSION,
            source_schema_version=source_schema_version,
            projection_kind=projection_kind,
            legacy_value=legacy_value,
            mapping_version=mapping_version,
            target=target,
        )
        mapping_hash = canonical_domain_pack_hash(content)
        return cls(
            source_schema_version=source_schema_version,
            projection_kind=projection_kind,
            legacy_value=legacy_value,
            mapping_version=mapping_version,
            target=target,
            mapping_id=(
                "compatibility_mapping_"
                + mapping_hash.removeprefix("sha256:")[:16]
            ),
            mapping_hash=mapping_hash,
        )

    def _content_record(self) -> dict[str, object]:
        return _compatibility_mapping_content_record(
            schema_version=self.schema_version,
            source_schema_version=self.source_schema_version,
            projection_kind=self.projection_kind,
            legacy_value=self.legacy_value,
            mapping_version=self.mapping_version,
            target=self.target,
        )

    def to_record(self) -> dict[str, object]:
        return {
            **self._content_record(),
            "mapping_id": self.mapping_id,
            "mapping_hash": self.mapping_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "CompatibilityMapping":
        canonical_domain_pack_json(record)
        _require_exact_keys(
            record,
            {
                "schema_version",
                "source_schema_version",
                "projection_kind",
                "legacy_value",
                "mapping_version",
                "target_kind",
                "target",
                "mapping_id",
                "mapping_hash",
            },
            "compatibility_mapping",
        )
        target_kind = _require_text(record["target_kind"], "target_kind")
        target = _compatibility_target_from_record(
            target_kind,
            _require_mapping(record["target"], "target"),
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            source_schema_version=_require_text(
                record["source_schema_version"],
                "source_schema_version",
            ),
            projection_kind=_require_text(
                record["projection_kind"],
                "projection_kind",
            ),
            legacy_value=_require_text(record["legacy_value"], "legacy_value"),
            mapping_version=_require_text(
                record["mapping_version"],
                "mapping_version",
            ),
            target=target,
            mapping_id=_require_text(record["mapping_id"], "mapping_id"),
            mapping_hash=_require_text(record["mapping_hash"], "mapping_hash"),
        )


@dataclass(frozen=True)
class CompatibilityResolutionFailure:
    reason_code: str
    schema_version: str = COMPATIBILITY_RESOLUTION_FAILURE_SCHEMA_VERSION
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.schema_version != COMPATIBILITY_RESOLUTION_FAILURE_SCHEMA_VERSION:
            raise DomainPackContractError(
                "unsupported_compatibility_resolution_failure_schema"
            )
        if (
            self.status != "rejected"
            or self.reason_code not in COMPATIBILITY_RESOLUTION_FAILURE_REASONS
        ):
            raise DomainPackContractError("invalid_compatibility_resolution_failure")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class CompatibilityMappingSet:
    mapping_set_id: str
    mapping_set_version: str
    mappings: tuple[CompatibilityMapping, ...]
    schema_version: str = COMPATIBILITY_MAPPING_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COMPATIBILITY_MAPPING_SET_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_compatibility_mapping_set_schema")
        _require_identifier(self.mapping_set_id, "mapping_set_id")
        _require_identifier(self.mapping_set_version, "mapping_set_version")
        if not isinstance(self.mappings, tuple) or any(
            not isinstance(item, CompatibilityMapping) for item in self.mappings
        ):
            raise DomainPackContractError("invalid_compatibility_mapping_set")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mapping_set_id": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "mappings": [
                item.to_record()
                for item in sorted(
                    self.mappings,
                    key=lambda item: (
                        item.source_schema_version,
                        item.projection_kind,
                        item.legacy_value,
                        item.mapping_version,
                        item.mapping_hash,
                    ),
                )
            ],
        }

    def mapping_set_hash(self) -> str:
        return canonical_domain_pack_hash(self.canonical_record())

    def contract_reference(self) -> DomainComponentContractReference:
        return DomainComponentContractReference(
            component_kind="compatibility_mapping_set",
            component_id=self.mapping_set_id,
            component_version=self.mapping_set_version,
            component_hash=self.mapping_set_hash(),
        )

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "CompatibilityMappingSet":
        canonical_domain_pack_json(record)
        _require_exact_keys(
            record,
            {
                "schema_version",
                "mapping_set_id",
                "mapping_set_version",
                "mappings",
            },
            "compatibility_mapping_set",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            mapping_set_id=_require_text(
                record["mapping_set_id"],
                "mapping_set_id",
            ),
            mapping_set_version=_require_text(
                record["mapping_set_version"],
                "mapping_set_version",
            ),
            mappings=tuple(
                CompatibilityMapping.from_record(item)
                for item in _require_record_sequence(record["mappings"], "mappings")
            ),
        )

    def resolve(
        self,
        *,
        source_schema_version: object,
        projection_kind: object,
        legacy_value: object,
    ) -> CompatibilityMapping | CompatibilityResolutionFailure:
        if (
            not isinstance(source_schema_version, str)
            or not isinstance(projection_kind, str)
            or not isinstance(legacy_value, str)
            or projection_kind not in COMPATIBILITY_PROJECTION_KINDS
        ):
            return CompatibilityResolutionFailure("invalid_compatibility_lookup")
        try:
            _require_identifier(source_schema_version, "source_schema_version")
            _require_identifier(legacy_value, "legacy_value")
        except DomainPackContractError:
            return CompatibilityResolutionFailure("invalid_compatibility_lookup")
        matches = tuple(
            item
            for item in self.mappings
            if item.source_schema_version == source_schema_version
            and item.projection_kind == projection_kind
            and item.legacy_value == legacy_value
        )
        if not matches:
            return CompatibilityResolutionFailure("unknown_compatibility_mapping")
        if len(matches) != 1:
            return CompatibilityResolutionFailure("ambiguous_compatibility_mapping")
        return matches[0]


@dataclass(frozen=True)
class DomainEvidenceReference:
    evidence_id: str
    evidence_schema_version: str
    evidence_hash: str
    schema_version: str = DOMAIN_EVIDENCE_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_EVIDENCE_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_evidence_reference_schema")
        _require_identifier(self.evidence_id, "evidence_id")
        _require_identifier(self.evidence_schema_version, "evidence_schema_version")
        _require_hash(self.evidence_hash, "evidence_hash")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "evidence_schema_version": self.evidence_schema_version,
            "evidence_hash": self.evidence_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "DomainEvidenceReference":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "evidence_id",
                "evidence_schema_version",
                "evidence_hash",
            },
            "domain_evidence_reference",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            evidence_id=_require_text(record["evidence_id"], "evidence_id"),
            evidence_schema_version=_require_text(
                record["evidence_schema_version"],
                "evidence_schema_version",
            ),
            evidence_hash=_require_text(record["evidence_hash"], "evidence_hash"),
        )


@dataclass(frozen=True)
class DomainAssessment:
    """A typed domain-evidence statement, never a release qualification."""

    domain_pack_reference: DomainPackReference
    plan_id: str
    plan_hash: str
    evidence_references: tuple[DomainEvidenceReference, ...]
    established_capability_references: tuple[DomainCapabilityReference, ...]
    status: str
    reason_code: str
    assessment_id: str
    assessment_hash: str
    schema_version: str = DOMAIN_ASSESSMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_ASSESSMENT_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_assessment_schema")
        if not isinstance(self.domain_pack_reference, DomainPackReference):
            raise DomainPackContractError("invalid_domain_assessment_pack")
        if (
            not isinstance(self.evidence_references, tuple)
            or not isinstance(self.established_capability_references, tuple)
            or any(
                not isinstance(item, DomainEvidenceReference)
                for item in self.evidence_references
            )
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.established_capability_references
            )
        ):
            raise DomainPackContractError("invalid_domain_assessment_references")
        _require_identifier(self.plan_id, "plan_id")
        _require_hash(self.plan_hash, "plan_hash")
        _require_identifier(self.assessment_id, "assessment_id")
        _require_hash(self.assessment_hash, "assessment_hash")
        if self.status == "established":
            if (
                self.reason_code != "exact_evidence_established"
                or not self.evidence_references
                or not self.established_capability_references
            ):
                raise DomainPackContractError("invalid_established_domain_assessment")
        elif self.status == "insufficient_evidence":
            if (
                self.reason_code not in DOMAIN_ASSESSMENT_INSUFFICIENCY_REASONS
                or self.established_capability_references
            ):
                raise DomainPackContractError("invalid_insufficient_domain_assessment")
        else:
            raise DomainPackContractError("invalid_domain_assessment_status")
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise DomainPackContractError("duplicate_evidence_reference")
        if len(set(self.established_capability_references)) != len(
            self.established_capability_references
        ):
            raise DomainPackContractError("duplicate_assessment_capability_reference")
        if any(
            item.domain_pack_id != self.domain_pack_reference.domain_pack_id
            for item in self.established_capability_references
        ):
            raise DomainPackContractError("cross_pack_assessment_capability_reference")
        expected_hash = canonical_domain_pack_hash(self._content_record())
        if self.assessment_hash != expected_hash:
            raise DomainPackContractError("domain_assessment_hash_mismatch")
        if self.assessment_id != (
            "domain_assessment_" + expected_hash.removeprefix("sha256:")[:16]
        ):
            raise DomainPackContractError("domain_assessment_id_mismatch")

    @classmethod
    def established(
        cls,
        plan: DomainPlan,
        *,
        evidence_references: tuple[DomainEvidenceReference, ...],
        established_capability_references: tuple[DomainCapabilityReference, ...],
    ) -> "DomainAssessment":
        _validate_assessment_inputs(
            plan,
            evidence_references=evidence_references,
            established_capability_references=established_capability_references,
        )
        assessment = cls._create(
            plan=plan,
            evidence_references=evidence_references,
            established_capability_references=established_capability_references,
            status="established",
            reason_code="exact_evidence_established",
        )
        assessment.validate_against_plan(plan)
        return assessment

    @classmethod
    def insufficient(
        cls,
        plan: DomainPlan,
        *,
        reason_code: str,
        evidence_references: tuple[DomainEvidenceReference, ...] = (),
    ) -> "DomainAssessment":
        if not isinstance(plan, DomainPlan):
            raise DomainPackContractError("invalid_domain_assessment_plan")
        if reason_code not in DOMAIN_ASSESSMENT_INSUFFICIENCY_REASONS:
            raise DomainPackContractError("invalid_domain_assessment_reason")
        if (
            not isinstance(evidence_references, tuple)
            or any(
                not isinstance(item, DomainEvidenceReference)
                for item in evidence_references
            )
            or len(set(evidence_references)) != len(evidence_references)
        ):
            raise DomainPackContractError("invalid_domain_assessment_evidence")
        assessment = cls._create(
            plan=plan,
            evidence_references=evidence_references,
            established_capability_references=(),
            status="insufficient_evidence",
            reason_code=reason_code,
        )
        assessment.validate_against_plan(plan)
        return assessment

    @classmethod
    def _create(
        cls,
        *,
        plan: DomainPlan,
        evidence_references: tuple[DomainEvidenceReference, ...],
        established_capability_references: tuple[DomainCapabilityReference, ...],
        status: str,
        reason_code: str,
    ) -> "DomainAssessment":
        content = _domain_assessment_content_record(
            schema_version=DOMAIN_ASSESSMENT_SCHEMA_VERSION,
            domain_pack_reference=plan.domain_pack_reference,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            evidence_references=evidence_references,
            established_capability_references=established_capability_references,
            status=status,
            reason_code=reason_code,
        )
        assessment_hash = canonical_domain_pack_hash(content)
        return cls(
            domain_pack_reference=plan.domain_pack_reference,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            evidence_references=evidence_references,
            established_capability_references=established_capability_references,
            status=status,
            reason_code=reason_code,
            assessment_id=(
                "domain_assessment_"
                + assessment_hash.removeprefix("sha256:")[:16]
            ),
            assessment_hash=assessment_hash,
        )

    def _content_record(self) -> dict[str, object]:
        return _domain_assessment_content_record(
            schema_version=self.schema_version,
            domain_pack_reference=self.domain_pack_reference,
            plan_id=self.plan_id,
            plan_hash=self.plan_hash,
            evidence_references=self.evidence_references,
            established_capability_references=self.established_capability_references,
            status=self.status,
            reason_code=self.reason_code,
        )

    def validate_against_plan(self, plan: DomainPlan) -> None:
        """Verify the assessment's exact plan and established capabilities."""

        if not isinstance(plan, DomainPlan):
            raise DomainPackContractError("invalid_domain_assessment_plan")
        if (
            self.domain_pack_reference != plan.domain_pack_reference
            or self.plan_id != plan.plan_id
            or self.plan_hash != plan.plan_hash
        ):
            raise DomainPackContractError("domain_assessment_plan_mismatch")
        if self.status == "established":
            _validate_assessment_inputs(
                plan,
                evidence_references=self.evidence_references,
                established_capability_references=self.established_capability_references,
            )

    def to_record(self) -> dict[str, object]:
        return {
            **self._content_record(),
            "assessment_id": self.assessment_id,
            "assessment_hash": self.assessment_hash,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
        *,
        plan: DomainPlan,
    ) -> "DomainAssessment":
        canonical_domain_pack_json(record)
        _require_exact_keys(
            record,
            {
                "schema_version",
                "domain_pack_reference",
                "plan_id",
                "plan_hash",
                "evidence_references",
                "established_capability_references",
                "status",
                "reason_code",
                "assessment_id",
                "assessment_hash",
            },
            "domain_assessment",
        )
        assessment = cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_reference=DomainPackReference.from_record(
                _require_mapping(
                    record["domain_pack_reference"],
                    "domain_pack_reference",
                )
            ),
            plan_id=_require_text(record["plan_id"], "plan_id"),
            plan_hash=_require_text(record["plan_hash"], "plan_hash"),
            evidence_references=tuple(
                DomainEvidenceReference.from_record(item)
                for item in _require_record_sequence(
                    record["evidence_references"],
                    "evidence_references",
                )
            ),
            established_capability_references=tuple(
                DomainCapabilityReference.from_record(item)
                for item in _require_record_sequence(
                    record["established_capability_references"],
                    "established_capability_references",
                )
            ),
            status=_require_text(record["status"], "status"),
            reason_code=_require_text(record["reason_code"], "reason_code"),
            assessment_id=_require_text(record["assessment_id"], "assessment_id"),
            assessment_hash=_require_text(
                record["assessment_hash"],
                "assessment_hash",
            ),
        )
        assessment.validate_against_plan(plan)
        return assessment


@dataclass(frozen=True)
class QualificationArtifactReference:
    artifact_id: str
    artifact_schema_version: str
    content_hash: str
    byte_count: int
    schema_version: str = QUALIFICATION_ARTIFACT_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != QUALIFICATION_ARTIFACT_REFERENCE_SCHEMA_VERSION:
            raise DomainPackContractError(
                "unsupported_qualification_artifact_reference_schema"
            )
        _require_identifier(self.artifact_id, "artifact_id")
        _require_identifier(self.artifact_schema_version, "artifact_schema_version")
        _require_hash(self.content_hash, "content_hash")
        if (
            not isinstance(self.byte_count, int)
            or isinstance(self.byte_count, bool)
            or self.byte_count <= 0
        ):
            raise DomainPackContractError("artifact_byte_count_invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_schema_version": self.artifact_schema_version,
            "content_hash": self.content_hash,
            "byte_count": self.byte_count,
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> "QualificationArtifactReference":
        _require_exact_keys(
            record,
            {
                "schema_version",
                "artifact_id",
                "artifact_schema_version",
                "content_hash",
                "byte_count",
            },
            "qualification_artifact_reference",
        )
        byte_count = record["byte_count"]
        if not isinstance(byte_count, int) or isinstance(byte_count, bool):
            raise DomainPackContractError("artifact_byte_count_invalid")
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            artifact_id=_require_text(record["artifact_id"], "artifact_id"),
            artifact_schema_version=_require_text(
                record["artifact_schema_version"],
                "artifact_schema_version",
            ),
            content_hash=_require_text(record["content_hash"], "content_hash"),
            byte_count=byte_count,
        )


@dataclass(frozen=True)
class QualificationSubject:
    """An immutable artifact subject to which a later evaluator may attach claims."""

    domain_pack_reference: DomainPackReference
    artifact_references: tuple[QualificationArtifactReference, ...]
    subject_id: str
    subject_hash: str
    schema_version: str = QUALIFICATION_SUBJECT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != QUALIFICATION_SUBJECT_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_qualification_subject_schema")
        if (
            not isinstance(self.domain_pack_reference, DomainPackReference)
            or not isinstance(self.artifact_references, tuple)
            or any(
                not isinstance(item, QualificationArtifactReference)
                for item in self.artifact_references
            )
        ):
            raise DomainPackContractError("invalid_qualification_subject")
        _require_identifier(self.subject_id, "subject_id")
        _require_hash(self.subject_hash, "subject_hash")
        if not self.artifact_references:
            raise DomainPackContractError("missing_qualification_artifact")
        if len({item.artifact_id for item in self.artifact_references}) != len(
            self.artifact_references
        ):
            raise DomainPackContractError("duplicate_qualification_artifact")
        expected_hash = canonical_domain_pack_hash(self._content_record())
        if self.subject_hash != expected_hash:
            raise DomainPackContractError("qualification_subject_hash_mismatch")
        if self.subject_id != (
            "qualification_subject_" + expected_hash.removeprefix("sha256:")[:16]
        ):
            raise DomainPackContractError("qualification_subject_id_mismatch")

    @classmethod
    def create(
        cls,
        *,
        domain_pack_reference: DomainPackReference,
        artifact_references: tuple[QualificationArtifactReference, ...],
    ) -> "QualificationSubject":
        if not isinstance(domain_pack_reference, DomainPackReference):
            raise DomainPackContractError("invalid_qualification_subject_pack")
        if (
            not isinstance(artifact_references, tuple)
            or any(
                not isinstance(item, QualificationArtifactReference)
                for item in artifact_references
            )
        ):
            raise DomainPackContractError("invalid_qualification_artifact")
        content = _qualification_subject_content_record(
            schema_version=QUALIFICATION_SUBJECT_SCHEMA_VERSION,
            domain_pack_reference=domain_pack_reference,
            artifact_references=artifact_references,
        )
        subject_hash = canonical_domain_pack_hash(content)
        return cls(
            domain_pack_reference=domain_pack_reference,
            artifact_references=artifact_references,
            subject_id=(
                "qualification_subject_" + subject_hash.removeprefix("sha256:")[:16]
            ),
            subject_hash=subject_hash,
        )

    def _content_record(self) -> dict[str, object]:
        return _qualification_subject_content_record(
            schema_version=self.schema_version,
            domain_pack_reference=self.domain_pack_reference,
            artifact_references=self.artifact_references,
        )

    def to_record(self) -> dict[str, object]:
        return {
            **self._content_record(),
            "subject_id": self.subject_id,
            "subject_hash": self.subject_hash,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "QualificationSubject":
        canonical_domain_pack_json(record)
        _require_exact_keys(
            record,
            {
                "schema_version",
                "domain_pack_reference",
                "artifact_references",
                "subject_id",
                "subject_hash",
            },
            "qualification_subject",
        )
        return cls(
            schema_version=_require_text(record["schema_version"], "schema_version"),
            domain_pack_reference=DomainPackReference.from_record(
                _require_mapping(
                    record["domain_pack_reference"],
                    "domain_pack_reference",
                )
            ),
            artifact_references=tuple(
                QualificationArtifactReference.from_record(item)
                for item in _require_record_sequence(
                    record["artifact_references"],
                    "artifact_references",
                )
            ),
            subject_id=_require_text(record["subject_id"], "subject_id"),
            subject_hash=_require_text(record["subject_hash"], "subject_hash"),
        )


@dataclass(frozen=True)
class OpenFailure:
    """A bounded failure returned before a Domain run is constructed."""

    reason_code: str
    schema_version: str = DOMAIN_OPEN_FAILURE_SCHEMA_VERSION
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_OPEN_FAILURE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_open_failure_schema")
        if self.status != "rejected" or self.reason_code not in OPEN_FAILURE_REASON_CODES:
            raise DomainPackContractError("invalid_domain_open_failure")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class DomainCandidateScope:
    """A plan-bound identity for one candidate-isolated Domain fork."""

    plan_id: str
    plan_hash: str
    candidate_id: str
    sequence_index: int
    schema_version: str = DOMAIN_CANDIDATE_SCOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_CANDIDATE_SCOPE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_candidate_scope_schema")
        _require_identifier(self.plan_id, "plan_id")
        _require_hash(self.plan_hash, "plan_hash")
        _require_identifier(self.candidate_id, "candidate_id")
        if (
            not isinstance(self.sequence_index, int)
            or isinstance(self.sequence_index, bool)
            or self.sequence_index < 0
        ):
            raise DomainPackContractError("invalid_domain_candidate_scope")

    @classmethod
    def for_plan(
        cls,
        plan: DomainPlan,
        *,
        candidate_id: str,
        sequence_index: int,
    ) -> "DomainCandidateScope":
        if not isinstance(plan, DomainPlan):
            raise DomainPackContractError("invalid_domain_candidate_scope_plan")
        return cls(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            candidate_id=candidate_id,
            sequence_index=sequence_index,
        )


@dataclass(frozen=True)
class DomainAssessmentEvidence:
    """Exact evidence offered to a Domain Pack without qualification authority."""

    evidence_references: tuple[DomainEvidenceReference, ...]
    established_capability_references: tuple[DomainCapabilityReference, ...] = ()
    insufficiency_reason: str | None = None
    schema_version: str = DOMAIN_ASSESSMENT_EVIDENCE_SCHEMA_VERSION
    evaluation_evidence_references: tuple[DomainEvidenceReference, ...] = ()
    release_evidence_references: tuple[DomainEvidenceReference, ...] = ()
    plan_id: str | None = None
    plan_hash: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_ASSESSMENT_EVIDENCE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_assessment_evidence_schema")
        if (
            not isinstance(self.evidence_references, tuple)
            or not isinstance(self.established_capability_references, tuple)
            or not isinstance(self.evaluation_evidence_references, tuple)
            or not isinstance(self.release_evidence_references, tuple)
            or any(
                not isinstance(item, DomainEvidenceReference)
                for item in self.evidence_references
            )
            or any(
                not isinstance(item, DomainCapabilityReference)
                for item in self.established_capability_references
            )
            or len(set(self.evidence_references)) != len(self.evidence_references)
            or len(set(self.established_capability_references))
            != len(self.established_capability_references)
            or any(
                not isinstance(item, DomainEvidenceReference)
                for item in (
                    *self.evaluation_evidence_references,
                    *self.release_evidence_references,
                )
            )
            or len(set(self.evaluation_evidence_references))
            != len(self.evaluation_evidence_references)
            or len(set(self.release_evidence_references))
            != len(self.release_evidence_references)
        ):
            raise DomainPackContractError("invalid_domain_assessment_evidence")
        if (self.plan_id is None) != (self.plan_hash is None):
            raise DomainPackContractError("invalid_domain_assessment_evidence")
        if self.plan_id is not None:
            _require_identifier(self.plan_id, "plan_id")
            _require_hash(self.plan_hash, "plan_hash")
        if self.insufficiency_reason is not None:
            if (
                self.insufficiency_reason
                not in DOMAIN_ASSESSMENT_INSUFFICIENCY_REASONS
                or self.established_capability_references
            ):
                raise DomainPackContractError("invalid_domain_assessment_evidence")


@dataclass(frozen=True)
class AssessmentFailure:
    """A bounded failure when an assessment cannot bind its declared plan."""

    reason_code: str
    schema_version: str = DOMAIN_ASSESSMENT_FAILURE_SCHEMA_VERSION
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.schema_version != DOMAIN_ASSESSMENT_FAILURE_SCHEMA_VERSION:
            raise DomainPackContractError("unsupported_domain_assessment_failure_schema")
        if (
            self.status != "rejected"
            or self.reason_code not in ASSESSMENT_FAILURE_REASON_CODES
        ):
            raise DomainPackContractError("invalid_domain_assessment_failure")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
        }


class DomainPackLifecycle(Protocol):
    """Runtime adapter selected by a Domain Pack without exposing its internals."""

    def open(self, plan: DomainPlan, runtime_scope: object) -> object:
        ...


@runtime_checkable
class DomainPackAssessmentLifecycle(Protocol):
    """Optional typed assessment adapter owned by a Domain Pack."""

    def assess(
        self,
        plan: DomainPlan,
        exact_evidence: object,
    ) -> DomainAssessment | AssessmentFailure:
        ...


@dataclass(frozen=True)
class DomainPack:
    """The public plan/open/assess boundary for one immutable Domain Pack."""

    descriptor: DomainPackDescriptor
    compatibility_mapping_set: CompatibilityMappingSet | None = None
    lifecycle: DomainPackLifecycle | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, DomainPackDescriptor):
            raise DomainPackContractError("invalid_domain_pack_descriptor")
        if self.compatibility_mapping_set is None:
            return
        selected = next(
            (
                item
                for item in self.descriptor.component_contracts
                if item.component_kind == "compatibility_mapping_set"
            ),
            None,
        )
        if (
            selected != self.compatibility_mapping_set.contract_reference()
            and not _compatibility_mapping_set_scoped_to_descriptor(
                self.compatibility_mapping_set,
                self.descriptor,
            )
        ):
            raise DomainPackContractError("incompatible_compatibility_mapping_set")

    def plan(
        self,
        intent: object,
        admitted_source: object,
    ) -> DomainPlan | PlanFailure:
        try:
            return _compile_domain_plan(
                self.descriptor,
                intent,
                admitted_source,
                compatibility_mapping_set=self.compatibility_mapping_set,
            )
        except DomainPackContractError as error:
            return PlanFailure(_planning_reason_for(error.reason_code))

    def open(self, plan: object, runtime_scope: object) -> object:
        """Open a run only after the complete immutable plan has been rechecked."""

        reason = _lifecycle_plan_failure_reason(
            descriptor=self.descriptor,
            compatibility_mapping_set=self.compatibility_mapping_set,
            plan=plan,
        )
        if reason is not None:
            return OpenFailure(reason)
        assert isinstance(plan, DomainPlan)
        if self.lifecycle is None:
            return OpenFailure("runtime_scope_unavailable")
        try:
            return self.lifecycle.open(plan, runtime_scope)
        except DomainPackContractError:
            return OpenFailure("invalid_runtime_scope")
        except Exception:
            return OpenFailure("runtime_construction_failed")

    def assess(
        self,
        plan: object,
        exact_evidence: object,
    ) -> DomainAssessment | AssessmentFailure:
        """Bind exact evidence to one plan without granting a qualification."""

        reason = _lifecycle_plan_failure_reason(
            descriptor=self.descriptor,
            compatibility_mapping_set=self.compatibility_mapping_set,
            plan=plan,
        )
        if reason is not None:
            return AssessmentFailure(reason)
        assert isinstance(plan, DomainPlan)
        if isinstance(self.lifecycle, DomainPackAssessmentLifecycle):
            try:
                assessed = self.lifecycle.assess(plan, exact_evidence)
            except DomainPackContractError:
                return AssessmentFailure("invalid_assessment_evidence")
            if isinstance(assessed, (DomainAssessment, AssessmentFailure)):
                return assessed
            return AssessmentFailure("invalid_assessment_evidence")
        if isinstance(exact_evidence, DomainAssessment):
            try:
                exact_evidence.validate_against_plan(plan)
            except DomainPackContractError:
                return AssessmentFailure("assessment_plan_drift")
            return exact_evidence
        if not isinstance(exact_evidence, DomainAssessmentEvidence):
            return AssessmentFailure("invalid_assessment_evidence")
        try:
            if exact_evidence.insufficiency_reason is not None:
                return DomainAssessment.insufficient(
                    plan,
                    reason_code=exact_evidence.insufficiency_reason,
                    evidence_references=exact_evidence.evidence_references,
                )
            return DomainAssessment.established(
                plan,
                evidence_references=exact_evidence.evidence_references,
                established_capability_references=(
                    exact_evidence.established_capability_references
                ),
            )
        except DomainPackContractError:
            return AssessmentFailure("invalid_assessment_evidence")


@dataclass(frozen=True)
class DomainPackRegistry:
    descriptors: tuple[DomainPackDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.descriptors, tuple):
            raise DomainPackContractError("invalid_domain_pack_registry")
        seen: dict[tuple[str, str], str] = {}
        for descriptor in self.descriptors:
            if not isinstance(descriptor, DomainPackDescriptor):
                raise DomainPackContractError("invalid_domain_pack_descriptor")
            key = (descriptor.domain_pack_id, descriptor.pack_version)
            existing_hash = seen.get(key)
            if existing_hash is not None:
                if existing_hash != descriptor.pack_hash():
                    raise DomainPackContractError("pack_version_reused_with_different_content")
                raise DomainPackContractError("duplicate_domain_pack_version")
            seen[key] = descriptor.pack_hash()

    def register(self, descriptor: DomainPackDescriptor) -> "DomainPackRegistry":
        return DomainPackRegistry((*self.descriptors, descriptor))

    def descriptor_for(
        self,
        domain_pack_id: str,
        pack_version: str | None = None,
    ) -> DomainPackDescriptor:
        _require_identifier(domain_pack_id, "domain_pack_id")
        matches = [
            item
            for item in self.descriptors
            if item.domain_pack_id == domain_pack_id
            and (pack_version is None or item.pack_version == pack_version)
        ]
        if not matches:
            raise DomainPackContractError(
                "unknown_domain_pack"
                if not any(
                    item.domain_pack_id == domain_pack_id for item in self.descriptors
                )
                else "unsupported_pack_version"
            )
        if len(matches) != 1:
            raise DomainPackContractError("ambiguous_domain_pack_version")
        return matches[0]

    def resolve(self, reference: DomainPackReference) -> DomainPackDescriptor:
        descriptor = self.descriptor_for(
            reference.domain_pack_id,
            reference.pack_version,
        )
        if descriptor.pack_hash() != reference.pack_hash:
            raise DomainPackContractError("domain_pack_hash_mismatch")
        return descriptor

    def plan(
        self,
        intent: object,
        admitted_source: object,
    ) -> DomainPlan | PlanFailure:
        if not isinstance(intent, DomainPlanningIntent):
            return PlanFailure("invalid_planning_intent")
        if not isinstance(intent.domain_pack_reference, DomainPackReference):
            return PlanFailure("invalid_planning_intent")
        try:
            descriptor = self.resolve(intent.domain_pack_reference)
        except DomainPackContractError as error:
            return PlanFailure(_planning_reason_for(error.reason_code))
        return DomainPack(descriptor).plan(intent, admitted_source)


def _lifecycle_plan_failure_reason(
    *,
    descriptor: DomainPackDescriptor,
    compatibility_mapping_set: CompatibilityMappingSet | None,
    plan: object,
) -> str | None:
    if not isinstance(plan, DomainPlan):
        return "invalid_domain_plan"
    if plan.domain_pack_reference != descriptor.reference():
        return "domain_pack_drift"
    try:
        plan.validate_against_descriptor(
            descriptor,
            compatibility_mapping_set=compatibility_mapping_set,
        )
    except DomainPackContractError:
        return "plan_contract_drift"
    return None


def _compile_domain_plan(
    descriptor: DomainPackDescriptor,
    intent: object,
    admitted_source: object,
    *,
    compatibility_mapping_set: CompatibilityMappingSet | None,
) -> DomainPlan:
    if not isinstance(intent, DomainPlanningIntent):
        raise DomainPackContractError("invalid_planning_intent")
    if not isinstance(admitted_source, AdmittedSource):
        raise DomainPackContractError("invalid_planning_intent")
    if admitted_source.admission_status != "admitted":
        raise DomainPackContractError("admitted_source_not_admitted")
    plan_requirements = descriptor.plan_requirements()
    held_out_capability_references = tuple(
        sorted(descriptor.held_out_capability_references, key=_capability_sort_key)
    )
    selected_projections, selected_capabilities, validated_runtime_contract = (
        _normalize_plan_selection_against_descriptor(
            descriptor,
            domain_pack_reference=intent.domain_pack_reference,
            task_type_keys=intent.task_type_keys,
            task_capability_projections=None,
            capability_references=intent.capability_references,
            runtime_contract=intent.runtime_contract,
            plan_requirements=plan_requirements,
            held_out_capability_references=held_out_capability_references,
        )
    )
    compatibility_mapping = _resolve_legacy_projection(
        legacy_projection=intent.legacy_projection,
        compatibility_mapping_set=compatibility_mapping_set,
        descriptor=descriptor,
        capability_references=selected_capabilities,
        runtime_contract=validated_runtime_contract,
    )
    return DomainPlan._create_unchecked(
        domain_pack_reference=descriptor.reference(),
        admitted_source=admitted_source,
        runtime_contract=validated_runtime_contract,
        task_capability_projections=selected_projections,
        capability_references=selected_capabilities,
        plan_requirements=plan_requirements,
        held_out_capability_references=held_out_capability_references,
        compatibility_mapping=compatibility_mapping,
    )


def _validate_intent_domain_pack_reference(
    descriptor: DomainPackDescriptor,
    value: object,
) -> None:
    if not isinstance(value, DomainPackReference):
        raise DomainPackContractError("invalid_planning_intent")
    if value.domain_pack_id != descriptor.domain_pack_id:
        raise DomainPackContractError("cross_pack_domain_reference")
    if value.pack_version != descriptor.pack_version:
        raise DomainPackContractError("unsupported_pack_version")
    if value.pack_hash != descriptor.pack_hash():
        raise DomainPackContractError("domain_pack_hash_mismatch")


def _select_task_capability_projections(
    descriptor: DomainPackDescriptor,
    task_type_keys: object,
) -> tuple[TaskCapabilityProjection, ...]:
    if not isinstance(task_type_keys, tuple) or not task_type_keys:
        raise DomainPackContractError("missing_task_type_projection")
    if any(not isinstance(item, str) for item in task_type_keys):
        raise DomainPackContractError("invalid_planning_intent")
    if len(set(task_type_keys)) != len(task_type_keys):
        raise DomainPackContractError("duplicate_task_type_projection")
    projections = {
        item.task_type_key: item for item in descriptor.task_capability_projections
    }
    selected: list[TaskCapabilityProjection] = []
    for task_type_key in task_type_keys:
        _require_identifier(task_type_key, "task_type_key")
        projection = projections.get(task_type_key)
        if projection is None:
            raise DomainPackContractError("unknown_task_type_projection")
        selected.append(projection)
    return tuple(selected)


def _select_capability_references(
    descriptor: DomainPackDescriptor,
    capability_references: object,
) -> tuple[DomainCapabilityReference, ...]:
    if not isinstance(capability_references, tuple) or not capability_references:
        raise DomainPackContractError("missing_capability_reference")
    selected: list[DomainCapabilityReference] = []
    seen_identity: set[tuple[str, str]] = set()
    declared_by_key = {
        item.capability_key: item for item in descriptor.capability_references
    }
    for reference in capability_references:
        if not isinstance(reference, DomainCapabilityReference):
            raise DomainPackContractError("invalid_planning_intent")
        identity = (reference.domain_pack_id, reference.capability_key)
        if identity in seen_identity:
            raise DomainPackContractError("duplicate_capability_reference")
        seen_identity.add(identity)
        if reference.domain_pack_id != descriptor.domain_pack_id:
            raise DomainPackContractError("cross_pack_capability_reference")
        declared = declared_by_key.get(reference.capability_key)
        if declared is None:
            raise DomainPackContractError("unknown_capability_reference")
        if reference != declared:
            raise DomainPackContractError("unsupported_capability_contract_version")
        selected.append(reference)
    return tuple(selected)


def _normalize_plan_selection_against_descriptor(
    descriptor: object,
    *,
    domain_pack_reference: object,
    task_type_keys: object,
    task_capability_projections: object | None,
    capability_references: object,
    runtime_contract: object,
    plan_requirements: object,
    held_out_capability_references: object,
) -> tuple[
    tuple[TaskCapabilityProjection, ...],
    tuple[DomainCapabilityReference, ...],
    DomainRuntimeContractReference,
]:
    """Validate and canonicalize all non-legacy selections for one plan."""

    if not isinstance(descriptor, DomainPackDescriptor):
        raise DomainPackContractError("invalid_domain_pack_descriptor")
    _validate_intent_domain_pack_reference(descriptor, domain_pack_reference)
    selected_projections = tuple(
        sorted(
            _select_task_capability_projections(descriptor, task_type_keys),
            key=lambda item: item.task_type_key,
        )
    )
    if task_capability_projections is not None:
        if (
            not isinstance(task_capability_projections, tuple)
            or any(
                not isinstance(item, TaskCapabilityProjection)
                for item in task_capability_projections
            )
            or len(task_capability_projections) != len(selected_projections)
            or {
                (item.task_type_key, frozenset(item.capability_references))
                for item in task_capability_projections
            }
            != {
                (item.task_type_key, frozenset(item.capability_references))
                for item in selected_projections
            }
        ):
            raise DomainPackContractError("capability_projection_mismatch")
    selected_capabilities = tuple(
        sorted(
            _select_capability_references(descriptor, capability_references),
            key=_capability_sort_key,
        )
    )
    selected_capability_set = set(selected_capabilities)
    if any(
        not set(projection.capability_references) <= selected_capability_set
        for projection in selected_projections
    ):
        raise DomainPackContractError("capability_projection_mismatch")
    if (
        not isinstance(runtime_contract, DomainRuntimeContractReference)
        or runtime_contract not in descriptor.runtime_contracts
    ):
        raise DomainPackContractError("unsupported_runtime_contract")
    if plan_requirements != descriptor.plan_requirements():
        raise DomainPackContractError("internally_inconsistent_descriptor")
    expected_held_out = set(descriptor.held_out_capability_references)
    if (
        not isinstance(held_out_capability_references, tuple)
        or any(
            not isinstance(item, DomainCapabilityReference)
            for item in held_out_capability_references
        )
        or len(held_out_capability_references) != len(expected_held_out)
        or set(held_out_capability_references) != expected_held_out
    ):
        raise DomainPackContractError("capability_projection_mismatch")
    return selected_projections, selected_capabilities, runtime_contract


def _validate_stored_compatibility_mapping(
    *,
    mapping: CompatibilityMapping,
    compatibility_mapping_set: CompatibilityMappingSet | None,
    descriptor: DomainPackDescriptor,
    capability_references: tuple[DomainCapabilityReference, ...],
    runtime_contract: DomainRuntimeContractReference,
) -> None:
    if compatibility_mapping_set is None:
        raise DomainPackContractError("unknown_compatibility_mapping")
    selected_mapping_reference = next(
        (
            item
            for item in descriptor.component_contracts
            if item.component_kind == "compatibility_mapping_set"
        ),
        None,
    )
    if (
        selected_mapping_reference != compatibility_mapping_set.contract_reference()
        and not _compatibility_mapping_set_scoped_to_descriptor(
            compatibility_mapping_set,
            descriptor,
        )
    ):
        raise DomainPackContractError("compatibility_mapping_target_mismatch")
    resolved_mapping = compatibility_mapping_set.resolve(
        source_schema_version=mapping.source_schema_version,
        projection_kind=mapping.projection_kind,
        legacy_value=mapping.legacy_value,
    )
    if isinstance(resolved_mapping, CompatibilityResolutionFailure):
        raise DomainPackContractError(resolved_mapping.reason_code)
    if resolved_mapping != mapping:
        raise DomainPackContractError("compatibility_mapping_target_mismatch")
    if not _compatibility_target_matches_plan(
        target=mapping.target,
        descriptor=descriptor,
        capability_references=capability_references,
        runtime_contract=runtime_contract,
    ):
        raise DomainPackContractError("compatibility_mapping_target_mismatch")


def _resolve_legacy_projection(
    *,
    legacy_projection: object,
    compatibility_mapping_set: CompatibilityMappingSet | None,
    descriptor: DomainPackDescriptor,
    capability_references: tuple[DomainCapabilityReference, ...],
    runtime_contract: DomainRuntimeContractReference,
) -> CompatibilityMapping | None:
    if legacy_projection is None:
        return None
    if not isinstance(legacy_projection, LegacyProjection):
        raise DomainPackContractError("invalid_planning_intent")
    if compatibility_mapping_set is None:
        raise DomainPackContractError("unknown_compatibility_mapping")
    resolved = compatibility_mapping_set.resolve(
        source_schema_version=legacy_projection.source_schema_version,
        projection_kind=legacy_projection.projection_kind,
        legacy_value=legacy_projection.legacy_value,
    )
    if isinstance(resolved, CompatibilityResolutionFailure):
        raise DomainPackContractError(resolved.reason_code)
    _validate_stored_compatibility_mapping(
        mapping=resolved,
        compatibility_mapping_set=compatibility_mapping_set,
        descriptor=descriptor,
        capability_references=capability_references,
        runtime_contract=runtime_contract,
    )
    return resolved


def _compatibility_target_matches_plan(
    *,
    target: CompatibilityTarget,
    descriptor: DomainPackDescriptor,
    capability_references: tuple[DomainCapabilityReference, ...],
    runtime_contract: DomainRuntimeContractReference,
) -> bool:
    if isinstance(target, DomainPackReference):
        return target == descriptor.reference()
    if isinstance(target, DomainCapabilityReference):
        return target in capability_references
    if isinstance(target, DomainRuntimeContractReference):
        return target == runtime_contract
    if isinstance(target, DomainComponentContractReference):
        return target in descriptor.component_contracts
    return False


def _compatibility_mapping_set_scoped_to_descriptor(
    mapping_set: CompatibilityMappingSet,
    descriptor: DomainPackDescriptor,
) -> bool:
    """Allow an external legacy map only when every target is pack-local.

    Initial descriptors retain a no-legacy-projection component reference for
    ordinary planning.  Compatibility readers may provide a versioned mapping
    set at the boundary, but that set must still be wholly scoped to the
    descriptor before a plan can be validated or opened.
    """

    if not mapping_set.mappings:
        return False
    capability_references = (
        *descriptor.capability_references,
        *descriptor.held_out_capability_references,
    )
    return all(
        _compatibility_target_matches_plan(
            target=item.target,
            descriptor=descriptor,
            capability_references=capability_references,
            runtime_contract=descriptor.runtime_contracts[0],
        )
        for item in mapping_set.mappings
    )


def _domain_plan_content_record(
    *,
    schema_version: str,
    domain_pack_reference: DomainPackReference,
    admitted_source: AdmittedSource,
    runtime_contract: DomainRuntimeContractReference,
    task_capability_projections: tuple[TaskCapabilityProjection, ...],
    capability_references: tuple[DomainCapabilityReference, ...],
    plan_requirements: DomainPlanRequirements,
    held_out_capability_references: tuple[DomainCapabilityReference, ...],
    compatibility_mapping: CompatibilityMapping | None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": schema_version,
        "domain_pack_reference": domain_pack_reference.to_record(),
        "admitted_source": admitted_source.to_record(),
        "runtime_contract": runtime_contract.to_record(),
        "task_capability_projections": [
            item.to_record()
            for item in sorted(
                task_capability_projections,
                key=lambda item: item.task_type_key,
            )
        ],
        "capability_references": [
            item.to_record()
            for item in sorted(capability_references, key=_capability_sort_key)
        ],
        "plan_requirements": plan_requirements.to_record(),
        "held_out_capability_references": [
            item.to_record()
            for item in sorted(
                held_out_capability_references,
                key=_capability_sort_key,
            )
        ],
    }
    if compatibility_mapping is not None:
        record["compatibility_mapping"] = compatibility_mapping.to_record()
    return record


def _compatibility_mapping_content_record(
    *,
    schema_version: str,
    source_schema_version: str,
    projection_kind: str,
    legacy_value: str,
    mapping_version: str,
    target: CompatibilityTarget,
) -> dict[str, object]:
    _validate_compatibility_mapping_target(projection_kind, target)
    return {
        "schema_version": schema_version,
        "source_schema_version": source_schema_version,
        "projection_kind": projection_kind,
        "legacy_value": legacy_value,
        "mapping_version": mapping_version,
        "target_kind": _compatibility_target_kind(target),
        "target": target.to_record(),
    }


def _compatibility_target_kind(target: CompatibilityTarget) -> str:
    if isinstance(target, DomainPackReference):
        return "domain_pack_reference"
    if isinstance(target, DomainCapabilityReference):
        return "domain_capability_reference"
    if isinstance(target, DomainRuntimeContractReference):
        return "domain_runtime_contract_reference"
    if isinstance(target, DomainComponentContractReference):
        return "domain_component_contract_reference"
    raise DomainPackContractError("invalid_compatibility_mapping_target")


def _compatibility_target_from_record(
    target_kind: str,
    record: Mapping[str, object],
) -> CompatibilityTarget:
    if target_kind == "domain_pack_reference":
        return DomainPackReference.from_record(record)
    if target_kind == "domain_capability_reference":
        return DomainCapabilityReference.from_record(record)
    if target_kind == "domain_runtime_contract_reference":
        return DomainRuntimeContractReference.from_record(record)
    if target_kind == "domain_component_contract_reference":
        return DomainComponentContractReference.from_record(record)
    raise DomainPackContractError("invalid_compatibility_mapping_target")


def _validate_compatibility_mapping_target(
    projection_kind: str,
    target: object,
) -> None:
    expected_types: dict[str, type[object]] = {
        "semantic_domain": DomainPackReference,
        "capability": DomainCapabilityReference,
        "held_out_capability": DomainCapabilityReference,
        "runtime": DomainRuntimeContractReference,
        "task_type": DomainComponentContractReference,
        "tool": DomainComponentContractReference,
        "coverage_cell": DomainComponentContractReference,
        "mutation_policy": DomainComponentContractReference,
    }
    expected_type = expected_types.get(projection_kind)
    if expected_type is None or not isinstance(target, expected_type):
        raise DomainPackContractError("invalid_compatibility_mapping_target")


def _validate_assessment_inputs(
    plan: object,
    *,
    evidence_references: object,
    established_capability_references: object,
) -> None:
    if not isinstance(plan, DomainPlan):
        raise DomainPackContractError("invalid_domain_assessment_plan")
    if (
        not isinstance(evidence_references, tuple)
        or not evidence_references
        or any(
            not isinstance(item, DomainEvidenceReference)
            for item in evidence_references
        )
        or len(set(evidence_references)) != len(evidence_references)
    ):
        raise DomainPackContractError("invalid_domain_assessment_evidence")
    if (
        not isinstance(established_capability_references, tuple)
        or not established_capability_references
        or any(
            not isinstance(item, DomainCapabilityReference)
            for item in established_capability_references
        )
        or len(set(established_capability_references))
        != len(established_capability_references)
    ):
        raise DomainPackContractError("invalid_domain_assessment_capabilities")
    plan_capabilities = set(plan.capability_references) | set(
        plan.held_out_capability_references
    )
    if not set(established_capability_references) <= plan_capabilities:
        raise DomainPackContractError("assessment_capability_not_in_plan")


def _domain_assessment_content_record(
    *,
    schema_version: str,
    domain_pack_reference: DomainPackReference,
    plan_id: str,
    plan_hash: str,
    evidence_references: tuple[DomainEvidenceReference, ...],
    established_capability_references: tuple[DomainCapabilityReference, ...],
    status: str,
    reason_code: str,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "domain_pack_reference": domain_pack_reference.to_record(),
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "evidence_references": [
            item.to_record()
            for item in sorted(
                evidence_references,
                key=lambda item: (
                    item.evidence_id,
                    item.evidence_schema_version,
                    item.evidence_hash,
                ),
            )
        ],
        "established_capability_references": [
            item.to_record()
            for item in sorted(
                established_capability_references,
                key=_capability_sort_key,
            )
        ],
        "status": status,
        "reason_code": reason_code,
    }


def _qualification_subject_content_record(
    *,
    schema_version: str,
    domain_pack_reference: DomainPackReference,
    artifact_references: tuple[QualificationArtifactReference, ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "domain_pack_reference": domain_pack_reference.to_record(),
        "artifact_references": [
            item.to_record()
            for item in sorted(
                artifact_references,
                key=lambda item: (
                    item.artifact_id,
                    item.artifact_schema_version,
                    item.content_hash,
                ),
            )
        ],
    }


def _planning_reason_for(reason_code: str) -> str:
    if reason_code in PLAN_FAILURE_REASON_CODES:
        return reason_code
    if reason_code in {
        "missing_capability_catalog",
        "incomplete_component_contracts",
        "missing_runtime_contract",
        "missing_task_capability_projection",
        "missing_held_out_capability_projection",
        "unknown_projection_capability",
        "unknown_held_out_capability",
    }:
        return "internally_inconsistent_descriptor"
    return "invalid_planning_intent"


def initial_domain_pack_registry() -> DomainPackRegistry:
    return DomainPackRegistry(
        (
            _initial_descriptor(
                "contacts",
                runtime_id="contacts_fixture",
                capabilities=(
                    "contact_lookup",
                    "followup_recording",
                    "contact_lookup_recovery",
                    "missing_contact_safe_failure",
                ),
                task_projections=(
                    ("contact_lookup", ("contact_lookup",)),
                    (
                        "contact_followup",
                        ("contact_lookup", "followup_recording"),
                    ),
                    (
                        "contact_lookup_recovery",
                        ("contact_lookup", "contact_lookup_recovery"),
                    ),
                ),
            ),
            _initial_descriptor(
                "mobile_messages",
                runtime_id="mobile_messages_fixture",
                capabilities=(
                    "message_search",
                    "reminder_creation",
                    "draft_reply",
                    "message_search_recovery",
                    "missing_message_safe_failure",
                ),
                task_projections=(
                    ("mobile_message_search", ("message_search",)),
                    (
                        "mobile_reminder_creation",
                        ("message_search", "reminder_creation"),
                    ),
                    (
                        "mobile_draft_reply",
                        ("message_search", "draft_reply"),
                    ),
                    (
                        "mobile_message_search_recovery",
                        ("message_search", "message_search_recovery"),
                    ),
                ),
            ),
            _initial_descriptor(
                "workspace_tasks",
                runtime_id="workspace_tasks_fixture",
                capabilities=(
                    "item_search",
                    "task_creation",
                    "comment_addition",
                    "item_search_recovery",
                    "missing_item_safe_failure",
                ),
                task_projections=(
                    ("workspace_item_search", ("item_search",)),
                    (
                        "workspace_task_creation",
                        ("item_search", "task_creation"),
                    ),
                    (
                        "workspace_comment_update",
                        ("item_search", "comment_addition"),
                    ),
                ),
            ),
        )
    )


def _initial_descriptor(
    domain_pack_id: str,
    *,
    runtime_id: str,
    capabilities: tuple[str, ...],
    task_projections: tuple[tuple[str, tuple[str, ...]], ...],
) -> DomainPackDescriptor:
    capability_references = tuple(
        DomainCapabilityReference(
            domain_pack_id=domain_pack_id,
            capability_key=capability_key,
            capability_contract_version=(
                f"{domain_pack_id}_{capability_key}_contract_v1"
            ),
        )
        for capability_key in capabilities
    )
    capabilities_by_key = {
        item.capability_key: item for item in capability_references
    }
    return DomainPackDescriptor(
        domain_pack_id=domain_pack_id,
        pack_version=f"{domain_pack_id}_pack_v1",
        capability_references=capability_references,
        component_contracts=tuple(
            _initial_component_reference(
                domain_pack_id,
                component_kind,
                capabilities=capabilities,
                task_projections=task_projections,
            )
            for component_kind in sorted(REQUIRED_COMPONENT_KINDS)
        ),
        runtime_contracts=(
            _initial_runtime_contract_reference(
                domain_pack_id,
                runtime_id,
                capabilities=capabilities,
            ),
        ),
        task_capability_projections=tuple(
            TaskCapabilityProjection(
                task_type_key=task_type_key,
                capability_references=tuple(
                    capabilities_by_key[capability_key]
                    for capability_key in capability_keys
                ),
            )
            for task_type_key, capability_keys in task_projections
        ),
        held_out_capability_references=capability_references,
    )


def _initial_component_reference(
    domain_pack_id: str,
    component_kind: str,
    *,
    capabilities: tuple[str, ...],
    task_projections: tuple[tuple[str, tuple[str, ...]], ...],
) -> DomainComponentContractReference:
    component_id = f"{domain_pack_id}_{component_kind}"
    component_version = f"{component_id}_v1"
    return DomainComponentContractReference(
        component_kind=component_kind,
        component_id=component_id,
        component_version=component_version,
        component_hash=canonical_domain_pack_hash(
            {
                "component_kind": component_kind,
                "component_id": component_id,
                "component_version": component_version,
                "contract_content": _initial_component_contract_content(
                    domain_pack_id,
                    component_kind,
                    capabilities=capabilities,
                    task_projections=task_projections,
                ),
            }
        ),
    )


def _initial_component_contract_content(
    domain_pack_id: str,
    component_kind: str,
    *,
    capabilities: tuple[str, ...],
    task_projections: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, object]:
    """Canonical initial content behind each exact component reference.

    These records deliberately state the contract behavior selected by the
    descriptor rather than deriving a digest from identifier labels alone.
    Future lifecycle components must compare their own canonical content to the
    selected hash before they are admitted to a Domain run.
    """

    task_type_keys = [task_type_key for task_type_key, _ in task_projections]
    projection_capability_keys = {
        task_type_key: list(capability_keys)
        for task_type_key, capability_keys in task_projections
    }
    content_by_kind: dict[str, dict[str, object]] = {
        "task_taxonomy": {
            "task_type_keys": task_type_keys,
            "capability_projections": projection_capability_keys,
        },
        "generation": {
            "generation_boundary": "shared_framework_provider_selection_v1",
            "task_contract_source": "domain_pack_task_taxonomy_v1",
        },
        "capability_evidence_floors": {
            "capability_keys": list(capabilities),
            "evidence_binding": "exact_capability_reference_v1",
        },
        "coverage_catalog": {
            "coverage_capability_keys": list(capabilities),
            "catalog_schema": "domain_capability_coverage_catalog_v1",
        },
        "coverage_profile": {
            "profile_id": f"{domain_pack_id}_initial_coverage_profile_v1",
            "selection_mode": "descriptor_fixed_v1",
        },
        "compiled_coverage_plan": {
            "compiler_contract": "domain_pack_coverage_compiler_v1",
            "assignment_source": "exact_coverage_profile_v1",
        },
        "assignment_policy": {
            "assignment_contract": "capability_projection_assignment_v1",
            "recovery_assignment": "explicit_assignment_structure_v1",
        },
        "parser_contract": {
            "parser_contract": "bounded_domain_task_parser_v1",
            "failure_mode": "bounded_rejection_v1",
        },
        "grounding_contract": {
            "grounding_contract": "admitted_source_grounding_v1",
            "source_boundary": "sanitized_admitted_source_v1",
        },
        "expected_state_contract": {
            "expected_state_contract": "domain_expected_state_v1",
            "state_comparison": "canonical_exact_v1",
        },
        "membership_contract": {
            "membership_contract": "exact_capability_membership_v1",
            "projection_consistency": "pre_execution_required_v1",
        },
        "held_out_suite": {
            "held_out_suite_id": f"{domain_pack_id}_held_out_suite_v1",
            "capability_keys": list(capabilities),
        },
        "held_out_tasks": {
            "held_out_task_contract": "canonical_held_out_tasks_v1",
            "capability_keys": list(capabilities),
        },
        "held_out_thresholds": {
            "threshold_contract": "domain_held_out_thresholds_v1",
            "required_capability_evidence": "all_declared_capabilities_v1",
        },
        "mutation_policy": {
            "mutation_policy": "shared_framework_mutation_policy_v1",
            "state_change_control": "independent_admission_required_v1",
        },
        "mutation_admission_mode": {
            "admission_mode": "independent_mutation_admission_v1",
            "qualification_constraint": "statically_qualifiable_only_v1",
        },
        "release_completeness": {
            "completeness_contract": "domain_release_completeness_v1",
            "capability_scope": "all_declared_capabilities_v1",
        },
        "release_machine_gates": {
            "machine_gate_contract": "domain_release_machine_gates_v1",
            "gate_evaluation": "all_applicable_gates_v1",
        },
        "compatibility_mapping_set": {
            "mapping_scope": "source_schema_and_projection_kind_v1",
            "mapping_default": "no_legacy_projection_v1",
        },
        "plan_schema": {
            "plan_schema": DOMAIN_PLAN_SCHEMA_VERSION,
            "plan_identity": "canonical_content_hash_v1",
        },
        "assessment_schema": {
            "assessment_schema": DOMAIN_ASSESSMENT_SCHEMA_VERSION,
            "assessment_boundary": "evidence_not_qualification_v1",
        },
    }
    try:
        content = content_by_kind[component_kind]
    except KeyError as error:
        raise DomainPackContractError("incomplete_component_contracts") from error
    return {
        "domain_pack_id": domain_pack_id,
        "component_kind": component_kind,
        "contract_content": content,
    }


def _initial_runtime_contract_reference(
    domain_pack_id: str,
    runtime_id: str,
    *,
    capabilities: tuple[str, ...],
) -> DomainRuntimeContractReference:
    runtime_version = f"{runtime_id}_v1"
    runtime_contract_version = f"{domain_pack_id}_runtime_contract_v1"
    runtime_implementation_hash = canonical_domain_pack_hash(
        {
            "runtime_id": runtime_id,
            "runtime_version": runtime_version,
            "implementation_content": {
                "domain_pack_id": domain_pack_id,
                "fixture_adapter_contract": f"{domain_pack_id}_fixture_adapter_v1",
                "fixture_state_contract": f"{domain_pack_id}_fixture_state_v1",
                "supported_capability_keys": list(capabilities),
                "runtime_scope_contract": "domain_pack_runtime_scope_v1",
            },
        }
    )
    return DomainRuntimeContractReference(
        runtime_id=runtime_id,
        runtime_version=runtime_version,
        runtime_contract_version=runtime_contract_version,
        runtime_implementation_hash=runtime_implementation_hash,
        runtime_contract_hash=canonical_domain_pack_hash(
            {
                "runtime_id": runtime_id,
                "runtime_version": runtime_version,
                "runtime_contract_version": runtime_contract_version,
                "runtime_implementation_hash": runtime_implementation_hash,
                "runtime_contract_content": {
                    "admitted_source_binding": "exact_source_hash_v1",
                    "runtime_identity_check": "exact_runtime_reference_v1",
                },
            }
        ),
    )


def _capability_sort_key(
    reference: DomainCapabilityReference,
) -> tuple[str, str, str]:
    return (
        reference.domain_pack_id,
        reference.capability_key,
        reference.capability_contract_version,
    )


def _require_exact_keys(
    record: Mapping[str, object],
    expected: set[str],
    field_name: str,
) -> None:
    if not isinstance(record, Mapping) or set(record) != expected:
        raise DomainPackContractError(f"{field_name}_keys_invalid")


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DomainPackContractError(f"{field_name}_invalid")
    return value


def _require_record_sequence(
    value: object,
    field_name: str,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DomainPackContractError(f"{field_name}_invalid")
    records = tuple(value)
    if any(not isinstance(item, Mapping) for item in records):
        raise DomainPackContractError(f"{field_name}_invalid")
    return records


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DomainPackContractError(f"{field_name}_invalid")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise DomainPackContractError(f"{field_name}_invalid")
    _validate_safe_record_value(text, path=field_name)
    return text


def _require_hash(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    if not _SHA256_RE.fullmatch(text):
        raise DomainPackContractError(f"{field_name}_invalid")
    return text


def _is_unsafe_record_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in _UNSAFE_KEY_NAMES
        or any(
            unsafe_name in lowered
            for unsafe_name in _UNSAFE_KEY_NAMES - {"token"}
        )
        or any(part in _UNSAFE_KEY_PARTS for part in lowered.split("_"))
    )


def _validate_safe_record_value(
    value: object,
    *,
    path: str,
    depth: int = 0,
    item_count: list[int] | None = None,
) -> None:
    if depth > MAX_DOMAIN_PACK_RECORD_DEPTH:
        raise DomainPackContractError("record_too_deep")
    if item_count is None:
        item_count = [0]
    item_count[0] += 1
    if item_count[0] > MAX_DOMAIN_PACK_RECORD_ITEMS:
        raise DomainPackContractError("record_too_large")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise DomainPackContractError("record_key_invalid")
            if _is_unsafe_record_key(key):
                raise DomainPackContractError("unsafe_record")
            _validate_safe_record_value(
                child,
                path=f"{path}.{key}",
                depth=depth + 1,
                item_count=item_count,
            )
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_safe_record_value(
                child,
                path=f"{path}.{index}",
                depth=depth + 1,
                item_count=item_count,
            )
        return
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_DOMAIN_PACK_TEXT_BYTES:
            raise DomainPackContractError("record_too_large")
        if any(pattern.search(value) for pattern in _UNSAFE_STRING_PATTERNS):
            raise DomainPackContractError("unsafe_record")
        return
    if value is None or isinstance(value, bool) or (
        isinstance(value, int) and not isinstance(value, bool)
    ):
        return
    raise DomainPackContractError("record_value_invalid")


DEFAULT_DOMAIN_PACK_REGISTRY = initial_domain_pack_registry()


def default_domain_pack_registry() -> DomainPackRegistry:
    """Return the immutable initial logical-domain registry."""

    return DEFAULT_DOMAIN_PACK_REGISTRY
