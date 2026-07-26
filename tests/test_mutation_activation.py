from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path

from synthesis.mutation_admission import (
    SEMANTIC_VERDICT_VERSION,
    SemanticJudgeRequest,
    SemanticJudgeResult,
    canonical_hash,
)
from synthesis.mutation_admission_config import (
    MUTATION_ADMISSION_JUDGE_PROVIDER,
    MUTATION_ADMISSION_JUDGE_ROLE,
    MutationAdmissionJudgeConfiguration,
)
from synthesis.mutation_calibration import (
    HUMAN_REVIEW_ATTESTATION,
    build_mutation_calibration_review_packet,
    build_mutation_calibration_split_freeze,
    import_human_reviewed_mutation_calibration_corpus,
)


class MutationActivationEvaluationTest(unittest.TestCase):
    def test_three_independent_repeats_produce_deterministic_activation_report(
        self,
    ) -> None:
        from synthesis.mutation_activation import (
            evaluate_mutation_activation,
            write_mutation_activation_report,
        )

        corpus = _reviewed_corpus()
        expected_verdicts = _expected_verdicts(corpus)
        calls: list[str] = []

        def judge(request: SemanticJudgeRequest) -> SemanticJudgeResult:
            calls.append(request.input_hash())
            verdict = expected_verdicts[(len(calls) - 1) % len(expected_verdicts)]
            return SemanticJudgeResult(
                verdict=_valid_verdict(request, verdict),
                provider_outcome="succeeded",
                attempts=1,
                timeout_seconds=30.0,
                judge_lineage=_judge_lineage(),
                token_usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            )

        first = evaluate_mutation_activation(
            corpus=corpus,
            generator_model="generator-model",
            judge_configuration=_judge_configuration(),
            judge=judge,
            monotonic=_deterministic_clock(),
        )
        first_calls = list(calls)
        calls.clear()
        second = evaluate_mutation_activation(
            corpus=corpus,
            generator_model="generator-model",
            judge_configuration=_judge_configuration(),
            judge=judge,
            monotonic=_deterministic_clock(),
        )

        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_path = root / "first.json"
            second_path = root / "second.json"
            write_mutation_activation_report(first_path, first)
            write_mutation_activation_report(second_path, second)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
        self.assertEqual(len(first_calls), 600)
        self.assertEqual(first_calls[:200], first_calls[200:400])
        self.assertEqual(first_calls[:200], first_calls[400:])
        self.assertEqual(first["schema_version"], "mutation_activation_report_v1")
        self.assertEqual(first["decision"], "activate")
        self.assertEqual(first["decision_reasons"], [])
        self.assertEqual(first["metrics"]["critical_false_supports"], 0)
        self.assertEqual(first["metrics"]["supported_precision"], 1.0)
        self.assertEqual(first["metrics"]["unsafe_case_capture"], 1.0)
        self.assertEqual(first["metrics"]["non_uncertain_coverage"], 0.9)
        self.assertEqual(first["metrics"]["exact_verdict_agreement"], 1.0)
        self.assertEqual(first["metrics"]["critical_flips_to_supported"], 0)
        self.assertEqual(first["operations"]["calls"], 600)
        self.assertEqual(first["operations"]["retries"], 0)
        self.assertEqual(first["operations"]["failures"], 0)
        self.assertEqual(first["operations"]["latency_ms"]["total"], 600)
        self.assertEqual(first["operations"]["tokens"]["total_tokens"], 7200)
        self.assertEqual(
            first["evidence"]["judge_configuration"]["model"],
            "independent-judge-model",
        )
        self.assertEqual(first["evidence"]["corpus_hash"], corpus["corpus_hash"])
        self.assertEqual(
            first["evidence"]["corpus_summary"],
            {
                "cases": 200,
                "unsupported_or_adversarial": 120,
                "held_out": 60,
                "domains": [
                    "contacts_fixture",
                    "mobile_messages_fixture",
                    "workspace_tasks_fixture",
                ],
                "task_types": [
                    "contact_followup",
                    "mobile_draft_reply",
                    "mobile_message_to_reminder",
                    "mobile_reminder_creation",
                    "workspace_comment_update",
                    "workspace_task_creation",
                ],
                "actions": [
                    "contact_followup_record",
                    "mobile_draft_reply_create",
                    "mobile_reminder_create",
                    "workspace_comment_add",
                    "workspace_task_create",
                ],
            },
        )
        self.assertTrue(first["evidence"]["held_out_split_hash"].startswith("sha256:"))
        self.assertTrue(first["report_hash"].startswith("sha256:"))
        serialized = json.dumps(first, sort_keys=True)
        for prohibited in (
            "raw_prompt",
            "raw_response",
            "credentials",
            "secret-test-key",
        ):
            self.assertNotIn(prohibited, serialized)
        self.assertEqual(
            set(first["breakdowns"]),
            {
                "domain",
                "task_type",
                "action",
                "provenance_origin",
                "verdict",
                "reason_code",
                "provider_outcome",
                "model_independence",
            },
        )
        self.assertEqual(
            {
                item["value"]
                for item in first["breakdowns"]["provenance_origin"]
            },
            {
                "declared_default",
                "deterministic_derivation",
                "instruction",
                "tool_observation",
            },
        )
        self.assertEqual(
            {
                item["value"]
                for item in first["breakdowns"]["model_independence"]
            },
            {"independent"},
        )
        self.assertTrue(
            all(
                evaluation["input_hash"].startswith("sha256:")
                and evaluation["normalized_input_hash"].startswith("sha256:")
                and evaluation["input_hash"] != evaluation["normalized_input_hash"]
                for evaluation in first["evaluations"]
            )
        )

    def test_metric_threshold_boundaries_are_inclusive_and_fail_below(self) -> None:
        corpus = _reviewed_corpus()
        baseline = _prediction_matrix(corpus)
        supported = _case_indexes(corpus, ground_truth="supported")
        unsafe = _case_indexes(corpus, ground_truth="unsupported")

        unsafe_boundary = _copy_predictions(baseline)
        for run, case_index in _first_positions(unsafe, 6):
            unsafe_boundary[run][case_index] = "failure"
        unsafe_fail = _copy_predictions(unsafe_boundary)
        run, case_index = _first_positions(unsafe, 7)[-1]
        unsafe_fail[run][case_index] = "failure"
        self.assertEqual(
            _evaluate_predictions(corpus, unsafe_boundary)["metrics"][
                "unsafe_case_capture"
            ],
            0.98,
        )
        self.assertNotIn(
            "unsafe_case_capture_below_threshold",
            _evaluate_predictions(corpus, unsafe_boundary)["decision_reasons"],
        )
        self.assertIn(
            "unsafe_case_capture_below_threshold",
            _evaluate_predictions(corpus, unsafe_fail)["decision_reasons"],
        )

        coverage_boundary = _copy_predictions(baseline)
        for case_index in supported[:40]:
            for run_index in range(3):
                coverage_boundary[run_index][case_index] = "uncertain"
        coverage_fail = _copy_predictions(coverage_boundary)
        coverage_fail[0][supported[40]] = "uncertain"
        self.assertEqual(
            _evaluate_predictions(corpus, coverage_boundary)["metrics"][
                "non_uncertain_coverage"
            ],
            0.70,
        )
        self.assertNotIn(
            "non_uncertain_coverage_below_threshold",
            _evaluate_predictions(corpus, coverage_boundary)["decision_reasons"],
        )
        self.assertIn(
            "non_uncertain_coverage_below_threshold",
            _evaluate_predictions(corpus, coverage_fail)["decision_reasons"],
        )

        agreement_boundary = _copy_predictions(baseline)
        for case_index in supported[:10]:
            agreement_boundary[0][case_index] = "uncertain"
        agreement_fail = _copy_predictions(agreement_boundary)
        agreement_fail[0][supported[10]] = "uncertain"
        self.assertEqual(
            _evaluate_predictions(corpus, agreement_boundary)["metrics"][
                "exact_verdict_agreement"
            ],
            0.95,
        )
        self.assertNotIn(
            "exact_verdict_agreement_below_threshold",
            _evaluate_predictions(corpus, agreement_boundary)["decision_reasons"],
        )
        self.assertIn(
            "exact_verdict_agreement_below_threshold",
            _evaluate_predictions(corpus, agreement_fail)["decision_reasons"],
        )

    def test_supported_precision_boundary_and_safety_asymmetry(self) -> None:
        corpus = _reviewed_corpus()
        baseline = _prediction_matrix(corpus)
        standard_unsafe = _case_indexes(
            corpus,
            ground_truth="unsupported",
            critical=False,
        )
        critical_unsafe = _case_indexes(
            corpus,
            ground_truth="unsupported",
            critical=True,
        )
        precision_boundary = _copy_predictions(baseline)
        supported = _case_indexes(corpus, ground_truth="supported")
        for case_index in supported:
            for run_index in range(3):
                precision_boundary[run_index][case_index] = "unsupported"
        for case_index in supported[:16]:
            for run_index in range(3):
                precision_boundary[run_index][case_index] = "supported"
        precision_boundary[0][supported[16]] = "supported"
        precision_boundary[0][standard_unsafe[0]] = "supported"
        precision_fail = _copy_predictions(precision_boundary)
        precision_fail[0][supported[0]] = "unsupported"

        passing = _evaluate_predictions(corpus, precision_boundary)
        failing = _evaluate_predictions(corpus, precision_fail)
        self.assertEqual(passing["metrics"]["supported_precision"], 0.98)
        self.assertNotIn(
            "supported_precision_below_threshold",
            passing["decision_reasons"],
        )
        self.assertLess(failing["metrics"]["supported_precision"], 0.98)
        self.assertIn(
            "supported_precision_below_threshold",
            failing["decision_reasons"],
        )
        self.assertEqual(passing["metrics"]["critical_false_supports"], 0)

        critical_flip = _copy_predictions(baseline)
        critical_flip[1][critical_unsafe[0]] = "supported"
        safety_report = _evaluate_predictions(corpus, critical_flip)
        self.assertEqual(safety_report["decision"], "no_go")
        self.assertEqual(safety_report["metrics"]["critical_false_supports"], 1)
        self.assertEqual(
            safety_report["metrics"]["critical_flips_to_supported"],
            1,
        )
        self.assertIn(
            "critical_false_supports_present",
            safety_report["decision_reasons"],
        )
        self.assertIn(
            "critical_flip_to_supported_present",
            safety_report["decision_reasons"],
        )

    def test_repeat_permutations_and_malformed_results_are_fail_closed(self) -> None:
        corpus = _reviewed_corpus()
        critical_unsafe = _case_indexes(
            corpus,
            ground_truth="unsupported",
            critical=True,
        )
        baseline = _prediction_matrix(corpus)
        case_index = critical_unsafe[0]
        expected = {
            ("supported", "unsupported", "unsupported"): (1, 1),
            ("unsupported", "supported", "unsupported"): (1, 1),
            ("unsupported", "unsupported", "supported"): (1, 1),
            ("supported", "supported", "supported"): (3, 0),
        }
        for permutation, counts in expected.items():
            with self.subTest(permutation=permutation):
                predictions = _copy_predictions(baseline)
                for run_index, verdict in enumerate(permutation):
                    predictions[run_index][case_index] = verdict
                report = _evaluate_predictions(corpus, predictions)
                self.assertEqual(
                    report["metrics"]["critical_false_supports"],
                    counts[0],
                )
                self.assertEqual(
                    report["metrics"]["critical_flips_to_supported"],
                    counts[1],
                )

        malformed = _copy_predictions(baseline)
        malformed[0][0] = "malformed"
        report = _evaluate_predictions(corpus, malformed)
        self.assertEqual(report["operations"]["failures"], 1)
        first = report["evaluations"][0]
        self.assertEqual(first["provider_outcome"], "output_invalid")
        self.assertEqual(first["verdict"], "failure")
        self.assertIsNone(first["output_hash"])
        self.assertEqual(report["decision"], "no_go")

        three_failures = _copy_predictions(baseline)
        for run_index in range(3):
            three_failures[run_index][0] = "failure"
        failure_report = _evaluate_predictions(corpus, three_failures)
        self.assertEqual(
            failure_report["metrics"]["exact_verdict_agreement"],
            0.995,
        )

    def test_same_model_and_non_reviewed_inputs_are_rejected_as_evidence(self) -> None:
        from synthesis.mutation_activation import evaluate_mutation_activation

        corpus = _reviewed_corpus()
        judge_configuration = _judge_configuration()
        same_model_configuration = MutationAdmissionJudgeConfiguration(
            role=judge_configuration.role,
            provider=judge_configuration.provider,
            model="generator-model",
            timeout_seconds=judge_configuration.timeout_seconds,
            max_retries=judge_configuration.max_retries,
        )
        with self.assertRaisesRegex(
            ValueError,
            "same-model judge cannot be activation evidence",
        ):
            evaluate_mutation_activation(
                corpus=corpus,
                generator_model="generator-model",
                judge_configuration=same_model_configuration,
                judge=lambda request: SemanticJudgeResult(
                    verdict=None,
                    provider_outcome="unavailable",
                    attempts=0,
                    timeout_seconds=30.0,
                ),
            )

        with self.assertRaisesRegex(ValueError, "generator model is invalid"):
            evaluate_mutation_activation(
                corpus=corpus,
                generator_model=" independent-judge-model ",
                judge_configuration=judge_configuration,
                judge=lambda request: SemanticJudgeResult(
                    verdict=None,
                    provider_outcome="unavailable",
                    attempts=0,
                    timeout_seconds=30.0,
                ),
            )

        non_reviewed = json.loads(json.dumps(corpus))
        non_reviewed["review_status"] = "generated"
        with self.assertRaisesRegex(ValueError, "not human reviewed"):
            evaluate_mutation_activation(
                corpus=non_reviewed,
                generator_model="generator-model",
                judge_configuration=judge_configuration,
                judge=lambda request: SemanticJudgeResult(
                    verdict=None,
                    provider_outcome="unavailable",
                    attempts=0,
                    timeout_seconds=30.0,
                ),
            )

    def test_offline_activation_report_validation_rejects_tampering(self) -> None:
        from synthesis.mutation_activation import (
            validate_mutation_activation_report,
        )

        corpus = _reviewed_corpus()
        report = _evaluate_predictions(corpus, _prediction_matrix(corpus))
        validate_mutation_activation_report(report)

        for path, replacement in (
            (("thresholds", "supported_precision_min"), 0.5),
            (("evidence", "corpus_summary", "cases"), 199),
            (("decision",), "no_go"),
        ):
            with self.subTest(path=path):
                tampered = json.loads(json.dumps(report))
                target = tampered
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                with self.assertRaises(ValueError):
                    validate_mutation_activation_report(tampered)

        same_model = json.loads(json.dumps(report))
        same_model["evidence"]["generator_model_hash"] = canonical_hash(
            same_model["evidence"]["judge_configuration"]["model"]
        )
        same_model["report_hash"] = canonical_hash(
            {
                key: value
                for key, value in same_model.items()
                if key != "report_hash"
            }
        )
        with self.assertRaisesRegex(ValueError, "model independence"):
            validate_mutation_activation_report(same_model)

        self_consistent_tamper = json.loads(json.dumps(report))
        self_consistent_tamper["evaluations"][0]["verdict"] = "unsupported"
        self_consistent_tamper["report_hash"] = canonical_hash(
            {
                key: value
                for key, value in self_consistent_tamper.items()
                if key != "report_hash"
            }
        )
        with self.assertRaisesRegex(ValueError, "metrics are inconsistent"):
            validate_mutation_activation_report(self_consistent_tamper)

        independence_tamper = json.loads(json.dumps(report))
        independence_tamper["evaluations"][0][
            "model_independence"
        ] = "unknown"
        independence_tamper["report_hash"] = canonical_hash(
            {
                key: value
                for key, value in independence_tamper.items()
                if key != "report_hash"
            }
        )
        with self.assertRaisesRegex(ValueError, "model independence"):
            validate_mutation_activation_report(independence_tamper)

