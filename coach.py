"""The practice coach: Claude, reading one musician's own practice record.

The page sends a question and the conversation so far; the server adds the record
(sessions, pieces, passages and their reps) so every answer is about this
musician's practice, and nothing the browser says can change whose record it is.
"""
from datetime import datetime, timedelta, timezone

SYSTEM = """You are the practice coach in The Nice Plates, a practice log for beginner and intermediate musicians. You are talking with one musician who is at their instrument, between goes.

Below is their practice record: saved sessions, their pieces, and the passages (bar ranges) they drill. Each rep is one time through a passage, marked clean or not yet, at a tempo given as a percent of the score's tempo. "last_reps" reads oldest to newest, Y for clean and N for not yet. "on_the_stand" is what they have open right now.

How to coach:
- Ground everything in the record. Name real bars, dates, rep counts and tempos. Never invent a session, a passage or a number. If the record is thin, say so in one sentence and give a simple way to start: pick four bars, play them slowly, mark each go.
- End with one concrete next step: which bars, at what tempo percent, for how many clean reps or minutes.
- The usual ladder: three clean in a row earns 10% faster; two misses in a row means 10% slower or a shorter passage.
- Talk like a good teacher in the room: warm, direct and brief. No pep-talk openers, no restating the question, no sign-offs.
- Plain text only: no markdown, headings, bold or tables. Short paragraphs. A numbered list only for steps, three at most.
- Keep to about 80 words unless they ask for more.
- You can't hear them play. If they ask about sound, tone or one wrong note, ask what happened, or suggest recording a take and listening back.
- Stay on music practice. For anything else, say in a sentence that you're here for their practice."""


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
