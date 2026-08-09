"""Workspace implementation of the public Domain Pack lifecycle.

The shared framework receives only the plan/open/generate/fork/attempt/replay
surface.  The fixture environment, tool registry, mutation preparation, and
verifier remain private implementation details of this module.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, cast

from awm_runtime.episodes import episode_id_for_candidate
from awm_runtime.runtime import RuntimeActionRequest, RuntimeSession
from synthesis.candidate_processing import (
    CandidateExecutionRequest,
    CandidateProcessingContext,
    CandidateProcessingOptions,
    PolicyGenerator,
    ProvisionalCandidateOutcome,
    process_candidate_through_gates,
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
from synthesis.execution import ExecutionResult
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
from synthesis.stable_ids import stable_id
from synthesis.tasks import CandidateTask
from synthesis.tools import ToolRegistry
from synthesis.verification import ExactAnswerVerifier, verify_contract
from synthesis.workspace_environment import WorkspaceEnvironmentInput, WorkspaceTasksEnvironment
from synthesis.workspace_tasks import (
    build_workspace_generation_spec,
    generate_workspace_fixture_candidates,
    prepare_workspace_candidate,
    scripted_workspace_solution_policy,
    workspace_mutation_policies,
    workspace_semantic_mutation_judge,
)
from synthesis.workspace_tools import build_workspace_tool_registry


_WORKSPACE_PACK_ID = "workspace_tasks"
_WORKSPACE_RUNTIME_ID = "workspace_tasks_fixture"
_CANONICAL_TASK_TYPES = frozenset(
    {
        "workspace_item_search",
        "workspace_task_creation",
        "workspace_comment_update",
    }
)
_RUNTIME_TASK_TO_PLAN_PROJECTION = {
    "workspace_item_lookup": "workspace_item_search",
    "workspace_item_search": "workspace_item_search",
    "workspace_task_creation": "workspace_task_creation",
    "workspace_comment_update": "workspace_comment_update",
}
_LEGACY_FIXTURE_TASK_TO_PLAN_PROJECTION = {
    "workspace_item_lookup": "workspace_item_search",
    "workspace_task_creation": "workspace_task_creation",
    "workspace_comment_update": "workspace_comment_update",
    # The legacy fallback is a search-only branch of the item-search
    # projection, not an independent task type that a partial plan may evade.
    "workspace_branch_fallback": "workspace_item_search",
}
_PLAN_CAPABILITY_KEYS_BY_TASK_TYPE = {
    "workspace_item_search": ("item_search",),
    "workspace_task_creation": ("item_search", "task_creation"),
    "workspace_comment_update": ("item_search", "comment_addition"),
}
_WORKSPACE_REPLAY_REASON_CODES = frozenset(
    {
        "invalid_replay_subject",
        "plan_drift",
        "domain_pack_drift",
        "runtime_contract_drift",
        "source_drift",
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
class WorkspaceRuntimeScope:
    """Admitted runtime inputs; deliberately no environment or registry escape hatch."""

    runtime_contract: DomainRuntimeContractReference
    admitted_source: AdmittedSource
    source_bundle: SourceBundle
    source_result: SourceGovernanceResult
    output_dir: Path
    domain_environment_input: WorkspaceEnvironmentInput | None = None
    source_provenance: Mapping[str, object] | None = None
    enable_mcp_adapter: bool = False
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
class WorkspaceReplaySubject:
    """The exact, sanitized subject that a Domain run may replay."""

    plan_id: str
    plan_hash: str
    domain_pack_reference: DomainPackReference
    admitted_source: AdmittedSource
    runtime_contract: DomainRuntimeContractReference
    capability_references: tuple[DomainCapabilityReference, ...]
    verifier_id: str
    verifier_version: str
    candidate: CandidateTask
    candidate_contract_hash: str
    episode: Mapping[str, object]
    episode_hash: str


@dataclass(frozen=True)
class WorkspaceReplayResult:
    status: str
    reason_code: str
    replayed_action_count: int = 0

    def __post_init__(self) -> None:
        if (
            self.status not in {"passed", "rejected"}
            or self.reason_code not in _WORKSPACE_REPLAY_REASON_CODES
            or (self.status == "passed" and self.reason_code != "replay_verified")
            or (self.status == "rejected" and self.reason_code == "replay_verified")
            or self.replayed_action_count < 0
        ):
            raise DomainPackContractError("invalid_workspace_replay_result")


@dataclass(frozen=True)
class WorkspaceAttemptResult:
    outcome: ProvisionalCandidateOutcome
    replay_subject: WorkspaceReplaySubject | None
    evidence_hash: str


def admitted_workspace_source(
    source_bundle: SourceBundle,
    source_result: SourceGovernanceResult,
) -> AdmittedSource:
    """Project previously admitted source facts into the canonical plan contract."""

    if not isinstance(source_bundle, SourceBundle) or not isinstance(
        source_result,
        SourceGovernanceResult,
    ):
        raise DomainPackContractError("invalid_workspace_admitted_source")
    if source_result.policy_outcome != "allowed":
        raise DomainPackContractError("workspace_source_not_admitted")
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


def build_workspace_domain_pack() -> DomainPack:
    descriptor = initial_domain_pack_registry().descriptor_for(_WORKSPACE_PACK_ID)
    return DomainPack(
        descriptor=descriptor,
        lifecycle=_WorkspaceLifecycle(descriptor_runtime=descriptor.runtime_contracts[0]),
    )


def workspace_planning_intent(pack: DomainPack) -> DomainPlanningIntent:
    """Select the current Workspace execution projections without mutable defaults."""

    if pack.descriptor.domain_pack_id != _WORKSPACE_PACK_ID:
        raise DomainPackContractError("invalid_workspace_domain_pack")
    projections = tuple(
        item
        for item in pack.descriptor.task_capability_projections
        if item.task_type_key in _CANONICAL_TASK_TYPES
    )
    selected_capabilities = tuple(
        sorted(
            {
                capability
                for projection in projections
                for capability in projection.capability_references
            },
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


def open_workspace_domain_run(
    *,
    source_bundle: SourceBundle,
    source_result: SourceGovernanceResult,
    output_dir: Path,
    source_provenance: Mapping[str, object] | None = None,
    domain_environment_input: WorkspaceEnvironmentInput | None = None,
    enable_mcp_adapter: bool = False,
    representative_fixture: bool = False,
) -> WorkspaceDomainRun | OpenFailure:
    """Build the plan first, then open the Workspace runtime through the deep seam."""

    pack = build_workspace_domain_pack()
    try:
        admitted_source = admitted_workspace_source(source_bundle, source_result)
    except DomainPackContractError:
        return OpenFailure("source_drift")
    plan = pack.plan(workspace_planning_intent(pack), admitted_source)
    if isinstance(plan, PlanFailure):
        return OpenFailure("plan_contract_drift")
    return cast(
        WorkspaceDomainRun | OpenFailure,
        pack.open(
            plan,
            WorkspaceRuntimeScope(
                runtime_contract=plan.runtime_contract,
                admitted_source=admitted_source,
                source_bundle=source_bundle,
                source_result=source_result,
                output_dir=output_dir,
                domain_environment_input=domain_environment_input,
                source_provenance=source_provenance,
                enable_mcp_adapter=enable_mcp_adapter,
                representative_fixture=representative_fixture,
            ),
        ),
    )


class _WorkspaceLifecycle:
    def __init__(self, *, descriptor_runtime: DomainRuntimeContractReference) -> None:
        self._descriptor_runtime = descriptor_runtime

    def open(
        self,
        plan: DomainPlan,
        runtime_scope: object,
    ) -> WorkspaceDomainRun | OpenFailure:
        if not isinstance(runtime_scope, WorkspaceRuntimeScope):
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
            WorkspaceEnvironmentInput,
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
            verified_source = admitted_workspace_source(
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
            or runtime.runtime_id != _WORKSPACE_RUNTIME_ID
        ):
            return OpenFailure("runtime_contract_drift")
        try:
            provenance = dict(
                runtime_scope.source_provenance or runtime_scope.source_result.provenance
            )
            environment_root = runtime_scope.output_dir / "environment"
            if runtime_scope.domain_environment_input is None:
                environment = WorkspaceTasksEnvironment.create_fixture(
                    environment_root,
                    source_provenance=provenance,
                    representative=runtime_scope.representative_fixture,
                )
            else:
                environment = WorkspaceTasksEnvironment.create_from_input(
                    environment_root,
                    runtime_scope.domain_environment_input,
                    source_provenance=provenance,
                )
            registry = build_workspace_tool_registry(environment)
            generation_spec = (
                build_workspace_generation_spec(
                    environment,
                    registry,
                    representative=runtime_scope.representative_fixture,
                )
                if runtime_scope.domain_environment_input is None
                else None
            )
            return WorkspaceDomainRun(
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


class WorkspaceDomainRun:
    """One opened Workspace plan with domain-owned generation and isolation."""

    def __init__(
        self,
        *,
        plan: DomainPlan,
        runtime_scope: WorkspaceRuntimeScope,
        environment: WorkspaceTasksEnvironment,
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
        self._mutation_policies = workspace_mutation_policies(environment)

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
        if seed.domain != _WORKSPACE_RUNTIME_ID:
            raise ValueError("domain_generation_seed_mismatch")
        if provider_adapter is None:
            return generate_workspace_fixture_candidates(seed)
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
        return workspace_semantic_mutation_judge

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
        if "search_workspace_items" not in {str(tool.get("name")) for tool in tools}:
            return "search tool is not registered"
        try:
            result = self._registry.execute(
                "search_workspace_items",
                {"query": "launch", "kind": "task"},
            )
        except Exception:
            return "search tool smoke check failed"
        if result.get("item_id") != "task_launch_plan":
            return "search tool smoke check returned unexpected data"
        return None

    def fork(
        self,
        candidate_scope: object,
    ) -> WorkspaceCandidateRun | CandidateForkFailure:
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
            registry = build_workspace_tool_registry(environment)
            adapter_shim = _workspace_adapter_shim(
                environment=environment,
                registry=registry,
                enabled=self._runtime_scope.enable_mcp_adapter,
            )
        except Exception:
            return CandidateForkFailure("candidate_isolation_unavailable")
        return WorkspaceCandidateRun(
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
    ) -> WorkspaceAttemptResult:
        scope = DomainCandidateScope.for_plan(
            self._plan,
            candidate_id=request.raw_task.candidate_id,
            sequence_index=request.sequence_index,
        )
        forked = self.fork(scope)
        if isinstance(forked, CandidateForkFailure):
            outcome = _fork_failure_outcome(request, forked.reason_code)
            return WorkspaceAttemptResult(
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

    def replay(self, subject: object) -> WorkspaceReplayResult:
        if not isinstance(subject, WorkspaceReplaySubject):
            return WorkspaceReplayResult("rejected", "invalid_replay_subject")
        if subject.plan_id != self._plan.plan_id or subject.plan_hash != self._plan.plan_hash:
            return WorkspaceReplayResult("rejected", "plan_drift")
        if subject.domain_pack_reference != self._plan.domain_pack_reference:
            return WorkspaceReplayResult("rejected", "domain_pack_drift")
        if subject.runtime_contract != self._plan.runtime_contract:
            return WorkspaceReplayResult("rejected", "runtime_contract_drift")
        if subject.admitted_source != self._plan.admitted_source:
            return WorkspaceReplayResult("rejected", "source_drift")
        if tuple(subject.capability_references) != tuple(self._plan.capability_references):
            return WorkspaceReplayResult("rejected", "capability_contract_drift")
        if (
            subject.verifier_id != self._verifier.verifier_id
            or subject.verifier_version != self._verifier.version
        ):
            return WorkspaceReplayResult("rejected", "verifier_drift")
        try:
            episode_hash = canonical_domain_pack_hash(subject.episode)
            validate_episode_log_record(subject.episode)
        except (ContractValidationError, DomainPackContractError):
            return WorkspaceReplayResult("rejected", "episode_drift")
        if episode_hash != subject.episode_hash:
            return WorkspaceReplayResult("rejected", "episode_drift")
        if subject.episode.get("candidate_id") != subject.candidate.candidate_id:
            return WorkspaceReplayResult("rejected", "episode_drift")
        if subject.episode.get("episode_id") != episode_id_for_candidate(
            subject.candidate.candidate_id
        ):
            return WorkspaceReplayResult("rejected", "episode_drift")
        try:
            candidate_contract_hash = _candidate_contract_hash(subject.candidate)
        except ContractValidationError:
            return WorkspaceReplayResult("rejected", "candidate_contract_drift")
        if candidate_contract_hash != subject.candidate_contract_hash:
            return WorkspaceReplayResult("rejected", "candidate_contract_drift")
        runtime = subject.episode.get("runtime")
        if not isinstance(runtime, Mapping) or (
            runtime.get("runtime_id") != self._plan.runtime_contract.runtime_id
            or runtime.get("runtime_version")
            != self._environment.runtime_metadata().runtime_version
        ):
            return WorkspaceReplayResult("rejected", "runtime_contract_drift")
        episode_verifier = subject.episode.get("verifier")
        if not isinstance(episode_verifier, Mapping) or (
            episode_verifier.get("id") != self._verifier.verifier_id
            or episode_verifier.get("version") != self._verifier.version
        ):
            return WorkspaceReplayResult("rejected", "verifier_drift")
        membership_reason = self._membership_reason(subject.candidate)
        if membership_reason is not None:
            return WorkspaceReplayResult("rejected", "capability_contract_drift")
        try:
            with tempfile.TemporaryDirectory(prefix="workspace-domain-replay-") as tmpdir:
                environment = self._environment.rebuild(Path(tmpdir))
                registry = build_workspace_tool_registry(environment)
                session = RuntimeSession(
                    environment=environment,
                    registry=registry,
                    registry_builder=build_workspace_tool_registry,
                )
                replayed_actions = _replay_episode_actions(
                    subject.episode,
                    session=session,
                )
                if replayed_actions is None:
                    return WorkspaceReplayResult("rejected", "replay_evidence_mismatch")
                final_response = _episode_final_response(subject.episode)
                if final_response is None:
                    return WorkspaceReplayResult("rejected", "replay_evidence_mismatch")
                verification = verify_contract(
                    subject.candidate.contract(),
                    ExecutionResult(trajectory=[], final_response=final_response),
                    environment=environment,
                )
                outcome = subject.episode.get("outcome")
                accepted = isinstance(outcome, Mapping) and outcome.get("status") == "accepted"
                if accepted and not verification.passed:
                    return WorkspaceReplayResult("rejected", "replay_verification_failed")
                return WorkspaceReplayResult(
                    "passed",
                    "replay_verified",
                    replayed_action_count=replayed_actions,
                )
        except Exception:
            return WorkspaceReplayResult("rejected", "replay_execution_failed")

    def _membership_reason(self, candidate: CandidateTask) -> str | None:
        try:
            contract = candidate.contract()
        except ContractValidationError:
            return "invalid_task_contract"
        if contract.intent.domain_id != _WORKSPACE_RUNTIME_ID:
            return "domain_mismatch"
        expected_legacy_fingerprint = _legacy_fixture_candidate_fingerprints().get(
            candidate.candidate_id
        )
        if expected_legacy_fingerprint is not None:
            if _workspace_candidate_semantic_fingerprint(candidate) != (
                expected_legacy_fingerprint
            ):
                return "legacy_fixture_membership_mismatch"
            # The current fixture corpus predates canonical capability fields.
            # Its five exact fixture records remain bounded by the selected
            # task projection and its exact capability contract; they are not
            # a general legacy-task escape hatch.
            return self._legacy_fixture_membership_reason(contract.intent.task_type)

        task_type = contract.intent.task_type
        if task_type in {"workspace_branch_fallback", "workspace_item_lookup"}:
            return "legacy_task_not_in_plan"
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

        plan_capability_keys = tuple(
            item.capability_key for item in projection.capability_references
        )
        if plan_capability_keys != _PLAN_CAPABILITY_KEYS_BY_TASK_TYPE[projection_key]:
            return "capability_contract_drift"
        declared_capabilities = tuple(contract.intent.required_capabilities)
        if declared_capabilities not in {
            plan_capability_keys,
            tuple(task_spec.required_capabilities),
        }:
            return "capability_membership_mismatch"

        tools_by_name = {
            str(tool["name"]): tool for tool in self._generation_spec.tools
        }
        state_changing = any(
            tools_by_name[tool_name].get("side_effects") == "state_mutating"
            for tool_name in expected_tools
        )
        expected_state_types = tuple(task_spec.allowed_expected_state_checks)
        if tuple(check.check_type for check in contract.expected_state) != (
            expected_state_types
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
        for state_check in contract.expected_state:
            for state_field, observation_field in (
                task_spec.expected_state_reference_fields
            ):
                if (
                    state_field not in state_check.expected
                    or observation_field not in observation
                    or canonical_domain_pack_hash(state_check.expected[state_field])
                    != canonical_domain_pack_hash(observation[observation_field])
                ):
                    return "grounding_membership_mismatch"
        if not _matches_workspace_expected_answer(
            contract=contract,
            task_type=task_type,
            observation=observation,
        ):
            return "grounding_membership_mismatch"
        return _recovery_membership_reason(
            contract=contract,
            state_changing=state_changing,
        )

    def _legacy_fixture_membership_reason(self, task_type: str) -> str | None:
        """Apply the opened plan to a fingerprinted pre-lifecycle fixture."""

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
        plan_capability_keys = tuple(
            item.capability_key for item in projection.capability_references
        )
        if plan_capability_keys != _PLAN_CAPABILITY_KEYS_BY_TASK_TYPE[projection_key]:
            return "capability_contract_drift"
        return None


@lru_cache(maxsize=1)
def _legacy_fixture_candidate_fingerprints() -> dict[str, str]:
    """Return the bounded pre-lifecycle fixture compatibility projection."""

    fixture_seed = DomainSeed(
        seed_id="seed_workspace_lifecycle_fixture_contract_v1",
        domain=_WORKSPACE_RUNTIME_ID,
        description="Workspace lifecycle fixture compatibility contract.",
        task_taxonomy=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
    )
    return {
        candidate.candidate_id: _workspace_candidate_semantic_fingerprint(candidate)
        for candidate in generate_workspace_fixture_candidates(fixture_seed)
    }


def _workspace_candidate_semantic_fingerprint(candidate: CandidateTask) -> str:
    """Hash task semantics while allowing the caller's nonsemantic seed lineage."""

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
                and canonical_domain_pack_hash(dict(primary_arguments))
                == arguments_hash
            ):
                return observation
    return None


