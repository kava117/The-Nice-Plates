/* Listening on the practice page. With Listen on, each time through the picked passage is
   heard, checked against the score, and counted as a rep: clean, or not yet and where.

   The notes come from Spotify's basic-pitch model (basic-pitch/, loaded on the first Listen),
   run in this browser: the sound is never recorded or sent anywhere. */

const TOGETHER = 0.06;   // notes struck within this many seconds of each other are one chord
const GHOST = 0.3;       // lining up: a heard note the score doesn't have costs this, a score note not heard costs 1,
const TIMING = 0.7;      // and a chord played twice as slow or fast as the pace so far about half that
const OVERTONES = [12, 19, 24, 28, 31, 36];   // a piano note also rings an octave up, a twelfth up, ...

const LETTERS = { 0: "C", 2: "D", 4: "E", 5: "F", 7: "G", 9: "A", 11: "B" };
const SIGNS = { "-2": "𝄫", "-1": "♭", 0: "", 1: "♯", 2: "𝄪" };
const SHARPS = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const FLATS = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
const spell = pitch => LETTERS[pitch.FundamentalNote] + (SIGNS[pitch.AccidentalHalfTones] ?? "");

// The passage as the score has it: [{t, bar, notes: [{midi, name, len}]}], times in seconds at the score's tempo.
function passageNotes(osmd, bars) {
  const it = osmd.Sheet.MusicPartManager.getIterator();
  while (!it.EndReached && it.CurrentMeasureIndex < bars.first) it.moveToNext();
  const events = scoreEvents(it, step => step.CurrentMeasureIndex >= bars.first && step.CurrentMeasureIndex <= bars.last);
  return events.filter(e => e.notes.length).map(e => ({
    t: e.seconds, bar: e.measure, notes: e.notes.map(n => ({ midi: n.midi, name: spell(n.pitch), len: n.seconds })),
  }));
}

// ---- hearing: sound in, notes out ----

// The model hears 2 s windows that overlap, at 22 050 samples a second, like basic-pitch's own
// evaluateModel. Feeding it one window at a time keeps every shape the same, so the graphics card
// compiles its programs once (on the first Listen), and windows are heard while the music goes on.
const RATE = 22050, WINDOW = 43844, HOP = 36164, LEAD = 3840, EDGE = 15, FRAMES_PER_SECOND = 86;
let model = null, work = Promise.resolve();   // one window at a time, in order, whichever go it's from
function loadModel() {
  model = model || (async () => {
    if (!window.basicPitch) await loadScript("/basic-pitch/basic-pitch.min.js");
    const graph = await basicPitch.loadGraphModel("/basic-pitch/model.json");
    const run = async window => {
      const input = basicPitch.tensor(window, [1, WINDOW, 1]);
      const out = graph.execute(input, ["Identity_1", "Identity_2"]);   // frames, onsets
      const [frames, onsets] = await Promise.all(out.map(t => t.array()));
      input.dispose();
      out.forEach(t => t.dispose());
      return [frames[0].slice(EDGE, -EDGE), onsets[0].slice(EDGE, -EDGE)];
    };
    try { await run(new Float32Array(WINDOW)); }
    catch (err) {   // some graphics drivers can't run it; the processor can, more slowly
      console.warn("Listening without the graphics card:", err);
      await basicPitch.setBackend("cpu");
      await run(new Float32Array(WINDOW));
    }
    return run;
  })();
  model.catch(() => { model = null; });   // a failed download can be tried again
  return model;
}

// Feed it sound as it comes (mono, 22 050 a second); finish() gives the notes heard:
// [{midi, t, d, a}], pitch, start and length in seconds, and loudness from 0 to 1.
function hearing() {
  let audio = new Float32Array(LEAD + RATE * 20), length = LEAD, next = 0, mine = Promise.resolve(), failed = null;
  const frames = [], onsets = [];
  const queue = start => { mine = work = work.then(async () => {
    if (failed) return;
    try {
      const window = new Float32Array(WINDOW);   // the last ones run on into silence
      window.set(audio.subarray(start, Math.min(start + WINDOW, length)));
      const [f, o] = await (await loadModel())(window);
      frames.push(...f);
      onsets.push(...o);
    } catch (err) { failed = err; }   // this go is lost; the next one starts afresh
  }); };
  return {
    push(samples) {
      if (length + samples.length > audio.length) {
        const bigger = new Float32Array(2 * (length + samples.length));
        bigger.set(audio.subarray(0, length));
        audio = bigger;
      }
      audio.set(samples, length);
      length += samples.length;
      for (; next + WINDOW <= length; next += HOP) queue(next);
    },
    get seconds() { return (length - LEAD) / RATE; },
    async finish() {
      for (; next < length; next += HOP) queue(next);
      await mine;
      if (failed) throw failed;
      const keep = Math.floor((length - LEAD) * FRAMES_PER_SECOND / RATE);
      // melodia off: no notes made up from ringing without a fresh strike, which a piano is full of
      return basicPitch.noteFramesToTime(basicPitch.outputToNotesPoly(frames.slice(0, keep), onsets.slice(0, keep), 0.5, 0.3, 5, true, null, null, false))
        .map(n => ({ midi: n.pitchMidi, t: n.startTimeSeconds, d: n.durationSeconds, a: n.amplitude }))
        .sort((a, b) => a.t - b.t);
    },
  };
}

