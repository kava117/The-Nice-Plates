# The Nice Plates 

Flask web app for practicing music. You upload your sheet music, it gets turned into a score you can practice in the browser, and eventually it'll keep track of how much time you put in.

Right now three things work(ish): signing in with Google, uploading a piece to your library, and opening it on the practice page. Home, Progress, and Settings are still mock-ups with fake data for now. There's a full rundown below.

## What works and what doesn't 

| Feature | Where it's at |
|---|---|
| Google sign-in / sign-out | Works if you've set the Google keys, otherwise you're in demo mode |
| Library | Works, shows your pieces |
| Uploading (PDF, PNG/JPG, MusicXML) | Works, up to 20 MB, saves MusicXML + MIDI. Other file types are turned away. Photos are read by homr (here, or on Azure through `HOMR_URL`), and by Claude when homr can't and there's an Anthropic key |
| Practice page (score, cursor, zoom) | Works, shows a Bach *Air* demo if you haven't picked a piece, and says so if a picked piece is gone. Keys for everything common; **Keys** on the page lists them |
| Passages | Drag across bars on the score (or type `12-16`, or `[` then `]` at the cursor) to pick a passage, and drag the handles at either end to change it. Bars outside it fade, Play loops it, and Next/Reset stay inside it. After each time through, **Yes** / **Not yet** (`Y` / `N`) counts a rep: 3 clean in a row offers a faster tempo, 2 misses a slower one. Passages save on their first rep and sit above the score with their last reps; "next up" marks the one with the fewest clean reps lately. See `PRACTICE_PLAN.md` |
| Playback | ▶ Play on the practice page plays the score on a piano sound, cursor following, from wherever the cursor is; tempo slider. Plays from the MusicXML (repeats included), not the stored MIDI |
| Coach | **Coach** on the practice page (or `C`) opens a panel beside the score. Ask about your practice and Claude answers from your own record: saved sessions, pieces, passages and their clean / not-yet reps, plus the piece and bars you have open. Each answer opens with one next step (which bars, what tempo, how many clean reps) in bold, readable from the music stand, then a line on why. Needs `ANTHROPIC_API_KEY`; without it the panel says the coach isn't switched on. The conversation stays in the tab (per piece) until **Start over** |
| Practice timer + session logging | Start / Pause / Stop and save on the practice page writes a `Sessions` row. Leaving the page pauses it; each timer saves once, and runs over 4 h aren't saved |
| Sheet → MIDI download (`POST /api/midi`) | API only, no UI |
| Recording transcription (`POST /api/transcribe`) | API only, needs an OpenAI key, no UI |
| Home tiles + stats | Your three most recently opened pieces, minutes on each, total time, day streak |
| Progress charts | This week's minutes per day, cumulative time, pieces practiced vs in the library |
| Settings | Shows your account and signs you out; the rest is mock-up |
| Library density toggle | Buttons show up but don't do anything |
| Recordings | Record a take on the practice page saves it to `Recordings` and plays it back; an empty take is turned away |

## How it all fits together

![](docs/system.svg)

It's all one Flask app. The browser only talks to Flask, and Flask handles everything else: SQLite, the sheet music converter, Google sign-in, and OpenAI. The one exception is homr on Render: it needs more memory than the free box has, so it runs on Azure (`homr_service/`) and Flask sends it each page. There's no background worker, so if a conversion takes a while, the upload page just sits there loading until it's done. Gunicorn runs 4 threads, so other visitors' pages keep loading meanwhile, and only one conversion runs at a time (a second upload waits its turn) so two homr runs can't share the 512 MB box.

