from flask import Flask, abort, jsonify, redirect, url_for, render_template, request, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from database import database
from datetime import date, datetime, timedelta, timezone
from itertools import accumulate
import os, secrets, time
from urllib.parse import quote
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from ml.api import api

load_dotenv() #loads the .env file and the secrets stored within

# Pages are Jinja templates in music-app-home/templates/ (they share header.html,
# sidebar.html and footer.html). Static files (styles.css, theme.js, images) are
# still served from music-app-home/ at the site root, so relative links work.
app = Flask(
    __name__,
    static_folder="music-app-home",
    static_url_path="",
    template_folder="music-app-home/templates",
)
app.register_blueprint(api)
secret = os.environ.get("SECRET_KEY")
if not secret and os.environ.get("RENDER"):   # Render sets RENDER; "dev-only" is public, so anyone could sign in as anyone
    raise RuntimeError("SECRET_KEY is not set. Add it in the Render dashboard under Environment.")
app.secret_key = secret or "dev-only"   # fine on a laptop only
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                  MAX_CONTENT_LENGTH=20 * 1024 * 1024)   # uploads and recordings; 20 MB is 20+ minutes of Opus audio
portNum = 8001

oauth = OAuth(app)
google = oauth.register(
    name = "google",
    client_id = os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs = {"scope": "openid email profile"},
)

with app.app_context():
    database.init_db()
    database.migrate()
    if not database.getPieces(database.demoUser()):   # free hosting wipes the disk on restart: keep one piece to try
        database.addPiece(database.demoUser(), "Air", "J. S. Bach", xml=open(app.static_folder + "/AirOnG.musicxml", "rb").read())

#handles logging in/out and passing credentials when required
login_manager = LoginManager(app)

#needed by the login manager to verify a user
class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]

@login_manager.user_loader
def load_user(user_id):
    row = database.getUserById(int(user_id))
    return User(row) if row else None

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return jsonify(error="login required"), 401
    return redirect(url_for("index"))

def user_id():
    return current_user.id if current_user.is_authenticated else database.demoUser()

@app.errorhandler(413)
def too_large(e):
    message = "File too large (max 20 MB)."
    if request.path == "/api/pieces":   # the library's upload form
        return redirect("/library?error=" + quote(message))
    return jsonify(error=message), 413

# Makes {{ year }} available to every template (used by footer.html).
@app.context_processor
def inject_year():
    me = current_user if current_user.is_authenticated else database.getUserById(database.demoUser())
    return {"year": date.today().year, "me": me}


# 
# the "current_user" data object has these attributes available on logged-in pages:
# .id = database id value
# .name = their google name
# .email = their email
# THE ABOVE 3 DO NOT EXIST FOR LOGGED OUT USERS
# .is_authenticated = basically if theyre logged in
# .is_active = if their account is active or banned (always true now)
# .is_anonymous = not relevant
# .get_id() = returns their database id as a string


# Flask session cookie info
PRACTICE_KEYS = ("current_piece_id", "selected_section_id", "timer_started_at", "timer_elapsed", "session_piece_ids", "timer_id")
TIMER_KEYS = ("timer_started_at", "timer_elapsed", "session_piece_ids", "timer_id")

MAX_SESSION = 4 * 3600   # a timer running longer than this was forgotten, not practiced
OVER_CAP = "drop"        # or "cap": save MAX_SESSION instead. The team still has to pick one.

# removes keys
def clear_practice_state():
    for key in PRACTICE_KEYS:
        session.pop(key, None)

#gets an actual number for the time spent practicing
def timer_seconds():
    elapsed = session.get("timer_elapsed", 0)
    started = session.get("timer_started_at")
    if started is not None:
        elapsed += time.time() - started
    return int(elapsed)

# returns a dict of the relevant cookie keys
def practice_state():
    return {
        "piece_id": session.get("current_piece_id"),
        "section_id": session.get("selected_section_id"),
        "running": session.get("timer_started_at") is not None,
        "elapsed": timer_seconds(),
    }

# returns the data of a single key
def read_id(data, key):
    try:
        n = int(data.get(key))
    except (TypeError, ValueError, AttributeError):
        return None
    return n if 0 < n < 2**63 else None   # SQLite integers are 64-bit: a bigger id crashed the query

