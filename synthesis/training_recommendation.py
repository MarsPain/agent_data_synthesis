"""Verifier-only Workspace training-recommendation evidence.

The external experiment boundary is intentionally small.  Experiment owners
choose the model, tokenizer, trainer, benchmark, and compute outside this
repository.  This module reads ordinary JSON evidence, checks the identities
and declarations that are visible in that evidence, recomputes the paired
binary statistic, and returns a bounded decision.  It never loads a model or
tokenizer, starts training, opens a sealed split, or performs an overlap scan.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from synthesis.domain_pack import (
    DomainPackContractError,
    canonical_domain_pack_hash,
)

WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION = "workspace_training_protocol_v1"
WORKSPACE_TRAINING_ARM_SCHEMA_VERSION = "workspace_training_arm_manifest_v1"
WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION = "workspace_training_evaluation_manifest_v1"
WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION = "workspace_training_paired_results_v1"
WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION = "workspace_training_leakage_report_v1"
WORKSPACE_TRAINING_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "workspace_training_experiment_manifest_v1"
)
TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION = "training_recommendation_result_v1"
TRAINING_RECOMMENDATION_GATE_SCHEMA_VERSION = "qualification_training_recommendation_v1"
PAIRED_BOOTSTRAP_SCHEMA_VERSION = "paired_percentile_bootstrap_v1"

# Short aliases keep the public names discoverable for callers that use the
# shorter vocabulary in the product specification.
TRAINING_PROTOCOL_SCHEMA_VERSION = WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION
TRAINING_ARM_SCHEMA_VERSION = WORKSPACE_TRAINING_ARM_SCHEMA_VERSION
TRAINING_EVALUATION_SCHEMA_VERSION = WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION
TRAINING_PAIRED_RESULTS_SCHEMA_VERSION = WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION
TRAINING_LEAKAGE_SCHEMA_VERSION = WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION
TRAINING_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    WORKSPACE_TRAINING_EVIDENCE_MANIFEST_SCHEMA_VERSION
)

TRAINING_PROTOCOL_FILENAME = "workspace_training_protocol.json"
TRAINING_BASELINE_FILENAME = "workspace_training_baseline.json"
TRAINING_TREATMENT_FILENAME = "workspace_training_treatment.json"
TRAINING_EVALUATION_FILENAME = "workspace_training_evaluation.json"
TRAINING_PAIRED_RESULTS_FILENAME = "workspace_training_paired_results.json"
TRAINING_LEAKAGE_FILENAME = "workspace_training_leakage.json"
TRAINING_RESULT_FILENAME = "training_recommendation_result.json"

EXTERNAL_EXPERIMENT_EVIDENCE_CLASS = "external_experiment"
CONFORMANCE_FIXTURE_EVIDENCE_CLASS = "conformance_fixture"
CONFORMANCE_FIXTURE_MARKER = "workspace_training_conformance_v1"
CONFORMANCE_FIXTURE_MARKER_ALLOWLIST = frozenset({CONFORMANCE_FIXTURE_MARKER})
TRAINING_EVIDENCE_CLASSES = {
    EXTERNAL_EXPERIMENT_EVIDENCE_CLASS,
    CONFORMANCE_FIXTURE_EVIDENCE_CLASS,
}
TRAINING_RESULT_STATUSES = {
    "training_recommended",
    "no_detected_meaningful_gain",
    "invalid_experiment",
    "insufficient_evidence",
    "protocol_conformance_passed",
}
TRAINING_DECISION_STATUSES = TRAINING_RESULT_STATUSES
TRAINING_BOOTSTRAP_REPLICATES = 10_000
TRAINING_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95
TRAINING_RELATIVE_GAIN_THRESHOLD = 0.01
TRAINING_COUNT_TOLERANCE = 0.10
BOOTSTRAP_REPLICATE_COUNT = TRAINING_BOOTSTRAP_REPLICATES
MEANINGFUL_GAIN_THRESHOLD = TRAINING_RELATIVE_GAIN_THRESHOLD
SAMPLE_COUNT_TOLERANCE = TRAINING_COUNT_TOLERANCE

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

TRAINING_REASON_CODES = frozenset(
    {
        "training_recommended",
        "no_detected_meaningful_gain",
        "protocol_conformance_passed",
        "evidence_missing",
        "evidence_unreadable",
        "evidence_malformed",
        "evidence_unknown_version",
        "content_hash_mismatch",
        "protocol_identity_mismatch",
        "protocol_not_preregistered",
        "publishable_release_missing",
        "publishable_release_invalid",
        "evidence_class_mismatch",
        "non_qualifying_evidence_class",
        "training_identity_mismatch",
        "common_inputs_mismatch",
        "control_manifest_mismatch",
        "release_manifest_mismatch",
        "manifest_membership_mismatch",
        "record_count_not_positive",
        "record_count_tolerance_exceeded",
        "task_ids_missing",
        "task_ids_duplicate",
        "task_ids_extra",
        "task_ids_reordered",
        "task_ids_arm_mismatch",
        "non_binary_outcome",
        "baseline_rate_not_positive",
        "calculation_mismatch",
        "bootstrap_mismatch",
        "leakage_identity_mismatch",
        "leakage_protocol_not_frozen",
        "leakage_evaluation_used_for_training",
        "leakage_overlap_unresolved",
        "post_registration_change",
        "evidence_file_hash_mismatch",
        "evidence_non_passing",
    }
)

_REASON_TEXT = {
    "training_recommended": "the paired lower bound exceeds the declared meaningful-gain threshold",
    "no_detected_meaningful_gain": "the paired lower bound does not exceed the declared meaningful-gain threshold",
    "protocol_conformance_passed": "the conformance fixture passed the numerical protocol checks",
    "evidence_missing": "required training evidence is missing",
    "evidence_unreadable": "training evidence could not be read as JSON evidence",
    "evidence_malformed": "training evidence is malformed",
    "evidence_unknown_version": "training evidence uses an unsupported schema version",
    "content_hash_mismatch": "a content-addressed training record does not match its declared hash",
    "protocol_identity_mismatch": "training evidence is bound to a different registered protocol",
    "protocol_not_preregistered": "the protocol was not frozen before training",
    "publishable_release_missing": "the protocol does not bind a Publishable release",
    "publishable_release_invalid": "the bound release is not a valid Publishable subject",
    "evidence_class_mismatch": "training evidence uses inconsistent evidence classes",
    "non_qualifying_evidence_class": "conformance evidence cannot establish a real training recommendation",
    "training_identity_mismatch": "baseline and treatment training identities differ",
    "common_inputs_mismatch": "baseline and treatment common inputs differ",
    "control_manifest_mismatch": "the arm evidence does not bind the registered control manifest",
    "release_manifest_mismatch": "the arm evidence does not bind the registered release manifest",
    "manifest_membership_mismatch": "training-record replacement membership is inconsistent",
    "record_count_not_positive": "inserted and removed training-record counts must be positive",
    "record_count_tolerance_exceeded": "inserted and removed training-record counts exceed the ten-percent tolerance",
    "task_ids_missing": "a registered evaluation task is missing from paired results",
    "task_ids_duplicate": "a paired task id occurs more than once",
    "task_ids_extra": "paired results contain an unregistered task id",
    "task_ids_reordered": "paired result task order differs from the registered order",
    "task_ids_arm_mismatch": "baseline and treatment do not share the registered task set",
    "non_binary_outcome": "paired outcomes are not binary",
    "baseline_rate_not_positive": "the observed baseline success rate is not positive",
    "calculation_mismatch": "a supplied aggregate calculation does not match recomputation",
    "bootstrap_mismatch": "a supplied bootstrap calculation does not match recomputation",
    "leakage_identity_mismatch": "leakage evidence does not bind the registered evaluation and scoring identities",
    "leakage_protocol_not_frozen": "leakage evidence does not confirm pre-training protocol registration",
    "leakage_evaluation_used_for_training": "the evaluation split was declared as training input",
    "leakage_overlap_unresolved": "leakage evidence reports unresolved overlap",
    "post_registration_change": "evidence reports a post-registration protocol change",
    "evidence_file_hash_mismatch": "an imported evidence file does not match its declared byte hash",
    "evidence_non_passing": "the training recommendation gate is not passing",
}


class TrainingRecommendationContractError(ValueError):
    """A bounded training-evidence contract failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _evidence_origin(evidence_class: object) -> str:
    if evidence_class == EXTERNAL_EXPERIMENT_EVIDENCE_CLASS:
        return "external_submitter"
    if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        return "repository_conformance"
    raise TrainingRecommendationContractError("evidence_class_mismatch")


class _TrainingFailure(TrainingRecommendationContractError):
    """Internal error that records whether an outcome is invalid or missing."""

    def __init__(self, reason_code: str, *, insufficient: bool = False) -> None:
        super().__init__(reason_code)
        self.insufficient = insufficient


def _hash_value(value: object) -> str:
    """Hash a bounded record while retaining finite statistical floats."""

    try:
        return canonical_domain_pack_hash(value)
    except DomainPackContractError:
        normalized = _normalize_finite_floats(value)
        if normalized is value:
            raise TrainingRecommendationContractError("evidence_malformed") from None
        try:
            return canonical_domain_pack_hash(normalized)
        except DomainPackContractError as exc:
            raise TrainingRecommendationContractError(exc.reason_code) from None


