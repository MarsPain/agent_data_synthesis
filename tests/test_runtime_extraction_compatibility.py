from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class RuntimeExtractionCompatibilityTest(unittest.TestCase):
    def test_awm_runtime_import_does_not_load_forbidden_synthesis_modules(self) -> None:
        forbidden_modules = (
            "synthesis.datasets",
            "synthesis.dataset_release",
            "synthesis.profile_decisions",
            "synthesis.release_pack",
            "synthesis.release_quality",
            "synthesis.sources",
            "synthesis.domain_sources",
            "synthesis.environments",
            "synthesis.mobile_environment",
            "synthesis.domain_pipeline",
            "synthesis.pipeline",
            "main",
        )
        script = textwrap.dedent(
            f"""
            import importlib
            import json
            import sys

            importlib.import_module("awm_runtime")

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

    def test_synthesis_runtime_reexports_boundary_owned_runtime_symbols(self) -> None:
        import awm_runtime
        import synthesis.runtime as compatibility_runtime

        boundary_owned_symbols = (
            "EnvironmentRuntime",
            "RUNTIME_CAPABILITY_FIELDS",
            "RUNTIME_CAPABILITY_STATUSES",
            "RuntimeActionRequest",
            "RuntimeActionResult",
            "RuntimeCapabilityDescriptor",
            "RuntimeMetadata",
            "RuntimeRegistry",
            "RuntimeSession",
            "runtime_metadata_from_environment",
            "validate_runtime_descriptor_safety",
            "validate_runtime_metadata_safety",
        )

        for symbol_name in boundary_owned_symbols:
            with self.subTest(symbol_name=symbol_name):
                self.assertIs(
                    getattr(compatibility_runtime, symbol_name),
                    getattr(awm_runtime, symbol_name),
                )

    def test_synthesis_runtime_registry_convenience_functions_match_with_explicit_registry(
        self,
    ) -> None:
        import awm_runtime
        import synthesis.runtime as compatibility_runtime

        descriptor = awm_runtime.RuntimeCapabilityDescriptor(
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
        registry = awm_runtime.RuntimeRegistry((descriptor,))

        self.assertEqual(
            compatibility_runtime.registered_runtime_ids(registry),
            awm_runtime.registered_runtime_ids(registry),
        )
        self.assertIs(
            compatibility_runtime.runtime_descriptor("fake_runtime", registry),
            awm_runtime.runtime_descriptor("fake_runtime", registry),
        )
        self.assertEqual(
            compatibility_runtime.runtime_capability_status(
                "fake_runtime",
                "supports_reward_labels",
                registry,
            ),
            awm_runtime.runtime_capability_status(
                "fake_runtime",
                "supports_reward_labels",
                registry,
            ),
        )
        self.assertEqual(
            compatibility_runtime.runtime_registry_with(
                descriptor,
                base=awm_runtime.RuntimeRegistry(()),
            ).registered_runtime_ids(),
            awm_runtime.runtime_registry_with(
                descriptor,
                base=awm_runtime.RuntimeRegistry(()),
            ).registered_runtime_ids(),
        )

    def test_synthesis_episodes_reexports_boundary_episode_symbols(self) -> None:
        import awm_runtime
        import synthesis.episodes as compatibility_episodes

        boundary_owned_symbols = (
            "EpisodeLog",
            "EpisodeTransition",
            "build_episode_log",
            "deterministic_content_hash",
            "sanitize_episode_value",
            "summarize_episode_for_quality",
        )

        for symbol_name in boundary_owned_symbols:
            with self.subTest(symbol_name=symbol_name):
                self.assertIs(
                    getattr(compatibility_episodes, symbol_name),
                    getattr(awm_runtime, symbol_name),
                )

    def test_runtime_facing_production_modules_do_not_import_compatibility_shims(
        self,
    ) -> None:
        runtime_facing_paths = (
            "synthesis/domain_pipeline.py",
            "synthesis/episodes.py",
            "synthesis/episode_quality.py",
            "synthesis/episode_replay.py",
            "synthesis/reward_labels.py",
            "synthesis/rollouts.py",
            "synthesis/mcp.py",
        )
        compatibility_shims = {
            "synthesis/episodes.py": "compatibility shim for legacy episode imports",
        }
        forbidden_imports = (
            re.compile(r"^\s*from\s+synthesis\.runtime\s+import\s+", re.MULTILINE),
            re.compile(r"^\s*import\s+synthesis\.runtime\s*$", re.MULTILINE),
            re.compile(r"^\s*from\s+synthesis\.episodes\s+import\s+", re.MULTILINE),
            re.compile(r"^\s*import\s+synthesis\.episodes\s*$", re.MULTILINE),
        )
        violations: list[str] = []
        for relative_path in runtime_facing_paths:
            if relative_path in compatibility_shims:
                continue
            source = Path(relative_path).read_text(encoding="utf-8")
            for forbidden_import in forbidden_imports:
                if forbidden_import.search(source):
                    violations.append(f"{relative_path}: {forbidden_import.pattern}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
