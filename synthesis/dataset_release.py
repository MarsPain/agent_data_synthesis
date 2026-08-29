from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synthesis.contracts import validate_dataset_release_report_record
from synthesis.profile_decisions import evaluation_domain_id, manifest_domain_id
from synthesis.runtime_registry import release_completeness_threshold_record


DATASET_RELEASE_REPORT_SCHEMA_VERSION = "dataset_release_report_v1"
REQUIRED_RELEASE_ARTIFACTS = (
    "samples",
    "rejections",
    "quality_report",
    "evaluation_report",
    "profile_decision_report",
)


@dataclass(frozen=True)
class ReleaseCompletenessThresholds:
    min_accepted_samples: int
    max_rejection_rate: float
    required_task_types: tuple[str, ...]
    required_tool_combinations: tuple[str, ...]
    required_capability_keys: tuple[str, ...] = ()
    minimum_recovery_samples: int = 0
    task_type_aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    recovery_task_type_alias: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "min_accepted_samples": self.min_accepted_samples,
            "max_rejection_rate": self.max_rejection_rate,
            "required_task_types": list(self.required_task_types),
            "required_tool_combinations": list(self.required_tool_combinations),
            "required_capability_keys": list(self.required_capability_keys),
            "minimum_recovery_samples": self.minimum_recovery_samples,
            "task_type_aliases": {
                key: list(value)
                for key, value in sorted(self.task_type_aliases.items())
            },
            "recovery_task_type_alias": self.recovery_task_type_alias,
        }