def _matches_workspace_expected_answer(
    *,
    contract: object,
    task_type: str,
    observation: Mapping[str, object],
) -> bool:
    """Verify the plan-owned final-answer grounding for canonical task types."""

    # The caller passes a validated TaskContract; keeping the public helper
    # structural avoids exposing TaskContract as another lifecycle seam.
    expected_outcome = getattr(contract, "expected_outcome", None)
    expected_state = getattr(contract, "expected_state", ())
    answer = getattr(expected_outcome, "final_answer_contains", None)
    if not isinstance(answer, str):
        return False
    if task_type == "workspace_item_search":
        return answer in {
            str(observation[field_name])
            for field_name in ("item_id", "summary")
            if isinstance(observation.get(field_name), str)
        }
    state_values: dict[str, object] = {}
    for state_check in expected_state:
        expected = getattr(state_check, "expected", None)
        if isinstance(expected, Mapping):
            state_values.update(expected)
    if task_type == "workspace_task_creation":
        title = state_values.get("title")
        return isinstance(title, str) and answer == f"task_{stable_id(title)}"
    if task_type == "workspace_comment_update":
        task_id = state_values.get("task_id")
        comment = state_values.get("comment")
        return (
            isinstance(task_id, str)
            and isinstance(comment, str)
            and answer == f"comment_{task_id}_{stable_id(comment)}"
        )
    return False


