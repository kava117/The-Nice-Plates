"""Passages: the bars a musician picks out of a piece to practice (Sections), and each time through them (Section_Reps)."""
import sqlite3

from support import AIR, db, flask_app, login, make_user


def piece_for(uid):
    return db.addPiece(uid, "Air", "J. S. Bach", xml=AIR)


def test_make_list_and_delete_a_passage(user):
    client, uid = user
    pid = piece_for(uid)
    made = client.post(f"/api/pieces/{pid}/sections", json={"start": 12, "end": 16})
    assert made.status_code == 201
    passage = made.get_json()
    assert (passage["start"], passage["end"], passage["reps"], passage["recent"]) == (12, 16, 0, [])

    client.post(f"/api/pieces/{pid}/sections", json={"start": 1, "end": 4})
    assert [(p["start"], p["end"]) for p in client.get(f"/api/pieces/{pid}/sections").get_json()] == [(1, 4), (12, 16)]

    assert client.delete(f"/api/sections/{passage['id']}").status_code == 204
    assert [(p["start"], p["end"]) for p in client.get(f"/api/pieces/{pid}/sections").get_json()] == [(1, 4)]


def test_the_same_bars_are_one_passage(user):
    client, uid = user
    pid = piece_for(uid)
    first = client.post(f"/api/pieces/{pid}/sections", json={"start": 5, "end": 8})
    again = client.post(f"/api/pieces/{pid}/sections", json={"start": 5, "end": 8})
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.get_json()["id"] == again.get_json()["id"]
    assert len(client.get(f"/api/pieces/{pid}/sections").get_json()) == 1


def test_one_bar_is_a_passage(user):
    client, uid = user
    assert client.post(f"/api/pieces/{piece_for(uid)}/sections", json={"start": 3, "end": 3}).status_code == 201


def test_bad_bars_are_400(user):
    client, uid = user
    pid = piece_for(uid)
    for body in ({}, {"start": 5}, {"start": 8, "end": 5}, {"start": 0, "end": 2}, {"start": "a", "end": 2},
                 {"start": 1, "end": 10**30}, [1, 2], "not json"):
        r = client.post(f"/api/pieces/{pid}/sections", json=body)
        assert r.status_code == 400, (body, r.status_code)


def test_reps_build_a_record_and_undo_takes_one_back(user):
    client, uid = user
    pid = piece_for(uid)
    sid = client.post(f"/api/pieces/{pid}/sections", json={"start": 12, "end": 16}).get_json()["id"]
    for clean, tempo in ((False, 60), (True, 60), (True, 70), (True, 70)):
        record = client.post(f"/api/sections/{sid}/reps", json={"clean": clean, "tempo": tempo}).get_json()
    assert (record["reps"], record["clean"], record["best_tempo"]) == (4, 3, 70)
    assert [r["clean"] for r in record["recent"]] == [False, True, True, True]   # oldest first
    assert record["last_practiced"]

    undone = client.delete(f"/api/sections/{sid}/reps/last").get_json()
    assert (undone["reps"], undone["clean"]) == (3, 2)
    assert [r["tempo"] for r in undone["recent"]] == [60, 60, 70]

    with sqlite3.connect(db.DB_NAME) as con:   # the old counter column keeps up
        assert con.execute("SELECT times_practiced FROM Sections WHERE id = ?", (sid,)).fetchone()[0] == 3


def test_undo_with_no_reps_is_harmless(user):
    client, uid = user
    sid = client.post(f"/api/pieces/{piece_for(uid)}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    r = client.delete(f"/api/sections/{sid}/reps/last")
    assert r.status_code == 200 and r.get_json()["reps"] == 0


def test_recent_reps_are_capped(user):
    client, uid = user
    sid = client.post(f"/api/pieces/{piece_for(uid)}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    for _ in range(db.RECENT_REPS + 5):
        record = client.post(f"/api/sections/{sid}/reps", json={"clean": True}).get_json()
    assert record["reps"] == db.RECENT_REPS + 5 and len(record["recent"]) == db.RECENT_REPS


def test_bad_reps_are_400(user):
    client, uid = user
    sid = client.post(f"/api/pieces/{piece_for(uid)}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    for body in ({}, {"clean": "yes"}, {"clean": 1}, {"clean": True, "tempo": 5}, {"clean": True, "tempo": 70.5},
                 {"clean": True, "tempo": "fast"}, [True], "not json"):
        r = client.post(f"/api/sections/{sid}/reps", json=body)
        assert r.status_code == 400, (body, r.status_code)


def test_deleting_a_passage_deletes_its_reps(user):
    client, uid = user
    sid = client.post(f"/api/pieces/{piece_for(uid)}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    client.post(f"/api/sections/{sid}/reps", json={"clean": True})
    client.delete(f"/api/sections/{sid}")
    with sqlite3.connect(db.DB_NAME) as con:
        assert con.execute("SELECT COUNT(*) FROM Section_Reps WHERE section_id = ?", (sid,)).fetchone()[0] == 0


def test_a_passage_can_be_selected_for_the_session(user):
    client, uid = user
    pid = piece_for(uid)
    sid = client.post(f"/api/pieces/{pid}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    state = client.post("/api/practice/section", json={"section_id": sid}).get_json()
    assert (state["piece_id"], state["section_id"]) == (pid, sid)
    client.delete(f"/api/sections/{sid}")
    assert client.get("/api/practice/state").get_json()["section_id"] is None


def test_other_peoples_passages_are_404(user):
    client, _ = user
    other = make_user()
    their_piece = piece_for(other)
    their_sid = login(flask_app.test_client(), other).post(
        f"/api/pieces/{their_piece}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    assert client.get(f"/api/pieces/{their_piece}/sections").status_code == 404
    assert client.post(f"/api/pieces/{their_piece}/sections", json={"start": 3, "end": 4}).status_code == 404
    assert client.post(f"/api/sections/{their_sid}/reps", json={"clean": True}).status_code == 404
    assert client.delete(f"/api/sections/{their_sid}/reps/last").status_code == 404
    assert client.delete(f"/api/sections/{their_sid}").status_code == 404
    assert db.getSectionRecord(their_sid) is not None


def test_guests_practice_as_the_demo_user(guest):
    pid = piece_for(db.demoUser())
    assert guest.post(f"/api/pieces/{pid}/sections", json={"start": 1, "end": 2}).status_code in (200, 201)


def test_reopening_the_piece_keeps_its_passage_and_another_piece_drops_it(user):
    """The practice page posts its piece on every load; that must not forget the passage left open last time."""
    client, uid = user
    pid, other = piece_for(uid), piece_for(uid)
    sid = client.post(f"/api/pieces/{pid}/sections", json={"start": 1, "end": 2}).get_json()["id"]
    client.post("/api/practice/section", json={"section_id": sid})
    assert client.post("/api/practice/piece", json={"piece_id": pid}).get_json()["section_id"] == sid
    assert client.post("/api/practice/piece", json={"piece_id": other}).get_json()["section_id"] is None


def test_practice_without_a_piece_opens_the_latest_one(user):
    """The sidebar's Practice link has no ?piece=; passages need a saved piece, so the page gets the latest one."""
    client, uid = user
    assert "|| null;" in client.get("/practice").get_data(as_text=True)   # no pieces yet: the demo score
    older, newer = piece_for(uid), piece_for(uid)
    db.touchPiece(newer)
    page = client.get("/practice")
    assert page.status_code == 200 and f'|| {newer};' in page.get_data(as_text=True)
    assert f'|| null;' in client.get(f"/practice?piece={older}").get_data(as_text=True)   # an explicit piece wins
