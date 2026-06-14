from __future__ import annotations

import json

from synthesis.contracts import (
    ContractValidationError,
    validate_mobile_messages_environment_input_record,
)
from synthesis.mobile_environment import (
    DraftReplyRecord,
    MessageRecord,
    MessageThreadRecord,
    MobileMessagesEnvironmentInput,
    ReminderRecord,
)


class MobileMessagesSourceImporter:
    domain_id = "mobile_messages_fixture"
    source_kind = "local_mobile_messages_json"

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> MobileMessagesEnvironmentInput:
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("environment source JSON is invalid") from exc
        if not isinstance(document, dict):
            raise ValueError("environment source payload must be an object")

        environment_input = MobileMessagesEnvironmentInput(
            threads=_threads_from_payload(document.get("threads")),
            messages=_messages_from_payload(document.get("messages")),
            reminders=_reminders_from_payload(document.get("reminders", [])),
            draft_replies=_drafts_from_payload(document.get("draft_replies", [])),
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
        )
        try:
            validate_mobile_messages_environment_input_record(environment_input.export())
        except ContractValidationError as exc:
            raise ValueError("environment source payload is invalid") from exc
        return environment_input


def _threads_from_payload(value: object) -> tuple[MessageThreadRecord, ...]:
    return tuple(
        MessageThreadRecord(
            thread_id=str(thread.get("thread_id", "")) if isinstance(thread, dict) else "",
            participant=str(thread.get("participant", "")) if isinstance(thread, dict) else "",
        )
        for thread in _list_or_empty(value)
    )


def _messages_from_payload(value: object) -> tuple[MessageRecord, ...]:
    return tuple(
        MessageRecord(
            message_id=str(message.get("message_id", "")) if isinstance(message, dict) else "",
            thread_id=str(message.get("thread_id", "")) if isinstance(message, dict) else "",
            sender=str(message.get("sender", "")) if isinstance(message, dict) else "",
            body=str(message.get("body", "")) if isinstance(message, dict) else "",
            received_at=str(message.get("received_at", "")) if isinstance(message, dict) else "",
        )
        for message in _list_or_empty(value)
    )


def _reminders_from_payload(value: object) -> tuple[ReminderRecord, ...]:
    return tuple(
        ReminderRecord(
            reminder_id=(
                str(reminder.get("reminder_id", ""))
                if isinstance(reminder, dict)
                else ""
            ),
            title=str(reminder.get("title", "")) if isinstance(reminder, dict) else "",
            due_at=_optional_text(reminder.get("due_at")) if isinstance(reminder, dict) else None,
            source_message_id=(
                _optional_text(reminder.get("source_message_id"))
                if isinstance(reminder, dict)
                else None
            ),
            created_at=(
                str(reminder.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(reminder, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for reminder in _list_or_empty(value)
    )


def _drafts_from_payload(value: object) -> tuple[DraftReplyRecord, ...]:
    return tuple(
        DraftReplyRecord(
            draft_id=str(draft.get("draft_id", "")) if isinstance(draft, dict) else "",
            thread_id=str(draft.get("thread_id", "")) if isinstance(draft, dict) else "",
            body=str(draft.get("body", "")) if isinstance(draft, dict) else "",
            created_at=(
                str(draft.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(draft, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for draft in _list_or_empty(value)
    )


def _list_or_empty(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
