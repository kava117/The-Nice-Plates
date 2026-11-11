# UI/UX revisions, round 1

This round implements `uiux.txt` on branch `uiux1`. It is committed in small steps (see `git log 7c12e46..HEAD`).

Before each commit I checked the change in a real browser (Playwright/Chromium against the local dev server). I also ran the unit tests (189 passed, 7 xfailed as before) and the repo's own browser scripts in `tests/browser/` (`passages.py`, `practice_timer.py`, `player.py`, `live.py`). I updated those scripts wherever the wording or behaviour changed on purpose.

Decisions made with the product owner before starting:
- Discard the untracked files left from an earlier attempt and write fresh versions.
- The microphone button that was called "Listen" is now **Auto-mark**, so that **Listen** can mean "play the music".
- Dragging a saved passage's ends **edits that passage in place and keeps its reps**.
- **Start practice** only starts the timed session. It does not start playback.

## 1. Summary of changes per task

### A. Practice passages

- **A1. "chunk" → "passage".** No user-facing text said "chunk". The only occurrence was a local variable in the recorder code. I checked the rendered text, titles, aria-labels and placeholders on Home, Library, Practice, Progress and Settings: none contain "chunk".
- **A2. "+ New passage".**
  - A new button sits in the passage row. It enters selection mode and shows: **"Drag across the bars you want to practice."** It also says you can tap the first and last bar, or type the bars in. Cancel or Esc leaves selection mode.
  - While the piece has no passages, the button is solid green so it stands out.
  - Dragging across bars without pressing the button still works. So do the Bars box, the `[` `]` keys and double-click.
- **A3. Auto-save.**
  - A passage saves as soon as it's made, whether by drag, Bars box, `[` `]` or double-click.
  - Dragging a handle saves the new bars after a 600 ms pause, as the **same** passage with its reps. This uses a new `PUT /api/sections/<id>` endpoint. There is no schema change. If the new bars match another passage, the endpoint returns 409 and changes nothing.
  - The Save button is gone, and so are the dashed "not saved" drafts.
  - A brief, non-blocking **"Passage saved"** toast confirms each save (new `toast.js`).
  - Reloading keeps everything. The browser check covers create, resize, reload.
- **A4. Delete always reachable.**
  - Every passage chip has a bin button with a label such as "Delete bars 3–6".
  - The selected passage has **Delete** beside its name in the rep row.
  - **Delete** or **Backspace** deletes the selected passage.
  - There is no confirmation dialog. Instead a toast says "Bars 3–6 deleted" with **Undo** for 5 seconds, and **Ctrl/⌘+Z** also undoes it. The server delete waits until the 5 seconds are up; leaving the page sends it at once.
  - A passage can be deleted straight after it's created.
- **A5. Deselect.** A click outside the passage, whether on another bar, empty sheet music or the page, deselects it and removes its highlight. So does **Esc**.
- **A6. "Was that correct?"**
  - What the answers do in the code: each Yes / Not yet saves a rep (correct or not, plus the tempo) to the passage. It also starts the practice timer if it isn't running. It drives the tempo advice too: 3 correct in a row offers a faster tempo, 2 misses a slower one. Finally, it feeds the dots on the chip, the "next up" pick and the coach.
  - New helper line: **"Answering tracks your progress on this passage and suggests when to change the tempo."**
  - Answering never hides Delete. Only Yes and Not yet are disabled, and only while an answer saves. The old "Remove? Keep" question that replaced the controls is gone.
- **A7. Empty state.** "No passages yet. A passage is a few bars you loop and practice on their own. Start one with **+ New passage**." It appears beside the button it names.

### B. Listen, practice and record

- **B1. Distinct labels and icons.**
  - **Listen** has a speaker icon and plays the selected passage or the whole piece. It reads Loading… / Stop while playing.
  - **Start practice** has a timer icon.
  - **Record yourself** has a record icon. It reads Cancel during the count-in and Stop recording while recording. Saved takes are listed as "Recordings".
  - The rep row's microphone button is now **Auto-mark**.
- **B2. Hierarchy.** Start practice is the toolbar's one solid (primary) button. Listen and Record yourself are secondary. Listen lost its green outline.
- **B3. Labels match state.**
  - Before a session, the button reads Start practice.
  - During one it reads Pause or Resume, and **Finish session** (was "Stop and save") appears next to it.
  - After Finish session, everything resets to Start practice and shows "Session saved: 5 min · See Progress".
  - Record yourself resets after a take, a cancel, or when the music runs out.
