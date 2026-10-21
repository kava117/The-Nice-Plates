# The Nice Plates 

Flask web app for practicing music. You upload your sheet music, it gets turned into a score you can practice in the browser, and eventually it'll keep track of how much time you put in.

Right now three things work(ish): signing in with Google, uploading a piece to your library, and opening it on the practice page. Dashboard, Progress, and Settings are still mock-ups with fake data for now. There's a full rundown below.

## What works and what doesn't 

| Feature | Where it's at |
|---|---|
| Google sign-in / sign-out | Works if you've set the Google keys, otherwise you're in demo mode |
| Library | Works, shows your pieces |
| Uploading (PDF, PNG/JPG, MusicXML) | Works once the ML stuff is installed, saves MusicXML + MIDI |
| Practice page (score, cursor, zoom) | Works, shows a Bach *Air* demo if you haven't picked a piece |
| Practice timer + session logging | Back end's done, but nothing on the front end uses it yet. Also needs a real login |
| Sheet → MIDI download (`POST /api/midi`) | API only, no UI |
| Recording transcription (`POST /api/transcribe`) | API only, needs an OpenAI key, no UI |
| Dashboard tiles + stats | Mock-up |
| Progress charts | Mock-up |
| Settings | Mock-up, none of the controls do anything yet |
| Library density toggle | Buttons show up but don't do anything |
| Sections, Recordings | Tables exist in the database, that's it |

## How it all fits together

It's all one Flask app. The browser only talks to Flask, and Flask handles everything else: SQLite, the sheet music converter, Google sign-in, and OpenAI. There's no background worker, so if a conversion takes a while, the page just sits there loading until it's done.

- **Front end:** plain Jinja templates, no framework, no build step. Scores are drawn with [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/) (it's checked in as `opensheetmusicdisplay.min.js`). There's light/dark mode, keyboard support, and reduced-motion handling.
- **Accounts:** Google sign-in through Authlib, with Flask-Login keeping you logged in. No Google keys means everyone just shares one demo account (`Sample User`).
- **Practice state:** your current piece, section, and timer are kept in the session cookie until you stop the timer. That's when it gets saved to the `Sessions` table.
- **Database:** one SQLite file, `niceplates.db`, that gets created in whatever folder you run the app from.

### The sheet music pipeline

Whatever you upload gets picked up at the right step for its file type and comes out the other end as MusicXML + MIDI. The actual note reading (OMR) is done by [homr](https://github.com/liebharc/homr).

| You upload | What happens |
|---|---|
| `.pdf` | each page gets turned into an image at 300 DPI → homr reads each page → pages get merged → MIDI |
| `.png`, `.jpg`, `.jpeg` | homr reads the image → MIDI |
| `.musicxml`, `.xml`, `.mxl` | already good to go → MIDI |

Couple things to know:
- homr only picks up pitch and rhythm, so dynamics and articulations get lost.
- For multi-page PDFs, every page needs the same number of parts or the merge breaks.
- You can run the converter on its own too:
  `python fileConversion/pdfToMidi.py INPUT [-o OUT] [--keep-intermediates]`
- `fileConversion/notes.txt` has our notes comparing oemer, homr, and Audiveris.

## Where stuff lives

| Path | What's in it |
|---|---|
| `app.py` | The Flask app: pages, Google login, practice/timer API |
| `database.py` | SQLite schema, migrations, and queries |
| `ml/api.py` | The `/api` routes for pieces, MIDI conversion, and transcription |
| `ml/text.py` | Pulls tempo, key, and time signature out of transcribed speech |
| `fileConversion/pdfToMidi.py` | The sheet music → MusicXML/MIDI converter (also works as a CLI) |
| `music-app-home/` | Static files (`styles.css`, scripts, images) |
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

## Config

You don't need any secrets to get it running. Each one just turns on a feature. Put them in a `.env` file in the project root (it's git-ignored, so please don't commit it).

| Variable | What it's for | If you leave it out |
|---|---|---|
| `SECRET_KEY` | Signs the session cookie | Uses `"dev-only"`, which is fine locally but not anywhere else |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in | Demo mode, sign-in just drops you on `/dashboard` |
| `OPENAI_API_KEY` | `/api/transcribe` | That route won't work |
| `PORT` | Port on Render | Runs on 8001 locally |

If you're setting up Google sign-in, add `http://localhost:8001/auth/google` (and the Render URL + `/auth/google`) as redirect URIs on the OAuth client.

## Dependencies

There are three requirements files:
- `requirements.txt` is the web app, versions pinned (Flask 3.1.3, Flask-Login 0.6.3, Authlib 1.8.0, python-dotenv, requests).
- `ml/requirements.txt` has flask, openai, python-dotenv, gunicorn, and pulls in everything from `fileConversion/requirements.txt`. Not pinned.
- `fileConversion/requirements.txt` has pymupdf, music21, `homr[cpu]`, and opencv-python-headless. Also not pinned.

## Deploying

`render.yaml` sets up one free Render web service on Python 3.11.9. It installs the app + ML requirements and starts with:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300
```

Right now Render doesn't have any env vars set besides `PYTHON_VERSION`, so the live site is in demo mode and using the `dev-only` secret. Also, the database lives on Render's disk, which gets **wiped every time we deploy**.

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
| `POST /api/timer/stop` | yes | Saves the practice session (optional `{notes}`) |

## Database

| Table | What's in it | Does the app use it yet? |
|---|---|---|
| `Users` | Google id, name, email, profile pic | Yes |
| `Pieces` | Title, composer, bpm, and the MusicXML + MIDI files | Yes (uploads) |
| `Sessions` | Practice time (seconds), date, notes | Yes (when the timer stops) |
| `Session_Pieces` | Which pieces you practiced in each session | Yes (when the timer stops) |
| `Sections` | Measure ranges in a piece | Not yet |
| `Recordings` | Audio recordings of a piece | Not yet |

If you change the schema, add it to the `MIGRATIONS` list in `database.py` (it's empty right now). They run in order and get tracked with `PRAGMA user_version`.

## Known issues

**Priority**
- `SECRET_KEY` falls back to `"dev-only"` and Render doesn't set a real one, so once Google login is on, someone could fake a session cookie.
- `/api/transcribe` and `/api/midi` don't need a login and don't have an upload size limit, so anyone could burn through our OpenAI credits or bog down the server.

**Also Problems**
- Nothing on the front end calls the timer/practice API yet. Plus those routes need a real login while the live site is in demo mode, so practice time never actually gets saved.
- The "Log out" button goes to `/landing` instead of `/logout`, so you don't actually get logged out.
- The sidebar always says "Sample User" no matter who's signed in.
- Every page is public, and all guests share the demo account, so if one guest uploads something, every guest sees it.
- If an upload fails, you just get a plain 500 page with no explanation.
- OMR runs during the request on a free Render instance, so it might hit the 300 s timeout or run out of memory (haven't tested this yet).
- The ML and conversion requirements aren't pinned.
- The database on Render gets wiped every deploy.
- Temp upload folders never get cleaned up.
- Going to `/auth/google` without Google keys, or hitting "deny" on the Google screen, crashes instead of redirecting.
- `niceplates.db` is opened relative to wherever you run the app from, so starting it from a different folder quietly gives you a brand new empty database.
- No tests yet, and `ml/README.md` is out of date (it still says Google login isn't done).
