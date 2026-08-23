"""Canonical evidence bindings emitted by the Contacts Domain run.

The legacy Contacts artifacts continue to use their historical projections.
This module is the current lifecycle boundary: accepted and rejected attempts
are bound to the exact Contacts Pack, plan, runtime, task contract, verifier,
mutation evidence, and episode that produced them.
"""

from __future__ import annotations

from collections.abc import Mapping

from synthesis.domain_pack import (
    DomainCapabilityReference,
    DomainPlan,
    canonical_domain_pack_hash,
)
from synthesis.mutation_admission import canonical_hash
from synthesis.tasks import CandidateTask


CONTACTS_EVIDENCE_BINDING_SCHEMA_VERSION = "contacts_evidence_binding_v1"


def canonical_capability_references(
    references: tuple[DomainCapabilityReference, ...],
) -> list[dict[str, object]]:
    return [
        reference.to_record()
        for reference in sorted(
            references,
            key=lambda reference: (
                reference.domain_pack_id,
                reference.capability_key,
                reference.capability_contract_version,
            ),
        )
    ]


def contacts_task_contract_hash(candidate: CandidateTask) -> str:
    contract = candidate.contract()
    return canonical_domain_pack_hash(
        {
            "candidate_id": contract.intent.candidate_id,
            "instruction": contract.intent.instruction,
            "domain_id": contract.intent.domain_id,
            "task_type": contract.intent.task_type,
            "difficulty": dict(contract.intent.difficulty),
            "required_capabilities": list(contract.intent.required_capabilities),
            "capability_references": canonical_capability_references(
                contract.intent.capability_references
            ),
            "required_tools": list(contract.policy_hint.required_tools),
            "primary_tool": contract.policy_hint.primary_tool,
            "primary_arguments": dict(contract.policy_hint.primary_arguments),
            "branch_plan": (
                dict(contract.policy_hint.branch_plan)
                if contract.policy_hint.branch_plan is not None
                else None
            ),
            "expected_outcome": {
                "final_answer_contains": contract.expected_outcome.final_answer_contains,
            },
            "expected_state": [
                {
                    "check_type": state_check.check_type,
                    "expected": dict(state_check.expected),
                }
                for state_check in contract.expected_state
            ],
            "mutation_policy": (
                dict(contract.mutation_authorization)
                if contract.mutation_authorization is not None
                else None
            ),
        }
    )


def contacts_task_capability_references(
    plan: DomainPlan,
    candidate: CandidateTask,
) -> tuple[DomainCapabilityReference, ...]:
    """Project one task type onto the exact capabilities selected by its plan."""

    contract = candidate.contract()
    projection_by_task_type = {
        projection.task_type_key: projection
        for projection in plan.task_capability_projections
    }
    projection_key = {
        "contact_lookup": "contact_lookup",
        "contact_followup": "contact_followup",
        "contact_branch_fallback": "contact_lookup_recovery",
        "contact_lookup_recovery": "contact_lookup_recovery",
    }.get(contract.intent.task_type)
    projection = projection_by_task_type.get(projection_key)
    if projection is None:
        return tuple(contract.intent.capability_references)
    references = set(projection.capability_references)
    recovery_paths = contract.intent.difficulty.get("recovery_paths")
    if (
        isinstance(recovery_paths, int)
        and not isinstance(recovery_paths, bool)
        and recovery_paths > 0
    ) or contract.policy_hint.branch_plan is not None:
        recovery_reference = next(
            (
                reference
                for reference in plan.capability_references
                if reference.capability_key == "contact_lookup_recovery"
            ),
            None,
        )
        if recovery_reference is not None:
            references.add(recovery_reference)
    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.domain_pack_id,
                reference.capability_key,
                reference.capability_contract_version,
            ),
        )
    )


def contacts_recovery_evidence(
    candidate: CandidateTask,
    sample: Mapping[str, object],
) -> dict[str, object]:
    """Verify the declared failed lookup and grounded fallback as a projection."""

    contract = candidate.contract()
    branch_plan = contract.policy_hint.branch_plan
    if branch_plan is None:
        return {"declared": False, "verified": False, "reason": "not_declared"}
    lineage = sample.get("lineage")
    branching = lineage.get("branching") if isinstance(lineage, Mapping) else None
    outcomes = branching.get("branch_outcomes") if isinstance(branching, Mapping) else None
    if not isinstance(outcomes, list) or not outcomes:
        return {
            "declared": True,
            "verified": False,
            "reason": "branch_execution_evidence_missing",
        }
    failed = next(
        (
            outcome
            for outcome in outcomes
            if isinstance(outcome, Mapping) and outcome.get("selected") is False
        ),
        None,
    )
    selected = next(
        (
            outcome
            for outcome in outcomes
            if isinstance(outcome, Mapping) and outcome.get("selected") is True
        ),
        None,
    )
    if not isinstance(failed, Mapping) or not isinstance(selected, Mapping):
        return {
            "declared": True,
            "verified": False,
            "reason": "initial_failure_or_fallback_missing",
        }
    failure_cause = failed.get("failure_cause")
    failed_trajectory = failed.get("trajectory")
    selected_trajectory = selected.get("trajectory")
    if failure_cause not in {"tool_runtime_error", "tool_schema_error"}:
        return {
            "declared": True,
            "verified": False,
            "reason": "initial_failure_not_admissible",
        }
    if not isinstance(failed_trajectory, list) or not isinstance(
        selected_trajectory,
        list,
    ):
        return {
            "declared": True,
            "verified": False,
            "reason": "trajectory_evidence_missing",
        }
    failed_action = _first_action(failed_trajectory)
    selected_action = _first_action(selected_trajectory)
    selected_observation = _last_observation(selected_trajectory)
    branches = branch_plan.get("branches")
    branch_by_id = {
        branch.get("branch_id"): branch
        for branch in branches
        if isinstance(branch, Mapping) and isinstance(branch.get("branch_id"), str)
    } if isinstance(branches, list) else {}
    selected_branch = branch_by_id.get(selected.get("branch_id"))
    transition_ok = (
        isinstance(failed.get("branch_id"), str)
        and isinstance(selected.get("branch_id"), str)
        and failed.get("branch_id") != selected.get("branch_id")
        and isinstance(selected_branch, Mapping)
        and selected_branch.get("parent_id") == failed.get("branch_id")
    )
    expected_answer = contract.expected_outcome.final_answer_contains
    final_response = sample.get("final_response")
    grounded_result = (
        isinstance(final_response, str)
        and expected_answer in final_response
        and isinstance(selected_observation, Mapping)
        and isinstance(selected_observation.get("email"), str)
        and expected_answer in str(selected_observation.get("email"))
    )
    verified = (
        failed_action is not None
        and selected_action is not None
        and failed_action != selected_action
        and transition_ok
        and grounded_result
    )
    return {
        "declared": True,
        "verified": verified,
        "reason": "verified" if verified else "recovery_transition_or_grounding_mismatch",
        "initial_failure_branch_id": failed.get("branch_id"),
        "fallback_branch_id": selected.get("branch_id"),
        "initial_failure_cause": failure_cause,
        "initial_action_hash": canonical_domain_pack_hash(failed_action or {}),
        "fallback_action_hash": canonical_domain_pack_hash(selected_action or {}),
        "fallback_observation_hash": canonical_domain_pack_hash(
            selected_observation or {}
        ),
    }