- **B4. "Practicing: …".** The line beside the timer shows **"Practicing: whole piece"** or **"Practicing: bars X–Y"** (or "bar X"), and follows the selection. While paused it says "Paused: …".
- **B5. Bars placeholder.** It now reads **"e.g. 12–16"** in muted italic, at full strength so it still meets AA. Screen readers also hear "Type bar numbers to make a passage".
- **B6. Change piece.** A **"‹ Change piece"** button at the start of the toolbar goes back to Library.

### C. Wording

- **C1. Upload flow** (new `upload.js` and `templates/upload_status.html`). Library's form and Home's button now upload by XMLHttpRequest:
  - **"Uploading your sheet music…"** shows with a **determinate progress bar**, based on the browser's real upload progress.
  - Then **"Converting to notation — this can take up to a minute"**. The server doesn't report conversion progress, so this stage uses **labelled stages** (Uploading → Converting → Done) and a spinner, not a bar.
  - Then **"Done — opening your piece…"**, and the practice page opens.
  - On failure, the server's reason (or a connection message) shows in red with a **Try again** button that resends the same file.
  - Without JavaScript the forms post exactly as before.
- **C2. Tutorial copy.**
  - "Score" is now "sheet music" in the tour, and in other user-facing text: the practice page's loading and error lines, the upload error, the live lane's label and the privacy page.
  - **"Pick a passage and click Listen to loop it."** and **"Lower the tempo to practice it slowly."** are in the tour.
  - Every step was reworded in plain language and names the new controls (+ New passage, Auto-mark, Finish session). The full list is in section 2.
- **C3.** The "Cozy" view size is now **"Large"**. The `data-density` value was renamed too, which is low-risk.

### D. Onboarding

- **D1.** **"Skip — I'm just starting out"** sits at the top of the questionnaire, with a note: "We'll start you at the beginner level. You can change it any time in Settings."
  - It saves level 1 (the beginner level) in all four categories and goes to Home. It is a separate form posting `skip=beginner`, which `/onboarding` handles. A unit test was added.
- **D2.** A small hint sits above the sheet music: "**Practice a few bars at a time.** Click **+ New passage**, then drag across the bars you want on the sheet music below."
  - It stays until this browser makes its first passage, remembered in localStorage. It also hides on pieces that already have passages.

### E. Visual polish

- **E1. Buttons.**
  - The 3D bottom edge on every pressable element is gone, header included. Pressing now nudges the button 1px.
  - Corners went from 12px to 8px.
  - Ghost buttons have a softer border that darkens on hover.
  - The 3px focus outline is unchanged.
- **E2. Practice time on cards.** The "N min practiced" badge over the art is removed. Home **and** Library show a quiet line under the title, such as "2h 15m practiced" or "Not practiced yet". This comes from a new `practiced` Jinja filter, which has unit tests.
- **E3. Collapsible sidebar.**
  - A toggle at the left of the top bar hides the sidebar, so the sheet music reflows to the full width.
  - The choice is remembered between visits in localStorage. It is applied before first paint, so there's no flash.
  - The toggle's `aria-expanded` and label ("Hide the menu" / "Show the menu") stay in step.
- **E4. Header.** "The Nice Plates" (logo and name) moved from the sidebar into the top bar. The bar went from 48px to a minimum of 44px, with 16px sides, slimmer buttons and less empty space.
- **E5. Dark mode.**
  - The turquoise accent `#3EC5BB` became sage green `#6FBF8A`, the same family as light mode's forest green. Its edge colour became `#3F8A5A`, and text on it is `#14201A`.
  - **WCAG AA:** a script measured every visible text node on Home, Library, Practice (with a passage selected and the rep row showing), Progress, Settings and Privacy, in both themes, against its real background. **All text passes**. The only failures were placeholders faded with opacity (2.96–4.26:1). They now use full-strength muted ink.
  - Text-box borders now use a `--control-edge` colour at ≥3:1 against every background, for WCAG 1.4.11 non-text contrast.
- **E6. Thumbnails.** Home showed stock photos of other music, and Library showed nothing. Now `thumbs.js` draws each piece's own first bars with OpenSheetMusicDisplay off-screen and crops a card-shaped box around the **title**. It saves that as a small JPEG in localStorage, and the existing CSS blurs and tints it.
  - Pieces are drawn one at a time, as their cards near the screen.
  - If drawing fails, the card keeps its plain tinted art.
