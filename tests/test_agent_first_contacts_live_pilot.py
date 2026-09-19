from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_synthesis.contacts import ContactsDomainAdapter, ContactsPilotConfiguration
from scripts.agent_first_contacts_pilot import (
    ContactsLivePilotAuthorization,
    ContactsLivePilotError,
    run_authorized_contacts_pilot,
)
from agent_synthesis.model import JsonModelResponse


class _ContactsPilotPolicyModel:
    """A deterministic stand-in that exercises the live-pilot boundary."""

    model_id = "contacts-pilot-policy-model"
    model_version = "contacts-pilot-policy-model-v1"
    provider_id = "openai_compatible"

    def complete(self, request: object) -> JsonModelResponse:
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {
                            "slot_id": slot.slot_id,
                            "content": slot.proposal_prompt.removeprefix(
                                "Return exactly this JSON proposal: "
                            ),
                        }
                        for slot in request.slots
                    ]
                }
            )
        return _agent_decision(request.task, request.observable_history)


class _OneGroundingFailurePolicyModel(_ContactsPilotPolicyModel):
    """Preserve all required behaviors while making one final answer ungrounded."""

    def complete(self, request: object) -> JsonModelResponse:
        response = super().complete(request)
        if (
            request.role == "agent"
            and "stale contact label" in request.task.instruction
            and any(tool.name == "record_followup" for tool in request.task.tools)
            and response.content.get("type") == "final_response"
        ):
            return JsonModelResponse(
                content={
                    "type": "final_response",
                    "content": "The follow-up was recorded.",
                }
            )
        return response


class ContactsLivePilotTest(unittest.TestCase):
    def test_authorization_is_required_before_creating_a_pilot_directory(self) -> None:
        model = _ContactsPilotPolicyModel()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "pilot"
            with self.assertRaisesRegex(
                ContactsLivePilotError,
                "live_provider_authorization_required",
            ):
                run_authorized_contacts_pilot(
                    output_directory=output,
                    adapter=ContactsDomainAdapter.fixture(),
                    model=model,
                    configuration=_configuration(model),
                    authorization=_authorization(approved=False),
                )
            self.assertFalse(output.exists())

    def test_authorized_pilot_records_diagnostic_evidence_and_replay(self) -> None:
        model = _ContactsPilotPolicyModel()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "pilot"
            result = run_authorized_contacts_pilot(
                output_directory=output,
                adapter=ContactsDomainAdapter.fixture(),
                model=model,
                configuration=_configuration(model),
                authorization=_authorization(approved=True),
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            public_artifacts = "".join(
                path.read_text(encoding="utf-8")
                for path in (
                    result.run.demonstrations_path,
                    result.run.negatives_path,
                    result.run.provider_usage_path,
                    result.run.manifest_path,
                    result.replay.report_path,
                    result.report_path,
                )
            )

        self.assertTrue(result.requirements_met)
        self.assertTrue(result.replay.aligned)
        self.assertEqual(result.run.demonstration_count, 8)
        self.assertEqual(result.run.negative_count, 0)
        self.assertEqual(report["collection_purpose"], "diagnostic_only")
        self.assertEqual(report["authorization"]["authorization_status"], "approved")
        self.assertEqual(report["attempt_summary"]["attempted"], 8)
        self.assertEqual(report["attempt_summary"]["task_attempt_limit"], 16)
        self.assertTrue(all(report["observed_behaviors"].values()))
        self.assertEqual(report["failed_episodes"], [])
        self.assertEqual(
            report["diagnostic_outcome"], "required_behaviors_observed"
        )
        self.assertNotIn("expected_email", public_artifacts)
        self.assertNotIn("private_case_bytes", public_artifacts)
        self.assertNotIn("injected-only", public_artifacts)

    def test_required_behavior_evidence_is_met_despite_one_target_shortfall(self) -> None:
        model = _OneGroundingFailurePolicyModel()
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_authorized_contacts_pilot(
                output_directory=Path(temporary_directory) / "pilot",
                adapter=ContactsDomainAdapter.fixture(),
                model=model,
                configuration=_configuration(model),
                authorization=_authorization(approved=True),
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

        self.assertTrue(result.requirements_met)
        self.assertEqual(result.run.demonstration_count, 7)
        self.assertEqual(result.run.negative_count, 1)
        self.assertFalse(report["attempt_summary"]["target_demonstrations_met"])
        self.assertTrue(report["feasibility_evidence"]["minimum_behavior_examples_met"])
        self.assertTrue(report["feasibility_evidence"]["attempt_ceiling_respected"])
        self.assertEqual(
            report["diagnostic_outcome"], "required_behaviors_observed"
        )


def _configuration(model: _ContactsPilotPolicyModel) -> ContactsPilotConfiguration:
    return ContactsPilotConfiguration(
        pilot_id="contacts-live-pilot-test",
        model_id=model.model_id,
        model_version=model.model_version,
        total_physical_request_limit=41,
        generation_request_limit=1,
        agent_request_limit=40,
        transport_retry_limit=0,
        max_output_tokens=1_024,
    )


def _authorization(*, approved: bool) -> ContactsLivePilotAuthorization:
    return ContactsLivePilotAuthorization(
        approved=approved,
        authorization_id="contacts-live-pilot-test-authorization",
        provider_id="openai_compatible",
        provider_host="provider.example.test",
        remote_model="contacts-pilot-policy-model",
    )


def _agent_decision(task: object, history: tuple[object, ...]) -> JsonModelResponse:
    tool_names = {tool.name for tool in task.tools}
    instruction = task.instruction

    def has_action(name: str) -> bool:
        return any(
            event.event_type == "action" and event.tool_name == name
            for event in history
        )

    has_target_lookup = any(
        event.event_type == "action"
        and event.tool_name == "lookup_contact"
        and event.arguments == {"name": "Alice Zhang"}
        for event in history
    )
    if "stale contact label" in instruction and not history:
        return _tool("lookup_contact", {"name": "Alice Zhang (stale)"})
    if "stale contact label" in instruction and not has_action("list_contacts"):
        return _tool("list_contacts", {})
    if "contact directory" in instruction and not has_action("list_contacts"):
        return _tool("list_contacts", {})
    if not has_target_lookup:
        return _tool("lookup_contact", {"name": "Alice Zhang"})
    if "record_followup" in tool_names and not has_action("record_followup"):
        return _tool(
            "record_followup",
            {"name": "Alice Zhang", "note": _requested_note(instruction)},
        )
    if "get_followup" in tool_names and not has_action("get_followup"):
        return _tool("get_followup", {"name": "Alice Zhang"})
    if "record_followup" in tool_names:
        return JsonModelResponse(
            content={
                "type": "final_response",
                "content": (
                    f"Recorded '{_requested_note(instruction)}' for Alice Zhang."
                ),
            }
        )
    return JsonModelResponse(
        content={
            "type": "final_response",
            "content": "Alice Zhang's email is alice.zhang@example.test.",
        }
    )


def _tool(name: str, arguments: dict[str, object]) -> JsonModelResponse:
    return JsonModelResponse(
        content={"type": "tool_call", "tool_name": name, "arguments": arguments}
    )


def _requested_note(instruction: str) -> str:
    marker = 'Record exactly this follow-up note: "'
    if marker not in instruction:
        return "Please send the proposal."
    return instruction.split(marker, maxsplit=1)[1].split('".', maxsplit=1)[0]
