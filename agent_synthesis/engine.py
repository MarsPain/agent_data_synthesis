"""Bounded, resumable Agent rollout engine for the Agent-first seam."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fcntl

from pydantic import BaseModel, JsonValue, ValidationError

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.enforcement import (
    CalibrationCampaignEvidence,
    CalibrationCohortEvidence,
    CalibrationEpisodeEvidence,
    SemanticEnforcementEligibilityReport,
    SemanticEnforcementPolicy,
    SemanticEnforcementRunConfiguration,
    evaluate_semantic_enforcement as evaluate_semantic_enforcement_evidence,
)
from agent_synthesis.domain import (
    CompilationRejection,
    CompiledTask,
    DomainEpisode,
    DomainRun,
    FrozenInitialState,
    TaskProposal,
    TaskSlot,
    ToolExecutionResult,
)
from agent_synthesis.episode import (
    AdmissionRecord,
    DeterministicAdmissionGates,
    EpisodeAssessment,
    EpisodeEvent,
    EpisodeOutcome,
    ExecutionTrace,
    ModelLineage,
    PublicEpisode,
    PublicTask,
    RoleLineage,
    ToolDefinition,
    bounded_event_for_public_tools,
    has_unsafe_public_material,
    sanitized_episode_record,
    sanitized_public_task,
)
from agent_synthesis.ledger import (
    AllocatedSlotRecord,
    FrozenStateRecord,
    PrivateLedger,
    ProviderRequestRecord,
    TaskCaseRecord,
    TerminalOutcomeRecord,
    WorkItemRecord,
)
from agent_synthesis.manifest import build_manifest, write_manifest
from agent_synthesis.model import (
    AgentRequest,
    FinalResponseDecision,
    GenerationResponse,
    JsonModelAdapter,
    JsonModelRequest,
    JsonModelResponse,
    ModelCallError,
    ModelRole,
    TaskGenerationRequest,
    TokenUsage,
    ToolCallDecision,
    parse_agent_decision,
)
from agent_synthesis.registry import AdapterRegistry
from agent_synthesis.quality import (
    JudgmentUnavailableReason,
    QualityJudgeIdentity,
    QualityJudgeRequest,
    QualityJudgeResponse,
    QualityJudgeUsage,
    QualityJudgment,
    BlindReviewQueueItem,
    HumanReviewLabel,
    ReviewCohort,
    ReviewLabelImportError,
    ReviewQueueConfiguration,
    aggregate_dimension_verdicts,
    blind_queue_items_for_cohort,
    build_review_cohort,
    build_quality_report,
    deterministic_results_for_episode,
    summarize_human_review,
)


@dataclass(frozen=True)
class RunResult:
    """Paths, durable status, and collection counts from one local synthesis trace."""

    run_directory: Path
    demonstrations_path: Path
    negatives_path: Path
    provider_usage_path: Path
    manifest_path: Path
    private_ledger_path: Path
    demonstration_count: int
    negative_count: int
    status: Literal["completed", "partial", "cancelled", "failed"]
    partial_reason: str | None
    task_attempt_count: int
    terminal_outcome_count: int
    physical_request_count: int
    run_report_path: Path
    shadow_judgments_path: Path
    quality_report_path: Path


@dataclass(frozen=True)
class ReplayEpisodeResult:
    """One provider-free comparison of saved and re-executed Episode evidence."""

    episode_id: str
    sequence: int
    status: Literal[
        "aligned",
        "observation_drift",
        "assessment_drift",
        "observation_and_assessment_drift",
        "not_executed",
        "replay_failed",
    ]
    observation_drift: bool
    assessment_drift: bool


@dataclass(frozen=True)
class ReplayResult:
    """A deterministic offline replay report written alongside a completed run."""

    run_directory: Path
    report_path: Path
    episode_results: tuple[ReplayEpisodeResult, ...]

    @property
    def aligned(self) -> bool:
        return all(result.status in {"aligned", "not_executed"} for result in self.episode_results)


@dataclass(frozen=True)
class ReviewQueueResult:
    """One newly frozen blind-review cohort and its public queue paths."""

    run_directory: Path
    cohort: ReviewCohort
    queue_path: Path
    cohorts_path: Path
    quality_report_path: Path


@dataclass(frozen=True)
class ReviewLabelImportResult:
    """The bounded status of one human-label import into frozen cohorts."""

    run_directory: Path
    status: Literal["incomplete", "complete"]
    complete: bool
    labels_path: Path
    report_path: Path
    quality_report_path: Path
    human_approved_episode_ids: tuple[str, ...]


@dataclass(frozen=True)
class _EpisodeContext:
    """Core-owned stable identity shared by one terminal record."""

    configuration: RunConfiguration
    domain_version: str
    sequence: int


@dataclass(frozen=True)
class _LogicalCallResult:
    """The charged physical records and one bounded logical request outcome."""

    response: JsonModelResponse | None
    records: tuple[ProviderRequestRecord, ...]
    error_code: str | None


@dataclass(frozen=True)
class _EpisodeAttemptResult:
    """One worker result, preserving incomplete work for a later resume."""

    episode: PublicEpisode | None
    partial_reason: Literal["operator_cancelled", "provider_request_budget_exhausted"] | None


@dataclass(frozen=True)
class _InFlightEpisode:
    """The owner and semantic admission key for one active Episode future."""

    sequence: int
    semantic_key: str
    owner_id: str


@dataclass(frozen=True)
class _RequestUsageSummary:
    """One role's physical-request and reported-usage aggregates."""

    physical_request_count: int
    retry_count: int
    repair_request_count: int
    known_input_tokens: int | None
    known_output_tokens: int | None
    known_total_tokens: int | None
    unknown_usage_count: int
    reserved_request_count: int
    failed_request_count: int
    completed_request_count: int


@dataclass(frozen=True)
class _ShadowJudgeContext:
    """Resolved shadow judge state; no unavailable state can dispatch a request."""

    model: JsonModelAdapter | None
    identity: QualityJudgeIdentity | None
    unavailable_reason: JudgmentUnavailableReason | None


@dataclass(frozen=True)
class _SemanticEnforcementContext:
    """The one preflight-validated policy allowed to alter a new run's admission."""

    configuration: SemanticEnforcementRunConfiguration


class SemanticEnforcementIneligibleError(ValueError):
    """Raised before dispatch when an enforce-mode run lacks exact eligibility evidence."""


