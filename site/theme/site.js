/* Theme toggle, mobile menu, on-page contents highlighting and client-side search. No dependencies, works from file:// and GitHub Pages. */
(function () {
  var root = document.documentElement;
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  var saved = store("cg-theme");
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  var tbtn = document.getElementById("theme-btn");
  if (tbtn) tbtn.addEventListener("click", function () {
    var cur = root.getAttribute("data-theme");
    if (!cur) cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    var next = cur === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next); store("cg-theme", next);
  });
  var mbtn = document.getElementById("menu-btn");
  if (mbtn) mbtn.addEventListener("click", function () {
    var open = document.body.classList.toggle("nav-open"); mbtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  // keep the current page's section open and scrolled into view in the sidebar
  var cur = document.querySelector('.sidebar a[aria-current="page"]');
  if (cur) { var d = cur.closest("details"); if (d) d.open = true; var sb = document.querySelector(".sidebar"); if (sb) sb.scrollTop = Math.max(0, cur.offsetTop - sb.clientHeight / 2); }

  // contents highlighting
  var links = [].slice.call(document.querySelectorAll(".toc a"));
  if (links.length && "IntersectionObserver" in window) {
    var map = {}; links.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { links.forEach(function (a) { a.classList.remove("on"); }); var a = map[e.target.id]; if (a) a.classList.add("on"); } });
    }, { rootMargin: "-80px 0px -70% 0px" });
    Object.keys(map).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
  }

  // search
  var input = document.getElementById("q"), box = document.getElementById("results");
  if (!input || !box) return;
  var base = document.body.getAttribute("data-base") || "";
  var index = null, loading = false, sel = -1;
  function load(cb) {
    if (index) return cb();
    if (loading) return;
    loading = true;
    var s = document.createElement("script"); s.src = base + "search-index.js"; s.onload = function () { index = window.SEARCH_INDEX || []; cb(); }; document.head.appendChild(s);
  }
  function run() {
    var q = input.value.trim().toLowerCase();
    if (q.length < 2) { box.classList.remove("open"); while (box.firstChild) box.removeChild(box.firstChild); return; }
    var words = q.split(/\s+/);
    var hits = [];
    index.forEach(function (p) {
      var t = p.t.toLowerCase(), best = 0, bestH = null, body = p.x.toLowerCase();
      var s = 0;
      words.forEach(function (w) { if (t.indexOf(w) >= 0) s += 12; if (body.indexOf(w) >= 0) s += 1; });
      p.h.forEach(function (h) {
        var hs = 0, ht = h[0].toLowerCase();
        words.forEach(function (w) { if (ht.indexOf(w) >= 0) hs += 6; });
        if (hs > best) { best = hs; bestH = h; }
      });
      s += best;
      var all = words.every(function (w) { return t.indexOf(w) >= 0 || body.indexOf(w) >= 0 || p.h.some(function (h) { return h[0].toLowerCase().indexOf(w) >= 0; }); });
      if (all && s > 0) hits.push({ p: p, s: s, h: bestH });
    });
    hits.sort(function (a, b) { return b.s - a.s; });
    hits = hits.slice(0, 12);
    sel = -1;
    // Built with DOM nodes and textContent, never innerHTML: page titles and headings come from the documents, and must stay text.
    while (box.firstChild) box.removeChild(box.firstChild);
    function row(href, title, sub) {
      var a = document.createElement("a"), b = document.createElement("b"), sp = document.createElement("span");
      a.setAttribute("href", href); b.textContent = title; sp.textContent = sub;
      a.appendChild(b); a.appendChild(sp); box.appendChild(a);
    }
    if (hits.length) {
      hits.forEach(function (h) {
        var deep = h.h && h.s >= 6;
        row(base + h.p.u + (deep ? "#" + encodeURIComponent(h.h[1]) : ""), h.p.t + (deep ? " \u203a " + h.h[0] : ""), h.p.s);
      });
    } else {
      row("#", "No results", "Try fewer or different words.");
      box.lastChild.addEventListener("click", function (e) { e.preventDefault(); });
    }
    box.classList.add("open");
  }
  input.addEventListener("input", function () { load(run); });
  input.addEventListener("focus", function () { load(run); });
  input.addEventListener("keydown", function (e) {
    var items = [].slice.call(box.querySelectorAll("a"));
    if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); e.preventDefault(); }
    else if (e.key === "Enter" && items[Math.max(sel, 0)]) { items[Math.max(sel, 0)].click(); return; }
    else if (e.key === "Escape") { box.classList.remove("open"); input.blur(); return; }
    items.forEach(function (a, i) { a.setAttribute("aria-selected", i === sel ? "true" : "false"); });
  });
  document.addEventListener("click", function (e) { if (!e.target.closest(".search")) box.classList.remove("open"); });
  document.addEventListener("keydown", function (e) { if (e.key === "/" && document.activeElement !== input && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); input.focus(); } });
})();
