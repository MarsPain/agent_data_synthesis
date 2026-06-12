from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from synthesis.contracts import validate_release_quality_audit_record


RELEASE_QUALITY_AUDIT_SCHEMA_VERSION = "release_quality_audit_v1"
RELEASE_QUALITY_AUDIT_FILENAME = "release_quality_audit.json"
DATASET_RELEASE_CARD_FILENAME = "dataset_release_card.md"
PROFILE_FIELDS = (
    "schema_version",
    "profile_id",
    "generation_mode",
    "profile_purpose",
    "config_hash",
)
REQUIRED_INPUT_FIELDS = (
    "manifest_path",
    "quality_report_path",
    "evaluation_report_path",
    "profile_decision_report_path",
    "dataset_release_report_path",
    "samples_path",
    "rejections_path",
)


@dataclass(frozen=True)
class ReleaseQualityThresholds:
    small_release_watch_accepted_samples: int = 8
    max_largest_task_type_share: float = 0.75
    max_largest_tool_combination_share: float = 0.8
    max_exact_duplicate_rate: float = 0.0
    max_duplicate_family_size: int = 2

    def export(self) -> dict[str, object]:
        return asdict(self)


def build_release_quality_audit(
    *,
    manifest_path: Path,
    thresholds: ReleaseQualityThresholds = ReleaseQualityThresholds(),
) -> dict[str, object]:
    base_dir = manifest_path.parent
    try:
        manifest = _load_mapping(manifest_path, "manifest")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        audit = _insufficient_evidence_audit(
            dataset_version="unknown_dataset",
            profile=_fallback_profile(),
            inputs=_default_inputs(manifest_path),
            thresholds=thresholds,
            reasons=[f"manifest is unreadable or malformed: {type(exc).__name__}"],
        )
        validate_release_quality_audit_record(audit)
        return audit

    profile = _profile_summary(manifest)
    dataset_version = _string_value(
        manifest.get("dataset_version"),
        "manifest.dataset_version",
        fallback="unknown_dataset",
    )
    inputs = _artifact_inputs(manifest=manifest, manifest_path=manifest_path)
    missing = [
        f"{path.name} is missing"
        for path in _input_paths(base_dir=base_dir, inputs=inputs).values()
        if not path.exists()
    ]
    if missing:
        audit = _insufficient_evidence_audit(
            dataset_version=dataset_version,
            profile=profile,
            inputs=inputs,
            thresholds=thresholds,
            reasons=missing,
        )
        validate_release_quality_audit_record(audit)
        return audit

    try:
        paths = _input_paths(base_dir=base_dir, inputs=inputs)
        quality_report = _load_mapping(paths["quality_report_path"], "quality_report")
        profile_decision_report = _load_mapping(
            paths["profile_decision_report_path"],
            "profile_decision_report",
        )
        dataset_release_report = _load_mapping(
            paths["dataset_release_report_path"],
            "dataset_release_report",
        )
        samples = _load_jsonl_mappings(paths["samples_path"], "samples")
        rejections = _load_jsonl_mappings(paths["rejections_path"], "rejections")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        audit = _insufficient_evidence_audit(
            dataset_version=dataset_version,
            profile=profile,
            inputs=inputs,
            thresholds=thresholds,
            reasons=[f"required audit input is unreadable or malformed: {type(exc).__name__}"],
        )
        validate_release_quality_audit_record(audit)
        return audit

    observed = _observed_summary(
        samples=samples,
        rejections=rejections,
        quality_report=quality_report,
        profile_decision_report=profile_decision_report,
        dataset_release_report=dataset_release_report,
    )
    duplicate_family_risks = _duplicate_family_risks(
        samples=samples,
        max_duplicate_family_size=thresholds.max_duplicate_family_size,
    )
    audit = {
        "schema_version": RELEASE_QUALITY_AUDIT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "profile": profile,
        "inputs": inputs,
        "observed": observed,
        "thresholds": thresholds.export(),
        "duplicate_family_risks": duplicate_family_risks,
        "decision": _decision(
            observed=observed,
            duplicate_family_risks=duplicate_family_risks,
            thresholds=thresholds,
        ),
    }
    validate_release_quality_audit_record(audit)
    return audit


