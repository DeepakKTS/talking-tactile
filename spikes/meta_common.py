"""Shared helpers for the Meta API spikes. Standard library only.

The spikes import this from their own directory (uv run puts the script
directory on sys.path). Product code will get its own client in
services/api/app/meta/; this file is for spikes only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "services" / "api" / ".env"
FIXTURES = ROOT / "fixtures"
RESULTS = Path(__file__).resolve().parent / "results"

# Prices from https://dev.meta.ai/docs/pricing-rate-limits, read 2026-10-24.
PRICES = {
    "muse-spark-1.3": {"input": 1.25 / 1e6, "cached_input": 0.15 / 1e6, "output": 4.25 / 1e6},
    "sam-3.1": {"image": 2.50 / 1000},
    "muse-voice-transcribe-1.0": {"audio_second": 0.18 / 3600},
}


def load_env() -> dict[str, str]:
    """Read services/api/.env as KEY=VALUE lines. Exits with a clear message if the key is missing."""
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("META_API_KEY"):
        sys.exit(
            f"No META_API_KEY in {ENV_FILE}. Copy .env.example there and add the key. "
            "Use --dry-run to check the request without a key."
        )
    env.setdefault("META_API_BASE", "https://api.meta.ai/v1")
    return env


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile, so p95 of 10 samples is the largest one."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(1, math.ceil(pct / 100 * len(s)))
    return s[k - 1]


def summarize(name: str, ms: list[float]) -> dict:
    out = {"name": name, "n": len(ms), "p50_ms": round(percentile(ms, 50), 1), "p95_ms": round(percentile(ms, 95), 1),
           "min_ms": round(min(ms), 1) if ms else None, "max_ms": round(max(ms), 1) if ms else None}
    print(f"{name}: n={out['n']} p50={out['p50_ms']} ms p95={out['p95_ms']} ms min={out['min_ms']} max={out['max_ms']}")
    return out


def _check_no_secret(text: str, secret: str | None) -> None:
    if secret and secret in text:
        raise RuntimeError("Refusing to write a file that contains the API key.")


def save_fixture(model_dir: str, case: str, obj: object, secret: str | None = None) -> Path:
    path = FIXTURES / model_dir / f"{case}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    _check_no_secret(text, secret)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"fixture: {path.relative_to(ROOT)}")
    return path


def save_results(model: str, obj: dict, secret: str | None = None) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{model}-{stamp}.json"
    obj = {"model": model, "run_at": stamp, **obj}
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    _check_no_secret(text, secret)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"results: {path.relative_to(ROOT)}")
    return path


def redacted_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() == "authorization" else v) for k, v in headers.items()}
