"""Serial, bounded Agent rollout engine for the provisional Agent-first seam."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, JsonValue, ValidationError

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.domain import (
    CompilationRejection,
    CompiledTask,
    DomainEpisode,
    DomainRun,
    FrozenInitialState,
    TaskProposal,
    TaskSlot,
    ToolExecutionResult,
)
from agent_synthesis.episode import (
    AdmissionRecord,
    EpisodeAssessment,
    EpisodeEvent,
    EpisodeOutcome,
    ExecutionTrace,
    ModelLineage,
    PublicEpisode,
    PublicTask,
    RoleLineage,
    ToolDefinition,
    bounded_event_for_public_tools,
    sanitized_episode_record,
    sanitized_public_task,
)
from agent_synthesis.ledger import (
    AllocatedSlotRecord,
    PrivateLedger,
    ProviderRequestRecord,
    TaskCaseRecord,
)
from agent_synthesis.manifest import build_manifest, write_manifest
from agent_synthesis.model import (
    AgentRequest,
    FinalResponseDecision,
    GenerationResponse,
    JsonModelAdapter,
    JsonModelRequest,
    JsonModelResponse,
    ModelCallError,
    ModelRole,
    TaskGenerationRequest,
    TokenUsage,
    ToolCallDecision,
    parse_agent_decision,
)
from agent_synthesis.registry import AdapterRegistry


@dataclass(frozen=True)
class RunResult:
    """Paths and collection counts from one completed local synthesis trace."""

    run_directory: Path
    demonstrations_path: Path
    negatives_path: Path
    provider_usage_path: Path
    manifest_path: Path
    private_ledger_path: Path
    demonstration_count: int
    negative_count: int


@dataclass(frozen=True)
class ReplayEpisodeResult:
    """One provider-free comparison of saved and re-executed Episode evidence."""

    episode_id: str
    sequence: int
    status: Literal[
        "aligned",
        "observation_drift",
        "assessment_drift",
        "observation_and_assessment_drift",
        "not_executed",
        "replay_failed",
    ]
    observation_drift: bool
    assessment_drift: bool


@dataclass(frozen=True)
class ReplayResult:
    """A deterministic offline replay report written alongside a completed run."""

    run_directory: Path
    report_path: Path
    episode_results: tuple[ReplayEpisodeResult, ...]

    @property
    def aligned(self) -> bool:
        return all(result.status in {"aligned", "not_executed"} for result in self.episode_results)


@dataclass(frozen=True)
class _EpisodeContext:
    """Core-owned stable identity shared by one terminal record."""

    configuration: RunConfiguration
    domain_version: str
    sequence: int


@dataclass(frozen=True)
class _LogicalCallResult:
    """The charged physical records and one bounded logical request outcome."""

    response: JsonModelResponse | None
    records: tuple[ProviderRequestRecord, ...]
    error_code: str | None


class SynthesisEngine:
    """Run registered Domains and JSON models with serial durable accounting."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def run(
        self,
        configuration: RunConfiguration | Mapping[str, object],
        output_directory: Path,
    ) -> RunResult:
        """Compile allocated slots and execute bounded Agent Episodes."""

        config = _validated_configuration(configuration)
        domain = self._registry.domain(config.domain_id)
        model = self._registry.model(config.model_id)
        output_directory.mkdir(parents=True, exist_ok=True)
        private_ledger_path = output_directory / ".private" / "ledger.sqlite3"
        demonstrations_path = output_directory / "demonstrations.jsonl"
        negatives_path = output_directory / "negatives.jsonl"
        provider_usage_path = output_directory / "provider_usage.json"
        manifest_path = output_directory / "manifest.json"

        ledger = PrivateLedger.create(private_ledger_path)
        try:
            domain_run = domain.open_run(config)
            ledger.record_run_metadata(config, domain_version=domain.domain_version)
            initial_state = domain_run.freeze_initial_state()
            ledger.record_initial_state(initial_state)
            slots = _bounded_slots(domain_run.slots(config.slot_limit), config.slot_limit)
            allocated = tuple(
                AllocatedSlotRecord.from_slot(sequence=sequence, slot=slot)
                for sequence, slot in enumerate(slots, start=1)
            )
            ledger.record_allocated_slots(allocated)

            demonstrations: list[PublicEpisode] = []
            negatives: list[PublicEpisode] = []
            admitted_semantic_keys: set[str] = set()

            for batch in _batches(allocated, config.generation_batch_size):
                generation = _call_model(
                    ledger=ledger,
                    model=model,
                    configuration=config,
                    request=TaskGenerationRequest(
                        slots=tuple(record.to_slot() for record in batch),
                        timeout_seconds=config.timeout_seconds,
                        max_response_bytes=config.max_response_bytes,
                        max_output_tokens=config.max_output_tokens,
                    ),
                    logical_request_id=(
                        f"task_generation:{batch[0].sequence:04d}-{batch[-1].sequence:04d}"
                    ),
                    sequence=None,
                    request_kind="initial",
                )
                contexts = {
                    record.sequence: _EpisodeContext(
                        configuration=config,
                        domain_version=domain.domain_version,
                        sequence=record.sequence,
                    )
                    for record in batch
                }
                if generation.response is None:
                    for record in batch:
                        negatives.append(
                            _pre_execution_negative(
                                context=contexts[record.sequence],
                                task=_fallback_public_task(record.to_slot()),
                                reason_code=generation.error_code
                                or "generation_failed",
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                    continue

                proposals, generation_reason = _mapped_generation_proposals(
                    generation.response,
                    batch,
                )
                if proposals is None:
                    assert generation_reason is not None
                    for record in batch:
                        negatives.append(
                            _pre_execution_negative(
                                context=contexts[record.sequence],
                                task=_fallback_public_task(record.to_slot()),
                                reason_code=generation_reason,
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                    continue

                for record in batch:
                    context = contexts[record.sequence]
                    try:
                        compilation = domain_run.compile(
                            record.to_slot(),
                            TaskProposal(content=proposals[record.slot_id]),
                        )
                    except Exception:  # noqa: BLE001 - Domain adapter errors must be bounded.
                        negatives.append(
                            _pre_execution_negative(
                                context=context,
                                task=_fallback_public_task(record.to_slot()),
                                reason_code="domain_compilation_failure",
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                        continue
                    if isinstance(compilation, CompilationRejection):
                        negatives.append(
                            _compilation_negative(
                                context=context,
                                rejection=compilation,
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                        continue
                    if not isinstance(compilation, CompiledTask):
                        negatives.append(
                            _pre_execution_negative(
                                context=context,
                                task=_fallback_public_task(record.to_slot()),
                                reason_code="domain_compilation_failure",
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                        continue

                    # The complete public/private case is committed before any Agent request.
                    ledger.record_task_case(
                        sequence=record.sequence,
                        slot_id=record.slot_id,
                        task=compilation,
                    )
                    if compilation.semantic_key in admitted_semantic_keys:
                        negatives.append(
                            _pre_execution_negative(
                                context=context,
                                task=compilation.public_task,
                                reason_code="duplicate_semantic_task",
                                lineage=_model_lineage(model, generation.records),
                            )
                        )
                        continue
                    episode = _run_agent_episode(
                        domain_run=domain_run,
                        task=compilation,
                        frozen_initial_state=initial_state,
                        context=context,
                        model=model,
                        ledger=ledger,
                        generation_records=generation.records,
                    )
                    if episode.outcome.collection == "demonstrations":
                        demonstrations.append(episode)
                        admitted_semantic_keys.add(compilation.semantic_key)
                    else:
                        negatives.append(episode)

            _write_collection(demonstrations_path, demonstrations)
            _write_collection(negatives_path, negatives)
            _write_provider_usage(provider_usage_path, ledger.provider_requests())
            manifest = build_manifest(
                run_id=config.run_id,
                configuration=config.normalized_public_record(),
                source_fingerprint=initial_state.fingerprint,
                artifact_paths=(
                    demonstrations_path,
                    negatives_path,
                    provider_usage_path,
                ),
            )
            write_manifest(manifest_path, manifest)
        finally:
            ledger.close()

        return RunResult(
            run_directory=output_directory,
            demonstrations_path=demonstrations_path,
            negatives_path=negatives_path,
            provider_usage_path=provider_usage_path,
            manifest_path=manifest_path,
            private_ledger_path=private_ledger_path,
            demonstration_count=len(demonstrations),
            negative_count=len(negatives),
        )

    def replay(self, run_directory: Path) -> ReplayResult:
        """Re-execute saved tool calls against frozen state without calling a model."""

        private_ledger_path = run_directory / ".private" / "ledger.sqlite3"
        ledger = PrivateLedger.open(private_ledger_path)
        try:
            metadata = ledger.run_metadata()
            configuration = metadata.configuration_model()
            frozen_initial_state = ledger.initial_state()
            task_cases = {record.sequence: record for record in ledger.task_cases()}
        finally:
            ledger.close()

        domain = self._registry.domain(configuration.domain_id)
        if domain.domain_version != metadata.domain_version:
            raise ValueError("replay Domain version does not match the saved run")
        domain_run = domain.open_run(configuration)
        episodes = _read_public_episodes(
            run_directory / "demonstrations.jsonl",
            run_directory / "negatives.jsonl",
        )
        results: list[ReplayEpisodeResult] = []
        for saved_episode in episodes:
            case = task_cases.get(saved_episode.sequence)
            if case is None:
                results.append(
                    ReplayEpisodeResult(
                        episode_id=saved_episode.episode_id,
                        sequence=saved_episode.sequence,
                        status="not_executed",
                        observation_drift=False,
                        assessment_drift=False,
                    )
                )
                continue
            results.append(
                _replay_episode(
                    domain_run=domain_run,
                    saved_episode=saved_episode,
                    case=case,
                    frozen_initial_state=frozen_initial_state,
                )
            )
        report_path = run_directory / "replay_report.json"
        _write_replay_report(report_path, tuple(results))
        return ReplayResult(
            run_directory=run_directory,
            report_path=report_path,
            episode_results=tuple(results),
        )


def _run_agent_episode(
    *,
    domain_run: DomainRun,
    task: CompiledTask,
    frozen_initial_state: FrozenInitialState,
    context: _EpisodeContext,
    model: JsonModelAdapter,
    ledger: PrivateLedger,
    generation_records: tuple[ProviderRequestRecord, ...],
) -> PublicEpisode:
    try:
        episode = domain_run.open_episode(task, frozen_initial_state)
    except Exception:  # noqa: BLE001 - Domain adapter errors must be bounded.
        return _execution_episode(
            context=context,
            task=task.public_task,
            trace=_incomplete_trace("episode_open_failure"),
            assessment=_incomplete_assessment("episode_open_failure"),
            lineage=_model_lineage(model, generation_records),
            terminal_reason="episode_open_failure",
        )

    safe_task = sanitized_public_task(task.public_task)
    events: list[EpisodeEvent] = []
    records: list[ProviderRequestRecord] = list(generation_records)
    mutation_authorization: Literal["not_applicable", "authorized", "rejected"] = (
        "not_applicable"
    )
    repairs_used = 0
    repair_pending = False
    steps_used = 0
    terminal_reason: str | None = None
    final_response_received = False

    while steps_used < context.configuration.step_limit:
        request = AgentRequest(
            task=safe_task,
            observable_history=tuple(events),
            remaining_step_budget=context.configuration.step_limit - steps_used,
            timeout_seconds=context.configuration.timeout_seconds,
            max_response_bytes=context.configuration.max_response_bytes,
            max_output_tokens=context.configuration.max_output_tokens,
        )
        request_kind: Literal["initial", "repair"] = "repair" if repair_pending else "initial"
        call = _call_model(
            ledger=ledger,
            model=model,
            configuration=context.configuration,
            request=request,
            logical_request_id=(
                f"agent:{context.sequence:04d}:step:{steps_used + 1}:repair:{repairs_used}"
            ),
            sequence=context.sequence,
            request_kind=request_kind,
        )
        records.extend(call.records)
        if call.response is None:
            terminal_reason = call.error_code or "agent_request_failed"
            events.append(EpisodeEvent(event_type="error", error_code=terminal_reason))
            break

        try:
            decision = parse_agent_decision(call.response.content)
        except (ValidationError, ValueError):
            events.append(EpisodeEvent(event_type="error", error_code="malformed_agent_decision"))
            if repairs_used >= context.configuration.decision_repair_limit:
                terminal_reason = "malformed_agent_decision"
                break
            repairs_used += 1
            repair_pending = True
            continue

        steps_used += 1
        repair_pending = False
        if isinstance(decision, FinalResponseDecision):
            events.append(
                bounded_event_for_public_tools(
                    EpisodeEvent(event_type="final_response", content=decision.content),
                    safe_task.tools,
                )
            )
            final_response_received = True
            break

        assert isinstance(decision, ToolCallDecision)
        action = bounded_event_for_public_tools(
            EpisodeEvent(
                event_type="action",
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            ),
            safe_task.tools,
        )
        events.append(action)
        tool_event, authorization = _execute_tool_decision(
            episode=episode,
            task=safe_task,
            decision=decision,
        )
        events.append(tool_event)
        if authorization == "authorized":
            mutation_authorization = "authorized"
        elif authorization == "rejected":
            mutation_authorization = "rejected"
            terminal_reason = "unauthorized_mutation"
            break

    if not final_response_received and terminal_reason is None:
        terminal_reason = "step_budget_exhausted"
        events.append(EpisodeEvent(event_type="error", error_code=terminal_reason))
    trace = ExecutionTrace(
        mutation_authorization=mutation_authorization,
        events=tuple(events),
    )
    assessment = _assess_episode(episode, trace, terminal_reason)
    return _execution_episode(
        context=context,
        task=task.public_task,
        trace=trace,
        assessment=assessment,
        lineage=_model_lineage(model, tuple(records)),
        terminal_reason=terminal_reason,
    )


def _execute_tool_decision(
    *,
    episode: DomainEpisode,
    task: PublicTask,
    decision: ToolCallDecision,
) -> tuple[EpisodeEvent, Literal["not_applicable", "authorized", "rejected"]]:
    tool = next((tool for tool in task.tools if tool.name == decision.tool_name), None)
    if tool is None:
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=decision.tool_name,
                error_code="unknown_tool",
            ),
            "not_applicable",
        )
    if not _valid_tool_arguments(tool, decision.arguments):
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code="invalid_tool_arguments",
            ),
            "not_applicable",
        )
    try:
        result = _validated_model(
            episode.execute_tool_call(tool.name, decision.arguments),
            ToolExecutionResult,
        )
    except Exception:  # noqa: BLE001 - Domain tool errors become observations.
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code="tool_failure",
            ),
            "not_applicable",
        )
    if result.result_type == "observation":
        assert result.observation is not None
        return (
            bounded_event_for_public_tools(
                EpisodeEvent(
                    event_type="observation",
                    tool_name=tool.name,
                    observation=result.observation,
                ),
                task.tools,
            ),
            "not_applicable",
        )
    if result.result_type == "state_change":
        assert result.change is not None
        return (
            bounded_event_for_public_tools(
                EpisodeEvent(
                    event_type="state_change",
                    tool_name=tool.name,
                    change=result.change,
                ),
                task.tools,
            ),
            "authorized",
        )
    assert result.error_code is not None
    if result.result_type == "unauthorized_mutation":
        return (
            EpisodeEvent(
                event_type="error",
                tool_name=tool.name,
                error_code=result.error_code,
            ),
            "rejected",
        )
    return (
        EpisodeEvent(
            event_type="error",
            tool_name=tool.name,
            error_code=result.error_code,
        ),
        "not_applicable",
    )


def _assess_episode(
    episode: DomainEpisode,
    trace: ExecutionTrace,
    terminal_reason: str | None,
) -> EpisodeAssessment:
    if terminal_reason is not None:
        return _incomplete_assessment(terminal_reason)
    try:
        return _validated_model(episode.assess(trace), EpisodeAssessment)
    except Exception:  # noqa: BLE001 - Domain assessment errors remain negatives.
        return _incomplete_assessment("domain_assessment_failure")


def _call_model(
    *,
    ledger: PrivateLedger,
    model: JsonModelAdapter,
    configuration: RunConfiguration,
    request: JsonModelRequest,
    logical_request_id: str,
    sequence: int | None,
    request_kind: Literal["initial", "repair"],
) -> _LogicalCallResult:
    """Reserve every physical dispatch and retry only bounded transport failures."""

    records: list[ProviderRequestRecord] = []
    role_limit = (
        configuration.generation_request_limit
        if request.role == "task_generation"
        else configuration.agent_request_limit
    )
    for physical_attempt in range(configuration.transport_retry_limit + 1):
        reservation = ledger.reserve_provider_request(
            role=request.role,
            logical_request_id=logical_request_id,
            role_limit=role_limit,
            total_limit=configuration.total_request_limit,
            sequence=sequence,
            request_kind=request_kind,
        )
        if reservation is None:
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_request_budget_exhausted",
            )
        try:
            raw_response = model.complete(request)
            response = _validated_model(raw_response, JsonModelResponse)
            if len(response.model_dump_json().encode("utf-8")) > request.max_response_bytes:
                raise ModelCallError(
                    "response_bytes_exceeded",
                    retryable=False,
                    response_hash=response.effective_response_hash,
                    usage=response.usage,
                )
            if (
                response.usage is not None
                and response.usage.output_tokens is not None
                and response.usage.output_tokens > request.max_output_tokens
            ):
                raise ModelCallError(
                    "response_tokens_exceeded",
                    retryable=False,
                    response_hash=response.effective_response_hash,
                    usage=response.usage,
                )
        except ModelCallError as error:
            finished = ledger.finish_provider_request(
                reservation.request_id,
                status="failed",
                response_hash=error.response_hash,
                usage=error.usage,
                error_code=error.error_code,
            )
            records.append(finished)
            if error.retryable and physical_attempt < configuration.transport_retry_limit:
                continue
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code=error.error_code,
            )
        except (ValidationError, TypeError, ValueError):
            finished = ledger.finish_provider_request(
                reservation.request_id,
                status="failed",
                error_code="provider_response_malformed",
            )
            records.append(finished)
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_response_malformed",
            )
        except Exception:  # noqa: BLE001 - Adapter failures must not escape the run.
            finished = ledger.finish_provider_request(
                reservation.request_id,
                status="failed",
                error_code="provider_adapter_failure",
            )
            records.append(finished)
            return _LogicalCallResult(
                response=None,
                records=tuple(records),
                error_code="provider_adapter_failure",
            )
        finished = ledger.finish_provider_request(
            reservation.request_id,
            status="completed",
            response_hash=response.effective_response_hash,
            usage=response.usage,
        )
        records.append(finished)
        return _LogicalCallResult(response=response, records=tuple(records), error_code=None)
    raise AssertionError("bounded model loop must return")


def _mapped_generation_proposals(
    response: JsonModelResponse,
    batch: tuple[AllocatedSlotRecord, ...],
) -> tuple[dict[str, str] | None, Literal["generation_malformed_output", "generation_slot_mismatch"] | None]:
    try:
        generated = GenerationResponse.model_validate(response.content)
    except ValidationError:
        return None, "generation_malformed_output"
    expected_ids = {record.slot_id for record in batch}
    actual_ids = [proposal.slot_id for proposal in generated.proposals]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        return None, "generation_slot_mismatch"
    return {proposal.slot_id: proposal.content for proposal in generated.proposals}, None


def _valid_tool_arguments(tool: ToolDefinition, arguments: dict[str, JsonValue]) -> bool:
    schema = tool.input_schema
    if schema.get("type") != "object":
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        return False
    if any(name not in arguments for name in required):
        return False
    if any(name not in properties for name in arguments):
        return False
    return all(
        isinstance(property_schema, dict)
        and _matches_schema(arguments[name], property_schema)
        for name, property_schema in properties.items()
        if name in arguments
    )


def _matches_schema(value: JsonValue, schema: dict[str, object]) -> bool:
    expected_type = schema.get("type")
    if expected_type == "string":
        if not isinstance(value, str):
            return False
        enum = schema.get("enum")
        return not isinstance(enum, list) or value in enum
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return False


def _execution_episode(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    trace: ExecutionTrace,
    assessment: EpisodeAssessment,
    lineage: ModelLineage,
    terminal_reason: str | None,
) -> PublicEpisode:
    admitted = (
        terminal_reason is None
        and assessment.passed
        and trace.mutation_authorization != "rejected"
    )
    reason_code = terminal_reason
    if not admitted and reason_code is None:
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
        mutation_authorization=trace.mutation_authorization,
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
        lineage=lineage,
    )


