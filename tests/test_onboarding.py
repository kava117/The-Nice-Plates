"""Onboarding: signed-in users pick four playing levels; Settings shows them."""
from support import db, flask_app, login, make_user

LEVELS = dict(rhythm_level=3, intonation_level=1, dynamics_level=4, range_level=2)


def test_a_new_account_is_sent_to_onboarding():
    client = login(flask_app.test_client(), make_user(onboarded=False))
    r = client.get("/home")
    assert r.status_code == 302 and r.headers["Location"].endswith("/onboarding")


def test_a_guest_is_not():
    assert flask_app.test_client().get("/home").status_code == 200


def test_saving_levels_lets_them_in_and_shows_on_settings():
    client = login(flask_app.test_client(), make_user(onboarded=False))
    r = client.post("/onboarding", data=LEVELS)
    assert r.status_code == 302 and r.headers["Location"].endswith("/home")
    html = client.get("/settings").get_data(as_text=True)
    assert "Syncopation" in html
    assert "Finding the notes" in html
    assert "Full expression" in html
    assert "Just outside" in html


def test_the_scores_are_on_the_user_row():
    uid = make_user(onboarded=False)
    db.setUserProficiency(uid, **LEVELS)
    got = db.getUserProficiency(uid)
    assert got["rhythm_level"] == 3 and got["onboarded_at"]
