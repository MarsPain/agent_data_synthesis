"""Bounded, diagnostic-only live pilot support at the Contacts operation layer.

This operation module deliberately does not import the legacy Contacts qualification,
compatibility, proof, canary, or provider-evidence machinery.  It runs the
new Agent-first seam once after explicit authorization, then writes a small
sanitized review record alongside the engine's public artifacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_synthesis.contacts import (
    ContactsDomainAdapter,
    ContactsPilotConfiguration,
    ContactsPilotRehearsal,
    rehearse_contacts_pilot,
    write_contacts_pilot_rehearsal,
)
from agent_synthesis.engine import ReplayResult, RunResult, SynthesisEngine
from agent_synthesis.episode import PublicEpisode
from agent_synthesis.model import JsonModelAdapter
from agent_synthesis.registry import AdapterRegistry


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SECRET_MARKERS = (
    "api_key",
    "credential",
    "passwd",
    "password",
    "secret",
    "access_token",
)


class ContactsLivePilotError(RuntimeError):
    """A bounded, reviewable reason for refusing or stopping a pilot."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class ContactsLivePilotAuthorization(BaseModel):
    """The explicit, non-secret authorization record for one diagnostic pilot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approved: bool = False
    authorization_id: str = Field(min_length=1, max_length=256)
    provider_id: str = Field(min_length=1, max_length=128)
    provider_host: str = Field(min_length=1, max_length=255)
    remote_model: str = Field(min_length=1, max_length=255)
    thinking_mode: Literal["enabled", "disabled"] | None = None

    @field_validator(
        "authorization_id",
        "provider_id",
        "provider_host",
        "remote_model",
    )
    @classmethod
    def _require_safe_identifier(cls, value: str) -> str:
        lowered = value.casefold()
        if (
            not _SAFE_IDENTIFIER.fullmatch(value)
            or lowered.startswith(("sk-", "bearer-"))
            or any(marker in lowered for marker in _SECRET_MARKERS)
        ):
            raise ValueError("pilot authorization fields must be safe identifiers")
        return value

    def validate_approval(self) -> None:
        if not self.approved:
            raise ContactsLivePilotError("live_provider_authorization_required")

    def public_record(self) -> dict[str, object]:
        return {
            "authorization_id": self.authorization_id,
            "authorization_status": "approved",
            "provider_id": self.provider_id,
            "provider_host": self.provider_host,
            "remote_model": self.remote_model,
            "thinking_mode": self.thinking_mode,
        }


@dataclass(frozen=True)
class ContactsLivePilotResult:
    """Paths and the diagnostic decision produced by one authorized pilot."""

    run: RunResult
    replay: ReplayResult
    rehearsal_path: Path
    report_path: Path
    requirements_met: bool


def run_authorized_contacts_pilot(
    *,
    output_directory: Path,
    adapter: ContactsDomainAdapter,
    model: JsonModelAdapter,
    configuration: ContactsPilotConfiguration,
    authorization: ContactsLivePilotAuthorization,
) -> ContactsLivePilotResult:
    """Run exactly one bounded Agent-first Contacts pilot after authorization.

    The runnable part is intentionally limited to the target eight slots.  The
    separately reviewed sixteen-slot ceiling remains recorded in the rehearsal
    artifact, so an insufficient outcome cannot silently spend another set of
    paid requests.
    """

    authorization.validate_approval()
    _validate_live_configuration(
        adapter=adapter,
        model=model,
        configuration=configuration,
        authorization=authorization,
        output_directory=output_directory,
    )

    rehearsal = rehearse_contacts_pilot(adapter, configuration)
    if rehearsal.capacity_status != "sufficient":
        raise ContactsLivePilotError("contacts_pilot_capacity_insufficient")

    output_directory.mkdir(parents=True)
    rehearsal_path = write_contacts_pilot_rehearsal(
        rehearsal,
        output_directory / "contacts_pilot_rehearsal.json",
    )
    engine = SynthesisEngine(AdapterRegistry(domains=(adapter,), models=(model,)))
    run = engine.run(configuration.rehearsal_run_configuration(), output_directory)
    replay = engine.replay(run.run_directory)
    episodes = _read_episodes(run)
    provider_usage = json.loads(run.provider_usage_path.read_text(encoding="utf-8"))
    report, requirements_met = _build_diagnostic_report(
        authorization=authorization,
        configuration=configuration,
        rehearsal=rehearsal,
        run=run,
        replay=replay,
        episodes=episodes,
        provider_usage=provider_usage,
    )
    report_path = output_directory / "contacts_live_pilot_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ContactsLivePilotResult(
        run=run,
        replay=replay,
        rehearsal_path=rehearsal_path,
        report_path=report_path,
        requirements_met=requirements_met,
    )


def _validate_live_configuration(
    *,
    adapter: ContactsDomainAdapter,
    model: JsonModelAdapter,
    configuration: ContactsPilotConfiguration,
    authorization: ContactsLivePilotAuthorization,
    output_directory: Path,
) -> None:
    if adapter.domain_id != ContactsDomainAdapter.domain_id:
        raise ContactsLivePilotError("contacts_pilot_domain_required")
    if model.model_id != configuration.model_id:
        raise ContactsLivePilotError("pilot_model_configuration_mismatch")
    if model.provider_id != authorization.provider_id:
        raise ContactsLivePilotError("pilot_provider_authorization_mismatch")
    if authorization.thinking_mode != configuration.thinking_mode:
        raise ContactsLivePilotError("pilot_thinking_authorization_mismatch")
    if getattr(model, "thinking_mode", None) != configuration.thinking_mode:
        raise ContactsLivePilotError("pilot_thinking_configuration_mismatch")
    if output_directory.exists():
        raise ContactsLivePilotError("pilot_output_directory_already_exists")


def _read_episodes(run: RunResult) -> tuple[PublicEpisode, ...]:
    records: list[PublicEpisode] = []
    for path in (run.demonstrations_path, run.negatives_path):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                records.append(PublicEpisode.model_validate_json(line))
    return tuple(sorted(records, key=lambda episode: episode.sequence))


def _build_diagnostic_report(
    *,
    authorization: ContactsLivePilotAuthorization,
    configuration: ContactsPilotConfiguration,
    rehearsal: ContactsPilotRehearsal,
    run: RunResult,
    replay: ReplayResult,
    episodes: tuple[PublicEpisode, ...],
    provider_usage: object,
) -> tuple[dict[str, object], bool]:
    demonstrations = tuple(
        episode for episode in episodes if episode.outcome.collection == "demonstrations"
    )
    negatives = tuple(
        episode for episode in episodes if episode.outcome.collection == "negatives"
    )
    observed_behaviors = {
        "direct_lookup": _has_direct_lookup(demonstrations),
        "authorized_mutation": _has_authorized_mutation(demonstrations),
        "successful_recovery": _has_successful_recovery(demonstrations),
    }
    target_demonstrations_met = len(demonstrations) >= configuration.target_demonstrations
    attempt_ceiling_respected = len(episodes) <= configuration.task_attempt_limit
    minimum_behavior_examples_met = all(observed_behaviors.values())
    requirements_met = (
        attempt_ceiling_respected
        and minimum_behavior_examples_met
        and replay.aligned
    )
    failed_episodes = [
        {
            "candidate_id": episode.candidate_id,
            "episode_id": episode.episode_id,
            "reason_code": episode.outcome.reason_code or "unspecified_failure",
            "verification_reason_codes": (
                list(episode.verification.reason_codes) if episode.verification else []
            ),
        }
        for episode in negatives
    ]
    assessment_alignment = {
        "executed_episode_count": sum(
            episode.verification is not None for episode in episodes
        ),
        "passed_assessment_count": sum(
            episode.verification is not None and episode.verification.passed
            for episode in demonstrations
        ),
        "admitted_episode_count": sum(
            episode.admission.status == "admitted" for episode in episodes
        ),
    }
    report: dict[str, object] = {
        "schema_version": "contacts_live_pilot_report_v1",
        "collection_purpose": "diagnostic_only",
        "authorization": authorization.public_record(),
        "pilot_configuration": configuration.model_dump(mode="json"),
        "preauthorization_rehearsal": {
            "source_fingerprint": rehearsal.source_fingerprint,
            "known_task_capacity": rehearsal.known_task_capacity,
            "capacity_status": rehearsal.capacity_status,
            "task_attempt_limit": rehearsal.task_attempt_limit,
            "diagnostic_semantic_groups": list(rehearsal.diagnostic_semantic_groups),
            "diagnostic_grounding_groups": list(rehearsal.diagnostic_grounding_groups),
        },
        "attempt_summary": {
            "target_demonstrations": configuration.target_demonstrations,
            "task_attempt_limit": configuration.task_attempt_limit,
            "attempted": len(episodes),
            "demonstrations": len(demonstrations),
            "negatives": len(negatives),
            "target_demonstrations_met": target_demonstrations_met,
        },
        "observed_behaviors": observed_behaviors,
        "feasibility_evidence": {
            "attempt_ceiling_respected": attempt_ceiling_respected,
            "minimum_behavior_examples_met": minimum_behavior_examples_met,
            "replay_aligned": replay.aligned,
        },
        "deterministic_assessment_alignment": assessment_alignment,
        "failed_episodes": failed_episodes,
        "provider_usage": provider_usage,
        "offline_replay": {
            "aligned": replay.aligned,
            "episode_count": len(replay.episode_results),
            "report_file": replay.report_path.name,
        },
        "artifacts": {
            "demonstrations_file": run.demonstrations_path.name,
            "negatives_file": run.negatives_path.name,
            "provider_usage_file": run.provider_usage_path.name,
            "manifest_file": run.manifest_path.name,
        },
        "diagnostic_outcome": (
            "required_behaviors_observed" if requirements_met else "insufficient_evidence"
        ),
    }
    return report, requirements_met


def _successful(episode: PublicEpisode) -> bool:
    return (
        episode.outcome.collection == "demonstrations"
        and episode.admission.status == "admitted"
        and episode.verification is not None
        and episode.verification.passed
    )


def _has_direct_lookup(episodes: tuple[PublicEpisode, ...]) -> bool:
    return any(
        _successful(episode)
        and episode.verification is not None
        and episode.verification.structural_key == "contacts.lookup.direct"
        for episode in episodes
    )


def _has_authorized_mutation(episodes: tuple[PublicEpisode, ...]) -> bool:
    return any(
        _successful(episode)
        and episode.mutation_authorization == "authorized"
        and episode.verification is not None
        and episode.verification.structural_key.startswith("contacts.followup.")
        and any(
            event.event_type == "state_change" and event.tool_name == "record_followup"
            for event in episode.events
        )
        for episode in episodes
    )


def _has_successful_recovery(episodes: tuple[PublicEpisode, ...]) -> bool:
    return any(
        _successful(episode)
        and episode.verification is not None
        and episode.verification.structural_key.endswith(".recovery")
        and any(
            event.event_type == "error" and event.error_code == "contact_not_found"
            for event in episode.events
        )
        for episode in episodes
    )