def _compilation_negative(
    *,
    context: _EpisodeContext,
    rejection: CompilationRejection,
    lineage: ModelLineage,
) -> PublicEpisode:
    return _pre_execution_negative(
        context=context,
        task=rejection.public_task,
        reason_code=rejection.reason_code,
        lineage=lineage,
    )


def _pre_execution_negative(
    *,
    context: _EpisodeContext,
    task: PublicTask,
    reason_code: str,
    lineage: ModelLineage,
) -> PublicEpisode:
    return PublicEpisode(
        episode_id=_episode_id(context.configuration.run_id, context.sequence),
        candidate_id=_candidate_id(context.configuration.run_id, context.sequence),
        sequence=context.sequence,
        domain_id=context.configuration.domain_id,
        domain_version=context.domain_version,
        task=task,
        events=(),
        outcome=EpisodeOutcome(
            collection="negatives",
            status="rejected_before_execution",
            reason_code=reason_code,
        ),
        admission=AdmissionRecord(
            mode=context.configuration.admission_mode,
            status="rejected",
        ),
        lineage=lineage,
    )


def _incomplete_trace(reason_code: str) -> ExecutionTrace:
    return ExecutionTrace(
        mutation_authorization="not_applicable",
        events=(EpisodeEvent(event_type="error", error_code=reason_code),),
    )


