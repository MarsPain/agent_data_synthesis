from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.validate_docs import resolve_link, strip_fenced_blocks


class DocumentationValidationTest(unittest.TestCase):
    def test_docs_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate_docs.py"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fenced_template_links_are_ignored(self) -> None:
        text = "before\n```md\n[placeholder](missing.md)\n```\nafter"
        self.assertEqual(strip_fenced_blocks(text), "before\nafter")

    def test_external_and_anchor_links_do_not_resolve_to_files(self) -> None:
        source = Path("docs/example.md")
        self.assertIsNone(resolve_link(source, "https://example.test/doc"))
        self.assertIsNone(resolve_link(source, "#local-heading"))


if __name__ == "__main__":
    unittest.main()
