from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


def _python_files_under(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root in paths:
        root_path = Path(root)
        if root_path.is_file() and root_path.suffix == ".py":
            files.append(root_path)
            continue
        if root_path.is_dir():
            files.extend(
                path for path in root_path.rglob("*.py") if ".venv" not in path.parts
            )
    return sorted(files)


def _removed_shim_import_violations(paths: tuple[str, ...]) -> list[str]:
    removed_modules = {"synthesis.runtime", "synthesis.episodes"}
    violations: list[str] = []
    for path in _python_files_under(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in removed_modules:
                violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in removed_modules:
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
    return violations


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

    def test_runtime_compatibility_shim_files_are_removed(self) -> None:
        self.assertFalse(Path("synthesis/runtime.py").exists())
        self.assertFalse(Path("synthesis/episodes.py").exists())

    def test_no_python_imports_reference_removed_runtime_shims(self) -> None:
        violations = _removed_shim_import_violations(("synthesis", "tests"))
        self.assertEqual(violations, [])

    def test_runtime_facing_production_modules_do_not_import_compatibility_shims(
        self,
    ) -> None:
        runtime_facing_paths = (
            "synthesis/domain_pipeline.py",
            "synthesis/episode_quality.py",
            "synthesis/episode_replay.py",
            "synthesis/reward_labels.py",
            "synthesis/rollouts.py",
            "synthesis/mcp.py",
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