async function transcribe(samples) {   // all at once, for a take already recorded
  const heard = hearing();
  heard.push(samples);
  return heard.finish();
}

// ---- checking: what was heard against what the score says ----

// How many of the chord's notes are among the heard ones; an octave off counts most of the way,
// since the model sometimes hears a piano note an octave out.
function overlap(want, got) {
  let found = 0;
  for (const w of want) {
    if (got.some(n => n.midi === w.midi)) found += 1;
    else if (got.some(n => Math.abs(n.midi - w.midi) === 12)) found += 0.8;
  }
  return found;
}

// Pairs chords of the score with chords heard, in order: an edit distance over chords, where a
// pairing also costs for being out of time with the pace so far (heard seconds per score second,
// starting from `pace`). Anything heard before the passage or after it is free. Returns [[i, j]].
function lineUp(expected, groups, pace) {
  const n = expected.length, w = groups.length + 1, size = (n + 1) * w;
  const cost = new Float64Array(size), step = new Uint8Array(size), speed = new Float64Array(size).fill(pace);
  const lastI = new Int32Array(size).fill(-1), lastJ = new Int32Array(size);
  const move = (to, from, c, how) => {
    cost[to] = c; step[to] = how; speed[to] = speed[from]; lastI[to] = lastI[from]; lastJ[to] = lastJ[from];
  };
  for (let i = 1; i <= n; i++) {
    const want = expected[i - 1].notes;
    for (let j = 0; j < w; j++) {
      const here = i * w + j, up = here - w;
      move(here, up, cost[up] + want.length, 1);   // not played
      if (!j) continue;
      const extra = cost[here - 1] + GHOST * groups[j - 1].notes.length;   // heard, not in the score
      if (extra < cost[here]) move(here, here - 1, extra, 2);
      const found = overlap(want, groups[j - 1].notes), from = up - 1;
      if (!found) continue;
      let c = cost[from] + want.length - found, p = speed[from];
      if (lastI[from] >= 0) {
        const ratio = (groups[j - 1].t - groups[lastJ[from]].t + 0.05) / (p * (expected[i - 1].t - expected[lastI[from]].t) + 0.05);
        c += Math.min(TIMING * Math.abs(Math.log(ratio)), 1.5);
        p *= Math.min(Math.max(ratio, 0.67), 1.5) ** 0.3;   // follows the player, but one pause doesn't throw it
      }
      if (c < cost[here]) {
        cost[here] = c; step[here] = 3; speed[here] = p; lastI[here] = i - 1; lastJ[here] = j - 1;
      }
    }
  }
  let j = 0;
  for (let k = 1; k < w; k++) if (cost[n * w + k] < cost[n * w + j]) j = k;
  const pairs = [];
  for (let i = n; i > 0;) {
    const how = step[i * w + j];
    if (how === 3) pairs.push([--i, --j]);
    else if (how === 2) j--;
    else i--;
  }
  return pairs.reverse();
}