def write_release_quality_audit(
    *,
    manifest_path: Path,
    output_path: Path | None = None,
) -> Path:
    audit = build_release_quality_audit(manifest_path=manifest_path)
    destination = output_path or manifest_path.parent / RELEASE_QUALITY_AUDIT_FILENAME
    destination.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def render_dataset_release_card(
    *,
    manifest_path: Path,
    release_quality_audit: Mapping[str, Any] | None = None,
) -> str:
    base_dir = manifest_path.parent
    manifest = _load_mapping(manifest_path, "manifest")
    artifacts = _mapping_or_empty(manifest.get("artifacts"))
    release_report = _maybe_load_mapping(
        base_dir / str(artifacts.get("dataset_release_report", "dataset_release_report.json"))
    )
    profile = _profile_summary(manifest)
    if release_quality_audit is None:
        audit_path = base_dir / str(artifacts.get("release_quality_audit", RELEASE_QUALITY_AUDIT_FILENAME))
        release_quality_audit = _maybe_load_mapping(audit_path)
    pack_path = base_dir / str(artifacts.get("dataset_release_pack", "dataset_release_pack.json"))
    release_pack = _maybe_load_mapping(pack_path)

    release_decision = _mapping_or_empty(
        _mapping_or_empty(release_report.get("decisions")).get("dataset_release")
        if release_report
        else None
    )
    release_observed = _mapping_or_empty(release_report.get("observed")) if release_report else {}
    release_completeness = _mapping_or_empty(
        _mapping_or_empty(release_report.get("release_completeness")).get("decision")
        if release_report
        else None
    )
    audit_decision = _mapping_or_empty(release_quality_audit.get("decision")) if release_quality_audit else {}
    audit_observed = _mapping_or_empty(release_quality_audit.get("observed")) if release_quality_audit else {}
    pack_verification = _mapping_or_empty(release_pack.get("verification")) if release_pack else {}

    lines = [
        "# Dataset Release Card",
        "",
        "## Identity",
        f"- dataset_version: {_string_value(manifest.get('dataset_version'), 'dataset_version', fallback='unknown')}",
        f"- profile_id: {_string_value(profile.get('profile_id'), 'profile.profile_id', fallback='unknown')}",
        f"- profile_purpose: {_string_value(profile.get('profile_purpose'), 'profile.profile_purpose', fallback='unknown')}",
        "",
        "## Release Decision",
        f"- dataset_release_status: {_string_value(release_decision.get('status'), 'dataset_release.status', fallback='not generated')}",
        f"- heldout_status: {_string_value(release_observed.get('heldout_status'), 'heldout_status', fallback='not generated')}",
        f"- profile_promotion_status: {_string_value(release_observed.get('profile_promotion_status'), 'profile_promotion_status', fallback='not generated')}",
        "",
        "## Artifact Integrity",
        _release_pack_line(release_pack, pack_verification),
        "",
        "## Quality Evidence",
        f"- accepted: {_int_value(release_observed.get('accepted'), fallback=manifest.get('accepted_count'))}",
        f"- rejected: {_int_value(release_observed.get('rejected'), fallback=manifest.get('rejected_count'))}",
        f"- release_quality_audit_status: {_string_value(audit_decision.get('status'), 'audit.status', fallback='not generated')}",
        *_audit_reason_lines(audit_decision),
        "",
        "## Coverage and Diversity",
        f"- release_completeness_status: {_string_value(release_completeness.get('status'), 'release_completeness.status', fallback='not generated')}",
        f"- task_type_count: {_int_value(audit_observed.get('task_type_count'), fallback='not generated')}",
        f"- tool_combination_count: {_int_value(audit_observed.get('tool_combination_count'), fallback='not generated')}",
        f"- duplicate_family_risk_groups: {_risk_count(release_quality_audit)}",
        "",
        "## Known Limitations",
        "- The audit uses deterministic concentration and family-key signals, not semantic equivalence classification.",
        "- Watch findings identify review evidence and do not change dataset release admission by default.",
        "",
        "## Non-Claims",
        "- Release admission, audit status, and pack verification evidence does not prove downstream model quality, transfer gain, or training utility.",
        "",
    ]
    return "\n".join(lines)


def write_dataset_release_card(
    *,
    manifest_path: Path,
    output_path: Path | None = None,
) -> Path:
    card = render_dataset_release_card(manifest_path=manifest_path)
    destination = output_path or manifest_path.parent / DATASET_RELEASE_CARD_FILENAME
    destination.write_text(card, encoding="utf-8")
    return destination


