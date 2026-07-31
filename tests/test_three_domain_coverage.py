from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class ThreeDomainCoverageFakeProvider:
    def __init__(self) -> None:
        self.assignments: list[dict[str, object]] = []

    def generate_json(self, prompt: str, *, role: str):
        from synthesis.domain_generation import DERIVED_FINAL_ANSWER_SENTINEL
        from synthesis.llm import LLMGenerationResult

        payload = json.loads(prompt)
        assignment = payload["coverage_assignment"]
        self.assignments.append(assignment)
        task_type = payload["task_types"][0]
        grounding = next(iter(payload["grounding_context"].values()))[0]
        observation = grounding["observation"]
        primary_arguments = grounding["primary_arguments"]
        ordinal = assignment["assignment_ordinal"]
        candidate_id = (
            f"{payload['batch_context']['candidate_id_prefix']}{ordinal:02d}"
        )
        instruction, expected_state = self._task_contract_parts(
            task_type["task_type"],
            observation,
            ordinal,
            assignment,
        )
        final_answer_contract = task_type["final_answer"]
        if final_answer_contract.get("value_contract") == "sentinel":
            final_answer = DERIVED_FINAL_ANSWER_SENTINEL
        else:
            field = final_answer_contract["allowed_fields"][0]
            final_answer = str(observation[field])
        record = {
            "candidate_id": candidate_id,
            "instruction": instruction,
            "task_type": task_type["task_type"],
            "difficulty": {
                "level": "provider_value_is_not_authoritative",
                "tool_count": len(task_type["required_tools"]),
                "constraint_count": 1,
                "state_changes": int(
                    assignment["state_behavior"] == "state_changing"
                ),
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "required_capabilities": task_type["required_capabilities"],
            "required_tools": task_type["required_tools"],
            "primary_tool": task_type["required_tools"][0],
            "primary_arguments": dict(primary_arguments),
            "final_answer_contains": final_answer,
            "expected_state": expected_state,
        }
        return LLMGenerationResult(
            content={"task_contracts": [record]},
            lineage={
                "role": role,
                "provider_host": "fake.provider.test",
                "model": "three-domain-coverage-fake",
                "config_hash": "sha256:" + "7" * 64,
                "retry_count": 0,
            },
        )

    @staticmethod
    def _task_contract_parts(
        task_type: str,
        observation: dict[str, object],
        ordinal: int,
        assignment: dict[str, object],
    ) -> tuple[str, list[dict[str, object]]]:
        if task_type == "contact_followup":
            note = f"Send coverage follow-up {ordinal} to {observation['email']}."
            return (
                f"Find {observation['name']}'s email and record the note "
                f'"{note}" as a follow-up.',
                [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": observation["name"],
                            "note": note,
                        },
                    }
                ],
            )
        if task_type == "mobile_reminder_creation":
            title = f"Review message {ordinal}"
            due_at = "tomorrow 9 AM"
            return (
                f"Find the message and create a reminder titled {title} due "
                f"{due_at}.",
                [
                    {
                        "check_type": "mobile_reminder",
                        "expected": {
                            "title": title,
                            "due_at": due_at,
                            "source_message_id": observation["message_id"],
                        },
                    }
                ],
            )
        if task_type == "mobile_draft_reply":
            body = f"Coverage reply {ordinal}."
            return (
                f'Find the message and draft the reply "{body}" in its thread.',
                [
                    {
                        "check_type": "mobile_draft_reply",
                        "expected": {
                            "thread_id": observation["thread_id"],
                            "body": body,
                        },
                    }
                ],
            )
        if task_type == "workspace_task_creation":
            title = f"Prepare coverage review {ordinal}"
            return (
                f"Find {observation['summary']} and create a task titled "
                f"{title} with high priority due this_week in that project.",
                [
                    {
                        "check_type": "workspace_task",
                        "expected": {
                            "project_id": observation["project_id"],
                            "title": title,
                            "priority": "high",
                            "due_label": "this_week",
                        },
                    }
                ],
            )
        if task_type == "workspace_comment_update":
            comment = f"Coverage reviewed {ordinal}."
            return (
                f'Find {observation["summary"]} and add the comment "{comment}".',
                [
                    {
                        "check_type": "workspace_comment",
                        "expected": {
                            "task_id": observation["item_id"],
                            "comment": comment,
                        },
                    }
                ],
            )
        if assignment["recovery"] != "none":
            return (
                f"Run assigned recovery case {ordinal}; if the direct lookup "
                "fails, use the declared fallback.",
                [],
            )
        if assignment["ambiguity"] == "deterministic_multi_result":
            return (
                f"Run assigned multi-result case {ordinal} and return the "
                "deterministic first result.",
                [],
            )
        grounding_label = next(
            (
                str(observation[key])
                for key in ("name", "message_id", "item_id")
                if key in observation
            ),
            f"case {ordinal}",
        )
        return (
            f"Run assigned exact-selector case {ordinal} for grounded result "
            f"{grounding_label}.",
            [],
        )


