from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


class ContactsLiveAcceptanceContractTest(unittest.TestCase):
    @staticmethod
    def _profile():
        from synthesis.run_profiles import load_run_profile

        return load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )

    @staticmethod
    def _config():
        from synthesis.llm import LLMConfig

        return LLMConfig(
            base_url="https://llm.example.test/v1",
            api_key="injected-only",
            model="contacts-generator-test-model",
        )

    def test_live_profile_uses_default_remote_judge_policy(self) -> None:
        from synthesis.contacts_live_acceptance import (
            DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS,
            DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES,
            DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
            DEFAULT_CONTACTS_MUTATION_JUDGE_THINKING_MODE,
            DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS,
            LiveContactsAcceptanceAuthorization,
        )

        judge = self._profile().mutation_admission.judge
        assert judge is not None
        self.assertEqual(judge.model, DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL)
        self.assertEqual(
            judge.timeout_seconds,
            DEFAULT_CONTACTS_MUTATION_JUDGE_TIMEOUT_SECONDS,
        )
        self.assertEqual(judge.max_retries, DEFAULT_CONTACTS_MUTATION_JUDGE_MAX_RETRIES)
        self.assertEqual(
            judge.thinking_mode,
            DEFAULT_CONTACTS_MUTATION_JUDGE_THINKING_MODE,
        )
        self.assertEqual(
            LiveContactsAcceptanceAuthorization(
                approved=True,
                authorization_id="contacts-live-default-timeout-20260904",
                candidate_budget=10,
                attempt_budget=10,
                generator_provider="openai_compatible",
                generator_model="contacts-generator-test-model",
                mutation_judge_provider="openai_compatible",
                mutation_judge_model=DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
            ).generator_timeout_seconds,
            DEFAULT_CONTACTS_GENERATOR_TIMEOUT_SECONDS,
        )

    def test_unapproved_authorization_fails_closed_before_transport_work(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
        )

        authorization = LiveContactsAcceptanceAuthorization(
            approved=False,
            authorization_id="contacts-live-test-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="contacts-judge-test-model",
        )

        with self.assertRaisesRegex(
            LiveContactsAcceptanceError,
            "contacts_live_provider_authorization_required",
        ):
            authorization.validate(
                profile={
                    "schema_version": "run_profile_v4",
                    "profile_id": "contacts_release_candidate",
                    "dataset_version": "dataset_contacts_release_candidate_v1",
                    "profile_purpose": "release_candidate",
                    "generation": {
                        "mode": "foundation_fixture",
                        "target_candidate_count": 10,
                    },
                    "seed": {
                        "domain": "contacts_fixture",
                        "seed_id": "seed_contacts_release_candidate_v1",
                        "task_taxonomy": [
                            "contact_lookup",
                            "contact_followup",
                            "contact_lookup_recovery",
                        ],
                    },
                    "coverage_profile": {
                        "profile_id": "contacts_representative",
                        "version": "contacts_representative_v1",
                        "target_accepted_sample_count": 5,
                    },
                    "features": {"enable_branching": True},
                    "mutation_admission": {
                        "mode": "enforce",
                        "judge": {
                            "provider": "openai_compatible",
                            "role": "mutation_admission_judge",
                            "model": "contacts-judge-test-model",
                        },
                    },
                },
                plan_attempt_ceiling=10,
            )

    def test_authorization_rejects_non_exact_contacts_profile_features(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
        )

        profile = self._profile().canonical()
        profile["features"] = {
            **profile["features"],
            "enable_task_expansion": True,
        }
        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-profile-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )

        with self.assertRaisesRegex(
            LiveContactsAcceptanceError,
            "contacts_live_release_profile_invalid",
        ):
            authorization.validate(profile=profile, plan_attempt_ceiling=10)

    def test_authorization_rejects_unknown_contacts_profile_fields(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
        )

        profile = self._profile().canonical()
        profile["features"] = {
            **profile["features"],
            "enable_unreviewed_feature": False,
        }
        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-profile-fields-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )

        with self.assertRaisesRegex(
            LiveContactsAcceptanceError,
            "contacts_live_release_profile_invalid",
        ):
            authorization.validate(profile=profile, plan_attempt_ceiling=10)

    def test_failed_preflight_writes_bounded_failure_before_generation(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
            run_live_contacts_acceptance,
        )

        generator_calls: list[httpx.Request] = []

        def unexpected_generator(request: httpx.Request) -> httpx.Response:
            generator_calls.append(request)
            raise AssertionError("generation must not follow a failed preflight")

        judge_requests: list[dict[str, object]] = []

        def unavailable_judge(request: httpx.Request) -> httpx.Response:
            judge_requests.append(json.loads(request.read()))
            return httpx.Response(503, json={"error": "unavailable"})

        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-preflight-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                httpx.Client(
                    transport=httpx.MockTransport(unexpected_generator)
                ) as generator_client,
                httpx.Client(
                    transport=httpx.MockTransport(unavailable_judge)
                ) as judge_client,
            ):
                with self.assertRaisesRegex(
                    LiveContactsAcceptanceError,
                    "contacts_live_mutation_judge_preflight_failed",
                ):
                    run_live_contacts_acceptance(
                        root / "acceptance",
                        profile=self._profile(),
                        authorization=authorization,
                        generator_config=self._config(),
                        generator_http_client=generator_client,
                        mutation_judge_http_client=judge_client,
                        proof_root=root / "proof",
                    )
            failure = json.loads(
                (
                    root
                    / "acceptance"
                    / "contacts_live_attempt_failure.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(generator_calls, [])
        self.assertEqual(failure["reason_code"], "contacts_live_mutation_judge_preflight_failed")
        self.assertEqual(failure["generator_usage"]["logical_calls"], 0)
        self.assertEqual(failure["mutation_judge_usage"]["attempts"], 1)
        self.assertEqual(
            failure["mutation_judge_usage"]["failure_classes"],
            {"http_status": 1},
        )
        self.assertEqual(judge_requests[0]["model"], "deepseek-v4-pro")
        self.assertEqual(judge_requests[0]["thinking"], {"type": "disabled"})
        serialized = json.dumps(failure).lower()
        self.assertNotIn("injected-only", serialized)
        self.assertNotIn("response", serialized)
        self.assertFalse((root / "proof").exists())

    def test_injected_live_contacts_run_builds_real_live_proof_and_replays_offline(
        self,
    ) -> None:
        from synthesis.contacts_live_acceptance import (
            run_live_contacts_acceptance,
            verify_live_contacts_acceptance_proof,
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
            timeout = request.extensions.get("timeout")
            assert isinstance(timeout, dict)
            self.assertEqual(set(timeout.values()), {90.0})
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            assignment = prompt["coverage_assignment"]
            task_spec = prompt["task_types"][0]
            grounding = next(iter(prompt["grounding_context"].values()))[0]
            observation = grounding["observation"]
            task_type = task_spec["task_type"]
            ordinal = assignment["assignment_ordinal"]
            name = observation["name"]
            email = observation["email"]
            if task_type == "contact_followup":
                instruction = (
                    f"Find {name}'s email."
                    if getattr(self, "_unsupported_followup_instruction", False)
                    else f"Find {name}'s email and record a follow-up to send {email}."
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
                instruction = f"Try the abbreviated name before finding {name}'s email."
                expected_state = []
            else:
                instruction = f"Find {name}'s email."
                expected_state = []
            return response(
                {
                    "task_contracts": [
                        {
                            "candidate_id": (
                                f"{prompt['batch_context']['candidate_id_prefix']}"
                                f"contacts_live_candidate_{ordinal:02d}"
                            ),
                            "instruction": instruction,
                            "task_type": task_type,
                            "difficulty": {},
                            "required_capabilities": task_spec[
                                "required_capabilities"
                            ],
                            "required_tools": assignment["required_tools"],
                            "primary_tool": assignment["required_tools"][0],
                            "primary_arguments": grounding["primary_arguments"],
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
                            "action_type": prompt["proposed_mutation"][
                                "action_type"
                            ],
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
                    "evidence_references": list(
                        dict.fromkeys(references.values())
                    ),
                    "input_hash": prompt["input_hash"],
                }
            )

        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
        )

        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-injected-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
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
                result = run_live_contacts_acceptance(
                    root / "acceptance",
                    profile=self._profile(),
                    authorization=authorization,
                    generator_config=self._config(),
                    generator_http_client=generator_client,
                    mutation_judge_http_client=judge_client,
                    proof_root=root / "proof",
                )
            provider = json.loads(
                result.provider_evidence_path.read_text(encoding="utf-8")
            )
            proof = json.loads(result.proof_path.read_text(encoding="utf-8"))
            offline_verification = verify_live_contacts_acceptance_proof(
                result.proof_path
            )
            from scripts.verify_contacts_acceptance_proof import main as verify_main

            with patch.object(
                sys,
                "argv",
                [
                    "verify_contacts_acceptance_proof.py",
                    str(result.proof_path),
                    "--real-live",
                ],
            ):
                offline_cli_status = verify_main()

        self.assertEqual(result.replay["provider_calls"], 0)
        self.assertEqual(result.replay["accepted_attempt_count"], 5)
        self.assertEqual(result.replay["rejected_attempt_count"], 0)
        self.assertEqual(offline_verification["status"], "passed")
        self.assertEqual(offline_cli_status, 0)
        self.assertEqual(result.qualification["effective_qualification"], "release_candidate")
        self.assertEqual(provider["evidence_class"], "real_live")
        self.assertEqual(provider["usage"]["replayable_calls"], 5)
        self.assertEqual(proof["subject"]["evidence_class"], "real_live")
        serialized = json.dumps(provider, sort_keys=True).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("raw_prompt", serialized)
        self.assertNotIn("provider_payload", serialized)

    def test_replay_uses_frozen_remote_admission_decision(
        self,
    ) -> None:
        self._unsupported_followup_instruction = True
        try:
            self.test_injected_live_contacts_run_builds_real_live_proof_and_replays_offline()
        finally:
            del self._unsupported_followup_instruction

    def test_frozen_live_evidence_rejects_logical_or_retry_budget_drift(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            SanitizedProviderEvidenceRecorder,
            validate_live_provider_evidence,
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
            "model": "deepseek-v4-pro",
            "config_hash": "sha256:" + "2" * 64,
            "role": "mutation_admission_judge",
            "role_version": "role_mutation_admission_judge_v1",
        }
        run_binding = {
            "profile_id": "contacts_release_candidate",
            "dataset_version": "dataset_contacts_release_candidate_v1",
            "seed_id": "seed_contacts_release_candidate_v1",
            "seed_domain": "contacts_fixture",
            "plan_id": "contacts_plan",
            "plan_hash": "sha256:" + "3" * 64,
            "coverage_plan_id": "contacts_coverage_plan",
            "coverage_plan_hash": "sha256:" + "4" * 64,
            "source_policy_hash": "sha256:" + "5" * 64,
        }

        def freeze_evidence(
            *, attempt_budget: int, retry_limit: int, attempts: list[dict[str, object]]
        ) -> dict[str, object]:
            authorization = LiveContactsAcceptanceAuthorization(
                approved=True,
                authorization_id="contacts-live-budget-drift-20260830",
                candidate_budget=attempt_budget,
                attempt_budget=attempt_budget,
                generator_provider="openai_compatible",
                generator_model="contacts-generator-test-model",
                mutation_judge_provider="openai_compatible",
                mutation_judge_model="deepseek-v4-pro",
                generator_retry_limit=retry_limit,
            )
            recorder = SanitizedProviderEvidenceRecorder(
                authorization=authorization,
                provider_identity=provider,
                mutation_judge_identity=judge,
            )
            for attempt in attempts:
                recorder.record_attempt(
                    assignment={"assignment_id": attempt["assignment_id"]},
                    request_hash=attempt["request_hash"],
                    response={"task_contracts": []},
                    response_hash=None,
                    outcome="validated",
                    usage={},
                    retry_count=attempt["retry_count"],
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
                return recorder.freeze(
                    Path(tmpdir) / "provider.json",
                    qualification={
                        "status": "passed",
                        "effective_qualification": "release_candidate",
                        "claims": {
                            "publishable": False,
                            "training_recommended": False,
                        },
                    },
                    release_pack_verification={"status": "passed"},
                    release_pack_hash="sha256:" + "6" * 64,
                    run_binding=run_binding,
                )

        with self.subTest(boundary="per_attempt_retry_limit"):
            evidence = freeze_evidence(
                attempt_budget=1,
                retry_limit=0,
                attempts=[
                    {
                        "assignment_id": "assignment_1",
                        "request_hash": "sha256:" + "7" * 64,
                        "retry_count": 0,
                    }
                ],
            )
            evidence["attempts"][0]["retry_count"] = 1
            with self.assertRaisesRegex(ValueError, "live_usage_malformed"):
                validate_live_provider_evidence(evidence)

        with self.subTest(boundary="logical_call_budget"):
            evidence = freeze_evidence(
                attempt_budget=2,
                retry_limit=1,
                attempts=[
                    {
                        "assignment_id": "assignment_1",
                        "request_hash": "sha256:" + "8" * 64,
                        "retry_count": 0,
                    },
                    {
                        "assignment_id": "assignment_2",
                        "request_hash": "sha256:" + "9" * 64,
                        "retry_count": 0,
                    },
                ],
            )
            evidence["authorization"]["attempt_budget"] = 1
            evidence["usage"]["physical_call_ceiling"] = 2
            with self.assertRaisesRegex(ValueError, "live_usage_malformed"):
                validate_live_provider_evidence(evidence)

    def test_offline_verifier_cli_requires_explicit_real_live_contract(self) -> None:
        from scripts.verify_contacts_acceptance_proof import parse_args

        with patch.object(
            sys,
            "argv",
            [
                "verify_contacts_acceptance_proof.py",
                "artifacts/contacts-proof",
                "--real-live",
            ],
        ):
            args = parse_args()

        self.assertEqual(args.proof_root, Path("artifacts/contacts-proof"))
        self.assertTrue(args.real_live)

    def test_live_budget_failure_is_recorded_without_provider_work(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
            run_live_contacts_acceptance,
        )

        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-budget-20260830",
            candidate_budget=10,
            attempt_budget=9,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaisesRegex(
                LiveContactsAcceptanceError,
                "contacts_live_attempt_budget_exceeded",
            ):
                run_live_contacts_acceptance(
                    root / "acceptance",
                    profile=self._profile(),
                    authorization=authorization,
                    generator_config=self._config(),
                    generator_http_client=object(),
                    mutation_judge_http_client=object(),
                    proof_root=root / "proof",
                )
            failure = json.loads(
                (
                    root
                    / "acceptance"
                    / "contacts_live_attempt_failure.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(failure["phase"], "preparation")
        self.assertEqual(failure["generator_usage"]["logical_calls"], 0)
        self.assertEqual(
            failure["run_binding"]["profile_id"],
            "contacts_release_candidate",
        )
        self.assertFalse(failure["provider_evidence_frozen"])

    def test_generator_failure_writes_bounded_usage_and_no_frozen_evidence(self) -> None:
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            LiveContactsAcceptanceError,
            run_live_contacts_acceptance,
        )

        def response(content: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(content)}}
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                },
            )

        def unavailable_generator(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(503, json={"error": "generator unavailable"})

        def judge_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            prompt = json.loads(body["messages"][1]["content"])
            references = prompt["validated_provenance"]["evidence_references"]
            arguments = prompt["proposed_mutation"]["requester_arguments"]
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
                    "argument_findings": [
                        {
                            "argument": name,
                            "outcome": "supported",
                            "reason_code": "argument_semantic_supported",
                            "evidence_references": [references[name]],
                        }
                        for name in arguments
                    ],
                    "reason_codes": [
                        "action_authorized",
                        "argument_semantic_supported",
                    ],
                    "evidence_references": list(
                        dict.fromkeys(references.values())
                    ),
                    "input_hash": prompt["input_hash"],
                }
            )

        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-generator-failure-20260830",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                httpx.Client(
                    transport=httpx.MockTransport(unavailable_generator)
                ) as generator_client,
                httpx.Client(
                    transport=httpx.MockTransport(judge_handler)
                ) as judge_client,
            ):
                with self.assertRaisesRegex(
                    LiveContactsAcceptanceError,
                    "contacts_live_coverage_evidence_incomplete",
                ):
                    run_live_contacts_acceptance(
                        root / "acceptance",
                        profile=self._profile(),
                        authorization=authorization,
                        generator_config=self._config(),
                        generator_http_client=generator_client,
                        mutation_judge_http_client=judge_client,
                        proof_root=root / "proof",
                    )
            failure = json.loads(
                (
                    root
                    / "acceptance"
                    / "contacts_live_attempt_failure.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(failure["phase"], "pipeline")
        self.assertGreater(failure["generator_usage"]["logical_calls"], 0)
        self.assertLessEqual(failure["generator_usage"]["logical_calls"], 10)
        self.assertEqual(
            failure["generator_usage"]["failure_classes"],
            {
                "http_status": failure["generator_usage"]["logical_calls"],
            },
        )
        self.assertFalse(failure["provider_evidence_frozen"])
        self.assertFalse(failure["proof_root_published"])
        serialized = json.dumps(failure).lower()
        self.assertNotIn("generator unavailable", serialized)
        self.assertNotIn("injected-only", serialized)

    def test_ambiguous_generator_timeout_is_classified_without_payload_retention(
        self,
    ) -> None:
        from synthesis.acceptance_replay import BoundedSanitizedProvider
        from synthesis.contacts_live_acceptance import (
            LiveContactsAcceptanceAuthorization,
            SanitizedProviderEvidenceRecorder,
            _generator_usage_summary,
        )
        from synthesis.llm import LLMProviderError

        class TimeoutProvider:
            def generate_json(self, prompt: str, *, role: str):
                del prompt, role
                raise LLMProviderError(
                    cause="llm_provider_error",
                    error_class="ReadTimeout",
                    retryable=True,
                    ambiguous=True,
                )

        authorization = LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-live-timeout-class-20260904",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )
        recorder = SanitizedProviderEvidenceRecorder(
            authorization=authorization,
            provider_identity={
                "provider_id": "openai_compatible",
                "provider_version": "openai_compatible_client_v1",
                "provider_host": "llm.example.test",
                "model": "contacts-generator-test-model",
                "config_hash": "sha256:" + "1" * 64,
                "parser_version": "domain_generation_parser_v1",
            },
            mutation_judge_identity={
                "provider": "openai_compatible",
                "provider_host": "llm.example.test",
                "model": "deepseek-v4-pro",
                "config_hash": "sha256:" + "2" * 64,
                "role": "mutation_admission_judge",
                "role_version": "role_mutation_admission_judge_v1",
            },
        )
        prompt = '{"diagnostic": true}'
        request_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        recorder.bind_assignment(
            request_hash=request_hash,
            assignment={"assignment_id": "contacts_timeout_assignment"},
        )
        provider = BoundedSanitizedProvider(
            TimeoutProvider(),
            recorder=recorder,
            max_logical_calls=10,
        )

        with self.assertRaisesRegex(LLMProviderError, "ReadTimeout"):
            provider.generate_json(prompt, role="task_generation")

        usage = _generator_usage_summary(recorder)
        self.assertEqual(usage["logical_calls"], 1)
        self.assertEqual(usage["failure_classes"], {"timeout": 1})
        self.assertNotIn("diagnostic", json.dumps(recorder.attempts))

    def test_rejection_summary_retains_allowlisted_membership_reason(self) -> None:
        from synthesis.contacts_live_acceptance import _bounded_rejection_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rejections.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "cause": "domain_plan_membership_rejected",
                        "details": {
                            "membership_reason": "grounding_membership_mismatch"
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            summary = _bounded_rejection_summary(path)

        self.assertEqual(summary["count"], 1)
        self.assertEqual(
            summary["membership_reasons"],
            {"grounding_membership_mismatch": 1},
        )

    def test_live_cli_requires_explicit_authorization_and_uses_contacts_profile(
        self,
    ) -> None:
        from scripts.run_contacts_live_acceptance import DEFAULT_PROFILE, parse_args

        with patch.object(
            sys,
            "argv",
            [
                "run_contacts_live_acceptance.py",
                "--authorize-live-provider",
                "--authorization-id",
                "contacts-live-cli-20260830",
                "--candidate-budget",
                "10",
                "--attempt-budget",
                "10",
                "--generator-model",
                "generator",
            ],
        ):
            args = parse_args()

        from synthesis.contacts_live_acceptance import (
            DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
        )

        self.assertEqual(args.run_profile, DEFAULT_PROFILE)
        self.assertEqual(
            args.mutation_judge_model,
            DEFAULT_CONTACTS_MUTATION_JUDGE_MODEL,
        )
        self.assertEqual(args.generator_timeout_seconds, 90.0)
        self.assertEqual(args.max_generator_retries, 0)
        self.assertTrue(args.authorize_live_provider)


if __name__ == "__main__":
    unittest.main()