def _recovery_membership_reason(
    *,
    contract: object,
    state_changing: bool,
) -> str | None:
    intent = getattr(contract, "intent", None)
    policy_hint = getattr(contract, "policy_hint", None)
    difficulty = getattr(intent, "difficulty", None)
    recovery_paths = (
        difficulty.get("recovery_paths") if isinstance(difficulty, Mapping) else None
    )
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
    lineage = getattr(intent, "lineage", None)
    generation_lineage = (
        lineage.get("generation") if isinstance(lineage, Mapping) else None
    )
    coverage_assignment = (
        generation_lineage.get("coverage_assignment")
        if isinstance(generation_lineage, Mapping)
        else None
    )
    if not isinstance(coverage_assignment, Mapping) or not isinstance(
        coverage_assignment.get("assignment_id"),
        str,
    ):
        return "recovery_assignment_missing"
    required_tools = getattr(policy_hint, "required_tools", ())
    branch_tools = _branch_plan_tool_names(branch_plan)
    if not branch_tools or not branch_tools <= set(required_tools):
        return "recovery_structure_mismatch"
    return None


def _branch_plan_tool_names(branch_plan: Mapping[str, object]) -> set[str]:
    raw_branches = branch_plan.get("branches")
    if not isinstance(raw_branches, list):
        return set()
    tool_names: set[str] = set()
    for branch in raw_branches:
        if not isinstance(branch, Mapping):
            return set()
        steps = branch.get("steps")
        if not isinstance(steps, list):
            return set()
        for step in steps:
            tool_name = step.get("tool_name") if isinstance(step, Mapping) else None
            if not isinstance(tool_name, str):
                return set()
            tool_names.add(tool_name)
    return tool_names