def _incomplete_assessment(reason_code: str) -> EpisodeAssessment:
    return EpisodeAssessment(
        passed=False,
        checks=(),
        reason_codes=(reason_code,),
        coverage_tags=(),
        structural_key="incomplete",
    )


def _fallback_public_task(_slot: TaskSlot) -> PublicTask:
    """A bounded public negative when generation fails before Domain compilation."""

    return PublicTask(
        instruction="Task generation failed before public task compilation.",
        tools=(
            ToolDefinition(
                name="unavailable",
                description="No executable tool is available before task compilation.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
            ),
        ),
    )


def _model_lineage(
    model: JsonModelAdapter,
    records: tuple[ProviderRequestRecord, ...],
) -> ModelLineage:
    by_role: dict[ModelRole, list[ProviderRequestRecord]] = defaultdict(list)
    for record in records:
        by_role[record.role].append(record)
    roles: list[RoleLineage] = []
    for role in ("task_generation", "agent"):
        role_records = by_role[role]
        if not role_records:
            continue
        usages = [record.usage for record in role_records]
        roles.append(
            RoleLineage(
                role=role,
                provider_id=model.provider_id,
                model_id=model.model_id,
                model_version=model.model_version,
                physical_request_count=len(role_records),
                retry_count=len(role_records)
                - len({record.logical_request_id for record in role_records}),
                response_hashes=tuple(
                    record.response_hash
                    for record in role_records
                    if record.response_hash is not None
                ),
                known_input_tokens=_known_token_total(usages, "input_tokens"),
                known_output_tokens=_known_token_total(usages, "output_tokens"),
                known_total_tokens=_known_token_total(usages, "total_tokens"),
                unknown_usage_count=sum(
                    1
                    for usage in usages
                    if usage is None or usage.total_tokens is None
                ),
            )
        )
    return ModelLineage(
        model_id=model.model_id,
        model_version=model.model_version,
        roles=tuple(roles),
    )


