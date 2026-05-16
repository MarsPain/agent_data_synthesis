from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FoundationCliTest(unittest.TestCase):
    def test_default_output_directory_is_outside_docs(self) -> None:
        from main import parse_args

        with patch.object(sys, "argv", ["main.py"]):
            args = parse_args()

        self.assertEqual(args.output_dir, Path("artifacts/foundation"))

    def test_main_writes_requested_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "foundation"
            env = {
                **os.environ,
                "AGENT_DATA_LLM_BASE_URL": "https://llm.example.test/v1",
                "AGENT_DATA_API_KEY": "secret-test-key",
                "AGENT_DATA_LLM_MODEL": "test-generator",
            }

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--output-dir",
                    str(output_dir),
                    "--dataset-version",
                    "dataset_cli_test",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "manifest.json").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], "dataset_cli_test")
            self.assertIn("accepted=2", result.stdout)
            self.assertNotIn("secret-test-key", result.stdout)

    def test_use_llm_requires_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("AGENT_DATA_LLM_BASE_URL", None)
            env.pop("AGENT_DATA_API_KEY", None)
            env.pop("AGENT_DATA_LLM_MODEL", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--use-llm",
                    "--output-dir",
                    str(Path(tmpdir) / "foundation"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "AGENT_DATA_LLM_BASE_URL, AGENT_DATA_API_KEY, and AGENT_DATA_LLM_MODEL",
                result.stderr,
            )
            self.assertNotIn("Authorization", result.stderr)


if __name__ == "__main__":
    unittest.main()
