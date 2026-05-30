from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from synthesis.contracts import validate_profile_decision_report_record


PROFILE_DECISION_REPORT_SCHEMA_VERSION = "profile_decision_report_v1"
PROFILE_SLICE_DIMENSIONS = (
    "run_profile_id",
    "generation_mode",
    "run_profile_schema_version",
)


@dataclass(frozen=True)
class DecisionThresholds:
    async_candidate_count: int = 100
    async_runtime_seconds: float = 600.0
    semantic_duplicate_min_candidates: int = 100
    semantic_duplicate_exact_rate: float = 0.1
    mvp_min_success_rate: float = 0.5
    mvp_min_executable_rate: float = 0.8
    mvp_max_infrastructure_rejection_rate: float = 0.0
    mvp_max_source_policy_rejection_rate: float = 0.0


@dataclass(frozen=True)
class ProfileDecisionInputs:
    manifest: Mapping[str, Any]
    quality_report: Mapping[str, Any]
    manifest_path: Path
    quality_report_path: Path
    parent_comparison: Mapping[str, Any] | None = None
    parent_comparison_path: Path | None = None
    runtime_seconds: float | None = None


def build_profile_decision_report(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    manifest_path: Path = Path("manifest.json"),
    quality_report_path: Path = Path("quality_report.json"),
    parent_comparison: Mapping[str, Any] | None = None,
    parent_comparison_path: Path | None = None,
    runtime_seconds: float | None = None,
    thresholds: DecisionThresholds | None = None,
) -> dict[str, object]:
    thresholds = thresholds or DecisionThresholds()
    observed = _observed_metrics(
        manifest=manifest,
        quality_report=quality_report,
        runtime_seconds=runtime_seconds,
    )
    report: dict[str, object] = {
        "schema_version": PROFILE_DECISION_REPORT_SCHEMA_VERSION,
        "dataset_version": _string_value(manifest.get("dataset_version"), "manifest.dataset_version"),
        "profile": _profile_summary(manifest),
        "inputs": {
            "manifest_path": manifest_path.name,
            "quality_report_path": quality_report_path.name,
            "parent_comparison_path": parent_comparison_path.name
            if parent_comparison_path is not None and parent_comparison is not None
            else None,
        },
        "observed": observed,
        "thresholds": asdict(thresholds),
        "decisions": {
            "async_orchestration": _async_decision(observed, thresholds),
            "semantic_duplicate_detection": _semantic_duplicate_decision(
                observed,
                thresholds,
            ),
            "mvp_quality_floor": _mvp_quality_decision(observed, thresholds),
        },
    }
    validate_profile_decision_report_record(report)
    return report


def load_profile_decision_inputs(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    parent_comparison_path: Path | None = None,
    runtime_seconds: float | None = None,
) -> ProfileDecisionInputs:
    parent_comparison = (
        json.loads(parent_comparison_path.read_text(encoding="utf-8"))
        if parent_comparison_path is not None
        else None
    )
    return ProfileDecisionInputs(
        manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
        quality_report=json.loads(quality_report_path.read_text(encoding="utf-8")),
        manifest_path=manifest_path,
        quality_report_path=quality_report_path,
        parent_comparison=parent_comparison,
        parent_comparison_path=parent_comparison_path,
        runtime_seconds=runtime_seconds,
    )


