from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.profile_decisions import DecisionThresholds, write_profile_decision_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a sanitized profile decision report from dataset artifacts."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--parent-comparison", type=Path, default=None)
    parser.add_argument("--runtime-seconds", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--async-candidate-count", type=int, default=100)
    parser.add_argument("--async-runtime-seconds", type=float, default=600.0)
    parser.add_argument("--semantic-duplicate-min-candidates", type=int, default=100)
    parser.add_argument("--semantic-duplicate-exact-rate", type=float, default=0.1)
    parser.add_argument("--mvp-min-success-rate", type=float, default=0.5)
    parser.add_argument("--mvp-min-executable-rate", type=float, default=0.8)
    parser.add_argument("--mvp-max-infrastructure-rejection-rate", type=float, default=0.0)
    parser.add_argument("--mvp-max-source-policy-rejection-rate", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = DecisionThresholds(
        async_candidate_count=args.async_candidate_count,
        async_runtime_seconds=args.async_runtime_seconds,
        semantic_duplicate_min_candidates=args.semantic_duplicate_min_candidates,
        semantic_duplicate_exact_rate=args.semantic_duplicate_exact_rate,
        mvp_min_success_rate=args.mvp_min_success_rate,
        mvp_min_executable_rate=args.mvp_min_executable_rate,
        mvp_max_infrastructure_rejection_rate=args.mvp_max_infrastructure_rejection_rate,
        mvp_max_source_policy_rejection_rate=args.mvp_max_source_policy_rejection_rate,
    )
    output_path = write_profile_decision_report(
        manifest_path=args.manifest,
        quality_report_path=args.quality_report,
        parent_comparison_path=args.parent_comparison,
        runtime_seconds=args.runtime_seconds,
        output_path=args.output,
        thresholds=thresholds,
    )
    print(f"profile_decision_report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