def _known_token_total(
    usages: Sequence[TokenUsage | None],
    field_name: Literal["input_tokens", "output_tokens", "total_tokens"],
) -> int | None:
    values: list[int] = []
    for usage in usages:
        if usage is None:
            continue
        value = getattr(usage, field_name)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def _replay_episode(
    *,
    domain_run: DomainRun,
    saved_episode: PublicEpisode,
    case: TaskCaseRecord,
    frozen_initial_state: FrozenInitialState,
) -> ReplayEpisodeResult:
    """Rebuild one saved case and compare its tool observations and assessment."""

    try:
        task = domain_run.restore_task_case(
            public_task=case.public_task,
            semantic_key=case.semantic_key,
            private_case_bytes=case.private_case_bytes(),
        )
        episode = domain_run.open_replay_episode(task, frozen_initial_state)
        trace, observation_drift = _replay_trace(
            episode=episode,
            task=task.public_task,
            saved_events=saved_episode.events,
        )
        if trace.mutation_authorization != saved_episode.mutation_authorization:
            observation_drift = True
        assessment = _replay_assessment(episode, trace, saved_episode.verification)
        assessment_drift = _assessment_drift(saved_episode.verification, assessment)
    except Exception:  # noqa: BLE001 - Replay reports Domain failures without providers.
        return ReplayEpisodeResult(
            episode_id=saved_episode.episode_id,
            sequence=saved_episode.sequence,
            status="replay_failed",
            observation_drift=True,
            assessment_drift=True,
        )
    status: Literal[
        "aligned",
        "observation_drift",
        "assessment_drift",
        "observation_and_assessment_drift",
    ]
    if observation_drift and assessment_drift:
        status = "observation_and_assessment_drift"
    elif observation_drift:
        status = "observation_drift"
    elif assessment_drift:
        status = "assessment_drift"
    else:
        status = "aligned"
    return ReplayEpisodeResult(
        episode_id=saved_episode.episode_id,
        sequence=saved_episode.sequence,
        status=status,
        observation_drift=observation_drift,
        assessment_drift=assessment_drift,
    )


