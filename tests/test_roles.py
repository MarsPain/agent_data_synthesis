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
            ["critic_refinement", "solution_policy", "task_generation"],
        )
        task_role = registry.require_enabled("task_generation")
        self.assertEqual(task_role.version, "role_task_generation_v1")
        self.assertEqual(task_role.owner_module, "synthesis.tasks")
        self.assertEqual(task_role.output_type, "candidate_tasks")
        self.assertEqual(task_role.retry_policy, "bounded_remote_json")
        self.assertIn("role_version", task_role.lineage_fields)
        self.assertIn("output_type", task_role.lineage_fields)

    def test_default_registry_contains_disabled_future_roles(self) -> None:
        registry = default_role_registry()

        self.assertEqual(registry.get("tool_generation").enabled, False)
        with self.assertRaisesRegex(DisabledRoleError, "tool_generation"):
            registry.require_enabled("tool_generation")

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
