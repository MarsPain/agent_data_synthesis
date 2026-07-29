from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.mutation_calibration import (
    HUMAN_LABEL_SCHEMA_VERSION,
    HUMAN_REVIEW_ATTESTATION,
    validate_human_mutation_calibration_label,
    validate_mutation_calibration_review_packet,
)


GROUND_TRUTH_KEYS = {
    "s": "supported",
    "u": "unsupported",
    "?": "uncertain",
}
REVIEWER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Blindly review semantic-mutation calibration cases and append "
            "strict human label records. The command supports safe resume."
        )
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    return parser.parse_args()


def load_packet(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_mutation_calibration_review_packet(raw)
    assert isinstance(raw, Mapping)
    return dict(raw)


def load_existing_labels(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    labels: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, Mapping):
            raise ValueError(f"human label line {line_number} is not an object")
        labels.append(dict(raw))
    return labels


def run_review(
    *,
    packet: Mapping[str, object],
    labels_path: Path,
    reviewer_id: str,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[int, int]:
    if REVIEWER_ID_PATTERN.fullmatch(reviewer_id) is None:
        raise ValueError("reviewer_id must use only letters, numbers, . _ : or -")
    cases = packet.get("cases")
    if not isinstance(cases, list):
        raise ValueError("review packet cases are missing")
    cases_by_id = {
        str(case["case_id"]): case
        for case in cases
        if isinstance(case, Mapping)
    }
    if len(cases_by_id) != len(cases):
        raise ValueError("review packet contains duplicate or invalid cases")

    existing = load_existing_labels(labels_path)
    labeled_ids: set[str] = set()
    for label in existing:
        validate_human_mutation_calibration_label(
            label,
            corpus_version=str(packet["corpus_version"]),
        )
        case_id = label.get("case_id")
        if not isinstance(case_id, str) or case_id not in cases_by_id:
            raise ValueError("existing human label references an unknown case")
        if case_id in labeled_ids:
            raise ValueError("existing human labels contain a duplicate case")
        case = cases_by_id[case_id]
        assert isinstance(case, Mapping)
        if (
            label.get("case_hash") != case.get("case_hash")
            or label.get("corpus_version") != packet.get("corpus_version")
        ):
            raise ValueError("existing human label does not match the packet")
        labeled_ids.add(case_id)

    ordered_cases = sorted(
        (
            case
            for case in cases_by_id.values()
            if str(case["case_id"]) not in labeled_ids
        ),
        key=lambda case: str(case["case_hash"]),
    )
    total = len(cases)
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    reviewed_now = 0
    for case in ordered_cases:
        assert isinstance(case, Mapping)
        _render_case(
            case,
            completed=len(labeled_ids) + reviewed_now,
            total=total,
            output_fn=output_fn,
        )
        while True:
            try:
                raw_choice = input_fn(
                    "Label [s=supported, u=unsupported, ?=uncertain, q=save/quit]: "
                )
            except EOFError:
                raw_choice = "q"
            choice = raw_choice.strip().lower()
            if choice == "q":
                return len(labeled_ids) + reviewed_now, total
            if choice in GROUND_TRUTH_KEYS:
                break
            output_fn("Invalid choice. Enter s, u, ?, or q.")

        current_time = (
            now_fn() if now_fn is not None else datetime.now(timezone.utc)
        )
        if current_time.tzinfo is None:
            raise ValueError("review timestamp must be timezone-aware")
        reviewed_at = current_time.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        label = {
            "schema_version": HUMAN_LABEL_SCHEMA_VERSION,
            "corpus_version": packet["corpus_version"],
            "case_id": case["case_id"],
            "case_hash": case["case_hash"],
            "ground_truth": GROUND_TRUTH_KEYS[choice],
            "reviewer_provenance": {
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "review_method": "human_direct_review",
                "human_review_attestation": HUMAN_REVIEW_ATTESTATION,
            },
        }
        validate_human_mutation_calibration_label(
            label,
            corpus_version=str(packet["corpus_version"]),
        )
        with labels_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    label,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            stream.flush()
        reviewed_now += 1
        output_fn(
            f"Saved {len(labeled_ids) + reviewed_now}/{total}: "
            f"{label['ground_truth']}"
        )
    return len(labeled_ids) + reviewed_now, total


def _render_case(
    case: Mapping[str, object],
    *,
    completed: int,
    total: int,
    output_fn: Callable[[str], None],
) -> None:
    normalized_input = case.get("normalized_input")
    if not isinstance(normalized_input, Mapping):
        raise ValueError("review case normalized_input is missing")
    proposed_action = normalized_input.get("proposed_action")
    provenance = normalized_input.get("validated_provenance")
    evidence = normalized_input.get("referenced_evidence")
    output_fn("")
    output_fn("=" * 78)
    output_fn(f"Progress: {completed}/{total}")
    output_fn(f"Review token: {str(case['case_hash'])[:24]}")
    output_fn(
        "Context: "
        f"domain={case['domain_id']} task={case['task_type']} "
        f"action={case['action_type']}"
    )
    output_fn(f"Instruction: {normalized_input.get('instruction')}")
    output_fn(
        "Proposed action:\n"
        + json.dumps(proposed_action, ensure_ascii=False, indent=2, sort_keys=True)
    )
    output_fn(
        "Validated provenance:\n"
        + json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True)
    )
    output_fn(
        "Referenced evidence:\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)
    )


def main() -> int:
    args = parse_args()
    try:
        packet = load_packet(args.packet)
        completed, total = run_review(
            packet=packet,
            labels_path=args.labels,
            reviewer_id=args.reviewer_id,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"mutation calibration review failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"review_progress={completed}/{total}")
    print(f"human_labels={args.labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
