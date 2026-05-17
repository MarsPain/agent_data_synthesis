from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synthesis.llm import LLMConfigurationError, LLMProviderError
from synthesis.pipeline import (
    build_llm_candidate_generator,
    build_llm_task_expansion_generator,
    run_foundation_pipeline,
)
from synthesis.refinement import deterministic_fixture_refiner
from synthesis.sources import build_external_fixture_source_bundle
from synthesis.sources import (
    ControlledSourceFetchError,
    FetchedSourceRequest,
    build_network_contacts_source_input,
)


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
        "--dataset-version",
        default="dataset_foundation_v1",
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
    args = parser.parse_args()
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
    candidate_generator = build_llm_candidate_generator() if args.use_llm else None
    task_expansion_generator = (
        build_llm_task_expansion_generator()
        if args.use_llm and args.enable_task_expansion
        else None
    )
    refiner = deterministic_fixture_refiner if args.enable_refinement else None
    source_bundle = (
        build_external_fixture_source_bundle(network_enabled=True)
        if args.enable_source_governance_fixture
        else None
    )
    contacts_environment_input = None
    source_events = None
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
    try:
        result = run_foundation_pipeline(
            args.output_dir,
            dataset_version=args.dataset_version,
            candidate_generator=candidate_generator,
            parent_artifact_path=args.parent_artifact,
            refiner=refiner,
            enable_branching=args.enable_branching,
            enable_task_expansion=args.enable_task_expansion,
            task_expansion_generator=task_expansion_generator,
            source_bundle=source_bundle,
            enable_source_audit=(
                args.enable_source_governance_fixture or args.enable_network_source
            ),
            contacts_environment_input=contacts_environment_input,
            source_events=source_events,
        )
    except (LLMConfigurationError, LLMProviderError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "Foundation pipeline complete: "
        f"accepted={result.accepted_count} "
        f"rejected={result.rejected_count} "
        f"manifest={result.manifest_path}"
    )
    return 0


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
