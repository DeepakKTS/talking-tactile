// As apps/web/src/explore/wakeLock.ts: the Screen Wake Lock is asked for first in the tap
// (Safari grants it only there), not awaited, and again when the page is visible. Refused
// or unsupported, the page says once how to keep the screen on.

export const WAKE_REFUSED = "To keep the screen on, set Auto-Lock to Never in Settings.";

export class ScreenAwake {
  constructor(onRefused, deps = { wakeLock: navigator.wakeLock, doc: document }) {
    this.onRefused = onRefused;
    this.deps = deps;
    this.lock = null;
    this.wanted = false;
    this.told = false;
    deps.doc.addEventListener("visibilitychange", () => {
      if (this.wanted && deps.doc.visibilityState === "visible") this.request();
    });
  }

  request() {
    this.wanted = true;
    const api = this.deps.wakeLock;
    if (!api) return Promise.resolve(this.refused("Not supported here"));
    let pending;
    try {
      pending = api.request("screen");
    } catch (err) {
      return Promise.resolve(this.refused(String(err)));
    }
    return pending.then(
      (lock) => {
        this.lock = lock;
        return null;
      },
      (err) => this.refused(`${err?.name ?? "Error"}: ${err?.message ?? err}`),
    );
  }

  refused(why) {
    if (!this.told) {
      this.told = true;
      this.onRefused(WAKE_REFUSED);
    }
    return why;
  }
}
