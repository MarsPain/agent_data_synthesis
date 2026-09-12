"""Private SQLite persistence for frozen cases and durable request accounting."""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.domain import CompiledTask, FrozenInitialState, TaskSlot
from agent_synthesis.episode import PublicTask
from agent_synthesis.model import ModelRole, TokenUsage


class FrozenStateRecord(BaseModel):
    """Validated private representation of a Domain's frozen initial state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contents_b64: str = Field(min_length=1)

    @classmethod
    def from_initial_state(cls, state: FrozenInitialState) -> FrozenStateRecord:
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
    """Private binding of the immutable run configuration and Domain version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configuration: dict[str, JsonValue]
    domain_version: str = Field(min_length=1, max_length=128)

    @classmethod
    def from_configuration(
        cls,
        configuration: RunConfiguration,
        *,
        domain_version: str,
    ) -> RunMetadataRecord:
        return cls(
            configuration=configuration.normalized_public_record(),
            domain_version=domain_version,
        )

    def configuration_model(self) -> RunConfiguration:
        return RunConfiguration.model_validate(self.configuration)


class AllocatedSlotRecord(BaseModel):
    """A persisted slot identity that consumes one task-attempt allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=256)
    proposal_prompt: str = Field(min_length=1, max_length=8_000)

    @classmethod
    def from_slot(cls, *, sequence: int, slot: TaskSlot) -> AllocatedSlotRecord:
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
    ) -> TaskCaseRecord:
        return cls(
            sequence=sequence,
            slot_id=slot_id,
            public_task=task.public_task,
            semantic_key=task.semantic_key,
            case_b64=base64.b64encode(task.private_case_bytes).decode("ascii"),
        )

    def private_case_bytes(self) -> bytes:
        return base64.b64decode(self.case_b64, validate=True)


class ProviderRequestRecord(BaseModel):
    """One durable physical request reservation, including unknown outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: int = Field(ge=1)
    role: ModelRole
    logical_request_id: str = Field(min_length=1, max_length=256)
    attempt: int = Field(ge=1)
    sequence: int | None = Field(default=None, ge=1)
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
    def _require_terminal_details(self) -> ProviderRequestRecord:
        if self.status == "reserved":
            if self.response_hash is not None or self.usage is not None or self.error_code is not None:
                raise ValueError("reserved request cannot have terminal details")
        elif self.status == "completed" and self.error_code is not None:
            raise ValueError("completed request cannot have an error code")
        elif self.status == "failed" and self.error_code is None:
            raise ValueError("failed request requires an error code")
        return self


class PrivateLedger:
    """SQLite store with slot and physical-request reservations committed first."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection

    @classmethod
    def create(cls, path: Path) -> PrivateLedger:
        if path.exists():
            raise FileExistsError(f"private ledger already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE run_metadata (
                record_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE frozen_state (
                record_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE allocated_slots (
                sequence INTEGER PRIMARY KEY,
                record_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE task_cases (
                sequence INTEGER PRIMARY KEY,
                record_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE provider_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_json TEXT NOT NULL
            )
            """
        )
        connection.commit()
        return cls(path, connection)

    @classmethod
    def open(cls, path: Path) -> PrivateLedger:
        connection = sqlite3.connect(path)
        return cls(path, connection)

    def close(self) -> None:
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
        with self._connection:
            self._connection.execute("DELETE FROM run_metadata")
            self._connection.execute(
                "INSERT INTO run_metadata(record_json) VALUES (?)",
                (record.model_dump_json(),),
            )

    def run_metadata(self) -> RunMetadataRecord:
        row = self._connection.execute(
            "SELECT record_json FROM run_metadata"
        ).fetchone()
        if row is None:
            raise LookupError("private ledger has no run metadata")
        return RunMetadataRecord.model_validate_json(row[0])

    def record_initial_state(self, state: FrozenInitialState) -> None:
        record = FrozenStateRecord.from_initial_state(state)
        with self._connection:
            self._connection.execute("DELETE FROM frozen_state")
            self._connection.execute(
                "INSERT INTO frozen_state(record_json) VALUES (?)",
                (record.model_dump_json(),),
            )

    def initial_state(self) -> FrozenInitialState:
        row = self._connection.execute(
            "SELECT record_json FROM frozen_state"
        ).fetchone()
        if row is None:
            raise LookupError("private ledger has no frozen initial state")
        return FrozenStateRecord.model_validate_json(row[0]).to_initial_state()

    def record_allocated_slots(self, slots: tuple[AllocatedSlotRecord, ...]) -> None:
        if len({record.sequence for record in slots}) != len(slots):
            raise ValueError("allocated slot sequences must be unique")
        if len({record.slot_id for record in slots}) != len(slots):
            raise ValueError("allocated slot ids must be unique")
        with self._connection:
            self._connection.executemany(
                "INSERT INTO allocated_slots(sequence, record_json) VALUES (?, ?)",
                ((record.sequence, record.model_dump_json()) for record in slots),
            )

    def allocated_slots(self) -> tuple[AllocatedSlotRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM allocated_slots ORDER BY sequence"
        ).fetchall()
        return tuple(AllocatedSlotRecord.model_validate_json(row[0]) for row in rows)

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
        with self._connection:
            self._connection.execute(
                "INSERT INTO task_cases(sequence, record_json) VALUES (?, ?)",
                (record.sequence, record.model_dump_json()),
            )

    def task_cases(self) -> tuple[TaskCaseRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM task_cases ORDER BY sequence"
        ).fetchall()
        return tuple(TaskCaseRecord.model_validate_json(row[0]) for row in rows)

    def reserve_provider_request(
        self,
        *,
        role: ModelRole,
        logical_request_id: str,
        role_limit: int,
        total_limit: int,
        sequence: int | None,
        request_kind: Literal["initial", "repair"],
    ) -> ProviderRequestRecord | None:
        """Commit a charged physical request before any model dispatch."""

        with self._connection:
            total_count = self._connection.execute(
                "SELECT COUNT(*) FROM provider_requests"
            ).fetchone()[0]
            role_count = self._connection.execute(
                "SELECT COUNT(*) FROM provider_requests WHERE json_extract(record_json, '$.role') = ?",
                (role,),
            ).fetchone()[0]
            if total_count >= total_limit or role_count >= role_limit:
                return None
            attempt = self._connection.execute(
                "SELECT COUNT(*) FROM provider_requests WHERE json_extract(record_json, '$.logical_request_id') = ?",
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
                request_kind=request_kind,
                status="reserved",
            )
            self._connection.execute(
                "UPDATE provider_requests SET record_json = ? WHERE request_id = ?",
                (record.model_dump_json(), request_id),
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
        with self._connection:
            self._connection.execute(
                "UPDATE provider_requests SET record_json = ? WHERE request_id = ?",
                (record.model_dump_json(), request_id),
            )
        return record

    def provider_requests(self) -> tuple[ProviderRequestRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM provider_requests ORDER BY request_id"
        ).fetchall()
        return tuple(ProviderRequestRecord.model_validate_json(row[0]) for row in rows)