def _insufficient_evidence_audit(
    *,
    dataset_version: str,
    profile: Mapping[str, object],
    inputs: Mapping[str, object],
    thresholds: ReleaseQualityThresholds,
    reasons: list[str],
) -> dict[str, object]:
    return {
        "schema_version": RELEASE_QUALITY_AUDIT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "profile": dict(profile),
        "inputs": dict(inputs),
        "observed": {
            "accepted": 0,
            "rejected": 0,
            "exact_duplicate_count": 0,
            "exact_duplicate_rate": 0.0,
            "task_type_count": 0,
            "tool_combination_count": 0,
            "largest_task_type_share": 0.0,
            "largest_tool_combination_share": 0.0,
            "release_completeness_status": "insufficient_evidence",
            "semantic_duplicate_detection_status": "insufficient_evidence",
        },
        "thresholds": thresholds.export(),
        "duplicate_family_risks": [],
        "decision": {
            "status": "insufficient_evidence",
            "reasons": reasons,
            "triggered_by": [],
        },
    }


def _observed_summary(
    *,
    samples: Sequence[Mapping[str, Any]],
    rejections: Sequence[Mapping[str, Any]],
    quality_report: Mapping[str, Any],
    profile_decision_report: Mapping[str, Any],
    dataset_release_report: Mapping[str, Any],
) -> dict[str, object]:
    accepted = len(samples)
    rejected = len(rejections)
    profile_observed = _mapping_or_empty(profile_decision_report.get("observed"))
    task_counts = _accepted_slice_counts(quality_report, "task_type")
    tool_counts = _accepted_slice_counts(quality_report, "tool_combination")
    return {
        "accepted": accepted,
        "rejected": rejected,
        "exact_duplicate_count": _int_value(
            profile_observed.get("exact_duplicate_count"),
            fallback=0,
        ),
        "exact_duplicate_rate": _number_value(
            profile_observed.get("exact_duplicate_rate"),
            fallback=0.0,
        ),
        "task_type_count": len(task_counts),
        "tool_combination_count": len(tool_counts),
        "largest_task_type_share": _largest_share(task_counts, accepted),
        "largest_tool_combination_share": _largest_share(tool_counts, accepted),
        "release_completeness_status": _release_completeness_status(dataset_release_report),
        "semantic_duplicate_detection_status": _semantic_duplicate_status(
            profile_decision_report,
            dataset_release_report,
        ),
    }


def _decision(
    *,
    observed: Mapping[str, object],
    duplicate_family_risks: Sequence[Mapping[str, object]],
    thresholds: ReleaseQualityThresholds,
) -> dict[str, object]:
    semantic_status = str(observed.get("semantic_duplicate_detection_status", ""))
    if semantic_status == "activate":
        return {
            "status": "blocked",
            "reasons": [
                "semantic_duplicate_detection is activated and must be implemented before release use"
            ],
            "triggered_by": ["semantic_duplicate_detection"],
        }

    reasons: list[str] = []
    triggered_by: list[str] = []
    accepted = _int_value(observed.get("accepted"), fallback=0)
    exact_duplicate_rate = _number_value(observed.get("exact_duplicate_rate"), fallback=0.0)
    largest_task_type_share = _number_value(
        observed.get("largest_task_type_share"),
        fallback=0.0,
    )
    largest_tool_combination_share = _number_value(
        observed.get("largest_tool_combination_share"),
        fallback=0.0,
    )
    if accepted < thresholds.small_release_watch_accepted_samples:
        reasons.append(
            f"accepted {accepted} is below small_release_watch_accepted_samples "
            f"{thresholds.small_release_watch_accepted_samples}"
        )
        triggered_by.append("small_release_size")
    if exact_duplicate_rate > thresholds.max_exact_duplicate_rate:
        reasons.append(
            f"exact_duplicate_rate {exact_duplicate_rate} is above max_exact_duplicate_rate "
            f"{thresholds.max_exact_duplicate_rate}"
        )
        triggered_by.append("exact_duplicate_rate")
    if largest_task_type_share > thresholds.max_largest_task_type_share:
        reasons.append(
            f"largest_task_type_share {largest_task_type_share} is above max_largest_task_type_share "
            f"{thresholds.max_largest_task_type_share}"
        )
        triggered_by.append("task_type_concentration")
    if largest_tool_combination_share > thresholds.max_largest_tool_combination_share:
        reasons.append(
            f"largest_tool_combination_share {largest_tool_combination_share} is above max_largest_tool_combination_share "
            f"{thresholds.max_largest_tool_combination_share}"
        )
        triggered_by.append("tool_combination_concentration")
    if duplicate_family_risks:
        reasons.append("duplicate family risk groups require review")
        triggered_by.append("duplicate_family_risk")
    if triggered_by:
        return {
            "status": "watch",
            "reasons": reasons,
            "triggered_by": triggered_by,
        }
    return {
        "status": "clear",
        "reasons": ["no configured release quality audit thresholds triggered"],
        "triggered_by": [],
    }


