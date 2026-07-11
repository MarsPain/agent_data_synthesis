from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contracts import ContractValidationError
from synthesis.downstream_benchmark import import_downstream_benchmark_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a sanitized external benchmark observation.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = import_downstream_benchmark_result(
            bundle_path=args.bundle,
            observation_path=args.observation,
            output_path=args.output,
        )
        result = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        print(f"error={type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"downstream_benchmark_result={output}")
    return 1 if result["decision"]["status"] == "insufficient_evidence" else 0


if __name__ == "__main__":
    raise SystemExit(main())
