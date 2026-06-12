from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from synthesis.environments import ContactEnvironment, ContactsEnvironmentInput
from synthesis.execution import SolutionPolicy, scripted_solution_policy
from synthesis.mcp import LocalContactsAdapterShim
from synthesis.mobile_environment import MobileMessagesEnvironment
from synthesis.mobile_tasks import (
    generate_mobile_fixture_candidates,
    scripted_mobile_solution_policy,
)
from synthesis.mobile_tools import build_mobile_tool_registry
from synthesis.seeds import DomainSeed
from synthesis.tasks import CandidateTask, generate_foundation_candidates
from synthesis.tools import ToolRegistry, build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


class PipelineEnvironment(Protocol):
    database_path: Path

    def metadata(self): ...

    def checkpoint(self) -> object: ...

    def restore_checkpoint(self, checkpoint: object) -> None: ...

    def rebuild(self, output_dir: Path): ...


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]
PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
RegistryBuilder = Callable[[PipelineEnvironment], ToolRegistry]


@dataclass(frozen=True)
class DomainPipelineBundle:
    domain_id: str
    environment: PipelineEnvironment
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
    contacts_environment_input: ContactsEnvironmentInput | None = None,
    enable_mcp_adapter: bool = False,
    include_branching: bool = False,
) -> DomainPipelineBundle:
    if seed.domain in {"contacts", "contacts_fixture"}:
        return _build_contacts_bundle(
            output_dir,
            source_provenance=source_provenance,
            contacts_environment_input=contacts_environment_input,
            enable_mcp_adapter=enable_mcp_adapter,
            include_branching=include_branching,
        )
    if seed.domain == "mobile_messages_fixture":
        if contacts_environment_input is not None:
            raise ValueError("mobile_messages_fixture does not support contacts source input")
        if enable_mcp_adapter:
            raise ValueError("MCP adapter support is contacts-only for mobile_messages_fixture")
        return _build_mobile_bundle(output_dir)
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
    contacts_environment_input: ContactsEnvironmentInput | None,
    enable_mcp_adapter: bool,
    include_branching: bool,
) -> DomainPipelineBundle:
    if contacts_environment_input is not None:
        environment = ContactEnvironment.create_from_input(
            output_dir,
            contacts_environment_input,
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


def _build_mobile_bundle(output_dir: Path) -> DomainPipelineBundle:
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
