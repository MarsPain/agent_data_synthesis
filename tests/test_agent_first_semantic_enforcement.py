from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_synthesis import (
    AdmissionRecord,
    AdapterRegistry,
    DeterministicAdmissionGates,
    QualityJudgeIdentity,
    ReviewQueueConfiguration,
    RunConfiguration,
    SemanticEnforcementIneligibleError,
    ShadowQualityConfiguration,
    SynthesisEngine,
)
from agent_synthesis.enforcement import (
    CalibrationCampaignEvidence,
    CalibrationCohortEvidence,
    CalibrationEpisodeEvidence,
    SemanticEnforcementDomainScope,
    SemanticEnforcementPolicy,
    SemanticEnforcementRunConfiguration,
    evaluate_semantic_enforcement,
    write_semantic_enforcement_eligibility_report,
)


class SemanticEnforcementEligibilityTest(unittest.TestCase):
    def test_exact_thresholds_activate_a_policy_for_three_domains(self) -> None:
        policy = _policy()
        development = _campaign(
            campaign_id="development-campaign",
            purpose="diagnostic-development",
            policy=policy,
            verdicts=(("pass", "pass"),) * 100,
            bind_policy=False,
        )
        evaluation = _campaign(
            campaign_id="evaluation-campaign",
            purpose="held-out-evaluation",
            policy=policy,
            verdicts=_threshold_verdicts(),
            bind_policy=True,
        )

        report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation,
        )

        self.assertEqual(report.eligibility, "eligible", report.ineligibility_reasons)
        self.assertEqual(report.evaluation.overall.agreement.numerator, 85)
        self.assertEqual(report.evaluation.overall.agreement.denominator, 100)
        self.assertEqual(report.evaluation.overall.false_pass.numerator, 1)
        self.assertEqual(report.evaluation.overall.false_pass.denominator, 20)
        self.assertEqual(report.evaluation.overall.false_fail.numerator, 0)
        self.assertEqual(report.evaluation.overall.false_fail.denominator, 19)
        self.assertEqual(report.evaluation.overall.critical_safety_false_pass.numerator, 0)
        self.assertEqual(len(report.evaluation.per_domain), 3)
        self.assertTrue(report.development.raw_rates_are_diagnostic)
        self.assertIn("finite-cohort", report.finite_cohort_notice.lower())
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = write_semantic_enforcement_eligibility_report(
                Path(temporary_directory) / "eligibility.json",
                report,
            )
            stored = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(
            stored["schema_version"],
            "agent_semantic_enforcement_eligibility_report_v1",
        )
        self.assertEqual(stored["activation_identity"], report.activation_identity)

    def test_enforcement_configuration_binds_an_eligible_policy_to_a_new_run(self) -> None:
        policy = _policy()
        development = _campaign(
            campaign_id="development-campaign",
            purpose="diagnostic-development",
            policy=policy,
            verdicts=(("pass", "pass"),) * 100,
            bind_policy=False,
        )
        evaluation = _campaign(
            campaign_id="evaluation-campaign",
            purpose="held-out-evaluation",
            policy=policy,
            verdicts=_threshold_verdicts(),
            bind_policy=True,
        )
        activation = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation,
        )

        configuration = RunConfiguration(
            run_id="enforced-fixture-run",
            domain_id="contacts",
            model_id="fixture-generator",
            slot_limit=1,
            admission_mode="enforced",
            semantic_enforcement=SemanticEnforcementRunConfiguration(
                policy=policy,
                activation=activation,
            ),
        )

        self.assertEqual(configuration.admission_mode, "enforced")
        assert configuration.semantic_enforcement is not None
        self.assertEqual(
            configuration.semantic_enforcement.activation.activation_identity,
            activation.activation_identity,
        )

    def test_enforced_admission_requires_a_passed_judge_and_all_deterministic_gates(self) -> None:
        gates = DeterministicAdmissionGates(
            execution=True,
            mutation_authorization=True,
            assessment=True,
            final_grounding=True,
            unsafe_material=True,
            semantic_key=True,
        )

        with self.assertRaisesRegex(ValueError, "judge pass"):
            AdmissionRecord(
                mode="enforced",
                status="admitted",
                gates=gates,
                semantic_judgment="uncertain",
                semantic_policy_id="fixture-semantic-policy",
            )

        admitted = AdmissionRecord(
            mode="enforced",
            status="admitted",
            gates=gates,
            semantic_judgment="pass",
            semantic_policy_id="fixture-semantic-policy",
        )
        self.assertEqual(admitted.semantic_judgment, "pass")

    def test_eligible_enforcement_admits_only_a_judge_pass(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _IndependentShadowJudge,
            _QualityDomain,
        )

        class RecordingGenerator(_GeneratorAndAgentModel):
            def __init__(self) -> None:
                self.requests: list[object] = []

            def complete(self, request: object) -> object:
                self.requests.append(request)
                return super().complete(request)

        policy, activation = _engine_policy_and_activation()
        generator = RecordingGenerator()
        judge = _IndependentShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(_QualityDomain(),), models=(generator, judge))
        )
        configuration = RunConfiguration(
            run_id="enforced-quality-fixture",
            domain_id="quality_review_test_domain",
            model_id=generator.model_id,
            slot_limit=1,
            admission_mode="enforced",
            source_scope_id=policy.source_scope_id,
            task_distribution_scope_id=policy.task_distribution_scope_id,
            generator_prompt_id=policy.generator_prompt_id,
            generator_decoding_id=policy.generator_decoding_id,
            agent_prompt_id=policy.agent_prompt_id,
            agent_decoding_id=policy.agent_decoding_id,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=judge.model_id,
                judge_request_limit=1,
                judge_prompt_id=policy.judge_prompt_id,
                judge_decoding_id=policy.judge_decoding_id,
            ),
            semantic_enforcement=SemanticEnforcementRunConfiguration(
                policy=policy,
                activation=activation,
            ),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            demonstration = _read_json_lines(result.demonstrations_path)[0]
            judgment = _read_json_lines(result.shadow_judgments_path)[0]
            quality_report = json.loads(
                result.quality_report_path.read_text(encoding="utf-8")
            )

        self.assertEqual(result.demonstration_count, 1)
        self.assertEqual(result.negative_count, 0)
        self.assertEqual(demonstration["admission"]["mode"], "enforced")
        self.assertEqual(demonstration["admission"]["semantic_judgment"], "pass")
        self.assertEqual(demonstration["admission"]["semantic_policy_id"], policy.policy_id)
        self.assertEqual(judgment["verdict"], "pass")
        self.assertEqual(quality_report["admission"]["mode"], "enforced")
        self.assertEqual(
            quality_report["semantic_enforcement"]["policy_id"],
            policy.policy_id,
        )
        self.assertEqual(
            quality_report["semantic_enforcement"]["activation_identity"],
            activation.activation_identity,
        )

    def test_enforced_run_keeps_fail_and_unavailable_judgments_out_of_demonstrations(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _ScriptedShadowJudge,
            _QualityDomain,
        )

        policy, activation = _engine_policy_and_activation()
        generator = _GeneratorAndAgentModel()
        judge = _ScriptedShadowJudge(("fail",))
        engine = SynthesisEngine(
            AdapterRegistry(domains=(_QualityDomain(),), models=(generator, judge))
        )
        configuration = _enforced_quality_configuration(
            policy=policy,
            activation=activation,
            judge_model_id=judge.model_id,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negative = _read_json_lines(result.negatives_path)[0]
            judgment = _read_json_lines(result.shadow_judgments_path)[0]

        self.assertEqual(result.demonstration_count, 0)
        self.assertEqual(result.negative_count, 1)
        self.assertEqual(negative["outcome"]["reason_code"], "semantic_judge_fail")
        self.assertEqual(negative["admission"]["semantic_judgment"], "fail")
        self.assertEqual(judgment["verdict"], "fail")

    def test_enforced_run_treats_an_unavailable_judge_as_uncertain_and_rejects_it(self) -> None:
        from tests.test_agent_first_quality_review import (
            _FailedShadowJudge,
            _GeneratorAndAgentModel,
            _QualityDomain,
        )

        policy, activation = _engine_policy_and_activation(
            judge_model_id="quality_failed_judge",
            judge_model_version="quality_failed_judge_v1",
        )
        generator = _GeneratorAndAgentModel()
        judge = _FailedShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(_QualityDomain(),), models=(generator, judge))
        )
        configuration = _enforced_quality_configuration(
            policy=policy,
            activation=activation,
            judge_model_id=judge.model_id,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negative = _read_json_lines(result.negatives_path)[0]
            judgment = _read_json_lines(result.shadow_judgments_path)[0]

        self.assertEqual(result.demonstration_count, 0)
        self.assertEqual(negative["outcome"]["reason_code"], "semantic_judge_unavailable")
        self.assertEqual(negative["admission"]["semantic_judgment"], "unavailable")
        self.assertEqual(judgment["verdict"], "unavailable")

    def test_enforced_run_requires_deterministic_gates_even_after_a_judge_pass(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _IndependentShadowJudge,
            _QualityDomain,
        )

        policy, activation = _engine_policy_and_activation()
        generator = _GeneratorAndAgentModel()
        judge = _IndependentShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(
                domains=(_QualityDomain(unsafe_public_tool_schema=True),),
                models=(generator, judge),
            )
        )
        configuration = _enforced_quality_configuration(
            policy=policy,
            activation=activation,
            judge_model_id=judge.model_id,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = engine.run(configuration, Path(temporary_directory))
            negative = _read_json_lines(result.negatives_path)[0]

        self.assertEqual(result.demonstration_count, 0)
        self.assertEqual(negative["admission"]["mode"], "enforced")
        self.assertEqual(negative["admission"]["semantic_judgment"], "pass")
        self.assertFalse(negative["admission"]["gates"]["unsafe_material"])

    def test_changed_policy_or_run_scope_cannot_borrow_an_old_activation(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _IndependentShadowJudge,
            _QualityDomain,
        )

        policy, activation = _engine_policy_and_activation()
        changed_policy = policy.model_copy(
            update={"source_scope_id": "new-source-scope-v1"}
        )
        with self.assertRaisesRegex(ValueError, "does not bind"):
            SemanticEnforcementRunConfiguration(
                policy=changed_policy,
                activation=activation,
            )

        forged_activation = activation.model_copy(
            update={
                "evaluation": activation.evaluation.model_copy(
                    update={"deterministic_selection_complete": False}
                ),
            }
        )
        with self.assertRaisesRegex(ValueError, "does not match frozen evidence"):
            SemanticEnforcementRunConfiguration(
                policy=policy,
                activation=forged_activation,
            )

        generator = _GeneratorAndAgentModel()
        judge = _IndependentShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(_QualityDomain(),), models=(generator, judge))
        )
        changed_run = _enforced_quality_configuration(
            policy=policy,
            activation=activation,
            judge_model_id=judge.model_id,
        ).model_copy(update={"source_scope_id": "new-source-scope-v1"})

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(
                SemanticEnforcementIneligibleError,
                "source, task, or model settings",
            ):
                engine.run(changed_run, Path(temporary_directory))

        valid_run = _enforced_quality_configuration(
            policy=policy,
            activation=activation,
            judge_model_id=judge.model_id,
        )
        assert valid_run.semantic_enforcement is not None
        forged_run = valid_run.model_copy(
            update={
                "semantic_enforcement": valid_run.semantic_enforcement.model_copy(
                    update={"activation": forged_activation}
                )
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(
                SemanticEnforcementIneligibleError,
                "does not match frozen evidence",
            ):
                engine.run(forged_run, Path(temporary_directory))

    def test_ineligible_enforcement_fails_before_dispatch_without_blocking_shadow_runs(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _IndependentShadowJudge,
            _QualityDomain,
        )

        class RecordingGenerator(_GeneratorAndAgentModel):
            def __init__(self) -> None:
                self.requests: list[object] = []

            def complete(self, request: object) -> object:
                self.requests.append(request)
                return super().complete(request)

        policy, ineligible_activation = _engine_policy_and_activation(
            evaluation_verdicts=(("fail", "fail"),) * 100,
        )
        generator = RecordingGenerator()
        judge = _IndependentShadowJudge()
        engine = SynthesisEngine(
            AdapterRegistry(domains=(_QualityDomain(),), models=(generator, judge))
        )
        enforced = _enforced_quality_configuration(
            policy=policy,
            activation=ineligible_activation,
            judge_model_id=judge.model_id,
        )
        shadow = RunConfiguration(
            run_id="shadow-quality-fixture",
            domain_id="quality_review_test_domain",
            model_id=generator.model_id,
            slot_limit=1,
            shadow_quality=ShadowQualityConfiguration(
                mode="shadow",
                judge_model_id=judge.model_id,
                judge_request_limit=1,
            ),
        )

        with tempfile.TemporaryDirectory() as enforced_directory, tempfile.TemporaryDirectory() as shadow_directory:
            with self.assertRaisesRegex(SemanticEnforcementIneligibleError, "ineligible"):
                engine.run(enforced, Path(enforced_directory))
            shadow_result = engine.run(shadow, Path(shadow_directory))

        self.assertEqual(len(generator.requests), 2)
        self.assertEqual(generator.requests[0].role, "task_generation")
        self.assertEqual(shadow_result.demonstration_count, 1)

    def test_engine_evaluates_existing_frozen_cohorts_and_imported_human_labels(self) -> None:
        from tests.test_agent_first_quality_review import (
            _GeneratorAndAgentModel,
            _IndependentShadowJudge,
            _QualityDomain,
            _human_pass_label,
        )

        policy, _ = _engine_policy_and_activation()
        generator = _GeneratorAndAgentModel()
        judge = _IndependentShadowJudge()
        development_engine = SynthesisEngine(
            AdapterRegistry(
                domains=(_QualityDomain(slot_count=100, slot_start=1),),
                models=(generator, judge),
            )
        )
        evaluation_engine = SynthesisEngine(
            AdapterRegistry(
                domains=(_QualityDomain(slot_count=100, slot_start=101),),
                models=(generator, judge),
            )
        )
        with tempfile.TemporaryDirectory() as development_directory, tempfile.TemporaryDirectory() as evaluation_directory:
            development_result = development_engine.run(
                _calibration_run_configuration(
                    run_id="quality-development-run",
                    policy=policy,
                    judge_model_id=judge.model_id,
                ),
                Path(development_directory),
            )
            development_queue = development_engine.create_review_queue(
                development_result.run_directory,
                ReviewQueueConfiguration(
                    cohort_id="quality-development-cohort",
                    purpose="diagnostic-development",
                    campaign_id="quality-development-campaign",
                    pass_sample_limit=100,
                ),
            )
            development_engine.import_review_labels(
                development_result.run_directory,
                [
                    _human_pass_label(
                        episode_id=item["episode_id"],
                        cohort_id=development_queue.cohort.cohort_id,
                        purpose="diagnostic-development",
                    )
                    for item in _read_json_lines(development_queue.queue_path)
                ],
            )

            evaluation_result = evaluation_engine.run(
                _calibration_run_configuration(
                    run_id="quality-evaluation-run",
                    policy=policy,
                    judge_model_id=judge.model_id,
                ),
                Path(evaluation_directory),
            )
            evaluation_queue = evaluation_engine.create_review_queue(
                evaluation_result.run_directory,
                ReviewQueueConfiguration(
                    cohort_id="quality-evaluation-cohort",
                    purpose="held-out-evaluation",
                    campaign_id="quality-evaluation-campaign",
                    quality_policy_id=policy.policy_id,
                    quality_policy_fingerprint=policy.fingerprint,
                ),
            )
            evaluation_engine.import_review_labels(
                evaluation_result.run_directory,
                [
                    _human_pass_label(
                        episode_id=item["episode_id"],
                        cohort_id=evaluation_queue.cohort.cohort_id,
                        purpose="held-out-evaluation",
                    )
                    for item in _read_json_lines(evaluation_queue.queue_path)
                ],
            )

            report = development_engine.evaluate_semantic_enforcement(
                policy=policy,
                development_run_directories=(development_result.run_directory,),
                development_campaign_id="quality-development-campaign",
                evaluation_run_directories=(evaluation_result.run_directory,),
                evaluation_campaign_id="quality-evaluation-campaign",
            )

        self.assertEqual(report.eligibility, "eligible", report.ineligibility_reasons)
        self.assertEqual(report.development.overall.reviewed_count, 100)
        self.assertEqual(report.evaluation.overall.reviewed_count, 100)
        self.assertTrue(report.evaluation.policy_bound_before_review)

    def test_evaluation_fails_closed_for_unavailable_denominators_identity_scope_reuse_and_safety(self) -> None:
        policy = _policy()
        development = _campaign(
            campaign_id="development-campaign",
            purpose="diagnostic-development",
            policy=policy,
            verdicts=(("pass", "pass"),) * 100,
            bind_policy=False,
        )
        evaluation = _campaign(
            campaign_id="evaluation-campaign",
            purpose="held-out-evaluation",
            policy=policy,
            verdicts=_threshold_verdicts(),
            bind_policy=True,
        )

        unavailable_episodes = list(evaluation.episodes)
        unavailable_episodes[10] = unavailable_episodes[10].model_copy(
            update={"judge_verdict": "unavailable", "human_verdict": "uncertain"}
        )
        unavailable_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": tuple(unavailable_episodes)}),
        )
        self.assertEqual(unavailable_report.eligibility, "eligible")
        self.assertEqual(unavailable_report.evaluation.overall.unavailable_judge_count, 1)
        self.assertEqual(
            unavailable_report.evaluation.overall.confusion_counts["uncertain"]["uncertain"],
            66,
        )

        undefined_episodes = tuple(
            episode.model_copy(update={"judge_verdict": "fail", "human_verdict": "fail"})
            for episode in evaluation.episodes
        )
        undefined_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": undefined_episodes}),
        )
        self.assertIn("overall_false_pass_denominator_zero", undefined_report.ineligibility_reasons)
        self.assertIn("overall_false_fail_denominator_zero", undefined_report.ineligibility_reasons)

        critical_episodes = list(evaluation.episodes)
        critical_episodes[0] = critical_episodes[0].model_copy(
            update={"human_critical_safety_failure": True}
        )
        critical_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": tuple(critical_episodes)}),
        )
        self.assertIn("critical_safety_false_pass_detected", critical_report.ineligibility_reasons)

        identity_episodes = list(evaluation.episodes)
        identity_episodes[0] = identity_episodes[0].model_copy(
            update={"generator_identity": policy.judge_identity}
        )
        identity_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": tuple(identity_episodes)}),
        )
        self.assertIn(
            "evaluation_generator_or_agent_identity_mismatch",
            identity_report.ineligibility_reasons,
        )

        scope_episodes = list(evaluation.episodes)
        scope_episodes[0] = scope_episodes[0].model_copy(
            update={"source_scope_id": "different-source-scope-v1"}
        )
        scope_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": tuple(scope_episodes)}),
        )
        self.assertIn("evaluation_source_or_task_scope_mismatch", scope_report.ineligibility_reasons)

        reused_episodes = list(evaluation.episodes)
        reused_episodes[0] = reused_episodes[0].model_copy(
            update={
                "semantic_task_group": development.episodes[0].semantic_task_group,
                "grounding_group": development.episodes[0].grounding_group,
            }
        )
        reused_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"episodes": tuple(reused_episodes)}),
        )
        self.assertIn("evaluation_reuses_development_evidence", reused_report.ineligibility_reasons)

        unreviewed_development_episode = development.episodes[0].model_copy(
            update={
                "evidence_id": "development-extra-evidence",
                "episode_id": "episode-development-extra",
                "semantic_task_group": _group("semantic", "development-extra"),
                "grounding_group": _group("grounding", "development-extra"),
            }
        )
        extra_development = development.model_copy(
            update={"episodes": (*development.episodes, unreviewed_development_episode)}
        )
        reused_unreviewed_episodes = list(evaluation.episodes)
        reused_unreviewed_episodes[0] = reused_unreviewed_episodes[0].model_copy(
            update={
                "semantic_task_group": unreviewed_development_episode.semantic_task_group,
                "grounding_group": unreviewed_development_episode.grounding_group,
            }
        )
        reused_unreviewed_report = evaluate_semantic_enforcement(
            policy=policy,
            development=extra_development,
            evaluation=evaluation.model_copy(
                update={"episodes": tuple(reused_unreviewed_episodes)}
            ),
        )
        self.assertIn(
            "evaluation_reuses_development_evidence",
            reused_unreviewed_report.ineligibility_reasons,
        )

        unstratified_development_episodes = list(development.episodes)
        unstratified_development_episodes[0] = unstratified_development_episodes[0].model_copy(
            update={
                "task_type": None,
                "difficulty": None,
                "structural_family": None,
            }
        )
        unstratified_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development.model_copy(
                update={"episodes": tuple(unstratified_development_episodes)}
            ),
            evaluation=evaluation,
        )
        self.assertIn("development_passes_not_stratified", unstratified_report.ineligibility_reasons)

        empty_engine = SynthesisEngine(AdapterRegistry(domains=(), models=()))
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_report = empty_engine.evaluate_semantic_enforcement(
                policy=policy,
                development_run_directories=(Path(temporary_directory) / "missing-development",),
                development_campaign_id="missing-development-campaign",
                evaluation_run_directories=(Path(temporary_directory) / "missing-evaluation",),
                evaluation_campaign_id="missing-evaluation-campaign",
            )
        self.assertIn("development_evidence_unavailable", missing_report.ineligibility_reasons)
        self.assertIn("evaluation_evidence_unavailable", missing_report.ineligibility_reasons)

        missing_label_episodes = list(evaluation.episodes)
        missing_label_episodes[0] = missing_label_episodes[0].model_copy(
            update={"human_verdict": None}
        )
        missing_label_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(
                update={"episodes": tuple(missing_label_episodes)}
            ),
        )
        self.assertIn("evaluation_human_labels_incomplete", missing_label_report.ineligibility_reasons)

        short_cohort = evaluation.cohorts[0].model_copy(
            update={"member_evidence_ids": evaluation.cohorts[0].member_evidence_ids[:-1]}
        )
        short_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development,
            evaluation=evaluation.model_copy(update={"cohorts": (short_cohort,)}),
        )
        self.assertIn("evaluation_review_quota_not_met", short_report.ineligibility_reasons)
        self.assertIn(
            "evaluation_selection_not_deterministically_complete",
            short_report.ineligibility_reasons,
        )

        failed_development_episodes = list(development.episodes)
        failed_development_episodes[0] = failed_development_episodes[0].model_copy(
            update={"judge_verdict": "fail", "human_verdict": "fail"}
        )
        failed_development_cohort = development.cohorts[0].model_copy(
            update={"member_evidence_ids": development.cohorts[0].member_evidence_ids[1:]}
        )
        failed_development_report = evaluate_semantic_enforcement(
            policy=policy,
            development=development.model_copy(
                update={
                    "episodes": tuple(failed_development_episodes),
                    "cohorts": (failed_development_cohort,),
                }
            ),
            evaluation=evaluation,
        )
        self.assertIn(
            "development_nonpass_or_unavailable_not_fully_reviewed",
            failed_development_report.ineligibility_reasons,
        )


