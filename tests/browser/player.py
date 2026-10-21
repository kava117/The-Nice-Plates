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
    page.goto(BASE + "/practice")
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

    assert not errors, errors
    browser.close()
print(f"player OK in {engine}")
