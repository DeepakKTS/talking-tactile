// The mosaic background of the landing page: the photo in hero.jpg drawn as raised dots that
// lift under the pointer. Paused under prefers-reduced-motion and by the pause button.
(() => {
  "use strict";

  /* ======================================================================
     Effect parameters ("Vignette Bloom"). Kept in full so the renderer
     can be retuned without touching code. This build implements the
     "mosaic" render mode used by this look.
     ====================================================================== */
  const PARAMS = {
    renderMode: "mosaic", bgMode: "solid", bgBlur: 12, bgOpacity: 90,
    cellSize: 16, coverage: 100, invert: false, styleBlend: "source-over",
    // Grid and look controls for this build. The reference grid spans about 117 dots;
    // gridCols sets how many dots span the photo here (higher = smaller dots).
    gridCols: 150, minCell: 6, maxCell: 14, dotFill: .96,
    focusX: .46, focusY: .32,        // keep the face in frame when the window crops the photo
    waveDepth: .22, waveScale: .78,  // wave strength and size
    bloomThreshold: .34, vignetteScale: .15,
    brightness: 12, contrast: 115, edgeEmphasis: 0, density: 0,
    toneCurve: [{x:0,y:0},{x:1,y:1}],
    tint: "#3ca6ff", tintOpacity: 0, overlayBlend: "multiply",
    saturation: 100, grayscale: 0,
    pfx: {
      vignette:{enabled:true,intensity:38}, scanLines:{enabled:false,intensity:40},
      chromatic:{enabled:false,intensity:15}, bloom:{enabled:true,intensity:25},
      filmGrain:{enabled:false,intensity:30}, glitch:{enabled:false,intensity:20},
      pixelate:{enabled:false,intensity:15}, halftone:{enabled:false,intensity:20},
      filmDust:{enabled:false,intensity:20}
    },
    animated: true, animStyle: "wave",
    animSpeed: {enabled:true,intensity:100}, animIntensity: {enabled:true,intensity:60},
    lights: {enabled:false,points:[]},
    mask: {enabled:false,invert:false,dataUrl:null}
  };

  const SRC = "assets/hero.jpg";

  /* ---------- helpers ---------- */
  const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
  const smooth = t => t * t * (3 - 2 * t);
  const hash = n => { const s = Math.sin(n * 12.9898) * 43758.5453; return s - Math.floor(s); };
  const hexToRgb = h => {
    h = (h || "").trim().replace("#", "");
    if (h.length === 3) h = h.split("").map(c => c + c).join("");
    const n = parseInt(h || "000000", 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const mk = (w, h) => { const c = document.createElement("canvas"); c.width = Math.max(1, w); c.height = Math.max(1, h); return c; };

  function toneLUT(points) {
    const pts = [...points].sort((a, b) => a.x - b.x);
    const lut = new Uint8ClampedArray(256);
    for (let i = 0; i < 256; i++) {
      const x = i / 255; let j = 0;
      while (j < pts.length - 2 && x > pts[j + 1].x) j++;
      const a = pts[j], b = pts[Math.min(j + 1, pts.length - 1)];
      const t = b.x === a.x ? 0 : clamp((x - a.x) / (b.x - a.x), 0, 1);
      lut[i] = Math.round((a.y + (b.y - a.y) * t) * 255);
    }
    return lut;
  }

  function blendChannel(mode, base, top) {
    const b = base / 255, t = top / 255;
    switch (mode) {
      case "multiply": return b * t * 255;
      case "screen": return (1 - (1 - b) * (1 - t)) * 255;
      case "overlay": return (b < .5 ? 2 * b * t : 1 - 2 * (1 - b) * (1 - t)) * 255;
      case "soft-light": return ((1 - 2 * t) * b * b + 2 * t * b) * 255;
      default: return top;
    }
  }

  /* ======================================================================
     Mosaic field renderer
     ====================================================================== */
  class MosaicField {
    constructor(canvas, img, p) {
      this.c = canvas; this.ctx = canvas.getContext("2d", { alpha: true });
      this.img = img; this.p = p;
      this.lut = toneLUT(p.toneCurve);
      this.t = 0; this.lastRender = 0; this.running = false; this.animating = true;
      this.ambientFps = 30; // ambient motion is slow; pointer response runs at full rate
      this.ptr = { x: -1e4, y: -1e4, tx: -1e4, ty: -1e4, active: false, lastMove: 0 };
      this.frameFn = ts => this.frame(ts);
      this.readTheme();
      this.resize();
    }

    readTheme() {
      const cs = getComputedStyle(document.documentElement);
      this.light = cs.getPropertyValue("--mode").trim() === "light";
      this.bg = hexToRgb(cs.getPropertyValue("--bg"));
      this.grout = hexToRgb(cs.getPropertyValue("--grout"));
      this.lift = parseFloat(cs.getPropertyValue("--tile-lift")) || 0;
    }

    /* Cell size is tied to the photo, not the screen: the photo always spans
       p.gridCols cells across, so the composition matches the reference at
       any window size. Cells snap to whole device pixels so dots stay crisp. */
    resize() {
      const p = this.p, iw = this.img.naturalWidth, ih = this.img.naturalHeight;
      this.vw = window.innerWidth; this.vh = window.innerHeight;
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      const coverW = iw * Math.max(this.vw / iw, this.vh / ih);
      const cssCell = clamp(coverW / p.gridCols, p.minCell, p.maxCell);
      this.cellPx = Math.max(4, Math.round(cssCell * this.dpr));
      this.cell = this.cellPx / this.dpr;
      this.cols = Math.ceil(this.vw / this.cell) + 1;
      this.rows = Math.ceil(this.vh / this.cell) + 1;
      this.cw = this.cols * this.cell; this.ch = this.rows * this.cell;
      this.ox = (this.cw - this.vw) / 2; this.oy = (this.ch - this.vh) / 2;
      const pw = this.cols * this.cellPx, ph = this.rows * this.cellPx;
      this.c.width = pw; this.c.height = ph;
      this.c.style.width = this.cw + "px"; this.c.style.height = this.ch + "px";
      this.c.style.transform = `translate(${-this.ox}px,${-this.oy}px)`;

      this.grid = mk(this.cols, this.rows); this.gctx = this.grid.getContext("2d");
      this.gdata = this.gctx.createImageData(this.cols, this.rows);
      this.bright = mk(this.cols, this.rows); this.bctx = this.bright.getContext("2d");
      this.bdata = this.bctx.createImageData(this.cols, this.rows);
      this.bloomA = mk(Math.ceil(this.cols / 2), Math.ceil(this.rows / 2));
      this.bloomB = mk(Math.ceil(this.cols / 7), Math.ceil(this.rows / 7));
      this.layer = mk(pw, ph); this.lctx = this.layer.getContext("2d");

      this.sample();
      this.buildMask();
      this.buildVignette();
      this.render(this.t);
    }

    /* step 2 + 4: average each cell, then apply color adjustments */
    sample() {
      const p = this.p, S = 4, sw = this.cols * S, sh = this.rows * S;
      const sc = mk(sw, sh), sx = sc.getContext("2d", { willReadFrequently: true });
      const iw = this.img.naturalWidth, ih = this.img.naturalHeight;
      const scale = Math.max(sw / iw, sh / ih);
      const dw = iw * scale, dh = ih * scale;
      sx.imageSmoothingEnabled = true; sx.imageSmoothingQuality = "high";
      sx.drawImage(this.img, (sw - dw) * p.focusX, (sh - dh) * p.focusY, dw, dh);
      const px = sx.getImageData(0, 0, sw, sh).data;

      const n = this.cols * this.rows;
      const base = new Float32Array(n * 3), lum = new Float32Array(n), vis = new Uint8Array(n);
      const tint = hexToRgb(p.tint), tA = p.tintOpacity / 100;
      const bAdd = (p.brightness / 100) * 128, con = p.contrast / 100;
      const sat = p.saturation / 100, gray = p.grayscale / 100;

      for (let cy = 0; cy < this.rows; cy++) for (let cx = 0; cx < this.cols; cx++) {
        let r = 0, g = 0, b = 0;
        for (let yy = 0; yy < S; yy++) for (let xx = 0; xx < S; xx++) {
          const k = ((cy * S + yy) * sw + (cx * S + xx)) * 4;
          r += px[k]; g += px[k + 1]; b += px[k + 2];
        }
        r /= S * S; g /= S * S; b /= S * S;
        r = (r + bAdd - 128) * con + 128; g = (g + bAdd - 128) * con + 128; b = (b + bAdd - 128) * con + 128;
        let L = .2126 * r + .7152 * g + .0722 * b;
        r = L + (r - L) * sat; g = L + (g - L) * sat; b = L + (b - L) * sat;
        L = .2126 * r + .7152 * g + .0722 * b;
        r += (L - r) * gray; g += (L - g) * gray; b += (L - b) * gray;
        r = this.lut[clamp(r | 0, 0, 255)]; g = this.lut[clamp(g | 0, 0, 255)]; b = this.lut[clamp(b | 0, 0, 255)];
        if (tA > 0) {
          r += (blendChannel(p.overlayBlend, r, tint[0]) - r) * tA;
          g += (blendChannel(p.overlayBlend, g, tint[1]) - g) * tA;
          b += (blendChannel(p.overlayBlend, b, tint[2]) - b) * tA;
        }
        if (p.invert) { r = 255 - r; g = 255 - g; b = 255 - b; }
        if (this.lift > 0) {
          r += (this.bg[0] - r) * this.lift; g += (this.bg[1] - g) * this.lift; b += (this.bg[2] - b) * this.lift;
        }
        const i = cy * this.cols + cx;
        base[i * 3] = clamp(r, 0, 255); base[i * 3 + 1] = clamp(g, 0, 255); base[i * 3 + 2] = clamp(b, 0, 255);
        lum[i] = (.2126 * base[i * 3] + .7152 * base[i * 3 + 1] + .0722 * base[i * 3 + 2]) / 255;
        vis[i] = hash(i + 1) * 100 < p.coverage ? 1 : 0;
      }

      if (p.edgeEmphasis > 0) {
        const e = p.edgeEmphasis / 100, C = this.cols;
        for (let y = 1; y < this.rows - 1; y++) for (let x = 1; x < C - 1; x++) {
          const i = y * C + x;
          const avg = (lum[i - 1] + lum[i + 1] + lum[i - C] + lum[i + C]) / 4;
          const k = 1 + e * Math.abs(lum[i] - avg) * 3;
          for (let ch = 0; ch < 3; ch++) base[i * 3 + ch] = clamp(base[i * 3 + ch] * k, 0, 255);
        }
      }
      this.base = base; this.lum = lum; this.vis = vis;
    }

    /* round tiles with thin grout, drawn once per resize */
    buildMask() {
      const m = mk(this.c.width, this.c.height), x = m.getContext("2d");
      const s = this.cellPx, r = (s * this.p.dotFill) / 2;
      x.fillStyle = "#000"; x.beginPath();
      for (let cy = 0; cy < this.rows; cy++) for (let cx = 0; cx < this.cols; cx++) {
        const px = cx * s + s / 2, py = cy * s + s / 2;
        x.moveTo(px + r, py); x.arc(px, py, r, 0, Math.PI * 2);
      }
      x.fill();
      this.mask = m;
    }

    buildVignette() {
      const w = this.c.width, h = this.c.height, v = mk(w, h), x = v.getContext("2d");
      const k = (this.p.pfx.vignette.intensity / 100) * this.p.vignetteScale;
      const cx = w / 2, cy = h * .45, R = Math.hypot(w, h) / 2;
      const g = x.createRadialGradient(cx, cy, R * .42, cx, cy, R * 1.02);
      const [r, gg, b] = this.bg;
      g.addColorStop(0, `rgba(${r},${gg},${b},0)`);
      g.addColorStop(.55, `rgba(${r},${gg},${b},${(k * .8).toFixed(3)})`);
      g.addColorStop(1, `rgba(${r},${gg},${b},${clamp(k * 2, 0, 1).toFixed(3)})`);
      x.fillStyle = g; x.fillRect(0, 0, w, h);
      this.vignette = v;
    }

    /* step 8: animation term for a cell, about -1..1 */
    wave(x, y, i, t) {
      const w = .6 + 1.4 * (this.p.animSpeed.intensity / 100);
      const f = this.p.waveScale; // spatial frequency per cell, scaled so the wave keeps its size in px
      switch (this.p.animStyle) {
        case "pulse": return Math.sin(t * w * 1.6);
        case "shimmer": return Math.sin(x * .9 + t * w * 2.2) * Math.sin(y * .7 - t * w * 1.3);
        case "ripple": return Math.sin(Math.hypot(x - this.cols / 2, y - this.rows / 2) * .35 * f - t * w * 1.6);
        case "flicker": return (hash(i + Math.floor(t * 8) * 7919) * 2 - 1) * .7;
        default:
          return .65 * Math.sin((x * .19 + y * .11) * f - t * w) + .35 * Math.sin((x * .06 - y * .17) * f - t * w * .63);
      }
    }

    render(t) {
      const p = this.p, ctx = this.ctx, W = this.c.width, H = this.c.height;
      const C = this.cols, R = this.rows, base = this.base, vis = this.vis, lum = this.lum;
      const d = this.gdata.data, bd = this.bdata.data;
      const amp = p.animated && p.animIntensity.enabled ? (p.animIntensity.intensity / 100) * p.waveDepth : 0;
      const pxC = (this.ptr.x + this.ox) / this.cell, pyC = (this.ptr.y + this.oy) / this.cell;
      const rad = clamp(Math.min(this.vw, this.vh) * .14, 80, 150) / this.cell;
      const bT0 = p.bloomThreshold, bT1 = Math.min(1, bT0 + .3);

      for (let y = 0; y < R; y++) for (let x = 0; x < C; x++) {
        const i = y * C + x, o = i * 4;
        if (!vis[i]) { d[o + 3] = 0; bd[o + 3] = 0; continue; }
        let m = 1 + amp * this.wave(x, y, i, t);
        const dist = Math.hypot(x + .5 - pxC, y + .5 - pyC);
        if (dist < rad) m += .8 * smooth(1 - dist / rad);
        const r = base[i * 3] * m, g = base[i * 3 + 1] * m, b = base[i * 3 + 2] * m;
        d[o] = r; d[o + 1] = g; d[o + 2] = b; d[o + 3] = 255;
        // bright pass for bloom: only highlights glow
        const k = smooth(clamp((lum[i] * m - bT0) / (bT1 - bT0), 0, 1));
        bd[o] = r * k; bd[o + 1] = g * k; bd[o + 2] = b * k; bd[o + 3] = 255;
      }
      this.gctx.putImageData(this.gdata, 0, 0);

      const l = this.lctx;
      l.globalCompositeOperation = "copy"; l.imageSmoothingEnabled = false;
      l.drawImage(this.grid, 0, 0, W, H);
      l.globalCompositeOperation = "destination-in";
      l.drawImage(this.mask, 0, 0);
      l.globalCompositeOperation = "source-over";

      // step 1: background
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, W, H);
      if (p.bgMode === "solid") {
        const [r, g, b] = this.grout;
        ctx.fillStyle = `rgba(${r},${g},${b},${p.bgOpacity / 100})`; ctx.fillRect(0, 0, W, H);
      } else if (p.bgMode === "photo" || p.bgMode === "blur") {
        ctx.globalAlpha = p.bgOpacity / 100; ctx.imageSmoothingEnabled = true;
        if (p.bgMode === "blur" && "filter" in ctx) ctx.filter = `blur(${p.bgBlur * this.dpr}px)`;
        ctx.drawImage(this.grid, 0, 0, W, H);
        ctx.filter = "none"; ctx.globalAlpha = 1;
      }

      // step 3: tiles
      ctx.globalCompositeOperation = p.styleBlend || "source-over";
      ctx.drawImage(this.layer, 0, 0);
      ctx.globalCompositeOperation = "source-over";
      if (this.ptr.x > -1e3) this.drawRaised(ctx, pxC, pyC, rad);

      // step 5: vignette, then bloom from the bright pass
      if (p.pfx.vignette.enabled) ctx.drawImage(this.vignette, 0, 0);
      if (p.pfx.bloom.enabled) {
        this.bctx.putImageData(this.bdata, 0, 0);
        const a = this.bloomA, b = this.bloomB, ax = a.getContext("2d"), bx = b.getContext("2d");
        ax.imageSmoothingEnabled = bx.imageSmoothingEnabled = true;
        ax.imageSmoothingQuality = bx.imageSmoothingQuality = "high";
        ax.clearRect(0, 0, a.width, a.height); ax.drawImage(this.bright, 0, 0, a.width, a.height);
        bx.clearRect(0, 0, b.width, b.height); bx.drawImage(a, 0, 0, b.width, b.height);
        const I = p.pfx.bloom.intensity / 100, lm = this.light ? .35 : 1;
        ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = clamp(I * 1.3 * lm, 0, 1); ctx.drawImage(a, 0, 0, W, H); // tight glow
        ctx.globalAlpha = clamp(I * 1.5 * lm, 0, 1); ctx.drawImage(b, 0, 0, W, H); // wide halo
        ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
      }
    }

    drawRaised(ctx, pxC, pyC, rad) {
      const s = this.cellPx, base = s * this.p.dotFill / 2, d = this.gdata.data;
      const x0 = Math.max(0, Math.floor(pxC - rad)), x1 = Math.min(this.cols - 1, Math.ceil(pxC + rad));
      const y0 = Math.max(0, Math.floor(pyC - rad)), y1 = Math.min(this.rows - 1, Math.ceil(pyC + rad));
      const sh = 1.6 * this.dpr, TAU = Math.PI * 2;
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
        const i = y * this.cols + x;
        if (!this.vis[i]) continue;
        const dist = Math.hypot(x + .5 - pxC, y + .5 - pyC);
        if (dist >= rad) continue;
        const f = smooth(1 - dist / rad);
        if (f < .05) continue;
        const r = base * (1 + .32 * f), cx = (x + .5) * s, cy = (y + .5) * s, o = i * 4;
        ctx.fillStyle = `rgba(0,0,0,${(this.light ? .2 : .5) * f})`;
        ctx.beginPath(); ctx.arc(cx + sh * .6 * f, cy + sh * f, r, 0, TAU); ctx.fill();
        ctx.fillStyle = `rgb(${d[o]},${d[o + 1]},${d[o + 2]})`;
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.fill();
        if (f > .3) {
          ctx.fillStyle = `rgba(255,248,228,${.4 * f})`;
          ctx.beginPath(); ctx.arc(cx - r * .32, cy - r * .36, r * .38, 0, TAU); ctx.fill();
        }
      }
    }

    updatePointer(now) {
      const P = this.ptr;
      if ((!P.active || now - P.lastMove > 2600) && this.animating) {
        const s = now / 1000; // idle drift: a slow fingertip tracing the frame
        P.tx = this.vw * (.5 + .3 * Math.sin(s * .23)); P.ty = this.vh * (.42 + .2 * Math.sin(s * .31 + 1.3));
      }
      if (P.x < -1e3) { P.x = P.tx; P.y = P.ty; }
      const k = 1 - Math.pow(.0009, Math.min(.05, (now - (this.lastPtr || now)) / 1000));
      this.lastPtr = now;
      P.x += (P.tx - P.x) * k; P.y += (P.ty - P.y) * k;
      return Math.abs(P.tx - P.x) + Math.abs(P.ty - P.y) > .3;
    }

    frame(ts) {
      const moving = this.updatePointer(ts);
      const gap = moving ? 0 : 1000 / this.ambientFps;
      if (this.lastRender && ts - this.lastRender < gap - 2) { requestAnimationFrame(this.frameFn); return; }
      const dt = this.lastRender ? Math.min(.1, (ts - this.lastRender) / 1000) : 0;
      this.lastRender = ts;
      if (this.animating) this.t += dt;
      this.render(this.t);
      if (this.animating || moving) requestAnimationFrame(this.frameFn);
      else { this.running = false; this.lastRender = 0; }
    }

    kick() {
      if (this.running) return;
      this.running = true; this.lastRender = 0; this.lastPtr = 0;
      requestAnimationFrame(this.frameFn);
    }

    setAnimating(on) { this.animating = on; if (on) this.kick(); }
  }

  /* ======================================================================
     Page wiring
     ====================================================================== */
  const canvas = document.getElementById("field");
  const reduceMQ = window.matchMedia("(prefers-reduced-motion: reduce)");
  const darkMQ = window.matchMedia("(prefers-color-scheme: dark)");
  const motionBtn = document.getElementById("motion");
  let field = null, userPaused = reduceMQ.matches; // reduced motion starts paused; the button can still override

  function setMotionUI(paused) {
    motionBtn.setAttribute("aria-pressed", String(paused));
    motionBtn.setAttribute("aria-label", paused ? "Play background animation" : "Pause background animation");
    document.getElementById("ico-pause").hidden = paused;
    document.getElementById("ico-play").hidden = !paused;
  }
  function applyMotion() {
    const paused = userPaused;
    setMotionUI(paused);
    if (field) field.setAnimating(!paused && PARAMS.animated && PARAMS.animSpeed.enabled);
  }
  motionBtn.addEventListener("click", () => { userPaused = !userPaused; applyMotion(); });
  reduceMQ.addEventListener?.("change", () => { userPaused = reduceMQ.matches; applyMotion(); });

  const img = new Image();
  img.decoding = "async";
  img.src = SRC;
  img.decode().catch(() => {}).then(() => {
    if (!img.naturalWidth) return; // background stays plain if the image fails
    field = new MosaicField(canvas, img, PARAMS);
    applyMotion();
    field.kick();
  });

  // resize, debounced to one frame
  let rz = 0;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(rz);
    rz = requestAnimationFrame(() => { if (field) { field.resize(); field.kick(); } });
  }, { passive: true });

  darkMQ.addEventListener?.("change", () => {
    if (!field) return;
    field.readTheme(); field.sample(); field.buildVignette(); field.render(field.t); field.kick();
  });

  // pointer = fingertip
  function onPoint(x, y) {
    if (!field) return;
    const P = field.ptr; P.tx = x; P.ty = y; P.active = true; P.lastMove = performance.now();
    field.kick();
  }
  window.addEventListener("pointermove", e => onPoint(e.clientX, e.clientY), { passive: true });
  window.addEventListener("pointerdown", e => onPoint(e.clientX, e.clientY), { passive: true });
  document.documentElement.addEventListener("pointerleave", () => { if (field) field.ptr.active = false; });

  // veil deepens as the page scrolls, keeping text over the mosaic readable
  const root = document.documentElement;
  let scRAF = 0;
  function onScroll() {
    if (scRAF) return;
    scRAF = requestAnimationFrame(() => {
      scRAF = 0;
      const k = clamp(window.scrollY / (window.innerHeight * .9), 0, 1);
      root.style.setProperty("--veil-a", (k * .5).toFixed(3));
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

})();
