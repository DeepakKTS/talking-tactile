// The microphone tap for hold-to-talk (src/explore/voice.ts): posts each render quantum of
// input (128 samples, under 3 ms) to the page, so stopping loses at most one quantum of the
// post-roll. A file of the app's own, not a blob: URL: the Content-Security-Policy's
// script-src, which covers worklets, allows only 'self' (vite.config.ts).
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice());
    return true;
  }
}
registerProcessor("tt-tap", Tap);
