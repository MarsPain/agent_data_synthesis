from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from synthesis.execution import SolutionPolicy
from synthesis.task_contracts import TaskContract


class CandidateAdmissionEvaluator(Protocol):
    def __call__(
        self,
        task_contract: TaskContract,
        solution_policy: SolutionPolicy,
    ) -> dict[str, object] | None: ...


def permit_candidate_execution(
    task_contract: TaskContract,
    solution_policy: SolutionPolicy,
) -> None:
    """Preserve execution while admission policy is not configured."""
    _ = task_contract, solution_policy


AUTHORIZATION_RECORD_VERSION = "mutation_authorization_record_v1"
SEMANTIC_VERDICT_VERSION = "semantic_mutation_verdict_v1"
ADMISSION_EVIDENCE_VERSION = "mutation_admission_evidence_v1"
VALIDATOR_VERSION = "mutation_admission_validator_v1"
ALLOWED_PROVENANCE_ORIGINS = {
    "instruction",
    "tool_observation",
    "declared_default",
    "deterministic_derivation",
}
DETERMINISTIC_FAILURE_CODES = {
    "authorization_record_missing",
    "authorization_action_mismatch",
    "requester_argument_provenance_missing",
    "provenance_origin_invalid",
    "instruction_span_invalid",
    "observation_reference_invalid",
    "declared_default_invalid",
    "deterministic_derivation_invalid",
    "authorization_record_hash_mismatch",
}
SEMANTIC_REASON_CODES = {
    "action_authorized",
    "argument_literal_supported",
    "argument_semantic_supported",
    "observation_reference_supported",
    "declared_default_supported",
    "deterministic_derivation_supported",
    "action_not_authorized",
    "action_negated",
    "conditional_authorization_ambiguous",
    "argument_not_supported",
    "provenance_mismatch",
    "evidence_ambiguous",
    "instruction_prompt_injection",
}


@dataclass(frozen=True)
class MutationArgumentPolicy:
    name: str
    requester_controlled: bool
    allowed_origins: tuple[str, ...]
    observation_tool: str | None = None
    observation_field: str | None = None
    observation_bindings: tuple[tuple[str, str], ...] = ()
    binding_argument_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class MutationActionPolicy:
    schema_version: str
    domain_id: str
    task_type: str
    action_type: str
    tool_name: str
    arguments: tuple[MutationArgumentPolicy, ...]


@dataclass(frozen=True)
class SemanticJudgeRequest:
    instruction: str
    action_type: str
    action_evidence_text: str
    argument_values: Mapping[str, object]
    argument_evidence_text: Mapping[str, str]
    argument_origins: Mapping[str, str]
    evidence_references: Mapping[str, str]

    def input_hash(self) -> str:
        return canonical_hash(
            {
                "instruction": self.instruction,
                "action_type": self.action_type,
                "action_evidence_text": self.action_evidence_text,
                "argument_values": dict(self.argument_values),
                "argument_evidence_text": dict(self.argument_evidence_text),
                "argument_origins": dict(self.argument_origins),
                "evidence_references": dict(self.evidence_references),
            }
        )


class SemanticMutationJudge(Protocol):
    def __call__(self, request: SemanticJudgeRequest) -> dict[str, object]: ...


