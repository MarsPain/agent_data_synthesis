from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class SandboxScannerTest(unittest.TestCase):
    def test_safe_pure_python_artifact_scans_cleanly(self) -> None:
        from synthesis.sandbox import GeneratedExecutableArtifact, scan_python_source

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_safe",
            artifact_kind="tool_handler",
            source_code="def handler(payload):\n    return {'ok': True, 'name': payload['name']}\n",
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        )

        scan = scan_python_source(artifact)

        self.assertEqual(scan.status, "passed")
        self.assertEqual(scan.violations, [])
        self.assertEqual(scan.source_hash, artifact.source_hash)

    def test_static_scanner_rejects_forbidden_imports_dynamic_eval_and_secrets(self) -> None:
        from synthesis.sandbox import GeneratedExecutableArtifact, scan_python_source

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_unsafe",
            artifact_kind="tool_handler",
            source_code=(
                "import os\n"
                "def handler(payload):\n"
                "    token = 'sk-live-1234567890abcdef1234567890abcdef'\n"
                "    return eval(payload['expr'])\n"
            ),
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        )

        scan = scan_python_source(artifact)

        self.assertEqual(scan.status, "rejected")
        categories = {violation["category"] for violation in scan.violations}
        self.assertIn("forbidden_import", categories)
        self.assertIn("dynamic_evaluation", categories)
        self.assertIn("raw_secret", categories)
        exported = json.dumps(scan.export(), sort_keys=True)
        self.assertNotIn("sk-live", exported)
        self.assertNotIn("eval(payload", exported)

    def test_static_scanner_rejects_filesystem_escape_and_network_access(self) -> None:
        from synthesis.sandbox import GeneratedExecutableArtifact, scan_python_source

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_escape",
            artifact_kind="environment_builder",
            source_code=(
                "import socket\n"
                "def build(payload):\n"
                "    return {'path': '/Users/H/.ssh/id_rsa', 'up': '../outside'}\n"
            ),
            declared_entrypoint="build",
            source_role="environment_generation",
            role_lineage=_lineage(role="environment_generation"),
            sandbox_policy_hash=_policy_hash(),
        )

        scan = scan_python_source(artifact)

        categories = {violation["category"] for violation in scan.violations}
        self.assertEqual(scan.status, "rejected")
        self.assertIn("forbidden_import", categories)
        self.assertIn("filesystem_escape", categories)
        self.assertIn("credential_path", categories)


class SandboxAdmissionAndExecutionTest(unittest.TestCase):
    def test_admission_rejects_unsafe_code_and_writes_sanitized_audit(self) -> None:
        from synthesis.sandbox import (
            GeneratedExecutableArtifact,
            SandboxPolicy,
            admit_generated_executable,
            scan_python_source,
        )

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_secret",
            artifact_kind="tool_handler",
            source_code=(
                "def handler(payload):\n"
                "    return {'token': 'sk-live-1234567890abcdef1234567890abcdef'}\n"
            ),
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        )
        scan = scan_python_source(artifact)

        with tempfile.TemporaryDirectory() as tmpdir:
            admission = admit_generated_executable(
                artifact=artifact,
                scan=scan,
                sandbox_policy=SandboxPolicy.generated_code_fixture(),
                audit_dir=Path(tmpdir),
            )

            self.assertFalse(admission.accepted)
            self.assertEqual(admission.rejection_cause, "unsafe_generated_code")
            audit_text = Path(admission.audit_artifact_path).read_text(encoding="utf-8")
            self.assertIn("raw_secret", audit_text)
            self.assertNotIn("sk-live", audit_text)
            self.assertNotIn("def handler", audit_text)

    def test_admitted_fixture_executes_with_hash_only_stdio(self) -> None:
        from synthesis.sandbox import (
            GeneratedExecutableArtifact,
            SandboxPolicy,
            admit_generated_executable,
            execute_admitted_python,
            scan_python_source,
        )

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_run",
            artifact_kind="verifier",
            source_code=(
                "def verify(payload):\n"
                "    return {'passed': payload['actual'] == payload['expected']}\n"
            ),
            declared_entrypoint="verify",
            source_role="verifier_generation",
            role_lineage=_lineage(role="verifier_generation"),
            sandbox_policy_hash=_policy_hash(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            policy = SandboxPolicy.generated_code_fixture()
            admission = admit_generated_executable(
                artifact=artifact,
                scan=scan_python_source(artifact),
                sandbox_policy=policy,
                audit_dir=Path(tmpdir) / "audit",
            )
            result = execute_admitted_python(
                artifact=artifact,
                admission=admission,
                payload={"actual": "yes", "expected": "yes"},
                artifact_dir=Path(tmpdir) / "run",
                timeout_seconds=2.0,
            )

            self.assertTrue(admission.accepted)
            self.assertEqual(result.status, "succeeded")
            self.assertFalse(result.timeout)
            exported = result.export()
            self.assertEqual(exported["stdout_bytes"], 0)
            self.assertEqual(exported["stderr_bytes"], 0)
            self.assertIn("stdout_hash", exported)
            self.assertNotIn("yes", json.dumps(exported))

    def test_execution_timeout_is_sanitized(self) -> None:
        from synthesis.sandbox import (
            GeneratedExecutableArtifact,
            SandboxAdmissionResult,
            execute_admitted_python,
        )

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_timeout",
            artifact_kind="tool_handler",
            source_code="def handler(payload):\n    while True:\n        pass\n",
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        )
        admission = SandboxAdmissionResult(
            artifact_id=artifact.artifact_id,
            scan_status="passed",
            policy_id="sandbox_generated_code_fixture",
            accepted=True,
            rejection_cause=None,
            sanitized_reason="accepted",
            audit_artifact_path="audit.json",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_admitted_python(
                artifact=artifact,
                admission=admission,
                payload={},
                artifact_dir=Path(tmpdir),
                timeout_seconds=0.1,
            )

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.timeout)
        self.assertEqual(result.sanitized_error_class, "TimeoutExpired")


class SandboxContractTest(unittest.TestCase):
    def test_contracts_reject_malformed_artifact_and_raw_secret_leakage(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_generated_code_scan_result_record,
            validate_generated_executable_artifact_record,
        )
        from synthesis.sandbox import GeneratedExecutableArtifact, scan_python_source

        artifact = GeneratedExecutableArtifact.from_source(
            artifact_id="bad id",
            artifact_kind="tool_handler",
            source_code="def handler(payload):\n    return {}\n",
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        ).export()

        with self.assertRaisesRegex(ContractValidationError, "artifact_id"):
            validate_generated_executable_artifact_record(artifact)

        safe = GeneratedExecutableArtifact.from_source(
            artifact_id="generated_exec_contract",
            artifact_kind="tool_handler",
            source_code="def handler(payload):\n    return {}\n",
            declared_entrypoint="handler",
            source_role="tool_generation",
            role_lineage=_lineage(),
            sandbox_policy_hash=_policy_hash(),
        )
        scan = scan_python_source(safe).export()
        scan["redaction_summary"]["leaked_secret"] = "sk-live-1234567890abcdef1234567890abcdef"
        with self.assertRaisesRegex(ContractValidationError, "raw secret"):
            validate_generated_code_scan_result_record(scan)


def _lineage(role: str = "tool_generation") -> dict[str, object]:
    return {
        "role": role,
        "role_version": f"role_{role}_v1",
        "output_type": "tool_proposal",
        "provider_host": "local",
        "model": "fixture",
        "config_hash": "fixture-config",
    }


def _policy_hash() -> str:
    return "sha256:" + "1" * 64


if __name__ == "__main__":
    unittest.main()
