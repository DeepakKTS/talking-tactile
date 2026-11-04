import { describe, expect, it } from "vitest";
import { SAMPLE_MS, WARM_MAX_MS, cameraResult, handsResult, measureHands, micResult, secureResult, summary, voiceResult, wakeResult, choiceResult, reportsResult, zoomFocusResult } from "./check";

const voice = (name: string, local: boolean, lang = "en-US") => ({ name, lang, localService: local, default: false }) as SpeechSynthesisVoice;

describe("device check", () => {
  it("says whether the camera faces the rear, and its size", () => {
    expect(cameraResult({ facingMode: "environment", width: 1280, height: 720 }, "Back Camera")).toEqual({
      name: "Camera", state: "ok", detail: "Rear camera, 1280 x 720, Back Camera.",
    });
    expect(cameraResult({ facingMode: "user", width: 640, height: 480 }, "").state).toBe("warn");
    expect(cameraResult(null, "", "NotAllowedError: denied")).toEqual({
      name: "Camera", state: "fail", detail: "The camera did not open: NotAllowedError: denied.",
    });
  });

  it("gives the hand tracker's frames a second, ms a frame, delegate and first result", () => {
    const gpu = { delegate: "GPU" as const, timeToFirstResultMs: 1240, fellBack: null };
    expect(handsResult(150, 5000, gpu, [12, 14])).toEqual({
      name: "Hand tracker", state: "ok",
      detail: "30.0 frames a second, delegate GPU, 13 ms a frame, first result 1.2 s after the first frame.",
    });
    const cpu = { delegate: "CPU" as const, timeToFirstResultMs: 900, fellBack: "no result from the GPU 8 s after its first frame" };
    const slow = handsResult(25, 5000, cpu, [90]);
    expect(slow.state).toBe("warn");
    expect(slow.detail).toContain("delegate CPU (GPU dropped: no result from the GPU 8 s after its first frame)");
    const never = handsResult(0, 0, gpu, [], false);
    expect(never.state).toBe("fail");
    expect(never.detail).toBe("No result within 30 s of warming up, on the GPU.");
    expect(never.detail).not.toContain("loading");
  });

  it("waits for the tracker to warm up before measuring, and counts nothing from before", async () => {
    const log: string[] = [];
    let frames = 0;
    let warmUp: (ok: boolean) => void = () => undefined;
    const tracker = {
      delegate: "CPU" as const, timeToFirstResultMs: 700, fellBack: "no result from the GPU 8 s after its first frame",
      whenWarm: (maxMs: number) => { log.push(`wait ${String(maxMs)}`); return new Promise<boolean>((r) => { warmUp = r; }); },
    };
    let clock = 0;
    const measuring = measureHands(
      tracker,
      { reset: () => { log.push("reset"); frames = 0; }, read: () => ({ frames, inferMs: [20] }) },
      (ms) => { log.push(`sample ${String(ms)}`); frames += 100; clock += ms; return Promise.resolve(); },
      () => clock,
    );
    frames = 37; // cold-start frames, before the first result: not counted
    await Promise.resolve();
    expect(log).toEqual([`wait ${String(WARM_MAX_MS)}`]);
    warmUp(true);
    const r = await measuring;
    expect(log).toEqual([`wait ${String(WARM_MAX_MS)}`, "reset", `sample ${String(SAMPLE_MS)}`]);
    expect(r.detail.startsWith("20.0 frames a second, delegate CPU")).toBe(true);
  });

  it("a tracker that never warms up is a failure with its delegate, not loading", async () => {
    const tracker = { delegate: "GPU" as const, timeToFirstResultMs: null, fellBack: null, whenWarm: () => Promise.resolve(false) };
    const r = await measureHands(tracker, { reset: () => undefined, read: () => ({ frames: 0, inferMs: [] }) }, () => Promise.resolve());
    expect(r).toEqual({ name: "Hand tracker", state: "fail", detail: "No result within 30 s of warming up, on the GPU." });
  });

  it("finds a voice that works offline, or says there is none", () => {
    expect(voiceResult([voice("Net", false), voice("Samantha", true)])).toEqual({
      name: "Local voice", state: "ok", detail: "Samantha (en-US), works offline.",
    });
    expect(voiceResult([voice("Net", false)]).state).toBe("fail");
    expect(voiceResult(null).state).toBe("fail");
  });

  it("reports the wake lock, the microphone, the secure page and a summary", () => {
    expect(wakeResult(true).state).toBe("ok");
    expect(wakeResult(false).detail).toContain("Auto-Lock");
    expect(wakeResult(true, "NotAllowedError: x").state).toBe("fail");
    expect(micResult().state).toBe("ok");
    expect(micResult("NotAllowedError: x").state).toBe("fail");
    expect(secureResult(false).detail).toContain("npm run dev:phone");
    expect(summary([secureResult(true), micResult()])).toBe("All 2 checks pass.");
    expect(summary([secureResult(true), micResult("x"), wakeResult(false)])).toBe("2 of 3 checks need a look: Microphone, Screen Wake Lock.");
  });
});

describe("the camera's lens, zoom and focus rows", () => {
  it("warns on a multi-lens camera and names how the camera was chosen", () => {
    const tri = choiceResult("facingMode environment (no Back Camera listed)", "Back Triple Camera", { width: 1280, height: 720, frameRate: 30 });
    expect(tri.state).toBe("warn");
    expect(tri.detail).toBe("Back Triple Camera, chosen by facingMode environment (no Back Camera listed); 1280 x 720 at 30 fps. A multi-lens camera can switch lenses close to the sheet.");
    expect(choiceResult("Back Camera, by deviceId", "Back Camera", { width: 1280, height: 720 }).state).toBe("ok");
  });

  it("says what the camera offers and what was fixed, or that nothing could be read", () => {
    const lock = { capabilities: { zoom: { min: 1, max: 10 }, focusMode: ["manual", "continuous"] }, plan: { zoom: 1, focusMode: "manual" }, applied: ["zoom 1", "focusMode manual"], failed: [] };
    const r = zoomFocusResult(lock, { zoom: 1, focusMode: "manual" } as MediaTrackSettings);
    expect(r).toEqual({ name: "Zoom and focus", state: "ok", detail: "zoom 1 to 10, now 1. focus modes manual, continuous, now manual. fixed: zoom 1, focusMode manual." });
    const none = zoomFocusResult({ capabilities: null, plan: {}, applied: [], failed: [] }, null);
    expect([none.state, none.detail]).toEqual(["warn", "getCapabilities() is not supported here: zoom and focus are left to the camera."]);
    expect(JSON.parse(reportsResult(lock, { width: 1 }).detail)).toEqual({ capabilities: lock.capabilities, settings: { width: 1 } });
  });
});
