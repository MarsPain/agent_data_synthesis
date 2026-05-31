from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.evaluation import write_evaluation_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a held-out evaluation report.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--parent-evaluation-report", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path = write_evaluation_report(
            manifest_path=args.manifest,
            quality_report_path=args.quality_report,
            parent_evaluation_report_path=args.parent_evaluation_report,
            output_path=args.output,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"evaluation_report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
