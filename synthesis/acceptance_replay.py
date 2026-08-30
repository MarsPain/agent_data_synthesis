"""Pack-neutral acceptance and replay contracts.

The acceptance boundary is deliberately smaller than a Domain Pack.  A pack
adapter supplies the planned run and owns all domain semantics; this module
only checks the shared identity envelope and later coordinates the common
evidence lifecycle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Protocol, runtime_checkable


_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONFIG_HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,239}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_.:-]{1,127}$")

MAX_GENERATOR_RETRIES = 3
PROVIDER_PARSER_VERSION = "domain_generation_parser_v1"
SANITIZED_EVIDENCE_POLICY_VERSION = "sanitized_provider_evidence_v1"

_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "headers",
    "password",
    "prompt",
    "provider_payload",
    "provider_prompt",
    "raw_payload",
    "raw_prompt",
    "raw_source",
    "secret",
    "source_payload",
    "token",
}
_UNSAFE_STRING_PATTERNS = (
    re.compile(r"authorization\s*:", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/@\s]+:[^/@\s]+@", re.IGNORECASE),
    re.compile(r"(?:^|\s)/(?:Users|home|private|var|tmp)/"),
    re.compile(r"[A-Za-z]:\\"),
)
_PROVIDER_RECORD_KEYS = frozenset(
    {
        "candidate_id",
        "instruction",
        "task_type",
        "difficulty",
        "required_capabilities",
        "required_tools",
        "primary_tool",
        "primary_arguments",
        "final_answer_contains",
        "expected_state",
    }
)
_RUN_BINDING_KEYS = frozenset(
    {
        "profile_id",
        "dataset_version",
        "seed_id",
        "seed_domain",
        "plan_id",
        "plan_hash",
        "coverage_plan_id",
        "coverage_plan_hash",
        "source_policy_hash",
    }
)
ACCEPTANCE_RUN_BINDING_KEYS = _RUN_BINDING_KEYS


class AcceptanceReplayError(ValueError):
    """A bounded failure at the pack-neutral acceptance boundary."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _require_hash(value: object, reason_code: str = "acceptance_binding_malformed") -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise AcceptanceReplayError(reason_code)
    return value


@dataclass(frozen=True)
class AcceptanceReplayContract:
    """Versioned, domain-independent evidence settings for one acceptance."""

    acceptance_schema_version: str
    provider_evidence_schema_version: str
    evidence_class: str
    freeze_policy: str
    provider_parser_version: str = PROVIDER_PARSER_VERSION
    replay_result_schema_version: str = "acceptance_replay_result_v1"
    provider_identity_keys: frozenset[str] = frozenset(
        {
            "provider_id",
            "provider_version",
            "provider_host",
            "model",
            "config_hash",
            "parser_version",
        }
    )
    judge_identity_keys: frozenset[str] = frozenset(
        {
            "provider",
            "provider_host",
            "model",
            "config_hash",
            "role",
            "role_version",
        }
    )
    expected_provider_id: str | None = None
    expected_provider_version: str | None = None
    expected_judge_provider: str | None = None
    expected_judge_role: str | None = None
    expected_judge_role_version: str | None = None
    provider_attempt_id_prefix: str = "provider_attempt"
    mutation_judge_attempt_id_prefix: str = "mutation_judge_attempt"
    preflight_failure_reason: str = (
        "acceptance_mutation_judge_preflight_failed"
    )
    pipeline_failure_reason: str = "acceptance_pipeline_failed"

    def validate_identities(
        self,
        provider: Mapping[str, object],
        judge: Mapping[str, object],
    ) -> None:
        if set(provider) != self.provider_identity_keys or set(judge) != self.judge_identity_keys:
            raise AcceptanceReplayError("acceptance_identity_malformed")
        for identity in (provider, judge):
            if any(
                not isinstance(identity.get(key), str) or not identity.get(key)
                for key in identity
                if key != "config_hash"
            ) or _CONFIG_HASH_RE.fullmatch(str(identity.get("config_hash", ""))) is None:
                raise AcceptanceReplayError("acceptance_identity_malformed")
            _sanitize_json_value(identity)
        if provider.get("model") == judge.get("model"):
            raise AcceptanceReplayError("mutation_judge_identity_not_independent")
        expected = (
            ("provider_id", self.expected_provider_id, provider),
            ("provider_version", self.expected_provider_version, provider),
            ("provider", self.expected_judge_provider, judge),
            ("role", self.expected_judge_role, judge),
            ("role_version", self.expected_judge_role_version, judge),
        )
        for key, expected_value, identity in expected:
            if expected_value is not None and identity.get(key) != expected_value:
                raise AcceptanceReplayError("acceptance_identity_mismatch")
        if provider.get("parser_version") != self.provider_parser_version:
            raise AcceptanceReplayError("acceptance_identity_mismatch")


DEFAULT_ACCEPTANCE_REPLAY_CONTRACT = AcceptanceReplayContract(
    acceptance_schema_version="acceptance_v1",
    provider_evidence_schema_version="provider_evidence_v1",
    evidence_class="real_live",
    freeze_policy=SANITIZED_EVIDENCE_POLICY_VERSION,
)


@dataclass(frozen=True)
class AcceptancePreparation:
    """Minimum immutable inputs shared by acceptance and replay consumers."""

    profile_record: Mapping[str, object]
    plan: object
    coverage_plan: object
    source_policy_hash: str
    run_binding: Mapping[str, object]

    def validate(self) -> None:
        if not isinstance(self.profile_record, Mapping):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        if not isinstance(self.run_binding, Mapping):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        _validate_safe_mapping(self.profile_record, "acceptance_binding_malformed")
        _validate_safe_mapping(self.run_binding, "acceptance_binding_malformed")
        if set(self.run_binding) != _RUN_BINDING_KEYS:
            raise AcceptanceReplayError("acceptance_binding_malformed")

        plan_id = _field(self.plan, "plan_id")
        plan_hash = _field(self.plan, "plan_hash")
        coverage_id = _field(self.coverage_plan, "plan_id")
        coverage_hash = _field(self.coverage_plan, "plan_hash")
        attempt_ceiling = _field(self.coverage_plan, "attempt_ceiling")
        if (
            not isinstance(plan_id, str)
            or not plan_id
            or not isinstance(coverage_id, str)
            or not coverage_id
            or not isinstance(attempt_ceiling, int)
            or isinstance(attempt_ceiling, bool)
            or attempt_ceiling <= 0
        ):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        _require_hash(plan_hash)
        _require_hash(coverage_hash)
        _require_hash(self.source_policy_hash)

        seed = self.profile_record.get("seed")
        profile_id = self.profile_record.get("profile_id")
        dataset_version = self.profile_record.get("dataset_version")
        seed_id = _field(seed, "seed_id")
        seed_domain = _field(seed, "domain")
        expected = {
            "profile_id": profile_id,
            "dataset_version": dataset_version,
            "seed_id": seed_id,
            "seed_domain": seed_domain,
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "coverage_plan_id": coverage_id,
            "coverage_plan_hash": coverage_hash,
            "source_policy_hash": self.source_policy_hash,
        }
        if any(not isinstance(value, str) or not value for value in expected.values()):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        if dict(self.run_binding) != expected:
            raise AcceptanceReplayError("acceptance_binding_mismatch")


@dataclass(frozen=True)
class AcceptancePipelineResult:
    """The framework-visible part of a domain adapter's pipeline result."""

    result: object
    accepted_count: int
    rejections_path: Path | None = None

    def validate(self) -> None:
        if (
            not isinstance(self.accepted_count, int)
            or isinstance(self.accepted_count, bool)
            or self.accepted_count < 0
            or (
                self.rejections_path is not None
                and not isinstance(self.rejections_path, Path)
            )
        ):
            raise AcceptanceReplayError("acceptance_pipeline_result_malformed")


@dataclass(frozen=True)
class AcceptanceReleaseEvidence:
    """Domain-produced release artifacts consumed by the shared harness."""

    replay_report_path: Path
    evaluation_report_path: Path
    profile_decision_path: Path
    dataset_release_report_path: Path
    release_quality_audit_path: Path
    release_pack_path: Path
    release_pack_verification: Mapping[str, object]
    qualification: Mapping[str, object]
    release_pack_hash: str


@dataclass(frozen=True)
class AcceptanceRunResult:
    acceptance_dir: Path
    proof_path: Path
    provider_evidence_path: Path
    replay: Mapping[str, object]
    qualification: Mapping[str, object]


@runtime_checkable
class AcceptanceAuthorization(Protocol):
    approved: bool
    attempt_budget: int
    generator_retry_limit: int

    def validate(
        self,
        *,
        profile: Mapping[str, object],
        plan_attempt_ceiling: int,
    ) -> None: ...

    def to_record(self) -> dict[str, object]: ...


