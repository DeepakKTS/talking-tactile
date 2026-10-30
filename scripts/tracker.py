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
ISSUE_STATUSES = ["open", "fixing", "closed"]  # same choices as the page
LOG_CAP = 500  # same cap as logEvent() in the page
DAY1 = dt.date(2026, 10, 26)
LAST_DAY = 10
# Same labels as DAYS in the page.
DAY_LABELS = {
    0: "Oct 23 to 25", 1: "Mon Oct 26", 2: "Tue Oct 27", 3: "Wed Oct 28", 4: "Thu Oct 29",
    5: "Fri Oct 30", 6: "Sat Oct 31", 7: "Sun Nov 1", 8: "Mon Nov 2", 9: "Tue Nov 3", 10: "Wed Nov 4",
}
GATE_WORDS = {"pending": "Pending", "pass": "Passed", "fail": "Failed", "fallback": "Fallback taken"}
TODO_HEADER = "Generated from TRACKER.html by scripts/tracker.py todo. Do not edit by hand."


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
    if prev == args.status:
        text = f'Task {t["id"]} "{t["title"]}" note updated, still {args.status}.'
    else:
        text = f'Task {t["id"]} "{t["title"]}" is now {args.status}.'
    if args.note:
        text += f" Note: {args.note}"
    commit(state, t, text, ts)
    return text


def cmd_add(state: dict, args: argparse.Namespace) -> str | None:
    if not 0 <= args.day <= LAST_DAY:
        raise TrackerError(f"Day must be 0 to {LAST_DAY}, got {args.day}.")
    if not args.title.strip():
        raise TrackerError("Task title is empty.")
    tasks = state["tasks"]
    prefix = f"d{args.day}-"
    numbers = [int(t["id"][len(prefix):]) for t in tasks
               if str(t.get("id", "")).startswith(prefix) and t["id"][len(prefix):].isdigit()]
    task = {
        "id": f"{prefix}{max(numbers, default=0) + 1}",
        "day": args.day,
        "title": args.title,
        "detail": args.detail,
        "timebox": args.timebox,
        "fallback": args.fallback,
        "status": "todo",
        "note": "",
        "done_at": None,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
    }
    # Keep tasks grouped by day: insert after the last task of the same or an earlier day.
    at = max((i + 1 for i, t in enumerate(tasks) if t.get("day", 0) <= args.day), default=0)
    tasks.insert(at, task)
    text = f'Task {task["id"]} "{task["title"]}" added to day {args.day}.'
    commit(state, task, text)
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
    if args.name is not None:
        if not args.name.strip():
            raise TrackerError("Metric name is empty.")
        text = f'Metric "{m.get("name", m["id"])}" renamed to "{args.name}" and set to {m["value"]} {m.get("unit", "")} ({args.source}).'
        m["name"] = args.name
    commit(state, m, text, ts)
    return text


def cmd_add_metric(state: dict, args: argparse.Namespace) -> str | None:
    if any(m.get("id") == args.metric_id for m in state["metrics"]):
        raise TrackerError(f"Metric id '{args.metric_id}' already exists.")
    if not args.metric_id.strip() or not args.name.strip() or not args.suite.strip():
        raise TrackerError("A metric needs an id, a suite and a name.")
    metric = {
        "id": args.metric_id,
        "suite": args.suite,
        "name": args.name,
        "cmp": args.cmp,
        "target": parse_number(args.target),
        "unit": args.unit,
        "report_only": args.report_only,
        "value": None,
        "measured_at": None,
        "source": "",
    }
    state["metrics"].append(metric)
    text = f'Metric added: "{args.name}", not measured yet.'
    commit(state, metric, text)
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


def cmd_issue_status(state: dict, args: argparse.Namespace) -> str | None:
    issue = find(state["issues"], args.issue_id, "issue")
    issue["status"] = args.status
    if args.note is not None:
        issue["note"] = args.note
    text = f"Issue {args.status}: {issue.get('title')}."
    if args.note:
        text += f" {args.note}"
    commit(state, issue, text)
    return text


def sentence(text: str) -> str:
    """Text ending in one period, whether or not it came with one."""
    return text.rstrip().rstrip(".") + "."


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
    text = f"Decision: {sentence(args.title)}"
    commit(state, decision, text)
    return text


