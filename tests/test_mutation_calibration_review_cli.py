from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


class MutationCalibrationReviewCliTest(unittest.TestCase):
    def test_blind_review_appends_strict_labels_and_resumes(self) -> None:
        from scripts.review_mutation_calibration_packet import run_review
        from synthesis.mutation_calibration import (
            HUMAN_REVIEW_ATTESTATION,
            build_mutation_calibration_review_packet,
        )

        packet = build_mutation_calibration_review_packet(
            corpus_version="mutation_calibration_corpus_v1"
        )
        output: list[str] = []
        first_inputs = iter(["s", "q"])
        second_inputs = iter(["u", "q"])
        reviewed_at = datetime(2026, 7, 26, 9, 30, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            labels_path = Path(tmpdir) / "human_labels.jsonl"
            first_progress = run_review(
                packet=packet,
                labels_path=labels_path,
                reviewer_id="reviewer.h",
                input_fn=lambda _: next(first_inputs),
                output_fn=output.append,
                now_fn=lambda: reviewed_at,
            )
            second_progress = run_review(
                packet=packet,
                labels_path=labels_path,
                reviewer_id="reviewer.h",
                input_fn=lambda _: next(second_inputs),
                output_fn=output.append,
                now_fn=lambda: reviewed_at,
            )

            labels = [
                json.loads(line)
                for line in labels_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(first_progress, (1, 200))
        self.assertEqual(second_progress, (2, 200))
        self.assertEqual(len(labels), 2)
        self.assertEqual(
            {label["ground_truth"] for label in labels},
            {"supported", "unsupported"},
        )
        self.assertEqual(len({label["case_id"] for label in labels}), 2)
        self.assertTrue(
            all(
                label["reviewer_provenance"]
                == {
                    "reviewer_id": "reviewer.h",
                    "reviewed_at": "2026-07-26T09:30:00Z",
                    "review_method": "human_direct_review",
                    "human_review_attestation": HUMAN_REVIEW_ATTESTATION,
                }
                for label in labels
            )
        )
        rendered = "\n".join(output)
        self.assertIn("Instruction:", rendered)
        self.assertIn("Proposed action:", rendered)
        self.assertIn("Referenced evidence:", rendered)
        self.assertNotIn("sampling_class", rendered)
        self.assertNotIn("scenario_tags", rendered)
        self.assertNotIn("held_out", rendered)
        self.assertNotIn("criticality=", rendered)
        self.assertTrue(
            all(
                scenario not in rendered
                for scenario in packet["coverage"]["scenario_tags"]
            )
        )

    def test_resume_rejects_a_label_bound_to_another_case_hash(self) -> None:
        from scripts.review_mutation_calibration_packet import run_review
        from synthesis.mutation_calibration import (
            HUMAN_REVIEW_ATTESTATION,
            build_mutation_calibration_review_packet,
        )

        packet = build_mutation_calibration_review_packet(
            corpus_version="mutation_calibration_corpus_v1"
        )
        case = packet["cases"][0]
        label = {
            "schema_version": "human_mutation_calibration_label_v1",
            "corpus_version": packet["corpus_version"],
            "case_id": case["case_id"],
            "case_hash": "sha256:" + "0" * 64,
            "ground_truth": "supported",
            "reviewer_provenance": {
                "reviewer_id": "reviewer.h",
                "reviewed_at": "2026-07-26T09:30:00Z",
                "review_method": "human_direct_review",
                "human_review_attestation": HUMAN_REVIEW_ATTESTATION,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            labels_path = Path(tmpdir) / "human_labels.jsonl"
            labels_path.write_text(json.dumps(label) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match the packet"):
                run_review(
                    packet=packet,
                    labels_path=labels_path,
                    reviewer_id="reviewer.h",
                    input_fn=lambda _: "q",
                    output_fn=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
