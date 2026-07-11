from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from operator import gt, lt
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    canonical_release_review_reason,
    validate_release_quality_audit_record,
    validate_release_review_item_record,
    validate_review_decision_record,
    validate_review_resolution_report_record,
)


RELEASE_REVIEW_ITEM_SCHEMA_VERSION = "release_review_item_v1"
RELEASE_REVIEW_QUEUE_FILENAME = "release_review_queue.jsonl"
RELEASE_QUALITY_AUDIT_FILENAME = "release_quality_audit.json"
FIXED_REVIEW_TIMESTAMP = "1970-01-01T00:00:00Z"
REVIEW_RESOLUTION_REPORT_SCHEMA_VERSION = "review_resolution_report_v1"
REVIEW_RESOLUTION_REPORT_FILENAME = "review_resolution_report.json"


@dataclass(frozen=True)
class DirectRiskSpec:
    trigger: str
    risk_kind: str
    observed_field: str
    threshold_field: str
    is_triggered: Callable[[int | float, int | float], bool]


DIRECT_RISK_SPECS = (
    DirectRiskSpec(
        trigger="small_release_size",
        risk_kind="small_release_size",
        observed_field="accepted",
        threshold_field="small_release_watch_accepted_samples",
        is_triggered=lt,
    ),
    DirectRiskSpec(
        trigger="exact_duplicate_rate",
        risk_kind="exact_duplicate_rate",
        observed_field="exact_duplicate_rate",
        threshold_field="max_exact_duplicate_rate",
        is_triggered=gt,
    ),
    DirectRiskSpec(
        trigger="task_type_concentration",
        risk_kind="task_type_concentration",
        observed_field="largest_task_type_share",
        threshold_field="max_largest_task_type_share",
        is_triggered=gt,
    ),
    DirectRiskSpec(
        trigger="tool_combination_concentration",
        risk_kind="tool_combination_concentration",
        observed_field="largest_tool_combination_share",
        threshold_field="max_largest_tool_combination_share",
        is_triggered=gt,
    ),
)
DIRECT_RISK_BY_TRIGGER = {spec.trigger: spec for spec in DIRECT_RISK_SPECS}
REVIEW_TRIGGER_ORDER = tuple(spec.trigger for spec in DIRECT_RISK_SPECS) + (
    "duplicate_family_risk",
)
TRIGGER_ORDER = {
    trigger: index for index, trigger in enumerate(REVIEW_TRIGGER_ORDER)
}


class ReleaseReviewEvidenceError(ValueError):
    """Signals invalid audit evidence without echoing raw input material."""


def build_release_review_items(
    audit: Mapping[str, Any],
) -> list[dict[str, object]]:
    try:
        validate_release_quality_audit_record(audit)
    except ContractValidationError as exc:
        raise ReleaseReviewEvidenceError("invalid_release_quality_audit") from exc

    decision = audit.get("decision")
    if not isinstance(decision, Mapping):
        raise ReleaseReviewEvidenceError("invalid_release_quality_audit")
    status = decision.get("status")
    if status == "clear":
        clear_triggers = _string_list(
            decision.get("triggered_by"),
            "invalid_audit_triggers",
        )
        if clear_triggers or _structured_review_triggers(audit):
            raise ReleaseReviewEvidenceError("audit_trigger_observation_mismatch")
        return []
    if status != "watch":
        return []

    dataset_version = _required_string(
        audit.get("dataset_version"),
        "invalid_dataset_version",
    )
    triggers = _string_list(
        decision.get("triggered_by"),
        "invalid_audit_triggers",
    )
    reasons = _string_list(
        decision.get("reasons"),
        "invalid_audit_reasons",
    )
    if len(triggers) != len(reasons):
        raise ReleaseReviewEvidenceError("audit_trigger_reason_mismatch")
    if len(set(triggers)) != len(triggers):
        raise ReleaseReviewEvidenceError("duplicate_audit_trigger")
    unknown_triggers = set(triggers) - set(TRIGGER_ORDER)
    if unknown_triggers:
        raise ReleaseReviewEvidenceError("unknown_audit_trigger")
    structured_triggers = _structured_review_triggers(audit)
    if not structured_triggers or set(triggers) != structured_triggers:
        raise ReleaseReviewEvidenceError("audit_trigger_observation_mismatch")

    trigger_reasons = dict(zip(triggers, reasons, strict=True))
    items = [
        _review_item(
            dataset_version=dataset_version,
            risk_kind=DIRECT_RISK_BY_TRIGGER[trigger].risk_kind,
            reason=_canonical_direct_reason(trigger, audit),
            sample_ids=[],
        )
        for trigger in sorted(
            set(triggers) & set(DIRECT_RISK_BY_TRIGGER),
            key=TRIGGER_ORDER.__getitem__,
        )
    ]

    duplicate_risks = _mapping_list(
        audit.get("duplicate_family_risks"),
        "invalid_duplicate_family_evidence",
    )
    has_duplicate_trigger = "duplicate_family_risk" in trigger_reasons
    if has_duplicate_trigger != bool(duplicate_risks):
        raise ReleaseReviewEvidenceError("duplicate_family_trigger_mismatch")
    if has_duplicate_trigger:
        items.extend(
            _duplicate_family_items(
                dataset_version=dataset_version,
                duplicate_risks=duplicate_risks,
            )
        )
    item_ids = [str(item["review_item_id"]) for item in items]
    if len(set(item_ids)) != len(item_ids):
        raise ReleaseReviewEvidenceError("duplicate_review_item")
    return items


