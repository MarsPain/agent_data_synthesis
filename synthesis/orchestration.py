"""Durable, opt-in serial orchestration for deterministic synthesis jobs.

The runner in this module owns job lifecycle state only. Candidate execution,
stable duplicate admission, and dataset assembly remain in
``synthesis.pipeline`` and its existing downstream seams.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    PolicyGenerator,
    ProvisionalCandidateOutcome,
)
from synthesis.pipeline import (
    CandidateGenerator,
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
)
from synthesis.tasks import CandidateTask, generate_scale_probe_candidates


JOB_SCHEMA_VERSION = "orchestration_job_v1"
WORK_ITEM_SCHEMA_VERSION = "orchestration_work_item_v1"
EVENT_SCHEMA_VERSION = "orchestration_event_v1"
TASK_CHECKPOINT_SCHEMA_VERSION = "task_contract_checkpoint_v1"
CANDIDATE_CHECKPOINT_SCHEMA_VERSION = "orchestration_candidate_checkpoint_v1"
INVALID_CANDIDATE_CHECKPOINT_SCHEMA_VERSION = "orchestration_invalid_candidate_v1"

JOB_STATUSES = {"pending", "running", "failed", "completed"}
WORK_ITEM_STATUSES = {"pending", "running", "completed"}
WORK_ITEM_RESULT_KINDS = {"accepted", "rejected"}
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class OrchestrationError(RuntimeError):
    """Base class for deterministic local orchestration errors."""


class JobConfigurationError(OrchestrationError, ValueError):
    """Raised when a job configuration is unsupported or drifts on resume."""


class JournalCorruptionError(OrchestrationError, ValueError):
    """Raised when durable journal history cannot be replayed safely."""


class InvalidTransitionError(OrchestrationError, ValueError):
    """Raised when a durable lifecycle transition is invalid."""


class JobInterruption(OrchestrationError):
    """Deterministic failure-injection signal leaving a job resumable."""

    def __init__(self, job_id: str, message: str = "serial job interrupted") -> None:
        super().__init__(message)
        self.job_id = job_id


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

    @property
    def status(self) -> str:
        return str(self.job_record["status"])

    @property
    def terminal(self) -> bool:
        return self.status in {"completed", "failed"}

    @property
    def job(self) -> Mapping[str, object]:
        """Compatibility alias for callers that prefer the shorter name."""

        return self.job_record


SerialJobInterruptionHook = Callable[[Mapping[str, object]], None]
TimestampFactory = Callable[[], str]


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
) -> SerialJobResult:
    """Run or resume one deterministic candidate set serially.

    A validated :class:`~synthesis.run_profiles.RunProfile` is the durable
    configuration identity. On creation the pipeline's generated candidate set
    is recorded before the first candidate is processed. On resume the stored
    candidate set and completed provisional outcomes are supplied back to the
    existing pipeline, which performs the normal stable merge and artifact
    assembly.
    """

    _validate_serial_configuration(
        job_id=job_id,
        run_profile=run_profile,
        interrupt_after=interrupt_after,
    )
    now = timestamp_factory or _utc_timestamp
    output_dir = Path(output_dir)
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
    orchestration_dir = output_dir / "orchestration" / job_id
    store = _LocalJobStore(orchestration_dir, timestamp_factory=now)

    if resume:
        if not store.exists:
            raise JobConfigurationError(
                f"cannot resume missing serial job: {job_id}"
            )
        store.load()
        store.validate_configuration(run_profile, execution_config_hash)
        if store.status == "completed":
            return store.result(output_dir)
        if store.status != "running":
            raise JobConfigurationError(
                f"serial job {job_id!r} is not resumable from status {store.status!r}"
            )
        store.resume()
        stored_tasks = tuple(
            _candidate_from_record(item["candidate"])
            for item in store.work_items
        )
        effective_candidate_generator: CandidateGenerator | None = (
            lambda _seed: list(stored_tasks)
        )
    else:
        if store.exists:
            raise JobConfigurationError(
                f"serial job already exists: {job_id}; pass resume=True"
            )
        store.create(
            job_id=job_id,
            run_profile=run_profile,
            execution_config_hash=execution_config_hash,
        )
        effective_candidate_generator = candidate_generator or _default_deterministic_generator(
            run_profile
        )

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
        if interrupt_after is not None and store.completed_work_item_count >= interrupt_after:
            store.interrupted(
                reason=f"interrupt_after={interrupt_after}",
            )
            raise JobInterruption(job_id)
        store.start_item(request.sequence_index, request.raw_task.candidate_id)
        if interruption_hook is not None:
            try:
                interruption_hook(store.item_for_sequence(request.sequence_index))
            except JobInterruption:
                raise
            except Exception as exc:
                store.interrupted(reason=type(exc).__name__)
                raise

    def complete_candidate(
        request: CandidateExecutionRequest,
        outcome: ProvisionalCandidateOutcome,
    ) -> None:
        store.complete_item(
            request.sequence_index,
            outcome,
            include_episode_log=write_episode_logs,
        )

    try:
        pipeline_result = run_foundation_pipeline(
            output_dir,
            dataset_version=run_profile.dataset_version,
            candidate_generator=effective_candidate_generator,
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
        )
    except JobInterruption:
        raise
    except Exception as exc:
        store.failed(error_class=type(exc).__name__)
        raise

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
            "dataset_version",
            "domain",
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
    _validate_sha256(record["config_hash"], "job.config_hash")
    _validate_sha256(
        record["execution_config_hash"],
        "job.execution_config_hash",
    )
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
    _require_non_empty_string(record["item_id"], "work_item.item_id")
    sequence_index = record["sequence_index"]
    if (
        not isinstance(sequence_index, int)
        or isinstance(sequence_index, bool)
        or sequence_index < 0
    ):
        raise ValueError("work_item.sequence_index must be a non-negative integer")
    _require_non_empty_string(record["candidate_id"], "work_item.candidate_id")
    if record["status"] not in WORK_ITEM_STATUSES:
        raise ValueError("work_item.status is unsupported")
    if not isinstance(record["candidate"], Mapping):
        raise ValueError("work_item.candidate must be an object")
    task_contract = record["task_contract"]
    if task_contract is not None and not isinstance(task_contract, Mapping):
        raise ValueError("work_item.task_contract must be an object or null")
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
    if record["status"] == "completed":
        if result_kind is None or not isinstance(record["outcome"], Mapping):
            raise ValueError("completed work_item must contain result_kind and outcome")
    elif record["outcome"] is not None:
        raise ValueError("non-completed work_item cannot contain an outcome")


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
    previous_hash = record["previous_integrity_hash"]
    if previous_hash is not None:
        _validate_sha256(previous_hash, "event.previous_integrity_hash")
    _validate_sha256(record["integrity_hash"], "event.integrity_hash")


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
        self._timestamp_factory = timestamp_factory
        self._job: dict[str, object] | None = None
        self._items: dict[str, dict[str, object]] = {}
        self._events: list[dict[str, object]] = []
        self._last_integrity_hash: str | None = None
        self._recovered_tail_bytes = 0

    @property
    def exists(self) -> bool:
        return self.orchestration_dir.exists()

    @property
    def job(self) -> dict[str, object]:
        if self._job is None:
            raise OrchestrationError("serial job store is not loaded")
        return self._job

    @property
    def work_items(self) -> tuple[dict[str, object], ...]:
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

    def create(
        self,
        *,
        job_id: str,
        run_profile: RunProfile,
        execution_config_hash: str,
    ) -> None:
        self.orchestration_dir.mkdir(parents=True, exist_ok=False)
        initial_job: dict[str, object] = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "status": "pending",
            "config_hash": run_profile.config_hash,
            "execution_config_hash": execution_config_hash,
            "dataset_version": run_profile.dataset_version,
            "domain": run_profile.seed.domain,
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

    def load(self) -> None:
        if not self.events_path.exists():
            raise JournalCorruptionError("serial job is missing its event journal")
        self._replay_events()
        if self._job is None:
            raise JournalCorruptionError("serial job journal has no job_created event")
        validate_job_record(self._job)
        for item in self.work_items:
            validate_work_item_record(item)
        if self._recovered_tail_bytes:
            self._append(
                "journal_tail_recovered",
                {"discarded_bytes": self._recovered_tail_bytes},
            )

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

    def resume(self) -> None:
        if self.status != "running":
            raise InvalidTransitionError("only a running serial job can be resumed")
        self._append("job_resumed", {})
        for item in self.work_items:
            if item["status"] == "running":
                self._append(
                    "work_item_requeued",
                    {"reason": "interrupted"},
                    work_item_id=str(item["item_id"]),
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
        if pipeline_result is None and self.status == "completed":
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
        )

    def _item_for_sequence(self, sequence_index: int) -> dict[str, object]:
        for item in self.work_items:
            if item["sequence_index"] == sequence_index:
                return item
        raise InvalidTransitionError(
            f"serial job has no work item at sequence index {sequence_index}"
        )

    def _append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        work_item_id: str | None = None,
    ) -> None:
        _assert_safe_orchestration_value(payload)
        sequence = len(self._events)
        event_without_integrity: dict[str, object] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "sequence": sequence,
            "event_id": f"event_{sequence:08d}",
            "job_id": str(payload.get("job_id", self._job["job_id"] if self._job else "")),
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
                    self.events_path.write_bytes(raw[:valid_prefix_end])
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

    def _apply_event(self, event: Mapping[str, object]) -> None:
        event_type = str(event["event_type"])
        payload = event["payload"]
        assert isinstance(payload, Mapping)
        work_item_id = event["work_item_id"]
        if event_type == "job_created":
            if self._job is not None or self._events[:-1]:
                raise JournalCorruptionError("job_created must be the first event")
            self._job = dict(payload)
            validate_job_record(self._job)
            return
        if self._job is None:
            raise JournalCorruptionError("event precedes job_created")
        if event_type == "job_started":
            self._require_job_status("pending")
            self._job["status"] = "running"
        elif event_type == "job_resumed":
            self._require_job_status("running")
        elif event_type == "candidate_set_bound":
            self._require_job_status("running")
            if self.candidate_set_hash is not None:
                raise InvalidTransitionError("candidate set is already bound")
            candidate_set_hash = payload.get("candidate_set_hash")
            _validate_sha256(candidate_set_hash, "candidate_set_hash")
            count = payload.get("target_candidate_count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise InvalidTransitionError("candidate set count is invalid")
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
            self._items[work_item_id] = item
        elif event_type == "work_item_started":
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
            item = self._require_item(work_item_id)
            if item["status"] != "running":
                raise InvalidTransitionError("only running work items can be requeued")
            item["status"] = "pending"
            item["started_at"] = None
        elif event_type == "work_item_completed":
            item = self._require_item(work_item_id)
            if item["status"] != "running":
                raise InvalidTransitionError("only running work items can complete")
            result_kind = payload.get("result_kind")
            outcome = payload.get("outcome")
            if result_kind not in WORK_ITEM_RESULT_KINDS or not isinstance(outcome, Mapping):
                raise InvalidTransitionError("work item completion payload is invalid")
            item["status"] = "completed"
            item["completed_at"] = self._timestamp_factory()
            item["result_kind"] = result_kind
            item["outcome"] = dict(outcome)
        elif event_type == "job_interrupted":
            self._require_job_status("running")
        elif event_type == "journal_tail_recovered":
            discarded_bytes = payload.get("discarded_bytes")
            if (
                not isinstance(discarded_bytes, int)
                or isinstance(discarded_bytes, bool)
                or discarded_bytes <= 0
            ):
                raise InvalidTransitionError(
                    "journal recovery byte count is invalid"
                )
        elif event_type == "job_failed":
            if self.status in {"completed", "failed"}:
                raise InvalidTransitionError("terminal job cannot fail")
            self._job["status"] = "failed"
        elif event_type == "job_completed":
            self._require_job_status("running")
            if any(item["status"] != "completed" for item in self.work_items):
                raise InvalidTransitionError("job cannot complete with pending work")
            references = payload.get("artifact_references")
            if not isinstance(references, Mapping):
                raise InvalidTransitionError("job completion artifacts are invalid")
            self._job["status"] = "completed"
            self._job["artifact_references"] = dict(references)
            self._job["accepted_count"] = payload.get("accepted_count", 0)
            self._job["rejected_count"] = payload.get("rejected_count", 0)
        else:
            raise JournalCorruptionError(f"unsupported serial job event: {event_type}")
        self._refresh_job()

    def _require_job_status(self, expected: str) -> None:
        if self.status != expected:
            raise InvalidTransitionError(
                f"job status {self.status!r} cannot accept transition from {expected!r}"
            )

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


def _validate_serial_configuration(
    *,
    job_id: str,
    run_profile: RunProfile,
    interrupt_after: int | None,
) -> None:
    _validate_job_id(job_id)
    if not isinstance(run_profile, RunProfile):
        raise JobConfigurationError("run_profile must be a validated RunProfile")
    if run_profile.generation.mode == "llm":
        raise JobConfigurationError(
            "serial deterministic orchestration does not support llm generation"
        )
    if run_profile.coverage_profile is not None:
        raise JobConfigurationError(
            "coverage orchestration is deferred to a later serial-job slice"
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
        return {"kind": "path", "value": str(value)}
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
    intent = _mapping_value(record["intent"], "intent")
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
    return TaskContract(
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


def _assert_safe_orchestration_value(value: object) -> None:
    """Reject secret-bearing or host-path state before it reaches the journal."""

    forbidden_key_fragments = (
        "api_key",
        "authorization_header",
        "credential",
        "environment_variable",
        "provider_payload",
        "provider_prompt",
        "provider_response",
        "raw_prompt",
        "raw_response",
        "raw_payload",
        "secret",
    )
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).lower()
            if any(fragment in key for fragment in forbidden_key_fragments):
                raise JobConfigurationError(
                    "orchestration state contains a forbidden sensitive field"
                )
            _assert_safe_orchestration_value(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _assert_safe_orchestration_value(nested)
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
    "EVENT_SCHEMA_VERSION",
    "InvalidTransitionError",
    "JOB_SCHEMA_VERSION",
    "JobConfigurationError",
    "JobInterruption",
    "JournalCorruptionError",
    "OrchestrationError",
    "SerialJobResult",
    "WORK_ITEM_SCHEMA_VERSION",
    "run_serial_job",
    "validate_event_record",
    "validate_job_record",
    "validate_work_item_record",
]
