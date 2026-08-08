from __future__ import annotations

import copy
import unittest
from dataclasses import replace


class DomainPackContractsTest(unittest.TestCase):
    def test_initial_descriptors_have_hash_bound_logical_identity_and_catalogs(self) -> None:
        from synthesis.domain_pack import (
            REQUIRED_PLAN_COMPONENT_KINDS,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        registry = initial_domain_pack_registry()
        expected_capabilities = {
            "contacts": {
                "contact_lookup",
                "followup_recording",
                "contact_lookup_recovery",
                "missing_contact_safe_failure",
            },
            "mobile_messages": {
                "message_search",
                "reminder_creation",
                "draft_reply",
                "message_search_recovery",
                "missing_message_safe_failure",
            },
            "workspace_tasks": {
                "item_search",
                "task_creation",
                "comment_addition",
                "item_search_recovery",
                "missing_item_safe_failure",
            },
        }

        for domain_pack_id, capability_keys in expected_capabilities.items():
            with self.subTest(domain_pack_id=domain_pack_id):
                descriptor = registry.descriptor_for(domain_pack_id)
                reference = descriptor.reference()

                self.assertEqual(reference.domain_pack_id, domain_pack_id)
                self.assertTrue(reference.pack_version.endswith("_pack_v1"))
                self.assertRegex(reference.pack_hash, r"^sha256:[0-9a-f]{64}$")
                self.assertEqual(
                    descriptor.canonical_bytes(),
                    descriptor.canonical_bytes(),
                )
                self.assertEqual(
                    {item.capability_key for item in descriptor.capability_references},
                    capability_keys,
                )
                self.assertTrue(descriptor.component_contracts)
                self.assertTrue(descriptor.runtime_contracts)
                self.assertEqual(
                    {item.component_kind for item in descriptor.component_contracts},
                    REQUIRED_PLAN_COMPONENT_KINDS,
                )
                for component in descriptor.component_contracts:
                    self.assertNotEqual(
                        component.component_hash,
                        canonical_domain_pack_hash(
                            {
                                "component_kind": component.component_kind,
                                "component_id": component.component_id,
                                "component_version": component.component_version,
                            }
                        ),
                    )
                for runtime in descriptor.runtime_contracts:
                    self.assertRegex(
                        runtime.runtime_implementation_hash,
                        r"^sha256:[0-9a-f]{64}$",
                    )
                    self.assertNotEqual(
                        runtime.runtime_contract_hash,
                        canonical_domain_pack_hash(
                            {
                                "runtime_id": runtime.runtime_id,
                                "runtime_version": runtime.runtime_version,
                                "runtime_contract_version": runtime.runtime_contract_version,
                            }
                        ),
                    )

        workspace_task_types = {
            item.task_type_key
            for item in registry.descriptor_for("workspace_tasks").task_capability_projections
        }
        self.assertEqual(
            workspace_task_types,
            {
                "workspace_item_search",
                "workspace_task_creation",
                "workspace_comment_update",
            },
        )

    def test_pure_planning_emits_a_byte_stable_hash_bound_plan(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            DomainPack,
            DomainPlan,
            DomainPlanningIntent,
            REQUIRED_PLAN_COMPONENT_KINDS,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("workspace_tasks")
        capabilities = {
            item.capability_key: item for item in descriptor.capability_references
        }
        intent = DomainPlanningIntent(
            domain_pack_reference=descriptor.reference(),
            task_type_keys=("workspace_task_creation",),
            capability_references=(
                capabilities["item_search"],
                capabilities["task_creation"],
            ),
            runtime_contract=descriptor.runtime_contracts[0],
        )
        admitted_source = AdmittedSource(
            source_id="workspace_fixture_source_v1",
            source_schema_version="workspace_source_v1",
            source_content_hash=canonical_domain_pack_hash({"fixture": "workspace"}),
            admission_policy_id="fixture_source_policy_v1",
            admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
        )

        self.assertEqual(
            DomainPlanningIntent.from_record(intent.to_record()).to_record(),
            intent.to_record(),
        )
        first = DomainPack(descriptor).plan(intent, admitted_source)
        second = DomainPack(descriptor).plan(intent, admitted_source)

        self.assertIsInstance(first, DomainPlan)
        self.assertEqual(first.to_record(), second.to_record())
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(
            first.plan_id,
            "domain_plan_" + first.plan_hash.removeprefix("sha256:")[:16],
        )
        self.assertEqual(first.domain_pack_reference, descriptor.reference())
        self.assertEqual(
            first.plan_requirements.component_contracts(),
            tuple(
                sorted(
                    descriptor.component_contracts,
                    key=lambda item: item.component_kind,
                )
            ),
        )
        requirements_record = first.to_record()["plan_requirements"]
        self.assertEqual(
            set(requirements_record),
            REQUIRED_PLAN_COMPONENT_KINDS,
        )
        self.assertEqual(
            requirements_record["coverage_profile"]["component_kind"],
            "coverage_profile",
        )
        self.assertEqual(
            requirements_record["compiled_coverage_plan"]["component_kind"],
            "compiled_coverage_plan",
        )
        self.assertEqual(
            requirements_record["mutation_admission_mode"]["component_kind"],
            "mutation_admission_mode",
        )
        self.assertEqual(
            requirements_record["release_machine_gates"]["component_kind"],
            "release_machine_gates",
        )

    def test_canonical_descriptor_and_plan_records_round_trip_and_detect_tampering(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            DomainPack,
            DomainPackContractError,
            DomainPackDescriptor,
            DomainPackRegistry,
            DomainPlan,
            DomainPlanningIntent,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("contacts")
        round_tripped_descriptor = DomainPackDescriptor.from_record(descriptor.to_record())
        self.assertEqual(round_tripped_descriptor.canonical_bytes(), descriptor.canonical_bytes())
        with self.assertRaises(DomainPackContractError):
            replace(
                descriptor,
                capability_references=list(descriptor.capability_references),
            )
        with self.assertRaises(DomainPackContractError):
            replace(
                descriptor.task_capability_projections[0],
                capability_references=list(
                    descriptor.task_capability_projections[0].capability_references
                ),
            )
        with self.assertRaises(DomainPackContractError):
            DomainPackRegistry([descriptor])

        contact_lookup = next(
            item
            for item in descriptor.capability_references
            if item.capability_key == "contact_lookup"
        )
        plan = DomainPack(descriptor).plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=("contact_lookup",),
                capability_references=(contact_lookup,),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            AdmittedSource(
                source_id="contacts_fixture_source_v1",
                source_schema_version="contacts_source_v1",
                source_content_hash=canonical_domain_pack_hash({"fixture": "contacts"}),
                admission_policy_id="fixture_source_policy_v1",
                admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
            ),
        )
        self.assertIsInstance(plan, DomainPlan)
        self.assertEqual(
            DomainPlan.from_record(plan.to_record(), descriptor=descriptor),
            plan,
        )

        tampered = copy.deepcopy(plan.to_record())
        tampered["plan_hash"] = "sha256:" + "0" * 64
        with self.assertRaises(DomainPackContractError):
            DomainPlan.from_record(tampered, descriptor=descriptor)

        noncanonical = copy.deepcopy(plan.to_record())
        noncanonical["compatibility_mapping"] = None
        with self.assertRaises(DomainPackContractError):
            DomainPlan.from_record(noncanonical, descriptor=descriptor)

        cross_pack = copy.deepcopy(plan.to_record())
        cross_pack["capability_references"][0]["domain_pack_id"] = "workspace_tasks"
        content = {
            key: value
            for key, value in cross_pack.items()
            if key not in {"plan_id", "plan_hash"}
        }
        plan_hash = canonical_domain_pack_hash(content)
        cross_pack["plan_hash"] = plan_hash
        cross_pack["plan_id"] = (
            "domain_plan_" + plan_hash.removeprefix("sha256:")[:16]
        )
        with self.assertRaises(DomainPackContractError) as raised:
            DomainPlan.from_record(cross_pack, descriptor=descriptor)
        self.assertEqual(raised.exception.reason_code, "cross_pack_capability_reference")

    def test_planning_fails_closed_with_bounded_reference_reasons(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            DomainCapabilityReference,
            DomainPack,
            DomainPlanningIntent,
            PlanFailure,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        registry = initial_domain_pack_registry()
        descriptor = registry.descriptor_for("workspace_tasks")
        item_search = next(
            item
            for item in descriptor.capability_references
            if item.capability_key == "item_search"
        )
        source = AdmittedSource(
            source_id="workspace_fixture_source_v1",
            source_schema_version="workspace_source_v1",
            source_content_hash=canonical_domain_pack_hash({"fixture": "workspace"}),
            admission_policy_id="fixture_source_policy_v1",
            admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
        )
        common = {
            "domain_pack_reference": descriptor.reference(),
            "task_type_keys": ("workspace_item_search",),
            "runtime_contract": descriptor.runtime_contracts[0],
        }
        intents = {
            "duplicate_capability_reference": DomainPlanningIntent(
                capability_references=(item_search, item_search),
                **common,
            ),
            "cross_pack_capability_reference": DomainPlanningIntent(
                capability_references=(
                    DomainCapabilityReference(
                        domain_pack_id="contacts",
                        capability_key="contact_lookup",
                        capability_contract_version="contacts_contact_lookup_contract_v1",
                    ),
                ),
                **common,
            ),
            "unsupported_capability_contract_version": DomainPlanningIntent(
                capability_references=(
                    replace(
                        item_search,
                        capability_contract_version="item_search_contract_v999",
                    ),
                ),
                **common,
            ),
            "unknown_capability_reference": DomainPlanningIntent(
                capability_references=(
                    DomainCapabilityReference(
                        domain_pack_id="workspace_tasks",
                        capability_key="unknown_capability",
                        capability_contract_version="unknown_capability_contract_v1",
                    ),
                ),
                **common,
            ),
            "unsupported_pack_version": DomainPlanningIntent(
                capability_references=(item_search,),
                domain_pack_reference=replace(
                    descriptor.reference(),
                    pack_version="workspace_tasks_pack_v999",
                ),
                task_type_keys=("workspace_item_search",),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            "unknown_task_type_projection": DomainPlanningIntent(
                capability_references=(item_search,),
                task_type_keys=("workspace_item_search_recovery",),
                domain_pack_reference=descriptor.reference(),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
        }

        for expected_reason, intent in intents.items():
            with self.subTest(reason=expected_reason):
                result = DomainPack(descriptor).plan(intent, source)
                self.assertIsInstance(result, PlanFailure)
                self.assertEqual(result.reason_code, expected_reason)

    def test_reusing_a_pack_version_with_changed_descriptor_bytes_fails_closed(self) -> None:
        from synthesis.domain_pack import (
            DomainPackContractError,
            DomainPackRegistry,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("contacts")
        changed_component = replace(
            descriptor.component_contracts[0],
            component_hash=canonical_domain_pack_hash({"changed": "bytes"}),
        )
        changed_descriptor = replace(
            descriptor,
            component_contracts=(
                changed_component,
                *descriptor.component_contracts[1:],
            ),
        )

        with self.assertRaises(DomainPackContractError) as raised:
            DomainPackRegistry((descriptor, changed_descriptor))

        self.assertEqual(raised.exception.reason_code, "pack_version_reused_with_different_content")

        changed_runtime_descriptor = replace(
            descriptor,
            runtime_contracts=(
                replace(
                    descriptor.runtime_contracts[0],
                    runtime_implementation_hash=canonical_domain_pack_hash(
                        {"runtime_implementation": "changed"}
                    ),
                ),
            ),
        )
        with self.assertRaises(DomainPackContractError) as raised:
            DomainPackRegistry((descriptor, changed_runtime_descriptor))

        self.assertEqual(raised.exception.reason_code, "pack_version_reused_with_different_content")

    def test_canonical_contract_records_reject_secrets_and_oversized_values(self) -> None:
        from synthesis.domain_pack import (
            DomainPackContractError,
            MAX_DOMAIN_PACK_TEXT_BYTES,
            canonical_domain_pack_json,
        )

        unsafe_records = (
            {"authorization": "Bearer secret-test-key"},
            {"nested_api_key": "not-safe"},
            {"field": "Authorization: Bearer secret-test-key"},
            {"source": "/Users/example/private.json"},
            {"field": "x" * (MAX_DOMAIN_PACK_TEXT_BYTES + 1)},
        )
        for record in unsafe_records:
            with self.subTest(record=next(iter(record))):
                with self.assertRaises(DomainPackContractError):
                    canonical_domain_pack_json(record)

    def test_compatibility_resolution_is_source_and_projection_scoped(self) -> None:
        from synthesis.domain_pack import (
            CompatibilityMapping,
            CompatibilityMappingSet,
            CompatibilityResolutionFailure,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("contacts")
        semantic_mapping = CompatibilityMapping.create(
            source_schema_version="run_profile_v1",
            projection_kind="semantic_domain",
            legacy_value="contacts_fixture",
            mapping_version="contacts_profile_mapping_v1",
            target=descriptor.reference(),
        )
        runtime_mapping = CompatibilityMapping.create(
            source_schema_version="run_profile_v1",
            projection_kind="runtime",
            legacy_value="contacts_fixture",
            mapping_version="contacts_runtime_mapping_v1",
            target=descriptor.runtime_contracts[0],
        )
        mappings = CompatibilityMappingSet(
            mapping_set_id="contacts_mapping_set_v1",
            mapping_set_version="contacts_mapping_set_v1",
            mappings=(semantic_mapping, runtime_mapping),
        )

        semantic_result = mappings.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="semantic_domain",
            legacy_value="contacts_fixture",
        )
        runtime_result = mappings.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="runtime",
            legacy_value="contacts_fixture",
        )
        missing_result = mappings.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="capability",
            legacy_value="contacts_fixture",
        )

        self.assertEqual(semantic_result.target, descriptor.reference())
        self.assertEqual(runtime_result.target, descriptor.runtime_contracts[0])
        self.assertIsInstance(missing_result, CompatibilityResolutionFailure)
        self.assertEqual(missing_result.reason_code, "unknown_compatibility_mapping")

        ambiguous = CompatibilityMappingSet(
            mapping_set_id="contacts_mapping_set_v2",
            mapping_set_version="contacts_mapping_set_v2",
            mappings=(
                semantic_mapping,
                CompatibilityMapping.create(
                    source_schema_version="run_profile_v1",
                    projection_kind="semantic_domain",
                    legacy_value="contacts_fixture",
                    mapping_version="contacts_profile_mapping_v2",
                    target=descriptor.reference(),
                ),
            ),
        ).resolve(
            source_schema_version="run_profile_v1",
            projection_kind="semantic_domain",
            legacy_value="contacts_fixture",
        )
        self.assertIsInstance(ambiguous, CompatibilityResolutionFailure)
        self.assertEqual(ambiguous.reason_code, "ambiguous_compatibility_mapping")

    def test_assessment_and_subject_bind_exact_evidence_without_qualification(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            DomainAssessment,
            DomainEvidenceReference,
            DomainPack,
            DomainPlan,
            DomainPlanningIntent,
            QualificationArtifactReference,
            QualificationSubject,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("workspace_tasks")
        item_search = next(
            item
            for item in descriptor.capability_references
            if item.capability_key == "item_search"
        )
        plan = DomainPack(descriptor).plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=("workspace_item_search",),
                capability_references=(item_search,),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            AdmittedSource(
                source_id="workspace_fixture_source_v1",
                source_schema_version="workspace_source_v1",
                source_content_hash=canonical_domain_pack_hash({"fixture": "workspace"}),
                admission_policy_id="fixture_source_policy_v1",
                admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
            ),
        )
        self.assertIsInstance(plan, DomainPlan)

        evidence = DomainEvidenceReference(
            evidence_id="workspace_execution_evidence_v1",
            evidence_schema_version="workspace_execution_evidence_v1",
            evidence_hash=canonical_domain_pack_hash({"accepted": "workspace"}),
        )
        assessment = DomainAssessment.established(
            plan,
            evidence_references=(evidence,),
            established_capability_references=(item_search,),
        )
        insufficient = DomainAssessment.insufficient(
            plan,
            reason_code="evidence_missing",
        )
        self.assertEqual(assessment.status, "established")
        self.assertEqual(insufficient.status, "insufficient_evidence")
        self.assertNotIn("qualification", assessment.to_record())
        self.assertEqual(
            DomainAssessment.from_record(assessment.to_record(), plan=plan),
            assessment,
        )

        artifact = QualificationArtifactReference(
            artifact_id="workspace_release_pack_v1",
            artifact_schema_version="dataset_release_pack_v1",
            content_hash=canonical_domain_pack_hash({"release": "workspace"}),
            byte_count=123,
        )
        subject = QualificationSubject.create(
            domain_pack_reference=descriptor.reference(),
            artifact_references=(artifact,),
        )
        changed_subject = QualificationSubject.create(
            domain_pack_reference=descriptor.reference(),
            artifact_references=(
                replace(
                    artifact,
                    content_hash=canonical_domain_pack_hash({"release": "changed"}),
                ),
            ),
        )
        self.assertNotEqual(subject.subject_hash, changed_subject.subject_hash)
        self.assertNotIn("qualification", subject.to_record())
        self.assertEqual(QualificationSubject.from_record(subject.to_record()), subject)

    def test_assessment_record_rejects_hash_consistent_cross_pack_capabilities(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            DomainAssessment,
            DomainEvidenceReference,
            DomainPack,
            DomainPackContractError,
            DomainPlan,
            DomainPlanningIntent,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        descriptor = initial_domain_pack_registry().descriptor_for("workspace_tasks")
        item_search = next(
            item
            for item in descriptor.capability_references
            if item.capability_key == "item_search"
        )
        plan = DomainPack(descriptor).plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=("workspace_item_search",),
                capability_references=(item_search,),
                runtime_contract=descriptor.runtime_contracts[0],
            ),
            AdmittedSource(
                source_id="workspace_fixture_source_v1",
                source_schema_version="workspace_source_v1",
                source_content_hash=canonical_domain_pack_hash({"fixture": "workspace"}),
                admission_policy_id="fixture_source_policy_v1",
                admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
            ),
        )
        self.assertIsInstance(plan, DomainPlan)
        assessment = DomainAssessment.established(
            plan,
            evidence_references=(
                DomainEvidenceReference(
                    evidence_id="workspace_execution_evidence_v1",
                    evidence_schema_version="workspace_execution_evidence_v1",
                    evidence_hash=canonical_domain_pack_hash({"accepted": "workspace"}),
                ),
            ),
            established_capability_references=(item_search,),
        )
        cross_pack_record = copy.deepcopy(assessment.to_record())
        cross_pack_record["established_capability_references"][0]["domain_pack_id"] = (
            "contacts"
        )
        content = {
            key: value
            for key, value in cross_pack_record.items()
            if key not in {"assessment_id", "assessment_hash"}
        }
        assessment_hash = canonical_domain_pack_hash(content)
        cross_pack_record["assessment_hash"] = assessment_hash
        cross_pack_record["assessment_id"] = (
            "domain_assessment_" + assessment_hash.removeprefix("sha256:")[:16]
        )

        with self.assertRaises(DomainPackContractError) as raised:
            DomainAssessment.from_record(cross_pack_record, plan=plan)

        self.assertEqual(
            raised.exception.reason_code,
            "cross_pack_assessment_capability_reference",
        )

        unsupported_version_record = copy.deepcopy(assessment.to_record())
        unsupported_version_record["established_capability_references"][0][
            "capability_contract_version"
        ] = "workspace_tasks_item_search_contract_v999"
        content = {
            key: value
            for key, value in unsupported_version_record.items()
            if key not in {"assessment_id", "assessment_hash"}
        }
        assessment_hash = canonical_domain_pack_hash(content)
        unsupported_version_record["assessment_hash"] = assessment_hash
        unsupported_version_record["assessment_id"] = (
            "domain_assessment_" + assessment_hash.removeprefix("sha256:")[:16]
        )
        with self.assertRaises(DomainPackContractError) as raised:
            DomainAssessment.from_record(unsupported_version_record, plan=plan)

        self.assertEqual(
            raised.exception.reason_code,
            "assessment_capability_not_in_plan",
        )

    def test_planning_rejects_an_ambiguous_scoped_compatibility_mapping(self) -> None:
        from synthesis.domain_pack import (
            AdmittedSource,
            CompatibilityMapping,
            CompatibilityMappingSet,
            DomainPack,
            DomainPlanningIntent,
            LegacyProjection,
            PlanFailure,
            canonical_domain_pack_hash,
            initial_domain_pack_registry,
        )

        base_descriptor = initial_domain_pack_registry().descriptor_for("contacts")
        mapping_set = CompatibilityMappingSet(
            mapping_set_id="contacts_ambiguous_mapping_set_v1",
            mapping_set_version="contacts_ambiguous_mapping_set_v1",
            mappings=(
                CompatibilityMapping.create(
                    source_schema_version="run_profile_v1",
                    projection_kind="runtime",
                    legacy_value="contacts_fixture",
                    mapping_version="contacts_runtime_mapping_v1",
                    target=base_descriptor.runtime_contracts[0],
                ),
                CompatibilityMapping.create(
                    source_schema_version="run_profile_v1",
                    projection_kind="runtime",
                    legacy_value="contacts_fixture",
                    mapping_version="contacts_runtime_mapping_v2",
                    target=base_descriptor.runtime_contracts[0],
                ),
            ),
        )
        descriptor = replace(
            base_descriptor,
            component_contracts=tuple(
                (
                    mapping_set.contract_reference()
                    if item.component_kind == "compatibility_mapping_set"
                    else item
                )
                for item in base_descriptor.component_contracts
            ),
        )
        contact_lookup = next(
            item
            for item in descriptor.capability_references
            if item.capability_key == "contact_lookup"
        )
        result = DomainPack(descriptor, mapping_set).plan(
            DomainPlanningIntent(
                domain_pack_reference=descriptor.reference(),
                task_type_keys=("contact_lookup",),
                capability_references=(contact_lookup,),
                runtime_contract=descriptor.runtime_contracts[0],
                legacy_projection=LegacyProjection(
                    source_schema_version="run_profile_v1",
                    projection_kind="runtime",
                    legacy_value="contacts_fixture",
                ),
            ),
            AdmittedSource(
                source_id="contacts_fixture_source_v1",
                source_schema_version="contacts_source_v1",
                source_content_hash=canonical_domain_pack_hash({"fixture": "contacts"}),
                admission_policy_id="fixture_source_policy_v1",
                admission_policy_hash=canonical_domain_pack_hash({"policy": "fixture"}),
            ),
        )

        self.assertIsInstance(result, PlanFailure)
        self.assertEqual(result.reason_code, "ambiguous_compatibility_mapping")


if __name__ == "__main__":
    unittest.main()
