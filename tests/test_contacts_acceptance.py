from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import httpx


class ContactsAcceptanceProofTest(unittest.TestCase):
    def test_contacts_evidence_is_sanitized_and_freeze_is_qualification_gated(self) -> None:
        from synthesis.contacts_acceptance import (
            ContactsAcceptanceAuthorization,
            ContactsSanitizedProviderEvidenceRecorder,
            sanitize_contacts_provider_response,
        )

        authorization = ContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-provider-freeze-20260830",
            candidate_budget=1,
            attempt_budget=1,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deterministic_contacts_mutation_judge_v1",
        )
        provider = {
            "provider_id": "openai_compatible",
            "provider_version": "openai_compatible_client_v1",
            "provider_host": "llm.example.test",
            "model": "contacts-generator-test-model",
            "config_hash": "sha256:" + "1" * 64,
            "parser_version": "domain_generation_parser_v1",
        }
        judge = {
            "provider": "openai_compatible",
            "provider_host": "llm.example.test",
            "model": "deterministic_contacts_mutation_judge_v1",
            "config_hash": "sha256:" + "2" * 64,
            "role": "mutation_admission_judge",
            "role_version": "role_mutation_admission_judge_v1",
        }
        recorder = ContactsSanitizedProviderEvidenceRecorder(
            authorization=authorization,
            provider_identity=provider,
            mutation_judge_identity=judge,
        )
        response = {
            "task_contracts": [
                {
                    "candidate_id": "contacts_b001_candidate",
                    "instruction": "Find Alice Zhang's email.",
                    "task_type": "contact_lookup",
                    "difficulty": {},
                    "required_capabilities": ["contact_lookup"],
                    "required_tools": ["lookup_contact_email"],
                    "primary_tool": "lookup_contact_email",
                    "primary_arguments": {"name": "Alice Zhang"},
                    "final_answer_contains": "alice.zhang@example.test",
                    "expected_state": [],
                }
            ]
        }
        self.assertEqual(sanitize_contacts_provider_response(response), response)
        with self.assertRaisesRegex(ValueError, "provider_response_not_sanitizable"):
            sanitize_contacts_provider_response(
                {**response, "raw_prompt": "must not be retained"}
            )
        recorder.record_attempt(
            assignment={"assignment_id": "assignment_1"},
            request_hash="sha256:" + "3" * 64,
            response=response,
            response_hash=None,
            outcome="validated",
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        )
        recorder.set_mutation_judge_usage(
            {
                "attempts": 1,
                "attempt_ceiling": 1,
                "tokens": {},
                "outcomes": {"response_received": 1},
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "provider.json"
            with self.assertRaisesRegex(
                ValueError, "real_release_candidate_not_verified"
            ):
                recorder.freeze(
                    output,
                    qualification={
                        "status": "insufficient_evidence",
                        "effective_qualification": "unqualified",
                        "claims": {
                            "publishable": False,
                            "training_recommended": False,
                        },
                    },
                    release_pack_verification={"status": "passed"},
                    release_pack_hash="sha256:" + "4" * 64,
                    run_binding={
                        "profile_id": "contacts_release_candidate",
                        "dataset_version": "dataset_contacts_release_candidate_v1",
                        "seed_id": "seed_contacts_release_candidate_v1",
                        "seed_domain": "contacts_fixture",
                        "plan_id": "contacts_plan",
                        "plan_hash": "sha256:" + "5" * 64,
                        "coverage_plan_id": "contacts_coverage_plan",
                        "coverage_plan_hash": "sha256:" + "6" * 64,
                        "source_policy_hash": "sha256:" + "7" * 64,
                    },
                )
            self.assertFalse(output.exists())

    def test_injected_contacts_acceptance_builds_provider_free_proof(self) -> None:
        from synthesis.contacts_acceptance import (
            ContactsAcceptanceAuthorization,
            run_contacts_acceptance_proof,
            verify_contacts_acceptance_proof,
        )
        from synthesis.llm import LLMConfig
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )
        invalid_first = bool(getattr(self, "_invalid_first_contacts_response", False))

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
            ordinal = assignment["assignment_ordinal"]
            email = observation["email"]
            name = observation["name"]
            if task_type == "contact_followup":
                instruction = (
                    f"Find {name}'s email and record a follow-up to send {email}."
                )
                expected_state = [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": name,
                            "note": f"Send follow-up email to {email}.",
                        },
                    }
                ]
            elif assignment["recovery"] != "none":
                instruction = (
                    f"Try the abbreviated name before finding {name}'s email."
                )
                expected_state = []
            else:
                instruction = f"Find {name}'s email."
                expected_state = []
            primary_arguments = (
                {"name": "Unknown Person"}
                if invalid_first and ordinal == 0
                else grounding["primary_arguments"]
            )
            return response(
                {
                    "task_contracts": [
                        {
                            "candidate_id": (
                                f"{prompt['batch_context']['candidate_id_prefix']}"
                                f"contacts_candidate_{ordinal:02d}"
                            ),
                            "instruction": instruction,
                            "task_type": task_type,
                            "difficulty": {},
                            "required_capabilities": task_spec[
                                "required_capabilities"
                            ],
                            "required_tools": assignment["required_tools"],
                            "primary_tool": assignment["required_tools"][0],
                            "primary_arguments": primary_arguments,
                            "final_answer_contains": email,
                            "expected_state": expected_state,
                        }
                    ]
                }
            )

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
            return response(
                {
                    "schema_version": "semantic_mutation_verdict_v1",
                    "verdict": "supported",
                    "action_findings": [
                        {
                            "action_type": prompt["proposed_mutation"][
                                "action_type"
                            ],
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
                    "evidence_references": list(
                        dict.fromkeys(references.values())
                    ),
                    "input_hash": prompt["input_hash"],
                }
            )

        authorization = ContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-provider-free-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deterministic_contacts_mutation_judge_v1",
            generator_retry_limit=0,
        )
        config = LLMConfig(
            base_url="https://llm.example.test/v1",
            api_key="injected-only",
            model="contacts-generator-test-model",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                httpx.Client(transport=httpx.MockTransport(generator_handler)) as generator_client,
                httpx.Client(transport=httpx.MockTransport(judge_handler)) as judge_client,
            ):
                result = run_contacts_acceptance_proof(
                    root / "acceptance",
                    profile=profile,
                    authorization=authorization,
                    generator_config=config,
                    generator_http_client=generator_client,
                    mutation_judge_http_client=judge_client,
                    proof_root=root / "proof",
                )

            proof_result = verify_contacts_acceptance_proof(result.proof_path)
            proof = json.loads(result.proof_path.read_text(encoding="utf-8"))
            provider = json.loads(
                result.provider_evidence_path.read_text(encoding="utf-8")
            )

        self.assertEqual(result.replay["provider_calls"], 0)
        if invalid_first:
            self.assertGreaterEqual(provider["usage"]["logical_calls"], 6)
            self.assertGreaterEqual(
                sum(item["outcome"] == "rejected" for item in provider["attempts"]),
                1,
            )
            self.assertEqual(result.replay["accepted_attempt_count"], 5)
            self.assertEqual(result.replay["rejected_attempt_count"], 1)
        else:
            self.assertEqual(result.replay["accepted_attempt_count"], 5)
            self.assertEqual(result.replay["rejected_attempt_count"], 0)
        self.assertEqual(result.qualification["effective_qualification"], "release_candidate")
        self.assertEqual(proof_result["status"], "passed")
        self.assertEqual(proof["summary"]["effective_qualification"], "release_candidate")
        self.assertEqual(proof["summary"]["fixture_conformance"], "passed")
        self.assertEqual(proof["summary"]["publishable"], False)
        self.assertEqual(proof["summary"]["training_recommended"], False)
        self.assertEqual(proof["summary"]["global_mutation_activation"], False)
        self.assertEqual(proof["summary"]["mobile_messages"], False)
        self.assertEqual(proof["summary"]["downstream_utility"], False)
        self.assertEqual(
            {case["case_id"] for case in proof_result["proof_cases"]},
            {
                "pack_identity",
                "plan_identity",
                "source_identity",
                "runtime_identity",
                "capability_membership",
                "assignment_membership",
                "mutation_admission",
                "episode_evidence",
                "verifier_identity",
                "coverage_evidence",
                "assessment_evidence",
                "release_pack",
                "qualification_dependency",
            },
        )
        self.assertTrue(
            all(case["status"] == "passed" for case in proof_result["proof_cases"])
        )
        self.assertEqual(proof["non_claims"]["mobile_messages"], False)

    def test_positive_contacts_proof_artifact_drift_fails_closed(self) -> None:
        from synthesis.contacts_acceptance import (
            ContactsAcceptanceAuthorization,
            run_contacts_acceptance_proof,
            verify_contacts_acceptance_proof,
        )
        from synthesis.llm import LLMConfig
        from synthesis.run_profiles import load_run_profile

        # A proof root is intentionally assembled with the same injected
        # contracts as the end-to-end test; the mutation is made only after
        # the immutable root has been written.
        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )
        authorization = ContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-provider-free-drift-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deterministic_contacts_mutation_judge_v1",
        )

        def response(content: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": {},
                },
            )

        def generator(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            assignment = prompt["coverage_assignment"]
            task_spec = prompt["task_types"][0]
            grounding = next(iter(prompt["grounding_context"].values()))[0]
            observation = grounding["observation"]
            task_type = task_spec["task_type"]
            return response(
                {
                    "task_contracts": [
                        {
                            "candidate_id": (
                                prompt["batch_context"]["candidate_id_prefix"]
                                + str(assignment["assignment_ordinal"])
                            ),
                            "instruction": (
                                f"Find {observation['name']}'s email and record a "
                                f"follow-up to send {observation['email']}."
                                if task_type == "contact_followup"
                                else (
                                    f"Try the abbreviated name before finding "
                                    f"{observation['name']}'s email."
                                    if assignment["recovery"] != "none"
                                    else f"Find {observation['name']}'s email."
                                )
                            ),
                            "task_type": task_type,
                            "difficulty": {},
                            "required_capabilities": task_spec[
                                "required_capabilities"
                            ],
                            "required_tools": assignment["required_tools"],
                            "primary_tool": assignment["required_tools"][0],
                            "primary_arguments": grounding["primary_arguments"],
                            "final_answer_contains": observation["email"],
                            "expected_state": (
                                [
                                    {
                                        "check_type": "contact_followup",
                                        "expected": {
                                            "name": observation["name"],
                                            "note": (
                                                "Send follow-up email to "
                                                f"{observation['email']} ."
                                            ).replace(" .", "."),
                                        },
                                    }
                                ]
                                if task_type == "contact_followup"
                                else []
                            ),
                        }
                    ]
                }
            )

        def judge(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            references = prompt["validated_provenance"]["evidence_references"]
            arguments = prompt["proposed_mutation"]["requester_arguments"]
            findings = [
                {
                    "argument": name,
                    "outcome": "supported",
                    "reason_code": "argument_semantic_supported",
                    "evidence_references": [references[name]],
                }
                for name in arguments
            ]
            return response(
                {
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
                    "argument_findings": findings,
                    "reason_codes": list(
                        dict.fromkeys(
                            [
                                "action_authorized",
                                *[
                                    "argument_semantic_supported"
                                    for _ in findings
                                ],
                            ]
                        )
                    ),
                    "evidence_references": list(dict.fromkeys(references.values())),
                    "input_hash": prompt["input_hash"],
                }
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                httpx.Client(transport=httpx.MockTransport(generator)) as generator_client,
                httpx.Client(transport=httpx.MockTransport(judge)) as judge_client,
            ):
                result = run_contacts_acceptance_proof(
                    root / "acceptance",
                    profile=profile,
                    authorization=authorization,
                    generator_config=LLMConfig(
                        base_url="https://llm.example.test/v1",
                        api_key="injected-only",
                        model="contacts-generator-test-model",
                    ),
                    generator_http_client=generator_client,
                    mutation_judge_http_client=judge_client,
                    proof_root=root / "proof",
                )
            plan_path = result.proof_path.parent / "positive" / "trace" / "plan.json"
            plan_path.write_bytes(plan_path.read_bytes() + b"\n")
            verification = verify_contacts_acceptance_proof(result.proof_path)

        self.assertEqual(verification["status"], "failed")
        self.assertEqual(
            verification["reason_codes"], ["contacts_proof_artifact_integrity"]
        )
        return

    def test_contract_valid_but_membership_invalid_response_is_replayed_as_rejection(
        self,
    ) -> None:
        self._invalid_first_contacts_response = True
        try:
            self.test_injected_contacts_acceptance_builds_provider_free_proof()
        finally:
            del self._invalid_first_contacts_response

    def test_missing_acceptance_authorization_writes_no_go_without_provider_evidence(
        self,
    ) -> None:
        from synthesis.contacts_acceptance import (
            ContactsAcceptanceAuthorization,
            ContactsAcceptanceError,
            run_contacts_acceptance_proof,
        )
        from synthesis.llm import LLMConfig
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )
        authorization = ContactsAcceptanceAuthorization(
            approved=False,
            authorization_id="contacts-provider-free-no-go-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deterministic_contacts_mutation_judge_v1",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaisesRegex(
                ContactsAcceptanceError,
                "contacts_provider_free_authorization_required",
            ):
                run_contacts_acceptance_proof(
                    root / "acceptance",
                    profile=profile,
                    authorization=authorization,
                    generator_config=LLMConfig(
                        base_url="https://llm.example.test/v1",
                        api_key="injected-only",
                        model="contacts-generator-test-model",
                    ),
                    generator_http_client=object(),
                    mutation_judge_http_client=object(),
                    proof_root=root / "proof",
                )
            failure = json.loads(
                (root / "acceptance" / "contacts_acceptance_failure.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse((root / "proof" / "contacts_acceptance_proof.json").exists())

        self.assertEqual(failure["status"], "failed")
        self.assertEqual(
            failure["reason_code"], "contacts_provider_free_authorization_required"
        )
        self.assertEqual(failure["generator_usage"]["logical_calls"], 0)
        self.assertFalse(failure["provider_evidence_frozen"])
        self.assertNotIn("injected-only", json.dumps(failure))

    def test_failed_judge_preflight_does_not_call_generator_or_freeze_evidence(
        self,
    ) -> None:
        from synthesis.contacts_acceptance import (
            ContactsAcceptanceAuthorization,
            ContactsAcceptanceError,
            run_contacts_acceptance_proof,
        )
        from synthesis.llm import LLMConfig
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )
        authorization = ContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-provider-free-preflight-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deterministic_contacts_mutation_judge_v1",
        )

        def unavailable_judge(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(503, json={"error": "not available"})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with httpx.Client(
                transport=httpx.MockTransport(unavailable_judge)
            ) as judge_client:
                with self.assertRaisesRegex(
                    ContactsAcceptanceError,
                    "contacts_mutation_judge_preflight_failed",
                ):
                    run_contacts_acceptance_proof(
                        root / "acceptance",
                        profile=profile,
                        authorization=authorization,
                        generator_config=LLMConfig(
                            base_url="https://llm.example.test/v1",
                            api_key="injected-only",
                            model="contacts-generator-test-model",
                        ),
                        generator_http_client=object(),
                        mutation_judge_http_client=judge_client,
                        proof_root=root / "proof",
                    )
            failure = json.loads(
                (root / "acceptance" / "contacts_acceptance_failure.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(
            failure["reason_code"], "contacts_mutation_judge_preflight_failed"
        )
        self.assertEqual(failure["generator_usage"]["logical_calls"], 0)
        self.assertEqual(failure["mutation_judge_usage"]["attempts"], 1)
        self.assertEqual(
            failure["mutation_judge_usage"]["failure_classes"],
            {"http_status": 1},
        )
        self.assertFalse(failure["provider_evidence_frozen"])


if __name__ == "__main__":
    unittest.main()