def _replay_trace(
    *,
    episode: DomainEpisode,
    task: PublicTask,
    saved_events: tuple[EpisodeEvent, ...],
) -> tuple[ExecutionTrace, bool]:
    safe_task = sanitized_public_task(task)
    actual_events: list[EpisodeEvent] = []
    observation_drift = False
    mutation_authorization: Literal["not_applicable", "authorized", "rejected"] = (
        "not_applicable"
    )
    index = 0
    while index < len(saved_events):
        event = saved_events[index]
        if event.event_type != "action":
            actual_events.append(event)
            index += 1
            continue
        actual_events.append(event)
        if event.tool_name is None:
            observation_drift = True
            index += 1
            continue
        decision = ToolCallDecision(
            type="tool_call",
            tool_name=event.tool_name,
            arguments=event.arguments or {},
        )
        actual_result, authorization = _execute_tool_decision(
            episode=episode,
            task=safe_task,
            decision=decision,
        )
        if authorization == "authorized":
            mutation_authorization = "authorized"
        elif authorization == "rejected":
            mutation_authorization = "rejected"
        if index + 1 >= len(saved_events):
            observation_drift = True
            actual_events.append(actual_result)
            index += 1
            continue
        expected_result = saved_events[index + 1]
        actual_events.append(actual_result)
        if expected_result != actual_result:
            observation_drift = True
        index += 2
    return (
        ExecutionTrace(
            mutation_authorization=mutation_authorization,
            events=tuple(actual_events),
        ),
        observation_drift,
    )


