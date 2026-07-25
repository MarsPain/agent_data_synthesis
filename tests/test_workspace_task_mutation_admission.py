from __future__ import annotations

import copy
import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import synthesis.mutation_admission
from synthesis.candidate_processing import (
    CandidateProcessingContext,
    CandidateProcessingOptions,
    process_candidate_through_gates,
)
from synthesis.llm import LLMConfig
from synthesis.mutation_admission import (
    build_local_candidate_admission_evaluator,
    policy_hash,
)
from synthesis.verification import ExactAnswerVerifier
from synthesis.workspace_environment import (
    WorkspaceCommentRecord,
    WorkspaceDocumentRecord,
    WorkspaceEnvironmentInput,
    WorkspaceProjectRecord,
    WorkspaceTaskRecord,
    WorkspaceTasksEnvironment,
)
from synthesis.workspace_tasks import (
    generate_workspace_fixture_candidates,
    prepare_workspace_candidate,
    scripted_workspace_solution_policy,
    workspace_mutation_policies,
    workspace_semantic_mutation_judge,
)
from synthesis.workspace_tools import build_workspace_tool_registry
from tests.test_workspace_pipeline import workspace_seed


class WorkspaceTaskMutationAuthorizationGenerationTest(unittest.TestCase):
    def test_workspace_task_creation_proposes_complete_requester_provenance(
        self,
    ) -> None:
        candidate = next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id
            == "candidate_workspace_launch_checklist_task"
        )

        record = candidate.contract().mutation_authorization

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(
            record["schema_version"],
            "mutation_authorization_record_v1",
        )
        self.assertEqual(
            record["policy_hash"],
            policy_hash(scripted_workspace_solution_policy(candidate)),
        )
        action = record["actions"][0]
        self.assertEqual(action["action_type"], "workspace_task_create")
        provenance = {
            argument["name"]: argument["origin"]
            for argument in action["arguments"]
        }
        self.assertEqual(
            provenance,
            {
                "title": "instruction",
                "priority": "instruction",
                "due_label": "instruction",
                "project_id": "tool_observation",
            },
        )
        task_policy = next(
            policy
            for policy in workspace_mutation_policies()
            if policy.task_type == "workspace_task_creation"
        )
        argument_policies = {
            argument.name: argument
            for argument in task_policy.arguments
        }
        for name in ("title", "priority", "due_label"):
            self.assertTrue(argument_policies[name].required)
            self.assertEqual(
                argument_policies[name].allowed_origins,
                ("instruction",),
            )


