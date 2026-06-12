from __future__ import annotations

from synthesis.mobile_environment import MobileMessagesEnvironment
from synthesis.tools import ToolDefinition, ToolRegistry


def build_mobile_tool_registry(environment: MobileMessagesEnvironment) -> ToolRegistry:
    registry = ToolRegistry(
        checkpoint_state=environment.checkpoint,
        restore_state=environment.restore_checkpoint,
    )

    def search_phone_messages(arguments: dict[str, object]) -> dict[str, object]:
        query = _required_string(arguments, "query", "search_phone_messages")
        participant = arguments.get("participant")
        if participant is not None and (
            not isinstance(participant, str) or not participant.strip()
        ):
            raise ValueError(
                "search_phone_messages requires participant to be a non-empty string when provided"
            )
        return environment.search_messages(
            query=query,
            participant=participant if isinstance(participant, str) else None,
        )

    registry.register(
        ToolDefinition(
            name="search_phone_messages",
            version="tool_search_phone_messages_v1",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "participant": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            side_effects="read_only",
        ),
        search_phone_messages,
    )

    def create_phone_reminder(arguments: dict[str, object]) -> dict[str, object]:
        title = _required_string(arguments, "title", "create_phone_reminder")
        due_at = arguments.get("due_at")
        source_message_id = arguments.get("source_message_id")
        if due_at is not None and (not isinstance(due_at, str) or not due_at.strip()):
            raise ValueError(
                "create_phone_reminder requires due_at to be a non-empty string when provided"
            )
        if source_message_id is not None and (
            not isinstance(source_message_id, str) or not source_message_id.strip()
        ):
            raise ValueError(
                "create_phone_reminder requires source_message_id to be a non-empty string when provided"
            )
        return environment.create_reminder(
            title=title,
            due_at=due_at if isinstance(due_at, str) else None,
            source_message_id=source_message_id if isinstance(source_message_id, str) else None,
        )

    registry.register(
        ToolDefinition(
            name="create_phone_reminder",
            version="tool_create_phone_reminder_v1",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_at": {"type": "string"},
                    "source_message_id": {"type": "string"},
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        create_phone_reminder,
    )

    def draft_message_reply(arguments: dict[str, object]) -> dict[str, object]:
        thread_id = _required_string(arguments, "thread_id", "draft_message_reply")
        body = _required_string(arguments, "body", "draft_message_reply")
        return environment.draft_reply(thread_id=thread_id, body=body)

    registry.register(
        ToolDefinition(
            name="draft_message_reply",
            version="tool_draft_message_reply_v1",
            schema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["thread_id", "body"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        draft_message_reply,
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
