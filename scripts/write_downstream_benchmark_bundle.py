from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contracts import ContractValidationError
from synthesis.downstream_benchmark import (
    BenchmarkMetric,
    BenchmarkProtocol,
    write_downstream_benchmark_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bind a verified release pack to a benchmark protocol.")
    parser.add_argument("--release-pack", type=Path, required=True)
    parser.add_argument("--benchmark-suite-id", required=True)
    parser.add_argument("--benchmark-suite-version", required=True)
    parser.add_argument("--primary-metric", default="task_success_rate")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.primary_metric != "task_success_rate":
        print("error=unsupported_primary_metric", file=sys.stderr)
        return 1
    protocol = BenchmarkProtocol(
        protocol_version="external_agent_benchmark_v1",
        benchmark_suite_id=args.benchmark_suite_id,
        benchmark_suite_version=args.benchmark_suite_version,
        primary_metric=args.primary_metric,
        metrics=(BenchmarkMetric("task_success_rate", "higher_is_better", 0.0, 1.0),),
    )
    try:
        output = write_downstream_benchmark_bundle(
            release_pack_path=args.release_pack,
            protocol=protocol,
            output_path=args.output,
        )
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        print(f"error={type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"downstream_benchmark_bundle={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
