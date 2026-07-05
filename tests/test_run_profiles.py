from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RunProfileTest(unittest.TestCase):
    def _write_profile(
        self,
        tmpdir: Path,
        *,
        overrides: dict[str, object] | None = None,
    ) -> Path:
        profile: dict[str, object] = {
            "schema_version": "run_profile_v1",
            "profile_id": "foundation_scale_probe_25",
            "dataset_version": "dataset_foundation_scale_probe_25",
            "seed": {
                "seed_id": "seed_contacts_v1",
                "domain": "contacts",
                "description": "Synthetic contact lookup and follow-up tasks.",
                "task_taxonomy": ["contact_lookup", "contact_followup"],
            },
            "generation": {
                "mode": "deterministic_scale_probe",
                "target_candidate_count": 25,
            },
            "features": {
                "enable_branching": False,
                "enable_task_expansion": True,
                "enable_refinement": False,
                "enable_mcp_adapter": False,
                "enable_sandbox_fixture": False,
                "enable_source_governance_fixture": False,
            },
        }
        if overrides:
            profile.update(overrides)
        path = tmpdir / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return path

    def test_loads_valid_profile_with_normalized_features_and_sanitized_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(Path(tmp), overrides={"features": {}})

            profile = load_run_profile(path)

            self.assertEqual(profile.schema_version, "run_profile_v1")
            self.assertEqual(profile.profile_id, "foundation_scale_probe_25")
            self.assertEqual(profile.dataset_version, "dataset_foundation_scale_probe_25")
            self.assertEqual(profile.seed.seed_id, "seed_contacts_v1")
            self.assertEqual(profile.seed.domain, "contacts")
            self.assertEqual(profile.seed.task_taxonomy, ("contact_lookup", "contact_followup"))
            self.assertEqual(profile.generation.mode, "deterministic_scale_probe")
            self.assertEqual(profile.generation.target_candidate_count, 25)
            self.assertFalse(profile.features.enable_branching)
            self.assertFalse(profile.features.enable_task_expansion)

            metadata = profile.sanitized_metadata()
            self.assertEqual(
                set(metadata),
                {
                    "schema_version",
                    "profile_id",
                    "generation_mode",
                    "profile_purpose",
                    "target_candidate_count",
                    "config_hash",
                    "enabled_features",
                    "seed",
                },
            )
            self.assertEqual(metadata["generation_mode"], "deterministic_scale_probe")
            self.assertEqual(metadata["profile_purpose"], "diagnostic_probe")
            self.assertEqual(metadata["seed"], {"domain": "contacts"})
            self.assertEqual(metadata["target_candidate_count"], 25)
            self.assertEqual(metadata["enabled_features"], [])
            self.assertRegex(str(metadata["config_hash"]), r"^sha256:[0-9a-f]{64}$")

    def test_load_run_profile_accepts_explicit_profile_purpose(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "run_profile_v1",
                        "profile_id": "release_contacts",
                        "dataset_version": "dataset_release_contacts",
                        "profile_purpose": "release_candidate",
                        "seed": {
                            "seed_id": "seed_contacts",
                            "domain": "contacts",
                            "description": "Contacts release candidate.",
                            "task_taxonomy": ["single_tool_lookup"],
                        },
                        "generation": {"mode": "foundation_fixture"},
                        "features": {},
                    }
                ),
                encoding="utf-8",
            )

            profile = load_run_profile(path)

            self.assertEqual(profile.profile_purpose, "release_candidate")
            self.assertEqual(
                profile.sanitized_metadata()["profile_purpose"],
                "release_candidate",
            )

    def test_deterministic_scale_probe_defaults_to_diagnostic_purpose(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json")
        )

        self.assertEqual(profile.profile_purpose, "diagnostic_probe")
        self.assertEqual(
            profile.sanitized_metadata()["profile_purpose"],
            "diagnostic_probe",
        )

    def test_mobile_fixture_profile_loads_as_diagnostic_probe(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/mobile-agent-fixture.json")
        )

        self.assertEqual(profile.profile_id, "mobile_agent_fixture")
        self.assertEqual(profile.seed.domain, "mobile_messages_fixture")
        self.assertEqual(profile.generation.mode, "mobile_fixture")
        self.assertEqual(profile.profile_purpose, "diagnostic_probe")
        self.assertEqual(
            profile.sanitized_metadata()["generation_mode"],
            "mobile_fixture",
        )

    def test_workspace_fixture_profile_loads_as_diagnostic_probe(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/workspace-tasks-fixture.json")
        )

        self.assertEqual(profile.profile_id, "workspace_tasks_fixture")
        self.assertEqual(profile.seed.domain, "workspace_tasks_fixture")
        self.assertEqual(profile.generation.mode, "workspace_fixture")
        self.assertEqual(profile.profile_purpose, "diagnostic_probe")
        self.assertEqual(
            profile.sanitized_metadata()["generation_mode"],
            "workspace_fixture",
        )

    def test_load_release_candidate_profiles_for_mobile_and_workspace(self) -> None:
        from synthesis.run_profiles import load_run_profile

        mobile = load_run_profile(
            Path("tests/fixtures/run_profiles/mobile-messages-release-candidate.json")
        )
        workspace = load_run_profile(
            Path("tests/fixtures/run_profiles/workspace-tasks-release-candidate.json")
        )

        self.assertEqual(mobile.profile_purpose, "release_candidate")
        self.assertEqual(mobile.generation.mode, "mobile_fixture")
        self.assertEqual(workspace.profile_purpose, "release_candidate")
        self.assertEqual(workspace.generation.mode, "workspace_fixture")

    def test_profile_purpose_participates_in_config_hash(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmpdir:
            base = {
                "schema_version": "run_profile_v1",
                "profile_id": "purpose_hash",
                "dataset_version": "dataset_purpose_hash",
                "seed": {
                    "seed_id": "seed_contacts",
                    "domain": "contacts",
                    "description": "Contacts release candidate.",
                    "task_taxonomy": ["single_tool_lookup"],
                },
                "generation": {"mode": "foundation_fixture"},
                "features": {},
            }
            release_path = Path(tmpdir) / "release.json"
            diagnostic_path = Path(tmpdir) / "diagnostic.json"
            release_path.write_text(
                json.dumps({**base, "profile_purpose": "release_candidate"}),
                encoding="utf-8",
            )
            diagnostic_path.write_text(
                json.dumps({**base, "profile_purpose": "diagnostic_probe"}),
                encoding="utf-8",
            )

            release_profile = load_run_profile(release_path)
            diagnostic_profile = load_run_profile(diagnostic_path)

            self.assertNotEqual(release_profile.config_hash, diagnostic_profile.config_hash)

    def test_rejects_invalid_schema_version(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(Path(tmp), overrides={"schema_version": "run_profile_v3"})

            with self.assertRaisesRegex(RunProfileValidationError, "schema_version"):
                load_run_profile(path)

    def test_existing_fixture_profiles_remain_v1_without_source_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        for fixture in (
            Path("tests/fixtures/run_profiles/foundation-fixture.json"),
            Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json"),
        ):
            with self.subTest(fixture=fixture.name):
                profile = load_run_profile(fixture)

                self.assertEqual(profile.schema_version, "run_profile_v1")
                self.assertIsNone(profile.source)
                self.assertNotIn("source", profile.sanitized_metadata())

    def test_v2_profile_loads_local_contacts_source_with_sanitized_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(Path("tests/fixtures/run_profiles/profile-local-contacts.json"))

        self.assertEqual(profile.schema_version, "run_profile_v2")
        self.assertIsNotNone(profile.source)
        assert profile.source is not None
        self.assertEqual(profile.source.kind, "local_contacts_json")
        self.assertEqual(profile.source.source_id, "source_profile_contacts_v1")
        self.assertEqual(profile.source.relative_path, "contacts-profile.json")
        self.assertEqual(profile.source.resolved_path.name, "contacts-profile.json")
        self.assertEqual(profile.source.max_bytes, 65536)
        self.assertNotIn("contacts-profile.json", json.dumps(profile.sanitized_metadata()))
        self.assertNotIn("source", profile.sanitized_metadata())

        metadata = profile.sanitized_metadata(
            source_summary={
                "kind": "local_contacts_json",
                "source_id": "source_profile_contacts_v1",
                "content_hash": "sha256:" + "1" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "2" * 64,
            }
        )
        self.assertEqual(metadata["source"]["source_id"], "source_profile_contacts_v1")
        self.assertNotIn("path", metadata["source"])

    def test_v2_profile_loads_local_mobile_source_with_sanitized_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/profile-local-mobile-messages.json")
        )

        self.assertEqual(profile.schema_version, "run_profile_v2")
        self.assertIsNotNone(profile.source)
        assert profile.source is not None
        self.assertEqual(profile.seed.domain, "mobile_messages_fixture")
        self.assertEqual(profile.source.kind, "local_mobile_messages_json")
        self.assertEqual(
            profile.source.source_id,
            "source_profile_mobile_messages_v1",
        )
        self.assertEqual(profile.source.relative_path, "mobile-messages-profile.json")
        self.assertEqual(profile.source.resolved_path.name, "mobile-messages-profile.json")
        self.assertNotIn("mobile-messages-profile.json", json.dumps(profile.sanitized_metadata()))
        self.assertNotIn("project update tomorrow", json.dumps(profile.sanitized_metadata()))

        metadata = profile.sanitized_metadata(
            source_summary={
                "kind": "local_mobile_messages_json",
                "source_id": "source_profile_mobile_messages_v1",
                "content_hash": "sha256:" + "1" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "2" * 64,
            }
        )
        self.assertEqual(metadata["source"]["kind"], "local_mobile_messages_json")
        self.assertNotIn("path", metadata["source"])

    def test_v2_profile_loads_local_workspace_source_with_sanitized_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/profile-local-workspace-tasks.json")
        )

        self.assertEqual(profile.schema_version, "run_profile_v2")
        self.assertIsNotNone(profile.source)
        assert profile.source is not None
        self.assertEqual(profile.seed.domain, "workspace_tasks_fixture")
        self.assertEqual(profile.source.kind, "local_workspace_tasks_json")
        self.assertEqual(
            profile.source.source_id,
            "source_profile_workspace_tasks_v1",
        )
        self.assertEqual(profile.source.relative_path, "workspace-tasks-profile.json")
        self.assertEqual(profile.source.resolved_path.name, "workspace-tasks-profile.json")
        self.assertNotIn("workspace-tasks-profile.json", json.dumps(profile.sanitized_metadata()))
        self.assertNotIn("Finalize launch plan", json.dumps(profile.sanitized_metadata()))

        metadata = profile.sanitized_metadata(
            source_summary={
                "kind": "local_workspace_tasks_json",
                "source_id": "source_profile_workspace_tasks_v1",
                "content_hash": "sha256:" + "1" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "2" * 64,
            }
        )
        self.assertEqual(metadata["source"]["kind"], "local_workspace_tasks_json")
        self.assertNotIn("path", metadata["source"])

    def test_v2_source_rejects_domain_source_kind_mismatches(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        mismatches = (
            ("contacts", "local_mobile_messages_json"),
            ("contacts", "local_workspace_tasks_json"),
            ("mobile_messages_fixture", "local_contacts_json"),
            ("mobile_messages_fixture", "local_workspace_tasks_json"),
            ("workspace_tasks_fixture", "local_contacts_json"),
            ("workspace_tasks_fixture", "local_mobile_messages_json"),
        )
        for domain, source_kind in mismatches:
            with self.subTest(domain=domain, source_kind=source_kind):
                with tempfile.TemporaryDirectory() as tmp:
                    path = self._write_profile(
                        Path(tmp),
                        overrides={
                            "schema_version": "run_profile_v2",
                            "seed": {
                                "seed_id": "seed_mismatch",
                                "domain": domain,
                                "description": "Mismatch probe.",
                                "task_taxonomy": ["probe"],
                            },
                            "generation": {"mode": "foundation_fixture"},
                            "source": {
                                "kind": source_kind,
                                "source_id": "source_profile_mismatch",
                                "path": "source.json",
                                "license_label": "cc-by-4.0",
                            },
                        },
                    )

                    with self.assertRaisesRegex(RunProfileValidationError, "source.kind"):
                        load_run_profile(path)

    def test_v2_source_declaration_changes_config_hash(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "contacts-a.json").write_text('{"contacts":[]}', encoding="utf-8")
            (tmpdir / "contacts-b.json").write_text('{"contacts":[]}', encoding="utf-8")
            first = self._write_profile(
                tmpdir,
                overrides={
                    "schema_version": "run_profile_v2",
                    "generation": {"mode": "foundation_fixture"},
                    "source": {
                        "kind": "local_contacts_json",
                        "source_id": "source_profile_contacts_v1",
                        "path": "contacts-a.json",
                        "license_label": "cc-by-4.0",
                    },
                },
            )
            first_profile = load_run_profile(first)
            second = self._write_profile(
                tmpdir,
                overrides={
                    "schema_version": "run_profile_v2",
                    "generation": {"mode": "foundation_fixture"},
                    "source": {
                        "kind": "local_contacts_json",
                        "source_id": "source_profile_contacts_v1",
                        "path": "contacts-b.json",
                        "license_label": "cc-by-4.0",
                    },
                },
            )
            second_profile = load_run_profile(second)

            self.assertNotEqual(first_profile.config_hash, second_profile.config_hash)

    def test_v2_source_rejects_unsafe_or_unknown_declarations(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        invalid_sources = (
            {"path": "/tmp/contacts.json"},
            {"path": "../contacts.json"},
            {"path": "contacts.txt"},
            {"max_bytes": 0},
            {"license_label": "bad-license"},
            {"kind": "csv"},
            {"source_id": ""},
            {"unexpected": True},
        )
        for invalid_source in invalid_sources:
            with self.subTest(invalid_source=invalid_source):
                with tempfile.TemporaryDirectory() as tmp:
                    tmpdir = Path(tmp)
                    source = {
                        "kind": "local_contacts_json",
                        "source_id": "source_profile_contacts_v1",
                        "path": "contacts.json",
                        "license_label": "cc-by-4.0",
                    }
                    source.update(invalid_source)
                    path = self._write_profile(
                        tmpdir,
                        overrides={
                            "schema_version": "run_profile_v2",
                            "generation": {"mode": "foundation_fixture"},
                            "source": source,
                        },
                    )

                    with self.assertRaises(RunProfileValidationError):
                        load_run_profile(path)

    def test_rejects_empty_profile_id_and_dataset_version(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={"profile_id": "", "dataset_version": ""},
            )

            with self.assertRaisesRegex(RunProfileValidationError, "profile_id"):
                load_run_profile(path)

    def test_rejects_invalid_generation_mode(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={"generation": {"mode": "async_orchestration"}},
            )

            with self.assertRaisesRegex(RunProfileValidationError, "generation.mode"):
                load_run_profile(path)

    def test_requires_positive_target_count_for_scale_probe(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={
                    "generation": {
                        "mode": "deterministic_scale_probe",
                        "target_candidate_count": 0,
                    }
                },
            )

            with self.assertRaisesRegex(RunProfileValidationError, "target_candidate_count"):
                load_run_profile(path)

    def test_rejects_unknown_feature_keys(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={"features": {"enable_branching": True, "enable_async": True}},
            )

            with self.assertRaisesRegex(RunProfileValidationError, "enable_async"):
                load_run_profile(path)

    def test_config_hash_is_stable_and_does_not_include_environment_secrets(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(Path(tmp))

            with patch.dict(os.environ, {"AGENT_DATA_API_KEY": "secret-one"}, clear=False):
                first = load_run_profile(path)
            with patch.dict(os.environ, {"AGENT_DATA_API_KEY": "secret-two"}, clear=False):
                second = load_run_profile(path)

            self.assertEqual(first.config_hash, second.config_hash)
            metadata_text = json.dumps(first.sanitized_metadata(), sort_keys=True)
            self.assertNotIn("secret-one", metadata_text)
            self.assertNotIn("AGENT_DATA_API_KEY", metadata_text)


class ScaleProbeCandidateTest(unittest.TestCase):
    def test_generates_requested_count_with_stable_unique_ids_and_contract_valid_tasks(self) -> None:
        from synthesis.contracts import validate_candidate_task
        from synthesis.seeds import foundation_seed
        from synthesis.tasks import generate_scale_probe_candidates

        first = generate_scale_probe_candidates(foundation_seed(), 12)
        second = generate_scale_probe_candidates(foundation_seed(), 12)

        self.assertEqual(len(first), 12)
        self.assertEqual(
            [candidate.export() for candidate in first],
            [candidate.export() for candidate in second],
        )
        ids = [candidate.candidate_id for candidate in first]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(candidate_id.startswith("candidate_scale_probe_") for candidate_id in ids))
        for candidate in first:
            validate_candidate_task(candidate)

    def test_scale_probe_includes_lookup_followup_and_probe_lineage(self) -> None:
        from synthesis.seeds import foundation_seed
        from synthesis.tasks import generate_scale_probe_candidates

        candidates = generate_scale_probe_candidates(foundation_seed(), 10)

        task_types = {candidate.constraints.get("task_type") for candidate in candidates}
        probe_cases = {candidate.constraints.get("probe_case") for candidate in candidates}
        tool_counts = {candidate.difficulty.get("tool_count") for candidate in candidates}
        lineage_hashes = {
            candidate.generation_lineage.get("config_hash")
            for candidate in candidates
            if candidate.generation_lineage
        }

        self.assertIn("contact_lookup", task_types)
        self.assertIn("contact_followup", task_types)
        self.assertIn("logical_support_failure", probe_cases)
        self.assertIn(1, tool_counts)
        self.assertIn(2, tool_counts)
        self.assertEqual(lineage_hashes, {"scale-probe-local-v1"})


if __name__ == "__main__":
    unittest.main()
