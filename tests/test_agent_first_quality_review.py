from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from agent_synthesis import (
    AdapterRegistry,
    AssessmentCheck,
    CompiledTask,
    EpisodeAssessment,
    FrozenInitialState,
    JsonModelResponse,
    ModelCallError,
    PublicTask,
    ReviewStratification,
    ReviewLabelImportError,
    ReviewQueueConfiguration,
    RunConfiguration,
    ShadowQualityConfiguration,
    SynthesisEngine,
    TaskProposal,
    TaskSlot,
    ToolDefinition,
)


@dataclass(frozen=True)
class _QualityCase:
    public_task: PublicTask


class _QualityDomain:
    domain_id = "quality_review_test_domain"
    domain_version = "quality_review_test_domain_v1"

    def __init__(
        self,
        *,
        unsafe_public_tool_schema: bool = False,
        slot_count: int = 1,
        slot_start: int = 1,
    ) -> None:
        self._unsafe_public_tool_schema = unsafe_public_tool_schema
        self._slot_count = slot_count
        self._slot_start = slot_start

    def open_run(self, configuration: RunConfiguration) -> "_QualityDomainRun":
        del configuration
        return _QualityDomainRun(
            unsafe_public_tool_schema=self._unsafe_public_tool_schema,
            slot_count=self._slot_count,
            slot_start=self._slot_start,
        )


class _QualityDomainRun:
    def __init__(
        self,
        *,
        unsafe_public_tool_schema: bool,
        slot_count: int,
        slot_start: int,
    ) -> None:
        self._unsafe_public_tool_schema = unsafe_public_tool_schema
        self._slot_count = slot_count
        self._slot_start = slot_start

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        slots = tuple(
            TaskSlot(
                slot_id=f"quality-review-{index:03d}",
                proposal_prompt="Return the fixed public task.",
            )
            for index in range(self._slot_start, self._slot_start + self._slot_count)
        )
        return slots[:limit]

    @property
    def known_task_capacity(self) -> int:
        return self._slot_count

    def freeze_initial_state(self) -> FrozenInitialState:
        contents = b'{"fixture":"quality-review"}'
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(contents).hexdigest(),
            contents=contents,
        )

    def compile(self, slot: TaskSlot, proposal: TaskProposal) -> CompiledTask:
        self._validate_proposal(slot, proposal)
        output_properties: dict[str, object] = {}
        if self._unsafe_public_tool_schema:
            output_properties["private_oracle"] = {"type": "string"}
        task = PublicTask(
            instruction="Confirm that the fixture task is complete.",
            tools=(
                ToolDefinition(
                    name="read_fixture",
                    description="Read the fixture value.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": output_properties},
                ),
            ),
        )
        return CompiledTask(
            public_task=task,
            semantic_key=f"quality-review:fixture:{slot.slot_id}",
            private_case_bytes=slot.slot_id.encode("utf-8"),
            domain_case=_QualityCase(task),
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        self._validate_restored_case(semantic_key, private_case_bytes)
        return CompiledTask(
            public_task=public_task,
            semantic_key=semantic_key,
            private_case_bytes=private_case_bytes,
            domain_case=_QualityCase(public_task),
        )

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_QualityEpisode":
        del task, frozen_initial_state
        return _QualityEpisode()

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_QualityEpisode":
        return self.open_episode(task, frozen_initial_state)

    @staticmethod
    def _validate_proposal(slot: TaskSlot, proposal: TaskProposal) -> None:
        assert slot.slot_id.startswith("quality-review-")
        assert proposal.content == "fixed quality review task"

    @staticmethod
    def _validate_restored_case(semantic_key: str, private_case_bytes: bytes) -> None:
        slot_id = private_case_bytes.decode("utf-8")
        assert semantic_key == f"quality-review:fixture:{slot_id}"


class _QualityEpisode:
    def execute_tool_call(self, tool_name: str, arguments: dict[str, object]) -> object:
        raise AssertionError(f"unexpected tool call: {tool_name} {arguments}")

    def assess(self, trace: object) -> EpisodeAssessment:
        del trace
        return EpisodeAssessment(
            passed=True,
            checks=(
                AssessmentCheck(name="final_response_grounded", passed=True),
                AssessmentCheck(name="fixture_complete", passed=True),
            ),
            reason_codes=(),
            coverage_tags=("fixture", "direct"),
            structural_key="quality.fixture.direct",
            review_stratification=ReviewStratification(
                task_type="fixture_task",
                difficulty="standard",
            ),
        )


class _GeneratorAndAgentModel:
    model_id = "quality_generator_agent"
    model_version = "quality_generator_agent_v1"
    provider_id = "deterministic_fake"

    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": "fixed quality review task",
                        }
                        for slot in request.slots
                    ]
                }
            )
        if request.role == "agent":
            return JsonModelResponse(
                content={"type": "final_response", "content": "The fixture task is complete."}
            )
        raise AssertionError(f"unexpected model role: {request.role}")