def write_profile_decision_report(
    *,
    manifest_path: Path,
    quality_report_path: Path,
    parent_comparison_path: Path | None = None,
    runtime_seconds: float | None = None,
    output_path: Path | None = None,
    thresholds: DecisionThresholds | None = None,
) -> Path:
    inputs = load_profile_decision_inputs(
        manifest_path=manifest_path,
        quality_report_path=quality_report_path,
        parent_comparison_path=parent_comparison_path,
        runtime_seconds=runtime_seconds,
    )
    report = build_profile_decision_report(
        manifest=inputs.manifest,
        quality_report=inputs.quality_report,
        manifest_path=inputs.manifest_path,
        quality_report_path=inputs.quality_report_path,
        parent_comparison=inputs.parent_comparison,
        parent_comparison_path=inputs.parent_comparison_path,
        runtime_seconds=inputs.runtime_seconds,
        thresholds=thresholds,
    )
    destination = output_path or manifest_path.parent / "profile_decision_report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _observed_metrics(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    runtime_seconds: float | None,
) -> dict[str, object]:
    counts = _mapping_value(quality_report.get("counts"), "quality_report.counts")
    rates = _mapping_value(quality_report.get("rates"), "quality_report.rates")
    rejection_causes = _mapping_value(
        quality_report.get("rejection_causes"),
        "quality_report.rejection_causes",
    )
    total_candidates = _int_value(counts.get("total"), "quality_report.counts.total")
    accepted = _int_value(counts.get("accepted"), "quality_report.counts.accepted")
    rejected = _int_value(counts.get("rejected"), "quality_report.counts.rejected")
    manifest_total = _int_value(manifest.get("accepted_count"), "manifest.accepted_count") + _int_value(
        manifest.get("rejected_count"),
        "manifest.rejected_count",
    )
    if total_candidates != manifest_total:
        raise ValueError(
            "quality_report.counts.total must equal manifest accepted_count + rejected_count"
        )

    exact_duplicate_count = _optional_int(
        rejection_causes.get("quality_duplicate"),
        "quality_report.rejection_causes.quality_duplicate",
    )
    infrastructure_rejection_count = _optional_int(
        rejection_causes.get("infrastructure_error"),
        "quality_report.rejection_causes.infrastructure_error",
    )
    source_policy_rejection_count = _optional_int(
        rejection_causes.get("source_policy_rejected"),
        "quality_report.rejection_causes.source_policy_rejected",
    )

    observed_runtime = None if runtime_seconds is None else float(runtime_seconds)
    return {
        "total_candidates": total_candidates,
        "accepted": accepted,
        "rejected": rejected,
        "success_rate": _optional_number(rates.get("success_rate")),
        "executable_rate": _optional_number(rates.get("executable_rate")),
        "exact_duplicate_count": exact_duplicate_count,
        "exact_duplicate_rate": _rate(exact_duplicate_count, total_candidates),
        "infrastructure_rejection_count": infrastructure_rejection_count,
        "infrastructure_rejection_rate": _rate(infrastructure_rejection_count, total_candidates),
        "source_policy_rejection_count": source_policy_rejection_count,
        "source_policy_rejection_rate": _rate(source_policy_rejection_count, total_candidates),
        "runtime_seconds": observed_runtime,
        "profile_slice_count": _profile_slice_count(quality_report),
    }


def _async_decision(
    observed: Mapping[str, object],
    thresholds: DecisionThresholds,
) -> dict[str, object]:
    reasons: list[str] = []
    triggered_by: list[str] = []
    total_candidates = _int_value(observed.get("total_candidates"), "observed.total_candidates")
    runtime_seconds = observed.get("runtime_seconds")
    if total_candidates >= thresholds.async_candidate_count:
        triggered_by.append("total_candidates")
        reasons.append(
            f"total_candidates {total_candidates} is at or above "
            f"async_candidate_count {thresholds.async_candidate_count}"
        )
    else:
        reasons.append(
            f"total_candidates {total_candidates} is below "
            f"async_candidate_count {thresholds.async_candidate_count}"
        )
    if isinstance(runtime_seconds, (int, float)) and not isinstance(runtime_seconds, bool):
        if float(runtime_seconds) >= thresholds.async_runtime_seconds:
            triggered_by.append("runtime_seconds")
            reasons.append(
                f"runtime_seconds {float(runtime_seconds)} is at or above "
                f"async_runtime_seconds {thresholds.async_runtime_seconds}"
            )
        else:
            reasons.append(
                f"runtime_seconds {float(runtime_seconds)} is below "
                f"async_runtime_seconds {thresholds.async_runtime_seconds}"
            )
    else:
        reasons.append("runtime_seconds is unavailable")
    return {
        "status": "activate" if triggered_by else "defer",
        "reasons": reasons,
        "triggered_by": triggered_by,
    }


