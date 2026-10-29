"""S2 bake-off, Gate A step 4.1b: two ways to find a figure's parts, run on one figure.

    LIVE=1 uv run python -m app.meta.s2_bakeoff FIGURE [--record]

FIGURE is heart, flower or japan_regions. First Spark lists the parts with the S1 prompt
and schema (one call). Then:

Arm A, Spark points and SAM segments. One Spark call returns a point inside each part on
the docs' 0-1000 grid of the image it was sent. Code maps it to integer source pixels,
floor(v * size / 1000) clamped to the image, which is the space SAM object prompts use.
One SAM point-prompt call per part.

Arm B, code finds regions and Spark names them. app.geometry.closed_regions finds closed
regions with no model; one Spark call, given the figure and the regions numbered on an
overlay, maps each part to region ids. No SAM call.

Writes eval/s2-bakeoff/FIGURE/: results.json with the counts and measurements, index.html
with each part's mask from each arm side by side and a blank pass/fail column, and the
images under img/ (git-ignored). Nothing here grades quality. A run needs 3 + parts calls
and stops after the listing if that would pass the run's call cap."""

import argparse
import asyncio
import base64
import html
import io
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

from app.config import MetaModels, load_tactile_rules
from app.geometry.closed_regions import Region, closed_regions
from app.geometry.scale import fit_to_page
from app.meta import sam_adapter
from app.meta.live import LiveCaller, LiveCallError, spark_units
from app.meta.record import Recorder
from app.meta.sam_diagnostic import checks
from app.meta.smoke import HEART
from app.models.regions import PageSize
from app.paths import FIXTURES_DIR, REPO_ROOT
from app.pipeline import s2_ground
from app.prompts import load_prompt

FIGURES = {
    "heart": HEART,
    "flower": FIXTURES_DIR / "eval" / "flower.png",
    "japan_regions": FIXTURES_DIR / "eval" / "japan_regions.png",
}
OUT_ROOT = REPO_ROOT / "eval" / "s2-bakeoff"
CALLER = "s2_bakeoff"
EFFORT = "medium"  # the S1 spike's effort for reading a figure (spikes/muse-spark.md)
GRID = 1000  # Spark's grounding grid, docs: image-understanding

# Arm B constants, chosen Oct 29 on heart.png, flower.png and japan_regions.png:
INK_BELOW = 64  # black outlines and borders are under it; fills, red leader lines are not
CLOSE_PX = 5  # seals breaks under 5 px, about 0.5 mm on the sheet, far under min_gap_mm
PAGE: PageSize = "letter"

# The S1 schema from the Spark spike (spikes/spark_spike.py), so the list is the one S1
# would make.
S1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "figure_type": {
            "enum": ["labeled_diagram", "bar_chart", "line_graph", "map", "flow_diagram", "other"]
        },
        "title": {"type": "string"},
        "summary": {"type": "string", "description": "Two sentences at most. No sight words."},
        "parts": {
            "type": "array",
            "maxItems": 25,
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {
                        "type": "string",
                        "description": "Short noun phrase SAM can segment, "
                        "such as 'left ventricle'",
                    },
                    "print_label": {
                        "type": "string",
                        "description": "The exact printed label text that points to this part, "
                        "or empty",
                    },
                },
                "required": ["phrase", "print_label"],
                "additionalProperties": False,
            },
        },
        "color_carries_meaning": {"type": "boolean"},
        "verdict": {"enum": ["make_tactile", "split_two_sheets", "describe_only"]},
        "verdict_reason": {"type": "string"},
    },
    "required": [
        "figure_type",
        "title",
        "summary",
        "parts",
        "color_carries_meaning",
        "verdict",
        "verdict_reason",
    ],
    "additionalProperties": False,
}

NAMING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "string"},
                    "region_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["part", "region_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["parts"],
    "additionalProperties": False,
}


def quoted(parts: list[str]) -> str:
    return ", ".join(f'"{p}"' for p in parts)


def points_prompt(parts: list[str]) -> str:
    """The docs' point-mode prompt (image-understanding), with our parts."""
    return (
        f"Point to each of the following objects in the image: {quoted(parts)}. "
        'For each object, answer in the format {"object_name": "<name>", "x": <int>, "y": <int>}. '
        "The coordinates should be in the 0-1000 range. Return a JSON array of results. "
        "If you cannot find an object, omit it from the results."
    )


