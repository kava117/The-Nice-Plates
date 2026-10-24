/* Passages on the practice page: pick bars out of the score, loop them, and count clean reps.

   Picking happens on the score, where the musician already reads: drag across bars, type
   "12-16" in the Bars box, or press [ and ] at the cursor. A click on a bar moves the cursor
   there; a double click picks that one bar. Bars outside the passage fade instead of
   blurring, so the lead-in stays readable.

   Practising: after each time through, Yes (Y) or Not yet (N). Three clean in a row at one
   tempo offers the next tempo up; two misses in a row offer a slower one.

   Keeping: a picked passage is saved (Sections) on its first rep, or with Save, and shows as
   a chip with its last reps. "Next up" marks the one with the fewest recent clean reps.

   Bars are measure indexes from 0 here; the server counts them from 1 (index + 1). */

const STREAK = 3;   // clean reps in a row at one tempo before offering a faster one
const SLIPS = 2;    // misses in a row before offering a slower one

// els: the elements in practice.html's #controls; tempo: the player's tempo slider (percent).
// onRep runs after each saved rep; onPick when the passage changes or a click moves the cursor;
// playing() says if the player is going.
function addPassages(osmd, els, { pieceId, tempo, onRep = () => {}, onPick = () => {}, playing = () => false }) {
  const { score, chips, form, input, rep, title, yes, no, dots, note, actions } = els;
  let saved = [];        // the piece's passages from the server, in bar order
  let active = null;     // the picked passage: {first, last, id}; id is null until it's saved
  let preview = null;    // bars under a drag, or between [ and the cursor, not picked yet
  let marking = null;    // the bar [ was pressed on, until ] picks the passage
  let boxes = [];        // one box per bar, in px from the top left of #score
  let undoable = false;  // the last rep can be taken back
  let offers = [];       // [text, action] buttons offered after a rep: a tempo change, the next passage
  let busy = false;

  const layer = Object.assign(document.createElement("div"), { className: "score-bars" });
  layer.setAttribute("aria-hidden", "true");   // the Bars box and [ ] keys do the same job from the keyboard

  // ---- talking to the server ----
  async function api(url, method = "GET", body) {
    const r = await fetch(url, body ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : { method });
    if (!r.ok) throw new Error(`${method} ${url}: ${r.status}`);
    return r.status === 204 ? null : r.json();
  }
  const keep = record => {   // put a passage from the server into `saved`, in bar order
    saved = [...saved.filter(p => p.id !== record.id), record].sort((a, b) => a.start - b.start || a.end - b.end);
    return record;
  };
  const savedFor = bars => bars && saved.find(p => p.start === bars.first + 1 && p.end === bars.last + 1);
  const remember = () => pieceId && (active && active.id
    ? api("/api/practice/section", "POST", { section_id: active.id })
    : api("/api/practice/piece", "POST", { piece_id: pieceId })).catch(() => {});   // only a convenience for the next visit

  // ---- bar numbers and labels ----
  const bars = () => (osmd.GraphicSheet ? osmd.GraphicSheet.MeasureList.length : 0);
  const number = i => {   // the bar number printed on the score
    const m = osmd.GraphicSheet && (osmd.GraphicSheet.MeasureList[i] || []).find(Boolean);
    return m ? m.MeasureNumber : i + 1;
  };
  const span = p => (p.first === p.last ? `${number(p.first)}` : `${number(p.first)}-${number(p.last)}`);
  const label = p => (p.first === p.last ? "Bar " : "Bars ") + span(p);
  const range = (a, b) => ({ first: Math.min(a, b), last: Math.max(a, b) });
  const asBars = record => ({ first: record.start - 1, last: record.end - 1, id: record.id });
  const record = () => active && active.id && saved.find(p => p.id === active.id);
  const speedName = percent => {
    const bpm = osmd.Sheet && osmd.Sheet.DefaultStartTempoInBpm;
    return bpm ? `${Math.round(bpm * percent / 100)} bpm` : `${percent} %`;
  };

  // "12-16", "12 16", "12" or "12 to 16", in printed bar numbers, to measure indexes
  function parse(text) {
    const found = text.match(/\d+/g);
    if (!found || found.length > 2) return null;
    const [a, b = a] = found.map(Number), index = n => {
      for (let i = 0; i < bars(); i++) if (number(i) === n) return i;
      return n - 1 < bars() ? n - 1 : -1;
    };
    const i = index(a), j = index(b);
    return i < 0 || j < 0 ? null : range(i, j);
  }

  // ---- the cursor ----
  const cursor = () => osmd.cursor.Iterator;
  const inside = i => active && marking === null && i >= active.first && i <= active.last;   // while marking, the cursor roams free
  function goTo(index) {   // cursor to the first note of a bar, scrolling only once
    const follow = osmd.FollowCursor;
    osmd.FollowCursor = false;
    osmd.cursor.reset();
    const it = cursor();
    while (!it.EndReached && it.CurrentMeasureIndex < index) it.moveToNextVisibleVoiceEntry(false);
    osmd.FollowCursor = follow;
    osmd.cursor.update();
    moved();
  }
  function moved() {   // after any cursor move: between [ and ], the passage-to-be follows the cursor
    if (marking === null) return;
    preview = range(marking, cursor().CurrentMeasureIndex);
    paint();
  }
  function toStart() {
    if (active) goTo(active.first);
    else osmd.cursor.reset();
  }
  // Next and Prev stay inside the passage once the cursor is in it: Next at the end goes round.
  function next() {
    const at = cursor().CurrentMeasureIndex, probe = cursor().clone();
    probe.moveToNextVisibleVoiceEntry(false);
    if (inside(at) && (probe.EndReached || !inside(probe.CurrentMeasureIndex))) return toStart(), true;
    return false;
  }
  function previous() {
    const at = cursor().CurrentMeasureIndex, probe = cursor().clone();
    probe.moveToPreviousVisibleVoiceEntry(false);
    return inside(at) && !inside(probe.CurrentMeasureIndex);   // true: stay on the first note
  }
  function bar(step) {   // Shift + arrows: a whole bar at a time
    const it = cursor(), at = it.CurrentMeasureIndex;
    const onFirstNote = it.CurrentSourceTimestamp.RealValue === it.CurrentMeasure.AbsoluteTimestamp.RealValue;
    let to = step > 0 ? at + 1 : onFirstNote ? at - 1 : at;
    if (inside(at)) to = to > active.last ? active.first : Math.max(to, active.first);
    goTo(Math.max(0, Math.min(to, bars() - 1)));
  }

  // ---- picking ----
  function pick(chosen) {
    const match = savedFor(chosen);
    active = match ? asBars(match) : chosen && { ...chosen, id: null };
    undoable = false;
    offers = [];
    marking = preview = null;
    note.textContent = "";
    if (active) toStart();   // back to the whole piece leaves the cursor where it is
    remember();
    render();
    onPick();
  }
  function clear() {
    if (marking !== null) { marking = preview = null; return render(); }   // Esc between [ and ] only drops the mark
    if (active) pick(null);
  }
  // [ marks the first bar; moving the cursor stretches the passage; ] picks it.
  // ] on its own ends the picked passage (or a one-bar passage) at the cursor.
  function markStart() {
    marking = cursor().CurrentMeasureIndex;
    moved();
    render();
  }
  function markEnd() {
    const at = cursor().CurrentMeasureIndex;
    pick(marking !== null ? range(marking, at) : range(active ? Math.min(at, active.first) : at, at));
  }

  // ---- the score overlay: a box per bar to click and drag on, faded outside the passage ----
  function measure() {
    const sheet = osmd.GraphicSheet;
    if (!sheet) return [];
    const unit = 10 * osmd.zoom, origin = score.getBoundingClientRect(), svgs = score.querySelectorAll("svg");
    return sheet.MeasureList.map((staves, index) => {
      const m = staves.find(Boolean);
      if (!m || !m.ParentMusicSystem) return null;
      const system = m.ParentMusicSystem, frame = system.PositionAndShape;
      const page = Math.max(0, sheet.MusicPages.indexOf(system.Parent)), svg = (svgs[page] || svgs[0]).getBoundingClientRect();
      const top = frame.AbsolutePosition.y + frame.BorderTop, bottom = frame.AbsolutePosition.y + frame.BorderBottom;
      return {
        index, system: `${page}.${system.Id}`,
        left: svg.left - origin.left + m.PositionAndShape.AbsolutePosition.x * unit,
        top: svg.top - origin.top + top * unit,
        width: m.PositionAndShape.Size.width * unit,
        height: (bottom - top) * unit,
      };
    });
  }
  const place = (el, box) => Object.assign(el.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });

  function draw() {   // after every render (load, zoom, resize)
    boxes = measure();
    if (!layer.isConnected) score.append(layer);
    layer.replaceChildren(...boxes.filter(Boolean).map(box => {
      const el = Object.assign(document.createElement("div"), { className: "score-bar" });
      el.dataset.index = box.index;
      place(el, box);
      return el;
    }));
    paint();
  }

  function paint() {
    const shown = preview || active;
    layer.querySelectorAll(".passage-frame").forEach(el => el.remove());
    layer.classList.toggle("has-passage", !!shown);
    for (const el of layer.querySelectorAll(".score-bar")) {
      const i = +el.dataset.index;
      el.classList.toggle("in", !!shown && i >= shown.first && i <= shown.last);
    }
    if (!shown) return;
    const lines = new Map();   // one frame per line of music the passage touches
    for (const box of boxes) {
      if (!box || box.index < shown.first || box.index > shown.last) continue;
      const line = lines.get(box.system);
      if (!line) lines.set(box.system, { ...box });
      else line.width = box.left + box.width - line.left;
    }
    const frames = [...lines.values()], handles = active && marking === null && (!preview || resizing);
    frames.forEach((box, n) => {
      const frame = Object.assign(document.createElement("div"), { className: "passage-frame" + (preview && !resizing ? " is-preview" : "") });
      place(frame, box);
      const text = marking !== null ? `${label(shown)}: ] on the last bar` : label(shown);   // between [ and ], say how to finish
      if (n === 0) frame.append(Object.assign(document.createElement("span"), { className: "passage-tab", textContent: text }));
      // Two handles, like a range slider's thumbs, but on the score: drag either one to move that end of the passage.
      if (handles && n === 0) frame.append(handle("start"));
      if (handles && n === frames.length - 1) frame.append(handle("end"));
      layer.append(frame);
    });
  }

  function handle(end) {
    const el = Object.assign(document.createElement("div"), { className: `passage-handle is-${end}`, title: `Drag to move the passage's ${end === "start" ? "first" : "last"} bar` });
    el.dataset.end = end;
    return el;
  }

  function barAt(x, y) {   // the bar under a point, or the nearest one: same line first, then sideways
    const o = score.getBoundingClientRect();
    x -= o.left; y -= o.top;
    let best = null, distance = Infinity;
    for (const box of boxes) {
      if (!box) continue;
      const dx = Math.max(box.left - x, 0, x - box.left - box.width), dy = Math.max(box.top - y, 0, y - box.top - box.height);
      if (dy * 1e4 + dx < distance) [best, distance] = [box.index, dy * 1e4 + dx];
    }
    return best;
  }

  let press = null;      // a pointer held down on a bar
  let resizing = null;   // a pointer dragging one of the passage's handles: {id, end}
  layer.addEventListener("pointerdown", e => {
    const grip = e.target.closest(".passage-handle");
    if (grip && e.button === 0) {
      resizing = { id: e.pointerId, end: grip.dataset.end };
      layer.setPointerCapture(e.pointerId);   // on the layer: repainting replaces the handle under the pointer
      return;
    }
    const el = e.target.closest(".score-bar");
    if (!el || e.button !== 0) return;
    press = { id: e.pointerId, x: e.clientX, y: e.clientY, from: +el.dataset.index, to: +el.dataset.index, dragging: false };
    el.setPointerCapture(e.pointerId);
  });
  layer.addEventListener("pointermove", e => {
    if (resizing && e.pointerId === resizing.id) {
      const at = barAt(e.clientX, e.clientY) ?? (resizing.end === "start" ? active.first : active.last);
      preview = resizing.end === "start" ? range(Math.min(at, active.last), active.last) : range(active.first, Math.max(at, active.first));
      return paint();
    }
    if (!press || e.pointerId !== press.id) return;
    if (!press.dragging && Math.hypot(e.clientX - press.x, e.clientY - press.y) < 6) return;   // still a click
    press.dragging = true;
    press.to = barAt(e.clientX, e.clientY) ?? press.to;
    preview = range(press.from, press.to);
    paint();
  });
  layer.addEventListener("pointerup", e => {
    if (resizing && e.pointerId === resizing.id) {
      const moved = preview && (preview.first !== active.first || preview.last !== active.last) && preview;
      resizing = preview = null;
      return moved ? pick(moved) : paint();
    }
    if (!press || e.pointerId !== press.id) return;
    const done = press;
    press = preview = null;
    if (done.dragging) pick(range(done.from, done.to));
    else if (e.shiftKey && active) pick(done.from < active.first ? range(done.from, active.last) : range(active.first, done.from));
    else { onPick(); goTo(done.from); }   // a click moves the cursor, and stops the player first
  });
  layer.addEventListener("pointercancel", () => { press = resizing = preview = null; paint(); });
  layer.addEventListener("dblclick", e => {
    const el = e.target.closest(".score-bar");
    if (el) pick(range(+el.dataset.index, +el.dataset.index));
  });

  // ---- reps ----
  function streak(p) {   // clean in a row at today's tempo, counting back from the newest
    let n = 0;
    for (const r of [...p.recent].reverse()) { if (!r.clean || r.tempo !== +tempo.value) break; n++; }
    return n;
  }
  function slips(p) {
    let n = 0;
    for (const r of [...p.recent].reverse()) { if (r.clean) break; n++; }
    return n;
  }
  function nextUp() {   // the saved passage with the fewest clean reps lately; never practiced beats long ago
    if (saved.length < 2) return null;
    const rank = p => [p.recent.slice(-5).filter(r => r.clean).length, p.last_practiced || ""];
    return saved.reduce((a, b) => {
      const [x, y] = [rank(a), rank(b)];
      return x[0] < y[0] || (x[0] === y[0] && x[1] <= y[1]) ? a : b;
    });
  }
  function setTempo(percent) {
    note.textContent = `Now at ${speedName(percent)}.`;
    tempo.value = percent;
    tempo.dispatchEvent(new Event("input"));    // the label
    tempo.dispatchEvent(new Event("change"));   // the player, if it's playing
  }

  async function save() {
    if (!active || active.id) return record();
    const made = keep(await api(`/api/pieces/${pieceId}/sections`, "POST", { start: active.first + 1, end: active.last + 1 }));
    active.id = made.id;
    await remember();   // finish before the timer starts: two requests at once would each write the session cookie, and one would lose
    return made;
  }

  async function addRep(clean) {
    if (!active || busy) return;
    if (!pieceId) { note.textContent = "Open a piece from your library to count reps."; return; }
    busy = true;
    try {
      await save();
      keep(await api(`/api/sections/${active.id}/reps`, "POST", { clean, tempo: +tempo.value }));
      undoable = true;
      onRep();
      feedback(clean);
      if (!playing()) toStart();   // ready for the next time through
    } catch (err) {
      console.error(err);
      note.textContent = "That rep didn't save. Check the connection and press again.";
    } finally {
      busy = false;
      render();
    }
  }

  function feedback(clean) {
    const p = record(), n = streak(p), t = +tempo.value;
    offers = [];
    if (clean && n >= STREAK && t < 100) {
      note.textContent = `${n} clean in a row at ${speedName(t)}.`;
      offers.push([`Try ${speedName(t + 10)}`, () => setTempo(t + 10)]);
    } else if (clean && n >= STREAK) {
      const up = nextUp();
      note.textContent = `${n} clean in a row at full speed.`;
      if (up && up.id !== p.id) offers.push([`Next up: ${label(asBars(up))}`, () => pick(asBars(up))]);
    } else if (clean) {
      note.textContent = `Clean: ${n} of ${STREAK} in a row.`;
    } else if (slips(p) >= SLIPS && t > +tempo.min) {
      note.textContent = `${slips(p)} misses in a row.`;
      offers.push([`Slow to ${speedName(t - 10)}`, () => setTempo(t - 10)]);
    } else {
      note.textContent = "Not yet.";
    }
  }

  function showActions() {
    const buttons = offers.map(([text, act]) => button(text, "btn btn-ghost press rep-offer", () => { offers = []; note.textContent = ""; act(); showActions(); }));
    if (undoable) buttons.push(button("Undo", "link-button", undo));
    if (active && !active.id && pieceId) buttons.push(button("Save", "link-button", () => save().then(render).catch(console.error)));
    if (active && active.id) buttons.push(button("Remove", "link-button", confirmRemove));
    actions.replaceChildren(...buttons);
  }
  const button = (text, className, onClick) => {
    const b = Object.assign(document.createElement("button"), { type: "button", className, textContent: text });
    b.addEventListener("click", onClick);
    return b;
  };

  async function undo() {
    if (!active || !active.id || busy) return;
    keep(await api(`/api/sections/${active.id}/reps/last`, "DELETE"));
    undoable = false;
    offers = [];
    note.textContent = "Took back the last rep.";
    render();
  }

  function confirmRemove() {
    const p = record();
    note.textContent = `Remove ${label(active)}${p.reps ? ` and its ${p.reps} rep${p.reps === 1 ? "" : "s"}` : ""}?`;
    actions.replaceChildren(
      button("Remove", "btn btn-ghost press rep-offer", async () => {
        await api(`/api/sections/${p.id}`, "DELETE");
        saved = saved.filter(s => s.id !== p.id);
        pick(null);
      }),
      button("Keep", "link-button", () => { note.textContent = ""; showActions(); }),
    );
  }

  // ---- the passage row and the rep row ----
  function dotsFor(p, count) {
    const box = Object.assign(document.createElement("span"), { className: "dots" });
    for (const r of p ? p.recent.slice(-count) : []) {
      const dot = Object.assign(document.createElement("span"), { className: r.clean ? "dot is-clean" : "dot" });
      dot.title = `${r.clean ? "Clean" : "Not yet"}${r.tempo ? ` at ${speedName(r.tempo)}` : ""}`;
      box.append(dot);
    }
    return box;
  }

  function chip(text, pressed, onClick, extra = "") {
    const b = button("", `chip press${extra}`, onClick);
    b.setAttribute("aria-pressed", pressed);
    b.append(Object.assign(document.createElement("span"), { className: "chip-label", textContent: text }));
    return b;
  }

  function renderChips() {
    const up = nextUp(), list = [chip("Whole piece", !active, clear)];
    const all = [...saved.map(asBars)];
    if (active && !active.id) all.push(active);
    all.sort((a, b) => a.first - b.first || a.last - b.last);
    for (const p of all) {
      const on = !!active && active.first === p.first && active.last === p.last;
      const r = p.id && saved.find(s => s.id === p.id);
      const c = chip(span(p), on, () => on || pick(p), p.id ? "" : " is-draft");
      c.setAttribute("aria-label", `${label(p)}${r ? `, ${r.reps} reps, ${r.clean} clean` : ", not saved"}`);
      if (r) c.append(dotsFor(r, 5));
      if (up && r && up.id === r.id && !on) c.append(Object.assign(document.createElement("span"), { className: "chip-tag", textContent: "next up" }));
      list.push(c);
    }
    if (!saved.length && !active && marking === null)
      list.push(Object.assign(document.createElement("span"), { className: "chip-hint", textContent: "Drag across bars on the score to pick a passage, then drag its green handles to adjust it." }));
    chips.replaceChildren(...list);
  }

  function renderLogger() {
    rep.hidden = !active;
    if (!active) return;
    title.textContent = label(active);
    yes.disabled = no.disabled = busy;
    dots.replaceChildren(...dotsFor(record(), 8).childNodes);
    if (!note.textContent && !record()) note.textContent = pieceId ? "Play it through, then say how it went." : "Open a piece from your library to count reps.";
    showActions();
  }

  function render() {
    renderChips();
    renderLogger();
    paint();
  }

  // ---- wiring ----
  yes.addEventListener("click", () => addRep(true));
  no.addEventListener("click", () => addRep(false));
  form.addEventListener("submit", e => {
    e.preventDefault();
    const chosen = parse(input.value);
    input.setCustomValidity(chosen ? "" : `Type bar numbers from ${number(0)} to ${number(bars() - 1)}, like 12-16.`);
    if (!chosen) return input.reportValidity();
    input.value = "";
    input.blur();
    pick(chosen);
  });
  input.addEventListener("input", () => input.setCustomValidity(""));

  const render0 = osmd.render.bind(osmd);   // OSMD re-renders on zoom and resize; the boxes follow
  osmd.render = (...args) => { const out = render0(...args); draw(); return out; };

  // After the score is drawn: fetch the piece's passages and pick up the one the last visit left on.
  async function ready(sectionId) {
    draw();
    if (!pieceId) return render();
    try { saved = await api(`/api/pieces/${pieceId}/sections`); } catch (err) { console.error(err); }
    const last = saved.find(p => p.id === sectionId);
    if (last) pick(asBars(last)); else render();
  }

  return {
    ready, next, previous, toStart, markStart, markEnd, clear, moved,
    nextBar: () => bar(1), previousBar: () => bar(-1),
    rep: addRep,
    get bars() { return active && { first: active.first, last: active.last }; },
  };
}
