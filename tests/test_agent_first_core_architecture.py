from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
import tomllib
import unittest
from pathlib import Path

from pydantic import ValidationError

from agent_synthesis import AdapterRegistry, FrozenInitialState, RunConfiguration


ROOT = Path(__file__).resolve().parents[1]
CORE_PACKAGE = ROOT / "agent_synthesis"
FORBIDDEN_IMPORT_ROOTS = {
    "synthesis",
    "awm_runtime",
    "release_lab",
    "importlib",
    "builtins",
}
PRODUCTION_DOMAIN_MARKERS = ("contacts", "mobile", "workspace")


class _IncompleteDomain:
    domain_id = "incomplete_domain"


class AgentFirstCoreArchitectureTest(unittest.TestCase):
    def test_configuration_is_validated_before_the_engine_can_use_it(self) -> None:
        with self.assertRaises(ValidationError):
            RunConfiguration.model_validate(
                {
                    "run_id": "validated-run",
                    "domain_id": "test_domain",
                    "model_id": "test_model",
                    "slot_limit": 1,
                    "unexpected_domain_escape_hatch": True,
                }
            )

    def test_configuration_rejects_a_secret_shaped_model_identity(self) -> None:
        with self.assertRaises(ValidationError):
            RunConfiguration(
                run_id="validated-run",
                domain_id="test_domain",
                model_id="sk-live-credential",
                slot_limit=1,
            )

    def test_configuration_rejects_embedded_secret_markers(self) -> None:
        with self.assertRaises(ValidationError):
            RunConfiguration(
                run_id="validated-run",
                domain_id="test_domain",
                model_id="client_secret_abc",
                slot_limit=1,
            )

    def test_registry_rejects_an_adapter_that_does_not_satisfy_the_domain_seam(self) -> None:
        with self.assertRaises(ValueError):
            AdapterRegistry(domains=(_IncompleteDomain(),), models=())

    def test_frozen_initial_state_rejects_a_fingerprint_that_does_not_bind_its_bytes(self) -> None:
        with self.assertRaises(ValidationError):
            FrozenInitialState(
                fingerprint="sha256:" + "0" * 64,
                contents=b"fixture bytes",
            )

    def test_core_import_does_not_load_legacy_packages(self) -> None:
        script = textwrap.dedent(
            """
            import json
            import sys

            import agent_synthesis

            forbidden = [
                name
                for name in sys.modules
                if name == "synthesis" or name.startswith("synthesis.")
                or name == "awm_runtime" or name.startswith("awm_runtime.")
            ]
            print(json.dumps(forbidden))
            raise SystemExit(bool(forbidden))
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_glossary_distinguishes_the_agent_first_adapter_from_the_legacy_pack(self) -> None:
        glossary = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Agent-first Domain adapter:**", glossary)
        self.assertIn("**Domain Pack (legacy core):**", glossary)

    def test_core_source_rejects_legacy_production_domain_and_release_lab_dependencies(self) -> None:
        imports: list[str] = []
        dynamic_imports: list[str] = []
        for source_path in CORE_PACKAGE.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            imports.extend(_import_targets(tree))
            dynamic_imports.extend(
                f"{source_path.relative_to(CORE_PACKAGE)}:{call}"
                for call in _dynamic_import_calls(tree)
            )

        self.assertEqual(_forbidden_import_targets(imports), [])
        self.assertEqual(dynamic_imports, [])
        production_module_files = [
            path.relative_to(CORE_PACKAGE).as_posix()
            for path in CORE_PACKAGE.rglob("*.py")
            if any(marker in path.stem.lower() for marker in PRODUCTION_DOMAIN_MARKERS)
        ]
        self.assertEqual(production_module_files, [])
        self.assertFalse((CORE_PACKAGE / "contracts.py").exists())
        self.assertFalse((ROOT / "release_lab").exists())

    def test_production_domain_import_aliases_are_rejected(self) -> None:
        tree = ast.parse("from domain_adapters import ContactsDomain")
        self.assertEqual(
            _forbidden_import_targets(_import_targets(tree)),
            ["domain_adapters.ContactsDomain"],
        )

    def test_dynamic_import_calls_are_rejected_by_the_architecture_guard(self) -> None:
        tree = ast.parse(
            "import importlib\nimportlib.import_module('domain_adapters.ContactsDomain')"
        )
        self.assertEqual(_dynamic_import_calls(tree), ["importlib.import_module"])

    def test_dynamic_import_aliases_and_builtins_are_rejected(self) -> None:
        tree = ast.parse(
            "from importlib import import_module\n"
            "import builtins\n"
            "import_module('domain_adapters.ContactsDomain')\n"
            "builtins.__import__('domain_adapters.ContactsDomain')\n"
            "__builtins__.__import__('domain_adapters.ContactsDomain')"
        )
        self.assertEqual(
            _dynamic_import_calls(tree),
            ["import_module", "builtins.__import__", "__builtins__.__import__"],
        )
        self.assertEqual(
            _forbidden_import_targets(_import_targets(tree)),
            ["importlib.import_module", "builtins"],
        )

    def test_pydantic_is_a_direct_runtime_dependency_of_the_new_core(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = project["project"]["dependencies"]
        self.assertTrue(
            any(dependency.startswith("pydantic") for dependency in dependencies),
            "the Agent-first core validates persistence models with Pydantic",
        )


def _import_targets(tree: ast.AST) -> list[str]:
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            targets.extend(
                f"{module}.{alias.name}" if module else alias.name
                for alias in node.names
            )
    return targets


def _forbidden_import_targets(imports: list[str]) -> list[str]:
    return [
        imported
        for imported in imports
        if imported.split(".", maxsplit=1)[0] in FORBIDDEN_IMPORT_ROOTS
        or any(
            marker in module_part.lower()
            for marker in PRODUCTION_DOMAIN_MARKERS
            for module_part in imported.split(".")
        )
    ]


def _dynamic_import_calls(tree: ast.AST) -> list[str]:
    importlib_names = {"importlib"}
    import_module_names: set[str] = set()
    builtins_names = {"builtins", "__builtins__"}
    builtin_import_names = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
                if alias.name == "builtins":
                    builtins_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                import_module_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "import_module"
                )
            if node.module == "builtins":
                builtin_import_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "__import__"
                )

    calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in (
            import_module_names | builtin_import_names
        ):
            calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in importlib_names:
                calls.append(f"{owner.id}.import_module")
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "__import__":
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in builtins_names:
                calls.append(f"{owner.id}.__import__")
    return calls


if __name__ == "__main__":
    unittest.main()
