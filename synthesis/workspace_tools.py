from __future__ import annotations

from synthesis.tools import ToolDefinition, ToolRegistry
from synthesis.workspace_environment import WorkspaceTasksEnvironment


def build_workspace_tool_registry(environment: WorkspaceTasksEnvironment) -> ToolRegistry:
    registry = ToolRegistry(
        checkpoint_state=environment.checkpoint,
        restore_state=environment.restore_checkpoint,
    )

    def search_workspace_items(arguments: dict[str, object]) -> dict[str, object]:
        query = _required_string(arguments, "query", "search_workspace_items")
        kind = arguments.get("kind")
        if kind is not None and (not isinstance(kind, str) or not kind.strip()):
            raise ValueError(
                "search_workspace_items requires kind to be a non-empty string when provided"
            )
        return environment.search_workspace_items(
            query=query,
            kind=kind if isinstance(kind, str) else None,
        )

    registry.register(
        ToolDefinition(
            name="search_workspace_items",
            version="tool_search_workspace_items_v1",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            side_effects="read_only",
        ),
        search_workspace_items,
    )

    def create_workspace_task(arguments: dict[str, object]) -> dict[str, object]:
        return environment.create_workspace_task(
            project_id=_required_string(
                arguments,
                "project_id",
                "create_workspace_task",
            ),
            title=_required_string(arguments, "title", "create_workspace_task"),
            priority=_required_string(arguments, "priority", "create_workspace_task"),
            due_label=_required_string(arguments, "due_label", "create_workspace_task"),
        )

    registry.register(
        ToolDefinition(
            name="create_workspace_task",
            version="tool_create_workspace_task_v1",
            schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "title": {"type": "string"},
                    "priority": {"type": "string"},
                    "due_label": {"type": "string"},
                },
                "required": ["project_id", "title", "priority", "due_label"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        create_workspace_task,
    )

    def add_workspace_comment(arguments: dict[str, object]) -> dict[str, object]:
        return environment.add_workspace_comment(
            task_id=_required_string(arguments, "task_id", "add_workspace_comment"),
            comment=_required_string(arguments, "comment", "add_workspace_comment"),
        )

    registry.register(
        ToolDefinition(
            name="add_workspace_comment",
            version="tool_add_workspace_comment_v1",
            schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "comment": {"type": "string"},
                },
                "required": ["task_id", "comment"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        add_workspace_comment,
    )
    return registry


def _required_string(
    arguments: dict[str, object],
    field_name: str,
    tool_name: str,
) -> str:
    value = arguments.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{tool_name} requires a non-empty string {field_name}")
    return value