def _policy() -> SemanticEnforcementPolicy:
    generator = QualityJudgeIdentity(
        provider_id="fixture-provider",
        model_id="fixture-generator",
        model_version="v1",
    )
    return SemanticEnforcementPolicy(
        policy_id="fixture-semantic-policy",
        rubric_id="agent_shadow_quality_rubric_v1",
        judge_identity=QualityJudgeIdentity(
            provider_id="fixture-provider",
            model_id="fixture-judge",
            model_version="v1",
        ),
        generator_identity=generator,
        agent_identity=generator,
        generator_prompt_id="fixture-generation-prompt-v1",
        generator_decoding_id="fixture-generation-decoding-v1",
        agent_prompt_id="fixture-agent-prompt-v1",
        agent_decoding_id="fixture-agent-decoding-v1",
        judge_prompt_id="fixture-judge-prompt-v1",
        judge_decoding_id="fixture-judge-decoding-v1",
        domain_scopes=(
            SemanticEnforcementDomainScope(domain_id="contacts", domain_version="contacts-v1"),
            SemanticEnforcementDomainScope(domain_id="mobile", domain_version="mobile-v1"),
            SemanticEnforcementDomainScope(domain_id="workspace", domain_version="workspace-v1"),
        ),
        source_scope_id="fixture-source-scope-v1",
        task_distribution_scope_id="fixture-task-distribution-v1",
    )


