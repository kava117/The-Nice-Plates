# Plan: Fix-First Changes

How to make the five changes in `FIX_FIRST.md`, on branch `bug-fixes` (from `main` at `a98b67f`).

## Problems in FIX_FIRST.md to resolve first

Checking the spec against the code turned up five things that would go wrong if built exactly as written:

| # | Spec says | Problem | Plan does |
|---|---|---|---|
| A | Change 2a: photos allowed "only when `PHOTO_UPLOADS` is on" | That would turn off the Claude photo path on Render. On Render `PHOTO_UPLOADS=off` and photos go to Claude when `ANTHROPIC_API_KEY` is set (`ml/api.py:73`). | Photos are allowed when homr can run (`PHOTO_UPLOADS` not `off`) **or** Claude can (`off` + key). `/api/midi` has no Claude path, so it rejects photos when `off`. |
| B | Change 4: guest "Sign in with Google" goes to `/auth/google` | `/auth/google` is the OAuth *callback*. Visiting it directly fails and drops you on `/home`. | Link to `/login/google`, as `settings.html:27` already does. |
| C | Change 1: `generateValue: true` in `render.yaml` | Render reads `render.yaml` env vars only for Blueprint-created services. The README says vars are set in the dashboard. | Add it to `render.yaml` anyway. Also add a step: **set `SECRET_KEY` in the Render dashboard by hand** if the service wasn't made as a Blueprint. The startup check catches it either way. |
| D | Change 1: update `.env.example` | There is no root `.env.example`, only `ml/.env.example` (OpenAI key). `app.py` loads `.env` from the project root. | Create a root `.env.example` listing `SECRET_KEY`, the Google keys, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PHOTO_UPLOADS`. |
| E | Change 5: "button says Pause" and "offer Resume" | Today there is one button that toggles Start practice / Stop and save. There is no Pause in the UI. | Add a Pause/Resume button next to Stop and save (see 5a). |

Also, in change 4 the optional "make logout a POST" means `settings.html:27` (`<a href="/logout">`) must change too, or it will stop working.

---

## Setup (before change 1)

1. Move the limit tests into the repo as `tests/`:
   - `tests/conftest.py`: temp working folder, isolated DB, `login()` helper, a `Clock` that patches only `app.time`.
   - `tests/test_fix_first.py`: one test per "Done when" box.
   - Keep the full limit suite as `tests/test_limits.py`. Its known failures are marked `xfail`, so they flip to passing as fixes land.
2. Add `pytest` to a new `requirements-dev.txt`.
3. Run with `python -m pytest tests/` (Python 3.11, with `ml/requirements.txt` installed).

One commit per change on `bug-fixes`. Changes 1–4 are small enough to review in one PR. Change 5 can be a second PR if the review gets long.

---

## Change 1: Real SECRET_KEY

**Files:** `app.py`, `render.yaml`, `.env.example` (new), `README.md`

1. `app.py:23`:
   ```python
   secret = os.environ.get("SECRET_KEY")
   if not secret and os.environ.get("RENDER"):
       raise RuntimeError("SECRET_KEY is not set. Add it in the Render dashboard (Environment).")
   app.secret_key = secret or "dev-only"
   ```
2. `render.yaml`:
   - Add `- key: SECRET_KEY` / `generateValue: true`.
   - Change the header comment from "no secrets needed" to say a `SECRET_KEY` is generated.
3. Create `.env.example` at the root (see D above).
4. README Config table: mark `SECRET_KEY` as required on Render.
5. **Manual step:** check the Render dashboard. If `SECRET_KEY` is missing there, add a random value (`python -c "import secrets; print(secrets.token_hex(32))"`).

**Tests**
- Forged `"dev-only"` cookie is rejected when `SECRET_KEY` is set.
- Booting with `RENDER=1` and no key raises. Run this in a subprocess, because the check runs at import time.
- Booting with neither set works.

---

## Change 2: Upload guards

**Files:** `ml/api.py`, `fileConversion/pdfToMidi.py`, `app.py`, `music-app-home/templates/library.html`

### 2a. One shared check
Add to `ml/api.py`:
```python
SCORES = {".musicxml", ".xml", ".mxl"}
PHOTOS = {".pdf", ".png", ".jpg", ".jpeg"}

