from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from synthesis.contracts import (
    ContractValidationError,
    validate_manifest_record,
    validate_rejection_record,
    validate_sample_record,
)
from synthesis.mutation_admission import validate_mutation_admission_evidence
from synthesis.mutation_admission_reporting import (
    build_mutation_admission_report,
    validate_mutation_admission_report,
    validate_retained_admission_material,
    validate_retained_release_material,
)


def verify_mutation_safe_manifest(manifest_path: Path) -> dict[str, object]:
    try:
        manifest = _load_mapping(manifest_path)
        validate_manifest_record(manifest)
    except (
        OSError,
        json.JSONDecodeError,
        ContractValidationError,
        RecursionError,
        ValueError,
    ) as exc:
        return _verification(
            "failed",
            [f"mutation-safe manifest is unreadable or invalid: {type(exc).__name__}"],
        )

    if manifest.get("schema_version") != "dataset_manifest_v2":
        return _verification(
            "failed",
            ["historical dataset_manifest_v1 cannot certify mutation safety"],
        )

    reasons: list[str] = []
    profile = manifest.get("run_profile")
    admission_profile = (
        profile.get("mutation_admission")
        if isinstance(profile, Mapping)
        else None
    )
    if (
        not isinstance(admission_profile, Mapping)
        or admission_profile.get("mode") != "enforce"
    ):
        reasons.append("mutation-safe release requires enforce mode")

    bindings = manifest.get("admission_artifacts")
    if not isinstance(bindings, Mapping):
        return _verification("failed", ["admission artifact bindings are missing"])
    reasons.extend(_artifact_binding_reasons(manifest_path.parent, bindings))
    if any("artifact" in reason and "mismatch" in reason for reason in reasons):
        return _verification("failed", reasons)

    try:
        samples = _load_jsonl(
            manifest_path.parent / _binding_path(bindings, "samples")
        )
        rejections = _load_jsonl(
            manifest_path.parent / _binding_path(bindings, "rejections")
        )
        report = _load_mapping(
            manifest_path.parent
            / _binding_path(bindings, "mutation_admission_report")
        )
        validate_mutation_admission_report(report)
        validate_retained_admission_material(report)
    except (
        OSError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        reasons.append(
            "admission artifacts are unreadable or invalid: "
            f"{type(exc).__name__}"
        )
        return _verification("failed", reasons)

    if report.get("dataset_version") != manifest.get("dataset_version"):
        reasons.append("mutation admission report dataset version mismatch")

    evidence_count = 0
    missing_count = 0
    observed_contracts: dict[str, set[object]] = {
        "evidence": set(),
        "authorization": set(),
        "domain_policy": set(),
        "semantic_verdict": set(),
    }
    for index, sample in enumerate(samples):
        try:
            validate_retained_release_material(sample)
        except ValueError:
            reasons.append(f"samples.{index} contains prohibited retained material")
        evidence = sample.get("mutation_admission")
        if not isinstance(evidence, Mapping):
            missing_count += 1
            reasons.append(
                f"samples.{index} is missing mutation admission evidence"
            )
            continue
        evidence_count += 1
        _observe_contract_versions(evidence, observed_contracts)
        if (
            _sample_has_state_change(sample)
            and evidence.get("classification") != "state_changing"
        ):
            reasons.append(
                f"samples.{index} state-changing sample is classified read-only"
            )
        reasons.extend(
            _evidence_failure_reasons(
                evidence,
                path=f"samples.{index}.mutation_admission",
                accepted=True,
            )
        )
        try:
            validate_sample_record(sample)
        except (ContractValidationError, ValueError):
            reasons.append(
                f"samples.{index} has invalid mutation admission evidence"
            )

    for index, rejection in enumerate(rejections):
        try:
            validate_retained_release_material(rejection)
        except ValueError:
            reasons.append(
                f"rejections.{index} contains prohibited retained material"
            )
        details = rejection.get("details")
        evidence = (
            details.get("mutation_admission")
            if isinstance(details, Mapping)
            else None
        )
        if not isinstance(evidence, Mapping):
            missing_count += 1
            if _record_declares_state_change(rejection):
                reasons.append(
                    f"rejections.{index} is missing mutation admission evidence"
                )
        else:
            evidence_count += 1
            _observe_contract_versions(evidence, observed_contracts)
            if (
                _record_declares_state_change(rejection)
                and evidence.get("classification") != "state_changing"
            ):
                reasons.append(
                    f"rejections.{index} state-changing rejection is classified read-only"
                )
            reasons.extend(
                _evidence_failure_reasons(
                    evidence,
                    path=f"rejections.{index}.details.mutation_admission",
                    accepted=False,
                )
            )
        try:
            validate_rejection_record(rejection)
        except (ContractValidationError, ValueError):
            reasons.append(
                f"rejections.{index} has invalid mutation admission evidence"
            )

    counts = report.get("counts")
    if isinstance(counts, Mapping):
        if counts.get("evidence_records") != evidence_count:
            reasons.append("mutation admission report evidence count mismatch")
        if counts.get("missing_evidence") != missing_count:
            reasons.append("mutation admission report missing count mismatch")
    else:
        reasons.append("mutation admission report counts are missing")
    try:
        expected_report = build_mutation_admission_report(
            dataset_version=str(manifest.get("dataset_version", "")),
            samples=samples,
            rejections=rejections,
        )
    except ValueError:
        expected_report = None
    if expected_report is not None and report != expected_report:
        reasons.append("mutation admission report content mismatch")
    reasons.extend(
        _contract_declaration_reasons(
            manifest.get("admission_contract_versions"),
            observed_contracts,
        )
    )

    return _verification("failed" if reasons else "passed", sorted(set(reasons)))


def _evidence_failure_reasons(
    evidence: Mapping[str, object],
    *,
    path: str,
    accepted: bool,
) -> list[str]:
    reasons: list[str] = []
    if evidence.get("schema_version") != "mutation_admission_evidence_v2":
        reasons.append(f"{path} uses an unsupported evidence contract")
    if evidence.get("diagnostic_only") is True:
        reasons.append(f"{path} is diagnostic-only")
    try:
        validate_mutation_admission_evidence(evidence)
        validate_retained_admission_material(evidence)
    except ValueError:
        reasons.append(f"{path} has invalid mutation admission evidence")
        return reasons

    if evidence.get("mode") != "enforce":
        reasons.append(f"{path} does not record enforce mode")
    if not accepted or evidence.get("classification") != "state_changing":
        return reasons

    verdict = evidence.get("semantic_verdict")
    judge_call = evidence.get("judge_call")
    if (
        evidence.get("admission_outcome") != "judge_supported"
        or not isinstance(verdict, Mapping)
        or verdict.get("verdict") != "supported"
        or not isinstance(judge_call, Mapping)
        or judge_call.get("outcome") != "succeeded"
    ):
        reasons.append(f"{path} lacks a supported semantic verdict")
    if evidence.get("model_independence") != "independent":
        reasons.append(f"{path} lacks generator/judge independence")
    return reasons


def _observe_contract_versions(
    evidence: Mapping[str, object],
    observed: dict[str, set[object]],
) -> None:
    observed["evidence"].add(evidence.get("schema_version"))
    versions = evidence.get("contract_versions")
    if not isinstance(versions, Mapping):
        return
    for key in ("authorization", "domain_policy", "semantic_verdict"):
        observed[key].add(versions.get(key))


def _contract_declaration_reasons(
    raw_declared: object,
    observed: Mapping[str, set[object]],
) -> list[str]:
    if not isinstance(raw_declared, Mapping):
        return ["admission contract version declarations are missing"]
    reasons = []
    for key, values in observed.items():
        raw_values = raw_declared.get(key)
        declared = set(raw_values) if isinstance(raw_values, list) else set()
        if values != declared:
            reasons.append(
                f"admission contract version declaration mismatch: {key}"
            )
    return reasons


def _artifact_binding_reasons(
    base_dir: Path,
    bindings: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for key in ("samples", "rejections", "mutation_admission_report"):
        try:
            binding = bindings[key]
            if not isinstance(binding, Mapping):
                raise ValueError
            path = base_dir / str(binding["path"])
            content = path.read_bytes()
            actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
            if (
                binding.get("sha256") != actual_hash
                or binding.get("byte_count") != len(content)
            ):
                reasons.append(f"{key} admission artifact hash mismatch")
        except (KeyError, OSError, TypeError, ValueError):
            reasons.append(f"{key} admission artifact is missing")
    return reasons


def _record_declares_state_change(record: Mapping[str, object]) -> bool:
    if record.get("cause") == "mutation_admission_failed":
        return True
    task = record.get("task")
    difficulty = task.get("difficulty") if isinstance(task, Mapping) else None
    state_changes = (
        difficulty.get("state_changes")
        if isinstance(difficulty, Mapping)
        else None
    )
    return (
        isinstance(state_changes, int)
        and not isinstance(state_changes, bool)
        and state_changes > 0
    )


def _sample_has_state_change(sample: Mapping[str, object]) -> bool:
    if _record_declares_state_change(sample):
        return True
    tools = sample.get("tools")
    state_changing_tools = {
        str(tool.get("name"))
        for tool in tools
        if isinstance(tool, Mapping)
        and tool.get("side_effects") == "state_mutating"
    } if isinstance(tools, list) else set()
    trajectory = sample.get("trajectory")
    if not isinstance(trajectory, list):
        return False
    return any(
        isinstance(event, Mapping)
        and (
            event.get("type") == "state_change"
            or (
                event.get("type") == "action"
                and event.get("tool") in state_changing_tools
            )
        )
        for event in trajectory
    )


def _binding_path(bindings: Mapping[str, Any], key: str) -> str:
    binding = bindings.get(key)
    if not isinstance(binding, Mapping):
        raise ValueError(f"{key} binding is missing")
    path = binding.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError(f"{key} binding path is missing")
    return path


def _load_jsonl(path: Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path.name} record must be an object")
        records.append(raw)
    return records


def _load_mapping(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path.name} must contain an object")
    return raw


def _verification(status: str, reasons: list[str]) -> dict[str, object]:
    return {"status": status, "reasons": reasons}
