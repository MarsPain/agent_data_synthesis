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
    sandbox_audits: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    sandbox_audits = sandbox_audits or []
    total_count = len(samples) + len(rejections)
    executable_count = len(samples) + sum(
        1 for rejection in rejections if rejection.get("cause") in EXECUTABLE_REJECTION_CAUSES
    )
    rejection_causes = _count_rejection_causes(rejections)
    slices = _build_slices(dataset_version, samples, rejections, sandbox_audits)

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
            "branch_attempts": _branch_attempt_count(samples, rejections),
            "branch_selected": _branch_selected_count(samples),
            "seed_transformations": _seed_transformation_count(samples, rejections),
            "task_suggestions": _task_suggestion_count(samples, rejections),
            "task_edits": _task_edit_count(samples, rejections),
        },
        "rates": {
            "success_rate": _rate(len(samples), executable_count),
            "executable_rate": _rate(executable_count, total_count),
        },
        "rejection_causes": rejection_causes,
        "role_outcomes": _build_role_outcomes(samples, rejections),
        "tool_proposal_outcomes": _tool_proposal_outcomes(samples, rejections),
        "branch_outcomes": _branch_outcomes(samples, rejections),
        "branch_failure_causes": _branch_failure_causes(samples, rejections),
        "suggestion_outcomes": _suggestion_outcomes(rejections),
        "editor_actions": _editor_actions(samples, rejections),
        "edit_rejection_causes": _edit_rejection_causes(rejections),
        "sandbox_admission_outcomes": _sandbox_admission_outcomes(sandbox_audits),
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
    sandbox_audits: list[dict[str, object]],
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
        "branch_depth": {},
        "selected_branch": {},
        "branch_outcome": {},
        "fallback_count": {},
        "seed_transformation_type": {},
        "taxonomy_node": {},
        "suggestion_outcome": {},
        "editor_action": {},
        "edit_rejection_cause": {},
        "source_kind": {},
        "license_policy_outcome": {},
        "external_source_eligibility": {},
        "source_rejection_cause": {},
        "environment_source_admission": {},
        "adapter_id": {},
        "adapter_protocol": {},
        "adapter_execution_outcome": {},
        "adapter_rejection_cause": {},
        "sandbox_artifact_kind": {},
        "sandbox_scan_status": {},
        "sandbox_admission_outcome": {},
        "sandbox_rejection_cause": {},
        "sandbox_execution_status": {},
        "run_profile_id": {},
        "generation_mode": {},
        "run_profile_schema_version": {},
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
        for branching in _sample_branching(sample):
            _add_branching_slices(dimensions, branching, accepted=True)
        for transformation in _sample_seed_transformations(sample):
            _add_seed_transformation_slices(dimensions, transformation, accepted=True)
        if _mapping(_mapping(sample.get("lineage")).get("task_suggester")):
            _add_slice(dimensions["suggestion_outcome"], "accepted", accepted=True)
        for editor in _sample_task_editors(sample):
            _add_slice(
                dimensions["editor_action"],
                str(editor.get("editor_action", "unknown")),
                accepted=True,
            )
        _add_source_governance_slices(
            dimensions,
            _sample_source_provenance(sample),
            accepted=True,
        )
        for adapter in _sample_adapter_lineages(sample):
            _add_adapter_slices(dimensions, adapter, accepted=True)
        _add_run_profile_slices(
            dimensions,
            _sample_run_profile_attribution(sample),
            accepted=True,
        )

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
        for branching in _rejection_branching(rejection):
            _add_branching_slices(dimensions, branching, accepted=False)
        for transformation in _rejection_seed_transformations(rejection):
            _add_seed_transformation_slices(dimensions, transformation, accepted=False)
        for suggestion in _rejection_task_suggestions(rejection):
            _add_slice(
                dimensions["taxonomy_node"],
                str(suggestion.get("target_taxonomy_node", "unknown")),
                accepted=False,
            )
            _add_slice(
                dimensions["suggestion_outcome"],
                str(suggestion.get("outcome", "unknown")),
                accepted=False,
            )
            if suggestion.get("rejection_reason"):
                _add_slice(
                    dimensions["edit_rejection_cause"],
                    str(suggestion["rejection_reason"]),
                    accepted=False,
                )
        for editor in _rejection_task_editors(rejection):
            _add_slice(
                dimensions["editor_action"],
                str(editor.get("editor_action", "unknown")),
                accepted=False,
            )
        _add_source_governance_slices(
            dimensions,
            _rejection_source_governance(rejection),
            accepted=False,
        )
        for adapter in _rejection_adapter_lineages(rejection):
            _add_adapter_slices(dimensions, adapter, accepted=False)
        _add_run_profile_slices(
            dimensions,
            _rejection_run_profile_attribution(rejection),
            accepted=False,
        )

    for audit in sandbox_audits:
        _add_sandbox_audit_slices(dimensions, audit)

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


