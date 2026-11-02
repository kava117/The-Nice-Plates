"""Change 3 check: pages stay fast while uploads convert, and conversions run one at a time.

Run from the repo root (Python 3.11 env):
    gunicorn --pythonpath tests/load upload_while_browsing:app --workers 1 --threads 4 --timeout 300 --bind 127.0.0.1:8123
    python tests/load/upload_while_browsing.py

As a gunicorn app, every conversion sleeps 8 s first (standing in for a 35 s homr run).
As a script, it starts two uploads, times /home and /library meanwhile, then prints the upload times.
Expect pages well under 1 s and upload times of about 8 s and 16 s.
"""
import sys, threading, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AIR = (REPO / "music-app-home" / "AirOnG.musicxml").read_bytes()
BASE = "http://127.0.0.1:8123"

if __name__ != "__main__":   # loaded by gunicorn
    sys.path.insert(0, str(REPO))
    from app import app
    import pdfToMidi
    real = pdfToMidi._to_musicxml
    def slow(src, work):
        time.sleep(8)
        return real(src, work)
    pdfToMidi._to_musicxml = slow
else:
    import requests
    took = []
    def upload():
        t = time.time()
        requests.post(BASE + "/api/pieces", files={"file": ("air.musicxml", AIR)}, allow_redirects=False)
        took.append(round(time.time() - t, 1))
    uploads = [threading.Thread(target=upload) for _ in range(2)]
    for u in uploads:
        u.start()
    time.sleep(1)
    for path in ("/home", "/library", "/home"):
        t = time.time()
        status = requests.get(BASE + path).status_code
        print(path, status, f"{time.time() - t:.3f} s")
    for u in uploads:
        u.join()
    print("upload times", sorted(took))
