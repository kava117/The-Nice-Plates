"""The Review page, and the limit on saved takes."""
from support import AIR, db, login, make_user


def test_review_is_in_the_menu_and_loads(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", "J. S. Bach", xml=AIR)
    home = client.get("/home").get_data(as_text=True)
    assert 'href="/review"' in home
    page = client.get(f"/review?piece={pid}")
    assert page.status_code == 200
    assert "Recordings" in page.get_data(as_text=True)


def test_review_with_no_pieces_says_so(user):
    client, _ = user
    page = client.get("/review").get_data(as_text=True)
    assert "Nothing to review yet" in page


def test_review_lists_the_takes_and_the_passages(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", "J. S. Bach", xml=AIR)
    db.addRecording(pid, b"audio", "Morning run")
    sid = client.post(f"/api/pieces/{pid}/sections", json={"start": 2, "end": 5}).get_json()["id"]
    client.post(f"/api/sections/{sid}/reps", json={"clean": True, "tempo": 90})
    page = client.get(f"/review?piece={pid}").get_data(as_text=True)
    assert "Morning run" in page
    assert "2–5" in page and "90 %" in page


def test_review_ignores_someone_elses_piece(user):
    client, uid = user
    mine = db.addPiece(uid, "Mine", None, xml=AIR)
    theirs = db.addPiece(make_user(), "Theirs", None, xml=AIR)
    page = client.get(f"/review?piece={theirs}").get_data(as_text=True)
    assert "Mine" in page and "Theirs" not in page
    assert client.get("/review?piece=abc").status_code == 200


def test_only_the_latest_takes_are_kept(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", None, xml=AIR)
    other = db.addPiece(uid, "Other", None, xml=AIR)
    db.addRecording(other, b"x", "Other piece")
    for i in range(db.MAX_TAKES + 3):
        db.addRecording(pid, b"audio", f"take {i}")
    names = [t["name"] for t in db.getRecordings(uid, pid)]
    assert len(names) == db.MAX_TAKES
    assert names[0] == f"take {db.MAX_TAKES + 2}" and "take 0" not in names   # the oldest went
    assert len(db.getRecordings(uid, other)) == 1   # another piece keeps its own


def test_default_take_names_keep_counting_past_the_limit(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", None, xml=AIR)
    import io
    for _ in range(db.MAX_TAKES + 2):
        r = client.post(f"/api/pieces/{pid}/recordings", data={"file": (io.BytesIO(b"audio"), "t.webm")}, content_type="multipart/form-data")
        assert r.status_code == 200
    assert r.get_json()["name"] == f"Air, take {db.MAX_TAKES + 2}"


def test_delete_a_take(user):
    client, uid = user
    pid = db.addPiece(uid, "Air", None, xml=AIR)
    take = db.addRecording(pid, b"audio", "Gone")
    other = make_user()
    assert client.delete(f"/api/recordings/{take}").status_code == 204
    assert db.getRecordings(uid, pid) == []
    assert client.delete(f"/api/recordings/{take}").status_code == 404
    theirs = db.addRecording(db.addPiece(other, "Theirs", None, xml=AIR), b"audio", "Theirs")
    assert client.delete(f"/api/recordings/{theirs}").status_code == 404
    assert db.getRecording(other, theirs) is not None


def test_practice_is_only_for_playing(user):
    client, uid = user
    db.addPiece(uid, "Air", None, xml=AIR)
    page = client.get("/practice").get_data(as_text=True)
    for gone in ('id="coach"', 'id="take-pick"', 'id="cursor-prev"', 'id="take-name"'):
        assert gone not in page
    for kept in ('id="play"', 'id="record"', 'id="tempo"', 'id="metro"', 'id="live-lane"'):
        assert kept in page