def write_release_review_queue(
    audit: Mapping[str, Any],
    *,
    output_path: Path = Path(RELEASE_REVIEW_QUEUE_FILENAME),
) -> Path | None:
    items = build_release_review_items(audit)
    if not items:
        output_path.unlink(missing_ok=True)
        return None
    for item in items:
        validate_release_review_item_record(item)
    output_path.write_text(
        "".join(
            json.dumps(
                item,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for item in items
        ),
        encoding="utf-8",
    )
    return output_path


def load_review_decisions(path: Path) -> list[dict[str, object]]:
    decisions = _load_jsonl_records(path, validate_review_decision_record)
    if not decisions:
        raise ReleaseReviewEvidenceError("review_decisions_empty")
    decision_ids = [str(decision["review_item_id"]) for decision in decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise ReleaseReviewEvidenceError("duplicate_review_decision")
    return decisions


def build_review_resolution_report(
    queue_path: Path,
    decisions_path: Path,
    *,
    expected_dataset_version: str | None = None,
) -> dict[str, object]:
    inputs = {
        "release_review_queue_path": _safe_basename(
            queue_path,
            RELEASE_REVIEW_QUEUE_FILENAME,
        ),
        "review_decisions_path": _safe_basename(
            decisions_path,
            "review_decisions.jsonl",
        ),
    }
    try:
        queue_items = _load_release_review_queue(queue_path)
    except (
        OSError,
        UnicodeError,
        ReleaseReviewEvidenceError,
    ) as exc:
        return _insufficient_evidence_report(
            dataset_version="unknown_dataset",
            inputs=inputs,
            queued=0,
            reason=_sanitized_failure_reason("release_review_queue", exc),
            trigger="release_review_queue",
        )

    dataset_version = str(queue_items[0]["dataset_version"])
    if (
        expected_dataset_version is not None
        and dataset_version != expected_dataset_version
    ):
        return _insufficient_evidence_report(
            dataset_version=expected_dataset_version,
            inputs=inputs,
            queued=len(queue_items),
            reason="queue_dataset_version_mismatch",
            trigger="release_review_queue",
        )
    try:
        decisions = load_review_decisions(decisions_path)
    except (
        OSError,
        UnicodeError,
        ReleaseReviewEvidenceError,
    ) as exc:
        return _insufficient_evidence_report(
            dataset_version=dataset_version,
            inputs=inputs,
            queued=len(queue_items),
            reason=_sanitized_failure_reason("review_decisions", exc),
            trigger="review_decisions",
        )

    queue_ids = {str(item["review_item_id"]) for item in queue_items}
    decision_ids = {str(decision["review_item_id"]) for decision in decisions}
    if not decision_ids <= queue_ids:
        return _insufficient_evidence_report(
            dataset_version=dataset_version,
            inputs=inputs,
            queued=len(queue_items),
            reason="unknown_review_item_id",
            trigger="review_decisions",
        )

    counts = {
        "queued": len(queue_items),
        "resolved": len(decisions),
        "pending": len(queue_items) - len(decisions),
        "accepted_risk": 0,
        "confirmed_issue": 0,
        "needs_follow_up": 0,
        "review_minutes": 0,
    }
    for decision in decisions:
        outcome = str(decision["outcome"])
        counts[outcome] += 1
        counts["review_minutes"] += int(decision["review_minutes"])

    if counts["pending"]:
        status = "pending_review"
        reasons = ["queued review items are pending decisions"]
        triggered_by = ["pending_review_items"]
    else:
        status = "reviewed"
        reasons = ["all queued review items have decisions"]
        triggered_by = ["review_decisions"]
    report: dict[str, object] = {
        "schema_version": REVIEW_RESOLUTION_REPORT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "inputs": inputs,
        "counts": counts,
        "decision": {
            "status": status,
            "reasons": reasons,
            "triggered_by": triggered_by,
        },
    }
    validate_review_resolution_report_record(report)
    return report


def write_review_resolution_report(
    queue_path: Path,
    decisions_path: Path,
    *,
    output_path: Path | None = None,
    expected_dataset_version: str | None = None,
) -> Path:
    report = build_review_resolution_report(
        queue_path,
        decisions_path,
        expected_dataset_version=expected_dataset_version,
    )
    validate_review_resolution_report_record(report)
    destination = output_path or queue_path.parent / REVIEW_RESOLUTION_REPORT_FILENAME
    destination.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _load_release_review_queue(path: Path) -> list[dict[str, object]]:
    items = _load_jsonl_records(path, validate_release_review_item_record)
    if not items:
        raise ReleaseReviewEvidenceError("release_review_queue_empty")
    review_item_ids = [str(item["review_item_id"]) for item in items]
    if len(set(review_item_ids)) != len(review_item_ids):
        raise ReleaseReviewEvidenceError("duplicate_release_review_item")
    dataset_versions = {str(item["dataset_version"]) for item in items}
    if len(dataset_versions) != 1:
        raise ReleaseReviewEvidenceError("queue_dataset_version_mismatch")
    return items


def _load_jsonl_records(
    path: Path,
    validator: Any,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                raw_record = json.loads(line)
                if not isinstance(raw_record, Mapping):
                    raise ReleaseReviewEvidenceError("invalid_jsonl_record")
                validator(raw_record)
            except ReleaseReviewEvidenceError:
                raise
            except (ValueError, RecursionError) as exc:
                raise ReleaseReviewEvidenceError("invalid_jsonl_record") from exc
            records.append(dict(raw_record))
    return records


def _insufficient_evidence_report(
    *,
    dataset_version: str,
    inputs: Mapping[str, str],
    queued: int,
    reason: str,
    trigger: str,
) -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": REVIEW_RESOLUTION_REPORT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "inputs": dict(inputs),
        "counts": {
            "queued": queued,
            "resolved": 0,
            "pending": queued,
            "accepted_risk": 0,
            "confirmed_issue": 0,
            "needs_follow_up": 0,
            "review_minutes": 0,
        },
        "decision": {
            "status": "insufficient_evidence",
            "reasons": [reason],
            "triggered_by": [trigger],
        },
    }
    validate_review_resolution_report_record(report)
    return report


def _sanitized_failure_reason(prefix: str, exc: BaseException) -> str:
    if isinstance(exc, ReleaseReviewEvidenceError):
        return str(exc)
    return f"{prefix}_invalid:{type(exc).__name__}"


def _safe_basename(path: Path, fallback: str) -> str:
    name = path.name
    lowered = name.casefold()
    unsafe_fragments = ("secret", "credential", "authorization", "api_key", "token")
    safe_characters = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
    )
    if (
        not name
        or any(fragment in lowered for fragment in unsafe_fragments)
        or any(character not in safe_characters for character in name)
    ):
        return fallback
    return name


def _duplicate_family_items(
    *,
    dataset_version: str,
    duplicate_risks: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for risk in duplicate_risks:
        sample_ids = _string_list(
            risk.get("sample_ids"),
            "invalid_duplicate_family_evidence",
        )
        sample_count = risk.get("sample_count")
        if (
            risk.get("risk_level") != "watch"
            or risk.get("risk_kind") != "same_task_type_and_tool_combination"
            or not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count != len(sample_ids)
        ):
            raise ReleaseReviewEvidenceError("invalid_duplicate_family_evidence")
        if not sample_ids:
            raise ReleaseReviewEvidenceError("invalid_duplicate_family_evidence")
        items.append(
            _review_item(
                dataset_version=dataset_version,
                risk_kind="duplicate_family",
                reason=(
                    f"{sample_count} accepted samples share the same task type "
                    "and tool combination"
                ),
                sample_ids=sorted(sample_ids),
            )
        )
    return sorted(items, key=lambda item: str(item["review_item_id"]))


def _canonical_direct_reason(
    trigger: str,
    audit: Mapping[str, Any],
) -> str:
    observed = audit["observed"]
    thresholds = audit["thresholds"]
    assert isinstance(observed, Mapping)
    assert isinstance(thresholds, Mapping)
    try:
        spec = DIRECT_RISK_BY_TRIGGER[trigger]
    except KeyError as exc:
        raise ReleaseReviewEvidenceError("unknown_audit_trigger") from exc
    return canonical_release_review_reason(
        spec.risk_kind,
        observed[spec.observed_field],
        thresholds[spec.threshold_field],
    )


def _structured_review_triggers(audit: Mapping[str, Any]) -> set[str]:
    observed = audit["observed"]
    thresholds = audit["thresholds"]
    duplicate_risks = audit["duplicate_family_risks"]
    assert isinstance(observed, Mapping)
    assert isinstance(thresholds, Mapping)
    assert isinstance(duplicate_risks, Sequence)
    triggers: set[str] = set()
    for spec in DIRECT_RISK_SPECS:
        if spec.is_triggered(
            observed[spec.observed_field],
            thresholds[spec.threshold_field],
        ):
            triggers.add(spec.trigger)
    if duplicate_risks:
        max_family_size = int(thresholds["max_duplicate_family_size"])
        for raw_risk in duplicate_risks:
            assert isinstance(raw_risk, Mapping)
            if int(raw_risk["sample_count"]) <= max_family_size:
                raise ReleaseReviewEvidenceError(
                    "audit_trigger_observation_mismatch"
                )
        triggers.add("duplicate_family_risk")
    return triggers


def _review_item(
    *,
    dataset_version: str,
    risk_kind: str,
    reason: str,
    sample_ids: list[str],
) -> dict[str, object]:
    canonical_payload = {
        "dataset_version": dataset_version,
        "source_artifact": RELEASE_QUALITY_AUDIT_FILENAME,
        "risk_kind": risk_kind,
        "risk_level": "watch",
        "reason": reason,
        "sample_ids": sorted(sample_ids),
    }
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    item: dict[str, object] = {
        "schema_version": RELEASE_REVIEW_ITEM_SCHEMA_VERSION,
        "review_item_id": "review_item:sha256:"
        + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "dataset_version": dataset_version,
        "source": {
            "artifact": RELEASE_QUALITY_AUDIT_FILENAME,
            "audit_status": "watch",
        },
        "risk": {
            "kind": risk_kind,
            "level": "watch",
            "reason": reason,
            "sample_ids": sorted(sample_ids),
        },
        "created_at": FIXED_REVIEW_TIMESTAMP,
    }
    validate_release_review_item_record(item)
    return item


def _required_string(raw: object, reason_code: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ReleaseReviewEvidenceError(reason_code)
    return raw


def _string_list(raw: object, reason_code: str) -> list[str]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ReleaseReviewEvidenceError(reason_code)
    return [_required_string(value, reason_code) for value in raw]


def _mapping_list(
    raw: object,
    reason_code: str,
) -> list[Mapping[str, Any]]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ReleaseReviewEvidenceError(reason_code)
    if not all(isinstance(value, Mapping) for value in raw):
        raise ReleaseReviewEvidenceError(reason_code)
    return list(raw)
