from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    validate_dataset_release_pack_record,
    validate_dataset_release_report_record,
    validate_manifest_record,
    validate_review_resolution_report_record,
)
from synthesis.datasets import (
    build_artifact_hash_record,
    serialize_dataset_manifest,
)
from synthesis.mutation_admission_release import verify_mutation_safe_manifest
from synthesis.mutation_admission_reporting import (
    MUTATION_ADMISSION_REPORT_SCHEMA_VERSION,
    validate_mutation_admission_report,
)


DATASET_RELEASE_PACK_SCHEMA_VERSION = "dataset_release_pack_v2"
LEGACY_DATASET_RELEASE_PACK_SCHEMA_VERSION = "dataset_release_pack_v1"
DATASET_RELEASE_PACK_FILENAME = "dataset_release_pack.json"
REQUIRED_MANIFEST_ARTIFACTS = (
    "samples",
    "rejections",
    "quality_report",
    "evaluation_report",
    "profile_decision_report",
    "dataset_release_report",
)
PACK_ARTIFACT_KEYS = (
    "manifest",
    "samples",
    "rejections",
    "quality_report",
    "evaluation_report",
    "profile_decision_report",
    "dataset_release_report",
)
PROFILE_FIELDS = (
    "schema_version",
    "profile_id",
    "generation_mode",
    "profile_purpose",
    "target_candidate_count",
    "config_hash",
    "generation_contract",
)


@dataclass(frozen=True)
class PostPackManifestAssessment:
    status: str


