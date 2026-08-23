"""Contacts implementation of the public Domain Pack lifecycle.

Contacts remains a small fixture domain, but its current execution path is
plan-first and run-scoped.  The shared framework receives generation,
candidate isolation, attempt, replay, and assessment results without gaining
access to the Contacts environment, registry, candidate preparer, verifier,
or mutation-policy composition.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Mapping, cast

from awm_runtime.episodes import deterministic_content_hash, episode_id_for_candidate
from awm_runtime.runtime import RuntimeActionRequest, RuntimeSession
from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    CandidateProcessingContext,
    CandidateProcessingOptions,
    PolicyGenerator,
    ProvisionalCandidateOutcome,
    process_candidate_through_gates,
)
from synthesis.contacts_evidence import (
    build_contacts_evidence_binding,
    canonical_capability_references,
    contacts_task_capability_references,
    contacts_task_contract_hash,
)
from synthesis.contact_mutations import (
    build_contact_followup_semantic_mutation_judge,
    contact_followup_mutation_policies,
    prepare_contact_candidate,
)
from synthesis.contracts import ContractValidationError, validate_episode_log_record
from synthesis.domain_generation import (
    DomainGenerationGroundingRequest,
    DomainGenerationRequest,
    DomainGenerationResult,
    DomainGenerationSpec,
    generate_domain_llm_candidates,
    _resolve_read_only_generation_grounding,
)
from synthesis.domain_pack import (
    AdmittedSource,
    DomainCapabilityReference,
    DomainCandidateScope,
    DomainPack,
    DomainPackContractError,
    DomainPackReference,
    DomainPlan,
    DomainPlanningIntent,
    DomainRuntimeContractReference,
    OpenFailure,
    PlanFailure,
    canonical_domain_pack_hash,
    initial_domain_pack_registry,
)
from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput
from synthesis.execution import ExecutionResult, SolutionPolicy, scripted_solution_policy
from synthesis.llm import LLMConfig
from synthesis.mcp import LocalRuntimeAdapterShim
from synthesis.mutation_admission import (
    CandidateAdmissionEvaluator,
    SemanticMutationJudge,
    build_local_candidate_admission_evaluator,
    canonical_hash,
    permit_candidate_execution,
)
from synthesis.runtime_registry import runtime_descriptor
from synthesis.seeds import DomainSeed
from synthesis.sources import SourceBundle, SourceGovernanceResult, validate_source_bundle
from synthesis.tasks import CandidateTask, build_contacts_generation_spec, generate_foundation_candidates
from synthesis.tools import ToolRegistry, admit_curated_tool, build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier, verify_contract


_CONTACTS_PACK_ID = "contacts"
_CONTACTS_RUNTIME_ID = "contacts_fixture"
_CONTACTS_LEGACY_INPUT_COMPATIBILITY_VERSION = "domain_legacy_input_v1"
_CANONICAL_TASK_TYPES = frozenset(
    {"contact_lookup", "contact_followup", "contact_lookup_recovery"}
)
_RUNTIME_TASK_TO_PLAN_PROJECTION = {
    "contact_lookup": "contact_lookup",
    "contact_followup": "contact_followup",
    "contact_branch_fallback": "contact_lookup_recovery",
    "contact_lookup_recovery": "contact_lookup_recovery",
}
_LEGACY_FIXTURE_TASK_TO_PLAN_PROJECTION = {
    "contact_lookup": "contact_lookup",
    "contact_followup": "contact_followup",
    "contact_branch_fallback": "contact_lookup_recovery",
}
_PLAN_CAPABILITY_KEYS_BY_TASK_TYPE = {
    "contact_lookup": ("contact_lookup",),
    "contact_followup": ("contact_lookup", "followup_recording"),
    "contact_lookup_recovery": (
        "contact_lookup",
        "contact_lookup_recovery",
    ),
}
_CONTACTS_REPLAY_REASON_CODES = frozenset(
    {
        "invalid_replay_subject",
        "plan_drift",
        "domain_pack_drift",
        "runtime_contract_drift",
        "source_drift",
        "candidate_scope_drift",
        "capability_contract_drift",
        "verifier_drift",
        "episode_drift",
        "candidate_contract_drift",
        "replay_evidence_mismatch",
        "replay_verification_failed",
        "replay_execution_failed",
        "replay_verified",
    }
)


@dataclass(frozen=True)
class ContactsRuntimeScope:
    """Admitted runtime inputs; no environment or registry escape hatch."""

    runtime_contract: DomainRuntimeContractReference
    admitted_source: AdmittedSource
    source_bundle: SourceBundle
    source_result: SourceGovernanceResult
    output_dir: Path
    domain_environment_input: ContactsEnvironmentInput | None = None
    source_provenance: Mapping[str, object] | None = None
    enable_mcp_adapter: bool = False
    include_branching: bool = False
    representative_fixture: bool = False


@dataclass(frozen=True)
class CandidateForkFailure:
    reason_code: str
    status: str = "rejected"

    def __post_init__(self) -> None:
        if self.reason_code not in {
            "invalid_candidate_scope",
            "candidate_scope_plan_drift",
            "candidate_isolation_unavailable",
        } or self.status != "rejected":
            raise DomainPackContractError("invalid_candidate_fork_failure")


@dataclass(frozen=True)
class ContactsReplaySubject:
    """The exact, sanitized subject that a Contacts run may replay."""

    plan_id: str
    plan_hash: str
    domain_pack_reference: DomainPackReference
    admitted_source: AdmittedSource
    runtime_contract: DomainRuntimeContractReference
    capability_references: tuple[DomainCapabilityReference, ...]
    candidate_scope: DomainCandidateScope
    verifier_id: str
    verifier_version: str
    candidate: CandidateTask
    candidate_contract_hash: str
    episode: Mapping[str, object]
    episode_hash: str


@dataclass(frozen=True)
class ContactsReplayResult:
    status: str
    reason_code: str
    replayed_action_count: int = 0

    def __post_init__(self) -> None:
        if (
            self.status not in {"passed", "rejected"}
            or self.reason_code not in _CONTACTS_REPLAY_REASON_CODES
            or (self.status == "passed" and self.reason_code != "replay_verified")
            or (self.status == "rejected" and self.reason_code == "replay_verified")
            or self.replayed_action_count < 0
        ):
            raise DomainPackContractError("invalid_contacts_replay_result")


@dataclass(frozen=True)
class ContactsAttemptResult:
    outcome: ProvisionalCandidateOutcome
    replay_subject: ContactsReplaySubject | None
    evidence_hash: str


def admitted_contacts_source(
    source_bundle: SourceBundle,
    source_result: SourceGovernanceResult,
) -> AdmittedSource:
    """Project admitted source governance facts into the plan contract."""

    if not isinstance(source_bundle, SourceBundle) or not isinstance(
        source_result,
        SourceGovernanceResult,
    ):
        raise DomainPackContractError("invalid_contacts_admitted_source")
    if source_result.policy_outcome != "allowed":
        raise DomainPackContractError("contacts_source_not_admitted")
    source_facts = [
        {
            "source_id": source.source_id,
            "source_kind": source.source_kind,
            "content_hash": source.content_hash,
        }
        for source in sorted(source_bundle.sources, key=lambda item: item.source_id)
    ]
    return AdmittedSource(
        source_id=source_bundle.bundle_id,
        source_schema_version="source_bundle_v1",
        source_content_hash=canonical_domain_pack_hash(
            {
                "source_bundle_id": source_bundle.bundle_id,
                "sources": source_facts,
            }
        ),
        admission_policy_id="source_governance_v1",
        admission_policy_hash=source_result.source_policy_hash,
    )


def build_contacts_domain_pack() -> DomainPack:
    descriptor = initial_domain_pack_registry().descriptor_for(_CONTACTS_PACK_ID)
    return DomainPack(
        descriptor=descriptor,
        lifecycle=_ContactsLifecycle(descriptor_runtime=descriptor.runtime_contracts[0]),
    )


def contacts_planning_intent(pack: DomainPack) -> DomainPlanningIntent:
    """Select the exact current Contacts task and capability catalog."""

    if pack.descriptor.domain_pack_id != _CONTACTS_PACK_ID:
        raise DomainPackContractError("invalid_contacts_domain_pack")
    projections = tuple(
        item
        for item in pack.descriptor.task_capability_projections
        if item.task_type_key in _CANONICAL_TASK_TYPES
    )
    selected_capabilities = tuple(
        sorted(
            pack.descriptor.capability_references,
            key=lambda item: (
                item.domain_pack_id,
                item.capability_key,
                item.capability_contract_version,
            ),
        )
    )
    return DomainPlanningIntent(
        domain_pack_reference=pack.descriptor.reference(),
        task_type_keys=tuple(
            item.task_type_key
            for item in sorted(projections, key=lambda item: item.task_type_key)
        ),
        capability_references=selected_capabilities,
        runtime_contract=pack.descriptor.runtime_contracts[0],
    )


def open_contacts_domain_run(
    *,
    source_bundle: SourceBundle,
    source_result: SourceGovernanceResult,
    output_dir: Path,
    source_provenance: Mapping[str, object] | None = None,
    domain_environment_input: ContactsEnvironmentInput | None = None,
    enable_mcp_adapter: bool = False,
    include_branching: bool = False,
    representative_fixture: bool = False,
) -> ContactsDomainRun | OpenFailure:
    """Compile the Contacts plan before constructing any runtime state."""

    pack = build_contacts_domain_pack()
    try:
        admitted_source = admitted_contacts_source(source_bundle, source_result)
    except DomainPackContractError:
        return OpenFailure("source_drift")
    plan = pack.plan(contacts_planning_intent(pack), admitted_source)
    if isinstance(plan, PlanFailure):
        return OpenFailure("plan_contract_drift")
    return cast(
        ContactsDomainRun | OpenFailure,
        pack.open(
            plan,
            ContactsRuntimeScope(
                runtime_contract=plan.runtime_contract,
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=output_dir,
                domain_environment_input=domain_environment_input,
                source_provenance=source_provenance,
                enable_mcp_adapter=enable_mcp_adapter,
                include_branching=include_branching,
                representative_fixture=representative_fixture,
            ),
        ),
    )


class _ContactsLifecycle:
    def __init__(self, *, descriptor_runtime: DomainRuntimeContractReference) -> None:
        self._descriptor_runtime = descriptor_runtime

    def open(
        self,
        plan: DomainPlan,
        runtime_scope: object,
    ) -> ContactsDomainRun | OpenFailure:
        if not isinstance(runtime_scope, ContactsRuntimeScope):
            return OpenFailure("invalid_runtime_scope")
        if not isinstance(runtime_scope.admitted_source, AdmittedSource):
            return OpenFailure("invalid_runtime_scope")
        if not isinstance(runtime_scope.source_bundle, SourceBundle) or not isinstance(
            runtime_scope.source_result,
            SourceGovernanceResult,
        ):
            return OpenFailure("invalid_runtime_scope")
        if runtime_scope.runtime_contract != plan.runtime_contract:
            return OpenFailure("runtime_contract_drift")
        if runtime_scope.runtime_contract != self._descriptor_runtime:
            return OpenFailure("runtime_contract_drift")
        if runtime_scope.admitted_source != plan.admitted_source:
            return OpenFailure("source_drift")
        if (
            runtime_scope.source_result.source_bundle_id
            != runtime_scope.source_bundle.bundle_id
            or runtime_scope.admitted_source.source_id
            != runtime_scope.source_bundle.bundle_id
        ):
            return OpenFailure("source_drift")
        if runtime_scope.source_result.policy_outcome != "allowed":
            return OpenFailure("source_drift")
        if runtime_scope.domain_environment_input is not None and not isinstance(
            runtime_scope.domain_environment_input,
            ContactsEnvironmentInput,
        ):
            return OpenFailure("invalid_runtime_scope")
        if runtime_scope.domain_environment_input is not None and (
            runtime_scope.domain_environment_input.source_bundle_id
            != runtime_scope.source_bundle.bundle_id
            or runtime_scope.domain_environment_input.source_policy_hash
            != runtime_scope.source_result.source_policy_hash
        ):
            return OpenFailure("source_drift")
        if not isinstance(runtime_scope.output_dir, Path):
            return OpenFailure("invalid_runtime_scope")
        if runtime_scope.source_provenance is not None and not isinstance(
            runtime_scope.source_provenance,
            Mapping,
        ):
            return OpenFailure("invalid_runtime_scope")
        try:
            verified_source_result = validate_source_bundle(runtime_scope.source_bundle)
            verified_source = admitted_contacts_source(
                runtime_scope.source_bundle,
                verified_source_result,
            )
        except Exception:
            return OpenFailure("source_drift")
        if (
            verified_source_result.source_policy_hash
            != runtime_scope.source_result.source_policy_hash
            or verified_source != plan.admitted_source
        ):
            return OpenFailure("source_drift")
        try:
            runtime = runtime_descriptor(plan.runtime_contract.runtime_id)
        except Exception:
            return OpenFailure("runtime_contract_drift")
        if (
            runtime.runtime_id != plan.runtime_contract.runtime_id
            or runtime.runtime_version != plan.runtime_contract.runtime_version
            or runtime.runtime_id != _CONTACTS_RUNTIME_ID
        ):
            return OpenFailure("runtime_contract_drift")
        try:
            provenance = dict(
                runtime_scope.source_provenance or runtime_scope.source_result.provenance
            )
            environment_root = runtime_scope.output_dir / "environment"
            if runtime_scope.domain_environment_input is None:
                environment = ContactEnvironment.create_fixture(
                    environment_root,
                    source_provenance=provenance,
                    representative=runtime_scope.representative_fixture,
                )
            else:
                environment = ContactEnvironment.create_from_input(
                    environment_root,
                    runtime_scope.domain_environment_input,
                    source_provenance=provenance,
                )
            registry = build_contact_tool_registry(environment)
            generation_spec = (
                build_contacts_generation_spec(
                    environment,
                    registry,
                    domain_plan=plan,
                )
                if runtime_scope.domain_environment_input is None and registry.export()
                else None
            )
            return ContactsDomainRun(
                plan=plan,
                runtime_scope=runtime_scope,
                environment=environment,
                registry=registry,
                generation_spec=generation_spec,
                verifier=ExactAnswerVerifier(),
                source_provenance=provenance,
            )
        except Exception:
            return OpenFailure("runtime_construction_failed")


class ContactsDomainRun:
    """One opened Contacts plan with domain-owned generation and isolation."""

    def __init__(
        self,
        *,
        plan: DomainPlan,
        runtime_scope: ContactsRuntimeScope,
        environment: ContactEnvironment,
        registry: ToolRegistry,
        generation_spec: DomainGenerationSpec | None,
        verifier: ExactAnswerVerifier,
        source_provenance: Mapping[str, object],
    ) -> None:
        self._plan = plan
        self._runtime_scope = runtime_scope
        self._environment = environment
        self._registry = registry
        self._generation_spec = generation_spec
        self._verifier = verifier
        self._source_provenance = dict(source_provenance)
        self._mutation_policies = contact_followup_mutation_policies(environment)

    @property
    def plan(self) -> DomainPlan:
        return self._plan

    @property
    def generation_spec(self) -> DomainGenerationSpec | None:
        return self._generation_spec

    def generate(
        self,
        request: DomainGenerationRequest | DomainSeed,
        provider_adapter: object | None = None,
    ) -> list[CandidateTask] | DomainGenerationResult:
        if isinstance(request, DomainSeed):
            seed = request
            target_candidate_count = None
            role_registry = None
        elif isinstance(request, DomainGenerationRequest):
            seed = request.seed
            target_candidate_count = request.target_candidate_count
            role_registry = request.role_registry
        else:
            raise ValueError("invalid_domain_generation_request")
        if seed.domain not in {_CONTACTS_PACK_ID, _CONTACTS_RUNTIME_ID}:
            raise ValueError("domain_generation_seed_mismatch")
        if provider_adapter is None:
            return generate_foundation_candidates(
                seed,
                include_branching=self._runtime_scope.include_branching,
            )
        if self._generation_spec is None:
            raise ValueError("source_backed_remote_context_not_allowed")
        if target_candidate_count is None:
            raise ValueError("target_candidate_count_required")
        return generate_domain_llm_candidates(
            seed,
            provider_adapter,
            spec=self._generation_spec,
            target_candidate_count=target_candidate_count,
            role_registry=role_registry,
        )

    def resolve_generation_grounding(
        self,
        request: DomainGenerationGroundingRequest,
    ) -> dict[str, object]:
        return _resolve_read_only_generation_grounding(
            self._generation_spec,
            request,
            executor=self._registry.execute,
        )

    def default_mutation_judge(self) -> SemanticMutationJudge:
        return build_contact_followup_semantic_mutation_judge(self._environment)

    def build_admission_evaluator(
        self,
        *,
        mode: str,
        judge: SemanticMutationJudge | None,
    ) -> CandidateAdmissionEvaluator:
        state_changing_tools = tuple(
            str(tool["name"])
            for tool in self._registry.export()
            if tool.get("side_effects") == "state_mutating"
        )
        return build_local_candidate_admission_evaluator(
            mode=mode,
            policies=self._mutation_policies,
            state_changing_tools=state_changing_tools,
            judge=judge,
        )

    def foundation_gate_failure(self) -> str | None:
        metadata = self._environment.metadata()
        if not metadata.environment_id or not metadata.version or not metadata.reset_recipe:
            return "environment reset metadata is incomplete"
        tools = self._registry.export()
        if not tools:
            return "registered tool smoke check found no tools"
        if "lookup_contact_email" not in {str(tool.get("name")) for tool in tools}:
            return "lookup tool is not registered"
        try:
            result = self._registry.execute(
                "lookup_contact_email",
                {"name": "Alice Zhang"},
            )
        except Exception:
            return "lookup tool smoke check failed"
        if result.get("email") != "alice.zhang@example.test":
            return "lookup tool smoke check returned unexpected data"
        return None

    def fork(
        self,
        candidate_scope: object,
    ) -> ContactsCandidateRun | CandidateForkFailure:
        if not isinstance(candidate_scope, DomainCandidateScope):
            return CandidateForkFailure("invalid_candidate_scope")
        if (
            candidate_scope.plan_id != self._plan.plan_id
            or candidate_scope.plan_hash != self._plan.plan_hash
        ):
            return CandidateForkFailure("candidate_scope_plan_drift")
        candidate_root = self._runtime_scope.output_dir / "candidate-environments" / (
            f"{candidate_scope.sequence_index:04d}-{candidate_scope.candidate_id}"
        )
        try:
            environment = self._environment.rebuild(candidate_root)
            registry = build_contact_tool_registry(environment)
            adapter_shim = _contacts_adapter_shim(
                environment=environment,
                registry=registry,
                enabled=self._runtime_scope.enable_mcp_adapter,
            )
        except Exception:
            return CandidateForkFailure("candidate_isolation_unavailable")
        return ContactsCandidateRun(
            domain_run=self,
            candidate_scope=candidate_scope,
            environment=environment,
            registry=registry,
            adapter_shim=adapter_shim,
        )

    def attempt(
        self,
        request: CandidateExecutionRequest,
        *,
        dataset_version: str,
        llm_config: LLMConfig | None = None,
        policy_generator: PolicyGenerator | None = None,
        admission_evaluator: CandidateAdmissionEvaluator = permit_candidate_execution,
        options: CandidateProcessingOptions | None = None,
    ) -> ContactsAttemptResult:
        try:
            scope = DomainCandidateScope.for_plan(
                self._plan,
                candidate_id=request.raw_task.candidate_id,
                sequence_index=request.sequence_index,
            )
        except DomainPackContractError:
            # Let the normal candidate-contract gate retain a bounded schema
            # rejection instead of turning malformed input into a run crash.
            scope = DomainCandidateScope.for_plan(
                self._plan,
                candidate_id="invalid_candidate_scope",
                sequence_index=request.sequence_index,
            )
        forked = self.fork(scope)
        if isinstance(forked, CandidateForkFailure):
            outcome = _fork_failure_outcome(
                request,
                forked.reason_code,
                plan=self._plan,
                candidate_scope=scope,
            )
            return ContactsAttemptResult(
                outcome=outcome,
                replay_subject=None,
                evidence_hash=_attempt_evidence_hash(
                    plan=self._plan,
                    candidate_id=outcome.candidate_id,
                    episode_hash=None,
                    outcome_status="rejected",
                ),
            )
        return forked.attempt(
            request.raw_task,
            dataset_version=dataset_version,
            llm_config=llm_config,
            policy_generator=policy_generator,
            admission_evaluator=admission_evaluator,
            options=options,
        )

    def replay(self, subject: object) -> ContactsReplayResult:
        if not isinstance(subject, ContactsReplaySubject):
            return ContactsReplayResult("rejected", "invalid_replay_subject")
        if subject.plan_id != self._plan.plan_id or subject.plan_hash != self._plan.plan_hash:
            return ContactsReplayResult("rejected", "plan_drift")
        if subject.domain_pack_reference != self._plan.domain_pack_reference:
            return ContactsReplayResult("rejected", "domain_pack_drift")
        if subject.runtime_contract != self._plan.runtime_contract:
            return ContactsReplayResult("rejected", "runtime_contract_drift")
        if subject.admitted_source != self._plan.admitted_source:
            return ContactsReplayResult("rejected", "source_drift")
        if not isinstance(subject.candidate_scope, DomainCandidateScope):
            return ContactsReplayResult("rejected", "candidate_scope_drift")
        if (
            subject.candidate_scope.plan_id != self._plan.plan_id
            or subject.candidate_scope.plan_hash != self._plan.plan_hash
            or subject.candidate_scope.candidate_id != subject.candidate.candidate_id
        ):
            return ContactsReplayResult("rejected", "candidate_scope_drift")
        if tuple(subject.capability_references) != tuple(self._plan.capability_references):
            return ContactsReplayResult("rejected", "capability_contract_drift")
        if (
            subject.verifier_id != self._verifier.verifier_id
            or subject.verifier_version != self._verifier.version
        ):
            return ContactsReplayResult("rejected", "verifier_drift")
        try:
            episode_hash = deterministic_content_hash(subject.episode)
            validate_episode_log_record(subject.episode)
        except (ContractValidationError, DomainPackContractError):
            return ContactsReplayResult("rejected", "episode_drift")
        if episode_hash != subject.episode_hash:
            return ContactsReplayResult("rejected", "episode_drift")
        if subject.episode.get("candidate_id") != subject.candidate.candidate_id:
            return ContactsReplayResult("rejected", "episode_drift")
        if subject.episode.get("episode_id") != episode_id_for_candidate(
            subject.candidate.candidate_id
        ):
            return ContactsReplayResult("rejected", "episode_drift")
        try:
            candidate_contract_hash = _candidate_contract_hash(subject.candidate)
        except ContractValidationError:
            return ContactsReplayResult("rejected", "candidate_contract_drift")
        if candidate_contract_hash != subject.candidate_contract_hash:
            return ContactsReplayResult("rejected", "candidate_contract_drift")
        if not _contacts_episode_binding_matches(
            subject.episode,
            plan=self._plan,
            candidate=subject.candidate,
            candidate_scope=subject.candidate_scope,
            verifier=self._verifier,
        ):
            binding = subject.episode.get("contacts_evidence")
            if (
                isinstance(binding, Mapping)
                and binding.get("candidate_scope")
                != _candidate_scope_record(subject.candidate_scope)
            ):
                return ContactsReplayResult("rejected", "candidate_scope_drift")
            return ContactsReplayResult("rejected", "replay_evidence_mismatch")
        runtime = subject.episode.get("runtime")
        if not isinstance(runtime, Mapping) or (
            runtime.get("runtime_id") != self._plan.runtime_contract.runtime_id
            or runtime.get("runtime_version")
            != self._environment.runtime_metadata().runtime_version
        ):
            return ContactsReplayResult("rejected", "runtime_contract_drift")
        episode_verifier = subject.episode.get("verifier")
        if not isinstance(episode_verifier, Mapping) or (
            episode_verifier.get("id") != self._verifier.verifier_id
            or episode_verifier.get("version") != self._verifier.version
        ):
            return ContactsReplayResult("rejected", "verifier_drift")
        if self._membership_reason(subject.candidate) is not None:
            return ContactsReplayResult("rejected", "capability_contract_drift")
        try:
            with tempfile.TemporaryDirectory(prefix="contacts-domain-replay-") as tmpdir:
                environment = self._environment.rebuild(Path(tmpdir))
                registry = build_contact_tool_registry(environment)
                session = RuntimeSession(
                    environment=environment,
                    registry=registry,
                    registry_builder=build_contact_tool_registry,
                )
                replayed_actions = _replay_episode_actions(
                    subject.episode,
                    session=session,
                )
                if replayed_actions is None:
                    return ContactsReplayResult("rejected", "replay_evidence_mismatch")
                final_response = _episode_final_response(subject.episode)
                if final_response is None:
                    return ContactsReplayResult("rejected", "replay_evidence_mismatch")
                verification = verify_contract(
                    subject.candidate.contract(),
                    ExecutionResult(trajectory=[], final_response=final_response),
                    environment=environment,
                )
                outcome = subject.episode.get("outcome")
                accepted = isinstance(outcome, Mapping) and outcome.get("status") == "accepted"
                if accepted and not verification.passed:
                    return ContactsReplayResult("rejected", "replay_verification_failed")
                return ContactsReplayResult(
                    "passed",
                    "replay_verified",
                    replayed_action_count=replayed_actions,
                )
        except Exception:
            return ContactsReplayResult("rejected", "replay_execution_failed")

    def _membership_reason(self, candidate: CandidateTask) -> str | None:
        try:
            contract = candidate.contract()
        except ContractValidationError:
            return "invalid_task_contract"
        if contract.intent.domain_id != _CONTACTS_RUNTIME_ID:
            return "domain_mismatch"
        generation_lineage = contract.intent.lineage.get("generation")
        assignment = (
            generation_lineage.get("coverage_assignment")
            if isinstance(generation_lineage, Mapping)
            else None
        )
        expected_legacy_fingerprint = _legacy_fixture_candidate_fingerprints().get(
            candidate.candidate_id
        )
        if expected_legacy_fingerprint is not None:
            legacy_compatibility = (
                generation_lineage.get("input_compatibility")
                if isinstance(generation_lineage, Mapping)
                else None
            )
            if _contacts_candidate_semantic_fingerprint(candidate) != (
                expected_legacy_fingerprint
            ):
                if (
                    contract.intent.capability_references
                    or contract.intent.required_capabilities
                    or assignment is not None
                    or legacy_compatibility
                    != _CONTACTS_LEGACY_INPUT_COMPATIBILITY_VERSION
                ):
                    return "legacy_fixture_membership_mismatch"
            return self._legacy_fixture_membership_reason(contract.intent.task_type)

        # Deterministic foundation and task-expansion candidates predate
        # canonical capability references. Keep those bounded compatibility
        # inputs executable; assigned/provider contracts are checked strictly.
        if (
            generation_lineage.get("input_compatibility")
            == _CONTACTS_LEGACY_INPUT_COMPATIBILITY_VERSION
            and not contract.intent.capability_references
            and assignment is None
        ):
            return None

        task_type = contract.intent.task_type
        projection_key = _RUNTIME_TASK_TO_PLAN_PROJECTION.get(task_type)
        if projection_key is None:
            return "task_type_not_in_plan"
        projection = next(
            (
                item
                for item in self._plan.task_capability_projections
                if item.task_type_key == projection_key
            ),
            None,
        )
        if projection is None:
            return "task_type_not_in_plan"
        if self._generation_spec is None:
            return "generation_context_unavailable"
        task_spec = next(
            (
                item
                for item in self._generation_spec.task_types
                if item.task_type == task_type
            ),
            None,
        )
        if task_spec is None:
            return "task_type_not_in_generation_contract"
        expected_tools = tuple(task_spec.required_tools)
        if tuple(contract.policy_hint.required_tools) != expected_tools:
            return "tool_membership_mismatch"
        if contract.policy_hint.primary_tool != expected_tools[0]:
            return "primary_tool_membership_mismatch"
        if tuple(contract.intent.required_capabilities) != tuple(
            task_spec.required_capabilities
        ):
            return "capability_membership_mismatch"

        if assignment is not None:
            if not isinstance(assignment, Mapping):
                return "assignment_membership_mismatch"
            if any(
                not isinstance(assignment.get(field_name), str)
                or not str(assignment.get(field_name)).strip()
                for field_name in ("assignment_id", "assignment_hash", "plan_id", "plan_hash")
            ):
                return "assignment_membership_mismatch"

        expected_capability_references = tuple(projection.capability_references)
        recovery_paths = contract.intent.difficulty.get("recovery_paths")
        if (
            isinstance(recovery_paths, int)
            and not isinstance(recovery_paths, bool)
            and recovery_paths > 0
        ) or contract.policy_hint.branch_plan is not None:
            recovery_reference = next(
                (
                    reference
                    for reference in self._plan.capability_references
                    if reference.capability_key == "contact_lookup_recovery"
                ),
                None,
            )
            if recovery_reference is not None:
                expected_capability_references = tuple(
                    sorted(
                        {*expected_capability_references, recovery_reference},
                        key=lambda reference: (
                            reference.domain_pack_id,
                            reference.capability_key,
                            reference.capability_contract_version,
                        ),
                    )
                )
        if canonical_capability_references(
            tuple(contract.intent.capability_references)
        ) != canonical_capability_references(expected_capability_references):
            return "capability_membership_mismatch"
        if canonical_capability_references(tuple(task_spec.capability_references)) != (
            canonical_capability_references(tuple(projection.capability_references))
        ):
            return "capability_contract_drift"
        if assignment is not None:
            assignment_catalog = assignment.get("catalog")
            assignment_capabilities = (
                assignment_catalog.get("capability_references")
                if isinstance(assignment_catalog, Mapping)
                else None
            )
            if assignment_capabilities != canonical_capability_references(
                tuple(contract.intent.capability_references)
            ):
                return "assignment_membership_mismatch"
            assignment_branch_plan_hash = (
                assignment_catalog.get("branch_plan_hash")
                if isinstance(assignment_catalog, Mapping)
                else None
            )
            if assignment_branch_plan_hash != canonical_hash(
                contract.policy_hint.branch_plan
            ):
                return "recovery_assignment_mismatch"

        tools_by_name = {
            str(tool["name"]): tool for tool in self._generation_spec.tools
        }
        state_changing = any(
            tools_by_name[tool_name].get("side_effects") == "state_mutating"
            for tool_name in expected_tools
        )
        if tuple(check.check_type for check in contract.expected_state) != tuple(
            task_spec.allowed_expected_state_checks
        ):
            return "expected_state_membership_mismatch"
        declared_state_changes = contract.intent.difficulty.get("state_changes")
        if (
            not isinstance(declared_state_changes, int)
            or isinstance(declared_state_changes, bool)
            or declared_state_changes != int(state_changing)
        ):
            return "state_behavior_membership_mismatch"
        observation = _grounding_observation_for_arguments(
            self._generation_spec,
            contract.policy_hint.primary_arguments,
        )
        if observation is None:
            return "grounding_membership_mismatch"
        for state_field, observation_field in task_spec.expected_state_reference_fields:
            for state_check in contract.expected_state:
                expected = state_check.expected
                if (
                    state_field not in expected
                    or observation_field not in observation
                    or canonical_domain_pack_hash(expected[state_field])
                    != canonical_domain_pack_hash(observation[observation_field])
                ):
                    return "grounding_membership_mismatch"
        if not _matches_contacts_expected_answer(
            contract=contract,
            observation=observation,
        ):
            return "grounding_membership_mismatch"
        return _recovery_membership_reason(
            contract=contract,
            state_changing=state_changing,
        )

    def _legacy_fixture_membership_reason(self, task_type: str) -> str | None:
        projection_key = _LEGACY_FIXTURE_TASK_TO_PLAN_PROJECTION.get(task_type)
        if projection_key is None:
            return "legacy_task_not_in_plan"
        projection = next(
            (
                item
                for item in self._plan.task_capability_projections
                if item.task_type_key == projection_key
            ),
            None,
        )
        if projection is None:
            return "legacy_task_not_in_plan"
        if tuple(item.capability_key for item in projection.capability_references) != (
            _PLAN_CAPABILITY_KEYS_BY_TASK_TYPE[projection_key]
        ):
            return "capability_contract_drift"
        return None


class ContactsCandidateRun:
    """Candidate-scoped Contacts state; no raw runtime session is exposed."""

    def __init__(
        self,
        *,
        domain_run: ContactsDomainRun,
        candidate_scope: DomainCandidateScope,
        environment: ContactEnvironment,
        registry: ToolRegistry,
        adapter_shim: LocalRuntimeAdapterShim | None,
    ) -> None:
        self._domain_run = domain_run
        self._candidate_scope = candidate_scope
        self._environment = environment
        self._registry = registry
        self._adapter_shim = adapter_shim
        self._rerun_count = 0

    def attempt(
        self,
        candidate: CandidateTask,
        *,
        dataset_version: str,
        llm_config: LLMConfig | None = None,
        policy_generator: PolicyGenerator | None = None,
        admission_evaluator: CandidateAdmissionEvaluator = permit_candidate_execution,
        options: CandidateProcessingOptions | None = None,
    ) -> ContactsAttemptResult:
        if (
            candidate.candidate_id != self._candidate_scope.candidate_id
            and _candidate_id_is_valid_scope_identifier(candidate.candidate_id)
        ):
            outcome = _fork_failure_outcome(
                CandidateExecutionRequest(
                    sequence_index=self._candidate_scope.sequence_index,
                    raw_task=candidate,
                ),
                "candidate_scope_plan_drift",
                plan=self._domain_run.plan,
                candidate_scope=self._candidate_scope,
            )
            outcome = _bind_contacts_outcome(
                plan=self._domain_run.plan,
                verifier=self._domain_run._verifier,
                candidate=candidate,
                candidate_scope=self._candidate_scope,
                outcome=outcome,
            )
            return ContactsAttemptResult(
                outcome=outcome,
                replay_subject=None,
                evidence_hash=_attempt_evidence_hash(
                    plan=self._domain_run.plan,
                    candidate_id=candidate.candidate_id,
                    episode_hash=None,
                    outcome_status="rejected",
                ),
            )
        prepared = prepare_contact_candidate(candidate)
        request = CandidateExecutionRequest(
            sequence_index=self._candidate_scope.sequence_index,
            raw_task=prepared,
        )
        context = CandidateProcessingContext(
            dataset_version=dataset_version,
            environment=self._environment,
            registry=self._registry,
            adapter_shim=self._adapter_shim,
            verifier=self._domain_run._verifier,
            llm_config=llm_config or LLMConfig.from_env(),
            generate_policy=policy_generator or scripted_solution_policy,
            admission_evaluator=admission_evaluator,
            membership_validator=self._domain_run._membership_reason,
            attempt_context_factory=self._build_rerun_context(
                dataset_version=dataset_version,
                llm_config=llm_config or LLMConfig.from_env(),
                policy_generator=policy_generator or scripted_solution_policy,
                admission_evaluator=admission_evaluator,
            ),
        )
        outcome = process_candidate_through_gates(
            request=request,
            context=context,
            options=options or CandidateProcessingOptions(),
        )
        bound_candidate = _without_legacy_input_marker(
            outcome.final_candidate or prepared
        )
        outcome = _bind_contacts_outcome(
            plan=self._domain_run.plan,
            verifier=self._domain_run._verifier,
            candidate=bound_candidate,
            candidate_scope=self._candidate_scope,
            outcome=outcome,
        )
        replay_subject = _replay_subject_from_outcome(
            plan=self._domain_run.plan,
            verifier=self._domain_run._verifier,
            candidate=bound_candidate,
            candidate_scope=self._candidate_scope,
            outcome=outcome,
        )
        binding = _outcome_contacts_binding(outcome)
        return ContactsAttemptResult(
            outcome=outcome,
            replay_subject=replay_subject,
            evidence_hash=_attempt_evidence_hash(
                plan=self._domain_run.plan,
                candidate_id=outcome.candidate_id,
                episode_hash=(
                    replay_subject.episode_hash if replay_subject is not None else None
                ),
                outcome_status="accepted" if outcome.sample is not None else "rejected",
            binding_hash=canonical_hash(binding) if binding is not None else None,
            ),
        )

    def _build_rerun_context(
        self,
        *,
        dataset_version: str,
        llm_config: LLMConfig,
        policy_generator: PolicyGenerator,
        admission_evaluator: CandidateAdmissionEvaluator,
    ):
        def factory(tool_proposal: object | None) -> CandidateProcessingContext:
            self._rerun_count += 1
            attempt_root = (
                self._domain_run._runtime_scope.output_dir
                / "candidate-environments"
                / f"{self._candidate_scope.sequence_index:04d}-{self._candidate_scope.candidate_id}"
                / "attempts"
                / f"{self._rerun_count:04d}"
            )
            environment = self._domain_run._environment.rebuild(attempt_root)
            registry = build_contact_tool_registry(environment)
            if tool_proposal is not None:
                admission = admit_curated_tool(tool_proposal, registry, environment)
                if not admission.accepted:
                    raise ValueError("rerun_tool_expansion_admission_failed")
            adapter_shim = _contacts_adapter_shim(
                environment=environment,
                registry=registry,
                enabled=self._domain_run._runtime_scope.enable_mcp_adapter,
            )
            return CandidateProcessingContext(
                dataset_version=dataset_version,
                environment=environment,
                registry=registry,
                adapter_shim=adapter_shim,
                verifier=self._domain_run._verifier,
                llm_config=llm_config,
                generate_policy=policy_generator,
                admission_evaluator=admission_evaluator,
                membership_validator=self._domain_run._membership_reason,
                attempt_context_factory=self._build_rerun_context(
                    dataset_version=dataset_version,
                    llm_config=llm_config,
                    policy_generator=policy_generator,
                    admission_evaluator=admission_evaluator,
                ),
            )

        return factory


def _bind_contacts_outcome(
    *,
    plan: DomainPlan,
    verifier: ExactAnswerVerifier,
    candidate: CandidateTask,
    candidate_scope: DomainCandidateScope,
    outcome: ProvisionalCandidateOutcome,
) -> ProvisionalCandidateOutcome:
    candidate = _without_legacy_input_marker(candidate)
    assignment = _candidate_assignment_lineage(candidate)
    if outcome.sample is not None:
        try:
            sample = _strip_legacy_input_marker(dict(outcome.sample))
            core_episode = (
                _strip_legacy_input_marker(dict(outcome.episode_log))
                if isinstance(outcome.episode_log, Mapping)
                else outcome.episode_log
            )
            binding = build_contacts_evidence_binding(
                plan=plan,
                candidate=candidate,
                verifier_id=verifier.verifier_id,
                verifier_version=verifier.version,
                sample=sample,
                episode=core_episode,
                episode_hash=(
                    deterministic_content_hash(core_episode)
                    if core_episode is not None
                    else None
                ),
                assignment=assignment,
                candidate_scope=_candidate_scope_record(candidate_scope),
            )
            _attach_contacts_binding_to_sample(sample, binding)
            episode = dict(core_episode) if isinstance(core_episode, Mapping) else None
            if episode is not None:
                episode["contacts_evidence"] = dict(binding)
            return replace(outcome, sample=sample, episode_log=episode)
        except (ContractValidationError, DomainPackContractError, ValueError):
            return replace(
                outcome,
                sample=None,
                rejection={
                    "candidate_id": outcome.candidate_id,
                    "cause": "domain_plan_membership_rejected",
                    "task": candidate.export(),
                    "details": {
                        "membership_reason": "evidence_binding_failed",
                        "contacts_evidence": _minimal_contacts_binding(
                            plan,
                            candidate_scope=candidate_scope,
                        ),
                        "domain_evidence": _minimal_contacts_binding(
                            plan,
                            candidate_scope=candidate_scope,
                        ),
                    },
                },
            )

    rejection = _strip_legacy_input_marker(dict(outcome.rejection or {}))
    raw_details = rejection.get("details")
    details = dict(raw_details) if isinstance(raw_details, Mapping) else {}
    try:
        binding = build_contacts_evidence_binding(
            plan=plan,
            candidate=candidate,
            verifier_id=verifier.verifier_id,
            verifier_version=verifier.version,
            sample={},
            episode=outcome.episode_log,
            episode_hash=(
                deterministic_content_hash(outcome.episode_log)
                if outcome.episode_log is not None
                else None
            ),
            assignment=assignment,
            candidate_scope=_candidate_scope_record(candidate_scope),
        )
    except ContractValidationError:
        binding = _minimal_contacts_binding(
            plan,
            candidate_scope=candidate_scope,
        )
    details["contacts_evidence"] = binding
    details["domain_evidence"] = binding
    rejection["details"] = details
    return replace(outcome, rejection=rejection)


def _attach_contacts_binding_to_sample(
    sample: dict[str, object],
    binding: Mapping[str, object],
) -> None:
    sample["contacts_evidence"] = dict(binding)
    sample["domain_evidence"] = dict(binding)
    for field_name in ("domain_pack_reference", "plan", "runtime_contract", "verifier"):
        value = binding.get(field_name)
        if isinstance(value, Mapping):
            sample["verifier_binding" if field_name == "verifier" else field_name] = dict(
                value
            )
    for field_name in ("capability_references", "task_capability_references"):
        value = binding.get(field_name)
        if isinstance(value, list):
            sample[field_name] = list(value)
    episode = binding.get("episode")
    if isinstance(episode, Mapping):
        sample["episode_binding"] = dict(episode)
    final_state = binding.get("final_state")
    if not isinstance(final_state, Mapping):
        final_state = binding.get("grounding")
    if isinstance(final_state, Mapping):
        sample["final_state_binding"] = dict(final_state)


def _candidate_assignment_lineage(candidate: CandidateTask) -> Mapping[str, object] | None:
    lineage = candidate.generation_lineage
    if not isinstance(lineage, Mapping):
        return None
    assignment = lineage.get("coverage_assignment")
    return assignment if isinstance(assignment, Mapping) else None


def _without_legacy_input_marker(candidate: CandidateTask) -> CandidateTask:
    lineage = candidate.generation_lineage
    if not isinstance(lineage, Mapping) or "input_compatibility" not in lineage:
        return candidate
    cleaned = dict(lineage)
    cleaned.pop("input_compatibility", None)
    return replace(candidate, generation_lineage=cleaned or None)


def _strip_legacy_input_marker(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _strip_legacy_input_marker(nested)
            for key, nested in value.items()
            if key != "input_compatibility"
        }
    if isinstance(value, list):
        return [_strip_legacy_input_marker(item) for item in value]
    return value


def _outcome_contacts_binding(
    outcome: ProvisionalCandidateOutcome,
) -> Mapping[str, object] | None:
    if outcome.sample is not None:
        binding = outcome.sample.get("contacts_evidence")
        return binding if isinstance(binding, Mapping) else None
    details = outcome.rejection.get("details") if outcome.rejection else None
    binding = details.get("contacts_evidence") if isinstance(details, Mapping) else None
    return binding if isinstance(binding, Mapping) else None


def _minimal_contacts_binding(
    plan: DomainPlan,
    *,
    candidate_scope: DomainCandidateScope | None = None,
) -> dict[str, object]:
    binding: dict[str, object] = {
        "schema_version": "contacts_evidence_binding_v1",
        "domain_pack_reference": plan.domain_pack_reference.to_record(),
        "plan": {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "plan_record": plan.to_record(),
        },
        "component_contracts": [
            contract.to_record() for contract in plan.component_contracts
        ],
        "source": plan.admitted_source.to_record(),
        "runtime_contract": plan.runtime_contract.to_record(),
        "capability_references": [
            reference.to_record() for reference in plan.capability_references
        ],
    }
    if candidate_scope is not None:
        binding["candidate_scope"] = _candidate_scope_record(candidate_scope)
    return binding


def _contacts_adapter_shim(
    *,
    environment: ContactEnvironment,
    registry: ToolRegistry,
    enabled: bool,
) -> LocalRuntimeAdapterShim | None:
    if not enabled:
        return None
    session = RuntimeSession(
        environment=environment,
        registry=registry,
        registry_builder=build_contact_tool_registry,
    )
    return LocalRuntimeAdapterShim(
        descriptor=runtime_descriptor(_CONTACTS_RUNTIME_ID),
        session=session,
    )


def _fork_failure_outcome(
    request: CandidateExecutionRequest,
    reason_code: str,
    *,
    plan: DomainPlan | None = None,
    candidate_scope: DomainCandidateScope | None = None,
) -> ProvisionalCandidateOutcome:
    details: dict[str, object] = {"reason_code": reason_code}
    if plan is not None:
        details["contacts_evidence"] = _minimal_contacts_binding(
            plan,
            candidate_scope=candidate_scope,
        )
        details["domain_evidence"] = details["contacts_evidence"]
    return ProvisionalCandidateOutcome(
        sequence_index=request.sequence_index,
        candidate_id=request.raw_task.candidate_id,
        sample=None,
        rejection={
            "candidate_id": request.raw_task.candidate_id,
            "cause": "domain_run_isolation_failed",
            "details": details,
        },
        task_record=request.raw_task.export(),
    )


def _replay_subject_from_outcome(
    *,
    plan: DomainPlan,
    verifier: ExactAnswerVerifier,
    candidate: CandidateTask,
    candidate_scope: DomainCandidateScope,
    outcome: ProvisionalCandidateOutcome,
) -> ContactsReplaySubject | None:
    episode = outcome.episode_log
    if episode is None:
        return None
    return ContactsReplaySubject(
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        domain_pack_reference=plan.domain_pack_reference,
        admitted_source=plan.admitted_source,
        runtime_contract=plan.runtime_contract,
        capability_references=tuple(plan.capability_references),
        candidate_scope=candidate_scope,
        verifier_id=verifier.verifier_id,
        verifier_version=verifier.version,
        candidate=candidate,
        candidate_contract_hash=_candidate_contract_hash(candidate),
        episode=dict(episode),
        episode_hash=deterministic_content_hash(episode),
    )


def _contacts_episode_binding_matches(
    episode: Mapping[str, object],
    *,
    plan: DomainPlan,
    candidate: CandidateTask,
    candidate_scope: DomainCandidateScope,
    verifier: ExactAnswerVerifier,
) -> bool:
    binding = episode.get("contacts_evidence")
    if not isinstance(binding, Mapping):
        return False
    if binding.get("schema_version") != "contacts_evidence_binding_v1":
        return False
    if binding.get("domain_pack_reference") != plan.domain_pack_reference.to_record():
        return False
    plan_binding = binding.get("plan")
    if not isinstance(plan_binding, Mapping) or (
        plan_binding.get("plan_id") != plan.plan_id
        or plan_binding.get("plan_hash") != plan.plan_hash
    ):
        return False
    if binding.get("source") != plan.admitted_source.to_record():
        return False
    if binding.get("candidate_scope") != _candidate_scope_record(candidate_scope):
        return False
    if binding.get("runtime_contract") != plan.runtime_contract.to_record():
        return False
    if binding.get("capability_references") != [
        reference.to_record() for reference in plan.capability_references
    ]:
        return False
    if binding.get("verifier") != {
        "id": verifier.verifier_id,
        "version": verifier.version,
    }:
        return False
    task_binding = binding.get("task_contract")
    if not isinstance(task_binding, Mapping):
        return False
    try:
        contract = candidate.contract()
    except ContractValidationError:
        return False
    assignment = binding.get("assignment")
    if assignment is not None:
        if not isinstance(assignment, Mapping):
            return False
        if binding.get("assignment_capability_references") != (
            canonical_capability_references(tuple(contract.intent.capability_references))
            if assignment.get("catalog") is not None
            else []
        ):
            # Assignment capability references are checked against the durable
            # catalog by membership; absence is valid for non-coverage runs.
            catalog = assignment.get("catalog")
            assignment_refs = (
                catalog.get("capability_references")
                if isinstance(catalog, Mapping)
                else None
            )
            if assignment_refs != canonical_capability_references(
                tuple(contract.intent.capability_references)
            ):
                return False
    final_state = binding.get("final_state")
    if not isinstance(final_state, Mapping):
        return False
    expected_state = [
        {
            "check_type": state_check.check_type,
            "expected": dict(state_check.expected),
        }
        for state_check in contract.expected_state
    ]
    if final_state.get("expected_state_hash") != canonical_domain_pack_hash(
        expected_state
    ):
        return False
    binding_episode = binding.get("episode")
    core_episode = dict(episode)
    core_episode.pop("contacts_evidence", None)
    return (
        task_binding.get("candidate_id") == contract.intent.candidate_id
        and task_binding.get("task_type") == contract.intent.task_type
        and task_binding.get("contract_hash") == contacts_task_contract_hash(candidate)
        and binding.get("task_capability_references")
        == canonical_capability_references(
            contacts_task_capability_references(plan, candidate)
        )
        and isinstance(binding_episode, Mapping)
        and binding_episode.get("episode_id") == episode.get("episode_id")
        and binding_episode.get("episode_hash") == deterministic_content_hash(core_episode)
        and binding_episode.get("core_episode_hash") == canonical_hash(core_episode)
    )


@lru_cache(maxsize=1)
def _legacy_fixture_candidate_fingerprints() -> dict[str, str]:
    fixture_seed = DomainSeed(
        seed_id="seed_contacts_lifecycle_fixture_contract_v1",
        domain=_CONTACTS_RUNTIME_ID,
        description="Contacts lifecycle fixture compatibility contract.",
        task_taxonomy=(
            "contact_lookup",
            "contact_followup",
            "contact_branch_fallback",
        ),
    )
    return {
        candidate.candidate_id: _contacts_candidate_semantic_fingerprint(candidate)
        for candidate in generate_foundation_candidates(
            fixture_seed,
            include_branching=True,
        )
    }


def _contacts_candidate_semantic_fingerprint(candidate: CandidateTask) -> str:
    contract = candidate.contract()
    return canonical_hash(
        {
            "candidate_id": candidate.candidate_id,
            "instruction": candidate.instruction,
            "constraints": dict(candidate.constraints),
            "difficulty": dict(candidate.difficulty),
            "tool_name": candidate.tool_name,
            "arguments": dict(candidate.arguments),
            "expected_answer": candidate.expected_answer,
            "expected_state": (
                {
                    check.check_type: dict(check.expected)
                    for check in contract.expected_state
                }
                if contract.expected_state
                else None
            ),
            "branch_plan": (
                dict(contract.policy_hint.branch_plan)
                if contract.policy_hint.branch_plan is not None
                else None
            ),
            "mutation_authorization": (
                dict(contract.mutation_authorization)
                if contract.mutation_authorization is not None
                else None
            ),
        }
    )


def _grounding_observation_for_arguments(
    spec: DomainGenerationSpec,
    arguments: Mapping[str, object],
) -> Mapping[str, object] | None:
    arguments_hash = canonical_domain_pack_hash(dict(arguments))
    for collection in spec.grounding_context.values():
        if not isinstance(collection, list):
            continue
        for entry in collection:
            if not isinstance(entry, Mapping):
                continue
            primary_arguments = entry.get("primary_arguments")
            observation = entry.get("observation")
            if (
                isinstance(primary_arguments, Mapping)
                and isinstance(observation, Mapping)
                and canonical_domain_pack_hash(dict(primary_arguments)) == arguments_hash
            ):
                return observation
    return None


def _matches_contacts_expected_answer(*, contract: object, observation: Mapping[str, object]) -> bool:
    expected_answer = getattr(getattr(contract, "expected_outcome", None), "final_answer_contains", None)
    if not isinstance(expected_answer, str):
        return False
    email = observation.get("email")
    if not isinstance(email, str) or expected_answer not in email:
        return False
    if getattr(getattr(contract, "intent", None), "task_type", None) != "contact_followup":
        return True
    state_values: dict[str, object] = {}
    for state_check in getattr(contract, "expected_state", ()):
        expected = getattr(state_check, "expected", None)
        if isinstance(expected, Mapping):
            state_values.update(expected)
    return (
        state_values.get("name") == observation.get("name")
        and isinstance(state_values.get("note"), str)
        and email in str(state_values["note"])
    )


def _recovery_membership_reason(*, contract: object, state_changing: bool) -> str | None:
    intent = getattr(contract, "intent", None)
    policy_hint = getattr(contract, "policy_hint", None)
    difficulty = getattr(intent, "difficulty", None)
    recovery_paths = difficulty.get("recovery_paths") if isinstance(difficulty, Mapping) else None
    branch_plan = getattr(policy_hint, "branch_plan", None)
    if branch_plan is None:
        if recovery_paths != 0:
            return "recovery_structure_mismatch"
        return None
    if (
        state_changing
        or not isinstance(recovery_paths, int)
        or isinstance(recovery_paths, bool)
        or recovery_paths < 1
    ):
        return "recovery_structure_mismatch"
    required_tools = getattr(policy_hint, "required_tools", ())
    branch_tools = _branch_plan_tool_names(branch_plan)
    if not branch_tools or not branch_tools <= set(required_tools):
        return "recovery_structure_mismatch"
    return None


def _branch_plan_tool_names(branch_plan: Mapping[str, object]) -> set[str]:
    raw_branches = branch_plan.get("branches")
    if not isinstance(raw_branches, list):
        return set()
    names: set[str] = set()
    for branch in raw_branches:
        if not isinstance(branch, Mapping) or not isinstance(branch.get("steps"), list):
            return set()
        for step in branch["steps"]:
            if not isinstance(step, Mapping) or not isinstance(step.get("tool_name"), str):
                return set()
            names.add(str(step["tool_name"]))
    return names


def _candidate_id_is_valid_scope_identifier(candidate_id: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9_.:-]{0,127}", candidate_id) is not None


def _candidate_scope_record(scope: DomainCandidateScope) -> dict[str, object]:
    return {
        "schema_version": scope.schema_version,
        "plan_id": scope.plan_id,
        "plan_hash": scope.plan_hash,
        "candidate_id": scope.candidate_id,
        "sequence_index": scope.sequence_index,
    }


def _candidate_contract_hash(candidate: CandidateTask) -> str:
    contract = candidate.contract()
    return canonical_hash(
        {
            "intent": {
                "candidate_id": contract.intent.candidate_id,
                "instruction": contract.intent.instruction,
                "domain_id": contract.intent.domain_id,
                "task_type": contract.intent.task_type,
                "difficulty": dict(contract.intent.difficulty),
                "required_capabilities": list(contract.intent.required_capabilities),
                "capability_references": [
                    reference.to_record()
                    for reference in contract.intent.capability_references
                ],
                "seed_ids": list(contract.intent.seed_ids),
                "lineage": dict(contract.intent.lineage),
            },
            "policy_hint": {
                "required_tools": list(contract.policy_hint.required_tools),
                "primary_tool": contract.policy_hint.primary_tool,
                "primary_arguments": dict(contract.policy_hint.primary_arguments),
                "branch_plan": (
                    dict(contract.policy_hint.branch_plan)
                    if contract.policy_hint.branch_plan is not None
                    else None
                ),
            },
            "expected_outcome": {
                "final_answer_contains": contract.expected_outcome.final_answer_contains,
            },
            "expected_state": [
                {
                    "check_type": check.check_type,
                    "expected": dict(check.expected),
                }
                for check in contract.expected_state
            ],
            "compatibility": dict(contract.compatibility),
            "mutation_authorization": (
                dict(contract.mutation_authorization)
                if contract.mutation_authorization is not None
                else None
            ),
        }
    )


def _attempt_evidence_hash(
    *,
    plan: DomainPlan,
    candidate_id: str,
    episode_hash: str | None,
    outcome_status: str,
    binding_hash: str | None = None,
) -> str:
    return canonical_domain_pack_hash(
        {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "candidate_id": candidate_id,
            "episode_hash": episode_hash,
            "outcome_status": outcome_status,
            "binding_hash": binding_hash,
        }
    )


def _replay_episode_actions(
    episode: Mapping[str, object],
    *,
    session: RuntimeSession,
) -> int | None:
    transitions = episode.get("transitions")
    if not isinstance(transitions, list):
        return None
    replayed_action_count = 0
    for index, transition in enumerate(transitions):
        if not isinstance(transition, Mapping) or transition.get("event_type") != "action":
            continue
        tool_name = transition.get("tool_name")
        arguments = transition.get("arguments")
        if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
            return None
        result = session.execute_action(
            RuntimeActionRequest(
                runtime_id=session.runtime_metadata().runtime_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                action_id=f"domain_replay_{transition.get('transition_index', index)}",
            )
        )
        if result.status != "succeeded":
            return None
        replayed_action_count += 1
        exported_result = result.export()
        observation = _next_transition(transitions, index, "observation", tool_name)
        if observation is not None and observation.get("observation_hash") != exported_result.get(
            "observation_hash"
        ):
            return None
        state_change = _next_transition(transitions, index, "state_change", tool_name)
        if state_change is not None and state_change.get("change_hash") != exported_result.get(
            "state_change_hash"
        ):
            return None
    return replayed_action_count


def _next_transition(
    transitions: list[object],
    start: int,
    event_type: str,
    tool_name: str,
) -> Mapping[str, object] | None:
    for transition in transitions[start + 1 :]:
        if not isinstance(transition, Mapping):
            continue
        if transition.get("event_type") == "action":
            return None
        if (
            transition.get("event_type") == event_type
            and transition.get("tool_name") == tool_name
        ):
            return transition
    return None


def _episode_final_response(episode: Mapping[str, object]) -> str | None:
    transitions = episode.get("transitions")
    if not isinstance(transitions, list):
        return None
    final = next(
        (
            transition
            for transition in transitions
            if isinstance(transition, Mapping)
            and transition.get("event_type") == "final_response"
        ),
        None,
    )
    content = final.get("content") if isinstance(final, Mapping) else None
    return content if isinstance(content, str) else None