def upload_problem(filename, claude_ok):
    """None if this upload can be read here, else a message for the user."""
```
- Empty name → "Choose a file to upload."
- Suffix (lowercased) not in `SCORES | PHOTOS` → "Upload a PDF, PNG, JPG or MusicXML file."
- Photo, `PHOTO_UPLOADS=off`, and not `claude_ok` → the existing "needs about 1 GB" message.
- `add_piece` calls it with `claude_ok = bool(ANTHROPIC_API_KEY)`, and `midi()` with `claude_ok=False`.
- Run the check **before** saving the file.
- Build the error redirect with `url_for("library", error=msg)` so `#` and `&` in filenames are encoded. This fixes the cut-off message for free.
- `/api/midi` returns `jsonify(error=msg), 400`.

`pdfToMidi._to_musicxml`: add `if suffix not in IMAGES: raise ValueError(...)` before the image branch, so homr never sees an unknown type even if a route forgets the check.

### 2b. Size limit
- In `app.py`, set `app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024`. This also limits recordings, and 20 MB is more than 20 minutes of Opus audio.
- Add `@app.errorhandler(413)`:
  - `/api/pieces` → redirect to the library with "File too large (max 20 MB)".
  - Other routes → JSON 413.
- **Gotcha:** for a large upload the server may reply 413 before reading the body, and some browsers then show "connection reset" instead of following the redirect. So also add a check in `library.html`: if `file.size > 20 MB`, show the message and don't submit.

### 2c. Temp cleanup
- Change `save_upload()` into a context manager built on `tempfile.TemporaryDirectory()`.
- `add_piece`: do everything (homr, Claude, MIDI) in that one folder and read the bytes before it closes. Drop the second `mkdtemp()` at `ml/api.py:76`.
- `midi()`: `send_file(path)` streams **after** the handler returns, so the folder would already be gone. Read the MIDI into `BytesIO` first, then `send_file(BytesIO(...), download_name=..., mimetype="audio/midi")`.
- `transcribe` gets the same context manager.

**Tests**
- `.gif`, `.webp`, `.HEIC`, no extension, and an empty name on both routes: rejected, and a mocked `run_homr` is never called.
- `.png` with `PHOTO_UPLOADS=off`:
  - with no key → rejected on both routes;
  - with a key → `/api/pieces` goes to (mocked) Claude, and `/api/midi` is still rejected.
- 25 MB upload → error message, not 500.
- 5 uploads (good and failing) → no new folders in the temp directory.

---

## Change 3: Gunicorn threads

**Files:** `render.yaml`, `ml/api.py`, `README.md`

1. Start command: `gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT`.
2. **Addition to the spec:** a module-level `CONVERT = threading.Semaphore(1)` in `ml/api.py`, held around the homr/Claude conversion.
   - A second simultaneous upload waits instead of starting a second homr in the same process. This closes the out-of-memory risk the spec lists as a known limit.
   - Page views aren't affected.
3. Thread safety: every DB call opens its own connection, Flask's session is per request, and homr runs as a subprocess. No shared mutable state was found.
4. README "Running it on Render": new start command.

**Test:** re-run the load script's "upload while browsing" scenario with the new command. `/home` should load in under 1 s while homr runs. The script is `scratchpad/tests/loadtest.py`; copy it to `tests/load/`.

---

## Change 4: Log out link

**Files:** `music-app-home/templates/header.html`, optionally `app.py` and `settings.html`

1. Replace line 38 and the commented block below it with:
   ```jinja
   {% if current_user.is_authenticated %}
     <a class="btn btn-ghost press" href="{{ url_for('logout') }}">Log out</a>
   {% else %}
     <a class="btn btn-ghost press" href="{{ url_for('login_google') }}">Sign in with Google</a>
   {% endif %}
   ```
2. Optional POST logout:
   - Make `/logout` accept `methods=["POST"]`.
   - Use `<form method="post" action="/logout"><button class="btn btn-ghost press">Log out</button></form>` in **both** `header.html` and `settings.html`.
   - The cookie is `SameSite=Lax`, which already blocks cross-site POSTs, so no CSRF token is needed.

**Tests**
- Signed in: the top bar links to `/logout`, and following it shows "Sign in with Google" on `/settings`.
- Guest: no "Log out" anywhere in `/home`.

