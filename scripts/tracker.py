#!/usr/bin/env python3
"""Safe command line updates for TRACKER.html.

Edits only the JSON inside <script id="tt-state" type="application/json">.
Serializes the same way the page's own Save to file does, so diffs stay small.
Standard library only. Python 3.11 or newer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "TRACKER.html"
BLOCK_RE = re.compile(
    r'(<script id="tt-state" type="application/json">)(.*?)(</script>)', re.S
)
TASK_STATUSES = ["todo", "doing", "done", "blocked", "cut"]
GATE_STATUSES = ["pending", "pass", "fail", "fallback"]
SEVERITIES = ["high", "medium", "low"]
SOURCES = ["live", "mock"]
LOG_CAP = 500  # same cap as logEvent() in the page
DAY1 = dt.date(2026, 10, 26)
LAST_DAY = 10


class TrackerError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# ---------- time and ids, matching the page ----------

def now_iso() -> str:
    """Same format as JS new Date().toISOString(), so string compares work."""
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def et_today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        # No tz database: EDT is UTC-4 for the whole build window.
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)).date()


def base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if n == 0:
            return out


def uid(prefix: str) -> str:
    """Same shape as uid() in the page: prefix-<ms base36><4 random chars>."""
    tail = "".join(random.choice("0123456789abcdefghijklmnopqrstuvwxyz") for _ in range(4))
    return f"{prefix}-{base36(int(time.time() * 1000))}{tail}"


def build_day(today: dt.date) -> int:
    if today < DAY1:
        return 0
    return min(LAST_DAY, (today - DAY1).days + 1)


# ---------- read and write ----------

def serialize(state: dict) -> str:
    """Same output as the page: JSON.stringify(out, null, 1) with < escaped."""
    text = json.dumps(state, indent=1, ensure_ascii=False).replace("<", "\\u003c")
    return "\n" + text + "\n"


def read_tracker(path: Path) -> tuple[str, int, int, dict]:
    """Return the file text, the JSON span, and the parsed state."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError as e:
        raise TrackerError(f"Cannot read {path}: {e}", 2) from e
    matches = list(BLOCK_RE.finditer(text))
    if len(matches) != 1:
        raise TrackerError(
            f"Expected one tt-state block in {path}, found {len(matches)}. Nothing written.", 2
        )
    m = matches[0]
    try:
        state = json.loads(m.group(2))
    except json.JSONDecodeError as e:
        raise TrackerError(f"tt-state JSON does not parse: {e}. Nothing written.", 2) from e
    if not isinstance(state, dict):
        raise TrackerError("tt-state JSON is not an object. Nothing written.", 2)
    for key in ("tasks", "gates", "metrics", "costs", "decisions", "issues", "log"):
        state.setdefault(key, [])
    state.setdefault("rev", 1)
    return text, m.start(2), m.end(2), state


def write_tracker(path: Path, original: str, start: int, end: int, state: dict) -> None:
    new_text = original[:start] + serialize(state) + original[end:]
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tracker.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
            f.flush()
            os.fsync(f.fileno())
        check_text, s2, e2, _ = read_tracker(tmp)
        if check_text[:s2] != original[:start] or check_text[e2:] != original[end:]:
            raise TrackerError("Content outside tt-state would change. Nothing written.", 2)
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() != original:
                raise TrackerError(
                    f"{path} changed while this command ran. Nothing written. Run it again.", 2
                )
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def commit(state: dict, item: dict | None, log_text: str, ts: str | None = None) -> None:
    """Stamp the item, log, bump rev. Pass ts so every field of one edit shares it."""
    ts = ts or now_iso()
    if item is not None:
        item["changed_at"] = ts
    state["log"].insert(0, {"ts": ts, "kind": "claude", "text": log_text})
    del state["log"][LOG_CAP:]
    state["rev"] = int(state["rev"]) + 1
    state["updated_at"] = ts


def find(items: list[dict], item_id: str, kind: str) -> dict:
    for x in items:
        if x.get("id") == item_id:
            return x
    ids = ", ".join(str(x.get("id")) for x in items)
    raise TrackerError(f"Unknown {kind} id '{item_id}'. Valid ids: {ids}")


def parse_number(raw: str) -> int | float:
    try:
        value = float(raw)
    except ValueError as e:
        raise TrackerError(f"Metric value must be a number, got '{raw}'.") from e
    if not math.isfinite(value):
        raise TrackerError(f"Metric value must be finite, got '{raw}'.")
    return int(value) if value.is_integer() else value


# ---------- commands ----------

