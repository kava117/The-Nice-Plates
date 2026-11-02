"""The first five fixes: a real SECRET_KEY, upload guards, gunicorn threads, the log out link,
and a practice timer that can be trusted."""
import pytest
from flask.sessions import SecureCookieSessionInterface

from support import AIR, boot, db, flask_app, make_user


# ---------------------------------------------------------------- 1. Real SECRET_KEY
def cookie_for(user_id, key):
    """A session cookie for user_id, signed with key."""
    real = flask_app.secret_key
    flask_app.secret_key = key
    try:
        return SecureCookieSessionInterface().get_signing_serializer(flask_app).dumps({"_user_id": str(user_id), "_fresh": True})
    finally:
        flask_app.secret_key = real


def test_cookie_signed_with_dev_only_is_rejected(monkeypatch):
    monkeypatch.setattr(flask_app, "secret_key", "a-real-random-secret")
    victim = make_user()
    db.addPiece(victim, "Victim's private piece", xml=AIR)
    attacker = flask_app.test_client()
    attacker.set_cookie("session", cookie_for(victim, "dev-only"))
    assert "Victim&#39;s private piece" not in attacker.get("/library").get_data(as_text=True)


def test_cookie_signed_with_the_real_key_still_works(monkeypatch):
    monkeypatch.setattr(flask_app, "secret_key", "a-real-random-secret")
    me = make_user()
    db.addPiece(me, "My own piece", xml=AIR)
    client = flask_app.test_client()
    client.set_cookie("session", cookie_for(me, "a-real-random-secret"))
    assert "My own piece" in client.get("/library").get_data(as_text=True)


def test_render_without_secret_key_refuses_to_boot():
    out = boot({"RENDER": "true"})
    assert out.returncode != 0
    assert "SECRET_KEY is not set" in out.stderr


def test_render_with_secret_key_boots():
    assert boot({"RENDER": "true", "SECRET_KEY": "x" * 64}).returncode == 0


def test_local_run_without_secret_key_still_boots():
    out = boot({})
    assert out.returncode == 0, out.stderr[-500:]


# ---------------------------------------------------------------- 2. Upload guards
import glob, io, tempfile
from unittest import mock

import pytest


