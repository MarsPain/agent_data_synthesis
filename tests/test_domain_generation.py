from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class DomainGenerationSpecTest(unittest.TestCase):
    def _valid_spec(self):
        from synthesis.domain_generation import DomainGenerationSpec, DomainTaskTypeSpec

        return DomainGenerationSpec(
            schema_version="domain_generation_spec_v1",
            domain_id="contacts_fixture",
            task_types=(
                DomainTaskTypeSpec(
                    task_type="contact_lookup",
                    required_tools=("lookup_contact_email",),
                    required_capabilities=("contact_lookup",),
                    final_answer_fields=("email",),
                ),
            ),
            tools=(
                {
                    "name": "lookup_contact_email",
                    "version": "tool_lookup_contact_email_v1",
                    "schema": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                    "side_effects": "read_only",
                },
            ),
            grounding_context={"contacts": [{"name": "Alice Zhang"}]},
            context_policy="synthetic_fixture",
            max_candidates_per_call=5,
        )

    def test_validates_and_exports_only_sanitized_spec_metadata(self) -> None:
        from synthesis.domain_generation import (
            grounding_context_hash,
            sanitized_generation_spec_metadata,
            validate_domain_generation_spec,
        )

        spec = self._valid_spec()
        validate_domain_generation_spec(spec)
        metadata = sanitized_generation_spec_metadata(spec)

        self.assertEqual(metadata["spec_version"], "domain_generation_spec_v1")
        self.assertEqual(metadata["domain_id"], "contacts_fixture")
        self.assertRegex(grounding_context_hash(spec), r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(metadata["grounding_context_hash"], grounding_context_hash(spec))
        self.assertNotIn("grounding_context", metadata)
        self.assertNotIn("Alice Zhang", str(metadata))

    def test_rejects_invalid_or_unsafe_specs(self) -> None:
        from synthesis.domain_generation import DomainTaskTypeSpec, validate_domain_generation_spec

        valid = self._valid_spec()
        invalid = (
            replace(valid, task_types=valid.task_types + valid.task_types),
            replace(valid, tools=()),
            replace(valid, task_types=(DomainTaskTypeSpec("lookup", ("missing",)),)),
            replace(valid, task_types=(DomainTaskTypeSpec("lookup", ("lookup_contact_email",), ("unknown_state",)),)),
            replace(valid, context_policy="governed_source_opt_in"),
            replace(valid, grounding_context={}),
            replace(valid, grounding_context={"api_key": "secret"}),
            replace(valid, grounding_context={"raw_source": {"row": "private"}}),
            replace(valid, grounding_context={"provider_prompt": "hidden prompt"}),
            replace(valid, tools=({**valid.tools[0], "side_effects": "Authorization: Bearer TOPSECRET"},)),
            replace(valid, grounding_context={"path": "/Users/example/private.json"}),
            replace(valid, grounding_context={"value": "Authorization: Bearer secret"}),
            replace(valid, max_candidates_per_call=0),
            replace(valid, max_candidates_per_call=6),
        )
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_domain_generation_spec(spec)

    def test_every_domain_bundle_owns_a_matching_generation_spec(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed, foundation_seed

        seeds = (
            foundation_seed(),
            DomainSeed("seed_mobile", "mobile_messages_fixture", "Mobile fixture.", ("mobile_message_search",)),
            DomainSeed("seed_workspace", "workspace_tasks_fixture", "Workspace fixture.", ("workspace_item_lookup",)),
        )
        expected_types = {
            "contacts_fixture": "contact_followup",
            "mobile_messages_fixture": "mobile_reminder_creation",
            "workspace_tasks_fixture": "workspace_task_creation",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for seed in seeds:
                with self.subTest(domain=seed.domain):
                    bundle = build_domain_pipeline_bundle(seed, Path(tmp) / seed.domain)
                    spec = bundle.generation_spec
                    self.assertEqual(spec.domain_id, bundle.domain_id)
                    self.assertIn(expected_types[bundle.domain_id], {item.task_type for item in spec.task_types})
                    self.assertEqual(
                        {tool["name"] for tool in spec.tools},
                        set(bundle.registry.tool_names()),
                    )
                    self.assertEqual(
                        spec.max_candidates_per_call,
                        {
                            "contacts_fixture": 5,
                            "mobile_messages_fixture": 2,
                            "workspace_tasks_fixture": 2,
                        }[bundle.domain_id],
                    )
                    grounding_entries = next(iter(spec.grounding_context.values()))
                    self.assertTrue(grounding_entries)
                    primary_tool = spec.task_types[0].required_tools[0]
                    for entry in grounding_entries:
                        self.assertEqual(
                            set(entry),
                            {"primary_arguments", "observation"},
                        )
                        self.assertEqual(
                            bundle.registry.execute(
                                primary_tool,
                                dict(entry["primary_arguments"]),
                            ),
                            entry["observation"],
                        )
                    prompt = json.loads(
                        build_domain_generation_prompt(
                            spec,
                            requested_candidate_count=1,
                            batch_context=build_generation_batch_context(
                                spec,
                                batch_index=1,
                            ),
                        )
                    )
                    prompt_task_types = {
                        item["task_type"]: item
                        for item in prompt["output_contract"]["task_type_contracts"]
                    }
                    tools_by_name = {tool["name"]: tool for tool in spec.tools}
                    for task_type_spec in spec.task_types:
                        self.assertTrue(task_type_spec.required_capabilities)
                        self.assertTrue(task_type_spec.final_answer_fields)
                        expected_state = prompt_task_types[
                            task_type_spec.task_type
                        ]["expected_state"]
                        self.assertEqual(
                            prompt_task_types[task_type_spec.task_type]["final_answer"],
                            {
                                "source": task_type_spec.final_answer_source,
                                "allowed_fields": list(task_type_spec.final_answer_fields),
                                "invented_text_allowed": False,
                            },
                        )
                        self.assertEqual(
                            prompt_task_types[task_type_spec.task_type][
                                "expected_state_tool"
                            ],
                            task_type_spec.expected_state_tool,
                        )
                        self.assertEqual(
                            prompt_task_types[task_type_spec.task_type][
                                "exact_record_values"
                            ]["required_capabilities"],
                            list(task_type_spec.required_capabilities),
                        )
                        if not task_type_spec.allowed_expected_state_checks:
                            self.assertIsNone(task_type_spec.expected_state_tool)
                            self.assertEqual(expected_state, {"mode": "empty"})
                            continue
                        mutating_tools = [
                            tool_name
                            for tool_name in task_type_spec.required_tools
                            if tools_by_name[tool_name]["side_effects"]
                            == "state_mutating"
                        ]
                        self.assertEqual(len(mutating_tools), 1)
                        self.assertEqual(
                            task_type_spec.expected_state_tool,
                            mutating_tools[0],
                        )
                        self.assertEqual(expected_state["mode"], "required")
                        self.assertEqual(
                            expected_state["exact_count"],
                            len(task_type_spec.allowed_expected_state_checks),
                        )
                        self.assertEqual(
                            expected_state["exact_items"],
                            [
                                {
                                    "check_type": check_type,
                                    "expected_must_match_tool_schema": mutating_tools[0],
                                    "expected_schema": tools_by_name[mutating_tools[0]][
                                        "schema"
                                    ],
                                }
                                for check_type in task_type_spec.allowed_expected_state_checks
                            ],
                        )

    def test_domain_task_types_declare_evidence_and_state_ownership(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed, foundation_seed

        seeds = (
            foundation_seed(),
            DomainSeed("seed_mobile", "mobile_messages_fixture", "Mobile.", ("search",)),
            DomainSeed("seed_workspace", "workspace_tasks_fixture", "Workspace.", ("search",)),
        )
        expected = {
            "contacts_fixture": {
                "contact_lookup": ("primary_observation", ("email",), None),
                "contact_followup": (
                    "primary_observation", ("email",), "record_contact_followup"
                ),
            },
            "mobile_messages_fixture": {
                "mobile_message_search": (
                    "primary_observation", ("message_id", "snippet"), None
                ),
                "mobile_reminder_creation": (
                    "primary_observation",
                    ("message_id", "snippet"),
                    "create_phone_reminder",
                ),
                "mobile_draft_reply": (
                    "primary_observation",
                    ("snippet",),
                    "draft_message_reply",
                ),
            },
            "workspace_tasks_fixture": {
                "workspace_item_search": (
                    "primary_observation", ("item_id", "summary"), None
                ),
                "workspace_task_creation": (
                    "state_tool_observation", ("task_id",), "create_workspace_task"
                ),
                "workspace_comment_update": (
                    "state_tool_observation", ("comment_id",), "add_workspace_comment"
                ),
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            for seed in seeds:
                bundle = build_domain_pipeline_bundle(seed, Path(tmp) / seed.domain)
                actual = {
                    item.task_type: (
                        item.final_answer_source,
                        item.final_answer_fields,
                        item.expected_state_tool,
                    )
                    for item in bundle.generation_spec.task_types
                }
                self.assertEqual(actual, expected[bundle.domain_id])

    def _provider_record(self, candidate_id: str = "contacts_b001_task_01"):
        return {
            "candidate_id": candidate_id,
            "instruction": "Find Alice Zhang's email address.",
            "task_type": "contact_lookup",
            "difficulty": {
                "level": "easy",
                "tool_count": 1,
                "constraint_count": 1,
                "state_changes": 0,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "required_capabilities": ["contact_lookup"],
            "required_tools": ["lookup_contact_email"],
            "primary_tool": "lookup_contact_email",
            "primary_arguments": {"name": "Alice Zhang"},
            "final_answer_contains": "alice.zhang@example.test",
            "expected_state": [],
        }

    def test_builds_deterministic_generation_batch_contexts(self) -> None:
        from synthesis.domain_generation import build_generation_batch_context

        spec = self._valid_spec()
        expected = {
            1: "contacts_b001_",
            2: "contacts_b002_",
            15: "contacts_b015_",
        }
        for batch_index, prefix in expected.items():
            context = build_generation_batch_context(spec, batch_index=batch_index)
            self.assertEqual(context.batch_index, batch_index)
            self.assertEqual(context.candidate_id_prefix, prefix)
        for invalid in (0, -1, True):
            with self.subTest(batch_index=invalid), self.assertRaises(ValueError):
                build_generation_batch_context(spec, batch_index=invalid)

    def test_batch_prefix_is_required_and_collision_details_are_fixed(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.seeds import foundation_seed

        spec = self._valid_spec()
        context = build_generation_batch_context(spec, batch_index=1)
        valid = self._provider_record("contacts_b001_task_01")
        contracts = parse_domain_task_contracts(
            {"task_contracts": [valid]},
            seed=foundation_seed(),
            spec=spec,
            batch_context=context,
            generation_lineage={},
        )
        self.assertEqual(contracts[0].intent.candidate_id, "contacts_b001_task_01")

        for candidate_id in ("task_01", "contacts_b002_task_01"):
            with self.subTest(candidate_id=candidate_id):
                with self.assertRaises(DomainGenerationValidationError) as raised:
                    parse_domain_task_contracts(
                        {"task_contracts": [self._provider_record(candidate_id)]},
                        seed=foundation_seed(),
                        spec=spec,
                        batch_context=context,
                        generation_lineage={},
                    )
                self.assertEqual(raised.exception.reason, "invalid_candidate_id")
                self.assertEqual(raised.exception.detail, "batch_prefix_mismatch")

        with self.assertRaises(DomainGenerationValidationError) as raised:
            parse_domain_task_contracts(
                {"task_contracts": [valid, valid]},
                seed=foundation_seed(),
                spec=spec,
                batch_context=context,
                generation_lineage={},
            )
        self.assertEqual(raised.exception.reason, "duplicate_candidate_id")
        self.assertEqual(raised.exception.detail, "within_batch")

    def test_prompt_and_provider_parser_enforce_domain_contract(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            parse_domain_task_contracts,
        )
        from synthesis.seeds import foundation_seed
        from synthesis.task_contracts import candidate_from_task_contract

        spec = self._valid_spec()
        from synthesis.domain_generation import build_generation_batch_context

        batch_context = build_generation_batch_context(spec, batch_index=1)
        first = build_domain_generation_prompt(
            spec,
            requested_candidate_count=1,
            batch_context=batch_context,
        )
        second = build_domain_generation_prompt(
            spec,
            requested_candidate_count=1,
            batch_context=batch_context,
        )
        self.assertEqual(first, second)
        self.assertIn("contacts_fixture", first)
        self.assertIn("lookup_contact_email", first)
        self.assertIn('"requested_candidate_count":1', first)
        self.assertNotIn("AGENT_DATA", first)
        self.assertNotIn("Authorization", first)
        output_contract = json.loads(first)["output_contract"]
        response_contract = output_contract["response"]
        record_contract = response_contract["task_contracts"]["items"]
        self.assertTrue(output_contract["json_only"])
        self.assertFalse(output_contract["markdown_allowed"])
        self.assertFalse(output_contract["commentary_allowed"])
        self.assertEqual(response_contract["type"], "object")
        self.assertEqual(response_contract["exact_keys"], ["task_contracts"])
        self.assertEqual(response_contract["task_contracts"]["type"], "array")
        self.assertEqual(response_contract["task_contracts"]["exact_count"], 1)
        self.assertEqual(response_contract["task_contracts"]["unique_by"], "candidate_id")
        self.assertEqual(record_contract["type"], "object")
        self.assertEqual(set(record_contract["exact_keys"]), set(self._provider_record()))
        self.assertEqual(record_contract["fields"]["candidate_id"]["type"], "string")
        self.assertTrue(record_contract["fields"]["candidate_id"]["non_empty"])
        self.assertEqual(
            record_contract["fields"]["candidate_id"]["starts_with"],
            "contacts_b001_",
        )
        self.assertEqual(
            json.loads(first)["batch_context"],
            {"batch_index": 1, "candidate_id_prefix": "contacts_b001_"},
        )
        self.assertEqual(record_contract["fields"]["difficulty"]["type"], "object")
        self.assertEqual(
            record_contract["fields"]["required_capabilities"]["type"],
            "array",
        )
        self.assertTrue(
            record_contract["fields"]["required_capabilities"]["non_empty"]
        )
        self.assertTrue(
            record_contract["fields"]["required_capabilities"]["unique_items"]
        )
        self.assertEqual(record_contract["fields"]["primary_arguments"]["type"], "object")
        self.assertEqual(record_contract["fields"]["expected_state"]["type"], "array")
        task_type_contract = output_contract["task_type_contracts"][0]
        self.assertEqual(task_type_contract["task_type"], "contact_lookup")
        self.assertEqual(task_type_contract["required_tools"], ["lookup_contact_email"])
        self.assertEqual(task_type_contract["primary_tool"], "lookup_contact_email")
        self.assertEqual(
            task_type_contract["exact_record_values"],
            {
                "task_type": "contact_lookup",
                "required_capabilities": ["contact_lookup"],
                "required_tools": ["lookup_contact_email"],
                "primary_tool": "lookup_contact_email",
            },
        )
        self.assertEqual(task_type_contract["expected_state"], {"mode": "empty"})
        self.assertEqual(
            output_contract["critical_rules"]["primary_tool"],
            {
                "must_equal": "required_tools[0]",
                "must_equal_selected_task_type_contract": True,
                "alternatives_allowed": False,
            },
        )
        self.assertEqual(
            output_contract["critical_rules"]["primary_arguments"],
            {
                "must_match_curated_tool_schema_for": "primary_tool",
                "must_copy_exact_from": "grounding_context.*.primary_arguments",
                "invented_arguments_allowed": False,
            },
        )
        self.assertNotIn("final_answer_contains", output_contract["critical_rules"])
        self.assertEqual(
            task_type_contract["final_answer"],
            {
                "source": "primary_observation",
                "allowed_fields": ["email"],
                "invented_text_allowed": False,
            },
        )
        self.assertIsNone(task_type_contract["expected_state_tool"])
        self.assertIn(
            "copy task_type, required_tools, and primary_tool exactly",
            json.loads(first)["instructions"],
        )
        self.assertIn(
            "copy final_answer_contains from an allowed field",
            json.loads(first)["instructions"].lower(),
        )
        self.assertIn(
            "copy primary_arguments exactly from one grounding_context entry",
            json.loads(first)["instructions"].lower(),
        )
        self.assertIn("lineage", output_contract["forbidden_fields"])
        self.assertIn("provider_payload", output_contract["forbidden_fields"])
        self.assertNotIn("output_item_keys", json.loads(first))

        contracts = parse_domain_task_contracts(
            {"task_contracts": [self._provider_record()]},
            seed=foundation_seed(),
            spec=spec,
            batch_context=batch_context,
            generation_lineage={"role": "task_generation", "provider_host": "llm.example.test"},
        )
        candidate = candidate_from_task_contract(contracts[0])
        self.assertEqual(candidate.tool_name, "lookup_contact_email")
        self.assertEqual(candidate.constraints["domain"], "contacts_fixture")

        invalid_records = (
            {**self._provider_record(), "domain_id": "contacts_fixture"},
            {**self._provider_record(), "task_type": "unknown"},
            {**self._provider_record(), "required_tools": ["missing_tool"]},
            {
                **self._provider_record(),
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
                "primary_tool": "record_contact_followup",
                "primary_arguments": {"name": "Alice Zhang", "note": "Follow up."},
            },
            {**self._provider_record(), "primary_arguments": {}},
            {**self._provider_record(), "branch_plan": {}},
            {**self._provider_record(), "instruction": "Authorization: Bearer TOPSECRET"},
        )
        for record in invalid_records:
            with self.subTest(record=record), self.assertRaises(Exception):
                parse_domain_task_contracts(
                    {"task_contracts": [record]},
                    seed=foundation_seed(),
                    spec=spec,
                    batch_context=batch_context,
                    generation_lineage={},
                )

    def test_bounded_generation_fulfills_exact_targets(self) -> None:
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.llm import LLMGenerationResult
        from synthesis.seeds import foundation_seed

        class FakeClient:
            def __init__(self) -> None:
                self.requested: list[int] = []

            def generate_json(self, prompt: str, *, role: str):
                payload = json.loads(prompt)
                count = payload["requested_candidate_count"]
                self.requested.append(count)
                prefix = payload["batch_context"]["candidate_id_prefix"]
                return LLMGenerationResult(
                    content={
                        "task_contracts": [
                            self_record(f"{prefix}task_{index:03d}")
                            for index in range(count)
                        ]
                    },
                    lineage={"role": role, "provider_host": "llm.example.test", "retry_count": 0},
                )

        self_record = self._provider_record
        for target, expected_calls in ((1, [1]), (5, [5]), (12, [5, 5, 2])):
            with self.subTest(target=target):
                client = FakeClient()
                result = generate_domain_llm_candidates(
                    foundation_seed(),
                    client,
                    spec=self._valid_spec(),
                    target_candidate_count=target,
                )
                self.assertEqual(client.requested, expected_calls)
                self.assertEqual(result.generated_candidate_count, target)
                self.assertEqual(len({item.candidate_id for item in result.candidates}), target)
        with self.assertRaises(ValueError):
            generate_domain_llm_candidates(
                foundation_seed(), FakeClient(), spec=self._valid_spec(),
                target_candidate_count=True,
            )

    def test_generation_classifies_every_strict_schema_failure(self) -> None:
        from synthesis.contracts import LLM_RESPONSE_SCHEMA_REASONS
        from synthesis.datasets import assemble_generation_stage_rejection
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.llm import LLMGenerationResult, LLMProviderError
        from synthesis.seeds import foundation_seed

        valid = self._provider_record()
        cases = {
            "response_shape_mismatch": ({"unexpected": []}, 1),
            "provider_record_keys_mismatch": (
                {"task_contracts": [{**valid, "provider_payload": "RAW_PROVIDER_MARKER"}]},
                1,
            ),
            "invalid_task_type": (
                {"task_contracts": [{**valid, "task_type": "unknown_task_type"}]},
                1,
            ),
            "invalid_required_tools": (
                {"task_contracts": [{**valid, "required_tools": ["unknown_tool"]}]},
                1,
            ),
            "invalid_primary_tool": (
                {"task_contracts": [{**valid, "primary_tool": "unknown_tool"}]},
                1,
            ),
            "invalid_tool_arguments": (
                {"task_contracts": [{**valid, "primary_arguments": {}}]},
                1,
            ),
            "invalid_difficulty": (
                {"task_contracts": [{**valid, "difficulty": "easy"}]},
                1,
            ),
            "invalid_expected_state": (
                {
                    "task_contracts": [
                        {
                            **valid,
                            "expected_state": [
                                {
                                    "check_type": "contact_followup",
                                    "expected": {"name": "Alice Zhang"},
                                }
                            ],
                        }
                    ]
                },
                1,
            ),
            "invalid_required_capabilities": (
                {"task_contracts": [{**valid, "required_capabilities": []}]},
                1,
            ),
            "invalid_candidate_id": (
                {"task_contracts": [{**valid, "candidate_id": "wrong_prefix_task"}]},
                1,
            ),
            "unsafe_provider_value": (
                {
                    "task_contracts": [
                        {
                            **valid,
                            "instruction": "Authorization: Bearer RAW_PROVIDER_MARKER",
                        }
                    ]
                },
                1,
            ),
            "duplicate_candidate_id": (
                {"task_contracts": [dict(valid), dict(valid)]},
                2,
            ),
            "batch_count_mismatch": ({"task_contracts": [dict(valid)]}, 2),
        }
        self.assertEqual(set(cases), LLM_RESPONSE_SCHEMA_REASONS)

        class FakeClient:
            def __init__(self, content: dict[str, object]) -> None:
                self.content = content

            def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
                return LLMGenerationResult(
                    content=self.content,
                    lineage={
                        "role": role,
                        "provider_host": "llm.example.test",
                        "retry_count": 0,
                    },
                )

        for expected_reason, (content, target) in cases.items():
            with self.subTest(reason=expected_reason):
                with self.assertRaises(LLMProviderError) as raised:
                    generate_domain_llm_candidates(
                        foundation_seed(),
                        FakeClient(content),
                        spec=self._valid_spec(),
                        target_candidate_count=target,
                    )
                error = raised.exception
                self.assertEqual(error.cause, "llm_response_schema_error")
                self.assertEqual(error.error_class, "DomainGenerationValidationError")
                self.assertEqual(error.schema_reason, expected_reason)
                persisted = json.dumps(
                    assemble_generation_stage_rejection(error=error),
                    sort_keys=True,
                )
                self.assertNotIn("RAW_PROVIDER_MARKER", persisted)
                self.assertNotIn("Alice Zhang", persisted)
                self.assertNotIn("candidate_contacts_generated", persisted)

    def test_required_capability_failures_have_fixed_details(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.seeds import foundation_seed

        spec = self._valid_spec()
        context = build_generation_batch_context(spec, batch_index=1)
        cases = {
            "required_capabilities_not_list": "contact_lookup",
            "required_capabilities_empty": [],
            "required_capabilities_duplicate": ["contact_lookup", "contact_lookup"],
            "required_capabilities_contract_mismatch": ["workspace_item_search"],
        }
        for expected_detail, required_capabilities in cases.items():
            with self.subTest(detail=expected_detail):
                record = {
                    **self._provider_record(),
                    "required_capabilities": required_capabilities,
                }
                with self.assertRaises(DomainGenerationValidationError) as raised:
                    parse_domain_task_contracts(
                        {"task_contracts": [record]},
                        seed=foundation_seed(),
                        spec=spec,
                        batch_context=context,
                        generation_lineage={},
                    )
                self.assertEqual(raised.exception.reason, "invalid_required_capabilities")
                self.assertEqual(raised.exception.detail, expected_detail)

    def test_generation_classifies_cross_batch_candidate_id_collision(self) -> None:
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.llm import LLMGenerationResult, LLMProviderError
        from synthesis.seeds import foundation_seed

        class FakeClient:
            def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
                return LLMGenerationResult(
                    content={"task_contracts": [self_record()]},
                    lineage={"role": role, "retry_count": 0},
                )

        self_record = self._provider_record
        spec = replace(self._valid_spec(), max_candidates_per_call=1)
        with self.assertRaises(LLMProviderError) as raised:
            generate_domain_llm_candidates(
                foundation_seed(),
                FakeClient(),
                spec=spec,
                target_candidate_count=2,
            )

        self.assertEqual(raised.exception.schema_reason, "duplicate_candidate_id")
        self.assertEqual(raised.exception.schema_detail, "across_batch")

    def test_expected_state_failures_have_fixed_details(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            "seed_mobile_expected_state",
            "mobile_messages_fixture",
            "Expected-state diagnostics.",
            ("mobile_reminder_creation",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        valid_state = {
            "check_type": "mobile_reminder",
            "expected": {
                "title": "Send the project update",
                "due_at": "tomorrow 9 AM",
                "source_message_id": "msg_maya_project_update",
            },
        }
        valid = {
            "candidate_id": "mobile_messages_b001_expected_state",
            "instruction": "Find Maya's project update and create a reminder.",
            "task_type": "mobile_reminder_creation",
            "difficulty": {
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "required_capabilities": ["message_search", "reminder_creation"],
            "required_tools": ["search_phone_messages", "create_phone_reminder"],
            "primary_tool": "search_phone_messages",
            "primary_arguments": {"query": "project update", "participant": "Maya"},
            "final_answer_contains": "msg_maya_project_update",
            "expected_state": [valid_state],
        }
        cases = {
            "expected_state_not_list": "RAW_STATE_MARKER",
            "expected_state_item_keys_mismatch": [
                {**valid_state, "provider_value": "RAW_STATE_MARKER"}
            ],
            "expected_state_check_type_invalid": [
                {**valid_state, "check_type": "RAW_STATE_MARKER"}
            ],
            "expected_state_check_duplicate": [valid_state, valid_state],
            "expected_state_expected_not_object": [
                {**valid_state, "expected": "RAW_STATE_MARKER"}
            ],
            "expected_state_missing": [],
            "expected_state_arguments_invalid": [
                {
                    **valid_state,
                    "expected": {
                        "title": "Send the project update",
                        "provider_value": "RAW_STATE_MARKER",
                    },
                }
            ],
        }
        context = build_generation_batch_context(
            bundle.generation_spec,
            batch_index=1,
        )
        for expected_detail, expected_state in cases.items():
            with self.subTest(detail=expected_detail):
                with self.assertRaises(DomainGenerationValidationError) as raised:
                    parse_domain_task_contracts(
                        {"task_contracts": [{**valid, "expected_state": expected_state}]},
                        seed=seed,
                        spec=bundle.generation_spec,
                        batch_context=context,
                        generation_lineage={},
                    )
                self.assertEqual(raised.exception.reason, "invalid_expected_state")
                self.assertEqual(raised.exception.detail, expected_detail)

    def test_domain_batch_policies_generate_thirty_unique_candidates(self) -> None:
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.llm import LLMGenerationResult
        from synthesis.seeds import DomainSeed, foundation_seed

        class DeterministicBatchClient:
            def __init__(self) -> None:
                self.requests: list[tuple[int, str]] = []

            def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
                payload = json.loads(prompt)
                count = payload["requested_candidate_count"]
                prefix = payload["batch_context"]["candidate_id_prefix"]
                self.requests.append((count, prefix))
                task_type = payload["task_types"][0]
                grounding = next(iter(payload["grounding_context"].values()))[0]
                field = task_type["final_answer"]["allowed_fields"][0]
                return LLMGenerationResult(
                    content={
                        "task_contracts": [
                            {
                                "candidate_id": f"{prefix}task_{index:02d}",
                                "instruction": "Execute the grounded fixture task.",
                                "task_type": task_type["task_type"],
                                "difficulty": {
                                    "level": "easy",
                                    "tool_count": 1,
                                    "constraint_count": 1,
                                    "state_changes": 0,
                                    "ambiguity": "none",
                                    "recovery_paths": 0,
                                },
                                "required_capabilities": task_type[
                                    "required_capabilities"
                                ],
                                "required_tools": task_type["required_tools"],
                                "primary_tool": task_type["required_tools"][0],
                                "primary_arguments": grounding["primary_arguments"],
                                "final_answer_contains": grounding["observation"][field],
                                "expected_state": [],
                            }
                            for index in range(count)
                        ]
                    },
                    lineage={"role": role, "retry_count": 0},
                )

        seeds = (
            foundation_seed(),
            DomainSeed("seed_mobile_30", "mobile_messages_fixture", "Mobile.", ("search",)),
            DomainSeed("seed_workspace_30", "workspace_tasks_fixture", "Workspace.", ("search",)),
        )
        expected_sizes = {
            "contacts_fixture": [5] * 6,
            "mobile_messages_fixture": [2] * 15,
            "workspace_tasks_fixture": [2] * 15,
        }
        with tempfile.TemporaryDirectory() as tmp:
            for seed in seeds:
                with self.subTest(domain=seed.domain):
                    bundle = build_domain_pipeline_bundle(seed, Path(tmp) / seed.domain)
                    client = DeterministicBatchClient()
                    result = generate_domain_llm_candidates(
                        seed,
                        client,
                        spec=bundle.generation_spec,
                        target_candidate_count=30,
                    )
                    self.assertEqual(
                        [count for count, _ in client.requests],
                        expected_sizes[bundle.domain_id],
                    )
                    for batch_index, (_, prefix) in enumerate(client.requests, start=1):
                        safe_domain = bundle.domain_id.removesuffix("_fixture")
                        self.assertEqual(prefix, f"{safe_domain}_b{batch_index:03d}_")
                    self.assertEqual(result.target_candidate_count, 30)
                    self.assertEqual(result.generated_candidate_count, 30)
                    self.assertEqual(
                        result.provider_call_count,
                        len(expected_sizes[bundle.domain_id]),
                    )
                    self.assertEqual(
                        len({candidate.candidate_id for candidate in result.candidates}),
                        30,
                    )

    def test_third_batch_prefix_failure_is_fail_closed_and_sanitized(self) -> None:
        from synthesis.datasets import assemble_generation_stage_rejection
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.llm import LLMGenerationResult, LLMProviderError
        from synthesis.seeds import foundation_seed

        class ThirdBatchFailureClient:
            def generate_json(self, prompt: str, *, role: str) -> LLMGenerationResult:
                payload = json.loads(prompt)
                count = payload["requested_candidate_count"]
                batch_index = payload["batch_context"]["batch_index"]
                prefix = payload["batch_context"]["candidate_id_prefix"]
                records = [
                    self_record(f"{prefix}task_{index:02d}")
                    for index in range(count)
                ]
                if batch_index == 3:
                    records[-1] = self_record("RAW_PROVIDER_MARKER_wrong_prefix")
                return LLMGenerationResult(
                    content={"task_contracts": records},
                    lineage={"role": role, "retry_count": 0},
                )

        self_record = self._provider_record
        with self.assertRaises(LLMProviderError) as raised:
            generate_domain_llm_candidates(
                foundation_seed(),
                ThirdBatchFailureClient(),
                spec=self._valid_spec(),
                target_candidate_count=30,
            )

        error = raised.exception
        self.assertEqual(error.cause, "llm_response_schema_error")
        self.assertEqual(error.schema_reason, "invalid_candidate_id")
        self.assertEqual(error.schema_detail, "batch_prefix_mismatch")
        self.assertEqual(error.lineage["batch_index"], 3)
        self.assertEqual(error.lineage["requested_candidate_count"], 5)
        persisted = json.dumps(
            assemble_generation_stage_rejection(error=error),
            sort_keys=True,
        )
        self.assertNotIn("RAW_PROVIDER_MARKER", persisted)
        self.assertNotIn("contacts_b001_", persisted)
        self.assertNotIn("contacts_b002_", persisted)

    def test_pipeline_resolves_candidate_generator_factory_after_bundle(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.seeds import DomainSeed

        captured: list[str] = []

        def factory(bundle):
            captured.append(bundle.generation_spec.domain_id)
            return bundle.candidate_generator

        seed = DomainSeed(
            "seed_mobile_factory",
            "mobile_messages_fixture",
            "Mobile factory test.",
            ("mobile_message_search",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_foundation_pipeline(
                Path(tmp),
                seed_override=seed,
                candidate_generator_factory=factory,
            )
        self.assertEqual(captured, ["mobile_messages_fixture"])

        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            run_foundation_pipeline(
                Path(tmp),
                candidate_generator=lambda seed: [],
                candidate_generator_factory=factory,
            )

    def test_generation_contract_evidence_is_computed_from_profile_and_result(self) -> None:
        from synthesis.domain_generation import (
            build_generation_contract_evidence,
            sanitized_generation_spec_metadata,
        )

        from synthesis.run_profiles import load_run_profile

        mapping = {
            "schema_version": "run_profile_v3",
            "profile_id": "contacts_representative_test",
            "dataset_version": "dataset_contacts_representative_test",
            "profile_purpose": "benchmark",
            "seed": {
                "seed_id": "seed_contacts_representative_test",
                "domain": "contacts_fixture",
                "description": "Representative contacts test.",
                "task_taxonomy": ["contact_lookup"],
            },
            "generation": {
                "mode": "llm",
                "target_candidate_count": 2,
                "context_policy": "synthetic_fixture",
            },
            "features": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            profile_path.write_text(__import__("json").dumps(mapping), encoding="utf-8")
            profile = load_run_profile(profile_path)
        evidence = build_generation_contract_evidence(
            profile=profile,
            spec_metadata=sanitized_generation_spec_metadata(self._valid_spec()),
            target_candidate_count=2,
            generated_candidate_count=2,
        )
        self.assertEqual(
            set(evidence),
            {
                "spec_version", "context_policy", "target_candidate_count",
                "generated_candidate_count", "target_fulfilled",
                "representative_eligible", "reason_codes", "grounding_context_hash",
            },
        )
        self.assertTrue(evidence["target_fulfilled"])
        self.assertTrue(evidence["representative_eligible"])
        self.assertEqual(evidence["reason_codes"], [])

    def test_generated_mobile_reminder_uses_existing_scripted_policy(self) -> None:
        from synthesis.domain_generation import (
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mobile_tasks import scripted_mobile_solution_policy_from_contract
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            "seed_mobile_generated",
            "mobile_messages_fixture",
            "Generated mobile reminder.",
            ("mobile_reminder_creation",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        record = {
            "candidate_id": "mobile_messages_b001_generated_reminder",
            "instruction": "Find Maya's project update and create a reminder.",
            "task_type": "mobile_reminder_creation",
            "difficulty": {
                "level": "medium", "tool_count": 2, "constraint_count": 2,
                "state_changes": 1, "ambiguity": "none", "recovery_paths": 0,
            },
            "required_capabilities": ["message_search", "reminder_creation"],
            "required_tools": ["search_phone_messages", "create_phone_reminder"],
            "primary_tool": "search_phone_messages",
            "primary_arguments": {"query": "project update", "participant": "Maya"},
            "final_answer_contains": "msg_maya_project_update",
            "expected_state": [{
                "check_type": "mobile_reminder",
                "expected": {
                    "title": "Send the project update",
                    "due_at": "tomorrow 9 AM",
                    "source_message_id": "msg_maya_project_update",
                },
            }],
        }
        contract = parse_domain_task_contracts(
            {"task_contracts": [record]},
            seed=seed,
            spec=bundle.generation_spec,
            batch_context=build_generation_batch_context(
                bundle.generation_spec,
                batch_index=1,
            ),
            generation_lineage={},
        )[0]
        policy = scripted_mobile_solution_policy_from_contract(contract)
        self.assertEqual(
            [step.tool_name for step in policy.steps],
            ["search_phone_messages", "create_phone_reminder"],
        )
        invalid_primary = {
            **record,
            "primary_tool": "create_phone_reminder",
            "primary_arguments": {"title": "Send the project update"},
        }
        with self.assertRaises(Exception):
            parse_domain_task_contracts(
                {"task_contracts": [invalid_primary]}, seed=seed,
                spec=bundle.generation_spec,
                batch_context=build_generation_batch_context(
                    bundle.generation_spec,
                    batch_index=1,
                ),
                generation_lineage={},
            )

    def test_rejects_state_contract_that_cannot_call_mutating_tool(self) -> None:
        from synthesis.domain_generation import (
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed("seed_workspace_generated", "workspace_tasks_fixture", "Workspace.", ("workspace_task_creation",))
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        record = {
            "candidate_id": "workspace_tasks_b001_incomplete",
            "instruction": "Create a launch task.",
            "task_type": "workspace_task_creation",
            "difficulty": {"level": "medium", "tool_count": 2, "constraint_count": 2, "state_changes": 1, "ambiguity": "none", "recovery_paths": 0},
            "required_capabilities": ["workspace_task_creation"],
            "required_tools": ["search_workspace_items", "create_workspace_task"],
            "primary_tool": "search_workspace_items",
            "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
            "final_answer_contains": "task_launch",
            "expected_state": [{"check_type": "workspace_task", "expected": {"title": "Launch"}}],
        }
        with self.assertRaises(Exception):
            parse_domain_task_contracts(
                {"task_contracts": [record]}, seed=seed, spec=bundle.generation_spec,
                batch_context=build_generation_batch_context(
                    bundle.generation_spec,
                    batch_index=1,
                ),
                generation_lineage={},
            )

    def test_read_only_task_cannot_add_registered_mutating_tool(self) -> None:
        from synthesis.domain_generation import (
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import foundation_seed

        seed = foundation_seed()
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        record = self._provider_record("contacts_b001_smuggled_mutation")
        record["required_tools"] = ["lookup_contact_email", "record_contact_followup"]
        record["primary_tool"] = "record_contact_followup"
        record["primary_arguments"] = {"name": "Alice Zhang", "note": "Follow up."}
        with self.assertRaises(Exception):
            parse_domain_task_contracts(
                {"task_contracts": [record]}, seed=seed,
                spec=bundle.generation_spec,
                batch_context=build_generation_batch_context(
                    bundle.generation_spec,
                    batch_index=1,
                ),
                generation_lineage={},
            )