@dataclass(frozen=True)
class LocalCandidateAdmissionEvaluator:
    mode: str
    policies: tuple[MutationActionPolicy, ...]
    state_changing_tools: frozenset[str]
    judge: SemanticMutationJudge | None

    def __call__(
        self,
        task_contract: TaskContract,
        solution_policy: SolutionPolicy,
    ) -> dict[str, object]:
        mutation_steps = [
            (index, step)
            for index, step in enumerate(solution_policy.steps)
            if step.tool_name in self.state_changing_tools
        ]
        if not mutation_steps:
            return _bypass_evidence(
                self.mode,
                classification="read_only",
                generator_lineage=_generator_lineage(task_contract),
            )

        policy = next(
            (
                candidate
                for candidate in self.policies
                if candidate.domain_id == task_contract.intent.domain_id
                and candidate.task_type == task_contract.intent.task_type
                and any(step.tool_name == candidate.tool_name for _, step in mutation_steps)
            ),
            None,
        )
        if self.mode == "disabled":
            return _disabled_evidence(task_contract, solution_policy, policy)
        if policy is None:
            return _failed_evidence(
                mode=self.mode,
                policy=None,
                solution_policy=solution_policy,
                authorization=task_contract.mutation_authorization,
                generator_lineage=_generator_lineage(task_contract),
                failures=[
                    _failure(
                        "authorization_record_missing",
                        "mutation_authorization",
                    )
                ],
            )

        validation = _validate_authorization(
            task_contract,
            solution_policy,
            policy,
        )
        if validation["failures"]:
            failures = validation["failures"]
            assert isinstance(failures, list)
            return _failed_evidence(
                mode=self.mode,
                policy=policy,
                solution_policy=solution_policy,
                authorization=task_contract.mutation_authorization,
                generator_lineage=_generator_lineage(task_contract),
                failures=failures,
            )

        request = validation["judge_request"]
        assert isinstance(request, SemanticJudgeRequest)
        assert self.judge is not None
        verdict = self.judge(request)
        verdict_hash = canonical_hash(verdict)
        authorization = task_contract.mutation_authorization
        assert authorization is not None
        raw_judge_lineage = verdict.get("judge_lineage")
        judge_lineage = (
            dict(raw_judge_lineage)
            if isinstance(raw_judge_lineage, Mapping)
            else {}
        )
        return {
            "schema_version": ADMISSION_EVIDENCE_VERSION,
            "classification": "state_changing",
            "mode": self.mode,
            "contract_versions": _contract_versions(policy),
            "deterministic_validation": {
                "status": "passed",
                "reason_codes": [],
                "findings": [],
            },
            "semantic_verdict": verdict,
            "hashes": {
                "authorization": canonical_hash(authorization),
                "input": request.input_hash(),
                "policy": policy_hash(solution_policy),
                "verdict": verdict_hash,
            },
            "lineage": {
                "generator": _generator_lineage(task_contract),
                "validator": {
                    "version": VALIDATOR_VERSION,
                    "config_hash": canonical_hash(_contract_versions(policy)),
                },
                "judge": judge_lineage,
            },
            "diagnostic_only": True,
        }


def build_local_candidate_admission_evaluator(
    *,
    mode: str,
    policies: Sequence[MutationActionPolicy],
    state_changing_tools: Sequence[str],
    judge: object | None = None,
) -> LocalCandidateAdmissionEvaluator:
    if mode not in {"disabled", "shadow"}:
        raise ValueError("mode must be disabled or shadow")
    selected_judge = judge
    if mode == "shadow" and not callable(selected_judge):
        raise ValueError("shadow mode requires a semantic mutation judge")
    if selected_judge is not None and not callable(selected_judge):
        raise TypeError("judge must be callable")
    return LocalCandidateAdmissionEvaluator(
        mode=mode,
        policies=tuple(policies),
        state_changing_tools=frozenset(state_changing_tools),
        judge=selected_judge,
    )


