"""Passages in a real browser: pick bars on the score, loop them, count reps, and the keys that do the same.

Run from the repo root (Python 3.11 env, plus: pip install playwright && python -m playwright install --with-deps chromium):
    SECRET_KEY=x gunicorn app:app --workers 1 --threads 4 --bind 127.0.0.1:8124
    python tests/browser/passages.py            # add --browser webkit for Safari's engine
Uses the demo user's copy of Air, and leaves its passages as it found them.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8124"
engine = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"
bar_at = "osmd.cursor.Iterator.CurrentMeasureIndex"   # 0-based: bar 3 is index 2

with sync_playwright() as p:
    browser = getattr(p, engine).launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    api = lambda url: page.evaluate(f"fetch('{url}').then(r => r.json())")
    title, note = page.locator("#rep-title"), page.locator("#rep-note")

    page.goto(BASE + "/library")
    piece = next(x["id"] for x in api("/api/pieces") if x["title"] == "Air")
    for old in api(f"/api/pieces/{piece}/sections"):
        page.evaluate(f"fetch('/api/sections/{old['id']}', {{method: 'DELETE'}})")
    page.goto(f"{BASE}/practice?piece={piece}")
    page.wait_for_function("!document.getElementById('play').disabled")
    page.wait_for_timeout(500)
    assert page.locator(".score-bar").count() == 37, "one box per bar of Air"
    assert not page.locator("#rep").is_visible()

    # drag from bar 3 to bar 6: a passage, not saved until its first rep
    def drag(a, b):
        one, two = page.locator(f'.score-bar[data-index="{a}"]').bounding_box(), page.locator(f'.score-bar[data-index="{b}"]').bounding_box()
        page.mouse.move(one["x"] + 20, one["y"] + one["height"] / 2)
        page.mouse.down()
        page.mouse.move(one["x"] + 60, one["y"] + one["height"] / 2, steps=4)
        page.mouse.move(two["x"] + two["width"] / 2, two["y"] + two["height"] / 2, steps=8)
        page.mouse.up()
        page.wait_for_timeout(400)
    drag(2, 5)
    assert title.inner_text() == "Bars 3-6" and page.evaluate(bar_at) == 2
    assert page.locator(".chip.is-draft").count() == 1 and api(f"/api/pieces/{piece}/sections") == []
    assert page.locator(".score-bar.in").count() == 4

    # a rep saves it, and starts the practice timer
    page.keyboard.press("y"); page.wait_for_timeout(400)
    saved = api(f"/api/pieces/{piece}/sections")
    assert [(s["start"], s["end"], s["reps"], s["clean"]) for s in saved] == [(3, 6, 1, 1)], saved
    assert page.locator("#timer").inner_text() == "Pause", "a rep should start the timer"
    assert api("/api/practice/state")["section_id"] == saved[0]["id"], "the timer start overwrote the remembered passage"
    assert note.inner_text() == "Clean: 1 of 3 in a row."

    # Next stays inside the passage and goes round; Shift+Right a bar at a time
    seen = set()
    for _ in range(40):
        page.keyboard.press("ArrowRight")
        seen.add(page.evaluate(bar_at))
    assert seen == {2, 3, 4, 5}, seen
    page.keyboard.press("Home"); assert page.evaluate(bar_at) == 2
    for want in (3, 4, 5, 2):
        page.keyboard.press("Shift+ArrowRight"); assert page.evaluate(bar_at) == want
    page.keyboard.press("ArrowLeft"); assert page.evaluate(bar_at) == 2, "Prev at the passage's first note stays put"

    # three clean in a row below full speed offers the next tempo up
    page.locator("#tempo").fill("70"); page.wait_for_timeout(100)
    for _ in range(3):
        page.keyboard.press("y"); page.wait_for_timeout(300)
    assert note.inner_text() == "3 clean in a row at 46 bpm.", note.inner_text()
    page.get_by_role("button", name="Try 53 bpm").click()
    assert page.locator("#tempo").input_value() == "80" and page.locator("#tempo-label").inner_text() == "53 bpm"
    page.keyboard.press("n"); page.wait_for_timeout(300)
    page.keyboard.press("n"); page.wait_for_timeout(300)
    assert page.get_by_role("button", name="Slow to 46 bpm").is_visible()
    page.get_by_role("button", name="Undo").click(); page.wait_for_timeout(300)
    assert api(f"/api/pieces/{piece}/sections")[0]["reps"] == 5

    # Play loops one bar: the cursor never leaves bar 3 and comes back to its start
    page.locator("#bars-input").fill("3"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
    assert title.inner_text() == "Bar 3"
    page.locator("#tempo").fill("200")
    page.keyboard.press("Space")
    page.wait_for_function("document.getElementById('play').textContent.includes('Stop')", timeout=30000)
    path = []
    for _ in range(40):
        page.wait_for_timeout(100)
        path.append(page.evaluate(f"[{bar_at}, osmd.cursor.Iterator.CurrentSourceTimestamp.RealValue]"))
    page.keyboard.press("Space")
    assert {b for b, _ in path} == {2}, f"left the passage: {path}"
    beats = [t for _, t in path]
    assert any(later < earlier for earlier, later in zip(beats, beats[1:])), "never went round"
    assert "Play" in page.locator("#play").inner_text()

    # arrows on the tempo slider change the tempo, not the cursor
    at = page.evaluate(bar_at)
    page.locator("#tempo").focus(); page.keyboard.press("ArrowLeft")
    assert page.evaluate(bar_at) == at and page.locator("#tempo").input_value() == "190"
    page.locator("#tempo").blur()

    # a click moves the cursor; [ and ] mark a passage at the cursor's bar
    page.keyboard.press("Escape")
    assert not page.locator("#rep").is_visible() and page.locator(".score-bar.in").count() == 0
    page.locator('.score-bar[data-index="9"]').click(position={"x": 10, "y": 60})
    assert page.evaluate(bar_at) == 9 and not page.locator("#rep").is_visible()
    page.keyboard.press("["); page.keyboard.press("Shift+ArrowRight"); page.keyboard.press("Shift+ArrowRight"); page.keyboard.press("]")
    assert title.inner_text() == "Bars 10-12", title.inner_text()

    # a bar number that isn't in the piece is refused
    page.locator("#bars-input").fill("400"); page.keyboard.press("Enter")
    assert title.inner_text() == "Bars 10-12" and not page.evaluate("document.getElementById('bars-input').validity.valid")
    page.locator("#bars-input").fill("")

    # the two handles move either end of the passage, like a range slider's thumbs
    def pull(end, to):
        grip, bar = page.locator(f".passage-handle.is-{end}").bounding_box(), page.locator(f'.score-bar[data-index="{to}"]').bounding_box()
        page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] + grip["height"] / 2); page.mouse.down()
        page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2, steps=10); page.mouse.up()
        page.wait_for_timeout(300)
        assert page.evaluate("getSelection().type") != "Range", "dragging selected text (and can scroll the page under the pointer)"
        return title.inner_text()
    assert page.locator(".passage-handle").count() == 2
    assert pull("end", 13) == "Bars 10-14" and pull("start", 11) == "Bars 12-14"
    assert pull("start", 13) == "Bar 14", "the start handle can't pass the end"

    # coming back opens the passage practiced last
    page.locator(".chip", has_text="3-6").click(); page.wait_for_timeout(300)
    page.reload()
    page.wait_for_function("!document.getElementById('play').disabled"); page.wait_for_timeout(800)
    assert title.inner_text() == "Bars 3-6" and page.evaluate(bar_at) == 2

    # Remove asks first
    page.get_by_role("button", name="Remove").click()
    assert "5 reps" in note.inner_text()
    page.locator("#rep-actions").get_by_role("button", name="Remove").click(); page.wait_for_timeout(400)
    assert api(f"/api/pieces/{piece}/sections") == [] and not page.locator("#rep").is_visible()

    # phone width: nothing scrolls sideways, and the rep buttons are on screen
    page.set_viewport_size({"width": 375, "height": 740})
    page.locator("#bars-input").fill("2-3"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= 375, f"page is {width} px wide"
    assert page.locator("#rep-yes").is_visible() and page.locator("#rep-no").is_visible()
    page.keyboard.press("Escape")

    # a piece that's gone says so, instead of showing Bach
    page.goto(BASE + "/practice?piece=999999"); page.wait_for_timeout(1500)
    assert page.locator("#score-missing").is_visible() and page.locator("#score svg").count() == 0

    page.goto(f"{BASE}/practice?piece={piece}")   # leave the timer as we found it
    page.wait_for_timeout(800)
    if page.locator("#stop").is_visible():
        page.locator("#stop").click()
    assert not errors, errors
    browser.close()
print(f"passages OK in {engine}")
