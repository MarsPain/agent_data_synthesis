from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


class CoveragePlanCompilationTest(unittest.TestCase):
    def test_contacts_inputs_compile_to_one_deterministic_sanitized_plan(self) -> None:
        from synthesis.contacts_coverage import (
            build_contacts_coverage_capacity,
            contacts_coverage_catalog,
            contacts_coverage_version_registry,
            resolve_contacts_coverage_profile,
        )
        from synthesis.coverage import compile_coverage_plan

        catalog = contacts_coverage_catalog()
        coverage_profile = resolve_contacts_coverage_profile(
            "contacts_smoke",
            "contacts_smoke_v1",
        )
        capacity = build_contacts_coverage_capacity(contact_count=6)
        version_registry = contacts_coverage_version_registry()

        first = compile_coverage_plan(
            catalog=catalog,
            coverage_profile=coverage_profile,
            version_registry=version_registry,
            selected_features=(),
            target_accepted_sample_count=6,
            target_candidate_count=9,
            admitted_capacity=capacity,
            balance_weight_overrides={"contacts.lookup_by_name": 2},
        )
        second = compile_coverage_plan(
            catalog=catalog,
            coverage_profile=coverage_profile,
            version_registry=version_registry,
            selected_features=(),
            target_accepted_sample_count=6,
            target_candidate_count=9,
            admitted_capacity=capacity,
            balance_weight_overrides={"contacts.lookup_by_name": 2},
        )

        self.assertEqual(first.to_bytes(), second.to_bytes())
        self.assertTrue(first.to_bytes().endswith(b"\n"))
        record = json.loads(first.to_bytes())
        self.assertEqual(
            set(record),
            {
                "schema_version",
                "plan_id",
                "plan_hash",
                "domain_id",
                "catalog",
                "coverage_profile",
                "selected_features",
                "target_accepted_sample_count",
                "target_candidate_count",
                "target_distribution",
                "attempt_ceiling",
                "policies",
                "cell_requirements",
                "overrides",
                "admitted_capacity",
            },
        )
        self.assertEqual(record["schema_version"], "coverage_plan_v1")
        self.assertEqual(record["domain_id"], "contacts_fixture")
        self.assertEqual(record["target_accepted_sample_count"], 6)
        self.assertEqual(record["target_candidate_count"], 9)
        self.assertEqual(record["attempt_ceiling"], 9)
        self.assertEqual(
            record["target_distribution"],
            [
                {
                    "cell_id": "contacts.followup_after_lookup",
                    "mandatory_floor": 1,
                    "balance_weight": 1,
                    "target_count": 2,
                },
                {
                    "cell_id": "contacts.lookup_by_name",
                    "mandatory_floor": 1,
                    "balance_weight": 2,
                    "target_count": 4,
                },
            ],
        )
        self.assertEqual(
            record["policies"],
            {
                "mandatory_floors": {
                    "policy_version": "mandatory_floors_v1",
                    "total_floor": 2,
                },
                "balancing": {
                    "policy_version": "weighted_lowest_saturation_v1",
                    "tie_break": "cell_id_ascending",
                },
                "grounding_reuse": {
                    "policy_version": "grounding_reuse_v1",
                    "max_accepted_samples_per_grounding_unit": 2,
                },
                "attempts": {
                    "policy_version": "bounded_attempt_ratio_v1",
                    "multiplier_numerator": 3,
                    "multiplier_denominator": 2,
                },
            },
        )
        self.assertEqual(
            record["cell_requirements"],
            [
                {
                    "cell_id": "contacts.followup_after_lookup",
                    "required_features": [],
                },
                {
                    "cell_id": "contacts.lookup_by_name",
                    "required_features": [],
                },
            ],
        )
        self.assertRegex(record["catalog"]["catalog_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(
            record["coverage_profile"]["profile_hash"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertRegex(record["admitted_capacity"]["capacity_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            record["plan_hash"],
            "sha256:a0a0f3094efa226ea731a4dfcc2202c99c9a38efa77254e5c237620089f59721",
        )
        self.assertEqual(record["plan_id"], "coverage_plan_a0a0f3094efa226e")

    def test_invalid_or_impossible_plan_inputs_fail_before_generation(self) -> None:
        from synthesis.contacts_coverage import (
            build_contacts_coverage_capacity,
            contacts_coverage_catalog,
            contacts_coverage_version_registry,
            resolve_contacts_coverage_profile,
        )
        from synthesis.coverage import (
            CoverageAttemptPolicy,
            CoveragePlanValidationError,
            compile_coverage_plan,
        )

        catalog = contacts_coverage_catalog()
        coverage_profile = resolve_contacts_coverage_profile(
            "contacts_smoke",
            "contacts_smoke_v1",
        )
        capacity = build_contacts_coverage_capacity(contact_count=6)
        version_registry = contacts_coverage_version_registry()

        def compile_with(**changes: object) -> object:
            arguments: dict[str, object] = {
                "catalog": catalog,
                "coverage_profile": coverage_profile,
                "version_registry": version_registry,
                "selected_features": (),
                "target_accepted_sample_count": 6,
                "target_candidate_count": 9,
                "admitted_capacity": capacity,
                "balance_weight_overrides": {},
            }
            arguments.update(changes)
            return compile_coverage_plan(**arguments)  # type: ignore[arg-type]

        duplicate_dimensions = replace(
            catalog.cells[0],
            cell_id="contacts.lookup_duplicate",
        )
        feature_cell = replace(
            catalog.cells[0],
            required_features=("enable_branching",),
        )
        invalid_cases = (
            (
                "unknown catalog version",
                lambda: compile_with(
                    catalog=replace(catalog, schema_version="coverage_catalog_v99")
                ),
                "unknown coverage catalog",
            ),
            (
                "unknown profile version",
                lambda: resolve_contacts_coverage_profile(
                    "contacts_smoke",
                    "contacts_smoke_v99",
                ),
                "unknown contacts coverage profile",
            ),
            (
                "unknown matching catalog and profile versions",
                lambda: compile_with(
                    catalog=replace(
                        catalog,
                        version="contacts_coverage_v99",
                    ),
                    coverage_profile=replace(
                        coverage_profile,
                        version="contacts_smoke_v99",
                        catalog_version="contacts_coverage_v99",
                    ),
                ),
                "unknown coverage catalog version",
            ),
            (
                "unknown matching profile version",
                lambda: compile_with(
                    coverage_profile=replace(
                        coverage_profile,
                        version="contacts_smoke_v99",
                    ),
                ),
                "unknown coverage profile version",
            ),
            (
                "invented v1 identities",
                lambda: compile_with(
                    catalog=replace(
                        catalog,
                        catalog_id="invented",
                        version="invented_v1",
                    ),
                    coverage_profile=replace(
                        coverage_profile,
                        catalog_id="invented",
                        catalog_version="invented_v1",
                    ),
                ),
                "unknown coverage catalog version",
            ),
            (
                "unknown dimension",
                lambda: compile_with(
                    catalog=replace(
                        catalog,
                        dimensions=(*catalog.dimensions, "provider_confidence"),
                        cells=tuple(
                            replace(
                                cell,
                                dimensions={
                                    **cell.dimensions,
                                    "provider_confidence": "high",
                                },
                            )
                            for cell in catalog.cells
                        ),
                    )
                ),
                "unknown coverage dimensions",
            ),
            (
                "duplicate cell id",
                lambda: compile_with(
                    catalog=replace(catalog, cells=(*catalog.cells, catalog.cells[0]))
                ),
                "duplicate coverage cell id",
            ),
            (
                "duplicate cell dimensions",
                lambda: compile_with(
                    catalog=replace(
                        catalog,
                        cells=(*catalog.cells, duplicate_dimensions),
                    )
                ),
                "duplicate coverage cell dimensions",
            ),
            (
                "contradictory attempt policy",
                lambda: compile_with(
                    coverage_profile=replace(
                        coverage_profile,
                        attempt_policy=CoverageAttemptPolicy(
                            policy_version="bounded_attempt_ratio_v1",
                            multiplier_numerator=1,
                            multiplier_denominator=2,
                        ),
                    )
                ),
                "attempt policy contradicts",
            ),
            (
                "boolean grounding reuse limit",
                lambda: compile_with(
                    coverage_profile=replace(
                        coverage_profile,
                        max_accepted_samples_per_grounding_unit=True,
                    )
                ),
                "grounding reuse limit must be a positive integer",
            ),
            (
                "boolean attempt multiplier",
                lambda: compile_with(
                    coverage_profile=replace(
                        coverage_profile,
                        attempt_policy=CoverageAttemptPolicy(
                            policy_version="bounded_attempt_ratio_v1",
                            multiplier_numerator=True,
                            multiplier_denominator=1,
                        ),
                    )
                ),
                "attempt policy multipliers must be positive integers",
            ),
            (
                "unavailable feature",
                lambda: compile_with(
                    catalog=replace(
                        catalog,
                        cells=(feature_cell, catalog.cells[1]),
                    )
                ),
                "requires unavailable features",
            ),
            (
                "unknown override cell",
                lambda: compile_with(
                    balance_weight_overrides={"contacts.unknown": 2}
                ),
                "unknown balance-weight override cell",
            ),
            (
                "override exceeds bound",
                lambda: compile_with(
                    balance_weight_overrides={"contacts.lookup_by_name": 5}
                ),
                "must be between 1 and 4",
            ),
            (
                "insufficient capacity",
                lambda: compile_with(
                    admitted_capacity=build_contacts_coverage_capacity(
                        contact_count=2
                    ),
                    target_accepted_sample_count=5,
                    target_candidate_count=8,
                ),
                "capacity is insufficient",
            ),
            (
                "candidate budget below attempt ceiling",
                lambda: compile_with(target_candidate_count=8),
                "target candidate count must equal the profile-derived attempt ceiling",
            ),
            (
                "statically impossible floors",
                lambda: compile_with(
                    coverage_profile=replace(
                        coverage_profile,
                        mandatory_floors={
                            "contacts.lookup_by_name": 4,
                            "contacts.followup_after_lookup": 4,
                        },
                    )
                ),
                "mandatory floors exceed target",
            ),
        )
        for label, operation, message in invalid_cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(CoveragePlanValidationError, message):
                    operation()

    def test_programmatic_preview_can_write_the_exact_sanitized_plan(self) -> None:
        from synthesis.pipeline import preview_coverage_plan
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-smoke.json")
        )
        self.assertEqual(profile.generation.target_candidate_count, 9)
        assert profile.coverage_profile is not None
        self.assertEqual(
            profile.coverage_profile.target_accepted_sample_count,
            6,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "coverage_plan.json"

            plan = preview_coverage_plan(
                profile,
                output_path=output_path,
            )

            self.assertEqual(output_path.read_bytes(), plan.to_bytes())
            self.assertEqual(
                json.loads(output_path.read_bytes())["target_accepted_sample_count"],
                6,
            )
            self.assertEqual(
                set(path.name for path in output_path.parent.iterdir()),
                {"coverage_plan.json"},
            )

    def test_programmatic_preview_uses_only_admitted_environment_capacity(self) -> None:
        from synthesis.coverage import CoveragePlanValidationError
        from synthesis.environments import ContactRecord, ContactsEnvironmentInput
        from synthesis.pipeline import preview_coverage_plan
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-coverage-smoke.json")
        )
        admitted_input = ContactsEnvironmentInput(
            contacts=(
                ContactRecord(
                    name="Only Contact",
                    email="only.contact@example.test",
                ),
            ),
            followups=(),
            source_bundle_id="source_bundle_capacity_probe",
            source_policy_hash="sha256:" + "1" * 64,
        )

        with self.assertRaisesRegex(
            CoveragePlanValidationError,
            "capacity is insufficient",
        ):
            preview_coverage_plan(
                profile,
                admitted_environment_input=admitted_input,
            )


if __name__ == "__main__":
    unittest.main()
