from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, TypedDict

from synthesis.coverage import canonical_coverage_hash


STRUCTURAL_TAXONOMY_SCHEMA_VERSION = "representative_structural_taxonomy_v1"
STRUCTURAL_TAXONOMY_ID = "representative_structural_taxonomy"
STRUCTURAL_TAXONOMY_VERSION = "representative_structural_taxonomy_v1"
STRUCTURAL_TAXONOMY_COMPARISON_VERSION = "structural_taxonomy_comparison_v1"

_TAXONOMY_DEFINITION = {
    "schema_version": STRUCTURAL_TAXONOMY_SCHEMA_VERSION,
    "taxonomy_id": STRUCTURAL_TAXONOMY_ID,
    "version": STRUCTURAL_TAXONOMY_VERSION,
    "features": [
        "domain",
        "task_type",
        "required_tool_sequence",
        "primary_selector_fields",
        "state_behavior",
        "cross_step_bindings",
        "recovery_signature",
    ],
    "excluded_features": [
        "coverage_assignment",
        "coverage_cell_id",
        "instruction_text",
        "provider_identity",
    ],
}


@dataclass(frozen=True)
class StructuralClassification:
    status: str
    family_id: str | None
    features: Mapping[str, object]
    unclassifiable_reason: str | None = None


class StructuralSummary(TypedDict):
    total_count: int
    classified_count: int
    unclassifiable_count: int
    unclassifiable_reasons: dict[str, int]
    distinct_family_count: int
    largest_family_count: int
    largest_family_share: float
    family_counts: dict[str, int]


def structural_taxonomy_identity() -> dict[str, object]:
    return {
        **_TAXONOMY_DEFINITION,
        "taxonomy_hash": canonical_coverage_hash(_TAXONOMY_DEFINITION),
    }


def classify_structural_sample(
    sample: Mapping[str, object],
) -> StructuralClassification:
    task = sample.get("task")
    constraints = task.get("constraints") if isinstance(task, Mapping) else None
    if not isinstance(constraints, Mapping):
        return _unclassifiable("missing_task_constraints")

    domain = constraints.get("domain")
    task_type = constraints.get("task_type")
    required_tools = constraints.get("required_tools")
    if (
        not isinstance(domain, str)
        or not domain
        or not isinstance(task_type, str)
        or not task_type
        or not isinstance(required_tools, list)
        or not required_tools
        or any(not isinstance(tool, str) or not tool for tool in required_tools)
    ):
        return _unclassifiable("invalid_task_constraints")

    trajectory = sample.get("trajectory")
    if not isinstance(trajectory, list):
        return _unclassifiable("missing_trajectory")
    actions = [
        item
        for item in trajectory
        if isinstance(item, Mapping) and item.get("type") == "action"
    ]
    if not actions:
        return _unclassifiable("missing_action")
    first_arguments = actions[0].get("arguments")
    if not isinstance(first_arguments, Mapping) or any(
        not isinstance(key, str) for key in first_arguments
    ):
        return _unclassifiable("invalid_primary_arguments")

    recovery_signature = _recovery_signature(sample)
    if recovery_signature is None:
        return _unclassifiable("invalid_branch_lineage")
    features = {
        "domain": domain,
        "task_type": task_type,
        "required_tool_sequence": list(required_tools),
        "primary_selector_fields": sorted(str(key) for key in first_arguments),
        "state_behavior": (
            "state_changing"
            if any(
                isinstance(item, Mapping)
                and item.get("type") == "state_change"
                for item in trajectory
            )
            else "read_only"
        ),
        "cross_step_bindings": _cross_step_bindings(trajectory),
        "recovery_signature": recovery_signature,
    }
    family_hash = canonical_coverage_hash(features).removeprefix("sha256:")
    return StructuralClassification(
        status="classified",
        family_id=f"structural_family_{family_hash[:16]}",
        features=features,
    )


