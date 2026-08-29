"""Authorization and replay contracts for the live Workspace acceptance run.

The live acceptance boundary is intentionally separate from the deterministic
Workspace tracer.  It may record only the narrow provider task-contract JSON
needed to replay production parsing and membership admission.  Prompts,
provider envelopes, credentials, and unrestricted source material never cross
the freeze boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from synthesis.acceptance_replay import (
    AcceptanceAuthorization,
    AcceptanceEvidenceRecorder,
    AcceptancePipelineResult,
    AcceptancePreparation,
    AcceptanceReleaseEvidence,
    AcceptanceReplayContract,
    AcceptanceReplayError,
    AcceptanceReplayHarness,
    AcceptanceUsageObserver,
    BoundedSanitizedProvider as _NeutralBoundedSanitizedProvider,
    CoverageAssignmentEvidenceObserver as _NeutralCoverageAssignmentEvidenceObserver,
    SanitizedMutationJudgeUsageObserver as _NeutralSanitizedMutationJudgeUsageObserver,
    SanitizedProviderEvidenceRecorder as _NeutralSanitizedProviderEvidenceRecorder,
    bounded_reason as _neutral_bounded_reason,
    bounded_usage as _neutral_bounded_usage,
    build_coverage_attempt_observer_factory as _neutral_observer_factory,
    load_provider_evidence as _neutral_load_provider_evidence,
    replay_frozen_provider_evidence as _neutral_replay_frozen_provider_evidence,
    sanitize_provider_response as _neutral_sanitize_provider_response,
    sum_usage as _neutral_sum_usage,
    validate_provider_evidence as _neutral_validate_provider_evidence,
)


LIVE_ACCEPTANCE_SCHEMA_VERSION = "workspace_live_acceptance_v1"
LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION = "workspace_live_attempt_failure_v1"
LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION = "workspace_live_provider_evidence_v1"
SANITIZED_EVIDENCE_POLICY_VERSION = "workspace_sanitized_provider_evidence_v1"
PROVIDER_PARSER_VERSION = "domain_generation_parser_v1"
MAX_LIVE_GENERATOR_RETRIES = 3

_WORKSPACE_ACCEPTANCE_CONTRACT = AcceptanceReplayContract(
    acceptance_schema_version=LIVE_ACCEPTANCE_SCHEMA_VERSION,
    provider_evidence_schema_version=LIVE_PROVIDER_EVIDENCE_SCHEMA_VERSION,
    evidence_class="real_live",
    freeze_policy=SANITIZED_EVIDENCE_POLICY_VERSION,
    provider_parser_version=PROVIDER_PARSER_VERSION,
    replay_result_schema_version="workspace_live_replay_result_v1",
    expected_provider_id="openai_compatible",
    expected_provider_version="openai_compatible_client_v1",
    expected_judge_provider="openai_compatible",
    expected_judge_role="mutation_admission_judge",
    expected_judge_role_version="role_mutation_admission_judge_v1",
    provider_attempt_id_prefix="live_provider_attempt",
    mutation_judge_attempt_id_prefix="live_mutation_judge_attempt",
    preflight_failure_reason="live_mutation_judge_preflight_failed",
    pipeline_failure_reason="live_pipeline_failed",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,239}$")
_AUTHORIZATION_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")


class LiveWorkspaceAcceptanceError(AcceptanceReplayError):
    """A bounded failure at the authorized live-provider boundary."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


def sanitize_provider_response(response: object) -> dict[str, object]:
    try:
        return _neutral_sanitize_provider_response(response)
    except AcceptanceReplayError as exc:
        raise LiveWorkspaceAcceptanceError(exc.reason_code) from None



