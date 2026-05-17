from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class SourceGovernanceContractTest(unittest.TestCase):
    def test_source_record_requires_content_hash(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_source_record

        record = _source_record()
        record.pop("content_hash")

        with self.assertRaisesRegex(ContractValidationError, "content_hash"):
            validate_source_record(record)

    def test_source_record_rejects_unknown_license_label(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_source_record

        record = _source_record()
        record["license_label"] = "mystery-license"

        with self.assertRaisesRegex(ContractValidationError, "license_label"):
            validate_source_record(record)

    def test_external_source_requires_explicit_license_decision(self) -> None:
        from synthesis.sources import (
            NetworkPolicy,
            SandboxPolicy,
            SourceBundle,
            SourcePolicyError,
            SourceRecord,
            validate_source_bundle,
        )

        bundle = SourceBundle(
            bundle_id="bundle_external_missing_policy",
            sources=(
                SourceRecord(
                    source_id="source_external_1",
                    source_kind="external",
                    origin_reference="https://allowed.example.test/data",
                    retrieval_timestamp="1970-01-01T00:00:00Z",
                    content_hash="sha256:" + "a" * 64,
                    license_label="cc-by-4.0",
                    retention_eligible=True,
                    export_eligible=True,
                ),
            ),
            license_decisions=(),
            network_policy=NetworkPolicy(
                enabled=True,
                allowed_hosts=("allowed.example.test",),
                request_budget=1,
                require_source_events=True,
            ),
            sandbox_policy=SandboxPolicy(
                policy_id="sandbox_external_fixture",
                filesystem_isolation="artifact_subdir",
                generated_code_allowed=False,
                secret_redaction=True,
            ),
        )

        with self.assertRaisesRegex(SourcePolicyError, "license decision"):
            validate_source_bundle(bundle)

    def test_source_event_contract_rejects_raw_secret_leakage(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_source_event_record

        event = {
            "schema_version": "source_event_v1",
            "event_type": "source_rejected",
            "source_id": "source_external_1",
            "source_kind": "external",
            "policy_outcome": "rejected",
            "origin_alias": "allowed.example.test",
            "content_hash": "sha256:" + "a" * 64,
            "rejection_causes": ["network_disabled"],
            "raw_payload": "AGENT_DATA_API_KEY=secret-test-key",
        }

        with self.assertRaisesRegex(ContractValidationError, "raw secret"):
            validate_source_event_record(event)


class SourceGovernancePipelineTest(unittest.TestCase):
    def test_external_source_is_rejected_by_default_before_environment_construction(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.sources import build_external_fixture_source_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_source_rejected",
                source_bundle=build_external_fixture_source_bundle(network_enabled=False),
                enable_source_audit=True,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            self.assertIsNotNone(result.source_events_path)
            self.assertFalse((Path(tmpdir) / "environment" / "contacts.sqlite3").exists())

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8"))
            self.assertEqual(rejection["cause"], "source_policy_rejected")
            self.assertEqual(
                rejection["details"]["source_governance"]["policy_outcome"],
                "rejected",
            )
            self.assertNotIn("secret", json.dumps(rejection))

            source_events = [
                json.loads(line)
                for line in result.source_events_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(source_events[0]["event_type"], "source_rejected")
            self.assertNotIn("raw_payload", source_events[0])

    def test_allowed_external_fixture_threads_source_provenance_and_audit_artifacts(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.sources import build_external_fixture_source_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_source_allowed",
                source_bundle=build_external_fixture_source_bundle(network_enabled=True),
                enable_source_audit=True,
            )

            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rejected_count, 1)
            self.assertIsNotNone(result.source_events_path)

            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            provenance = sample["lineage"]["source_provenance"]
            self.assertEqual(provenance["source_kinds"], ["external"])
            self.assertEqual(provenance["license_outcomes"], ["allowed"])
            self.assertTrue(provenance["external_source_eligible"])
            self.assertEqual(
                sample["environment"]["source_provenance"]["source_policy_hash"],
                provenance["source_policy_hash"],
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["source_events"], "source_events.jsonl")
            self.assertEqual(manifest["source_policy_hashes"], [provenance["source_policy_hash"]])

            rejection = json.loads(result.rejections_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                rejection["details"]["source_governance"]["source_policy_hash"],
                provenance["source_policy_hash"],
            )
            self.assertNotIn("raw_payload", json.dumps(rejection))


def _source_record() -> dict[str, object]:
    return {
        "schema_version": "source_record_v1",
        "source_id": "source_fixture_contacts",
        "source_kind": "fixture",
        "origin_reference": "fixture://contacts",
        "retrieval_timestamp": None,
        "content_hash": "sha256:" + "0" * 64,
        "license_label": "fixture_internal",
        "retention_eligible": True,
        "export_eligible": True,
    }


if __name__ == "__main__":
    unittest.main()
