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
    "llm_provider_error",
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
            "refined_attempted": _refined_attempted_count(samples, rejections),
            "refined_accepted": _refined_accepted_count(samples),
            "refined_rejected": _refined_rejected_count(rejections),
            "capability_gaps": _capability_gap_count(samples, rejections),
            "tool_proposals": _tool_proposal_count(samples, rejections),
        },
        "rates": {
            "success_rate": _rate(len(samples), total_count),
            "executable_rate": _rate(executable_count, total_count),
        },
        "rejection_causes": rejection_causes,
        "role_outcomes": _build_role_outcomes(samples, rejections),
        "tool_proposal_outcomes": _tool_proposal_outcomes(samples, rejections),
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
        "refinement_status": {},
        "role_name": {},
        "role_output_type": {},
        "capability_gap_type": {},
        "proposed_tool": {},
        "proposed_tool_side_effect": {},
        "tool_proposal_outcome": {},
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
        _add_slice(dimensions["refinement_status"], _sample_refinement_status(sample), accepted=True)
        for lineage in _sample_role_lineages(sample):
            _add_slice(dimensions["role_name"], _role_name(lineage), accepted=True)
            _add_slice(dimensions["role_output_type"], _role_output_type(lineage), accepted=True)
        for expansion in _sample_tool_expansions(sample):
            _add_tool_expansion_slices(dimensions, expansion, accepted=True)

    for rejection in rejections:
        task = _mapping(rejection.get("task"))
        cause = str(rejection.get("cause", "unknown"))
        _add_slice(dimensions["dataset_version"], dataset_version, accepted=False)
        _add_slice(dimensions["task_type"], _task_type(task), accepted=False)
        _add_slice(dimensions["difficulty_level"], _difficulty_level(task), accepted=False)
        _add_slice(dimensions["curriculum_level"], _difficulty_level(task), accepted=False)
        _add_slice(dimensions["tool_combination"], _rejection_tool_combination(task), accepted=False)
        _add_slice(dimensions["rejection_cause"], cause, accepted=False)
        _add_slice(
            dimensions["refinement_status"],
            _rejection_refinement_status(rejection),
            accepted=False,
        )
        for lineage in _rejection_role_lineages(rejection):
            _add_slice(dimensions["role_name"], _role_name(lineage), accepted=False)
            _add_slice(dimensions["role_output_type"], _role_output_type(lineage), accepted=False)
        for expansion in _rejection_tool_expansions(rejection):
            _add_tool_expansion_slices(dimensions, expansion, accepted=False)

    return {
        dimension: {key: _with_rates(counts) for key, counts in sorted(values.items())}
        for dimension, values in sorted(dimensions.items())
    }


def _build_role_outcomes(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, object]:
    outcomes: dict[str, dict[str, Any]] = {}
    for sample in samples:
        for lineage in _sample_role_lineages(sample):
            _add_role_outcome(outcomes, lineage, accepted=True)
    for rejection in rejections:
        for lineage in _rejection_role_lineages(rejection):
            _add_role_outcome(outcomes, lineage, accepted=False)
    return {
        role: {
            "attempted": values["attempted"],
            "accepted": values["accepted"],
            "rejected": values["rejected"],
            "retry_count": values["retry_count"],
            "tokens": dict(sorted(values["tokens"].items())),
            "cost": dict(sorted(values["cost"].items())),
            "output_types": sorted(values["output_types"]),
        }
        for role, values in sorted(outcomes.items())
    }


def _add_tool_expansion_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    expansion: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    gap = _mapping(expansion.get("gap"))
    proposal = _mapping(expansion.get("proposal"))
    admission = _mapping(expansion.get("admission"))
    if gap:
        _add_slice(dimensions["capability_gap_type"], str(gap.get("gap_type", "unknown")), accepted=accepted)
    if proposal:
        _add_slice(dimensions["proposed_tool"], str(proposal.get("tool_name", "unknown")), accepted=accepted)
        _add_slice(
            dimensions["proposed_tool_side_effect"],
            str(proposal.get("side_effects", "unknown")),
            accepted=accepted,
        )
    if admission:
        _add_slice(dimensions["tool_proposal_outcome"], str(admission.get("outcome", "unknown")), accepted=accepted)