class CancellationSignal:
    """Thread-safe cooperative cancellation for a bounded local run."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


class RunLockedError(RuntimeError):
    """Raised when another live process currently owns a run directory."""


class FrozenInputError(ValueError):
    """Raised when a required private frozen-input snapshot is unavailable."""


FailureInjector = Callable[[str], None]


class _RunDirectoryWriterLock:
    """An advisory process-lifetime lock with no persistent recovery state."""

    def __init__(self, run_directory: Path) -> None:
        self._path = run_directory / ".private" / "writer.lock"
        self._handle: object | None = None

    def __enter__(self) -> "_RunDirectoryWriterLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise RunLockedError(f"run directory already has an active writer: {self._path.parent}") from None
        self._handle = handle
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        handle = self._handle
        if handle is None:
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        self._handle = None


class SynthesisEngine:
    """Run registered Domains and JSON models with bounded durable accounting."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def _shadow_judge_context(
        self,
        configuration: RunConfiguration,
        generator_and_agent_model: JsonModelAdapter,
    ) -> _ShadowJudgeContext:
        """Resolve the optional judge without allowing identity failures to dispatch."""

        quality = configuration.shadow_quality
        if quality.mode == "disabled":
            return _ShadowJudgeContext(
                model=None,
                identity=None,
                unavailable_reason="not_requested",
            )
        if quality.judge_model_id is None:
            return _ShadowJudgeContext(
                model=None,
                identity=None,
                unavailable_reason="judge_identity_missing",
            )
        try:
            judge = self._registry.model(quality.judge_model_id)
        except KeyError:
            return _ShadowJudgeContext(
                model=None,
                identity=None,
                unavailable_reason="judge_not_registered",
            )
        try:
            identity = QualityJudgeIdentity(
                provider_id=judge.provider_id,
                model_id=judge.model_id,
                model_version=judge.model_version,
            )
        except (TypeError, ValidationError, ValueError):
            return _ShadowJudgeContext(
                model=None,
                identity=None,
                unavailable_reason="judge_identity_missing",
            )
        try:
            generator_identity = QualityJudgeIdentity(
                provider_id=generator_and_agent_model.provider_id,
                model_id=generator_and_agent_model.model_id,
                model_version=generator_and_agent_model.model_version,
            )
        except (TypeError, ValidationError, ValueError):
            return _ShadowJudgeContext(
                model=None,
                identity=None,
                unavailable_reason="judge_identity_missing",
            )
        judge_identity = (identity.provider_id, identity.model_id, identity.model_version)
        generator_identity_key = (
            generator_identity.provider_id,
            generator_identity.model_id,
            generator_identity.model_version,
        )
        if judge_identity == generator_identity_key:
            return _ShadowJudgeContext(
                model=None,
                identity=identity,
                unavailable_reason="judge_identity_matches_generator",
            )
        return _ShadowJudgeContext(model=judge, identity=identity, unavailable_reason=None)

    def _semantic_enforcement_context(
        self,
        *,
        configuration: RunConfiguration,
        domain: object,
        generator_and_agent_model: JsonModelAdapter,
        shadow_judge: _ShadowJudgeContext,
    ) -> _SemanticEnforcementContext | None:
        """Reject stale, mismatched, or unavailable activation before any provider call."""

        if configuration.admission_mode == "deterministic":
            return None
        enforcement = configuration.semantic_enforcement
        if enforcement is None:
            raise SemanticEnforcementIneligibleError(
                "enforced admission requires semantic enforcement evidence"
            )
        activation = enforcement.activation
        policy = enforcement.policy
        if activation.eligibility != "eligible":
            raise SemanticEnforcementIneligibleError(
                "semantic enforcement activation is ineligible"
            )
        if (
            activation.policy_id != policy.policy_id
            or activation.policy_fingerprint != policy.fingerprint
        ):
            raise SemanticEnforcementIneligibleError(
                "semantic enforcement activation does not bind its policy"
            )
        expected_activation = evaluate_semantic_enforcement_evidence(
            policy=policy,
            development=activation.development_evidence,
            evaluation=activation.evaluation_evidence,
        )
        if activation != expected_activation:
            raise SemanticEnforcementIneligibleError(
                "semantic enforcement activation does not match frozen evidence"
            )
        if (
            policy.judge_identity is None
            or policy.generator_identity is None
            or policy.agent_identity is None
            or not policy.domain_scopes
        ):
            raise SemanticEnforcementIneligibleError(
                "enforcement policy identity or scope is unavailable"
            )
        domain_id = getattr(domain, "domain_id", None)
        domain_version = getattr(domain, "domain_version", None)
        if not isinstance(domain_id, str) or not isinstance(domain_version, str):
            raise SemanticEnforcementIneligibleError("enforcement Domain identity is unavailable")
        if (domain_id, domain_version) not in {
            (scope.domain_id, scope.domain_version) for scope in policy.domain_scopes
        }:
            raise SemanticEnforcementIneligibleError(
                "enforcement policy does not cover this Domain version"
            )
        try:
            model_identity = QualityJudgeIdentity(
                provider_id=generator_and_agent_model.provider_id,
                model_id=generator_and_agent_model.model_id,
                model_version=generator_and_agent_model.model_version,
            )
        except (TypeError, ValidationError, ValueError):
            raise SemanticEnforcementIneligibleError(
                "enforcement generator and Agent identity is unavailable"
            ) from None
        if (
            model_identity != policy.generator_identity
            or model_identity != policy.agent_identity
        ):
            raise SemanticEnforcementIneligibleError(
                "enforcement generator or Agent identity differs from activation"
            )
        if (
            configuration.source_scope_id != policy.source_scope_id
            or configuration.task_distribution_scope_id != policy.task_distribution_scope_id
            or configuration.generator_prompt_id != policy.generator_prompt_id
            or configuration.generator_decoding_id != policy.generator_decoding_id
            or configuration.agent_prompt_id != policy.agent_prompt_id
            or configuration.agent_decoding_id != policy.agent_decoding_id
        ):
            raise SemanticEnforcementIneligibleError(
                "enforcement source, task, or model settings differ from activation"
            )
        quality = configuration.shadow_quality
        if (
            quality.mode != "shadow"
            or quality.judge_model_id != policy.judge_identity.model_id
            or quality.rubric_id != policy.rubric_id
            or quality.judge_prompt_id != policy.judge_prompt_id
            or quality.judge_decoding_id != policy.judge_decoding_id
        ):
            raise SemanticEnforcementIneligibleError(
                "enforcement judge settings differ from activation"
            )
        if shadow_judge.model is None or shadow_judge.identity != policy.judge_identity:
            raise SemanticEnforcementIneligibleError(
                "enforcement judge identity is unavailable or differs from activation"
            )
        return _SemanticEnforcementContext(configuration=enforcement)

    def run(
        self,
        configuration: RunConfiguration | Mapping[str, object],
        output_directory: Path,
        *,
        cancellation_signal: CancellationSignal | None = None,
        failure_injector: FailureInjector | object | None = None,
        resume: bool = False,
    ) -> RunResult:
        """Start one bounded run, or delegate an explicit resume to the same lifecycle."""

        if resume:
            return self.resume(
                configuration,
                output_directory,
                cancellation_signal=cancellation_signal,
                failure_injector=failure_injector,
            )
        config = _validated_configuration(configuration)
        run_directory = Path(output_directory)
        run_directory.mkdir(parents=True, exist_ok=True)
        paths = _RunPaths.from_directory(run_directory)
        domain = self._registry.domain(config.domain_id)
        model = self._registry.model(config.model_id)
        shadow_judge = self._shadow_judge_context(config, model)
        semantic_enforcement = self._semantic_enforcement_context(
            configuration=config,
            domain=domain,
            generator_and_agent_model=model,
            shadow_judge=shadow_judge,
        )
        with _RunDirectoryWriterLock(run_directory):
            ledger = PrivateLedger.create(paths.private_ledger_path)
            try:
                domain_run = domain.open_run(config)
                frozen_initial_state = domain_run.freeze_initial_state()
                ledger.record_run_metadata(config, domain_version=domain.domain_version)
                ledger.record_initial_state(frozen_initial_state)
                known_task_capacity = _known_task_capacity(domain_run, config.slot_limit)
                ledger.record_run_status(
                    status="running",
                    known_task_capacity=known_task_capacity,
                )
                _write_frozen_snapshot(paths.frozen_snapshot_path, frozen_initial_state)
                _checkpoint(failure_injector, "after_snapshot_persistence")
                if (
                    config.accepted_target is not None
                    and known_task_capacity is not None
                    and config.accepted_target > known_task_capacity
                ):
                    ledger.record_run_status(
                        status="failed",
                        reason_code="known_task_capacity_insufficient",
                        known_task_capacity=known_task_capacity,
                    )
                    return _finalize_run(
                        paths=paths,
                        ledger=ledger,
                        configuration=config,
                        frozen_initial_state=frozen_initial_state,
                        status="failed",
                        partial_reason="known_task_capacity_insufficient",
                        known_task_capacity=known_task_capacity,
                        shadow_judge=shadow_judge,
                    )
                slots = _bounded_slots(domain_run.slots(config.slot_limit), config.slot_limit)
                ledger.record_allocated_slots(
                    tuple(
                        AllocatedSlotRecord.from_slot(sequence=sequence, slot=slot)
                        for sequence, slot in enumerate(slots, start=1)
                    )
                )
                return _drive_run(
                    configuration=config,
                    domain_version=domain.domain_version,
                    domain_run=domain_run,
                    model=model,
                    ledger=ledger,
                    paths=paths,
                    frozen_initial_state=frozen_initial_state,
                    known_task_capacity=known_task_capacity,
                    cancellation_signal=cancellation_signal,
                    failure_injector=failure_injector,
                    shadow_judge=shadow_judge,
                    semantic_enforcement=semantic_enforcement,
                )
            finally:
                ledger.close()

    def resume(
        self,
        configuration_or_run_directory: RunConfiguration | Mapping[str, object] | Path | str,
        output_directory: RunConfiguration | Mapping[str, object] | Path | str | None = None,
        *,
        cancellation_signal: CancellationSignal | None = None,
        failure_injector: FailureInjector | object | None = None,
    ) -> RunResult:
        """Resume one run only after validating its frozen configuration and input."""

        requested_configuration, run_directory = _resume_arguments(
            configuration_or_run_directory,
            output_directory,
        )
        paths = _RunPaths.from_directory(run_directory)
        with _RunDirectoryWriterLock(run_directory):
            ledger = PrivateLedger.open(paths.private_ledger_path)
            try:
                metadata = ledger.run_metadata()
                configuration = metadata.configuration_model()
                if (
                    requested_configuration is not None
                    and requested_configuration.normalized_public_record()
                    != configuration.normalized_public_record()
                ):
                    raise ValueError("resume configuration does not match the saved run")
                domain = self._registry.domain(configuration.domain_id)
                model = self._registry.model(configuration.model_id)
                shadow_judge = self._shadow_judge_context(configuration, model)
                semantic_enforcement = self._semantic_enforcement_context(
                    configuration=configuration,
                    domain=domain,
                    generator_and_agent_model=model,
                    shadow_judge=shadow_judge,
                )
                if domain.domain_version != metadata.domain_version:
                    raise ValueError("resume Domain version does not match the saved run")
                frozen_initial_state = _read_frozen_snapshot(paths.frozen_snapshot_path, ledger)
                domain_run = _open_run_from_frozen_state(
                    domain,
                    configuration,
                    frozen_initial_state,
                )
                known_task_capacity = _known_task_capacity(domain_run, configuration.slot_limit)
                if (
                    configuration.accepted_target is not None
                    and known_task_capacity is not None
                    and configuration.accepted_target > known_task_capacity
                ):
                    ledger.record_run_status(
                        status="failed",
                        reason_code="known_task_capacity_insufficient",
                        known_task_capacity=known_task_capacity,
                    )
                    return _finalize_run(
                        paths=paths,
                        ledger=ledger,
                        configuration=configuration,
                        frozen_initial_state=frozen_initial_state,
                        status="failed",
                        partial_reason="known_task_capacity_insufficient",
                        known_task_capacity=known_task_capacity,
                        shadow_judge=shadow_judge,
                    )
                prior_status = ledger.run_status()
                if (
                    prior_status.status == "running"
                    and ledger.allocated_slot_count() == 0
                ):
                    slots = _bounded_slots(
                        domain_run.slots(configuration.slot_limit),
                        configuration.slot_limit,
                    )
                    ledger.record_allocated_slots(
                        tuple(
                            AllocatedSlotRecord.from_slot(sequence=sequence, slot=slot)
                            for sequence, slot in enumerate(slots, start=1)
                        )
                    )
                ledger.recover_inflight_work()
                ledger.record_run_status(
                    status="running",
                    known_task_capacity=known_task_capacity,
                )
                return _drive_run(
                    configuration=configuration,
                    domain_version=metadata.domain_version,
                    domain_run=domain_run,
                    model=model,
                    ledger=ledger,
                    paths=paths,
                    frozen_initial_state=frozen_initial_state,
                    known_task_capacity=known_task_capacity,
                    cancellation_signal=cancellation_signal,
                    failure_injector=failure_injector,
                    shadow_judge=shadow_judge,
                    semantic_enforcement=semantic_enforcement,
                )
            finally:
                ledger.close()

    def replay(self, run_directory: Path) -> ReplayResult:
        """Re-execute saved tool calls against the frozen snapshot without model calls."""

        paths = _RunPaths.from_directory(run_directory)
        ledger = PrivateLedger.open(paths.private_ledger_path)
        try:
            metadata = ledger.run_metadata()
            configuration = metadata.configuration_model()
            frozen_initial_state = _read_frozen_snapshot(paths.frozen_snapshot_path, ledger)
            task_cases = {record.sequence: record for record in ledger.task_cases()}
        finally:
            ledger.close()

        domain = self._registry.domain(configuration.domain_id)
        if domain.domain_version != metadata.domain_version:
            raise ValueError("replay Domain version does not match the saved run")
        domain_run = _open_run_from_frozen_state(domain, configuration, frozen_initial_state)
        episodes = _read_public_episodes(paths.demonstrations_path, paths.negatives_path)
        results: list[ReplayEpisodeResult] = []
        for saved_episode in episodes:
            case = task_cases.get(saved_episode.sequence)
            if case is None:
                results.append(
                    ReplayEpisodeResult(
                        episode_id=saved_episode.episode_id,
                        sequence=saved_episode.sequence,
                        status="not_executed",
                        observation_drift=False,
                        assessment_drift=False,
                    )
                )
                continue
            results.append(
                _replay_episode(
                    domain_run=domain_run,
                    saved_episode=saved_episode,
                    case=case,
                    frozen_initial_state=frozen_initial_state,
                )
            )
        report_path = Path(run_directory) / "replay_report.json"
        _write_replay_report(report_path, tuple(results))
        return ReplayResult(
            run_directory=Path(run_directory),
            report_path=report_path,
            episode_results=tuple(results),
        )

    def create_review_queue(
        self,
        run_directory: Path,
        configuration: ReviewQueueConfiguration | Mapping[str, object],
    ) -> ReviewQueueResult:
        """Freeze one blind diagnostic or held-out cohort for a completed run."""

        queue_configuration = (
            configuration
            if isinstance(configuration, ReviewQueueConfiguration)
            else ReviewQueueConfiguration.model_validate(configuration)
        )
        paths = _RunPaths.from_directory(Path(run_directory))
        with _RunDirectoryWriterLock(paths.run_directory):
            ledger = PrivateLedger.open(paths.private_ledger_path)
            try:
                metadata = ledger.run_metadata()
                status = ledger.run_status()
                if status.status != "completed":
                    raise ValueError("review queues require a completed run directory")
                cohorts = _read_review_cohorts(paths.review_cohorts_path)
                if any(
                    cohort.cohort_id == queue_configuration.cohort_id
                    for cohort in cohorts
                ):
                    raise ReviewLabelImportError("review cohort id is already frozen")
                episodes = tuple(record.episode for record in ledger.terminal_outcomes())
                cohort, _ = build_review_cohort(
                    configuration=queue_configuration,
                    episodes=episodes,
                    judgments=ledger.quality_judgments(),
                    existing_episode_ids=frozenset(
                        episode_id for existing in cohorts for episode_id in existing.episode_ids
                    ),
                )
                updated_cohorts = tuple((*cohorts, cohort))
                _write_review_cohorts(paths.review_cohorts_path, updated_cohorts)
                _write_blind_review_queue(
                    paths.review_queue_path,
                    updated_cohorts,
                    episodes,
                )
                _refresh_quality_report_and_manifest(
                    paths=paths,
                    ledger=ledger,
                    configuration=metadata.configuration_model(),
                    status=status,
                )
                return ReviewQueueResult(
                    run_directory=paths.run_directory,
                    cohort=cohort,
                    queue_path=paths.review_queue_path,
                    cohorts_path=paths.review_cohorts_path,
                    quality_report_path=paths.quality_report_path,
                )
            finally:
                ledger.close()

    def import_review_labels(
        self,
        run_directory: Path,
        labels: Iterable[Mapping[str, object]] | Path | str,
    ) -> ReviewLabelImportResult:
        """Import only direct-human labels bound to frozen blind-review members."""

        paths = _RunPaths.from_directory(Path(run_directory))
        submitted_labels = _parse_submitted_human_labels(labels)
        with _RunDirectoryWriterLock(paths.run_directory):
            ledger = PrivateLedger.open(paths.private_ledger_path)
            try:
                metadata = ledger.run_metadata()
                status = ledger.run_status()
                if status.status != "completed":
                    raise ValueError("review labels require a completed run directory")
                cohorts = _read_review_cohorts(paths.review_cohorts_path)
                if not cohorts:
                    raise ReviewLabelImportError("review labels require a frozen review cohort")
                existing_labels = _read_human_review_labels(paths.human_review_labels_path)
                episodes = tuple(record.episode for record in ledger.terminal_outcomes())
                _validate_submitted_human_labels(
                    submitted_labels,
                    existing_labels=existing_labels,
                    cohorts=cohorts,
                    episodes=episodes,
                )
                all_labels = tuple((*existing_labels, *submitted_labels))
                _write_human_review_labels(paths.human_review_labels_path, all_labels)
                summary = summarize_human_review(cohorts, all_labels)
                if summary.status == "not_started":
                    raise AssertionError("frozen cohorts must have an import status")
                _write_review_label_import_report(
                    paths.review_label_import_report_path,
                    cohorts=cohorts,
                    labels=all_labels,
                )
                _refresh_quality_report_and_manifest(
                    paths=paths,
                    ledger=ledger,
                    configuration=metadata.configuration_model(),
                    status=status,
                )
                return ReviewLabelImportResult(
                    run_directory=paths.run_directory,
                    status=summary.status,
                    complete=summary.complete,
                    labels_path=paths.human_review_labels_path,
                    report_path=paths.review_label_import_report_path,
                    quality_report_path=paths.quality_report_path,
                    human_approved_episode_ids=summary.human_approved_episode_ids,
                )
            finally:
                ledger.close()

    def evaluate_semantic_enforcement(
        self,
        *,
        policy: SemanticEnforcementPolicy | Mapping[str, object],
        development_run_directories: Sequence[Path],
        development_campaign_id: str,
        evaluation_run_directories: Sequence[Path],
        evaluation_campaign_id: str,
    ) -> SemanticEnforcementEligibilityReport:
        """Evaluate existing frozen cohorts through the established label-import seam."""

        resolved_policy = (
            policy
            if isinstance(policy, SemanticEnforcementPolicy)
            else SemanticEnforcementPolicy.model_validate(policy)
        )
        development = _calibration_campaign_from_runs(
            run_directories=development_run_directories,
            campaign_id=development_campaign_id,
            purpose="diagnostic-development",
        )
        evaluation = _calibration_campaign_from_runs(
            run_directories=evaluation_run_directories,
            campaign_id=evaluation_campaign_id,
            purpose="held-out-evaluation",
        )
        return evaluate_semantic_enforcement_evidence(
            policy=resolved_policy,
            development=development,
            evaluation=evaluation,
        )


