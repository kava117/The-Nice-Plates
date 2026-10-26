# The Nice Plates: Fix-First Changes

2026-10-21

## Overview

These five changes fix the problems from the 2026-10-21 test pass (`main` at `a98b67f`, see ISSUES.md) that a stranger on the live Render site could run into. Ship them before any new features.

| # | Change | ISSUES.md ref | Size |
| --- | --- | --- | --- |
| 1 | Real `SECRET_KEY` | #1 | One config line + a startup check |
| 2 | Upload guards: allow-list, size limit, temp cleanup | #3, Will cause trouble later | Small, touches 2 files |
| 3 | Gunicorn threads | #2 (short-term half) | One line |
| 4 | Log out link | #5 | Template only |
| 5 | Trustworthy practice timer | #4 | Biggest: front end + `api_timer_stop` |

Do them in this order. Changes 1–4 can each be their own small PR, and change 5 can be split into two (front end and back end). Out of scope here: the background conversion queue, moving the timer into the database, and making the demo account read-only.

## 1. Real SECRET_KEY

Production has to sign session cookies with a random secret, and the app has to refuse to boot on Render without one. Right now `app.py:23` falls back to `"dev-only"`, which means anyone can forge a cookie for any user id.

**Changes**

- `render.yaml`: add a `SECRET_KEY` env var with `generateValue: true`. Render then makes a random value once and keeps it across deploys. Remove the "no secrets needed" comment.
- `app.py`: keep the `"dev-only"` fallback for local runs only. If `SECRET_KEY` is unset **and** `RENDER` is set (Render sets it automatically), stop at startup with a clear error message instead of serving traffic.
- `.env.example` (or the README Config table): note that each dev should set their own random `SECRET_KEY` locally once Google login is on.

**Done when**

- [ ] The deployed site rejects a cookie signed with `"dev-only"`.
- [ ] Running with `RENDER=1` and no `SECRET_KEY` fails at boot with a readable message.
- [ ] Local `python app.py` with no `.env` still starts.

Note: changing the key logs everyone out once. That's fine at this stage.

## 2. Upload guards

Every upload route should accept only known file types, cap the file size, and clean up after itself. Right now a `.gif` gets past the `PHOTO_UPLOADS=off` guard and runs homr, which peaked at 963 MB on a 512 MB box.

### 2a. File-type allow-list

| Extension | Allowed? | Goes to |
| --- | --- | --- |
| `.musicxml`, `.xml`, `.mxl` | Always | MusicXML → MIDI |
| `.pdf`, `.png`, `.jpg`, `.jpeg` | Only when `PHOTO_UPLOADS` is on | OMR → MusicXML → MIDI |
| Anything else (`.gif`, `.webp`, `.heic`, `.txt`, no extension) | Never | Rejected |

- Compare extensions case-insensitively, so `SCORE.PDF` and `score.pdf` are treated the same.
- Use one shared check for **both** `POST /api/pieces` and `POST /api/midi`. Right now `/api/midi` ignores `PHOTO_UPLOADS` completely (`ml/api.py:29`).
- On rejection, `/api/pieces` redirects to the library with an error message, and `/api/midi` returns 400 with the message. The message should list the allowed types.
- `fileConversion/pdfToMidi.py`: `_to_musicxml` should raise an error on an unknown suffix instead of sending it to homr. That way there's still protection if a route forgets the check.
- Reject an empty filename (`not upload.filename`) the same way, instead of letting it crash in `save_upload`.

### 2b. Size limit

- Set Flask's `MAX_CONTENT_LENGTH` to 20 MB.
- Handle the 413 error. The library upload shows "File too large (max 20 MB)", and the API routes return 413 JSON.

### 2c. Temp-file cleanup

- `save_upload` and `add_piece` currently leave two `mkdtemp()` folders behind per upload. Switch to temp directories that get deleted automatically when the request finishes, including when conversion fails.

**Done when**

- [ ] Both routes reject a `.gif`, `.webp` or extensionless file, and homr never starts.
- [ ] With `PHOTO_UPLOADS=off`, both routes reject a `.png`.
- [ ] A 25 MB file gets the "too large" message, not a 500.
- [ ] After 5 uploads (good and failed), no new folders are left in the temp directory.

## 3. Gunicorn threads

