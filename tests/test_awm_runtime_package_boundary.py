from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
import re


class AwmRuntimePackageBoundaryTest(unittest.TestCase):
    def test_package_import_does_not_load_synthesis_domain_or_dataset_modules(self) -> None:
        forbidden_modules = (
            "synthesis.datasets",
            "synthesis.dataset_release",
            "synthesis.profile_decisions",
            "synthesis.domain_pipeline",
            "synthesis.environments",
            "synthesis.mobile_environment",
            "synthesis.tasks",
            "synthesis.mobile_tasks",
            "main",
        )
        script = textwrap.dedent(
            f"""
            import importlib
            import json
            import sys

            importlib.import_module("awm_runtime")
            importlib.import_module("awm_runtime.runtime")
            importlib.import_module("awm_runtime.episodes")

            forbidden = {forbidden_modules!r}
            loaded = sorted(name for name in forbidden if name in sys.modules)
            print(json.dumps(loaded))
            sys.exit(1 if loaded else 0)
            """
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_runtime_boundary_exports_stable_primitives(self) -> None:
        from awm_runtime import (
            EnvironmentRuntime,
            RuntimeActionRequest,
            RuntimeActionResult,
            RuntimeCapabilityDescriptor,
            RuntimeMetadata,
            RuntimeRegistry,
            RuntimeSession,
            runtime_capability_status,
            runtime_descriptor,
            runtime_registry_with,
        )

        descriptor = RuntimeCapabilityDescriptor(
            runtime_id="fake_runtime",
            runtime_version="runtime_fake_v1",
            domain_id="fake_domain",
            supports_rebuild=False,
            supports_checkpoint_restore=False,
            supports_episode_replay=False,
            supports_reward_labels=True,
            supports_local_adapter=False,
            state_changing_tools=("fake_write",),
            task_taxonomy=("fake_lookup",),
        )
        registry = RuntimeRegistry((descriptor,))

        self.assertIs(registry.descriptor("fake_runtime"), descriptor)
        self.assertIs(runtime_descriptor("fake_runtime", registry), descriptor)
        self.assertEqual(
            runtime_capability_status(
                "fake_runtime",
                "supports_reward_labels",
                registry,
            ),
            "supported",
        )
        self.assertEqual(
            runtime_registry_with(descriptor).registered_runtime_ids(),
            ("fake_runtime",),
        )
        self.assertTrue(hasattr(EnvironmentRuntime, "__instancecheck__"))
        self.assertEqual(RuntimeMetadata.__name__, "RuntimeMetadata")
        self.assertEqual(RuntimeActionRequest.__name__, "RuntimeActionRequest")
        self.assertEqual(RuntimeActionResult.__name__, "RuntimeActionResult")
        self.assertEqual(RuntimeSession.__name__, "RuntimeSession")

    def test_compatibility_runtime_imports_reexport_new_boundary_symbols(self) -> None:
        import awm_runtime
        import synthesis.runtime as compatibility_runtime

        self.assertIs(
            compatibility_runtime.RuntimeCapabilityDescriptor,
            awm_runtime.RuntimeCapabilityDescriptor,
        )
        self.assertIs(compatibility_runtime.RuntimeRegistry, awm_runtime.RuntimeRegistry)
        self.assertIs(compatibility_runtime.RuntimeMetadata, awm_runtime.RuntimeMetadata)
        self.assertIs(compatibility_runtime.RuntimeActionRequest, awm_runtime.RuntimeActionRequest)
        self.assertIs(compatibility_runtime.RuntimeActionResult, awm_runtime.RuntimeActionResult)
        self.assertIs(compatibility_runtime.RuntimeSession, awm_runtime.RuntimeSession)
        self.assertEqual(
            compatibility_runtime.registered_runtime_ids(),
            ("contacts_fixture", "mobile_messages_fixture"),
        )

    def test_episode_boundary_and_compatibility_imports_match(self) -> None:
        import awm_runtime.episodes as boundary_episodes
        import synthesis.episodes as compatibility_episodes

        self.assertIs(
            compatibility_episodes.EpisodeTransition,
            boundary_episodes.EpisodeTransition,
        )
        self.assertIs(compatibility_episodes.EpisodeLog, boundary_episodes.EpisodeLog)
        self.assertIs(
            compatibility_episodes.build_episode_log,
            boundary_episodes.build_episode_log,
        )
        self.assertIs(
            compatibility_episodes.deterministic_content_hash,
            boundary_episodes.deterministic_content_hash,
        )
        self.assertIs(
            compatibility_episodes.summarize_episode_for_quality,
            boundary_episodes.summarize_episode_for_quality,
        )

    def test_runtime_facing_production_modules_do_not_import_compatibility_shims(self) -> None:
        runtime_facing_paths = (
            "synthesis/candidate_processing.py",
            "synthesis/domain_pipeline.py",
            "synthesis/environments.py",
            "synthesis/episode_quality.py",
            "synthesis/episode_replay.py",
            "synthesis/mcp.py",
            "synthesis/mobile_environment.py",
            "synthesis/reward_labels.py",
            "synthesis/rollouts.py",
        )
        forbidden_imports = (
            re.compile(r"^\s*from\s+synthesis\.runtime\s+import\s+", re.MULTILINE),
            re.compile(r"^\s*import\s+synthesis\.runtime\s*$", re.MULTILINE),
            re.compile(r"^\s*from\s+synthesis\.episodes\s+import\s+", re.MULTILINE),
            re.compile(r"^\s*import\s+synthesis\.episodes\s*$", re.MULTILINE),
        )
        violations: list[str] = []
        for relative_path in runtime_facing_paths:
            source = Path(relative_path).read_text(encoding="utf-8")
            for forbidden_import in forbidden_imports:
                if forbidden_import.search(source):
                    violations.append(f"{relative_path}: {forbidden_import.pattern}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