def cmd_show(state: dict, args: argparse.Namespace) -> str | None:
    tasks = state["tasks"]
    day = build_day(et_today())
    counts = Counter(t.get("status") for t in tasks)
    out = [
        f"rev {state.get('rev')}  updated {state.get('updated_at')}",
        f"Build day {day}",
        "Tasks: " + ", ".join(f"{s} {counts.get(s, 0)}" for s in TASK_STATUSES),
        "",
        f"Open tasks for day {day}:",
    ]
    open_today = [t for t in tasks if t.get("day") == day and t.get("status") not in ("done", "cut")]
    for t in open_today:
        box = f" ({t['timebox']})" if t.get("timebox") else ""
        out.append(f"  {t['id']} [{t['status']}] {t['title']}{box}")
    if not open_today:
        out.append("  none")
    for status in ("doing", "blocked"):
        listed = [t for t in tasks if t.get("status") == status]
        if listed:
            out += ["", f"{status.capitalize()}:"]
            out += [f"  {t['id']} {t['title']}: {t.get('note') or 'no note'}" for t in listed]
    out += ["", "Gates:"]
    for g in state["gates"]:
        ev = f"  evidence: {g['evidence']}" if g.get("evidence") else ""
        out.append(f"  {g['id']} day {g.get('day')} {g.get('status')}: {g.get('title')}{ev}")
    measured = [m for m in state["metrics"] if m.get("value") is not None]
    if measured:
        out += ["", "Measured:"]
        for m in measured:
            out.append(
                f"  {m['id']} {m['value']} {m.get('unit', '')} (goal {m.get('cmp')} {m.get('target')}, {m.get('source') or 'no source'})"
            )
    open_issues = [i for i in state["issues"] if i.get("status") != "closed"]
    if open_issues:
        out += ["", "Open issues:"]
        out += [f"  ({i.get('severity')}) {i.get('title')}" for i in open_issues]
    spent = sum(float(c.get("usd") or 0) for c in state["costs"])
    out += ["", f"Spent ${spent:.2f} of ${state.get('budget_usd', 150)}", "", "Recent log:"]
    out += [f"  {e.get('ts')} [{e.get('kind')}] {e.get('text')}" for e in state["log"][:5]]
    print("\n".join(out))
    return None


def cmd_status(state: dict, args: argparse.Namespace) -> str | None:
    t = find(state["tasks"], args.task_id, "task")
    if t.get("status") == args.status and args.note is None:
        print(f"Task {t['id']} is already {args.status}. Nothing written.")
        return None
    ts = now_iso()
    prev = t.get("status")
    t["status"] = args.status
    # Same done_at rule as setTaskStatus() in the page.
    if args.status == "done":
        if prev != "done":
            t["done_at"] = ts
    elif prev == "done":
        t["done_at"] = None
    if args.note is not None:
        t["note"] = args.note
    text = f'Task {t["id"]} "{t["title"]}" is now {args.status}.'
    if args.note:
        text += f" Note: {args.note}"
    commit(state, t, text, ts)
    return text


def cmd_log(state: dict, args: argparse.Namespace) -> str | None:
    if not args.text.strip():
        raise TrackerError("Log text is empty.")
    commit(state, None, args.text)
    return args.text


def cmd_metric(state: dict, args: argparse.Namespace) -> str | None:
    m = find(state["metrics"], args.metric_id, "metric")
    ts = now_iso()
    m["value"] = parse_number(args.value)
    m["measured_at"] = ts
    m["source"] = args.source
    text = f'Metric "{m.get("name", m["id"])}" set to {m["value"]} {m.get("unit", "")} ({args.source}).'
    commit(state, m, text, ts)
    return text


def cmd_issue(state: dict, args: argparse.Namespace) -> str | None:
    if not args.text.strip():
        raise TrackerError("Issue text is empty.")
    ts = now_iso()
    issue = {
        "id": uid("i"),
        "ts": ts,
        "title": args.text,
        "severity": args.severity,
        "status": "open",
        "note": "",
    }
    state["issues"].insert(0, issue)
    text = f"Issue opened: {args.text}."
    commit(state, issue, text, ts)
    return text


def cmd_decision(state: dict, args: argparse.Namespace) -> str | None:
    if not args.title.strip() or not args.chose.strip():
        raise TrackerError("A decision needs a title and what was chosen.")
    decision = {
        "id": uid("dec"),
        "date": et_today().isoformat(),
        "title": args.title,
        "decision": args.chose,
        "why": args.why,
    }
    state["decisions"].append(decision)
    text = f"Decision: {args.title}."
    commit(state, decision, text)
    return text


def cmd_gate(state: dict, args: argparse.Namespace) -> str | None:
    g = find(state["gates"], args.gate_id, "gate")
    g["status"] = args.status
    if args.evidence is not None:
        g["evidence"] = args.evidence
    text = f"Gate {g['id']} is now {args.status}."
    if args.evidence:
        text += f" Evidence: {args.evidence}"
    commit(state, g, text)
    return text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update TRACKER.html safely.")
    p.add_argument("--file", type=Path, default=DEFAULT_FILE, help="tracker file (default: repo TRACKER.html)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="print a summary").set_defaults(func=cmd_show)

    s = sub.add_parser("status", help="set a task status")
    s.add_argument("task_id")
    s.add_argument("status", choices=TASK_STATUSES)
    s.add_argument("--note")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("log", help="add a log entry")
    s.add_argument("text")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("metric", help="record a measured number")
    s.add_argument("metric_id")
    s.add_argument("value")
    s.add_argument("--source", choices=SOURCES, required=True)
    s.set_defaults(func=cmd_metric)

    s = sub.add_parser("issue", help="open an issue")
    s.add_argument("text")
    s.add_argument("--severity", choices=SEVERITIES, required=True)
    s.set_defaults(func=cmd_issue)

    s = sub.add_parser("decision", help="record a decision")
    s.add_argument("title")
    s.add_argument("--chose", required=True)
    s.add_argument("--why", required=True)
    s.set_defaults(func=cmd_decision)

    s = sub.add_parser("gate", help="set a gate status")
    s.add_argument("gate_id", choices=["A", "B", "C", "D"])
    s.add_argument("status", choices=GATE_STATUSES)
    s.add_argument("--evidence")
    s.set_defaults(func=cmd_gate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text, start, end, state = read_tracker(args.file)
        changed = args.func(state, args)
        if changed is not None:
            write_tracker(args.file, text, start, end, state)
            print(f"rev {state['rev']}: {changed}")
    except TrackerError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
