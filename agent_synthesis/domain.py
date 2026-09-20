"""The deliberately small Domain adapter seam for the Agent-first core."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.episode import EpisodeAssessment, ExecutionTrace, PublicTask


class TaskSlot(BaseModel):
    """One deterministic, Domain-issued proposal slot."""

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
    def _fingerprint_binds_contents(self) -> FrozenInitialState:
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
    reason_code: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )


class ToolExecutionResult(BaseModel):
    """One bounded result from a Domain-owned tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result_type: Literal[
        "observation",
        "state_change",
        "tool_failure",
        "unauthorized_mutation",
    ]
    observation: dict[str, JsonValue] | None = None
    change: dict[str, JsonValue] | None = None
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    @model_validator(mode="after")
    def _match_payload_to_result_type(self) -> ToolExecutionResult:
        if self.result_type == "observation":
            if self.observation is None or self.change is not None or self.error_code is not None:
                raise ValueError("observation result requires only observation")
        elif self.result_type == "state_change":
            if self.change is None or self.observation is not None or self.error_code is not None:
                raise ValueError("state_change result requires only change")
        elif self.error_code is None or self.observation is not None or self.change is not None:
            raise ValueError("tool failure result requires only error_code")
        return self
class DomainEpisode(Protocol):
    """One isolated, Domain-owned Episode execution."""

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> ToolExecutionResult: ...

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

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> DomainEpisode: ...

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask: ...

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> DomainEpisode: ...


@runtime_checkable
class DomainAdapter(Protocol):
    """A registered Domain adapter with no dependency on core internals."""

    domain_id: str
    domain_version: str

    def open_run(self, configuration: RunConfiguration) -> DomainRun: ...


@runtime_checkable
class FrozenStateResumableDomainAdapter(Protocol):
    """Optional recovery capability for adapters that can reopen from private bytes."""

    def open_run_from_frozen_state(
        self,
        configuration: RunConfiguration,
        frozen_initial_state: FrozenInitialState,
    ) -> DomainRun: ...
