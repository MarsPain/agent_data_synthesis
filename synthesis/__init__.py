"""Local executable foundation for Agent data synthesis."""

from __future__ import annotations

from typing import Any

__all__ = [
    "PipelineResult",
    "SerialJobResult",
    "run_foundation_pipeline",
    "run_serial_job",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        if name in {"SerialJobResult", "run_serial_job"}:
            from synthesis.orchestration import SerialJobResult, run_serial_job

            return {
                "SerialJobResult": SerialJobResult,
                "run_serial_job": run_serial_job,
            }[name]
        from synthesis.pipeline import PipelineResult, run_foundation_pipeline

        return {
            "PipelineResult": PipelineResult,
            "run_foundation_pipeline": run_foundation_pipeline,
        }[name]
    raise AttributeError(f"module 'synthesis' has no attribute {name!r}")
