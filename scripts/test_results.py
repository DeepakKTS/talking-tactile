"""Tests for scripts/results.py and scripts/latency_film.py. Run:
python3 -m unittest -v scripts/test_results.py

The whole of make results runs on synthetic data in a scratch copy of the repo (Nov 3, the
tracker's d9 task); these cover the arithmetic, the checks and the doc replacement. The audio
onsets are found in a synthetic signal, so no ffmpeg is needed here."""

from __future__ import annotations

import math
import sys
import unittest
from array import array
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import latency_film as film
import results as res

TOUCH = {"n": 45, "mean_mm": 2.25, "p95_mm": 4.32}


class LatencyTest(unittest.TestCase):
    def test_frames_become_milliseconds_at_each_rows_fps(self) -> None:
        rows = [{"a": "57", "b": "60", "fps": "30"}, {"a": "30", "b": "126", "fps": "29.97"}]
        ms = res.latencies_ms(rows, "a", "b")
        self.assertAlmostEqual(ms[0], 100.0)
        self.assertAlmostEqual(ms[1], 96 / 29.97 * 1000)
        self.assertEqual(res.summary_ms([100.0, 66.7, 133.3]), {"n": 3, "p50": 100, "p95": 133, "max": 133})

    def test_an_unfinished_or_backwards_row_is_refused(self) -> None:
        for row in ({"a": "", "b": "60", "fps": "30"}, {"a": "61", "b": "60", "fps": "30"}, {"a": "1", "b": "2", "fps": "0"}):
            with self.assertRaises(res.ResultsError):
                res.latencies_ms([row], "a", "b")
        with self.assertRaises(res.ResultsError):
            res.latencies_ms([], "a", "b")


class SpanTest(unittest.TestCase):
    TEXT = ("A: <!-- tt:gate-b -->TBD<!-- /tt:gate-b -->.\n"
            "B: <!-- tt:voice-device -->TBD: the film<!-- /tt:voice-device -->.\n")

    def test_only_spans_with_a_value_change_and_the_markers_stay(self) -> None:
        out, done = res.replace_spans(self.TEXT, {"gate-b": "mean 2 mm"})
        self.assertEqual(done, ["gate-b"])
        self.assertIn("<!-- tt:gate-b -->mean 2 mm<!-- /tt:gate-b -->", out)
        self.assertIn("<!-- tt:voice-device -->TBD: the film<!-- /tt:voice-device -->", out)
        self.assertEqual(res.replace_spans(out, {"gate-b": "mean 2 mm"})[0], out)  # a rerun changes nothing

    def test_the_doc_sentences_name_the_results_file_and_count_right(self) -> None:
        one = {"n": 1, "p50": 3203, "p95": 3203, "max": 3203}
        v = res.doc_values(TOUCH, {"n": 1, "p50": 100, "p95": 100, "max": 100}, one)
        self.assertEqual(v["gate-b"], "mean 2.25 mm, p95 4.32 mm over 45 touches (`eval/gate-b/RESULTS.md`)")
        self.assertIn("over 1 entry (", v["earcon-device"])
        self.assertEqual(v["voice-device"], "p50 3.2 s, p95 3.2 s over 1 take (`eval/gate-b/RESULTS.md`)")
        self.assertTrue(v["limits-touch"].startswith("\n- **") and v["limits-touch"].endswith(".\n"))
        self.assertEqual(res.doc_values(None, None, None), {})
        self.assertTrue(res.doc_values(TOUCH, None, None)["limits-touch"].endswith("or less (`eval/gate-b/RESULTS.md`).\n"))


class FilmTest(unittest.TestCase):
    def test_sounds_are_found_where_they_start_above_the_background(self) -> None:
        rate = film.RATE
        samples = array("h", [0] * (rate * 10))
        for i in range(len(samples)):
            samples[i] = (i * 7919) % 61 - 30  # quiet background
        for start in (2.0, 5.0, 8.0):
            for i in range(int(start * rate), int((start + 0.15) * rate)):
                samples[i] = int(16000 * math.sin(2 * math.pi * 880 * i / rate))
        self.assertEqual(film.onsets(samples, rate), [2.0, 5.0, 8.0])
        self.assertEqual(film.onsets(array("h"), rate), [])

    def test_a_time_maps_to_the_first_frame_shown_at_or_after_it(self) -> None:
        self.assertEqual(film.frame_at(2.0, Fraction(30)), 60)
        self.assertEqual(film.frame_at(2.01, Fraction(30)), 61)
        self.assertEqual(film.frame_at(4.2, Fraction(30000, 1001)), 126)


if __name__ == "__main__":
    unittest.main()
