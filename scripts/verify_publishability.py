from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.publishability import (
    load_publishability_bundle,
    evaluate_publishability,
    write_publishability_decision,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a publishability evidence bundle without publishing it."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--release-pack",
        type=Path,
        default=None,
        help="Optional local pack path for independent byte and pack verification.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--now",
        required=True,
        help="Explicit evaluation timestamp; required for authority validity checks.",
    )
    parser.add_argument(
        "--trusted-key",
        action="append",
        default=[],
        metavar="KEY_ID=KEY",
        help="Out-of-band key material; may be repeated and is never written to evidence.",
    )
    parser.add_argument(
        "--trusted-policy-hash",
        action="append",
        default=[],
        metavar="SHA256",
        help="Out-of-band authority-policy hash; may be repeated.",
    )
    parser.add_argument(
        "--trusted-bundle-content-hash",
        action="append",
        default=[],
        metavar="SHA256",
        help="Out-of-band real-evidence bundle content hash; may be repeated.",
    )
    parser.add_argument(
        "--trusted-release-pack-verification-hash",
        action="append",
        default=[],
        metavar="SHA256",
        help="Out-of-band exact release-pack verification hash; may be repeated.",
    )
    return parser.parse_args()


def _trusted_keys(raw_values: list[str]) -> dict[str, str]:
    trusted: dict[str, str] = {}
    for raw in raw_values:
        key_id, separator, key = raw.partition("=")
        if not separator or not key_id or not key or key_id in trusted:
            raise ValueError("trusted keys must use unique KEY_ID=KEY entries")
        trusted[key_id] = key
    return trusted


def main() -> int:
    args = parse_args()
    try:
        bundle = load_publishability_bundle(args.bundle)
        decision = evaluate_publishability(
            bundle=bundle,
            trusted_keys=_trusted_keys(args.trusted_key),
            trusted_policy_hashes=args.trusted_policy_hash,
            trusted_bundle_content_hashes=args.trusted_bundle_content_hash,
            trusted_release_pack_verification_hashes=args.trusted_release_pack_verification_hash,
            now=args.now,
            release_pack_path=args.release_pack,
        )
        if args.output is not None:
            write_publishability_decision(args.output, decision)
            print(f"publishability_decision={args.output}")
        else:
            print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error={type(exc).__name__}", file=sys.stderr)
        return 1
    return 0 if decision["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
