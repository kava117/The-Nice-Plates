import sqlite3
from contextlib import contextmanager

DB_NAME = "niceplates.db"

#helper to get the database and enable references (foreign keys) properly
def connect():
    db = sqlite3.connect(DB_NAME)
    db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = sqlite3.Row
    return db

@contextmanager
def get_db():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


#New changes to the database go here (adding columns, new tables, etc.)
MIGRATIONS = [

]

def migrate():
    with get_db() as database:
        database.execute("BEGIN IMMEDIATE")
        version = database.execute("PRAGMA user_version").fetchone()[0]
        for i, statement in enumerate(MIGRATIONS[version:], start=version):
            database.execute(statement)
            database.execute(f"PRAGMA user_version = {i + 1}")

#create database when initializing
def init_db():
    with get_db() as database: #connects to "niceplates.db" database file
        database.executescript("""
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_sub TEXT UNIQUE,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                profile_picture BLOB DEFAULT NULL,
                date_registered DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES Users(id),
                time_spent INTEGER NOT NULL DEFAULT 0, --seconds
                date DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_notes TEXT
            );

            CREATE TABLE IF NOT EXISTS Pieces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES Users(id),
                title TEXT NOT NULL,
                composer TEXT DEFAULT NULL,
                bpm INTEGER DEFAULT NULL,
                date_created DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_viewed DATETIME,
                midi BLOB,
                xml BLOB
            );

            CREATE TABLE IF NOT EXISTS Sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                piece_id INTEGER NOT NULL REFERENCES Pieces(id),
                start_measure INTEGER NOT NULL DEFAULT 0,
                end_measure INTEGER NOT NULL DEFAULT 0,
                times_practiced INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS Session_Pieces (
                session_id INTEGER NOT NULL REFERENCES Sessions(id),
                piece_id INTEGER NOT NULL REFERENCES Pieces(id),
                referenced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, piece_id)
            );
            
            CREATE TABLE IF NOT EXISTS Recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                piece_id INTEGER NOT NULL REFERENCES Pieces(id),
                audio BLOB NOT NULL,
                date_created DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS Index_Session_Pieces_Piece_Id ON Session_Pieces(piece_id);
            CREATE INDEX IF NOT EXISTS Index_Sessions_User_Id ON Sessions(user_id);
            CREATE INDEX IF NOT EXISTS Index_Pieces_User_Id ON Pieces(user_id);
            CREATE INDEX IF NOT EXISTS Index_Sections_Piece_Id ON Sections(piece_id);
            CREATE INDEX IF NOT EXISTS Index_Recordings_Piece_Id ON Recordings(piece_id);

        """)


def getUsers():
    with get_db() as database:
        rows = database.execute("SELECT id, name, email FROM Users").fetchall()
        return [dict(row) for row in rows]

def getUserById(user_id):
    with get_db() as database:
        row = database.execute(
            "SELECT id, name, email FROM Users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

def getOrCreateGoogleUser(sub, name, email, email_verified=False):
    email = email.strip().lower()
    with get_db() as database:
        # check if there is a user with the google id already registered
        row = database.execute(
            "SELECT id, name, email FROM Users WHERE google_sub = ?", (sub,)
        ).fetchone()
        if row:
            return dict(row)

        # if a user is registered with the email account returned by OAuth, but no google_sub exists, register the ids together if the email is verified
        if email_verified:
            row = database.execute(
                "SELECT id, name, email FROM Users WHERE email = ? AND google_sub IS NULL",
                (email,),
            ).fetchone()
            if row:
                database.execute(
                    "UPDATE Users SET google_sub = ? WHERE id = ?", (sub, row["id"])
                )
                return dict(row)

        # if the user does not exist yet, create one
        cur = database.execute(
            "INSERT INTO Users (google_sub, name, email) VALUES (?, ?, ?)",
            (sub, name, email),
        )
        return {"id": cur.lastrowid, "name": name, "email": email}

def getPieces(user_id):
    with get_db() as database:
        rows = database.execute(
            "SELECT id, title, composer, bpm FROM Pieces WHERE user_id = ? ",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

def getSessions(user_id):
    with get_db() as database:
        rows = database.execute(
            "SELECT id, time_spent, date, session_notes FROM Sessions WHERE user_id = ? ORDER BY date DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

def getSessionPieces(session_id):
    with get_db() as database:
        rows = database.execute(
            "SELECT p.id, p.title, sp.referenced_at FROM Session_Pieces sp JOIN Pieces p ON p.id = sp.piece_id WHERE sp.session_id = ? ORDER BY sp.referenced_at",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def addUser(name, email):
    email = email.strip().lower()
    with get_db() as database:
        cur = database.execute(
            "INSERT INTO Users (name, email) VALUES (?, ?)",
            (name, email),
        )
        return cur.lastrowid #use this to reference the user in any next steps

def addPiece(user_id, title, composer=None, bpm=None):
    with get_db() as database:
        cur = database.execute(
            "INSERT INTO Pieces (user_id, title, composer, bpm, xml) VALUES (?, ?, ?, ?, ?)",
            (user_id, title, composer, bpm),
        )
        return cur.lastrowid #use this to reference the piece in any next steps

def addSession(user_id, time_spent, notes=None, piece_ids=()):
    with get_db() as database:
        cur = database.execute(
            "INSERT INTO Sessions (user_id, time_spent, session_notes) VALUES (?, ?, ?)",
            (user_id, time_spent, notes),
        )
        session_id = cur.lastrowid
        database.executemany(
            "INSERT INTO Session_Pieces (session_id, piece_id) VALUES (?, ?)",
            [(session_id, pid) for pid in set(piece_ids)],
        )
        return session_id #use this to reference the session in any next steps