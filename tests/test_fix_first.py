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
