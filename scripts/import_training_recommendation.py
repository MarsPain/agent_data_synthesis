from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.training_recommendation import (
    CONFORMANCE_FIXTURE_EVIDENCE_CLASS,
    EXTERNAL_EXPERIMENT_EVIDENCE_CLASS,
    import_training_recommendation_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import and verify a Workspace external training experiment."
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--baseline", "--baseline-manifest", dest="baseline", type=Path, required=True)
    parser.add_argument("--treatment", "--treatment-manifest", dest="treatment", type=Path, required=True)
    parser.add_argument("--evaluation", "--evaluation-manifest", dest="evaluation", type=Path, required=True)
    parser.add_argument("--paired-results", "--paired", dest="paired_results", type=Path, required=True)
    parser.add_argument("--leakage", "--leakage-report", dest="leakage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--evidence-class",
        choices=(EXTERNAL_EXPERIMENT_EVIDENCE_CLASS, CONFORMANCE_FIXTURE_EVIDENCE_CLASS),
        default=EXTERNAL_EXPERIMENT_EVIDENCE_CLASS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = import_training_recommendation_evidence(
        protocol_path=args.protocol,
        baseline_path=args.baseline,
        treatment_path=args.treatment,
        evaluation_path=args.evaluation,
        paired_results_path=args.paired_results,
        leakage_path=args.leakage,
        output_path=args.output,
        evidence_class=args.evidence_class,
    )
    print(f"training_recommendation_result={args.output}")
    return 0 if result["decision"]["status"] in {
        "training_recommended",
        "protocol_conformance_passed",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
