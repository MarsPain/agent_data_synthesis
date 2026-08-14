"""Canonical Workspace evidence bindings.

The compatibility task corpus still uses historical task and capability
strings at ingestion boundaries.  This module is the release-facing binding:
every emitted Workspace evidence record uses the Domain Pack references and
hashes selected by the opened plan.
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


WORKSPACE_EVIDENCE_BINDING_SCHEMA_VERSION = "workspace_evidence_binding_v1"


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


def workspace_task_capability_references(
    candidate: CandidateTask,
) -> tuple[DomainCapabilityReference, ...]:
    return tuple(candidate.capability_references)


def workspace_task_contract_hash(candidate: CandidateTask) -> str:
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


def workspace_recovery_evidence(
    candidate: CandidateTask,
    sample: Mapping[str, object],
) -> dict[str, object]:
    contract = candidate.contract()
    branch_plan = contract.policy_hint.branch_plan
    if branch_plan is None:
        return {
            "declared": False,
            "verified": False,
            "reason": "not_declared",
        }
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
            if isinstance(outcome, Mapping)
            and outcome.get("selected") is False
        ),
        None,
    )
    selected = next(
        (
            outcome
            for outcome in outcomes
            if isinstance(outcome, Mapping)
            and outcome.get("selected") is True
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
    if failed.get("outcome") != "rejected" or selected.get("outcome") != "accepted":
        return {
            "declared": True,
            "verified": False,
            "reason": "branch_outcome_status_mismatch",
        }
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
    failed_branch_id = failed.get("branch_id")
    selected_branch_id = selected.get("branch_id")
    branches = branch_plan.get("branches")
    branch_by_id = {
        branch.get("branch_id"): branch
        for branch in branches
        if isinstance(branch, Mapping) and isinstance(branch.get("branch_id"), str)
    } if isinstance(branches, list) else {}
    selected_branch = branch_by_id.get(selected_branch_id)
    transition_ok = (
        isinstance(failed_branch_id, str)
        and isinstance(selected_branch_id, str)
        and failed_branch_id != selected_branch_id
        and isinstance(selected_branch, Mapping)
        and selected_branch.get("parent_id") == failed_branch_id
    )
    expected_answer = contract.expected_outcome.final_answer_contains
    final_response = sample.get("final_response")
    grounded_result = (
        isinstance(final_response, str)
        and expected_answer in final_response
        and isinstance(selected_observation, Mapping)
        and any(
            isinstance(selected_observation.get(field), str)
            and expected_answer in str(selected_observation.get(field))
            for field in ("item_id", "summary")
        )
    )
    verified = (
        _has_action(failed_trajectory)
        and _has_action(selected_trajectory)
        and failed_action != selected_action
        and transition_ok
        and grounded_result
    )
    return {
        "declared": True,
        "verified": verified,
        "reason": "verified"
        if verified
        else "recovery_transition_or_grounding_mismatch",
        "initial_failure_branch_id": failed.get("branch_id"),
        "fallback_branch_id": selected.get("branch_id"),
        "initial_failure_cause": failure_cause,
        "initial_action_hash": canonical_domain_pack_hash(failed_action),
        "fallback_action_hash": canonical_domain_pack_hash(selected_action),
        "fallback_observation_hash": canonical_domain_pack_hash(
            selected_observation or {}
        ),
    }


def build_workspace_evidence_binding(
    *,
    plan: DomainPlan,
    candidate: CandidateTask,
    verifier_id: str,
    verifier_version: str,
    sample: Mapping[str, object],
    episode: Mapping[str, object] | None,
    episode_hash: str | None,
    assignment: Mapping[str, object] | None,
) -> dict[str, object]:
    contract = candidate.contract()
    task_capabilities = canonical_capability_references(
        contract.intent.capability_references
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
    core_episode_hash = (
        canonical_hash(episode) if episode is not None else None
    )
    binding: dict[str, object] = {
        "schema_version": WORKSPACE_EVIDENCE_BINDING_SCHEMA_VERSION,
        "domain_pack_reference": plan.domain_pack_reference.to_record(),
        "plan": {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "plan_record": plan.to_record(),
        },
        "component_contracts": [
            contract.to_record()
            for contract in plan.component_contracts
        ],
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
            "contract_hash": workspace_task_contract_hash(candidate),
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
                "evidence": dict(mutation)
                if isinstance(mutation, Mapping)
                else None,
            }
            if mutation is not None
            else None
        ),
        "episode": (
            {
                "episode_id": episode.get("episode_id"),
                "episode_hash": episode_hash,
                "core_episode_hash": core_episode_hash,
            }
            if episode is not None
            else None
        ),
        "verifier": {
            "id": verifier_id,
            "version": verifier_version,
        },
        "verification_hash": canonical_domain_pack_hash(verification or {}),
        "recovery": workspace_recovery_evidence(candidate, sample),
    }
    return binding


def _assignment_capability_references(
    assignment: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if assignment is None:
        return []
    catalog = assignment.get("catalog")
    references = catalog.get("capability_references") if isinstance(catalog, Mapping) else None
    if not isinstance(references, list):
        return []
    return [dict(reference) for reference in references if isinstance(reference, Mapping)]


def _first_action(trajectory: list[object]) -> Mapping[str, object] | None:
    return next(
        (
            event
            for event in trajectory
            if isinstance(event, Mapping) and event.get("type") == "action"
        ),
        None,
    )


def _has_action(trajectory: list[object]) -> bool:
    return _first_action(trajectory) is not None


def _last_observation(trajectory: list[object]) -> Mapping[str, object] | None:
    observations = [
        event.get("observation")
        for event in trajectory
        if isinstance(event, Mapping)
        and event.get("type") == "observation"
        and isinstance(event.get("observation"), Mapping)
    ]
    return observations[-1] if observations else None
