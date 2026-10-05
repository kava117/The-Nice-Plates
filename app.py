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

if __name__ == "__main__":
    app.run(port=portNum)
