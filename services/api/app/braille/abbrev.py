"""Key abbreviations for labels whose braille does not fit on the sheet. Each starts as the
initials (or the first letters of a single word) and grows, letter by letter, until every
label has its own. Teachers can change them in review."""

import re
from collections.abc import Sequence

_FILLER = "abcdefghijklmnopqrstuvwxyz"


def _letter_stream(label: str) -> str:
    words: list[str] = re.findall(r"[a-z]+", label.lower()) or ["x"]
    initials = "".join(w[0] for w in words)
    rest = "".join(w[1:] for w in reversed(words))
    if len(words) == 1:
        return words[0]
    return initials + rest


def _suffix(k: int) -> str:
    """0 -> "", 1 -> "a", 26 -> "z", 27 -> "aa": bijective base 26 in letters."""
    out = ""
    while k > 0:
        k, r = divmod(k - 1, len(_FILLER))
        out = _FILLER[r] + out
    return out


def abbreviations(labels: Sequence[str], start: int) -> dict[str, str]:
    unique = list(dict.fromkeys(labels))
    streams: dict[str, str] = {}
    twins: dict[str, int] = {}
    used: set[str] = set()
    for label in unique:
        # Labels with the same letters ("T-cell", "t cell") get distinct letter suffixes,
        # so every stream is distinct and the growth below always ends. A suffixed stream can
        # equal another label's own ("a" + "a" is the label "aa"), so the suffix moves on
        # until the stream is unused.
        stream = _letter_stream(label)
        k = twins.get(stream, 0)
        while stream + _suffix(k) in used:
            k += 1
        twins[stream] = k + 1
        streams[label] = stream + _suffix(k)
        used.add(streams[label])
    length = {label: start for label in unique}
    while True:
        current = {label: streams[label][: length[label]] for label in unique}
        seen: dict[str, list[str]] = {}
        for label, short in current.items():
            seen.setdefault(short, []).append(label)
        clashes = [group for group in seen.values() if len(group) > 1]
        if not clashes:
            return current
        for group in clashes:
            for label in group:
                length[label] += 1
