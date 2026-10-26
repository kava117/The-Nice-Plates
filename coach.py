"""The practice coach: Claude, reading one musician's own practice record.

The page sends a question and the conversation so far; the server adds the record
(sessions, pieces, passages and their reps) so every answer is about this
musician's practice, and nothing the browser says can change whose record it is.
"""
from datetime import datetime, timedelta, timezone

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
