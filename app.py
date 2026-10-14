from flask import Flask, jsonify, redirect, url_for, render_template, request, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from database import database
from datetime import date
import os, time
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

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
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)
portNum = 8001

oauth = OAuth(app)
google = oauth.register(
    name = "google",
    client_id = os.environ["GOOGLE_CLIENT_ID"],
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs = {"scope": "openid email profile"},
)

with app.app_context():
    database.init_db()
    database.migrate()

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

# Makes {{ year }} available to every template (used by footer.html).
@app.context_processor
def inject_year():
    return {"year": date.today().year}


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
PRACTICE_KEYS = ("current_piece_id", "selected_section_id", "timer_started_at", "timer_elapsed", "session_piece_ids")

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
        return int(data.get(key))
    except (TypeError, ValueError):
        return None

# only track pieces once a timer exists (running or paused with banked time)
def remember_piece(piece_id):
    if session.get("timer_started_at") is not None or session.get("timer_elapsed"):
        session["session_piece_ids"] = sorted(set(session.get("session_piece_ids", []) + [piece_id]))

# ==================================================================
# LOADING ALL OF OUR HTML PAGES
# ================================================================== 

#API ROUTES

#gets the practice state of the user
@app.route("/api/practice/state")
@login_required
def api_state():
    return jsonify(practice_state())

#pick a practice piece
@app.route("/api/practice/piece", methods=["POST"])
@login_required
def api_select_piece():
    piece_id = read_id(request.get_json(silent=True) or {}, "piece_id")
    if piece_id is None or not database.getPieceForUser(current_user.id, piece_id):
        return jsonify(error="piece not found"), 404
    session["current_piece_id"] = piece_id
    session.pop("selected_section_id", None)   # this section no longer relevant
    remember_piece(piece_id)
    return jsonify(practice_state())

#pick a practice section
@app.route("/api/practice/section", methods=["POST"])
@login_required
def api_select_section():
    section_id = read_id(request.get_json(silent=True) or {}, "section_id")
    section = database.getSectionForUser(current_user.id, section_id) if section_id else None
    if not section:
        return jsonify(error="section not found"), 404
    session["selected_section_id"] = section["id"]
    session["current_piece_id"] = section["piece_id"]   # a section implies its piece
    remember_piece(piece_id)
    return jsonify(practice_state())

#begin tracking a sessions length
@app.route("/api/timer/start", methods=["POST"])
@login_required
def api_timer_start():
    if session.get("timer_started_at") is None:         # dont reset timer if already started
        session["timer_started_at"] = time.time()
        piece_id = session.get("current_piece_id")
        if piece_id: #initializes session piece list
            session["session_piece_ids"] = sorted(set(session.get("session_piece_ids", []) + [piece_id]))
    return jsonify(practice_state())

#pause a session (settings change, page navigation, etc.)
@app.route("/api/timer/pause", methods=["POST"])
@login_required
def api_timer_pause():
    if session.get("timer_started_at") is not None:
        session["timer_elapsed"] = timer_seconds()      # keep track of currently elapsed time to return to or store later
        session["timer_started_at"] = None
    return jsonify(practice_state())

#stop the timer, and save the session to the database
@app.route("/api/timer/stop", methods=["POST"])
@login_required
def api_timer_stop():
    total = timer_seconds()
    notes = (request.get_json(silent=True) or {}).get("notes")
    session_id = None
    if total > 0:
        session_id = database.addSession(
            current_user.id, total, notes,
            piece_ids=session.get("session_piece_ids", []),
        )
    for key in ("timer_started_at", "timer_elapsed", "session_piece_ids"):
        session.pop(key, None)
    return jsonify(saved_session_id=session_id, time_spent=total, **practice_state())


#NORMAL ROUTES

@app.route("/")
@app.route("/index.html")
def index():
    return render_template("index.html")

@app.route("/home.html")
@login_required
def home():
    return render_template("home.html")

@app.route("/library.html")
@login_required
def library():
    return render_template("library.html")

@app.route("/progress.html")
@login_required
def progress():
    return render_template("progress.html")

@app.route("/settings.html")
@login_required
def settings():
    return render_template("settings.html")

@app.route("/practice.html")
@login_required
def practice():
    return render_template("practice.html")

@app.route("/login/google")
def login_google():
    redirect_uri = url_for("auth_google", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google")
def auth_google():
    token = google.authorize_access_token()
    info = token["userinfo"]
    row = database.getOrCreateGoogleUser(
        sub=info["sub"],
        name=info.get("name") or info["email"].split("@")[0],  # Users.name is NOT NULL
        email=info["email"],
        email_verified=info.get("email_verified", False),
    )
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