---

## Change 5: Trustworthy practice timer

**Files:** `database/database.py`, `app.py`, `music-app-home/templates/practice.html`

### 5a. Front end (`practice.html`)
- **Controls:** `[Start practice]` → while running `[Pause] [Stop and save]` → while paused `[Resume] [Stop and save]`.
- **One `render(state)` function** sets the button labels and clock from the server's `{running, elapsed}`. Every timer call goes through it.
- **On load:** `fetch("/api/practice/state").then(render)`. This replaces `let running = false`.
- **On hide:** listen for `pagehide`, and for `visibilitychange` when `document.hidden`. If running, call `navigator.sendBeacon("/api/timer/pause")`.
- **On visible again:** re-fetch the state and render. It will show Resume.

### 5b. Back end (`app.py`)
- `api_timer_start`: when no timer exists yet (no `timer_started_at` and no `timer_elapsed`), set `session["timer_id"] = secrets.token_hex(8)`. Resuming keeps the same id.
- `/api/timer/pause`: keep as is. `sendBeacon` sends a POST with no JSON, which the route already handles.
- `api_timer_stop`:
  - Apply the cap (5c).
  - Pass `timer_id` to `addSession`.
  - Pop `timer_id` with the other keys.
  - Add `timer_id` to `PRACTICE_KEYS`.

### 5c. The 4 h cap
- Add `MAX_SESSION = 4 * 3600` and `OVER_CAP = "drop"  # or "cap"`.
- `"cap"` saves `min(total, MAX_SESSION)`.
- `"drop"` saves nothing and returns `{"saved_session_id": null, "too_long": true}`. The page shows "That session ran too long to count".
- **Recommendation: `"drop"`.** With pause-on-hide in place, only a timer left running in a visible tab can reach 4 h, and a 4 h entry would still inflate the stats.
- **The team needs to decide this.** It's a one-word switch either way, so it doesn't block the rest of the work.

### 5d. Database (`database.py`)
- First entries in `MIGRATIONS`:
  ```python
  "ALTER TABLE Sessions ADD COLUMN timer_id TEXT",
  "CREATE UNIQUE INDEX IF NOT EXISTS Index_Sessions_Timer_Id ON Sessions(timer_id)",
  ```
  SQLite unique indexes allow many `NULL`s, so old rows are fine.
- `addSession(..., timer_id=None)`: on `sqlite3.IntegrityError`, return the id of the existing row where `timer_id = ? AND user_id = ?`, and insert no duplicate `Session_Pieces`.

### 5e. Check before relying on it
The beacon's pause only sticks if the browser stores the `Set-Cookie` from the beacon response.
- Test in Chrome (Playwright) and by hand in Safari.
- If Safari drops it, fall back to timer state in the DB: a `Timers` table keyed by user. That's out of scope today, so raise it with the team first.

**Tests**
- Start, reload: the page shows Pause and Stop, and the clock is not 0.
- Start, pagehide, wait 60 s (fake clock), come back: Resume shows, and the saved time excludes the 60 s.
- Start, 5 h, stop: follows `OVER_CAP`.
- Start, copy the cookie, stop, restore the cookie, stop → exactly one `Sessions` row, and both responses carry the same id.
- Home and Progress totals equal `SUM(time_spent)` from `Sessions` afterwards.
- Migration runs on an existing DB from `main` without losing rows.

---

## Before merging
- [ ] `python -m pytest tests/` passes, with the old limit-suite failures now `xfail` → pass where fixed.
- [ ] Browser check (Playwright) for the timer and the top bar.
- [ ] Deploy to Render after changes 1–3:
  - forged cookie rejected;
  - `.gif` rejected;
  - `/home` stays fast during a photo upload.
- [ ] README: Config (`SECRET_KEY` required on Render), Render start command, remove fixed items from the status table.
- [ ] Update `ISSUES.md`: tick off what's fixed.

## Decisions needed from the team
1. **Over-cap sessions:** `"drop"` (recommended) or `"cap"`.
2. **Logout as POST:** yes (recommended, small) or keep the link.
3. **Was the Render service created as a Blueprint?** This decides whether `render.yaml` env vars apply or `SECRET_KEY` goes in the dashboard.
