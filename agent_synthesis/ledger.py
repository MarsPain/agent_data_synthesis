"""Private SQLite persistence for resumable Agent-first synthesis runs."""

from __future__ import annotations

import base64
import sqlite3
import threading
from pathlib import Path
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.domain import CompiledTask, FrozenInitialState, TaskSlot
from agent_synthesis.episode import PublicEpisode, PublicTask, sanitized_episode_record
from agent_synthesis.model import ModelRole, TokenUsage
from agent_synthesis.quality import QualityJudgment


class FrozenStateRecord(BaseModel):
    """Validated private representation of a Domain's frozen initial state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contents_b64: str = Field(min_length=1)

    @classmethod
    def from_initial_state(cls, state: FrozenInitialState) -> "FrozenStateRecord":
        return cls(
            fingerprint=state.fingerprint,
            contents_b64=base64.b64encode(state.contents).decode("ascii"),
        )

    def to_initial_state(self) -> FrozenInitialState:
        return FrozenInitialState(
            fingerprint=self.fingerprint,
            contents=base64.b64decode(self.contents_b64, validate=True),
        )


class RunMetadataRecord(BaseModel):
    """Private binding of immutable run configuration and Domain version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configuration: dict[str, JsonValue]
    domain_version: str = Field(min_length=1, max_length=128)

    @classmethod
    def from_configuration(
        cls,
        configuration: RunConfiguration,
        *,
        domain_version: str,
    ) -> "RunMetadataRecord":
        return cls(
            configuration=configuration.normalized_public_record(),
            domain_version=domain_version,
        )

    def configuration_model(self) -> RunConfiguration:
        return RunConfiguration.model_validate(self.configuration)


class RunStatusRecord(BaseModel):
    """Durable lifecycle status that remains honest across interruption."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["running", "completed", "partial", "cancelled", "failed"]
    reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    known_task_capacity: int | None = Field(default=None, ge=0)


class AllocatedSlotRecord(BaseModel):
    """A persisted slot identity that consumes at most one task-attempt allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=256)
    proposal_prompt: str = Field(min_length=1, max_length=8_000)

    @classmethod
    def from_slot(cls, *, sequence: int, slot: TaskSlot) -> "AllocatedSlotRecord":
        return cls(
            sequence=sequence,
            slot_id=slot.slot_id,
            proposal_prompt=slot.proposal_prompt,
        )

    def to_slot(self) -> TaskSlot:
        return TaskSlot(slot_id=self.slot_id, proposal_prompt=self.proposal_prompt)


class TaskCaseRecord(BaseModel):
    """Validated private record for one compiled Domain task case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=256)
    public_task: PublicTask
    semantic_key: str = Field(min_length=1, max_length=512)
    case_b64: str = Field(min_length=1)

    @classmethod
    def from_compiled_task(
        cls,
        *,
        sequence: int,
        slot_id: str,
        task: CompiledTask,
    ) -> "TaskCaseRecord":
        return cls(
            sequence=sequence,
            slot_id=slot_id,
            public_task=task.public_task,
            semantic_key=task.semantic_key,
            case_b64=base64.b64encode(task.private_case_bytes).decode("ascii"),
        )

    def private_case_bytes(self) -> bytes:
        return base64.b64decode(self.case_b64, validate=True)


class WorkItemRecord(BaseModel):
    """Durable ownership for one allocated Candidate sequence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=256)
    status: Literal["pending", "generating", "compiled", "running", "terminal"]
    owner_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def _match_ownership_to_state(self) -> "WorkItemRecord":
        if self.status in {"generating", "running"} and self.owner_id is None:
            raise ValueError("in-flight work requires an owner")
        if self.status not in {"generating", "running"} and self.owner_id is not None:
            raise ValueError("ready or terminal work cannot retain an owner")
        return self


