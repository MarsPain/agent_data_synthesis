from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    def export(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "instruction": self.instruction,
            "constraints": self.constraints,
            "difficulty": self.difficulty,
        }


def generate_foundation_candidates(seed: DomainSeed) -> list[CandidateTask]:
    common_difficulty = {
        "level": "easy",
        "tool_count": 1,
        "state_changes": 0,
        "ambiguity": "none",
        "recovery_paths": 0,
    }
    return [
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
    ]


def generate_llm_backed_candidates(seed: DomainSeed, client: Any) -> list[CandidateTask]:
    result = client.generate_json(_candidate_generation_prompt(seed), role="task_generation")
    raw_candidates = result.content.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("LLM candidate response must contain a candidates list")

    candidates: list[CandidateTask] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise ValueError("Each LLM candidate must be a JSON object")
        candidates.append(_candidate_from_mapping(seed, raw_candidate))
    return candidates


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
        "level, tool_count, state_changes, ambiguity, and recovery_paths. "
        "constraints and arguments must be JSON objects. tool_name must be "
        "lookup_contact_email. arguments.name must be one of the full contact "
        "names above. expected_answer must be the exact matching email above."
    )


def _candidate_from_mapping(seed: DomainSeed, raw: dict[str, Any]) -> CandidateTask:
    difficulty = _normalize_difficulty(raw["difficulty"])
    constraints = _normalize_constraints(raw["constraints"])
    arguments = raw["arguments"]
    if not isinstance(arguments, dict):
        raise ValueError("candidate arguments must be an object")

    return CandidateTask(
        candidate_id=str(raw["candidate_id"]),
        instruction=str(raw["instruction"]),
        constraints=constraints,
        difficulty=difficulty,
        tool_name=_normalize_tool_name(str(raw["tool_name"])),
        arguments=arguments,
        expected_answer=str(raw["expected_answer"]),
        seed_ids=(seed.seed_id,),
    )


def _normalize_difficulty(raw_difficulty: Any) -> dict[str, object]:
    if isinstance(raw_difficulty, dict):
        return raw_difficulty
    if isinstance(raw_difficulty, str):
        return {
            "level": raw_difficulty,
            "tool_count": 1,
            "state_changes": 0,
            "ambiguity": "unspecified",
            "recovery_paths": 0,
        }
    raise ValueError("candidate difficulty must be an object")


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
