from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from synthesis.contracts import (
    ContractValidationError,
    REWARD_LABEL_CHECK_NAMES,
    validate_episode_log_record,
    validate_reward_label_record,
    validate_reward_label_report_record,
)


REWARD_LABELS_FILENAME = "reward_labels.jsonl"
REWARD_LABEL_REPORT_FILENAME = "reward_label_report.json"
KNOWN_REWARD_RUNTIMES = frozenset({"contacts_fixture", "mobile_messages_fixture"})
STATE_CHANGING_TOOLS = frozenset(
    {"record_contact_followup", "create_phone_reminder", "draft_message_reply"}
)

_CHECK_ORDER = (
    "labels_present",
    "label_contract_valid",
    "episode_contract_valid",
    "quality_evidence_aligned",
    "replay_evidence_aligned",
    "usable_label_coverage",
    "sanitized_summaries",
)
_REQUIRED_CHECKS = frozenset(
    {
        "labels_present",
        "label_contract_valid",
        "episode_contract_valid",
        "quality_evidence_aligned",
        "usable_label_coverage",
        "sanitized_summaries",
    }
)
_REPLAY_REQUIRED_CHECKS = frozenset(
    {
        "contract_valid",
        "runtime_supported",
        "runtime_rebuilt",
        "actions_replayed",
        "accepted_has_final_response",
    }
)
_QUALITY_REQUIRED_CHECKS = frozenset(
    {
        "contract_valid",
        "has_action",
        "has_observation",
        "accepted_has_final_response",
        "accepted_has_no_error",
    }
)


@dataclass(frozen=True)
class RewardLabelThresholds:
    outcome: float = 0.35
    contract: float = 0.20
    execution: float = 0.20
    state_support: float = 0.15
    replay_consistency: float = 0.10


def build_reward_labels(
    *,
    episodes: Sequence[Mapping[str, object]],
    episode_quality_report: Mapping[str, object] | None = None,
    episode_replay_report: Mapping[str, object] | None = None,
    thresholds: RewardLabelThresholds = RewardLabelThresholds(),
) -> tuple[dict[str, object], ...]:
    quality_summaries = _summary_by_episode_id(episode_quality_report)
    replay_summaries = _summary_by_episode_id(episode_replay_report)
    labels: list[dict[str, object]] = []

    for episode in episodes:
        labels.append(
            _build_label(
                episode=episode,
                quality_summary=quality_summaries.get(str(episode.get("episode_id"))),
                replay_summary=(
                    replay_summaries.get(str(episode.get("episode_id")))
                    if episode_replay_report is not None
                    else None
                ),
                has_quality_report=episode_quality_report is not None,
                has_replay_report=episode_replay_report is not None,
                thresholds=thresholds,
            )
        )

    ranked_labels = _rank_preference_groups(labels)
    for label in ranked_labels:
        validate_reward_label_record(label)
    return tuple(ranked_labels)


