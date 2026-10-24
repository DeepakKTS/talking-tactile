import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import { matchLabel, parseIntent, similarity } from "./intents";
import { RegionIndex } from "./regionIndex";
import { SYNTHETIC } from "./testkit";

const INDEX = new RegionIndex(SYNTHETIC, EXPLORE);
const MIN = EXPLORE.intents.min_label_similarity;
const parse = (text: string) => parseIntent(text, INDEX.regions, MIN);

describe("local intent parser", () => {
  it.each([
    ["stop", "stop"], ["Stop.", "stop"], ["be quiet", "stop"], ["cancel", "stop"],
    ["repeat", "repeat"], ["say that again", "repeat"], ["Repeat that, please.", "repeat"],
    ["more", "more"], ["tell me more", "more"], ["Um, tell me more.", "more"], ["what else", "more"],
    ["what is here", "here"], ["What's this?", "here"], ["what am I touching", "here"],
    ["where am I", "here"],
  ])("%j is %s", (text, kind) => {
    expect(parse(text).kind).toBe(kind);
  });

  it.each([
    ["where is the left lobe", "left lobe"],
    ["Where's the stem?", "stem"],
    ["find the inner core", "inner core"],
    ["take me to the cross vessel", "cross vessel"],
    ["where is the left lob", "left lobe"], // cut off
    ["where is the rite lobe", "right lobe"], // misheard
    ["where are the right lobes", "right lobe"],
    ["where is the write lobe", "right lobe"],
    ["where is the outer chamber please", "outer chamber"],
    ["where is oc", "outer chamber"], // the braille abbreviation
  ])("%j finds %s", (text, label) => {
    const got = parse(text);
    expect(got.kind).toBe("where");
    if (got.kind === "where") expect(got.region.label).toBe(label);
  });

  it("says when no part has that name, without guessing", () => {
    expect(parse("where is the mitochondria")).toEqual({ kind: "where_unknown", name: "mitochondria" });
  });

  it("sends anything else to /api/ask unchanged", () => {
    expect(parse("What does the stem connect to?")).toEqual({
      kind: "ask",
      text: "What does the stem connect to?",
    });
    expect(parse("")).toEqual({ kind: "none" });
    expect(parse("   ")).toEqual({ kind: "none" });
  });

  it("does not take a question that only mentions a command word", () => {
    expect(parse("why does the pump stop").kind).toBe("ask");
    expect(parse("is there more than one lobe").kind).toBe("ask");
  });
});

describe("fuzzy label matching", () => {
  it("scores 1 for the same words and less for each edit", () => {
    expect(similarity("left lobe", "left lobe")).toBe(1);
    expect(similarity("Left  Lobe", "left lobe")).toBe(1);
    expect(similarity("left lob", "left lobe")).toBeGreaterThanOrEqual(8 / 9);
    expect(similarity("rite", "right")).toBe(1); // sounds alike
    expect(similarity("stem", "steam")).toBeLessThan(1);
    expect(similarity("stem", "pore")).toBeLessThan(MIN);
  });

  it("is symmetric and between 0 and 1", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 20 }), fc.string({ maxLength: 20 }), (a, b) => {
        const s = similarity(a, b);
        expect(s).toBe(similarity(b, a));
        expect(s).toBeGreaterThanOrEqual(0);
        expect(s).toBeLessThanOrEqual(1);
      }),
    );
  });

  it("picks the best label, and nothing below min_label_similarity", () => {
    expect(matchLabel("rite lobe", INDEX.regions, MIN)?.label).toBe("right lobe");
    expect(matchLabel("lobe", INDEX.regions, MIN)).toBeNull(); // two lobes, neither close enough
    expect(matchLabel("xyz", INDEX.regions, MIN)).toBeNull();
  });
});
