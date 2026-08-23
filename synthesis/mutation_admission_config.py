from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass


MUTATION_ADMISSION_JUDGE_ROLE = "mutation_admission_judge"
MUTATION_ADMISSION_JUDGE_PROVIDER = "openai_compatible"
MUTATION_ADMISSION_JUDGE_REQUIRED_KEYS = {
    "role",
    "provider",
    "model",
    "timeout_seconds",
    "max_retries",
}
MUTATION_ADMISSION_JUDGE_OPTIONAL_KEYS = {"thinking_mode"}
MUTATION_ADMISSION_JUDGE_KEYS = (
    MUTATION_ADMISSION_JUDGE_REQUIRED_KEYS
    | MUTATION_ADMISSION_JUDGE_OPTIONAL_KEYS
)
MUTATION_ADMISSION_JUDGE_THINKING_MODES = {"enabled", "disabled"}
MAX_MUTATION_ADMISSION_JUDGE_TIMEOUT_SECONDS = 120.0
MAX_MUTATION_ADMISSION_JUDGE_RETRIES = 1
MODEL_IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}")


@dataclass(frozen=True)
class MutationAdmissionJudgeConfiguration:
    role: str
    provider: str
    model: str
    timeout_seconds: float
    max_retries: int
    thinking_mode: str | None = None

    def canonical(self) -> dict[str, object]:
        canonical: dict[str, object] = {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        if self.thinking_mode is not None:
            canonical["thinking_mode"] = self.thinking_mode
        return canonical


def parse_mutation_admission_judge_configuration(
    raw: object,
) -> MutationAdmissionJudgeConfiguration:
    if (
        not isinstance(raw, Mapping)
        or not MUTATION_ADMISSION_JUDGE_REQUIRED_KEYS <= set(raw)
        or not set(raw) <= MUTATION_ADMISSION_JUDGE_KEYS
    ):
        raise ValueError("must contain exact supported keys")
    role = raw.get("role")
    if role != MUTATION_ADMISSION_JUDGE_ROLE:
        raise ValueError(f"role must be {MUTATION_ADMISSION_JUDGE_ROLE}")
    provider = raw.get("provider")
    if provider != MUTATION_ADMISSION_JUDGE_PROVIDER:
        raise ValueError(f"provider must be {MUTATION_ADMISSION_JUDGE_PROVIDER}")
    model = raw.get("model")
    if not isinstance(model, str) or MODEL_IDENTITY_RE.fullmatch(model) is None:
        raise ValueError("model must be a bounded model identifier")
    timeout_seconds = raw.get("timeout_seconds")
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(float(timeout_seconds))
        or not 0
        < float(timeout_seconds)
        <= MAX_MUTATION_ADMISSION_JUDGE_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "timeout_seconds must be finite and in "
            f"(0, {MAX_MUTATION_ADMISSION_JUDGE_TIMEOUT_SECONDS:g}]"
        )
    max_retries = raw.get("max_retries")
    if (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= MAX_MUTATION_ADMISSION_JUDGE_RETRIES
    ):
        raise ValueError(
            f"max_retries must be between 0 and {MAX_MUTATION_ADMISSION_JUDGE_RETRIES}"
        )
    thinking_mode = raw.get("thinking_mode")
    if (
        thinking_mode is not None
        and (
            not isinstance(thinking_mode, str)
            or thinking_mode not in MUTATION_ADMISSION_JUDGE_THINKING_MODES
        )
    ):
        raise ValueError(
            "thinking_mode must be enabled, disabled, or omitted"
        )
    return MutationAdmissionJudgeConfiguration(
        role=role,
        provider=provider,
        model=model,
        timeout_seconds=float(timeout_seconds),
        max_retries=max_retries,
        thinking_mode=thinking_mode,
    )
