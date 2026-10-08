"""python ml/test_text.py   (no API key needed)"""
from text import process

assert process("Minuet in G major at 80 bpm, three four") == {"tempo": 80, "key": "G major", "time_signature": "3/4"}
assert process("F sharp minor, 4/4, 120 beats per minute")["key"] == "F sharp minor"
assert process("hello there") == {"tempo": None, "key": None, "time_signature": None}
print("ok")
