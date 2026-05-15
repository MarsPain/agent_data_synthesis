from __future__ import annotations

import subprocess
import sys
import unittest


class DocumentationValidationTest(unittest.TestCase):
    def test_docs_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate_docs.py"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
