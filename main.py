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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_generator = build_llm_candidate_generator() if args.use_llm else None
    task_expansion_generator = (
        build_llm_task_expansion_generator()
        if args.use_llm and args.enable_task_expansion
        else None
    )
    refiner = deterministic_fixture_refiner if args.enable_refinement else None
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


if __name__ == "__main__":
    raise SystemExit(main())