def write_reward_labels(path: Path, labels: Sequence[Mapping[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for label in labels:
        validate_reward_label_record(label)
        lines.append(json.dumps(label, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def read_reward_labels(path: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"reward label line {line_number} must be a JSON object")
        validate_reward_label_record(parsed)
        records.append(parsed)
    return tuple(records)


def build_reward_label_report(
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    episode_quality_report_path: Path | None = None,
    episode_replay_report_path: Path | None = None,
    reward_labels_path: Path | None = None,
) -> dict[str, object]:
    runtime_counts: Counter[str] = Counter()
    label_status_counts: Counter[str] = Counter()
    scalar_rewards: list[float] = []
    label_summaries: list[dict[str, object]] = []
    check_failures = {name: 0 for name in _CHECK_ORDER}

    if not labels:
        check_failures["labels_present"] = 1
        check_failures["usable_label_coverage"] = 1

    for label in labels:
        try:
            validate_reward_label_record(label)
        except ContractValidationError:
            check_failures["label_contract_valid"] += 1
            continue

        runtime_id = str(label["runtime_id"])
        label_status = str(label["label_status"])
        scalar_reward = float(label["scalar_reward"])
        reasons = {str(reason) for reason in _sequence(label["reasons"])}
        runtime_counts[runtime_id] += 1
        label_status_counts[label_status] += 1
        scalar_rewards.append(scalar_reward)

        failed_checks = _failed_report_checks(label_status=label_status, reasons=reasons)
        for check_name in failed_checks:
            check_failures[check_name] += 1
        label_summaries.append(
            {
                "label_id": str(label["label_id"]),
                "episode_id": str(label["episode_id"]),
                "candidate_id": str(label["candidate_id"]),
                "runtime_id": runtime_id,
                "label_status": label_status,
                "scalar_reward": scalar_reward,
                "failed_checks": failed_checks,
            }
        )

    usable = label_status_counts.get("usable", 0)
    if labels and usable == 0:
        check_failures["usable_label_coverage"] = max(
            check_failures["usable_label_coverage"],
            1,
        )

    checks = [
        {
            "name": check_name,
            "status": "failed" if check_failures[check_name] else "passed",
            "passed": max(len(labels) - check_failures[check_name], 0),
            "failed": check_failures[check_name],
            "required": check_name in _REQUIRED_CHECKS,
        }
        for check_name in _CHECK_ORDER
    ]
    average_reward = round(sum(scalar_rewards) / len(scalar_rewards), 6) if scalar_rewards else 0.0
    report: dict[str, object] = {
        "schema_version": "reward_label_report_v1",
        "dataset_version": dataset_version,
        "inputs": {
            "manifest_path": _artifact_name(manifest_path, "manifest.json"),
            "episodes_path": _artifact_name(episodes_path, "episodes.jsonl"),
            "episode_quality_report_path": _artifact_name(
                episode_quality_report_path,
                None,
            ),
            "episode_replay_report_path": _artifact_name(
                episode_replay_report_path,
                None,
            ),
            "reward_labels_path": _artifact_name(reward_labels_path, REWARD_LABELS_FILENAME),
        },
        "observed": {
            "episode_count": len(episodes),
            "label_count": len(labels),
            "usable": usable,
            "excluded": label_status_counts.get("excluded", 0),
            "insufficient_evidence": label_status_counts.get("insufficient_evidence", 0),
            "runtime_counts": dict(sorted(runtime_counts.items())),
            "average_scalar_reward": average_reward,
        },
        "checks": checks,
        "label_summaries": label_summaries,
        "decision": _decision_for_report(
            episode_count=len(episodes),
            check_failures=check_failures,
            label_status_counts=label_status_counts,
        ),
    }
    validate_reward_label_report_record(report)
    return report


def write_reward_label_report(
    path: Path,
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    episode_quality_report_path: Path | None = None,
    episode_replay_report_path: Path | None = None,
    reward_labels_path: Path | None = None,
) -> Path:
    report = build_reward_label_report(
        dataset_version=dataset_version,
        episodes=episodes,
        labels=labels,
        manifest_path=manifest_path,
        episodes_path=episodes_path,
        episode_quality_report_path=episode_quality_report_path,
        episode_replay_report_path=episode_replay_report_path,
        reward_labels_path=reward_labels_path,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _build_label(
    *,
    episode: Mapping[str, object],
    quality_summary: Mapping[str, object] | None,
    replay_summary: Mapping[str, object] | None,
    has_quality_report: bool,
    has_replay_report: bool,
    thresholds: RewardLabelThresholds,
) -> dict[str, object]:
    try:
        validate_episode_log_record(episode)
    except ContractValidationError:
        return _excluded_invalid_episode_label(episode)

    episode_id = str(episode["episode_id"])
    candidate_id = str(episode["candidate_id"])
    runtime = _mapping(episode["runtime"])
    outcome = _mapping(episode["outcome"])
    transitions = _sequence(episode["transitions"])
    runtime_id = str(runtime["runtime_id"])
    outcome_status = str(outcome["status"])
    tool_names = _tool_names(transitions)
    reasons: list[str] = []

    components = {
        "outcome": 1.0 if outcome_status == "accepted" else 0.0,
        "contract": 1.0,
        "execution": 0.0,
        "state_support": 1.0,
        "replay_consistency": 0.5,
    }

    if outcome_status == "accepted":
        reasons.append("accepted_episode")
    else:
        reasons.append(f"{outcome_status}_episode")

    label_status = "usable"
    if runtime_id not in KNOWN_REWARD_RUNTIMES:
        label_status = "excluded"
        reasons.append("runtime_unsupported")

    quality_failed_checks = _failed_checks(quality_summary)
    if not has_quality_report or quality_summary is None:
        label_status = "insufficient_evidence"
        reasons.append("quality_evidence_absent")
    elif quality_failed_checks:
        reasons.append("quality_checks_failed")
        if _QUALITY_REQUIRED_CHECKS.intersection(quality_failed_checks):
            label_status = "insufficient_evidence"
    else:
        reasons.append("quality_checks_passed")
        components["execution"] = 0.5

    if _state_change_supported(tool_names=tool_names, quality_summary=quality_summary):
        components["state_support"] = 1.0
    else:
        components["state_support"] = 0.0
        reasons.append("state_change_support_missing")

    replay_failed_checks = _failed_checks(replay_summary)
    if not has_replay_report:
        reasons.append("replay_evidence_absent")
    elif replay_summary is None:
        label_status = "insufficient_evidence"
        reasons.append("replay_evidence_absent")
    elif replay_failed_checks:
        reasons.append("replay_checks_failed")
        components["replay_consistency"] = 0.0
        components["execution"] = 0.0 if _REPLAY_REQUIRED_CHECKS.intersection(replay_failed_checks) else 0.5
    else:
        reasons.append("replay_checks_passed")
        components["replay_consistency"] = 1.0
        if components["execution"] > 0.0:
            components["execution"] = 1.0

    scalar_reward = _scalar_reward(components, thresholds)
    label = {
        "schema_version": "reward_label_v1",
        "label_id": f"reward_label_{candidate_id}",
        "episode_id": episode_id,
        "candidate_id": candidate_id,
        "runtime_id": runtime_id,
        "outcome_status": outcome_status,
        "scalar_reward": scalar_reward,
        "label_status": label_status,
        "label_source": _label_source(
            has_quality_report=has_quality_report,
            has_replay_report=has_replay_report,
        ),
        "components": components,
        "preference_group": {
            "group_id": _preference_group_id(runtime_id=runtime_id, tool_names=tool_names),
            "rank": 1,
            "tie_breaker": candidate_id,
        },
        "reasons": _dedupe(reasons),
    }
    validate_reward_label_record(label)
    return label


def _excluded_invalid_episode_label(episode: Mapping[str, object]) -> dict[str, object]:
    runtime = episode.get("runtime")
    outcome = episode.get("outcome")
    runtime_id = (
        str(runtime.get("runtime_id", "contacts_fixture"))
        if isinstance(runtime, Mapping)
        else "contacts_fixture"
    )
    if runtime_id not in KNOWN_REWARD_RUNTIMES:
        runtime_id = "contacts_fixture"
    label = {
        "schema_version": "reward_label_v1",
        "label_id": f"reward_label_{episode.get('candidate_id', 'unknown_candidate')}",
        "episode_id": str(episode.get("episode_id", "unknown_episode")),
        "candidate_id": str(episode.get("candidate_id", "unknown_candidate")),
        "runtime_id": runtime_id,
        "outcome_status": (
            str(outcome.get("status", "failed")) if isinstance(outcome, Mapping) else "failed"
        ),
        "scalar_reward": 0.0,
        "label_status": "excluded",
        "label_source": {},
        "components": {
            "outcome": 0.0,
            "contract": 0.0,
            "execution": 0.0,
            "state_support": 0.0,
            "replay_consistency": 0.0,
        },
        "preference_group": {
            "group_id": f"pref_{runtime_id}_invalid",
            "rank": 1,
            "tie_breaker": str(episode.get("candidate_id", "unknown_candidate")),
        },
        "reasons": ["episode_contract_invalid"],
    }
    validate_reward_label_record(label)
    return label


def _summary_by_episode_id(
    report: Mapping[str, object] | None,
) -> dict[str, Mapping[str, object]]:
    if report is None:
        return {}
    summaries = report.get("episode_summaries")
    if not isinstance(summaries, Sequence) or isinstance(summaries, str):
        return {}
    by_episode: dict[str, Mapping[str, object]] = {}
    for summary in summaries:
        if isinstance(summary, Mapping) and isinstance(summary.get("episode_id"), str):
            by_episode[str(summary["episode_id"])] = summary
    return by_episode


def _failed_checks(summary: Mapping[str, object] | None) -> frozenset[str]:
    if summary is None:
        return frozenset()
    failed = summary.get("failed_checks")
    if not isinstance(failed, Sequence) or isinstance(failed, str):
        return frozenset()
    return frozenset(str(check) for check in failed)


def _state_change_supported(
    *,
    tool_names: Sequence[str],
    quality_summary: Mapping[str, object] | None,
) -> bool:
    if not set(tool_names).intersection(STATE_CHANGING_TOOLS):
        return True
    if quality_summary is None:
        return False
    return int(quality_summary.get("state_change_count", 0)) > 0


def _scalar_reward(
    components: Mapping[str, float],
    thresholds: RewardLabelThresholds,
) -> float:
    return round(
        thresholds.outcome * components["outcome"]
        + thresholds.contract * components["contract"]
        + thresholds.execution * components["execution"]
        + thresholds.state_support * components["state_support"]
        + thresholds.replay_consistency * components["replay_consistency"],
        6,
    )


def _label_source(*, has_quality_report: bool, has_replay_report: bool) -> dict[str, object]:
    source: dict[str, object] = {}
    if has_quality_report:
        source["quality_report"] = "episode_quality_report_v1"
    if has_replay_report:
        source["replay_report"] = "episode_replay_report_v1"
    return source


def _preference_group_id(*, runtime_id: str, tool_names: Sequence[str]) -> str:
    if "record_contact_followup" in tool_names:
        capability = "contact_followup"
    elif "create_phone_reminder" in tool_names:
        capability = "mobile_reminder"
    elif "draft_message_reply" in tool_names:
        capability = "mobile_draft_reply"
    elif "search_phone_messages" in tool_names:
        capability = "mobile_message_lookup"
    else:
        capability = "contact_lookup"
    return f"pref_{runtime_id}_{capability}"


def _rank_preference_groups(labels: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    copied = [dict(label) for label in labels]
    for label in copied:
        preference_group = _mapping(label["preference_group"])
        groups[str(preference_group["group_id"])].append(label)
    for group_labels in groups.values():
        ranked = sorted(
            group_labels,
            key=lambda label: (-float(label["scalar_reward"]), str(label["candidate_id"])),
        )
        for rank, label in enumerate(ranked, start=1):
            label["preference_group"] = {
                **_mapping(label["preference_group"]),
                "rank": rank,
            }
    return tuple(copied)


def _failed_report_checks(*, label_status: str, reasons: set[str]) -> list[str]:
    failed_checks: list[str] = []
    if "episode_contract_invalid" in reasons:
        failed_checks.append("episode_contract_valid")
    if "quality_evidence_absent" in reasons or "quality_checks_failed" in reasons:
        failed_checks.append("quality_evidence_aligned")
    if "replay_evidence_absent" in reasons or "replay_checks_failed" in reasons:
        failed_checks.append("replay_evidence_aligned")
    if label_status != "usable":
        failed_checks.append("usable_label_coverage")
    return [check for check in failed_checks if check in REWARD_LABEL_CHECK_NAMES]


def _decision_for_report(
    *,
    episode_count: int,
    check_failures: Mapping[str, int],
    label_status_counts: Mapping[str, int],
) -> dict[str, object]:
    if episode_count == 0:
        return {
            "status": "insufficient_evidence",
            "reasons": ["no_episode_logs_available"],
            "triggered_by": [],
        }
    required_failures = [
        check_name
        for check_name in _REQUIRED_CHECKS
        if check_failures.get(check_name, 0)
    ]
    if required_failures:
        return {
            "status": "failed",
            "reasons": ["required_reward_label_checks_failed"],
            "triggered_by": sorted(required_failures),
        }
    watch_triggers = [
        check_name
        for check_name in _CHECK_ORDER
        if check_failures.get(check_name, 0) and check_name not in _REQUIRED_CHECKS
    ]
    if label_status_counts.get("excluded", 0):
        watch_triggers.append("usable_label_coverage")
    if watch_triggers:
        return {
            "status": "watch",
            "reasons": ["reward_label_optional_evidence_requires_review"],
            "triggered_by": sorted(set(watch_triggers)),
        }
    return {"status": "passed", "reasons": [], "triggered_by": []}


def _artifact_name(path: Path | None, default: str | None) -> str | None:
    return default if path is None else path.name


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


assert set(_CHECK_ORDER) == REWARD_LABEL_CHECK_NAMES
