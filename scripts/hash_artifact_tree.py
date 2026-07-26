from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.representative_activation_gate import hash_artifact_tree


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute a deterministic SHA-256 digest for an artifact tree."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(hash_artifact_tree(args.path))
    except (OSError, ValueError) as exc:
        print(f"artifact tree hash failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