FALLBACK_RELEASE_COMPLETENESS_THRESHOLDS = ReleaseCompletenessThresholds(
    min_accepted_samples=5,
    max_rejection_rate=0.2,
    required_task_types=(
        "lookup_contact_email",
        "contact_followup",
        "contact_branch_fallback",
    ),
    required_tool_combinations=(
        "lookup_contact_email",
        "lookup_contact_email+record_contact_followup",
    ),
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
    release_completeness = _release_completeness(
        manifest=manifest,
        quality_report=quality_report,
        observed=observed,
        domain_id=_release_completeness_domain_id(manifest),
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
        "release_completeness": release_completeness,
        "decisions": {
            "dataset_release": _dataset_release_decision(
                profile=profile,
                manifest=manifest,
                quality_report=quality_report,
                evaluation_report=evaluation_report,
                profile_decision_report=profile_decision_report,
                observed=observed,
                release_completeness=release_completeness,
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
    release_completeness: Mapping[str, object],
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

    orchestration = manifest.get("orchestration")
    if isinstance(orchestration, Mapping):
        if (
            orchestration.get("status") != "completed"
            or orchestration.get("completeness") != "complete"
            or orchestration.get("release_eligible") is False
        ):
            return {
                "status": "insufficient_evidence",
                "reasons": [
                    "orchestration job is cancelled or incomplete; release admission is unavailable"
                ],
                "triggered_by": ["orchestration_completeness"],
            }

    profile_purpose = _string_value(profile.get("profile_purpose"), "profile.profile_purpose")
    if profile_purpose != "release_candidate":
        return {
            "status": "ineligible",
            "reasons": [f"profile_purpose {profile_purpose} is not release_candidate"],
            "triggered_by": ["profile_purpose"],
        }

    mismatch_reason = _evaluation_domain_mismatch_reason(
        manifest=manifest,
        evaluation_report=evaluation_report,
    )
    if mismatch_reason is not None:
        return {
            "status": "insufficient_evidence",
            "reasons": [mismatch_reason],
            "triggered_by": ["evaluation_domain"],
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

    completeness_decision = _mapping_or_empty(release_completeness.get("decision"))
    if completeness_decision.get("status") != "passed":
        reasons = [
            str(reason)
            for reason in completeness_decision.get("reasons", [])
            if isinstance(reason, str) and reason.strip()
        ]
        return {
            "status": "insufficient_evidence",
            "reasons": reasons or ["release completeness did not meet admission"],
            "triggered_by": ["release_completeness"],
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


def _evaluation_domain_mismatch_reason(
    *,
    manifest: Mapping[str, Any],
    evaluation_report: Mapping[str, Any] | None,
) -> str | None:
    if evaluation_report is None:
        return None
    evaluation_domain = evaluation_domain_id(evaluation_report)
    if evaluation_domain is None:
        return None
    manifest_domain = manifest_domain_id(manifest)
    if evaluation_domain == manifest_domain:
        return None
    return (
        f"evaluation domain {evaluation_domain} does not match "
        f"manifest domain {manifest_domain}"
    )


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


def _release_completeness(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    observed: Mapping[str, object],
    domain_id: str | None,
) -> dict[str, object]:
    accepted = _optional_int(observed.get("accepted"), 0)
    rejected = _optional_int(observed.get("rejected"), 0)
    total = accepted + rejected
    rejection_rate = rejected / total if total else 0.0
    slices = _mapping_or_empty(quality_report.get("slices"))
    task_types = sorted(
        _accepted_slice_keys(_mapping_or_empty(slices.get("task_type")))
    )
    tool_combinations = sorted(
        _normalize_tool_combination(key)
        for key in _accepted_slice_keys(_mapping_or_empty(slices.get("tool_combination")))
    )
    canonical_capability_evidence = _canonical_capability_evidence(
        manifest=manifest,
        quality_report=quality_report,
    )
    capability_keys = sorted(
        _accepted_capability_keys(canonical_capability_evidence)
    )
    recovery_samples = _optional_int(
        canonical_capability_evidence.get("verified_recovery_samples"),
        0,
    )
    thresholds = _release_completeness_thresholds(
        domain_id,
        task_types=task_types,
        tool_combinations=tool_combinations,
    )
    coverage_task_types = _compatibility_task_type_keys(
        task_types,
        recovery_samples,
        thresholds.task_type_aliases,
        thresholds.recovery_task_type_alias,
    )
    observed_summary = {
        "accepted": accepted,
        "rejected": rejected,
        "rejection_rate": rejection_rate,
        "task_types": task_types,
        "tool_combinations": tool_combinations,
        "capability_keys": capability_keys,
        "verified_recovery_samples": recovery_samples,
        "capability_evidence_available": bool(canonical_capability_evidence),
    }
    return {
        "thresholds": thresholds.export(),
        "observed": observed_summary,
        "decision": _release_completeness_decision(
            thresholds=thresholds,
            accepted=accepted,
            rejection_rate=rejection_rate,
            task_types=coverage_task_types,
            tool_combinations=tool_combinations,
            capability_keys=capability_keys,
            recovery_samples=recovery_samples,
            capability_evidence_available=bool(canonical_capability_evidence),
        ),
    }


def _release_completeness_thresholds(
    domain_id: str | None,
    *,
    task_types: list[str],
    tool_combinations: list[str],
) -> ReleaseCompletenessThresholds:
    threshold_record = release_completeness_threshold_record(domain_id)
    if threshold_record is not None:
        return ReleaseCompletenessThresholds(
            min_accepted_samples=_threshold_int(
                threshold_record.get("min_accepted_samples"),
                "min_accepted_samples",
            ),
            max_rejection_rate=_threshold_number(
                threshold_record.get("max_rejection_rate"),
                "max_rejection_rate",
            ),
            required_task_types=_threshold_strings(
                threshold_record.get("required_task_types"),
                "required_task_types",
            ),
            required_tool_combinations=_threshold_strings(
                threshold_record.get("required_tool_combinations"),
                "required_tool_combinations",
            ),
            required_capability_keys=_threshold_strings(
                threshold_record.get("required_capability_keys", []),
                "required_capability_keys",
            ),
            minimum_recovery_samples=_threshold_nonnegative_int(
                threshold_record.get("minimum_recovery_samples", 0),
                "minimum_recovery_samples",
            ),
            task_type_aliases=_threshold_aliases(
                threshold_record.get("task_type_aliases", {}),
                "task_type_aliases",
            ),
            recovery_task_type_alias=_threshold_optional_string(
                threshold_record.get("recovery_task_type_alias"),
                "recovery_task_type_alias",
            ),
        )
    return ReleaseCompletenessThresholds(
        min_accepted_samples=FALLBACK_RELEASE_COMPLETENESS_THRESHOLDS.min_accepted_samples,
        max_rejection_rate=FALLBACK_RELEASE_COMPLETENESS_THRESHOLDS.max_rejection_rate,
        required_task_types=tuple(task_types),
        required_tool_combinations=tuple(tool_combinations),
    )


def _compatibility_task_type_keys(
    task_types: list[str],
    recovery_samples: int,
    aliases: Mapping[str, tuple[str, ...]],
    recovery_alias: str | None,
) -> list[str]:
    normalized = set(task_types)
    for task_type in task_types:
        normalized.update(aliases.get(task_type, ()))
    if recovery_samples > 0 and recovery_alias is not None:
        normalized.add(recovery_alias)
    return sorted(normalized)


def _release_completeness_decision(
    *,
    thresholds: ReleaseCompletenessThresholds,
    accepted: int,
    rejection_rate: float,
    task_types: list[str],
    tool_combinations: list[str],
    capability_keys: list[str],
    recovery_samples: int,
    capability_evidence_available: bool,
) -> dict[str, object]:
    reasons: list[str] = []
    triggered_by: list[str] = []

    if accepted >= thresholds.min_accepted_samples:
        reasons.append(
            f"accepted {accepted} is at or above min_accepted_samples "
            f"{thresholds.min_accepted_samples}"
        )
    else:
        reasons.append(
            f"accepted {accepted} is below min_accepted_samples "
            f"{thresholds.min_accepted_samples}"
        )
        triggered_by.append("accepted")

    if rejection_rate <= thresholds.max_rejection_rate:
        reasons.append(
            f"rejection_rate {rejection_rate} is at or below max_rejection_rate "
            f"{thresholds.max_rejection_rate}"
        )
    else:
        reasons.append(
            f"rejection_rate {rejection_rate} is above max_rejection_rate "
            f"{thresholds.max_rejection_rate}"
        )
        triggered_by.append("rejection_rate")

    missing_task_types = sorted(set(thresholds.required_task_types).difference(task_types))
    if not thresholds.required_task_types:
        reasons.append("required task type thresholds are empty")
        triggered_by.append("task_type_coverage")
    elif missing_task_types:
        reasons.append(f"required task types are missing: {', '.join(missing_task_types)}")
        triggered_by.append("task_type_coverage")
    else:
        reasons.append("required task types are covered")

    missing_tool_combinations = sorted(
        set(thresholds.required_tool_combinations).difference(tool_combinations)
    )
    if not thresholds.required_tool_combinations:
        reasons.append("required tool combination thresholds are empty")
        triggered_by.append("tool_combination_coverage")
    elif missing_tool_combinations:
        reasons.append(
            "required tool combinations are missing: "
            + ", ".join(missing_tool_combinations)
        )
        triggered_by.append("tool_combination_coverage")
    else:
        reasons.append("required tool combinations are covered")

    if thresholds.required_capability_keys:
        if not capability_evidence_available:
            reasons.append("canonical capability evidence is unavailable")
            # Preserve the pre-domain-pack compatibility path for historical
            # reports; current domain writers always emit this evidence.
        else:
            missing_capabilities = sorted(
                set(thresholds.required_capability_keys).difference(capability_keys)
            )
            if missing_capabilities:
                reasons.append(
                    "required capabilities are missing: "
                    + ", ".join(missing_capabilities)
                )
                triggered_by.append("capability_coverage")
            else:
                reasons.append("required capabilities are covered")

    if recovery_samples >= thresholds.minimum_recovery_samples:
        reasons.append(
            f"verified recovery samples {recovery_samples} meet minimum "
            f"{thresholds.minimum_recovery_samples}"
        )
    else:
        reasons.append(
            f"verified recovery samples {recovery_samples} are below minimum "
            f"{thresholds.minimum_recovery_samples}"
        )
        if capability_evidence_available:
            triggered_by.append("recovery_coverage")

    if triggered_by:
        return {
            "status": "insufficient_evidence",
            "reasons": reasons,
            "triggered_by": triggered_by,
        }
    return {
        "status": "passed",
        "reasons": reasons,
        "triggered_by": [
            "accepted",
            "rejection_rate",
            "task_type_coverage",
            "tool_combination_coverage",
            "capability_coverage",
            "recovery_coverage",
        ],
    }


def _accepted_slice_keys(slices: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for raw_key, raw_slice in slices.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            continue
        slice_record = _mapping_or_empty(raw_slice)
        if _optional_int(slice_record.get("accepted"), 0) > 0:
            keys.append(raw_key)
    return keys


def _canonical_capability_evidence(
    *,
    manifest: Mapping[str, Any],
    quality_report: Mapping[str, Any],
) -> Mapping[str, Any]:
    manifest_evidence = manifest.get("domain_capability_evidence")
    if isinstance(manifest_evidence, Mapping):
        return manifest_evidence
    quality_evidence = quality_report.get("domain_capability_evidence")
    if isinstance(quality_evidence, Mapping):
        return quality_evidence
    slices = _mapping_or_empty(quality_report.get("slices"))
    capability_slices = slices.get("capability")
    if isinstance(capability_slices, Mapping) and capability_slices:
        return {
            "accepted_capability_counts": {
                str(key): _optional_int(
                    _mapping_or_empty(value).get("accepted"),
                    0,
                )
                for key, value in capability_slices.items()
            },
            "verified_recovery_samples": 0,
        }
    return {}


def _accepted_capability_keys(evidence: Mapping[str, Any]) -> set[str]:
    counts = evidence.get("accepted_capability_counts")
    if not isinstance(counts, Mapping):
        counts = evidence.get("accepted_counts")
    if not isinstance(counts, Mapping):
        return set()
    return {
        str(key)
        for key, value in counts.items()
        if _optional_int(value, 0) > 0
    }


def _normalize_tool_combination(raw: str) -> str:
    parts = [part.strip() for part in raw.replace(">", "+").split("+")]
    return "+".join(part for part in parts if part)


def _release_completeness_domain_id(
    manifest: Mapping[str, Any],
) -> str:
    profile = manifest.get("run_profile")
    profile_id = profile.get("profile_id") if isinstance(profile, Mapping) else None
    if isinstance(profile_id, str) and release_completeness_threshold_record(profile_id):
        return profile_id
    return manifest_domain_id(manifest)


def _profile_summary(manifest: Mapping[str, Any]) -> dict[str, object]:
    profile = _mapping_value(manifest.get("run_profile"), "manifest.run_profile")
    allowed_keys = (
        "schema_version",
        "profile_id",
        "generation_mode",
        "profile_purpose",
        "target_candidate_count",
        "config_hash",
        "generation_contract",
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


def _threshold_int(raw: object, path: str) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    raise ValueError(f"release threshold {path} must be a positive integer")


def _threshold_nonnegative_int(raw: object, path: str) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return raw
    raise ValueError(f"release threshold {path} must be a non-negative integer")


def _threshold_number(raw: object, path: str) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and float(raw) >= 0.0:
        return float(raw)
    raise ValueError(f"release threshold {path} must be a non-negative number")


def _threshold_strings(raw: object, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"release threshold {path} must be a list")
    values: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"release threshold {path}.{index} must be a non-empty string")
        values.append(value)
    return tuple(values)


def _threshold_optional_string(raw: object, path: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"release threshold {path} must be a non-empty string")
    return raw


def _threshold_aliases(
    raw: object,
    path: str,
) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"release threshold {path} must be an object")
    aliases: dict[str, tuple[str, ...]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"release threshold {path} contains an invalid key")
        aliases[key] = _threshold_strings(values, f"{path}.{key}")
    return aliases
