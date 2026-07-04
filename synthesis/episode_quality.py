from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from synthesis.contracts import (
    ContractValidationError,
    EPISODE_QUALITY_CHECK_NAMES,
    validate_episode_log_record,
    validate_episode_quality_report_record,
)
from awm_runtime.episodes import summarize_episode_for_quality
from awm_runtime.runtime import RuntimeRegistry
from synthesis.runtime_registry import runtime_descriptor


EPISODES_FILENAME = "episodes.jsonl"
EPISODE_QUALITY_REPORT_FILENAME = "episode_quality_report.json"

_REQUIRED_CHECKS = frozenset(
    {
        "contract_valid",
        "has_action",
        "has_observation",
        "accepted_has_final_response",
        "accepted_has_no_error",
    }
)
_CHECK_ORDER = (
    "contract_valid",
    "has_action",
    "has_observation",
    "accepted_has_final_response",
    "accepted_has_no_error",
    "state_change_supported",
    "runtime_known",
)


@dataclass(frozen=True)
class EpisodeQualityThresholds:
    required_checks: frozenset[str] = _REQUIRED_CHECKS


def write_episode_logs(path: Path, episodes: Sequence[Mapping[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for episode in episodes:
        validate_episode_log_record(episode)
        lines.append(json.dumps(episode, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def read_episode_logs(path: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"episode log line {line_number} must be a JSON object")
        validate_episode_log_record(parsed)
        records.append(parsed)
    return tuple(records)


def build_episode_quality_report(
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    runtime_registry: RuntimeRegistry | None = None,
) -> dict[str, object]:
    summaries: list[dict[str, object]] = []
    check_failures: dict[str, int] = {name: 0 for name in _CHECK_ORDER}
    runtime_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    tool_names: set[str] = set()

    for record in episodes:
        summary, failed_checks = _score_episode(
            record,
            runtime_registry=runtime_registry,
        )
        summaries.append(summary)
        runtime_counts[str(summary["runtime_id"])] += 1
        outcome_counts[str(summary["outcome_status"])] += 1
        tool_names.update(str(tool_name) for tool_name in summary["tool_names"])
        for check_name in failed_checks:
            check_failures[check_name] += 1

    checks = [
        {
            "name": check_name,
            "status": "failed" if check_failures[check_name] else "passed",
            "passed": max(len(episodes) - check_failures[check_name], 0),
            "failed": check_failures[check_name],
            "required": check_name in _REQUIRED_CHECKS,
        }
        for check_name in _CHECK_ORDER
    ]
    decision = _decision_for_checks(
        episode_count=len(episodes),
        check_failures=check_failures,
    )
    report: dict[str, object] = {
        "schema_version": "episode_quality_report_v1",
        "dataset_version": dataset_version,
        "inputs": {
            "manifest_path": _artifact_name(manifest_path, "manifest.json"),
            "episodes_path": _artifact_name(episodes_path, EPISODES_FILENAME),
        },
        "observed": {
            "episode_count": len(episodes),
            "accepted": outcome_counts.get("accepted", 0),
            "rejected": outcome_counts.get("rejected", 0),
            "failed": outcome_counts.get("failed", 0),
            "runtime_counts": dict(sorted(runtime_counts.items())),
            "tool_names": sorted(tool_names),
        },
        "checks": checks,
        "episode_summaries": summaries,
        "decision": decision,
    }
    validate_episode_quality_report_record(report)
    return report


def write_episode_quality_report(
    path: Path,
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    runtime_registry: RuntimeRegistry | None = None,
) -> Path:
    report = build_episode_quality_report(
        dataset_version=dataset_version,
        episodes=episodes,
        manifest_path=manifest_path,
        episodes_path=episodes_path,
        runtime_registry=runtime_registry,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _score_episode(
    record: Mapping[str, object],
    *,
    runtime_registry: RuntimeRegistry | None,
) -> tuple[dict[str, object], tuple[str, ...]]:
    failed_checks: list[str] = []
    try:
        validate_episode_log_record(record)
    except ContractValidationError:
        failed_checks.append("contract_valid")
        summary = _invalid_episode_summary(record)
        summary["failed_checks"] = failed_checks
        return summary, tuple(failed_checks)

    summary = summarize_episode_for_quality(record)
    transitions = record["transitions"]
    assert isinstance(transitions, Sequence)
    error_count = _transition_count(transitions, "error")
    summary = {
        "episode_id": str(record["episode_id"]),
        "candidate_id": str(record["candidate_id"]),
        **summary,
        "error_count": error_count,
    }

    if summary["action_count"] < 1:
        failed_checks.append("has_action")
    if summary["observation_count"] < 1:
        failed_checks.append("has_observation")
    if summary["outcome_status"] == "accepted" and summary["final_response_count"] != 1:
        failed_checks.append("accepted_has_final_response")
    if summary["outcome_status"] == "accepted" and error_count:
        failed_checks.append("accepted_has_no_error")
    runtime_id = str(summary["runtime_id"])
    try:
        descriptor = runtime_descriptor(runtime_id, runtime_registry)
    except KeyError:
        failed_checks.append("runtime_known")
        descriptor = None
    tools = set(str(tool_name) for tool_name in summary["tool_names"])
    state_changing_tools = descriptor.state_changing_tools if descriptor is not None else ()
    if tools.intersection(state_changing_tools) and summary["state_change_count"] < 1:
        failed_checks.append("state_change_supported")
    summary["failed_checks"] = failed_checks
    return summary, tuple(failed_checks)


def _invalid_episode_summary(record: Mapping[str, object]) -> dict[str, object]:
    runtime = record.get("runtime")
    outcome = record.get("outcome")
    return {
        "episode_id": str(record.get("episode_id", "unknown_episode")),
        "candidate_id": str(record.get("candidate_id", "unknown_candidate")),
        "runtime_id": (
            str(runtime.get("runtime_id", "unknown_runtime"))
            if isinstance(runtime, Mapping)
            else "unknown_runtime"
        ),
        "outcome_status": (
            str(outcome.get("status", "failed")) if isinstance(outcome, Mapping) else "failed"
        ),
        "action_count": 0,
        "observation_count": 0,
        "state_change_count": 0,
        "final_response_count": 0,
        "error_count": 0,
        "tool_names": [],
    }


def _decision_for_checks(
    *,
    episode_count: int,
    check_failures: Mapping[str, int],
) -> dict[str, object]:
    if episode_count == 0:
        return {
            "status": "insufficient_evidence",
            "reasons": ["no episode logs are available"],
            "triggered_by": [],
        }
    required_failures = [
        name for name in _CHECK_ORDER if name in _REQUIRED_CHECKS and check_failures[name]
    ]
    if required_failures:
        return {
            "status": "failed",
            "reasons": [
                f"required checks failed: {', '.join(required_failures)}",
            ],
            "triggered_by": required_failures,
        }
    optional_failures = [
        name for name in _CHECK_ORDER if name not in _REQUIRED_CHECKS and check_failures[name]
    ]
    if optional_failures:
        return {
            "status": "watch",
            "reasons": [
                f"optional diagnostic checks failed: {', '.join(optional_failures)}",
            ],
            "triggered_by": optional_failures,
        }
    return {"status": "passed", "reasons": [], "triggered_by": []}


def _transition_count(transitions: Sequence[object], event_type: str) -> int:
    return sum(
        1
        for transition in transitions
        if isinstance(transition, Mapping) and transition.get("event_type") == event_type
    )


def _artifact_name(path: Path | None, default: str) -> str:
    if path is None:
        return default
    return path.name


assert set(_CHECK_ORDER) == EPISODE_QUALITY_CHECK_NAMES