def cmd_decision_edit(state: dict, args: argparse.Namespace) -> str | None:
    decision = find(state["decisions"], args.decision_id, "decision")
    changes = {"title": args.title, "decision": args.chose, "why": args.why}
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        raise TrackerError("Give at least one of --title, --chose or --why.")
    if any(not v.strip() for k, v in changes.items() if k != "why"):
        raise TrackerError("A decision's title and what was chosen cannot be empty.")
    old = decision["title"]
    decision.update(changes)
    text = f"Decision edited: {sentence(old)}"
    if "title" in changes and changes["title"] != old:
        text += f" Now: {sentence(changes['title'])}"
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


def read_ledger(path: Path) -> tuple[float, int, int]:
    """Totals of eval/live/ledger.jsonl: (USD, live calls, live calls with no price).
    Cache hits are not calls; a failed call has cost_usd null and counts as unpriced."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise TrackerError(f"Cannot read the ledger {path}: {e}. Nothing written.") from e
    usd, calls, unpriced = 0.0, 0, 0
    for n, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TrackerError(f"{path} line {n} does not parse: {e}. Nothing written.") from e
        cost = line.get("cost_usd") if isinstance(line, dict) else None
        if not isinstance(line, dict) or (cost is not None and not isinstance(cost, (int, float))):
            raise TrackerError(f"{path} line {n} has no usable cost_usd. Nothing written.")
        if line.get("cache") == "hit":
            continue
        calls += 1
        if cost is None:
            unpriced += 1
        else:
            usd += cost
    return round(usd, 6), calls, unpriced


def cmd_spend(state: dict, args: argparse.Namespace) -> str | None:
    """Keep one cost entry, marked source "ledger", equal to the ledger's total. Costs added
    by hand in the page stay as they are and add to it."""
    ledger = args.ledger or args.file.parent / "eval" / "live" / "ledger.jsonl"
    usd, calls, unpriced = read_ledger(ledger)
    item = f"Meta Model API, {calls} live calls, from eval/live/ledger.jsonl"
    if unpriced:
        item += f" ({unpriced} unpriced)"
    entry = next((c for c in state["costs"] if c.get("source") == "ledger"), None)
    if entry is not None and (entry.get("usd"), entry.get("item")) == (usd, item):
        print(f"Spend is already ${usd} from the ledger. Nothing written.")
        return None
    ts = now_iso()
    if entry is None:
        entry = {"source": "ledger"}
        state["costs"].insert(0, entry)
    entry.update(ts=ts, item=item, usd=usd)
    text = f"Spend set from the ledger: ${usd} over {calls} live calls"
    text += f", {unpriced} of them unpriced." if unpriced else "."
    commit(state, None, text, ts)
    return text


def render_todo(state: dict) -> str:
    """TODO.md as a pure function of the tracker state."""
    tasks, gates = state["tasks"], state["gates"]
    out = [
        TODO_HEADER,
        "",
        "# TODO.md",
        "",
        f"Tracker rev {state.get('rev')}, updated {state.get('updated_at')}. "
        "Change tasks with scripts/tracker.py, then run scripts/tracker.py todo.",
        "If a task runs 50 percent over its time box, take its fallback. If it has none, propose one first.",
    ]
    days = sorted({t.get("day") for t in tasks} | {g.get("day") for g in gates}, key=lambda d: (d is None, d))
    for day in days:
        day_gates = [g for g in gates if g.get("day") == day]
        heading = f"## Day {day}: {DAY_LABELS.get(day, '')}".rstrip(": ")
        if day_gates:
            heading += ". Gate " + ", ".join(g["id"] for g in day_gates)
        out += ["", heading, ""]
        for t in (t for t in tasks if t.get("day") == day):
            status = t.get("status", "todo")
            label = f"{t['id']} {t['title']}"
            line = f"- [{'x' if status == 'done' else ' '}] "
            line += f"~~{label}~~" if status == "cut" else label
            if t.get("timebox"):
                line += f" ({t['timebox']})"
            if status not in ("todo", "done"):
                line += f" [{status}]"
            out.append(line)
            if t.get("detail"):
                out.append(f"  - {t['detail']}")
            if t.get("fallback"):
                out.append(f"  - Fallback: {t['fallback']}")
            if t.get("note"):
                out.append(f"  - Note: {t['note']}")
        for g in day_gates:
            status = g.get("status", "pending")
            out.append(
                f"- [{'x' if status == 'pass' else ' '}] Gate {g['id']}: {g.get('title', '')} "
                f"[{GATE_WORDS.get(status, status)}]"
            )
            out.append(f"  - Pass when: {g.get('test', '')}")
            if g.get("fallback"):
                out.append(f"  - Fallback: {g['fallback']}")
            if g.get("evidence"):
                out.append(f"  - Evidence: {g['evidence']}")
    open_issues = [i for i in state["issues"] if i.get("status") != "closed"]
    out += ["", "## Open issues", ""]
    out += [f"- ({i.get('severity')}) {i.get('title')}" + (f": {i['note']}" if i.get("note") else "") for i in open_issues]
    if not open_issues:
        out.append("None. Add one with scripts/tracker.py issue.")
    return "\n".join(out) + "\n"


def atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def cmd_todo(state: dict, args: argparse.Namespace) -> str | None:
    out = args.out or args.file.parent / "TODO.md"
    atomic_write(out, render_todo(state))
    print(f"Wrote {out} from tracker rev {state.get('rev')}.")
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update TRACKER.html safely.")
    p.add_argument("--file", type=Path, default=DEFAULT_FILE, help="tracker file (default: repo TRACKER.html)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="print a summary").set_defaults(func=cmd_show)

    s = sub.add_parser("todo", help="regenerate TODO.md from the tracker")
    s.add_argument("--out", type=Path, help="output file (default: TODO.md next to the tracker)")
    s.set_defaults(func=cmd_todo)

    s = sub.add_parser("status", help="set a task status")
    s.add_argument("task_id")
    s.add_argument("status", choices=TASK_STATUSES)
    s.add_argument("--note")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("add", help="add a task")
    s.add_argument("day", type=int)
    s.add_argument("title")
    s.add_argument("--detail", default="")
    s.add_argument("--timebox", default="")
    s.add_argument("--fallback", default="")
    s.add_argument("--tags", default="", help="comma separated, such as docs,license")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("log", help="add a log entry")
    s.add_argument("text")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("metric", help="record a measured number")
    s.add_argument("metric_id")
    s.add_argument("value")
    s.add_argument("--source", choices=SOURCES, required=True)
    s.add_argument("--name", help="rename the metric")
    s.set_defaults(func=cmd_metric)

    s = sub.add_parser("add-metric", help="add a metric, not measured yet")
    s.add_argument("metric_id")
    s.add_argument("--suite", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--unit", required=True)
    s.add_argument("--cmp", choices=["<=", ">="], default="<=")
    s.add_argument("--target", default="0")
    s.add_argument("--report-only", action="store_true")
    s.set_defaults(func=cmd_add_metric)

    s = sub.add_parser("issue", help="open an issue")
    s.add_argument("text")
    s.add_argument("--severity", choices=SEVERITIES, required=True)
    s.set_defaults(func=cmd_issue)

    s = sub.add_parser("issue-status", help="set an issue status, such as closed")
    s.add_argument("issue_id")
    s.add_argument("status", choices=ISSUE_STATUSES)
    s.add_argument("--note")
    s.set_defaults(func=cmd_issue_status)

    s = sub.add_parser("decision", help="record a decision")
    s.add_argument("title")
    s.add_argument("--chose", required=True)
    s.add_argument("--why", required=True)
    s.set_defaults(func=cmd_decision)

    s = sub.add_parser("decision-edit", help="correct a recorded decision")
    s.add_argument("decision_id")
    s.add_argument("--title")
    s.add_argument("--chose")
    s.add_argument("--why")
    s.set_defaults(func=cmd_decision_edit)

    s = sub.add_parser("gate", help="set a gate status")
    s.add_argument("gate_id", choices=["A", "B", "C", "D"])
    s.add_argument("status", choices=GATE_STATUSES)
    s.add_argument("--evidence")
    s.set_defaults(func=cmd_gate)

    s = sub.add_parser("spend", help="set the spend from eval/live/ledger.jsonl totals")
    s.add_argument("--ledger", type=Path, help="ledger file (default: eval/live/ledger.jsonl next to the tracker)")
    s.set_defaults(func=cmd_spend)
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
