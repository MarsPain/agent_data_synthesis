from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from synthesis.datasets import (
    attach_evaluation_report_to_manifest,
    attach_profile_decision_report_to_manifest,
)
from synthesis.evaluation import write_evaluation_report
from synthesis.llm import LLMConfigurationError, LLMProviderError
from synthesis.pipeline import (
    build_llm_candidate_generator,
    build_llm_task_expansion_generator,
    run_foundation_pipeline,
)
from synthesis.profile_decisions import write_profile_decision_report
from synthesis.refinement import deterministic_fixture_refiner
from synthesis.run_profiles import RunProfile, RunProfileValidationError, load_run_profile
from synthesis.sources import build_external_fixture_source_bundle
from synthesis.sources import (
    ControlledSourceFetchError,
    FetchedSourceRequest,
    ProfileLocalContactsSourceRequest,
    build_network_contacts_source_input,
    build_profile_local_contacts_source_input,
)
from synthesis.tasks import generate_scale_probe_candidates


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
        help="Validated run_profile_v1 or run_profile_v2 JSON file for configuring a local run.",
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
    args = parser.parse_args()
    args.loaded_run_profile = _load_profile_or_error(parser, args.run_profile)
    if args.loaded_run_profile is None:
        args.dataset_version = args.dataset_version or "dataset_foundation_v1"
    elif args.dataset_version is None:
        args.dataset_version = args.loaded_run_profile.dataset_version

    if args.loaded_run_profile is not None:
        _validate_profile_cli_combinations(parser, args.loaded_run_profile, args)

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
    candidate_generator = _profile_candidate_generator(profile, use_llm=args.use_llm)
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
    source_bundle = (
        build_external_fixture_source_bundle(network_enabled=True)
        if _feature_enabled(args, profile, "enable_source_governance_fixture")
        else None
    )
    contacts_environment_input = None
    source_events = None
    profile_source_summary = None
    if profile is not None and profile.source is not None:
        try:
            profile_source = build_profile_local_contacts_source_input(
                ProfileLocalContactsSourceRequest.from_run_profile_source(profile.source)
            )
        except ControlledSourceFetchError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        source_bundle = profile_source.source_bundle
        contacts_environment_input = profile_source.environment_input
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
        contacts_environment_input = network_source.environment_input
        source_events = network_source.events
    start_time = time.perf_counter() if args.write_profile_decision_report else None
    try:
        result = run_foundation_pipeline(
            args.output_dir,
            dataset_version=args.dataset_version,
            candidate_generator=candidate_generator,
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
            contacts_environment_input=contacts_environment_input,
            source_events=source_events,
            enable_mcp_adapter=_feature_enabled(args, profile, "enable_mcp_adapter"),
            enable_sandbox_fixture=_feature_enabled(args, profile, "enable_sandbox_fixture"),
            seed_override=profile.seed if profile is not None else None,
            run_profile_metadata=(
                profile.sanitized_metadata(source_summary=profile_source_summary)
                if profile is not None
                else None
            ),
        )
    except (LLMConfigurationError, LLMProviderError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

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
            f" profile_decision_report={profile_decision_report_path}"
            if profile_decision_report_path is not None
            else ""
        )
    )
    return 0


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


def _validate_profile_cli_combinations(
    parser: argparse.ArgumentParser,
    profile: RunProfile,
    args: argparse.Namespace,
) -> None:
    if profile.generation.mode == "llm" and not args.use_llm:
        parser.error('run profile generation.mode="llm" requires --use-llm')
    if profile.generation.mode != "llm" and args.use_llm:
        parser.error("--use-llm requires run profile generation.mode=\"llm\"")
    if args.enable_network_source and profile.features.enable_source_governance_fixture:
        parser.error(
            "run profile enable_source_governance_fixture conflicts with --enable-network-source"
        )
    if profile.source is not None:
        if args.enable_network_source:
            parser.error("profile source conflicts with --enable-network-source")
        if args.enable_source_governance_fixture or profile.features.enable_source_governance_fixture:
            parser.error(
                "profile source conflicts with enable_source_governance_fixture"
            )
        if profile.seed.domain != "contacts":
            parser.error("profile source requires seed.domain=\"contacts\"")


def _profile_candidate_generator(
    profile: RunProfile | None,
    *,
    use_llm: bool,
):
    if profile is None:
        return build_llm_candidate_generator() if use_llm else None
    if profile.generation.mode == "llm":
        return build_llm_candidate_generator()
    if profile.generation.mode == "deterministic_scale_probe":
        assert profile.generation.target_candidate_count is not None
        return lambda seed: generate_scale_probe_candidates(
            seed,
            profile.generation.target_candidate_count,
        )
    return None


def _feature_enabled(
    args: argparse.Namespace,
    profile: RunProfile | None,
    feature_name: str,
) -> bool:
    cli_enabled = bool(getattr(args, feature_name))
    profile_enabled = bool(getattr(profile.features, feature_name)) if profile else False
    return cli_enabled or profile_enabled


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