@dataclass(frozen=True)
class LiveWorkspaceAcceptanceAuthorization:
    """The operator's explicit, bounded authorization envelope."""

    approved: bool
    authorization_id: str
    candidate_budget: int
    attempt_budget: int
    generator_provider: str
    generator_model: str
    mutation_judge_provider: str
    mutation_judge_model: str
    generator_retry_limit: int = 2
    evidence_policy: str = SANITIZED_EVIDENCE_POLICY_VERSION

    def validate(
        self,
        *,
        profile: Mapping[str, object],
        plan_attempt_ceiling: int,
    ) -> None:
        if not self.approved:
            raise LiveWorkspaceAcceptanceError("live_provider_authorization_required")
        if _AUTHORIZATION_ID_RE.fullmatch(self.authorization_id) is None:
            raise LiveWorkspaceAcceptanceError("authorization_identity_invalid")
        if self.evidence_policy != SANITIZED_EVIDENCE_POLICY_VERSION:
            raise LiveWorkspaceAcceptanceError("sanitized_evidence_policy_required")
        for value in (self.candidate_budget, self.attempt_budget):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
        if (
            not isinstance(self.generator_retry_limit, int)
            or isinstance(self.generator_retry_limit, bool)
            or self.generator_retry_limit not in range(MAX_LIVE_GENERATOR_RETRIES + 1)
        ):
            raise LiveWorkspaceAcceptanceError("generator_retry_budget_invalid")
        if not isinstance(plan_attempt_ceiling, int) or plan_attempt_ceiling <= 0:
            raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
        if plan_attempt_ceiling > self.attempt_budget:
            raise LiveWorkspaceAcceptanceError("attempt_budget_exceeded")
        generation = profile.get("generation")
        seed = profile.get("seed")
        mutation = profile.get("mutation_admission")
        coverage = profile.get("coverage_profile")
        features = profile.get("features")
        if (
            profile.get("schema_version") != "run_profile_v4"
            or profile.get("profile_id") != "workspace_tasks_live_acceptance_rc"
            or profile.get("dataset_version")
            != "dataset_workspace_tasks_live_acceptance_rc_v1"
            or profile.get("profile_purpose") != "release_candidate"
            or not isinstance(generation, Mapping)
            or generation.get("mode") != "llm"
            or generation.get("target_candidate_count") != 24
            or not isinstance(seed, Mapping)
            or seed.get("domain") != "workspace_tasks_fixture"
            or seed.get("seed_id") != "seed_workspace_tasks_live_acceptance_rc_v1"
            or seed.get("task_taxonomy")
            != [
                "workspace_item_search",
                "workspace_task_creation",
                "workspace_comment_update",
            ]
            or not isinstance(coverage, Mapping)
            or coverage.get("profile_id") != "workspace_tasks_representative"
            or coverage.get("version") != "workspace_tasks_representative_v1"
            or coverage.get("target_accepted_sample_count") != 12
            or not isinstance(features, Mapping)
            or features.get("enable_branching") is not True
            or not isinstance(mutation, Mapping)
            or mutation.get("mode") != "enforce"
        ):
            raise LiveWorkspaceAcceptanceError("live_workspace_profile_invalid")
        target = generation.get("target_candidate_count")
        if (
            not isinstance(target, int)
            or isinstance(target, bool)
            or target <= 0
            or target > self.candidate_budget
        ):
            raise LiveWorkspaceAcceptanceError("candidate_budget_exceeded")
        judge = mutation.get("judge")
        if not isinstance(judge, Mapping):
            raise LiveWorkspaceAcceptanceError("mutation_judge_identity_required")
        if (
            self.generator_provider != "openai_compatible"
            or self.mutation_judge_provider != "openai_compatible"
            or judge.get("provider") != self.mutation_judge_provider
            or judge.get("role") != "mutation_admission_judge"
            or judge.get("model") != self.mutation_judge_model
            or not isinstance(self.generator_model, str)
            or _IDENTIFIER_RE.fullmatch(self.generator_model) is None
            or not isinstance(self.mutation_judge_model, str)
            or _IDENTIFIER_RE.fullmatch(self.mutation_judge_model) is None
            or self.generator_model == self.mutation_judge_model
        ):
            raise LiveWorkspaceAcceptanceError("mutation_judge_identity_not_independent")


    def to_record(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "authorization_id": self.authorization_id,
            "candidate_budget": self.candidate_budget,
            "attempt_budget": self.attempt_budget,
            "generator_provider": self.generator_provider,
            "generator_model": self.generator_model,
            "mutation_judge_provider": self.mutation_judge_provider,
            "mutation_judge_model": self.mutation_judge_model,
            "generator_retry_limit": self.generator_retry_limit,
            "evidence_policy": self.evidence_policy,
        }


def _bounded_usage(value: object) -> dict[str, int]:
    return _neutral_bounded_usage(value)


