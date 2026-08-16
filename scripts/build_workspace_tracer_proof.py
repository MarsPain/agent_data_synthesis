from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.workspace_tracer import build_workspace_tracer_proof


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deterministic offline Workspace tracer proof root."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/workspace-tracer-proof"),
        help="Directory that will contain the proof root and its bound artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    proof_path = build_workspace_tracer_proof(args.output_dir)
    print(
        json.dumps(
            {
                "proof_root": str(proof_path.parent),
                "proof_path": str(proof_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
