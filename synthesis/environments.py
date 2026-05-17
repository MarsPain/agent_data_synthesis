from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvironmentMetadata:
    environment_id: str
    version: str
    reset_recipe: dict[str, object]
    source_provenance: dict[str, object] | None = None


class ContactEnvironment:
    environment_id = "contacts_fixture"
    version = "env_contacts_v2"

    @classmethod
    def create_fixture(
        cls,
        output_dir: Path,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "ContactEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "contacts.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(database_path, source_provenance=source_provenance)
        with closing(environment.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE contacts (
                        name TEXT PRIMARY KEY,
                        email TEXT NOT NULL
                    )
                    """
                )
                connection.executemany(
                    "INSERT INTO contacts(name, email) VALUES (?, ?)",
                    [
                        ("Alice Zhang", "alice.zhang@example.test"),
                        ("Ben Carter", "ben.carter@example.test"),
                    ],
                )
                connection.execute(
                    """
                    CREATE TABLE contact_followups (
                        name TEXT PRIMARY KEY,
                        note TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
                        FOREIGN KEY(name) REFERENCES contacts(name)
                    )
                    """
                )
        return environment

    def __init__(
        self,
        database_path: Path,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> None:
        self.database_path = database_path
        self.source_provenance = source_provenance

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def checkpoint(self) -> bytes:
        return self.database_path.read_bytes()

    def restore_checkpoint(self, checkpoint: bytes) -> None:
        self.database_path.write_bytes(checkpoint)

    def lookup_email(self, name: str) -> dict[str, str]:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT email FROM contacts WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown contact: {name}")
        return {"name": name, "email": row[0]}

    def list_contact_names(self) -> dict[str, str]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT name FROM contacts ORDER BY name"
            ).fetchall()
        return {"contacts": ", ".join(str(row[0]) for row in rows)}

    def record_followup(self, name: str, note: str) -> dict[str, object]:
        self.lookup_email(name)
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO contact_followups(name, note)
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET note = excluded.note
                    """,
                    (name, note),
                )
                row = connection.execute(
                    "SELECT COUNT(*) FROM contact_followups WHERE name = ? AND note = ?",
                    (name, note),
                ).fetchone()
        return {
            "name": name,
            "note": note,
            "followup_count": int(row[0]) if row else 0,
            "state_change": {
                "entity": "contact_followup",
                "operation": "upsert",
                "name": name,
            },
        }

    def has_followup(self, name: str, note: str) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM contact_followups WHERE name = ? AND note = ?",
                (name, note),
            ).fetchone()
        return row is not None

    def metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe={
                "type": "sqlite_fixture",
                "fixture": "contacts",
                "database": self.database_path.name,
                "tables": ["contacts", "contact_followups"],
            },
            source_provenance=self.source_provenance,
        )
