from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    validate_coverage_quality_summary_record,
    validate_dataset_release_report_record,
    validate_generation_contract_record,
    validate_evaluation_report_record,
    validate_manifest_record,
    validate_profile_decision_report_record,
    validate_release_quality_audit_record,
    validate_representative_scale_campaign_record,
    validate_representative_scale_evidence_record,
    validate_review_resolution_report_record,
)
from synthesis.coverage_evidence import (
    coverage_quality_summary,
    verify_sanitized_coverage_evidence,
)
from synthesis.mutation_admission_config import (
    parse_mutation_admission_judge_configuration,
)
from synthesis.profile_contracts import (
    REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS,
)


SCALE_CAMPAIGN_SCHEMA_VERSION = "representative_scale_campaign_v1"
SCALE_EVIDENCE_SCHEMA_VERSION = "representative_scale_evidence_v1"
REQUIRED_DOMAINS = (
    "contacts_fixture",
    "mobile_messages_fixture",
    "workspace_tasks_fixture",
)
DIAGNOSTIC_GENERATION_MODES = {
    "foundation_fixture",
    "deterministic_scale_probe",
    "mobile_fixture",
    "workspace_fixture",
}
REPRESENTATIVE_GENERATION_MODES = {"llm"}
REQUIRED_ARTIFACTS = {
    "manifest": "manifest.json",
    "quality_report": "quality_report.json",
    "evaluation_report": "evaluation_report.json",
    "profile_decision_report": "profile_decision_report.json",
    "dataset_release_report": "dataset_release_report.json",
    "release_quality_audit": "release_quality_audit.json",
}
OPTIONAL_REVIEW_ARTIFACT = "review_resolution_report.json"


@dataclass(frozen=True)
class CampaignRunInput:
    domain_id: str
    artifact_dir: Path


@dataclass(frozen=True)
class ScaleCampaignInput:
    campaign_label: str
    runs: tuple[CampaignRunInput, ...]


def load_scale_campaign(path: Path) -> ScaleCampaignInput:
    record = json.loads(path.read_text(encoding="utf-8"))
    validate_representative_scale_campaign_record(record)
    base_dir = path.parent
    runs = tuple(
        CampaignRunInput(
            domain_id=str(run["domain_id"]),
            artifact_dir=base_dir / str(run["artifact_dir"]),
        )
        for run in record["runs"]
    )
    by_domain = {run.domain_id: run for run in runs}
    return ScaleCampaignInput(
        campaign_label=str(record["campaign_label"]),
        runs=tuple(by_domain[domain] for domain in REQUIRED_DOMAINS),
    )


def classify_run(artifacts: Mapping[str, Any]) -> str:
    if artifacts.get("valid") is not True:
        return "insufficient_evidence"
    generation_mode = artifacts.get("generation_mode")
    if generation_mode in DIAGNOSTIC_GENERATION_MODES:
        return "diagnostic_only"
    if generation_mode in REPRESENTATIVE_GENERATION_MODES:
        schema_version = artifacts.get("schema_version")
        if schema_version not in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS:
            return "insufficient_evidence"
        if schema_version == "run_profile_v4":
            mutation_admission = artifacts.get("mutation_admission")
            if (
                not isinstance(mutation_admission, Mapping)
                or mutation_admission.get("mode") != "enforce"
            ):
                return "insufficient_evidence"
            try:
                parse_mutation_admission_judge_configuration(
                    mutation_admission.get("judge")
                )
            except ValueError:
                return "insufficient_evidence"
        if artifacts.get("profile_purpose") != "benchmark":
            return "insufficient_evidence"
        generation_contract = artifacts.get("generation_contract")
        try:
            validate_generation_contract_record(generation_contract)
        except (ContractValidationError, TypeError, ValueError):
            return "insufficient_evidence"
        if not isinstance(generation_contract, Mapping):
            return "insufficient_evidence"
        if generation_contract.get("target_fulfilled") is not True:
            return "insufficient_evidence"
        if generation_contract.get("representative_eligible") is not True:
            return "insufficient_evidence"
        if generation_contract.get("reason_codes") != []:
            return "insufficient_evidence"
        if artifacts.get("target_candidate_count") != generation_contract.get("target_candidate_count"):
            return "insufficient_evidence"
        if (
            artifacts.get("coverage_selected") is True
            and artifacts.get("coverage_fulfillment_status") != "passed"
        ):
            return "insufficient_evidence"
        return "representative"
    return "insufficient_evidence"