def build_structural_taxonomy_comparison(
    *,
    comparison_id: str,
    baseline_samples: Iterable[Mapping[str, object]],
    campaign_samples: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    if not isinstance(comparison_id, str) or not comparison_id:
        raise ValueError("structural taxonomy comparison id must not be empty")
    baseline = _summarize_samples(baseline_samples)
    campaign = _summarize_samples(campaign_samples)
    return {
        "schema_version": STRUCTURAL_TAXONOMY_COMPARISON_VERSION,
        "comparison_id": comparison_id,
        "taxonomy": structural_taxonomy_identity(),
        "baseline": baseline,
        "campaign": campaign,
        "like_for_like": {
            "classified_count_delta": (
                campaign["classified_count"]
                - baseline["classified_count"]
            ),
            "distinct_family_count_delta": (
                campaign["distinct_family_count"]
                - baseline["distinct_family_count"]
            ),
            "largest_family_share_delta": (
                campaign["largest_family_share"]
                - baseline["largest_family_share"]
            ),
        },
    }


def write_structural_taxonomy_comparison(
    *,
    comparison_id: str,
    baseline_samples_path: Path,
    campaign_samples_path: Path,
    output_path: Path,
) -> Path:
    report = build_structural_taxonomy_comparison(
        comparison_id=comparison_id,
        baseline_samples=_load_jsonl_samples(baseline_samples_path),
        campaign_samples=_load_jsonl_samples(campaign_samples_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _load_jsonl_samples(path: Path) -> list[Mapping[str, object]]:
    samples: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, Mapping):
            raise ValueError("structural taxonomy sample must be an object")
        samples.append(record)
    return samples


def _summarize_samples(
    samples: Iterable[Mapping[str, object]],
) -> StructuralSummary:
    family_counts: Counter[str] = Counter()
    unclassifiable_reasons: Counter[str] = Counter()
    total_count = 0
    for sample in samples:
        total_count += 1
        classification = classify_structural_sample(sample)
        if classification.status == "classified":
            assert classification.family_id is not None
            family_counts[classification.family_id] += 1
        else:
            assert classification.unclassifiable_reason is not None
            unclassifiable_reasons[classification.unclassifiable_reason] += 1

    classified_count = sum(family_counts.values())
    largest_family_count = max(family_counts.values(), default=0)
    return {
        "total_count": total_count,
        "classified_count": classified_count,
        "unclassifiable_count": sum(unclassifiable_reasons.values()),
        "unclassifiable_reasons": dict(sorted(unclassifiable_reasons.items())),
        "distinct_family_count": len(family_counts),
        "largest_family_count": largest_family_count,
        "largest_family_share": (
            largest_family_count / classified_count
            if classified_count
            else 0.0
        ),
        "family_counts": dict(sorted(family_counts.items())),
    }


def _unclassifiable(reason: str) -> StructuralClassification:
    return StructuralClassification(
        status="unclassifiable",
        family_id=None,
        features={},
        unclassifiable_reason=reason,
    )


def _cross_step_bindings(trajectory: list[object]) -> list[str]:
    prior_observations: list[tuple[str, Mapping[str, object]]] = []
    bindings: set[str] = set()
    for item in trajectory:
        if not isinstance(item, Mapping):
            continue
        tool_name = item.get("tool")
        if not isinstance(tool_name, str):
            continue
        if item.get("type") == "observation":
            observation = item.get("observation")
            if isinstance(observation, Mapping):
                prior_observations.append((tool_name, observation))
            continue
        if item.get("type") != "action":
            continue
        arguments = item.get("arguments")
        if not isinstance(arguments, Mapping):
            continue
        for argument_name, argument_value in arguments.items():
            if not isinstance(argument_name, str) or not _is_binding_scalar(
                argument_value
            ):
                continue
            for observation_tool, observation in prior_observations:
                for field_name, observed_value in observation.items():
                    if (
                        isinstance(field_name, str)
                        and _is_binding_scalar(observed_value)
                        and observed_value == argument_value
                    ):
                        bindings.add(
                            f"{observation_tool}.{field_name}"
                            f"->{tool_name}.{argument_name}"
                        )
    return sorted(bindings)


def _is_binding_scalar(value: object) -> bool:
    return isinstance(value, (str, int, float, bool)) and value != ""


def _recovery_signature(sample: Mapping[str, object]) -> str | None:
    lineage = sample.get("lineage")
    branching = lineage.get("branching") if isinstance(lineage, Mapping) else None
    if branching is None:
        return "none"
    if not isinstance(branching, Mapping):
        return None
    outcomes = branching.get("branch_outcomes")
    if not isinstance(outcomes, list):
        return None
    rejected_action = _branch_action(outcomes, outcome="rejected")
    accepted_action = _branch_action(outcomes, outcome="accepted")
    if rejected_action is None or accepted_action is None:
        return None
    rejected_arguments = rejected_action.get("arguments")
    accepted_arguments = accepted_action.get("arguments")
    if not isinstance(rejected_arguments, Mapping) or not isinstance(
        accepted_arguments,
        Mapping,
    ):
        return None
    return _argument_change_signature(
        rejected_arguments,
        accepted_arguments,
    )


def _branch_action(
    outcomes: list[object],
    *,
    outcome: str,
) -> Mapping[str, object] | None:
    for item in outcomes:
        if not isinstance(item, Mapping) or item.get("outcome") != outcome:
            continue
        trajectory = item.get("trajectory")
        if not isinstance(trajectory, list):
            return None
        for event in trajectory:
            if (
                isinstance(event, Mapping)
                and event.get("type") == "action"
            ):
                return event
    return None


def _argument_change_signature(
    rejected: Mapping[object, object],
    accepted: Mapping[object, object],
) -> str:
    rejected_keys = {str(key) for key in rejected if isinstance(key, str)}
    accepted_keys = {str(key) for key in accepted if isinstance(key, str)}
    parts = [
        "removed:" + ",".join(sorted(rejected_keys - accepted_keys)),
        "added:" + ",".join(sorted(accepted_keys - rejected_keys)),
    ]
    for key in sorted(rejected_keys & accepted_keys):
        before = rejected[key]
        after = accepted[key]
        if before != after:
            parts.append(f"changed:{key}:{_value_change_kind(before, after)}")
    return "|".join(parts)


def _value_change_kind(before: object, after: object) -> str:
    if not isinstance(before, str) or not isinstance(after, str):
        return "replaced"
    before_tokens = before.casefold().split()
    after_tokens = after.casefold().split()
    if before_tokens == list(reversed(after_tokens)):
        return "restored_token_order"
    if len(before_tokens) < len(after_tokens):
        return "expanded_tokens"
    if len(before_tokens) > len(after_tokens):
        return "reduced_tokens"
    normalized_before = "".join(character for character in before if character.isalnum())
    normalized_after = "".join(character for character in after if character.isalnum())
    if normalized_before.casefold() == normalized_after.casefold():
        return "normalized_punctuation"
    if "@" in before and "@" not in after:
        return "replaced_email_selector"
    return "replaced_value"
