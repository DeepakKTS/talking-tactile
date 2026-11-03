"""The device latency film: from the videos to eval/gate-b/videos.sha256 and a latency.csv to
finish by hand. Needs ffmpeg and ffprobe (brew install ffmpeg).

    python3 scripts/latency_film.py touch VIDEO...    # touch to tone: writes latency.csv
    python3 scripts/latency_film.py voice VIDEO...    # release to first word: voice-latency.csv

Both write videos.sha256 (sha256 and name of each video; the videos stay out of git) and one
row per sound the audio track has, with the video's fps read from its file info.

touch: each sound is an earcon. frame_earcon is the first frame where the audio rises above
the background; fill in part and frame_enter, the first frame where the fingertip visibly
crosses the traced outline, by stepping through the video. Delete rows for other sounds.

voice: frame_first_word is left blank too, since the thinking tone also makes sound: fill in
frame_release (the finger leaves the talk button) and frame_first_word for each take.

Then make results. Standard library only, apart from the ffmpeg tools."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import subprocess
import sys
from array import array
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "eval" / "gate-b"
RATE = 8000  # audio samples a second for the onset search
WINDOW = 80  # samples: 10 ms
QUIET_MS = 300  # a new sound starts only after this much background
TOUCH_COLUMNS = ["touch_no", "part", "frame_enter", "frame_earcon", "fps", "video"]
VOICE_COLUMNS = ["take", "question", "frame_release", "frame_first_word", "fps", "video"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fps(video: Path) -> Fraction:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate",
                          "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    rate = Fraction(out)
    if rate <= 0:
        raise ValueError(f"{video.name}: no frame rate in the file info ({out!r})")
    return rate


def pcm(video: Path) -> array:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    samples = array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def onsets(samples: array, rate: int = RATE) -> list[float]:
    """Seconds where the sound rises above the background after at least QUIET_MS of it: the
    background is the 20th percentile of 10 ms loudness, a sound is 6 times that and at least
    1 percent of full scale."""
    rms = [math.sqrt(sum(s * s for s in samples[i:i + WINDOW]) / WINDOW) for i in range(0, len(samples) - WINDOW + 1, WINDOW)]
    if not rms:
        return []
    floor = sorted(rms)[len(rms) // 5]
    level = max(6 * floor, 0.01 * 32768)
    quiet_needed = QUIET_MS * rate // 1000 // WINDOW
    out, quiet = [], quiet_needed
    for i, r in enumerate(rms):
        if r >= level:
            if quiet >= quiet_needed:
                out.append(i * WINDOW / rate)
            quiet = 0
        else:
            quiet += 1
    return out


def frame_at(seconds: float, rate: Fraction) -> int:
    """The first frame shown at or after this time (frame 0 starts at 0 s)."""
    return math.ceil(round(seconds * rate, 6))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("kind", choices=["touch", "voice"])
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=OUT, help="folder for the csv and videos.sha256 (default eval/gate-b)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    hashes = args.out / "videos.sha256"
    known = dict(line.split("  ", 1)[::-1] for line in hashes.read_text().splitlines() if "  " in line) if hashes.exists() else {}
    rows = []
    for video in args.videos:
        known[video.name] = sha256(video)
        rate = fps(video)
        fps_text = f"{float(rate):.3f}".rstrip("0").rstrip(".")
        if args.kind == "touch":
            for t in onsets(pcm(video)):
                rows.append({"touch_no": len(rows) + 1, "part": "", "frame_enter": "", "frame_earcon": frame_at(t, rate),
                             "fps": fps_text, "video": video.name})
        else:
            rows.append({"take": len(rows) + 1, "question": "", "frame_release": "", "frame_first_word": "",
                         "fps": fps_text, "video": video.name})
    hashes.write_text("".join(f"{h}  {name}\n" for name, h in sorted(known.items())))
    path = args.out / ("latency.csv" if args.kind == "touch" else "voice-latency.csv")
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TOUCH_COLUMNS if args.kind == "touch" else VOICE_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {path} ({len(rows)} rows to finish by hand) and {hashes} ({len(known)} videos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