def _campaign(
    *,
    campaign_id: str,
    purpose: str,
    policy: SemanticEnforcementPolicy,
    verdicts: tuple[tuple[str, str], ...],
    bind_policy: bool,
    domains: tuple[tuple[str, str, int], ...] = (
        ("contacts", "contacts-v1", 34),
        ("mobile", "mobile-v1", 33),
        ("workspace", "workspace-v1", 33),
    ),
) -> CalibrationCampaignEvidence:
    episodes: list[CalibrationEpisodeEvidence] = []
    cursor = 0
    for domain_id, domain_version, count in domains:
        for offset in range(count):
            judge_verdict, human_verdict = verdicts[cursor]
            evidence_id = f"{campaign_id}-{domain_id}-{offset:03d}"
            episodes.append(
                CalibrationEpisodeEvidence(
                    evidence_id=evidence_id,
                    episode_id=f"episode-{evidence_id}",
                    domain_id=domain_id,
                    domain_version=domain_version,
                    deterministic_eligible=True,
                    semantic_task_group=_group("semantic", evidence_id),
                    grounding_group=_group("grounding", evidence_id),
                    task_type=f"{domain_id}_task",
                    difficulty="standard",
                    structural_family=f"{domain_id}.fixture.direct",
                    judge_verdict=judge_verdict,
                    judge_identity=policy.judge_identity,
                    human_verdict=human_verdict,
                    human_critical_safety_failure=False,
                    generator_identity=policy.generator_identity,
                    agent_identity=policy.agent_identity,
                    source_scope_id=policy.source_scope_id,
                    task_distribution_scope_id=policy.task_distribution_scope_id,
                    generator_prompt_id=policy.generator_prompt_id,
                    generator_decoding_id=policy.generator_decoding_id,
                    agent_prompt_id=policy.agent_prompt_id,
                    agent_decoding_id=policy.agent_decoding_id,
                    judge_prompt_id=policy.judge_prompt_id,
                    judge_decoding_id=policy.judge_decoding_id,
                )
            )
            cursor += 1
    return CalibrationCampaignEvidence(
        campaign_id=campaign_id,
        purpose=purpose,
        cohorts=(
            CalibrationCohortEvidence(
                cohort_id=f"{campaign_id}-cohort",
                member_evidence_ids=tuple(episode.evidence_id for episode in episodes),
                selection_method=(
                    "held_out_all_deterministically_eligible"
                    if purpose == "held-out-evaluation"
                    else "diagnostic_all_nonpass_stratified_pass"
                ),
                policy_id=policy.policy_id if bind_policy else None,
                policy_fingerprint=policy.fingerprint if bind_policy else None,
                stratified_pass_stratum_count=3,
            ),
        ),
        episodes=tuple(episodes),
    )


