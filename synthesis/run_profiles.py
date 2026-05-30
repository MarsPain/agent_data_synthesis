from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthesis.seeds import DomainSeed


RUN_PROFILE_SCHEMA_VERSION = "run_profile_v1"
GENERATION_MODES = {"foundation_fixture", "deterministic_scale_probe", "llm"}
FEATURE_KEYS = (
    "enable_branching",
    "enable_task_expansion",
    "enable_refinement",
    "enable_mcp_adapter",
    "enable_sandbox_fixture",
    "enable_source_governance_fixture",
)


class RunProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RunProfileGeneration:
    mode: str
    target_candidate_count: int | None = None

    def canonical(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "target_candidate_count": self.target_candidate_count,
        }


@dataclass(frozen=True)
class RunProfileFeatures:
    enable_branching: bool = False
    enable_task_expansion: bool = False
    enable_refinement: bool = False
    enable_mcp_adapter: bool = False
    enable_sandbox_fixture: bool = False
    enable_source_governance_fixture: bool = False

    def enabled_feature_names(self) -> list[str]:
        return [key for key in FEATURE_KEYS if bool(getattr(self, key))]

    def canonical(self) -> dict[str, object]:
        return {key: bool(getattr(self, key)) for key in FEATURE_KEYS}


@dataclass(frozen=True)
class RunProfile:
    schema_version: str
    profile_id: str
    dataset_version: str
    seed: DomainSeed
    generation: RunProfileGeneration
    features: RunProfileFeatures
    config_hash: str

    def sanitized_metadata(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "generation_mode": self.generation.mode,
            "target_candidate_count": self.generation.target_candidate_count,
            "config_hash": self.config_hash,
            "enabled_features": self.features.enabled_feature_names(),
        }

    def canonical(self) -> dict[str, object]:
        return _canonical_profile_mapping(
            schema_version=self.schema_version,
            profile_id=self.profile_id,
            dataset_version=self.dataset_version,
            seed=self.seed,
            generation=self.generation,
            features=self.features,
        )


def load_run_profile(path: Path) -> RunProfile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise RunProfileValidationError(f"run profile JSON is invalid: {exc}") from exc

    if not isinstance(raw, dict):
        raise RunProfileValidationError("run profile must be a JSON object")

    schema_version = _require_string(raw.get("schema_version"), "schema_version")
    if schema_version != RUN_PROFILE_SCHEMA_VERSION:
        raise RunProfileValidationError(
            f"schema_version must be {RUN_PROFILE_SCHEMA_VERSION}"
        )
    profile_id = _require_string(raw.get("profile_id"), "profile_id")
    dataset_version = _require_string(raw.get("dataset_version"), "dataset_version")
    seed = _load_seed(raw.get("seed"))
    generation = _load_generation(raw.get("generation"))
    features = _load_features(raw.get("features", {}))
    canonical = _canonical_profile_mapping(
        schema_version=schema_version,
        profile_id=profile_id,
        dataset_version=dataset_version,
        seed=seed,
        generation=generation,
        features=features,
    )
    return RunProfile(
        schema_version=schema_version,
        profile_id=profile_id,
        dataset_version=dataset_version,
        seed=seed,
        generation=generation,
        features=features,
        config_hash=_config_hash(canonical),
    )


def _load_seed(raw_seed: object) -> DomainSeed:
    seed = _require_mapping(raw_seed, "seed")
    taxonomy = seed.get("task_taxonomy")
    if not isinstance(taxonomy, list):
        raise RunProfileValidationError("seed.task_taxonomy must be a list")
    task_taxonomy = tuple(
        _require_string(value, f"seed.task_taxonomy.{index}")
        for index, value in enumerate(taxonomy)
    )
    if not task_taxonomy:
        raise RunProfileValidationError("seed.task_taxonomy must not be empty")
    return DomainSeed(
        seed_id=_require_string(seed.get("seed_id"), "seed.seed_id"),
        domain=_require_string(seed.get("domain"), "seed.domain"),
        description=_require_string(seed.get("description"), "seed.description"),
        task_taxonomy=task_taxonomy,
    )


def _load_generation(raw_generation: object) -> RunProfileGeneration:
    generation = _require_mapping(raw_generation, "generation")
    mode = _require_string(generation.get("mode"), "generation.mode")
    if mode not in GENERATION_MODES:
        raise RunProfileValidationError(
            f"generation.mode must be one of {sorted(GENERATION_MODES)}"
        )
    raw_count = generation.get("target_candidate_count")
    target_candidate_count = _optional_positive_int(
        raw_count,
        "generation.target_candidate_count",
    )
    if mode == "deterministic_scale_probe" and target_candidate_count is None:
        raise RunProfileValidationError(
            "generation.target_candidate_count is required for deterministic_scale_probe"
        )
    return RunProfileGeneration(
        mode=mode,
        target_candidate_count=target_candidate_count,
    )


def _load_features(raw_features: object) -> RunProfileFeatures:
    features = _require_mapping(raw_features, "features")
    unknown_keys = sorted(str(key) for key in features if key not in FEATURE_KEYS)
    if unknown_keys:
        raise RunProfileValidationError(
            f"unsupported feature keys: {', '.join(unknown_keys)}"
        )
    values: dict[str, bool] = {}
    for key in FEATURE_KEYS:
        value = features.get(key, False)
        if not isinstance(value, bool):
            raise RunProfileValidationError(f"features.{key} must be a bool")
        values[key] = value
    return RunProfileFeatures(**values)


def _canonical_profile_mapping(
    *,
    schema_version: str,
    profile_id: str,
    dataset_version: str,
    seed: DomainSeed,
    generation: RunProfileGeneration,
    features: RunProfileFeatures,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "profile_id": profile_id,
        "dataset_version": dataset_version,
        "seed": {
            "seed_id": seed.seed_id,
            "domain": seed.domain,
            "description": seed.description,
            "task_taxonomy": list(seed.task_taxonomy),
        },
        "generation": generation.canonical(),
        "features": features.canonical(),
    }


def _config_hash(canonical_profile: dict[str, object]) -> str:
    encoded = json.dumps(
        canonical_profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _require_mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunProfileValidationError(f"{field_name} must be an object")
    return value


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunProfileValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RunProfileValidationError(f"{field_name} must be a positive integer")
    return value
