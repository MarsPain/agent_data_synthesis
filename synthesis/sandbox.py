from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthesis.contracts import (
    validate_generated_code_scan_result_record,
    validate_generated_executable_artifact_record,
    validate_sandbox_admission_result_record,
    validate_sandbox_execution_result_record,
)


SCANNER_VERSION = "python_static_sandbox_scanner_v1"
FORBIDDEN_IMPORT_ROOTS = {
    "builtins",
    "ftplib",
    "http",
    "importlib",
    "os",
    "pathlib",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}
FORBIDDEN_CALLS = {
    "__import__",
    "builtins.__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "locals",
    "open",
}
SHELL_PATTERNS = {"pip", "uv", "npm", "curl", "wget"}
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|api[_-]?key\s*[:=]|authorization\s*:)",
    re.IGNORECASE,
)
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SandboxPolicy:
    policy_id: str
    filesystem_isolation: str
    generated_code_allowed: bool
    secret_redaction: bool

    @classmethod
    def generated_code_fixture(cls) -> "SandboxPolicy":
        return cls(
            policy_id="sandbox_generated_code_fixture",
            filesystem_isolation="artifact_subdir",
            generated_code_allowed=True,
            secret_redaction=True,
        )

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "sandbox_policy_v1",
            "policy_id": self.policy_id,
            "filesystem_isolation": self.filesystem_isolation,
            "generated_code_allowed": self.generated_code_allowed,
            "secret_redaction": self.secret_redaction,
        }


@dataclass(frozen=True)
class GeneratedExecutableArtifact:
    artifact_id: str
    artifact_kind: str
    language: str
    source_hash: str
    declared_entrypoint: str
    source_role: str
    role_lineage: dict[str, object]
    created_at: str
    sandbox_policy_hash: str
    source_code: str

    @classmethod
    def from_source(
        cls,
        *,
        artifact_id: str,
        artifact_kind: str,
        source_code: str,
        declared_entrypoint: str,
        source_role: str,
        role_lineage: dict[str, object],
        sandbox_policy_hash: str,
        created_at: str = "1970-01-01T00:00:00Z",
    ) -> "GeneratedExecutableArtifact":
        return cls(
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            language="python",
            source_hash=_content_hash(source_code),
            declared_entrypoint=declared_entrypoint,
            source_role=source_role,
            role_lineage=dict(role_lineage),
            created_at=created_at,
            sandbox_policy_hash=sandbox_policy_hash,
            source_code=source_code,
        )

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "generated_executable_artifact_v1",
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "language": self.language,
            "source_hash": self.source_hash,
            "declared_entrypoint": self.declared_entrypoint,
            "source_role": self.source_role,
            "role_lineage": dict(self.role_lineage),
            "created_at": self.created_at,
            "sandbox_policy_hash": self.sandbox_policy_hash,
        }


@dataclass(frozen=True)
class GeneratedCodeScanResult:
    status: str
    violations: list[dict[str, object]]
    forbidden_symbols: list[str]
    source_hash: str
    scanner_version: str
    redaction_summary: dict[str, object]

    def export(self) -> dict[str, object]:
        record = {
            "schema_version": "generated_code_scan_result_v1",
            "status": self.status,
            "violations": [dict(violation) for violation in self.violations],
            "forbidden_symbols": list(self.forbidden_symbols),
            "source_hash": self.source_hash,
            "scanner_version": self.scanner_version,
            "redaction_summary": dict(self.redaction_summary),
        }
        validate_generated_code_scan_result_record(record)
        return record


@dataclass(frozen=True)
class SandboxAdmissionResult:
    artifact_id: str
    scan_status: str
    policy_id: str
    accepted: bool
    rejection_cause: str | None
    sanitized_reason: str
    audit_artifact_path: str

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "schema_version": "sandbox_admission_result_v1",
            "artifact_id": self.artifact_id,
            "scan_status": self.scan_status,
            "policy_id": self.policy_id,
            "accepted": self.accepted,
            "rejection_cause": self.rejection_cause,
            "sanitized_reason": self.sanitized_reason,
            "audit_artifact_path": Path(self.audit_artifact_path).name,
        }
        validate_sandbox_admission_result_record(record)
        return record


