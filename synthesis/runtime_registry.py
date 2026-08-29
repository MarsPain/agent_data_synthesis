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


def release_completeness_threshold_record(runtime_id: str | None) -> dict[str, object] | None:
    normalized_runtime_id = "contacts_fixture" if runtime_id in {None, "contacts"} else runtime_id
    threshold = _RELEASE_COMPLETENESS_THRESHOLDS.get(normalized_runtime_id)
    if threshold is None:
        return None
    required_task_types = threshold.get("required_task_types", ())
    required_tool_combinations = threshold.get("required_tool_combinations", ())
    required_capability_keys = threshold.get("required_capability_keys", ())
    minimum_recovery_samples = threshold.get("minimum_recovery_samples", 0)
    task_type_aliases = threshold.get("task_type_aliases", {})
    recovery_task_type_alias = threshold.get("recovery_task_type_alias")
    return {
        "min_accepted_samples": threshold["min_accepted_samples"],
        "max_rejection_rate": threshold["max_rejection_rate"],
        "required_task_types": (
            list(required_task_types)
            if isinstance(required_task_types, (list, tuple))
            else []
        ),
        "required_tool_combinations": (
            list(required_tool_combinations)
            if isinstance(required_tool_combinations, (list, tuple))
            else []
        ),
        "required_capability_keys": (
            list(required_capability_keys)
            if isinstance(required_capability_keys, (list, tuple))
            else []
        ),
        "minimum_recovery_samples": (
            int(minimum_recovery_samples)
            if isinstance(minimum_recovery_samples, (int, float, str))
            else 0
        ),
        "task_type_aliases": (
            {
                str(key): list(value)
                for key, value in task_type_aliases.items()
                if isinstance(key, str) and isinstance(value, (list, tuple))
            }
            if isinstance(task_type_aliases, dict)
            else {}
        ),
        "recovery_task_type_alias": (
            recovery_task_type_alias
            if isinstance(recovery_task_type_alias, str)
            else None
        ),
    }


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


_RELEASE_COMPLETENESS_THRESHOLDS: dict[str, dict[str, object]] = {
    "contacts_fixture": {
        "min_accepted_samples": 5,
        "max_rejection_rate": 0.2,
        "required_task_types": (
            "lookup_contact_email",
            "contact_followup",
            "contact_branch_fallback",
        ),
        "required_tool_combinations": (
            "lookup_contact_email",
            "lookup_contact_email+record_contact_followup",
        ),
    },
    "contacts_release_candidate": {
        "min_accepted_samples": 5,
        "max_rejection_rate": 0.2,
        "required_task_types": (
            "lookup_contact_email",
            "contact_followup",
            "contact_branch_fallback",
        ),
        "required_tool_combinations": (
            "lookup_contact_email",
            "lookup_contact_email+record_contact_followup",
        ),
        "required_capability_keys": (
            "contact_lookup",
            "followup_recording",
            "contact_lookup_recovery",
        ),
        "minimum_recovery_samples": 1,
        "task_type_aliases": {
            "contact_lookup": (
                "lookup_contact_email",
                "contact_branch_fallback",
            ),
            "contact_followup": ("contact_followup",),
            "contact_lookup_recovery": ("contact_branch_fallback",),
        },
        "recovery_task_type_alias": "contact_branch_fallback",
    },
    "mobile_messages_fixture": {
        "min_accepted_samples": 5,
        "max_rejection_rate": 0.2,
        "required_task_types": (
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
        "required_tool_combinations": (
            "search_phone_messages",
            "search_phone_messages+create_phone_reminder",
            "search_phone_messages+draft_message_reply",
        ),
    },
    "workspace_tasks_fixture": {
        "min_accepted_samples": 5,
        "max_rejection_rate": 0.2,
        "required_task_types": (
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
        "required_tool_combinations": (
            "search_workspace_items",
            "search_workspace_items+create_workspace_task",
            "search_workspace_items+add_workspace_comment",
        ),
        "required_capability_keys": (
            "item_search",
            "task_creation",
            "comment_addition",
            "item_search_recovery",
        ),
        "minimum_recovery_samples": 1,
        "task_type_aliases": {
            "workspace_item_search": ("workspace_item_lookup",),
            "workspace_task_creation": ("workspace_task_creation",),
            "workspace_comment_update": ("workspace_comment_update",),
        },
        "recovery_task_type_alias": "workspace_branch_fallback",
    },
}