class _IndependentShadowJudge:
    model_id = "quality_independent_judge"
    model_version = "quality_independent_judge_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        return JsonModelResponse(
            content={
                "dimensions": [
                    {
                        "dimension": dimension,
                        "verdict": "pass",
                        "reason_codes": [],
                        "event_references": [{"event_index": 0}],
                    }
                    for dimension in (
                        "instruction_fidelity",
                        "action_efficiency",
                        "observation_grounding",
                        "final_response_quality",
                        "safety",
                    )
                ]
            }
        )


class _ScriptedShadowJudge(_IndependentShadowJudge):
    def __init__(self, verdicts: tuple[str, ...]) -> None:
        super().__init__()
        self._verdicts = iter(verdicts)

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        verdict = next(self._verdicts)
        dimensions: list[dict[str, object]] = []
        for dimension in (
            "instruction_fidelity",
            "action_efficiency",
            "observation_grounding",
            "final_response_quality",
            "safety",
        ):
            dimension_verdict = "pass"
            reason_codes: list[str] = []
            if dimension == "safety" and verdict == "fail":
                dimension_verdict = "fail"
                reason_codes = ["unsafe_action"]
            elif dimension == "final_response_quality" and verdict == "uncertain":
                dimension_verdict = "uncertain"
                reason_codes = ["ambiguous_observable_evidence"]
            dimensions.append(
                {
                    "dimension": dimension,
                    "verdict": dimension_verdict,
                    "reason_codes": reason_codes,
                    "event_references": [{"event_index": 0}],
                }
            )
        return JsonModelResponse(content={"dimensions": dimensions})


class _InvalidShadowJudge(_IndependentShadowJudge):
    model_id = "quality_invalid_judge"
    model_version = "quality_invalid_judge_v1"

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        return JsonModelResponse(content={"dimensions": []})


class _FailedShadowJudge(_IndependentShadowJudge):
    model_id = "quality_failed_judge"
    model_version = "quality_failed_judge_v1"

    def complete(self, request: object) -> JsonModelResponse:
        self.requests.append(request)
        raise ModelCallError("provider_timeout", retryable=False)


