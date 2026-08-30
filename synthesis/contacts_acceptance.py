"""Provider-free Contacts acceptance and replay proof.

This module is the Contacts-owned adapter for the pack-neutral acceptance
harness.  It deliberately accepts injected transports only: the later live
acceptance ticket may reuse the adapter, but this proof cannot accidentally
turn a default or test invocation into a provider request.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urlparse

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
    SanitizedMutationJudgeUsageObserver as _NeutralSanitizedMutationJudgeUsageObserver,
    SanitizedProviderEvidenceRecorder as _NeutralSanitizedProviderEvidenceRecorder,
    bounded_reason,
    build_coverage_attempt_observer_factory,
    hash_value,
    load_provider_evidence as _neutral_load_provider_evidence,
    sanitize_provider_response as _neutral_sanitize_provider_response,
    validate_provider_evidence as _neutral_validate_provider_evidence,
)
from synthesis.compatibility import verify_compatibility_corpus
from synthesis.candidate_processing import CandidateExecutionRequest
from synthesis.contacts_domain_pack import (
    ContactsDomainRun,
    build_contacts_domain_pack,
    open_contacts_domain_run,
)
from synthesis.contacts_qualification import (
    CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION,
    CONTACTS_RELEASE_CANDIDATE_PROFILE_ID,
    CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES,
    CONTACTS_RELEASE_TARGET_CANDIDATES,
    qualify_contacts_release_candidate,
    write_contacts_release_candidate_qualification,
)
from synthesis.coverage_assignments import (
    build_coverage_assignment_scheduler_factory,
)
from synthesis.datasets import (
    attach_dataset_release_pack_to_manifest,
    attach_dataset_release_report_to_manifest,
    attach_episode_replay_report_to_manifest,
    attach_evaluation_report_to_manifest,
    attach_profile_decision_report_to_manifest,
    attach_release_quality_audit_to_manifest,
)
from synthesis.domain_pack import DomainAssessment, DomainPackContractError, DomainPlan
from synthesis.domain_sources import build_domain_fixture_source_bundle
from synthesis.episode_replay import write_episode_replay_report
from synthesis.episode_quality import read_episode_logs
from synthesis.evaluation import write_evaluation_report
from synthesis.llm import LLMConfig
from synthesis.mutation_admission import (
    SemanticJudgeRequest,
    build_openai_compatible_semantic_mutation_judge,
)
from synthesis.pipeline import preview_coverage_plan, run_foundation_pipeline
from synthesis.profile_contracts import REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS
from synthesis.profile_decisions import write_profile_decision_report
from synthesis.release_pack import verify_dataset_release_pack, write_dataset_release_pack
from synthesis.release_quality import write_release_quality_audit
from synthesis.run_profiles import RunProfile
from synthesis.sources import SourceGovernanceResult, validate_source_bundle


CONTACTS_ACCEPTANCE_SCHEMA_VERSION = "contacts_provider_free_acceptance_v1"
CONTACTS_PROVIDER_EVIDENCE_SCHEMA_VERSION = "contacts_provider_free_evidence_v1"
CONTACTS_PROOF_SCHEMA_VERSION = "contacts_acceptance_proof_v1"
CONTACTS_PROOF_CASE_SCHEMA_VERSION = "contacts_acceptance_proof_case_v1"
CONTACTS_PROOF_FILENAME = "contacts_acceptance_proof.json"
CONTACTS_EVIDENCE_CLASS = "provider_free_injected"
CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION = (
    "contacts_sanitized_provider_evidence_v1"
)
CONTACTS_PROVIDER_PARSER_VERSION = "domain_generation_parser_v1"
MAX_CONTACTS_GENERATOR_RETRIES = 3

_CONTACTS_ACCEPTANCE_CONTRACT = AcceptanceReplayContract(
    acceptance_schema_version=CONTACTS_ACCEPTANCE_SCHEMA_VERSION,
    provider_evidence_schema_version=CONTACTS_PROVIDER_EVIDENCE_SCHEMA_VERSION,
    evidence_class=CONTACTS_EVIDENCE_CLASS,
    freeze_policy=CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION,
    provider_parser_version=CONTACTS_PROVIDER_PARSER_VERSION,
    replay_result_schema_version="contacts_provider_free_replay_result_v1",
    expected_provider_id="openai_compatible",
    expected_provider_version="openai_compatible_client_v1",
    expected_judge_provider="openai_compatible",
    expected_judge_role="mutation_admission_judge",
    expected_judge_role_version="role_mutation_admission_judge_v1",
    provider_attempt_id_prefix="contacts_provider_attempt",
    mutation_judge_attempt_id_prefix="contacts_mutation_judge_attempt",
    preflight_failure_reason="contacts_mutation_judge_preflight_failed",
    pipeline_failure_reason="contacts_pipeline_failed",
)

_AUTHORIZATION_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,239}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

CONTACTS_PROOF_CASE_EXPECTATIONS: dict[str, tuple[str, str]] = {
    "pack_identity": ("rejected", "contacts_domain_pack_drift"),
    "plan_identity": ("rejected", "contacts_plan_drift"),
    "source_identity": ("rejected", "contacts_source_drift"),
    "runtime_identity": ("rejected", "contacts_runtime_contract_drift"),
    "capability_membership": (
        "rejected",
        "contacts_capability_contract_drift",
    ),
    "assignment_membership": (
        "rejected",
        "contacts_assignment_membership_mismatch",
    ),
    "mutation_admission": (
        "rejected",
        "contacts_mutation_admission_failed",
    ),
    "episode_evidence": ("rejected", "contacts_episode_drift"),
    "verifier_identity": ("rejected", "contacts_verifier_drift"),
    "coverage_evidence": (
        "rejected",
        "contacts_coverage_evidence_incomplete",
    ),
    "assessment_evidence": ("rejected", "contacts_assessment_incomplete"),
    "release_pack": ("rejected", "contacts_release_pack_not_verified"),
    "qualification_dependency": (
        "rejected",
        "contacts_qualification_dependency_invalidated",
    ),
}

CONTACTS_PROOF_SUMMARY: dict[str, object] = {
    "effective_qualification": "release_candidate",
    "fixture_conformance": "passed",
    "publishable": False,
    "training_recommended": False,
    "global_mutation_activation": False,
    "mobile_messages": False,
    "downstream_utility": False,
}


class ContactsAcceptanceError(AcceptanceReplayError):
    """A bounded failure at the provider-free Contacts proof boundary."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


@dataclass(frozen=True)
class ContactsAcceptanceAuthorization:
    """A bounded proof authorization; it carries no provider credential."""

    approved: bool
    authorization_id: str
    candidate_budget: int
    attempt_budget: int
    generator_provider: str
    generator_model: str
    mutation_judge_provider: str
    mutation_judge_model: str
    generator_retry_limit: int = 0
    evidence_policy: str = CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION

    def validate(
        self,
        *,
        profile: Mapping[str, object],
        plan_attempt_ceiling: int,
    ) -> None:
        if not self.approved:
            raise ContactsAcceptanceError("contacts_provider_free_authorization_required")
        if _AUTHORIZATION_ID_RE.fullmatch(self.authorization_id) is None:
            raise ContactsAcceptanceError("contacts_authorization_identity_invalid")
        if self.evidence_policy != CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION:
            raise ContactsAcceptanceError("contacts_sanitized_evidence_policy_required")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (self.candidate_budget, self.attempt_budget)
        ):
            raise ContactsAcceptanceError("contacts_authorization_budget_invalid")
        if (
            not isinstance(self.generator_retry_limit, int)
            or isinstance(self.generator_retry_limit, bool)
            or self.generator_retry_limit not in range(MAX_CONTACTS_GENERATOR_RETRIES + 1)
        ):
            raise ContactsAcceptanceError("contacts_generator_retry_budget_invalid")
        if (
            not isinstance(plan_attempt_ceiling, int)
            or isinstance(plan_attempt_ceiling, bool)
            or plan_attempt_ceiling <= 0
            or plan_attempt_ceiling > self.attempt_budget
        ):
            raise ContactsAcceptanceError("contacts_attempt_budget_exceeded")

        generation = profile.get("generation")
        seed = profile.get("seed")
        features = profile.get("features")
        mutation = profile.get("mutation_admission")
        coverage = profile.get("coverage_profile")
        if (
            profile.get("schema_version") not in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS
            or profile.get("profile_id") != CONTACTS_RELEASE_CANDIDATE_PROFILE_ID
            or profile.get("dataset_version") != CONTACTS_RELEASE_CANDIDATE_DATASET_VERSION
            or profile.get("profile_purpose") != "release_candidate"
            or not isinstance(generation, Mapping)
            or generation.get("mode") != "foundation_fixture"
            or generation.get("target_candidate_count") != CONTACTS_RELEASE_TARGET_CANDIDATES
            or not isinstance(seed, Mapping)
            or seed.get("domain") != "contacts_fixture"
            or seed.get("seed_id") != "seed_contacts_release_candidate_v1"
            or seed.get("task_taxonomy")
            != [
                "contact_lookup",
                "contact_followup",
                "contact_lookup_recovery",
            ]
            or not isinstance(features, Mapping)
            or features.get("enable_branching") is not True
            or not isinstance(mutation, Mapping)
            or mutation.get("mode") != "enforce"
            or not isinstance(coverage, Mapping)
            or coverage.get("profile_id") != "contacts_representative"
            or coverage.get("version") != "contacts_representative_v1"
            or coverage.get("target_accepted_sample_count")
            != CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES
        ):
            raise ContactsAcceptanceError("contacts_release_profile_invalid")
        if self.candidate_budget < int(generation["target_candidate_count"]):
            raise ContactsAcceptanceError("contacts_candidate_budget_exceeded")
        judge = mutation.get("judge")
        if not isinstance(judge, Mapping):
            raise ContactsAcceptanceError("contacts_mutation_judge_identity_required")
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
            raise ContactsAcceptanceError("contacts_mutation_judge_identity_not_independent")

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
            "generator_retry_limit": self.generator_retry_limit,
            "evidence_policy": self.evidence_policy,
        }


