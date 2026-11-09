/* Recording a take with the score: a bar of count-in ticks, then the take starts on the
   downbeat and a lane over the score shows the notes coming, with your pitch drawn as it
   happens (in tune, or off and which way).

   Pitch is found on the audio thread (YIN, de Cheveigné and Kawahara 2002) every ~5 ms from
   the last ~15 ms of sound, so the line keeps up with the bow. One note at a time: a violin,
   a voice, a flute, not piano chords. */

// The difference function, normalised: dips toward 0 at the period. Returns [period in
// samples (fractional), how clear the dip was (0 to 1)], or [0, 0] for no clear pitch.
function yin(x, start, n, tauMin, tauMax, d) {
  d[0] = 1;
  let sum = 0;
  for (let tau = 1; tau <= tauMax; tau++) {
    let s = 0;
    for (let j = 0; j < n; j++) { const v = x[start + j] - x[start + j + tau]; s += v * v; }
    sum += s;
    d[tau] = sum ? s * tau / sum : 1;
  }
  for (let tau = tauMin; tau < tauMax; tau++) {
    if (d[tau] >= 0.15) continue;
    while (tau + 1 < tauMax && d[tau + 1] < d[tau]) tau++;   // down to the bottom of the dip
    const a = d[tau - 1], b = d[tau], c = d[tau + 1], bend = a - 2 * b + c;
    return [tau + (bend > 0 ? (a - c) / (2 * bend) : 0), 1 - b];
  }
  return [0, 0];
}

const TRACK = `${yin}
registerProcessor("pitch", class extends AudioWorkletProcessor {
  constructor() {
    super();
    this.tauMax = Math.ceil(sampleRate / 170);          // just under the violin's open G (196 Hz)
    this.tauMin = Math.floor(sampleRate / 3200);
    this.n = Math.ceil(this.tauMax * 1.5);               // the window: n + tauMax samples, about 15 ms
    this.size = this.n + this.tauMax;
    this.hop = 256;
    this.x = new Float32Array(this.size * 2);
    this.d = new Float32Array(this.tauMax + 1);
    this.filled = 0; this.since = 0;
  }
  process([input]) {
    const sound = input[0];
    if (!sound) return true;
    for (let i = 0; i < sound.length; i++) {
      if (this.filled === this.x.length) { this.x.copyWithin(0, this.size); this.filled = this.size; }
      this.x[this.filled++] = sound[i];
      if (++this.since < this.hop || this.filled < this.size) continue;
      this.since = 0;
      const start = this.filled - this.size;
      let energy = 0;
      for (let j = start; j < this.filled; j++) energy += this.x[j] * this.x[j];
      const [tau, clear] = yin(this.x, start, this.n, this.tauMin, this.tauMax, this.d);
      // stamped with when the middle of the window was heard, on the page's audio clock
      const t = currentTime + (i + 1 - this.size / 2) / sampleRate;
      this.port.postMessage([t, tau ? sampleRate / tau : 0, clear, 10 * Math.log10(energy / this.size + 1e-12)]);
    }
    return true;
  }
});`;

const NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const noteName = midi => NAMES[((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);
const IN_TUNE = 0.35;      // semitones either side of the score's note that count as on it (35 cents)
const SLACK = 0.12;        // seconds early or late a note can be and still be held against the score's note
const PX_PER_SECOND = 150;

// Starts a take on `stream`. events: scoreEvents() from the cursor, at the score's tempo; speed: the
// tempo slider as a fraction; beats and beat: the count-in (how many, seconds each at that speed).
// onRoll fires on the downbeat (start recording then), onEnd when the music runs out.
// Returns { stop() }: stops listening and leaves the lane showing the take.
async function liveTake({ stream, osmd, lane, events, speed, beats, beat, onRoll, onEnd }) {
  const context = new AudioContext({ latencyHint: "interactive" });
  const url = URL.createObjectURL(new Blob([TRACK], { type: "text/javascript" }));
  try { await Promise.all([context.resume(), context.audioWorklet.addModule(url)]); }
  catch (err) { context.close(); throw err; }
  finally { URL.revokeObjectURL(url); }
  const tracker = new AudioWorkletNode(context, "pitch");
  const mute = new GainNode(context, { gain: 0 });
  context.createMediaStreamSource(stream).connect(tracker).connect(mute).connect(context.destination);   // silent, but keeps it running

  // The ticks go out a little ahead so none is late; the musician hears them outputLatency later,
  // so the downbeat they play to, and the score's notes, sit that much later on the audio clock.
  const heardLate = context.outputLatency || context.baseLatency || 0;
  const first = context.currentTime + 0.15;
  const downbeat = first + beats * beat;
  for (let k = 0; k < beats; k++) countTick(context, first + k * beat, k === 0);
  const zero = downbeat + heardLate;
  // the score's notes, in seconds from the downbeat: {t, end, midi}. Only the top staff: the
  // violin's own line, or a piano score's right hand, not the bass under it.
  const top = Math.min(...events.flatMap(e => e.notes.map(n => n.staff)));
  const notes = [];
  for (const e of events) for (const n of e.notes) if (n.staff === top) notes.push({ t: e.seconds / speed, end: (e.seconds + n.seconds) / speed, midi: n.midi });
  const end = (events.end ?? Math.max(...notes.map(n => n.end), 0) * speed) / speed;

  const trail = lane.trail = [];   // what was played: {t, midi, want, on} (on: true, false, or null where the score rests)
  let floor = null, last = [], rolling = false, ended = false, steps = 1, running = true;

  tracker.port.onmessage = ({ data: [t, hz, clear, level] }) => {
    // the room's own noise, as Listen keeps it: drops at once, settles on a steady hum, and under
    // music creeps up only half a dB a second, so a long held note doesn't fade from the lane
    if (floor === null || level < floor) floor = level;
    else floor += level < floor + 6 ? 0.05 * (level - floor) : 0.5 * 256 / context.sampleRate;
    if (!hz || clear < 0.8 || level < Math.max(floor + 12, -62)) { last = []; return; }
    const midi = 69 + 12 * Math.log2(hz / 440);
    last = [...last.slice(-2), midi];
    if (last.length < 3) return;
    const middle = [...last].sort((a, b) => a - b)[1];   // one stray frame (a bow change, a scratch) can't spike the line
    const s = t - zero;
    let want = null;
    for (const n of notes) {
      if (n.t - SLACK > s) break;
      if (s <= n.end + SLACK && (want === null || Math.abs(n.midi - middle) < Math.abs(want - middle))) want = n.midi;
    }
    trail.push({ t: s, midi: middle, want, on: want === null ? null : Math.abs(middle - want) <= IN_TUNE });
  };

  const now = () => {   // the audio clock, smoothly between its 3 ms steps
    const ts = context.getOutputTimestamp();
    if (!ts.performanceTime) return context.currentTime;   // no output device to time against
    return ts.contextTime + Math.min(Math.max(0, performance.now() - ts.performanceTime) / 1000, 0.05);
  };
  const draw = drawLane(lane, notes);
  function frame() {
    if (!running) return;
    const t = now();
    if (!rolling && t >= downbeat) { rolling = true; onRoll(); }
    const s = t - zero;
    while (steps < events.length && events[steps].seconds / speed <= s) { osmd.cursor.next(); steps++; }   // the score's cursor keeps time
    if (!ended && s > end + 0.8) { ended = true; onEnd(); }
    const counted = (t - first - heardLate) / beat;   // beats of the count-in heard so far
    draw(s, trail, s < 0 ? { left: beats - Math.floor(counted), of: beats, phase: counted - Math.floor(counted) } : null);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    stop() {
      if (!running) return;
      running = false;
      context.close();
      draw(trail.length ? trail.at(-1).t : 0, trail, null, true);
    },
  };
}

// One tick: a short high blip, higher on the first beat of the bar.
function countTick(context, at, first) {
  const tone = new OscillatorNode(context, { frequency: first ? 1760 : 1320 });
  const level = new GainNode(context, { gain: 0 });
  level.gain.setValueAtTime(0, at);
  level.gain.linearRampToValueAtTime(first ? 0.5 : 0.35, at + 0.002);
  level.gain.exponentialRampToValueAtTime(0.001, at + 0.06);
  tone.connect(level).connect(context.destination);
  tone.start(at);
  tone.stop(at + 0.07);
}

// The lane: pitch up the side, time along. The score's notes are blue bars sliding left to the
// now line; what you play is drawn at that line as it happens. Returns draw(now, trail, count, still).
function drawLane(canvas, notes) {
  const g = canvas.getContext("2d"), css = getComputedStyle(canvas);
  const colour = name => css.getPropertyValue(name).trim();
  const ink = colour("--ink"), muted = colour("--ink-muted"), line = colour("--line");
  const blue = colour("--lane-note"), on = colour("--lane-on"), off = colour("--lane-off");
  const midis = notes.map(n => n.midi);
  let low = Math.min(...midis, 67) - 2, high = Math.max(...midis, 67) + 2;
  if (high - low < 14) { const grow = (14 - (high - low)) / 2; low -= Math.floor(grow); high += Math.ceil(grow); }
  const motion = !matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (now, trail, count, still) => {
    const ratio = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
      canvas.width = Math.round(w * ratio);
      canvas.height = Math.round(h * ratio);
    }
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, w, h);
    const pad = 10, row = (h - 2 * pad) / (high - low), nowX = Math.round(w * 0.3);
    const x = t => nowX + (t - now) * PX_PER_SECOND, y = midi => h - pad - (midi - low) * row;
    const from = now - nowX / PX_PER_SECOND, to = now + (w - nowX) / PX_PER_SECOND;

    // a faint line for each C, named, so the eye has somewhere to stand
    g.font = "600 10px " + colour("--font-body");
    g.textBaseline = "middle";
    for (let m = Math.ceil(low / 12) * 12; m <= high; m += 12) {
      g.fillStyle = line;
      g.fillRect(0, Math.round(y(m)), w, 1);
      g.fillStyle = muted;
      g.fillText(noteName(m), 4, y(m) - 6);
    }

    // the score's notes, named when there's room
    for (const n of notes) {
      if (n.end < from || n.t > to) continue;
      const left = x(n.t), width = Math.max(4, (n.end - n.t) * PX_PER_SECOND - 2), top = y(n.midi) - row * 0.45;
      const playing = n.t <= now && now <= n.end;
      g.globalAlpha = n.end < now ? 0.35 : playing ? 1 : 0.75;
      g.fillStyle = blue;
      g.beginPath();
      g.roundRect(left, top, width, Math.max(3, row * 0.9), Math.min(4, row * 0.45));
      g.fill();
      if (width > 26 && row >= 7) {
        g.fillStyle = colour("--on-accent");
        g.fillText(noteName(n.midi), left + 4, y(n.midi) + 0.5);
      }
    }
    g.globalAlpha = 1;

    // now
    g.fillStyle = ink;
    g.globalAlpha = 0.5;
    g.fillRect(nowX, 0, 1, h);
    g.globalAlpha = 1;

    // what was played: dots, joined while the note carries on
    let i = trail.length;
    while (i > 0 && trail[i - 1].t >= from) i--;
    const paint = p => (p.on === null ? muted : p.on ? on : off);
    g.lineWidth = 2.5;
    g.lineCap = "round";
    for (let k = Math.max(i, 1); k < trail.length; k++) {
      const a = trail[k - 1], b = trail[k];
      if (b.t - a.t > 0.04 || Math.abs(b.midi - a.midi) > 1.5) continue;   // a new note: lift the pen
      g.strokeStyle = paint(b);
      g.beginPath();
      g.moveTo(x(a.t), y(a.midi));
      g.lineTo(x(b.t), y(b.midi));
      g.stroke();
    }
    let dotAt = -1;
    for (let k = i; k < trail.length; k++) {
      const p = trail[k];
      if (p.t - dotAt < 0.06) continue;   // a dot every 60 ms
      dotAt = p.t;
      g.fillStyle = paint(p);
      g.beginPath();
      g.arc(x(p.t), y(p.midi), 3, 0, 2 * Math.PI);
      g.fill();
    }

    // the newest pitch: a bigger dot at the now line, with its name and how far off
    const head = trail.at(-1);
    if (head && (still || now - head.t < 0.08)) {
      const hx = x(head.t), hy = y(head.midi);
      g.fillStyle = paint(head);
      g.globalAlpha = 0.25;
      g.beginPath(); g.arc(hx, hy, 9, 0, 2 * Math.PI); g.fill();
      g.globalAlpha = 1;
      g.beginPath(); g.arc(hx, hy, 5, 0, 2 * Math.PI); g.fill();
      const near = Math.round(head.midi), cents = Math.round((head.midi - near) * 100);
      const label = noteName(near) + (Math.abs(cents) >= 5 ? ` ${cents > 0 ? "+" : "−"}${Math.abs(cents)}¢` : "");
      g.font = "700 12px " + colour("--font-body");
      const lw = g.measureText(label).width + 10, ly = hy > 26 ? hy - 20 : hy + 20;   // a chip above the dot, off the line
      g.fillStyle = colour("--surface");
      g.beginPath(); g.roundRect(hx - lw / 2, ly - 9, lw, 18, 9); g.fill();
      g.fillStyle = ink;
      g.fillText(label, hx - lw / 2 + 5, ly + 0.5);
    }

    // the count-in: the beats left, big, popping on each tick
    if (count && count.left >= 1 && count.left <= count.of) {
      const pop = motion ? 1 + 0.35 * Math.max(0, 1 - count.phase * 4) : 1;
      g.save();
      g.translate(w / 2, h / 2);
      g.scale(pop, pop);
      g.font = `400 ${Math.round(h * 0.55)}px ${colour("--font-display")}`;
      g.textAlign = "center";
      g.fillStyle = ink;
      g.globalAlpha = motion ? 0.35 + 0.65 * (1 - count.phase) : 1;
      g.fillText(String(count.left), 0, 2);
      g.restore();
    }
  };
}