@dataclass(frozen=True)
class SandboxExecutionResult:
    artifact_id: str
    status: str
    timeout: bool
    exit_class: str
    stdout_hash: str
    stdout_bytes: int
    stderr_hash: str
    stderr_bytes: int
    duration_ms: int
    sanitized_error_class: str | None

    def export(self) -> dict[str, object]:
        record = {
            "schema_version": "sandbox_execution_result_v1",
            "artifact_id": self.artifact_id,
            "status": self.status,
            "timeout": self.timeout,
            "exit_class": self.exit_class,
            "stdout_hash": self.stdout_hash,
            "stdout_bytes": self.stdout_bytes,
            "stderr_hash": self.stderr_hash,
            "stderr_bytes": self.stderr_bytes,
            "duration_ms": self.duration_ms,
            "sanitized_error_class": self.sanitized_error_class,
        }
        validate_sandbox_execution_result_record(record)
        return record


def sandbox_policy_hash(policy: SandboxPolicy) -> str:
    canonical = json.dumps(policy.export(), sort_keys=True, separators=(",", ":"))
    return _content_hash(canonical)


def scan_python_source(artifact: GeneratedExecutableArtifact) -> GeneratedCodeScanResult:
    violations: list[dict[str, object]] = []
    forbidden_symbols: set[str] = set()
    try:
        tree = ast.parse(artifact.source_code)
    except SyntaxError as exc:
        violations.append(_violation("syntax_error", exc.lineno or 0, "python_syntax"))
        return _scan_result(artifact, violations, forbidden_symbols)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import(alias.name, getattr(node, "lineno", 0), violations, forbidden_symbols)
        elif isinstance(node, ast.ImportFrom):
            _check_import(node.module or "", getattr(node, "lineno", 0), violations, forbidden_symbols)
        elif isinstance(node, ast.Call):
            target = _call_target(node.func)
            if target in FORBIDDEN_CALLS:
                forbidden_symbols.add(target)
                category = "dynamic_evaluation" if target in {"eval", "exec", "compile"} else "forbidden_call"
                violations.append(_violation(category, getattr(node, "lineno", 0), target))
            for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    _check_string(argument.value, getattr(argument, "lineno", 0), violations, forbidden_symbols)
        elif isinstance(node, ast.Attribute):
            target = _attribute_target(node)
            if target in {"os.environ", "sys.path"}:
                forbidden_symbols.add(target)
                violations.append(_violation("forbidden_attribute", getattr(node, "lineno", 0), target))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            _check_string(node.value, getattr(node, "lineno", 0), violations, forbidden_symbols)

    return _scan_result(artifact, violations, forbidden_symbols)


def admit_generated_executable(
    *,
    artifact: GeneratedExecutableArtifact,
    scan: GeneratedCodeScanResult,
    sandbox_policy: SandboxPolicy,
    audit_dir: Path,
) -> SandboxAdmissionResult:
    audit_dir.mkdir(parents=True, exist_ok=True)
    policy_errors = _policy_errors(sandbox_policy)
    accepted = scan.status == "passed" and not policy_errors
    rejection_cause = None if accepted else "unsafe_generated_code"
    reason = "accepted" if accepted else _sanitized_reason(scan, policy_errors)
    audit_path = audit_dir / f"{artifact.artifact_id}.sandbox_audit.json"
    admission = SandboxAdmissionResult(
        artifact_id=artifact.artifact_id,
        scan_status=scan.status,
        policy_id=sandbox_policy.policy_id,
        accepted=accepted,
        rejection_cause=rejection_cause,
        sanitized_reason=reason,
        audit_artifact_path=str(audit_path),
    )
    audit = build_sandbox_audit_record(
        artifact=artifact,
        scan=scan,
        admission=admission,
        execution=None,
    )
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return admission


