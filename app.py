from flask import Flask

# Serve the static pages in music-app-home/ from the site root, so the
# relative links between them (index.html, home.html, styles.css, theme.js) work.
app = Flask(__name__, static_folder="music-app-home", static_url_path="")
portNum = 8001


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(port=portNum)
