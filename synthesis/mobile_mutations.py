from __future__ import annotations

import re
from dataclasses import replace

from synthesis.execution import SolutionPolicy, ToolStep
from synthesis.mobile_environment import MobileMessagesEnvironment
from synthesis.mobile_tasks import (
    MOBILE_MESSAGE_GROUNDING_ARGUMENTS,
    scripted_mobile_solution_policy,
)
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


REMINDER_TASK_TYPES = {
    "mobile_message_to_reminder",
    "mobile_reminder_creation",
}


def mobile_mutation_policies(
    environment: MobileMessagesEnvironment,
) -> tuple[MutationActionPolicy, ...]:
    message_bindings = _message_bindings(environment, "message_id")
    thread_bindings = _message_bindings(environment, "thread_id")
    reminder_policy = MutationActionPolicy(
        schema_version="mobile_reminder_mutation_policy_v1",
        domain_id="mobile_messages_fixture",
        task_type="mobile_message_to_reminder",
        action_type="mobile_reminder_create",
        tool_name="create_phone_reminder",
        arguments=(
            MutationArgumentPolicy(
                name="title",
                requester_controlled=True,
                allowed_origins=("instruction",),
            ),
            MutationArgumentPolicy(
                name="due_at",
                requester_controlled=True,
                allowed_origins=("instruction",),
                required=False,
            ),
            MutationArgumentPolicy(
                name="source_message_id",
                requester_controlled=False,
                allowed_origins=("tool_observation",),
                observation_tool="search_phone_messages",
                observation_field="message_id",
                observation_bindings=message_bindings,
                binding_argument_names=("query", "participant"),
                binding_token_aliases=(
                    ("project", "status"),
                    ("update", "note"),
                ),
            ),
        ),
    )
    draft_policy = MutationActionPolicy(
        schema_version="mobile_draft_reply_mutation_policy_v1",
        domain_id="mobile_messages_fixture",
        task_type="mobile_draft_reply",
        action_type="mobile_draft_reply_create",
        tool_name="draft_message_reply",
        arguments=(
            MutationArgumentPolicy(
                name="body",
                requester_controlled=True,
                allowed_origins=("instruction",),
            ),
            MutationArgumentPolicy(
                name="thread_id",
                requester_controlled=False,
                allowed_origins=("tool_observation",),
                observation_tool="search_phone_messages",
                observation_field="thread_id",
                observation_bindings=thread_bindings,
                binding_argument_names=("query", "participant"),
                binding_token_aliases=(
                    ("minutes", "minute"),
                    ("late", "delay"),
                ),
            ),
        ),
    )
    return (
        reminder_policy,
        replace(reminder_policy, task_type="mobile_reminder_creation"),
        draft_policy,
    )


def _message_bindings(
    environment: MobileMessagesEnvironment,
    field: str,
) -> tuple[tuple[str, str], ...]:
    bindings: list[tuple[str, str]] = []
    for arguments in MOBILE_MESSAGE_GROUNDING_ARGUMENTS:
        try:
            observation = environment.search_messages(**arguments)
        except KeyError:
            continue
        value = observation.get(field)
        if isinstance(value, str):
            bindings.append(
                (
                    canonical_hash(arguments),
                    canonical_hash(value),
                )
            )
    return tuple(bindings)


def _mobile_semantic_mutation_verdict(
    request: SemanticJudgeRequest,
) -> dict[str, object]:
    instruction = request.instruction.lower()
    action_reference = request.evidence_references["action"]
    action_reason = "action_authorized"
    action_outcome = "supported"
    if "ignore previous" in instruction or "ignore all previous" in instruction:
        action_reason = "instruction_prompt_injection"
        action_outcome = "unsupported"
    elif re.search(
        (
            r"\b(?:do not|don't|without)\b[^.]{0,80}"
            r"\b(?:reminder|reply|response)\b"
        ),
        instruction,
    ):
        action_reason = "action_negated"
        action_outcome = "unsupported"
    elif any(
        phrase in instruction
        for phrase in (
            "if appropriate",
            "if needed",
            "maybe create",
            "maybe draft",
            "consider creating",
            "consider drafting",
        )
    ):
        action_reason = "conditional_authorization_ambiguous"
        action_outcome = "uncertain"
    elif not _action_is_supported(request):
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
            outcome = "supported"
            reason = "observation_reference_supported"
        elif origin == "instruction":
            value = str(request.argument_values.get(name, "")).strip()
            evidence_text = str(request.argument_evidence.get(name, "")).strip()
            if not value:
                outcome = "unsupported"
                reason = "argument_not_supported"
            elif value.lower() in instruction:
                if _literal_argument_is_supported(value, instruction):
                    outcome = "supported"
                    reason = "argument_literal_supported"
                else:
                    outcome = "unsupported"
                    reason = "argument_not_supported"
            elif _argument_is_semantically_supported(value, evidence_text):
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


