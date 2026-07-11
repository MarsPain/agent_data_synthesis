from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contracts import ContractValidationError
from synthesis.scale_evidence import write_representative_scale_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write deterministic three-domain scale evidence.")
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = write_representative_scale_evidence(
            campaign_path=args.campaign,
            output_path=args.output,
        )
    except (OSError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        print(f"error={type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"representative_scale_evidence={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