def _reviewed_corpus() -> dict[str, object]:
    packet = build_mutation_calibration_review_packet(
        corpus_version="mutation_calibration_corpus_v1"
    )
    cases = packet["cases"]
    assert isinstance(cases, list)
    labels = [
        {
            "schema_version": "human_mutation_calibration_label_v1",
            "corpus_version": packet["corpus_version"],
            "case_id": case["case_id"],
            "case_hash": case["case_hash"],
            "ground_truth": _ground_truth(case),
            "reviewer_provenance": {
                "reviewer_id": "reviewer.alice",
                "reviewed_at": "2026-07-25T09:30:00Z",
                "review_method": "human_direct_review",
                "human_review_attestation": HUMAN_REVIEW_ATTESTATION,
            },
        }
        for case in cases
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        packet_path = root / "packet.json"
        freeze_path = root / "freeze.json"
        labels_path = root / "labels.jsonl"
        output_path = root / "reviewed.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        freeze = build_mutation_calibration_split_freeze(packet)
        freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
        labels_path.write_text(
            "".join(
                json.dumps(label, sort_keys=True, separators=(",", ":")) + "\n"
                for label in labels
            ),
            encoding="utf-8",
        )
        return import_human_reviewed_mutation_calibration_corpus(
            packet_path=packet_path,
            freeze_path=freeze_path,
            labels_path=labels_path,
            output_path=output_path,
        )


def _ground_truth(case: Mapping[str, object]) -> str:
    if case["sampling_class"] == "supported_candidate":
        return "supported"
    if case["scenario_tags"] == ["conditional_authorization"]:
        return "uncertain"
    return "unsupported"


def _expected_verdicts(corpus: Mapping[str, object]) -> list[str]:
    reviewed_cases = corpus["cases"]
    assert isinstance(reviewed_cases, list)
    return [
        str(reviewed["human_review"]["ground_truth"])
        for reviewed in reviewed_cases
    ]


def _judge_configuration() -> MutationAdmissionJudgeConfiguration:
    return MutationAdmissionJudgeConfiguration(
        role=MUTATION_ADMISSION_JUDGE_ROLE,
        provider=MUTATION_ADMISSION_JUDGE_PROVIDER,
        model="independent-judge-model",
        timeout_seconds=30.0,
        max_retries=1,
    )


def _judge_lineage() -> dict[str, object]:
    return {
        "role": MUTATION_ADMISSION_JUDGE_ROLE,
        "role_version": "role_mutation_admission_judge_v1",
        "provider_host": "judge.example.test",
        "model": "independent-judge-model",
        "config_hash": canonical_hash(
            {
                "role": MUTATION_ADMISSION_JUDGE_ROLE,
                "model": "independent-judge-model",
            }
        ),
    }


def _valid_verdict(
    request: SemanticJudgeRequest,
    verdict: str,
) -> dict[str, object]:
    if verdict == "supported":
        action_outcome = "supported"
        action_reason = "action_authorized"
        argument_outcome = "supported"
        argument_reason = "argument_literal_supported"
    elif verdict == "unsupported":
        action_outcome = "unsupported"
        action_reason = "action_not_authorized"
        argument_outcome = "unsupported"
        argument_reason = "argument_not_supported"
    else:
        action_outcome = "uncertain"
        action_reason = "conditional_authorization_ambiguous"
        argument_outcome = "uncertain"
        argument_reason = "evidence_ambiguous"
    action_reference = request.evidence_references["action"]
    argument_findings = [
        {
            "argument": argument,
            "outcome": argument_outcome,
            "reason_code": argument_reason,
            "evidence_references": [request.evidence_references[argument]],
        }
        for argument in request.argument_values
    ]
    evidence_references = list(
        dict.fromkeys(
            [
                action_reference,
                *(
                    request.evidence_references[argument]
                    for argument in request.argument_values
                ),
            ]
        )
    )
    return {
        "schema_version": SEMANTIC_VERDICT_VERSION,
        "verdict": verdict,
        "action_findings": [
            {
                "action_type": request.action_type,
                "outcome": action_outcome,
                "reason_code": action_reason,
                "evidence_references": [action_reference],
            }
        ],
        "argument_findings": argument_findings,
        "reason_codes": list(dict.fromkeys([action_reason, argument_reason])),
        "evidence_references": evidence_references,
        "input_hash": request.input_hash(),
        "judge_lineage": _judge_lineage(),
    }


def _deterministic_clock():
    value = 0.0

    def clock() -> float:
        nonlocal value
        value += 0.001
        return value

    return clock


def _prediction_matrix(corpus: Mapping[str, object]) -> list[list[str]]:
    expected = _expected_verdicts(corpus)
    return [list(expected), list(expected), list(expected)]


def _copy_predictions(predictions: list[list[str]]) -> list[list[str]]:
    return [list(run) for run in predictions]


def _case_indexes(
    corpus: Mapping[str, object],
    *,
    ground_truth: str,
    critical: bool | None = None,
) -> list[int]:
    reviewed_cases = corpus["cases"]
    assert isinstance(reviewed_cases, list)
    return [
        index
        for index, reviewed in enumerate(reviewed_cases)
        if reviewed["human_review"]["ground_truth"] == ground_truth
        and (
            critical is None
            or (reviewed["case"]["criticality"] == "critical") is critical
        )
    ]


def _first_positions(case_indexes: list[int], count: int) -> list[tuple[int, int]]:
    return [
        (offset // len(case_indexes), case_indexes[offset % len(case_indexes)])
        for offset in range(count)
    ]


def _evaluate_predictions(
    corpus: Mapping[str, object],
    predictions: list[list[str]],
) -> dict[str, object]:
    from synthesis.mutation_activation import evaluate_mutation_activation

    call_index = 0

    def judge(request: SemanticJudgeRequest) -> SemanticJudgeResult:
        nonlocal call_index
        run_index, case_index = divmod(call_index, len(predictions[0]))
        predicted = predictions[run_index][case_index]
        call_index += 1
        if predicted == "failure":
            return SemanticJudgeResult(
                verdict=None,
                provider_outcome="unavailable",
                attempts=2,
                timeout_seconds=30.0,
                judge_lineage=_judge_lineage(),
            )
        if predicted == "malformed":
            return SemanticJudgeResult(
                verdict={"verdict": "supported", "raw_response": "do not retain"},
                provider_outcome="succeeded",
                attempts=1,
                timeout_seconds=30.0,
                judge_lineage=_judge_lineage(),
            )
        return SemanticJudgeResult(
            verdict=_valid_verdict(request, predicted),
            provider_outcome="succeeded",
            attempts=1,
            timeout_seconds=30.0,
            judge_lineage=_judge_lineage(),
        )

    return evaluate_mutation_activation(
        corpus=corpus,
        generator_model="generator-model",
        judge_configuration=_judge_configuration(),
        judge=judge,
        monotonic=_deterministic_clock(),
    )


if __name__ == "__main__":
    unittest.main()
