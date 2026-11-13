/* Plays the score on the practice page, so you can hear what it should sound like.
   It walks the same cursor the page shows (repeats and endings included), so the
   sound and the cursor stay together. Piano: Salamander samples played with Tone.js,
   both loaded on the first Play. Stop leaves the cursor where the music stopped,
   and the next Play carries on from there. With a passage picked (passages.js),
   Play stays inside its bars and goes round again until Stop. */

const PIANO = ["A0", "C1", "Fs1", "C2", "Fs2", "C3", "Fs3", "C4", "Fs4", "C5", "Fs5", "C6", "Fs6", "C7", "Fs7", "C8"];

// One entry per cursor step from `start` to the end: when it sounds, in which bar, and which notes start there.
// OSMD timestamps and lengths are in whole notes; halfTone + 12 is the MIDI number.
// With `keep`, the walk stops at the first step keep(iterator) turns down, and events.end
// is when that step would sound: the end of the passage, rests included.
function scoreEvents(start, keep) {
  const it = start.clone(), events = [];
  let seconds = 0, last = it.CurrentEnrolledTimestamp.RealValue, bpm = it.CurrentBpm || 80;
  while (!it.EndReached) {
    const now = it.CurrentEnrolledTimestamp.RealValue;   // "enrolled" = with repeats played out
    seconds += (now - last) * 4 * 60 / bpm;
    last = now;
    if (keep && !keep(it)) { events.end = seconds; break; }
    bpm = it.CurrentBpm || bpm;
    const notes = [];
    for (const entry of it.CurrentVoiceEntries || []) {
      for (const note of entry.Notes) {
        if (note.isRest() || (note.NoteTie && note.NoteTie.StartNote !== note)) continue;   // a tie sounds once, for its whole length
        const length = entry.IsGrace ? 1 / 32 : (note.NoteTie ? note.NoteTie.Duration : note.Length).RealValue;
        notes.push({ midi: note.halfTone + 12, seconds: length * 4 * 60 / bpm, pitch: note.Pitch, staff: entry.ParentSourceStaffEntry.ParentStaff.idInMusicSheet });
      }
    }
    events.push({ seconds, measure: it.CurrentMeasureIndex, notes });
    it.moveToNext();
  }
  return events;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = Object.assign(document.createElement("script"), { src, onload: resolve, onerror: reject });
    document.head.append(script);
  });
}

// The page that actually scrolls: <main> on a desktop frame, the window on a phone.
function scoreScroller() {
  const main = document.querySelector("main");
  if (main && main.scrollHeight > main.clientHeight + 1) return main;
  return document.scrollingElement || document.documentElement;
}

// Keep the OSMD cursor in the open band under the pinned practice toolbar, so Listen and a
// take don't force the musician to chase the notes by hand. OSMD's own FollowCursor uses
// scrollIntoView and parks the cursor under that toolbar.
function keepCursorInView(osmd) {
  const el = osmd && osmd.cursor && osmd.cursor.cursorElement;
  if (!el || !el.getBoundingClientRect) return;
  const scroller = scoreScroller();
  const controls = document.getElementById("controls");
  const pad = (controls ? controls.getBoundingClientRect().height : 0) + 12;
  const box = scroller === document.scrollingElement || scroller === document.documentElement
    ? { top: 0, bottom: window.innerHeight, height: window.innerHeight }
    : (() => { const r = scroller.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, height: r.height }; })();
  const visibleTop = box.top + pad;
  const visibleBottom = box.bottom - 24;
  const rect = el.getBoundingClientRect();
  if (rect.top >= visibleTop && rect.bottom <= visibleBottom) return;
  const band = Math.max(80, visibleBottom - visibleTop);
  const target = visibleTop + band * 0.3;   // a little below the toolbar, not glued to it
  const delta = rect.top - target;
  if (Math.abs(delta) < 4) return;
  // instant while the music is moving: smooth scroll stacks up and lags behind the cursor
  if (scroller === document.scrollingElement || scroller === document.documentElement) {
    window.scrollBy(0, delta);
  } else {
    scroller.scrollTop += delta;
  }
}

// Beat length (seconds at the score's tempo × the slider) and beats per bar, from the cursor.
function beatOf(osmd, speed) {
  const it = osmd.cursor && osmd.cursor.Iterator;
  const bpm = (it && it.CurrentBpm) || (osmd.Sheet && osmd.Sheet.DefaultStartTempoInBpm) || 80;
  const time = it && it.CurrentMeasure && it.CurrentMeasure.ActiveTimeSignature;
  const perBar = (time && time.Numerator) || 4;
  const denom = (time && time.Denominator) || 4;
  return { beat: (4 / denom) * 60 / bpm / speed, perBar };
}

