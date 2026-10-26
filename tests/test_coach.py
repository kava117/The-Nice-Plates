"""The coach: Claude answers from the musician's own practice record, and only theirs."""
import json
from unittest import mock

import pytest

import coach
from support import AIR, db, login, flask_app, make_user


@pytest.fixture(autouse=True)
def fresh_hour():
    coach._asked.clear()


def fake_claude(text="Bars 12-16 at 80%, three clean in a row."):
    reply = mock.Mock(content=[mock.Mock(type="text", text=text)], model="claude-haiku-5-5",
                      usage=mock.Mock(input_tokens=900, output_tokens=40))
    client = mock.Mock()
    client.messages.create.return_value = reply
    return mock.patch("anthropic.Anthropic", return_value=client)


def practised(uid):
    """a piece with a passage, a few reps and a saved session"""
    pid = db.addPiece(uid, "Air", "J. S. Bach", bpm=60, xml=AIR)
    sid, _ = db.addSection(pid, 12, 16)
    for clean, tempo in [(False, 80), (True, 80), (True, 80)]:
        db.addRep(sid, clean, tempo)
    db.addSession(uid, 25 * 60, "left hand slow", piece_ids=[pid])
    return pid


def sent(made):
    return made.return_value.messages.create.call_args.kwargs


def test_answers_from_the_musicians_own_record(user, monkeypatch):
    client, uid = user
    monkeypatch.setenv("ANTHROPIC_API_KEY", " sk-test\n")
    pid = practised(uid)
    with fake_claude() as made:
        r = client.post("/api/coach", json={"message": "What next?", "piece_id": pid, "passage": {"start": 12, "end": 16}})
    assert r.status_code == 200 and r.get_json()["reply"].startswith("Bars 12-16")
    call = sent(made)
    assert call["model"] == "claude-haiku-5-5"
    assert call["messages"] == [{"role": "user", "content": "What next?"}]
    practice = json.loads(call["system"].split("Practice record:\n", 1)[1])
    passage = practice["pieces"][0]["passages"][0]
    assert (passage["bars"], passage["reps"], passage["clean"], passage["last_reps"]) == ("bars 12-16", 3, 2, "NYY")
    assert practice["totals"]["sessions"] == 1 and practice["recent_sessions"][0]["notes"] == "left hand slow"
    assert practice["on_the_stand"] == {"piece": "Air", "passage": "bars 12-16", "minutes_on_the_timer": 0}
    assert made.call_args.kwargs["api_key"] == "sk-test"   # a pasted key's newline is trimmed


def test_someone_elses_piece_is_not_read(user, monkeypatch):
    client, _ = user
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    theirs = practised(make_user())
    with fake_claude() as made:
        client.post("/api/coach", json={"message": "Help", "piece_id": theirs, "passage": {"start": 12, "end": 16}})
    practice = sent(made)["system"]
    assert "left hand slow" not in practice and '"piece": null' in practice and '"passage": null' in practice


def test_the_conversation_goes_back_with_the_question(user, monkeypatch):
    client, _ = user
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    history = [{"role": "user", "content": "What next?"}, {"role": "assistant", "content": "Bars 12-16."}]
    with fake_claude() as made:
        client.post("/api/coach", json={"message": "How fast?", "history": history})
    assert sent(made)["messages"] == history + [{"role": "user", "content": "How fast?"}]


def test_a_long_conversation_is_cut_at_a_question(user, monkeypatch):
    client, _ = user
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    history = [{"role": ("user", "assistant")[i % 2], "content": f"turn {i}"} for i in range(coach.MAX_TURNS + 1)]
    history.append({"role": "assistant", "content": "last answer"})
    with fake_claude() as made:
        client.post("/api/coach", json={"message": "And now?", "history": history[1:]})
    messages = sent(made)["messages"]
    assert messages[0]["role"] == "user" and len(messages) <= coach.MAX_TURNS + 1
