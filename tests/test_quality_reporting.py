from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthesis.tasks import CandidateTask


class QualityReportingTest(unittest.TestCase):
    def test_builds_dataset_report_with_counts_rates_slices_and_rejection_causes(self) -> None:
        from synthesis.quality import build_quality_report

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[_sample()],
            rejections=[_rejection()],
        )

        self.assertEqual(report["schema_version"], "quality_report_v1")
        self.assertEqual(report["counts"]["total"], 2)
        self.assertEqual(report["counts"]["accepted"], 1)
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertEqual(report["counts"]["executable"], 2)
        self.assertEqual(report["rates"]["success_rate"], 0.5)
        self.assertEqual(report["rates"]["executable_rate"], 1.0)
        self.assertEqual(report["rejection_causes"], {"verification_failed": 1})
        self.assertIn("dataset_test", report["slices"]["dataset_version"])
        self.assertIn("easy", report["slices"]["difficulty_level"])
        self.assertIn("lookup_contact_email", report["slices"]["tool_combination"])
        self.assertIn("task_generation", report["slices"]["generator_role"])
        self.assertIn("exact_answer_verifier", report["slices"]["verifier_type"])
        self.assertIn("verification_failed", report["slices"]["rejection_cause"])
        self.assertEqual(report["counts"]["capability_gaps"], 0)
        self.assertEqual(report["counts"]["tool_proposals"], 0)

    def test_success_rate_uses_executable_candidates_as_denominator(self) -> None:
        from synthesis.quality import build_quality_report

        rejection = _rejection()
        rejection["cause"] = "tool_missing"

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[_sample()],
            rejections=[rejection],
        )

        self.assertEqual(report["counts"]["executable"], 1)
        self.assertEqual(report["rates"]["success_rate"], 1.0)
        self.assertEqual(report["rates"]["executable_rate"], 0.5)

    def test_report_summarizes_role_outcomes_tokens_cost_and_role_slices(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["generator"] = {
            "role": "task_generation",
            "role_version": "role_task_generation_v1",
            "output_type": "candidate_tasks",
            "provider_host": "llm.example.test",
            "model": "test-generator",
            "config_hash": "task-hash",
            "retry_count": 1,
            "tokens": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
            "cost": {"total_usd": 0.03},
        }
        sample["lineage"]["solution_policy"] = {
            "role": "solution_policy",
            "role_version": "role_solution_policy_v1",
            "output_type": "solution_policy",
            "provider_host": "llm.example.test",
            "model": "test-generator",
            "config_hash": "policy-hash",
            "retry_count": 0,
            "tokens": {"total_tokens": 4},
        }
        rejection = _rejection()
        rejection["details"]["refinement"] = {
            "outcome": "rejected",
            "lineage": {
                "role": "critic_refinement",
                "role_version": "role_critic_refinement_v1",
                "output_type": "refinement_attempt",
                "provider_host": "llm.example.test",
                "model": "test-generator",
                "config_hash": "critic-hash",
                "retry_count": 2,
                "tokens": {"total_tokens": 9},
            },
        }

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[rejection],
        )

        self.assertEqual(
            report["role_outcomes"]["task_generation"],
            {
                "attempted": 1,
                "accepted": 1,
                "rejected": 0,
                "retry_count": 1,
                "tokens": {"completion_tokens": 5, "prompt_tokens": 7, "total_tokens": 12},
                "cost": {"total_usd": 0.03},
                "output_types": ["candidate_tasks"],
            },
        )
        self.assertEqual(report["role_outcomes"]["solution_policy"]["accepted"], 1)
        self.assertEqual(report["role_outcomes"]["solution_policy"]["tokens"], {"total_tokens": 4})
        self.assertEqual(report["role_outcomes"]["critic_refinement"]["rejected"], 1)
        self.assertEqual(report["role_outcomes"]["critic_refinement"]["retry_count"], 2)
        self.assertIn("task_generation", report["slices"]["role_name"])
        self.assertIn("solution_policy", report["slices"]["role_output_type"])
        self.assertIn("refinement_attempt", report["slices"]["role_output_type"])

    def test_report_summarizes_capability_gaps_and_tool_proposal_outcomes(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["tool_expansion"] = {
            "gap": {
                "gap_type": "unknown_tool",
                "tool_name": "list_contact_names",
                "cause": "tool_missing",
            },
            "proposal": {
                "tool_name": "list_contact_names",
                "side_effects": "read_only",
                "lineage": {"role": "tool_generation", "output_type": "tool_proposal"},
            },
            "admission": {"outcome": "accepted", "tool_name": "list_contact_names"},
        }
        rejection = _rejection()
        rejection["details"]["capability_gap"] = {
            "gap_type": "incompatible_arguments",
            "tool_name": "lookup_contact_email",
            "cause": "tool_schema_error",
        }
        rejection["details"]["tool_proposal"] = {
            "proposal": {
                "tool_name": "lookup_contact_email",
                "side_effects": "read_only",
                "lineage": {"role": "tool_generation", "output_type": "tool_proposal"},
            },
            "admission": {"outcome": "rejected", "reason": "schema mismatch"},
        }

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[rejection],
        )

        self.assertEqual(report["counts"]["capability_gaps"], 2)
        self.assertEqual(report["counts"]["tool_proposals"], 2)
        self.assertEqual(report["tool_proposal_outcomes"], {"accepted": 1, "rejected": 1})
        self.assertIn("unknown_tool", report["slices"]["capability_gap_type"])
        self.assertIn("list_contact_names", report["slices"]["proposed_tool"])
        self.assertIn("read_only", report["slices"]["proposed_tool_side_effect"])

    def test_report_summarizes_branch_attempts_and_slices(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["branching"] = {
            "schema_version": "branch_lineage_v1",
            "plan_id": "branch_plan_candidate_contacts_alice_fallback",
            "selected_branch_id": "fallback_full_name",
            "branch_depth": 2,
            "fallback_count": 1,
            "branch_outcomes": [
                {
                    "schema_version": "branch_outcome_v1",
                    "branch_id": "direct_short_name",
                    "attempted": True,
                    "selected": False,
                    "outcome": "rejected",
                    "failure_cause": "tool_runtime_error",
                    "retry_eligible": True,
                    "refinement_eligible": False,
                    "message": "Unknown contact: Alice",
                    "depth": 1,
                    "trajectory": [],
                },
                {
                    "schema_version": "branch_outcome_v1",
                    "branch_id": "fallback_full_name",
                    "attempted": True,
                    "selected": True,
                    "outcome": "accepted",
                    "failure_cause": None,
                    "retry_eligible": False,
                    "refinement_eligible": False,
                    "message": "accepted",
                    "depth": 2,
                    "trajectory": [],
                },
            ],
        }

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[],
        )

        self.assertEqual(report["counts"]["branch_attempts"], 2)
        self.assertEqual(report["counts"]["branch_selected"], 1)
        self.assertEqual(report["branch_outcomes"], {"accepted": 1, "rejected": 1})
        self.assertEqual(report["branch_failure_causes"], {"tool_runtime_error": 1})
        self.assertIn("2", report["slices"]["branch_depth"])
        self.assertIn("fallback_full_name", report["slices"]["selected_branch"])
        self.assertIn("1", report["slices"]["fallback_count"])

    def test_report_summarizes_seed_transformations_suggestions_and_edits(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["seed_transformation"] = {
            "schema_version": "seed_transformation_v1",
            "transformation_id": "transform_seed_contacts_followup",
            "source_seed_id": "seed_contacts_v1",
            "transformation_type": "taxonomy_expansion",
            "target_taxonomy_node": "contact_followup",
            "capability_target": "stateful_contact_followup",
            "difficulty_movement": "easy_to_medium",
            "lineage": {"role": "scripted_seed_transformation"},
        }
        sample["lineage"]["task_suggester"] = {
            "role": "task_suggester",
            "output_type": "task_suggestion",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "suggestion-local-v1",
        }
        sample["lineage"]["task_editor"] = {
            "role": "task_editor",
            "output_type": "edited_task",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "editor-local-v1",
            "editor_action": "created_candidate",
        }
        rejection = _rejection()
        rejection["cause"] = "task_suggestion_rejected"
        rejection["details"]["seed_transformation"] = sample["lineage"]["seed_transformation"]
        rejection["details"]["task_suggestion"] = {
            "suggestion_id": "suggestion_network_lookup",
            "target_taxonomy_node": "network_research",
            "outcome": "rejected",
            "rejection_reason": "unsupported_taxonomy_node",
            "lineage": sample["lineage"]["task_suggester"],
        }
        rejection["details"]["role_lineages"] = {
            "task_suggester": sample["lineage"]["task_suggester"]
        }

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[rejection],
        )

        self.assertEqual(report["counts"]["seed_transformations"], 2)
        self.assertEqual(report["counts"]["task_suggestions"], 2)
        self.assertEqual(report["counts"]["task_edits"], 1)
        self.assertEqual(report["suggestion_outcomes"], {"rejected": 1})
        self.assertEqual(report["editor_actions"], {"created_candidate": 1})
        self.assertEqual(report["edit_rejection_causes"], {"unsupported_taxonomy_node": 1})
        self.assertIn("taxonomy_expansion", report["slices"]["seed_transformation_type"])
        self.assertIn("contact_followup", report["slices"]["taxonomy_node"])
        self.assertIn("task_suggester", report["slices"]["role_name"])
        self.assertIn("task_editor", report["slices"]["role_name"])

    def test_report_summarizes_source_governance_slices(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["source_provenance"] = {
            "source_bundle_id": "bundle_allowed_external_fixture",
            "source_policy_hash": "source-policy-hash",
            "source_ids": ["source_external_contacts"],
            "source_kinds": ["external"],
            "license_outcomes": ["allowed"],
            "license_labels": ["cc-by-4.0"],
            "external_source_eligible": True,
        }
        rejection = _rejection()
        rejection["cause"] = "source_policy_rejected"
        rejection["details"]["source_governance"] = {
            "source_bundle_id": "bundle_rejected_external_fixture",
            "source_policy_hash": "source-policy-rejected",
            "source_ids": ["source_external_contacts"],
            "source_kinds": ["external"],
            "license_outcomes": ["rejected"],
            "license_labels": ["unknown"],
            "external_source_eligible": False,
            "rejection_causes": ["license_unknown"],
        }

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[rejection],
        )

        self.assertIn("external", report["slices"]["source_kind"])
        self.assertIn("allowed", report["slices"]["license_policy_outcome"])
        self.assertIn("rejected", report["slices"]["license_policy_outcome"])
        self.assertIn("eligible", report["slices"]["external_source_eligibility"])
        self.assertIn("ineligible", report["slices"]["external_source_eligibility"])
        self.assertIn("license_unknown", report["slices"]["source_rejection_cause"])
        self.assertEqual(report["counts"]["executable"], 1)

    def test_report_summarizes_sandbox_audit_slices(self) -> None:
        from synthesis.quality import build_quality_report

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[_sample()],
            rejections=[],
            sandbox_audits=[
                {
                    "artifact": {"artifact_kind": "tool_handler"},
                    "scan": {"status": "passed"},
                    "admission": {"accepted": True},
                    "execution": {"status": "succeeded"},
                },
                {
                    "artifact": {"artifact_kind": "verifier"},
                    "scan": {"status": "rejected"},
                    "admission": {
                        "accepted": False,
                        "rejection_cause": "unsafe_generated_code",
                    },
                    "execution": None,
                },
            ],
        )

        self.assertEqual(report["sandbox_admission_outcomes"], {"accepted": 1, "rejected": 1})
        self.assertIn("tool_handler", report["slices"]["sandbox_artifact_kind"])
        self.assertIn("verifier", report["slices"]["sandbox_artifact_kind"])
        self.assertIn("passed", report["slices"]["sandbox_scan_status"])
        self.assertIn("rejected", report["slices"]["sandbox_scan_status"])
        self.assertIn("accepted", report["slices"]["sandbox_admission_outcome"])
        self.assertIn("unsafe_generated_code", report["slices"]["sandbox_rejection_cause"])
        self.assertIn("succeeded", report["slices"]["sandbox_execution_status"])

    def test_report_summarizes_run_profile_slices_for_samples_and_rejections(self) -> None:
        from synthesis.quality import build_quality_report

        sample = _sample()
        sample["lineage"]["run_profile"] = _run_profile_attribution()
        rejection = _rejection()
        rejection["details"]["run_profile"] = _run_profile_attribution()

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[sample],
            rejections=[rejection],
        )

        self.assertEqual(
            report["slices"]["run_profile_id"]["foundation_fixture_profile"],
            {"total": 2, "accepted": 1, "rejected": 1, "success_rate": 0.5},
        )
        self.assertEqual(
            report["slices"]["generation_mode"]["foundation_fixture"],
            {"total": 2, "accepted": 1, "rejected": 1, "success_rate": 0.5},
        )
        self.assertEqual(
            report["slices"]["run_profile_schema_version"]["run_profile_v1"],
            {"total": 2, "accepted": 1, "rejected": 1, "success_rate": 0.5},
        )

    def test_no_profile_records_do_not_create_unknown_profile_slices(self) -> None:
        from synthesis.quality import build_quality_report

        report = build_quality_report(
            dataset_version="dataset_test",
            samples=[_sample()],
            rejections=[_rejection()],
        )

        self.assertEqual(report["slices"]["run_profile_id"], {})
        self.assertEqual(report["slices"]["generation_mode"], {})
        self.assertEqual(report["slices"]["run_profile_schema_version"], {})

    def test_duplicate_signature_uses_normalized_instruction_and_ordered_actions(self) -> None:
        from synthesis.quality import duplicate_signature

        sample = _sample()
        sample["task"]["instruction"] = "  Find Alice Zhang's   email address. "

        self.assertEqual(
            duplicate_signature(sample),
            ("find alice zhang's email address.", ("lookup_contact_email",)),
        )

    def test_parent_comparison_reports_count_rate_slice_and_cause_deltas(self) -> None:
        from synthesis.quality import build_parent_comparison

        parent = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_parent",
            "counts": {"accepted": 1, "rejected": 2},
            "rates": {"success_rate": 0.25, "executable_rate": 0.75},
            "slices": {"difficulty_level": {"easy": {}, "medium": {}}},
            "rejection_causes": {"verification_failed": 2},
        }
        current = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_current",
            "counts": {"accepted": 3, "rejected": 1},
            "rates": {"success_rate": 0.75, "executable_rate": 1.0},
            "slices": {"difficulty_level": {"easy": {}, "hard": {}}},
            "rejection_causes": {"quality_duplicate": 1},
        }

        comparison = build_parent_comparison(current=current, parent=parent)

        self.assertEqual(comparison["accepted_count_delta"], 2)
        self.assertEqual(comparison["rejected_count_delta"], -1)
        self.assertEqual(comparison["success_rate_delta"], 0.5)
        self.assertEqual(comparison["executable_rate_delta"], 0.25)
        self.assertEqual(comparison["new_slice_keys"], {"difficulty_level": ["hard"]})
        self.assertEqual(comparison["removed_slice_keys"], {"difficulty_level": ["medium"]})
        self.assertEqual(
            comparison["rejection_cause_deltas"],
            {"quality_duplicate": 1, "verification_failed": -2},
        )

    def test_parent_comparison_reports_new_profile_slice_keys(self) -> None:
        from synthesis.quality import build_parent_comparison

        parent = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_parent",
            "counts": {"accepted": 1, "rejected": 0},
            "rates": {"success_rate": 1.0, "executable_rate": 1.0},
            "slices": {"dataset_version": {"dataset_parent": {}}},
            "rejection_causes": {},
        }
        current = {
            "schema_version": "quality_report_v1",
            "dataset_version": "dataset_current",
            "counts": {"accepted": 1, "rejected": 0},
            "rates": {"success_rate": 1.0, "executable_rate": 1.0},
            "slices": {
                "dataset_version": {"dataset_current": {}},
                "run_profile_id": {"foundation_fixture_profile": {}},
                "generation_mode": {"foundation_fixture": {}},
                "run_profile_schema_version": {"run_profile_v1": {}},
            },
            "rejection_causes": {},
        }

        comparison = build_parent_comparison(current=current, parent=parent)

        self.assertEqual(
            comparison["new_slice_keys"],
            {
                "dataset_version": ["dataset_current"],
                "generation_mode": ["foundation_fixture"],
                "run_profile_id": ["foundation_fixture_profile"],
                "run_profile_schema_version": ["run_profile_v1"],
            },
        )

    def test_parent_comparison_reports_coverage_and_concentration_deltas(
        self,
    ) -> None:
        from synthesis.quality import build_parent_comparison

        def report(
            dataset_version: str,
            *,
            family_count: int,
            family_share: float,
            grounding_count: int,
            max_reuse: int,
            difficulty: dict[str, int],
            status: str,
            digest: str,
        ) -> dict[str, object]:
            return {
                "schema_version": "quality_report_v1",
                "dataset_version": dataset_version,
                "counts": {"accepted": 10, "rejected": 0},
                "rates": {
                    "success_rate": 1.0,
                    "executable_rate": 1.0,
                },
                "slices": {},
                "rejection_causes": {},
                "coverage": {
                    "evidence_hash": "sha256:" + digest * 64,
                    "distributions": {
                        "structural_families": {
                            "distinct_count": family_count,
                            "largest_family_share": family_share,
                        },
                        "grounding_reuse": {
                            "distinct_grounding_count": grounding_count,
                            "max_accepted_per_grounding": max_reuse,
                        },
                        "difficulty": {
                            "accepted_by_level": difficulty,
                        },
                    },
                    "fulfillment": {"status": status},
                },
            }

        comparison = build_parent_comparison(
            current=report(
                "dataset_current",
                family_count=5,
                family_share=0.3,
                grounding_count=8,
                max_reuse=2,
                difficulty={"easy": 4, "hard": 6},
                status="fulfilled",
                digest="b",
            ),
            parent=report(
                "dataset_parent",
                family_count=3,
                family_share=0.6,
                grounding_count=5,
                max_reuse=3,
                difficulty={"easy": 7, "medium": 3},
                status="incomplete",
                digest="a",
            ),
        )

        self.assertEqual(
            comparison["coverage"],
            {
                "parent_evidence_hash": "sha256:" + "a" * 64,
                "current_evidence_hash": "sha256:" + "b" * 64,
                "structural_family_count_delta": 2,
                "largest_family_share_delta": -0.3,
                "distinct_grounding_count_delta": 3,
                "max_accepted_per_grounding_delta": -1,
                "difficulty_count_deltas": {
                    "easy": -3,
                    "hard": 6,
                    "medium": -3,
                },
                "parent_fulfillment_status": "incomplete",
                "current_fulfillment_status": "fulfilled",
            },
        )

    def test_review_record_has_stable_shape(self) -> None:
        from synthesis.quality import build_review_record

        record = build_review_record(
            candidate_id="candidate_duplicate",
            cause="quality_duplicate",
            task={"instruction": "Find Alice Zhang's email address."},
            uncertainty_reason="Exact duplicate requires human policy review.",
            source_artifact="rejections.jsonl",
        )

        self.assertEqual(record["schema_version"], "human_review_record_v1")
        self.assertEqual(record["candidate_id"], "candidate_duplicate")
        self.assertEqual(record["cause"], "quality_duplicate")
        self.assertEqual(record["source_artifact"], "rejections.jsonl")
        self.assertEqual(record["created_at"], "1970-01-01T00:00:00Z")

    def test_curriculum_order_sorts_fixture_candidates_by_difficulty(self) -> None:
        from synthesis.tasks import CandidateTask, order_candidates_by_curriculum

        hard = CandidateTask(
            candidate_id="candidate_hard",
            instruction="Hard task.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={**_difficulty(), "level": "hard", "tool_count": 2},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )
        easy = CandidateTask(
            candidate_id="candidate_easy",
            instruction="Easy task.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=_difficulty(),
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )

        ordered = order_candidates_by_curriculum([hard, easy])

        self.assertEqual([candidate.candidate_id for candidate in ordered], ["candidate_easy", "candidate_hard"])


class QualityPipelineTest(unittest.TestCase):
    def test_writes_quality_report_and_manifest_reference(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_test")

            self.assertTrue(result.quality_report_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["quality_report"], "quality_report.json")

            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["accepted"], 2)
            self.assertEqual(report["counts"]["rejected"], 1)

    def test_run_profile_purpose_is_preserved_in_manifest_and_sample_lineage(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(Path("tests/fixtures/run_profiles/foundation-fixture.json"))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            result = run_foundation_pipeline(
                output_dir,
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_profile"]["profile_purpose"], "release_candidate")

            sample = json.loads(
                result.samples_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(
                sample["lineage"]["run_profile"]["profile_purpose"],
                "release_candidate",
            )

    def test_rejects_later_duplicate_accepted_candidate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def duplicate_generator(seed) -> list[CandidateTask]:
            task = CandidateTask(
                candidate_id="candidate_contacts_alice",
                instruction="Find Alice Zhang's email address using the contact database.",
                constraints={"must_use_tool": "lookup_contact_email"},
                difficulty=_difficulty(),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=(seed.seed_id,),
            )
            return [
                task,
                CandidateTask(
                    candidate_id="candidate_contacts_alice_duplicate",
                    instruction="  find alice zhang's email address using the contact database. ",
                    constraints=task.constraints,
                    difficulty=task.difficulty,
                    tool_name=task.tool_name,
                    arguments=task.arguments,
                    expected_answer=task.expected_answer,
                    seed_ids=task.seed_ids,
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_duplicate_test",
                candidate_generator=duplicate_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "quality_duplicate")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rejection_causes"], {"quality_duplicate": 1})

    def test_rejects_final_answer_not_supported_by_observation(self) -> None:
        from synthesis.execution import ExecutionResult
        from synthesis.pipeline import run_foundation_pipeline

        def generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_unsupported_answer",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty=_difficulty(),
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        unsupported_execution = ExecutionResult(
            trajectory=[
                {"type": "action", "tool": "lookup_contact_email", "arguments": {"name": "Alice Zhang"}},
                {
                    "type": "observation",
                    "tool": "lookup_contact_email",
                    "observation": {"name": "Alice Zhang", "email": "wrong@example.test"},
                },
                {
                    "type": "final_response",
                    "content": "Alice Zhang's email is alice.zhang@example.test.",
                },
            ],
            final_response="Alice Zhang's email is alice.zhang@example.test.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "synthesis.candidate_processing.execute_candidate",
                return_value=unsupported_execution,
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_logic_test",
                    candidate_generator=generator,
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "solution_logic_error")

    def test_writes_parent_comparison_when_parent_artifact_is_provided(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            parent_path = tmp_path / "parent_quality_report.json"
            parent_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality_report_v1",
                        "dataset_version": "dataset_parent",
                        "counts": {"accepted": 0, "rejected": 1},
                        "rates": {"success_rate": 0.0, "executable_rate": 1.0},
                        "slices": {"rejection_cause": {"verification_failed": {}}},
                        "rejection_causes": {"verification_failed": 1},
                    }
                ),
                encoding="utf-8",
            )

            result = run_foundation_pipeline(
                tmp_path / "current",
                dataset_version="dataset_current",
                parent_artifact_path=parent_path,
            )

            self.assertIsNotNone(result.parent_comparison_path)
            comparison = json.loads(result.parent_comparison_path.read_text(encoding="utf-8"))
            self.assertEqual(comparison["parent_dataset_version"], "dataset_parent")
            self.assertEqual(comparison["current_dataset_version"], "dataset_current")

    def test_review_queue_is_disabled_by_default_and_enabled_by_policy(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def duplicates(seed) -> list[CandidateTask]:
            base = CandidateTask(
                candidate_id="candidate_a",
                instruction="Find Alice Zhang's email address.",
                constraints={"must_use_tool": "lookup_contact_email"},
                difficulty=_difficulty(),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=(seed.seed_id,),
            )
            return [
                base,
                CandidateTask(
                    candidate_id="candidate_b",
                    instruction=base.instruction,
                    constraints=base.constraints,
                    difficulty=base.difficulty,
                    tool_name=base.tool_name,
                    arguments=base.arguments,
                    expected_answer=base.expected_answer,
                    seed_ids=base.seed_ids,
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            disabled_dir = Path(tmpdir) / "disabled"
            enabled_dir = Path(tmpdir) / "enabled"
            disabled = run_foundation_pipeline(
                disabled_dir,
                dataset_version="dataset_review_disabled",
                candidate_generator=duplicates,
            )
            enabled = run_foundation_pipeline(
                enabled_dir,
                dataset_version="dataset_review_enabled",
                candidate_generator=duplicates,
                route_reviewable_failures=True,
            )

            self.assertIsNone(disabled.review_queue_path)
            self.assertFalse((disabled_dir / "review_queue.jsonl").exists())
            self.assertFalse((disabled_dir / "release_review_queue.jsonl").exists())
            self.assertFalse((disabled_dir / "review_resolution_report.json").exists())
            self.assertIsNotNone(enabled.review_queue_path)
            self.assertEqual(enabled.review_queue_path, enabled_dir / "review_queue.jsonl")
            self.assertFalse((enabled_dir / "release_review_queue.jsonl").exists())
            self.assertFalse((enabled_dir / "review_resolution_report.json").exists())
            record = json.loads(enabled.review_queue_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["schema_version"], "human_review_record_v1")
            self.assertEqual(record["cause"], "quality_duplicate")

    def test_optional_artifacts_are_removed_when_disabled_on_reused_output_dir(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def duplicates(seed) -> list[CandidateTask]:
            base = CandidateTask(
                candidate_id="candidate_a",
                instruction="Find Alice Zhang's email address.",
                constraints={"must_use_tool": "lookup_contact_email"},
                difficulty=_difficulty(),
                tool_name="lookup_contact_email",
                arguments={"name": "Alice Zhang"},
                expected_answer="alice.zhang@example.test",
                seed_ids=(seed.seed_id,),
            )
            return [
                base,
                CandidateTask(
                    candidate_id="candidate_b",
                    instruction=base.instruction,
                    constraints=base.constraints,
                    difficulty=base.difficulty,
                    tool_name=base.tool_name,
                    arguments=base.arguments,
                    expected_answer=base.expected_answer,
                    seed_ids=base.seed_ids,
                ),
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "dataset"
            parent_path = Path(tmpdir) / "parent_quality_report.json"
            parent_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality_report_v1",
                        "dataset_version": "dataset_parent",
                        "counts": {"accepted": 0, "rejected": 1},
                        "rates": {"success_rate": 0.0, "executable_rate": 1.0},
                        "slices": {"rejection_cause": {"verification_failed": {}}},
                        "rejection_causes": {"verification_failed": 1},
                    }
                ),
                encoding="utf-8",
            )

            enabled = run_foundation_pipeline(
                output_dir,
                dataset_version="dataset_optional_enabled",
                candidate_generator=duplicates,
                parent_artifact_path=parent_path,
                route_reviewable_failures=True,
            )
            self.assertTrue(enabled.review_queue_path.exists())
            self.assertTrue(enabled.parent_comparison_path.exists())

            disabled = run_foundation_pipeline(
                output_dir,
                dataset_version="dataset_optional_disabled",
                candidate_generator=duplicates,
            )

            self.assertIsNone(disabled.review_queue_path)
            self.assertIsNone(disabled.parent_comparison_path)
            self.assertFalse((output_dir / "review_queue.jsonl").exists())
            self.assertFalse((output_dir / "parent_comparison.json").exists())


def _difficulty() -> dict[str, object]:
    return {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }


def _sample() -> dict[str, object]:
    return {
        "sample_id": "sample_candidate_contacts_alice",
        "dataset_version": "dataset_test",
        "environment": {"id": "contacts_fixture", "version": "env_contacts_v1"},
        "tools": [{"name": "lookup_contact_email", "version": "tool_lookup_contact_email_v1"}],
        "task": {
            "instruction": "Find Alice Zhang's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": _difficulty(),
        },
        "trajectory": [
            {"type": "action", "tool": "lookup_contact_email", "arguments": {"name": "Alice Zhang"}},
            {
                "type": "observation",
                "tool": "lookup_contact_email",
                "observation": {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
            },
            {"type": "final_response", "content": "Alice Zhang's email is alice.zhang@example.test."},
        ],
        "final_response": "Alice Zhang's email is alice.zhang@example.test.",
        "verifier": {"id": "exact_answer_verifier", "version": "verifier_exact_answer_v1"},
        "verification": {
            "passed": True,
            "checks": [
                {
                    "name": "final_response_contains_expected_answer",
                    "passed": True,
                    "expected": "alice.zhang@example.test",
                    "actual": "Alice Zhang's email is alice.zhang@example.test.",
                }
            ],
        },
        "quality": {"scores": {"executable": 1.0}, "tags": ["foundation"]},
        "lineage": {"generator": {"role": "task_generation"}, "verifier": {"id": "exact_answer_verifier"}},
    }


def _rejection() -> dict[str, object]:
    return {
        "candidate_id": "candidate_contacts_ben_bad_expectation",
        "cause": "verification_failed",
        "task": {
            "candidate_id": "candidate_contacts_ben_bad_expectation",
            "instruction": "Find Ben Carter's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": _difficulty(),
        },
        "details": {"check": "final_response_contains_expected_answer"},
    }


def _run_profile_attribution() -> dict[str, object]:
    return {
        "schema_version": "run_profile_attribution_v1",
        "profile_schema_version": "run_profile_v1",
        "profile_id": "foundation_fixture_profile",
        "generation_mode": "foundation_fixture",
        "profile_purpose": "release_candidate",
        "config_hash": "sha256:" + "1" * 64,
    }


if __name__ == "__main__":
    unittest.main()