@dataclass(frozen=True)
class _RunPaths:
    run_directory: Path
    demonstrations_path: Path
    negatives_path: Path
    provider_usage_path: Path
    run_report_path: Path
    shadow_judgments_path: Path
    quality_report_path: Path
    review_queue_path: Path
    review_cohorts_path: Path
    human_review_labels_path: Path
    review_label_import_report_path: Path
    manifest_path: Path
    private_ledger_path: Path
    frozen_snapshot_path: Path

    @classmethod
    def from_directory(cls, run_directory: Path) -> "_RunPaths":
        directory = Path(run_directory)
        private_directory = directory / ".private"
        return cls(
            run_directory=directory,
            demonstrations_path=directory / "demonstrations.jsonl",
            negatives_path=directory / "negatives.jsonl",
            provider_usage_path=directory / "provider_usage.json",
            run_report_path=directory / "run_report.json",
            shadow_judgments_path=directory / "shadow_quality_judgments.jsonl",
            quality_report_path=directory / "quality_report.json",
            review_queue_path=directory / "blind_review_queue.jsonl",
            review_cohorts_path=directory / "review_cohorts.json",
            human_review_labels_path=directory / "human_review_labels.jsonl",
            review_label_import_report_path=directory / "review_label_import_report.json",
            manifest_path=directory / "manifest.json",
            private_ledger_path=private_directory / "ledger.sqlite3",
            frozen_snapshot_path=private_directory / "frozen_state.json",
        )


def _calibration_campaign_from_runs(
    *,
    run_directories: Sequence[Path],
    campaign_id: str,
    purpose: Literal["diagnostic-development", "held-out-evaluation"],
) -> CalibrationCampaignEvidence:
    """Project existing private-ledger facts into calibration evidence without new labels."""

    cohorts: list[CalibrationCohortEvidence] = []
    episodes: list[CalibrationEpisodeEvidence] = []
    unavailable_source_count = 0
    seen_run_directories: set[Path] = set()
    for supplied_directory in run_directories:
        directory = Path(supplied_directory).resolve()
        if directory in seen_run_directories:
            continue
        seen_run_directories.add(directory)
        try:
            paths = _RunPaths.from_directory(directory)
            ledger = PrivateLedger.open(paths.private_ledger_path)
            try:
                metadata = ledger.run_metadata()
                configuration = metadata.configuration_model()
                if ledger.run_status().status != "completed":
                    unavailable_source_count += 1
                    continue
                stored_cohorts = _read_review_cohorts(paths.review_cohorts_path)
                matching_cohorts = tuple(
                    cohort
                    for cohort in stored_cohorts
                    if cohort.purpose == purpose and cohort.campaign_id == campaign_id
                )
                if not matching_cohorts:
                    unavailable_source_count += 1
                    continue
                terminal_records = ledger.terminal_outcomes()
                terminals_by_episode_id = {
                    terminal.episode.episode_id: terminal for terminal in terminal_records
                }
                task_cases = {case.sequence: case for case in ledger.task_cases()}
                judgments_by_episode_id = {
                    judgment.episode_id: judgment for judgment in ledger.quality_judgments()
                }
                labels_by_key = {
                    (label.cohort_id, label.episode_id): label
                    for label in _read_human_review_labels(paths.human_review_labels_path)
                }
                memberships_by_episode_id = {
                    episode_id: cohort
                    for cohort in matching_cohorts
                    for episode_id in cohort.episode_ids
                }
                evidence_ids = {
                    episode_id: _calibration_evidence_id(configuration.run_id, episode_id)
                    for episode_id in terminals_by_episode_id
                }
                for cohort in matching_cohorts:
                    cohorts.append(
                        CalibrationCohortEvidence(
                            cohort_id=_calibration_cohort_id(
                                configuration.run_id,
                                cohort.cohort_id,
                            ),
                            member_evidence_ids=tuple(
                                evidence_ids.get(
                                    episode_id,
                                    _calibration_evidence_id(
                                        configuration.run_id,
                                        episode_id,
                                    ),
                                )
                                for episode_id in cohort.episode_ids
                            ),
                            selection_method=cohort.selection_method,
                            policy_id=cohort.quality_policy_id,
                            policy_fingerprint=cohort.quality_policy_fingerprint,
                            stratified_pass_stratum_count=(
                                cohort.stratified_pass_stratum_count
                            ),
                        )
                    )
                for terminal in terminal_records:
                    episode = terminal.episode
                    cohort = memberships_by_episode_id.get(episode.episode_id)
                    label = (
                        labels_by_key.get((cohort.cohort_id, episode.episode_id))
                        if cohort is not None
                        else None
                    )
                    judgment = judgments_by_episode_id.get(episode.episode_id)
                    semantic_key = (
                        task_cases[episode.sequence].semantic_key
                        if episode.sequence in task_cases
                        else None
                    )
                    episodes.append(
                        CalibrationEpisodeEvidence(
                            evidence_id=evidence_ids[episode.episode_id],
                            episode_id=episode.episode_id,
                            domain_id=episode.domain_id,
                            domain_version=episode.domain_version,
                            deterministic_eligible=episode.admission.gates.passed,
                            semantic_task_group=(
                                _canonical_calibration_group(
                                    "semantic-task",
                                    episode.domain_id,
                                    episode.domain_version,
                                    semantic_key,
                                )
                                if semantic_key is not None
                                else None
                            ),
                            grounding_group=(
                                _canonical_calibration_group(
                                    "grounding",
                                    episode.domain_id,
                                    episode.domain_version,
                                    semantic_key,
                                )
                                if semantic_key is not None
                                else None
                            ),
                            task_type=(
                                episode.verification.review_stratification.task_type
                                if episode.verification is not None
                                and episode.verification.review_stratification is not None
                                else None
                            ),
                            difficulty=(
                                episode.verification.review_stratification.difficulty
                                if episode.verification is not None
                                and episode.verification.review_stratification is not None
                                else None
                            ),
                            structural_family=(
                                episode.verification.structural_key
                                if episode.verification is not None
                                else None
                            ),
                            judge_verdict=(
                                judgment.verdict if judgment is not None else "unavailable"
                            ),
                            judge_identity=(
                                judgment.judge_identity if judgment is not None else None
                            ),
                            human_verdict=(
                                label.aggregate_verdict if label is not None else None
                            ),
                            human_critical_safety_failure=(
                                _human_label_has_critical_safety_failure(label)
                                if label is not None
                                else False
                            ),
                            generator_identity=_lineage_identity(
                                episode,
                                "task_generation",
                            ),
                            agent_identity=_lineage_identity(episode, "agent"),
                            source_scope_id=configuration.source_scope_id,
                            task_distribution_scope_id=(
                                configuration.task_distribution_scope_id
                            ),
                            generator_prompt_id=configuration.generator_prompt_id,
                            generator_decoding_id=configuration.generator_decoding_id,
                            agent_prompt_id=configuration.agent_prompt_id,
                            agent_decoding_id=configuration.agent_decoding_id,
                            judge_prompt_id=configuration.shadow_quality.judge_prompt_id,
                            judge_decoding_id=(
                                configuration.shadow_quality.judge_decoding_id
                            ),
                        )
                    )
            finally:
                ledger.close()
        except (OSError, LookupError, ReviewLabelImportError, ValidationError, ValueError):
            unavailable_source_count += 1
    return CalibrationCampaignEvidence(
        campaign_id=campaign_id,
        purpose=purpose,
        cohorts=tuple(cohorts),
        episodes=tuple(episodes),
        unavailable_source_count=unavailable_source_count,
    )


def _calibration_evidence_id(run_id: str, episode_id: str) -> str:
    return _canonical_calibration_group("episode", run_id, episode_id)


def _calibration_cohort_id(run_id: str, cohort_id: str) -> str:
    return _canonical_calibration_group("cohort", run_id, cohort_id)


