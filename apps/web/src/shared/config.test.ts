import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import exploreYaml from "../../../../config/explore.yaml?raw";
import { ConfigError, EXPLORE, loadExploreConfig } from "./config";

function edit(path: string, value: unknown): unknown {
  const data = parse(exploreYaml) as Record<string, unknown>;
  const keys = path.split(".");
  let target = data;
  for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
  const last = keys[keys.length - 1] ?? "";
  if (value === DELETE) {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete target[last];
  } else {
    target[last] = value;
  }
  return data;
}
const DELETE = Symbol("delete");

describe("explore config", () => {
  it("loads config/explore.yaml at startup", () => {
    expect(EXPLORE.hysteresis.enter_hold_ms).toBe(120);
    expect(EXPLORE.dwell.speed_below_mm_s).toBe(15);
    expect(EXPLORE.fingertip.one_euro.beta).toBe(0.007);
    expect(EXPLORE.health.off_page_points_before_recal).toBe(15);
  });

  it("matches the YAML file exactly", () => {
    expect(loadExploreConfig(parse(exploreYaml))).toEqual(parse(exploreYaml));
  });

  it.each([
    ["hysteresis", DELETE],
    ["hysteresis.enter_hold_ms", DELETE],
    ["hysteresis.enter_hold_ms", -1],
    ["hysteresis.enter_hold_ms", 1.5],
    ["hysteresis.enter_shrink_mm", -0.5],
    ["hysteresis.exit_grow_mm", "2"],
    ["dwell.hold_ms", 0],
    ["dwell.speed_below_mm_s", null],
    ["earcons.max_per_second", 0],
    ["earcons.texture_hz.solid", DELETE],
    ["earcons.texture_hz.dots", -1],
    ["earcons.default_hz", DELETE],
    ["fingertip.filter", "kalman"],
    ["fingertip.one_euro.beta", -0.1],
    ["fingertip.one_euro.mincutoff_hz", 0],
    ["fingertip.one_euro.typo", 1],
    ["guidance.update_ms", 0],
    ["health.off_page_points_before_recal", 1.5],
    ["registration.mark_inset_mm", -1],
    ["extra_section", {}],
  ])("refuses %s = %s and names the field", (path, value) => {
    const field = path.split(".").pop() ?? path;
    expect(() => loadExploreConfig(edit(path, value))).toThrow(ConfigError);
    expect(() => loadExploreConfig(edit(path, value))).toThrow(new RegExp(field));
  });

  it("refuses a file that is not a mapping", () => {
    expect(() => loadExploreConfig([1, 2])).toThrow(ConfigError);
    expect(() => loadExploreConfig(null)).toThrow(ConfigError);
  });
});
