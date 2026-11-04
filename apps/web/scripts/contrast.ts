// WCAG 2.2 contrast for every text and background pair the app draws, in both themes, read
// from src/styles/tokens.css. node scripts/contrast.ts prints the table in docs/DESIGN.md;
// contrast.test.ts fails if a pair drops below its AA minimum.
//
// Method: each color is sRGB. A translucent color is composited over what is under it
// (source over, in sRGB, as browsers paint), so the glass is its fill over the page
// background, and the glass under its sheen is the sheen's brightest point over that.
// color-mix(in srgb, X p%, transparent) is X at alpha p; color-mix(in srgb, X p%, Y) is the
// opaque mix. Relative luminance and the ratio are WCAG 2.2's (1.4.3, 1.4.11):
// L = 0.2126 R + 0.7152 G + 0.0722 B on linearized channels, ratio (L1 + 0.05) / (L2 + 0.05).
// Minimums: 4.5 for text, 3 for large text (24 px, or 18.66 px bold) and for the parts of
// controls and states that are not text (field edges, focus ring, step icons).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const TOKENS_PATH = fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url));

export type Rgba = [number, number, number, number];
export type Theme = "light" | "dark";

/** The custom properties of the light block and of the pinned dark block. */
export function readThemes(source: string = readFileSync(TOKENS_PATH, "utf8")): Record<Theme, Record<string, string>> {
  const css = source.replace(/\/\*[\s\S]*?\*\//g, ""); // comments may name a property
  const props = (block: string) => {
    const out: Record<string, string> = {};
    for (const m of block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) out[m[1] ?? ""] = (m[2] ?? "").trim();
    return out;
  };
  const blocks = [...css.matchAll(/:root\s*\{([^}]*)\}/g)].map((m) => props(m[1] ?? ""));
  const light = Object.assign({}, ...blocks) as Record<string, string>;
  const dark = props(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/.exec(css)?.[1] ?? "");
  return { light, dark: { ...light, ...dark } };
}

export function parseColor(v: string): Rgba {
  const hex = /^#([0-9a-f]{6})$/i.exec(v);
  if (hex) {
    const n = parseInt(hex[1] ?? "", 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  const rgba = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(v);
  if (rgba) return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3]), rgba[4] === undefined ? 1 : Number(rgba[4])];
  throw new Error(`not a color: ${v}`);
}

/** Source over: a translucent color painted on an opaque one. */
export function over(top: Rgba, under: Rgba): Rgba {
  const a = top[3];
  return [top[0] * a + under[0] * (1 - a), top[1] * a + under[1] * (1 - a), top[2] * a + under[2] * (1 - a), 1];
}

const alpha = (c: Rgba, a: number): Rgba => [c[0], c[1], c[2], c[3] * a];
const mix = (a: Rgba, p: number, b: Rgba): Rgba => [a[0] * p + b[0] * (1 - p), a[1] * p + b[1] * (1 - p), a[2] * p + b[2] * (1 - p), 1];

