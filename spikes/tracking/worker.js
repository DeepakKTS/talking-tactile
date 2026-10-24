// Hand tracking worker. Receives one ImageBitmap at a time, returns landmarks only.
// ?stub=<ms> in the page URL replaces the model with a fixed delay, for testing the frame loop.

let stubMs = 0;

self.onmessage = async (e) => {
  const msg = e.data;
  if (msg.type === "init") {
    stubMs = msg.stubMs || 0;
    self.postMessage({ type: "ready", backend: `stub ${stubMs} ms` });
    return;
  }
  if (msg.type === "frame") {
    const t0 = performance.now();
    if (stubMs) await new Promise((r) => setTimeout(r, stubMs));
    msg.bitmap.close();
    self.postMessage({ type: "result", id: msg.id, hands: [], inferMs: performance.now() - t0 });
  }
};
