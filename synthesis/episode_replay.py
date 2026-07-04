from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from awm_runtime.runtime import (
    RuntimeActionRequest,
    RuntimeActionResult,
    RuntimeRegistry,
)
from synthesis.contracts import (
    ContractValidationError,
    validate_episode_log_record,
    validate_episode_replay_report_record,
)
from synthesis.domain_pipeline import build_domain_pipeline_bundle, rebuild_domain_pipeline_bundle
from synthesis.episode_quality import EPISODES_FILENAME
from synthesis.runtime_registry import (
    registered_runtime_ids,
    runtime_capability_status,
    runtime_descriptor,
)


EPISODE_REPLAY_REPORT_FILENAME = "episode_replay_report.json"

_REQUIRED_CHECKS = frozenset(
    {
        "contract_valid",
        "runtime_supported",
        "runtime_rebuilt",
        "actions_replayed",
        "accepted_has_final_response",
    }
)
_CHECK_ORDER = (
    "contract_valid",
    "runtime_supported",
    "runtime_rebuilt",
    "actions_replayed",
    "accepted_has_final_response",
    "observation_hash_match",
    "state_change_hash_match",
    "runtime_metadata_stable",
)


@dataclass(frozen=True)
class EpisodeReplayThresholds:
    required_checks: frozenset[str] = _REQUIRED_CHECKS
    supported_runtimes: frozenset[str] = field(
        default_factory=lambda: frozenset(registered_runtime_ids())
    )
    state_changing_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(_registered_state_changing_tools())
    )


def replay_episode(
    record: Mapping[str, object],
    replay_root: Path,
    *,
    runtime_registry: RuntimeRegistry | None = None,
) -> tuple[dict[str, object], tuple[str, ...]]:
    failed_checks: list[str] = []
    try:
        validate_episode_log_record(record)
    except ContractValidationError:
        summary = _invalid_episode_summary(record)
        summary["failed_checks"] = ["contract_valid"]
        return summary, ("contract_valid",)

    runtime = _mapping(record["runtime"])
    outcome = _mapping(record["outcome"])
    transitions = _sequence(record["transitions"])
    candidate_id = str(record["candidate_id"])
    runtime_id = str(runtime["runtime_id"])
    tool_names = _tool_names(transitions)
    action_count = _transition_count(transitions, "action")
    final_response_count = _transition_count(transitions, "final_response")

    summary = {
        "episode_id": str(record["episode_id"]),
        "candidate_id": candidate_id,
        "runtime_id": runtime_id,
        "outcome_status": str(outcome["status"]),
        "action_count": action_count,
        "replayed_action_count": 0,
        "observation_match_count": 0,
        "observation_mismatch_count": 0,
        "state_change_match_count": 0,
        "state_change_mismatch_count": 0,
        "final_response_count": final_response_count,
        "tool_names": tool_names,
    }

    if (
        runtime_capability_status(
            runtime_id,
            "supports_episode_replay",
            runtime_registry,
        )
        != "supported"
    ):
        summary["failed_checks"] = ["runtime_supported"]
        return summary, ("runtime_supported",)

    descriptor = runtime_descriptor(runtime_id, runtime_registry)

    try:
        seed = descriptor.rebuild_seed
        if seed is None:
            raise ValueError(f"runtime has no rebuild seed: {runtime_id}")
        base_root = replay_root / "_base" / runtime_id
        base_bundle = build_domain_pipeline_bundle(seed, base_root)
        bundle = rebuild_domain_pipeline_bundle(base_bundle, replay_root / candidate_id)
        session = bundle.runtime_session()
    except Exception:
        summary["failed_checks"] = ["runtime_rebuilt"]
        return summary, ("runtime_rebuilt",)

    metadata = session.runtime_metadata()
    if (
        metadata.runtime_id != runtime_id
        or metadata.runtime_version != str(runtime["runtime_version"])
    ):
        failed_checks.append("runtime_metadata_stable")

    for action in _transitions_of_type(transitions, "action"):
        tool_name = str(action.get("tool_name", ""))
        arguments = action.get("arguments")
        if not isinstance(arguments, Mapping):
            failed_checks.append("actions_replayed")
            continue
        request = RuntimeActionRequest(
            runtime_id=runtime_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            action_id=f"replay_{candidate_id}_{action['transition_index']}",
        )
        result = session.execute_action(request)
        if result.status != "succeeded":
            failed_checks.append("actions_replayed")
            continue
        summary["replayed_action_count"] = int(summary["replayed_action_count"]) + 1
        _compare_observation(
            summary=summary,
            transitions=transitions,
            action=action,
            replayed_result=result,
        )
        if tool_name in descriptor.state_changing_tools:
            _compare_state_change(
                summary=summary,
                transitions=transitions,
                action=action,
                replayed_result=result,
            )

    if summary["replayed_action_count"] != action_count:
        failed_checks.append("actions_replayed")
    if summary["outcome_status"] == "accepted" and final_response_count != 1:
        failed_checks.append("accepted_has_final_response")
    if summary["observation_mismatch_count"]:
        failed_checks.append("observation_hash_match")
    if summary["state_change_mismatch_count"]:
        failed_checks.append("state_change_hash_match")

    deduped_failed_checks = tuple(_dedupe(failed_checks))
    summary["failed_checks"] = list(deduped_failed_checks)
    return summary, deduped_failed_checks