def _add_branching_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    branching: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    _add_slice(dimensions["branch_depth"], str(branching.get("branch_depth", "unknown")), accepted=accepted)
    _add_slice(
        dimensions["selected_branch"],
        str(branching.get("selected_branch_id", "none")),
        accepted=accepted,
    )
    _add_slice(dimensions["fallback_count"], str(branching.get("fallback_count", "0")), accepted=accepted)
    for outcome in _sequence(branching.get("branch_outcomes")):
        if isinstance(outcome, Mapping):
            _add_slice(
                dimensions["branch_outcome"],
                str(outcome.get("outcome", "unknown")),
                accepted=accepted,
            )


def _add_seed_transformation_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    transformation: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    _add_slice(
        dimensions["seed_transformation_type"],
        str(transformation.get("transformation_type", "unknown")),
        accepted=accepted,
    )
    _add_slice(
        dimensions["taxonomy_node"],
        str(transformation.get("target_taxonomy_node", "unknown")),
        accepted=accepted,
    )


def _add_source_governance_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    provenance: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    if not provenance:
        return
    for source_kind in _sequence(provenance.get("source_kinds")):
        _add_slice(dimensions["source_kind"], str(source_kind), accepted=accepted)
    for outcome in _sequence(provenance.get("license_outcomes")):
        _add_slice(dimensions["license_policy_outcome"], str(outcome), accepted=accepted)
    eligibility = "eligible" if provenance.get("external_source_eligible") else "ineligible"
    _add_slice(dimensions["external_source_eligibility"], eligibility, accepted=accepted)
    for cause in _sequence(provenance.get("rejection_causes")):
        _add_slice(dimensions["source_rejection_cause"], str(cause), accepted=accepted)
    if provenance.get("environment_source_admission"):
        _add_slice(
            dimensions["environment_source_admission"],
            str(provenance.get("environment_source_admission")),
            accepted=accepted,
        )


def _add_adapter_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    adapter: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    _add_slice(dimensions["adapter_id"], str(adapter.get("adapter_id", "unknown")), accepted=accepted)
    _add_slice(
        dimensions["adapter_protocol"],
        str(adapter.get("protocol_label", "unknown")),
        accepted=accepted,
    )
    _add_slice(
        dimensions["adapter_execution_outcome"],
        str(adapter.get("execution_status", "unknown")),
        accepted=accepted,
    )
    rejection_cause = adapter.get("rejection_cause")
    if rejection_cause:
        _add_slice(dimensions["adapter_rejection_cause"], str(rejection_cause), accepted=accepted)


def _add_sandbox_audit_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    audit: Mapping[str, Any],
) -> None:
    artifact = _mapping(audit.get("artifact"))
    scan = _mapping(audit.get("scan"))
    admission = _mapping(audit.get("admission"))
    execution = _mapping(audit.get("execution"))
    accepted = bool(admission.get("accepted"))
    if artifact:
        _add_slice(
            dimensions["sandbox_artifact_kind"],
            str(artifact.get("artifact_kind", "unknown")),
            accepted=accepted,
        )
    if scan:
        _add_slice(
            dimensions["sandbox_scan_status"],
            str(scan.get("status", "unknown")),
            accepted=accepted,
        )
    if admission:
        outcome = "accepted" if admission.get("accepted") else "rejected"
        _add_slice(dimensions["sandbox_admission_outcome"], outcome, accepted=accepted)
        rejection_cause = admission.get("rejection_cause")
        if rejection_cause:
            _add_slice(
                dimensions["sandbox_rejection_cause"],
                str(rejection_cause),
                accepted=accepted,
            )
    if execution:
        _add_slice(
            dimensions["sandbox_execution_status"],
            str(execution.get("status", "unknown")),
            accepted=accepted,
        )