def _canonical_calibration_group(kind: str, *parts: str) -> str:
    payload = json.dumps((kind, *parts), separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _lineage_identity(
    episode: PublicEpisode,
    role: Literal["task_generation", "agent"],
) -> QualityJudgeIdentity | None:
    lineage = next((item for item in episode.lineage.roles if item.role == role), None)
    if lineage is None:
        return None
    try:
        return QualityJudgeIdentity(
            provider_id=lineage.provider_id,
            model_id=lineage.model_id,
            model_version=lineage.model_version,
        )
    except (TypeError, ValidationError, ValueError):
        return None


def _human_label_has_critical_safety_failure(label: HumanReviewLabel) -> bool:
    return any(
        dimension.dimension == "safety"
        and dimension.verdict == "fail"
        and "critical_safety_failure" in dimension.reason_codes
        for dimension in label.dimensions
    )


def _read_review_cohorts(path: Path) -> tuple[ReviewCohort, ...]:
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "agent_review_cohorts_v1":
            raise ValueError
        records = payload.get("cohorts")
        if not isinstance(records, list):
            raise ValueError
        cohorts = tuple(ReviewCohort.model_validate(record) for record in records)
    except (OSError, TypeError, ValidationError, ValueError):
        raise ReviewLabelImportError("frozen review cohort metadata is invalid") from None
    if len({cohort.cohort_id for cohort in cohorts}) != len(cohorts):
        raise ReviewLabelImportError("frozen review cohort ids must be unique")
    memberships = [episode_id for cohort in cohorts for episode_id in cohort.episode_ids]
    if len(set(memberships)) != len(memberships):
        raise ReviewLabelImportError("frozen review cohorts must not overlap")
    return cohorts


def _write_review_cohorts(path: Path, cohorts: Sequence[ReviewCohort]) -> None:
    payload = {
        "schema_version": "agent_review_cohorts_v1",
        "cohorts": [cohort.model_dump(mode="json") for cohort in cohorts],
    }
    _atomic_write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _write_blind_review_queue(
    path: Path,
    cohorts: Sequence[ReviewCohort],
    episodes: Sequence[PublicEpisode],
) -> None:
    items = [
        item
        for cohort in cohorts
        for item in blind_queue_items_for_cohort(cohort, episodes)
    ]
    lines = (
        json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        + "\n"
        for item in items
    )
    _atomic_write_text(path, "".join(lines))


def _read_human_review_labels(path: Path) -> tuple[HumanReviewLabel, ...]:
    if not path.exists():
        return ()
    try:
        labels = tuple(
            HumanReviewLabel.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        )
    except (OSError, ValidationError, ValueError):
        raise ReviewLabelImportError("stored human review labels are invalid") from None
    keys = {(label.cohort_id, label.episode_id) for label in labels}
    if len(keys) != len(labels):
        raise ReviewLabelImportError("stored human review labels are duplicated")
    return labels


def _parse_submitted_human_labels(
    source: Iterable[Mapping[str, object]] | Path | str,
) -> tuple[HumanReviewLabel, ...]:
    try:
        if isinstance(source, (Path, str)):
            path = Path(source)
            values: Iterable[object] = (
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line
            )
        else:
            values = source
        labels = tuple(HumanReviewLabel.model_validate(value) for value in values)
    except (OSError, TypeError, ValidationError, ValueError, json.JSONDecodeError):
        raise ReviewLabelImportError("submitted human review labels are malformed or unsafe") from None
    keys = {(label.cohort_id, label.episode_id) for label in labels}
    if len(keys) != len(labels):
        raise ReviewLabelImportError("submitted human review labels are duplicated")
    return labels


def _validate_submitted_human_labels(
    submitted: Sequence[HumanReviewLabel],
    *,
    existing_labels: Sequence[HumanReviewLabel],
    cohorts: Sequence[ReviewCohort],
    episodes: Sequence[PublicEpisode],
) -> None:
    cohorts_by_id = {cohort.cohort_id: cohort for cohort in cohorts}
    episodes_by_id = {episode.episode_id: episode for episode in episodes}
    existing_keys = {(label.cohort_id, label.episode_id) for label in existing_labels}
    for label in submitted:
        cohort = cohorts_by_id.get(label.cohort_id)
        if cohort is None or cohort.purpose != label.purpose:
            raise ReviewLabelImportError("human review label has a foreign cohort or purpose")
        if label.episode_id not in cohort.episode_ids:
            raise ReviewLabelImportError("human review label targets an Episode outside its queue")
        key = (label.cohort_id, label.episode_id)
        if key in existing_keys:
            raise ReviewLabelImportError("human review label duplicates an imported label")
        episode = episodes_by_id.get(label.episode_id)
        if episode is None:
            raise ReviewLabelImportError("human review label targets an unknown Episode")
        try:
            QualityJudgeResponse(dimensions=label.dimensions).validate_event_references(
                len(episode.events)
            )
        except (ValidationError, ValueError):
            raise ReviewLabelImportError("human review evidence references are invalid") from None


def _write_human_review_labels(path: Path, labels: Sequence[HumanReviewLabel]) -> None:
    ordered = sorted(labels, key=lambda label: (label.cohort_id, label.episode_id))
    lines = (
        json.dumps(label.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        + "\n"
        for label in ordered
    )
    _atomic_write_text(path, "".join(lines))


def _write_review_label_import_report(
    path: Path,
    *,
    cohorts: Sequence[ReviewCohort],
    labels: Sequence[HumanReviewLabel],
) -> None:
    summary = summarize_human_review(cohorts, labels)
    payload = {
        "schema_version": "agent_review_label_import_report_v1",
        "status": summary.status,
        "complete": summary.complete,
        "cohorts": [
            {
                "cohort_id": cohort.cohort_id,
                "purpose": cohort.purpose,
                "membership_hash": cohort.membership_hash,
                "member_count": len(cohort.episode_ids),
                "selection_method": cohort.selection_method,
                "stratified_pass_stratum_count": cohort.stratified_pass_stratum_count,
                "campaign_id": cohort.campaign_id,
                "quality_policy_id": cohort.quality_policy_id,
                "quality_policy_fingerprint": cohort.quality_policy_fingerprint,
                "imported_label_count": summary.cohort_imported_label_counts.get(
                    cohort.cohort_id,
                    0,
                ),
                "missing_label_count": len(cohort.episode_ids)
                - summary.cohort_imported_label_counts.get(cohort.cohort_id, 0),
            }
            for cohort in cohorts
        ],
        "human_approved_episode_ids": list(summary.human_approved_episode_ids),
    }
    _atomic_write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _refresh_quality_report_and_manifest(
    *,
    paths: _RunPaths,
    ledger: PrivateLedger,
    configuration: RunConfiguration,
    status: object,
) -> None:
    run_status = getattr(status, "status")
    partial_reason = getattr(status, "reason_code")
    known_task_capacity = getattr(status, "known_task_capacity")
    if not isinstance(run_status, str):
        raise ValueError("run status is invalid")
    if partial_reason is not None and not isinstance(partial_reason, str):
        raise ValueError("run partial reason is invalid")
    if known_task_capacity is not None and not isinstance(known_task_capacity, int):
        raise ValueError("run capacity is invalid")
    episodes = tuple(record.episode for record in ledger.terminal_outcomes())
    requests = ledger.provider_requests()
    cohorts = _read_review_cohorts(paths.review_cohorts_path)
    human_labels = _read_human_review_labels(paths.human_review_labels_path)
    _write_quality_report(
        paths=paths,
        configuration=configuration,
        status=run_status,
        partial_reason=partial_reason,
        known_task_capacity=known_task_capacity,
        allocated_slot_count=ledger.allocated_slot_count(),
        episodes=episodes,
        judgments=ledger.quality_judgments(),
        requests=requests,
        cohorts=cohorts,
        human_labels=human_labels,
    )
    _write_public_manifest(
        paths=paths,
        configuration=configuration,
        source_fingerprint=ledger.initial_state().fingerprint,
    )


def _resume_arguments(
    configuration_or_run_directory: RunConfiguration | Mapping[str, object] | Path | str,
    output_directory: RunConfiguration | Mapping[str, object] | Path | str | None,
) -> tuple[RunConfiguration | None, Path]:
    if isinstance(configuration_or_run_directory, (Path, str)):
        run_directory = Path(configuration_or_run_directory)
        if output_directory is None:
            return None, run_directory
        if isinstance(output_directory, RunConfiguration) or isinstance(output_directory, Mapping):
            return _validated_configuration(output_directory), run_directory
        raise TypeError("resume run directory can only be paired with a configuration")
    if output_directory is None or isinstance(output_directory, (RunConfiguration, Mapping)):
        raise TypeError("resume configuration requires an output directory")
    return _validated_configuration(configuration_or_run_directory), Path(output_directory)


def _write_frozen_snapshot(path: Path, state: FrozenInitialState) -> None:
    record = FrozenStateRecord.from_initial_state(state)
    _atomic_write_text(path, record.model_dump_json(indent=2) + "\n")


def _read_frozen_snapshot(path: Path, ledger: PrivateLedger) -> FrozenInitialState:
    try:
        snapshot_record = FrozenStateRecord.model_validate_json(path.read_text(encoding="utf-8"))
        snapshot = snapshot_record.to_initial_state()
        if snapshot_record != ledger.initial_state_record():
            raise ValueError("snapshot does not match the operational ledger")
        return snapshot
    except Exception:  # noqa: BLE001 - no mutable source may be consulted on failure.
        raise FrozenInputError("frozen input snapshot is missing or corrupt") from None


def _open_run_from_frozen_state(
    domain: object,
    configuration: RunConfiguration,
    frozen_initial_state: FrozenInitialState,
) -> DomainRun:
    restore = getattr(domain, "open_run_from_frozen_state", None)
    if callable(restore):
        return restore(configuration, frozen_initial_state)
    run = domain.open_run(configuration)
    try:
        current_state = run.freeze_initial_state()
    except Exception:  # noqa: BLE001 - non-resumable adapters must fail closed on resume.
        raise FrozenInputError("Domain cannot verify the saved frozen input") from None
    if current_state != frozen_initial_state:
        raise FrozenInputError("Domain cannot reconstruct the saved frozen input")
    return run


def _known_task_capacity(domain_run: DomainRun, attempt_limit: int) -> int | None:
    try:
        capacity = getattr(domain_run, "known_task_capacity", None)
    except Exception:  # noqa: BLE001 - capability disclosure is optional.
        capacity = None
    if callable(capacity):
        try:
            capacity = capacity()
        except Exception:  # noqa: BLE001 - an unavailable declaration remains unknown.
            capacity = None
    if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity >= 0:
        return capacity
    slot_capacity = getattr(domain_run, "slot_capacity", None)
    if callable(slot_capacity):
        try:
            declared = slot_capacity(attempt_limit)
            capacity = getattr(declared, "known_task_capacity", None)
        except Exception:  # noqa: BLE001 - an unavailable declaration remains unknown.
            capacity = None
        if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity >= 0:
            return capacity
    return None


def _is_cancelled(signal: CancellationSignal | None) -> bool:
    return signal is not None and signal.is_set()


def _checkpoint(failure_injector: FailureInjector | object | None, phase: str) -> None:
    if failure_injector is None:
        return
    checkpoint = getattr(failure_injector, "checkpoint", None)
    if callable(checkpoint):
        checkpoint(phase)
        return
    if callable(failure_injector):
        failure_injector(phase)
        return
    raise TypeError("failure_injector must be callable or expose checkpoint(phase)")


def _drive_run(
    *,
    configuration: RunConfiguration,
    domain_version: str,
    domain_run: DomainRun,
    model: JsonModelAdapter,
    ledger: PrivateLedger,
    paths: _RunPaths,
    frozen_initial_state: FrozenInitialState,
    known_task_capacity: int | None,
    cancellation_signal: CancellationSignal | None,
    failure_injector: FailureInjector | object | None,
    shadow_judge: _ShadowJudgeContext,
    semantic_enforcement: _SemanticEnforcementContext | None,
) -> RunResult:
    """Dispatch only bounded work and leave incomplete ownership resumable."""

    owner_prefix = f"run-{uuid.uuid4().hex}"
    active_semantic_keys: set[str] = set()
    admitted_semantic_keys = set(ledger.admitted_semantic_keys())
    _, accepted_count = ledger.terminal_outcome_summary()
    futures: dict[Future[_EpisodeAttemptResult], _InFlightEpisode] = {}
    stop_reason: str | None = None

    def context_for(sequence: int) -> _EpisodeContext:
        return _EpisodeContext(
            configuration=configuration,
            domain_version=domain_version,
            sequence=sequence,
        )

    def commit_terminal(episode: PublicEpisode, semantic_key: str | None) -> None:
        nonlocal accepted_count
        committed_episode = episode
        if (
            semantic_key is not None
            and episode.admission.status == "admitted"
            and semantic_key in admitted_semantic_keys
        ):
            committed_episode = _pre_execution_negative(
                context=context_for(episode.sequence),
                task=episode.task,
                reason_code="duplicate_semantic_task",
                lineage=_model_lineage(
                    model,
                    ledger.provider_requests_for_sequence(episode.sequence),
                ),
            )
        judgment: QualityJudgment | None = None
        if semantic_enforcement is not None:
            judgment = _evaluate_quality_judgment(
                ledger=ledger,
                configuration=configuration,
                episode=committed_episode,
                shadow_judge=shadow_judge,
                allow_provider_calls=True,
            )
            committed_episode = _apply_semantic_enforcement(
                episode=committed_episode,
                policy_id=semantic_enforcement.configuration.policy.policy_id,
                judgment=judgment,
            )
        _checkpoint(failure_injector, "before_terminal_commit")
        ledger.commit_terminal_outcome(
            sequence=committed_episode.sequence,
            episode=committed_episode,
            semantic_key=semantic_key,
        )
        _checkpoint(failure_injector, "after_terminal_commit")
        if judgment is not None:
            ledger.record_quality_judgment(judgment)
        if committed_episode.admission.status == "admitted":
            accepted_count += 1
            assert semantic_key is not None
            admitted_semantic_keys.add(semantic_key)

    def commit_pre_execution(
        *,
        sequence: int,
        task: PublicTask,
        reason_code: str,
        semantic_key: str | None = None,
        records: tuple[ProviderRequestRecord, ...] | None = None,
    ) -> None:
        commit_terminal(
            _pre_execution_negative(
                context=context_for(sequence),
                task=task,
                reason_code=reason_code,
                lineage=_model_lineage(
                    model,
                    records if records is not None else ledger.provider_requests_for_sequence(sequence),
                ),
            ),
            semantic_key,
        )

    def generate_pending_batch() -> str | None:
        if _is_cancelled(cancellation_signal):
            return "operator_cancelled"
        pending = ledger.work_items_with_status(
            "pending",
            limit=configuration.generation_batch_size,
        )
        if not pending:
            return None
        if not ledger.has_remaining_request_budget(
            role="task_generation",
            role_limit=configuration.generation_request_limit,
            total_limit=configuration.total_request_limit,
        ):
            return "provider_request_budget_exhausted"
        batch = tuple(ledger.allocated_slot(item.sequence) for item in pending)
        owner_id = f"{owner_prefix}:generation:{batch[0].sequence}-{batch[-1].sequence}"
        claimed: list[WorkItemRecord] = []
        for item in pending:
            if _is_cancelled(cancellation_signal):
                for claimed_item in claimed:
                    ledger.return_work_to_ready(
                        sequence=claimed_item.sequence,
                        owner_id=owner_id,
                    )
                return "operator_cancelled"
            ledger.claim_work(
                sequence=item.sequence,
                owner_id=owner_id,
                status="generating",
            )
            claimed.append(item)
        if _is_cancelled(cancellation_signal):
            for claimed_item in claimed:
                ledger.return_work_to_ready(
                    sequence=claimed_item.sequence,
                    owner_id=owner_id,
                )
            return "operator_cancelled"
        generation = _call_model(
            ledger=ledger,
            model=model,
            configuration=configuration,
            request=TaskGenerationRequest(
                slots=tuple(record.to_slot() for record in batch),
                timeout_seconds=configuration.timeout_seconds,
                max_response_bytes=configuration.max_response_bytes,
                max_output_tokens=configuration.max_output_tokens,
            ),
            logical_request_id=(
                f"task_generation:{batch[0].sequence:04d}-{batch[-1].sequence:04d}"
            ),
            sequence=None,
            related_sequences=tuple(record.sequence for record in batch),
            request_kind="initial",
            failure_injector=failure_injector,
            cancellation_signal=cancellation_signal,
        )
        if generation.response is None:
            if generation.error_code in {
                "operator_cancelled",
                "provider_request_budget_exhausted",
            }:
                for item in pending:
                    ledger.return_work_to_ready(sequence=item.sequence, owner_id=owner_id)
                return generation.error_code
            for record in batch:
                commit_pre_execution(
                    sequence=record.sequence,
                    task=_fallback_public_task(record.to_slot()),
                    reason_code=generation.error_code or "generation_failed",
                    records=generation.records,
                )
            return None
        proposals, generation_reason = _mapped_generation_proposals(generation.response, batch)
        if proposals is None:
            assert generation_reason is not None
            for record in batch:
                commit_pre_execution(
                    sequence=record.sequence,
                    task=_fallback_public_task(record.to_slot()),
                    reason_code=generation_reason,
                    records=generation.records,
                )
            return None
        for record in batch:
            context = context_for(record.sequence)
            try:
                compilation = domain_run.compile(
                    record.to_slot(),
                    TaskProposal(content=proposals[record.slot_id]),
                )
            except Exception:  # noqa: BLE001 - Domain failures become bounded negatives.
                commit_pre_execution(
                    sequence=record.sequence,
                    task=_fallback_public_task(record.to_slot()),
                    reason_code="domain_compilation_failure",
                    records=generation.records,
                )
                continue
            if isinstance(compilation, CompilationRejection):
                commit_terminal(
                    _compilation_negative(
                        context=context,
                        rejection=compilation,
                        lineage=_model_lineage(model, generation.records),
                    ),
                    None,
                )
                continue
            if not isinstance(compilation, CompiledTask):
                commit_pre_execution(
                    sequence=record.sequence,
                    task=_fallback_public_task(record.to_slot()),
                    reason_code="domain_compilation_failure",
                    records=generation.records,
                )
                continue
            _checkpoint(failure_injector, "before_task_case_persistence")
            ledger.record_task_case(
                sequence=record.sequence,
                slot_id=record.slot_id,
                task=compilation,
            )
            _checkpoint(failure_injector, "after_task_case_persistence")
        return None

    def dispatch_ready_work(executor: ThreadPoolExecutor) -> str | None:
        remaining_target = (
            configuration.max_concurrency
            if configuration.accepted_target is None
            else max(0, configuration.accepted_target - accepted_count - len(futures))
        )
        available_workers = min(
            configuration.max_concurrency - len(futures),
            remaining_target,
        )
        if available_workers <= 0:
            return None
        probe_size = max(configuration.max_concurrency * 16, 64)
        for work in ledger.work_items_with_status("compiled", limit=probe_size):
            if _is_cancelled(cancellation_signal):
                return "operator_cancelled"
            if available_workers <= 0:
                break
            case = ledger.task_case(work.sequence)
            if case is None:
                commit_pre_execution(
                    sequence=work.sequence,
                    task=_fallback_public_task(ledger.allocated_slot(work.sequence).to_slot()),
                    reason_code="task_case_missing",
                )
                continue
            if case.semantic_key in admitted_semantic_keys:
                commit_pre_execution(
                    sequence=work.sequence,
                    task=case.public_task,
                    reason_code="duplicate_semantic_task",
                    semantic_key=case.semantic_key,
                )
                continue
            if case.semantic_key in active_semantic_keys:
                continue
            if not ledger.has_remaining_request_budget(
                role="agent",
                role_limit=configuration.agent_request_limit,
                total_limit=configuration.total_request_limit,
            ):
                return "provider_request_budget_exhausted"
            try:
                task = domain_run.restore_task_case(
                    public_task=case.public_task,
                    semantic_key=case.semantic_key,
                    private_case_bytes=case.private_case_bytes(),
                )
            except Exception:  # noqa: BLE001 - corrupted private cases must not dispatch.
                commit_pre_execution(
                    sequence=work.sequence,
                    task=case.public_task,
                    reason_code="task_case_restore_failure",
                    semantic_key=case.semantic_key,
                )
                continue
            if _is_cancelled(cancellation_signal):
                return "operator_cancelled"
            owner_id = f"{owner_prefix}:episode:{work.sequence}"
            ledger.claim_work(sequence=work.sequence, owner_id=owner_id, status="running")
            if _is_cancelled(cancellation_signal):
                ledger.return_work_to_ready(sequence=work.sequence, owner_id=owner_id)
                return "operator_cancelled"
            future = executor.submit(
                _run_agent_episode,
                domain_run=domain_run,
                task=task,
                frozen_initial_state=frozen_initial_state,
                context=context_for(work.sequence),
                model=model,
                ledger=ledger,
                generation_records=ledger.provider_requests_for_sequence(work.sequence),
                cancellation_signal=cancellation_signal,
                failure_injector=failure_injector,
            )
            futures[future] = _InFlightEpisode(
                sequence=work.sequence,
                semantic_key=case.semantic_key,
                owner_id=owner_id,
            )
            active_semantic_keys.add(case.semantic_key)
            available_workers -= 1
        return None

    def collect_completed(done: set[Future[_EpisodeAttemptResult]]) -> None:
        nonlocal stop_reason
        for future in done:
            in_flight = futures.pop(future)
            active_semantic_keys.discard(in_flight.semantic_key)
            result = future.result()
            if result.partial_reason is not None:
                ledger.return_work_to_ready(
                    sequence=in_flight.sequence,
                    owner_id=in_flight.owner_id,
                )
                if stop_reason is None:
                    stop_reason = result.partial_reason
                continue
            assert result.episode is not None
            commit_terminal(result.episode, in_flight.semantic_key)

    with ThreadPoolExecutor(max_workers=configuration.max_concurrency) as executor:
        while True:
            completed_now = {future for future in futures if future.done()}
            if completed_now:
                collect_completed(completed_now)
                continue
            if stop_reason is None and _is_cancelled(cancellation_signal):
                stop_reason = "operator_cancelled"
            if (
                stop_reason is None
                and configuration.accepted_target is not None
                and accepted_count >= configuration.accepted_target
            ):
                stop_reason = "accepted_target_reached"
            if stop_reason is not None:
                if futures:
                    completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                    collect_completed(completed)
                    continue
                break
            dispatch_reason = dispatch_ready_work(executor)
            if dispatch_reason is not None:
                stop_reason = dispatch_reason
                continue
            if futures:
                completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                collect_completed(completed)
                continue
            if ledger.work_items_with_status("pending", limit=1):
                generation_reason = generate_pending_batch()
                if generation_reason is not None:
                    stop_reason = generation_reason
                continue
            if ledger.work_items_with_status("compiled", limit=1):
                stop_reason = "scheduler_no_progress"
            break

    if _is_cancelled(cancellation_signal):
        status: Literal["completed", "partial", "cancelled", "failed"] = "cancelled"
        partial_reason: str | None = "operator_cancelled"
    elif configuration.accepted_target is not None and accepted_count >= configuration.accepted_target:
        status = "completed"
        partial_reason = None
    elif stop_reason == "provider_request_budget_exhausted":
        status = "partial"
        partial_reason = stop_reason
    elif stop_reason == "scheduler_no_progress":
        status = "partial"
        partial_reason = stop_reason
    elif configuration.accepted_target is not None:
        status = "partial"
        partial_reason = _incomplete_target_reason(
            configuration=configuration,
            ledger=ledger,
            known_task_capacity=known_task_capacity,
        )
    else:
        status = "completed"
        partial_reason = None
    ledger.record_run_status(
        status=status,
        reason_code=partial_reason,
        known_task_capacity=known_task_capacity,
    )
    return _finalize_run(
        paths=paths,
        ledger=ledger,
        configuration=configuration,
        frozen_initial_state=frozen_initial_state,
        status=status,
        partial_reason=partial_reason,
        known_task_capacity=known_task_capacity,
        shadow_judge=shadow_judge,
    )


def _incomplete_target_reason(
    *,
    configuration: RunConfiguration,
    ledger: PrivateLedger,
    known_task_capacity: int | None,
) -> str:
    allocated_count = ledger.allocated_slot_count()
    if allocated_count < configuration.slot_limit:
        return "domain_slot_exhausted"
    if known_task_capacity is None:
        return "unknown_task_capacity"
    return "bounded_replacement_exhausted"


def _finalize_run(
    *,
    paths: _RunPaths,
    ledger: PrivateLedger,
    configuration: RunConfiguration,
    frozen_initial_state: FrozenInitialState,
    status: Literal["completed", "partial", "cancelled", "failed"],
    partial_reason: str | None,
    known_task_capacity: int | None,
    shadow_judge: _ShadowJudgeContext,
) -> RunResult:
    terminal_outcome_count, accepted_count = ledger.terminal_outcome_summary()
    allocated_slot_count = ledger.allocated_slot_count()
    _write_terminal_collections(paths, ledger.iter_terminal_outcomes())
    _write_shadow_quality_judgments(
        paths=paths,
        ledger=ledger,
        configuration=configuration,
        shadow_judge=shadow_judge,
        allow_provider_calls=status != "cancelled",
    )
    requests = ledger.provider_requests()
    _write_provider_usage(paths.provider_usage_path, requests)
    _write_run_report(
        paths.run_report_path,
        configuration=configuration,
        status=status,
        partial_reason=partial_reason,
        known_task_capacity=known_task_capacity,
        allocated_slot_count=allocated_slot_count,
        terminal_outcome_count=terminal_outcome_count,
        accepted_count=accepted_count,
        requests=requests,
    )
    cohorts = _read_review_cohorts(paths.review_cohorts_path)
    human_labels = _read_human_review_labels(paths.human_review_labels_path)
    _write_quality_report(
        paths=paths,
        configuration=configuration,
        status=status,
        partial_reason=partial_reason,
        known_task_capacity=known_task_capacity,
        allocated_slot_count=allocated_slot_count,
        episodes=tuple(record.episode for record in ledger.terminal_outcomes()),
        judgments=ledger.quality_judgments(),
        requests=requests,
        cohorts=cohorts,
        human_labels=human_labels,
    )
    _write_public_manifest(
        paths=paths,
        configuration=configuration,
        source_fingerprint=frozen_initial_state.fingerprint,
    )
    demonstrations = accepted_count
    negatives = terminal_outcome_count - demonstrations
    return RunResult(
        run_directory=paths.run_directory,
        demonstrations_path=paths.demonstrations_path,
        negatives_path=paths.negatives_path,
        provider_usage_path=paths.provider_usage_path,
        manifest_path=paths.manifest_path,
        private_ledger_path=paths.private_ledger_path,
        demonstration_count=demonstrations,
        negative_count=negatives,
        status=status,
        partial_reason=partial_reason,
        task_attempt_count=allocated_slot_count,
        terminal_outcome_count=terminal_outcome_count,
        physical_request_count=len(requests),
        run_report_path=paths.run_report_path,
        shadow_judgments_path=paths.shadow_judgments_path,
        quality_report_path=paths.quality_report_path,
    )


def _write_shadow_quality_judgments(
    *,
    paths: _RunPaths,
    ledger: PrivateLedger,
    configuration: RunConfiguration,
    shadow_judge: _ShadowJudgeContext,
    allow_provider_calls: bool,
) -> None:
    """Evaluate each new terminal Episode in shadow, never changing its admission."""

    for terminal in ledger.terminal_outcomes():
        episode = terminal.episode
        if ledger.quality_judgment(episode.sequence) is not None:
            continue
        judgment = _evaluate_quality_judgment(
            ledger=ledger,
            configuration=configuration,
            episode=episode,
            shadow_judge=shadow_judge,
            allow_provider_calls=allow_provider_calls,
        )
        ledger.record_quality_judgment(judgment)
    lines = (
        json.dumps(
            judgment.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for judgment in ledger.quality_judgments()
    )
    _atomic_write_text(paths.shadow_judgments_path, "".join(lines))


def _evaluate_quality_judgment(
    *,
    ledger: PrivateLedger,
    configuration: RunConfiguration,
    episode: PublicEpisode,
    shadow_judge: _ShadowJudgeContext,
    allow_provider_calls: bool,
) -> QualityJudgment:
    """Judge one bounded Episode without deciding how it will be admitted."""

    if shadow_judge.model is None or not allow_provider_calls:
        reason = shadow_judge.unavailable_reason or "not_requested"
        return _unavailable_quality_judgment(
            episode=episode,
            reason=reason,
            identity=shadow_judge.identity,
            records=(),
        )
    request = QualityJudgeRequest(
        task=episode.task,
        observable_events=episode.events,
        deterministic_results=deterministic_results_for_episode(episode),
        timeout_seconds=configuration.timeout_seconds,
        max_response_bytes=configuration.max_response_bytes,
        max_output_tokens=configuration.max_output_tokens,
    )
    call = _call_model(
        ledger=ledger,
        model=shadow_judge.model,
        configuration=configuration,
        request=request,
        logical_request_id=f"quality_judge:{episode.sequence:04d}",
        sequence=episode.sequence,
        related_sequences=(),
        request_kind="initial",
        failure_injector=None,
        cancellation_signal=None,
    )
    if call.response is None:
        reason: JudgmentUnavailableReason = (
            "request_budget_exhausted"
            if call.error_code == "provider_request_budget_exhausted"
            else "provider_failed"
        )
        return _unavailable_quality_judgment(
            episode=episode,
            reason=reason,
            identity=shadow_judge.identity,
            records=call.records,
        )
    try:
        response = QualityJudgeResponse.model_validate(call.response.content)
        response = response.validate_event_references(len(episode.events))
    except (TypeError, ValueError, ValidationError):
        return _unavailable_quality_judgment(
            episode=episode,
            reason="invalid_judgment",
            identity=shadow_judge.identity,
            records=call.records,
        )
    assert shadow_judge.identity is not None
    return QualityJudgment(
        sequence=episode.sequence,
        episode_id=episode.episode_id,
        domain_id=episode.domain_id,
        availability="available",
        verdict=aggregate_dimension_verdicts(response.dimensions),
        dimensions=response.dimensions,
        judge_identity=shadow_judge.identity,
        usage=_quality_judge_usage(call.records),
    )


def _unavailable_quality_judgment(
    *,
    episode: PublicEpisode,
    reason: JudgmentUnavailableReason,
    identity: QualityJudgeIdentity | None,
    records: Sequence[ProviderRequestRecord],
) -> QualityJudgment:
    return QualityJudgment(
        sequence=episode.sequence,
        episode_id=episode.episode_id,
        domain_id=episode.domain_id,
        availability="unavailable",
        verdict="unavailable",
        unavailable_reason=reason,
        judge_identity=identity,
        usage=_quality_judge_usage(records),
    )


def _apply_semantic_enforcement(
    *,
    episode: PublicEpisode,
    policy_id: str,
    judgment: QualityJudgment,
) -> PublicEpisode:
    """Turn one already-deterministic outcome into an explicit enforce-mode result."""

    admitted = episode.admission.gates.passed and judgment.verdict == "pass"
    if admitted:
        outcome = EpisodeOutcome(
            collection="demonstrations",
            status="succeeded",
            reason_code=None,
        )
    elif episode.admission.gates.passed:
        outcome = EpisodeOutcome(
            collection="negatives",
            status="rejected_after_execution",
            reason_code=f"semantic_judge_{judgment.verdict}",
        )
    else:
        outcome = episode.outcome
    return episode.model_copy(
        update={
            "outcome": outcome,
            "admission": AdmissionRecord(
                mode="enforced",
                status="admitted" if admitted else "rejected",
                gates=episode.admission.gates,
                semantic_judgment=judgment.verdict,
                semantic_policy_id=policy_id,
            ),
        }
    )


def _quality_judge_usage(
    records: Sequence[ProviderRequestRecord],
) -> QualityJudgeUsage:
    summary = _request_usage_summary(records)
    return QualityJudgeUsage(
        physical_request_count=summary.physical_request_count,
        retry_count=summary.retry_count,
        response_hashes=tuple(
            record.response_hash for record in records if record.response_hash is not None
        ),
        known_input_tokens=summary.known_input_tokens,
        known_output_tokens=summary.known_output_tokens,
        known_total_tokens=summary.known_total_tokens,
        unknown_usage_count=summary.unknown_usage_count,
    )


def _write_quality_report(
    *,
    paths: _RunPaths,
    configuration: RunConfiguration,
    status: Literal["completed", "partial", "cancelled", "failed"],
    partial_reason: str | None,
    known_task_capacity: int | None,
    allocated_slot_count: int,
    episodes: Sequence[PublicEpisode],
    judgments: Sequence[QualityJudgment],
    requests: tuple[ProviderRequestRecord, ...],
    cohorts: Sequence[ReviewCohort] = (),
    human_labels: Sequence[HumanReviewLabel] = (),
) -> None:
    payload = build_quality_report(
        run_id=configuration.run_id,
        run_status=status,
        partial_reason=partial_reason,
        allocated_task_attempt_count=allocated_slot_count,
        known_task_capacity=known_task_capacity,
        episodes=episodes,
        judgments=judgments,
        provider_usage=_provider_usage_payload(requests),
        cohorts=cohorts,
        human_labels=human_labels,
        admission_mode=configuration.admission_mode,
        semantic_enforcement=_semantic_enforcement_report_payload(configuration),
    )
    _atomic_write_text(paths.quality_report_path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _semantic_enforcement_report_payload(
    configuration: RunConfiguration,
) -> dict[str, object] | None:
    """Expose optional eligibility separately from shadow/core operation."""

    enforcement = configuration.semantic_enforcement
    if enforcement is None:
        return None
    activation = enforcement.activation
    return {
        "status": (
            "eligible_enforced"
            if activation.eligibility == "eligible"
            else "ineligible_not_dispatched"
        ),
        "policy_id": enforcement.policy.policy_id,
        "policy_fingerprint": enforcement.policy.fingerprint,
        "activation_identity": activation.activation_identity,
        "evaluation_evidence_fingerprint": activation.evaluation_evidence_fingerprint,
        "eligibility": activation.eligibility,
        "ineligibility_reasons": list(activation.ineligibility_reasons),
        "finite_cohort_notice": activation.finite_cohort_notice,
    }


def _write_public_manifest(
    *,
    paths: _RunPaths,
    configuration: RunConfiguration,
    source_fingerprint: str,
) -> None:
    """Hash every available public Agent-first artifact, never the private ledger."""

    base_paths = (
        paths.demonstrations_path,
        paths.negatives_path,
        paths.provider_usage_path,
        paths.run_report_path,
        paths.shadow_judgments_path,
        paths.quality_report_path,
    )
    optional_paths = (
        paths.review_queue_path,
        paths.review_cohorts_path,
        paths.human_review_labels_path,
        paths.review_label_import_report_path,
    )
    artifact_paths = tuple(
        sorted(
            (*base_paths, *(path for path in optional_paths if path.is_file())),
            key=lambda path: path.name,
        )
    )
    manifest = build_manifest(
        run_id=configuration.run_id,
        configuration=configuration.normalized_public_record(),
        source_fingerprint=source_fingerprint,
        artifact_paths=artifact_paths,
    )
    write_manifest(paths.manifest_path, manifest)


def _run_agent_episode(
    *,
    domain_run: DomainRun,
    task: CompiledTask,
    frozen_initial_state: FrozenInitialState,
    context: _EpisodeContext,
    model: JsonModelAdapter,
    ledger: PrivateLedger,
    generation_records: tuple[ProviderRequestRecord, ...],
    cancellation_signal: CancellationSignal | None,
    failure_injector: FailureInjector | object | None,
) -> _EpisodeAttemptResult:
    try:
        episode = domain_run.open_episode(task, frozen_initial_state)
    except Exception:  # noqa: BLE001 - Domain adapter errors must be bounded.
        return _EpisodeAttemptResult(
            episode=_execution_episode(
                context=context,
                task=task.public_task,
                trace=_incomplete_trace("episode_open_failure"),
                assessment=_incomplete_assessment("episode_open_failure"),
                lineage=_model_lineage(model, generation_records),
                terminal_reason="episode_open_failure",
                unsafe_material_detected=has_unsafe_public_material(task.public_task),
            ),
            partial_reason=None,
        )

    safe_task = sanitized_public_task(task.public_task)
    unsafe_material_detected = has_unsafe_public_material(task.public_task)
    events: list[EpisodeEvent] = []
    records: list[ProviderRequestRecord] = list(generation_records)
    mutation_authorization: Literal["not_applicable", "authorized", "rejected"] = (
        "not_applicable"
    )
    repairs_used = 0
    repair_pending = False
    steps_used = 0
    terminal_reason: str | None = None
    final_response_received = False

    while steps_used < context.configuration.step_limit:
        if _is_cancelled(cancellation_signal):
            return _EpisodeAttemptResult(
                episode=None,
                partial_reason="operator_cancelled",
            )
        request = AgentRequest(
            task=safe_task,
            observable_history=tuple(events),
            remaining_step_budget=context.configuration.step_limit - steps_used,
            timeout_seconds=context.configuration.timeout_seconds,
            max_response_bytes=context.configuration.max_response_bytes,
            max_output_tokens=context.configuration.max_output_tokens,
        )
        request_kind: Literal["initial", "repair"] = "repair" if repair_pending else "initial"
        call = _call_model(
            ledger=ledger,
            model=model,
            configuration=context.configuration,
            request=request,
            logical_request_id=(
                f"agent:{context.sequence:04d}:step:{steps_used + 1}:repair:{repairs_used}"
            ),
            sequence=context.sequence,
            related_sequences=(),
            request_kind=request_kind,
            failure_injector=failure_injector,
            cancellation_signal=cancellation_signal,
        )
        records.extend(call.records)
        if call.response is None:
            if call.error_code == "operator_cancelled":
                return _EpisodeAttemptResult(
                    episode=None,
                    partial_reason="operator_cancelled",
                )
            if call.error_code == "provider_request_budget_exhausted":
                return _EpisodeAttemptResult(
                    episode=None,
                    partial_reason="provider_request_budget_exhausted",
                )
            terminal_reason = call.error_code or "agent_request_failed"
            events.append(EpisodeEvent(event_type="error", error_code=terminal_reason))
            break

        try:
            decision = parse_agent_decision(call.response.content)
        except (ValidationError, ValueError):
            events.append(EpisodeEvent(event_type="error", error_code="malformed_agent_decision"))
            if repairs_used >= context.configuration.decision_repair_limit:
                terminal_reason = "malformed_agent_decision"
                break
            repairs_used += 1
            repair_pending = True
            continue

        steps_used += 1
        repair_pending = False
        if isinstance(decision, FinalResponseDecision):
            unsafe_material_detected = (
                unsafe_material_detected
                or has_unsafe_public_material(decision.content)
            )
            events.append(
                bounded_event_for_public_tools(
                    EpisodeEvent(event_type="final_response", content=decision.content),
                    safe_task.tools,
                )
            )
            final_response_received = True
            break

        assert isinstance(decision, ToolCallDecision)
        unsafe_material_detected = (
            unsafe_material_detected
            or has_unsafe_public_material(decision.model_dump(mode="json"))
        )
        action = bounded_event_for_public_tools(
            EpisodeEvent(
                event_type="action",
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            ),
            safe_task.tools,
        )
        events.append(action)
        tool_event, authorization, tool_material_unsafe = _execute_tool_decision(
            episode=episode,
            task=safe_task,
            decision=decision,
        )
        events.append(tool_event)
        unsafe_material_detected = unsafe_material_detected or tool_material_unsafe
        if authorization == "authorized":
            mutation_authorization = "authorized"
        elif authorization == "rejected":
            mutation_authorization = "rejected"
            terminal_reason = "unauthorized_mutation"
            break

    if not final_response_received and terminal_reason is None:
        terminal_reason = "step_budget_exhausted"
        events.append(EpisodeEvent(event_type="error", error_code=terminal_reason))
    trace = ExecutionTrace(
        mutation_authorization=mutation_authorization,
        events=tuple(events),
    )
    assessment = _assess_episode(episode, trace, terminal_reason)
    return _EpisodeAttemptResult(
        episode=_execution_episode(
            context=context,
            task=task.public_task,
            trace=trace,
            assessment=assessment,
            lineage=_model_lineage(model, tuple(records)),
            terminal_reason=terminal_reason,
            unsafe_material_detected=unsafe_material_detected,
        ),
        partial_reason=None,
    )


def _execute_tool_decision(
    *,
    episode: DomainEpisode,
    task: PublicTask,
    decision: ToolCallDecision,
) -> tuple[
    EpisodeEvent,
    Literal["not_applicable", "authorized", "rejected"],
    bool,
]:
    tool = next((tool for tool in task.tools if tool.name == decision.tool_name), None)
    if tool is None:
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=decision.tool_name,
                error_code="unknown_tool",
            ),
            "not_applicable",
            has_unsafe_public_material(decision.model_dump(mode="json")),
        )
    if not _valid_tool_arguments(tool, decision.arguments):
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code="invalid_tool_arguments",
            ),
            "not_applicable",
            has_unsafe_public_material(decision.model_dump(mode="json")),
        )
    try:
        result = _validated_model(
            episode.execute_tool_call(tool.name, decision.arguments),
            ToolExecutionResult,
        )
    except Exception:  # noqa: BLE001 - Domain tool errors become observations.
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code="tool_failure",
            ),
            "not_applicable",
            has_unsafe_public_material(decision.model_dump(mode="json")),
        )
    if result.result_type == "observation":
        assert result.observation is not None
        return (
            bounded_event_for_public_tools(
                EpisodeEvent(
                    event_type="observation",
                    tool_name=tool.name,
                    observation=result.observation,
                ),
                task.tools,
            ),
            "not_applicable",
            has_unsafe_public_material(result),
        )
    if result.result_type == "state_change":
        assert result.change is not None
        return (
            bounded_event_for_public_tools(
                EpisodeEvent(
                    event_type="state_change",
                    tool_name=tool.name,
                    change=result.change,
                ),
                task.tools,
            ),
            "authorized",
            has_unsafe_public_material(result),
        )
    assert result.error_code is not None
    if result.result_type == "unauthorized_mutation":
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code=result.error_code,
            ),
            "rejected",
            has_unsafe_public_material(result),
        )
    return (
        EpisodeEvent(
            event_type="error",
            tool_name=tool.name,
            error_code=result.error_code,
        ),
        "not_applicable",
        has_unsafe_public_material(result),
    )


