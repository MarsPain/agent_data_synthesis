from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthesis.environments import ContactEnvironment
from synthesis.execution import scripted_solution_policy
from synthesis.llm import LLMConfig
from synthesis.tasks import CandidateTask
from synthesis.tools import build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


def _candidate(candidate_id: str, *, instruction: str | None = None) -> CandidateTask:
    return CandidateTask(
        candidate_id=candidate_id,
        instruction=instruction or "Find Alice Zhang's email address using the contact database.",
        constraints={"must_use_tool": "lookup_contact_email"},
        difficulty={
            "level": "easy",
            "tool_count": 1,
            "constraint_count": 1,
            "state_changes": 0,
            "ambiguity": "none",
            "recovery_paths": 0,
        },
        tool_name="lookup_contact_email",
        arguments={"name": "Alice Zhang"},
        expected_answer="alice.zhang@example.test",
        seed_ids=("seed_contacts_v1",),
    )


def _context(tmpdir: Path):
    from synthesis.candidate_processing import CandidateProcessingContext

    environment = ContactEnvironment.create_fixture(tmpdir)
    registry = build_contact_tool_registry(environment)
    return CandidateProcessingContext(
        dataset_version="dataset_candidate_merge_test",
        environment=environment,
        registry=registry,
        adapter_shim=None,
        verifier=ExactAnswerVerifier(),
        llm_config=LLMConfig(base_url=None),
        generate_policy=scripted_solution_policy,
    )


class CandidateMergeTest(unittest.TestCase):
    def test_merge_sorts_outcomes_and_rejects_later_duplicate_signature(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            CandidateExecutionRequest,
            ProvisionalCandidateOutcome,
            merge_candidate_outcomes,
            process_candidate_through_gates,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            context = _context(Path(tmpdir))
            later_duplicate = process_candidate_through_gates(
                request=CandidateExecutionRequest(
                    sequence_index=2,
                    raw_task=_candidate("candidate_later_duplicate"),
                ),
                context=context,
                options=CandidateProcessingOptions(),
            )
            first = process_candidate_through_gates(
                request=CandidateExecutionRequest(
                    sequence_index=1,
                    raw_task=_candidate("candidate_first"),
                ),
                context=context,
                options=CandidateProcessingOptions(),
            )
            unrelated_rejection = ProvisionalCandidateOutcome(
                sequence_index=0,
                candidate_id="candidate_rejected",
                sample=None,
                rejection={
                    "candidate_id": "candidate_rejected",
                    "cause": "verification_failed",
                    "task": _candidate("candidate_rejected").export(),
                    "details": {"message": "already rejected"},
                },
            )

        result = merge_candidate_outcomes((later_duplicate, unrelated_rejection, first))

        self.assertEqual(
            [sample["sample_id"] for sample in result.samples],
            ["sample_candidate_first"],
        )
        self.assertEqual(
            [rejection["candidate_id"] for rejection in result.rejections],
            ["candidate_rejected", "candidate_later_duplicate"],
        )
        self.assertEqual(result.rejections[1]["cause"], "quality_duplicate")
        self.assertEqual(
            result.rejections[1]["details"]["signature"],
            [
                "find alice zhang's email address using the contact database.",
                ["lookup_contact_email"],
            ],
        )

    def test_merge_preserves_review_and_tool_proposal_order_by_sequence(self) -> None:
        from synthesis.candidate_processing import (
            ProvisionalCandidateOutcome,
            merge_candidate_outcomes,
        )

        result = merge_candidate_outcomes(
            (
                ProvisionalCandidateOutcome(
                    sequence_index=2,
                    candidate_id="candidate_two",
                    sample=None,
                    rejection={"candidate_id": "candidate_two", "cause": "x", "task": {}, "details": {}},
                    review_records=({"candidate_id": "candidate_two"},),
                    tool_proposal_records=({"candidate_id": "candidate_two"},),
                ),
                ProvisionalCandidateOutcome(
                    sequence_index=1,
                    candidate_id="candidate_one",
                    sample=None,
                    rejection={"candidate_id": "candidate_one", "cause": "x", "task": {}, "details": {}},
                    review_records=({"candidate_id": "candidate_one"},),
                    tool_proposal_records=({"candidate_id": "candidate_one"},),
                ),
            )
        )

        self.assertEqual(
            [record["candidate_id"] for record in result.review_records],
            ["candidate_one", "candidate_two"],
        )
        self.assertEqual(
            [record["candidate_id"] for record in result.tool_proposal_records],
            ["candidate_one", "candidate_two"],
        )

    def test_merge_rejects_outcomes_without_exactly_one_terminal_record(self) -> None:
        from synthesis.candidate_processing import (
            ProvisionalCandidateOutcome,
            merge_candidate_outcomes,
        )

        with self.assertRaisesRegex(ValueError, "exactly one sample or rejection"):
            merge_candidate_outcomes(
                (
                    ProvisionalCandidateOutcome(
                        sequence_index=0,
                        candidate_id="candidate_missing_terminal",
                        sample=None,
                        rejection=None,
                    ),
                )
            )

    def test_pipeline_isolates_stateful_candidate_environment_from_later_candidates(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def candidates(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_record_followup",
                    instruction="Record a follow-up note for Alice Zhang.",
                    constraints={
                        "task_type": "contact_followup",
                        "required_tools": ["lookup_contact_email", "record_contact_followup"],
                    },
                    difficulty={
                        "level": "medium",
                        "tool_count": 2,
                        "constraint_count": 2,
                        "state_changes": 1,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                    expected_state={
                        "contact_followup": {
                            "name": "Alice Zhang",
                            "note": "Send follow-up email to alice.zhang@example.test.",
                        }
                    },
                ),
                _candidate(
                    "candidate_check_state_isolation",
                    instruction="Find Alice Zhang's email address using the contact database.",
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_candidate_isolation_test",
                candidate_generator=candidates,
            )

            self.assertEqual(result.accepted_count, 2)
            shared_environment = ContactEnvironment(Path(tmpdir) / "environment" / "contacts.sqlite3")
            self.assertFalse(
                shared_environment.has_followup(
                    "Alice Zhang",
                    "Send follow-up email to alice.zhang@example.test.",
                )
            )

    def test_pipeline_rebuilds_adapter_against_candidate_local_registry(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def candidates(seed) -> list[CandidateTask]:
            return [_candidate("candidate_adapter_local")]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_adapter_isolation_test",
                candidate_generator=candidates,
                enable_mcp_adapter=True,
            )

            self.assertEqual(result.accepted_count, 1)


if __name__ == "__main__":
    unittest.main()