# only track pieces once a timer exists (running or paused with banked time)
def remember_piece(piece_id):
    if session.get("timer_started_at") is not None or session.get("timer_elapsed"):
        session["session_piece_ids"] = sorted(set(session.get("session_piece_ids", []) + [piece_id]))



#API ROUTES

#gets the practice state of the user
@app.route("/api/practice/state")
def api_state():
    return jsonify(practice_state())

#pick a practice piece
@app.route("/api/practice/piece", methods=["POST"])
def api_select_piece():
    piece_id = read_id(request.get_json(silent=True) or {}, "piece_id")
    if piece_id is None or not database.getPieceForUser(user_id(), piece_id):
        return jsonify(error="piece not found"), 404
    if session.get("current_piece_id") != piece_id:
        session.pop("selected_section_id", None)   # a passage of another piece no longer applies
    session["current_piece_id"] = piece_id
    remember_piece(piece_id)
    return jsonify(practice_state())

#pick a practice section
@app.route("/api/practice/section", methods=["POST"])
def api_select_section():
    section_id = read_id(request.get_json(silent=True) or {}, "section_id")
    section = database.getSectionForUser(user_id(), section_id) if section_id else None
    if not section:
        return jsonify(error="section not found"), 404
    session["selected_section_id"] = section["id"]
    session["current_piece_id"] = section["piece_id"]   # a section implies its piece
    remember_piece(section["piece_id"])
    return jsonify(practice_state())


# ---- Passages: bars picked out of a piece to practice (Sections), and each time through them (Section_Reps) ----
MAX_BAR = 10000

def read_bars(data):
    """(start, end) bar numbers from {"start": 12, "end": 16}, or None if they don't make a passage"""
    try:
        start, end = int(data.get("start")), int(data.get("end"))
    except (TypeError, ValueError, AttributeError):
        return None
    return (start, end) if 1 <= start <= end <= MAX_BAR else None

def my_section(section_id):
    return database.getSectionForUser(user_id(), section_id) or abort(404)

@app.route("/api/pieces/<int:piece_id>/sections")
def api_sections(piece_id):
    database.getPieceForUser(user_id(), piece_id) or abort(404)
    return jsonify(database.getSections(user_id(), piece_id))

@app.route("/api/pieces/<int:piece_id>/sections", methods=["POST"])
def api_add_section(piece_id):
    database.getPieceForUser(user_id(), piece_id) or abort(404)
    bars = read_bars(request.get_json(silent=True) or {})
    if not bars:
        return jsonify(error=f"start and end must be bar numbers from 1 to {MAX_BAR}, start first"), 400
    section_id, created = database.addSection(piece_id, *bars)
    return jsonify(database.getSectionRecord(section_id)), 201 if created else 200

@app.route("/api/sections/<int:section_id>", methods=["DELETE"])
def api_delete_section(section_id):
    my_section(section_id)
    database.deleteSection(section_id)
    if session.get("selected_section_id") == section_id:
        session.pop("selected_section_id")
    return "", 204

@app.route("/api/sections/<int:section_id>/reps", methods=["POST"])
def api_add_rep(section_id):
    my_section(section_id)
    data = request.get_json(silent=True)
    clean, tempo = (data.get("clean"), data.get("tempo")) if isinstance(data, dict) else (None, None)
    if not isinstance(clean, bool):
        return jsonify(error="clean must be true or false"), 400
    if tempo is not None and not (isinstance(tempo, int) and 10 <= tempo <= 400):
        return jsonify(error="tempo must be a whole percent from 10 to 400"), 400
    database.addRep(section_id, clean, tempo)
    return jsonify(database.getSectionRecord(section_id))

@app.route("/api/sections/<int:section_id>/reps/last", methods=["DELETE"])
def api_undo_rep(section_id):
    my_section(section_id)
    database.deleteLastRep(section_id)
    return jsonify(database.getSectionRecord(section_id))

#begin tracking a sessions length
@app.route("/api/timer/start", methods=["POST"])
def api_timer_start():
    if session.get("timer_started_at") is None:         # dont reset timer if already started
        if not session.get("timer_elapsed"):            # a new timer, not a resume: its id lets it be saved only once
            session["timer_id"] = secrets.token_hex(8)
        session["timer_started_at"] = time.time()
        piece_id = session.get("current_piece_id")
        if piece_id: #initializes session piece list
            session["session_piece_ids"] = sorted(set(session.get("session_piece_ids", []) + [piece_id]))
    return jsonify(practice_state())

