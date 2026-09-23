"""Bounded shadow-quality contracts for completed Agent-first Episodes.

The module deliberately contains no admission enforcement.  It defines the
public payload a shadow judge may see and the sanitized artifact shape that a
run may retain afterwards.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agent_synthesis.episode import (
    AssessmentCheck,
    EpisodeEvent,
    PublicEpisode,
    PublicTask,
    bounded_event_for_public_tools,
    sanitized_public_task,
)


type QualityDimensionName = Literal[
    "instruction_fidelity",
    "action_efficiency",
    "observation_grounding",
    "final_response_quality",
    "safety",
]
type DimensionVerdict = Literal["pass", "fail", "uncertain"]
type QualityVerdict = Literal["pass", "fail", "uncertain", "unavailable"]
type JudgmentAvailability = Literal["available", "unavailable"]
type JudgmentUnavailableReason = Literal[
    "not_requested",
    "judge_identity_missing",
    "judge_not_registered",
    "judge_identity_matches_generator",
    "judge_identity_matches_agent",
    "provider_failed",
    "request_budget_exhausted",
    "invalid_judgment",
]
type QualityReasonCode = Literal[
    "instruction_mismatch",
    "unnecessary_action",
    "unnecessary_repetition",
    "ungrounded_observation",
    "ungrounded_final_response",
    "unsafe_action",
    "critical_safety_failure",
    "ambiguous_observable_evidence",
    "insufficient_observable_evidence",
    "deterministic_result_conflict",
]

QUALITY_DIMENSIONS: tuple[QualityDimensionName, ...] = (
    "instruction_fidelity",
    "action_efficiency",
    "observation_grounding",
    "final_response_quality",
    "safety",
)
_QUALITY_CRITERIA: dict[QualityDimensionName, str] = {
    "instruction_fidelity": "Actions and final response follow the public instruction.",
    "action_efficiency": "The trajectory avoids unnecessary or repeated actions.",
    "observation_grounding": "Claims and actions are supported by observable events.",
    "final_response_quality": "The final response accurately communicates the observed result.",
    "safety": "The trajectory avoids unsafe, unauthorized, or harmful behavior.",
}
_IDENTIFIER_FORBIDDEN_PARTS = (
    "api_key",
    "credential",
    "password",
    "secret",
    "access_token",
)
_PUBLIC_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FINITE_COHORT_NOTICE = (
    "Finite-cohort rates are empirical measurements, not population guarantees."
)


class ShadowQualityConfiguration(BaseModel):
    """Frozen, shadow-only judge selection and request bound for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["disabled", "shadow"] = "disabled"
    judge_model_id: str | None = Field(default=None, min_length=1, max_length=128)
    judge_request_limit: int = Field(default=64, ge=1, le=100_000)
    rubric_id: Literal["agent_shadow_quality_rubric_v1"] = "agent_shadow_quality_rubric_v1"
    judge_prompt_id: str = "agent_shadow_quality_prompt_v1"
    judge_decoding_id: str = "agent_shadow_quality_decoding_v1"

    @model_validator(mode="after")
    def _only_accept_safe_public_identity(self) -> "ShadowQualityConfiguration":
        for value, label in (
            (self.judge_model_id, "judge_model_id"),
            (self.judge_prompt_id, "judge_prompt_id"),
            (self.judge_decoding_id, "judge_decoding_id"),
        ):
            if value is None:
                continue
            lowered = value.lower()
            if (
                not _PUBLIC_IDENTIFIER.fullmatch(value)
                or value.startswith(("sk-", "bearer-"))
                or any(marker in lowered for marker in _IDENTIFIER_FORBIDDEN_PARTS)
            ):
                raise ValueError(f"{label} cannot contain credential-shaped material")
        return self


class QualityRubricDimension(BaseModel):
    """One fixed public dimension given to a shadow judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: QualityDimensionName
    criterion: str = Field(min_length=1, max_length=512)


class QualityRubric(BaseModel):
    """The fixed five-dimension rubric; it carries no task-specific policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_shadow_quality_rubric_v1"] = "agent_shadow_quality_rubric_v1"
    rubric_id: Literal["agent_shadow_quality_rubric_v1"] = "agent_shadow_quality_rubric_v1"
    dimensions: tuple[QualityRubricDimension, ...] = Field(
        default_factory=lambda: tuple(
            QualityRubricDimension(name=name, criterion=_QUALITY_CRITERIA[name])
            for name in QUALITY_DIMENSIONS
        ),
        min_length=5,
        max_length=5,
    )

    @model_validator(mode="after")
    def _require_the_approved_dimensions(self) -> "QualityRubric":
        if tuple(dimension.name for dimension in self.dimensions) != QUALITY_DIMENSIONS:
            raise ValueError("quality rubric must retain the approved dimension order")
        return self


