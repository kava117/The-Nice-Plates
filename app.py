from datetime import date

from flask import Flask, render_template

# Pages are Jinja templates in music-app-home/templates/ (they share header.html,
# sidebar.html and footer.html). Static files (styles.css, theme.js, images) are
# still served from music-app-home/ at the site root, so relative links work.
app = Flask(
    __name__,
    static_folder="music-app-home",
    static_url_path="",
    template_folder="music-app-home/templates",
)
portNum = 8001


# Makes {{ year }} available to every template (used by footer.html).
@app.context_processor
def inject_year():
    return {"year": date.today().year}


@app.route("/")
@app.route("/index.html")
def index():
    return render_template("index.html")


@app.route("/home.html")
def home():
    return render_template("home.html")


if __name__ == "__main__":
    app.run(port=portNum)