def _add_role_outcome(
    outcomes: dict[str, dict[str, Any]],
    lineage: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    role = _role_name(lineage)
    values = outcomes.setdefault(
        role,
        {
            "attempted": 0,
            "accepted": 0,
            "rejected": 0,
            "retry_count": 0,
            "tokens": {},
            "cost": {},
            "output_types": set(),
        },
    )
    values["attempted"] += 1
    if accepted:
        values["accepted"] += 1
    else:
        values["rejected"] += 1
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        values["retry_count"] += retry_count
    values["output_types"].add(_role_output_type(lineage))
    _add_numeric_mapping(values["tokens"], _mapping(lineage.get("tokens")))
    _add_numeric_mapping(values["cost"], _mapping(lineage.get("cost")))


def _add_numeric_mapping(target: dict[str, int | float], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        name = str(key)
        target[name] = target.get(name, 0) + value


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


def _refined_accepted_count(samples: list[dict[str, object]]) -> int:
    return sum(1 for sample in samples if _sample_refinement_status(sample) == "refined_accepted")


def _refined_rejected_count(rejections: list[dict[str, object]]) -> int:
    return sum(
        1
        for rejection in rejections
        if _rejection_refinement_status(rejection) == "refined_rejected"
    )


def _refined_attempted_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return _refined_accepted_count(samples) + _refined_rejected_count(rejections)


def _capability_gap_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return sum(1 for sample in samples for _ in _sample_tool_expansions(sample)) + sum(
        1
        for rejection in rejections
        if _mapping(_mapping(rejection.get("details")).get("capability_gap"))
    )


def _tool_proposal_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return sum(1 for sample in samples for _ in _sample_tool_expansions(sample)) + sum(
        1
        for rejection in rejections
        for _ in _rejection_tool_expansions(rejection)
    )


def _tool_proposal_outcomes(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for expansion in [
        *[expansion for sample in samples for expansion in _sample_tool_expansions(sample)],
        *[expansion for rejection in rejections for expansion in _rejection_tool_expansions(rejection)],
    ]:
        outcome = str(_mapping(expansion.get("admission")).get("outcome", "unknown"))
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return dict(sorted(outcomes.items()))


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


def _sample_role_lineages(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    role_lineages = [
        role_lineage
        for role_lineage in (
            _mapping(lineage.get("generator")),
            _mapping(lineage.get("solution_policy")),
            _mapping(lineage.get("refinement")),
        )
        if role_lineage
    ]
    for expansion in _sample_tool_expansions(sample):
        proposal_lineage = _mapping(_mapping(expansion.get("proposal")).get("lineage"))
        if proposal_lineage:
            role_lineages.append(proposal_lineage)
    return role_lineages


def _rejection_role_lineages(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    lineages: list[Mapping[str, Any]] = []
    direct_lineage = _mapping(details.get("lineage"))
    if direct_lineage:
        lineages.append(direct_lineage)
    role_lineages = details.get("role_lineages")
    if isinstance(role_lineages, Mapping):
        for raw_lineage in role_lineages.values():
            lineage = _mapping(raw_lineage)
            if lineage:
                lineages.append(lineage)
    elif isinstance(role_lineages, list):
        for raw_lineage in role_lineages:
            lineage = _mapping(raw_lineage)
            if lineage:
                lineages.append(lineage)
    refinement = _mapping(details.get("refinement"))
    refinement_lineage = _mapping(refinement.get("lineage"))
    if refinement_lineage:
        lineages.append(refinement_lineage)
    for expansion in _rejection_tool_expansions(rejection):
        proposal_lineage = _mapping(_mapping(expansion.get("proposal")).get("lineage"))
        if proposal_lineage:
            lineages.append(proposal_lineage)
    return lineages


def _sample_tool_expansions(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    expansion = _mapping(lineage.get("tool_expansion"))
    return [expansion] if expansion else []


def _rejection_tool_expansions(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    expansion = _mapping(details.get("tool_proposal"))
    return [expansion] if expansion else []


def _role_name(lineage: Mapping[str, Any]) -> str:
    return str(lineage.get("role", "unknown"))


def _role_output_type(lineage: Mapping[str, Any]) -> str:
    return str(lineage.get("output_type", "unknown"))


def _verifier_type(sample: Mapping[str, Any]) -> str:
    verifier = _mapping(sample.get("verifier"))
    return str(verifier.get("id", "unknown"))


def _sample_refinement_status(sample: Mapping[str, Any]) -> str:
    lineage = _mapping(sample.get("lineage"))
    if isinstance(lineage.get("refinement"), Mapping):
        return "refined_accepted"
    return "unrefined"


def _rejection_refinement_status(rejection: Mapping[str, Any]) -> str:
    details = _mapping(rejection.get("details"))
    if isinstance(details.get("refinement"), Mapping):
        return "refined_rejected"
    return "unrefined"


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
