from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from awm_runtime.runtime import EnvironmentRuntime, RuntimeSession
from synthesis.contact_mutations import (
    build_contact_followup_semantic_mutation_judge,
    contact_followup_mutation_policies,
    prepare_contact_candidate,
)
from synthesis.domain_generation import DomainGenerationSpec
from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput
from synthesis.execution import SolutionPolicy, scripted_solution_policy
from synthesis.mcp import LocalRuntimeAdapterShim
from synthesis.mutation_admission import MutationActionPolicy, SemanticMutationJudge
from synthesis.mobile_environment import (
    MobileMessagesEnvironment,
    MobileMessagesEnvironmentInput,
)
from synthesis.mobile_mutations import (
    mobile_semantic_mutation_judge,
    mobile_mutation_policies,
    prepare_mobile_candidate,
)
from synthesis.mobile_tasks import (
    build_mobile_generation_spec,
    generate_mobile_fixture_candidates,
    scripted_mobile_solution_policy,
)
from synthesis.mobile_tools import build_mobile_tool_registry
from synthesis.runtime_registry import runtime_descriptor
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, build_contacts_generation_spec, generate_foundation_candidates
from synthesis.tools import ToolRegistry, build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier
from synthesis.workspace_environment import WorkspaceEnvironmentInput, WorkspaceTasksEnvironment
from synthesis.workspace_tasks import (
    build_workspace_generation_spec,
    generate_workspace_fixture_candidates,
    scripted_workspace_solution_policy,
    workspace_mutation_policies,
    workspace_semantic_mutation_judge,
)
from synthesis.workspace_tools import build_workspace_tool_registry


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
RegistryBuilder = Callable[[EnvironmentRuntime], ToolRegistry]
CandidatePreparer = Callable[[CandidateTask], CandidateTask]


def preserve_candidate(candidate: CandidateTask) -> CandidateTask:
    return candidate


@dataclass(frozen=True)
class DomainPipelineBundle:
    domain_id: str
    environment: EnvironmentRuntime
    registry: ToolRegistry
    verifier: ExactAnswerVerifier
    candidate_generator: CandidateGenerator
    policy_generator: PolicyGenerator
    registry_builder: RegistryBuilder
    generation_spec: DomainGenerationSpec | None
    candidate_preparer: CandidatePreparer = preserve_candidate
    mutation_policies: tuple[MutationActionPolicy, ...] = ()
    mutation_judge: SemanticMutationJudge | None = None
    adapter_shim: LocalRuntimeAdapterShim | None = None

    def runtime_session(self) -> RuntimeSession:
        return RuntimeSession(
            environment=self.environment,
            registry=self.registry,
            registry_builder=self.registry_builder,
        )


def build_domain_pipeline_bundle(
    seed: DomainSeed,
    output_dir: Path,
    *,
    source_provenance: dict[str, object] | None = None,
    domain_environment_input: object | None = None,
    enable_mcp_adapter: bool = False,
    include_branching: bool = False,
) -> DomainPipelineBundle:
    if seed.domain in {"contacts", "contacts_fixture"}:
        return _build_contacts_bundle(
            output_dir,
            source_provenance=source_provenance,
            domain_environment_input=domain_environment_input,
            enable_mcp_adapter=enable_mcp_adapter,
            include_branching=include_branching,
        )
    if seed.domain == "mobile_messages_fixture":
        if (
            domain_environment_input is not None
            and not isinstance(domain_environment_input, MobileMessagesEnvironmentInput)
        ):
            raise ValueError(
                "mobile_messages_fixture source input must be MobileMessagesEnvironmentInput"
            )
        return _build_mobile_bundle(
            output_dir,
            source_provenance=source_provenance,
            mobile_environment_input=domain_environment_input,
            enable_mcp_adapter=enable_mcp_adapter,
        )
    if seed.domain == "workspace_tasks_fixture":
        if (
            domain_environment_input is not None
            and not isinstance(domain_environment_input, WorkspaceEnvironmentInput)
        ):
            raise ValueError(
                "workspace_tasks_fixture source input must be WorkspaceEnvironmentInput"
            )
        return _build_workspace_bundle(
            output_dir,
            source_provenance=source_provenance,
            workspace_environment_input=domain_environment_input,
            enable_mcp_adapter=enable_mcp_adapter,
        )
    raise ValueError(f"Unsupported seed domain: {seed.domain}")


def rebuild_domain_pipeline_bundle(
    base_bundle: DomainPipelineBundle,
    output_dir: Path,
    *,
    enable_mcp_adapter: bool = False,
) -> DomainPipelineBundle:
    environment = base_bundle.environment.rebuild(output_dir)
    registry = base_bundle.registry_builder(environment)
    adapter_shim = _build_local_adapter_shim(
        base_bundle.domain_id,
        RuntimeSession(
            environment=environment,
            registry=registry,
            registry_builder=base_bundle.registry_builder,
        ),
        enable_mcp_adapter=enable_mcp_adapter,
    )
    return DomainPipelineBundle(
        domain_id=base_bundle.domain_id,
        environment=environment,
        registry=registry,
        verifier=base_bundle.verifier,
        candidate_generator=base_bundle.candidate_generator,
        policy_generator=base_bundle.policy_generator,
        registry_builder=base_bundle.registry_builder,
        generation_spec=base_bundle.generation_spec,
        candidate_preparer=base_bundle.candidate_preparer,
        mutation_policies=base_bundle.mutation_policies,
        mutation_judge=base_bundle.mutation_judge,
        adapter_shim=adapter_shim,
    )


