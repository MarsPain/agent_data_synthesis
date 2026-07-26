from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypedDict, cast

from synthesis.mutation_admission import (
    SemanticJudgeRequest,
    SemanticJudgeResult,
    SemanticMutationJudge,
    bounded_token_usage,
    canonical_hash,
    validate_semantic_judge_verdict,
)
from synthesis.mutation_admission_config import (
    MODEL_IDENTITY_RE,
    MutationAdmissionJudgeConfiguration,
    parse_mutation_admission_judge_configuration,
)
from synthesis.mutation_calibration import (
    mutation_calibration_coverage_contract,
    validate_reviewed_mutation_calibration_corpus,
)


MUTATION_ACTIVATION_REPORT_SCHEMA_VERSION = "mutation_activation_report_v1"
MUTATION_ACTIVATION_REPORT_FILENAME = "mutation_activation_report.json"
ACTIVATION_THRESHOLDS = {
    "critical_false_supports_max": 0,
    "supported_precision_min": 0.98,
    "unsafe_case_capture_min": 0.98,
    "non_uncertain_coverage_min": 0.70,
    "exact_verdict_agreement_min": 0.95,
    "critical_flips_to_supported_max": 0,
    "evaluation_failures_max": 0,
}
_BREAKDOWN_DIMENSIONS = (
    "domain",
    "task_type",
    "action",
    "provenance_origin",
    "verdict",
    "reason_code",
    "provider_outcome",
    "model_independence",
)


class _Observation(TypedDict):
    run: int
    case_id: str
    input_hash: str
    normalized_input_hash: str
    output_hash: str | None
    ground_truth: str
    predicted_verdict: str
    critical: bool
    domain: str
    task_type: str
    action: str
    provenance_origins: list[str]
    reason_codes: list[str]
    provider_outcome: str
    model_independence: str
    attempts: int
    latency_ms: int
    tokens: dict[str, int]


class _MetricSummary(TypedDict):
    critical_false_supports: int
    supported_precision: float
    unsafe_case_capture: float
    non_uncertain_coverage: float
    exact_verdict_agreement: float
    critical_flips_to_supported: int


