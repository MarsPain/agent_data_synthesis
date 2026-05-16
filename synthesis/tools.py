from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from synthesis.environments import ContactEnvironment


ToolHandler = Callable[[dict[str, object]], dict[str, object]]


class ToolRegistryError(RuntimeError):
    pass


class ToolMissingError(ToolRegistryError):
    pass


class ToolSchemaError(ToolRegistryError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    schema: dict[str, object]
    side_effects: str

    def export(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "schema": self.schema,
            "side_effects": self.side_effects,
        }


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._tools[definition.name] = RegisteredTool(definition, handler)

    def execute(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name not in self._tools:
            raise ToolMissingError(f"Unknown tool: {name}")
        tool = self._tools[name]
        _validate_arguments(tool.definition, arguments)
        return tool.handler(arguments)

    def export(self) -> list[dict[str, object]]:
        return [tool.definition.export() for tool in self._tools.values()]


def build_contact_tool_registry(environment: ContactEnvironment) -> ToolRegistry:
    registry = ToolRegistry()

    def lookup_contact_email(arguments: dict[str, object]) -> dict[str, object]:
        name = arguments.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("lookup_contact_email requires a non-empty string name")
        return environment.lookup_email(name)

    registry.register(
        ToolDefinition(
            name="lookup_contact_email",
            version="tool_lookup_contact_email_v1",
            schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full contact name to look up.",
                    }
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            side_effects="read_only",
        ),
        lookup_contact_email,
    )

    def record_contact_followup(arguments: dict[str, object]) -> dict[str, object]:
        name = arguments.get("name")
        note = arguments.get("note")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("record_contact_followup requires a non-empty string name")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("record_contact_followup requires a non-empty string note")
        return environment.record_followup(name, note)

    registry.register(
        ToolDefinition(
            name="record_contact_followup",
            version="tool_record_contact_followup_v1",
            schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full contact name receiving a follow-up note.",
                    },
                    "note": {
                        "type": "string",
                        "description": "Follow-up note to persist for the contact.",
                    },
                },
                "required": ["name", "note"],
                "additionalProperties": False,
            },
            side_effects="state_mutating",
        ),
        record_contact_followup,
    )
    return registry


def _validate_arguments(definition: ToolDefinition, arguments: dict[str, object]) -> None:
    schema = definition.schema
    if schema.get("type") != "object":
        raise ToolSchemaError(f"{definition.name} schema must be an object schema")
    if not isinstance(arguments, dict):
        raise ToolSchemaError(f"{definition.name} arguments must be an object")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ToolSchemaError(f"{definition.name} schema properties must be an object")

    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ToolSchemaError(f"{definition.name} schema required must be a list")
    for field_name in required:
        if not isinstance(field_name, str):
            raise ToolSchemaError(f"{definition.name} schema required entries must be strings")
        if field_name not in arguments:
            raise ToolSchemaError(f"{definition.name} missing required argument: {field_name}")

    if schema.get("additionalProperties") is False:
        allowed = set(properties)
        extra = set(arguments) - allowed
        if extra:
            names = ", ".join(sorted(extra))
            raise ToolSchemaError(f"{definition.name} has unexpected arguments: {names}")

    for field_name, raw_property_schema in properties.items():
        if field_name not in arguments:
            continue
        if not isinstance(raw_property_schema, dict):
            raise ToolSchemaError(f"{definition.name}.{field_name} schema must be an object")
        expected_type = raw_property_schema.get("type")
        value = arguments[field_name]
        if expected_type == "string" and not isinstance(value, str):
            raise ToolSchemaError(f"{definition.name}.{field_name} must be a string")
