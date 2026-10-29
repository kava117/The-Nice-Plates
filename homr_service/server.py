"""homr as a web service: POST one page image to /read, get homr's MusicXML back.

homr peaks around 1.7 GB on a 300 DPI page, more than the site's free 512 MB box,
so it runs here and the site sends it pages (HOMR_URL). Locally:
    HOMR_TOKEN=dev gunicorn server:app --bind 127.0.0.1:8003
"""
import hmac, os, subprocess, tempfile, threading
from pathlib import Path

from flask import Flask, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024   # the site's own upload limit
IMAGES = {".png", ".jpg", ".jpeg"}
ONE_AT_A_TIME = threading.Semaphore(1)   # two homr runs at once would need ~3.5 GB


@app.get("/")
def alive():
    return "homr is up\n"


@app.post("/read")
def read():
    token = os.environ.get("HOMR_TOKEN", "").strip()   # unset means nobody gets in, so a public URL can't spend the credits
    sent = request.headers.get("Authorization", "").encode()
    if not token or not hmac.compare_digest(sent, f"Bearer {token}".encode()):
        return "wrong or missing token\n", 401
    upload = request.files.get("file")
    suffix = Path(upload.filename or "").suffix.lower() if upload else ""
    if suffix not in IMAGES:
        return "send one page as a PNG or JPG in the form field 'file'\n", 400
    with tempfile.TemporaryDirectory() as tmp, ONE_AT_A_TIME:
        image = Path(tmp) / f"page{suffix}"
        upload.save(image)
        run = subprocess.run(["homr", str(image)], capture_output=True, text=True, timeout=240)
        xml = image.with_suffix(".musicxml")   # where homr writes it
        if run.returncode or not xml.exists():
            return (run.stderr or run.stdout)[-2000:] or "homr wrote nothing\n", 422
        return xml.read_bytes(), {"Content-Type": "application/vnd.recordare.musicxml+xml"}
