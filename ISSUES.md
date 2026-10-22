# Known issues and recommended fixes

Results of a full test pass on `main` at `a98b67f` (2026-10-21). It covered:
- 78 server tests;
- a load test under Render's start command (`gunicorn app:app --timeout 300`, Python 3.11, one sync worker);
- a real homr run on one rendered page of Bach's *Air*;
- 27 checks in headless Chrome.

27 problems confirmed. Fix the **Fix first** section before building new features on top.

**Not tested:** real Google sign-in, real Claude photo reading (the API was faked; there was no key), real OpenAI transcription, and a live Render deploy.

---

## Fix first

### 1. Anyone can sign in as any user
**Fixed** on `bug-fixes` (335564e). Still to do: check `SECRET_KEY` is set in the Render dashboard.

`app.py:23` falls back to `SECRET_KEY = "dev-only"`, and `render.yaml` sets no `SECRET_KEY`. Its comment even says "no secrets needed". With the public key, anyone can sign their own session cookie. The test made a cookie for another user's id and read their library.

**Fix**
- In `render.yaml`, add `- key: SECRET_KEY` with `generateValue: true` so Render creates a random key.
- In `app.py`, refuse to start without a real key when deployed. For example, raise if `SECRET_KEY` is unset and `RENDER` is set.

### 2. One photo upload freezes the whole site
**Short-term half fixed** on `bug-fixes` (40b0515): 4 threads, and one conversion at a time. The background queue is still to do.

Render runs a single sync gunicorn worker. Reading one page with homr took 35 s, and during that time another visitor's `/home` took 34.6 s. The Claude path blocks the same way. Any request over 300 s is killed and the user gets an error page.

**Fix**
- Short term: add threads to the start command, e.g. `gunicorn app:app --workers 1 --threads 4 --timeout 300`, so page views keep being served during an upload. SQLite handled 40 simultaneous writes without errors.
- Longer term: run the conversion in the background. Save the piece as "processing", return straight away, and have the practice page poll until it's ready.

### 3. Render's `PHOTO_UPLOADS=off` guard can be bypassed, which crashes the server
**Fixed** on `bug-fixes` (3fbe9ad).

`ml/api.py:72` only checks for `.pdf/.png/.jpg/.jpeg`. Anything else falls through to `_to_musicxml`, and its `else` branch sends unknown file types to homr. That includes `.gif`, `.webp`, iPhone `.HEIC`, `.txt` and files with no extension. homr peaked at **963 MB** on one page, and the free plan has 512 MB. This was confirmed on a real server: a `.gif` ran homr with the guard on. `/api/midi` (`ml/api.py:29`) ignores the guard entirely.

**Fix**
- Accept an explicit list of types and reject everything else with a message: `.pdf .png .jpg .jpeg .musicxml .xml .mxl`, plus `.heic`/`.webp` if you add conversion for them.
- In `fileConversion/pdfToMidi.py`, make `_to_musicxml` raise on an unknown suffix instead of treating it as an image.
- Apply the same `PHOTO_UPLOADS` check to `/api/midi`, or remove that route if nothing uses it.

### 4. Practice time can't be trusted
**Fixed** on `bug-fixes` (3816acb). Over-4 h sessions are dropped (`OVER_CAP` in `app.py`) until the team decides.

- Leaving the practice page doesn't pause the timer. It keeps counting in the cookie.
- After a page reload the button says "Start practice" while the server is still counting. `practice.html:77` starts with `running = false` and never asks the server.
- A timer left running overnight saves as a 30-hour session.
- Replaying an old cookie saves the same session twice. This happens with two tabs or the back button.

**Fix**
- On page load, call `/api/practice/state` and set the button and clock from it.
- On `pagehide`, call `navigator.sendBeacon("/api/timer/pause")`.
- In `api_timer_stop` (`app.py:174`), cap a session, e.g. at 4 h. Ignore time after a long gap: if the elapsed time is over the cap, save the cap or nothing.
- Prevent double saves: store a random `timer_id` in the session at start, and save it with the row under a unique constraint, or keep the timer in the database instead of the cookie.

### 5. "Log out" in the top bar doesn't log out
**Fixed** on `bug-fixes` (289d0b5). Logout is still a link, not a POST.

`header.html:38` links to `/index`, so the user stays signed in. Guests also see "Log out".

**Fix**
- Point the link to `/logout`.
- Show "Sign in with Google" when `current_user.is_anonymous`. The commented-out block below the link already sketches this; switch it to use `current_user`.
- Optional: make logout a `POST` so other sites can't log users out with a link.

---

## Broken features

