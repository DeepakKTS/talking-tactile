"""The S2 bake-off of Oct 29 (Gate A step 4.1b), kept to replay v1 Arm A for the scorer.

The bake-off compared two ways to find a figure's parts. Arm A: one Spark call points to
each part on the docs' 0-1000 grid, code maps the point to source pixels, and one SAM point
prompt per part segments it. Arm B: code found closed regions and Spark named them. S2 is
locked on Arm A v2f (app/pipeline/s2_points.py); Arm B's code is deleted, and its results,
grades and sheets stay under eval/s2-bakeoff/ as data. The passing masks of both arms are
saved there too (FIGURE/reference/).

Here: the S1 listing and Arm A, replayed from fixtures/recorded/bakeoff_*.json with
replay_arm_a, never live."""

import base64
import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from app.config import MetaModels, load_tactile_rules
from app.meta import sam_adapter
from app.meta.cost import CostMeter
from app.meta.live import DEFAULT_BASE, Ledger, LiveCaller, spark_units
from app.meta.record import ReplayTransport
from app.meta.sam_diagnostic import checks
from app.meta.smoke import HEART
from app.paths import FIXTURES_DIR, RECORDED_DIR, REPO_ROOT
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


def s1_list_body(models: MetaModels, png: bytes) -> dict[str, Any]:
    """The S1 listing call: the S1 prompt and schema on one figure."""
    s1 = load_prompt("s1_understand.v1.json").template
    return spark_body(models, s1["system"], s1["user"], [png], ("FigureUnderstanding", S1_SCHEMA))


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


def shown(path: Path) -> str:
    """A path as the ledger and the sheet show it: from the repo root when it is inside."""
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else path.name


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class Bakeoff:
    """The listing and Arm A, as the live run made them."""

    def __init__(self, live: LiveCaller, fig: Figure) -> None:
        self.live = live
        self.fig = fig
        self.models = load_tactile_rules().meta.models
        self.masks: dict[str, npt.NDArray[np.bool_]] = {}  # Arm A's full-size mask per part

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
        )
        content = str(res.body["choices"][0]["message"]["content"])
        line = res.ledger_line
        return content, {
            "latency_ms": line["latency_ms"],
            "cost_usd": line["cost_usd"],
            "usage": line["usage"],
        }

    async def list_parts(self) -> tuple[list[dict[str, str]], dict[str, Any]]:
        content, meta = await self._spark("list", s1_list_body(self.models, self.fig.png))
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
                mask |= sam_adapter.full_mask(inst, (w, h))
            row |= {
                "instances": sam_adapter.instance_count(parsed),
                "confidences": [i.confidence for i in insts],
                "masks": [checks(i, (h, w)) for i in insts],
                "mask_px": int(mask.sum()),
                "point_in_mask": bool(mask[point[1], point[0]]),
            }
            if insts:
                self.masks[part] = mask
            rows.append(row)
        return rows, meta

    async def run(self) -> dict[str, Any]:
        parts_full, listing = await self.list_parts()
        parts = [p["phrase"] for p in parts_full]
        rows, meta = await self.arm_a(parts)
        return {
            "figure": self.fig.name,
            "parts": parts_full,
            "listing": listing,
            "arm_a_rows": rows,
            "arm_a": meta,
            "calls": self.live.calls,
        }


def replayer(figure: str) -> LiveCaller:
    """A caller that answers from fixtures/recorded/bakeoff_FIGURE_*.json, never the network.
    The Arm B naming call is recorded there too and never asked for now."""
    rules = load_tactile_rules().meta
    return LiveCaller(
        key="unused-in-replay",
        base_url=DEFAULT_BASE,
        ledger=Ledger(Path(tempfile.mkdtemp()) / "ledger.jsonl"),
        meter=CostMeter(rules),
        cap=rules.live_call_cap,
        transport=ReplayTransport.from_files(sorted(RECORDED_DIR.glob(f"bakeoff_{figure}_*.json"))),
    )


async def replay_arm_a(
    name: str,
) -> tuple[Figure, dict[str, Any], dict[str, npt.NDArray[np.bool_]]]:
    """A figure, its replayed run, and Arm A's mask per part."""
    fig = load_figure(name, FIGURES[name])
    run = Bakeoff(replayer(name), fig)
    return fig, await run.run(), run.masks
