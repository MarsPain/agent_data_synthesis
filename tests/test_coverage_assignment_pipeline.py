from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AssignmentAwareFakeProvider:
    def __init__(
        self,
        *,
        mismatch_first_assignment: bool = False,
        inject_assignment_field: bool = False,
        violate_grounding_scope: bool = False,
        violate_cross_step_binding: bool = False,
    ) -> None:
        self.payloads: list[dict[str, object]] = []
        self._mismatch_first_assignment = mismatch_first_assignment
        self._inject_assignment_field = inject_assignment_field
        self._violate_grounding_scope = violate_grounding_scope
        self._violate_cross_step_binding = violate_cross_step_binding

    def generate_json(self, prompt: str, *, role: str):
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL
        from synthesis.llm import LLMGenerationResult

        payload = json.loads(prompt)
        self.payloads.append(payload)
        assignment = payload["coverage_assignment"]
        task_type = payload["task_types"][0]
        if self._mismatch_first_assignment and len(self.payloads) == 1:
            task_type = {
                "task_type": "contact_lookup",
                "required_tools": ["lookup_contact_email"],
                "required_capabilities": ["contact_lookup"],
                "allowed_expected_state_checks": [],
                "expected_state_tool": None,
                "final_answer": {
                    "source": "primary_observation",
                    "allowed_fields": ["email"],
                    "invented_text_allowed": False,
                },
            }
        entry = next(iter(payload["grounding_context"].values()))[0]
        candidate_id = (
            f"{payload['batch_context']['candidate_id_prefix']}"
            f"{assignment['assignment_ordinal']:02d}"
        )
        expected_state = []
        if task_type["task_type"] == "contact_followup":
            expected_state = [
                {
                    "check_type": "contact_followup",
                    "expected": {
                        "name": entry["observation"]["name"],
                        "note": (
                            f"Send follow-up email to "
                            f"{entry['observation']['email']}."
                        ),
                    },
                }
            ]
        final_answer = (
            DERIVED_FINAL_ANSWER_SENTINEL
            if task_type["final_answer"].get("value_contract") == "sentinel"
            else entry["observation"]["email"]
        )
        record = {
            "candidate_id": candidate_id,
            "instruction": (
                f"Find {entry['observation']['name']}'s email and record a "
                f"follow-up to send {entry['observation']['email']}."
                if task_type["task_type"] == "contact_followup"
                else f"Find {entry['observation']['name']}'s email."
            ),
            "task_type": task_type["task_type"],
            "difficulty": {
                "level": "easy",
                "tool_count": len(task_type["required_tools"]),
                "constraint_count": 1,
                "state_changes": int(
                    task_type["task_type"] == "contact_followup"
                ),
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
        if self._violate_grounding_scope:
            record["primary_arguments"] = {"name": "Ben Carter"}
        if self._violate_cross_step_binding and expected_state:
            expected_state[0]["expected"]["name"] = "Ben Carter"
        if self._inject_assignment_field:
            record["assignment_id"] = assignment["assignment_id"]
        return LLMGenerationResult(
            content={"task_contracts": [record]},
            lineage={
                "role": role,
                "provider_host": "fake.provider.test",
                "model": "deterministic-fake",
                "config_hash": "sha256:" + "1" * 64,
                "retry_count": 0,
            },
        )


class CoverageAssignmentPipelineTest(unittest.TestCase):
    def _run(self, provider: AssignmentAwareFakeProvider, output_dir: Path):
        from synthesis.coverage_assignments import (
            build_coverage_assignment_candidate_generator_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-tracer.json")
        )
        return run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            coverage_candidate_generator_factory=(
                build_coverage_assignment_candidate_generator_factory(provider)
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
        )

    def test_coverage_profile_runs_read_only_and_state_changing_assignments(self) -> None:
        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 0)
            self.assertIsNotNone(result.coverage_plan_path)
            assert result.coverage_plan_path is not None
            self.assertTrue(result.coverage_plan_path.exists())
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                {sample["task"]["constraints"]["task_type"] for sample in samples},
                {"contact_lookup", "contact_followup"},
            )
            self.assertEqual(
                {
                    tuple(
                        event["tool"]
                        for event in sample["trajectory"]
                        if event["type"] == "action"
                    )
                    for sample in samples
                },
                {
                    ("lookup_contact_email",),
                    ("lookup_contact_email", "record_contact_followup"),
                },
            )
            followup_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"]["task_type"]
                == "contact_followup"
            )
            self.assertEqual(
                followup_sample["mutation_admission"]["admission_outcome"],
                "judge_supported",
            )
            self.assertEqual(
                followup_sample["mutation_admission"]["semantic_verdict"][
                    "verdict"
                ],
                "supported",
            )
            self.assertEqual(
                {
                    sample["task"]["constraints"]["task_type"]: sample["task"][
                        "difficulty"
                    ]
                    for sample in samples
                },
                {
                    "contact_lookup": {
                        "level": "basic",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    "contact_followup": {
                        "level": "intermediate",
                        "tool_count": 2,
                        "constraint_count": 1,
                        "state_changes": 1,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                },
            )
            for sample in samples:
                assignment = sample["lineage"]["generator"]["coverage_assignment"]
                self.assertEqual(
                    set(assignment),
                    {
                        "schema_version",
                        "assignment_id",
                        "assignment_hash",
                        "assignment_ordinal",
                        "plan_id",
                        "plan_hash",
                        "cell_id",
                        "catalog",
                        "coverage_profile",
                        "scheduler",
                        "grounding_scope",
                    },
                )
                self.assertRegex(
                    assignment["assignment_hash"],
                    r"^sha256:[0-9a-f]{64}$",
                )
                self.assertNotIn("grounding_context", assignment)

            self.assertEqual(len(provider.payloads), 2)
            for payload in provider.payloads:
                assignment = payload["coverage_assignment"]
                self.assertEqual(payload["requested_candidate_count"], 1)
                self.assertEqual(len(payload["task_types"]), 1)
                self.assertEqual(
                    {tool["name"] for tool in payload["tools"]},
                    set(assignment["required_tools"]),
                )
                grounding = next(iter(payload["grounding_context"].values()))
                self.assertEqual(len(grounding), 1)
                forbidden = payload["output_contract"]["forbidden_fields"]
                for field in (
                    "assignment_id",
                    "assignment_hash",
                    "cell_id",
                    "coverage_score",
                    "fulfillment",
                    "lineage",
                    "plan_id",
                    "plan_hash",
                ):
                    self.assertIn(field, forbidden)

            persisted = " ".join(
                path.read_text(encoding="utf-8")
                for path in Path(tmp).glob("*.json*")
            )
            self.assertNotIn("provider_prompt", persisted)
            self.assertNotIn("provider_response", persisted)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["artifacts"]["coverage_plan"],
                "coverage_plan.json",
            )
            from synthesis.contracts import ContractValidationError
            from synthesis.contracts import validate_manifest_record

            invalid_overrides = (
                {"unexpected": {}},
                {"balance_weights": {"contacts.unknown": 2}},
                {"balance_weights": {"contacts.lookup_by_name": 5}},
            )
            for overrides in invalid_overrides:
                with self.subTest(overrides=overrides):
                    invalid_manifest = json.loads(json.dumps(manifest))
                    invalid_manifest["run_profile"]["coverage_profile"][
                        "overrides"
                    ] = overrides
                    with self.assertRaises(ContractValidationError):
                        validate_manifest_record(invalid_manifest)
            first_plan_bytes = result.coverage_plan_path.read_bytes()

        second_provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as second_tmp:
            second_result = self._run(second_provider, Path(second_tmp))
            first_assignments = [
                payload["coverage_assignment"] for payload in provider.payloads
            ]
            second_assignments = [
                payload["coverage_assignment"] for payload in second_provider.payloads
            ]
            self.assertEqual(first_assignments, second_assignments)
            assert second_result.coverage_plan_path is not None
            self.assertEqual(
                first_plan_bytes,
                second_result.coverage_plan_path.read_bytes(),
            )

    def test_assignment_mismatch_is_rejected_without_reclassification(self) -> None:
        provider = AssignmentAwareFakeProvider(mismatch_first_assignment=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(
                result.rejections_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(rejection["cause"], "coverage_assignment_mismatch")
            assignment = rejection["details"]["coverage_assignment"]
            self.assertEqual(
                assignment["cell_id"],
                "contacts.followup_after_lookup",
            )
            self.assertEqual(
                rejection["details"]["mismatch_reason"],
                "task_type_mismatch",
            )
            self.assertNotIn("provider_response", str(rejection))

    def test_provider_cannot_set_locally_owned_assignment_fields(self) -> None:
        provider = AssignmentAwareFakeProvider(inject_assignment_field=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 2)
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(
                {rejection["cause"] for rejection in rejections},
                {"llm_response_schema_error"},
            )
            for rejection in rejections:
                self.assertEqual(rejection["candidate_id"], "generation_stage")
                self.assertEqual(
                    rejection["details"]["schema_reason"],
                    "provider_record_keys_mismatch",
                )
                self.assertIn(
                    "coverage_assignment",
                    rejection["details"],
                )
                self.assertNotIn("assignment_id", rejection["task"])

    def test_candidate_must_use_the_assigned_grounding_scope(self) -> None:
        provider = AssignmentAwareFakeProvider(violate_grounding_scope=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 2)
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(
                {
                    rejection["details"]["mismatch_reason"]
                    for rejection in rejections
                },
                {"grounding_scope_mismatch"},
            )

    def test_followup_state_must_bind_to_the_assigned_lookup(self) -> None:
        provider = AssignmentAwareFakeProvider(
            violate_cross_step_binding=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(
                result.rejections_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(
                rejection["details"]["mismatch_reason"],
                "grounding_scope_mismatch",
            )

    def test_non_coverage_run_keeps_the_existing_artifact_set(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            result = run_foundation_pipeline(Path(tmp))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            self.assertIsNone(result.coverage_plan_path)
            self.assertNotIn("coverage_plan", manifest["artifacts"])
            self.assertFalse((Path(tmp) / "coverage_plan.json").exists())

    def test_non_coverage_remote_followup_contract_keeps_existing_semantics(
        self,
    ) -> None:
        from synthesis.domain_generation import (
            build_generation_batch_context,
            task_contract_from_provider_record,
        )
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmp:
            seed = foundation_seed()
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
            spec = bundle.generation_spec
            assert spec is not None
            context = build_generation_batch_context(spec, batch_index=2)
            record = {
                "candidate_id": f"{context.candidate_id_prefix}compat",
                "instruction": "Record a follow-up after finding Alice Zhang.",
                "task_type": "contact_followup",
                "difficulty": {},
                "required_capabilities": [
                    "contact_lookup",
                    "contact_followup",
                ],
                "required_tools": [
                    "lookup_contact_email",
                    "record_contact_followup",
                ],
                "primary_tool": "lookup_contact_email",
                "primary_arguments": {"name": "Alice Zhang"},
                "final_answer_contains": "alice.zhang@example.test",
                "expected_state": [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": "Outside Grounding",
                            "note": "Compatibility probe.",
                        },
                    }
                ],
            }

            contract = task_contract_from_provider_record(
                record,
                seed=seed,
                spec=spec,
                candidate_id_prefix=context.candidate_id_prefix,
                generation_lineage={},
            )

            self.assertEqual(
                contract.expected_state[0].expected["name"],
                "Outside Grounding",
            )

    def test_cli_executes_the_coverage_profile_through_the_assignment_path(
        self,
    ) -> None:
        import os
        import sys

        from main import main

        provider = AssignmentAwareFakeProvider()

        def generate_json(_client, prompt: str, *, role: str):
            return provider.generate_json(prompt, role=role)

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "coverage-cli"
            argv = [
                "main.py",
                "--run-profile",
                "tests/fixtures/run_profiles/contacts-coverage-tracer.json",
                "--use-llm",
                "--output-dir",
                str(output_dir),
            ]
            env = {
                "AGENT_DATA_LLM_BASE_URL": "https://fake.provider.test/v1",
                "AGENT_DATA_API_KEY": "coverage-cli-secret",
                "AGENT_DATA_LLM_MODEL": "coverage-generator",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(sys, "argv", argv),
                patch(
                    "synthesis.llm.OpenAICompatibleClient.generate_json",
                    new=generate_json,
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(
                manifest["artifacts"]["coverage_plan"],
                "coverage_plan.json",
            )


if __name__ == "__main__":
    unittest.main()
