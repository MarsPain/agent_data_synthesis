from __future__ import annotations

import unittest
from pathlib import Path


class DomainPackContractTest(unittest.TestCase):
    def test_workspace_domain_is_registered_through_domain_pack_boundary(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.runtime_registry import runtime_descriptor
        from tests.test_workspace_pipeline import workspace_seed

        with self.subTest(boundary="runtime_descriptor"):
            descriptor = runtime_descriptor("workspace_tasks_fixture")
            self.assertEqual(descriptor.domain_id, "workspace_tasks_fixture")
            self.assertIn("create_workspace_task", descriptor.state_changing_tools)

        with self.subTest(boundary="domain_pipeline"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                bundle = build_domain_pipeline_bundle(workspace_seed(), Path(tmpdir))

            self.assertEqual(bundle.domain_id, "workspace_tasks_fixture")
            self.assertIn("search_workspace_items", bundle.registry.tool_names())

    def test_workspace_support_does_not_add_core_consumer_allowlists(self) -> None:
        forbidden_paths = (
            Path("synthesis/episode_quality.py"),
            Path("synthesis/episode_replay.py"),
            Path("synthesis/reward_labels.py"),
            Path("synthesis/rollouts.py"),
            Path("synthesis/mcp.py"),
            Path("synthesis/profile_decisions.py"),
            Path("synthesis/dataset_release.py"),
        )

        for path in forbidden_paths:
            with self.subTest(path=str(path)):
                source = path.read_text(encoding="utf-8").lower()
                self.assertNotIn("workspace_tasks_fixture", source)
                self.assertNotIn("workspace_", source)
                self.assertNotIn("search_workspace_items", source)
                self.assertNotIn("create_workspace_task", source)
                self.assertNotIn("add_workspace_comment", source)

    def test_workspace_specific_code_is_limited_to_allowed_boundaries(self) -> None:
        allowed_prefixes = (
            "synthesis/workspace_",
            "synthesis/domain_pipeline.py",
            "synthesis/runtime_registry.py",
            "synthesis/evaluation.py",
            "synthesis/run_profiles.py",
            "tests/",
            "docs/",
        )
        allowed_exact = {
            "synthesis/contracts.py",
            "synthesis/domain_pack.py",
            "synthesis/qualification.py",
            "synthesis/coverage_registry.py",
            "synthesis/domain_sources.py",
            "synthesis/compatibility.py",
            "synthesis/pipeline.py",
            "synthesis/scale_evidence.py",
            "synthesis/task_contracts.py",
            "synthesis/verification.py",
        }
        for path in Path(".").glob("**/*.py"):
            if ".worktrees" in path.parts or ".git" in path.parts:
                continue
            source = path.read_text(encoding="utf-8").lower()
            if "workspace" not in source:
                continue
            normalized = path.as_posix()
            self.assertTrue(
                normalized in allowed_exact
                or any(normalized.startswith(prefix) for prefix in allowed_prefixes),
                f"workspace-specific code found outside allowed boundaries: {normalized}",
            )


if __name__ == "__main__":
    unittest.main()