- **E7.** Practice time and streak moved to the top of Home.
- **E8.** Home and Library drop the 960px content cap (now 1600px, footer to match).
  - Library's grid fits as many columns as the screen holds. Compact / Normal / Large now set a minimum card width (150 / 220 / 320px) instead of a fixed 6 / 4 / 3 columns.
  - Home's few tiles (up to three pieces plus the actions tile) stretch to fill the row.

### Accessibility checks

- **Mono audio:** nothing is panned or depends on stereo. The piano, count-in and recordings are all centre-mixed, and nothing is conveyed only by sound.
- **200% zoom and large fonts:** I tested Home, Library, Practice, Progress and Settings at a 640px viewport (200% zoom on a 1280px laptop) and with a 200% root font size. There is no sideways scrolling and nothing is clipped. To get there:
  - the top bar now grows with its text
  - the passage row wraps
  - the short labels kick in from 760px
  - the Bars box is sized in `em`
- **Keyboard and labels:** every new control is a native `<button>` or link, with a visible label or an `aria-label`:
  - + New passage (`aria-pressed`, and its hint is linked with `aria-describedby`)
  - each chip's bin ("Delete bars 3–6"), the rep row's Delete, and the toast's Undo
  - the sidebar toggle, Change piece, Try again, and Skip
  
  Also:
  - Toasts and upload progress are announced through polite live regions.
  - Making a passage works entirely from the keyboard: the Bars box or `[` `]`, then Delete and Ctrl/⌘+Z.
  - The Library view-size buttons now report `aria-pressed`.

## 2. User-facing strings changed (old → new)

**Practice toolbar and passages**

| Old | New |
|---|---|
| ▶ Play / ■ Stop / Loading piano… | Listen / Stop / Loading… (with speaker icon) |
| Play or stop (Space) *(tooltip)* | Hear the selected passage, or the whole piece (Space) |
| Start practice / Pause / Resume | Start practice / Pause / Resume (unchanged words, now the primary button with a timer icon) |
| Start or pause the practice timer *(tooltip)* | Time a practice session: it's added to Progress when you finish |
| Stop and save | Finish session |
| Save this session to Progress *(tooltip)* | End this session and add its time to Progress |
| 1:23 *(clock alone)* | Practicing: whole piece · 1:23 / Practicing: bars 3–6 · 1:23 / Paused: … |
| That session ran too long to count | That session ran over 4 hours, so it wasn't counted |
| Saved 5 min · See Progress | Session saved: 5 min · See Progress |
| Practice timer *(group label)* | Practice session |
| Record a take | Record yourself (with record icon) |
| Record *(group label)* | Record yourself |
| Record yourself, then listen back *(tooltip)* | Record yourself, then play it back |
| Name this take | Name this recording |
| Takes / Takes (N) | Recordings / Recordings (N) |
| Takes you've saved for this piece *(tooltip)* | Recordings you've saved for this piece |
| Take N *(unnamed take)* | Recording N |
| Open a piece from the library to record it | Open a piece from Library to record yourself |
| Allow the microphone to record a take | Allow the microphone to record yourself |
| That take was empty. Try again. | That recording was empty. Try again. |
| — | ‹ Change piece (tooltip: Back to Library to pick another piece) |
| 12-16 *(Bars placeholder)* | e.g. 12–16 |
| — | + New passage (+ New on narrow screens) |
| — | Drag across the bars you want to practice. Or tap the first bar, then the last, or type them in Bars. · Cancel |
| Drag across bars on the score to pick a passage, then drag its green handles to adjust it. | No passages yet. A passage is a few bars you loop and practice on their own. Start one with + New passage. |
| — | Practice a few bars at a time. Click + New passage, then drag across the bars you want on the sheet music below. |
| Save *(passage button)* | *(removed: passages save automatically)* |
| Remove / "Remove Bars 3-6 and its N reps?" / Remove · Keep | Delete (bin icon) / *(no question)* toast "Bars 3–6 deleted" · Undo |
| — | Passage saved · Passage restored · "Bars X–Y is already a passage" · "Those bars are already a passage" · "That passage didn't save. Check the connection." · Try again · "The new bars didn't save. Check the connection." |
| — | Delete bars 3–6 *(bin button label)* |
| Bars 3-6 / 3-6 *(hyphen)* | Bars 3–6 / 3–6 *(en dash)* |
| Bars 3-6, N reps, M clean / , not saved *(chip label)* | Bars 3–6, N reps, M correct / , saving |
| Was that clean? | Was that correct? |
| — | Answering tracks your progress on this passage and suggests when to change the tempo. |
| Clean: 1 of 3 in a row. | Correct: 1 of 3 in a row. |
| 3 clean in a row at 46 bpm. / … at full speed. | 3 correct in a row at 46 bpm. / … at full speed. |
| Clean / Not yet *(dot tooltip)* | Correct / Not yet |
| Undo *(rep)* | Undo last answer |
| Took back the last rep. | Took back the last answer. |
| Play it through, then say how it went. | *(removed: the question and its helper line say this)* |
| Listen / Listening *(mic button)* | Auto-mark / Auto-marking |
| Hears each go and marks it for you. Nothing is recorded. (L) | Auto-mark: hears each go through the microphone and answers for you. Nothing is recorded. (L) |
| …Allow it from the address bar, then press Listen. / …Plug one in, then press Listen. / Listening couldn't start. Check the connection, then press Listen again. | …then press Auto-mark. / …then press Auto-mark. / Auto-mark couldn't start. Check the connection, then press Auto-mark again. |
| Drag to move the passage's first/last bar *(handle tooltip)* | *(unchanged)* |
| "Bars 3-6: ] on the last bar" *(while marking)* | "Bars 3–6: ] on the last bar", or "…: now tap the last bar" in + New passage mode |
| Loading the score… | Loading the sheet music… |
| The score didn't load. Reload the page to try again. | The sheet music didn't load. Reload the page to try again. |
| Back to your library | Back to Library |
| The score's notes coming up, and the pitch you play, as it happens *(lane label)* | The notes coming up in the sheet music, and the pitch you play, as it happens |