def execute_admitted_python(
    *,
    artifact: GeneratedExecutableArtifact,
    admission: SandboxAdmissionResult,
    payload: dict[str, object],
    artifact_dir: Path,
    timeout_seconds: float,
) -> SandboxExecutionResult:
    if not admission.accepted:
        raise ValueError("artifact must be admitted before execution")
    started = time.monotonic()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=artifact_dir) as run_dir_raw:
        run_dir = Path(run_dir_raw)
        generated_path = run_dir / "generated_artifact.py"
        wrapper_path = run_dir / "sandbox_wrapper.py"
        input_path = run_dir / "payload.json"
        result_path = run_dir / "result.json"
        generated_path.write_text(artifact.source_code, encoding="utf-8")
        input_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        wrapper_path.write_text(_wrapper_source(artifact.declared_entrypoint), encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", str(wrapper_path)],
                cwd=run_dir,
                env={"PYTHONIOENCODING": "utf-8"},
                input="",
                capture_output=True,
                text=False,
                timeout=timeout_seconds,
                preexec_fn=_resource_limiter(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return _execution_result(
                artifact_id=artifact.artifact_id,
                status="failed",
                timeout=True,
                exit_class="timeout",
                stdout=exc.stdout or b"",
                stderr=exc.stderr or b"",
                started=started,
                error_class="TimeoutExpired",
            )
        error_class: str | None = None
        status = "succeeded"
        exit_class = "zero"
        if completed.returncode != 0:
            status = "failed"
            exit_class = "nonzero"
            error_class = _read_error_class(result_path) or "ProcessFailed"
        elif not result_path.exists():
            status = "failed"
            exit_class = "wrapper_error"
            error_class = "MissingResult"
        else:
            try:
                json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                status = "failed"
                exit_class = "non_json"
                error_class = "NonJsonResult"
        return _execution_result(
            artifact_id=artifact.artifact_id,
            status=status,
            timeout=False,
            exit_class=exit_class,
            stdout=completed.stdout,
            stderr=completed.stderr,
            started=started,
            error_class=error_class,
        )


def build_sandbox_audit_record(
    *,
    artifact: GeneratedExecutableArtifact,
    scan: GeneratedCodeScanResult,
    admission: SandboxAdmissionResult,
    execution: SandboxExecutionResult | None,
) -> dict[str, object]:
    return {
        "schema_version": "sandbox_audit_v1",
        "artifact": artifact.export(),
        "scan": scan.export(),
        "admission": admission.export(),
        "execution": execution.export() if execution is not None else None,
    }


def build_deterministic_sandbox_fixture(output_dir: Path) -> list[dict[str, object]]:
    policy = SandboxPolicy.generated_code_fixture()
    policy_hash = sandbox_policy_hash(policy)
    audit_dir = output_dir / "sandbox_audit"
    safe_artifact = GeneratedExecutableArtifact.from_source(
        artifact_id="generated_exec_fixture_safe",
        artifact_kind="verifier",
        source_code="def verify(payload):\n    return {'passed': payload['actual'] == payload['expected']}\n",
        declared_entrypoint="verify",
        source_role="verifier_generation",
        role_lineage=_fixture_lineage("verifier_generation", "verifier_definition"),
        sandbox_policy_hash=policy_hash,
    )
    unsafe_artifact = GeneratedExecutableArtifact.from_source(
        artifact_id="generated_exec_fixture_unsafe",
        artifact_kind="tool_handler",
        source_code=(
            "import os\n"
            "def handler(payload):\n"
            "    return {'token': 'sk-live-1234567890abcdef1234567890abcdef'}\n"
        ),
        declared_entrypoint="handler",
        source_role="tool_generation",
        role_lineage=_fixture_lineage("tool_generation", "tool_proposal"),
        sandbox_policy_hash=policy_hash,
    )

    records: list[dict[str, object]] = []
    safe_scan = scan_python_source(safe_artifact)
    safe_admission = admit_generated_executable(
        artifact=safe_artifact,
        scan=safe_scan,
        sandbox_policy=policy,
        audit_dir=audit_dir,
    )
    safe_execution = execute_admitted_python(
        artifact=safe_artifact,
        admission=safe_admission,
        payload={"actual": "alice.zhang@example.test", "expected": "alice.zhang@example.test"},
        artifact_dir=output_dir / "sandbox_run",
        timeout_seconds=2.0,
    )
    records.append(
        build_sandbox_audit_record(
            artifact=safe_artifact,
            scan=safe_scan,
            admission=safe_admission,
            execution=safe_execution,
        )
    )

    unsafe_scan = scan_python_source(unsafe_artifact)
    unsafe_admission = admit_generated_executable(
        artifact=unsafe_artifact,
        scan=unsafe_scan,
        sandbox_policy=policy,
        audit_dir=audit_dir,
    )
    records.append(
        build_sandbox_audit_record(
            artifact=unsafe_artifact,
            scan=unsafe_scan,
            admission=unsafe_admission,
            execution=None,
        )
    )
    return records


def _check_import(
    module: str,
    line_number: int,
    violations: list[dict[str, object]],
    forbidden_symbols: set[str],
) -> None:
    root = module.split(".", 1)[0]
    if root in FORBIDDEN_IMPORT_ROOTS:
        forbidden_symbols.add(root)
        violations.append(_violation("forbidden_import", line_number, root))


def _check_string(
    value: str,
    line_number: int,
    violations: list[dict[str, object]],
    forbidden_symbols: set[str],
) -> None:
    lowered = value.lower()
    if SECRET_RE.search(value):
        violations.append(_violation("raw_secret", line_number, "redacted_token"))
    if value.startswith("/") or value.startswith("~") or "../" in value or value == "..":
        violations.append(_violation("filesystem_escape", line_number, "path_literal"))
    if "/.ssh/" in lowered or ".aws/credentials" in lowered or "id_rsa" in lowered:
        violations.append(_violation("credential_path", line_number, "credential_path"))
    for pattern in SHELL_PATTERNS:
        if re.search(rf"\b{re.escape(pattern)}\b", lowered):
            forbidden_symbols.add(pattern)
            violations.append(_violation("package_or_shell_command", line_number, pattern))


def _scan_result(
    artifact: GeneratedExecutableArtifact,
    violations: list[dict[str, object]],
    forbidden_symbols: set[str],
) -> GeneratedCodeScanResult:
    status = "rejected" if violations else "passed"
    return GeneratedCodeScanResult(
        status=status,
        violations=violations,
        forbidden_symbols=sorted(forbidden_symbols),
        source_hash=artifact.source_hash,
        scanner_version=SCANNER_VERSION,
        redaction_summary={
            "raw_source_exported": False,
            "redacted_token_count": sum(
                1 for violation in violations if violation.get("category") == "raw_secret"
            ),
        },
    )


def _violation(category: str, line_number: int, symbol: str) -> dict[str, object]:
    return {
        "category": category,
        "line_number": max(line_number, 0),
        "symbol": symbol,
    }


def _call_target(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_target(node)
    return "unknown"


def _attribute_target(node: ast.Attribute) -> str:
    parts = [node.attr]
    current = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _policy_errors(policy: SandboxPolicy) -> list[str]:
    errors: list[str] = []
    if not policy.generated_code_allowed:
        errors.append("generated_code_not_allowed")
    if policy.filesystem_isolation != "artifact_subdir":
        errors.append("filesystem_isolation_required")
    if not policy.secret_redaction:
        errors.append("redaction_required")
    return errors


def _sanitized_reason(scan: GeneratedCodeScanResult, policy_errors: list[str]) -> str:
    categories = sorted({str(violation.get("category")) for violation in scan.violations})
    reasons = [*policy_errors, *categories]
    return "rejected:" + ",".join(reasons or ["unknown"])


def _wrapper_source(entrypoint: str) -> str:
    return textwrap.dedent(
        f"""
        import importlib.util
        import json
        import traceback
        from pathlib import Path

        run_dir = Path.cwd()
        result_path = run_dir / "result.json"
        try:
            spec = importlib.util.spec_from_file_location("generated_artifact", run_dir / "generated_artifact.py")
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            payload = json.loads((run_dir / "payload.json").read_text(encoding="utf-8"))
            result = getattr(module, {entrypoint!r})(payload)
            json.dumps(result, sort_keys=True)
            result_path.write_text(json.dumps({{"ok": True, "result": result}}, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            result_path.write_text(
                json.dumps({{"ok": False, "error_class": type(exc).__name__}}, sort_keys=True),
                encoding="utf-8",
            )
            raise SystemExit(1)
        """
    ).lstrip()


def _resource_limiter() -> Any:
    if os.name != "posix":
        return None

    def limit() -> None:
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
            memory = 128 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        except Exception:
            return

    return limit


def _execution_result(
    *,
    artifact_id: str,
    status: str,
    timeout: bool,
    exit_class: str,
    stdout: bytes,
    stderr: bytes,
    started: float,
    error_class: str | None,
) -> SandboxExecutionResult:
    return SandboxExecutionResult(
        artifact_id=artifact_id,
        status=status,
        timeout=timeout,
        exit_class=exit_class,
        stdout_hash=_content_hash(stdout),
        stdout_bytes=len(stdout),
        stderr_hash=_content_hash(stderr),
        stderr_bytes=len(stderr),
        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        sanitized_error_class=error_class,
    )


def _read_error_class(result_path: Path) -> str | None:
    if not result_path.exists():
        return None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    error_class = result.get("error_class")
    return str(error_class) if error_class else None


def _fixture_lineage(role: str, output_type: str) -> dict[str, object]:
    return {
        "role": role,
        "role_version": f"role_{role}_v0",
        "output_type": output_type,
        "provider_host": "local",
        "model": "fixture",
        "config_hash": "sandbox-fixture-v1",
    }


def _content_hash(content: str | bytes) -> str:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()
