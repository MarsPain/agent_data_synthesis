from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx


class WorkspaceLiveAcceptanceContractTest(unittest.TestCase):
    def _authorization(self, *, approved: bool = True):
        from synthesis.workspace_live_acceptance import (
            LiveWorkspaceAcceptanceAuthorization,
        )

        return LiveWorkspaceAcceptanceAuthorization(
            approved=approved,
            authorization_id="workspace-acceptance-test-20260822",
            candidate_budget=12,
            attempt_budget=24,
            generator_provider="openai_compatible",
            generator_model="generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="independent-judge-test-model",
        )

    def test_unapproved_authorization_fails_closed(self) -> None:
        from synthesis.workspace_live_acceptance import (
            LiveWorkspaceAcceptanceError,
        )

        with self.assertRaisesRegex(
            LiveWorkspaceAcceptanceError,
            "live_provider_authorization_required",
        ):
            self._authorization(approved=False).validate(
                profile={
                    "schema_version": "run_profile_v4",
                    "profile_purpose": "release_candidate",
                    "generation": {"mode": "llm", "target_candidate_count": 12},
                    "seed": {"domain": "workspace_tasks_fixture"},
                    "coverage_profile": {},
                    "mutation_admission": {
                        "mode": "enforce",
                        "judge": {
                            "provider": "openai_compatible",
                            "model": "independent-judge-test-model",
                        },
                    },
                },
                plan_attempt_ceiling=24,
            )

    def test_sanitizer_keeps_contract_response_but_never_prompt_or_credentials(
        self,
    ) -> None:
        from synthesis.workspace_live_acceptance import sanitize_provider_response

        response = {
            "task_contracts": [
                {
                    "candidate_id": "workspace_tasks_b001_offline_candidate",
                    "instruction": "Find the Alpha Launch project.",
                    "task_type": "workspace_item_search",
                    "difficulty": {},
                    "required_capabilities": ["item_search"],
                    "required_tools": ["search_workspace_items"],
                    "primary_tool": "search_workspace_items",
                    "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
                    "final_answer_contains": "project_alpha",
                    "expected_state": [],
                }
            ]
        }

        sanitized = sanitize_provider_response(response)

        self.assertEqual(sanitized, response)
        serialized = json.dumps(sanitized, sort_keys=True)
        self.assertNotIn("prompt", serialized.lower())
        self.assertNotIn("authorization", serialized.lower())
        self.assertNotIn("api_key", serialized.lower())

        with self.assertRaisesRegex(ValueError, "provider_response_not_sanitizable"):
            sanitize_provider_response(
                {
                    **response,
                    "raw_prompt": "do not persist this",
                }
            )

    def test_freeze_requires_independent_release_candidate_verification(self) -> None:
        from synthesis.workspace_live_acceptance import (
            LiveWorkspaceAcceptanceError,
            SanitizedProviderEvidenceRecorder,
        )

        recorder = SanitizedProviderEvidenceRecorder(
            authorization=self._authorization(),
            provider_identity={
                "provider_id": "openai_compatible",
                "provider_version": "openai_compatible_client_v1",
                "provider_host": "llm.example.test",
                "model": "generator-test-model",
                "config_hash": "sha256:" + "1" * 64,
                "parser_version": "domain_generation_parser_v1",
            },
            mutation_judge_identity={
                "provider": "openai_compatible",
                "model": "independent-judge-test-model",
                "role": "mutation_admission_judge",
            },
        )
        recorder.record_attempt(
            assignment={"assignment_id": "assignment_1"},
            request_hash="sha256:" + "2" * 64,
            response={"task_contracts": []},
            response_hash=None,
            outcome="validated",
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "provider.json"
            with self.assertRaisesRegex(
                LiveWorkspaceAcceptanceError,
                "real_release_candidate_not_verified",
            ):
                recorder.freeze(
                    output,
                    qualification={
                        "status": "insufficient_evidence",
                        "effective_qualification": "unqualified",
                    },
                    release_pack_verification={"status": "passed"},
                    release_pack_hash="sha256:" + "4" * 64,
                )
            self.assertFalse(output.exists())

    def test_freeze_records_only_replayable_sanitized_attempts(self) -> None:
        from synthesis.workspace_live_acceptance import (
            SanitizedProviderEvidenceRecorder,
        )

        recorder = SanitizedProviderEvidenceRecorder(
            authorization=self._authorization(),
            provider_identity={
                "provider_id": "openai_compatible",
                "provider_version": "openai_compatible_client_v1",
                "provider_host": "llm.example.test",
                "model": "generator-test-model",
                "config_hash": "sha256:" + "1" * 64,
                "parser_version": "domain_generation_parser_v1",
            },
            mutation_judge_identity={
                "provider": "openai_compatible",
                "model": "independent-judge-test-model",
                "role": "mutation_admission_judge",
            },
        )
        recorder.record_attempt(
            assignment={"assignment_id": "assignment_1"},
            request_hash="sha256:" + "2" * 64,
            response={
                "task_contracts": [
                    {
                        "candidate_id": "workspace_tasks_b001_candidate",
                        "instruction": "Find Alpha Launch.",
                        "task_type": "workspace_item_search",
                        "difficulty": {},
                        "required_capabilities": ["item_search"],
                        "required_tools": ["search_workspace_items"],
                        "primary_tool": "search_workspace_items",
                        "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
                        "final_answer_contains": "project_alpha",
                        "expected_state": [],
                    }
                ]
            },
            response_hash=None,
            outcome="validated",
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        )
        recorder.record_attempt(
            assignment={"assignment_id": "assignment_2"},
            request_hash="sha256:" + "5" * 64,
            response=None,
            response_hash=None,
            outcome="provider_error",
            reason_code="llm_provider_error",
            usage={},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "provider.json"
            result = recorder.freeze(
                output,
                qualification={
                    "status": "passed",
                    "effective_qualification": "release_candidate",
                    "claims": {
                        "publishable": False,
                        "training_recommended": False,
                    },
                },
                release_pack_verification={"status": "passed"},
                release_pack_hash="sha256:" + "4" * 64,
                run_binding={
                    "profile_id": "workspace_tasks_live_acceptance_rc",
                    "dataset_version": "dataset_workspace_tasks_live_acceptance_rc_v1",
                    "seed_id": "seed_workspace_tasks_live_acceptance_rc_v1",
                    "seed_domain": "workspace_tasks_fixture",
                    "plan_id": "workspace_plan",
                    "plan_hash": "sha256:" + "5" * 64,
                    "coverage_plan_id": "coverage_plan",
                    "coverage_plan_hash": "sha256:" + "6" * 64,
                    "source_policy_hash": "sha256:" + "7" * 64,
                },
            )
            evidence = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result["evidence_class"], "real_live")
        self.assertEqual(len(evidence["attempts"]), 2)
        self.assertEqual(len(evidence["replay_attempts"]), 1)
        self.assertNotIn("raw_prompt", json.dumps(evidence).lower())
        self.assertNotIn("raw_payload", json.dumps(evidence).lower())
        self.assertNotIn("api_key", json.dumps(evidence).lower())
        self.assertTrue(evidence["frozen"])

    def test_injected_provider_transport_builds_real_live_replay_proof(self) -> None:
        from synthesis.llm import LLMConfig
        from synthesis.run_profiles import load_run_profile
        from synthesis.workspace_live_acceptance import (
            LiveWorkspaceAcceptanceAuthorization,
            run_live_workspace_acceptance,
        )

        profile = load_run_profile(
            Path(__file__).parent
            / "fixtures"
            / "run_profiles"
            / "workspace-tasks-live-acceptance.json"
        )
        config = LLMConfig(
            base_url="https://llm.example.test/v1",
            api_key="test-key",
            model="generator-test-model",
        )

        def response(content: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(content)}}
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 11,
                        "total_tokens": 18,
                    },
                },
            )

        def generator_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            assignment = prompt["coverage_assignment"]
            task_spec = prompt["task_types"][0]
            grounding = next(iter(prompt["grounding_context"].values()))[0]
            observation = grounding["observation"]
            task_type = task_spec["task_type"]
            assignment_ordinal = assignment["assignment_ordinal"]
            sample_label = f"coverage sample {assignment_ordinal:02d}"
            expected_state = []
            if task_type == "workspace_task_creation":
                project_id = observation["project_id"]
                project_name = observation["summary"].split(" (", 1)[0]
                task_title = f"Prepare launch checklist {assignment_ordinal:02d}"
                instruction = (
                    f"Find the {project_name} project and create a high-priority task "
                    f"titled {task_title} due this week ({sample_label})."
                )
                expected_state = [
                    {
                        "check_type": "workspace_task",
                        "expected": {
                            "project_id": project_id,
                            "title": task_title,
                            "priority": "high",
                            "due_label": "this_week",
                        },
                    }
                ]
                final_answer = "$derived_from_expected_state$"
            elif task_type == "workspace_comment_update":
                task_id = observation["item_id"]
                summary = observation["summary"]
                comment = f"Added launch checklist owner ({sample_label})."
                instruction = (
                    f"Find the {summary} task and add a comment assigning the "
                    f"checklist owner ({sample_label})."
                )
                expected_state = [
                    {
                        "check_type": "workspace_comment",
                        "expected": {"task_id": task_id, "comment": comment},
                    }
                ]
                final_answer = "$derived_from_expected_state$"
            else:
                summary = observation["summary"]
                if assignment.get("recovery") != "none":
                    instruction = (
                        "Find the checklist owner note in workspace comments after "
                        f"the direct task lookup fails ({sample_label})."
                    )
                else:
                    instruction = (
                        f"Find the workspace item described as {summary} "
                        f"({sample_label})."
                    )
                final_answer = observation["item_id"]
            contract = {
                "candidate_id": (
                    prompt["batch_context"]["candidate_id_prefix"]
                    + "injected_candidate"
                ),
                "instruction": instruction,
                "task_type": task_type,
                "difficulty": {},
                "required_capabilities": task_spec["required_capabilities"],
                "required_tools": task_spec["required_tools"],
                "primary_tool": task_spec["required_tools"][0],
                "primary_arguments": grounding["primary_arguments"],
                "final_answer_contains": final_answer,
                "expected_state": expected_state,
            }
            return response({"task_contracts": [contract]})

        def judge_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            references = prompt["validated_provenance"]["evidence_references"]
            arguments = prompt["proposed_mutation"]["requester_arguments"]
            argument_findings = [
                {
                    "argument": name,
                    "outcome": "supported",
                    "reason_code": "argument_semantic_supported",
                    "evidence_references": [references[name]],
                }
                for name in arguments
            ]
            verdict = {
                "schema_version": "semantic_mutation_verdict_v1",
                "verdict": "supported",
                "action_findings": [
                    {
                        "action_type": prompt["proposed_mutation"]["action_type"],
                        "outcome": "supported",
                        "reason_code": "action_authorized",
                        "evidence_references": [references["action"]],
                    }
                ],
                "argument_findings": argument_findings,
                "reason_codes": list(
                    dict.fromkeys(
                        ["action_authorized"]
                        + [
                            "argument_semantic_supported"
                            for _ in argument_findings
                        ]
                    )
                ),
                "evidence_references": list(dict.fromkeys(references.values())),
                "input_hash": prompt["input_hash"],
            }
            return response(verdict)

        authorization = LiveWorkspaceAcceptanceAuthorization(
            approved=True,
            authorization_id="workspace-acceptance-injected-20260822",
            candidate_budget=24,
            attempt_budget=24,
            generator_provider="openai_compatible",
            generator_model="generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="workspace-independent-mutation-judge",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                httpx.Client(
                    transport=httpx.MockTransport(generator_handler)
                ) as generator_client,
                httpx.Client(
                    transport=httpx.MockTransport(judge_handler)
                ) as judge_client,
            ):
                result = run_live_workspace_acceptance(
                    root / "acceptance",
                    profile=profile,
                    authorization=authorization,
                    generator_config=config,
                    generator_http_client=generator_client,
                    mutation_judge_http_client=judge_client,
                    proof_root=root / "proof",
                )
            provider = json.loads(
                result.provider_evidence_path.read_text(encoding="utf-8")
            )
            proof = json.loads(result.proof_path.read_text(encoding="utf-8"))

        self.assertEqual(result.replay["provider_calls"], 0)
        self.assertEqual(provider["evidence_class"], "real_live")
        self.assertEqual(provider["usage"]["replayable_calls"], 12)
        self.assertEqual(proof["subject"]["evidence_class"], "real_live")
        serialized = json.dumps(provider, sort_keys=True).lower()
        self.assertNotIn("raw_prompt", serialized)
        self.assertNotIn("api_key", serialized)


if __name__ == "__main__":
    unittest.main()
