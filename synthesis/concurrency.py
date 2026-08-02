"""Validation shared by local bounded orchestration entry points."""

from __future__ import annotations


# A local thread pool with a larger bound is almost certainly an operator
# configuration error and can exhaust descriptors or memory before useful work
# starts. The bound is deliberately generous for the local runner while still
# making the implementation-safe range explicit.
MAX_LOCAL_CONCURRENCY = 1024


def validate_concurrency(value: object, *, field_name: str = "max_concurrency") -> int:
    """Return a safe positive worker bound or raise ``ValueError``."""

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > MAX_LOCAL_CONCURRENCY
    ):
        raise ValueError(
            f"{field_name} must be a positive integer no greater than "
            f"{MAX_LOCAL_CONCURRENCY}"
        )
    return value
