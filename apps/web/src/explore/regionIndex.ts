// Which region is under a point in sheet mm. A bounding box check first, then point in
// polygon, smallest region first so a child wins over its parent. An outline can be shrunk
// (inset above 0) or grown (below 0) by a margin, measured as the distance to its nearest
// edge, which is what the hysteresis in the touch state machine needs.
import type { ExploreConfig } from "../shared/config";
import type { Region, RegionsFile } from "../shared/regions";
import type { Pt } from "./homography";

export interface IndexedRegion {
  id: string;
  label: string;
  region: Region;
  polygon: readonly Pt[];
  /** min x, min y, max x, max y */
  box: readonly [number, number, number, number];
  area: number;
  /** A point inside the region: regions.json centroid_mm, which is placed inside. */
  centroid: Pt;
  earconHz: number;
}

export function pointInPolygon(poly: readonly Pt[], p: Pt): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (!a || !b) continue;
    if (a[1] > p[1] !== b[1] > p[1]) {
      const x = a[0] + ((p[1] - a[1]) * (b[0] - a[0])) / (b[1] - a[1]);
      if (p[0] < x) inside = !inside;
    }
  }
  return inside;
}

function edgeDistance(poly: readonly Pt[], p: Pt): number {
  let best = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (!a || !b) continue;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
    best = Math.min(best, Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)));
  }
  return best;
}

/** Distance to the nearest edge, positive inside the polygon and negative outside. */
export function signedDistance(poly: readonly Pt[], p: Pt): number {
  const d = edgeDistance(poly, p);
  return pointInPolygon(poly, p) ? d : -d;
}

function area(poly: readonly Pt[]): number {
  let s = 0;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (a && b) s += b[0] * a[1] - a[0] * b[1];
  }
  return Math.abs(s) / 2;
}

function box(poly: readonly Pt[]): IndexedRegion["box"] {
  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export class RegionIndex {
  /** Smallest area first. */
  readonly regions: readonly IndexedRegion[];
  private readonly ids: ReadonlyMap<string, IndexedRegion>;

  constructor(
    readonly file: RegionsFile,
    cfg: ExploreConfig,
  ) {
    const pitch = new Map<string, number>(file.textures.map((t) => [t.id, t.earcon_hz]));
    this.regions = file.regions
      .map((r): IndexedRegion => {
        const polygon = r.polygon_mm.map(([x, y]) => [x, y] as const);
        const b = box(polygon);
        return {
          id: r.id,
          label: r.label,
          region: r,
          polygon,
          box: b,
          area: area(polygon),
          centroid: r.centroid_mm ? [r.centroid_mm[0], r.centroid_mm[1]] : [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2],
          earconHz: (r.texture !== undefined ? pitch.get(r.texture) : undefined) ?? cfg.earcons.default_hz,
        };
      })
      .sort((a, b) => a.area - b.area || (a.id < b.id ? -1 : 1));
    this.ids = new Map(this.regions.map((r) => [r.id, r]));
  }

  byId(id: string): IndexedRegion | undefined {
    return this.ids.get(id);
  }

  /** True when p is inside r's outline shrunk by insetMm (grown when insetMm is negative). */
  contains(r: IndexedRegion, p: Pt, insetMm: number): boolean {
    const grow = Math.max(0, -insetMm);
    const [x0, y0, x1, y1] = r.box;
    if (p[0] < x0 - grow || p[0] > x1 + grow || p[1] < y0 - grow || p[1] > y1 + grow) return false;
    const inside = pointInPolygon(r.polygon, p);
    if (insetMm > 0) return inside && edgeDistance(r.polygon, p) >= insetMm;
    if (inside) return true;
    return insetMm < 0 && edgeDistance(r.polygon, p) <= grow;
  }

  /** The smallest region whose outline, shrunk by insetMm, holds p. */
  hit(p: Pt, insetMm: number): IndexedRegion | null {
    for (const r of this.regions) if (this.contains(r, p, insetMm)) return r;
    return null;
  }
}
