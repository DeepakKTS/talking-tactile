// Keeps the screen on while exploring. Safari grants a Screen Wake Lock only within a tap,
// so request() is the first call in the Start and Check handlers, before any await; it is
// never awaited there, so nothing waits on it. The browser drops the lock when the page is
// hidden, so it is asked for again when the page is visible. Refused or unsupported, the
// page says once how to keep the screen on another way.

export const WAKE_REFUSED = "To keep the screen on, set Auto-Lock to Never in Settings.";

export interface LockLike {
  release(): Promise<void>;
}

export interface WakeDeps {
  wakeLock?: { request(type: "screen"): Promise<LockLike> };
  doc: Pick<Document, "visibilityState" | "addEventListener">;
}

// Safari before 16.4 has no navigator.wakeLock, though the DOM types always declare it.
const browserDeps = (): WakeDeps => ("wakeLock" in navigator ? { wakeLock: navigator.wakeLock, doc: document } : { doc: document });

export class ScreenAwake {
  private lock: LockLike | null = null;
  private wanted = false;
  private told = false;

  /** onRefused shows and speaks the sentence; it is called once at most. */
  constructor(
    private readonly onRefused: (text: string) => void,
    private readonly deps: WakeDeps = browserDeps(),
  ) {
    deps.doc.addEventListener("visibilitychange", () => {
      if (this.wanted && deps.doc.visibilityState === "visible") void this.request();
    });
  }

  get held(): boolean {
    return this.lock !== null;
  }

  /** Call first in the tap handler, before any await, and do not await it there. Settles
   * with null once held, or with the reason it was not. */
  request(): Promise<string | null> {
    this.wanted = true;
    const api = this.deps.wakeLock;
    if (!api) return Promise.resolve(this.refused("Not supported here"));
    let pending: Promise<LockLike>;
    try {
      pending = api.request("screen");
    } catch (err) {
      return Promise.resolve(this.refused(reason(err)));
    }
    return pending.then(
      (lock) => {
        this.lock = lock;
        return null;
      },
      (err: unknown) => this.refused(reason(err)),
    );
  }

  async release(): Promise<void> {
    this.wanted = false;
    const lock = this.lock;
    this.lock = null;
    await lock?.release();
  }

  private refused(why: string): string {
    if (!this.told) {
      this.told = true;
      this.onRefused(WAKE_REFUSED);
    }
    return why;
  }
}

const reason = (err: unknown) => (err instanceof Error ? `${err.name}: ${err.message}` : String(err));
