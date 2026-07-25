from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

from synthesis.mutation_admission import validate_mutation_admission_evidence


MUTATION_ADMISSION_REPORT_SCHEMA_VERSION = "mutation_admission_report_v1"
MUTATION_ADMISSION_REPORT_FILENAME = "mutation_admission_report.json"
MUTATION_ADMISSION_DIMENSIONS = (
    "domain",
    "task_type",
    "action",
    "provenance",
    "verdict",
    "reason",
    "provider_outcome",
    "model_independence",
)
_PROVENANCE_BY_REASON = {
    "argument_literal_supported": "instruction",
    "argument_semantic_supported": "instruction",
    "observation_reference_supported": "tool_observation",
    "declared_default_supported": "declared_default",
    "deterministic_derivation_supported": "deterministic_derivation",
    "instruction_span_invalid": "instruction",
    "observation_reference_invalid": "tool_observation",
    "declared_default_invalid": "declared_default",
    "deterministic_derivation_invalid": "deterministic_derivation",
}
_PROHIBITED_RETAINED_KEYS = {
    "chain_of_thought",
    "credentials",
    "headers",
    "prompt",
    "raw_prompt",
    "raw_response",
    "response",
}
_PROHIBITED_RETAINED_KEY_FRAGMENTS = (
    "api_key",
    "authorization_header",
    "credential",
    "provider_payload",
    "provider_prompt",
    "raw_judge",
    "secret",
)
_PROHIBITED_RETAINED_VALUE_MARKERS = (
    "agent_data_api_key",
    "authorization:",
    "secret-test-key",
    "sk-live",
    "sk-test",
)
_PROVENANCE_BY_REFERENCE_PREFIX = {
    "instruction.": "instruction",
    "observation.": "tool_observation",
    "default.": "declared_default",
    "derivation.": "deterministic_derivation",
}


def build_mutation_admission_report(
    *,
    dataset_version: str,
    samples: Iterable[Mapping[str, object]],
    rejections: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    dimension_counts = {
        dimension: Counter[str]()
        for dimension in MUTATION_ADMISSION_DIMENSIONS
    }
    accepted = 0
    rejected = 0
    state_changing = 0
    read_only = 0
    missing = 0

    for outcome, records in (("accepted", samples), ("rejected", rejections)):
        for record in records:
            evidence = _admission_evidence(record, outcome=outcome)
            if evidence is None:
                missing += 1
                continue
            validate_mutation_admission_evidence(evidence)
            validate_retained_admission_material(evidence)
            if outcome == "accepted":
                accepted += 1
            else:
                rejected += 1
            if evidence.get("classification") == "state_changing":
                state_changing += 1
            else:
                read_only += 1
            dimensions = _record_dimensions(record, evidence)
            for dimension in MUTATION_ADMISSION_DIMENSIONS:
                values = dimensions[dimension]
                for value in values:
                    dimension_counts[dimension][value] += 1

    report: dict[str, object] = {
        "schema_version": MUTATION_ADMISSION_REPORT_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "counts": {
            "evidence_records": accepted + rejected,
            "accepted": accepted,
            "rejected": rejected,
            "state_changing": state_changing,
            "read_only": read_only,
            "missing_evidence": missing,
        },
        "dimensions": {
            dimension: [
                {"value": value, "count": count}
                for value, count in sorted(dimension_counts[dimension].items())
            ]
            for dimension in MUTATION_ADMISSION_DIMENSIONS
        },
    }
    validate_mutation_admission_report(report)
    return report


def write_mutation_admission_report(
    *,
    dataset_version: str,
    samples: Iterable[Mapping[str, object]],
    rejections: Iterable[Mapping[str, object]],
    output_path: Path,
) -> Path:
    report = build_mutation_admission_report(
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
    )
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def validate_mutation_admission_report(raw: object) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("mutation_admission_report must be an object")
    if set(raw) != {"schema_version", "dataset_version", "counts", "dimensions"}:
        raise ValueError("mutation_admission_report keys are invalid")
    if raw.get("schema_version") != MUTATION_ADMISSION_REPORT_SCHEMA_VERSION:
        raise ValueError("mutation_admission_report schema_version is unsupported")
    if not isinstance(raw.get("dataset_version"), str) or not raw.get("dataset_version"):
        raise ValueError("mutation_admission_report dataset_version is invalid")
    counts = raw.get("counts")
    expected_counts = {
        "evidence_records",
        "accepted",
        "rejected",
        "state_changing",
        "read_only",
        "missing_evidence",
    }
    if not isinstance(counts, Mapping) or set(counts) != expected_counts:
        raise ValueError("mutation_admission_report counts are invalid")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counts.values()
    ):
        raise ValueError("mutation_admission_report count is invalid")
    if counts["evidence_records"] != counts["accepted"] + counts["rejected"]:
        raise ValueError("mutation_admission_report outcome counts are inconsistent")
    if counts["evidence_records"] != counts["state_changing"] + counts["read_only"]:
        raise ValueError("mutation_admission_report classification counts are inconsistent")

    dimensions = raw.get("dimensions")
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(
        MUTATION_ADMISSION_DIMENSIONS
    ):
        raise ValueError("mutation_admission_report dimensions are invalid")
    for dimension in MUTATION_ADMISSION_DIMENSIONS:
        rows = dimensions.get(dimension)
        if not isinstance(rows, list):
            raise ValueError(f"mutation_admission_report {dimension} rows are invalid")
        previous = ""
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"value", "count"}:
                raise ValueError(
                    f"mutation_admission_report {dimension} row is invalid"
                )
            value = row.get("value")
            count = row.get("count")
            if (
                not isinstance(value, str)
                or not value
                or value <= previous
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count <= 0
            ):
                raise ValueError(
                    f"mutation_admission_report {dimension} row is invalid"
                )
            previous = value
    validate_retained_admission_material(raw)


