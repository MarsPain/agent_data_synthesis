from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from awm_runtime.runtime import RuntimeMetadata, runtime_metadata_from_environment
from synthesis.contracts import validate_mobile_messages_environment_input_record
from synthesis.environments import EnvironmentMetadata


@dataclass(frozen=True)
class MessageThreadRecord:
    thread_id: str
    participant: str

    def export(self) -> dict[str, object]:
        return {"thread_id": self.thread_id, "participant": self.participant}


@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    thread_id: str
    sender: str
    body: str
    received_at: str

    def export(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "body": self.body,
            "received_at": self.received_at,
        }


@dataclass(frozen=True)
class ReminderRecord:
    reminder_id: str
    title: str
    due_at: str | None
    source_message_id: str | None
    created_at: str = "1970-01-01T00:00:00Z"

    def export(self) -> dict[str, object]:
        return {
            "reminder_id": self.reminder_id,
            "title": self.title,
            "due_at": self.due_at,
            "source_message_id": self.source_message_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DraftReplyRecord:
    draft_id: str
    thread_id: str
    body: str
    created_at: str = "1970-01-01T00:00:00Z"

    def export(self) -> dict[str, object]:
        return {
            "draft_id": self.draft_id,
            "thread_id": self.thread_id,
            "body": self.body,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class MobileMessagesEnvironmentInput:
    threads: tuple[MessageThreadRecord, ...]
    messages: tuple[MessageRecord, ...]
    reminders: tuple[ReminderRecord, ...] = ()
    draft_replies: tuple[DraftReplyRecord, ...] = ()
    source_bundle_id: str | None = None
    source_policy_hash: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "mobile_messages_environment_input_v1",
            "threads": [thread.export() for thread in self.threads],
            "messages": [message.export() for message in self.messages],
            "reminders": [reminder.export() for reminder in self.reminders],
            "draft_replies": [draft.export() for draft in self.draft_replies],
            "source_bundle_id": self.source_bundle_id,
            "source_policy_hash": self.source_policy_hash,
        }


class MobileMessagesEnvironment:
    environment_id = "mobile_messages_fixture"
    version = "env_mobile_messages_v1"

    @classmethod
    def create_fixture(
        cls,
        output_dir: Path,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "MobileMessagesEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "mobile_messages.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(database_path, source_provenance=source_provenance)
        with closing(environment.connect()) as connection:
            with connection:
                _create_schema(connection)
                _insert_mobile_input(connection, _fixture_input())
        return environment

    @classmethod
    def create_from_input(
        cls,
        output_dir: Path,
        environment_input: MobileMessagesEnvironmentInput,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "MobileMessagesEnvironment":
        validate_mobile_messages_environment_input_record(environment_input.export())
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "mobile_messages.sqlite3"
        if database_path.exists():
            database_path.unlink()
        environment = cls(
            database_path,
            source_provenance=source_provenance,
            source_input=environment_input,
        )
        with closing(environment.connect()) as connection:
            with connection:
                _create_schema(connection)
                _insert_mobile_input(connection, environment_input)
        return environment

    def __init__(
        self,
        database_path: Path,
        *,
        source_provenance: dict[str, object] | None = None,
        source_input: MobileMessagesEnvironmentInput | None = None,
    ) -> None:
        self.database_path = database_path
        self.source_provenance = source_provenance
        self.source_input = source_input

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @classmethod
    def fixture_message_binding_values(
        cls,
        field: str,
    ) -> tuple[str, ...]:
        if field not in {"message_id", "thread_id"}:
            raise ValueError("unsupported mobile fixture binding field")
        return tuple(
            str(getattr(message, field))
            for message in _fixture_input().messages
        )

    def checkpoint(self) -> bytes:
        return self.database_path.read_bytes()

    def restore_checkpoint(self, checkpoint: bytes) -> None:
        self.database_path.write_bytes(checkpoint)

    def rebuild(self, output_dir: Path) -> "MobileMessagesEnvironment":
        if self.source_input is not None:
            return type(self).create_from_input(
                output_dir,
                self.source_input,
                source_provenance=self.source_provenance,
            )
        return type(self).create_fixture(
            output_dir,
            source_provenance=self.source_provenance,
        )

    def search_messages(
        self,
        *,
        query: str,
        participant: str | None = None,
    ) -> dict[str, object]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query must be a non-empty string")
        clauses = ["LOWER(messages.body) LIKE ?"]
        parameters: list[object] = [f"%{query_text.lower()}%"]
        if participant is not None:
            participant_text = participant.strip()
            if not participant_text:
                raise ValueError("participant must be a non-empty string when provided")
            clauses.append("LOWER(message_threads.participant) = ?")
            parameters.append(participant_text.lower())

        with closing(self.connect()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    messages.message_id,
                    messages.thread_id,
                    message_threads.participant,
                    messages.body
                FROM messages
                JOIN message_threads ON message_threads.thread_id = messages.thread_id
                WHERE {' AND '.join(clauses)}
                ORDER BY messages.received_at, messages.message_id
                LIMIT 1
                """,
                tuple(parameters),
            ).fetchone()
        if row is None:
            raise KeyError(f"No phone message matched query: {query}")
        body = str(row[3])
        return {
            "message_id": str(row[0]),
            "thread_id": str(row[1]),
            "participant": str(row[2]),
            "snippet": body[:120],
        }

    def create_reminder(
        self,
        *,
        title: str,
        due_at: str | None = None,
        source_message_id: str | None = None,
    ) -> dict[str, object]:
        title_text = title.strip()
        if not title_text:
            raise ValueError("title must be a non-empty string")
        source_text = source_message_id.strip() if source_message_id else None
        reminder_id = f"reminder_{source_text}" if source_text else f"reminder_{_stable_id(title_text)}"
        record = ReminderRecord(
            reminder_id=reminder_id,
            title=title_text,
            due_at=due_at.strip() if isinstance(due_at, str) and due_at.strip() else None,
            source_message_id=source_text,
        )
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO reminders(reminder_id, title, due_at, source_message_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(reminder_id) DO UPDATE SET
                        title = excluded.title,
                        due_at = excluded.due_at,
                        source_message_id = excluded.source_message_id
                    """,
                    (
                        record.reminder_id,
                        record.title,
                        record.due_at,
                        record.source_message_id,
                        record.created_at,
                    ),
                )
        exported = record.export()
        exported["state_change"] = {
            "entity": "mobile_reminder",
            "operation": "upsert",
            "reminder_id": record.reminder_id,
        }
        return exported

    def draft_reply(self, *, thread_id: str, body: str) -> dict[str, object]:
        thread_text = thread_id.strip()
        body_text = body.strip()
        if not thread_text:
            raise ValueError("thread_id must be a non-empty string")
        if not body_text:
            raise ValueError("body must be a non-empty string")
        record = DraftReplyRecord(
            draft_id=f"draft_{thread_text}",
            thread_id=thread_text,
            body=body_text,
        )
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO draft_replies(draft_id, thread_id, body, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(draft_id) DO UPDATE SET
                        thread_id = excluded.thread_id,
                        body = excluded.body
                    """,
                    (
                        record.draft_id,
                        record.thread_id,
                        record.body,
                        record.created_at,
                    ),
                )
        exported = record.export()
        exported["state_change"] = {
            "entity": "mobile_draft_reply",
            "operation": "upsert",
            "draft_id": record.draft_id,
        }
        return exported

    def has_reminder(
        self,
        *,
        title: str,
        due_at: str | None = None,
        source_message_id: str | None = None,
    ) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM reminders
                WHERE title = ? AND due_at IS ? AND source_message_id IS ?
                """,
                (title, due_at, source_message_id),
            ).fetchone()
        return row is not None

    def has_draft_reply(self, *, thread_id: str, body: str) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM draft_replies WHERE thread_id = ? AND body = ?",
                (thread_id, body),
            ).fetchone()
        return row is not None

    def metadata(self) -> EnvironmentMetadata:
        reset_recipe: dict[str, object] = {
            "type": "sqlite_fixture",
            "fixture": "mobile_messages",
            "database": self.database_path.name,
            "tables": [
                "message_threads",
                "messages",
                "reminders",
                "draft_replies",
            ],
        }
        if self.source_input is not None:
            reset_recipe = {
                "type": "sqlite_mobile_messages_source_input",
                "fixture": "mobile_messages",
                "database": self.database_path.name,
                "tables": [
                    "message_threads",
                    "messages",
                    "reminders",
                    "draft_replies",
                ],
                "source_bundle_id": self.source_input.source_bundle_id,
                "source_policy_hash": self.source_input.source_policy_hash,
                "thread_count": len(self.source_input.threads),
                "message_count": len(self.source_input.messages),
                "reminder_count": len(self.source_input.reminders),
                "draft_reply_count": len(self.source_input.draft_replies),
            }
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe=reset_recipe,
            source_provenance=self.source_provenance,
        )

    def runtime_metadata(self) -> RuntimeMetadata:
        return runtime_metadata_from_environment(self.metadata())


def _stable_id(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE message_threads (
            thread_id TEXT PRIMARY KEY,
            participant TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            received_at TEXT NOT NULL,
            FOREIGN KEY(thread_id) REFERENCES message_threads(thread_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE reminders (
            reminder_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            due_at TEXT,
            source_message_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(source_message_id) REFERENCES messages(message_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE draft_replies (
            draft_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(thread_id) REFERENCES message_threads(thread_id)
        )
        """
    )


def _insert_mobile_input(
    connection: sqlite3.Connection,
    environment_input: MobileMessagesEnvironmentInput,
) -> None:
    connection.executemany(
        "INSERT INTO message_threads(thread_id, participant) VALUES (?, ?)",
        [
            (thread.thread_id, thread.participant)
            for thread in environment_input.threads
        ],
    )
    connection.executemany(
        """
        INSERT INTO messages(message_id, thread_id, sender, body, received_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                message.message_id,
                message.thread_id,
                message.sender,
                message.body,
                message.received_at,
            )
            for message in environment_input.messages
        ],
    )
    connection.executemany(
        """
        INSERT INTO reminders(reminder_id, title, due_at, source_message_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                reminder.reminder_id,
                reminder.title,
                reminder.due_at,
                reminder.source_message_id,
                reminder.created_at,
            )
            for reminder in environment_input.reminders
        ],
    )
    connection.executemany(
        """
        INSERT INTO draft_replies(draft_id, thread_id, body, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            (draft.draft_id, draft.thread_id, draft.body, draft.created_at)
            for draft in environment_input.draft_replies
        ],
    )


def _fixture_input() -> MobileMessagesEnvironmentInput:
    return MobileMessagesEnvironmentInput(
        threads=(
            MessageThreadRecord("thread_maya", "Maya"),
            MessageThreadRecord("thread_alex", "Alex"),
            MessageThreadRecord("thread_delivery", "Delivery"),
            MessageThreadRecord("thread_priya", "Priya"),
            MessageThreadRecord("thread_morgan", "Morgan"),
            MessageThreadRecord("thread_jordan", "Jordan"),
        ),
        messages=(
            MessageRecord(
                message_id="msg_maya_project_update",
                thread_id="thread_maya",
                sender="Maya",
                body="Can you remind me to send the project update tomorrow at 9 AM?",
                received_at="2026-06-12T08:00:00Z",
            ),
            MessageRecord(
                message_id="msg_alex_late_reply",
                thread_id="thread_alex",
                sender="Alex",
                body="Please reply that I will be five minutes late.",
                received_at="2026-06-12T08:05:00Z",
            ),
            MessageRecord(
                message_id="msg_delivery_pickup_code",
                thread_id="thread_delivery",
                sender="Delivery",
                body="Your pickup code is 4821. Ask the desk if the sender is missing.",
                received_at="2026-06-12T08:10:00Z",
            ),
            MessageRecord(
                message_id="msg_priya_design_review",
                thread_id="thread_priya",
                sender="Priya",
                body="The design review moved to Friday at 2 PM.",
                received_at="2026-06-12T08:15:00Z",
            ),
            MessageRecord(
                message_id="msg_morgan_finance_review",
                thread_id="thread_morgan",
                sender="Morgan",
                body="The project update invoice is ready for finance review.",
                received_at="2026-06-12T08:20:00Z",
            ),
            MessageRecord(
                message_id="msg_jordan_quarterly_planning",
                thread_id="thread_jordan",
                sender="Jordan",
                body="The quarterly planning notes are ready for review.",
                received_at="2026-06-12T08:25:00Z",
            ),
        ),
    )