def _action_is_supported(request: SemanticJudgeRequest) -> bool:
    tokens = _semantic_tokens(request.action_evidence_text)
    if request.action_type == "mobile_reminder_create":
        return (
            "reminder" in tokens
            and bool(tokens & {"add", "create", "make", "schedule", "set"})
        )
    if request.action_type == "mobile_draft_reply_create":
        return (
            bool(tokens & {"reply", "response"})
            and bool(tokens & {"compose", "draft", "prepare", "write"})
        )
    return False


def _argument_is_semantically_supported(value: str, evidence_text: str) -> bool:
    value_tokens = _semantic_tokens(value)
    evidence_tokens = _semantic_tokens(evidence_text)
    if not value_tokens or ("not" in evidence_tokens) != ("not" in value_tokens):
        return False
    return value_tokens.issubset(evidence_tokens)


def _literal_argument_is_supported(value: str, instruction: str) -> bool:
    start = instruction.index(value.lower())
    sentence_start = max(
        instruction.rfind(".", 0, start),
        instruction.rfind(";", 0, start),
        start - 48,
    )
    prefix = instruction[sentence_start + 1:start]
    return re.search(
        r"\b(?:do\s+not|don't|not\s+to|without)\b[^.]{0,40}$",
        prefix,
    ) is None


def _semantic_tokens(value: str) -> set[str]:
    normalized = value.lower()
    normalized = re.sub(r"\b0?9:00\b", "9 am", normalized)
    aliases = {
        "delayed": "delay",
        "delays": "delay",
        "drafted": "draft",
        "nine": "9",
        "replies": "reply",
        "responses": "response",
        "sent": "send",
        "share": "send",
        "sharing": "send",
        "thanks": "thank",
        "thanking": "thank",
        "told": "tell",
        "telling": "tell",
    }
    stopwords = {
        "a",
        "an",
        "and",
        "at",
        "about",
        "by",
        "for",
        "him",
        "me",
        "of",
        "on",
        "saying",
        "the",
        "to",
        "you",
    }
    return {
        aliases.get(token, token)
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in stopwords
    }


mobile_semantic_mutation_judge = DeterministicSemanticMutationJudge(
    evaluate=_mobile_semantic_mutation_verdict,
    model="deterministic_mobile_mutation_judge_v1",
)


def prepare_mobile_candidate(candidate: CandidateTask) -> CandidateTask:
    task_type = candidate.constraints.get("task_type")
    if task_type in REMINDER_TASK_TYPES:
        return propose_mobile_reminder_authorization(candidate)
    if task_type == "mobile_draft_reply":
        return propose_mobile_draft_reply_authorization(candidate)
    return candidate


def propose_mobile_reminder_authorization(
    candidate: CandidateTask,
) -> CandidateTask:
    policy = scripted_mobile_solution_policy(candidate)
    instruction = normalized_instruction(candidate.instruction)
    source_index, source_step = _policy_step(policy, "search_phone_messages")
    mutation_index, mutation_step = _policy_step(policy, "create_phone_reminder")
    arguments = [
        _instruction_argument(
            instruction,
            name="title",
            value=mutation_step.arguments.get("title"),
            fallback_pattern=r"\breminder\b[^.]*",
        ),
    ]
    if "due_at" in mutation_step.arguments:
        arguments.append(
            _instruction_argument(
                instruction,
                name="due_at",
                value=mutation_step.arguments.get("due_at"),
                fallback_pattern=(
                    r"\b(?:today|tomorrow|tonight|next|on|at|by)\b[^.]*"
                ),
            )
        )
    arguments.append(
        _observation_argument(
            instruction,
            name="source_message_id",
            source_index=source_index,
            source_step=source_step,
            source_field="message_id",
            mutation_value=mutation_step.arguments.get("source_message_id"),
            binding_pattern=(
                r"\b(?:find|locate|search(?:\s+for)?|look\s+up)\b[^.]*"
            ),
        )
    )
    return _with_authorization(
        candidate,
        policy=policy,
        instruction=instruction,
        action_type="mobile_reminder_create",
        mutation_index=mutation_index,
        action_pattern=(
            r"\b(?:create|make|set|add|schedule)\b"
            r"[^.]{0,160}\breminder\b[^.]*"
        ),
        arguments=arguments,
    )