**Keys panel**

| Old | New |
|---|---|
| Space: Play or stop | Space: Listen, or stop |
| Mouse: Drag across bars to pick a passage; … | Mouse: Drag across bars to make a passage; … |
| [ ]: Mark a passage: [ on its first bar, ] on its last | [ ]: Make a passage: [ on its first bar, ] on its last |
| — | Delete: Delete the selected passage · Ctrl + Z: Undo that delete, for 5 seconds |
| Y N: That went clean, or not yet | Y N: That was correct, or not yet |
| L: Listen, and mark each go for you | L: Auto-mark: hears each go and marks it for you |
| Esc: Back to the whole piece | Esc: Deselect the passage: back to the whole piece |

**Uploads (Library and Home)**

| Old | New |
|---|---|
| Reading your sheet… *(button while uploading)* | Uploading your sheet music… → Converting to notation — this can take up to a minute → Done — opening your piece… (with Uploading / Converting / Done stages) |
| File too large (max 20 MB). *(client check)* | That file is over 20 MB. Try a smaller PDF or photo. |
| That file is over 20 MB *(Home)* | That file is over 20 MB. Try a smaller PDF or photo. |
| — | The upload didn't get through. Check your connection and try again. · Something went wrong on our side (N). Try again in a moment. · The upload finished, but the piece didn't open. Check Library, or try again. · Try again |
| Could not read X. Upload a PDF, a photo of a score, or a MusicXML file. | Could not read X. Upload a PDF, a photo of sheet music, or a MusicXML file. |
| Upload new sheets *(Home)* | Upload sheet music |

**Library and Home**

| Old | New |
|---|---|
| Cozy | Large |
| N min practiced *(badge over the art)* | Xh Ym practiced / Ym practiced / Under a minute practiced / Not practiced yet *(line under the title)* |
| — | Hide the menu / Show the menu *(sidebar toggle)* |

**Onboarding**

| Old | New |
|---|---|
| — | Skip — I'm just starting out · We'll start you at the beginner level. You can change it any time in Settings. |

**Progress**

| Old | New |
|---|---|
| On Practice, press **Start practice** when you sit down, then **Stop and save**. That minute shows up here. | On Practice, click **Start practice** when you sit down, then **Finish session** when you're done. The time shows up here. |

**Tour (tour.js)**

