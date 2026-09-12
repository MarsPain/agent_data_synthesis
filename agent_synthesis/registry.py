"""Explicit registration for the two adapter families used by the core."""

from __future__ import annotations

from collections.abc import Sequence

from agent_synthesis.domain import DomainAdapter
from agent_synthesis.model import JsonModelAdapter


class AdapterRegistry:
    """Resolve registered Domain and model adapters by their stable identifiers."""

    def __init__(
        self,
        *,
        domains: Sequence[DomainAdapter],
        models: Sequence[JsonModelAdapter],
    ) -> None:
        self._domains = _indexed_adapters(
            domains,
            "domain_id",
            "Domain",
            required_members=("domain_version", "open_run"),
        )
        self._models = _indexed_adapters(
            models,
            "model_id",
            "model",
            required_members=("model_version", "provider_id", "complete"),
        )

    def domain(self, domain_id: str) -> DomainAdapter:
        try:
            return self._domains[domain_id]
        except KeyError:
            raise KeyError(f"unregistered Domain adapter: {domain_id}") from None

    def model(self, model_id: str) -> JsonModelAdapter:
        try:
            return self._models[model_id]
        except KeyError:
            raise KeyError(f"unregistered model adapter: {model_id}") from None


def _indexed_adapters[T](
    adapters: Sequence[T],
    identifier_name: str,
    adapter_name: str,
    *,
    required_members: tuple[str, ...],
) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for adapter in adapters:
        identifier = getattr(adapter, identifier_name, None)
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{adapter_name} adapter has an invalid {identifier_name}")
        if identifier in indexed:
            raise ValueError(f"{adapter_name} adapter is registered twice: {identifier}")
        for member_name in required_members:
            member = getattr(adapter, member_name, None)
            if member_name.endswith(("version", "_id")):
                valid = isinstance(member, str) and bool(member)
            else:
                valid = callable(member)
            if not valid:
                raise ValueError(
                    f"{adapter_name} adapter {identifier} lacks a valid {member_name}"
                )
        indexed[identifier] = adapter
    return indexed
