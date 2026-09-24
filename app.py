from flask import Flask, g, jsonify
import sqlite3
from database import database

app = Flask(__name__)
portNum = 8001
DATABASE = "niceplates.db"

with app.app_context():
    database.init_db()

def access_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

@app.route("/")
def test():
    return "<p>Wow we tested<p>"

@app.route("/add-user")
def addUserRoute():
    testName = "Laura Bailey"
    testEmail = "lbailey4022@yahoo.com"
    database.addUser(testName,testEmail)
    return "<p>New user added to the database!<p>"

@app.route("/fetch-users")
def fetchUsersRoute():
    return jsonify(database.fetchUsers())

if __name__ == "__main__":
    app.run(port=portNum)