def _threshold_verdicts() -> tuple[tuple[str, str], ...]:
    # Every Domain has judge passes; Contacts is exactly at its 10% false-pass
    # ceiling. Overall there are 19 pass/pass, one pass/fail, 66
    # uncertain/uncertain, and 14 fail/uncertain outcomes.
    return (
        *(("pass", "pass"),) * 9,
        ("pass", "fail"),
        *(("uncertain", "uncertain"),) * 20,
        *(("fail", "uncertain"),) * 4,
        *(("pass", "pass"),) * 5,
        *(("uncertain", "uncertain"),) * 23,
        *(("fail", "uncertain"),) * 5,
        *(("pass", "pass"),) * 5,
        *(("uncertain", "uncertain"),) * 23,
        *(("fail", "uncertain"),) * 5,
    )


def _group(kind: str, value: str) -> str:
    return "sha256:" + hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()


def _engine_policy_and_activation(
    *,
    judge_model_id: str = "quality_independent_judge",
    judge_model_version: str = "quality_independent_judge_v1",
    evaluation_verdicts: tuple[tuple[str, str], ...] | None = None,
) -> tuple[
    SemanticEnforcementPolicy,
    object,
]:
    generator = QualityJudgeIdentity(
        provider_id="deterministic_fake",
        model_id="quality_generator_agent",
        model_version="quality_generator_agent_v1",
    )
    policy = SemanticEnforcementPolicy(
        policy_id="quality-fixture-semantic-policy",
        judge_identity=QualityJudgeIdentity(
            provider_id="deterministic_fake",
            model_id=judge_model_id,
            model_version=judge_model_version,
        ),
        generator_identity=generator,
        agent_identity=generator,
        generator_prompt_id="fixture-generation-prompt-v1",
        generator_decoding_id="fixture-generation-decoding-v1",
        agent_prompt_id="fixture-agent-prompt-v1",
        agent_decoding_id="fixture-agent-decoding-v1",
        judge_prompt_id="fixture-judge-prompt-v1",
        judge_decoding_id="fixture-judge-decoding-v1",
        domain_scopes=(
            SemanticEnforcementDomainScope(
                domain_id="quality_review_test_domain",
                domain_version="quality_review_test_domain_v1",
            ),
        ),
        source_scope_id="fixture-source-scope-v1",
        task_distribution_scope_id="fixture-task-distribution-v1",
    )
    domains = (("quality_review_test_domain", "quality_review_test_domain_v1", 100),)
    development = _campaign(
        campaign_id="quality-development-campaign",
        purpose="diagnostic-development",
        policy=policy,
        verdicts=(("pass", "pass"),) * 100,
        bind_policy=False,
        domains=domains,
    )
    evaluation = _campaign(
        campaign_id="quality-evaluation-campaign",
        purpose="held-out-evaluation",
        policy=policy,
        verdicts=evaluation_verdicts or (("pass", "pass"),) * 100,
        bind_policy=True,
        domains=domains,
    )
    return policy, evaluate_semantic_enforcement(
        policy=policy,
        development=development,
        evaluation=evaluation,
    )


