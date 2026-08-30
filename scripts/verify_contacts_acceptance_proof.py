from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contacts_acceptance import verify_contacts_acceptance_proof
from synthesis.contacts_live_acceptance import verify_live_contacts_acceptance_proof


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one Contacts acceptance proof offline without provider "
            "calls."
        )
    )
    parser.add_argument(
        "proof_root",
        type=Path,
        help="Proof directory or its contacts_acceptance_proof.json root manifest.",
    )
    parser.add_argument(
        "--real-live",
        action="store_true",
        help="Verify a proof containing frozen real_live provider evidence.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = (
        verify_live_contacts_acceptance_proof(args.proof_root)
        if args.real_live
        else verify_contacts_acceptance_proof(args.proof_root)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