def validate_retained_admission_material(raw: object) -> None:
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            lowered = str(key).lower()
            if (
                lowered in _PROHIBITED_RETAINED_KEYS
                or lowered in {"observation", "observations"}
                or any(
                    fragment in lowered
                    for fragment in _PROHIBITED_RETAINED_KEY_FRAGMENTS
                )
            ):
                raise ValueError("retained mutation admission material is prohibited")
            validate_retained_admission_material(value)
        return
    if isinstance(raw, list):
        for value in raw:
            validate_retained_admission_material(value)
        return
    if isinstance(raw, str):
        lowered = raw.lower()
        if any(marker in lowered for marker in _PROHIBITED_RETAINED_VALUE_MARKERS):
            raise ValueError("retained mutation admission material is prohibited")


def validate_retained_release_material(raw: object) -> None:
    _validate_retained_release_material(raw)


def _validate_retained_release_material(raw: object) -> None:
    if isinstance(raw, Mapping):
        trajectory = raw.get("trajectory")
        if isinstance(trajectory, list):
            _validate_trajectory_observation_references(trajectory)
        for key, value in raw.items():
            lowered = str(key).lower()
            if (
                lowered in _PROHIBITED_RETAINED_KEYS
                or any(
                    fragment in lowered
                    for fragment in _PROHIBITED_RETAINED_KEY_FRAGMENTS
                )
            ):
                raise ValueError("retained release material is prohibited")
            if lowered in {"observation", "observations"} and not (
                lowered == "observation"
                and raw.get("type") == "observation"
            ):
                raise ValueError("retained release material is prohibited")
            _validate_retained_release_material(value)
        return
    if isinstance(raw, list):
        for value in raw:
            _validate_retained_release_material(value)
        return
    if isinstance(raw, str):
        lowered = raw.lower()
        if any(marker in lowered for marker in _PROHIBITED_RETAINED_VALUE_MARKERS):
            raise ValueError("retained release material is prohibited")


def _validate_trajectory_observation_references(
    trajectory: list[object],
) -> None:
    for index, event in enumerate(trajectory):
        if not isinstance(event, Mapping) or event.get("type") != "observation":
            continue
        previous = trajectory[index - 1] if index > 0 else None
        if (
            not isinstance(previous, Mapping)
            or previous.get("type") != "action"
            or previous.get("tool") != event.get("tool")
        ):
            raise ValueError("retained release material is prohibited")


def _admission_evidence(
    record: Mapping[str, object],
    *,
    outcome: str,
) -> Mapping[str, object] | None:
    raw = (
        record.get("mutation_admission")
        if outcome == "accepted"
        else _nested_admission_evidence(record)
    )
    return raw if isinstance(raw, Mapping) else None


def _nested_admission_evidence(
    record: Mapping[str, object],
) -> object:
    details = record.get("details")
    if not isinstance(details, Mapping):
        return None
    return details.get("mutation_admission")