- **Front end:** plain Jinja templates, no framework, no build step. Scores are drawn with [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/) (it's checked in as `opensheetmusicdisplay.min.js`). There's light/dark mode, keyboard support, and reduced-motion handling.
- **Accounts:** Google sign-in through Authlib, with Flask-Login keeping you logged in. No Google keys means everyone just shares one demo account (`Sample User`).
- **Practice state:** your current piece, section, and timer are kept in the session cookie until you stop the timer. That's when it gets saved to the `Sessions` table.
- **Database:** one SQLite file, `niceplates.db`, made in whatever folder you run the app from. Set `DATABASE_URL` to a Postgres connection string and it uses Postgres instead, with the same tables.

### The sheet music pipeline

Whatever you upload gets picked up at the right step for its file type and comes out the other end as MusicXML + MIDI. The actual note reading (OMR) is done by [homr](https://github.com/liebharc/homr).

| You upload | What happens |
|---|---|
| `.pdf` | each page gets turned into an image at 300 DPI → homr reads each page → pages get merged → MIDI |
| `.png`, `.jpg`, `.jpeg` | homr reads the image → MIDI |
| any of those, with `HOMR_URL` set | the same, but each page goes to homr on its own box (`homr_service/`, on Azure) |
| any of those, when homr fails and `ANTHROPIC_API_KEY` is set | Claude reads the image instead (first page of a PDF) → MIDI |
| any of those, with `PHOTO_UPLOADS=off` and no `HOMR_URL` | Claude reads it, and homr never runs |
| `.musicxml`, `.xml`, `.mxl` | already good to go → MIDI |

Couple things to know:
- homr only picks up pitch and rhythm, so dynamics and articulations get lost.
- For multi-page PDFs, every page needs the same number of parts or the merge breaks.
- You can run the converter on its own too:
  `python fileConversion/pdfToMidi.py INPUT [-o OUT] [--keep-intermediates]`
- `fileConversion/notes.txt` has our notes comparing oemer, homr, and Audiveris.

## Running it on Render (free tier)

The free box has 512 MB, which is not enough for homr, so homr runs on Azure (see "homr on Azure" below) and Claude is the backup. Set these in the Render dashboard (it does not read them from `render.yaml`) and press Manual Deploy after each push.

| Variable | Why |
|---|---|
| `SECRET_KEY` | **Required.** Signs login cookies; the app refuses to start on Render without it. A Blueprint generates it; otherwise make one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in; without them everyone is `Sample User` |
| `FORWARDED_ALLOW_IPS=*` | so the sign-in redirect is built as https behind Render's proxy |
| `PHOTO_UPLOADS=off` | homr never starts on the 512 MB box itself. Photos and PDFs go to `HOMR_URL`, or to Claude without it |
| `HOMR_URL`, `HOMR_TOKEN` | homr on Azure: the box's `https://` address and the token it was started with |
| `ANTHROPIC_API_KEY` | needed for the coach, and for Claude to read photos homr can't; `ANTHROPIC_WORKSPACE_ID` too if the key was made outside a workspace |
| `COACH_MODEL` | optional, default `claude-haiku-5-5`. Each question sends the practice record (a few thousand tokens), so Haiku keeps it to a fraction of a cent |
| `CLAUDE_MODEL` | optional, default `claude-haiku-5-5` (under a cent a page; `claude-sonnet-5-5` reads dotted rhythms better at 20 times the price) |
| `DATABASE_URL` | **Needed for saved data.** A Postgres connection string, e.g. from a free Neon project. Without it the app uses SQLite on the instance disk, which Render wipes on every deploy and every spin-down, so accounts, pieces and sessions vanish |

### homr on Azure

homr peaks at about 1.7 GB on a 300 DPI page, so it gets its own box and the site sends it one page at a time. `homr_service/` is that box: a small Flask app that takes a page image and sends back homr's MusicXML. On Azure Container Apps it sleeps when nobody is uploading. The first 180,000 vCPU-seconds a month are free, which at 2 vCPUs is about 25 hours awake; the registry Azure builds it in costs about $5 a month of credit.

One-time setup. Run it in Cloud Shell (the `>_` button at the top of portal.azure.com, Bash, nothing to install) with `homr_service/` uploaded next to you, or from the repo root after `brew install azure-cli` and `az login`:

```bash
az provider register --namespace Microsoft.ContainerRegistry --wait
TOKEN=$(openssl rand -hex 32)
az containerapp up --name nice-plates-homr --resource-group nice-plates --location eastus \
  --source homr_service --ingress external --target-port 8000 --env-vars HOMR_TOKEN=$TOKEN
az containerapp update --name nice-plates-homr --resource-group nice-plates \
  --cpu 2.0 --memory 4.0Gi --min-replicas 0 --max-replicas 1
echo "HOMR_URL=https://$(az containerapp show --name nice-plates-homr --resource-group nice-plates \
  --query properties.configuration.ingress.fqdn -o tsv)"
echo "HOMR_TOKEN=$TOKEN"
```

`up` builds the image in Azure (no Docker needed) and takes 5–10 minutes. Then in the Render dashboard set the two printed values, keep `PHOTO_UPLOADS=off`, and press Manual Deploy. Opening the `HOMR_URL` address should say `homr is up`. After changing `homr_service/`, run `az containerapp up --name nice-plates-homr --resource-group nice-plates --source homr_service`; without `--env-vars` it keeps the token, and the size settings stay too.

Couple things to know:
- The first upload after a quiet spell waits up to a minute while the box wakes up, then up to about a minute per page. For a demo, `--min-replicas 1` keeps it awake, but that bills by the hour, so set it back to 0 afterwards.
- If the box is unreachable, has a different token, or homr can't read the page, Claude reads the upload instead (when `ANTHROPIC_API_KEY` is set). The Render log says `homr read <file>` or `homr could not read <file> (why); Claude will` for every upload.
- The box's own log: `az containerapp logs show --name nice-plates-homr --resource-group nice-plates --follow`.
- If Azure refuses `eastus`, try another region; student subscriptions only allow some.
- `az group delete --name nice-plates` removes all of it and stops it using credit.

## Where stuff lives

| Path | What's in it |
|---|---|
| `app.py` | The Flask app: pages, Google login, practice/timer API |
| `coach.py` | The coach: what Claude is told about your practice, and the call itself |
| `database.py` | SQLite schema, migrations, and queries |
| `ml/api.py` | The `/api` routes for pieces, MIDI conversion, and transcription |
| `ml/text.py` | Pulls tempo, key, and time signature out of transcribed speech |
| `fileConversion/pdfToMidi.py` | The sheet music → MusicXML/MIDI converter (also works as a CLI) |
| `homr_service/` | homr as a small web service with its Dockerfile, for a box with the memory homr needs. The site uses it when `HOMR_URL` is set |
| `music-app-home/` | Static files (`styles.css`, scripts, images). `player.js` plays the score; `Tone.js` (MIT) and `samples/piano/` (Salamander Grand, CC BY 3.0) are vendored for it |
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

You can also run `ml/api.py` by itself on port 8002 with `python ml/api.py`.

### Tests

```bash
pip install -r requirements.txt -r ml/requirements.txt -r requirements-dev.txt
python -m pytest tests/
```

The tests use a throwaway database in a temp folder and ignore your `.env`. `tests/test_limits.py` marks known bugs as expected failures (`xfail`, with the `ISSUES.md` entry). When you fix one, its test starts failing with `XPASS(strict)`. That's the cue to delete the `@known(...)` marker.

## Config

You don't need any secrets to run it locally. Each one just turns on a feature. Copy `.env.example` to `.env` in the project root and fill in what you need (`.env` is git-ignored, so please don't commit it).

| Variable | What it's for | If you leave it out |
|---|---|---|
| `SECRET_KEY` | Signs the session cookie | Uses `"dev-only"` locally. On Render (where `RENDER` is set) the app refuses to start without it |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in | Demo mode, sign-in just drops you on `/home` |
| `OPENAI_API_KEY` | `/api/transcribe` | That route won't work |
| `PORT` | Port on Render | Runs on 8001 locally |

If you're setting up Google sign-in, add `http://localhost:8001/auth/google` (and the Render URL + `/auth/google`) as redirect URIs on the OAuth client.

## Dependencies

There are four requirements files:
- `requirements.txt` is the web app, versions pinned (Flask 3.1.3, Flask-Login 0.6.3, Authlib 1.8.0, python-dotenv, requests).
- `ml/requirements.txt` has flask, openai, python-dotenv, gunicorn, and pulls in everything from `fileConversion/requirements.txt`. Not pinned.
- `fileConversion/requirements.txt` has pymupdf, music21, `homr[cpu]`, opencv-python-headless, and requests. Also not pinned.
- `homr_service/requirements.txt` is the homr box on Azure: homr 0.7.0, Flask, and gunicorn, pinned.

## Deploying

`render.yaml` sets up one free Render web service on Python 3.11.9. It installs the app + ML requirements and starts with:

```bash
gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT
```

Keep it at one worker: a second worker is a second process, which would double homr's memory.

Without Google keys the live site is in demo mode. It needs a `SECRET_KEY` (see above) or it won't start. Also, the database lives on Render's disk, which gets **wiped every time we deploy**.

## API

The piece and ML routes (`ml/api.py`) use the demo account if nobody's signed in. The practice and timer routes (`app.py`) need a real login, and you'll get `401 {"error": "login required"}` without one.

| Method + path | Login? | What it does |
|---|---|---|
| `GET /api/pieces` | demo is fine | Lists your pieces (`id, title, composer, bpm`) |
| `POST /api/pieces` | demo is fine | Takes a `file` (+ optional `title`, `composer`), converts it, saves it, sends you to `/practice?piece=ID` |
| `GET /api/pieces/<id>/musicxml` | demo is fine, has to be your piece | Gives back the MusicXML, or a 404 if it's not yours |
| `POST /api/midi` | no | Converts an uploaded `file` and sends back a `.mid` (doesn't save anything) |
| `POST /api/transcribe` | no | Sends audio to OpenAI Whisper and pulls out tempo/key/time from what's said |
| `GET /api/practice/state` | yes | Current piece, section, and timer |
| `POST /api/practice/piece` | yes | Sets the current piece (`{piece_id}`) |
| `POST /api/practice/section` | yes | Sets the current section (`{section_id}`) |
| `POST /api/timer/start` | yes | Starts the timer (does nothing if it's already going) |
| `POST /api/timer/pause` | yes | Pauses and saves the time so far |
| `POST /api/timer/stop` | yes | Saves the practice session (optional `{notes}`, text, up to 2,000 characters) |
| `GET /api/pieces/<id>/sections` | demo is fine, has to be your piece | The piece's passages in bar order, each with its last 20 reps (`recent`, oldest first), `reps`, `clean`, `best_tempo`, `last_practiced` |
| `POST /api/pieces/<id>/sections` | demo is fine, has to be your piece | Makes a passage (`{start, end}`, bar numbers from 1). The same bars again give back the same passage (200 instead of 201) |
| `DELETE /api/sections/<id>` | demo is fine, has to be yours | Removes a passage and its reps |
| `POST /api/sections/<id>/reps` | demo is fine, has to be yours | Counts one time through (`{clean: true/false, tempo: percent}`) and gives back the passage |
| `DELETE /api/sections/<id>/reps/last` | demo is fine, has to be yours | Takes back the newest rep (Undo) |
| `POST /api/coach` | demo is fine | Answers a question about your practice (`{message, history, piece_id, passage: {start, end}}`; `history` is the earlier questions and answers in turn). Gives back `{reply}`. 503 with no Anthropic key, 429 past 40 questions an hour |

## Database

| Table | What's in it | Does the app use it yet? |
|---|---|---|
| `Users` | Google id, name, email, profile pic | Yes |
| `Pieces` | Title, composer, bpm, and the MusicXML + MIDI files | Yes (uploads) |
| `Sessions` | Practice time (seconds), date, notes | Yes (when the timer stops) |
| `Session_Pieces` | Which pieces you practiced in each session | Yes (when the timer stops) |
| `Sections` | Passages: bar ranges in a piece (`start_measure`, `end_measure`, counted from 1 in score order) | Yes (passages on the practice page) |
| `Section_Reps` | Each time through a passage: clean or not, tempo (percent of the score's), date | Yes (Yes / Not yet on the practice page) |
| `Recordings` | Audio recordings of a piece | Yes (Record a take) |

If you change the schema, add it to the `MIGRATIONS` list in `database.py` (it's empty right now). They run in order and get tracked with `PRAGMA user_version`.

## Known issues

**Priority**
- `/api/transcribe` and `/api/midi` don't need a login, so anyone could burn through our OpenAI credits.

**Also Problems**
- Nothing on the front end calls the timer/practice API yet. Plus those routes need a real login while the live site is in demo mode, so practice time never actually gets saved.
- The sidebar always says "Sample User" no matter who's signed in.
- Every page is public, and all guests share the demo account, so if one guest uploads something, every guest sees it.
- If an upload fails, you just get a plain 500 page with no explanation.
- OMR runs during the request, one upload at a time, so a queue of uploads can hit the 300 s timeout (haven't tested this on Render yet).
- The ML and conversion requirements aren't pinned.
- The database on Render gets wiped every deploy.
- Going to `/auth/google` without Google keys, or hitting "deny" on the Google screen, crashes instead of redirecting.
- `niceplates.db` is opened relative to wherever you run the app from, so starting it from a different folder quietly gives you a brand new empty database.
- `ml/README.md` is out of date (it still says Google login isn't done).
