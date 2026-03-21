from __future__ import annotations

import unittest

from ops.hygiene_recommendations import build_hygiene_recommended_actions


class TestHygieneRecommendations(unittest.TestCase):
    def test_build_hygiene_recommended_actions_converts_candidates(self) -> None:
        out = build_hygiene_recommended_actions(
            [
                {
                    "basename": "old-big.jsonl",
                    "bytes": 8000,
                    "reason": "oversize_inactive_session",
                }
            ]
        )

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["action"], "session.archive")
        self.assertEqual(
            out[0]["args"]["target_basename"],
            "old-big.jsonl",
        )
        self.assertEqual(out[0]["reason"], "oversize_inactive_session")
        self.assertEqual(out[0]["source"], "session_hygiene")

    def test_build_hygiene_recommended_actions_ignores_blank_basename(self) -> None:
        out = build_hygiene_recommended_actions(
            [
                {"basename": "", "reason": "x"},
                {"basename": "ok.jsonl", "reason": ""},
            ]
        )

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["args"]["target_basename"], "ok.jsonl")
        self.assertEqual(out[0]["reason"], "session_hygiene_candidate")


if __name__ == "__main__":
    unittest.main()
