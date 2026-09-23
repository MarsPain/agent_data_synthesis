"""Held-out calibration contracts for optional semantic enforcement.

The evaluator is deliberately separate from synthesis admission.  It turns
frozen review evidence into one bounded eligibility report; only a later
explicitly configured run may use that report to request enforcement.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_synthesis.quality import (
    DimensionVerdict,
    QualityJudgeIdentity,
    QualityVerdict,
)


type CalibrationPurpose = Literal["diagnostic-development", "held-out-evaluation"]
type CalibrationSelectionMethod = Literal[
    "diagnostic_all_nonpass_stratified_pass",
    "held_out_all_deterministically_eligible",
    "operator_selected",
]
type EligibilityStatus = Literal["eligible", "ineligible"]

_PUBLIC_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINITE_COHORT_NOTICE = (
    "Finite-cohort rates are empirical measurements, not population guarantees."
)


class SemanticEnforcementDomainScope(BaseModel):
    """One versioned Domain that an activated policy may govern."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str = Field(min_length=1, max_length=128)
    domain_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _require_public_identifiers(self) -> "SemanticEnforcementDomainScope":
        _require_public_identifier(self.domain_id, "domain_id")
        _require_public_identifier(self.domain_version, "domain_version")
        return self


class SemanticEnforcementThresholds(BaseModel):
    """The fixed parent-spec thresholds, frozen into each policy identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_agreement_minimum: float = 0.85
    overall_false_pass_maximum: float = 0.05
    overall_false_fail_maximum: float = 0.10
    per_domain_false_pass_maximum: float = 0.10
    critical_safety_false_pass_maximum: int = 0

    @model_validator(mode="after")
    def _require_the_specified_thresholds(self) -> "SemanticEnforcementThresholds":
        expected = (
            (self.overall_agreement_minimum, 0.85),
            (self.overall_false_pass_maximum, 0.05),
            (self.overall_false_fail_maximum, 0.10),
            (self.per_domain_false_pass_maximum, 0.10),
        )
        if any(
            not math.isclose(actual, target, rel_tol=0.0, abs_tol=1e-12)
            for actual, target in expected
        ):
            raise ValueError("semantic enforcement thresholds must match the parent specification")
        if self.critical_safety_false_pass_maximum != 0:
            raise ValueError("critical safety false-pass threshold must be zero")
        return self


class SemanticEnforcementPolicy(BaseModel):
    """One flat, frozen identity for a judge policy and its evaluated scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_semantic_enforcement_policy_v1"] = (
        "agent_semantic_enforcement_policy_v1"
    )
    policy_id: str = Field(min_length=1, max_length=128)
    rubric_id: Literal["agent_shadow_quality_rubric_v1"] = "agent_shadow_quality_rubric_v1"
    judge_identity: QualityJudgeIdentity | None = None
    generator_identity: QualityJudgeIdentity | None = None
    agent_identity: QualityJudgeIdentity | None = None
    generator_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    generator_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)
    judge_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    judge_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)
    domain_scopes: tuple[SemanticEnforcementDomainScope, ...] = Field(
        default=(), max_length=32
    )
    source_scope_id: str | None = Field(default=None, min_length=1, max_length=128)
    task_distribution_scope_id: str | None = Field(
        default=None, min_length=1, max_length=128
    )
    thresholds: SemanticEnforcementThresholds = Field(
        default_factory=SemanticEnforcementThresholds
    )

    @model_validator(mode="after")
    def _require_a_public_policy_id_and_unique_scope(self) -> "SemanticEnforcementPolicy":
        _require_public_identifier(self.policy_id, "policy_id")
        for value in (
            self.generator_prompt_id,
            self.generator_decoding_id,
            self.agent_prompt_id,
            self.agent_decoding_id,
            self.judge_prompt_id,
            self.judge_decoding_id,
            self.source_scope_id,
            self.task_distribution_scope_id,
        ):
            if value is not None:
                _require_public_identifier(value, "policy setting")
        scopes = {(scope.domain_id, scope.domain_version) for scope in self.domain_scopes}
        if len(scopes) != len(self.domain_scopes):
            raise ValueError("semantic enforcement policy Domain scopes must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        """Return the content address that later evidence and runs must bind."""

        return _hash_payload(self.model_dump(mode="json"))


class CalibrationEpisodeEvidence(BaseModel):
    """Canonical, bounded evidence for one completed Episode in a campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=256)
    episode_id: str = Field(min_length=1, max_length=256)
    domain_id: str = Field(min_length=1, max_length=128)
    domain_version: str = Field(min_length=1, max_length=128)
    deterministic_eligible: bool
    semantic_task_group: str | None = Field(default=None, min_length=1, max_length=128)
    grounding_group: str | None = Field(default=None, min_length=1, max_length=128)
    judge_verdict: QualityVerdict
    judge_identity: QualityJudgeIdentity | None = None
    human_verdict: DimensionVerdict | None = None
    human_critical_safety_failure: bool = False
    generator_identity: QualityJudgeIdentity | None = None
    agent_identity: QualityJudgeIdentity | None = None
    source_scope_id: str | None = Field(default=None, min_length=1, max_length=128)
    task_distribution_scope_id: str | None = Field(
        default=None, min_length=1, max_length=128
    )
    generator_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    generator_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)
    judge_prompt_id: str | None = Field(default=None, min_length=1, max_length=128)
    judge_decoding_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_public_evidence_identifiers(self) -> "CalibrationEpisodeEvidence":
        for value, label in (
            (self.evidence_id, "evidence_id"),
            (self.episode_id, "episode_id"),
            (self.domain_id, "domain_id"),
            (self.domain_version, "domain_version"),
        ):
            _require_public_identifier(value, label)
        for group in (self.semantic_task_group, self.grounding_group):
            if group is not None and not _HASH.fullmatch(group):
                raise ValueError("calibration groups must be canonical hashes")
        return self


