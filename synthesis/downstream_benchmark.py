from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    validate_dataset_release_pack_record,
    validate_downstream_benchmark_bundle_record,
    validate_downstream_benchmark_observation_record,
    validate_downstream_benchmark_result_record,
)
from synthesis.release_pack import verify_dataset_release_pack


BUNDLE_SCHEMA_VERSION = "downstream_benchmark_bundle_v1"
OBSERVATION_SCHEMA_VERSION = "downstream_benchmark_observation_v1"
RESULT_SCHEMA_VERSION = "downstream_benchmark_result_v1"
RESULT_REASON_CODES = {
    "observation_unreadable_or_malformed",
    "benchmark_identity_mismatch",
    "release_identity_mismatch",
    "benchmark_suite_mismatch",
    "evaluation_identity_invalid",
    "metric_contract_invalid",
}


@dataclass(frozen=True)
class BenchmarkMetric:
    name: str
    direction: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class BenchmarkProtocol:
    protocol_version: str
    benchmark_suite_id: str
    benchmark_suite_version: str
    primary_metric: str
    metrics: tuple[BenchmarkMetric, ...]

    def export(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "benchmark_suite_id": self.benchmark_suite_id,
            "benchmark_suite_version": self.benchmark_suite_version,
            "baseline_arm": "baseline_without_synthetic_release",
            "treatment_arm": "treatment_with_exact_synthetic_release",
            "primary_metric": self.primary_metric,
            "metrics": [asdict(metric) for metric in self.metrics],
            "result_schema_version": RESULT_SCHEMA_VERSION,
        }


def build_downstream_benchmark_bundle(
    *, release_pack_path: Path, protocol: BenchmarkProtocol
) -> dict[str, object]:
    verification = verify_dataset_release_pack(release_pack_path)
    status = _mapping(_mapping(verification["verification"])).get("status")
    if status != "passed":
        raise ValueError("dataset release pack verification must pass")
    pack = _load_mapping(release_pack_path)
    validate_dataset_release_pack_record(pack)
    pack_bytes = release_pack_path.read_bytes()
    pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()
    protocol_record = protocol.export()
    identity = {
        "dataset_version": pack["dataset_version"],
        "release_id": pack["release_id"],
        "release_pack_sha256": pack_sha256,
        "protocol": protocol_record,
    }
    benchmark_id = "downstream_benchmark:sha256:" + hashlib.sha256(
        _canonical_json(identity)
    ).hexdigest()
    bundle: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "benchmark_id": benchmark_id,
        "dataset_version": str(pack["dataset_version"]),
        "release": {
            "release_id": str(pack["release_id"]),
            "pack_path": release_pack_path.name,
            "pack_sha256": pack_sha256,
            "pack_byte_count": len(pack_bytes),
        },
        "protocol": protocol_record,
        "claims": {
            "changes_release_admission": False,
            "proves_causality": False,
            "trains_inside_repository": False,
        },
    }
    validate_downstream_benchmark_bundle_record(bundle)
    return bundle


def write_downstream_benchmark_bundle(
    *, release_pack_path: Path, protocol: BenchmarkProtocol, output_path: Path
) -> Path:
    bundle = build_downstream_benchmark_bundle(
        release_pack_path=release_pack_path,
        protocol=protocol,
    )
    _write_json(output_path, bundle)
    return output_path


def build_downstream_benchmark_result(
    *, bundle: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, object]:
    validate_downstream_benchmark_bundle_record(bundle)
    reason = _observation_failure_reason(bundle, observation)
    if reason is not None:
        return _insufficient_result(bundle, reason)

    protocol = _mapping(bundle["protocol"])
    arms = _mapping(observation["arms"])
    baseline = _mapping(arms["baseline"])
    treatment = _mapping(arms["treatment"])
    baseline_metrics = _mapping(baseline["metrics"])
    treatment_metrics = _mapping(treatment["metrics"])
    primary_metric = str(protocol["primary_metric"])
    baseline_value = float(baseline_metrics[primary_metric])
    treatment_value = float(treatment_metrics[primary_metric])
    absolute_delta = treatment_value - baseline_value
    relative_delta = None if baseline_value == 0 else absolute_delta / baseline_value
    metric = next(
        _mapping(item)
        for item in protocol["metrics"]
        if _mapping(item)["name"] == primary_metric
    )
    direction = str(metric["direction"])
    improved = (
        treatment_value > baseline_value
        if direction == "higher_is_better"
        else treatment_value < baseline_value
    )
    if improved:
        status = "improved"
        reason_text = "treatment primary metric exceeds baseline primary metric"
        if direction == "lower_is_better":
            reason_text = "treatment primary metric is below baseline primary metric"
    else:
        status = "no_detected_improvement"
        reason_text = "treatment primary metric does not improve on baseline primary metric"
    result: dict[str, object] = {
        **{key: observation[key] for key in _observation_keys()},
        "schema_version": RESULT_SCHEMA_VERSION,
        "comparison": {
            "primary_metric": primary_metric,
            "absolute_delta": absolute_delta,
            "relative_delta": relative_delta,
        },
        "decision": {"status": status, "reasons": [reason_text]},
    }
    validate_downstream_benchmark_result_record(result)
    return result


