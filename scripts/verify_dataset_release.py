from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthesis.release_pack import (
    DATASET_RELEASE_PACK_FILENAME,
    verify_dataset_release_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a dataset release pack without rerunning generation."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory containing dataset_release_pack.json.",
    )
    selector.add_argument(
        "--release-pack",
        type=Path,
        help="Path to dataset_release_pack.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_path = (
        args.release_pack
        if args.release_pack is not None
        else args.output_dir / DATASET_RELEASE_PACK_FILENAME
    )
    result = verify_dataset_release_pack(pack_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    verification = result.get("verification")
    status = verification.get("status") if isinstance(verification, dict) else None
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
