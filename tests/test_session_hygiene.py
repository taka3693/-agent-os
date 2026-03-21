from __future__ import annotations

import unittest

from ops.session_hygiene import select_archive_candidates


class TestSessionHygiene(unittest.TestCase):
    def test_select_archive_candidates_filters_active_and_small(self) -> None:
        out = select_archive_candidates(
            [
                {"basename": "a.jsonl", "bytes": 100},
                {"basename": "b.jsonl", "bytes": 6000},
                {"basename": "c.jsonl", "bytes": 9000},
            ],
            warn_bytes=5000,
            active_basenames=["c.jsonl"],
        )

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["basename"], "b.jsonl")
        self.assertEqual(out[0]["bytes"], 6000)
        self.assertEqual(out[0]["reason"], "oversize_inactive_session")

    def test_select_archive_candidates_sorts_descending(self) -> None:
        out = select_archive_candidates(
            [
                {"basename": "x.jsonl", "bytes": 7000},
                {"basename": "y.jsonl", "bytes": 12000},
                {"basename": "z.jsonl", "bytes": 8000},
            ],
            warn_bytes=5000,
        )

        self.assertEqual(
            [x["basename"] for x in out],
            ["y.jsonl", "z.jsonl", "x.jsonl"],
        )

    def test_select_archive_candidates_ignores_invalid_rows(self) -> None:
        out = select_archive_candidates(
            [
                {"basename": "", "bytes": 9999},
                {"basename": "ok.jsonl", "bytes": "7000"},
                {"basename": "neg.jsonl", "bytes": -1},
                {"basename": "bad.jsonl", "bytes": "abc"},
            ],
            warn_bytes=5000,
        )

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["basename"], "ok.jsonl")


if __name__ == "__main__":
    unittest.main()