// When each chord of the score was played, or would have been: its pair's time, else in
// proportion between the nearest pairs. pace: the middle one between pairs, so a pause doesn't skew it.
function timeline(expected, groups, pairs, guess) {
  const ratios = [];
  for (let k = 1; k < pairs.length; k++) {
    const score = expected[pairs[k][0]].t - expected[pairs[k - 1][0]].t;
    if (score > 0.05) ratios.push((groups[pairs[k][1]].t - groups[pairs[k - 1][1]].t) / score);
  }
  ratios.sort((a, b) => a - b);
  const pace = ratios.length ? ratios[ratios.length >> 1] : guess;
  const paired = new Map(pairs.map(([i, j]) => [i, groups[j].t]));
  const at = expected.map((chord, i) => {
    if (paired.has(i)) return paired.get(i);
    let k = pairs.length - 1;
    while (k >= 0 && pairs[k][0] > i) k--;
    const before = pairs[k], after = pairs[k + 1];
    if (before && after) {
      const [a, b] = [expected[before[0]].t, expected[after[0]].t];
      return groups[before[1]].t + (chord.t - a) / (b - a) * (groups[after[1]].t - groups[before[1]].t);
    }
    const near = before || after;
    return groups[near[1]].t + (chord.t - expected[near[0]].t) * pace;
  });
  return { at, pace };
}

// One time through the passage: what was played right, what went wrong, and where.
// pace: a first guess at heard seconds per score second; least: fewest notes that make it a go at the passage.
function checkPass(expected, heard, { pace: guess = 1, flats = false, least } = {}) {
  const total = expected.reduce((sum, chord) => sum + chord.notes.length, 0), none = { heard: false, total, played: 0 };
  const groups = [];
  for (const n of heard) {
    const last = groups.at(-1);
    if (last && n.t - last.t <= TOGETHER) last.notes.push(n);
    else groups.push({ t: n.t, notes: [n] });
  }
  const pairs = lineUp(expected, groups, guess);
  if (!pairs.length) return none;
  const { at, pace } = timeline(expected, groups, pairs, guess);
  const slack = at.map((t, i) => {   // how far off a note can land and still be the score's note
    const gaps = [at[i + 1] - t, t - at[i - 1]].filter(g => g > 0);
    return Math.min(Math.max(0.4 * Math.min(...gaps, 0.6), 0.07), 0.25);
  });

  // note by note: the closest unused heard note of that pitch, else an octave off
  const used = new Set(), name = midi => (flats ? FLATS : SHARPS)[midi % 12];
  const closest = (list, t) => list.sort((a, b) => Math.abs(a.t - t) - Math.abs(b.t - t))[0];
  const chords = expected.map((chord, i) => {
    const got = [], missed = [];
    for (const want of chord.notes) {
      const near = heard.filter(n => !used.has(n) && Math.abs(n.t - at[i]) <= slack[i]);
      const hit = closest(near.filter(n => n.midi === want.midi), at[i]) || closest(near.filter(n => Math.abs(n.midi - want.midi) === 12), at[i]);
      if (hit) { used.add(hit); got.push(want); } else missed.push(want);
    }
    return { bar: chord.bar, got, missed };
  });
  // The model can be late to catch the middle notes of a big chord: heard while the score
  // still has it sounding, it's that note.
  chords.forEach((c, i) => {
    c.missed = c.missed.filter(want => {
      const late = heard.find(n => !used.has(n) && n.midi === want.midi && n.t > at[i] && n.t <= at[i] + want.len * pace);
      if (late) { used.add(late); c.got.push(want); }
      return !late;
    });
  });
  const played = chords.reduce((sum, c) => sum + c.got.length, 0);
  const first = chords.findIndex(c => c.got.length), last = chords.findLastIndex(c => c.got.length);
  const count = list => list.reduce((sum, c) => sum + c.missed.length, 0);
  const head = chords.slice(0, first), tail = chords.slice(last + 1);
  const startedAt = count(head) > 1 ? chords[first].bar : null, stoppedAt = count(tail) > 1 ? chords[last + 1].bar : null;
  // A go at the passage: most of it, or a clean start on its first notes that broke off.
  const opening = chords.slice(0, 3), began = startedAt === null && count(opening) <= 1 && played >= Math.min(4, total);
  if (played < (least ?? Math.max(3, total / 2)) && !began) return { ...none, played };
  const from = at[first] - slack[first], to = at[last] + slack[last];

  // A missed note with another key struck where it should have been, a few keys away: the wrong
  // note. Not the same key sounding on (held or pedalled), which the model can hear again.
  const echo = n => heard.some(o => o !== n && o.midi === n.midi && o.t < n.t - TOGETHER && o.t + o.d >= n.t - 0.03);
  const wrong = [], missed = [], faint = [];
  chords.forEach((c, i) => {
    for (const want of c.missed) {
      const near = heard.filter(n => !used.has(n) && Math.abs(n.t - at[i]) <= Math.max(slack[i], 0.15) &&
        n.midi !== want.midi && Math.abs(n.midi - want.midi) <= 4 && !echo(n));
      const instead = near.sort((a, b) => Math.abs(a.midi - want.midi) - Math.abs(b.midi - want.midi))[0];
      if (instead && i >= first && i <= last) {
        used.add(instead);
        wrong.push({ bar: c.bar, wanted: want.name, played: name(instead.midi) });
      } else if ((i < first && startedAt !== null) || (i > last && stoppedAt !== null)) {
        continue;   // never reached: said once, as where it started or stopped
      } else (c.got.length ? faint : missed).push({ bar: c.bar, name: want.name });
    }
  });
  // faint: a note missing from a chord whose other notes were heard. The model loses the middle
  // of a big chord now and then, so a few don't count against the go; a whole chord missing does.

  // Heard notes the score doesn't have, besides the wrong ones. Most are the piano's own ringing:
  // a note held or pedalled sounding again, an overtone, or a quiet blip.
  const quietest = Math.min(...heard.filter(n => used.has(n)).map(n => n.a));
  const ringing = n => echo(n) || heard.some(o => o !== n && o.t <= n.t + TOGETHER && o.t + o.d >= n.t - 0.03 &&
    (OVERTONES.includes(n.midi - o.midi) || o.midi - n.midi === 12));
  const extras = heard.filter(n => !used.has(n) && n.t >= from && n.t <= to && !ringing(n) && !(n.d < 0.12 && n.a < quietest));

  // a pause: far longer between two chords than the score has, at the pace played
  let pausedAt = null, worst = 0;
  for (let i = first, k; i < last; i = k) {
    for (k = i + 1; k < last && !chords[k].got.length; k++);
    const want = (expected[k].t - expected[i].t) * pace, took = at[k] - at[i];
    if (took > Math.max(2 * want, want + 0.8) && took / want > worst) [pausedAt, worst] = [chords[k].bar, took / want];
  }

  return { heard: true, total, played, pace, from, to, wrong, missed, faint, extras: extras.length, startedAt, stoppedAt, pausedAt };
}

