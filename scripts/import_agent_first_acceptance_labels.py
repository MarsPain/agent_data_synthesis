"""Import one Domain's blind human labels through the existing engine contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis.engine import SynthesisEngine
from agent_synthesis.registry import AdapterRegistry
from scripts.run_agent_first_three_domain_acceptance import load_verified_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-fingerprint", required=True)
    parser.add_argument("--domain", required=True, choices=("contacts", "mobile_messages", "workspace_tasks"))
    parser.add_argument("--labels", required=True, type=Path)
    args = parser.parse_args()
    plan = load_verified_plan(args.plan, args.plan_fingerprint)
    if args.domain not in plan["domains"]:
        parser.error("Domain is outside the frozen campaign")
    result = SynthesisEngine(AdapterRegistry(domains=(), models=())).import_review_labels(
        args.plan.parent / args.domain, args.labels
    )
    print(json.dumps({"status": result.status, "human_approved_episode_count": len(result.human_approved_episode_ids), "report": str(result.report_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
