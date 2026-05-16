from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainSeed:
    seed_id: str
    domain: str
    description: str
    task_taxonomy: tuple[str, ...]


def foundation_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_contacts_v1",
        domain="contacts_fixture",
        description="Small contact lookup domain for proving local executable samples.",
        task_taxonomy=("single_tool_lookup", "verification_failure_fixture"),
    )
