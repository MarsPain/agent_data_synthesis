from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthesis.contracts import SOURCE_LICENSE_LABELS
from synthesis.llm import LLMConfig
from synthesis.mutation_admission_config import (
    MutationAdmissionJudgeConfiguration,
    parse_mutation_admission_judge_configuration,
)
from synthesis.profile_contracts import (
    REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS,
)
from synthesis.seeds import DomainSeed


RUN_PROFILE_SCHEMA_VERSION = "run_profile_v1"
RUN_PROFILE_SCHEMA_VERSIONS = {
    "run_profile_v1",
    "run_profile_v2",
    "run_profile_v3",
    "run_profile_v4",
}
GENERATION_CONTEXT_POLICIES = {"synthetic_fixture"}
GENERATION_MODES = {
    "foundation_fixture",
    "deterministic_scale_probe",
    "mobile_fixture",
    "workspace_fixture",
    "llm",
}
PROFILE_PURPOSES = {"diagnostic_probe", "release_candidate", "benchmark"}
SOURCE_KINDS = {
    "local_contacts_json",
    "local_mobile_messages_json",
    "local_workspace_tasks_json",
}
SOURCE_KEYS = {"kind", "source_id", "path", "license_label", "max_bytes"}
DEFAULT_SOURCE_MAX_BYTES = 65536
MUTATION_ADMISSION_MODES = {"disabled", "shadow", "enforce"}
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
    context_policy: str | None = None

    def canonical(self) -> dict[str, object]:
        canonical: dict[str, object] = {
            "mode": self.mode,
            "target_candidate_count": self.target_candidate_count,
        }
        if self.context_policy is not None:
            canonical["context_policy"] = self.context_policy
        return canonical


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
class RunProfileSource:
    kind: str
    source_id: str
    relative_path: str
    resolved_path: Path
    license_label: str
    max_bytes: int

    def canonical(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source_id": self.source_id,
            "path": self.relative_path,
            "license_label": self.license_label,
            "max_bytes": self.max_bytes,
        }


@dataclass(frozen=True)
class RunProfileMutationAdmission:
    mode: str = "disabled"
    judge: MutationAdmissionJudgeConfiguration | None = None

    def canonical(self) -> dict[str, object]:
        canonical: dict[str, object] = {"mode": self.mode}
        if self.judge is not None:
            canonical["judge"] = self.judge.canonical()
        return canonical


