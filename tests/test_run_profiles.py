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
                    "target_candidate_count",
                    "config_hash",
                    "enabled_features",
                },
            )
            self.assertEqual(metadata["generation_mode"], "deterministic_scale_probe")
            self.assertEqual(metadata["target_candidate_count"], 25)
            self.assertEqual(metadata["enabled_features"], [])
            self.assertRegex(str(metadata["config_hash"]), r"^sha256:[0-9a-f]{64}$")

    def test_rejects_invalid_schema_version(self) -> None:
        from synthesis.run_profiles import RunProfileValidationError, load_run_profile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_profile(Path(tmp), overrides={"schema_version": "run_profile_v2"})

            with self.assertRaisesRegex(RunProfileValidationError, "schema_version"):
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
