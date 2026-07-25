from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from awm_runtime.runtime import RuntimeMetadata, runtime_metadata_from_environment
from synthesis.contracts import validate_workspace_tasks_environment_input_record
from synthesis.environments import EnvironmentMetadata
from synthesis.stable_ids import stable_id as _stable_id


@dataclass(frozen=True)
class WorkspaceProjectRecord:
    project_id: str
    name: str
    status: str

    def export(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status,
        }


@dataclass(frozen=True)
class WorkspaceTaskRecord:
    task_id: str
    project_id: str
    title: str
    priority: str
    due_label: str
    status: str = "open"
    created_at: str = "1970-01-01T00:00:00Z"

    def export(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "title": self.title,
            "priority": self.priority,
            "due_label": self.due_label,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkspaceDocumentRecord:
    document_id: str
    project_id: str
    title: str
    body: str

    def export(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "project_id": self.project_id,
            "title": self.title,
            "body": self.body,
        }


@dataclass(frozen=True)
class WorkspaceCommentRecord:
    comment_id: str
    task_id: str
    body: str
    created_at: str = "1970-01-01T00:00:00Z"

    def export(self) -> dict[str, object]:
        return {
            "comment_id": self.comment_id,
            "task_id": self.task_id,
            "body": self.body,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkspaceEnvironmentInput:
    projects: tuple[WorkspaceProjectRecord, ...]
    tasks: tuple[WorkspaceTaskRecord, ...]
    documents: tuple[WorkspaceDocumentRecord, ...]
    comments: tuple[WorkspaceCommentRecord, ...]
    source_bundle_id: str | None = None
    source_policy_hash: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "workspace_tasks_environment_input_v1",
            "projects": [project.export() for project in self.projects],
            "tasks": [task.export() for task in self.tasks],
            "documents": [document.export() for document in self.documents],
            "comments": [comment.export() for comment in self.comments],
            "source_bundle_id": self.source_bundle_id,
            "source_policy_hash": self.source_policy_hash,
        }


class WorkspaceTasksEnvironment:
    environment_id = "workspace_tasks_fixture"
    version = "env_workspace_tasks_v1"

    @classmethod
    def create_fixture(
        cls,
        output_dir: Path,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "WorkspaceTasksEnvironment":
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "workspace_tasks.sqlite3"
        if database_path.exists():
            database_path.unlink()

        environment = cls(database_path, source_provenance=source_provenance)
        with closing(environment.connect()) as connection:
            with connection:
                _create_schema(connection)
                _insert_workspace_input(connection, _fixture_input())
        return environment

    @classmethod
    def create_from_input(
        cls,
        output_dir: Path,
        environment_input: WorkspaceEnvironmentInput,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "WorkspaceTasksEnvironment":
        validate_workspace_tasks_environment_input_record(environment_input.export())
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "workspace_tasks.sqlite3"
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
                _insert_workspace_input(connection, environment_input)
        return environment

    def __init__(
        self,
        database_path: Path,
        *,
        source_provenance: dict[str, object] | None = None,
        source_input: WorkspaceEnvironmentInput | None = None,
    ) -> None:
        self.database_path = database_path
        self.source_provenance = source_provenance
        self.source_input = source_input

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def checkpoint(self) -> bytes:
        return self.database_path.read_bytes()

    def restore_checkpoint(self, checkpoint: bytes) -> None:
        self.database_path.write_bytes(checkpoint)

    def rebuild(self, output_dir: Path) -> "WorkspaceTasksEnvironment":
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

    def search_workspace_items(
        self,
        *,
        query: str,
        kind: str | None = None,
    ) -> dict[str, object]:
        query_text = _required_text(query, "query")
        kind_text = kind.strip().lower() if isinstance(kind, str) and kind.strip() else None
        if kind_text is not None and kind_text not in {"project", "task", "document", "comment"}:
            raise ValueError("kind must be project, task, document, or comment when provided")

        matches = self._search_matches(query_text)
        if kind_text is not None:
            matches = [match for match in matches if match["kind"] == kind_text]
        if not matches:
            raise KeyError(f"No workspace item matched query: {query}")
        return matches[0]

    def create_workspace_task(
        self,
        *,
        project_id: str,
        title: str,
        priority: str,
        due_label: str,
    ) -> dict[str, object]:
        project_text = _required_text(project_id, "project_id")
        title_text = _required_text(title, "title")
        priority_text = _required_text(priority, "priority")
        due_text = _required_text(due_label, "due_label")
        self._require_project(project_text)

        record = WorkspaceTaskRecord(
            task_id=f"task_{_stable_id(title_text)}",
            project_id=project_text,
            title=title_text,
            priority=priority_text,
            due_label=due_text,
        )
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO workspace_tasks(
                        task_id,
                        project_id,
                        title,
                        priority,
                        due_label,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        project_id = excluded.project_id,
                        title = excluded.title,
                        priority = excluded.priority,
                        due_label = excluded.due_label,
                        status = excluded.status
                    """,
                    (
                        record.task_id,
                        record.project_id,
                        record.title,
                        record.priority,
                        record.due_label,
                        record.status,
                        record.created_at,
                    ),
                )
        exported = record.export()
        exported["state_change"] = {
            "entity": "workspace_task",
            "operation": "upsert",
            "task_id": record.task_id,
            "project_id": record.project_id,
        }
        return exported

    def project_search_bindings(
        self,
    ) -> tuple[tuple[dict[str, object], str], ...]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT project_id, name
                FROM workspace_projects
                ORDER BY project_id
                """
            ).fetchall()
        return tuple(
            (
                {"query": str(name), "kind": "project"},
                str(project_id),
            )
            for project_id, name in rows
        )

    def add_workspace_comment(self, *, task_id: str, comment: str) -> dict[str, object]:
        task_text = _required_text(task_id, "task_id")
        comment_text = _required_text(comment, "comment")
        self._require_task(task_text)

        record = WorkspaceCommentRecord(
            comment_id=f"comment_{task_text}_{_stable_id(comment_text)}",
            task_id=task_text,
            body=comment_text,
        )
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO workspace_comments(comment_id, task_id, body, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(comment_id) DO UPDATE SET
                        task_id = excluded.task_id,
                        body = excluded.body
                    """,
                    (
                        record.comment_id,
                        record.task_id,
                        record.body,
                        record.created_at,
                    ),
                )
        exported = record.export()
        exported["comment"] = exported.pop("body")
        exported["state_change"] = {
            "entity": "workspace_comment",
            "operation": "upsert",
            "comment_id": record.comment_id,
            "task_id": record.task_id,
        }
        return exported

    def has_workspace_task(
        self,
        *,
        project_id: str,
        title: str,
        priority: str,
        due_label: str,
    ) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM workspace_tasks
                WHERE project_id = ? AND title = ? AND priority = ? AND due_label = ?
                """,
                (project_id, title, priority, due_label),
            ).fetchone()
        return row is not None

    def has_workspace_comment(self, *, task_id: str, comment: str) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM workspace_comments WHERE task_id = ? AND body = ?",
                (task_id, comment),
            ).fetchone()
        return row is not None

    def metadata(self) -> EnvironmentMetadata:
        reset_recipe: dict[str, object] = {
            "type": "sqlite_fixture",
            "fixture": "workspace_tasks",
            "database": self.database_path.name,
            "tables": [
                "workspace_projects",
                "workspace_tasks",
                "workspace_documents",
                "workspace_comments",
            ],
        }
        if self.source_input is not None:
            reset_recipe.update(
                {
                    "source_bundle_id": self.source_input.source_bundle_id,
                    "source_policy_hash": self.source_input.source_policy_hash,
                }
            )
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe=reset_recipe,
            source_provenance=self.source_provenance,
        )

    def runtime_metadata(self) -> RuntimeMetadata:
        return runtime_metadata_from_environment(self.metadata())

    def _search_matches(self, query: str) -> list[dict[str, object]]:
        like_query = f"%{query.lower()}%"
        with closing(self.connect()) as connection:
            rows: list[dict[str, object]] = []
            rows.extend(_project_matches(connection, like_query))
            rows.extend(_task_matches(connection, like_query))
            rows.extend(_document_matches(connection, like_query))
            rows.extend(_comment_matches(connection, like_query))
        return sorted(rows, key=lambda row: (str(row["kind"]), str(row["item_id"])))

    def _require_project(self, project_id: str) -> None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM workspace_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown workspace project: {project_id}")

    def _require_task(self, task_id: str) -> None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM workspace_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown workspace task: {task_id}")


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE workspace_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE workspace_tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            priority TEXT NOT NULL,
            due_label TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES workspace_projects(project_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE workspace_documents (
            document_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES workspace_projects(project_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE workspace_comments (
            comment_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES workspace_tasks(task_id)
        )
        """
    )


def _insert_workspace_input(
    connection: sqlite3.Connection,
    environment_input: WorkspaceEnvironmentInput,
) -> None:
    connection.executemany(
        "INSERT INTO workspace_projects(project_id, name, status) VALUES (?, ?, ?)",
        [
            (project.project_id, project.name, project.status)
            for project in environment_input.projects
        ],
    )
    connection.executemany(
        """
        INSERT INTO workspace_tasks(
            task_id,
            project_id,
            title,
            priority,
            due_label,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                task.task_id,
                task.project_id,
                task.title,
                task.priority,
                task.due_label,
                task.status,
                task.created_at,
            )
            for task in environment_input.tasks
        ],
    )
    connection.executemany(
        """
        INSERT INTO workspace_documents(document_id, project_id, title, body)
        VALUES (?, ?, ?, ?)
        """,
        [
            (document.document_id, document.project_id, document.title, document.body)
            for document in environment_input.documents
        ],
    )
    connection.executemany(
        """
        INSERT INTO workspace_comments(comment_id, task_id, body, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            (comment.comment_id, comment.task_id, comment.body, comment.created_at)
            for comment in environment_input.comments
        ],
    )


def _fixture_input() -> WorkspaceEnvironmentInput:
    return WorkspaceEnvironmentInput(
        projects=(
            WorkspaceProjectRecord("project_alpha", "Alpha Launch", "active"),
            WorkspaceProjectRecord("project_beta", "Beta Research", "active"),
        ),
        tasks=(
            WorkspaceTaskRecord(
                "task_launch_plan",
                "project_alpha",
                "Finalize launch plan",
                "high",
                "this_week",
            ),
            WorkspaceTaskRecord(
                "task_metrics_review",
                "project_alpha",
                "Review launch metrics dashboard",
                "medium",
                "next_week",
            ),
            WorkspaceTaskRecord(
                "task_research_notes",
                "project_beta",
                "Summarize customer research notes",
                "medium",
                "later",
            ),
        ),
        documents=(
            WorkspaceDocumentRecord(
                "doc_launch_brief",
                "project_alpha",
                "Launch Brief",
                "Launch owners, target dates, and rollout criteria.",
            ),
            WorkspaceDocumentRecord(
                "doc_research_summary",
                "project_beta",
                "Research Summary",
                "Customer feedback themes and open questions.",
            ),
        ),
        comments=(
            WorkspaceCommentRecord(
                "comment_task_launch_plan_owner",
                "task_launch_plan",
                "Assign launch checklist owner before review.",
            ),
            WorkspaceCommentRecord(
                "comment_task_research_notes_source",
                "task_research_notes",
                "Link research notes to the summary document.",
            ),
        ),
    )


def _project_matches(
    connection: sqlite3.Connection,
    like_query: str,
) -> list[dict[str, object]]:
    return [
        {
            "kind": "project",
            "item_id": str(row[0]),
            "project_id": str(row[0]),
            "summary": f"{row[1]} ({row[2]})",
        }
        for row in connection.execute(
            """
            SELECT project_id, name, status
            FROM workspace_projects
            WHERE LOWER(name) LIKE ? OR LOWER(status) LIKE ?
            ORDER BY project_id
            """,
            (like_query, like_query),
        ).fetchall()
    ]


def _task_matches(
    connection: sqlite3.Connection,
    like_query: str,
) -> list[dict[str, object]]:
    return [
        {
            "kind": "task",
            "item_id": str(row[0]),
            "project_id": str(row[1]),
            "summary": f"{row[2]} [{row[3]}, {row[4]}]",
        }
        for row in connection.execute(
            """
            SELECT task_id, project_id, title, priority, due_label
            FROM workspace_tasks
            WHERE LOWER(title) LIKE ?
            ORDER BY created_at, task_id
            """,
            (like_query,),
        ).fetchall()
    ]


def _document_matches(
    connection: sqlite3.Connection,
    like_query: str,
) -> list[dict[str, object]]:
    return [
        {
            "kind": "document",
            "item_id": str(row[0]),
            "project_id": str(row[1]),
            "summary": f"{row[2]}: {str(row[3])[:120]}",
        }
        for row in connection.execute(
            """
            SELECT document_id, project_id, title, body
            FROM workspace_documents
            WHERE LOWER(title) LIKE ? OR LOWER(body) LIKE ?
            ORDER BY document_id
            """,
            (like_query, like_query),
        ).fetchall()
    ]


def _comment_matches(
    connection: sqlite3.Connection,
    like_query: str,
) -> list[dict[str, object]]:
    return [
        {
            "kind": "comment",
            "item_id": str(row[0]),
            "task_id": str(row[1]),
            "summary": str(row[2])[:120],
        }
        for row in connection.execute(
            """
            SELECT comment_id, task_id, body
            FROM workspace_comments
            WHERE LOWER(body) LIKE ?
            ORDER BY created_at, comment_id
            """,
            (like_query,),
        ).fetchall()
    ]


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
