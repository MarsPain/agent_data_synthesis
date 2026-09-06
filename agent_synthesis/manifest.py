"""Flat public manifest persistence for final Agent-first artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ManifestFile(BaseModel):
    """One final public artifact bound by a flat content hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)


class RunManifest(BaseModel):
    """Public run identity without object-level or nested evidence hashes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "agent_run_manifest_v1"
    run_id: str = Field(min_length=1, max_length=128)
    configuration: dict[str, JsonValue]
    source_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    files: tuple[ManifestFile, ...]


def build_manifest(
    *,
    run_id: str,
    configuration: dict[str, object],
    source_fingerprint: str,
    artifact_paths: tuple[Path, ...],
) -> RunManifest:
    """Build a manifest that binds only the final public collection files."""

    files = tuple(
        ManifestFile(
            path=path.name,
            sha256=_content_hash(path.read_bytes()),
            byte_count=path.stat().st_size,
        )
        for path in artifact_paths
    )
    return RunManifest(
        run_id=run_id,
        configuration=configuration,
        source_fingerprint=source_fingerprint,
        files=files,
    )


def write_manifest(path: Path, manifest: RunManifest) -> None:
    """Write validated, deterministic JSON for the public run manifest."""

    path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def _content_hash(contents: bytes) -> str:
    return "sha256:" + hashlib.sha256(contents).hexdigest()
