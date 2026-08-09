from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path


class ContactsMobileCompatibilityTest(unittest.TestCase):
    def test_supported_profiles_compile_with_exact_plan_and_lineage(self) -> None:
        from synthesis.compatibility import (
            CompatibilityCompilation,
            canonical_projection_has_no_legacy_semantic_aliases,
            compatibility_mapping_set,
            compile_legacy_profile,
        )
        from synthesis.domain_pack import DomainPlan, default_domain_pack_registry

        cases = (
            (
                "tests/fixtures/run_profiles/foundation-fixture.json",
                "contacts",
                "contacts_fixture",
                "contacts",
                "contact_lookup",
            ),
            (
                "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
                "mobile_messages",
                "mobile_messages_fixture",
                "mobile_messages_fixture",
                "mobile_message_search",
            ),
        )
        for raw_path, domain_pack_id, runtime_id, legacy_domain, task_type in cases:
            with self.subTest(path=raw_path):
                result = compile_legacy_profile(Path(raw_path))
                self.assertIsInstance(result, CompatibilityCompilation)
                assert isinstance(result, CompatibilityCompilation)
                self.assertEqual(result.plan.domain_pack_reference.domain_pack_id, domain_pack_id)
                self.assertEqual(result.plan.runtime_contract.runtime_id, runtime_id)
                descriptor = default_domain_pack_registry().descriptor_for(domain_pack_id)
                mapping_set = compatibility_mapping_set(domain_pack_id)
                result.plan.validate_against_descriptor(
                    descriptor,
                    compatibility_mapping_set=mapping_set,
                )
                round_trip = DomainPlan.from_record(
                    result.plan.to_record(),
                    descriptor=descriptor,
                    compatibility_mapping_set=mapping_set,
                )
                self.assertEqual(round_trip.to_record(), result.plan.to_record())
                self.assertEqual(
                    result.plan.compatibility_mapping.legacy_value,
                    legacy_domain,
                )
                self.assertEqual(
                    result.plan.compatibility_mapping.target,
                    result.plan.domain_pack_reference,
                )
                self.assertEqual(result.migration_lineage.source_profile_hash, result.legacy_profile.profile_hash)
                self.assertIn(
                    task_type,
                    {
                        item.task_type_key
                        for item in result.plan.task_capability_projections
                    },
                )
                self.assertTrue(
                    canonical_projection_has_no_legacy_semantic_aliases(
                        result.canonical_projection
                    )
                )
                self.assertEqual(
                    result.canonical_projection["runtime"]["runtime_id"],
                    runtime_id,
                )

    def test_negative_profiles_fail_with_frozen_reasons(self) -> None:
        from synthesis.compatibility import CompatibilityFailure, compile_legacy_profile

        cases = {
            "profile-local-contacts-bad-license.json": "invalid_source_license",
            "profile-local-contacts-bad-schema.json": "source_schema_invalid",
            "profile-local-contacts-missing-file.json": "source_missing",
            "foundation-release-candidate.json": "unsupported_network_work",
        }
        for filename, expected_reason in cases.items():
            with self.subTest(filename=filename):
                result = compile_legacy_profile(
                    Path("tests/fixtures/run_profiles") / filename
                )
                self.assertIsInstance(result, CompatibilityFailure)
                assert isinstance(result, CompatibilityFailure)
                self.assertEqual(result.reason_code, expected_reason)
                self.assertEqual(result.status, "rejected")
                self.assertEqual(
                    result.assessment.runnability.reason_code,
                    expected_reason,
                )

    def test_unknown_semantic_label_is_not_ignored_and_input_is_unchanged(self) -> None:
        from synthesis.compatibility import (
            CompatibilityFailure,
            compile_legacy_profile_record,
            inject_unknown_semantic_label,
        )

        source_path = Path("tests/fixtures/run_profiles/foundation-fixture.json")
        original = source_path.read_bytes()
        record = json.loads(original.decode("utf-8"))
        result = compile_legacy_profile_record(
            inject_unknown_semantic_label(record),
            source_path=source_path,
        )

        self.assertIsInstance(result, CompatibilityFailure)
        assert isinstance(result, CompatibilityFailure)
        self.assertEqual(result.reason_code, "unknown_task_label")
        self.assertEqual(source_path.read_bytes(), original)

    def test_source_profile_migration_reads_without_rewriting_original_bytes(self) -> None:
        from synthesis.compatibility import CompatibilityCompilation, compile_legacy_profile

        source_path = Path("tests/fixtures/run_profiles/profile-local-contacts.json")
        original = source_path.read_bytes()
        result = compile_legacy_profile(source_path)

        self.assertIsInstance(result, CompatibilityCompilation)
        self.assertEqual(source_path.read_bytes(), original)
        assert isinstance(result, CompatibilityCompilation)
        self.assertEqual(
            result.plan.admitted_source.source_content_hash,
            "sha256:" + __import__("hashlib").sha256(
                (source_path.parent / "contacts-profile.json").read_bytes()
            ).hexdigest(),
        )

    def test_source_limits_and_record_paths_fail_closed(self) -> None:
        from synthesis.compatibility import CompatibilityFailure, compile_legacy_profile_record

        source_path = Path("tests/fixtures/run_profiles/profile-local-contacts.json")
        record = json.loads(source_path.read_text(encoding="utf-8"))

        limited = json.loads(json.dumps(record))
        limited["source"]["max_bytes"] = 1
        limited_result = compile_legacy_profile_record(
            limited,
            source_path=source_path,
        )
        self.assertIsInstance(limited_result, CompatibilityFailure)
        assert isinstance(limited_result, CompatibilityFailure)
        self.assertEqual(limited_result.reason_code, "source_exceeds_max_bytes")

        unsafe = json.loads(json.dumps(record))
        unsafe["source"]["path"] = "../escaped.json"
        unsafe_result = compile_legacy_profile_record(
            unsafe,
            source_path=source_path,
        )
        self.assertIsInstance(unsafe_result, CompatibilityFailure)
        assert isinstance(unsafe_result, CompatibilityFailure)
        self.assertEqual(unsafe_result.reason_code, "unsafe_source_path")

    def test_failure_details_are_bounded_and_source_symlinks_fail_closed(self) -> None:
        from synthesis.compatibility import (
            CompatibilityFailure,
            compile_legacy_profile,
            compile_legacy_profile_record,
            inject_unknown_semantic_label,
        )

        source_path = Path("tests/fixtures/run_profiles/foundation-fixture.json")
        record = json.loads(source_path.read_text(encoding="utf-8"))
        unknown = compile_legacy_profile_record(
            inject_unknown_semantic_label(record, label="secret-user-input"),
            source_path=source_path,
        )
        self.assertIsInstance(unknown, CompatibilityFailure)
        assert isinstance(unknown, CompatibilityFailure)
        self.assertNotIn("detail", unknown.to_record())

        profile_source = Path("tests/fixtures/run_profiles/profile-local-contacts.json")
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            root = Path(tmpdir)
            profile = root / profile_source.name
            shutil.copy2(profile_source, profile)
            outside_source = Path(outside) / "contacts-profile.json"
            outside_source.write_bytes(
                (profile_source.parent / "contacts-profile.json").read_bytes()
            )
            (root / "contacts-profile.json").symlink_to(outside_source)
            result = compile_legacy_profile(profile, corpus_root=root)
            self.assertIsInstance(result, CompatibilityFailure)
            assert isinstance(result, CompatibilityFailure)
            self.assertEqual(result.reason_code, "unsafe_source_path")

    def test_scoped_mapping_set_does_not_alias_runtime_and_semantic_fields(self) -> None:
        from synthesis.compatibility import compatibility_mapping_set
        from synthesis.domain_pack import CompatibilityResolutionFailure

        mapping_set = compatibility_mapping_set("contacts")
        semantic = mapping_set.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="semantic_domain",
            legacy_value="contacts_fixture",
        )
        runtime = mapping_set.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="runtime",
            legacy_value="contacts_fixture",
        )
        unknown = mapping_set.resolve(
            source_schema_version="run_profile_v1",
            projection_kind="capability",
            legacy_value="contacts_fixture",
        )

        self.assertNotIsInstance(semantic, CompatibilityResolutionFailure)
        self.assertNotIsInstance(runtime, CompatibilityResolutionFailure)
        self.assertIsInstance(unknown, CompatibilityResolutionFailure)
        assert semantic is not None and runtime is not None
        self.assertEqual(semantic.target.domain_pack_id, "contacts")
        self.assertEqual(runtime.target.runtime_id, "contacts_fixture")

    def test_mapping_set_covers_held_out_legacy_labels(self) -> None:
        from synthesis.compatibility import compatibility_mapping_set
        from synthesis.domain_pack import CompatibilityResolutionFailure

        cases = {
            "contacts": {
                "contact_lookup": "contact_lookup",
                "state_change": "followup_recording",
                "branching": "contact_lookup_recovery",
                "missing_contact": "missing_contact_safe_failure",
            },
            "mobile_messages": {
                "mobile_message_lookup": "message_search",
                "mobile_message_to_reminder": "reminder_creation",
                "mobile_draft_reply": "draft_reply",
                "mobile_branching": "message_search_recovery",
                "mobile_missing_message": "missing_message_safe_failure",
            },
        }
        for domain_pack_id, labels in cases.items():
            mapping_set = compatibility_mapping_set(domain_pack_id)
            for legacy_value, capability_key in labels.items():
                with self.subTest(domain_pack_id=domain_pack_id, legacy_value=legacy_value):
                    resolved = mapping_set.resolve(
                        source_schema_version="run_profile_v4",
                        projection_kind="held_out_capability",
                        legacy_value=legacy_value,
                    )
                    self.assertNotIsInstance(resolved, CompatibilityResolutionFailure)
                    assert resolved is not None
                    self.assertEqual(resolved.target.capability_key, capability_key)

    def test_ambiguous_and_cross_pack_mappings_fail_closed(self) -> None:
        from synthesis.compatibility import CompatibilityFailure, compatibility_mapping_set, compile_legacy_profile
        from synthesis.domain_pack import (
            CompatibilityMapping,
            CompatibilityMappingSet,
            default_domain_pack_registry,
        )

        contacts = default_domain_pack_registry().descriptor_for("contacts")
        semantic = compatibility_mapping_set("contacts").resolve(
            source_schema_version="run_profile_v1",
            projection_kind="semantic_domain",
            legacy_value="contacts",
        )
        assert isinstance(semantic, CompatibilityMapping)
        ambiguous = CompatibilityMappingSet(
            mapping_set_id="contacts_ambiguous_compatibility_set",
            mapping_set_version="contacts_ambiguous_compatibility_set_v1",
            mappings=(
                semantic,
                CompatibilityMapping.create(
                    source_schema_version="run_profile_v1",
                    projection_kind="semantic_domain",
                    legacy_value="contacts",
                    mapping_version="contacts_semantic_mapping_v999",
                    target=contacts.reference(),
                ),
            ),
        )
        ambiguous_result = compile_legacy_profile(
            Path("tests/fixtures/run_profiles/foundation-fixture.json"),
            mapping_set=ambiguous,
        )
        self.assertIsInstance(ambiguous_result, CompatibilityFailure)
        assert isinstance(ambiguous_result, CompatibilityFailure)
        self.assertEqual(ambiguous_result.reason_code, "ambiguous_compatibility_mapping")

        cross_pack = CompatibilityMappingSet(
            mapping_set_id="contacts_cross_pack_compatibility_set",
            mapping_set_version="contacts_cross_pack_compatibility_set_v1",
            mappings=(
                CompatibilityMapping.create(
                    source_schema_version="run_profile_v1",
                    projection_kind="semantic_domain",
                    legacy_value="contacts",
                    mapping_version="contacts_cross_pack_mapping_v1",
                    target=default_domain_pack_registry()
                    .descriptor_for("mobile_messages")
                    .reference(),
                ),
            ),
        )
        cross_pack_result = compile_legacy_profile(
            Path("tests/fixtures/run_profiles/foundation-fixture.json"),
            mapping_set=cross_pack,
        )
        self.assertIsInstance(cross_pack_result, CompatibilityFailure)
        assert isinstance(cross_pack_result, CompatibilityFailure)
        self.assertEqual(cross_pack_result.reason_code, "cross_pack_mapping_target")

    def test_frozen_corpus_has_26_profiles_two_bridges_four_chains_and_four_axes(self) -> None:
        from synthesis.compatibility import verify_compatibility_corpus

        root = Path("tests/fixtures/compatibility")
        manifest = json.loads((root / "corpus_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["profile_count"], 28)
        self.assertEqual(
            sum(row["role"] == "historical_input" for row in manifest["profiles"]),
            26,
        )
        self.assertEqual(
            sum(row["role"] == "synthetic_compatibility_evidence" for row in manifest["profiles"]),
            2,
        )
        self.assertEqual(manifest["chain_count"], 4)
        for row in manifest["profiles"]:
            self.assertEqual(
                set(row["expected"]),
                {
                    "readability",
                    "runnability",
                    "semantic_equivalence",
                    "evidence_admissibility",
                },
            )
            for axis in row["expected"].values():
                self.assertIn(axis["status"], {"passed", "failed", "insufficient_evidence"})
                self.assertTrue(axis["reason_code"])

        result = verify_compatibility_corpus(root)
        self.assertEqual(result.status, "passed", result.to_record())
        self.assertEqual(set(result.chain_results), {
            "contacts_historical_v1",
            "mobile_historical_v1",
            "contacts_mutation_aware_v2",
            "mobile_mutation_aware_v2",
        })
        self.assertTrue(
            all(
                chain["historical_claim"] == "historical_only"
                and chain["current_evidence_status"] == "insufficient_evidence"
                for chain in result.chain_results.values()
            )
        )

    def test_corpus_rejects_tampered_dependencies_and_unknown_labels(self) -> None:
        from synthesis.compatibility import verify_compatibility_corpus

        root = Path("tests/fixtures/compatibility")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied = Path(tmpdir) / "compatibility"
            shutil.copytree(root, copied)
            dependency = copied / "chains/contacts-v1/samples.jsonl"
            dependency.write_bytes(dependency.read_bytes() + b"tampered\n")
            result = verify_compatibility_corpus(copied)
            self.assertEqual(result.status, "failed")
            self.assertIn("dependency_tampered", result.reason_codes)

        with tempfile.TemporaryDirectory() as tmpdir:
            copied = Path(tmpdir) / "compatibility"
            shutil.copytree(root, copied)
            manifest_path = copied / "corpus_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            row = next(
                item
                for item in manifest["profiles"]
                if item["profile_id"] == "foundation_fixture_profile"
            )
            profile_path = copied / row["file"]["path"]
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["seed"]["task_taxonomy"].append("unknown_semantic_label")
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            content = profile_path.read_bytes()
            for file_record in manifest["files"]:
                if file_record["path"] == row["file"]["path"]:
                    file_record["sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
                    file_record["byte_count"] = len(content)
            row["file"]["sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
            row["file"]["byte_count"] = len(content)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = verify_compatibility_corpus(copied)
            self.assertEqual(result.status, "failed")
            self.assertIn("unknown_semantic_label", result.reason_codes)

        with tempfile.TemporaryDirectory() as tmpdir:
            copied = Path(tmpdir) / "compatibility"
            shutil.copytree(root, copied)
            manifest_path = copied / "corpus_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["profiles"].append(json.loads(json.dumps(manifest["profiles"][0])))
            manifest["profile_count"] += 1
            manifest["historical_profile_count"] += 1
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = verify_compatibility_corpus(copied)
            self.assertEqual(result.status, "failed")
            self.assertIn("manifest_invalid", result.reason_codes)

        with tempfile.TemporaryDirectory() as tmpdir:
            copied = Path(tmpdir) / "compatibility"
            shutil.copytree(root, copied)
            manifest_path = copied / "corpus_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bridge = next(
                item
                for item in manifest["profiles"]
                if item["profile_id"] == "contacts_compatibility_bridge_v3"
            )
            bridge["role"] = "historical_input"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = verify_compatibility_corpus(copied)
            self.assertEqual(result.status, "failed")
            self.assertIn("manifest_invalid", result.reason_codes)

        with tempfile.TemporaryDirectory() as tmpdir:
            copied = Path(tmpdir) / "compatibility"
            shutil.copytree(root, copied)
            manifest_path = copied / "corpus_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            chain = next(
                item
                for item in manifest["chains"]
                if item["chain_id"] == "contacts_historical_v1"
            )
            chain["domain_pack_id"] = "mobile_messages"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = verify_compatibility_corpus(copied)
            self.assertEqual(result.status, "failed")
            self.assertIn("expected_assessment_mismatch", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