class ContactsSanitizedProviderEvidenceRecorder(_NeutralSanitizedProviderEvidenceRecorder):
    """Contacts facade over the neutral recorder with Contacts schemas."""

    def __init__(
        self,
        *,
        authorization: ContactsAcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> None:
        super().__init__(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=mutation_judge_identity,
            contract=_CONTACTS_ACCEPTANCE_CONTRACT,
        )


class ContactsSanitizedMutationJudgeUsageObserver(
    _NeutralSanitizedMutationJudgeUsageObserver
):
    def __init__(self, *, attempt_ceiling: int | None = None) -> None:
        super().__init__(
            attempt_ceiling=attempt_ceiling,
            attempt_id_prefix="contacts_mutation_judge_attempt",
        )


# Short names make the Contacts seam easy to discover while the long names
# communicate the retention boundary in generated documentation.
SanitizedProviderEvidenceRecorder = ContactsSanitizedProviderEvidenceRecorder
SanitizedMutationJudgeUsageObserver = ContactsSanitizedMutationJudgeUsageObserver


def sanitize_contacts_provider_response(response: object) -> dict[str, object]:
    try:
        return _neutral_sanitize_provider_response(response)
    except AcceptanceReplayError as exc:
        raise ContactsAcceptanceError(exc.reason_code) from None


def validate_contacts_provider_evidence(
    evidence: Mapping[str, object],
    *,
    contract: AcceptanceReplayContract = _CONTACTS_ACCEPTANCE_CONTRACT,
) -> None:
    try:
        _neutral_validate_provider_evidence(
            evidence,
            contract=contract,
        )
    except AcceptanceReplayError as exc:
        raise ContactsAcceptanceError(_map_reason(exc.reason_code)) from None


def load_contacts_provider_evidence(
    path: Path,
    *,
    contract: AcceptanceReplayContract = _CONTACTS_ACCEPTANCE_CONTRACT,
) -> dict[str, object]:
    try:
        return _neutral_load_provider_evidence(
            path,
            contract=contract,
        )
    except AcceptanceReplayError as exc:
        raise ContactsAcceptanceError(_map_reason(exc.reason_code)) from None


def _map_reason(reason_code: str) -> str:
    return {
        "acceptance_identity_malformed": "contacts_acceptance_identity_malformed",
        "acceptance_identity_mismatch": "contacts_acceptance_identity_mismatch",
        "acceptance_binding_malformed": "contacts_run_binding_malformed",
        "acceptance_binding_mismatch": "contacts_run_binding_mismatch",
        "acceptance_evidence_malformed": "contacts_provider_evidence_malformed",
        "acceptance_evidence_missing": "contacts_provider_evidence_missing",
        "acceptance_replay_input_malformed": "contacts_replay_input_malformed",
        "acceptance_replay_input_mismatch": "contacts_replay_input_mismatch",
        "acceptance_replay_inputs_missing": "contacts_replay_inputs_missing",
        "acceptance_replay_failed": "contacts_replay_contract_failed",
        "acceptance_replay_count_mismatch": "contacts_replay_count_mismatch",
        "acceptance_release_evidence_missing": "contacts_release_evidence_missing",
        "acceptance_release_path_unsafe": "contacts_release_path_unsafe",
        "acceptance_release_identity_mismatch": "contacts_release_identity_mismatch",
        "release_pack_not_independently_verified": "contacts_release_pack_not_verified",
        "real_release_candidate_not_verified": "contacts_release_candidate_not_verified",
        "qualification_evidence_not_freezable": "contacts_qualification_not_freezable",
        "acceptance_proof_failed": "contacts_acceptance_proof_failed",
    }.get(reason_code, reason_code)


def _safe_provider_host(base_url: object) -> str:
    if not isinstance(base_url, str) or not base_url:
        return "unconfigured"
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


def _generator_identity(config: LLMConfig) -> dict[str, object]:
    lineage = config.lineage("task_generation")
    return {
        "provider_id": "openai_compatible",
        "provider_version": "openai_compatible_client_v1",
        "provider_host": _safe_provider_host(config.base_url),
        "model": config.model,
        "config_hash": lineage["config_hash"],
        "parser_version": CONTACTS_PROVIDER_PARSER_VERSION,
    }


def _mutation_judge_identity(profile: object, config: LLMConfig) -> dict[str, object]:
    judge = profile.mutation_admission.judge
    if judge is None:
        raise ContactsAcceptanceError("contacts_mutation_judge_identity_required")
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


def _contacts_run_binding(
    *,
    profile: RunProfile,
    plan: object,
    coverage_plan: object,
    source_result: SourceGovernanceResult,
) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "dataset_version": profile.dataset_version,
        "seed_id": profile.seed.seed_id,
        "seed_domain": profile.seed.domain,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "coverage_plan_id": coverage_plan.plan_id,
        "coverage_plan_hash": coverage_plan.plan_hash,
        "source_policy_hash": source_result.source_policy_hash,
    }


def _contacts_preflight_request() -> SemanticJudgeRequest:
    return SemanticJudgeRequest(
        instruction=(
            "Find Alice Zhang's email and record a follow-up to send "
            "alice.zhang@example.test."
        ),
        task_type="contact_followup",
        action_type="contact_followup_record",
        action_evidence_text="record a follow-up to send alice.zhang@example.test",
        argument_values={
            "name": "Alice Zhang",
            "note": "Send follow-up email to alice.zhang@example.test.",
        },
        argument_evidence={
            "name": {
                "name": "Alice Zhang",
                "source_arguments": {"name": "Alice Zhang"},
            },
            "note": "record a follow-up to send alice.zhang@example.test",
        },
        argument_origins={"name": "tool_observation", "note": "instruction"},
        evidence_references={
            "action": "contacts_preflight_action",
            "name": "contacts_preflight_name",
            "note": "contacts_preflight_note",
        },
    )


def _preflight_contacts_mutation_judge(
    *,
    profile: object,
    generator_config: LLMConfig,
    http_client: object | None,
    observer: ContactsSanitizedMutationJudgeUsageObserver,
) -> dict[str, object]:
    judge_config = profile.mutation_admission.judge
    if judge_config is None:
        raise ContactsAcceptanceError("contacts_mutation_judge_identity_required")
    judge = build_openai_compatible_semantic_mutation_judge(
        config=LLMConfig(
            base_url=generator_config.base_url,
            api_key=generator_config.api_key,
            model=judge_config.model,
            temperature=0.0,
        ),
        http_client=http_client,
        timeout_seconds=float(judge_config.timeout_seconds),
        max_retries=int(judge_config.max_retries),
        thinking_mode=getattr(judge_config, "thinking_mode", None),
        attempt_observer=observer,
    )
    result = judge(_contacts_preflight_request())
    verdict = result.verdict
    return {
        "status": (
            "passed"
            if result.provider_outcome == "succeeded"
            and isinstance(verdict, Mapping)
            and verdict.get("verdict") == "supported"
            else "failed"
        ),
        "provider_outcome": result.provider_outcome,
        "attempts": result.attempts,
    }


def _mutation_judge_attempt_ceiling(profile: object, coverage_plan: object) -> int:
    judge = profile.mutation_admission.judge
    retry_count = getattr(judge, "max_retries", None)
    attempt_ceiling = getattr(coverage_plan, "attempt_ceiling", None)
    if (
        not isinstance(retry_count, int)
        or isinstance(retry_count, bool)
        or retry_count not in {0, 1}
        or not isinstance(attempt_ceiling, int)
        or isinstance(attempt_ceiling, bool)
        or attempt_ceiling <= 0
    ):
        raise ContactsAcceptanceError("contacts_authorization_budget_invalid")
    return (attempt_ceiling + 1) * (retry_count + 1)


