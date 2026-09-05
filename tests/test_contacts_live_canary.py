from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import httpx


class ContactsLiveContractCanaryTest(unittest.TestCase):
    @staticmethod
    def _profile():
        from synthesis.run_profiles import load_run_profile

        return load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )

    @staticmethod
    def _authorization():
        from synthesis.contacts_live_acceptance import LiveContactsAcceptanceAuthorization

        return LiveContactsAcceptanceAuthorization(
            approved=True,
            authorization_id="contacts-canary-test-20260904",
            candidate_budget=10,
            attempt_budget=10,
            generator_provider="openai_compatible",
            generator_model="contacts-generator-test-model",
            mutation_judge_provider="openai_compatible",
            mutation_judge_model="deepseek-v4-pro",
        )

    @staticmethod
    def _config():
        from synthesis.llm import LLMConfig

        return LLMConfig(
            base_url="https://llm.example.test/v1",
            api_key="injected-only",
            model="contacts-generator-test-model",
        )

    def test_canary_accepts_one_exact_followup_without_publishing_a_proof(self) -> None:
        from synthesis.contacts_live_canary import run_contacts_live_contract_canary

        def handler(request: httpx.Request) -> httpx.Response:
            request_body = json.loads(request.read())
            payload = json.loads(request_body["messages"][1]["content"])
            task_spec = payload["task_types"][0]
            self.assertEqual(task_spec["task_type"], "contact_followup")
            grounding = next(iter(payload["grounding_context"].values()))[0]
            observation = grounding["observation"]
            prompt_contract = payload["output_contract"]["task_type_contracts"][0]
            self.assertEqual(
                prompt_contract["expected_state"]["grounding_bindings"],
                [
                    {
                        "state_field": "name",
                        "observation_field": "name",
                        "match": "exact",
                    },
                    {
                        "state_field": "note",
                        "observation_field": "email",
                        "match": "contains",
                    },
                ],
            )
            record = {
                "candidate_id": (
                    f"{payload['batch_context']['candidate_id_prefix']}canary"
                ),
                "instruction": (
                    f"Find {observation['name']}'s email and record a follow-up "
                    f"to send {observation['email']}."
                ),
                "task_type": task_spec["task_type"],
                "difficulty": {},
                "required_capabilities": task_spec["required_capabilities"],
                "required_tools": task_spec["required_tools"],
                "primary_tool": task_spec["required_tools"][0],
                "primary_arguments": grounding["primary_arguments"],
                "final_answer_contains": observation["email"],
                "expected_state": [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": observation["name"],
                            "note": (
                                f"Send follow-up email to {observation['email']}."
                            ),
                        },
                    }
                ],
            }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps({"task_contracts": [record]})}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 8},
                },
            )

        def judge_handler(request: httpx.Request) -> httpx.Response:
            request_body = json.loads(request.read())
            prompt = json.loads(request_body["messages"][1]["content"])
            references = prompt["validated_provenance"]["evidence_references"]
            arguments = prompt["proposed_mutation"]["requester_arguments"]
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
                "evidence_references": list(dict.fromkeys(references.values())),
                "input_hash": prompt["input_hash"],
            }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(verdict)}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "canary"
            with (
                httpx.Client(transport=httpx.MockTransport(handler)) as client,
                httpx.Client(transport=httpx.MockTransport(judge_handler)) as judge_client,
            ):
                result = run_contacts_live_contract_canary(
                    output_dir,
                    profile=self._profile(),
                    authorization=self._authorization(),
                    generator_config=self._config(),
                    generator_http_client=client,
                    mutation_judge_http_client=judge_client,
                )
            record = json.loads(result.record_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "passed")
        self.assertEqual(record["canary"]["task_type"], "contact_followup")
        self.assertEqual(record["generator_usage"]["logical_calls"], 1)
        self.assertEqual(record["admission_replay"]["status"], "passed")
        self.assertEqual(record["admission_replay"]["provider_calls"], 0)
        self.assertTrue(record["non_qualifying"])
        self.assertNotIn("instruction", json.dumps(record).lower())
        self.assertNotIn("injected-only", json.dumps(record).lower())

    def test_canary_rejects_an_ungrounded_followup_note_without_a_proof(self) -> None:
        from synthesis.contacts_live_canary import (
            ContactsLiveContractCanaryError,
            run_contacts_live_contract_canary,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            request_body = json.loads(request.read())
            payload = json.loads(request_body["messages"][1]["content"])
            task_spec = payload["task_types"][0]
            grounding = next(iter(payload["grounding_context"].values()))[0]
            observation = grounding["observation"]
            record = {
                "candidate_id": (
                    f"{payload['batch_context']['candidate_id_prefix']}invalid"
                ),
                "instruction": "RAW_CANARY_INSTRUCTION_MARKER",
                "task_type": task_spec["task_type"],
                "difficulty": {},
                "required_capabilities": task_spec["required_capabilities"],
                "required_tools": task_spec["required_tools"],
                "primary_tool": task_spec["required_tools"][0],
                "primary_arguments": grounding["primary_arguments"],
                "final_answer_contains": observation["email"],
                "expected_state": [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": observation["name"],
                            "note": "RAW_CANARY_NOTE_MARKER",
                        },
                    }
                ],
            }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps({"task_contracts": [record]})}}],
                    "usage": {},
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "canary"
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(
                    ContactsLiveContractCanaryError,
                    "contacts_canary_generation_contract_invalid",
                ):
                    run_contacts_live_contract_canary(
                        output_dir,
                        profile=self._profile(),
                        authorization=self._authorization(),
                        generator_config=self._config(),
                        generator_http_client=client,
                    )
            record = json.loads(
                (output_dir / "contacts_live_contract_canary.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(record["status"], "failed")
        self.assertEqual(
            record["reason_code"],
            "contacts_canary_generation_contract_invalid",
        )
        self.assertFalse(record["provider_evidence_frozen"])
        serialized = json.dumps(record)
        self.assertNotIn("RAW_CANARY_INSTRUCTION_MARKER", serialized)
        self.assertNotIn("RAW_CANARY_NOTE_MARKER", serialized)


if __name__ == "__main__":
    unittest.main()
