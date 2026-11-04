// The mouse and touch demo on a sheet page. It reads the sheet's regions.json, the same file
// Explore uses, and lays a transparent outline of every touchable part over tactile.svg.
// Both use page millimeters: the SVG's viewBox is the page size from regions.json, so one
// unit is one millimeter on the printed sheet.
//
// What it does, after Explore's region engine (apps/web/src/explore/touch.ts):
//   entering a part plays its texture tone, resting on it says its name;
//   crossing a line between two parts says the line, then the part;
//   resting inside the outline but on no part says the subject's name;
//   a click, a tap, or Enter on a focused part says its name at once.
// The numbers are config/explore.yaml's (scripts/test_site.py checks they match).
// The real product follows a fingertip on the printed sheet with the phone's camera.
(() => {
  "use strict";

  const CFG = {
    enter_shrink_mm: 1.0,
    exit_grow_mm: 2.0,
    enter_hold_ms: 120,
    exit_hold_ms: 120,
    speed_below_mm_s: 15,
    hold_ms: 600,
    speed_window_ms: 200,
    default_hz: 440.0,
    tone_ms: 80,
    gain: 0.3,
    exit_tick_hz: 1568.0,
    exit_tick_ms: 20,
    exit_tick_gain: 0.12,
  };
  const NS = "http://www.w3.org/2000/svg";

  const root = document.querySelector("[data-regions]");
  if (!root) return;
  const frame = root.querySelector(".sheet-frame");
  const inner = root.querySelector(".sheet-inner");
  const readout = document.getElementById("said");
  const speechBtn = document.getElementById("speech");
  const status = document.getElementById("sheet-status");

  const capital = s => s.charAt(0).toUpperCase() + s.slice(1);
  const named = r => (r.group ? `${r.label}, part of the ${r.group}` : r.label);

  /* ---------- geometry, in millimeters ---------- */
  function inside(poly, x, y) {
    let c = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
    return c;
  }
  function edgeDist(poly, x, y) {
    let best = Infinity;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [ax, ay] = poly[j], [bx, by] = poly[i];
      const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
      const t = L ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L)) : 0;
      best = Math.min(best, Math.hypot(x - (ax + t * dx), y - (ay + t * dy)));
    }
    return best;
  }
  // inside the outline shrunk by inset (grown when inset is negative)
  function contains(poly, x, y, inset) {
    const inn = inside(poly, x, y);
    if (inset >= 0) return inn && edgeDist(poly, x, y) >= inset;
    return inn || edgeDist(poly, x, y) <= -inset;
  }
  function area(poly) {
    let a = 0;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) a += (poly[j][0] + poly[i][0]) * (poly[j][1] - poly[i][1]);
    return Math.abs(a / 2);
  }

  /* ---------- sound ---------- */
  let speechOn = true, ctx = null;
  function activate() {
    if (!ctx && (window.AudioContext || window.webkitAudioContext)) {
      try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch { ctx = null; }
    }
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
  }
  function tone(hz, ms, gain) {
    if (!speechOn || !ctx || ctx.state !== "running") return;
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
    o.frequency.value = hz;
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + ms / 1000);
    o.connect(g).connect(ctx.destination);
    o.start(t); o.stop(t + ms / 1000 + 0.02);
  }
  function say(text) {
    readout.textContent = text;
    if (!speechOn || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    window.speechSynthesis.speak(u);
  }
  function stop() { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }

  if (speechBtn) {
    if (!("speechSynthesis" in window)) {
      speechBtn.disabled = true;
      speechBtn.textContent = "Speech is not available in this browser";
    }
    speechBtn.addEventListener("click", () => {
      speechOn = !speechOn;
      speechBtn.setAttribute("aria-pressed", String(speechOn));
      speechBtn.textContent = speechOn ? "Speech on" : "Speech off";
      if (!speechOn) stop(); else activate();
    });
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape") stop(); });

  /* ---------- the sheet ---------- */
  fetch(root.dataset.regions)
    .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
    .then(build)
    .catch(() => { if (status) status.textContent = "The parts could not be loaded, so the demo is off. The sheet and the part list below still show every part."; });

  function build(file) {
    const W = file.page.width_mm, H = file.page.height_mm;
    const pitch = new Map((file.textures || []).map(t => [t.id, Number(t.earcon_hz)]));
    const parts = file.regions.filter(r => r.touchable).map(r => ({
      id: r.id, label: r.label, group: r.group, poly: r.polygon_mm, area: area(r.polygon_mm),
      hz: (r.texture !== undefined ? pitch.get(r.texture) : undefined) ?? CFG.default_hz,
    })).sort((a, b) => a.area - b.area || (a.id < b.id ? -1 : 1));
    const byId = new Map(parts.map(p => [p.id, p]));
    const borders = new Map();
    for (const l of file.lines || []) if (l.separates) borders.set([...l.separates].sort().join("|"), l.label);
    const border = (a, b) => borders.get([a.id, b.id].sort().join("|")) ?? null;
    const subject = file.subject || null;

    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "sheet-overlay");
    svg.setAttribute("role", "group");
    svg.setAttribute("aria-label", `Touchable parts of the sheet, ${parts.length}. Tab to a part, Enter says its name.`);
    const shapes = new Map();
    // the largest first, so a smaller part is drawn over a larger one
    for (const p of [...parts].reverse()) {
      const el = document.createElementNS(NS, "polygon");
      el.setAttribute("points", p.poly.map(([x, y]) => `${x},${y}`).join(" "));
      el.setAttribute("class", "part");
      el.setAttribute("tabindex", "0");
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", capital(named(p)));
      el.dataset.part = p.id;
      el.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); speakPart(p); }
      });
      el.addEventListener("focus", () => highlight(p));
      el.addEventListener("blur", () => highlight(state.current));
      shapes.set(p.id, el);
      svg.appendChild(el);
    }
    inner.appendChild(svg);

    // Zoom to the figure: the subject's outline plus 25 mm, room for the braille labels
    // beside it, within the page. The whole page stays one press away.
    const zoomBtn = document.getElementById("zoom");
    if (subject && zoomBtn) {
      const xs = subject.polygon_mm.map(p => p[0]), ys = subject.polygon_mm.map(p => p[1]), pad = 25;
      const x0 = Math.max(0, Math.min(...xs) - pad), x1 = Math.min(W, Math.max(...xs) + pad);
      const y0 = Math.max(0, Math.min(...ys) - pad), y1 = Math.min(H, Math.max(...ys) + pad);
      const zoom = on => {
        frame.classList.toggle("zoomed", on);
        frame.style.aspectRatio = on ? `${x1 - x0} / ${y1 - y0}` : "";
        inner.style.width = on ? `${(W / (x1 - x0)) * 100}%` : "";
        inner.style.transform = on ? `translate(${(-x0 / W) * 100}%, ${(-y0 / H) * 100}%)` : "";
        zoomBtn.textContent = on ? "Show the whole page" : "Zoom to the figure";
      };
      zoomBtn.hidden = false;
      zoomBtn.addEventListener("click", () => zoom(!frame.classList.contains("zoomed")));
      zoom(true);
    }

    for (const b of document.querySelectorAll("[data-say]")) {
      const p = byId.get(b.dataset.say);
      if (!p) continue;
      b.disabled = false;
      b.addEventListener("click", () => { activate(); speakPart(p); });
      b.addEventListener("focus", () => highlight(p));
      b.addEventListener("blur", () => highlight(state.current));
    }
    if (status) status.textContent = `${parts.length} touchable parts loaded from regions.json.`;

    let lit = null;
    function highlight(p) {
      if (lit) lit.classList.remove("on");
      lit = p ? shapes.get(p.id) : null;
      if (lit) lit.classList.add("on");
    }
    function speakPart(p) { tone(p.hz, CFG.tone_ms, CFG.gain); say(capital(named(p))); }

    /* the touch machine, one pointer */
    const state = { current: null, labelled: false, pending: null, pendingAt: 0, leftAt: null, left: null,
      outSince: null, slowSince: null, subjectSince: null, subjectSaid: false, samples: [], last: null };

    function hit(x, y, inset) {
      for (const p of parts) if (contains(p.poly, x, y, inset)) return p; // smallest first
      return null;
    }
    // straight line speed over the last speed_window_ms; one sample per tick, so a still
    // pointer, which sends no events, still counts as resting
    function slow(t) {
      const s = state.samples;
      while (s.length > 1 && t - s[0].t > CFG.speed_window_ms) s.shift();
      if (s.length < 2) return true;
      const a = s[0], b = s[s.length - 1], dt = (b.t - a.t) / 1000;
      return dt <= 0 || Math.hypot(b.x - a.x, b.y - a.y) / dt < CFG.speed_below_mm_s;
    }
    function enter(p, t) {
      const from = state.current ?? (state.left && t - state.leftAt <= CFG.hold_ms ? state.left : null);
      if (state.current) tone(CFG.exit_tick_hz, CFG.exit_tick_ms, CFG.exit_tick_gain);
      state.current = p; state.labelled = false; state.outSince = null; state.subjectSaid = false;
      highlight(p);
      tone(p.hz, CFG.tone_ms, CFG.gain);
      const line = from ? border(from, p) : null;
      if (line) { say(`${capital(line)}, ${named(p)}`); state.labelled = true; }
    }
    function step(t) {
      if (!state.last) return;
      const { x, y } = state.last;
      state.samples.push({ x, y, t });
      const isSlow = slow(t);
      state.slowSince = isSlow ? (state.slowSince ?? t) : null;
      const cur = state.current;
      const keep = cur && contains(cur.poly, x, y, -CFG.exit_grow_mm);
      const cand = hit(x, y, CFG.enter_shrink_mm);
      const target = cand && cand !== cur && (!keep || cand.area < cur.area) ? cand : null;
      if (target) {
        if (state.pending !== target) { state.pending = target; state.pendingAt = t; }
        else if (t - state.pendingAt >= CFG.enter_hold_ms) { state.pending = null; enter(target, t); }
      } else {
        state.pending = null;
      }
      if (cur && !keep && state.current === cur) {
        state.outSince ??= t;
        if (t - state.outSince >= CFG.exit_hold_ms) {
          tone(CFG.exit_tick_hz, CFG.exit_tick_ms, CFG.exit_tick_gain);
          state.left = cur; state.leftAt = t; state.current = null; state.outSince = null;
          highlight(null);
        }
      } else if (cur && keep) {
        state.outSince = null;
      }
      if (state.current && !state.labelled && state.slowSince !== null && t - state.slowSince >= CFG.hold_ms) {
        state.labelled = true;
        say(capital(named(state.current)));
      }
      if (!state.current && subject) {
        const inSub = contains(subject.polygon_mm, x, y, state.subjectSaid ? -CFG.exit_grow_mm : CFG.enter_shrink_mm);
        if (!inSub) { state.subjectSaid = false; state.subjectSince = null; }
        else {
          state.subjectSince ??= t;
          const from = Math.max(state.slowSince ?? Infinity, state.subjectSince);
          if (!state.subjectSaid && state.slowSince !== null && t - from >= CFG.hold_ms) {
            state.subjectSaid = true;
            say(capital(subject.label));
          }
        }
      } else {
        state.subjectSince = null;
      }
    }

    function toMm(e) {
      const m = svg.getScreenCTM();
      if (!m) return null;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
      return { x: pt.x, y: pt.y };
    }
    let timer = 0;
    function track(e) {
      const p = toMm(e);
      if (!p) return;
      const t = performance.now();
      state.last = { x: p.x, y: p.y, t };
      if (!timer) timer = window.setInterval(() => step(performance.now()), 33);
    }
    function leave(e) {
      window.clearInterval(timer); timer = 0;
      if (state.current && e.pointerType === "mouse") tone(CFG.exit_tick_hz, CFG.exit_tick_ms, CFG.exit_tick_gain);
      Object.assign(state, { current: null, pending: null, last: null, samples: [], slowSince: null, subjectSince: null, subjectSaid: false, left: null });
      highlight(null);
    }
    let down = null;
    svg.addEventListener("pointermove", track);
    svg.addEventListener("pointerdown", e => { activate(); down = { t: performance.now(), x: e.clientX, y: e.clientY }; track(e); });
    svg.addEventListener("pointerup", e => {
      // a click or a short tap says the part under it at once
      if (!down || performance.now() - down.t > 400 || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 10) { down = null; return; }
      down = null;
      const p = toMm(e);
      if (!p) return;
      const r = hit(p.x, p.y, 0);
      if (r) {
        if (state.current !== r) { state.current = r; highlight(r); }
        state.labelled = true;
        speakPart(r);
      } else if (subject && contains(subject.polygon_mm, p.x, p.y, 0)) {
        state.subjectSaid = true;
        say(capital(subject.label));
      }
    });
    svg.addEventListener("pointerleave", leave);
    svg.addEventListener("pointercancel", leave);
  }
})();
