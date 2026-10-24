// Shared test inputs for Explore: the synthetic figure's regions.json, exactly as the
// pipeline writes it (a pytest keeps the fixture in step), and small hand made sheets.
import synthetic from "../../../../fixtures/synthetic/regions.json";
import { parseRegions, type RegionsFile } from "../shared/regions";
import type { Pt } from "./homography";

export const SYNTHETIC: RegionsFile = parseRegions(synthetic);

export const square = (x: number, y: number, s: number): Pt[] => [
  [x, y],
  [x + s, y],
  [x + s, y + s],
  [x, y + s],
];

export function sheet(
  regions: { id: string; poly: Pt[]; label?: string; texture?: string; centroid?: Pt }[],
): RegionsFile {
  return parseRegions({
    schema_version: 1,
    figure_id: "test",
    title: "Test",
    figure_type: "labeled_diagram",
    page: { size: "letter", width_mm: 215.9, height_mm: 279.4 },
    summary: "A test sheet.",
    textures: [{ id: "dots", meaning: "a", earcon_hz: 523.25 }],
    regions: regions.map((r) => ({
      id: r.id,
      label: r.label ?? `part ${r.id}`,
      polygon_mm: r.poly,
      source: "teacher",
      verified_by_teacher: true,
      ...(r.texture ? { texture: r.texture } : {}),
      ...(r.centroid ? { centroid_mm: r.centroid } : {}),
    })),
  });
}
