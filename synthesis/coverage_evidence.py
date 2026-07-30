from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import hashlib
import json

from synthesis.coverage import CoveragePlan, canonical_coverage_hash


COVERAGE_EVIDENCE_SCHEMA_VERSION = "coverage_evidence_v1"
COVERAGE_EVIDENCE_FILENAME = "coverage_evidence.json"
COVERAGE_QUALITY_SUMMARY_SCHEMA_VERSION = "coverage_quality_summary_v1"
_SHA256_PREFIX = "sha256:"


def build_coverage_evidence(
    *,
    dataset_version: str,
    plan: CoveragePlan,
    reconciliation: Mapping[str, object],
    run_profile: Mapping[str, object],
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
    samples_artifact: Mapping[str, object],
    rejections_artifact: Mapping[str, object],
) -> dict[str, object]:
    sample_identities = [
        _sample_identity(sample)
        for sample in samples
    ]
    rejection_identities = [
        _rejection_identity(rejection)
        for rejection in rejections
    ]
    assignment_records = _assignment_records(
        sample_identities,
        rejection_identities,
    )
    cells = _cell_evidence(
        plan=plan,
        reconciliation=reconciliation,
        assignment_records=assignment_records,
    )
    counts = _coverage_counts(
        plan=plan,
        reconciliation=reconciliation,
        assignment_records=assignment_records,
        samples=sample_identities,
        rejections=rejection_identities,
        cells=cells,
    )
    identities = {
        "catalog": {
            "catalog_id": plan.catalog["catalog_id"],
            "version": plan.catalog["version"],
            "identity_hash": plan.catalog["catalog_hash"],
        },
        "coverage_profile": {
            "profile_id": plan.coverage_profile["profile_id"],
            "version": plan.coverage_profile["version"],
            "identity_hash": plan.coverage_profile["profile_hash"],
        },
        "plan": {
            "plan_id": plan.plan_id,
            "identity_hash": plan.plan_hash,
        },
        "scheduler": _scheduler_identity(),
        "run_profile": _run_profile_identity(run_profile),
        "assignments": {
            "count": len(assignment_records),
            "identity_hash": canonical_coverage_hash(
                [
                    {
                        "assignment_id": record["assignment_id"],
                        "assignment_hash": record["assignment_hash"],
                    }
                    for record in assignment_records
                ]
            ),
        },
        "accepted_samples": {
            "count": len(sample_identities),
            "identity_hash": canonical_coverage_hash(sample_identities),
            "artifact": _artifact_binding(
                samples_artifact,
                expected_path="samples.jsonl",
            ),
        },
        "rejections": {
            "count": len(rejection_identities),
            "identity_hash": canonical_coverage_hash(rejection_identities),
            "artifact": _artifact_binding(
                rejections_artifact,
                expected_path="rejections.jsonl",
            ),
        },
    }
    payload: dict[str, object] = {
        "schema_version": COVERAGE_EVIDENCE_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "identities": identities,
        "counts": counts,
        "cells": cells,
        "distributions": _coverage_distributions(
            assignment_records=assignment_records,
            samples=samples,
            rejections=rejections,
        ),
        "fulfillment": _coverage_fulfillment(
            reconciliation=reconciliation,
            cells=cells,
            counts=counts,
        ),
    }
    evidence_hash = canonical_coverage_hash(payload)
    return {
        "schema_version": COVERAGE_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": (
            "coverage_evidence_"
            + evidence_hash.removeprefix("sha256:")[:16]
        ),
        "evidence_hash": evidence_hash,
        **{
            key: value
            for key, value in payload.items()
            if key != "schema_version"
        },
    }


def coverage_quality_summary(
    evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": COVERAGE_QUALITY_SUMMARY_SCHEMA_VERSION,
        "evidence_id": evidence["evidence_id"],
        "evidence_hash": evidence["evidence_hash"],
        "counts": dict(_mapping(evidence.get("counts"))),
        "distributions": dict(_mapping(evidence.get("distributions"))),
        "fulfillment": dict(_mapping(evidence.get("fulfillment"))),
    }


def validate_coverage_quality_summary_record(
    summary: Mapping[str, object],
) -> None:
    if set(summary) != {
        "schema_version",
        "evidence_id",
        "evidence_hash",
        "counts",
        "distributions",
        "fulfillment",
    }:
        raise ValueError("coverage quality summary contains unsupported keys")
    if (
        summary.get("schema_version")
        != COVERAGE_QUALITY_SUMMARY_SCHEMA_VERSION
    ):
        raise ValueError("coverage quality summary schema version is unsupported")
    evidence_hash = _hash_value(summary.get("evidence_hash"))
    if summary.get("evidence_id") != (
        "coverage_evidence_"
        + evidence_hash.removeprefix(_SHA256_PREFIX)[:16]
    ):
        raise ValueError("coverage quality summary evidence id is invalid")

    counts = _validated_counts(summary.get("counts"))
    _validate_distributions(summary.get("distributions"), counts=counts)
    fulfillment = _mapping(summary.get("fulfillment"))
    if set(fulfillment) != {
        "status",
        "mandatory_fulfilled",
        "target_fulfilled",
        "reasons",
    }:
        raise ValueError("coverage quality summary fulfillment is invalid")
    mandatory = fulfillment.get("mandatory_fulfilled")
    target = fulfillment.get("target_fulfilled")
    if not isinstance(mandatory, bool) or not isinstance(target, bool):
        raise ValueError("coverage quality summary fulfillment is invalid")
    expected_target = _int(counts["remaining"]) == 0
    if target is not expected_target:
        raise ValueError("coverage quality summary target fulfillment is invalid")
    expected_status = "fulfilled" if mandatory and target else "incomplete"
    if fulfillment.get("status") != expected_status:
        raise ValueError("coverage quality summary fulfillment status is invalid")
    _validate_fulfillment_reasons(
        fulfillment.get("reasons"),
        mandatory_fulfilled=mandatory,
        target_fulfilled=target,
        counts=counts,
    )


