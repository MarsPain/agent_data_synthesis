from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from synthesis.environments import EnvironmentMetadata
from synthesis.runtime import RuntimeMetadata, runtime_metadata_from_environment


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


class MobileMessagesEnvironment:
    environment_id = "mobile_messages_fixture"
    version = "env_mobile_messages_v1"

    @classmethod
    def create_fixture(cls, output_dir: Path) -> "MobileMessagesEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "mobile_messages.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(database_path)
        with closing(environment.connect()) as connection:
            with connection:
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
                connection.executemany(
                    "INSERT INTO message_threads(thread_id, participant) VALUES (?, ?)",
                    [
                        ("thread_maya", "Maya"),
                        ("thread_alex", "Alex"),
                        ("thread_delivery", "Delivery"),
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO messages(message_id, thread_id, sender, body, received_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "msg_maya_project_update",
                            "thread_maya",
                            "Maya",
                            "Can you remind me to send the project update tomorrow at 9 AM?",
                            "2026-06-12T08:00:00Z",
                        ),
                        (
                            "msg_alex_late_reply",
                            "thread_alex",
                            "Alex",
                            "Please reply that I will be five minutes late.",
                            "2026-06-12T08:05:00Z",
                        ),
                        (
                            "msg_delivery_pickup_code",
                            "thread_delivery",
                            "Delivery",
                            "Your pickup code is 4821. Ask the desk if the sender is missing.",
                            "2026-06-12T08:10:00Z",
                        ),
                    ],
                )
        return environment

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def checkpoint(self) -> bytes:
        return self.database_path.read_bytes()

    def restore_checkpoint(self, checkpoint: bytes) -> None:
        self.database_path.write_bytes(checkpoint)

    def rebuild(self, output_dir: Path) -> "MobileMessagesEnvironment":
        return type(self).create_fixture(output_dir)

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
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe={
                "type": "sqlite_fixture",
                "fixture": "mobile_messages",
                "database": self.database_path.name,
                "tables": [
                    "message_threads",
                    "messages",
                    "reminders",
                    "draft_replies",
                ],
            },
        )

    def runtime_metadata(self) -> RuntimeMetadata:
        return runtime_metadata_from_environment(self.metadata())


def _stable_id(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")
