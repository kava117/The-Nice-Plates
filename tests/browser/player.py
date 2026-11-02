"""Playback check in a real browser: the player makes sound, the cursor follows it, Stop and tempo work.

Run from the repo root (Python 3.11 env, plus: pip install playwright && python -m playwright install --with-deps chromium):
    SECRET_KEY=x gunicorn app:app --workers 1 --threads 4 --bind 127.0.0.1:8124
    python tests/browser/player.py            # add --browser webkit for Safari's engine
Whether it sounds right (notes, the repeat in Air) still needs a listen by hand.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8124"
engine = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"
where = "osmd.cursor.Iterator.CurrentEnrolledTimestamp.RealValue"   # cursor position, in whole notes from the start

with sync_playwright() as p:
    browser = getattr(p, engine).launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/library")   # /practice alone opens the latest piece, so open Air by its id
    air = next(x["id"] for x in page.evaluate("fetch('/api/pieces').then(r => r.json())") if x["title"] == "Air")
    page.goto(f"{BASE}/practice?piece={air}")
    play = page.locator("#play")
    play.wait_for(state="visible")
    page.wait_for_function("!document.getElementById('play').disabled")
    assert page.locator("#tempo-label").inner_text() == "66 bpm"

    # Air, repeats played out: 433 cursor steps, 71 whole notes at 66 bpm
    events = page.evaluate("scoreEvents(osmd.cursor.Iterator).length")
    seconds = page.evaluate("scoreEvents(osmd.cursor.Iterator).at(-1).seconds")
    assert events == 433 and abs(seconds - 71 * 4 * 60 / 66) < 3, (events, seconds)

    play.click()
    page.wait_for_function("document.getElementById('play').textContent.includes('Stop')", timeout=30000)   # piano loaded
    page.evaluate("window.meter = new Tone.Meter(); Tone.getDestination().connect(meter)")
    page.wait_for_timeout(3000)
    level = page.evaluate("meter.getValue()")
    moved = page.evaluate(where)
    assert level > -60, f"no sound: {level} dB"
    assert 0.5 < moved < 2.5, f"cursor at {moved} whole notes after 3 s (expect about 66/60 * 3 / 4 = 0.8, more if loading was fast)"

    play.click()   # Stop
    stopped_at = page.evaluate(where)
    page.wait_for_timeout(1000)
    assert page.evaluate(where) == stopped_at and "Play" in play.inner_text(), "cursor kept moving after Stop"

    # half tempo from the beginning: about half as far in the same time
    page.locator("#cursor-reset").click()
    page.locator("#tempo").fill("50")
    assert page.locator("#tempo-label").inner_text() == "33 bpm"
    play.click(); page.wait_for_timeout(3000); play.click()
    slow = page.evaluate(where)
    assert 0.2 < slow < 0.6, f"at 50 % the cursor reached {slow} whole notes in 3 s"

    # Next while playing stops playback
    play.click(); page.wait_for_timeout(500)
    page.locator("#cursor-next").click()
    assert "Play" in play.inner_text()

    # deep into the piece the score has scrolled, but Play/Stop must still be on screen and clickable
    for width, height in ((1280, 720), (375, 700)):
        page.set_viewport_size({"width": width, "height": height})
        page.locator("#cursor-reset").click()
        page.evaluate("for (let i = 0; i < 250; i++) osmd.cursor.next()")   # followCursor scrolls each step
        page.wait_for_timeout(1500)                                          # let the smooth scroll finish
        on_top = page.evaluate("""() => {
            const b = document.getElementById('play').getBoundingClientRect();
            return document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2) === document.getElementById('play');
        }""")
        scrolled = page.evaluate("Math.max(document.querySelector('main').scrollTop, window.scrollY)")
        assert scrolled > 300 and on_top, f"{width} px: scrolled {scrolled}, Play reachable: {on_top}"
        play.click(); page.wait_for_function("document.getElementById('play').textContent.includes('Stop')")
        play.click(); assert "Play" in play.inner_text()

    assert not errors, errors
    browser.close()
print(f"player OK in {engine}")
