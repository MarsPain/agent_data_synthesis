from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict

from synthesis.datasets import (
    attach_dataset_release_card_to_manifest,
    attach_dataset_release_report_to_manifest,
    attach_dataset_release_pack_to_manifest,
    attach_episode_quality_report_to_manifest,
    attach_episode_replay_report_to_manifest,
    attach_episodes_to_manifest,
    attach_evaluation_report_to_manifest,
    attach_profile_decision_report_to_manifest,
    attach_release_quality_audit_to_manifest,
    attach_release_review_queue_to_manifest,
    attach_reward_label_report_to_manifest,
    attach_reward_labels_to_manifest,
)
from synthesis.dataset_release import write_dataset_release_report
from synthesis.coverage import CoveragePlanValidationError
from synthesis.coverage_assignments import (
    build_coverage_assignment_scheduler_factory,
)
from synthesis.episode_quality import (
    EPISODE_QUALITY_REPORT_FILENAME,
    build_episode_quality_report,
    read_episode_logs,
    write_episode_quality_report,
)
from synthesis.episode_replay import (
    EPISODE_REPLAY_REPORT_FILENAME,
    build_episode_replay_report,
    write_episode_replay_report,
)
from synthesis.evaluation import write_evaluation_report
from synthesis.concurrency import validate_concurrency
from synthesis.llm import (
    LLMConfig,
    LLMConfigurationError,
    LLMProviderError,
    OpenAICompatibleClient,
)
from synthesis.orchestration import (
    CancellationSignal,
    OrchestrationError,
    SerialJobResult,
    run_serial_job,
)
from synthesis.pipeline import (
    CandidateGenerator,
    build_domain_llm_candidate_generator_factory,
    build_llm_candidate_generator,
    build_llm_task_expansion_generator,
    preview_coverage_plan,
    run_foundation_pipeline,
)
from synthesis.profile_decisions import write_profile_decision_report
from synthesis.profile_contracts import (
    REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS,
)
from synthesis.release_pack import DATASET_RELEASE_PACK_FILENAME, write_dataset_release_pack
from synthesis.release_quality import (
    DATASET_RELEASE_CARD_FILENAME,
    RELEASE_QUALITY_AUDIT_FILENAME,
    write_dataset_release_card,
    write_release_quality_audit,
)
from synthesis.release_review import (
    RELEASE_REVIEW_QUEUE_FILENAME,
    write_release_review_queue,
)
from synthesis.qualification import (
    QUALIFICATION_REPORT_FILENAME,
    write_release_candidate_qualification,
)
from synthesis.reward_labels import (
    REWARD_LABELS_FILENAME,
    REWARD_LABEL_REPORT_FILENAME,
    build_reward_labels,
    write_reward_label_report,
    write_reward_labels,
)
from synthesis.refinement import deterministic_fixture_refiner
from synthesis.run_profiles import RunProfile, RunProfileValidationError, load_run_profile
from synthesis.domain_sources import (
    ProfileLocalDomainSourceRequest,
    build_profile_local_domain_source_input,
    resolve_domain_source_importer,
)
from synthesis.sources import SourceBundle, build_external_fixture_source_bundle
from synthesis.sources import (
    ControlledSourceFetchError,
    FetchedSourceRequest,
    build_network_contacts_source_input,
)
from synthesis.tasks import generate_scale_probe_candidates


