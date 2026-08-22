"""Authorization and replay contracts for the live Workspace acceptance run.

The live acceptance boundary is intentionally separate from the deterministic
Workspace tracer.  It may record only the narrow provider task-contract JSON
needed to replay production parsing and membership admission.  Prompts,
provider envelopes, credentials, and unrestricted source material never cross
the freeze boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse


LIVE_ACCEPTANCE_SCHEMA_VERSION = "workspace_live_acceptance_v1"
LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION = "workspace_live_provider_evidence_v1"
SANITIZED_EVIDENCE_POLICY_VERSION = "workspace_sanitized_provider_evidence_v1"
PROVIDER_PARSER_VERSION = "domain_generation_parser_v1"

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONFIG_HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,239}$")
_AUTHORIZATION_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
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


class LiveWorkspaceAcceptanceError(ValueError):
    """A bounded failure at the authorized live-provider boundary."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


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
        raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable") from exc


def _hash_value(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_hash(value: object, reason: str = "live_evidence_malformed") -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise LiveWorkspaceAcceptanceError(reason)
    return value


def _require_identifier(value: object, reason: str = "live_evidence_malformed") -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise LiveWorkspaceAcceptanceError(reason)
    return value


def _sanitize_json_value(value: object, *, depth: int = 0) -> object:
    if depth > 12:
        raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
    if isinstance(value, str):
        if len(value) > 4096 or any(pattern.search(value) for pattern in _UNSAFE_STRING_PATTERNS):
            raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
        return value
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_KEYS:
                raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
            sanitized[key] = _sanitize_json_value(child, depth=depth + 1)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 100:
            raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
        return [_sanitize_json_value(child, depth=depth + 1) for child in value]
    raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")


def sanitize_provider_response(response: object) -> dict[str, object]:
    """Return only the bounded provider task-contract response shape.

    This function deliberately does not repair or normalize a response.  A
    response outside the production provider contract is not a replay input.
    """

    if not isinstance(response, Mapping) or set(response) != {"task_contracts"}:
        raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
    task_contracts = response.get("task_contracts")
    if not isinstance(task_contracts, list) or len(task_contracts) > 5:
        raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
    sanitized_contracts: list[dict[str, object]] = []
    for raw_contract in task_contracts:
        if not isinstance(raw_contract, Mapping) or set(raw_contract) != _PROVIDER_RECORD_KEYS:
            raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
        sanitized = _sanitize_json_value(raw_contract)
        if not isinstance(sanitized, Mapping):
            raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
        sanitized_contracts.append(dict(sanitized))
    result = {"task_contracts": sanitized_contracts}
    if len(_canonical_bytes(result)) > 256 * 1024:
        raise LiveWorkspaceAcceptanceError("provider_response_not_sanitizable")
    return result


@dataclass(frozen=True)
class LiveWorkspaceAcceptanceAuthorization:
    """The operator's explicit, bounded authorization envelope."""

    approved: bool
    authorization_id: str
    candidate_budget: int
    attempt_budget: int
    generator_provider: str
    generator_model: str
    mutation_judge_provider: str
    mutation_judge_model: str
    evidence_policy: str = SANITIZED_EVIDENCE_POLICY_VERSION

    def validate(
        self,
        *,
        profile: Mapping[str, object],
        plan_attempt_ceiling: int,
    ) -> None:
        if not self.approved:
            raise LiveWorkspaceAcceptanceError("live_provider_authorization_required")
        if _AUTHORIZATION_ID_RE.fullmatch(self.authorization_id) is None:
            raise LiveWorkspaceAcceptanceError("authorization_identity_invalid")
        if self.evidence_policy != SANITIZED_EVIDENCE_POLICY_VERSION:
            raise LiveWorkspaceAcceptanceError("sanitized_evidence_policy_required")
        for value in (self.candidate_budget, self.attempt_budget):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
        if not isinstance(plan_attempt_ceiling, int) or plan_attempt_ceiling <= 0:
            raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
        if plan_attempt_ceiling > self.attempt_budget:
            raise LiveWorkspaceAcceptanceError("attempt_budget_exceeded")
        generation = profile.get("generation")
        seed = profile.get("seed")
        mutation = profile.get("mutation_admission")
        coverage = profile.get("coverage_profile")
        features = profile.get("features")
        if (
            profile.get("schema_version") != "run_profile_v4"
            or profile.get("profile_id") != "workspace_tasks_live_acceptance_rc"
            or profile.get("dataset_version")
            != "dataset_workspace_tasks_live_acceptance_rc_v1"
            or profile.get("profile_purpose") != "release_candidate"
            or not isinstance(generation, Mapping)
            or generation.get("mode") != "llm"
            or generation.get("target_candidate_count") != 24
            or not isinstance(seed, Mapping)
            or seed.get("domain") != "workspace_tasks_fixture"
            or seed.get("seed_id") != "seed_workspace_tasks_live_acceptance_rc_v1"
            or seed.get("task_taxonomy")
            != [
                "workspace_item_search",
                "workspace_task_creation",
                "workspace_comment_update",
            ]
            or not isinstance(coverage, Mapping)
            or coverage.get("profile_id") != "workspace_tasks_representative"
            or coverage.get("version") != "workspace_tasks_representative_v1"
            or coverage.get("target_accepted_sample_count") != 12
            or not isinstance(features, Mapping)
            or features.get("enable_branching") is not True
            or not isinstance(mutation, Mapping)
            or mutation.get("mode") != "enforce"
        ):
            raise LiveWorkspaceAcceptanceError("live_workspace_profile_invalid")
        target = generation.get("target_candidate_count")
        if (
            not isinstance(target, int)
            or isinstance(target, bool)
            or target <= 0
            or target > self.candidate_budget
        ):
            raise LiveWorkspaceAcceptanceError("candidate_budget_exceeded")
        judge = mutation.get("judge")
        if not isinstance(judge, Mapping):
            raise LiveWorkspaceAcceptanceError("mutation_judge_identity_required")
        if (
            self.generator_provider != "openai_compatible"
            or self.mutation_judge_provider != "openai_compatible"
            or judge.get("provider") != self.mutation_judge_provider
            or judge.get("role") != "mutation_admission_judge"
            or judge.get("model") != self.mutation_judge_model
            or not isinstance(self.generator_model, str)
            or _IDENTIFIER_RE.fullmatch(self.generator_model) is None
            or not isinstance(self.mutation_judge_model, str)
            or _IDENTIFIER_RE.fullmatch(self.mutation_judge_model) is None
            or self.generator_model == self.mutation_judge_model
        ):
            raise LiveWorkspaceAcceptanceError("mutation_judge_identity_not_independent")

    def to_record(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "authorization_id": self.authorization_id,
            "candidate_budget": self.candidate_budget,
            "attempt_budget": self.attempt_budget,
            "generator_provider": self.generator_provider,
            "generator_model": self.generator_model,
            "mutation_judge_provider": self.mutation_judge_provider,
            "mutation_judge_model": self.mutation_judge_model,
            "evidence_policy": self.evidence_policy,
        }


def _bounded_usage(value: object) -> dict[str, int]:
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


def _sum_usage(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for record in records:
        usage = record.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for key, value in _bounded_usage(usage).items():
            totals[key] = totals.get(key, 0) + value
    return dict(sorted(totals.items()))


class SanitizedProviderEvidenceRecorder:
    """Capture sanitized provider attempts and freeze them after qualification."""

    def __init__(
        self,
        *,
        authorization: LiveWorkspaceAcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> None:
        self.authorization = authorization
        safe_provider_identity = _sanitize_json_value(provider_identity)
        safe_judge_identity = _sanitize_json_value(mutation_judge_identity)
        if not isinstance(safe_provider_identity, Mapping) or not isinstance(
            safe_judge_identity, Mapping
        ):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
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
            raise LiveWorkspaceAcceptanceError("live_evidence_already_frozen")
        _require_hash(request_hash)
        if not isinstance(assignment, Mapping):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        if not isinstance(assignment.get("assignment_id"), str):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        safe_assignment = _sanitize_json_value(assignment)
        safe_lineage = _sanitize_json_value(
            assignment_lineage if assignment_lineage is not None else assignment
        )
        if not isinstance(safe_assignment, Mapping) or not isinstance(
            safe_lineage, Mapping
        ):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        self._pending_assignments[request_hash] = dict(safe_assignment)
        self._pending_assignment_lineages[request_hash] = dict(safe_lineage)

    def bind_sample_assignments(
        self,
        assignments_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Bind accepted sample assignments without replacing issued lineage."""

        for record in self._attempts:
            assignment_id = record.get("assignment_id")
            assignment = assignments_by_id.get(str(assignment_id))
            current_assignment = record.get("assignment")
            if (
                assignment is not None
                and (
                    not isinstance(current_assignment, Mapping)
                    or "task_type" not in current_assignment
                )
            ):
                record["assignment"] = dict(assignment)

    def set_mutation_judge_usage(self, usage: Mapping[str, object]) -> None:
        self._mutation_judge_usage = {
            "attempts": int(usage.get("attempts", 0))
            if isinstance(usage.get("attempts"), int)
            and not isinstance(usage.get("attempts"), bool)
            else 0,
            "tokens": _bounded_usage(usage.get("tokens")),
            "outcomes": dict(usage.get("outcomes", {}))
            if isinstance(usage.get("outcomes"), Mapping)
            else {},
        }

    def _assignment_for_request(self, request_hash: str) -> dict[str, object]:
        assignment = self._pending_assignments.pop(request_hash, None)
        if assignment is not None:
            return assignment
        return {"assignment_id": f"unbound_{request_hash.removeprefix('sha256:')[:16]}"}

    def _find_attempt(self, assignment_id: str) -> dict[str, object] | None:
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
        record = self._find_attempt(assignment_id)
        if record is None:
            raise LiveWorkspaceAcceptanceError("live_evidence_assignment_missing")
        if outcome not in {"provider_error", "rejected", "validated"}:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        record["outcome"] = outcome
        if reason_code is not None:
            record["reason_code"] = reason_code

    def record_generation_rejection(
        self,
        assignment: object,
        rejection: Mapping[str, object],
    ) -> None:
        assignment_id = assignment.lineage().get("assignment_id")
        if not isinstance(assignment_id, str):
            raise LiveWorkspaceAcceptanceError("live_evidence_assignment_missing")
        details = rejection.get("details") if isinstance(rejection, Mapping) else None
        reason = None
        if isinstance(details, Mapping):
            for key in ("schema_reason", "reason_code", "cause"):
                candidate = details.get(key)
                if isinstance(candidate, str):
                    reason = candidate
                    break
        if reason is None and isinstance(rejection.get("cause"), str):
            reason = str(rejection["cause"])
        existing = self._find_attempt(assignment_id)
        if existing is not None and existing.get("outcome") == "provider_error":
            existing.setdefault("reason_code", _bounded_reason(reason))
            return
        self.mark_attempt(
            assignment_id=assignment_id,
            outcome="rejected",
            reason_code=_bounded_reason(reason),
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
            raise LiveWorkspaceAcceptanceError("live_evidence_already_frozen")
        if not isinstance(assignment, Mapping):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        assignment_id = assignment.get("assignment_id")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        safe_assignment = _sanitize_json_value(assignment)
        if not isinstance(safe_assignment, Mapping):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        _require_hash(request_hash)
        if outcome not in {"provider_error", "rejected", "validated"}:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        sanitized_response: dict[str, object] | None = None
        computed_response_hash: str | None = None
        if response is not None:
            sanitized_response = sanitize_provider_response(response)
            computed_response_hash = _hash_value(sanitized_response)
            if response_hash is not None and response_hash != computed_response_hash:
                raise LiveWorkspaceAcceptanceError("live_evidence_identity_mismatch")
        elif response_hash is not None:
            _require_hash(response_hash, "live_evidence_identity_mismatch")
        record: dict[str, object] = {
            "attempt_id": f"live_provider_attempt_{len(self._attempts) + 1:04d}",
            "assignment_id": assignment_id,
            "assignment": dict(safe_assignment),
            "assignment_lineage": dict(safe_assignment),
            "request_hash": request_hash,
            "response": sanitized_response,
            "response_hash": computed_response_hash,
            "parser_version": PROVIDER_PARSER_VERSION,
            "outcome": outcome,
            "usage": _bounded_usage(usage),
            "retry_count": retry_count,
        }
        if reason_code is not None:
            if not isinstance(reason_code, str) or not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", reason_code):
                raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
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
            raise LiveWorkspaceAcceptanceError("live_evidence_already_frozen")
        if (
            qualification.get("status") != "passed"
            or qualification.get("effective_qualification") != "release_candidate"
            or not isinstance(qualification.get("claims"), Mapping)
            or qualification["claims"].get("publishable") is not False
            or qualification["claims"].get("training_recommended") is not False
        ):
            raise LiveWorkspaceAcceptanceError("real_release_candidate_not_verified")
        if release_pack_verification.get("status") != "passed":
            raise LiveWorkspaceAcceptanceError("release_pack_not_independently_verified")
        _require_hash(release_pack_hash)
        if not self._attempts:
            raise LiveWorkspaceAcceptanceError("live_evidence_missing")
        if not isinstance(run_binding, Mapping):
            raise LiveWorkspaceAcceptanceError("live_run_binding_missing")
        safe_run_binding = _sanitize_json_value(run_binding)
        if not isinstance(safe_run_binding, Mapping):
            raise LiveWorkspaceAcceptanceError("live_run_binding_malformed")
        replay_attempts = [
            record
            for record in self._attempts
            if record.get("outcome") == "validated"
            and isinstance(record.get("response"), Mapping)
            and isinstance(record.get("response_hash"), str)
        ]
        if not replay_attempts:
            raise LiveWorkspaceAcceptanceError("live_replay_inputs_missing")
        records = [dict(record) for record in self._attempts]
        evidence: dict[str, object] = {
            "schema_version": LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION,
            "evidence_class": "real_live",
            "frozen": True,
            "freeze_policy": SANITIZED_EVIDENCE_POLICY_VERSION,
            "authorization": self.authorization.to_record(),
            "provider": dict(self.provider_identity),
            "mutation_judge": dict(self.mutation_judge_identity),
            "run_binding": dict(safe_run_binding),
            "attempts": records,
            "replay_attempts": [dict(record) for record in replay_attempts],
            "usage": {
                "logical_calls": len(records),
                "replayable_calls": len(replay_attempts),
                "tokens": _sum_usage(records),
                "retries": sum(
                    int(record.get("retry_count", 0))
                    for record in records
                    if isinstance(record.get("retry_count"), int)
                    and not isinstance(record.get("retry_count"), bool)
                ),
            },
            "mutation_judge_usage": dict(self._mutation_judge_usage),
            "cost": {
                "status": "not_reported",
                "amount": None,
                "currency": None,
            },
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
    """Record bounded judge usage without retaining judge prompts or payloads."""

    def __init__(self) -> None:
        self._attempts: list[dict[str, object]] = []

    def before_provider_call(self, *, prompt_hash: str) -> str:
        _require_hash(prompt_hash)
        attempt_id = f"live_mutation_judge_attempt_{len(self._attempts) + 1:04d}"
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
        record["usage"] = _bounded_usage(lineage.get("tokens"))

    def provider_attempt_failed(
        self,
        *,
        attempt_id: object,
        error: BaseException,
    ) -> None:
        record = self._find(attempt_id)
        record["outcome"] = "provider_error"
        cause = getattr(error, "cause", None)
        record["reason_code"] = (
            cause
            if isinstance(cause, str) and re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", cause)
            else "llm_provider_error"
        )

    def _find(self, attempt_id: object) -> dict[str, object]:
        for record in self._attempts:
            if record.get("attempt_id") == attempt_id:
                return record
        raise LiveWorkspaceAcceptanceError("live_judge_attempt_missing")

    def to_record(self) -> dict[str, object]:
        return {
            "attempts": len(self._attempts),
            "tokens": _sum_usage(self._attempts),
            "outcomes": {
                outcome: sum(record.get("outcome") == outcome for record in self._attempts)
                for outcome in sorted({str(record.get("outcome")) for record in self._attempts})
            },
        }


class BoundedSanitizedProvider:
    """Provider adapter that records only sanitized generation responses."""

    def __init__(
        self,
        delegate: object,
        *,
        recorder: SanitizedProviderEvidenceRecorder,
        max_logical_calls: int,
    ) -> None:
        if not isinstance(max_logical_calls, int) or isinstance(max_logical_calls, bool) or max_logical_calls <= 0:
            raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
        self._delegate = delegate
        self._recorder = recorder
        self._max_logical_calls = max_logical_calls
        self._logical_calls = 0

    @property
    def logical_calls(self) -> int:
        return self._logical_calls

    def generate_json(self, prompt: str, *, role: str) -> Any:
        from synthesis.llm import LLMProviderError

        if not isinstance(prompt, str) or not prompt:
            raise LiveWorkspaceAcceptanceError("provider_request_invalid")
        if role != "task_generation":
            raise LiveWorkspaceAcceptanceError("provider_role_invalid")
        request_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        assignment = self._recorder._assignment_for_request(request_hash)
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
                reason_code=_bounded_reason(getattr(exc, "cause", None)),
                usage=_bounded_usage(lineage.get("tokens")),
                retry_count=_bounded_retry_count(getattr(exc, "retry_count", 0)),
            )
            raise
        content = getattr(result, "content", None)
        lineage = getattr(result, "lineage", {})
        safe_response: Mapping[str, object] | None
        response_hash: str | None
        try:
            safe_response = sanitize_provider_response(content)
            response_hash = _hash_value(safe_response)
        except LiveWorkspaceAcceptanceError:
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
            retry_count=_bounded_retry_count(
                lineage.get("retry_count", 0) if isinstance(lineage, Mapping) else 0
            ),
        )
        return result

def _bounded_retry_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _bounded_reason(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", value):
        return value
    return "llm_provider_error"


def _normalize_prompt_hash(value: object) -> str:
    if isinstance(value, str) and _HASH_RE.fullmatch(value):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
        return "sha256:" + value
    raise LiveWorkspaceAcceptanceError("live_evidence_malformed")


class CoverageAssignmentEvidenceObserver:
    """Bridge production coverage-attempt callbacks into the recorder."""

    def __init__(self, recorder: SanitizedProviderEvidenceRecorder) -> None:
        self._recorder = recorder
        self._assignment_ids: dict[str, str] = {}

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
            raise LiveWorkspaceAcceptanceError("live_evidence_assignment_missing")
        request_hash = _normalize_prompt_hash(prompt_hash)
        self._assignment_ids[request_hash] = assignment_id
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
            record = self._recorder._find_attempt(assignment_id)
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
                reason_code=_bounded_reason(getattr(error, "cause", None)),
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
) -> object:
    """Return the factory shape accepted by the production coverage scheduler."""

    def factory(assignment: object) -> CoverageAssignmentEvidenceObserver:
        del assignment
        return CoverageAssignmentEvidenceObserver(recorder)

    return factory


def validate_live_provider_evidence(
    evidence: Mapping[str, object],
) -> None:
    """Validate a frozen live evidence file before any production replay."""

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
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    if (
        evidence.get("schema_version") != LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION
        or evidence.get("evidence_class") != "real_live"
        or evidence.get("frozen") is not True
        or evidence.get("freeze_policy") != SANITIZED_EVIDENCE_POLICY_VERSION
    ):
        raise LiveWorkspaceAcceptanceError("live_evidence_identity_mismatch")
    authorization = evidence.get("authorization")
    if not isinstance(authorization, Mapping) or authorization.get("approved") is not True:
        raise LiveWorkspaceAcceptanceError("live_provider_authorization_required")
    provider = evidence.get("provider")
    judge = evidence.get("mutation_judge")
    if not isinstance(provider, Mapping) or not isinstance(judge, Mapping):
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    if set(provider) != {
        "provider_id",
        "provider_version",
        "provider_host",
        "model",
        "config_hash",
        "parser_version",
    } or set(judge) != {
        "provider",
        "provider_host",
        "model",
        "config_hash",
        "role",
        "role_version",
    }:
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    try:
        _sanitize_json_value(provider)
        _sanitize_json_value(judge)
    except LiveWorkspaceAcceptanceError:
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed") from None
    for identity in (provider, judge):
        if any(
            not isinstance(identity.get(key), str) or not identity.get(key)
            for key in identity
            if key != "config_hash"
        ) or _CONFIG_HASH_RE.fullmatch(str(identity.get("config_hash", ""))) is None:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    if provider.get("model") == judge.get("model"):
        raise LiveWorkspaceAcceptanceError("mutation_judge_identity_not_independent")
    authorization = evidence.get("authorization")
    if (
        not isinstance(authorization, Mapping)
        or authorization.get("approved") is not True
        or authorization.get("generator_provider") != provider.get("provider_id")
        or authorization.get("generator_model") != provider.get("model")
        or authorization.get("mutation_judge_provider") != judge.get("provider")
        or authorization.get("mutation_judge_model") != judge.get("model")
    ):
        raise LiveWorkspaceAcceptanceError("live_identity_binding_mismatch")
    run_binding = evidence.get("run_binding")
    if not isinstance(run_binding, Mapping):
        raise LiveWorkspaceAcceptanceError("live_run_binding_malformed")
    required_binding_keys = {
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
    if set(run_binding) != required_binding_keys:
        raise LiveWorkspaceAcceptanceError("live_run_binding_malformed")
    for key in (
        "profile_id",
        "dataset_version",
        "seed_id",
        "seed_domain",
        "plan_id",
        "coverage_plan_id",
    ):
        if not isinstance(run_binding.get(key), str) or not run_binding.get(key):
            raise LiveWorkspaceAcceptanceError("live_run_binding_malformed")
    for key in ("plan_hash", "coverage_plan_hash", "source_policy_hash"):
        _require_hash(run_binding.get(key), "live_run_binding_malformed")
    attempts = evidence.get("attempts")
    replay_attempts = evidence.get("replay_attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(replay_attempts, list):
        raise LiveWorkspaceAcceptanceError("live_evidence_missing")
    attempt_by_id: dict[str, Mapping[str, object]] = {}
    for raw_attempt in attempts:
        if not isinstance(raw_attempt, Mapping):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
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
        if not set(raw_attempt) <= allowed_attempt_keys:
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        attempt_id = raw_attempt.get("attempt_id")
        assignment_id = raw_attempt.get("assignment_id")
        if (
            not isinstance(attempt_id, str)
            or _IDENTIFIER_RE.fullmatch(attempt_id) is None
            or not isinstance(assignment_id, str)
            or _IDENTIFIER_RE.fullmatch(assignment_id) is None
            or attempt_id in attempt_by_id
            or not _HASH_RE.fullmatch(str(raw_attempt.get("request_hash", "")))
            or raw_attempt.get("parser_version") != PROVIDER_PARSER_VERSION
            or raw_attempt.get("outcome")
            not in {"provider_error", "rejected", "validated"}
            or not isinstance(raw_attempt.get("assignment"), Mapping)
            or not isinstance(raw_attempt.get("assignment_lineage"), Mapping)
            or raw_attempt["assignment"].get("assignment_id") != assignment_id
            or raw_attempt["assignment_lineage"].get("assignment_id")
            != assignment_id
            or not isinstance(raw_attempt.get("usage"), Mapping)
            or not isinstance(raw_attempt.get("retry_count"), int)
            or isinstance(raw_attempt.get("retry_count"), bool)
            or raw_attempt.get("retry_count") < 0
        ):
            raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
        response = raw_attempt.get("response")
        response_hash = raw_attempt.get("response_hash")
        if response is not None:
            sanitized = sanitize_provider_response(response)
            if response_hash != _hash_value(sanitized):
                raise LiveWorkspaceAcceptanceError("live_evidence_identity_mismatch")
        elif response_hash is not None:
            _require_hash(response_hash, "live_evidence_identity_mismatch")
        elif raw_attempt.get("outcome") == "validated":
            raise LiveWorkspaceAcceptanceError("live_replay_input_malformed")
        attempt_by_id[attempt_id] = raw_attempt
    if (
        provider.get("provider_id") != "openai_compatible"
        or provider.get("provider_version") != "openai_compatible_client_v1"
        or provider.get("parser_version") != PROVIDER_PARSER_VERSION
        or judge.get("provider") != "openai_compatible"
        or judge.get("role") != "mutation_admission_judge"
        or judge.get("role_version") != "role_mutation_admission_judge_v1"
    ):
        raise LiveWorkspaceAcceptanceError("live_provider_identity_mismatch")
    replay_ids: set[str] = set()
    for raw_attempt in replay_attempts:
        if not isinstance(raw_attempt, Mapping):
            raise LiveWorkspaceAcceptanceError("live_replay_input_malformed")
        attempt_id = raw_attempt.get("attempt_id")
        if not isinstance(attempt_id, str) or attempt_id in replay_ids:
            raise LiveWorkspaceAcceptanceError("live_replay_input_malformed")
        source = attempt_by_id.get(attempt_id)
        if source is None or source.get("outcome") != "validated":
            raise LiveWorkspaceAcceptanceError("live_replay_input_mismatch")
        if raw_attempt.get("response") != source.get("response") or raw_attempt.get("response_hash") != source.get("response_hash"):
            raise LiveWorkspaceAcceptanceError("live_replay_input_mismatch")
        replay_ids.add(attempt_id)
    if not replay_ids:
        raise LiveWorkspaceAcceptanceError("live_replay_inputs_missing")
    usage = evidence.get("usage")
    if (
        not isinstance(usage, Mapping)
        or usage.get("logical_calls") != len(attempts)
        or usage.get("replayable_calls") != len(replay_attempts)
        or not isinstance(usage.get("tokens"), Mapping)
    ):
        raise LiveWorkspaceAcceptanceError("live_usage_malformed")
    cost = evidence.get("cost")
    if (
        not isinstance(cost, Mapping)
        or cost.get("status") != "not_reported"
        or cost.get("amount") is not None
        or cost.get("currency") is not None
    ):
        raise LiveWorkspaceAcceptanceError("live_cost_malformed")
    qualification = evidence.get("qualification")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("effective_qualification") != "release_candidate"
        or qualification.get("release_pack_verification_status") != "passed"
        or not _HASH_RE.fullmatch(str(qualification.get("release_pack_hash", "")))
    ):
        raise LiveWorkspaceAcceptanceError("real_release_candidate_not_verified")


def load_live_provider_evidence(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveWorkspaceAcceptanceError("live_evidence_unreadable") from exc
    if not isinstance(value, Mapping):
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    validate_live_provider_evidence(value)
    return dict(value)


def replay_sanitized_provider_evidence(
    evidence: Mapping[str, object] | Path,
    *,
    plan: object,
    seed: object,
    environment_path: Path,
) -> dict[str, object]:
    """Replay frozen responses through the production parser and membership gate.

    The implementation intentionally constructs no provider client.  Runtime
    execution and episode verification remain the production replay contracts;
    this seam verifies the provider-input half of that chain.
    """

    if isinstance(evidence, Path):
        loaded = load_live_provider_evidence(evidence)
    elif isinstance(evidence, Mapping):
        validate_live_provider_evidence(evidence)
        loaded = dict(evidence)
    else:
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    if not environment_path.is_file() or environment_path.is_symlink():
        raise LiveWorkspaceAcceptanceError("live_replay_environment_missing")
    from synthesis.workspace_tracer import replay_provider_attempts

    try:
        replayed = replay_provider_attempts(
            root_dir=environment_path.parent,
            artifacts={"workspace_environment": {"path": environment_path.name}},
            anchors={"workspace_environment": "workspace_environment"},
            plan=plan,
            seed=seed,
            provider=loaded,
            assignment_evidence={
                "assignments": [
                    dict(attempt["assignment_lineage"])
                    for attempt in loaded["replay_attempts"]
                    if isinstance(attempt, Mapping)
                    and isinstance(attempt.get("assignment_lineage"), Mapping)
                ],
                "assignment_contracts": [
                    dict(attempt["assignment"])
                    for attempt in loaded["replay_attempts"]
                    if isinstance(attempt, Mapping)
                    and isinstance(attempt.get("assignment"), Mapping)
                ],
            },
        )
    except Exception as exc:
        raise LiveWorkspaceAcceptanceError("live_replay_contract_failed") from exc
    expected = len(loaded["replay_attempts"])
    if replayed != expected:
        raise LiveWorkspaceAcceptanceError("live_replay_count_mismatch")
    return {
        "schema_version": "workspace_live_replay_result_v1",
        "status": "passed",
        "reason_code": "replay_verified",
        "replayed_attempt_count": replayed,
        "provider_calls": 0,
        "evidence_class": "real_live",
    }


@dataclass(frozen=True)
class LiveWorkspaceAcceptanceResult:
    acceptance_dir: Path
    proof_path: Path
    provider_evidence_path: Path
    replay: Mapping[str, object]
    qualification: Mapping[str, object]


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveWorkspaceAcceptanceError("live_artifact_unreadable") from exc
    if not isinstance(value, Mapping):
        raise LiveWorkspaceAcceptanceError("live_artifact_malformed")
    return dict(value)


def _ensure_empty_directory(path: Path, reason: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise LiveWorkspaceAcceptanceError(reason)
    path.mkdir(parents=True, exist_ok=True)


def _profile_seed(profile: object) -> object:
    return profile.seed


def _build_live_plan_and_coverage(profile: object, output_dir: Path) -> tuple[object, object, object]:
    from synthesis.domain_pack import DomainPlan, PlanFailure
    from synthesis.domain_sources import build_domain_fixture_source_bundle
    from synthesis.sources import validate_source_bundle
    from synthesis.workspace_domain_pack import (
        admitted_workspace_source,
        build_workspace_domain_pack,
        workspace_planning_intent,
    )
    from synthesis.pipeline import preview_coverage_plan

    source_bundle = build_domain_fixture_source_bundle(profile.seed.domain)
    source_result = validate_source_bundle(source_bundle)
    pack = build_workspace_domain_pack()
    admitted_source = admitted_workspace_source(source_bundle, source_result)
    plan = pack.plan(workspace_planning_intent(pack), admitted_source)
    if isinstance(plan, PlanFailure) or not isinstance(plan, DomainPlan):
        raise LiveWorkspaceAcceptanceError("workspace_plan_not_admitted")
    coverage_plan = preview_coverage_plan(profile)
    _write_json(output_dir / "coverage_plan_preflight.json", coverage_plan.canonical())
    return plan, coverage_plan, source_result


def _generator_identity(config: object) -> dict[str, object]:
    lineage = config.lineage("task_generation")
    return {
        "provider_id": "openai_compatible",
        "provider_version": "openai_compatible_client_v1",
        "provider_host": _safe_provider_host(config.base_url),
        "model": config.model,
        "config_hash": lineage["config_hash"],
        "parser_version": PROVIDER_PARSER_VERSION,
    }


def _mutation_judge_identity(profile: object, config: object) -> dict[str, object]:
    from synthesis.llm import LLMConfig

    judge = profile.mutation_admission.judge
    judge_config = LLMConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        model=judge.model,
        temperature=0.0,
    )
    lineage = judge_config.lineage("mutation_admission_judge")
    return {
        "provider": judge.provider,
        "provider_host": _safe_provider_host(judge_config.base_url),
        "model": judge.model,
        "config_hash": lineage["config_hash"],
        "role": judge.role,
        "role_version": "role_mutation_admission_judge_v1",
    }


def _safe_provider_host(base_url: object) -> str:
    if not isinstance(base_url, str) or not base_url:
        return "unconfigured"
    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if hostname is None:
        return "unconfigured"
    try:
        port = parsed.port
    except ValueError:
        return "unconfigured"
    return f"{hostname}:{port}" if port is not None else hostname


def _environment_path(output_dir: Path) -> Path:
    candidates = (
        output_dir / "environment" / "workspace_tasks.sqlite3",
        output_dir / "workspace_tasks.sqlite3",
    )
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            return path
    raise LiveWorkspaceAcceptanceError("live_replay_environment_missing")


def _write_live_pipeline_reports(
    *,
    output_dir: Path,
    profile: object,
    result: object,
    runtime_seconds: float,
) -> tuple[Path, Path, Path, Path, Path, Path, dict[str, object]]:
    from synthesis.datasets import (
        attach_dataset_release_pack_to_manifest,
        attach_dataset_release_report_to_manifest,
        attach_episode_replay_report_to_manifest,
        attach_evaluation_report_to_manifest,
        attach_profile_decision_report_to_manifest,
        attach_release_quality_audit_to_manifest,
    )
    from synthesis.dataset_release import write_dataset_release_report
    from synthesis.episode_replay import write_episode_replay_report
    from synthesis.episode_quality import read_episode_logs
    from synthesis.evaluation import write_evaluation_report
    from synthesis.profile_decisions import write_profile_decision_report
    from synthesis.qualification import write_workspace_release_candidate_qualification
    from synthesis.release_pack import verify_dataset_release_pack, write_dataset_release_pack
    from synthesis.release_quality import write_release_quality_audit

    if result.episode_logs_path is None or result.coverage_evidence_path is None:
        raise LiveWorkspaceAcceptanceError("run_completeness")
    episodes = read_episode_logs(result.episode_logs_path)
    replay_path = write_episode_replay_report(
        output_dir / "episode_replay_report.json",
        dataset_version=profile.dataset_version,
        episodes=episodes,
        manifest_path=result.manifest_path,
        episodes_path=result.episode_logs_path,
    )
    attach_episode_replay_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=replay_path,
    )
    evaluation_path = write_evaluation_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
    )
    attach_evaluation_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=evaluation_path,
    )
    profile_decision_path = write_profile_decision_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        runtime_seconds=runtime_seconds,
    )
    attach_profile_decision_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=profile_decision_path,
    )
    dataset_release_report_path = write_dataset_release_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        profile_decision_report_path=profile_decision_path,
    )
    attach_dataset_release_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=dataset_release_report_path,
    )
    audit_path = write_release_quality_audit(
        manifest_path=result.manifest_path,
        output_path=output_dir / "release_quality_audit.json",
    )
    attach_release_quality_audit_to_manifest(
        manifest_path=result.manifest_path,
        audit_path=audit_path,
    )
    pack_path = output_dir / "dataset_release_pack.json"
    attach_dataset_release_pack_to_manifest(
        manifest_path=result.manifest_path,
        pack_path=pack_path,
    )
    write_dataset_release_pack(
        manifest_path=result.manifest_path,
        dataset_release_report_path=dataset_release_report_path,
        output_path=pack_path,
    )
    pack_verification = verify_dataset_release_pack(pack_path)
    verification = pack_verification.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "passed":
        raise LiveWorkspaceAcceptanceError("release_pack_not_independently_verified")
    _write_json(output_dir / "release_pack_verification.json", pack_verification)
    qualification_path = output_dir / "qualification_report.json"
    write_workspace_release_candidate_qualification(
        manifest_path=result.manifest_path,
        release_pack_path=pack_path,
        release_quality_audit_path=audit_path,
        output_path=qualification_path,
    )
    return (
        replay_path,
        evaluation_path,
        profile_decision_path,
        dataset_release_report_path,
        audit_path,
        pack_path,
        _load_json(qualification_path),
    )


def run_live_workspace_acceptance(
    output_dir: Path,
    *,
    profile: object,
    authorization: LiveWorkspaceAcceptanceAuthorization,
    generator_config: object | None = None,
    generator_http_client: object | None = None,
    mutation_judge_http_client: object | None = None,
    proof_root: Path | None = None,
    max_generator_retries: int = 2,
) -> LiveWorkspaceAcceptanceResult:
    """Run and freeze one explicitly authorized live Workspace acceptance.

    The caller must provide a release-candidate profile and an authorization
    envelope.  No provider client is created until the exact Domain plan,
    coverage plan, identity checks, and spending bounds have passed.
    """

    from synthesis.llm import LLMConfig, LLMConfigurationError, OpenAICompatibleClient
    from synthesis.coverage_assignments import build_coverage_assignment_scheduler_factory
    from synthesis.pipeline import run_foundation_pipeline

    output_dir = Path(output_dir)
    proof_root = Path(proof_root) if proof_root is not None else output_dir.parent / (output_dir.name + "-tracer-proof")
    _ensure_empty_directory(output_dir, "live_acceptance_output_not_empty")
    _ensure_empty_directory(proof_root, "live_proof_output_not_empty")
    if max_generator_retries not in {0, 1, 2}:
        raise LiveWorkspaceAcceptanceError("generator_retry_budget_invalid")
    if not hasattr(profile, "canonical") or not hasattr(profile, "seed"):
        raise LiveWorkspaceAcceptanceError("live_workspace_profile_invalid")
    plan, coverage_plan, source_result = _build_live_plan_and_coverage(profile, output_dir)
    profile_record = profile.canonical()
    authorization.validate(
        profile=profile_record,
        plan_attempt_ceiling=coverage_plan.attempt_ceiling,
    )
    try:
        config = generator_config or LLMConfig.from_env()
    except LLMConfigurationError as exc:
        raise LiveWorkspaceAcceptanceError("llm_configuration_required") from exc
    if not isinstance(config, LLMConfig) or not config.configured:
        raise LiveWorkspaceAcceptanceError("llm_configuration_required")
    if config.model != authorization.generator_model:
        raise LiveWorkspaceAcceptanceError("generator_identity_mismatch")
    judge_config = profile.mutation_admission.judge
    if judge_config.model != authorization.mutation_judge_model:
        raise LiveWorkspaceAcceptanceError("mutation_judge_identity_mismatch")
    _write_json(
        output_dir / "authorization.json",
        {
            "schema_version": LIVE_ACCEPTANCE_SCHEMA_VERSION,
            "status": "authorized",
            "authorization": authorization.to_record(),
            "domain_plan": {
                "plan_id": plan.plan_id,
                "plan_hash": plan.plan_hash,
                "domain_pack_reference": plan.domain_pack_reference.to_record(),
            },
            "coverage_plan": {
                "plan_id": coverage_plan.plan_id,
                "plan_hash": coverage_plan.plan_hash,
                "attempt_ceiling": coverage_plan.attempt_ceiling,
                "target_accepted_sample_count": coverage_plan.target_accepted_sample_count,
            },
            "source_policy_hash": source_result.source_policy_hash,
            "generator": _generator_identity(config),
            "mutation_judge": _mutation_judge_identity(profile, config),
        },
    )
    _write_json(output_dir / "run_profile.json", profile_record)

    recorder = SanitizedProviderEvidenceRecorder(
        authorization=authorization,
        provider_identity=_generator_identity(config),
        mutation_judge_identity=_mutation_judge_identity(profile, config),
    )
    provider = BoundedSanitizedProvider(
        OpenAICompatibleClient(
            config,
            http_client=generator_http_client,
            max_retries=max_generator_retries,
        ),
        recorder=recorder,
        max_logical_calls=authorization.attempt_budget,
    )
    judge_usage = SanitizedMutationJudgeUsageObserver()
    started = time.perf_counter()
    try:
        result = run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                provider,
                attempt_observer_factory=build_coverage_attempt_observer_factory(recorder),
                generation_rejection_callback=recorder.record_generation_rejection,
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
            write_episode_logs=True,
            mutation_judge_http_client=mutation_judge_http_client,
            mutation_judge_attempt_observer=judge_usage,
            llm_config=config,
            max_concurrency=1,
        )
    except (LLMConfigurationError, LiveWorkspaceAcceptanceError) as exc:
        raise LiveWorkspaceAcceptanceError(
            getattr(exc, "reason_code", "live_pipeline_failed")
        ) from exc
    runtime_seconds = time.perf_counter() - started
    if result.accepted_count < 5:
        raise LiveWorkspaceAcceptanceError("workspace_coverage_evidence_incomplete")
    (
        replay_path,
        evaluation_path,
        profile_decision_path,
        dataset_release_report_path,
        audit_path,
        pack_path,
        qualification,
    ) = _write_live_pipeline_reports(
        output_dir=output_dir,
        profile=profile,
        result=result,
        runtime_seconds=runtime_seconds,
    )
    if qualification.get("status") != "passed" or qualification.get("effective_qualification") != "release_candidate":
        raise LiveWorkspaceAcceptanceError("real_release_candidate_not_verified")
    verification_record = _load_json(output_dir / "release_pack_verification.json")
    verification = verification_record.get("verification")
    if not isinstance(verification, Mapping):
        raise LiveWorkspaceAcceptanceError("release_pack_not_independently_verified")
    samples = []
    try:
        for line in result.samples_path.read_text(encoding="utf-8").splitlines():
            if line:
                value = json.loads(line)
                if isinstance(value, Mapping):
                    samples.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveWorkspaceAcceptanceError("live_artifact_unreadable") from exc
    assignments_by_id: dict[str, Mapping[str, object]] = {}
    for sample in samples:
        evidence = sample.get("workspace_evidence")
        assignment = evidence.get("assignment") if isinstance(evidence, Mapping) else None
        assignment_id = assignment.get("assignment_id") if isinstance(assignment, Mapping) else None
        if isinstance(assignment_id, str) and isinstance(assignment, Mapping):
            assignments_by_id[assignment_id] = assignment
    recorder.bind_sample_assignments(assignments_by_id)
    recorder.set_mutation_judge_usage(judge_usage.to_record())
    provider_evidence_path = output_dir / "trace" / "provider.json"
    provider_evidence = recorder.freeze(
        provider_evidence_path,
        qualification=qualification,
        release_pack_verification=verification,
        release_pack_hash="sha256:" + hashlib.sha256(pack_path.read_bytes()).hexdigest(),
        run_binding={
            "profile_id": profile.profile_id,
            "dataset_version": profile.dataset_version,
            "seed_id": profile.seed.seed_id,
            "seed_domain": profile.seed.domain,
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "coverage_plan_id": coverage_plan.plan_id,
            "coverage_plan_hash": coverage_plan.plan_hash,
            "source_policy_hash": source_result.source_policy_hash,
        },
    )
    replay = replay_sanitized_provider_evidence(
        provider_evidence,
        plan=plan,
        seed=_profile_seed(profile),
        environment_path=_environment_path(output_dir),
    )
    non_accepted = [
        record for record in provider_evidence["attempts"]
        if isinstance(record, Mapping) and record.get("outcome") != "validated"
    ]
    _write_json(
        output_dir / "acceptance.json",
        {
            "schema_version": LIVE_ACCEPTANCE_SCHEMA_VERSION,
            "status": "accepted",
            "authorization": authorization.to_record(),
            "qualification": {
                "status": qualification.get("status"),
                "effective_qualification": qualification.get("effective_qualification"),
                "publishable": qualification.get("claims", {}).get("publishable")
                if isinstance(qualification.get("claims"), Mapping)
                else None,
                "training_recommended": qualification.get("claims", {}).get("training_recommended")
                if isinstance(qualification.get("claims"), Mapping)
                else None,
            },
            "provider_evidence": {
                "path": "trace/provider.json",
                "evidence_class": "real_live",
                "logical_calls": provider_evidence["usage"]["logical_calls"],
                "replayable_calls": provider_evidence["usage"]["replayable_calls"],
                "non_accepted_attempt_count": len(non_accepted),
                "usage": provider_evidence["usage"],
                "cost": provider_evidence["cost"],
            },
            "replay": dict(replay),
            "artifacts": {
                "replay_report": replay_path.name,
                "evaluation_report": evaluation_path.name,
                "profile_decision_report": profile_decision_path.name,
                "dataset_release_report": dataset_release_report_path.name,
                "release_quality_audit": audit_path.name,
                "release_pack": pack_path.name,
            },
        },
    )
    from synthesis.workspace_tracer import (
        build_workspace_tracer_proof_from_live_acceptance,
        verify_workspace_tracer_proof,
    )

    proof_path = build_workspace_tracer_proof_from_live_acceptance(
        proof_root,
        output_dir,
    )
    proof_result = verify_workspace_tracer_proof(proof_path)
    if proof_result.get("status") != "passed":
        raise LiveWorkspaceAcceptanceError("live_tracer_proof_failed")
    return LiveWorkspaceAcceptanceResult(
        acceptance_dir=output_dir,
        proof_path=proof_path,
        provider_evidence_path=proof_root / "positive" / "trace" / "provider.json",
        replay=replay,
        qualification=qualification,
    )
