/* The coach on the practice page: ask about your own practice, answered from your record (coach.py).
   A panel beside the score, so the bars it talks about stay in view. The conversation lives in
   sessionStorage per piece: it survives a reload, and a new tab starts fresh.

   addCoach(els, { pieceId, passage, title, score }) wires it; passage() gives the picked bars as
   {first, last} indexes, title() the piece's title, and score (passages.js) lights up and picks the
   bars an answer names. */
function addCoach(els, { pieceId, passage = () => null, title = () => "", score }) {
  const { panel, toggle, close, restart, sub, thread, empty, lead, asks, form, input, send } = els;
  const KEY = `coach:${pieceId || "demo"}`, OPEN = "coach-open";
  let turns = load(), busy = false, failed = "";

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || []; } catch { return []; }
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(turns.slice(-24))); } catch {}
  }

  const named = b => (b.first === b.last ? `bar ${b.first + 1}` : `bars ${b.first + 1}–${b.last + 1}`);
  const capital = text => text[0].toUpperCase() + text.slice(1);

  // ---- what's on the page ----
  function where() {   // under the coach's name: what it's looking at
    const name = title(), bars = passage();
    sub.textContent = name ? `${name} · ${bars ? named(bars) : "whole piece"}` : bars ? capital(named(bars)) : "";
    sub.hidden = !sub.textContent;
  }

  function greeting() {   // a teacher at the start of a lesson
    const name = title();
    return name && name.length <= 24 ? `How’s ${name} going?` : "How’s practice going?";
  }
  function questions() {   // asked word for word: what you press is what it reads
    const bars = passage();
    return [
      bars ? `How should I work on ${named(bars)}?` : "Which passage needs the most work?",
      "What should I practise next?",
      "Am I ready to go faster?",
    ];
  }

  function hint() {
    const bars = passage(), name = bars && named(bars);
    input.placeholder = !bars ? "The left hand keeps rushing…"
      : `${capital(name)} ${bars.first === bars.last ? "keeps" : "keep"} falling apart…`;
  }

  function paragraphs(text, linked) {   // a line each: an answer's first line is its next step (coach.py's SYSTEM)
    const box = document.createDocumentFragment();
    for (const part of text.split(/\n+/)) {
      if (!part.trim()) continue;
      const p = document.createElement("p");
      p.append(linked && score ? barLinks(part.trim()) : part.trim());
      box.append(p);
    }
    return box;
  }

  // "bars 17-20" in an answer: lights those bars on the score while pointed at, picks them on a click
  const BARS = /\bbars? \d+(?:\s?(?:-|–|to)\s?\d+)?/gi;
  function barLinks(text) {
    const box = document.createDocumentFragment();
    let at = 0;
    for (const found of text.matchAll(BARS)) {
      const words = found[0], link = Object.assign(document.createElement("button"), { type: "button", className: "coach-bars", textContent: words });
      const on = () => score.point(words), off = () => score.point(null);
      link.addEventListener("pointerenter", on);
      link.addEventListener("focus", on);
      link.addEventListener("pointerleave", off);
      link.addEventListener("blur", off);
      link.addEventListener("click", () => score.choose(words));
      box.append(text.slice(at, found.index), link);
      at = found.index + words.length;
    }
    box.append(text.slice(at));
    return box;
  }

  // Under an answer, its first line in one press: those bars picked and that tempo set, ready to play.
  function setUp(step) {
    const bars = (step.match(BARS) || [])[0], percent = +(step.match(/\b(\d{2,3}) ?%/) || [])[1];
    if (!bars || !score) return [];
    const tempo = percent >= 40 && percent <= 200 && percent % 10 === 0 ? percent : 0;   // what the slider can be set to
    const label = `Set up ${bars.toLowerCase().replace("-", "–")}${tempo ? ` at ${tempo}%` : ""}`;
    const button = Object.assign(document.createElement("button"), { type: "button", className: "coach-setup press", textContent: label });
    button.addEventListener("click", () => {
      if (!score.choose(bars)) return;
      if (tempo) score.setTempo(tempo);
      button.textContent = "Ready when you are";
      setTimeout(() => { button.textContent = label; }, 2500);
      if (matchMedia("(max-width: 900px)").matches) setOpen(false, { focus: false });   // the sheet covers the score
    });
    return [button];
  }

  function render() {
    empty.hidden = turns.length > 0 || busy;
    restart.hidden = turns.length === 0;
    if (!empty.hidden) {
      lead.textContent = greeting();
      asks.replaceChildren(...questions().map(question => {
        const b = Object.assign(document.createElement("button"), { type: "button", className: "coach-ask", textContent: question });
        b.addEventListener("click", () => ask(question));
        return b;
      }));
    }
    thread.querySelectorAll(".coach-turn, .coach-wait, .coach-error").forEach(el => el.remove());
    for (const turn of turns) {
      const el = document.createElement("div");
      el.className = `coach-turn coach-${turn.role === "user" ? "q" : "a"}`;
      el.append(paragraphs(turn.content, turn.role === "assistant"));
      if (turn.role === "assistant") el.append(...setUp(turn.content.split("\n")[0]));
      thread.append(el);
    }
    if (busy) {
      thread.append(Object.assign(document.createElement("div"), {
        className: "coach-wait", role: "status",
        innerHTML: '<span class="coach-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="visually-hidden">Reading your practice log</span>',
      }));
    }
    if (failed) thread.append(Object.assign(document.createElement("p"), { className: "coach-error", role: "alert", textContent: failed }));
    send.disabled = busy || !input.value.trim();
    hint();
    where();
    // waiting or failed: the bottom. An answer: its question at the top, so it reads from the start.
    const asked = !busy && !failed && [...thread.querySelectorAll(".coach-q")].pop();
    thread.scrollTop = !empty.hidden ? 0 : asked
      ? thread.scrollTop + asked.getBoundingClientRect().top - thread.getBoundingClientRect().top - 12
      : thread.scrollHeight;
  }

  // ---- asking ----
  async function ask(question) {
    question = question.trim();
    if (!question || busy) return;
    const history = turns.slice();
    const bars = passage();
    turns.push({ role: "user", content: question });
    busy = true; failed = "";
    input.value = ""; grow();
    render();
    try {
      const r = await fetch("/api/coach", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question, history,
          piece_id: pieceId || null,
          passage: bars && { start: bars.first + 1, end: bars.last + 1 },
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || "The coach can't answer right now. Try again in a minute.");
      turns.push({ role: "assistant", content: data.reply });
      save();
    } catch (err) {
      turns.pop();
      if (!input.value.trim()) { input.value = question; grow(); }   // back in the box, ready to send again
      failed = err instanceof TypeError ? "No connection. Check the network and send it again." : err.message;   // fetch throws TypeError offline
    } finally {
      busy = false;
      render();
      if (isOpen()) input.focus();
    }
  }

  function grow() {   // the box grows with the question, up to six lines
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 6 * 22 + 20)}px`;
  }

  form.addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
  input.addEventListener("input", () => { grow(); send.disabled = busy || !input.value.trim(); });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); }
  });
  restart.addEventListener("click", () => {
    turns = []; failed = ""; save();
    render();
    input.focus();
  });

  // ---- opening and closing ----
  const isOpen = () => !panel.hidden;
  function setOpen(open, { focus = true } = {}) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open);
    toggle.classList.toggle("is-on", open);
    document.body.classList.toggle("coach-open", open);
    try { sessionStorage.setItem(OPEN, open ? "1" : ""); } catch {}
    dispatchEvent(new Event("resize"));   // the score re-flows into the narrower column
    if (open) { render(); if (focus) input.focus(); }
    else if (focus) toggle.focus();
  }
  const flip = () => setOpen(!isOpen());

  toggle.addEventListener("click", flip);
  close.addEventListener("click", () => setOpen(false));
  panel.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); }
  });

  let wasOpen = false;
  try { wasOpen = !!sessionStorage.getItem(OPEN); } catch {}
  if (wasOpen) setOpen(true, { focus: false });

  hint();
  return { toggle: flip, get open() { return isOpen(); }, refresh: () => { hint(); where(); if (isOpen() && !turns.length) render(); } };
}
