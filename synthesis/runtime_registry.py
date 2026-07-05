from __future__ import annotations

from awm_runtime.runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
from synthesis.seeds import DomainSeed, foundation_seed


def registered_runtime_ids(registry: RuntimeRegistry | None = None) -> tuple[str, ...]:
    return _registry(registry).registered_runtime_ids()


def runtime_descriptor(
    runtime_id: str,
    registry: RuntimeRegistry | None = None,
) -> RuntimeCapabilityDescriptor:
    return _registry(registry).descriptor(runtime_id)


def runtime_capability_status(
    runtime_id: object,
    capability_name: str,
    registry: RuntimeRegistry | None = None,
) -> str:
    from awm_runtime.runtime import runtime_capability_status as boundary_status

    return boundary_status(runtime_id, capability_name, _registry(registry))


def runtime_registry_with(
    *descriptors: RuntimeCapabilityDescriptor,
    base: RuntimeRegistry | None = None,
) -> RuntimeRegistry:
    registry = _registry(base)
    for descriptor in descriptors:
        registry = registry.register(descriptor)
    return registry


def _registry(registry: RuntimeRegistry | None) -> RuntimeRegistry:
    return DEFAULT_RUNTIME_REGISTRY if registry is None else registry


def _mobile_messages_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_mobile_messages_v1",
        domain="mobile_messages_fixture",
        description="Synthetic phone messages, reminders, and draft replies.",
        task_taxonomy=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
    )


def _workspace_tasks_seed() -> DomainSeed:
    return DomainSeed(
        seed_id="seed_workspace_tasks_v1",
        domain="workspace_tasks_fixture",
        description="Synthetic workspace projects, tasks, documents, and comments.",
        task_taxonomy=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
    )


def _contacts_descriptor() -> RuntimeCapabilityDescriptor:
    seed = foundation_seed()
    return RuntimeCapabilityDescriptor(
        runtime_id="contacts_fixture",
        runtime_version="contacts_fixture_v1",
        domain_id="contacts_fixture",
        supports_rebuild=True,
        supports_checkpoint_restore=True,
        supports_episode_replay=True,
        supports_reward_labels=True,
        supports_local_adapter=True,
        state_changing_tools=("record_contact_followup",),
        task_taxonomy=seed.task_taxonomy,
        reward_preference_groups={
            "__default__": "contact_lookup",
            "record_contact_followup": "contact_followup",
        },
        rebuild_seed=seed,
        descriptor_metadata={"adapter_support": "local_contacts_adapter"},
    )


def _mobile_descriptor() -> RuntimeCapabilityDescriptor:
    seed = _mobile_messages_seed()
    return RuntimeCapabilityDescriptor(
        runtime_id="mobile_messages_fixture",
        runtime_version="mobile_messages_fixture_v1",
        domain_id="mobile_messages_fixture",
        supports_rebuild=True,
        supports_checkpoint_restore=True,
        supports_episode_replay=True,
        supports_reward_labels=True,
        supports_local_adapter=True,
        state_changing_tools=("create_phone_reminder", "draft_message_reply"),
        task_taxonomy=seed.task_taxonomy,
        reward_preference_groups={
            "__default__": "mobile_message_lookup",
            "create_phone_reminder": "mobile_reminder",
            "draft_message_reply": "mobile_draft_reply",
            "search_phone_messages": "mobile_message_lookup",
        },
        rebuild_seed=seed,
        descriptor_metadata={"adapter_support": "local_runtime_adapter"},
    )


def _workspace_descriptor() -> RuntimeCapabilityDescriptor:
    seed = _workspace_tasks_seed()
    return RuntimeCapabilityDescriptor(
        runtime_id="workspace_tasks_fixture",
        runtime_version="workspace_tasks_fixture_v1",
        domain_id="workspace_tasks_fixture",
        supports_rebuild=True,
        supports_checkpoint_restore=True,
        supports_episode_replay=True,
        supports_reward_labels=True,
        supports_local_adapter=True,
        state_changing_tools=("create_workspace_task", "add_workspace_comment"),
        task_taxonomy=seed.task_taxonomy,
        reward_preference_groups={
            "__default__": "workspace_item_lookup",
            "search_workspace_items": "workspace_item_lookup",
            "create_workspace_task": "workspace_task_creation",
            "add_workspace_comment": "workspace_comment_update",
        },
        rebuild_seed=seed,
        descriptor_metadata={"adapter_support": "local_runtime_adapter"},
    )


DEFAULT_RUNTIME_REGISTRY = RuntimeRegistry(
    (
        _contacts_descriptor(),
        _mobile_descriptor(),
        _workspace_descriptor(),
    )
)