def _duplicate_family_risks(
    *,
    samples: Sequence[Mapping[str, Any]],
    max_duplicate_family_size: int,
) -> list[dict[str, object]]:
    family_ids: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        sample_id = _string_value(sample.get("sample_id"), "sample.sample_id", fallback="")
        if not sample_id:
            continue
        family_ids[_family_key(sample)].append(sample_id)
    risks = []
    for family_key, sample_ids in sorted(family_ids.items()):
        if len(sample_ids) <= max_duplicate_family_size:
            continue
        risks.append(
            {
                "family_key": family_key,
                "risk_kind": "same_task_type_and_tool_combination",
                "risk_level": "watch",
                "sample_ids": sorted(sample_ids),
                "sample_count": len(sample_ids),
                "reason": (
                    f"{len(sample_ids)} accepted samples share the same task type "
                    "and tool combination"
                ),
            }
        )
    return risks


def _family_key(sample: Mapping[str, Any]) -> str:
    task = _mapping_or_empty(sample.get("task"))
    parts = (
        _task_type(task),
        "+".join(_ordered_tool_names(sample)),
        _verifier_type(sample),
        _difficulty_level(task),
    )
    raw_key = "|".join(parts)
    return "sha256:" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _accepted_slice_counts(report: Mapping[str, Any], dimension: str) -> Counter[str]:
    slices = _mapping_or_empty(_mapping_or_empty(report.get("slices")).get(dimension))
    counts: Counter[str] = Counter()
    for raw_key, raw_slice in slices.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            continue
        accepted = _int_value(_mapping_or_empty(raw_slice).get("accepted"), fallback=0)
        if accepted > 0:
            counts[_normalize_tool_combination(raw_key) if dimension == "tool_combination" else raw_key] += accepted
    return counts


def _largest_share(counts: Counter[str], accepted: int) -> float:
    if accepted <= 0 or not counts:
        return 0.0
    return max(counts.values()) / accepted


def _profile_summary(manifest: Mapping[str, Any]) -> dict[str, object]:
    profile = _mapping_or_empty(manifest.get("run_profile"))
    summary = {key: profile[key] for key in PROFILE_FIELDS if key in profile}
    return summary or _fallback_profile()


def _fallback_profile() -> dict[str, object]:
    return {
        "schema_version": "run_profile_v1",
        "profile_id": "unknown_profile",
        "generation_mode": "foundation_fixture",
        "profile_purpose": "diagnostic_probe",
        "config_hash": "sha256:" + "0" * 64,
    }


