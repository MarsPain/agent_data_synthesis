from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from synthesis.seeds import foundation_seed
from synthesis.tasks import CandidateTask


class OpenAICompatibleProviderTest(unittest.TestCase):
    def test_config_reads_only_agent_data_prefixed_environment_variables(self) -> None:
        from synthesis.llm import LLMConfig

        with patch.dict(
            os.environ,
            {
                "LLM_BASE_URL": "https://wrong.example.test/v1",
                "API_KEY": "wrong-key",
                "LLM_MODEL": "wrong-model",
                "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                "AGENT_DATA_API_KEY": "secret-test-key",
                "AGENT_DATA_LLM_MODEL": "test-generator",
            },
            clear=False,
        ):
            config = LLMConfig.from_env()

        self.assertEqual(config.base_url, "https://llm.example.test/v1")
        self.assertEqual(config.api_key, "secret-test-key")
        self.assertEqual(config.model, "test-generator")
        self.assertEqual(config.provider_host, "llm.example.test")

    def test_chat_completion_request_returns_content_and_redacted_lineage(self) -> None:
        from synthesis.llm import LLMConfig, OpenAICompatibleClient

        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({"candidates": []}),
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 5,
                        "total_tokens": 12,
                    },
                },
            )

        client = OpenAICompatibleClient(
            LLMConfig(
                base_url="https://llm.example.test/v1",
                api_key="secret-test-key",
                model="test-generator",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        result = client.generate_json("Generate candidate tasks.", role="task_generation")

        self.assertEqual(captured["url"], "https://llm.example.test/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer secret-test-key")
        self.assertEqual(captured["payload"]["model"], "test-generator")
        self.assertEqual(result.content, {"candidates": []})
        self.assertEqual(result.lineage["provider_host"], "llm.example.test")
        self.assertEqual(result.lineage["tokens"]["total_tokens"], 12)
        self.assertNotIn("secret-test-key", json.dumps(result.lineage))
        self.assertNotIn("secret-test-key", repr(client.config))

    def test_llm_candidate_generator_parses_remote_candidates(self) -> None:
        from synthesis.tasks import generate_llm_backed_candidates

        seed = foundation_seed()

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                self.prompt = prompt
                self.role = role
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "candidates": [
                                {
                                    "candidate_id": "candidate_llm_alice",
                                    "instruction": "Find Alice Zhang's email address.",
                                    "constraints": {"must_use_tool": "lookup_contact_email"},
                                    "difficulty": {
                                        "level": "easy",
                                        "tool_count": 1,
                                        "state_changes": 0,
                                        "ambiguity": "none",
                                        "recovery_paths": 0,
                                    },
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice Zhang"},
                                    "expected_answer": "alice.zhang@example.test",
                                }
                            ]
                        },
                        "lineage": {"provider_host": "llm.example.test"},
                    },
                )()

        fake_client = FakeClient()
        candidates = generate_llm_backed_candidates(seed, fake_client)

        self.assertEqual(fake_client.role, "task_generation")
        self.assertIn("contacts_fixture", fake_client.prompt)
        self.assertIn("lookup_contact_email", fake_client.prompt)
        self.assertIn("Alice Zhang -> alice.zhang@example.test", fake_client.prompt)
        self.assertIn("Ben Carter -> ben.carter@example.test", fake_client.prompt)
        self.assertEqual(len(candidates), 1)
        self.assertIsInstance(candidates[0], CandidateTask)
        self.assertEqual(candidates[0].candidate_id, "candidate_llm_alice")
        self.assertEqual(candidates[0].seed_ids, ("seed_contacts_v1",))

    def test_llm_candidate_generator_normalizes_scalar_difficulty(self) -> None:
        from synthesis.tasks import generate_llm_backed_candidates

        seed = foundation_seed()

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "candidates": [
                                {
                                    "candidate_id": "candidate_llm_alice",
                                    "instruction": "Find Alice Zhang's email address.",
                                    "constraints": {"must_use_tool": "lookup_contact_email"},
                                    "difficulty": "easy",
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice Zhang"},
                                    "expected_answer": "alice.zhang@example.test",
                                }
                            ]
                        },
                        "lineage": {"provider_host": "llm.example.test"},
                    },
                )()

        candidates = generate_llm_backed_candidates(seed, FakeClient())

        self.assertEqual(
            candidates[0].difficulty,
            {
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 0,
                "state_changes": 0,
                "ambiguity": "unspecified",
                "recovery_paths": 0,
            },
        )

    def test_llm_candidate_generator_normalizes_scalar_constraints(self) -> None:
        from synthesis.tasks import generate_llm_backed_candidates

        seed = foundation_seed()

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "candidates": [
                                {
                                    "candidate_id": "candidate_llm_alice",
                                    "instruction": "Find Alice Zhang's email address.",
                                    "constraints": "must use lookup_contact_email",
                                    "difficulty": {
                                        "level": "easy",
                                        "tool_count": 1,
                                        "state_changes": 0,
                                        "ambiguity": "none",
                                        "recovery_paths": 0,
                                    },
                                    "tool_name": "lookup_contact_email",
                                    "arguments": {"name": "Alice Zhang"},
                                    "expected_answer": "alice.zhang@example.test",
                                }
                            ]
                        },
                        "lineage": {"provider_host": "llm.example.test"},
                    },
                )()

        candidates = generate_llm_backed_candidates(seed, FakeClient())

        self.assertEqual(
            candidates[0].constraints,
            {"description": "must use lookup_contact_email"},
        )

    def test_llm_candidate_generator_normalizes_known_contact_tool_alias(self) -> None:
        from synthesis.tasks import generate_llm_backed_candidates

        seed = foundation_seed()

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "candidates": [
                                {
                                    "candidate_id": "candidate_llm_alice",
                                    "instruction": "Find Alice Zhang's email address.",
                                    "constraints": {"must_use_tool": "lookup_contact_email"},
                                    "difficulty": {
                                        "level": "easy",
                                        "tool_count": 1,
                                        "state_changes": 0,
                                        "ambiguity": "none",
                                        "recovery_paths": 0,
                                    },
                                    "tool_name": "lookup_contact",
                                    "arguments": {"name": "Alice Zhang"},
                                    "expected_answer": "alice.zhang@example.test",
                                }
                            ]
                        },
                        "lineage": {"provider_host": "llm.example.test"},
                    },
                )()

        candidates = generate_llm_backed_candidates(seed, FakeClient())

        self.assertEqual(candidates[0].tool_name, "lookup_contact_email")

    def test_pipeline_can_use_injected_llm_candidate_generator(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def llm_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_llm_alice",
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
                    dataset_version="dataset_llm_test",
                    candidate_generator=llm_generator,
                )

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            self.assertEqual(sample["task"]["instruction"], "Find Alice Zhang's email address.")
            self.assertNotIn("secret-test-key", json.dumps(sample))

    def test_pipeline_can_build_llm_candidate_generator_from_env(self) -> None:
        from synthesis.pipeline import build_llm_candidate_generator, run_foundation_pipeline

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            self.assertEqual(request.headers.get("authorization"), "Bearer secret-test-key")
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "candidates": [
                                            {
                                                "candidate_id": "candidate_llm_alice",
                                                "instruction": "Find Alice Zhang's email address.",
                                                "constraints": {
                                                    "must_use_tool": "lookup_contact_email"
                                                },
                                                "difficulty": {
                                                    "level": "easy",
                                                    "tool_count": 1,
                                                    "state_changes": 0,
                                                    "ambiguity": "none",
                                                    "recovery_paths": 0,
                                                },
                                                "tool_name": "lookup_contact_email",
                                                "arguments": {"name": "Alice Zhang"},
                                                "expected_answer": "alice.zhang@example.test",
                                            }
                                        ]
                                    }
                                ),
                            }
                        }
                    ],
                    "usage": {"total_tokens": 20},
                },
            )

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
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
                    dataset_version="dataset_llm_provider_test",
                    candidate_generator=build_llm_candidate_generator(http_client=http_client),
                )

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(request_count, 1)
            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(sample["lineage"]["generator"]["provider_host"], "llm.example.test")
            self.assertEqual(sample["lineage"]["generator"]["tokens"]["total_tokens"], 20)
            self.assertEqual(sample["lineage"]["generator"]["retry_count"], 0)
            self.assertIn("prompt_hash", sample["lineage"]["generator"])
            self.assertNotIn("secret-test-key", json.dumps(sample))

    def test_chat_completion_retries_transient_status_and_records_retry_count(self) -> None:
        from synthesis.llm import LLMConfig, OpenAICompatibleClient

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({"candidates": []}),
                            }
                        }
                    ],
                    "usage": {"total_tokens": 9},
                },
            )

        client = OpenAICompatibleClient(
            LLMConfig(
                base_url="https://llm.example.test/v1",
                api_key="secret-test-key",
                model="test-generator",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            sleeper=lambda _: None,
        )

        result = client.generate_json("Generate candidate tasks.", role="task_generation")

        self.assertEqual(request_count, 2)
        self.assertEqual(result.content, {"candidates": []})
        self.assertEqual(result.lineage["retry_count"], 1)
        self.assertEqual(result.lineage["error_class"], None)

    def test_chat_completion_exhausted_retry_error_is_sanitized(self) -> None:
        from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "secret-test-key should not leak"})

        client = OpenAICompatibleClient(
            LLMConfig(
                base_url="https://llm.example.test/v1",
                api_key="secret-test-key",
                model="test-generator",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            sleeper=lambda _: None,
        )

        with self.assertRaises(LLMProviderError) as raised:
            client.generate_json("Generate candidate tasks with secret-test-key.", role="task_generation")

        error = raised.exception
        self.assertEqual(error.cause, "llm_provider_error")
        self.assertEqual(error.error_class, "HTTPStatusError")
        self.assertEqual(error.retry_count, 1)
        self.assertTrue(error.retryable)
        self.assertNotIn("secret-test-key", str(error))

    def test_malformed_chat_completion_content_is_response_schema_error(self) -> None:
        from synthesis.llm import LLMConfig, LLMProviderError, OpenAICompatibleClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "not-json"}}]},
            )

        client = OpenAICompatibleClient(
            LLMConfig(
                base_url="https://llm.example.test/v1",
                api_key="secret-test-key",
                model="test-generator",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(LLMProviderError) as raised:
            client.generate_json("Generate candidate tasks.", role="task_generation")

        self.assertEqual(raised.exception.cause, "llm_response_schema_error")
        self.assertEqual(raised.exception.error_class, "JSONDecodeError")

    def test_llm_candidate_generator_classifies_invalid_candidate_array(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.tasks import generate_llm_backed_candidates

        seed = foundation_seed()

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {"candidates": {"not": "a list"}},
                        "lineage": {"provider_host": "llm.example.test"},
                    },
                )()

        with self.assertRaises(LLMProviderError) as raised:
            generate_llm_backed_candidates(seed, FakeClient())

        self.assertEqual(raised.exception.cause, "llm_response_schema_error")

    def test_llm_solution_policy_generator_parses_remote_policy(self) -> None:
        from synthesis.execution import SolutionPolicy, generate_llm_backed_solution_policy

        task = CandidateTask(
            candidate_id="candidate_contacts_alice_followup",
            instruction="Find Alice Zhang's email and record a follow-up note.",
            constraints={
                "task_type": "contact_followup",
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
            },
            difficulty={"level": "medium", "tool_count": 2},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> object:
                self.prompt = prompt
                self.role = role
                return type(
                    "FakeResult",
                    (),
                    {
                        "content": {
                            "policy": {
                                "policy_id": "policy_llm_followup",
                                "steps": [
                                    {
                                        "tool_name": "lookup_contact_email",
                                        "arguments": {"name": "Alice Zhang"},
                                    },
                                    {
                                        "tool_name": "record_contact_followup",
                                        "arguments": {
                                            "name": "Alice Zhang",
                                            "note": "Send follow-up email to alice.zhang@example.test.",
                                        },
                                    },
                                ],
                                "final_response_template": "{name}'s email is {email}. Follow-up recorded.",
                            }
                        },
                        "lineage": {
                            "role": "solution_policy",
                            "provider_host": "llm.example.test",
                            "model": "test-generator",
                            "config_hash": "abc123",
                        },
                    },
                )()

        fake_client = FakeClient()
        policy = generate_llm_backed_solution_policy(task, fake_client)

        self.assertEqual(fake_client.role, "solution_policy")
        self.assertIn("candidate_contacts_alice_followup", fake_client.prompt)
        self.assertIsInstance(policy, SolutionPolicy)
        self.assertEqual(policy.policy_id, "policy_llm_followup")
        self.assertEqual([step.tool_name for step in policy.steps], ["lookup_contact_email", "record_contact_followup"])
        self.assertEqual(policy.lineage["provider_host"], "llm.example.test")

    def test_remote_critic_refinement_uses_openai_boundary_and_sanitized_lineage(self) -> None:
        from synthesis.llm import LLMConfig, OpenAICompatibleClient
        from synthesis.refinement import generate_llm_backed_refinement

        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "repair_decision": "repair_candidate",
                                        "critic_diagnosis": "Ben Carter expected answer is stale.",
                                        "candidate": {
                                            "candidate_id": "candidate_contacts_ben_bad_expectation_refined_1",
                                            "instruction": "Find Ben Carter's email address.",
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
                                            "arguments": {"name": "Ben Carter"},
                                            "expected_answer": "ben.carter@example.test",
                                        },
                                    }
                                ),
                            }
                        }
                    ],
                    "usage": {"total_tokens": 31},
                },
            )

        client = OpenAICompatibleClient(
            LLMConfig(
                base_url="https://llm.example.test/v1",
                api_key="secret-test-key",
                model="test-generator",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        task = CandidateTask(
            candidate_id="candidate_contacts_ben_bad_expectation",
            instruction="Find Ben Carter's email address.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={"level": "easy", "tool_count": 1},
            tool_name="lookup_contact_email",
            arguments={"name": "Ben Carter"},
            expected_answer="ben@example.test",
            seed_ids=("seed_contacts_v1",),
        )

        attempt = generate_llm_backed_refinement(
            task=task,
            source_failure_cause="verification_failed",
            source_failure_details={"expected": "ben@example.test"},
            attempt_number=1,
            client=client,
        )

        self.assertEqual(captured["authorization"], "Bearer secret-test-key")
        self.assertEqual(captured["payload"]["model"], "test-generator")
        self.assertEqual(attempt.lineage["role"], "critic_refinement")
        self.assertEqual(attempt.lineage["provider_host"], "llm.example.test")
        self.assertEqual(attempt.lineage["model"], "test-generator")
        self.assertEqual(attempt.lineage["retry_count"], 0)
        self.assertEqual(attempt.lineage["tokens"]["total_tokens"], 31)
        self.assertIn("prompt_hash", attempt.lineage)
        self.assertNotIn("secret-test-key", json.dumps(attempt.export()))


if __name__ == "__main__":
    unittest.main()