def _build_contacts_bundle(
    output_dir: Path,
    *,
    source_provenance: dict[str, object] | None,
    domain_environment_input: object | None,
    enable_mcp_adapter: bool,
    include_branching: bool,
) -> DomainPipelineBundle:
    if (
        domain_environment_input is not None
        and not isinstance(domain_environment_input, ContactsEnvironmentInput)
    ):
        raise ValueError("contacts_fixture source input must be ContactsEnvironmentInput")
    if domain_environment_input is not None:
        environment = ContactEnvironment.create_from_input(
            output_dir,
            domain_environment_input,
            source_provenance=source_provenance,
        )
    else:
        environment = ContactEnvironment.create_fixture(
            output_dir,
            source_provenance=source_provenance,
        )
    registry = build_contact_tool_registry(environment)
    session = RuntimeSession(
        environment=environment,
        registry=registry,
        registry_builder=build_contact_tool_registry,
    )
    adapter_shim = _build_local_adapter_shim(
        "contacts_fixture",
        session,
        enable_mcp_adapter=enable_mcp_adapter,
    )
    candidate_generator: CandidateGenerator = generate_foundation_candidates
    if include_branching:
        candidate_generator = lambda seed: generate_foundation_candidates(
            seed,
            include_branching=True,
        )
    return DomainPipelineBundle(
        domain_id="contacts_fixture",
        environment=environment,
        registry=registry,
        verifier=ExactAnswerVerifier(),
        candidate_generator=candidate_generator,
        policy_generator=scripted_solution_policy,
        registry_builder=build_contact_tool_registry,
        generation_spec=(
            build_contacts_generation_spec(environment, registry)
            if domain_environment_input is None
            else None
        ),
        candidate_preparer=prepare_contact_candidate,
        mutation_policies=contact_followup_mutation_policies(environment),
        mutation_judge=build_contact_followup_semantic_mutation_judge(environment),
        adapter_shim=adapter_shim,
    )


def _build_mobile_bundle(
    output_dir: Path,
    *,
    source_provenance: dict[str, object] | None,
    mobile_environment_input: object | None,
    enable_mcp_adapter: bool,
) -> DomainPipelineBundle:
    if mobile_environment_input is not None:
        assert isinstance(mobile_environment_input, MobileMessagesEnvironmentInput)
        environment = MobileMessagesEnvironment.create_from_input(
            output_dir,
            mobile_environment_input,
            source_provenance=source_provenance,
        )
    else:
        environment = MobileMessagesEnvironment.create_fixture(
            output_dir,
            source_provenance=source_provenance,
        )
    registry = build_mobile_tool_registry(environment)
    session = RuntimeSession(
        environment=environment,
        registry=registry,
        registry_builder=build_mobile_tool_registry,
    )
    adapter_shim = _build_local_adapter_shim(
        "mobile_messages_fixture",
        session,
        enable_mcp_adapter=enable_mcp_adapter,
    )
    return DomainPipelineBundle(
        domain_id="mobile_messages_fixture",
        environment=environment,
        registry=registry,
        verifier=ExactAnswerVerifier(),
        candidate_generator=generate_mobile_fixture_candidates,
        policy_generator=scripted_mobile_solution_policy,
        registry_builder=build_mobile_tool_registry,
        generation_spec=(
            build_mobile_generation_spec(environment, registry)
            if mobile_environment_input is None
            else None
        ),
        candidate_preparer=prepare_mobile_candidate,
        mutation_policies=mobile_mutation_policies(environment),
        mutation_judge=mobile_semantic_mutation_judge,
        adapter_shim=adapter_shim,
    )


def _build_workspace_bundle(
    output_dir: Path,
    *,
    source_provenance: dict[str, object] | None,
    workspace_environment_input: object | None,
    enable_mcp_adapter: bool,
) -> DomainPipelineBundle:
    if workspace_environment_input is not None:
        assert isinstance(workspace_environment_input, WorkspaceEnvironmentInput)
        environment = WorkspaceTasksEnvironment.create_from_input(
            output_dir,
            workspace_environment_input,
            source_provenance=source_provenance,
        )
    else:
        environment = WorkspaceTasksEnvironment.create_fixture(
            output_dir,
            source_provenance=source_provenance,
        )
    registry = build_workspace_tool_registry(environment)
    session = RuntimeSession(
        environment=environment,
        registry=registry,
        registry_builder=build_workspace_tool_registry,
    )
    adapter_shim = _build_local_adapter_shim(
        "workspace_tasks_fixture",
        session,
        enable_mcp_adapter=enable_mcp_adapter,
    )
    return DomainPipelineBundle(
        domain_id="workspace_tasks_fixture",
        environment=environment,
        registry=registry,
        verifier=ExactAnswerVerifier(),
        candidate_generator=generate_workspace_fixture_candidates,
        policy_generator=scripted_workspace_solution_policy,
        registry_builder=build_workspace_tool_registry,
        generation_spec=(
            build_workspace_generation_spec(environment, registry)
            if workspace_environment_input is None
            else None
        ),
        mutation_policies=workspace_mutation_policies(),
        mutation_judge=workspace_semantic_mutation_judge,
        adapter_shim=adapter_shim,
    )


def _build_local_adapter_shim(
    runtime_id: str,
    session: RuntimeSession,
    *,
    enable_mcp_adapter: bool,
) -> LocalRuntimeAdapterShim | None:
    if not enable_mcp_adapter:
        return None
    descriptor = runtime_descriptor(runtime_id)
    return LocalRuntimeAdapterShim(descriptor=descriptor, session=session)
