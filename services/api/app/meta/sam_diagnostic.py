"""SAM 3.1 diagnostic, Gate A step 4.1 (tracker d1-6): why did "left ventricle" on heart.png
find nothing?

    LIVE=1 uv run python -m app.meta.sam_diagnostic [--record]

A control photo of a banana runs first. If SAM finds no banana, the run stops: the request
or the decoding is wrong, not the line art. Then heart.png as a whole, and three parts in two
phrasings each. Every answer with instances is decoded and checked against the docs (the
raster is the size of its bounds, the bounds are inside the image), and an overlay PNG goes
to data/sam_diagnostic/ (git-ignored) for a look by eye. The request is the S2 one: one
phrase, the S2 prompt's metadata, the image file as it is. 8 calls."""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from app.config import load_tactile_rules
from app.meta import sam_adapter
from app.meta.live import LiveCaller, LiveCallError
from app.meta.record import Recorder
from app.meta.smoke import HEART
from app.paths import DATA_DIR, FIXTURES_DIR
from app.pipeline import s2_ground
from app.prompts import load_prompt

CONTROL = FIXTURES_DIR / "control" / "banana.png"
OUT_DIR = DATA_DIR / "sam_diagnostic"
CALLER = "sam_diagnostic"


@dataclass(frozen=True)
class Case:
    name: str
    image: Path
    phrase: str


CONTROL_CASE = Case("control_banana", CONTROL, "banana")
CASES = [
    CONTROL_CASE,
    Case("heart_whole", HEART, "heart"),
    Case("heart_left_ventricle", HEART, "left ventricle"),
    Case("heart_left_ventricle_of_the_heart", HEART, "left ventricle of the heart"),
    Case("heart_aorta", HEART, "aorta"),
    Case("heart_aorta_of_the_heart", HEART, "aorta of the heart"),
    Case("heart_right_atrium", HEART, "right atrium"),
    Case("heart_right_atrium_of_the_heart", HEART, "right atrium of the heart"),
]


def checks(inst: sam_adapter.Decoded, image_hw: tuple[int, int]) -> dict[str, Any]:
    h, w = image_hw
    left, top, right, bottom = inst.bounds
    row: dict[str, Any] = {"object_id": inst.object_id, "decodes": inst.raster is not None}
    if inst.raster is None:
        return row | {"bounds": list(inst.bounds), "error": inst.error}
    return row | {
        "bounds": list(inst.bounds),
        "raster_hw": list(inst.raster.shape),
        "raster_is_bounds_size": inst.raster.shape == (bottom - top, right - left),
        "raster_scale": [
            round(inst.raster.shape[0] / (bottom - top), 4),
            round(inst.raster.shape[1] / (right - left), 4),
        ],
        "inside_image": 0 <= left < right <= w and 0 <= top < bottom <= h,
        "px": int(inst.raster.sum()),
    }


def overlay(image: npt.NDArray[np.uint8], insts: list[sam_adapter.Decoded]) -> npt.NDArray[Any]:
    """The image with each decoded raster painted red at its bounds, half transparent. A
    raster smaller than its bounds (SAM sends one at most 1024 px on a side) is stretched to
    them, nearest pixel, for viewing only."""
    out = image.astype(np.float32)
    for inst in insts:
        if inst.raster is None:
            continue
        left, top, right, bottom = inst.bounds
        rh, rw = inst.raster.shape
        rows = np.arange(bottom - top) * rh // (bottom - top)
        cols = np.arange(right - left) * rw // (right - left)
        stretched = inst.raster[rows][:, cols]
        region = out[top:bottom, left:right]
        mask = stretched[: region.shape[0], : region.shape[1]]
        region[mask] = region[mask] * 0.5 + np.array([255.0, 0.0, 0.0]) * 0.5
    return out.astype(np.uint8)


async def one(live: LiveCaller, case: Case, record: bool, out_dir: Path | None) -> dict[str, Any]:
    models = load_tactile_rules().meta.models
    image = np.asarray(Image.open(case.image).convert("RGB"))
    h, w = image.shape[:2]
    res = await live.post_sse(
        "/responses",
        sam_adapter.request_body(
            models.sam, case.image.read_bytes(), load_prompt(s2_ground.PROMPT).template, case.phrase
        ),
        caller=CALLER,
        model=models.sam,
        describe=f"fixtures/{case.image.relative_to(FIXTURES_DIR)} {w}x{h}, phrase: {case.phrase}",
        units=lambda _usage: {"images": 1},
        record_as=f"sam_diag_{case.name}" if record else None,
    )
    row: dict[str, Any] = {
        "case": case.name,
        "image": case.image.name,
        "phrase": case.phrase,
        "status": res.status,
        "latency_ms": res.latency_ms,
        "cost_usd": res.ledger_line["cost_usd"],
    }
    try:
        parsed = await sam_adapter.parse_events(res.body)
    except sam_adapter.ParseError as exc:
        return row | {"instances": None, "parse_error": str(exc)}
    insts = sam_adapter.decoded(parsed)
    row |= {
        "instances": len(sam_adapter.instances(parsed)),
        "confidences": [i.confidence for i in insts],
        "masks": [checks(i, (h, w)) for i in insts],
    }
    if insts and out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(overlay(image, insts)).save(out_dir / f"{case.name}.png")
    return row


async def run(
    live: LiveCaller, record: bool, out_dir: Path | None, cases: list[Case] = CASES
) -> tuple[list[dict[str, Any]], bool]:
    """The cases in order. Returns the rows and whether the control stopped the run."""
    rows = []
    for case in cases:
        row = await one(live, case, record, out_dir)
        rows.append(row)
        if case == CONTROL_CASE and not row["instances"]:
            return rows, True
    return rows, False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--record", action="store_true", help="save each call to fixtures/recorded/")
    ap.add_argument("--cases", help="comma-separated case names, to run only those")
    args = ap.parse_args()
    cases = CASES
    if args.cases:
        by_name = {c.name: c for c in CASES}
        unknown = [n for n in args.cases.split(",") if n not in by_name]
        if unknown:
            ap.error(f"unknown cases {unknown}; known: {list(by_name)}")
        cases = [by_name[n] for n in args.cases.split(",")]
    live = LiveCaller.from_env(load_tactile_rules().meta, recorder=Recorder())
    try:
        rows, stopped = asyncio.run(run(live, args.record, OUT_DIR, cases))
    except LiveCallError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    for row in rows:
        print(json.dumps(row))
    if stopped:
        print("stopped: the control found no banana, so the request or decoding is wrong")
    print(f"spent ${live.meter.spent_usd:.5f} on {live.calls} calls")
    sys.exit(1 if stopped else 0)


if __name__ == "__main__":
    main()