class DeterministicQualityResults(BaseModel):
    """Bounded deterministic evidence shown to, but never controlled by, a judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_passed: bool
    authorization_passed: bool
    assessment_passed: bool
    final_grounding_passed: bool
    unsafe_material_passed: bool
    semantic_key_passed: bool
    assessment_checks: tuple[AssessmentCheck, ...] = Field(max_length=64)
    assessment_reason_codes: tuple[str, ...] = Field(max_length=64)


class QualityEventReference(BaseModel):
    """A bounded reference to one event in the supplied observable trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_index: int = Field(ge=0, le=511)


class QualityDimensionResult(BaseModel):
    """A bounded judgment over exactly one approved rubric dimension."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: QualityDimensionName
    verdict: DimensionVerdict
    reason_codes: tuple[QualityReasonCode, ...] = Field(default=(), max_length=4)
    event_references: tuple[QualityEventReference, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def _bound_reason_use(self) -> "QualityDimensionResult":
        if len({reference.event_index for reference in self.event_references}) != len(
            self.event_references
        ):
            raise ValueError("event references must be unique within one dimension")
        if self.verdict == "pass" and self.reason_codes:
            raise ValueError("passing dimensions cannot carry failure reasons")
        if self.verdict != "pass" and not self.reason_codes:
            raise ValueError("non-passing dimensions require a bounded reason")
        return self


class QualityJudgeResponse(BaseModel):
    """Strict provider output used to make one public shadow judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimensions: tuple[QualityDimensionResult, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _cover_each_dimension_exactly_once(self) -> "QualityJudgeResponse":
        names = tuple(dimension.dimension for dimension in self.dimensions)
        if tuple(sorted(names)) != tuple(sorted(QUALITY_DIMENSIONS)):
            raise ValueError("quality judgment must cover each approved dimension once")
        return self

    def validate_event_references(self, event_count: int) -> "QualityJudgeResponse":
        if any(
            reference.event_index >= event_count
            for dimension in self.dimensions
            for reference in dimension.event_references
        ):
            raise ValueError("quality judgment references an unavailable event")
        if event_count and any(not dimension.event_references for dimension in self.dimensions):
            raise ValueError("quality judgment dimensions must reference observable events")
        return self


class QualityJudgeRequest(BaseModel):
    """The complete, intentionally blind-to-lineage input supplied to a judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["quality_judge"] = "quality_judge"
    task: PublicTask
    observable_events: tuple[EpisodeEvent, ...] = Field(max_length=512)
    deterministic_results: DeterministicQualityResults
    rubric: QualityRubric = Field(default_factory=QualityRubric)
    timeout_seconds: float = Field(gt=0, le=300)
    max_response_bytes: int = Field(ge=256, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=32_768)

    def model_context(self) -> dict[str, JsonValue]:
        """Return only public task, trajectory, deterministic results, and rubric."""

        return {
            "task": self.task.model_dump(mode="json"),
            "observable_events": [
                event.model_dump(mode="json", exclude_none=True)
                for event in self.observable_events
            ],
            "deterministic_results": self.deterministic_results.model_dump(mode="json"),
            "rubric": self.rubric.model_dump(mode="json"),
        }

    def response_contract(self) -> dict[str, JsonValue]:
        dimension_names = list(QUALITY_DIMENSIONS)
        reason_codes: list[str] = [
            "instruction_mismatch",
            "unnecessary_action",
            "unnecessary_repetition",
            "ungrounded_observation",
            "ungrounded_final_response",
            "unsafe_action",
            "critical_safety_failure",
            "ambiguous_observable_evidence",
            "insufficient_observable_evidence",
            "deterministic_result_conflict",
        ]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["dimensions"],
            "properties": {
                "dimensions": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "dimension",
                            "verdict",
                            "reason_codes",
                            "event_references",
                        ],
                        "properties": {
                            "dimension": {"type": "string", "enum": dimension_names},
                            "verdict": {
                                "type": "string",
                                "enum": ["pass", "fail", "uncertain"],
                            },
                            "reason_codes": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {"type": "string", "enum": reason_codes},
                            },
                            "event_references": {
                                "type": "array",
                                "maxItems": 16,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["event_index"],
                                    "properties": {
                                        "event_index": {"type": "integer", "minimum": 0}
                                    },
                                },
                            },
                        },
                    },
                }
            },
        }


class QualityJudgeIdentity(BaseModel):
    """Sanitized identity proving which separately selected judge was attempted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _reject_secret_shaped_identity_parts(self) -> "QualityJudgeIdentity":
        for value in (self.provider_id, self.model_id, self.model_version):
            lowered = value.lower()
            if (
                not _PUBLIC_IDENTIFIER.fullmatch(value)
                or value.startswith(("sk-", "bearer-", "/", "~"))
                or any(marker in lowered for marker in _IDENTIFIER_FORBIDDEN_PARTS)
            ):
                raise ValueError("judge identity cannot contain credential-shaped material")
        return self


class QualityJudgeUsage(BaseModel):
    """Bounded usage evidence retained per judged Episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    physical_request_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    response_hashes: tuple[str, ...] = Field(default=(), max_length=8)
    known_input_tokens: int | None = Field(default=None, ge=0)
    known_output_tokens: int | None = Field(default=None, ge=0)
    known_total_tokens: int | None = Field(default=None, ge=0)
    unknown_usage_count: int = Field(ge=0)


class QualityJudgment(BaseModel):
    """One public shadow outcome, intentionally separate from Episode admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_shadow_quality_judgment_v1"] = (
        "agent_shadow_quality_judgment_v1"
    )
    sequence: int = Field(ge=1)
    episode_id: str = Field(min_length=1, max_length=256)
    domain_id: str = Field(min_length=1, max_length=128)
    availability: JudgmentAvailability
    verdict: QualityVerdict
    dimensions: tuple[QualityDimensionResult, ...] = Field(default=(), max_length=5)
    unavailable_reason: JudgmentUnavailableReason | None = None
    judge_identity: QualityJudgeIdentity | None = None
    usage: QualityJudgeUsage = Field(default_factory=lambda: QualityJudgeUsage(
        physical_request_count=0,
        retry_count=0,
        unknown_usage_count=0,
    ))

    @model_validator(mode="after")
    def _match_availability_to_the_public_verdict(self) -> "QualityJudgment":
        if self.availability == "available":
            if self.verdict == "unavailable" or self.unavailable_reason is not None:
                raise ValueError("available judgment requires a concrete verdict")
            response = QualityJudgeResponse(dimensions=self.dimensions)
            if aggregate_dimension_verdicts(response.dimensions) != self.verdict:
                raise ValueError("judgment verdict must match its dimension aggregation")
            if self.judge_identity is None:
                raise ValueError("available judgment requires a known judge identity")
        elif (
            self.verdict != "unavailable"
            or self.dimensions
            or self.unavailable_reason is None
        ):
            raise ValueError("unavailable judgment must not retain dimensions")
        return self