def _sum_usage(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return _neutral_sum_usage(records)


class SanitizedProviderEvidenceRecorder(_NeutralSanitizedProviderEvidenceRecorder):
    """Workspace-compatible facade over the pack-neutral evidence recorder."""

    def __init__(
        self,
        *,
        authorization: LiveWorkspaceAcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> None:
        super().__init__(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=mutation_judge_identity,
            contract=_WORKSPACE_ACCEPTANCE_CONTRACT,
        )

    def freeze(
        self,
        output_path: Path,
        *,
        qualification: Mapping[str, object],
        release_pack_verification: Mapping[str, object],
        release_pack_hash: str,
        run_binding: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            return super().freeze(
                output_path,
                qualification=qualification,
                release_pack_verification=release_pack_verification,
                release_pack_hash=release_pack_hash,
                run_binding=run_binding,
            )
        except AcceptanceReplayError as exc:
            raise LiveWorkspaceAcceptanceError(
                _map_neutral_reason(exc.reason_code)
            ) from None


class SanitizedMutationJudgeUsageObserver(_NeutralSanitizedMutationJudgeUsageObserver):
    """Workspace-compatible facade over bounded judge usage evidence."""

    def __init__(self, *, attempt_ceiling: int | None = None) -> None:
        super().__init__(
            attempt_ceiling=attempt_ceiling,
            attempt_id_prefix="live_mutation_judge_attempt",
        )


BoundedSanitizedProvider = _NeutralBoundedSanitizedProvider
CoverageAssignmentEvidenceObserver = _NeutralCoverageAssignmentEvidenceObserver
build_coverage_attempt_observer_factory = _neutral_observer_factory


def _bounded_reason(value: object) -> str:
    return _neutral_bounded_reason(value)


def _map_neutral_reason(reason_code: str) -> str:
    return {
        "acceptance_evidence_malformed": "live_evidence_malformed",
        "acceptance_identity_malformed": "live_evidence_malformed",
        "acceptance_identity_mismatch": "live_evidence_identity_mismatch",
        "acceptance_binding_malformed": "live_run_binding_malformed",
        "acceptance_evidence_missing": "live_evidence_missing",
        "acceptance_replay_input_malformed": "live_replay_input_malformed",
        "acceptance_replay_input_mismatch": "live_replay_input_mismatch",
        "acceptance_replay_inputs_missing": "live_replay_inputs_missing",
        "acceptance_evidence_unreadable": "live_evidence_unreadable",
        "acceptance_replay_failed": "live_replay_contract_failed",
        "acceptance_replay_count_mismatch": "live_replay_count_mismatch",
        "acceptance_judge_attempt_missing": "live_judge_attempt_missing",
        "acceptance_assignment_missing": "live_evidence_assignment_missing",
        "acceptance_evidence_already_frozen": "live_evidence_already_frozen",
        "acceptance_authorization_malformed": "live_evidence_malformed",
        "acceptance_release_evidence_missing": "live_evidence_missing",
        "acceptance_release_evidence_malformed": "live_evidence_malformed",
        "acceptance_release_identity_mismatch": "live_evidence_identity_mismatch",
        "acceptance_release_path_unsafe": "live_evidence_malformed",
        "acceptance_proof_failed": "live_tracer_proof_failed",
        "acceptance_pipeline_result_malformed": "live_evidence_malformed",
        "qualification_evidence_not_freezable": "real_release_candidate_not_verified",
    }.get(reason_code, reason_code)


def _raise_workspace_reason(error: AcceptanceReplayError) -> None:
    raise LiveWorkspaceAcceptanceError(
        _map_neutral_reason(error.reason_code)
    ) from None


def validate_live_provider_evidence(evidence: Mapping[str, object]) -> None:
    try:
        _neutral_validate_provider_evidence(
            evidence,
            contract=_WORKSPACE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        _raise_workspace_reason(exc)


def load_live_provider_evidence(path: Path) -> dict[str, object]:
    try:
        value = _neutral_load_provider_evidence(
            path,
            contract=_WORKSPACE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        _raise_workspace_reason(exc)
    return value


def replay_sanitized_provider_evidence(
    evidence: Mapping[str, object] | Path,
    *,
    plan: object,
    seed: object,
    environment_path: Path,
) -> dict[str, object]:
    """Replay frozen provider input through the Workspace-owned tracer hook."""

    def replay_loaded(loaded: Mapping[str, object]) -> int:
        if not environment_path.is_file() or environment_path.is_symlink():
            raise LiveWorkspaceAcceptanceError("live_replay_environment_missing")
        from synthesis.workspace_tracer import replay_provider_attempts

        try:
            return replay_provider_attempts(
                root_dir=environment_path.parent,
                artifacts={"workspace_environment": {"path": environment_path.name}},
                anchors={"workspace_environment": "workspace_environment"},
                plan=plan,
                seed=seed,
                provider=loaded,
                assignment_evidence={
                    "assignments": [
                        dict(attempt["assignment_lineage"])
                        for attempt in loaded["replay_attempts"]
                        if isinstance(attempt, Mapping)
                        and isinstance(attempt.get("assignment_lineage"), Mapping)
                    ],
                    "assignment_contracts": [
                        dict(attempt["assignment"])
                        for attempt in loaded["replay_attempts"]
                        if isinstance(attempt, Mapping)
                        and isinstance(attempt.get("assignment"), Mapping)
                    ],
                },
            )
        except Exception as exc:
            raise LiveWorkspaceAcceptanceError(
                "live_replay_contract_failed"
            ) from exc

    try:
        return _neutral_replay_frozen_provider_evidence(
            evidence,
            replay=replay_loaded,
            contract=_WORKSPACE_ACCEPTANCE_CONTRACT,
        )
    except AcceptanceReplayError as exc:
        _raise_workspace_reason(exc)
    raise AssertionError("unreachable")

@dataclass(frozen=True)
class LiveWorkspaceAcceptanceResult:
    acceptance_dir: Path
    proof_path: Path
    provider_evidence_path: Path
    replay: Mapping[str, object]
    qualification: Mapping[str, object]


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _live_run_binding(
    *,
    profile: object,
    plan: object,
    coverage_plan: object,
    source_result: object,
) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "dataset_version": profile.dataset_version,
        "seed_id": profile.seed.seed_id,
        "seed_domain": profile.seed.domain,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "coverage_plan_id": coverage_plan.plan_id,
        "coverage_plan_hash": coverage_plan.plan_hash,
        "source_policy_hash": source_result.source_policy_hash,
    }


def _mutation_judge_attempt_ceiling(profile: object, coverage_plan: object) -> int:
    """Derive a physical judge-call ceiling from the authorized plan bound."""

    judge = profile.mutation_admission.judge
    retry_count = getattr(judge, "max_retries", None)
    attempt_ceiling = getattr(coverage_plan, "attempt_ceiling", None)
    if (
        not isinstance(retry_count, int)
        or isinstance(retry_count, bool)
        or retry_count not in {0, 1}
        or not isinstance(attempt_ceiling, int)
        or isinstance(attempt_ceiling, bool)
        or attempt_ceiling <= 0
    ):
        raise LiveWorkspaceAcceptanceError("authorization_budget_invalid")
    # One contract-validity preflight plus at most one judgment per planned
    # candidate, each with the profile's bounded retry count.
    return (attempt_ceiling + 1) * (retry_count + 1)


def _generator_physical_call_ceiling(
    authorization: LiveWorkspaceAcceptanceAuthorization,
) -> int:
    """Bind retry-expanded generator calls to the explicit authorization."""

    retry_limit = authorization.generator_retry_limit
    attempt_budget = authorization.attempt_budget
    if (
        not isinstance(retry_limit, int)
        or isinstance(retry_limit, bool)
        or retry_limit not in range(MAX_LIVE_GENERATOR_RETRIES + 1)
        or not isinstance(attempt_budget, int)
        or isinstance(attempt_budget, bool)
        or attempt_budget <= 0
    ):
        raise LiveWorkspaceAcceptanceError("generator_retry_budget_invalid")
    return attempt_budget * (retry_limit + 1)


def _live_mutation_judge_preflight_request() -> object:
    """Build a fixed, non-source-backed semantic-judge contract probe."""

    from synthesis.mutation_admission import SemanticJudgeRequest

    return SemanticJudgeRequest(
        instruction=(
            "Create a high-priority task titled Judge readiness in the Alpha "
            "Launch project due this week."
        ),
        task_type="workspace_task_creation",
        action_type="workspace_task_create",
        action_evidence_text="Create a high-priority task",
        argument_values={
            "title": "Judge readiness",
            "project_id": "project_alpha",
            "priority": "high",
            "due_label": "this_week",
        },
        argument_evidence={
            "title": "Judge readiness",
            "project_id": {"project_id": "project_alpha"},
            "priority": "high-priority",
            "due_label": "this week",
        },
        argument_origins={
            "title": "instruction",
            "project_id": "tool_observation",
            "priority": "instruction",
            "due_label": "instruction",
        },
        evidence_references={
            "action": "live_preflight_action",
            "title": "live_preflight_title",
            "project_id": "live_preflight_project",
            "priority": "live_preflight_priority",
            "due_label": "live_preflight_due",
        },
    )


def _preflight_live_mutation_judge(
    *,
    profile: object,
    generator_config: object,
    http_client: object | None,
    attempt_observer: SanitizedMutationJudgeUsageObserver,
) -> dict[str, object]:
    """Prove the exact independent-judge contract before generation spend."""

    from synthesis.llm import LLMConfig
    from synthesis.mutation_admission import (
        build_openai_compatible_semantic_mutation_judge,
    )

    judge_config = profile.mutation_admission.judge
    judge = build_openai_compatible_semantic_mutation_judge(
        config=LLMConfig(
            base_url=generator_config.base_url,
            api_key=generator_config.api_key,
            model=judge_config.model,
            temperature=0.0,
        ),
        http_client=http_client,
        timeout_seconds=float(judge_config.timeout_seconds),
        max_retries=int(judge_config.max_retries),
        thinking_mode=getattr(judge_config, "thinking_mode", None),
        attempt_observer=attempt_observer,
    )
    result = judge(_live_mutation_judge_preflight_request())
    verdict = result.verdict
    status = (
        "passed"
        if result.provider_outcome == "succeeded"
        and isinstance(verdict, Mapping)
        and verdict.get("verdict") == "supported"
        else "failed"
    )
    return {
        "status": status,
        "provider_outcome": result.provider_outcome,
        "attempts": result.attempts,
    }


def _generator_usage_summary(
    recorder: SanitizedProviderEvidenceRecorder,
) -> dict[str, object]:
    attempts = recorder.attempts
    retries = sum(
        int(record.get("retry_count", 0))
        for record in attempts
        if isinstance(record.get("retry_count"), int)
        and not isinstance(record.get("retry_count"), bool)
    )
    return {
        "logical_calls": len(attempts),
        "tokens": _sum_usage(attempts),
        "retries": retries,
        "physical_calls": len(attempts) + retries,
        "physical_call_ceiling": _generator_physical_call_ceiling(
            recorder.authorization
        ),
        "outcomes": {
            outcome: sum(record.get("outcome") == outcome for record in attempts)
            for outcome in sorted({str(record.get("outcome")) for record in attempts})
        },
    }


def _bounded_rejection_summary(rejections_path: Path | None) -> dict[str, object]:
    if rejections_path is None or not rejections_path.is_file():
        return {"count": 0, "causes": {}}
    causes: dict[str, int] = {}
    count = 0
    try:
        for line in rejections_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, Mapping):
                raise ValueError("rejection record is malformed")
            count += 1
            cause = record.get("cause")
            bounded_cause = _bounded_reason(cause)
            causes[bounded_cause] = causes.get(bounded_cause, 0) + 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {"count": 0, "causes": {"rejection_summary_unavailable": 1}}
    return {"count": count, "causes": dict(sorted(causes.items()))}


def _write_live_attempt_failure(
    output_dir: Path,
    *,
    reason_code: str,
    phase: str,
    authorization: LiveWorkspaceAcceptanceAuthorization,
    run_binding: Mapping[str, object],
    recorder: SanitizedProviderEvidenceRecorder,
    mutation_judge_usage: SanitizedMutationJudgeUsageObserver,
    mutation_judge_preflight: Mapping[str, object] | None,
    rejections_path: Path | None = None,
    qualification: Mapping[str, object] | None = None,
) -> Path:
    """Persist a no-response audit record for an unsuccessful live attempt."""

    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", reason_code):
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    if phase not in {"mutation_judge_preflight", "pipeline", "release_evidence", "qualification"}:
        raise LiveWorkspaceAcceptanceError("live_evidence_malformed")
    qualification_summary = None
    if isinstance(qualification, Mapping):
        qualification_summary = {
            "status": qualification.get("status"),
            "effective_qualification": qualification.get("effective_qualification"),
        }
    record: dict[str, object] = {
        "schema_version": LIVE_ATTEMPT_FAILURE_SCHEMA_VERSION,
        "status": "failed",
        "reason_code": reason_code,
        "phase": phase,
        "authorization": authorization.to_record(),
        "run_binding": dict(run_binding),
        "generator_usage": _generator_usage_summary(recorder),
        "mutation_judge_usage": mutation_judge_usage.to_failure_record(),
        "mutation_judge_preflight": (
            dict(mutation_judge_preflight)
            if isinstance(mutation_judge_preflight, Mapping)
            else {"status": "not_started"}
        ),
        "non_accepted_attempts": _bounded_rejection_summary(rejections_path),
        "provider_evidence_frozen": False,
        "tracer_proof_published": False,
        "qualification": qualification_summary,
    }
    destination = output_dir / "live_attempt_failure.json"
    _write_json(destination, record)
    return destination


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveWorkspaceAcceptanceError("live_artifact_unreadable") from exc
    if not isinstance(value, Mapping):
        raise LiveWorkspaceAcceptanceError("live_artifact_malformed")
    return dict(value)


def _profile_seed(profile: object) -> object:
    return profile.seed


def _build_live_plan_and_coverage(profile: object, output_dir: Path) -> tuple[object, object, object]:
    from synthesis.domain_pack import DomainPlan, PlanFailure
    from synthesis.domain_sources import build_domain_fixture_source_bundle
    from synthesis.sources import validate_source_bundle
    from synthesis.workspace_domain_pack import (
        admitted_workspace_source,
        build_workspace_domain_pack,
        workspace_planning_intent,
    )
    from synthesis.pipeline import preview_coverage_plan

    source_bundle = build_domain_fixture_source_bundle(profile.seed.domain)
    source_result = validate_source_bundle(source_bundle)
    pack = build_workspace_domain_pack()
    admitted_source = admitted_workspace_source(source_bundle, source_result)
    plan = pack.plan(workspace_planning_intent(pack), admitted_source)
    if isinstance(plan, PlanFailure) or not isinstance(plan, DomainPlan):
        raise LiveWorkspaceAcceptanceError("workspace_plan_not_admitted")
    coverage_plan = preview_coverage_plan(profile)
    _write_json(output_dir / "coverage_plan_preflight.json", coverage_plan.canonical())
    return plan, coverage_plan, source_result


def _generator_identity(config: object) -> dict[str, object]:
    lineage = config.lineage("task_generation")
    return {
        "provider_id": "openai_compatible",
        "provider_version": "openai_compatible_client_v1",
        "provider_host": _safe_provider_host(config.base_url),
        "model": config.model,
        "config_hash": lineage["config_hash"],
        "parser_version": PROVIDER_PARSER_VERSION,
    }


def _mutation_judge_identity(profile: object, config: object) -> dict[str, object]:
    from synthesis.llm import LLMConfig

    judge = profile.mutation_admission.judge
    judge_config = LLMConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        model=judge.model,
        temperature=0.0,
    )
    lineage = judge_config.lineage(
        "mutation_admission_judge",
        thinking_mode=getattr(judge, "thinking_mode", None),
    )
    return {
        "provider": judge.provider,
        "provider_host": _safe_provider_host(judge_config.base_url),
        "model": judge.model,
        "config_hash": lineage["config_hash"],
        "role": judge.role,
        "role_version": "role_mutation_admission_judge_v1",
    }


def _safe_provider_host(base_url: object) -> str:
    if not isinstance(base_url, str) or not base_url:
        return "unconfigured"
    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if hostname is None:
        return "unconfigured"
    try:
        port = parsed.port
    except ValueError:
        return "unconfigured"
    return f"{hostname}:{port}" if port is not None else hostname


def _environment_path(output_dir: Path) -> Path:
    candidates = (
        output_dir / "environment" / "workspace_tasks.sqlite3",
        output_dir / "workspace_tasks.sqlite3",
    )
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            return path
    raise LiveWorkspaceAcceptanceError("live_replay_environment_missing")


def _write_live_pipeline_reports(
    *,
    output_dir: Path,
    profile: object,
    result: object,
    runtime_seconds: float,
) -> tuple[Path, Path, Path, Path, Path, Path, dict[str, object]]:
    from synthesis.datasets import (
        attach_dataset_release_pack_to_manifest,
        attach_dataset_release_report_to_manifest,
        attach_episode_replay_report_to_manifest,
        attach_evaluation_report_to_manifest,
        attach_profile_decision_report_to_manifest,
        attach_release_quality_audit_to_manifest,
    )
    from synthesis.dataset_release import write_dataset_release_report
    from synthesis.episode_replay import write_episode_replay_report
    from synthesis.episode_quality import read_episode_logs
    from synthesis.evaluation import write_evaluation_report
    from synthesis.profile_decisions import write_profile_decision_report
    from synthesis.qualification import write_workspace_release_candidate_qualification
    from synthesis.release_pack import verify_dataset_release_pack, write_dataset_release_pack
    from synthesis.release_quality import write_release_quality_audit

    if result.episode_logs_path is None or result.coverage_evidence_path is None:
        raise LiveWorkspaceAcceptanceError("run_completeness")
    episodes = read_episode_logs(result.episode_logs_path)
    replay_path = write_episode_replay_report(
        output_dir / "episode_replay_report.json",
        dataset_version=profile.dataset_version,
        episodes=episodes,
        manifest_path=result.manifest_path,
        episodes_path=result.episode_logs_path,
    )
    attach_episode_replay_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=replay_path,
    )
    evaluation_path = write_evaluation_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
    )
    attach_evaluation_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=evaluation_path,
    )
    profile_decision_path = write_profile_decision_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        runtime_seconds=runtime_seconds,
    )
    attach_profile_decision_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=profile_decision_path,
    )
    dataset_release_report_path = write_dataset_release_report(
        manifest_path=result.manifest_path,
        quality_report_path=result.quality_report_path,
        evaluation_report_path=evaluation_path,
        profile_decision_report_path=profile_decision_path,
    )
    attach_dataset_release_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=dataset_release_report_path,
    )
    audit_path = write_release_quality_audit(
        manifest_path=result.manifest_path,
        output_path=output_dir / "release_quality_audit.json",
    )
    attach_release_quality_audit_to_manifest(
        manifest_path=result.manifest_path,
        audit_path=audit_path,
    )
    pack_path = output_dir / "dataset_release_pack.json"
    attach_dataset_release_pack_to_manifest(
        manifest_path=result.manifest_path,
        pack_path=pack_path,
    )
    write_dataset_release_pack(
        manifest_path=result.manifest_path,
        dataset_release_report_path=dataset_release_report_path,
        output_path=pack_path,
    )
    pack_verification = verify_dataset_release_pack(pack_path)
    verification = pack_verification.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "passed":
        raise LiveWorkspaceAcceptanceError("release_pack_not_independently_verified")
    _write_json(output_dir / "release_pack_verification.json", pack_verification)
    qualification_path = output_dir / "qualification_report.json"
    write_workspace_release_candidate_qualification(
        manifest_path=result.manifest_path,
        release_pack_path=pack_path,
        release_quality_audit_path=audit_path,
        output_path=qualification_path,
    )
    return (
        replay_path,
        evaluation_path,
        profile_decision_path,
        dataset_release_report_path,
        audit_path,
        pack_path,
        _load_json(qualification_path),
    )


