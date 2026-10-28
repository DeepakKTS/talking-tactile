"""Exact shapes for the synthetic figure, in figure-area millimeters (origin at the top-left
of the figure area, y down). Each shape rasterizes exactly by testing pixel centers."""

import math
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from app.models.mask import BoolImage

Coords = NDArray[np.float64]

# Vertices used to write curved outlines into truth.json. Well under the 200 point limit.
_ARC_STEPS = 16
_ELLIPSE_STEPS = 144


class Shape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["rect", "rounded_rect", "ellipse"]
    x0: float
    y0: float
    x1: float
    y1: float
    radius: float = 0.0  # corner radius for rounded_rect

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def grown(self, d: float) -> "Shape":
        """The exact outward offset by d mm (a rect grows into a rounded rect)."""
        kind = "rounded_rect" if self.kind == "rect" else self.kind
        return Shape(
            kind=kind,
            x0=self.x0 - d,
            y0=self.y0 - d,
            x1=self.x1 + d,
            y1=self.y1 + d,
            radius=self.radius + d if kind == "rounded_rect" else 0.0,
        )

    def inside(self, x: Coords, y: Coords) -> BoolImage:
        cx, cy = self.center
        hw, hh = self.width / 2, self.height / 2
        if self.kind == "rect":
            out: BoolImage = (np.abs(x - cx) <= hw) & (np.abs(y - cy) <= hh)
            return out
        if self.kind == "ellipse":
            out = ((x - cx) / hw) ** 2 + ((y - cy) / hh) ** 2 <= 1.0
            return out
        r = self.radius
        dx = np.maximum(np.abs(x - cx) - (hw - r), 0.0)
        dy = np.maximum(np.abs(y - cy) - (hh - r), 0.0)
        out = (np.abs(x - cx) <= hw) & (np.abs(y - cy) <= hh) & (dx**2 + dy**2 <= r**2)
        return out

    def area(self) -> float:
        if self.kind == "rect":
            return self.width * self.height
        if self.kind == "ellipse":
            return math.pi * self.width * self.height / 4
        r = self.radius
        return self.width * self.height - (4 - math.pi) * r * r

    def outline(self) -> list[tuple[float, float]]:
        """Outline vertices in order, clockwise on screen (y down)."""
        if self.kind == "rect":
            return [(self.x0, self.y0), (self.x1, self.y0), (self.x1, self.y1), (self.x0, self.y1)]
        cx, cy = self.center
        if self.kind == "ellipse":
            hw, hh = self.width / 2, self.height / 2
            return [
                (
                    cx + hw * math.cos(2 * math.pi * i / _ELLIPSE_STEPS),
                    cy + hh * math.sin(2 * math.pi * i / _ELLIPSE_STEPS),
                )
                for i in range(_ELLIPSE_STEPS)
            ]
        r = self.radius
        corners = [
            (self.x1 - r, self.y0 + r, -math.pi / 2),
            (self.x1 - r, self.y1 - r, 0.0),
            (self.x0 + r, self.y1 - r, math.pi / 2),
            (self.x0 + r, self.y0 + r, math.pi),
        ]
        points: list[tuple[float, float]] = []
        for ccx, ccy, start in corners:
            for i in range(_ARC_STEPS + 1):
                a = start + (math.pi / 2) * i / _ARC_STEPS
                points.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
        return points
