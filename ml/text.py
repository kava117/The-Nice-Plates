"""Transcript text -> music info. Plain regex, no API call."""
import re

WORD_NUM = {"two": 2, "three": 3, "four": 4, "six": 6, "eight": 8}


def process(text):
    """Return {"tempo": bpm or None, "key": "G major" or None, "time_signature": "3/4" or None}"""
    t = text.lower()
    tempo = re.search(r"(\d{2,3})\s*(?:bpm|beats per minute)", t)
    key = re.search(r"\b([a-g])\s?(sharp|flat)?\s+(major|minor)\b", t)
    sig = re.search(r"\b(\d)\s*/\s*(\d)\b|\b(two|three|four|six)[\s-](four|eight)\b", t)
    return {
        "tempo": int(tempo[1]) if tempo else None,
        "key": " ".join(filter(None, key.groups())).capitalize() if key else None,
        "time_signature": f"{sig[1]}/{sig[2]}" if sig and sig[1] else f"{WORD_NUM[sig[3]]}/{WORD_NUM[sig[4]]}" if sig else None,
    }
