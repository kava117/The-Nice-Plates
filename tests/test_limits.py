"""Limit tests: every route pushed past normal use.

Each test asserts what SHOULD happen. Known defects are marked xfail(strict=True) with their
ISSUES.md entry; when a fix lands the test passes, strict turns that into a failure, and the
marker should be deleted.
"""
import glob, io, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from unittest import mock

import pytest

from support import AIR, REPO, WORK, appmod, clock, db, flask_app, login, make_user


def known(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


def upload(client, name, data, url="/api/pieces", **form):
    return client.post(url, data={"file": (io.BytesIO(data), name), **form},
                       content_type="multipart/form-data")


# ---------------------------------------------------------------- boot & pages
PAGES = ["/", "/index", "/home", "/library", "/progress", "/settings", "/practice"]

@pytest.mark.parametrize("path", PAGES)
def test_page_loads_as_guest(guest, path):
    assert guest.get(path).status_code == 200

@pytest.mark.parametrize("path", PAGES)
def test_page_loads_signed_in(user, path):
    assert user[0].get(path).status_code == 200

def test_demo_piece_seeded_once_across_restarts():
    for _ in range(2):   # two more cold boots in the same folder
        subprocess.run([sys.executable, "-c", "import app"],
                       cwd=WORK, check=True, capture_output=True, env={**os.environ, "PYTHONPATH": str(REPO)})
    airs = [p for p in db.getPieces(db.demoUser()) if p["title"] == "Air"]
    assert len(airs) == 1

def test_top_bar_log_out_link_signs_you_out(user):
    client, _ = user
    html = client.get("/home").get_data(as_text=True)
    href = html.split('class="btn btn-ghost press" href="', 1)[1].split('"', 1)[0]   # the top-bar Log out link
    client.get(href, follow_redirects=True)
    assert "Sign in with Google" in client.get("/settings").get_data(as_text=True), f"Log out goes to {href} and you stay signed in"

def test_settings_shows_sign_out_when_signed_in(user):
    assert "/logout" in user[0].get("/settings").get_data(as_text=True)

def test_logout_route_signs_out(user):
    client, _ = user
    client.get("/logout")
    assert "Sign in with Google" in client.get("/settings").get_data(as_text=True)


# ---------------------------------------------------------------- practice API
@pytest.mark.parametrize("body", [{}, {"piece_id": "abc"}, {"piece_id": None}, {"piece_id": [1]},
                                  {"piece_id": 10**30}, {"piece_id": -1}, "not json"])
def test_select_piece_bad_input_is_404_not_500(guest, body):
    r = guest.post("/api/practice/piece", data=body if isinstance(body, str) else json.dumps(body),
                   content_type="application/json")
    assert r.status_code == 404

def test_cannot_select_another_users_piece(user):
    client, _ = user
    other_piece = db.addPiece(make_user(), "Secret", xml=AIR)
    assert client.post("/api/practice/piece", json={"piece_id": other_piece}).status_code == 404

def test_sections_can_be_selected():
    """The practice page makes Sections rows (passages), so this endpoint can succeed."""
    assert any("Sections" in l and "INSERT" in l for l in Path(db.__file__).read_text().splitlines()), \
        "no code path creates a Section; /api/practice/section always 404s"

def test_timer_start_pause_resume_stop_adds_up(user):
    client, uid = user
    c, patch = clock()
    with patch:
        client.post("/api/timer/start"); c.offset += 60
        client.post("/api/timer/pause"); c.offset += 600     # paused time must not count
        client.post("/api/timer/start"); c.offset += 30
        r = client.post("/api/timer/stop", json={"notes": "scales"}).get_json()
    assert r["time_spent"] == 90 and r["saved_session_id"]
    assert db.getSessions(uid)[0]["time_spent"] == 90

def test_stop_without_start_saves_nothing(user):
    assert user[0].post("/api/timer/stop").get_json()["saved_session_id"] is None

def test_timer_double_start_does_not_reset(user):
    client, _ = user
    c, patch = clock()
    with patch:
        client.post("/api/timer/start"); c.offset += 100
        client.post("/api/timer/start"); c.offset += 20
        assert client.post("/api/timer/stop").get_json()["time_spent"] == 120

def test_non_string_notes_are_rejected_cleanly(user):
    client, _ = user
    client.post("/api/timer/start")
    with clock(5)[1]:
        r = client.post("/api/timer/stop", json={"notes": {"a": 1}})
    assert r.status_code in (200, 400), f"got {r.status_code}"
    with clock(5)[1]:
        assert client.post("/api/timer/stop", json=["a list"]).status_code == 200   # no notes, still saves

def test_abandoned_timer_does_not_log_a_30_hour_session(user):
    """Close the tab mid-practice, come back tomorrow, press Stop."""
    client, _ = user
    client.post("/api/timer/start")
    with clock(30 * 3600)[1]:
        r = client.post("/api/timer/stop").get_json()
    assert r["time_spent"] <= 4 * 3600, f"saved a {r['time_spent'] / 3600:.0f} h session"

def test_replaying_an_old_cookie_does_not_save_the_session_twice(user):
    client, uid = user
    client.post("/api/timer/start")
    cookie = client.get_cookie("session").value
    with clock(600)[1]:
        client.post("/api/timer/stop")
        client.set_cookie("session", cookie)          # e.g. two tabs, or the back button
        client.post("/api/timer/stop")
    assert len(db.getSessions(uid)) == 1, "the same practice was saved twice"



# ---------------------------------------------------------------- uploads
def test_upload_musicxml_end_to_end(user):
    client, uid = user
    r = upload(client, "air.musicxml", AIR, title="My Air", composer="Bach")
    assert r.status_code == 302 and "/practice?piece=" in r.location
    pid = int(r.location.split("=")[1])
    assert db.getMidi(pid)["midi"][:4] == b"MThd"
    x = client.get(f"/api/pieces/{pid}/musicxml")
    assert x.status_code == 200 and b"score-partwise" in x.data

@known("Broken features: .mxl served zipped")
def test_upload_mxl_is_served_as_musicxml_the_page_can_draw(user, tmp_path):
    from music21 import converter
    mxl = tmp_path / "air.mxl"
    converter.parse(AIR).write("mxl", fp=mxl)
    client, _ = user
    r = upload(client, "air.mxl", mxl.read_bytes())
    assert r.status_code == 302 and "/practice?piece=" in r.location, r.location
    served = client.get(f"/api/pieces/{r.location.split('=')[1]}/musicxml")
    assert not served.data.startswith(b"PK"), "a zipped .mxl is served as application/xml; the page can't draw it"

def test_upload_broken_xml_shows_error(user):
    r = upload(user[0], "bad.musicxml", b"<score-partwise><oops")
    assert r.status_code == 302 and "error=" in r.location

def test_upload_error_message_survives_hash_in_filename(user):
    r = upload(user[0], "etude #3.musicxml", b"<nope")
    assert "#" not in r.location.split("?", 1)[1] or "%23" in r.location, f"message cut at '#': {r.location}"

def test_upload_with_empty_filename_is_handled(user):
    r = upload(user[0], "", AIR)
    assert r.status_code in (302, 400), f"got {r.status_code}"

def test_upload_without_file_is_400(user):
    assert user[0].post("/api/pieces", data={}, content_type="multipart/form-data").status_code == 400

@pytest.mark.parametrize("name", ["notes.txt", "score.gif", "score.webp", "IMG_0001.HEIC", "noextension"])
def test_unsupported_types_never_reach_homr(user, name, monkeypatch):
    """On Render (PHOTO_UPLOADS=off) homr would need ~1 GB on a 512 MB box."""
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    import homr_omr, pdfToMidi
    called = mock.Mock(side_effect=RuntimeError("homr ran"))
    monkeypatch.setattr(pdfToMidi, "run_homr", called)
    r = upload(user[0], name, b"hello")
    assert not called.called, f"{name} was sent to homr"
    assert r.status_code in (302, 400)

def fake_claude(xml_text):
    final = mock.Mock(content=[mock.Mock(text=xml_text)])
    stream = mock.MagicMock()
    stream.__enter__.return_value.get_final_message.return_value = final
    client = mock.Mock()
    client.beta.messages.stream.return_value = stream
    return mock.patch("anthropic.Anthropic", return_value=client)

def tiny_pdf(tmp_path):
    import pymupdf
    doc = pymupdf.open(); doc.new_page().insert_text((72, 72), "score"); p = tmp_path / "x.pdf"; doc.save(p)
    return p.read_bytes()

@pytest.mark.parametrize("name", ["score.pdf", "SCORE.PDF", "photo.png", "PHOTO.JPG", "Photo.Jpeg"])
def test_photo_uploads_via_claude(user, name, monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    monkeypatch.setenv("ANTHROPIC_API_KEY", " sk-test\n")
    data = tiny_pdf(tmp_path) if name.lower().endswith(".pdf") else b"\x89PNG fake"
    with fake_claude("Here you go:\n" + AIR.decode()):
        r = upload(user[0], name, data)
    assert "/practice?piece=" in r.location, f"{name}: {r.location}"

def test_photos_use_the_cheap_model_and_never_fall_back(user, monkeypatch):
    monkeypatch.setenv("PHOTO_UPLOADS", "off"); monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with fake_claude(AIR.decode()) as made:
        upload(user[0], "photo.png", b"\x89PNG")
    sent = made.return_value.beta.messages.stream.call_args.kwargs
    assert sent["model"] == "claude-haiku-5-5" and "fallbacks" not in sent

def test_claude_truncated_reply_shows_error(user, monkeypatch):
    monkeypatch.setenv("PHOTO_UPLOADS", "off"); monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with fake_claude(AIR.decode()[:3000]):
        r = upload(user[0], "photo.png", b"\x89PNG")
    assert "error=" in r.location

def test_photo_declined_without_key_on_free_box(user, monkeypatch):
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    r = upload(user[0], "photo.png", b"\x89PNG")
    assert "error=" in r.location and "1%20GB" in r.location

def test_upload_size_is_limited():
    assert flask_app.config.get("MAX_CONTENT_LENGTH"), "no upload size limit: one big upload fills RAM/disk on a 512 MB box"

def test_uploads_clean_up_temp_files(user):
    before = len(glob.glob(tempfile.gettempdir() + "/tmp*"))
    for _ in range(5):
        upload(user[0], "air.musicxml", AIR)
    after = len(glob.glob(tempfile.gettempdir() + "/tmp*"))
    assert after - before == 0, f"{after - before} temp dirs left behind by 5 uploads"


# ---------------------------------------------------------------- /api/midi and /api/transcribe
def test_api_midi_from_musicxml(guest):
    r = upload(guest, "air.musicxml", AIR, url="/api/midi")
    assert r.status_code == 200 and r.data[:4] == b"MThd"

def test_api_midi_bad_type_is_400(guest):
    assert upload(guest, "notes.txt", b"hi", url="/api/midi").status_code == 400

def test_api_midi_respects_photo_uploads_off(guest, monkeypatch):
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    import pdfToMidi
    called = mock.Mock(side_effect=RuntimeError("homr ran"))
    monkeypatch.setattr(pdfToMidi, "run_homr", called)
    upload(guest, "photo.png", b"\x89PNG", url="/api/midi")
    assert not called.called, "/api/midi sends photos to homr even with PHOTO_UPLOADS=off"

@known("Crashes: /api/transcribe without key")
def test_api_transcribe_without_openai_key_fails_cleanly(guest):
    r = upload(guest, "take.webm", b"\x1aE\xdf\xa3", url="/api/transcribe")
    assert r.status_code != 500, "500 instead of a clear 'transcription not configured' error"


# ---------------------------------------------------------------- recordings
def test_record_and_play_back(user):
    client, uid = user
    pid = db.addPiece(uid, "Rec", xml=AIR)
    rid = upload(client, "take.webm", b"WEBMDATA", url=f"/api/pieces/{pid}/recordings").get_json()["id"]
    r = client.get(f"/api/recordings/{rid}")
    assert r.status_code == 200 and r.data == b"WEBMDATA"

def test_cannot_record_on_or_play_others_pieces(user):
    client, _ = user
    other = make_user(); pid = db.addPiece(other, "x", xml=AIR); rid = db.addRecording(pid, b"private")
    assert upload(client, "t.webm", b"x", url=f"/api/pieces/{pid}/recordings").status_code == 404
    assert client.get(f"/api/recordings/{rid}").status_code == 404

def test_recording_without_file_is_400(user):
    client, uid = user
    pid = db.addPiece(uid, "Rec", xml=AIR)
    assert client.post(f"/api/pieces/{pid}/recordings").status_code == 400

@known("Broken features: playback always audio/webm")
def test_safari_recording_plays_back_with_its_own_type(user):
    """Safari's MediaRecorder makes audio/mp4; playback is always labelled audio/webm."""
    client, uid = user
    pid = db.addPiece(uid, "Rec", xml=AIR)
    rid = client.post(f"/api/pieces/{pid}/recordings",
                      data={"file": (io.BytesIO(b"\0\0\0\x18ftypM4A "), "take.mp4", "audio/mp4")},
                      content_type="multipart/form-data").get_json()["id"]
    assert client.get(f"/api/recordings/{rid}").mimetype == "audio/mp4"

def test_empty_recording_is_rejected(user):
    client, uid = user
    pid = db.addPiece(uid, "Rec", xml=AIR)
    r = upload(client, "take.webm", b"", url=f"/api/pieces/{pid}/recordings")
    assert r.status_code == 400, "an empty take is saved as a recording"


# ---------------------------------------------------------------- home & progress numbers
def test_home_and_progress_show_saved_practice(user):
    client, uid = user
    pid = db.addPiece(uid, "Counted", xml=AIR)
    db.addSession(uid, 3 * 3600 + 25 * 60, piece_ids=[pid])
    home = client.get("/home").get_data(as_text=True)
    assert "3h 25m" in home and "205 min practiced" in home and "1 day<" in home
    prog = client.get("/progress").get_data(as_text=True)
    assert 'height: 100%' in prog

def test_progress_with_no_sessions(user):
    prog = user[0].get("/progress").get_data(as_text=True)
    assert "0,150 600,150" in prog
    assert "No practice saved yet" in prog

def test_progress_offers_to_save_time_left_on_the_timer(user):
    client, uid = user
    with client.session_transaction() as s:
        s["timer_elapsed"] = 25 * 60   # paused by leaving the practice page
    prog = client.get("/progress").get_data(as_text=True)
    assert "25 min</strong> on the practice timer" in prog and 'id="save-timer"' in prog
    client.post("/api/timer/stop")
    prog = client.get("/progress").get_data(as_text=True)
    assert 'id="save-timer"' not in prog and "No practice saved yet" not in prog
    assert [s["time_spent"] for s in db.getSessions(uid)] == [25 * 60]


# ---------------------------------------------------------------- sign-in
def test_google_login_without_keys_goes_home(guest):
    r = guest.get("/login/google")
    assert r.status_code == 302 and r.location.endswith("/home")

def test_google_callback_garbage_goes_home(guest):
    r = guest.get("/auth/google?code=junk&state=junk")
    assert r.status_code == 302 and r.location.endswith("/home")

@known("Crashes: duplicate email on sign-in")
def test_google_sign_in_with_unverified_email_that_already_exists(guest):
    """A second Google account (or unverified one) whose email matches an existing user."""
    email = f"dupe{time.time()}@test.dev"
    db.getOrCreateGoogleUser(sub="first", name="A", email=email, email_verified=True)
    info = {"userinfo": {"sub": f"second-{time.time()}", "email": email, "email_verified": False, "name": "B"}}
    with mock.patch.object(appmod.google, "authorize_access_token", return_value=info):
        r = guest.get("/auth/google")
    assert r.status_code != 500


# ---------------------------------------------------------------- ml/api.py run alone (README: python ml/api.py)
@known("Broken features: ml/api.py alone has no LoginManager")
def test_ml_api_runs_alone():
    code = ("import sys; sys.path.insert(0, %r); from flask import Flask; import api as m;"
            "a = Flask('x'); a.register_blueprint(m.api); m.database.init_db();"
            "print(a.test_client().get('/api/pieces').status_code)") % str(REPO / "ml")
    out = subprocess.run([sys.executable, "-c", code], cwd=WORK, capture_output=True, text=True)
    assert out.stdout.strip() == "200", (out.stdout + out.stderr)[-400:]


# ---------------------------------------------------------------- ml/text.py
@pytest.mark.parametrize("said, expect", [
    ("let's take it at 90 bpm", {"tempo": 90}),
    ("this is in b flat minor", {"key": "B flat minor"}),
    ("it's in F sharp major", {"key": "F sharp major"}),
    ("six eight time", {"time_signature": "6/8"}),
    ("three four", {"time_signature": "3/4"}),
    ("play it in 3/4", {"time_signature": "3/4"}),
    pytest.param("two two time", {"time_signature": "2/2"}, marks=known("ml/text.py: no 'two two'")),
    pytest.param("tempo one hundred twenty", {"tempo": 120}, marks=known("ml/text.py: no spelled-out tempos")),
    ("at 60 beats per minute", {"tempo": 60}),
])
def test_text_process(said, expect):
    from ml import text
    got = text.process(said)
    assert {k: got[k] for k in expect} == expect


# ---------------------------------------------------------------- playback (player.js)
@pytest.mark.parametrize("path", ["/player.js", "/Tone.js", "/samples/piano/C4.mp3", "/samples/piano/Fs7.mp3", "/samples/piano/A0.mp3"])
def test_player_files_are_served(guest, path):
    r = guest.get(path)
    assert r.status_code == 200 and len(r.data) > 1000