// Every time through the passage in what was heard, in order. Usually one; more when it was
// played round and round without a break, or begun again after a slip. Another time through
// starts on the passage's first notes; anything else heard around it doesn't count.
function compareTake(expected, heard, opts = {}) {
  const pass = checkPass(expected, heard, opts);
  if (!pass.heard) return [];
  const again = (notes, least) => compareTake(expected, notes, { ...opts, least }).filter(p => p.startedAt === null);
  return [
    ...again(heard.filter(n => n.t < pass.from - 0.3), 3),   // a go that broke off before this one
    pass,
    ...again(heard.filter(n => n.t > pass.to + 0.3)),
  ];
}

// ---- saying how it went ----

const joined = list => (list.length < 2 ? list.join("") : `${list.slice(0, -1).join(", ")} and ${list.at(-1)}`);

// A go in one line for the rep row, plus a note for each bar that went wrong, to mark on the score.
// number: a bar index to the number printed on the score.
function verdict(pass, number) {
  const bars = new Map(), at = i => bars.get(i) || bars.set(i, { notes: [], missed: [], also: [] }).get(i);
  pass.wrong.forEach(w => at(w.bar).notes.push(`${w.played} instead of ${w.wanted}`));
  const allowance = Math.max(1, Math.round(pass.total / 20));   // see faint, in checkPass
  [...pass.missed, ...(pass.faint.length > allowance ? pass.faint : [])].forEach(m => at(m.bar).missed.push(m.name));
  if (pass.startedAt !== null) at(pass.startedAt).also.push("started here");
  if (pass.pausedAt !== null) at(pass.pausedAt).also.push("a pause before this bar");
  if (pass.stoppedAt !== null) at(pass.stoppedAt).also.push("stopped here");
  if (!bars.size) return { clean: true, why: "", slips: [] };

  const said = b => [...b.notes, ...(b.missed.length ? [`missed ${joined(b.missed)}`] : [])];
  const order = [...bars.keys()].sort((a, b) => a - b), noted = order.filter(i => said(bars.get(i)).length);
  let why;
  if (pass.stoppedAt !== null) why = `Stopped in bar ${number(pass.stoppedAt)}.`;
  else if (pass.startedAt !== null) why = `Started at bar ${number(pass.startedAt)}.`;
  else if (noted.length) {
    why = `Bar ${number(noted[0])}: ${joined(said(bars.get(noted[0])))}.`;
    if (noted.length > 1) why += ` Also bar${noted.length > 2 ? "s" : ""} ${joined(noted.slice(1).map(number))}.`;
  } else why = `Paused before bar ${number(pass.pausedAt)}.`;
  const sentence = s => s[0].toUpperCase() + s.slice(1);
  // level 1: one slip in the bar (a note, or a pause before it); 2: more, or where the go started or stopped
  const level = (b, i) => (b.notes.length + b.missed.length + (i === pass.pausedAt) +
    2 * (i === pass.startedAt || i === pass.stoppedAt) >= 2 ? 2 : 1);
  return { clean: false, why, slips: order.map(i => ({ bar: i, level: level(bars.get(i), i), text: sentence(joined([...said(bars.get(i)), ...bars.get(i).also])) })) };
}

