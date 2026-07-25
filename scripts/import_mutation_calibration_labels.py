from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.mutation_calibration import (
    REVIEWED_CORPUS_FILENAME,
    import_human_reviewed_mutation_calibration_corpus,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import a complete directly human-reviewed semantic-mutation "
            "calibration corpus without calling a judge."
        )
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--split-freeze", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(REVIEWED_CORPUS_FILENAME),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        corpus = import_human_reviewed_mutation_calibration_corpus(
            packet_path=args.packet,
            freeze_path=args.split_freeze,
            labels_path=args.labels,
            output_path=args.output,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(
            f"mutation calibration import failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"reviewed_corpus={args.output}")
    print(f"corpus_hash={corpus['corpus_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
