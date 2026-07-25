from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.mutation_calibration import (
    write_mutation_calibration_review_packet,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a deterministic semantic-mutation calibration review packet "
            "and freeze its held-out split without calling a judge."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--corpus-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = write_mutation_calibration_review_packet(
            args.output_dir,
            corpus_version=args.corpus_version,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(
            f"mutation calibration export failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"review_packet={paths.packet_path}")
    print(f"split_freeze={paths.freeze_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