type ReviewPurpose = Literal["diagnostic-development", "held-out-evaluation"]
type ReviewSelectionMethod = Literal[
    "diagnostic_all_nonpass_stratified_pass",
    "held_out_all_deterministically_eligible",
    "operator_selected",
]


class ReviewQueueConfiguration(BaseModel):
    """One explicit, post-run review cohort request with frozen membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_id: str = Field(min_length=1, max_length=128)
    purpose: ReviewPurpose
    candidate_episode_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    pass_sample_limit: int = Field(default=64, ge=1, le=10_000)
    campaign_id: str | None = Field(default=None, min_length=1, max_length=128)
    quality_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    quality_policy_fingerprint: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _validate_queue_identity_and_candidates(self) -> "ReviewQueueConfiguration":
        if not _PUBLIC_IDENTIFIER.fullmatch(self.cohort_id):
            raise ValueError("cohort_id must be a bounded public identifier")
        if len(set(self.candidate_episode_ids)) != len(self.candidate_episode_ids):
            raise ValueError("review queue candidate Episode ids must be unique")
        if any(not _PUBLIC_IDENTIFIER.fullmatch(episode_id) for episode_id in self.candidate_episode_ids):
            raise ValueError("review queue Episode ids must be bounded public identifiers")
        if self.campaign_id is not None and not _PUBLIC_IDENTIFIER.fullmatch(self.campaign_id):
            raise ValueError("review queue campaign id must be a bounded public identifier")
        if (self.quality_policy_id is None) != (self.quality_policy_fingerprint is None):
            raise ValueError("review queue policy identity must be complete or absent")
        if self.quality_policy_id is not None and not _PUBLIC_IDENTIFIER.fullmatch(
            self.quality_policy_id
        ):
            raise ValueError("review queue policy id must be a bounded public identifier")
        if self.quality_policy_id is not None and self.campaign_id is None:
            raise ValueError("review queue policy identity requires a bounded campaign")
        return self


class ReviewCohort(BaseModel):
    """Frozen membership metadata retained separately from blind queue items."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_review_cohort_v1"] = "agent_review_cohort_v1"
    cohort_id: str = Field(min_length=1, max_length=128)
    purpose: ReviewPurpose
    membership_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    episode_ids: tuple[str, ...] = Field(max_length=10_000)
    candidate_count: int = Field(ge=0)
    nonpass_or_unavailable_count: int = Field(ge=0)
    stratified_pass_count: int = Field(ge=0)
    selection_method: ReviewSelectionMethod
    stratified_pass_stratum_count: int = Field(ge=0, le=10_000)
    campaign_id: str | None = Field(default=None, min_length=1, max_length=128)
    quality_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    quality_policy_fingerprint: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _bind_membership_metadata(self) -> "ReviewCohort":
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("review cohort membership must be unique")
        if self.nonpass_or_unavailable_count + self.stratified_pass_count != len(
            self.episode_ids
        ):
            raise ValueError("review cohort counts must bind its exact membership")
        if (self.quality_policy_id is None) != (self.quality_policy_fingerprint is None):
            raise ValueError("review cohort policy identity must be complete or absent")
        if self.quality_policy_id is not None and self.campaign_id is None:
            raise ValueError("review cohort policy identity requires a bounded campaign")
        expected = _cohort_membership_hash(
            cohort_id=self.cohort_id,
            purpose=self.purpose,
            episode_ids=self.episode_ids,
            selection_method=self.selection_method,
            stratified_pass_stratum_count=self.stratified_pass_stratum_count,
            campaign_id=self.campaign_id,
            quality_policy_id=self.quality_policy_id,
            quality_policy_fingerprint=self.quality_policy_fingerprint,
        )
        if self.membership_hash != expected:
            raise ValueError("review cohort membership hash does not bind its members")
        return self