class _WorkspaceAcceptanceAdapter:
    """Bind Workspace semantics to the pack-neutral acceptance harness."""

    evidence_contract = _WORKSPACE_ACCEPTANCE_CONTRACT

    def __init__(self) -> None:
        self._profile: object | None = None
        self._output_dir: Path | None = None

    def error_for_reason(self, reason_code: str) -> LiveWorkspaceAcceptanceError:
        return LiveWorkspaceAcceptanceError(_map_neutral_reason(reason_code))

    def prepare(self, *, profile: object, output_dir: Path) -> AcceptancePreparation:
        self._profile = profile
        self._output_dir = output_dir
        plan, coverage_plan, source_result = _build_live_plan_and_coverage(
            profile,
            output_dir,
        )
        profile_record = profile.canonical()
        return AcceptancePreparation(
            profile_record=profile_record,
            plan=plan,
            coverage_plan=coverage_plan,
            source_policy_hash=source_result.source_policy_hash,
            run_binding=_live_run_binding(
                profile=profile,
                plan=plan,
                coverage_plan=coverage_plan,
                source_result=source_result,
            ),
        )

    def validate_authorization(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        authorization: AcceptanceAuthorization,
        max_generator_retries: int,
    ) -> None:
        authorization.validate(
            profile=preparation.profile_record,
            plan_attempt_ceiling=int(
                getattr(preparation.coverage_plan, "attempt_ceiling")
            ),
        )
        if max_generator_retries != authorization.generator_retry_limit:
            raise LiveWorkspaceAcceptanceError("generator_retry_authorization_mismatch")
        del profile

    def resolve_generator_config(self, supplied: object | None) -> object:
        from synthesis.llm import LLMConfig, LLMConfigurationError

        try:
            config = supplied or LLMConfig.from_env()
        except LLMConfigurationError as exc:
            raise LiveWorkspaceAcceptanceError("llm_configuration_required") from exc
        if not isinstance(config, LLMConfig) or not config.configured:
            raise LiveWorkspaceAcceptanceError("llm_configuration_required")
        return config

    def validate_generator_config(
        self,
        *,
        profile: object,
        authorization: AcceptanceAuthorization,
        config: object,
    ) -> None:
        from synthesis.llm import LLMConfig

        if not isinstance(config, LLMConfig) or not config.configured:
            raise LiveWorkspaceAcceptanceError("llm_configuration_required")
        if config.model != authorization.generator_model:
            raise LiveWorkspaceAcceptanceError("generator_identity_mismatch")
        judge_config = profile.mutation_admission.judge
        if judge_config.model != authorization.mutation_judge_model:
            raise LiveWorkspaceAcceptanceError("mutation_judge_identity_mismatch")

    def generator_identity(self, config: object) -> Mapping[str, object]:
        return _generator_identity(config)

    def mutation_judge_identity(
        self,
        *,
        profile: object,
        config: object,
    ) -> Mapping[str, object]:
        return _mutation_judge_identity(profile, config)

    def create_recorder(
        self,
        *,
        authorization: AcceptanceAuthorization,
        provider_identity: Mapping[str, object],
        mutation_judge_identity: Mapping[str, object],
    ) -> AcceptanceEvidenceRecorder:
        return SanitizedProviderEvidenceRecorder(
            authorization=authorization,
            provider_identity=provider_identity,
            mutation_judge_identity=mutation_judge_identity,
        )

    def create_usage_observer(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> AcceptanceUsageObserver:
        return SanitizedMutationJudgeUsageObserver(
            attempt_ceiling=self.mutation_judge_attempt_ceiling(
                profile=profile,
                preparation=preparation,
            )
        )

    def preflight_mutation_judge(
        self,
        *,
        profile: object,
        config: object,
        http_client: object | None,
        observer: AcceptanceUsageObserver,
    ) -> Mapping[str, object]:
        return _preflight_live_mutation_judge(
            profile=profile,
            generator_config=config,
            http_client=http_client,
            attempt_observer=observer,
        )

    def build_provider(
        self,
        *,
        config: object,
        authorization: AcceptanceAuthorization,
        recorder: AcceptanceEvidenceRecorder,
        http_client: object | None,
        max_generator_retries: int,
    ) -> object:
        from synthesis.llm import LLMConfig, OpenAICompatibleClient

        if not isinstance(config, LLMConfig):
            raise LiveWorkspaceAcceptanceError("llm_configuration_required")
        return BoundedSanitizedProvider(
            OpenAICompatibleClient(
                config,
                http_client=http_client,
                max_retries=max_generator_retries,
            ),
            recorder=recorder,
            max_logical_calls=authorization.attempt_budget,
        )

    def run_pipeline(
        self,
        *,
        output_dir: Path,
        profile: object,
        provider: object,
        recorder: AcceptanceEvidenceRecorder,
        observer: AcceptanceUsageObserver,
        mutation_judge_http_client: object | None,
        config: object,
    ) -> AcceptancePipelineResult:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.llm import LLMConfig
        from synthesis.pipeline import run_foundation_pipeline

        if not isinstance(config, LLMConfig):
            raise LiveWorkspaceAcceptanceError("llm_configuration_required")
        result = run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                provider,
                attempt_observer_factory=build_coverage_attempt_observer_factory(
                    recorder
                ),
                generation_rejection_callback=recorder.record_generation_rejection,
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
            write_episode_logs=True,
            mutation_judge_http_client=mutation_judge_http_client,
            mutation_judge_attempt_observer=observer,
            llm_config=config,
            max_concurrency=1,
        )
        return AcceptancePipelineResult(
            result=result,
            accepted_count=result.accepted_count,
            rejections_path=result.rejections_path,
        )

    def validate_pipeline(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
        pipeline: AcceptancePipelineResult,
    ) -> None:
        del profile, preparation
        if pipeline.accepted_count < 5:
            raise LiveWorkspaceAcceptanceError(
                "workspace_coverage_evidence_incomplete"
            )

    def mutation_judge_attempt_ceiling(
        self,
        *,
        profile: object,
        preparation: AcceptancePreparation,
    ) -> int:
        return _mutation_judge_attempt_ceiling(profile, preparation.coverage_plan)

    def write_release_evidence(
        self,
        *,
        output_dir: Path,
        profile: object,
        pipeline: AcceptancePipelineResult,
        runtime_seconds: float,
    ) -> AcceptanceReleaseEvidence:
        (
            replay_path,
            evaluation_path,
            profile_decision_path,
            dataset_release_report_path,
            audit_path,
            pack_path,
            qualification,
        ) = _write_live_pipeline_reports(
            output_dir=output_dir,
            profile=profile,
            result=pipeline.result,
            runtime_seconds=runtime_seconds,
        )
        verification_record = _load_json(output_dir / "release_pack_verification.json")
        verification = verification_record.get("verification")
        if not isinstance(verification, Mapping):
            raise LiveWorkspaceAcceptanceError("release_pack_not_independently_verified")
        return AcceptanceReleaseEvidence(
            replay_report_path=replay_path,
            evaluation_report_path=evaluation_path,
            profile_decision_path=profile_decision_path,
            dataset_release_report_path=dataset_release_report_path,
            release_quality_audit_path=audit_path,
            release_pack_path=pack_path,
            release_pack_verification=verification,
            qualification=qualification,
            release_pack_hash="sha256:" + hashlib.sha256(pack_path.read_bytes()).hexdigest(),
        )

    def bind_sample_assignments(
        self,
        *,
        recorder: AcceptanceEvidenceRecorder,
        pipeline: AcceptancePipelineResult,
    ) -> None:
        result = pipeline.result
        samples = []
        try:
            for line in result.samples_path.read_text(encoding="utf-8").splitlines():
                if line:
                    value = json.loads(line)
                    if isinstance(value, Mapping):
                        samples.append(value)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LiveWorkspaceAcceptanceError("live_artifact_unreadable") from exc
        assignments_by_id: dict[str, Mapping[str, object]] = {}
        for sample in samples:
            evidence = sample.get("workspace_evidence")
            assignment = evidence.get("assignment") if isinstance(evidence, Mapping) else None
            assignment_id = (
                assignment.get("assignment_id")
                if isinstance(assignment, Mapping)
                else None
            )
            if isinstance(assignment_id, str) and isinstance(assignment, Mapping):
                assignments_by_id[assignment_id] = assignment
        recorder.bind_sample_assignments(assignments_by_id)

    def replay(
        self,
        *,
        evidence: Mapping[str, object],
        preparation: AcceptancePreparation,
    ) -> Mapping[str, object]:
        if self._output_dir is None or self._profile is None:
            raise LiveWorkspaceAcceptanceError("live_replay_environment_missing")
        return replay_sanitized_provider_evidence(
            evidence,
            plan=preparation.plan,
            seed=_profile_seed(self._profile),
            environment_path=_environment_path(self._output_dir),
        )

    def build_proof(self, *, proof_root: Path, acceptance_dir: Path) -> Path:
        from synthesis.workspace_tracer import build_workspace_tracer_proof_from_live_acceptance

        return build_workspace_tracer_proof_from_live_acceptance(
            proof_root,
            acceptance_dir,
        )

    def verify_proof(self, proof_path: Path) -> Mapping[str, object]:
        from synthesis.workspace_tracer import verify_workspace_tracer_proof

        return verify_workspace_tracer_proof(proof_path)

    def provider_evidence_path(
        self,
        *,
        proof_path: Path,
        acceptance_dir: Path,
    ) -> Path:
        del acceptance_dir
        return proof_path.parent / "positive" / "trace" / "provider.json"

    def write_failure(
        self,
        output_dir: Path,
        *,
        reason_code: str,
        phase: str,
        authorization: AcceptanceAuthorization,
        preparation: AcceptancePreparation,
        recorder: AcceptanceEvidenceRecorder,
        observer: AcceptanceUsageObserver,
        mutation_judge_preflight: Mapping[str, object] | None,
        rejections_path: Path | None = None,
        qualification: Mapping[str, object] | None = None,
    ) -> Path:
        return _write_live_attempt_failure(
            output_dir,
            reason_code=reason_code,
            phase=phase,
            authorization=authorization,
            run_binding=preparation.run_binding,
            recorder=recorder,
            mutation_judge_usage=observer,
            mutation_judge_preflight=mutation_judge_preflight,
            rejections_path=rejections_path,
            qualification=qualification,
        )


