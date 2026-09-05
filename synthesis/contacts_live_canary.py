"""One-call, non-qualifying live Contacts generation-contract canary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from synthesis.acceptance_replay import (
    SanitizedMutationJudgeUsageObserver,
    bounded_provider_failure_class,
    bounded_usage,
)
from synthesis.candidate_processing import CandidateExecutionRequest
from synthesis.contacts_domain_pack import ContactsDomainRun, open_contacts_domain_run
from synthesis.contacts_live_acceptance import LiveContactsAcceptanceAuthorization
from synthesis.coverage_assignments import (
    _assignment_generation_spec,
    _single_provider_record,
    _validate_assignment_membership,
    _with_locally_derived_difficulty,
    build_coverage_assignment_prompt,
    issue_initial_coverage_assignments,
)
from synthesis.coverage_registry import resolve_domain_coverage_planning
from synthesis.domain_generation import (
    DomainGenerationValidationError,
    build_generation_batch_context,
    task_contract_from_provider_record,
)
from synthesis.domain_sources import build_domain_fixture_source_bundle
from synthesis.execution import scripted_solution_policy
from synthesis.llm import LLMConfig, LLMConfigurationError, LLMProviderError, OpenAICompatibleClient
from synthesis.mutation_admission import (
    CandidateAdmissionDecision,
    build_openai_compatible_semantic_mutation_judge,
)
from synthesis.pipeline import preview_coverage_plan
from synthesis.roles import TASK_GENERATION_ROLE, default_role_registry
from synthesis.run_profiles import RunProfile
from synthesis.sources import validate_source_bundle
from synthesis.task_contracts import candidate_from_task_contract


CONTACTS_LIVE_CONTRACT_CANARY_SCHEMA_VERSION = "contacts_live_contract_canary_v1"
CONTACTS_LIVE_CONTRACT_CANARY_FILENAME = "contacts_live_contract_canary.json"


class ContactsLiveContractCanaryError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ContactsLiveContractCanaryResult:
    status: str
    record_path: Path


def run_contacts_live_contract_canary(
    output_dir: Path,
    *,
    profile: RunProfile,
    authorization: LiveContactsAcceptanceAuthorization,
    generator_config: LLMConfig | None = None,
    generator_http_client: object | None = None,
    mutation_judge_http_client: object | None = None,
) -> ContactsLiveContractCanaryResult:
    """Check one follow-up generation contract without release qualification.

    The canary makes at most one generator request.  It retains only bounded
    identity, usage, assignment, and validation status; never provider content.
    """

    output_dir = Path(output_dir)
    record_path = output_dir / CONTACTS_LIVE_CONTRACT_CANARY_FILENAME
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ContactsLiveContractCanaryError("contacts_canary_output_not_empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    authorization_record = _authorization_record(authorization)
    try:
        if not isinstance(profile, RunProfile):
            raise ContactsLiveContractCanaryError("contacts_canary_profile_invalid")
        coverage_plan = preview_coverage_plan(profile)
        authorization.validate(
            profile=profile.canonical(),
            plan_attempt_ceiling=int(coverage_plan.attempt_ceiling),
        )
        config = _resolve_generator_config(generator_config)
        if config.model != authorization.generator_model:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_generator_identity_mismatch"
            )
        result_record = _run_one_followup_canary(
            profile=profile,
            authorization=authorization,
            config=config,
            generator_http_client=generator_http_client,
            mutation_judge_http_client=mutation_judge_http_client,
            coverage_plan=coverage_plan,
        )
    except Exception as exc:
        record = _failure_record(
            authorization_record=authorization_record,
            error=exc,
        )
        _write_json(record_path, record)
        if isinstance(exc, ContactsLiveContractCanaryError):
            raise
        raise ContactsLiveContractCanaryError(record["reason_code"]) from None

    record = {
        "schema_version": CONTACTS_LIVE_CONTRACT_CANARY_SCHEMA_VERSION,
        "status": "passed",
        "non_qualifying": True,
        "authorization": authorization_record,
        **result_record,
    }
    _write_json(record_path, record)
    return ContactsLiveContractCanaryResult(status="passed", record_path=record_path)


def _run_one_followup_canary(
    *,
    profile: RunProfile,
    authorization: LiveContactsAcceptanceAuthorization,
    config: LLMConfig,
    generator_http_client: object | None,
    mutation_judge_http_client: object | None,
    coverage_plan: object,
) -> dict[str, object]:
    source_bundle = build_domain_fixture_source_bundle(profile.seed.domain)
    source_result = validate_source_bundle(source_bundle)
    with tempfile.TemporaryDirectory(prefix="contacts-live-contract-canary-") as tmpdir:
        run = open_contacts_domain_run(
            source_bundle=source_bundle,
            source_result=source_result,
            output_dir=Path(tmpdir),
            include_branching=True,
        )
        if not isinstance(run, ContactsDomainRun) or run.generation_spec is None:
            raise ContactsLiveContractCanaryError("contacts_canary_domain_run_invalid")

        planning = resolve_domain_coverage_planning(profile.seed.domain)
        coverage_reference = profile.coverage_profile
        if coverage_reference is None:
            raise ContactsLiveContractCanaryError("contacts_canary_profile_invalid")
        coverage_profile = planning.resolve_profile(
            coverage_reference.profile_id,
            coverage_reference.version,
        )
        catalog = planning.resolve_catalog(coverage_profile.catalog_version)
        assignments = issue_initial_coverage_assignments(
            plan=coverage_plan,
            catalog=catalog,
            spec=run.generation_spec,
        )
        assignment = next(
            (
                item
                for item in assignments
                if item.dimensions.get("task_type") == "contact_followup"
            ),
            None,
        )
        if assignment is None:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_followup_assignment_missing"
            )

        assignment_spec = _assignment_generation_spec(run.generation_spec, assignment)
        batch_context = build_generation_batch_context(
            assignment_spec,
            batch_index=assignment.assignment_ordinal + 1,
        )
        prompt = build_coverage_assignment_prompt(
            assignment_spec,
            assignment=assignment,
            batch_context=batch_context,
        )
        client = OpenAICompatibleClient(
            config,
            http_client=generator_http_client,
            max_retries=0,
            timeout_seconds=authorization.generator_timeout_seconds,
        )
        result = default_role_registry().invoke_json(
            TASK_GENERATION_ROLE,
            client,
            prompt,
        )

        generation_lineage = {
            **result.lineage,
            "coverage_assignment": assignment.lineage(),
        }
        raw_record = _single_provider_record(result.content)
        contract = task_contract_from_provider_record(
            raw_record,
            seed=profile.seed,
            spec=assignment_spec,
            candidate_id_prefix=batch_context.candidate_id_prefix,
            generation_lineage=generation_lineage,
        )
        contract = _validate_assignment_membership(
            raw_record=raw_record,
            contract=contract,
            assignment=assignment,
            assignment_spec=assignment_spec,
            seed=profile.seed,
            batch_context=batch_context,
            generation_lineage=generation_lineage,
        )
        contract = _with_locally_derived_difficulty(contract, assignment)
        candidate = candidate_from_task_contract(contract)
        membership_reason = run._membership_reason(candidate)
        if membership_reason is not None:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_domain_plan_membership_rejected"
            )

        remote_evaluator, judge_observer = _remote_admission_evaluator(
            run=run,
            profile=profile,
            config=config,
            mutation_judge_http_client=mutation_judge_http_client,
        )
        admitted = run.attempt(
            CandidateExecutionRequest(sequence_index=0, raw_task=candidate),
            dataset_version=profile.dataset_version,
            llm_config=config,
            policy_generator=scripted_solution_policy,
            admission_evaluator=remote_evaluator,
        )
        if admitted.outcome.sample is None:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_remote_admission_rejected"
            )
        frozen_evidence = admitted.outcome.sample.get("mutation_admission")
        if not isinstance(frozen_evidence, Mapping):
            raise ContactsLiveContractCanaryError(
                "contacts_canary_admission_evidence_missing"
            )
        replayed_attempt = run.attempt(
            CandidateExecutionRequest(sequence_index=1, raw_task=candidate),
            dataset_version=profile.dataset_version,
            llm_config=LLMConfig(
                base_url=None,
                api_key=None,
                model="contacts-canary-provider-free-replay",
            ),
            policy_generator=scripted_solution_policy,
            admission_evaluator=_frozen_admission_evaluator(
                candidate_id=candidate.candidate_id,
                evidence=dict(frozen_evidence),
            ),
        )
        if replayed_attempt.outcome.sample is None or replayed_attempt.replay_subject is None:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_admission_replay_outcome_mismatch"
            )
        replay_result = run.replay(replayed_attempt.replay_subject)
        if replay_result.status != "passed":
            raise ContactsLiveContractCanaryError(
                "contacts_canary_admission_replay_contract_failed"
            )

        lineage = config.lineage(TASK_GENERATION_ROLE)
        return {
            "canary": {
                "task_type": "contact_followup",
                "assignment_id": assignment.assignment_id,
                "assignment_hash": assignment.assignment_hash,
                "membership": "passed",
            },
            "generator": {
                "provider_host": lineage["provider_host"],
                "model": config.model,
                "config_hash": lineage["config_hash"],
                "timeout_seconds": authorization.generator_timeout_seconds,
            },
            "generator_usage": {
                "logical_calls": 1,
                "physical_calls": 1,
                "physical_call_ceiling": 1,
                "retries": 0,
                "tokens": bounded_usage(result.lineage.get("tokens")),
            },
            "mutation_judge_usage": judge_observer.to_failure_record(),
            "admission_replay": {
                "status": "passed",
                "provider_calls": 0,
            },
        }


def _remote_admission_evaluator(
    *,
    run: ContactsDomainRun,
    profile: RunProfile,
    config: LLMConfig,
    mutation_judge_http_client: object | None,
):
    judge_configuration = profile.mutation_admission.judge
    if judge_configuration is None:
        raise ContactsLiveContractCanaryError("contacts_canary_judge_configuration_missing")
    observer = SanitizedMutationJudgeUsageObserver(attempt_ceiling=1)
    judge = build_openai_compatible_semantic_mutation_judge(
        config=LLMConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            model=judge_configuration.model,
            temperature=0.0,
        ),
        http_client=mutation_judge_http_client,
        timeout_seconds=float(judge_configuration.timeout_seconds),
        max_retries=int(judge_configuration.max_retries),
        thinking_mode=getattr(judge_configuration, "thinking_mode", None),
        attempt_observer=observer,
    )
    return run.build_admission_evaluator(mode="enforce", judge=judge), observer


def _frozen_admission_evaluator(*, candidate_id: str, evidence: dict[str, object]):
    def evaluate(task_contract: object, solution_policy: object) -> CandidateAdmissionDecision:
        del solution_policy
        intent = getattr(task_contract, "intent", None)
        if getattr(intent, "candidate_id", None) != candidate_id:
            raise ContactsLiveContractCanaryError(
                "contacts_canary_admission_evidence_mismatch"
            )
        return CandidateAdmissionDecision(
            execution_permitted=True,
            evidence=dict(evidence),
        )

    return evaluate


def _resolve_generator_config(supplied: LLMConfig | None) -> LLMConfig:
    try:
        config = supplied if supplied is not None else LLMConfig.from_env()
    except LLMConfigurationError as exc:
        raise ContactsLiveContractCanaryError(
            "contacts_canary_llm_configuration_required"
        ) from exc
    if not isinstance(config, LLMConfig) or not config.configured:
        raise ContactsLiveContractCanaryError("contacts_canary_llm_configuration_required")
    return config


def _authorization_record(
    authorization: LiveContactsAcceptanceAuthorization,
) -> dict[str, object]:
    return authorization.to_record()


def _failure_record(
    *,
    authorization_record: Mapping[str, object],
    error: Exception,
) -> dict[str, object]:
    reason_code = (
        error.reason_code
        if isinstance(error, ContactsLiveContractCanaryError)
        else "contacts_canary_failed"
    )
    generator_failure_class = (
        bounded_provider_failure_class(error)
        if isinstance(error, LLMProviderError)
        else None
    )
    record: dict[str, object] = {
        "schema_version": CONTACTS_LIVE_CONTRACT_CANARY_SCHEMA_VERSION,
        "status": "failed",
        "non_qualifying": True,
        "reason_code": reason_code,
        "authorization": dict(authorization_record),
        "generator_usage": {
            "logical_calls": 1 if isinstance(error, LLMProviderError) else 0,
            "physical_calls": 1 if isinstance(error, LLMProviderError) else 0,
            "physical_call_ceiling": 1,
            "retries": 0,
            "tokens": {},
        },
        "proof_root_published": False,
        "provider_evidence_frozen": False,
    }
    if generator_failure_class is not None:
        record["generator_failure_classes"] = {generator_failure_class: 1}
    if isinstance(error, DomainGenerationValidationError):
        record["reason_code"] = "contacts_canary_generation_contract_invalid"
        record["generation_schema_reason"] = error.reason
        record["generation_schema_detail"] = error.detail
    return record


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "CONTACTS_LIVE_CONTRACT_CANARY_FILENAME",
    "CONTACTS_LIVE_CONTRACT_CANARY_SCHEMA_VERSION",
    "ContactsLiveContractCanaryError",
    "ContactsLiveContractCanaryResult",
    "run_contacts_live_contract_canary",
]
