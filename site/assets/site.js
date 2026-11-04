// Shared by every page: the mobile menu, the glass sheen that follows the pointer, and on the
// landing page the nav link of the section in view.
(() => {
  "use strict";

  // glass sheen follows the pointer
  const glassEls = [...document.querySelectorAll(".glass")];
  let sheenRAF = 0, lastE = null;
  window.addEventListener("pointermove", e => {
    lastE = e;
    if (sheenRAF) return;
    sheenRAF = requestAnimationFrame(() => {
      sheenRAF = 0;
      for (const el of glassEls) {
        const r = el.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight) continue;
        el.style.setProperty("--mx", (lastE.clientX - r.left) + "px");
        el.style.setProperty("--my", (lastE.clientY - r.top) + "px");
      }
    });
  }, { passive: true });

  // mobile menu
  const menuBtn = document.getElementById("menu-btn"), menu = document.getElementById("menu");
  if (menuBtn && menu) {
    const setMenu = open => {
      menu.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
      menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    };
    menuBtn.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
    menu.addEventListener("click", e => { if (e.target.closest("a")) setMenu(false); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && menu.classList.contains("open")) { setMenu(false); menuBtn.focus(); } });
    document.addEventListener("click", e => { if (!e.target.closest(".site-header")) setMenu(false); });
  }

  // current-section highlight in the nav, for links to a section of this page
  const links = [...document.querySelectorAll('.nav-links a[href^="#"]')];
  if (links.length && "IntersectionObserver" in window) {
    const byId = new Map(links.map(a => [a.getAttribute("href").slice(1), a]));
    const io = new IntersectionObserver(entries => {
      for (const en of entries) if (en.isIntersecting) {
        links.forEach(a => a.removeAttribute("aria-current"));
        byId.get(en.target.id)?.setAttribute("aria-current", "true");
      }
    }, { rootMargin: "-45% 0px -50% 0px" });
    for (const id of byId.keys()) { const s = document.getElementById(id); if (s) io.observe(s); }
  }
})();
