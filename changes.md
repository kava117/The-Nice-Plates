# Changes: pull of 2026-10-21

`main` fast-forwarded from `9ff3bea` to `a98b67f` by merging PR #14 (`MusicRender`, by Madhav Khanal).
The PR is titled "Free Render box: photos via Claude, sign-in that never breaks the app, account in the sidebar".

14 files changed, 271 insertions, 105 deletions.

## Pages now use real data

- **Home** (`/home`): shows the three most recently opened pieces, seconds practiced per piece, total practice time, and a day streak (days in a row with a saved session, counted in UTC).
- **Progress** (`/progress`): shows minutes for each day of the current week (Monday to Sunday), a running total over all sessions, and how many pieces have been practiced out of how many are in the library.
- **Practice**: the timer saves a Session when it stops. The new Record button saves audio to the `Recordings` table.
- Opening a piece's MusicXML marks the piece as viewed. The library is now sorted by most recently viewed.

## Sign-in

- A failed, cancelled, or misconfigured Google sign-in now opens the app as the shared demo user instead of showing an error. Missing Google keys or an unreachable Google also send the user in as the demo user.
- The sidebar and Settings show the signed-in account (`me` is available in every template). Settings has a sign-in / sign-out button.
- **Practice and timer API routes no longer need a login.** `@login_required` was removed from `/api/practice/*` and `/api/timer/*`. Without a login these routes act as the demo user.

## Photo and PDF uploads

- With `ANTHROPIC_API_KEY` set and `PHOTO_UPLOADS=off`, a Claude vision model turns photos and PDFs (first page) into MusicXML instead of homr. The default model is `claude-sonnet-5-5`, which reads dotted rhythms that Haiku misses. `CLAUDE_MODEL` overrides it.
- `ANTHROPIC_WORKSPACE_ID` is optional and is sent as a header when set. Both values are trimmed of whitespace, because pasted keys often end in a newline.
- With `PHOTO_UPLOADS=off` and no API key, photo uploads are declined with a clear message instead of crashing the server.
- If an upload can't be read, the library page shows a plain message and the server log records the full exception.

## Free hosting (Render)

- `render.yaml` sets `PHOTO_UPLOADS=off`: homr needs about 1 GB of RAM and the free plan has 512 MB.
- If the demo user has no pieces at startup, the app adds Bach's "Air" (`static/AirOnG.musicxml`). Render's free plan wipes the disk on restart, so this keeps one piece available to try.

## Database (`database/database.py`)

New functions:
- `touchPiece(piece_id)`: sets `last_viewed` to now.
- `getPieceSeconds(user_id)`: seconds practiced per piece, from linked sessions.
- `addRecording(piece_id, audio)` and `getRecording(user_id, recording_id)`.

Changed: `getPieces` now orders by `COALESCE(last_viewed, date_created) DESC`.

## New API endpoints (`ml/api.py`)

- `POST /pieces/<id>/recordings`: uploads a recording (form field `file`).
- `GET /recordings/<id>`: plays a recording back as `audio/webm`.

## Docs and dependencies

- README: explains how the parts fit together and what Render needs.
- New diagram: `docs/system.svg`.
- `ml/README.md` updated.
- `ml/requirements.txt`: added `anthropic`. Run `pip install -r ml/requirements.txt`.

## Commits

| Commit | Date | Message |
|---|---|---|
| `a98b67f` | 2026-10-21 | Merge pull request #14 from kava117/MusicRender |
| `f593e3e` | 2026-10-19 | Every page reads and writes the database |
| `c5e344f` | 2026-10-18 | Trim pasted whitespace off the Anthropic key and workspace id |
| `0a82ff5` | 2026-10-18 | README: how it fits together, and what Render needs |
| `a45cd61` | 2026-10-18 | Log why an upload could not be read |
| `d07e868` | 2026-10-18 | Merge `kava/main` into MusicRender |
| `414f711` | 2026-10-18 | Sidebar and Settings show the signed-in account |
| `6194acb` | 2026-10-18 | Sonnet reads dotted rhythms that Haiku misses |
| `a927f66` | 2026-10-18 | Photos via a Claude vision model when `ANTHROPIC_API_KEY` is set |
| `03a3385` | 2026-10-18 | Failed or cancelled Google sign-in lands as the demo user |
| `b269254` | 2026-10-15 | Free hosting: decline photo uploads instead of crashing |
