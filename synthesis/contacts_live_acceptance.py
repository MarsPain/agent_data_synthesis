"""Explicitly authorized live Contacts acceptance.

The Contacts provider-free proof is the canonical semantic path.  This module
only adds the operator boundary that is allowed to use a configured provider:
the exact Contacts Release Candidate profile, explicit budgets, independent
mutation-judge preflight, bounded failure evidence, and a ``real_live``
provider-evidence contract.  Tests can inject transports; no test needs a
credential or a provider service.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil

from synthesis.acceptance_replay import (
    AcceptanceAuthorization,
    AcceptanceEvidenceRecorder,
    AcceptancePipelineResult,
    AcceptancePreparation,
    AcceptanceReleaseEvidence,
    AcceptanceReplayContract,
    AcceptanceReplayError,
    AcceptanceReplayHarness,
    AcceptanceUsageObserver,
    BoundedSanitizedProvider,
    CoverageAssignmentEvidenceObserver,
    SanitizedMutationJudgeUsageObserver as _NeutralSanitizedMutationJudgeUsageObserver,
    SanitizedProviderEvidenceRecorder as _NeutralSanitizedProviderEvidenceRecorder,
    bounded_reason,
    build_coverage_attempt_observer_factory,
    load_provider_evidence as _neutral_load_provider_evidence,
    replay_frozen_provider_evidence as _neutral_replay_frozen_provider_evidence,
    sanitize_provider_response as _neutral_sanitize_provider_response,
    sum_usage,
    validate_provider_evidence as _neutral_validate_provider_evidence,
)
from synthesis.contacts_acceptance import (
    CONTACTS_PROVIDER_PARSER_VERSION,
    CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION,
    CONTACTS_RELEASE_CANDIDATE_PROFILE_ID,
    CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES,
    CONTACTS_RELEASE_TARGET_CANDIDATES,
    CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION,
    ContactsAcceptanceError,
    _ContactsAcceptanceAdapter,
    _mutation_judge_attempt_ceiling,
    _mutation_judge_identity,
    _preflight_contacts_mutation_judge,
    build_contacts_acceptance_proof,
    replay_contacts_provider_evidence as _replay_contacts_provider_evidence,
    verify_contacts_acceptance_proof,
)
from synthesis.coverage_assignments import (
    build_coverage_assignment_scheduler_factory,
)
from synthesis.llm import LLMConfig, LLMConfigurationError, OpenAICompatibleClient
from synthesis.run_profiles import RunProfile


LIVE_ACCEPTANCE_SCHEMA_VERSION = "contacts_live_acceptance_v1"
LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION = "contacts_live_attempt_failure_v1"
LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION = "contacts_live_provider_evidence_v1"
LIVE_EVIDENCE_CLASS = "real_live"
SANITIZED_EVIDENCE_POLICY_VERSION = CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION
PROVIDER_PARSER_VERSION = CONTACTS_PROVIDER_PARSER_VERSION
MAX_LIVE_GENERATOR_RETRIES = 3
CONTACTS_LIVE_PROOF_FAILURE_FILENAME = "contacts_live_attempt_failure.json"
DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL = "deepseek-v4-pro"
DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS = 90.0
DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES = 0
DEFAULT_CONTACTS_MUTATION_JUDGE_THINKING_MODE = "disabled"
DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS = 90.0

# Domain-prefixed spellings are convenient for callers that keep several
# acceptance contracts in one namespace.
CONTACTS_LIVE_ACCEPTANCE_SCHEMA_VERSION = LIVE_ACCEPTANCE_SCHEMA_VERSION
CONTACTS_LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION = LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION
CONTACTS_LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION = LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION
CONTACTS_LIVE_EVIDENCE_CLASS = LIVE_EVIDENCE_CLASS
CONTACTS_LIVE_SANITIZED_EVIDENCE_POLICY_VERSION = SANITIZED_EVIDENCE_POLICY_VERSION

_CONTACTS_LIVE_ACCEPTANCE_CONTRACT = AcceptanceReplayContract(
    acceptance_schema_version=LIVE_ACCEPTANCE_SCHEMA_VERSION,
    provider_evidence_schema_version=LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION,
    evidence_class=LIVE_EVIDENCE_CLASS,
    freeze_policy=SANITIZED_EVIDENCE_POLICY_VERSION,
    provider_parser_version=PROVIDER_PARSER_VERSION,
    replay_result_schema_version="contacts_live_replay_result_v1",
    expected_provider_id="openai_compatible",
    expected_provider_version="openai_compatible_client_v1",
    expected_judge_provider="openai_compatible",
    expected_judge_role="mutation_admission_judge",
    expected_judge_role_version="role_mutation_admission_judge_v1",
    provider_attempt_id_prefix="contacts_live_provider_attempt",
    mutation_judge_attempt_id_prefix="contacts_live_mutation_judge_attempt",
    preflight_failure_reason="contacts_live_mutation_judge_preflight_failed",
    pipeline_failure_reason="contacts_live_pipeline_failed",
)

# Keep the contract inspectable for offline verification and test transports;
# callers still reach provider work only through the explicitly authorized
# runner below.
CONTACTS_LIVE_ACCEPTANCE_CONTRACT = _CONTACTS_LIVE_ACCEPTANCE_CONTRACT

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,239}$")
_AUTHORIZATION_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_.:-]{1,127}$")
_CONTACTS_MEMBERSHIP_REASONS = frozenset(
    {
        "assignment_membership_mismatch",
        "capability_membership_mismatch",
        "domain_mismatch",
        "evidence_binding_failed",
        "grounding_expected_state_mismatch",
        "grounding_final_answer_mismatch",
        "grounding_followup_state_mismatch",
        "expected_state_membership_mismatch",
        "grounding_membership_mismatch",
        "grounding_primary_arguments_mismatch",
        "legacy_fixture_membership_mismatch",
        "primary_tool_membership_mismatch",
        "recovery_assignment_mismatch",
        "recovery_evidence_missing",
        "recovery_structure_mismatch",
        "state_behavior_membership_mismatch",
        "tool_membership_mismatch",
    }
)

_EXACT_CONTACTS_RELEASE_PROFILE: dict[str, object] = {
    "schema_version": "run_profile_v4",
    "profile_id": CONTACTS_RELEASE_CANDIDATE_PROFILE_ID,
    "dataset_version": CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION,
    "profile_purpose": "release_candidate",
    "seed": {
        "seed_id": "seed_contacts_release_candidate_v1",
        "domain": "contacts_fixture",
        "description": "Canonical Contacts release-candidate evidence profile.",
        "task_taxonomy": [
            "contact_lookup",
            "contact_followup",
            "contact_lookup_recovery",
        ],
    },
    "generation": {
        "mode": "foundation_fixture",
        "target_candidate_count": CONTACTS_RELEASE_TARGET_CANDIDATES,
    },
    "features": {
        "enable_branching": True,
        "enable_task_expansion": False,
        "enable_refinement": False,
        "enable_mcp_adapter": False,
        "enable_sandbox_fixture": False,
        "enable_source_governance_fixture": False,
    },
    "mutation_admission": {
        "mode": "enforce",
        "judge": {
            "role": "mutation_admission_judge",
            "provider": "openai_compatible",
            "model": DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
            "timeout_seconds": DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS,
            "max_retries": DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES,
            "thinking_mode": DEFAULT_CONTACTS_MUTATION_JUDGE_THINKING_MODE,
        },
    },
    "coverage_profile": {
        "profile_id": "contacts_representative",
        "version": "contacts_representative_v1",
        "target_accepted_sample_count": CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES,
    },
}


class LiveContactsAcceptanceError(ContactsAcceptanceError):
    """A bounded failure at the authorized live Contacts boundary."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code, message)