class _AsyncJobKwargs(TypedDict):
    output_dir: Path
    job_id: str
    run_profile: RunProfile
    resume: bool
    candidate_generator: CandidateGenerator | None
    source_bundle: SourceBundle | None
    domain_environment_input: object | None
    source_events: list[dict[str, object]] | None
    enable_source_audit: bool
    run_profile_metadata: dict[str, object]
    parent_artifact_path: Path | None
    write_episode_logs: bool
    authorization_limits: dict[str, object] | None
    recover_stale_lock: bool
    provider_factory: Callable[[], object] | None
    provider_alias: str | None
    model_alias: str | None
    cancellation_signal: CancellationSignal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local Agent data synthesis foundation pipeline."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/foundation"),
        help="Directory for JSONL samples, rejections, manifest, and fixture state.",
    )
    parser.add_argument(
        "--run-profile",
        type=Path,
        default=None,
        help=(
            "Validated run_profile_v1, run_profile_v2, run_profile_v3, "
            "or run_profile_v4 JSON file."
        ),
    )
    parser.add_argument(
        "--enable-async-runner",
        "--enable-async",
        "--async",
        dest="enable_async_runner",
        action="store_true",
        help=(
            "Opt into a durable local orchestration job. Requires a validated "
            "--run-profile and --job-id."
        ),
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Stable local orchestration job identifier for explicit async runs.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the durable async job identified by --job-id.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=_positive_int_argument,
        default=None,
        help="Positive async worker bound; omitted async runs use one worker.",
    )
    parser.add_argument(
        "--recover-stale-lock",
        action="store_true",
        help="Explicitly recover a validated stale async job lock.",
    )
    parser.add_argument(
        "--logical-call-budget",
        type=_positive_logical_call_budget_argument,
        default=None,
        help="Cumulative logical provider-call authorization for async LLM jobs.",
    )
    parser.add_argument(
        "--provider-alias",
        default=None,
        help="Sanitized provider alias persisted in async usage evidence.",
    )
    parser.add_argument(
        "--model-alias",
        default=None,
        help="Sanitized model alias persisted in async usage evidence.",
    )
    parser.add_argument(
        "--preview-coverage-plan",
        action="store_true",
        help=(
            "Print the sanitized coverage plan selected by the run profile and "
            "exit without generating or executing candidates."
        ),
    )
    parser.add_argument(
        "--write-coverage-plan",
        action="store_true",
        help=(
            "Write coverage_plan.json under --output-dir and exit without "
            "generating or executing candidates."
        ),
    )
    parser.add_argument(
        "--dataset-version",
        default=None,
        help="Dataset version id written into samples and manifest.",
    )
    parser.add_argument(
        "--parent-artifact",
        type=Path,
        default=None,
        help="Optional parent manifest or quality report JSON for local version comparison.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Generate candidate tasks through the configured remote OpenAI-compatible API.",
    )
    parser.add_argument(
        "--enable-refinement",
        action="store_true",
        help="Enable the deterministic one-shot critic/refinement fixture loop.",
    )
    parser.add_argument(
        "--enable-branching",
        action="store_true",
        help="Enable the deterministic multi-path branching fixture.",
    )
    parser.add_argument(
        "--enable-task-expansion",
        action="store_true",
        help="Enable deterministic seed transformation and task suggester/editor expansion.",
    )
    parser.add_argument(
        "--enable-mcp-adapter",
        action="store_true",
        help="Route fixture tool calls through the local in-process MCP-compatible adapter shim.",
    )
    parser.add_argument(
        "--enable-sandbox-fixture",
        action="store_true",
        help="Enable deterministic generated-code sandbox scan/admission/execution fixture.",
    )
    parser.add_argument(
        "--enable-source-governance-fixture",
        action="store_true",
        help=(
            "Enable deterministic no-network external-source governance fixture "
            "and source event auditing."
        ),
    )
    parser.add_argument(
        "--enable-network-source",
        action="store_true",
        help="Enable controlled opt-in HTTPS source ingestion for the contacts environment.",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="HTTPS source URL for controlled network-backed contacts ingestion.",
    )
    parser.add_argument(
        "--source-license-label",
        default=None,
        help="License label for the controlled external source.",
    )
    parser.add_argument(
        "--allowed-source-host",
        action="append",
        default=[],
        help="Exact source host allowed for controlled ingestion. Repeat for multiple hosts.",
    )
    parser.add_argument(
        "--source-timeout-seconds",
        type=float,
        default=5.0,
        help="Timeout for controlled source fetches.",
    )
    parser.add_argument(
        "--source-max-bytes",
        type=int,
        default=65536,
        help="Maximum accepted source payload size in bytes.",
    )
    parser.add_argument(
        "--mock-source-fixture",
        type=Path,
        default=None,
        help="No-network test fixture used as the source response body.",
    )
    parser.add_argument(
        "--write-profile-decision-report",
        action="store_true",
        help="Write profile_decision_report.json and reference it from the manifest.",
    )
    parser.add_argument(
        "--write-evaluation-report",
        action="store_true",
        help="Write evaluation_report.json and reference it from the manifest.",
    )
    parser.add_argument(
        "--write-episode-quality-report",
        action="store_true",
        help="Write episodes.jsonl and episode_quality_report.json for runtime episode evidence scoring.",
    )
    parser.add_argument(
        "--write-episode-replay-report",
        action="store_true",
        help="Write episode_replay_report.json by replaying sanitized episode logs against fresh runtimes.",
    )
    parser.add_argument(
        "--write-reward-label-report",
        action="store_true",
        help=(
            "Write reward_labels.jsonl and reward_label_report.json from sanitized "
            "episode evidence without training a reward model."
        ),
    )
    parser.add_argument(
        "--write-dataset-release-report",
        action="store_true",
        help="Write dataset_release_report.json and reference it from the manifest.",
    )
    parser.add_argument(
        "--write-dataset-release-pack",
        action="store_true",
        help="Write dataset_release_pack.json with artifact hashes and release evidence.",
    )
    parser.add_argument(
        "--write-release-quality-audit",
        action="store_true",
        help="Write release_quality_audit.json with release evidence risk signals.",
    )
    parser.add_argument(
        "--write-qualification-report",
        action="store_true",
        help=(
            "Write qualification_report.json by evaluating the exact release "
            "Release Candidate evidence boundary."
        ),
    )
    parser.add_argument(
        "--write-release-review-queue",
        action="store_true",
        help="Write release_review_queue.jsonl for release-quality audit watch signals.",
    )
    parser.add_argument(
        "--write-dataset-release-card",
        action="store_true",
        help="Write dataset_release_card.md for human review of release evidence.",
    )
    args = parser.parse_args()
    if args.write_dataset_release_pack and not args.write_dataset_release_report:
        parser.error("--write-dataset-release-pack requires --write-dataset-release-report")
    if args.write_release_quality_audit and not args.write_dataset_release_report:
        parser.error("--write-release-quality-audit requires --write-dataset-release-report")
    if args.write_qualification_report and not args.write_dataset_release_pack:
        parser.error(
            "--write-qualification-report requires --write-dataset-release-pack"
        )
    if args.write_qualification_report and not args.write_release_quality_audit:
        parser.error(
            "--write-qualification-report requires --write-release-quality-audit"
        )
    if args.write_release_review_queue and not args.write_release_quality_audit:
        parser.error(
            "--write-release-review-queue requires --write-release-quality-audit"
        )
    if args.write_dataset_release_card and not args.write_dataset_release_report:
        parser.error("--write-dataset-release-card requires --write-dataset-release-report")
    if args.write_dataset_release_report:
        if not args.write_evaluation_report:
            parser.error("--write-dataset-release-report requires --write-evaluation-report")
        if not args.write_profile_decision_report:
            parser.error(
                "--write-dataset-release-report requires --write-profile-decision-report"
            )
    args.loaded_run_profile = _load_profile_or_error(parser, args.run_profile)
    if args.loaded_run_profile is None:
        args.dataset_version = args.dataset_version or "dataset_foundation_v1"
    elif args.dataset_version is None:
        args.dataset_version = args.loaded_run_profile.dataset_version

    if args.loaded_run_profile is not None:
        _validate_profile_cli_combinations(parser, args.loaded_run_profile, args)
    _validate_async_cli_combinations(parser, args.loaded_run_profile, args)
    coverage_preview_requested = (
        args.preview_coverage_plan or args.write_coverage_plan
    )
    if coverage_preview_requested and (
        args.loaded_run_profile is None
        or args.loaded_run_profile.coverage_profile is None
    ):
        parser.error(
            "--preview-coverage-plan and --write-coverage-plan require a run "
            "profile with coverage_profile"
        )
    if args.enable_network_source:
        if not args.source_url:
            parser.error("--enable-network-source requires --source-url")
        if not args.source_license_label:
            parser.error("--enable-network-source requires --source-license-label")
        if not args.allowed_source_host:
            parser.error("--enable-network-source requires --allowed-source-host")
    return args