class WorkspaceCandidateRun:
    """Candidate-scoped Workspace state; it exposes no raw runtime session."""

    def __init__(
        self,
        *,
        domain_run: WorkspaceDomainRun,
        candidate_scope: DomainCandidateScope,
        environment: WorkspaceTasksEnvironment,
        registry: ToolRegistry,
        adapter_shim: LocalRuntimeAdapterShim | None,
    ) -> None:
        self._domain_run = domain_run
        self._candidate_scope = candidate_scope
        self._environment = environment
        self._registry = registry
        self._adapter_shim = adapter_shim

    def attempt(
        self,
        candidate: CandidateTask,
        *,
        dataset_version: str,
        llm_config: LLMConfig | None = None,
        policy_generator: PolicyGenerator | None = None,
        admission_evaluator: CandidateAdmissionEvaluator = permit_candidate_execution,
        options: CandidateProcessingOptions | None = None,
    ) -> WorkspaceAttemptResult:
        if candidate.candidate_id != self._candidate_scope.candidate_id:
            outcome = _fork_failure_outcome(
                CandidateExecutionRequest(
                    sequence_index=self._candidate_scope.sequence_index,
                    raw_task=candidate,
                ),
                "candidate_scope_plan_drift",
            )
            return WorkspaceAttemptResult(
                outcome=outcome,
                replay_subject=None,
                evidence_hash=_attempt_evidence_hash(
                    plan=self._domain_run.plan,
                    candidate_id=candidate.candidate_id,
                    episode_hash=None,
                    outcome_status="rejected",
                ),
            )
        prepared = prepare_workspace_candidate(candidate)
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
            generate_policy=policy_generator or scripted_workspace_solution_policy,
            admission_evaluator=admission_evaluator,
            membership_validator=self._domain_run._membership_reason,
        )
        outcome = process_candidate_through_gates(
            request=request,
            context=context,
            options=options or CandidateProcessingOptions(),
        )
        replay_subject = _replay_subject_from_outcome(
            plan=self._domain_run.plan,
            verifier=self._domain_run._verifier,
            candidate=prepared,
            outcome=outcome,
        )
        episode_hash = replay_subject.episode_hash if replay_subject is not None else None
        outcome_status = "accepted" if outcome.sample is not None else "rejected"
        return WorkspaceAttemptResult(
            outcome=outcome,
            replay_subject=replay_subject,
            evidence_hash=_attempt_evidence_hash(
                plan=self._domain_run.plan,
                candidate_id=outcome.candidate_id,
                episode_hash=episode_hash,
                outcome_status=outcome_status,
            ),
        )


