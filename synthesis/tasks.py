from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synthesis.llm import LLMProviderError
from synthesis.roles import RoleRegistry, TASK_GENERATION_ROLE, default_role_registry
from synthesis.seeds import DomainSeed


@dataclass(frozen=True)
class CandidateTask:
    candidate_id: str
    instruction: str
    constraints: dict[str, object]
    difficulty: dict[str, object]
    tool_name: str
    arguments: dict[str, object]
    expected_answer: str
    seed_ids: tuple[str, ...]
    generation_lineage: dict[str, object] | None = None
    expected_state: dict[str, object] | None = None
    branch_plan: dict[str, object] | None = None

    def export(self) -> dict[str, object]:
        record: dict[str, object] = {
            "candidate_id": self.candidate_id,
            "instruction": self.instruction,
            "constraints": self.constraints,
            "difficulty": self.difficulty,
        }
        if self.branch_plan is not None:
            record["branch_plan"] = self.branch_plan
        return record


def generate_foundation_candidates(
    seed: DomainSeed,
    *,
    include_branching: bool = False,
) -> list[CandidateTask]:
    common_difficulty = {
        "level": "easy",
        "tool_count": 1,
        "constraint_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }
    candidates = [
        CandidateTask(
            candidate_id="candidate_contacts_alice",
            instruction="Find Alice Zhang's email address using the contact database.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=common_difficulty,
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_contacts_ben_bad_expectation",
            instruction="Find Ben Carter's email address using the contact database.",
            constraints={"must_use_tool": "lookup_contact_email"},
            difficulty=common_difficulty,
            tool_name="lookup_contact_email",
            arguments={"name": "Ben Carter"},
            expected_answer="ben@example.test",
            seed_ids=(seed.seed_id,),
        ),
        CandidateTask(
            candidate_id="candidate_contacts_alice_followup",
            instruction=(
                "Find Alice Zhang's email address and record that a follow-up "
                "email should be sent."
            ),
            constraints={
                "task_type": "contact_followup",
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
            },
            difficulty={
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            tool_name="lookup_contact_email",
            arguments={"name": "Alice Zhang"},
            expected_answer="alice.zhang@example.test",
            seed_ids=(seed.seed_id,),
            expected_state={
                "contact_followup": {
                    "name": "Alice Zhang",
                    "note": "Send follow-up email to alice.zhang@example.test.",
                }
            },
        ),
    ]
    if include_branching:
        candidates.append(_branching_contact_candidate(seed))
    return order_candidates_by_curriculum(candidates)


def generate_llm_backed_candidates(
    seed: DomainSeed,
    client: Any,
    *,
    role_registry: RoleRegistry | None = None,
) -> list[CandidateTask]:
    registry = role_registry or default_role_registry()
    result = registry.invoke_json(
        TASK_GENERATION_ROLE,
        client,
        _candidate_generation_prompt(seed),
    )
    raw_candidates = result.content.get("candidates")
    if not isinstance(raw_candidates, list):
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class="TypeError",
            retryable=False,
            retry_count=_lineage_retry_count(result.lineage),
            lineage=result.lineage,
        )

    candidates: list[CandidateTask] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise LLMProviderError(
                cause="llm_response_schema_error",
                error_class="TypeError",
                retryable=False,
                retry_count=_lineage_retry_count(result.lineage),
                lineage=result.lineage,
            )
        candidates.append(_candidate_from_mapping(seed, raw_candidate, result.lineage))
    return candidates


def candidate_from_mapping(
    raw: dict[str, Any],
    *,
    seed_ids: tuple[str, ...],
    generation_lineage: dict[str, object] | None = None,
) -> CandidateTask:
    difficulty = _normalize_difficulty(raw["difficulty"])
    constraints = _normalize_constraints(raw["constraints"])
    arguments = raw["arguments"]
    if not isinstance(arguments, dict):
        raise TypeError("candidate arguments must be an object")
    expected_state = raw.get("expected_state")
    if expected_state is not None and not isinstance(expected_state, dict):
        raise TypeError("candidate expected_state must be an object")
    branch_plan = raw.get("branch_plan")
    if branch_plan is not None and not isinstance(branch_plan, dict):
        raise TypeError("candidate branch_plan must be an object")

    return CandidateTask(
        candidate_id=str(raw["candidate_id"]),
        instruction=str(raw["instruction"]),
        constraints=constraints,
        difficulty=difficulty,
        tool_name=_normalize_tool_name(str(raw["tool_name"])),
        arguments=arguments,
        expected_answer=str(raw["expected_answer"]),
        seed_ids=seed_ids,
        generation_lineage=dict(generation_lineage) if generation_lineage else None,
        expected_state=expected_state,
        branch_plan=branch_plan,
    )


def _branching_contact_candidate(seed: DomainSeed) -> CandidateTask:
    return CandidateTask(
        candidate_id="candidate_contacts_alice_branch_fallback",
        instruction=(
            "Find Alice Zhang's email address. If an abbreviated lookup fails, "
            "fall back to the full contact name."
        ),
        constraints={
            "task_type": "contact_branch_fallback",
            "required_tools": ["lookup_contact_email"],
            "expected_branch": "fallback_full_name",
        },
        difficulty={
            "level": "medium",
            "tool_count": 1,
            "constraint_count": 2,
            "state_changes": 0,
            "ambiguity": "recoverable_short_name",
            "recovery_paths": 1,
            "branch_depth": 2,
            "fallback_count": 1,
        },
        tool_name="lookup_contact_email",
        arguments={"name": "Alice"},
        expected_answer="alice.zhang@example.test",
        seed_ids=(seed.seed_id,),
        branch_plan={
            "schema_version": "branch_plan_v1",
            "plan_id": "branch_plan_candidate_contacts_alice_fallback",
            "max_depth": 2,
            "branches": [
                {
                    "branch_id": "direct_short_name",
                    "node_type": "attempt",
                    "parent_id": None,
                    "condition": "Try the abbreviated name first.",
                    "steps": [
                        {
                            "tool_name": "lookup_contact_email",
                            "arguments": {"name": "Alice"},
                        }
                    ],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "fallback_on_failure",
                },
                {
                    "branch_id": "fallback_full_name",
                    "node_type": "fallback",
                    "parent_id": "direct_short_name",
                    "condition": "Use the full name after the abbreviated lookup fails.",
                    "steps": [
                        {
                            "tool_name": "lookup_contact_email",
                            "arguments": {"name": "Alice Zhang"},
                        }
                    ],
                    "final_response_template": "{name}'s email is {email}.",
                    "terminal_outcome": "accept_on_success",
                },
            ],
        },
    )


def _candidate_generation_prompt(seed: DomainSeed) -> str:
    taxonomy = ", ".join(seed.task_taxonomy)
    return (
        "Generate candidate Agent data synthesis tasks for a small executable domain.\n"
        f"Domain: {seed.domain}\n"
        f"Description: {seed.description}\n"
        f"Task taxonomy: {taxonomy}\n"
        "Available tools: lookup_contact_email(name: string) -> contact email.\n"
        "Available contacts and expected emails: "
        "Alice Zhang -> alice.zhang@example.test; "
        "Ben Carter -> ben.carter@example.test.\n"
        "Return JSON with a candidates array. Each candidate must include "
        "candidate_id, instruction, constraints, difficulty, tool_name, "
        "arguments, and expected_answer. difficulty must be an object with "
        "level, tool_count, constraint_count, state_changes, ambiguity, "
        "and recovery_paths. "
        "constraints and arguments must be JSON objects. tool_name must be "
        "lookup_contact_email. arguments.name must be one of the full contact "
        "names above. expected_answer must be the exact matching email above."
    )


def _candidate_from_mapping(
    seed: DomainSeed,
    raw: dict[str, Any],
    generation_lineage: dict[str, object],
) -> CandidateTask:
    try:
        return candidate_from_mapping(
            raw,
            seed_ids=(seed.seed_id,),
            generation_lineage=generation_lineage,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            cause="llm_response_schema_error",
            error_class=type(exc).__name__,
            retryable=False,
            retry_count=_lineage_retry_count(generation_lineage),
            lineage=generation_lineage,
        ) from exc


def _normalize_difficulty(raw_difficulty: Any) -> dict[str, object]:
    if isinstance(raw_difficulty, dict):
        difficulty = dict(raw_difficulty)
        difficulty.setdefault("level", "unspecified")
        difficulty.setdefault("tool_count", 1)
        difficulty.setdefault("constraint_count", 0)
        difficulty.setdefault("state_changes", 0)
        difficulty.setdefault("ambiguity", "unspecified")
        difficulty.setdefault("recovery_paths", 0)
        return difficulty
    if isinstance(raw_difficulty, str):
        return {
            "level": raw_difficulty,
            "tool_count": 1,
            "constraint_count": 0,
            "state_changes": 0,
            "ambiguity": "unspecified",
            "recovery_paths": 0,
        }
    raise ValueError("candidate difficulty must be an object")


def order_candidates_by_curriculum(candidates: list[CandidateTask]) -> list[CandidateTask]:
    return sorted(candidates, key=_curriculum_sort_key)


def _curriculum_sort_key(candidate: CandidateTask) -> tuple[int, int, int, int, int, str]:
    difficulty = candidate.difficulty
    level_rank = {"easy": 0, "medium": 1, "hard": 2}.get(str(difficulty.get("level")), 99)
    return (
        level_rank,
        _int_difficulty(difficulty.get("tool_count")),
        _int_difficulty(difficulty.get("constraint_count")),
        _int_difficulty(difficulty.get("state_changes")),
        _int_difficulty(difficulty.get("recovery_paths")),
        candidate.candidate_id,
    )


def _int_difficulty(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _normalize_constraints(raw_constraints: Any) -> dict[str, object]:
    if isinstance(raw_constraints, dict):
        return raw_constraints
    if isinstance(raw_constraints, str):
        return {"description": raw_constraints}
    raise ValueError("candidate constraints must be an object")


def _normalize_tool_name(raw_tool_name: str) -> str:
    aliases = {
        "lookup_contact": "lookup_contact_email",
        "lookup_email": "lookup_contact_email",
        "contact_lookup": "lookup_contact_email",
    }
    return aliases.get(raw_tool_name, raw_tool_name)


def _lineage_retry_count(lineage: dict[str, object]) -> int:
    retry_count = lineage.get("retry_count", 0)
    if isinstance(retry_count, int) and not isinstance(retry_count, bool):
        return retry_count
    return 0