def _enforced_quality_configuration(
    *,
    policy: SemanticEnforcementPolicy,
    activation: object,
    judge_model_id: str,
) -> RunConfiguration:
    return RunConfiguration(
        run_id="enforced-quality-fixture",
        domain_id="quality_review_test_domain",
        model_id="quality_generator_agent",
        slot_limit=1,
        admission_mode="enforced",
        source_scope_id=policy.source_scope_id,
        task_distribution_scope_id=policy.task_distribution_scope_id,
        generator_prompt_id=policy.generator_prompt_id,
        generator_decoding_id=policy.generator_decoding_id,
        agent_prompt_id=policy.agent_prompt_id,
        agent_decoding_id=policy.agent_decoding_id,
        shadow_quality=ShadowQualityConfiguration(
            mode="shadow",
            judge_model_id=judge_model_id,
            judge_request_limit=1,
            judge_prompt_id=policy.judge_prompt_id,
            judge_decoding_id=policy.judge_decoding_id,
        ),
        semantic_enforcement=SemanticEnforcementRunConfiguration(
            policy=policy,
            activation=activation,
        ),
    )


def _calibration_run_configuration(
    *,
    run_id: str,
    policy: SemanticEnforcementPolicy,
    judge_model_id: str,
) -> RunConfiguration:
    return RunConfiguration(
        run_id=run_id,
        domain_id="quality_review_test_domain",
        model_id="quality_generator_agent",
        slot_limit=100,
        max_concurrency=4,
        total_request_limit=256,
        generation_request_limit=64,
        agent_request_limit=192,
        source_scope_id=policy.source_scope_id,
        task_distribution_scope_id=policy.task_distribution_scope_id,
        generator_prompt_id=policy.generator_prompt_id,
        generator_decoding_id=policy.generator_decoding_id,
        agent_prompt_id=policy.agent_prompt_id,
        agent_decoding_id=policy.agent_decoding_id,
        shadow_quality=ShadowQualityConfiguration(
            mode="shadow",
            judge_model_id=judge_model_id,
            judge_request_limit=100,
            judge_prompt_id=policy.judge_prompt_id,
            judge_decoding_id=policy.judge_decoding_id,
        ),
    )


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
