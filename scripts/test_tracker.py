"""Tests for scripts/tracker.py. Run: python3 -m unittest -v scripts/test_tracker.py

Every test works on a temp copy of testdata/tracker_fixture.html.
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
# A frozen copy of the tracker as the kit shipped it, so tests never depend on live project state.
FIXTURE_FILE = SCRIPTS / "testdata" / "tracker_fixture.html"
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
        shutil.copyfile(FIXTURE_FILE, self.file)
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

    def test_note_only_keeps_status_and_says_so(self) -> None:
        s = self.assert_ok_write("status", "d1-4", "todo", "--note", "Pin Python 3.11 with uv")
        t = self.find(s["tasks"], "d1-4")
        self.assertEqual((t["status"], t["note"], t["done_at"]), ("todo", "Pin Python 3.11 with uv", None))
        self.assertEqual(
            s["log"][0]["text"],
            'Task d1-4 "Repo skeleton and kit" note updated, still todo. Note: Pin Python 3.11 with uv',
        )

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


class TestAdd(TrackerTestCase):
    def test_add_with_every_field(self) -> None:
        s = self.assert_ok_write(
            "add", "9", "Credit the heart figure", "--detail", "README and video credit.",
            "--timebox", "15 min", "--fallback", "A slide at the end.", "--tags", "docs, license",
        )
        t = self.find(s["tasks"], "d9-5")
        self.assertEqual(
            {k: t[k] for k in ("day", "title", "detail", "timebox", "fallback", "status", "note", "done_at", "tags")},
            {"day": 9, "title": "Credit the heart figure", "detail": "README and video credit.", "timebox": "15 min",
             "fallback": "A slide at the end.", "status": "todo", "note": "", "done_at": None, "tags": ["docs", "license"]},
        )
        self.assertRegex(t["changed_at"], ISO_RE)
        self.assertEqual(s["log"][0]["text"], 'Task d9-5 "Credit the heart figure" added to day 9.')
        self.assertEqual(len(s["tasks"]), len(self.initial["tasks"]) + 1)

    def test_new_task_sits_after_its_day(self) -> None:
        s = self.assert_ok_write("add", "9", "X")
        ids = [t["id"] for t in s["tasks"]]
        self.assertEqual(ids[ids.index("d9-5") - 1], "d9-4")
        self.assertEqual(ids[ids.index("d9-5") + 1], "d10-1")
        s = self.assert_ok_write("add", "0", "Y")
        ids = [t["id"] for t in s["tasks"]]
        self.assertEqual(ids[ids.index("d0-10") - 1], "d0-9")
        self.assertEqual(ids[ids.index("d0-10") + 1], "d1-1")

    def test_ids_count_up_and_defaults_are_empty(self) -> None:
        self.assert_ok_write("add", "3", "First")
        s = self.assert_ok_write("add", "3", "Second")
        a, b = self.find(s["tasks"], "d3-6"), self.find(s["tasks"], "d3-7")
        self.assertEqual((a["title"], b["title"]), ("First", "Second"))
        self.assertEqual((b["detail"], b["timebox"], b["fallback"], b["tags"]), ("", "", "", []))

    def test_added_task_works_with_status_and_todo(self) -> None:
        self.assert_ok_write("add", "9", "Credit the heart figure", "--timebox", "15 min")
        s = self.assert_ok_write("status", "d9-5", "done", "--note", "Credit is in the README")
        self.assertEqual(self.find(s["tasks"], "d9-5")["status"], "done")
        self.assertEqual(self.run_cli("todo").returncode, 0)
        self.assertIn("- [x] d9-5 Credit the heart figure (15 min)", (self.dir / "TODO.md").read_text(encoding="utf-8"))

    def test_bad_input_writes_nothing(self) -> None:
        self.assert_fails_unchanged("add", "11", "Too late")
        self.assert_fails_unchanged("add", "-1", "Too early")
        self.assert_fails_unchanged("add", "nine", "Not a number")
        self.assert_fails_unchanged("add", "9", "   ")
        self.assert_fails_unchanged("add", "9")


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

    def test_rename_with_a_value(self) -> None:
        s = self.assert_ok_write("metric", "lat-earcon", "0.3", "--source", "mock", "--name", "Code path to earcon, p95")
        m = self.find(s["metrics"], "lat-earcon")
        self.assertEqual((m["name"], m["value"], m["target"]), ("Code path to earcon, p95", 0.3, 100))
        self.assertIn('renamed to "Code path to earcon, p95"', s["log"][0]["text"])
        self.assert_fails_unchanged("metric", "lat-earcon", "1", "--source", "mock", "--name", " ")


class TestAddMetric(TrackerTestCase):
    def test_added_metric_is_not_measured(self) -> None:
        s = self.assert_ok_write("add-metric", "lat-device", "--suite", "Latency", "--name", "On device, p95", "--unit", "ms", "--report-only")
        m = s["metrics"][-1]
        self.assertEqual(len(s["metrics"]), len(self.initial["metrics"]) + 1)
        self.assertEqual((m["id"], m["cmp"], m["target"], m["report_only"]), ("lat-device", "<=", 0, True))
        self.assertEqual((m["value"], m["measured_at"], m["source"]), (None, None, ""))
        s = self.assert_ok_write("metric", "lat-device", "180", "--source", "live")
        self.assertEqual(self.find(s["metrics"], "lat-device")["value"], 180)

    def test_bad_new_metric(self) -> None:
        self.assert_fails_unchanged("add-metric", "lat-earcon", "--suite", "Latency", "--name", "x", "--unit", "ms")
        self.assert_fails_unchanged("add-metric", "y", "--suite", "Latency", "--name", "x", "--unit", "ms", "--target", "soon")
        self.assert_fails_unchanged("add-metric", "y", "--suite", "Latency", "--unit", "ms")


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

    def test_close_with_a_note(self) -> None:
        s = self.assert_ok_write("issue", "Earcon late", "--severity", "medium")
        iid = s["issues"][0]["id"]
        s = self.assert_ok_write("issue-status", iid, "closed", "--note", "Decided")
        i = self.find(s["issues"], iid)
        self.assertEqual((i["status"], i["note"]), ("closed", "Decided"))
        self.assertEqual(s["log"][0]["text"], "Issue closed: Earcon late. Decided")
        r = self.run_cli("todo", "--out", str(self.dir / "TODO.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Earcon late", (self.dir / "TODO.md").read_text())

    def test_bad_issue_status(self) -> None:
        self.assert_fails_unchanged("issue-status", "i-nope", "closed")
        s = self.assert_ok_write("issue", "x", "--severity", "low")
        self.assert_fails_unchanged("issue-status", s["issues"][0]["id"], "gone")


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


    def test_decision_edit(self) -> None:
        s = self.assert_ok_write("decision", "Old title", "--chose", "A", "--why", "B")
        dec = s["decisions"][-1]
        s = self.assert_ok_write("decision-edit", dec["id"], "--title", "New title", "--why", "C")
        d = s["decisions"][-1]
        self.assertEqual((d["id"], d["title"], d["decision"], d["why"], d["date"]), (dec["id"], "New title", "A", "C", dec["date"]))
        self.assertEqual(len(s["decisions"]), len(self.initial["decisions"]) + 1)
        self.assertEqual(s["log"][0]["text"], "Decision edited: Old title. Now: New title.")

    def test_decision_titles_ending_in_a_period_log_one_period(self) -> None:
        s = self.assert_ok_write("decision", "Ends here.", "--chose", "A", "--why", "B")
        self.assertEqual(s["log"][0]["text"], "Decision: Ends here.")
        dec_id = s["decisions"][-1]["id"]
        s = self.assert_ok_write("decision-edit", dec_id, "--title", "Now this.")
        self.assertEqual(s["log"][0]["text"], "Decision edited: Ends here. Now: Now this.")

    def test_decision_edit_needs_a_known_id_and_a_change(self) -> None:
        self.assert_fails_unchanged("decision-edit", "dec-nope", "--title", "x")
        s = self.assert_ok_write("decision", "T", "--chose", "A", "--why", "B")
        dec_id = s["decisions"][-1]["id"]
        self.assert_fails_unchanged("decision-edit", dec_id)
        self.assert_fails_unchanged("decision-edit", dec_id, "--title", " ")


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


class TestSpend(TrackerTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Outside self.dir, which must hold only the tracker after each write.
        self.ledger_dir = tempfile.TemporaryDirectory()
        self.ledger = Path(self.ledger_dir.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self.ledger_dir.cleanup()
        super().tearDown()

    def write_ledger(self, *lines: dict) -> None:
        self.ledger.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")

    def spend(self) -> dict:
        return self.assert_ok_write("spend", "--ledger", str(self.ledger))

    def test_spend_totals_live_calls_and_skips_cache_hits(self) -> None:
        self.write_ledger(
            {"cache": "miss", "status": 200, "cost_usd": 0.1},
            {"cache": "hit", "status": None, "cost_usd": 0.0},
            {"cache": "miss", "status": 200, "cost_usd": 0.25},
            {"cache": "miss", "status": 500, "cost_usd": None, "error": "busy"},
        )
        s = self.spend()
        [entry] = [c for c in s["costs"] if c.get("source") == "ledger"]
        self.assertEqual(entry["usd"], 0.35)
        self.assertEqual(entry["item"], "Meta Model API, 3 live calls, from eval/live/ledger.jsonl (1 unpriced)")
        self.assertEqual(entry["ts"], s["updated_at"])
        self.assertEqual(s["log"][0]["text"], "Spend set from the ledger: $0.35 over 3 live calls, 1 of them unpriced.")
        self.assertIn("Spent $0.35 of $", self.run_cli("show").stdout)

    def test_a_second_run_updates_the_same_entry_and_keeps_hand_costs(self) -> None:
        self.write_ledger({"cache": "miss", "cost_usd": 0.5})
        self.spend()
        state = self.state()
        state["costs"].append({"ts": "2026-10-28T00:00:00.000Z", "item": "printer paper", "usd": 2})
        pre, _, post = split(self.read_text())
        self.file.write_text(pre + tracker.serialize(state) + post, encoding="utf-8")
        self.before_text, self.before = self.read_text(), self.state()
        self.write_ledger({"cache": "miss", "cost_usd": 0.5}, {"cache": "miss", "cost_usd": 0.75})
        s = self.spend()
        self.assertEqual(len([c for c in s["costs"] if c.get("source") == "ledger"]), 1)
        self.assertEqual(sum(c["usd"] for c in s["costs"]), 3.25)
        self.assertIn("2 live calls", s["costs"][0]["item"])

    def test_an_unchanged_ledger_writes_nothing(self) -> None:
        self.write_ledger({"cache": "miss", "cost_usd": 0.5})
        self.spend()
        r = self.run_cli("spend", "--ledger", str(self.ledger))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Nothing written", r.stdout)
        self.assertEqual(self.read_text(), self.before_text)

    def test_a_missing_or_broken_ledger_fails_unchanged(self) -> None:
        r = self.assert_fails_unchanged("spend", "--ledger", str(self.ledger))
        self.assertIn("Cannot read the ledger", r.stderr)
        self.ledger.write_text('{"cache": "miss", "cost_usd": 0.1}\n{not json\n', encoding="utf-8")
        r = self.assert_fails_unchanged("spend", "--ledger", str(self.ledger))
        self.assertIn("line 2 does not parse", r.stderr)
        self.write_ledger({"cache": "miss", "cost_usd": "free"})
        self.assert_fails_unchanged("spend", "--ledger", str(self.ledger))


class TestTodo(TrackerTestCase):
    def todo(self, *extra: str) -> str:
        r = self.run_cli("todo", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.dir / "TODO.md").read_text(encoding="utf-8")

    def test_header_days_and_every_task_once(self) -> None:
        text = self.todo()
        self.assertEqual(text.splitlines()[0], tracker.TODO_HEADER)
        self.assertEqual(
            text.splitlines()[0],
            "Generated from TRACKER.html by scripts/tracker.py todo. Do not edit by hand.",
        )
        headings = [line for line in text.splitlines() if line.startswith("## Day ")]
        self.assertEqual(len(headings), 11)
        self.assertEqual(headings[0], "## Day 0: Oct 23 to 25")
        self.assertEqual(headings[1], "## Day 1: Mon Oct 26. Gate A")
        self.assertEqual(headings[5], "## Day 5: Fri Oct 30. Gate C")
        for t in self.initial["tasks"]:
            self.assertEqual(len(re.findall(rf"^- \[[ x]\] (~~)?{re.escape(t['id'])} ", text, re.M)), 1, t["id"])
        self.assertTrue(text.endswith("\n"))

    def test_tasks_sit_under_their_day(self) -> None:
        text = self.todo()
        sections = re.split(r"^## ", text, flags=re.M)
        for t in self.initial["tasks"]:
            sec = next(s for s in sections if re.search(rf"^- \[[ x]\] (~~)?{re.escape(t['id'])} ", s, re.M))
            self.assertTrue(sec.startswith(f"Day {t['day']}:"), t["id"])

    def test_timebox_detail_and_fallback(self) -> None:
        text = self.todo()
        self.assertIn(
            "- [ ] d0-6 Buy materials (1 h)\n"
            "  - Puffy fabric paint in 2 colors, heavy cardstock, a phone stand or gooseneck clamp, masking tape, a ruler.\n"
            "  - Fallback: Hot glue and layered card also work.\n",
            text,
        )
        self.assertIn(
            "- [ ] d0-1 Submit the hackathon application (1 h)\n"
            "  - Use the crisp answers in Handbook, Application answers. One application only.\n"
            "- [ ] d0-2",
            text,
        )
        self.assertEqual(text.count("  - Fallback:"), sum(1 for t in self.initial["tasks"] if t["fallback"]) + 4)
        for t in self.initial["tasks"]:
            if t["detail"]:
                self.assertEqual(text.count(f"\n  - {t['detail']}\n"), 1, t["id"])

    def test_empty_detail_and_fallback_add_no_lines(self) -> None:
        state = json.loads(json.dumps(self.initial))
        t = self.find(state["tasks"], "d0-6")
        t["detail"], t["fallback"] = "", ""
        text = tracker.render_todo(state)
        self.assertIn("- [ ] d0-6 Buy materials (1 h)\n- [ ] d0-7", text)

    def test_status_marks_and_notes(self) -> None:
        self.assertEqual(self.run_cli("status", "d0-1", "done", "--note", "Sent Sat").returncode, 0)
        self.assertEqual(self.run_cli("status", "d0-2", "cut").returncode, 0)
        self.assertEqual(self.run_cli("status", "d0-3", "doing").returncode, 0)
        self.assertEqual(self.run_cli("status", "d0-4", "blocked", "--note", "No reply").returncode, 0)
        text = self.todo()
        self.assertIn(
            "- [x] d0-1 Submit the hackathon application (1 h)\n"
            "  - Use the crisp answers in Handbook, Application answers. One application only.\n"
            "  - Note: Sent Sat\n",
            text,
        )
        self.assertIn("- [ ] ~~d0-2 Make the Weavory repo public and its README current~~ (30 min) [cut]", text)
        self.assertIn("- [ ] d0-3 Email Northeastern disability services (20 min) [doing]", text)
        self.assertIn(
            "- [ ] d0-4 Email Perkins School for the Blind (20 min) [blocked]\n"
            "  - Ask an educator or transcriber for a remote review of one tactile sheet and the talking layer.\n"
            "  - Note: No reply\n",
            text,
        )

    def test_gates_render_with_status_and_evidence(self) -> None:
        self.assertEqual(self.run_cli("gate", "A", "pass", "--evidence", "spikes/ p50 1.1 s").returncode, 0)
        text = self.todo()
        self.assertIn("- [x] Gate A: Models answer [Passed]\n  - Pass when: ", text)
        self.assertIn("  - Evidence: spikes/ p50 1.1 s\n", text)
        self.assertIn("- [ ] Gate B: Tracking is accurate [Pending]", text)
        day1 = re.split(r"^## ", text, flags=re.M)[2]
        self.assertTrue(day1.startswith("Day 1:") and "Gate A:" in day1)

    def test_open_issues(self) -> None:
        self.assertIn("## Open issues\n\nNone.", self.todo())
        self.assertEqual(self.run_cli("issue", "Earcon late, 140 ms", "--severity", "high").returncode, 0)
        self.assertIn("- (high) Earcon late, 140 ms", self.todo())

    def test_does_not_touch_tracker_and_is_deterministic(self) -> None:
        first = self.todo()
        self.assertEqual(self.read_text(), self.before_text)
        self.assertEqual(self.todo(), first)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["TODO.md", "TRACKER.html"])

    def test_out_option(self) -> None:
        out = self.dir / "sub.md"
        r = self.run_cli("todo", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.read_text(encoding="utf-8").startswith(tracker.TODO_HEADER))
        self.assertFalse((self.dir / "TODO.md").exists())

    def test_broken_tracker_writes_nothing(self) -> None:
        pre, raw, post = split(self.before_text)
        with open(self.file, "w", encoding="utf-8", newline="") as f:
            f.write(pre + raw.replace("{", "{,", 1) + post)
        r = self.run_cli("todo")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.dir / "TODO.md").exists())


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
