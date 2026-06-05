from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthesis.contracts import validate_dataset_release_report_record


DATASET_RELEASE_REPORT_SCHEMA_VERSION = "dataset_release_report_v1"
REQUIRED_RELEASE_ARTIFACTS = (
    "samples",
    "rejections",
    "quality_report",
    "evaluation_report",
    "profile_decision_report",
)


@dataclass(frozen=True)
class DatasetReleaseInputs:
    manifest: Mapping[str, Any]
    quality_report: Mapping[str, Any]
    evaluation_report: Mapping[str, Any] | None
    profile_decision_report: Mapping[str, Any] | None
    manifest_path: Path
    quality_report_path: Path
    evaluation_report_path: Path | None = None
    profile_decision_report_path: Path | None = None


def build_dataset_release_report(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any] | None,
    profile_decision_report: Mapping[str, Any] | None,
    manifest_path: Path = Path("manifest.json"),
    quality_report_path: Path = Path("quality_report.json"),
    evaluation_report_path: Path | None = Path("evaluation_report.json"),
    profile_decision_report_path: Path | None = Path("profile_decision_report.json"),
) -> dict[str, object]:
    profile = _profile_summary(manifest)
    observed = _observed_summary(
        manifest=manifest,
        quality_report=quality_report,
        evaluation_report=evaluation_report,
        profile_decision_report=profile_decision_report,
    )
    report: dict[str, object] = {
        "schema_version": DATASET_RELEASE_REPORT_SCHEMA_VERSION,
        "dataset_version": _string_value(
            manifest.get("dataset_version"),
            "manifest.dataset_version",
        ),
        "profile": profile,
        "inputs": {
            "manifest_path": manifest_path.name,
            "quality_report_path": quality_report_path.name,
            "evaluation_report_path": (
                evaluation_report_path.name
                if evaluation_report_path is not None
                else "evaluation_report.json"
            ),
            "profile_decision_report_path": (
                profile_decision_report_path.name
                if profile_decision_report_path is not None
                else "profile_decision_report.json"
            ),
        },
        "observed": observed,
        "decisions": {
            "dataset_release": _dataset_release_decision(
                profile=profile,
                manifest=manifest,
                quality_report=quality_report,
                evaluation_report=evaluation_report,
                profile_decision_report=profile_decision_report,
                observed=observed,
            )
        },
        "release_artifacts": _release_artifacts(manifest),
    }
    validate_dataset_release_report_record(report)
    return report


def load_dataset_release_inputs(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    evaluation_report_path: Path | None = None,
    profile_decision_report_path: Path | None = None,
) -> DatasetReleaseInputs:
    evaluation_report = (
        json.loads(evaluation_report_path.read_text(encoding="utf-8"))
        if evaluation_report_path is not None
        else None
    )
    profile_decision_report = (
        json.loads(profile_decision_report_path.read_text(encoding="utf-8"))
        if profile_decision_report_path is not None
        else None
    )
    return DatasetReleaseInputs(
        manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
        quality_report=json.loads(quality_report_path.read_text(encoding="utf-8")),
        evaluation_report=evaluation_report,
        profile_decision_report=profile_decision_report,
        manifest_path=manifest_path,
        quality_report_path=quality_report_path,
        evaluation_report_path=evaluation_report_path,
        profile_decision_report_path=profile_decision_report_path,
    )


def write_dataset_release_report(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    evaluation_report_path: Path | None = None,
    profile_decision_report_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    inputs = load_dataset_release_inputs(
        manifest_path=manifest_path,
        quality_report_path=quality_report_path,
        evaluation_report_path=evaluation_report_path,
        profile_decision_report_path=profile_decision_report_path,
    )
    report = build_dataset_release_report(
        manifest=inputs.manifest,
        quality_report=inputs.quality_report,
        evaluation_report=inputs.evaluation_report,
        profile_decision_report=inputs.profile_decision_report,
        manifest_path=inputs.manifest_path,
        quality_report_path=inputs.quality_report_path,
        evaluation_report_path=inputs.evaluation_report_path,
        profile_decision_report_path=inputs.profile_decision_report_path,
    )
    destination = output_path or manifest_path.parent / "dataset_release_report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _dataset_release_decision(
    *,
    profile: Mapping[str, object],
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any] | None,
    profile_decision_report: Mapping[str, Any] | None,
    observed: Mapping[str, object],
) -> dict[str, object]:
    missing = _missing_evidence(
        manifest=manifest,
        quality_report=quality_report,
        evaluation_report=evaluation_report,
        profile_decision_report=profile_decision_report,
        observed=observed,
    )
    if missing:
        return {
            "status": "insufficient_evidence",
            "reasons": [f"{field} is unavailable or malformed" for field in missing],
            "triggered_by": [],
        }

    profile_purpose = _string_value(profile.get("profile_purpose"), "profile.profile_purpose")
    if profile_purpose != "release_candidate":
        return {
            "status": "ineligible",
            "reasons": [f"profile_purpose {profile_purpose} is not release_candidate"],
            "triggered_by": ["profile_purpose"],
        }

    async_status = _string_value(
        observed.get("async_orchestration_status"),
        "observed.async_orchestration_status",
    )
    semantic_status = _string_value(
        observed.get("semantic_duplicate_detection_status"),
        "observed.semantic_duplicate_detection_status",
    )
    blocked_by = []
    if async_status == "activate":
        blocked_by.append("async_orchestration")
    if semantic_status == "activate":
        blocked_by.append("semantic_duplicate_detection")
    if blocked_by:
        return {
            "status": "blocked",
            "reasons": [
                f"{gate} requires implementation before dataset release"
                for gate in blocked_by
            ],
            "triggered_by": blocked_by,
        }

    failed_by = []
    if observed.get("profile_promotion_status") != "passed":
        failed_by.append("profile_promotion")
    if observed.get("heldout_status") != "passed":
        failed_by.append("heldout_evaluation")
    source_policy_rejection_rate = _number_value(
        observed.get("source_policy_rejection_rate"),
        "observed.source_policy_rejection_rate",
    )
    if source_policy_rejection_rate > 0.0:
        failed_by.append("source_policy_rejection_rate")
    if failed_by:
        return {
            "status": "failed",
            "reasons": [f"{field} did not meet release admission" for field in failed_by],
            "triggered_by": failed_by,
        }

    return {
        "status": "passed",
        "reasons": ["release admission passed"],
        "triggered_by": ["profile_promotion", "heldout_evaluation", "source_policy"],
    }


