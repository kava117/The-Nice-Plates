# Plan: Practising a Passage

2026-10-24. Branch `practice-sessions`, built on `playback` (which sits on `bug-fixes`, PR #16), because all three change the practice page.

## Who it's for

A musician at the piano, laptop or tablet on the stand. Their hands are on the keys, so they touch the page between goes, not during one. Teachers set work in bar numbers: "bars 17 to 24, until it's clean."

## Decisions

| Question | Choice | Why |
|---|---|---|
| How to pick bars | Drag across them on the score. Or type `12-16` in the Bars box, or press `[` on the first bar and `]` on the last | The score is where the eyes already are. Typing matches a teacher's assignment. The keys keep hands near the instrument |
| A slider, or two thumbs for start and end | The two thumbs, but on the score: a handle at each end of the passage frame | People know two-thumb sliders. A slider under the score sits away from the notes, and on a 40-bar piece one bar is a few pixels of thumb; a handle on the bar itself snaps to whole bars |
| Showing the passage | A green frame; the other bars fade to about 30 % | Blur would hide the bar before the passage, and you need to read it to come in |
| A click on a bar | Moves the cursor there. A double click picks that one bar | Moving the cursor is the common case; picking needs a drag |
| Play with a passage | Plays it, rests one beat, and goes round until Stop | Hearing it a few times is how you learn how it goes |
| Next, Prev, Reset, Shift + arrows | Stay inside the passage; Next on its last note goes back to its first | The cursor shouldn't wander off the bars you're working on |
| Counting reps | After each go: **Yes** (`Y`) or **Not yet** (`N`). Dots show the last reps | One key per go. "Not yet" because the player is a beginner |
| Tempo | 3 clean in a row at one tempo offers 10 % faster; 2 misses in a row offer 10 % slower | The usual slow-practice ladder. The page offers; the musician decides |
| Saving | On the first rep, or with Save | Picking bars only to listen shouldn't fill the list |
| History | Saved passages sit above the score in bar order, each with its last 5 reps. "next up" marks the one with the fewest clean reps in its last 5; never practised comes first | Opening a piece shows where the work is |
| Coming back | The page reopens the passage you left on | |
| Timer | The first rep starts the practice timer if it's off | Forgetting Start was the main reason practice time went unsaved |

## Keys

| Key | Does |
|---|---|
| `Space` | Play or stop |
| `←` `→` | Previous or next note |
| `Shift` + `←` `→` | Previous or next bar |
| `Home` | Start of the passage, or of the piece |
| `[` then `]` | Mark a passage: first bar, then last |
| `Y` `N` | Clean, or not yet |
| `Esc` | Back to the whole piece |
| `+` `-` | Zoom |
| `?` | The list of keys |

Arrows on the tempo slider move the slider, not the cursor. A mouse click doesn't leave focus on a toolbar button, so the next `Space` plays instead of pressing that button again.

## Data

- `Sections` already existed. `start_measure` and `end_measure` count bars from 1 in score order, so they match the printed numbers unless the score opens with a pickup bar.
- `Section_Reps` is new: `section_id`, `clean`, `tempo` (percent of the score's), `date`. It's a new table, so `CREATE TABLE IF NOT EXISTS` in `init_db` covers old databases. No `MIGRATIONS` entry, so nothing to reorder against `bug-fixes` or `classes`.
- `Sections.times_practiced` counts reps too.

## Left out

- Naming a passage ("the run in bar 14").
- Tying a recorded take to a passage. The take check in `PLAYBACK_PLAN.md` would want it.
- A metronome and count-in.
- Touch: a sideways drag picks bars. Not tried on a real iPad yet.

## Tests

- `tests/test_passages.py`: the routes, other people's passages, bad input.
- `tests/browser/passages.py`: drag, reps, keys, the loop, phone width.
