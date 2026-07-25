from __future__ import annotations

import re
from dataclasses import replace

from synthesis.environments import ContactEnvironment
from synthesis.execution import scripted_solution_policy
from synthesis.mutation_admission import (
    SEMANTIC_VERDICT_VERSION,
    DeterministicSemanticMutationJudge,
    MutationActionPolicy,
    MutationArgumentPolicy,
    SemanticJudgeRequest,
    canonical_hash,
    normalized_instruction,
    policy_hash,
)
from synthesis.tasks import CandidateTask


def prepare_contact_candidate(candidate: CandidateTask) -> CandidateTask:
    if candidate.constraints.get("task_type") != "contact_followup":
        return candidate
    return propose_contact_followup_authorization(candidate)


def contact_followup_mutation_policies(
    environment: ContactEnvironment | None = None,
) -> tuple[MutationActionPolicy, ...]:
    contact_names = (
        environment.contact_names()
        if environment is not None
        else ContactEnvironment.fixture_contact_names()
    )
    bindings = tuple(
        (
            canonical_hash({"name": name}),
            canonical_hash(name),
        )
        for name in contact_names
    )
    return (
        MutationActionPolicy(
            schema_version="contact_followup_mutation_policy_v1",
            domain_id="contacts_fixture",
            task_type="contact_followup",
            action_type="contact_followup_record",
            tool_name="record_contact_followup",
            arguments=(
                MutationArgumentPolicy(
                    name="name",
                    requester_controlled=True,
                    allowed_origins=("instruction", "tool_observation"),
                    observation_tool="lookup_contact_email",
                    observation_field="name",
                    observation_bindings=bindings,
                    binding_argument_names=("name",),
                ),
                MutationArgumentPolicy(
                    name="note",
                    requester_controlled=True,
                    allowed_origins=("instruction",),
                ),
            ),
            operational_defaults=(
                ("created_at", "contact_followup_created_at_default_v1"),
            ),
            deterministic_derivations=(
                (
                    "followup_count",
                    "contact_followup_count_from_persisted_state_v1",
                ),
            ),
        ),
    )


def build_contact_followup_semantic_mutation_judge(
    environment: ContactEnvironment,
) -> DeterministicSemanticMutationJudge:
    contact_emails = {
        name: str(environment.lookup_email(name)["email"])
        for name in environment.contact_names()
    }
    return DeterministicSemanticMutationJudge(
        evaluate=lambda request: _contact_followup_semantic_mutation_verdict(
            request,
            contact_emails,
        ),
        model="deterministic_contact_followup_judge_v1",
    )


def _contact_followup_semantic_mutation_verdict(
    request: SemanticJudgeRequest,
    contact_emails: dict[str, str],
) -> dict[str, object]:
    instruction = request.instruction.lower()
    action_reference = request.evidence_references["action"]
    action_reason = "action_authorized"
    action_outcome = "supported"
    if "ignore previous" in instruction or "ignore all previous" in instruction:
        action_reason = "instruction_prompt_injection"
        action_outcome = "unsupported"
    elif re.search(
        r"\b(?:do not|don't|without)\b[^.]{0,80}\b(?:record|follow.?up)\b",
        instruction,
    ):
        action_reason = "action_negated"
        action_outcome = "unsupported"
    elif any(
        phrase in instruction
        for phrase in ("if appropriate", "if needed", "maybe record", "consider recording")
    ):
        action_reason = "conditional_authorization_ambiguous"
        action_outcome = "uncertain"
    elif not {"record", "follow"}.issubset(
        _semantic_tokens(request.action_evidence_text)
    ):
        action_reason = "action_not_authorized"
        action_outcome = "unsupported"

    action_findings = [
        {
            "action_type": request.action_type,
            "outcome": action_outcome,
            "reason_code": action_reason,
            "evidence_references": [action_reference],
        }
    ]
    argument_findings: list[dict[str, object]] = []
    outcomes = [action_outcome]
    reason_codes = [action_reason]
    all_references = [action_reference]
    for name, origin in request.argument_origins.items():
        reference = request.evidence_references[name]
        if origin == "tool_observation":
            selected_name = request.argument_values.get(name)
            evidence = request.argument_evidence.get(name)
            source_arguments = (
                evidence.get("source_arguments")
                if isinstance(evidence, dict)
                else None
            )
            if (
                isinstance(selected_name, str)
                and selected_name in contact_emails
                and isinstance(source_arguments, dict)
                and source_arguments.get("name") == selected_name
            ):
                outcome = "supported"
                reason = "observation_reference_supported"
            else:
                outcome = "unsupported"
                reason = "provenance_mismatch"
        elif origin == "instruction":
            value = str(request.argument_values.get(name, ""))
            evidence_text = str(request.argument_evidence.get(name, ""))
            if value.lower() in instruction:
                outcome = "supported"
                reason = "argument_literal_supported"
            else:
                selected_name = request.argument_values.get("name")
                expected_email = (
                    contact_emails.get(selected_name)
                    if isinstance(selected_name, str)
                    else None
                )
                expected_note = (
                    f"Send follow-up email to {expected_email}."
                    if expected_email is not None
                    else None
                )
                if (
                    name == "note"
                    and value == expected_note
                    and {"follow", "up"}.issubset(
                        _semantic_tokens(evidence_text)
                    )
                ):
                    outcome = "supported"
                    reason = "argument_semantic_supported"
                else:
                    outcome = "unsupported"
                    reason = "argument_not_supported"
        else:
            outcome = "unsupported"
            reason = "provenance_mismatch"
        argument_findings.append(
            {
                "argument": name,
                "outcome": outcome,
                "reason_code": reason,
                "evidence_references": [reference],
            }
        )
        outcomes.append(outcome)
        reason_codes.append(reason)
        all_references.append(reference)

    verdict = (
        "unsupported"
        if "unsupported" in outcomes
        else "uncertain"
        if "uncertain" in outcomes
        else "supported"
    )
    return {
        "schema_version": SEMANTIC_VERDICT_VERSION,
        "verdict": verdict,
        "action_findings": action_findings,
        "argument_findings": argument_findings,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "evidence_references": list(dict.fromkeys(all_references)),
        "input_hash": request.input_hash(),
    }


