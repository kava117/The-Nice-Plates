# Plan: Hear the Piece, Then Check Your Take

2026-10-21. Two features for the practice page:

1. **Player:** press Play and hear what the piece should sound like, with the score cursor following along.
2. **Take check:** after recording a take, see which notes were right, wrong or missed, and where you rushed or dragged, measure by measure.

Builds on `bug-fixes` (after the five fix-first changes). Phase 1 can ship without Phase 2.

**Status:** Phase 1 is built on branch `playback`. Phase 2 waits until users have tried the player.

## What's there today

| Piece | Status |
|---|---|
| Upload pipeline | Saves MusicXML **and** MIDI for every piece (`ml/api.py` `add_piece`) |
| `GET /api/pieces/<id>/musicxml` | Serves the score; the practice page draws it with OpenSheetMusicDisplay (OSMD) **2.2.0**, vendored as `opensheetmusicdisplay.min.js` |
| Stored MIDI | In `Pieces.midi`, read by `database.getMidi()`, but **no route serves it** |
| Playback | None. The free OSMD build draws and moves a cursor, but has no audio |
| Record | Saves a webm (Chrome) or mp4 (Safari) take to `Recordings`, plays it back. Nothing analyses it |
| `/api/transcribe` | Whisper **speech** to text, for spoken tempo/key commands. Not music transcription, so not usable here |

## Decisions this plan makes

| Question | Choice | Why |
|---|---|---|
| Play from MusicXML or MIDI? | **MusicXML**, via the OSMD cursor | The cursor knows which measure and note it's on, so sound and score stay in sync for free. MIDI has no idea where a note is on the page. music21's MIDI export also doesn't expand repeats, and *Air* has repeats. Stored MIDI stays for export and a later fallback. |
| Use `osmd-audio-player`? | **No**, write a small player (~150 lines) | Last release 2022, depends on OSMD `^0.8.4`; we ship 2.2. It's the same idea (walk the cursor, schedule notes), so we write that loop ourselves against the API we have. |
| Sound engine | **Tone.js 15** `Sampler` with ~15 Salamander piano samples (CC-BY 3.0) | The sampler repitches between samples, so a few files cover the keyboard. Vendor `tone.min.js` and the samples into `music-app-home/` like OSMD, so there's no build step and no third-party host at runtime. About 1.5 MB, loaded on first Play. |
| Recording → notes | **Spotify basic-pitch in the browser** (`@spotify/basic-pitch` 1.0.1, Apache-2.0, TensorFlow.js) | Polyphonic, made for this. Running in the browser means no memory cost on the 512 MB Render box, and `decodeAudioData` reads webm and mp4 alike, so no ffmpeg on the server. Loaded only when someone asks for a check. |
| Where the comparison runs | **Server, in Python** | Testable with the pytest suite we already have. music21 (already installed) gives exact measure numbers from the MusicXML, and results can be stored for Progress. |

---

## Phase 1: Player

**Files:** `music-app-home/templates/practice.html`, new `music-app-home/player.js`, vendored `music-app-home/vendor/tone.min.js` + `music-app-home/samples/piano/*.mp3`

### 1a. Score → note events (`player.js`)
`scoreEvents(osmd)` walks a **clone** of the cursor's iterator and returns one entry per cursor step:
```js
{ step, measure, beat,            // beat = position in quarter notes from the start
  notes: [{ midi, quarters }],    // midi = halfTone + 12; quarters = Length.RealValue * 4
}
```
- Skip rests and tied-over notes (only the first note of a tie sounds, for the tied total).
- Tempo from the score's first metronome mark, else `Pieces.bpm`, else 80.
- Follow repeats the way the cursor does, so the sound and the cursor always agree. **Checked:** OSMD 2.2's iterator plays repeats and first/second endings out (*Air*: measures 1–12, 1–11, 13–37, 14–37; 433 steps), and `CurrentEnrolledTimestamp` counts time with them included.

### 1b. Playback
- Controls next to the zoom buttons: one `▶ Play` / `■ Stop` button and a tempo slider (40–200 %, label in bpm). Play starts from wherever the cursor is: move it with Prev/Next/Reset to choose the start.
- Schedule every event on `Tone.Transport`, and `Tone.Draw` to call `osmd.cursor.next()` at each step, so the cursor moves on the audio clock, not `setTimeout`.
- Tempo change while playing: restart from the cursor at the new speed (simpler than ramping, and it handles tempo marks in the score).
- Stop leaves the cursor where the music stopped, so the next Play carries on. Moving the cursor or zooming by hand, or leaving the page, stops playback.
- `Tone.start()` runs inside the Play click (browsers block audio until a click).
- The timer is separate: Play doesn't start practice time.

### 1c. Later (left out so users can try the basic player first)
- Count-in: one bar of clicks.
- Loop measures A–B (the `Sections` table already has `start_measure`/`end_measure`; this would give it its first real use).
- Mute left or right hand (part/staff index in the events).

**Tests**
- Python: none needed.
- Playwright (`tests/browser/player.py`): load *Air*, press Play, after 3 s the cursor has moved off the first note and no JS errors; Stop returns the cursor; tempo 50 % moves it half as far.
- By hand: it sounds right, including the repeat.

---

## Phase 2: Take check

**Files:** `practice.html`, new `music-app-home/takecheck.js`, vendored basic-pitch model + `tfjs`, `ml/api.py`, new `ml/compare.py`, `database/database.py`