class ThreeDomainCoverageCatalogTest(unittest.TestCase):
    def test_shared_scheduler_and_validator_have_no_domain_name_branches(self) -> None:
        for path in (
            Path("synthesis/coverage.py"),
            Path("synthesis/coverage_assignments.py"),
        ):
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8").lower()
                self.assertNotIn("contacts", source)
                self.assertNotIn("mobile", source)
                self.assertNotIn("workspace", source)

    def test_all_domain_catalogs_are_reachable_through_one_shared_contract(self) -> None:
        from synthesis.coverage import validate_coverage_catalog_reachability
        from synthesis.coverage_registry import resolve_domain_coverage_planning
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        domains = (
            "contacts_fixture",
            "mobile_messages_fixture",
            "workspace_tasks_fixture",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for domain_id in domains:
                with self.subTest(domain_id=domain_id):
                    seed = DomainSeed(
                        seed_id=f"seed_{domain_id}_coverage_contract",
                        domain=domain_id,
                        description="Validate domain-owned coverage declarations.",
                        task_taxonomy=(),
                    )
                    bundle = build_domain_pipeline_bundle(
                        seed,
                        Path(tmp) / domain_id,
                    )
                    planning = resolve_domain_coverage_planning(domain_id)
                    assert bundle.generation_spec is not None

                    validate_coverage_catalog_reachability(
                        planning.catalog,
                        bundle.generation_spec,
                        execute_tool=bundle.registry.execute,
                    )

                    self.assertGreaterEqual(len(planning.catalog.cells), 3)
                    self.assertTrue(planning.catalog.compatibility_constraints)
                    self.assertTrue(planning.catalog.difficulty_semantics)
                    self.assertIn(
                        "read_only",
                        {
                            cell.dimensions["state_behavior"]
                            for cell in planning.catalog.cells
                        },
                    )
                    self.assertIn(
                        "state_changing",
                        {
                            cell.dimensions["state_behavior"]
                            for cell in planning.catalog.cells
                        },
                    )

    def test_reachability_rejects_a_cell_that_the_domain_cannot_execute(self) -> None:
        from synthesis.coverage import (
            CoveragePlanValidationError,
            validate_coverage_catalog_reachability,
        )
        from synthesis.coverage_registry import resolve_domain_coverage_planning
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        with tempfile.TemporaryDirectory() as tmp:
            seed = DomainSeed(
                seed_id="seed_unreachable_coverage_cell",
                domain="mobile_messages_fixture",
                description="Reject an unreachable coverage cell.",
                task_taxonomy=(),
            )
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
            planning = resolve_domain_coverage_planning(seed.domain)
            assert bundle.generation_spec is not None
            unreachable = replace(
                planning.catalog.cells[0],
                cell_id="mobile.unreachable_tool",
                dimensions={
                    **planning.catalog.cells[0].dimensions,
                    "required_tools": ("missing_mobile_tool",),
                },
            )

            with self.assertRaisesRegex(
                CoveragePlanValidationError,
                "unreachable coverage cell mobile.unreachable_tool",
            ):
                validate_coverage_catalog_reachability(
                    replace(
                        planning.catalog,
                        cells=(*planning.catalog.cells, unreachable),
                    ),
                    bundle.generation_spec,
                    execute_tool=bundle.registry.execute,
                )

    def test_reachability_executes_recovery_failure_and_success_paths(self) -> None:
        from synthesis.coverage import (
            CoveragePlanValidationError,
            validate_coverage_catalog_reachability,
        )
        from synthesis.coverage_registry import resolve_domain_coverage_planning
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        with tempfile.TemporaryDirectory() as tmp:
            seed = DomainSeed(
                seed_id="seed_unreachable_recovery",
                domain="mobile_messages_fixture",
                description="Reject a recovery path whose direct branch succeeds.",
                task_taxonomy=(),
            )
            bundle = build_domain_pipeline_bundle(seed, Path(tmp))
            planning = resolve_domain_coverage_planning(seed.domain)
            assert bundle.generation_spec is not None
            recovery = next(
                cell
                for cell in planning.catalog.cells
                if cell.dimensions["recovery"] != "none"
            )
            branch_plan = json.loads(json.dumps(recovery.branch_plan))
            branch_plan["branches"][0]["steps"][0]["arguments"] = {
                "query": "pickup code",
                "participant": "Delivery",
            }
            invalid_recovery = replace(
                recovery,
                branch_plan=branch_plan,
            )

            with self.assertRaisesRegex(
                CoveragePlanValidationError,
                f"unreachable coverage cell {recovery.cell_id}",
            ):
                validate_coverage_catalog_reachability(
                    replace(
                        planning.catalog,
                        cells=tuple(
                            invalid_recovery if cell is recovery else cell
                            for cell in planning.catalog.cells
                        ),
                    ),
                    bundle.generation_spec,
                    execute_tool=bundle.registry.execute,
                )

    def test_catalog_rejects_unlisted_dimension_cross_products(self) -> None:
        from synthesis.coverage import CoveragePlanValidationError, compile_coverage_plan
        from synthesis.coverage_registry import resolve_domain_coverage_planning

        planning = resolve_domain_coverage_planning("mobile_messages_fixture")
        recovery = next(
            cell
            for cell in planning.catalog.cells
            if cell.dimensions["recovery"] != "none"
        )
        invalid_recovery = replace(
            recovery,
            dimensions={
                **recovery.dimensions,
                "grounding_pattern": "query_and_participant",
            },
        )
        catalog = replace(
            planning.catalog,
            cells=tuple(
                invalid_recovery if cell is recovery else cell
                for cell in planning.catalog.cells
            ),
        )
        profile = planning.resolve_profile(
            "mobile_messages_smoke",
            "mobile_messages_smoke_v1",
        )

        with self.assertRaisesRegex(
            CoveragePlanValidationError,
            "violates compatibility constraints",
        ):
            compile_coverage_plan(
                catalog=catalog,
                coverage_profile=profile,
                version_registry=planning.version_registry,
                selected_features=("enable_branching",),
                target_accepted_sample_count=5,
                target_candidate_count=8,
                admitted_capacity=planning.resolve_capacity(None),
            )

    def test_all_domains_execute_distinct_cells_through_one_pipeline(self) -> None:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        probes = (
            ("contacts-coverage-catalog-probe.json", 3),
            ("mobile-coverage-catalog-probe.json", 5),
            ("workspace-coverage-catalog-probe.json", 5),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for fixture_name, expected_cells in probes:
                with self.subTest(fixture=fixture_name):
                    profile = load_run_profile(
                        Path("tests/fixtures/run_profiles") / fixture_name
                    )
                    provider = ThreeDomainCoverageFakeProvider()
                    result = run_foundation_pipeline(
                        Path(tmp) / profile.profile_id,
                        dataset_version=profile.dataset_version,
                        coverage_scheduler_factory=(
                            build_coverage_assignment_scheduler_factory(provider)
                        ),
                        seed_override=profile.seed,
                        run_profile_metadata=profile.sanitized_metadata(),
                        run_profile=profile,
                    )

                    self.assertEqual(result.accepted_count, expected_cells)
                    self.assertEqual(result.rejected_count, 0)
                    assert result.coverage_reconciliation is not None
                    self.assertEqual(
                        result.coverage_reconciliation["status"],
                        "complete",
                    )
                    reconciled_cells = result.coverage_reconciliation["cells"]
                    self.assertEqual(len(reconciled_cells), expected_cells)
                    self.assertTrue(
                        all(cell["accepted"] == 1 for cell in reconciled_cells)
                    )
                    self.assertEqual(
                        len(
                            {
                                assignment["cell_id"]
                                for assignment in provider.assignments
                            }
                        ),
                        expected_cells,
                    )

    def test_fake_provider_reaches_more_cells_as_each_domain_target_grows(self) -> None:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        fixture_names = (
            "contacts-coverage-catalog-probe.json",
            "mobile-coverage-catalog-probe.json",
            "workspace-coverage-catalog-probe.json",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for fixture_name in fixture_names:
                with self.subTest(fixture=fixture_name):
                    profile = load_run_profile(
                        Path("tests/fixtures/run_profiles") / fixture_name
                    )
                    assert profile.coverage_profile is not None
                    small_target = 2
                    small_profile = replace(
                        profile,
                        generation=replace(
                            profile.generation,
                            target_candidate_count=3,
                        ),
                        coverage_profile=replace(
                            profile.coverage_profile,
                            target_accepted_sample_count=small_target,
                        ),
                    )
                    small_provider = ThreeDomainCoverageFakeProvider()
                    small_result = run_foundation_pipeline(
                        Path(tmp) / f"{profile.profile_id}-small",
                        dataset_version=profile.dataset_version,
                        coverage_scheduler_factory=(
                            build_coverage_assignment_scheduler_factory(
                                small_provider
                            )
                        ),
                        seed_override=small_profile.seed,
                        run_profile_metadata=small_profile.sanitized_metadata(),
                        run_profile=small_profile,
                    )
                    large_provider = ThreeDomainCoverageFakeProvider()
                    large_result = run_foundation_pipeline(
                        Path(tmp) / f"{profile.profile_id}-large",
                        dataset_version=profile.dataset_version,
                        coverage_scheduler_factory=(
                            build_coverage_assignment_scheduler_factory(
                                large_provider
                            )
                        ),
                        seed_override=profile.seed,
                        run_profile_metadata=profile.sanitized_metadata(),
                        run_profile=profile,
                    )

                    small_cells = {
                        assignment["cell_id"]
                        for assignment in small_provider.assignments
                    }
                    large_cells = {
                        assignment["cell_id"]
                        for assignment in large_provider.assignments
                    }
                    self.assertEqual(small_result.accepted_count, small_target)
                    self.assertGreater(large_result.accepted_count, small_target)
                    self.assertLess(len(small_cells), len(large_cells))
                    self.assertTrue(small_cells < large_cells)

    def test_plan_rejects_a_target_above_cell_usable_capacity(self) -> None:
        from synthesis.coverage import CoveragePlanValidationError, compile_coverage_plan
        from synthesis.coverage_registry import resolve_domain_coverage_planning

        planning = resolve_domain_coverage_planning("mobile_messages_fixture")
        base_profile = planning.resolve_profile(
            "mobile_messages_smoke",
            "mobile_messages_smoke_v1",
        )
        constrained_profile = replace(
            base_profile,
            mandatory_floors={
                "mobile.search_deterministic_multi_result": 2,
            },
            balance_weights={
                "mobile.search_deterministic_multi_result": 1,
            },
        )

        with self.assertRaisesRegex(
            CoveragePlanValidationError,
            "exceed the maximum for coverage cell",
        ):
            compile_coverage_plan(
                catalog=planning.catalog,
                coverage_profile=constrained_profile,
                version_registry=planning.version_registry,
                selected_features=("enable_branching",),
                target_accepted_sample_count=2,
                target_candidate_count=3,
                admitted_capacity=planning.resolve_capacity(None),
            )

    def test_catalog_rejects_out_of_range_or_conflicting_grounding_identity(
        self,
    ) -> None:
        from synthesis.coverage import CoveragePlanValidationError, compile_coverage_plan
        from synthesis.coverage_registry import resolve_domain_coverage_planning

        planning = resolve_domain_coverage_planning("contacts_fixture")
        profile = planning.resolve_profile(
            "contacts_smoke",
            "contacts_smoke_v1",
        )
        lookup, followup, recovery = planning.catalog.cells
        invalid_catalogs = (
            (
                replace(
                    planning.catalog,
                    cells=(
                        replace(
                            lookup,
                            grounding_unit_indices=(0, 1, 2, 3, 4, 99),
                        ),
                        followup,
                        recovery,
                    ),
                ),
                "grounding unit index exceeds declared grounding context size",
            ),
            (
                replace(
                    planning.catalog,
                    cells=(
                        lookup,
                        replace(
                            followup,
                            grounding_unit_ids=(
                                "conflicting_alice",
                                *followup.grounding_unit_ids[1:],
                            ),
                        ),
                        recovery,
                    ),
                ),
                "conflicting stable unit ids",
            ),
        )
        for catalog, message in invalid_catalogs:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    CoveragePlanValidationError,
                    message,
                ):
                    compile_coverage_plan(
                        catalog=catalog,
                        coverage_profile=profile,
                        version_registry=planning.version_registry,
                        selected_features=(),
                        target_accepted_sample_count=2,
                        target_candidate_count=3,
                        admitted_capacity=planning.resolve_capacity_for_catalog(
                            catalog,
                            None,
                        ),
                    )

    def test_plan_rejects_overlapping_grounding_reuse_even_with_aggregate_capacity(
        self,
    ) -> None:
        from synthesis.coverage import CoveragePlanValidationError, compile_coverage_plan
        from synthesis.coverage_registry import resolve_domain_coverage_planning

        planning = resolve_domain_coverage_planning("mobile_messages_fixture")
        base_profile = planning.resolve_profile(
            "mobile_messages_smoke",
            "mobile_messages_smoke_v1",
        )
        overlapping_profile = replace(
            base_profile,
            mandatory_floors={
                "mobile.reminder_from_message": 5,
                "mobile.search_with_sender_fallback": 1,
            },
            balance_weights={
                "mobile.reminder_from_message": 1,
                "mobile.search_with_sender_fallback": 1,
            },
            max_accepted_samples_per_grounding_unit=1,
        )

        with self.assertRaisesRegex(
            CoveragePlanValidationError,
            "exceed declared usable grounding capacity",
        ):
            compile_coverage_plan(
                catalog=planning.catalog,
                coverage_profile=overlapping_profile,
                version_registry=planning.version_registry,
                selected_features=("enable_branching",),
                target_accepted_sample_count=6,
                target_candidate_count=9,
                admitted_capacity=planning.resolve_capacity(None),
            )

    def test_representative_profiles_declare_pilot_and_campaign_capacity(
        self,
    ) -> None:
        from synthesis.coverage import compile_coverage_plan
        from synthesis.coverage_assignments import issue_initial_coverage_assignments
        from synthesis.coverage_registry import resolve_domain_coverage_planning
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.seeds import DomainSeed

        profiles = (
            (
                "contacts_fixture",
                "contacts_representative",
                "contacts_representative_v1",
                12,
            ),
            (
                "mobile_messages_fixture",
                "mobile_messages_representative",
                "mobile_messages_representative_v1",
                12,
            ),
            (
                "workspace_tasks_fixture",
                "workspace_tasks_representative",
                "workspace_tasks_representative_v1",
                12,
            ),
            (
                "contacts_fixture",
                "contacts_representative",
                "contacts_representative_v2",
                30,
            ),
            (
                "mobile_messages_fixture",
                "mobile_messages_representative",
                "mobile_messages_representative_v2",
                30,
            ),
            (
                "workspace_tasks_fixture",
                "workspace_tasks_representative",
                "workspace_tasks_representative_v2",
                30,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for domain_id, profile_id, version, target in profiles:
                with self.subTest(domain_id=domain_id, target=target):
                    planning = resolve_domain_coverage_planning(domain_id)
                    coverage_profile = planning.resolve_profile(
                        profile_id,
                        version,
                    )
                    catalog = planning.resolve_catalog(
                        coverage_profile.catalog_version
                    )
                    plan = compile_coverage_plan(
                        catalog=catalog,
                        coverage_profile=coverage_profile,
                        version_registry=planning.version_registry,
                        selected_features=("enable_branching",),
                        target_accepted_sample_count=target,
                        target_candidate_count=target * 2,
                        admitted_capacity=planning.resolve_capacity_for_catalog(
                            catalog,
                            None,
                        ),
                    )
                    seed = DomainSeed(
                        seed_id=f"seed_{domain_id}_capacity",
                        domain=domain_id,
                        description="Verify overlap-aware grounding allocation.",
                        task_taxonomy=(),
                    )
                    bundle = build_domain_pipeline_bundle(
                        seed,
                        Path(tmp) / domain_id,
                        representative_fixture=(
                            catalog.version.endswith("_v2")
                        ),
                    )
                    assert bundle.generation_spec is not None
                    assignments = issue_initial_coverage_assignments(
                        plan=plan,
                        catalog=catalog,
                        spec=bundle.generation_spec,
                    )
                    reuse_counts: dict[str, int] = {}
                    cells_by_id = {
                        cell.cell_id: cell
                        for cell in catalog.cells
                    }
                    for assignment in assignments:
                        cell = cells_by_id[assignment.cell_id]
                        grounding_unit_id = next(
                            unit_id
                            for index, unit_id in zip(
                                cell.grounding_unit_indices,
                                cell.grounding_unit_ids,
                            )
                            if index == assignment.grounding_unit_index
                        )
                        reuse_counts[grounding_unit_id] = (
                            reuse_counts.get(grounding_unit_id, 0) + 1
                        )

                    self.assertEqual(plan.target_accepted_sample_count, target)
                    self.assertEqual(plan.attempt_ceiling, target * 2)
                    self.assertEqual(len(assignments), target)
                    self.assertLessEqual(max(reuse_counts.values()), 2)

    def test_campaign_run_profiles_preview_bounded_versioned_plans(self) -> None:
        from synthesis.pipeline import preview_coverage_plan
        from synthesis.run_profiles import load_run_profile

        fixtures = (
            ("contacts-coverage-pilot-12.json", 12, "contacts_coverage_v1"),
            (
                "mobile-messages-coverage-pilot-12.json",
                12,
                "mobile_messages_coverage_v1",
            ),
            (
                "workspace-tasks-coverage-pilot-12.json",
                12,
                "workspace_tasks_coverage_v1",
            ),
            ("contacts-coverage-campaign-30.json", 30, "contacts_coverage_v2"),
            (
                "mobile-messages-coverage-campaign-30.json",
                30,
                "mobile_messages_coverage_v2",
            ),
            (
                "workspace-tasks-coverage-campaign-30.json",
                30,
                "workspace_tasks_coverage_v2",
            ),
        )
        fixture_root = Path("tests/fixtures/run_profiles")
        for fixture_name, target, catalog_version in fixtures:
            with self.subTest(fixture=fixture_name):
                profile = load_run_profile(fixture_root / fixture_name)
                plan = preview_coverage_plan(profile)

                self.assertEqual(plan.target_accepted_sample_count, target)
                self.assertEqual(plan.target_candidate_count, target * 2)
                self.assertEqual(plan.attempt_ceiling, target * 2)
                self.assertEqual(plan.catalog["version"], catalog_version)
                self.assertEqual(
                    sum(
                        int(cell["target_count"])
                        for cell in plan.target_distribution
                    ),
                    target,
                )

    def test_fake_provider_three_domain_pilots_are_structurally_non_degenerate(
        self,
    ) -> None:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        fixture_names = (
            "contacts-coverage-pilot-12.json",
            "mobile-messages-coverage-pilot-12.json",
            "workspace-tasks-coverage-pilot-12.json",
        )
        fixture_root = Path("tests/fixtures/run_profiles")
        with tempfile.TemporaryDirectory() as tmp:
            for fixture_name in fixture_names:
                with self.subTest(fixture=fixture_name):
                    profile = load_run_profile(fixture_root / fixture_name)
                    provider = ThreeDomainCoverageFakeProvider()
                    result = run_foundation_pipeline(
                        Path(tmp) / profile.profile_id,
                        dataset_version=profile.dataset_version,
                        coverage_scheduler_factory=(
                            build_coverage_assignment_scheduler_factory(provider)
                        ),
                        seed_override=profile.seed,
                        run_profile_metadata=profile.sanitized_metadata(),
                        run_profile=profile,
                    )

                    self.assertEqual(result.accepted_count, 12)
                    self.assertEqual(result.rejected_count, 0)
                    assert result.coverage_evidence_path is not None
                    evidence = json.loads(
                        result.coverage_evidence_path.read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(
                        evidence["fulfillment"]["status"],
                        "fulfilled",
                    )
                    self.assertLess(
                        evidence["distributions"]["structural_families"][
                            "largest_family_share"
                        ],
                        0.5,
                    )
                    self.assertGreaterEqual(
                        evidence["distributions"]["grounding_reuse"][
                            "distinct_grounding_count"
                        ],
                        6,
                    )
                    self.assertEqual(
                        evidence["counts"]["attempted"],
                        12,
                    )
                    self.assertEqual(
                        evidence["counts"]["attempt_ceiling"],
                        24,
                    )

    def test_fake_campaign_confirms_structural_cells_saturate_by_pilot(
        self,
    ) -> None:
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        fixture_pairs = (
            (
                "contacts-coverage-pilot-12.json",
                "contacts-coverage-campaign-30.json",
            ),
            (
                "mobile-messages-coverage-pilot-12.json",
                "mobile-messages-coverage-campaign-30.json",
            ),
            (
                "workspace-tasks-coverage-pilot-12.json",
                "workspace-tasks-coverage-campaign-30.json",
            ),
        )
        fixture_root = Path("tests/fixtures/run_profiles")
        with tempfile.TemporaryDirectory() as tmp:
            for pilot_name, campaign_name in fixture_pairs:
                with self.subTest(campaign=campaign_name):
                    evidence_records = []
                    for fixture_name in (pilot_name, campaign_name):
                        profile = load_run_profile(
                            fixture_root / fixture_name
                        )
                        result = run_foundation_pipeline(
                            Path(tmp) / profile.profile_id,
                            dataset_version=profile.dataset_version,
                            coverage_scheduler_factory=(
                                build_coverage_assignment_scheduler_factory(
                                    ThreeDomainCoverageFakeProvider()
                                )
                            ),
                            seed_override=profile.seed,
                            run_profile_metadata=profile.sanitized_metadata(),
                            run_profile=profile,
                        )
                        self.assertEqual(result.rejected_count, 0)
                        assert result.coverage_evidence_path is not None
                        evidence_records.append(
                            json.loads(
                                result.coverage_evidence_path.read_text(
                                    encoding="utf-8"
                                )
                            )
                        )

                    pilot, campaign = evidence_records
                    self.assertEqual(pilot["counts"]["accepted"], 12)
                    self.assertEqual(campaign["counts"]["accepted"], 30)
                    self.assertEqual(campaign["counts"]["attempted"], 30)
                    self.assertEqual(campaign["counts"]["attempt_ceiling"], 60)
                    self.assertEqual(
                        campaign["fulfillment"]["status"],
                        "fulfilled",
                    )
                    self.assertEqual(
                        pilot["distributions"]["structural_families"][
                            "distinct_count"
                        ],
                        campaign["distributions"]["structural_families"][
                            "distinct_count"
                        ],
                    )


if __name__ == "__main__":
    unittest.main()