def _normalize_finite_floats(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TrainingRecommendationContractError("evidence_malformed")
        return {"__finite_float__": repr(value)}
    if isinstance(value, Mapping):
        return {str(key): _normalize_finite_floats(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_finite_floats(child) for child in value]
    return value


def _mapping(value: object, reason: str = "evidence_malformed") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrainingRecommendationContractError(reason)
    return value


def _string(value: object, reason: str = "evidence_malformed") -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise TrainingRecommendationContractError(reason)
    return value


def _identifier(value: object, reason: str = "evidence_malformed") -> str:
    text = _string(value, reason)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise TrainingRecommendationContractError(reason)
    return text


def _hash(value: object, reason: str = "evidence_malformed") -> str:
    text = _string(value, reason)
    if not _HASH_RE.fullmatch(text):
        raise TrainingRecommendationContractError(reason)
    return text


def _bool(value: object, reason: str = "evidence_malformed") -> bool:
    if not isinstance(value, bool):
        raise TrainingRecommendationContractError(reason)
    return value


def _integer(value: object, reason: str = "evidence_malformed") -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TrainingRecommendationContractError(reason)
    return value


def _sequence(value: object, reason: str = "evidence_malformed") -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TrainingRecommendationContractError(reason)
    return list(value)


def _safe_object(value: object, reason: str = "evidence_malformed") -> object:
    if not isinstance(value, (Mapping, Sequence, str, int, float, bool, type(None))):
        raise TrainingRecommendationContractError(reason)
    try:
        _hash_value({"value": value})
    except (TrainingRecommendationContractError, DomainPackContractError):
        raise TrainingRecommendationContractError(reason) from None
    return value


def _exact_keys(record: Mapping[str, object], expected: set[str]) -> None:
    if set(record) != expected:
        raise TrainingRecommendationContractError("evidence_malformed")


def _record_with_identity(
    record: Mapping[str, object], *, id_field: str, hash_field: str, prefix: str
) -> dict[str, object]:
    core = dict(record)
    core.pop(id_field, None)
    core.pop(hash_field, None)
    content_hash = _hash_value(core)
    return {
        **core,
        id_field: prefix + content_hash.removeprefix("sha256:")[:24],
        hash_field: content_hash,
    }


def _assert_identity(
    record: Mapping[str, object], *, id_field: str, hash_field: str, prefix: str
) -> None:
    declared_hash = _hash(record.get(hash_field))
    expected_hash = _hash_value(
        {key: value for key, value in record.items() if key not in {id_field, hash_field}}
    )
    if declared_hash != expected_hash:
        raise TrainingRecommendationContractError("content_hash_mismatch")
    declared_id = _identifier(record.get(id_field))
    if declared_id != prefix + declared_hash.removeprefix("sha256:")[:24]:
        raise TrainingRecommendationContractError("content_hash_mismatch")


def _protocol_reference(protocol: Mapping[str, object]) -> dict[str, object]:
    _validate_protocol(protocol)
    return {
        "protocol_id": str(protocol["protocol_id"]),
        "protocol_hash": str(protocol["content_hash"]),
    }


def _validate_protocol_reference_record(value: Mapping[str, object]) -> None:
    _exact_keys(value, {"protocol_id", "protocol_hash"})
    _identifier(value.get("protocol_id"))
    _hash(value.get("protocol_hash"))


def _domain_pack_reference(value: object) -> dict[str, object]:
    reference = _mapping(value, "publishable_release_invalid")
    _exact_keys(
        reference,
        {"schema_version", "domain_pack_id", "pack_version", "pack_hash"},
    )
    if reference.get("schema_version") != "domain_pack_reference_v1":
        raise TrainingRecommendationContractError("publishable_release_invalid")
    return {
        "schema_version": reference["schema_version"],
        "domain_pack_id": _identifier(
            reference.get("domain_pack_id"), "publishable_release_invalid"
        ),
        "pack_version": _identifier(
            reference.get("pack_version"), "publishable_release_invalid"
        ),
        "pack_hash": _hash(reference.get("pack_hash"), "publishable_release_invalid"),
    }


def _publishable_release(value: object) -> dict[str, object]:
    supplied = _mapping(value, "publishable_release_missing")
    subject = supplied.get("subject")
    source = _mapping(subject) if isinstance(subject, Mapping) else supplied
    qualification = supplied.get(
        "effective_qualification",
        supplied.get("qualification", source.get("qualification")),
    )
    if qualification != "publishable":
        raise TrainingRecommendationContractError("publishable_release_invalid")
    decision = supplied.get("decision")
    decision_map = _mapping(decision) if isinstance(decision, Mapping) else supplied
    status = decision_map.get("status", supplied.get("status"))
    if status not in {None, "passed", "publishable"}:
        raise TrainingRecommendationContractError("publishable_release_invalid")
    bundle_hash = supplied.get(
        "publishability_bundle_hash",
        supplied.get("bundle_content_hash", supplied.get("bundle_hash")),
    )
    decision_hash = supplied.get(
        "publishability_decision_hash",
        supplied.get("decision_hash"),
    )
    result: dict[str, object] = {
        "qualification": "publishable",
        "subject_id": _identifier(source.get("subject_id"), "publishable_release_invalid"),
        "subject_hash": _hash(source.get("subject_hash"), "publishable_release_invalid"),
        "release_id": _identifier(source.get("release_id"), "publishable_release_invalid"),
        "release_pack_hash": _hash(
            source.get("release_pack_hash"), "publishable_release_invalid"
        ),
        "publishability_bundle_hash": _hash(bundle_hash, "publishable_release_invalid"),
        "publishability_decision_hash": _hash(
            decision_hash, "publishable_release_invalid"
        ),
    }
    result["domain_pack_reference"] = _domain_pack_reference(
        source.get("domain_pack_reference", supplied.get("domain_pack_reference"))
    )
    return result


def _normalize_manifest_reference(value: object, label: str) -> dict[str, object]:
    supplied = _mapping(value, "evidence_malformed")
    manifest_id = supplied.get("manifest_id", supplied.get("id"))
    if manifest_id is None:
        raise TrainingRecommendationContractError("evidence_malformed")
    manifest_id = _identifier(manifest_id)
    raw_records = supplied.get("record_hashes", supplied.get("records"))
    records = _sequence(raw_records, "evidence_malformed")
    normalized_records: list[str] = []
    seen: set[str] = set()
    for item in records:
        record = _string(item)
        if record in seen:
            raise TrainingRecommendationContractError("manifest_membership_mismatch")
        seen.add(record)
        normalized_records.append(record)
    if not normalized_records:
        raise TrainingRecommendationContractError("record_count_not_positive")
    declared_hash = supplied.get("content_hash", supplied.get("manifest_hash"))
    if declared_hash is None:
        declared_hash = _hash_value(
            {
                "manifest_id": manifest_id,
                "record_hashes": normalized_records,
            }
        )
    declared_hash = _hash(declared_hash)
    expected_hash = _hash_value(
        {
            "manifest_id": manifest_id,
            "record_hashes": normalized_records,
        }
    )
    if declared_hash != expected_hash:
        raise TrainingRecommendationContractError("content_hash_mismatch")
    declared_count = supplied.get("record_count", len(normalized_records))
    if _integer(declared_count) != len(normalized_records):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    return {
        "manifest_id": manifest_id,
        "content_hash": declared_hash,
        "record_hashes": normalized_records,
        "record_count": len(normalized_records),
        "manifest_kind": label,
    }


def _registration(value: object | None) -> dict[str, object]:
    if value is None:
        raise TrainingRecommendationContractError("evidence_missing")
    supplied = dict(_mapping(value, "evidence_malformed"))
    if set(supplied) != {
        "registered_at",
        "registered_before_training",
        "post_registration_change",
    }:
        raise TrainingRecommendationContractError("evidence_malformed")
    return {
        "registered_at": _string(supplied["registered_at"]),
        "registered_before_training": _bool(supplied["registered_before_training"]),
        "post_registration_change": _bool(supplied["post_registration_change"]),
    }


def _field(fields: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in fields:
            return fields[name]
    raise TrainingRecommendationContractError("evidence_missing")


def build_training_recommendation_protocol(
    *,
    specification: Mapping[str, object] | None = None,
    evidence_class: str = EXTERNAL_EXPERIMENT_EVIDENCE_CLASS,
    **fields: object,
) -> dict[str, object]:
    """Build the immutable pre-training Workspace protocol declaration.

    The function requires all experiment choices that affect interpretation;
    it never selects a model, tokenizer, trainer, benchmark, corpus, or budget.
    ``specification`` is a convenience for callers that already hold one
    structured registration object.
    """

    if evidence_class not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    values: dict[str, object] = {}
    if specification is not None:
        values.update(dict(_mapping(specification)))
    values.update(fields)
    declared_class = values.pop("evidence_class", None)
    if declared_class is not None and evidence_class == EXTERNAL_EXPERIMENT_EVIDENCE_CLASS:
        evidence_class = _string(declared_class)
    publishable_release = _publishable_release(
        _field(values, "publishable_release", "publishability")
    )
    model = _safe_object(_field(values, "model", "initial_model"))
    tokenizer = _safe_object(_field(values, "tokenizer", "tokenizer_declaration"))
    training_system = _safe_object(_field(values, "training_system", "trainer"))
    training_code = _safe_object(_field(values, "training_code", "code"))
    environment = _safe_object(
        _field(values, "environment", "training_environment")
    )
    hyperparameters = _safe_object(_field(values, "hyperparameters"))
    seed = _string(_field(values, "seed"))
    schedule = _safe_object(_field(values, "schedule"))
    stopping_rules = _safe_object(
        _field(values, "stopping_rules", "stopping")
    )
    exclusion_rules = _safe_object(
        _field(values, "exclusion_rules", "exclusions")
    )
    common_inputs = _safe_object(_field(values, "common_inputs"))
    control_manifest = _normalize_manifest_reference(
        _field(values, "control_manifest", "control_corpus"), "control"
    )
    release_manifest = _normalize_manifest_reference(
        _field(values, "release_manifest", "release_corpus"), "release"
    )
    benchmark = _mapping(_field(values, "benchmark", "benchmark_suite"))
    benchmark_record = {
        "suite_id": _identifier(
            benchmark.get("suite_id", benchmark.get("benchmark_suite_id"))
        ),
        "suite_version": _string(
            benchmark.get("suite_version", benchmark.get("benchmark_suite_version"))
        ),
    }
    sealed_split = _mapping(_field(values, "sealed_split", "split"))
    split_record = {
        "split_id": _identifier(sealed_split.get("split_id")),
        "split_hash": _hash(sealed_split.get("split_hash")),
    }
    task_ids = [_identifier(item) for item in _sequence(_field(values, "ordered_task_ids", "task_ids"))]
    if not task_ids:
        raise TrainingRecommendationContractError("evidence_malformed")
    if len(set(task_ids)) != len(task_ids):
        raise TrainingRecommendationContractError("task_ids_duplicate")
    scoring = _mapping(_field(values, "scoring", "scoring_code"))
    scoring_code_hash = _hash(
        scoring.get("scoring_code_hash", scoring.get("code_hash"))
    )
    leakage_method = _mapping(_field(values, "leakage_method", "leakage"))
    leakage_method_record = {
        "method_id": _identifier(leakage_method.get("method_id")),
        "method_hash": _hash(leakage_method.get("method_hash")),
    }
    supplied_schemas = values.get("result_schemas")
    default_schemas = {
        "protocol": WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION,
        "baseline": WORKSPACE_TRAINING_ARM_SCHEMA_VERSION,
        "treatment": WORKSPACE_TRAINING_ARM_SCHEMA_VERSION,
        "evaluation": WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION,
        "paired_results": WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION,
        "leakage": WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION,
        "result": TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION,
    }
    if supplied_schemas is not None:
        supplied_map = _mapping(supplied_schemas)
        if set(supplied_map) != set(default_schemas):
            raise TrainingRecommendationContractError("evidence_malformed")
        default_schemas = {
            key: _string(supplied_map[key]) for key in default_schemas
        }
    registration = _registration(_field(values, "registration"))
    selection_rule = _safe_object(_field(values, "selection_rule"))
    bootstrap_seed = _string(_field(values, "bootstrap_seed"))
    origin = _evidence_origin(evidence_class)
    conformance_marker = (
        CONFORMANCE_FIXTURE_MARKER
        if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS
        else None
    )
    training_identity = {
        "model": model,
        "tokenizer": tokenizer,
        "training_system": training_system,
        "training_code": training_code,
        "environment": environment,
        "hyperparameters": hyperparameters,
        "seed": seed,
        "schedule": schedule,
        "stopping_rules": stopping_rules,
        "exclusion_rules": exclusion_rules,
    }
    record: dict[str, object] = {
        "schema_version": WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION,
        "evidence_class": evidence_class,
        "evidence_origin": origin,
        "conformance_marker": conformance_marker,
        "registration": registration,
        "publishable_release": publishable_release,
        "training_identity": training_identity,
        "common_inputs": common_inputs,
        "manifests": {
            "control": control_manifest,
            "release": release_manifest,
        },
        "matching": {
            "unit": "training_record_replacement",
            "selection_rule": selection_rule,
            "tolerance": TRAINING_COUNT_TOLERANCE,
        },
        "evaluation": {
            "benchmark": benchmark_record,
            "sealed_split": split_record,
            "ordered_task_ids": task_ids,
            "scoring_code_hash": scoring_code_hash,
            "metric": {
                "name": "task_success_rate",
                "outcome_type": "binary",
                "direction": "higher_is_better",
            },
        },
        "bootstrap": {
            "schema_version": PAIRED_BOOTSTRAP_SCHEMA_VERSION,
            "algorithm": "paired_percentile_bootstrap",
            "replicate_count": TRAINING_BOOTSTRAP_REPLICATES,
            "seed": bootstrap_seed,
            "confidence_level": TRAINING_BOOTSTRAP_CONFIDENCE_LEVEL,
            "interval": "two_sided_percentile",
            "lower_rank": 250,
            "upper_rank": 9_750,
            "relative_lower_bound_threshold": TRAINING_RELATIVE_GAIN_THRESHOLD,
            "draw_rule": "unsigned_int(SHA256(UTF8(seed + ':' + replicate + ':' + draw))) mod N",
        },
        "leakage_method": leakage_method_record,
        "result_schemas": default_schemas,
    }
    result = _record_with_identity(
        record,
        id_field="protocol_id",
        hash_field="content_hash",
        prefix="workspace_training_protocol_",
    )
    _validate_protocol(result)
    return result


build_workspace_training_protocol = build_training_recommendation_protocol
build_training_protocol = build_training_recommendation_protocol


def _protocol_training_identity(protocol: Mapping[str, object]) -> Mapping[str, object]:
    return _mapping(protocol["training_identity"])


def build_training_recommendation_arm_manifest(
    *,
    protocol: Mapping[str, object],
    arm: str,
    training_record_hashes: Sequence[str],
    removed_control_record_hashes: Sequence[str] = (),
    inserted_release_record_hashes: Sequence[str] = (),
    training_identity: Mapping[str, object] | None = None,
    common_inputs: object | None = None,
    optional_observations: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build one content-addressed baseline or treatment arm declaration."""

    _validate_protocol(protocol)
    if arm not in {"baseline", "treatment"}:
        raise TrainingRecommendationContractError("evidence_malformed")
    records = [_string(item) for item in training_record_hashes]
    if not records or len(set(records)) != len(records):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    removed = [_string(item) for item in removed_control_record_hashes]
    inserted = [_string(item) for item in inserted_release_record_hashes]
    if len(set(removed)) != len(removed) or len(set(inserted)) != len(inserted):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    identity = (
        _protocol_training_identity(protocol)
        if training_identity is None
        else _mapping(training_identity)
    )
    inputs = (
        protocol["common_inputs"] if common_inputs is None else _safe_object(common_inputs)
    )
    manifest = {
        "manifest_id": f"{arm}_training_v1",
        "content_hash": _hash_value(
            {"arm": arm, "record_hashes": records}
        ),
        "record_hashes": records,
        "record_count": len(records),
    }
    record: dict[str, object] = {
        "schema_version": WORKSPACE_TRAINING_ARM_SCHEMA_VERSION,
        "evidence_class": protocol["evidence_class"],
        "evidence_origin": protocol["evidence_origin"],
        "arm": arm,
        "protocol_reference": _protocol_reference(protocol),
        "training_identity": identity,
        "common_inputs": inputs,
        "training_manifest": manifest,
        "replacement": {
            "removed_control_record_hashes": removed,
            "inserted_release_record_hashes": inserted,
            "removed_record_count": len(removed),
            "inserted_record_count": len(inserted),
        },
        "optional_observations": (
            {} if optional_observations is None else dict(_mapping(optional_observations))
        ),
    }
    return _record_with_identity(
        record,
        id_field="arm_manifest_id",
        hash_field="content_hash",
        prefix=f"workspace_training_{arm}_",
    )


build_training_arm_manifest = build_training_recommendation_arm_manifest
build_workspace_training_arm_manifest = build_training_recommendation_arm_manifest


def build_training_recommendation_evaluation_manifest(
    *, protocol: Mapping[str, object]
) -> dict[str, object]:
    """Build the sealed-evaluation identity without reading its samples."""

    _validate_protocol(protocol)
    evaluation = _mapping(protocol["evaluation"])
    record = {
        "schema_version": WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION,
        "evidence_class": protocol["evidence_class"],
        "evidence_origin": protocol["evidence_origin"],
        "protocol_reference": _protocol_reference(protocol),
        "benchmark": dict(_mapping(evaluation["benchmark"])),
        "sealed_split": dict(_mapping(evaluation["sealed_split"])),
        "ordered_task_ids": list(_sequence(evaluation["ordered_task_ids"])),
        "scoring_code_hash": evaluation["scoring_code_hash"],
        "result_schema_version": _mapping(protocol["result_schemas"])["paired_results"],
    }
    return _record_with_identity(
        record,
        id_field="evaluation_id",
        hash_field="content_hash",
        prefix="workspace_training_evaluation_",
    )


build_workspace_training_evaluation_manifest = (
    build_training_recommendation_evaluation_manifest
)


def build_training_recommendation_paired_results(
    *,
    protocol: Mapping[str, object],
    evaluation: Mapping[str, object],
    baseline_successes: Sequence[int],
    treatment_successes: Sequence[int],
    reported_statistics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build ordered paired binary outcomes; no task payloads are accepted."""

    _validate_protocol(protocol)
    _validate_evaluation(evaluation)
    task_ids = list(_sequence(_mapping(protocol["evaluation"])["ordered_task_ids"]))
    baseline = list(baseline_successes)
    treatment = list(treatment_successes)
    if len(baseline) != len(task_ids) or len(treatment) != len(task_ids):
        raise TrainingRecommendationContractError("task_ids_arm_mismatch")
    for outcome in [*baseline, *treatment]:
        if outcome not in {0, 1} or isinstance(outcome, bool):
            raise TrainingRecommendationContractError("non_binary_outcome")
    rows = [
        {
            "task_id": task_id,
            "baseline_success": base,
            "treatment_success": treat,
        }
        for task_id, base, treat in zip(task_ids, baseline, treatment)
    ]
    if reported_statistics is None:
        reported = {
            "baseline_success_rate": sum(baseline) / len(baseline),
            "treatment_success_rate": sum(treatment) / len(treatment),
        }
    else:
        reported = dict(_mapping(reported_statistics))
    record = {
        "schema_version": WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION,
        "evidence_class": protocol["evidence_class"],
        "evidence_origin": protocol["evidence_origin"],
        "protocol_reference": _protocol_reference(protocol),
        "evaluation_reference": {
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_hash": evaluation["content_hash"],
        },
        "results": rows,
        "reported_statistics": reported,
        "result_schema_version": _mapping(protocol["result_schemas"])["result"],
    }
    return _record_with_identity(
        record,
        id_field="paired_results_id",
        hash_field="content_hash",
        prefix="workspace_training_paired_",
    )


build_workspace_training_paired_results = build_training_recommendation_paired_results


def build_training_recommendation_leakage_report(
    *, protocol: Mapping[str, object], evaluation: Mapping[str, object],
    protocol_frozen_before_training: bool = True,
    evaluation_used_for_training: bool = False,
    unresolved_overlap_count: int = 0,
) -> dict[str, object]:
    """Build a declaration-only leakage report.

    ``unresolved_overlap_count`` is supplied evidence.  It is never computed
    here because the sealed split is intentionally unavailable to this repo.
    """

    _validate_protocol(protocol)
    _validate_evaluation(evaluation)
    if unresolved_overlap_count < 0:
        raise TrainingRecommendationContractError("evidence_malformed")
    leakage_method = dict(_mapping(protocol["leakage_method"]))
    record = {
        "schema_version": WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION,
        "evidence_class": protocol["evidence_class"],
        "evidence_origin": protocol["evidence_origin"],
        "protocol_reference": _protocol_reference(protocol),
        "evaluation_reference": {
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_hash": evaluation["content_hash"],
        },
        "sealed_split_hash": _mapping(protocol["evaluation"])["sealed_split"]["split_hash"],
        "scoring_code_hash": _mapping(protocol["evaluation"])["scoring_code_hash"],
        "leakage_method": leakage_method,
        "protocol_frozen_before_training": _bool(protocol_frozen_before_training),
        "evaluation_used_for_training": _bool(evaluation_used_for_training),
        "unresolved_overlap_count": _integer(unresolved_overlap_count),
    }
    return _record_with_identity(
        record,
        id_field="leakage_report_id",
        hash_field="content_hash",
        prefix="workspace_training_leakage_",
    )


build_workspace_training_leakage_report = build_training_recommendation_leakage_report


def paired_percentile_bootstrap(
    baseline_successes: Sequence[int],
    treatment_successes: Sequence[int],
    *,
    seed: str,
    replicate_count: int = TRAINING_BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    """Recompute the specified deterministic paired percentile bootstrap."""

    baseline = list(baseline_successes)
    treatment = list(treatment_successes)
    if not baseline or len(baseline) != len(treatment):
        raise TrainingRecommendationContractError("task_ids_arm_mismatch")
    if replicate_count != TRAINING_BOOTSTRAP_REPLICATES:
        raise TrainingRecommendationContractError("bootstrap_mismatch")
    seed_text = _string(seed)
    n = len(baseline)
    draws: list[float] = []
    for replicate in range(replicate_count):
        base_total = 0
        treat_total = 0
        for draw in range(n):
            digest = hashlib.sha256(
                f"{seed_text}:{replicate}:{draw}".encode()
            ).digest()
            index = int.from_bytes(digest, "big", signed=False) % n
            base_total += baseline[index]
            treat_total += treatment[index]
        draws.append((treat_total - base_total) / n)
    draws.sort()
    lower = draws[249]
    upper = draws[9_749]
    return {
        "schema_version": PAIRED_BOOTSTRAP_SCHEMA_VERSION,
        "algorithm": "paired_percentile_bootstrap",
        "replicate_count": replicate_count,
        "seed": seed_text,
        "confidence_level": TRAINING_BOOTSTRAP_CONFIDENCE_LEVEL,
        "interval": "two_sided_percentile",
        "lower_rank": 250,
        "upper_rank": 9_750,
        "lower_bound": lower,
        "upper_bound": upper,
        "draw_rule": "unsigned_int(SHA256(UTF8(seed + ':' + replicate + ':' + draw))) mod N",
    }


compute_paired_percentile_bootstrap = paired_percentile_bootstrap
paired_bootstrap = paired_percentile_bootstrap


def _validate_protocol(record: Mapping[str, object], *, check_identity: bool = True) -> None:
    _exact_keys(
        record,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "conformance_marker",
            "registration",
            "publishable_release",
            "training_identity",
            "common_inputs",
            "manifests",
            "matching",
            "evaluation",
            "bootstrap",
            "leakage_method",
            "result_schemas",
            "protocol_id",
            "content_hash",
        },
    )
    if record.get("schema_version") != WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    evidence_class = record.get("evidence_class")
    if evidence_class not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    origin = record.get("evidence_origin")
    expected_origin = _evidence_origin(evidence_class)
    if origin != expected_origin:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    marker = record.get("conformance_marker")
    if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        if marker not in CONFORMANCE_FIXTURE_MARKER_ALLOWLIST:
            raise TrainingRecommendationContractError("non_qualifying_evidence_class")
    elif marker is not None:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    registration = _mapping(record.get("registration"))
    _exact_keys(
        registration,
        {"registered_at", "registered_before_training", "post_registration_change"},
    )
    _string(registration.get("registered_at"))
    if not _bool(registration.get("registered_before_training")):
        raise TrainingRecommendationContractError("protocol_not_preregistered")
    if _bool(registration.get("post_registration_change")):
        raise TrainingRecommendationContractError("post_registration_change")
    _publishable_release(record.get("publishable_release"))
    identity = _mapping(record.get("training_identity"))
    _exact_keys(
        identity,
        {
            "model",
            "tokenizer",
            "training_system",
            "training_code",
            "environment",
            "hyperparameters",
            "seed",
            "schedule",
            "stopping_rules",
            "exclusion_rules",
        },
    )
    for value in identity.values():
        _safe_object(value)
    _safe_object(record.get("common_inputs"))
    manifests = _mapping(record.get("manifests"))
    _exact_keys(manifests, {"control", "release"})
    control = _normalize_manifest_reference(manifests.get("control"), "control")
    release = _normalize_manifest_reference(manifests.get("release"), "release")
    if control["manifest_kind"] != "control" or release["manifest_kind"] != "release":
        raise TrainingRecommendationContractError("evidence_malformed")
    matching = _mapping(record.get("matching"))
    _exact_keys(matching, {"unit", "selection_rule", "tolerance"})
    if matching.get("unit") != "training_record_replacement":
        raise TrainingRecommendationContractError("evidence_malformed")
    tolerance = matching.get("tolerance")
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
        raise TrainingRecommendationContractError("evidence_malformed")
    if not math.isclose(float(tolerance), TRAINING_COUNT_TOLERANCE):
        raise TrainingRecommendationContractError("evidence_malformed")
    _safe_object(matching.get("selection_rule"))
    evaluation = _mapping(record.get("evaluation"))
    _exact_keys(evaluation, {"benchmark", "sealed_split", "ordered_task_ids", "scoring_code_hash", "metric"})
    benchmark = _mapping(evaluation.get("benchmark"))
    _exact_keys(benchmark, {"suite_id", "suite_version"})
    _identifier(benchmark.get("suite_id"))
    _string(benchmark.get("suite_version"))
    split = _mapping(evaluation.get("sealed_split"))
    _exact_keys(split, {"split_id", "split_hash"})
    _identifier(split.get("split_id"))
    _hash(split.get("split_hash"))
    tasks = [_identifier(item) for item in _sequence(evaluation.get("ordered_task_ids"))]
    if not tasks:
        raise TrainingRecommendationContractError("evidence_malformed")
    if len(set(tasks)) != len(tasks):
        raise TrainingRecommendationContractError("task_ids_duplicate")
    _hash(evaluation.get("scoring_code_hash"))
    metric = _mapping(evaluation.get("metric"))
    _exact_keys(metric, {"name", "outcome_type", "direction"})
    if dict(metric) != {
        "name": "task_success_rate",
        "outcome_type": "binary",
        "direction": "higher_is_better",
    }:
        raise TrainingRecommendationContractError("evidence_malformed")
    bootstrap = _mapping(record.get("bootstrap"))
    _exact_keys(
        bootstrap,
        {
            "schema_version",
            "algorithm",
            "replicate_count",
            "seed",
            "confidence_level",
            "interval",
            "lower_rank",
            "upper_rank",
            "relative_lower_bound_threshold",
            "draw_rule",
        },
    )
    if (
        bootstrap.get("schema_version") != PAIRED_BOOTSTRAP_SCHEMA_VERSION
        or bootstrap.get("algorithm") != "paired_percentile_bootstrap"
        or bootstrap.get("replicate_count") != TRAINING_BOOTSTRAP_REPLICATES
        or bootstrap.get("confidence_level") != TRAINING_BOOTSTRAP_CONFIDENCE_LEVEL
        or bootstrap.get("interval") != "two_sided_percentile"
        or bootstrap.get("lower_rank") != 250
        or bootstrap.get("upper_rank") != 9_750
        or bootstrap.get("relative_lower_bound_threshold") != TRAINING_RELATIVE_GAIN_THRESHOLD
        or bootstrap.get("draw_rule")
        != "unsigned_int(SHA256(UTF8(seed + ':' + replicate + ':' + draw))) mod N"
    ):
        raise TrainingRecommendationContractError("bootstrap_mismatch")
    _string(bootstrap.get("seed"))
    leakage_method = _mapping(record.get("leakage_method"))
    _exact_keys(leakage_method, {"method_id", "method_hash"})
    _identifier(leakage_method.get("method_id"))
    _hash(leakage_method.get("method_hash"))
    schemas = _mapping(record.get("result_schemas"))
    _exact_keys(
        schemas,
        {"protocol", "baseline", "treatment", "evaluation", "paired_results", "leakage", "result"},
    )
    for value in schemas.values():
        _string(value)
    expected_schemas = {
        "protocol": WORKSPACE_TRAINING_PROTOCOL_SCHEMA_VERSION,
        "baseline": WORKSPACE_TRAINING_ARM_SCHEMA_VERSION,
        "treatment": WORKSPACE_TRAINING_ARM_SCHEMA_VERSION,
        "evaluation": WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION,
        "paired_results": WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION,
        "leakage": WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION,
        "result": TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION,
    }
    if dict(schemas) != expected_schemas:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    if check_identity:
        _assert_identity(
            record,
            id_field="protocol_id",
            hash_field="content_hash",
            prefix="workspace_training_protocol_",
        )


def validate_training_recommendation_protocol_record(record: Mapping[str, object]) -> None:
    _validate_protocol(_mapping(record))


validate_workspace_training_protocol_record = validate_training_recommendation_protocol_record
validate_training_protocol_record = validate_training_recommendation_protocol_record


def _validate_arm(record: Mapping[str, object], *, check_identity: bool = True) -> None:
    _exact_keys(
        record,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "arm",
            "protocol_reference",
            "training_identity",
            "common_inputs",
            "training_manifest",
            "replacement",
            "optional_observations",
            "arm_manifest_id",
            "content_hash",
        },
    )
    if record.get("schema_version") != WORKSPACE_TRAINING_ARM_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    if record.get("arm") not in {"baseline", "treatment"}:
        raise TrainingRecommendationContractError("evidence_malformed")
    _validate_protocol_reference_record(_mapping(record.get("protocol_reference")))
    _safe_object(record.get("training_identity"))
    _safe_object(record.get("common_inputs"))
    manifest = _mapping(record.get("training_manifest"))
    _exact_keys(manifest, {"manifest_id", "content_hash", "record_hashes", "record_count"})
    _identifier(manifest.get("manifest_id"))
    _hash(manifest.get("content_hash"))
    records = [_string(item) for item in _sequence(manifest.get("record_hashes"))]
    if not records or len(set(records)) != len(records):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    if _integer(manifest.get("record_count")) != len(records):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    if manifest.get("content_hash") != _hash_value(
        {"arm": record["arm"], "record_hashes": records}
    ):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    replacement = _mapping(record.get("replacement"))
    _exact_keys(
        replacement,
        {
            "removed_control_record_hashes",
            "inserted_release_record_hashes",
            "removed_record_count",
            "inserted_record_count",
        },
    )
    removed = [_string(item) for item in _sequence(replacement.get("removed_control_record_hashes"))]
    inserted = [_string(item) for item in _sequence(replacement.get("inserted_release_record_hashes"))]
    if len(set(removed)) != len(removed) or len(set(inserted)) != len(inserted):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    if _integer(replacement.get("removed_record_count")) != len(removed) or _integer(
        replacement.get("inserted_record_count")
    ) != len(inserted):
        raise TrainingRecommendationContractError("manifest_membership_mismatch")
    _mapping(record.get("optional_observations"))
    if record.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if record.get("evidence_origin") != _evidence_origin(record.get("evidence_class")):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if check_identity:
        _assert_identity(
            record,
            id_field="arm_manifest_id",
            hash_field="content_hash",
            prefix=f"workspace_training_{record['arm']}_",
        )


def validate_training_recommendation_arm_record(record: Mapping[str, object]) -> None:
    _validate_arm(_mapping(record))


validate_workspace_training_arm_record = validate_training_recommendation_arm_record
validate_training_arm_manifest_record = validate_training_recommendation_arm_record


def _validate_evaluation(record: Mapping[str, object], *, check_identity: bool = True) -> None:
    _exact_keys(
        record,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "protocol_reference",
            "benchmark",
            "sealed_split",
            "ordered_task_ids",
            "scoring_code_hash",
            "result_schema_version",
            "evaluation_id",
            "content_hash",
        },
    )
    if record.get("schema_version") != WORKSPACE_TRAINING_EVALUATION_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    _validate_protocol_reference_record(_mapping(record.get("protocol_reference")))
    benchmark = _mapping(record.get("benchmark"))
    _exact_keys(benchmark, {"suite_id", "suite_version"})
    _identifier(benchmark.get("suite_id"))
    _string(benchmark.get("suite_version"))
    split = _mapping(record.get("sealed_split"))
    _exact_keys(split, {"split_id", "split_hash"})
    _identifier(split.get("split_id"))
    _hash(split.get("split_hash"))
    tasks = [_identifier(item) for item in _sequence(record.get("ordered_task_ids"))]
    if len(set(tasks)) != len(tasks):
        raise TrainingRecommendationContractError("task_ids_duplicate")
    _hash(record.get("scoring_code_hash"))
    _string(record.get("result_schema_version"))
    if record.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if record.get("evidence_origin") != _evidence_origin(record.get("evidence_class")):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if check_identity:
        _assert_identity(
            record,
            id_field="evaluation_id",
            hash_field="content_hash",
            prefix="workspace_training_evaluation_",
        )


def validate_training_recommendation_evaluation_record(record: Mapping[str, object]) -> None:
    _validate_evaluation(_mapping(record))


validate_workspace_training_evaluation_record = validate_training_recommendation_evaluation_record
validate_training_evaluation_manifest_record = validate_training_recommendation_evaluation_record


def _validate_paired(record: Mapping[str, object], *, check_identity: bool = True) -> None:
    _exact_keys(
        record,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "protocol_reference",
            "evaluation_reference",
            "results",
            "reported_statistics",
            "result_schema_version",
            "paired_results_id",
            "content_hash",
        },
    )
    if record.get("schema_version") != WORKSPACE_TRAINING_PAIRED_RESULTS_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    _validate_protocol_reference_record(_mapping(record.get("protocol_reference")))
    evaluation_ref = _mapping(record.get("evaluation_reference"))
    _exact_keys(evaluation_ref, {"evaluation_id", "evaluation_hash"})
    _identifier(evaluation_ref.get("evaluation_id"))
    _hash(evaluation_ref.get("evaluation_hash"))
    rows = _sequence(record.get("results"))
    if not rows:
        raise TrainingRecommendationContractError("evidence_malformed")
    seen: set[str] = set()
    for row in rows:
        item = _mapping(row)
        _exact_keys(item, {"task_id", "baseline_success", "treatment_success"})
        task_id = _identifier(item.get("task_id"))
        if task_id in seen:
            raise TrainingRecommendationContractError("task_ids_duplicate")
        seen.add(task_id)
        for key in ("baseline_success", "treatment_success"):
            outcome = item.get(key)
            if outcome not in {0, 1} or isinstance(outcome, bool):
                raise TrainingRecommendationContractError("non_binary_outcome")
    reported = _mapping(record.get("reported_statistics"))
    for key in ("baseline_success_rate", "treatment_success_rate"):
        value = reported.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise TrainingRecommendationContractError("calculation_mismatch")
    _string(record.get("result_schema_version"))
    if record.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if record.get("evidence_origin") != _evidence_origin(record.get("evidence_class")):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if check_identity:
        _assert_identity(
            record,
            id_field="paired_results_id",
            hash_field="content_hash",
            prefix="workspace_training_paired_",
        )


def validate_training_recommendation_paired_results_record(record: Mapping[str, object]) -> None:
    _validate_paired(_mapping(record))


validate_workspace_training_paired_results_record = validate_training_recommendation_paired_results_record
validate_paired_results_record = validate_training_recommendation_paired_results_record


def _validate_leakage(record: Mapping[str, object], *, check_identity: bool = True) -> None:
    _exact_keys(
        record,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "protocol_reference",
            "evaluation_reference",
            "sealed_split_hash",
            "scoring_code_hash",
            "leakage_method",
            "protocol_frozen_before_training",
            "evaluation_used_for_training",
            "unresolved_overlap_count",
            "leakage_report_id",
            "content_hash",
        },
    )
    if record.get("schema_version") != WORKSPACE_TRAINING_LEAKAGE_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    _validate_protocol_reference_record(_mapping(record.get("protocol_reference")))
    evaluation_ref = _mapping(record.get("evaluation_reference"))
    _exact_keys(evaluation_ref, {"evaluation_id", "evaluation_hash"})
    _identifier(evaluation_ref.get("evaluation_id"))
    _hash(evaluation_ref.get("evaluation_hash"))
    _hash(record.get("sealed_split_hash"))
    _hash(record.get("scoring_code_hash"))
    method = _mapping(record.get("leakage_method"))
    _exact_keys(method, {"method_id", "method_hash"})
    _identifier(method.get("method_id"))
    _hash(method.get("method_hash"))
    _bool(record.get("protocol_frozen_before_training"))
    _bool(record.get("evaluation_used_for_training"))
    if _integer(record.get("unresolved_overlap_count")) < 0:
        raise TrainingRecommendationContractError("evidence_malformed")
    if record.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if record.get("evidence_origin") != _evidence_origin(record.get("evidence_class")):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    if check_identity:
        _assert_identity(
            record,
            id_field="leakage_report_id",
            hash_field="content_hash",
            prefix="workspace_training_leakage_",
        )


