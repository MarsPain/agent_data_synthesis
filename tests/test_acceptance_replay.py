from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


class AcceptanceReplayContractTest(unittest.TestCase):
    def test_preparation_rejects_mismatched_plan_and_coverage_bindings(self) -> None:
        from synthesis.acceptance_replay import (
            AcceptancePreparation,
            AcceptanceReplayError,
        )

        preparation = AcceptancePreparation(
            profile_record={
                "profile_id": "fixture_acceptance",
                "dataset_version": "dataset_fixture_v1",
                "seed": {"seed_id": "seed_fixture_v1", "domain": "fixture"},
            },
            plan={"plan_id": "plan_fixture", "plan_hash": "sha256:" + "1" * 64},
            coverage_plan={
                "plan_id": "coverage_fixture",
                "plan_hash": "sha256:" + "2" * 64,
                "attempt_ceiling": 1,
            },
            source_policy_hash="sha256:" + "3" * 64,
            run_binding={
                "profile_id": "fixture_acceptance",
                "dataset_version": "dataset_fixture_v1",
                "seed_id": "seed_fixture_v1",
                "seed_domain": "fixture",
                "plan_id": "plan_fixture",
                "plan_hash": "sha256:" + "1" * 64,
                "coverage_plan_id": "coverage_fixture",
                "coverage_plan_hash": "sha256:" + "9" * 64,
                "source_policy_hash": "sha256:" + "3" * 64,
            },
        )

        with self.assertRaisesRegex(
            AcceptanceReplayError,
            "acceptance_binding_mismatch",
        ):
            preparation.validate()

    def test_freeze_rejects_unsafe_authorization_records(self) -> None:
        from synthesis.acceptance_replay import (
            AcceptanceReplayError,
            SanitizedProviderEvidenceRecorder,
        )

        authorization = SimpleNamespace(
            attempt_budget=1,
            generator_retry_limit=0,
            to_record=lambda: {
                "approved": True,
                "authorization_id": "fixture-acceptance-unsafe",
                "api_key": "must-not-be-retained",
            },
        )
        recorder = SanitizedProviderEvidenceRecorder(
            authorization=authorization,
            provider_identity={
                "provider_id": "openai_compatible",
                "provider_version": "client_v1",
                "provider_host": "fixture.test",
                "model": "generator",
                "config_hash": "sha256:" + "1" * 64,
                "parser_version": "domain_generation_parser_v1",
            },
            mutation_judge_identity={
                "provider": "openai_compatible",
                "provider_host": "fixture.test",
                "model": "judge",
                "config_hash": "sha256:" + "2" * 64,
                "role": "mutation_admission_judge",
                "role_version": "judge_v1",
            },
        )
        recorder.record_attempt(
            assignment={"assignment_id": "assignment_1"},
            request_hash="sha256:" + "3" * 64,
            response={"task_contracts": []},
            response_hash=None,
            outcome="validated",
            usage={},
        )
        recorder.set_mutation_judge_usage(
            {
                "attempts": 1,
                "attempt_ceiling": 1,
                "tokens": {},
                "outcomes": {"response_received": 1},
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(
                AcceptanceReplayError,
                "acceptance_authorization_malformed",
            ):
                recorder.freeze(
                    Path(tmpdir) / "provider.json",
                    qualification={
                        "status": "passed",
                        "effective_qualification": "release_candidate",
                        "claims": {
                            "publishable": False,
                            "training_recommended": False,
                        },
                    },
                    release_pack_verification={"status": "passed"},
                    release_pack_hash="sha256:" + "4" * 64,
                    run_binding={
                        "profile_id": "fixture_acceptance",
                        "dataset_version": "dataset_fixture_v1",
                        "seed_id": "seed_fixture_v1",
                        "seed_domain": "fixture",
                        "plan_id": "plan_fixture",
                        "plan_hash": "sha256:" + "5" * 64,
                        "coverage_plan_id": "coverage_fixture",
                        "coverage_plan_hash": "sha256:" + "6" * 64,
                        "source_policy_hash": "sha256:" + "7" * 64,
                    },
                )

    def test_harness_drives_common_sequence_through_adapter_without_runtime_input(self) -> None:
        from synthesis.acceptance_replay import (
            AcceptancePipelineResult,
            AcceptancePreparation,
            AcceptanceReleaseEvidence,
            AcceptanceReplayContract,
            AcceptanceReplayHarness,
            SanitizedProviderEvidenceRecorder,
        )

        class Authorization:
            approved = True
            attempt_budget = 1
            generator_retry_limit = 0

            def validate(self, *, profile: object, plan_attempt_ceiling: int) -> None:
                del profile, plan_attempt_ceiling

            def to_record(self) -> dict[str, object]:
                return {
                    "approved": True,
                    "authorization_id": "fixture-acceptance-001",
                    "attempt_budget": 1,
                    "generator_retry_limit": 0,
                    "generator_provider": "openai_compatible",
                    "generator_model": "generator",
                    "mutation_judge_provider": "openai_compatible",
                    "mutation_judge_model": "judge",
                }

        class Observer:
            def to_record(self) -> dict[str, object]:
                return {
                    "attempts": 1,
                    "attempt_ceiling": 1,
                    "tokens": {},
                    "outcomes": {"response_received": 1},
                }

            def to_failure_record(self) -> dict[str, object]:
                return self.to_record()

        class Adapter:
            evidence_contract = AcceptanceReplayContract(
                acceptance_schema_version="fixture_acceptance_v1",
                provider_evidence_schema_version="fixture_provider_evidence_v1",
                evidence_class="fixture_live",
                freeze_policy="fixture_sanitized_evidence_v1",
            )

            def __init__(self) -> None:
                self.events: list[str] = []
                self.recorder = None

            def prepare(self, *, profile: object, output_dir: Path) -> AcceptancePreparation:
                del profile
                self.events.append("prepare")
                return AcceptancePreparation(
                    profile_record={
                        "profile_id": "fixture_acceptance",
                        "dataset_version": "dataset_fixture_v1",
                        "seed": {
                            "seed_id": "seed_fixture_v1",
                            "domain": "fixture",
                        },
                    },
                    plan={
                        "plan_id": "plan_fixture",
                        "plan_hash": "sha256:" + "1" * 64,
                    },
                    coverage_plan={
                        "plan_id": "coverage_fixture",
                        "plan_hash": "sha256:" + "2" * 64,
                        "attempt_ceiling": 1,
                        "target_accepted_sample_count": 1,
                    },
                    source_policy_hash="sha256:" + "3" * 64,
                    run_binding={
                        "profile_id": "fixture_acceptance",
                        "dataset_version": "dataset_fixture_v1",
                        "seed_id": "seed_fixture_v1",
                        "seed_domain": "fixture",
                        "plan_id": "plan_fixture",
                        "plan_hash": "sha256:" + "1" * 64,
                        "coverage_plan_id": "coverage_fixture",
                        "coverage_plan_hash": "sha256:" + "2" * 64,
                        "source_policy_hash": "sha256:" + "3" * 64,
                    },
                )

            def validate_authorization(self, **kwargs: object) -> None:
                self.events.append("validate_authorization")
                kwargs["authorization"].validate(
                    profile=kwargs["preparation"].profile_record,
                    plan_attempt_ceiling=1,
                )

            def resolve_generator_config(self, supplied: object | None) -> object:
                self.events.append("resolve_config")
                return supplied or object()

            def validate_generator_config(self, **kwargs: object) -> None:
                del kwargs
                self.events.append("validate_config")

            def generator_identity(self, config: object) -> dict[str, object]:
                del config
                return {
                    "provider_id": "openai_compatible",
                    "provider_version": "client_v1",
                    "provider_host": "fixture.test",
                    "model": "generator",
                    "config_hash": "sha256:" + "4" * 64,
                    "parser_version": "domain_generation_parser_v1",
                }

            def mutation_judge_identity(self, *, profile: object, config: object) -> dict[str, object]:
                del profile, config
                return {
                    "provider": "openai_compatible",
                    "provider_host": "fixture.test",
                    "model": "judge",
                    "config_hash": "sha256:" + "5" * 64,
                    "role": "mutation_admission_judge",
                    "role_version": "judge_v1",
                }

            def create_recorder(self, **kwargs: object) -> object:
                self.events.append("create_recorder")
                self.recorder = SanitizedProviderEvidenceRecorder(
                    authorization=kwargs["authorization"],
                    provider_identity=kwargs["provider_identity"],
                    mutation_judge_identity=kwargs["mutation_judge_identity"],
                    contract=self.evidence_contract,
                )
                return self.recorder

            def create_usage_observer(self, **kwargs: object) -> Observer:
                del kwargs
                self.events.append("create_observer")
                return Observer()

            def preflight_mutation_judge(self, **kwargs: object) -> dict[str, object]:
                del kwargs
                self.events.append("preflight")
                return {"status": "passed"}

            def build_provider(self, **kwargs: object) -> object:
                del kwargs
                self.events.append("build_provider")
                return object()

            def run_pipeline(self, **kwargs: object) -> AcceptancePipelineResult:
                self.events.append("pipeline")
                recorder = kwargs["recorder"]
                recorder.record_attempt(
                    assignment={"assignment_id": "assignment_1"},
                    request_hash="sha256:" + "6" * 64,
                    response={"task_contracts": []},
                    response_hash=None,
                    outcome="validated",
                    usage={},
                )
                return AcceptancePipelineResult(result=object(), accepted_count=1)

            def validate_pipeline(self, **kwargs: object) -> None:
                del kwargs
                self.events.append("validate_pipeline")

            def mutation_judge_attempt_ceiling(self, **kwargs: object) -> int:
                del kwargs
                return 1

            def write_release_evidence(self, **kwargs: object) -> AcceptanceReleaseEvidence:
                self.events.append("release")
                output_dir = kwargs["output_dir"]
                pack = output_dir / "dataset_release_pack.json"
                paths = [
                    output_dir / "episode_replay_report.json",
                    output_dir / "evaluation_report.json",
                    output_dir / "profile_decision_report.json",
                    output_dir / "dataset_release_report.json",
                    output_dir / "release_quality_audit.json",
                    pack,
                ]
                for path in paths:
                    path.write_text("{}\n", encoding="utf-8")
                return AcceptanceReleaseEvidence(
                    replay_report_path=paths[0],
                    evaluation_report_path=paths[1],
                    profile_decision_path=paths[2],
                    dataset_release_report_path=paths[3],
                    release_quality_audit_path=paths[4],
                    release_pack_path=pack,
                    release_pack_verification={"status": "passed"},
                    qualification={
                        "status": "passed",
                        "effective_qualification": "release_candidate",
                        "claims": {
                            "publishable": False,
                            "training_recommended": False,
                        },
                    },
                    release_pack_hash="sha256:" + hashlib.sha256(pack.read_bytes()).hexdigest(),
                )

            def bind_sample_assignments(self, **kwargs: object) -> None:
                del kwargs

            def replay(self, *, evidence: object, preparation: object) -> int:
                del preparation
                self.events.append("replay")
                return len(evidence["replay_attempts"])

            def build_proof(self, *, proof_root: Path, acceptance_dir: Path) -> Path:
                del acceptance_dir
                self.events.append("proof")
                proof = proof_root / "fixture_proof.json"
                proof.write_text("{}\n", encoding="utf-8")
                return proof

            def verify_proof(self, proof_path: Path) -> dict[str, object]:
                del proof_path
                self.events.append("verify_proof")
                return {"status": "passed"}

            def provider_evidence_path(self, *, proof_path: Path, acceptance_dir: Path) -> Path:
                del proof_path
                return acceptance_dir / "trace" / "provider.json"

            def write_failure(self, *args: object, **kwargs: object) -> Path:
                del args, kwargs
                raise AssertionError("happy path must not write a failure")

        adapter = Adapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AcceptanceReplayHarness(adapter).run(
                Path(tmpdir) / "acceptance",
                profile=object(),
                authorization=Authorization(),
                proof_root=Path(tmpdir) / "proof",
            )

        self.assertEqual(result.replay["provider_calls"], 0)
        self.assertEqual(
            adapter.events,
            [
                "prepare",
                "validate_authorization",
                "resolve_config",
                "validate_config",
                "create_recorder",
                "create_observer",
                "preflight",
                "build_provider",
                "pipeline",
                "validate_pipeline",
                "release",
                "replay",
                "proof",
                "verify_proof",
            ],
        )


if __name__ == "__main__":
    unittest.main()