def build_contacts_evidence_binding(
    *,
    plan: DomainPlan,
    candidate: CandidateTask,
    verifier_id: str,
    verifier_version: str,
    sample: Mapping[str, object],
    episode: Mapping[str, object] | None,
    episode_hash: str | None,
    assignment: Mapping[str, object] | None,
    candidate_scope: Mapping[str, object] | None,
) -> dict[str, object]:
    contract = candidate.contract()
    task_capabilities = canonical_capability_references(
        contacts_task_capability_references(plan, candidate)
    )
    mutation = sample.get("mutation_admission")
    verification = sample.get("verification")
    expected_state = [
        {
            "check_type": state_check.check_type,
            "expected": dict(state_check.expected),
        }
        for state_check in contract.expected_state
    ]
    assignment_record = dict(assignment) if assignment is not None else None
    assignment_capability_references = _assignment_capability_references(
        assignment_record
    )
    verification_record = dict(verification) if isinstance(verification, Mapping) else {}
    core_episode_hash = canonical_hash(episode) if episode is not None else None
    return {
        "schema_version": CONTACTS_EVIDENCE_BINDING_SCHEMA_VERSION,
        "domain_pack_reference": plan.domain_pack_reference.to_record(),
        "plan": {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "plan_record": plan.to_record(),
        },
        "component_contracts": [
            contract.to_record() for contract in plan.component_contracts
        ],
        "source": plan.admitted_source.to_record(),
        "candidate_scope": (
            dict(candidate_scope) if candidate_scope is not None else None
        ),
        "runtime_contract": plan.runtime_contract.to_record(),
        "capability_references": canonical_capability_references(
            tuple(plan.capability_references)
        ),
        "task_capability_references": task_capabilities,
        "assignment": assignment_record,
        "assignment_capability_references": assignment_capability_references,
        "task_contract": {
            "candidate_id": contract.intent.candidate_id,
            "task_type": contract.intent.task_type,
            "contract_hash": contacts_task_contract_hash(candidate),
        },
        "grounding": {
            "primary_arguments_hash": canonical_domain_pack_hash(
                dict(contract.policy_hint.primary_arguments)
            ),
            "expected_state_hash": canonical_domain_pack_hash(expected_state),
            "expected_answer_hash": canonical_domain_pack_hash(
                contract.expected_outcome.final_answer_contains
            ),
        },
        "final_state": {
            "expected_state_hash": canonical_domain_pack_hash(expected_state),
            "verification_hash": canonical_hash(verification_record),
            "verification_passed": verification_record.get("passed") is True,
        },
        "mutation": (
            {
                "evidence_hash": canonical_hash(mutation),
            }
            if mutation is not None
            else None
        ),
        "recovery": contacts_recovery_evidence(candidate, sample),
        "episode": (
            {
                "episode_id": episode.get("episode_id"),
                "episode_hash": episode_hash,
                "core_episode_hash": core_episode_hash,
            }
            if episode is not None
            else None
        ),
        "verifier": {"id": verifier_id, "version": verifier_version},
    }


def _assignment_capability_references(
    assignment: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if assignment is None:
        return []
    catalog = assignment.get("catalog")
    references = catalog.get("capability_references") if isinstance(catalog, Mapping) else None
    if not isinstance(references, list):
        return []
    return [dict(item) for item in references if isinstance(item, Mapping)]


def _first_action(trajectory: list[object]) -> Mapping[str, object] | None:
    return next(
        (
            event
            for event in trajectory
            if isinstance(event, Mapping) and event.get("type") == "action"
        ),
        None,
    )


def _last_observation(trajectory: list[object]) -> Mapping[str, object] | None:
    observations = [
        event.get("observation")
        for event in trajectory
        if isinstance(event, Mapping) and event.get("type") == "observation"
    ]
    value = observations[-1] if observations else None
    return value if isinstance(value, Mapping) else None
