from __future__ import annotations

import unittest

from ops.action_queue import (
    APPROVAL_REQUIRED,
    AUTO_ALLOWED,
    FORBIDDEN,
    build_action_queue,
)


class TestActionQueue(unittest.TestCase):
    def test_build_action_queue_sorts_by_policy(self) -> None:
        out = build_action_queue(
            [
                {"action": "a", "policy": AUTO_ALLOWED},
                {"action": "b", "policy": APPROVAL_REQUIRED},
                {"action": "c", "policy": FORBIDDEN},
            ]
        )

        self.assertEqual([x["action"] for x in out[AUTO_ALLOWED]], ["a"])
        self.assertEqual([x["action"] for x in out[APPROVAL_REQUIRED]], ["b"])
        self.assertEqual([x["action"] for x in out[FORBIDDEN]], ["c"])

    def test_build_action_queue_unknown_policy_goes_forbidden(self) -> None:
        out = build_action_queue(
            [
                {"action": "x", "policy": ""},
                {"action": "y"},
                {"action": "z", "policy": "weird"},
            ]
        )

        self.assertEqual(out[AUTO_ALLOWED], [])
        self.assertEqual(out[APPROVAL_REQUIRED], [])
        self.assertEqual(
            [x["action"] for x in out[FORBIDDEN]],
            ["x", "y", "z"],
        )


if __name__ == "__main__":
    unittest.main()