def _assess_episode(
    episode: DomainEpisode,
    trace: ExecutionTrace,
    terminal_reason: str | None,
) -> EpisodeAssessment:
    if terminal_reason is not None:
        return _incomplete_assessment(terminal_reason)
    try:
        return _validated_model(episode.assess(trace), EpisodeAssessment)
    except Exception:  # noqa: BLE001 - Domain assessment errors remain negatives.
        return _incomplete_assessment("domain_assessment_failure")


def _call_model(
    *,
    ledger: PrivateLedger,
    model: JsonModelAdapter,
    configuration: RunConfiguration,
    request: JsonModelRequest,
    logical_request_id: str,
    sequence: int | None,
    related_sequences: tuple[int, ...],
    request_kind: Literal["initial", "repair"],
    failure_injector: FailureInjector | object | None,
    cancellation_signal: CancellationSignal | None,
) -> _LogicalCallResult:
    """Reserve every physical dispatch and retry only bounded transport failures."""

    records: list[ProviderRequestRecord] = []
    role_limit = {
        "task_generation": configuration.generation_request_limit,
        "agent": configuration.agent_request_limit,
        "quality_judge": configuration.shadow_quality.judge_request_limit,
    }[request.role]
    for physical_attempt in range(configuration.transport_retry_limit + 1):
        if _is_cancelled(cancellation_signal):
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="operator_cancelled",
            )
        reservation = ledger.reserve_provider_request(
            role=request.role,
            logical_request_id=logical_request_id,
            role_limit=role_limit,
            total_limit=configuration.total_request_limit,
            sequence=sequence,
            related_sequences=related_sequences,
            request_kind=request_kind,
        )
        if reservation is None:
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_request_budget_exhausted",
            )
        if _is_cancelled(cancellation_signal):
            return _LogicalCallResult(
                response=None,
                records=tuple((*records, reservation)),
                error_code="operator_cancelled",
            )
        def persist(
            *,
            status: Literal["completed", "failed"],
            response_hash: str | None = None,
            usage: TokenUsage | None = None,
            error_code: str | None = None,
        ) -> ProviderRequestRecord:
            _checkpoint(failure_injector, "before_response_persistence")
            finished = ledger.finish_provider_request(
                reservation.request_id,
                status=status,
                response_hash=response_hash,
                usage=usage,
                error_code=error_code,
            )
            _checkpoint(failure_injector, "after_response_persistence")
            return finished

        _checkpoint(failure_injector, "before_request_dispatch")
        if _is_cancelled(cancellation_signal):
            return _LogicalCallResult(
                response=None,
                records=tuple((*records, reservation)),
                error_code="operator_cancelled",
            )
        try:
            raw_response = model.complete(request)
        except ModelCallError as error:
            _checkpoint(failure_injector, "after_request_dispatch")
            finished = persist(
                status="failed",
                response_hash=error.response_hash,
                usage=error.usage,
                error_code=error.error_code,
            )
            records.append(finished)
            if error.retryable and physical_attempt < configuration.transport_retry_limit:
                continue
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code=error.error_code,
            )
        except (ValidationError, TypeError, ValueError):
            _checkpoint(failure_injector, "after_request_dispatch")
            records.append(persist(status="failed", error_code="provider_response_malformed"))
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_response_malformed",
            )
        except Exception:  # noqa: BLE001 - Adapter failures must not escape the run.
            _checkpoint(failure_injector, "after_request_dispatch")
            records.append(persist(status="failed", error_code="provider_adapter_failure"))
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_adapter_failure",
            )
        _checkpoint(failure_injector, "after_request_dispatch")
        try:
            response = _validated_model(raw_response, JsonModelResponse)
            if len(response.model_dump_json().encode("utf-8")) > request.max_response_bytes:
                raise ModelCallError(
                    "response_bytes_exceeded",
                    retryable=False,
                    response_hash=response.effective_response_hash,
                    usage=response.usage,
                )
            if (
                response.usage is not None
                and response.usage.output_tokens is not None
                and response.usage.output_tokens > request.max_output_tokens
            ):
                raise ModelCallError(
                    "response_tokens_exceeded",
                    retryable=False,
                    response_hash=response.effective_response_hash,
                    usage=response.usage,
                )
        except ModelCallError as error:
            records.append(
                persist(
                    status="failed",
                    response_hash=error.response_hash,
                    usage=error.usage,
                    error_code=error.error_code,
                )
            )
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code=error.error_code,
            )
        except (ValidationError, TypeError, ValueError):
            records.append(persist(status="failed", error_code="provider_response_malformed"))
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_response_malformed",
            )
        records.append(
            persist(
                status="completed",
                response_hash=response.effective_response_hash,
                usage=response.usage,
            )
        )
        return _LogicalCallResult(response=response, records=tuple(records), error_code=None)
    raise AssertionError("bounded model loop must return")


