from __future__ import annotations

import unittest


class DatasetReleaseTest(unittest.TestCase):
    def test_release_candidate_with_small_undercovered_evidence_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(
                profile_purpose="release_candidate",
                accepted_count=2,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=2,
                rejected=1,
                task_types=("lookup_contact_email", "contact_followup"),
                tool_combinations=(
                    "lookup_contact_email",
                    "lookup_contact_email > record_contact_followup",
                ),
            ),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(
            report["decisions"]["dataset_release"]["status"],
            "insufficient_evidence",
        )
        self.assertEqual(
            report["release_completeness"]["decision"]["status"],
            "insufficient_evidence",
        )
        self.assertIn(
            "release_completeness",
            report["decisions"]["dataset_release"]["triggered_by"],
        )

    def test_release_candidate_with_complete_evidence_passes_release_admission(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ),
                tool_combinations=(
                    "lookup_contact_email",
                    "lookup_contact_email > record_contact_followup",
                ),
            ),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "passed")
        self.assertEqual(report["release_completeness"]["decision"]["status"], "passed")

    def test_mobile_release_candidate_with_contacts_evaluation_domain_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_mobile_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ),
                tool_combinations=(
                    "lookup_contact_email",
                    "lookup_contact_email > record_contact_followup",
                ),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="contacts_fixture",
                suite_id="contacts_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        decision = report["decisions"]["dataset_release"]
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("evaluation_domain", decision["triggered_by"])
        self.assertIn(
            "evaluation domain contacts_fixture does not match manifest domain mobile_messages_fixture",
            decision["reasons"],
        )

    def test_mobile_release_candidate_with_mobile_evaluation_domain_passes(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_mobile_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ),
                tool_combinations=(
                    "lookup_contact_email",
                    "lookup_contact_email > record_contact_followup",
                ),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="mobile_messages_fixture",
                suite_id="mobile_messages_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "passed")

    def test_workspace_release_candidate_with_workspace_evaluation_domain_passes(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_workspace_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "workspace_item_lookup",
                    "workspace_task_creation",
                    "workspace_comment_update",
                    "workspace_branch_fallback",
                ),
                tool_combinations=(
                    "search_workspace_items",
                    "search_workspace_items > create_workspace_task",
                    "search_workspace_items > add_workspace_comment",
                ),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="workspace_tasks_fixture",
                suite_id="workspace_tasks_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "passed")

    def test_workspace_release_candidate_with_mobile_evaluation_domain_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_workspace_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=1,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "workspace_item_lookup",
                    "workspace_task_creation",
                    "workspace_comment_update",
                    "workspace_branch_fallback",
                ),
                tool_combinations=(
                    "search_workspace_items",
                    "search_workspace_items > create_workspace_task",
                    "search_workspace_items > add_workspace_comment",
                ),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="mobile_messages_fixture",
                suite_id="mobile_messages_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        decision = report["decisions"]["dataset_release"]
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIn("evaluation_domain", decision["triggered_by"])
        self.assertIn(
            "evaluation domain mobile_messages_fixture does not match manifest domain workspace_tasks_fixture",
            decision["reasons"],
        )

    def test_diagnostic_profile_is_ineligible_for_release(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="diagnostic_probe"),
            quality_report=_quality_report(),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "ineligible")

    def test_activated_async_orchestration_blocks_release(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="release_candidate"),
            quality_report=_quality_report(),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(
                profile_promotion_status="passed",
                async_status="activate",
            ),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "blocked")

    def test_activated_semantic_duplicate_detection_blocks_release(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="release_candidate"),
            quality_report=_quality_report(),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(
                profile_promotion_status="passed",
                semantic_status="activate",
            ),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "blocked")

    def test_failed_profile_promotion_fails_release(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="release_candidate"),
            quality_report=_quality_report(),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="failed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "failed")

    def test_missing_evaluation_evidence_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="release_candidate"),
            quality_report=_quality_report(),
            evaluation_report=None,
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(
            report["decisions"]["dataset_release"]["status"],
            "insufficient_evidence",
        )

    def test_missing_release_artifact_reference_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        manifest = _manifest(profile_purpose="release_candidate")
        manifest["artifacts"].pop("evaluation_report")

        report = build_dataset_release_report(
            manifest=manifest,
            quality_report=_quality_report(),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(
            report["decisions"]["dataset_release"]["status"],
            "insufficient_evidence",
        )

    def test_source_policy_rejection_rate_above_zero_fails_release(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_manifest(profile_purpose="release_candidate", rejected_count=1),
            quality_report=_quality_report(rejected=1, source_policy_rejections=1),
            evaluation_report=_evaluation_report(status="passed"),
            profile_decision_report=_profile_decision_report(profile_promotion_status="passed"),
        )

        self.assertEqual(report["decisions"]["dataset_release"]["status"], "failed")


def _manifest(
    *,
    profile_purpose: str,
    accepted_count: int = 3,
    rejected_count: int = 0,
) -> dict[str, object]:
    return {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_release",
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
            "evaluation_report": "evaluation_report.json",
            "profile_decision_report": "profile_decision_report.json",
        },
        "run_profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "release_profile",
            "generation_mode": "foundation_fixture",
            "profile_purpose": profile_purpose,
            "target_candidate_count": None,
            "config_hash": "sha256:" + "a" * 64,
            "enabled_features": [],
        },
    }