def _missing_evidence(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any] | None,
    profile_decision_report: Mapping[str, Any] | None,
    observed: Mapping[str, object],
) -> list[str]:
    missing: list[str] = []
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        missing.append("manifest.artifacts")
    else:
        for artifact_key in REQUIRED_RELEASE_ARTIFACTS:
            if not isinstance(artifacts.get(artifact_key), str) or not artifacts.get(artifact_key):
                missing.append(f"manifest.artifacts.{artifact_key}")
    if not isinstance(quality_report.get("counts"), Mapping):
        missing.append("quality_report.counts")
    if not isinstance(quality_report.get("rates"), Mapping):
        missing.append("quality_report.rates")
    if evaluation_report is None:
        missing.append("evaluation_report")
    if profile_decision_report is None:
        missing.append("profile_decision_report")
    for field in (
        "heldout_status",
        "profile_promotion_status",
        "async_orchestration_status",
        "semantic_duplicate_detection_status",
    ):
        if not isinstance(observed.get(field), str) or not str(observed.get(field)).strip():
            missing.append(f"observed.{field}")
    return missing


def _observed_summary(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any] | None,
    profile_decision_report: Mapping[str, Any] | None,
) -> dict[str, object]:
    counts = _mapping_or_empty(quality_report.get("counts"))
    rates = _mapping_or_empty(quality_report.get("rates"))
    rejection_causes = _mapping_or_empty(quality_report.get("rejection_causes"))
    accepted = _optional_int(counts.get("accepted"), manifest.get("accepted_count"))
    rejected = _optional_int(counts.get("rejected"), manifest.get("rejected_count"))
    total = accepted + rejected
    source_policy_rejections = _optional_int(
        rejection_causes.get("source_policy_rejected"),
        0,
    )
    decisions = _mapping_or_empty(
        profile_decision_report.get("decisions")
        if isinstance(profile_decision_report, Mapping)
        else None
    )
    return {
        "accepted": accepted,
        "rejected": rejected,
        "success_rate": _optional_number(rates.get("success_rate"), 0.0),
        "executable_rate": _optional_number(rates.get("executable_rate"), 0.0),
        "source_policy_rejection_rate": source_policy_rejections / total if total else 0.0,
        "heldout_status": _decision_status(evaluation_report, "decision"),
        "profile_promotion_status": _decision_status(decisions, "profile_promotion"),
        "async_orchestration_status": _decision_status(decisions, "async_orchestration"),
        "semantic_duplicate_detection_status": _decision_status(
            decisions,
            "semantic_duplicate_detection",
        ),
    }


def _profile_summary(manifest: Mapping[str, Any]) -> dict[str, object]:
    profile = _mapping_value(manifest.get("run_profile"), "manifest.run_profile")
    allowed_keys = (
        "schema_version",
        "profile_id",
        "generation_mode",
        "profile_purpose",
        "target_candidate_count",
        "config_hash",
    )
    return {key: profile[key] for key in allowed_keys if key in profile}


def _release_artifacts(manifest: Mapping[str, Any]) -> dict[str, object]:
    artifacts = _mapping_or_empty(manifest.get("artifacts"))
    return {
        key: artifacts[key]
        for key in REQUIRED_RELEASE_ARTIFACTS
        if isinstance(artifacts.get(key), str) and artifacts.get(key)
    }


def _decision_status(raw: object, decision_name: str) -> str | None:
    decision_container = _mapping_or_empty(raw)
    decision = _mapping_or_empty(decision_container.get(decision_name))
    status = decision.get("status")
    if isinstance(status, str) and status.strip():
        return status
    return "insufficient_evidence"


def _mapping_value(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be an object")
    return raw


def _mapping_or_empty(raw: object) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _string_value(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return raw


def _number_value(raw: object, path: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{path} must be a number")
    return float(raw)


def _optional_int(primary: object, fallback: object) -> int:
    value = primary if primary is not None else fallback
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _optional_number(primary: object, fallback: float) -> float:
    if isinstance(primary, (int, float)) and not isinstance(primary, bool):
        return float(primary)
    return fallback