def build_episode_replay_report(
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    runtime_registry: RuntimeRegistry | None = None,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="episode-replay-") as tmpdir:
        replay_root = Path(tmpdir)
        summaries: list[dict[str, object]] = []
        check_failures: dict[str, int] = {name: 0 for name in _CHECK_ORDER}
        runtime_counts: Counter[str] = Counter()
        tool_names: set[str] = set()

        for record in episodes:
            summary, failed_checks = replay_episode(
                record,
                replay_root,
                runtime_registry=runtime_registry,
            )
            summaries.append(summary)
            runtime_counts[str(summary["runtime_id"])] += 1
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
    report: dict[str, object] = {
        "schema_version": "episode_replay_report_v1",
        "dataset_version": dataset_version,
        "inputs": {
            "manifest_path": _artifact_name(manifest_path, "manifest.json"),
            "episodes_path": _artifact_name(episodes_path, EPISODES_FILENAME),
        },
        "observed": {
            "episode_count": len(episodes),
            "replayed": sum(int(summary["replayed_action_count"]) > 0 for summary in summaries),
            "runtime_counts": dict(sorted(runtime_counts.items())),
            "tool_names": sorted(tool_names),
        },
        "checks": checks,
        "episode_summaries": summaries,
        "runtime_boundary_evidence": {
            "runtime_methods_used": ["rebuild", "runtime_metadata", "execute_action"],
            "registry_methods_used": [],
            "requires_external_package": False,
            "extraction_signal": "runtime_session_replay_boundary_exercised",
        },
        "decision": _decision_for_checks(
            episode_count=len(episodes),
            check_failures=check_failures,
        ),
    }
    validate_episode_replay_report_record(report)
    return report


def write_episode_replay_report(
    path: Path,
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    runtime_registry: RuntimeRegistry | None = None,
) -> Path:
    report = build_episode_replay_report(
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


def _compare_observation(
    *,
    summary: dict[str, object],
    transitions: Sequence[object],
    action: Mapping[str, object],
    replayed_result: RuntimeActionResult,
) -> None:
    original = _next_transition(
        transitions,
        after_index=int(action["transition_index"]),
        event_type="observation",
        tool_name=str(action["tool_name"]),
    )
    if original is None:
        summary["observation_mismatch_count"] = int(summary["observation_mismatch_count"]) + 1
        return
    if replayed_result.export()["observation_hash"] == original.get("observation_hash"):
        summary["observation_match_count"] = int(summary["observation_match_count"]) + 1
    else:
        summary["observation_mismatch_count"] = int(summary["observation_mismatch_count"]) + 1


def _compare_state_change(
    *,
    summary: dict[str, object],
    transitions: Sequence[object],
    action: Mapping[str, object],
    replayed_result: RuntimeActionResult,
) -> None:
    original = _next_transition(
        transitions,
        after_index=int(action["transition_index"]),
        event_type="state_change",
        tool_name=str(action["tool_name"]),
    )
    if original is None:
        return
    if replayed_result.state_change is None:
        summary["state_change_mismatch_count"] = int(summary["state_change_mismatch_count"]) + 1
        return
    if replayed_result.export()["state_change_hash"] == original.get("change_hash"):
        summary["state_change_match_count"] = int(summary["state_change_match_count"]) + 1
    else:
        summary["state_change_mismatch_count"] = int(summary["state_change_mismatch_count"]) + 1


def _next_transition(
    transitions: Sequence[object],
    *,
    after_index: int,
    event_type: str,
    tool_name: str,
) -> Mapping[str, object] | None:
    for raw_transition in transitions:
        if not isinstance(raw_transition, Mapping):
            continue
        if int(raw_transition.get("transition_index", 0)) <= after_index:
            continue
        if raw_transition.get("event_type") != event_type:
            continue
        if raw_transition.get("tool_name") == tool_name:
            return raw_transition
    return None


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
        "replayed_action_count": 0,
        "observation_match_count": 0,
        "observation_mismatch_count": 0,
        "state_change_match_count": 0,
        "state_change_mismatch_count": 0,
        "final_response_count": 0,
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
            "reasons": ["no_episode_logs_available"],
            "triggered_by": [],
        }
    required_failures = [
        check_name for check_name in _REQUIRED_CHECKS if check_failures.get(check_name, 0)
    ]
    if required_failures:
        return {
            "status": "failed",
            "reasons": ["required_replay_checks_failed"],
            "triggered_by": sorted(required_failures),
        }
    optional_failures = [
        check_name
        for check_name, failure_count in check_failures.items()
        if failure_count and check_name not in _REQUIRED_CHECKS
    ]
    if optional_failures:
        return {
            "status": "watch",
            "reasons": ["optional_replay_diagnostics_failed"],
            "triggered_by": sorted(optional_failures),
        }
    return {"status": "passed", "reasons": [], "triggered_by": []}


def _artifact_name(path: Path | None, default: str) -> str:
    return default if path is None else path.name


def _registered_state_changing_tools(
    runtime_registry: RuntimeRegistry | None = None,
) -> tuple[str, ...]:
    tools: set[str] = set()
    for runtime_id in registered_runtime_ids(runtime_registry):
        tools.update(runtime_descriptor(runtime_id, runtime_registry).state_changing_tools)
    return tuple(sorted(tools))


def _transitions_of_type(
    transitions: Sequence[object],
    event_type: str,
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        transition
        for transition in transitions
        if isinstance(transition, Mapping) and transition.get("event_type") == event_type
    )


def _transition_count(transitions: Sequence[object], event_type: str) -> int:
    return len(_transitions_of_type(transitions, event_type))


def _tool_names(transitions: Sequence[object]) -> list[str]:
    names: list[str] = []
    for transition in transitions:
        if not isinstance(transition, Mapping) or transition.get("tool_name") is None:
            continue
        tool_name = str(transition["tool_name"])
        if tool_name not in names:
            names.append(tool_name)
    return names


def _dedupe(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return value


def _sequence(value: object) -> Sequence[object]:
    assert isinstance(value, Sequence)
    return value
