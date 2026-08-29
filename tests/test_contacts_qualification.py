from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class ContactsReleaseProvider:
    """Deterministic provider-shaped input used only by offline tests."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def generate_json(self, prompt: str, *, role: str):
        from synthesis.llm import LLMGenerationResult

        payload = json.loads(prompt)
        self.payloads.append(payload)
        assignment = payload["coverage_assignment"]
        task_type = assignment["task_type"]
        grounding = next(iter(payload["grounding_context"].values()))[0]
        observation = grounding["observation"]
        capabilities = list(payload["task_types"][0]["required_capabilities"])
        required_tools = list(assignment["required_tools"])
        recovery = assignment["recovery"] != "none"
        record: dict[str, object] = {
            "candidate_id": (
                f"{payload['batch_context']['candidate_id_prefix']}"
                f"{assignment['assignment_ordinal']:02d}"
            ),
            "instruction": (
                f"Find {observation['name']}'s email and record a follow-up "
                f"to send {observation['email']}."
                if task_type == "contact_followup"
                else (
                    f"Try the abbreviated name before finding "
                    f"{observation['name']}'s email."
                    if recovery
                    else f"Find {observation['name']}'s email."
                )
            ),
            "task_type": task_type,
            "difficulty": {
                "level": assignment["difficulty"],
                "tool_count": len(required_tools),
                "constraint_count": 2 if recovery else 1,
                "state_changes": int(task_type == "contact_followup"),
                "ambiguity": assignment["ambiguity"],
                "recovery_paths": int(recovery),
            },
            "required_capabilities": capabilities,
            "required_tools": required_tools,
            "primary_tool": required_tools[0],
            "primary_arguments": dict(grounding["primary_arguments"]),
            "final_answer_contains": observation["email"],
            "expected_state": (
                [
                    {
                        "check_type": "contact_followup",
                        "expected": {
                            "name": observation["name"],
                            "note": (
                                f"Send follow-up email to {observation['email']}."
                            ),
                        },
                    }
                ]
                if task_type == "contact_followup"
                else []
            ),
        }
        return LLMGenerationResult(
            content={"task_contracts": [record]},
            lineage={
                "role": role,
                "provider_host": "offline.contacts.test",
                "model": "deterministic_contacts_generator_v1",
                "config_hash": "sha256:" + "1" * 64,
                "retry_count": 0,
            },
        )


class ContactsQualificationTest(unittest.TestCase):
    def test_release_profile_selects_only_contacts_contracts(self) -> None:
        from synthesis.contacts_qualification import contacts_release_candidate_profile

        profile = contacts_release_candidate_profile()

        self.assertEqual(profile["profile_id"], "contacts_release_candidate")
        self.assertEqual(profile["profile_version"], "contacts_release_candidate_v1")
        self.assertEqual(
            profile["domain_pack_reference"]["domain_pack_id"],
            "contacts",
        )
        self.assertEqual(
            {item["capability_key"] for item in profile["capability_references"]},
            {
                "contact_lookup",
                "followup_recording",
                "contact_lookup_recovery",
                "missing_contact_safe_failure",
            },
        )
        self.assertEqual(
            profile["coverage"]["profile_id"],
            "contacts_representative",
        )
        self.assertEqual(profile["held_out"]["suite_id"], "contacts_heldout_v1")
        self.assertEqual(profile["mutation"]["mode"], "enforce")
        self.assertNotIn("workspace", json.dumps(profile).lower())

    def test_current_contacts_evidence_qualifies_without_higher_claims(self) -> None:
        from synthesis.contacts_qualification import qualify_contacts_release_candidate
        from synthesis.coverage_assignments import (
            build_coverage_assignment_scheduler_factory,
        )
        from synthesis.datasets import (
            attach_dataset_release_pack_to_manifest,
            attach_dataset_release_report_to_manifest,
            attach_profile_decision_report_to_manifest,
            attach_release_quality_audit_to_manifest,
        )
        from synthesis.dataset_release import write_dataset_release_report
        from synthesis.evaluation import write_evaluation_report
        from synthesis.mutation_admission import build_local_candidate_admission_evaluator
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.profile_decisions import write_profile_decision_report
        from synthesis.release_pack import (
            verify_dataset_release_pack,
            write_dataset_release_pack,
        )
        from synthesis.release_quality import write_release_quality_audit
        from synthesis.run_profiles import load_run_profile
        from synthesis.contact_mutations import (
            build_contact_followup_semantic_mutation_judge,
            contact_followup_mutation_policies,
        )
        from synthesis.environments import ContactEnvironment
        from synthesis.contracts import validate_qualification_report_record

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/contacts-release-candidate.json")
        )
        provider = ContactsReleaseProvider()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            admission_environment = ContactEnvironment.create_fixture(
                root / "admission"
            )
            admission_evaluator = build_local_candidate_admission_evaluator(
                mode="enforce",
                policies=contact_followup_mutation_policies(admission_environment),
                state_changing_tools=("record_contact_followup",),
                judge=build_contact_followup_semantic_mutation_judge(
                    admission_environment
                ),
            )
            result = run_foundation_pipeline(
                root / "release",
                dataset_version=profile.dataset_version,
                coverage_scheduler_factory=build_coverage_assignment_scheduler_factory(
                    provider
                ),
                admission_evaluator=admission_evaluator,
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
                run_profile=profile,
            )
            self.assertEqual(result.accepted_count, 5)
            self.assertGreaterEqual(len(provider.payloads), 5)

            evaluation_path = write_evaluation_report(
                manifest_path=result.manifest_path,
                quality_report_path=result.quality_report_path,
            )
            from synthesis.datasets import attach_evaluation_report_to_manifest

            attach_evaluation_report_to_manifest(
                manifest_path=result.manifest_path,
                report_path=evaluation_path,
            )
            profile_decision_path = write_profile_decision_report(
                manifest_path=result.manifest_path,
                quality_report_path=result.quality_report_path,
                evaluation_report_path=evaluation_path,
                runtime_seconds=1.0,
            )
            attach_profile_decision_report_to_manifest(
                manifest_path=result.manifest_path,
                report_path=profile_decision_path,
            )
            release_report_path = write_dataset_release_report(
                manifest_path=result.manifest_path,
                quality_report_path=result.quality_report_path,
                evaluation_report_path=evaluation_path,
                profile_decision_report_path=profile_decision_path,
            )
            release_report = json.loads(
                release_report_path.read_text(encoding="utf-8")
            )
            from synthesis.contacts_qualification import (
                contacts_release_candidate_profile,
            )

            self.assertEqual(
                release_report["release_completeness"]["thresholds"],
                contacts_release_candidate_profile()["completeness"],
            )
            attach_dataset_release_report_to_manifest(
                manifest_path=result.manifest_path,
                report_path=release_report_path,
            )
            audit_path = write_release_quality_audit(
                manifest_path=result.manifest_path,
            )
            attach_release_quality_audit_to_manifest(
                manifest_path=result.manifest_path,
                audit_path=audit_path,
            )
            pack_path = root / "release" / "dataset_release_pack.json"
            attach_dataset_release_pack_to_manifest(
                manifest_path=result.manifest_path,
                pack_path=pack_path,
            )
            write_dataset_release_pack(
                manifest_path=result.manifest_path,
                dataset_release_report_path=release_report_path,
                output_path=pack_path,
            )
            self.assertEqual(
                verify_dataset_release_pack(pack_path)["verification"]["status"],
                "passed",
            )

            manifest_before = result.manifest_path.read_bytes()
            pack_before = pack_path.read_bytes()
            report = qualify_contacts_release_candidate(
                manifest_path=result.manifest_path,
                release_pack_path=pack_path,
                release_quality_audit_path=audit_path,
            )
            self.assertEqual(result.manifest_path.read_bytes(), manifest_before)
            self.assertEqual(pack_path.read_bytes(), pack_before)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["effective_qualification"], "release_candidate")
            self.assertTrue(report["claims"]["release_candidate"])
            self.assertFalse(report["claims"]["publishable"])
            self.assertFalse(report["claims"]["training_recommended"])
            validate_qualification_report_record(report)
            from synthesis.qualification import write_release_candidate_qualification

            qualification_path = root / "release" / "qualification_report.json"
            write_release_candidate_qualification(
                manifest_path=result.manifest_path,
                release_pack_path=pack_path,
                release_quality_audit_path=audit_path,
                output_path=qualification_path,
            )
            written = json.loads(qualification_path.read_text(encoding="utf-8"))
            self.assertEqual(written["effective_qualification"], "release_candidate")

            # A byte-changing repack is a fresh subject.  The old decision
            # history is accepted as input only after the new subject is
            # independently evaluated; it is never carried over by identity.
            repacked_path = pack_path.read_bytes() + b"\n"
            pack_path.write_bytes(repacked_path)
            same_directory_repack = qualify_contacts_release_candidate(
                manifest_path=result.manifest_path,
                release_pack_path=pack_path,
                release_quality_audit_path=audit_path,
                history=report["historical_decisions"],
            )
            self.assertEqual(same_directory_repack["status"], "passed")
            self.assertNotEqual(
                same_directory_repack["subject"]["subject_hash"],
                report["subject"]["subject_hash"],
            )

    def test_invalidating_contacts_release_dependency_removes_current_claim(self) -> None:
        from synthesis.qualification import (
            build_release_candidate_evidence,
            evaluate_cumulative_qualification,
        )
        from tests.test_qualification import (
            _binding,
            _passing_domain_assessment,
            _passing_machine_gates,
            _release_completeness,
            _release_pack_verification,
            _release_quality_audit,
        )

        binding = _binding()
        release_candidate = evaluate_cumulative_qualification(
            subject=binding,
            evidence=build_release_candidate_evidence(
                binding=binding,
                machine_gates=_passing_machine_gates(),
                domain_assessment=_passing_domain_assessment(binding),
                release_completeness=_release_completeness(),
                release_quality_audit=_release_quality_audit(),
                release_pack_verification=_release_pack_verification(),
            ),
        )
        invalidated = evaluate_cumulative_qualification(
            subject=binding,
            history=release_candidate["historical_decisions"],
            invalidated_evidence=("release_pack",),
        )

        self.assertEqual(invalidated["effective_qualification"], "unqualified")
        self.assertEqual(invalidated["status"], "insufficient_evidence")
        self.assertIn(
            "qualification_dependency_invalidated",
            invalidated["decision"]["reason_codes"],
        )

    def test_legacy_contacts_release_pack_cannot_be_promoted(self) -> None:
        from synthesis.contacts_qualification import qualify_contacts_release_candidate
        from synthesis.run_profiles import load_run_profile
        from synthesis.pipeline import run_foundation_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile = load_run_profile(
                Path("tests/fixtures/run_profiles/foundation-release-candidate.json")
            )
            result = run_foundation_pipeline(
                root,
                dataset_version=profile.dataset_version,
                seed_override=profile.seed,
                run_profile_metadata=profile.sanitized_metadata(),
                run_profile=profile,
            )
            manifest_path = result.manifest_path
            report = qualify_contacts_release_candidate(
                manifest_path=manifest_path,
                release_pack_path=root / "legacy-pack.json",
            )

        self.assertNotEqual(report["effective_qualification"], "release_candidate")
        self.assertFalse(report["claims"]["publishable"])


if __name__ == "__main__":
    unittest.main()
