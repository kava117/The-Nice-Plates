/* Plays the score on the practice page, so you can hear what it should sound like.
   It walks the same cursor the page shows (repeats and endings included), so the
   sound and the cursor stay together. Piano: Salamander samples played with Tone.js,
   both loaded on the first Play. Stop leaves the cursor where the music stopped,
   and the next Play carries on from there. With a passage picked (passages.js),
   Play stays inside its bars and goes round again until Stop. */

const PIANO = ["A0", "C1", "Fs1", "C2", "Fs2", "C3", "Fs3", "C4", "Fs4", "C5", "Fs5", "C6", "Fs6", "C7", "Fs7", "C8"];

// One entry per cursor step from `start` to the end: when it sounds and which notes start there.
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
        notes.push({ midi: note.halfTone + 12, seconds: length * 4 * 60 / bpm });
      }
    }
    events.push({ seconds, notes });
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

// button toggles Play / Stop; tempo is a range input in percent of the score's tempo.
// passage() gives the picked bars as {first, last} measure indexes (0-based), or null for the
// whole piece; toStart() puts the cursor on the passage's first note.
function addPlayer(osmd, button, tempo, { passage = () => null, toStart } = {}) {
  let piano, playing = false;

  async function play() {
    playing = true;
    button.textContent = "Loading piano…";
    if (!window.Tone) await loadScript("/Tone.js");
    await Tone.start();   // browsers only allow sound after a click
    if (!piano) {
      piano = new Tone.Sampler({
        urls: Object.fromEntries(PIANO.map(n => [n.replace("s", "#"), n + ".mp3"])),
        baseUrl: "/samples/piano/", release: 1,
      }).toDestination();
      await Tone.loaded();
    }
    if (!playing) return;   // Stop was pressed while loading
    schedule();
    button.textContent = "■ Stop";
  }

  // Plays from the cursor to the end of the piece, or to the end of the passage and round again.
  function schedule() {
    const bars = passage(), at = osmd.cursor.Iterator;
    if (bars && (at.EndReached || at.CurrentMeasureIndex < bars.first || at.CurrentMeasureIndex > bars.last)) toStart();
    else if (!bars && at.EndReached) osmd.cursor.reset();
    const inside = bars && (step => step.CurrentMeasureIndex >= bars.first && step.CurrentMeasureIndex <= bars.last);
    const speed = tempo.value / 100, transport = Tone.getTransport(), draw = Tone.getDraw();
    const events = scoreEvents(osmd.cursor.Iterator, inside);
    if (!events.length) return stop();
    transport.cancel();
    transport.position = 0;
    events.forEach((event, i) => transport.schedule(time => {
      for (const note of event.notes) piano.triggerAttackRelease(Tone.Frequency(note.midi, "midi").toFrequency(), note.seconds / speed, time, 0.7);
      if (i > 0) draw.schedule(() => osmd.cursor.next(), time);   // step 0 is where the cursor already is
    }, event.seconds / speed));
    const end = events.end ?? events.at(-1).seconds + Math.max(0, ...events.at(-1).notes.map(n => n.seconds));
    if (bars) {
      const beat = 60 / (osmd.Sheet.DefaultStartTempoInBpm || 80);   // one beat of quiet, then back to the first bar
      transport.schedule(time => draw.schedule(() => {
        if (!playing) return;
        transport.stop();
        toStart();
        schedule();
      }, time), (end + beat) / speed);
    } else {
      transport.schedule(time => draw.schedule(stop, time), end / speed);
    }
    transport.start("+0.1");
  }

  function stop() {
    playing = false;
    if (window.Tone) {
      Tone.getTransport().stop();
      Tone.getTransport().cancel();
      Tone.getDraw().cancel();
    }
    if (piano) piano.releaseAll();
    button.textContent = "▶ Play";
  }

  button.addEventListener("click", () => playing ? stop() : play());
  tempo.addEventListener("change", () => { if (playing) { stop(); play(); } });   // carry on from the cursor at the new speed
  addEventListener("pagehide", stop);
  return { stop, get playing() { return playing; } };
}
