from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from synthesis.environments import ContactEnvironment


ToolHandler = Callable[[dict[str, object]], dict[str, object]]


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
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].handler(arguments)

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
    return registry
