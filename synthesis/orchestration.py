"""Durable, opt-in local orchestration for deterministic synthesis jobs.

The runner in this module owns job lifecycle state only. Candidate execution,
stable duplicate admission, and dataset assembly remain in
``synthesis.pipeline`` and its existing downstream seams.
"""

from __future__ import annotations

import errno
import hashlib
import inspect
import json
import os
import re
import secrets
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported local runner is POSIX-only.
    fcntl = None  # type: ignore[assignment]

from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    PolicyGenerator,
    ProvisionalCandidateOutcome,
)
from synthesis.concurrency import validate_concurrency
from synthesis.coverage_assignments import (
    CoverageAssignment,
    CoverageAssignmentRecovery,
    CoverageAssignmentSchedulerFactory,
    build_coverage_assignment_scheduler_factory,
)
from synthesis.domain_generation import (
    generate_domain_llm_candidates,
)
from synthesis.llm import LLMProviderAmbiguousError, LLMProviderError
from synthesis.pipeline import (
    CandidateGenerator,
    CandidateGeneratorFactory,
    PipelineCancellation,
    PipelineResult,
    run_foundation_pipeline,
)
from synthesis.run_profiles import RunProfile
from synthesis.domain_sources import (
    ProfileLocalDomainSourceRequest,
    build_profile_local_domain_source_input,
    resolve_domain_source_importer,
)
from synthesis.sources import (
    ControlledSourceFetchError,
    SourceBundle,
    build_external_fixture_source_bundle,
)
from synthesis.task_contracts import (
    ExpectedOutcome,
    ExpectedStateCheck,
    PolicyHint,
    TaskContract,
    TaskIntent,
    candidate_from_task_contract,
    validate_task_contract,
)
from synthesis.tasks import CandidateTask, generate_scale_probe_candidates


JOB_SCHEMA_VERSION = "orchestration_job_v1"
WORK_ITEM_SCHEMA_VERSION = "orchestration_work_item_v1"
EVENT_SCHEMA_VERSION = "orchestration_event_v1"
TASK_CHECKPOINT_SCHEMA_VERSION = "task_contract_checkpoint_v1"
CANDIDATE_CHECKPOINT_SCHEMA_VERSION = "orchestration_candidate_checkpoint_v1"
INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION = "orchestration_invalid_candidate_v1"
CONFIGURATION_IDENTITY_SCHEMA_VERSION = "orchestration_configuration_identity_v1"
LOCK_SCHEMA_VERSION = "orchestration_lock_v1"
PROVIDER_ATTEMPT_SCHEMA_VERSION = "orchestration_provider_attempt_v1"
PROVIDER_USAGE_SCHEMA_VERSION = "orchestration_provider_usage_v1"

JOB_STATUSES = {
    "pending",
    "running",
    "cancelling",
    "cancelled",
    "failed",
    "completed",
}
WORK_ITEM_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}
WORK_ITEM_RESULT_KINDS = {"accepted", "rejected"}
JOB_EXECUTION_MODES = {"candidate_set", "coverage"}
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_UNSET_CONCURRENCY = object()


class OrchestrationError(RuntimeError):
    """Base class for deterministic local orchestration errors."""


class JobConfigurationError(OrchestrationError, ValueError):
    """Raised when a job configuration is unsupported or drifts on resume."""


class LogicalCallBudgetExceeded(JobConfigurationError):
    """Raised before a provider action could exceed cumulative authorization."""


class JournalCorruptionError(OrchestrationError, ValueError):
    """Raised when durable journal history cannot be replayed safely."""


class InvalidTransitionError(OrchestrationError, ValueError):
    """Raised when a durable lifecycle transition is invalid."""


class JobInterruption(OrchestrationError):
    """Deterministic failure-injection signal leaving a job resumable."""

    def __init__(self, job_id: str, message: str = "serial job interrupted") -> None:
        super().__init__(message)
        self.job_id = job_id


class JobLockError(OrchestrationError):
    """Raised when another local writer owns the serial job lock."""


class StaleJobLockError(JobLockError):
    """Raised when recovering an orphaned lock was not explicitly requested."""