def validate_mutation_admission_evidence(raw: object) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("mutation_admission must be an object")
    base_keys = {
        "schema_version",
        "classification",
        "mode",
        "contract_versions",
        "deterministic_validation",
        "hashes",
        "lineage",
        "diagnostic_only",
    }
    allowed_keys = base_keys | {"semantic_verdict"}
    if not set(raw).issubset(allowed_keys) or not base_keys.issubset(raw):
        raise ValueError("mutation_admission contains unsupported or missing keys")
    if raw.get("schema_version") != ADMISSION_EVIDENCE_VERSION:
        raise ValueError("mutation_admission schema_version is unsupported")
    classification = raw.get("classification")
    if classification not in {"read_only", "state_changing"}:
        raise ValueError("mutation_admission classification is unsupported")
    mode = raw.get("mode")
    if mode not in {"disabled", "shadow"}:
        raise ValueError("mutation_admission mode is unsupported")
    if not isinstance(raw.get("diagnostic_only"), bool):
        raise ValueError("mutation_admission diagnostic_only must be a bool")

    versions = _exact_mapping(
        raw.get("contract_versions"),
        {"authorization", "domain_policy", "semantic_verdict"},
        "mutation_admission.contract_versions",
    )
    if versions.get("authorization") != AUTHORIZATION_RECORD_VERSION:
        raise ValueError("mutation_admission authorization version is unsupported")
    if versions.get("semantic_verdict") != SEMANTIC_VERDICT_VERSION:
        raise ValueError("mutation_admission semantic verdict version is unsupported")
    if not isinstance(versions.get("domain_policy"), str):
        raise ValueError("mutation_admission domain policy version must be a string")

    validation = _exact_mapping(
        raw.get("deterministic_validation"),
        {"status", "reason_codes", "findings"},
        "mutation_admission.deterministic_validation",
    )
    status = validation.get("status")
    if status not in {"passed", "failed", "bypassed", "not_evaluated"}:
        raise ValueError("mutation_admission validation status is unsupported")
    reason_codes = _string_list(
        validation.get("reason_codes"),
        "mutation_admission.deterministic_validation.reason_codes",
    )
    if any(code not in DETERMINISTIC_FAILURE_CODES for code in reason_codes):
        raise ValueError("mutation_admission deterministic reason code is unsupported")
    findings = validation.get("findings")
    if not isinstance(findings, list):
        raise ValueError("mutation_admission deterministic findings must be a list")
    for index, finding_raw in enumerate(findings):
        finding = _exact_mapping(
            finding_raw,
            {"failure_class", "code", "field_path", "evidence_references"},
            f"mutation_admission.deterministic_validation.findings.{index}",
        )
        if finding.get("failure_class") != "mutation_admission_failed":
            raise ValueError("mutation_admission finding failure class is unsupported")
        if finding.get("code") not in DETERMINISTIC_FAILURE_CODES:
            raise ValueError("mutation_admission finding code is unsupported")
        _bounded_string(finding.get("field_path"), "mutation_admission finding field_path")
        _string_list(finding.get("evidence_references"), "evidence_references")
    if status == "failed" and (not reason_codes or not findings):
        raise ValueError("failed mutation_admission requires reasons and findings")
    if status != "failed" and (reason_codes or findings):
        raise ValueError("non-failed mutation_admission cannot contain failures")

    semantic_verdict = raw.get("semantic_verdict")
    if status == "passed" and mode == "shadow" and classification == "state_changing":
        _validate_semantic_verdict(semantic_verdict)
    elif semantic_verdict is not None:
        raise ValueError("semantic verdict is not allowed on this admission path")

    hashes = raw.get("hashes")
    if not isinstance(hashes, Mapping):
        raise ValueError("mutation_admission hashes must be an object")
    allowed_hashes = {"authorization", "input", "policy", "verdict"}
    if not set(hashes).issubset(allowed_hashes):
        raise ValueError("mutation_admission hash name is unsupported")
    for name, value in hashes.items():
        if not _is_sha256(value):
            raise ValueError(f"mutation_admission hash {name} is invalid")
    if semantic_verdict is not None:
        if set(hashes) != allowed_hashes:
            raise ValueError("semantic mutation_admission requires all hashes")
        assert isinstance(semantic_verdict, Mapping)
        if hashes.get("input") != semantic_verdict.get("input_hash"):
            raise ValueError("mutation_admission input hash mismatch")
        if hashes.get("verdict") != canonical_hash(semantic_verdict):
            raise ValueError("mutation_admission verdict hash mismatch")

    lineage = raw.get("lineage")
    if not isinstance(lineage, Mapping) or not {
        "generator",
        "validator",
    }.issubset(lineage):
        raise ValueError("mutation_admission generator and validator lineage are required")
    if not set(lineage).issubset({"generator", "validator", "judge"}):
        raise ValueError("mutation_admission lineage key is unsupported")
    generator = _exact_mapping(
        lineage.get("generator"),
        {"role", "role_version", "provider_host", "model", "config_hash"},
        "mutation_admission.lineage.generator",
    )
    for key in ("role", "role_version", "provider_host", "model", "config_hash"):
        _bounded_string(
            generator.get(key),
            f"mutation_admission.lineage.generator.{key}",
        )
    validator = _exact_mapping(
        lineage.get("validator"),
        {"version", "config_hash"},
        "mutation_admission.lineage.validator",
    )
    if validator.get("version") != VALIDATOR_VERSION or not _is_sha256(
        validator.get("config_hash")
    ):
        raise ValueError("mutation_admission validator lineage is invalid")
    if semantic_verdict is not None:
        judge = lineage.get("judge")
        assert isinstance(semantic_verdict, Mapping)
        if judge != semantic_verdict.get("judge_lineage"):
            raise ValueError("mutation_admission judge lineage mismatch")


