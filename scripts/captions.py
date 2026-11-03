"""docs/submission/captions.srt from the narration in docs/submission/VIDEO_SCRIPT.md.

    python3 scripts/captions.py

Each shot's narration is split into sentences, and the shot's time (less 0.3 s at each end)
is shared between them by length. A cue has at most two lines of 42 characters, the usual
limit for captions; a longer sentence becomes several cues. Run it again after the script's
narration or timings change. Standard library only."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "docs" / "submission" / "VIDEO_SCRIPT.md"
OUT = REPO / "docs" / "submission" / "captions.srt"
LINE = 42
MARGIN_S = 0.3


def seconds(t: str) -> float:
    m, s = t.split(":")
    return int(m) * 60 + float(s)


def shots(markdown: str) -> list[tuple[float, float, str]]:
    """(start, end, narration) for each row of the shot table that has narration."""
    out = []
    for line in markdown.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        m = re.fullmatch(r"(\d+:\d\d) to (\d+:\d\d)", cells[1])
        if not m:
            raise ValueError(f"shot {cells[0]}: no time range in {cells[1]!r}")
        text = cells[3]
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if text:
            out.append((seconds(m.group(1)), seconds(m.group(2)), text))
    return out


def wrap(text: str, width: int = LINE) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def cues(text: str) -> list[str]:
    """Sentences, each as one or more cues of at most two lines."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        lines = wrap(sentence)
        out += ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
    return out


def stamp(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(markdown: str) -> str:
    blocks, n = [], 0
    for start, end, text in shots(markdown):
        parts = cues(text)
        t, span = start + MARGIN_S, end - start - 2 * MARGIN_S
        total = sum(len(p) for p in parts)
        for p in parts:
            d = span * len(p) / total
            n += 1
            blocks.append(f"{n}\n{stamp(t)} --> {stamp(t + d)}\n{p}\n")
            t += d
    return "\n".join(blocks)


def main() -> int:
    OUT.write_text(srt(SCRIPT.read_text()))
    print(f"Wrote {OUT.relative_to(REPO)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
