from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from synthesis.llm import LLMProviderError
from synthesis.mutation_admission_config import MUTATION_ADMISSION_JUDGE_ROLE


ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

TASK_GENERATION_ROLE = "task_generation"
SOLUTION_POLICY_ROLE = "solution_policy"
CRITIC_REFINEMENT_ROLE = "critic_refinement"
ENVIRONMENT_GENERATION_ROLE = "environment_generation"
TOOL_GENERATION_ROLE = "tool_generation"
VERIFIER_GENERATION_ROLE = "verifier_generation"
JUDGE_VERIFICATION_ROLE = "judge_verification"
TASK_SUGGESTER_ROLE = "task_suggester"
TASK_EDITOR_ROLE = "task_editor"


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    version: str
    owner_module: str
    output_type: str
    enabled: bool
    retry_policy: str
    lineage_fields: tuple[str, ...]
    requires_sandbox_admission: bool = False

    def __post_init__(self) -> None:
        if not ROLE_NAME_RE.match(self.name):
            raise ValueError("role name must be a non-empty snake_case identifier")
        _require_non_empty(self.version, "role version")
        _require_non_empty(self.owner_module, "owner module")
        _require_non_empty(self.output_type, "output type")
        _require_non_empty(self.retry_policy, "retry policy")
        if not self.lineage_fields:
            raise ValueError("lineage_fields must contain at least one field")
        for field in self.lineage_fields:
            _require_non_empty(field, "lineage field")

    def lineage_metadata(self) -> dict[str, object]:
        return {
            "role_version": self.version,
            "output_type": self.output_type,
            "owner_module": self.owner_module,
            "retry_policy": self.retry_policy,
            "requires_sandbox_admission": self.requires_sandbox_admission,
        }


class DisabledRoleError(RuntimeError):
    def __init__(self, role: RoleDefinition) -> None:
        super().__init__(
            f"Role {role.name} is disabled. Enable it with an explicit plan "
            f"before producing {role.output_type}."
        )
        self.role = role


class RoleRegistry:
    def __init__(self, roles: Iterable[RoleDefinition]) -> None:
        by_name: dict[str, RoleDefinition] = {}
        for role in roles:
            if role.name in by_name:
                raise ValueError(f"duplicate role: {role.name}")
            by_name[role.name] = role
        self._roles = dict(sorted(by_name.items()))

    def get(self, name: str) -> RoleDefinition:
        try:
            return self._roles[name]
        except KeyError as exc:
            raise KeyError(f"unknown role: {name}") from exc

    def require_enabled(self, name: str) -> RoleDefinition:
        role = self.get(name)
        if not role.enabled:
            raise DisabledRoleError(role)
        return role

    def enabled_roles(self) -> list[RoleDefinition]:
        return [role for role in self._roles.values() if role.enabled]

    def roles(self) -> list[RoleDefinition]:
        """Return every registered role in deterministic name order."""

        return list(self._roles.values())

    def invoke_json(self, name: str, client: Any, prompt: str) -> Any:
        role = self.require_enabled(name)
        try:
            result = client.generate_json(prompt, role=role.name)
        except LLMProviderError as exc:
            exc.lineage.update(role.lineage_metadata())
            raise
        result.lineage.update(role.lineage_metadata())
        return result


def default_role_registry() -> RoleRegistry:
    return RoleRegistry(
        [
            _enabled_role(
                name=TASK_GENERATION_ROLE,
                version="role_task_generation_v1",
                owner_module="synthesis.tasks",
                output_type="candidate_tasks",
            ),
            _enabled_role(
                name=SOLUTION_POLICY_ROLE,
                version="role_solution_policy_v1",
                owner_module="synthesis.execution",
                output_type="solution_policy",
            ),
            _enabled_role(
                name=TASK_EDITOR_ROLE,
                version="role_task_editor_v1",
                owner_module="synthesis.tasks",
                output_type="edited_task",
            ),
            _enabled_role(
                name=CRITIC_REFINEMENT_ROLE,
                version="role_critic_refinement_v1",
                owner_module="synthesis.refinement",
                output_type="refinement_attempt",
            ),
            _disabled_role(
                name=ENVIRONMENT_GENERATION_ROLE,
                version="role_environment_generation_v0",
                owner_module="synthesis.environments",
                output_type="environment_definition",
                requires_sandbox_admission=True,
            ),
            _enabled_role(
                name=TOOL_GENERATION_ROLE,
                version="role_tool_generation_v1",
                owner_module="synthesis.tools",
                output_type="tool_proposal",
            ),
            _disabled_role(
                name=VERIFIER_GENERATION_ROLE,
                version="role_verifier_generation_v0",
                owner_module="synthesis.verification",
                output_type="verifier_definition",
                requires_sandbox_admission=True,
            ),
            _disabled_role(
                name=JUDGE_VERIFICATION_ROLE,
                version="role_judge_verification_v0",
                owner_module="synthesis.verification",
                output_type="judge_verdict",
            ),
            _enabled_role(
                name=MUTATION_ADMISSION_JUDGE_ROLE,
                version="role_mutation_admission_judge_v1",
                owner_module="synthesis.mutation_admission",
                output_type="semantic_mutation_verdict",
            ),
            _enabled_role(
                name=TASK_SUGGESTER_ROLE,
                version="role_task_suggester_v1",
                owner_module="synthesis.tasks",
                output_type="task_suggestion",
            ),
        ]
    )


def _enabled_role(
    *,
    name: str,
    version: str,
    owner_module: str,
    output_type: str,
) -> RoleDefinition:
    return RoleDefinition(
        name=name,
        version=version,
        owner_module=owner_module,
        output_type=output_type,
        enabled=True,
        retry_policy="bounded_remote_json",
        lineage_fields=_standard_lineage_fields(),
    )


def _disabled_role(
    *,
    name: str,
    version: str,
    owner_module: str,
    output_type: str,
    requires_sandbox_admission: bool = False,
) -> RoleDefinition:
    return RoleDefinition(
        name=name,
        version=version,
        owner_module=owner_module,
        output_type=output_type,
        enabled=False,
        retry_policy="not_enabled",
        lineage_fields=_standard_lineage_fields(),
        requires_sandbox_admission=requires_sandbox_admission,
    )


def _standard_lineage_fields() -> tuple[str, ...]:
    return (
        "role",
        "role_version",
        "output_type",
        "owner_module",
        "retry_policy",
        "provider_host",
        "model",
        "config_hash",
        "prompt_hash",
        "retry_count",
        "tokens",
        "error_class",
    )


def _require_non_empty(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
