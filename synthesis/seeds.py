from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainSeed:
    seed_id: str
    domain: str
    description: str
    task_taxonomy: tuple[str, ...]


@dataclass(frozen=True)
class SeedTransformation:
    transformation_id: str
    source_seed_id: str
    transformation_type: str
    target_taxonomy_node: str
    capability_target: str
    difficulty_movement: str
    lineage: dict[str, object]

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "seed_transformation_v1",
            "transformation_id": self.transformation_id,
            "source_seed_id": self.source_seed_id,
            "transformation_type": self.transformation_type,
            "target_taxonomy_node": self.target_taxonomy_node,
            "capability_target": self.capability_target,
            "difficulty_movement": self.difficulty_movement,
            "lineage": dict(self.lineage),
        }


def foundation_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_contacts_v1",
        domain="contacts_fixture",
        description="Small contact lookup domain for proving local executable samples.",
        task_taxonomy=(
            "single_tool_lookup",
            "verification_failure_fixture",
            "contact_followup",
            "branch_fallback",
        ),
    )


def deterministic_seed_transformations(seed: DomainSeed) -> list[SeedTransformation]:
    lineage = _local_seed_transformation_lineage()
    return [
        SeedTransformation(
            transformation_id="transform_seed_contacts_followup",
            source_seed_id=seed.seed_id,
            transformation_type="taxonomy_expansion",
            target_taxonomy_node="contact_followup",
            capability_target="stateful_contact_followup",
            difficulty_movement="easy_to_medium",
            lineage=lineage,
        ),
        SeedTransformation(
            transformation_id="transform_seed_contacts_unsupported_network",
            source_seed_id=seed.seed_id,
            transformation_type="taxonomy_expansion",
            target_taxonomy_node="unsupported_network_research",
            capability_target="network_contact_research",
            difficulty_movement="medium_to_hard",
            lineage=lineage,
        ),
    ]


def _local_seed_transformation_lineage() -> dict[str, object]:
    return {
        "role": "scripted_seed_transformation",
        "role_version": "role_scripted_seed_transformation_v1",
        "output_type": "seed_transformation",
        "owner_module": "synthesis.seeds",
        "retry_policy": "none",
        "provider_host": "local",
        "model": "scripted",
        "config_hash": "seed-transform-local-v1",
        "configured": False,
    }
