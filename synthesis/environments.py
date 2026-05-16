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


class ContactEnvironment:
    environment_id = "contacts_fixture"
    version = "env_contacts_v1"

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @classmethod
    def create_fixture(cls, output_dir: Path) -> "ContactEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "contacts.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(database_path)
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
        return environment

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def lookup_email(self, name: str) -> dict[str, str]:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT email FROM contacts WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown contact: {name}")
        return {"name": name, "email": row[0]}

    def metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe={
                "type": "sqlite_fixture",
                "fixture": "contacts",
                "database": self.database_path.name,
            },
        )
