from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.workspace_tracer import verify_workspace_tracer_proof


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify one Workspace tracer proof root without provider calls."
    )
    parser.add_argument(
        "proof_root",
        type=Path,
        help="Proof directory or its workspace_tracer_proof.json root manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = verify_workspace_tracer_proof(args.proof_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
