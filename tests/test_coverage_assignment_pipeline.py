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
        duplicate_followup_instruction: bool = False,
    ) -> None:
        self.payloads: list[dict[str, object]] = []
        self._mismatch_first_assignment = mismatch_first_assignment
        self._inject_assignment_field = inject_assignment_field
        self._violate_grounding_scope = violate_grounding_scope
        self._violate_cross_step_binding = violate_cross_step_binding
        self._duplicate_followup_instruction = duplicate_followup_instruction

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
        if (
            self._duplicate_followup_instruction
            and task_type["task_type"] == "contact_followup"
        ):
            record["instruction"] = (
                "Find the contact email and record a follow-up."
            )
        if self._violate_grounding_scope:
            record["primary_arguments"] = {"name": "Unassigned Contact"}
        if self._violate_cross_step_binding and expected_state:
            expected_state[0]["expected"]["name"] = "Unassigned Contact"
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
    def _run(
        self,
        provider: AssignmentAwareFakeProvider,
        output_dir: Path,
        *,
        policy_generator=None,
        admission_evaluator=None,
        refiner=None,
        profile_path: str = (
            "tests/fixtures/run_profiles/contacts-coverage-tracer.json"
        ),
    ):
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path(profile_path)
        )
        pipeline_options = {}
        if policy_generator is not None:
            pipeline_options["policy_generator"] = policy_generator
        if admission_evaluator is not None:
            pipeline_options["admission_evaluator"] = admission_evaluator
        if refiner is not None:
            pipeline_options["refiner"] = refiner
        return run_foundation_pipeline(
            output_dir,
            dataset_version=profile.dataset_version,
            coverage_scheduler_factory=(
                build_coverage_assignment_scheduler_factory(provider)
            ),
            seed_override=profile.seed,
            run_profile_metadata=profile.sanitized_metadata(),
            run_profile=profile,
            **pipeline_options,
        )

    def test_coverage_run_derives_and_enforces_profile_attribution(self) -> None:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path(
                "tests/fixtures/run_profiles/"
                "contacts-coverage-tracer.json"
            )
        )
        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = run_foundation_pipeline(
                Path(tmp),
                dataset_version=profile.dataset_version,
                coverage_scheduler_factory=(
                    build_coverage_assignment_scheduler_factory(provider)
                ),
                seed_override=profile.seed,
                run_profile=profile,
            )
            manifest = json.loads(
                result.manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["run_profile"],
                profile.sanitized_metadata(),
            )
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["identities"]["run_profile"]["profile_id"],
                profile.profile_id,
            )

        mismatched = profile.sanitized_metadata()
        mismatched["profile_id"] = "mismatched_profile"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                ValueError,
                "must match the authoritative run profile",
            ):
                run_foundation_pipeline(
                    Path(tmp),
                    dataset_version=profile.dataset_version,
                    coverage_scheduler_factory=(
                        build_coverage_assignment_scheduler_factory(provider)
                    ),
                    seed_override=profile.seed,
                    run_profile_metadata=mismatched,
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
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["status"],
                "complete",
            )
            self.assertEqual(
                result.coverage_reconciliation["attempts"],
                {"ceiling": 3, "issued": 2, "remaining": 1},
            )
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

    def test_coverage_run_writes_hash_bound_evidence_artifact(self) -> None:
        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertIsNotNone(result.coverage_evidence_path)
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(evidence),
                {
                    "schema_version",
                    "evidence_id",
                    "evidence_hash",
                    "dataset_version",
                    "identities",
                    "counts",
                    "cells",
                    "distributions",
                    "fulfillment",
                },
            )
            self.assertEqual(evidence["schema_version"], "coverage_evidence_v1")
            self.assertRegex(evidence["evidence_id"], r"^coverage_evidence_[0-9a-f]{16}$")
            self.assertRegex(evidence["evidence_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(
                set(evidence["identities"]),
                {
                    "catalog",
                    "coverage_profile",
                    "plan",
                    "scheduler",
                    "run_profile",
                    "assignments",
                    "accepted_samples",
                    "rejections",
                },
            )
            for identity in (
                "scheduler",
                "run_profile",
                "assignments",
                "accepted_samples",
                "rejections",
            ):
                self.assertRegex(
                    evidence["identities"][identity]["identity_hash"],
                    r"^sha256:[0-9a-f]{64}$",
                )
            self.assertEqual(evidence["counts"]["accepted"], 2)
            self.assertEqual(evidence["counts"]["rejected"], 0)
            self.assertEqual(evidence["fulfillment"]["status"], "fulfilled")
            manifest = json.loads(
                result.manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["artifacts"]["coverage_evidence"],
                "coverage_evidence.json",
            )

    def test_coverage_evidence_verification_rejects_identity_drift(self) -> None:
        from synthesis.coverage_evidence import verify_coverage_evidence

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))
            assert result.coverage_evidence_path is not None
            assert result.coverage_plan_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            plan = json.loads(
                result.coverage_plan_path.read_text(encoding="utf-8")
            )
            manifest = json.loads(
                result.manifest_path.read_text(encoding="utf-8")
            )
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

            verify_coverage_evidence(
                evidence,
                plan=plan,
                run_profile=manifest["run_profile"],
                samples=samples,
                rejections=rejections,
            )

            drift_cases = []
            catalog_drift = json.loads(json.dumps(plan))
            catalog_drift["catalog"]["catalog_hash"] = "sha256:" + "1" * 64
            drift_cases.append(("catalog", catalog_drift, manifest["run_profile"], samples))
            profile_drift = json.loads(json.dumps(plan))
            profile_drift["coverage_profile"]["profile_hash"] = "sha256:" + "2" * 64
            drift_cases.append(("profile", profile_drift, manifest["run_profile"], samples))
            plan_drift = json.loads(json.dumps(plan))
            plan_drift["plan_hash"] = "sha256:" + "3" * 64
            drift_cases.append(("plan", plan_drift, manifest["run_profile"], samples))
            run_profile_drift = json.loads(json.dumps(manifest["run_profile"]))
            run_profile_drift["profile_id"] = "changed_profile"
            drift_cases.append(("run_profile", plan, run_profile_drift, samples))
            assignment_drift = json.loads(json.dumps(samples))
            assignment_drift[0]["lineage"]["generator"]["coverage_assignment"][
                "assignment_hash"
            ] = "sha256:" + "4" * 64
            drift_cases.append(
                ("assignment", plan, manifest["run_profile"], assignment_drift)
            )
            drift_cases.append(
                ("sample_membership", plan, manifest["run_profile"], samples[1:])
            )

            for label, changed_plan, changed_profile, changed_samples in drift_cases:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(
                        ValueError,
                        "coverage evidence identity mismatch",
                    ):
                        verify_coverage_evidence(
                            evidence,
                            plan=changed_plan,
                            run_profile=changed_profile,
                            samples=changed_samples,
                            rejections=rejections,
                        )

    def test_profile_decision_loader_rejects_coverage_artifact_drift(
        self,
    ) -> None:
        from synthesis.profile_decisions import (
            write_profile_decision_report,
        )

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))
            decision_path = write_profile_decision_report(
                manifest_path=result.manifest_path,
                quality_report_path=result.quality_report_path,
            )
            self.assertTrue(decision_path.exists())

            result.samples_path.write_text(
                result.samples_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "coverage evidence binding is invalid",
            ):
                write_profile_decision_report(
                    manifest_path=result.manifest_path,
                    quality_report_path=result.quality_report_path,
                )

    def test_coverage_evidence_contract_rejects_inconsistent_counts(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_coverage_evidence_record,
        )
        from synthesis.coverage import canonical_coverage_hash

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )

            validate_coverage_evidence_record(evidence)
            invalid = json.loads(json.dumps(evidence))
            invalid["counts"]["accepted"] = 1
            invalid_payload = {
                key: value
                for key, value in invalid.items()
                if key not in {"evidence_id", "evidence_hash"}
            }
            invalid_hash = canonical_coverage_hash(invalid_payload)
            invalid["evidence_hash"] = invalid_hash
            invalid["evidence_id"] = (
                "coverage_evidence_"
                + invalid_hash.removeprefix("sha256:")[:16]
            )

            with self.assertRaisesRegex(
                ContractValidationError,
                "does not reconcile",
            ):
                validate_coverage_evidence_record(invalid)

    def test_quality_report_embeds_only_sanitized_coverage_summary(self) -> None:
        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            quality = json.loads(
                result.quality_report_path.read_text(encoding="utf-8")
            )

            self.assertEqual(
                set(quality["coverage"]),
                {
                    "schema_version",
                    "evidence_id",
                    "evidence_hash",
                    "counts",
                    "distributions",
                    "fulfillment",
                },
            )
            self.assertEqual(
                quality["coverage"]["evidence_hash"],
                evidence["evidence_hash"],
            )
            self.assertEqual(
                quality["coverage"]["fulfillment"]["status"],
                "fulfilled",
            )
            serialized = json.dumps(quality["coverage"])
            for forbidden in (
                "provider_prompt",
                "provider_response",
                "source_payload",
                "primary_arguments",
                "instruction",
            ):
                self.assertNotIn(forbidden, serialized)

    def test_assignment_mismatch_is_backfilled_without_reclassification(self) -> None:
        provider = AssignmentAwareFakeProvider(mismatch_first_assignment=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertEqual(len(provider.payloads), 3)
            self.assertEqual(
                [
                    payload["coverage_assignment"]["cell_id"]
                    for payload in provider.payloads
                ],
                [
                    "contacts.followup_after_lookup",
                    "contacts.lookup_by_name",
                    "contacts.followup_after_lookup",
                ],
            )
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
            self.assertEqual(
                result.coverage_reconciliation,
                {
                    "schema_version": "coverage_reconciliation_v1",
                    "status": "complete",
                    "attempts": {
                        "ceiling": 3,
                        "issued": 3,
                        "remaining": 0,
                    },
                    "cells": [
                        {
                            "cell_id": "contacts.followup_after_lookup",
                            "planned": 1,
                            "in_flight": 0,
                            "accepted": 1,
                            "rejected": 1,
                            "remaining": 0,
                            "deficit_reason": None,
                        },
                        {
                            "cell_id": "contacts.lookup_by_name",
                            "planned": 1,
                            "in_flight": 0,
                            "accepted": 1,
                            "rejected": 0,
                            "remaining": 0,
                            "deficit_reason": None,
                        },
                    ],
                    "waves": [
                        {
                            "wave": 1,
                            "issued": 2,
                            "in_flight_after_generation": 1,
                            "accepted": 1,
                            "rejected": 1,
                        },
                        {
                            "wave": 2,
                            "issued": 1,
                            "in_flight_after_generation": 1,
                            "accepted": 1,
                            "rejected": 0,
                        },
                    ],
                },
            )
            first_samples = result.samples_path.read_bytes()
            first_rejections = result.rejections_path.read_bytes()
            first_reconciliation = result.coverage_reconciliation

        second_provider = AssignmentAwareFakeProvider(
            mismatch_first_assignment=True
        )
        with tempfile.TemporaryDirectory() as second_tmp:
            second_result = self._run(second_provider, Path(second_tmp))

            self.assertEqual(
                [
                    payload["coverage_assignment"]
                    for payload in provider.payloads
                ],
                [
                    payload["coverage_assignment"]
                    for payload in second_provider.payloads
                ],
            )
            self.assertEqual(
                first_samples,
                second_result.samples_path.read_bytes(),
            )
            self.assertEqual(
                first_rejections,
                second_result.rejections_path.read_bytes(),
            )
            self.assertEqual(
                first_reconciliation,
                second_result.coverage_reconciliation,
            )

    def test_candidate_processing_rejection_leaves_a_backfill_deficit(self) -> None:
        from dataclasses import replace

        from synthesis.execution import ToolStep, scripted_solution_policy

        rejected_first_followup = False

        def policy_generator(candidate):
            nonlocal rejected_first_followup
            policy = scripted_solution_policy(candidate)
            if (
                candidate.constraints["task_type"] == "contact_followup"
                and not rejected_first_followup
            ):
                rejected_first_followup = True
                return replace(
                    policy,
                    steps=(
                        ToolStep(
                            tool_name="lookup_contact_email",
                            arguments={"name": "Unassigned Contact"},
                        ),
                    ),
                )
            return policy

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                policy_generator=policy_generator,
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertEqual(len(provider.payloads), 3)
            rejection = json.loads(
                result.rejections_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(rejection["cause"], "tool_runtime_error")
            assignment = rejection["details"]["role_lineages"]["generator"][
                "coverage_assignment"
            ]
            self.assertEqual(
                assignment["cell_id"],
                "contacts.followup_after_lookup",
            )
            assert result.coverage_reconciliation is not None
            followup = result.coverage_reconciliation["cells"][0]
            self.assertEqual(
                followup,
                {
                    "cell_id": "contacts.followup_after_lookup",
                    "planned": 1,
                    "in_flight": 0,
                    "accepted": 1,
                    "rejected": 1,
                    "remaining": 0,
                    "deficit_reason": None,
                },
            )

    def test_semantic_mutation_rejection_leaves_a_backfill_deficit(self) -> None:
        from dataclasses import replace

        from synthesis.contact_mutations import (
            build_contact_followup_semantic_mutation_judge,
            contact_followup_mutation_policies,
        )
        from synthesis.environments import ContactEnvironment
        from synthesis.mutation_admission import (
            build_local_candidate_admission_evaluator,
        )

        with tempfile.TemporaryDirectory() as environment_tmp:
            environment = ContactEnvironment.create_fixture(
                Path(environment_tmp)
            )
            base_judge = build_contact_followup_semantic_mutation_judge(
                environment
            )
            rejected_first_followup = False

            def judge(request):
                nonlocal rejected_first_followup
                result = base_judge(request)
                if rejected_first_followup:
                    return result
                rejected_first_followup = True
                verdict = dict(result.verdict or {})
                action_findings = [
                    dict(item)
                    for item in verdict["action_findings"]
                ]
                action_findings[0]["outcome"] = "unsupported"
                action_findings[0]["reason_code"] = "action_not_authorized"
                verdict["verdict"] = "unsupported"
                verdict["action_findings"] = action_findings
                verdict["reason_codes"] = [
                    "action_not_authorized",
                    *[
                        reason
                        for reason in verdict["reason_codes"]
                        if reason != "action_authorized"
                    ],
                ]
                return replace(result, verdict=verdict)

            evaluator = build_local_candidate_admission_evaluator(
                mode="enforce",
                policies=contact_followup_mutation_policies(environment),
                state_changing_tools=("record_contact_followup",),
                judge=judge,
            )
            provider = AssignmentAwareFakeProvider()
            with tempfile.TemporaryDirectory() as tmp:
                result = self._run(
                    provider,
                    Path(tmp),
                    admission_evaluator=evaluator,
                )
                self.assertEqual(result.accepted_count, 2)
                self.assertEqual(result.rejected_count, 1)
                rejection = json.loads(
                    result.rejections_path.read_text(
                        encoding="utf-8"
                    ).splitlines()[0]
                )
                self.assertEqual(
                    rejection["cause"],
                    "mutation_admission_failed",
                )
                self.assertEqual(len(provider.payloads), 3)
                assert result.coverage_reconciliation is not None
                self.assertEqual(
                    result.coverage_reconciliation["cells"][0]["rejected"],
                    1,
                )

    def test_verification_rejection_leaves_a_backfill_deficit(self) -> None:
        from dataclasses import replace

        from synthesis.execution import scripted_solution_policy

        rejected_first_followup = False

        def policy_generator(candidate):
            nonlocal rejected_first_followup
            policy = scripted_solution_policy(candidate)
            if (
                candidate.constraints["task_type"] == "contact_followup"
                and not rejected_first_followup
            ):
                rejected_first_followup = True
                return replace(
                    policy,
                    final_response_template="No matching email was found.",
                )
            return policy

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                policy_generator=policy_generator,
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(
                result.rejections_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertEqual(len(provider.payloads), 3)
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["cells"][0]["rejected"],
                1,
            )

    def test_exact_duplicates_exhaust_only_the_declared_backfill_budget(
        self,
    ) -> None:
        provider = AssignmentAwareFakeProvider(
            duplicate_followup_instruction=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                profile_path=(
                    "tests/fixtures/run_profiles/"
                    "contacts-coverage-backfill.json"
                ),
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 3)
            self.assertEqual(len(provider.payloads), 5)
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(
                {rejection["cause"] for rejection in rejections},
                {"quality_duplicate"},
            )
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["attempts"],
                {"ceiling": 5, "issued": 5, "remaining": 0},
            )
            self.assertEqual(
                result.coverage_reconciliation["cells"][0][
                    "deficit_reason"
                ],
                "target_deficit",
            )
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["counts"],
                {
                    "target_accepted": 3,
                    "attempt_ceiling": 5,
                    "attempted": 5,
                    "generated": 5,
                    "accepted": 2,
                    "rejected": 3,
                    "remaining": 1,
                    "unassigned_accepted": 0,
                    "unassigned_rejected": 0,
                },
            )
            self.assertEqual(
                evidence["distributions"]["exact_duplicates"],
                {"count": 3, "rate": 0.6},
            )
            self.assertEqual(
                evidence["fulfillment"],
                {
                    "status": "incomplete",
                    "mandatory_fulfilled": True,
                    "target_fulfilled": False,
                    "reasons": [
                        "target_distribution_underfilled",
                        "attempt_ceiling_exhausted",
                    ],
                },
            )
            quality = json.loads(
                result.quality_report_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                quality["coverage"]["fulfillment"]["status"],
                "incomplete",
            )

    def test_assignment_invalid_refinement_is_rejected_before_rerun(
        self,
    ) -> None:
        from dataclasses import replace

        from synthesis.execution import scripted_solution_policy
        from synthesis.refinement import RefinementAttempt

        failed_first_followup = False

        def policy_generator(candidate):
            nonlocal failed_first_followup
            policy = scripted_solution_policy(candidate)
            if (
                candidate.constraints["task_type"] == "contact_followup"
                and not failed_first_followup
            ):
                failed_first_followup = True
                return replace(
                    policy,
                    final_response_template="No matching email was found.",
                )
            return policy

        def refiner(context):
            revised = replace(
                context.task,
                candidate_id=f"{context.task.candidate_id}_refined_1",
                arguments={"name": "Unassigned Contact"},
            )
            return RefinementAttempt(
                original_candidate_id=context.task.candidate_id,
                attempt_number=1,
                source_failure_cause=context.source_failure_cause,
                source_failure_details=context.source_failure_details,
                critic_diagnosis="Move the task outside its assigned grounding.",
                repair_decision="repair_candidate",
                lineage={
                    "role": "local_critic_refinement",
                    "provider_host": "local",
                    "model": "deterministic",
                    "config_hash": "coverage_refinement_test_v1",
                    "configured": True,
                },
                revised_candidate=revised,
            )

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                policy_generator=policy_generator,
                refiner=refiner,
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(
                result.rejections_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(
                rejection["cause"],
                "coverage_assignment_mismatch",
            )
            self.assertEqual(
                rejection["details"]["mismatch_reason"],
                "grounding_scope_mismatch",
            )
            self.assertEqual(
                rejection["details"]["refinement"]["outcome"],
                "rejected",
            )
            self.assertEqual(len(provider.payloads), 3)
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["cells"][0]["rejected"],
                1,
            )

    def test_assignment_valid_refinement_can_fulfill_with_a_revised_id(
        self,
    ) -> None:
        from dataclasses import replace

        from synthesis.execution import scripted_solution_policy
        from synthesis.refinement import RefinementAttempt

        failed_first_followup = False

        def policy_generator(candidate):
            nonlocal failed_first_followup
            policy = scripted_solution_policy(candidate)
            if (
                candidate.constraints["task_type"] == "contact_followup"
                and not failed_first_followup
            ):
                failed_first_followup = True
                return replace(
                    policy,
                    final_response_template="No matching email was found.",
                )
            return policy

        def refiner(context):
            return RefinementAttempt(
                original_candidate_id=context.task.candidate_id,
                attempt_number=1,
                source_failure_cause=context.source_failure_cause,
                source_failure_details=context.source_failure_details,
                critic_diagnosis="Retry the assigned task with a revised id.",
                repair_decision="repair_candidate",
                lineage={
                    "role": "local_critic_refinement",
                    "provider_host": "local",
                    "model": "deterministic",
                    "config_hash": "coverage_refinement_test_v1",
                    "configured": True,
                },
                revised_candidate=replace(
                    context.task,
                    candidate_id=f"{context.task.candidate_id}_refined_1",
                ),
            )

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                policy_generator=policy_generator,
                refiner=refiner,
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 0)
            self.assertEqual(len(provider.payloads), 2)
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["attempts"],
                {"ceiling": 3, "issued": 2, "remaining": 1},
            )
            samples = result.samples_path.read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertTrue(
                any("_refined_1" in json.loads(line)["sample_id"] for line in samples)
            )

    def test_contacts_coverage_samples_bind_exact_domain_capabilities(self) -> None:
        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                if line
            ]

        self.assertEqual(len(samples), 2)
        expected_keys = {
            "contact_lookup",
            "followup_recording",
        }
        for sample in samples:
            binding = sample["contacts_evidence"]
            self.assertEqual(binding, sample["domain_evidence"])
            self.assertEqual(
                binding["domain_pack_reference"]["domain_pack_id"],
                "contacts",
            )
            self.assertEqual(
                {
                    reference["capability_key"]
                    for reference in binding["capability_references"]
                },
                {
                    "contact_lookup",
                    "followup_recording",
                    "contact_lookup_recovery",
                    "missing_contact_safe_failure",
                },
            )
            task_keys = {
                reference["capability_key"]
                for reference in binding["task_capability_references"]
            }
            self.assertTrue(task_keys <= expected_keys)
            self.assertEqual(
                binding["assignment_capability_references"],
                binding["task_capability_references"],
            )
            self.assertEqual(
                {
                    reference["capability_key"]
                    for reference in binding["assignment"]["catalog"][
                        "capability_references"
                    ]
                },
                task_keys,
            )
            self.assertTrue(binding["final_state"]["verification_passed"])

    def test_unverified_contacts_recovery_receives_no_coverage_credit(self) -> None:
        from dataclasses import replace
        from synthesis.execution import scripted_solution_policy

        def direct_success_policy(candidate):
            policy = scripted_solution_policy(candidate)
            if candidate.branch_plan is None:
                return policy
            branches = candidate.branch_plan["branches"]
            fallback = branches[-1]
            return replace(
                policy,
                branch_plan={
                    "schema_version": "branch_plan_v1",
                    "plan_id": "branch_plan_contacts_unverified_recovery",
                    "max_depth": 1,
                    "branches": [
                        {
                            "branch_id": "direct_success",
                            "node_type": "attempt",
                            "parent_id": None,
                            "condition": "Use the fallback selector directly.",
                            "steps": list(fallback["steps"]),
                            "final_response_template": "{name}'s email is {email}.",
                            "terminal_outcome": "accept_on_success",
                        }
                    ],
                },
            )

        provider = AssignmentAwareFakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                provider,
                Path(tmp),
                policy_generator=direct_success_policy,
                profile_path=(
                    "tests/fixtures/run_profiles/contacts-coverage-catalog-probe.json"
                ),
            )
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )

        recovery_cell = next(
            cell
            for cell in result.coverage_reconciliation["cells"]
            if cell["cell_id"] == "contacts.lookup_with_recovery"
        )
        evidence_recovery_cell = next(
            cell
            for cell in evidence["cells"]
            if cell["cell_id"] == "contacts.lookup_with_recovery"
        )
        self.assertEqual(result.accepted_count, 2)
        self.assertEqual(recovery_cell["accepted"], 0)
        self.assertEqual(evidence_recovery_cell["accepted"], 0)

    def test_provider_cannot_set_locally_owned_assignment_fields(self) -> None:
        provider = AssignmentAwareFakeProvider(inject_assignment_field=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 3)
            self.assertEqual(len(provider.payloads), 3)
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
            assert result.coverage_reconciliation is not None
            self.assertEqual(
                result.coverage_reconciliation["status"],
                "incomplete",
            )
            self.assertEqual(
                result.coverage_reconciliation["attempts"],
                {"ceiling": 3, "issued": 3, "remaining": 0},
            )
            self.assertEqual(
                result.coverage_reconciliation["cells"],
                [
                    {
                        "cell_id": "contacts.followup_after_lookup",
                        "planned": 1,
                        "in_flight": 0,
                        "accepted": 0,
                        "rejected": 2,
                        "remaining": 1,
                        "deficit_reason": "mandatory_deficit",
                    },
                    {
                        "cell_id": "contacts.lookup_by_name",
                        "planned": 1,
                        "in_flight": 0,
                        "accepted": 0,
                        "rejected": 1,
                        "remaining": 1,
                        "deficit_reason": "mandatory_deficit",
                    },
                ],
            )
            assert result.coverage_evidence_path is not None
            evidence = json.loads(
                result.coverage_evidence_path.read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["counts"]["attempted"], 3)
            self.assertEqual(evidence["counts"]["generated"], 0)
            self.assertEqual(evidence["counts"]["accepted"], 0)
            self.assertEqual(evidence["counts"]["rejected"], 3)
            self.assertEqual(evidence["counts"]["remaining"], 2)
            self.assertEqual(
                {
                    cell["cell_id"]: cell["rejection_causes"]
                    for cell in evidence["cells"]
                },
                {
                    "contacts.followup_after_lookup": {
                        "llm_response_schema_error": 2
                    },
                    "contacts.lookup_by_name": {
                        "llm_response_schema_error": 1
                    },
                },
            )

    def test_candidate_must_use_the_assigned_grounding_scope(self) -> None:
        provider = AssignmentAwareFakeProvider(violate_grounding_scope=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(provider, Path(tmp))

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 3)
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
            self.assertEqual(result.rejected_count, 2)
            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(
                {
                    (
                        rejection["cause"],
                        rejection["details"]["schema_reason"],
                        rejection["details"]["schema_detail"],
                    )
                    for rejection in rejections
                },
                {
                    (
                        "llm_response_schema_error",
                        "invalid_expected_state",
                        "expected_state_grounding_binding_mismatch",
                    )
                },
            )

    def test_non_coverage_run_keeps_the_existing_artifact_set(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            result = run_foundation_pipeline(Path(tmp))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            self.assertIsNone(result.coverage_plan_path)
            self.assertIsNone(result.coverage_reconciliation)
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
            grounding = next(iter(spec.grounding_context.values()))[0]
            observation = grounding["observation"]
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
                "primary_arguments": grounding["primary_arguments"],
                "final_answer_contains": observation["email"],
                "expected_state": [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": observation["name"],
                            "note": f"Compatibility probe for {observation['email']}.",
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
                observation["name"],
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
