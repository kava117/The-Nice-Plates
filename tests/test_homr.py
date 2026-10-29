"""homr on its own box (homr_service/, reached through HOMR_URL), and Claude stepping in when it can't read a page."""
import io, subprocess, sys
from pathlib import Path
from unittest import mock

import pytest
import requests

from support import AIR, REPO
from test_limits import fake_claude, upload

sys.path.insert(0, str(REPO / "homr_service"))
import homr_omr, server


@pytest.fixture
def homr_box(monkeypatch):
    """The site as it runs on Render with homr on Azure. Returns what the box was sent."""
    monkeypatch.setenv("PHOTO_UPLOADS", "off")
    monkeypatch.setenv("HOMR_URL", "https://homr.example/ \n")   # pasted, with a slash and a newline
    monkeypatch.setenv("HOMR_TOKEN", " t0ken\n")
    sent = []
    def post(url, files, headers, timeout):
        name, f = files["file"]
        sent.append({"url": url, "name": name, "auth": headers["Authorization"], "data": f.read()})
        return mock.Mock(ok=True, content=AIR)
    monkeypatch.setattr(homr_omr.requests, "post", post)
    return sent


# ---------------------------------------------------------------- the site, with HOMR_URL
def test_photos_go_to_the_homr_box_before_claude(user, homr_box, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with fake_claude("unused") as claude:
        r = upload(user[0], "photo.png", b"\x89PNG fake")
    assert "/practice?piece=" in r.location, r.location
    assert homr_box == [{"url": "https://homr.example/read", "name": "photo.png", "auth": "Bearer t0ken", "data": b"\x89PNG fake"}]
    assert not claude.called
    assert user[0].get(f"/api/pieces/{r.location.split('=')[1]}/musicxml").data == AIR


def test_each_pdf_page_goes_to_the_box_and_comes_back_as_one_score(user, homr_box, tmp_path):
    import pymupdf
    doc = pymupdf.open(); doc.new_page(); doc.new_page(); pdf = tmp_path / "two.pdf"; doc.save(pdf)
    r = upload(user[0], "two.pdf", pdf.read_bytes())
    assert "/practice?piece=" in r.location, r.location
    assert [page["name"] for page in homr_box] == ["page_000.png", "page_001.png"]
    served = user[0].get(f"/api/pieces/{r.location.split('=')[1]}/musicxml").data
    assert served.count(b"<measure ") == 2 * AIR.count(b"<measure ")


@pytest.mark.parametrize("trouble", [
    requests.ConnectionError("no such host"),                                  # deleted, out of credit, or a typo in HOMR_URL
    mock.Mock(ok=False, status_code=422, text="ValueError: No staffs found"),  # homr ran and couldn't read the page
    mock.Mock(ok=False, status_code=401, text="wrong or missing token"),
    mock.Mock(ok=True, content=b"<html>an error page</html>"),                 # not MusicXML
], ids=["unreachable", "homr-failed", "wrong-token", "not-musicxml"])
def test_claude_reads_it_when_the_box_cant(user, homr_box, monkeypatch, trouble):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    box = mock.Mock(side_effect=trouble) if isinstance(trouble, Exception) else mock.Mock(return_value=trouble)
    monkeypatch.setattr(homr_omr.requests, "post", box)
    with fake_claude(AIR.decode()) as claude:
        r = upload(user[0], "photo.png", b"\x89PNG")
    assert box.called and claude.called
    assert "/practice?piece=" in r.location, r.location


def test_without_a_key_a_failed_read_is_a_plain_message(user, homr_box, monkeypatch):
    monkeypatch.setattr(homr_omr.requests, "post", mock.Mock(side_effect=requests.ConnectionError("no such host")))
    r = upload(user[0], "photo.png", b"\x89PNG")
    assert "/library?error=Could%20not%20read%20photo.png" in r.location


def test_api_midi_reads_photos_on_the_box(guest, homr_box):
    r = upload(guest, "photo.png", b"\x89PNG", url="/api/midi")
    assert r.status_code == 200 and r.data[:4] == b"MThd" and len(homr_box) == 1


def test_on_a_laptop_claude_backs_up_homr_too(user, monkeypatch):
    import pdfToMidi
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(pdfToMidi, "run_homr", mock.Mock(side_effect=RuntimeError("homr not found")))
    with fake_claude(AIR.decode()) as claude:
        r = upload(user[0], "photo.png", b"\x89PNG")
    assert claude.called and "/practice?piece=" in r.location, r.location


# ---------------------------------------------------------------- the box itself (homr_service/server.py)
@pytest.fixture
def box(monkeypatch):
    monkeypatch.setenv("HOMR_TOKEN", "t0ken")
    return server.app.test_client()


def fake_homr(writes=AIR, code=0):
    def run(cmd, **kw):
        if writes:
            Path(cmd[1]).with_suffix(".musicxml").write_bytes(writes)
        return subprocess.CompletedProcess(cmd, code, "", "ValueError: No staffs found" if code else "")
    return mock.patch.object(server.subprocess, "run", side_effect=run)


def page(name="page.png", token="t0ken"):
    return {"data": {"file": (io.BytesIO(b"\x89PNG"), name)}, "content_type": "multipart/form-data",
            "headers": {"Authorization": f"Bearer {token}"}}


def test_box_is_up(box):
    assert box.get("/").status_code == 200


def test_box_reads_a_page(box):
    with fake_homr() as run:
        r = box.post("/read", **page())
    assert r.status_code == 200 and r.data == AIR
    assert run.call_args.args[0][0] == "homr"


@pytest.mark.parametrize("token", ["", "wrong", "t0ken-and-more"])
def test_box_wants_the_token(box, token):
    with fake_homr() as run:
        assert box.post("/read", **page(token=token)).status_code == 401
    assert not run.called


def test_box_with_no_token_set_lets_nobody_in(box, monkeypatch):
    monkeypatch.delenv("HOMR_TOKEN")
    with fake_homr() as run:
        assert box.post("/read", **page(token="")).status_code == 401
    assert not run.called


@pytest.mark.parametrize("name", ["score.pdf", "notes.txt", "noextension", ""])
def test_box_takes_page_images_only(box, name):
    with fake_homr() as run:
        assert box.post("/read", **page(name=name)).status_code == 400
    assert not run.called


def test_box_says_why_homr_couldnt_read_it(box):
    with fake_homr(writes=None, code=1):
        r = box.post("/read", **page())
    assert r.status_code == 422 and b"No staffs found" in r.data
