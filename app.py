from flask import Flask

app = Flask(__name__)
portNum = 8001


@app.route("/")
def test():
    return "<p>Wow we tested<p>"

if __name__ == "__main__":
    app.run(port=portNum)