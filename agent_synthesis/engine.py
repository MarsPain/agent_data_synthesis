"""Bounded, resumable Agent rollout engine for the provisional Agent-first seam."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fcntl

from pydantic import BaseModel, JsonValue, ValidationError

from agent_synthesis.configuration import RunConfiguration
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
    physical_request_count: int
    run_report_path: Path


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
        with _RunDirectoryWriterLock(run_directory):
            ledger = PrivateLedger.create(paths.private_ledger_path)
            try:
                domain_run = domain.open_run(config)
                frozen_initial_state = domain_run.freeze_initial_state()
                ledger.record_run_metadata(config, domain_version=domain.domain_version)
                ledger.record_initial_state(frozen_initial_state)
                _write_frozen_snapshot(paths.frozen_snapshot_path, frozen_initial_state)
                known_task_capacity = _known_task_capacity(domain_run, config.slot_limit)
                ledger.record_run_status(
                    status="running",
                    known_task_capacity=known_task_capacity,
                )
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
                if domain.domain_version != metadata.domain_version:
                    raise ValueError("resume Domain version does not match the saved run")
                frozen_initial_state = _read_frozen_snapshot(paths.frozen_snapshot_path, ledger)
                domain_run = _open_run_from_frozen_state(
                    domain,
                    configuration,
                    frozen_initial_state,
                )
                known_task_capacity = _known_task_capacity(domain_run, configuration.slot_limit)
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


@dataclass(frozen=True)
class _RunPaths:
    run_directory: Path
    demonstrations_path: Path
    negatives_path: Path
    provider_usage_path: Path
    run_report_path: Path
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
            manifest_path=directory / "manifest.json",
            private_ledger_path=private_directory / "ledger.sqlite3",
            frozen_snapshot_path=private_directory / "frozen_state.json",
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
    except Exception:  # noqa: BLE001 - legacy adapters must fail closed on resume.
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
) -> RunResult:
    """Dispatch only bounded work and leave incomplete ownership resumable."""

    owner_prefix = f"run-{uuid.uuid4().hex}"
    active_semantic_keys: set[str] = set()
    admitted_semantic_keys = set(ledger.admitted_semantic_keys())
    accepted_count = sum(
        outcome.episode.admission.status == "admitted"
        for outcome in ledger.terminal_outcomes()
    )
    futures: dict[Future[_EpisodeAttemptResult], tuple[int, str, str]] = {}
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
        _checkpoint(failure_injector, "before_terminal_commit")
        ledger.commit_terminal_outcome(
            sequence=committed_episode.sequence,
            episode=committed_episode,
            semantic_key=semantic_key,
        )
        _checkpoint(failure_injector, "after_terminal_commit")
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
        for item in pending:
            ledger.claim_work(
                sequence=item.sequence,
                owner_id=owner_id,
                status="generating",
            )
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
        )
        if generation.response is None:
            if generation.error_code == "provider_request_budget_exhausted":
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
            else max(0, configuration.accepted_target - accepted_count)
        )
        available_workers = min(
            configuration.max_concurrency - len(futures),
            remaining_target,
        )
        if available_workers <= 0:
            return None
        probe_size = max(configuration.max_concurrency * 16, 64)
        for work in ledger.work_items_with_status("compiled", limit=probe_size):
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
            owner_id = f"{owner_prefix}:episode:{work.sequence}"
            ledger.claim_work(sequence=work.sequence, owner_id=owner_id, status="running")
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
            futures[future] = (work.sequence, case.semantic_key, owner_id)
            active_semantic_keys.add(case.semantic_key)
            available_workers -= 1
        return None

    def collect_completed(done: set[Future[_EpisodeAttemptResult]]) -> None:
        nonlocal stop_reason
        for future in done:
            sequence, semantic_key, owner_id = futures.pop(future)
            active_semantic_keys.discard(semantic_key)
            result = future.result()
            if result.partial_reason is not None:
                ledger.return_work_to_ready(sequence=sequence, owner_id=owner_id)
                if stop_reason is None:
                    stop_reason = result.partial_reason
                continue
            assert result.episode is not None
            commit_terminal(result.episode, semantic_key)

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
    )


def _incomplete_target_reason(
    *,
    configuration: RunConfiguration,
    ledger: PrivateLedger,
    known_task_capacity: int | None,
) -> str:
    allocated_count = len(ledger.allocated_slots())
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
) -> RunResult:
    outcomes = ledger.terminal_outcomes()
    _write_terminal_collections(paths, outcomes)
    requests = ledger.provider_requests()
    _write_provider_usage(paths.provider_usage_path, requests)
    _write_run_report(
        paths.run_report_path,
        configuration=configuration,
        status=status,
        partial_reason=partial_reason,
        known_task_capacity=known_task_capacity,
        allocated_slot_count=len(ledger.allocated_slots()),
        outcomes=outcomes,
        requests=requests,
    )
    manifest = build_manifest(
        run_id=configuration.run_id,
        configuration=configuration.normalized_public_record(),
        source_fingerprint=frozen_initial_state.fingerprint,
        artifact_paths=(
            paths.demonstrations_path,
            paths.negatives_path,
            paths.provider_usage_path,
        ),
    )
    write_manifest(paths.manifest_path, manifest)
    demonstrations = sum(
        outcome.episode.outcome.collection == "demonstrations" for outcome in outcomes
    )
    negatives = len(outcomes) - demonstrations
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
        task_attempt_count=len(outcomes),
        physical_request_count=len(requests),
        run_report_path=paths.run_report_path,
    )


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
            ),
            partial_reason=None,
        )

    safe_task = sanitized_public_task(task.public_task)
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
        )
        records.extend(call.records)
        if call.response is None:
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
            events.append(
                bounded_event_for_public_tools(
                    EpisodeEvent(event_type="final_response", content=decision.content),
                    safe_task.tools,
                )
            )
            final_response_received = True
            break

        assert isinstance(decision, ToolCallDecision)
        action = bounded_event_for_public_tools(
            EpisodeEvent(
                event_type="action",
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            ),
            safe_task.tools,
        )
        events.append(action)
        tool_event, authorization = _execute_tool_decision(
            episode=episode,
            task=safe_task,
            decision=decision,
        )
        events.append(tool_event)
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
        ),
        partial_reason=None,
    )


def _execute_tool_decision(
    *,
    episode: DomainEpisode,
    task: PublicTask,
    decision: ToolCallDecision,
) -> tuple[EpisodeEvent, Literal["not_applicable", "authorized", "rejected"]]:
    tool = next((tool for tool in task.tools if tool.name == decision.tool_name), None)
    if tool is None:
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=decision.tool_name,
                error_code="unknown_tool",
            ),
            "not_applicable",
        )
    if not _valid_tool_arguments(tool, decision.arguments):
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code="invalid_tool_arguments",
            ),
            "not_applicable",
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
        )
    return (
        EpisodeEvent(
            event_type="error",
            tool_name=tool.name,
            error_code=result.error_code,
        ),
        "not_applicable",
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
) -> _LogicalCallResult:
    """Reserve every physical dispatch and retry only bounded transport failures."""

    records: list[ProviderRequestRecord] = []
    role_limit = (
        configuration.generation_request_limit
        if request.role == "task_generation"
        else configuration.agent_request_limit
    )
    for physical_attempt in range(configuration.transport_retry_limit + 1):
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
) -> PublicEpisode:
    admitted = (
        terminal_reason is None
        and assessment.passed
        and trace.mutation_authorization != "rejected"
    )
    reason_code = terminal_reason
    if not admitted and reason_code is None:
        reason_code = (
            "unauthorized_mutation"
            if trace.mutation_authorization == "rejected"
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
            mode=context.configuration.admission_mode,
            status="admitted" if admitted else "rejected",
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
    )


def _pre_execution_negative(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    reason_code: str,
    lineage: ModelLineage,
) -> PublicEpisode:
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
            mode=context.configuration.admission_mode,
            status="rejected",
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
        usages = [record.usage for record in role_records]
        roles.append(
            RoleLineage(
                role=role,
                provider_id=model.provider_id,
                model_id=model.model_id,
                model_version=model.model_version,
                physical_request_count=len(role_records),
                retry_count=len(role_records)
                - len({record.logical_request_id for record in role_records}),
                response_hashes=tuple(
                    record.response_hash
                    for record in role_records
                    if record.response_hash is not None
                ),
                known_input_tokens=_known_token_total(usages, "input_tokens"),
                known_output_tokens=_known_token_total(usages, "output_tokens"),
                known_total_tokens=_known_token_total(usages, "total_tokens"),
                unknown_usage_count=sum(
                    1
                    for usage in usages
                    if usage is None or usage.total_tokens is None
                ),
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
        actual_result, authorization = _execute_tool_decision(
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
    outcomes: tuple[TerminalOutcomeRecord, ...],
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
    by_role: dict[ModelRole, list[ProviderRequestRecord]] = defaultdict(list)
    for record in records:
        by_role[record.role].append(record)
    roles = {
        role: _usage_summary(role_records)
        for role, role_records in sorted(by_role.items())
    }
    return {
        "schema_version": "agent_provider_usage_v1",
        "total_physical_requests": len(records),
        "reserved_request_count": sum(record.status == "reserved" for record in records),
        "failed_request_count": sum(record.status == "failed" for record in records),
        "completed_request_count": sum(record.status == "completed" for record in records),
        "roles": roles,
    }


def _usage_summary(records: list[ProviderRequestRecord]) -> dict[str, object]:
    usages = [record.usage for record in records]
    return {
        "physical_request_count": len(records),
        "retry_count": len(records)
        - len({record.logical_request_id for record in records}),
        "repair_request_count": sum(
            1 for record in records if record.request_kind == "repair"
        ),
        "reserved_request_count": sum(record.status == "reserved" for record in records),
        "failed_request_count": sum(record.status == "failed" for record in records),
        "completed_request_count": sum(record.status == "completed" for record in records),
        "known_input_tokens": _known_token_total(usages, "input_tokens"),
        "known_output_tokens": _known_token_total(usages, "output_tokens"),
        "known_total_tokens": _known_token_total(usages, "total_tokens"),
        "unknown_usage_count": sum(
            1 for usage in usages if usage is None or usage.total_tokens is None
        ),
    }


def _write_run_report(
    path: Path,
    *,
    configuration: RunConfiguration,
    status: Literal["completed", "partial", "cancelled", "failed"],
    partial_reason: str | None,
    known_task_capacity: int | None,
    allocated_slot_count: int,
    outcomes: tuple[TerminalOutcomeRecord, ...],
    requests: tuple[ProviderRequestRecord, ...],
) -> None:
    accepted_count = sum(
        outcome.episode.outcome.collection == "demonstrations" for outcome in outcomes
    )
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
            "task_attempt_count": len(outcomes),
            "accepted_count": accepted_count,
            "negative_count": len(outcomes) - accepted_count,
            "incomplete_slot_count": allocated_slot_count - len(outcomes),
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