@dataclass(frozen=True)
class LiveContactsAcceptanceAuthorization:
    """The operator's explicit, bounded authorization envelope."""

    approved: bool
    authorization_id: str
    candidate_budget: int
    attempt_budget: int
    generator_provider: str
    generator_model: str
    mutation_judge_provider: str
    mutation_judge_model: str
    generator_timeout_seconds: float = DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS
    generator_retry_limit: int = 0
    evidence_policy: str = SANITIZED_EVIDENCE_POLICY_VERSION

    def validate(
        self,
        *,
        profile: Mapping[str, object],
        plan_attempt_ceiling: int,
    ) -> None:
        if not self.approved:
            raise LiveContactsAcceptanceError(
                "contacts_live_provider_authorization_required"
            )
        if _AUTHORIZATION_ID_RE.fullmatch(self.authorization_id) is None:
            raise LiveContactsAcceptanceError(
                "contacts_live_authorization_identity_invalid"
            )
        if self.evidence_policy != SANITIZED_EVIDENCE_POLICY_VERSION:
            raise LiveContactsAcceptanceError(
                "contacts_live_sanitized_evidence_policy_required"
            )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (self.candidate_budget, self.attempt_budget)
        ):
            raise LiveContactsAcceptanceError("contacts_live_authorization_budget_invalid")
        if (
            not isinstance(self.generator_timeout_seconds, (int, float))
            or isinstance(self.generator_timeout_seconds, bool)
            or float(self.generator_timeout_seconds)
            != DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS
        ):
            raise LiveContactsAcceptanceError(
                "contacts_live_generator_timeout_policy_invalid"
            )
        if (
            not isinstance(self.generator_retry_limit, int)
            or isinstance(self.generator_retry_limit, bool)
            or self.generator_retry_limit not in range(MAX_LIVE_GENERATOR_RETRIES + 1)
        ):
            raise LiveContactsAcceptanceError("contacts_live_generator_retry_budget_invalid")
        if (
            not isinstance(plan_attempt_ceiling, int)
            or isinstance(plan_attempt_ceiling, bool)
            or plan_attempt_ceiling <= 0
            or plan_attempt_ceiling > self.attempt_budget
        ):
            raise LiveContactsAcceptanceError("contacts_live_attempt_budget_exceeded")

        if not isinstance(profile, Mapping) or dict(profile) != _EXACT_CONTACTS_RELEASE_PROFILE:
            raise LiveContactsAcceptanceError("contacts_live_release_profile_invalid")
        generation = profile["generation"]
        mutation = profile["mutation_admission"]
        judge = mutation["judge"]
        target = generation.get("target_candidate_count")
        if (
            not isinstance(target, int)
            or isinstance(target, bool)
            or target <= 0
            or target > self.candidate_budget
        ):
            raise LiveContactsAcceptanceError("contacts_live_candidate_budget_exceeded")
        if not isinstance(judge, Mapping):
            raise LiveContactsAcceptanceError(
                "contacts_live_mutation_judge_identity_required"
            )
        if (
            self.generator_provider != "openai_compatible"
            or self.mutation_judge_provider != "openai_compatible"
            or judge.get("provider") != self.mutation_judge_provider
            or judge.get("role") != "mutation_admission_judge"
            or judge.get("model") != self.mutation_judge_model
            or judge.get("timeout_seconds")
            != DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS
            or judge.get("max_retries") != DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES
            or not isinstance(self.generator_model, str)
            or _IDENTIFIER_RE.fullmatch(self.generator_model) is None
            or not isinstance(self.mutation_judge_model, str)
            or _IDENTIFIER_RE.fullmatch(self.mutation_judge_model) is None
            or self.generator_model == self.mutation_judge_model
        ):
            raise LiveContactsAcceptanceError(
                "contacts_live_mutation_judge_identity_not_independent"
            )

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
            "generator_timeout_seconds": self.generator_timeout_seconds,
            "generator_retry_limit": self.generator_retry_limit,
            "evidence_policy": self.evidence_policy,
        }