def _record_dimensions(
    record: Mapping[str, object],
    evidence: Mapping[str, object],
) -> dict[str, tuple[str, ...]]:
    task = record.get("task")
    constraints = task.get("constraints") if isinstance(task, Mapping) else None
    domain = (
        constraints.get("domain")
        if isinstance(constraints, Mapping)
        else None
    )
    if not isinstance(domain, str) or not domain:
        environment = record.get("environment")
        domain = environment.get("id") if isinstance(environment, Mapping) else None
    task_type = (
        constraints.get("task_type")
        if isinstance(constraints, Mapping)
        else None
    )
    verdict = evidence.get("semantic_verdict")
    action_findings = (
        verdict.get("action_findings")
        if isinstance(verdict, Mapping)
        else None
    )
    actions = _finding_values(action_findings, "action_type")
    if not actions:
        actions = _declared_action_values(record, evidence)
    reason_codes = _reason_codes(evidence, verdict)
    provenances = _provenance_origins(evidence, verdict, reason_codes)
    if not provenances:
        provenances = _provenance_fallback(evidence)
    judge_call = evidence.get("judge_call")
    provider_outcome = (
        judge_call.get("outcome")
        if isinstance(judge_call, Mapping)
        else "not_called"
    )
    semantic_verdict = (
        verdict.get("verdict")
        if isinstance(verdict, Mapping)
        else evidence.get("admission_outcome")
    )
    return {
        "domain": (_dimension_value(domain),),
        "task_type": (_dimension_value(task_type),),
        "action": actions or ("not_available",),
        "provenance": provenances or ("not_available",),
        "verdict": (_dimension_value(semantic_verdict),),
        "reason": reason_codes or ("none",),
        "provider_outcome": (_dimension_value(provider_outcome),),
        "model_independence": (
            _dimension_value(evidence.get("model_independence")),
        ),
    }


def _finding_values(raw: object, key: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        sorted(
            {
                str(finding[key])
                for finding in raw
                if isinstance(finding, Mapping)
                and isinstance(finding.get(key), str)
                and finding.get(key)
            }
        )
    )


def _declared_action_values(
    record: Mapping[str, object],
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    if evidence.get("classification") == "read_only":
        return ("not_applicable",)
    tools = record.get("tools")
    state_changing_tools = {
        str(tool.get("name"))
        for tool in tools
        if isinstance(tool, Mapping)
        and tool.get("side_effects") == "state_mutating"
    } if isinstance(tools, list) else set()
    trajectory = record.get("trajectory")
    if isinstance(trajectory, list):
        actions = {
            str(event.get("tool"))
            for event in trajectory
            if isinstance(event, Mapping)
            and event.get("type") == "action"
            and event.get("tool") in state_changing_tools
        }
        if actions:
            return tuple(sorted(actions))
    task = record.get("task")
    constraints = task.get("constraints") if isinstance(task, Mapping) else None
    required_tools = (
        constraints.get("required_tools")
        if isinstance(constraints, Mapping)
        else None
    )
    if isinstance(required_tools, list) and required_tools:
        last_tool = required_tools[-1]
        if isinstance(last_tool, str) and last_tool:
            return (last_tool,)
    return ()


def _provenance_fallback(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    if evidence.get("classification") == "read_only":
        return ("not_applicable",)
    validation = evidence.get("deterministic_validation")
    status = validation.get("status") if isinstance(validation, Mapping) else None
    if status == "passed":
        return ("not_available",)
    if status == "not_evaluated":
        return ("not_evaluated",)
    return ()


def _provenance_origins(
    evidence: Mapping[str, object],
    verdict: object,
    reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    references: list[str] = []
    if isinstance(verdict, Mapping):
        findings = verdict.get("argument_findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, Mapping):
                    continue
                raw_references = finding.get("evidence_references")
                if isinstance(raw_references, list):
                    references.extend(
                        str(reference)
                        for reference in raw_references
                        if isinstance(reference, str)
                    )
    validation = evidence.get("deterministic_validation")
    if isinstance(validation, Mapping):
        findings = validation.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, Mapping):
                    continue
                raw_references = finding.get("evidence_references")
                if isinstance(raw_references, list):
                    references.extend(
                        str(reference)
                        for reference in raw_references
                        if isinstance(reference, str)
                    )
    origins = {
        origin
        for reference in references
        for prefix, origin in _PROVENANCE_BY_REFERENCE_PREFIX.items()
        if reference.startswith(prefix)
    }
    origins.update(
        _PROVENANCE_BY_REASON[reason]
        for reason in reason_codes
        if reason in _PROVENANCE_BY_REASON
    )
    return tuple(sorted(origins))


def _reason_codes(
    evidence: Mapping[str, object],
    verdict: object,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    validation = evidence.get("deterministic_validation")
    if isinstance(validation, Mapping):
        raw_reasons = validation.get("reason_codes")
        if isinstance(raw_reasons, list):
            reasons.update(str(reason) for reason in raw_reasons if reason)
    if isinstance(verdict, Mapping):
        raw_reasons = verdict.get("reason_codes")
        if isinstance(raw_reasons, list):
            reasons.update(str(reason) for reason in raw_reasons if reason)
    return tuple(sorted(reasons))


def _dimension_value(raw: object) -> str:
    return raw if isinstance(raw, str) and raw else "not_available"