class AgentFirstShadowQualityReviewTest(unittest.TestCase):
    def test_shadow_judgment_is_independent_and_never_changes_deterministic_admission(self) -> None:
        baseline_result, baseline_episode = self._run_without_shadow_judge()
        shadow_judge = _IndependentShadowJudge()
        shadow_result, shadow_episode = self._run_with_shadow_judge(shadow_judge)

        self.assertEqual(
            _episode_without_identity(baseline_episode),
            _episode_without_identity(shadow_episode),
        )
        self.assertEqual(shadow_result.demonstration_count, 1)
        self.assertEqual(shadow_result.negative_count, 0)
        self.assertTrue(shadow_result.shadow_judgments_path.is_file())
        self.assertTrue(shadow_result.quality_report_path.is_file())

        judgment = _read_json_lines(shadow_result.shadow_judgments_path)[0]
        self.assertEqual(judgment["availability"], "available")
        self.assertEqual(judgment["verdict"], "pass")
        self.assertNotIn("admission", judgment)
        self.assertNotIn("lineage", judgment)

        self.assertEqual(len(shadow_judge.requests), 1)
        judge_context = shadow_judge.requests[0].model_context()
        self.assertEqual(
            set(judge_context),
            {"task", "observable_events", "deterministic_results", "rubric"},
        )
        self.assertNotIn("admission", judge_context)
        self.assertNotIn("lineage", judge_context)
        self.assertNotIn("private_case", json.dumps(judge_context, sort_keys=True))

        report = json.loads(shadow_result.quality_report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["yield"]["deterministically_admitted_demonstration_count"], 1)
        self.assertEqual(report["shadow_judgments"]["verdict_counts"], {"pass": 1})
        self.assertEqual(
            report["structural_family_distribution"]["demonstrations"],
            {"quality.fixture.direct": 1},
        )
        self.assertNotIn("quality_score", json.dumps(report, sort_keys=True))
        self.assertNotEqual(
            baseline_result.provider_usage_path.read_bytes(),
            shadow_result.provider_usage_path.read_bytes(),
        )

    def test_unsafe_public_material_fails_a_deterministic_admission_gate(self) -> None:
        domain = _QualityDomain(unsafe_public_tool_schema=True)
        engine = SynthesisEngine(
            AdapterRegistry(domains=(domain,), models=(_GeneratorAndAgentModel(),))
        )
        configuration = RunConfiguration(
            run_id="quality-unsafe-public-material",
            domain_id=domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negatives = _read_json_lines(result.negatives_path)
            public_text = "".join(
                path.read_text(encoding="utf-8")
                for path in (
                    result.negatives_path,
                    result.shadow_judgments_path,
                    result.quality_report_path,
                )
            )

        self.assertEqual(result.demonstration_count, 0)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(negatives[0]["outcome"]["reason_code"], "unsafe_public_material")
        self.assertFalse(negatives[0]["admission"]["gates"]["unsafe_material"])
        self.assertNotIn("private_oracle", public_text)
        self.assertNotIn("/Users/agent/private-fixture.json", public_text)

    def test_blind_held_out_queue_accepts_only_complete_queue_bound_human_labels(self) -> None:
        shadow_judge = _IndependentShadowJudge()
        result, episode = self._run_with_shadow_judge(shadow_judge)
        engine = self._engine_for_review_import(shadow_judge)
        queue = engine.create_review_queue(
            result.run_directory,
            ReviewQueueConfiguration(
                cohort_id="quality-held-out",
                purpose="held-out-evaluation",
            ),
        )
        queue_item = _read_json_lines(queue.queue_path)[0]

        self.assertEqual(
            queue.cohort.selection_method,
            "held_out_all_deterministically_eligible",
        )

        self.assertEqual(
            set(queue_item),
            {
                "schema_version",
                "cohort_id",
                "purpose",
                "episode_id",
                "sequence",
                "domain_id",
                "task",
                "observable_trajectory",
            },
        )
        self.assertEqual(queue_item["episode_id"], episode["episode_id"])
        self.assertNotIn("lineage", queue_item)
        self.assertNotIn("admission", queue_item)
        self.assertNotIn("judgment", queue_item)
        self.assertNotIn("verification", queue_item)

        incomplete = engine.import_review_labels(result.run_directory, [])
        self.assertEqual(incomplete.status, "incomplete")
        self.assertFalse(incomplete.complete)

        foreign_label = _human_pass_label(
            episode_id="episode_not_in_the_queue",
            cohort_id="quality-held-out",
            purpose="held-out-evaluation",
        )
        with self.assertRaises(ReviewLabelImportError):
            engine.import_review_labels(result.run_directory, [foreign_label])

        unsafe_label = _human_pass_label(
            episode_id=episode["episode_id"],
            cohort_id="quality-held-out",
            purpose="held-out-evaluation",
        )
        unsafe_provenance = unsafe_label["reviewer_provenance"]
        assert isinstance(unsafe_provenance, dict)
        unsafe_provenance["reviewer_id"] = "/private/reviewer"
        with self.assertRaises(ReviewLabelImportError):
            engine.import_review_labels(result.run_directory, [unsafe_label])

        completed = engine.import_review_labels(
            result.run_directory,
            [
                _human_pass_label(
                    episode_id=episode["episode_id"],
                    cohort_id="quality-held-out",
                    purpose="held-out-evaluation",
                )
            ],
        )
        self.assertEqual(completed.status, "complete")
        self.assertTrue(completed.complete)
        self.assertEqual(completed.human_approved_episode_ids, (episode["episode_id"],))
        with self.assertRaises(ReviewLabelImportError):
            engine.import_review_labels(
                result.run_directory,
                [
                    _human_pass_label(
                        episode_id=episode["episode_id"],
                        cohort_id="quality-held-out",
                        purpose="held-out-evaluation",
                    )
                ],
            )

        report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["review"]["demonstration_acceptance"]["denominator"], 1)
        self.assertEqual(report["review"]["demonstration_acceptance"]["human_pass_count"], 1)

    def test_diagnostic_queue_includes_all_nonpasses_and_a_stratified_pass_fill(self) -> None:
        domain = _QualityDomain(slot_count=4)
        shadow_judge = _ScriptedShadowJudge(("fail", "uncertain", "pass", "pass"))
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_GeneratorAndAgentModel(), shadow_judge),
            )
        )
        configuration = RunConfiguration(
            run_id="quality-development",
            domain_id=domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=4,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=shadow_judge.model_id,
                judge_request_limit=4,
            ),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            queue = engine.create_review_queue(
                result.run_directory,
                ReviewQueueConfiguration(
                    cohort_id="quality-development",
                    purpose="diagnostic-development",
                    pass_sample_limit=1,
                ),
            )
            queue_items = _read_json_lines(queue.queue_path)
            with self.assertRaises(ValueError):
                engine.create_review_queue(
                    result.run_directory,
                    ReviewQueueConfiguration(
                        cohort_id="overlapping-held-out",
                        purpose="held-out-evaluation",
                        candidate_episode_ids=(queue_items[0]["episode_id"],),
                    ),
                )
            labels = [
                _human_label(
                    episode_id=item["episode_id"],
                    cohort_id="quality-development",
                    purpose="diagnostic-development",
                    verdict=("fail" if index == 0 else "uncertain" if index == 1 else "pass"),
                )
                for index, item in enumerate(queue_items)
            ]
            partial = engine.import_review_labels(result.run_directory, labels[:2])
            complete = engine.import_review_labels(result.run_directory, labels[2:])
            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.demonstration_count, 4)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(queue.cohort.nonpass_or_unavailable_count, 2)
        self.assertEqual(queue.cohort.stratified_pass_count, 1)
        self.assertEqual(
            queue.cohort.selection_method,
            "diagnostic_all_nonpass_stratified_pass",
        )
        self.assertEqual(queue.cohort.stratified_pass_stratum_count, 1)
        self.assertEqual(len(queue_items), 3)
        self.assertEqual(partial.status, "incomplete")
        self.assertEqual(complete.status, "complete")
        self.assertEqual(len(complete.human_approved_episode_ids), 1)
        self.assertEqual(
            report["shadow_judgments"]["verdict_counts"],
            {"fail": 1, "pass": 2, "uncertain": 1},
        )

    def test_matching_judge_identity_and_invalid_judgment_stay_explicitly_unavailable(self) -> None:
        matching_domain = _QualityDomain()
        matching_model = _GeneratorAndAgentModel()
        matching_engine = SynthesisEngine(
            AdapterRegistry(domains=(matching_domain,), models=(matching_model,))
        )
        matching_configuration = RunConfiguration(
            run_id="quality-matching-identity",
            domain_id=matching_domain.domain_id,
            model_id=matching_model.model_id,
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=matching_model.model_id,
                judge_request_limit=1,
            ),
        )
        invalid_domain = _QualityDomain()
        invalid_judge = _InvalidShadowJudge()
        invalid_engine = SynthesisEngine(
            AdapterRegistry(
                domains=(invalid_domain,),
                models=(_GeneratorAndAgentModel(), invalid_judge),
            )
        )
        invalid_configuration = RunConfiguration(
            run_id="quality-invalid-judgment",
            domain_id=invalid_domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=invalid_judge.model_id,
                judge_request_limit=1,
            ),
        )
        missing_domain = _QualityDomain()
        missing_engine = SynthesisEngine(
            AdapterRegistry(
                domains=(missing_domain,),
                models=(_GeneratorAndAgentModel(),),
            )
        )
        missing_configuration = RunConfiguration(
            run_id="quality-missing-judge-identity",
            domain_id=missing_domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(mode="shadow"),
        )

        with tempfile.TemporaryDirectory() as matching_directory, tempfile.TemporaryDirectory() as invalid_directory, tempfile.TemporaryDirectory() as missing_directory:
            matching_result = matching_engine.run(
                matching_configuration,
                Path(matching_directory),
            )
            invalid_result = invalid_engine.run(
                invalid_configuration,
                Path(invalid_directory),
            )
            missing_result = missing_engine.run(
                missing_configuration,
                Path(missing_directory),
            )
            matching_judgment = _read_json_lines(matching_result.shadow_judgments_path)[0]
            invalid_judgment = _read_json_lines(invalid_result.shadow_judgments_path)[0]
            missing_judgment = _read_json_lines(missing_result.shadow_judgments_path)[0]

        self.assertEqual(matching_judgment["verdict"], "unavailable")
        self.assertEqual(
            matching_judgment["unavailable_reason"],
            "judge_identity_matches_generator",
        )
        self.assertEqual(invalid_judgment["verdict"], "unavailable")
        self.assertEqual(invalid_judgment["unavailable_reason"], "invalid_judgment")
        self.assertEqual(missing_judgment["verdict"], "unavailable")
        self.assertEqual(missing_judgment["unavailable_reason"], "judge_identity_missing")
        self.assertEqual(invalid_result.demonstration_count, 1)

    def test_provider_failed_judgment_is_unavailable_without_changing_admission(self) -> None:
        domain = _QualityDomain()
        failed_judge = _FailedShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_GeneratorAndAgentModel(), failed_judge),
            )
        )
        configuration = RunConfiguration(
            run_id="quality-provider-failed",
            domain_id=domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=failed_judge.model_id,
                judge_request_limit=1,
            ),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            judgment = _read_json_lines(result.shadow_judgments_path)[0]

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(judgment["verdict"], "unavailable")
        self.assertEqual(judgment["unavailable_reason"], "provider_failed")

    @staticmethod
    def _engine_for_review_import(shadow_judge: _IndependentShadowJudge) -> SynthesisEngine:
        return SynthesisEngine(
            AdapterRegistry(
                domains=(_QualityDomain(),),
                models=(_GeneratorAndAgentModel(), shadow_judge),
            )
        )

    def _run_without_shadow_judge(self) -> tuple[object, dict[str, object]]:
        domain = _QualityDomain()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(domain,), models=(_GeneratorAndAgentModel(),))
        )
        configuration = RunConfiguration(
            run_id="quality-baseline",
            domain_id=domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
        )
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output_directory = Path(temporary_directory.name)
        result = engine.run(configuration, output_directory)
        return result, _read_json_lines(result.demonstrations_path)[0]

    def _run_with_shadow_judge(
        self,
        shadow_judge: _IndependentShadowJudge,
    ) -> tuple[object, dict[str, object]]:
        domain = _QualityDomain()
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(domain,),
                models=(_GeneratorAndAgentModel(), shadow_judge),
            )
        )
        configuration = RunConfiguration(
            run_id="quality-shadow",
            domain_id=domain.domain_id,
            model_id="quality_generator_agent",
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=shadow_judge.model_id,
                judge_request_limit=2,
            ),
        )
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output_directory = Path(temporary_directory.name)
        result = engine.run(configuration, output_directory)
        return result, _read_json_lines(result.demonstrations_path)[0]