def _validate_semantic_verdict(raw: object) -> None:
    verdict = _exact_mapping(
        raw,
        {
            "schema_version",
            "verdict",
            "action_findings",
            "argument_findings",
            "reason_codes",
            "evidence_references",
            "input_hash",
            "judge_lineage",
        },
        "mutation_admission.semantic_verdict",
    )
    if verdict.get("schema_version") != SEMANTIC_VERDICT_VERSION:
        raise ValueError("semantic mutation verdict version is unsupported")
    if verdict.get("verdict") not in {"supported", "unsupported", "uncertain"}:
        raise ValueError("semantic mutation verdict is unsupported")
    reasons = _string_list(verdict.get("reason_codes"), "semantic reason_codes")
    if not reasons or any(reason not in SEMANTIC_REASON_CODES for reason in reasons):
        raise ValueError("semantic mutation reason code is unsupported")
    references = _string_list(
        verdict.get("evidence_references"),
        "semantic evidence_references",
    )
    if not references:
        raise ValueError("semantic mutation verdict requires evidence references")
    if not _is_sha256(verdict.get("input_hash")):
        raise ValueError("semantic mutation verdict input hash is invalid")
    for collection_name, required_keys in (
        (
            "action_findings",
            {"action_type", "outcome", "reason_code", "evidence_references"},
        ),
        (
            "argument_findings",
            {"argument", "outcome", "reason_code", "evidence_references"},
        ),
    ):
        findings = verdict.get(collection_name)
        if not isinstance(findings, list) or not findings:
            raise ValueError(f"semantic mutation {collection_name} must not be empty")
        for index, finding_raw in enumerate(findings):
            finding = _exact_mapping(
                finding_raw,
                required_keys,
                f"semantic mutation {collection_name}.{index}",
            )
            if finding.get("outcome") not in {"supported", "unsupported", "uncertain"}:
                raise ValueError("semantic mutation finding outcome is unsupported")
            if finding.get("reason_code") not in SEMANTIC_REASON_CODES:
                raise ValueError("semantic mutation finding reason is unsupported")
            _string_list(finding.get("evidence_references"), "finding references")
    judge = _exact_mapping(
        verdict.get("judge_lineage"),
        {"role", "role_version", "provider_host", "model", "config_hash"},
        "semantic mutation judge_lineage",
    )
    for key in ("role", "role_version", "provider_host", "model"):
        _bounded_string(judge.get(key), f"semantic mutation judge_lineage.{key}")
    if not _is_sha256(judge.get("config_hash")):
        raise ValueError("semantic mutation judge config_hash is invalid")


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def normalized_instruction(instruction: str) -> str:
    return " ".join(instruction.split())


def policy_hash(policy: SolutionPolicy) -> str:
    return canonical_hash(
        {
            "policy_id": policy.policy_id,
            "role": policy.role,
            "steps": [
                {
                    "tool_name": step.tool_name,
                    "arguments": step.arguments,
                }
                for step in policy.steps
            ],
            "final_response_template": policy.final_response_template,
            "branch_plan": policy.branch_plan,
        }
    )


def instruction_span(
    instruction: str,
    text: str,
    *,
    reference_id: str,
) -> dict[str, object]:
    normalized = normalized_instruction(instruction)
    start = normalized.index(text)
    end = start + len(text)
    return {
        "reference_id": reference_id,
        "kind": "instruction_span",
        "start": start,
        "end": end,
        "evidence_hash": canonical_hash(text),
    }


