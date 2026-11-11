"""Deleting a piece from the library: it goes with its passages, reps, recordings and session links; sessions stay."""
from support import AIR, db, flask_app, login, make_user


def test_delete_a_piece_and_what_hangs_off_it(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", "J. S. Bach", xml=AIR)
    sid = client.post(f"/api/pieces/{pid}/sections", json={"start": 1, "end": 4}).get_json()["id"]
    client.post(f"/api/sections/{sid}/reps", json={"clean": True})
    db.addRecording(pid, b"audio")
    db.addSession(uid, 120, piece_ids=[pid])
    client.post("/api/practice/piece", json={"piece_id": pid})

    assert client.delete(f"/api/pieces/{pid}").status_code == 204
    assert db.getPieceForUser(uid, pid) is None
    assert db.getSectionRecord(sid) is None
    assert db.getRecordings(uid, pid) == []
    assert db.getPieceSeconds(uid) == {}
    assert sum(s["time_spent"] for s in db.getSessions(uid)) == 120   # practice time is kept
    assert client.get("/api/practice/state").get_json()["piece_id"] is None
    assert client.delete(f"/api/pieces/{pid}").status_code == 404


def test_cannot_delete_someone_elses_piece(user):
    client, _ = user
    other = make_user()
    theirs = db.addPiece(other, "Air", "J. S. Bach", xml=AIR)
    assert client.delete(f"/api/pieces/{theirs}").status_code == 404
    assert db.getPieceForUser(other, theirs) is not None


def test_library_has_a_delete_button_and_confirm_dialog(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", "J. S. Bach", xml=AIR)
    page = client.get("/library").get_data(as_text=True)
    assert f'data-delete="{pid}"' in page
    assert 'id="delete-dialog"' in page
