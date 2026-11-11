"""Settings: rename yourself, delete your account."""
from support import db, flask_app
from test_guests import guest_login


def test_renaming_saves_and_rejects_blank_names():
    client, uid = guest_login()
    assert client.patch("/api/account", json={"name": "  Ana  "}).json == {"name": "Ana"}
    assert db.getUserById(uid)["name"] == "Ana"
    assert client.patch("/api/account", json={"name": "   "}).status_code == 400
    assert client.patch("/api/account", json={"name": "x" * 61}).status_code == 400
    assert db.getUserById(uid)["name"] == "Ana"


def test_signed_out_visitors_cannot_rename_or_delete():
    client = flask_app.test_client()
    assert client.patch("/api/account", json={"name": "x"}).status_code == 401
    assert client.delete("/api/account").status_code == 401


def test_deleting_an_account_removes_it_and_signs_out():
    (client, uid), (_, other) = guest_login(), guest_login()
    assert client.delete("/api/account").status_code == 204
    assert db.getUserById(uid) is None and db.getPieces(uid) == []
    assert db.getUserById(other) and db.getPieces(other)
    with client.session_transaction() as s:
        assert "_user_id" not in s