class TerminalOutcomeRecord(BaseModel):
    """One atomically committed public Candidate outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    semantic_key: str | None = Field(default=None, min_length=1, max_length=512)
    episode: PublicEpisode


class ProviderRequestRecord(BaseModel):
    """One durable physical request reservation, including unknown outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: int = Field(ge=1)
    role: ModelRole
    logical_request_id: str = Field(min_length=1, max_length=256)
    attempt: int = Field(ge=1)
    sequence: int | None = Field(default=None, ge=1)
    related_sequences: tuple[int, ...] = Field(default=(), max_length=64)
    request_kind: Literal["initial", "repair"]
    status: Literal["reserved", "completed", "failed"]
    response_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    usage: TokenUsage | None = None
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    @model_validator(mode="after")
    def _require_terminal_details(self) -> "ProviderRequestRecord":
        if len(set(self.related_sequences)) != len(self.related_sequences):
            raise ValueError("related request sequences must be unique")
        if self.sequence is not None and self.sequence in self.related_sequences:
            raise ValueError("primary request sequence must not be repeated")
        if self.status == "reserved":
            if self.response_hash is not None or self.usage is not None or self.error_code is not None:
                raise ValueError("reserved request cannot have terminal details")
        elif self.status == "completed" and self.error_code is not None:
            raise ValueError("completed request cannot have an error code")
        elif self.status == "failed" and self.error_code is None:
            raise ValueError("failed request requires an error code")
        return self


