"""Validated, exportable configuration for one Agent-first synthesis run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunConfiguration(BaseModel):
    """Configuration the core understands without learning Domain semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    domain_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    slot_limit: int = Field(ge=1, le=1_000)
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
                "token",
            )
        ):
            raise ValueError("public configuration identifiers cannot contain credentials")
        return value

    def normalized_public_record(self) -> dict[str, object]:
        """Return the complete configuration allowed in public artifacts."""

        return self.model_dump(mode="json")
