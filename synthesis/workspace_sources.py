from __future__ import annotations

import json

from synthesis.contracts import (
    ContractValidationError,
    validate_workspace_tasks_environment_input_record,
)
from synthesis.workspace_environment import (
    WorkspaceCommentRecord,
    WorkspaceDocumentRecord,
    WorkspaceEnvironmentInput,
    WorkspaceProjectRecord,
    WorkspaceTaskRecord,
)


class WorkspaceTasksSourceImporter:
    domain_id = "workspace_tasks_fixture"
    source_kind = "local_workspace_tasks_json"

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> WorkspaceEnvironmentInput:
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("environment source JSON is invalid") from exc
        if not isinstance(document, dict):
            raise ValueError("environment source payload must be an object")

        environment_input = WorkspaceEnvironmentInput(
            projects=_projects_from_payload(document.get("projects")),
            tasks=_tasks_from_payload(document.get("tasks")),
            documents=_documents_from_payload(document.get("documents")),
            comments=_comments_from_payload(document.get("comments")),
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
        )
        try:
            validate_workspace_tasks_environment_input_record(environment_input.export())
        except ContractValidationError as exc:
            raise ValueError("environment source payload is invalid") from exc
        return environment_input


def _projects_from_payload(value: object) -> tuple[WorkspaceProjectRecord, ...]:
    return tuple(
        WorkspaceProjectRecord(
            project_id=str(project.get("project_id", "")) if isinstance(project, dict) else "",
            name=str(project.get("name", "")) if isinstance(project, dict) else "",
            status=str(project.get("status", "")) if isinstance(project, dict) else "",
        )
        for project in _list_or_empty(value)
    )


def _tasks_from_payload(value: object) -> tuple[WorkspaceTaskRecord, ...]:
    return tuple(
        WorkspaceTaskRecord(
            task_id=str(task.get("task_id", "")) if isinstance(task, dict) else "",
            project_id=str(task.get("project_id", "")) if isinstance(task, dict) else "",
            title=str(task.get("title", "")) if isinstance(task, dict) else "",
            priority=str(task.get("priority", "")) if isinstance(task, dict) else "",
            due_label=str(task.get("due_label", "")) if isinstance(task, dict) else "",
            status=str(task.get("status", "open")) if isinstance(task, dict) else "open",
            created_at=(
                str(task.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(task, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for task in _list_or_empty(value)
    )


def _documents_from_payload(value: object) -> tuple[WorkspaceDocumentRecord, ...]:
    return tuple(
        WorkspaceDocumentRecord(
            document_id=(
                str(document.get("document_id", ""))
                if isinstance(document, dict)
                else ""
            ),
            project_id=(
                str(document.get("project_id", ""))
                if isinstance(document, dict)
                else ""
            ),
            title=str(document.get("title", "")) if isinstance(document, dict) else "",
            body=str(document.get("body", "")) if isinstance(document, dict) else "",
        )
        for document in _list_or_empty(value)
    )


def _comments_from_payload(value: object) -> tuple[WorkspaceCommentRecord, ...]:
    return tuple(
        WorkspaceCommentRecord(
            comment_id=(
                str(comment.get("comment_id", ""))
                if isinstance(comment, dict)
                else ""
            ),
            task_id=str(comment.get("task_id", "")) if isinstance(comment, dict) else "",
            body=str(comment.get("body", "")) if isinstance(comment, dict) else "",
            created_at=(
                str(comment.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(comment, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for comment in _list_or_empty(value)
    )


def _list_or_empty(value: object) -> list[object]:
    return value if isinstance(value, list) else []
