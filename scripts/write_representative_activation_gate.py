from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.representative_activation_gate import (
    build_representative_activation_gate_from_paths,
    write_representative_activation_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write the final representative mutation activation/no-go gate."
    )
    parser.add_argument("--activation-report", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--protected-campaign", type=Path, required=True)
    parser.add_argument("--protected-baseline-hash", required=True)
    parser.add_argument("--activation-judge-cost-usd", type=float, required=True)
    parser.add_argument(
        "--representative-pipeline-cost-usd",
        type=float,
        required=True,
    )
    parser.add_argument("--limitation", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        protected_root = args.protected_campaign.resolve()
        if args.output.resolve().is_relative_to(protected_root):
            raise ValueError("gate output must not modify protected campaign")
        report = build_representative_activation_gate_from_paths(
            activation_report_path=args.activation_report,
            campaign_path=args.campaign,
            protected_campaign_path=args.protected_campaign,
            protected_baseline_hash=args.protected_baseline_hash,
            costs={
                "activation_judge_usd": args.activation_judge_cost_usd,
                "representative_pipeline_usd": (
                    args.representative_pipeline_cost_usd
                ),
            },
            limitations=args.limitation,
        )
        write_representative_activation_gate(args.output, report)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        print(
            f"representative activation gate failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"representative_activation_gate={args.output}")
    print(f"decision={report['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