def build_dataset_release_pack(
    *,
    manifest_path: Path,
    dataset_release_report_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest = _load_canonical_manifest(manifest_path)
    mutation_safe = _is_mutation_safe_manifest(manifest)
    mutation_verification = (
        verify_mutation_safe_manifest(manifest_path)
        if mutation_safe
        else None
    )
    if (
        mutation_verification is not None
        and mutation_verification.get("status") != "passed"
    ):
        reasons = mutation_verification.get("reasons")
        reason_text = (
            "; ".join(str(reason) for reason in reasons)
            if isinstance(reasons, list)
            else "unknown mutation admission failure"
        )
        raise ValueError(
            f"mutation-safe release admission failed: {reason_text}"
        )
    dataset_release_report = _load_mapping(
        dataset_release_report_path,
        "dataset_release_report",
    )
    validate_dataset_release_report_record(dataset_release_report)
    _require_passed_release_report(dataset_release_report)

    artifact_paths = _release_artifact_paths(
        base_dir=base_dir,
        manifest_path=manifest_path,
        dataset_release_report_path=dataset_release_report_path,
        manifest=manifest,
    )
    artifacts = {
        key: build_artifact_hash_record(path).export()
        for key, path in artifact_paths.items()
    }
    dataset_version = _string_value(
        dataset_release_report.get("dataset_version"),
        "dataset_release_report.dataset_version",
    )
    pack: dict[str, object] = {
        "schema_version": (
            DATASET_RELEASE_PACK_SCHEMA_VERSION
            if mutation_safe
            else LEGACY_DATASET_RELEASE_PACK_SCHEMA_VERSION
        ),
        "dataset_version": dataset_version,
        "release_id": _release_id(dataset_version, artifacts),
        "profile": _profile_summary(dataset_release_report),
        "inputs": {
            "manifest_path": manifest_path.name,
            "dataset_release_report_path": dataset_release_report_path.name,
        },
        "artifacts": artifacts,
        "evidence": _evidence(dataset_release_report),
        "verification": _verification_record(
            "passed",
            (
                "all required artifacts are present",
                "artifact hashes are recorded",
                "dataset release admission passed",
            ),
        ),
    }
    if mutation_safe:
        pack["mutation_admission"] = {
            "manifest_schema_version": "dataset_manifest_v2",
            "mode": "enforce",
            "report_schema_version": MUTATION_ADMISSION_REPORT_SCHEMA_VERSION,
            "status": "passed",
        }
    validate_dataset_release_pack_record(pack)
    return pack


def write_dataset_release_pack(
    *,
    manifest_path: Path,
    dataset_release_report_path: Path,
    output_path: Path | None = None,
) -> Path:
    pack = build_dataset_release_pack(
        manifest_path=manifest_path,
        dataset_release_report_path=dataset_release_report_path,
    )
    destination = output_path or manifest_path.parent / DATASET_RELEASE_PACK_FILENAME
    destination.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def verify_dataset_release_pack(pack_path: Path) -> dict[str, object]:
    try:
        pack = _load_mapping(pack_path, "dataset_release_pack")
        validate_dataset_release_pack_record(pack)
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        return _verification_result(
            "insufficient_evidence",
            [f"release pack is unreadable or malformed: {type(exc).__name__}"],
        )

    reasons: list[str] = []
    allowed_post_pack_review_attachment = False
    base_dir = pack_path.parent
    artifacts = _mapping_value(pack.get("artifacts"), "artifacts")
    for key, raw_artifact in artifacts.items():
        artifact = _mapping_value(raw_artifact, f"artifacts.{key}")
        relative_path = _string_value(artifact.get("path"), f"artifacts.{key}.path")
        artifact_path = base_dir / relative_path
        if not artifact_path.exists():
            reasons.append(f"{key} artifact is missing: {relative_path}")
            continue
        current = build_artifact_hash_record(artifact_path)
        expected_hash = _string_value(
            artifact.get("sha256"),
            f"artifacts.{key}.sha256",
        )
        expected_byte_count = _int_value(
            artifact.get("byte_count"),
            f"artifacts.{key}.byte_count",
        )
        manifest_mismatch = (
            current.sha256 != expected_hash
            or current.byte_count != expected_byte_count
        )
        if key == "manifest" and manifest_mismatch:
            assessment = _assess_post_pack_review_resolution_attachment(
                manifest_path=artifact_path,
                expected_hash=expected_hash,
                expected_byte_count=expected_byte_count,
                pack_dataset_version=_string_value(
                    pack.get("dataset_version"),
                    "dataset_version",
                ),
            )
            if assessment.status == "allowed":
                allowed_post_pack_review_attachment = True
                continue
            reasons.append(assessment.status)
        if current.sha256 != expected_hash:
            reasons.append(f"{key} hash mismatch")
        if current.byte_count != expected_byte_count:
            reasons.append(f"{key} byte count mismatch")

    try:
        referenced = _load_referenced_json_artifacts(base_dir, artifacts)
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        return _verification_result(
            "insufficient_evidence",
            [f"referenced JSON artifact is unreadable or malformed: {type(exc).__name__}"],
        )

    reasons.extend(_metadata_mismatch_reasons(pack, referenced))
    reasons.extend(_release_evidence_failure_reasons(pack, referenced))
    mutation_verification: Mapping[str, object] | None = None
    if _is_mutation_safe_pack(pack):
        manifest_artifact = _mapping_value(
            artifacts.get("manifest"),
            "artifacts.manifest",
        )
        mutation_verification = verify_mutation_safe_manifest(
            base_dir
            / _string_value(
                manifest_artifact.get("path"),
                "artifacts.manifest.path",
            )
        )
        if mutation_verification.get("status") != "passed":
            raw_reasons = mutation_verification.get("reasons")
            if isinstance(raw_reasons, list):
                reasons.extend(str(reason) for reason in raw_reasons)
            else:
                reasons.append("mutation-safe release admission failed")
    if reasons:
        return _verification_result(
            "failed",
            reasons,
            mutation_admission=mutation_verification,
        )
    if allowed_post_pack_review_attachment:
        return _verification_result(
            "passed",
            [
                "allowed: manifest raw hash mismatch was exempted for a controlled "
                "post-pack review resolution attachment",
                "all other referenced artifacts match recorded hashes",
                "release evidence is internally consistent",
            ],
            mutation_admission=mutation_verification,
        )
    return _verification_result(
        "passed",
        [
            "all referenced artifacts match recorded hashes",
            "release evidence is internally consistent",
        ],
        mutation_admission=mutation_verification,
    )


def _assess_post_pack_review_resolution_attachment(
    *,
    manifest_path: Path,
    expected_hash: str,
    expected_byte_count: int,
    pack_dataset_version: str,
) -> PostPackManifestAssessment:
    try:
        manifest = _load_mapping(manifest_path, "manifest")
        validate_manifest_record(manifest)
        manifest_dataset_version = _string_value(
            manifest.get("dataset_version"),
            "manifest.dataset_version",
        )
        if manifest_dataset_version != pack_dataset_version:
            return PostPackManifestAssessment("uncontrolled_manifest_drift")

        artifacts = dict(
            _mapping_value(manifest.get("artifacts"), "manifest.artifacts")
        )
    except (
        OSError,
        json.JSONDecodeError,
        ContractValidationError,
        RecursionError,
        ValueError,
    ):
        return PostPackManifestAssessment("invalid_manifest")

    if "review_resolution_report" not in artifacts:
        return PostPackManifestAssessment("uncontrolled_manifest_drift")
    report_name = _string_value(
        artifacts.pop("review_resolution_report"),
        "manifest.artifacts.review_resolution_report",
    )
    try:
        report = _load_mapping(
            manifest_path.parent / report_name,
            "review_resolution_report",
        )
        validate_review_resolution_report_record(report)
    except (
        OSError,
        json.JSONDecodeError,
        ContractValidationError,
        RecursionError,
        ValueError,
    ):
        return PostPackManifestAssessment("invalid_review_report")

    if report.get("dataset_version") != pack_dataset_version:
        return PostPackManifestAssessment("review_dataset_mismatch")

    original_manifest = dict(manifest)
    original_manifest["artifacts"] = artifacts
    original_bytes = serialize_dataset_manifest(original_manifest).encode("utf-8")
    if (
        len(original_bytes) == expected_byte_count
        and "sha256:" + hashlib.sha256(original_bytes).hexdigest() == expected_hash
    ):
        return PostPackManifestAssessment("allowed")
    return PostPackManifestAssessment("uncontrolled_manifest_drift")


def _release_artifact_paths(
    *,
    base_dir: Path,
    manifest_path: Path,
    dataset_release_report_path: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    artifacts = _mapping_value(manifest.get("artifacts"), "manifest.artifacts")
    required_manifest_artifacts = _required_manifest_artifact_keys(manifest)
    missing = [
        key
        for key in required_manifest_artifacts
        if not isinstance(artifacts.get(key), str) or not str(artifacts.get(key)).strip()
    ]
    if missing:
        raise ValueError(f"manifest.artifacts missing required keys: {', '.join(missing)}")
    paths: dict[str, Path] = {
        "manifest": manifest_path,
        "dataset_release_report": dataset_release_report_path,
    }
    for key in (
        "samples",
        "rejections",
        "quality_report",
        "evaluation_report",
        "profile_decision_report",
        *_mutation_admission_artifact_keys(manifest),
    ):
        paths[key] = base_dir / _string_value(artifacts.get(key), f"manifest.artifacts.{key}")
    artifact_keys = [
        *PACK_ARTIFACT_KEYS,
        *_mutation_admission_artifact_keys(manifest),
    ]
    return {key: paths[key] for key in artifact_keys}


def _release_id(
    dataset_version: str,
    artifacts: Mapping[str, object],
) -> str:
    hash_inputs = []
    for key in sorted(artifacts):
        artifact = _mapping_value(artifacts[key], f"artifacts.{key}")
        hash_inputs.append(
            {
                "key": key,
                "sha256": _string_value(artifact.get("sha256"), f"artifacts.{key}.sha256"),
            }
        )
    digest = hashlib.sha256(
        json.dumps(hash_inputs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"{dataset_version}:sha256:{digest}"


def _is_mutation_safe_manifest(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema_version") == "dataset_manifest_v2"


def _is_mutation_safe_pack(pack: Mapping[str, Any]) -> bool:
    return pack.get("schema_version") == DATASET_RELEASE_PACK_SCHEMA_VERSION


def _mutation_admission_artifact_keys(
    manifest: Mapping[str, Any],
) -> tuple[str, ...]:
    return (
        ("mutation_admission_report",)
        if _is_mutation_safe_manifest(manifest)
        else ()
    )


def _required_manifest_artifact_keys(
    manifest: Mapping[str, Any],
) -> list[str]:
    return [
        *REQUIRED_MANIFEST_ARTIFACTS,
        *_mutation_admission_artifact_keys(manifest),
    ]


def _evidence(dataset_release_report: Mapping[str, Any]) -> dict[str, object]:
    observed = _mapping_value(dataset_release_report.get("observed"), "observed")
    decisions = _mapping_value(dataset_release_report.get("decisions"), "decisions")
    dataset_release = _mapping_value(
        decisions.get("dataset_release"),
        "decisions.dataset_release",
    )
    release_completeness = _mapping_value(
        dataset_release_report.get("release_completeness"),
        "release_completeness",
    )
    release_completeness_decision = _mapping_value(
        release_completeness.get("decision"),
        "release_completeness.decision",
    )
    return {
        "accepted": _int_value(observed.get("accepted"), "observed.accepted"),
        "rejected": _int_value(observed.get("rejected"), "observed.rejected"),
        "heldout_status": _string_value(
            observed.get("heldout_status"),
            "observed.heldout_status",
        ),
        "profile_promotion_status": _string_value(
            observed.get("profile_promotion_status"),
            "observed.profile_promotion_status",
        ),
        "dataset_release_status": _string_value(
            dataset_release.get("status"),
            "decisions.dataset_release.status",
        ),
        "release_completeness_status": _string_value(
            release_completeness_decision.get("status"),
            "release_completeness.decision.status",
        ),
        "async_orchestration_status": _string_value(
            observed.get("async_orchestration_status"),
            "observed.async_orchestration_status",
        ),
        "semantic_duplicate_detection_status": _string_value(
            observed.get("semantic_duplicate_detection_status"),
            "observed.semantic_duplicate_detection_status",
        ),
    }


def _profile_summary(dataset_release_report: Mapping[str, Any]) -> dict[str, object]:
    profile = _mapping_value(dataset_release_report.get("profile"), "profile")
    return {field: profile[field] for field in PROFILE_FIELDS if field in profile}


def _require_passed_release_report(dataset_release_report: Mapping[str, Any]) -> None:
    evidence = _evidence(dataset_release_report)
    if evidence["dataset_release_status"] != "passed":
        raise ValueError("dataset_release_report decisions.dataset_release.status must be passed")
    if evidence["release_completeness_status"] != "passed":
        raise ValueError("dataset_release_report release_completeness.decision.status must be passed")


def _load_referenced_json_artifacts(
    base_dir: Path,
    artifacts: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    referenced: dict[str, Mapping[str, Any]] = {}
    json_artifact_keys = [
        "manifest",
        "quality_report",
        "evaluation_report",
        "profile_decision_report",
        "dataset_release_report",
    ]
    if "mutation_admission_report" in artifacts:
        json_artifact_keys.append("mutation_admission_report")
    for key in json_artifact_keys:
        artifact = _mapping_value(artifacts.get(key), f"artifacts.{key}")
        path = base_dir / _string_value(artifact.get("path"), f"artifacts.{key}.path")
        referenced[key] = _load_mapping(path, key)
        if key == "mutation_admission_report":
            validate_mutation_admission_report(referenced[key])
    return referenced


def _metadata_mismatch_reasons(
    pack: Mapping[str, Any],
    referenced: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    pack_dataset_version = _string_value(pack.get("dataset_version"), "dataset_version")
    for key, record in referenced.items():
        dataset_version = record.get("dataset_version")
        if dataset_version != pack_dataset_version:
            reasons.append(f"{key} dataset version mismatch")

    manifest = referenced["manifest"]
    manifest_artifacts = _mapping_value(manifest.get("artifacts"), "manifest.artifacts")
    required_manifest_artifacts = list(REQUIRED_MANIFEST_ARTIFACTS)
    if _is_mutation_safe_pack(pack):
        required_manifest_artifacts.append("mutation_admission_report")
    for key in required_manifest_artifacts:
        if not isinstance(manifest_artifacts.get(key), str) or not manifest_artifacts.get(key):
            reasons.append(f"manifest missing required artifact reference: {key}")

    pack_profile = _profile_core(pack.get("profile"))
    for key, raw_profile in (
        ("manifest", manifest.get("run_profile")),
        ("evaluation_report", referenced["evaluation_report"].get("profile")),
        ("profile_decision_report", referenced["profile_decision_report"].get("profile")),
        ("dataset_release_report", referenced["dataset_release_report"].get("profile")),
    ):
        if raw_profile is None:
            reasons.append(f"{key} profile metadata is missing")
            continue
        profile = _profile_core(raw_profile)
        if "generation_contract" in pack_profile and "generation_contract" not in profile:
            reasons.append(f"{key} profile generation_contract is missing")
        if "generation_contract" in profile and "generation_contract" not in pack_profile:
            reasons.append("pack profile generation_contract is missing")
        for field, value in pack_profile.items():
            if field in profile and profile[field] != value:
                reasons.append(f"{key} profile {field} mismatch")
    return reasons


def _release_evidence_failure_reasons(
    pack: Mapping[str, Any],
    referenced: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    evidence = _mapping_value(pack.get("evidence"), "evidence")
    if evidence.get("dataset_release_status") != "passed":
        reasons.append("dataset release status is not passed")
    if evidence.get("release_completeness_status") != "passed":
        reasons.append("release completeness status is not passed")

    release_report_evidence = _evidence(referenced["dataset_release_report"])
    if release_report_evidence["dataset_release_status"] != "passed":
        reasons.append("dataset release status is not passed")
    if release_report_evidence["release_completeness_status"] != "passed":
        reasons.append("release completeness status is not passed")
    for field, value in release_report_evidence.items():
        if evidence.get(field) != value:
            reasons.append(f"release evidence {field} mismatch")
    return sorted(set(reasons))


def _profile_core(raw: object) -> dict[str, object]:
    profile = _mapping_value(raw, "profile")
    return {field: profile[field] for field in PROFILE_FIELDS if field in profile}


def _verification_record(status: str, reasons: tuple[str, ...] | list[str]) -> dict[str, object]:
    return {"status": status, "reasons": list(reasons)}


def _verification_result(
    status: str,
    reasons: list[str],
    *,
    mutation_admission: Mapping[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "verification": _verification_record(status, reasons)
    }
    if mutation_admission is not None:
        result["mutation_admission"] = dict(mutation_admission)
    return result


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    return _mapping_value(record, label)


def _load_canonical_manifest(path: Path) -> Mapping[str, Any]:
    raw_manifest = path.read_text(encoding="utf-8")
    manifest = _mapping_value(json.loads(raw_manifest), "manifest")
    validate_manifest_record(manifest)
    if raw_manifest != serialize_dataset_manifest(manifest):
        raise ValueError("manifest must use canonical dataset manifest serialization")
    return manifest


def _mapping_value(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be an object")
    return raw


def _string_value(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return raw


def _int_value(raw: object, path: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return raw