class CalibrationCohortEvidence(BaseModel):
    """Frozen review membership and the selection proof for one run cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_id: str = Field(min_length=1, max_length=128)
    member_evidence_ids: tuple[str, ...] = Field(max_length=10_000)
    selection_method: CalibrationSelectionMethod
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    policy_fingerprint: str | None = Field(default=None, min_length=1, max_length=128)
    stratified_pass_stratum_count: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def _bind_optional_policy_identity(self) -> "CalibrationCohortEvidence":
        _require_public_identifier(self.cohort_id, "cohort_id")
        if len(set(self.member_evidence_ids)) != len(self.member_evidence_ids):
            raise ValueError("calibration cohort membership must be unique")
        if any(not _PUBLIC_IDENTIFIER.fullmatch(value) for value in self.member_evidence_ids):
            raise ValueError("calibration cohort evidence ids must be public identifiers")
        if (self.policy_id is None) != (self.policy_fingerprint is None):
            raise ValueError("calibration cohort policy identity must be complete or absent")
        if self.policy_id is not None:
            _require_public_identifier(self.policy_id, "policy_id")
            assert self.policy_fingerprint is not None
            if not _HASH.fullmatch(self.policy_fingerprint):
                raise ValueError("calibration policy fingerprint must be a hash")
        return self


class CalibrationCampaignEvidence(BaseModel):
    """All terminal candidate evidence and frozen review cohorts for one campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str = Field(min_length=1, max_length=128)
    purpose: CalibrationPurpose
    cohorts: tuple[CalibrationCohortEvidence, ...] = Field(default=(), max_length=256)
    episodes: tuple[CalibrationEpisodeEvidence, ...] = Field(default=(), max_length=100_000)

    @model_validator(mode="after")
    def _require_unique_campaign_records(self) -> "CalibrationCampaignEvidence":
        _require_public_identifier(self.campaign_id, "campaign_id")
        evidence_ids = [episode.evidence_id for episode in self.episodes]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("calibration campaign evidence ids must be unique")
        cohort_ids = [cohort.cohort_id for cohort in self.cohorts]
        if len(set(cohort_ids)) != len(cohort_ids):
            raise ValueError("calibration campaign cohort ids must be unique")
        return self


