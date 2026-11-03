"""Pre-flight before a demo or a take: one line per check, OK or FAIL, exit 1 on any FAIL.

    make preflight                         # or: python3 scripts/preflight.py
    python3 scripts/preflight.py --live    # also the live smoke: one call per Meta model

Checks, in order:
- the key file: services/api/.env has a non-empty MODEL_API_KEY line and is git-ignored (the
  value is never printed);
- with --live only: app.meta.smoke under caffeinate -i (three live calls, costs credits);
- the phone certificate: valid for another day, for this Mac's LAN address and .local name;
- ports 8000, 5173 and 8443: free, or held by the server meant to be there;
- the heart and the Commons brain, published version 4, through the API (the one on :8000,
  else a mock one started for the check), and through the phone's web server when it runs;
- CI on HEAD, the working tree clean and pushed;
- the credits left, from eval/live/ledger.jsonl.

Standard library only, like the other scripts here."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracker import read_ledger

REPO = Path(__file__).resolve().parent.parent
API_DIR = REPO / "services" / "api"
ENV_FILE = API_DIR / ".env"
CERT = REPO / "apps" / "web" / ".certs" / "phone.pem"
LEDGER = REPO / "eval" / "live" / "ledger.jsonl"
RULES = REPO / "config" / "tactile_rules.yaml"
KEY_NAME = "MODEL_API_KEY"
FIGURES = {
    "heart": "913ba16a635188097dbb235741e05e376d23cca17bdb1789aec79a1497a67ada",
    "Commons brain": "046e94d4f0b53298900ab96754caeb348dbc624b35841512d4e5b1198a36a699",
}
VERSION = 4
# Each demo port and the process names that belong on it (lsof's command, lower case).
PORTS = {8000: ("python", "uvicorn"), 5173: ("node",), 8443: ("python",)}
MIN_CREDITS_USD = 10.0  # below this, a live take could run out


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def line(self, ok: bool, name: str, detail: str) -> None:
        self.failed += not ok
        print(f"{'OK' if ok else 'FAIL':4}  {name}: {detail}", flush=True)


def run(cmd: list[str], cwd: Path = REPO, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def key_line_set(text: str) -> bool:
    """True when some line sets KEY_NAME to a non-empty value (quotes and spaces aside)."""
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip().removeprefix("export ").strip() == KEY_NAME and value.strip().strip("'\"").strip():
            return True
    return False


def cert_names(text: str) -> set[str]:
    """The DNS names and IP addresses in `openssl x509 -text` output."""
    return set(re.findall(r"(?:DNS|IP Address):([^\s,]+)", text))


def lan_address() -> str | None:
    for iface in ("en0", "en1"):
        out = run(["ipconfig", "getifaddr", iface]).stdout.strip()
        if out:
            return out
    return None


def local_name() -> str | None:
    out = run(["scutil", "--get", "LocalHostName"]).stdout.strip()
    return f"{out}.local" if out else None


def listener(port: int) -> tuple[str, str] | None:
    """(command, pid) of the process listening on the TCP port, or None when it is free."""
    out = run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"]).stdout
    pid = re.search(r"^p(\d+)", out, re.MULTILINE)
    cmd = re.search(r"^c(.+)", out, re.MULTILINE)
    return (cmd.group(1), pid.group(1)) if pid and cmd else None


def port_ok(port: int, held: tuple[str, str] | None) -> bool:
    return held is None or held[0].lower().startswith(PORTS[port])


def get(url: str, timeout: float = 10) -> tuple[int, bytes]:
    # The phone certificate is made for the LAN; here it is only the path that is checked.
    ctx = ssl._create_unverified_context() if url.startswith("https") else None
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError as e:
        return 0, str(e).encode()


def figure_detail(status: int, body: bytes) -> tuple[bool, str]:
    if status != 200:
        return False, f"HTTP {status} {body[:120].decode(errors='replace')}"
    try:
        regions = json.loads(body).get("regions", [])
    except (ValueError, AttributeError):
        return False, "regions.json is not JSON"
    return bool(regions), f"{len(regions)} regions"


def credits_left(spent: float, budget: float) -> tuple[bool, str]:
    left = budget - spent
    return left >= MIN_CREDITS_USD, f"${left:.2f} of ${budget:.0f} left (spent ${spent:.2f})"


def check_key(c: Check) -> None:
    if not ENV_FILE.is_file():
        c.line(False, "key file", "services/api/.env is missing")
        return
    ignored = run(["git", "check-ignore", "-q", str(ENV_FILE)]).returncode == 0
    has_key = key_line_set(ENV_FILE.read_text(errors="replace"))
    c.line(has_key and ignored, "key file", f"services/api/.env, key line {'set' if has_key else 'EMPTY or missing'}, "
           f"{'git-ignored' if ignored else 'NOT git-ignored'}")


def check_smoke(c: Check) -> None:
    p = run(["caffeinate", "-i", "env", "LIVE=1", "uv", "run", "python", "-m", "app.meta.smoke"], cwd=API_DIR, timeout=300)
    last = (p.stdout.strip().splitlines() or p.stderr.strip().splitlines() or ["no output"])[-1]
    c.line(p.returncode == 0, "live smoke", last[:160])


def check_cert(c: Check) -> None:
    if not CERT.is_file():
        c.line(False, "phone certificate", "apps/web/.certs/phone.pem is missing: cd apps/web && npm run cert:phone")
        return
    fresh = run(["openssl", "x509", "-in", str(CERT), "-noout", "-checkend", "86400"]).returncode == 0
    names = cert_names(run(["openssl", "x509", "-in", str(CERT), "-noout", "-text"]).stdout)
    want = [n for n in (lan_address(), local_name()) if n]
    missing = [n for n in want if n not in names]
    detail = f"for {', '.join(want)}" if not missing else f"not for {', '.join(missing)}: cd apps/web && npm run cert:phone"
    c.line(fresh and not missing and len(want) == 2, "phone certificate",
           ("" if fresh else "expires within a day; ") + (detail if want else "no LAN address"))


def check_ports(c: Check) -> dict[int, bool]:
    up = {}
    for port in PORTS:
        held = listener(port)
        up[port] = held is not None
        state = "free" if held is None else f"{held[0]} (pid {held[1]})"
        c.line(port_ok(port, held), f"port {port}", state)
    return up


def mock_api() -> tuple[subprocess.Popen[bytes], str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "MOCK_META": "1"}
    env.pop("LIVE", None)
    proc = subprocess.Popen(["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=API_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    end = time.monotonic() + 60
    while time.monotonic() < end and get(f"{base}/api/health", 2)[0] != 200:
        time.sleep(0.5)
    return proc, base


def check_figures(c: Check, up: dict[int, bool]) -> None:
    proc = None
    if up[8000]:
        bases = {"API :8000": "http://127.0.0.1:8000"}
    else:
        proc, base = mock_api()
        bases = {"a mock API": base}
    if up[5173]:
        bases["the phone's web server :5173"] = "https://127.0.0.1:5173"
    try:
        for name, fid in FIGURES.items():
            for via, base in bases.items():
                ok, detail = figure_detail(*get(f"{base}/api/figures/{fid}/published/{VERSION}/regions.json"))
                c.line(ok, f"{name} v{VERSION}", f"{detail}, through {via}")
    finally:
        if proc:
            proc.terminate()
            proc.wait(10)


def check_git(c: Check) -> None:
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    p = run(["gh", "run", "list", "--commit", head, "--limit", "1", "--json", "status,conclusion"])
    try:
        runs = json.loads(p.stdout)
    except ValueError:
        runs = None
    if runs is None:
        c.line(False, "CI", f"gh failed: {p.stderr.strip()[:120]}")
    elif not runs:
        c.line(False, "CI", f"no run for HEAD {head[:7]} (pushed?)")
    else:
        r = runs[0]
        c.line(r["conclusion"] == "success", "CI", f"HEAD {head[:7]}: {r['status']} {r['conclusion'] or ''}".strip())
    dirty = run(["git", "status", "--porcelain"]).stdout.splitlines()
    c.line(not dirty, "git clean", "nothing to commit" if not dirty else f"{len(dirty)} changed or untracked: {dirty[0].strip()}")
    fetched = run(["git", "fetch", "--quiet"], timeout=30).returncode == 0
    ahead = run(["git", "rev-list", "--count", "@{u}..HEAD"]).stdout.strip()
    behind = run(["git", "rev-list", "--count", "HEAD..@{u}"]).stdout.strip()
    ok = ahead == "0" and behind == "0"
    c.line(ok, "git pushed", ("in step with the remote" if ok else f"{ahead} ahead, {behind} behind")
           + ("" if fetched else " (could not fetch; as of the last fetch)"))


def check_credits(c: Check) -> None:
    m = re.search(r"^\s*budget_usd:\s*([\d.]+)", RULES.read_text(), re.MULTILINE)
    budget = float(m.group(1)) if m else 150.0
    spent, calls, _ = read_ledger(LEDGER)
    ok, detail = credits_left(spent, budget)
    c.line(ok, "credits", f"{detail}, {calls} live calls in the ledger")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="also run the live smoke (three Meta calls, costs credits)")
    args = ap.parse_args(argv)
    c = Check()
    steps: list[Callable[[Check], object]] = [check_key]
    if args.live:
        steps.append(check_smoke)
    steps += [check_cert]
    for step in steps:
        step(c)
    check_figures(c, check_ports(c))
    check_git(c)
    check_credits(c)
    print(f"\n{'PREFLIGHT: ALL OK' if not c.failed else f'PREFLIGHT: {c.failed} FAIL'}")
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
