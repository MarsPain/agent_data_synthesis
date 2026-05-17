from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


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

    def test_fetched_source_request_rejects_unsafe_scheme_and_host(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_fetched_source_request_record,
        )

        request = _fetched_source_request()
        request["url"] = "http://allowed.example.test/contacts.json"

        with self.assertRaisesRegex(ContractValidationError, "https"):
            validate_fetched_source_request_record(request)

        request = _fetched_source_request()
        request["url"] = "https://blocked.example.test/contacts.json"

        with self.assertRaisesRegex(ContractValidationError, "allowlisted"):
            validate_fetched_source_request_record(request)

    def test_contacts_environment_input_requires_valid_contact_rows(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_contacts_environment_input_record,
        )

        record = _contacts_environment_input()
        record["contacts"][0].pop("email")

        with self.assertRaisesRegex(ContractValidationError, "contacts.0.email"):
            validate_contacts_environment_input_record(record)

    def test_source_event_contract_accepts_fetch_and_environment_admission_events(self) -> None:
        from synthesis.contracts import validate_source_event_record

        for event_type in (
            "fetch_attempt",
            "fetch_accepted",
            "fetch_rejected",
            "environment_source_admitted",
            "environment_source_rejected",
        ):
            event = _source_event(event_type)
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

    def test_controlled_fetch_builds_contacts_environment_without_exporting_payload(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.sources import (
            FetchedSourceRequest,
            build_network_contacts_source_input,
        )

        payload = json.dumps(
            {
                "contacts": [
                    {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
                    {"name": "Ben Carter", "email": "ben.carter@example.test"},
                ],
                "followups": [],
            }
        ).encode("utf-8")
        client = _MockHttpClient(
            _HttpResponse(
                status_code=200,
                headers={"content-type": "application/json; charset=utf-8"},
                content=payload,
            )
        )
        source_input = build_network_contacts_source_input(
            FetchedSourceRequest(
                url="https://allowed.example.test/contacts.json",
                allowed_hosts=("allowed.example.test",),
                request_budget=1,
                timeout_seconds=2.0,
                max_bytes=4096,
                expected_content_type="application/json",
                license_label="cc-by-4.0",
                require_source_audit=True,
            ),
            http_client=client,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_network_contacts",
                source_bundle=source_input.source_bundle,
                contacts_environment_input=source_input.environment_input,
                source_events=source_input.events,
                enable_source_audit=True,
            )

            self.assertEqual(client.requests, 1)
            self.assertEqual(result.accepted_count, 2)
            self.assertIsNotNone(result.source_events_path)
            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            provenance = sample["lineage"]["source_provenance"]
            self.assertEqual(provenance["source_kinds"], ["external"])
            self.assertTrue(provenance["external_source_eligible"])
            self.assertEqual(
                sample["environment"]["reset_recipe"]["source_bundle_id"],
                source_input.environment_input.source_bundle_id,
            )
            exported = (
                result.samples_path.read_text(encoding="utf-8")
                + result.rejections_path.read_text(encoding="utf-8")
                + result.manifest_path.read_text(encoding="utf-8")
                + result.source_events_path.read_text(encoding="utf-8")
            )
            self.assertNotIn("contacts.json", exported)
            self.assertNotIn("Alice Zhang", result.source_events_path.read_text(encoding="utf-8"))

    def test_controlled_fetch_rejects_oversize_payload_with_sanitized_event(self) -> None:
        from synthesis.sources import (
            ControlledSourceFetchError,
            FetchedSourceRequest,
            build_network_contacts_source_input,
        )

        client = _MockHttpClient(
            _HttpResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                content=b'{"contacts":[]}',
            )
        )

        with self.assertRaisesRegex(ControlledSourceFetchError, "payload too large") as raised:
            build_network_contacts_source_input(
                FetchedSourceRequest(
                    url="https://allowed.example.test/contacts.json",
                    allowed_hosts=("allowed.example.test",),
                    request_budget=1,
                    timeout_seconds=2.0,
                    max_bytes=4,
                    expected_content_type="application/json",
                    license_label="cc-by-4.0",
                    require_source_audit=True,
                ),
                http_client=client,
            )

        self.assertEqual(client.requests, 1)
        events = raised.exception.events
        self.assertEqual(events[-1]["event_type"], "fetch_rejected")
        self.assertEqual(events[-1]["rejection_causes"], ["payload_too_large"])
        self.assertNotIn("contacts", json.dumps(events))

    def test_environment_source_rejection_does_not_count_as_executable(self) -> None:
        from synthesis.pipeline import run_foundation_pipeline
        from synthesis.sources import (
            FetchedSourceRequest,
            build_network_contacts_source_input,
        )

        client = _MockHttpClient(
            _HttpResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                content=json.dumps({"contacts": [{"name": "", "email": "bad"}]}).encode("utf-8"),
            )
        )
        source_input = build_network_contacts_source_input(
            FetchedSourceRequest(
                url="https://allowed.example.test/contacts.json",
                allowed_hosts=("allowed.example.test",),
                request_budget=1,
                timeout_seconds=2.0,
                max_bytes=4096,
                expected_content_type="application/json",
                license_label="cc-by-4.0",
                require_source_audit=True,
            ),
            http_client=client,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_bad_environment_source",
                source_bundle=source_input.source_bundle,
                contacts_environment_input=source_input.environment_input,
                source_events=source_input.events,
                enable_source_audit=True,
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 1)
            report = json.loads(result.quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["executable"], 0)
            self.assertEqual(report["rates"]["executable_rate"], 0.0)
            self.assertIn("rejected", report["slices"]["environment_source_admission"])


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


def _fetched_source_request() -> dict[str, object]:
    return {
        "schema_version": "fetched_source_request_v1",
        "url": "https://allowed.example.test/contacts.json",
        "allowed_hosts": ["allowed.example.test"],
        "request_budget": 1,
        "timeout_seconds": 2.0,
        "max_bytes": 4096,
        "expected_content_type": "application/json",
        "license_label": "cc-by-4.0",
        "require_source_audit": True,
    }


def _contacts_environment_input() -> dict[str, object]:
    return {
        "schema_version": "contacts_environment_input_v1",
        "contacts": [{"name": "Alice Zhang", "email": "alice.zhang@example.test"}],
        "followups": [],
        "source_bundle_id": "bundle_network_contacts",
        "source_policy_hash": "sha256:" + "1" * 64,
        "validation_errors": [],
    }


def _source_event(event_type: str) -> dict[str, object]:
    return {
        "schema_version": "source_event_v1",
        "event_type": event_type,
        "source_id": "source_external_contacts",
        "source_kind": "external",
        "policy_outcome": "allowed" if event_type.endswith("accepted") or event_type.endswith("admitted") else "rejected",
        "origin_alias": "allowed.example.test",
        "content_hash": "sha256:" + "2" * 64,
        "license_label": "cc-by-4.0",
        "license_outcome": "allowed",
        "source_policy_hash": "sha256:" + "3" * 64,
        "rejection_causes": [] if event_type.endswith("accepted") or event_type.endswith("admitted") else ["payload_too_large"],
    }


class _HttpResponse(SimpleNamespace):
    status_code: int
    headers: dict[str, str]
    content: bytes


class _MockHttpClient:
    def __init__(self, response: _HttpResponse) -> None:
        self.response = response
        self.requests = 0

    def get(self, url: str, *, timeout: float, follow_redirects: bool) -> _HttpResponse:
        self.requests += 1
        self.last_request = {
            "url": url,
            "timeout": timeout,
            "follow_redirects": follow_redirects,
        }
        return self.response


if __name__ == "__main__":
    unittest.main()
