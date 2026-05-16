from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


EXECUTABLE_REJECTION_CAUSES = {
    "verification_failed",
    "quality_duplicate",
    "solution_logic_error",
}

RETRYABLE_REJECTION_CAUSES = {
    "tool_runtime_error",
    "infrastructure_error",
}

REVIEWABLE_REJECTION_CAUSES = {
    "quality_duplicate",
    "solution_logic_error",
}


def build_quality_report(
    *,
    dataset_version: str,
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, object]:
    total_count = len(samples) + len(rejections)
    executable_count = len(samples) + sum(
        1 for rejection in rejections if rejection.get("cause") in EXECUTABLE_REJECTION_CAUSES
    )
    rejection_causes = _count_rejection_causes(rejections)
    slices = _build_slices(dataset_version, samples, rejections)

    return {
        "schema_version": "quality_report_v1",
        "dataset_version": dataset_version,
        "counts": {
            "total": total_count,
            "accepted": len(samples),
            "rejected": len(rejections),
            "executable": executable_count,
        },
        "rates": {
            "success_rate": _rate(len(samples), total_count),
            "executable_rate": _rate(executable_count, total_count),
        },
        "rejection_causes": rejection_causes,
        "slices": slices,
    }


def duplicate_signature(sample: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    task = _mapping(sample.get("task"))
    instruction = _normalize_instruction(task.get("instruction"))
    tools = tuple(
        str(event.get("tool"))
        for event in _sequence(sample.get("trajectory"))
        if isinstance(event, Mapping) and event.get("type") == "action" and event.get("tool")
    )
    return (instruction, tools)


def candidate_duplicate_signature(
    *,
    instruction: str,
    trajectory: list[dict[str, object]],
) -> tuple[str, tuple[str, ...]]:
    return (
        _normalize_instruction(instruction),
        tuple(
            str(event.get("tool"))
            for event in trajectory
            if event.get("type") == "action" and event.get("tool")
        ),
    )


def final_answer_is_logically_supported(sample: Mapping[str, Any]) -> bool:
    expected_answer = _expected_answer(sample)
    if not expected_answer:
        return False
    final_response = str(sample.get("final_response", ""))
    if expected_answer not in final_response:
        return False

    observations = [
        event.get("observation")
        for event in _sequence(sample.get("trajectory"))
        if isinstance(event, Mapping) and event.get("type") == "observation"
    ]
    if not observations:
        return False
    return any(expected_answer in json.dumps(observation, ensure_ascii=False, sort_keys=True) for observation in observations)


def build_parent_comparison(
    *,
    current: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> dict[str, object]:
    current_counts = _report_counts(current)
    parent_counts = _report_counts(parent)
    current_rates = _report_rates(current)
    parent_rates = _report_rates(parent)

    return {
        "schema_version": "parent_comparison_v1",
        "parent_dataset_version": parent.get("dataset_version"),
        "current_dataset_version": current.get("dataset_version"),
        "accepted_count_delta": current_counts["accepted"] - parent_counts["accepted"],
        "rejected_count_delta": current_counts["rejected"] - parent_counts["rejected"],
        "success_rate_delta": round(current_rates["success_rate"] - parent_rates["success_rate"], 10),
        "executable_rate_delta": round(
            current_rates["executable_rate"] - parent_rates["executable_rate"],
            10,
        ),
        "new_slice_keys": _slice_key_delta(current, parent),
        "removed_slice_keys": _slice_key_delta(parent, current),
        "rejection_cause_deltas": _rejection_cause_deltas(current, parent),
    }


def build_review_record(
    *,
    candidate_id: str,
    cause: str,
    task: Mapping[str, Any],
    uncertainty_reason: str,
    source_artifact: str,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, object]:
    return {
        "schema_version": "human_review_record_v1",
        "candidate_id": candidate_id,
        "cause": cause,
        "task": dict(task),
        "uncertainty_reason": uncertainty_reason,
        "source_artifact": source_artifact,
        "created_at": created_at,
    }


def retry_eligible(cause: str) -> bool:
    return cause in RETRYABLE_REJECTION_CAUSES


def reviewable(cause: str) -> bool:
    return cause in REVIEWABLE_REJECTION_CAUSES


def _build_slices(
    dataset_version: str,
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, object]:
    dimensions: dict[str, dict[str, dict[str, int]]] = {
        "dataset_version": {},
        "domain": {},
        "task_type": {},
        "difficulty_level": {},
        "tool_combination": {},
        "generator_role": {},
        "verifier_type": {},
        "rejection_cause": {},
        "curriculum_level": {},
    }
    for sample in samples:
        _add_slice(dimensions["dataset_version"], str(sample.get("dataset_version", dataset_version)), accepted=True)
        _add_slice(dimensions["domain"], _sample_domain(sample), accepted=True)
        _add_slice(dimensions["task_type"], _task_type(_mapping(sample.get("task"))), accepted=True)
        _add_slice(dimensions["difficulty_level"], _difficulty_level(_mapping(sample.get("task"))), accepted=True)
        _add_slice(dimensions["curriculum_level"], _difficulty_level(_mapping(sample.get("task"))), accepted=True)
        _add_slice(dimensions["tool_combination"], _tool_combination(sample), accepted=True)
        _add_slice(dimensions["generator_role"], _generator_role(sample), accepted=True)
        _add_slice(dimensions["verifier_type"], _verifier_type(sample), accepted=True)

    for rejection in rejections:
        task = _mapping(rejection.get("task"))
        cause = str(rejection.get("cause", "unknown"))
        _add_slice(dimensions["dataset_version"], dataset_version, accepted=False)
        _add_slice(dimensions["task_type"], _task_type(task), accepted=False)
        _add_slice(dimensions["difficulty_level"], _difficulty_level(task), accepted=False)
        _add_slice(dimensions["curriculum_level"], _difficulty_level(task), accepted=False)
        _add_slice(dimensions["tool_combination"], _rejection_tool_combination(task), accepted=False)
        _add_slice(dimensions["rejection_cause"], cause, accepted=False)

    return {
        dimension: {key: _with_rates(counts) for key, counts in sorted(values.items())}
        for dimension, values in sorted(dimensions.items())
    }


def _add_slice(
    values: dict[str, dict[str, int]],
    key: str,
    *,
    accepted: bool,
) -> None:
    normalized_key = key or "unknown"
    counts = values.setdefault(normalized_key, {"total": 0, "accepted": 0, "rejected": 0})
    counts["total"] += 1
    if accepted:
        counts["accepted"] += 1
    else:
        counts["rejected"] += 1


def _with_rates(counts: dict[str, int]) -> dict[str, object]:
    return {
        "total": counts["total"],
        "accepted": counts["accepted"],
        "rejected": counts["rejected"],
        "success_rate": _rate(counts["accepted"], counts["total"]),
    }


def _count_rejection_causes(rejections: list[dict[str, object]]) -> dict[str, int]:
    causes: dict[str, int] = {}
    for rejection in rejections:
        cause = str(rejection.get("cause", "unknown"))
        causes[cause] = causes.get(cause, 0) + 1
    return dict(sorted(causes.items()))


def _normalize_instruction(raw: object) -> str:
    return re.sub(r"\s+", " ", str(raw or "").strip().lower())


def _sample_domain(sample: Mapping[str, Any]) -> str:
    environment = _mapping(sample.get("environment"))
    environment_id = str(environment.get("id", "unknown"))
    return environment_id.removesuffix("_fixture")


def _task_type(task: Mapping[str, Any]) -> str:
    constraints = _mapping(task.get("constraints"))
    if constraints.get("task_type"):
        return str(constraints["task_type"])
    if constraints.get("must_use_tool"):
        return str(constraints["must_use_tool"])
    return "unknown"


def _difficulty_level(task: Mapping[str, Any]) -> str:
    difficulty = _mapping(task.get("difficulty"))
    return str(difficulty.get("level", "unknown"))


def _tool_combination(sample: Mapping[str, Any]) -> str:
    tools = [
        str(event.get("tool"))
        for event in _sequence(sample.get("trajectory"))
        if isinstance(event, Mapping) and event.get("type") == "action" and event.get("tool")
    ]
    return " > ".join(tools) if tools else "none"


def _rejection_tool_combination(task: Mapping[str, Any]) -> str:
    constraints = _mapping(task.get("constraints"))
    return str(constraints.get("must_use_tool", "unknown"))


def _generator_role(sample: Mapping[str, Any]) -> str:
    lineage = _mapping(sample.get("lineage"))
    generator = _mapping(lineage.get("generator"))
    return str(generator.get("role", "unknown"))


def _verifier_type(sample: Mapping[str, Any]) -> str:
    verifier = _mapping(sample.get("verifier"))
    return str(verifier.get("id", "unknown"))


def _expected_answer(sample: Mapping[str, Any]) -> str | None:
    verification = _mapping(sample.get("verification"))
    for check in _sequence(verification.get("checks")):
        if isinstance(check, Mapping) and check.get("passed") and check.get("expected"):
            return str(check["expected"])
    return None


def _report_counts(report: Mapping[str, Any]) -> dict[str, int]:
    if isinstance(report.get("counts"), Mapping):
        counts = _mapping(report.get("counts"))
        return {
            "accepted": int(counts.get("accepted", 0)),
            "rejected": int(counts.get("rejected", 0)),
        }
    return {
        "accepted": int(report.get("accepted_count", 0)),
        "rejected": int(report.get("rejected_count", 0)),
    }


def _report_rates(report: Mapping[str, Any]) -> dict[str, float]:
    rates_source = report.get("rates")
    if not isinstance(rates_source, Mapping):
        rates_source = report.get("quality")
    rates = _mapping(rates_source)
    return {
        "success_rate": float(rates.get("success_rate", 0.0)),
        "executable_rate": float(rates.get("executable_rate", 0.0)),
    }


def _slice_key_delta(source: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, list[str]]:
    source_slices = _mapping(source.get("slices"))
    baseline_slices = _mapping(baseline.get("slices"))
    result: dict[str, list[str]] = {}
    for dimension, raw_keys in sorted(source_slices.items()):
        if not isinstance(raw_keys, Mapping):
            continue
        baseline_keys = baseline_slices.get(dimension, {})
        if not isinstance(baseline_keys, Mapping):
            baseline_keys = {}
        new_keys = sorted(set(raw_keys) - set(baseline_keys))
        if new_keys:
            result[str(dimension)] = new_keys
    return result


def _rejection_cause_deltas(
    current: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> dict[str, int]:
    current_causes = _mapping(current.get("rejection_causes"))
    parent_causes = _mapping(parent.get("rejection_causes"))
    deltas: dict[str, int] = {}
    for cause in sorted(set(current_causes) | set(parent_causes)):
        delta = int(current_causes.get(cause, 0)) - int(parent_causes.get(cause, 0))
        if delta:
            deltas[str(cause)] = delta
    return deltas


def _mapping(raw: object) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    return {}


def _sequence(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