def _mapped_generation_proposals(
    response: JsonModelResponse,
    batch: tuple[AllocatedSlotRecord, ...],
) -> tuple[dict[str, str] | None, Literal["generation_malformed_output", "generation_slot_mismatch"] | None]:
    try:
        generated = GenerationResponse.model_validate(response.content)
    except ValidationError:
        return None, "generation_malformed_output"
    expected_ids = {record.slot_id for record in batch}
    actual_ids = [proposal.slot_id for proposal in generated.proposals]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        return None, "generation_slot_mismatch"
    return {proposal.slot_id: proposal.content for proposal in generated.proposals}, None


def _valid_tool_arguments(tool: ToolDefinition, arguments: dict[str, JsonValue]) -> bool:
    schema = tool.input_schema
    if schema.get("type") != "object":
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        return False
    if any(name not in arguments for name in required):
        return False
    if any(name not in properties for name in arguments):
        return False
    return all(
        isinstance(property_schema, dict)
        and _matches_schema(arguments[name], property_schema)
        for name, property_schema in properties.items()
        if name in arguments
    )


def _matches_schema(value: JsonValue, schema: dict[str, object]) -> bool:
    expected_type = schema.get("type")
    if expected_type == "string":
        if not isinstance(value, str):
            return False
        enum = schema.get("enum")
        return not isinstance(enum, list) or value in enum
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return False