def build_representative_scale_evidence(
    campaign: ScaleCampaignInput,
) -> dict[str, object]:
    summaries = [_build_domain_summary(run) for run in campaign.runs]
    public_summaries = [_public_domain_summary(summary) for summary in summaries]
    review = _aggregate_review(summaries)
    triggered = [
        signal
        for signal in ("async_orchestration", "semantic_duplicate_detection")
        if any(signal in summary["signals"] for summary in summaries)
    ]
    identity = {
        "campaign_label": campaign.campaign_label,
        "domains": [
            {
                "domain_id": summary["domain_id"],
                "dataset_version": summary["dataset_version"],
                "profile_id": summary["profile_id"],
                "artifacts": summary["artifacts"],
            }
            for summary in public_summaries
        ],
    }
    digest = hashlib.sha256(_canonical_json(identity)).hexdigest()
    evidence: dict[str, object] = {
        "schema_version": SCALE_EVIDENCE_SCHEMA_VERSION,
        "campaign_id": f"scale_campaign:sha256:{digest}",
        "campaign_label": campaign.campaign_label,
        "domains": public_summaries,
        "review": review,
        "triggered_signals": triggered,
        "decision": select_recommendation(summaries),
    }
    validate_representative_scale_evidence_record(evidence)
    return evidence


