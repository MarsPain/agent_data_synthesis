"""Explicit composition point for the production Agent-first Domain adapters.

The generic core never imports this module. It names the built-in adapters in
one place while callers remain free to register test-only or local-source
adapters through ``AdapterRegistry``.
"""

from __future__ import annotations

from pathlib import Path

from agent_synthesis.contacts import ContactsDomainAdapter
from agent_synthesis.domain import DomainAdapter
from agent_synthesis.mobile_messages import MobileMessagesDomainAdapter
from agent_synthesis.workspace_tasks import WorkspaceTasksDomainAdapter


BUILTIN_DOMAIN_IDS = (
    ContactsDomainAdapter.domain_id,
    MobileMessagesDomainAdapter.domain_id,
    WorkspaceTasksDomainAdapter.domain_id,
)


def builtin_fixture_domains() -> tuple[DomainAdapter, ...]:
    """Build the fixture-backed adapters used by the built-in composition path."""

    return (
        ContactsDomainAdapter.fixture(),
        MobileMessagesDomainAdapter.fixture(),
        WorkspaceTasksDomainAdapter.fixture(),
    )


def builtin_domain(domain_id: str, source: Path | None = None) -> DomainAdapter:
    """Compose one built-in Domain from a fixture or a local source file."""

    adapters = {
        ContactsDomainAdapter.domain_id: ContactsDomainAdapter,
        MobileMessagesDomainAdapter.domain_id: MobileMessagesDomainAdapter,
        WorkspaceTasksDomainAdapter.domain_id: WorkspaceTasksDomainAdapter,
    }
    try:
        adapter = adapters[domain_id]
    except KeyError:
        raise ValueError(f"unsupported built-in Domain: {domain_id}") from None
    return adapter.fixture() if source is None else adapter.from_local_file(source)
