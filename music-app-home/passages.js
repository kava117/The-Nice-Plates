/* Passages on the practice page: pick bars out of the score, loop them, and count clean reps.

   Making one happens on the score, where the musician already reads: drag across bars, type
   "12-16" in the Bars box, or press [ and ] at the cursor. "+ New passage" says how (and lets a
   tap on the first bar, then the last, do it on a phone). A click on a bar moves the cursor
   there; a click outside the picked passage, or Esc, lets go of it. A double click picks one bar.
   Bars outside the passage fade instead of blurring, so the lead-in stays readable.

   Practising: after each time through, "Was that correct?" Yes (Y) or Not yet (N). Each answer is
   a rep saved to the passage (Section_Reps, with the tempo), it starts the practice timer, and it
   steers the tempo: three correct in a row offers the next tempo up, two misses a slower one.

   Keeping: a passage saves (Sections) as soon as it's made, and dragging its handles saves its
   new bars a moment later, its reps kept. Each passage is a chip with its last reps and a delete
   button; "Next up" marks the one with the fewest recent correct reps. Deleting waits 5 seconds
   behind an Undo before it reaches the server.

   Bars are measure indexes from 0 here; the server counts them from 1 (index + 1). */

const STREAK = 3;   // clean reps in a row at one tempo before offering a faster one
const SLIPS = 2;    // misses in a row before offering a slower one
const DOTS = 5;
const TRASH = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>';     // most reps shown as dots for a passage, the same last few "next up" ranks by

