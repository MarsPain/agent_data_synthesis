"""Bounded Contacts and Mobile legacy compatibility.

The compatibility boundary is intentionally separate from the runtime pipeline.
It reads frozen legacy bytes, selects explicit projection mappings, and emits a
canonical plan/projection together with migration lineage.  It never rewrites
the input and it never treats a historical decision as current release
evidence.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from synthesis.contracts import (
    ContractValidationError,
    validate_contacts_environment_input_record,
    validate_mobile_messages_environment_input_record,
    validate_manifest_record,
)
from synthesis.domain_pack import (
    AdmittedSource,
    CompatibilityMapping,
    CompatibilityMappingSet,
    CompatibilityResolutionFailure,
    DomainCapabilityReference,
    DomainPack,
    DomainPackContractError,
    DomainPackDescriptor,
    DomainPlan,
    DomainPlanningIntent,
    DomainRuntimeContractReference,
    LegacyProjection,
    PlanFailure,
    canonical_domain_pack_hash,
    default_domain_pack_registry,
)
from synthesis.domain_sources import resolve_domain_source_importer
from synthesis.mutation_admission_reporting import (
    validate_mutation_admission_report,
)
from synthesis.release_pack import verify_dataset_release_pack
from synthesis.run_profiles import (
    RunProfile,
    RunProfileValidationError,
    load_run_profile,
)


COMPATIBILITY_CORPUS_SCHEMA_VERSION = "compatibility_corpus_manifest_v1"
COMPATIBILITY_CHAIN_SCHEMA_VERSION = "compatibility_chain_v1"
COMPATIBILITY_PROJECTION_SCHEMA_VERSION = "canonical_domain_projection_v1"
COMPATIBILITY_LINEAGE_SCHEMA_VERSION = "domain_migration_lineage_v1"
COMPATIBILITY_STATUS_VALUES = frozenset(
    {"passed", "failed", "insufficient_evidence"}
)
COMPATIBILITY_AXES = (
    "readability",
    "runnability",
    "semantic_equivalence",
    "evidence_admissibility",
)
COMPATIBILITY_HISTORICAL_PROFILE_IDS = frozenset(
    {
        "foundation_fixture_profile",
        "foundation_release_candidate",
        "foundation_scale_probe_25",
        "contacts_coverage_smoke",
        "foundation_profile_local_contacts",
        "foundation_profile_local_contacts_bad_license",
        "foundation_profile_local_contacts_bad_schema",
        "foundation_profile_local_contacts_missing_file",
        "contacts_coverage_pilot_12",
        "contacts_coverage_campaign_30",
        "contacts_coverage_structural_pilot_12",
        "contacts_coverage_structural_campaign_30",
        "contacts_representative_llm_100",
        "contacts_coverage_backfill",
        "contacts_coverage_catalog_probe",
        "contacts_coverage_tracer",
        "mobile_messages_release_candidate",
        "mobile_agent_fixture",
        "profile_local_mobile_messages",
        "profile_local_mobile_messages_bad_schema",
        "mobile_coverage_catalog_probe",
        "mobile_messages_coverage_pilot_12",
        "mobile_messages_coverage_campaign_30",
        "mobile_messages_coverage_structural_pilot_12",
        "mobile_messages_coverage_structural_campaign_30",
        "mobile_messages_representative_llm_100",
    }
)
COMPATIBILITY_SYNTHETIC_PROFILE_IDS = frozenset(
    {
        "contacts_compatibility_bridge_v3",
        "mobile_messages_compatibility_bridge_v3",
    }
)
COMPATIBILITY_CHAIN_IDS = frozenset(
    {
        "contacts_historical_v1",
        "mobile_historical_v1",
        "contacts_mutation_aware_v2",
        "mobile_mutation_aware_v2",
    }
)
_COMPATIBILITY_PROFILE_SCHEMA_BY_ID = {
    **dict.fromkeys(
        (
            "foundation_fixture_profile",
            "foundation_release_candidate",
            "foundation_scale_probe_25",
            "contacts_coverage_smoke",
            "mobile_messages_release_candidate",
            "mobile_agent_fixture",
        ),
        "run_profile_v1",
    ),
    **dict.fromkeys(
        (
            "foundation_profile_local_contacts",
            "foundation_profile_local_contacts_bad_license",
            "foundation_profile_local_contacts_bad_schema",
            "foundation_profile_local_contacts_missing_file",
            "profile_local_mobile_messages",
            "profile_local_mobile_messages_bad_schema",
        ),
        "run_profile_v2",
    ),
    **dict.fromkeys(
        (
            "contacts_coverage_pilot_12",
            "contacts_coverage_campaign_30",
            "contacts_coverage_structural_pilot_12",
            "contacts_coverage_structural_campaign_30",
            "contacts_representative_llm_100",
            "contacts_coverage_backfill",
            "contacts_coverage_catalog_probe",
            "contacts_coverage_tracer",
            "mobile_coverage_catalog_probe",
            "mobile_messages_coverage_pilot_12",
            "mobile_messages_coverage_campaign_30",
            "mobile_messages_coverage_structural_pilot_12",
            "mobile_messages_coverage_structural_campaign_30",
            "mobile_messages_representative_llm_100",
        ),
        "run_profile_v4",
    ),
    **dict.fromkeys(COMPATIBILITY_SYNTHETIC_PROFILE_IDS, "run_profile_v3"),
}
_COMPATIBILITY_PROFILE_ROLE_BY_ID = {
    **dict.fromkeys(COMPATIBILITY_HISTORICAL_PROFILE_IDS, "historical_input"),
    **dict.fromkeys(
        COMPATIBILITY_SYNTHETIC_PROFILE_IDS,
        "synthetic_compatibility_evidence",
    ),
}
_COMPATIBILITY_CHAIN_EXPECTATIONS = {
    "contacts_historical_v1": (
        "contacts",
        "foundation_release_candidate",
        "run_profile_v1",
    ),
    "mobile_historical_v1": (
        "mobile_messages",
        "mobile_messages_release_candidate",
        "run_profile_v1",
    ),
    "contacts_mutation_aware_v2": (
        "contacts",
        "contacts_mutation_compatibility_v2",
        "run_profile_v4",
    ),
    "mobile_mutation_aware_v2": (
        "mobile_messages",
        "mobile_mutation_compatibility_v2",
        "run_profile_v4",
    ),
}

# These are deliberately closed.  A new failure vocabulary is a compatibility
# contract change, not an opportunity to leak parser or filesystem exceptions.
COMPATIBILITY_REASON_CODES = frozenset(
    {
        "legacy_record_readable",
        "legacy_profile_json_invalid",
        "legacy_profile_schema_invalid",
        "invalid_source_license",
        "source_missing",
        "source_exceeds_max_bytes",
        "unsafe_source_path",
        "source_schema_invalid",
        "source_kind_unsupported",
        "supported_profile_compiled",
        "unsupported_schema_version",
        "unsupported_domain",
        "cross_pack_reference",
        "unknown_task_label",
        "ambiguous_task_label",
        "unsupported_network_work",
        "diagnostic_label_only",
        "missing_task_projection",
        "compatibility_mapping_selected",
        "invalid_compatibility_lookup",
        "unknown_compatibility_mapping",
        "ambiguous_compatibility_mapping",
        "cross_pack_mapping_target",
        "compatibility_mapping_target_mismatch",
        "canonical_projection_matches_reviewed_oracle",
        "canonical_projection_missing",
        "historical_only",
        "synthetic_compatibility_evidence",
        "current_pack_reference_missing",
        "dependency_missing",
        "dependency_tampered",
        "dependency_schema_invalid",
        "historical_decision_reproduced",
        "historical_decision_not_reproduced",
        "unmanifested_file",
        "manifest_invalid",
        "profile_row_missing",
        "expected_projection_mismatch",
        "expected_assessment_mismatch",
        "unknown_semantic_label",
    }
)
_COMPATIBILITY_SAFE_DETAIL_VALUES = frozenset(
    {
        "ContractValidationError",
        "FileNotFoundError",
        "IsADirectoryError",
        "JSONDecodeError",
        "KeyError",
        "NotADirectoryError",
        "OSError",
        "PermissionError",
        "RunProfileValidationError",
        "UnicodeDecodeError",
        "ValueError",
    }
)

DOMAIN_BY_LEGACY_VALUE = {
    "contacts": "contacts",
    "contacts_fixture": "contacts",
    "mobile_messages": "mobile_messages",
    "mobile_messages_fixture": "mobile_messages",
}

_CONTACT_TASK_PROJECTIONS = {
    "single_tool_lookup": ("contact_lookup", ("contact_lookup",)),
    "lookup_contact_email": ("contact_lookup", ("contact_lookup",)),
    "contact_lookup": ("contact_lookup", ("contact_lookup",)),
    "contact_followup": (
        "contact_followup",
        ("contact_lookup", "followup_recording"),
    ),
    "branch_fallback": (
        "contact_lookup",
        ("contact_lookup", "contact_lookup_recovery"),
    ),
    "contact_branch_fallback": (
        "contact_lookup",
        ("contact_lookup", "contact_lookup_recovery"),
    ),
}
_CONTACT_HELD_OUT_PROJECTIONS = {
    "contact_lookup": "contact_lookup",
    "state_change": "followup_recording",
    "branching": "contact_lookup_recovery",
    "missing_contact": "missing_contact_safe_failure",
}
_MOBILE_TASK_PROJECTIONS = {
    "mobile_message_lookup": (
        "mobile_message_search",
        ("message_search",),
    ),
    "mobile_message_search": (
        "mobile_message_search",
        ("message_search",),
    ),
    "mobile_message_to_reminder": (
        "mobile_reminder_creation",
        ("message_search", "reminder_creation"),
    ),
    "mobile_reminder_creation": (
        "mobile_reminder_creation",
        ("message_search", "reminder_creation"),
    ),
    "mobile_draft_reply": (
        "mobile_draft_reply",
        ("message_search", "draft_reply"),
    ),
    "mobile_branch_fallback": (
        "mobile_message_search",
        ("message_search", "message_search_recovery"),
    ),
}
_MOBILE_HELD_OUT_PROJECTIONS = {
    "mobile_message_lookup": "message_search",
    "mobile_message_to_reminder": "reminder_creation",
    "mobile_draft_reply": "draft_reply",
    "mobile_branching": "message_search_recovery",
    "mobile_missing_message": "missing_message_safe_failure",
}

_CONTACT_DIAGNOSTIC_LABELS = {"verification_failure_fixture"}
_MOBILE_DIAGNOSTIC_LABELS: set[str] = set()
_UNSUPPORTED_NETWORK_LABELS = {
    "unsupported_network_research",
    "network_contact_research",
}


def _plain_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _content_hash(content: bytes) -> str:
    return "sha256:" + _plain_sha256(content)


def _hash_record(path: Path, *, relative_path: str | None = None) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": relative_path or path.name,
        "sha256": _content_hash(content),
        "byte_count": len(content),
    }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is invalid")
    return value


def _require_hash(value: object, field_name: str) -> str:
    value = _require_text(value, field_name)
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{field_name} is invalid")
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise ValueError(f"{field_name} is invalid")
    return value


def _safe_relative_path(value: object, field_name: str) -> str:
    path = _require_text(value, field_name).replace("\\", "/")
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts or path.startswith("~"):
        raise ValueError(f"{field_name} is unsafe")
    if not path or path.endswith("/"):
        raise ValueError(f"{field_name} is invalid")
    return path


@dataclass(frozen=True)
class CompatibilityAxisResult:
    status: str
    reason_code: str

    def __post_init__(self) -> None:
        if self.status not in COMPATIBILITY_STATUS_VALUES:
            raise ValueError("compatibility axis status is unsupported")
        if self.reason_code not in COMPATIBILITY_REASON_CODES:
            raise ValueError("compatibility axis reason code is unsupported")

    def to_record(self) -> dict[str, str]:
        return {"status": self.status, "reason_code": self.reason_code}

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "CompatibilityAxisResult":
        if set(record) != {"status", "reason_code"}:
            raise ValueError("compatibility axis keys are invalid")
        return cls(
            status=_require_text(record["status"], "status"),
            reason_code=_require_text(record["reason_code"], "reason_code"),
        )


@dataclass(frozen=True)
class CompatibilityAssessment:
    readability: CompatibilityAxisResult
    runnability: CompatibilityAxisResult
    semantic_equivalence: CompatibilityAxisResult
    evidence_admissibility: CompatibilityAxisResult

    def __post_init__(self) -> None:
        for axis in COMPATIBILITY_AXES:
            if not isinstance(getattr(self, axis), CompatibilityAxisResult):
                raise ValueError(f"{axis} is invalid")

    @property
    def status(self) -> str:
        statuses = {getattr(self, axis).status for axis in COMPATIBILITY_AXES}
        if "failed" in statuses:
            return "failed"
        if "insufficient_evidence" in statuses:
            return "insufficient_evidence"
        return "passed"

    @property
    def axes(self) -> Mapping[str, CompatibilityAxisResult]:
        return {axis: getattr(self, axis) for axis in COMPATIBILITY_AXES}

    @property
    def reason_codes(self) -> Mapping[str, str]:
        return {
            axis: getattr(self, axis).reason_code for axis in COMPATIBILITY_AXES
        }

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": "compatibility_assessment_v1",
            "status": self.status,
            "axes": {
                axis: getattr(self, axis).to_record() for axis in COMPATIBILITY_AXES
            },
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "CompatibilityAssessment":
        if set(record) != {"schema_version", "status", "axes"}:
            raise ValueError("compatibility assessment keys are invalid")
        if record.get("schema_version") != "compatibility_assessment_v1":
            raise ValueError("compatibility assessment schema is unsupported")
        axes = record.get("axes")
        if not isinstance(axes, Mapping) or set(axes) != set(COMPATIBILITY_AXES):
            raise ValueError("compatibility assessment axes are invalid")
        result = cls(
            **{
                axis: CompatibilityAxisResult.from_record(
                    _mapping(axes[axis], f"axes.{axis}")
                )
                for axis in COMPATIBILITY_AXES
            }
        )
        if record.get("status") != result.status:
            raise ValueError("compatibility assessment status is inconsistent")
        return result


@dataclass(frozen=True)
class MigrationLineage:
    source_path: str
    source_profile_id: str
    source_schema_version: str
    source_profile_hash: str
    source_profile_byte_count: int
    mapping_id: str
    mapping_version: str
    mapping_hash: str
    mapping_set_id: str
    mapping_set_version: str
    mapping_set_hash: str
    derivation_reason: str
    schema_version: str = COMPATIBILITY_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COMPATIBILITY_LINEAGE_SCHEMA_VERSION:
            raise ValueError("migration lineage schema is unsupported")
        _safe_relative_path(self.source_path, "source_path")
        for field_name in (
            "source_profile_id",
            "source_schema_version",
            "mapping_id",
            "mapping_version",
            "mapping_set_id",
            "mapping_set_version",
            "derivation_reason",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "source_profile_hash",
            "mapping_hash",
            "mapping_set_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        if (
            not isinstance(self.source_profile_byte_count, int)
            or isinstance(self.source_profile_byte_count, bool)
            or self.source_profile_byte_count <= 0
        ):
            raise ValueError("source_profile_byte_count is invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_profile_id": self.source_profile_id,
            "source_schema_version": self.source_schema_version,
            "source_profile_hash": self.source_profile_hash,
            "source_profile_byte_count": self.source_profile_byte_count,
            "selected_mapping": {
                "mapping_id": self.mapping_id,
                "mapping_version": self.mapping_version,
                "mapping_hash": self.mapping_hash,
            },
            "mapping_set": {
                "mapping_set_id": self.mapping_set_id,
                "mapping_set_version": self.mapping_set_version,
                "mapping_set_hash": self.mapping_set_hash,
            },
            "derivation_reason": self.derivation_reason,
        }


@dataclass(frozen=True)
class LegacyProfile:
    path: Path
    relative_path: str
    raw_bytes: bytes
    record: Mapping[str, object]
    profile: RunProfile
    source_content_hash: str | None = None
    source_byte_count: int | None = None

    @property
    def profile_hash(self) -> str:
        return _content_hash(self.raw_bytes)

    @property
    def byte_count(self) -> int:
        return len(self.raw_bytes)

    @property
    def profile_id(self) -> str:
        return self.profile.profile_id

    @property
    def schema_version(self) -> str:
        return self.profile.schema_version


@dataclass(frozen=True)
class CompatibilityFailure:
    reason_code: str
    assessment: CompatibilityAssessment
    detail: str | None = None
    schema_version: str = "compatibility_failure_v1"
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.reason_code not in COMPATIBILITY_REASON_CODES:
            raise ValueError("compatibility failure reason is unsupported")
        if self.status != "rejected":
            raise ValueError("compatibility failure status is invalid")

    def to_record(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
            "assessment": self.assessment.to_record(),
        }
        if self.detail in _COMPATIBILITY_SAFE_DETAIL_VALUES:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True)
class CompatibilityCompilation:
    legacy_profile: LegacyProfile
    plan: DomainPlan
    canonical_projection: Mapping[str, object]
    migration_lineage: MigrationLineage
    assessment: CompatibilityAssessment
    selected_mapping: CompatibilityMapping

    @property
    def status(self) -> str:
        return self.assessment.status

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": "compatibility_compilation_v1",
            "status": self.status,
            "plan": self.plan.to_record(),
            "canonical_projection": dict(self.canonical_projection),
            "migration_lineage": self.migration_lineage.to_record(),
            "assessment": self.assessment.to_record(),
        }


@dataclass(frozen=True)
class CorpusVerificationResult:
    status: str
    reason_codes: tuple[str, ...]
    profile_results: Mapping[str, object]
    chain_results: Mapping[str, object]
    schema_version: str = "compatibility_corpus_verification_v1"

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "profiles": dict(self.profile_results),
            "chains": dict(self.chain_results),
        }


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} is invalid")
    return value


def _json_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("json_invalid") from exc
    return _mapping(value, path.name)


def _assessment(
    *,
    readability: tuple[str, str],
    runnability: tuple[str, str],
    semantic_equivalence: tuple[str, str],
    evidence_admissibility: tuple[str, str],
) -> CompatibilityAssessment:
    return CompatibilityAssessment(
        readability=CompatibilityAxisResult(*readability),
        runnability=CompatibilityAxisResult(*runnability),
        semantic_equivalence=CompatibilityAxisResult(*semantic_equivalence),
        evidence_admissibility=CompatibilityAxisResult(*evidence_admissibility),
    )


def _failure(
    reason_code: str,
    *,
    readability: tuple[str, str] = ("passed", "legacy_record_readable"),
    runnability: tuple[str, str] = ("failed", "unknown_task_label"),
    semantic_equivalence: tuple[str, str] = (
        "insufficient_evidence",
        "canonical_projection_missing",
    ),
    evidence_admissibility: tuple[str, str] = (
        "insufficient_evidence",
        "current_pack_reference_missing",
    ),
    detail: str | None = None,
) -> CompatibilityFailure:
    return CompatibilityFailure(
        reason_code=reason_code,
        assessment=_assessment(
            readability=readability,
            runnability=runnability,
            semantic_equivalence=semantic_equivalence,
            evidence_admissibility=evidence_admissibility,
        ),
        detail=(detail if detail in _COMPATIBILITY_SAFE_DETAIL_VALUES else None),
    )


def _normalize_domain(domain: str) -> str | None:
    return DOMAIN_BY_LEGACY_VALUE.get(domain)


def _profile_relative_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.name if path.is_absolute() else path.as_posix()


def read_legacy_profile(
    path: Path,
    *,
    corpus_root: Path | None = None,
) -> LegacyProfile | CompatibilityFailure:
    """Read one frozen profile without changing its bytes."""

    if corpus_root is not None:
        try:
            path.resolve(strict=True).relative_to(corpus_root.resolve(strict=True))
        except ValueError:
            return _failure(
                "unsafe_source_path",
                readability=("failed", "unsafe_source_path"),
                runnability=("failed", "unsafe_source_path"),
            )
        except OSError as exc:
            return _failure(
                "dependency_missing",
                readability=("failed", "dependency_missing"),
                runnability=("failed", "source_missing"),
                detail=type(exc).__name__,
            )
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return _failure(
            "dependency_missing",
            readability=("failed", "dependency_missing"),
            runnability=("failed", "source_missing"),
            detail=type(exc).__name__,
        )
    try:
        record = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _failure(
            "legacy_profile_json_invalid",
            readability=("failed", "legacy_profile_json_invalid"),
            runnability=("insufficient_evidence", "legacy_profile_schema_invalid"),
            detail=type(exc).__name__,
        )
    if not isinstance(record, Mapping):
        return _failure(
            "legacy_profile_schema_invalid",
            readability=("failed", "legacy_profile_schema_invalid"),
            runnability=("insufficient_evidence", "legacy_profile_schema_invalid"),
        )
    try:
        profile = load_run_profile(path)
    except RunProfileValidationError as exc:
        message = str(exc)
        reason = (
            "invalid_source_license"
            if "license_label" in message
            else "legacy_profile_schema_invalid"
        )
        return _failure(
            reason,
            readability=("failed", reason),
            runnability=("insufficient_evidence", reason),
            detail=message,
        )
    return LegacyProfile(
        path=path,
        relative_path=_profile_relative_path(path, corpus_root),
        raw_bytes=raw_bytes,
        record=record,
        profile=profile,
    )


def _read_source_bytes(
    profile: LegacyProfile,
) -> bytes | CompatibilityFailure | None:
    source = profile.profile.source
    if source is None:
        return None
    source_path = profile.path.parent / source.relative_path
    try:
        source_root = profile.path.parent.resolve(strict=True)
        resolved_source_path = source_path.resolve(strict=True)
        resolved_source_path.relative_to(source_root)
        source_bytes = resolved_source_path.read_bytes()
    except ValueError:
        return _failure(
            "unsafe_source_path",
            runnability=("failed", "unsafe_source_path"),
        )
    except OSError as exc:
        return _failure(
            "source_missing",
            runnability=("failed", "source_missing"),
            detail=type(exc).__name__,
        )
    if len(source_bytes) > source.max_bytes:
        return _failure(
            "source_exceeds_max_bytes",
            runnability=("failed", "source_exceeds_max_bytes"),
        )
    return source_bytes


def _source_failure(
    profile: LegacyProfile,
    source_bytes: bytes | None,
) -> CompatibilityFailure | None:
    source = profile.profile.source
    if source is None:
        return None
    if source_bytes is None:
        return _failure(
            "source_missing",
            runnability=("failed", "source_missing"),
        )
    try:
        try:
            importer = resolve_domain_source_importer(
                profile.profile.seed.domain,
                source.kind,
            )
        except ValueError as exc:
            return _failure(
                "source_kind_unsupported",
                runnability=("failed", "source_kind_unsupported"),
                detail=type(exc).__name__,
            )
        environment_input = importer.build_environment_input(
            source_bytes,
            source_bundle_id="compatibility_source_bundle",
            source_policy_hash=canonical_domain_pack_hash(
                {
                    "source_id": source.source_id,
                    "license_label": source.license_label,
                    "max_bytes": source.max_bytes,
                }
            ),
        )
        export = getattr(environment_input, "export", None)
        if not callable(export):
            return _failure(
                "source_schema_invalid",
                runnability=("failed", "source_schema_invalid"),
            )
        exported = export()
        if source.kind == "local_contacts_json":
            validate_contacts_environment_input_record(exported)
        else:
            validate_mobile_messages_environment_input_record(exported)
        if isinstance(exported, Mapping):
            if not exported.get("validation_errors"):
                return None
    except (ValueError, ContractValidationError, KeyError) as exc:
        return _failure(
            "source_schema_invalid",
            runnability=("failed", "source_schema_invalid"),
            detail=type(exc).__name__,
        )
    return _failure(
        "source_schema_invalid",
        runnability=("failed", "source_schema_invalid"),
    )


def _source_facts(
    profile: LegacyProfile,
    source_bytes: bytes | None,
) -> tuple[str, str, int]:
    source = profile.profile.source
    if source is None:
        return (
            "legacy_profile_" + _plain_sha256(profile.raw_bytes)[:24],
            profile.profile.schema_version,
            len(profile.raw_bytes),
        )
    if source_bytes is None:
        raise ValueError("source bytes are missing")
    return (
        source.source_id,
        "contacts_environment_input_v1"
        if source.kind == "local_contacts_json"
        else "mobile_messages_environment_input_v1",
        len(source_bytes),
    )


def _mapping_set(
    descriptor: DomainPackDescriptor,
) -> CompatibilityMappingSet:
    domain = descriptor.domain_pack_id
    runtime = descriptor.runtime_contracts[0]
    capability_by_key = {
        item.capability_key: item for item in descriptor.capability_references
    }
    task_component = next(
        item
        for item in descriptor.component_contracts
        if item.component_kind == "task_taxonomy"
    )
    values: list[CompatibilityMapping] = []
    semantic_values = (
        ("contacts", "contacts_fixture")
        if domain == "contacts"
        else ("mobile_messages", "mobile_messages_fixture")
    )
    for schema_version in ("run_profile_v1", "run_profile_v2", "run_profile_v3", "run_profile_v4"):
        for legacy_value in semantic_values:
            values.append(
                CompatibilityMapping.create(
                    source_schema_version=schema_version,
                    projection_kind="semantic_domain",
                    legacy_value=legacy_value,
                    mapping_version=f"{domain}_semantic_domain_mapping_v1",
                    target=descriptor.reference(),
                )
            )
        values.append(
            CompatibilityMapping.create(
                source_schema_version=schema_version,
                projection_kind="runtime",
                legacy_value=runtime.runtime_id,
                mapping_version=f"{domain}_runtime_mapping_v1",
                target=runtime,
            )
        )
    task_projections = (
        _CONTACT_TASK_PROJECTIONS if domain == "contacts" else _MOBILE_TASK_PROJECTIONS
    )
    held_out_projections = (
        _CONTACT_HELD_OUT_PROJECTIONS
        if domain == "contacts"
        else _MOBILE_HELD_OUT_PROJECTIONS
    )
    for schema_version in ("run_profile_v1", "run_profile_v2", "run_profile_v3", "run_profile_v4"):
        for legacy_value, capability_key in held_out_projections.items():
            values.append(
                CompatibilityMapping.create(
                    source_schema_version=schema_version,
                    projection_kind="held_out_capability",
                    legacy_value=legacy_value,
                    mapping_version=f"{domain}_held_out_mapping_v1",
                    target=capability_by_key[capability_key],
                )
            )
    for schema_version in ("run_profile_v1", "run_profile_v2", "run_profile_v3", "run_profile_v4"):
        for legacy_value, (canonical_task, _capability_keys) in task_projections.items():
            _ = canonical_task
            values.append(
                CompatibilityMapping.create(
                    source_schema_version=schema_version,
                    projection_kind="task_type",
                    legacy_value=legacy_value,
                    mapping_version=f"{domain}_task_mapping_v1",
                    target=task_component,
                )
            )
        for capability_key, capability in capability_by_key.items():
            values.append(
                CompatibilityMapping.create(
                    source_schema_version=schema_version,
                    projection_kind="capability",
                    legacy_value=capability_key,
                    mapping_version=f"{domain}_capability_mapping_v1",
                    target=capability,
                )
            )
    return CompatibilityMappingSet(
        mapping_set_id=f"{domain}_compatibility_mapping_set_v1",
        mapping_set_version=f"{domain}_compatibility_mapping_set_v1",
        mappings=tuple(values),
    )


def compatibility_mapping_set(domain_pack_id: str) -> CompatibilityMappingSet:
    """Return the explicit, projection-scoped mapping set for one domain."""

    descriptor = default_domain_pack_registry().descriptor_for(domain_pack_id)
    if domain_pack_id not in {"contacts", "mobile_messages"}:
        raise ValueError("compatibility mappings are scoped to Contacts and Mobile")
    return _mapping_set(descriptor)


def _mapping_for_profile(
    profile: LegacyProfile,
    descriptor: DomainPackDescriptor,
    mapping_set: CompatibilityMappingSet,
) -> CompatibilityMapping | CompatibilityFailure:
    legacy_domain = str(profile.profile.seed.domain)
    result = mapping_set.resolve(
        source_schema_version=profile.profile.schema_version,
        projection_kind="semantic_domain",
        legacy_value=legacy_domain,
    )
    if isinstance(result, CompatibilityResolutionFailure):
        return _failure(
            result.reason_code,
            runnability=("failed", result.reason_code),
        )
    if result.target != descriptor.reference():
        return _failure(
            "cross_pack_mapping_target",
            runnability=("failed", "cross_pack_mapping_target"),
        )
    runtime_result = mapping_set.resolve(
        source_schema_version=profile.profile.schema_version,
        projection_kind="runtime",
        legacy_value=descriptor.runtime_contracts[0].runtime_id,
    )
    if isinstance(runtime_result, CompatibilityResolutionFailure):
        return _failure(
            runtime_result.reason_code,
            runnability=("failed", runtime_result.reason_code),
        )
    if runtime_result.target != descriptor.runtime_contracts[0]:
        return _failure(
            "cross_pack_mapping_target",
            runnability=("failed", "cross_pack_mapping_target"),
        )
    return result


def _canonical_task_data(
    profile: LegacyProfile,
    descriptor: DomainPackDescriptor,
    mapping_set: CompatibilityMappingSet,
) -> tuple[tuple[str, ...], tuple[DomainCapabilityReference, ...], tuple[str, ...]] | CompatibilityFailure:
    domain = descriptor.domain_pack_id
    task_projections = (
        _CONTACT_TASK_PROJECTIONS if domain == "contacts" else _MOBILE_TASK_PROJECTIONS
    )
    diagnostic_labels = (
        _CONTACT_DIAGNOSTIC_LABELS
        if domain == "contacts"
        else _MOBILE_DIAGNOSTIC_LABELS
    )
    canonical_tasks: list[str] = []
    capability_keys: list[str] = []
    diagnostics: list[str] = []
    for label in profile.profile.seed.task_taxonomy:
        if label in _UNSUPPORTED_NETWORK_LABELS:
            return _failure(
                "unsupported_network_work",
                runnability=("failed", "unsupported_network_work"),
            )
        if label in diagnostic_labels:
            diagnostics.append(label)
            continue
        projection = task_projections.get(label)
        if projection is None:
            return _failure(
                "unknown_task_label",
                runnability=("failed", "unknown_task_label"),
                detail=label,
            )
        task_type, projected_capabilities = projection
        if task_type not in canonical_tasks:
            canonical_tasks.append(task_type)
        recovery_task_type = {
            "branch_fallback": "contact_lookup_recovery",
            "contact_branch_fallback": "contact_lookup_recovery",
            "mobile_branch_fallback": "mobile_message_search_recovery",
        }.get(label)
        if recovery_task_type is not None and recovery_task_type not in canonical_tasks:
            canonical_tasks.append(recovery_task_type)
        for capability_key in projected_capabilities:
            if capability_key not in capability_keys:
                capability_keys.append(capability_key)
    if not canonical_tasks:
        return _failure(
            "missing_task_projection",
            runnability=("failed", "missing_task_projection"),
        )
    capabilities_by_key = {
        item.capability_key: item for item in descriptor.capability_references
    }
    try:
        capabilities = tuple(capabilities_by_key[key] for key in capability_keys)
    except KeyError as exc:
        return _failure(
            "unknown_task_label",
            runnability=("failed", "unknown_task_label"),
            detail=str(exc),
        )
    task_component = next(
        item
        for item in descriptor.component_contracts
        if item.component_kind == "task_taxonomy"
    )
    for label in profile.profile.seed.task_taxonomy:
        if label in diagnostic_labels or label in _UNSUPPORTED_NETWORK_LABELS:
            continue
        task_mapping = mapping_set.resolve(
            source_schema_version=profile.profile.schema_version,
            projection_kind="task_type",
            legacy_value=label,
        )
        if isinstance(task_mapping, CompatibilityResolutionFailure):
            return _failure(
                task_mapping.reason_code,
                runnability=("failed", task_mapping.reason_code),
            )
        if task_mapping.target != task_component:
            return _failure(
                "cross_pack_mapping_target",
                runnability=("failed", "cross_pack_mapping_target"),
            )
    for capability_key, capability in zip(capability_keys, capabilities):
        capability_mapping = mapping_set.resolve(
            source_schema_version=profile.profile.schema_version,
            projection_kind="capability",
            legacy_value=capability_key,
        )
        if isinstance(capability_mapping, CompatibilityResolutionFailure):
            return _failure(
                capability_mapping.reason_code,
                runnability=("failed", capability_mapping.reason_code),
            )
        if capability_mapping.target != capability:
            return _failure(
                "cross_pack_mapping_target",
                runnability=("failed", "cross_pack_mapping_target"),
            )
    return tuple(canonical_tasks), capabilities, tuple(diagnostics)


def _admitted_source(
    profile: LegacyProfile,
    descriptor: DomainPackDescriptor,
    source_bytes: bytes | None,
) -> AdmittedSource:
    source_id, source_schema_version, source_byte_count = _source_facts(
        profile,
        source_bytes,
    )
    source_content_hash = (
        _content_hash(source_bytes)
        if source_bytes is not None
        else profile.profile_hash
    )
    return AdmittedSource(
        source_id=source_id,
        source_schema_version=source_schema_version,
        source_content_hash=source_content_hash,
        admission_policy_id=f"{descriptor.domain_pack_id}_compatibility_policy_v1",
        admission_policy_hash=canonical_domain_pack_hash(
            {
                "domain_pack_id": descriptor.domain_pack_id,
                "source_kind": (
                    profile.profile.source.kind
                    if profile.profile.source is not None
                    else "legacy_profile"
                ),
                "source_byte_count": source_byte_count,
            }
        ),
    )


def _canonical_projection(
    *,
    profile: LegacyProfile,
    descriptor: DomainPackDescriptor,
    plan: DomainPlan,
    lineage: MigrationLineage,
    diagnostics: tuple[str, ...],
) -> dict[str, object]:
    profile_metadata: dict[str, object] = {
        "schema_version": profile.profile.schema_version,
        "profile_purpose": profile.profile.profile_purpose,
        "generation_mode": profile.profile.generation.mode,
        "features": profile.profile.features.canonical(),
    }
    if profile.profile.coverage_profile is not None:
        profile_metadata["coverage_profile"] = profile.profile.coverage_profile.canonical()
    if profile.profile.schema_version == "run_profile_v4":
        profile_metadata["mutation_admission"] = profile.profile.mutation_admission.canonical()
    source = profile.profile.source
    source_record: dict[str, object] = {
        "source_id": plan.admitted_source.source_id,
        "source_schema_version": plan.admitted_source.source_schema_version,
        "source_content_hash": plan.admitted_source.source_content_hash,
        "admission_policy_id": plan.admitted_source.admission_policy_id,
        "admission_policy_hash": plan.admitted_source.admission_policy_hash,
    }
    if source is not None:
        source_record["kind"] = source.kind
        source_record["license_label"] = source.license_label
    capabilities = [item.to_record() for item in plan.capability_references]
    held_out = [item.to_record() for item in plan.held_out_capability_references]
    task_types = [item.task_type_key for item in plan.task_capability_projections]
    return {
        "schema_version": COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "domain_pack_reference": descriptor.reference().to_record(),
        "semantic": {
            "domain_pack_reference": descriptor.reference().to_record(),
            "task_type_references": [
                {"task_type_key": task_type} for task_type in task_types
            ],
            "capability_references": capabilities,
            "held_out_capability_references": held_out,
            "component_contracts": [item.to_record() for item in plan.component_contracts],
        },
        "runtime": {
            "runtime_id": plan.runtime_contract.runtime_id,
            "runtime_version": plan.runtime_contract.runtime_version,
            "runtime_contract_version": plan.runtime_contract.runtime_contract_version,
            "runtime_contract_hash": plan.runtime_contract.runtime_contract_hash,
        },
        "profile": profile_metadata,
        "source": source_record,
        "diagnostic_labels": list(diagnostics),
        "migration_lineage": lineage.to_record(),
    }


def compile_legacy_profile(
    path: Path,
    *,
    corpus_root: Path | None = None,
    mapping_set: CompatibilityMappingSet | None = None,
) -> CompatibilityCompilation | CompatibilityFailure:
    """Compile one supported legacy profile into canonical Domain semantics."""

    loaded = read_legacy_profile(path, corpus_root=corpus_root)
    if isinstance(loaded, CompatibilityFailure):
        return loaded
    profile = loaded
    domain = _normalize_domain(profile.profile.seed.domain)
    if domain is None:
        reason = (
            "cross_pack_reference"
            if profile.profile.seed.domain == "workspace_tasks_fixture"
            else "unsupported_domain"
        )
        return _failure(
            reason,
            runnability=("failed", reason),
        )
    source_bytes = _read_source_bytes(profile)
    if isinstance(source_bytes, CompatibilityFailure):
        return source_bytes
    source_failure = _source_failure(profile, source_bytes)
    if source_failure is not None:
        return source_failure
    descriptor = default_domain_pack_registry().descriptor_for(domain)
    selected_mapping_set = mapping_set or compatibility_mapping_set(domain)
    selected_mapping = _mapping_for_profile(
        profile,
        descriptor,
        selected_mapping_set,
    )
    if isinstance(selected_mapping, CompatibilityFailure):
        return selected_mapping
    task_data = _canonical_task_data(profile, descriptor, selected_mapping_set)
    if isinstance(task_data, CompatibilityFailure):
        return task_data
    task_types, capabilities, diagnostics = task_data
    try:
        admitted_source = _admitted_source(profile, descriptor, source_bytes)
        intent = DomainPlanningIntent(
            domain_pack_reference=descriptor.reference(),
            task_type_keys=task_types,
            capability_references=capabilities,
            runtime_contract=descriptor.runtime_contracts[0],
            legacy_projection=LegacyProjection(
                source_schema_version=profile.profile.schema_version,
                projection_kind="semantic_domain",
                legacy_value=str(profile.profile.seed.domain),
            ),
        )
        planned = DomainPack(descriptor, selected_mapping_set).plan(
            intent,
            admitted_source,
        )
        if isinstance(planned, PlanFailure):
            reason = planned.reason_code
            if reason not in COMPATIBILITY_REASON_CODES:
                reason = "unsupported_domain"
            return _failure(reason, runnability=("failed", reason))
        plan = planned
    except (DomainPackContractError, ValueError) as exc:
        reason = getattr(exc, "reason_code", "unsupported_domain")
        if reason not in COMPATIBILITY_REASON_CODES:
            reason = "unsupported_domain"
        return _failure(reason, runnability=("failed", reason), detail=str(exc))

    lineage = MigrationLineage(
        source_path=profile.relative_path,
        source_profile_id=profile.profile.profile_id,
        source_schema_version=profile.profile.schema_version,
        source_profile_hash=profile.profile_hash,
        source_profile_byte_count=profile.byte_count,
        mapping_id=selected_mapping.mapping_id,
        mapping_version=selected_mapping.mapping_version,
        mapping_hash=selected_mapping.mapping_hash,
        mapping_set_id=selected_mapping_set.mapping_set_id,
        mapping_set_version=selected_mapping_set.mapping_set_version,
        mapping_set_hash=selected_mapping_set.mapping_set_hash(),
        derivation_reason="explicit_projection_scoped_legacy_mapping",
    )
    assessment = _assessment(
        readability=("passed", "legacy_record_readable"),
        runnability=("passed", "supported_profile_compiled"),
        semantic_equivalence=(
            "passed",
            "canonical_projection_matches_reviewed_oracle",
        ),
        evidence_admissibility=(
            "insufficient_evidence",
            (
                "synthetic_compatibility_evidence"
                if profile.profile.profile_id.endswith("_compatibility_bridge_v3")
                else "historical_only"
            ),
        ),
    )
    projection = _canonical_projection(
        profile=profile,
        descriptor=descriptor,
        plan=plan,
        lineage=lineage,
        diagnostics=diagnostics,
    )
    return CompatibilityCompilation(
        legacy_profile=profile,
        plan=plan,
        canonical_projection=projection,
        migration_lineage=lineage,
        assessment=assessment,
        selected_mapping=selected_mapping,
    )


def _verify_file_manifest(root: Path, manifest: Mapping[str, object]) -> list[str]:
    raw_files = manifest.get("files")
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes, bytearray)):
        return ["manifest_invalid"]
    expected: dict[str, Mapping[str, object]] = {}
    reasons: list[str] = []
    for index, raw_file in enumerate(raw_files):
        try:
            record = _mapping(raw_file, f"files.{index}")
            path = _safe_relative_path(record.get("path"), f"files.{index}.path")
            if path in expected:
                reasons.append("manifest_invalid")
            expected[path] = record
            _require_hash(record.get("sha256"), f"files.{index}.sha256")
            byte_count = record.get("byte_count")
            if (
                not isinstance(byte_count, int)
                or isinstance(byte_count, bool)
                or byte_count < 0
            ):
                raise ValueError("byte_count")
        except ValueError:
            reasons.append("manifest_invalid")
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "corpus_manifest.json"
    }
    if actual_paths != set(expected):
        reasons.append("unmanifested_file")
    for relative_path, record in expected.items():
        dependency_path = root / relative_path
        if not dependency_path.exists():
            reasons.append("dependency_missing")
            continue
        if dependency_path.is_symlink():
            reasons.append("dependency_tampered")
            continue
        actual = _hash_record(dependency_path, relative_path=relative_path)
        if (
            actual["sha256"] != record.get("sha256")
            or actual["byte_count"] != record.get("byte_count")
        ):
            reasons.append("dependency_tampered")
    return list(dict.fromkeys(reasons))


def _expected_axis_record(row: Mapping[str, object]) -> CompatibilityAssessment:
    expected = _mapping(row.get("expected"), "expected")
    if set(expected) != set(COMPATIBILITY_AXES):
        raise ValueError("expected axes are invalid")
    return CompatibilityAssessment(
        **{
            axis: CompatibilityAxisResult.from_record(
                _mapping(expected[axis], f"expected.{axis}")
            )
            for axis in COMPATIBILITY_AXES
        }
    )


def _verify_chain(root: Path, chain: Mapping[str, object]) -> dict[str, object]:
    chain_id = _require_text(chain.get("chain_id"), "chain_id")
    expected_chain = _COMPATIBILITY_CHAIN_EXPECTATIONS.get(chain_id)
    expected_domain_pack_id = expected_chain[0] if expected_chain is not None else None
    expected_historical_profile_id = (
        expected_chain[1] if expected_chain is not None else None
    )
    expected_historical_profile_schema = (
        expected_chain[2] if expected_chain is not None else None
    )
    expected_runtime_domain = (
        "contacts_fixture"
        if expected_domain_pack_id == "contacts"
        else "mobile_messages_fixture"
        if expected_domain_pack_id == "mobile_messages"
        else None
    )
    chain_root = root / _safe_relative_path(chain.get("root_path"), "root_path")
    pack_path = chain_root / "dataset_release_pack.json"
    expected_pack_schema = _require_text(
        chain.get("release_pack_schema_version"),
        "release_pack_schema_version",
    )
    expected_manifest_schema = _require_text(
        chain.get("manifest_schema_version"),
        "manifest_schema_version",
    )
    reasons: list[str] = []
    try:
        verification = verify_dataset_release_pack(pack_path)
        pack = _json_mapping(pack_path)
        manifest = _json_mapping(chain_root / "manifest.json")
        metadata = _json_mapping(chain_root / "chain_metadata.json")
        profile_decision = _json_mapping(
            chain_root / "profile_decision_report.json"
        )
        validate_manifest_record(manifest)
        historical_profile = _mapping(
            manifest.get("run_profile"),
            "manifest.run_profile",
        )
        historical_profile_seed = _mapping(
            historical_profile.get("seed"),
            "manifest.run_profile.seed",
        )
        historical_domain = historical_profile_seed.get("domain")
        if historical_domain == "contacts":
            historical_domain = "contacts_fixture"
        historical_decision_profile = _mapping(
            profile_decision.get("profile"),
            "profile_decision.profile",
        )
        if pack.get("schema_version") != expected_pack_schema:
            reasons.append("historical_decision_not_reproduced")
        if manifest.get("schema_version") != expected_manifest_schema:
            reasons.append("dependency_schema_invalid")
        if (
            chain.get("domain_pack_id") != expected_domain_pack_id
            or chain.get("historical_profile_id")
            != expected_historical_profile_id
            or chain.get("historical_profile_schema_version")
            != expected_historical_profile_schema
            or metadata.get("schema_version") != COMPATIBILITY_CHAIN_SCHEMA_VERSION
            or metadata.get("chain_id") != chain_id
            or metadata.get("domain_pack_id") != chain.get("domain_pack_id")
            or metadata.get("historical_profile_id")
            != historical_profile.get("profile_id")
            or metadata.get("historical_profile_schema_version")
            != historical_profile.get("schema_version")
            or metadata.get("historical_profile_config_hash")
            != historical_profile.get("config_hash")
            or historical_domain != expected_runtime_domain
            or metadata.get("historical_profile_id")
            != chain.get("historical_profile_id")
            or metadata.get("historical_profile_schema_version")
            != chain.get("historical_profile_schema_version")
            or metadata.get("historical_profile_config_hash")
            != chain.get("historical_profile_config_hash")
            or historical_decision_profile.get("domain")
            != historical_domain
            or any(
                historical_decision_profile.get(field_name)
                != historical_profile.get(field_name)
                for field_name in (
                    "config_hash",
                    "generation_mode",
                    "profile_id",
                    "profile_purpose",
                    "schema_version",
                    "target_candidate_count",
                )
            )
            or metadata.get("manifest_schema_version") != expected_manifest_schema
            or metadata.get("release_pack_schema_version") != expected_pack_schema
            or metadata.get("historical_decision") != "passed"
            or metadata.get("current_evidence_status") != "insufficient_evidence"
            or metadata.get("claim_scope") != "historical_only"
        ):
            reasons.append("expected_assessment_mismatch")
        verification_record = verification.get("verification")
        if not isinstance(verification_record, Mapping):
            verification_record = {}
        if verification_record.get("status") != "passed":
            reasons.append("historical_decision_not_reproduced")
        else:
            reasons.append("historical_decision_reproduced")
        if expected_manifest_schema == "dataset_manifest_v2":
            mutation_report_path = chain_root / "mutation_admission_report.json"
            try:
                validate_mutation_admission_report(_json_mapping(mutation_report_path))
            except (OSError, ValueError):
                reasons.append("dependency_schema_invalid")
    except (OSError, ValueError, ContractValidationError):
        reasons.append("dependency_schema_invalid")
    expected_claim = chain.get("current_evidence_status")
    if expected_claim != "insufficient_evidence":
        reasons.append("expected_assessment_mismatch")
    return {
        "chain_id": chain_id,
        "status": "passed" if not any(
            reason
            in {
                "historical_decision_not_reproduced",
                "dependency_schema_invalid",
                "expected_assessment_mismatch",
            }
            for reason in reasons
        ) else "failed",
        "reason_codes": list(dict.fromkeys(reasons)),
        "historical_claim": "historical_only",
        "current_evidence_status": "insufficient_evidence",
    }


def verify_compatibility_corpus(
    corpus_root: Path,
) -> CorpusVerificationResult:
    """Verify every frozen profile, oracle, chain, and dependency."""

    manifest_path = corpus_root / "corpus_manifest.json"
    try:
        manifest = _json_mapping(manifest_path)
        if manifest.get("schema_version") != COMPATIBILITY_CORPUS_SCHEMA_VERSION:
            raise ValueError("schema")
        reasons = _verify_file_manifest(corpus_root, manifest)
    except (OSError, ValueError):
        return CorpusVerificationResult(
            status="failed",
            reason_codes=("manifest_invalid",),
            profile_results={},
            chain_results={},
        )

    profile_results: dict[str, object] = {}
    raw_profiles = manifest.get("profiles")
    if not isinstance(raw_profiles, Sequence) or isinstance(raw_profiles, (str, bytes, bytearray)):
        reasons.append("manifest_invalid")
        raw_profiles = ()
    declared_profile_count = manifest.get("profile_count")
    declared_historical_count = manifest.get("historical_profile_count")
    declared_synthetic_count = manifest.get("synthetic_bridge_count")
    if (
        not isinstance(declared_profile_count, int)
        or isinstance(declared_profile_count, bool)
        or declared_profile_count != len(raw_profiles)
        or not isinstance(declared_historical_count, int)
        or isinstance(declared_historical_count, bool)
        or not isinstance(declared_synthetic_count, int)
        or isinstance(declared_synthetic_count, bool)
    ):
        reasons.append("manifest_invalid")
    else:
        historical_count = sum(
            isinstance(raw_row, Mapping)
            and raw_row.get("role") == "historical_input"
            for raw_row in raw_profiles
        )
        synthetic_count = sum(
            isinstance(raw_row, Mapping)
            and raw_row.get("role") == "synthetic_compatibility_evidence"
            for raw_row in raw_profiles
        )
        if (
            historical_count != declared_historical_count
            or synthetic_count != declared_synthetic_count
            or historical_count + synthetic_count != declared_profile_count
        ):
            reasons.append("manifest_invalid")
    profile_ids_seen: set[str] = set()
    profile_paths_seen: set[str] = set()
    for raw_row in raw_profiles:
        try:
            row = _mapping(raw_row, "profile")
            if row.get("schema_version") != "compatibility_profile_entry_v1":
                reasons.append("manifest_invalid")
            profile_id = _require_text(row.get("profile_id"), "profile_id")
            if profile_id in profile_ids_seen:
                reasons.append("manifest_invalid")
            profile_ids_seen.add(profile_id)
            expected_profile_role = _COMPATIBILITY_PROFILE_ROLE_BY_ID.get(profile_id)
            expected_profile_schema = _COMPATIBILITY_PROFILE_SCHEMA_BY_ID.get(
                profile_id
            )
            if (
                expected_profile_role is None
                or row.get("role") != expected_profile_role
                or row.get("source_schema_version") != expected_profile_schema
            ):
                reasons.append("manifest_invalid")
            file_record = _mapping(row.get("file"), f"{profile_id}.file")
            profile_relative_path = _safe_relative_path(
                file_record.get("path"), f"{profile_id}.file.path"
            )
            if profile_relative_path in profile_paths_seen:
                reasons.append("manifest_invalid")
            profile_paths_seen.add(profile_relative_path)
            if row.get("role") not in {
                "historical_input",
                "synthetic_compatibility_evidence",
            }:
                reasons.append("manifest_invalid")
            if row.get("source_path") != profile_relative_path:
                reasons.append("expected_assessment_mismatch")
            try:
                raw_profile_record = _json_mapping(corpus_root / profile_relative_path)
                if (
                    raw_profile_record.get("profile_id") != profile_id
                    or raw_profile_record.get("schema_version")
                    != row.get("source_schema_version")
                ):
                    reasons.append("expected_assessment_mismatch")
            except ValueError:
                pass
            profile_path = corpus_root / _safe_relative_path(
                file_record.get("path"), f"{profile_id}.file.path"
            )
            actual_profile_file = _hash_record(
                profile_path,
                relative_path=str(file_record.get("path")),
            )
            if (
                actual_profile_file["sha256"] != file_record.get("sha256")
                or actual_profile_file["byte_count"] != file_record.get("byte_count")
            ):
                reasons.append("dependency_tampered")
            compiled = compile_legacy_profile(profile_path, corpus_root=corpus_root)
            expected_assessment = _expected_axis_record(row)
            if isinstance(compiled, CompatibilityFailure):
                observed_assessment = compiled.assessment
                observed = compiled.to_record()
            else:
                observed_assessment = compiled.assessment
                observed = {
                    "status": compiled.status,
                    "assessment": compiled.assessment.to_record(),
                }
                if not canonical_projection_has_no_legacy_semantic_aliases(
                    compiled.canonical_projection
                ):
                    reasons.append("expected_projection_mismatch")
                expected_projection = row.get("expected_projection")
                if expected_projection is None:
                    reasons.append("canonical_projection_missing")
                    observed["projection_match"] = False
                else:
                    expected_path = corpus_root / _safe_relative_path(
                        expected_projection, f"{profile_id}.expected_projection"
                    )
                    try:
                        expected_record = _json_mapping(expected_path)
                    except ValueError:
                        expected_record = None
                    expected_projection_record = (
                        expected_record.get("projection")
                        if isinstance(expected_record, Mapping)
                        else None
                    )
                    if (
                        not isinstance(expected_record, Mapping)
                        or expected_record.get("profile_id") != profile_id
                        or expected_record.get("schema_version")
                        != "reviewed_canonical_projection_v1"
                        or expected_record.get("review_status") != "reviewed"
                        or expected_projection_record
                        != dict(compiled.canonical_projection)
                    ):
                        reasons.append("expected_projection_mismatch")
                        observed["projection_match"] = False
                    else:
                        observed["projection_match"] = True
                if compiled.selected_mapping.mapping_id == "":
                    reasons.append("unknown_compatibility_mapping")
            if observed_assessment != expected_assessment:
                reasons.append("expected_assessment_mismatch")
            if (
                isinstance(compiled, CompatibilityFailure)
                and compiled.reason_code == "unknown_task_label"
            ):
                reasons.append("unknown_semantic_label")
            profile_results[profile_id] = observed
        except (OSError, ValueError, DomainPackContractError):
            reasons.append("profile_row_missing")
    if profile_ids_seen != (
        COMPATIBILITY_HISTORICAL_PROFILE_IDS
        | COMPATIBILITY_SYNTHETIC_PROFILE_IDS
    ):
        reasons.append("manifest_invalid")

    chain_results: dict[str, object] = {}
    raw_chains = manifest.get("chains")
    if not isinstance(raw_chains, Sequence) or isinstance(raw_chains, (str, bytes, bytearray)):
        reasons.append("manifest_invalid")
        raw_chains = ()
    declared_chain_count = manifest.get("chain_count")
    if (
        not isinstance(declared_chain_count, int)
        or isinstance(declared_chain_count, bool)
        or declared_chain_count != len(raw_chains)
    ):
        reasons.append("manifest_invalid")
    chain_ids_seen: set[str] = set()
    for raw_chain in raw_chains:
        try:
            chain_record = _mapping(raw_chain, "chain")
            chain_id = _require_text(chain_record.get("chain_id"), "chain_id")
            if chain_id in chain_ids_seen:
                reasons.append("manifest_invalid")
            chain_ids_seen.add(chain_id)
            chain_result = _verify_chain(corpus_root, chain_record)
            chain_results[chain_id] = chain_result
            raw_reason_codes = chain_result.get("reason_codes")
            if isinstance(raw_reason_codes, Sequence) and not isinstance(
                raw_reason_codes, (str, bytes, bytearray)
            ):
                reasons.extend(
                    reason
                    for reason in raw_reason_codes
                    if isinstance(reason, str)
                    and reason not in {"historical_decision_reproduced"}
                )
        except (OSError, ValueError, ContractValidationError):
            reasons.append("dependency_schema_invalid")
    if chain_ids_seen != COMPATIBILITY_CHAIN_IDS:
        reasons.append("manifest_invalid")

    reasons = list(dict.fromkeys(reasons))
    status = "passed" if not reasons else "failed"
    return CorpusVerificationResult(
        status=status,
        reason_codes=tuple(reasons),
        profile_results=profile_results,
        chain_results=chain_results,
    )


def canonical_projection_has_no_legacy_semantic_aliases(
    projection: Mapping[str, object],
) -> bool:
    """Check the canonical semantic namespace without rejecting runtime ids."""

    semantic = projection.get("semantic")
    if not isinstance(semantic, Mapping):
        return False
    forbidden = {
        "contacts_fixture",
        "mobile_messages_fixture",
        "state_change",
        "branching",
        "fixture",
    }
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True)
    return not any(alias in encoded for alias in forbidden)


def inject_unknown_semantic_label(
    record: Mapping[str, object],
    *,
    label: str = "unknown_semantic_label",
) -> dict[str, object]:
    """Return a copied profile record with one unknown label for fail-closed tests."""

    copied = json.loads(json.dumps(record))
    seed = copied.get("seed")
    if not isinstance(seed, dict) or not isinstance(seed.get("task_taxonomy"), list):
        raise ValueError("profile seed taxonomy is invalid")
    seed["task_taxonomy"].append(label)
    return copied


def compile_legacy_profile_record(
    record: Mapping[str, object],
    *,
    source_path: Path,
    corpus_root: Path | None = None,
    mapping_set: CompatibilityMappingSet | None = None,
) -> CompatibilityCompilation | CompatibilityFailure:
    """Compile a copied legacy record while retaining the original path boundary."""

    with tempfile.TemporaryDirectory(prefix="compatibility-profile-") as tmpdir:
        temporary_root = Path(tmpdir)
        temporary_profile = temporary_root / source_path.name
        temporary_profile.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        source = record.get("source")
        if isinstance(source, Mapping) and isinstance(source.get("path"), str):
            try:
                relative_source_path = _safe_relative_path(
                    source["path"],
                    "source.path",
                )
            except ValueError:
                return _failure(
                    "unsafe_source_path",
                    runnability=("failed", "unsafe_source_path"),
                )
            source_path_value = source_path.parent / relative_source_path
            if source_path_value.exists():
                temporary_source_path = temporary_root / relative_source_path
                temporary_source_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_source_path.write_bytes(source_path_value.read_bytes())
        return compile_legacy_profile(
            temporary_profile,
            corpus_root=corpus_root,
            mapping_set=mapping_set,
        )


__all__ = [
    "COMPATIBILITY_AXES",
    "COMPATIBILITY_CHAIN_IDS",
    "COMPATIBILITY_CORPUS_SCHEMA_VERSION",
    "COMPATIBILITY_HISTORICAL_PROFILE_IDS",
    "COMPATIBILITY_REASON_CODES",
    "COMPATIBILITY_SYNTHETIC_PROFILE_IDS",
    "CompatibilityAssessment",
    "CompatibilityAxisResult",
    "CompatibilityCompilation",
    "CompatibilityFailure",
    "CorpusVerificationResult",
    "LegacyProfile",
    "MigrationLineage",
    "canonical_projection_has_no_legacy_semantic_aliases",
    "compatibility_mapping_set",
    "compile_legacy_profile",
    "compile_legacy_profile_record",
    "inject_unknown_semantic_label",
    "read_legacy_profile",
    "verify_compatibility_corpus",
]
