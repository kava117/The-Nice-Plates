from flask import Flask, g, jsonify
import sqlite3
from database import database

app = Flask(__name__)
portNum = 8001

with app.app_context():
    database.init_db()
    database.migrate()

def access_db():
    if 'db' not in g:
        g.db = database.connect()
    return g.db

@app.route("/")
def test():
    return "<p>Wow we tested<p>"

@app.route("/add-user")
def addUserRoute():
    testName = "Laura Bailey"
    testEmail = "lbailey4022@yahoo.com"
    try:
        database.addUser(testName,testEmail.strip().lower())
    except sqlite3.IntegrityError: #this is the error thats passed when the UNIQUE constraint would fail
        return jsonify({"error":"That email is already registered"}), 409
    return "<p>New user added to the database!<p>"


@app.route("/fetch-users")
def fetchUsersRoute():
    return jsonify(database.fetchUsers())

if __name__ == "__main__":
    app.run(port=portNum)
