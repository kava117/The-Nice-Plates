"""Shared setup for the tests: an isolated working folder and database, and small helpers.

Imported by conftest.py before any test module, so app.py is only ever imported once, here.
"""
import os, sys, tempfile, time
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="niceplates-test-"))

# never use a developer's real keys or settings
ENV_KEYS = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SECRET_KEY", "RENDER", "ANTHROPIC_API_KEY",
            "ANTHROPIC_WORKSPACE_ID", "CLAUDE_MODEL", "PHOTO_UPLOADS", "OPENAI_API_KEY", "HOMR_URL", "HOMR_TOKEN")
for k in ENV_KEYS:
    os.environ.pop(k, None)

os.chdir(WORK)   # niceplates.db is created in the cwd
sys.path.insert(0, str(REPO))
with mock.patch("dotenv.load_dotenv"):   # ...and never read the repo's .env
    import app as appmod
from database import database as db

flask_app = appmod.app
flask_app.config["TESTING"] = False   # keep real error handling: 500s show up as 500s
AIR = (REPO / "music-app-home" / "AirOnG.musicxml").read_bytes()


def make_user(n=[0]):
    n[0] += 1
    return db.getOrCreateGoogleUser(sub=f"sub-{n[0]}-{time.time()}", name=f"User {n[0]}",
                                    email=f"user{n[0]}.{time.time()}@test.dev", email_verified=True)["id"]


def login(client, uid):
    with client.session_transaction() as s:
        s["_user_id"] = str(uid)
        s["_fresh"] = True
    return client


class Clock:
    """Stands in for app.py's `time` module only, so cookies and logging keep the real clock."""
    def __init__(self, offset=0.0): self.offset = offset
    def time(self): return _real_time() + self.offset

_real_time = time.time

def clock(offset=0.0):
    c = Clock(offset)
    return c, mock.patch.object(appmod, "time", c)


def boot(env):
    """Import app.py in a fresh Python with exactly these settings; returns the CompletedProcess."""
    import subprocess
    clean = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    # empty strings stop load_dotenv from filling these in from the repo's .env
    clean.update({k: "" for k in ENV_KEYS}, **env)
    return subprocess.run([sys.executable, "-c", "import app"], cwd=WORK, capture_output=True, text=True,
                          env={**clean, "PYTHONPATH": str(REPO)})