@dataclass(frozen=True)
class RunProfile:
    schema_version: str
    profile_id: str
    dataset_version: str
    profile_purpose: str
    seed: DomainSeed
    generation: RunProfileGeneration
    features: RunProfileFeatures
    config_hash: str
    source: RunProfileSource | None = None
    mutation_admission: RunProfileMutationAdmission = RunProfileMutationAdmission()

    def sanitized_metadata(
        self,
        *,
        source_summary: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "generation_mode": self.generation.mode,
            "profile_purpose": self.profile_purpose,
            "target_candidate_count": self.generation.target_candidate_count,
            "config_hash": self.config_hash,
            "enabled_features": self.features.enabled_feature_names(),
            "seed": {"domain": self.seed.domain},
        }
        if source_summary is not None:
            metadata["source"] = dict(source_summary)
        if self.schema_version == "run_profile_v4":
            metadata["mutation_admission"] = self.mutation_admission.canonical()
        return metadata

    def canonical(self) -> dict[str, object]:
        return _canonical_profile_mapping(
            schema_version=self.schema_version,
            profile_id=self.profile_id,
            dataset_version=self.dataset_version,
            profile_purpose=self.profile_purpose,
            seed=self.seed,
            generation=self.generation,
            features=self.features,
            source=self.source,
            mutation_admission=self.mutation_admission,
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
    if schema_version not in RUN_PROFILE_SCHEMA_VERSIONS:
        raise RunProfileValidationError(
            f"schema_version must be one of {sorted(RUN_PROFILE_SCHEMA_VERSIONS)}"
        )
    profile_id = _require_string(raw.get("profile_id"), "profile_id")
    dataset_version = _require_string(raw.get("dataset_version"), "dataset_version")
    seed = _load_seed(raw.get("seed"))
    generation = _load_generation(raw.get("generation"), schema_version=schema_version)
    profile_purpose = _load_profile_purpose(
        raw.get("profile_purpose"),
        generation_mode=generation.mode,
    )
    features = _load_features(raw.get("features", {}))
    source = _load_source(raw.get("source"), schema_version=schema_version, profile_path=path)
    mutation_admission = _load_mutation_admission(
        raw.get("mutation_admission"),
        schema_version=schema_version,
    )
    _validate_mutation_admission_compatibility(
        schema_version=schema_version,
        profile_purpose=profile_purpose,
        generation=generation,
        mutation_admission=mutation_admission,
    )
    _validate_generation_compatibility(
        schema_version=schema_version,
        profile_purpose=profile_purpose,
        generation=generation,
        source=source,
    )
    _validate_source_domain_compatibility(seed, source)
    canonical = _canonical_profile_mapping(
        schema_version=schema_version,
        profile_id=profile_id,
        dataset_version=dataset_version,
        profile_purpose=profile_purpose,
        seed=seed,
        generation=generation,
        features=features,
        source=source,
        mutation_admission=mutation_admission,
    )
    return RunProfile(
        schema_version=schema_version,
        profile_id=profile_id,
        dataset_version=dataset_version,
        profile_purpose=profile_purpose,
        seed=seed,
        generation=generation,
        features=features,
        config_hash=_config_hash(canonical),
        source=source,
        mutation_admission=mutation_admission,
    )


def _load_mutation_admission(
    raw_mutation_admission: object,
    *,
    schema_version: str,
) -> RunProfileMutationAdmission:
    if schema_version != "run_profile_v4":
        if raw_mutation_admission is not None:
            raise RunProfileValidationError(
                "mutation_admission is only supported for run_profile_v4"
            )
        return RunProfileMutationAdmission()
    if raw_mutation_admission is None:
        raise RunProfileValidationError(
            "mutation_admission is required for run_profile_v4"
        )
    mutation_admission = _require_mapping(
        raw_mutation_admission,
        "mutation_admission",
    )
    unknown_keys = sorted(
        str(key) for key in mutation_admission if key not in {"mode", "judge"}
    )
    if unknown_keys:
        raise RunProfileValidationError(
            f"unsupported mutation_admission keys: {', '.join(unknown_keys)}"
        )
    mode = _require_string(mutation_admission.get("mode"), "mutation_admission.mode")
    if mode not in MUTATION_ADMISSION_MODES:
        raise RunProfileValidationError(
            f"mutation_admission.mode must be one of {sorted(MUTATION_ADMISSION_MODES)}"
        )
    raw_judge = mutation_admission.get("judge")
    if raw_judge is not None and mode not in {"shadow", "enforce"}:
        raise RunProfileValidationError(
            "mutation_admission.judge is only supported in shadow or enforce mode"
        )
    if mode == "enforce" and raw_judge is None:
        raise RunProfileValidationError(
            "mutation_admission.judge is required in enforce mode"
        )
    judge = _load_mutation_judge(raw_judge) if raw_judge is not None else None
    return RunProfileMutationAdmission(mode=mode, judge=judge)


def _load_mutation_judge(raw_judge: object) -> MutationAdmissionJudgeConfiguration:
    try:
        return parse_mutation_admission_judge_configuration(raw_judge)
    except ValueError as exc:
        raise RunProfileValidationError(
            f"mutation_admission.judge {exc}"
        ) from exc


def _validate_mutation_admission_compatibility(
    *,
    schema_version: str,
    profile_purpose: str,
    generation: RunProfileGeneration,
    mutation_admission: RunProfileMutationAdmission,
) -> None:
    if schema_version != "run_profile_v4":
        return
    if (
        profile_purpose == "release_candidate"
        and mutation_admission.mode != "enforce"
    ):
        raise RunProfileValidationError(
            "run_profile_v4 release_candidate profiles require enforce mode"
        )
    if mutation_admission.mode != "enforce":
        return
    judge = mutation_admission.judge
    if judge is None:
        raise RunProfileValidationError(
            "mutation_admission.judge is required in enforce mode"
        )
    generator_model = (
        "scripted_scale_probe"
        if generation.mode == "deterministic_scale_probe"
        else "scripted"
        if generation.mode
        in {
            "foundation_fixture",
            "mobile_fixture",
            "workspace_fixture",
        }
        else LLMConfig.from_env().model
        if generation.mode == "llm"
        else None
    )
    if not isinstance(generator_model, str) or not generator_model:
        raise RunProfileValidationError(
            "enforce mode requires an explicit generator model"
        )
    if judge.model == generator_model:
        raise RunProfileValidationError(
            "enforce mode requires different generator and judge models"
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


def _load_generation(
    raw_generation: object,
    *,
    schema_version: str,
) -> RunProfileGeneration:
    generation = _require_mapping(raw_generation, "generation")
    if schema_version in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS:
        unknown_keys = sorted(
            str(key)
            for key in generation
            if key not in {"mode", "target_candidate_count", "context_policy"}
        )
        if unknown_keys:
            raise RunProfileValidationError(
                f"unsupported generation keys: {', '.join(unknown_keys)}"
            )
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
    context_policy = (
        generation.get("context_policy")
        if schema_version in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS
        else None
    )
    if context_policy is not None:
        context_policy = _require_string(context_policy, "generation.context_policy")
    return RunProfileGeneration(
        mode=mode,
        target_candidate_count=target_candidate_count,
        context_policy=context_policy,
    )


def _validate_generation_compatibility(
    *,
    schema_version: str,
    profile_purpose: str,
    generation: RunProfileGeneration,
    source: RunProfileSource | None,
) -> None:
    if schema_version not in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS:
        return
    if schema_version == "run_profile_v4" and profile_purpose != "benchmark":
        if generation.context_policy is not None:
            raise RunProfileValidationError(
                "generation.context_policy requires benchmark purpose"
            )
        return
    if generation.mode != "llm":
        if generation.context_policy is not None:
            raise RunProfileValidationError(
                "generation.context_policy is only supported for representative llm generation"
            )
        return
    if generation.target_candidate_count is None:
        raise RunProfileValidationError(
            "generation.target_candidate_count is required for representative llm generation"
        )
    if generation.context_policy not in GENERATION_CONTEXT_POLICIES:
        raise RunProfileValidationError(
            "generation.context_policy must be synthetic_fixture for representative llm generation"
        )
    if profile_purpose != "benchmark":
        raise RunProfileValidationError(
            "profile_purpose must be benchmark for representative llm generation"
        )
    if source is not None:
        raise RunProfileValidationError(
            "source is not supported for representative llm generation"
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


def _load_profile_purpose(value: object, *, generation_mode: str) -> str:
    if value is None:
        return _default_profile_purpose(generation_mode)
    purpose = _require_string(value, "profile_purpose")
    if purpose not in PROFILE_PURPOSES:
        raise RunProfileValidationError(
            f"profile_purpose must be one of {sorted(PROFILE_PURPOSES)}"
        )
    return purpose


def _default_profile_purpose(generation_mode: str) -> str:
    if generation_mode in {
        "deterministic_scale_probe",
        "mobile_fixture",
        "workspace_fixture",
    }:
        return "diagnostic_probe"
    return "release_candidate"


def _load_source(
    raw_source: object,
    *,
    schema_version: str,
    profile_path: Path,
) -> RunProfileSource | None:
    if schema_version != "run_profile_v2":
        if raw_source is not None:
            raise RunProfileValidationError("source is only supported for run_profile_v2")
        return None
    if raw_source is None:
        return None

    source = _require_mapping(raw_source, "source")
    unknown_keys = sorted(str(key) for key in source if key not in SOURCE_KEYS)
    if unknown_keys:
        raise RunProfileValidationError(
            f"unsupported source keys: {', '.join(unknown_keys)}"
        )
    kind = _require_string(source.get("kind"), "source.kind")
    if kind not in SOURCE_KINDS:
        raise RunProfileValidationError(
            f"source.kind must be one of {sorted(SOURCE_KINDS)}"
        )
    source_id = _require_string(source.get("source_id"), "source.source_id")
    relative_path = _require_string(source.get("path"), "source.path")
    source_path = Path(relative_path)
    if source_path.is_absolute():
        raise RunProfileValidationError("source.path must be relative")
    if ".." in source_path.parts:
        raise RunProfileValidationError("source.path must not contain parent traversal")
    if source_path.suffix != ".json":
        raise RunProfileValidationError("source.path must have a .json suffix")
    license_label = _require_string(source.get("license_label"), "source.license_label")
    if license_label not in SOURCE_LICENSE_LABELS:
        raise RunProfileValidationError(
            f"source.license_label must be one of {sorted(SOURCE_LICENSE_LABELS)}"
        )
    max_bytes = _optional_positive_int(
        source.get("max_bytes", DEFAULT_SOURCE_MAX_BYTES),
        "source.max_bytes",
    )
    assert max_bytes is not None
    return RunProfileSource(
        kind=kind,
        source_id=source_id,
        relative_path=relative_path,
        resolved_path=profile_path.parent / source_path,
        license_label=license_label,
        max_bytes=max_bytes,
    )


def _validate_source_domain_compatibility(
    seed: DomainSeed,
    source: RunProfileSource | None,
) -> None:
    if source is None:
        return
    normalized_domain = (
        "contacts_fixture"
        if seed.domain in {"contacts", "contacts_fixture"}
        else seed.domain
    )
    allowed = {
        "contacts_fixture": {"local_contacts_json"},
        "mobile_messages_fixture": {"local_mobile_messages_json"},
        "workspace_tasks_fixture": {"local_workspace_tasks_json"},
    }
    if source.kind not in allowed.get(normalized_domain, set()):
        raise RunProfileValidationError(
            f"source.kind {source.kind!r} is not supported for seed.domain {seed.domain!r}"
        )


def _canonical_profile_mapping(
    *,
    schema_version: str,
    profile_id: str,
    dataset_version: str,
    profile_purpose: str,
    seed: DomainSeed,
    generation: RunProfileGeneration,
    features: RunProfileFeatures,
    source: RunProfileSource | None = None,
    mutation_admission: RunProfileMutationAdmission = RunProfileMutationAdmission(),
) -> dict[str, object]:
    canonical: dict[str, object] = {
        "schema_version": schema_version,
        "profile_id": profile_id,
        "dataset_version": dataset_version,
        "profile_purpose": profile_purpose,
        "seed": {
            "seed_id": seed.seed_id,
            "domain": seed.domain,
            "description": seed.description,
            "task_taxonomy": list(seed.task_taxonomy),
        },
        "generation": generation.canonical(),
        "features": features.canonical(),
    }
    if source is not None:
        canonical["source"] = source.canonical()
    if schema_version == "run_profile_v4":
        canonical["mutation_admission"] = mutation_admission.canonical()
    return canonical


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
