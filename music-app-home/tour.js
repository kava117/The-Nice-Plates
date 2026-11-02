/* A short look around the page, shared by every page. The ? in the top bar starts it; the first
   visit to Home and Practice offers it once. Each step dims the page, lights one thing and says
   what it's for in a sentence. Steps whose thing isn't on screen are skipped, so a renamed id
   only drops a step. */
(function () {
  var TOURS = {
    "/home": [
      { el: ".nav-list", title: "Getting around", text: "Library holds your pieces, Practice is where you play, and Progress shows your time." },
      { el: ".tiles .card", title: "Your pieces", text: "Your most recent pieces. Click one to practise it." },
      { el: ".upload-now", title: "Add your music", text: "Upload a PDF, a photo or a MusicXML file, and it becomes a score you can play along with." },
      { el: "[data-tour-help]", title: "Help is here", text: "Each page has its own quick tour. Press ? whenever you're stuck." },
    ],
    "/library": [
      { el: "#upload", title: "Add a piece", text: "Pick a PDF, a photo or a MusicXML file. A photo can take half a minute to read." },
      { el: ".library-grid .card", title: "Open a piece", text: "Click a piece to practise it." },
    ],
    "/practice": [
      { el: ".passage-row", title: "Pick a passage", text: "Drag across bars on the score, or type bars like 12-16. Play then loops just those bars." },
      { el: "#play", around: ".tool-group", title: "Hear it", text: "Play follows the cursor. Slide the tempo down to learn it slowly." },
      { el: "#rep", title: "Count each go", text: "Say if it went clean, or press Listen and it marks each go for you." },
      { el: "#timer", title: "Time your practice", text: "Start when you sit down. Stop and save adds the time to Progress." },
      { el: "#coach-toggle", title: "Ask the coach", text: "Stuck on some bars? The coach reads your practice and suggests what to try next." },
    ],
    "/progress": [
      { el: ".practice-panel", title: "This week", text: "Minutes practised each day, from the timer on Practice." },
      { el: ".donut-row", title: "Your pieces", text: "How many pieces you've practised, out of everything in your library." },
    ],
    "/settings": [
      { el: "#settings-account", title: "You and your level", text: "Your account, and the playing levels you picked. Update them any time." },
    ],
  };
  var OFFER = ["/home", "/practice"];   // the first pages people land on; others have just the ?

  var tour = TOURS[location.pathname];
  var help = document.querySelector("[data-tour-help]");
  if (!tour || !help) return;
  help.hidden = false;

  var reduced = matchMedia("(prefers-reduced-motion: reduce)");
  var narrow = matchMedia("(max-width: 600px)");
  var shade, hole, card, steps, at, before;

  function remember(key) { try { localStorage.setItem(key, "1"); } catch (e) {} }
  function seen(key) { try { return localStorage.getItem(key) === "1"; } catch (e) { return true; } }
  var KEY = "tour-seen:" + location.pathname;

  function find(step) {   // around: light the group the thing sits in, like Play with its tempo
    var el = document.querySelector(step.el);
    return el && step.around ? el.closest(step.around) || el : el;
  }

  function shown(step) {
    var el = find(step);
    if (!el || el.closest("[hidden]")) return null;
    var r = el.getBoundingClientRect();
    return r.width && r.height ? el : null;
  }

  function make(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  }

  function start() {
    if (shade) return;
    steps = tour.filter(shown);
    if (!steps.length) return;
    remember(KEY);
    dismissOffer();
    before = document.activeElement;

    shade = make("div", "tour");
    hole = make("div", "tour-hole");
    card = make("section", "tour-card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-labelledby", "tour-title");
    card.innerHTML =
      '<div class="tour-meta"><div class="tour-dots" aria-hidden="true"></div><span class="tour-count" id="tour-count"></span></div>' +
      '<h2 class="tour-title" id="tour-title"></h2>' +
      '<p class="tour-text"></p>' +
      '<div class="tour-actions">' +
      '<button type="button" class="link-button tour-skip">Skip</button>' +
      '<button type="button" class="btn btn-ghost press tour-back">Back</button>' +
      '<button type="button" class="btn btn-solid press tour-next">Next</button>' +
      "</div>";
    steps.forEach(function () { card.querySelector(".tour-dots").appendChild(make("span")); });
    shade.append(hole, card);
    document.body.appendChild(shade);

    card.querySelector(".tour-skip").onclick = stop;
    card.querySelector(".tour-back").onclick = function () { go(at - 1); };
    card.querySelector(".tour-next").onclick = function () { at === steps.length - 1 ? stop() : go(at + 1); };
    addEventListener("keydown", keys, true);
    addEventListener("resize", follow);
    document.addEventListener("scroll", follow, true);
    go(0, true);
  }

  function go(i, first) {
    if (i < 0 || i >= steps.length) return;
    at = i;
    var step = steps[i], el = find(step);
    card.querySelector(".tour-title").textContent = step.title;
    card.querySelector(".tour-text").textContent = step.text;
    card.querySelector("#tour-count").textContent = i + 1 + " of " + steps.length;
    card.querySelectorAll(".tour-dots span").forEach(function (dot, k) { dot.classList.toggle("is-on", k === i); });
    card.querySelector(".tour-back").hidden = i === 0;
    card.querySelector(".tour-next").textContent = i === steps.length - 1 ? "Done" : "Next";

    el.scrollIntoView({ block: "nearest", behavior: reduced.matches ? "auto" : "smooth" });
    shade.classList.toggle("is-first", !!first);
    card.classList.remove("is-in");
    void card.offsetWidth;   // restarts the card's entrance for each step
    card.classList.add("is-in");
    place(el);
    setTimeout(function () { if (shade && at === i) place(el); }, 350);   // after a smooth scroll lands
    card.querySelector(".tour-next").focus({ preventScroll: true });
  }

  // The lit box around the step's thing, kept inside the window, and the card beside it.
  function place(el) {
    var pad = 6, r = el.getBoundingClientRect();
    var main = el.closest("main"), edge = main ? main.getBoundingClientRect().top : 0;   // the part of the page that scrolls
    var top = Math.max(r.top - pad, edge + 4), left = Math.max(r.left - pad, 8);
    var bottom = Math.min(r.bottom + pad, innerHeight - 8), right = Math.min(r.right + pad, innerWidth - 8);
    Object.assign(hole.style, { top: top + "px", left: left + "px", width: Math.max(right - left, 0) + "px", height: Math.max(bottom - top, 0) + "px" });

    if (narrow.matches) { card.style.top = card.style.left = ""; return; }   // docked to the bottom by the CSS
    var gap = 14, w = card.offsetWidth, h = card.offsetHeight, y;
    if (bottom + gap + h <= innerHeight - 8) y = bottom + gap;
    else if (top - gap - h >= 8) y = top - gap - h;
    else y = innerHeight - h - 16;
    var x = Math.min(Math.max(left, 16), innerWidth - w - 16);
    card.style.top = y + "px";
    card.style.left = x + "px";
  }

  var frame;
  function follow() {   // scrolling or resizing: keep up at once, without the glide
    if (!shade || frame) return;
    frame = requestAnimationFrame(function () {
      frame = null;
      if (!shade) return;
      shade.classList.add("is-following");
      place(find(steps[at]));
      requestAnimationFrame(function () { if (shade) shade.classList.remove("is-following"); });
    });
  }

  function keys(e) {
    e.stopImmediatePropagation();   // the page's own shortcuts (Space plays, arrows move) wait
    if (e.key === "Escape") { e.preventDefault(); stop(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); at === steps.length - 1 ? stop() : go(at + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(at - 1); }
    else if (e.key === "Tab") {   // round the card's buttons only
      var all = Array.prototype.filter.call(card.querySelectorAll("button"), function (b) { return !b.hidden; });
      var k = all.indexOf(document.activeElement);
      e.preventDefault();
      all[(k + (e.shiftKey ? all.length - 1 : 1)) % all.length].focus();
    }
  }

  function stop() {
    if (!shade) return;
    removeEventListener("keydown", keys, true);
    removeEventListener("resize", follow);
    document.removeEventListener("scroll", follow, true);
    var gone = shade;
    shade = null;
    gone.classList.add("is-out");
    setTimeout(function () { gone.remove(); }, reduced.matches ? 0 : 200);
    if (before && before.focus) before.focus({ preventScroll: true });
  }

  // ---- the first visit: offered once, never forced ----
  var offer;
  function dismissOffer(hint) {
    if (!offer) return;
    offer.remove();
    offer = null;
    if (hint) {   // show where help lives from now on
      help.classList.remove("is-hinting");
      void help.offsetWidth;
      help.classList.add("is-hinting");
    }
  }

  if (OFFER.indexOf(location.pathname) >= 0 && !seen(KEY)) {
    setTimeout(function () {
      if (shade || !tour.some(shown)) return;
      remember(KEY);
      offer = make("section", "tour-offer");
      offer.setAttribute("aria-label", "A quick look around");
      offer.innerHTML =
        '<p class="tour-offer-title">New here?</p>' +
        '<p class="tour-offer-text">A quick look around this page takes under a minute.</p>' +
        '<div class="tour-actions">' +
        '<button type="button" class="link-button tour-later">Not now</button>' +
        '<button type="button" class="btn btn-solid press tour-go">Show me</button>' +
        "</div>";
      offer.querySelector(".tour-go").onclick = start;
      offer.querySelector(".tour-later").onclick = function () { dismissOffer(true); };
      document.body.appendChild(offer);
    }, location.pathname === "/practice" ? 1500 : 700);   // after the page, and the score, settle
  }

  help.addEventListener("click", start);
})();