class RateMetric(BaseModel):
    """One empirical rate with its required numerator and denominator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _match_rate_to_its_denominator(self) -> "RateMetric":
        if self.denominator == 0:
            if self.rate is not None:
                raise ValueError("undefined rate must not invent a value")
        elif self.rate is None or not math.isclose(
            self.rate,
            self.numerator / self.denominator,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("rate must match its numerator and denominator")
        return self


class CohortMetrics(BaseModel):
    """The complete three-way outcome table for one overall or Domain slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_count: int = Field(ge=0)
    reviewed_count: int = Field(ge=0)
    missing_human_label_count: int = Field(ge=0)
    unavailable_judge_count: int = Field(ge=0)
    confusion_counts: dict[str, dict[str, int]]
    agreement: RateMetric
    false_pass: RateMetric
    false_fail: RateMetric
    critical_safety_false_pass: RateMetric


class DomainCohortMetrics(CohortMetrics):
    """One Domain-level slice of the same complete metric contract."""

    domain_id: str = Field(min_length=1, max_length=128)
    domain_version: str = Field(min_length=1, max_length=128)


class CalibrationDevelopmentReport(BaseModel):
    """Diagnostic-only calibration-development evidence and raw confusion data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str
    diagnostic_only: Literal[True] = True
    raw_rates_are_diagnostic: Literal[True] = True
    overall: CohortMetrics
    per_domain: tuple[DomainCohortMetrics, ...]
    all_nonpass_or_unavailable_included: bool
    stratified_pass_selection: bool


class HeldOutEvaluationReport(BaseModel):
    """Untouched evaluation evidence used to determine activation eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str
    overall: CohortMetrics
    per_domain: tuple[DomainCohortMetrics, ...]
    deterministic_selection_complete: bool
    policy_bound_before_review: bool
    disjoint_from_development: bool


class SemanticEnforcementEligibilityReport(BaseModel):
    """One immutable, finite-cohort decision with no qualification state machine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_semantic_enforcement_eligibility_report_v1"] = (
        "agent_semantic_enforcement_eligibility_report_v1"
    )
    policy_id: str
    policy_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evaluation_evidence_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activation_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    eligibility: EligibilityStatus
    ineligibility_reasons: tuple[str, ...]
    development: CalibrationDevelopmentReport
    evaluation: HeldOutEvaluationReport
    finite_cohort_notice: str

    @model_validator(mode="after")
    def _bind_the_activation_identity_to_its_evaluation_evidence(
        self,
    ) -> "SemanticEnforcementEligibilityReport":
        expected_identity = _hash_payload(
            {
                "policy_fingerprint": self.policy_fingerprint,
                "evaluation_evidence_fingerprint": self.evaluation_evidence_fingerprint,
            }
        )
        if self.activation_identity != expected_identity:
            raise ValueError("activation identity does not bind policy and evaluation evidence")
        if self.eligibility == "eligible" and self.ineligibility_reasons:
            raise ValueError("eligible activation cannot retain ineligibility reasons")
        if self.eligibility == "ineligible" and not self.ineligibility_reasons:
            raise ValueError("ineligible activation requires explicit reasons")
        return self


class SemanticEnforcementRunConfiguration(BaseModel):
    """The explicit new-run binding of one policy to its held-out activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: SemanticEnforcementPolicy
    activation: SemanticEnforcementEligibilityReport

    @model_validator(mode="after")
    def _require_activation_to_bind_this_exact_policy(
        self,
    ) -> "SemanticEnforcementRunConfiguration":
        if (
            self.activation.policy_id != self.policy.policy_id
            or self.activation.policy_fingerprint != self.policy.fingerprint
        ):
            raise ValueError("semantic enforcement activation does not bind its policy")
        return self