| Step | Old | New |
|---|---|---|
| Home · Getting around | Library holds your pieces, Practice is where you play, and Progress shows your time. | …and Progress shows how much you've practiced. |
| Home · Your pieces | Click one to practice it. The bar on top shows the minutes you've put in. | Click one to practice it. The line under each title shows how long you've practiced it. |
| Home · Add your music | Upload a PDF, a photo of the page or a MusicXML file. It becomes a score you can play along with. | …We turn it into sheet music you can play along with. |
| Library · Add a piece | A PDF, a photo of the page or a MusicXML file. A photo can take half a minute to read. | Upload a PDF, a photo of the page or a MusicXML file. Turning it into sheet music can take up to a minute. |
| Practice · "Pick a passage" → "Make a passage" | Work on a few bars at a time. Drag across them on the score, or type them here, and Play loops just those. / Try it: type 1-4 in Bars and press Enter. | A passage is a few bars you practice on their own. Click + New passage, then drag across those bars on the sheet music. / Or type bar numbers: put 1–4 in Bars and press Enter. |
| Practice · Hear it | Play follows along on the score. Slow the tempo right down while you learn it. | Pick a passage and click Listen to loop it. Lower the tempo to practice it slowly. |
| Practice · "Count each go" → "Count each try" | Play it through, then say if it went clean. Or press Listen and it marks each go for you. | After each time through, answer Yes or Not yet. Or turn on Auto-mark and it listens through your microphone and answers for you. |
| Practice · Time your practice | Press Start practice when you sit down. When you're done, Stop and save — that minute lands on Progress. | Start practice times your session. Click Finish session when you're done, and the time shows up on Progress. |
| Progress · How time gets here | Nothing shows until a session is saved. On Practice: Start practice, then Stop and save. | Nothing shows here until you finish a session. On Practice, click Start practice, then Finish session. |
| Progress · This week | Minutes practiced each day. They appear after you press Stop and save on Practice. | Minutes practiced each day, added when you click Finish session on Practice. |
| Settings | Your account, and the playing levels you picked. Update them any time. | …You can change them any time. |

**Privacy page**

| Old | New |
|---|---|
| …Listen results shown on the score… | …Auto-mark results shown on the sheet music… |
| To show your library, score, Progress charts… | To show your library, sheet music, Progress charts… |
| …into a playable score (OMR)… | …into playable sheet music (OMR)… |

## 3. Tasks not completed, or completed with a caveat

All tasks were implemented. Caveats:

- **C1:** the "Converting" stage can't show a determinate bar, because the server doesn't report conversion progress. As the task allows, it uses labelled stages and a spinner. The upload stage does have a real bar.
- **E6:** thumbnails are rendered **in the browser**. There's no server-side notation renderer, so the first visit to Home or Library draws each missing thumbnail once (loading OpenSheetMusicDisplay, ~1 MB), then caches it per browser. A server-side renderer would remove that first-visit cost.
- **E8:** I read "fit the entire screen" as "use the full width": the 960px cap is gone and the grids fill the row. A Library with few pieces still leaves empty columns to the right, because cards keep a sensible width rather than stretching to banners. Home's few tiles do stretch.
- **WCAG AA (E5):** text contrast was measured by script across the main pages in both themes, along with text-box borders. Onboarding wasn't in the browser scan, because it needs a fresh Google account. It uses the same tokens and components. Icon-only and non-text checks beyond text boxes (switches, chart colours on Progress) were reviewed by eye, not measured.
- **Code identifiers kept** (low-risk rule):
  - `Sections`, `section_id` and the `/api/sections` routes still mean passages.
  - A rep's `clean` field and column mean "correct". There's a comment in `app.py`.
  - The recorder's `take` variables mean recordings. There's a comment in `practice.html`.
  - The coach's server prompt (`coach.py`) still calls reps "clean", so the coach's answers may say "clean" while the page says "correct".

## 4. Unrelated bugs noticed but not fixed

1. **Every guest shares one account.** "Continue as guest" signs everyone into the same Sample User. While testing, passages appeared on the demo piece that no test made. They came from another browser using the same server, because guests see, and can delete, each other's passages, recordings and sessions.
2. **Pieces can't be removed.** There's no delete-piece route or button, so every upload, including a test or mistaken one, stays in Library for good.
3. **Uploads with no title get the file name** ("AirOnG") and can't be renamed afterwards.
4. **`OVER_CAP` in `app.py` is still undecided** ("The team still has to pick one"). Sessions over 4 hours are silently dropped.
5. **The practice page with no pieces at all** falls back to the bundled demo score, where passages can't be saved (there's no piece id). It says "Open a piece from your library to count reps", but you can still make passages that vanish on reload.

(Fixed in passing, because it was on a control being reworked: Library's view-size buttons never updated `aria-pressed`.)