def _add_run_profile_slices(
    dimensions: dict[str, dict[str, dict[str, int]]],
    attribution: Mapping[str, Any],
    *,
    accepted: bool,
) -> None:
    if not attribution:
        return
    profile_id = attribution.get("profile_id")
    if profile_id:
        _add_slice(dimensions["run_profile_id"], str(profile_id), accepted=accepted)
    generation_mode = attribution.get("generation_mode")
    if generation_mode:
        _add_slice(dimensions["generation_mode"], str(generation_mode), accepted=accepted)
    profile_schema_version = attribution.get("profile_schema_version")
    if profile_schema_version:
        _add_slice(
            dimensions["run_profile_schema_version"],
            str(profile_schema_version),
            accepted=accepted,
        )


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


def _sandbox_admission_outcomes(sandbox_audits: list[dict[str, object]]) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for audit in sandbox_audits:
        admission = _mapping(audit.get("admission"))
        if not admission:
            continue
        outcome = "accepted" if admission.get("accepted") else "rejected"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return dict(sorted(outcomes.items()))


def _branch_attempt_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return sum(
        len(_sequence(branching.get("branch_outcomes")))
        for sample in samples
        for branching in _sample_branching(sample)
    ) + sum(
        len(_sequence(branching.get("branch_outcomes")))
        for rejection in rejections
        for branching in _rejection_branching(rejection)
    )


def _branch_selected_count(samples: list[dict[str, object]]) -> int:
    return sum(
        1
        for sample in samples
        for branching in _sample_branching(sample)
        for outcome in _sequence(branching.get("branch_outcomes"))
        if isinstance(outcome, Mapping) and outcome.get("selected")
    )


