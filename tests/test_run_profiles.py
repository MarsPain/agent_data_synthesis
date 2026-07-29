from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RunProfileTest(unittest.TestCase):
    def _load_mapping(self, mapping: dict[str, object]):
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(mapping), encoding="utf-8")
            return load_run_profile(path)

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

    def test_versioned_profile_can_select_a_versioned_coverage_profile(self) -> None:
        from synthesis.run_profiles import load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={
                    "generation": {
                        "mode": "deterministic_scale_probe",
                        "target_candidate_count": 6,
                    },
                    "coverage_profile": {
                        "profile_id": "contacts_smoke",
                        "version": "contacts_smoke_v1",
                        "target_accepted_sample_count": 6,
                        "overrides": {
                            "balance_weights": {
                                "contacts.lookup_by_name": 2,
                            }
                        },
                    },
                },
            )

            profile = load_run_profile(path)

            self.assertIsNotNone(profile.coverage_profile)
            assert profile.coverage_profile is not None
            self.assertEqual(profile.coverage_profile.profile_id, "contacts_smoke")
            self.assertEqual(profile.coverage_profile.version, "contacts_smoke_v1")
            self.assertEqual(
                profile.coverage_profile.target_accepted_sample_count,
                6,
            )
            self.assertEqual(
                profile.coverage_profile.balance_weight_overrides,
                {"contacts.lookup_by_name": 2},
            )
            self.assertEqual(
                profile.sanitized_metadata()["coverage_profile"],
                {
                    "profile_id": "contacts_smoke",
                    "version": "contacts_smoke_v1",
                    "target_accepted_sample_count": 6,
                    "overrides": {
                        "balance_weights": {
                            "contacts.lookup_by_name": 2,
                        }
                    },
                },
            )
            self.assertEqual(
                profile.canonical()["coverage_profile"],
                profile.sanitized_metadata()["coverage_profile"],
            )

    def test_coverage_profile_requires_an_explicit_accepted_sample_target(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(
                Path(tmp),
                overrides={
                    "coverage_profile": {
                        "profile_id": "contacts_smoke",
                        "version": "contacts_smoke_v1",
                    },
                },
            )

            with self.assertRaisesRegex(
                RunProfileValidationError,
                "coverage_profile.target_accepted_sample_count",
            ):
                load_run_profile(path)

    def test_rejects_invalid_schema_version(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(Path(tmp), overrides={"schema_version": "run_profile_v5"})

            with self.assertRaisesRegex(RunProfileValidationError, "schema_version"):
                load_run_profile(path)

    def test_checked_in_v1_v2_profile_hashes_remain_stable(self) -> None:
        from synthesis.run_profiles import load_run_profile

        expected = {
            "foundation-fixture.json": "sha256:58469be5b1e3a1818a490fe075d432e5f6771a69cddab1fa3af08c59e5c7e530",
            "foundation-release-candidate.json": "sha256:7ae3c60d24adb0cf0753a5e45596f74f8dfb5a3e4269a132e633f6c18f1813cd",
            "foundation-scale-probe-25.json": "sha256:12c21033834f204c57a469d70cc32b73323a9cd31c0b37bd2ffc347ca1a3d827",
            "mobile-agent-fixture.json": "sha256:2d052aa7594b11243220c5a6d59b90d2b4267e833e5487d5bc4fc658e6e4651b",
            "mobile-messages-release-candidate.json": "sha256:4f2b7db1294e3de73a929361ef292648d2e488978d9bf35240ff5b28a65e0629",
            "profile-local-contacts.json": "sha256:44aa516aaa8d3a1c1c4c72fbd56b021b3dab13556915c98cf7762c8b7cfb38ac",
            "profile-local-mobile-messages.json": "sha256:c77961280280a0966b272e24e99de4727341808b7164fa179b73ff173bd90851",
            "profile-local-workspace-tasks.json": "sha256:9b77b3426fc56e2acde4c6cd2470903e5e2a6d6715e786f563e03f9eb246752c",
            "workspace-tasks-fixture.json": "sha256:47b41a9b32f5c9e9be74d7d9e56ab4b5c2573ab8a6ef028b05283ec5a4c9c9fc",
            "workspace-tasks-release-candidate.json": "sha256:d484f1c6068a7290a0cdb64b244ba3799b6bc512f16eaec6d257b68e93eeb2b8",
        }
        root = Path("tests/fixtures/run_profiles")
        for name, config_hash in expected.items():
            with self.subTest(profile=name):
                self.assertEqual(load_run_profile(root / name).config_hash, config_hash)

        with tempfile.TemporaryDirectory() as tmp:
            base = json.loads((root / "foundation-fixture.json").read_text(encoding="utf-8"))
            base["generation"]["context_policy"] = "synthetic_fixture"
            path = Path(tmp) / "legacy-extra-context.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            self.assertEqual(
                load_run_profile(path).config_hash,
                expected["foundation-fixture.json"],
            )

    def test_v4_selects_disabled_shadow_or_enforce_mutation_admission(self) -> None:
        base = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_comment_shadow_test",
            "dataset_version": "dataset_workspace_comment_shadow_test",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_comment_shadow_test",
                "domain": "workspace_tasks_fixture",
                "description": "Exercise workspace comment admission.",
                "task_taxonomy": ["workspace_comment_update"],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }

        disabled = self._load_mapping(
            {**base, "mutation_admission": {"mode": "disabled"}}
        )
        shadow = self._load_mapping(
            {**base, "mutation_admission": {"mode": "shadow"}}
        )
        enforce = self._load_mapping(
            {
                **base,
                "mutation_admission": {
                    "mode": "enforce",
                    "judge": {
                        "role": "mutation_admission_judge",
                        "provider": "openai_compatible",
                        "model": "independent-judge-model",
                        "timeout_seconds": 12.5,
                        "max_retries": 1,
                    },
                },
            }
        )

        self.assertEqual(disabled.mutation_admission.mode, "disabled")
        self.assertEqual(shadow.mutation_admission.mode, "shadow")
        self.assertEqual(enforce.mutation_admission.mode, "enforce")
        self.assertEqual(
            shadow.sanitized_metadata()["mutation_admission"],
            {"mode": "shadow"},
        )
        self.assertNotEqual(disabled.config_hash, shadow.config_hash)
        self.assertNotEqual(shadow.config_hash, enforce.config_hash)

    def test_v4_configures_remote_mutation_judge_without_credentials(self) -> None:
        profile = self._load_mapping(
            {
                "schema_version": "run_profile_v4",
                "profile_id": "workspace_comment_independent_judge",
                "dataset_version": "dataset_workspace_comment_independent_judge",
                "profile_purpose": "diagnostic_probe",
                "seed": {
                    "seed_id": "seed_workspace_comment_independent_judge",
                    "domain": "workspace_tasks_fixture",
                    "description": "Exercise an independently configured judge.",
                    "task_taxonomy": ["workspace_comment_update"],
                },
                "generation": {"mode": "workspace_fixture"},
                "features": {},
                "mutation_admission": {
                    "mode": "shadow",
                    "judge": {
                        "role": "mutation_admission_judge",
                        "provider": "openai_compatible",
                        "model": "independent-judge-model",
                        "timeout_seconds": 12.5,
                        "max_retries": 1,
                    },
                },
            }
        )

        assert profile.mutation_admission.judge is not None
        self.assertEqual(profile.mutation_admission.judge.model, "independent-judge-model")
        self.assertEqual(profile.mutation_admission.judge.timeout_seconds, 12.5)
        self.assertEqual(profile.mutation_admission.judge.max_retries, 1)
        self.assertEqual(
            profile.sanitized_metadata()["mutation_admission"],
            {
                "mode": "shadow",
                "judge": {
                    "role": "mutation_admission_judge",
                    "provider": "openai_compatible",
                    "model": "independent-judge-model",
                    "timeout_seconds": 12.5,
                    "max_retries": 1,
                },
            },
        )
        self.assertNotIn("api_key", repr(profile))
        self.assertNotIn("credential", repr(profile))

    def test_v4_release_candidates_require_independent_enforcement_configuration(
        self,
    ) -> None:
        base = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_release_enforcement",
            "dataset_version": "dataset_workspace_release_enforcement",
            "profile_purpose": "release_candidate",
            "seed": {
                "seed_id": "seed_workspace_release_enforcement",
                "domain": "workspace_tasks_fixture",
                "description": "Validate release enforcement configuration.",
                "task_taxonomy": ["workspace_item_lookup"],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }
        judge = {
            "role": "mutation_admission_judge",
            "provider": "openai_compatible",
            "model": "independent-judge-model",
            "timeout_seconds": 12.5,
            "max_retries": 1,
        }

        for mutation_admission in (
            {"mode": "disabled"},
            {"mode": "shadow", "judge": judge},
            {"mode": "enforce"},
            {"mode": "enforce", "judge": {**judge, "model": "scripted"}},
        ):
            with self.subTest(mutation_admission=mutation_admission):
                with self.assertRaises(Exception):
                    self._load_mapping(
                        {
                            **base,
                            "mutation_admission": mutation_admission,
                        }
                    )

        profile = self._load_mapping(
            {
                **base,
                "mutation_admission": {"mode": "enforce", "judge": judge},
            }
        )
        self.assertEqual(profile.mutation_admission.mode, "enforce")
        self.assertEqual(
            profile.mutation_admission.judge.model,
            "independent-judge-model",
        )

    def test_v4_llm_enforcement_requires_an_explicit_different_generator_model(
        self,
    ) -> None:
        base = {
            "schema_version": "run_profile_v4",
            "profile_id": "llm_enforcement_independence",
            "dataset_version": "dataset_llm_enforcement_independence",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_llm_enforcement_independence",
                "domain": "workspace_tasks_fixture",
                "description": "Validate remote generator and judge independence.",
                "task_taxonomy": ["workspace_comment_update"],
            },
            "generation": {"mode": "llm"},
            "features": {},
            "mutation_admission": {
                "mode": "enforce",
                "judge": {
                    "role": "mutation_admission_judge",
                    "provider": "openai_compatible",
                    "model": "judge-model",
                    "timeout_seconds": 12.5,
                    "max_retries": 1,
                },
            },
        }

        for generator_model in ("", "judge-model"):
            with self.subTest(generator_model=generator_model), patch.dict(
                os.environ,
                {"AGENT_DATA_LLM_MODEL": generator_model},
                clear=False,
            ):
                with self.assertRaises(Exception):
                    self._load_mapping(base)

        with patch.dict(
            os.environ,
            {"AGENT_DATA_LLM_MODEL": "independent-generator-model"},
            clear=False,
        ):
            profile = self._load_mapping(base)

        self.assertEqual(profile.mutation_admission.mode, "enforce")

    def test_v4_rejects_unsafe_or_unbounded_mutation_judge_configuration(self) -> None:
        base = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_comment_judge_validation",
            "dataset_version": "dataset_workspace_comment_judge_validation",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_comment_judge_validation",
                "domain": "workspace_tasks_fixture",
                "description": "Validate independent judge configuration.",
                "task_taxonomy": ["workspace_comment_update"],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }
        valid_judge = {
            "role": "mutation_admission_judge",
            "provider": "openai_compatible",
            "model": "independent-judge-model",
            "timeout_seconds": 12.5,
            "max_retries": 1,
        }
        invalid_judges = (
            {**valid_judge, "api_key": "must-not-be-retained"},
            {**valid_judge, "role": "judge_verification"},
            {**valid_judge, "provider": "unbounded_provider"},
            {**valid_judge, "model": ""},
            {**valid_judge, "timeout_seconds": 0},
            {**valid_judge, "max_retries": 2},
        )

        for judge in invalid_judges:
            with self.subTest(judge=judge), self.assertRaises(Exception):
                self._load_mapping(
                    {
                        **base,
                        "mutation_admission": {"mode": "shadow", "judge": judge},
                    }
                )

    def test_older_profiles_normalize_to_disabled_without_changing_hashes(self) -> None:
        profile = self._load_mapping(
            {
                "schema_version": "run_profile_v1",
                "profile_id": "legacy_disabled_test",
                "dataset_version": "dataset_legacy_disabled_test",
                "seed": {
                    "seed_id": "seed_legacy_disabled_test",
                    "domain": "contacts",
                    "description": "Legacy profile behavior.",
                    "task_taxonomy": ["contact_lookup"],
                },
                "generation": {"mode": "foundation_fixture"},
                "features": {},
            }
        )

        self.assertEqual(profile.mutation_admission.mode, "disabled")
        self.assertNotIn("mutation_admission", profile.canonical())
        self.assertNotIn("mutation_admission", profile.sanitized_metadata())

    def test_mutation_admission_is_versioned_and_rejects_unknown_configuration(self) -> None:
        base = {
            "schema_version": "run_profile_v4",
            "profile_id": "workspace_comment_admission_validation",
            "dataset_version": "dataset_workspace_comment_admission_validation",
            "profile_purpose": "diagnostic_probe",
            "seed": {
                "seed_id": "seed_workspace_comment_admission_validation",
                "domain": "workspace_tasks_fixture",
                "description": "Validate admission configuration.",
                "task_taxonomy": ["workspace_comment_update"],
            },
            "generation": {"mode": "workspace_fixture"},
            "features": {},
        }

        for mutation_admission in (
            None,
            {"mode": "enforce"},
            {"mode": "shadow", "extra": True},
        ):
            with self.subTest(mutation_admission=mutation_admission), self.assertRaises(Exception):
                mapping = dict(base)
                if mutation_admission is not None:
                    mapping["mutation_admission"] = mutation_admission
                self._load_mapping(mapping)

        legacy = dict(base)
        legacy["schema_version"] = "run_profile_v1"
        legacy["mutation_admission"] = {"mode": "shadow"}
        with self.assertRaises(Exception):
            self._load_mapping(legacy)

    def test_v3_llm_requires_target_and_synthetic_context_policy(self) -> None:
        base = {
            "schema_version": "run_profile_v3",
            "profile_id": "mobile_representative_test",
            "dataset_version": "dataset_mobile_representative_test",
            "profile_purpose": "benchmark",
            "seed": {
                "seed_id": "seed_mobile_representative_test",
                "domain": "mobile_messages_fixture",
                "description": "Generate grounded executable mobile tasks.",
                "task_taxonomy": ["mobile_message_search", "mobile_reminder_creation"],
            },
            "generation": {
                "mode": "llm",
                "target_candidate_count": 2,
                "context_policy": "synthetic_fixture",
            },
            "features": {},
        }

        profile = self._load_mapping(base)
        self.assertEqual(profile.generation.target_candidate_count, 2)
        self.assertEqual(profile.generation.context_policy, "synthetic_fixture")

        invalid_generations = (
            {"mode": "llm", "context_policy": "synthetic_fixture"},
            {"mode": "llm", "target_candidate_count": 0, "context_policy": "synthetic_fixture"},
            {"mode": "llm", "target_candidate_count": 2},
            {"mode": "llm", "target_candidate_count": 2, "context_policy": "governed_source_opt_in"},
            {"mode": "llm", "target_candidate_count": 2, "context_policy": "synthetic_fixture", "extra": True},
            {"mode": "mobile_fixture", "context_policy": "synthetic_fixture"},
        )
        for generation in invalid_generations:
            with self.subTest(generation=generation), self.assertRaises(Exception):
                self._load_mapping({**base, "generation": generation})

        with self.assertRaises(Exception):
            self._load_mapping({**base, "profile_purpose": "release_candidate"})
        with self.assertRaises(Exception):
            self._load_mapping({
                **base,
                "source": {
                    "kind": "local_mobile_messages_json",
                    "source_id": "source_mobile",
                    "path": "messages.json",
                    "license_label": "cc-by-4.0",
                },
            })

    def test_v4_llm_benchmark_combines_representative_generation_and_enforcement(
        self,
    ) -> None:
        mapping = {
            "schema_version": "run_profile_v4",
            "profile_id": "mobile_representative_enforce",
            "dataset_version": "dataset_mobile_representative_enforce",
            "profile_purpose": "benchmark",
            "seed": {
                "seed_id": "seed_mobile_representative_enforce",
                "domain": "mobile_messages_fixture",
                "description": "Generate mutation-admitted representative tasks.",
                "task_taxonomy": [
                    "mobile_message_search",
                    "mobile_reminder_creation",
                ],
            },
            "generation": {
                "mode": "llm",
                "target_candidate_count": 100,
                "context_policy": "synthetic_fixture",
            },
            "features": {},
            "mutation_admission": {
                "mode": "enforce",
                "judge": {
                    "role": "mutation_admission_judge",
                    "provider": "openai_compatible",
                    "model": "independent-judge-model",
                    "timeout_seconds": 30.0,
                    "max_retries": 1,
                },
            },
        }
        with patch.dict(
            os.environ,
            {"AGENT_DATA_LLM_MODEL": "generator-model"},
            clear=False,
        ):
            profile = self._load_mapping(mapping)

        self.assertEqual(profile.generation.target_candidate_count, 100)
        self.assertEqual(profile.generation.context_policy, "synthetic_fixture")
        self.assertEqual(profile.mutation_admission.mode, "enforce")

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

    def test_checked_in_representative_profiles_use_v4_enforcement_contract(
        self,
    ) -> None:
        from synthesis.run_profiles import load_run_profile

        with patch.dict(
            os.environ,
            {"AGENT_DATA_LLM_MODEL": "representative-generator-model"},
            clear=False,
        ):
            for name in (
                "contacts-representative-llm-100.json",
                "mobile-messages-representative-llm-100.json",
                "workspace-tasks-representative-llm-100.json",
            ):
                with self.subTest(profile=name):
                    profile = load_run_profile(
                        Path("tests/fixtures/run_profiles") / name
                    )
                    self.assertEqual(profile.schema_version, "run_profile_v4")
                    self.assertEqual(profile.profile_purpose, "benchmark")
                    self.assertEqual(
                        profile.generation.target_candidate_count,
                        100,
                    )
                    self.assertEqual(
                        profile.generation.context_policy,
                        "synthetic_fixture",
                    )
                    self.assertEqual(profile.mutation_admission.mode, "enforce")
                    self.assertIsNone(profile.source)

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