def _mobile_manifest(
    *,
    profile_purpose: str,
    accepted_count: int = 3,
    rejected_count: int = 0,
) -> dict[str, object]:
    manifest = _manifest(
        profile_purpose=profile_purpose,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )
    run_profile = manifest["run_profile"]
    assert isinstance(run_profile, dict)
    run_profile.update(
        {
            "schema_version": "run_profile_v2",
            "profile_id": "profile_local_mobile_messages",
            "generation_mode": "mobile_fixture",
            "seed": {"domain": "mobile_messages_fixture"},
        }
    )
    return manifest


def _workspace_manifest(
    *,
    profile_purpose: str,
    accepted_count: int = 3,
    rejected_count: int = 0,
) -> dict[str, object]:
    manifest = _manifest(
        profile_purpose=profile_purpose,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )
    run_profile = manifest["run_profile"]
    assert isinstance(run_profile, dict)
    run_profile.update(
        {
            "schema_version": "run_profile_v1",
            "profile_id": "workspace_tasks_fixture",
            "generation_mode": "workspace_fixture",
            "seed": {"domain": "workspace_tasks_fixture"},
        }
    )
    return manifest


def _quality_report(
    *,
    accepted: int = 3,
    rejected: int = 0,
    source_policy_rejections: int = 0,
    task_types: tuple[str, ...] = (
        "lookup_contact_email",
        "contact_followup",
        "contact_branch_fallback",
    ),
    tool_combinations: tuple[str, ...] = (
        "lookup_contact_email",
        "lookup_contact_email > record_contact_followup",
    ),
) -> dict[str, object]:
    total = accepted + rejected
    accepted_per_task_type = accepted // len(task_types) if task_types else 0
    accepted_per_tool_combination = accepted // len(tool_combinations) if tool_combinations else 0
    return {
        "schema_version": "quality_report_v1",
        "dataset_version": "dataset_release",
        "counts": {
            "total": total,
            "accepted": accepted,
            "rejected": rejected,
        },
        "rates": {
            "success_rate": accepted / total,
            "executable_rate": 1.0,
        },
        "rejection_causes": (
            {"source_policy_rejected": source_policy_rejections}
            if source_policy_rejections
            else {}
        ),
        "slices": {
            "task_type": {
                task_type: {
                    "accepted": accepted_per_task_type,
                    "rejected": 0,
                    "total": accepted_per_task_type,
                    "success_rate": 1.0,
                }
                for task_type in task_types
            },
            "tool_combination": {
                tool_combination: {
                    "accepted": accepted_per_tool_combination,
                    "rejected": 0,
                    "total": accepted_per_tool_combination,
                    "success_rate": 1.0,
                }
                for tool_combination in tool_combinations
            },
        },
    }


def _evaluation_report(*, status: str) -> dict[str, object]:
    return {
        "schema_version": "evaluation_report_v1",
        "decision": {
            "status": status,
            "reasons": ["held-out evaluation passed"],
            "triggered_by": ["pass_rate"],
        },
    }


def _domain_evaluation_report(
    *,
    status: str,
    domain_id: str,
    suite_id: str,
) -> dict[str, object]:
    report = _evaluation_report(status=status)
    report["suite"] = {
        "suite_id": suite_id,
        "suite_version": suite_id,
        "domain_id": domain_id,
        "task_count": 5,
    }
    report["domain"] = {"domain_id": domain_id, "source": "test"}
    return report


def _profile_decision_report(
    *,
    profile_promotion_status: str,
    async_status: str = "defer",
    semantic_status: str = "defer",
) -> dict[str, object]:
    return {
        "schema_version": "profile_decision_report_v1",
        "decisions": {
            "async_orchestration": {
                "status": async_status,
                "reasons": ["async decision"],
                "triggered_by": [],
            },
            "semantic_duplicate_detection": {
                "status": semantic_status,
                "reasons": ["semantic duplicate decision"],
                "triggered_by": [],
            },
            "profile_promotion": {
                "status": profile_promotion_status,
                "reasons": ["profile promotion decision"],
                "triggered_by": [],
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