def validate_coverage_evidence_record(
    evidence: Mapping[str, object],
) -> None:
    expected_keys = {
        "schema_version",
        "evidence_id",
        "evidence_hash",
        "dataset_version",
        "identities",
        "counts",
        "cells",
        "distributions",
        "fulfillment",
    }
    if set(evidence) != expected_keys:
        raise ValueError("coverage evidence contains unsupported keys")
    if evidence.get("schema_version") != COVERAGE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("coverage evidence schema version is unsupported")
    evidence_hash = _hash_value(evidence.get("evidence_hash"))
    expected_hash = canonical_coverage_hash(
        {
            key: value
            for key, value in evidence.items()
            if key not in {"evidence_id", "evidence_hash"}
        }
    )
    if evidence_hash != expected_hash:
        raise ValueError("coverage evidence hash is invalid")
    if evidence.get("evidence_id") != (
        "coverage_evidence_"
        + evidence_hash.removeprefix(_SHA256_PREFIX)[:16]
    ):
        raise ValueError("coverage evidence id is invalid")
    if not isinstance(evidence.get("dataset_version"), str):
        raise ValueError("coverage evidence dataset version is invalid")

    identities = _mapping(evidence.get("identities"))
    if set(identities) != {
        "catalog",
        "coverage_profile",
        "plan",
        "scheduler",
        "run_profile",
        "assignments",
        "accepted_samples",
        "rejections",
    }:
        raise ValueError("coverage evidence identities are invalid")
    for identity_name in identities:
        identity = _mapping(identities[identity_name])
        _hash_value(identity.get("identity_hash"))
    for counted_identity in (
        "assignments",
        "accepted_samples",
        "rejections",
    ):
        _int(_mapping(identities[counted_identity]).get("count"))
    _artifact_binding(
        _mapping(identities["accepted_samples"]).get("artifact"),
        expected_path="samples.jsonl",
    )
    _artifact_binding(
        _mapping(identities["rejections"]).get("artifact"),
        expected_path="rejections.jsonl",
    )

    counts = _validated_counts(evidence.get("counts"))
    if _int(_mapping(identities["assignments"])["count"]) != _int(
        counts["attempted"]
    ):
        raise ValueError("coverage evidence assignment count does not reconcile")
    if _int(_mapping(identities["accepted_samples"])["count"]) != (
        _int(counts["accepted"]) + _int(counts["unassigned_accepted"])
    ):
        raise ValueError("coverage evidence sample count does not reconcile")
    if _int(_mapping(identities["rejections"])["count"]) != (
        _int(counts["rejected"]) + _int(counts["unassigned_rejected"])
    ):
        raise ValueError("coverage evidence rejection count does not reconcile")

    raw_cells = evidence.get("cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise ValueError("coverage evidence cells are invalid")
    cells = [_validated_cell(cell) for cell in raw_cells]
    if [cell["cell_id"] for cell in cells] != sorted(
        str(cell["cell_id"]) for cell in cells
    ):
        raise ValueError("coverage evidence cells must be sorted")
    if sum(_int(cell["planned"]) for cell in cells) != _int(
        counts["target_accepted"]
    ):
        raise ValueError("coverage evidence planned cells do not reconcile")
    for field in ("attempted", "generated", "accepted", "rejected", "remaining"):
        if sum(_int(cell[field]) for cell in cells) != _int(counts[field]):
            raise ValueError(
                f"coverage evidence cell {field} counts do not reconcile"
            )
    _validate_distributions(evidence.get("distributions"), counts=counts)
    _validate_fulfillment(
        evidence.get("fulfillment"),
        cells=cells,
        counts=counts,
    )


def verify_coverage_evidence(
    evidence: Mapping[str, object],
    *,
    plan: Mapping[str, object],
    run_profile: Mapping[str, object],
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> None:
    validate_coverage_evidence_record(evidence)
    _validate_plan_identity(plan, run_profile=run_profile)
    identities = _mapping(evidence["identities"])
    expected_catalog = {
        "catalog_id": _mapping(plan.get("catalog")).get("catalog_id"),
        "version": _mapping(plan.get("catalog")).get("version"),
        "identity_hash": _mapping(plan.get("catalog")).get("catalog_hash"),
    }
    expected_profile = {
        "profile_id": _mapping(plan.get("coverage_profile")).get("profile_id"),
        "version": _mapping(plan.get("coverage_profile")).get("version"),
        "identity_hash": _mapping(plan.get("coverage_profile")).get(
            "profile_hash"
        ),
    }
    expected_plan = {
        "plan_id": plan.get("plan_id"),
        "identity_hash": plan.get("plan_hash"),
    }
    expected_scheduler = _scheduler_identity()
    expected_run_profile = _run_profile_identity(run_profile)
    sample_identities = [_sample_identity(sample) for sample in samples]
    rejection_identities = [
        _rejection_identity(rejection)
        for rejection in rejections
    ]
    assignment_records = _assignment_records(
        sample_identities,
        rejection_identities,
    )
    expected_identity_bindings = {
        "catalog": expected_catalog,
        "coverage_profile": expected_profile,
        "plan": expected_plan,
        "scheduler": expected_scheduler,
        "run_profile": expected_run_profile,
        "assignments": {
            "count": len(assignment_records),
            "identity_hash": canonical_coverage_hash(
                [
                    {
                        "assignment_id": record["assignment_id"],
                        "assignment_hash": record["assignment_hash"],
                    }
                    for record in assignment_records
                ]
            ),
        },
        "accepted_samples": {
            "count": len(sample_identities),
            "identity_hash": canonical_coverage_hash(sample_identities),
            "artifact": _jsonl_artifact_binding(
                "samples.jsonl",
                samples,
            ),
        },
        "rejections": {
            "count": len(rejection_identities),
            "identity_hash": canonical_coverage_hash(rejection_identities),
            "artifact": _jsonl_artifact_binding(
                "rejections.jsonl",
                rejections,
            ),
        },
    }
    if dict(identities) != expected_identity_bindings:
        raise ValueError("coverage evidence identity mismatch")

    expected_counts, expected_cells = _expected_external_counts_and_cells(
        plan=plan,
        assignment_records=assignment_records,
        sample_identities=sample_identities,
        rejection_identities=rejection_identities,
    )
    if dict(_mapping(evidence["counts"])) != expected_counts:
        raise ValueError("coverage evidence identity mismatch")
    if evidence["cells"] != expected_cells:
        raise ValueError("coverage evidence identity mismatch")
    if dict(_mapping(evidence["distributions"])) != _coverage_distributions(
        assignment_records=assignment_records,
        samples=samples,
        rejections=rejections,
    ):
        raise ValueError("coverage evidence identity mismatch")
    expected_fulfillment = _coverage_fulfillment(
        reconciliation={
            "status": (
                "complete"
                if expected_counts["remaining"] == 0
                else "incomplete"
            )
        },
        cells=expected_cells,
        counts=expected_counts,
    )
    if dict(_mapping(evidence["fulfillment"])) != expected_fulfillment:
        raise ValueError("coverage evidence identity mismatch")


def verify_sanitized_coverage_evidence(
    evidence: Mapping[str, object],
    *,
    plan: Mapping[str, object],
    run_profile: Mapping[str, object],
    samples_artifact: Mapping[str, object],
    rejections_artifact: Mapping[str, object],
) -> None:
    validate_coverage_evidence_record(evidence)
    _validate_plan_identity(plan, run_profile=run_profile)
    identities = _mapping(evidence["identities"])
    expected_fixed = {
        "catalog": {
            "catalog_id": _mapping(plan.get("catalog")).get("catalog_id"),
            "version": _mapping(plan.get("catalog")).get("version"),
            "identity_hash": _mapping(plan.get("catalog")).get(
                "catalog_hash"
            ),
        },
        "coverage_profile": {
            "profile_id": _mapping(
                plan.get("coverage_profile")
            ).get("profile_id"),
            "version": _mapping(
                plan.get("coverage_profile")
            ).get("version"),
            "identity_hash": _mapping(
                plan.get("coverage_profile")
            ).get("profile_hash"),
        },
        "plan": {
            "plan_id": plan.get("plan_id"),
            "identity_hash": plan.get("plan_hash"),
        },
        "scheduler": _scheduler_identity(),
        "run_profile": _run_profile_identity(run_profile),
    }
    for name, expected in expected_fixed.items():
        if dict(_mapping(identities.get(name))) != expected:
            raise ValueError("coverage evidence identity mismatch")
    accepted = _mapping(identities["accepted_samples"])
    rejected = _mapping(identities["rejections"])
    if _artifact_binding(
        accepted.get("artifact"),
        expected_path="samples.jsonl",
    ) != _artifact_binding(
        samples_artifact,
        expected_path="samples.jsonl",
    ):
        raise ValueError("coverage evidence identity mismatch")
    if _artifact_binding(
        rejected.get("artifact"),
        expected_path="rejections.jsonl",
    ) != _artifact_binding(
        rejections_artifact,
        expected_path="rejections.jsonl",
    ):
        raise ValueError("coverage evidence identity mismatch")


def _sample_identity(sample: Mapping[str, object]) -> dict[str, object]:
    assignment = _sample_assignment(sample)
    return {
        "sample_id": str(sample.get("sample_id", "")),
        "sample_hash": canonical_coverage_hash(sample),
        "assignment_id": (
            assignment.get("assignment_id")
            if assignment is not None
            else None
        ),
        "assignment_hash": (
            assignment.get("assignment_hash")
            if assignment is not None
            else None
        ),
        "cell_id": (
            assignment.get("cell_id")
            if assignment is not None
            else None
        ),
        "grounding_hash": _grounding_hash(assignment),
    }


def _rejection_identity(
    rejection: Mapping[str, object],
) -> dict[str, object]:
    assignment, generated = _rejection_assignment(rejection)
    return {
        "candidate_id": str(rejection.get("candidate_id", "")),
        "cause": str(rejection.get("cause", "")),
        "rejection_hash": canonical_coverage_hash(rejection),
        "assignment_id": (
            assignment.get("assignment_id")
            if assignment is not None
            else None
        ),
        "assignment_hash": (
            assignment.get("assignment_hash")
            if assignment is not None
            else None
        ),
        "cell_id": (
            assignment.get("cell_id")
            if assignment is not None
            else None
        ),
        "grounding_hash": _grounding_hash(assignment),
        "generated": generated,
    }


def _assignment_records(
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    tagged_identities = [
        *((identity, True) for identity in samples),
        *((identity, False) for identity in rejections),
    ]
    for identity, accepted in tagged_identities:
        assignment_id = identity.get("assignment_id")
        assignment_hash = identity.get("assignment_hash")
        cell_id = identity.get("cell_id")
        if (
            not isinstance(assignment_id, str)
            or not assignment_id
            or not isinstance(assignment_hash, str)
            or not assignment_hash
            or not isinstance(cell_id, str)
            or not cell_id
        ):
            continue
        record = {
            "assignment_id": assignment_id,
            "assignment_hash": assignment_hash,
            "cell_id": cell_id,
            "grounding_hash": identity.get("grounding_hash"),
            "accepted": accepted,
            "generated": (
                True
                if accepted
                else bool(identity.get("generated"))
            ),
            "rejection_cause": (
                None
                if accepted
                else identity.get("cause")
            ),
        }
        if assignment_id in by_id:
            raise ValueError("coverage assignment identity is duplicated")
        by_id[assignment_id] = record
    return [
        by_id[assignment_id]
        for assignment_id in sorted(by_id)
    ]


def _cell_evidence(
    *,
    plan: CoveragePlan,
    reconciliation: Mapping[str, object],
    assignment_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    raw_cells = reconciliation.get("cells")
    if not isinstance(raw_cells, list):
        raise ValueError("coverage reconciliation cells must be a list")
    records_by_cell: dict[str, list[dict[str, object]]] = {}
    for assignment in assignment_records:
        records_by_cell.setdefault(str(assignment["cell_id"]), []).append(
            assignment
        )
    floors_by_cell = {
        str(item["cell_id"]): _int(item["mandatory_floor"])
        for item in plan.target_distribution
    }
    cells: list[dict[str, object]] = []
    for raw_cell in raw_cells:
        cell = _mapping(raw_cell)
        cell_id = str(cell.get("cell_id", ""))
        assignments = records_by_cell.get(cell_id, [])
        rejection_causes = Counter(
            str(assignment["rejection_cause"])
            for assignment in assignments
            if assignment.get("rejection_cause") is not None
        )
        cells.append(
            {
                "cell_id": cell_id,
                "planned": _int(cell.get("planned")),
                "mandatory_floor": floors_by_cell[cell_id],
                "attempted": len(assignments),
                "generated": sum(
                    int(bool(assignment["generated"]))
                    for assignment in assignments
                ),
                "accepted": _int(cell.get("accepted")),
                "rejected": _int(cell.get("rejected")),
                "remaining": _int(cell.get("remaining")),
                "rejection_causes": dict(sorted(rejection_causes.items())),
                "deficit_reason": cell.get("deficit_reason"),
            }
        )
    return sorted(cells, key=lambda item: str(item["cell_id"]))


def _coverage_counts(
    *,
    plan: CoveragePlan,
    reconciliation: Mapping[str, object],
    assignment_records: list[dict[str, object]],
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
    cells: list[dict[str, object]],
) -> dict[str, object]:
    attempts = _mapping(reconciliation.get("attempts"))
    assigned_samples = sum(
        int(identity.get("assignment_id") is not None)
        for identity in samples
    )
    assigned_rejections = sum(
        int(identity.get("assignment_id") is not None)
        for identity in rejections
    )
    return {
        "target_accepted": plan.target_accepted_sample_count,
        "attempt_ceiling": plan.attempt_ceiling,
        "attempted": _int(attempts.get("issued")),
        "generated": sum(
            int(bool(assignment["generated"]))
            for assignment in assignment_records
        ),
        "accepted": sum(_int(cell["accepted"]) for cell in cells),
        "rejected": sum(_int(cell["rejected"]) for cell in cells),
        "remaining": sum(_int(cell["remaining"]) for cell in cells),
        "unassigned_accepted": len(samples) - assigned_samples,
        "unassigned_rejected": len(rejections) - assigned_rejections,
    }


def _coverage_distributions(
    *,
    assignment_records: list[dict[str, object]],
    samples: list[dict[str, object]],
    rejections: list[dict[str, object]],
) -> dict[str, object]:
    accepted = [
        assignment
        for assignment in assignment_records
        if assignment["accepted"] is True
    ]
    family_counts = Counter(
        str(assignment["cell_id"])
        for assignment in accepted
    )
    grounding_counts = Counter(
        str(assignment["grounding_hash"])
        for assignment in accepted
        if isinstance(assignment.get("grounding_hash"), str)
    )
    reuse_distribution = Counter(grounding_counts.values())
    difficulty_counts = Counter(
        str(_mapping(_mapping(sample.get("task")).get("difficulty")).get("level"))
        for sample in samples
    )
    largest_family_count = max(family_counts.values(), default=0)
    exact_duplicate_count = sum(
        int(rejection.get("cause") == "quality_duplicate")
        for rejection in rejections
    )
    dataset_total = len(samples) + len(rejections)
    return {
        "structural_families": {
            "distinct_count": len(family_counts),
            "largest_family_count": largest_family_count,
            "largest_family_share": (
                largest_family_count / len(accepted)
                if accepted
                else 0.0
            ),
            "accepted_by_cell": dict(sorted(family_counts.items())),
        },
        "grounding_reuse": {
            "distinct_grounding_count": len(grounding_counts),
            "max_accepted_per_grounding": max(
                grounding_counts.values(),
                default=0,
            ),
            "reuse_count_distribution": {
                str(reuse_count): grounding_count
                for reuse_count, grounding_count in sorted(
                    reuse_distribution.items()
                )
            },
        },
        "difficulty": {
            "accepted_by_level": dict(sorted(difficulty_counts.items())),
        },
        "exact_duplicates": {
            "count": exact_duplicate_count,
            "rate": (
                exact_duplicate_count / dataset_total
                if dataset_total
                else 0.0
            ),
        },
    }


def _coverage_fulfillment(
    *,
    reconciliation: Mapping[str, object],
    cells: list[dict[str, object]],
    counts: Mapping[str, object],
) -> dict[str, object]:
    mandatory_fulfilled = all(
        _int(cell["accepted"]) >= _int(cell["mandatory_floor"])
        for cell in cells
    )
    target_fulfilled = (
        reconciliation.get("status") == "complete"
        and _int(counts["remaining"]) == 0
    )
    reasons: list[str] = []
    if not mandatory_fulfilled:
        reasons.append("mandatory_cells_underfilled")
    if not target_fulfilled:
        reasons.append("target_distribution_underfilled")
    if (
        not target_fulfilled
        and _int(counts["attempted"]) >= _int(counts["attempt_ceiling"])
    ):
        reasons.append("attempt_ceiling_exhausted")
    fulfilled = mandatory_fulfilled and target_fulfilled
    return {
        "status": "fulfilled" if fulfilled else "incomplete",
        "mandatory_fulfilled": mandatory_fulfilled,
        "target_fulfilled": target_fulfilled,
        "reasons": reasons,
    }


def _sample_assignment(
    sample: Mapping[str, object],
) -> Mapping[str, object] | None:
    lineage = sample.get("lineage")
    generator = (
        lineage.get("generator")
        if isinstance(lineage, Mapping)
        else None
    )
    assignment = (
        generator.get("coverage_assignment")
        if isinstance(generator, Mapping)
        else None
    )
    return assignment if isinstance(assignment, Mapping) else None


def _rejection_assignment(
    rejection: Mapping[str, object],
) -> tuple[Mapping[str, object] | None, bool]:
    details = rejection.get("details")
    if not isinstance(details, Mapping):
        return None, False
    direct = details.get("coverage_assignment")
    if isinstance(direct, Mapping):
        return direct, False
    role_lineages = details.get("role_lineages")
    generator = (
        role_lineages.get("generator")
        if isinstance(role_lineages, Mapping)
        else None
    )
    assignment = (
        generator.get("coverage_assignment")
        if isinstance(generator, Mapping)
        else None
    )
    if isinstance(assignment, Mapping):
        return assignment, True
    return None, False


def _grounding_hash(
    assignment: Mapping[str, object] | None,
) -> str | None:
    grounding = (
        assignment.get("grounding_scope")
        if isinstance(assignment, Mapping)
        else None
    )
    value = (
        grounding.get("grounding_hash")
        if isinstance(grounding, Mapping)
        else None
    )
    return value if isinstance(value, str) else None


def _scheduler_identity() -> dict[str, object]:
    scheduler = {
        "schema_version": "coverage_scheduler_v1",
        "selection_policy": "mandatory_then_largest_normalized_deficit_v1",
        "tie_break": "cell_id_ascending",
    }
    return {
        "schema_version": scheduler["schema_version"],
        "identity_hash": canonical_coverage_hash(scheduler),
    }


def _run_profile_identity(
    run_profile: Mapping[str, object],
) -> dict[str, object]:
    return {
        **{
            key: run_profile[key]
            for key in (
                "schema_version",
                "profile_id",
                "profile_purpose",
                "generation_mode",
                "config_hash",
            )
            if key in run_profile
        },
        "identity_hash": canonical_coverage_hash(run_profile),
    }


def _expected_external_counts_and_cells(
    *,
    plan: Mapping[str, object],
    assignment_records: list[dict[str, object]],
    sample_identities: list[dict[str, object]],
    rejection_identities: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    raw_distribution = plan.get("target_distribution")
    if not isinstance(raw_distribution, list):
        raise ValueError("coverage evidence identity mismatch")
    plan_cells = {
        str(_mapping(item).get("cell_id")): _mapping(item)
        for item in raw_distribution
    }
    assignments_by_cell: dict[str, list[dict[str, object]]] = {}
    for assignment in assignment_records:
        assignments_by_cell.setdefault(
            str(assignment["cell_id"]),
            [],
        ).append(assignment)
    cells: list[dict[str, object]] = []
    for cell_id in sorted(plan_cells):
        plan_cell = plan_cells[cell_id]
        assignments = assignments_by_cell.get(cell_id, [])
        accepted = sum(
            int(assignment["accepted"] is True)
            for assignment in assignments
        )
        rejected = len(assignments) - accepted
        planned = _int(plan_cell.get("target_count"))
        mandatory_floor = _int(plan_cell.get("mandatory_floor"))
        remaining = max(planned - accepted, 0)
        rejection_causes = Counter(
            str(assignment["rejection_cause"])
            for assignment in assignments
            if assignment.get("rejection_cause") is not None
        )
        cells.append(
            {
                "cell_id": cell_id,
                "planned": planned,
                "mandatory_floor": mandatory_floor,
                "attempted": len(assignments),
                "generated": sum(
                    int(bool(assignment["generated"]))
                    for assignment in assignments
                ),
                "accepted": accepted,
                "rejected": rejected,
                "remaining": remaining,
                "rejection_causes": dict(sorted(rejection_causes.items())),
                "deficit_reason": (
                    None
                    if remaining == 0
                    else (
                        "mandatory_deficit"
                        if accepted < mandatory_floor
                        else "target_deficit"
                    )
                ),
            }
        )
    accepted = sum(_int(cell["accepted"]) for cell in cells)
    rejected = sum(_int(cell["rejected"]) for cell in cells)
    attempted = len(assignment_records)
    counts: dict[str, object] = {
        "target_accepted": _int(plan.get("target_accepted_sample_count")),
        "attempt_ceiling": _int(plan.get("attempt_ceiling")),
        "attempted": attempted,
        "generated": sum(
            int(bool(assignment["generated"]))
            for assignment in assignment_records
        ),
        "accepted": accepted,
        "rejected": rejected,
        "remaining": sum(_int(cell["remaining"]) for cell in cells),
        "unassigned_accepted": sum(
            int(identity.get("assignment_id") is None)
            for identity in sample_identities
        ),
        "unassigned_rejected": sum(
            int(identity.get("assignment_id") is None)
            for identity in rejection_identities
        ),
    }
    return counts, cells


def _validated_cell(value: object) -> dict[str, object]:
    cell = _mapping(value)
    expected_keys = {
        "cell_id",
        "planned",
        "mandatory_floor",
        "attempted",
        "generated",
        "accepted",
        "rejected",
        "remaining",
        "rejection_causes",
        "deficit_reason",
    }
    if set(cell) != expected_keys:
        raise ValueError("coverage evidence cell contains unsupported keys")
    cell_id = cell.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("coverage evidence cell id is invalid")
    for field in (
        "planned",
        "mandatory_floor",
        "attempted",
        "generated",
        "accepted",
        "rejected",
        "remaining",
    ):
        _int(cell.get(field))
    if _int(cell["attempted"]) != (
        _int(cell["accepted"]) + _int(cell["rejected"])
    ):
        raise ValueError("coverage evidence cell attempts do not reconcile")
    if _int(cell["accepted"]) + _int(cell["remaining"]) != _int(
        cell["planned"]
    ):
        raise ValueError("coverage evidence cell accepted count does not reconcile")
    if not (
        _int(cell["accepted"])
        <= _int(cell["generated"])
        <= _int(cell["attempted"])
    ):
        raise ValueError("coverage evidence cell generated count does not reconcile")
    rejection_causes = _mapping(cell.get("rejection_causes"))
    from synthesis.contracts import REJECTION_CAUSES

    if any(
        not isinstance(cause, str)
        or cause not in REJECTION_CAUSES
        or _int(count) < 1
        for cause, count in rejection_causes.items()
    ):
        raise ValueError("coverage evidence rejection causes are invalid")
    if sum(_int(count) for count in rejection_causes.values()) != _int(
        cell["rejected"]
    ):
        raise ValueError("coverage evidence rejection causes do not reconcile")
    expected_deficit = (
        None
        if _int(cell["remaining"]) == 0
        else (
            "mandatory_deficit"
            if _int(cell["accepted"]) < _int(cell["mandatory_floor"])
            else "target_deficit"
        )
    )
    if cell.get("deficit_reason") != expected_deficit:
        raise ValueError("coverage evidence deficit reason is invalid")
    return dict(cell)


def _validate_plan_identity(
    plan: Mapping[str, object],
    *,
    run_profile: Mapping[str, object],
) -> None:
    expected_keys = {
        "schema_version",
        "plan_id",
        "plan_hash",
        "domain_id",
        "catalog",
        "coverage_profile",
        "selected_features",
        "target_accepted_sample_count",
        "target_candidate_count",
        "target_distribution",
        "attempt_ceiling",
        "policies",
        "cell_requirements",
        "overrides",
        "admitted_capacity",
    }
    if set(plan) != expected_keys or plan.get("schema_version") != (
        "coverage_plan_v1"
    ):
        raise ValueError("coverage evidence identity mismatch")
    plan_hash = _hash_value(plan.get("plan_hash"))
    expected_hash = canonical_coverage_hash(
        {
            key: value
            for key, value in plan.items()
            if key not in {"plan_id", "plan_hash"}
        }
    )
    if plan_hash != expected_hash or plan.get("plan_id") != (
        "coverage_plan_" + plan_hash.removeprefix(_SHA256_PREFIX)[:16]
    ):
        raise ValueError("coverage evidence identity mismatch")

    from synthesis.coverage_registry import resolve_domain_coverage_planning

    domain_id = plan.get("domain_id")
    if not isinstance(domain_id, str):
        raise ValueError("coverage evidence identity mismatch")
    planning = resolve_domain_coverage_planning(domain_id)
    catalog = _mapping(plan.get("catalog"))
    if (
        catalog.get("catalog_id") != planning.catalog.catalog_id
        or catalog.get("version") != planning.catalog.version
        or catalog.get("catalog_hash")
        != canonical_coverage_hash(planning.catalog.canonical())
    ):
        raise ValueError("coverage evidence identity mismatch")
    coverage_profile = _mapping(plan.get("coverage_profile"))
    profile_id = coverage_profile.get("profile_id")
    profile_version = coverage_profile.get("version")
    if not isinstance(profile_id, str) or not isinstance(
        profile_version,
        str,
    ):
        raise ValueError("coverage evidence identity mismatch")
    resolved_profile = planning.resolve_profile(profile_id, profile_version)
    if coverage_profile.get("profile_hash") != canonical_coverage_hash(
        resolved_profile.canonical()
    ):
        raise ValueError("coverage evidence identity mismatch")

    selected_profile = _mapping(run_profile.get("coverage_profile"))
    if (
        selected_profile.get("profile_id") != profile_id
        or selected_profile.get("version") != profile_version
        or selected_profile.get("target_accepted_sample_count")
        != plan.get("target_accepted_sample_count")
        or run_profile.get("target_candidate_count")
        != plan.get("target_candidate_count")
    ):
        raise ValueError("coverage evidence identity mismatch")


def _artifact_binding(
    value: object,
    *,
    expected_path: str,
) -> dict[str, object]:
    artifact = _mapping(value)
    if set(artifact) != {"path", "sha256", "byte_count"}:
        raise ValueError("coverage evidence artifact binding is invalid")
    if artifact.get("path") != expected_path:
        raise ValueError("coverage evidence artifact path is invalid")
    digest = _hash_value(artifact.get("sha256"))
    byte_count = _int(artifact.get("byte_count"))
    return {
        "path": expected_path,
        "sha256": digest,
        "byte_count": byte_count,
    }


def _jsonl_artifact_binding(
    path: str,
    records: list[dict[str, object]],
) -> dict[str, object]:
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8")
    return {
        "path": path,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "byte_count": len(content),
    }


def _validate_distributions(
    value: object,
    *,
    counts: Mapping[str, object],
) -> None:
    distributions = _mapping(value)
    if set(distributions) != {
        "structural_families",
        "grounding_reuse",
        "difficulty",
        "exact_duplicates",
    }:
        raise ValueError("coverage evidence distributions are invalid")
    structural = _mapping(distributions["structural_families"])
    if set(structural) != {
        "distinct_count",
        "largest_family_count",
        "largest_family_share",
        "accepted_by_cell",
    }:
        raise ValueError("coverage evidence structural families are invalid")
    accepted_by_cell = _mapping(structural.get("accepted_by_cell"))
    for cell_id, count in accepted_by_cell.items():
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError(
                "coverage evidence structural families are invalid"
            )
        _int(count)
    if sum(_int(count) for count in accepted_by_cell.values()) != _int(
        counts["accepted"]
    ):
        raise ValueError("coverage evidence structural families do not reconcile")
    largest_family_count = max(
        (_int(count) for count in accepted_by_cell.values()),
        default=0,
    )
    if _int(structural.get("distinct_count")) != len(accepted_by_cell):
        raise ValueError("coverage evidence structural families do not reconcile")
    if _int(structural.get("largest_family_count")) != largest_family_count:
        raise ValueError("coverage evidence structural families do not reconcile")
    expected_largest_share = (
        largest_family_count / _int(counts["accepted"])
        if _int(counts["accepted"])
        else 0.0
    )
    if _rate_value(structural.get("largest_family_share")) != (
        expected_largest_share
    ):
        raise ValueError("coverage evidence structural families do not reconcile")

    grounding = _mapping(distributions["grounding_reuse"])
    if set(grounding) != {
        "distinct_grounding_count",
        "max_accepted_per_grounding",
        "reuse_count_distribution",
    }:
        raise ValueError("coverage evidence grounding reuse is invalid")
    reuse_distribution = _mapping(grounding.get("reuse_count_distribution"))
    accepted_from_reuse = 0
    distinct_from_reuse = 0
    maximum_reuse = 0
    for reuse_count, grounding_count in reuse_distribution.items():
        if (
            not isinstance(reuse_count, str)
            or not reuse_count.isdigit()
            or int(reuse_count) < 1
        ):
            raise ValueError("coverage evidence grounding reuse is invalid")
        grounding_count_value = _int(grounding_count)
        if grounding_count_value < 1:
            raise ValueError("coverage evidence grounding reuse is invalid")
        accepted_from_reuse += int(reuse_count) * grounding_count_value
        distinct_from_reuse += grounding_count_value
        maximum_reuse = max(maximum_reuse, int(reuse_count))
    if (
        accepted_from_reuse != _int(counts["accepted"])
        or _int(grounding.get("distinct_grounding_count"))
        != distinct_from_reuse
        or _int(grounding.get("max_accepted_per_grounding"))
        != maximum_reuse
    ):
        raise ValueError("coverage evidence grounding reuse does not reconcile")

    difficulty = _mapping(distributions["difficulty"])
    if set(difficulty) != {"accepted_by_level"}:
        raise ValueError("coverage evidence difficulty is invalid")
    accepted_by_level = _mapping(difficulty.get("accepted_by_level"))
    for level, count in accepted_by_level.items():
        if not isinstance(level, str) or not level:
            raise ValueError("coverage evidence difficulty is invalid")
        _int(count)
    if sum(_int(count) for count in accepted_by_level.values()) != (
        _int(counts["accepted"]) + _int(counts["unassigned_accepted"])
    ):
        raise ValueError("coverage evidence difficulty counts do not reconcile")

    duplicates = _mapping(distributions["exact_duplicates"])
    if set(duplicates) != {"count", "rate"}:
        raise ValueError("coverage evidence exact duplicates are invalid")
    duplicate_count = _int(duplicates.get("count"))
    membership_count = sum(
        _int(counts[field])
        for field in (
            "accepted",
            "rejected",
            "unassigned_accepted",
            "unassigned_rejected",
        )
    )
    if duplicate_count > (
        _int(counts["rejected"]) + _int(counts["unassigned_rejected"])
    ):
        raise ValueError("coverage evidence exact duplicates do not reconcile")
    expected_duplicate_rate = (
        duplicate_count / membership_count
        if membership_count
        else 0.0
    )
    if _rate_value(duplicates.get("rate")) != expected_duplicate_rate:
        raise ValueError("coverage evidence exact duplicates do not reconcile")


def _validate_fulfillment(
    value: object,
    *,
    cells: list[dict[str, object]],
    counts: Mapping[str, object],
) -> None:
    fulfillment = _mapping(value)
    if set(fulfillment) != {
        "status",
        "mandatory_fulfilled",
        "target_fulfilled",
        "reasons",
    }:
        raise ValueError("coverage evidence fulfillment is invalid")
    mandatory_fulfilled = all(
        _int(cell["accepted"]) >= _int(cell["mandatory_floor"])
        for cell in cells
    )
    target_fulfilled = _int(counts["remaining"]) == 0
    if fulfillment.get("mandatory_fulfilled") is not mandatory_fulfilled:
        raise ValueError("coverage evidence mandatory fulfillment is invalid")
    if fulfillment.get("target_fulfilled") is not target_fulfilled:
        raise ValueError("coverage evidence target fulfillment is invalid")
    expected_status = (
        "fulfilled"
        if mandatory_fulfilled and target_fulfilled
        else "incomplete"
    )
    if fulfillment.get("status") != expected_status:
        raise ValueError("coverage evidence fulfillment status is invalid")
    _validate_fulfillment_reasons(
        fulfillment.get("reasons"),
        mandatory_fulfilled=mandatory_fulfilled,
        target_fulfilled=target_fulfilled,
        counts=counts,
    )


def _validated_counts(value: object) -> Mapping[str, object]:
    counts = _mapping(value)
    if set(counts) != {
        "target_accepted",
        "attempt_ceiling",
        "attempted",
        "generated",
        "accepted",
        "rejected",
        "remaining",
        "unassigned_accepted",
        "unassigned_rejected",
    }:
        raise ValueError("coverage evidence counts are invalid")
    for count in counts.values():
        _int(count)
    if _int(counts["attempted"]) != (
        _int(counts["accepted"]) + _int(counts["rejected"])
    ):
        raise ValueError("coverage evidence attempted count does not reconcile")
    if _int(counts["accepted"]) + _int(counts["remaining"]) != _int(
        counts["target_accepted"]
    ):
        raise ValueError("coverage evidence accepted count does not reconcile")
    if _int(counts["attempted"]) > _int(counts["attempt_ceiling"]):
        raise ValueError("coverage evidence exceeds the attempt ceiling")
    if not (
        _int(counts["accepted"])
        <= _int(counts["generated"])
        <= _int(counts["attempted"])
    ):
        raise ValueError("coverage evidence generated count does not reconcile")
    return counts


def _validate_fulfillment_reasons(
    value: object,
    *,
    mandatory_fulfilled: bool,
    target_fulfilled: bool,
    counts: Mapping[str, object],
) -> None:
    expected: list[str] = []
    if not mandatory_fulfilled:
        expected.append("mandatory_cells_underfilled")
    if not target_fulfilled:
        expected.append("target_distribution_underfilled")
    if (
        not target_fulfilled
        and _int(counts["attempted"]) >= _int(counts["attempt_ceiling"])
    ):
        expected.append("attempt_ceiling_exhausted")
    if value != expected:
        raise ValueError("coverage evidence fulfillment reasons are invalid")


def _hash_value(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_SHA256_PREFIX)
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError("coverage evidence hash is invalid")
    return value


def _rate_value(value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError("coverage evidence rate is invalid")
    return float(value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("coverage evidence value must be an object")
    return value


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("coverage evidence count must be non-negative")
    return value
