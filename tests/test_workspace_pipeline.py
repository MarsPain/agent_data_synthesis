from __future__ import annotations

import json
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from synthesis.execution import ExecutionResult
from synthesis.seeds import DomainSeed


def workspace_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_workspace_tasks_v1",
        domain="workspace_tasks_fixture",
        description="Synthetic workspace projects, tasks, documents, and comments.",
        task_taxonomy=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
    )


class WorkspacePipelineTest(unittest.TestCase):
    def test_workspace_fixture_candidates_cover_expected_task_shapes(self) -> None:
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        candidates = generate_workspace_fixture_candidates(workspace_seed())

        task_types = {candidate.constraints.get("task_type") for candidate in candidates}
        self.assertGreaterEqual(len(candidates), 4)
        self.assertIn("workspace_item_lookup", task_types)
        self.assertIn("workspace_task_creation", task_types)
        self.assertIn("workspace_comment_update", task_types)
        self.assertIn("workspace_branch_fallback", task_types)
        for candidate in candidates:
            self.assertEqual(candidate.constraints["domain"], "workspace_tasks_fixture")
            self.assertIn("task_type", candidate.constraints)

    def test_workspace_release_candidate_fixture_has_release_sample_floor(self) -> None:
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        candidates = generate_workspace_fixture_candidates(workspace_seed())

        self.assertGreaterEqual(len(candidates), 5)
        self.assertTrue(
            {
                "workspace_item_lookup",
                "workspace_task_creation",
                "workspace_comment_update",
                "workspace_branch_fallback",
            }.issubset({candidate.constraints["task_type"] for candidate in candidates})
        )

    def test_workspace_candidates_export_through_candidate_task_contract(self) -> None:
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        allowed_export_keys = {
            "candidate_id",
            "instruction",
            "constraints",
            "difficulty",
            "branch_plan",
        }
        for candidate in generate_workspace_fixture_candidates(workspace_seed()):
            with self.subTest(candidate=candidate.candidate_id):
                contract = candidate.contract()
                exported = candidate.export()

                self.assertEqual(contract.intent.domain_id, "workspace_tasks_fixture")
                self.assertLessEqual(set(exported), allowed_export_keys)
                self.assertNotIn("workspace_expected_state", exported)
                self.assertNotIn("workspace_payload", exported)

    def test_scripted_workspace_policy_uses_only_workspace_tools(self) -> None:
        from synthesis.workspace_tasks import (
            generate_workspace_fixture_candidates,
            scripted_workspace_solution_policy,
        )

        candidates = generate_workspace_fixture_candidates(workspace_seed())
        policies = {
            str(candidate.constraints["task_type"]): scripted_workspace_solution_policy(candidate)
            for candidate in candidates
        }

        self.assertEqual(
            [step.tool_name for step in policies["workspace_item_lookup"].steps],
            ["search_workspace_items"],
        )
        self.assertEqual(
            [step.tool_name for step in policies["workspace_task_creation"].steps],
            ["search_workspace_items", "create_workspace_task"],
        )
        self.assertEqual(
            [step.tool_name for step in policies["workspace_comment_update"].steps],
            ["search_workspace_items", "add_workspace_comment"],
        )
        self.assertIsNotNone(policies["workspace_branch_fallback"].branch_plan)

    def test_workspace_expected_state_declarations_use_contract_checks(self) -> None:
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        check_types: set[str] = set()
        for candidate in generate_workspace_fixture_candidates(workspace_seed()):
            check_types.update(
                state_check.check_type
                for state_check in candidate.contract().expected_state
            )

        self.assertIn("workspace_task", check_types)
        self.assertIn("workspace_comment", check_types)

    def test_workspace_comment_proposes_versioned_authorization_and_provenance(self) -> None:
        from synthesis.mutation_admission import policy_hash
        from synthesis.workspace_tasks import (
            generate_workspace_fixture_candidates,
            scripted_workspace_solution_policy,
        )

        candidate = next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id == "candidate_workspace_launch_comment"
        )
        contract = candidate.contract()
        record = contract.mutation_authorization

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(
            record["schema_version"],
            "mutation_authorization_record_v1",
        )
        self.assertRegex(str(record["instruction_hash"]), r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            record["policy_hash"],
            policy_hash(scripted_workspace_solution_policy(candidate)),
        )
        action = record["actions"][0]
        self.assertEqual(action["action_type"], "workspace_comment_add")
        self.assertEqual(action["action_ref"], "policy.steps.1")
        provenance = {
            argument["name"]: argument
            for argument in action["arguments"]
        }
        self.assertEqual(provenance["comment"]["origin"], "instruction")
        self.assertEqual(provenance["comment"]["support"], "semantic")
        self.assertEqual(provenance["task_id"]["origin"], "tool_observation")
        self.assertEqual(
            provenance["task_id"]["evidence"]["source_action_ref"],
            "policy.steps.0",
        )
        self.assertEqual(
            provenance["task_id"]["evidence"]["source_field"],
            "item_id",
        )
        self.assertRegex(
            str(provenance["task_id"]["evidence"]["value_hash"]),
            r"^sha256:[0-9a-f]{64}$",
        )

    def test_domain_bundle_can_build_workspace_fixture(self) -> None:
        from awm_runtime.runtime import RuntimeSession
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.workspace_environment import WorkspaceTasksEnvironment
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(workspace_seed(), Path(tmpdir))
            session = bundle.runtime_session()

        self.assertEqual(bundle.domain_id, "workspace_tasks_fixture")
        self.assertIsInstance(bundle.environment, WorkspaceTasksEnvironment)
        self.assertEqual(
            bundle.registry.tool_names(),
            [
                "add_workspace_comment",
                "create_workspace_task",
                "search_workspace_items",
            ],
        )
        self.assertEqual(bundle.candidate_generator, generate_workspace_fixture_candidates)
        self.assertEqual(bundle.registry_builder, build_workspace_tool_registry)
        self.assertIsInstance(session, RuntimeSession)
        self.assertEqual(session.runtime_metadata().runtime_id, "workspace_tasks_fixture")

    def test_domain_bundle_can_build_workspace_from_source_input(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.workspace_environment import (
            WorkspaceEnvironmentInput,
            WorkspaceProjectRecord,
            WorkspaceTaskRecord,
        )

        environment_input = WorkspaceEnvironmentInput(
            projects=(WorkspaceProjectRecord("project_custom", "Custom Workspace", "active"),),
            tasks=(
                WorkspaceTaskRecord(
                    "task_custom_plan",
                    "project_custom",
                    "Prepare custom launch plan",
                    "high",
                    "today",
                ),
            ),
            documents=(),
            comments=(),
            source_bundle_id="bundle_source_workspace_tasks_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(
                workspace_seed(),
                Path(tmpdir),
                source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
                domain_environment_input=environment_input,
            )
            result = bundle.environment.search_workspace_items(query="custom", kind="task")

        self.assertEqual(result["item_id"], "task_custom_plan")

    def test_workspace_runtime_descriptor_advertises_domain_capabilities(self) -> None:
        from synthesis.runtime_registry import runtime_descriptor

        descriptor = runtime_descriptor("workspace_tasks_fixture")

        self.assertEqual(descriptor.runtime_id, "workspace_tasks_fixture")
        self.assertEqual(descriptor.domain_id, "workspace_tasks_fixture")
        self.assertTrue(descriptor.supports_episode_replay)
        self.assertTrue(descriptor.supports_reward_labels)
        self.assertTrue(descriptor.supports_local_adapter)
        self.assertEqual(
            descriptor.state_changing_tools,
            ("create_workspace_task", "add_workspace_comment"),
        )
        self.assertIn("workspace_item_lookup", descriptor.task_taxonomy)
        self.assertEqual(
            descriptor.reward_preference_groups["create_workspace_task"],
            "workspace_task_creation",
        )

    def test_workspace_expected_state_reference_grounding_gate(self) -> None:
        from synthesis.domain_generation import (
            DERIVED_FINAL_ANSWER_SENTINEL,
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(workspace_seed(), Path(tmpdir))
        spec = bundle.generation_spec
        context = build_generation_batch_context(spec, batch_index=1)
        record = {
            "candidate_id": "workspace_tasks_b001_comment",
            "instruction": "Find the launch plan task and add a comment.",
            "task_type": "workspace_comment_update",
            "difficulty": {"level": "medium", "tool_count": 2},
            "required_capabilities": ["workspace_search", "workspace_comment_update"],
            "required_tools": ["search_workspace_items", "add_workspace_comment"],
            "primary_tool": "search_workspace_items",
            "primary_arguments": {"query": "launch plan", "kind": "task"},
            "final_answer_contains": DERIVED_FINAL_ANSWER_SENTINEL,
            "expected_state": [
                {
                    "check_type": "workspace_comment",
                    "expected": {
                        "task_id": "task_invented_reference",
                        "comment": "Assign the checklist owner.",
                    },
                }
            ],
        }
        with self.assertRaises(DomainGenerationValidationError) as raised:
            parse_domain_task_contracts(
                {"task_contracts": [record]},
                seed=workspace_seed(),
                spec=spec,
                batch_context=context,
                generation_lineage={},
            )
        self.assertEqual(raised.exception.reason, "invalid_expected_state")
        self.assertEqual(
            raised.exception.detail,
            "expected_state_reference_not_grounded",
        )

    def test_workspace_minting_uses_shared_stable_id_primitive(self) -> None:
        from synthesis.stable_ids import stable_id
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))
            created = environment.create_workspace_task(
                project_id="project_alpha",
                title="Prepare Launch Checklist!",
                priority="high",
                due_label="this_week",
            )
            comment = environment.add_workspace_comment(
                task_id="task_launch_plan",
                comment="Assign Owner: QA Team",
            )

        self.assertEqual(
            created["task_id"],
            f"task_{stable_id('Prepare Launch Checklist!')}",
        )
        self.assertEqual(
            comment["comment_id"],
            f"comment_task_launch_plan_{stable_id('Assign Owner: QA Team')}",
        )

    def test_workspace_expected_state_verification_checks_created_task(self) -> None:
        from synthesis.verification import ExactAnswerVerifier
        from synthesis.workspace_environment import WorkspaceTasksEnvironment
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        candidate = next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id == "candidate_workspace_launch_checklist_task"
        )
        execution = ExecutionResult(
            trajectory=[],
            final_response="Workspace task created: task_prepare_launch_checklist.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))
            failed = ExactAnswerVerifier().verify(candidate, execution, environment=environment)
            environment.create_workspace_task(
                project_id="project_alpha",
                title="Prepare launch checklist",
                priority="high",
                due_label="this_week",
            )
            passed = ExactAnswerVerifier().verify(candidate, execution, environment=environment)

        self.assertFalse(failed.passed)
        self.assertEqual(failed.checks[-1]["name"], "workspace_task_state_matches_expected")
        self.assertEqual(failed.checks[-1]["cause"], "solution_logic_error")
        self.assertTrue(passed.passed)

    def test_workspace_expected_state_verification_checks_added_comment(self) -> None:
        from synthesis.verification import ExactAnswerVerifier
        from synthesis.workspace_environment import WorkspaceTasksEnvironment
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        candidate = next(
            candidate
            for candidate in generate_workspace_fixture_candidates(workspace_seed())
            if candidate.candidate_id == "candidate_workspace_launch_comment"
        )
        execution = ExecutionResult(
            trajectory=[],
            final_response="Workspace comment added for task_launch_plan.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))
            failed = ExactAnswerVerifier().verify(candidate, execution, environment=environment)
            environment.add_workspace_comment(
                task_id="task_launch_plan",
                comment="Added launch checklist owner.",
            )
            passed = ExactAnswerVerifier().verify(candidate, execution, environment=environment)

        self.assertFalse(failed.passed)
        self.assertEqual(
            failed.checks[-1]["name"],
            "workspace_comment_state_matches_expected",
        )
        self.assertEqual(failed.checks[-1]["cause"], "solution_logic_error")
        self.assertTrue(passed.passed)

    def test_workspace_run_profiles_preserve_outcomes_and_emit_disabled_or_shadow_evidence(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        results: dict[
            str,
            tuple[object, list[dict[str, object]], dict[str, object]],
        ] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for mode in ("disabled", "shadow"):
                profile = load_run_profile(
                    Path(f"tests/fixtures/run_profiles/workspace-comments-{mode}.json")
                )
                result = run_foundation_pipeline(
                    root / mode,
                    dataset_version=profile.dataset_version,
                    seed_override=profile.seed,
                    run_profile=profile,
                    run_profile_metadata=profile.sanitized_metadata(),
                )
                samples = [
                    json.loads(line)
                    for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                    if line
                ]
                manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
                results[mode] = (result, samples, manifest)

        disabled_result, disabled_samples, disabled_manifest = results["disabled"]
        shadow_result, shadow_samples, shadow_manifest = results["shadow"]
        self.assertEqual(
            (disabled_result.accepted_count, disabled_result.rejected_count),
            (shadow_result.accepted_count, shadow_result.rejected_count),
        )
        self.assertEqual(
            disabled_manifest["sample_contract_versions"],
            ["dataset_sample_v2"],
        )
        self.assertEqual(
            shadow_manifest["sample_contract_versions"],
            ["dataset_sample_v2"],
        )
        for mode, samples in (
            ("disabled", disabled_samples),
            ("shadow", shadow_samples),
        ):
            comment = next(
                sample
                for sample in samples
                if sample["sample_id"] == "sample_candidate_workspace_launch_comment"
            )
            evidence = comment["mutation_admission"]
            self.assertEqual(comment["schema_version"], "dataset_sample_v2")
            self.assertEqual(evidence["mode"], mode)
            if mode == "shadow":
                self.assertEqual(evidence["semantic_verdict"]["verdict"], "supported")
            else:
                self.assertNotIn("semantic_verdict", evidence)

            lookup = next(
                sample
                for sample in samples
                if sample["sample_id"] == "sample_candidate_workspace_launch_lookup"
            )
            self.assertEqual(
                lookup["mutation_admission"]["classification"],
                "read_only",
            )

    def test_remote_shadow_and_enforce_profiles_audit_model_independence(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            judge_input = json.loads(payload["messages"][1]["content"])
            mutation = judge_input["proposed_mutation"]
            provenance = judge_input["validated_provenance"]
            references = provenance["evidence_references"]
            verdict = {
                "schema_version": "semantic_mutation_verdict_v1",
                "verdict": "supported",
                "action_findings": [
                    {
                        "action_type": mutation["action_type"],
                        "outcome": "supported",
                        "reason_code": "action_authorized",
                        "evidence_references": [references["action"]],
                    }
                ],
                "argument_findings": [
                    {
                        "argument": name,
                        "outcome": "supported",
                        "reason_code": (
                            "observation_reference_supported"
                            if origin == "tool_observation"
                            else "argument_semantic_supported"
                        ),
                        "evidence_references": [references[name]],
                    }
                    for name, origin in provenance["argument_origins"].items()
                ],
                "reason_codes": [
                    "action_authorized",
                    "argument_semantic_supported",
                    "observation_reference_supported",
                ],
                "evidence_references": list(references.values()),
                "input_hash": judge_input["input_hash"],
            }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(verdict)}}],
                    "usage": {},
                },
            )

        base_profile = {
            "schema_version": "run_profile_v4",
            "dataset_version": "dataset_workspace_remote_shadow",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_remote_shadow",
                "domain": "workspace_tasks_fixture",
                "description": "Audit independent semantic mutation judgment.",
                "task_taxonomy": [
                    "workspace_item_lookup",
                    "workspace_comment_update",
                ],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }
        env = {
            "AGENT_DATA_LLM_BASE_URL": "https://judge.example.test/v1",
            "AGENT_DATA_API_KEY": "secret-test-key",
            "AGENT_DATA_LLM_MODEL": "task-generator-model",
        }

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            root = Path(tmpdir)
            for label, mode, expected_status, judge_model in (
                (
                    "shadow_independent",
                    "shadow",
                    "independent",
                    "independent-judge-model",
                ),
                ("shadow_same_model", "shadow", "same_model", "scripted"),
                (
                    "enforce_independent",
                    "enforce",
                    "independent",
                    "independent-judge-model",
                ),
            ):
                with self.subTest(label=label):
                    mapping = {
                        **base_profile,
                        "profile_id": f"workspace_remote_{label}",
                        "mutation_admission": {
                            "mode": mode,
                            "judge": {
                                "role": "mutation_admission_judge",
                                "provider": "openai_compatible",
                                "model": judge_model,
                                "timeout_seconds": 7.0,
                                "max_retries": 1,
                            },
                        },
                    }
                    profile_path = root / f"{label}.json"
                    profile_path.write_text(json.dumps(mapping), encoding="utf-8")
                    profile = load_run_profile(profile_path)
                    result = run_foundation_pipeline(
                        root / f"output-{label}",
                        dataset_version=profile.dataset_version,
                        seed_override=profile.seed,
                        run_profile=profile,
                        run_profile_metadata=profile.sanitized_metadata(),
                        mutation_judge_http_client=httpx.Client(
                            transport=httpx.MockTransport(handler)
                        ),
                    )
                    samples = [
                        json.loads(line)
                        for line in result.samples_path.read_text(
                            encoding="utf-8"
                        ).splitlines()
                        if line
                    ]
                    comment = next(
                        sample
                        for sample in samples
                        if sample["sample_id"]
                        == "sample_candidate_workspace_launch_comment"
                    )
                    evidence = comment["mutation_admission"]
                    self.assertEqual(
                        evidence["model_independence"],
                        expected_status,
                    )
                    self.assertEqual(evidence["lineage"]["judge"]["model"], judge_model)
                    self.assertEqual(
                        evidence["diagnostic_only"],
                        mode == "shadow",
                    )
                    self.assertNotIn("secret-test-key", json.dumps(evidence))

    def test_remote_enforce_profile_fails_closed_on_provider_retry_exhaustion(
        self,
    ) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            raise httpx.ReadTimeout("raw provider timeout", request=request)

        profile_mapping = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_remote_enforce_failure",
            "dataset_version": "dataset_workspace_remote_enforce_failure",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_remote_enforce_failure",
                "domain": "workspace_tasks_fixture",
                "description": "Fail closed when the independent judge is unavailable.",
                "task_taxonomy": [
                    "workspace_item_lookup",
                    "workspace_comment_update",
                ],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
            "mutation_admission": {
                "mode": "enforce",
                "judge": {
                    "role": "mutation_admission_judge",
                    "provider": "openai_compatible",
                    "model": "independent-judge-model",
                    "timeout_seconds": 3.0,
                    "max_retries": 1,
                },
            },
        }
        env = {
            "AGENT_DATA_LLM_BASE_URL": "https://judge.example.test/v1",
            "AGENT_DATA_API_KEY": "secret-test-key",
            "AGENT_DATA_LLM_MODEL": "task-generator-model",
        }

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            root = Path(tmpdir)
            profile_path = root / "enforce.json"
            profile_path.write_text(
                json.dumps(profile_mapping),
                encoding="utf-8",
            )
            profile = load_run_profile(profile_path)
            result = run_foundation_pipeline(
                root / "output",
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile=profile,
                run_profile_metadata=profile.sanitized_metadata(),
                mutation_judge_http_client=httpx.Client(
                    transport=httpx.MockTransport(handler)
                ),
            )
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line
            ]

        admission_rejections = [
            rejection
            for rejection in rejections
            if rejection["cause"] == "mutation_admission_failed"
        ]
        self.assertGreater(request_count, 0)
        self.assertTrue(admission_rejections)
        self.assertTrue(
            all(
                rejection["details"]["admission_reason"] == "judge_unavailable"
                and rejection["details"]["mutation_admission"]["judge_call"]
                == {
                    "outcome": "unavailable",
                    "attempts": 2,
                    "timeout_seconds": 3.0,
                }
                for rejection in admission_rejections
            )
        )
        self.assertTrue(
            all(
                sample["mutation_admission"]["classification"] == "read_only"
                for sample in samples
            )
        )
        retained = json.dumps(admission_rejections, sort_keys=True)
        self.assertNotIn("raw provider timeout", retained)
        self.assertNotIn("secret-test-key", retained)


if __name__ == "__main__":
    unittest.main()