def naming_prompt(parts: list[str], n_regions: int) -> str:
    return (
        "The first image is a science figure. The second is the same figure with its closed "
        f"regions tinted and numbered 1 to {n_regions}. The parts of the figure are: "
        f"{quoted(parts)}. For each part, give the numbers of the regions that make it up. "
        "A part may span several regions. Leave out any region that belongs to none of these "
        "parts, and any part you cannot find."
    )


def to_px(v: float, size: int) -> int:
    """A 0-1000 grid value to an integer pixel of an axis size px long. Spark can answer a
    little outside the grid (docs), so the result is clamped to the image."""
    return min(size - 1, max(0, math.floor(v * size / GRID)))


def parse_points(content: str, parts: list[str]) -> dict[str, tuple[float, float]]:
    """The first JSON array in Spark's answer, as {part: (x, y)} on the 0-1000 grid. Names
    not in parts are left out, and the first point per part wins."""
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match is None:
        return {}
    out: dict[str, tuple[float, float]] = {}
    for item in json.loads(match.group(0)):
        name = item.get("object_name") if isinstance(item, dict) else None
        if name in parts and name not in out:
            out[name] = (float(item["x"]), float(item["y"]))
    return out


def calls_needed(n_parts: int) -> int:
    return 1 + 1 + n_parts + 1  # list, points, one SAM call per part, naming


