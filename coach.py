"""The practice coach: Claude, reading one musician's own practice record.

The page sends a question and the conversation so far; the server adds the record
(sessions, pieces, passages and their reps) so every answer is about this
musician's practice, and nothing the browser says can change whose record it is.
"""
import json, logging, os, re, threading, time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

MODEL = "claude-haiku-5-5"   # cheap and quick; COACH_MODEL swaps it
MAX_MESSAGE = 1000           # characters in one question
MAX_TURNS = 12               # earlier questions and answers sent back with a new one
PER_HOUR = 40                # questions one account can ask in an hour

SYSTEM = """You are the practice coach in The Nice Plates, a practice log for beginner and intermediate musicians. You are talking with one musician who is at their instrument, between goes.

Below is their practice record: saved sessions, their pieces, and the passages (bar ranges) they drill. Each rep is one time through a passage, marked clean or not yet, at a tempo given as a percent of the score's tempo. "last_reps" reads oldest to newest, Y for clean and N for not yet. "on_the_stand" is what they have open right now.

They read your answer from the music stand, so the shape matters:
- First line: the next step, one sentence on its own, starting with a verb: which bars, at what tempo percent, until how many clean reps. If they asked a question of fact, the first line answers it instead.
- Then a blank line and at most two short sentences on why, from the record.
- About 60 words in all, unless they ask for more. Plain text only: no markdown, headings, bold or tables. A numbered list only for steps, three at most.

How to coach:
- Ground everything in the record. Name real bars, dates, rep counts and tempos. Never invent a session, a passage or a number. If the record is thin, say so in one sentence and give a simple way to start: pick four bars, play them slowly, mark each go.
- The usual ladder: three clean in a row earns 10% faster; two misses in a row means 10% slower or a shorter passage.
- Talk like a good teacher in the room: warm, direct and brief. No pep-talk openers, no restating the question, no sign-offs.
- You can't hear them play. If they ask about sound, tone or one wrong note, ask what happened, or suggest recording a take and listening back.
- Stay on music practice. For anything else, say in a sentence that you're here for their practice."""


class Unavailable(Exception):
    """the coach can't answer; the message is for the musician, the cause goes to the log"""
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def read_history(value):
    """the conversation so far as Claude messages, or None if it isn't one"""
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    turns = value[-MAX_TURNS:]
    if turns and isinstance(turns[0], dict) and turns[0].get("role") == "assistant":
        turns = turns[1:]   # the cut landed on an answer: start at a question
    for i, turn in enumerate(turns):
        if not (isinstance(turn, dict) and turn.get("role") == ("user", "assistant")[i % 2]
                and isinstance(turn.get("content"), str) and 0 < len(turn["content"]) <= 4000):
            return None
    if turns and turns[-1]["role"] != "assistant":
        return None
    return [{"role": t["role"], "content": t["content"]} for t in turns]


_asked, _lock = defaultdict(deque), threading.Lock()

def allowed(uid, now=None):
    """counts this question against the account's hour; False once it's used up"""
    now = time.time() if now is None else now
    with _lock:
        asked = _asked[uid]
        while asked and now - asked[0] > 3600:
            asked.popleft()
        if len(asked) >= PER_HOUR:
            return False
        asked.append(now)
        return True


def minutes(seconds):
    return round((seconds or 0) / 60)

def bars(start, end):
    return f"bar {start}" if start == end else f"bars {start}-{end}"

def record(log, total_sessions, total_seconds, streak, piece=None, passage=None, timer=0):
    """the musician's practice as Claude reads it: short keys, no ids, dates as days"""
    today = datetime.now(timezone.utc).date()
    week = (today - timedelta(days=6)).isoformat()
    return {
        "today": today.isoformat(),
        "totals": {
            "sessions": total_sessions,
            "hours": round(total_seconds / 3600, 1),
            "days_in_a_row": streak,
            "minutes_last_7_days": sum(minutes(s["seconds"]) for s in log["sessions"] if s["date"][:10] >= week),
        },
        "recent_sessions": [
            {"date": s["date"][:10], "minutes": minutes(s["seconds"]), "pieces": s["pieces"],
             **({"notes": s["notes"][:300]} if s["notes"] else {})}
            for s in log["sessions"]
        ],
        "pieces": [
            {"title": p["title"], "composer": p["composer"], "score_bpm": p["bpm"], "minutes_practised": minutes(p["seconds"]),
             "passages": [
                 {"bars": bars(s["start"], s["end"]), "reps": s["reps"], "clean": s["clean"],
                  "last_reps": "".join("Y" if r["clean"] else "N" for r in s["recent"][-10:]),
                  "best_clean_tempo_percent": s["best_tempo"],
                  "last_practised": s["last_practiced"] and s["last_practiced"][:10]}
                 for s in p["passages"]
             ]}
            for p in log["pieces"][:12]
        ],
        "on_the_stand": {
            "piece": piece and piece["title"],
            "passage": passage and bars(*passage),
            "minutes_on_the_timer": minutes(timer),
        },
    }


def plain(text):
    """what's left if the model slips into markdown anyway"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"^#+\s*", "", text, flags=re.M).strip()


def ask(practice, history, message):
    """one answer from Claude, about this practice record"""
    key, workspace = (os.environ.get(k, "").strip() for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"))
    if not key:
        raise Unavailable("The coach isn't switched on for this site yet.")
    try:
        import anthropic   # in ml/requirements.txt, not the bare web app's
    except ImportError:
        logging.warning("coach: ANTHROPIC_API_KEY is set but the anthropic package isn't installed")
        raise Unavailable("The coach isn't switched on for this site yet.")
    client = anthropic.Anthropic(api_key=key, default_headers={"anthropic-workspace-id": workspace} if workspace else {},
                                 timeout=45, max_retries=2)
    try:
        reply = client.messages.create(
            model=os.environ.get("COACH_MODEL", MODEL), max_tokens=700,
            system=SYSTEM + "\n\nPractice record:\n" + json.dumps(practice, ensure_ascii=False),
            messages=[*history, {"role": "user", "content": message}],
        )
    except anthropic.RateLimitError as e:
        logging.warning("coach: rate limited: %s", e)
        raise Unavailable("The coach is busy. Ask again in a few seconds.", 429)
    except Exception as e:   # a bad key, no credit, no network: the musician can't fix any of these
        logging.exception("coach: Claude call failed")
        raise Unavailable("The coach can't answer right now. Try again in a minute.", 502) from e
    used = getattr(reply, "usage", None)
    logging.warning("Coach answered with %s: %s tokens in, %s out", getattr(reply, "model", "?"),
                    getattr(used, "input_tokens", "?"), getattr(used, "output_tokens", "?"))   # what each question cost, in Render's log
    text = plain("".join(b.text for b in reply.content if getattr(b, "type", "") == "text"))
    return text or "I don't have anything useful on that. Try asking about a passage or today's practice."