def _validate_authorization(
    task_contract: TaskContract,
    solution_policy: SolutionPolicy,
    policy: MutationActionPolicy,
) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    authorization = task_contract.mutation_authorization
    if authorization is None:
        failures.append(_failure("authorization_record_missing", "mutation_authorization"))
        return {"failures": failures}
    if authorization.get("schema_version") != AUTHORIZATION_RECORD_VERSION:
        failures.append(
            _failure(
                "authorization_record_hash_mismatch",
                "mutation_authorization.schema_version",
            )
        )

    instruction = normalized_instruction(task_contract.intent.instruction)
    if authorization.get("instruction_hash") != canonical_hash(instruction):
        failures.append(
            _failure(
                "authorization_record_hash_mismatch",
                "mutation_authorization.instruction_hash",
            )
        )
    if authorization.get("policy_hash") != policy_hash(solution_policy):
        failures.append(
            _failure(
                "authorization_record_hash_mismatch",
                "mutation_authorization.policy_hash",
            )
        )

    raw_actions = authorization.get("actions")
    if not isinstance(raw_actions, list) or len(raw_actions) != 1:
        failures.append(
            _failure(
                "authorization_action_mismatch",
                "mutation_authorization.actions",
            )
        )
        return {"failures": failures}
    action = raw_actions[0]
    if not isinstance(action, Mapping):
        failures.append(
            _failure(
                "authorization_action_mismatch",
                "mutation_authorization.actions.0",
            )
        )
        return {"failures": failures}

    mutation_index = next(
        (
            index
            for index, step in enumerate(solution_policy.steps)
            if step.tool_name == policy.tool_name
        ),
        None,
    )
    expected_action_ref = (
        f"policy.steps.{mutation_index}" if mutation_index is not None else "policy.steps.missing"
    )
    if (
        mutation_index is None
        or action.get("action_ref") != expected_action_ref
        or action.get("action_type") != policy.action_type
    ):
        failures.append(
            _failure(
                "authorization_action_mismatch",
                "mutation_authorization.actions.0",
            )
        )

    action_evidence_text, action_reference = _validated_instruction_evidence(
        action.get("instruction_evidence"),
        instruction,
        "mutation_authorization.actions.0.instruction_evidence",
        failures,
    )
    raw_arguments = action.get("arguments")
    argument_records = {
        str(argument.get("name")): argument
        for argument in raw_arguments
        if isinstance(argument, Mapping) and isinstance(argument.get("name"), str)
    } if isinstance(raw_arguments, list) else {}

    mutation_arguments = (
        solution_policy.steps[mutation_index].arguments
        if mutation_index is not None
        else {}
    )
    argument_values: dict[str, object] = {}
    evidence_texts: dict[str, str] = {}
    argument_origins: dict[str, str] = {}
    evidence_references: dict[str, str] = {"action": action_reference}
    for argument_policy in policy.arguments:
        argument = argument_records.get(argument_policy.name)
        path = f"mutation_authorization.actions.0.arguments.{argument_policy.name}"
        if argument is None:
            code = (
                "requester_argument_provenance_missing"
                if argument_policy.requester_controlled
                else "observation_reference_invalid"
            )
            failures.append(_failure(code, path))
            continue
        origin = argument.get("origin")
        if (
            origin not in ALLOWED_PROVENANCE_ORIGINS
            or origin not in argument_policy.allowed_origins
        ):
            failures.append(_failure("provenance_origin_invalid", f"{path}.origin"))
            continue
        assert isinstance(origin, str)
        argument_values[argument_policy.name] = mutation_arguments.get(argument_policy.name)
        argument_origins[argument_policy.name] = origin
        if origin == "instruction":
            evidence_text, reference = _validated_instruction_evidence(
                argument.get("evidence"),
                instruction,
                f"{path}.evidence",
                failures,
            )
            support = argument.get("support")
            if support not in {"literal", "semantic"}:
                failures.append(_failure("provenance_origin_invalid", f"{path}.support"))
            evidence_texts[argument_policy.name] = evidence_text
            evidence_references[argument_policy.name] = reference
        elif origin == "tool_observation":
            reference = _validate_observation_evidence(
                argument.get("evidence"),
                instruction=instruction,
                solution_policy=solution_policy,
                mutation_index=mutation_index,
                argument_name=argument_policy.name,
                argument_value=mutation_arguments.get(argument_policy.name),
                argument_policy=argument_policy,
                path=f"{path}.evidence",
                failures=failures,
            )
            evidence_references[argument_policy.name] = reference
            evidence_texts[argument_policy.name] = ""
        else:
            reference = _validate_declared_evidence(
                argument.get("evidence"),
                origin=origin,
                path=f"{path}.evidence",
                failures=failures,
            )
            evidence_references[argument_policy.name] = reference
            evidence_texts[argument_policy.name] = ""

    if failures:
        return {"failures": failures}
    return {
        "failures": [],
        "judge_request": SemanticJudgeRequest(
            instruction=instruction,
            action_type=policy.action_type,
            action_evidence_text=action_evidence_text,
            argument_values=argument_values,
            argument_evidence_text=evidence_texts,
            argument_origins=argument_origins,
            evidence_references=evidence_references,
        ),
    }