export function luminance([r, g, b]: Rgba): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function ratio(fg: Rgba, bg: Rgba): number {
  const solid = over(fg, bg);
  const [a, b] = [luminance(solid), luminance(bg)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export interface Pair {
  theme: Theme;
  fg: string;
  bg: string;
  use: string;
  min: number;
  ratio: number;
}

/** Every pair the app draws: what is written or drawn, on what, and its minimum. */
export function pairs(themes = readThemes()): Pair[] {
  const out: Pair[] = [];
  for (const theme of ["light", "dark"] as const) {
    const t = themes[theme];
    const c = (name: string) => parseColor(t[name] ?? "");
    const page = c("--bg");
    const glassTop = over(c("--glass-fill-2"), page);
    const glass = over(c("--glass-fill"), page);
    const sheen = over(c("--glass-sheen"), glassTop);
    const surface = c("--surface");
    const backgrounds: Record<string, Rgba> = {
      "page (--bg)": page,
      "glass, top (--glass-fill-2 over --bg)": glassTop,
      "glass (--glass-fill over --bg)": glass,
      "glass under its sheen (--glass-sheen over the glass top)": sheen,
      "surface (--surface: items, fields, buttons)": surface,
    };
    const add = (fg: string, color: Rgba, bg: string, under: Rgba, use: string, min: number) => {
      out.push({ theme, fg, bg, use, min, ratio: ratio(color, under) });
    };
    for (const [bg, under] of Object.entries(backgrounds)) {
      add("--text", c("--text"), bg, under, "body text", 4.5);
      add("--text-2", c("--text-2"), bg, under, "secondary text", 4.5);
      add("--accent", c("--accent"), bg, under, "links, badges, step text", 4.5);
      add("--danger", c("--danger"), bg, under, "error text", 4.5);
      add("--warn", c("--warn"), bg, under, "warning text, flags", 4.5);
      add("--ok", c("--ok"), bg, under, "Checked flag", 4.5);
      add("--focus", c("--focus"), bg, under, "focus ring", 3);
      add("--field-edge", c("--field-edge"), bg, under, "field and button edge, pending step", 3);
    }
    add("--info", c("--info"), "surface (--surface: items, fields, buttons)", surface, "For your information edge", 3);
    add("--accent-ink", c("--accent-ink"), "accent (--accent: primary buttons, pressed toggles, tile)", c("--accent"), "button text", 4.5);
    add("--accent", c("--accent"), "surface (--surface: items, fields, buttons)", surface, "done step icon, tone edge", 3);
    const dropzone = over(alpha(surface, 0.6), glass);
    add("--text", c("--text"), "drop area (--surface 60% over the glass)", dropzone, "drop area heading", 4.5);
    add("--text-2", c("--text-2"), "drop area (--surface 60% over the glass)", dropzone, "accepted types and limit", 4.5);
    const dropOver = mix(c("--accent"), 0.1, surface);
    add("--text", c("--text"), "drop area, file over it (--accent 10% in --surface)", dropOver, "drop area heading", 4.5);
    add("--text-2", c("--text-2"), "drop area, file over it (--accent 10% in --surface)", dropOver, "accepted types and limit", 4.5);
    for (const [bg, under] of [["glass", glass], ["glass under its sheen", sheen]] as const) {
      const notice = over(alpha(c("--danger"), 0.1), under);
      add("--text", c("--text"), `error notice (--danger 10% over the ${bg})`, notice, "error message", 4.5);
      add("--danger", c("--danger"), `error notice (--danger 10% over the ${bg})`, notice, "Not uploaded.", 4.5);
    }
    const confirm = mix(c("--warn"), 0.08, surface);
    add("--text", c("--text"), "confirm box (--warn 8% in --surface)", confirm, "question", 4.5);
    const pressedText = c("--accent-ink");
    add("--accent-ink", pressedText, "pressed toggle (--accent)", c("--accent"), "check mark and words", 4.5);
  }
  return out;
}

export function table(rows: Pair[] = pairs()): string {
  const lines = ["| Theme | Text or mark | On | Used for | Ratio | Needs | Result |", "|---|---|---|---|---|---|---|"];
  for (const p of rows) {
    lines.push(`| ${p.theme} | \`${p.fg}\` | ${p.bg} | ${p.use} | ${p.ratio.toFixed(2)} | ${p.min} | ${p.ratio >= p.min ? "pass" : "FAIL"} |`);
  }
  return lines.join("\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(table());
  for (const theme of ["light", "dark"] as const) {
    const text = pairs().filter((p) => p.theme === theme && p.min === 4.5);
    const worst = text.reduce((a, b) => (b.ratio < a.ratio ? b : a));
    console.log(`\nWorst text pair, ${theme}: ${worst.fg} on ${worst.bg}, ${worst.ratio.toFixed(2)}`);
  }
}