def _execution_episode(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    trace: ExecutionTrace,
    assessment: EpisodeAssessment,
    lineage: ModelLineage,
    terminal_reason: str | None,
    unsafe_material_detected: bool = False,
) -> PublicEpisode:
    unsafe_material_detected = (
        unsafe_material_detected
        or has_unsafe_public_material(task)
        or has_unsafe_public_material(trace)
        or has_unsafe_public_material(assessment)
    )
    final_grounding_passed = any(
        check.name == "final_response_grounded" and check.passed
        for check in assessment.checks
    )
    gates = DeterministicAdmissionGates(
        execution=terminal_reason is None,
        mutation_authorization=trace.mutation_authorization != "rejected",
        assessment=assessment.passed,
        final_grounding=final_grounding_passed,
        unsafe_material=not unsafe_material_detected,
        semantic_key=True,
    )
    admitted = gates.passed
    reason_code = terminal_reason
    if not admitted and reason_code is None:
        reason_code = (
            "unsafe_public_material"
            if not gates.unsafe_material
            else "unauthorized_mutation"
            if not gates.mutation_authorization
            else "final_response_grounding_missing"
            if not gates.final_grounding
            else assessment.reason_codes[0]
            if assessment.reason_codes
            else "deterministic_assessment_failed"
        )
    return PublicEpisode(
        episode_id=_episode_id(context.configuration.run_id, context.sequence),
        candidate_id=_candidate_id(context.configuration.run_id, context.sequence),
        sequence=context.sequence,
        domain_id=context.configuration.domain_id,
        domain_version=context.domain_version,
        task=task,
        events=trace.events,
        mutation_authorization=trace.mutation_authorization,
        outcome=EpisodeOutcome(
            collection="demonstrations" if admitted else "negatives",
            status="succeeded" if admitted else "rejected_after_execution",
            reason_code=reason_code,
        ),
        verification=assessment,
        admission=AdmissionRecord(
            mode="deterministic",
            status="admitted" if admitted else "rejected",
            gates=gates,
        ),
        lineage=lineage,
    )


def _compilation_negative(
    *,
    context: _EpisodeContext,
    rejection: CompilationRejection,
    lineage: ModelLineage,
) -> PublicEpisode:
    return _pre_execution_negative(
        context=context,
        task=rejection.public_task,
        reason_code=rejection.reason_code,
        lineage=lineage,
        unsafe_material_detected=has_unsafe_public_material(rejection.public_task),
    )


def _pre_execution_negative(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    reason_code: str,
    lineage: ModelLineage,
    unsafe_material_detected: bool = False,
) -> PublicEpisode:
    unsafe_material_detected = unsafe_material_detected or has_unsafe_public_material(task)
    gates = DeterministicAdmissionGates(
        execution=False,
        mutation_authorization=reason_code not in {
            "mutation_not_authorized_by_public_task",
            "unauthorized_mutation",
        },
        assessment=False,
        final_grounding=False,
        unsafe_material=not unsafe_material_detected,
        semantic_key=False,
    )
    return PublicEpisode(
        episode_id=_episode_id(context.configuration.run_id, context.sequence),
        candidate_id=_candidate_id(context.configuration.run_id, context.sequence),
        sequence=context.sequence,
        domain_id=context.configuration.domain_id,
        domain_version=context.domain_version,
        task=task,
        events=(),
        outcome=EpisodeOutcome(
            collection="negatives",
            status="rejected_before_execution",
            reason_code=reason_code,
        ),
        admission=AdmissionRecord(
            mode="deterministic",
            status="rejected",
            gates=gates,
        ),
        lineage=lineage,
    )


def _incomplete_trace(reason_code: str) -> ExecutionTrace:
    return ExecutionTrace(
        mutation_authorization="not_applicable",
        events=(EpisodeEvent(event_type="error", error_code=reason_code),),
    )


def _incomplete_assessment(reason_code: str) -> EpisodeAssessment:
    return EpisodeAssessment(
        passed=False,
        checks=(),
        reason_codes=(reason_code,),
        coverage_tags=(),
        structural_key="incomplete",
    )


