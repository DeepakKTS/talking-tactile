import { describe, expect, it } from "vitest";
import cases from "../../../../fixtures/regions/cases.json";
import golden from "../../../../fixtures/regions/golden.json";
import { RegionsError, parseRegions, type RegionsFile } from "./regions";

type Case = (typeof cases.cases)[number];

function applyCase(c: Case): unknown {
  const obj: unknown = structuredClone(golden);
  let target = obj as Record<string | number, unknown>;
  for (const key of c.path.slice(0, -1)) target = target[key] as Record<string | number, unknown>;
  const last = c.path[c.path.length - 1];
  if (last === undefined) throw new Error(`case ${c.name} has an empty path`);
  if (c.op === "delete") {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete target[last];
  } else {
    target[last] = "value" in c ? c.value : undefined;
  }
  return obj;
}

describe("parseRegions", () => {
  it("accepts the golden fixture and returns it unchanged", () => {
    expect(parseRegions(structuredClone(golden))).toEqual(golden);
  });

  it.each(cases.cases.map((c) => [c.name, c] as const))("shared case: %s", (_name, c) => {
    const obj = applyCase(c);
    if (c.valid) expect(() => parseRegions(obj)).not.toThrow();
    else expect(() => parseRegions(obj)).toThrow(RegionsError);
  });

  it("rejects a list at the top level and says where the problem is", () => {
    expect(() => parseRegions([golden])).toThrow(/must be object/);
    const bad: unknown = structuredClone(golden);
    (bad as { regions: { label: unknown }[] }).regions.forEach((r) => (r.label = 7));
    expect(() => parseRegions(bad)).toThrow(/\/regions\/0\/label must be string/);
  });

  it("types a hand-written file the same way the schema does", () => {
    const sample = {
      schema_version: 1,
      figure_id: "abc",
      title: "t",
      figure_type: "other",
      page: { size: "a4", width_mm: 210, height_mm: 297 },
      summary: "s",
      textures: [{ id: "solid", meaning: "m", earcon_hz: 330 }],
      regions: [
        {
          id: "a",
          label: "a",
          polygon_mm: [[0, 0], [1, 0], [0, 1]],
          parent: null,
          neighbors: [{ id: "a", direction: "inside" }],
          source: "teacher",
          verified_by_teacher: true,
        },
      ],
    } satisfies RegionsFile;
    expect(parseRegions(sample)).toEqual(sample);
  });
});