// A short click on Tone's clock, so it lands on the same transport time as the notes and cursor.
function toneTick(time, first, bus) {
  const ctx = Tone.getContext().rawContext;   // Tone's wrapped context: the node constructors refuse it, its create* methods don't
  const tone = ctx.createOscillator(), level = ctx.createGain();
  tone.frequency.value = first ? 1760 : 1320;
  level.gain.setValueAtTime(0, time);
  level.gain.linearRampToValueAtTime(first ? 0.5 : 0.35, time + 0.002);
  level.gain.exponentialRampToValueAtTime(0.001, time + 0.06);
  tone.connect(level).connect(bus);
  tone.start(time);
  tone.stop(time + 0.07);
}

// button toggles Listen / Stop (its .tool-label; the icon stays); tempo is a range input in percent of the score's tempo.
// passage() gives the picked bars as {first, last} measure indexes (0-based), or null for the
// whole piece; toStart() puts the cursor on the passage's first note.
// metro() is true when the metronome should click with Listen; setTicks(on) mutes mid-play.
function addPlayer(osmd, button, tempo, { passage = () => null, toStart, metro = () => false } = {}) {
  let piano, playing = false, followWas = true, clickBus = null;
  const word = button.querySelector(".tool-label") || button;
  const say = (text, state) => { word.textContent = text; button.dataset.state = state; };

  async function play() {
    playing = true;
    say("Loading…", "loading");
    if (!window.Tone) await loadScript("/Tone.js");
    await Tone.start();   // browsers only allow sound after a click
    if (!piano) {
      piano = new Tone.Sampler({
        urls: Object.fromEntries(PIANO.map(n => [n.replace("s", "#"), n + ".mp3"])),
        baseUrl: "/samples/piano/", release: 1,
      }).toDestination();
      await Tone.loaded();
    }
    if (!clickBus) {
      const ctx = Tone.getContext().rawContext;
      clickBus = ctx.createGain();
      clickBus.gain.value = metro() ? 1 : 0;
      clickBus.connect(ctx.destination);
    }
    if (!playing) return;   // Stop was pressed while loading
    schedule();
    say("Stop", "playing");
  }

  // Plays from the cursor to the end of the piece, or to the end of the passage and round again.
  // Notes, cursor steps and metronome ticks all share Tone's transport, so they stay locked.
  function schedule() {
    const bars = passage(), at = osmd.cursor.Iterator;
    if (bars && (at.EndReached || at.CurrentMeasureIndex < bars.first || at.CurrentMeasureIndex > bars.last)) toStart();
    else if (!bars && at.EndReached) osmd.cursor.reset();
    const inside = bars && (step => step.CurrentMeasureIndex >= bars.first && step.CurrentMeasureIndex <= bars.last);
    const speed = tempo.value / 100, transport = Tone.getTransport(), draw = Tone.getDraw();
    const events = scoreEvents(osmd.cursor.Iterator, inside);
    if (!events.length) return stop();
    followWas = osmd.FollowCursor;
    osmd.FollowCursor = false;   // our keepCursorInView handles the scroll, clear of the toolbar
    transport.cancel();
    transport.position = 0;
    clickBus.gain.setValueAtTime(metro() ? 1 : 0, Tone.now());
    events.forEach((event, i) => transport.schedule(time => {
      for (const note of event.notes) piano.triggerAttackRelease(Tone.Frequency(note.midi, "midi").toFrequency(), note.seconds / speed, time, 0.7);
      if (i > 0) draw.schedule(() => { osmd.cursor.next(); keepCursorInView(osmd); }, time);   // step 0 is where the cursor already is
    }, event.seconds / speed));
    keepCursorInView(osmd);
    const end = events.end ?? events.at(-1).seconds + Math.max(0, ...events.at(-1).notes.map(n => n.seconds));
    const { beat, perBar } = beatOf(osmd, speed);
    const until = end / speed;
    for (let t = 0, i = 0; t <= until + 1e-6; t += beat, i++) {
      const first = i % perBar === 0;
      transport.schedule(time => toneTick(time, first, clickBus), t);
    }
    if (bars) {
      const gap = 60 / (osmd.Sheet.DefaultStartTempoInBpm || 80);   // one beat of quiet, then back to the first bar
      transport.schedule(time => draw.schedule(() => {
        if (!playing) return;
        transport.stop();
        toStart();
        keepCursorInView(osmd);
        schedule();
      }, time), (end + gap) / speed);
    } else {
      transport.schedule(time => draw.schedule(stop, time), end / speed);
    }
    transport.start("+0.1");
  }

  function stop() {
    playing = false;
    osmd.FollowCursor = followWas;
    if (window.Tone) {
      Tone.getTransport().stop();
      Tone.getTransport().cancel();
      Tone.getDraw().cancel();
    }
    if (piano) piano.releaseAll();
    say("Listen", "stopped");
  }

  button.addEventListener("click", () => playing ? stop() : play());
  tempo.addEventListener("change", () => { if (playing) { stop(); play(); } });   // carry on from the cursor at the new speed
  addEventListener("pagehide", stop);
  return {
    stop,
    get playing() { return playing; },
    setTicks(on) { if (clickBus) clickBus.gain.setValueAtTime(on ? 1 : 0, Tone.now()); },
  };
}