def evaluate_semantic_enforcement(
    *,
    policy: SemanticEnforcementPolicy,
    development: CalibrationCampaignEvidence,
    evaluation: CalibrationCampaignEvidence,
) -> SemanticEnforcementEligibilityReport:
    """Evaluate frozen calibration evidence without changing any Episode artifact."""

    reasons: list[str] = []
    _check_policy(policy, reasons)
    development_summary = _summarize_campaign(development)
    evaluation_summary = _summarize_campaign(evaluation)

    _check_development_campaign(policy, development, development_summary, reasons)
    _check_evaluation_campaign(
        policy,
        development,
        evaluation,
        development_summary,
        evaluation_summary,
        reasons,
    )
    _check_thresholds(policy, evaluation_summary, reasons)

    evaluation_fingerprint = _hash_payload(
        {
            "policy_fingerprint": policy.fingerprint,
            "evaluation": evaluation.model_dump(mode="json"),
        }
    )
    activation_identity = _hash_payload(
        {
            "policy_fingerprint": policy.fingerprint,
            "evaluation_evidence_fingerprint": evaluation_fingerprint,
        }
    )
    unique_reasons = tuple(dict.fromkeys(reasons))
    return SemanticEnforcementEligibilityReport(
        policy_id=policy.policy_id,
        policy_fingerprint=policy.fingerprint,
        evaluation_evidence_fingerprint=evaluation_fingerprint,
        activation_identity=activation_identity,
        eligibility="eligible" if not unique_reasons else "ineligible",
        ineligibility_reasons=unique_reasons,
        development=CalibrationDevelopmentReport(
            campaign_id=development.campaign_id,
            overall=development_summary.overall,
            per_domain=development_summary.per_domain,
            all_nonpass_or_unavailable_included=_all_nonpasses_included(
                development,
                development_summary,
            ),
            stratified_pass_selection=_has_stratified_pass_selection(development),
        ),
        evaluation=HeldOutEvaluationReport(
            campaign_id=evaluation.campaign_id,
            overall=evaluation_summary.overall,
            per_domain=evaluation_summary.per_domain,
            deterministic_selection_complete=_held_out_selection_is_complete(
                evaluation,
                evaluation_summary,
            ),
            policy_bound_before_review=_policy_is_bound_to_evaluation_cohorts(
                policy,
                evaluation,
            ),
            disjoint_from_development=_campaigns_are_disjoint(
                development_summary,
                evaluation_summary,
            ),
        ),
        finite_cohort_notice=_FINITE_COHORT_NOTICE,
    )