def _artifact_inputs(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> dict[str, object]:
    artifacts = _mapping_or_empty(manifest.get("artifacts"))
    return {
        "manifest_path": manifest_path.name,
        "quality_report_path": _artifact_name(artifacts, "quality_report", "quality_report.json"),
        "evaluation_report_path": _artifact_name(artifacts, "evaluation_report", "evaluation_report.json"),
        "profile_decision_report_path": _artifact_name(
            artifacts,
            "profile_decision_report",
            "profile_decision_report.json",
        ),
        "dataset_release_report_path": _artifact_name(
            artifacts,
            "dataset_release_report",
            "dataset_release_report.json",
        ),
        "samples_path": _artifact_name(artifacts, "samples", "samples.jsonl"),
        "rejections_path": _artifact_name(artifacts, "rejections", "rejections.jsonl"),
    }


def _default_inputs(manifest_path: Path) -> dict[str, object]:
    return {
        "manifest_path": manifest_path.name,
        "quality_report_path": "quality_report.json",
        "evaluation_report_path": "evaluation_report.json",
        "profile_decision_report_path": "profile_decision_report.json",
        "dataset_release_report_path": "dataset_release_report.json",
        "samples_path": "samples.jsonl",
        "rejections_path": "rejections.jsonl",
    }


def _input_paths(*, base_dir: Path, inputs: Mapping[str, object]) -> dict[str, Path]:
    return {
        key: base_dir / _string_value(inputs.get(key), key, fallback="")
        for key in REQUIRED_INPUT_FIELDS
    }


def _artifact_name(
    artifacts: Mapping[str, Any],
    key: str,
    fallback: str,
) -> str:
    return _string_value(artifacts.get(key), f"artifacts.{key}", fallback=fallback)


def _load_mapping(path: Path, name: str) -> Mapping[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ValueError(f"{name} must be an object")
    return loaded


def _maybe_load_mapping(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _load_mapping(path, path.name)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _load_jsonl_mappings(path: Path, name: str) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, Mapping):
            raise ValueError(f"{name}.{line_number} must be an object")
        records.append(record)
    return records


def _release_completeness_status(report: Mapping[str, Any]) -> str:
    release_completeness = _mapping_or_empty(report.get("release_completeness"))
    decision = _mapping_or_empty(release_completeness.get("decision"))
    return _string_value(
        decision.get("status"),
        "release_completeness.decision.status",
        fallback="insufficient_evidence",
    )


def _semantic_duplicate_status(
    profile_decision_report: Mapping[str, Any],
    dataset_release_report: Mapping[str, Any],
) -> str:
    profile_decisions = _mapping_or_empty(profile_decision_report.get("decisions"))
    semantic_decision = _mapping_or_empty(
        profile_decisions.get("semantic_duplicate_detection")
    )
    status = semantic_decision.get("status")
    if isinstance(status, str) and status.strip():
        return status
    observed = _mapping_or_empty(dataset_release_report.get("observed"))
    return _string_value(
        observed.get("semantic_duplicate_detection_status"),
        "observed.semantic_duplicate_detection_status",
        fallback="insufficient_evidence",
    )


def _task_type(task: Mapping[str, Any]) -> str:
    constraints = _mapping_or_empty(task.get("constraints"))
    return _string_value(
        constraints.get("task_type") or constraints.get("must_use_tool"),
        "task.task_type",
        fallback="unknown",
    )


def _difficulty_level(task: Mapping[str, Any]) -> str:
    difficulty = _mapping_or_empty(task.get("difficulty"))
    return _string_value(difficulty.get("level"), "task.difficulty.level", fallback="unknown")


def _ordered_tool_names(sample: Mapping[str, Any]) -> tuple[str, ...]:
    tools = [
        str(event.get("tool"))
        for event in _sequence_or_empty(sample.get("trajectory"))
        if isinstance(event, Mapping) and event.get("type") == "action" and event.get("tool")
    ]
    return tuple(tools)


def _verifier_type(sample: Mapping[str, Any]) -> str:
    verifier = _mapping_or_empty(sample.get("verifier"))
    return _string_value(verifier.get("id"), "verifier.id", fallback="unknown")


def _normalize_tool_combination(raw: str) -> str:
    parts = [part.strip() for part in raw.replace(">", "+").split("+")]
    return "+".join(part for part in parts if part)


def _release_pack_line(
    release_pack: Mapping[str, Any] | None,
    verification: Mapping[str, Any],
) -> str:
    if not release_pack:
        return "- release pack: not generated"
    return (
        "- release pack: "
        f"{_string_value(release_pack.get('release_id'), 'release_id', fallback='unknown')} "
        f"verification_status={_string_value(verification.get('status'), 'verification.status', fallback='unknown')}"
    )


def _audit_reason_lines(audit_decision: Mapping[str, Any]) -> list[str]:
    reasons = [
        reason
        for reason in _sequence_or_empty(audit_decision.get("reasons"))
        if isinstance(reason, str) and reason.strip()
    ]
    if not reasons:
        return ["- release_quality_audit_reasons: not generated"]
    return [f"- release_quality_audit_reason: {reason}" for reason in reasons]


def _risk_count(release_quality_audit: Mapping[str, Any] | None) -> object:
    if not release_quality_audit:
        return "not generated"
    risks = release_quality_audit.get("duplicate_family_risks")
    if isinstance(risks, Sequence) and not isinstance(risks, str):
        return len(risks)
    return "unknown"


def _mapping_or_empty(raw: object) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _sequence_or_empty(raw: object) -> Sequence[Any]:
    return raw if isinstance(raw, Sequence) and not isinstance(raw, str) else ()


def _string_value(raw: object, path: str, *, fallback: str) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw
    return fallback


def _int_value(raw: object, *, fallback: object) -> int | object:
    value = raw if raw is not None else fallback
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return fallback


def _number_value(raw: object, *, fallback: float) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0.0:
        return float(raw)
    return fallback
