"""Pre-commit secret check. Refuses staged content that holds the Meta API key, or that assigns
MODEL_API_KEY anywhere but .env.example, or a .env file itself.

The key is read from services/api/.env and compared as bytes, so binary files count too. Only
the staged blobs are read, not the working tree. Findings name the file and the reason. They
never print the key or any part of it.

Run from the repo root: python3 scripts/check_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ENV_FILE = Path("services") / "api" / ".env"
KEY_NAME = "MODEL_API_KEY"
ALLOWED_ASSIGN = {".env.example"}
ASSIGN_RE = re.compile(rb"\b" + KEY_NAME.encode() + rb"[ \t]*=")


def read_key(env_file: Path) -> str | None:
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == KEY_NAME:
            value = value.strip().strip('"').strip("'")
            return value or None
    return None


def staged_paths() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
    ).stdout
    return [p.decode() for p in out.split(b"\0") if p]


def staged_blob(path: str) -> bytes:
    return subprocess.run(["git", "cat-file", "blob", f":{path}"], check=True, capture_output=True).stdout


def findings(path: str, data: bytes, key: str | None) -> list[str]:
    found = []
    if Path(path).name == ".env":
        found.append("is a .env file")
    if key and key.encode() in data:
        found.append("contains the API key from services/api/.env")
    if path not in ALLOWED_ASSIGN and ASSIGN_RE.search(data):
        found.append(f"assigns {KEY_NAME} (only .env.example may)")
    return found


def main() -> int:
    key = read_key(ENV_FILE)
    bad = [(p, why) for p in staged_paths() for why in findings(p, staged_blob(p), key)]
    for path, why in bad:
        print(f"secret check: {path} {why}", file=sys.stderr)
    if bad:
        print("secret check: commit refused. Unstage or fix the files above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
