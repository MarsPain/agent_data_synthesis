from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from awm_runtime.runtime import RuntimeMetadata, runtime_metadata_from_environment
from synthesis.contracts import validate_contacts_environment_input_record


CONTACT_FIXTURE_ROWS = (
    ("Alice Zhang", "alice.zhang@example.test"),
    ("Ben Carter", "ben.carter@example.test"),
    ("Carla Diaz", "carla.diaz@example.test"),
    ("David Kim", "david.kim@example.test"),
    ("Elena Petrova", "elena.petrova@example.test"),
    ("Frank Osei", "frank.osei@example.test"),
)
CONTACT_REPRESENTATIVE_FIXTURE_ROWS = CONTACT_FIXTURE_ROWS + (
    ("Grace Liu", "grace.liu@example.test"),
    ("Hassan Rahman", "hassan.rahman@example.test"),
    ("Ingrid Novak", "ingrid.novak@example.test"),
    ("Jamal Thompson", "jamal.thompson@example.test"),
    ("Keiko Sato", "keiko.sato@example.test"),
    ("Luis Moreno", "luis.moreno@example.test"),
    ("Nadia Ahmed", "nadia.ahmed@example.test"),
    ("Owen Brooks", "owen.brooks@example.test"),
    ("Priyanka Shah", "priyanka.shah@example.test"),
)


@dataclass(frozen=True)
class EnvironmentMetadata:
    environment_id: str
    version: str
    reset_recipe: dict[str, object]
    source_provenance: dict[str, object] | None = None


@dataclass(frozen=True)
class ContactRecord:
    name: str
    email: str

    def export(self) -> dict[str, object]:
        return {"name": self.name, "email": self.email}


@dataclass(frozen=True)
class ContactFollowupRecord:
    name: str
    note: str
    created_at: str = "1970-01-01T00:00:00Z"

    def export(self) -> dict[str, object]:
        return {
            "name": self.name,
            "note": self.note,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ContactsEnvironmentInput:
    contacts: tuple[ContactRecord, ...]
    followups: tuple[ContactFollowupRecord, ...]
    source_bundle_id: str
    source_policy_hash: str
    validation_errors: tuple[str, ...] = ()

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "contacts_environment_input_v1",
            "contacts": [contact.export() for contact in self.contacts],
            "followups": [followup.export() for followup in self.followups],
            "source_bundle_id": self.source_bundle_id,
            "source_policy_hash": self.source_policy_hash,
            "validation_errors": list(self.validation_errors),
        }


class ContactEnvironment:
    environment_id = "contacts_fixture"
    version = "env_contacts_v2"

    @classmethod
    def create_fixture(
        cls,
        output_dir: Path,
        *,
        source_provenance: dict[str, object] | None = None,
        representative: bool = False,
    ) -> "ContactEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "contacts.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(
            database_path,
            source_provenance=source_provenance,
            representative_fixture=representative,
        )
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
                    (
                        CONTACT_REPRESENTATIVE_FIXTURE_ROWS
                        if representative
                        else CONTACT_FIXTURE_ROWS
                    ),
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

    @classmethod
    def create_from_input(
        cls,
        output_dir: Path,
        environment_input: ContactsEnvironmentInput,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "ContactEnvironment":
        validate_contacts_environment_input_record(environment_input.export())
        if environment_input.validation_errors:
            raise ValueError("; ".join(environment_input.validation_errors))
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "contacts.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(
            database_path,
            source_provenance=source_provenance,
            source_input=environment_input,
        )
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
                        (contact.name, contact.email)
                        for contact in environment_input.contacts
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
                connection.executemany(
                    """
                    INSERT INTO contact_followups(name, note, created_at)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (followup.name, followup.note, followup.created_at)
                        for followup in environment_input.followups
                    ],
                )
        return environment

    def __init__(
        self,
        database_path: Path,
        *,
        source_provenance: dict[str, object] | None = None,
        source_input: ContactsEnvironmentInput | None = None,
        representative_fixture: bool = False,
    ) -> None:
        self.database_path = database_path
        self.source_provenance = source_provenance
        self.source_input = source_input
        self.representative_fixture = representative_fixture
        if representative_fixture:
            self.version = "env_contacts_representative_v3"

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def checkpoint(self) -> bytes:
        return self.database_path.read_bytes()

    def restore_checkpoint(self, checkpoint: bytes) -> None:
        self.database_path.write_bytes(checkpoint)

    def rebuild(self, output_dir: Path) -> "ContactEnvironment":
        if self.source_input is not None:
            return type(self).create_from_input(
                output_dir,
                self.source_input,
                source_provenance=self.source_provenance,
            )
        return type(self).create_fixture(
            output_dir,
            source_provenance=self.source_provenance,
            representative=self.representative_fixture,
        )

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
        return {"contacts": ", ".join(self.contact_names())}

    def contact_names(self) -> tuple[str, ...]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT name FROM contacts ORDER BY name"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    @classmethod
    def fixture_contact_names(cls) -> tuple[str, ...]:
        return tuple(name for name, _email in CONTACT_FIXTURE_ROWS)

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
        reset_recipe: dict[str, object] = {
            "type": "sqlite_fixture",
            "fixture": "contacts",
            "database": self.database_path.name,
            "tables": ["contacts", "contact_followups"],
        }
        if self.source_input is not None:
            reset_recipe = {
                "type": "sqlite_contacts_source_input",
                "fixture": "contacts",
                "database": self.database_path.name,
                "tables": ["contacts", "contact_followups"],
                "source_bundle_id": self.source_input.source_bundle_id,
                "source_policy_hash": self.source_input.source_policy_hash,
                "contact_count": len(self.source_input.contacts),
                "followup_count": len(self.source_input.followups),
            }
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe=reset_recipe,
            source_provenance=self.source_provenance,
        )

    def runtime_metadata(self) -> RuntimeMetadata:
        return runtime_metadata_from_environment(self.metadata())
