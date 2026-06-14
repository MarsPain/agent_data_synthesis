from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput
from synthesis.execution import SolutionPolicy, scripted_solution_policy
from synthesis.mcp import LocalContactsAdapterShim
from synthesis.mobile_environment import (
    MobileMessagesEnvironment,
    MobileMessagesEnvironmentInput,
)
from synthesis.mobile_tasks import (
    generate_mobile_fixture_candidates,
    scripted_mobile_solution_policy,
)
from synthesis.mobile_tools import build_mobile_tool_registry
from synthesis.runtime import EnvironmentRuntime
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, generate_foundation_candidates
from synthesis.tools import ToolRegistry, build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
RegistryBuilder = Callable[[EnvironmentRuntime], ToolRegistry]


@dataclass(frozen=True)
class DomainPipelineBundle:
    domain_id: str
    environment: EnvironmentRuntime
    registry: ToolRegistry
    verifier: ExactAnswerVerifier
    candidate_generator: CandidateGenerator
    policy_generator: PolicyGenerator
    registry_builder: RegistryBuilder
    adapter_shim: LocalContactsAdapterShim | None = None


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
        if enable_mcp_adapter:
            raise ValueError("MCP adapter support is contacts-only for mobile_messages_fixture")
        return _build_mobile_bundle(
            output_dir,
            source_provenance=source_provenance,
            mobile_environment_input=domain_environment_input,
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
    adapter_shim = None
    if base_bundle.domain_id == "contacts_fixture" and enable_mcp_adapter:
        adapter_shim = LocalContactsAdapterShim(
            environment=environment,
            registry=registry,
        )
    elif enable_mcp_adapter:
        raise ValueError(f"MCP adapter support is unavailable for {base_bundle.domain_id}")
    return DomainPipelineBundle(
        domain_id=base_bundle.domain_id,
        environment=environment,
        registry=registry,
        verifier=base_bundle.verifier,
        candidate_generator=base_bundle.candidate_generator,
        policy_generator=base_bundle.policy_generator,
        registry_builder=base_bundle.registry_builder,
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
    adapter_shim = (
        LocalContactsAdapterShim(environment=environment, registry=registry)
        if enable_mcp_adapter
        else None
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
        adapter_shim=adapter_shim,
    )


def _build_mobile_bundle(
    output_dir: Path,
    *,
    source_provenance: dict[str, object] | None,
    mobile_environment_input: object | None,
) -> DomainPipelineBundle:
    if mobile_environment_input is not None:
        assert isinstance(mobile_environment_input, MobileMessagesEnvironmentInput)
        environment = MobileMessagesEnvironment.create_from_input(
            output_dir,
            mobile_environment_input,
            source_provenance=source_provenance,
        )
    else:
        environment = MobileMessagesEnvironment.create_fixture(output_dir)
    registry = build_mobile_tool_registry(environment)
    return DomainPipelineBundle(
        domain_id="mobile_messages_fixture",
        environment=environment,
        registry=registry,
        verifier=ExactAnswerVerifier(),
        candidate_generator=generate_mobile_fixture_candidates,
        policy_generator=scripted_mobile_solution_policy,
        registry_builder=build_mobile_tool_registry,
    )