class WorkspaceTaskMutationAdmissionCandidateProcessingTest(unittest.TestCase):
    def _candidate(self):
        return next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id
            == "candidate_workspace_launch_checklist_task"
        )

    def _process(
        self,
        candidate,
        *,
        environment_input: WorkspaceEnvironmentInput | None = None,
        mode: str = "shadow",
    ):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = (
            WorkspaceTasksEnvironment.create_from_input(
                Path(temporary_directory.name),
                environment_input,
            )
            if environment_input is not None
            else WorkspaceTasksEnvironment.create_fixture(
                Path(temporary_directory.name)
            )
        )
        evaluator = build_local_candidate_admission_evaluator(
            mode=mode,
            policies=workspace_mutation_policies(environment),
            state_changing_tools=(
                "create_workspace_task",
                "add_workspace_comment",
            ),
            judge=workspace_semantic_mutation_judge,
        )
        outcome = process_candidate_through_gates(
            raw_task=candidate,
            context=CandidateProcessingContext(
                dataset_version="dataset_workspace_task_admission_test",
                environment=environment,
                registry=build_workspace_tool_registry(environment),
                adapter_shim=None,
                verifier=ExactAnswerVerifier(),
                llm_config=LLMConfig(base_url=None),
                generate_policy=scripted_workspace_solution_policy,
                admission_evaluator=evaluator,
            ),
            options=CandidateProcessingOptions(),
        )
        return outcome, environment

    def _with_task(
        self,
        *,
        instruction: str,
        expected_task: dict[str, object],
        search_arguments: dict[str, object] | None = None,
        candidate_id: str = "candidate_workspace_task_admission_case",
    ):
        base = self._candidate()
        return prepare_workspace_candidate(
            replace(
                base,
                candidate_id=candidate_id,
                instruction=instruction,
                arguments=search_arguments or dict(base.arguments),
                expected_answer=f"task_{str(expected_task['title']).lower().replace(' ', '_')}",
                expected_state={"workspace_task": expected_task},
            )
        )

    def test_literal_task_creation_executes_with_supported_shadow_evidence(
        self,
    ) -> None:
        outcome, environment = self._process(self._candidate())

        self.assertTrue(
            environment.has_workspace_task(
                project_id="project_alpha",
                title="Prepare launch checklist",
                priority="high",
                due_label="this_week",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertIn(
            "argument_literal_supported",
            evidence["semantic_verdict"]["reason_codes"],
        )
        self.assertIn(
            "argument_semantic_supported",
            evidence["semantic_verdict"]["reason_codes"],
        )
        self.assertIn(
            "observation_reference_supported",
            evidence["semantic_verdict"]["reason_codes"],
        )

    def test_supported_workspace_task_creation_executes_in_enforce_mode(
        self,
    ) -> None:
        outcome, environment = self._process(
            self._candidate(),
            mode="enforce",
        )

        self.assertTrue(
            environment.has_workspace_task(
                project_id="project_alpha",
                title="Prepare launch checklist",
                priority="high",
                due_label="this_week",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(evidence["mode"], "enforce")
        self.assertEqual(evidence["admission_outcome"], "judge_supported")
        self.assertEqual(evidence["model_independence"], "independent")

    def test_semantic_task_content_and_project_selection_are_supported(
        self,
    ) -> None:
        candidate = self._with_task(
            instruction=(
                "Locate the Alpha Launch project, then add a planning item to "
                "check launch readiness with urgent priority and a deadline "
                "during the current week."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Review launch readiness",
                "priority": "high",
                "due_label": "this_week",
            },
        )

        outcome, environment = self._process(candidate)

        self.assertTrue(
            environment.has_workspace_task(
                project_id="project_alpha",
                title="Review launch readiness",
                priority="high",
                due_label="this_week",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
        self.assertIn(
            "argument_semantic_supported",
            evidence["semantic_verdict"]["reason_codes"],
        )

    def test_beta_project_observation_is_bound_to_the_selected_project(
        self,
    ) -> None:
        candidate = self._with_task(
            instruction=(
                "Find the Beta Research project, then create the task "
                '"Summarize beta findings" with medium priority due next week.'
            ),
            search_arguments={"query": "Beta Research", "kind": "project"},
            expected_task={
                "project_id": "project_beta",
                "title": "Summarize beta findings",
                "priority": "medium",
                "due_label": "next_week",
            },
        )

        outcome, environment = self._process(candidate)

        self.assertTrue(
            environment.has_workspace_task(
                project_id="project_beta",
                title="Summarize beta findings",
                priority="medium",
                due_label="next_week",
            )
        )
        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")

    def test_direct_project_selection_does_not_require_a_lookup_verb(
        self,
    ) -> None:
        candidate = self._with_task(
            instruction=(
                "Create the high-priority launch checklist task due this week "
                "in the Alpha Launch project."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
        )

        outcome, _ = self._process(candidate)

        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")

    def test_project_name_tokens_are_not_global_cross_project_aliases(
        self,
    ) -> None:
        candidate = self._with_task(
            instruction=(
                "Create the high-priority launch checklist task due this week "
                "in the Gamma Launch project."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
        )
        environment_input = WorkspaceEnvironmentInput(
            projects=(
                WorkspaceProjectRecord(
                    "project_alpha",
                    "Alpha Launch",
                    "active",
                ),
                WorkspaceProjectRecord(
                    "project_gamma",
                    "Gamma Launch",
                    "active",
                ),
            ),
            tasks=(
                WorkspaceTaskRecord(
                    "task_existing",
                    "project_alpha",
                    "Existing task",
                    "medium",
                    "later",
                ),
            ),
            documents=(
                WorkspaceDocumentRecord(
                    "doc_gamma",
                    "project_gamma",
                    "Gamma brief",
                    "Gamma project context.",
                ),
            ),
            comments=(
                WorkspaceCommentRecord(
                    "comment_existing",
                    "task_existing",
                    "Existing task context.",
                ),
            ),
        )

        outcome, _ = self._process(
            candidate,
            environment_input=environment_input,
        )

        assert outcome.sample is not None
        evidence = outcome.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "failed",
        )
        self.assertIn(
            "observation_reference_invalid",
            evidence["deterministic_validation"]["reason_codes"],
        )

    def test_unsafe_task_creation_inputs_produce_bounded_shadow_findings(
        self,
    ) -> None:
        negated = self._with_task(
            instruction=(
                "Find the Alpha Launch project but do not create the high-priority "
                "launch checklist task due this week."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_negated",
        )
        invented = self._with_task(
            instruction=(
                "Find the Alpha Launch project and create a high-priority task "
                "for reviewing launch readiness due this week."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Publish secret roadmap",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_invented_content",
        )
        invented_qualifier = self._with_task(
            instruction=(
                "Find the Alpha Launch project and create a task to review "
                "launch readiness with high priority due this week."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Review launch readiness privately",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_invented_qualifier",
        )
        false_binding = self._with_task(
            instruction=(
                "Find the Alpha Launch project and create the high-priority "
                "launch checklist task due this week."
            ),
            expected_task={
                "project_id": "project_beta",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_false_binding",
        )
        rejected_project = self._with_task(
            instruction=(
                "Do not use the Alpha Launch project. Create the high-priority "
                "launch checklist task due this week in the Beta Research project."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_rejected_project",
        )
        conflicting_destination = self._with_task(
            instruction=(
                "Find the Alpha Launch project, then create the high-priority "
                "launch checklist task due this week in the Beta Research project."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_conflicting_destination",
        )
        negated_priority = self._with_task(
            instruction=(
                "Find the Alpha Launch project and create the launch checklist "
                "task due this week, but do not use high priority."
            ),
            expected_task={
                "project_id": "project_alpha",
                "title": "Launch checklist",
                "priority": "high",
                "due_label": "this_week",
            },
            candidate_id="candidate_workspace_task_negated_priority",
        )
        smuggled_record = copy.deepcopy(self._candidate().mutation_authorization)
        assert smuggled_record is not None
        smuggled_record["actions"][0]["arguments"].append(
            {
                "name": "admin_override",
                "origin": "instruction",
                "support": "literal",
                "evidence": smuggled_record["actions"][0][
                    "instruction_evidence"
                ],
            }
        )
        smuggled = replace(
            self._candidate(),
            candidate_id="candidate_workspace_task_parameter_smuggling",
            mutation_authorization=smuggled_record,
        )

        negated_outcome, _ = self._process(negated)
        invented_outcome, _ = self._process(invented)
        invented_qualifier_outcome, _ = self._process(invented_qualifier)
        binding_outcome, _ = self._process(false_binding)
        rejected_project_outcome, _ = self._process(rejected_project)
        conflicting_destination_outcome, _ = self._process(
            conflicting_destination
        )
        negated_priority_outcome, _ = self._process(negated_priority)
        smuggling_outcome, _ = self._process(smuggled)

        for outcome, expected_reason in (
            (negated_outcome, "action_negated"),
            (invented_outcome, "argument_not_supported"),
            (invented_qualifier_outcome, "argument_not_supported"),
        ):
            assert outcome.sample is not None
            verdict = outcome.sample["mutation_admission"]["semantic_verdict"]
            self.assertEqual(verdict["verdict"], "unsupported")
            self.assertIn(expected_reason, verdict["reason_codes"])
        assert negated_priority_outcome.sample is not None
        negated_priority_verdict = negated_priority_outcome.sample[
            "mutation_admission"
        ]["semantic_verdict"]
        self.assertEqual(negated_priority_verdict["verdict"], "unsupported")
        self.assertIn(
            "argument_not_supported",
            negated_priority_verdict["reason_codes"],
        )
        for outcome in (binding_outcome, smuggling_outcome):
            assert outcome.sample is not None
            evidence = outcome.sample["mutation_admission"]
            self.assertEqual(
                evidence["deterministic_validation"]["status"],
                "failed",
            )
            self.assertNotIn("semantic_verdict", evidence)
        self.assertIn(
            "observation_reference_invalid",
            binding_outcome.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        assert rejected_project_outcome.sample is not None
        rejected_project_verdict = rejected_project_outcome.sample[
            "mutation_admission"
        ]["semantic_verdict"]
        self.assertEqual(rejected_project_verdict["verdict"], "unsupported")
        self.assertIn(
            "provenance_mismatch",
            rejected_project_verdict["reason_codes"],
        )
        assert conflicting_destination_outcome.sample is not None
        conflicting_destination_verdict = conflicting_destination_outcome.sample[
            "mutation_admission"
        ]["semantic_verdict"]
        self.assertEqual(
            conflicting_destination_verdict["verdict"],
            "unsupported",
        )
        self.assertIn(
            "provenance_mismatch",
            conflicting_destination_verdict["reason_codes"],
        )
        self.assertIn(
            "authorization_action_mismatch",
            smuggling_outcome.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        self.assertNotIn(
            "admin_override",
            repr(smuggling_outcome.sample["mutation_admission"]),
        )

    def test_paraphrased_workspace_comment_preparation_does_not_regress(
        self,
    ) -> None:
        base = next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id == "candidate_workspace_launch_comment"
        )
        candidate = prepare_workspace_candidate(
            replace(
                base,
                instruction=(
                    "Find the launch plan task and write a comment about its owner."
                ),
                expected_state={
                    "workspace_comment": {
                        "task_id": "task_launch_plan",
                        "comment": "Owner noted.",
                    }
                },
            )
        )

        outcome, environment = self._process(candidate)

        self.assertTrue(
            environment.has_workspace_comment(
                task_id="task_launch_plan",
                comment="Owner noted.",
            )
        )
        self.assertIsNotNone(outcome.sample)

    def test_retained_30_v5_lookup_only_inputs_remain_immutable_shadow_findings(
        self,
    ) -> None:
        fixture_path = Path(
            "tests/fixtures/mutation_admission/workspace-task-creation-30-v5.json"
        )
        retained = json.loads(fixture_path.read_text(encoding="utf-8"))
        historical_path = Path(retained["source_artifact"])
        if historical_path.exists():
            self.assertEqual(
                hashlib.sha256(historical_path.read_bytes()).hexdigest(),
                retained["source_sha256"],
            )

        outcomes = {}
        for sample in retained["samples"]:
            with self.subTest(sample_id=sample["sample_id"]):
                candidate = self._with_task(
                    candidate_id=sample["sample_id"],
                    instruction=sample["instruction"],
                    search_arguments=sample["search_arguments"],
                    expected_task=sample["expected_task"],
                )

                outcome, environment = self._process(candidate)

                self.assertTrue(environment.has_workspace_task(**sample["expected_task"]))
                self.assertIsNotNone(outcome.sample)
                outcomes[sample["sample_id"]] = outcome

        false_binding = outcomes["sample_workspace_tasks_b002_01"]
        assert false_binding.sample is not None
        self.assertIn(
            "observation_reference_invalid",
            false_binding.sample["mutation_admission"][
                "deterministic_validation"
            ]["reason_codes"],
        )
        lookup_only = outcomes["sample_workspace_tasks_b002_02"]
        assert lookup_only.sample is not None
        evidence = lookup_only.sample["mutation_admission"]
        self.assertEqual(
            evidence["deterministic_validation"]["status"],
            "passed",
        )
        self.assertEqual(evidence["semantic_verdict"]["verdict"], "unsupported")
        self.assertIn(
            "action_not_authorized",
            evidence["semantic_verdict"]["reason_codes"],
        )

    def test_shared_admission_kernel_has_no_workspace_task_branches(self) -> None:
        source = inspect.getsource(synthesis.mutation_admission)

        for domain_owned_name in (
            "workspace_tasks_fixture",
            "create_workspace_task",
            "workspace_task_creation",
        ):
            self.assertNotIn(domain_owned_name, source)


class WorkspaceTaskMutationAdmissionPipelineTest(unittest.TestCase):
    def test_shadow_profile_keeps_workspace_outcomes_and_existing_behaviors(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        base_profile = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_task_mutation_admission",
            "dataset_version": "dataset_workspace_task_mutation_admission",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_task_mutation_admission",
                "domain": "workspace_tasks_fixture",
                "description": "Shadow-admit workspace task creation.",
                "task_taxonomy": [
                    "workspace_item_lookup",
                    "workspace_task_creation",
                    "workspace_comment_update",
                    "workspace_branch_fallback",
                ],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {}
            samples = {}

            def generated_without_authorization(seed):
                return [
                    replace(candidate, mutation_authorization=None)
                    for candidate in generate_workspace_fixture_candidates(seed)
                ]

            for mode in ("disabled", "shadow"):
                profile_path = root / f"{mode}.json"
                profile_path.write_text(
                    json.dumps(
                        {
                            **base_profile,
                            "profile_id": f"workspace_task_{mode}",
                            "mutation_admission": {"mode": mode},
                        }
                    ),
                    encoding="utf-8",
                )
                profile = load_run_profile(profile_path)
                results[mode] = run_foundation_pipeline(
                    root / f"output-{mode}",
                    dataset_version=profile.dataset_version,
                    seed_override=profile.seed,
                    run_profile=profile,
                    run_profile_metadata=profile.sanitized_metadata(),
                    candidate_generator=generated_without_authorization,
                )
                samples[mode] = [
                    json.loads(line)
                    for line in results[mode].samples_path.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line
                ]

        self.assertEqual(
            (
                results["disabled"].accepted_count,
                results["disabled"].rejected_count,
            ),
            (
                results["shadow"].accepted_count,
                results["shadow"].rejected_count,
            ),
        )
        shadow_by_id = {
            sample["sample_id"]: sample
            for sample in samples["shadow"]
        }
        for candidate_id in (
            "candidate_workspace_launch_checklist_task",
            "candidate_workspace_launch_comment",
        ):
            evidence = shadow_by_id[f"sample_{candidate_id}"][
                "mutation_admission"
            ]
            self.assertEqual(evidence["admission_outcome"], "judge_supported")
            self.assertEqual(
                evidence["semantic_verdict"]["verdict"],
                "supported",
            )
        read_only = shadow_by_id["sample_candidate_workspace_launch_lookup"][
            "mutation_admission"
        ]
        self.assertEqual(read_only["classification"], "read_only")
        self.assertNotIn("semantic_verdict", read_only)


if __name__ == "__main__":
    unittest.main()
