"""Arm A v2 of S2 on one figure: Spark points with guards, SAM, group unions.

    LIVE=1 uv run python -m app.meta.s2_armav2 FIGURE --record
    uv run python -m app.meta.s2_armav2 FIGURE --replay

The parts are the bake-off's list for the figure (FIGURE/results.json), so v1 and v2 are
graded on the same parts. One Spark call returns, per part, a kind (area, thin or group),
the members of a group, the part it sits inside, and every instance of the part (main
drawing and insets), each with 1 to 3 points on the docs' 0-1000 grid.

Point guard, in code. A point on label text, a leader line or ink (app/geometry/
print_marks.py) moves to the nearest pixel within GUARD_PX that is none of those, is part
of the figure (not the page or the sea: s2_grading.object_mask), and is within FILL_DELTA
(layout.color_group_max_delta) of the part's fill color. The fill color is the median color
under the instance's clean points, or, if it has none, the commonest color among such
pixels within GUARD_PX. With no such pixel the point is dropped and flagged.

SAM, per the docs (sam/segmenting, read Oct 29): an object takes one or more points, a
point with a leading - is negative, and one request names up to 16 objects. The docs give
no option for several candidate masks per prompt, so none is sent. One SAM call per part
that is not a group, one object per instance with all of its positive points. Negative
points come from v1's spill: for each other part with a point inside this part's v1 Arm A
mask, the first such point, unless it is within GUARD_PX of one of this part's own points.
Groups get no call; a group's mask is the union of its members' masks.

Post-processing. Each instance keeps the connected pieces of its mask that hold one of its
positive points and drops pieces under S3's speck floor. Where parts overlap, each pixel
goes to the smallest mask claiming it; the pixels each part loses are recorded, and specks
that leaves are dropped again. Parts of kind thin keep their result and are marked thin;
how they appear on the sheet is decided later.

Writes eval/s2-bakeoff/FIGURE/results_v2.json and v2.html, a sheet with each part's v1 and
v2 masks side by side and blank grade columns, and images under img/ (git-ignored)."""

import argparse
import asyncio
import html
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from app.config import load_tactile_rules
from app.geometry import print_marks
from app.meta import s2_bakeoff as bake
from app.meta import s2_grading as grading
from app.meta import sam_adapter
from app.meta.cost import CostMeter
from app.meta.live import DEFAULT_BASE, Ledger, LiveCaller, LiveCallError, spark_units
from app.meta.record import Recorder, ReplayTransport
from app.paths import RECORDED_DIR
from app.pipeline import s2_ground
from app.prompts import load_prompt

Mask = npt.NDArray[np.bool_]
Point = tuple[int, int]

CALLER = "s2_armav2"
GUARD_PX = 15
MAX_OBJECTS = 16  # sam/segmenting: box and point prompts name up to 16 objects
KINDS = ("area", "thin", "group")