def upload(client, name, data, url="/api/pieces"):
    return client.post(url, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


@pytest.fixture
def no_homr(monkeypatch):
    import pdfToMidi
    called = mock.Mock(side_effect=RuntimeError("homr ran"))
    monkeypatch.setattr(pdfToMidi, "run_homr", called)
    return called


@pytest.mark.parametrize("url", ["/api/pieces", "/api/midi"])
@pytest.mark.parametrize("name", ["score.gif", "score.webp", "IMG_0001.HEIC", "noextension", ""])
def test_unknown_types_are_rejected_and_homr_never_starts(guest, no_homr, url, name):
    r = upload(guest, name, b"hello", url)
    assert not no_homr.called
    if url == "/api/midi":
        assert r.status_code == 400 and r.get_json()["error"]
    else:
        assert r.status_code == 302 and "/library?error=" in r.location


@pytest.mark.parametrize("url", ["/api/pieces", "/api/midi"])
def test_photos_rejected_when_photo_uploads_off_and_no_key(guest, no_homr, monkeypatch, url):
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    r = upload(guest, "photo.png", b"\x89PNG", url)
    assert not no_homr.called
    assert r.status_code == 400 if url == "/api/midi" else "1%20GB" in r.location


def test_photos_go_to_claude_when_off_with_a_key_but_midi_still_rejects(guest, no_homr, monkeypatch):
    from test_limits import fake_claude
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with fake_claude(AIR.decode()):
        assert "/practice?piece=" in upload(guest, "photo.png", b"\x89PNG").location
    assert upload(guest, "photo.png", b"\x89PNG", "/api/midi").status_code == 400
    assert not no_homr.called


def test_25_mb_upload_gets_too_large_message(guest):
    big = b"x" * (25 * 1024 * 1024)
    r = upload(guest, "big.musicxml", big)
    assert r.status_code == 302 and "too%20large" in r.location
    r = upload(guest, "big.musicxml", big, "/api/midi")
    assert r.status_code == 413 and "too large" in r.get_json()["error"]


def test_five_uploads_leave_no_temp_folders(guest, no_homr):
    before = set(glob.glob(tempfile.gettempdir() + "/*"))
    for name, data in [("air.musicxml", AIR), ("bad.musicxml", b"<oops"), ("photo.png", b"\x89PNG"),
                       ("air.musicxml", AIR), ("score.gif", b"GIF")]:
        upload(guest, name, data)
    upload(guest, "air.musicxml", AIR, "/api/midi")
    assert set(glob.glob(tempfile.gettempdir() + "/*")) - before == set()


# ---------------------------------------------------------------- 3. Gunicorn threads
def test_two_uploads_at_once_convert_one_at_a_time(monkeypatch):
    """With 4 threads in one process, a second homr run would go over 512 MB. tests/load/ checks page speed."""
    import threading, time
    import pdfToMidi
    running, most = [0], [0]
    real = pdfToMidi._to_musicxml
    def slow(src, work):
        running[0] += 1; most[0] = max(most[0], running[0])
        time.sleep(0.3)
        running[0] -= 1
        return real(src, work)
    monkeypatch.setattr(pdfToMidi, "_to_musicxml", slow)
    uploads = [threading.Thread(target=upload, args=(flask_app.test_client(), "air.musicxml", AIR)) for _ in range(3)]
    for u in uploads: u.start()
    for u in uploads: u.join()
    assert most[0] == 1


# ---------------------------------------------------------------- 4. Log out link
def test_log_out_in_the_top_bar_signs_you_out(user):
    client, uid = user
    db.addPiece(uid, "Only mine", xml=AIR)
    assert 'href="/logout">Log out' in client.get("/library").get_data(as_text=True)
    client.get("/logout")
    page = client.get("/library").get_data(as_text=True)
    assert "Only mine" not in page and "Sign in with Google" in page and ">Log out<" not in page


def test_guest_never_sees_log_out(guest):
    for path in ("/home", "/library", "/settings", "/practice"):
        page = guest.get(path).get_data(as_text=True)
        assert ">Log out<" not in page and 'href="/logout"' not in page and 'href="/login/google"' in page


# ---------------------------------------------------------------- 5. Trustworthy practice timer

from support import appmod, clock


def test_reload_shows_the_running_timer(user):
    client, _ = user
    client.post("/api/timer/start")
    with clock(90)[1]:
        state = client.get("/api/practice/state").get_json()   # what practice.html fetches on load
    assert state["running"] and state["elapsed"] >= 90


def test_time_away_is_not_counted(user):
    client, uid = user
    c, patch = clock()
    with patch:
        client.post("/api/timer/start"); c.offset += 30
        client.post("/api/timer/pause"); c.offset += 60   # pagehide beacon, then a minute in the library
        state = client.get("/api/practice/state").get_json()
        assert not state["running"] and state["elapsed"] == 30   # the page shows Resume
        client.post("/api/timer/start"); c.offset += 10
        assert client.post("/api/timer/stop").get_json()["time_spent"] == 40
    assert [s["time_spent"] for s in db.getSessions(uid)] == [40]


def test_beacon_pause_needs_no_json(user):
    client, _ = user
    client.post("/api/timer/start")
    r = client.post("/api/timer/pause", data=b"", content_type="text/plain;charset=UTF-8")   # what sendBeacon sends
    assert r.status_code == 200 and not r.get_json()["running"]


@pytest.mark.parametrize("policy", ["drop", "cap"])
def test_five_hour_timer_follows_over_cap(user, monkeypatch, policy):
    monkeypatch.setattr(appmod, "OVER_CAP", policy)
    client, uid = user
    client.post("/api/timer/start")
    with clock(5 * 3600)[1]:
        r = client.post("/api/timer/stop").get_json()
    saved = [s["time_spent"] for s in db.getSessions(uid)]
    if policy == "drop":
        assert r["saved_session_id"] is None and r["too_long"] and saved == []
    else:
        assert r["time_spent"] == appmod.MAX_SESSION and saved == [appmod.MAX_SESSION]
    assert not client.get("/api/practice/state").get_json()["running"]


def test_stopping_the_same_timer_twice_saves_one_row(user):
    client, uid = user
    client.post("/api/timer/start")
    cookie = client.get_cookie("session").value   # a second tab
    with clock(600)[1]:
        first = client.post("/api/timer/stop").get_json()
        client.set_cookie("session", cookie)
        second = client.post("/api/timer/stop").get_json()
    assert len(db.getSessions(uid)) == 1
    assert first["saved_session_id"] == second["saved_session_id"] is not None


def test_a_new_timer_after_stopping_is_a_new_session(user):
    client, uid = user
    for _ in range(2):
        client.post("/api/timer/start")
        with clock(60)[1]:
            client.post("/api/timer/stop")
    assert len(db.getSessions(uid)) == 2


def test_home_and_progress_totals_match_sessions(user):
    client, uid = user
    for seconds in (120, 300):
        client.post("/api/timer/start")
        with clock(seconds)[1]:
            client.post("/api/timer/stop")
    with db.get_db() as con:
        total = con.execute("SELECT SUM(time_spent) FROM Sessions WHERE user_id = ?", (uid,)).fetchone()[0]
    assert total == 420
    totals = []
    real = appmod.render_template
    def spy(name, **kw):
        totals.append(kw.get("total", (kw.get("totals") or [None])[-1]))
        return real(name, **kw)
    with mock.patch.object(appmod, "render_template", spy):
        client.get("/home"); client.get("/progress")
    assert totals == [420, 420]


@pytest.mark.skipif(db.POSTGRES, reason="builds an old SQLite file")
def test_migration_keeps_rows_in_a_db_from_main(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", str(tmp_path / "old.db"))
    db.init_db()   # the schema main shipped: no migrations, user_version 0
    uid = db.getOrCreateGoogleUser(sub="old", name="Old", email="old@test.dev", email_verified=True)["id"]
    with db.get_db() as con:
        con.execute("INSERT INTO Sessions (user_id, time_spent) VALUES (?, 50), (?, 70)", (uid, uid))
    db.migrate(); db.migrate()   # runs once, then is a no-op
    with db.get_db() as con:
        rows = con.execute("SELECT time_spent, timer_id FROM Sessions ORDER BY id").fetchall()
        assert con.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert [tuple(r) for r in rows] == [(50, None), (70, None)]
    assert db.addSession(uid, 10, timer_id="t") == db.addSession(uid, 10, timer_id="t")
