from flask import Flask, render_template

app = Flask(__name__)
portNum = 8001


@app.route("/dashboard")
def test():
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(port=portNum, debug=True)