def _semantic_tokens(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "for",
        "find",
        "of",
        "recorded",
        "send",
        "sent",
        "should",
        "the",
        "to",
    }
    return set(re.findall(r"[a-z0-9]+", value.lower())) - stopwords


def propose_contact_followup_authorization(candidate: CandidateTask) -> CandidateTask:
    policy = scripted_solution_policy(candidate)
    instruction = normalized_instruction(candidate.instruction)
    source_index, source_step = _policy_step(policy, "lookup_contact_email")
    mutation_index, mutation_step = _policy_step(
        policy,
        "record_contact_followup",
    )
    action_evidence = _instruction_regex_evidence(
        instruction,
        r"\b(?:record|add|save)\b[^.]{0,200}\bfollow[- ]?up\b[^.]*",
        reference_id="instruction.action",
    )
    name_evidence = _instruction_regex_evidence(
        instruction,
        (
            r"(?i:\b(?:find|look\s+up|lookup)\s+(?:the\s+contact\s+)?)"
            r"(?P<name>[A-Z][A-Za-z-]*(?:\s+[A-Z][A-Za-z-]*)+)"
        ),
        reference_id="instruction.selected_contact",
        group="name",
    )
    note = mutation_step.arguments.get("note")
    note_evidence = (
        _instruction_literal_evidence(
            instruction,
            note,
            reference_id="instruction.note",
        )
        if isinstance(note, str) and note in instruction
        else _instruction_regex_evidence(
            instruction,
            r"\bfollow[- ]?up\b[^.]*",
            reference_id="instruction.note",
        )
    )
    record: dict[str, object] = {
        "schema_version": "mutation_authorization_record_v1",
        "instruction_hash": canonical_hash(instruction),
        "policy_hash": policy_hash(policy),
        "actions": [
            {
                "action_ref": f"policy.steps.{mutation_index}",
                "action_type": "contact_followup_record",
                "instruction_evidence": action_evidence,
                "arguments": [
                    {
                        "name": "name",
                        "origin": "tool_observation",
                        "evidence": {
                            "reference_id": "observation.selected_contact",
                            "kind": "tool_observation",
                            "source_action_ref": f"policy.steps.{source_index}",
                            "source_field": "name",
                            "source_arguments_hash": canonical_hash(
                                source_step.arguments
                            ),
                            "value_hash": canonical_hash(
                                mutation_step.arguments.get("name")
                            ),
                            "binding_instruction_evidence": name_evidence,
                        },
                    },
                    {
                        "name": "note",
                        "origin": "instruction",
                        "support": "semantic",
                        "evidence": note_evidence,
                    },
                ],
            }
        ],
    }
    return replace(candidate, mutation_authorization=record)


def _policy_step(policy, tool_name: str):
    for index, step in enumerate(policy.steps):
        if step.tool_name == tool_name:
            return index, step
    raise ValueError(f"contact follow-up policy requires {tool_name}")


def _instruction_regex_evidence(
    instruction: str,
    pattern: str,
    *,
    reference_id: str,
    group: str | int = 0,
) -> dict[str, object]:
    match = re.search(pattern, instruction)
    if match is None:
        return _instruction_evidence(
            instruction,
            0,
            min(1, len(instruction)),
            reference_id=reference_id,
        )
    start, end = match.span(group)
    return _instruction_evidence(
        instruction,
        start,
        end,
        reference_id=reference_id,
    )


def _instruction_literal_evidence(
    instruction: str,
    text: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    start = instruction.index(text)
    return _instruction_evidence(
        instruction,
        start,
        start + len(text),
        reference_id=reference_id,
    )


def _instruction_evidence(
    instruction: str,
    start: int,
    end: int,
    *,
    reference_id: str,
) -> dict[str, object]:
    text = instruction[start:end]
    return {
        "reference_id": reference_id,
        "kind": "instruction_span",
        "start": start,
        "end": end,
        "evidence_hash": canonical_hash(text),
    }
