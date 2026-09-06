"""The library-first synthesis engine for the provisional Agent-first seam."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.domain import (
    CompilationRejection,
    CompiledTask,
    TaskGenerationRequest,
    TaskProposal,
    TaskSlot,
)
from agent_synthesis.episode import (
    AdmissionRecord,
    EpisodeAssessment,
    EpisodeOutcome,
    ExecutionTrace,
    ModelLineage,
    PublicEpisode,
    PublicTask,
    sanitized_episode_record,
)
from agent_synthesis.ledger import PrivateLedger
from agent_synthesis.manifest import build_manifest, write_manifest
from agent_synthesis.registry import AdapterRegistry


@dataclass(frozen=True)
class RunResult:
    """Paths and collection counts from one completed local synthesis trace."""

    run_directory: Path
    demonstrations_path: Path
    negatives_path: Path
    manifest_path: Path
    private_ledger_path: Path
    demonstration_count: int
    negative_count: int


@dataclass(frozen=True)
class _EpisodeContext:
    """Core-owned identity and sanitized lineage shared by one terminal record."""

    configuration: RunConfiguration
    domain_version: str
    lineage: ModelLineage
    sequence: int


class SynthesisEngine:
    """Run registered adapters while retaining core-owned persistence and export."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def run(
        self,
        configuration: RunConfiguration | Mapping[str, object],
        output_directory: Path,
    ) -> RunResult:
        """Run one bounded deterministic trace and write its public artifacts."""

        config = _validated_configuration(configuration)
        domain = self._registry.domain(config.domain_id)
        model = self._registry.model(config.model_id)
        lineage = ModelLineage(model_id=model.model_id, model_version=model.model_version)
        output_directory.mkdir(parents=True, exist_ok=True)
        private_ledger_path = output_directory / ".private" / "ledger.sqlite3"
        demonstrations_path = output_directory / "demonstrations.jsonl"
        negatives_path = output_directory / "negatives.jsonl"
        manifest_path = output_directory / "manifest.json"

        ledger = PrivateLedger.create(private_ledger_path)
        try:
            domain_run = domain.open_run(config)
            initial_state = domain_run.freeze_initial_state()
            ledger.record_initial_state(initial_state)
            slots = _bounded_slots(domain_run.slots(config.slot_limit), config.slot_limit)
            demonstrations: list[PublicEpisode] = []
            negatives: list[PublicEpisode] = []

            for sequence, slot in enumerate(slots, start=1):
                context = _EpisodeContext(
                    configuration=config,
                    domain_version=domain.domain_version,
                    lineage=lineage,
                    sequence=sequence,
                )
                proposal = _validated_model(
                    model.propose(
                        TaskGenerationRequest(
                            slot_id=slot.slot_id,
                            proposal_prompt=slot.proposal_prompt,
                        )
                    ),
                    TaskProposal,
                )
                compilation = domain_run.compile(slot, proposal)
                if isinstance(compilation, CompilationRejection):
                    negatives.append(
                        _compilation_negative(
                            context=context,
                            rejection=compilation,
                        )
                    )
                    continue
                if not isinstance(compilation, CompiledTask):
                    raise TypeError("Domain compilation must return CompiledTask or CompilationRejection")

                ledger.record_task_case(
                    sequence=sequence,
                    slot_id=slot.slot_id,
                    task=compilation,
                )
                episode = domain_run.open_episode(compilation)
                trace = _validated_model(episode.execute(), ExecutionTrace)
                assessment = _validated_model(episode.assess(trace), EpisodeAssessment)
                record = _execution_episode(
                    context=context,
                    task=compilation.public_task,
                    trace=trace,
                    assessment=assessment,
                )
                if record.outcome.collection == "demonstrations":
                    demonstrations.append(record)
                else:
                    negatives.append(record)

            _write_collection(demonstrations_path, demonstrations)
            _write_collection(negatives_path, negatives)
            manifest = build_manifest(
                run_id=config.run_id,
                configuration=config.normalized_public_record(),
                source_fingerprint=initial_state.fingerprint,
                artifact_paths=(demonstrations_path, negatives_path),
            )
            write_manifest(manifest_path, manifest)
        finally:
            ledger.close()

        return RunResult(
            run_directory=output_directory,
            demonstrations_path=demonstrations_path,
            negatives_path=negatives_path,
            manifest_path=manifest_path,
            private_ledger_path=private_ledger_path,
            demonstration_count=len(demonstrations),
            negative_count=len(negatives),
        )


def _validated_configuration(
    configuration: RunConfiguration | Mapping[str, object],
) -> RunConfiguration:
    if isinstance(configuration, RunConfiguration):
        return configuration
    return RunConfiguration.model_validate(configuration)


_ValidatedModel = TypeVar("_ValidatedModel", bound=BaseModel)


def _validated_model(
    value: object,
    model_type: type[_ValidatedModel],
) -> _ValidatedModel:
    if isinstance(value, model_type):
        return value
    return model_type.model_validate(value)


def _bounded_slots(slots: tuple[TaskSlot, ...], limit: int) -> tuple[TaskSlot, ...]:
    bounded = slots[:limit]
    slot_ids = tuple(slot.slot_id for slot in bounded)
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("Domain emitted duplicate deterministic slot ids")
    return bounded


def _compilation_negative(
    *,
    context: _EpisodeContext,
    rejection: CompilationRejection,
) -> PublicEpisode:
    return PublicEpisode(
        episode_id=_episode_id(context.configuration.run_id, context.sequence),
        candidate_id=_candidate_id(context.configuration.run_id, context.sequence),
        sequence=context.sequence,
        domain_id=context.configuration.domain_id,
        domain_version=context.domain_version,
        task=rejection.public_task,
        events=(),
        outcome=EpisodeOutcome(
            collection="negatives",
            status="rejected_before_execution",
            reason_code=rejection.reason_code,
        ),
        admission=AdmissionRecord(
            mode=context.configuration.admission_mode,
            status="rejected",
        ),
        lineage=context.lineage,
    )


def _execution_episode(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    trace: ExecutionTrace,
    assessment: EpisodeAssessment,
) -> PublicEpisode:
    admitted = assessment.passed and trace.mutation_authorization != "rejected"
    reason_code = None
    if not admitted:
        reason_code = (
            "unauthorized_mutation"
            if trace.mutation_authorization == "rejected"
            else assessment.reason_codes[0]
            if assessment.reason_codes
            else "deterministic_assessment_failed"
        )
    return PublicEpisode(
        episode_id=_episode_id(context.configuration.run_id, context.sequence),
        candidate_id=_candidate_id(context.configuration.run_id, context.sequence),
        sequence=context.sequence,
        domain_id=context.configuration.domain_id,
        domain_version=context.domain_version,
        task=task,
        events=trace.events,
        outcome=EpisodeOutcome(
            collection="demonstrations" if admitted else "negatives",
            status="succeeded" if admitted else "rejected_after_execution",
            reason_code=reason_code,
        ),
        verification=assessment,
        admission=AdmissionRecord(
            mode=context.configuration.admission_mode,
            status="admitted" if admitted else "rejected",
        ),
        lineage=context.lineage,
    )


def _write_collection(path: Path, episodes: list[PublicEpisode]) -> None:
    contents = "".join(
        json.dumps(
            sanitized_episode_record(episode),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for episode in episodes
    )
    path.write_text(contents, encoding="utf-8")


def _candidate_id(run_id: str, sequence: int) -> str:
    return f"candidate_{run_id}_{sequence:04d}"


def _episode_id(run_id: str, sequence: int) -> str:
    return f"episode_{run_id}_{sequence:04d}"