def _validated_instruction_evidence(
    raw_evidence: object,
    instruction: str,
    path: str,
    failures: list[dict[str, object]],
) -> tuple[str, str]:
    if not isinstance(raw_evidence, Mapping):
        failures.append(_failure("instruction_span_invalid", path))
        return "", "invalid_instruction_reference"
    reference = raw_evidence.get("reference_id")
    start = raw_evidence.get("start")
    end = raw_evidence.get("end")
    if (
        raw_evidence.get("kind") != "instruction_span"
        or not isinstance(reference, str)
        or not reference
        or len(reference) > 80
        or re.fullmatch(r"[a-z0-9_.:-]+", reference) is None
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(instruction)
    ):
        failures.append(_failure("instruction_span_invalid", path))
        return "", str(reference or "invalid_instruction_reference")
    text = instruction[start:end]
    if raw_evidence.get("evidence_hash") != canonical_hash(text):
        failures.append(
            _failure("instruction_span_invalid", path, evidence_references=[reference])
        )
    return text, reference


def _validate_declared_evidence(
    raw_evidence: object,
    *,
    origin: str,
    path: str,
    failures: list[dict[str, object]],
) -> str:
    failure_code = (
        "declared_default_invalid"
        if origin == "declared_default"
        else "deterministic_derivation_invalid"
    )
    if not isinstance(raw_evidence, Mapping):
        failures.append(_failure(failure_code, path))
        return f"invalid_{origin}_reference"
    reference = raw_evidence.get("reference_id")
    declaration_hash = raw_evidence.get("declaration_hash")
    if (
        raw_evidence.get("kind") != origin
        or not isinstance(reference, str)
        or re.fullmatch(r"[a-z0-9_.:-]{1,80}", reference) is None
        or not _is_sha256(declaration_hash)
    ):
        failures.append(_failure(failure_code, path))
    return str(reference or f"invalid_{origin}_reference")


def _validate_observation_evidence(
    raw_evidence: object,
    *,
    instruction: str,
    solution_policy: SolutionPolicy,
    mutation_index: int | None,
    argument_name: str,
    argument_value: object,
    argument_policy: MutationArgumentPolicy,
    path: str,
    failures: list[dict[str, object]],
) -> str:
    if not isinstance(raw_evidence, Mapping):
        failures.append(_failure("observation_reference_invalid", path))
        return "invalid_observation_reference"
    reference = raw_evidence.get("reference_id")
    source_ref = raw_evidence.get("source_action_ref")
    source_index = _policy_step_index(source_ref)
    valid_source = (
        isinstance(reference, str)
        and bool(reference)
        and len(reference) <= 80
        and re.fullmatch(r"[a-z0-9_.:-]+", reference) is not None
        and raw_evidence.get("kind") == "tool_observation"
        and source_index is not None
        and mutation_index is not None
        and source_index < mutation_index
        and source_index < len(solution_policy.steps)
        and solution_policy.steps[source_index].tool_name == argument_policy.observation_tool
        and raw_evidence.get("source_field") == argument_policy.observation_field
        and raw_evidence.get("source_arguments_hash")
        == canonical_hash(solution_policy.steps[source_index].arguments)
        and raw_evidence.get("value_hash") == canonical_hash(argument_value)
    )
    if valid_source and argument_policy.observation_bindings:
        binding = (
            str(raw_evidence.get("source_arguments_hash")),
            str(raw_evidence.get("value_hash")),
        )
        valid_source = binding in argument_policy.observation_bindings
    binding_text, _ = _validated_instruction_evidence(
        raw_evidence.get("binding_instruction_evidence"),
        instruction,
        f"{path}.binding_instruction_evidence",
        failures,
    )
    if valid_source and argument_policy.binding_argument_names:
        assert source_index is not None
        source_arguments = solution_policy.steps[source_index].arguments
        expected_tokens = {
            token
            for name in argument_policy.binding_argument_names
            for token in _evidence_tokens(str(source_arguments.get(name, "")))
        }
        valid_source = bool(expected_tokens) and expected_tokens.issubset(
            _evidence_tokens(binding_text)
        )
    if not valid_source:
        failures.append(
            _failure(
                "observation_reference_invalid",
                path,
                evidence_references=[str(reference)] if reference else [],
            )
        )
    return str(reference or f"invalid_{argument_name}_observation_reference")


def _policy_step_index(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"policy\.steps\.(\d+)", value)
    return int(match.group(1)) if match else None


