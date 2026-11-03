"""Tests for scripts/captions.py. Run: python3 -m unittest -v scripts/test_captions.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import captions

TABLE = """| # | Time | On screen | Narration | Caption | Criterion | Phone |
|---|---|---|---|---|---|---|
| 1 | 0:00 to 0:10 | x | "One short sentence. Say "more" to hear the rest of what the teacher wrote about this part of it." | | | |
| 2 | 0:10 to 0:20 | x | | | | |
"""


class CaptionsTest(unittest.TestCase):
    def test_narration_rows_with_their_times_and_inner_quotes_kept(self) -> None:
        self.assertEqual(captions.shots(TABLE), [(0.0, 10.0, 'One short sentence. Say "more" to hear the rest of what the teacher wrote about this part of it.')])

    def test_cues_fill_the_shot_inside_its_margins_two_lines_of_42_at_most(self) -> None:
        out = captions.srt(TABLE)
        self.assertTrue(out.startswith("1\n00:00:00,300 --> "))
        self.assertIn(" --> 00:00:09,700\n", out)
        text = [ln for ln in out.splitlines() if ln and "-->" not in ln and not ln.isdigit()]
        self.assertTrue(all(len(ln) <= captions.LINE for ln in text), text)
        self.assertEqual(" ".join(text), 'One short sentence. Say "more" to hear the rest of what the teacher wrote about this part of it.')

    def test_the_committed_file_matches_the_script(self) -> None:
        self.assertEqual(captions.OUT.read_text(), captions.srt(captions.SCRIPT.read_text()))


if __name__ == "__main__":
    unittest.main()
