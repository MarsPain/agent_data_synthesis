from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.dataset_release import write_dataset_release_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a dataset release admission report from existing artifacts."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--evaluation-report", type=Path, required=True)
    parser.add_argument("--profile-decision-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = write_dataset_release_report(
        manifest_path=args.manifest,
        quality_report_path=args.quality_report,
        evaluation_report_path=args.evaluation_report,
        profile_decision_report_path=args.profile_decision_report,
        output_path=args.output,
    )
    print(f"dataset_release_report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
