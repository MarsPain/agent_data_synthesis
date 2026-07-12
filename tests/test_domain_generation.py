from __future__ import annotations

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
            max_candidates_per_call=20,
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
            replace(valid, max_candidates_per_call=21),
        )
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_domain_generation_spec(spec)

    def test_every_domain_bundle_owns_a_matching_generation_spec(self) -> None:
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

    def _provider_record(self, candidate_id: str = "candidate_contacts_generated"):
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

    def test_prompt_and_provider_parser_enforce_domain_contract(self) -> None:
        from synthesis.domain_generation import (
            build_domain_generation_prompt,
            parse_domain_task_contracts,
        )
        from synthesis.seeds import foundation_seed
        from synthesis.task_contracts import candidate_from_task_contract

        spec = self._valid_spec()
        first = build_domain_generation_prompt(spec, requested_candidate_count=1)
        second = build_domain_generation_prompt(spec, requested_candidate_count=1)
        self.assertEqual(first, second)
        self.assertIn("contacts_fixture", first)
        self.assertIn("lookup_contact_email", first)
        self.assertIn('"requested_candidate_count":1', first)
        self.assertNotIn("AGENT_DATA", first)
        self.assertNotIn("Authorization", first)

        contracts = parse_domain_task_contracts(
            {"task_contracts": [self._provider_record()]},
            seed=foundation_seed(),
            spec=spec,
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
                    generation_lineage={},
                )

    def test_bounded_generation_fulfills_exact_targets(self) -> None:
        import json
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
                offset = sum(self.requested[:-1])
                return LLMGenerationResult(
                    content={
                        "task_contracts": [
                            self_record(f"candidate_contacts_{offset + index:03d}")
                            for index in range(count)
                        ]
                    },
                    lineage={"role": role, "provider_host": "llm.example.test", "retry_count": 0},
                )

        self_record = self._provider_record
        for target, expected_calls in ((1, [1]), (20, [20]), (21, [20, 1]), (45, [20, 20, 5])):
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
        from synthesis.domain_generation import parse_domain_task_contracts
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
            "candidate_id": "candidate_mobile_generated_reminder",
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
                spec=bundle.generation_spec, generation_lineage={},
            )

    def test_rejects_state_contract_that_cannot_call_mutating_tool(self) -> None:
        from synthesis.domain_generation import parse_domain_task_contracts
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        seed = DomainSeed("seed_workspace_generated", "workspace_tasks_fixture", "Workspace.", ("workspace_task_creation",))
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        record = {
            "candidate_id": "candidate_workspace_incomplete",
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
                generation_lineage={},
            )

    def test_read_only_task_cannot_add_registered_mutating_tool(self) -> None:
        from synthesis.domain_generation import parse_domain_task_contracts
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import foundation_seed

        seed = foundation_seed()
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
        record = self._provider_record("candidate_contacts_smuggled_mutation")
        record["required_tools"] = ["lookup_contact_email", "record_contact_followup"]
        record["primary_tool"] = "record_contact_followup"
        record["primary_arguments"] = {"name": "Alice Zhang", "note": "Follow up."}
        with self.assertRaises(Exception):
            parse_domain_task_contracts(
                {"task_contracts": [record]}, seed=seed,
                spec=bundle.generation_spec, generation_lineage={},
            )
