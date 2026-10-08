from flask import Flask, g, jsonify, redirect, url_for, render_template, request
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
from database import database
from datetime import date
import os
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
login_manager.login_view = "index" #where not logged in users redirect to

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


def access_db():
    if 'db' not in g:
        g.db = database.connect()
    return g.db

# Makes {{ year }} available to every template (used by footer.html).
@app.context_processor
def inject_year():
    return {"year": date.today().year}

# ==================================================================
# LOADING ALL OF OUR HTML PAGES
# ================================================================== 
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
    login_user(User(row))
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(port=portNum)