def propose_mobile_draft_reply_authorization(
    candidate: CandidateTask,
) -> CandidateTask:
    policy = scripted_mobile_solution_policy(candidate)
    instruction = normalized_instruction(candidate.instruction)
    source_index, source_step = _policy_step(policy, "search_phone_messages")
    mutation_index, mutation_step = _policy_step(policy, "draft_message_reply")
    return _with_authorization(
        candidate,
        policy=policy,
        instruction=instruction,
        action_type="mobile_draft_reply_create",
        mutation_index=mutation_index,
        action_pattern=(
            r"\b(?:draft|write|compose|prepare)\b"
            r"[^.]{0,200}\b(?:repl(?:y|ies)|responses?)\b[^.]*"
        ),
        arguments=[
            _instruction_argument(
                instruction,
                name="body",
                value=mutation_step.arguments.get("body"),
                fallback_pattern=r"\b(?:repl(?:y|ies)|responses?)\b[^.]*",
            ),
            _observation_argument(
                instruction,
                name="thread_id",
                source_index=source_index,
                source_step=source_step,
                source_field="thread_id",
                mutation_value=mutation_step.arguments.get("thread_id"),
                binding_pattern=(
                    r"\b(?:find|locate|search(?:\s+for)?|look\s+up)\b[^.]*"
                ),
            ),
        ],
    )


def _with_authorization(
    candidate: CandidateTask,
    *,
    policy: SolutionPolicy,
    instruction: str,
    action_type: str,
    mutation_index: int,
    action_pattern: str,
    arguments: list[dict[str, object]],
) -> CandidateTask:
    record: dict[str, object] = {
        "schema_version": "mutation_authorization_record_v1",
        "instruction_hash": canonical_hash(instruction),
        "policy_hash": policy_hash(policy),
        "actions": [
            {
                "action_ref": f"policy.steps.{mutation_index}",
                "action_type": action_type,
                "instruction_evidence": _instruction_regex_evidence(
                    instruction,
                    action_pattern,
                    reference_id="instruction.action",
                ),
                "arguments": arguments,
            }
        ],
    }
    return replace(candidate, mutation_authorization=record)


def _instruction_argument(
    instruction: str,
    *,
    name: str,
    value: object,
    fallback_pattern: str,
) -> dict[str, object]:
    literal = str(value) if isinstance(value, str) else ""
    evidence = (
        _instruction_literal_evidence(
            instruction,
            literal,
            reference_id=f"instruction.{name}",
        )
        if literal and literal.lower() in instruction.lower()
        else _instruction_regex_evidence(
            instruction,
            fallback_pattern,
            reference_id=f"instruction.{name}",
        )
    )
    return {
        "name": name,
        "origin": "instruction",
        "support": "literal" if literal and literal.lower() in instruction.lower() else "semantic",
        "evidence": evidence,
    }


def _observation_argument(
    instruction: str,
    *,
    name: str,
    source_index: int,
    source_step: ToolStep,
    source_field: str,
    mutation_value: object,
    binding_pattern: str,
) -> dict[str, object]:
    return {
        "name": name,
        "origin": "tool_observation",
        "evidence": {
            "reference_id": f"observation.selected_{source_field}",
            "kind": "tool_observation",
            "source_action_ref": f"policy.steps.{source_index}",
            "source_field": source_field,
            "source_arguments_hash": canonical_hash(source_step.arguments),
            "value_hash": canonical_hash(mutation_value),
            "binding_instruction_evidence": _instruction_regex_evidence(
                instruction,
                binding_pattern,
                reference_id="instruction.selected_message",
            ),
        },
    }


def _policy_step(policy: SolutionPolicy, tool_name: str) -> tuple[int, ToolStep]:
    for index, step in enumerate(policy.steps):
        if step.tool_name == tool_name:
            return index, step
    raise ValueError(f"mobile mutation policy requires {tool_name}")


def _instruction_regex_evidence(
    instruction: str,
    pattern: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    match = re.search(pattern, instruction, re.IGNORECASE)
    if match is None:
        return _instruction_evidence(
            instruction,
            0,
            min(1, len(instruction)),
            reference_id=reference_id,
        )
    return _instruction_evidence(
        instruction,
        *match.span(),
        reference_id=reference_id,
    )


def _instruction_literal_evidence(
    instruction: str,
    text: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    start = instruction.lower().index(text.lower())
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
