"""UEB braille through liblouis's lou_translate. The Python bindings do not install into
this project's Python (see the tracker decision), so the backend runs the command line
tool once per figure with one label per line."""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from app.config import Braille

_SPACE = " "


class BrailleError(Exception):
    """A label could not be translated."""


class BrailleUnavailableError(BrailleError):
    """lou_translate or its tables are missing."""


def _has_control(text: str) -> bool:
    return any(ord(c) < ord(_SPACE) for c in text)


class Translator:
    def __init__(self, rules: Braille, binary: str | None = None) -> None:
        path = binary or shutil.which("lou_translate")
        if path is None or not Path(path).is_file():
            raise BrailleUnavailableError(
                "lou_translate was not found. Install liblouis: brew install liblouis"
            )
        self._cmd = [path, "--forward", f"{rules.display},{rules.table}"]
        self._timeout = rules.translate_timeout_s

    def translate(self, texts: Sequence[str]) -> list[str]:
        """Unicode braille for each text, in order. One process for the whole list."""
        if not texts:
            return []
        for text in texts:
            if _has_control(text):
                raise BrailleError(f"label has a control character: {text!r}")
        proc = subprocess.run(
            self._cmd,
            input="\n".join(texts) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self._timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise BrailleError(f"lou_translate failed: {proc.stderr.strip()}")
        out = proc.stdout[:-1] if proc.stdout.endswith("\n") else proc.stdout
        lines = out.split("\n")
        if len(lines) != len(texts):
            raise BrailleError(f"lou_translate returned {len(lines)} lines for {len(texts)} labels")
        return lines
