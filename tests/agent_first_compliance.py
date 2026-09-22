"""Reusable black-box compliance assertions for Agent-first Domain adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import unittest


def assert_agent_episode_compliance(
    case: unittest.TestCase,
    *,
    demonstrations: Sequence[Mapping[str, object]],
    negatives: Sequence[Mapping[str, object]],
    replay_aligned: bool,
) -> None:
    """Assert generic admission, final-grounding, isolation, and replay gates.

    This deliberately reads only the public Episode schema.  Domain-specific
    tool and state semantics remain with the individual adapter tests.
    """

    episode_ids: set[object] = set()
    semantic_public_keys = {"oracle", "private_case", "expected_state"}
    for episode in demonstrations:
        case.assertEqual(episode["outcome"]["collection"], "demonstrations")
        case.assertEqual(episode["outcome"]["status"], "succeeded")
        case.assertEqual(episode["admission"]["mode"], "deterministic")
        case.assertEqual(episode["admission"]["status"], "admitted")
        gates = episode["admission"]["gates"]
        assert isinstance(gates, Mapping)
        case.assertTrue(all(gates.values()))
        case.assertIsNotNone(episode["verification"])
        verification = episode["verification"]
        assert isinstance(verification, Mapping)
        case.assertTrue(verification["passed"])
        case.assertTrue(
            any(event["event_type"] == "final_response" for event in episode["events"])
        )
        case.assertFalse(episode["mutation_authorization"] == "rejected")
        case.assertFalse(bool(semantic_public_keys & set(episode)))
        episode_ids.add(episode["episode_id"])

    for episode in negatives:
        case.assertEqual(episode["outcome"]["collection"], "negatives")
        case.assertIn(
            episode["outcome"]["status"],
            {"rejected_before_execution", "rejected_after_execution"},
        )
        case.assertEqual(episode["admission"]["mode"], "deterministic")
        case.assertEqual(episode["admission"]["status"], "rejected")
        gates = episode["admission"]["gates"]
        assert isinstance(gates, Mapping)
        case.assertIn(False, gates.values())
        case.assertFalse(bool(semantic_public_keys & set(episode)))
        episode_ids.add(episode["episode_id"])

    case.assertEqual(len(episode_ids), len(demonstrations) + len(negatives))
    case.assertTrue(replay_aligned)
