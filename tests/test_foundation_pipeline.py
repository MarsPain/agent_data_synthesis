from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.tasks import CandidateTask, EditedTask, TaskExpansionResult


class FoundationPipelineTest(unittest.TestCase):
    def test_generates_verified_sample_and_manifest(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_test")

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.samples_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.rejections_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            sample = samples[0]
            self.assertEqual(sample["dataset_version"], "dataset_test")
            self.assertEqual(sample["environment"]["id"], "contacts_fixture")
            self.assertEqual(sample["tools"][0]["name"], "lookup_contact_email")
            self.assertEqual(sample["task"]["difficulty"]["tool_count"], 1)
            self.assertEqual(sample["trajectory"][-1]["type"], "final_response")
            self.assertIn("verifier", sample)
            self.assertEqual(sample["verifier"]["id"], "exact_answer_verifier")
            self.assertTrue(sample["verification"]["passed"])
            self.assertIn("provider_host", sample["lineage"]["generator"])
            self.assertEqual(sample["lineage"]["generator"]["provider_host"], "local")
            self.assertEqual(sample["lineage"]["generator"]["model"], "scripted")
            self.assertEqual(sample["lineage"]["generator"]["role"], "scripted_task_generation")
            self.assertEqual(sample["lineage"]["generator"]["role_version"], "role_scripted_task_generation_v1")
            self.assertEqual(sample["lineage"]["generator"]["output_type"], "candidate_tasks")
            self.assertNotIn("secret-test-key", json.dumps(sample))

            stateful_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("task_type") == "contact_followup"
            )
            action_tools = [
                event["tool"]
                for event in stateful_sample["trajectory"]
                if event["type"] == "action"
            ]
            self.assertEqual(
                action_tools,
                ["lookup_contact_email", "record_contact_followup"],
            )
            self.assertTrue(
                any(event["type"] == "state_change" for event in stateful_sample["trajectory"])
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role"],
                "scripted_solution_policy",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role_version"],
                "role_scripted_solution_policy_v1",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["output_type"],
                "solution_policy",
            )
            self.assertEqual(stateful_sample["quality"]["tags"], ["foundation", "sqlite_fixture", "multi_step", "stateful"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_test")
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["rejected_count"], 1)
            self.assertEqual(manifest["quality"]["success_rate"], 2 / 3)
            self.assertEqual(manifest["schema_version"], "dataset_manifest_v1")
            self.assertIsNone(manifest["parent_dataset_version"])
            self.assertEqual(manifest["artifacts"]["quality_report"], "quality_report.json")
            self.assertEqual(manifest["environment_versions"], ["env_contacts_v2"])
            self.assertEqual(
                manifest["tool_versions"],
                ["tool_lookup_contact_email_v1", "tool_record_contact_followup_v1"],
            )
            self.assertEqual(manifest["verifier_versions"], ["verifier_exact_answer_state_v2"])
            self.assertEqual(manifest["rejection_causes"], {"verification_failed": 1})

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertIn("expected", rejection["details"])

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["schema_version"], "quality_report_v1")
            self.assertEqual(quality_report["counts"]["accepted"], 2)
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertIn("difficulty_level", quality_report["slices"])
            self.assertIn(
                "lookup_contact_email > record_contact_followup",
                quality_report["slices"]["tool_combination"],
            )

    def test_adapter_fixture_path_records_lineage_without_changing_default_counts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            direct = run_foundation_pipeline(
                Path(tmpdir) / "direct",
                dataset_version="dataset_direct",
            )
            adapter = run_foundation_pipeline(
                Path(tmpdir) / "adapter",
                dataset_version="dataset_adapter",
                enable_mcp_adapter=True,
            )

            self.assertEqual(adapter.accepted_count, direct.accepted_count)
            self.assertEqual(adapter.rejected_count, direct.rejected_count)
            direct_samples = [
                json.loads(line)
                for line in direct.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            adapter_samples = [
                json.loads(line)
                for line in adapter.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [sample["final_response"] for sample in adapter_samples],
                [sample["final_response"] for sample in direct_samples],
            )
            self.assertNotIn("adapter", direct_samples[0]["lineage"])
            self.assertEqual(
                adapter_samples[0]["lineage"]["adapter"][0]["adapter_id"],
                "contacts_local_mcp_adapter",
            )
            self.assertEqual(
                adapter_samples[0]["lineage"]["adapter"][0]["execution_status"],
                "succeeded",
            )

            report = json.loads(adapter.quality_report_path.read_text(encoding="utf-8"))
            self.assertIn(
                "contacts_local_mcp_adapter",
                report["slices"]["adapter_id"],
            )
            self.assertIn(
                "mcp-compatible-local-shim",
                report["slices"]["adapter_protocol"],
            )
            self.assertIn("succeeded", report["slices"]["adapter_execution_outcome"])

    def test_sandbox_fixture_records_audit_artifact_without_changing_default_counts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            direct = run_foundation_pipeline(
                Path(tmpdir) / "direct",
                dataset_version="dataset_direct",
            )
            sandboxed = run_foundation_pipeline(
                Path(tmpdir) / "sandboxed",
                dataset_version="dataset_sandboxed",
                enable_sandbox_fixture=True,
            )

            self.assertEqual(sandboxed.accepted_count, direct.accepted_count)
            self.assertEqual(sandboxed.rejected_count, direct.rejected_count)
            self.assertIsNotNone(sandboxed.sandbox_audits_path)
            manifest = json.loads(sandboxed.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["sandbox_audits"], "sandbox_audits.jsonl")
            audits = [
                json.loads(line)
                for line in sandboxed.sandbox_audits_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [audit["admission"]["accepted"] for audit in audits],
                [True, False],
            )
            audit_text = sandboxed.sandbox_audits_path.read_text(encoding="utf-8")
            self.assertNotIn("def ", audit_text)
            self.assertNotIn("sk-live", audit_text)

            report = json.loads(sandboxed.quality_report_path.read_text(encoding="utf-8"))
            self.assertIn("passed", report["slices"]["sandbox_scan_status"])
            self.assertIn("rejected", report["slices"]["sandbox_admission_outcome"])
            self.assertIn("succeeded", report["slices"]["sandbox_execution_status"])

            direct_manifest = json.loads(direct.manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("sandbox_audits", direct_manifest["artifacts"])

    def test_adapter_contract_rejection_is_non_executable(self) -> None:
        from synthesis.execution import SolutionPolicy, ToolStep
        from synthesis.pipeline import run_foundation_pipeline

        def one_candidate(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_bad_adapter_args",
                    instruction="Find Alice Zhang's email address.",
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
                    seed_ids=(seed.seed_id,),
                )
            ]

        def bad_policy(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_bad_adapter_args",
                role="scripted_solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": 42},
                    ),
                ),
                final_response_template="{email}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_adapter_rejection",
                candidate_generator=one_candidate,
                policy_generator=bad_policy,
                enable_mcp_adapter=True,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "adapter_contract_rejected")
            self.assertEqual(
                rejection["details"]["adapter_rejection"]["rejection_cause"],
                "tool_schema_error",
            )
            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["executable"], 0)
            self.assertIn("tool_schema_error", report["slices"]["adapter_rejection_cause"])

    def test_execution_rejects_malformed_solution_policy_before_tool_call(self) -> None:
        from synthesis.execution import PolicyValidationError, execute_candidate
        from synthesis.environments import ContactEnvironment
        from synthesis.tools import build_contact_tool_registry

        task = CandidateTask(
            candidate_id="candidate_bad_policy",
            instruction="Find Alice Zhang's email address.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={"level": "easy", "tool_count": 1},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )
        policy = SolutionPolicy(
            policy_id="policy_bad",
            role="scripted_solution_policy",
            steps=(ToolStep(tool_name="", arguments={"name": "Alice Zhang"}),),
            final_response_template="{email}",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)

            with self.assertRaisesRegex(PolicyValidationError, "steps.0.tool_name"):
                execute_candidate(task, registry, policy=policy)

    def test_branch_execution_preserves_failed_branch_events_without_state_leakage(self) -> None:
        from synthesis.execution import SolutionPolicy, execute_candidate
        from synthesis.environments import ContactEnvironment
        from synthesis.tools import build_contact_tool_registry

        task = CandidateTask(
            candidate_id="candidate_branch_state_reset",
            instruction="Try a mutating branch, then fall back to a read-only lookup.",
            constraints={"task_type": "contact_branch_fallback"},
            difficulty={
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 1,
                "branch_depth": 2,
                "fallback_count": 1,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
            branch_plan={
                "schema_version": "branch_plan_v1",
                "plan_id": "branch_plan_state_reset",
                "max_depth": 2,
                "branches": [
                    {
                        "branch_id": "mutating_bad_template",
                        "node_type": "attempt",
                        "parent_id": None,
                        "condition": "Record a follow-up but fail response rendering.",
                        "steps": [
                            {
                                "tool_name": "record_contact_followup",
                                "arguments": {
                                    "name": "Alice Zhang",
                                    "note": "temporary note",
                                },
                            }
                        ],
                        "final_response_template": "{missing_field}",
                        "terminal_outcome": "fallback_on_failure",
                    },
                    {
                        "branch_id": "read_only_lookup",
                        "node_type": "fallback",
                        "parent_id": "mutating_bad_template",
                        "condition": "Use the read-only lookup after the branch fails.",
                        "steps": [
                            {
                                "tool_name": "lookup_contact_email",
                                "arguments": {"name": "Alice Zhang"},
                            }
                        ],
                        "final_response_template": "{name}'s email is {email}.",
                        "terminal_outcome": "accept_on_success",
                    },
                ],
            },
        )
        policy = SolutionPolicy(
            policy_id="policy_branch_state_reset",
            role="scripted_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            branch_plan=task.branch_plan,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)

            execution = execute_candidate(task, registry, policy=policy)

            failed_branch = execution.branch_outcomes[0]
            self.assertEqual(failed_branch["branch_id"], "mutating_bad_template")
            self.assertTrue(
                any(event["type"] == "state_change" for event in failed_branch["trajectory"])
            )
            self.assertFalse(environment.has_followup("Alice Zhang", "temporary note"))
            self.assertEqual(execution.branch_outcomes[1]["branch_id"], "read_only_lookup")

    def test_task_expansion_adds_edited_candidate_and_inspectable_rejection(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_task_expansion",
                enable_task_expansion=True,
            )

            self.assertEqual(result.accepted_count, 3)
            self.assertEqual(result.rejected_count, 2)

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            expanded = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("taxonomy_node") == "contact_followup"
                and sample["task"]["constraints"].get("source") == "task_expansion"
            )
            self.assertEqual(
                expanded["lineage"]["seed_transformation"]["target_taxonomy_node"],
                "contact_followup",
            )
            self.assertEqual(expanded["lineage"]["task_suggester"]["role"], "task_suggester")
            self.assertEqual(expanded["lineage"]["task_editor"]["role"], "task_editor")
            self.assertEqual(expanded["lineage"]["task_editor"]["output_type"], "edited_task")
            self.assertEqual(
                [event["tool"] for event in expanded["trajectory"] if event["type"] == "action"],
                ["lookup_contact_email", "record_contact_followup"],
            )

            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(encoding="utf-8").splitlines()
            ]
            suggestion_rejection = next(
                rejection
                for rejection in rejections
                if rejection["cause"] == "task_suggestion_rejected"
            )
            self.assertEqual(
                suggestion_rejection["details"]["task_suggestion"]["outcome"],
                "rejected",
            )
            self.assertEqual(
                suggestion_rejection["details"]["role_lineages"]["task_suggester"]["role"],
                "task_suggester",
            )

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["seed_transformations"], 2)
            self.assertEqual(quality_report["counts"]["task_suggestions"], 2)
            self.assertEqual(quality_report["counts"]["task_edits"], 1)
            self.assertIn("contact_followup", quality_report["slices"]["taxonomy_node"])
            self.assertIn("accepted", quality_report["slices"]["suggestion_outcome"])
            self.assertIn("rejected", quality_report["slices"]["suggestion_outcome"])
            self.assertIn("created_candidate", quality_report["slices"]["editor_action"])

    def test_task_expansion_uses_normal_tool_expansion_rerun_gate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import CapabilityGap, ToolProposal

        def no_initial_candidates(seed) -> list[CandidateTask]:
            return []

        def expansion_generator(seed) -> TaskExpansionResult:
            return TaskExpansionResult(
                candidates=[
                    CandidateTask(
                        candidate_id="candidate_expanded_list_contacts",
                        instruction="List the known contact names.",
                        constraints={"must_use_tool": "list_contact_names"},
                        difficulty={
                            "level": "easy",
                            "tool_count": 1,
                            "constraint_count": 1,
                            "state_changes": 0,
                            "ambiguity": "none",
                            "recovery_paths": 0,
                        },
                        tool_name="list_contact_names",
                        arguments={},
                        expected_answer="Alice Zhang",
                        seed_ids=(seed.seed_id,),
                    )
                ],
                rejected_suggestions=[],
            )

        def proposal_generator(gap: CapabilityGap) -> ToolProposal:
            self.assertEqual(gap.tool_name, "list_contact_names")
            return ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "proposal-hash",
                },
            )

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_list_contacts",
                role="solution_policy",
                steps=(ToolStep(tool_name="list_contact_names", arguments={}),),
                final_response_template="Known contacts: {contacts}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_expansion_tool_gate",
                candidate_generator=no_initial_candidates,
                policy_generator=policy_generator,
                enable_task_expansion=True,
                task_expansion_generator=expansion_generator,
                tool_proposal_generator=proposal_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["trajectory"][0]["tool"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["admission"]["outcome"], "accepted")

    def test_task_expansion_rejections_preserve_valid_nested_contracts(self) -> None:
        from synthesis.contracts import (
            validate_seed_transformation_record,
            validate_task_suggestion_record,
        )
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_task_expansion_contracts",
                enable_task_expansion=True,
            )

            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(encoding="utf-8").splitlines()
            ]
            suggestion_rejection = next(
                rejection
                for rejection in rejections
                if rejection["cause"] == "task_suggestion_rejected"
            )

            validate_seed_transformation_record(suggestion_rejection["details"]["seed_transformation"])
            validate_task_suggestion_record(suggestion_rejection["details"]["task_suggestion"])

    def test_task_expansion_persists_editor_rejection_details(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def no_initial_candidates(seed) -> list[CandidateTask]:
            return []

        def expansion_generator(seed) -> TaskExpansionResult:
            return TaskExpansionResult(
                candidates=[],
                rejected_suggestions=[],
                rejected_edits=[
                    EditedTask(
                        suggestion_id="suggestion_editor_rejected",
                        editor_action="rejected",
                        lineage={
                            "role": "task_editor",
                            "role_version": "role_task_editor_v1",
                            "output_type": "edited_task",
                            "provider_host": "local",
                            "model": "scripted",
                            "config_hash": "task_editor_local_v1",
                        },
                        rejection={
                            "cause": "unsupported_tool",
                            "message": "Edited task requested an unsupported executable tool.",
                        },
                    )
                ],
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_editor_rejection",
                candidate_generator=no_initial_candidates,
                enable_task_expansion=True,
                task_expansion_generator=expansion_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "task_editor_rejected")
            self.assertEqual(rejection["details"]["task_editor"]["editor_action"], "rejected")
            self.assertEqual(
                rejection["details"]["role_lineages"]["task_editor"]["role"],
                "task_editor",
            )

    def test_stateful_task_rejects_policy_that_skips_required_mutation(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def stateful_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_contacts_alice_followup",
                    instruction="Find Alice Zhang's email and record a follow-up note.",
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
                )
            ]

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_skip_mutation",
                role="scripted_solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": "Alice Zhang"},
                    ),
                ),
                final_response_template="{name}'s email is {email}. Follow-up recorded.",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_state_verifier_test",
                candidate_generator=stateful_candidate_generator,
                policy_generator=policy_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "solution_logic_error")
            self.assertEqual(rejection["details"]["check"], "contact_followup_state_matches_expected")

    def test_verification_rejection_preserves_generator_and_policy_role_lineage(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def generated_bad_expectation(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_generated_ben_bad",
                    instruction="Find Ben Carter's email address.",
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
                    arguments={"name": "Ben Carter"},
                    expected_answer="ben@example.test",
                    seed_ids=(seed.seed_id,),
                    generation_lineage={
                        "role": "task_generation",
                        "role_version": "role_task_generation_v1",
                        "output_type": "candidate_tasks",
                        "provider_host": "llm.example.test",
                        "model": "test-generator",
                        "config_hash": "task-hash",
                    },
                )
            ]

        def remote_policy(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_generated_ben",
                role="solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": "Ben Carter"},
                    ),
                ),
                final_response_template="{name}'s email is {email}.",
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_role_rejection_lineage",
                candidate_generator=generated_bad_expectation,
                policy_generator=remote_policy,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertEqual(
                rejection["details"]["role_lineages"]["generator"]["role"],
                "task_generation",
            )
            self.assertEqual(
                rejection["details"]["role_lineages"]["solution_policy"]["role"],
                "solution_policy",
            )
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["role_outcomes"]["task_generation"]["rejected"], 1)
            self.assertEqual(quality_report["role_outcomes"]["solution_policy"]["rejected"], 1)

    def test_remote_policy_error_preserves_llm_cause_and_role_lineage(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def one_candidate(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_generated_alice",
                    instruction="Find Alice Zhang's email address.",
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
                    seed_ids=(seed.seed_id,),
                )
            ]

        def failing_policy(task: CandidateTask) -> SolutionPolicy:
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="TypeError",
                retryable=False,
                retry_count=2,
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                    "retry_count": 2,
                    "error_class": "TypeError",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_policy_error_lineage",
                candidate_generator=one_candidate,
                policy_generator=failing_policy,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "llm_response_schema_error")
            self.assertEqual(rejection["details"]["retry_count"], 2)
            self.assertEqual(rejection["details"]["lineage"]["role"], "solution_policy")
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["role_outcomes"]["solution_policy"]["rejected"], 1)

    def test_rejects_candidate_when_tool_execution_fails(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_contact_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_unknown_contact",
                    instruction="Find John Doe's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "John Doe"},
                    expected_answer="john.doe@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_tool_error_test",
                    candidate_generator=invalid_contact_generator,
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_runtime_error")
            self.assertEqual(rejection["details"]["error_class"], "KeyError")
            self.assertIn("John Doe", rejection["details"]["message"])

    def test_rejects_candidate_when_tool_arguments_violate_schema(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_arguments_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool_argument",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_schema_error_test",
                candidate_generator=invalid_arguments_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ToolSchemaError")
            self.assertIn("name", rejection["details"]["message"])

    def test_rejects_candidate_when_required_tool_is_missing(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def missing_tool_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="missing_tool",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_missing_test",
                candidate_generator=missing_tool_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_missing")
            self.assertEqual(rejection["details"]["error_class"], "ToolMissingError")
            self.assertEqual(rejection["details"]["capability_gap"]["gap_type"], "unknown_tool")

    def test_explicit_tool_expansion_admits_curated_tool_and_reruns_candidate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import CapabilityGap, ToolProposal

        def missing_tool_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_list_contacts",
                    instruction="List the known contact names.",
                    constraints={"must_use_tool": "list_contact_names"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="list_contact_names",
                    arguments={},
                    expected_answer="Alice Zhang",
                    seed_ids=(seed.seed_id,),
                )
            ]

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_list_contacts",
                role="solution_policy",
                steps=(ToolStep(tool_name="list_contact_names", arguments={}),),
                final_response_template="Known contacts: {contacts}",
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                },
            )

        def proposal_generator(gap: CapabilityGap) -> ToolProposal:
            self.assertEqual(gap.tool_name, "list_contact_names")
            return ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "proposal-hash",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_expansion_test",
                candidate_generator=missing_tool_generator,
                policy_generator=policy_generator,
                tool_proposal_generator=proposal_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            self.assertIsNotNone(result.tool_proposals_path)

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["trajectory"][0]["tool"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["proposal"]["tool_name"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["admission"]["outcome"], "accepted")

            proposals = [
                json.loads(line)
                for line in result.tool_proposals_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(proposals[0]["proposal"]["tool_name"], "list_contact_names")
            self.assertEqual(proposals[0]["admission"]["outcome"], "accepted")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["tool_proposals"], "tool_proposals.jsonl")

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["tool_proposals"], 1)
            self.assertEqual(quality_report["counts"]["capability_gaps"], 1)
            self.assertIn("list_contact_names", quality_report["slices"]["proposed_tool"])

    def test_branching_fixture_executes_fallback_path_and_reports_lineage(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_branching_test",
                enable_branching=True,
            )

            self.assertEqual(result.accepted_count, 3)
            self.assertEqual(result.rejected_count, 1)
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            branch_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("task_type") == "contact_branch_fallback"
            )

            self.assertEqual(branch_sample["lineage"]["branching"]["selected_branch_id"], "fallback_full_name")
            self.assertEqual(branch_sample["lineage"]["branching"]["branch_depth"], 2)
            self.assertEqual(len(branch_sample["lineage"]["branching"]["branch_outcomes"]), 2)
            self.assertEqual(
                branch_sample["lineage"]["branching"]["branch_outcomes"][0]["failure_cause"],
                "tool_runtime_error",
            )
            self.assertTrue(branch_sample["lineage"]["branching"]["branch_outcomes"][1]["selected"])
            self.assertEqual(branch_sample["trajectory"][0]["arguments"], {"name": "Alice Zhang"})
            self.assertIn("branching", branch_sample["quality"]["tags"])

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["branch_attempts"], 2)
            self.assertEqual(quality_report["counts"]["branch_selected"], 1)
            self.assertEqual(quality_report["branch_outcomes"], {"accepted": 1, "rejected": 1})
            self.assertIn("2", quality_report["slices"]["branch_depth"])
            self.assertIn("fallback_full_name", quality_report["slices"]["selected_branch"])

    def test_branch_failure_classifies_missing_tool_cause(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def branch_missing_tool(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_branch_missing_tool",
                    instruction="Try a missing branch tool.",
                    constraints={"task_type": "contact_branch_fallback"},
                    difficulty={
                        "level": "medium",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 1,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                    branch_plan={
                        "schema_version": "branch_plan_v1",
                        "plan_id": "branch_plan_missing_tool",
                        "max_depth": 1,
                        "branches": [
                            {
                                "branch_id": "missing_tool",
                                "node_type": "attempt",
                                "parent_id": None,
                                "condition": "Use a missing tool.",
                                "steps": [{"tool_name": "missing_tool", "arguments": {}}],
                                "final_response_template": "{email}",
                                "terminal_outcome": "accept_on_success",
                            }
                        ],
                    },
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_branch_missing_tool",
                candidate_generator=branch_missing_tool,
            )

            self.assertEqual(result.accepted_count, 0)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                rejection["details"]["branch_outcomes"][0]["failure_cause"],
                "tool_missing",
            )
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["branch_failure_causes"], {"tool_missing": 1})

    def test_rejects_candidate_when_candidate_shape_is_invalid(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_candidate_schema_error_test",
                candidate_generator=invalid_candidate_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "unknown_candidate")
            self.assertEqual(rejection["cause"], "candidate_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ContractValidationError")

    def test_registered_tool_smoke_gate_classifies_empty_registry(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("synthesis.pipeline.build_contact_tool_registry", return_value=ToolRegistry()):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_smoke_gate_test",
                    candidate_generator=lambda seed: [],
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "foundation_gate")
            self.assertEqual(rejection["cause"], "infrastructure_error")
            self.assertEqual(rejection["details"]["error_class"], "FoundationGateError")

    def test_generation_stage_provider_failure_writes_inspectable_artifacts(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def failing_generator(seed) -> list[CandidateTask]:
            raise LLMProviderError(
                cause="llm_provider_error",
                error_class="HTTPStatusError",
                retryable=True,
                retry_count=2,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_generation_failure_test",
                candidate_generator=failing_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "generation_stage")
            self.assertEqual(rejection["cause"], "llm_provider_error")
            self.assertEqual(rejection["details"]["error_class"], "HTTPStatusError")
            self.assertEqual(rejection["details"]["retry_count"], 2)
            self.assertTrue(rejection["details"]["retry_eligible"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rejection_causes"], {"llm_provider_error": 1})

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertEqual(quality_report["rejection_causes"], {"llm_provider_error": 1})


if __name__ == "__main__":
    unittest.main()