def _episode_without_identity(episode: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in episode.items()
        if key not in {"episode_id", "candidate_id", "lineage"}
    }


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _human_pass_label(
    *,
    episode_id: object,
    cohort_id: str,
    purpose: str,
) -> dict[str, object]:
    assert isinstance(episode_id, str)
    return {
        "schema_version": "agent_human_review_label_v1",
        "episode_id": episode_id,
        "cohort_id": cohort_id,
        "purpose": purpose,
        "dimensions": [
            {
                "dimension": dimension,
                "verdict": "pass",
                "reason_codes": [],
                "event_references": [{"event_index": 0}],
            }
            for dimension in (
                "instruction_fidelity",
                "action_efficiency",
                "observation_grounding",
                "final_response_quality",
                "safety",
            )
        ],
        "reviewer_provenance": {
            "reviewer_id": "reviewer.alpha",
            "review_method": "human_direct_review",
            "human_review_attestation": (
                "I directly reviewed this Episode and did not use generated or "
                "judge-produced labels as human ground truth."
            ),
        },
    }


def _human_label(
    *,
    episode_id: object,
    cohort_id: str,
    purpose: str,
    verdict: str,
) -> dict[str, object]:
    label = _human_pass_label(
        episode_id=episode_id,
        cohort_id=cohort_id,
        purpose=purpose,
    )
    if verdict == "pass":
        return label
    dimensions = label["dimensions"]
    assert isinstance(dimensions, list)
    target = dimensions[-1]
    assert isinstance(target, dict)
    target["verdict"] = verdict
    target["reason_codes"] = [
        "unsafe_action" if verdict == "fail" else "ambiguous_observable_evidence"
    ]
    return label


if __name__ == "__main__":
    unittest.main()
