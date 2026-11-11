"""Continue as guest: each guest gets its own user and its own copy of the starter pieces."""
from support import db, flask_app, make_user


def guest_login():
    client = flask_app.test_client()
    assert client.get("/login/guest").status_code == 302
    with client.session_transaction() as s:
        return client, int(s["_user_id"])


def template_ids():
    return [p["id"] for p in db.getPieces(db.starterUser())]


def test_two_guests_are_separate_users_with_their_own_pieces():
    (_, a), (_, b) = guest_login(), guest_login()
    assert a != b and not {db.demoUser(), db.starterUser()} & {a, b}
    pa, pb = db.getPieces(a), db.getPieces(b)
    assert len(pa) == len(pb) == len(template_ids()) > 0
    assert not {p["id"] for p in pa} & {p["id"] for p in pb}


def test_a_guest_deleting_a_piece_leaves_the_template_and_other_guests_alone():
    (client, a), (_, b) = guest_login(), guest_login()
    before_template, before_b = template_ids(), db.getPieces(b)
    piece = db.getPieces(a)[0]["id"]
    assert client.delete(f"/api/pieces/{piece}").status_code == 204
    assert piece not in [p["id"] for p in db.getPieces(a)]
    assert template_ids() == before_template
    assert db.getPieces(b) == before_b
    assert db.getXML(before_b[0]["id"])


def test_a_guest_cannot_delete_the_template_or_another_guests_piece():
    (client, _), (_, b) = guest_login(), guest_login()
    for piece in template_ids()[:1] + [db.getPieces(b)[0]["id"]]:
        assert client.delete(f"/api/pieces/{piece}").status_code == 404
    assert flask_app.test_client().delete(f"/api/pieces/{template_ids()[0]}").status_code == 401


def test_guests_skip_onboarding():
    client, _ = guest_login()
    assert client.get("/home").status_code == 200


def test_old_guests_are_removed_with_their_data():
    client, old = guest_login()
    piece = db.getPieces(old)[0]["id"]
    db.addSession(old, 60, piece_ids=[piece])
    db.addRecording(piece, b"take")
    db.addRep(db.addSection(piece, 1, 2)[0], 1)
    with db.get_db() as database:
        database.execute("UPDATE Users SET date_registered = '2000-01-01 00:00:00' WHERE id = ?", (old,))
    real = make_user()
    with db.get_db() as database:
        database.execute("UPDATE Users SET date_registered = '2000-01-01 00:00:00' WHERE id = ?", (real,))
    _, fresh = guest_login()
    assert db.getUserById(old) is None and db.getPieces(old) == []
    assert db.getUserById(fresh) and db.getUserById(real)
    assert template_ids()


def test_a_new_signup_gets_the_starter_pieces():
    from app import give_starter_piece
    uid = make_user()
    give_starter_piece(uid)
    pieces = db.getPieces(uid)
    assert sorted(p["title"] for p in pieces) == ["Air", "Minuet in G", "Ode to Joy"]
    assert not {p["id"] for p in pieces} & set(template_ids())


def test_seeding_adds_missing_starters_once():
    from app import seed_starter_pieces
    for p in db.getPieces(db.starterUser()):
        if p["title"] != "Air":
            db.deletePiece(db.starterUser(), p["id"])
    seed_starter_pieces()
    seed_starter_pieces()
    assert sorted(p["title"] for p in db.getPieces(db.starterUser())) == ["Air", "Minuet in G", "Ode to Joy"]
