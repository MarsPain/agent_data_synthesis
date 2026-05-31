from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from synthesis.environments import ContactEnvironment
from synthesis.execution import SolutionPolicy, ToolStep, scripted_solution_policy
from synthesis.llm import LLMConfig
from synthesis.mcp import LocalContactsAdapterShim
from synthesis.tasks import CandidateTask
from synthesis.tools import CapabilityGap, ToolProposal, build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


class CandidateProcessingRecordTest(unittest.TestCase):
    def _candidate(self, **overrides: object) -> CandidateTask:
        values = {
            "candidate_id": "candidate_contacts_alice",
            "instruction": "Find Alice Zhang's email address using the contact database.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": {
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 1,
                "state_changes": 0,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "tool_name": "lookup_contact_email",
            "arguments": {"name": "Alice Zhang"},
            "expected_answer": "alice.zhang@example.test",
            "seed_ids": ("seed_contacts_v1",),
        }
        values.update(overrides)
        return CandidateTask(**values)

    def _context(self, tmpdir: Path, *, generate_policy=scripted_solution_policy):
        from synthesis.candidate_processing import CandidateProcessingContext

        environment = ContactEnvironment.create_fixture(tmpdir)
        registry = build_contact_tool_registry(environment)
        return CandidateProcessingContext(
            dataset_version="dataset_candidate_boundary_test",
            environment=environment,
            registry=registry,
            adapter_shim=None,
            verifier=ExactAnswerVerifier(),
            llm_config=LLMConfig(base_url=None),
            generate_policy=generate_policy,
        )

    def test_context_options_and_outcome_records_are_immutable_and_explicit(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingContext,
            CandidateProcessingOptions,
            CandidateProcessingOutcome,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)
            context = CandidateProcessingContext(
                dataset_version="dataset_candidate_boundary_test",
                environment=environment,
                registry=registry,
                adapter_shim=LocalContactsAdapterShim(
                    environment=environment,
                    registry=registry,
                ),
                verifier=ExactAnswerVerifier(),
                llm_config=LLMConfig(base_url=None),
                generate_policy=scripted_solution_policy,
            )

        options = CandidateProcessingOptions()
        outcome = CandidateProcessingOutcome(
            sample={"candidate_id": "candidate_test"},
            rejection=None,
            duplicate_signature=("instruction", ("lookup_contact_email",)),
        )

        self.assertEqual(context.dataset_version, "dataset_candidate_boundary_test")
        self.assertFalse(options.route_reviewable_failures)
        self.assertIsNone(options.refiner)
        self.assertIsNone(options.tool_proposal_generator)
        self.assertEqual(outcome.review_records, ())
        self.assertEqual(outcome.tool_proposal_records, ())
        self.assertIsInstance(outcome.review_records, tuple)
        self.assertIsInstance(outcome.tool_proposal_records, tuple)

        with self.assertRaises(FrozenInstanceError):
            options.route_reviewable_failures = True
        with self.assertRaises(FrozenInstanceError):
            outcome.sample = None

    def test_policy_and_tool_proposal_aliases_match_expected_call_shapes(self) -> None:
        from synthesis.candidate_processing import (
            PolicyGenerator,
            ToolProposalGenerator,
        )

        def policy_generator(task: CandidateTask):
            return scripted_solution_policy(task)

        self.assertIsNotNone(PolicyGenerator)
        self.assertIsNotNone(ToolProposalGenerator)
        self.assertEqual(policy_generator.__name__, "policy_generator")

    def test_valid_candidate_returns_sample_signature_without_mutating_admission_set(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            process_candidate_through_gates,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            context = self._context(Path(tmpdir))
            accepted_signatures: set[tuple[str, tuple[str, ...]]] = set()

            outcome = process_candidate_through_gates(
                raw_task=self._candidate(),
                context=context,
                accepted_signatures=accepted_signatures,
                options=CandidateProcessingOptions(),
            )

        self.assertIsNotNone(outcome.sample)
        self.assertIsNone(outcome.rejection)
        self.assertEqual(outcome.review_records, ())
        self.assertEqual(outcome.tool_proposal_records, ())
        self.assertEqual(
            outcome.accepted_signature,
            (
                "find alice zhang's email address using the contact database.",
                ("lookup_contact_email",),
            ),
        )
        self.assertEqual(accepted_signatures, set())

    def test_invalid_candidate_schema_returns_rejection_without_sample(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            process_candidate_through_gates,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            outcome = process_candidate_through_gates(
                raw_task=self._candidate(candidate_id=""),
                context=self._context(Path(tmpdir)),
                accepted_signatures=set(),
                options=CandidateProcessingOptions(),
            )

        self.assertIsNone(outcome.sample)
        self.assertIsNone(outcome.accepted_signature)
        self.assertIsNotNone(outcome.rejection)
        self.assertEqual(outcome.rejection["cause"], "candidate_schema_error")

    def test_review_routing_returns_records_for_merge_admitted_duplicates_when_enabled(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            CandidateExecutionRequest,
            merge_candidate_outcomes,
            process_candidate_through_gates,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            context = self._context(Path(tmpdir))
            first = process_candidate_through_gates(
                request=CandidateExecutionRequest(
                    sequence_index=0,
                    raw_task=self._candidate(candidate_id="candidate_first"),
                ),
                context=context,
                options=CandidateProcessingOptions(route_reviewable_failures=False),
            )
            duplicate = process_candidate_through_gates(
                request=CandidateExecutionRequest(
                    sequence_index=1,
                    raw_task=self._candidate(candidate_id="candidate_duplicate"),
                ),
                context=context,
                options=CandidateProcessingOptions(route_reviewable_failures=True),
            )

        disabled = merge_candidate_outcomes((first, duplicate))
        enabled = merge_candidate_outcomes(
            (first, duplicate),
            route_reviewable_failures=True,
        )

        self.assertEqual(disabled.rejections[0]["cause"], "quality_duplicate")
        self.assertEqual(disabled.review_records, ())
        self.assertEqual(enabled.rejections[0]["cause"], "quality_duplicate")
        self.assertEqual(len(enabled.review_records), 1)
        self.assertEqual(enabled.review_records[0]["cause"], "quality_duplicate")

    def test_tool_proposal_rerun_returns_proposal_record_with_accepted_sample(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            process_candidate_through_gates,
        )

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_list_contacts",
                role="solution_policy",
                steps=(ToolStep(tool_name="list_contact_names", arguments={}),),
                final_response_template="Known contacts: {contacts}",
            )

        def proposal_generator(gap: CapabilityGap) -> ToolProposal:
            return ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "local",
                    "model": "scripted",
                    "config_hash": "proposal-hash",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            context = self._context(Path(tmpdir), generate_policy=policy_generator)
            outcome = process_candidate_through_gates(
                raw_task=self._candidate(
                    candidate_id="candidate_list_contacts",
                    instruction="List the known contact names.",
                    constraints={"must_use_tool": "list_contact_names"},
                    tool_name="list_contact_names",
                    arguments={},
                    expected_answer="Alice Zhang",
                ),
                context=context,
                accepted_signatures=set(),
                options=CandidateProcessingOptions(
                    tool_proposal_generator=proposal_generator,
                ),
            )

        self.assertIsNotNone(outcome.sample)
        self.assertIsNone(outcome.rejection)
        self.assertEqual(len(outcome.tool_proposal_records), 1)
        self.assertEqual(
            outcome.tool_proposal_records[0]["admission"]["outcome"],
            "accepted",
        )
        self.assertEqual(
            outcome.registry_mutations,
            (
                {
                    "schema_version": "candidate_registry_mutation_v1",
                    "candidate_id": "candidate_list_contacts",
                    "mutation_type": "curated_tool_admission",
                    "tool_name": "list_contact_names",
                    "outcome": "accepted",
                    "tool_version": "tool_list_contact_names_v1",
                },
            ),
        )
        self.assertEqual(
            outcome.sample["lineage"]["tool_expansion"]["admission"]["outcome"],
            "accepted",
        )

    def test_duplicate_candidate_returns_provisional_sample_for_merge_admission(self) -> None:
        from synthesis.candidate_processing import (
            CandidateProcessingOptions,
            process_candidate_through_gates,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            context = self._context(Path(tmpdir))
            outcome = process_candidate_through_gates(
                raw_task=self._candidate(),
                context=context,
                accepted_signatures={
                    (
                        "find alice zhang's email address using the contact database.",
                        ("lookup_contact_email",),
                    )
                },
                options=CandidateProcessingOptions(),
            )

        self.assertIsNotNone(outcome.sample)
        self.assertIsNone(outcome.rejection)
        self.assertEqual(
            outcome.duplicate_signature,
            (
                "find alice zhang's email address using the contact database.",
                ("lookup_contact_email",),
            ),
        )


if __name__ == "__main__":
    unittest.main()