def import_downstream_benchmark_result(
    *, bundle_path: Path, observation_path: Path, output_path: Path
) -> Path:
    bundle = _load_mapping(bundle_path)
    validate_downstream_benchmark_bundle_record(bundle)
    try:
        observation = _load_mapping(observation_path)
        result = build_downstream_benchmark_result(
            bundle=bundle,
            observation=observation,
        )
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError, TypeError):
        result = _insufficient_result(bundle, "observation_unreadable_or_malformed")
    _write_json(output_path, result)
    return output_path


def _observation_failure_reason(
    bundle: Mapping[str, Any], observation: Mapping[str, Any]
) -> str | None:
    expected_keys = _observation_keys()
    if set(observation) != expected_keys:
        return "observation_unreadable_or_malformed"
    if observation.get("benchmark_id") != bundle.get("benchmark_id"):
        return "benchmark_identity_mismatch"
    release = _mapping(bundle["release"])
    if (
        observation.get("dataset_version") != bundle.get("dataset_version")
        or observation.get("release_id") != release.get("release_id")
        or observation.get("release_pack_sha256") != release.get("pack_sha256")
    ):
        return "release_identity_mismatch"
    protocol = _mapping(bundle["protocol"])
    if (
        observation.get("benchmark_suite_id") != protocol.get("benchmark_suite_id")
        or observation.get("benchmark_suite_version") != protocol.get("benchmark_suite_version")
    ):
        return "benchmark_suite_mismatch"
    try:
        validate_downstream_benchmark_observation_record(observation)
    except ContractValidationError as exc:
        message = str(exc)
        if "evaluation_seed_ids" in message or "evaluation_sample_count" in message:
            return "evaluation_identity_invalid"
        if "arms" in message or "metrics" in message or "model_alias" in message:
            return "metric_contract_invalid"
        return "observation_unreadable_or_malformed"
    if not _metrics_match_protocol(protocol, observation):
        return "metric_contract_invalid"
    return None


def _metrics_match_protocol(
    protocol: Mapping[str, Any], observation: Mapping[str, Any]
) -> bool:
    metric_specs = {
        str(_mapping(raw)["name"]): _mapping(raw)
        for raw in protocol["metrics"]
    }
    arms = _mapping(observation["arms"])
    for arm_name in ("baseline", "treatment"):
        metrics = _mapping(_mapping(arms[arm_name])["metrics"])
        if set(metrics) != set(metric_specs):
            return False
        for name, raw_value in metrics.items():
            value = float(raw_value)
            spec = metric_specs[name]
            if (
                not math.isfinite(value)
                or value < float(spec["minimum"])
                or value > float(spec["maximum"])
            ):
                return False
    return True


def _insufficient_result(
    bundle: Mapping[str, Any], reason: str
) -> dict[str, object]:
    if reason not in RESULT_REASON_CODES:
        raise ValueError("unsupported result reason code")
    release = _mapping(bundle["release"])
    protocol = _mapping(bundle["protocol"])
    result: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "benchmark_id": str(bundle["benchmark_id"]),
        "dataset_version": str(bundle["dataset_version"]),
        "release_id": str(release["release_id"]),
        "release_pack_sha256": str(release["pack_sha256"]),
        "benchmark_suite_id": str(protocol["benchmark_suite_id"]),
        "benchmark_suite_version": str(protocol["benchmark_suite_version"]),
        "evaluation_seed_ids": [],
        "evaluation_sample_count": 0,
        "arms": None,
        "comparison": None,
        "decision": {
            "status": "insufficient_evidence",
            "reasons": [reason],
        },
    }
    validate_downstream_benchmark_result_record(result)
    return result


def _observation_keys() -> set[str]:
    return {
        "schema_version",
        "benchmark_id",
        "dataset_version",
        "release_id",
        "release_pack_sha256",
        "benchmark_suite_id",
        "benchmark_suite_version",
        "evaluation_seed_ids",
        "evaluation_sample_count",
        "arms",
    }


def _load_mapping(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping")
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