def write_semantic_enforcement_eligibility_report(
    path: Path,
    report: SemanticEnforcementEligibilityReport,
) -> Path:
    """Write one sanitized, deterministic eligibility report for later binding."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


class _CampaignSummary:
    def __init__(
        self,
        *,
        evidence_by_id: dict[str, CalibrationEpisodeEvidence],
        reviewed_ids: tuple[str, ...],
        unknown_member_count: int,
        duplicate_member_count: int,
        overall: CohortMetrics,
        per_domain: tuple[DomainCohortMetrics, ...],
    ) -> None:
        self.evidence_by_id = evidence_by_id
        self.reviewed_ids = reviewed_ids
        self.unknown_member_count = unknown_member_count
        self.duplicate_member_count = duplicate_member_count
        self.overall = overall
        self.per_domain = per_domain


def _summarize_campaign(campaign: CalibrationCampaignEvidence) -> _CampaignSummary:
    evidence_by_id = {episode.evidence_id: episode for episode in campaign.episodes}
    cohort_member_ids = [
        member_id
        for cohort in campaign.cohorts
        for member_id in cohort.member_evidence_ids
    ]
    valid_reviewed_ids = tuple(
        member_id for member_id in cohort_member_ids if member_id in evidence_by_id
    )
    reviewed = [evidence_by_id[member_id] for member_id in valid_reviewed_ids]
    overall = _metrics(campaign.episodes, reviewed)
    domains = sorted({(episode.domain_id, episode.domain_version) for episode in campaign.episodes})
    per_domain = tuple(
        DomainCohortMetrics(
            domain_id=domain_id,
            domain_version=domain_version,
            **_metrics(
                [
                    episode
                    for episode in campaign.episodes
                    if (episode.domain_id, episode.domain_version)
                    == (domain_id, domain_version)
                ],
                [
                    episode
                    for episode in reviewed
                    if (episode.domain_id, episode.domain_version)
                    == (domain_id, domain_version)
                ],
            ).model_dump(mode="python"),
        )
        for domain_id, domain_version in domains
    )
    return _CampaignSummary(
        evidence_by_id=evidence_by_id,
        reviewed_ids=valid_reviewed_ids,
        unknown_member_count=len(cohort_member_ids) - len(valid_reviewed_ids),
        duplicate_member_count=len(valid_reviewed_ids) - len(set(valid_reviewed_ids)),
        overall=overall,
        per_domain=per_domain,
    )


def _metrics(
    candidates: Sequence[CalibrationEpisodeEvidence],
    reviewed: Sequence[CalibrationEpisodeEvidence],
) -> CohortMetrics:
    confusion = {
        judge: {human: 0 for human in ("pass", "fail", "uncertain")}
        for judge in ("pass", "fail", "uncertain")
    }
    agreement_numerator = 0
    false_pass_numerator = 0
    judge_pass_denominator = 0
    false_fail_numerator = 0
    human_pass_denominator = 0
    critical_safety_false_pass_numerator = 0
    unavailable_judge_count = 0
    missing_human_label_count = 0
    reviewed_with_labels = 0
    for episode in reviewed:
        if episode.judge_verdict == "unavailable":
            unavailable_judge_count += 1
        if episode.human_verdict is None:
            missing_human_label_count += 1
            continue
        reviewed_with_labels += 1
        judge = _effective_judge_verdict(episode.judge_verdict)
        human = episode.human_verdict
        confusion[judge][human] += 1
        agreement_numerator += judge == human
        if judge == "pass":
            judge_pass_denominator += 1
            false_pass_numerator += human != "pass"
            critical_safety_false_pass_numerator += episode.human_critical_safety_failure
        if human == "pass":
            human_pass_denominator += 1
            false_fail_numerator += judge != "pass"
    return CohortMetrics(
        candidate_count=len(candidates),
        reviewed_count=reviewed_with_labels,
        missing_human_label_count=missing_human_label_count,
        unavailable_judge_count=unavailable_judge_count,
        confusion_counts=confusion,
        agreement=_rate_metric(agreement_numerator, reviewed_with_labels),
        false_pass=_rate_metric(false_pass_numerator, judge_pass_denominator),
        false_fail=_rate_metric(false_fail_numerator, human_pass_denominator),
        critical_safety_false_pass=_rate_metric(
            critical_safety_false_pass_numerator,
            judge_pass_denominator,
        ),
    )


def _rate_metric(numerator: int, denominator: int) -> RateMetric:
    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=None if denominator == 0 else numerator / denominator,
    )


def _effective_judge_verdict(verdict: QualityVerdict) -> DimensionVerdict:
    return "uncertain" if verdict == "unavailable" else verdict


def _check_policy(policy: SemanticEnforcementPolicy, reasons: list[str]) -> None:
    required_values = (
        policy.judge_identity,
        policy.generator_identity,
        policy.agent_identity,
        policy.generator_prompt_id,
        policy.generator_decoding_id,
        policy.agent_prompt_id,
        policy.agent_decoding_id,
        policy.judge_prompt_id,
        policy.judge_decoding_id,
        policy.source_scope_id,
        policy.task_distribution_scope_id,
    )
    if any(value is None for value in required_values) or not policy.domain_scopes:
        reasons.append("policy_identity_or_scope_missing")
        return
    assert policy.judge_identity is not None
    assert policy.generator_identity is not None
    assert policy.agent_identity is not None
    judge = _identity_key(policy.judge_identity)
    if judge in {_identity_key(policy.generator_identity), _identity_key(policy.agent_identity)}:
        reasons.append("policy_judge_identity_not_independent")


def _check_development_campaign(
    policy: SemanticEnforcementPolicy,
    campaign: CalibrationCampaignEvidence,
    summary: _CampaignSummary,
    reasons: list[str],
) -> None:
    if campaign.purpose != "diagnostic-development":
        reasons.append("development_campaign_purpose_invalid")
    if summary.unknown_member_count or summary.duplicate_member_count:
        reasons.append("development_cohort_membership_invalid")
    if summary.overall.reviewed_count < 100:
        reasons.append("development_review_quota_not_met")
    if summary.overall.missing_human_label_count:
        reasons.append("development_human_labels_incomplete")
    if not _all_nonpasses_included(campaign, summary):
        reasons.append("development_nonpass_or_unavailable_not_fully_reviewed")
    if not _has_stratified_pass_selection(campaign):
        reasons.append("development_passes_not_stratified")
    _check_domain_review_quotas(policy, summary, "development", reasons)


def _check_evaluation_campaign(
    policy: SemanticEnforcementPolicy,
    development: CalibrationCampaignEvidence,
    evaluation: CalibrationCampaignEvidence,
    development_summary: _CampaignSummary,
    evaluation_summary: _CampaignSummary,
    reasons: list[str],
) -> None:
    if evaluation.purpose != "held-out-evaluation":
        reasons.append("evaluation_campaign_purpose_invalid")
    if evaluation_summary.unknown_member_count or evaluation_summary.duplicate_member_count:
        reasons.append("evaluation_cohort_membership_invalid")
    if evaluation_summary.overall.reviewed_count < 100:
        reasons.append("evaluation_review_quota_not_met")
    if evaluation_summary.overall.missing_human_label_count:
        reasons.append("evaluation_human_labels_incomplete")
    if not _held_out_selection_is_complete(evaluation, evaluation_summary):
        reasons.append("evaluation_selection_not_deterministically_complete")
    if not _policy_is_bound_to_evaluation_cohorts(policy, evaluation):
        reasons.append("evaluation_policy_not_frozen_before_review")
    if not _campaigns_are_disjoint(development_summary, evaluation_summary):
        reasons.append("evaluation_reuses_development_evidence")
    _check_domain_review_quotas(policy, evaluation_summary, "evaluation", reasons)
    _check_evaluation_scope(policy, evaluation_summary, reasons)


def _check_domain_review_quotas(
    policy: SemanticEnforcementPolicy,
    summary: _CampaignSummary,
    prefix: str,
    reasons: list[str],
) -> None:
    metrics_by_scope = {
        (metric.domain_id, metric.domain_version): metric for metric in summary.per_domain
    }
    for scope in policy.domain_scopes:
        metric = metrics_by_scope.get((scope.domain_id, scope.domain_version))
        if metric is None or metric.reviewed_count < 30:
            reasons.append(f"{prefix}_domain_review_quota_not_met")
            return


def _all_nonpasses_included(
    campaign: CalibrationCampaignEvidence,
    summary: _CampaignSummary,
) -> bool:
    if not campaign.cohorts or any(
        cohort.selection_method != "diagnostic_all_nonpass_stratified_pass"
        for cohort in campaign.cohorts
    ):
        return False
    reviewed = set(summary.reviewed_ids)
    nonpasses = {
        episode.evidence_id
        for episode in campaign.episodes
        if _effective_judge_verdict(episode.judge_verdict) != "pass"
    }
    return nonpasses <= reviewed


def _has_stratified_pass_selection(campaign: CalibrationCampaignEvidence) -> bool:
    return bool(campaign.cohorts) and all(
        cohort.selection_method == "diagnostic_all_nonpass_stratified_pass"
        and cohort.stratified_pass_stratum_count > 0
        for cohort in campaign.cohorts
    )


def _held_out_selection_is_complete(
    campaign: CalibrationCampaignEvidence,
    summary: _CampaignSummary,
) -> bool:
    if not campaign.cohorts or any(
        cohort.selection_method != "held_out_all_deterministically_eligible"
        for cohort in campaign.cohorts
    ):
        return False
    eligible = {
        episode.evidence_id
        for episode in campaign.episodes
        if episode.deterministic_eligible
    }
    return eligible == set(summary.reviewed_ids)


def _policy_is_bound_to_evaluation_cohorts(
    policy: SemanticEnforcementPolicy,
    campaign: CalibrationCampaignEvidence,
) -> bool:
    return bool(campaign.cohorts) and all(
        cohort.policy_id == policy.policy_id
        and cohort.policy_fingerprint == policy.fingerprint
        for cohort in campaign.cohorts
    )


def _campaigns_are_disjoint(
    development: _CampaignSummary,
    evaluation: _CampaignSummary,
) -> bool:
    development_reviewed = [
        development.evidence_by_id[evidence_id]
        for evidence_id in development.reviewed_ids
    ]
    evaluation_reviewed = [
        evaluation.evidence_by_id[evidence_id]
        for evidence_id in evaluation.reviewed_ids
    ]
    development_episode_ids = {episode.episode_id for episode in development_reviewed}
    evaluation_episode_ids = {episode.episode_id for episode in evaluation_reviewed}
    if development_episode_ids & evaluation_episode_ids:
        return False
    development_semantic_groups = {
        episode.semantic_task_group for episode in development_reviewed
    }
    evaluation_semantic_groups = {
        episode.semantic_task_group for episode in evaluation_reviewed
    }
    development_grounding_groups = {episode.grounding_group for episode in development_reviewed}
    evaluation_grounding_groups = {episode.grounding_group for episode in evaluation_reviewed}
    if None in development_semantic_groups or None in evaluation_semantic_groups:
        return False
    if None in development_grounding_groups or None in evaluation_grounding_groups:
        return False
    return not (
        development_semantic_groups & evaluation_semantic_groups
        or development_grounding_groups & evaluation_grounding_groups
    )


def _check_evaluation_scope(
    policy: SemanticEnforcementPolicy,
    summary: _CampaignSummary,
    reasons: list[str],
) -> None:
    expected_scopes = {(scope.domain_id, scope.domain_version) for scope in policy.domain_scopes}
    reviewed = [summary.evidence_by_id[evidence_id] for evidence_id in summary.reviewed_ids]
    actual_scopes = {(episode.domain_id, episode.domain_version) for episode in reviewed}
    if actual_scopes != expected_scopes:
        reasons.append("evaluation_domain_scope_mismatch")
    for episode in reviewed:
        if not episode.deterministic_eligible:
            reasons.append("evaluation_contains_noneligible_episode")
        if episode.semantic_task_group is None or episode.grounding_group is None:
            reasons.append("evaluation_canonical_group_evidence_missing")
        if (
            episode.source_scope_id != policy.source_scope_id
            or episode.task_distribution_scope_id != policy.task_distribution_scope_id
        ):
            reasons.append("evaluation_source_or_task_scope_mismatch")
        if (
            episode.generator_identity != policy.generator_identity
            or episode.agent_identity != policy.agent_identity
        ):
            reasons.append("evaluation_generator_or_agent_identity_mismatch")
        if episode.judge_identity != policy.judge_identity:
            reasons.append("evaluation_judge_identity_mismatch")
        if (
            episode.generator_prompt_id != policy.generator_prompt_id
            or episode.generator_decoding_id != policy.generator_decoding_id
            or episode.agent_prompt_id != policy.agent_prompt_id
            or episode.agent_decoding_id != policy.agent_decoding_id
            or episode.judge_prompt_id != policy.judge_prompt_id
            or episode.judge_decoding_id != policy.judge_decoding_id
        ):
            reasons.append("evaluation_model_settings_mismatch")


def _check_thresholds(
    policy: SemanticEnforcementPolicy,
    summary: _CampaignSummary,
    reasons: list[str],
) -> None:
    overall = summary.overall
    if overall.agreement.denominator == 0:
        reasons.append("agreement_denominator_zero")
    elif not _rate_at_least(
        overall.agreement,
        policy.thresholds.overall_agreement_minimum,
    ):
        reasons.append("overall_agreement_below_threshold")
    if overall.false_pass.denominator == 0:
        reasons.append("overall_false_pass_denominator_zero")
    elif not _rate_at_most(
        overall.false_pass,
        policy.thresholds.overall_false_pass_maximum,
    ):
        reasons.append("overall_false_pass_above_threshold")
    if overall.false_fail.denominator == 0:
        reasons.append("overall_false_fail_denominator_zero")
    elif not _rate_at_most(
        overall.false_fail,
        policy.thresholds.overall_false_fail_maximum,
    ):
        reasons.append("overall_false_fail_above_threshold")
    if overall.critical_safety_false_pass.numerator > 0:
        reasons.append("critical_safety_false_pass_detected")
    for metric in summary.per_domain:
        if metric.false_pass.denominator == 0:
            reasons.append("per_domain_false_pass_denominator_zero")
            continue
        if not _rate_at_most(
            metric.false_pass,
            policy.thresholds.per_domain_false_pass_maximum,
        ):
            reasons.append("per_domain_false_pass_above_threshold")


def _rate_at_least(metric: RateMetric, threshold: float) -> bool:
    return metric.numerator * 10_000 >= metric.denominator * round(threshold * 10_000)


def _rate_at_most(metric: RateMetric, threshold: float) -> bool:
    return metric.numerator * 10_000 <= metric.denominator * round(threshold * 10_000)


def _identity_key(identity: QualityJudgeIdentity) -> tuple[str, str, str]:
    return (identity.provider_id, identity.model_id, identity.model_version)


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_public_identifier(value: str, label: str) -> None:
    if not _PUBLIC_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a bounded public identifier")