def _replay_assessment(
    episode: DomainEpisode,
    trace: ExecutionTrace,
    saved_assessment: EpisodeAssessment | None,
) -> EpisodeAssessment | None:
    if saved_assessment is None:
        return None
    if saved_assessment.structural_key == "incomplete":
        reason_code = saved_assessment.reason_codes[0] if saved_assessment.reason_codes else "replay_incomplete"
        return _incomplete_assessment(reason_code)
    try:
        return _validated_model(episode.assess(trace), EpisodeAssessment)
    except Exception:  # noqa: BLE001 - Replay assessment errors become drift evidence.
        return _incomplete_assessment("domain_assessment_failure")


def _assessment_drift(
    saved: EpisodeAssessment | None,
    replayed: EpisodeAssessment | None,
) -> bool:
    if saved is None or replayed is None:
        return saved is not replayed
    return saved.model_dump(mode="json") != replayed.model_dump(mode="json")


def _read_public_episodes(*paths: Path) -> tuple[PublicEpisode, ...]:
    episodes: list[PublicEpisode] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"missing public Episode collection: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                episodes.append(PublicEpisode.model_validate_json(line))
    return tuple(sorted(episodes, key=lambda episode: episode.sequence))


def _write_replay_report(
    path: Path,
    results: tuple[ReplayEpisodeResult, ...],
) -> None:
    payload = {
        "schema_version": "agent_replay_report_v1",
        "aligned": all(result.status in {"aligned", "not_executed"} for result in results),
        "episodes": [
            {
                "episode_id": result.episode_id,
                "sequence": result.sequence,
                "status": result.status,
                "observation_drift": result.observation_drift,
                "assessment_drift": result.assessment_drift,
            }
            for result in results
        ],
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
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


def _write_provider_usage(
    path: Path,
    records: tuple[ProviderRequestRecord, ...],
) -> None:
    by_role: dict[ModelRole, list[ProviderRequestRecord]] = defaultdict(list)
    for record in records:
        by_role[record.role].append(record)
    roles = {
        role: _usage_summary(role_records)
        for role, role_records in sorted(by_role.items())
    }
    payload = {
        "schema_version": "agent_provider_usage_v1",
        "total_physical_requests": len(records),
        "roles": roles,
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _usage_summary(records: list[ProviderRequestRecord]) -> dict[str, object]:
    usages = [record.usage for record in records]
    return {
        "physical_request_count": len(records),
        "retry_count": len(records)
        - len({record.logical_request_id for record in records}),
        "repair_request_count": sum(
            1 for record in records if record.request_kind == "repair"
        ),
        "known_input_tokens": _known_token_total(usages, "input_tokens"),
        "known_output_tokens": _known_token_total(usages, "output_tokens"),
        "known_total_tokens": _known_token_total(usages, "total_tokens"),
        "unknown_usage_count": sum(
            1 for usage in usages if usage is None or usage.total_tokens is None
        ),
    }


def _validated_configuration(
    configuration: RunConfiguration | Mapping[str, object],
) -> RunConfiguration:
    if isinstance(configuration, RunConfiguration):
        return configuration
    return RunConfiguration.model_validate(configuration)


def _validated_model[ValidatedModel: BaseModel](
    value: object,
    model_type: type[ValidatedModel],
) -> ValidatedModel:
    if isinstance(value, model_type):
        return value
    return model_type.model_validate(value)


def _bounded_slots(slots: tuple[TaskSlot, ...], limit: int) -> tuple[TaskSlot, ...]:
    bounded = slots[:limit]
    slot_ids = tuple(slot.slot_id for slot in bounded)
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("Domain emitted duplicate deterministic slot ids")
    return bounded


def _batches[
    Item
](items: tuple[Item, ...], size: int) -> tuple[tuple[Item, ...], ...]:
    return tuple(tuple(items[index : index + size]) for index in range(0, len(items), size))


def _candidate_id(run_id: str, sequence: int) -> str:
    return f"candidate_{run_id}_{sequence:04d}"


def _episode_id(run_id: str, sequence: int) -> str:
    return f"episode_{run_id}_{sequence:04d}"
