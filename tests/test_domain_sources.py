from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class DomainSourceImporterTest(unittest.TestCase):
    def test_contacts_importer_uses_shared_profile_local_governance(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.environments import ContactsEnvironmentInput

        importer = resolve_domain_source_importer(
            "contacts_fixture",
            "local_contacts_json",
        )
        source_import = build_profile_local_domain_source_input(
            ProfileLocalDomainSourceRequest(
                domain_id="contacts_fixture",
                kind="local_contacts_json",
                source_id="source_profile_contacts_v1",
                path=Path("tests/fixtures/run_profiles/contacts-profile.json"),
                license_label="cc-by-4.0",
                max_bytes=65536,
            ),
            importer=importer,
        )

        self.assertEqual(source_import.domain_id, "contacts_fixture")
        self.assertEqual(source_import.source_kind, "local_contacts_json")
        self.assertIsInstance(source_import.environment_input, ContactsEnvironmentInput)
        self.assertEqual(
            source_import.source_summary["source_id"],
            "source_profile_contacts_v1",
        )
        self.assertRegex(
            str(source_import.source_summary["source_policy_hash"]),
            r"^sha256:[0-9a-f]{64}$",
        )
        exported = json.dumps(source_import.events, sort_keys=True)
        self.assertNotIn("contacts-profile.json", exported)
        self.assertNotIn("alice.zhang@example.test", exported)

    def test_mobile_importer_uses_shared_profile_local_governance(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.mobile_environment import MobileMessagesEnvironmentInput

        importer = resolve_domain_source_importer(
            "mobile_messages_fixture",
            "local_mobile_messages_json",
        )
        source_import = build_profile_local_domain_source_input(
            ProfileLocalDomainSourceRequest(
                domain_id="mobile_messages_fixture",
                kind="local_mobile_messages_json",
                source_id="source_profile_mobile_messages_v1",
                path=Path("tests/fixtures/run_profiles/mobile-messages-profile.json"),
                license_label="cc-by-4.0",
                max_bytes=65536,
            ),
            importer=importer,
        )

        self.assertEqual(source_import.domain_id, "mobile_messages_fixture")
        self.assertEqual(source_import.source_kind, "local_mobile_messages_json")
        self.assertIsInstance(
            source_import.environment_input,
            MobileMessagesEnvironmentInput,
        )
        self.assertEqual(source_import.source_summary["kind"], "local_mobile_messages_json")
        exported = json.dumps(source_import.events, sort_keys=True)
        self.assertNotIn("mobile-messages-profile.json", exported)
        self.assertNotIn("project update tomorrow", exported)
        self.assertNotIn("4821", exported)

    def test_resolver_rejects_mismatched_domain_and_source_kind(self) -> None:
        from synthesis.domain_sources import resolve_domain_source_importer

        with self.assertRaisesRegex(ValueError, "local_mobile_messages_json"):
            resolve_domain_source_importer(
                "contacts_fixture",
                "local_mobile_messages_json",
            )
        with self.assertRaisesRegex(ValueError, "local_contacts_json"):
            resolve_domain_source_importer(
                "mobile_messages_fixture",
                "local_contacts_json",
            )

    def test_profile_local_source_rejects_payload_without_leaking_content(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.sources import ControlledSourceFetchError

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mobile.json"
            path.write_text(
                json.dumps({"threads": [], "messages": []}),
                encoding="utf-8",
            )
            importer = resolve_domain_source_importer(
                "mobile_messages_fixture",
                "local_mobile_messages_json",
            )

            with self.assertRaisesRegex(
                ControlledSourceFetchError,
                "environment source",
            ) as raised:
                build_profile_local_domain_source_input(
                    ProfileLocalDomainSourceRequest(
                        domain_id="mobile_messages_fixture",
                        kind="local_mobile_messages_json",
                        source_id="source_mobile_bad",
                        path=path,
                        license_label="cc-by-4.0",
                        max_bytes=65536,
                    ),
                    importer=importer,
                )

        exported = json.dumps(raised.exception.events, sort_keys=True)
        self.assertNotIn(str(path), exported)
        self.assertNotIn("mobile.json", exported)


if __name__ == "__main__":
    unittest.main()
