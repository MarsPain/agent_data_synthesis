"""The deliberately small Domain adapter seam for the Agent-first core."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.episode import EpisodeAssessment, ExecutionTrace, PublicTask


class TaskSlot(BaseModel):
    """One deterministic, Domain-issued proposal slot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(min_length=1, max_length=256)
    proposal_prompt: str = Field(min_length=1, max_length=8_000)


class TaskGenerationRequest(BaseModel):
    """The bounded input supplied to a registered task-proposal model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(min_length=1, max_length=256)
    proposal_prompt: str = Field(min_length=1, max_length=8_000)


class TaskProposal(BaseModel):
    """A model proposal that a Domain, rather than the core, interprets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1, max_length=16_000)


class FrozenInitialState(BaseModel):
    """Opaque, privately persisted input bytes admitted by a Domain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contents: bytes = Field(min_length=1)

    @model_validator(mode="after")
    def _fingerprint_binds_contents(self) -> "FrozenInitialState":
        expected = "sha256:" + hashlib.sha256(self.contents).hexdigest()
        if self.fingerprint != expected:
            raise ValueError("frozen initial state fingerprint does not bind its contents")
        return self


@dataclass(frozen=True)
class CompiledTask:
    """A Domain-owned task case with a bounded public view and sealed private bytes."""

    public_task: PublicTask
    semantic_key: str
    private_case_bytes: bytes
    domain_case: object

    def __post_init__(self) -> None:
        if not self.semantic_key:
            raise ValueError("compiled task semantic_key must not be empty")
        if not self.private_case_bytes:
            raise ValueError("compiled task private_case_bytes must not be empty")


class CompilationRejection(BaseModel):
    """A sanitized deterministic compilation failure for the negatives collection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    public_task: PublicTask
    reason_code: str = Field(min_length=1, max_length=128)


@runtime_checkable
class DomainEpisode(Protocol):
    """One isolated, Domain-owned Episode execution."""

    def execute(self) -> ExecutionTrace: ...

    def assess(self, trace: ExecutionTrace) -> EpisodeAssessment: ...


@runtime_checkable
class DomainRun(Protocol):
    """Run-scoped Domain behavior hidden behind the core's one adapter seam."""

    def slots(self, limit: int) -> tuple[TaskSlot, ...]: ...

    def freeze_initial_state(self) -> FrozenInitialState: ...

    def compile(
        self,
        slot: TaskSlot,
        proposal: TaskProposal,
    ) -> CompiledTask | CompilationRejection: ...

    def open_episode(self, task: CompiledTask) -> DomainEpisode: ...


@runtime_checkable
class DomainAdapter(Protocol):
    """A registered Domain adapter with no dependency on core internals."""

    domain_id: str
    domain_version: str

    def open_run(self, configuration: RunConfiguration) -> DomainRun: ...


@runtime_checkable
class TaskProposalModel(Protocol):
    """A registered, provider-neutral proposal source for this first core slice."""

    model_id: str
    model_version: str

    def propose(self, request: TaskGenerationRequest) -> TaskProposal: ...
