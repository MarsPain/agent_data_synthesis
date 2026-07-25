from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class MutationCalibrationExportTest(unittest.TestCase):
    def test_export_is_deterministic_balanced_and_freezes_held_out_cases(self) -> None:
        from synthesis.mutation_calibration import (
            build_mutation_calibration_review_packet,
            write_mutation_calibration_review_packet,
        )

        first = build_mutation_calibration_review_packet(
            corpus_version="mutation_calibration_corpus_v1"
        )
        second = build_mutation_calibration_review_packet(
            corpus_version="mutation_calibration_corpus_v1"
        )

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "mutation_calibration_review_packet_v1")
        self.assertEqual(first["review_status"], "pending_human_review")
        self.assertEqual(first["counts"]["cases"], 200)
        self.assertGreaterEqual(
            first["counts"]["unsupported_or_adversarial"],
            100,
        )
        self.assertEqual(first["counts"]["held_out"], 60)
        self.assertEqual(
            set(first["coverage"]["domains"]),
            {
                "contacts_fixture",
                "mobile_messages_fixture",
                "workspace_tasks_fixture",
            },
        )
        self.assertEqual(
            set(first["coverage"]["actions"]),
            {
                "contact_followup_record",
                "mobile_draft_reply_create",
                "mobile_reminder_create",
                "workspace_comment_add",
                "workspace_task_create",
            },
        )
        self.assertEqual(set(first["coverage"]["actions"].values()), {40})
        self.assertEqual(
            set(first["coverage"]["task_types"]),
            {
                "contact_followup",
                "mobile_draft_reply",
                "mobile_message_to_reminder",
                "mobile_reminder_creation",
                "workspace_comment_update",
                "workspace_task_creation",
            },
        )
        self.assertEqual(
            set(first["coverage"]["scenario_tags"]),
            {
                "conditional_authorization",
                "deterministic_derivations",
                "false_provenance",
                "legitimate_defaults",
                "literal_support",
                "missing_requester_content",
                "negation",
                "parameter_smuggling",
                "prompt_injection",
                "semantic_paraphrase",
            },
        )
        self.assertEqual(len({case["case_id"] for case in first["cases"]}), 200)
        self.assertTrue(
            all(
                case["case_hash"].startswith("sha256:")
                and case["normalized_input"]["instruction"]
                == " ".join(case["normalized_input"]["instruction"].split())
                for case in first["cases"]
            )
        )
        for scenario, expected_kind in (
            ("legitimate_defaults", "declared_default"),
            ("deterministic_derivations", "deterministic_derivation"),
        ):
            scenario_cases = [
                case
                for case in first["cases"]
                if case["scenario_tags"] == [scenario]
            ]
            self.assertTrue(
                all(
                    len(
                        case["normalized_input"]["validated_provenance"][
                            "supplemental_evidence_references"
                        ]
                    )
                    == 1
                    and case["normalized_input"]["referenced_evidence"][
                        case["normalized_input"]["validated_provenance"][
                            "supplemental_evidence_references"
                        ][0]
                    ]["kind"]
                    == expected_kind
                    for case in scenario_cases
                )
            )
        false_provenance_cases = [
            case
            for case in first["cases"]
            if case["scenario_tags"] == ["false_provenance"]
        ]
        self.assertTrue(
            all(
                any(
                    case["normalized_input"]["validated_provenance"][
                        "argument_origins"
                    ][argument["name"]]
                    not in argument["allowed_origins"]
                    for argument in case["action_policy"]["arguments"]
                    if argument["requester_controlled"]
                )
                for case in false_provenance_cases
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            first_dir = Path(tmpdir) / "first"
            second_dir = Path(tmpdir) / "second"
            first_paths = write_mutation_calibration_review_packet(
                first_dir,
                corpus_version="mutation_calibration_corpus_v1",
            )
            second_paths = write_mutation_calibration_review_packet(
                second_dir,
                corpus_version="mutation_calibration_corpus_v1",
            )

            self.assertEqual(
                first_paths.packet_path.read_bytes(),
                second_paths.packet_path.read_bytes(),
            )
            self.assertEqual(
                first_paths.freeze_path.read_bytes(),
                second_paths.freeze_path.read_bytes(),
            )
            freeze = json.loads(first_paths.freeze_path.read_text(encoding="utf-8"))
            self.assertEqual(
                freeze["schema_version"],
                "mutation_calibration_split_freeze_v1",
            )
            self.assertEqual(
                freeze["freeze_stage"],
                "before_prompt_or_policy_tuning",
            )
            self.assertEqual(freeze["packet_hash"], first["packet_hash"])
            self.assertEqual(len(freeze["held_out_case_ids"]), 60)
            self.assertTrue(freeze["freeze_hash"].startswith("sha256:"))

    def test_exported_policy_snapshots_match_current_domain_policies(self) -> None:
        from synthesis.contact_mutations import contact_followup_mutation_policies
        from synthesis.environments import ContactEnvironment
        from synthesis.mobile_environment import MobileMessagesEnvironment
        from synthesis.mobile_mutations import mobile_mutation_policies
        from synthesis.mutation_calibration import (
            build_mutation_calibration_review_packet,
        )
        from synthesis.workspace_environment import WorkspaceTasksEnvironment
        from synthesis.workspace_tasks import workspace_mutation_policies

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_policies = [
                *contact_followup_mutation_policies(
                    ContactEnvironment.create_fixture(root / "contacts")
                ),
                *mobile_mutation_policies(
                    MobileMessagesEnvironment.create_fixture(root / "mobile")
                ),
                *workspace_mutation_policies(
                    WorkspaceTasksEnvironment.create_fixture(root / "workspace")
                ),
            ]
        expected = {
            (policy.domain_id, policy.task_type, policy.action_type):
            self._runtime_policy_snapshot(policy)
            for policy in runtime_policies
        }
        packet = build_mutation_calibration_review_packet(
            corpus_version="mutation_calibration_corpus_v1"
        )
        observed = {}
        for case in packet["cases"]:
            policy = dict(case["action_policy"])
            observed[
                (case["domain_id"], case["task_type"], case["action_type"])
            ] = policy

        self.assertEqual(observed, expected)

    @staticmethod
    def _runtime_policy_snapshot(policy) -> dict[str, object]:
        return {
            "schema_version": policy.schema_version,
            "domain_id": policy.domain_id,
            "task_type": policy.task_type,
            "action_type": policy.action_type,
            "tool_name": policy.tool_name,
            "operational_defaults": [
                {"field": field, "declaration_id": declaration_id}
                for field, declaration_id in policy.operational_defaults
            ],
            "deterministic_derivations": [
                {"field": field, "declaration_id": declaration_id}
                for field, declaration_id
                in policy.deterministic_derivations
            ],
            "arguments": [
                {
                    "name": argument.name,
                    "requester_controlled": argument.requester_controlled,
                    "allowed_origins": list(argument.allowed_origins),
                    "required": argument.required,
                    "observation_tool": argument.observation_tool,
                    "observation_field": argument.observation_field,
                    "observation_bindings": [
                        {
                            "arguments_hash": arguments_hash,
                            "value_hash": value_hash,
                        }
                        for arguments_hash, value_hash
                        in argument.observation_bindings
                    ],
                    "binding_argument_names": list(
                        argument.binding_argument_names
                    ),
                    "binding_token_aliases": [
                        list(alias) for alias in argument.binding_token_aliases
                    ],
                }
                for argument in policy.arguments
            ],
        }


class MutationCalibrationImportTest(unittest.TestCase):
    def test_valid_complete_human_import_produces_reviewed_hash_bound_corpus(self) -> None:
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            labels_path = root / "human_labels.jsonl"
            labels = self._labels(packet)
            labels_path.write_text(
                "".join(
                    json.dumps(label, sort_keys=True, separators=(",", ":")) + "\n"
                    for label in labels
                ),
                encoding="utf-8",
            )

            first_output = root / "reviewed-first.json"
            second_output = root / "reviewed-second.json"
            first = import_human_reviewed_mutation_calibration_corpus(
                packet_path=paths.packet_path,
                freeze_path=paths.freeze_path,
                labels_path=labels_path,
                output_path=first_output,
            )
            second = import_human_reviewed_mutation_calibration_corpus(
                packet_path=paths.packet_path,
                freeze_path=paths.freeze_path,
                labels_path=labels_path,
                output_path=second_output,
            )

            self.assertEqual(first, second)
            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(
                first["schema_version"],
                "reviewed_mutation_calibration_corpus_v1",
            )
            self.assertEqual(first["review_status"], "human_reviewed")
            self.assertEqual(first["counts"]["cases"], 200)
            self.assertEqual(first["counts"]["held_out"], 60)
            self.assertEqual(first["counts"]["ground_truth"]["supported"], 80)
            self.assertEqual(first["counts"]["ground_truth"]["uncertain"], 20)
            self.assertEqual(first["counts"]["ground_truth"]["unsupported"], 100)
            self.assertEqual(first["source"]["packet_hash"], packet["packet_hash"])
            self.assertTrue(first["source"]["freeze_hash"].startswith("sha256:"))
            self.assertTrue(first["corpus_hash"].startswith("sha256:"))
            self.assertTrue(
                all(
                    reviewed["human_review"]["reviewer_provenance"]["review_method"]
                    == "human_direct_review"
                    for reviewed in first["cases"]
                )
            )

    def test_import_rejects_duplicate_cases_and_duplicate_labels(self) -> None:
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            labels = self._labels(packet)
            labels_path = root / "labels.jsonl"
            self._write_labels(labels_path, labels)

            duplicate_packet = json.loads(json.dumps(packet))
            duplicate_packet["cases"].append(duplicate_packet["cases"][0])
            duplicate_packet_path = root / "duplicate-packet.json"
            duplicate_packet_path.write_text(
                json.dumps(duplicate_packet),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "duplicate mutation calibration case",
            ):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=duplicate_packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            self._write_labels(labels_path, [*labels, labels[0]])
            with self.assertRaisesRegex(
                ValueError,
                "duplicate mutation calibration human label",
            ):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    def test_import_rejects_changed_held_out_assignment(self) -> None:
        from synthesis.mutation_admission import canonical_hash
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            case = next(case for case in packet["cases"] if case["split"] == "tuning")
            case["split"] = "held_out"
            scenario = case["scenario_tags"][0]
            variant = case["case_id"].rsplit(":", 1)[-1]
            case["hashes"]["split_assignment"] = canonical_hash(
                {
                    "corpus_version": packet["corpus_version"],
                    "action_type": case["action_type"],
                    "scenario": scenario,
                    "variant": variant,
                    "split": "held_out",
                }
            )
            case["case_hash"] = canonical_hash(
                {key: value for key, value in case.items() if key != "case_hash"}
            )
            packet["counts"]["held_out"] += 1
            packet["packet_hash"] = canonical_hash(
                {key: value for key, value in packet.items() if key != "packet_hash"}
            )
            changed_packet_path = root / "changed-split.json"
            changed_packet_path.write_text(json.dumps(packet), encoding="utf-8")
            labels_path = root / "labels.jsonl"
            self._write_labels(labels_path, self._labels(packet))

            with self.assertRaisesRegex(
                ValueError,
                "held-out assignment changed",
            ):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=changed_packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    def test_import_rejects_invalid_missing_or_non_human_label_provenance(self) -> None:
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            valid_labels = self._labels(packet)
            labels_path = root / "labels.jsonl"

            invalid_label = json.loads(json.dumps(valid_labels))
            invalid_label[0]["ground_truth"] = "mostly_supported"
            self._write_labels(labels_path, invalid_label)
            with self.assertRaisesRegex(ValueError, "ground_truth is invalid"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            missing_provenance = json.loads(json.dumps(valid_labels))
            missing_provenance[0].pop("reviewer_provenance")
            self._write_labels(labels_path, missing_provenance)
            with self.assertRaisesRegex(ValueError, "label keys are invalid"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            generated_label = json.loads(json.dumps(valid_labels))
            generated_label[0]["reviewer_provenance"][
                "review_method"
            ] = "judge_generated"
            self._write_labels(labels_path, generated_label)
            with self.assertRaisesRegex(
                ValueError,
                "generated or judge-produced labels cannot be human ground truth",
            ):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    def test_import_rejects_incomplete_labels_and_post_freeze_input_changes(self) -> None:
        from synthesis.mutation_admission import canonical_hash
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            labels_path = root / "labels.jsonl"
            self._write_labels(labels_path, self._labels(packet)[:-1])
            with self.assertRaisesRegex(ValueError, "human labels are incomplete"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            changed_packet = json.loads(json.dumps(packet))
            case = changed_packet["cases"][0]
            case["normalized_input"]["instruction"] += " Changed after freeze."
            case["hashes"]["normalized_input"] = canonical_hash(
                case["normalized_input"]
            )
            case["case_hash"] = canonical_hash(
                {key: value for key, value in case.items() if key != "case_hash"}
            )
            changed_packet["packet_hash"] = canonical_hash(
                {
                    key: value
                    for key, value in changed_packet.items()
                    if key != "packet_hash"
                }
            )
            changed_packet_path = root / "changed-input.json"
            changed_packet_path.write_text(
                json.dumps(changed_packet),
                encoding="utf-8",
            )
            self._write_labels(labels_path, self._labels(changed_packet))
            with self.assertRaisesRegex(ValueError, "post-freeze input change"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=changed_packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    def test_import_rejects_bound_case_and_freeze_tampering(self) -> None:
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            labels_path = root / "labels.jsonl"
            self._write_labels(labels_path, self._labels(packet))

            packet_mutations = (
                (
                    "action policy",
                    lambda changed: changed["cases"][0]["action_policy"].update(
                        {"schema_version": "changed_policy_v1"}
                    ),
                    "action policy is inconsistent",
                ),
                (
                    "evidence",
                    lambda changed: changed["cases"][0]["normalized_input"][
                        "referenced_evidence"
                    ].pop("evidence.action"),
                    "evidence references are inconsistent",
                ),
                (
                    "criticality",
                    lambda changed: changed["cases"][0].update(
                        {"criticality": "critical"}
                    ),
                    "criticality is inconsistent",
                ),
            )
            for name, mutate, message in packet_mutations:
                with self.subTest(contamination=name):
                    changed = json.loads(json.dumps(packet))
                    mutate(changed)
                    changed_path = root / f"changed-{name.replace(' ', '-')}.json"
                    changed_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        import_human_reviewed_mutation_calibration_corpus(
                            packet_path=changed_path,
                            freeze_path=paths.freeze_path,
                            labels_path=labels_path,
                            output_path=root / "reviewed.json",
                        )

            freeze = json.loads(paths.freeze_path.read_text(encoding="utf-8"))
            freeze["freeze_hash"] = f"sha256:{'0' * 64}"
            changed_freeze_path = root / "changed-freeze.json"
            changed_freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "split freeze hash mismatch"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=changed_freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    def test_import_rejects_label_hash_version_and_extra_case_mismatches(self) -> None:
        from synthesis.mutation_calibration import (
            import_human_reviewed_mutation_calibration_corpus,
            write_mutation_calibration_review_packet,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = write_mutation_calibration_review_packet(
                root,
                corpus_version="mutation_calibration_corpus_v1",
            )
            packet = json.loads(paths.packet_path.read_text(encoding="utf-8"))
            valid_labels = self._labels(packet)
            labels_path = root / "labels.jsonl"

            mismatched_hash = json.loads(json.dumps(valid_labels))
            mismatched_hash[0]["case_hash"] = mismatched_hash[1]["case_hash"]
            self._write_labels(labels_path, mismatched_hash)
            with self.assertRaisesRegex(ValueError, "label case hash mismatch"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            mismatched_version = json.loads(json.dumps(valid_labels))
            mismatched_version[0]["corpus_version"] = "another_corpus_v1"
            self._write_labels(labels_path, mismatched_version)
            with self.assertRaisesRegex(ValueError, "corpus_version mismatch"):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

            extra_case = json.loads(json.dumps(valid_labels))
            extra_label = json.loads(json.dumps(valid_labels[0]))
            extra_label["case_id"] = "mutation_calibration_case:unknown:extra:alpha"
            extra_case.append(extra_label)
            self._write_labels(labels_path, extra_case)
            with self.assertRaisesRegex(
                ValueError,
                "unknown mutation calibration case label",
            ):
                import_human_reviewed_mutation_calibration_corpus(
                    packet_path=paths.packet_path,
                    freeze_path=paths.freeze_path,
                    labels_path=labels_path,
                    output_path=root / "reviewed.json",
                )

    @staticmethod
    def _labels(packet: dict[str, object]) -> list[dict[str, object]]:
        from synthesis.mutation_calibration import HUMAN_REVIEW_ATTESTATION

        cases = packet["cases"]
        assert isinstance(cases, list)
        return [
            {
                "schema_version": "human_mutation_calibration_label_v1",
                "corpus_version": packet["corpus_version"],
                "case_id": case["case_id"],
                "case_hash": case["case_hash"],
                "ground_truth": (
                    "supported"
                    if case["sampling_class"] == "supported_candidate"
                    else "uncertain"
                    if case["scenario_tags"] == ["conditional_authorization"]
                    else "unsupported"
                ),
                "reviewer_provenance": {
                    "reviewer_id": "reviewer.alice",
                    "reviewed_at": "2026-07-25T09:30:00Z",
                    "review_method": "human_direct_review",
                    "human_review_attestation": HUMAN_REVIEW_ATTESTATION,
                },
            }
            for case in cases
        ]

    @staticmethod
    def _write_labels(
        path: Path,
        labels: list[dict[str, object]],
    ) -> None:
        path.write_text(
            "".join(
                json.dumps(label, sort_keys=True, separators=(",", ":")) + "\n"
                for label in labels
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