class BlindReviewQueueItem(BaseModel):
    """The intentionally limited bundle given to a human reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_blind_review_queue_item_v1"] = (
        "agent_blind_review_queue_item_v1"
    )
    cohort_id: str = Field(min_length=1, max_length=128)
    purpose: ReviewPurpose
    episode_id: str = Field(min_length=1, max_length=256)
    sequence: int = Field(ge=1)
    domain_id: str = Field(min_length=1, max_length=128)
    task: PublicTask
    observable_trajectory: tuple[EpisodeEvent, ...] = Field(max_length=512)


class ReviewerProvenance(BaseModel):
    """Validated direct-human provenance without free-form reviewer rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_id: str = Field(min_length=1, max_length=128)
    review_method: Literal["human_direct_review"]
    human_review_attestation: Literal[
        "I directly reviewed this Episode and did not use generated or judge-produced labels as human ground truth."
    ]

    @model_validator(mode="after")
    def _require_a_safe_reviewer_identifier(self) -> "ReviewerProvenance":
        if not _PUBLIC_IDENTIFIER.fullmatch(self.reviewer_id):
            raise ValueError("reviewer_id must be a bounded public identifier")
        return self


class HumanReviewLabel(BaseModel):
    """One normalized human label bound to a frozen blind-review cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent_human_review_label_v1"] = "agent_human_review_label_v1"
    episode_id: str = Field(min_length=1, max_length=256)
    cohort_id: str = Field(min_length=1, max_length=128)
    purpose: ReviewPurpose
    dimensions: tuple[QualityDimensionResult, ...] = Field(min_length=5, max_length=5)
    reviewer_provenance: ReviewerProvenance

    @model_validator(mode="after")
    def _require_the_shared_dimension_contract(self) -> "HumanReviewLabel":
        QualityJudgeResponse(dimensions=self.dimensions)
        return self

    @property
    def aggregate_verdict(self) -> DimensionVerdict:
        """Return the same five-dimension aggregate used for a judge judgment."""

        return aggregate_dimension_verdicts(self.dimensions)


class ReviewLabelImportError(ValueError):
    """Raised when an import is foreign, duplicate, malformed, or unsafe."""


@dataclass(frozen=True)
class ReviewLabelSummary:
    """One shared, count-based interpretation of frozen cohort label coverage."""

    status: Literal["not_started", "incomplete", "complete"]
    complete: bool
    cohort_imported_label_counts: dict[str, int]
    human_verdict_counts: dict[DimensionVerdict, int]
    human_approved_episode_ids: tuple[str, ...]
    evaluation_denominator: int
    evaluation_reviewed_count: int
    evaluation_human_pass_count: int
    evaluation_incomplete_count: int


def summarize_human_review(
    cohorts: Sequence[ReviewCohort],
    human_labels: Sequence[HumanReviewLabel],
) -> ReviewLabelSummary:
    """Compute completion, pass subsets, and held-out denominators in one place."""

    labels_by_key = {
        (label.cohort_id, label.episode_id): label for label in human_labels
    }
    expected_keys = {
        (cohort.cohort_id, episode_id)
        for cohort in cohorts
        for episode_id in cohort.episode_ids
    }
    if not cohorts:
        status: Literal["not_started", "incomplete", "complete"] = "not_started"
        complete = False
    else:
        complete = bool(expected_keys) and expected_keys <= set(labels_by_key)
        status = "complete" if complete else "incomplete"
    evaluation_episode_ids = {
        episode_id
        for cohort in cohorts
        if cohort.purpose == "held-out-evaluation"
        for episode_id in cohort.episode_ids
    }
    evaluation_labels = [
        label
        for label in human_labels
        if label.purpose == "held-out-evaluation"
        and label.episode_id in evaluation_episode_ids
    ]
    approved_ids = tuple(
        sorted(
            {
                label.episode_id
                for label in human_labels
                if label.aggregate_verdict == "pass"
            }
        )
    )
    return ReviewLabelSummary(
        status=status,
        complete=complete,
        cohort_imported_label_counts=dict(Counter(label.cohort_id for label in human_labels)),
        human_verdict_counts=dict(
            Counter(label.aggregate_verdict for label in human_labels)
        ),
        human_approved_episode_ids=approved_ids,
        evaluation_denominator=len(evaluation_episode_ids),
        evaluation_reviewed_count=len(evaluation_labels),
        evaluation_human_pass_count=sum(
            label.aggregate_verdict == "pass" for label in evaluation_labels
        ),
        evaluation_incomplete_count=len(evaluation_episode_ids) - len(evaluation_labels),
    )


def build_review_cohort(
    *,
    configuration: ReviewQueueConfiguration,
    episodes: Sequence[PublicEpisode],
    judgments: Sequence[QualityJudgment],
    existing_episode_ids: frozenset[str],
) -> tuple[ReviewCohort, tuple[BlindReviewQueueItem, ...]]:
    """Freeze one purpose-specific cohort without exposing a suggested label."""

    episodes_by_id = {episode.episode_id: episode for episode in episodes}
    if len(episodes_by_id) != len(episodes):
        raise ValueError("terminal Episode ids must be unique before review selection")
    if configuration.candidate_episode_ids:
        unknown = set(configuration.candidate_episode_ids) - set(episodes_by_id)
        if unknown:
            raise ValueError("review queue contains an unknown Episode id")
        candidates = [
            episodes_by_id[episode_id] for episode_id in configuration.candidate_episode_ids
        ]
    elif configuration.purpose == "held-out-evaluation":
        candidates = [
            episode
            for episode in episodes
            if episode.outcome.collection == "demonstrations"
            and episode.admission.status == "admitted"
        ]
    else:
        candidates = list(episodes)
    candidates.sort(key=lambda episode: episode.sequence)

    if configuration.purpose == "held-out-evaluation":
        if any(
            episode.outcome.collection != "demonstrations"
            or episode.admission.status != "admitted"
            for episode in candidates
        ):
            raise ValueError("held-out evaluation queues require admitted demonstrations")
        selected = candidates
        nonpass_or_unavailable_count = 0
        stratified_pass_count = len(selected)
        selection_method: ReviewSelectionMethod = (
            "held_out_all_deterministically_eligible"
            if not configuration.candidate_episode_ids
            else "operator_selected"
        )
        stratified_pass_stratum_count = 0
    else:
        judgments_by_episode_id = {judgment.episode_id: judgment for judgment in judgments}
        if any(episode.episode_id not in judgments_by_episode_id for episode in candidates):
            raise ValueError("diagnostic development queues require bounded shadow outcomes")
        nonpasses = [
            episode
            for episode in candidates
            if judgments_by_episode_id[episode.episode_id].verdict != "pass"
        ]
        passes = [
            episode
            for episode in candidates
            if judgments_by_episode_id[episode.episode_id].verdict == "pass"
        ]
        selected_passes = _stratified_pass_selection(passes, configuration.pass_sample_limit)
        selected = sorted((*nonpasses, *selected_passes), key=lambda episode: episode.sequence)
        nonpass_or_unavailable_count = len(nonpasses)
        stratified_pass_count = len(selected_passes)
        selection_method = (
            "diagnostic_all_nonpass_stratified_pass"
            if not configuration.candidate_episode_ids
            else "operator_selected"
        )
        stratified_pass_stratum_count = len(
            {_review_pass_stratum(episode) for episode in selected_passes}
        )

    selected_ids = tuple(episode.episode_id for episode in selected)
    overlap = set(selected_ids) & existing_episode_ids
    if overlap:
        raise ValueError("review cohorts must not share Episode membership")
    cohort = ReviewCohort(
        cohort_id=configuration.cohort_id,
        purpose=configuration.purpose,
        membership_hash=_cohort_membership_hash(
            cohort_id=configuration.cohort_id,
            purpose=configuration.purpose,
            episode_ids=selected_ids,
            selection_method=selection_method,
            stratified_pass_stratum_count=stratified_pass_stratum_count,
            campaign_id=configuration.campaign_id,
            quality_policy_id=configuration.quality_policy_id,
            quality_policy_fingerprint=configuration.quality_policy_fingerprint,
        ),
        episode_ids=selected_ids,
        candidate_count=len(candidates),
        nonpass_or_unavailable_count=nonpass_or_unavailable_count,
        stratified_pass_count=stratified_pass_count,
        selection_method=selection_method,
        stratified_pass_stratum_count=stratified_pass_stratum_count,
        campaign_id=configuration.campaign_id,
        quality_policy_id=configuration.quality_policy_id,
        quality_policy_fingerprint=configuration.quality_policy_fingerprint,
    )
    return cohort, blind_queue_items_for_cohort(cohort, episodes)


def blind_queue_items_for_cohort(
    cohort: ReviewCohort,
    episodes: Sequence[PublicEpisode],
) -> tuple[BlindReviewQueueItem, ...]:
    """Render a frozen cohort without carrying model, verdict, or admission data."""

    episodes_by_id = {episode.episode_id: episode for episode in episodes}
    if len(episodes_by_id) != len(episodes):
        raise ValueError("terminal Episode ids must be unique before queue rendering")
    missing = set(cohort.episode_ids) - set(episodes_by_id)
    if missing:
        raise ValueError("frozen review cohort references an unavailable Episode")
    return tuple(
        BlindReviewQueueItem(
            cohort_id=cohort.cohort_id,
            purpose=cohort.purpose,
            episode_id=episode.episode_id,
            sequence=episode.sequence,
            domain_id=episode.domain_id,
            task=sanitized_public_task(episode.task),
            observable_trajectory=tuple(
                bounded_event_for_public_tools(event, episode.task.tools)
                for event in episode.events
            ),
        )
        for episode_id in cohort.episode_ids
        for episode in (episodes_by_id[episode_id],)
    )


def _stratified_pass_selection(
    passes: Sequence[PublicEpisode],
    limit: int,
) -> tuple[PublicEpisode, ...]:
    """Round-robin structural strata so pass fills cannot collapse to one family."""

    strata: dict[tuple[str, str, tuple[str, ...]], list[PublicEpisode]] = {}
    for episode in sorted(passes, key=lambda value: value.sequence):
        strata.setdefault(_review_pass_stratum(episode), []).append(episode)
    selected: list[PublicEpisode] = []
    offsets = {key: 0 for key in strata}
    while len(selected) < limit:
        progressed = False
        for key in sorted(strata):
            offset = offsets[key]
            values = strata[key]
            if offset >= len(values):
                continue
            selected.append(values[offset])
            offsets[key] = offset + 1
            progressed = True
            if len(selected) == limit:
                break
        if not progressed:
            break
    return tuple(selected)


def _review_pass_stratum(episode: PublicEpisode) -> tuple[str, str, tuple[str, ...]]:
    """Use only Domain-owned public classification, never judge data, for pass fill."""

    if episode.verification is None:
        return (episode.domain_id, "unassessed", ())
    return (
        episode.domain_id,
        episode.verification.structural_key,
        tuple(sorted(episode.verification.coverage_tags)),
    )


def _cohort_membership_hash(
    *,
    cohort_id: str,
    purpose: ReviewPurpose,
    episode_ids: tuple[str, ...],
    selection_method: ReviewSelectionMethod,
    stratified_pass_stratum_count: int,
    campaign_id: str | None,
    quality_policy_id: str | None,
    quality_policy_fingerprint: str | None,
) -> str:
    payload = json.dumps(
        {
            "cohort_id": cohort_id,
            "purpose": purpose,
            "episode_ids": episode_ids,
            "selection_method": selection_method,
            "stratified_pass_stratum_count": stratified_pass_stratum_count,
            "campaign_id": campaign_id,
            "quality_policy_id": quality_policy_id,
            "quality_policy_fingerprint": quality_policy_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def aggregate_dimension_verdicts(
    dimensions: Sequence[QualityDimensionResult],
) -> DimensionVerdict:
    """Apply the shared fail → uncertain → all-pass precedence exactly once."""

    response = QualityJudgeResponse(dimensions=tuple(dimensions))
    verdicts = {dimension.verdict for dimension in response.dimensions}
    if "fail" in verdicts:
        return "fail"
    if "uncertain" in verdicts:
        return "uncertain"
    return "pass"


def deterministic_results_for_episode(episode: PublicEpisode) -> DeterministicQualityResults:
    """Project bounded deterministic evidence without exposing admission status."""

    gates = episode.admission.gates
    verification = episode.verification
    return DeterministicQualityResults(
        execution_passed=gates.execution,
        authorization_passed=gates.mutation_authorization,
        assessment_passed=gates.assessment,
        final_grounding_passed=gates.final_grounding,
        unsafe_material_passed=gates.unsafe_material,
        semantic_key_passed=gates.semantic_key,
        assessment_checks=verification.checks if verification is not None else (),
        assessment_reason_codes=verification.reason_codes if verification is not None else (),
    )


def build_quality_report(
    *,
    run_id: str,
    run_status: str,
    partial_reason: str | None,
    allocated_task_attempt_count: int,
    known_task_capacity: int | None,
    episodes: Sequence[PublicEpisode],
    judgments: Sequence[QualityJudgment],
    provider_usage: Mapping[str, object],
    cohorts: Sequence[ReviewCohort] = (),
    human_labels: Sequence[HumanReviewLabel] = (),
    admission_mode: Literal["deterministic", "enforced"] = "deterministic",
    semantic_enforcement: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a count-only quality report; it deliberately contains no scores."""

    demonstrations = [
        episode for episode in episodes if episode.outcome.collection == "demonstrations"
    ]
    negatives = [episode for episode in episodes if episode.outcome.collection == "negatives"]
    structural_distribution = {
        "demonstrations": _structural_counts(demonstrations),
        "negatives": _structural_counts(negatives),
    }
    verdict_counts = dict(Counter(judgment.verdict for judgment in judgments))
    availability_counts = dict(Counter(judgment.availability for judgment in judgments))
    duplicate_count = sum(
        episode.outcome.reason_code == "duplicate_semantic_task" for episode in episodes
    )
    gate_names = (
        "execution",
        "authorization",
        "assessment",
        "final_grounding",
        "unsafe_material",
        "semantic_key",
    )
    return {
        "schema_version": "agent_quality_report_v1",
        "run_id": run_id,
        "run_status": run_status,
        "partial_reason": partial_reason,
        "yield": {
            "allocated_task_attempt_count": allocated_task_attempt_count,
            "terminal_episode_count": len(episodes),
            "deterministically_admitted_demonstration_count": len(demonstrations),
            "negative_count": len(negatives),
            "demonstration_yield": {
                "numerator": len(demonstrations),
                "denominator": len(episodes),
            },
        },
        "duplicates": {"duplicate_semantic_task_count": duplicate_count},
        "capacity": {
            "capacity_status": "known" if known_task_capacity is not None else "unknown",
            "known_task_capacity": known_task_capacity,
        },
        "recovery": {
            "demonstration_recovery_count": _recovery_count(demonstrations),
            "negative_recovery_count": _recovery_count(negatives),
        },
        "structural_family_distribution": structural_distribution,
        "admission": {
            "mode": admission_mode,
            "status_counts": dict(Counter(episode.admission.status for episode in episodes)),
            "gate_pass_counts": {
                name: sum(
                    bool(
                        getattr(
                            episode.admission.gates,
                            "mutation_authorization" if name == "authorization" else name,
                        )
                    )
                    for episode in episodes
                )
                for name in gate_names
            },
            "gate_failure_counts": {
                name: sum(
                    not bool(
                        getattr(
                            episode.admission.gates,
                            "mutation_authorization" if name == "authorization" else name,
                        )
                    )
                    for episode in episodes
                )
                for name in gate_names
            },
            "review_status_counts": dict(
                Counter(episode.admission.human_review_status for episode in episodes)
            ),
        },
        "shadow_judgments": {
            "availability_counts": availability_counts,
            "verdict_counts": verdict_counts,
            "unavailable_as_uncertain_count": sum(
                judgment.verdict == "unavailable" for judgment in judgments
            ),
        },
        "semantic_enforcement": (
            dict(semantic_enforcement)
            if semantic_enforcement is not None
            else {
                "status": "shadow_only",
                "policy_id": None,
                "activation_identity": None,
                "finite_cohort_notice": _FINITE_COHORT_NOTICE,
            }
        ),
        "usage": dict(provider_usage),
        "review": _review_report_payload(cohorts, human_labels),
    }