def png_of(image: npt.NDArray[np.uint8]) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return buf.getvalue()


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def spark_body(
    models: MetaModels,
    system: str | None,
    text: str,
    images: list[bytes],
    schema: tuple[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content += [{"type": "image_url", "image_url": {"url": data_url(p)}} for p in images]
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    if system is not None:
        messages.insert(0, {"role": "system", "content": system})
    body: dict[str, Any] = {
        "model": models.spark,
        "reasoning_effort": EFFORT,
        "messages": messages,
    }
    if schema is not None:
        name, js = schema
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": name, "schema": js},
        }
    return body


@dataclass(frozen=True)
class Figure:
    name: str
    path: Path
    image: npt.NDArray[np.uint8]

    @property
    def size(self) -> tuple[int, int]:
        return int(self.image.shape[1]), int(self.image.shape[0])

    @property
    def png(self) -> bytes:
        return self.path.read_bytes()


def load_figure(name: str, path: Path) -> Figure:
    return Figure(name, path, np.asarray(Image.open(path).convert("RGB")))


def floor_px(fig: Figure) -> float:
    """S3's speck floor, speck_max_area_mm2, in pixels of this figure on a letter page."""
    rules = load_tactile_rules()
    w, h = fig.size
    mm_per_px = fit_to_page(w, h, PAGE, rules.page).mm_per_px
    return rules.reconcile.speck_max_area_mm2 / mm_per_px**2


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def numbered_overlay(
    fig: Figure, labels: npt.NDArray[np.int32], regions: list[Region]
) -> npt.NDArray[np.uint8]:
    """Each region tinted a color of its own, its id at its anchor in black on white."""
    rng = np.random.default_rng(7)
    colors = rng.integers(60, 230, size=(len(regions) + 1, 3)).astype(np.float32)
    out = fig.image.astype(np.float32)
    inside = labels > 0
    out[inside] = out[inside] * 0.45 + colors[labels[inside]] * 0.55
    img = Image.fromarray(out.astype(np.uint8))
    draw = ImageDraw.Draw(img)
    f = font(max(14, fig.size[0] // 70))
    for r in regions:
        draw.text(
            r.anchor,
            str(r.id),
            fill=(0, 0, 0),
            font=f,
            anchor="mm",
            stroke_width=3,
            stroke_fill=(255, 255, 255),
        )
    return np.asarray(img)


def part_view(
    fig: Figure, mask: npt.NDArray[np.bool_] | None, point: tuple[int, int] | None
) -> Image.Image:
    """The figure with one mask in red and, for Arm A, its prompt point in blue."""
    out = fig.image.astype(np.float32)
    if mask is not None:
        out[mask] = out[mask] * 0.4 + np.array([255.0, 0.0, 0.0]) * 0.6
    img = Image.fromarray(out.astype(np.uint8))
    if point is not None:
        draw = ImageDraw.Draw(img)
        r = max(8, fig.size[0] // 120)
        x, y = point
        draw.ellipse((x - r, y - r, x + r, y + r), outline=(0, 60, 255), width=max(3, r // 3))
        draw.line((x - 2 * r, y, x + 2 * r, y), fill=(0, 60, 255), width=2)
        draw.line((x, y - 2 * r, x, y + 2 * r), fill=(0, 60, 255), width=2)
    scale = 720 / max(img.size)
    return img.resize(
        (round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS
    )


def full_mask(inst: sam_adapter.Decoded, size: tuple[int, int]) -> npt.NDArray[np.bool_]:
    """A decoded raster scaled to its bounds, nearest pixel, on a full-size array."""
    w, h = size
    out = np.zeros((h, w), bool)
    if inst.raster is None:
        return out
    left, top, right, bottom = inst.bounds
    rh, rw = inst.raster.shape
    rows = np.arange(bottom - top) * rh // (bottom - top)
    cols = np.arange(right - left) * rw // (right - left)
    out[top:bottom, left:right] = inst.raster[rows][:, cols][: h - top, : w - left]
    return out


def shown(path: Path) -> str:
    """A path as the ledger and the sheet show it: from the repo root when it is inside."""
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else path.name


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class Bakeoff:
    def __init__(self, live: LiveCaller, fig: Figure, record: bool, out_dir: Path) -> None:
        self.live = live
        self.fig = fig
        self.record = record
        self.out_dir = out_dir
        self.models = load_tactile_rules().meta.models

    def _name(self, what: str) -> str | None:
        return f"bakeoff_{self.fig.name}_{what}" if self.record else None

    def _describe(self, what: str) -> str:
        w, h = self.fig.size
        return f"{shown(self.fig.path)} {w}x{h}, {what}"

    async def _spark(self, what: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        res = await self.live.post_json(
            "/chat/completions",
            body,
            caller=CALLER,
            model=self.models.spark,
            describe=self._describe(what),
            units=spark_units,
            record_as=self._name(what),
        )
        content = str(res.body["choices"][0]["message"]["content"])
        line = res.ledger_line
        return content, {
            "latency_ms": line["latency_ms"],
            "cost_usd": line["cost_usd"],
            "usage": line["usage"],
        }

    async def list_parts(self) -> tuple[list[dict[str, str]], dict[str, Any]]:
        s1 = load_prompt("s1_understand.v1.json").template
        body = spark_body(
            self.models,
            s1["system"],
            s1["user"],
            [self.fig.png],
            ("FigureUnderstanding", S1_SCHEMA),
        )
        content, meta = await self._spark("list", body)
        understanding = json.loads(content)
        return understanding["parts"], meta | {"understanding": understanding}

    async def arm_a(self, parts: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        content, meta = await self._spark(
            "points", spark_body(self.models, None, points_prompt(parts), [self.fig.png], None)
        )
        grid = parse_points(content, parts)
        meta |= {"answer": content}
        w, h = self.fig.size
        rows = []
        metadata = load_prompt(s2_ground.PROMPT).template["metadata"]
        for part in parts:
            row: dict[str, Any] = {"part": part, "grid_point": grid.get(part)}
            if part not in grid:
                rows.append(row | {"point_px": None, "instances": None})
                continue
            gx, gy = grid[part]
            point = (to_px(gx, w), to_px(gy, h))
            res = await self.live.post_sse(
                "/responses",
                sam_adapter.point_request_body(
                    self.models.sam, self.fig.png, (w, h), point, metadata
                ),
                caller=CALLER,
                model=self.models.sam,
                describe=self._describe(f"point {point[0]},{point[1]} for {part}"),
                units=lambda _usage: {"images": 1},
                record_as=self._name(f"sam_{slug(part)}"),
            )
            row |= {
                "point_px": list(point),
                "latency_ms": res.latency_ms,
                "cost_usd": res.ledger_line["cost_usd"],
            }
            try:
                parsed = await sam_adapter.parse_events(res.body)
            except sam_adapter.ParseError as exc:
                rows.append(row | {"instances": None, "parse_error": str(exc)})
                continue
            insts = sam_adapter.decoded(parsed)
            mask = np.zeros((h, w), bool)
            for inst in insts:
                mask |= full_mask(inst, (w, h))
            row |= {
                "instances": len(sam_adapter.instances(parsed)),
                "confidences": [i.confidence for i in insts],
                "masks": [checks(i, (h, w)) for i in insts],
                "mask_px": int(mask.sum()),
                "point_in_mask": bool(mask[point[1], point[0]]),
            }
            self._save(f"a_{slug(part)}", part_view(self.fig, mask if insts else None, point))
            rows.append(row)
        return rows, meta

    async def arm_b(self, parts: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        floor = floor_px(self.fig)
        labels, regions = closed_regions(
            self.fig.image, ink_below=INK_BELOW, close_px=CLOSE_PX, floor_px=floor
        )
        overlay = numbered_overlay(self.fig, labels, regions)
        self._save("b_regions", Image.fromarray(overlay), full=True)
        body = spark_body(
            self.models,
            None,
            naming_prompt(parts, len(regions)),
            [self.fig.png, png_of(overlay)],
            ("RegionNames", NAMING_SCHEMA),
        )
        content, meta = await self._spark("name_regions", body)
        valid = {r.id for r in regions}
        named: dict[str, list[int]] = {}
        for item in json.loads(content)["parts"]:
            if item["part"] in parts and item["part"] not in named:
                named[item["part"]] = [int(i) for i in item["region_ids"]]
        rows = []
        for part in parts:
            ids = named.get(part)
            row: dict[str, Any] = {"part": part, "region_ids": ids}
            if ids:
                good = [i for i in ids if i in valid]
                mask = np.isin(labels, good)
                row |= {
                    "invalid_ids": [i for i in ids if i not in valid],
                    "mask_px": int(mask.sum()),
                }
                self._save(f"b_{slug(part)}", part_view(self.fig, mask, None))
            rows.append(row)
        assigned = {i for ids in named.values() for i in ids if i in valid}
        meta |= {
            "ink_below": INK_BELOW,
            "close_px": CLOSE_PX,
            "floor_px": round(floor, 1),
            "regions": len(regions),
            "regions_assigned": len(assigned),
            "regions_unassigned": len(valid - assigned),
            "answer": json.loads(content),
        }
        return rows, meta

    def _save(self, name: str, img: Image.Image, full: bool = False) -> None:
        d = self.out_dir / "img"
        d.mkdir(parents=True, exist_ok=True)
        if full:
            scale = 1400 / max(img.size)
            img = img.resize(
                (round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS
            )
        img.convert("RGB").save(d / f"{name}.jpg", quality=82)

    async def run(self) -> dict[str, Any]:
        parts_full, listing = await self.list_parts()
        parts = [p["phrase"] for p in parts_full]
        result: dict[str, Any] = {
            "figure": self.fig.name,
            "image": shown(self.fig.path),
            "size": list(self.fig.size),
            "parts": parts_full,
            "listing": listing,
            "calls_needed": calls_needed(len(parts)),
            "cap": self.live.cap,
        }
        if calls_needed(len(parts)) > self.live.cap:
            return result | {"stopped": "the parts need more calls than the run cap"}
        result["arm_a_rows"], result["arm_a"] = await self.arm_a(parts)
        result["arm_b_rows"], result["arm_b"] = await self.arm_b(parts)
        result["spent_usd"] = round(self.live.meter.spent_usd, 6)
        result["calls"] = self.live.calls
        return result


def write_sheet(result: dict[str, Any], out_dir: Path) -> None:
    """index.html: one row per part, each arm's mask and numbers, a blank pass/fail column."""
    esc = html.escape
    a_rows = {r["part"]: r for r in result.get("arm_a_rows", [])}
    b_rows = {r["part"]: r for r in result.get("arm_b_rows", [])}

    def cell(img: str | None, facts: list[str]) -> str:
        pic = f'<img src="img/{img}.jpg" alt="">' if img else "<p>no mask</p>"
        return f"<td>{pic}<ul>{''.join(f'<li>{esc(f)}</li>' for f in facts)}</ul></td>"

    rows = []
    for p in result["parts"]:
        part = p["phrase"]
        a, b = a_rows.get(part, {}), b_rows.get(part, {})
        a_facts = [f"grid point {a.get('grid_point')}", f"pixel point {a.get('point_px')}"]
        if a.get("instances") is not None:
            a_facts += [
                f"instances {a['instances']}",
                f"confidence {[round(c, 3) for c in a['confidences'] if c is not None]}",
                f"point inside the mask {a['point_in_mask']}",
                f"mask px {a['mask_px']}",
                f"latency {a['latency_ms']} ms, cost ${a['cost_usd']}",
            ]
            for m in a["masks"]:
                a_facts.append(
                    f"raster {m.get('raster_hw')} for bounds {m.get('bounds')}, "
                    f"scale {m.get('raster_scale')}"
                )
        b_facts = [f"region ids {b.get('region_ids')}"]
        if b.get("region_ids"):
            b_facts += [f"invalid ids {b['invalid_ids']}", f"mask px {b['mask_px']}"]
        a_img = f"a_{slug(part)}" if a.get("instances") else None
        b_img = f"b_{slug(part)}" if b.get("region_ids") else None
        rows.append(
            f"<tr><th>{esc(part)}<br><small>label: {esc(p['print_label'] or 'none')}</small></th>"
            f"{cell(a_img, a_facts)}{cell(b_img, b_facts)}<td></td><td></td></tr>"
        )
    b = result.get("arm_b", {})
    a = result.get("arm_a", {})
    summary = [
        f"Image {result['image']}, {result['size'][0]} x {result['size'][1]} px",
        f"Parts listed by Spark: {len(result['parts'])}. Calls {result.get('calls')}, "
        f"spent ${result.get('spent_usd')}",
        f"Arm A points call: {a.get('latency_ms')} ms, ${a.get('cost_usd')}",
        f"Arm B: ink below {b.get('ink_below')}, closing {b.get('close_px')} px square, floor "
        f"{b.get('floor_px')} px. Regions {b.get('regions')}, assigned "
        f"{b.get('regions_assigned')}, unassigned {b.get('regions_unassigned')}. Naming call "
        f"{b.get('latency_ms')} ms, ${b.get('cost_usd')}",
    ]
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>S2 bake-off: {esc(result["figure"])}</title>
<style>
body {{ font: 15px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #111; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #999; padding: 6px; vertical-align: top; }}
td img {{ width: 360px; display: block; }}
td:nth-child(4), td:nth-child(5) {{ min-width: 90px; }}
ul {{ margin: 4px 0; padding-left: 18px; font-size: 13px; }}
.regions {{ max-width: 100%; }}
</style></head><body>
<h1>S2 bake-off: {esc(result["figure"])}</h1>
<ul>{"".join(f"<li>{esc(s)}</li>" for s in summary)}</ul>
<h2>Arm B regions as sent to Spark</h2>
<img class="regions" src="img/b_regions.jpg" alt="The figure with its regions numbered">
<h2>Parts</h2>
<table><tr><th>Part</th><th>Arm A: Spark point, SAM mask</th>
<th>Arm B: code regions named by Spark</th><th>Arm A pass/fail</th><th>Arm B pass/fail</th></tr>
{"".join(rows)}
</table></body></html>
"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


async def bake(live: LiveCaller, fig: Figure, record: bool, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = await Bakeoff(live, fig, record, out_dir).run()
    (out_dir / "results.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if "stopped" not in result:
        write_sheet(result, out_dir)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("figure", choices=sorted(FIGURES))
    ap.add_argument("--record", action="store_true", help="save each call to fixtures/recorded/")
    args = ap.parse_args()
    live = LiveCaller.from_env(load_tactile_rules().meta, recorder=Recorder())
    fig = load_figure(args.figure, FIGURES[args.figure])
    try:
        result = asyncio.run(bake(live, fig, args.record, OUT_ROOT / args.figure))
    except LiveCallError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    if "stopped" in result:
        print(
            f"stopped after the listing: {result['stopped']} "
            f"({result['calls_needed']} > {result['cap']})"
        )
    print(json.dumps({k: result.get(k) for k in ("figure", "calls", "spent_usd")}))
    print(f"spent ${live.meter.spent_usd:.5f} on {live.calls} calls")


if __name__ == "__main__":
    main()