def _read_json(path: Path, reason_code: str = "contacts_artifact_unreadable") -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContactsAcceptanceError(reason_code) from exc
    if not isinstance(value, Mapping):
        raise ContactsAcceptanceError("contacts_artifact_malformed")
    return dict(value)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class _ContactsAcceptanceAdapter:
    evidence_contract = _CONTACTS_ACCEPTANCE_CONTRACT

    def __init__(self) -> None:
        self._profile: RunProfile | None = None
        self._output_dir: Path | None = None

    def error_for_reason(self, reason_code: str) -> ContactsAcceptanceError:
        return ContactsAcceptanceError(_map_reason(reason_code))

    def prepare(self, *, profile: object, output_dir: Path) -> AcceptancePreparation:
        if not isinstance(profile, RunProfile):
            raise ContactsAcceptanceError("contacts_release_profile_invalid")
        self._profile = profile
        self._output_dir = output_dir
        if profile.profile_id != CONTACTS_RELEASE_CANDIDATE_PROFILE_ID:
            raise ContactsAcceptanceError("contacts_release_profile_invalid")
        source_bundle = build_domain_fixture_source_bundle(profile.seed.domain)
        try:
            source_result = validate_source_bundle(source_bundle)
        except Exception as exc:
            raise ContactsAcceptanceError("contacts_source_drift") from exc
        from synthesis.contacts_domain_pack import (
            admitted_contacts_source,
            build_contacts_domain_pack,
            contacts_planning_intent,
        )

        pack = build_contacts_domain_pack()
        admitted_source = admitted_contacts_source(source_bundle, source_result)
        plan = pack.plan(contacts_planning_intent(pack), admitted_source)
        if not isinstance(plan, DomainPlan):
            raise ContactsAcceptanceError("contacts_plan_not_admitted")
        coverage_plan = preview_coverage_plan(
            profile,
            output_path=output_dir / "coverage_plan_preflight.json",
        )
        preparation = AcceptancePreparation(
            profile_record=profile.canonical(),
            plan=plan,
            coverage_plan=coverage_plan,
            source_policy_hash=source_result.source_policy_hash,
            run_binding=_contacts_run_binding(
                profile=profile,
                plan=plan,
                coverage_plan=coverage_plan,
                source_result=source_result,
            ),
        )
        return preparation

    def validate_authorization(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        authorization: AcceptanceAuthorization,
        max_generator_retries: int,
    ) -> None:
        del profile
        authorization.validate(
            profile=preparation.profile_record,
            plan_attempt_ceiling=int(preparation.coverage_plan.attempt_ceiling),
        )
        if max_generator_retries != authorization.generator_retry_limit:
            raise ContactsAcceptanceError("contacts_generator_retry_authorization_mismatch")

    def resolve_generator_config(self, supplied: object | None) -> object:
        if not isinstance(supplied, LLMConfig) or not supplied.configured:
            raise ContactsAcceptanceError("contacts_injected_generator_config_required")
        return supplied

    def validate_generator_config(
        self,
        *,
        profile: object,
        authorization: AcceptanceAuthorization,
        config: object,
    ) -> None:
        if not isinstance(config, LLMConfig) or not config.configured:
            raise ContactsAcceptanceError("contacts_injected_generator_config_required")
        if config.model != authorization.generator_model:
            raise ContactsAcceptanceError("contacts_generator_identity_mismatch")
        judge = profile.mutation_admission.judge
        if judge is None or judge.model != authorization.mutation_judge_model:
            raise ContactsAcceptanceError("contacts_mutation_judge_identity_mismatch")

    def generator_identity(self, config: object) -> Mapping[str, object]:
        if not isinstance(config, LLMConfig):
            raise ContactsAcceptanceError("contacts_injected_generator_config_required")
        return _generator_identity(config)

    def mutation_judge_identity(
        self,
        *,
        profile: object,
        config: object,
    ) -> Mapping[str, object]:
        if not isinstance(config, LLMConfig):
            raise ContactsAcceptanceError("contacts_injected_generator_config_required")
        return _mutation_judge_identity(profile, config)

    def create_recorder(
        self,
        *,
        authorization: AcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> AcceptanceEvidenceRecorder:
        if not isinstance(authorization, ContactsAcceptanceAuthorization):
            raise ContactsAcceptanceError("contacts_acceptance_authorization_malformed")
        return ContactsSanitizedProviderEvidenceRecorder(
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
        return ContactsSanitizedMutationJudgeUsageObserver(
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
            observer, ContactsSanitizedMutationJudgeUsageObserver
        ):
            raise ContactsAcceptanceError("contacts_acceptance_preflight_malformed")
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
        from synthesis.llm import OpenAICompatibleClient

        if not isinstance(config, LLMConfig):
            raise ContactsAcceptanceError("contacts_injected_generator_config_required")
        if http_client is None:
            raise ContactsAcceptanceError("contacts_injected_generator_transport_required")
        return BoundedSanitizedProvider(
            OpenAICompatibleClient(
                config,
                http_client=http_client,
                max_retries=max_generator_retries,
            ),
            recorder=recorder,  # type: ignore[arg-type]
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
            raise ContactsAcceptanceError("contacts_pipeline_configuration_invalid")
        if not isinstance(recorder, ContactsSanitizedProviderEvidenceRecorder) or not isinstance(
            observer, ContactsSanitizedMutationJudgeUsageObserver
        ):
            raise ContactsAcceptanceError("contacts_pipeline_evidence_recorder_invalid")
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
        result = pipeline.result
        if pipeline.accepted_count < CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES:
            raise ContactsAcceptanceError("contacts_coverage_evidence_incomplete")
        if (
            result.episode_logs_path is None
            or result.coverage_plan_path is None
            or result.coverage_evidence_path is None
        ):
            raise ContactsAcceptanceError("contacts_run_completeness_incomplete")

    def mutation_judge_attempt_ceiling(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> int:
        return _mutation_judge_attempt_ceiling(profile, preparation.coverage_plan)

    def write_release_evidence(
        self,
        *,
        output_dir: Path,
        profile: object,
        pipeline: AcceptancePipelineResult,
        runtime_seconds: float,
    ) -> AcceptanceReleaseEvidence:
        if not isinstance(profile, RunProfile):
            raise ContactsAcceptanceError("contacts_release_profile_invalid")
        result = pipeline.result
        if result.episode_logs_path is None:
            raise ContactsAcceptanceError("contacts_run_completeness_incomplete")
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
        from synthesis.dataset_release import write_dataset_release_report

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
        pack_verification_record = verify_dataset_release_pack(pack_path)
        verification = pack_verification_record.get("verification")
        if not isinstance(verification, Mapping) or verification.get("status") != "passed":
            raise ContactsAcceptanceError("contacts_release_pack_not_verified")
        _write_json(output_dir / "release_pack_verification.json", pack_verification_record)
        qualification_path = output_dir / "qualification_report.json"
        write_contacts_release_candidate_qualification(
            manifest_path=result.manifest_path,
            release_pack_path=pack_path,
            release_quality_audit_path=audit_path,
            output_path=qualification_path,
        )
        qualification = _read_json(qualification_path)
        return AcceptanceReleaseEvidence(
            replay_report_path=replay_path,
            evaluation_report_path=evaluation_path,
            profile_decision_path=profile_decision_path,
            dataset_release_report_path=dataset_release_report_path,
            release_quality_audit_path=audit_path,
            release_pack_path=pack_path,
            release_pack_verification=verification,
            qualification=qualification,
            release_pack_hash="sha256:" + hashlib.sha256(pack_path.read_bytes()).hexdigest(),
        )

    def bind_sample_assignments(
        self,
        *,
        recorder: AcceptanceEvidenceRecorder,
        pipeline: AcceptancePipelineResult,
    ) -> None:
        result = pipeline.result
        try:
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ContactsAcceptanceError("contacts_artifact_unreadable") from exc
        assignments: dict[str, Mapping[str, object]] = {}
        for sample in samples:
            if not isinstance(sample, Mapping):
                continue
            evidence = sample.get("contacts_evidence", sample.get("domain_evidence"))
            assignment = evidence.get("assignment") if isinstance(evidence, Mapping) else None
            if isinstance(assignment, Mapping) and isinstance(
                assignment.get("assignment_id"), str
            ):
                assignments[str(assignment["assignment_id"])] = assignment
        bind = getattr(recorder, "bind_sample_assignments", None)
        if not callable(bind):
            raise ContactsAcceptanceError("contacts_assignment_binding_unavailable")
        bind(assignments)

    def replay(
        self,
        *,
        evidence: Mapping[str, object],
        preparation: AcceptancePreparation,
    ) -> int | Mapping[str, object]:
        if self._profile is None or self._output_dir is None:
            raise ContactsAcceptanceError("contacts_replay_context_missing")
        return replay_contacts_provider_evidence(
            evidence,
            profile=self._profile,
            plan=preparation.plan,
            acceptance_dir=self._output_dir,
        )

    def build_proof(self, *, proof_root: Path, acceptance_dir: Path) -> Path:
        return build_contacts_acceptance_proof(proof_root, acceptance_dir)

    def verify_proof(self, proof_path: Path) -> Mapping[str, object]:
        result = verify_contacts_acceptance_proof(proof_path)
        if result.get("status") != "passed":
            reasons = result.get("reason_codes")
            reason = (
                str(reasons[0])
                if isinstance(reasons, list) and reasons and isinstance(reasons[0], str)
                else "contacts_acceptance_proof_failed"
            )
            raise ContactsAcceptanceError(reason, str(result.get("detail", reason)))
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
        if not isinstance(authorization, ContactsAcceptanceAuthorization):
            raise ContactsAcceptanceError("contacts_acceptance_authorization_malformed")
        if not isinstance(observer, ContactsSanitizedMutationJudgeUsageObserver):
            raise ContactsAcceptanceError("contacts_acceptance_usage_malformed")
        rejection_summary = _bounded_rejection_summary(rejections_path)
        qualification_summary = None
        if isinstance(qualification, Mapping):
            qualification_summary = {
                "status": qualification.get("status"),
                "effective_qualification": qualification.get("effective_qualification"),
            }
        record = {
            "schema_version": "contacts_acceptance_failure_v1",
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
            "provider_evidence_frozen": False,
            "proof_root_published": False,
            "qualification": qualification_summary,
        }
        destination = output_dir / "contacts_acceptance_failure.json"
        _write_json(destination, record)
        return destination


def _bounded_rejection_summary(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file() or path.is_symlink():
        return {"count": 0, "causes": {}}
    causes: dict[str, int] = {}
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
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {"count": 0, "causes": {"rejection_summary_unavailable": 1}}
    return {"count": count, "causes": dict(sorted(causes.items()))}


def _generator_usage_summary(
    recorder: AcceptanceEvidenceRecorder,
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
        "physical_calls": len(attempts) + retries,
        "retries": retries,
        "outcomes": {
            outcome: sum(record.get("outcome") == outcome for record in attempts)
            for outcome in sorted({str(record.get("outcome")) for record in attempts})
        },
    }


@dataclass(frozen=True)
class ContactsAcceptanceResult:
    acceptance_dir: Path
    proof_path: Path
    provider_evidence_path: Path
    replay: Mapping[str, object]
    qualification: Mapping[str, object]


def run_contacts_acceptance_proof(
    output_dir: Path,
    *,
    profile: RunProfile,
    authorization: ContactsAcceptanceAuthorization,
    generator_config: LLMConfig,
    generator_http_client: object,
    mutation_judge_http_client: object,
    proof_root: Path | None = None,
    max_generator_retries: int | None = None,
) -> ContactsAcceptanceResult:
    """Run the Contacts proof with explicitly injected transports only."""

    output_dir = Path(output_dir)
    output_was_nonempty = output_dir.exists() and (
        not output_dir.is_dir() or any(output_dir.iterdir())
    )
    proof_was_nonempty = proof_root is not None and Path(proof_root).exists() and (
        not Path(proof_root).is_dir() or any(Path(proof_root).iterdir())
    )
    proof_path = (
        Path(proof_root)
        if proof_root is not None
        else output_dir.parent / (output_dir.name + "-proof")
    )
    if generator_http_client is None or mutation_judge_http_client is None:
        if not output_was_nonempty:
            _write_early_failure(
                output_dir,
                profile=profile,
                authorization=authorization,
                reason_code="contacts_injected_transport_required",
            )
        raise ContactsAcceptanceError("contacts_injected_transport_required")
    try:
        result = AcceptanceReplayHarness(_ContactsAcceptanceAdapter()).run(
            output_dir,
            profile=profile,
            authorization=authorization,
            generator_config=generator_config,
            generator_http_client=generator_http_client,
            mutation_judge_http_client=mutation_judge_http_client,
            proof_root=proof_root,
            max_generator_retries=max_generator_retries,
        )
    except ContactsAcceptanceError as exc:
        if (
            not output_was_nonempty
            and not (output_dir / "contacts_acceptance_failure.json").is_file()
        ):
            _write_early_failure(
                output_dir,
                profile=profile,
                authorization=authorization,
                reason_code=exc.reason_code,
            )
        if not proof_was_nonempty and proof_path.is_dir() and not proof_path.is_symlink():
            shutil.rmtree(proof_path)
        raise
    except Exception as exc:
        reason = _map_reason(getattr(exc, "reason_code", "contacts_acceptance_failed"))
        if not output_was_nonempty:
            _write_early_failure(
                output_dir,
                profile=profile,
                authorization=authorization,
                reason_code=reason,
            )
        if not proof_was_nonempty and proof_path.is_dir() and not proof_path.is_symlink():
            shutil.rmtree(proof_path)
        raise ContactsAcceptanceError(reason) from None
    return ContactsAcceptanceResult(
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
    """Write a bounded record when the neutral harness fails before recording."""

    if output_dir.exists() and not output_dir.is_dir():
        return
    preparation: AcceptancePreparation | None = None
    if isinstance(profile, RunProfile):
        try:
            preparation = _ContactsAcceptanceAdapter().prepare(
                profile=profile,
                output_dir=output_dir,
            )
        except Exception:
            preparation = None
    try:
        authorization_record = authorization.to_record()
    except Exception:
        authorization_record = {}
    if not isinstance(authorization_record, Mapping):
        authorization_record = {}
    run_binding = (
        dict(preparation.run_binding)
        if preparation is not None
        else {}
    )
    attempt_ceiling = (
        preparation.coverage_plan.attempt_ceiling
        if preparation is not None
        and isinstance(preparation.coverage_plan.attempt_ceiling, int)
        else None
    )
    _write_json(
        output_dir / "contacts_acceptance_failure.json",
        {
            "schema_version": "contacts_acceptance_failure_v1",
            "status": "failed",
            "reason_code": reason_code,
            "phase": "preparation",
            "authorization": dict(authorization_record),
            "run_binding": run_binding,
            "generator_usage": {
                "logical_calls": 0,
                "physical_calls": 0,
                "retries": 0,
                "outcomes": {},
            },
            "mutation_judge_usage": {
                "attempts": 0,
                "attempt_ceiling": attempt_ceiling,
                "tokens": {},
                "outcomes": {},
            },
            "mutation_judge_preflight": {"status": "not_started"},
            "rejections": {"count": 0, "causes": {}},
            "provider_evidence_frozen": False,
            "proof_root_published": False,
            "qualification": None,
        },
    )


def replay_contacts_provider_evidence(
    evidence: Mapping[str, object] | Path,
    *,
    profile: RunProfile,
    plan: object,
    acceptance_dir: Path,
    contract: AcceptanceReplayContract = _CONTACTS_ACCEPTANCE_CONTRACT,
) -> dict[str, object]:
    """Replay sanitized Contacts responses through production contracts."""

    loaded = (
        load_contacts_provider_evidence(evidence, contract=contract)
        if isinstance(evidence, Path)
        else dict(evidence)
    )
    if not isinstance(evidence, Path):
        validate_contacts_provider_evidence(loaded, contract=contract)
    if not isinstance(plan, DomainPlan):
        raise ContactsAcceptanceError("contacts_plan_not_admitted")
    source_bundle = build_domain_fixture_source_bundle(profile.seed.domain)
    source_result = validate_source_bundle(source_bundle)
    with tempfile.TemporaryDirectory(prefix="contacts-provider-replay-") as tmpdir:
        run = open_contacts_domain_run(
            source_bundle=source_bundle,
            source_result=source_result,
            output_dir=Path(tmpdir),
            include_branching=True,
        )
        if not isinstance(run, ContactsDomainRun) or run.plan != plan:
            raise ContactsAcceptanceError("contacts_plan_drift")

        replay = _replay_contacts_attempts(
            loaded=loaded,
            profile=profile,
            run=run,
            contract=contract,
        )
        return {
            **replay,
            **_replay_release_outcomes(
                acceptance_dir=Path(acceptance_dir),
                profile=profile,
                plan=plan,
            ),
        }


def _replay_contacts_attempts(
    *,
    loaded: Mapping[str, object],
    profile: RunProfile,
    run: ContactsDomainRun,
    contract: AcceptanceReplayContract,
) -> dict[str, object]:
    attempts = loaded.get("attempts")
    replay_attempts = loaded.get("replay_attempts")
    if (
        not isinstance(attempts, list)
        or not attempts
        or not isinstance(replay_attempts, list)
        or not replay_attempts
    ):
        raise ContactsAcceptanceError("contacts_replay_inputs_missing")

    from synthesis.domain_generation import (
        build_generation_batch_context,
        parse_domain_task_contracts,
    )
    from synthesis.coverage_assignments import (
        _assignment_generation_spec,
        _build_coverage_assignment,
        _single_provider_record,
        _validate_assignment_membership,
        _with_locally_derived_difficulty,
    )
    from synthesis.coverage_registry import resolve_domain_coverage_planning
    from synthesis.execution import scripted_solution_policy
    from synthesis.llm import LLMConfig

    coverage_plan = preview_coverage_plan(profile)
    catalog_version = coverage_plan.catalog.get("version")
    if not isinstance(catalog_version, str):
        raise ContactsAcceptanceError("contacts_coverage_plan_drift")
    try:
        catalog = resolve_domain_coverage_planning(
            profile.seed.domain
        ).resolve_catalog(catalog_version)
    except Exception as exc:
        raise ContactsAcceptanceError("contacts_coverage_plan_drift") from exc
    if run.generation_spec is None:
        raise ContactsAcceptanceError("contacts_generation_contract_missing")
    cells = {cell.cell_id: cell for cell in catalog.cells}
    provider_identity = loaded.get("provider")
    if not isinstance(provider_identity, Mapping):
        raise ContactsAcceptanceError("contacts_provider_evidence_malformed")
    replay_generator_lineage = {
        "role": "task_generation",
        "role_version": "role_task_generation_v1",
        "provider_host": provider_identity.get("provider_host"),
        "model": provider_identity.get("model"),
        "config_hash": provider_identity.get("config_hash"),
    }
    if any(
        not isinstance(value, str) or not value
        for value in replay_generator_lineage.values()
    ):
        raise ContactsAcceptanceError("contacts_provider_evidence_malformed")

    processed = 0
    replayed_contracts = 0
    accepted = 0
    rejected = 0
    for raw_attempt in attempts:
        if not isinstance(raw_attempt, Mapping):
            raise ContactsAcceptanceError("contacts_replay_input_malformed")
        attempt_outcome = raw_attempt.get("outcome")
        if attempt_outcome not in {"provider_error", "rejected", "validated"}:
            raise ContactsAcceptanceError("contacts_replay_input_malformed")
        assignment = raw_attempt.get("assignment")
        assignment_lineage = raw_attempt.get("assignment_lineage")
        response = raw_attempt.get("response")
        if not isinstance(assignment, Mapping) or not isinstance(
            assignment_lineage, Mapping
        ):
            raise ContactsAcceptanceError("contacts_replay_input_malformed")
        if assignment.get("assignment_id") != raw_attempt.get("assignment_id"):
            raise ContactsAcceptanceError("contacts_assignment_membership_mismatch")
        if assignment_lineage.get("assignment_id") != raw_attempt.get("assignment_id"):
            raise ContactsAcceptanceError("contacts_assignment_membership_mismatch")
        ordinal = assignment.get("assignment_ordinal")
        cell_id = assignment.get("cell_id")
        grounding_scope = assignment.get("grounding_scope")
        grounding_index = (
            grounding_scope.get("unit_index")
            if isinstance(grounding_scope, Mapping)
            else None
        )
        cell = cells.get(cell_id) if isinstance(cell_id, str) else None
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 0
            or cell is None
            or not isinstance(grounding_index, int)
            or isinstance(grounding_index, bool)
            or grounding_index < 0
        ):
            raise ContactsAcceptanceError("contacts_assignment_membership_mismatch")
        try:
            expected_assignment = _build_coverage_assignment(
                plan=coverage_plan,
                catalog=catalog,
                cell=cell,
                assignment_ordinal=ordinal,
                grounding_index=grounding_index,
                spec=run.generation_spec,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContactsAcceptanceError(
                "contacts_assignment_membership_mismatch"
            ) from exc
        if (
            dict(assignment) != expected_assignment.provider_contract()
            or dict(assignment_lineage) != expected_assignment.lineage()
        ):
            raise ContactsAcceptanceError("contacts_assignment_membership_mismatch")
        if attempt_outcome == "provider_error":
            if response is not None:
                raise ContactsAcceptanceError("contacts_replay_input_mismatch")
            processed += 1
            continue
        if not isinstance(response, Mapping):
            raise ContactsAcceptanceError("contacts_replay_input_malformed")
        # The run-owned generation spec is used by the production parser; the
        # assignment lineage then makes Contacts membership re-validate the
        # exact issued plan, grounding, capabilities, and recovery branch.
        assignment_spec = _assignment_generation_spec(
            run.generation_spec,
            expected_assignment,
        )
        batch_context = build_generation_batch_context(
            assignment_spec,
            batch_index=ordinal + 1,
        )
        try:
            raw_record = _single_provider_record(response)
            generation_lineage = {
                **replay_generator_lineage,
                "coverage_assignment": expected_assignment.lineage(),
            }
            contracts = parse_domain_task_contracts(
                response,
                seed=profile.seed,
                spec=assignment_spec,
                batch_context=batch_context,
                generation_lineage=generation_lineage,
            )
            if len(contracts) == 1:
                validated_contract = _validate_assignment_membership(
                    raw_record=raw_record,
                    contract=contracts[0],
                    assignment=expected_assignment,
                    assignment_spec=assignment_spec,
                    seed=profile.seed,
                    batch_context=batch_context,
                    generation_lineage=generation_lineage,
                )
                validated_contract = _with_locally_derived_difficulty(
                    validated_contract,
                    expected_assignment,
                )
                contracts = [validated_contract]
        except Exception as exc:
            if attempt_outcome == "rejected":
                processed += 1
                rejected += 1
                continue
            raise ContactsAcceptanceError("contacts_provider_contract_rejected") from exc
        if len(contracts) != 1:
            if attempt_outcome == "rejected":
                processed += 1
                rejected += 1
                continue
            raise ContactsAcceptanceError("contacts_provider_contract_rejected")
        from synthesis.task_contracts import candidate_from_task_contract

        candidate = candidate_from_task_contract(contracts[0])
        outcome = run.attempt(
            CandidateExecutionRequest(
                sequence_index=ordinal,
                raw_task=candidate,
            ),
            dataset_version=profile.dataset_version,
            llm_config=LLMConfig(
                base_url=None,
                api_key=None,
                model="contacts-provider-free-replay",
            ),
            policy_generator=scripted_solution_policy,
            admission_evaluator=run.build_admission_evaluator(
                mode="enforce",
                judge=run.default_mutation_judge(),
            ),
        )
        if outcome.outcome.sample is not None:
            accepted += 1
        else:
            rejected += 1
        if attempt_outcome == "rejected" and outcome.outcome.sample is not None:
            raise ContactsAcceptanceError("contacts_replay_outcome_mismatch")
        if attempt_outcome == "validated" and outcome.outcome.sample is None:
            raise ContactsAcceptanceError("contacts_replay_outcome_mismatch")
        if attempt_outcome == "validated":
            replayed_contracts += 1
        if outcome.replay_subject is not None:
            replayed = run.replay(outcome.replay_subject)
            if replayed.status != "passed":
                raise ContactsAcceptanceError(
                    "contacts_replay_contract_failed"
                )
        processed += 1
    return {
        "schema_version": contract.replay_result_schema_version,
        "status": "passed",
        "reason_code": "contacts_replay_verified",
        "replayed_attempt_count": replayed_contracts,
        "processed_attempt_count": processed,
        "accepted_attempt_count": accepted,
        "rejected_attempt_count": rejected,
        "provider_calls": 0,
        "evidence_class": contract.evidence_class,
    }


def _replay_release_outcomes(
    *,
    acceptance_dir: Path,
    profile: RunProfile,
    plan: DomainPlan,
) -> dict[str, object]:
    """Re-run release boundaries while keeping the replay provider-free."""

    coverage_path = acceptance_dir / "coverage_evidence.json"
    if not coverage_path.is_file() or coverage_path.is_symlink():
        raise ContactsAcceptanceError("contacts_coverage_evidence_incomplete")
    try:
        coverage = _read_json(coverage_path)
        from synthesis.coverage_evidence import validate_coverage_evidence_record

        validate_coverage_evidence_record(coverage)
    except (ContactsAcceptanceError, TypeError, ValueError):
        raise ContactsAcceptanceError("contacts_coverage_evidence_incomplete") from None
    fulfillment = _mapping(coverage.get("fulfillment"), "contacts_coverage_fulfillment")
    if fulfillment.get("status") != "fulfilled":
        raise ContactsAcceptanceError("contacts_coverage_evidence_incomplete")

    pack_path = acceptance_dir / "dataset_release_pack.json"
    if not pack_path.is_file() or pack_path.is_symlink():
        raise ContactsAcceptanceError("contacts_release_pack_not_verified")
    pack_verification = verify_dataset_release_pack(pack_path)
    if _mapping(
        pack_verification.get("verification"),
        "contacts_release_pack_verification",
    ).get("status") != "passed":
        raise ContactsAcceptanceError("contacts_release_pack_not_verified")
    qualification = qualify_contacts_release_candidate(
        manifest_path=acceptance_dir / "manifest.json",
        release_pack_path=pack_path,
        release_quality_audit_path=acceptance_dir / "release_quality_audit.json",
    )
    if (
        qualification.get("status") != "passed"
        or qualification.get("effective_qualification") != "release_candidate"
    ):
        raise ContactsAcceptanceError("contacts_qualification_not_verified")
    assessment = _assessment_from_qualification(qualification, plan)
    if assessment.status != "established":
        raise ContactsAcceptanceError("contacts_assessment_incomplete")
    return {
        "coverage": {
            "status": "passed",
            "fulfillment": fulfillment.get("status"),
            "evidence_id": coverage.get("evidence_id"),
        },
        "assessment": {
            "status": "passed",
            "assessment_id": assessment.assessment_id,
            "assessment_hash": assessment.assessment_hash,
        },
        "qualification": {
            "status": "passed",
            "effective_qualification": qualification.get(
                "effective_qualification"
            ),
            "release_pack_hash": _file_hash(pack_path)[0],
        },
    }


def _file_hash(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    return "sha256:" + hashlib.sha256(content).hexdigest(), len(content)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ContactsAcceptanceError("contacts_acceptance_missing")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ContactsAcceptanceError("contacts_acceptance_symlink")
    shutil.copytree(source, destination)


def _artifact_records(root: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name == CONTACTS_PROOF_FILENAME:
            continue
        digest, byte_count = _file_hash(path)
        relative = path.relative_to(root).as_posix()
        artifact_id = "artifact_" + hashlib.sha256(relative.encode()).hexdigest()[:16]
        records[artifact_id] = {
            "artifact_id": artifact_id,
            "path": relative,
            "sha256": digest,
            "byte_count": byte_count,
        }
    return records


def _artifact_for_path(
    records: Mapping[str, Mapping[str, object]],
    root: Path,
    path: Path,
) -> str:
    relative = path.relative_to(root).as_posix()
    for artifact_id, record in records.items():
        if record.get("path") == relative:
            return artifact_id
    raise ContactsAcceptanceError("contacts_proof_anchor_missing")


def _mutate_json_file(
    source: Path,
    destination: Path,
    *,
    path: str,
    mutate: Any,
) -> None:
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContactsAcceptanceError("contacts_proof_case_positive_unreadable") from exc
    mutate(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mutate_jsonl_file(source: Path, destination: Path, mutate: Any) -> None:
    try:
        records = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContactsAcceptanceError("contacts_proof_case_positive_unreadable") from exc
    mutate(records)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _proof_identity(root: Mapping[str, object]) -> str:
    material = dict(root)
    material["proof_id"] = ""
    material["proof_hash"] = ""
    return hash_value(material)


def _build_case(
    *,
    proof_root: Path,
    records: dict[str, dict[str, object]],
    case_id: str,
    target_path: Path,
    mutation_path: str,
    mutate: Any,
    jsonl: bool = False,
) -> dict[str, object]:
    positive_path = proof_root / "positive" / target_path.relative_to(proof_root / "positive")
    case_dir = proof_root / "negative" / case_id
    case_positive = case_dir / "positive" / positive_path.name
    case_mutated = case_dir / "mutated" / positive_path.name
    case_record_path = case_dir / "case.json"
    case_positive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(positive_path, case_positive)
    if jsonl:
        _mutate_jsonl_file(positive_path, case_mutated, mutate)
    else:
        _mutate_json_file(
            positive_path,
            case_mutated,
            path=mutation_path,
            mutate=mutate,
        )
    positive_hash, positive_bytes = _file_hash(positive_path)
    mutated_hash, mutated_bytes = _file_hash(case_mutated)
    unrelated = {
        artifact_id: record["sha256"]
        for artifact_id, record in records.items()
        if record.get("path") != target_path.relative_to(proof_root).as_posix()
    }
    expected_status, expected_reason = CONTACTS_PROOF_CASE_EXPECTATIONS[case_id]
    case = {
        "schema_version": CONTACTS_PROOF_CASE_SCHEMA_VERSION,
        "case_id": case_id,
        "target_artifact_id": _artifact_for_path(records, proof_root, target_path),
        "mutation_path": mutation_path,
        "expected_status": expected_status,
        "expected_reason_code": expected_reason,
        "positive_path": case_positive.relative_to(proof_root).as_posix(),
        "mutated_path": case_mutated.relative_to(proof_root).as_posix(),
        "positive_sha256": positive_hash,
        "positive_byte_count": positive_bytes,
        "mutated_sha256": mutated_hash,
        "mutated_byte_count": mutated_bytes,
        "unrelated_artifact_ids": sorted(unrelated),
        "unrelated_artifact_hashes": unrelated,
    }
    _write_json(case_record_path, case)
    return {
        **case,
        "path": case_record_path.relative_to(proof_root).as_posix(),
    }


def _load_positive_artifacts(
    proof_root: Path,
    *,
    evidence_contract: AcceptanceReplayContract,
) -> dict[str, object]:
    positive = proof_root / "positive"
    acceptance = _read_json(positive / "acceptance.json")
    provider_path = positive / "trace" / "provider.json"
    provider = load_contacts_provider_evidence(
        provider_path,
        contract=evidence_contract,
    )
    profile = _read_json(positive / "run_profile.json")
    pack = _read_json(positive / "dataset_release_pack.json")
    qualification = _read_json(positive / "qualification_report.json")
    return {
        "acceptance": acceptance,
        "provider": provider,
        "profile": profile,
        "pack": pack,
        "qualification": qualification,
    }


def _validate_positive_bindings(
    *,
    positive: Path,
    profile: RunProfile,
    plan: DomainPlan,
    provider: Mapping[str, object],
    qualification: Mapping[str, object],
    pack_path: Path,
) -> dict[str, object]:
    """Check the identity envelope before any positive proof is assembled."""

    expected_pack = build_contacts_domain_pack().descriptor
    if (
        plan.domain_pack_reference != expected_pack.reference()
        or plan.runtime_contract != expected_pack.runtime_contracts[0]
        or set(plan.capability_references)
        != set(expected_pack.capability_references)
    ):
        raise ContactsAcceptanceError("contacts_plan_binding_mismatch")

    profile_record = _read_json(positive / "run_profile.json")
    if profile_record != profile.canonical():
        raise ContactsAcceptanceError("contacts_profile_binding_mismatch")
    coverage_path = positive / "coverage_plan.json"
    coverage = _read_json(coverage_path)
    expected_coverage = preview_coverage_plan(profile).canonical()
    if coverage != expected_coverage:
        raise ContactsAcceptanceError("contacts_coverage_plan_binding_mismatch")

    raw_authorization = _mapping(
        provider.get("authorization"),
        "contacts_provider_authorization",
    )
    try:
        ContactsAcceptanceAuthorization(
            approved=raw_authorization.get("approved"),  # type: ignore[arg-type]
            authorization_id=raw_authorization.get("authorization_id"),  # type: ignore[arg-type]
            candidate_budget=raw_authorization.get("candidate_budget"),  # type: ignore[arg-type]
            attempt_budget=raw_authorization.get("attempt_budget"),  # type: ignore[arg-type]
            generator_provider=raw_authorization.get("generator_provider"),  # type: ignore[arg-type]
            generator_model=raw_authorization.get("generator_model"),  # type: ignore[arg-type]
            mutation_judge_provider=raw_authorization.get("mutation_judge_provider"),  # type: ignore[arg-type]
            mutation_judge_model=raw_authorization.get("mutation_judge_model"),  # type: ignore[arg-type]
            generator_retry_limit=raw_authorization.get("generator_retry_limit"),  # type: ignore[arg-type]
            evidence_policy=raw_authorization.get("evidence_policy"),  # type: ignore[arg-type]
        ).validate(
            profile=profile.canonical(),
            plan_attempt_ceiling=coverage["attempt_ceiling"],  # type: ignore[arg-type]
        )
    except (ContactsAcceptanceError, TypeError, ValueError):
        raise ContactsAcceptanceError("contacts_authorization_binding_mismatch") from None

    expected_binding = {
        "profile_id": profile.profile_id,
        "dataset_version": profile.dataset_version,
        "seed_id": profile.seed.seed_id,
        "seed_domain": profile.seed.domain,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "coverage_plan_id": coverage["plan_id"],
        "coverage_plan_hash": coverage["plan_hash"],
        "source_policy_hash": plan.admitted_source.admission_policy_hash,
    }
    run_binding = _mapping(provider.get("run_binding"), "contacts_run_binding")
    if dict(run_binding) != expected_binding:
        raise ContactsAcceptanceError("contacts_run_binding_mismatch")

    authorization = _read_json(positive / "authorization.json")
    if (
        authorization.get("status") != "authorized"
        or authorization.get("generator") != provider.get("provider")
        or authorization.get("mutation_judge") != provider.get("mutation_judge")
        or authorization.get("authorization") != provider.get("authorization")
        or authorization.get("source_policy_hash")
        != plan.admitted_source.admission_policy_hash
    ):
        raise ContactsAcceptanceError("contacts_authorization_binding_mismatch")
    authorized_plan = _mapping(authorization.get("domain_plan"), "contacts_authorization")
    authorized_coverage = _mapping(
        authorization.get("coverage_plan"),
        "contacts_authorization",
    )
    if (
        authorized_plan.get("plan_id") != plan.plan_id
        or authorized_plan.get("plan_hash") != plan.plan_hash
        or authorized_coverage.get("plan_id") != coverage["plan_id"]
        or authorized_coverage.get("plan_hash") != coverage["plan_hash"]
    ):
        raise ContactsAcceptanceError("contacts_authorization_binding_mismatch")

    pack_hash, _ = _file_hash(pack_path)
    if (
        qualification.get("status") != "passed"
        or qualification.get("effective_qualification") != "release_candidate"
        or not isinstance(qualification.get("claims"), Mapping)
        or qualification["claims"].get("publishable") is not False
        or qualification["claims"].get("training_recommended") is not False
    ):
        raise ContactsAcceptanceError("contacts_qualification_not_verified")
    provider_qualification = _mapping(
        provider.get("qualification"),
        "contacts_provider_qualification",
    )
    if (
        provider_qualification.get("release_pack_hash") != pack_hash
        or provider_qualification.get("release_pack_verification_status") != "passed"
    ):
        raise ContactsAcceptanceError("contacts_provider_qualification_mismatch")
    qualification_binding = _mapping(
        qualification.get("qualification_binding"),
        "contacts_qualification_binding",
    )
    if (
        qualification_binding.get("release_pack_hash") != pack_hash
        or qualification_binding.get("plan_id") != plan.plan_id
        or qualification_binding.get("plan_hash") != plan.plan_hash
    ):
        raise ContactsAcceptanceError("contacts_qualification_binding_mismatch")
    return coverage


def build_contacts_acceptance_proof(
    proof_root: Path,
    acceptance_root: Path,
    *,
    evidence_contract: AcceptanceReplayContract = _CONTACTS_ACCEPTANCE_CONTRACT,
) -> Path:
    """Copy and independently assemble one Contacts acceptance proof.

    The proof graph is shared by the provider-free and real-live Contacts
    paths.  The evidence contract remains an explicit input so the proof can
    preserve which boundary produced its frozen provider evidence.
    """

    proof_root = Path(proof_root)
    acceptance_root = Path(acceptance_root)
    if proof_root.exists() and any(proof_root.iterdir()):
        raise ContactsAcceptanceError("contacts_proof_output_not_empty")
    if not acceptance_root.is_dir() or acceptance_root.is_symlink():
        raise ContactsAcceptanceError("contacts_acceptance_missing")
    proof_root.mkdir(parents=True, exist_ok=True)
    _copy_tree(acceptance_root, proof_root / "positive")
    positive = proof_root / "positive"
    loaded = _load_positive_artifacts(
        proof_root,
        evidence_contract=evidence_contract,
    )
    acceptance = loaded["acceptance"]
    provider = loaded["provider"]
    profile_record = loaded["profile"]
    qualification = loaded["qualification"]
    if acceptance.get("status") != "accepted":
        raise ContactsAcceptanceError("contacts_acceptance_not_accepted")
    if acceptance.get("replay", {}).get("provider_calls") != 0:
        raise ContactsAcceptanceError("contacts_replay_provider_calls_nonzero")
    if qualification.get("effective_qualification") != "release_candidate":
        raise ContactsAcceptanceError("contacts_release_candidate_not_verified")
    if not isinstance(profile_record, Mapping) or profile_record.get("profile_id") != CONTACTS_RELEASE_CANDIDATE_PROFILE_ID:
        raise ContactsAcceptanceError("contacts_release_profile_invalid")

    samples_path = positive / "samples.jsonl"
    samples = _load_jsonl(samples_path)
    if len(samples) < CONTACTS_RELEASE_TARGET_ACCEPTED_SAMPLES:
        raise ContactsAcceptanceError("contacts_coverage_evidence_incomplete")
    first_binding = _mapping(
        samples[0].get("contacts_evidence", samples[0].get("domain_evidence")),
        "contacts_evidence",
    )
    plan_record = _mapping(_mapping(first_binding.get("plan"), "contacts_plan").get("plan_record"), "contacts_plan_record")
    domain_pack = build_contacts_domain_pack()
    try:
        plan = DomainPlan.from_record(plan_record, descriptor=domain_pack.descriptor)
    except (DomainPackContractError, TypeError, ValueError) as exc:
        raise ContactsAcceptanceError("contacts_plan_not_admitted") from exc

    pack_path = positive / "dataset_release_pack.json"
    pack_verification = verify_dataset_release_pack(pack_path)
    if _mapping(pack_verification.get("verification"), "release_pack_verification").get("status") != "passed":
        raise ContactsAcceptanceError("contacts_release_pack_not_verified")
    recorded_pack_verification = _read_json(positive / "release_pack_verification.json")
    if recorded_pack_verification != pack_verification:
        raise ContactsAcceptanceError("contacts_release_pack_verification_mismatch")
    profile = _load_run_profile_from_record(positive / "run_profile.json")
    _validate_positive_bindings(
        positive=positive,
        profile=profile,
        plan=plan,
        provider=provider,
        qualification=qualification,
        pack_path=pack_path,
    )
    independently_qualified = qualify_contacts_release_candidate(
        manifest_path=positive / "manifest.json",
        release_pack_path=pack_path,
        release_quality_audit_path=positive / "release_quality_audit.json",
    )
    if independently_qualified != qualification:
        raise ContactsAcceptanceError("contacts_qualification_reconstruction_mismatch")

    # Reconstruct and execute the frozen provider input via the public Contacts
    # run.  This is the authoritative zero-provider replay result.
    replay = replay_contacts_provider_evidence(
        provider,
        profile=profile,
        plan=plan,
        acceptance_dir=positive,
        contract=evidence_contract,
    )
    if replay.get("status") != "passed" or replay.get("provider_calls") != 0:
        raise ContactsAcceptanceError("contacts_replay_contract_failed")
    if acceptance.get("replay") != replay:
        raise ContactsAcceptanceError("contacts_replay_result_mismatch")

    trace = positive / "trace"
    trace.mkdir(parents=True, exist_ok=True)
    _write_json(trace / "domain_pack.json", domain_pack.descriptor.to_record())
    _write_json(trace / "plan.json", plan.to_record())
    _write_json(trace / "source.json", plan.admitted_source.to_record())
    _write_json(trace / "runtime.json", plan.runtime_contract.to_record())
    _write_json(trace / "qualification.json", qualification)
    _write_json(trace / "replay.json", replay)
    _write_json(trace / "provider.json", provider)
    assignments = _assignment_evidence_from_provider(provider)
    _write_json(
        trace / "assignments.json",
        {
            "schema_version": "contacts_acceptance_assignment_evidence_v1",
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "assignments": [item["lineage"] for item in assignments],
            "assignment_contracts": [item["assignment"] for item in assignments],
        },
    )
    mutation = next(
        (
            sample.get("mutation_admission")
            for sample in samples
            if isinstance(sample.get("mutation_admission"), Mapping)
            and sample["mutation_admission"].get("classification") == "state_changing"
        ),
        None,
    )
    if not isinstance(mutation, Mapping):
        raise ContactsAcceptanceError("contacts_mutation_admission_missing")
    _write_json(trace / "mutation_admission.json", dict(mutation))
    assessment = _assessment_from_qualification(qualification, plan)
    _write_json(trace / "assessment.json", assessment.to_record())

    compatibility_destination = proof_root / "compatibility" / "corpus"
    _copy_tree(
        Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "compatibility",
        compatibility_destination,
    )
    compatibility_result = verify_compatibility_corpus(compatibility_destination)
    _write_json(
        proof_root / "compatibility" / "compatibility_result.json",
        compatibility_result.to_record(),
    )
    _write_json(
        proof_root / "conformance" / "contacts_conformance.json",
        {
            "schema_version": "contacts_acceptance_conformance_v1",
            "status": "passed",
            "evidence_class": "conformance_fixture",
            "effective_qualification": "release_candidate",
            "publishable": False,
            "training_recommended": False,
            "scope": "fixture_and_contract_conformance_only",
        },
    )

    records = _artifact_records(proof_root)
    anchors_paths: dict[str, Path] = {
        "acceptance": positive / "acceptance.json",
        "domain_pack": trace / "domain_pack.json",
        "plan": trace / "plan.json",
        "source": trace / "source.json",
        "runtime": trace / "runtime.json",
        "provider": trace / "provider.json",
        "assignments": trace / "assignments.json",
        "mutation_admission": trace / "mutation_admission.json",
        "manifest": positive / "manifest.json",
        "run_profile": positive / "run_profile.json",
        "contacts_environment": positive / "environment" / "contacts.sqlite3",
        "coverage_plan": positive / "coverage_plan.json",
        "coverage_evidence": positive / "coverage_evidence.json",
        "samples": positive / "samples.jsonl",
        "rejections": positive / "rejections.jsonl",
        "episodes": positive / "episodes.jsonl",
        "replay_report": positive / "episode_replay_report.json",
        "evaluation_report": positive / "evaluation_report.json",
        "profile_decision_report": positive / "profile_decision_report.json",
        "dataset_release_report": positive / "dataset_release_report.json",
        "release_quality_audit": positive / "release_quality_audit.json",
        "mutation_admission_report": positive / "mutation_admission_report.json",
        "release_pack_verification": positive / "release_pack_verification.json",
        "release_pack": pack_path,
        "qualification": trace / "qualification.json",
        "assessment": trace / "assessment.json",
        "compatibility_result": proof_root / "compatibility" / "compatibility_result.json",
        "compatibility_manifest": compatibility_destination / "corpus_manifest.json",
        "conformance": proof_root / "conformance" / "contacts_conformance.json",
    }
    # The current Contacts fixture names its SQLite file explicitly; fail
    # closed if a runtime change silently changes this proof anchor.
    for path in anchors_paths.values():
        if not path.is_file() or path.is_symlink():
            raise ContactsAcceptanceError(
                "contacts_proof_anchor_missing",
                f"missing Contacts proof anchor: {path}",
            )
    anchors = {
        name: _artifact_for_path(records, proof_root, path)
        for name, path in anchors_paths.items()
    }
    target_paths = {
        "pack_identity": anchors_paths["domain_pack"],
        "plan_identity": anchors_paths["plan"],
        "source_identity": anchors_paths["source"],
        "runtime_identity": anchors_paths["runtime"],
        "capability_membership": anchors_paths["assignments"],
        "assignment_membership": anchors_paths["assignments"],
        "mutation_admission": anchors_paths["mutation_admission"],
        "episode_evidence": anchors_paths["episodes"],
        "verifier_identity": anchors_paths["samples"],
        "coverage_evidence": anchors_paths["coverage_evidence"],
        "assessment_evidence": anchors_paths["assessment"],
        "release_pack": anchors_paths["release_pack"],
        "qualification_dependency": anchors_paths["qualification"],
    }
    mutations: dict[str, tuple[str, Any, bool]] = {
        "pack_identity": ("pack_version", _mutate_pack, False),
        "plan_identity": ("plan_hash", _mutate_plan, False),
        "source_identity": ("source_content_hash", _mutate_source, False),
        "runtime_identity": ("runtime_version", _mutate_runtime, False),
        "capability_membership": ("assignment_contracts[0].capability_references[0].capability_key", _mutate_capability, False),
        "assignment_membership": ("assignment_contracts[0].assignment_hash", _mutate_assignment, False),
        "mutation_admission": ("admission_outcome", _mutate_mutation, False),
        "episode_evidence": ("[0].episode_id", _mutate_episode, True),
        "verifier_identity": ("[0].verifier.version", _mutate_verifier, True),
        "coverage_evidence": ("fulfillment.status", _mutate_coverage, False),
        "assessment_evidence": ("status", _mutate_assessment, False),
        "release_pack": ("verification.status", _mutate_release_pack, False),
        "qualification_dependency": ("effective_qualification", _mutate_qualification, False),
    }
    proof_cases = [
        _build_case(
            proof_root=proof_root,
            records=records,
            case_id=case_id,
            target_path=target_paths[case_id],
            mutation_path=mutations[case_id][0],
            mutate=mutations[case_id][1],
            jsonl=mutations[case_id][2],
        )
        for case_id in sorted(CONTACTS_PROOF_CASE_EXPECTATIONS)
    ]
    records = _artifact_records(proof_root)
    anchors = {
        name: _artifact_for_path(records, proof_root, path)
        for name, path in anchors_paths.items()
    }
    root: dict[str, object] = {
        "schema_version": CONTACTS_PROOF_SCHEMA_VERSION,
        "proof_id": "",
        "proof_hash": "",
        "root_type": CONTACTS_PROOF_SCHEMA_VERSION,
        "summary": dict(CONTACTS_PROOF_SUMMARY),
        "conformance": {
            "status": "passed",
            "evidence_class": "conformance_fixture",
            "effective_qualification": "release_candidate",
        },
        "non_claims": {
            "publishable": False,
            "training_recommended": False,
            "global_mutation_activation": False,
            "mobile_messages": False,
            "downstream_utility": False,
        },
        "subject": {
            "domain_pack_reference": plan.domain_pack_reference.to_record(),
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "release_id": _mapping(loaded["pack"], "release_pack").get("release_id"),
            "release_pack_hash": _file_hash(pack_path)[0],
            "evidence_class": evidence_contract.evidence_class,
        },
        "anchors": anchors,
        "artifacts": [records[key] for key in sorted(records)],
        "proof_cases": proof_cases,
        "dependencies": [
            {"from": anchors["plan"], "to": anchors["domain_pack"], "relation": "plan_binds_domain_pack"},
            {"from": anchors["plan"], "to": anchors["source"], "relation": "plan_binds_source"},
            {"from": anchors["plan"], "to": anchors["runtime"], "relation": "plan_binds_runtime"},
            {"from": anchors["provider"], "to": anchors["assignments"], "relation": "provider_answers_assignments"},
            {"from": anchors["samples"], "to": anchors["mutation_admission"], "relation": "samples_bind_mutation_admission"},
            {"from": anchors["samples"], "to": anchors["assignments"], "relation": "samples_bind_assignments"},
            {"from": anchors["release_pack"], "to": anchors["manifest"], "relation": "pack_binds_manifest"},
            {"from": anchors["qualification"], "to": anchors["release_pack"], "relation": "qualification_binds_pack"},
            {"from": anchors["assessment"], "to": anchors["plan"], "relation": "assessment_binds_plan"},
            {"from": anchors["compatibility_result"], "to": anchors["compatibility_manifest"], "relation": "compatibility_binds_corpus"},
            {"from": anchors["conformance"], "to": anchors["qualification"], "relation": "conformance_does_not_raise_qualification"},
        ],
    }
    proof_hash = _proof_identity(root)
    root["proof_hash"] = proof_hash
    root["proof_id"] = "contacts_acceptance_proof_" + proof_hash.removeprefix("sha256:")[:16]
    proof_path = proof_root / CONTACTS_PROOF_FILENAME
    _write_json(proof_path, root)
    return proof_path


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContactsAcceptanceError("contacts_artifact_unreadable") from exc
    if any(not isinstance(value, Mapping) for value in values):
        raise ContactsAcceptanceError("contacts_artifact_malformed")
    return [dict(value) for value in values]


def _mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContactsAcceptanceError(reason)
    return value


def _assignment_evidence_from_provider(
    provider: Mapping[str, object],
) -> list[dict[str, Mapping[str, object]]]:
    attempts = provider.get("attempts")
    if not isinstance(attempts, list):
        raise ContactsAcceptanceError("contacts_provider_evidence_malformed")
    result: list[dict[str, Mapping[str, object]]] = []
    seen: set[str] = set()
    for raw in attempts:
        if not isinstance(raw, Mapping):
            continue
        assignment_id = raw.get("assignment_id")
        assignment = raw.get("assignment")
        lineage = raw.get("assignment_lineage")
        if not isinstance(assignment_id, str) or not isinstance(assignment, Mapping) or not isinstance(lineage, Mapping):
            raise ContactsAcceptanceError("contacts_provider_evidence_malformed")
        if assignment_id in seen:
            continue
        seen.add(assignment_id)
        result.append({"assignment": assignment, "lineage": lineage})
    if not result:
        raise ContactsAcceptanceError("contacts_assignment_evidence_missing")
    return result


def _load_run_profile_from_record(path: Path) -> RunProfile:
    from synthesis.run_profiles import load_run_profile

    return load_run_profile(path)


def _assessment_from_qualification(
    qualification: Mapping[str, object],
    plan: DomainPlan,
) -> DomainAssessment:
    history = qualification.get("historical_decisions")
    if not isinstance(history, list) or not history:
        raise ContactsAcceptanceError("contacts_assessment_missing")
    evidence = _mapping(history[-1], "contacts_qualification_history")
    gates = _mapping(_mapping(evidence.get("evidence"), "contacts_qualification_evidence").get("gates"), "contacts_qualification_gates")
    raw = _mapping(gates.get("domain_assessment"), "contacts_assessment_missing")
    keys = {
        "schema_version",
        "domain_pack_reference",
        "plan_id",
        "plan_hash",
        "evidence_references",
        "established_capability_references",
        "status",
        "reason_code",
        "assessment_id",
        "assessment_hash",
    }
    try:
        return DomainAssessment.from_record(
            {key: raw[key] for key in keys},
            plan=plan,
        )
    except (KeyError, TypeError, ValueError, DomainPackContractError) as exc:
        raise ContactsAcceptanceError("contacts_assessment_incomplete") from exc


def _mutate_pack(value: object) -> None:
    if isinstance(value, dict):
        value["pack_version"] = "contacts_pack_drifted"


def _mutate_plan(value: object) -> None:
    if isinstance(value, dict):
        value["plan_hash"] = "sha256:" + "0" * 64


def _mutate_source(value: object) -> None:
    if isinstance(value, dict):
        value["source_content_hash"] = "sha256:" + "0" * 64


def _mutate_runtime(value: object) -> None:
    if isinstance(value, dict):
        value["runtime_version"] = "contacts_fixture_drifted"


def _mutate_capability(value: object) -> None:
    if isinstance(value, dict):
        contracts = value.get("assignment_contracts")
        if isinstance(contracts, list) and contracts and isinstance(contracts[0], dict):
            refs = contracts[0].get("capability_references")
            if isinstance(refs, list) and refs:
                refs[0] = dict(refs[0])
                refs[0]["capability_key"] = "foreign_capability"


def _mutate_assignment(value: object) -> None:
    if isinstance(value, dict):
        contracts = value.get("assignment_contracts")
        if isinstance(contracts, list) and contracts and isinstance(contracts[0], dict):
            contracts[0]["assignment_hash"] = "sha256:" + "0" * 64


def _mutate_mutation(value: object) -> None:
    if isinstance(value, dict):
        value["admission_outcome"] = "judge_unsupported"


def _mutate_episode(value: object) -> None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        value[0]["episode_id"] = "episode_contacts_drifted"


def _mutate_verifier(value: object) -> None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        verifier = value[0].get("verifier")
        if isinstance(verifier, dict):
            verifier["version"] = "contacts_verifier_drifted"


def _mutate_coverage(value: object) -> None:
    if isinstance(value, dict):
        fulfillment = value.get("fulfillment")
        if isinstance(fulfillment, dict):
            fulfillment["status"] = "incomplete"


def _mutate_assessment(value: object) -> None:
    if isinstance(value, dict):
        value["status"] = "insufficient"


def _mutate_release_pack(value: object) -> None:
    if isinstance(value, dict):
        verification = value.get("verification")
        if isinstance(verification, dict):
            verification["status"] = "failed"


def _mutate_qualification(value: object) -> None:
    if isinstance(value, dict):
        value["effective_qualification"] = "unqualified"


def _verify_artifacts(root: Path, records: Mapping[str, Mapping[str, object]]) -> None:
    for record in records.values():
        relative = record.get("path")
        if not isinstance(relative, str):
            raise ContactsAcceptanceError("contacts_proof_artifact_malformed")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ContactsAcceptanceError("contacts_proof_artifact_missing")
        digest, byte_count = _file_hash(path)
        if digest != record.get("sha256") or byte_count != record.get("byte_count"):
            raise ContactsAcceptanceError("contacts_proof_artifact_integrity")


def _verify_case(
    *,
    root: Path,
    records: Mapping[str, Mapping[str, object]],
    case: Mapping[str, object],
) -> dict[str, object]:
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or case_id not in CONTACTS_PROOF_CASE_EXPECTATIONS:
        raise ContactsAcceptanceError("contacts_proof_case_malformed")
    case_path = root / str(case.get("path"))
    case_record = _read_json(case_path, "contacts_proof_case_malformed")
    expected_status, expected_reason = CONTACTS_PROOF_CASE_EXPECTATIONS[case_id]
    if (
        case_record.get("schema_version") != CONTACTS_PROOF_CASE_SCHEMA_VERSION
        or case_record.get("case_id") != case_id
        or case_record.get("expected_status") != expected_status
        or case_record.get("expected_reason_code") != expected_reason
    ):
        raise ContactsAcceptanceError("contacts_proof_case_expectation_mismatch")
    positive_path = root / str(case_record.get("positive_path"))
    mutated_path = root / str(case_record.get("mutated_path"))
    target_id = case_record.get("target_artifact_id")
    target = records.get(str(target_id))
    if target is None:
        raise ContactsAcceptanceError("contacts_proof_case_target_missing")
    if positive_path.read_bytes() != (root / str(target["path"])).read_bytes():
        raise ContactsAcceptanceError("contacts_proof_case_positive_copy_mismatch")
    positive_bytes = positive_path.read_bytes()
    mutated_bytes = mutated_path.read_bytes()
    if positive_bytes == mutated_bytes:
        raise ContactsAcceptanceError("contacts_proof_case_not_mutated")
    if (
        case_record.get("positive_sha256") != _file_hash(positive_path)[0]
        or case_record.get("positive_byte_count") != _file_hash(positive_path)[1]
        or case_record.get("mutated_sha256") != _file_hash(mutated_path)[0]
        or case_record.get("mutated_byte_count") != _file_hash(mutated_path)[1]
    ):
        raise ContactsAcceptanceError("contacts_proof_case_integrity")
    differences = _json_difference(positive_bytes, mutated_bytes)
    mutation_path = str(case_record.get("mutation_path"))
    if mutation_path != "replacement" and differences != [mutation_path]:
        raise ContactsAcceptanceError(
            "contacts_proof_case_mutation_scope",
            f"case={case_id} expected={mutation_path} actual={differences}",
        )
    if mutation_path == "replacement" and not differences:
        raise ContactsAcceptanceError(
            "contacts_proof_case_mutation_scope",
            f"case={case_id} expected replacement mutation",
        )
    observed_status, observed_reason = _observe_case(case_id, root, mutated_path)
    if (observed_status, observed_reason) != (expected_status, expected_reason):
        raise ContactsAcceptanceError("contacts_proof_case_expectation_mismatch")
    unrelated_ids = case_record.get("unrelated_artifact_ids")
    unrelated_hashes = case_record.get("unrelated_artifact_hashes")
    if not isinstance(unrelated_ids, list) or not isinstance(unrelated_hashes, Mapping):
        raise ContactsAcceptanceError("contacts_proof_case_independence_missing")
    for artifact_id in unrelated_ids:
        record = records.get(str(artifact_id))
        if record is None or unrelated_hashes.get(artifact_id) != record.get("sha256"):
            raise ContactsAcceptanceError("contacts_proof_case_independence_changed")
    return {
        "case_id": case_id,
        "status": "passed",
        "reason_code": expected_reason,
        "observed_status": observed_status,
        "mutation_path": mutation_path,
    }


def _json_difference(positive: bytes, mutated: bytes) -> list[str]:
    try:
        first = json.loads(positive.decode("utf-8"))
        second = json.loads(mutated.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        try:
            first = [
                json.loads(line)
                for line in positive.decode("utf-8").splitlines()
                if line
            ]
            second = [
                json.loads(line)
                for line in mutated.decode("utf-8").splitlines()
                if line
            ]
        except (UnicodeError, json.JSONDecodeError):
            return ["replacement"]
    differences: list[str] = []

    def visit(left: object, right: object, path: str) -> None:
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            for key in sorted(set(left) | set(right), key=str):
                next_path = f"{path}.{key}" if path else str(key)
                if key not in left or key not in right:
                    differences.append(next_path)
                else:
                    visit(left[key], right[key], next_path)
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                next_path = f"{path}[{index}]"
                if index >= len(left) or index >= len(right):
                    differences.append(next_path)
                else:
                    visit(left[index], right[index], next_path)
            return
        if left != right:
            differences.append(path or "replacement")

    visit(first, second, "")
    return differences


def _observe_case(case_id: str, root: Path, mutated_path: Path) -> tuple[str, str]:
    try:
        positive_trace = root / "positive" / "trace"
        if case_id == "pack_identity":
            from synthesis.domain_pack import DomainPackDescriptor

            mutated = DomainPackDescriptor.from_record(_read_json(mutated_path))
            expected = DomainPackDescriptor.from_record(
                _read_json(positive_trace / "domain_pack.json")
            )
            if mutated != expected:
                return "rejected", "contacts_domain_pack_drift"
        elif case_id == "plan_identity":
            expected = DomainPlan.from_record(
                _read_json(positive_trace / "plan.json"),
                descriptor=build_contacts_domain_pack().descriptor,
            )
            try:
                mutated = DomainPlan.from_record(
                    _read_json(mutated_path),
                    descriptor=build_contacts_domain_pack().descriptor,
                )
            except (DomainPackContractError, TypeError, ValueError):
                return "rejected", "contacts_plan_drift"
            if mutated != expected:
                return "rejected", "contacts_plan_drift"
        elif case_id == "source_identity":
            from synthesis.domain_pack import AdmittedSource

            raw = _read_json(mutated_path)
            mutated = AdmittedSource.from_record(raw)
            expected = AdmittedSource.from_record(
                _read_json(positive_trace / "source.json")
            )
            if mutated != expected:
                return "rejected", "contacts_source_drift"
        elif case_id == "runtime_identity":
            from synthesis.domain_pack import DomainRuntimeContractReference

            raw = _read_json(mutated_path)
            mutated = DomainRuntimeContractReference.from_record(raw)
            expected = DomainRuntimeContractReference.from_record(
                _read_json(positive_trace / "runtime.json")
            )
            if mutated != expected:
                return "rejected", "contacts_runtime_contract_drift"
        elif case_id == "capability_membership":
            from synthesis.domain_pack import DomainCapabilityReference

            raw = _read_json(mutated_path)
            contracts = raw.get("assignment_contracts")
            refs = (
                contracts[0].get("capability_references")
                if isinstance(contracts, list)
                and contracts
                and isinstance(contracts[0], Mapping)
                else None
            )
            parsed = [
                DomainCapabilityReference.from_record(item)
                for item in refs
            ] if isinstance(refs, list) else []
            if set(parsed) != set(build_contacts_domain_pack().descriptor.capability_references) and parsed:
                return "rejected", "contacts_capability_contract_drift"
        elif case_id == "assignment_membership":
            raw = _read_json(mutated_path)
            contracts = raw.get("assignment_contracts", [])
            lineages = raw.get("assignments", [])
            if (
                contracts
                and lineages
                and contracts[0].get("assignment_hash")
                != lineages[0].get("assignment_hash")
            ):
                return "rejected", "contacts_assignment_membership_mismatch"
        elif case_id == "mutation_admission":
            from synthesis.mutation_admission import validate_mutation_admission_evidence

            raw = _read_json(mutated_path)
            try:
                validate_mutation_admission_evidence(raw)
            except (TypeError, ValueError):
                return "rejected", "contacts_mutation_admission_failed"
        elif case_id == "episode_evidence":
            from synthesis.contracts import validate_episode_log_record

            mutated = _load_jsonl(mutated_path)
            expected = _load_jsonl(root / "positive" / "episodes.jsonl")
            try:
                validate_episode_log_record(mutated[0])
            except (TypeError, ValueError):
                return "rejected", "contacts_episode_drift"
            if mutated and expected and mutated[0].get("episode_id") != expected[0].get("episode_id"):
                return "rejected", "contacts_episode_drift"
        elif case_id == "verifier_identity":
            from synthesis.contracts import validate_sample_record

            mutated = _load_jsonl(mutated_path)
            expected = _load_jsonl(root / "positive" / "samples.jsonl")
            try:
                validate_sample_record(mutated[0])
            except (TypeError, ValueError):
                return "rejected", "contacts_verifier_drift"
            if (
                mutated
                and expected
                and _mapping(mutated[0].get("verifier"), "verifier").get("version")
                != _mapping(expected[0].get("verifier"), "verifier").get("version")
            ):
                return "rejected", "contacts_verifier_drift"
        elif case_id == "coverage_evidence":
            from synthesis.coverage_evidence import validate_coverage_evidence_record

            try:
                validate_coverage_evidence_record(_read_json(mutated_path))
            except (TypeError, ValueError):
                return "rejected", "contacts_coverage_evidence_incomplete"
        elif case_id == "assessment_evidence":
            try:
                DomainAssessment.from_record(
                    _read_json(mutated_path),
                    plan=DomainPlan.from_record(
                        _read_json(positive_trace / "plan.json"),
                        descriptor=build_contacts_domain_pack().descriptor,
                    ),
                )
            except (ContactsAcceptanceError, DomainPackContractError, TypeError, ValueError):
                return "rejected", "contacts_assessment_incomplete"
        elif case_id == "release_pack":
            from synthesis.contracts import validate_dataset_release_pack_record

            raw = _read_json(mutated_path)
            try:
                validate_dataset_release_pack_record(raw)
            except (TypeError, ValueError):
                return "rejected", "contacts_release_pack_not_verified"
            if _mapping(raw.get("verification"), "release_pack_verification").get("status") != "passed":
                return "rejected", "contacts_release_pack_not_verified"
        elif case_id == "qualification_dependency":
            from synthesis.contracts import validate_qualification_report_record

            raw = _read_json(mutated_path)
            try:
                validate_qualification_report_record(raw)
            except (TypeError, ValueError):
                return "rejected", "contacts_qualification_dependency_invalidated"
            if raw.get("effective_qualification") != "release_candidate":
                return "rejected", "contacts_qualification_dependency_invalidated"
    except (ContactsAcceptanceError, KeyError, TypeError, IndexError):
        return "rejected", CONTACTS_PROOF_CASE_EXPECTATIONS[case_id][1]
    raise ContactsAcceptanceError("contacts_proof_case_expectation_mismatch")


def verify_contacts_acceptance_proof(
    proof_path: Path,
    *,
    evidence_contract: AcceptanceReplayContract = _CONTACTS_ACCEPTANCE_CONTRACT,
) -> dict[str, object]:
    """Verify a Contacts proof root using only its copied artifacts."""

    try:
        root_path = Path(proof_path)
        if root_path.is_dir():
            root_path = root_path / CONTACTS_PROOF_FILENAME
        root = _read_json(root_path, "contacts_proof_root_missing")
        if set(root) != {
            "schema_version",
            "proof_id",
            "proof_hash",
            "root_type",
            "summary",
            "conformance",
            "non_claims",
            "subject",
            "anchors",
            "artifacts",
            "proof_cases",
            "dependencies",
        }:
            raise ContactsAcceptanceError("contacts_proof_root_malformed")
        if root.get("schema_version") != CONTACTS_PROOF_SCHEMA_VERSION or root.get("root_type") != CONTACTS_PROOF_SCHEMA_VERSION:
            raise ContactsAcceptanceError("contacts_proof_root_unknown_version")
        proof_hash = root.get("proof_hash")
        if not isinstance(proof_hash, str) or not _HASH_RE.fullmatch(proof_hash) or _proof_identity(root) != proof_hash:
            raise ContactsAcceptanceError("contacts_proof_identity_mismatch")
        if root.get("proof_id") != "contacts_acceptance_proof_" + proof_hash.removeprefix("sha256:")[:16]:
            raise ContactsAcceptanceError("contacts_proof_identity_mismatch")
        if root.get("summary") != CONTACTS_PROOF_SUMMARY:
            raise ContactsAcceptanceError("contacts_proof_summary_mismatch")
        if root.get("non_claims") != {
            "publishable": False,
            "training_recommended": False,
            "global_mutation_activation": False,
            "mobile_messages": False,
            "downstream_utility": False,
        }:
            raise ContactsAcceptanceError("contacts_proof_non_claims_mismatch")
        conformance = _mapping(root.get("conformance"), "contacts_proof_conformance_malformed")
        if conformance.get("status") != "passed" or conformance.get("evidence_class") != "conformance_fixture":
            raise ContactsAcceptanceError("contacts_proof_conformance_failed")
        artifacts_raw = root.get("artifacts")
        if not isinstance(artifacts_raw, list):
            raise ContactsAcceptanceError("contacts_proof_artifacts_malformed")
        records: dict[str, Mapping[str, object]] = {}
        for raw in artifacts_raw:
            record = _mapping(raw, "contacts_proof_artifacts_malformed")
            artifact_id = record.get("artifact_id")
            if not isinstance(artifact_id, str) or artifact_id in records:
                raise ContactsAcceptanceError("contacts_proof_artifacts_malformed")
            records[artifact_id] = record
        root_dir = root_path.parent
        _verify_artifacts(root_dir, records)
        anchors = _mapping(root.get("anchors"), "contacts_proof_anchors_malformed")
        anchor_paths = {
            name: root_dir / str(records[str(artifact_id)]["path"])
            for name, artifact_id in anchors.items()
            if str(artifact_id) in records
        }
        required_anchors = {
            "acceptance",
            "domain_pack",
            "plan",
            "source",
            "runtime",
            "provider",
            "assignments",
            "mutation_admission",
            "manifest",
            "run_profile",
            "contacts_environment",
            "coverage_plan",
            "coverage_evidence",
            "samples",
            "rejections",
            "episodes",
            "replay_report",
            "evaluation_report",
            "profile_decision_report",
            "dataset_release_report",
            "release_quality_audit",
            "mutation_admission_report",
            "release_pack_verification",
            "release_pack",
            "qualification",
            "assessment",
            "compatibility_result",
            "compatibility_manifest",
            "conformance",
        }
        if set(anchor_paths) != required_anchors or any(
            not path.is_file() for path in anchor_paths.values()
        ):
            raise ContactsAcceptanceError(
                "contacts_proof_anchor_missing",
                f"anchors={sorted(anchor_paths)} required={sorted(required_anchors)} raw={sorted(anchors)}",
            )

        provider = load_contacts_provider_evidence(
            anchor_paths["provider"],
            contract=evidence_contract,
        )
        if provider.get("evidence_class") != evidence_contract.evidence_class:
            raise ContactsAcceptanceError("contacts_provider_evidence_class_mismatch")
        profile = _load_run_profile_from_record(anchor_paths["run_profile"])
        samples = _load_jsonl(anchor_paths["samples"])
        first_binding = _mapping(samples[0].get("contacts_evidence", samples[0].get("domain_evidence")), "contacts_evidence")
        plan_record = _mapping(_mapping(first_binding.get("plan"), "contacts_plan").get("plan_record"), "contacts_plan_record")
        plan = DomainPlan.from_record(
            plan_record,
            descriptor=build_contacts_domain_pack().descriptor,
        )
        pack_path = anchor_paths["release_pack"]
        pack_verification = verify_dataset_release_pack(pack_path)
        if _mapping(
            pack_verification.get("verification"),
            "contacts_release_pack_verification",
        ).get("status") != "passed":
            raise ContactsAcceptanceError("contacts_release_pack_not_verified")
        recorded_pack_verification = _read_json(
            anchor_paths["release_pack_verification"]
        )
        if recorded_pack_verification != pack_verification:
            raise ContactsAcceptanceError("contacts_release_pack_verification_mismatch")
        qualification = _read_json(anchor_paths["qualification"])
        _validate_positive_bindings(
            positive=root_dir / "positive",
            profile=profile,
            plan=plan,
            provider=provider,
            qualification=qualification,
            pack_path=pack_path,
        )
        replay = replay_contacts_provider_evidence(
            provider,
            profile=profile,
            plan=plan,
            acceptance_dir=root_dir / "positive",
            contract=evidence_contract,
        )
        if replay.get("status") != "passed" or replay.get("provider_calls") != 0:
            raise ContactsAcceptanceError("contacts_replay_contract_failed")
        acceptance = _read_json(anchor_paths["acceptance"])
        if acceptance.get("status") != "accepted" or acceptance.get("replay") != replay:
            raise ContactsAcceptanceError("contacts_replay_result_mismatch")
        independently_qualified = qualify_contacts_release_candidate(
            manifest_path=anchor_paths["manifest"],
            release_pack_path=pack_path,
            release_quality_audit_path=anchor_paths["release_quality_audit"],
        )
        if independently_qualified != qualification:
            raise ContactsAcceptanceError("contacts_qualification_reconstruction_mismatch")
        if qualification.get("effective_qualification") != "release_candidate":
            raise ContactsAcceptanceError("contacts_release_candidate_not_verified")
        assessment = _read_json(anchor_paths["assessment"])
        assessment_object = DomainAssessment.from_record(assessment, plan=plan)
        if assessment_object.status != "established":
            raise ContactsAcceptanceError("contacts_assessment_incomplete")
        compatibility_result = _read_json(anchor_paths["compatibility_result"])
        if compatibility_result.get("status") != "passed" or verify_compatibility_corpus(anchor_paths["compatibility_manifest"].parent).to_record() != compatibility_result:
            raise ContactsAcceptanceError("contacts_compatibility_failed")
        cases = root.get("proof_cases")
        if not isinstance(cases, list) or {str(case.get("case_id")) for case in cases if isinstance(case, Mapping)} != set(CONTACTS_PROOF_CASE_EXPECTATIONS):
            raise ContactsAcceptanceError("contacts_proof_case_set_invalid")
        case_results = [
            _verify_case(root=root_dir, records=records, case=case)
            for case in sorted(cases, key=lambda value: str(value.get("case_id")))
            if isinstance(case, Mapping)
        ]
        return {
            "schema_version": "contacts_acceptance_verification_v1",
            "status": "passed",
            "reason_codes": ["contacts_acceptance_proof_passed"],
            "proof_identity": proof_hash,
            "summary": dict(CONTACTS_PROOF_SUMMARY),
            "chain": {
                "plan_id": plan.plan_id,
                "plan_hash": plan.plan_hash,
                "release_pack_hash": _file_hash(pack_path)[0],
                "sample_count": len(samples),
                "replay": replay,
                "qualification": "release_candidate",
            },
            "proof_cases": case_results,
        }
    except ContactsAcceptanceError as exc:
        return {
            "schema_version": "contacts_acceptance_verification_v1",
            "status": "failed",
            "reason_codes": [exc.reason_code],
            "detail": str(exc),
        }
    except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
        return {
            "schema_version": "contacts_acceptance_verification_v1",
            "status": "failed",
            "reason_codes": ["contacts_proof_verification_failed"],
            "error_class": type(exc).__name__,
        }


# Naming aliases keep the domain acceptance boundary easy to discover without
# exposing the neutral harness itself.
run_contacts_acceptance = run_contacts_acceptance_proof
replay_sanitized_contacts_provider_evidence = replay_contacts_provider_evidence
sanitize_provider_response = sanitize_contacts_provider_response
validate_provider_evidence = validate_contacts_provider_evidence
load_provider_evidence = load_contacts_provider_evidence


__all__ = [
    "CONTACTS_ACCEPTANCE_SCHEMA_VERSION",
    "CONTACTS_EVIDENCE_CLASS",
    "CONTACTS_PROOF_CASE_EXPECTATIONS",
    "CONTACTS_PROOF_FILENAME",
    "CONTACTS_PROOF_SCHEMA_VERSION",
    "CONTACTS_SANITIZED_EVIDENCE_POLICY_VERSION",
    "ContactsAcceptanceAuthorization",
    "ContactsAcceptanceError",
    "ContactsAcceptanceResult",
    "ContactsSanitizedMutationJudgeUsageObserver",
    "ContactsSanitizedProviderEvidenceRecorder",
    "SanitizedMutationJudgeUsageObserver",
    "SanitizedProviderEvidenceRecorder",
    "load_provider_evidence",
    "replay_sanitized_contacts_provider_evidence",
    "run_contacts_acceptance",
    "sanitize_provider_response",
    "validate_provider_evidence",
    "build_contacts_acceptance_proof",
    "load_contacts_provider_evidence",
    "replay_contacts_provider_evidence",
    "run_contacts_acceptance_proof",
    "sanitize_contacts_provider_response",
    "validate_contacts_provider_evidence",
    "verify_contacts_acceptance_proof",
]