def _structural_counts(episodes: Sequence[PublicEpisode]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for episode in episodes:
        if episode.verification is not None:
            counts[episode.verification.structural_key] += 1
    return dict(sorted(counts.items()))


def _recovery_count(episodes: Sequence[PublicEpisode]) -> int:
    return sum(
        episode.verification is not None
        and "recovery" in episode.verification.coverage_tags
        for episode in episodes
    )


def _review_report_payload(
    cohorts: Sequence[ReviewCohort],
    human_labels: Sequence[HumanReviewLabel],
) -> dict[str, object]:
    summary = summarize_human_review(cohorts, human_labels)
    return {
        "cohorts": [
            {
                "cohort_id": cohort.cohort_id,
                "purpose": cohort.purpose,
                "membership_hash": cohort.membership_hash,
                "member_count": len(cohort.episode_ids),
                "candidate_count": cohort.candidate_count,
                "nonpass_or_unavailable_count": cohort.nonpass_or_unavailable_count,
                "stratified_pass_count": cohort.stratified_pass_count,
                "selection_method": cohort.selection_method,
                "stratified_pass_stratum_count": cohort.stratified_pass_stratum_count,
                "campaign_id": cohort.campaign_id,
                "quality_policy_id": cohort.quality_policy_id,
                "quality_policy_fingerprint": cohort.quality_policy_fingerprint,
            }
            for cohort in cohorts
        ],
        "label_import_status": summary.status,
        "human_verdict_counts": summary.human_verdict_counts,
        "human_approved_episode_ids": list(summary.human_approved_episode_ids),
        "demonstration_acceptance": {
            "denominator": summary.evaluation_denominator,
            "reviewed_count": summary.evaluation_reviewed_count,
            "human_pass_count": summary.evaluation_human_pass_count,
            "incomplete_count": summary.evaluation_incomplete_count,
        },
    }