class PrivateLedger:
    """SQLite operational ledger with durable ownership and request reservations."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection
        self._lock = threading.RLock()

    @classmethod
    def create(cls, path: Path) -> "PrivateLedger":
        if path.exists():
            raise FileExistsError(f"private ledger already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = _open_connection(path)
        ledger = cls(path, connection)
        ledger._create_schema()
        return ledger

    @classmethod
    def open(cls, path: Path) -> "PrivateLedger":
        if not path.exists():
            raise FileNotFoundError(f"private ledger does not exist: {path}")
        connection = _open_connection(path)
        ledger = cls(path, connection)
        ledger._create_schema()
        return ledger

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_metadata (
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_status (
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS frozen_state (
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS allocated_slots (
                    sequence INTEGER PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_cases (
                    sequence INTEGER PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    sequence INTEGER PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS terminal_outcomes (
                    sequence INTEGER PRIMARY KEY,
                    semantic_key TEXT,
                    admitted INTEGER NOT NULL,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS quality_judgments (
                    sequence INTEGER PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS work_items_status
                ON work_items(json_extract(record_json, '$.status'))
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS terminal_outcomes_admitted_semantic_key
                ON terminal_outcomes(semantic_key)
                WHERE admitted = 1 AND semantic_key IS NOT NULL
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_request_sequences (
                    request_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    PRIMARY KEY (request_id, sequence)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS provider_request_sequences_sequence
                ON provider_request_sequences(sequence, request_id)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS provider_requests_role
                ON provider_requests(json_extract(record_json, '$.role'))
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS provider_requests_logical_request
                ON provider_requests(json_extract(record_json, '$.logical_request_id'))
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def record_run_metadata(
        self,
        configuration: RunConfiguration,
        *,
        domain_version: str,
    ) -> None:
        record = RunMetadataRecord.from_configuration(
            configuration,
            domain_version=domain_version,
        )
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM run_metadata")
            self._connection.execute(
                "INSERT INTO run_metadata(record_json) VALUES (?)",
                (record.model_dump_json(),),
            )

    def run_metadata(self) -> RunMetadataRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM run_metadata"
            ).fetchone()
        if row is None:
            raise LookupError("private ledger has no run metadata")
        return RunMetadataRecord.model_validate_json(row[0])

    def record_run_status(
        self,
        *,
        status: Literal["running", "completed", "partial", "cancelled", "failed"],
        reason_code: str | None = None,
        known_task_capacity: int | None = None,
    ) -> RunStatusRecord:
        record = RunStatusRecord(
            status=status,
            reason_code=reason_code,
            known_task_capacity=known_task_capacity,
        )
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM run_status")
            self._connection.execute(
                "INSERT INTO run_status(record_json) VALUES (?)",
                (record.model_dump_json(),),
            )
        return record

    def run_status(self) -> RunStatusRecord:
        with self._lock:
            row = self._connection.execute("SELECT record_json FROM run_status").fetchone()
        if row is None:
            raise LookupError("private ledger has no run status")
        return RunStatusRecord.model_validate_json(row[0])

    def record_initial_state(self, state: FrozenInitialState) -> None:
        record = FrozenStateRecord.from_initial_state(state)
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM frozen_state")
            self._connection.execute(
                "INSERT INTO frozen_state(record_json) VALUES (?)",
                (record.model_dump_json(),),
            )

    def initial_state_record(self) -> FrozenStateRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM frozen_state"
            ).fetchone()
        if row is None:
            raise LookupError("private ledger has no frozen initial state")
        return FrozenStateRecord.model_validate_json(row[0])

    def initial_state(self) -> FrozenInitialState:
        return self.initial_state_record().to_initial_state()

    def record_allocated_slots(self, slots: tuple[AllocatedSlotRecord, ...]) -> None:
        if len({record.sequence for record in slots}) != len(slots):
            raise ValueError("allocated slot sequences must be unique")
        if len({record.slot_id for record in slots}) != len(slots):
            raise ValueError("allocated slot ids must be unique")
        work_items = tuple(
            WorkItemRecord(
                sequence=record.sequence,
                slot_id=record.slot_id,
                status="pending",
            )
            for record in slots
        )
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT INTO allocated_slots(sequence, record_json) VALUES (?, ?)",
                ((record.sequence, record.model_dump_json()) for record in slots),
            )
            self._connection.executemany(
                "INSERT INTO work_items(sequence, record_json) VALUES (?, ?)",
                ((record.sequence, record.model_dump_json()) for record in work_items),
            )

    def allocated_slots(self) -> tuple[AllocatedSlotRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM allocated_slots ORDER BY sequence"
            ).fetchall()
        return tuple(AllocatedSlotRecord.model_validate_json(row[0]) for row in rows)

    def allocated_slot_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM allocated_slots").fetchone()
        assert row is not None
        return int(row[0])

    def allocated_slot(self, sequence: int) -> AllocatedSlotRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM allocated_slots WHERE sequence = ?", (sequence,)
            ).fetchone()
        if row is None:
            raise LookupError(f"unknown allocated slot sequence: {sequence}")
        return AllocatedSlotRecord.model_validate_json(row[0])

    def work_items(self) -> tuple[WorkItemRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM work_items ORDER BY sequence"
            ).fetchall()
        return tuple(WorkItemRecord.model_validate_json(row[0]) for row in rows)

    def work_items_with_status(
        self,
        status: Literal["pending", "generating", "compiled", "running", "terminal"],
        *,
        limit: int | None = None,
    ) -> tuple[WorkItemRecord, ...]:
        query = (
            "SELECT record_json FROM work_items "
            "WHERE json_extract(record_json, '$.status') = ? ORDER BY sequence"
        )
        parameters: tuple[object, ...] = (status,)
        if limit is not None:
            if limit < 1:
                raise ValueError("work item query limit must be positive")
            query += " LIMIT ?"
            parameters += (limit,)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return tuple(WorkItemRecord.model_validate_json(row[0]) for row in rows)

    def work_item(self, sequence: int) -> WorkItemRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM work_items WHERE sequence = ?", (sequence,)
            ).fetchone()
        if row is None:
            raise LookupError(f"unknown work item sequence: {sequence}")
        return WorkItemRecord.model_validate_json(row[0])

    def claim_work(
        self,
        *,
        sequence: int,
        owner_id: str,
        status: Literal["generating", "running"],
    ) -> WorkItemRecord:
        with self._lock, self._connection:
            current = self._work_item_in_transaction(sequence)
            expected = "pending" if status == "generating" else "compiled"
            if current.status != expected:
                raise ValueError(
                    f"work item {sequence} must be {expected} before {status}, got {current.status}"
                )
            claimed = current.model_copy(update={"status": status, "owner_id": owner_id})
            self._write_work_item(claimed)
        return claimed

    def return_work_to_ready(self, *, sequence: int, owner_id: str) -> WorkItemRecord:
        with self._lock, self._connection:
            current = self._work_item_in_transaction(sequence)
            if current.owner_id != owner_id:
                raise ValueError(f"work item {sequence} is not owned by {owner_id}")
            ready = self._ready_work_item_in_transaction(current)
            self._write_work_item(ready)
        return ready

    def recover_inflight_work(self) -> tuple[WorkItemRecord, ...]:
        """Clear abandoned owners after the process-lifetime writer lock is acquired."""

        recovered: list[WorkItemRecord] = []
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT record_json FROM work_items ORDER BY sequence"
            ).fetchall()
            for row in rows:
                current = WorkItemRecord.model_validate_json(row[0])
                if current.status not in {"generating", "running"}:
                    continue
                ready = self._ready_work_item_in_transaction(current)
                self._write_work_item(ready)
                recovered.append(ready)
        return tuple(recovered)

    def record_task_case(
        self,
        *,
        sequence: int,
        slot_id: str,
        task: CompiledTask,
    ) -> None:
        record = TaskCaseRecord.from_compiled_task(
            sequence=sequence,
            slot_id=slot_id,
            task=task,
        )
        with self._lock, self._connection:
            work = self._work_item_in_transaction(sequence)
            if work.slot_id != slot_id:
                raise ValueError("task case slot id does not match allocated work")
            if work.status != "generating":
                raise ValueError("task cases may only be recorded by generating work")
            self._connection.execute(
                "INSERT INTO task_cases(sequence, record_json) VALUES (?, ?)",
                (record.sequence, record.model_dump_json()),
            )
            self._write_work_item(
                work.model_copy(update={"status": "compiled", "owner_id": None})
            )

    def task_cases(self) -> tuple[TaskCaseRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM task_cases ORDER BY sequence"
            ).fetchall()
        return tuple(TaskCaseRecord.model_validate_json(row[0]) for row in rows)

    def task_case(self, sequence: int) -> TaskCaseRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM task_cases WHERE sequence = ?", (sequence,)
            ).fetchone()
        return None if row is None else TaskCaseRecord.model_validate_json(row[0])

    def commit_terminal_outcome(
        self,
        *,
        sequence: int,
        episode: PublicEpisode,
        semantic_key: str | None,
    ) -> TerminalOutcomeRecord:
        """Commit public outcome and terminal work state in one SQLite transaction."""

        safe_episode = PublicEpisode.model_validate(sanitized_episode_record(episode))
        if safe_episode.sequence != sequence:
            raise ValueError("terminal Episode sequence does not match work item")
        record = TerminalOutcomeRecord(
            sequence=sequence,
            semantic_key=semantic_key,
            episode=safe_episode,
        )
        admitted = int(safe_episode.admission.status == "admitted")
        with self._lock, self._connection:
            work = self._work_item_in_transaction(sequence)
            if work.status == "terminal":
                raise ValueError(f"work item {sequence} already has a terminal outcome")
            if self._terminal_outcome_exists_in_transaction(sequence):
                raise ValueError(f"terminal outcome already exists for sequence {sequence}")
            self._connection.execute(
                """
                INSERT INTO terminal_outcomes(sequence, semantic_key, admitted, record_json)
                VALUES (?, ?, ?, ?)
                """,
                (sequence, semantic_key, admitted, record.model_dump_json()),
            )
            self._write_work_item(
                work.model_copy(update={"status": "terminal", "owner_id": None})
            )
        return record

    def terminal_outcomes(self) -> tuple[TerminalOutcomeRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM terminal_outcomes ORDER BY sequence"
            ).fetchall()
        return tuple(TerminalOutcomeRecord.model_validate_json(row[0]) for row in rows)

    def iter_terminal_outcomes(self) -> Iterator[TerminalOutcomeRecord]:
        """Yield terminal records in stable sequence without materializing a run."""

        with self._lock:
            cursor = self._connection.execute(
                "SELECT record_json FROM terminal_outcomes ORDER BY sequence"
            )
            for row in cursor:
                yield TerminalOutcomeRecord.model_validate_json(row[0])

    def terminal_outcome_summary(self) -> tuple[int, int]:
        """Return terminal and admitted counts without loading public Episodes."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(
                        SUM(
                            CASE
                                WHEN json_extract(record_json, '$.episode.admission.status') = 'admitted'
                                THEN 1
                                ELSE 0
                            END
                        ),
                        0
                    )
                FROM terminal_outcomes
                """
            ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1])

    def terminal_outcome(self, sequence: int) -> TerminalOutcomeRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM terminal_outcomes WHERE sequence = ?", (sequence,)
            ).fetchone()
        return None if row is None else TerminalOutcomeRecord.model_validate_json(row[0])

    def record_quality_judgment(self, judgment: QualityJudgment) -> QualityJudgment:
        """Persist exactly one shadow result for a completed Episode sequence."""

        with self._lock, self._connection:
            terminal = self._terminal_outcome_exists_in_transaction(judgment.sequence)
            if not terminal:
                raise ValueError("quality judgment requires a terminal Episode")
            if self._connection.execute(
                "SELECT 1 FROM quality_judgments WHERE sequence = ?",
                (judgment.sequence,),
            ).fetchone() is not None:
                raise ValueError(
                    f"quality judgment already exists for sequence {judgment.sequence}"
                )
            self._connection.execute(
                "INSERT INTO quality_judgments(sequence, record_json) VALUES (?, ?)",
                (judgment.sequence, judgment.model_dump_json()),
            )
        return judgment

    def quality_judgment(self, sequence: int) -> QualityJudgment | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT record_json FROM quality_judgments WHERE sequence = ?",
                (sequence,),
            ).fetchone()
        return None if row is None else QualityJudgment.model_validate_json(row[0])

    def quality_judgments(self) -> tuple[QualityJudgment, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM quality_judgments ORDER BY sequence"
            ).fetchall()
        return tuple(QualityJudgment.model_validate_json(row[0]) for row in rows)

    def admitted_semantic_keys(self) -> frozenset[str]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT semantic_key FROM terminal_outcomes
                WHERE admitted = 1 AND semantic_key IS NOT NULL
                """
            ).fetchall()
        return frozenset(str(row[0]) for row in rows)

    def reserve_provider_request(
        self,
        *,
        role: ModelRole,
        logical_request_id: str,
        role_limit: int,
        total_limit: int,
        sequence: int | None,
        related_sequences: tuple[int, ...] = (),
        request_kind: Literal["initial", "repair"],
    ) -> ProviderRequestRecord | None:
        """Commit one charged physical request before model dispatch."""

        with self._lock, self._connection:
            if not self._request_budget_available_in_transaction(
                role=role,
                role_limit=role_limit,
                total_limit=total_limit,
            ):
                return None
            attempt = self._connection.execute(
                """
                SELECT COUNT(*) FROM provider_requests
                WHERE json_extract(record_json, '$.logical_request_id') = ?
                """,
                (logical_request_id,),
            ).fetchone()[0] + 1
            cursor = self._connection.execute(
                "INSERT INTO provider_requests(record_json) VALUES (?)",
                ("{}",),
            )
            request_id = cursor.lastrowid
            assert isinstance(request_id, int)
            record = ProviderRequestRecord(
                request_id=request_id,
                role=role,
                logical_request_id=logical_request_id,
                attempt=attempt,
                sequence=sequence,
                related_sequences=related_sequences,
                request_kind=request_kind,
                status="reserved",
            )
            self._connection.execute(
                "UPDATE provider_requests SET record_json = ? WHERE request_id = ?",
                (record.model_dump_json(), request_id),
            )
            request_sequences = related_sequences
            if sequence is not None:
                request_sequences = (sequence, *request_sequences)
            self._connection.executemany(
                """
                INSERT INTO provider_request_sequences(request_id, sequence)
                VALUES (?, ?)
                """,
                ((request_id, request_sequence) for request_sequence in request_sequences),
            )
        return record

    def finish_provider_request(
        self,
        request_id: int,
        *,
        status: Literal["completed", "failed"],
        response_hash: str | None = None,
        usage: TokenUsage | None = None,
        error_code: str | None = None,
    ) -> ProviderRequestRecord:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT record_json FROM provider_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown provider request reservation: {request_id}")
            prior = ProviderRequestRecord.model_validate_json(row[0])
            if prior.status != "reserved":
                raise ValueError(f"provider request {request_id} was already finished")
            record = prior.model_copy(
                update={
                    "status": status,
                    "response_hash": response_hash,
                    "usage": usage,
                    "error_code": error_code,
                }
            )
            record = ProviderRequestRecord.model_validate(record.model_dump(mode="json"))
            self._connection.execute(
                "UPDATE provider_requests SET record_json = ? WHERE request_id = ?",
                (record.model_dump_json(), request_id),
            )
        return record

    def provider_requests(self) -> tuple[ProviderRequestRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM provider_requests ORDER BY request_id"
            ).fetchall()
        return tuple(ProviderRequestRecord.model_validate_json(row[0]) for row in rows)

    def provider_requests_for_sequence(self, sequence: int) -> tuple[ProviderRequestRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT provider_requests.record_json
                FROM provider_request_sequences
                JOIN provider_requests
                  ON provider_requests.request_id = provider_request_sequences.request_id
                WHERE provider_request_sequences.sequence = ?
                ORDER BY provider_requests.request_id
                """,
                (sequence,),
            ).fetchall()
            if not rows:
                rows = self._connection.execute(
                    """
                    SELECT provider_requests.record_json
                    FROM provider_requests
                    WHERE json_extract(provider_requests.record_json, '$.sequence') = ?
                       OR EXISTS (
                            SELECT 1
                            FROM json_each(
                                provider_requests.record_json,
                                '$.related_sequences'
                            )
                            WHERE value = ?
                       )
                    ORDER BY provider_requests.request_id
                    """,
                    (sequence, sequence),
                ).fetchall()
        return tuple(ProviderRequestRecord.model_validate_json(row[0]) for row in rows)

    def has_remaining_request_budget(
        self,
        *,
        role: ModelRole,
        role_limit: int,
        total_limit: int,
    ) -> bool:
        with self._lock:
            return self._request_budget_available_in_transaction(
                role=role,
                role_limit=role_limit,
                total_limit=total_limit,
            )

    def _request_budget_available_in_transaction(
        self,
        *,
        role: ModelRole,
        role_limit: int,
        total_limit: int,
    ) -> bool:
        total_count = self._connection.execute(
            "SELECT COUNT(*) FROM provider_requests"
        ).fetchone()[0]
        role_count = self._connection.execute(
            """
            SELECT COUNT(*) FROM provider_requests
            WHERE json_extract(record_json, '$.role') = ?
            """,
            (role,),
        ).fetchone()[0]
        return total_count < total_limit and role_count < role_limit

    def _work_item_in_transaction(self, sequence: int) -> WorkItemRecord:
        row = self._connection.execute(
            "SELECT record_json FROM work_items WHERE sequence = ?", (sequence,)
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown work item sequence: {sequence}")
        return WorkItemRecord.model_validate_json(row[0])

    def _write_work_item(self, record: WorkItemRecord) -> None:
        self._connection.execute(
            "UPDATE work_items SET record_json = ? WHERE sequence = ?",
            (record.model_dump_json(), record.sequence),
        )

    def _ready_work_item_in_transaction(self, current: WorkItemRecord) -> WorkItemRecord:
        status: Literal["pending", "compiled"] = (
            "compiled" if self._task_case_exists_in_transaction(current.sequence) else "pending"
        )
        return current.model_copy(update={"status": status, "owner_id": None})

    def _task_case_exists_in_transaction(self, sequence: int) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM task_cases WHERE sequence = ?", (sequence,)
            ).fetchone()
            is not None
        )

    def _terminal_outcome_exists_in_transaction(self, sequence: int) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM terminal_outcomes WHERE sequence = ?", (sequence,)
            ).fetchone()
            is not None
        )


def _open_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection
