# The Nice Plates 

Flask web app for practicing music. You upload your sheet music, it gets turned into a score you can practice in the browser, and it keeps track of how much time you put in.

Signing in with Google, uploading, the practice page (score, playback, passages, timer, recordings), Home and Progress all work. Settings is the one page that's still mostly a mock-up. There's a full rundown below.

## What works and what doesn't 

| Feature | Where it's at |
|---|---|
| Google sign-in / sign-out | Works if you've set the Google keys, otherwise everyone shares the demo account. A new account starts with Bach's *Air* in its library |
| Library | Works, shows your pieces. The density buttons switch between 6, 4 and 3 per row |
| Uploading (PDF, PNG/JPG, MusicXML) | Works, up to 20 MB, saves MusicXML + MIDI. Other file types are turned away, and a failed upload says so on the Library page. Photos need homr (1 GB of memory) or, on a small server, an Anthropic key |
| Practice page (score, cursor, zoom) | Works. Opens the piece you looked at last, or Bach's *Air* if you have nothing else, and says so if a picked piece is gone. Keys for everything common; **Keys** on the page lists them |
| Passages | Drag across bars on the score (or type `12-16`, or `[` then `]` at the cursor) to pick a passage, and drag the handles at either end to change it. Bars outside it fade, Play loops it, and Next/Reset stay inside it. After each time through, **Yes** / **Not yet** (`Y` / `N`) counts a rep: 3 clean in a row offers a faster tempo, 2 misses a slower one. Passages save on their first rep and sit above the score with their last reps; "next up" marks the one with the fewest clean reps lately |
| Playback | ▶ Play on the practice page plays the score on a piano sound, cursor following, from wherever the cursor is; tempo slider. Plays from the MusicXML (repeats included), not the stored MIDI |
| Practice timer + session logging | Start / Pause / Stop and save on the practice page writes a `Sessions` row; counting a rep starts it too. Leaving the page pauses it; each timer saves once, and runs over 4 h aren't saved |
| Recordings | Record a take on the practice page saves it to `Recordings` and plays it back; an empty take is turned away |
| Home tiles + stats | Your three most recently opened pieces, minutes on each, total time, day streak |
| Progress charts | This week's minutes per day, cumulative time, pieces practiced vs in the library. Time left on a running timer gets a Save button |
| Settings | Shows your name and email and signs you in or out; the practice settings and account buttons are mock-ups |
| Sheet → MIDI download (`POST /api/midi`) | API only, no UI |
| Recording transcription (`POST /api/transcribe`) | API only, needs an OpenAI key, no UI |

## How it all fits together

![](docs/system.svg)

It's all one Flask app. The browser only talks to Flask, and Flask handles everything else: the database, the sheet music converter, Google sign-in, Claude, and OpenAI. There's no background worker, so if a conversion takes a while, the upload page just sits there loading until it's done. Gunicorn runs 4 threads, so other visitors' pages keep loading meanwhile, and only one conversion runs at a time (a second upload waits its turn) so two homr runs can't share the 512 MB box.

- **Front end:** plain Jinja templates, no framework, no build step. Scores are drawn with [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/) (it's checked in as `opensheetmusicdisplay.min.js`) and played with [Tone.js](https://tonejs.github.io/). There's light/dark mode, keyboard support, and reduced-motion handling.
- **Accounts:** Google sign-in through Authlib, with Flask-Login keeping you logged in. Anyone not signed in uses one shared demo account (`Sample User`).
- **Practice state:** your current piece, passage, and timer are kept in the session cookie until you stop the timer. That's when it gets saved to the `Sessions` table.
- **Database:** one SQLite file, `niceplates.db`, made in whatever folder you run the app from. Set `DATABASE_URL` to a Postgres connection string and it uses Postgres instead, with the same tables. The startup log says which one it's using.

### The sheet music pipeline

Whatever you upload gets picked up at the right step for its file type and comes out the other end as MusicXML + MIDI. The actual note reading (OMR) is done by [homr](https://github.com/liebharc/homr), or by Claude on a server too small for homr.

| You upload | What happens |
|---|---|
| `.pdf` | each page gets turned into an image at 300 DPI → homr reads each page → pages get merged → MIDI |
| `.png`, `.jpg`, `.jpeg` | homr reads the image → MIDI |
| any of those, with `PHOTO_UPLOADS=off` | Claude reads the image instead of homr (first page only of a PDF) → MIDI. Without an `ANTHROPIC_API_KEY` the upload is turned away |
| `.musicxml`, `.xml`, `.mxl` | already good to go → MIDI |

Couple things to know:
- homr only picks up pitch and rhythm, so dynamics and articulations get lost.
- For multi-page PDFs, every page needs the same number of parts or the merge breaks.
- Each Claude read logs the model and tokens it used, so the cost shows in Render's log.
- You can run the converter on its own too:
  `python fileConversion/pdfToMidi.py INPUT [-o OUT] [--keep-intermediates]`
- `fileConversion/notes.txt` has our notes comparing oemer, homr, and Audiveris.

## Where stuff lives

| Path | What's in it |
|---|---|
| `app.py` | The Flask app: pages, Google login, practice/timer and passages API |
| `database/database.py` | Schema, migrations, and queries (SQLite, or Postgres with `DATABASE_URL`) |
| `ml/api.py` | The `/api` routes for pieces, uploads (including the Claude reader), recordings, MIDI conversion, and transcription |
| `ml/transcribe.py`, `ml/text.py` | Whisper transcription, and pulling tempo, key, and time signature out of what was said |
| `fileConversion/pdfToMidi.py` | The sheet music → MusicXML/MIDI converter (also works as a CLI); `homr_omr.py` and `easyParts.py` are its homr and MIDI steps |
| `music-app-home/` | Templates and static files (`styles.css`, scripts, images). `player.js` plays the score and `passages.js` runs passages; `Tone.js` (MIT) and `samples/piano/` (Salamander Grand, CC BY 3.0) are vendored for playback |
| `tests/` | pytest tests, plus browser and load checks (see [Tests](#tests)) |
| `docs/system.svg` | The diagram above |
| `render.yaml` | Render deploy config |

## Running it locally

You'll need Python **3.11 or 3.12** (homr won't work on other versions).

```bash
# just the web app
pip install -r requirements.txt

# add this if you want uploads and the ML routes to work
pip install -r ml/requirements.txt

python app.py
```

Then go to http://localhost:8001.

The app still starts up if you skip the ML install. The pages will load, but uploads, `/api/midi`, and `/api/transcribe` will throw a 500 until you install it.

### Tests

```bash
pip install -r requirements.txt -r ml/requirements.txt -r requirements-dev.txt
python -m pytest tests/
```

The tests use a throwaway database in a temp folder and ignore your `.env`. Set `DATABASE_URL` to run them against Postgres instead. `tests/test_limits.py` marks known bugs as expected failures (`@known(...)`, which is `xfail(strict=True)`). When you fix one, its test starts failing with `XPASS(strict)`. That's the cue to delete the marker.

`tests/browser/` drives the real app in Playwright (passages, playback, the timer, uploading your own piece), and `tests/load/` checks that pages stay fast while uploads convert. They aren't pytest tests; each file's docstring says how to start the server and run it. You'll need `pip install playwright && python -m playwright install --with-deps chromium` first.

## Config

You don't need any secrets to run it locally. Each one just turns on a feature. Copy `.env.example` to `.env` in the project root and fill in what you need (`.env` is git-ignored, so please don't commit it).

| Variable | What it's for | If you leave it out |
|---|---|---|
| `SECRET_KEY` | Signs the session cookie | Uses `"dev-only"` locally. On Render (where `RENDER` is set) the app refuses to start without it |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in | Everyone is the demo user; sign-in just drops you on `/home` |
| `DATABASE_URL` | A Postgres connection string | SQLite, in `niceplates.db` |
| `PHOTO_UPLOADS` | `off` sends photos and PDFs to Claude instead of homr | homr reads them (needs about 1 GB of memory) |
| `ANTHROPIC_API_KEY` | Claude reading photos when `PHOTO_UPLOADS=off`. Add `ANTHROPIC_WORKSPACE_ID` if the key was made outside a workspace | Photo and PDF uploads are turned away when `PHOTO_UPLOADS=off` |
| `CLAUDE_MODEL` | Which Claude model reads photos | `claude-haiku-5-5`. Leave it out rather than empty; an empty value breaks it |
| `OPENAI_API_KEY` | `/api/transcribe` | That route won't work |
| `PORT` | Port on Render | Runs on 8001 locally |

If you're setting up Google sign-in, add `http://localhost:8001/auth/google` (and the Render URL + `/auth/google`) as redirect URIs on the OAuth client.

## Dependencies

There are four requirements files:
- `requirements.txt` is the web app, versions pinned (Flask, Flask-Login, Authlib, python-dotenv, requests, psycopg for Postgres, and their dependencies).
- `ml/requirements.txt` has flask, openai, anthropic, python-dotenv, gunicorn, and pulls in everything from `fileConversion/requirements.txt`. Not pinned.
- `fileConversion/requirements.txt` has pymupdf, music21, `homr[cpu]`, and opencv-python-headless. Also not pinned.
- `requirements-dev.txt` is pytest, for the tests.

## Deploying on Render (free tier)

`render.yaml` sets up one free Render web service on Python 3.11.9. It installs the app + ML requirements and starts with:

```bash
gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT
```

Keep it at one worker: a second worker is a second process, which would double homr's memory.

The free box has 512 MB, which is not enough for homr, so `render.yaml` sets `PHOTO_UPLOADS=off` and photos go to Claude instead. Set the rest in the Render dashboard and press Manual Deploy after each push.

| Variable | Why |
|---|---|
| `SECRET_KEY` | **Required.** Signs login cookies; the app refuses to start on Render without it. A Blueprint generates it; otherwise make one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | **Needed for saved data.** A Postgres connection string, e.g. from a free Neon project. Without it the app uses SQLite on the instance disk, which Render wipes on every deploy and every spin-down, so accounts, pieces and sessions vanish (the startup log warns about this) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in; without them everyone is `Sample User` |
| `FORWARDED_ALLOW_IPS=*` | so the sign-in redirect is built as https behind Render's proxy |
| `ANTHROPIC_API_KEY` | needed for photo and PDF uploads; `ANTHROPIC_WORKSPACE_ID` too if the key was made outside a workspace |
| `CLAUDE_MODEL` | optional, default `claude-haiku-5-5` (under a cent a page; `claude-sonnet-5-5` reads dotted rhythms better at 20 times the price) |

## API

Every route works without signing in: if nobody's signed in, it uses the shared demo account. Routes that take an id give back a 404 if it isn't yours.

| Method + path | What it does |
|---|---|
| `GET /api/pieces` | Lists your pieces (`id, title, composer, bpm`) |
| `POST /api/pieces` | Takes a `file` (+ optional `title`, `composer`), converts it, saves it, sends you to `/practice?piece=ID`. If it can't, sends you back to `/library?error=...` |
| `GET /api/pieces/<id>/musicxml` | Gives back the MusicXML (and marks the piece as recently opened) |
| `POST /api/pieces/<id>/recordings` | Saves an audio `file` as a take of the piece |
| `GET /api/recordings/<id>` | Plays a take back |
| `POST /api/midi` | Converts an uploaded `file` and sends back a `.mid` (doesn't save anything) |
| `POST /api/transcribe` | Sends audio to OpenAI Whisper and pulls out tempo/key/time from what's said |
| `GET /api/practice/state` | Current piece, passage, and timer |
| `POST /api/practice/piece` | Sets the current piece (`{piece_id}`) |
| `POST /api/practice/section` | Sets the current passage (`{section_id}`) |
| `POST /api/timer/start` | Starts the timer (does nothing if it's already going) |
| `POST /api/timer/pause` | Pauses and keeps the time so far |
| `POST /api/timer/stop` | Saves the practice session (optional `{notes}`, text, up to 2,000 characters) |
| `GET /api/pieces/<id>/sections` | The piece's passages in bar order, each with its last 20 reps (`recent`, oldest first), `reps`, `clean`, `best_tempo`, `last_practiced` |
| `POST /api/pieces/<id>/sections` | Makes a passage (`{start, end}`, bar numbers from 1). The same bars again give back the same passage (200 instead of 201) |
| `DELETE /api/sections/<id>` | Removes a passage and its reps |
| `POST /api/sections/<id>/reps` | Counts one time through (`{clean: true/false, tempo: percent}`) and gives back the passage |
| `DELETE /api/sections/<id>/reps/last` | Takes back the newest rep (Undo) |

## Database

| Table | What's in it |
|---|---|
| `Users` | Google id, name, email, profile pic |
| `Pieces` | Title, composer, bpm, the MusicXML + MIDI files, when it was last opened |
| `Sessions` | Practice time (seconds), date, notes, and the timer it came from (so a timer saves only once) |
| `Session_Pieces` | Which pieces you practiced in each session |
| `Sections` | Passages: bar ranges in a piece (`start_measure`, `end_measure`, counted from 1 in score order) |
| `Section_Reps` | Each time through a passage: clean or not, tempo (percent of the score's), date |
| `Recordings` | Audio recordings of a piece |

If you change the schema, add it to the end of the `MIGRATIONS` list in `database/database.py`. They run in order and get tracked with `PRAGMA user_version` on SQLite, or a one-row `Schema_Version` table on Postgres. New tables can just go in `init_db` with `CREATE TABLE IF NOT EXISTS`.

## Known issues

**Priority**
- `/api/transcribe` and `/api/midi` don't need a login, so anyone could burn through our OpenAI credits or tie up the converter.
- Every page is public, and all guests share the demo account, so if one guest uploads something, every guest sees it.

**Also problems** (most have an `@known` test in `tests/test_limits.py`)
- `/api/transcribe` without an `OPENAI_API_KEY` gives a 500 instead of a clear error.
- Signing in with Google crashes if another account already has that email.
- `.mxl` uploads are stored zipped, so the practice page can't draw them.
- `SCORE.PDF` (uppercase) fails on the Claude path; `score.pdf` works.
- Recordings are always played back as `audio/webm`, whatever the browser recorded.
- `ml/api.py` doesn't run on its own anymore (`python ml/api.py`), since it has no LoginManager.
- `ml/text.py` misses "two two time" and spelled-out tempos like "one hundred twenty".
- OMR runs during the request, one upload at a time, so a queue of uploads can hit the 300 s timeout.
- The ML and conversion requirements aren't pinned.
- `niceplates.db` is opened relative to wherever you run the app from, so starting it from a different folder quietly gives you a brand new empty database.
- Timers over 4 hours are dropped; the team still has to pick between dropping and capping them (`OVER_CAP` in `app.py`).