#pause a session (settings change, page navigation, etc.)
@app.route("/api/timer/pause", methods=["POST"])
def api_timer_pause():
    if session.get("timer_started_at") is not None:
        session["timer_elapsed"] = timer_seconds()      # keep track of currently elapsed time to return to or store later
        session["timer_started_at"] = None
    return jsonify(practice_state())

#stop the timer, and save the session to the database
@app.route("/api/timer/stop", methods=["POST"])
def api_timer_stop():
    total = timer_seconds()
    too_long = total > MAX_SESSION and OVER_CAP == "drop"
    if OVER_CAP == "cap":
        total = min(total, MAX_SESSION)
    if too_long:
        total = 0
    data = request.get_json(silent=True)
    notes = data.get("notes") if isinstance(data, dict) else None
    if notes is not None and not isinstance(notes, str):
        return jsonify(error="notes must be text"), 400
    notes = notes[:2000] if notes else None
    session_id = None
    if total > 0:
        session_id = database.addSession(
            user_id(), total, notes,
            piece_ids=session.get("session_piece_ids", []),
            timer_id=session.get("timer_id"),
        )
    for key in TIMER_KEYS:
        session.pop(key, None)
    return jsonify(saved_session_id=session_id, time_spent=total, too_long=too_long, **practice_state())


# ==================================================================
# LOADING ALL OF OUR HTML PAGES
# ================================================================== 

@app.route("/")
@app.route("/index")
def index():
    return render_template("index.html")

def utc_today():  # SQLite stamps sessions in UTC
    return datetime.now(timezone.utc).date()

def streak(sessions):  # days in a row with a saved session, counting back from today
    days, day, n = {s["date"][:10] for s in sessions}, utc_today(), 0
    while day.isoformat() in days:
        n, day = n + 1, day - timedelta(days=1)
    return n

@app.route("/home")
def home():
    sessions = database.getSessions(user_id())
    return render_template("home.html", pieces=database.getPieces(user_id())[:3], seconds=database.getPieceSeconds(user_id()),
                           total=sum(s["time_spent"] for s in sessions), streak=streak(sessions))

@app.route("/library")
def library():
    return render_template("library.html", pieces=database.getPieces(user_id()))

@app.route("/progress")
def progress():
    sessions = database.getSessions(user_id())
    monday = utc_today() - timedelta(days=utc_today().weekday())
    per_day = [sum(s["time_spent"] for s in sessions if s["date"][:10] == (monday + timedelta(days=i)).isoformat()) for i in range(7)]
    return render_template("progress.html", per_day=per_day, totals=list(accumulate(s["time_spent"] for s in reversed(sessions))),
                           pieces=len(database.getPieces(user_id())), practiced=len(database.getPieceSeconds(user_id())))

@app.route("/settings")
def settings():
    return render_template("settings.html")

@app.route("/practice")
def practice():
    # The sidebar's Practice link has no ?piece=: open the piece looked at last, so passages and reps can be saved.
    latest = None if request.args.get("piece") else next(iter(database.getPieces(user_id())), None)
    return render_template("practice.html", latest_piece=latest and latest["id"])

def give_starter_piece(uid):
    """Bach's Air, so a new account has a piece to practice before its first upload (the demo user gets it at startup)"""
    if not database.getPieces(uid):
        with open(os.path.join(app.static_folder, "AirOnG.musicxml"), "rb") as f:
            database.addPiece(uid, "Air", "J. S. Bach", xml=f.read())

@app.route("/login/google")
def login_google():
    try:
        return google.authorize_redirect(url_for("auth_google", _external=True)) if google.client_id else redirect(url_for("home"))
    except Exception:   # no Google keys, or Google unreachable: enter as the shared demo user
        return redirect(url_for("home"))

@app.route("/auth/google")
def auth_google():
    try:
        info = google.authorize_access_token()["userinfo"]
    except Exception:   # cancelled, expired or misconfigured sign-in: enter as the shared demo user
        return redirect(url_for("home"))
    row = database.getOrCreateGoogleUser(
        sub=info["sub"],
        name=info.get("name") or info["email"].split("@")[0],  # Users.name is NOT NULL
        email=info["email"],
        email_verified=info.get("email_verified", False),
    )
    give_starter_piece(row["id"])
    clear_practice_state()
    login_user(User(row))
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    logout_user()
    clear_practice_state()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(port=portNum)
