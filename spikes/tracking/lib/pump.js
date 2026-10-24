// Newest frame only (RULES 4.1): at most one frame in flight. A frame offered
// while the worker is busy is dropped, never queued.

export function createFramePump(send) {
  let inFlight = false;
  const stats = { offered: 0, sent: 0, dropped: 0, failed: 0 };

  return {
    stats,
    get busy() {
      return inFlight;
    },
    // makeFrame may be async (createImageBitmap). The slot is taken before it
    // runs, so a second offer during capture is dropped too.
    async offer(makeFrame) {
      stats.offered++;
      if (inFlight) {
        stats.dropped++;
        return false;
      }
      inFlight = true;
      try {
        send(await makeFrame());
        stats.sent++;
        return true;
      } catch (err) {
        inFlight = false;
        stats.failed++;
        throw err;
      }
    },
    // Call when the worker answers for the frame in flight.
    done() {
      inFlight = false;
    },
  };
}
