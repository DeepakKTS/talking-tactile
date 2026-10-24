// The local intent parser: the commonest requests need no network. "where is", "more",
// "repeat", "stop" and "what is here" are handled on the device; a part's name is matched
// to the sheet's labels and braille abbreviations with an edit distance score, and nothing
// below intents.min_label_similarity is guessed. Anything else is a question for /api/ask.
import type { IndexedRegion } from "./regionIndex";

export type Intent =
  | { kind: "none" }
  | { kind: "stop" }
  | { kind: "repeat" }
  | { kind: "more" }
  | { kind: "here" }
  | { kind: "where"; region: IndexedRegion; name: string }
  | { kind: "where_unknown"; name: string }
  | { kind: "ask"; text: string };

const FILLER = /^(?:(?:um|uh|er|hey|ok|okay|so|please|and)\s+)+|(?:\s+(?:please|now|again please))+$/g;

const WHOLE: readonly [RegExp, Intent["kind"]][] = [
  [/^(?:stop|stop talking|quiet|be quiet|hush|shh+|cancel|silence|enough)$/, "stop"],
  [/^(?:repeat|repeat that|again|say (?:that|it) again|what did you say|pardon|come again)$/, "repeat"],
  [/^(?:more|tell me more|more please|what else|go on|continue|describe (?:it|this|that)|more about (?:it|this|that))$/, "more"],
  [/^(?:what(?: i|')?s (?:this|here|that)|what is (?:this|here|that)|whats (?:this|here|that)|where am i|what am i (?:touching|on|pointing at)|what part is this|what is under my finger)$/, "here"],
];

const WHERE = /^(?:where(?: i|')?s|where is|wheres|where are|find|show me|take me to|go to|locate|guide me to|how do i get to|help me find)\s+(?:the\s+|a\s+|an\s+|my\s+)?(.+)$/;

export function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[^a-z0-9' ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseIntent(
  text: string,
  regions: readonly IndexedRegion[],
  minSimilarity: number,
): Intent {
  const said = normalize(text).replace(FILLER, "").trim();
  if (!said) return { kind: "none" };
  for (const [re, kind] of WHOLE) {
    if (re.test(said)) return { kind } as Intent;
  }
  const where = WHERE.exec(said);
  if (where?.[1]) {
    const name = where[1].trim();
    const region = matchLabel(name, regions, minSimilarity);
    return region ? { kind: "where", region, name } : { kind: "where_unknown", name };
  }
  return { kind: "ask", text: text.trim() };
}

/** The region whose label or abbreviation is closest to name, if close enough. */
export function matchLabel(
  name: string,
  regions: readonly IndexedRegion[],
  minSimilarity: number,
): IndexedRegion | null {
  let best: IndexedRegion | null = null;
  let score = minSimilarity;
  for (const r of regions) {
    const names = [r.label, r.region.abbrev].filter((n): n is string => !!n);
    const s = Math.max(...names.map((n) => similarity(name, n)));
    if (s > score || (s === score && best === null)) {
      best = r;
      score = s;
    }
  }
  return best;
}

/** 1 minus the edit distance over the longer length, on the spelling or on a rough
 * sound key, whichever is closer, so "rite lobe" matches "right lobe". */
export function similarity(a: string, b: string): number {
  return Math.max(score(normalize(a), normalize(b)), score(soundKey(a), soundKey(b)));
}

function score(x: string, y: string): number {
  const n = Math.max(x.length, y.length);
  return n === 0 ? 1 : 1 - levenshtein(x, y) / n;
}

// English spellings that sound alike, folded together word by word.
const SOUNDS: readonly [RegExp, string][] = [
  [/ght/g, "t"], [/^wr/, "r"], [/^kn/, "n"], [/ph/g, "f"], [/ck/g, "k"],
  [/c(?=[eiy])/g, "s"], [/[cq]/g, "k"], [/x/g, "ks"], [/z/g, "s"],
  [/(.)\1+/g, "$1"], [/(?<=...)e$/, ""],
];

function soundKey(text: string): string {
  return normalize(text)
    .replace(/'/g, "")
    .split(" ")
    .map((w) => SOUNDS.reduce((acc, [re, to]) => acc.replace(re, to), w))
    .join(" ");
}

function levenshtein(a: string, b: string): number {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      const sub = (prev[j - 1] ?? 0) + (a[i - 1] === b[j - 1] ? 0 : 1);
      cur.push(Math.min(sub, (prev[j] ?? 0) + 1, (cur[j - 1] ?? 0) + 1));
    }
    prev = cur;
  }
  return prev[b.length] ?? 0;
}
