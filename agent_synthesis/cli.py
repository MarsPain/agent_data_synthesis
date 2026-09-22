"""Thin command-line adapter for an application-supplied Agent-first engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from agent_synthesis.configuration import RunConfiguration
from agent_synthesis.engine import ReviewLabelImportResult, RunResult, SynthesisEngine


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse only file locations and lifecycle selection; the engine owns behavior."""

    parser = argparse.ArgumentParser(description="Run or resume Agent-first synthesis.")
    parser.add_argument(
        "--configuration",
        required=True,
        type=Path,
        help="Path to a validated public Agent-first run configuration JSON file.",
    )
    parser.add_argument(
        "--output-directory",
        required=True,
        type=Path,
        help="Run directory to create or resume.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the durable run in --output-directory.",
    )
    return parser.parse_args(argv)


def run_cli(
    engine: SynthesisEngine,
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> RunResult:
    """Load configuration, delegate one lifecycle call, and print sanitized status."""

    args = parse_args(argv)
    configuration = _read_configuration(args.configuration)
    result = (
        engine.resume(configuration, args.output_directory)
        if args.resume
        else engine.run(configuration, args.output_directory)
    )
    stream = stdout or sys.stdout
    stream.write(
        json.dumps(
            {
                "status": result.status,
                "partial_reason": result.partial_reason,
                "task_attempt_count": result.task_attempt_count,
                "terminal_outcome_count": result.terminal_outcome_count,
                "accepted_count": result.demonstration_count,
                "negative_count": result.negative_count,
                "physical_request_count": result.physical_request_count,
            },
            sort_keys=True,
        )
        + "\n"
    )
    return result


def main(
    engine: SynthesisEngine,
    argv: Sequence[str] | None = None,
) -> int:
    """Run the injected engine and expose non-completed statuses to shell callers."""

    result = run_cli(engine, argv)
    return 0 if result.status == "completed" else 2


def parse_review_import_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse only completed-run and reviewer-owned label locations."""

    parser = argparse.ArgumentParser(description="Import Agent-first blind-review labels.")
    parser.add_argument(
        "--output-directory",
        required=True,
        type=Path,
        help="Completed Agent-first run directory containing frozen review cohorts.",
    )
    parser.add_argument(
        "--labels",
        required=True,
        type=Path,
        help="Reviewer-owned JSONL labels bound to the frozen blind-review queue.",
    )
    return parser.parse_args(argv)


def import_review_labels_cli(
    engine: SynthesisEngine,
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> ReviewLabelImportResult:
    """Delegate direct-human import without exposing private run state to the CLI."""

    args = parse_review_import_args(argv)
    result = engine.import_review_labels(args.output_directory, args.labels)
    stream = stdout or sys.stdout
    stream.write(
        json.dumps(
            {
                "status": result.status,
                "complete": result.complete,
                "human_approved_episode_ids": result.human_approved_episode_ids,
            },
            sort_keys=True,
        )
        + "\n"
    )
    return result


def _read_configuration(path: Path) -> RunConfiguration:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read Agent-first configuration: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("Agent-first configuration must be a JSON object")
    return RunConfiguration.model_validate(payload)