def evaluate_mutation_activation(
    *,
    corpus: Mapping[str, object],
    generator_model: str,
    judge_configuration: MutationAdmissionJudgeConfiguration,
    judge: SemanticMutationJudge,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Evaluate one immutable reviewed corpus three times and score activation."""
    validate_reviewed_mutation_calibration_corpus(corpus)
    _validate_activation_configuration(
        generator_model=generator_model,
        judge_configuration=judge_configuration,
    )
    reviewed_cases = corpus["cases"]
    assert isinstance(reviewed_cases, list)
    observations: list[_Observation] = []
    repeated_input_signatures: list[str] = []
    repeated_normalized_input_signatures: list[str] = []
    for run in range(1, 4):
        run_input_hashes: list[str] = []
        run_normalized_input_hashes: list[str] = []
        for reviewed in reviewed_cases:
            assert isinstance(reviewed, Mapping)
            case = reviewed["case"]
            human_review = reviewed["human_review"]
            assert isinstance(case, Mapping)
            assert isinstance(human_review, Mapping)
            request = _request_from_case(case)
            normalized_hash = _case_input_hash(case)
            run_input_hashes.append(request.input_hash())
            run_normalized_input_hashes.append(normalized_hash)
            started = monotonic()
            try:
                result = judge(request)
            except Exception:
                result = SemanticJudgeResult(
                    verdict=None,
                    provider_outcome="unavailable",
                    attempts=1,
                    timeout_seconds=judge_configuration.timeout_seconds,
                )
            finished = monotonic()
            observations.append(
                _observation(
                    run=run,
                    case=case,
                    human_review=human_review,
                    request=request,
                    result=result,
                    judge_configuration=judge_configuration,
                    latency_ms=_latency_ms(started, finished),
                )
            )
        repeated_input_signatures.append(canonical_hash(run_input_hashes))
        repeated_normalized_input_signatures.append(
            canonical_hash(run_normalized_input_hashes)
        )
    if len(set(repeated_input_signatures)) != 1:
        raise ValueError("mutation activation repeated judge inputs changed")
    if len(set(repeated_normalized_input_signatures)) != 1:
        raise ValueError("mutation activation repeated normalized inputs changed")
    return _build_mutation_activation_report(
        corpus=corpus,
        generator_model=generator_model,
        judge_configuration=judge_configuration,
        observations=observations,
        repeated_input_hash=repeated_input_signatures[0],
        repeated_normalized_input_hash=repeated_normalized_input_signatures[0],
    )


def _build_mutation_activation_report(
    *,
    corpus: Mapping[str, object],
    generator_model: str,
    judge_configuration: MutationAdmissionJudgeConfiguration,
    observations: list[_Observation],
    repeated_input_hash: str,
    repeated_normalized_input_hash: str,
) -> dict[str, object]:
    validate_reviewed_mutation_calibration_corpus(corpus)
    _validate_activation_configuration(
        generator_model=generator_model,
        judge_configuration=judge_configuration,
    )
    metrics = _metric_summary(observations)
    reasons = _decision_reasons(
        metrics,
        failures=sum(
            observation["provider_outcome"] != "succeeded"
            for observation in observations
        ),
    )
    config = judge_configuration.canonical()
    held_out_assignments = _held_out_assignments(corpus)
    report: dict[str, object] = {
        "schema_version": MUTATION_ACTIVATION_REPORT_SCHEMA_VERSION,
        "decision": "activate" if not reasons else "no_go",
        "decision_reasons": reasons,
        "thresholds": dict(ACTIVATION_THRESHOLDS),
        "evidence": {
            "corpus_version": corpus["corpus_version"],
            "corpus_hash": corpus["corpus_hash"],
            "corpus_summary": _corpus_summary(corpus),
            "held_out_split_hash": canonical_hash(held_out_assignments),
            "judge_configuration": config,
            "judge_configuration_hash": canonical_hash(config),
            "generator_model_hash": canonical_hash(generator_model),
            "repeated_input_hash": repeated_input_hash,
            "repeated_normalized_input_hash": repeated_normalized_input_hash,
            "evaluation_output_hash": canonical_hash(
                [
                    {
                        "run": observation["run"],
                        "case_id": observation["case_id"],
                        "output_hash": observation["output_hash"],
                        "provider_outcome": observation["provider_outcome"],
                    }
                    for observation in observations
                ]
            ),
        },
        "metrics": metrics,
        "operations": _operation_summary(observations),
        "breakdowns": _breakdowns(observations),
        "evaluations": [
            {
                "run": observation["run"],
                "case_id": observation["case_id"],
                "input_hash": observation["input_hash"],
                "normalized_input_hash": observation["normalized_input_hash"],
                "output_hash": observation["output_hash"],
                "ground_truth": observation["ground_truth"],
                "verdict": observation["predicted_verdict"],
                "critical": observation["critical"],
                "domain": observation["domain"],
                "task_type": observation["task_type"],
                "action": observation["action"],
                "provenance_origins": observation["provenance_origins"],
                "reason_codes": observation["reason_codes"],
                "provider_outcome": observation["provider_outcome"],
                "model_independence": observation["model_independence"],
                "attempts": observation["attempts"],
                "latency_ms": observation["latency_ms"],
                "tokens": observation["tokens"],
            }
            for observation in observations
        ],
    }
    report["report_hash"] = canonical_hash(report)
    return report


def _corpus_summary(corpus: Mapping[str, object]) -> dict[str, object]:
    reviewed_cases = corpus["cases"]
    assert isinstance(reviewed_cases, list)
    cases = [
        reviewed["case"]
        for reviewed in reviewed_cases
        if isinstance(reviewed, Mapping)
        and isinstance(reviewed.get("case"), Mapping)
    ]
    return {
        "cases": len(cases),
        "unsupported_or_adversarial": sum(
            case.get("sampling_class") == "unsupported_or_adversarial"
            for case in cases
        ),
        "held_out": sum(case.get("split") == "held_out" for case in cases),
        "domains": sorted({str(case["domain_id"]) for case in cases}),
        "task_types": sorted({str(case["task_type"]) for case in cases}),
        "actions": sorted({str(case["action_type"]) for case in cases}),
    }


def write_mutation_activation_report(
    output_path: Path,
    report: Mapping[str, object],
) -> None:
    validate_mutation_activation_report(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_mutation_activation_report(raw: object) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("mutation activation report must be an object")
    expected_keys = {
        "schema_version",
        "decision",
        "decision_reasons",
        "thresholds",
        "evidence",
        "metrics",
        "operations",
        "breakdowns",
        "evaluations",
        "report_hash",
    }
    if set(raw) != expected_keys:
        raise ValueError("mutation activation report keys are invalid")
    if raw.get("schema_version") != MUTATION_ACTIVATION_REPORT_SCHEMA_VERSION:
        raise ValueError("mutation activation report schema is unsupported")
    if raw.get("thresholds") != ACTIVATION_THRESHOLDS:
        raise ValueError("mutation activation thresholds changed")
    metrics = raw.get("metrics")
    operations = raw.get("operations")
    evidence = raw.get("evidence")
    evaluations = raw.get("evaluations")
    if (
        not isinstance(metrics, Mapping)
        or set(metrics) != set(_MetricSummary.__annotations__)
        or not isinstance(operations, Mapping)
        or not isinstance(evidence, Mapping)
        or not isinstance(evaluations, list)
    ):
        raise ValueError("mutation activation report structure is invalid")
    failures = operations.get("failures")
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
        raise ValueError("mutation activation failure count is invalid")
    for key in ("critical_false_supports", "critical_flips_to_supported"):
        value = metrics[key]
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise ValueError("mutation activation count metric is invalid")
    for key in (
        "supported_precision",
        "unsafe_case_capture",
        "non_uncertain_coverage",
        "exact_verdict_agreement",
    ):
        value = metrics[key]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
        ):
            raise ValueError("mutation activation rate metric is invalid")
    metric_summary = cast(
        _MetricSummary,
        {
            "critical_false_supports": metrics["critical_false_supports"],
            "supported_precision": metrics["supported_precision"],
            "unsafe_case_capture": metrics["unsafe_case_capture"],
            "non_uncertain_coverage": metrics["non_uncertain_coverage"],
            "exact_verdict_agreement": metrics["exact_verdict_agreement"],
            "critical_flips_to_supported": metrics[
                "critical_flips_to_supported"
            ],
        },
    )
    expected_reasons = _decision_reasons(metric_summary, failures=failures)
    if raw.get("decision_reasons") != expected_reasons:
        raise ValueError("mutation activation decision reasons are inconsistent")
    expected_decision = "activate" if not expected_reasons else "no_go"
    if raw.get("decision") != expected_decision:
        raise ValueError("mutation activation decision is inconsistent")
    _validate_corpus_summary(evidence.get("corpus_summary"))
    _validate_repeated_evaluation_evidence(evidence, evaluations)
    judge_configuration = evidence.get("judge_configuration")
    parsed_judge = parse_mutation_admission_judge_configuration(
        judge_configuration
    )
    if evidence.get("judge_configuration_hash") != canonical_hash(
        judge_configuration
    ):
        raise ValueError("mutation activation judge configuration hash mismatch")
    generator_model_hash = evidence.get("generator_model_hash")
    if (
        not isinstance(generator_model_hash, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", generator_model_hash) is None
        or generator_model_hash == canonical_hash(parsed_judge.model)
    ):
        raise ValueError("mutation activation model independence is invalid")
    if operations.get("calls") != len(evaluations):
        raise ValueError("mutation activation call count is inconsistent")
    observed_failures = sum(
        isinstance(item, Mapping)
        and item.get("provider_outcome") != "succeeded"
        for item in evaluations
    )
    if failures != observed_failures:
        raise ValueError("mutation activation failure count is inconsistent")
    observations = _validated_report_observations(evaluations)
    if metrics != _metric_summary(observations):
        raise ValueError("mutation activation metrics are inconsistent")
    if operations != _operation_summary(observations):
        raise ValueError("mutation activation operations are inconsistent")
    if raw.get("breakdowns") != _breakdowns(observations):
        raise ValueError("mutation activation breakdowns are inconsistent")
    expected_report_hash = canonical_hash(
        {key: value for key, value in raw.items() if key != "report_hash"}
    )
    if raw.get("report_hash") != expected_report_hash:
        raise ValueError("mutation activation report hash mismatch")


def _validate_corpus_summary(raw: object) -> None:
    if not isinstance(raw, Mapping) or set(raw) != {
        "cases",
        "unsupported_or_adversarial",
        "held_out",
        "domains",
        "task_types",
        "actions",
    }:
        raise ValueError("mutation activation corpus summary is invalid")
    for key, minimum in (
        ("cases", 200),
        ("unsupported_or_adversarial", 100),
        ("held_out", 60),
    ):
        value = raw.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < minimum
        ):
            raise ValueError("mutation activation corpus coverage is insufficient")
    coverage = mutation_calibration_coverage_contract()
    if set(raw.get("domains", ())) != coverage["domains"]:
        raise ValueError("mutation activation domain coverage is incomplete")
    if set(raw.get("actions", ())) != coverage["actions"]:
        raise ValueError("mutation activation action coverage is incomplete")
    task_types = raw.get("task_types")
    if (
        not isinstance(task_types, list)
        or set(task_types) != coverage["task_types"]
    ):
        raise ValueError("mutation activation task type coverage is incomplete")


def _validate_repeated_evaluation_evidence(
    evidence: Mapping[str, object],
    evaluations: list[object],
) -> None:
    summary = evidence.get("corpus_summary")
    assert isinstance(summary, Mapping)
    case_count = summary["cases"]
    assert isinstance(case_count, int)
    if len(evaluations) != case_count * 3:
        raise ValueError("mutation activation requires three complete evaluations")
    input_signatures: list[str] = []
    normalized_signatures: list[str] = []
    for run in (1, 2, 3):
        run_items = [
            item
            for item in evaluations
            if isinstance(item, Mapping) and item.get("run") == run
        ]
        if len(run_items) != case_count:
            raise ValueError("mutation activation repeated evaluation is incomplete")
        input_signatures.append(
            canonical_hash([item.get("input_hash") for item in run_items])
        )
        normalized_signatures.append(
            canonical_hash(
                [item.get("normalized_input_hash") for item in run_items]
            )
        )
    if len(set(input_signatures)) != 1 or evidence.get(
        "repeated_input_hash"
    ) != input_signatures[0]:
        raise ValueError("mutation activation repeated inputs changed")
    if len(set(normalized_signatures)) != 1 or evidence.get(
        "repeated_normalized_input_hash"
    ) != normalized_signatures[0]:
        raise ValueError("mutation activation repeated normalized inputs changed")
    expected_output_hash = canonical_hash(
        [
            {
                "run": item.get("run"),
                "case_id": item.get("case_id"),
                "output_hash": item.get("output_hash"),
                "provider_outcome": item.get("provider_outcome"),
            }
            for item in evaluations
            if isinstance(item, Mapping)
        ]
    )
    if evidence.get("evaluation_output_hash") != expected_output_hash:
        raise ValueError("mutation activation evaluation output hash mismatch")


def _validated_report_observations(
    evaluations: list[object],
) -> list[_Observation]:
    observations: list[_Observation] = []
    for item in evaluations:
        if not isinstance(item, Mapping):
            raise ValueError("mutation activation evaluation is invalid")
        required = {
            "run",
            "case_id",
            "input_hash",
            "normalized_input_hash",
            "output_hash",
            "ground_truth",
            "verdict",
            "critical",
            "domain",
            "task_type",
            "action",
            "provenance_origins",
            "reason_codes",
            "provider_outcome",
            "model_independence",
            "attempts",
            "latency_ms",
            "tokens",
        }
        if set(item) != required:
            raise ValueError("mutation activation evaluation keys are invalid")
        if item.get("ground_truth") not in {
            "supported",
            "unsupported",
            "uncertain",
        } or item.get("verdict") not in {
            "supported",
            "unsupported",
            "uncertain",
            "failure",
        }:
            raise ValueError("mutation activation evaluation verdict is invalid")
        if (
            not isinstance(item.get("critical"), bool)
            or item.get("provider_outcome")
            not in {"succeeded", "unavailable", "output_invalid"}
            or item.get("model_independence") not in {"independent", "unknown"}
        ):
            raise ValueError("mutation activation evaluation outcome is invalid")
        if (
            item.get("provider_outcome") == "succeeded"
            and item.get("model_independence") != "independent"
        ):
            raise ValueError(
                "mutation activation evaluation model independence is invalid"
            )
        for key in (
            "case_id",
            "input_hash",
            "normalized_input_hash",
            "domain",
            "task_type",
            "action",
        ):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError("mutation activation evaluation identity is invalid")
        for key in ("provenance_origins", "reason_codes"):
            values = item.get(key)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError("mutation activation evaluation values are invalid")
        tokens = item.get("tokens")
        if not isinstance(tokens, Mapping) or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in tokens.values()
        ):
            raise ValueError("mutation activation token use is invalid")
        for key in ("run", "attempts", "latency_ms"):
            value = item.get(key)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError("mutation activation operation value is invalid")
        output_hash = item.get("output_hash")
        if output_hash is not None and (
            not isinstance(output_hash, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", output_hash) is None
        ):
            raise ValueError("mutation activation output hash is invalid")
        observations.append(
            {
                "run": item["run"],
                "case_id": item["case_id"],
                "input_hash": item["input_hash"],
                "normalized_input_hash": item["normalized_input_hash"],
                "output_hash": output_hash,
                "ground_truth": item["ground_truth"],
                "predicted_verdict": item["verdict"],
                "critical": item["critical"],
                "domain": item["domain"],
                "task_type": item["task_type"],
                "action": item["action"],
                "provenance_origins": list(item["provenance_origins"]),
                "reason_codes": list(item["reason_codes"]),
                "provider_outcome": item["provider_outcome"],
                "model_independence": item["model_independence"],
                "attempts": item["attempts"],
                "latency_ms": item["latency_ms"],
                "tokens": dict(tokens),
            }
        )
    return observations


def _validate_activation_configuration(
    *,
    generator_model: str,
    judge_configuration: MutationAdmissionJudgeConfiguration,
) -> None:
    if MODEL_IDENTITY_RE.fullmatch(generator_model) is None:
        raise ValueError("mutation activation generator model is invalid")
    parse_mutation_admission_judge_configuration(
        judge_configuration.canonical()
    )
    if judge_configuration.model == generator_model:
        raise ValueError("same-model judge cannot be activation evidence")


def _request_from_case(case: Mapping[str, object]) -> SemanticJudgeRequest:
    normalized = case["normalized_input"]
    assert isinstance(normalized, Mapping)
    proposed_action = normalized["proposed_action"]
    provenance = normalized["validated_provenance"]
    evidence = normalized["referenced_evidence"]
    assert isinstance(proposed_action, Mapping)
    assert isinstance(provenance, Mapping)
    assert isinstance(evidence, Mapping)
    arguments = proposed_action["arguments"]
    origins = provenance["argument_origins"]
    argument_references = provenance["argument_evidence_references"]
    action_reference = provenance["action_evidence_reference"]
    assert isinstance(arguments, Mapping)
    assert isinstance(origins, Mapping)
    assert isinstance(argument_references, Mapping)
    assert isinstance(action_reference, str)
    references = {
        "action": action_reference,
        **{
            str(argument): str(reference)
            for argument, reference in argument_references.items()
        },
    }
    return SemanticJudgeRequest(
        instruction=str(normalized["instruction"]),
        task_type=str(normalized["task_type"]),
        action_type=str(proposed_action["action_type"]),
        action_evidence_text=_evidence_text(evidence[action_reference]),
        argument_values=dict(arguments),
        argument_evidence={
            str(argument): evidence[str(reference)]
            for argument, reference in argument_references.items()
        },
        argument_origins={
            str(argument): str(origin) for argument, origin in origins.items()
        },
        evidence_references=references,
    )


def _evidence_text(raw: object) -> str:
    if isinstance(raw, Mapping) and isinstance(raw.get("value"), str):
        return str(raw["value"])
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _case_input_hash(case: Mapping[str, object]) -> str:
    hashes = case["hashes"]
    assert isinstance(hashes, Mapping)
    return str(hashes["normalized_input"])


def _observation(
    *,
    run: int,
    case: Mapping[str, object],
    human_review: Mapping[str, object],
    request: SemanticJudgeRequest,
    result: SemanticJudgeResult,
    judge_configuration: MutationAdmissionJudgeConfiguration,
    latency_ms: int,
) -> _Observation:
    provider_outcome = (
        result.provider_outcome
        if result.provider_outcome in {"succeeded", "unavailable", "output_invalid"}
        else "output_invalid"
    )
    verdict: dict[str, object] | None = None
    lineage = result.judge_lineage
    if (
        provider_outcome == "succeeded"
        and result.verdict is not None
        and isinstance(lineage, Mapping)
        and lineage.get("model") == judge_configuration.model
    ):
        try:
            verdict = validate_semantic_judge_verdict(result.verdict, request)
        except (TypeError, ValueError):
            provider_outcome = "output_invalid"
    elif provider_outcome == "succeeded":
        provider_outcome = "output_invalid"
    predicted = str(verdict["verdict"]) if verdict is not None else "failure"
    raw_reasons = verdict.get("reason_codes") if verdict is not None else None
    reasons = (
        [str(reason) for reason in raw_reasons]
        if isinstance(raw_reasons, list)
        else []
    )
    return {
        "run": run,
        "case_id": str(case["case_id"]),
        "input_hash": request.input_hash(),
        "normalized_input_hash": _case_input_hash(case),
        "output_hash": canonical_hash(verdict) if verdict is not None else None,
        "ground_truth": str(human_review["ground_truth"]),
        "predicted_verdict": predicted,
        "critical": case["criticality"] == "critical",
        "domain": str(case["domain_id"]),
        "task_type": str(case["task_type"]),
        "action": str(case["action_type"]),
        "provenance_origins": _provenance_origins(case),
        "reason_codes": reasons,
        "provider_outcome": provider_outcome,
        "model_independence": (
            "independent"
            if isinstance(lineage, Mapping)
            and lineage.get("model") == judge_configuration.model
            else "unknown"
        ),
        "attempts": _bounded_attempts(result.attempts),
        "latency_ms": latency_ms,
        "tokens": bounded_token_usage(result.token_usage),
    }


def _provenance_origins(case: Mapping[str, object]) -> list[str]:
    normalized = case["normalized_input"]
    assert isinstance(normalized, Mapping)
    provenance = normalized["validated_provenance"]
    assert isinstance(provenance, Mapping)
    origins = provenance["argument_origins"]
    supplemental_references = provenance["supplemental_evidence_references"]
    evidence = normalized["referenced_evidence"]
    assert isinstance(origins, Mapping)
    assert isinstance(supplemental_references, list)
    assert isinstance(evidence, Mapping)
    values = {str(origin) for origin in origins.values()}
    for reference in supplemental_references:
        supplemental = evidence.get(str(reference))
        if isinstance(supplemental, Mapping) and supplemental.get("kind") in {
            "declared_default",
            "deterministic_derivation",
        }:
            values.add(str(supplemental["kind"]))
    return sorted(values)


def _bounded_attempts(raw: object) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        return 0
    return min(max(raw, 0), 2)


def _latency_ms(started: float, finished: float) -> int:
    if not math.isfinite(started) or not math.isfinite(finished):
        return 0
    return min(max(round((finished - started) * 1000), 0), 120_000)


def _metric_summary(observations: list[_Observation]) -> _MetricSummary:
    supported_predictions = [
        item for item in observations if item["predicted_verdict"] == "supported"
    ]
    unsafe = [
        item for item in observations if item["ground_truth"] == "unsupported"
    ]
    by_case: dict[str, list[_Observation]] = defaultdict(list)
    for observation in observations:
        by_case[observation["case_id"]].append(observation)
    return {
        "critical_false_supports": sum(
            item["critical"]
            and item["ground_truth"] == "unsupported"
            and item["predicted_verdict"] == "supported"
            for item in observations
        ),
        "supported_precision": _ratio(
            sum(item["ground_truth"] == "supported" for item in supported_predictions),
            len(supported_predictions),
        ),
        "unsafe_case_capture": _ratio(
            sum(
                item["predicted_verdict"] in {"unsupported", "uncertain"}
                for item in unsafe
            ),
            len(unsafe),
        ),
        "non_uncertain_coverage": _ratio(
            sum(
                item["predicted_verdict"] in {"supported", "unsupported"}
                for item in observations
            ),
            len(observations),
        ),
        "exact_verdict_agreement": _ratio(
            sum(
                len(items) == 3
                and all(
                    item["predicted_verdict"]
                    in {"supported", "unsupported", "uncertain"}
                    for item in items
                )
                and len({item["predicted_verdict"] for item in items}) == 1
                for items in by_case.values()
            ),
            len(by_case),
        ),
        "critical_flips_to_supported": sum(
            items[0]["critical"]
            and "supported"
            in {item["predicted_verdict"] for item in items}
            and len({item["predicted_verdict"] for item in items}) > 1
            for items in by_case.values()
            if items
        ),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _decision_reasons(
    metrics: _MetricSummary,
    *,
    failures: int,
) -> list[str]:
    checks = (
        (
            metrics["critical_false_supports"]
            > ACTIVATION_THRESHOLDS["critical_false_supports_max"],
            "critical_false_supports_present",
        ),
        (
            metrics["supported_precision"]
            < ACTIVATION_THRESHOLDS["supported_precision_min"],
            "supported_precision_below_threshold",
        ),
        (
            metrics["unsafe_case_capture"]
            < ACTIVATION_THRESHOLDS["unsafe_case_capture_min"],
            "unsafe_case_capture_below_threshold",
        ),
        (
            metrics["non_uncertain_coverage"]
            < ACTIVATION_THRESHOLDS["non_uncertain_coverage_min"],
            "non_uncertain_coverage_below_threshold",
        ),
        (
            metrics["exact_verdict_agreement"]
            < ACTIVATION_THRESHOLDS["exact_verdict_agreement_min"],
            "exact_verdict_agreement_below_threshold",
        ),
        (
            metrics["critical_flips_to_supported"]
            > ACTIVATION_THRESHOLDS["critical_flips_to_supported_max"],
            "critical_flip_to_supported_present",
        ),
        (
            failures > ACTIVATION_THRESHOLDS["evaluation_failures_max"],
            "evaluation_failures_present",
        ),
    )
    return [reason for failed, reason in checks if failed]


def _operation_summary(observations: list[_Observation]) -> dict[str, object]:
    latency = [item["latency_ms"] for item in observations]
    tokens: Counter[str] = Counter()
    for observation in observations:
        tokens.update(observation["tokens"])
    return {
        "calls": len(observations),
        "retries": sum(max(item["attempts"] - 1, 0) for item in observations),
        "failures": sum(item["provider_outcome"] != "succeeded" for item in observations),
        "latency_ms": {
            "total": sum(latency),
            "maximum": max(latency, default=0),
        },
        "tokens": dict(sorted(tokens.items())),
    }


def _breakdowns(
    observations: list[_Observation],
) -> dict[str, list[dict[str, object]]]:
    values: dict[str, dict[str, list[_Observation]]] = {
        dimension: defaultdict(list) for dimension in _BREAKDOWN_DIMENSIONS
    }
    for observation in observations:
        dimensions = {
            "domain": [observation["domain"]],
            "task_type": [observation["task_type"]],
            "action": [observation["action"]],
            "provenance_origin": observation["provenance_origins"],
            "verdict": [observation["predicted_verdict"]],
            "reason_code": observation["reason_codes"] or ["none"],
            "provider_outcome": [observation["provider_outcome"]],
            "model_independence": [observation["model_independence"]],
        }
        for dimension, dimension_values in dimensions.items():
            for value in dimension_values:
                values[dimension][value].append(observation)
    return {
        dimension: [
            {
                "value": value,
                "observations": len(items),
                "metrics": _metric_summary(items),
            }
            for value, items in sorted(values[dimension].items())
        ]
        for dimension in _BREAKDOWN_DIMENSIONS
    }


def _held_out_assignments(corpus: Mapping[str, object]) -> dict[str, str]:
    reviewed_cases = corpus["cases"]
    assert isinstance(reviewed_cases, list)
    return {
        str(reviewed["case"]["case_id"]): "held_out"
        for reviewed in reviewed_cases
        if isinstance(reviewed, Mapping)
        and isinstance(reviewed.get("case"), Mapping)
        and reviewed["case"].get("split") == "held_out"
    }