def _fallback_public_task(_slot: TaskSlot) -> PublicTask:
    """A bounded public negative when generation fails before Domain compilation."""

    return PublicTask(
        instruction="Task generation failed before public task compilation.",
        tools=(
            ToolDefinition(
                name="unavailable",
                description="No executable tool is available before task compilation.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
            ),
        ),
    )


def _model_lineage(
    model: JsonModelAdapter,
    records: tuple[ProviderRequestRecord, ...],
) -> ModelLineage:
    by_role: dict[ModelRole, list[ProviderRequestRecord]] = defaultdict(list)
    for record in records:
        by_role[record.role].append(record)
    roles: list[RoleLineage] = []
    for role in ("task_generation", "agent"):
        role_records = by_role[role]
        if not role_records:
            continue
        summary = _request_usage_summary(role_records)
        roles.append(
            RoleLineage(
                role=role,
                provider_id=model.provider_id,
                model_id=model.model_id,
                model_version=model.model_version,
                physical_request_count=summary.physical_request_count,
                retry_count=summary.retry_count,
                response_hashes=tuple(
                    record.response_hash
                    for record in role_records
                    if record.response_hash is not None
                ),
                known_input_tokens=summary.known_input_tokens,
                known_output_tokens=summary.known_output_tokens,
                known_total_tokens=summary.known_total_tokens,
                unknown_usage_count=summary.unknown_usage_count,
            )
        )
    return ModelLineage(
        model_id=model.model_id,
        model_version=model.model_version,
        roles=tuple(roles),
    )


def _known_token_total(
    usages: Sequence[TokenUsage | None],
    field_name: Literal["input_tokens", "output_tokens", "total_tokens"],
) -> int | None:
    values: list[int] = []
    for usage in usages:
        if usage is None:
            continue
        value = getattr(usage, field_name)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def _replay_episode(
    *,
    domain_run: DomainRun,
    saved_episode: PublicEpisode,
    case: TaskCaseRecord,
    frozen_initial_state: FrozenInitialState,
) -> ReplayEpisodeResult:
    """Rebuild one saved case and compare its tool observations and assessment."""

    try:
        task = domain_run.restore_task_case(
            public_task=case.public_task,
            semantic_key=case.semantic_key,
            private_case_bytes=case.private_case_bytes(),
        )
        episode = domain_run.open_replay_episode(task, frozen_initial_state)
        trace, observation_drift = _replay_trace(
            episode=episode,
            task=task.public_task,
            saved_events=saved_episode.events,
        )
        if trace.mutation_authorization != saved_episode.mutation_authorization:
            observation_drift = True
        assessment = _replay_assessment(episode, trace, saved_episode.verification)
        assessment_drift = _assessment_drift(saved_episode.verification, assessment)
    except Exception:  # noqa: BLE001 - Replay reports Domain failures without providers.
        return ReplayEpisodeResult(
            episode_id=saved_episode.episode_id,
            sequence=saved_episode.sequence,
            status="replay_failed",
            observation_drift=True,
            assessment_drift=True,
        )
    status: Literal[
        "aligned",
        "observation_drift",
        "assessment_drift",
        "observation_and_assessment_drift",
    ]
    if observation_drift and assessment_drift:
        status = "observation_and_assessment_drift"
    elif observation_drift:
        status = "observation_drift"
    elif assessment_drift:
        status = "assessment_drift"
    else:
        status = "aligned"
    return ReplayEpisodeResult(
        episode_id=saved_episode.episode_id,
        sequence=saved_episode.sequence,
        status=status,
        observation_drift=observation_drift,
        assessment_drift=assessment_drift,
    )


def _replay_trace(
    *,
    episode: DomainEpisode,
    task: PublicTask,
    saved_events: tuple[EpisodeEvent, ...],
) -> tuple[ExecutionTrace, bool]:
    safe_task = sanitized_public_task(task)
    actual_events: list[EpisodeEvent] = []
    observation_drift = False
    mutation_authorization: Literal["not_applicable", "authorized", "rejected"] = (
        "not_applicable"
    )
    index = 0
    while index < len(saved_events):
        event = saved_events[index]
        if event.event_type != "action":
            actual_events.append(event)
            index += 1
            continue
        actual_events.append(event)
        if event.tool_name is None:
            observation_drift = True
            index += 1
            continue
        decision = ToolCallDecision(
            type="tool_call",
            tool_name=event.tool_name,
            arguments=event.arguments or {},
        )
        actual_result, authorization, _ = _execute_tool_decision(
            episode=episode,
            task=safe_task,
            decision=decision,
        )
        if authorization == "authorized":
            mutation_authorization = "authorized"
        elif authorization == "rejected":
            mutation_authorization = "rejected"
        if index + 1 >= len(saved_events):
            observation_drift = True
            actual_events.append(actual_result)
            index += 1
            continue
        expected_result = saved_events[index + 1]
        actual_events.append(actual_result)
        if expected_result != actual_result:
            observation_drift = True
        index += 2
    return (
        ExecutionTrace(
            mutation_authorization=mutation_authorization,
            events=tuple(actual_events),
        ),
        observation_drift,
    )


def _replay_assessment(
    episode: DomainEpisode,
    trace: ExecutionTrace,
    saved_assessment: EpisodeAssessment | None,
) -> EpisodeAssessment | None:
    if saved_assessment is None:
        return None
    if saved_assessment.structural_key == "incomplete":
        reason_code = saved_assessment.reason_codes[0] if saved_assessment.reason_codes else "replay_incomplete"
        return _incomplete_assessment(reason_code)
    try:
        return _validated_model(episode.assess(trace), EpisodeAssessment)
    except Exception:  # noqa: BLE001 - Replay assessment errors become drift evidence.
        return _incomplete_assessment("domain_assessment_failure")


def _assessment_drift(
    saved: EpisodeAssessment | None,
    replayed: EpisodeAssessment | None,
) -> bool:
    if saved is None or replayed is None:
        return saved is not replayed
    return saved.model_dump(mode="json") != replayed.model_dump(mode="json")


def _read_public_episodes(*paths: Path) -> tuple[PublicEpisode, ...]:
    episodes: list[PublicEpisode] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"missing public Episode collection: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                episodes.append(PublicEpisode.model_validate_json(line))
    return tuple(sorted(episodes, key=lambda episode: episode.sequence))


def _write_replay_report(
    path: Path,
    results: tuple[ReplayEpisodeResult, ...],
) -> None:
    payload = {
        "schema_version": "agent_replay_report_v1",
        "aligned": all(result.status in {"aligned", "not_executed"} for result in results),
        "episodes": [
            {
                "episode_id": result.episode_id,
                "sequence": result.sequence,
                "status": result.status,
                "observation_drift": result.observation_drift,
                "assessment_drift": result.assessment_drift,
            }
            for result in results
        ],
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _atomic_write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(contents, encoding="utf-8")
    os.replace(temporary_path, path)


def _write_terminal_collections(
    paths: _RunPaths,
    outcomes: Iterable[TerminalOutcomeRecord],
) -> None:
    demonstration_temporary = paths.demonstrations_path.with_name(
        f".{paths.demonstrations_path.name}.{uuid.uuid4().hex}.tmp"
    )
    negative_temporary = paths.negatives_path.with_name(
        f".{paths.negatives_path.name}.{uuid.uuid4().hex}.tmp"
    )
    paths.demonstrations_path.parent.mkdir(parents=True, exist_ok=True)
    with demonstration_temporary.open("w", encoding="utf-8") as demonstrations, negative_temporary.open(
        "w", encoding="utf-8"
    ) as negatives:
        for outcome in outcomes:
            line = (
                json.dumps(
                    sanitized_episode_record(outcome.episode),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            destination = (
                demonstrations
                if outcome.episode.outcome.collection == "demonstrations"
                else negatives
            )
            destination.write(line)
    os.replace(demonstration_temporary, paths.demonstrations_path)
    os.replace(negative_temporary, paths.negatives_path)


def _write_provider_usage(
    path: Path,
    records: tuple[ProviderRequestRecord, ...],
) -> None:
    _atomic_write_text(path, json.dumps(_provider_usage_payload(records), sort_keys=True, indent=2) + "\n")


def _provider_usage_payload(records: tuple[ProviderRequestRecord, ...]) -> dict[str, object]:
    summary = _request_usage_summary(records)
    by_role: dict[ModelRole, list[ProviderRequestRecord]] = defaultdict(list)
    for record in records:
        by_role[record.role].append(record)
    roles = {
        role: _usage_summary(role_records)
        for role, role_records in sorted(by_role.items())
    }
    return {
        "schema_version": "agent_provider_usage_v1",
        "total_physical_requests": summary.physical_request_count,
        "reserved_request_count": summary.reserved_request_count,
        "failed_request_count": summary.failed_request_count,
        "completed_request_count": summary.completed_request_count,
        "roles": roles,
    }


def _usage_summary(records: list[ProviderRequestRecord]) -> dict[str, object]:
    summary = _request_usage_summary(records)
    return {
        "physical_request_count": summary.physical_request_count,
        "retry_count": summary.retry_count,
        "repair_request_count": summary.repair_request_count,
        "reserved_request_count": summary.reserved_request_count,
        "failed_request_count": summary.failed_request_count,
        "completed_request_count": summary.completed_request_count,
        "known_input_tokens": summary.known_input_tokens,
        "known_output_tokens": summary.known_output_tokens,
        "known_total_tokens": summary.known_total_tokens,
        "unknown_usage_count": summary.unknown_usage_count,
    }


def _request_usage_summary(
    records: Sequence[ProviderRequestRecord],
) -> _RequestUsageSummary:
    usages = [record.usage for record in records]
    return _RequestUsageSummary(
        physical_request_count=len(records),
        retry_count=len(records) - len({record.logical_request_id for record in records}),
        repair_request_count=sum(record.request_kind == "repair" for record in records),
        known_input_tokens=_known_token_total(usages, "input_tokens"),
        known_output_tokens=_known_token_total(usages, "output_tokens"),
        known_total_tokens=_known_token_total(usages, "total_tokens"),
        unknown_usage_count=sum(
            usage is None or usage.total_tokens is None for usage in usages
        ),
        reserved_request_count=sum(record.status == "reserved" for record in records),
        failed_request_count=sum(record.status == "failed" for record in records),
        completed_request_count=sum(record.status == "completed" for record in records),
    )


def _write_run_report(
    path: Path,
    *,
    configuration: RunConfiguration,
    status: Literal["completed", "partial", "cancelled", "failed"],
    partial_reason: str | None,
    known_task_capacity: int | None,
    allocated_slot_count: int,
    terminal_outcome_count: int,
    accepted_count: int,
    requests: tuple[ProviderRequestRecord, ...],
) -> None:
    payload = {
        "schema_version": "agent_run_report_v1",
        "status": status,
        "partial_reason": partial_reason,
        "targets": {
            "accepted_target": configuration.accepted_target,
            "task_attempt_limit": configuration.slot_limit,
        },
        "capacity": {
            "known_task_capacity": known_task_capacity,
            "allocated_slot_count": allocated_slot_count,
            "capacity_status": (
                "known" if known_task_capacity is not None else "unknown"
            ),
        },
        "outcomes": {
            "task_attempt_count": allocated_slot_count,
            "terminal_outcome_count": terminal_outcome_count,
            "accepted_count": accepted_count,
            "negative_count": terminal_outcome_count - accepted_count,
            "incomplete_slot_count": allocated_slot_count - terminal_outcome_count,
        },
        "provider_usage": _provider_usage_payload(requests),
    }
    _atomic_write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _validated_configuration(
    configuration: RunConfiguration | Mapping[str, object],
) -> RunConfiguration:
    if isinstance(configuration, RunConfiguration):
        return configuration
    return RunConfiguration.model_validate(configuration)


def _validated_model[ValidatedModel: BaseModel](
    value: object,
    model_type: type[ValidatedModel],
) -> ValidatedModel:
    if isinstance(value, model_type):
        return value
    return model_type.model_validate(value)


def _bounded_slots(slots: tuple[TaskSlot, ...], limit: int) -> tuple[TaskSlot, ...]:
    bounded = slots[:limit]
    slot_ids = tuple(slot.slot_id for slot in bounded)
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("Domain emitted duplicate deterministic slot ids")
    return bounded


def _candidate_id(run_id: str, sequence: int) -> str:
    return f"candidate_{run_id}_{sequence:04d}"


def _episode_id(run_id: str, sequence: int) -> str:
    return f"episode_{run_id}_{sequence:04d}"