def _semantic_duplicate_decision(
    observed: Mapping[str, object],
    thresholds: DecisionThresholds,
) -> dict[str, object]:
    reasons: list[str] = []
    triggered_by: list[str] = []
    total_candidates = _int_value(observed.get("total_candidates"), "observed.total_candidates")
    exact_duplicate_rate = _number_value(
        observed.get("exact_duplicate_rate"),
        "observed.exact_duplicate_rate",
    )
    if total_candidates < thresholds.semantic_duplicate_min_candidates:
        reasons.append(
            f"total_candidates {total_candidates} is below "
            f"semantic_duplicate_min_candidates {thresholds.semantic_duplicate_min_candidates}"
        )
        return {"status": "defer", "reasons": reasons, "triggered_by": triggered_by}

    triggered_by.append("total_candidates")
    reasons.append(
        f"total_candidates {total_candidates} is at or above "
        f"semantic_duplicate_min_candidates {thresholds.semantic_duplicate_min_candidates}"
    )
    if exact_duplicate_rate >= thresholds.semantic_duplicate_exact_rate:
        triggered_by.append("exact_duplicate_rate")
        reasons.append(
            f"exact_duplicate_rate {exact_duplicate_rate} is at or above "
            f"semantic_duplicate_exact_rate {thresholds.semantic_duplicate_exact_rate}"
        )
        return {
            "status": "activate",
            "reasons": reasons,
            "triggered_by": triggered_by,
        }

    reasons.append(
        f"exact_duplicate_rate {exact_duplicate_rate} is below "
        f"semantic_duplicate_exact_rate {thresholds.semantic_duplicate_exact_rate}"
    )
    return {"status": "defer", "reasons": reasons, "triggered_by": []}


def _mvp_quality_decision(
    observed: Mapping[str, object],
    thresholds: DecisionThresholds,
) -> dict[str, object]:
    required_rates = {
        "success_rate": observed.get("success_rate"),
        "executable_rate": observed.get("executable_rate"),
    }
    missing = [
        name
        for name, value in required_rates.items()
        if not isinstance(value, (int, float)) or isinstance(value, bool)
    ]
    if missing:
        return {
            "status": "insufficient_evidence",
            "reasons": [f"{name} is unavailable or malformed" for name in missing],
            "triggered_by": [],
        }

    checks = (
        (
            "success_rate",
            float(required_rates["success_rate"]),
            "mvp_min_success_rate",
            thresholds.mvp_min_success_rate,
            "at or above",
            lambda observed_value, threshold: observed_value >= threshold,
        ),
        (
            "executable_rate",
            float(required_rates["executable_rate"]),
            "mvp_min_executable_rate",
            thresholds.mvp_min_executable_rate,
            "at or above",
            lambda observed_value, threshold: observed_value >= threshold,
        ),
        (
            "infrastructure_rejection_rate",
            _number_value(
                observed.get("infrastructure_rejection_rate"),
                "observed.infrastructure_rejection_rate",
            ),
            "mvp_max_infrastructure_rejection_rate",
            thresholds.mvp_max_infrastructure_rejection_rate,
            "at or below",
            lambda observed_value, threshold: observed_value <= threshold,
        ),
        (
            "source_policy_rejection_rate",
            _number_value(
                observed.get("source_policy_rejection_rate"),
                "observed.source_policy_rejection_rate",
            ),
            "mvp_max_source_policy_rejection_rate",
            thresholds.mvp_max_source_policy_rejection_rate,
            "at or below",
            lambda observed_value, threshold: observed_value <= threshold,
        ),
    )

    reasons: list[str] = []
    triggered_by: list[str] = []
    failed = False
    for metric, observed_value, threshold_name, threshold_value, phrase, predicate in checks:
        if predicate(observed_value, threshold_value):
            triggered_by.append(metric)
            reasons.append(
                f"{metric} {observed_value} is {phrase} {threshold_name} {threshold_value}"
            )
        else:
            failed = True
            reasons.append(
                f"{metric} {observed_value} does not meet {threshold_name} {threshold_value}"
            )
    return {
        "status": "failed" if failed else "passed",
        "reasons": reasons,
        "triggered_by": [] if failed else triggered_by,
    }


def _profile_summary(manifest: Mapping[str, Any]) -> dict[str, object] | None:
    profile = manifest.get("run_profile")
    if not isinstance(profile, Mapping):
        return None
    allowed_keys = (
        "schema_version",
        "profile_id",
        "generation_mode",
        "target_candidate_count",
        "config_hash",
    )
    return {key: profile[key] for key in allowed_keys if key in profile}


def _profile_slice_count(quality_report: Mapping[str, Any]) -> int:
    slices = quality_report.get("slices")
    if not isinstance(slices, Mapping):
        return 0
    return sum(
        len(values)
        for dimension in PROFILE_SLICE_DIMENSIONS
        if isinstance((values := slices.get(dimension)), Mapping)
    )


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


def _optional_int(raw: object, path: str) -> int:
    if raw is None:
        return 0
    return _int_value(raw, path)


def _number_value(raw: object, path: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{path} must be a number")
    return float(raw)


def _optional_number(raw: object) -> float | None:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    return float(raw)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
