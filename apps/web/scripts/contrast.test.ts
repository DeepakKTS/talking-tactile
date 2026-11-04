import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOKENS_PATH, pairs, parseColor, ratio, readThemes, table } from "./contrast";

describe("tokens.css contrast", () => {
  it("meets WCAG AA for every pair the app draws, in both themes", () => {
    const low = pairs().filter((p) => p.ratio < p.min).map((p) => `${p.theme}: ${p.fg} on ${p.bg} is ${p.ratio.toFixed(2)}, needs ${String(p.min)}`);
    expect(low).toEqual([]);
  });

  it("follows the system setting and data-theme with the same dark values", () => {
    const css = readFileSync(TOKENS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const block = (re: RegExp) => [...(re.exec(css)?.[1] ?? "").matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((m) => `${m[1] ?? ""}:${(m[2] ?? "").trim()}`);
    const system = block(/:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/);
    expect(system.length).toBeGreaterThan(20);
    expect(system).toEqual(block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/));
  });

  it("keeps the landing page's colors", () => {
    const { light, dark } = readThemes();
    expect([dark["--bg"], dark["--text"], dark["--accent"], dark["--accent-ink"], dark["--focus"]]).toEqual(["#000000", "#ece4cf", "#c9b27c", "#17140c", "#e8d7a6"]);
    expect([light["--bg"], light["--text"], light["--accent"], light["--focus"]]).toEqual(["#e7e1d1", "#1b1912", "#6b5627", "#2f5d8a"]);
  });

  it("computes WCAG ratios: black on white is 21, a translucent color is composited first", () => {
    expect(ratio(parseColor("#000000"), parseColor("#ffffff"))).toBeCloseTo(21, 5);
    expect(ratio(parseColor("rgba(0, 0, 0, 0)"), parseColor("#777777"))).toBeCloseTo(1, 5);
    expect(table()).toContain("| light | `--text` | page (--bg)");
  });

  it("names a solid --surface equal to the glass over the background, within rounding", () => {
    for (const theme of ["light", "dark"] as const) {
      const t = readThemes()[theme];
      const [r, g, b] = parseColor(t["--glass-fill"] ?? "");
      const a = parseColor(t["--glass-fill"] ?? "")[3];
      const bg = parseColor(t["--bg"] ?? "");
      const want = [r, g, b].map((v, i) => Math.round(v * a + (bg[i] ?? 0) * (1 - a)));
      const got = parseColor(t["--surface"] ?? "").slice(0, 3);
      got.forEach((v, i) => { expect(Math.abs(v - (want[i] ?? 0))).toBeLessThanOrEqual(1); });
    }
  });
});