def _workspace_adapter_shim(
    *,
    environment: WorkspaceTasksEnvironment,
    registry: ToolRegistry,
    enabled: bool,
) -> LocalRuntimeAdapterShim | None:
    if not enabled:
        return None
    session = RuntimeSession(
        environment=environment,
        registry=registry,
        registry_builder=build_workspace_tool_registry,
    )
    return LocalRuntimeAdapterShim(
        descriptor=runtime_descriptor(_WORKSPACE_RUNTIME_ID),
        session=session,
    )


def _fork_failure_outcome(
    request: CandidateExecutionRequest,
    reason_code: str,
) -> ProvisionalCandidateOutcome:
    return ProvisionalCandidateOutcome(
        sequence_index=request.sequence_index,
        candidate_id=request.raw_task.candidate_id,
        sample=None,
        rejection={
            "candidate_id": request.raw_task.candidate_id,
            "cause": "domain_run_isolation_failed",
            "details": {"reason_code": reason_code},
        },
        task_record=request.raw_task.export(),
    )


def _replay_subject_from_outcome(
    *,
    plan: DomainPlan,
    verifier: ExactAnswerVerifier,
    candidate: CandidateTask,
    outcome: ProvisionalCandidateOutcome,
) -> WorkspaceReplaySubject | None:
    episode = outcome.episode_log
    if episode is None:
        return None
    return WorkspaceReplaySubject(
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        domain_pack_reference=plan.domain_pack_reference,
        admitted_source=plan.admitted_source,
        runtime_contract=plan.runtime_contract,
        capability_references=tuple(plan.capability_references),
        verifier_id=verifier.verifier_id,
        verifier_version=verifier.version,
        candidate=candidate,
        candidate_contract_hash=_candidate_contract_hash(candidate),
        episode=dict(episode),
        episode_hash=canonical_domain_pack_hash(episode),
    )


def _candidate_contract_hash(candidate: CandidateTask) -> str:
    """Hash every semantic task-contract field bound to a replay episode."""

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
) -> str:
    return canonical_domain_pack_hash(
        {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "candidate_id": candidate_id,
            "episode_hash": episode_hash,
            "outcome_status": outcome_status,
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
        if observation is not None and (
            observation.get("observation_hash") != exported_result.get("observation_hash")
        ):
            return None
        state_change = _next_transition(transitions, index, "state_change", tool_name)
        if state_change is not None and (
            state_change.get("change_hash") != exported_result.get("state_change_hash")
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
