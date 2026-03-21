from __future__ import annotations

import unittest

from ops.policy import (
    APPROVAL_REQUIRED,
    AUTO_ALLOWED,
    FORBIDDEN,
    classify_action_policy,
    decide_recommended_action,
)


class TestPolicy(unittest.TestCase):
    def test_read_actions_are_auto_allowed(self) -> None:
        self.assertEqual(
            classify_action_policy("service.status_openclaw_gateway"),
            AUTO_ALLOWED,
        )
        self.assertEqual(
            classify_action_policy("session.list_jsonl_sizes"),
            AUTO_ALLOWED,
        )

    def test_mutating_actions_require_approval(self) -> None:
        self.assertEqual(
            classify_action_policy("session.archive"),
            APPROVAL_REQUIRED,
        )
        self.assertEqual(
            classify_action_policy("service.restart_openclaw_gateway"),
            APPROVAL_REQUIRED,
        )

    def test_unknown_action_is_forbidden(self) -> None:
        self.assertEqual(
            classify_action_policy("unknown.action"),
            FORBIDDEN,
        )

    def test_decide_recommended_action_adds_policy(self) -> None:
        item = {
            "action": "session.archive",
            "args": {"target_basename": "abc.jsonl"},
            "reason": "test",
        }
        out = decide_recommended_action(item)

        self.assertEqual(out["policy"], APPROVAL_REQUIRED)
        self.assertEqual(out["action"], "session.archive")
        self.assertEqual(out["args"]["target_basename"], "abc.jsonl")


if __name__ == "__main__":
    unittest.main()
