from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthesis.contracts import ContractValidationError, validate_manifest_record
from synthesis.datasets import attach_review_resolution_report_to_manifest
from synthesis.release_review import (
    REVIEW_RESOLUTION_REPORT_FILENAME,
    write_review_resolution_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve an existing local release-review queue without rerunning synthesis."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decisions-path", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.output_dir / "manifest.json"
    try:
        manifest = _load_manifest(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ContractValidationError, ValueError) as exc:
        print(f"manifest is absent or malformed: {type(exc).__name__}", file=sys.stderr)
        return 1

    artifacts = manifest.get("artifacts")
    assert isinstance(artifacts, Mapping)
    queue_artifact = artifacts.get("release_review_queue")
    if not isinstance(queue_artifact, str) or not queue_artifact.strip():
        print(
            "manifest is missing release_review_queue artifact",
            file=sys.stderr,
        )
        return 1
    dataset_version = manifest.get("dataset_version")
    assert isinstance(dataset_version, str)
    report_path = write_review_resolution_report(
        args.output_dir / queue_artifact,
        args.decisions_path,
        output_path=args.output_dir / REVIEW_RESOLUTION_REPORT_FILENAME,
        expected_dataset_version=dataset_version,
    )
    attach_review_resolution_report_to_manifest(
        manifest_path=manifest_path,
        report_path=report_path,
    )
    print(f"review_resolution_report={report_path}")
    return 0


def _load_manifest(path: Path) -> dict[str, object]:
    raw_manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("manifest must be a JSON object")
    validate_manifest_record(raw_manifest)
    return dict(raw_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