@runtime_checkable
class AcceptanceEvidenceRecorder(Protocol):
    @property
    def attempts(self) -> Sequence[Mapping[str, object]]: ...

    def set_mutation_judge_usage(self, usage: Mapping[str, object]) -> None: ...

    def freeze(
        self,
        output_path: Path,
        *,
        qualification: Mapping[str, object],
        release_pack_verification: Mapping[str, object],
        release_pack_hash: str,
        run_binding: Mapping[str, object] | None = None,
    ) -> dict[str, object]: ...


@runtime_checkable
class AcceptanceUsageObserver(Protocol):
    def to_record(self) -> dict[str, object]: ...

    def to_failure_record(self) -> dict[str, object]: ...


class AcceptanceReplayAdapter(Protocol):
    """Domain-owned hooks for the neutral acceptance/replay sequence.

    Adapter methods receive a planned run or sanitized evidence, never a raw
    runtime session.  Plan selection, capability floors, assessment, and
    tracer/proof semantics stay behind this boundary.
    """

    evidence_contract: AcceptanceReplayContract

    def prepare(self, *, profile: object, output_dir: Path) -> AcceptancePreparation: ...

    def validate_authorization(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        authorization: AcceptanceAuthorization,
        max_generator_retries: int,
    ) -> None: ...

    def resolve_generator_config(self, supplied: object | None) -> object: ...

    def validate_generator_config(
        self,
        *,
        profile: object,
        authorization: AcceptanceAuthorization,
        config: object,
    ) -> None: ...

    def generator_identity(self, config: object) -> Mapping[str, object]: ...

    def mutation_judge_identity(
        self,
        *,
        profile: object,
        config: object,
    ) -> Mapping[str, object]: ...

    def create_recorder(
        self,
        *,
        authorization: AcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> AcceptanceEvidenceRecorder: ...

    def create_usage_observer(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> AcceptanceUsageObserver: ...

    def preflight_mutation_judge(
        self,
        *,
        profile: object,
        config: object,
        http_client: object | None,
        observer: AcceptanceUsageObserver,
    ) -> Mapping[str, object]: ...

    def build_provider(
        self,
        *,
        config: object,
        authorization: AcceptanceAuthorization,
        recorder: AcceptanceEvidenceRecorder,
        http_client: object | None,
        max_generator_retries: int,
    ) -> object: ...

    def run_pipeline(
        self,
        *,
        output_dir: Path,
        profile: object,
        provider: object,
        recorder: AcceptanceEvidenceRecorder,
        observer: AcceptanceUsageObserver,
        mutation_judge_http_client: object | None,
        config: object,
    ) -> AcceptancePipelineResult: ...

    def validate_pipeline(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        pipeline: AcceptancePipelineResult,
    ) -> None: ...

    def mutation_judge_attempt_ceiling(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> int: ...

    def write_release_evidence(
        self,
        *,
        output_dir: Path,
        profile: object,
        pipeline: AcceptancePipelineResult,
        runtime_seconds: float,
    ) -> AcceptanceReleaseEvidence: ...

    def bind_sample_assignments(
        self,
        *,
        recorder: AcceptanceEvidenceRecorder,
        pipeline: AcceptancePipelineResult,
    ) -> None: ...

    def replay(
        self,
        *,
        evidence: Mapping[str, object],
        preparation: AcceptancePreparation,
    ) -> int | Mapping[str, object]: ...

    def build_proof(self, *, proof_root: Path, acceptance_dir: Path) -> Path: ...

    def verify_proof(self, proof_path: Path) -> Mapping[str, object]: ...

    def provider_evidence_path(
        self,
        *,
        proof_path: Path,
        acceptance_dir: Path,
    ) -> Path: ...

    def write_failure(
        self,
        output_dir: Path,
        *,
        reason_code: str,
        phase: str,
        authorization: AcceptanceAuthorization,
        preparation: AcceptancePreparation,
        recorder: AcceptanceEvidenceRecorder,
        observer: AcceptanceUsageObserver,
        mutation_judge_preflight: Mapping[str, object] | None,
        rejections_path: Path | None = None,
        qualification: Mapping[str, object] | None = None,
    ) -> Path: ...


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AcceptanceReplayError("provider_response_not_sanitizable") from exc


def hash_value(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sanitize_json_value(value: object, *, depth: int = 0) -> object:
    if depth > 12:
        raise AcceptanceReplayError("provider_response_not_sanitizable")
    if isinstance(value, str):
        if len(value) > 4096 or any(pattern.search(value) for pattern in _UNSAFE_STRING_PATTERNS):
            raise AcceptanceReplayError("provider_response_not_sanitizable")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            raise AcceptanceReplayError("provider_response_not_sanitizable")
        return value
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_KEYS:
                raise AcceptanceReplayError("provider_response_not_sanitizable")
            sanitized[key] = _sanitize_json_value(child, depth=depth + 1)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 100:
            raise AcceptanceReplayError("provider_response_not_sanitizable")
        return [_sanitize_json_value(child, depth=depth + 1) for child in value]
    raise AcceptanceReplayError("provider_response_not_sanitizable")


def sanitize_provider_response(response: object) -> dict[str, object]:
    """Keep only the bounded task-contract response accepted by the parser."""

    if not isinstance(response, Mapping) or set(response) != {"task_contracts"}:
        raise AcceptanceReplayError("provider_response_not_sanitizable")
    task_contracts = response.get("task_contracts")
    if not isinstance(task_contracts, list) or len(task_contracts) > 5:
        raise AcceptanceReplayError("provider_response_not_sanitizable")
    sanitized_contracts: list[dict[str, object]] = []
    for raw_contract in task_contracts:
        if not isinstance(raw_contract, Mapping) or set(raw_contract) != _PROVIDER_RECORD_KEYS:
            raise AcceptanceReplayError("provider_response_not_sanitizable")
        sanitized = _sanitize_json_value(raw_contract)
        if not isinstance(sanitized, Mapping):
            raise AcceptanceReplayError("provider_response_not_sanitizable")
        sanitized_contracts.append(dict(sanitized))
    result = {"task_contracts": sanitized_contracts}
    if len(_canonical_bytes(result)) > 256 * 1024:
        raise AcceptanceReplayError("provider_response_not_sanitizable")
    return result


def bounded_usage(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    usage: dict[str, int] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ):
        raw = value.get(key)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            usage[key] = raw
    return usage


def sum_usage(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for record in records:
        usage = record.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for key, value in bounded_usage(usage).items():
            totals[key] = totals.get(key, 0) + value
    return dict(sorted(totals.items()))


def bounded_retry_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def bounded_reason(value: object) -> str:
    if isinstance(value, str) and _REASON_RE.fullmatch(value):
        return value
    return "llm_provider_error"


def bounded_judge_failure_class(error: BaseException) -> str:
    """Classify provider failure without retaining its message or payload."""

    error_class = getattr(error, "error_class", type(error).__name__)
    if error_class in {
        "ConnectTimeout",
        "PoolTimeout",
        "ReadTimeout",
        "TimeoutException",
        "WriteTimeout",
    }:
        return "timeout"
    if error_class == "HTTPStatusError":
        return "http_status"
    if error_class in {
        "ConnectError",
        "NetworkError",
        "ProtocolError",
        "RemoteProtocolError",
        "TransportError",
    }:
        return "transport"
    if error_class in {"JSONDecodeError", "KeyError", "TypeError", "ValueError"}:
        return "response_schema"
    if error_class == "LLMConfigurationError":
        return "configuration"
    return "provider_error"


def _physical_call_ceiling(authorization: object) -> int:
    retry_limit = _field(authorization, "generator_retry_limit")
    attempt_budget = _field(authorization, "attempt_budget")
    if (
        not isinstance(retry_limit, int)
        or isinstance(retry_limit, bool)
        or retry_limit not in range(MAX_GENERATOR_RETRIES + 1)
        or not isinstance(attempt_budget, int)
        or isinstance(attempt_budget, bool)
        or attempt_budget <= 0
    ):
        raise AcceptanceReplayError("generator_retry_budget_invalid")
    return attempt_budget * (retry_limit + 1)


class SanitizedProviderEvidenceRecorder:
    """Capture bounded provider attempts and freeze them after qualification."""

    def __init__(
        self,
        *,
        authorization: AcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
        contract: AcceptanceReplayContract = DEFAULT_ACCEPTANCE_REPLAY_CONTRACT,
    ) -> None:
        self.authorization = authorization
        self.contract = contract
        safe_provider_identity = _sanitize_json_value(provider_identity)
        safe_judge_identity = _sanitize_json_value(mutation_judge_identity)
        if not isinstance(safe_provider_identity, Mapping) or not isinstance(
            safe_judge_identity, Mapping
        ):
            raise AcceptanceReplayError("acceptance_identity_malformed")
        self.provider_identity = dict(safe_provider_identity)
        self.mutation_judge_identity = dict(safe_judge_identity)
        self._attempts: list[dict[str, object]] = []
        self._pending_assignments: dict[str, dict[str, object]] = {}
        self._pending_assignment_lineages: dict[str, dict[str, object]] = {}
        self._mutation_judge_usage: dict[str, object] = {}
        self._frozen = False

    @property
    def attempts(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self._attempts)

    def bind_assignment(
        self,
        *,
        request_hash: str,
        assignment: Mapping[str, object],
        assignment_lineage: Mapping[str, object] | None = None,
    ) -> None:
        if self._frozen:
            raise AcceptanceReplayError("acceptance_evidence_already_frozen")
        _require_hash(request_hash)
        if not isinstance(assignment, Mapping) or not isinstance(
            assignment.get("assignment_id"), str
        ):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        safe_assignment = _sanitize_json_value(assignment)
        safe_lineage = _sanitize_json_value(
            assignment_lineage if assignment_lineage is not None else assignment
        )
        if not isinstance(safe_assignment, Mapping) or not isinstance(
            safe_lineage, Mapping
        ):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        self._pending_assignments[request_hash] = dict(safe_assignment)
        self._pending_assignment_lineages[request_hash] = dict(safe_lineage)

    def bind_sample_assignments(
        self,
        assignments_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        for record in self._attempts:
            assignment_id = record.get("assignment_id")
            assignment = assignments_by_id.get(str(assignment_id))
            current_assignment = record.get("assignment")
            if assignment is not None and (
                not isinstance(current_assignment, Mapping)
                or "task_type" not in current_assignment
            ):
                safe_assignment = _sanitize_json_value(assignment)
                if isinstance(safe_assignment, Mapping):
                    record["assignment"] = dict(safe_assignment)

    def set_mutation_judge_usage(self, usage: Mapping[str, object]) -> None:
        attempt_ceiling = usage.get("attempt_ceiling")
        if (
            not isinstance(attempt_ceiling, int)
            or isinstance(attempt_ceiling, bool)
            or attempt_ceiling <= 0
        ):
            raise AcceptanceReplayError("authorization_budget_invalid")
        attempts = usage.get("attempts")
        if (
            not isinstance(attempts, int)
            or isinstance(attempts, bool)
            or attempts < 0
            or attempts > attempt_ceiling
        ):
            raise AcceptanceReplayError("live_usage_malformed")
        outcomes = usage.get("outcomes")
        if not isinstance(outcomes, Mapping):
            raise AcceptanceReplayError("live_usage_malformed")
        safe_outcomes: dict[str, int] = {}
        for outcome, count in outcomes.items():
            if (
                outcome not in {"provider_error", "response_received"}
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
            ):
                raise AcceptanceReplayError("live_usage_malformed")
            safe_outcomes[str(outcome)] = count
        if sum(safe_outcomes.values()) != attempts:
            raise AcceptanceReplayError("live_usage_malformed")
        self._mutation_judge_usage = {
            "attempts": attempts,
            "attempt_ceiling": attempt_ceiling,
            "tokens": bounded_usage(usage.get("tokens")),
            "outcomes": safe_outcomes,
        }

    def assignment_for_request(self, request_hash: str) -> dict[str, object]:
        assignment = self._pending_assignments.pop(request_hash, None)
        if assignment is not None:
            return assignment
        return {"assignment_id": f"unbound_{request_hash.removeprefix('sha256:')[:16]}"}

    def attempt_for_assignment(self, assignment_id: str) -> dict[str, object] | None:
        for record in reversed(self._attempts):
            if record.get("assignment_id") == assignment_id:
                return record
        return None

    def mark_attempt(
        self,
        *,
        assignment_id: str,
        outcome: str,
        reason_code: str | None = None,
    ) -> None:
        record = self.attempt_for_assignment(assignment_id)
        if record is None:
            raise AcceptanceReplayError("acceptance_assignment_missing")
        if outcome not in {"provider_error", "rejected", "validated"}:
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        record["outcome"] = outcome
        if reason_code is not None:
            record["reason_code"] = bounded_reason(reason_code)

    def record_generation_rejection(
        self,
        assignment: object,
        rejection: Mapping[str, object],
    ) -> None:
        lineage = assignment.lineage()
        assignment_id = lineage.get("assignment_id")
        if not isinstance(assignment_id, str):
            raise AcceptanceReplayError("acceptance_assignment_missing")
        details = rejection.get("details") if isinstance(rejection, Mapping) else None
        reason: object = None
        if isinstance(details, Mapping):
            for key in ("schema_reason", "reason_code", "cause"):
                if isinstance(details.get(key), str):
                    reason = details[key]
                    break
        if reason is None and isinstance(rejection.get("cause"), str):
            reason = rejection["cause"]
        existing = self.attempt_for_assignment(assignment_id)
        if existing is not None and existing.get("outcome") == "provider_error":
            existing.setdefault("reason_code", bounded_reason(reason))
            return
        self.mark_attempt(
            assignment_id=assignment_id,
            outcome="rejected",
            reason_code=bounded_reason(reason),
        )

    def record_attempt(
        self,
        *,
        assignment: Mapping[str, object],
        request_hash: str,
        response: Mapping[str, object] | None,
        response_hash: str | None,
        outcome: str,
        usage: Mapping[str, object] | None,
        reason_code: str | None = None,
        retry_count: int = 0,
    ) -> dict[str, object]:
        if self._frozen:
            raise AcceptanceReplayError("acceptance_evidence_already_frozen")
        if not isinstance(assignment, Mapping):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        assignment_id = assignment.get("assignment_id")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        safe_assignment = _sanitize_json_value(assignment)
        if not isinstance(safe_assignment, Mapping):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        _require_hash(request_hash)
        if outcome not in {"provider_error", "rejected", "validated"}:
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0:
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        sanitized_response: dict[str, object] | None = None
        computed_response_hash: str | None = None
        if response is not None:
            sanitized_response = sanitize_provider_response(response)
            computed_response_hash = hash_value(sanitized_response)
            if response_hash is not None and response_hash != computed_response_hash:
                raise AcceptanceReplayError("acceptance_identity_mismatch")
        elif response_hash is not None:
            _require_hash(response_hash, "acceptance_identity_mismatch")
        record: dict[str, object] = {
            "attempt_id": (
                f"{self.contract.provider_attempt_id_prefix}_"
                f"{len(self._attempts) + 1:04d}"
            ),
            "assignment_id": assignment_id,
            "assignment": dict(safe_assignment),
            "assignment_lineage": dict(safe_assignment),
            "request_hash": request_hash,
            "response": sanitized_response,
            "response_hash": computed_response_hash,
            "parser_version": self.contract.provider_parser_version,
            "outcome": outcome,
            "usage": bounded_usage(usage),
            "retry_count": retry_count,
        }
        if reason_code is not None:
            if not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
                raise AcceptanceReplayError("acceptance_evidence_malformed")
            record["reason_code"] = reason_code
        self._attempts.append(record)
        record["assignment_lineage"] = dict(
            self._pending_assignment_lineages.pop(request_hash, safe_assignment)
        )
        return record

    def freeze(
        self,
        output_path: Path,
        *,
        qualification: Mapping[str, object],
        release_pack_verification: Mapping[str, object],
        release_pack_hash: str,
        run_binding: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if self._frozen or output_path.exists():
            raise AcceptanceReplayError("acceptance_evidence_already_frozen")
        if (
            qualification.get("status") != "passed"
            or qualification.get("effective_qualification") != "release_candidate"
            or not isinstance(qualification.get("claims"), Mapping)
            or qualification["claims"].get("publishable") is not False
            or qualification["claims"].get("training_recommended") is not False
        ):
            raise AcceptanceReplayError("real_release_candidate_not_verified")
        if release_pack_verification.get("status") != "passed":
            raise AcceptanceReplayError("release_pack_not_independently_verified")
        _require_hash(release_pack_hash)
        if not self._attempts:
            raise AcceptanceReplayError("acceptance_evidence_missing")
        if set(self._mutation_judge_usage) != {
            "attempts",
            "attempt_ceiling",
            "tokens",
            "outcomes",
        }:
            raise AcceptanceReplayError("live_usage_malformed")
        if not isinstance(run_binding, Mapping):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        safe_run_binding = _sanitize_json_value(run_binding)
        if not isinstance(safe_run_binding, Mapping):
            raise AcceptanceReplayError("acceptance_binding_malformed")
        replay_attempts = [
            record
            for record in self._attempts
            if record.get("outcome") == "validated"
            and isinstance(record.get("response"), Mapping)
            and isinstance(record.get("response_hash"), str)
        ]
        retry_limit = getattr(self.authorization, "generator_retry_limit", None)
        attempt_budget = getattr(self.authorization, "attempt_budget", None)
        if (
            not isinstance(retry_limit, int)
            or isinstance(retry_limit, bool)
            or retry_limit not in range(MAX_GENERATOR_RETRIES + 1)
            or not isinstance(attempt_budget, int)
            or isinstance(attempt_budget, bool)
            or attempt_budget <= 0
            or len(self._attempts) > attempt_budget
            or any(
                not isinstance(record.get("retry_count"), int)
                or isinstance(record.get("retry_count"), bool)
                or record.get("retry_count") < 0
                or record.get("retry_count") > retry_limit
                for record in self._attempts
            )
        ):
            raise AcceptanceReplayError("live_usage_malformed")
        if not replay_attempts:
            raise AcceptanceReplayError("acceptance_replay_inputs_missing")
        records = [dict(record) for record in self._attempts]
        retries = sum(
            int(record.get("retry_count", 0))
            for record in records
            if isinstance(record.get("retry_count"), int)
            and not isinstance(record.get("retry_count"), bool)
        )
        evidence: dict[str, object] = {
            "schema_version": self.contract.provider_evidence_schema_version,
            "evidence_class": self.contract.evidence_class,
            "frozen": True,
            "freeze_policy": self.contract.freeze_policy,
            "authorization": _bounded_record(
                self.authorization.to_record(),
                "acceptance_authorization_malformed",
            ),
            "provider": dict(self.provider_identity),
            "mutation_judge": dict(self.mutation_judge_identity),
            "run_binding": dict(safe_run_binding),
            "attempts": records,
            "replay_attempts": [dict(record) for record in replay_attempts],
            "usage": {
                "logical_calls": len(records),
                "replayable_calls": len(replay_attempts),
                "tokens": sum_usage(records),
                "retries": retries,
                "physical_calls": len(records) + retries,
                "physical_call_ceiling": _physical_call_ceiling(self.authorization),
            },
            "mutation_judge_usage": dict(self._mutation_judge_usage),
            "cost": {"status": "not_reported", "amount": None, "currency": None},
            "qualification": {
                "effective_qualification": "release_candidate",
                "release_pack_hash": release_pack_hash,
                "release_pack_verification_status": "passed",
            },
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._frozen = True
        return evidence


class SanitizedMutationJudgeUsageObserver:
    """Record bounded judge usage without retaining prompts or payloads."""

    def __init__(
        self,
        *,
        attempt_ceiling: int | None = None,
        attempt_id_prefix: str = "mutation_judge_attempt",
    ) -> None:
        if attempt_ceiling is not None and (
            not isinstance(attempt_ceiling, int)
            or isinstance(attempt_ceiling, bool)
            or attempt_ceiling <= 0
        ):
            raise AcceptanceReplayError("authorization_budget_invalid")
        self._attempt_ceiling = attempt_ceiling
        self._attempt_id_prefix = attempt_id_prefix
        self._attempts: list[dict[str, object]] = []

    def before_provider_call(self, *, prompt_hash: str) -> str:
        _require_hash(prompt_hash)
        if (
            self._attempt_ceiling is not None
            and len(self._attempts) >= self._attempt_ceiling
        ):
            raise AcceptanceReplayError("acceptance_mutation_judge_attempt_budget_exceeded")
        attempt_id = f"{self._attempt_id_prefix}_{len(self._attempts) + 1:04d}"
        self._attempts.append(
            {
                "attempt_id": attempt_id,
                "request_hash": prompt_hash,
                "outcome": "in_flight",
                "usage": {},
            }
        )
        return attempt_id

    def provider_response_received(
        self,
        *,
        attempt_id: object,
        lineage: Mapping[str, object],
    ) -> None:
        record = self._find(attempt_id)
        record["outcome"] = "response_received"
        record["provider"] = {
            key: lineage[key]
            for key in ("provider_host", "model", "config_hash", "role", "role_version")
            if key in lineage and isinstance(lineage[key], (str, int))
        }
        record["usage"] = bounded_usage(lineage.get("tokens"))

    def provider_attempt_failed(
        self,
        *,
        attempt_id: object,
        error: BaseException,
    ) -> None:
        record = self._find(attempt_id)
        record["outcome"] = "provider_error"
        cause = getattr(error, "cause", None)
        record["reason_code"] = bounded_reason(cause)
        record["failure_class"] = bounded_judge_failure_class(error)

    def _find(self, attempt_id: object) -> dict[str, object]:
        for record in self._attempts:
            if record.get("attempt_id") == attempt_id:
                return record
        raise AcceptanceReplayError("acceptance_judge_attempt_missing")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "attempts": len(self._attempts),
            "tokens": sum_usage(self._attempts),
            "outcomes": {
                outcome: sum(record.get("outcome") == outcome for record in self._attempts)
                for outcome in sorted({str(record.get("outcome")) for record in self._attempts})
            },
        }
        if self._attempt_ceiling is not None:
            record["attempt_ceiling"] = self._attempt_ceiling
        return record

    def to_failure_record(self) -> dict[str, object]:
        record = self.to_record()
        record["failure_classes"] = {
            failure_class: sum(
                attempt.get("failure_class") == failure_class
                for attempt in self._attempts
            )
            for failure_class in sorted(
                {
                    str(attempt.get("failure_class"))
                    for attempt in self._attempts
                    if isinstance(attempt.get("failure_class"), str)
                }
            )
        }
        return record


class BoundedSanitizedProvider:
    """Provider adapter that records only bounded generation responses."""

    def __init__(
        self,
        delegate: object,
        *,
        recorder: SanitizedProviderEvidenceRecorder,
        max_logical_calls: int,
        role: str = "task_generation",
    ) -> None:
        if (
            not isinstance(max_logical_calls, int)
            or isinstance(max_logical_calls, bool)
            or max_logical_calls <= 0
        ):
            raise AcceptanceReplayError("authorization_budget_invalid")
        self._delegate = delegate
        self._recorder = recorder
        self._max_logical_calls = max_logical_calls
        self._role = role
        self._logical_calls = 0

    @property
    def logical_calls(self) -> int:
        return self._logical_calls

    def generate_json(self, prompt: str, *, role: str) -> Any:
        from synthesis.llm import LLMProviderError

        if not isinstance(prompt, str) or not prompt:
            raise AcceptanceReplayError("provider_request_invalid")
        if role != self._role:
            raise AcceptanceReplayError("provider_role_invalid")
        request_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        assignment = self._recorder.assignment_for_request(request_hash)
        self._logical_calls += 1
        if self._logical_calls > self._max_logical_calls:
            self._recorder.record_attempt(
                assignment=assignment,
                request_hash=request_hash,
                response=None,
                response_hash=None,
                outcome="provider_error",
                reason_code="live_attempt_budget_exceeded",
                usage={},
            )
            raise LLMProviderError(
                cause="live_attempt_budget_exceeded",
                error_class="LiveAttemptBudgetExceeded",
                retryable=False,
                retry_count=0,
                lineage={
                    "role": role,
                    "prompt_hash": request_hash,
                    "error_class": "LiveAttemptBudgetExceeded",
                    "retry_count": 0,
                    "tokens": {},
                },
            )
        try:
            result = self._delegate.generate_json(prompt, role=role)
        except LLMProviderError as exc:
            lineage = exc.lineage if isinstance(exc.lineage, Mapping) else {}
            self._recorder.record_attempt(
                assignment=assignment,
                request_hash=request_hash,
                response=None,
                response_hash=None,
                outcome="provider_error",
                reason_code=bounded_reason(getattr(exc, "cause", None)),
                usage=bounded_usage(lineage.get("tokens")),
                retry_count=bounded_retry_count(getattr(exc, "retry_count", 0)),
            )
            raise
        content = getattr(result, "content", None)
        lineage = getattr(result, "lineage", {})
        safe_response: Mapping[str, object] | None
        response_hash: str | None
        try:
            safe_response = sanitize_provider_response(content)
            response_hash = hash_value(safe_response)
        except AcceptanceReplayError:
            safe_response = None
            response_hash = None
        self._recorder.record_attempt(
            assignment=assignment,
            request_hash=request_hash,
            response=safe_response,
            response_hash=response_hash,
            outcome="rejected",
            reason_code=(None if safe_response is not None else "provider_response_not_sanitizable"),
            usage=(lineage.get("tokens") if isinstance(lineage, Mapping) else {}),
            retry_count=bounded_retry_count(
                lineage.get("retry_count", 0) if isinstance(lineage, Mapping) else 0
            ),
        )
        return result


class CoverageAssignmentEvidenceObserver:
    """Bridge scheduler callbacks into the bounded evidence recorder."""

    def __init__(self, recorder: SanitizedProviderEvidenceRecorder) -> None:
        self._recorder = recorder

    def before_provider_call(
        self,
        *,
        assignment: object,
        batch_context: object,
        requested_candidate_count: int,
        prompt_hash: str,
    ) -> None:
        del batch_context, requested_candidate_count
        lineage = assignment.lineage()
        assignment_id = lineage.get("assignment_id")
        if not isinstance(assignment_id, str):
            raise AcceptanceReplayError("acceptance_assignment_missing")
        request_hash = prompt_hash
        if not isinstance(request_hash, str):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        if _HASH_RE.fullmatch(request_hash) is None:
            if re.fullmatch(r"[0-9a-f]{64}", request_hash):
                request_hash = "sha256:" + request_hash
            else:
                raise AcceptanceReplayError("acceptance_evidence_malformed")
        self._recorder.bind_assignment(
            request_hash=request_hash,
            assignment=assignment.provider_contract(),
            assignment_lineage=lineage,
        )

    def provider_response_received(
        self,
        *,
        assignment: object,
        batch_context: object,
        requested_candidate_count: int,
        lineage: Mapping[str, object],
    ) -> None:
        del batch_context, requested_candidate_count, lineage
        assignment_id = assignment.lineage().get("assignment_id")
        if isinstance(assignment_id, str):
            record = self._recorder.attempt_for_assignment(assignment_id)
            if record is not None and record.get("outcome") == "rejected":
                record.pop("reason_code", None)

    def provider_attempt_failed(
        self,
        *,
        assignment: object,
        batch_context: object,
        requested_candidate_count: int,
        error: BaseException,
    ) -> None:
        del batch_context, requested_candidate_count
        assignment_id = assignment.lineage().get("assignment_id")
        if isinstance(assignment_id, str):
            self._recorder.mark_attempt(
                assignment_id=assignment_id,
                outcome="provider_error",
                reason_code=bounded_reason(getattr(error, "cause", None)),
            )

    def validated_contracts_checkpointed(
        self,
        *,
        assignment: object,
        batch_context: object,
        requested_candidate_count: int,
        contracts: Sequence[object],
        lineage: Mapping[str, object],
    ) -> None:
        del batch_context, requested_candidate_count, contracts, lineage
        assignment_id = assignment.lineage().get("assignment_id")
        if isinstance(assignment_id, str):
            self._recorder.mark_attempt(
                assignment_id=assignment_id,
                outcome="validated",
            )


def build_coverage_attempt_observer_factory(
    recorder: SanitizedProviderEvidenceRecorder,
) -> Callable[[object], CoverageAssignmentEvidenceObserver]:
    """Return the callback factory accepted by coverage scheduling."""

    def factory(assignment: object) -> CoverageAssignmentEvidenceObserver:
        del assignment
        return CoverageAssignmentEvidenceObserver(recorder)

    return factory


def _validate_safe_mapping(value: object, reason_code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AcceptanceReplayError(reason_code)
    try:
        safe = _sanitize_json_value(value)
    except AcceptanceReplayError:
        raise AcceptanceReplayError(reason_code) from None
    if not isinstance(safe, Mapping):
        raise AcceptanceReplayError(reason_code)
    return safe


def validate_provider_evidence(
    evidence: Mapping[str, object],
    *,
    contract: AcceptanceReplayContract = DEFAULT_ACCEPTANCE_REPLAY_CONTRACT,
) -> None:
    """Validate a frozen provider evidence record before replay."""

    if not isinstance(evidence, Mapping):
        raise AcceptanceReplayError("acceptance_evidence_malformed")
    required = {
        "schema_version",
        "evidence_class",
        "frozen",
        "freeze_policy",
        "authorization",
        "provider",
        "mutation_judge",
        "run_binding",
        "attempts",
        "replay_attempts",
        "usage",
        "mutation_judge_usage",
        "cost",
        "qualification",
    }
    if set(evidence) != required:
        raise AcceptanceReplayError("acceptance_evidence_malformed")
    if (
        evidence.get("schema_version") != contract.provider_evidence_schema_version
        or evidence.get("evidence_class") != contract.evidence_class
        or evidence.get("frozen") is not True
        or evidence.get("freeze_policy") != contract.freeze_policy
    ):
        raise AcceptanceReplayError("acceptance_identity_mismatch")

    authorization = evidence.get("authorization")
    if not isinstance(authorization, Mapping) or authorization.get("approved") is not True:
        raise AcceptanceReplayError("live_provider_authorization_required")
    _validate_safe_mapping(authorization, "acceptance_evidence_malformed")
    provider = evidence.get("provider")
    judge = evidence.get("mutation_judge")
    if not isinstance(provider, Mapping) or not isinstance(judge, Mapping):
        raise AcceptanceReplayError("acceptance_evidence_malformed")
    contract.validate_identities(provider, judge)
    if (
        authorization.get("generator_provider") != provider.get("provider_id")
        or authorization.get("generator_model") != provider.get("model")
        or authorization.get("mutation_judge_provider") != judge.get("provider")
        or authorization.get("mutation_judge_model") != judge.get("model")
    ):
        raise AcceptanceReplayError("live_identity_binding_mismatch")

    authorized_retry_limit = authorization.get("generator_retry_limit")
    authorized_attempt_budget = authorization.get("attempt_budget")
    if (
        not isinstance(authorized_retry_limit, int)
        or isinstance(authorized_retry_limit, bool)
        or authorized_retry_limit not in range(MAX_GENERATOR_RETRIES + 1)
        or not isinstance(authorized_attempt_budget, int)
        or isinstance(authorized_attempt_budget, bool)
        or authorized_attempt_budget <= 0
    ):
        raise AcceptanceReplayError("live_usage_malformed")

    run_binding = evidence.get("run_binding")
    if not isinstance(run_binding, Mapping):
        raise AcceptanceReplayError("acceptance_binding_malformed")
    if set(run_binding) != _RUN_BINDING_KEYS:
        raise AcceptanceReplayError("acceptance_binding_malformed")
    for key in ("profile_id", "dataset_version", "seed_id", "seed_domain", "plan_id", "coverage_plan_id"):
        if not isinstance(run_binding.get(key), str) or not run_binding.get(key):
            raise AcceptanceReplayError("acceptance_binding_malformed")
    for key in ("plan_hash", "coverage_plan_hash", "source_policy_hash"):
        _require_hash(run_binding.get(key), "acceptance_binding_malformed")
    _validate_safe_mapping(run_binding, "acceptance_binding_malformed")

    attempts = evidence.get("attempts")
    replay_attempts = evidence.get("replay_attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(replay_attempts, list):
        raise AcceptanceReplayError("acceptance_evidence_missing")
    attempt_by_id: dict[str, Mapping[str, object]] = {}
    allowed_attempt_keys = {
        "attempt_id",
        "assignment_id",
        "assignment",
        "assignment_lineage",
        "request_hash",
        "response",
        "response_hash",
        "parser_version",
        "outcome",
        "usage",
        "retry_count",
        "reason_code",
    }
    for raw_attempt in attempts:
        if not isinstance(raw_attempt, Mapping):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        if not set(raw_attempt) <= allowed_attempt_keys:
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        attempt_id = raw_attempt.get("attempt_id")
        assignment_id = raw_attempt.get("assignment_id")
        if (
            not isinstance(attempt_id, str)
            or _IDENTIFIER_RE.fullmatch(attempt_id) is None
            or not isinstance(assignment_id, str)
            or _IDENTIFIER_RE.fullmatch(assignment_id) is None
            or attempt_id in attempt_by_id
            or not attempt_id.startswith(contract.provider_attempt_id_prefix + "_")
            or _HASH_RE.fullmatch(str(raw_attempt.get("request_hash", ""))) is None
            or raw_attempt.get("parser_version") != contract.provider_parser_version
            or raw_attempt.get("outcome") not in {"provider_error", "rejected", "validated"}
            or not isinstance(raw_attempt.get("assignment"), Mapping)
            or not isinstance(raw_attempt.get("assignment_lineage"), Mapping)
            or raw_attempt["assignment"].get("assignment_id") != assignment_id
            or raw_attempt["assignment_lineage"].get("assignment_id") != assignment_id
            or not isinstance(raw_attempt.get("usage"), Mapping)
            or not isinstance(raw_attempt.get("retry_count"), int)
            or isinstance(raw_attempt.get("retry_count"), bool)
            or raw_attempt.get("retry_count") < 0
        ):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        if raw_attempt["retry_count"] > authorized_retry_limit:
            raise AcceptanceReplayError("live_usage_malformed")
        _validate_safe_mapping(raw_attempt["assignment"], "acceptance_evidence_malformed")
        _validate_safe_mapping(raw_attempt["assignment_lineage"], "acceptance_evidence_malformed")
        if dict(raw_attempt["usage"]) != bounded_usage(raw_attempt["usage"]):
            raise AcceptanceReplayError("live_usage_malformed")
        response = raw_attempt.get("response")
        response_hash = raw_attempt.get("response_hash")
        if response is not None:
            sanitized = sanitize_provider_response(response)
            if response_hash != hash_value(sanitized):
                raise AcceptanceReplayError("acceptance_identity_mismatch")
        elif raw_attempt.get("outcome") == "provider_error" and response_hash is not None:
            raise AcceptanceReplayError("acceptance_replay_input_mismatch")
        elif response_hash is not None:
            _require_hash(response_hash, "acceptance_identity_mismatch")
        elif raw_attempt.get("outcome") == "validated":
            raise AcceptanceReplayError("acceptance_replay_input_malformed")
        if raw_attempt.get("reason_code") is not None and (
            not isinstance(raw_attempt.get("reason_code"), str)
            or _REASON_RE.fullmatch(str(raw_attempt.get("reason_code"))) is None
        ):
            raise AcceptanceReplayError("acceptance_evidence_malformed")
        attempt_by_id[attempt_id] = raw_attempt

    replay_ids: set[str] = set()
    for raw_attempt in replay_attempts:
        if not isinstance(raw_attempt, Mapping):
            raise AcceptanceReplayError("acceptance_replay_input_malformed")
        if not set(raw_attempt) <= allowed_attempt_keys:
            raise AcceptanceReplayError("acceptance_replay_input_malformed")
        _validate_safe_mapping(raw_attempt, "acceptance_replay_input_malformed")
        attempt_id = raw_attempt.get("attempt_id")
        if not isinstance(attempt_id, str) or attempt_id in replay_ids:
            raise AcceptanceReplayError("acceptance_replay_input_malformed")
        source = attempt_by_id.get(attempt_id)
        if source is None or source.get("outcome") != "validated":
            raise AcceptanceReplayError("acceptance_replay_input_mismatch")
        if (
            raw_attempt.get("response") != source.get("response")
            or raw_attempt.get("response_hash") != source.get("response_hash")
            or raw_attempt.get("assignment") != source.get("assignment")
            or raw_attempt.get("assignment_lineage")
            != source.get("assignment_lineage")
            or raw_attempt.get("request_hash") != source.get("request_hash")
        ):
            raise AcceptanceReplayError("acceptance_replay_input_mismatch")
        replay_ids.add(attempt_id)
    if not replay_ids:
        raise AcceptanceReplayError("acceptance_replay_inputs_missing")
    expected_replay_ids = {
        str(raw_attempt.get("attempt_id"))
        for raw_attempt in attempts
        if isinstance(raw_attempt, Mapping)
        and raw_attempt.get("outcome") == "validated"
        and isinstance(raw_attempt.get("response"), Mapping)
        and isinstance(raw_attempt.get("response_hash"), str)
    }
    if replay_ids != expected_replay_ids:
        raise AcceptanceReplayError("acceptance_replay_input_mismatch")

    usage = evidence.get("usage")
    if (
        not isinstance(usage, Mapping)
        or set(usage)
        != {
            "logical_calls",
            "replayable_calls",
            "tokens",
            "retries",
            "physical_calls",
            "physical_call_ceiling",
        }
        or usage.get("logical_calls") != len(attempts)
        or usage.get("replayable_calls") != len(replay_attempts)
        or not isinstance(usage.get("tokens"), Mapping)
        or dict(usage["tokens"]) != bounded_usage(usage["tokens"])
    ):
        raise AcceptanceReplayError("live_usage_malformed")
    retries = usage.get("retries")
    physical_calls = usage.get("physical_calls")
    physical_call_ceiling = usage.get("physical_call_ceiling")
    authorized_retry_limit = authorization.get("generator_retry_limit")
    authorized_attempt_budget = authorization.get("attempt_budget")
    if (
        not isinstance(retries, int)
        or isinstance(retries, bool)
        or retries < 0
        or not isinstance(physical_calls, int)
        or isinstance(physical_calls, bool)
        or physical_calls != len(attempts) + retries
        or not isinstance(physical_call_ceiling, int)
        or isinstance(physical_call_ceiling, bool)
        or not isinstance(authorized_retry_limit, int)
        or isinstance(authorized_retry_limit, bool)
        or authorized_retry_limit not in range(MAX_GENERATOR_RETRIES + 1)
        or not isinstance(authorized_attempt_budget, int)
        or isinstance(authorized_attempt_budget, bool)
        or authorized_attempt_budget <= 0
        or len(attempts) > authorized_attempt_budget
        or physical_call_ceiling != authorized_attempt_budget * (authorized_retry_limit + 1)
        or physical_calls > physical_call_ceiling
    ):
        raise AcceptanceReplayError("live_usage_malformed")

    mutation_judge_usage = evidence.get("mutation_judge_usage")
    if (
        not isinstance(mutation_judge_usage, Mapping)
        or set(mutation_judge_usage) != {"attempts", "attempt_ceiling", "tokens", "outcomes"}
    ):
        raise AcceptanceReplayError("live_usage_malformed")
    judge_attempts = mutation_judge_usage.get("attempts")
    judge_attempt_ceiling = mutation_judge_usage.get("attempt_ceiling")
    judge_tokens = mutation_judge_usage.get("tokens")
    judge_outcomes = mutation_judge_usage.get("outcomes")
    if (
        not isinstance(judge_attempts, int)
        or isinstance(judge_attempts, bool)
        or judge_attempts < 1
        or not isinstance(judge_attempt_ceiling, int)
        or isinstance(judge_attempt_ceiling, bool)
        or judge_attempt_ceiling < judge_attempts
        or not isinstance(judge_tokens, Mapping)
        or dict(judge_tokens) != bounded_usage(judge_tokens)
        or not isinstance(judge_outcomes, Mapping)
    ):
        raise AcceptanceReplayError("live_usage_malformed")
    safe_judge_outcomes: dict[str, int] = {}
    for outcome, count in judge_outcomes.items():
        if (
            outcome not in {"provider_error", "response_received"}
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            raise AcceptanceReplayError("live_usage_malformed")
        safe_judge_outcomes[str(outcome)] = count
    if sum(safe_judge_outcomes.values()) != judge_attempts:
        raise AcceptanceReplayError("live_usage_malformed")
    cost = evidence.get("cost")
    if (
        not isinstance(cost, Mapping)
        or cost.get("status") != "not_reported"
        or cost.get("amount") is not None
        or cost.get("currency") is not None
    ):
        raise AcceptanceReplayError("live_cost_malformed")
    qualification = evidence.get("qualification")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("effective_qualification") != "release_candidate"
        or qualification.get("release_pack_verification_status") != "passed"
        or _HASH_RE.fullmatch(str(qualification.get("release_pack_hash", ""))) is None
    ):
        raise AcceptanceReplayError("real_release_candidate_not_verified")


def load_provider_evidence(
    path: Path,
    *,
    contract: AcceptanceReplayContract = DEFAULT_ACCEPTANCE_REPLAY_CONTRACT,
) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceReplayError("acceptance_evidence_unreadable") from exc
    if not isinstance(value, Mapping):
        raise AcceptanceReplayError("acceptance_evidence_malformed")
    validate_provider_evidence(value, contract=contract)
    return dict(value)


def replay_frozen_provider_evidence(
    evidence: Mapping[str, object] | Path,
    *,
    replay: Callable[[Mapping[str, object]], int | Mapping[str, object]],
    contract: AcceptanceReplayContract = DEFAULT_ACCEPTANCE_REPLAY_CONTRACT,
) -> dict[str, object]:
    """Replay sanitized evidence through a pack-owned, provider-free callback."""

    loaded = (
        load_provider_evidence(evidence, contract=contract)
        if isinstance(evidence, Path)
        else dict(evidence)
    )
    if not isinstance(evidence, Path):
        validate_provider_evidence(loaded, contract=contract)
    try:
        replayed = replay(loaded)
    except AcceptanceReplayError:
        raise
    except Exception as exc:
        raise AcceptanceReplayError("acceptance_replay_failed") from exc
    if isinstance(replayed, Mapping):
        result = dict(replayed)
        if result.get("status") != "passed" or result.get("provider_calls") != 0:
            raise AcceptanceReplayError("acceptance_replay_failed")
        return result
    expected = len(loaded["replay_attempts"])
    if not isinstance(replayed, int) or isinstance(replayed, bool) or replayed != expected:
        raise AcceptanceReplayError("acceptance_replay_count_mismatch")
    return {
        "schema_version": contract.replay_result_schema_version,
        "status": "passed",
        "reason_code": "replay_verified",
        "replayed_attempt_count": replayed,
        "provider_calls": 0,
        "evidence_class": contract.evidence_class,
    }


def _record(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    to_record = getattr(value, "to_record", None)
    if callable(to_record):
        result = to_record()
        if isinstance(result, Mapping):
            return dict(result)
    canonical = getattr(value, "canonical", None)
    if callable(canonical):
        result = canonical()
        if isinstance(result, Mapping):
            return dict(result)
    raise AcceptanceReplayError("acceptance_binding_malformed")


def _bounded_record(value: object, reason_code: str) -> dict[str, object]:
    try:
        record = _record(value)
        safe = _sanitize_json_value(record)
    except AcceptanceReplayError:
        raise AcceptanceReplayError(reason_code) from None
    if not isinstance(safe, Mapping):
        raise AcceptanceReplayError(reason_code)
    return dict(safe)


def _ensure_empty_directory(path: Path, reason_code: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise AcceptanceReplayError(reason_code)
    path.mkdir(parents=True, exist_ok=True)


def _reason_code(error: BaseException, fallback: str) -> str:
    reason = getattr(error, "reason_code", None)
    if isinstance(reason, str) and _REASON_RE.fullmatch(reason):
        return reason
    return fallback


def _hash_file(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise AcceptanceReplayError("release_pack_not_independently_verified") from exc


def _path_is_file(path: object) -> bool:
    return isinstance(path, Path) and path.is_file() and not path.is_symlink()


def _validate_release(
    release: AcceptanceReleaseEvidence,
    *,
    output_dir: Path,
) -> None:
    paths = (
        release.replay_report_path,
        release.evaluation_report_path,
        release.profile_decision_path,
        release.dataset_release_report_path,
        release.release_quality_audit_path,
        release.release_pack_path,
    )
    if any(not _path_is_file(path) for path in paths):
        raise AcceptanceReplayError("acceptance_release_evidence_missing")
    try:
        for path in paths:
            path.resolve().relative_to(output_dir.resolve())
    except ValueError as exc:
        raise AcceptanceReplayError("acceptance_release_path_unsafe") from exc
    if not isinstance(release.release_pack_verification, Mapping):
        raise AcceptanceReplayError("release_pack_not_independently_verified")
    if release.release_pack_verification.get("status") != "passed":
        raise AcceptanceReplayError("release_pack_not_independently_verified")
    if not isinstance(release.release_pack_hash, str) or _HASH_RE.fullmatch(
        release.release_pack_hash
    ) is None:
        raise AcceptanceReplayError("acceptance_release_identity_mismatch")
    if _hash_file(release.release_pack_path) != release.release_pack_hash:
        raise AcceptanceReplayError("acceptance_release_identity_mismatch")
    _bounded_record(release.release_pack_verification, "release_pack_not_independently_verified")


def _validate_qualification(qualification: Mapping[str, object]) -> None:
    claims = qualification.get("claims")
    if (
        qualification.get("status") != "passed"
        or qualification.get("effective_qualification") != "release_candidate"
        or not isinstance(claims, Mapping)
        or claims.get("publishable") is not False
        or claims.get("training_recommended") is not False
    ):
        raise AcceptanceReplayError("real_release_candidate_not_verified")
    _bounded_record(qualification, "real_release_candidate_not_verified")


class AcceptanceReplayHarness:
    """Run the common acceptance lifecycle through one Domain Pack adapter."""

    def __init__(self, adapter: AcceptanceReplayAdapter) -> None:
        self._adapter = adapter

    def _error_for_reason(self, reason_code: str) -> BaseException:
        error_factory = getattr(self._adapter, "error_for_reason", None)
        if callable(error_factory):
            return error_factory(reason_code)
        return AcceptanceReplayError(reason_code)

    def _write_failure(
        self,
        output_dir: Path,
        *,
        reason_code: str,
        phase: str,
        authorization: AcceptanceAuthorization,
        preparation: AcceptancePreparation,
        recorder: AcceptanceEvidenceRecorder,
        observer: AcceptanceUsageObserver,
        mutation_judge_preflight: Mapping[str, object] | None,
        rejections_path: Path | None = None,
        qualification: Mapping[str, object] | None = None,
    ) -> None:
        try:
            self._adapter.write_failure(
                output_dir,
                reason_code=reason_code,
                phase=phase,
                authorization=authorization,
                preparation=preparation,
                recorder=recorder,
                observer=observer,
                mutation_judge_preflight=mutation_judge_preflight,
                rejections_path=rejections_path,
                qualification=qualification,
            )
        except Exception:
            # The original bounded reason remains the actionable failure.  A
            # failure writer must never turn a safe rejection into a traceback
            # containing provider or source details.
            return

    def run(
        self,
        output_dir: Path,
        *,
        profile: object,
        authorization: AcceptanceAuthorization,
        generator_config: object | None = None,
        generator_http_client: object | None = None,
        mutation_judge_http_client: object | None = None,
        proof_root: Path | None = None,
        max_generator_retries: int | None = None,
    ) -> AcceptanceRunResult:
        output_dir = Path(output_dir)
        proof_root = (
            Path(proof_root)
            if proof_root is not None
            else output_dir.parent / (output_dir.name + "-proof")
        )
        _ensure_empty_directory(output_dir, "acceptance_output_not_empty")
        _ensure_empty_directory(proof_root, "acceptance_proof_output_not_empty")

        preparation = self._adapter.prepare(profile=profile, output_dir=output_dir)
        if not isinstance(preparation, AcceptancePreparation):
            raise AcceptanceReplayError("acceptance_preparation_malformed")
        preparation.validate()
        profile_record = dict(preparation.profile_record)
        retry_limit = (
            max_generator_retries
            if max_generator_retries is not None
            else _field(authorization, "generator_retry_limit")
        )
        if (
            not isinstance(retry_limit, int)
            or isinstance(retry_limit, bool)
            or retry_limit not in range(MAX_GENERATOR_RETRIES + 1)
        ):
            raise AcceptanceReplayError("generator_retry_budget_invalid")
        self._adapter.validate_authorization(
            profile=profile,
            preparation=preparation,
            authorization=authorization,
            max_generator_retries=retry_limit,
        )
        try:
            config = self._adapter.resolve_generator_config(generator_config)
        except Exception as exc:
            if isinstance(exc, AcceptanceReplayError):
                raise
            reason_code = _reason_code(exc, "llm_configuration_required")
            raise AcceptanceReplayError(reason_code) from exc
        self._adapter.validate_generator_config(
            profile=profile,
            authorization=authorization,
            config=config,
        )

        provider_identity = dict(self._adapter.generator_identity(config))
        judge_identity = dict(
            self._adapter.mutation_judge_identity(profile=profile, config=config)
        )
        self._adapter.evidence_contract.validate_identities(
            provider_identity,
            judge_identity,
        )
        auth_record = _bounded_record(
            authorization.to_record(),
            "acceptance_authorization_malformed",
        )
        if auth_record.get("approved") is not True:
            raise AcceptanceReplayError("live_provider_authorization_required")
        provider_identity = _bounded_record(
            provider_identity,
            "acceptance_identity_malformed",
        )
        judge_identity = _bounded_record(
            judge_identity,
            "acceptance_identity_malformed",
        )
        if (
            auth_record.get("generator_provider") != provider_identity.get("provider_id")
            or auth_record.get("generator_model") != provider_identity.get("model")
            or auth_record.get("mutation_judge_provider") != judge_identity.get("provider")
            or auth_record.get("mutation_judge_model") != judge_identity.get("model")
        ):
            raise AcceptanceReplayError("live_identity_binding_mismatch")
        physical_call_ceiling = _physical_call_ceiling(authorization)
        judge_attempt_ceiling = self._adapter.mutation_judge_attempt_ceiling(
            profile=profile,
            preparation=preparation,
        )
        if (
            not isinstance(judge_attempt_ceiling, int)
            or isinstance(judge_attempt_ceiling, bool)
            or judge_attempt_ceiling <= 0
        ):
            raise AcceptanceReplayError("authorization_budget_invalid")

        plan_record = _record(preparation.plan)
        coverage_record = _record(preparation.coverage_plan)
        _write_json(
            output_dir / "authorization.json",
            {
                "schema_version": self._adapter.evidence_contract.acceptance_schema_version,
                "status": "authorized",
                "authorization": auth_record,
                "domain_plan": {
                    "plan_id": _field(preparation.plan, "plan_id"),
                    "plan_hash": _field(preparation.plan, "plan_hash"),
                    "domain_pack_reference": plan_record.get("domain_pack_reference"),
                },
                "coverage_plan": {
                    "plan_id": _field(preparation.coverage_plan, "plan_id"),
                    "plan_hash": _field(preparation.coverage_plan, "plan_hash"),
                    "attempt_ceiling": _field(preparation.coverage_plan, "attempt_ceiling"),
                    "target_accepted_sample_count": coverage_record.get(
                        "target_accepted_sample_count"
                    ),
                },
                "source_policy_hash": preparation.source_policy_hash,
                "generator": provider_identity,
                "mutation_judge": judge_identity,
                "generator_physical_call_ceiling": physical_call_ceiling,
                "mutation_judge_attempt_ceiling": judge_attempt_ceiling,
            },
        )
        _write_json(output_dir / "run_profile.json", profile_record)

        recorder = self._adapter.create_recorder(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=judge_identity,
        )
        observer = self._adapter.create_usage_observer(
            profile=profile,
            preparation=preparation,
        )
        started = time.perf_counter()
        mutation_judge_preflight: Mapping[str, object] | None = None
        try:
            raw_preflight = self._adapter.preflight_mutation_judge(
                profile=profile,
                config=config,
                http_client=mutation_judge_http_client,
                observer=observer,
            )
            if not isinstance(raw_preflight, Mapping):
                raise self._error_for_reason("acceptance_preflight_malformed")
            mutation_judge_preflight = _bounded_record(
                raw_preflight,
                "acceptance_preflight_malformed",
            )
            if mutation_judge_preflight.get("status") != "passed":
                reason_code = self._adapter.evidence_contract.preflight_failure_reason
                raise self._error_for_reason(reason_code)
        except Exception as exc:
            reason_code = _reason_code(
                exc,
                self._adapter.evidence_contract.preflight_failure_reason,
            )
            self._write_failure(
                output_dir,
                reason_code=reason_code,
                phase="mutation_judge_preflight",
                authorization=authorization,
                preparation=preparation,
                recorder=recorder,
                observer=observer,
                mutation_judge_preflight=mutation_judge_preflight,
            )
            raise

        try:
            provider = self._adapter.build_provider(
                config=config,
                authorization=authorization,
                recorder=recorder,
                http_client=generator_http_client,
                max_generator_retries=retry_limit,
            )
            pipeline = self._adapter.run_pipeline(
                output_dir=output_dir,
                profile=profile,
                provider=provider,
                recorder=recorder,
                observer=observer,
                mutation_judge_http_client=mutation_judge_http_client,
                config=config,
            )
            if not isinstance(pipeline, AcceptancePipelineResult):
                raise AcceptanceReplayError("acceptance_pipeline_result_malformed")
            pipeline.validate()
            self._adapter.validate_pipeline(
                profile=profile,
                preparation=preparation,
                pipeline=pipeline,
            )
        except Exception as exc:
            reason_code = _reason_code(
                exc,
                self._adapter.evidence_contract.pipeline_failure_reason,
            )
            self._write_failure(
                output_dir,
                reason_code=reason_code,
                phase="pipeline",
                authorization=authorization,
                preparation=preparation,
                recorder=recorder,
                observer=observer,
                mutation_judge_preflight=mutation_judge_preflight,
                rejections_path=(
                    pipeline.rejections_path
                    if "pipeline" in locals()
                    and isinstance(pipeline, AcceptancePipelineResult)
                    else None
                ),
            )
            if isinstance(exc, AcceptanceReplayError):
                raise self._error_for_reason(reason_code) from exc
            raise

        runtime_seconds = time.perf_counter() - started
        try:
            release = self._adapter.write_release_evidence(
                output_dir=output_dir,
                profile=profile,
                pipeline=pipeline,
                runtime_seconds=runtime_seconds,
            )
            if not isinstance(release, AcceptanceReleaseEvidence):
                raise AcceptanceReplayError("acceptance_release_evidence_malformed")
            _validate_release(release, output_dir=output_dir)
        except Exception as exc:
            reason_code = _reason_code(exc, "release_evidence_not_verified")
            self._write_failure(
                output_dir,
                reason_code=reason_code,
                phase="release_evidence",
                authorization=authorization,
                preparation=preparation,
                recorder=recorder,
                observer=observer,
                mutation_judge_preflight=mutation_judge_preflight,
                rejections_path=pipeline.rejections_path,
            )
            if isinstance(exc, AcceptanceReplayError):
                raise self._error_for_reason(reason_code) from exc
            raise

        try:
            if not isinstance(release.qualification, Mapping):
                raise AcceptanceReplayError("real_release_candidate_not_verified")
            _validate_qualification(release.qualification)
            self._adapter.bind_sample_assignments(
                recorder=recorder,
                pipeline=pipeline,
            )
            recorder.set_mutation_judge_usage(
                _bounded_record(observer.to_record(), "live_usage_malformed")
            )
            provider_evidence_path = output_dir / "trace" / "provider.json"
            provider_evidence = recorder.freeze(
                provider_evidence_path,
                qualification=release.qualification,
                release_pack_verification=release.release_pack_verification,
                release_pack_hash=release.release_pack_hash,
                run_binding=preparation.run_binding,
            )
        except Exception as exc:
            reason_code = _reason_code(exc, "qualification_evidence_not_freezable")
            self._write_failure(
                output_dir,
                reason_code=reason_code,
                phase="qualification",
                authorization=authorization,
                preparation=preparation,
                recorder=recorder,
                observer=observer,
                mutation_judge_preflight=mutation_judge_preflight,
                rejections_path=pipeline.rejections_path,
                qualification=release.qualification,
            )
            if isinstance(exc, AcceptanceReplayError):
                raise self._error_for_reason(reason_code) from exc
            raise

        try:
            replay = replay_frozen_provider_evidence(
                provider_evidence,
                replay=lambda evidence: self._adapter.replay(
                    evidence=evidence,
                    preparation=preparation,
                ),
                contract=self._adapter.evidence_contract,
            )
        except AcceptanceReplayError as exc:
            raise self._error_for_reason(_reason_code(exc, "acceptance_replay_failed")) from exc
        non_accepted = [
            record
            for record in provider_evidence.get("attempts", [])
            if isinstance(record, Mapping) and record.get("outcome") != "validated"
        ]
        _write_json(
            output_dir / "acceptance.json",
            {
                "schema_version": self._adapter.evidence_contract.acceptance_schema_version,
                "status": "accepted",
                "authorization": auth_record,
                "qualification": {
                    "status": release.qualification.get("status"),
                    "effective_qualification": release.qualification.get(
                        "effective_qualification"
                    ),
                    "publishable": release.qualification["claims"].get("publishable"),
                    "training_recommended": release.qualification["claims"].get(
                        "training_recommended"
                    ),
                },
                "mutation_judge_preflight": dict(mutation_judge_preflight or {}),
                "provider_evidence": {
                    "path": "trace/provider.json",
                    "evidence_class": provider_evidence["evidence_class"],
                    "logical_calls": provider_evidence["usage"]["logical_calls"],
                    "replayable_calls": provider_evidence["usage"]["replayable_calls"],
                    "non_accepted_attempt_count": len(non_accepted),
                    "usage": provider_evidence["usage"],
                    "cost": provider_evidence["cost"],
                },
                "replay": dict(replay),
                "artifacts": {
                    "replay_report": release.replay_report_path.name,
                    "evaluation_report": release.evaluation_report_path.name,
                    "profile_decision_report": release.profile_decision_path.name,
                    "dataset_release_report": release.dataset_release_report_path.name,
                    "release_quality_audit": release.release_quality_audit_path.name,
                    "release_pack": release.release_pack_path.name,
                },
            },
        )
        proof_path = self._adapter.build_proof(
            proof_root=proof_root,
            acceptance_dir=output_dir,
        )
        proof_result = self._adapter.verify_proof(proof_path)
        if proof_result.get("status") != "passed":
            raise self._error_for_reason("acceptance_proof_failed")
        return AcceptanceRunResult(
            acceptance_dir=output_dir,
            proof_path=proof_path,
            provider_evidence_path=self._adapter.provider_evidence_path(
                proof_path=proof_path,
                acceptance_dir=output_dir,
            ),
            replay=replay,
            qualification=release.qualification,
        )


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "AcceptanceAuthorization",
    "ACCEPTANCE_RUN_BINDING_KEYS",
    "AcceptanceEvidenceRecorder",
    "AcceptancePipelineResult",
    "AcceptancePreparation",
    "AcceptanceReleaseEvidence",
    "AcceptanceReplayAdapter",
    "AcceptanceReplayContract",
    "AcceptanceReplayError",
    "AcceptanceReplayHarness",
    "AcceptanceRunResult",
    "AcceptanceUsageObserver",
    "BoundedSanitizedProvider",
    "CoverageAssignmentEvidenceObserver",
    "DEFAULT_ACCEPTANCE_REPLAY_CONTRACT",
    "MAX_GENERATOR_RETRIES",
    "PROVIDER_PARSER_VERSION",
    "SANITIZED_EVIDENCE_POLICY_VERSION",
    "SanitizedMutationJudgeUsageObserver",
    "SanitizedProviderEvidenceRecorder",
    "bounded_judge_failure_class",
    "bounded_reason",
    "bounded_retry_count",
    "bounded_usage",
    "build_coverage_attempt_observer_factory",
    "hash_value",
    "load_provider_evidence",
    "replay_frozen_provider_evidence",
    "sanitize_provider_response",
    "sum_usage",
    "validate_provider_evidence",
]