One slow upload shouldn't freeze the site for everyone else. In the test, a 35 s homr run made another visitor's `/home` take 34.6 s, because Render runs a single sync worker.

**Change**

- The `render.yaml` start command becomes `gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT`.
- Keep **one** worker. A second worker would double homr's memory use and go over the 512 MB limit. Threads share that one process.
- SQLite already handled 40 simultaneous writes in the test, so the database doesn't need any changes.

**Done when**

- [ ] While a photo upload is converting, `/home` and `/library` still load in under 1 s.

Known limit: two photo uploads at the same time will still run two homr jobs in the same process, which can run out of memory. The real fix is the background queue, which is out of scope here. Until then, memory is protected by the allow-list in change 2 and by keeping `PHOTO_UPLOADS` off on Render.

## 4. Log out link

The top bar should show the right action for whoever's viewing, and "Log out" should actually log you out. Right now `header.html:38` links to `/index`, and guests see "Log out" too.

**Changes** (`header.html`)

| Who's viewing | Top bar shows | Goes to |
| --- | --- | --- |
| Signed-in user | Log out | `/logout` |
| Guest / demo user (`current_user.is_anonymous`) | Sign in with Google | `/auth/google` |

- The commented-out block under the link already sketches this out. Switch it to check `current_user`.
- Optional, and small: make `/logout` a POST (a tiny form styled to look like a link), so another site can't log people out with a plain link.

**Done when**

- [ ] Clicking Log out and then visiting `/library` shows the guest view.
- [ ] A guest never sees "Log out".

## 5. Trustworthy practice timer

The server's timer state should be the one source of truth, and every saved session should reflect real practice. Home and Progress now show real numbers, so bad timer data shows up right in the app.

| Problem today | Fix | Where |
| --- | --- | --- |
| After a reload the button says "Start practice" while the server is still counting | On page load, call `GET /api/practice/state` and set the button label and clock from it. Don't assume `running = false`. | `practice.html:77` |
| Leaving the page keeps the timer running | When the page is hidden, send a pause with `navigator.sendBeacon("/api/timer/pause")`. Listen for both `pagehide` and `visibilitychange` (hidden), because mobile browsers often skip `pagehide`. | `practice.html` |
| A timer left running overnight saves a 30-hour session | Cap sessions at **4 h** in `api_timer_stop`. See the open question below for what to save past the cap. | `app.py:174` |
| Two tabs or the back button save the same session twice | At start, store a random `timer_id` in the session. Save it on the `Sessions` row with a unique constraint. A second stop with the same id returns the session that's already saved instead of inserting a new one. | `app.py`, `database.py` |

**Database change**

- Add a nullable `timer_id` column to `Sessions` with a unique index. This is the first entry in `MIGRATIONS` in `database.py`. Existing rows keep `NULL`.

**Things to check while building**

- Timer state lives in the session cookie, so the pause only sticks if the browser saves the `Set-Cookie` from the beacon's response. Test this in Chrome and Safari. If it doesn't stick, the fallback is to move timer state into the database now instead of later.
- The pause on hide also fires when the user just switches tabs for a second. When they come back, the page should offer "Resume" rather than quietly restarting.

**Open question for the team**

- When a session goes past the 4 h cap, do we save exactly 4 h, or save nothing and show "That session ran too long to count"? Saving nothing keeps the stats more accurate, and saving the cap is friendlier to the user.

**Done when**

- [ ] Start, then reload: the button says Pause and the clock shows the right time.
- [ ] Start, go to Library, wait 1 min, come back: the minute away isn't counted.
- [ ] A timer started and left for 5 h saves according to the team's cap decision.
- [ ] Stopping the same timer from two tabs leaves exactly one `Sessions` row.
- [ ] After these tests, the Home and Progress totals match the `Sessions` table.

## Before merging

- [ ] All existing server tests still pass, plus new tests for each "Done when" item above.
- [ ] Do one live Render deploy after changes 1–3, since the test pass never ran against Render.
- [ ] Update the README: Config table (`SECRET_KEY` required on Render), Deploying (new start command), Known issues (remove what's fixed).

**Out of scope here:** the background conversion queue, timer state in the database (unless the beacon check in change 5 fails), a read-only demo account, the `.mxl` and uppercase-`.PDF` conversion fixes, and an app-wide 500 handler. These come next in ISSUES.md's suggested order.
