"""Validated, exportable configuration for one Agent-first synthesis run."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunConfiguration(BaseModel):
    """Configuration the core understands without learning Domain semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    domain_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    slot_limit: int = Field(ge=1, le=1_000)
    generation_batch_size: int = Field(default=8, ge=1, le=64)
    step_limit: int = Field(default=12, ge=1, le=64)
    total_request_limit: int = Field(default=256, ge=1, le=10_000)
    generation_request_limit: int = Field(default=64, ge=1, le=10_000)
    agent_request_limit: int = Field(default=192, ge=1, le=10_000)
    transport_retry_limit: int = Field(default=2, ge=0, le=2)
    decision_repair_limit: int = Field(default=1, ge=0, le=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_response_bytes: int = Field(default=64_000, ge=256, le=1_000_000)
    max_output_tokens: int = Field(default=1_024, ge=1, le=32_768)
    admission_mode: Literal["deterministic"] = "deterministic"

    @field_validator("run_id", "domain_id", "model_id")
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

    def normalized_public_record(self) -> dict[str, object]:
        """Return the complete configuration allowed in public artifacts."""

        return self.model_dump(mode="json")