V2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "string"},
                    "kind": {"enum": list(KINDS)},
                    "members": {"type": "array", "items": {"type": "string"}},
                    "parent": {"type": "string"},
                    "instances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "where": {"type": "string"},
                                "points": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 3,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "x": {"type": "integer"},
                                            "y": {"type": "integer"},
                                        },
                                        "required": ["x", "y"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["where", "points"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["part", "kind", "members", "parent", "instances"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["parts"],
    "additionalProperties": False,
}


def v2_prompt(parts: list[dict[str, str]]) -> str:
    listed = "; ".join(
        f'"{p["phrase"]}" (printed label "{p["print_label"]}")'
        if p["print_label"]
        else f'"{p["phrase"]}"'
        for p in parts
    )
    return (
        f"The image is a science figure. Its parts are: {listed}. For each part, using the "
        "part name exactly as given, return:\n"
        '- kind: "area" for a part with a filled interior; "thin" for a part drawn as a '
        'line or a strip too narrow to hold a fingertip; "group" for a part made of other '
        "listed parts.\n"
        "- members: for a group, the listed parts it is made of; otherwise empty.\n"
        "- parent: the listed part this part sits inside, or empty.\n"
        "- instances: every place the part appears, in the main drawing and in any inset or "
        "enlarged view. A group has no instances. For each instance, 1 to 3 points spread "
        "across its filled interior, each as far as possible from the part's edges. For an "
        "elongated part such as a vessel or a stalk, put the points on its midline along its "
        "length. Never put a point on label text, a leader line or an outline, or on the "
        "part's tip or edge.\n"
        "Coordinates are on a 0 to 1000 grid of this image: x from the left edge, y from the "
        "top edge."
    )


def v2_body(models: Any, png: bytes, parts: list[dict[str, str]]) -> dict[str, Any]:
    return bake.spark_body(models, None, v2_prompt(parts), [png], ("PartPoints", V2_SCHEMA))


@dataclass
class Scene:
    """What the guard needs from a figure: the image, its print marks and its object area."""

    image: npt.NDArray[np.uint8]
    marks: print_marks.PrintMarks
    obj: Mask
    clean: Mask = field(init=False)

    def __post_init__(self) -> None:
        m = self.marks
        self.clean = self.obj & ~(m.text | m.line | m.ink)

    def on(self, p: Point) -> list[str]:
        x, y = p
        m = self.marks
        return [k for k, a in (("text", m.text), ("line", m.line), ("ink", m.ink)) if a[y, x]]


def scene_of(image: npt.NDArray[np.uint8]) -> Scene:
    return Scene(image, print_marks.find(image), grading.object_mask(image))


def fill_delta() -> float:
    return float(load_tactile_rules().layout.color_group_max_delta)


def window(scene: Scene, p: Point) -> tuple[slice, slice, npt.NDArray[np.float64]]:
    """The GUARD_PX disk around p as row and column slices, and each pixel's distance."""
    h, w = scene.clean.shape
    x, y = p
    rows = slice(max(0, y - GUARD_PX), min(h, y + GUARD_PX + 1))
    cols = slice(max(0, x - GUARD_PX), min(w, x + GUARD_PX + 1))
    yy, xx = np.mgrid[rows, cols]
    return rows, cols, np.hypot(xx - x, yy - y)


def common_color(scene: Scene, p: Point) -> npt.NDArray[np.float64] | None:
    """The median color of the commonest color bin (32 levels a channel) among clean pixels
    within GUARD_PX of p."""
    rows, cols, dist = window(scene, p)
    ok = scene.clean[rows, cols] & (dist <= GUARD_PX)
    px = scene.image[rows, cols][ok].astype(int)
    if not len(px):
        return None
    bins = (px // 32) @ np.array([64, 8, 1])
    top = np.bincount(bins).argmax()
    return np.asarray(np.median(px[bins == top], axis=0), np.float64)


def guard(scene: Scene, p: Point, fill: npt.NDArray[np.float64] | None) -> dict[str, Any]:
    """A point as sent: kept if clean, else moved to the nearest clean pixel of the fill
    color within GUARD_PX, else dropped."""
    on = scene.on(p)
    if not on:
        return {"px": list(p), "on": [], "sent": list(p), "moved_px": 0.0, "dropped": False}
    ref = fill if fill is not None else common_color(scene, p)
    out: dict[str, Any] = {"px": list(p), "on": on, "sent": None, "moved_px": None}
    if ref is None:
        return out | {"dropped": True}
    rows, cols, dist = window(scene, p)
    color = np.linalg.norm(scene.image[rows, cols].astype(float) - ref, axis=2)
    ok = scene.clean[rows, cols] & (dist <= GUARD_PX) & (color <= fill_delta())
    if not ok.any():
        return out | {"dropped": True}
    r, c = np.unravel_index(np.argmin(np.where(ok, dist, np.inf)), dist.shape)
    sent = [int(cols.start + c), int(rows.start + r)]
    return out | {"sent": sent, "moved_px": round(float(dist[r, c]), 1), "dropped": False}


def guard_instance(scene: Scene, points: list[Point]) -> list[dict[str, Any]]:
    clean = [p for p in points if not scene.on(p)]
    fill = (
        np.asarray(np.median([scene.image[y, x].astype(int) for x, y in clean], axis=0), float)
        if clean
        else None
    )
    return [guard(scene, p, fill) for p in points]


def negatives(
    part: str, own: list[Point], others: dict[str, list[Point]], v1: Mask | None
) -> list[dict[str, Any]]:
    """For each other part with a point inside this part's v1 mask, that point, unless it
    is within GUARD_PX of one of this part's own points."""
    if v1 is None:
        return []
    out = []
    for q, pts in others.items():
        if q == part:
            continue
        for x, y in pts:
            if v1[y, x] and all(np.hypot(x - a, y - b) > GUARD_PX for a, b in own):
                out.append({"of": q, "xy": [x, y]})
                break
    return out


def keep_pieces(mask: Mask, points: list[Point], floor_px: float) -> tuple[Mask, int]:
    """The 8-connected pieces of mask that hold a point, less pieces under floor_px, and
    how many pieces were dropped."""
    n, labels, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    held = {int(labels[y, x]) for x, y in points} - {0}
    keep = [i for i in held if st[i, cv2.CC_STAT_AREA] >= floor_px]
    return np.isin(labels, keep), (n - 1) - len(keep)


def drop_specks(mask: Mask, floor_px: float) -> Mask:
    n, labels, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= floor_px]
    return np.isin(labels, keep)


def contest(
    masks: dict[str, Mask], floor_px: float
) -> tuple[dict[str, Mask], dict[str, dict[str, int]], dict[str, int]]:
    """Each pixel claimed by several masks goes to the smallest. Returns the masks, the
    pixels each part lost to each other part, and the pixels each lost to specks after."""
    if not masks:
        return {}, {}, {}
    order = sorted(masks, key=lambda p: int(masks[p].sum()))
    shape = next(iter(masks.values())).shape
    owner = np.full(shape, -1, np.int32)
    for i, p in enumerate(order):
        owner[masks[p] & (owner < 0)] = i
    out, lost, respeck = {}, {}, {}
    for i, p in enumerate(order):
        mine = owner == i
        took = owner[masks[p] & ~mine]
        ids, counts = np.unique(took, return_counts=True)
        lost[p] = {order[int(j)]: int(c) for j, c in zip(ids, counts, strict=True)}
        cleaned = drop_specks(mine, floor_px)
        respeck[p] = int(mine.sum() - cleaned.sum())
        out[p] = cleaned
    return out, lost, respeck


def xy(p: list[int]) -> Point:
    return int(p[0]), int(p[1])


def members_of(part: str, info: dict[str, dict[str, Any]], seen: set[str]) -> list[str]:
    """A group's listed members, with member groups opened up."""
    out: list[str] = []
    for m in info[part]["members"]:
        if m in seen or m not in info:
            continue
        seen.add(m)
        out += members_of(m, info, seen) if info[m]["kind"] == "group" else [m]
    return out


class ArmAv2:
    def __init__(
        self,
        live: LiveCaller,
        fig: bake.Figure,
        parts: list[dict[str, str]],
        v1: dict[str, Mask],
        record: bool,
    ) -> None:
        self.live = live
        self.fig = fig
        self.parts = parts
        self.v1 = v1
        self.record = record
        self.models = load_tactile_rules().meta.models
        self.scene = scene_of(fig.image)
        self.floor = bake.floor_px(fig)
        self.final: dict[str, Mask] = {}
        self.kept: dict[str, Mask] = {}  # before contested pixels are resolved

    def _name(self, what: str) -> str | None:
        return f"armav2_{self.fig.name}_{what}" if self.record else None

    def to_px(self, pt: dict[str, Any]) -> Point:
        w, h = self.fig.size
        return bake.to_px(float(pt["x"]), w), bake.to_px(float(pt["y"]), h)

    async def ask_spark(self) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        res = await self.live.post_json(
            "/chat/completions",
            v2_body(self.models, self.fig.png, self.parts),
            caller=CALLER,
            model=self.models.spark,
            describe=bake.shown(self.fig.path) + ", v2 parts and points",
            units=spark_units,
            record_as=self._name("points"),
        )
        content = str(res.body["choices"][0]["message"]["content"])
        line = res.ledger_line
        meta = {
            "latency_ms": line["latency_ms"],
            "cost_usd": line["cost_usd"],
            "usage": line["usage"],
            "answer": json.loads(content),
        }
        names = {p["phrase"] for p in self.parts}
        info: dict[str, dict[str, Any]] = {}
        for item in meta["answer"]["parts"]:
            if item["part"] in names and item["part"] not in info:
                info[item["part"]] = item
        return info, meta

    async def segment(
        self, part: str, objects: list[tuple[list[Point], list[Point]]]
    ) -> tuple[list[sam_adapter.Decoded], dict[str, Any]]:
        w, h = self.fig.size
        metadata = load_prompt(s2_ground.PROMPT).template["metadata"]
        res = await self.live.post_sse(
            "/responses",
            sam_adapter.objects_request_body(
                self.models.sam, self.fig.png, (w, h), objects, metadata
            ),
            caller=CALLER,
            model=self.models.sam,
            describe=bake.shown(self.fig.path) + f", v2 {len(objects)} objects for {part}",
            units=lambda _usage: {"images": 1},
            record_as=self._name(f"sam_{bake.slug(part)}"),
        )
        meta: dict[str, Any] = {
            "latency_ms": res.latency_ms,
            "cost_usd": res.ledger_line["cost_usd"],
        }
        try:
            parsed = await sam_adapter.parse_events(res.body)
        except sam_adapter.ParseError as exc:
            return [], meta | {"parse_error": str(exc)}
        return sam_adapter.decoded(parsed), meta | {"instances": sam_adapter.instance_count(parsed)}

    def guarded_rows(self, info: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """One row per listed part, with Spark's kind, members and parent, and each
        instance's points through the guard."""
        rows: dict[str, dict[str, Any]] = {}
        for p in self.parts:
            part = p["phrase"]
            item = info.get(part)
            row: dict[str, Any] = {"part": part, "print_label": p["print_label"], "flags": []}
            rows[part] = row
            if item is None:
                row |= {"kind": None, "members": [], "parent": "", "instances": []}
                row["flags"].append("not in Spark's answer")
                continue
            row |= {k: item[k] for k in ("kind", "members", "parent")}
            row["instances"] = []
            for inst in item["instances"] if item["kind"] != "group" else []:
                guarded = guard_instance(self.scene, [self.to_px(pt) for pt in inst["points"]])
                row["instances"].append(
                    {"where": inst["where"], "grid": inst["points"], "points": guarded}
                )
                row["flags"] += [
                    f"point {g['px']} on {' and '.join(g['on'])} dropped"
                    for g in guarded
                    if g["dropped"]
                ]
        return rows

    async def segment_part(self, row: dict[str, Any], sent: dict[str, list[Point]]) -> Mask | None:
        """One SAM call for a part, one object per instance; the instance pieces that hold
        a prompt point, less specks, as one mask."""
        part = row["part"]
        insts = [i for i in row["instances"] if any(g["sent"] for g in i["points"])]
        if len(insts) > MAX_OBJECTS:
            row["flags"].append(f"{len(insts)} instances, sent the first {MAX_OBJECTS}")
            insts = insts[:MAX_OBJECTS]
        if not insts:
            row["flags"].append("no point left to send")
            return None
        negs = negatives(part, sent[part], sent, self.v1.get(part))
        row["negatives"] = negs
        objects = [
            ([xy(g["sent"]) for g in i["points"] if g["sent"]], [xy(n["xy"]) for n in negs])
            for i in insts
        ]
        decoded, row["sam"] = await self.segment(part, objects)
        by_id = {d.object_id: d for d in decoded}
        mask = np.zeros(self.fig.image.shape[:2], bool)
        for k, (inst, (pos, _)) in enumerate(zip(insts, objects, strict=True), 1):
            d = by_id.get(str(k))
            inst["object_id"] = k
            if d is None:
                inst |= {"confidence": None, "raw_px": 0, "kept_px": 0}
                row["flags"].append(f"no mask for instance {k}")
                continue
            raw = bake.full_mask(d, self.fig.size)
            piece, dropped = keep_pieces(raw, pos, self.floor)
            inst |= {
                "confidence": d.confidence,
                "raw_px": int(raw.sum()),
                "kept_px": int(piece.sum()),
                "pieces_dropped": dropped,
                "points_in_mask": [bool(raw[y, x]) for x, y in pos],
            }
            if not all(inst["points_in_mask"]):
                row["flags"].append(f"a point of instance {k} is outside its SAM mask")
            mask |= piece
        row["kept_px"] = int(mask.sum())
        return mask if mask.any() else None

    def finish(
        self, rows: dict[str, dict[str, Any]], kept: dict[str, Mask], info: dict[str, Any]
    ) -> dict[str, Mask]:
        """Contested pixels to the smaller mask, then group unions, then the flags."""
        final, lost, respeck = contest(kept, self.floor)
        for part in final:
            rows[part] |= {
                "lost_to": lost[part],
                "lost_px": sum(lost[part].values()),
                "respeck_px": respeck[part],
            }
        shape = self.fig.image.shape[:2]
        for part, row in rows.items():
            if row["kind"] != "group":
                continue
            row["unknown_members"] = [m for m in row["members"] if m not in info]
            union = np.zeros(shape, bool)
            for m in members_of(part, info, {part}):
                if m in final:
                    union |= final[m]
            if union.any():
                final[part] = union
        for part, row in rows.items():
            row["final_px"] = int(final[part].sum()) if part in final else 0
            if row["kind"] == "thin":
                row["flags"].append("thin: kept for the record, sheet use decided later")
            if not row["final_px"]:
                row["flags"].append("no mask")
        return final

    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "figure": self.fig.name,
            "image": bake.shown(self.fig.path),
            "size": list(self.fig.size),
            "cap": self.live.cap,
            "guard_px": GUARD_PX,
            "fill_delta": fill_delta(),
            "floor_px": round(self.floor, 1),
            "print_marks": {
                "words": len(self.scene.marks.words),
                "leader_segments": len(self.scene.marks.segments),
            },
        }
        if 1 + len(self.parts) > self.live.cap:
            return result | {"stopped": "the parts need more calls than the run cap"}
        info, result["spark"] = await self.ask_spark()
        rows = self.guarded_rows(info)
        sent = {
            part: [xy(g["sent"]) for i in r["instances"] for g in i["points"] if g["sent"]]
            for part, r in rows.items()
            if r["kind"] != "group"
        }
        kept: dict[str, Mask] = {}
        for part, row in rows.items():
            if row["kind"] in (None, "group"):
                continue
            mask = await self.segment_part(row, sent)
            if mask is not None:
                kept[part] = mask
        self.kept = kept
        self.final = self.finish(rows, kept, info)
        result["rows"] = list(rows.values())
        result["calls"] = self.live.calls
        result["spent_usd"] = round(self.live.meter.spent_usd, 6)
        return result


def replayer(figure: str) -> LiveCaller:
    """A caller that answers from fixtures/recorded/armav2_FIGURE_*.json, never the network."""
    rules = load_tactile_rules().meta
    return LiveCaller(
        key="unused-in-replay",
        base_url=DEFAULT_BASE,
        ledger=Ledger(Path(tempfile.mkdtemp()) / "ledger.jsonl"),
        meter=CostMeter(rules),
        cap=rules.live_call_cap,
        transport=ReplayTransport.from_files(sorted(RECORDED_DIR.glob(f"armav2_{figure}_*.json"))),
    )


def marked_view(
    image: npt.NDArray[np.uint8], mask: Mask | None, row: dict[str, Any]
) -> Image.Image:
    """The focus view of a v2 mask: positive points as crosshairs, negative points as an X,
    dropped points as a ring."""
    img = grading.focus_view(image, mask, None)
    scale = img.width / image.shape[1]
    draw = ImageDraw.Draw(img)
    for inst in row.get("instances", []):
        for g in inst["points"]:
            if g["sent"]:
                cross(draw, g["sent"], scale)
            else:
                x, y = (v * scale for v in g["px"])
                for width, color in ((5, (255, 255, 255)), (2, (200, 0, 0))):
                    draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline=color, width=width)
    for n in row.get("negatives", []):
        x, y = (v * scale for v in n["xy"])
        for width, color in ((5, (255, 255, 255)), (2, (0, 0, 0))):
            draw.line((x - 8, y - 8, x + 8, y + 8), fill=color, width=width)
            draw.line((x - 8, y + 8, x + 8, y - 8), fill=color, width=width)
    return img


def cross(draw: ImageDraw.ImageDraw, p: list[int], scale: float) -> None:
    x, y = p[0] * scale, p[1] * scale
    arm, gap = 16, 4
    for width, color in ((5, (255, 255, 255)), (2, (0, 0, 0))):
        draw.line((x - arm, y, x - gap, y), fill=color, width=width)
        draw.line((x + gap, y, x + arm, y), fill=color, width=width)
        draw.line((x, y - arm, x, y - gap), fill=color, width=width)
        draw.line((x, y + gap, x, y + arm), fill=color, width=width)


def v2_facts(row: dict[str, Any]) -> list[str]:
    out = [f"kind {row['kind']}"]
    if row["members"]:
        out.append("members " + ", ".join(row["members"]))
    if row["parent"]:
        out.append(f"inside {row['parent']}")
    for i in row["instances"]:
        moved = [g for g in i["points"] if g["on"] and not g["dropped"]]
        conf = i.get("confidence")
        n = sum(1 for g in i["points"] if g["sent"])
        out.append(
            f"{i['where']}: {n} point{'' if n == 1 else 's'} sent"
            + (f", {len(moved)} moved" if moved else "")
            + ("" if conf is None else f", confidence {conf:.3f}")
        )
    if row.get("negatives"):
        out.append("negative points at " + ", ".join(n["of"] for n in row["negatives"]))
    if row.get("lost_px"):
        out.append(f"lost {row['lost_px']} px to smaller masks")
    out.append(f"final mask {row['final_px']} px")
    return out + [f"FLAG: {f}" for f in row["flags"]]


def write_sheet(result: dict[str, Any], v1_rows: dict[str, dict[str, Any]], out_dir: Path) -> None:
    """v2.html: one part at a time with the v1 and v2 masks side by side, then a table with
    blank v2 grade columns."""
    esc = html.escape
    steps, rows = [], []
    for row in result["rows"]:
        s = bake.slug(row["part"])
        v1 = v1_rows.get(row["part"], {})
        v1_facts = [
            f"v1 point {v1.get('point_px')}",
            "confidence "
            + ", ".join(f"{c:.3f}" for c in v1.get("confidences") or [] if c is not None),
        ]
        steps.append(
            {
                "part": row["part"],
                "label": row["print_label"] or "none",
                "a": f"img/v2sheet_v1_{s}.jpg",
                "b": f"img/v2sheet_v2_{s}.jpg",
                "a_facts": v1_facts,
                "b_facts": v2_facts(row),
            }
        )
        facts = "".join(
            f"<li{' class=flag' if f.startswith('FLAG') else ''}>{esc(f)}</li>"
            for f in v2_facts(row)
        )
        rows.append(
            f"<tr><th>{esc(row['part'])}<br><small>label: {esc(row['print_label'] or 'none')}"
            f"</small></th><td><img src='img/v2sheet_v1_{s}.jpg' alt=''></td>"
            f"<td><img src='img/v2sheet_v2_{s}.jpg' alt=''><ul>{facts}</ul></td>"
            "<td></td><td></td></tr>"
        )
    sp = result["spark"]
    summary = [
        f"Image {result['image']}, {result['size'][0]} x {result['size'][1]} px",
        f"Calls {result['calls']}, spent ${result['spent_usd']}. Spark call "
        f"{sp['latency_ms']} ms, ${sp['cost_usd']}",
        f"Guard: {result['guard_px']} px, fill color within {result['fill_delta']}. Speck "
        f"floor {result['floor_px']} px",
    ]
    view = bake.step_view(
        steps,
        ("v1: one Spark point, SAM mask", "v2: guarded points, SAM, post-processed"),
        "The figure is at 30% and the mask at full strength. In v2, crosshairs are the "
        "points sent, an X is a negative point and a red ring is a dropped point.",
        ("v1", "v2"),
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>S2 Arm A v2: {esc(result["figure"])}</title>
<style>
body {{ font: 15px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #111; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #999; padding: 6px; vertical-align: top; }}
td img {{ width: 360px; display: block; }}
ul {{ margin: 4px 0; padding-left: 18px; font-size: 13px; }}
.flag {{ color: #a00; font-weight: 600; }}
#step {{ border: 2px solid #333; padding: 12px; margin-bottom: 24px; }}
#name {{ font-size: 40px; font-weight: 700; margin: 8px 0 0; }}
#label {{ margin: 0 0 8px; color: #444; }}
.nav {{ display: flex; gap: 12px; align-items: center; }}
.nav button {{ font-size: 18px; padding: 6px 16px; }}
.pair {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.pair figure {{ margin: 0; flex: 1 1 420px; }}
.pair img {{ width: 100%; border: 1px solid #999; }}
</style></head><body>
<h1>S2 Arm A v2: {esc(result["figure"])}</h1>
<ul>{"".join(f"<li>{esc(s)}</li>" for s in summary)}</ul>
{view}
<h2>Parts</h2>
<table><thead><tr><th>Part</th><th>v1</th><th>v2</th><th>v2 grade</th><th>Reason</th></tr>
</thead><tbody>
{"".join(rows)}
</tbody></table></body></html>
"""
    (out_dir / "v2.html").write_text(page, encoding="utf-8")


def save_views(
    fig: bake.Figure,
    result: dict[str, Any],
    final: dict[str, Mask],
    v1_masks: dict[str, Mask],
    v1_rows: dict[str, dict[str, Any]],
    out_dir: Path,
) -> None:
    d = out_dir / "img"
    d.mkdir(parents=True, exist_ok=True)
    for row in result["rows"]:
        s = bake.slug(row["part"])
        point = v1_rows.get(row["part"], {}).get("point_px")
        grading.focus_view(fig.image, v1_masks.get(row["part"]), point).save(
            d / f"v2sheet_v1_{s}.jpg", quality=85
        )
        marked_view(fig.image, final.get(row["part"]), row).save(
            d / f"v2sheet_v2_{s}.jpg", quality=85
        )


async def run_figure(
    live: LiveCaller, name: str, record: bool, write: str
) -> tuple[ArmAv2, dict[str, Any]]:
    """write is "all" for a live run (results_v2.json, v2.html and img/), "images" to redraw
    img/ from a replay, or "none"."""
    out_dir = bake.OUT_ROOT / name
    v1_result = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    fig, v1 = await grading.replay_masks(name)
    run = ArmAv2(live, fig, v1_result["parts"], v1["a"], record)
    result = await run.run()
    if write == "none" or "stopped" in result:
        return run, result
    v1_rows = {r["part"]: r for r in v1_result["arm_a_rows"]}
    save_views(fig, result, run.final, v1["a"], v1_rows, out_dir)
    if write == "all":
        (out_dir / "results_v2.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
        write_sheet(result, v1_rows, out_dir)
    return run, result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("figure", choices=sorted(bake.FIGURES))
    ap.add_argument("--record", action="store_true", help="save each call to fixtures/recorded/")
    ap.add_argument("--replay", action="store_true", help="redraw from the recorded calls, offline")
    args = ap.parse_args()
    if args.replay:
        _, result = asyncio.run(run_figure(replayer(args.figure), args.figure, False, "images"))
        print(f"redrew {bake.OUT_ROOT / args.figure / 'img'} from {result.get('calls')} calls")
        return
    live = LiveCaller.from_env(load_tactile_rules().meta, recorder=Recorder())
    try:
        _, result = asyncio.run(run_figure(live, args.figure, args.record, "all"))
    except LiveCallError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    if "stopped" in result:
        print(f"stopped: {result['stopped']}")
    print(f"spent ${live.meter.spent_usd:.5f} on {live.calls} calls")


if __name__ == "__main__":
    main()
