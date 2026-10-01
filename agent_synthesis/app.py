"""Public command composition for the Agent-first synthesis engine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from agent_synthesis.builtin_domains import builtin_domain, builtin_fixture_domains
from agent_synthesis.cli import import_review_labels_cli, run_cli
from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.engine import SynthesisEngine
from agent_synthesis.model import (
    DeterministicJsonModelAdapter,
    OpenAICompatibleJsonAdapter,
)
from agent_synthesis.registry import AdapterRegistry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent-first data synthesis")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--configuration", required=True, type=Path)
        command.add_argument("--output-directory", required=True, type=Path)
        command.add_argument("--source", type=Path)
        model = command.add_mutually_exclusive_group(required=True)
        model.add_argument("--fixture-responses", type=Path)
        model.add_argument("--authorize-live-provider", action="store_true")
        command.add_argument("--authorization-id")
        command.add_argument("--model-version", default="provider-version-unavailable")
        command.add_argument("--remote-model")
    replay = commands.add_parser("replay")
    replay.add_argument("--output-directory", required=True, type=Path)
    queue = commands.add_parser("create-review-queue")
    queue.add_argument("--output-directory", required=True, type=Path)
    queue.add_argument("--cohort-id", required=True)
    queue.add_argument(
        "--purpose",
        required=True,
        choices=("calibration-development", "held-out-evaluation"),
    )
    review = commands.add_parser("import-review-labels")
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--labels", required=True, type=Path)
    return parser


def _configuration(path: Path) -> RunConfiguration:
    record = json.loads(path.read_text(encoding="utf-8"))
    return RunConfiguration.model_validate(record)


def _model(args: argparse.Namespace, configuration: RunConfiguration) -> object:
    if args.fixture_responses is not None:
        if args.authorization_id is not None:
            raise ValueError("fixture responses cannot carry a live authorization")
        if configuration.max_concurrency != 1:
            raise ValueError("scripted fixture responses require max_concurrency=1")
        responses = [
            json.loads(line)
            for line in args.fixture_responses.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return DeterministicJsonModelAdapter(
            model_id=configuration.model_id,
            model_version="fixture-v1",
            responses=responses,
        )
    if not args.authorization_id or not args.authorization_id.strip():
        raise ValueError("live provider requires a non-secret authorization ID")
    base_url = os.environ.get("AGENT_DATA_LLM_BASE_URL")
    api_key = os.environ.get("AGENT_DATA_API_KEY")
    remote_model = args.remote_model or os.environ.get("AGENT_DATA_LLM_MODEL")
    if not base_url or not api_key or not remote_model:
        raise ValueError("live provider requires base URL, API key, and remote model")
    return OpenAICompatibleJsonAdapter(
        model_id=configuration.model_id,
        model_version=args.model_version,
        base_url=base_url,
        api_key=api_key,
        remote_model=remote_model,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "import-review-labels":
        engine = SynthesisEngine(AdapterRegistry(domains=(), models=()))
        import_review_labels_cli(
            engine,
            ["--output-directory", str(args.output_directory), "--labels", str(args.labels)],
        )
        return 0
    if args.command == "create-review-queue":
        engine = SynthesisEngine(AdapterRegistry(domains=(), models=()))
        result = engine.create_review_queue(args.output_directory, {
            "cohort_id": args.cohort_id,
            "purpose": args.purpose,
        })
        print(json.dumps({
            "cohort_id": result.cohort.cohort_id,
            "episode_count": len(result.cohort.episode_ids),
            "queue": str(result.queue_path),
        }, sort_keys=True))
        return 0
    if args.command == "replay":
        engine = SynthesisEngine(
            AdapterRegistry(domains=builtin_fixture_domains(), models=())
        )
        result = engine.replay(args.output_directory)
        print(json.dumps({
            "aligned": result.aligned,
            "episode_count": len(result.episode_results),
            "report": str(result.report_path),
        }, sort_keys=True))
        return 0 if result.aligned else 2
    configuration = _configuration(args.configuration)
    domain = builtin_domain(configuration.domain_id, args.source)
    model = _model(args, configuration)
    engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
    cli_args = [
        "--configuration", str(args.configuration),
        "--output-directory", str(args.output_directory),
    ]
    if args.command == "resume":
        cli_args.append("--resume")
    result = run_cli(engine, cli_args)
    return 0 if result.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