def _evidence_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _bypass_evidence(
    mode: str,
    *,
    classification: str,
    generator_lineage: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": ADMISSION_EVIDENCE_VERSION,
        "classification": classification,
        "mode": mode,
        "contract_versions": {
            "authorization": AUTHORIZATION_RECORD_VERSION,
            "domain_policy": "not_applicable",
            "semantic_verdict": SEMANTIC_VERDICT_VERSION,
        },
        "deterministic_validation": {
            "status": "bypassed",
            "reason_codes": [],
            "findings": [],
        },
        "hashes": {},
        "lineage": {
            "generator": generator_lineage,
            "validator": {
                "version": VALIDATOR_VERSION,
                "config_hash": canonical_hash({"classification": classification}),
            }
        },
        "diagnostic_only": mode != "disabled",
    }


def _disabled_evidence(
    task_contract: TaskContract,
    solution_policy: SolutionPolicy,
    policy: MutationActionPolicy | None,
) -> dict[str, object]:
    authorization = task_contract.mutation_authorization
    hashes = {"policy": policy_hash(solution_policy)}
    if authorization is not None:
        hashes["authorization"] = canonical_hash(authorization)
    return {
        "schema_version": ADMISSION_EVIDENCE_VERSION,
        "classification": "state_changing",
        "mode": "disabled",
        "contract_versions": _contract_versions(policy),
        "deterministic_validation": {
            "status": "not_evaluated",
            "reason_codes": [],
            "findings": [],
        },
        "hashes": hashes,
        "lineage": {
            "generator": _generator_lineage(task_contract),
            "validator": {
                "version": VALIDATOR_VERSION,
                "config_hash": canonical_hash({"mode": "disabled"}),
            }
        },
        "diagnostic_only": False,
    }


def _failed_evidence(
    *,
    mode: str,
    policy: MutationActionPolicy | None,
    solution_policy: SolutionPolicy,
    authorization: Mapping[str, object] | None,
    generator_lineage: dict[str, object],
    failures: list[dict[str, object]],
) -> dict[str, object]:
    hashes = {"policy": policy_hash(solution_policy)}
    if authorization is not None:
        hashes["authorization"] = canonical_hash(authorization)
    return {
        "schema_version": ADMISSION_EVIDENCE_VERSION,
        "classification": "state_changing",
        "mode": mode,
        "contract_versions": _contract_versions(policy),
        "deterministic_validation": {
            "status": "failed",
            "reason_codes": _unique(str(finding["code"]) for finding in failures),
            "findings": failures,
        },
        "hashes": hashes,
        "lineage": {
            "generator": generator_lineage,
            "validator": {
                "version": VALIDATOR_VERSION,
                "config_hash": canonical_hash(_contract_versions(policy)),
            }
        },
        "diagnostic_only": True,
    }


def _contract_versions(policy: MutationActionPolicy | None) -> dict[str, object]:
    return {
        "authorization": AUTHORIZATION_RECORD_VERSION,
        "domain_policy": policy.schema_version if policy is not None else "unconfigured",
        "semantic_verdict": SEMANTIC_VERDICT_VERSION,
    }


def _generator_lineage(task_contract: TaskContract) -> dict[str, object]:
    intent_lineage = task_contract.intent.lineage
    nested_generation = intent_lineage.get("generation")
    source = (
        nested_generation
        if isinstance(nested_generation, Mapping)
        else intent_lineage
    )
    return {
        key: str(source.get(key, "unknown"))
        for key in ("role", "role_version", "provider_host", "model", "config_hash")
    }


def _failure(
    code: str,
    field_path: str,
    *,
    evidence_references: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "failure_class": "mutation_admission_failed",
        "code": code,
        "field_path": field_path,
        "evidence_references": list(evidence_references),
    }


def _exact_mapping(
    raw: object,
    keys: set[str],
    path: str,
) -> Mapping[str, object]:
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise ValueError(f"{path} must contain exact supported keys")
    return raw


def _string_list(raw: object, path: str) -> list[str]:
    if not isinstance(raw, list) or any(
        not isinstance(value, str) or not value or len(value) > 160
        for value in raw
    ):
        raise ValueError(f"{path} must be a bounded string list")
    return raw


def _bounded_string(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 240:
        raise ValueError(f"{path} must be a bounded string")
    return raw


def _is_sha256(raw: object) -> bool:
    return isinstance(raw, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", raw) is not None


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))