// els: the elements in practice.html's #controls; tempo: the player's tempo slider (percent).
// onRep runs after each saved rep; onPick when the passage changes or a click moves the cursor;
// playing() says if the player is going.
function addPassages(osmd, els, { pieceId, tempo, onRep = () => {}, onPick = () => {}, playing = () => false }) {
  const { score, chips, form, input, rep, title, yes, no, dots, note, actions, newButton, remove, empty, selectHint, cancelSelect, firstHint } = els;
  // firstHint: how to make a passage, by the sheet music, until this browser has made its first one
  const FIRST = "made-a-passage";
  let madeOne = false;
  try { madeOne = localStorage.getItem(FIRST) === "1"; } catch {}
  let saved = [];        // the piece's passages from the server, in bar order
  let active = null;     // the picked passage: {first, last, id}; id is null until it's saved
  let preview = null;    // bars under a drag, or between [ and the cursor, not picked yet
  let marking = null;    // the bar [ was pressed on, until ] picks the passage
  let boxes = [];        // one box per bar, in px from the top left of #score
  let undoable = false;  // the last rep can be taken back
  let offers = [];       // [text, action] buttons offered after a rep: a tempo change, the next passage
  let slips = new Map(); // bars the last go heard (listen.js) went wrong in: index -> what happened
  let busy = false;
  let selecting = false; // "+ New passage" was pressed: the next drag (or two taps) makes a passage
  let moveTimer = null;  // a handle drag's new bars, saved after a short pause
  const doomed = new Map(); // passages deleted but still undoable: id -> the server's DELETE, to send

  const layer = Object.assign(document.createElement("div"), { className: "score-bars" });
  layer.setAttribute("aria-hidden", "true");   // the Bars box and [ ] keys do the same job from the keyboard

  // ---- talking to the server ----
  async function api(url, method = "GET", body, extra = {}) {
    const r = await fetch(url, body ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), ...extra } : { method, ...extra });
    if (!r.ok) throw Object.assign(new Error(`${method} ${url}: ${r.status}`), { status: r.status, body: await r.json().catch(() => null) });
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
  const span = p => (p.first === p.last ? `${number(p.first)}` : `${number(p.first)}–${number(p.last)}`);
  const label = p => (p.first === p.last ? "Bar " : "Bars ") + span(p);
  const range = (a, b) => ({ first: Math.min(a, b), last: Math.max(a, b) });
  const asBars = record => ({ first: record.start - 1, last: record.end - 1, id: record.id });
  const record = () => active && active.id && saved.find(p => p.id === active.id);
  const speedName = percent => {
    const bpm = osmd.Sheet && osmd.Sheet.DefaultStartTempoInBpm;
    return bpm ? `${Math.round(bpm * percent / 100)} bpm` : `${percent} %`;
  };

  // "12-16", "12–16", "12 16", "12" or "12 to 16", in printed bar numbers, to measure indexes
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
    flushMove();
    const match = savedFor(chosen);
    active = match ? asBars(match) : chosen && { ...chosen, id: null };
    undoable = false;
    offers = [];
    slips = new Map();
    marking = preview = null;
    selecting = false;
    note.textContent = "";
    if (active) toStart();   // back to the whole piece leaves the cursor where it is
    if (active && !active.id && pieceId) autoSave();
    else remember();
    render();
    onPick();
  }
  // A new passage saves as soon as it's made: no Save button to forget.
  async function autoSave() {
    const mine = active;
    try {
      await save(mine);
      if (active === mine) toast("Passage saved");
    } catch (err) {
      console.error(err);
      if (active === mine) toast("That passage didn't save. Check the connection.", { action: "Try again", onAction: autoSave, ms: 6000 });
    }
    render();
  }
  function clear() {
    if (selecting) { selecting = false; marking = preview = null; return render(); }   // Esc first leaves "+ New passage"
    if (marking !== null) { marking = preview = null; return render(); }   // Esc between [ and ] only drops the mark
    if (active) pick(null);
  }
  function startNew() {   // "+ New passage": say how, and let go of the picked passage so the score is clear
    if (selecting) return clear();
    if (active) pick(null);
    selecting = true;
    marking = preview = null;
    render();
  }

  // ---- moving a saved passage's ends: its new bars save after a short pause, its reps kept ----
  function move(bars) {
    if (!active || !active.id) return pick(bars);
    const match = savedFor(bars);
    if (match && match.id !== active.id) { toast(`${label(bars)} is already a passage`); return pick(bars); }
    Object.assign(active, bars);
    const r = record();
    if (r) Object.assign(r, { start: bars.first + 1, end: bars.last + 1 });
    clearTimeout(moveTimer);
    moveTimer = setTimeout(flushMove, 600);
    toStart();
    render();
    onPick();
  }
  async function flushMove() {
    if (!moveTimer) return;
    clearTimeout(moveTimer);
    moveTimer = null;
    const r = record();
    if (!r) return;
    try {
      keep(await api(`/api/sections/${r.id}`, "PUT", { start: r.start, end: r.end }));
      toast("Passage saved");
    } catch (err) {
      console.error(err);
      try { saved = await api(`/api/pieces/${pieceId}/sections`); } catch {}   // back to what the server has
      const now = saved.find(p => p.id === r.id);
      if (active && active.id === r.id && now) Object.assign(active, asBars(now));
      toast(err.status === 409 ? "Those bars are already a passage" : "The new bars didn't save. Check the connection.");
    }
    render();
  }

  // ---- deleting: gone at once, with 5 seconds to Undo before the server forgets it and its reps ----
  function del(p) {
    if (!p) return;
    flushMove();
    const r = p.id && saved.find(s => s.id === p.id);
    const was = active && active.first === p.first && active.last === p.last;
    if (!r) { if (was) pick(null); return; }   // never saved: nothing to undo
    saved = saved.filter(s => s.id !== r.id);
    const send = () => { doomed.delete(r.id); return api(`/api/sections/${r.id}`, "DELETE", undefined, { keepalive: true }).catch(console.error); };
    doomed.set(r.id, send);
    if (was) pick(null); else render();
    const restore = () => {
      undoDelete = null;
      doomed.delete(r.id);
      keep(r);
      if (was) pick(asBars(r)); else render();
      toast("Passage restored");
    };
    undoDelete = restore;
    toast(`${label(asBars(r))} deleted`, {
      action: "Undo", ms: 5000, onAction: restore,
      onEnd: () => { if (undoDelete === restore) undoDelete = null; send(); },
    });
  }
  // Ctrl+Z (Cmd+Z) undoes the delete while its Undo is still offered: no reaching for the toast.
  let undoDelete = null;
  addEventListener("keydown", e => {
    if (!undoDelete || e.key.toLowerCase() !== "z" || !(e.ctrlKey || e.metaKey) || e.shiftKey) return;
    if (e.target.closest("input, textarea, [contenteditable]")) return;   // the box's own undo
    e.preventDefault();
    const box = document.getElementById("toast");
    if (box && box.finish) box.finish(true);   // close the toast without sending the delete
    if (undoDelete) undoDelete();
  });
  const flushDeletes = () => Promise.all([...doomed.values()].map(send => send()));
  addEventListener("pagehide", () => { flushDeletes(); flushMove(); });
  // The coach (coach.js) names bars in its answers: they light up under the pointer, and a click picks them.
  function point(text) {   // "bars 17-20" lights those bars; null turns them off
    const shown = text && parse(text);
    for (const el of layer.querySelectorAll(".score-bar")) {
      const i = +el.dataset.index;
      el.classList.toggle("pointed", !!shown && i >= shown.first && i <= shown.last);
    }
  }
  function choose(text) {   // false: this piece has no such bars
    const chosen = parse(text);
    if (chosen) pick(chosen);
    return !!chosen;
  }
  // [{bar, text}]: where a go slipped, marked on the score until the next one
  function mark(list) {
    slips = new Map(list.map(s => [s.bar, s.text]));
    paint();
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
    if (marking === null && active && active.id) return move(range(Math.min(at, active.first), at));
    pick(marking !== null ? range(marking, at) : range(at, at));
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
    layer.classList.toggle("is-selecting", selecting);
    for (const el of layer.querySelectorAll(".score-bar")) {
      const i = +el.dataset.index;
      el.classList.toggle("in", !!shown && i >= shown.first && i <= shown.last);
      el.classList.toggle("slip", slips.has(i));
      if (slips.has(i)) el.title = slips.get(i);
      else el.removeAttribute("title");
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
      const text = marking !== null ? `${label(shown)}: ${selecting ? "now tap the last bar" : "] on the last bar"}` : label(shown);   // say how to finish
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
  let layerUp = 0;   // the click that follows a drag on the score isn't a click outside the passage
  layer.addEventListener("pointerup", e => {
    layerUp = performance.now();
    if (resizing && e.pointerId === resizing.id) {
      const moved = preview && (preview.first !== active.first || preview.last !== active.last) && preview;
      resizing = preview = null;
      return moved ? move(moved) : paint();
    }
    if (!press || e.pointerId !== press.id) return;
    const done = press;
    press = preview = null;
    if (done.dragging) pick(range(done.from, done.to));
    else if (selecting && marking === null) { marking = done.from; preview = range(done.from, done.from); paint(); }   // "+ New passage": first tap
    else if (selecting) pick(range(marking, done.from));                                                               // ...and the last
    else if (e.shiftKey && active) pick(done.from < active.first ? range(done.from, active.last) : range(active.first, done.from));
    else {   // a click moves the cursor, and stops the player first; outside the picked passage it lets go of it
      if (active && (done.from < active.first || done.from > active.last)) pick(null);
      onPick();
      goTo(done.from);
    }
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
  function misses(p) {
    let n = 0;
    for (const r of [...p.recent].reverse()) { if (r.clean) break; n++; }
    return n;
  }
  function nextUp() {   // the saved passage with the fewest clean reps lately; never practiced beats long ago
    if (saved.length < 2) return null;
    const rank = p => [p.recent.slice(-DOTS).filter(r => r.clean).length, p.last_practiced || ""];
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

  async function save(p = active) {   // p: the passage to keep, even if another is picked meanwhile
    if (!p || p.id) return record();
    await flushDeletes();   // re-making bars just deleted must not get back the row about to go
    const made = keep(await api(`/api/pieces/${pieceId}/sections`, "POST", { start: p.first + 1, end: p.last + 1 }));
    p.id = made.id;
    if (!madeOne) { madeOne = true; try { localStorage.setItem(FIRST, "1"); } catch {} }
    if (p !== active) return made;
    await remember();   // finish before the timer starts: two requests at once would each write the session cookie, and one would lose
    return made;
  }

  // why: what went wrong, when listen.js heard the go; it leads the line under the dots
  async function addRep(clean, why = "") {
    if (!active || busy) return;
    if (!pieceId) { note.textContent = "Open a piece from your library to count reps."; return; }
    busy = true;
    try {
      await save();
      keep(await api(`/api/sections/${active.id}/reps`, "POST", { clean, tempo: +tempo.value }));
      undoable = true;
      onRep();
      feedback(clean, why);
      if (!playing()) toStart();   // ready for the next time through
    } catch (err) {
      console.error(err);
      note.textContent = "That rep didn't save. Check the connection and press again.";
    } finally {
      busy = false;
      render();
    }
  }

  function feedback(clean, why) {
    const p = record(), n = streak(p), t = +tempo.value;
    let said = "";
    offers = [];
    if (clean && n >= STREAK && t < 100) {
      said = `${n} correct in a row at ${speedName(t)}.`;
      offers.push([`Try ${speedName(t + 10)}`, () => setTempo(t + 10)]);
    } else if (clean && n >= STREAK) {
      const up = nextUp();
      said = `${n} correct in a row at full speed.`;
      if (up && up.id !== p.id) offers.push([`Next up: ${label(asBars(up))}`, () => pick(asBars(up))]);
    } else if (clean) {
      said = `Correct: ${n} of ${STREAK} in a row.`;
    } else if (misses(p) >= SLIPS && t > +tempo.min) {
      said = `${misses(p)} misses in a row.`;
      offers.push([`Slow to ${speedName(t - 10)}`, () => setTempo(t - 10)]);
    } else if (!why) {
      said = "Not yet.";
    }
    note.textContent = [why, said].filter(Boolean).join(" ");
  }

  function showActions() {
    const buttons = offers.map(([text, act]) => button(text, "btn btn-ghost press rep-offer", () => { offers = []; note.textContent = ""; act(); showActions(); }));
    if (undoable) buttons.push(button("Undo last answer", "link-button", undo));
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
    note.textContent = "Took back the last answer.";
    render();
  }

  // ---- the passage row and the rep row ----
  function dotsFor(p) {
    const box = Object.assign(document.createElement("span"), { className: "dots" });
    for (const r of p ? p.recent.slice(-DOTS) : []) {
      const dot = Object.assign(document.createElement("span"), { className: r.clean ? "dot is-clean" : "dot" });
      dot.title = `${r.clean ? "Correct" : "Not yet"}${r.tempo ? ` at ${speedName(r.tempo)}` : ""}`;
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
    const up = nextUp(), list = [chip("Whole piece", !active, () => active && pick(null))];
    const all = [...saved.map(asBars)];
    if (active && !active.id) all.push(active);
    all.sort((a, b) => a.first - b.first || a.last - b.last);
    for (const p of all) {
      const on = !!active && active.first === p.first && active.last === p.last;
      const r = p.id && saved.find(s => s.id === p.id);
      const c = chip(span(p), on, () => on || pick(p));
      c.setAttribute("aria-label", `${label(p)}${r ? `, ${r.reps} reps, ${r.clean} correct` : ", saving"}`);
      if (r && !on) c.append(dotsFor(r));   // the picked passage's dots are in the rep row below
      if (up && r && up.id === r.id && !on) c.append(Object.assign(document.createElement("span"), { className: "chip-tag", textContent: "next up" }));
      const wrap = Object.assign(document.createElement("span"), { className: `chip-wrap${on ? " is-on" : ""}${p.id ? "" : " is-draft"}` });
      wrap.append(c, trash(`Delete ${label(p).toLowerCase()}`, "chip-delete", () => del(p)));
      list.push(wrap);
    }
    chips.replaceChildren(...list);
    if (firstHint) firstHint.hidden = madeOne || saved.length > 0 || selecting;
    const none = !saved.length && !active && !selecting;
    chips.hidden = selecting;
    chips.classList.toggle("is-alone", !saved.length && !active);   // just Whole piece: room for the empty state beside it
    empty.hidden = !none || !!(firstHint && !firstHint.hidden);   // the tip by the score already says it
    selectHint.hidden = !selecting;
    newButton.setAttribute("aria-pressed", selecting);
    newButton.classList.toggle("is-first", none);   // the one way to start: it stands out until there's a passage
    rep.closest("#controls").classList.toggle("is-selecting", selecting);
  }
  // A bin icon button, labelled for screen readers
  function trash(name, className, onClick) {
    const b = button("", `${className} press`, e => { e.stopPropagation(); onClick(); });
    b.setAttribute("aria-label", name);
    b.title = name;
    b.innerHTML = TRASH;
    return b;
  }

  function renderLogger() {
    rep.hidden = !active;
    if (!active) return;
    title.textContent = label(active);
    remove.setAttribute("aria-label", `Delete ${label(active).toLowerCase()}`);
    yes.disabled = no.disabled = busy;   // only while an answer saves; Delete never waits
    dots.replaceChildren(...dotsFor(record()).childNodes);
    if (!note.textContent && !record()) note.textContent = pieceId ? "" : "Open a piece from your library to count reps.";
    showActions();
  }

  function render() {
    renderChips();
    renderLogger();
    paint();
  }

  // ---- wiring ----
  remove.addEventListener("click", () => del(active));
  newButton.addEventListener("click", startNew);
  cancelSelect.addEventListener("click", clear);
  // A click on the page outside the score and the controls lets go of the picked passage (Esc does too).
  document.addEventListener("click", e => {
    if ((!active && !selecting) || performance.now() - layerUp < 400) return;
    if (e.target.closest("#controls, .coach, .score-bars, .toast-region, .tour, button, a, input, select, textarea, summary, label, audio, [role=dialog]")) return;
    if (!e.target.closest("main")) return;
    selecting ? clear() : pick(null);
  });
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
    ready, next, previous, toStart, markStart, markEnd, clear, moved, point, choose, setTempo, mark, number, label, startNew,
    deleteActive: () => del(active),
    get selecting() { return selecting; },
    get count() { return saved.length; },
    tell: text => { note.textContent = text; },
    nextBar: () => bar(1), previousBar: () => bar(-1),
    rep: addRep,
    get bars() { return active && { first: active.first, last: active.last }; },
  };
}