def validate_training_recommendation_leakage_record(record: Mapping[str, object]) -> None:
    _validate_leakage(_mapping(record))


validate_workspace_training_leakage_record = validate_training_recommendation_leakage_record
validate_leakage_report_record = validate_training_recommendation_leakage_record


def _validate_protocol_reference(
    supplied: Mapping[str, object], protocol: Mapping[str, object]
) -> None:
    if supplied.get("protocol_id") != protocol.get("protocol_id") or supplied.get(
        "protocol_hash"
    ) != protocol.get("content_hash"):
        raise _TrainingFailure("protocol_identity_mismatch")


def _failure_result(
    *,
    reason_code: str,
    insufficient: bool,
    evidence_class: str = "unknown",
    protocol: Mapping[str, object] | None = None,
    evidence_manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if reason_code not in TRAINING_REASON_CODES:
        reason_code = "evidence_malformed"
    status = "insufficient_evidence" if insufficient else "invalid_experiment"
    if reason_code in {"non_qualifying_evidence_class", "evidence_class_mismatch"}:
        status = "invalid_experiment"
    protocol_reference = None
    experiment_id = None
    publishable_release = None
    if isinstance(protocol, Mapping):
        protocol_reference = {
            "protocol_id": protocol.get("protocol_id"),
            "protocol_hash": protocol.get("content_hash"),
        }
        experiment_id = protocol.get("protocol_id")
        try:
            candidate_release = protocol.get("publishable_release")
            if isinstance(candidate_release, Mapping):
                publishable_release = _publishable_release(candidate_release)
        except TrainingRecommendationContractError:
            publishable_release = None
    return _build_result(
        evidence_class=evidence_class,
        evidence_origin=(
            _evidence_origin(evidence_class)
            if evidence_class in TRAINING_EVIDENCE_CLASSES
            else "unknown"
        ),
        experiment_id=experiment_id,
        protocol_reference=protocol_reference,
        publishable_release=publishable_release,
        evidence_manifest=evidence_manifest,
        decision_status=status,
        reason_codes=[reason_code],
        evaluation=None,
        bootstrap=None,
        conformance=None,
    )


def _build_result(
    *,
    evidence_class: str,
    evidence_origin: str,
    experiment_id: object,
    protocol_reference: Mapping[str, object] | None,
    publishable_release: Mapping[str, object] | None,
    evidence_manifest: Mapping[str, object] | None,
    decision_status: str,
    reason_codes: Sequence[str],
    evaluation: Mapping[str, object] | None,
    bootstrap: Mapping[str, object] | None,
    conformance: Mapping[str, object] | None,
) -> dict[str, object]:
    codes = list(dict.fromkeys(reason_codes))
    for code in codes:
        if code not in TRAINING_REASON_CODES:
            raise TrainingRecommendationContractError("evidence_malformed")
    core: dict[str, object] = {
        "schema_version": TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION,
        "evidence_class": evidence_class,
        "evidence_origin": evidence_origin,
        "experiment_id": experiment_id,
        "protocol_reference": protocol_reference,
        "publishable_release": (
            None if publishable_release is None else dict(publishable_release)
        ),
        "evidence_manifest": evidence_manifest,
        "decision": {
            "status": decision_status,
            "reason_codes": codes,
            "reasons": [_REASON_TEXT.get(code, "bounded training evidence decision") for code in codes],
        },
        "evaluation": None if evaluation is None else dict(evaluation),
        "bootstrap": None if bootstrap is None else dict(bootstrap),
        "conformance": None if conformance is None else dict(conformance),
        "status": decision_status,
    }
    result = _record_with_identity(
        core,
        id_field="result_id",
        hash_field="content_hash",
        prefix="training_recommendation_",
    )
    return result


def _classify_validation_failure(exc: TrainingRecommendationContractError) -> bool:
    return exc.reason_code in {
        "evidence_missing",
        "evidence_unreadable",
        "evidence_malformed",
        "evidence_unknown_version",
        "content_hash_mismatch",
    }


def evaluate_training_recommendation(
    *,
    protocol: Mapping[str, object] | None,
    baseline: Mapping[str, object] | None,
    treatment: Mapping[str, object] | None,
    evaluation: Mapping[str, object] | None,
    paired_results: Mapping[str, object] | None,
    leakage: Mapping[str, object] | None,
    expected_evidence_class: str | None = None,
    evidence_manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Verify an imported experiment and return a bounded decision."""

    if any(item is None for item in (protocol, baseline, treatment, evaluation, paired_results, leakage)):
        return _failure_result(reason_code="evidence_missing", insufficient=True)
    assert protocol is not None and baseline is not None and treatment is not None
    assert evaluation is not None and paired_results is not None and leakage is not None
    evidence_class = protocol.get("evidence_class", "unknown")
    if expected_evidence_class is not None and evidence_class != expected_evidence_class:
        return _failure_result(
            reason_code="evidence_class_mismatch",
            insufficient=False,
            evidence_class=str(evidence_class),
            protocol=protocol,
            evidence_manifest=evidence_manifest,
        )
    try:
        # Validate structure first without content-address identity checks.  A
        # semantic mutation receives its specific bounded reason; the final
        # identity pass still rejects the changed bytes.
        _validate_protocol(protocol, check_identity=False)
        _validate_arm(baseline, check_identity=False)
        _validate_arm(treatment, check_identity=False)
        _validate_evaluation(evaluation, check_identity=False)
        _validate_paired(paired_results, check_identity=False)
        _validate_leakage(leakage, check_identity=False)
        if evidence_class not in TRAINING_EVIDENCE_CLASSES:
            raise _TrainingFailure("evidence_class_mismatch")
        expected_origin = _evidence_origin(evidence_class)
        if protocol.get("evidence_origin") != expected_origin:
            raise _TrainingFailure("evidence_class_mismatch")
        if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
            # The origin is part of the immutable protocol, so changing only
            # the label can never promote a fixture to real evidence.
            if protocol.get("evidence_origin") != expected_origin:
                raise _TrainingFailure("non_qualifying_evidence_class")
        elif evidence_class != EXTERNAL_EXPERIMENT_EVIDENCE_CLASS:
            raise _TrainingFailure("non_qualifying_evidence_class")

        _validate_protocol_reference(_mapping(baseline["protocol_reference"]), protocol)
        _validate_protocol_reference(_mapping(treatment["protocol_reference"]), protocol)
        _validate_protocol_reference(_mapping(evaluation["protocol_reference"]), protocol)
        _validate_protocol_reference(_mapping(paired_results["protocol_reference"]), protocol)
        _validate_protocol_reference(_mapping(leakage["protocol_reference"]), protocol)
        if baseline.get("arm") != "baseline" or treatment.get("arm") != "treatment":
            raise _TrainingFailure("task_ids_arm_mismatch")
        if baseline.get("evidence_class") != evidence_class or treatment.get("evidence_class") != evidence_class:
            raise _TrainingFailure("evidence_class_mismatch")
        if evaluation.get("evidence_class") != evidence_class or paired_results.get("evidence_class") != evidence_class or leakage.get("evidence_class") != evidence_class:
            raise _TrainingFailure("evidence_class_mismatch")
        if any(
            record.get("evidence_origin") != expected_origin
            for record in (baseline, treatment, evaluation, paired_results, leakage)
        ):
            raise _TrainingFailure("evidence_class_mismatch")

        protocol_identity = _mapping(protocol["training_identity"])
        if _hash_value(baseline["training_identity"]) != _hash_value(protocol_identity) or _hash_value(
            treatment["training_identity"]
        ) != _hash_value(protocol_identity):
            raise _TrainingFailure("training_identity_mismatch")
        if _hash_value(baseline["training_identity"]) != _hash_value(treatment["training_identity"]):
            raise _TrainingFailure("training_identity_mismatch")
        if _hash_value(baseline["common_inputs"]) != _hash_value(protocol["common_inputs"]) or _hash_value(
            treatment["common_inputs"]
        ) != _hash_value(protocol["common_inputs"]):
            raise _TrainingFailure("common_inputs_mismatch")

        manifests = _mapping(protocol["manifests"])
        control = _mapping(manifests["control"])
        release = _mapping(manifests["release"])
        base_manifest = _mapping(baseline["training_manifest"])
        treatment_manifest = _mapping(treatment["training_manifest"])
        if base_manifest.get("record_hashes") != control.get("record_hashes"):
            raise _TrainingFailure("control_manifest_mismatch")
        removed = list(_sequence(_mapping(baseline["replacement"])["removed_control_record_hashes"]))
        treatment_removed = list(_sequence(_mapping(treatment["replacement"])["removed_control_record_hashes"]))
        inserted = list(_sequence(_mapping(treatment["replacement"])["inserted_release_record_hashes"]))
        baseline_inserted = list(_sequence(_mapping(baseline["replacement"])["inserted_release_record_hashes"]))
        if removed != treatment_removed or baseline_inserted:
            raise _TrainingFailure("manifest_membership_mismatch")
        control_records = list(_sequence(control["record_hashes"]))
        release_records = list(_sequence(release["record_hashes"]))
        if any(item not in control_records for item in removed) or any(
            item not in release_records for item in inserted
        ):
            raise _TrainingFailure("manifest_membership_mismatch")
        if len(set(removed).intersection(inserted)):
            raise _TrainingFailure("manifest_membership_mismatch")
        removed_count = len(removed)
        inserted_count = len(inserted)
        if removed_count <= 0 or inserted_count <= 0:
            raise _TrainingFailure("record_count_not_positive")
        if abs(inserted_count - removed_count) / removed_count > TRAINING_COUNT_TOLERANCE:
            raise _TrainingFailure("record_count_tolerance_exceeded")
        expected_treatment = [item for item in control_records if item not in removed] + inserted
        if list(_sequence(treatment_manifest["record_hashes"])) != expected_treatment:
            raise _TrainingFailure("manifest_membership_mismatch")
        if control.get("manifest_id") != manifests["control"].get("manifest_id") or control.get(
            "content_hash"
        ) != manifests["control"].get("content_hash"):
            raise _TrainingFailure("control_manifest_mismatch")
        if release.get("manifest_id") != manifests["release"].get("manifest_id") or release.get(
            "content_hash"
        ) != manifests["release"].get("content_hash"):
            raise _TrainingFailure("release_manifest_mismatch")
        protocol_evaluation = _mapping(protocol["evaluation"])
        for key in ("benchmark", "sealed_split", "ordered_task_ids", "scoring_code_hash"):
            if evaluation.get(key) != protocol_evaluation.get(key):
                raise _TrainingFailure("protocol_identity_mismatch")
        protocol_schemas = _mapping(protocol["result_schemas"])
        if evaluation.get("result_schema_version") != protocol_schemas["paired_results"]:
            raise _TrainingFailure("protocol_identity_mismatch")
        if paired_results.get("result_schema_version") != protocol_schemas["result"]:
            raise _TrainingFailure("protocol_identity_mismatch")
        evaluation_ref = _mapping(paired_results["evaluation_reference"])
        if evaluation_ref.get("evaluation_id") != evaluation.get("evaluation_id") or evaluation_ref.get(
            "evaluation_hash"
        ) != evaluation.get("content_hash"):
            raise _TrainingFailure("protocol_identity_mismatch")
        leakage_ref = _mapping(leakage["evaluation_reference"])
        if leakage_ref.get("evaluation_id") != evaluation.get("evaluation_id") or leakage_ref.get(
            "evaluation_hash"
        ) != evaluation.get("content_hash"):
            raise _TrainingFailure("leakage_identity_mismatch")
        if leakage.get("sealed_split_hash") != protocol_evaluation["sealed_split"]["split_hash"] or leakage.get(
            "scoring_code_hash"
        ) != protocol_evaluation["scoring_code_hash"]:
            raise _TrainingFailure("leakage_identity_mismatch")
        if leakage.get("leakage_method") != protocol["leakage_method"]:
            raise _TrainingFailure("leakage_identity_mismatch")
        if not leakage.get("protocol_frozen_before_training"):
            raise _TrainingFailure("leakage_protocol_not_frozen")
        if leakage.get("evaluation_used_for_training"):
            raise _TrainingFailure("leakage_evaluation_used_for_training")
        if leakage.get("unresolved_overlap_count") != 0:
            raise _TrainingFailure("leakage_overlap_unresolved")

        expected_tasks = list(_sequence(protocol_evaluation["ordered_task_ids"]))
        actual_tasks = [
            _mapping(row)["task_id"] for row in _sequence(paired_results["results"])
        ]
        if len(actual_tasks) < len(expected_tasks):
            raise _TrainingFailure("task_ids_missing")
        if len(actual_tasks) > len(expected_tasks):
            raise _TrainingFailure("task_ids_extra")
        if len(set(actual_tasks)) != len(actual_tasks):
            raise _TrainingFailure("task_ids_duplicate")
        if actual_tasks != expected_tasks:
            if set(actual_tasks) == set(expected_tasks):
                raise _TrainingFailure("task_ids_reordered")
            missing = set(expected_tasks) - set(actual_tasks)
            raise _TrainingFailure("task_ids_missing" if missing else "task_ids_extra")
        rows = [_mapping(row) for row in _sequence(paired_results["results"])]
        baseline_successes = [int(row["baseline_success"]) for row in rows]
        treatment_successes = [int(row["treatment_success"]) for row in rows]
        baseline_rate = sum(baseline_successes) / len(rows)
        treatment_rate = sum(treatment_successes) / len(rows)
        if baseline_rate <= 0:
            raise _TrainingFailure("baseline_rate_not_positive")
        reported = _mapping(paired_results["reported_statistics"])
        if not math.isclose(float(reported["baseline_success_rate"]), baseline_rate, rel_tol=0, abs_tol=1e-12) or not math.isclose(
            float(reported["treatment_success_rate"]), treatment_rate, rel_tol=0, abs_tol=1e-12
        ):
            raise _TrainingFailure("calculation_mismatch")
        bootstrap_spec = _mapping(protocol["bootstrap"])
        bootstrap = paired_percentile_bootstrap(
            baseline_successes,
            treatment_successes,
            seed=str(bootstrap_spec["seed"]),
            replicate_count=int(bootstrap_spec["replicate_count"]),
        )
        absolute_delta = treatment_rate - baseline_rate
        relative_delta = absolute_delta / baseline_rate
        lower_bound = bootstrap["lower_bound"]
        if not isinstance(lower_bound, (int, float)) or isinstance(lower_bound, bool):
            raise _TrainingFailure("bootstrap_mismatch")
        relative_lower_bound = float(lower_bound) / baseline_rate
        evaluation_result = {
            "baseline_success_rate": baseline_rate,
            "treatment_success_rate": treatment_rate,
            "absolute_delta": absolute_delta,
            "relative_delta": relative_delta,
            "task_count": len(rows),
            "metric": "task_success_rate",
        }
        bootstrap_result = {
            **bootstrap,
            "relative_lower_bound": relative_lower_bound,
        }
        # A final identity pass proves that the imported bytes have not been
        # changed after their semantic fields were checked.
        _validate_protocol(protocol)
        _validate_arm(baseline)
        _validate_arm(treatment)
        _validate_evaluation(evaluation)
        _validate_paired(paired_results)
        _validate_leakage(leakage)
        decision_status = (
            "training_recommended"
            if relative_lower_bound > TRAINING_RELATIVE_GAIN_THRESHOLD
            else "no_detected_meaningful_gain"
        )
        if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
            return _build_result(
                evidence_class=evidence_class,
                evidence_origin="repository_conformance",
                experiment_id=protocol["protocol_id"],
                protocol_reference=_mapping(protocol["protocol_reference"])
                if "protocol_reference" in protocol
                else {
                    "protocol_id": protocol["protocol_id"],
                    "protocol_hash": protocol["content_hash"],
                },
                publishable_release=_mapping(protocol["publishable_release"]),
                evidence_manifest=evidence_manifest,
                decision_status="protocol_conformance_passed",
                reason_codes=["protocol_conformance_passed"],
                evaluation=evaluation_result,
                bootstrap=bootstrap_result,
                conformance={"status": "passed", "numerical_status": decision_status},
            )
        return _build_result(
            evidence_class=evidence_class,
            evidence_origin="external_submitter",
            experiment_id=protocol["protocol_id"],
            protocol_reference={
                "protocol_id": protocol["protocol_id"],
                "protocol_hash": protocol["content_hash"],
            },
            publishable_release=_mapping(protocol["publishable_release"]),
            evidence_manifest=evidence_manifest,
            decision_status=decision_status,
            reason_codes=[decision_status],
            evaluation=evaluation_result,
            bootstrap=bootstrap_result,
            conformance=None,
        )
    except _TrainingFailure as exc:
        return _failure_result(
            reason_code=exc.reason_code,
            insufficient=exc.insufficient,
            evidence_class=str(evidence_class),
            protocol=protocol,
            evidence_manifest=evidence_manifest,
        )
    except TrainingRecommendationContractError as exc:
        return _failure_result(
            reason_code=exc.reason_code,
            insufficient=_classify_validation_failure(exc),
            evidence_class=str(evidence_class),
            protocol=protocol,
            evidence_manifest=evidence_manifest,
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return _failure_result(
            reason_code="evidence_malformed",
            insufficient=True,
            evidence_class=str(evidence_class),
            protocol=protocol,
            evidence_manifest=evidence_manifest,
        )


evaluate_workspace_training_recommendation = evaluate_training_recommendation
verify_training_recommendation = evaluate_training_recommendation


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise TrainingRecommendationContractError("evidence_unreadable") from None
    if not isinstance(value, Mapping):
        raise TrainingRecommendationContractError("evidence_malformed")
    return value


def _file_reference(kind: str, path: Path, record: Mapping[str, object]) -> dict[str, object]:
    name = path.name
    if not _ARTIFACT_NAME_RE.fullmatch(name):
        raise TrainingRecommendationContractError("evidence_file_hash_mismatch")
    raw = path.read_bytes()
    return {
        "kind": kind,
        "path": name,
        "schema_version": record.get("schema_version"),
        "content_hash": record.get("content_hash"),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "byte_count": len(raw),
    }


def build_training_experiment_evidence_manifest(
    *,
    protocol_path: Path,
    baseline_path: Path,
    treatment_path: Path,
    evaluation_path: Path,
    paired_results_path: Path,
    leakage_path: Path,
    records: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Bind imported file bytes without persisting their absolute paths."""

    supplied = records or {
        "protocol": _load_json_mapping(protocol_path),
        "baseline": _load_json_mapping(baseline_path),
        "treatment": _load_json_mapping(treatment_path),
        "evaluation": _load_json_mapping(evaluation_path),
        "paired_results": _load_json_mapping(paired_results_path),
        "leakage": _load_json_mapping(leakage_path),
    }
    paths = {
        "protocol": protocol_path,
        "baseline": baseline_path,
        "treatment": treatment_path,
        "evaluation": evaluation_path,
        "paired_results": paired_results_path,
        "leakage": leakage_path,
    }
    files = [
        _file_reference(kind, paths[kind], _mapping(supplied[kind]))
        for kind in ("protocol", "baseline", "treatment", "evaluation", "paired_results", "leakage")
    ]
    protocol = _mapping(supplied["protocol"])
    record = {
        "schema_version": WORKSPACE_TRAINING_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "evidence_class": protocol.get("evidence_class"),
        "evidence_origin": protocol.get("evidence_origin"),
        "protocol_reference": {
            "protocol_id": protocol.get("protocol_id"),
            "protocol_hash": protocol.get("content_hash"),
        },
        "files": files,
    }
    result = _record_with_identity(
        record,
        id_field="evidence_manifest_id",
        hash_field="content_hash",
        prefix="workspace_training_evidence_",
    )
    validate_training_experiment_evidence_manifest_record(result)
    return result


def validate_training_experiment_evidence_manifest_record(
    record: Mapping[str, object],
) -> None:
    value = _mapping(record)
    _exact_keys(
        value,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "protocol_reference",
            "files",
            "evidence_manifest_id",
            "content_hash",
        },
    )
    if value.get("schema_version") != WORKSPACE_TRAINING_EVIDENCE_MANIFEST_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    if value.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    expected_origin = (
        "external_submitter"
        if value.get("evidence_class") == EXTERNAL_EXPERIMENT_EVIDENCE_CLASS
        else "repository_conformance"
    )
    if value.get("evidence_origin") != expected_origin:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    _validate_protocol_reference_record(_mapping(value.get("protocol_reference")))
    files = _sequence(value.get("files"))
    expected_kinds = ["protocol", "baseline", "treatment", "evaluation", "paired_results", "leakage"]
    if len(files) != len(expected_kinds):
        raise TrainingRecommendationContractError("evidence_malformed")
    for raw_file, expected_kind in zip(files, expected_kinds):
        file_record = _mapping(raw_file)
        _exact_keys(
            file_record,
            {"kind", "path", "schema_version", "content_hash", "sha256", "byte_count"},
        )
        if file_record.get("kind") != expected_kind:
            raise TrainingRecommendationContractError("evidence_malformed")
        path = _string(file_record.get("path"))
        if not _ARTIFACT_NAME_RE.fullmatch(path):
            raise TrainingRecommendationContractError("evidence_malformed")
        _string(file_record.get("schema_version"))
        _hash(file_record.get("content_hash"))
        _hash(file_record.get("sha256"))
        if _integer(file_record.get("byte_count")) < 0:
            raise TrainingRecommendationContractError("evidence_malformed")
    _assert_identity(
        value,
        id_field="evidence_manifest_id",
        hash_field="content_hash",
        prefix="workspace_training_evidence_",
    )


def import_training_recommendation_evidence(
    *,
    protocol_path: Path,
    baseline_path: Path,
    treatment_path: Path,
    evaluation_path: Path,
    paired_results_path: Path,
    leakage_path: Path,
    output_path: Path | None = None,
    evidence_class: str = EXTERNAL_EXPERIMENT_EVIDENCE_CLASS,
) -> dict[str, object]:
    """Import six ordinary JSON files and write only a sanitized result."""

    paths = {
        "protocol": protocol_path,
        "baseline": baseline_path,
        "treatment": treatment_path,
        "evaluation": evaluation_path,
        "paired_results": paired_results_path,
        "leakage": leakage_path,
    }
    try:
        records = {kind: _load_json_mapping(path) for kind, path in paths.items()}
        manifest = build_training_experiment_evidence_manifest(
            protocol_path=protocol_path,
            baseline_path=baseline_path,
            treatment_path=treatment_path,
            evaluation_path=evaluation_path,
            paired_results_path=paired_results_path,
            leakage_path=leakage_path,
            records=records,
        )
        result = evaluate_training_recommendation(
            protocol=records["protocol"],
            baseline=records["baseline"],
            treatment=records["treatment"],
            evaluation=records["evaluation"],
            paired_results=records["paired_results"],
            leakage=records["leakage"],
            expected_evidence_class=evidence_class,
            evidence_manifest=manifest,
        )
    except TrainingRecommendationContractError as exc:
        result = _failure_result(
            reason_code=exc.reason_code,
            insufficient=_classify_validation_failure(exc),
            evidence_class="unknown",
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        result = _failure_result(reason_code="evidence_unreadable", insufficient=True)
    if output_path is not None:
        output_path.write_text(
            json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


build_training_evidence_manifest = build_training_experiment_evidence_manifest
import_workspace_training_evidence = import_training_recommendation_evidence
import_training_experiment = import_training_recommendation_evidence
import_training_evidence = import_training_recommendation_evidence


def validate_training_recommendation_result_record(record: Mapping[str, object]) -> None:
    value = _mapping(record)
    _exact_keys(
        value,
        {
            "schema_version",
            "evidence_class",
            "evidence_origin",
            "experiment_id",
            "protocol_reference",
            "publishable_release",
            "evidence_manifest",
            "decision",
            "evaluation",
            "bootstrap",
            "conformance",
            "result_id",
            "content_hash",
            "status",
        },
    )
    if value.get("schema_version") != TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    decision = _mapping(value.get("decision"))
    _exact_keys(decision, {"status", "reason_codes", "reasons"})
    status = decision.get("status")
    if status not in TRAINING_RESULT_STATUSES or value.get("status") != status:
        raise TrainingRecommendationContractError("evidence_malformed")
    evidence_class = value.get("evidence_class")
    if evidence_class in TRAINING_EVIDENCE_CLASSES and value.get(
        "evidence_origin"
    ) != _evidence_origin(evidence_class):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    codes = [_string(item) for item in _sequence(decision.get("reason_codes"))]
    if not codes or any(code not in TRAINING_REASON_CODES for code in codes):
        raise TrainingRecommendationContractError("evidence_malformed")
    reasons = [_string(item) for item in _sequence(decision.get("reasons"))]
    if len(reasons) != len(codes):
        raise TrainingRecommendationContractError("evidence_malformed")
    if status in {"training_recommended", "no_detected_meaningful_gain", "protocol_conformance_passed"}:
        if not isinstance(value.get("evaluation"), Mapping) or not isinstance(value.get("bootstrap"), Mapping):
            raise TrainingRecommendationContractError("evidence_malformed")
    else:
        if value.get("evaluation") is not None or value.get("bootstrap") is not None:
            raise TrainingRecommendationContractError("evidence_malformed")
    publishable_release = value.get("publishable_release")
    if publishable_release is not None:
        _publishable_release(publishable_release)
    if evidence_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        conformance = _mapping(value.get("conformance"))
        if (
            status != "protocol_conformance_passed"
            or conformance.get("status") != "passed"
        ):
            raise TrainingRecommendationContractError("non_qualifying_evidence_class")
    elif evidence_class == EXTERNAL_EXPERIMENT_EVIDENCE_CLASS:
        if status == "protocol_conformance_passed":
            raise TrainingRecommendationContractError("non_qualifying_evidence_class")
        if value.get("conformance") is not None:
            raise TrainingRecommendationContractError("evidence_class_mismatch")
    elif evidence_class not in {None, "unknown"}:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    _assert_identity(
        value,
        id_field="result_id",
        hash_field="content_hash",
        prefix="training_recommendation_",
    )


validate_training_result_record = validate_training_recommendation_result_record


def write_training_recommendation_result(
    output_path: Path, result: Mapping[str, object]
) -> Path:
    """Write a standalone validated training decision."""

    validate_training_recommendation_result_record(result)
    output_path.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_training_recommendation_result(input_path: Path) -> dict[str, object]:
    value = _load_json_mapping(input_path)
    validate_training_recommendation_result_record(value)
    return dict(value)


def _binding_record(binding: object) -> Mapping[str, object]:
    if hasattr(binding, "to_record"):
        binding = binding.to_record()  # type: ignore[union-attr]
    return _mapping(binding)


def _gate_identity(binding: object) -> dict[str, object]:
    if all(hasattr(binding, name) for name in ("subject_id", "subject_hash", "binding_hash", "release_pack_hash")):
        qualified_binding: Any = binding
        return {
            "subject_id": _identifier(qualified_binding.subject_id),
            "subject_hash": _hash(qualified_binding.subject_hash),
            "binding_hash": _hash(qualified_binding.binding_hash),
            "release_pack_hash": _hash(qualified_binding.release_pack_hash),
        }
    value = _binding_record(binding)
    subject = _mapping(value.get("artifact_subject"), "evidence_malformed")
    return {
        "subject_id": _identifier(subject.get("subject_id")),
        "subject_hash": _hash(subject.get("subject_hash")),
        "binding_hash": _hash(value.get("binding_hash")),
        "release_pack_hash": _hash(value.get("release_pack_hash")),
    }


def _publishable_release_matches_binding(
    release: Mapping[str, object], binding: object
) -> bool:
    binding_record = _binding_record(binding)
    subject = _mapping(binding_record.get("artifact_subject"))
    return all(
        release.get(field) == expected
        for field, expected in (
            ("subject_id", subject.get("subject_id")),
            ("subject_hash", subject.get("subject_hash")),
            ("release_pack_hash", binding_record.get("release_pack_hash")),
            ("domain_pack_reference", binding_record.get("domain_pack_reference")),
        )
    )


def _training_gate_status(result: Mapping[str, object]) -> str:
    decision_status = str(_mapping(result["decision"])["status"])
    if (
        result["evidence_class"] == EXTERNAL_EXPERIMENT_EVIDENCE_CLASS
        and decision_status == "training_recommended"
    ):
        return "passed"
    if decision_status == "insufficient_evidence":
        return "insufficient_evidence"
    return "failed"


def build_training_recommendation_gate(
    *, binding: object, result: Mapping[str, object]
) -> dict[str, object]:
    """Adapt a pure training result to the cumulative qualification gate."""

    validate_training_recommendation_result_record(result)
    status = str(_mapping(result["decision"])["status"])
    gate_status = _training_gate_status(result)
    passed = gate_status == "passed"
    identity = _gate_identity(binding)
    release = _mapping(result.get("publishable_release"), "publishable_release_invalid")
    if not _publishable_release_matches_binding(release, binding):
        raise TrainingRecommendationContractError("publishable_release_invalid")
    protocol_reference = result.get("protocol_reference")
    protocol_record = {
        "status": "passed" if passed else gate_status,
        "protocol_reference": protocol_reference,
    }
    experiment_record = {
        "status": "passed" if passed else gate_status,
        "result_id": result["result_id"],
        "result_hash": result["content_hash"],
    }
    leakage_record = {
        "status": "passed" if passed else gate_status,
        "result_id": result["result_id"],
    }
    return {
        "schema_version": TRAINING_RECOMMENDATION_GATE_SCHEMA_VERSION,
        "status": gate_status,
        **identity,
        "evidence_class": result["evidence_class"],
        "result": dict(result),
        "evidence_ids": [
            str(result["result_id"]),
            str(protocol_reference.get("protocol_id"))
            if isinstance(protocol_reference, Mapping)
            else str(result["result_id"]),
        ],
        "verification": {
            "status": "passed" if passed else gate_status,
            "result_id": result["result_id"],
            "result_hash": result["content_hash"],
            "decision_status": status,
        },
        "protocol": protocol_record,
        "experiment": experiment_record,
        "leakage": leakage_record,
    }


build_qualification_training_recommendation_gate = build_training_recommendation_gate


def validate_training_recommendation_gate_record(record: Mapping[str, object]) -> None:
    value = _mapping(record)
    _exact_keys(
        value,
        {
            "schema_version",
            "status",
            "subject_id",
            "subject_hash",
            "binding_hash",
            "release_pack_hash",
            "evidence_class",
            "evidence_ids",
            "result",
            "verification",
            "protocol",
            "experiment",
            "leakage",
        },
    )
    if value.get("schema_version") != TRAINING_RECOMMENDATION_GATE_SCHEMA_VERSION:
        raise TrainingRecommendationContractError("evidence_unknown_version")
    if value.get("status") not in {"passed", "failed", "insufficient_evidence"}:
        raise TrainingRecommendationContractError("evidence_malformed")
    _identifier(value.get("subject_id"))
    _hash(value.get("subject_hash"))
    _hash(value.get("binding_hash"))
    _hash(value.get("release_pack_hash"))
    if value.get("evidence_class") not in TRAINING_EVIDENCE_CLASSES:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    evidence_ids = [_string(item) for item in _sequence(value.get("evidence_ids"))]
    if not evidence_ids:
        raise TrainingRecommendationContractError("evidence_missing")
    result = _mapping(value.get("result"))
    validate_training_recommendation_result_record(result)
    if value.get("evidence_class") != result.get("evidence_class"):
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    expected_status = _training_gate_status(result)
    if value.get("status") != expected_status:
        raise TrainingRecommendationContractError("evidence_non_passing")
    release = _mapping(result.get("publishable_release"), "publishable_release_invalid")
    if any(
        release.get(field) != value.get(field)
        for field in ("subject_id", "subject_hash", "release_pack_hash")
    ):
        raise TrainingRecommendationContractError("publishable_release_invalid")
    verification = _mapping(value.get("verification"))
    _exact_keys(
        verification,
        {"status", "result_id", "result_hash", "decision_status"},
    )
    if (
        verification.get("status") != expected_status
        or verification.get("result_id") != result.get("result_id")
        or verification.get("result_hash") != result.get("content_hash")
        or verification.get("decision_status")
        != _mapping(result.get("decision"))["status"]
    ):
        raise TrainingRecommendationContractError("evidence_non_passing")
    protocol = _mapping(value.get("protocol"))
    _exact_keys(protocol, {"status", "protocol_reference"})
    if protocol.get("status") != expected_status or protocol.get(
        "protocol_reference"
    ) != result.get("protocol_reference"):
        raise TrainingRecommendationContractError("protocol_identity_mismatch")
    experiment = _mapping(value.get("experiment"))
    _exact_keys(experiment, {"status", "result_id", "result_hash"})
    if (
        experiment.get("status") != expected_status
        or experiment.get("result_id") != result.get("result_id")
        or experiment.get("result_hash") != result.get("content_hash")
    ):
        raise TrainingRecommendationContractError("evidence_non_passing")
    leakage = _mapping(value.get("leakage"))
    _exact_keys(leakage, {"status", "result_id"})
    if (
        leakage.get("status") != expected_status
        or leakage.get("result_id") != result.get("result_id")
    ):
        raise TrainingRecommendationContractError("evidence_non_passing")
    expected_evidence_ids = [str(result["result_id"])]
    protocol_reference = result.get("protocol_reference")
    if isinstance(protocol_reference, Mapping):
        expected_evidence_ids.append(str(protocol_reference["protocol_id"]))
    if evidence_ids != expected_evidence_ids:
        raise TrainingRecommendationContractError("evidence_identity_mismatch")


def build_training_recommendation_qualification_evidence(
    *,
    binding: object,
    release_candidate_evidence: Mapping[str, object],
    publishability_gate: Mapping[str, object],
    result: Mapping[str, object],
    evidence_class: str = "real",
) -> dict[str, object]:
    """Compose cumulative evidence without changing lower-level artifacts."""

    gate = build_training_recommendation_gate(binding=binding, result=result)
    result_class = result["evidence_class"]
    if result_class == CONFORMANCE_FIXTURE_EVIDENCE_CLASS:
        if evidence_class not in {"conformance_fixture", "fixture", "synthetic_fixture"}:
            raise TrainingRecommendationContractError("non_qualifying_evidence_class")
    elif result_class != EXTERNAL_EXPERIMENT_EVIDENCE_CLASS:
        raise TrainingRecommendationContractError("evidence_class_mismatch")
    release = _mapping(result.get("publishable_release"), "publishable_release_invalid")
    if not _publishable_release_matches_binding(release, binding):
        raise TrainingRecommendationContractError("publishable_release_invalid")
    identity = _gate_identity(binding)
    publishability = _mapping(publishability_gate)
    if publishability.get("status") != "passed" or any(
        publishability.get(field) != identity[field]
        for field in ("subject_id", "subject_hash", "binding_hash", "release_pack_hash")
    ):
        raise TrainingRecommendationContractError("publishable_release_invalid")
    rc_gates = _mapping(release_candidate_evidence.get("gates"))
    gates = dict(rc_gates)
    gates["publishability"] = dict(publishability)
    gates["training_recommendation"] = gate
    binding_record = dict(_binding_record(binding))
    qualification = (
        "training_recommended" if gate["status"] == "passed" else "publishable"
    )
    return {
        "schema_version": "qualification_evidence_v1",
        "qualification": qualification,
        "evidence_class": evidence_class,
        "binding": binding_record,
        "gates": gates,
        "evidence_graph": list(_sequence(release_candidate_evidence.get("evidence_graph", binding_record.get("evidence_graph", [])))),
    }


build_training_recommendation_evidence = build_training_recommendation_qualification_evidence


__all__ = [
    "BOOTSTRAP_REPLICATE_COUNT",
    "CONFORMANCE_FIXTURE_EVIDENCE_CLASS",
    "CONFORMANCE_FIXTURE_MARKER",
    "CONFORMANCE_FIXTURE_MARKER_ALLOWLIST",
    "EXTERNAL_EXPERIMENT_EVIDENCE_CLASS",
    "MEANINGFUL_GAIN_THRESHOLD",
    "PAIRED_BOOTSTRAP_SCHEMA_VERSION",
    "SAMPLE_COUNT_TOLERANCE",
    "TRAINING_BOOTSTRAP_REPLICATES",
    "TRAINING_COUNT_TOLERANCE",
    "TRAINING_EVIDENCE_CLASSES",
    "TRAINING_REASON_CODES",
    "TRAINING_RECOMMENDATION_GATE_SCHEMA_VERSION",
    "TRAINING_RECOMMENDATION_RESULT_SCHEMA_VERSION",
    "TRAINING_RELATIVE_GAIN_THRESHOLD",
    "TrainingRecommendationContractError",
    "build_training_evidence_manifest",
    "build_training_experiment_evidence_manifest",
    "build_training_protocol",
    "build_training_recommendation_arm_manifest",
    "build_training_recommendation_evaluation_manifest",
    "build_training_recommendation_gate",
    "build_training_recommendation_leakage_report",
    "build_training_recommendation_paired_results",
    "build_training_recommendation_protocol",
    "build_training_recommendation_qualification_evidence",
    "build_workspace_training_protocol",
    "compute_paired_percentile_bootstrap",
    "evaluate_training_recommendation",
    "evaluate_workspace_training_recommendation",
    "import_training_evidence",
    "import_training_experiment",
    "import_training_recommendation_evidence",
    "load_training_recommendation_result",
    "paired_percentile_bootstrap",
    "validate_training_experiment_evidence_manifest_record",
    "validate_training_recommendation_arm_record",
    "validate_training_recommendation_evaluation_record",
    "validate_training_recommendation_gate_record",
    "validate_training_recommendation_leakage_record",
    "validate_training_recommendation_paired_results_record",
    "validate_training_recommendation_protocol_record",
    "validate_training_recommendation_result_record",
    "write_training_recommendation_result",
]
