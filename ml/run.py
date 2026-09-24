"""Usage: python ml/run.py clip.mp3   -> prints transcript + music info as JSON"""
import json, sys
from transcribe import transcribe
from text import process

r = transcribe(sys.argv[1])
print(json.dumps({**r, "music": process(r["text"])}, indent=2))
