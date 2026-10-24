"""Tests for scripts/tracker.py. Run: python3 -m unittest -v scripts/test_tracker.py

Every test works on a copy of TRACKER.html in a temp directory.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TRACKER = SCRIPTS / "tracker.py"
REAL_FILE = SCRIPTS.parent / "TRACKER.html"
BLOCK_RE = re.compile(r'(<script id="tt-state" type="application/json">)(.*?)(</script>)', re.S)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

sys.path.insert(0, str(SCRIPTS))
import tracker  # noqa: E402


def split(text: str) -> tuple[str, str, str]:
    m = BLOCK_RE.search(text)
    assert m is not None
    return text[: m.start(2)], m.group(2), text[m.end(2) :]


class TrackerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "TRACKER.html"
        shutil.copyfile(REAL_FILE, self.file)
        self.before_text = self.read_text()
        self.before = self.state()
        self.initial = self.before

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def read_text(self) -> str:
        with open(self.file, encoding="utf-8", newline="") as f:
            return f.read()

    def state(self) -> dict:
        return json.loads(split(self.read_text())[1])

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TRACKER), "--file", str(self.file), *args],
            capture_output=True,
            text=True,
        )

    def assert_ok_write(self, *args: str) -> dict:
        r = self.run_cli(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        after_text = self.read_text()
        pre, _, post = split(after_text)
        bpre, _, bpost = split(self.before_text)
        self.assertEqual(pre, bpre, "bytes before the block changed")
        self.assertEqual(post, bpost, "bytes after the block changed")
        self.assertEqual(len(BLOCK_RE.findall(after_text)), 1)
        self.assertNotIn("<", split(after_text)[1])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["TRACKER.html"], "temp file left behind")
        s = self.state()
        self.assertEqual(s["rev"], self.before["rev"] + 1)
        self.assertRegex(s["updated_at"], ISO_RE)
        self.assertEqual(s["log"][0]["kind"], "claude")
        self.assertEqual(s["log"][0]["ts"], s["updated_at"])
        self.assertEqual(len(s["log"]), len(self.before["log"]) + 1)
        self.before_text, self.before = after_text, s
        return s

    def assert_fails_unchanged(self, *args: str) -> subprocess.CompletedProcess:
        r = self.run_cli(*args)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.read_text(), self.before_text, "file changed on a failed command")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["TRACKER.html"])
        return r

    @staticmethod
    def find(items: list[dict], item_id: str) -> dict:
        return next(x for x in items if x["id"] == item_id)


class TestSerialization(TrackerTestCase):
    def test_round_trip_is_byte_identical(self) -> None:
        _, raw, _ = split(self.before_text)
        self.assertEqual(tracker.serialize(json.loads(raw)), raw)

    def test_now_iso_matches_js_format(self) -> None:
        self.assertRegex(tracker.now_iso(), ISO_RE)

    def test_build_day(self) -> None:
        import datetime as dt

        self.assertEqual(tracker.build_day(dt.date(2026, 10, 24)), 0)
        self.assertEqual(tracker.build_day(dt.date(2026, 10, 26)), 1)
        self.assertEqual(tracker.build_day(dt.date(2026, 11, 4)), 10)
        self.assertEqual(tracker.build_day(dt.date(2026, 11, 9)), 10)


class TestShow(TrackerTestCase):
    def test_show_prints_and_does_not_write(self) -> None:
        r = self.run_cli("show")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"rev {self.before['rev']}", r.stdout)
        self.assertIn("Gates:", r.stdout)
        self.assertIn("Tasks: todo", r.stdout)
        self.assertEqual(self.read_text(), self.before_text)


class TestStatus(TrackerTestCase):
    def test_every_status_and_done_at(self) -> None:
        for status in ["doing", "blocked", "cut", "todo"]:
            s = self.assert_ok_write("status", "d1-5", status)
            t = self.find(s["tasks"], "d1-5")
            self.assertEqual(t["status"], status)
            self.assertIsNone(t["done_at"])
            self.assertRegex(t["changed_at"], ISO_RE)
        s = self.assert_ok_write("status", "d1-5", "done", "--note", "p50 1.2 s, p95 2.0 s")
        t = self.find(s["tasks"], "d1-5")
        self.assertEqual(t["status"], "done")
        self.assertRegex(t["done_at"], ISO_RE)
        self.assertEqual(t["done_at"], t["changed_at"])
        self.assertEqual(t["note"], "p50 1.2 s, p95 2.0 s")
        self.assertIn('Task d1-5 "Spike Muse Spark" is now done. Note: p50 1.2 s, p95 2.0 s', s["log"][0]["text"])
        s = self.assert_ok_write("status", "d1-5", "doing")
        self.assertIsNone(self.find(s["tasks"], "d1-5")["done_at"])
        self.assertEqual(self.find(s["tasks"], "d1-5")["note"], "p50 1.2 s, p95 2.0 s")

    def test_same_status_without_note_is_noop(self) -> None:
        r = self.run_cli("status", "d1-5", "todo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_text(), self.before_text)

    def test_only_target_task_changes(self) -> None:
        s = self.assert_ok_write("status", "d0-1", "doing")
        for old, new in zip(self.initial["tasks"], s["tasks"]):
            if old["id"] != "d0-1":
                self.assertEqual(old, new)

    def test_invalid_task_id(self) -> None:
        r = self.assert_fails_unchanged("status", "d9-99", "done")
        self.assertIn("Unknown task id", r.stderr)

    def test_invalid_status_value(self) -> None:
        self.assert_fails_unchanged("status", "d1-5", "finished")


class TestLog(TrackerTestCase):
    def test_log(self) -> None:
        s = self.assert_ok_write("log", "Spike notes written")
        self.assertEqual(s["log"][0]["text"], "Spike notes written")

    def test_script_tag_text_is_escaped(self) -> None:
        s = self.assert_ok_write("log", "odd </script><b>text</b>")
        self.assertEqual(s["log"][0]["text"], "odd </script><b>text</b>")
        self.assertIn("\\u003c/script>", self.read_text())

    def test_empty_log(self) -> None:
        self.assert_fails_unchanged("log", "  ")


class TestMetric(TrackerTestCase):
    def test_metric_live_int_and_mock_float(self) -> None:
        s = self.assert_ok_write("metric", "touch-mean", "4", "--source", "live")
        m = self.find(s["metrics"], "touch-mean")
        self.assertEqual((m["value"], m["source"]), (4, "live"))
        self.assertIsInstance(m["value"], int)
        self.assertRegex(m["measured_at"], ISO_RE)
        self.assertEqual(m["changed_at"], m["measured_at"])
        s = self.assert_ok_write("metric", "lat-answer", "1.75", "--source", "mock")
        m = self.find(s["metrics"], "lat-answer")
        self.assertEqual((m["value"], m["source"]), (1.75, "mock"))

    def test_invalid_metric_id(self) -> None:
        r = self.assert_fails_unchanged("metric", "nope", "1", "--source", "live")
        self.assertIn("Unknown metric id", r.stderr)

    def test_non_numeric_value(self) -> None:
        self.assert_fails_unchanged("metric", "touch-mean", "fast", "--source", "live")
        self.assert_fails_unchanged("metric", "touch-mean", "nan", "--source", "live")

    def test_bad_or_missing_source(self) -> None:
        self.assert_fails_unchanged("metric", "touch-mean", "3", "--source", "guess")
        self.assert_fails_unchanged("metric", "touch-mean", "3")


class TestIssue(TrackerTestCase):
    def test_each_severity(self) -> None:
        for sev in ["high", "medium", "low"]:
            s = self.assert_ok_write("issue", f"SAM misses thin lines {sev}", "--severity", sev)
            i = s["issues"][0]
            self.assertEqual(i["title"], f"SAM misses thin lines {sev}")
            self.assertEqual((i["severity"], i["status"], i["note"]), (sev, "open", ""))
            self.assertRegex(i["id"], r"^i-[0-9a-z]+$")
            self.assertRegex(i["ts"], ISO_RE)
            self.assertEqual(i["ts"], i["changed_at"])
        self.assertEqual(len({i["id"] for i in s["issues"]}), 3)

    def test_bad_severity(self) -> None:
        self.assert_fails_unchanged("issue", "x", "--severity", "urgent")
        self.assert_fails_unchanged("issue", "x")


class TestDecision(TrackerTestCase):
    def test_decision(self) -> None:
        s = self.assert_ok_write("decision", "Laptop for Explore", "--chose", "Laptop with phone as webcam", "--why", "Phone ran at 9 fps")
        d = s["decisions"][-1]
        self.assertEqual(len(s["decisions"]), len(self.initial["decisions"]) + 1)
        self.assertEqual((d["title"], d["decision"], d["why"]), ("Laptop for Explore", "Laptop with phone as webcam", "Phone ran at 9 fps"))
        self.assertRegex(d["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(d["id"], r"^dec-[0-9a-z]+$")
        self.assertEqual(s["log"][0]["text"], "Decision: Laptop for Explore.")

    def test_decision_needs_fields(self) -> None:
        self.assert_fails_unchanged("decision", "Title only")
        self.assert_fails_unchanged("decision", "T", "--chose", "x")


class TestGate(TrackerTestCase):
    def test_gate_with_and_without_evidence(self) -> None:
        s = self.assert_ok_write("gate", "A", "pass", "--evidence", "spikes/ p50 and p95 written")
        g = self.find(s["gates"], "A")
        self.assertEqual((g["status"], g["evidence"]), ("pass", "spikes/ p50 and p95 written"))
        self.assertRegex(g["changed_at"], ISO_RE)
        s = self.assert_ok_write("gate", "B", "fallback")
        g = self.find(s["gates"], "B")
        self.assertEqual((g["status"], g["evidence"]), ("fallback", ""))
        self.assertEqual(s["log"][0]["text"], "Gate B is now fallback.")

    def test_invalid_gate(self) -> None:
        self.assert_fails_unchanged("gate", "E", "pass")
        self.assert_fails_unchanged("gate", "A", "maybe")


class TestBrokenFile(TrackerTestCase):
    def corrupt(self, new_text: str) -> None:
        with open(self.file, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        self.before_text = new_text

    def test_corrupted_json_block(self) -> None:
        pre, raw, post = split(self.before_text)
        broken = raw.replace("{", "{,", 1)
        self.assertNotEqual(broken, raw)
        self.corrupt(pre + broken + post)
        for args in (["show"], ["log", "x"], ["status", "d1-5", "doing"]):
            r = self.assert_fails_unchanged(*args)
            self.assertIn("does not parse", r.stderr)

    def test_missing_block(self) -> None:
        self.corrupt(self.before_text.replace('id="tt-state"', 'id="tt-gone"'))
        r = self.assert_fails_unchanged("log", "x")
        self.assertIn("found 0", r.stderr)

    def test_duplicate_block(self) -> None:
        pre, raw, post = split(self.before_text)
        extra = '<script id="tt-state" type="application/json">{}</script>'
        self.corrupt(pre + raw + post.replace("</body>", extra + "</body>", 1))
        r = self.assert_fails_unchanged("log", "x")
        self.assertIn("found 2", r.stderr)

    def test_file_changed_during_write_is_refused(self) -> None:
        text, start, end, state = tracker.read_tracker(self.file)
        tracker.commit(state, None, "x")
        self.corrupt(self.before_text + "\n")
        with self.assertRaises(tracker.TrackerError):
            tracker.write_tracker(self.file, text, start, end, state)
        self.assertEqual(self.read_text(), self.before_text)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["TRACKER.html"])


if __name__ == "__main__":
    unittest.main()
