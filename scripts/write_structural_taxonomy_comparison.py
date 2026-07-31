from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.structural_taxonomy import (
    write_structural_taxonomy_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify legacy and coverage-driven samples with one versioned "
            "structural taxonomy."
        )
    )
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--baseline-samples", type=Path, required=True)
    parser.add_argument("--campaign-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = write_structural_taxonomy_comparison(
            comparison_id=args.comparison_id,
            baseline_samples_path=args.baseline_samples,
            campaign_samples_path=args.campaign_samples,
            output_path=args.output,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error={type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"structural_taxonomy_comparison={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
