from flask import Flask, g
import sqlite3
import database.database

app = Flask(__name__)
portNum = 8001
DATABASE = "niceplates.db"

with app.app_context():
    database.init_db(DATABASE)

def access_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

@app.route("/")
def test():
    return "<p>Wow we tested<p>"

if __name__ == "__main__":
    app.run(port=portNum)