def _branch_outcomes(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for branching in [
        *[branching for sample in samples for branching in _sample_branching(sample)],
        *[branching for rejection in rejections for branching in _rejection_branching(rejection)],
    ]:
        for outcome in _sequence(branching.get("branch_outcomes")):
            if not isinstance(outcome, Mapping):
                continue
            name = str(outcome.get("outcome", "unknown"))
            outcomes[name] = outcomes.get(name, 0) + 1
    return dict(sorted(outcomes.items()))


def _branch_failure_causes(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, int]:
    causes: dict[str, int] = {}
    for branching in [
        *[branching for sample in samples for branching in _sample_branching(sample)],
        *[branching for rejection in rejections for branching in _rejection_branching(rejection)],
    ]:
        for outcome in _sequence(branching.get("branch_outcomes")):
            if not isinstance(outcome, Mapping):
                continue
            cause = outcome.get("failure_cause")
            if not cause:
                continue
            name = str(cause)
            causes[name] = causes.get(name, 0) + 1
    return dict(sorted(causes.items()))


def _seed_transformation_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return sum(
        1 for sample in samples for _ in _sample_seed_transformations(sample)
    ) + sum(
        1 for rejection in rejections for _ in _rejection_seed_transformations(rejection)
    )


def _task_suggestion_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    accepted = sum(
        1
        for sample in samples
        if _mapping(_mapping(sample.get("lineage")).get("task_suggester"))
    )
    rejected = sum(
        1 for rejection in rejections for _ in _rejection_task_suggestions(rejection)
    )
    return accepted + rejected


def _task_edit_count(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> int:
    return sum(1 for sample in samples for _ in _sample_task_editors(sample)) + sum(
        1 for rejection in rejections for _ in _rejection_task_editors(rejection)
    )


def _suggestion_outcomes(rejections: list[dict[str, object]]) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for suggestion in [
        suggestion
        for rejection in rejections
        for suggestion in _rejection_task_suggestions(rejection)
    ]:
        outcome = str(suggestion.get("outcome", "unknown"))
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return dict(sorted(outcomes.items()))


def _editor_actions(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, int]:
    actions: dict[str, int] = {}
    for editor in [
        *[editor for sample in samples for editor in _sample_task_editors(sample)],
        *[editor for rejection in rejections for editor in _rejection_task_editors(rejection)],
    ]:
        action = str(editor.get("editor_action", "unknown"))
        actions[action] = actions.get(action, 0) + 1
    return dict(sorted(actions.items()))


def _edit_rejection_causes(rejections: list[dict[str, object]]) -> dict[str, int]:
    causes: dict[str, int] = {}
    for suggestion in [
        suggestion
        for rejection in rejections
        for suggestion in _rejection_task_suggestions(rejection)
    ]:
        reason = suggestion.get("rejection_reason")
        if not reason:
            continue
        name = str(reason)
        causes[name] = causes.get(name, 0) + 1
    for editor in [
        editor
        for rejection in rejections
        for editor in _rejection_task_editors(rejection)
    ]:
        rejection = _mapping(editor.get("rejection"))
        cause = rejection.get("cause")
        if not cause:
            continue
        name = str(cause)
        causes[name] = causes.get(name, 0) + 1
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


def _sample_role_lineages(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    role_lineages = [
        role_lineage
        for role_lineage in (
            _mapping(lineage.get("generator")),
            _mapping(lineage.get("solution_policy")),
            _mapping(lineage.get("refinement")),
            _mapping(lineage.get("task_suggester")),
            _mapping(lineage.get("task_editor")),
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


def _sample_branching(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    branching = _mapping(lineage.get("branching"))
    return [branching] if branching else []


def _sample_seed_transformations(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    transformation = _mapping(lineage.get("seed_transformation"))
    return [transformation] if transformation else []


def _sample_task_editors(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    editor = _mapping(lineage.get("task_editor"))
    return [editor] if editor else []


def _sample_source_provenance(sample: Mapping[str, Any]) -> Mapping[str, Any]:
    lineage = _mapping(sample.get("lineage"))
    return _mapping(lineage.get("source_provenance"))


def _sample_adapter_lineages(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    lineage = _mapping(sample.get("lineage"))
    adapters = lineage.get("adapter")
    if isinstance(adapters, list):
        return [_mapping(adapter) for adapter in adapters if _mapping(adapter)]
    return []


def _sample_run_profile_attribution(sample: Mapping[str, Any]) -> Mapping[str, Any]:
    lineage = _mapping(sample.get("lineage"))
    return _mapping(lineage.get("run_profile"))


def _rejection_tool_expansions(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    expansion = _mapping(details.get("tool_proposal"))
    return [expansion] if expansion else []


def _rejection_branching(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    branch_outcomes = _sequence(details.get("branch_outcomes"))
    if not branch_outcomes:
        return []
    selected = next(
        (outcome for outcome in branch_outcomes if isinstance(outcome, Mapping) and outcome.get("selected")),
        {},
    )
    depth_values = [
        outcome.get("depth")
        for outcome in branch_outcomes
        if isinstance(outcome, Mapping) and isinstance(outcome.get("depth"), int)
    ]
    selected_depth = selected.get("depth") if isinstance(selected, Mapping) else None
    branch_depth = selected_depth if isinstance(selected_depth, int) else max(depth_values, default=0)
    return [
        {
            "schema_version": "branch_lineage_v1",
            "plan_id": "unknown_branch_plan",
            "selected_branch_id": str(selected.get("branch_id", "none")) if isinstance(selected, Mapping) else "none",
            "branch_depth": branch_depth,
            "fallback_count": sum(
                1
                for outcome in branch_outcomes
                if isinstance(outcome, Mapping) and not outcome.get("selected")
            ),
            "branch_outcomes": branch_outcomes,
        }
    ]


def _rejection_seed_transformations(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    transformation = _mapping(details.get("seed_transformation"))
    return [transformation] if transformation else []


def _rejection_task_suggestions(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    suggestion = _mapping(details.get("task_suggestion"))
    return [suggestion] if suggestion else []


def _rejection_task_editors(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    editor = _mapping(details.get("task_editor"))
    return [editor] if editor else []


def _rejection_source_governance(rejection: Mapping[str, Any]) -> Mapping[str, Any]:
    details = _mapping(rejection.get("details"))
    return _mapping(details.get("source_governance"))


def _rejection_adapter_lineages(rejection: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details = _mapping(rejection.get("details"))
    adapter = _mapping(details.get("adapter_rejection"))
    return [adapter] if adapter else []


def _rejection_run_profile_attribution(rejection: Mapping[str, Any]) -> Mapping[str, Any]:
    details = _mapping(rejection.get("details"))
    return _mapping(details.get("run_profile"))


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
