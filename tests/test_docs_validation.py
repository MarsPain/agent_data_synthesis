from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.validate_docs import (
    contains_top_link,
    is_wayfinder_map,
    is_wayfinder_map_path,
    resolve_link,
    strip_fenced_blocks,
)


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

    def test_localized_readme_link_must_appear_near_the_top(self) -> None:
        source = Path("README.md").resolve()
        target = Path("README.zh.md").resolve()
        self.assertTrue(
            contains_top_link(
                source,
                target,
                "# Agent Data Synthesis\n\n[简体中文](README.zh.md)\n",
            )
        )
        self.assertFalse(
            contains_top_link(
                source,
                target,
                "\n" * 8 + "[简体中文](README.zh.md)\n",
            )
        )

    def test_wayfinder_map_is_distinct_from_feature_index(self) -> None:
        self.assertTrue(
            is_wayfinder_map(
                "# Decision Map\n\n- **Status:** open\n"
                "- **Label:** `wayfinder:map`\n"
                "- **Assignee:** Unassigned\n"
            )
        )
        self.assertFalse(is_wayfinder_map("# Implementation Feature\n"))

    def test_wayfinder_map_path_is_explicitly_suffixed(self) -> None:
        self.assertTrue(
            is_wayfinder_map_path(
                Path(".scratch/outcome-validated-domain-pack-wayfinding/README.md")
            )
        )
        self.assertFalse(
            is_wayfinder_map_path(
                Path(".scratch/outcome-validated-domain-pack/README.md")
            )
        )


if __name__ == "__main__":
    unittest.main()