### 2a. Spike first (half a day, before building anything else)
Answer these with real takes of *Air* (laptop mic and phone, Chrome and Safari):
1. How accurate is basic-pitch on our recordings: notes found vs played, octave errors, ghost notes from the sustain pedal?
2. How long does it take in the browser for a 1-minute take, and how big is the download (tfjs + model)?
3. Do the model files ship in the npm package, or do we fetch them from the basic-pitch repo?

If accuracy is poor on phone recordings, Phase 2 still ships, but the results show as "hints", not scores (see 2d).

### 2b. Browser: take → played notes (`takecheck.js`)
- After a take is saved, show **Check this take**.
- On click: lazy-load tfjs + basic-pitch, decode the Blob with `AudioContext.decodeAudioData`, resample to 22 050 Hz mono (`OfflineAudioContext`), run the model, and turn its output into notes with `outputToNotesPoly` → `noteFramesToTime`.
- Result: `[{ midi, start, end, velocity }]` in seconds. Show "Listening to your take…" while it runs.
- POST it as JSON to `/api/recordings/<id>/check`. The audio never leaves the database again.

### 2c. Server: expected notes + alignment (`ml/compare.py`)
```python
def expected_notes(xml_bytes):   # music21: expandRepeats(), then [(measure, beat_quarters, midi, quarters)]
def align(expected, played):     # -> list of (expected_note | None, played_note | None)
def report(pairs):               # -> {accuracy, tempo, measures: [{number, right, wrong, missed, extra, timing}]}
```
**Alignment** (the hard part):
- Group notes into **onset events**: expected notes at the same beat; played notes starting within 50 ms of each other (a chord).
- Align the two event sequences with dynamic programming (edit distance / DTW). Match cost = how different the pitch sets are, so a chord with one wrong note is a partial match. Insert = extra notes, delete = missed notes.
- **Subsequence alignment:** the take can start and stop anywhere in the piece (free start and end on the expected side). Nobody records the whole piece every time.
- **Tempo:** from the matched pairs, fit played seconds against expected beats; overall tempo is the slope. Measures whose local slope is >10 % off are "rushed" or "dragged".
- Pitch: exact match is right. One octave off counts as right but is flagged (basic-pitch makes octave errors); other pitches are wrong.

**Route** `POST /api/recordings/<int:recording_id>/check`:
- Owner check as in `play_recording`.
- Validate the JSON: list of ≤ 5 000 notes, numeric fields, `0 ≤ midi ≤ 127`.
- Load the piece's MusicXML, run `compare`, store, and return the report.

**Database:** `MIGRATIONS` entry `ALTER TABLE Recordings ADD COLUMN analysis TEXT` (the JSON report). Also store the upload's mimetype while touching this table (`ALTER TABLE Recordings ADD COLUMN mime TEXT`), which fixes the Safari playback bug in ISSUES.md.

### 2d. Showing the result
- Under the take: **"87 % of notes right · 92 bpm (score: 100) · 3 measures to look at"**.
- A list, worst first: "m. 12: missed E5", "m. 20–24: rushed about 12 %".
- Click a line → move the cursor to that measure, and offer **Play this bit** (Phase 1 player, from that measure).
- Optional: colour wrong/missed noteheads red on the score (OSMD `NoteheadColor`, then re-render).
- Word it as feedback ("to look at"), not a grade, because transcription isn't perfect.

**Tests**
- `tests/test_compare.py`, synthetic note lists against `AirOnG.musicxml`:
  - a perfect take → 100 %;
  - one note missing / wrong / extra → reported in the right measure;
  - the whole take at 80 % tempo → 100 % right, tempo reported 0.8×;
  - a take of measures 5–9 only → aligned there, nothing "missed" outside it;
  - an octave error → right, flagged;
  - junk input (empty, 10 000 notes, midi 300) → 400, not 500.
- End to end, no microphone: render *Air* with the Phase 1 player through `Tone.Offline` to an audio buffer, feed it to basic-pitch in Playwright, check ≥ 90 %. This also gives a basic-pitch accuracy baseline on clean audio.

---

## Risks

| Risk | What we do |
|---|---|
| basic-pitch is shaky on phone recordings | Spike 2a measures it; results are worded as hints; the octave tolerance absorbs the most common error |
| OSMD cursor and music21 disagree on repeats | Test both on *Air*; if they differ, the player follows music21's expansion too (send the expanded note list from the server) |
| tfjs + model are a big download | Only loaded on "Check this take"; cached by the browser afterwards |
| Old phones are slow to transcribe | Show progress; cap checks at 3 minutes of audio for now |
| Shared demo account | Checks on demo-user takes are visible to all guests, same as recordings today |

## Order and size

1. Phase 1 player, a small PR (1a, 1b). Ship it.
2. Spike 2a, then decide whether to continue.
3. `ml/compare.py` + tests, a PR testable without any audio.
4. Browser transcription + UI (2b, 2d), a PR.

## Decisions needed from the team
1. **Piano only?** The sampler and basic-pitch's pitch range assume piano. Other instruments would need other samples, and basic-pitch handles most pitched instruments.
2. **Keep generating MIDI on upload?** It isn't needed for either feature. Keep it for export (a "Download MIDI" link is one route away), or drop it to make uploads faster.
3. **Store take checks for Progress** (e.g. accuracy over time per piece)? The `analysis` column makes this possible later. This plan only shows the latest check.
