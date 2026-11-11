"""Change 5 check in a real browser: the pause beacon's cookie sticks, reload keeps running, time away isn't counted.

The session clock starts from a rep or a recording now (no Start practice button). This script
starts it through the same API the page uses, then checks Pause / Resume / Finish session.

Run from the repo root (Python 3.11 env, plus: pip install playwright && python -m playwright install --with-deps chromium):
    SECRET_KEY=x gunicorn app:app --workers 1 --threads 4 --bind 127.0.0.1:8124
    python tests/browser/practice_timer.py            # add --browser webkit for Safari's engine
Safari itself still needs a check by hand: start, switch to Library for a minute, come back, expect Resume.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8124"
engine = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"

with sync_playwright() as p:
    browser = getattr(p, engine).launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    state = lambda: page.evaluate("fetch('/api/practice/state').then(r => r.json())")
    timer, stop, clock = page.locator("#timer"), page.locator("#stop"), page.locator("#clock")

    page.goto(BASE + "/practice"); page.wait_for_timeout(800)
    assert not timer.is_visible() and not stop.is_visible()

    # Same path Record / a rep uses: POST /api/timer/start, then the page picks it up on refresh.
    page.evaluate("fetch('/api/timer/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})")
    page.reload(); page.wait_for_timeout(1200)
    assert timer.inner_text() == "Pause" and stop.is_visible()
    assert not clock.inner_text().endswith("0:00"), "reload lost the running timer"
    page.wait_for_timeout(1100)

    page.goto(BASE + "/library"); page.wait_for_timeout(500)
    away = state()
    assert not away["running"], "the pagehide beacon's pause didn't stick"
    page.wait_for_timeout(6000)
    page.goto(BASE + "/practice"); page.wait_for_timeout(800)
    assert timer.inner_text() == "Resume" and state()["elapsed"] == away["elapsed"], "time away was counted"

    stop.click(); page.wait_for_timeout(500)
    assert not timer.is_visible() and clock.inner_text().startswith("Session saved")

    page.evaluate("fetch('/api/timer/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})")
    page.reload(); page.wait_for_timeout(1000)
    assert timer.inner_text() == "Pause"
    page.evaluate("Object.defineProperty(document, 'hidden', {value: true, configurable: true}); document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(500)
    assert timer.inner_text() == "Resume" and not state()["running"]
    page.locator("#stop").click()

    assert not errors, errors
    browser.close()
print(f"practice timer OK in {engine}")
