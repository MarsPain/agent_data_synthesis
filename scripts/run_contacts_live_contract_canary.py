from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contacts_live_acceptance import (
    DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS,
    DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
    LiveContactsAcceptanceAuthorization,
)
from synthesis.contacts_live_canary import (
    ContactsLiveContractCanaryError,
    run_contacts_live_contract_canary,
)
from synthesis.run_profiles import load_run_profile


DEFAULT_PROFILE = (
    ROOT / "tests" / "fixtures" / "run_profiles" / "contacts-release-candidate.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one non-qualifying, one-call Contacts follow-up grounding canary."
        )
    )
    parser.add_argument("--authorize-live-provider", action="store_true", required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--generator-model", required=True)
    parser.add_argument(
        "--generator-timeout-seconds",
        type=float,
        default=DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--mutation-judge-model",
        default=DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
    )
    parser.add_argument("--run-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "contacts-live-contract-canary",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        profile = load_run_profile(args.run_profile)
        authorization = LiveContactsAcceptanceAuthorization(
            approved=args.authorize_live_provider,
            authorization_id=args.authorization_id,
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model=args.generator_model,
            generator_timeout_seconds=args.generator_timeout_seconds,
            mutation_judge_provider="openai_compatible",
            mutation_judge_model=args.mutation_judge_model,
            generator_retry_limit=0,
        )
        result = run_contacts_live_contract_canary(
            args.output_dir,
            profile=profile,
            authorization=authorization,
        )
    except (ContactsLiveContractCanaryError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": getattr(exc, "reason_code", "contacts_canary_failed"),
                    "canary_dir": str(args.output_dir),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": result.status,
                "record_path": str(result.record_path),
                "non_qualifying": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
