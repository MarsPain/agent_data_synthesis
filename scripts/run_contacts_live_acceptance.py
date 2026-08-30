from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contacts_live_acceptance import (
    CONTACTS_LIVE_PROOF_FAILURE_FILENAME,
    LiveContactsAcceptanceAuthorization,
    LiveContactsAcceptanceError,
    run_live_contacts_acceptance,
)
from synthesis.run_profiles import load_run_profile


DEFAULT_PROFILE = (
    ROOT
    / "tests"
    / "fixtures"
    / "run_profiles"
    / "contacts-release-candidate.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly authorized live Contacts acceptance, freeze "
            "sanitized provider evidence, and build its replay proof."
        )
    )
    parser.add_argument(
        "--authorize-live-provider",
        action="store_true",
        required=True,
        help="Required explicit authorization for the provider-backed run.",
    )
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--candidate-budget", required=True, type=int)
    parser.add_argument("--attempt-budget", required=True, type=int)
    parser.add_argument("--generator-model", required=True)
    parser.add_argument("--mutation-judge-model", required=True)
    parser.add_argument("--run-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "contacts-live-acceptance",
    )
    parser.add_argument("--proof-dir", type=Path, default=None)
    parser.add_argument(
        "--max-generator-retries",
        type=int,
        choices=(0, 1, 2, 3),
        default=0,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        profile = load_run_profile(args.run_profile)
        authorization = LiveContactsAcceptanceAuthorization(
            approved=args.authorize_live_provider,
            authorization_id=args.authorization_id,
            candidate_budget=args.candidate_budget,
            attempt_budget=args.attempt_budget,
            generator_provider="openai_compatible",
            generator_model=args.generator_model,
            mutation_judge_provider="openai_compatible",
            mutation_judge_model=args.mutation_judge_model,
            generator_retry_limit=args.max_generator_retries,
        )
        result = run_live_contacts_acceptance(
            args.output_dir,
            profile=profile,
            authorization=authorization,
            proof_root=args.proof_dir,
            max_generator_retries=args.max_generator_retries,
        )
    except (LiveContactsAcceptanceError, OSError, ValueError) as exc:
        reason_code = getattr(exc, "reason_code", "contacts_live_acceptance_failed")
        failure_path = args.output_dir / CONTACTS_LIVE_PROOF_FAILURE_FILENAME
        failure_record = (
            str(failure_path)
            if failure_path.is_file() and not failure_path.is_symlink()
            else None
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_codes": [reason_code],
                    "acceptance_dir": str(args.output_dir),
                    "failure_record_path": failure_record,
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
                "status": "accepted",
                "acceptance_dir": str(result.acceptance_dir),
                "proof_path": str(result.proof_path),
                "provider_evidence_path": str(result.provider_evidence_path),
                "replay": dict(result.replay),
                "qualification": dict(result.qualification),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
