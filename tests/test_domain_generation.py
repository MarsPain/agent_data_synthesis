from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


def _first_grounding_example(entries, task_type_spec):
    for entry in entries:
        observation = entry.get("observation") if isinstance(entry, dict) else None
        if not isinstance(observation, dict):
            continue
        for field in task_type_spec.final_answer_fields:
            value = observation.get(field)
            if isinstance(value, str) and value:
                return {"field": field, "value": value}
    return None


def _windowed_entries(spec, batch_index: int):
    entries = next(iter(spec.grounding_context.values()))
    window = spec.grounding_window_size
    if window is None:
        return list(entries)
    count = len(entries)
    start = ((batch_index - 1) * window) % count
    return [entries[(start + offset) % count] for offset in range(window)]


class AxisAwareBatchClient:
    """Deterministic fake provider for batch-axis tests.

    Reads the focused task type, grounding window, and diversity contract from
    each rendered prompt and emits distinct, fully compliant records: grounded
    final answers for primary-observation types, the sentinel for derived
    types, and schema-conformant expected-state arguments with grounded
    reference values. An optional ``mutate`` hook receives
    ``(batch_index, records)`` and may replace the records to inject failures.
    """

    def __init__(self, mutate=None) -> None:
        self.payloads: list[dict[str, object]] = []
        self.prompts: list[str] = []
        self._mutate = mutate

    def generate_json(self, prompt: str, *, role: str):
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL
        from synthesis.llm import LLMGenerationResult

        payload = json.loads(prompt)
        self.prompts.append(prompt)
        self.payloads.append(payload)
        count = payload["requested_candidate_count"]
        batch_index = payload["batch_context"]["batch_index"]
        prefix = payload["batch_context"]["candidate_id_prefix"]
        task_type = payload["task_types"][0]
        final_answer_contract = task_type["final_answer"]
        expected_state_contract = payload["output_contract"]["task_type_contracts"][0][
            "expected_state"
        ]
        entries = next(iter(payload["grounding_context"].values()))
        records = []
        for index in range(count):
            candidate_id = f"{prefix}task_{index:02d}"
            entry = entries[index % len(entries)]
            if final_answer_contract.get("value_contract") == "sentinel":
                final_answer = DERIVED_FINAL_ANSWER_SENTINEL
            else:
                field = final_answer_contract["allowed_fields"][0]
                final_answer = entry["observation"][field]
            expected_state = []
            if expected_state_contract["mode"] == "required":
                reference_fields = expected_state_contract.get("reference_fields", {})
                grounding_bindings = {
                    binding["state_field"]: binding
                    for binding in expected_state_contract.get("grounding_bindings", [])
                }
                for item in expected_state_contract["exact_items"]:
                    expected = {}
                    for prop in item["expected_schema"]["properties"]:
                        binding = grounding_bindings.get(prop)
                        if binding is not None:
                            observation_value = entry["observation"][
                                binding["observation_field"]
                            ]
                            expected[prop] = (
                                observation_value
                                if binding["match"] == "exact"
                                else f"{prop}_{candidate_id}: {observation_value}"
                            )
                        elif prop in reference_fields:
                            expected[prop] = entry["observation"][
                                reference_fields[prop]
                            ]
                        else:
                            expected[prop] = f"{prop}_{candidate_id}"
                    expected_state.append(
                        {"check_type": item["check_type"], "expected": expected}
                    )
            records.append(
                {
                    "candidate_id": candidate_id,
                    "instruction": f"Execute grounded task {candidate_id}.",
                    "task_type": task_type["task_type"],
                    "difficulty": {
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    "required_capabilities": task_type["required_capabilities"],
                    "required_tools": task_type["required_tools"],
                    "primary_tool": task_type["required_tools"][0],
                    "primary_arguments": dict(entry["primary_arguments"]),
                    "final_answer_contains": final_answer,
                    "expected_state": expected_state,
                }
            )
        if self._mutate is not None:
            records = self._mutate(batch_index, records)
        return LLMGenerationResult(
            content={"task_contracts": records},
            lineage={"role": role, "retry_count": 0},
        )


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
            grounding_context={
                "contacts": [
                    {
                        "primary_arguments": {"name": "Alice Zhang"},
                        "observation": {
                            "name": "Alice Zhang",
                            "email": "alice.zhang@example.test",
                        },
                    }
                ]
            },
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
            DERIVED_FINAL_ANSWER_SENTINEL,
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
                    tools_by_name = {tool["name"]: tool for tool in spec.tools}
                    for type_index, task_type_spec in enumerate(spec.task_types):
                        prompt = json.loads(
                            build_domain_generation_prompt(
                                spec,
                                requested_candidate_count=1,
                                batch_context=build_generation_batch_context(
                                    spec,
                                    batch_index=type_index + 1,
                                ),
                            )
                        )
                        self.assertEqual(
                            [item["task_type"] for item in prompt["task_types"]],
                            [task_type_spec.task_type],
                        )
                        prompt_task_types = {
                            item["task_type"]: item
                            for item in prompt["output_contract"]["task_type_contracts"]
                        }
                        self.assertEqual(
                            sorted(prompt_task_types),
                            [task_type_spec.task_type],
                        )
                        self.assertTrue(task_type_spec.required_capabilities)
                        self.assertTrue(task_type_spec.final_answer_fields)
                        expected_state = prompt_task_types[
                            task_type_spec.task_type
                        ]["expected_state"]
                        expected_final_answer: dict[str, object] = {
                            "source": task_type_spec.final_answer_source,
                            "allowed_fields": list(task_type_spec.final_answer_fields),
                            "invented_text_allowed": False,
                        }
                        if task_type_spec.final_answer_derivation is not None:
                            expected_final_answer["value_contract"] = "sentinel"
                            expected_final_answer["sentinel"] = (
                                DERIVED_FINAL_ANSWER_SENTINEL
                            )
                        else:
                            example = _first_grounding_example(
                                _windowed_entries(spec, type_index + 1),
                                task_type_spec,
                            )
                            if example is not None:
                                expected_final_answer["example"] = example
                        self.assertEqual(
                            prompt_task_types[task_type_spec.task_type]["final_answer"],
                            expected_final_answer,
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
                "example": {"field": "email", "value": "alice.zhang@example.test"},
            },
        )
        self.assertIsNone(task_type_contract["expected_state_tool"])
        self.assertIn(
            "copy task_type, required_tools, and primary_tool exactly",
            json.loads(first)["instructions"],
        )
        self.assertIn(
            "substring copied from the observation value",
            json.loads(first)["instructions"].lower(),
        )
        self.assertIn(
            "copying the field name itself is forbidden",
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
            "invalid_final_answer": (
                {"task_contracts": [{**valid, "final_answer_contains": "email"}]},
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

    def test_domain_batch_policies_generate_thirty_axis_compliant_candidates(self) -> None:
        from synthesis.domain_generation import (
            generate_domain_llm_candidates,
            grounding_context_hash,
            sanitized_generation_spec_metadata,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed, foundation_seed

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
                    spec = bundle.generation_spec
                    client = AxisAwareBatchClient()
                    result = generate_domain_llm_candidates(
                        seed,
                        client,
                        spec=spec,
                        target_candidate_count=30,
                    )
                    sizes = expected_sizes[bundle.domain_id]
                    self.assertEqual(
                        [payload["requested_candidate_count"] for payload in client.payloads],
                        sizes,
                    )
                    full_entries = next(iter(spec.grounding_context.values()))
                    emitted_so_far: list[str] = []
                    for batch_index, payload in enumerate(client.payloads, start=1):
                        focused = spec.task_types[(batch_index - 1) % len(spec.task_types)]
                        self.assertEqual(
                            [item["task_type"] for item in payload["task_types"]],
                            [focused.task_type],
                        )
                        self.assertEqual(
                            [
                                item["task_type"]
                                for item in payload["output_contract"]["task_type_contracts"]
                            ],
                            [focused.task_type],
                        )
                        rendered = next(iter(payload["grounding_context"].values()))
                        self.assertEqual(rendered, _windowed_entries(spec, batch_index))
                        self.assertLessEqual(len(rendered), len(full_entries))
                        expected_excluded = emitted_so_far[-20:]
                        diversity = payload["diversity_contract"]
                        self.assertEqual(
                            diversity["excluded_instructions"],
                            expected_excluded,
                        )
                        self.assertIn(
                            "do not repeat or paraphrase",
                            diversity["rule"],
                        )
                        prefix = payload["batch_context"]["candidate_id_prefix"]
                        safe_domain = bundle.domain_id.removesuffix("_fixture")
                        self.assertEqual(prefix, f"{safe_domain}_b{batch_index:03d}_")
                        emitted_so_far.extend(
                            f"Execute grounded task {prefix}task_{index:02d}."
                            for index in range(payload["requested_candidate_count"])
                        )
                    self.assertGreater(len(set(client.prompts)), 1)
                    self.assertEqual(result.target_candidate_count, 30)
                    self.assertEqual(result.generated_candidate_count, 30)
                    self.assertEqual(result.provider_call_count, len(sizes))
                    self.assertEqual(
                        len({candidate.candidate_id for candidate in result.candidates}),
                        30,
                    )
                    per_type = 30 // len(spec.task_types)
                    type_counts: dict[str, int] = {}
                    for candidate in result.candidates:
                        task_type = str(candidate.constraints["task_type"])
                        type_counts[task_type] = type_counts.get(task_type, 0) + 1
                    self.assertEqual(
                        type_counts,
                        {item.task_type: per_type for item in spec.task_types},
                    )
                    fields_by_type = {
                        item.task_type: item.final_answer_fields
                        for item in spec.task_types
                    }
                    safe_domain = bundle.domain_id.removesuffix("_fixture")
                    for candidate in result.candidates:
                        task_type = str(candidate.constraints["task_type"])
                        self.assertNotIn(
                            candidate.expected_answer,
                            fields_by_type[task_type],
                        )
                        batch = int(
                            candidate.candidate_id.removeprefix(f"{safe_domain}_b")[:3]
                        )
                        lineage = candidate.generation_lineage or {}
                        self.assertEqual(
                            lineage.get("excluded_instruction_count"),
                            min((batch - 1) * sizes[0], 20),
                        )
                        self.assertNotIn("excluded_instructions", lineage)
                        if task_type != "workspace_task_creation" and task_type != (
                            "workspace_comment_update"
                        ):
                            grounded_values = [
                                value
                                for entry in full_entries
                                for field in fields_by_type[task_type]
                                for value in [entry["observation"].get(field)]
                                if isinstance(value, str)
                            ]
                            self.assertTrue(
                                any(
                                    candidate.expected_answer in value
                                    for value in grounded_values
                                ),
                                f"{candidate.candidate_id} not grounded",
                            )
                    if bundle.domain_id == "workspace_tasks_fixture":
                        derived_answers = {
                            candidate.expected_answer
                            for candidate in result.candidates
                            if str(candidate.constraints["task_type"])
                            in {"workspace_task_creation", "workspace_comment_update"}
                        }
                        self.assertEqual(len(derived_answers), 20)
                    self.assertEqual(
                        result.spec_metadata,
                        sanitized_generation_spec_metadata(spec),
                    )
                    self.assertEqual(
                        result.spec_metadata["grounding_context_hash"],
                        grounding_context_hash(spec),
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

    def test_grounding_gates_are_fail_closed_and_sanitized(self) -> None:
        from synthesis.datasets import assemble_generation_stage_rejection
        from synthesis.domain_generation import generate_domain_llm_candidates
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.llm import LLMProviderError
        from synthesis.seeds import DomainSeed, foundation_seed

        def replace_final_answer(value: str):
            def mutate(batch_index: int, records: list[dict]) -> list[dict]:
                if batch_index == 2:
                    records[0]["final_answer_contains"] = value
                return records

            return mutate

        def replace_mobile_reference(batch_index: int, records: list[dict]) -> list[dict]:
            if batch_index == 2:
                for item in records[0]["expected_state"]:
                    if "source_message_id" in item["expected"]:
                        item["expected"]["source_message_id"] = "msg_ungrounded_zzz"
            return records

        cases = (
            (
                "field_name_literal",
                foundation_seed(),
                replace_final_answer("email"),
                "invalid_final_answer",
                "final_answer_field_name_literal",
                None,
            ),
            (
                "ungrounded_final_answer",
                foundation_seed(),
                replace_final_answer("ungrounded_value_zzz"),
                "invalid_final_answer",
                "final_answer_not_grounded",
                "ungrounded_value_zzz",
            ),
            (
                "sentinel_mismatch",
                DomainSeed(
                    "seed_workspace_fail", "workspace_tasks_fixture", "Workspace.", ("search",)
                ),
                replace_final_answer("task_hardcoded_zzz"),
                "invalid_final_answer",
                "final_answer_sentinel_mismatch",
                "task_hardcoded_zzz",
            ),
            (
                "ungrounded_reference",
                DomainSeed(
                    "seed_mobile_fail", "mobile_messages_fixture", "Mobile.", ("search",)
                ),
                replace_mobile_reference,
                "invalid_expected_state",
                "expected_state_reference_not_grounded",
                "msg_ungrounded_zzz",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for name, seed, mutate, reason, detail, injected in cases:
                with self.subTest(gate=name):
                    bundle = build_domain_pipeline_bundle(seed, Path(tmp) / name)
                    client = AxisAwareBatchClient(mutate=mutate)
                    with self.assertRaises(LLMProviderError) as raised:
                        generate_domain_llm_candidates(
                            seed,
                            client,
                            spec=bundle.generation_spec,
                            target_candidate_count=30,
                        )
                    error = raised.exception
                    self.assertEqual(error.cause, "llm_response_schema_error")
                    self.assertEqual(error.schema_reason, reason)
                    self.assertEqual(error.schema_detail, detail)
                    self.assertEqual(error.lineage["batch_index"], 2)
                    self.assertEqual(len(client.payloads), 2)
                    persisted = json.dumps(
                        assemble_generation_stage_rejection(error=error),
                        sort_keys=True,
                    )
                    safe_domain = bundle.domain_id.removesuffix("_fixture")
                    markers = [
                        "Execute grounded task",
                        f"{safe_domain}_b001_",
                        f"{safe_domain}_b002_",
                    ]
                    if injected is not None:
                        markers.append(injected)
                    for marker in markers:
                        self.assertNotIn(marker, persisted)

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


class FinalAnswerDerivationTest(unittest.TestCase):
    def _workspace_bundle(self, tmp_path: Path):
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            "seed_workspace_derivation",
            "workspace_tasks_fixture",
            "Workspace derivation.",
            ("workspace_task_creation",),
        )
        return seed, build_domain_pipeline_bundle(seed, Path(tmp_path))

    def _workspace_record(
        self,
        task_type: str,
        *,
        final_answer: str,
        expected_state: list[dict[str, object]],
    ) -> dict[str, object]:
        capabilities = {
            "workspace_task_creation": ["workspace_search", "workspace_task_creation"],
            "workspace_comment_update": ["workspace_search", "workspace_comment_update"],
        }
        tools = {
            "workspace_task_creation": ["search_workspace_items", "create_workspace_task"],
            "workspace_comment_update": ["search_workspace_items", "add_workspace_comment"],
        }
        return {
            "candidate_id": f"workspace_tasks_b001_{task_type}",
            "instruction": "Run the grounded workspace mutation.",
            "task_type": task_type,
            "difficulty": {
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "required_capabilities": capabilities[task_type],
            "required_tools": tools[task_type],
            "primary_tool": "search_workspace_items",
            "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
            "final_answer_contains": final_answer,
            "expected_state": expected_state,
        }

    def test_shared_stable_id_primitive_rules(self) -> None:
        from synthesis.stable_ids import stable_id

        self.assertEqual(stable_id("Prepare Launch Checklist!"), "prepare_launch_checklist")
        self.assertEqual(stable_id("  spaced value  "), "spaced_value")
        self.assertEqual(stable_id("Already_Good-1"), "already_good_1")

    def test_workspace_spec_declares_exact_derivation_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, bundle = self._workspace_bundle(tmp)
        self.assertIsNotNone(bundle.generation_spec)
        templates = {
            item.task_type: item.final_answer_derivation
            for item in bundle.generation_spec.task_types
        }
        self.assertEqual(
            templates,
            {
                "workspace_item_search": None,
                "workspace_task_creation": "task_{title|stable_id}",
                "workspace_comment_update": "comment_{task_id}_{comment|stable_id}",
            },
        )

    def test_derivation_templates_are_validated_against_spec_contract(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationSpec,
            DomainTaskTypeSpec,
            validate_domain_generation_spec,
        )

        tools = (
            {
                "name": "search_items",
                "version": "tool_search_items_v1",
                "schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "side_effects": "read_only",
            },
            {
                "name": "mutate_item",
                "version": "tool_mutate_item_v1",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
                "side_effects": "state_mutating",
            },
        )

        def spec_with(task_type: DomainTaskTypeSpec) -> DomainGenerationSpec:
            return DomainGenerationSpec(
                schema_version="domain_generation_spec_v1",
                domain_id="workspace_tasks_fixture",
                task_types=(task_type,),
                tools=tools,
                grounding_context={
                    "items": [
                        {
                            "primary_arguments": {"query": "alpha"},
                            "observation": {"item_id": "item_alpha"},
                        }
                    ]
                },
                context_policy="synthetic_fixture",
                max_candidates_per_call=5,
            )

        base = {
            "task_type": "custom_mutation",
            "required_tools": ("search_items", "mutate_item"),
            "allowed_expected_state_checks": ("workspace_task",),
            "required_capabilities": ("custom_mutation",),
            "expected_state_tool": "mutate_item",
            "final_answer_fields": ("item_id",),
        }
        invalid_specs = (
            spec_with(DomainTaskTypeSpec(**base, final_answer_derivation="item_{title|stable_id}")),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="",
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="item_{unknown_field}",
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="item_{title|upper}",
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="item_{title",
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="item_static",
                )
            ),
        )
        for spec in invalid_specs:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_domain_generation_spec(spec)
        validate_domain_generation_spec(
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    final_answer_source="state_tool_observation",
                    final_answer_derivation="item_{title|stable_id}_{note}",
                )
            )
        )

    def test_sentinel_record_derives_task_and_comment_ids(self) -> None:
        from synthesis.domain_generation import (
            DERIVED_FINAL_ANSWER_SENTINEL,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        with tempfile.TemporaryDirectory() as tmp:
            seed, bundle = self._workspace_bundle(tmp)
        spec = bundle.generation_spec
        context = build_generation_batch_context(spec, batch_index=1)
        task_record = self._workspace_record(
            "workspace_task_creation",
            final_answer=DERIVED_FINAL_ANSWER_SENTINEL,
            expected_state=[
                {
                    "check_type": "workspace_task",
                    "expected": {
                        "project_id": "project_alpha",
                        "title": "Prepare Launch Checklist!",
                        "priority": "high",
                        "due_label": "this_week",
                    },
                }
            ],
        )
        comment_record = self._workspace_record(
            "workspace_comment_update",
            final_answer=DERIVED_FINAL_ANSWER_SENTINEL,
            expected_state=[
                {
                    "check_type": "workspace_comment",
                    "expected": {
                        "task_id": "task_launch_plan",
                        "comment": "Assign Owner: QA Team",
                    },
                }
            ],
        )
        contracts = parse_domain_task_contracts(
            {"task_contracts": [task_record, comment_record]},
            seed=seed,
            spec=spec,
            batch_context=context,
            generation_lineage={},
        )
        self.assertEqual(
            contracts[0].expected_outcome.final_answer_contains,
            "task_prepare_launch_checklist",
        )
        self.assertEqual(
            contracts[1].expected_outcome.final_answer_contains,
            "comment_task_launch_plan_assign_owner__qa_team",
        )

    def test_non_sentinel_value_fails_with_sentinel_mismatch(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        with tempfile.TemporaryDirectory() as tmp:
            seed, bundle = self._workspace_bundle(tmp)
        spec = bundle.generation_spec
        record = self._workspace_record(
            "workspace_task_creation",
            final_answer="task_prepare_launch_checklist",
            expected_state=[
                {
                    "check_type": "workspace_task",
                    "expected": {
                        "project_id": "project_alpha",
                        "title": "Prepare Launch Checklist!",
                        "priority": "high",
                        "due_label": "this_week",
                    },
                }
            ],
        )
        with self.assertRaises(DomainGenerationValidationError) as raised:
            parse_domain_task_contracts(
                {"task_contracts": [record]},
                seed=seed,
                spec=spec,
                batch_context=build_generation_batch_context(spec, batch_index=1),
                generation_lineage={},
            )
        self.assertEqual(raised.exception.reason, "invalid_final_answer")
        self.assertEqual(raised.exception.detail, "final_answer_sentinel_mismatch")

    def test_derivation_failure_fails_closed(self) -> None:
        from synthesis.domain_generation import (
            DERIVED_FINAL_ANSWER_SENTINEL,
            DomainGenerationSpec,
            DomainGenerationValidationError,
            DomainTaskTypeSpec,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )
        from synthesis.seeds import DomainSeed

        spec = DomainGenerationSpec(
            schema_version="domain_generation_spec_v1",
            domain_id="workspace_tasks_fixture",
            task_types=(
                DomainTaskTypeSpec(
                    task_type="custom_mutation",
                    required_tools=("search_items", "mutate_item"),
                    allowed_expected_state_checks=("workspace_task",),
                    required_capabilities=("custom_mutation",),
                    expected_state_tool="mutate_item",
                    final_answer_source="state_tool_observation",
                    final_answer_fields=("item_id",),
                    final_answer_derivation="item_{note|stable_id}",
                ),
            ),
            tools=(
                {
                    "name": "search_items",
                    "version": "tool_search_items_v1",
                    "schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    "side_effects": "read_only",
                },
                {
                    "name": "mutate_item",
                    "version": "tool_mutate_item_v1",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["title"],
                        "additionalProperties": False,
                    },
                    "side_effects": "state_mutating",
                },
            ),
            grounding_context={
                "items": [
                    {
                        "primary_arguments": {"query": "alpha"},
                        "observation": {"item_id": "item_alpha"},
                    }
                ]
            },
            context_policy="synthetic_fixture",
            max_candidates_per_call=5,
        )
        record = {
            "candidate_id": "workspace_tasks_b001_derivation_failure",
            "instruction": "Mutate the alpha item.",
            "task_type": "custom_mutation",
            "difficulty": {"level": "medium", "tool_count": 2},
            "required_capabilities": ["custom_mutation"],
            "required_tools": ["search_items", "mutate_item"],
            "primary_tool": "search_items",
            "primary_arguments": {"query": "alpha"},
            "final_answer_contains": DERIVED_FINAL_ANSWER_SENTINEL,
            "expected_state": [
                {"check_type": "workspace_task", "expected": {"title": "Alpha"}}
            ],
        }
        with self.assertRaises(DomainGenerationValidationError) as raised:
            parse_domain_task_contracts(
                {"task_contracts": [record]},
                seed=DomainSeed(
                    "seed_workspace_derivation",
                    "workspace_tasks_fixture",
                    "Workspace derivation.",
                    ("custom_mutation",),
                ),
                spec=spec,
                batch_context=build_generation_batch_context(spec, batch_index=1),
                generation_lineage={},
            )
        self.assertEqual(raised.exception.reason, "invalid_final_answer")
        self.assertEqual(raised.exception.detail, "final_answer_derivation_failed")

    def test_prompt_renders_sentinel_contract_for_derived_types(self) -> None:
        from synthesis.domain_generation import (
            DERIVED_FINAL_ANSWER_SENTINEL,
            build_domain_generation_prompt,
            build_generation_batch_context,
        )

        with tempfile.TemporaryDirectory() as tmp:
            _, bundle = self._workspace_bundle(tmp)
        spec = bundle.generation_spec
        prompt = json.loads(
            build_domain_generation_prompt(
                spec,
                requested_candidate_count=1,
                batch_context=build_generation_batch_context(spec, batch_index=2),
            )
        )
        task_types = {item["task_type"]: item for item in prompt["task_types"]}
        derived = task_types["workspace_task_creation"]["final_answer"]
        self.assertEqual(derived["value_contract"], "sentinel")
        self.assertEqual(derived["sentinel"], DERIVED_FINAL_ANSWER_SENTINEL)
        contract_blocks = {
            item["task_type"]: item
            for item in prompt["output_contract"]["task_type_contracts"]
        }
        self.assertEqual(
            contract_blocks["workspace_task_creation"]["final_answer"]["value_contract"],
            "sentinel",
        )


class FinalAnswerGroundingTest(unittest.TestCase):
    def _domain_cases(self, tmp: str) -> dict[str, dict[str, object]]:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed, foundation_seed

        difficulty = {
            "level": "easy",
            "tool_count": 1,
            "constraint_count": 1,
            "state_changes": 0,
            "ambiguity": "none",
            "recovery_paths": 0,
        }
        contacts_seed = foundation_seed()
        contacts = build_domain_pipeline_bundle(contacts_seed, Path(tmp) / "contacts")
        mobile_seed = DomainSeed(
            "seed_mobile_grounding",
            "mobile_messages_fixture",
            "Mobile grounding.",
            ("mobile_message_search",),
        )
        mobile = build_domain_pipeline_bundle(mobile_seed, Path(tmp) / "mobile")
        workspace_seed = DomainSeed(
            "seed_workspace_grounding",
            "workspace_tasks_fixture",
            "Workspace grounding.",
            ("workspace_item_search",),
        )
        workspace = build_domain_pipeline_bundle(workspace_seed, Path(tmp) / "workspace")
        return {
            "contacts_fixture": {
                "seed": contacts_seed,
                "spec": contacts.generation_spec,
                "record": {
                    "candidate_id": "contacts_b001_lookup",
                    "instruction": "Find Alice Zhang's email address.",
                    "task_type": "contact_lookup",
                    "difficulty": difficulty,
                    "required_capabilities": ["contact_lookup"],
                    "required_tools": ["lookup_contact_email"],
                    "primary_tool": "lookup_contact_email",
                    "primary_arguments": {"name": "Alice Zhang"},
                    "final_answer_contains": "alice.zhang@example.test",
                    "expected_state": [],
                },
                "field_literal": "email",
                "grounded_values": ("alice.zhang@example.test", "alice.zhang"),
                "example": {"field": "email", "value": "alice.zhang@example.test"},
            },
            "mobile_messages_fixture": {
                "seed": mobile_seed,
                "spec": mobile.generation_spec,
                "record": {
                    "candidate_id": "mobile_messages_b001_lookup",
                    "instruction": "Find Maya's project update message.",
                    "task_type": "mobile_message_search",
                    "difficulty": difficulty,
                    "required_capabilities": ["message_search"],
                    "required_tools": ["search_phone_messages"],
                    "primary_tool": "search_phone_messages",
                    "primary_arguments": {"query": "project update", "participant": "Maya"},
                    "final_answer_contains": "msg_maya_project_update",
                    "expected_state": [],
                },
                "field_literal": "snippet",
                "grounded_values": (
                    "msg_maya_project_update",
                    "remind me to send the project update",
                ),
                "example": {"field": "message_id", "value": "msg_maya_project_update"},
            },
            "workspace_tasks_fixture": {
                "seed": workspace_seed,
                "spec": workspace.generation_spec,
                "record": {
                    "candidate_id": "workspace_tasks_b001_lookup",
                    "instruction": "Find the Alpha Launch project.",
                    "task_type": "workspace_item_search",
                    "difficulty": difficulty,
                    "required_capabilities": ["workspace_search"],
                    "required_tools": ["search_workspace_items"],
                    "primary_tool": "search_workspace_items",
                    "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
                    "final_answer_contains": "project_alpha",
                    "expected_state": [],
                },
                "field_literal": "item_id",
                "grounded_values": ("project_alpha", "Alpha Launch (active)"),
                "example": {"field": "item_id", "value": "project_alpha"},
            },
        }

    def test_field_name_literal_fails_with_fixed_detail(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cases = self._domain_cases(tmp)
            for domain, case in cases.items():
                with self.subTest(domain=domain):
                    record = {**case["record"], "final_answer_contains": case["field_literal"]}
                    with self.assertRaises(DomainGenerationValidationError) as raised:
                        parse_domain_task_contracts(
                            {"task_contracts": [record]},
                            seed=case["seed"],
                            spec=case["spec"],
                            batch_context=build_generation_batch_context(
                                case["spec"],
                                batch_index=1,
                            ),
                            generation_lineage={},
                        )
                    self.assertEqual(raised.exception.reason, "invalid_final_answer")
                    self.assertEqual(
                        raised.exception.detail,
                        "final_answer_field_name_literal",
                    )

    def test_ungrounded_value_fails_with_fixed_detail(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationValidationError,
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cases = self._domain_cases(tmp)
            for domain, case in cases.items():
                with self.subTest(domain=domain):
                    record = {
                        **case["record"],
                        "final_answer_contains": "ungrounded_value_zzz",
                    }
                    with self.assertRaises(DomainGenerationValidationError) as raised:
                        parse_domain_task_contracts(
                            {"task_contracts": [record]},
                            seed=case["seed"],
                            spec=case["spec"],
                            batch_context=build_generation_batch_context(
                                case["spec"],
                                batch_index=1,
                            ),
                            generation_lineage={},
                        )
                    self.assertEqual(raised.exception.reason, "invalid_final_answer")
                    self.assertEqual(raised.exception.detail, "final_answer_not_grounded")

    def test_grounded_values_pass(self) -> None:
        from synthesis.domain_generation import (
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cases = self._domain_cases(tmp)
            for domain, case in cases.items():
                for value in case["grounded_values"]:
                    with self.subTest(domain=domain, value=value):
                        record = {**case["record"], "final_answer_contains": value}
                        contracts = parse_domain_task_contracts(
                            {"task_contracts": [record]},
                            seed=case["seed"],
                            spec=case["spec"],
                            batch_context=build_generation_batch_context(
                                case["spec"],
                                batch_index=1,
                            ),
                            generation_lineage={},
                        )
                        self.assertEqual(
                            contracts[0].expected_outcome.final_answer_contains,
                            value,
                        )

    def test_prompt_renders_grounded_rule_and_per_type_examples(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cases = self._domain_cases(tmp)
            for domain, case in cases.items():
                with self.subTest(domain=domain):
                    spec = case["spec"]
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
                    instructions = prompt["instructions"].lower()
                    self.assertIn("copying the field name itself is forbidden", instructions)
                    self.assertIn("substring copied from the observation value", instructions)
                    focused = prompt["task_types"][0]
                    self.assertEqual(
                        focused["final_answer"]["example"],
                        case["example"],
                    )
                    contract_block = prompt["output_contract"]["task_type_contracts"][0]
                    self.assertEqual(
                        contract_block["final_answer"]["example"],
                        case["example"],
                    )

    def test_derived_types_render_no_example(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )

        with tempfile.TemporaryDirectory() as tmp:
            case = self._domain_cases(tmp)["workspace_tasks_fixture"]
            spec = case["spec"]
            prompt = json.loads(
                build_domain_generation_prompt(
                    spec,
                    requested_candidate_count=1,
                    batch_context=build_generation_batch_context(spec, batch_index=2),
                )
            )
            for block in prompt["task_types"]:
                if block["task_type"] == "workspace_task_creation":
                    self.assertNotIn("example", block["final_answer"])


class ExpectedStateReferenceTest(unittest.TestCase):
    def _mobile_bundle(self, tmp: str):
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            "seed_mobile_reference",
            "mobile_messages_fixture",
            "Mobile reference grounding.",
            ("mobile_reminder_creation",),
        )
        return seed, build_domain_pipeline_bundle(seed, Path(tmp) / "mobile")

    def _workspace_bundle(self, tmp: str):
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            "seed_workspace_reference",
            "workspace_tasks_fixture",
            "Workspace reference grounding.",
            ("workspace_comment_update",),
        )
        return seed, build_domain_pipeline_bundle(seed, Path(tmp) / "workspace")

    def _mobile_reminder_record(self, source_message_id: str) -> dict[str, object]:
        return {
            "candidate_id": "mobile_messages_b001_reminder",
            "instruction": "Find Maya's project update and create a reminder.",
            "task_type": "mobile_reminder_creation",
            "difficulty": {"level": "medium", "tool_count": 2},
            "required_capabilities": ["message_search", "reminder_creation"],
            "required_tools": ["search_phone_messages", "create_phone_reminder"],
            "primary_tool": "search_phone_messages",
            "primary_arguments": {"query": "project update", "participant": "Maya"},
            "final_answer_contains": "msg_maya_project_update",
            "expected_state": [
                {
                    "check_type": "mobile_reminder",
                    "expected": {
                        "title": "Send the project update",
                        "due_at": "tomorrow 9 AM",
                        "source_message_id": source_message_id,
                    },
                }
            ],
        }

    def _mobile_draft_record(self, thread_id: str) -> dict[str, object]:
        return {
            "candidate_id": "mobile_messages_b001_draft",
            "instruction": "Find Alex's late message and draft a reply.",
            "task_type": "mobile_draft_reply",
            "difficulty": {"level": "medium", "tool_count": 2},
            "required_capabilities": ["message_search", "draft_reply"],
            "required_tools": ["search_phone_messages", "draft_message_reply"],
            "primary_tool": "search_phone_messages",
            "primary_arguments": {"query": "five minutes late", "participant": "Alex"},
            "final_answer_contains": "I will be five minutes late.",
            "expected_state": [
                {
                    "check_type": "mobile_draft_reply",
                    "expected": {
                        "thread_id": thread_id,
                        "body": "I will be five minutes late.",
                    },
                }
            ],
        }

    def _workspace_comment_record(self, task_id: str) -> dict[str, object]:
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL

        return {
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
                        "task_id": task_id,
                        "comment": "Assign the checklist owner.",
                    },
                }
            ],
        }

    def _parse(self, *, seed, spec, record):
        from synthesis.domain_generation import (
            build_generation_batch_context,
            parse_domain_task_contracts,
        )

        return parse_domain_task_contracts(
            {"task_contracts": [record]},
            seed=seed,
            spec=spec,
            batch_context=build_generation_batch_context(spec, batch_index=1),
            generation_lineage={},
        )

    def test_domain_specs_declare_reference_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, mobile = self._mobile_bundle(tmp)
            _, workspace = self._workspace_bundle(tmp + "_ws")
        mobile_refs = {
            item.task_type: item.expected_state_reference_fields
            for item in mobile.generation_spec.task_types
        }
        self.assertEqual(
            mobile_refs,
            {
                "mobile_message_search": (),
                "mobile_reminder_creation": (("source_message_id", "message_id"),),
                "mobile_draft_reply": (("thread_id", "thread_id"),),
            },
        )
        workspace_refs = {
            item.task_type: item.expected_state_reference_fields
            for item in workspace.generation_spec.task_types
        }
        self.assertEqual(
            workspace_refs,
            {
                "workspace_item_search": (),
                "workspace_task_creation": (),
                "workspace_comment_update": (("task_id", "item_id"),),
            },
        )

    def test_grounded_references_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mobile_seed, mobile = self._mobile_bundle(tmp)
            workspace_seed, workspace = self._workspace_bundle(tmp)
        reminder = self._mobile_reminder_record("msg_maya_project_update")
        draft = self._mobile_draft_record("thread_alex")
        comment = self._workspace_comment_record("task_launch_plan")
        self.assertEqual(
            self._parse(
                seed=mobile_seed, spec=mobile.generation_spec, record=reminder
            )[0].intent.task_type,
            "mobile_reminder_creation",
        )
        self.assertEqual(
            self._parse(
                seed=mobile_seed, spec=mobile.generation_spec, record=draft
            )[0].intent.task_type,
            "mobile_draft_reply",
        )
        contracts = self._parse(
            seed=workspace_seed, spec=workspace.generation_spec, record=comment
        )
        self.assertEqual(
            contracts[0].expected_outcome.final_answer_contains,
            "comment_task_launch_plan_assign_the_checklist_owner",
        )

    def test_ungrounded_references_fail_with_fixed_detail(self) -> None:
        from synthesis.domain_generation import DomainGenerationValidationError

        with tempfile.TemporaryDirectory() as tmp:
            mobile_seed, mobile = self._mobile_bundle(tmp)
            workspace_seed, workspace = self._workspace_bundle(tmp)
            cases = (
                (mobile_seed, mobile.generation_spec, self._mobile_reminder_record("msg_invented")),
                (mobile_seed, mobile.generation_spec, self._mobile_draft_record("thread_invented")),
                (workspace_seed, workspace.generation_spec, self._workspace_comment_record("task_invented")),
            )
            for seed, spec, record in cases:
                with self.subTest(record=record["task_type"]):
                    with self.assertRaises(DomainGenerationValidationError) as raised:
                        self._parse(seed=seed, spec=spec, record=record)
                    self.assertEqual(raised.exception.reason, "invalid_expected_state")
                    self.assertEqual(
                        raised.exception.detail,
                        "expected_state_reference_not_grounded",
                    )

    def test_undeclared_fields_remain_unchecked(self) -> None:
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL

        with tempfile.TemporaryDirectory() as tmp:
            workspace_seed, workspace = self._workspace_bundle(tmp)
        record = {
            "candidate_id": "workspace_tasks_b001_create",
            "instruction": "Create a launch follow-up task.",
            "task_type": "workspace_task_creation",
            "difficulty": {"level": "medium", "tool_count": 2},
            "required_capabilities": ["workspace_search", "workspace_task_creation"],
            "required_tools": ["search_workspace_items", "create_workspace_task"],
            "primary_tool": "search_workspace_items",
            "primary_arguments": {"query": "Alpha Launch", "kind": "project"},
            "final_answer_contains": DERIVED_FINAL_ANSWER_SENTINEL,
            "expected_state": [
                {
                    "check_type": "workspace_task",
                    "expected": {
                        "project_id": "project_not_in_grounding",
                        "title": "Prepare launch checklist",
                        "priority": "high",
                        "due_label": "this_week",
                    },
                }
            ],
        }
        contracts = self._parse(
            seed=workspace_seed, spec=workspace.generation_spec, record=record
        )
        self.assertEqual(
            contracts[0].expected_outcome.final_answer_contains,
            "task_prepare_launch_checklist",
        )

    def test_reference_fields_are_validated_against_spec_contract(self) -> None:
        from synthesis.domain_generation import (
            DomainGenerationSpec,
            DomainTaskTypeSpec,
            validate_domain_generation_spec,
        )

        tools = (
            {
                "name": "search_items",
                "version": "tool_search_items_v1",
                "schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "side_effects": "read_only",
            },
            {
                "name": "mutate_item",
                "version": "tool_mutate_item_v1",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
                "side_effects": "state_mutating",
            },
        )

        def spec_with(task_type: DomainTaskTypeSpec) -> DomainGenerationSpec:
            return DomainGenerationSpec(
                schema_version="domain_generation_spec_v1",
                domain_id="workspace_tasks_fixture",
                task_types=(task_type,),
                tools=tools,
                grounding_context={
                    "items": [
                        {
                            "primary_arguments": {"query": "alpha"},
                            "observation": {"item_id": "item_alpha"},
                        }
                    ]
                },
                context_policy="synthetic_fixture",
                max_candidates_per_call=5,
            )

        base = {
            "task_type": "custom_mutation",
            "required_tools": ("search_items", "mutate_item"),
            "allowed_expected_state_checks": ("workspace_task",),
            "required_capabilities": ("custom_mutation",),
            "expected_state_tool": "mutate_item",
            "final_answer_source": "state_tool_observation",
            "final_answer_fields": ("item_id",),
            "final_answer_derivation": "item_{title|stable_id}",
        }
        invalid_specs = (
            spec_with(
                DomainTaskTypeSpec(
                    task_type="read_only_refs",
                    required_tools=("search_items",),
                    required_capabilities=("custom_mutation",),
                    final_answer_fields=("item_id",),
                    expected_state_reference_fields=(("title", "item_id"),),
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    expected_state_reference_fields=(("unknown_field", "item_id"),),
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    expected_state_reference_fields=(("not a field", "item_id"),),
                )
            ),
            spec_with(
                DomainTaskTypeSpec(
                    **base,
                    expected_state_reference_fields=(
                        ("title", "item_id"),
                        ("title", "item_id"),
                    ),
                )
            ),
        )
        for spec in invalid_specs:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_domain_generation_spec(spec)

    def test_prompt_renders_reference_contract(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )

        with tempfile.TemporaryDirectory() as tmp:
            _, mobile = self._mobile_bundle(tmp)
        spec = mobile.generation_spec
        prompt = json.loads(
            build_domain_generation_prompt(
                spec,
                requested_candidate_count=1,
                batch_context=build_generation_batch_context(spec, batch_index=2),
            )
        )
        self.assertIn("reference", prompt["instructions"].lower())
        reminder = next(
            item
            for item in prompt["output_contract"]["task_type_contracts"]
            if item["task_type"] == "mobile_reminder_creation"
        )
        self.assertEqual(
            reminder["expected_state"]["reference_fields"],
            {"source_message_id": "message_id"},
        )


class ContactsFixtureWindowTest(unittest.TestCase):
    def test_contacts_grounding_window_rotates_across_six_entries(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            build_generation_batch_context,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmp))
        spec = bundle.generation_spec
        full_entries = next(iter(spec.grounding_context.values()))
        self.assertEqual(len(full_entries), 6)
        self.assertEqual(spec.grounding_window_size, 2)
        windows = []
        for batch_index in (1, 2, 3, 4):
            prompt = json.loads(
                build_domain_generation_prompt(
                    spec,
                    requested_candidate_count=1,
                    batch_context=build_generation_batch_context(
                        spec,
                        batch_index=batch_index,
                    ),
                )
            )
            windows.append(
                [
                    entry["observation"]["email"]
                    for entry in next(iter(prompt["grounding_context"].values()))
                ]
            )
        self.assertEqual(
            windows,
            [
                ["alice.zhang@example.test", "ben.carter@example.test"],
                ["carla.diaz@example.test", "david.kim@example.test"],
                ["elena.petrova@example.test", "frank.osei@example.test"],
                ["alice.zhang@example.test", "ben.carter@example.test"],
            ],
        )