class SanitizedProviderEvidenceRecorder(_NeutralSanitizedProviderEvidenceRecorder):
    """Recorder facade that freezes Contacts evidence as ``real_live``."""

    def __init__(
        self,
        *,
        authorization: LiveContactsAcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> None:
        super().__init__(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=mutation_judge_identity,
            contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
        )


class SanitizedMutationJudgeUsageObserver(
    _NeutralSanitizedMutationJudgeUsageObserver
):
    """Bounded judge usage observer with Contacts live attempt IDs."""

    def __init__(self, *, attempt_ceiling: int | None = None) -> None:
        super().__init__(
            attempt_ceiling=attempt_ceiling,
            attempt_id_prefix="contacts_live_mutation_judge_attempt",
        )


def sanitize_provider_response(response: object) -> dict[str, object]:
    try:
        return _neutral_sanitize_provider_response(response)
    except AcceptanceReplayError as exc:
        raise LiveContactsAcceptanceError(exc.reason_code) from None


def validate_live_provider_evidence(evidence: Mapping[str, object]) -> None:
    try:
        _neutral_validate_provider_evidence(
            evidence,
            contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        raise LiveContactsAcceptanceError(_map_reason(exc.reason_code)) from None


def load_live_provider_evidence(path: Path) -> dict[str, object]:
    try:
        return _neutral_load_provider_evidence(
            path,
            contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        raise LiveContactsAcceptanceError(_map_reason(exc.reason_code)) from None


def replay_sanitized_provider_evidence(
    evidence: Mapping[str, object] | Path,
    *,
    profile: RunProfile,
    plan: object,
    acceptance_dir: Path,
) -> dict[str, object]:
    """Replay frozen Contacts provider input without another provider call."""

    try:
        return _neutral_replay_frozen_provider_evidence(
            evidence,
            replay=lambda loaded: _replay_contacts_provider_evidence(
                loaded,
                profile=profile,
                plan=plan,
                acceptance_dir=acceptance_dir,
                contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
            ),
            contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        raise LiveContactsAcceptanceError(_map_reason(exc.reason_code)) from None


def verify_live_contacts_acceptance_proof(proof_path: Path) -> dict[str, object]:
    """Verify a frozen real-live Contacts proof without provider access."""

    return verify_contacts_acceptance_proof(
        Path(proof_path),
        evidence_contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
    )


def _map_reason(reason_code: str) -> str:
    return {
        "acceptance_identity_malformed": "contacts_live_evidence_malformed",
        "acceptance_identity_mismatch": "contacts_live_evidence_identity_mismatch",
        "acceptance_binding_malformed": "contacts_live_run_binding_malformed",
        "acceptance_binding_mismatch": "contacts_live_run_binding_mismatch",
        "acceptance_evidence_malformed": "contacts_live_evidence_malformed",
        "acceptance_evidence_missing": "contacts_live_evidence_missing",
        "acceptance_replay_input_malformed": "contacts_live_replay_input_malformed",
        "acceptance_replay_input_mismatch": "contacts_live_replay_input_mismatch",
        "acceptance_replay_inputs_missing": "contacts_live_replay_inputs_missing",
        "acceptance_replay_failed": "contacts_live_replay_contract_failed",
        "acceptance_replay_count_mismatch": "contacts_live_replay_count_mismatch",
        "acceptance_judge_attempt_missing": "contacts_live_judge_attempt_missing",
        "acceptance_assignment_missing": "contacts_live_assignment_missing",
        "acceptance_evidence_already_frozen": "contacts_live_evidence_already_frozen",
        "acceptance_release_evidence_missing": "contacts_live_evidence_missing",
        "acceptance_release_path_unsafe": "contacts_live_evidence_malformed",
        "acceptance_release_identity_mismatch": "contacts_live_evidence_identity_mismatch",
        "release_pack_not_independently_verified": "contacts_live_release_pack_not_verified",
        "real_release_candidate_not_verified": "contacts_live_release_candidate_not_verified",
        "qualification_evidence_not_freezable": "contacts_live_qualification_not_freezable",
        "acceptance_proof_failed": "contacts_live_acceptance_proof_failed",
    }.get(reason_code, reason_code)


def _generator_identity(config: LLMConfig) -> dict[str, object]:
    lineage = config.lineage("task_generation")
    return {
        "provider_id": "openai_compatible",
        "provider_version": "openai_compatible_client_v1",
        "provider_host": _safe_provider_host(config.base_url),
        "model": config.model,
        "config_hash": lineage["config_hash"],
        "parser_version": PROVIDER_PARSER_VERSION,
    }


def _safe_provider_host(base_url: object) -> str:
    if not isinstance(base_url, str) or not base_url:
        return "unconfigured"
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    if parsed.hostname is None:
        return "unconfigured"
    try:
        return (
            f"{parsed.hostname}:{parsed.port}"
            if parsed.port is not None
            else parsed.hostname
        )
    except ValueError:
        return "unconfigured"


def _generator_physical_call_ceiling(
    authorization: LiveContactsAcceptanceAuthorization,
) -> int:
    if (
        not isinstance(authorization.generator_retry_limit, int)
        or isinstance(authorization.generator_retry_limit, bool)
        or authorization.generator_retry_limit not in range(MAX_LIVE_GENERATOR_RETRIES + 1)
        or not isinstance(authorization.attempt_budget, int)
        or isinstance(authorization.attempt_budget, bool)
        or authorization.attempt_budget <= 0
    ):
        raise LiveContactsAcceptanceError("contacts_live_generator_retry_budget_invalid")
    return authorization.attempt_budget * (authorization.generator_retry_limit + 1)


def _generator_usage_summary(
    recorder: SanitizedProviderEvidenceRecorder,
) -> dict[str, object]:
    attempts = recorder.attempts
    retries = sum(
        int(record.get("retry_count", 0))
        for record in attempts
        if isinstance(record.get("retry_count"), int)
        and not isinstance(record.get("retry_count"), bool)
    )
    return {
        "logical_calls": len(attempts),
        "tokens": sum_usage(attempts),
        "retries": retries,
        "physical_calls": len(attempts) + retries,
        "physical_call_ceiling": _generator_physical_call_ceiling(
            recorder.authorization
        ),
        "outcomes": {
            outcome: sum(record.get("outcome") == outcome for record in attempts)
            for outcome in sorted({str(record.get("outcome")) for record in attempts})
        },
        "failure_classes": dict(recorder.generation_failure_classes),
    }


def _bounded_rejection_summary(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file() or path.is_symlink():
        return {"count": 0, "causes": {}, "membership_reasons": {}}
    causes: dict[str, int] = {}
    membership_reasons: dict[str, int] = {}
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, Mapping):
                raise ValueError("rejection record is malformed")
            count += 1
            cause = bounded_reason(record.get("cause"))
            causes[cause] = causes.get(cause, 0) + 1
            details = record.get("details")
            membership_reason = (
                details.get("membership_reason")
                if cause == "domain_plan_membership_rejected"
                and isinstance(details, Mapping)
                else None
            )
            if (
                isinstance(membership_reason, str)
                and membership_reason in _CONTACTS_MEMBERSHIP_REASONS
            ):
                membership_reasons[membership_reason] = (
                    membership_reasons.get(membership_reason, 0) + 1
                )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {
            "count": 0,
            "causes": {"rejection_summary_unavailable": 1},
            "membership_reasons": {},
        }
    return {
        "count": count,
        "causes": dict(sorted(causes.items())),
        "membership_reasons": dict(sorted(membership_reasons.items())),
    }


def _bounded_frozen_usage(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {
            "logical_calls": 0,
            "tokens": {},
            "retries": 0,
            "physical_calls": 0,
            "physical_call_ceiling": 0,
            "outcomes": {},
            "failure_classes": {},
        }
    numeric_fields = {
        field_name: value.get(field_name)
        for field_name in (
            "logical_calls",
            "retries",
            "physical_calls",
            "physical_call_ceiling",
        )
        if isinstance(value.get(field_name), int)
        and not isinstance(value.get(field_name), bool)
        and value.get(field_name) >= 0
    }
    outcomes = value.get("outcomes")
    bounded_outcomes = (
        {
            str(key): count
            for key, count in outcomes.items()
            if isinstance(key, str)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        }
        if isinstance(outcomes, Mapping)
        else {}
    )
    return {
        "logical_calls": numeric_fields.get("logical_calls", 0),
        "tokens": sum_usage(
            [{"usage": value.get("tokens")}]
            if isinstance(value.get("tokens"), Mapping)
            else []
        ),
        "retries": numeric_fields.get("retries", 0),
        "physical_calls": numeric_fields.get("physical_calls", 0),
        "physical_call_ceiling": numeric_fields.get(
            "physical_call_ceiling", 0
        ),
        "outcomes": bounded_outcomes,
        "failure_classes": (
            {
                str(key): count
                for key, count in value.get("failure_classes", {}).items()
                if isinstance(key, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            }
            if isinstance(value.get("failure_classes"), Mapping)
            else {}
        ),
    }


def _bounded_frozen_judge_usage(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {
            "attempts": 0,
            "attempt_ceiling": None,
            "tokens": {},
            "outcomes": {},
            "failure_classes": {},
        }
    attempts = value.get("attempts")
    ceiling = value.get("attempt_ceiling")
    outcomes = value.get("outcomes")
    failure_classes = value.get("failure_classes")
    return {
        "attempts": (
            attempts
            if isinstance(attempts, int)
            and not isinstance(attempts, bool)
            and attempts >= 0
            else 0
        ),
        "attempt_ceiling": (
            ceiling
            if isinstance(ceiling, int)
            and not isinstance(ceiling, bool)
            and ceiling >= 0
            else None
        ),
        "tokens": sum_usage(
            [{"usage": value.get("tokens")}]
            if isinstance(value.get("tokens"), Mapping)
            else []
        ),
        "outcomes": (
            {
                str(key): count
                for key, count in outcomes.items()
                if isinstance(key, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            }
            if isinstance(outcomes, Mapping)
            else {}
        ),
        "failure_classes": (
            {
                str(key): count
                for key, count in failure_classes.items()
                if isinstance(key, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            }
            if isinstance(failure_classes, Mapping)
            else {}
        ),
    }


def _bounded_frozen_run_binding(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    keys = (
        "profile_id",
        "dataset_version",
        "seed_id",
        "seed_domain",
        "plan_id",
        "plan_hash",
        "coverage_plan_id",
        "coverage_plan_hash",
        "source_policy_hash",
    )
    return {
        key: value[key]
        for key in keys
        if isinstance(value.get(key), str)
    }


def _retain_only_failure_record(output_dir: Path) -> None:
    failure_path = output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME
    if not output_dir.is_dir() or output_dir.is_symlink():
        return
    for child in list(output_dir.iterdir()):
        if child == failure_path:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def _discard_post_freeze_artifacts(
    output_dir: Path,
    *,
    authorization: object,
    reason_code: str,
    phase: str,
) -> None:
    """Discard reusable provider evidence after a later proof failure.

    This is called only for an output directory that was empty when the run
    started.  It reads the already-sanitized record for bounded usage and
    binding fields, then retains only the failure audit record.
    """

    provider_path = output_dir / "trace" / "provider.json"
    try:
        provider = json.loads(provider_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        provider = {}
    if not isinstance(provider, Mapping):
        provider = {}
    try:
        authorization_record = authorization.to_record()
    except Exception:
        authorization_record = {}
    if not isinstance(authorization_record, Mapping):
        authorization_record = {}
    rejection_summary = _bounded_rejection_summary(output_dir / "rejections.jsonl")
    qualification = None
    qualification_path = output_dir / "qualification_report.json"
    try:
        raw_qualification = json.loads(
            qualification_path.read_text(encoding="utf-8")
        )
        if isinstance(raw_qualification, Mapping):
            qualification = {
                "status": raw_qualification.get("status"),
                "effective_qualification": raw_qualification.get(
                    "effective_qualification"
                ),
            }
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    if output_dir.is_dir() and not output_dir.is_symlink():
        _retain_only_failure_record(output_dir)
    usage = _bounded_frozen_usage(provider.get("usage"))
    judge_usage = _bounded_frozen_judge_usage(
        provider.get("mutation_judge_usage")
    )
    _write_json(
        output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME,
        {
            "schema_version": LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION,
            "status": "failed",
            "reason_code": reason_code,
            "phase": phase,
            "authorization": dict(authorization_record),
            "run_binding": _bounded_frozen_run_binding(
                provider.get("run_binding")
            ),
            "generator_usage": usage,
            "mutation_judge_usage": judge_usage,
            "mutation_judge_preflight": {"status": "completed"},
            "rejections": rejection_summary,
            "non_accepted_attempts": rejection_summary,
            "provider_evidence_frozen": False,
            "provider_evidence_discarded": True,
            "proof_root_published": False,
            "tracer_proof_published": False,
            "qualification": qualification,
        },
    )


class _ContactsLiveAcceptanceAdapter(_ContactsAcceptanceAdapter):
    """Bind Contacts semantics to the neutral live acceptance harness."""

    evidence_contract = _CONTACTS_LIVE_ACCEPTANCE_CONTRACT

    def error_for_reason(self, reason_code: str) -> LiveContactsAcceptanceError:
        return LiveContactsAcceptanceError(_map_reason(reason_code))

    def validate_authorization(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        authorization: AcceptanceAuthorization,
        max_generator_retries: int,
    ) -> None:
        del profile
        if not isinstance(authorization, LiveContactsAcceptanceAuthorization):
            raise LiveContactsAcceptanceError(
                "contacts_live_authorization_malformed"
            )
        authorization.validate(
            profile=preparation.profile_record,
            plan_attempt_ceiling=int(preparation.coverage_plan.attempt_ceiling),
        )
        if max_generator_retries != authorization.generator_retry_limit:
            raise LiveContactsAcceptanceError(
                "contacts_live_generator_retry_authorization_mismatch"
            )

    def resolve_generator_config(self, supplied: object | None) -> object:
        try:
            config = supplied if supplied is not None else LLMConfig.from_env()
        except LLMConfigurationError as exc:
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            ) from exc
        if not isinstance(config, LLMConfig) or not config.configured:
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            )
        return config

    def validate_generator_config(
        self,
        *,
        profile: object,
        authorization: AcceptanceAuthorization,
        config: object,
    ) -> None:
        if not isinstance(config, LLMConfig) or not config.configured:
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            )
        if config.model != authorization.generator_model:
            raise LiveContactsAcceptanceError(
                "contacts_live_generator_identity_mismatch"
            )
        judge = profile.mutation_admission.judge
        if judge is None or judge.model != authorization.mutation_judge_model:
            raise LiveContactsAcceptanceError(
                "contacts_live_mutation_judge_identity_mismatch"
            )

    def generator_identity(self, config: object) -> Mapping[str, object]:
        if not isinstance(config, LLMConfig):
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            )
        return _generator_identity(config)

    def mutation_judge_identity(
        self,
        *,
        profile: object,
        config: object,
    ) -> Mapping[str, object]:
        if not isinstance(config, LLMConfig):
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            )
        return _mutation_judge_identity(profile, config)

    def create_recorder(
        self,
        *,
        authorization: AcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> AcceptanceEvidenceRecorder:
        if not isinstance(authorization, LiveContactsAcceptanceAuthorization):
            raise LiveContactsAcceptanceError(
                "contacts_live_authorization_malformed"
            )
        return SanitizedProviderEvidenceRecorder(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=mutation_judge_identity,
        )

    def create_usage_observer(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> AcceptanceUsageObserver:
        return SanitizedMutationJudgeUsageObserver(
            attempt_ceiling=self.mutation_judge_attempt_ceiling(
                profile=profile,
                preparation=preparation,
            )
        )

    def preflight_mutation_judge(
        self,
        *,
        profile: object,
        config: object,
        http_client: object | None,
        observer: AcceptanceUsageObserver,
    ) -> Mapping[str, object]:
        if not isinstance(config, LLMConfig) or not isinstance(
            observer, SanitizedMutationJudgeUsageObserver
        ):
            raise LiveContactsAcceptanceError("contacts_live_preflight_malformed")
        return _preflight_contacts_mutation_judge(
            profile=profile,
            generator_config=config,
            http_client=http_client,
            observer=observer,
        )

    def build_provider(
        self,
        *,
        config: object,
        authorization: AcceptanceAuthorization,
        recorder: AcceptanceEvidenceRecorder,
        http_client: object | None,
        max_generator_retries: int,
    ) -> object:
        if not isinstance(config, LLMConfig):
            raise LiveContactsAcceptanceError(
                "contacts_live_llm_configuration_required"
            )
        if not isinstance(authorization, LiveContactsAcceptanceAuthorization):
            raise LiveContactsAcceptanceError(
                "contacts_live_authorization_malformed"
            )
        if not isinstance(recorder, SanitizedProviderEvidenceRecorder):
            raise LiveContactsAcceptanceError(
                "contacts_live_evidence_recorder_invalid"
            )
        return BoundedSanitizedProvider(
            OpenAICompatibleClient(
                config,
                http_client=http_client,
                max_retries=max_generator_retries,
                timeout_seconds=authorization.generator_timeout_seconds,
            ),
            recorder=recorder,
            max_logical_calls=authorization.attempt_budget,
        )

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
    ) -> AcceptancePipelineResult:
        if not isinstance(profile, RunProfile) or not isinstance(config, LLMConfig):
            raise LiveContactsAcceptanceError(
                "contacts_live_pipeline_configuration_invalid"
            )
        if not isinstance(recorder, SanitizedProviderEvidenceRecorder) or not isinstance(
            observer, SanitizedMutationJudgeUsageObserver
        ):
            raise LiveContactsAcceptanceError(
                "contacts_live_pipeline_evidence_recorder_invalid"
            )
        from synthesis.pipeline import run_foundation_pipeline

        result = run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                provider,
                attempt_observer_factory=build_coverage_attempt_observer_factory(
                    recorder
                ),
                generation_rejection_callback=recorder.record_generation_rejection,
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
            write_episode_logs=True,
            mutation_judge_http_client=mutation_judge_http_client,
            mutation_judge_attempt_observer=observer,
            llm_config=config,
            max_concurrency=1,
        )
        return AcceptancePipelineResult(
            result=result,
            accepted_count=result.accepted_count,
            rejections_path=result.rejections_path,
        )

    def validate_pipeline(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        pipeline: AcceptancePipelineResult,
    ) -> None:
        del profile, preparation
        if pipeline.accepted_count < CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES:
            raise LiveContactsAcceptanceError(
                "contacts_live_coverage_evidence_incomplete"
            )
        result = pipeline.result
        if (
            result.episode_logs_path is None
            or result.coverage_plan_path is None
            or result.coverage_evidence_path is None
        ):
            raise LiveContactsAcceptanceError(
                "contacts_live_run_completeness_incomplete"
            )

    def mutation_judge_attempt_ceiling(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> int:
        try:
            return _mutation_judge_attempt_ceiling(
                profile,
                preparation.coverage_plan,
            )
        except ContactsAcceptanceError as exc:
            raise LiveContactsAcceptanceError(
                _map_reason(exc.reason_code)
            ) from None

    def write_release_evidence(
        self,
        *,
        output_dir: Path,
        profile: object,
        pipeline: AcceptancePipelineResult,
        runtime_seconds: float,
    ) -> AcceptanceReleaseEvidence:
        try:
            return super().write_release_evidence(
                output_dir=output_dir,
                profile=profile,
                pipeline=pipeline,
                runtime_seconds=runtime_seconds,
            )
        except ContactsAcceptanceError as exc:
            raise LiveContactsAcceptanceError(
                _map_reason(exc.reason_code)
            ) from None

    def bind_sample_assignments(
        self,
        *,
        recorder: AcceptanceEvidenceRecorder,
        pipeline: AcceptancePipelineResult,
    ) -> None:
        try:
            super().bind_sample_assignments(recorder=recorder, pipeline=pipeline)
        except ContactsAcceptanceError as exc:
            raise LiveContactsAcceptanceError(
                _map_reason(exc.reason_code)
            ) from None

    def replay(
        self,
        *,
        evidence: Mapping[str, object],
        preparation: AcceptancePreparation,
    ) -> int | Mapping[str, object]:
        if self._profile is None or self._output_dir is None:
            raise LiveContactsAcceptanceError("contacts_live_replay_context_missing")
        return replay_sanitized_provider_evidence(
            evidence,
            profile=self._profile,
            plan=preparation.plan,
            acceptance_dir=self._output_dir,
        )

    def build_proof(self, *, proof_root: Path, acceptance_dir: Path) -> Path:
        try:
            return build_contacts_acceptance_proof(
                proof_root,
                acceptance_dir,
                evidence_contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
            )
        except ContactsAcceptanceError as exc:
            raise LiveContactsAcceptanceError(
                _map_reason(exc.reason_code)
            ) from None

    def verify_proof(self, proof_path: Path) -> Mapping[str, object]:
        result = verify_contacts_acceptance_proof(
            proof_path,
            evidence_contract=_CONTACTS_LIVE_ACCEPTANCE_CONTRACT,
        )
        if result.get("status") != "passed":
            reasons = result.get("reason_codes")
            reason = (
                str(reasons[0])
                if isinstance(reasons, list)
                and reasons
                and isinstance(reasons[0], str)
                else "contacts_live_acceptance_proof_failed"
            )
            raise LiveContactsAcceptanceError(
                _map_reason(reason),
                str(result.get("detail", reason)),
            )
        return result

    def provider_evidence_path(
        self,
        *,
        proof_path: Path,
        acceptance_dir: Path,
    ) -> Path:
        del acceptance_dir
        return proof_path.parent / "positive" / "trace" / "provider.json"

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
    ) -> Path:
        if not isinstance(authorization, LiveContactsAcceptanceAuthorization):
            raise LiveContactsAcceptanceError("contacts_live_authorization_malformed")
        if not isinstance(recorder, SanitizedProviderEvidenceRecorder) or not isinstance(
            observer, SanitizedMutationJudgeUsageObserver
        ):
            raise LiveContactsAcceptanceError("contacts_live_usage_malformed")
        if not _REASON_RE.fullmatch(reason_code) or phase not in {
            "mutation_judge_preflight",
            "pipeline",
            "release_evidence",
            "qualification",
        }:
            raise LiveContactsAcceptanceError("contacts_live_evidence_malformed")
        rejection_summary = _bounded_rejection_summary(rejections_path)
        qualification_summary = None
        if isinstance(qualification, Mapping):
            qualification_summary = {
                "status": qualification.get("status"),
                "effective_qualification": qualification.get(
                    "effective_qualification"
                ),
            }
        record = {
            "schema_version": LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION,
            "status": "failed",
            "reason_code": _map_reason(reason_code),
            "phase": phase,
            "authorization": authorization.to_record(),
            "run_binding": dict(preparation.run_binding),
            "generator_usage": _generator_usage_summary(recorder),
            "mutation_judge_usage": observer.to_failure_record(),
            "mutation_judge_preflight": (
                dict(mutation_judge_preflight)
                if isinstance(mutation_judge_preflight, Mapping)
                else {"status": "not_started"}
            ),
            "rejections": rejection_summary,
            "non_accepted_attempts": rejection_summary,
            "provider_evidence_frozen": False,
            "proof_root_published": False,
            "tracer_proof_published": False,
            "qualification": qualification_summary,
        }
        destination = output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME
        _write_json(destination, record)
        return destination


@dataclass(frozen=True)
class LiveContactsAcceptanceResult:
    acceptance_dir: Path
    proof_path: Path
    provider_evidence_path: Path
    replay: Mapping[str, object]
    qualification: Mapping[str, object]


def run_live_contacts_acceptance(
    output_dir: Path,
    *,
    profile: object,
    authorization: LiveContactsAcceptanceAuthorization,
    generator_config: object | None = None,
    generator_http_client: object | None = None,
    mutation_judge_http_client: object | None = None,
    proof_root: Path | None = None,
    max_generator_retries: int | None = None,
) -> LiveContactsAcceptanceResult:
    """Run one explicitly authorized Contacts acceptance.

    ``generator_http_client`` and ``mutation_judge_http_client`` are optional
    injection seams for tests.  When omitted, the operator's configured
    OpenAI-compatible clients are used; this function never obtains a
    credential implicitly from an artifact or from a test fixture.
    """

    output_dir = Path(output_dir)
    live_proof_root = (
        Path(proof_root)
        if proof_root is not None
        else output_dir.parent / (output_dir.name + "-proof")
    )
    output_was_nonempty = output_dir.exists() and (
        not output_dir.is_dir() or any(output_dir.iterdir())
    )
    proof_was_nonempty = live_proof_root.exists() and (
        not live_proof_root.is_dir() or any(live_proof_root.iterdir())
    )
    try:
        result = AcceptanceReplayHarness(_ContactsLiveAcceptanceAdapter()).run(
            output_dir,
            profile=profile,
            authorization=authorization,
            generator_config=generator_config,
            generator_http_client=generator_http_client,
            mutation_judge_http_client=mutation_judge_http_client,
            proof_root=live_proof_root,
            max_generator_retries=max_generator_retries,
        )
    except Exception as exc:
        reason_code = _map_reason(
            getattr(exc, "reason_code", "contacts_live_acceptance_failed")
        )
        failure_path = output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME
        frozen_provider_path = output_dir / "trace" / "provider.json"
        if (
            not output_was_nonempty
            and frozen_provider_path.is_file()
            and not frozen_provider_path.is_symlink()
        ):
            _discard_post_freeze_artifacts(
                output_dir,
                authorization=authorization,
                reason_code=reason_code,
                phase=(
                    "replay"
                    if "replay" in reason_code
                    else "proof"
                ),
            )
        elif not output_was_nonempty and not failure_path.is_file():
            _write_early_failure(
                output_dir,
                profile=profile,
                authorization=authorization,
                reason_code=reason_code,
            )
        if not output_was_nonempty and failure_path.is_file():
            _retain_only_failure_record(output_dir)
        if (
            not proof_was_nonempty
            and live_proof_root.is_dir()
            and not live_proof_root.is_symlink()
        ):
            shutil.rmtree(live_proof_root)
        if isinstance(exc, LiveContactsAcceptanceError):
            raise
        raise LiveContactsAcceptanceError(reason_code) from None
    return LiveContactsAcceptanceResult(
        acceptance_dir=result.acceptance_dir,
        proof_path=result.proof_path,
        provider_evidence_path=result.provider_evidence_path,
        replay=result.replay,
        qualification=result.qualification,
    )


def _write_early_failure(
    output_dir: Path,
    *,
    profile: object,
    authorization: object,
    reason_code: str,
) -> None:
    """Write a bounded audit record for failures before recorder creation."""

    if output_dir.exists() and not output_dir.is_dir():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    run_binding: Mapping[str, object] = {}
    attempt_ceiling: int | None = None
    if isinstance(profile, RunProfile):
        try:
            preparation = _ContactsLiveAcceptanceAdapter().prepare(
                profile=profile,
                output_dir=output_dir,
            )
            run_binding = preparation.run_binding
            raw_ceiling = preparation.coverage_plan.attempt_ceiling
            if isinstance(raw_ceiling, int) and not isinstance(raw_ceiling, bool):
                attempt_ceiling = raw_ceiling
        except Exception:
            pass
    try:
        authorization_record = authorization.to_record()
    except Exception:
        authorization_record = {}
    if not isinstance(authorization_record, Mapping):
        authorization_record = {}
    _write_json(
        output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME,
        {
            "schema_version": LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION,
            "status": "failed",
            "reason_code": reason_code,
            "phase": "preparation",
            "authorization": dict(authorization_record),
            "run_binding": dict(run_binding),
            "generator_usage": {
                "logical_calls": 0,
                "tokens": {},
                "retries": 0,
                "physical_calls": 0,
                "physical_call_ceiling": (
                    authorization_record.get("attempt_budget", 0)
                    * (authorization_record.get("generator_retry_limit", 0) + 1)
                    if isinstance(authorization_record.get("attempt_budget"), int)
                    and isinstance(
                        authorization_record.get("generator_retry_limit"), int
                    )
                    else 0
                ),
                "outcomes": {},
                "failure_classes": {},
            },
            "mutation_judge_usage": {
                "attempts": 0,
                "attempt_ceiling": attempt_ceiling,
                "tokens": {},
                "outcomes": {},
                "failure_classes": {},
            },
            "mutation_judge_preflight": {"status": "not_started"},
            "rejections": {"count": 0, "causes": {}, "membership_reasons": {}},
            "non_accepted_attempts": {
                "count": 0,
                "causes": {},
                "membership_reasons": {},
            },
            "provider_evidence_frozen": False,
            "proof_root_published": False,
            "tracer_proof_published": False,
            "qualification": None,
        },
    )


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# Compatibility aliases keep the operator boundary discoverable under either
# adjective order used by callers and documentation.
ContactsLiveAcceptanceAuthorization = LiveContactsAcceptanceAuthorization
ContactsLiveAcceptanceError = LiveContactsAcceptanceError
ContactsLiveAcceptanceResult = LiveContactsAcceptanceResult
ContactsLiveSanitizedProviderEvidenceRecorder = SanitizedProviderEvidenceRecorder
ContactsLiveSanitizedMutationJudgeUsageObserver = SanitizedMutationJudgeUsageObserver
run_contacts_live_acceptance = run_live_contacts_acceptance
sanitize_contacts_provider_response = sanitize_provider_response
validate_contacts_provider_evidence = validate_live_provider_evidence
load_contacts_live_provider_evidence = load_live_provider_evidence
replay_contacts_provider_evidence = replay_sanitized_provider_evidence
verify_contacts_live_acceptance_proof = verify_live_contacts_acceptance_proof
validate_provider_evidence = validate_live_provider_evidence
load_provider_evidence = load_live_provider_evidence


__all__ = [
    "CONTACTS_LIVE_PROOF_FAILURE_FILENAME",
    "DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL",
    "DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS",
    "DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES",
    "DEFAULT_CONTACTS_MUTATION_JUDGE_THINKING_MODE",
    "DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS",
    "CONTACTS_LIVE_ACCEPTANCE_CONTRACT",
    "CONTACTS_LIVE_ACCEPTANCE_SCHEMA_VERSION",
    "CONTACTS_LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION",
    "CONTACTS_LIVE_EVIDENCE_CLASS",
    "LIVE_ACCEPTANCE_SCHEMA_VERSION",
    "LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION",
    "LIVE_EVIDENCE_CLASS",
    "LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION",
    "CONTACTS_LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION",
    "CONTACTS_LIVE_SANITIZED_EVIDENCE_POLICY_VERSION",
    "BoundedSanitizedProvider",
    "build_coverage_attempt_observer_factory",
    "MAX_LIVE_GENERATOR_RETRIES",
    "PROVIDER_PARSER_VERSION",
    "SANITIZED_EVIDENCE_POLICY_VERSION",
    "ContactsLiveAcceptanceAuthorization",
    "ContactsLiveAcceptanceError",
    "ContactsLiveAcceptanceResult",
    "ContactsLiveSanitizedMutationJudgeUsageObserver",
    "ContactsLiveSanitizedProviderEvidenceRecorder",
    "CoverageAssignmentEvidenceObserver",
    "LiveContactsAcceptanceAuthorization",
    "LiveContactsAcceptanceError",
    "LiveContactsAcceptanceResult",
    "SanitizedMutationJudgeUsageObserver",
    "SanitizedProviderEvidenceRecorder",
    "load_live_provider_evidence",
    "load_contacts_live_provider_evidence",
    "load_provider_evidence",
    "replay_contacts_provider_evidence",
    "replay_sanitized_provider_evidence",
    "verify_contacts_live_acceptance_proof",
    "verify_live_contacts_acceptance_proof",
    "run_contacts_live_acceptance",
    "run_live_contacts_acceptance",
    "sanitize_provider_response",
    "sanitize_contacts_provider_response",
    "validate_contacts_provider_evidence",
    "validate_live_provider_evidence",
    "validate_provider_evidence",
]