| Issue | Where | Recommended fix |
|---|---|---|
| `.mxl` uploads are saved, but the practice page can't draw them ("Corrupted zip") and falls back to the demo. | `ml/api.py:90` serves the zip as `application/xml`. | On upload, unzip `.mxl` to plain MusicXML before saving, e.g. `converter.parse(src).write("musicxml", ...)` or read `META-INF/container.xml`. |
| `SCORE.PDF` (capital letters) fails on the Claude path. | `ml/api.py:51`: `with_suffix(".pdf")` points to a file that doesn't exist. | Keep the original path in a variable: `pdf = src; src = src.with_suffix(".png"); ... fitz.open(pdf)`. Also switch `import fitz` to `import pymupdf`. |
| A missing or deleted piece quietly shows the Bach demo. | `practice.html:38` | Fall back only when no `?piece=` was given. Otherwise show "This piece couldn't be found" with a link to the library. |
| Safari recordings won't play back. | `ml/api.py:102` always sends `audio/webm`; Safari records `audio/mp4`. | Store the upload's `mimetype` in a new `Recordings.mime` column and send it back on playback. |
| `python ml/api.py` crashes on the first request (`no attribute 'login_manager'`). | `ml/api.py` `__main__` | Add `LoginManager(app)` in the `__main__` block, or drop the standalone mode from the README. |
| Settings Save, "Log out of all devices" and "Delete account" do nothing. | `settings.html` | Add a `POST /settings` that updates `Users.name`, plus a delete-account route. Or hide these controls until they work. |
| Sections can't be created, so `/api/practice/section` always returns 404. | `database.py` | Add `addSection` and a UI to make one, or remove the endpoint for now. |

---

## Crashes (500 errors) that should be clear messages

| Request | Cause | Fix |
|---|---|---|
| ~~Upload with an empty filename~~ **Fixed** | `save_upload` (`ml/api.py:21`) tries to save to a directory | Reject `not upload.filename` with a 400 or a library error message. |
| ~~`/api/midi` with an unsupported type~~ **Fixed** | `convert` raises `ValueError` | Catch it and return a 400 with the message. |
| `/api/transcribe` with no `OPENAI_API_KEY` | `OpenAIError` | Check the key first and return 503 "transcription not configured". |
| `piece_id` = 10³⁰ | SQLite `OverflowError` | In `read_id`, reject ids outside 1…2⁶³−1. |
| Timer notes sent as an object | SQLite can't store a dict | Accept a string only and cap its length (e.g. 2,000 characters). |
| Google sign-in where the email already belongs to another account | `UNIQUE` on `Users.email` (`database.py:113`) | Catch `IntegrityError`, then link the accounts or show "an account with this email already exists". |

Also add an app-wide `@app.errorhandler(500)` that shows a friendly page instead of Flask's default.

---

## Will cause trouble later

- **Fixed:** ~~**No upload size limit.**~~ One big file can fill memory or disk on a 512 MB box. Set `app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024` and handle `413`.
- **Fixed:** ~~**Temp files are never deleted.**~~ Each upload leaves 2 folders from `tempfile.mkdtemp()`. Use `tempfile.TemporaryDirectory()` as a context manager in `save_upload` and `add_piece`.
- **Empty recordings are saved.** Reject zero-byte files with a 400.
- **Fixed:** ~~**A `#` in a filename cuts the error message short.**~~ For example `etude #3.xml` becomes "Could not read etude". Build the redirect with `url_for("library", error=msg)` so the message is URL-encoded.
- **The demo account is shared.** Logged-out visitors can read and change the demo user's pieces, sessions and recordings, and recording ids are sequential. Once Google sign-in is live, consider making the demo read-only.
- **`ml/text.py` misses phrases:**
  - "two two time" and "cut time" aren't recognised; add `two` to the denominator group.
  - Spelled-out tempos ("one hundred twenty") aren't recognised.
- **Dependencies:**
  - `homr[cpu]` isn't an extra in homr 0.7.0, so pip ignores it. Use plain `homr`.
  - Pin versions in `ml/requirements.txt`. Only the root `requirements.txt` is pinned.
- **README is out of date.** It says the library density toggle does nothing; it works now.

---

## Measurements

| What | Result |
|---|---|
| Boot | 0.3 s, 78 MB idle |
| Read load, 10 users | 229 req/s, p95 66 ms, 0 errors |
| Read load, 50 users | 237 req/s, p95 287 ms, 0 errors |
| 40 timers stopped at the same moment | 40/40 saved, no lock errors |
| homr, one page, 2 CPUs | 35.6 s, peak **963 MB** |
| homr accuracy on a clean, computer-engraved page | left hand 100%, right hand (two voices) ~76% by notes; expect worse from phone photos |
| Phone width (375 px) | every page fits, no sideways scrolling |

## What works
- **Pages:** every page loads with no console errors.
- **Uploads:** MusicXML upload, conversion to MIDI, and the practice page drawing it.
- **Practice page:** cursor and zoom work.
- **Timer and recording:** the timer saves a session, and recording saves a take that plays back in Chrome.
- **Home and Progress:** both show real numbers.
- **Sign-in fallback:** Google sign-in falls back to the demo user without keys or on a bad callback.
- **Look and layout:** the library density toggle, dark mode, and the phone layout all work.

## Suggested order
1. `SECRET_KEY` (#1). It's a one-line Render change.
2. File-type allow-list and `/api/midi` guard (#3), upload size limit, temp-file cleanup.
3. `--threads 4` (#2).
4. Timer fixes (#4) and the Log out link (#5).
5. `.mxl` and uppercase-`.PDF` fixes, 500 handlers.
6. Turn the test suite into `tests/` in the repo and run it before each merge.