// ---- the Listen button ----

// Hands the microphone's sound over from the audio thread, about 20 ms at a time.
const TAP = `registerProcessor("tap", class extends AudioWorkletProcessor {
  constructor() { super(); this.block = new Float32Array(1024); this.n = 0; }
  process([input]) {
    const sound = input[0];
    for (let i = 0; sound && i < sound.length; i++) {
      this.block[this.n++] = sound[i];
      if (this.n === 1024) { this.port.postMessage(this.block); this.block = new Float32Array(1024); this.n = 0; }
    }
    return true;
  }
});`;

const READY = "Play it through. I’ll mark it when you stop.";

// button: Listen, in the rep row; status: the line beside it ("Was that clean?" while not listening).
// passages and player: passages.js and player.js; tempo: the tempo slider, a first guess at the pace.
function addListening(osmd, { button, status }, { passages, player, tempo }) {
  const word = button.querySelector(".listen-word"), asked = status.textContent;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioWorkletNode) {
    button.hidden = true;   // an old browser: the Yes and Not yet buttons still work
    return { toggle() {}, picked() {}, stop() {} };
  }
  let state = "off";            // off, starting, on
  let stream = null, context = null;
  let expected = [], longest = 1, length = 1;   // the passage's notes, its longest gap and its length, in score seconds
  let go = null;                // the go being heard: {heard, start, onset, loud, onsets}
  let now = 0, floor = null, recent = [], before = [], quietUntil = 0;
  let ratio = 1, pos = 0, prev = 0;

  const say = text => { status.textContent = text; };
  const pace = () => 100 / tempo.value;   // heard seconds per score second, at the slider's tempo
  function show() {
    button.setAttribute("aria-pressed", state !== "off");
    button.classList.toggle("is-on", state === "on");
    button.classList.toggle("is-starting", state === "starting");
    word.textContent = state === "on" ? "Listening" : state === "starting" ? "Starting…" : "Listen";
    button.closest(".rep-row").classList.toggle("is-listening", state === "on");
    if (state === "off") { say(asked); button.style.removeProperty("--level"); }
  }

  // A new passage, or none: listen for that one from its start.
  function picked() {
    go = null;
    if (!passages.bars) return stop();
    if (state !== "on") return;
    expected = passageNotes(osmd, passages.bars);
    const gaps = expected.slice(1).map((c, i) => c.t - expected[i].t);
    longest = Math.max(0.5, ...gaps);
    length = expected.length ? expected.at(-1).t - expected[0].t + longest : 1;
    say(READY);
  }

  async function start() {
    if (!passages.bars || state !== "off") return;
    state = "starting";
    show();
    say("Getting ready to listen…");
    let mine, ours;
    try {
      // the browser's voice clean-up would smear the notes, so ask for the plain sound
      mine = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
      ours = new AudioContext();
      const url = URL.createObjectURL(new Blob([TAP], { type: "text/javascript" }));
      await Promise.all([ours.audioWorklet.addModule(url), loadModel()]);
      URL.revokeObjectURL(url);
      if (state !== "starting") throw null;   // Listen was pressed again while it got ready
      const tap = new AudioWorkletNode(ours, "tap");
      tap.port.onmessage = e => { if (context === ours) block(e.data); };
      ours.createMediaStreamSource(mine)
        .connect(new BiquadFilterNode(ours, { type: "lowpass", frequency: 0.45 * RATE }))   // nothing the slower rate can't hold
        .connect(tap).connect(ours.destination);   // silent, but keeps it running
      [stream, context, state] = [mine, ours, "on"];
      [ratio, pos, prev, now, floor, recent, before] = [ours.sampleRate / RATE, 0, 0, 0, null, [], []];
      show();
      picked();
    } catch (err) {
      if (mine) mine.getTracks().forEach(t => t.stop());
      if (ours) ours.close();
      if (err === null) return;
      console.error(err);
      state = "off";
      show();
      passages.tell(err.name === "NotAllowedError" ? "The microphone is blocked for this page. Allow it from the address bar, then press Listen."
        : err.name === "NotFoundError" ? "No microphone found. Plug one in, then press Listen."
        : "Listening couldn’t start. Check the connection, then press Listen again.");
    }
  }

  function stop() {
    if (stream) stream.getTracks().forEach(t => t.stop());
    if (context) context.close();
    [stream, context, go, state] = [null, null, null, "off"];
    show();
  }

  // to 22 050 samples a second, with straight lines between samples (the filter took out what's too high to keep)
  function resample(x) {
    const out = new Float32Array(Math.ceil((x.length - pos) / ratio) + 1);
    let n = 0;
    for (; pos < x.length - 1; pos += ratio) {
      const i = Math.floor(pos), a = i < 0 ? prev : x[i];
      out[n++] = a + (x[i + 1] - a) * (pos - i);
    }
    pos -= x.length;
    prev = x[x.length - 1];
    return out.subarray(0, n);
  }

  // Each block of sound: is a go starting, going on, or over? A go starts on a note, and ends after a
  // moment's quiet, or when no new note comes for longer than the passage's longest wait.
  function block(samples) {
    const seconds = samples.length / context.sampleRate;
    now += seconds;
    let sum = 0;
    for (const s of samples) sum += s * s;
    const level = 10 * Math.log10(sum / samples.length + 1e-12);   // in dB
    floor = floor === null ? level : Math.min(level, floor + seconds * 0.5);   // the room: drops at once, rises slowly
    const onset = level > floor + 15 && recent.length > 0 && level - Math.min(...recent) > 4;
    recent = [...recent.slice(-2), level];
    button.style.setProperty("--level", Math.min(Math.max((level - floor - 6) / 30, 0), 1).toFixed(2));

    const sound = resample(samples);
    if (player.playing) { quietUntil = now + 1.5; go = null; }   // the page's own piano, and its ringing after
    if (now < quietUntil) return;
    if (!go) {
      before.push(sound);   // a moment before the first note, so its start is heard whole
      while (before.length > 1 && before.reduce((n, s) => n + s.length, 0) - before[0].length > 0.4 * RATE) before.shift();
      if (!onset) return;
      go = { heard: hearing(), start: now, onset: now, loud: now, onsets: 0 };
      before.forEach(s => go.heard.push(s));
      before = [];
      say("Listening…");
    } else go.heard.push(sound);
    if (onset) { go.onset = now; go.onsets++; }
    if (level > floor + 10) go.loud = now;
    const wait = Math.min(Math.max(1.5 * longest * pace() + 0.5, 2), 5);
    if (now - go.loud > 0.9 || now - go.onset > wait || now - go.start > Math.min(4 * length * pace() + 5, 120)) {
      const done = go;
      go = null;
      check(done);
    }
  }

  async function check(take) {
    const bars = passages.bars, notes = expected;
    if (take.onsets < 3 || take.heard.seconds < 1) { if (!go) say(READY); return; }   // a knock or a word, not a go
    say("Checking…");
    let passes;
    try {
      const flats = notes.flatMap(c => c.notes).filter(n => n.name.includes("♭")).length > notes.flatMap(c => c.notes).filter(n => n.name.includes("♯")).length;
      passes = compareTake(notes, await take.heard.finish(), { pace: pace(), flats });
    } catch (err) {
      console.error(err);
      passes = null;
    }
    const still = passages.bars;
    if (state !== "on" || !still || still.first !== bars.first || still.last !== bars.last) return;   // moved on meanwhile
    if (!go) say("Ready for the next go.");
    if (!passes) return passages.tell("Couldn’t check that go. Play it again, or mark it with Y or N.");
    if (!passes.length) return passages.tell(`That didn’t sound like ${passages.label(bars).toLowerCase()}, so it wasn’t counted.`);
    let said;
    for (const pass of passes) {
      said = verdict(pass, passages.number);
      await passages.rep(said.clean, said.why);
    }
    passages.mark(said.slips, said.clean);
  }

  button.addEventListener("click", () => (state === "off" ? start() : stop()));
  addEventListener("pagehide", stop);
  return { toggle: () => button.hidden || button.click(), picked, stop };
}
