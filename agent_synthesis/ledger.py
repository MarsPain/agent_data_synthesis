"""Private SQLite ledger persistence owned by the core's storage module."""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agent_synthesis.domain import CompiledTask, FrozenInitialState


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


class TaskCaseRecord(BaseModel):
    """Validated private record for one compiled Domain task case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=256)
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
            semantic_key=task.semantic_key,
            case_b64=base64.b64encode(task.private_case_bytes).decode("ascii"),
        )

    def private_case_bytes(self) -> bytes:
        return base64.b64decode(self.case_b64, validate=True)


class PrivateLedger:
    """Small SQLite store for admitted fixture bytes and compiled task cases."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection

    @classmethod
    def create(cls, path: Path) -> "PrivateLedger":
        if path.exists():
            raise FileExistsError(f"private ledger already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE frozen_state (
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
        connection.commit()
        return cls(path, connection)

    @classmethod
    def open(cls, path: Path) -> "PrivateLedger":
        connection = sqlite3.connect(path)
        return cls(path, connection)

    def close(self) -> None:
        self._connection.close()

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
