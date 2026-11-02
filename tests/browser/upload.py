"""Your own music, not just the demo: upload a different piece and practice a passage of it.

Run from the repo root (Python 3.11 env with ml/requirements.txt, plus playwright):
    SECRET_KEY=x gunicorn app:app --workers 1 --threads 4 --bind 127.0.0.1:8124
    python tests/browser/upload.py
Uses a Bach chorale from music21's corpus (four voices, a pickup bar), uploaded once from the
Library and once from Home.
"""
import re, sys, tempfile
from pathlib import Path
from music21 import corpus
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8124"
engine = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"
chorale = Path(tempfile.mkdtemp()) / "chorale.musicxml"
corpus.parse("bach/bwv66.6").write("musicxml", fp=chorale)

with sync_playwright() as p:
    browser = getattr(p, engine).launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    ready = "document.getElementById('play') && !document.getElementById('play').disabled"

    # from the Library, with a title and composer
    page.goto(BASE + "/library")
    page.set_input_files("#sheet", str(chorale))
    page.locator("#upload input[name=title]").fill("Chorale 66.6")
    page.locator("#upload input[name=composer]").fill("J. S. Bach")
    page.locator("#upload button[type=submit]").click()
    page.wait_for_url(re.compile(r"/practice\?piece=\d+"), timeout=60000)
    page.wait_for_function(ready); page.wait_for_timeout(500)
    piece = page.url.split("piece=")[1]
    assert page.evaluate("osmd.Sheet.Staves.length") == 4, "four voices"
    bars = page.locator(".score-bar").count()
    assert bars > 5, bars

    # passages work on it: the pickup bar is numbered 0, so typed bar numbers are the printed ones
    page.locator("#bars-input").fill("1-2"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
    assert page.locator("#rep-title").inner_text() == "Bars 1-2"
    assert page.evaluate("osmd.cursor.Iterator.CurrentMeasureIndex") == 1
    page.keyboard.press("y"); page.wait_for_timeout(500)
    saved = page.evaluate(f"fetch('/api/pieces/{piece}/sections').then(r => r.json())")
    assert [(s["start"], s["end"], s["reps"]) for s in saved] == [(2, 3, 1)], saved
    page.locator("#stop").click(); page.wait_for_timeout(300)

    # it's in the library, and Home offers to continue it
    page.goto(BASE + "/library")
    assert page.locator(".card-title", has_text="Chorale 66.6").count() == 1
    page.goto(BASE + "/home")
    assert "Chorale 66.6" in page.locator(".btn-stack").inner_text()

    # from Home: one click opens the file picker and lands on the new piece
    page.set_input_files("#home-upload", str(chorale))
    page.wait_for_url(re.compile(r"/practice\?piece=\d+"), timeout=60000)
    page.wait_for_function(ready)
    assert page.url.split("piece=")[1] != piece

    assert not errors, errors
    browser.close()
print(f"upload OK in {engine}")
