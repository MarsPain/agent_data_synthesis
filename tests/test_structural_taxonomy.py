from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _search_sample(
    *,
    sample_id: str,
    coverage_cell_id: str | None = None,
) -> dict[str, object]:
    generator: dict[str, object] = {}
    if coverage_cell_id is not None:
        generator["coverage_assignment"] = {"cell_id": coverage_cell_id}
    return {
        "sample_id": sample_id,
        "task": {
            "constraints": {
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_search",
                "required_tools": ["search_phone_messages"],
            }
        },
        "trajectory": [
            {
                "type": "action",
                "tool": "search_phone_messages",
                "arguments": {
                    "query": "project update",
                    "participant": "Maya",
                },
            },
            {
                "type": "observation",
                "tool": "search_phone_messages",
                "observation": {
                    "message_id": "msg_maya_project_update",
                    "thread_id": "thread_maya",
                },
            },
        ],
        "lineage": {"generator": generator},
    }


def _draft_reply_sample(sample_id: str) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "task": {
            "constraints": {
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_draft_reply",
                "required_tools": [
                    "search_phone_messages",
                    "draft_message_reply",
                ],
            }
        },
        "trajectory": [
            {
                "type": "action",
                "tool": "search_phone_messages",
                "arguments": {"query": "project update", "participant": "Maya"},
            },
            {
                "type": "observation",
                "tool": "search_phone_messages",
                "observation": {
                    "message_id": "msg_maya_project_update",
                    "thread_id": "thread_maya",
                },
            },
            {
                "type": "action",
                "tool": "draft_message_reply",
                "arguments": {
                    "thread_id": "thread_maya",
                    "body": "I will review it.",
                },
            },
        ],
    }


class StructuralTaxonomyTest(unittest.TestCase):
    def test_legacy_and_coverage_samples_use_one_like_for_like_classifier(
        self,
    ) -> None:
        from synthesis.structural_taxonomy import classify_structural_sample

        legacy = classify_structural_sample(
            _search_sample(sample_id="legacy"),
        )
        coverage = classify_structural_sample(
            _search_sample(
                sample_id="coverage",
                coverage_cell_id="mobile.search_exact_participant",
            ),
        )
        draft = classify_structural_sample(
            _draft_reply_sample("draft"),
        )

        self.assertEqual(legacy.status, "classified")
        self.assertEqual(legacy.family_id, coverage.family_id)
        self.assertNotEqual(legacy.family_id, draft.family_id)
        self.assertIn(
            "search_phone_messages.thread_id->draft_message_reply.thread_id",
            draft.features["cross_step_bindings"],
        )
        self.assertNotIn("coverage_assignment", draft.features)

    def test_comparison_records_unclassifiable_counts_and_concentration(
        self,
    ) -> None:
        from synthesis.structural_taxonomy import (
            build_structural_taxonomy_comparison,
        )

        report = build_structural_taxonomy_comparison(
            comparison_id="mobile_messages",
            baseline_samples=[
                _search_sample(sample_id="legacy_1"),
                _search_sample(sample_id="legacy_2"),
                _draft_reply_sample("legacy_3"),
            ],
            campaign_samples=[
                _search_sample(
                    sample_id="coverage_1",
                    coverage_cell_id="mobile.search_exact_participant",
                ),
                _draft_reply_sample("coverage_2"),
                {"sample_id": "unclassifiable"},
            ],
        )

        self.assertEqual(
            report["taxonomy"]["version"],
            "representative_structural_taxonomy_v1",
        )
        self.assertEqual(report["baseline"]["classified_count"], 3)
        self.assertEqual(report["baseline"]["unclassifiable_count"], 0)
        self.assertEqual(report["baseline"]["largest_family_share"], 2 / 3)
        self.assertEqual(report["campaign"]["classified_count"], 2)
        self.assertEqual(report["campaign"]["unclassifiable_count"], 1)
        self.assertEqual(
            report["campaign"]["unclassifiable_reasons"],
            {"missing_task_constraints": 1},
        )
        self.assertEqual(report["campaign"]["largest_family_share"], 0.5)
        self.assertEqual(
            report["like_for_like"]["largest_family_share_delta"],
            0.5 - (2 / 3),
        )

    def test_comparison_writer_emits_deterministic_versioned_json(self) -> None:
        from synthesis.structural_taxonomy import (
            write_structural_taxonomy_comparison,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_path = root / "baseline.jsonl"
            campaign_path = root / "campaign.jsonl"
            output_path = root / "comparison.json"
            baseline_path.write_text(
                json.dumps(_search_sample(sample_id="legacy")) + "\n",
                encoding="utf-8",
            )
            campaign_path.write_text(
                json.dumps(
                    _search_sample(
                        sample_id="coverage",
                        coverage_cell_id="mobile.search_exact_participant",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            written = write_structural_taxonomy_comparison(
                comparison_id="mobile_messages",
                baseline_samples_path=baseline_path,
                campaign_samples_path=campaign_path,
                output_path=output_path,
            )

            self.assertEqual(written, output_path)
            self.assertTrue(output_path.read_bytes().endswith(b"\n"))
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["baseline"]["family_counts"],
                report["campaign"]["family_counts"],
            )


if __name__ == "__main__":
    unittest.main()
