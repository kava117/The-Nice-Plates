"""One test per "Done when" box in FIX_FIRST.md."""
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
