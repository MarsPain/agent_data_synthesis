from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from synthesis.mutation_activation import (
    ACTIVATION_THRESHOLDS,
    validate_mutation_activation_report,
)
from synthesis.mutation_admission import canonical_hash
from synthesis.mutation_admission_config import (
    parse_mutation_admission_judge_configuration,
)
from synthesis.mutation_admission_release import verify_mutation_safe_manifest
from synthesis.scale_evidence import (
    CampaignRunInput,
    REQUIRED_DOMAINS,
    REQUIRED_ARTIFACTS as SCALE_REQUIRED_ARTIFACTS,
    build_representative_scale_evidence,
    load_scale_campaign,
)


REPRESENTATIVE_ACTIVATION_GATE_SCHEMA_VERSION = (
    "representative_mutation_activation_gate_v1"
)
REPRESENTATIVE_ACTIVATION_GATE_FILENAME = (
    "representative_mutation_activation_gate.json"
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class _PathGateEvidence:
    activation_report: dict[str, object]
    representative_evidence: dict[str, object]
    representative_lineage: dict[str, dict[str, object]]
    mutation_verifications: dict[str, object]
    protected_current_hash: str
    artifact_hashes: dict[str, str]


def build_representative_activation_gate(
    *,
    activation_report: Mapping[str, object],
    representative_evidence: Mapping[str, object],
    representative_lineage: Mapping[str, object],
    mutation_verifications: Mapping[str, object],
    protected_baseline_hash: str,
    protected_current_hash: str,
    artifact_hashes: Mapping[str, str],
    costs: Mapping[str, float],
    limitations: Sequence[str],
) -> dict[str, object]:
    """Build the final safety-first framework activation decision."""
    validate_mutation_activation_report(activation_report)
    domains = _representative_domains(representative_evidence)
    lineages = _representative_lineages(representative_lineage)
    verifications = _mutation_verifications(mutation_verifications)
    normalized_costs = _costs(costs)
    normalized_limitations = _limitations(limitations)
    normalized_artifacts = _artifact_hashes(artifact_hashes)
    _require_hash(protected_baseline_hash, "protected baseline hash")
    _require_hash(protected_current_hash, "protected current hash")

    activation_evidence = activation_report["evidence"]
    activation_operations = activation_report["operations"]
    assert isinstance(activation_evidence, Mapping)
    assert isinstance(activation_operations, Mapping)
    reasons = _gate_reasons(
        activation_decision=str(activation_report["decision"]),
        domains=domains,
        lineages=lineages,
        verifications=verifications,
        protected_baseline_hash=protected_baseline_hash,
        protected_current_hash=protected_current_hash,
    )
    decision = "activate" if not reasons else "no_go"
    failed_verifications = sum(
        verification["status"] != "passed"
        for verification in verifications.values()
    )
    activation_failures = activation_operations.get("failures")
    assert isinstance(activation_failures, int)
    report: dict[str, object] = {
        "schema_version": REPRESENTATIVE_ACTIVATION_GATE_SCHEMA_VERSION,
        "decision": decision,
        "decision_reasons": reasons,
        "readiness": {
            "framework_activation": (
                "activated" if decision == "activate" else "not_activated"
            ),
            "dataset_release": "not_established",
        },
        "activation": {
            "decision": activation_report["decision"],
            "decision_reasons": activation_report["decision_reasons"],
            "thresholds": activation_report["thresholds"],
            "metrics": activation_report["metrics"],
            "corpus": activation_evidence["corpus_summary"],
            "corpus_version": activation_evidence["corpus_version"],
            "corpus_hash": activation_evidence["corpus_hash"],
            "held_out_split_hash": activation_evidence[
                "held_out_split_hash"
            ],
            "repeated_input_hash": activation_evidence[
                "repeated_input_hash"
            ],
            "repeated_normalized_input_hash": activation_evidence[
                "repeated_normalized_input_hash"
            ],
            "evaluation_output_hash": activation_evidence[
                "evaluation_output_hash"
            ],
            "failures": activation_failures,
            "report_hash": activation_report["report_hash"],
        },
        "model_lineage": {
            "generator_model_hash": activation_evidence[
                "generator_model_hash"
            ],
            "judge_configuration": activation_evidence[
                "judge_configuration"
            ],
        },
        "representative": {
            "campaign_id": representative_evidence.get("campaign_id"),
            "domains": domains,
            "lineage": lineages,
        },
        "mutation_verifications": verifications,
        "protected_baseline": {
            "expected_hash": protected_baseline_hash,
            "current_hash": protected_current_hash,
            "unchanged": protected_baseline_hash == protected_current_hash,
        },
        "artifacts": normalized_artifacts,
        "operations": {
            "failures": activation_failures + failed_verifications,
            "costs_usd": {
                **normalized_costs,
                "total": round(sum(normalized_costs.values()), 6),
            },
        },
        "limitations": normalized_limitations,
    }
    report["report_hash"] = canonical_hash(report)
    validate_representative_activation_gate(report)
    return report


def build_representative_activation_gate_from_paths(
    *,
    activation_report_path: Path,
    campaign_path: Path,
    protected_campaign_path: Path,
    protected_baseline_hash: str,
    costs: Mapping[str, float],
    limitations: Sequence[str],
) -> dict[str, object]:
    evidence = _path_gate_evidence(
        activation_report_path=activation_report_path,
        campaign_path=campaign_path,
        protected_campaign_path=protected_campaign_path,
    )
    return build_representative_activation_gate(
        activation_report=evidence.activation_report,
        representative_evidence=evidence.representative_evidence,
        representative_lineage=evidence.representative_lineage,
        mutation_verifications=evidence.mutation_verifications,
        protected_baseline_hash=protected_baseline_hash,
        protected_current_hash=evidence.protected_current_hash,
        artifact_hashes=evidence.artifact_hashes,
        costs=costs,
        limitations=limitations,
    )


def write_representative_activation_gate(
    output_path: Path,
    report: Mapping[str, object],
) -> None:
    validate_representative_activation_gate(report)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_representative_activation_gate(
    *,
    report: Mapping[str, object],
    activation_report: Mapping[str, object],
    representative_evidence: Mapping[str, object],
    representative_lineage: Mapping[str, object],
    mutation_verifications: Mapping[str, object],
    protected_current_hash: str,
    artifact_hashes: Mapping[str, str],
) -> dict[str, object]:
    try:
        validate_representative_activation_gate(report)
        protected = _mapping(
            report.get("protected_baseline"),
            "protected baseline",
        )
        operations = _mapping(report.get("operations"), "operations")
        costs = _mapping(operations.get("costs_usd"), "costs")
        expected = build_representative_activation_gate(
            activation_report=activation_report,
            representative_evidence=representative_evidence,
            representative_lineage=representative_lineage,
            mutation_verifications=mutation_verifications,
            protected_baseline_hash=str(protected["expected_hash"]),
            protected_current_hash=protected_current_hash,
            artifact_hashes=artifact_hashes,
            costs={
                "activation_judge_usd": _as_float(
                    costs["activation_judge_usd"],
                    "activation judge cost",
                ),
                "representative_pipeline_usd": _as_float(
                    costs["representative_pipeline_usd"],
                    "representative pipeline cost",
                ),
            },
            limitations=_limitations(_sequence(report.get("limitations"))),
        )
        if report != expected:
            raise ValueError("representative activation evidence changed")
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return {
            "status": "failed",
            "reasons": [
                "representative activation evidence is invalid or changed: "
                f"{type(exc).__name__}"
            ],
        }
    return {
        "status": "passed",
        "reasons": [
            "activation, representative, mutation, and protected-baseline "
            "evidence match recorded hashes"
        ],
    }


def verify_representative_activation_gate_from_paths(
    *,
    report_path: Path,
    activation_report_path: Path,
    campaign_path: Path,
    protected_campaign_path: Path,
) -> dict[str, object]:
    try:
        report = _load_json_mapping(report_path)
        evidence = _path_gate_evidence(
            activation_report_path=activation_report_path,
            campaign_path=campaign_path,
            protected_campaign_path=protected_campaign_path,
        )
        return verify_representative_activation_gate(
            report=report,
            activation_report=evidence.activation_report,
            representative_evidence=evidence.representative_evidence,
            representative_lineage=evidence.representative_lineage,
            mutation_verifications=evidence.mutation_verifications,
            protected_current_hash=evidence.protected_current_hash,
            artifact_hashes=evidence.artifact_hashes,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return {
            "status": "failed",
            "reasons": [
                "representative activation evidence is invalid or changed: "
                f"{type(exc).__name__}"
            ],
        }


def hash_artifact_tree(root: Path) -> str:
    if not root.is_dir():
        raise ValueError("protected campaign directory is missing")
    digest = hashlib.sha256()
    entries = sorted(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("protected campaign directory contains a symlink")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError("protected campaign directory is empty")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def _path_gate_evidence(
    *,
    activation_report_path: Path,
    campaign_path: Path,
    protected_campaign_path: Path,
) -> _PathGateEvidence:
    activation_report = _load_json_mapping(activation_report_path)
    campaign = load_scale_campaign(campaign_path)
    protected_root = protected_campaign_path.resolve()
    if campaign_path.resolve().is_relative_to(protected_root):
        raise ValueError("representative campaign must be fresh")
    if any(
        run.artifact_dir.resolve().is_relative_to(protected_root)
        for run in campaign.runs
    ):
        raise ValueError(
            "representative artifacts must not modify protected baseline"
        )
    return _PathGateEvidence(
        activation_report=activation_report,
        representative_evidence=build_representative_scale_evidence(
            campaign
        ),
        representative_lineage=_representative_lineage_from_paths(
            campaign.runs
        ),
        mutation_verifications={
            run.domain_id: verify_mutation_safe_manifest(
                run.artifact_dir / "manifest.json"
            )
            for run in campaign.runs
        },
        protected_current_hash=hash_artifact_tree(
            protected_campaign_path
        ),
        artifact_hashes={
            "activation_report": _file_hash(activation_report_path),
            "campaign": _file_hash(campaign_path),
            **{
                f"{run.domain_id}_manifest": _file_hash(
                    run.artifact_dir / "manifest.json"
                )
                for run in campaign.runs
            },
        },
    )


def validate_representative_activation_gate(raw: object) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("representative activation gate must be an object")
    if set(raw) != {
        "schema_version",
        "decision",
        "decision_reasons",
        "readiness",
        "activation",
        "model_lineage",
        "representative",
        "mutation_verifications",
        "protected_baseline",
        "artifacts",
        "operations",
        "limitations",
        "report_hash",
    }:
        raise ValueError("representative activation gate keys are invalid")
    if raw.get("schema_version") != REPRESENTATIVE_ACTIVATION_GATE_SCHEMA_VERSION:
        raise ValueError("representative activation gate schema is unsupported")
    expected_hash = canonical_hash(
        {key: value for key, value in raw.items() if key != "report_hash"}
    )
    if raw.get("report_hash") != expected_hash:
        raise ValueError("representative activation gate hash mismatch")
    activation = _mapping(raw.get("activation"), "activation")
    if activation.get("thresholds") != ACTIVATION_THRESHOLDS:
        raise ValueError("representative activation thresholds changed")
    for key in (
        "corpus_hash",
        "held_out_split_hash",
        "repeated_input_hash",
        "repeated_normalized_input_hash",
        "evaluation_output_hash",
        "report_hash",
    ):
        _require_hash(activation.get(key), f"activation {key}")
    activation_failures = activation.get("failures")
    if (
        not isinstance(activation_failures, int)
        or isinstance(activation_failures, bool)
        or activation_failures < 0
    ):
        raise ValueError("activation failure count is invalid")
    lineage = _mapping(raw.get("model_lineage"), "model_lineage")
    parse_mutation_admission_judge_configuration(
        lineage.get("judge_configuration")
    )
    _require_hash(lineage.get("generator_model_hash"), "generator model hash")
    representative = _mapping(raw.get("representative"), "representative")
    campaign_id = representative.get("campaign_id")
    if (
        not isinstance(campaign_id, str)
        or re.fullmatch(r"scale_campaign:sha256:[0-9a-f]{64}", campaign_id)
        is None
    ):
        raise ValueError("representative campaign id is invalid")
    domains = _normalized_representative_domains(
        representative.get("domains")
    )
    lineages = _representative_lineages(
        _mapping(representative.get("lineage"), "representative lineage")
    )
    verifications = _mutation_verifications(
        _mapping(raw.get("mutation_verifications"), "mutation verifications")
    )
    protected = _mapping(raw.get("protected_baseline"), "protected baseline")
    expected_protected = protected.get("expected_hash")
    current_protected = protected.get("current_hash")
    _require_hash(expected_protected, "protected baseline expected hash")
    _require_hash(current_protected, "protected baseline current hash")
    if protected.get("unchanged") != (expected_protected == current_protected):
        raise ValueError("protected baseline status is inconsistent")
    artifacts = _mapping(raw.get("artifacts"), "artifacts")
    _artifact_hashes({str(key): str(value) for key, value in artifacts.items()})
    limitations = raw.get("limitations")
    _limitations(limitations if isinstance(limitations, Sequence) else ())
    operations = _mapping(raw.get("operations"), "operations")
    failed_verifications = sum(
        verification["status"] != "passed"
        for verification in verifications.values()
    )
    if operations.get("failures") != activation_failures + failed_verifications:
        raise ValueError("representative activation failures are inconsistent")
    costs = _mapping(operations.get("costs_usd"), "costs")
    cost_parts = {key: value for key, value in costs.items() if key != "total"}
    normalized_costs = _costs(cost_parts)
    if costs.get("total") != round(sum(normalized_costs.values()), 6):
        raise ValueError("representative activation costs are inconsistent")
    activation_decision = activation.get("decision")
    reasons = _gate_reasons(
        activation_decision=str(activation_decision),
        domains=domains,
        lineages=lineages,
        verifications=verifications,
        protected_baseline_hash=str(expected_protected),
        protected_current_hash=str(current_protected),
    )
    decision = "activate" if not reasons else "no_go"
    if raw.get("decision") != decision or raw.get("decision_reasons") != reasons:
        raise ValueError("representative activation decision is inconsistent")
    expected_readiness = {
        "framework_activation": (
            "activated" if decision == "activate" else "not_activated"
        ),
        "dataset_release": "not_established",
    }
    if raw.get("readiness") != expected_readiness:
        raise ValueError("representative activation readiness is inconsistent")


def _gate_reasons(
    *,
    activation_decision: str,
    domains: list[dict[str, object]],
    lineages: dict[str, dict[str, object]],
    verifications: dict[str, dict[str, object]],
    protected_baseline_hash: str,
    protected_current_hash: str,
) -> list[str]:
    reasons: list[str] = []
    if activation_decision != "activate":
        reasons.append("activation_evaluation_no_go")
    if any(
        domain["classification"] != "representative"
        or domain["heldout_status"] != "passed"
        or domain["quality_status"] != "passed"
        for domain in domains
    ):
        reasons.append("representative_quality_evidence_failed")
    if any(domain["dataset_release_status"] == "passed" for domain in domains):
        reasons.append("representative_release_readiness_claim_present")
    if any(
        lineage["model_independence"] != "independent"
        for lineage in lineages.values()
    ):
        reasons.append("representative_model_independence_failed")
    if any(item["status"] != "passed" for item in verifications.values()):
        reasons.append("representative_mutation_verification_failed")
    if protected_baseline_hash != protected_current_hash:
        reasons.append("protected_baseline_changed")
    return reasons


def _representative_domains(
    evidence: Mapping[str, object],
) -> list[dict[str, object]]:
    if evidence.get("schema_version") != "representative_scale_evidence_v1":
        raise ValueError("representative scale evidence schema is unsupported")
    raw_domains = evidence.get("domains")
    if not isinstance(raw_domains, list):
        raise ValueError("representative scale domains are invalid")
    domains: list[dict[str, object]] = []
    for raw in raw_domains:
        if not isinstance(raw, Mapping):
            raise ValueError("representative scale domain is invalid")
        observed = raw.get("observed")
        if not isinstance(observed, Mapping):
            raise ValueError("representative scale observations are invalid")
        domains.append(
            {
                "domain_id": str(raw.get("domain_id")),
                "classification": str(raw.get("classification")),
                "heldout_status": str(observed.get("heldout_status")),
                "quality_status": str(
                    observed.get("mvp_quality_floor_status")
                ),
                "dataset_release_status": str(
                    observed.get("dataset_release_status")
                ),
                "report_hashes": _scale_report_hashes(
                    raw.get("artifacts")
                ),
            }
        )
    if {domain["domain_id"] for domain in domains} != set(REQUIRED_DOMAINS):
        raise ValueError("representative scale domain coverage is incomplete")
    return sorted(domains, key=lambda item: str(item["domain_id"]))


def _normalized_representative_domains(
    raw_domains: object,
) -> list[dict[str, object]]:
    if not isinstance(raw_domains, list):
        raise ValueError("representative scale domains are invalid")
    domains: list[dict[str, object]] = []
    required_keys = {
        "domain_id",
        "classification",
        "heldout_status",
        "quality_status",
        "dataset_release_status",
        "report_hashes",
    }
    for raw in raw_domains:
        if not isinstance(raw, Mapping) or set(raw) != required_keys:
            raise ValueError("normalized representative domain is invalid")
        domains.append(
            {
                "domain_id": str(raw["domain_id"]),
                "classification": str(raw["classification"]),
                "heldout_status": str(raw["heldout_status"]),
                "quality_status": str(raw["quality_status"]),
                "dataset_release_status": str(
                    raw["dataset_release_status"]
                ),
                "report_hashes": _scale_report_hashes(
                    raw["report_hashes"]
                ),
            }
        )
    if {domain["domain_id"] for domain in domains} != set(REQUIRED_DOMAINS):
        raise ValueError("representative scale domain coverage is incomplete")
    return sorted(domains, key=lambda item: str(item["domain_id"]))


def _representative_lineage_from_paths(
    runs: Sequence[CampaignRunInput],
) -> dict[str, dict[str, object]]:
    lineage: dict[str, dict[str, object]] = {}
    for run in runs:
        manifest = _load_json_mapping(run.artifact_dir / "manifest.json")
        profile = _mapping(manifest.get("run_profile"), "run profile")
        admission = _mapping(
            profile.get("mutation_admission"),
            "mutation admission profile",
        )
        judge = parse_mutation_admission_judge_configuration(
            admission.get("judge")
        )
        generator_models = _generator_models(run.artifact_dir)
        generator_model_hash = (
            canonical_hash(next(iter(generator_models)))
            if len(generator_models) == 1
            else None
        )
        judge_model_hash = canonical_hash(judge.model)
        lineage[run.domain_id] = {
            "profile_id": profile.get("profile_id"),
            "dataset_version": manifest.get("dataset_version"),
            "profile_config_hash": profile.get("config_hash"),
            "generator_model_hash": generator_model_hash,
            "judge_model_hash": judge_model_hash,
            "judge_configuration_hash": canonical_hash(judge.canonical()),
            "model_independence": (
                "unknown"
                if generator_model_hash is None
                else "same_model"
                if generator_model_hash == judge_model_hash
                else "independent"
            ),
        }
    return _representative_lineages(lineage)


def _representative_lineages(
    raw: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if set(raw) != set(REQUIRED_DOMAINS):
        raise ValueError("representative lineage domain coverage is incomplete")
    normalized: dict[str, dict[str, object]] = {}
    required_keys = {
        "profile_id",
        "dataset_version",
        "profile_config_hash",
        "generator_model_hash",
        "judge_model_hash",
        "judge_configuration_hash",
        "model_independence",
    }
    for domain in sorted(REQUIRED_DOMAINS):
        item = _mapping(raw[domain], f"{domain} lineage")
        if set(item) != required_keys:
            raise ValueError("representative lineage keys are invalid")
        for key in ("profile_id", "dataset_version"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError("representative lineage identity is invalid")
        for key in (
            "profile_config_hash",
            "judge_model_hash",
            "judge_configuration_hash",
        ):
            _require_hash(item.get(key), f"representative lineage {key}")
        generator_hash = item.get("generator_model_hash")
        if generator_hash is not None:
            _require_hash(
                generator_hash,
                "representative lineage generator model hash",
            )
        judge_hash = item["judge_model_hash"]
        expected_independence = (
            "unknown"
            if generator_hash is None
            else "same_model"
            if generator_hash == judge_hash
            else "independent"
        )
        if item.get("model_independence") != expected_independence:
            raise ValueError("representative model independence is inconsistent")
        normalized[domain] = dict(item)
    return normalized


def _generator_models(artifact_dir: Path) -> set[str]:
    models: set[str] = set()
    for path, record_kind in (
        (artifact_dir / "samples.jsonl", "sample"),
        (artifact_dir / "rejections.jsonl", "rejection"),
    ):
        for record in _load_jsonl(path):
            if record_kind == "sample":
                lineage = record.get("lineage")
                generator = (
                    lineage.get("generator")
                    if isinstance(lineage, Mapping)
                    else None
                )
            else:
                details = record.get("details")
                role_lineages = (
                    details.get("role_lineages")
                    if isinstance(details, Mapping)
                    else None
                )
                generator = (
                    role_lineages.get("generator")
                    if isinstance(role_lineages, Mapping)
                    else None
                )
            model = (
                generator.get("model")
                if isinstance(generator, Mapping)
                else None
            )
            if isinstance(model, str) and model:
                models.add(model)
    return models


def _mutation_verifications(
    raw: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if set(raw) != set(REQUIRED_DOMAINS):
        raise ValueError("mutation verification domain coverage is incomplete")
    normalized: dict[str, dict[str, object]] = {}
    for domain in sorted(REQUIRED_DOMAINS):
        verification = _mapping(raw.get(domain), f"{domain} verification")
        status = verification.get("status")
        reasons = verification.get("reasons")
        if status not in {"passed", "failed"} or not isinstance(reasons, list):
            raise ValueError("mutation verification is invalid")
        normalized[domain] = {
            "status": status,
            "reasons": [str(reason) for reason in reasons],
        }
    return normalized


def _costs(raw: Mapping[str, object]) -> dict[str, float]:
    required = {"activation_judge_usd", "representative_pipeline_usd"}
    if set(raw) != required:
        raise ValueError("representative activation costs are invalid")
    normalized: dict[str, float] = {}
    for key in sorted(required):
        value = raw[key]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError("representative activation cost is invalid")
        normalized[key] = float(value)
    return normalized


def _limitations(raw: Sequence[object]) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("representative activation limitations must be a list")
    limitations = [str(value) for value in raw]
    if not limitations or any(not value.strip() for value in limitations):
        raise ValueError("representative activation limitations are required")
    return limitations


def _artifact_hashes(raw: Mapping[str, str]) -> dict[str, str]:
    required = {
        "activation_report",
        "campaign",
        *(f"{domain}_manifest" for domain in REQUIRED_DOMAINS),
    }
    if set(raw) != required:
        raise ValueError("representative activation artifact hashes are incomplete")
    normalized = dict(sorted(raw.items()))
    for key, value in normalized.items():
        _require_hash(value, f"{key} hash")
    return normalized


def _require_hash(raw: object, path: str) -> None:
    if not isinstance(raw, str) or _SHA256_RE.fullmatch(raw) is None:
        raise ValueError(f"{path} is invalid")


def _scale_report_hashes(raw: object) -> dict[str, str]:
    artifacts = _mapping(raw, "representative domain artifacts")
    if set(artifacts) != set(SCALE_REQUIRED_ARTIFACTS):
        raise ValueError("representative report hashes are incomplete")
    hashes: dict[str, str] = {}
    for key in sorted(SCALE_REQUIRED_ARTIFACTS):
        raw_artifact = artifacts[key]
        value = (
            raw_artifact
            if isinstance(raw_artifact, str)
            else _mapping(raw_artifact, f"{key} artifact").get("sha256")
        )
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("representative report hash is invalid")
        hashes[key] = value
    return hashes


def _mapping(raw: object, path: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be an object")
    return raw


def _load_json_mapping(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path.name} must contain an object")
    return dict(raw)


def _load_jsonl(path: Path) -> list[Mapping[str, object]]:
    records: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path.name} contains a non-object record")
        records.append(raw)
    return records


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _as_float(raw: object, path: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{path} is invalid")
    return float(raw)


def _sequence(raw: object) -> Sequence[object]:
    if not isinstance(raw, list):
        raise ValueError("limitations must be a list")
    return raw
