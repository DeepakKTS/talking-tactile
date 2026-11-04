"""Builds fixtures/recorded/png_pixels.json, on the Mac the recordings were made on: for each
PNG the replayed flows send, the hash of its decoded pixels and the digest the recordings hold.
With it, a replay on Linux (where Pillow writes the same pixels to other bytes) finds the same
recordings (app/meta/record.py _digest).

    cd services/api && uv run python -m app.meta.png_pixels

It runs the replayed tests (the heart through the API, the question replays, demo-sheets) and
the plan eval's figures with TT_PNG_CAPTURE set, then keeps the digests a recording holds.
No live call."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.meta.record import CAPTURE_ENV, PNG_PIXELS
from app.paths import RECORDED_DIR

API = Path(__file__).resolve().parents[2]
PLAN = (
    "import asyncio, pathlib, tempfile, app.meta.plan_eval as p; "
    "p.WORK = pathlib.Path(tempfile.mkdtemp()); "
    "n = [k for k in p.FIGURES if p.FIGURES[k][0].is_file()]; p.write_index(n); "
    "asyncio.run(p.main_async(n))"
)
TESTS = ["tests/test_e2e_heart_replay.py", "tests/test_ask_replay.py", "tests/test_demo_sheets.py"]


def main() -> None:
    if sys.platform != "darwin":
        sys.exit("Build the map on macOS, where the recordings' PNG bytes were made.")
    out = Path(tempfile.mkdtemp()) / "capture.jsonl"
    env = {**os.environ, CAPTURE_ENV: str(out), "MOCK_META": "1"}
    env.pop("LIVE", None)
    for cmd in (["uv", "run", "python", "-c", PLAN], ["uv", "run", "pytest", "-q", *TESTS]):
        subprocess.run(cmd, cwd=API, env=env, check=True, stdout=subprocess.DEVNULL)
    recorded = "".join(p.read_text("utf-8") for p in RECORDED_DIR.glob("*.json"))
    found: dict[str, set[str]] = {}
    for line in out.read_text("utf-8").splitlines():
        row = json.loads(line)
        if row["digest"] in recorded:
            found.setdefault(row["pixels"], set()).add(row["digest"])
    PNG_PIXELS.write_text(
        json.dumps({k: sorted(v) for k, v in sorted(found.items())}, indent=1) + "\n", "utf-8"
    )
    print(f"{len(found)} images, {sum(len(v) for v in found.values())} digests -> {PNG_PIXELS}")


if __name__ == "__main__":
    main()