def run_live_workspace_acceptance(
    output_dir: Path,
    *,
    profile: object,
    authorization: LiveWorkspaceAcceptanceAuthorization,
    generator_config: object | None = None,
    generator_http_client: object | None = None,
    mutation_judge_http_client: object | None = None,
    proof_root: Path | None = None,
    max_generator_retries: int = 2,
) -> LiveWorkspaceAcceptanceResult:
    """Run the Workspace adapter through the pack-neutral acceptance harness."""

    if not hasattr(profile, "canonical") or not hasattr(profile, "seed"):
        raise LiveWorkspaceAcceptanceError("live_workspace_profile_invalid")
    output_dir = Path(output_dir)
    workspace_proof_root = (
        Path(proof_root)
        if proof_root is not None
        else output_dir.parent / (output_dir.name + "-tracer-proof")
    )
    result = AcceptanceReplayHarness(_WorkspaceAcceptanceAdapter()).run(
        output_dir,
        profile=profile,
        authorization=authorization,
        generator_config=generator_config,
        generator_http_client=generator_http_client,
        mutation_judge_http_client=mutation_judge_http_client,
        proof_root=workspace_proof_root,
        max_generator_retries=max_generator_retries,
    )
    return LiveWorkspaceAcceptanceResult(
        acceptance_dir=result.acceptance_dir,
        proof_path=result.proof_path,
        provider_evidence_path=result.provider_evidence_path,
        replay=result.replay,
        qualification=result.qualification,
    )
