import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import type { AudioPort } from "./audio";
import type { Pt } from "./homography";
import { Metrics } from "./metrics";
import { type AskRequest, ExploreSession, OFFLINE_ANSWER, keyAction } from "./session";
import { SYNTHETIC } from "./testkit";

class FakeAudio implements AudioPort {
  log: string[] = [];
  speaking = false;
  lastSaid = "";
  earcon(hz: number) {
    this.log.push(`earcon ${hz}`);
    return performance.now();
  }
  exitTick() {
    this.log.push("tick");
    return performance.now();
  }
  beep() {
    this.log.push("beep");
    return performance.now();
  }
  chime() {
    this.log.push("chime");
    return performance.now();
  }
  say(text: string) {
    this.log.push(`say ${text}`);
    this.lastSaid = text;
  }
  stop() {
    this.log.push("stop");
  }
  said() {
    return this.log.filter((l) => l.startsWith("say ")).map((l) => l.slice(4));
  }
}

const FRAME = 1000 / 30;
const centroid = (label: string): Pt => {
  const r = SYNTHETIC.regions.find((x) => x.label === label);
  if (!r?.centroid_mm) throw new Error(label);
  return [r.centroid_mm[0], r.centroid_mm[1]];
};

function setup(ask?: (r: AskRequest) => Promise<string>) {
  const audio = new FakeAudio();
  const metrics = new Metrics();
  const asked: AskRequest[] = [];
  const session = new ExploreSession(SYNTHETIC, EXPLORE, {
    audio,
    metrics,
    ask: async (r) => {
      asked.push(r);
      if (ask) return ask(r);
      throw new TypeError("Failed to fetch");
    },
  });
  // Frame times run ahead of the clock; receivedAt is the real clock, as the code under
  // test reads it, so code time is measured for real.
  let t = 1000;
  const hold = (p: Pt | null, ms: number) => {
    for (const end = t + ms; t < end; t += FRAME) session.finger({ p, t, receivedAt: performance.now() });
  };
  return { audio, metrics, session, asked, hold };
}

