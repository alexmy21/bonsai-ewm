# Tests for the tid helpers — pure functions, no external processes.

import unittest

from bonsai_ewm.adapters import displacement_tokens, memory_tokens


class MemoryTokensTests(unittest.TestCase):
    def test_removes_consecutive_duplicates_and_caps(self):
        self.assertEqual(
            memory_tokens(["tid1", "tid1", "tid2", "tid3", "tid2", "tid4"]),
            ["tid1", "tid2", "tid3", "tid2", "tid4"],
        )
        self.assertEqual(memory_tokens(["tid1", "tid2", "tid3", "tid4"], cap=2), ["tid3", "tid4"])

    def test_empty(self):
        self.assertEqual(memory_tokens([]), [])


class DisplacementTokensTests(unittest.TestCase):
    def test_keeps_only_unseen_and_marks_seen(self):
        seen = set()
        out = displacement_tokens(seen, ["tid1", "tid2", "tid1"])
        self.assertEqual(out, ["tid1", "tid2"])
        self.assertEqual(seen, {"tid1", "tid2"})

    def test_repeats_collapse(self):
        seen = {"tid1", "tid2"}
        out = displacement_tokens(seen, ["tid1", "tid3"])
        self.assertEqual(out, ["tid3"])
        self.assertEqual(seen, {"tid1", "tid2", "tid3"})


if __name__ == "__main__":
    unittest.main()
