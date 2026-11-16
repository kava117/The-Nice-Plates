/* The sign-in page's piano (index.html): the opening of Ode to Joy on the stand, a cursor walking it
   the way Practice's does, the keys going down under it, and a rep dot filling each time round.
   Built from plain elements in CSS 3D (styles.css, "Welcome page"). Still for reduced motion. */
(function () {
  var keysBox = document.getElementById("piano-keys"), page = document.getElementById("piano-page");
  var piano = document.getElementById("piano"), stage = document.getElementById("hello-stage");
  if (!keysBox || !page) return;
  var SVG = "http://www.w3.org/2000/svg";
  var still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Two octaves and a top C. Black keys sit after C, D, F, G and A.
  var WHITE = ["C", "D", "E", "F", "G", "A", "B"], KEY_W = 32, keys = {};
  for (var o = 4; o <= 6; o++) {
    WHITE.forEach(function (n, i) {
      if (o === 6 && n !== "C") return;
      var x = ((o - 4) * 7 + i) * KEY_W;
      var key = document.createElement("div");
      key.className = "key";
      key.style.left = x + "px";
      keysBox.appendChild(key);
      keys[n + o] = key;
      if (o < 6 && "CDFGA".indexOf(n) >= 0) {
        var black = document.createElement("div");
        black.className = "key key-black";
        black.style.left = x + KEY_W - 10 + "px";
        keysBox.appendChild(black);
      }
    });
  }

  // Ode to Joy, bars 1–4: [note, beats]
  var TUNE = [["E4", 1], ["E4", 1], ["F4", 1], ["G4", 1], ["G4", 1], ["F4", 1], ["E4", 1], ["D4", 1],
              ["C4", 1], ["C4", 1], ["D4", 1], ["E4", 1], ["E4", 1.5], ["D4", 0.5], ["D4", 2]];
  var STEP = { C4: -2, D4: -1, E4: 0, F4: 1, G4: 2 };   // staff steps above the bottom line
  var BOTTOM = 158, GAP = 6, BAR_X = [84, 160, 236, 312], BAR_W = 76;
  var AT = [[14, 31, 48, 65], [14, 31, 48, 65], [14, 31, 48, 65], [12, 37, 58]];

  function el(name, attrs, parent) {
    var e = document.createElementNS(SVG, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (parent || page).appendChild(e);
    return e;
  }

  el("rect", { x: 0, y: 0, width: 400, height: 240, class: "sheet" });
  el("text", { x: 200, y: 42, class: "sheet-title", "text-anchor": "middle" }).textContent = "Ode to Joy";
  el("text", { x: 384, y: 66, class: "sheet-small", "text-anchor": "end" }).textContent = "L. van Beethoven";
  var cursor = el("rect", { x: 0, y: 102, width: 18, height: 66, rx: 3, class: "sheet-cursor" });
  for (var l = 0; l < 5; l++) el("line", { x1: 16, x2: 388, y1: BOTTOM - l * 12, y2: BOTTOM - l * 12, class: "sheet-line" });
  el("text", { x: 14, y: 150, class: "sheet-clef" }).textContent = "𝄞";
  el("text", { x: 64, y: 133, class: "sheet-time", "text-anchor": "middle" }).textContent = "4";
  el("text", { x: 64, y: 157, class: "sheet-time", "text-anchor": "middle" }).textContent = "4";
  BAR_X.slice(1).forEach(function (x) { el("line", { x1: x, x2: x, y1: BOTTOM - 48, y2: BOTTOM, class: "sheet-line" }); });
  el("line", { x1: 384, x2: 384, y1: BOTTOM - 48, y2: BOTTOM, class: "sheet-line" });
  el("rect", { x: 386, y: BOTTOM - 48, width: 3, height: 48, class: "sheet-ink" });

  var heads = [], xs = [], n = 0;
  AT.forEach(function (bar, b) {
    bar.forEach(function (dx) {
      var note = TUNE[n], x = BAR_X[b] + dx, y = BOTTOM - STEP[note[0]] * GAP, beats = note[1];
      var g = el("g", { class: "sheet-note" });
      if (note[0] === "C4") el("line", { x1: x - 10, x2: x + 10, y1: y, y2: y, class: "sheet-line" }, g);
      el("ellipse", { cx: x, cy: y, rx: 6.2, ry: 4.4, transform: "rotate(-20 " + x + " " + y + ")",
                      class: beats === 2 ? "sheet-head is-open" : "sheet-head" }, g);
      el("line", { x1: x + 5.6, x2: x + 5.6, y1: y - 1, y2: y - 36, class: "sheet-stem" }, g);
      if (beats === 0.5) el("path", { d: "M" + (x + 5.6) + " " + (y - 36) + "c2 7 10 9 7 19 2-8-3-11-7-13", class: "sheet-ink" }, g);
      if (beats === 1.5) el("circle", { cx: x + 11, cy: y - 3, r: 1.7, class: "sheet-ink" }, g);
      heads.push(g); xs.push(x); n++;
    });
  });
  var dots = [0, 1, 2].map(function (i) { return el("circle", { cx: 352 + i * 14, cy: 214, r: 4.5, class: "sheet-dot" }); });

  function show(i) {
    heads.forEach(function (h, j) { h.classList.toggle("is-now", j === i); });
    cursor.style.transform = "translateX(" + (xs[i] - 9) + "px)";
  }
  show(0);
  if (still) return;

  // Play it: each note lights on the page and its key goes down; each time round fills a dot.
  var BEAT = 540, i = 0, round = 0;
  function tick() {
    if (document.hidden) return setTimeout(tick, 400);
    var note = TUNE[i], key = keys[note[0]], ms = note[1] * BEAT;
    show(i);
    key.classList.add("is-down");
    setTimeout(function () { key.classList.remove("is-down"); }, ms * 0.82);
    i++;
    if (i < TUNE.length) return setTimeout(tick, ms);
    i = 0;
    setTimeout(function () {
      if (round === dots.length) { round = 0; dots.forEach(function (d) { d.classList.remove("is-clean"); }); }
      else dots[round++].classList.add("is-clean");
      setTimeout(tick, BEAT * 2);
    }, ms);
  }
  setTimeout(tick, 900);

  // It leans a little toward the pointer, eased so it never jumps.
  var want = { x: 0, y: 0 }, now = { x: 0, y: 0 };
  window.addEventListener("pointermove", function (e) {
    want.x = (e.clientY / innerHeight - 0.5) * -6;
    want.y = (e.clientX / innerWidth - 0.5) * 10;
  });
  (function lean() {
    now.x += (want.x - now.x) * 0.06;
    now.y += (want.y - now.y) * 0.06;
    piano.style.setProperty("--lean-x", now.x.toFixed(2) + "deg");
    piano.style.setProperty("--lean-y", now.y.toFixed(2) + "deg");
    requestAnimationFrame(lean);
  })();
  stage.classList.add("is-live");
})();