class CancellationSignal:
    """Thread-safe cooperative cancellation signal for one local job.

    The signal is deliberately local and one-way. A caller may also pass a
    standard :class:`threading.Event` to ``run_serial_job``; this small wrapper
    exists for callers that want an explicit ``cancel()`` operation.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def set(self) -> None:
        """Provide ``threading.Event``-compatible spelling for test operators."""

        self.cancel()

    def is_set(self) -> bool:
        return self._event.is_set()


class _CancellationController:
    def __init__(
        self,
        store: "_LocalJobStore",
        signal: object | None,
    ) -> None:
        self._store = store
        self._signal = signal
        self._lock = threading.Lock()
        self._requested = False

    def check(self) -> bool:
        """Observe the signal and durably request cancellation once."""

        if not _cancellation_signal_is_set(self._signal):
            return self._requested or self._store.status == "cancelling"
        self.request()
        return True

    def request(self) -> None:
        with self._lock:
            self._requested = True
            self._store.request_cancellation(reason="operator_requested")

# Public names make deterministic fake providers easy to write without exposing
# provider-specific transport or credential details.
ProviderAttemptAmbiguous = LLMProviderAmbiguousError
ProviderResponseLost = LLMProviderAmbiguousError


@dataclass(frozen=True)
class SerialJobResult:
    """Observable result of one create, resume, or idempotent inspect operation."""

    job_record: Mapping[str, object]
    work_items: tuple[Mapping[str, object], ...]
    pipeline_result: PipelineResult | None
    orchestration_dir: Path
    job_path: Path
    work_items_path: Path
    events_path: Path
    provider_usage_path: Path | None = None
    provider_attempts: tuple[Mapping[str, object], ...] = ()
    provider_usage: Mapping[str, object] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return str(self.job_record["status"])

    @property
    def terminal(self) -> bool:
        return self.status in {"completed", "cancelled", "failed"}

    @property
    def job(self) -> Mapping[str, object]:
        """Compatibility alias for callers that prefer the shorter name."""

        return self.job_record

    @property
    def max_concurrency(self) -> int:
        return validate_concurrency(self.job_record["max_concurrency"])


SerialJobInterruptionHook = Callable[[Mapping[str, object]], None]
TimestampFactory = Callable[[], str]
ProviderFactory = Callable[[], object]


@dataclass(frozen=True)
class _ResolvedSerialInputs:
    source_bundle: SourceBundle | None
    domain_environment_input: object | None
    source_events: list[dict[str, object]] | None
    run_profile_metadata: dict[str, object] | None


def run_serial_job(
    output_dir: Path,
    *,
    job_id: str,
    run_profile: RunProfile,
    resume: bool = False,
    candidate_generator: CandidateGenerator | None = None,
    candidate_generator_factory: CandidateGeneratorFactory | None = None,
    policy_generator: PolicyGenerator | None = None,
    source_bundle: SourceBundle | None = None,
    domain_environment_input: object | None = None,
    source_events: list[dict[str, object]] | None = None,
    run_profile_metadata: dict[str, object] | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
    write_episode_logs: bool = False,
    interrupt_after: int | None = None,
    interruption_hook: SerialJobInterruptionHook | None = None,
    timestamp_factory: TimestampFactory | None = None,
    authorization_limits: Mapping[str, object] | None = None,
    recover_stale_lock: bool = False,
    provider: object | None = None,
    provider_factory: ProviderFactory | None = None,
    provider_alias: str | None = None,
    model_alias: str | None = None,
    max_concurrency: int | None | object = _UNSET_CONCURRENCY,
    cancellation_signal: object | None = None,
) -> SerialJobResult:
    """Run or resume one local job under an exclusive lock.

    Deterministic fixture jobs retain their original candidate-generator path.
    An explicit provider opts a representative ``llm`` profile into durable
    generation-attempt journaling. Provider aliases are identity only; provider
    objects and credentials are never written. Omitting the concurrency bound
    selects one worker; a resumed job reuses the bound recorded at creation.
    """

    _validate_cancellation_signal(cancellation_signal)
    provider_identity = _normalize_provider_identity(
        provider_present=(provider is not None or provider_factory is not None),
        generation_mode=(
            run_profile.generation.mode
            if isinstance(run_profile, RunProfile)
            else None
        ),
        provider_alias=provider_alias,
        model_alias=model_alias,
    )
    requested_max_concurrency = _normalize_requested_concurrency(max_concurrency)
    normalized_limits = _normalize_authorization_limits(authorization_limits)
    _validate_serial_configuration(
        job_id=job_id,
        run_profile=run_profile,
        interrupt_after=interrupt_after,
        provider_identity=provider_identity,
        authorization_limits=normalized_limits,
        provider=provider,
        provider_factory=provider_factory,
        candidate_generator=candidate_generator,
        candidate_generator_factory=candidate_generator_factory,
        max_concurrency=requested_max_concurrency,
    )
    now = timestamp_factory or _utc_timestamp
    output_dir = Path(output_dir)
    orchestration_dir = output_dir / "orchestration" / job_id
    store = _LocalJobStore(orchestration_dir, timestamp_factory=now)

    def validate_stale_state() -> None:
        if resume and store.exists:
            store.load(repair_tail=False)

    with _LocalJobLock(
        serial_job_lock_path(output_dir, job_id),
        timestamp_factory=now,
        recover_stale_lock=recover_stale_lock,
        stale_state_validator=validate_stale_state,
    ) as lock:
        return _run_serial_job_locked(
            output_dir,
            job_id=job_id,
            run_profile=run_profile,
            resume=resume,
            candidate_generator=candidate_generator,
            candidate_generator_factory=candidate_generator_factory,
            policy_generator=policy_generator,
            source_bundle=source_bundle,
            domain_environment_input=domain_environment_input,
            source_events=source_events,
            run_profile_metadata=run_profile_metadata,
            parent_artifact_path=parent_artifact_path,
            route_reviewable_failures=route_reviewable_failures,
            write_episode_logs=write_episode_logs,
            interrupt_after=interrupt_after,
            interruption_hook=interruption_hook,
            timestamp_factory=now,
            authorization_limits=normalized_limits,
            provider=provider,
            provider_factory=provider_factory,
            provider_identity=provider_identity,
            max_concurrency=requested_max_concurrency,
            cancellation_signal=cancellation_signal,
            store=store,
            lock=lock,
        )


def _run_serial_job_locked(
    output_dir: Path,
    *,
    job_id: str,
    run_profile: RunProfile,
    resume: bool = False,
    candidate_generator: CandidateGenerator | None = None,
    candidate_generator_factory: CandidateGeneratorFactory | None = None,
    policy_generator: PolicyGenerator | None = None,
    source_bundle: SourceBundle | None = None,
    domain_environment_input: object | None = None,
    source_events: list[dict[str, object]] | None = None,
    run_profile_metadata: dict[str, object] | None = None,
    parent_artifact_path: Path | None = None,
    route_reviewable_failures: bool = False,
    write_episode_logs: bool = False,
    interrupt_after: int | None = None,
    interruption_hook: SerialJobInterruptionHook | None = None,
    timestamp_factory: TimestampFactory | None = None,
    authorization_limits: Mapping[str, object] | None = None,
    provider: object | None = None,
    provider_factory: ProviderFactory | None = None,
    provider_identity: Mapping[str, str] | None = None,
    max_concurrency: int | None = None,
    cancellation_signal: object | None = None,
    store: _LocalJobStore | None = None,
    lock: _LocalJobLock | None = None,
) -> SerialJobResult:
    """Run or resume one deterministic candidate set with a local bound.

    A validated :class:`~synthesis.run_profiles.RunProfile` is the durable
    configuration identity. On creation the pipeline's generated candidate set
    is recorded before the first candidate is processed. Candidate work uses
    the persisted local concurrency bound; on resume the stored candidate set
    and completed provisional outcomes are supplied back to the existing
    pipeline, which performs the normal stable merge and artifact assembly.
    """

    now = timestamp_factory or _utc_timestamp
    output_dir = Path(output_dir)
    authorization_limits = _normalize_authorization_limits(authorization_limits)
    if store is None:
        orchestration_dir = output_dir / "orchestration" / job_id
        store = _LocalJobStore(orchestration_dir, timestamp_factory=now)
    provider_mode = provider_identity is not None
    coverage_mode = run_profile.coverage_profile is not None
    provider_holder = [provider]

    def resolve_provider() -> object:
        if provider_holder[0] is None:
            if provider_factory is None:
                raise JobConfigurationError(
                    "provider or provider_factory is required for llm serial jobs"
                )
            provider_holder[0] = provider_factory()
        client = provider_holder[0]
        if client is None or not callable(getattr(client, "generate_json", None)):
            raise JobConfigurationError(
                "provider must expose generate_json(prompt, role=...)"
            )
        return client

    coverage_recovery: tuple[CoverageAssignmentRecovery, ...] | None = None
    cancellation_controller: _CancellationController | None = None
    if resume:
        if not store.exists:
            raise JobConfigurationError(
                f"cannot resume missing serial job: {job_id}"
            )
        if not store.loaded:
            store.load(repair_tail=False)
        persisted_max_concurrency = store.max_concurrency
        if (
            max_concurrency is not None
            and max_concurrency != persisted_max_concurrency
        ):
            raise JobConfigurationError(
                "max_concurrency does not match durable serial job"
            )
        effective_max_concurrency = persisted_max_concurrency
        store.validate_configuration_identity(
            run_profile,
            authorization_limits,
            output_dir=output_dir,
            provider_identity=provider_identity,
            max_concurrency=effective_max_concurrency,
        )
    resolved_inputs = _resolve_profile_source_inputs(
        run_profile,
        source_bundle=source_bundle,
        domain_environment_input=domain_environment_input,
        source_events=source_events,
        run_profile_metadata=run_profile_metadata,
    )
    source_bundle = resolved_inputs.source_bundle
    domain_environment_input = resolved_inputs.domain_environment_input
    source_events = resolved_inputs.source_events
    run_profile_metadata = resolved_inputs.run_profile_metadata
    execution_config_hash = _execution_config_hash(
        policy_generator=policy_generator,
        source_bundle=source_bundle,
        domain_environment_input=domain_environment_input,
        source_events=source_events,
        run_profile_metadata=run_profile_metadata,
        parent_artifact_path=parent_artifact_path,
        route_reviewable_failures=route_reviewable_failures,
        write_episode_logs=write_episode_logs,
    )
    if resume:
        store.validate_configuration(run_profile, execution_config_hash)
        store.rebuild_snapshots()
        store.repair_journal_tail()
        if lock is not None and lock.stale_recovered:
            store.lock_recovered()
        if store.status == "completed":
            return store.result(output_dir)
        if store.status not in {"running", "cancelling", "cancelled", "failed"}:
            raise JobConfigurationError(
                f"serial job {job_id!r} is not resumable from status {store.status!r}"
            )
        cancellation_controller = _CancellationController(
            store,
            cancellation_signal,
        )
        store.resume()
        if coverage_mode:
            store.recover_coverage_provider_checkpoints()
            store.recover_coverage_generation_rejections(
                include_episode_log=write_episode_logs,
            )
        stored_tasks = tuple(
            _candidate_from_record(item["candidate"])
            for item in store.work_items
        )
        effective_candidate_generator: CandidateGenerator | None = None
    else:
        if store.exists:
            raise JobConfigurationError(
                f"serial job already exists: {job_id}; pass resume=True"
            )
        effective_max_concurrency = max_concurrency or 1
        store.create(
            job_id=job_id,
            run_profile=run_profile,
            execution_config_hash=execution_config_hash,
            output_dir=output_dir,
            authorization_limits=authorization_limits,
            provider_identity=provider_identity,
            max_concurrency=effective_max_concurrency,
        )
        cancellation_controller = _CancellationController(
            store,
            cancellation_signal,
        )
        effective_candidate_generator = candidate_generator

    assert cancellation_controller is not None
    cancellation_check = cancellation_controller.check

    effective_candidate_generator_factory: CandidateGeneratorFactory | None = None
    coverage_scheduler_factory: CoverageAssignmentSchedulerFactory | None = None
    if coverage_mode:
        if not provider_mode:
            raise JobConfigurationError(
                "coverage serial orchestration requires an explicit provider"
            )

        def coverage_assignment_wave(
            assignments: tuple[CoverageAssignment, ...],
            wave: int,
        ) -> None:
            if cancellation_check():
                raise PipelineCancellation()
            for assignment in assignments:
                store.create_coverage_item(assignment, wave=wave)
            if interruption_hook is not None:
                interruption_hook(
                    {
                        "event_type": "coverage_wave_issued",
                        "coverage_wave": wave,
                        "assignments": [
                            assignment.lineage()
                            for assignment in assignments
                        ],
                    }
                )
            if cancellation_check():
                raise PipelineCancellation()

        def coverage_generation_rejection(
            assignment: CoverageAssignment,
            rejection: Mapping[str, object],
        ) -> None:
            if cancellation_check():
                raise PipelineCancellation()
            store.record_coverage_generation_rejection(
                assignment.assignment_ordinal,
                rejection,
            )
            store.start_item(
                assignment.assignment_ordinal,
                assignment.assignment_id,
            )
            candidate_id = rejection.get("candidate_id")
            outcome = ProvisionalCandidateOutcome(
                sequence_index=assignment.assignment_ordinal,
                candidate_id=(
                    str(candidate_id)
                    if isinstance(candidate_id, str)
                    else "generation_stage"
                ),
                rejection=dict(rejection),
            )
            store.complete_item(
                assignment.assignment_ordinal,
                outcome,
                include_episode_log=write_episode_logs,
            )
            if interruption_hook is not None:
                interruption_hook(
                    {
                        "event_type": "coverage_generation_rejected",
                        **store.item_for_sequence(assignment.assignment_ordinal),
                    }
                )

        def coverage_attempt_observer_factory(assignment: CoverageAssignment):
            return _CoverageProviderAttemptObserver(
                store,
                assignment=assignment,
                provider_identity=provider_identity,
                interruption_hook=interruption_hook,
                cancellation_check=cancellation_check,
            )

        coverage_scheduler_factory = build_coverage_assignment_scheduler_factory(
            resolve_provider(),
            assignment_wave_callback=coverage_assignment_wave,
            attempt_observer_factory=coverage_attempt_observer_factory,
            generation_rejection_callback=coverage_generation_rejection,
            max_concurrency=effective_max_concurrency,
        )
        if resume:
            coverage_recovery = _coverage_recovery_from_store(store)
        effective_candidate_generator = None
        effective_candidate_generator_factory = None
    elif provider_mode:
        def provider_generator_factory(bundle):
            generation_spec = getattr(bundle, "generation_spec", None)
            if generation_spec is None:
                raise JobConfigurationError(
                    "provider-backed serial generation requires a fixture generation spec"
                )
            target_candidate_count = run_profile.generation.target_candidate_count
            if target_candidate_count is None:
                raise JobConfigurationError(
                    "provider-backed serial generation requires a target candidate count"
                )

            def generate(seed):
                observer = _ProviderAttemptObserver(
                    store,
                    provider_identity=provider_identity,
                    interruption_hook=interruption_hook,
                    cancellation_check=cancellation_check,
                )
                return generate_domain_llm_candidates(
                    seed,
                    resolve_provider(),
                    spec=generation_spec,
                    target_candidate_count=target_candidate_count,
                    initial_contracts=store.provider_checkpoint_contracts,
                    starting_batch_index=store.next_provider_batch_index,
                    attempt_observer=observer,
                )

            return generate

        if resume and store.candidate_set_hash is not None:
            effective_candidate_generator = lambda _seed: list(stored_tasks)
        else:
            effective_candidate_generator_factory = provider_generator_factory
    elif resume:
        if store.candidate_set_hash is not None:
            effective_candidate_generator = lambda _seed: list(stored_tasks)
        else:
            # Cancellation may happen before deterministic candidate intent is
            # durably bound. Rebuild that intent from the validated profile on
            # resume; once bound, the persisted candidate set remains the sole
            # source of truth.
            effective_candidate_generator = candidate_generator or _default_deterministic_generator(
                run_profile
            )
            effective_candidate_generator_factory = candidate_generator_factory
    else:
        effective_candidate_generator = candidate_generator or _default_deterministic_generator(
            run_profile
        )
        effective_candidate_generator_factory = candidate_generator_factory

    completed_outcomes = {
        _sequence_index(item): _outcome_from_record(item["outcome"])
        for item in store.work_items
        if item["status"] == "completed" and item.get("outcome") is not None
    }

    def bind_candidate_set(tasks: tuple[CandidateTask, ...]) -> None:
        candidate_records = tuple(_candidate_to_record(task) for task in tasks)
        candidate_set_hash = _hash_json(candidate_records)
        configured_target = run_profile.generation.target_candidate_count
        if configured_target is not None and len(candidate_records) != configured_target:
            raise JobConfigurationError(
                "generated candidate count does not match the validated run profile"
            )
        if store.candidate_set_hash is None:
            store.bind_candidate_set(candidate_records, candidate_set_hash)
            return
        if (
            store.candidate_set_hash != candidate_set_hash
            or store.target_candidate_count != len(candidate_records)
        ):
            raise JobConfigurationError(
                "deterministic candidate set does not match durable serial job"
            )
        durable_records = tuple(
            item["candidate"]
            for item in sorted(
                store.work_items,
                key=lambda item: _sequence_index(item),
            )
        )
        if durable_records != candidate_records:
            raise JobConfigurationError(
                "durable candidate intent does not match the generated candidate set"
            )

    def start_candidate(request: CandidateExecutionRequest) -> None:
        if cancellation_check():
            raise PipelineCancellation()
        if interrupt_after is not None and store.completed_work_item_count >= interrupt_after:
            store.interrupted(
                reason=f"interrupt_after={interrupt_after}",
            )
            raise JobInterruption(job_id)
        store.start_item(request.sequence_index, request.raw_task.candidate_id)
        if interruption_hook is not None:
            try:
                interruption_hook(
                    {
                        "event_type": "work_item_started",
                        **store.item_for_sequence(request.sequence_index),
                    }
                )
            except JobInterruption:
                raise
            except Exception as exc:
                store.interrupted(reason=type(exc).__name__)
                raise

    def complete_candidate(
        request: CandidateExecutionRequest,
        outcome: ProvisionalCandidateOutcome,
    ) -> None:
        # A bounded concurrent drain may allow a worker to return after the
        # pipeline has observed cancellation. Leave that item interrupted;
        # recording a late completion would race the cancellation journal.
        if cancellation_check():
            return
        store.complete_item(
            request.sequence_index,
            outcome,
            include_episode_log=write_episode_logs,
        )
        if interruption_hook is not None:
            try:
                interruption_hook(
                    {
                        "event_type": "work_item_completed",
                        **store.item_for_sequence(request.sequence_index),
                    }
                )
            except JobInterruption:
                raise
            except Exception as exc:
                store.interrupted(reason=type(exc).__name__)
                raise

    def finish_cancellation(
        pipeline_result: PipelineResult | None = None,
    ) -> SerialJobResult:
        cancellation_controller.request()
        store.recover_inflight_provider_attempts()
        store.interrupt_running_items(reason="operator_cancelled")
        store.cancelled(pipeline_result)
        return store.result(output_dir, pipeline_result=pipeline_result)

    try:
        pipeline_result = run_foundation_pipeline(
            output_dir,
            dataset_version=run_profile.dataset_version,
            candidate_generator=effective_candidate_generator,
            candidate_generator_factory=effective_candidate_generator_factory,
            candidate_set_callback=bind_candidate_set,
            candidate_start_callback=start_candidate,
            candidate_outcome_callback=complete_candidate,
            precomputed_candidate_outcomes=completed_outcomes,
            policy_generator=policy_generator,
            parent_artifact_path=parent_artifact_path,
            route_reviewable_failures=route_reviewable_failures,
            enable_branching=run_profile.features.enable_branching,
            source_bundle=source_bundle,
            enable_source_audit=(
                run_profile.features.enable_source_governance_fixture
                or run_profile.source is not None
            ),
            domain_environment_input=domain_environment_input,
            source_events=source_events,
            enable_mcp_adapter=run_profile.features.enable_mcp_adapter,
            enable_sandbox_fixture=run_profile.features.enable_sandbox_fixture,
            seed_override=run_profile.seed,
            run_profile_metadata=(
                run_profile_metadata or run_profile.sanitized_metadata()
            ),
            run_profile=run_profile,
            write_episode_logs=write_episode_logs,
            coverage_scheduler_factory=coverage_scheduler_factory,
            coverage_recovery=coverage_recovery,
            max_concurrency=effective_max_concurrency,
            cancellation_check=cancellation_check,
        )
    except JobInterruption:
        if cancellation_controller.check():
            return finish_cancellation()
        raise
    except PipelineCancellation:
        return finish_cancellation()
    except LLMProviderError as exc:
        if cancellation_controller.check():
            return finish_cancellation()
        if getattr(exc, "ambiguous", False):
            store.interrupted(reason="provider_attempt_ambiguous")
            raise
        store.fail_running_items(error_class=type(exc).__name__)
        store.failed(error_class=type(exc).__name__)
        raise
    except Exception as exc:
        if cancellation_controller.check():
            return finish_cancellation()
        store.fail_running_items(error_class=type(exc).__name__)
        store.failed(error_class=type(exc).__name__)
        raise

    if cancellation_controller.check():
        return finish_cancellation(pipeline_result)

    if store.work_items and any(
        item["status"] != "completed" for item in store.work_items
    ):
        store.failed(error_class="incomplete_work_items")
        raise OrchestrationError(
            "pipeline returned before every serial work item reached a terminal outcome"
        )
    store.completed(pipeline_result)
    return store.result(output_dir, pipeline_result=pipeline_result)


def validate_job_record(record: Mapping[str, object]) -> None:
    """Validate a persisted versioned job record."""

    _require_exact_keys(
        record,
        {
            "schema_version",
            "job_id",
            "status",
            "config_hash",
            "execution_config_hash",
            "configuration_identity",
            "configuration_identity_hash",
            "authorization_limits",
            "output_ownership_hash",
            "dataset_version",
            "domain",
            "execution_mode",
            "max_concurrency",
            "target_candidate_count",
            "candidate_set_hash",
            "work_item_count",
            "completed_work_item_count",
            "accepted_work_item_count",
            "rejected_work_item_count",
            "accepted_count",
            "rejected_count",
            "created_at",
            "updated_at",
            "artifact_references",
        },
        "job",
    )
    if record["schema_version"] != JOB_SCHEMA_VERSION:
        raise ValueError("job.schema_version is unsupported")
    _validate_job_id(record["job_id"])
    if record["status"] not in JOB_STATUSES:
        raise ValueError("job.status is unsupported")
    if record["execution_mode"] not in JOB_EXECUTION_MODES:
        raise ValueError("job.execution_mode is unsupported")
    try:
        validate_concurrency(record["max_concurrency"])
    except ValueError as exc:
        raise ValueError(f"job.max_concurrency is invalid: {exc}") from exc
    _validate_sha256(record["config_hash"], "job.config_hash")
    _validate_sha256(
        record["execution_config_hash"],
        "job.execution_config_hash",
    )
    _validate_sha256(
        record["configuration_identity_hash"],
        "job.configuration_identity_hash",
    )
    if not isinstance(record["configuration_identity"], Mapping):
        raise ValueError("job.configuration_identity must be an object")
    if not isinstance(record["authorization_limits"], Mapping):
        raise ValueError("job.authorization_limits must be an object")
    _assert_safe_orchestration_value(record["configuration_identity"])
    _assert_safe_orchestration_value(record["authorization_limits"])
    _validate_sha256(record["output_ownership_hash"], "job.output_ownership_hash")
    for field_name in ("dataset_version", "domain", "created_at", "updated_at"):
        _require_non_empty_string(record[field_name], f"job.{field_name}")
    target = record["target_candidate_count"]
    if target is not None and (
        not isinstance(target, int)
        or isinstance(target, bool)
        or target < 0
    ):
        raise ValueError("job.target_candidate_count must be a non-negative integer or null")
    candidate_set_hash = record["candidate_set_hash"]
    if candidate_set_hash is not None:
        _validate_sha256(candidate_set_hash, "job.candidate_set_hash")
    for field_name in (
        "work_item_count",
        "completed_work_item_count",
        "accepted_work_item_count",
        "rejected_work_item_count",
        "accepted_count",
        "rejected_count",
    ):
        value = record[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"job.{field_name} must be a non-negative integer")
    if not isinstance(record["artifact_references"], Mapping):
        raise ValueError("job.artifact_references must be an object")
    _assert_safe_orchestration_value(record["artifact_references"])


def validate_work_item_record(record: Mapping[str, object]) -> None:
    """Validate a persisted versioned work-item record."""

    _require_exact_keys(
        record,
        {
            "schema_version",
            "job_id",
            "item_id",
            "sequence_index",
            "candidate_id",
            "status",
            "candidate",
            "task_contract",
            "coverage_assignment",
            "coverage_wave",
            "coverage_generation_rejection",
            "attempt_count",
            "created_at",
            "started_at",
            "completed_at",
            "result_kind",
            "outcome",
        },
        "work_item",
    )
    if record["schema_version"] != WORK_ITEM_SCHEMA_VERSION:
        raise ValueError("work_item.schema_version is unsupported")
    _validate_job_id(record["job_id"])
    sequence_index = record["sequence_index"]
    if (
        not isinstance(sequence_index, int)
        or isinstance(sequence_index, bool)
        or sequence_index < 0
    ):
        raise ValueError("work_item.sequence_index must be a non-negative integer")
    if record["item_id"] != _work_item_id(str(record["job_id"]), sequence_index):
        raise ValueError("work_item.item_id does not match job and sequence")
    _require_non_empty_string(record["candidate_id"], "work_item.candidate_id")
    if record["status"] not in WORK_ITEM_STATUSES:
        raise ValueError("work_item.status is unsupported")
    if not isinstance(record["candidate"], Mapping):
        raise ValueError("work_item.candidate must be an object")
    _assert_safe_orchestration_value(record["candidate"])
    task_contract = record["task_contract"]
    if task_contract is not None and not isinstance(task_contract, Mapping):
        raise ValueError("work_item.task_contract must be an object or null")
    if task_contract is not None:
        _assert_safe_orchestration_value(task_contract)
    coverage_assignment = record["coverage_assignment"]
    if coverage_assignment is not None:
        if not isinstance(coverage_assignment, Mapping):
            raise ValueError(
                "work_item.coverage_assignment must be an object or null"
            )
        _assert_safe_orchestration_value(coverage_assignment)
    coverage_wave = record["coverage_wave"]
    if coverage_wave is not None and (
        not isinstance(coverage_wave, int)
        or isinstance(coverage_wave, bool)
        or coverage_wave <= 0
    ):
        raise ValueError("work_item.coverage_wave must be a positive integer or null")
    generation_rejection = record["coverage_generation_rejection"]
    if generation_rejection is not None:
        if not isinstance(generation_rejection, Mapping):
            raise ValueError(
                "work_item.coverage_generation_rejection must be an object or null"
            )
        _assert_safe_orchestration_value(generation_rejection)
    if (coverage_assignment is None) != (coverage_wave is None):
        raise ValueError(
            "coverage assignment and coverage wave must be present together"
        )
    attempt_count = record["attempt_count"]
    if not isinstance(attempt_count, int) or isinstance(attempt_count, bool) or attempt_count < 0:
        raise ValueError("work_item.attempt_count must be a non-negative integer")
    for field_name in ("created_at",):
        _require_non_empty_string(record[field_name], f"work_item.{field_name}")
    for field_name in ("started_at", "completed_at"):
        value = record[field_name]
        if value is not None:
            _require_non_empty_string(value, f"work_item.{field_name}")
    result_kind = record["result_kind"]
    if result_kind is not None and result_kind not in WORK_ITEM_RESULT_KINDS:
        raise ValueError("work_item.result_kind is unsupported")
    status = record["status"]
    if status == "pending":
        if record["started_at"] is not None or record["completed_at"] is not None:
            raise ValueError("pending work_item cannot have lifecycle timestamps")
        if result_kind is not None or record["outcome"] is not None:
            raise ValueError("pending work_item cannot have a terminal outcome")
    elif status == "running":
        if attempt_count < 1 or record["started_at"] is None:
            raise ValueError("running work_item must have an issued attempt")
        if (
            record["completed_at"] is not None
            or result_kind is not None
            or record["outcome"] is not None
        ):
            raise ValueError("running work_item cannot have a terminal outcome")
    elif status == "completed":
        if attempt_count < 1 or record["started_at"] is None or record["completed_at"] is None:
            raise ValueError("completed work_item must have complete lifecycle timestamps")
        if result_kind is None or not isinstance(record["outcome"], Mapping):
            raise ValueError("completed work_item must contain result_kind and outcome")
        _validate_outcome_record_shape(record["outcome"])
        sample = record["outcome"].get("sample")
        rejection = record["outcome"].get("rejection")
        expected_kind = "accepted" if sample is not None else "rejected"
        if expected_kind != result_kind:
            raise ValueError("work_item result_kind does not match outcome")
    elif status in {"failed", "cancelled"}:
        if attempt_count < 1:
            raise ValueError(f"{status} work_item must contain an issued attempt")
        if record["started_at"] is not None:
            raise ValueError(f"{status} work_item cannot remain started")
        if record["completed_at"] is not None:
            raise ValueError(f"{status} work_item cannot have a completion timestamp")
        if result_kind is not None or record["outcome"] is not None:
            raise ValueError(f"{status} work_item cannot have a terminal outcome")


def validate_event_record(record: Mapping[str, object]) -> None:
    """Validate one append-only event record without applying transitions."""

    _require_exact_keys(
        record,
        {
            "schema_version",
            "sequence",
            "event_id",
            "job_id",
            "work_item_id",
            "event_type",
            "payload",
            "previous_integrity_hash",
            "integrity_hash",
        },
        "event",
    )
    if record["schema_version"] != EVENT_SCHEMA_VERSION:
        raise ValueError("event.schema_version is unsupported")
    sequence = record["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("event.sequence must be a non-negative integer")
    if record["event_id"] != f"event_{sequence:08d}":
        raise ValueError("event.event_id does not match event.sequence")
    _validate_job_id(record["job_id"])
    work_item_id = record["work_item_id"]
    if work_item_id is not None:
        _require_non_empty_string(work_item_id, "event.work_item_id")
    _require_non_empty_string(record["event_type"], "event.event_type")
    if not isinstance(record["payload"], Mapping):
        raise ValueError("event.payload must be an object")
    _assert_safe_orchestration_value(record["payload"])
    previous_hash = record["previous_integrity_hash"]
    if previous_hash is not None:
        _validate_sha256(previous_hash, "event.previous_integrity_hash")
    _validate_sha256(record["integrity_hash"], "event.integrity_hash")


def _validate_outcome_record_shape(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("work_item.outcome must be an object")
    sample = value.get("sample")
    rejection = value.get("rejection")
    if (sample is None) == (rejection is None):
        raise ValueError("work_item.outcome must contain exactly one sample or rejection")
    if sample is not None and not isinstance(sample, Mapping):
        raise ValueError("work_item.outcome.sample must be an object or null")
    if rejection is not None and not isinstance(rejection, Mapping):
        raise ValueError("work_item.outcome.rejection must be an object or null")
    for field_name in ("sequence_index", "candidate_id"):
        if field_name not in value:
            raise ValueError(f"work_item.outcome.{field_name} is required")
    if (
        not isinstance(value["sequence_index"], int)
        or isinstance(value["sequence_index"], bool)
        or value["sequence_index"] < 0
    ):
        raise ValueError("work_item.outcome.sequence_index must be non-negative")
    _require_non_empty_string(value["candidate_id"], "work_item.outcome.candidate_id")
    _assert_safe_orchestration_value(value)


def serial_job_lock_path(output_dir: Path, job_id: str) -> Path:
    """Return the local lock path for one job without exposing host paths."""

    _validate_job_id(job_id)
    return Path(output_dir) / "orchestration" / f".{job_id}.lock"


class _LocalJobLock:
    def __init__(
        self,
        path: Path,
        *,
        timestamp_factory: TimestampFactory,
        recover_stale_lock: bool,
        stale_state_validator: Callable[[], None] | None,
    ) -> None:
        self.path = path
        self._timestamp_factory = timestamp_factory
        self._recover_stale_lock = recover_stale_lock
        self._stale_state_validator = stale_state_validator
        self._fd: int | None = None
        self.stale_recovered = False
        self._token = secrets.token_hex(16)

    def __enter__(self) -> "_LocalJobLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def acquire(self) -> None:
        if fcntl is None:
            raise JobLockError("exclusive local job locks require a POSIX filesystem")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o600,
            )
            self._lock_fd(fd)
            self._write_metadata(fd)
            self._fd = fd
            return
        except FileExistsError:
            pass
        except Exception:
            self._close_fd(fd if "fd" in locals() else None, unlink=True)
            raise

        try:
            fd = os.open(self.path, os.O_RDWR)
        except OSError as exc:
            raise JobLockError("serial job lock disappeared during acquisition") from exc
        try:
            try:
                self._lock_fd(fd)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise JobLockError("serial job is already owned by another writer") from exc
                raise JobLockError("serial job lock cannot be acquired") from exc

            metadata = self._read_metadata(fd)
            if metadata.get("released") is not True and _lock_metadata_pid_is_alive(metadata):
                raise JobLockError("serial job lock is owned by a live writer")
            if metadata.get("released") is not True and not self._recover_stale_lock:
                raise StaleJobLockError(
                    "serial job lock is stale; pass recover_stale_lock=True explicitly"
                )
            if metadata.get("released") is not True and self._stale_state_validator is not None:
                self._stale_state_validator()
            self._write_metadata(fd, recovered=True)
            self.stale_recovered = metadata.get("released") is not True
            self._fd = fd
        except Exception:
            self._close_fd(fd, unlink=False)
            raise

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            # Keep the inode stable across release. A later writer can acquire
            # the same file description without racing an unlink/recreate gap.
            try:
                self._write_metadata(fd, released=True)
            except OSError:
                # A failed release marker leaves a conservative stale lock;
                # explicit recovery is then required on the next run.
                pass
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _lock_fd(self, fd: int) -> None:
        assert fcntl is not None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise exc

    def _write_metadata(
        self,
        fd: int,
        *,
        recovered: bool = False,
        released: bool = False,
    ) -> None:
        metadata: dict[str, object] = {
            "schema_version": LOCK_SCHEMA_VERSION,
            "pid": os.getpid(),
            "token": self._token,
            "acquired_at": self._timestamp_factory(),
            "released": released,
        }
        if recovered:
            metadata["recovered_stale_lock"] = True
        _assert_safe_orchestration_value(metadata)
        encoded = _json_bytes(metadata) + b"\n"
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, encoded)
        os.fsync(fd)

    def _read_metadata(self, fd: int) -> Mapping[str, object]:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 65536)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JobLockError("serial job lock metadata is malformed") from exc
        if not isinstance(value, Mapping):
            raise JobLockError("serial job lock metadata must be an object")
        expected = {"schema_version", "pid", "token", "acquired_at", "released"}
        if set(value) - expected - {"recovered_stale_lock"}:
            raise JobLockError("serial job lock metadata contains unsupported fields")
        if value.get("schema_version") != LOCK_SCHEMA_VERSION:
            raise JobLockError("serial job lock schema is unsupported")
        pid = value.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise JobLockError("serial job lock pid is invalid")
        _require_non_empty_string(value.get("token"), "lock.token")
        _require_non_empty_string(value.get("acquired_at"), "lock.acquired_at")
        if "released" in value and not isinstance(value["released"], bool):
            raise JobLockError("serial job lock release marker is invalid")
        return value

    def _close_fd(self, fd: int | None, *, unlink: bool) -> None:
        if fd is None:
            return
        try:
            if unlink:
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _lock_metadata_pid_is_alive(metadata: Mapping[str, object]) -> bool:
    pid = metadata["pid"]
    assert isinstance(pid, int)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class _ProviderAttemptObserver:
    """Bridge domain generation callbacks to the durable provider journal."""

    def __init__(
        self,
        store: "_LocalJobStore",
        *,
        provider_identity: Mapping[str, str] | None,
        interruption_hook: SerialJobInterruptionHook | None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> None:
        if provider_identity is None:
            raise JobConfigurationError("provider identity is required")
        self._store = store
        self._provider_identity = provider_identity
        self._interruption_hook = interruption_hook
        self._cancellation_check = cancellation_check
        self._attempt_id: str | None = None

    def before_provider_call(
        self,
        *,
        batch_context,
        requested_candidate_count: int,
        prompt_hash: str,
    ) -> None:
        if self._cancellation_check is not None and self._cancellation_check():
            raise PipelineCancellation()
        self._attempt_id = self._store.prepare_provider_attempt(
            role="task_generation",
            provider_identity=self._provider_identity,
            batch_index=batch_context.batch_index,
            requested_candidate_count=requested_candidate_count,
            prompt_hash=prompt_hash,
        )
        self._call_hook(
            {
                "event_type": "provider_attempt_intent",
                "attempt_id": self._attempt_id,
                "batch_index": batch_context.batch_index,
            }
        )
        if self._cancellation_check is not None and self._cancellation_check():
            raise PipelineCancellation()
        self._store.issue_provider_attempt(self._attempt_id)
        self._call_hook(
            {
                "event_type": "provider_attempt_issued",
                "attempt_id": self._attempt_id,
                "batch_index": batch_context.batch_index,
            }
        )

    def provider_response_received(
        self,
        *,
        batch_context,
        requested_candidate_count: int,
        lineage: Mapping[str, object],
    ) -> None:
        _ = batch_context, requested_candidate_count
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError("provider response has no durable attempt")
        self._store.complete_provider_attempt(
            self._attempt_id,
            lineage=lineage,
        )

    def provider_attempt_failed(
        self,
        *,
        batch_context,
        requested_candidate_count: int,
        error: BaseException,
    ) -> None:
        _ = batch_context, requested_candidate_count
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError("provider failure has no durable attempt")
        self._store.fail_provider_attempt(self._attempt_id, error=error)

    def validated_contracts_checkpointed(
        self,
        *,
        batch_context,
        requested_candidate_count: int,
        contracts: tuple[TaskContract, ...],
        lineage: Mapping[str, object],
    ) -> None:
        _ = requested_candidate_count, lineage
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError(
                "validated provider response has no durable attempt"
            )
        self._store.checkpoint_provider_contracts(
            self._attempt_id,
            batch_index=batch_context.batch_index,
            contracts=contracts,
        )
        self._call_hook(
            {
                "event_type": "provider_contract_checkpointed",
                "attempt_id": self._attempt_id,
                "batch_index": batch_context.batch_index,
                "contract_count": len(contracts),
            }
        )

    def _call_hook(self, event: Mapping[str, object]) -> None:
        if self._interruption_hook is not None:
            self._interruption_hook(event)


class _CoverageProviderAttemptObserver:
    """Journal one provider call for one durable coverage assignment."""

    def __init__(
        self,
        store: "_LocalJobStore",
        *,
        assignment: CoverageAssignment,
        provider_identity: Mapping[str, str] | None,
        interruption_hook: SerialJobInterruptionHook | None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> None:
        if provider_identity is None:
            raise JobConfigurationError("coverage provider identity is required")
        self._store = store
        self._assignment = assignment
        self._provider_identity = provider_identity
        self._interruption_hook = interruption_hook
        self._cancellation_check = cancellation_check
        self._attempt_id: str | None = None

    def before_provider_call(
        self,
        *,
        assignment: CoverageAssignment,
        batch_context: object,
        requested_candidate_count: int,
        prompt_hash: str,
    ) -> None:
        _ = assignment, batch_context
        if self._cancellation_check is not None and self._cancellation_check():
            raise PipelineCancellation()
        self._attempt_id = self._store.prepare_provider_attempt(
            role="task_generation",
            provider_identity=self._provider_identity,
            batch_index=self._assignment.assignment_ordinal + 1,
            requested_candidate_count=requested_candidate_count,
            prompt_hash=prompt_hash,
        )
        self._call_hook(
            {
                "event_type": "provider_attempt_intent",
                "attempt_id": self._attempt_id,
                "batch_index": self._assignment.assignment_ordinal + 1,
                "coverage_assignment_id": self._assignment.assignment_id,
            }
        )
        if self._cancellation_check is not None and self._cancellation_check():
            raise PipelineCancellation()
        self._store.issue_provider_attempt(self._attempt_id)
        self._call_hook(
            {
                "event_type": "provider_attempt_issued",
                "attempt_id": self._attempt_id,
                "batch_index": self._assignment.assignment_ordinal + 1,
                "coverage_assignment_id": self._assignment.assignment_id,
            }
        )

    def provider_response_received(
        self,
        *,
        assignment: CoverageAssignment,
        batch_context: object,
        requested_candidate_count: int,
        lineage: Mapping[str, object],
    ) -> None:
        _ = assignment, batch_context, requested_candidate_count
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError(
                "coverage provider response has no durable attempt"
            )
        self._store.complete_provider_attempt(
            self._attempt_id,
            lineage=lineage,
        )

    def provider_attempt_failed(
        self,
        *,
        assignment: CoverageAssignment,
        batch_context: object,
        requested_candidate_count: int,
        error: BaseException,
    ) -> None:
        _ = assignment, batch_context, requested_candidate_count
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError(
                "coverage provider failure has no durable attempt"
            )
        self._store.fail_provider_attempt(self._attempt_id, error=error)

    def validated_contracts_checkpointed(
        self,
        *,
        assignment: CoverageAssignment,
        batch_context: object,
        requested_candidate_count: int,
        contracts: tuple[TaskContract, ...],
        lineage: Mapping[str, object],
    ) -> None:
        _ = assignment, batch_context, requested_candidate_count, lineage
        if self._cancellation_check is not None and self._cancellation_check():
            return
        if self._attempt_id is None:
            raise InvalidTransitionError(
                "coverage checkpoint has no durable attempt"
            )
        self._store.checkpoint_provider_contracts(
            self._attempt_id,
            batch_index=self._assignment.assignment_ordinal + 1,
            contracts=contracts,
        )
        self._call_hook(
            {
                "event_type": "provider_contract_checkpointed",
                "attempt_id": self._attempt_id,
                "batch_index": self._assignment.assignment_ordinal + 1,
                "coverage_assignment_id": self._assignment.assignment_id,
            }
        )
        if len(contracts) != 1:
            raise InvalidTransitionError(
                "coverage provider checkpoint must contain one contract"
            )
        candidate = candidate_from_task_contract(contracts[0])
        self._store.bind_coverage_candidate(
            self._assignment.assignment_ordinal,
            candidate,
        )
        self._call_hook(
            {
                "event_type": "coverage_candidate_bound",
                "coverage_assignment_id": self._assignment.assignment_id,
                "sequence_index": self._assignment.assignment_ordinal,
            }
        )

    def _call_hook(self, event: Mapping[str, object]) -> None:
        if self._interruption_hook is not None:
            self._interruption_hook(event)


def _coverage_recovery_from_store(
    store: "_LocalJobStore",
) -> tuple[CoverageAssignmentRecovery, ...]:
    recoveries: list[CoverageAssignmentRecovery] = []
    for item in store.work_items:
        assignment_record = item.get("coverage_assignment")
        wave = item.get("coverage_wave")
        if not isinstance(assignment_record, Mapping) or not isinstance(wave, int):
            raise JournalCorruptionError(
                "coverage job contains an invalid durable assignment"
            )
        try:
            assignment = CoverageAssignment.from_durable_record(assignment_record)
        except (TypeError, ValueError) as exc:
            raise JournalCorruptionError(
                "coverage assignment recovery state is malformed"
            ) from exc
        candidate_record = item.get("candidate")
        candidate: CandidateTask | None = None
        if isinstance(candidate_record, Mapping) and candidate_record.get(
            "schema_version"
        ) != INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
            try:
                candidate = _candidate_from_record(candidate_record)
            except (TypeError, ValueError) as exc:
                raise JournalCorruptionError(
                    "coverage candidate recovery state is malformed"
                ) from exc
        outcome = None
        if item["status"] == "completed":
            outcome_value = item.get("outcome")
            if outcome_value is None:
                raise JournalCorruptionError(
                    "completed coverage item has no durable outcome"
                )
            outcome = _outcome_from_record(outcome_value)
        generation_rejection = item.get("coverage_generation_rejection")
        if generation_rejection is not None and not isinstance(
            generation_rejection,
            Mapping,
        ):
            raise JournalCorruptionError(
                "coverage generation rejection state is malformed"
            )
        recoveries.append(
            CoverageAssignmentRecovery(
                assignment=assignment,
                wave=wave,
                candidate=candidate,
                generation_rejection=(
                    dict(generation_rejection)
                    if isinstance(generation_rejection, Mapping)
                    else None
                ),
                outcome=outcome,
            )
        )
    return tuple(recoveries)


class _LocalJobStore:
    def __init__(
        self,
        orchestration_dir: Path,
        *,
        timestamp_factory: TimestampFactory,
    ) -> None:
        self.orchestration_dir = orchestration_dir
        self.job_path = orchestration_dir / "job.json"
        self.work_items_path = orchestration_dir / "work_items.jsonl"
        self.events_path = orchestration_dir / "events.jsonl"
        self.provider_usage_path = orchestration_dir / "provider_usage.json"
        self._timestamp_factory = timestamp_factory
        self._job: dict[str, object] | None = None
        self._items: dict[str, dict[str, object]] = {}
        self._events: list[dict[str, object]] = []
        self._provider_attempts: dict[str, dict[str, object]] = {}
        self._provider_checkpoints: list[dict[str, object]] = []
        self._mutex = threading.RLock()
        self._last_integrity_hash: str | None = None
        self._recovered_tail_bytes = 0
        self._recovered_tail_prefix: bytes | None = None
        self._snapshots_need_rebuild = False
        self._loaded = False

    @property
    def exists(self) -> bool:
        return self.orchestration_dir.exists()

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def job(self) -> dict[str, object]:
        if self._job is None:
            raise OrchestrationError("serial job store is not loaded")
        return self._job

    @property
    def work_items(self) -> tuple[dict[str, object], ...]:
        with self._mutex:
            return tuple(
                self._items[item_id]
                for item_id in sorted(
                    self._items,
                    key=lambda key: _sequence_index(self._items[key]),
                )
            )

    @property
    def status(self) -> str:
        return str(self.job["status"])

    @property
    def max_concurrency(self) -> int:
        try:
            return validate_concurrency(
                self.job["max_concurrency"],
                field_name="job.max_concurrency",
            )
        except ValueError as exc:
            raise JournalCorruptionError(
                "durable job concurrency bound is invalid"
            ) from exc

    @property
    def candidate_set_hash(self) -> str | None:
        value = self.job["candidate_set_hash"]
        return str(value) if value is not None else None

    @property
    def target_candidate_count(self) -> int | None:
        value = self.job["target_candidate_count"]
        return _integer_value(value, "job.target_candidate_count") if value is not None else None

    @property
    def completed_work_item_count(self) -> int:
        return _integer_value(
            self.job["completed_work_item_count"],
            "job.completed_work_item_count",
        )

    @property
    def provider_attempts(self) -> tuple[dict[str, object], ...]:
        with self._mutex:
            return tuple(
                dict(self._provider_attempts[attempt_id])
                for attempt_id in sorted(
                    self._provider_attempts,
                    key=lambda attempt_id: _integer_value(
                        self._provider_attempts[attempt_id]["attempt_sequence"],
                        "provider_attempt.attempt_sequence",
                    ),
                )
            )

    @property
    def provider_checkpoint_contracts(self) -> tuple[TaskContract, ...]:
        contracts: list[TaskContract] = []
        for checkpoint in self._provider_checkpoints:
            records = checkpoint["contracts"]
            if not isinstance(records, list):
                raise JournalCorruptionError(
                    "provider contract checkpoint records are malformed"
                )
            for record in records:
                if not isinstance(record, Mapping):
                    raise JournalCorruptionError(
                        "provider contract checkpoint item is malformed"
                    )
                try:
                    contracts.append(_task_contract_from_record(record))
                except (KeyError, TypeError, ValueError) as exc:
                    raise JournalCorruptionError(
                        "provider contract checkpoint item is invalid"
                    ) from exc
        return tuple(contracts)

    def provider_checkpoint_for_batch(
        self,
        batch_index: int,
    ) -> tuple[Mapping[str, object], ...] | None:
        matches = [
            checkpoint
            for checkpoint in self._provider_checkpoints
            if checkpoint["batch_index"] == batch_index
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise JournalCorruptionError(
                "provider checkpoint batch identity is duplicated"
            )
        contracts = matches[0].get("contracts")
        if not isinstance(contracts, list) or not all(
            isinstance(contract, Mapping) for contract in contracts
        ):
            raise JournalCorruptionError(
                "provider checkpoint contracts are malformed"
            )
        return tuple(dict(contract) for contract in contracts)

    @property
    def next_provider_batch_index(self) -> int:
        checkpoint_batches = [
            _integer_value(item["batch_index"], "provider_checkpoint.batch_index")
            for item in self._provider_checkpoints
        ]
        unfinished_batches = [
            _integer_value(item["batch_index"], "provider_attempt.batch_index")
            for item in self.provider_attempts
            if item["status"] not in {"checkpointed"}
        ]
        if unfinished_batches:
            return max(1, max(unfinished_batches))
        if checkpoint_batches:
            return max(checkpoint_batches) + 1
        return 1

    @property
    def issued_logical_call_count(self) -> int:
        return sum(
            attempt["status"] != "intent"
            for attempt in self.provider_attempts
        )

    @property
    def provider_usage(self) -> dict[str, object]:
        identity = _provider_identity_from_job(self.job)
        budget = _logical_call_budget_from_limits(
            self.job.get("authorization_limits"),
            required=False,
        )
        attempts = []
        retry_count = 0
        for attempt in self.provider_attempts:
            summary = {
                "schema_version": PROVIDER_ATTEMPT_SCHEMA_VERSION,
                "attempt_id": attempt["attempt_id"],
                "attempt_sequence": attempt["attempt_sequence"],
                "role": attempt["role"],
                "provider_alias": attempt["provider_alias"],
                "model_alias": attempt["model_alias"],
                "batch_index": attempt["batch_index"],
                "status": attempt["status"],
                "issued": attempt["status"] != "intent",
                "logical_call_number": attempt.get("logical_call_number"),
                "retry_count": attempt.get("retry_count", 0),
                "token_usage": _json_copy(attempt.get("token_usage", {})),
                "price_metadata": _json_copy(attempt.get("price_metadata")),
            }
            if attempt.get("error_class") is not None:
                summary["error_class"] = attempt["error_class"]
            if attempt.get("cause") is not None:
                summary["cause"] = attempt["cause"]
            attempts.append(summary)
            retry_count += _integer_value(
                attempt.get("retry_count", 0),
                "provider_attempt.retry_count",
            )
        usage: dict[str, object] = {
            "schema_version": PROVIDER_USAGE_SCHEMA_VERSION,
            "provider_alias": identity.get("provider_alias") if identity else None,
            "model_alias": identity.get("model_alias") if identity else None,
            "logical_call_budget": budget,
            "issued_logical_calls": self.issued_logical_call_count,
            "known_attempts": sum(
                attempt["status"] in {"known", "failed", "checkpointed"}
                for attempt in self.provider_attempts
            ),
            "ambiguous_attempts": sum(
                attempt["status"] == "ambiguous"
                for attempt in self.provider_attempts
            ),
            "transport_retry_count": retry_count,
            "attempts": attempts,
        }
        _assert_safe_orchestration_value(usage)
        return usage

    def create(
        self,
        *,
        job_id: str,
        run_profile: RunProfile,
        execution_config_hash: str,
        output_dir: Path,
        authorization_limits: Mapping[str, object],
        provider_identity: Mapping[str, str] | None,
        max_concurrency: int,
    ) -> None:
        self.orchestration_dir.mkdir(parents=True, exist_ok=False)
        initial_job: dict[str, object] = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "status": "pending",
            "config_hash": run_profile.config_hash,
            "execution_config_hash": execution_config_hash,
            "configuration_identity": _normalized_configuration_identity(
                run_profile,
                authorization_limits,
                provider_identity=provider_identity,
                max_concurrency=max_concurrency,
            ),
            "configuration_identity_hash": _configuration_identity_hash(
                run_profile,
                authorization_limits,
                provider_identity=provider_identity,
                max_concurrency=max_concurrency,
            ),
            "authorization_limits": _json_copy(authorization_limits),
            "output_ownership_hash": _output_ownership_hash(output_dir, job_id),
            "dataset_version": run_profile.dataset_version,
            "domain": run_profile.seed.domain,
            "execution_mode": (
                "coverage"
                if run_profile.coverage_profile is not None
                else "candidate_set"
            ),
            "max_concurrency": validate_concurrency(max_concurrency),
            "target_candidate_count": run_profile.generation.target_candidate_count,
            "candidate_set_hash": None,
            "work_item_count": 0,
            "completed_work_item_count": 0,
            "accepted_work_item_count": 0,
            "rejected_work_item_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "created_at": self._timestamp_factory(),
            "updated_at": self._timestamp_factory(),
            "artifact_references": {},
        }
        validate_job_record(initial_job)
        self._append("job_created", initial_job)
        self._append("job_started", {})
        self._loaded = True

    def load(self, *, repair_tail: bool = True) -> None:
        if self._loaded:
            return
        if not self.events_path.exists():
            raise JournalCorruptionError("serial job is missing its event journal")
        self._replay_events()
        if self._job is None:
            raise JournalCorruptionError("serial job journal has no job_created event")
        validate_job_record(self._job)
        for item in self.work_items:
            validate_work_item_record(item)
        self._validate_reconstructed_state()
        self._validate_snapshots()
        self._loaded = True
        if repair_tail:
            self.rebuild_snapshots()
            self.repair_journal_tail()

    def rebuild_snapshots(self) -> None:
        if not self._snapshots_need_rebuild:
            return
        self._write_snapshots()
        self._snapshots_need_rebuild = False

    def repair_journal_tail(self) -> None:
        if not self._recovered_tail_bytes:
            return
        if self._recovered_tail_prefix is None:
            raise JournalCorruptionError("serial job journal recovery prefix is unavailable")
        with self.events_path.open("wb") as handle:
            handle.write(self._recovered_tail_prefix)
            handle.flush()
            os.fsync(handle.fileno())
        discarded_bytes = self._recovered_tail_bytes
        self._recovered_tail_bytes = 0
        self._recovered_tail_prefix = None
        self._append(
            "journal_tail_recovered",
            {"discarded_bytes": discarded_bytes},
        )

    def lock_recovered(self) -> None:
        self._append("job_lock_recovered", {"recovered_stale_lock": True})

    def validate_configuration(
        self,
        run_profile: RunProfile,
        execution_config_hash: str,
    ) -> None:
        if self.job["config_hash"] != run_profile.config_hash:
            raise JobConfigurationError(
                "run profile configuration hash does not match durable serial job"
            )
        if self.job["dataset_version"] != run_profile.dataset_version:
            raise JobConfigurationError(
                "dataset version does not match durable serial job"
            )
        if self.job["domain"] != run_profile.seed.domain:
            raise JobConfigurationError("run profile domain does not match durable serial job")
        if self.job["execution_config_hash"] != execution_config_hash:
            raise JobConfigurationError(
                "serial execution inputs do not match durable serial job"
            )

    def validate_configuration_identity(
        self,
        run_profile: RunProfile,
        authorization_limits: Mapping[str, object],
        *,
        output_dir: Path,
        provider_identity: Mapping[str, str] | None,
        max_concurrency: int,
    ) -> None:
        if self.job["job_id"] != self.orchestration_dir.name:
            raise JobConfigurationError("durable job identity does not match its directory")
        if self.job["config_hash"] != run_profile.config_hash:
            raise JobConfigurationError(
                "run profile configuration hash does not match durable serial job"
            )
        if self.job["dataset_version"] != run_profile.dataset_version:
            raise JobConfigurationError(
                "dataset version does not match durable serial job"
            )
        if self.job["domain"] != run_profile.seed.domain:
            raise JobConfigurationError("run profile domain does not match durable serial job")
        expected_identity = _normalized_configuration_identity(
            run_profile,
            authorization_limits,
            provider_identity=provider_identity,
            max_concurrency=max_concurrency,
        )
        expected_hash = _hash_json(expected_identity)
        if self.job["configuration_identity_hash"] != expected_hash:
            raise JobConfigurationError(
                "normalized configuration identity does not match durable serial job"
            )
        if self.job["configuration_identity"] != expected_identity:
            raise JobConfigurationError(
                "durable normalized configuration identity is inconsistent"
            )
        if self.job["authorization_limits"] != dict(authorization_limits):
            raise JobConfigurationError(
                "declared authorization limits do not match durable serial job"
            )
        if self.job["output_ownership_hash"] != _output_ownership_hash(
            output_dir,
            str(self.job["job_id"]),
        ):
            raise JobConfigurationError(
                "serial job output ownership does not match durable state"
            )

    def resume(self) -> None:
        if self.status not in {"running", "cancelling", "cancelled", "failed"}:
            raise InvalidTransitionError(
                "only a running, cancelling, cancelled, or failed serial job can be resumed"
            )
        self._append("job_resumed", {})
        self.recover_inflight_provider_attempts()
        for item in self.work_items:
            if item["status"] in {"running", "cancelled", "failed"}:
                self._append(
                    "work_item_requeued",
                    {
                        "reason": (
                            "failed"
                            if item["status"] == "failed"
                            else "interrupted"
                        )
                    },
                    work_item_id=str(item["item_id"]),
                )

    def request_cancellation(self, *, reason: str) -> None:
        if self._job is None or self.status in {"cancelling", "cancelled"}:
            return
        if self.status != "running":
            return
        self._append(
            "job_cancelling",
            {"reason": _safe_error_class(reason)},
        )

    def interrupt_running_items(self, *, reason: str) -> None:
        for item in self.work_items:
            if item["status"] != "running":
                continue
            self._append(
                "work_item_interrupted",
                {"reason": _safe_error_class(reason)},
                work_item_id=str(item["item_id"]),
            )

    def fail_running_items(self, *, error_class: str) -> None:
        for item in self.work_items:
            if item["status"] != "running":
                continue
            self._append(
                "work_item_failed",
                {"error_class": _safe_error_class(error_class)},
                work_item_id=str(item["item_id"]),
            )

    def cancelled(self, pipeline_result: PipelineResult | None) -> None:
        if self.status == "cancelled":
            return
        if self.status != "cancelling":
            raise InvalidTransitionError(
                "only a cancelling serial job can become cancelled"
            )
        if any(item["status"] == "running" for item in self.work_items):
            raise InvalidTransitionError(
                "running work items must be settled before job cancellation"
            )
        references = (
            _pipeline_result_references(pipeline_result)
            if pipeline_result is not None
            else {}
        )
        accepted_count = (
            pipeline_result.accepted_count
            if pipeline_result is not None
            else self.job["accepted_work_item_count"]
        )
        rejected_count = (
            pipeline_result.rejected_count
            if pipeline_result is not None
            else self.job["rejected_work_item_count"]
        )
        self._append(
            "job_cancelled",
            {
                "artifact_references": references,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
            },
        )

    def recover_coverage_provider_checkpoints(self) -> None:
        for item in self.work_items:
            assignment_record = item.get("coverage_assignment")
            candidate_record = item.get("candidate")
            if (
                assignment_record is None
                or item["status"] not in {"pending", "running"}
                or not isinstance(candidate_record, Mapping)
                or candidate_record.get("schema_version")
                != INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION
            ):
                continue
            if not isinstance(assignment_record, Mapping):
                raise JournalCorruptionError(
                    "coverage assignment checkpoint is malformed"
                )
            try:
                assignment = CoverageAssignment.from_durable_record(
                    assignment_record
                )
            except (TypeError, ValueError) as exc:
                raise JournalCorruptionError(
                    "coverage assignment checkpoint is malformed"
                ) from exc
            checkpoint_records = self.provider_checkpoint_for_batch(
                assignment.assignment_ordinal + 1
            )
            if checkpoint_records is None:
                continue
            if len(checkpoint_records) != 1:
                raise JournalCorruptionError(
                    "coverage provider checkpoint must contain one contract"
                )
            try:
                candidate = candidate_from_task_contract(
                    _task_contract_from_record(checkpoint_records[0])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise JournalCorruptionError(
                    "coverage provider checkpoint contract is malformed"
                ) from exc
            self.bind_coverage_candidate(
                assignment.assignment_ordinal,
                candidate,
            )

    def recover_coverage_generation_rejections(
        self,
        *,
        include_episode_log: bool,
    ) -> None:
        for item in self.work_items:
            rejection = item.get("coverage_generation_rejection")
            assignment_record = item.get("coverage_assignment")
            if (
                rejection is None
                or assignment_record is None
                or item["status"] == "completed"
            ):
                continue
            if not isinstance(assignment_record, Mapping) or not isinstance(
                rejection,
                Mapping,
            ):
                raise JournalCorruptionError(
                    "coverage generation rejection recovery state is malformed"
                )
            try:
                assignment = CoverageAssignment.from_durable_record(
                    assignment_record
                )
            except (TypeError, ValueError) as exc:
                raise JournalCorruptionError(
                    "coverage generation rejection assignment is malformed"
                ) from exc
            self.start_item(
                assignment.assignment_ordinal,
                assignment.assignment_id,
            )
            candidate_id = rejection.get("candidate_id")
            outcome = ProvisionalCandidateOutcome(
                sequence_index=assignment.assignment_ordinal,
                candidate_id=(
                    str(candidate_id)
                    if isinstance(candidate_id, str)
                    else "generation_stage"
                ),
                rejection=dict(rejection),
            )
            self.complete_item(
                assignment.assignment_ordinal,
                outcome,
                include_episode_log=include_episode_log,
            )

    def recover_inflight_provider_attempts(self) -> None:
        for attempt in self.provider_attempts:
            if attempt["status"] != "issued":
                continue
            self._append(
                "provider_attempt_ambiguous",
                {
                    "attempt_id": attempt["attempt_id"],
                    "reason": "process_interrupted_after_issue",
                    "error_class": "ProviderResponseLost",
                },
            )

    def prepare_provider_attempt(
        self,
        *,
        role: str,
        provider_identity: Mapping[str, str],
        batch_index: int,
        requested_candidate_count: int,
        prompt_hash: str,
    ) -> str:
        with self._mutex:
            self._ensure_provider_budget()
            for attempt in self.provider_attempts:
                if (
                    attempt["status"] == "intent"
                    and attempt["role"] == role
                    and attempt["batch_index"] == batch_index
                    and attempt["requested_candidate_count"]
                    == requested_candidate_count
                ):
                    if attempt["prompt_hash"] != prompt_hash:
                        raise JobConfigurationError(
                            "provider attempt prompt identity does not match durable intent"
                        )
                    return str(attempt["attempt_id"])
            attempt_sequence = max(
                [
                    _integer_value(
                        attempt["attempt_sequence"],
                        "provider_attempt.attempt_sequence",
                    )
                    for attempt in self.provider_attempts
                ],
                default=0,
            ) + 1
            attempt_id = _provider_attempt_id(
                str(self.job["job_id"]),
                attempt_sequence,
            )
            self._append(
                "provider_work_intent",
                {
                    "attempt_id": attempt_id,
                    "attempt_sequence": attempt_sequence,
                    "role": role,
                    "provider_alias": provider_identity["provider_alias"],
                    "model_alias": provider_identity["model_alias"],
                    "batch_index": batch_index,
                    "requested_candidate_count": requested_candidate_count,
                    "prompt_hash": prompt_hash,
                },
            )
            return attempt_id

    def issue_provider_attempt(self, attempt_id: str) -> None:
        with self._mutex:
            attempt = self._provider_attempt(attempt_id)
            if attempt["status"] != "intent":
                raise InvalidTransitionError(
                    "provider attempt is not waiting to be issued"
                )
            self._ensure_provider_budget()
            self._append(
                "provider_attempt_issued",
                {
                    "attempt_id": attempt_id,
                    "logical_call_number": self.issued_logical_call_count + 1,
                },
            )

    def complete_provider_attempt(
        self,
        attempt_id: str,
        *,
        lineage: Mapping[str, object],
    ) -> None:
        attempt = self._provider_attempt(attempt_id)
        if attempt["status"] != "issued":
            raise InvalidTransitionError(
                "only an issued provider attempt can receive a response"
            )
        sanitized = _sanitize_provider_lineage(lineage)
        self._append(
            "provider_attempt_known",
            {
                "attempt_id": attempt_id,
                "retry_count": sanitized["retry_count"],
                "token_usage": sanitized["token_usage"],
                "price_metadata": sanitized["price_metadata"],
            },
        )

    def fail_provider_attempt(
        self,
        attempt_id: str,
        *,
        error: BaseException,
    ) -> None:
        attempt = self._provider_attempt(attempt_id)
        if attempt["status"] != "issued":
            raise InvalidTransitionError(
                "only an issued provider attempt can fail"
            )
        if bool(getattr(error, "ambiguous", False)):
            self._append(
                "provider_attempt_ambiguous",
                {
                    "attempt_id": attempt_id,
                    "reason": "provider_accepted_response_lost",
                    "error_class": _safe_error_class(type(error).__name__),
                },
            )
            return
        lineage = _sanitize_provider_lineage(
            getattr(error, "lineage", {})
            if isinstance(getattr(error, "lineage", {}), Mapping)
            else {}
        )
        self._append(
            "provider_attempt_failed",
            {
                "attempt_id": attempt_id,
                "cause": _safe_error_class(str(getattr(error, "cause", "provider_error"))),
                "error_class": _safe_error_class(type(error).__name__),
                "retry_count": _safe_retry_count(getattr(error, "retry_count", 0)),
                "token_usage": lineage["token_usage"],
                "price_metadata": lineage["price_metadata"],
            },
        )

    def checkpoint_provider_contracts(
        self,
        attempt_id: str,
        *,
        batch_index: int,
        contracts: tuple[TaskContract, ...],
    ) -> None:
        attempt = self._provider_attempt(attempt_id)
        if attempt["status"] != "known":
            raise InvalidTransitionError(
                "only a known provider response can be checkpointed"
            )
        records = [_task_contract_to_record(contract) for contract in contracts]
        if not records:
            raise InvalidTransitionError(
                "provider contract checkpoint must contain at least one contract"
            )
        self._append(
            "provider_contract_checkpointed",
            {
                "attempt_id": attempt_id,
                "batch_index": batch_index,
                "contracts": records,
            },
        )

    def bind_candidate_set(
        self,
        candidate_records: tuple[dict[str, object], ...],
        candidate_set_hash: str,
    ) -> None:
        if self.candidate_set_hash is not None:
            raise InvalidTransitionError("candidate set is already bound")
        self._append(
            "candidate_set_bound",
            {
                "candidate_set_hash": candidate_set_hash,
                "target_candidate_count": len(candidate_records),
            },
        )
        for sequence_index, candidate in enumerate(candidate_records):
            candidate_id = _work_item_candidate_id(
                candidate.get("candidate_id"),
                sequence_index,
            )
            item_id = _work_item_id(str(self.job["job_id"]), sequence_index)
            work_item = {
                "schema_version": WORK_ITEM_SCHEMA_VERSION,
                "job_id": self.job["job_id"],
                "item_id": item_id,
                "sequence_index": sequence_index,
                "candidate_id": candidate_id,
                "status": "pending",
                "candidate": candidate,
                "task_contract": _task_contract_checkpoint_from_record(candidate),
                "coverage_assignment": None,
                "coverage_wave": None,
                "coverage_generation_rejection": None,
                "attempt_count": 0,
                "created_at": self._timestamp_factory(),
                "started_at": None,
                "completed_at": None,
                "result_kind": None,
                "outcome": None,
            }
            validate_work_item_record(work_item)
            self._append(
                "work_item_created",
                work_item,
                work_item_id=item_id,
            )

    def create_coverage_item(
        self,
        assignment: CoverageAssignment,
        *,
        wave: int,
    ) -> None:
        sequence_index = assignment.assignment_ordinal
        item_id = _work_item_id(str(self.job["job_id"]), sequence_index)
        candidate_id = _work_item_candidate_id(
            assignment.assignment_id,
            sequence_index,
        )
        candidate = {
            "schema_version": INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION,
            "candidate_id": candidate_id,
        }
        work_item = {
            "schema_version": WORK_ITEM_SCHEMA_VERSION,
            "job_id": self.job["job_id"],
            "item_id": item_id,
            "sequence_index": sequence_index,
            "candidate_id": candidate_id,
            "status": "pending",
            "candidate": candidate,
            "task_contract": None,
            "coverage_assignment": assignment.durable_record(),
            "coverage_wave": wave,
            "coverage_generation_rejection": None,
            "attempt_count": 0,
            "created_at": self._timestamp_factory(),
            "started_at": None,
            "completed_at": None,
            "result_kind": None,
            "outcome": None,
        }
        validate_work_item_record(work_item)
        self._append(
            "work_item_created",
            work_item,
            work_item_id=item_id,
        )

    def bind_coverage_candidate(
        self,
        sequence_index: int,
        candidate: CandidateTask,
    ) -> None:
        item = self._item_for_sequence(sequence_index)
        if item["coverage_assignment"] is None:
            raise InvalidTransitionError(
                "work item is not a coverage assignment"
            )
        if item["status"] not in {"pending", "running"}:
            raise InvalidTransitionError(
                "coverage candidate cannot be bound after completion"
            )
        candidate_record = _candidate_to_record(candidate)
        if candidate_record.get("schema_version") != CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
            raise InvalidTransitionError(
                "coverage candidate checkpoint is invalid"
            )
        self._append(
            "coverage_candidate_bound",
            {
                "candidate": candidate_record,
                "task_contract": _task_contract_checkpoint_from_record(
                    candidate_record
                ),
            },
            work_item_id=str(item["item_id"]),
        )

    def record_coverage_generation_rejection(
        self,
        sequence_index: int,
        rejection: Mapping[str, object],
    ) -> None:
        item = self._item_for_sequence(sequence_index)
        if item["coverage_assignment"] is None:
            raise InvalidTransitionError(
                "work item is not a coverage assignment"
            )
        self._append(
            "coverage_generation_rejected",
            {"rejection": dict(rejection)},
            work_item_id=str(item["item_id"]),
        )

    def start_item(self, sequence_index: int, candidate_id: str) -> None:
        item = self._item_for_sequence(sequence_index)
        if item["candidate_id"] != _work_item_candidate_id(
            candidate_id,
            sequence_index,
        ):
            raise InvalidTransitionError(
                f"candidate identity mismatch at sequence index {sequence_index}"
            )
        self._append(
            "work_item_started",
            {},
            work_item_id=str(item["item_id"]),
        )

    def complete_item(
        self,
        sequence_index: int,
        outcome: ProvisionalCandidateOutcome,
        *,
        include_episode_log: bool,
    ) -> None:
        item = self._item_for_sequence(sequence_index)
        if item["status"] != "running":
            raise InvalidTransitionError(
                f"work item {item['item_id']} is not running"
            )
        outcome_record = _outcome_to_record(
            outcome,
            include_episode_log=include_episode_log,
        )
        result_kind = "accepted" if outcome.sample is not None else "rejected"
        self._append(
            "work_item_completed",
            {
                "result_kind": result_kind,
                "outcome": outcome_record,
            },
            work_item_id=str(item["item_id"]),
        )

    def interrupted(self, *, reason: str) -> None:
        if self.status == "running":
            self._append("job_interrupted", {"reason": reason})

    def failed(self, *, error_class: str) -> None:
        if self._job is None or self.status in {"completed", "failed"}:
            return
        self._append(
            "job_failed",
            {"error_class": _safe_error_class(error_class)},
        )

    def completed(self, pipeline_result: PipelineResult) -> None:
        if self.status != "running":
            raise InvalidTransitionError("only a running serial job can complete")
        if any(item["status"] != "completed" for item in self.work_items):
            raise InvalidTransitionError("all work items must complete before job completion")
        self._append(
            "job_completed",
            {
                "artifact_references": _pipeline_result_references(pipeline_result),
                "accepted_count": pipeline_result.accepted_count,
                "rejected_count": pipeline_result.rejected_count,
            },
        )

    def item_for_sequence(self, sequence_index: int) -> Mapping[str, object]:
        return dict(self._item_for_sequence(sequence_index))

    def result(
        self,
        output_dir: Path,
        *,
        pipeline_result: PipelineResult | None = None,
    ) -> SerialJobResult:
        if (
            pipeline_result is None
            and self.status in {"completed", "cancelled"}
            and self.job["artifact_references"]
        ):
            pipeline_result = _pipeline_result_from_references(
                output_dir,
                self.job["artifact_references"],
                accepted_count=self.job["accepted_count"]
                if "accepted_count" in self.job
                else self.job["accepted_work_item_count"],
                rejected_count=self.job["rejected_count"]
                if "rejected_count" in self.job
                else self.job["rejected_work_item_count"],
            )
        return SerialJobResult(
            job_record=dict(self.job),
            work_items=tuple(dict(item) for item in self.work_items),
            pipeline_result=pipeline_result,
            orchestration_dir=self.orchestration_dir,
            job_path=self.job_path,
            work_items_path=self.work_items_path,
            events_path=self.events_path,
            provider_usage_path=(
                self.provider_usage_path if self._provider_attempts else None
            ),
            provider_attempts=self.provider_attempts,
            provider_usage=self.provider_usage,
        )

    def _item_for_sequence(self, sequence_index: int) -> dict[str, object]:
        for item in self.work_items:
            if item["sequence_index"] == sequence_index:
                return item
        raise InvalidTransitionError(
            f"serial job has no work item at sequence index {sequence_index}"
        )

    def _provider_attempt(self, attempt_id: str) -> dict[str, object]:
        try:
            return self._provider_attempts[attempt_id]
        except KeyError as exc:
            raise InvalidTransitionError(
                "provider event references an unknown attempt"
            ) from exc

    def _ensure_provider_budget(self) -> None:
        budget = _logical_call_budget_from_limits(
            self.job.get("authorization_limits"),
            required=True,
        )
        assert budget is not None
        if self.issued_logical_call_count >= budget:
            raise LogicalCallBudgetExceeded(
                "cumulative logical-call authorization is exhausted"
            )

    def _append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        work_item_id: str | None = None,
    ) -> None:
        with self._mutex:
            self._append_unlocked(
                event_type,
                payload,
                work_item_id=work_item_id,
            )

    def _append_unlocked(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        work_item_id: str | None = None,
    ) -> None:
        _assert_safe_orchestration_value(payload)
        sequence = len(self._events)
        event_job_id = str(payload.get("job_id", self._job["job_id"] if self._job else ""))
        if self._job is not None and event_job_id != self._job["job_id"]:
            raise InvalidTransitionError("event job identity does not match durable job")
        event_without_integrity: dict[str, object] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "sequence": sequence,
            "event_id": f"event_{sequence:08d}",
            "job_id": event_job_id,
            "work_item_id": work_item_id,
            "event_type": event_type,
            "payload": _json_copy(dict(payload)),
            "previous_integrity_hash": self._last_integrity_hash,
        }
        integrity_hash = _hash_json(event_without_integrity)
        event = {
            **event_without_integrity,
            "integrity_hash": integrity_hash,
        }
        validate_event_record(event)
        self._append_event_bytes(event)
        self._events.append(event)
        self._last_integrity_hash = integrity_hash
        self._apply_event(event)
        self._write_snapshots()

    def _append_event_bytes(self, event: Mapping[str, object]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a+b") as handle:
            if handle.tell() > 0:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    handle.write(b"\n")
            handle.seek(0, os.SEEK_END)
            handle.write(_json_bytes(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _replay_events(self) -> None:
        raw = self.events_path.read_bytes()
        lines = raw.splitlines(keepends=True)
        last_non_empty = max(
            (index for index, line in enumerate(lines) if line.strip()),
            default=-1,
        )
        valid_prefix_end = 0
        for index, line in enumerate(lines):
            content = line.strip()
            if not content:
                valid_prefix_end += len(line)
                continue
            try:
                parsed = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if (
                    index == last_non_empty
                    and not line.endswith((b"\n", b"\r"))
                    and _looks_like_truncated_json(content)
                ):
                    self._recovered_tail_bytes = len(raw) - valid_prefix_end
                    self._recovered_tail_prefix = raw[:valid_prefix_end]
                    break
                raise JournalCorruptionError(
                    "serial job journal contains malformed or truncated event data"
                ) from exc
            if not isinstance(parsed, dict):
                raise JournalCorruptionError("serial job journal event must be an object")
            try:
                validate_event_record(parsed)
                expected_sequence = len(self._events)
                if parsed["sequence"] != expected_sequence:
                    raise JournalCorruptionError(
                        "serial job journal sequence is not monotonic"
                    )
                expected_previous = self._last_integrity_hash
                if parsed["previous_integrity_hash"] != expected_previous:
                    raise JournalCorruptionError(
                        "serial job journal integrity chain is broken"
                    )
                expected_hash = _hash_json(
                    {
                        key: parsed[key]
                        for key in parsed
                        if key != "integrity_hash"
                    }
                )
                if parsed["integrity_hash"] != expected_hash:
                    raise JournalCorruptionError(
                        "serial job journal integrity hash is invalid"
                    )
                if self._job is not None and parsed["job_id"] != self._job["job_id"]:
                    raise JournalCorruptionError("serial job journal event belongs to another job")
                self._events.append(parsed)
                self._last_integrity_hash = str(parsed["integrity_hash"])
                self._apply_event(parsed)
            except JournalCorruptionError:
                raise
            except (InvalidTransitionError, ValueError) as exc:
                raise JournalCorruptionError(
                    "serial job journal event failed validation"
                ) from exc
            valid_prefix_end += len(line)

    def _validate_reconstructed_state(self) -> None:
        assert self._job is not None
        if self._job["job_id"] != self.orchestration_dir.name:
            raise JournalCorruptionError("journal job identity does not match its directory")
        if self._job["configuration_identity_hash"] != _hash_json(
            self._job["configuration_identity"]
        ):
            raise JournalCorruptionError("configuration identity hash is invalid")
        items = self.work_items
        if self._job["work_item_count"] != len(items):
            raise JournalCorruptionError("job work-item count does not match journal state")
        if self._job["completed_work_item_count"] != sum(
            item["status"] == "completed" for item in items
        ):
            raise JournalCorruptionError("job completed count does not match journal state")
        if self._job["accepted_work_item_count"] != sum(
            item["status"] == "completed" and item["result_kind"] == "accepted"
            for item in items
        ):
            raise JournalCorruptionError("job accepted count does not match journal state")
        if self._job["rejected_work_item_count"] != sum(
            item["status"] == "completed" and item["result_kind"] == "rejected"
            for item in items
        ):
            raise JournalCorruptionError("job rejected count does not match journal state")
        if self._job["execution_mode"] == "coverage":
            if self._job["candidate_set_hash"] is not None:
                raise JournalCorruptionError(
                    "coverage job cannot bind a candidate set"
                )
            if tuple(item["sequence_index"] for item in items) != tuple(
                range(len(items))
            ):
                raise JournalCorruptionError(
                    "coverage work-item sequence indexes are not contiguous"
                )
            for item in items:
                assignment = item.get("coverage_assignment")
                wave = item.get("coverage_wave")
                if not isinstance(assignment, Mapping) or not isinstance(wave, int):
                    raise JournalCorruptionError(
                        "coverage work item is missing durable assignment state"
                    )
                try:
                    parsed_assignment = CoverageAssignment.from_durable_record(
                        assignment
                    )
                except (TypeError, ValueError) as exc:
                    raise JournalCorruptionError(
                        "coverage work item assignment is malformed"
                    ) from exc
                if parsed_assignment.assignment_ordinal != item["sequence_index"]:
                    raise JournalCorruptionError(
                        "coverage assignment sequence identity is inconsistent"
                    )
                candidate_record = item.get("candidate")
                if not isinstance(candidate_record, Mapping):
                    raise JournalCorruptionError(
                        "coverage work item candidate is malformed"
                    )
                if item["coverage_generation_rejection"] is not None and candidate_record.get(
                    "schema_version"
                ) != INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
                    raise JournalCorruptionError(
                        "coverage generation rejection has a bound candidate"
                    )
        elif self._job["candidate_set_hash"] is None:
            if items:
                raise JournalCorruptionError("work items exist before candidate set binding")
        else:
            records = tuple(item["candidate"] for item in items)
            if self._job["candidate_set_hash"] != _hash_json(records):
                raise JournalCorruptionError("durable candidate set hash is invalid")
            if self._job["target_candidate_count"] != len(records):
                raise JournalCorruptionError(
                    "durable candidate target does not match work items"
                )
            if tuple(item["sequence_index"] for item in items) != tuple(range(len(items))):
                raise JournalCorruptionError("work-item sequence indexes are not contiguous")
        budget = _logical_call_budget_from_limits(
            self._job.get("authorization_limits"),
            required=False,
        )
        if budget is not None and self.issued_logical_call_count > budget:
            raise JournalCorruptionError(
                "provider logical-call usage exceeds durable authorization"
            )
        checkpoint_ids = {
            str(checkpoint["attempt_id"])
            for checkpoint in self._provider_checkpoints
        }
        checkpoint_batches: set[int] = set()
        checkpoint_candidate_ids: set[str] = set()
        for checkpoint in self._provider_checkpoints:
            batch_index = _integer_value(
                checkpoint["batch_index"],
                "provider_checkpoint.batch_index",
            )
            if batch_index in checkpoint_batches:
                raise JournalCorruptionError(
                    "provider checkpoint batch identity is duplicated"
                )
            checkpoint_batches.add(batch_index)
            checkpoint_records = checkpoint.get("contracts")
            if not isinstance(checkpoint_records, list):
                raise JournalCorruptionError(
                    "provider checkpoint contracts are malformed"
                )
            for record in checkpoint_records:
                if not isinstance(record, Mapping):
                    raise JournalCorruptionError(
                        "provider checkpoint contract is malformed"
                    )
                try:
                    candidate_id = _task_contract_from_record(record).intent.candidate_id
                except (KeyError, TypeError, ValueError) as exc:
                    raise JournalCorruptionError(
                        "provider checkpoint contract is invalid"
                    ) from exc
                if candidate_id in checkpoint_candidate_ids:
                    raise JournalCorruptionError(
                        "provider checkpoint candidate identity is duplicated"
                    )
                checkpoint_candidate_ids.add(candidate_id)
        if any(
            attempt["status"] == "checkpointed"
            and str(attempt["attempt_id"]) not in checkpoint_ids
            for attempt in self.provider_attempts
        ):
            raise JournalCorruptionError(
                "provider checkpoint state is inconsistent with attempts"
            )

    def _validate_snapshots(self) -> None:
        if not self.job_path.exists() or not self.work_items_path.exists():
            self._snapshots_need_rebuild = True
            return
        try:
            snapshot_job = json.loads(self.job_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JournalCorruptionError("serial job snapshot is malformed") from exc
        if not isinstance(snapshot_job, Mapping):
            raise JournalCorruptionError("serial job snapshot must be an object")
        try:
            validate_job_record(snapshot_job)
        except (TypeError, ValueError) as exc:
            raise JournalCorruptionError("serial job snapshot failed validation") from exc
        try:
            snapshot_items = [
                json.loads(line)
                for line in self.work_items_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JournalCorruptionError("work-item snapshot is malformed") from exc
        if not all(isinstance(item, Mapping) for item in snapshot_items):
            raise JournalCorruptionError("work-item snapshot entries must be objects")
        try:
            for item in snapshot_items:
                validate_work_item_record(item)
        except (TypeError, ValueError) as exc:
            raise JournalCorruptionError("work-item snapshot failed validation") from exc
        if _stable_snapshot_record(snapshot_job) != _stable_snapshot_record(self.job):
            self._snapshots_need_rebuild = True
        if [_stable_snapshot_record(item) for item in snapshot_items] != [
            _stable_snapshot_record(item) for item in self.work_items
        ]:
            self._snapshots_need_rebuild = True
        if not self.provider_usage_path.exists():
            self._snapshots_need_rebuild = True
        else:
            try:
                snapshot_usage = json.loads(
                    self.provider_usage_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise JournalCorruptionError(
                    "provider usage snapshot is malformed"
                ) from exc
            if not isinstance(snapshot_usage, Mapping):
                raise JournalCorruptionError(
                    "provider usage snapshot must be an object"
                )
            if _stable_snapshot_record(snapshot_usage) != _stable_snapshot_record(
                self.provider_usage
            ):
                self._snapshots_need_rebuild = True

    def _apply_event(self, event: Mapping[str, object]) -> None:
        event_type = str(event["event_type"])
        payload = event["payload"]
        assert isinstance(payload, Mapping)
        work_item_id = event["work_item_id"]
        if event_type == "job_created":
            if work_item_id is not None or self._job is not None or self._events[:-1]:
                raise JournalCorruptionError("job_created must be the first event")
            self._job = dict(payload)
            if event["job_id"] != self._job.get("job_id"):
                raise JournalCorruptionError("job_created event identity does not match payload")
            validate_job_record(self._job)
            return
        if self._job is None:
            raise JournalCorruptionError("event precedes job_created")
        if event_type == "job_started":
            _require_payload_keys(payload, set())
            self._require_no_work_item(work_item_id)
            self._require_job_status("pending")
            self._job["status"] = "running"
        elif event_type == "job_cancelling":
            _require_payload_keys(payload, {"reason"})
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            _require_non_empty_string(payload.get("reason"), "job_cancelling.reason")
            self._job["status"] = "cancelling"
        elif event_type == "job_resumed":
            _require_payload_keys(payload, set())
            self._require_no_work_item(work_item_id)
            if self.status not in {"running", "cancelling", "cancelled", "failed"}:
                raise InvalidTransitionError(
                    f"job status {self.status!r} cannot accept resume"
                )
            self._job["status"] = "running"
        elif event_type == "candidate_set_bound":
            _require_payload_keys(payload, {"candidate_set_hash", "target_candidate_count"})
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            if self.candidate_set_hash is not None:
                raise InvalidTransitionError("candidate set is already bound")
            candidate_set_hash = payload.get("candidate_set_hash")
            _validate_sha256(candidate_set_hash, "candidate_set_hash")
            count = payload.get("target_candidate_count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise InvalidTransitionError("candidate set count is invalid")
            original_target = self._job["target_candidate_count"]
            if original_target is not None and original_target != count:
                raise InvalidTransitionError("candidate set count drifts from run profile")
            self._job["candidate_set_hash"] = candidate_set_hash
            self._job["target_candidate_count"] = count
        elif event_type == "work_item_created":
            self._require_job_status("running")
            if work_item_id is None or work_item_id in self._items:
                raise InvalidTransitionError("work item identity is duplicated")
            if not isinstance(work_item_id, str):
                raise InvalidTransitionError("work item identity must be a string")
            item = dict(payload)
            validate_work_item_record(item)
            if item["item_id"] != work_item_id:
                raise InvalidTransitionError("work item event identity does not match payload")
            if item["job_id"] != self._job["job_id"]:
                raise InvalidTransitionError("work item belongs to another job")
            if item["sequence_index"] != len(self._items):
                raise InvalidTransitionError("work item sequence indexes are reordered")
            if item["item_id"] != _work_item_id(str(self._job["job_id"]), item["sequence_index"]):
                raise InvalidTransitionError("work item identity is not locally derived")
            if self._job["execution_mode"] == "coverage":
                if item["coverage_assignment"] is None:
                    raise InvalidTransitionError(
                        "coverage job work item is missing its assignment"
                    )
            elif any(
                item[field_name] is not None
                for field_name in (
                    "coverage_assignment",
                    "coverage_wave",
                    "coverage_generation_rejection",
                )
            ):
                raise InvalidTransitionError(
                    "candidate-set work item contains coverage state"
                )
            self._items[work_item_id] = item
        elif event_type == "work_item_started":
            _require_payload_keys(payload, set())
            self._require_job_status("running")
            item = self._require_item(work_item_id)
            if item["status"] != "pending":
                raise InvalidTransitionError("only pending work items can start")
            item["status"] = "running"
            item["attempt_count"] = _integer_value(
                item["attempt_count"],
                "work_item.attempt_count",
            ) + 1
            item["started_at"] = self._timestamp_factory()
        elif event_type == "work_item_requeued":
            _require_payload_keys(payload, {"reason"})
            _require_non_empty_string(payload.get("reason"), "work_item_requeued.reason")
            item = self._require_item(work_item_id)
            if item["status"] not in {"running", "failed", "cancelled"}:
                raise InvalidTransitionError(
                    "only running, failed, or cancelled work items can be requeued"
                )
            item["status"] = "pending"
            item["started_at"] = None
        elif event_type == "work_item_interrupted":
            _require_payload_keys(payload, {"reason"})
            _require_non_empty_string(
                payload.get("reason"),
                "work_item_interrupted.reason",
            )
            item = self._require_item(work_item_id)
            if item["status"] != "running":
                raise InvalidTransitionError(
                    "only running work items can be interrupted"
                )
            item["status"] = "cancelled"
            item["started_at"] = None
        elif event_type == "work_item_failed":
            _require_payload_keys(payload, {"error_class"})
            _require_non_empty_string(
                payload.get("error_class"),
                "work_item_failed.error_class",
            )
            item = self._require_item(work_item_id)
            if item["status"] != "running":
                raise InvalidTransitionError(
                    "only running work items can fail"
                )
            item["status"] = "failed"
            item["started_at"] = None
        elif event_type == "work_item_completed":
            _require_payload_keys(payload, {"result_kind", "outcome"})
            item = self._require_item(work_item_id)
            if item["status"] != "running":
                raise InvalidTransitionError("only running work items can complete")
            result_kind = payload.get("result_kind")
            outcome = payload.get("outcome")
            if result_kind not in WORK_ITEM_RESULT_KINDS or not isinstance(outcome, Mapping):
                raise InvalidTransitionError("work item completion payload is invalid")
            _validate_outcome_record_shape(outcome)
            candidate_record = item["candidate"]
            if not isinstance(candidate_record, Mapping):
                raise InvalidTransitionError("work item candidate intent is not an object")
            sequence_index = item["sequence_index"]
            if not isinstance(sequence_index, int) or isinstance(sequence_index, bool):
                raise InvalidTransitionError("work item sequence index is invalid")
            candidate_schema = candidate_record.get("schema_version")
            candidate_identity_matches = (
                candidate_schema == INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION
                or _work_item_candidate_id(
                    outcome["candidate_id"],
                    sequence_index,
                )
                == item["candidate_id"]
            )
            if outcome["sequence_index"] != sequence_index or not candidate_identity_matches:
                raise InvalidTransitionError("work item outcome identity does not match intent")
            expected_kind = "accepted" if outcome.get("sample") is not None else "rejected"
            if result_kind != expected_kind:
                raise InvalidTransitionError("work item result kind does not match outcome")
            item["status"] = "completed"
            item["completed_at"] = self._timestamp_factory()
            item["result_kind"] = result_kind
            item["outcome"] = dict(outcome)
        elif event_type == "coverage_candidate_bound":
            _require_payload_keys(payload, {"candidate", "task_contract"})
            item = self._require_item(work_item_id)
            if item["coverage_assignment"] is None:
                raise InvalidTransitionError(
                    "coverage candidate binding references a non-coverage item"
                )
            if item["status"] not in {"pending", "running"}:
                raise InvalidTransitionError(
                    "coverage candidate cannot be bound after completion"
                )
            candidate = payload.get("candidate")
            task_contract = payload.get("task_contract")
            if not isinstance(candidate, Mapping):
                raise InvalidTransitionError("coverage candidate is malformed")
            if not isinstance(task_contract, Mapping):
                raise InvalidTransitionError("coverage task checkpoint is malformed")
            try:
                parsed_candidate = _candidate_from_record(candidate)
                validate_task_contract(parsed_candidate.contract())
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidTransitionError(
                    "coverage candidate checkpoint is invalid"
                ) from exc
            item["candidate"] = _json_copy(candidate)
            item["task_contract"] = _json_copy(task_contract)
            item["candidate_id"] = parsed_candidate.candidate_id
        elif event_type == "coverage_generation_rejected":
            _require_payload_keys(payload, {"rejection"})
            item = self._require_item(work_item_id)
            if item["coverage_assignment"] is None:
                raise InvalidTransitionError(
                    "coverage rejection references a non-coverage item"
                )
            if item["status"] != "pending" or item["coverage_generation_rejection"] is not None:
                raise InvalidTransitionError(
                    "coverage generation rejection transition is invalid"
                )
            rejection = payload.get("rejection")
            if not isinstance(rejection, Mapping):
                raise InvalidTransitionError(
                    "coverage generation rejection is malformed"
                )
            item["coverage_generation_rejection"] = _json_copy(rejection)
        elif event_type == "provider_work_intent":
            _require_payload_keys(
                payload,
                {
                    "attempt_id",
                    "attempt_sequence",
                    "role",
                    "provider_alias",
                    "model_alias",
                    "batch_index",
                    "requested_candidate_count",
                    "prompt_hash",
                },
            )
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            attempt_id = payload.get("attempt_id")
            attempt_sequence = payload.get("attempt_sequence")
            if not isinstance(attempt_id, str) or attempt_id != _provider_attempt_id(
                str(self.job["job_id"]), attempt_sequence
            ):
                raise InvalidTransitionError("provider attempt identity is invalid")
            if attempt_id in self._provider_attempts:
                raise InvalidTransitionError("provider attempt identity is duplicated")
            if (
                not isinstance(attempt_sequence, int)
                or isinstance(attempt_sequence, bool)
                or attempt_sequence <= 0
            ):
                raise InvalidTransitionError("provider attempt sequence is invalid")
            if attempt_sequence != len(self._provider_attempts) + 1:
                raise InvalidTransitionError("provider attempt sequence is not contiguous")
            role = payload.get("role")
            provider_alias = payload.get("provider_alias")
            model_alias = payload.get("model_alias")
            _validate_provider_alias(role, "provider_attempt.role")
            _validate_provider_alias(provider_alias, "provider_attempt.provider_alias")
            _validate_provider_alias(model_alias, "provider_attempt.model_alias")
            configured_identity = _provider_identity_from_job(self.job)
            if configured_identity != {
                "provider_alias": provider_alias,
                "model_alias": model_alias,
            }:
                raise InvalidTransitionError(
                    "provider attempt aliases drift from durable job identity"
                )
            batch_index = payload.get("batch_index")
            requested = payload.get("requested_candidate_count")
            if (
                not isinstance(batch_index, int)
                or isinstance(batch_index, bool)
                or batch_index <= 0
                or not isinstance(requested, int)
                or isinstance(requested, bool)
                or requested <= 0
            ):
                raise InvalidTransitionError("provider attempt batch shape is invalid")
            prompt_hash = payload.get("prompt_hash")
            if not isinstance(prompt_hash, str) or _HEX_SHA256_RE.fullmatch(prompt_hash) is None:
                raise InvalidTransitionError("provider attempt prompt hash is invalid")
            self._provider_attempts[attempt_id] = {
                "schema_version": PROVIDER_ATTEMPT_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "attempt_sequence": attempt_sequence,
                "role": role,
                "provider_alias": provider_alias,
                "model_alias": model_alias,
                "batch_index": batch_index,
                "requested_candidate_count": requested,
                "prompt_hash": prompt_hash,
                "status": "intent",
                "logical_call_number": None,
                "retry_count": 0,
                "token_usage": {},
                "price_metadata": None,
                "error_class": None,
                "cause": None,
                "contracts": None,
            }
        elif event_type == "provider_attempt_issued":
            _require_payload_keys(payload, {"attempt_id", "logical_call_number"})
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            attempt = self._provider_attempt(str(payload.get("attempt_id")))
            if attempt["status"] != "intent":
                raise InvalidTransitionError("provider attempt was already issued")
            logical_call_number = payload.get("logical_call_number")
            if (
                not isinstance(logical_call_number, int)
                or isinstance(logical_call_number, bool)
                or logical_call_number != self.issued_logical_call_count + 1
            ):
                raise InvalidTransitionError("provider logical call number is invalid")
            budget = _logical_call_budget_from_limits(
                self.job.get("authorization_limits"),
                required=True,
            )
            assert budget is not None
            if logical_call_number > budget:
                raise InvalidTransitionError("provider logical call budget was exceeded")
            attempt["status"] = "issued"
            attempt["logical_call_number"] = logical_call_number
        elif event_type == "provider_attempt_known":
            _require_payload_keys(
                payload,
                {"attempt_id", "retry_count", "token_usage", "price_metadata"},
            )
            self._require_no_work_item(work_item_id)
            self._require_job_status_in({"running", "cancelling"})
            attempt = self._provider_attempt(str(payload.get("attempt_id")))
            if attempt["status"] != "issued":
                raise InvalidTransitionError("provider attempt cannot become known")
            _validate_provider_usage_payload(payload)
            attempt["status"] = "known"
            attempt["retry_count"] = payload["retry_count"]
            attempt["token_usage"] = dict(payload["token_usage"])
            attempt["price_metadata"] = _json_copy(payload["price_metadata"])
        elif event_type == "provider_attempt_ambiguous":
            _require_payload_keys(payload, {"attempt_id", "reason", "error_class"})
            self._require_no_work_item(work_item_id)
            self._require_job_status_in({"running", "cancelling"})
            attempt = self._provider_attempt(str(payload.get("attempt_id")))
            if attempt["status"] != "issued":
                raise InvalidTransitionError("provider attempt cannot become ambiguous")
            _require_non_empty_string(payload.get("reason"), "provider_attempt.reason")
            _validate_provider_alias(payload.get("error_class"), "provider_attempt.error_class")
            attempt["status"] = "ambiguous"
            attempt["error_class"] = payload["error_class"]
            attempt["cause"] = "llm_provider_ambiguous"
        elif event_type == "provider_attempt_failed":
            _require_payload_keys(
                payload,
                {
                    "attempt_id",
                    "cause",
                    "error_class",
                    "retry_count",
                    "token_usage",
                    "price_metadata",
                },
            )
            self._require_no_work_item(work_item_id)
            self._require_job_status_in({"running", "cancelling"})
            attempt = self._provider_attempt(str(payload.get("attempt_id")))
            if attempt["status"] != "issued":
                raise InvalidTransitionError("provider attempt cannot fail twice")
            _validate_provider_usage_payload(payload)
            _require_non_empty_string(payload.get("cause"), "provider_attempt.cause")
            _validate_provider_alias(payload.get("error_class"), "provider_attempt.error_class")
            attempt["status"] = "failed"
            attempt["cause"] = payload["cause"]
            attempt["error_class"] = payload["error_class"]
            attempt["retry_count"] = payload["retry_count"]
            attempt["token_usage"] = dict(payload["token_usage"])
            attempt["price_metadata"] = _json_copy(payload["price_metadata"])
        elif event_type == "provider_contract_checkpointed":
            _require_payload_keys(payload, {"attempt_id", "batch_index", "contracts"})
            self._require_no_work_item(work_item_id)
            self._require_job_status_in({"running", "cancelling"})
            attempt = self._provider_attempt(str(payload.get("attempt_id")))
            if attempt["status"] != "known":
                raise InvalidTransitionError(
                    "provider contract checkpoint requires a known response"
                )
            batch_index = payload.get("batch_index")
            if batch_index != attempt["batch_index"]:
                raise InvalidTransitionError("provider checkpoint batch drifts from attempt")
            contracts = payload.get("contracts")
            if not isinstance(contracts, list) or not contracts:
                raise InvalidTransitionError("provider checkpoint contracts are invalid")
            candidate_ids: set[str] = set()
            for record in contracts:
                if not isinstance(record, Mapping):
                    raise InvalidTransitionError("provider checkpoint contract is not an object")
                try:
                    contract = _task_contract_from_record(record)
                    candidate_id = contract.intent.candidate_id
                except (KeyError, TypeError, ValueError) as exc:
                    raise InvalidTransitionError(
                        "provider checkpoint contract is malformed"
                    ) from exc
                if candidate_id in candidate_ids:
                    raise InvalidTransitionError(
                        "provider checkpoint contains duplicate candidate ids"
                    )
                candidate_ids.add(candidate_id)
            attempt["status"] = "checkpointed"
            attempt["contracts"] = _json_copy(contracts)
            self._provider_checkpoints.append(
                {
                    "attempt_id": attempt["attempt_id"],
                    "batch_index": batch_index,
                    "contracts": _json_copy(contracts),
                }
            )
        elif event_type == "job_interrupted":
            _require_payload_keys(payload, {"reason"})
            _require_non_empty_string(payload.get("reason"), "job_interrupted.reason")
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
        elif event_type == "journal_tail_recovered":
            _require_payload_keys(payload, {"discarded_bytes"})
            self._require_no_work_item(work_item_id)
            discarded_bytes = payload.get("discarded_bytes")
            if (
                not isinstance(discarded_bytes, int)
                or isinstance(discarded_bytes, bool)
                or discarded_bytes <= 0
            ):
                raise InvalidTransitionError(
                    "journal recovery byte count is invalid"
                )
        elif event_type == "job_lock_recovered":
            _require_payload_keys(payload, {"recovered_stale_lock"})
            self._require_no_work_item(work_item_id)
            if payload.get("recovered_stale_lock") is not True:
                raise InvalidTransitionError("lock recovery marker is invalid")
        elif event_type == "job_failed":
            _require_payload_keys(payload, {"error_class"})
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            _require_non_empty_string(payload.get("error_class"), "job_failed.error_class")
            self._job["status"] = "failed"
        elif event_type == "job_cancelled":
            _require_payload_keys(
                payload,
                {"artifact_references", "accepted_count", "rejected_count"},
            )
            self._require_no_work_item(work_item_id)
            self._require_job_status("cancelling")
            if any(item["status"] == "running" for item in self.work_items):
                raise InvalidTransitionError(
                    "job cannot be cancelled with running work items"
                )
            references = payload.get("artifact_references")
            if not isinstance(references, Mapping):
                raise InvalidTransitionError(
                    "cancelled job artifact references are invalid"
                )
            accepted_count = payload.get("accepted_count")
            rejected_count = payload.get("rejected_count")
            if (
                not isinstance(accepted_count, int)
                or isinstance(accepted_count, bool)
                or accepted_count < 0
                or not isinstance(rejected_count, int)
                or isinstance(rejected_count, bool)
                or rejected_count < 0
            ):
                raise InvalidTransitionError(
                    "cancelled job artifact counts are invalid"
                )
            _assert_safe_orchestration_value(references)
            self._job["status"] = "cancelled"
            self._job["artifact_references"] = dict(references)
            self._job["accepted_count"] = accepted_count
            self._job["rejected_count"] = rejected_count
        elif event_type == "job_completed":
            _require_payload_keys(
                payload,
                {"artifact_references", "accepted_count", "rejected_count"},
            )
            self._require_no_work_item(work_item_id)
            self._require_job_status("running")
            if any(item["status"] != "completed" for item in self.work_items):
                raise InvalidTransitionError("job cannot complete with pending work")
            references = payload.get("artifact_references")
            if not isinstance(references, Mapping):
                raise InvalidTransitionError("job completion artifacts are invalid")
            accepted_count = payload.get("accepted_count")
            rejected_count = payload.get("rejected_count")
            _assert_safe_orchestration_value(references)
            self._job["status"] = "completed"
            self._job["artifact_references"] = dict(references)
            self._job["accepted_count"] = accepted_count
            self._job["rejected_count"] = rejected_count
        else:
            raise JournalCorruptionError(f"unsupported serial job event: {event_type}")
        self._refresh_job()

    def _require_job_status(self, expected: str) -> None:
        if self.status != expected:
            raise InvalidTransitionError(
                f"job status {self.status!r} cannot accept transition from {expected!r}"
            )

    def _require_job_status_in(self, expected: set[str]) -> None:
        if self.status not in expected:
            raise InvalidTransitionError(
                f"job status {self.status!r} cannot accept transition from {sorted(expected)!r}"
            )

    def _require_no_work_item(self, work_item_id: object) -> None:
        if work_item_id is not None:
            raise InvalidTransitionError("job event cannot reference a work item")

    def _require_item(self, work_item_id: object) -> dict[str, object]:
        if not isinstance(work_item_id, str) or work_item_id not in self._items:
            raise InvalidTransitionError("event references an unknown work item")
        return self._items[work_item_id]

    def _refresh_job(self) -> None:
        if self._job is None:
            return
        items = self.work_items
        self._job["work_item_count"] = len(items)
        self._job["completed_work_item_count"] = sum(
            item["status"] == "completed" for item in items
        )
        self._job["accepted_work_item_count"] = sum(
            item["status"] == "completed" and item["result_kind"] == "accepted"
            for item in items
        )
        self._job["rejected_work_item_count"] = sum(
            item["status"] == "completed" and item["result_kind"] == "rejected"
            for item in items
        )
        self._job["updated_at"] = self._timestamp_factory()
        validate_job_record(self._job)

    def _write_snapshots(self) -> None:
        if self._job is None:
            return
        self._refresh_job()
        _atomic_write_json(self.job_path, self._job)
        content = "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in self.work_items
        )
        _atomic_write_text(self.work_items_path, content)
        _atomic_write_json(self.provider_usage_path, self.provider_usage)


def _normalize_requested_concurrency(
    max_concurrency: object,
) -> int | None:
    if max_concurrency is _UNSET_CONCURRENCY:
        return None
    if max_concurrency is None:
        raise JobConfigurationError(
            "max_concurrency must be a positive integer"
        )
    try:
        return validate_concurrency(max_concurrency)
    except ValueError as exc:
        raise JobConfigurationError(str(exc)) from exc


def _validate_cancellation_signal(signal: object | None) -> None:
    if signal is None:
        return
    is_set = getattr(signal, "is_set", None)
    if not callable(is_set):
        raise JobConfigurationError(
            "cancellation_signal must expose is_set()"
        )


def _cancellation_signal_is_set(signal: object | None) -> bool:
    if signal is None:
        return False
    is_set = getattr(signal, "is_set", None)
    if not callable(is_set):
        raise JobConfigurationError(
            "cancellation_signal must expose is_set()"
        )
    value = is_set()
    if not isinstance(value, bool):
        raise JobConfigurationError(
            "cancellation_signal.is_set() must return a boolean"
        )
    return value


def _validate_serial_configuration(
    *,
    job_id: str,
    run_profile: RunProfile,
    interrupt_after: int | None,
    provider_identity: Mapping[str, str] | None,
    authorization_limits: Mapping[str, object],
    provider: object | None,
    provider_factory: ProviderFactory | None,
    candidate_generator: CandidateGenerator | None,
    candidate_generator_factory: CandidateGeneratorFactory | None,
    max_concurrency: int | None,
) -> None:
    _validate_job_id(job_id)
    if not isinstance(run_profile, RunProfile):
        raise JobConfigurationError("run_profile must be a validated RunProfile")
    if run_profile.generation.mode == "llm" and provider_identity is None:
        raise JobConfigurationError(
            "llm serial orchestration requires an explicit provider"
        )
    if run_profile.generation.mode != "llm" and provider_identity is not None:
        raise JobConfigurationError(
            "provider-backed serial orchestration requires llm generation mode"
        )
    if provider_identity is not None:
        _logical_call_budget_from_limits(authorization_limits, required=True)
    if provider is not None and provider_factory is not None:
        raise JobConfigurationError("provider and provider_factory are mutually exclusive")
    if provider_factory is not None and not callable(provider_factory):
        raise JobConfigurationError("provider_factory must be callable")
    if provider is not None and not callable(getattr(provider, "generate_json", None)):
        raise JobConfigurationError(
            "provider must expose generate_json(prompt, role=...)"
        )
    if provider_identity is not None and (
        candidate_generator is not None or candidate_generator_factory is not None
    ):
        raise JobConfigurationError(
            "provider-backed orchestration owns the candidate generator"
        )
    if run_profile.features.enable_task_expansion:
        raise JobConfigurationError(
            "task-expansion orchestration is deferred to a later serial-job slice"
        )
    if run_profile.features.enable_refinement:
        raise JobConfigurationError(
            "refinement orchestration is deferred to a later serial-job slice"
        )
    if interrupt_after is not None and (
        not isinstance(interrupt_after, int)
        or isinstance(interrupt_after, bool)
        or interrupt_after < 0
    ):
        raise JobConfigurationError("interrupt_after must be a non-negative integer or null")
    if max_concurrency is not None:
        try:
            validate_concurrency(max_concurrency)
        except ValueError as exc:
            raise JobConfigurationError(str(exc)) from exc


def _normalize_authorization_limits(
    value: Mapping[str, object] | None,
) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise JobConfigurationError("authorization_limits must be an object or null")
    try:
        normalized = json.loads(
            json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
        )
    except (TypeError, ValueError) as exc:
        raise JobConfigurationError(
            "authorization_limits must contain JSON-compatible values"
        ) from exc
    if not isinstance(normalized, dict):
        raise JobConfigurationError("authorization_limits must be an object")
    _assert_safe_orchestration_value(normalized)
    return normalized


def _normalize_provider_identity(
    *,
    provider_present: bool,
    generation_mode: str | None,
    provider_alias: str | None,
    model_alias: str | None,
) -> dict[str, str] | None:
    aliases_present = provider_alias is not None or model_alias is not None
    if not provider_present and aliases_present:
        raise JobConfigurationError(
            "provider aliases require an explicit provider or provider_factory"
        )
    if not provider_present:
        if generation_mode == "llm":
            raise JobConfigurationError(
                "llm serial orchestration requires an explicit provider"
            )
        return None
    _validate_provider_alias(provider_alias, "provider_alias")
    _validate_provider_alias(model_alias, "model_alias")
    return {
        "provider_alias": str(provider_alias),
        "model_alias": str(model_alias),
    }


def _validate_provider_alias(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _PROVIDER_ALIAS_RE.fullmatch(value) is None:
        raise JobConfigurationError(
            f"{field_name} must be a safe non-empty provider/model alias"
        )


def _logical_call_budget_from_limits(
    limits: object,
    *,
    required: bool,
) -> int | None:
    if not isinstance(limits, Mapping):
        if required:
            raise JobConfigurationError(
                "authorization_limits.logical_call_budget is required"
            )
        return None
    value = limits.get("logical_call_budget")
    if value is None:
        if required:
            raise JobConfigurationError(
                "authorization_limits.logical_call_budget is required"
            )
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise JobConfigurationError(
            "authorization_limits.logical_call_budget must be a positive integer"
        )
    return value


def _provider_identity_from_job(
    job: Mapping[str, object],
) -> dict[str, str] | None:
    identity = job.get("configuration_identity")
    if not isinstance(identity, Mapping):
        return None
    provider = identity.get("provider")
    if provider is None:
        return None
    if not isinstance(provider, Mapping):
        raise JournalCorruptionError("durable provider identity is malformed")
    provider_alias = provider.get("provider_alias")
    model_alias = provider.get("model_alias")
    _validate_provider_alias(provider_alias, "provider.provider_alias")
    _validate_provider_alias(model_alias, "provider.model_alias")
    return {
        "provider_alias": str(provider_alias),
        "model_alias": str(model_alias),
    }


def _provider_attempt_id(job_id: str, attempt_sequence: object) -> str:
    if not isinstance(attempt_sequence, int) or isinstance(attempt_sequence, bool):
        raise ValueError("provider attempt sequence must be an integer")
    return f"{job_id}:provider:{attempt_sequence:06d}"


def _safe_retry_count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return min(value, 1000)


def _sanitize_provider_lineage(lineage: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(lineage, Mapping):
        lineage = {}
    token_usage: dict[str, int] = {}
    raw_tokens = lineage.get("tokens", {})
    if isinstance(raw_tokens, Mapping):
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
        ):
            value = raw_tokens.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                token_usage[key] = value
    price_metadata = lineage.get("price_metadata")
    if isinstance(price_metadata, Mapping):
        sanitized_price: dict[str, object] = {}
        for key in ("input", "output", "total", "currency"):
            value = price_metadata.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sanitized_price[key] = value
            elif key == "currency" and isinstance(value, str) and value.isalpha():
                sanitized_price[key] = value[:12]
        price_metadata_value: dict[str, object] | None = sanitized_price or None
    else:
        price_metadata_value = None
    return {
        "retry_count": _safe_retry_count(lineage.get("retry_count", 0)),
        "token_usage": token_usage,
        "price_metadata": price_metadata_value,
    }


def _validate_provider_usage_payload(payload: Mapping[str, object]) -> None:
    retry_count = payload.get("retry_count")
    if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0:
        raise InvalidTransitionError("provider retry count is invalid")
    token_usage = payload.get("token_usage")
    if not isinstance(token_usage, Mapping):
        raise InvalidTransitionError("provider token usage is invalid")
    for key, value in token_usage.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise InvalidTransitionError("provider token usage contains invalid fields")
    price_metadata = payload.get("price_metadata")
    if price_metadata is not None and not isinstance(price_metadata, Mapping):
        raise InvalidTransitionError("provider price metadata is invalid")


def _normalized_configuration_identity(
    run_profile: RunProfile,
    authorization_limits: Mapping[str, object],
    *,
    provider_identity: Mapping[str, str] | None = None,
    max_concurrency: int = 1,
) -> dict[str, object]:
    source: dict[str, object] | None = None
    if run_profile.source is not None:
        source = {
            "kind": run_profile.source.kind,
            "source_id": run_profile.source.source_id,
            "license_label": run_profile.source.license_label,
            "max_bytes": run_profile.source.max_bytes,
        }
    identity: dict[str, object] = {
        "schema_version": CONFIGURATION_IDENTITY_SCHEMA_VERSION,
        "profile": {
            "schema_version": run_profile.schema_version,
            "profile_id": run_profile.profile_id,
            "dataset_version": run_profile.dataset_version,
            "profile_purpose": run_profile.profile_purpose,
        },
        "domain": run_profile.seed.domain,
        "seed": {
            "seed_id": run_profile.seed.seed_id,
            "description": run_profile.seed.description,
            "task_taxonomy": list(run_profile.seed.task_taxonomy),
        },
        "generation": run_profile.generation.canonical(),
        "enabled_features": run_profile.features.canonical(),
        "source": source,
        "mutation_admission": run_profile.mutation_admission.canonical(),
        "coverage_profile": (
            run_profile.coverage_profile.canonical()
            if run_profile.coverage_profile is not None
            else None
        ),
        "authorization_limits": _json_copy(dict(authorization_limits)),
        "max_concurrency": validate_concurrency(max_concurrency),
    }
    if provider_identity is not None:
        identity["provider"] = {
            "provider_alias": provider_identity["provider_alias"],
            "model_alias": provider_identity["model_alias"],
        }
    _assert_safe_orchestration_value(identity)
    return identity


def _configuration_identity_hash(
    run_profile: RunProfile,
    authorization_limits: Mapping[str, object],
    *,
    provider_identity: Mapping[str, str] | None = None,
    max_concurrency: int = 1,
) -> str:
    return _hash_json(
        _normalized_configuration_identity(
            run_profile,
            authorization_limits,
            provider_identity=provider_identity,
            max_concurrency=max_concurrency,
        )
    )


def _output_ownership_hash(output_dir: Path, job_id: str) -> str:
    # The resolved path participates only in this digest. The durable record
    # can therefore bind ownership without retaining a host path.
    binding = {
        "schema_version": "orchestration_output_ownership_v1",
        "job_id": job_id,
        "resolved_output": str(Path(output_dir).expanduser().resolve()),
    }
    return _hash_json(binding)


def _stable_snapshot_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_snapshot_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_stable_snapshot_value(nested) for nested in value]
    return value


def _stable_snapshot_record(value: object) -> object:
    if not isinstance(value, Mapping):
        return _stable_snapshot_value(value)
    return _stable_snapshot_value(
        {
            key: nested
            for key, nested in value.items()
            if key not in {"created_at", "updated_at", "started_at", "completed_at"}
        }
    )


def _resolve_profile_source_inputs(
    run_profile: RunProfile,
    *,
    source_bundle: SourceBundle | None,
    domain_environment_input: object | None,
    source_events: list[dict[str, object]] | None,
    run_profile_metadata: dict[str, object] | None,
) -> _ResolvedSerialInputs:
    if run_profile.source is not None and (
        source_bundle is None and domain_environment_input is None
    ):
        try:
            importer = resolve_domain_source_importer(
                run_profile.seed.domain,
                run_profile.source.kind,
            )
            imported = build_profile_local_domain_source_input(
                ProfileLocalDomainSourceRequest(
                    domain_id=importer.domain_id,
                    kind=run_profile.source.kind,
                    source_id=run_profile.source.source_id,
                    path=run_profile.source.resolved_path,
                    license_label=run_profile.source.license_label,
                    max_bytes=run_profile.source.max_bytes,
                ),
                importer=importer,
            )
        except (ControlledSourceFetchError, ValueError) as exc:
            raise JobConfigurationError(
                f"profile-local source admission failed: {type(exc).__name__}"
            ) from exc
        if run_profile_metadata is None:
            run_profile_metadata = run_profile.sanitized_metadata(
                source_summary=imported.source_summary,
            )
        return _ResolvedSerialInputs(
            source_bundle=imported.source_bundle,
            domain_environment_input=imported.environment_input,
            source_events=list(imported.events),
            run_profile_metadata=run_profile_metadata,
        )
    if (
        source_bundle is None
        and run_profile.features.enable_source_governance_fixture
    ):
        source_bundle = build_external_fixture_source_bundle(network_enabled=True)
    if run_profile_metadata is None:
        run_profile_metadata = run_profile.sanitized_metadata()
    return _ResolvedSerialInputs(
        source_bundle=source_bundle,
        domain_environment_input=domain_environment_input,
        source_events=source_events,
        run_profile_metadata=run_profile_metadata,
    )


def _execution_config_hash(
    *,
    policy_generator: PolicyGenerator | None,
    source_bundle: SourceBundle | None,
    domain_environment_input: object | None,
    source_events: list[dict[str, object]] | None,
    run_profile_metadata: dict[str, object] | None,
    parent_artifact_path: Path | None,
    route_reviewable_failures: bool,
    write_episode_logs: bool,
) -> str:
    try:
        binding = {
            "schema_version": "serial_execution_config_v1",
            "policy_generator": _stable_execution_value(policy_generator),
            "source_bundle": _stable_execution_value(source_bundle),
            "domain_environment_input": _stable_execution_value(
                domain_environment_input
            ),
            "source_events": _stable_execution_value(source_events),
            "run_profile_metadata": _stable_execution_value(run_profile_metadata),
            "parent_artifact_path": _stable_execution_value(parent_artifact_path),
            "route_reviewable_failures": route_reviewable_failures,
            "write_episode_logs": write_episode_logs,
        }
    except (TypeError, ValueError) as exc:
        raise JobConfigurationError(
            "serial execution inputs must have a stable export or canonical value"
        ) from exc
    return _hash_json(binding)


def _stable_execution_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return {
            "kind": "path",
            "digest": _hash_json(str(value.expanduser().resolve())),
        }
    if callable(value):
        target = value
        if not getattr(target, "__qualname__", None):
            target = getattr(type(value), "__call__", target)
        module = getattr(target, "__module__", None)
        qualname = getattr(target, "__qualname__", None)
        if not isinstance(module, str) or not isinstance(qualname, str):
            raise TypeError("callable has no stable module and qualified name")
        source_hash: str | None = None
        try:
            source_hash = _hash_json(inspect.getsource(target))
        except (OSError, TypeError):
            pass
        return {
            "kind": "callable",
            "module": module,
            "qualname": qualname,
            "source_hash": source_hash,
        }
    export = getattr(value, "export", None)
    if callable(export):
        return {
            "kind": "export",
            "type": _qualified_type_name(value),
            "value": _stable_execution_value(export()),
        }
    canonical = getattr(value, "canonical", None)
    if callable(canonical):
        return {
            "kind": "canonical",
            "type": _qualified_type_name(value),
            "value": _stable_execution_value(canonical()),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "kind": "dataclass",
            "type": _qualified_type_name(value),
            "value": _stable_execution_value(asdict(value)),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_execution_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_stable_execution_value(item) for item in value]
    raise TypeError(f"unsupported stable execution value: {type(value).__name__}")


def _qualified_type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _default_deterministic_generator(run_profile: RunProfile) -> CandidateGenerator | None:
    if run_profile.generation.mode == "deterministic_scale_probe":
        target = run_profile.generation.target_candidate_count
        if target is None:
            raise JobConfigurationError(
                "deterministic scale-probe serial jobs require a target candidate count"
            )
        return lambda seed: generate_scale_probe_candidates(seed, target)
    if run_profile.generation.mode.endswith("_fixture"):
        return None
    raise JobConfigurationError(
        f"unsupported deterministic serial generation mode: {run_profile.generation.mode}"
    )


def _candidate_to_record(task: CandidateTask) -> dict[str, object]:
    try:
        contract = task.contract()
    except Exception:
        # Invalid generated candidates still need an intent slot so their
        # schema rejection can be checkpointed without retaining the raw
        # malformed candidate payload.
        return {
            "schema_version": INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION,
            "candidate_id": task.candidate_id,
        }
    record = _task_contract_to_record(contract)
    _assert_safe_orchestration_value(record)
    return record


def _candidate_from_record(record: object) -> CandidateTask:
    if not isinstance(record, Mapping):
        raise JournalCorruptionError("durable candidate intent must be an object")
    schema_version = record.get("schema_version")
    if schema_version == INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
        return CandidateTask(
            candidate_id=str(record.get("candidate_id", "")),
            instruction="",
            constraints={},
            difficulty={},
            tool_name="",
            arguments={},
            expected_answer="",
            seed_ids=(),
        )
    if schema_version != CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
        raise JournalCorruptionError("durable candidate intent schema is unsupported")
    try:
        return candidate_from_task_contract(
            _task_contract_from_record(record)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise JournalCorruptionError("durable candidate intent is malformed") from exc


def _task_contract_to_record(contract: TaskContract) -> dict[str, object]:
    return {
        "schema_version": CANDIDATE_CHECKPOINT_SCHEMA_VERSION,
        "candidate_id": contract.intent.candidate_id,
        "intent": {
            "candidate_id": contract.intent.candidate_id,
            "instruction": contract.intent.instruction,
            "domain_id": contract.intent.domain_id,
            "task_type": contract.intent.task_type,
            "difficulty": _json_copy(contract.intent.difficulty),
            "required_capabilities": list(contract.intent.required_capabilities),
            "seed_ids": list(contract.intent.seed_ids),
            "lineage": _json_copy(contract.intent.lineage),
        },
        "policy_hint": {
            "required_tools": list(contract.policy_hint.required_tools),
            "primary_tool": contract.policy_hint.primary_tool,
            "primary_arguments": _json_copy(contract.policy_hint.primary_arguments),
            "branch_plan": _json_copy(contract.policy_hint.branch_plan),
        },
        "expected_outcome": {
            "final_answer_contains": contract.expected_outcome.final_answer_contains,
        },
        "expected_state": [
            {
                "check_type": check.check_type,
                "expected": _json_copy(check.expected),
            }
            for check in contract.expected_state
        ],
        "compatibility": _json_copy(contract.compatibility),
        "mutation_authorization": _json_copy(contract.mutation_authorization),
    }


def _task_contract_from_record(record: Mapping[str, object]) -> TaskContract:
    if record.get("schema_version") != CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("task contract checkpoint schema is unsupported")
    intent = _mapping_value(record["intent"], "intent")
    if record.get("candidate_id") != intent.get("candidate_id"):
        raise ValueError("task contract checkpoint candidate identity is inconsistent")
    policy_hint = _mapping_value(record["policy_hint"], "policy_hint")
    expected_outcome = _mapping_value(record["expected_outcome"], "expected_outcome")
    expected_state = record["expected_state"]
    if not isinstance(expected_state, list):
        raise TypeError("expected_state must be a list")
    required_capabilities = _list_value(
        intent["required_capabilities"],
        "required_capabilities",
    )
    seed_ids = _list_value(intent["seed_ids"], "seed_ids")
    required_tools = _list_value(policy_hint["required_tools"], "required_tools")
    checks = []
    for value in expected_state:
        check = _mapping_value(value, "expected_state item")
        checks.append(
            ExpectedStateCheck(
                check_type=str(check["check_type"]),
                expected=dict(_mapping_value(check["expected"], "expected state")),
            )
        )
    contract = TaskContract(
        intent=TaskIntent(
            candidate_id=str(intent["candidate_id"]),
            instruction=str(intent["instruction"]),
            domain_id=str(intent["domain_id"]),
            task_type=str(intent["task_type"]),
            difficulty=dict(_mapping_value(intent["difficulty"], "difficulty")),
            required_capabilities=tuple(str(value) for value in required_capabilities),
            seed_ids=tuple(str(value) for value in seed_ids),
            lineage=dict(_mapping_value(intent["lineage"], "lineage")),
        ),
        policy_hint=PolicyHint(
            required_tools=tuple(str(value) for value in required_tools),
            primary_tool=(
                str(policy_hint["primary_tool"])
                if policy_hint.get("primary_tool") is not None
                else None
            ),
            primary_arguments=dict(
                _mapping_value(policy_hint["primary_arguments"], "primary_arguments")
            ),
            branch_plan=_optional_mapping_value(policy_hint.get("branch_plan")),
        ),
        expected_outcome=ExpectedOutcome(
            final_answer_contains=str(expected_outcome["final_answer_contains"]),
        ),
        expected_state=tuple(checks),
        compatibility=dict(_mapping_value(record["compatibility"], "compatibility")),
        mutation_authorization=_optional_mapping_value(
            record.get("mutation_authorization")
        ),
    )
    return validate_task_contract(contract)


def _task_contract_checkpoint_from_record(
    candidate_record: Mapping[str, object],
) -> dict[str, object] | None:
    try:
        task = _candidate_from_record(candidate_record)
        contract = task.contract()
    except Exception:
        return None
    return {
        "schema_version": TASK_CHECKPOINT_SCHEMA_VERSION,
        "candidate_id": contract.intent.candidate_id,
        "domain_id": contract.intent.domain_id,
        "task_type": contract.intent.task_type,
        "required_tools": list(contract.policy_hint.required_tools),
        "expected_answer": contract.expected_outcome.final_answer_contains,
        "expected_state": [
            {
                "check_type": check.check_type,
                "expected": _json_copy(check.expected),
            }
            for check in contract.expected_state
        ],
    }


def _outcome_to_record(
    outcome: ProvisionalCandidateOutcome,
    *,
    include_episode_log: bool,
) -> dict[str, object]:
    if (outcome.sample is None) == (outcome.rejection is None):
        raise InvalidTransitionError(
            "candidate outcome must contain exactly one sample or rejection"
        )
    signature = None
    if outcome.duplicate_signature is not None:
        signature = [
            outcome.duplicate_signature[0],
            list(outcome.duplicate_signature[1]),
        ]
    record = {
        "sequence_index": outcome.sequence_index,
        "candidate_id": outcome.candidate_id,
        "sample": _json_copy(outcome.sample),
        "rejection": _json_copy(outcome.rejection),
        "review_records": _json_copy(list(outcome.review_records)),
        "tool_proposal_records": _json_copy(list(outcome.tool_proposal_records)),
        "duplicate_signature": signature,
        "environment_isolation": _json_copy(outcome.environment_isolation),
        "registry_mutations": _json_copy(list(outcome.registry_mutations)),
        "task_record": _json_copy(outcome.task_record),
        "episode_log": _json_copy(outcome.episode_log)
        if include_episode_log
        else None,
    }
    _assert_safe_orchestration_value(record)
    return record


def _outcome_from_record(record: object) -> ProvisionalCandidateOutcome:
    if not isinstance(record, Mapping):
        raise JournalCorruptionError("durable candidate outcome must be an object")
    signature_value = record.get("duplicate_signature")
    signature: tuple[str, tuple[str, ...]] | None = None
    if signature_value is not None:
        if (
            not isinstance(signature_value, list)
            or len(signature_value) != 2
            or not isinstance(signature_value[0], str)
            or not isinstance(signature_value[1], list)
        ):
            raise JournalCorruptionError("durable duplicate signature is malformed")
        signature = (
            signature_value[0],
            tuple(str(value) for value in signature_value[1]),
        )
    try:
        sample = record.get("sample")
        rejection = record.get("rejection")
        if sample is not None and not isinstance(sample, dict):
            raise TypeError("sample must be an object or null")
        if rejection is not None and not isinstance(rejection, dict):
            raise TypeError("rejection must be an object or null")
        review_records = record.get("review_records", [])
        tool_proposal_records = record.get("tool_proposal_records", [])
        registry_mutations = record.get("registry_mutations", [])
        if not all(
            isinstance(value, list)
            for value in (review_records, tool_proposal_records, registry_mutations)
        ):
            raise TypeError("outcome record collections must be lists")
        environment_isolation = record.get("environment_isolation", {})
        if not isinstance(environment_isolation, dict):
            raise TypeError("environment_isolation must be an object")
        task_record = record.get("task_record")
        if task_record is not None and not isinstance(task_record, dict):
            raise TypeError("task_record must be an object or null")
        episode_log = record.get("episode_log")
        if episode_log is not None and not isinstance(episode_log, dict):
            raise TypeError("episode_log must be an object or null")
        outcome = ProvisionalCandidateOutcome(
            sequence_index=int(record["sequence_index"]),
            candidate_id=str(record["candidate_id"]),
            sample=sample,
            rejection=rejection,
            review_records=tuple(review_records),
            tool_proposal_records=tuple(tool_proposal_records),
            duplicate_signature=signature,
            environment_isolation=environment_isolation,
            registry_mutations=tuple(registry_mutations),
            task_record=task_record,
            episode_log=episode_log,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise JournalCorruptionError("durable candidate outcome is malformed") from exc
    if (outcome.sample is None) == (outcome.rejection is None):
        raise JournalCorruptionError("durable candidate outcome has invalid result shape")
    return outcome


def _pipeline_result_references(result: PipelineResult) -> dict[str, str | None]:
    references: dict[str, str | None] = {}
    for field_name in (
        "samples_path",
        "manifest_path",
        "rejections_path",
        "quality_report_path",
        "tool_proposals_path",
        "source_events_path",
        "sandbox_audits_path",
        "parent_comparison_path",
        "review_queue_path",
        "mutation_admission_report_path",
        "episode_logs_path",
        "coverage_plan_path",
        "coverage_evidence_path",
    ):
        value = getattr(result, field_name)
        if value is None:
            references[field_name] = None
            continue
        path = Path(value)
        if path.is_absolute():
            references[field_name] = path.name
        else:
            references[field_name] = str(path)
    return references


def _pipeline_result_from_references(
    output_dir: Path,
    references: object,
    *,
    accepted_count: object,
    rejected_count: object,
) -> PipelineResult:
    if not isinstance(references, Mapping):
        raise JournalCorruptionError("job artifact references must be an object")

    def path_for(field_name: str) -> Path | None:
        value = references.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise JournalCorruptionError("job artifact reference must be relative")
        path = Path(value)
        if ".." in path.parts:
            raise JournalCorruptionError("job artifact reference cannot traverse parents")
        return output_dir / path

    if not isinstance(accepted_count, int) or not isinstance(rejected_count, int):
        raise JournalCorruptionError("job artifact counts are invalid")
    return PipelineResult(
        samples_path=path_for("samples_path") or output_dir / "samples.jsonl",
        manifest_path=path_for("manifest_path") or output_dir / "manifest.json",
        rejections_path=path_for("rejections_path") or output_dir / "rejections.jsonl",
        quality_report_path=path_for("quality_report_path")
        or output_dir / "quality_report.json",
        tool_proposals_path=path_for("tool_proposals_path"),
        source_events_path=path_for("source_events_path"),
        sandbox_audits_path=path_for("sandbox_audits_path"),
        parent_comparison_path=path_for("parent_comparison_path"),
        review_queue_path=path_for("review_queue_path"),
        mutation_admission_report_path=path_for("mutation_admission_report_path"),
        episode_logs_path=path_for("episode_logs_path"),
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        coverage_plan_path=path_for("coverage_plan_path"),
        coverage_evidence_path=path_for("coverage_evidence_path"),
        coverage_reconciliation=None,
    )


def _work_item_id(job_id: str, sequence_index: int) -> str:
    return f"{job_id}:work:{sequence_index:06d}"


def _work_item_candidate_id(candidate_id: object, sequence_index: int) -> str:
    if isinstance(candidate_id, str) and candidate_id.strip():
        return candidate_id
    return f"candidate_sequence_{sequence_index:06d}"


def _sequence_index(record: Mapping[str, object]) -> int:
    return _integer_value(record.get("sequence_index"), "work_item.sequence_index")


def _integer_value(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise JournalCorruptionError(f"{field_name} must be an integer")
    return value


def _hash_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(value)).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_copy(value: object) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _assert_safe_orchestration_value(
    value: object,
    *,
    _path: tuple[str, ...] = (),
) -> None:
    """Reject secret-bearing or host-path state before it reaches the journal."""

    def semantic_authorization_metadata(
        path: tuple[str, ...],
        nested: object,
    ) -> bool:
        return (
            isinstance(nested, str)
            and path[-2:]
            in {
                ("mutation_admission", "contract_versions"),
                ("mutation_admission", "hashes"),
            }
            and (
                nested == "mutation_authorization_record_v1"
                or _SHA256_RE.fullmatch(nested) is not None
            )
        )

    forbidden_key_fragments = (
        "api_key",
        "api_token",
        "access_token",
        "authorization_header",
        "credential",
        "environment_variable",
        "private_key",
        "provider_payload",
        "provider_prompt",
        "provider_response",
        "private_payload",
        "raw_prompt",
        "raw_response",
        "raw_payload",
        "secret",
    )
    forbidden_exact_keys = {
        "authorization",
        "headers",
        "password",
        "raw_content",
    }
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).lower()
            allowed_semantic_authorization = (
                key == "authorization"
                and semantic_authorization_metadata(_path, nested)
            )
            if (
                key in forbidden_exact_keys
                and not allowed_semantic_authorization
            ) or any(
                fragment in key for fragment in forbidden_key_fragments
            ):
                raise JobConfigurationError(
                    "orchestration state contains a forbidden sensitive field: "
                    + key
                )
            _assert_safe_orchestration_value(nested, _path=(*_path, key))
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _assert_safe_orchestration_value(nested, _path=_path)
        return
    if isinstance(value, str):
        lowered = value.lower()
        if (
            value.startswith(("/", "~"))
            or ":\\" in value
            or "/users/" in lowered
            or "/private/" in lowered
            or "/tmp/" in lowered
            or "authorization:" in lowered
            or "secret-test-key" in lowered
            or "sk-live" in lowered
            or "sk-test" in lowered
        ):
            raise JobConfigurationError(
                "orchestration state contains a host path or secret-like value"
            )


def _looks_like_truncated_json(content: bytes) -> bool:
    """Return true only for an unterminated final JSON object append."""

    stripped = content.lstrip()
    if not stripped.startswith(b"{"):
        return False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return not stripped.rstrip().endswith(b"}")

    stack: list[str] = []
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            stack.append(character)
        elif character in "]}":
            if not stack or (character == "]" and stack[-1] != "[") or (
                character == "}" and stack[-1] != "{"
            ):
                return False
            stack.pop()
    return in_string or bool(stack)


def _atomic_write_json(path: Path, value: object) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _validate_job_id(value: object) -> None:
    if not isinstance(value, str) or _JOB_ID_RE.fullmatch(value) is None:
        raise ValueError("job_id must be 1-128 characters of letters, digits, _, ., or -")


def _validate_sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_exact_keys(
    record: Mapping[str, object],
    expected: set[str],
    field_name: str,
) -> None:
    actual = set(record)
    missing = expected - actual
    unexpected = actual - expected
    if missing or unexpected:
        raise ValueError(
            f"{field_name} keys mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _require_payload_keys(payload: Mapping[str, object], expected: set[str]) -> None:
    actual = set(payload)
    if actual != expected:
        raise InvalidTransitionError(
            f"event payload keys mismatch; expected={sorted(expected)}, actual={sorted(actual)}"
        )


def _mapping_value(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return value


def _list_value(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _optional_mapping_value(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("optional candidate field must be an object or null")
    return dict(value)


def _safe_error_class(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", value) else "OrchestrationError"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "CancellationSignal",
    "CONFIGURATION_IDENTITY_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "InvalidTransitionError",
    "JOB_SCHEMA_VERSION",
    "JobConfigurationError",
    "JobInterruption",
    "JobLockError",
    "JournalCorruptionError",
    "LOCK_SCHEMA_VERSION",
    "LogicalCallBudgetExceeded",
    "OrchestrationError",
    "PROVIDER_ATTEMPT_SCHEMA_VERSION",
    "PROVIDER_USAGE_SCHEMA_VERSION",
    "ProviderAttemptAmbiguous",
    "ProviderResponseLost",
    "SerialJobResult",
    "StaleJobLockError",
    "WORK_ITEM_SCHEMA_VERSION",
    "run_serial_job",
    "serial_job_lock_path",
    "validate_event_record",
    "validate_job_record",
    "validate_work_item_record",
]