describe("explore session", () => {
  it("opens with the title, the summary and how to get help", () => {
    const { audio, session } = setup();
    session.intro();
    expect(audio.said()).toEqual([`${SYNTHETIC.title}. ${SYNTHETIC.summary} Press H for help.`]);
  });

  it("plays the part's earcon on entry and says its label on dwell", () => {
    const { audio, hold } = setup();
    hold(centroid("left lobe"), 1500);
    expect(audio.log).toEqual([`earcon ${EXPLORE.earcons.texture_hz.lines}`, "say Left lobe"]);
  });

  it("logs entry to earcon and frame to earcon times", () => {
    const { metrics, hold } = setup();
    hold(centroid("left lobe"), 500);
    expect(metrics.enterToEarconMs.count).toBe(1);
    expect(metrics.enterToEarconMs.p50).toBeGreaterThanOrEqual(EXPLORE.hysteresis.enter_hold_ms);
    expect(metrics.frameToEarconMs.count).toBe(1);
  });

  it("answers what is here, more and repeat on the device", async () => {
    const { audio, session, hold, asked } = setup();
    hold(centroid("left lobe"), 1500);
    await session.command("what is here");
    await session.command("tell me more");
    await session.command("repeat");
    const said = audio.said();
    expect(said[1]).toBe("Left lobe");
    expect(said[2]).toBe("Right lobe is to the right. Stem is below.");
    expect(said[3]).toBe(said[2]);
    expect(asked).toEqual([]);
  });

  it("says when the finger is on no part", async () => {
    const { audio, session, hold } = setup();
    hold([3, 3], 500);
    await session.command("what is this");
    expect(audio.said()).toEqual(["Not on a part."]);
  });

  it("guides to a part by name, beeps, then chimes and says the label on arrival", async () => {
    const { audio, session, hold } = setup();
    hold([100, 265], 300);
    await session.command("where is the inner core");
    hold([100, 265], 3000);
    expect(audio.said()[0]).toMatch(/^Inner core\. Up, \d+ centimeters\.$/);
    expect(audio.log.filter((l) => l === "beep").length).toBeGreaterThan(2);
    hold(centroid("inner core"), 600);
    const tail = audio.log.slice(-3);
    expect(tail).toContain("chime");
    expect(audio.said().at(-1)).toBe("Inner core");
  });

  it("does not beep over its own speech", async () => {
    const { audio, session, hold } = setup();
    hold([100, 265], 300);
    audio.speaking = true;
    await session.command("where is the stem");
    hold([100, 265], 1500);
    expect(audio.log.filter((l) => l === "beep")).toEqual([]);
  });

  it("says when no part has that name", async () => {
    const { audio, session } = setup();
    await session.command("where is the mitochondria");
    expect(audio.said()).toEqual(["There is no mitochondria on this sheet."]);
  });

  it("stop ends speech and guidance", async () => {
    const { audio, session, hold } = setup();
    hold([100, 265], 300);
    await session.command("where is the stem");
    session.stop();
    const before = audio.log.length;
    hold([100, 265], 2000);
    expect(audio.log.slice(before).filter((l) => l === "beep")).toEqual([]);
    expect(audio.log).toContain("stop");
  });

  it("sends other questions to /api/ask with the touch context", async () => {
    const { audio, session, hold, asked } = setup(() => Promise.resolve("It joins the two lobes."));
    hold(centroid("right lobe"), 1500);
    hold(centroid("left lobe"), 1500);
    await session.command("What does the stem connect to?");
    expect(asked).toEqual([{
      figure_id: SYNTHETIC.figure_id,
      question: "What does the stem connect to?",
      region_id: SYNTHETIC.regions.find((r) => r.label === "left lobe")?.id,
      recent_region_ids: ["r8"],
    }]);
    expect(audio.said().at(-1)).toBe("It joins the two lobes.");
  });

  it("keeps labels, earcons and guidance working when the network is off", async () => {
    const { audio, session, hold } = setup(); // every ask fails as offline
    await session.command("What does the stem do?");
    expect(audio.said()).toEqual([OFFLINE_ANSWER]);
    hold(centroid("stem"), 1500);
    expect(audio.log.slice(-2)).toEqual([`earcon ${EXPLORE.earcons.texture_hz.grid}`, "say Stem"]);
    await session.command("where is the pore");
    hold(centroid("stem"), 1000);
    expect(audio.log.filter((l) => l === "beep").length).toBeGreaterThan(0);
  });

  it("asks to set the corners again when points keep landing off the sheet", () => {
    const { audio, hold } = setup();
    hold([-40, 500], (EXPLORE.health.off_page_points_before_recal + 5) * FRAME);
    expect(audio.said()).toEqual(["Your finger is off the sheet. Press R to set the corners again."]);
    hold([-40, 500], 3000);
    expect(audio.said()).toHaveLength(1);
  });
});

describe("camera sight", () => {
  const dark = EXPLORE.health.dark_frame_below / 2;
  const light = 0.5;
  const feed = (session: ExploreSession, b: number, from: number, ms: number) => {
    for (let t = from; t < from + ms; t += FRAME) session.sight(b, t);
  };

  it("says the camera cannot see the sheet dark_warn_ms after it goes dark, once", () => {
    const { audio, session } = setup();
    expect(EXPLORE.health.dark_warn_ms).toBeLessThan(2000 - 2 * FRAME); // the a11y pass asks for 2 s
    feed(session, light, 0, 1000);
    feed(session, dark, 1000, EXPLORE.health.dark_warn_ms - FRAME);
    expect(audio.said()).toEqual([]);
    feed(session, dark, 1000 + EXPLORE.health.dark_warn_ms - FRAME, 3000);
    expect(audio.said()).toEqual(["The camera cannot see the sheet."]);
  });

  it("says when it can see again, and a short dip says nothing", () => {
    const { audio, session } = setup();
    feed(session, dark, 0, 2500);
    feed(session, light, 2500, 500);
    expect(audio.said()).toEqual(["The camera cannot see the sheet.", "The camera can see the sheet again."]);
    feed(session, dark, 3000, 1000);
    feed(session, light, 4000, 1000);
    expect(audio.said()).toHaveLength(2);
  });
});

describe("keys", () => {
  it.each([
    ["Escape", "stop"], ["r", "recalibrate"], ["R", "recalibrate"], ["h", "help"],
    ["m", "more"], [".", "repeat"], ["w", "here"], ["x", null],
  ] as const)("%s is %s", (key, action) => {
    expect(keyAction(key)).toBe(action);
  });
});
