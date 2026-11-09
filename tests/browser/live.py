"""Record a take in a real browser, with a fake violin for the microphone: the count-in, the lane
following the score, how fast a new pitch shows, and the take saving.

Run from the repo root (Python 3.11 env, plus: pip install playwright && python -m playwright install --with-deps chromium):
    SECRET_KEY=x gunicorn app:app --workers 1 --threads 4 --bind 127.0.0.1:8124
    python tests/browser/live.py            # add --shots DIR to see the lane
How the lane looks, and a real violin, still need a go by hand.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8124"
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None   # a folder for screenshots

# The microphone is a sawtooth (rich in overtones, like a bowed string), silent until the test plays it.
FAKE_MIC = """
navigator.mediaDevices.getUserMedia = async () => {
  const ctx = new AudioContext(), osc = new OscillatorNode(ctx, { type: "sawtooth", frequency: 440 });
  const gain = new GainNode(ctx, { gain: 0 }), out = ctx.createMediaStreamDestination();
  osc.connect(gain).connect(out);
  osc.start();
  window.fake = { ctx, osc, gain };
  return out.stream;
};
"""

# Plays the top staff's highest notes from the downbeat (when the button turns to Stop recording).
PLAY_THE_SCORE = """async () => {
  const events = scoreEvents(osmd.cursor.Iterator), speed = tempo.value / 100;
  await new Promise(r => { const f = () => record.textContent.includes("Stop") ? r() : requestAnimationFrame(f); f(); });
  const t = fake.ctx.currentTime;
  const staff = Math.min(...events.flatMap(e => e.notes.map(n => n.staff)));   // the top staff, as the lane draws
  for (const e of events) if (e.notes.some(n => n.staff === staff)) {
    const top = Math.max(...e.notes.filter(n => n.staff === staff).map(n => n.midi));
    fake.osc.frequency.setValueAtTime(440 * 2 ** ((top - 69) / 12), t + e.seconds / speed);
  }
  fake.gain.gain.setValueAtTime(0.3, t);
}"""

# From the moment the sound jumps to a new pitch until the lane has it: in milliseconds.
LAG = """async () => {
  const trail = document.getElementById("live-canvas").trail, target = 69 + 12 * Math.log2(1000 / 440);
  fake.osc.frequency.cancelScheduledValues(0);
  const start = performance.now();
  fake.osc.frequency.setValueAtTime(1000, fake.ctx.currentTime);
  await new Promise(r => { const f = () => trail.length && Math.abs(trail.at(-1).midi - target) < 0.3 || performance.now() - start > 2000 ? r() : requestAnimationFrame(f); f(); });
  return performance.now() - start;
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(FAKE_MIC)
    page.goto(BASE + "/library")
    air = next(x["id"] for x in page.evaluate("fetch('/api/pieces').then(r => r.json())") if x["title"] == "Air")
    page.goto(f"{BASE}/practice?piece={air}")
    page.wait_for_function("!document.getElementById('play').disabled")
    lane = page.locator("#live-lane")
    assert lane.is_hidden()

    page.locator("#take-name").fill("Live lane test")
    page.locator("#record").click()
    page.evaluate(f"() => {{ ({PLAY_THE_SCORE})(); }}")   # waits for the downbeat by itself
    lane.wait_for(state="visible")
    assert page.locator("#record").inner_text() == "Cancel"
    page.wait_for_timeout(1500)
    if SHOTS: page.screenshot(path=f"{SHOTS}/count-in.png")
    # one bar of 4/4 at 66 bpm (Air): about 3.6 s of ticks before the take starts
    counted = page.evaluate("""() => new Promise(r => { const t = performance.now();
      const f = () => record.textContent.includes("Stop") ? r(performance.now() - t) : requestAnimationFrame(f); f(); })""")
    assert 1500 < counted < 3200, f"take started {counted:.0f} ms after the screenshot, expected about 2100"
    assert page.locator("#record").evaluate("b => b.classList.contains('is-recording')")

    page.wait_for_timeout(8000)
    if SHOTS: page.screenshot(path=f"{SHOTS}/take.png")
    trail = page.evaluate("document.getElementById('live-canvas').trail.filter(p => p.on !== null && p.t > 0.3)")
    on = sum(p["on"] for p in trail) / max(1, len(trail))
    assert len(trail) > 8 * 100, f"only {len(trail)} pitches in 8 s"   # about 190 a second
    assert on > 0.9, f"only {on:.0%} of the score-in-tune notes drawn as in tune"
    assert page.evaluate("osmd.cursor.Iterator.CurrentEnrolledTimestamp.RealValue") > 1, "cursor didn't move with the take"

    lags = [page.evaluate(LAG)]
    page.evaluate("fake.osc.frequency.setValueAtTime(440, fake.ctx.currentTime)")
    page.wait_for_timeout(300)
    lags += [page.evaluate(LAG)]
    assert max(lags) < 80, f"a new pitch took {max(lags):.0f} ms to reach the lane"

    page.locator("#record").click()   # Stop
    page.wait_for_function("document.getElementById('take').textContent.includes('Saved')", timeout=10000)
    assert lane.is_visible(), "the lane should stay up to look back at"
    page.locator("#live-close").click()
    assert lane.is_hidden()

    # Cancel during the count-in records nothing
    page.locator("#record").click()
    lane.wait_for(state="visible")
    page.locator("#record").click()
    assert page.locator("#record").inner_text() == "Record a take" and lane.is_hidden()
    page.wait_for_timeout(4500)
    assert page.locator("#record").inner_text() == "Record a take", "a cancelled count-in started recording anyway"

    assert not errors, errors
    print(f"ok: {len(trail)} pitches, {on:.0%} in tune, new pitch on screen in {max(lags):.0f} ms")
    browser.close()
