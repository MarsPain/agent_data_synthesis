from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.llm import LLMConfig
from synthesis.mutation_activation import (
    MUTATION_ACTIVATION_REPORT_FILENAME,
    evaluate_mutation_activation,
    write_mutation_activation_report,
)
from synthesis.mutation_admission import (
    build_openai_compatible_semantic_mutation_judge,
)
from synthesis.mutation_admission_config import (
    parse_mutation_admission_judge_configuration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run three independent semantic-mutation judge evaluations over a "
            "human-reviewed corpus and write an activation or no-go report."
        )
    )
    parser.add_argument("--reviewed-corpus", type=Path, required=True)
    parser.add_argument("--judge-config", type=Path, required=True)
    parser.add_argument("--generator-model", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(MUTATION_ACTIVATION_REPORT_FILENAME),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        corpus = _load_mapping(args.reviewed_corpus)
        judge_configuration = parse_mutation_admission_judge_configuration(
            _load_mapping(args.judge_config)
        )
        provider_config = LLMConfig.from_env()
        judge = build_openai_compatible_semantic_mutation_judge(
            config=LLMConfig(
                base_url=provider_config.base_url,
                api_key=provider_config.api_key,
                model=judge_configuration.model,
                temperature=0.0,
            ),
            timeout_seconds=judge_configuration.timeout_seconds,
            max_retries=judge_configuration.max_retries,
        )
        report = evaluate_mutation_activation(
            corpus=corpus,
            generator_model=args.generator_model,
            judge_configuration=judge_configuration,
            judge=judge,
        )
        write_mutation_activation_report(args.output, report)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"mutation activation evaluation failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"activation_report={args.output}")
    print(f"decision={report['decision']}")
    print(f"report_hash={report['report_hash']}")
    return 0


def _load_mapping(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("mutation activation input must be an object")
    return dict(raw)


if __name__ == "__main__":
    raise SystemExit(main())
