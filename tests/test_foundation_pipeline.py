from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Callable
from unittest.mock import patch

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.tasks import CandidateTask, EditedTask, TaskExpansionResult


class FoundationPipelineTest(unittest.TestCase):
    def test_default_fixture_source_provenance_matches_seed_domain(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.seeds import DomainSeed, foundation_seed
        from synthesis.domain_sources import build_domain_fixture_source_bundle

        cases = (
            (
                foundation_seed(),
                "bundle_contacts_fixture",
                "source_fixture_contacts",
                "fixture://contacts",
            ),
            (
                DomainSeed("seed_mobile", "mobile_messages_fixture", "Mobile.", ("search",)),
                "bundle_mobile_messages_fixture",
                "source_fixture_mobile_messages",
                "fixture://mobile_messages",
            ),
            (
                DomainSeed("seed_workspace", "workspace_tasks_fixture", "Workspace.", ("search",)),
                "bundle_workspace_tasks_fixture",
                "source_fixture_workspace_tasks",
                "fixture://workspace_tasks",
            ),
        )
        for seed, bundle_id, source_id, origin_reference in cases:
            with self.subTest(domain=seed.domain):
                bundle = build_domain_fixture_source_bundle(seed.domain)
                self.assertEqual(bundle.bundle_id, bundle_id)
                self.assertEqual(bundle.sources[0].source_id, source_id)
                self.assertEqual(bundle.sources[0].origin_reference, origin_reference)

        observed_domains: list[str] = []

        def capture_bundle(domain_id: str):
            observed_domains.append(domain_id)
            return build_domain_fixture_source_bundle(domain_id)

        def generation_failure(_seed):
            from synthesis.llm import LLMProviderError

            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="DomainGenerationValidationError",
                schema_reason="response_shape_mismatch",
            )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "synthesis.pipeline.build_domain_fixture_source_bundle",
            side_effect=capture_bundle,
        ):
            for seed, bundle_id, source_id, _ in cases:
                result = run_foundation_pipeline(
                    Path(tmpdir) / seed.domain,
                    seed_override=seed,
                    candidate_generator=generation_failure,
                )
                rejection = self._read_jsonl(result.rejections_path)[0]
                provenance = rejection["details"]["source_governance"]
                self.assertEqual(provenance["source_bundle_id"], bundle_id)
                self.assertEqual(provenance["source_ids"], [source_id])

        self.assertEqual(
            observed_domains,
            [seed.domain for seed, _, _, _ in cases],
        )

    def test_default_fixture_source_provenance_reaches_isolated_samples(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.seeds import DomainSeed, foundation_seed

        cases = (
            (foundation_seed(), "bundle_contacts_fixture"),
            (
                DomainSeed(
                    "seed_mobile_provenance",
                    "mobile_messages_fixture",
                    "Mobile provenance.",
                    ("mobile_message_search",),
                ),
                "bundle_mobile_messages_fixture",
            ),
            (
                DomainSeed(
                    "seed_workspace_provenance",
                    "workspace_tasks_fixture",
                    "Workspace provenance.",
                    ("workspace_item_search",),
                ),
                "bundle_workspace_tasks_fixture",
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            for seed, bundle_id in cases:
                with self.subTest(domain=seed.domain):
                    result = run_foundation_pipeline(
                        Path(tmpdir) / seed.domain,
                        dataset_version=f"dataset_{seed.domain}_provenance",
                        seed_override=seed,
                    )
                    samples = self._read_jsonl(result.samples_path)

                    self.assertGreater(len(samples), 0)
                    for sample in samples:
                        self.assertEqual(
                            sample["environment"]["source_provenance"]["source_bundle_id"],
                            bundle_id,
                        )
                        self.assertEqual(
                            sample["lineage"]["source_provenance"]["source_bundle_id"],
                            bundle_id,
                        )

    def _normalized_artifacts(self, result) -> dict[str, object]:
        artifacts: dict[str, object] = {
            "samples": self._read_jsonl(result.samples_path),
            "manifest": self._read_json(result.manifest_path),
            "rejections": self._read_jsonl(result.rejections_path),
            "quality_report": self._read_json(result.quality_report_path),
        }
        optional_paths = {
            "tool_proposals": result.tool_proposals_path,
            "source_events": result.source_events_path,
            "sandbox_audits": result.sandbox_audits_path,
            "parent_comparison": result.parent_comparison_path,
            "review_queue": result.review_queue_path,
        }
        for name, path in optional_paths.items():
            if path is None:
                artifacts[name] = None
            elif path.suffix == ".jsonl":
                artifacts[name] = self._read_jsonl(path)
            else:
                artifacts[name] = self._read_json(path)
        return self._normalize_artifact_value(artifacts)

    def _read_json(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_jsonl(self, path: Path) -> list[object]:
        text = path.read_text(encoding="utf-8")
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines()]

    def _normalize_artifact_value(self, value: object) -> object:
        if isinstance(value, dict):
            normalized: dict[str, object] = {}
            for key, nested_value in value.items():
                if key in {"dataset_version", "parent_dataset_version"}:
                    normalized[key] = "<dataset_version>" if nested_value else nested_value
                elif key == "duration_ms":
                    normalized[key] = "<duration_ms>"
                else:
                    normalized[key] = self._normalize_artifact_value(nested_value)
            return normalized
        if isinstance(value, list):
            return [self._normalize_artifact_value(item) for item in value]
        return value

    def test_refactor_sensitive_fixture_artifacts_are_deterministic(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.sources import (
            FetchedSourceRequest,
            build_external_fixture_source_bundle,
            build_network_contacts_source_input,
        )

        class FixtureHttpResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def __init__(self, content: bytes) -> None:
                self.content = content

        class FixtureHttpClient:
            def __init__(self, content: bytes) -> None:
                self.content = content

            def get(self, url: str, *, timeout: float, follow_redirects: bool) -> FixtureHttpResponse:
                return FixtureHttpResponse(self.content)

        def source_governance_kwargs(tmpdir: Path) -> dict[str, object]:
            return {
                "source_bundle": build_external_fixture_source_bundle(network_enabled=True),
                "enable_source_audit": True,
            }

        def network_source_kwargs(tmpdir: Path) -> dict[str, object]:
            payload = json.dumps(
                {
                    "contacts": [
                        {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
                        {"name": "Ben Carter", "email": "ben.carter@example.test"},
                    ],
                    "followups": [],
                }
            ).encode("utf-8")
            source_input = build_network_contacts_source_input(
                FetchedSourceRequest(
                    url="https://allowed.example.test/contacts.json",
                    allowed_hosts=("allowed.example.test",),
                    request_budget=1,
                    timeout_seconds=5.0,
                    max_bytes=65536,
                    expected_content_type="application/json",
                    license_label="cc-by-4.0",
                    require_source_audit=True,
                ),
                http_client=FixtureHttpClient(payload),
            )
            return {
                "source_bundle": source_input.source_bundle,
                "domain_environment_input": source_input.environment_input,
                "source_events": source_input.events,
                "enable_source_audit": True,
            }

        case_factories: tuple[tuple[str, Callable[[Path], dict[str, object]]], ...] = (
            ("default", lambda tmpdir: {}),
            ("branching", lambda tmpdir: {"enable_branching": True}),
            ("task_expansion", lambda tmpdir: {"enable_task_expansion": True}),
            ("mcp_adapter", lambda tmpdir: {"enable_mcp_adapter": True}),
            ("source_governance", source_governance_kwargs),
            ("sandbox", lambda tmpdir: {"enable_sandbox_fixture": True}),
            ("network_source", network_source_kwargs),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for case_name, build_kwargs in case_factories:
                with self.subTest(case=case_name):
                    first = run_foundation_pipeline(
                        root / case_name / "first",
                        dataset_version=f"dataset_{case_name}_first",
                        **build_kwargs(root),
                    )
                    second = run_foundation_pipeline(
                        root / case_name / "second",
                        dataset_version=f"dataset_{case_name}_second",
                        **build_kwargs(root),
                    )

                    self.assertEqual(
                        self._normalized_artifacts(first),
                        self._normalized_artifacts(second),
                    )

    def test_candidate_merge_preserves_ordered_admission_contract(self) -> None:
        from synthesis.candidate_processing import (
            ProvisionalCandidateOutcome,
            merge_candidate_outcomes,
        )

        result = merge_candidate_outcomes(
            (
                ProvisionalCandidateOutcome(
                    sequence_index=0,
                    candidate_id="candidate_sample",
                    sample={"sample_id": "sample_candidate"},
                    rejection=None,
                    review_records=({"candidate_id": "candidate_review"},),
                    tool_proposal_records=({"candidate_id": "candidate_tool"},),
                    duplicate_signature=("instruction", ("lookup_contact_email",)),
                ),
            )
        )

        self.assertEqual(result.samples, ({"sample_id": "sample_candidate"},))
        self.assertEqual(result.rejections, ())
        self.assertEqual(result.review_records, ({"candidate_id": "candidate_review"},))
        self.assertEqual(result.tool_proposal_records, ({"candidate_id": "candidate_tool"},))
        self.assertEqual(
            result.accepted_signatures,
            frozenset({("instruction", ("lookup_contact_email",))}),
        )

        with self.assertRaisesRegex(ValueError, "exactly one"):
            merge_candidate_outcomes(
                (
                    ProvisionalCandidateOutcome(
                        sequence_index=0,
                        candidate_id="candidate_missing_terminal",
                    ),
                )
            )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            merge_candidate_outcomes(
                (
                    ProvisionalCandidateOutcome(
                        sequence_index=0,
                        candidate_id="candidate_bad",
                        sample={"sample_id": "sample_bad"},
                        rejection={"cause": "bad"},
                    ),
                )
            )

    def test_generates_verified_sample_and_manifest(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(Path(tmpdir), dataset_version="dataset_test")

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.samples_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.rejections_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            sample = samples[0]
            self.assertEqual(sample["dataset_version"], "dataset_test")
            self.assertEqual(sample["environment"]["id"], "contacts_fixture")
            self.assertEqual(sample["tools"][0]["name"], "lookup_contact_email")
            self.assertEqual(sample["task"]["difficulty"]["tool_count"], 1)
            self.assertEqual(sample["trajectory"][-1]["type"], "final_response")
            self.assertIn("verifier", sample)
            self.assertEqual(sample["verifier"]["id"], "exact_answer_verifier")
            self.assertTrue(sample["verification"]["passed"])
            self.assertIn("provider_host", sample["lineage"]["generator"])
            self.assertEqual(sample["lineage"]["generator"]["provider_host"], "local")
            self.assertEqual(sample["lineage"]["generator"]["model"], "scripted")
            self.assertEqual(sample["lineage"]["generator"]["role"], "scripted_task_generation")
            self.assertEqual(sample["lineage"]["generator"]["role_version"], "role_scripted_task_generation_v1")
            self.assertEqual(sample["lineage"]["generator"]["output_type"], "candidate_tasks")
            self.assertNotIn("secret-test-key", json.dumps(sample))

            stateful_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("task_type") == "contact_followup"
            )
            action_tools = [
                event["tool"]
                for event in stateful_sample["trajectory"]
                if event["type"] == "action"
            ]
            self.assertEqual(
                action_tools,
                ["lookup_contact_email", "record_contact_followup"],
            )
            self.assertTrue(
                any(event["type"] == "state_change" for event in stateful_sample["trajectory"])
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role"],
                "scripted_solution_policy",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["role_version"],
                "role_scripted_solution_policy_v1",
            )
            self.assertEqual(
                stateful_sample["lineage"]["solution_policy"]["output_type"],
                "solution_policy",
            )
            self.assertEqual(stateful_sample["quality"]["tags"], ["foundation", "sqlite_fixture", "multi_step", "stateful"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_test")
            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["rejected_count"], 1)
            self.assertEqual(manifest["quality"]["success_rate"], 2 / 3)
            self.assertEqual(manifest["schema_version"], "dataset_manifest_v1")
            self.assertIsNone(manifest["parent_dataset_version"])
            self.assertEqual(manifest["artifacts"]["quality_report"], "quality_report.json")
            self.assertEqual(manifest["environment_versions"], ["env_contacts_v2"])
            self.assertEqual(
                manifest["tool_versions"],
                ["tool_lookup_contact_email_v1", "tool_record_contact_followup_v1"],
            )
            self.assertEqual(manifest["verifier_versions"], ["verifier_exact_answer_state_v2"])
            self.assertEqual(manifest["rejection_causes"], {"verification_failed": 1})
            self.assertNotIn("run_profile", manifest)

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertIn("expected", rejection["details"])
            self.assertTrue(all("run_profile" not in sample["lineage"] for sample in samples))
            self.assertNotIn("run_profile", rejection["details"])

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["schema_version"], "quality_report_v1")
            self.assertEqual(quality_report["counts"]["accepted"], 2)
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertIn("difficulty_level", quality_report["slices"])
            self.assertIn(
                "lookup_contact_email > record_contact_followup",
                quality_report["slices"]["tool_combination"],
            )

    def test_episode_logs_are_opt_in_and_kept_out_of_public_samples(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            default = run_foundation_pipeline(
                root / "default",
                dataset_version="dataset_default_episode_opt_in",
            )
            opt_in = run_foundation_pipeline(
                root / "opt-in",
                dataset_version="dataset_episode_opt_in",
                write_episode_logs=True,
            )

            self.assertIsNone(default.episode_logs_path)
            self.assertFalse((root / "default" / "episodes.jsonl").exists())
            self.assertFalse((root / "default" / "episode_replay_report.json").exists())
            self.assertIsNotNone(opt_in.episode_logs_path)
            assert opt_in.episode_logs_path is not None
            self.assertTrue(opt_in.episode_logs_path.exists())
            episodes = [
                json.loads(line)
                for line in opt_in.episode_logs_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(episodes), opt_in.accepted_count + opt_in.rejected_count)
            self.assertTrue(
                all(episode["runtime"]["runtime_id"] == "contacts_fixture" for episode in episodes)
            )
            samples = [
                json.loads(line)
                for line in opt_in.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(all("episode_log" not in sample for sample in samples))

    def test_pipeline_uses_seed_override_and_writes_sanitized_run_profile_metadata(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(Path("tests/fixtures/run_profiles/foundation-fixture.json"))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"AGENT_DATA_API_KEY": "secret-profile-key"},
                clear=False,
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version=profile.dataset_version,
                    seed_override=profile.seed,
                    run_profile_metadata=profile.sanitized_metadata(),
                )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_profile"]["profile_id"], "foundation_fixture_profile")
            self.assertEqual(manifest["run_profile"]["generation_mode"], "foundation_fixture")
            self.assertEqual(manifest["run_profile"]["profile_purpose"], "release_candidate")
            self.assertEqual(manifest["run_profile"]["target_candidate_count"], None)
            self.assertEqual(manifest["run_profile"]["enabled_features"], [])
            self.assertRegex(manifest["run_profile"]["config_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertNotIn("secret-profile-key", result.manifest_path.read_text(encoding="utf-8"))

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["lineage"]["seed_ids"], ["seed_contacts_v1"])
            self.assertEqual(
                sample["lineage"]["run_profile"],
                {
                    "schema_version": "run_profile_attribution_v1",
                    "profile_schema_version": "run_profile_v1",
                    "profile_id": "foundation_fixture_profile",
                    "generation_mode": "foundation_fixture",
                    "profile_purpose": "release_candidate",
                    "config_hash": manifest["run_profile"]["config_hash"],
                },
            )
            self.assertNotIn("target_candidate_count", sample["lineage"]["run_profile"])
            self.assertNotIn("enabled_features", sample["lineage"]["run_profile"])
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["details"]["run_profile"], sample["lineage"]["run_profile"])

    def test_run_profile_attribution_builder_excludes_manifest_only_fields(self) -> None:
        from synthesis.datasets import _run_profile_attribution

        attribution = _run_profile_attribution(
            {
                "schema_version": "run_profile_v2",
                "profile_id": "foundation_profile_local_contacts",
                "generation_mode": "foundation_fixture",
                "target_candidate_count": 25,
                "config_hash": "sha256:" + "1" * 64,
                "enabled_features": ["enable_branching"],
                "profile_path": "/tmp/profile.json",
                "source": {
                    "kind": "local_contacts_json",
                    "source_id": "source_profile_contacts_v1",
                    "content_hash": "sha256:" + "2" * 64,
                    "license_label": "cc-by-4.0",
                    "source_policy_hash": "sha256:" + "3" * 64,
                    "path": "contacts-profile.json",
                    "raw_payload": {"contacts": []},
                },
            }
        )

        self.assertEqual(
            attribution,
            {
                "schema_version": "run_profile_attribution_v1",
                "profile_schema_version": "run_profile_v2",
                "profile_id": "foundation_profile_local_contacts",
                "generation_mode": "foundation_fixture",
                "config_hash": "sha256:" + "1" * 64,
                "source": {
                    "kind": "local_contacts_json",
                    "source_id": "source_profile_contacts_v1",
                    "content_hash": "sha256:" + "2" * 64,
                    "license_label": "cc-by-4.0",
                    "source_policy_hash": "sha256:" + "3" * 64,
                },
            },
        )

    def test_scale_probe_profile_pipeline_outputs_stable_decision_evidence(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile
        from synthesis.tasks import generate_scale_probe_candidates

        profile = load_run_profile(Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json"))

        with tempfile.TemporaryDirectory() as tmpdir:
            first = run_foundation_pipeline(
                Path(tmpdir) / "first",
                dataset_version=profile.dataset_version,
                candidate_generator=lambda seed: generate_scale_probe_candidates(
                    seed,
                    profile.generation.target_candidate_count or 0,
                ),
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
            )
            second = run_foundation_pipeline(
                Path(tmpdir) / "second",
                dataset_version=profile.dataset_version,
                candidate_generator=lambda seed: generate_scale_probe_candidates(
                    seed,
                    profile.generation.target_candidate_count or 0,
                ),
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
            )

            self.assertEqual(first.accepted_count, 14)
            self.assertEqual(first.rejected_count, 11)
            self.assertEqual(
                self._normalized_artifacts(first),
                self._normalized_artifacts(second),
            )
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            report = json.loads(first.quality_report_path.read_text(encoding="utf-8"))
            samples = [
                json.loads(line)
                for line in first.samples_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(report["counts"]["total"], 25)
            self.assertEqual(report["rejection_causes"]["quality_duplicate"], 3)
            self.assertEqual(report["rejection_causes"]["verification_failed"], 4)
            self.assertEqual(report["rejection_causes"]["solution_logic_error"], 4)
            self.assertEqual(manifest["run_profile"]["profile_id"], "foundation_scale_probe_25")
            self.assertEqual(manifest["run_profile"]["target_candidate_count"], 25)
            self.assertRegex(manifest["run_profile"]["config_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(
                [sample["sample_id"] for sample in samples[:3]],
                [
                    "sample_candidate_scale_probe_0001",
                    "sample_candidate_scale_probe_0004",
                    "sample_candidate_scale_probe_0007",
                ],
            )

    def test_profile_local_source_pipeline_writes_sanitized_source_metadata(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.run_profiles import load_run_profile
        from synthesis.sources import (
            ProfileLocalContactsSourceRequest,
            build_profile_local_contacts_source_input,
        )

        profile = load_run_profile(Path("tests/fixtures/run_profiles/profile-local-contacts.json"))
        assert profile.source is not None
        source_input = build_profile_local_contacts_source_input(
            ProfileLocalContactsSourceRequest.from_run_profile_source(profile.source)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version=profile.dataset_version,
                source_bundle=source_input.source_bundle,
                domain_environment_input=source_input.environment_input,
                source_events=source_input.events,
                enable_source_audit=True,
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(
                    source_summary=source_input.source_summary
                ),
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertIsNotNone(result.source_events_path)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_profile"]["schema_version"], "run_profile_v2")
            self.assertEqual(manifest["run_profile"]["source"], source_input.source_summary)
            self.assertEqual(manifest["source_policy_hashes"], [source_input.source_summary["source_policy_hash"]])

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["lineage"]["source_provenance"]["source_kinds"], ["local_file"])
            self.assertEqual(sample["environment"]["reset_recipe"]["contact_count"], 4)
            self.assertEqual(
                sample["lineage"]["run_profile"]["source"],
                {
                    "kind": "local_contacts_json",
                    "source_id": "source_profile_contacts_v1",
                    "content_hash": source_input.source_summary["content_hash"],
                    "license_label": "cc-by-4.0",
                    "source_policy_hash": source_input.source_summary["source_policy_hash"],
                },
            )
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["details"]["run_profile"], sample["lineage"]["run_profile"])

            audit_text = (
                result.manifest_path.read_text(encoding="utf-8")
                + result.source_events_path.read_text(encoding="utf-8")
                + result.quality_report_path.read_text(encoding="utf-8")
                + result.rejections_path.read_text(encoding="utf-8")
            )
            self.assertNotIn("contacts-profile.json", audit_text)
            self.assertNotIn("alice.zhang@example.test", audit_text)
            self.assertNotIn("ben.carter@example.test", audit_text)
            self.assertNotIn("clara.nguyen@example.test", audit_text)
            self.assertNotIn("devon.lee@example.test", audit_text)

    def test_adapter_fixture_path_records_lineage_without_changing_default_counts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            direct = run_foundation_pipeline(
                Path(tmpdir) / "direct",
                dataset_version="dataset_direct",
            )
            adapter = run_foundation_pipeline(
                Path(tmpdir) / "adapter",
                dataset_version="dataset_adapter",
                enable_mcp_adapter=True,
            )

            self.assertEqual(adapter.accepted_count, direct.accepted_count)
            self.assertEqual(adapter.rejected_count, direct.rejected_count)
            direct_samples = [
                json.loads(line)
                for line in direct.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            adapter_samples = [
                json.loads(line)
                for line in adapter.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [sample["final_response"] for sample in adapter_samples],
                [sample["final_response"] for sample in direct_samples],
            )
            self.assertNotIn("adapter", direct_samples[0]["lineage"])
            self.assertEqual(
                adapter_samples[0]["lineage"]["adapter"][0]["adapter_id"],
                "contacts_local_mcp_adapter",
            )
            self.assertEqual(
                adapter_samples[0]["lineage"]["adapter"][0]["execution_status"],
                "succeeded",
            )

            report = json.loads(adapter.quality_report_path.read_text(encoding="utf-8"))
            self.assertIn(
                "contacts_local_mcp_adapter",
                report["slices"]["adapter_id"],
            )
            self.assertIn(
                "mcp-compatible-local-shim",
                report["slices"]["adapter_protocol"],
            )
            self.assertIn("succeeded", report["slices"]["adapter_execution_outcome"])

    def test_sandbox_fixture_records_audit_artifact_without_changing_default_counts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            direct = run_foundation_pipeline(
                Path(tmpdir) / "direct",
                dataset_version="dataset_direct",
            )
            sandboxed = run_foundation_pipeline(
                Path(tmpdir) / "sandboxed",
                dataset_version="dataset_sandboxed",
                enable_sandbox_fixture=True,
            )

            self.assertEqual(sandboxed.accepted_count, direct.accepted_count)
            self.assertEqual(sandboxed.rejected_count, direct.rejected_count)
            self.assertIsNotNone(sandboxed.sandbox_audits_path)
            manifest = json.loads(sandboxed.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["sandbox_audits"], "sandbox_audits.jsonl")
            audits = [
                json.loads(line)
                for line in sandboxed.sandbox_audits_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [audit["admission"]["accepted"] for audit in audits],
                [True, False],
            )
            audit_text = sandboxed.sandbox_audits_path.read_text(encoding="utf-8")
            self.assertNotIn("def ", audit_text)
            self.assertNotIn("sk-live", audit_text)

            report = json.loads(sandboxed.quality_report_path.read_text(encoding="utf-8"))
            self.assertIn("passed", report["slices"]["sandbox_scan_status"])
            self.assertIn("rejected", report["slices"]["sandbox_admission_outcome"])
            self.assertIn("succeeded", report["slices"]["sandbox_execution_status"])

            direct_manifest = json.loads(direct.manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("sandbox_audits", direct_manifest["artifacts"])

    def test_adapter_contract_rejection_is_non_executable(self) -> None:
        from synthesis.execution import SolutionPolicy, ToolStep
        from synthesis.pipeline import run_foundation_pipeline

        def one_candidate(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_bad_adapter_args",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        def bad_policy(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_bad_adapter_args",
                role="scripted_solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": 42},
                    ),
                ),
                final_response_template="{email}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_adapter_rejection",
                candidate_generator=one_candidate,
                policy_generator=bad_policy,
                enable_mcp_adapter=True,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "adapter_contract_rejected")
            self.assertEqual(
                rejection["details"]["adapter_rejection"]["rejection_cause"],
                "tool_schema_error",
            )
            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["executable"], 0)
            self.assertIn("tool_schema_error", report["slices"]["adapter_rejection_cause"])

    def test_execution_rejects_malformed_solution_policy_before_tool_call(self) -> None:
        from synthesis.execution import PolicyValidationError, execute_candidate
        from synthesis.environments import ContactEnvironment
        from synthesis.tools import build_contact_tool_registry

        task = CandidateTask(
            candidate_id="candidate_bad_policy",
            instruction="Find Alice Zhang's email address.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty={"level": "easy", "tool_count": 1},
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
        )
        policy = SolutionPolicy(
            policy_id="policy_bad",
            role="scripted_solution_policy",
            steps=(ToolStep(tool_name="", arguments={"name": "Alice Zhang"}),),
            final_response_template="{email}",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)

            with self.assertRaisesRegex(PolicyValidationError, "steps.0.tool_name"):
                execute_candidate(task, registry, policy=policy)

    def test_branch_execution_preserves_failed_branch_events_without_state_leakage(self) -> None:
        from synthesis.execution import SolutionPolicy, execute_candidate
        from synthesis.environments import ContactEnvironment
        from synthesis.tools import build_contact_tool_registry

        task = CandidateTask(
            candidate_id="candidate_branch_state_reset",
            instruction="Try a mutating branch, then fall back to a read-only lookup.",
            constraints={"task_type": "contact_branch_fallback"},
            difficulty={
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 1,
                "branch_depth": 2,
                "fallback_count": 1,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=("seed_contacts_v1",),
            branch_plan={
                "schema_version": "branch_plan_v1",
                "plan_id": "branch_plan_state_reset",
                "max_depth": 2,
                "branches": [
                    {
                        "branch_id": "mutating_bad_template",
                        "node_type": "attempt",
                        "parent_id": None,
                        "condition": "Record a follow-up but fail response rendering.",
                        "steps": [
                            {
                                "tool_name": "record_contact_followup",
                                "arguments": {
                                    "name": "Alice Zhang",
                                    "note": "temporary note",
                                },
                            }
                        ],
                        "final_response_template": "{missing_field}",
                        "terminal_outcome": "fallback_on_failure",
                    },
                    {
                        "branch_id": "read_only_lookup",
                        "node_type": "fallback",
                        "parent_id": "mutating_bad_template",
                        "condition": "Use the read-only lookup after the branch fails.",
                        "steps": [
                            {
                                "tool_name": "lookup_contact_email",
                                "arguments": {"name": "Alice Zhang"},
                            }
                        ],
                        "final_response_template": "{name}'s email is {email}.",
                        "terminal_outcome": "accept_on_success",
                    },
                ],
            },
        )
        policy = SolutionPolicy(
            policy_id="policy_branch_state_reset",
            role="scripted_solution_policy",
            steps=(),
            final_response_template="branch_plan",
            branch_plan=task.branch_plan,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = build_contact_tool_registry(environment)

            execution = execute_candidate(task, registry, policy=policy)

            failed_branch = execution.branch_outcomes[0]
            self.assertEqual(failed_branch["branch_id"], "mutating_bad_template")
            self.assertTrue(
                any(event["type"] == "state_change" for event in failed_branch["trajectory"])
            )
            self.assertFalse(environment.has_followup("Alice Zhang", "temporary note"))
            self.assertEqual(execution.branch_outcomes[1]["branch_id"], "read_only_lookup")

    def test_task_expansion_adds_edited_candidate_and_inspectable_rejection(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_task_expansion",
                enable_task_expansion=True,
            )

            self.assertEqual(result.accepted_count, 3)
            self.assertEqual(result.rejected_count, 2)

            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            expanded = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("taxonomy_node") == "contact_followup"
                and sample["task"]["constraints"].get("source") == "task_expansion"
            )
            self.assertEqual(
                expanded["lineage"]["seed_transformation"]["target_taxonomy_node"],
                "contact_followup",
            )
            self.assertEqual(expanded["lineage"]["task_suggester"]["role"], "task_suggester")
            self.assertEqual(expanded["lineage"]["task_editor"]["role"], "task_editor")
            self.assertEqual(expanded["lineage"]["task_editor"]["output_type"], "edited_task")
            self.assertEqual(
                [event["tool"] for event in expanded["trajectory"] if event["type"] == "action"],
                ["lookup_contact_email", "record_contact_followup"],
            )

            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(encoding="utf-8").splitlines()
            ]
            suggestion_rejection = next(
                rejection
                for rejection in rejections
                if rejection["cause"] == "task_suggestion_rejected"
            )
            self.assertEqual(
                suggestion_rejection["details"]["task_suggestion"]["outcome"],
                "rejected",
            )
            self.assertEqual(
                suggestion_rejection["details"]["role_lineages"]["task_suggester"]["role"],
                "task_suggester",
            )

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["seed_transformations"], 2)
            self.assertEqual(quality_report["counts"]["task_suggestions"], 2)
            self.assertEqual(quality_report["counts"]["task_edits"], 1)
            self.assertIn("contact_followup", quality_report["slices"]["taxonomy_node"])
            self.assertIn("accepted", quality_report["slices"]["suggestion_outcome"])
            self.assertIn("rejected", quality_report["slices"]["suggestion_outcome"])
            self.assertIn("created_candidate", quality_report["slices"]["editor_action"])

    def test_task_expansion_uses_normal_tool_expansion_rerun_gate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import CapabilityGap, ToolProposal

        def no_initial_candidates(seed) -> list[CandidateTask]:
            return []

        def expansion_generator(seed) -> TaskExpansionResult:
            return TaskExpansionResult(
                candidates=[
                    CandidateTask(
                        candidate_id="candidate_expanded_list_contacts",
                        instruction="List the known contact names.",
                        constraints={"must_use_tool": "list_contact_names"},
                        difficulty={
                            "level": "easy",
                            "tool_count": 1,
                            "constraint_count": 1,
                            "state_changes": 0,
                            "ambiguity": "none",
                            "recovery_paths": 0,
                        },
                        tool_name="list_contact_names",
                        arguments={},
                        expected_answer="Alice Zhang",
                        seed_ids=(seed.seed_id,),
                    )
                ],
                rejected_suggestions=[],
            )

        def proposal_generator(gap: CapabilityGap) -> ToolProposal:
            self.assertEqual(gap.tool_name, "list_contact_names")
            return ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "proposal-hash",
                },
            )

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_list_contacts",
                role="solution_policy",
                steps=(ToolStep(tool_name="list_contact_names", arguments={}),),
                final_response_template="Known contacts: {contacts}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_expansion_tool_gate",
                candidate_generator=no_initial_candidates,
                policy_generator=policy_generator,
                enable_task_expansion=True,
                task_expansion_generator=expansion_generator,
                tool_proposal_generator=proposal_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["trajectory"][0]["tool"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["admission"]["outcome"], "accepted")

    def test_task_expansion_rejections_preserve_valid_nested_contracts(self) -> None:
        from synthesis.contracts import (
            validate_seed_transformation_record,
            validate_task_suggestion_record,
        )
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_task_expansion_contracts",
                enable_task_expansion=True,
            )

            rejections = [
                json.loads(line)
                for line in result.rejections_path.read_text(encoding="utf-8").splitlines()
            ]
            suggestion_rejection = next(
                rejection
                for rejection in rejections
                if rejection["cause"] == "task_suggestion_rejected"
            )

            validate_seed_transformation_record(suggestion_rejection["details"]["seed_transformation"])
            validate_task_suggestion_record(suggestion_rejection["details"]["task_suggestion"])

    def test_task_expansion_persists_editor_rejection_details(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def no_initial_candidates(seed) -> list[CandidateTask]:
            return []

        def expansion_generator(seed) -> TaskExpansionResult:
            return TaskExpansionResult(
                candidates=[],
                rejected_suggestions=[],
                rejected_edits=[
                    EditedTask(
                        suggestion_id="suggestion_editor_rejected",
                        editor_action="rejected",
                        lineage={
                            "role": "task_editor",
                            "role_version": "role_task_editor_v1",
                            "output_type": "edited_task",
                            "provider_host": "local",
                            "model": "scripted",
                            "config_hash": "task_editor_local_v1",
                        },
                        rejection={
                            "cause": "unsupported_tool",
                            "message": "Edited task requested an unsupported executable tool.",
                        },
                    )
                ],
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_editor_rejection",
                candidate_generator=no_initial_candidates,
                enable_task_expansion=True,
                task_expansion_generator=expansion_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "task_editor_rejected")
            self.assertEqual(rejection["details"]["task_editor"]["editor_action"], "rejected")
            self.assertEqual(
                rejection["details"]["role_lineages"]["task_editor"]["role"],
                "task_editor",
            )

    def test_stateful_task_rejects_policy_that_skips_required_mutation(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def stateful_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_contacts_alice_followup",
                    instruction="Find Alice Zhang's email and record a follow-up note.",
                    constraints={
                        "task_type": "contact_followup",
                        "required_tools": ["lookup_contact_email", "record_contact_followup"],
                    },
                    difficulty={
                        "level": "medium",
                        "tool_count": 2,
                        "constraint_count": 2,
                        "state_changes": 1,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                    expected_state={
                        "contact_followup": {
                            "name": "Alice Zhang",
                            "note": "Send follow-up email to alice.zhang@example.test.",
                        }
                    },
                )
            ]

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_skip_mutation",
                role="scripted_solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": "Alice Zhang"},
                    ),
                ),
                final_response_template="{name}'s email is {email}. Follow-up recorded.",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_state_verifier_test",
                candidate_generator=stateful_candidate_generator,
                policy_generator=policy_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "solution_logic_error")
            self.assertEqual(rejection["details"]["check"], "contact_followup_state_matches_expected")

    def test_verification_rejection_preserves_generator_and_policy_role_lineage(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def generated_bad_expectation(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_generated_ben_bad",
                    instruction="Find Ben Carter's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Ben Carter"},
                    expected_answer="ben@example.test",
                    seed_ids=(seed.seed_id,),
                    generation_lineage={
                        "role": "task_generation",
                        "role_version": "role_task_generation_v1",
                        "output_type": "candidate_tasks",
                        "provider_host": "llm.example.test",
                        "model": "test-generator",
                        "config_hash": "task-hash",
                    },
                )
            ]

        def remote_policy(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_generated_ben",
                role="solution_policy",
                steps=(
                    ToolStep(
                        tool_name="lookup_contact_email",
                        arguments={"name": "Ben Carter"},
                    ),
                ),
                final_response_template="{name}'s email is {email}.",
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_role_rejection_lineage",
                candidate_generator=generated_bad_expectation,
                policy_generator=remote_policy,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "verification_failed")
            self.assertEqual(
                rejection["details"]["role_lineages"]["generator"]["role"],
                "task_generation",
            )
            self.assertEqual(
                rejection["details"]["role_lineages"]["solution_policy"]["role"],
                "solution_policy",
            )
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["role_outcomes"]["task_generation"]["rejected"], 1)
            self.assertEqual(quality_report["role_outcomes"]["solution_policy"]["rejected"], 1)

    def test_remote_policy_error_preserves_llm_cause_and_role_lineage(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def one_candidate(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_generated_alice",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        def failing_policy(task: CandidateTask) -> SolutionPolicy:
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="TypeError",
                retryable=False,
                retry_count=2,
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                    "retry_count": 2,
                    "error_class": "TypeError",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_policy_error_lineage",
                candidate_generator=one_candidate,
                policy_generator=failing_policy,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "llm_response_schema_error")
            self.assertEqual(rejection["details"]["retry_count"], 2)
            self.assertEqual(rejection["details"]["lineage"]["role"], "solution_policy")
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["role_outcomes"]["solution_policy"]["rejected"], 1)

    def test_rejects_candidate_when_tool_execution_fails(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_contact_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_unknown_contact",
                    instruction="Find John Doe's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "John Doe"},
                    expected_answer="john.doe@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                    "AGENT_DATA_API_KEY": "secret-test-key",
                    "AGENT_DATA_LLM_MODEL": "test-generator",
                },
                clear=False,
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_tool_error_test",
                    candidate_generator=invalid_contact_generator,
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_runtime_error")
            self.assertEqual(rejection["details"]["error_class"], "KeyError")
            self.assertIn("John Doe", rejection["details"]["message"])

    def test_rejects_candidate_when_tool_arguments_violate_schema(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_arguments_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool_argument",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_schema_error_test",
                candidate_generator=invalid_arguments_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ToolSchemaError")
            self.assertIn("name", rejection["details"]["message"])

    def test_rejects_candidate_when_required_tool_is_missing(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def missing_tool_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_missing_tool",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="missing_tool",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_missing_test",
                candidate_generator=missing_tool_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["cause"], "tool_missing")
            self.assertEqual(rejection["details"]["error_class"], "ToolMissingError")
            self.assertEqual(rejection["details"]["capability_gap"]["gap_type"], "unknown_tool")

    def test_explicit_tool_expansion_admits_curated_tool_and_reruns_candidate(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import CapabilityGap, ToolProposal

        def missing_tool_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_list_contacts",
                    instruction="List the known contact names.",
                    constraints={"must_use_tool": "list_contact_names"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="list_contact_names",
                    arguments={},
                    expected_answer="Alice Zhang",
                    seed_ids=(seed.seed_id,),
                )
            ]

        def policy_generator(task: CandidateTask) -> SolutionPolicy:
            return SolutionPolicy(
                policy_id="policy_list_contacts",
                role="solution_policy",
                steps=(ToolStep(tool_name="list_contact_names", arguments={}),),
                final_response_template="Known contacts: {contacts}",
                lineage={
                    "role": "solution_policy",
                    "role_version": "role_solution_policy_v1",
                    "output_type": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                },
            )

        def proposal_generator(gap: CapabilityGap) -> ToolProposal:
            self.assertEqual(gap.tool_name, "list_contact_names")
            return ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "proposal-hash",
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_tool_expansion_test",
                candidate_generator=missing_tool_generator,
                policy_generator=policy_generator,
                tool_proposal_generator=proposal_generator,
            )

            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.rejected_count, 0)
            self.assertIsNotNone(result.tool_proposals_path)

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(sample["trajectory"][0]["tool"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["proposal"]["tool_name"], "list_contact_names")
            self.assertEqual(sample["lineage"]["tool_expansion"]["admission"]["outcome"], "accepted")

            proposals = [
                json.loads(line)
                for line in result.tool_proposals_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(proposals[0]["proposal"]["tool_name"], "list_contact_names")
            self.assertEqual(proposals[0]["admission"]["outcome"], "accepted")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["tool_proposals"], "tool_proposals.jsonl")

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["tool_proposals"], 1)
            self.assertEqual(quality_report["counts"]["capability_gaps"], 1)
            self.assertIn("list_contact_names", quality_report["slices"]["proposed_tool"])

    def test_branching_fixture_executes_fallback_path_and_reports_lineage(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_branching_test",
                enable_branching=True,
            )

            self.assertEqual(result.accepted_count, 3)
            self.assertEqual(result.rejected_count, 1)
            samples = [
                json.loads(line)
                for line in result.samples_path.read_text(encoding="utf-8").splitlines()
            ]
            branch_sample = next(
                sample
                for sample in samples
                if sample["task"]["constraints"].get("task_type") == "contact_branch_fallback"
            )

            self.assertEqual(branch_sample["lineage"]["branching"]["selected_branch_id"], "fallback_full_name")
            self.assertEqual(branch_sample["lineage"]["branching"]["branch_depth"], 2)
            self.assertEqual(len(branch_sample["lineage"]["branching"]["branch_outcomes"]), 2)
            self.assertEqual(
                branch_sample["lineage"]["branching"]["branch_outcomes"][0]["failure_cause"],
                "tool_runtime_error",
            )
            self.assertTrue(branch_sample["lineage"]["branching"]["branch_outcomes"][1]["selected"])
            self.assertEqual(branch_sample["trajectory"][0]["arguments"], {"name": "Alice Zhang"})
            self.assertIn("branching", branch_sample["quality"]["tags"])

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["branch_attempts"], 2)
            self.assertEqual(quality_report["counts"]["branch_selected"], 1)
            self.assertEqual(quality_report["branch_outcomes"], {"accepted": 1, "rejected": 1})
            self.assertIn("2", quality_report["slices"]["branch_depth"])
            self.assertIn("fallback_full_name", quality_report["slices"]["selected_branch"])

    def test_branch_failure_classifies_missing_tool_cause(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def branch_missing_tool(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="candidate_branch_missing_tool",
                    instruction="Try a missing branch tool.",
                    constraints={"task_type": "contact_branch_fallback"},
                    difficulty={
                        "level": "medium",
                        "tool_count": 1,
                        "constraint_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 1,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(seed.seed_id,),
                    branch_plan={
                        "schema_version": "branch_plan_v1",
                        "plan_id": "branch_plan_missing_tool",
                        "max_depth": 1,
                        "branches": [
                            {
                                "branch_id": "missing_tool",
                                "node_type": "attempt",
                                "parent_id": None,
                                "condition": "Use a missing tool.",
                                "steps": [{"tool_name": "missing_tool", "arguments": {}}],
                                "final_response_template": "{email}",
                                "terminal_outcome": "accept_on_success",
                            }
                        ],
                    },
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_branch_missing_tool",
                candidate_generator=branch_missing_tool,
            )

            self.assertEqual(result.accepted_count, 0)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                rejection["details"]["branch_outcomes"][0]["failure_cause"],
                "tool_missing",
            )
            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["branch_failure_causes"], {"tool_missing": 1})

    def test_rejects_candidate_when_candidate_shape_is_invalid(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline

        def invalid_candidate_generator(seed) -> list[CandidateTask]:
            return [
                CandidateTask(
                    candidate_id="",
                    instruction="Find Alice Zhang's email address.",
                    constraints={"must_use_tool": "lookup_contact_email"},
                    difficulty={
                        "level": "easy",
                        "tool_count": 1,
                        "state_changes": 0,
                        "ambiguity": "none",
                        "recovery_paths": 0,
                    },
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                    expected_answer="alice.zhang@example.test",
                    seed_ids=(),
                )
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_candidate_schema_error_test",
                candidate_generator=invalid_candidate_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "unknown_candidate")
            self.assertEqual(rejection["cause"], "candidate_schema_error")
            self.assertEqual(rejection["details"]["error_class"], "ContractValidationError")

    def test_registered_tool_smoke_gate_classifies_empty_registry(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "synthesis.contacts_domain_pack.build_contact_tool_registry",
                return_value=ToolRegistry(),
            ):
                result = run_foundation_pipeline(
                    Path(tmpdir),
                    dataset_version="dataset_smoke_gate_test",
                    candidate_generator=lambda seed: [],
                )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "foundation_gate")
            self.assertEqual(rejection["cause"], "infrastructure_error")
            self.assertEqual(rejection["details"]["error_class"], "FoundationGateError")

    def test_generation_stage_provider_failure_writes_inspectable_artifacts(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.pipeline import run_foundation_pipeline

        def failing_generator(seed) -> list[CandidateTask]:
            raise LLMProviderError(
                cause="llm_provider_error",
                error_class="HTTPStatusError",
                retryable=True,
                retry_count=2,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_generation_failure_test",
                candidate_generator=failing_generator,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.quality_report_path.exists())

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rejection["candidate_id"], "generation_stage")
            self.assertEqual(rejection["cause"], "llm_provider_error")
            self.assertEqual(rejection["details"]["error_class"], "HTTPStatusError")
            self.assertEqual(rejection["details"]["retry_count"], 2)
            self.assertTrue(rejection["details"]["retry_eligible"])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rejection_causes"], {"llm_provider_error": 1})

            quality_report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(quality_report["counts"]["rejected"], 1)
            self.assertEqual(quality_report["rejection_causes"], {"llm_provider_error": 1})


if __name__ == "__main__":
    unittest.main()


class ContactsFixtureEnlargementTest(unittest.TestCase):
    def test_default_fixture_has_six_contacts_and_preserves_original_rows(self) -> None:
        from synthesis.environments import ContactEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            names = environment.list_contact_names()["contacts"]
            alice = environment.lookup_email("Alice Zhang")
            ben = environment.lookup_email("Ben Carter")

        self.assertEqual(
            names,
            "Alice Zhang, Ben Carter, Carla Diaz, David Kim, Elena Petrova, Frank Osei",
        )
        self.assertEqual(
            alice,
            {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
        )
        self.assertEqual(
            ben,
            {"name": "Ben Carter", "email": "ben.carter@example.test"},
        )
