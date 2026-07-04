"""Local executable foundation for Agent data synthesis."""

from __future__ import annotations

from typing import Any

__all__ = ["PipelineResult", "run_foundation_pipeline"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from synthesis.pipeline import PipelineResult, run_foundation_pipeline

        exports = {
            "PipelineResult": PipelineResult,
            "run_foundation_pipeline": run_foundation_pipeline,
        }
        return exports[name]
    raise AttributeError(f"module 'synthesis' has no attribute {name!r}")
