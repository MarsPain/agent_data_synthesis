from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.representative_activation_gate import (
    verify_representative_activation_gate_from_paths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify representative activation evidence offline."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--activation-report", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--protected-campaign", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = verify_representative_activation_gate_from_paths(
        report_path=args.report,
        activation_report_path=args.activation_report,
        campaign_path=args.campaign,
        protected_campaign_path=args.protected_campaign,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