def main() -> int:
    args = parse_args()
    profile: RunProfile | None = args.loaded_run_profile
    source_bundle = (
        build_external_fixture_source_bundle(network_enabled=True)
        if _feature_enabled(args, profile, "enable_source_governance_fixture")
        else None
    )
    domain_environment_input = None
    source_events = None
    profile_source_summary = None
    if profile is not None and profile.source is not None:
        try:
            importer = resolve_domain_source_importer(
                profile.seed.domain,
                profile.source.kind,
            )
            profile_source = build_profile_local_domain_source_input(
                ProfileLocalDomainSourceRequest(
                    domain_id=importer.domain_id,
                    kind=profile.source.kind,
                    source_id=profile.source.source_id,
                    path=profile.source.resolved_path,
                    license_label=profile.source.license_label,
                    max_bytes=profile.source.max_bytes,
                ),
                importer=importer,
            )
        except (ControlledSourceFetchError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        source_bundle = profile_source.source_bundle
        domain_environment_input = profile_source.environment_input
        source_events = profile_source.events
        profile_source_summary = profile_source.source_summary
    if args.enable_network_source:
        try:
            network_source = build_network_contacts_source_input(
                FetchedSourceRequest(
                    url=args.source_url,
                    allowed_hosts=tuple(args.allowed_source_host),
                    request_budget=1,
                    timeout_seconds=args.source_timeout_seconds,
                    max_bytes=args.source_max_bytes,
                    expected_content_type="application/json",
                    license_label=args.source_license_label,
                    require_source_audit=True,
                ),
                http_client=(
                    _FixtureHttpClient(args.mock_source_fixture)
                    if args.mock_source_fixture is not None
                    else None
                ),
            )
        except ControlledSourceFetchError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        source_bundle = network_source.source_bundle
        domain_environment_input = network_source.environment_input
        source_events = network_source.events
    if args.preview_coverage_plan or args.write_coverage_plan:
        assert profile is not None
        try:
            plan = preview_coverage_plan(
                profile,
                admitted_environment_input=domain_environment_input,
                output_path=(
                    args.output_dir / "coverage_plan.json"
                    if args.write_coverage_plan
                    else None
                ),
            )
        except (CoveragePlanValidationError, ValueError) as exc:
            print(f"coverage plan validation failed: {exc}", file=sys.stderr)
            return 1
        if args.preview_coverage_plan:
            sys.stdout.write(plan.to_bytes().decode("utf-8"))
        elif args.write_coverage_plan:
            print(f"Coverage plan written: {args.output_dir / 'coverage_plan.json'}")
        return 0
    start_time = time.perf_counter() if args.write_profile_decision_report else None
    async_job_result: SerialJobResult | None = None
    if args.enable_async_runner:
        assert profile is not None
        try:
            async_job_result = _run_async_job(
                args,
                profile=profile,
                source_bundle=source_bundle,
                domain_environment_input=domain_environment_input,
                source_events=source_events,
                profile_source_summary=profile_source_summary,
            )
            if async_job_result.pipeline_result is None:
                if async_job_result.status == "cancelled":
                    _print_async_job_status(async_job_result)
                    return 0
                raise OrchestrationError(
                    "async job did not produce inspectable pipeline artifacts"
                )
            result = async_job_result.pipeline_result
        except (LLMConfigurationError, LLMProviderError, OrchestrationError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        coverage_scheduler_factory = None
        if profile is not None and profile.coverage_profile is not None:
            candidate_generator = None
            candidate_generator_factory = None
            coverage_scheduler_factory = (
                build_coverage_assignment_scheduler_factory(
                    OpenAICompatibleClient(LLMConfig.from_env())
                )
            )
        else:
            candidate_generator, candidate_generator_factory = (
                _profile_candidate_generators(
                    profile,
                    use_llm=args.use_llm,
                )
            )
        task_expansion_generator = (
            build_llm_task_expansion_generator()
            if args.use_llm and _feature_enabled(args, profile, "enable_task_expansion")
            else None
        )
        refiner = (
            deterministic_fixture_refiner
            if _feature_enabled(args, profile, "enable_refinement")
            else None
        )
        try:
            result = run_foundation_pipeline(
                args.output_dir,
                dataset_version=args.dataset_version,
                candidate_generator=candidate_generator,
                candidate_generator_factory=candidate_generator_factory,
                coverage_scheduler_factory=(
                    coverage_scheduler_factory
                ),
                parent_artifact_path=args.parent_artifact,
                refiner=refiner,
                enable_branching=_feature_enabled(args, profile, "enable_branching"),
                enable_task_expansion=_feature_enabled(args, profile, "enable_task_expansion"),
                task_expansion_generator=task_expansion_generator,
                source_bundle=source_bundle,
                enable_source_audit=(
                    _feature_enabled(args, profile, "enable_source_governance_fixture")
                    or args.enable_network_source
                    or (profile is not None and profile.source is not None)
                ),
                domain_environment_input=domain_environment_input,
                source_events=source_events,
                enable_mcp_adapter=_feature_enabled(args, profile, "enable_mcp_adapter"),
                enable_sandbox_fixture=_feature_enabled(args, profile, "enable_sandbox_fixture"),
                seed_override=profile.seed if profile is not None else None,
                run_profile_metadata=(
                    profile.sanitized_metadata(source_summary=profile_source_summary)
                    if profile is not None
                    else None
                ),
                run_profile=profile,
                write_episode_logs=(
                    args.write_episode_quality_report
                    or args.write_episode_replay_report
                    or args.write_reward_label_report
                ),
            )
        except (LLMConfigurationError, LLMProviderError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    episodes = None
    episode_quality_report = None
    episode_quality_report_path = None
    if args.write_episode_quality_report:
        assert result.episode_logs_path is not None
        episodes = read_episode_logs(result.episode_logs_path)
        episode_quality_report = build_episode_quality_report(
            dataset_version=args.dataset_version,
            episodes=episodes,
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        episode_quality_report_path = result.manifest_path.parent / EPISODE_QUALITY_REPORT_FILENAME
        episode_quality_report_path = write_episode_quality_report(
            episode_quality_report_path,
            dataset_version=args.dataset_version,
            episodes=episodes,
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        attach_episodes_to_manifest(
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        attach_episode_quality_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=episode_quality_report_path,
        )

    episode_replay_report = None
    episode_replay_report_path = None
    if args.write_episode_replay_report:
        assert result.episode_logs_path is not None
        if episodes is None:
            episodes = read_episode_logs(result.episode_logs_path)
        episode_replay_report = build_episode_replay_report(
            dataset_version=args.dataset_version,
            episodes=episodes,
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        episode_replay_report_path = result.manifest_path.parent / EPISODE_REPLAY_REPORT_FILENAME
        episode_replay_report_path = write_episode_replay_report(
            episode_replay_report_path,
            dataset_version=args.dataset_version,
            episodes=episodes,
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        attach_episodes_to_manifest(
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        attach_episode_replay_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=episode_replay_report_path,
        )

    reward_label_report_path = None
    if args.write_reward_label_report:
        assert result.episode_logs_path is not None
        if episodes is None:
            episodes = read_episode_logs(result.episode_logs_path)
        if episode_quality_report is None:
            episode_quality_report = build_episode_quality_report(
                dataset_version=args.dataset_version,
                episodes=episodes,
                manifest_path=result.manifest_path,
                episodes_path=result.episode_logs_path,
            )
        if episode_replay_report is None:
            episode_replay_report = build_episode_replay_report(
                dataset_version=args.dataset_version,
                episodes=episodes,
                manifest_path=result.manifest_path,
                episodes_path=result.episode_logs_path,
            )
        reward_labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=episode_quality_report,
            episode_replay_report=episode_replay_report,
        )
        reward_labels_path = result.manifest_path.parent / REWARD_LABELS_FILENAME
        reward_labels_path = write_reward_labels(reward_labels_path, reward_labels)
        reward_label_report_path = result.manifest_path.parent / REWARD_LABEL_REPORT_FILENAME
        reward_label_report_path = write_reward_label_report(
            reward_label_report_path,
            dataset_version=args.dataset_version,
            episodes=episodes,
            labels=reward_labels,
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
            episode_quality_report_path=episode_quality_report_path,
            episode_replay_report_path=episode_replay_report_path,
            reward_labels_path=reward_labels_path,
        )
        attach_episodes_to_manifest(
            manifest_path=result.manifest_path,
            episodes_path=result.episode_logs_path,
        )
        attach_reward_labels_to_manifest(
            manifest_path=result.manifest_path,
            labels_path=reward_labels_path,
        )
        attach_reward_label_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=reward_label_report_path,
        )

    evaluation_report_path = None
    if args.write_evaluation_report:
        evaluation_report_path = write_evaluation_report(
            manifest_path=result.manifest_path,
            quality_report_path=result.quality_report_path,
        )
        attach_evaluation_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=evaluation_report_path,
        )

    profile_decision_report_path = None
    if args.write_profile_decision_report:
        assert start_time is not None
        profile_decision_report_path = write_profile_decision_report(
            manifest_path=result.manifest_path,
            quality_report_path=result.quality_report_path,
            parent_comparison_path=result.parent_comparison_path,
            evaluation_report_path=evaluation_report_path,
            runtime_seconds=time.perf_counter() - start_time,
        )
        attach_profile_decision_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=profile_decision_report_path,
        )

    dataset_release_report_path = None
    if args.write_dataset_release_report:
        dataset_release_report_path = write_dataset_release_report(
            manifest_path=result.manifest_path,
            quality_report_path=result.quality_report_path,
            evaluation_report_path=evaluation_report_path,
            profile_decision_report_path=profile_decision_report_path,
        )
        attach_dataset_release_report_to_manifest(
            manifest_path=result.manifest_path,
            report_path=dataset_release_report_path,
        )

    release_quality_audit_path = None
    release_review_queue_path = None
    if args.write_release_quality_audit:
        assert dataset_release_report_path is not None
        release_quality_audit_path = result.manifest_path.parent / RELEASE_QUALITY_AUDIT_FILENAME
        release_quality_audit_path = write_release_quality_audit(
            manifest_path=result.manifest_path,
            output_path=release_quality_audit_path,
        )
        attach_release_quality_audit_to_manifest(
            manifest_path=result.manifest_path,
            audit_path=release_quality_audit_path,
        )
        if args.write_release_review_queue:
            release_review_queue_path = _write_release_review_queue_for_audit(
                manifest_path=result.manifest_path,
                audit_path=release_quality_audit_path,
            )

    dataset_release_pack_path = None
    if args.write_dataset_release_pack:
        assert dataset_release_report_path is not None
        dataset_release_pack_path = result.manifest_path.parent / DATASET_RELEASE_PACK_FILENAME
        release_pack_error = _dataset_release_pack_preflight_error(dataset_release_report_path)
        if release_pack_error is not None:
            print(release_pack_error, file=sys.stderr)
            return 1
        attach_dataset_release_pack_to_manifest(
            manifest_path=result.manifest_path,
            pack_path=dataset_release_pack_path,
        )
        try:
            write_dataset_release_pack(
                manifest_path=result.manifest_path,
                dataset_release_report_path=dataset_release_report_path,
                output_path=dataset_release_pack_path,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    dataset_release_card_path = None
    if args.write_dataset_release_card:
        assert dataset_release_report_path is not None
        dataset_release_card_path = result.manifest_path.parent / DATASET_RELEASE_CARD_FILENAME
        dataset_release_card_path = write_dataset_release_card(
            manifest_path=result.manifest_path,
            output_path=dataset_release_card_path,
        )
        attach_dataset_release_card_to_manifest(
            manifest_path=result.manifest_path,
            card_path=dataset_release_card_path,
        )
        if dataset_release_pack_path is not None:
            try:
                write_dataset_release_pack(
                    manifest_path=result.manifest_path,
                    dataset_release_report_path=dataset_release_report_path,
                    output_path=dataset_release_pack_path,
                )
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1

    qualification_report_path = None
    if args.write_qualification_report:
        assert dataset_release_pack_path is not None
        qualification_report_path = (
            result.manifest_path.parent / QUALIFICATION_REPORT_FILENAME
        )
        qualification_report_path = write_release_candidate_qualification(
            manifest_path=result.manifest_path,
            release_pack_path=dataset_release_pack_path,
            release_quality_audit_path=release_quality_audit_path,
            output_path=qualification_report_path,
        )

    print(
        "Foundation pipeline complete: "
        f"accepted={result.accepted_count} "
        f"rejected={result.rejected_count} "
        f"manifest={result.manifest_path}"
        + (
            f" evaluation_report={evaluation_report_path}"
            if evaluation_report_path is not None
            else ""
        )
        + (
            f" episode_quality_report={episode_quality_report_path}"
            if episode_quality_report_path is not None
            else ""
        )
        + (
            f" episode_replay_report={episode_replay_report_path}"
            if episode_replay_report_path is not None
            else ""
        )
        + (
            f" reward_label_report={reward_label_report_path}"
            if reward_label_report_path is not None
            else ""
        )
        + (
            f" profile_decision_report={profile_decision_report_path}"
            if profile_decision_report_path is not None
            else ""
        )
        + (
            f" dataset_release_report={dataset_release_report_path}"
            if dataset_release_report_path is not None
            else ""
        )
        + (
            f" mutation_admission_report={result.mutation_admission_report_path}"
            if result.mutation_admission_report_path is not None
            else ""
        )
        + (
            f" dataset_release_pack={dataset_release_pack_path}"
            if dataset_release_pack_path is not None
            else ""
        )
        + (
            f" release_quality_audit={release_quality_audit_path}"
            if release_quality_audit_path is not None
            else ""
        )
        + (
            f" release_review_queue={release_review_queue_path}"
            if release_review_queue_path is not None
            else ""
        )
        + (
            f" dataset_release_card={dataset_release_card_path}"
            if dataset_release_card_path is not None
            else ""
        )
        + (
            f" qualification_report={qualification_report_path}"
            if qualification_report_path is not None
            else ""
        )
    )
    if async_job_result is not None:
        _print_async_job_status(async_job_result)
    return 0


def _write_release_review_queue_for_audit(
    *,
    manifest_path: Path,
    audit_path: Path,
) -> Path | None:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    queue_path = write_release_review_queue(
        audit,
        output_path=manifest_path.parent / RELEASE_REVIEW_QUEUE_FILENAME,
    )
    if queue_path is None:
        return None
    attach_release_review_queue_to_manifest(
        manifest_path=manifest_path,
        queue_path=queue_path,
    )
    return queue_path


def _load_profile_or_error(
    parser: argparse.ArgumentParser,
    profile_path: Path | None,
) -> RunProfile | None:
    if profile_path is None:
        return None
    try:
        return load_run_profile(profile_path)
    except FileNotFoundError:
        parser.error(f"run profile not found: {profile_path}")
    except RunProfileValidationError as exc:
        parser.error(f"invalid run profile: {exc}")


def _positive_int_argument(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    try:
        return validate_concurrency(parsed)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_logical_call_budget_argument(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "logical_call_budget must be a positive integer"
        )
    return parsed


def _validate_async_cli_combinations(
    parser: argparse.ArgumentParser,
    profile: RunProfile | None,
    args: argparse.Namespace,
) -> None:
    async_only_options = (
        (args.job_id is not None, "--job-id"),
        (args.resume, "--resume"),
        (args.max_concurrency is not None, "--max-concurrency"),
        (args.recover_stale_lock, "--recover-stale-lock"),
        (args.logical_call_budget is not None, "--logical-call-budget"),
        (args.provider_alias is not None, "--provider-alias"),
        (args.model_alias is not None, "--model-alias"),
    )
    if not args.enable_async_runner:
        for supplied, option in async_only_options:
            if supplied:
                parser.error(f"{option} requires --enable-async-runner")
        return

    if profile is None:
        parser.error("--enable-async-runner requires --run-profile")
    if args.job_id is None:
        parser.error("--enable-async-runner requires --job-id")
    if args.recover_stale_lock and not args.resume:
        parser.error("--recover-stale-lock requires --resume")
    if args.preview_coverage_plan or args.write_coverage_plan:
        parser.error(
            "coverage-plan preview and async orchestration are mutually exclusive"
        )
    if args.enable_task_expansion or args.enable_refinement:
        parser.error(
            "async orchestration does not support task expansion or refinement"
        )

    assert profile is not None
    for feature_name in (
        "enable_branching",
        "enable_mcp_adapter",
        "enable_sandbox_fixture",
        "enable_source_governance_fixture",
    ):
        if getattr(args, feature_name) and not getattr(profile.features, feature_name):
            parser.error(
                f"--{feature_name.replace('_', '-')} must be declared in the "
                "run profile for async orchestration"
            )

    if profile.generation.mode == "llm":
        if args.logical_call_budget is None:
            parser.error(
                "async llm orchestration requires --logical-call-budget"
            )
    elif any(
        supplied
        for supplied, option in async_only_options
        if option
        in {
            "--logical-call-budget",
            "--provider-alias",
            "--model-alias",
        }
    ):
        parser.error(
            "provider aliases and logical-call authorization require llm generation"
        )


def _run_async_job(
    args: argparse.Namespace,
    *,
    profile: RunProfile,
    source_bundle: object | None,
    domain_environment_input: object | None,
    source_events: list[dict[str, object]] | None,
    profile_source_summary: dict[str, object] | None,
) -> SerialJobResult:
    if args.dataset_version != profile.dataset_version:
        profile = profile.with_dataset_version(args.dataset_version)

    candidate_generator = None
    if profile.generation.mode != "llm":
        candidate_generator, _ = _profile_candidate_generators(
            profile,
            use_llm=False,
        )

    provider_factory = None
    provider_alias = None
    model_alias = None
    authorization_limits = None
    if profile.generation.mode == "llm":
        provider_config = LLMConfig.from_env()
        provider_alias = args.provider_alias or "openai_compatible"
        model_alias = args.model_alias or provider_config.model
        authorization_limits = {
            "logical_call_budget": args.logical_call_budget,
        }

        def build_provider() -> OpenAICompatibleClient:
            return OpenAICompatibleClient(provider_config)

        provider_factory = build_provider

    cancellation_signal = CancellationSignal()
    common_kwargs: _AsyncJobKwargs = {
        "output_dir": args.output_dir,
        "job_id": args.job_id,
        "run_profile": profile,
        "resume": args.resume,
        "candidate_generator": candidate_generator,
        "source_bundle": source_bundle,
        "domain_environment_input": domain_environment_input,
        "source_events": source_events,
        "enable_source_audit": (
            args.enable_network_source
            or profile.source is not None
            or profile.features.enable_source_governance_fixture
        ),
        "run_profile_metadata": profile.sanitized_metadata(
            source_summary=profile_source_summary,
        ),
        "parent_artifact_path": args.parent_artifact,
        "write_episode_logs": (
            args.write_episode_quality_report
            or args.write_episode_replay_report
            or args.write_reward_label_report
        ),
        "authorization_limits": authorization_limits,
        "recover_stale_lock": args.recover_stale_lock,
        "provider_factory": provider_factory,
        "provider_alias": provider_alias,
        "model_alias": model_alias,
        "cancellation_signal": cancellation_signal,
    }
    with _async_signal_handlers(cancellation_signal):
        if args.max_concurrency is None:
            return run_serial_job(**common_kwargs)
        return run_serial_job(
            **common_kwargs,
            max_concurrency=args.max_concurrency,
        )


@contextmanager
def _async_signal_handlers(
    cancellation_signal: CancellationSignal,
) -> Iterator[None]:
    previous_handlers: dict[int, Any] = {}

    def request_cancellation(_signum: int, _frame: Any) -> None:
        cancellation_signal.cancel()

    for registered_signal in (signal.SIGINT, signal.SIGTERM):
        signal_number = int(registered_signal)
        previous_handlers[signal_number] = signal.getsignal(registered_signal)
        signal.signal(registered_signal, request_cancellation)
    try:
        yield
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)


def _print_async_job_status(async_job_result: SerialJobResult) -> None:
    print(
        "Async synthesis job: "
        f"job_id={async_job_result.job_record['job_id']} "
        f"status={async_job_result.status} "
        f"max_concurrency={async_job_result.max_concurrency} "
        f"job={async_job_result.job_path} "
        f"events={async_job_result.events_path} "
        f"provider_usage={async_job_result.provider_usage_path}"
    )


def _validate_profile_cli_combinations(
    parser: argparse.ArgumentParser,
    profile: RunProfile,
    args: argparse.Namespace,
) -> None:
    coverage_preview_requested = (
        args.preview_coverage_plan or args.write_coverage_plan
    )
    if (
        profile.generation.mode == "llm"
        and not args.use_llm
        and not coverage_preview_requested
    ):
        parser.error('run profile generation.mode="llm" requires --use-llm')
    if profile.generation.mode != "llm" and args.use_llm:
        parser.error("--use-llm requires run profile generation.mode=\"llm\"")
    if args.enable_network_source and profile.features.enable_source_governance_fixture:
        parser.error(
            "run profile enable_source_governance_fixture conflicts with --enable-network-source"
        )
    if args.enable_network_source and profile.seed.domain not in {"contacts", "contacts_fixture"}:
        parser.error("--enable-network-source is contacts-only for run profiles")
    if profile.source is not None:
        if args.enable_network_source:
            parser.error("profile source conflicts with --enable-network-source")
        if args.enable_source_governance_fixture or profile.features.enable_source_governance_fixture:
            parser.error(
                "profile source conflicts with enable_source_governance_fixture"
            )

def _profile_candidate_generators(
    profile: RunProfile | None,
    *,
    use_llm: bool,
):
    if profile is None:
        return (build_llm_candidate_generator() if use_llm else None, None)
    if profile.generation.mode == "llm":
        if profile.schema_version in REPRESENTATIVE_RUN_PROFILE_SCHEMA_VERSIONS:
            assert profile.generation.target_candidate_count is not None
            return (
                None,
                build_domain_llm_candidate_generator_factory(
                    profile.generation.target_candidate_count
                ),
            )
        return build_llm_candidate_generator(), None
    if profile.generation.mode == "deterministic_scale_probe":
        assert profile.generation.target_candidate_count is not None
        return (
            lambda seed: generate_scale_probe_candidates(
                seed,
                profile.generation.target_candidate_count,
            ),
            None,
        )
    return None, None


def _feature_enabled(
    args: argparse.Namespace,
    profile: RunProfile | None,
    feature_name: str,
) -> bool:
    cli_enabled = bool(getattr(args, feature_name))
    profile_enabled = bool(getattr(profile.features, feature_name)) if profile else False
    return cli_enabled or profile_enabled


def _dataset_release_pack_preflight_error(dataset_release_report_path: Path) -> str | None:
    report = json.loads(dataset_release_report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        return "dataset_release_report must be a JSON object"
    decisions = report.get("decisions")
    if not isinstance(decisions, dict):
        return "dataset_release_report decisions must be an object"
    dataset_release = decisions.get("dataset_release")
    if not isinstance(dataset_release, dict):
        return "dataset_release_report decisions.dataset_release must be an object"
    if dataset_release.get("status") != "passed":
        return "dataset_release_report decisions.dataset_release.status must be passed"
    release_completeness = report.get("release_completeness")
    if not isinstance(release_completeness, dict):
        return "dataset_release_report release_completeness must be an object"
    completeness_decision = release_completeness.get("decision")
    if not isinstance(completeness_decision, dict):
        return "dataset_release_report release_completeness.decision must be an object"
    if completeness_decision.get("status") != "passed":
        return "dataset_release_report release_completeness.decision.status must be passed"
    return None


class _FixtureHttpResponse:
    status_code = 200

    def __init__(self, body: bytes) -> None:
        self.headers = {"content-type": "application/json"}
        self.content = body


class _FixtureHttpClient:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def get(
        self,
        url: str,
        *,
        timeout: float,
        follow_redirects: bool,
    ) -> _FixtureHttpResponse:
        return _FixtureHttpResponse(self.fixture_path.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
