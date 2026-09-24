import sqlite3
import json

#create/repair database when initializing
def init_db():
    with sqlite3.connect("niceplates.db") as database: #connects to "niceplates.db" database file
        cursor = database.cursor() #cursor acts as the real connection to the database
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                pieces TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS Session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pieces TEXT NOT NULL DEFAULT '{}',
                time_spent INTEGER NOT NULL DEFAULT 0,
                date DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_notes TEXT
            );

            CREATE TABLE IF NOT EXISTS Piece (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                composer TEXT,
                bpm INTEGER,
                sections TEXT NOT NULL DEFAULT '{}',
                recordings TEXT NOT NULL DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS Recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audio BLOB NOT NULL
            );
            
            
        """)

        database.commit()

def fetchUsers():
    with sqlite3.connect("niceplates.db") as database:
        database.row_factory = sqlite3.Row
        cursor = database.cursor()
        cursor.execute("SELECT id, name, email, pieces FROM Users")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def addUser(name, email):
    with sqlite3.connect("niceplates.db") as database:
        cursor = database.cursor()
        cursor.execute(
            "INSERT INTO Users (name, email) VALUES (?, ?)",
            (name, email)
        )
        database.commit()