def write_representative_scale_evidence(
    *, campaign_path: Path, output_path: Path
) -> Path:
    evidence = build_representative_scale_evidence(load_scale_campaign(campaign_path))
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def select_recommendation(
    domain_summaries: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    if any(summary["classification"] == "insufficient_evidence" for summary in domain_summaries):
        return decision("expand_representative_evidence", "required domain evidence is incomplete")
    representative = [
        summary for summary in domain_summaries
        if summary["classification"] == "representative"
    ]
    if not representative:
        return decision("expand_representative_evidence", "no representative domain run is available")
    if any(has_quality_problem(summary) for summary in representative):
        return decision("improve_generation_or_verification", "representative quality evidence requires remediation")
    if any(has_signal(summary, "semantic_duplicate_detection") for summary in representative):
        return decision("activate_semantic_duplicate_detection", "representative semantic duplicate decision activated")
    if any(has_signal(summary, "async_orchestration") for summary in representative):
        return decision("activate_async_orchestration", "representative async decision activated")
    return decision("no_change_recommended", "representative evidence activates no development gate")


def decision(recommendation: str, reason: str) -> dict[str, object]:
    return {"recommendation": recommendation, "reasons": [reason]}


def has_quality_problem(summary: Mapping[str, Any]) -> bool:
    observed = _mapping(summary.get("observed"))
    return (
        observed.get("heldout_status") == "failed"
        or observed.get("mvp_quality_floor_status") == "failed"
        or int(summary.get("_confirmed_issue_count", 0)) > 0
    )


def has_signal(summary: Mapping[str, Any], signal: str) -> bool:
    signals = summary.get("signals", ())
    return isinstance(signals, Sequence) and signal in signals


def _build_domain_summary(run: CampaignRunInput) -> dict[str, Any]:
    artifact_records = _artifact_records(run.artifact_dir)
    try:
        records = _load_and_validate_artifacts(run)
        manifest = records["manifest"]
        profile_report = records["profile_decision_report"]
        release_report = records["dataset_release_report"]
        audit = records["release_quality_audit"]
        evaluation = records["evaluation_report"]
        profile = _mapping(profile_report["profile"])
        manifest_profile = _mapping(manifest["run_profile"])
        generation_contract = manifest_profile.get("generation_contract")
        generation_mode = str(profile["generation_mode"])
        _validate_cross_artifact_identity(run.domain_id, records)
        _validate_generation_contract_identity(records, generation_contract)
        review = records.get("review_resolution_report")
        review_counts = _review_counts(review)
        async_status = _decision_status(profile_report, "async_orchestration")
        semantic_status = _decision_status(profile_report, "semantic_duplicate_detection")
        signals = []
        if async_status == "activate":
            signals.append("async_orchestration")
        if semantic_status == "activate":
            signals.append("semantic_duplicate_detection")
        observed_profile = _mapping(profile_report["observed"])
        coverage_selected = isinstance(
            manifest_profile.get("coverage_profile"),
            Mapping,
        )
        coverage_status = (
            _decision_status(profile_report, "coverage_fulfillment")
            if coverage_selected
            and "coverage_fulfillment" in _mapping(
                profile_report.get("decisions")
            )
            else (
                "insufficient_evidence"
                if coverage_selected
                else None
            )
        )
        summary: dict[str, Any] = {
            "domain_id": run.domain_id,
            "dataset_version": str(manifest["dataset_version"]),
            "profile_id": str(profile["profile_id"]),
            "generation_mode": generation_mode,
            "classification": classify_run({
                "valid": True,
                "generation_mode": generation_mode,
                "generation_contract": generation_contract,
                "schema_version": manifest_profile.get("schema_version"),
                "profile_purpose": manifest_profile.get("profile_purpose"),
                "target_candidate_count": manifest_profile.get("target_candidate_count"),
                "mutation_admission": manifest_profile.get("mutation_admission"),
                "coverage_selected": coverage_selected,
                "coverage_fulfillment_status": coverage_status,
            }),
            "artifacts": artifact_records,
            "observed": {
                "total_candidates": int(observed_profile["total_candidates"]),
                "accepted": int(observed_profile["accepted"]),
                "rejected": int(observed_profile["rejected"]),
                "runtime_seconds": float(observed_profile.get("runtime_seconds") or 0.0),
                "exact_duplicate_count": int(observed_profile["exact_duplicate_count"]),
                "exact_duplicate_rate": float(observed_profile["exact_duplicate_rate"]),
                "heldout_status": str(_mapping(evaluation["decision"])["status"]),
                "mvp_quality_floor_status": _decision_status(profile_report, "mvp_quality_floor"),
                "profile_promotion_status": _decision_status(profile_report, "profile_promotion"),
                "dataset_release_status": _decision_status(release_report, "dataset_release"),
                "release_audit_status": str(_mapping(audit["decision"])["status"]),
                "review_resolution_status": (
                    str(_mapping(review["decision"])["status"]) if review else None
                ),
            },
            "signals": signals,
            "_review": review_counts,
            "_confirmed_issue_count": review_counts["confirmed_issue"],
        }
        if coverage_selected:
            summary["observed"]["coverage_fulfillment_status"] = (
                coverage_status
            )
        return summary
    except (OSError, json.JSONDecodeError, ContractValidationError, KeyError, TypeError, ValueError):
        return _insufficient_domain_summary(run.domain_id, artifact_records)


def _validate_generation_contract_identity(
    records: Mapping[str, Mapping[str, Any]],
    expected: object,
) -> None:
    if expected is None:
        return
    profiles = (
        records["evaluation_report"].get("profile"),
        records["profile_decision_report"].get("profile"),
        records["dataset_release_report"].get("profile"),
    )
    for profile in profiles:
        if not isinstance(profile, Mapping) or profile.get("generation_contract") != expected:
            raise ValueError("generation contract metadata mismatch across artifacts")


def _load_and_validate_artifacts(run: CampaignRunInput) -> dict[str, Mapping[str, Any]]:
    validators = {
        "manifest": validate_manifest_record,
        "evaluation_report": validate_evaluation_report_record,
        "profile_decision_report": validate_profile_decision_report_record,
        "dataset_release_report": validate_dataset_release_report_record,
        "release_quality_audit": validate_release_quality_audit_record,
    }
    records: dict[str, Mapping[str, Any]] = {}
    for key, filename in REQUIRED_ARTIFACTS.items():
        record = _load_mapping(run.artifact_dir / filename)
        if key == "quality_report":
            if record.get("schema_version") != "quality_report_v1":
                raise ContractValidationError("quality_report schema_version is unsupported")
        else:
            validators[key](record)
        records[key] = record
    review_path = run.artifact_dir / OPTIONAL_REVIEW_ARTIFACT
    if review_path.exists():
        review = _load_mapping(review_path)
        validate_review_resolution_report_record(review)
        records["review_resolution_report"] = review
    _validate_coverage_artifact_bindings(run.artifact_dir, records)
    return records


def _validate_coverage_artifact_bindings(
    directory: Path,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    manifest = records["manifest"]
    run_profile = manifest.get("run_profile")
    if not (
        isinstance(run_profile, Mapping)
        and isinstance(run_profile.get("coverage_profile"), Mapping)
    ):
        return
    artifacts = _mapping(manifest.get("artifacts"))
    expected_filenames = {
        "coverage_evidence": "coverage_evidence.json",
        "coverage_plan": "coverage_plan.json",
        "samples": "samples.jsonl",
        "rejections": "rejections.jsonl",
    }
    for key, expected_filename in expected_filenames.items():
        if artifacts.get(key) != expected_filename:
            raise ValueError(f"coverage artifact {key} is unavailable")

    evidence = _load_mapping(directory / "coverage_evidence.json")
    plan = _load_mapping(directory / "coverage_plan.json")
    samples_artifact = _artifact_hash_binding(
        directory / "samples.jsonl"
    )
    rejections_artifact = _artifact_hash_binding(
        directory / "rejections.jsonl"
    )
    verify_sanitized_coverage_evidence(
        evidence,
        plan=plan,
        run_profile=run_profile,
        samples_artifact=samples_artifact,
        rejections_artifact=rejections_artifact,
    )
    if evidence.get("dataset_version") != manifest.get("dataset_version"):
        raise ValueError("coverage evidence dataset identity mismatch")

    quality_coverage = _mapping(
        records["quality_report"].get("coverage")
    )
    validate_coverage_quality_summary_record(quality_coverage)
    expected_summary = coverage_quality_summary(evidence)
    if dict(quality_coverage) != expected_summary:
        raise ValueError("coverage quality summary identity mismatch")
    profile_coverage = _mapping(
        records["profile_decision_report"].get("coverage")
    )
    if dict(profile_coverage) != expected_summary:
        raise ValueError("coverage profile decision identity mismatch")
    manifest_binding = _mapping(manifest.get("coverage"))
    if (
        manifest_binding.get("evidence_id") != evidence.get("evidence_id")
        or manifest_binding.get("evidence_hash")
        != evidence.get("evidence_hash")
        or dict(
            _mapping(manifest_binding.get("evidence_artifact"))
        )
        != _artifact_hash_binding(directory / "coverage_evidence.json")
        or dict(
            _mapping(manifest_binding.get("samples_artifact"))
        )
        != samples_artifact
        or dict(
            _mapping(manifest_binding.get("rejections_artifact"))
        )
        != rejections_artifact
    ):
        raise ValueError("coverage manifest binding mismatch")


def _validate_cross_artifact_identity(domain_id: str, records: Mapping[str, Mapping[str, Any]]) -> None:
    dataset_versions = {
        str(record.get("dataset_version"))
        for record in records.values()
    }
    if len(dataset_versions) != 1:
        raise ValueError("dataset identity mismatch")
    evaluation = records["evaluation_report"]
    if _mapping(evaluation["suite"]).get("domain_id") != domain_id:
        raise ValueError("evaluation domain mismatch")
    profiles = []
    manifest_profile = records["manifest"].get("run_profile")
    if manifest_profile:
        profiles.append(_mapping(manifest_profile))
    for key in ("evaluation_report", "profile_decision_report", "dataset_release_report", "release_quality_audit"):
        profile = records[key].get("profile")
        if profile:
            profiles.append(_mapping(profile))
    identities = {
        (str(profile.get("profile_id")), str(profile.get("generation_mode")), str(profile.get("config_hash")))
        for profile in profiles
    }
    if len(identities) != 1:
        raise ValueError("profile identity mismatch")
    review = records.get("review_resolution_report")
    if review and str(review.get("dataset_version")) not in dataset_versions:
        raise ValueError("review dataset mismatch")


def _artifact_records(directory: Path) -> dict[str, dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {}
    for key, filename in REQUIRED_ARTIFACTS.items():
        path = directory / filename
        artifacts[key] = {
            "path": filename,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "0" * 64,
        }
    review_path = directory / OPTIONAL_REVIEW_ARTIFACT
    if review_path.is_file():
        artifacts["review_resolution_report"] = {
            "path": OPTIONAL_REVIEW_ARTIFACT,
            "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        }
    if (directory / "coverage_evidence.json").is_file():
        for key, filename in {
            "coverage_evidence": "coverage_evidence.json",
            "coverage_plan": "coverage_plan.json",
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
        }.items():
            path = directory / filename
            artifacts[key] = {
                "path": filename,
                "sha256": (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else "0" * 64
                ),
            }
    return artifacts


def _insufficient_domain_summary(domain_id: str, artifacts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "domain_id": domain_id,
        "dataset_version": f"unknown_{domain_id}",
        "profile_id": f"unknown_{domain_id}",
        "generation_mode": "unknown",
        "classification": "insufficient_evidence",
        "artifacts": dict(artifacts),
        "observed": {
            "total_candidates": 0,
            "accepted": 0,
            "rejected": 0,
            "runtime_seconds": 0.0,
            "exact_duplicate_count": 0,
            "exact_duplicate_rate": 0.0,
            "heldout_status": "insufficient_evidence",
            "mvp_quality_floor_status": "insufficient_evidence",
            "profile_promotion_status": "insufficient_evidence",
            "dataset_release_status": "insufficient_evidence",
            "release_audit_status": "insufficient_evidence",
            "review_resolution_status": None,
        },
        "signals": [],
        "_review": _empty_review(),
        "_confirmed_issue_count": 0,
    }


def _public_domain_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if not key.startswith("_")}


def _aggregate_review(summaries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    total = _empty_review()
    for summary in summaries:
        for key, value in _mapping(summary.get("_review")).items():
            total[key] += int(value)
    return total


def _review_counts(review: Mapping[str, Any] | None) -> dict[str, int]:
    if not review:
        return _empty_review()
    counts = _mapping(review["counts"])
    return {key: int(counts[key]) for key in _empty_review()}


def _empty_review() -> dict[str, int]:
    return {
        "queued": 0,
        "resolved": 0,
        "pending": 0,
        "confirmed_issue": 0,
        "accepted_risk": 0,
        "needs_follow_up": 0,
        "review_minutes": 0,
    }


def _decision_status(report: Mapping[str, Any], name: str) -> str:
    return str(_mapping(_mapping(report["decisions"])[name])["status"])


def _load_mapping(path: Path) -> Mapping[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, Mapping):
        raise ContractValidationError(f"{path.name} must contain an object")
    return record


def _artifact_hash_binding(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": path.name,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "byte_count": len(content),
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping")
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
