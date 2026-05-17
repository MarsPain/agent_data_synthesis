import unittest

from synthesis.roles import (
    DisabledRoleError,
    RoleDefinition,
    RoleRegistry,
    default_role_registry,
)


class RoleRegistryTests(unittest.TestCase):
    def test_default_registry_contains_current_enabled_roles_in_deterministic_order(self) -> None:
        registry = default_role_registry()

        self.assertEqual(
            [role.name for role in registry.enabled_roles()],
            [
                "critic_refinement",
                "solution_policy",
                "task_editor",
                "task_generation",
                "task_suggester",
                "tool_generation",
            ],
        )
        task_role = registry.require_enabled("task_generation")
        self.assertEqual(task_role.version, "role_task_generation_v1")
        self.assertEqual(task_role.owner_module, "synthesis.tasks")
        self.assertEqual(task_role.output_type, "candidate_tasks")
        self.assertEqual(task_role.retry_policy, "bounded_remote_json")
        self.assertIn("role_version", task_role.lineage_fields)
        self.assertIn("output_type", task_role.lineage_fields)

    def test_default_registry_enables_tool_generation_only_for_proposals(self) -> None:
        registry = default_role_registry()

        role = registry.require_enabled("tool_generation")
        self.assertEqual(role.version, "role_tool_generation_v1")
        self.assertEqual(role.owner_module, "synthesis.tools")
        self.assertEqual(role.output_type, "tool_proposal")

    def test_default_registry_enables_task_suggester_and_editor_contract_roles(self) -> None:
        registry = default_role_registry()

        suggester = registry.require_enabled("task_suggester")
        editor = registry.require_enabled("task_editor")

        self.assertEqual(suggester.version, "role_task_suggester_v1")
        self.assertEqual(suggester.owner_module, "synthesis.tasks")
        self.assertEqual(suggester.output_type, "task_suggestion")
        self.assertEqual(editor.version, "role_task_editor_v1")
        self.assertEqual(editor.owner_module, "synthesis.tasks")
        self.assertEqual(editor.output_type, "edited_task")

    def test_default_registry_keeps_other_future_roles_disabled(self) -> None:
        registry = default_role_registry()

        with self.assertRaisesRegex(DisabledRoleError, "tool_generation"):
            RoleRegistry([registry.get("tool_generation").__class__(
                name="tool_generation",
                version="role_tool_generation_v0",
                owner_module="synthesis.tools",
                output_type="tool_definition",
                enabled=False,
                retry_policy="not_enabled",
                lineage_fields=("role",),
            )]).require_enabled("tool_generation")
        with self.assertRaisesRegex(DisabledRoleError, "environment_generation"):
            registry.require_enabled("environment_generation")
        with self.assertRaisesRegex(DisabledRoleError, "verifier_generation"):
            registry.require_enabled("verifier_generation")
        with self.assertRaisesRegex(DisabledRoleError, "judge_verification"):
            registry.require_enabled("judge_verification")

    def test_registry_rejects_duplicate_and_invalid_role_names(self) -> None:
        role = RoleDefinition(
            name="task_generation",
            version="role_task_generation_v1",
            owner_module="synthesis.tasks",
            output_type="candidate_tasks",
            enabled=True,
            retry_policy="bounded_remote_json",
            lineage_fields=("role",),
        )

        with self.assertRaisesRegex(ValueError, "duplicate role"):
            RoleRegistry([role, role])
        with self.assertRaisesRegex(ValueError, "role name"):
            RoleDefinition(
                name=" ",
                version="role_invalid_v1",
                owner_module="synthesis.tasks",
                output_type="candidate_tasks",
                enabled=True,
                retry_policy="bounded_remote_json",
                lineage_fields=("role",),
            )

    def test_invoke_json_does_not_call_client_for_disabled_role(self) -> None:
        registry = default_role_registry()
        client = _RecordingClient()

        with self.assertRaisesRegex(DisabledRoleError, "environment_generation"):
            registry.invoke_json("environment_generation", client, "prompt")

        self.assertEqual(client.calls, [])

    def test_invoke_json_adds_role_metadata_to_lineage(self) -> None:
        registry = default_role_registry()
        client = _RecordingClient()

        result = registry.invoke_json("solution_policy", client, "prompt")

        self.assertEqual(client.calls, [("prompt", "solution_policy")])
        self.assertEqual(result.lineage["role"], "solution_policy")
        self.assertEqual(result.lineage["role_version"], "role_solution_policy_v1")
        self.assertEqual(result.lineage["output_type"], "solution_policy")
        self.assertEqual(result.lineage["owner_module"], "synthesis.execution")


class _RecordingResult:
    def __init__(self) -> None:
        self.content = {"ok": True}
        self.lineage = {
            "role": "solution_policy",
            "provider_host": "example.test",
            "model": "model",
            "config_hash": "hash",
        }


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_json(self, prompt: str, *, role: str) -> _RecordingResult:
        self.calls.append((prompt, role))
        return _RecordingResult()


if __name__ == "__main__":
    unittest.main()
