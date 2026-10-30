import { describe, expect, it } from "vitest";
import { cameraResult, handsResult, micResult, secureResult, summary, voiceResult, wakeResult } from "./check";

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

  it("gives the hand tracker's frames a second and its delegate", () => {
    expect(handsResult(150, 5000, "mediapipe GPU", [12, 14])).toEqual({
      name: "Hand tracker", state: "ok", detail: "30.0 frames a second, delegate GPU, 13 ms a frame.",
    });
    expect(handsResult(25, 5000, "mediapipe CPU", [90]).state).toBe("warn");
    expect(handsResult(0, 5000, "loading", []).state).toBe("fail");
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
