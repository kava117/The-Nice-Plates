/* The coach on the practice page: ask about your own practice, answered from your record (coach.py).
   A panel beside the score, so the bars it talks about stay in view. The conversation lives in
   sessionStorage per piece: it survives a reload, and a new tab starts fresh.

   addCoach(els, { pieceId, passage }) wires it; passage() gives the picked bars as {first, last} indexes. */
function addCoach(els, { pieceId, passage = () => null }) {
  const { panel, toggle, close, restart, thread, empty, asks, form, input, send } = els;
  const KEY = `coach:${pieceId || "demo"}`, OPEN = "coach-open";
  let turns = load(), busy = false, failed = null;

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || []; } catch { return []; }
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(turns.slice(-24))); } catch {}
  }

  const named = b => (b.first === b.last ? `bar ${b.first + 1}` : `bars ${b.first + 1}-${b.last + 1}`);

  // ---- what's on the page ----
  function suggestions() {
    const bars = passage();
    return [
      ["What should I practise now?", "What should I practise now?"],
      bars ? [`Help with ${named(bars)}`, `How should I work on ${named(bars)}?`]
           : ["Which passage needs work?", "Which passage needs the most work, and how should I start on it?"],
      ["Am I ready to go faster?", "Am I ready to go faster on what I've been practising?"],
    ];
  }

  function paragraphs(text) {
    const box = document.createDocumentFragment();
    for (const part of text.split(/\n{2,}/)) {
      const p = document.createElement("p");
      p.textContent = part.trim();
      if (p.textContent) box.append(p);
    }
    return box;
  }

  function render() {
    empty.hidden = turns.length > 0 || busy;
    restart.hidden = turns.length === 0;
    if (!empty.hidden) {
      asks.replaceChildren(...suggestions().map(([label, question]) => {
        const b = Object.assign(document.createElement("button"), { type: "button", className: "coach-ask press", textContent: label });
        b.addEventListener("click", () => ask(question));
        return b;
      }));
    }
    thread.querySelectorAll(".coach-turn, .coach-wait, .coach-error").forEach(el => el.remove());
    for (const turn of turns) {
      const el = document.createElement("div");
      el.className = `coach-turn coach-${turn.role === "user" ? "q" : "a"}`;
      el.append(paragraphs(turn.content));
      thread.append(el);
    }
    if (busy) {
      thread.append(Object.assign(document.createElement("div"), {
        className: "coach-wait", role: "status",
        innerHTML: '<span class="coach-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="visually-hidden">Reading your practice log</span>',
      }));
    }
    if (failed) {
      const el = Object.assign(document.createElement("p"), { className: "coach-error", role: "alert", textContent: failed.error + " " });
      const again = Object.assign(document.createElement("button"), { type: "button", className: "link-button", textContent: "Ask again" });
      again.addEventListener("click", () => { const q = failed.question; failed = null; ask(q); });
      el.append(again);
      thread.append(el);
    }
    send.disabled = busy || !input.value.trim();
    thread.scrollTop = empty.hidden ? thread.scrollHeight : 0;   // newest answer in view; before one, the lead line
  }

  // ---- asking ----
  async function ask(question) {
    question = question.trim();
    if (!question || busy) return;
    const history = turns.slice();
    const bars = passage();
    turns.push({ role: "user", content: question });
    busy = true; failed = null;
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
      turns.pop();   // the question goes back in the box, ready to send again
      failed = { question, error: err instanceof TypeError ? "No connection. Check the network and ask again." : err.message };   // fetch throws TypeError offline
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
    turns = []; failed = null; save();
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

  return { toggle: flip, get open() { return isOpen(); }, refresh: () => isOpen() && !turns.length && render() };
}
