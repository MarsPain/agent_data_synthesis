"""Validated, exportable configuration for one Agent-first synthesis run."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_synthesis.enforcement import SemanticEnforcementRunConfiguration
from agent_synthesis.quality import ShadowQualityConfiguration


class RunConfiguration(BaseModel):
    """Configuration the core understands without learning Domain semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    domain_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    slot_limit: int = Field(ge=1, le=10_000)
    accepted_target: int | None = Field(default=None, ge=1, le=10_000)
    generation_batch_size: int = Field(default=8, ge=1, le=64)
    max_concurrency: int = Field(default=4, ge=1, le=16)
    step_limit: int = Field(default=12, ge=1, le=64)
    total_request_limit: int = Field(default=256, ge=1, le=100_000)
    generation_request_limit: int = Field(default=64, ge=1, le=100_000)
    agent_request_limit: int = Field(default=192, ge=1, le=100_000)
    transport_retry_limit: int = Field(default=2, ge=0, le=2)
    decision_repair_limit: int = Field(default=1, ge=0, le=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_response_bytes: int = Field(default=64_000, ge=256, le=1_000_000)
    max_output_tokens: int = Field(default=1_024, ge=1, le=32_768)
    source_scope_id: str = Field(
        default="agent_first_source_scope_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    task_distribution_scope_id: str = Field(
        default="agent_first_task_distribution_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    generator_prompt_id: str = Field(
        default="agent_task_generation_prompt_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    generator_decoding_id: str = Field(
        default="agent_task_generation_decoding_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    agent_prompt_id: str = Field(
        default="agent_rollout_prompt_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    agent_decoding_id: str = Field(
        default="agent_rollout_decoding_v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    admission_mode: Literal["deterministic", "enforced"] = "deterministic"
    shadow_quality: ShadowQualityConfiguration = Field(
        default_factory=ShadowQualityConfiguration
    )
    semantic_enforcement: SemanticEnforcementRunConfiguration | None = None

    @field_validator(
        "run_id",
        "domain_id",
        "model_id",
        "source_scope_id",
        "task_distribution_scope_id",
        "generator_prompt_id",
        "generator_decoding_id",
        "agent_prompt_id",
        "agent_decoding_id",
    )
    @classmethod
    def _reject_secret_shaped_identifier(cls, value: str) -> str:
        lowered = value.lower()
        if lowered.startswith(("sk-", "bearer-")) or any(
            marker in lowered
            for marker in (
                "api_key",
                "credential",
                "passwd",
                "password",
                "secret",
                "access_token",
            )
        ):
            raise ValueError("public configuration identifiers cannot contain credentials")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _require_finite_timeout(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("timeout_seconds must be finite")
        return value

    @model_validator(mode="before")
    @classmethod
    def _normalize_attempt_limit_aliases(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        record = dict(value)
        aliases = tuple(
            record.pop(name)
            for name in ("attempt_limit", "task_attempt_limit")
            if name in record
        )
        if not aliases:
            return record
        if len(set(aliases)) != 1:
            raise ValueError("attempt limit aliases must agree")
        alias_value = aliases[0]
        if "slot_limit" in record and record["slot_limit"] != alias_value:
            raise ValueError("slot_limit and attempt limit must agree")
        record["slot_limit"] = alias_value
        return record

    @model_validator(mode="after")
    def _bound_accepted_target_by_attempt_ceiling(self) -> RunConfiguration:
        if self.accepted_target is not None and self.accepted_target > self.slot_limit:
            raise ValueError("accepted_target cannot exceed slot_limit")
        if self.admission_mode == "enforced" and self.semantic_enforcement is None:
            raise ValueError("enforced admission requires semantic enforcement evidence")
        if self.admission_mode == "deterministic" and self.semantic_enforcement is not None:
            raise ValueError("deterministic admission cannot carry enforcement evidence")
        return self

    @property
    def attempt_limit(self) -> int:
        """Return the explicit ceiling for allocated task attempts."""

        return self.slot_limit

    def normalized_public_record(self) -> dict[str, object]:
        """Return the complete configuration allowed in public artifacts."""

        return self.model_dump(mode="json")
