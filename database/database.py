import os, re, sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_NAME = "niceplates.db"

# With DATABASE_URL set (a Postgres URL, e.g. from Neon), everything is kept there and survives
# restarts. Without it, a local SQLite file, which free hosting wipes on every restart.
# The SQL below is written once, for SQLite; Postgres gets it through translate().
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
    IntegrityError = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    IntegrityError = sqlite3.IntegrityError

PG_REWRITES = [
    (re.compile(r"INTEGER PRIMARY KEY AUTOINCREMENT", re.I), "SERIAL PRIMARY KEY"),
    (re.compile(r"\bBLOB\b", re.I), "BYTEA"),
    (re.compile(r"\bDATETIME\b", re.I), "TIMESTAMP"),
    (re.compile(r"\?"), "%s"),
]

def translate(sql):
    """SQLite SQL as Postgres SQL"""
    for pattern, replacement in PG_REWRITES:
        sql = pattern.sub(replacement, sql)
    if re.match(r"\s*INSERT OR IGNORE", sql, re.I):
        sql = re.sub(r"INSERT OR IGNORE", "INSERT", sql, count=1, flags=re.I) + " ON CONFLICT DO NOTHING"
    return sql

def plain(value):
    """Postgres hands back datetimes and memoryviews; the app expects SQLite's strings and bytes"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, memoryview):
        return bytes(value)
    return value

class Row(dict):
    """a dict that also reads by position, like sqlite3.Row"""
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Result:
    def __init__(self, cursor, lastrowid=None):
        self.cursor, self.lastrowid, self.rowcount = cursor, lastrowid, cursor.rowcount
    def fetchone(self):
        row = self.cursor.fetchone() if self.cursor.description else None
        return Row({k: plain(v) for k, v in row.items()}) if row else None
    def fetchall(self):
        return [Row({k: plain(v) for k, v in row.items()}) for row in self.cursor.fetchall()] if self.cursor.description else []

class PostgresDB:
    """the slice of sqlite3.Connection this file uses, on a Postgres connection"""
    def __init__(self):
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    def execute(self, sql, params=()):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            return Result(self.conn.cursor())   # Postgres opens the transaction by itself
        sql = translate(sql)
        returning = re.match(r"\s*INSERT INTO (\w+)", sql, re.I)
        if returning and returning.group(1).lower() != "session_pieces" and "RETURNING" not in sql.upper() and "ON CONFLICT" not in sql.upper():
            cursor = self.conn.execute(sql + " RETURNING id", params)   # sqlite's lastrowid
            return Result(cursor, cursor.fetchone()["id"])
        return Result(self.conn.execute(sql, params))
    def executemany(self, sql, rows):
        with self.conn.cursor() as cursor:
            cursor.executemany(translate(sql), list(rows))
    def executescript(self, script):
        script = re.sub(r"--[^\n]*", "", script)   # comments may hold a ";"
        for statement in script.split(";"):
            if statement.strip():
                self.conn.execute(translate(statement))
    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()

#helper to get the database and enable references (foreign keys) properly
def connect():
    if POSTGRES:
        return PostgresDB()
    db = sqlite3.connect(DB_NAME)
    db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = sqlite3.Row
    return db

@contextmanager
def get_db():
    db = connect()
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


#New changes to the database go here (adding columns, new tables, etc.)
MIGRATIONS = [
    "ALTER TABLE Sessions ADD COLUMN timer_id TEXT",   # one practice timer saves at most one row; old rows keep NULL
    "CREATE UNIQUE INDEX IF NOT EXISTS Index_Sessions_Timer_Id ON Sessions(timer_id)",
]

def migrate():
    with get_db() as database:
        database.execute("BEGIN IMMEDIATE")
        if POSTGRES:   # no PRAGMA user_version there: a one-row table keeps the count
            database.execute("CREATE TABLE IF NOT EXISTS Schema_Version (version INTEGER NOT NULL)")
            row = database.execute("SELECT version FROM Schema_Version").fetchone()
            if row is None:
                database.execute("INSERT INTO Schema_Version (version) VALUES (0) ON CONFLICT DO NOTHING")
            version = row["version"] if row else 0
        else:
            version = database.execute("PRAGMA user_version").fetchone()[0]
        for i, statement in enumerate(MIGRATIONS[version:], start=version):
            database.execute(statement)
            if POSTGRES:
                database.execute("UPDATE Schema_Version SET version = ?", (i + 1,))
            else:
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

            -- one row per time through a passage (a row in Sections): did it go clean, and how fast
            -- (a new table, so IF NOT EXISTS covers old databases too; no MIGRATIONS entry needed)
            CREATE TABLE IF NOT EXISTS Section_Reps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_id INTEGER NOT NULL REFERENCES Sections(id) ON DELETE CASCADE,
                clean INTEGER NOT NULL,             -- 1 = clean, 0 = not yet
                tempo INTEGER,                      -- percent of the score's tempo
                date DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS Index_Section_Reps_Section_Id ON Section_Reps(section_id);
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
            "SELECT id, title, composer, bpm FROM Pieces WHERE user_id = ? ORDER BY COALESCE(last_viewed, date_created) DESC, id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    
def getPieceForUser(user_id, piece_id):
    with get_db() as database:
        row = database.execute(
            "SELECT id, title, composer, bpm FROM Pieces WHERE id = ? AND user_id = ?",
            (piece_id, user_id),
        ).fetchone()
        return dict(row) if row else None

def getXML(piece_id):
    with get_db() as database:
        row = database.execute(
            "SELECT xml FROM Pieces WHERE id = ?",
            (piece_id,)
        ).fetchone()
        return dict(row) if row else None
        
def getMidi(piece_id):
    with get_db() as database:
        row = database.execute(
            "SELECT midi FROM Pieces WHERE id = ?",
            (piece_id,)
        ).fetchone()
        return dict(row) if row else None

def getSectionForUser(user_id, section_id):
    with get_db() as database:
        row = database.execute(
            """SELECT s.id, s.piece_id, s.start_measure, s.end_measure
               FROM Sections s JOIN Pieces p ON p.id = s.piece_id
               WHERE s.id = ? AND p.user_id = ?""",
            (section_id, user_id),
        ).fetchone()
        return dict(row) if row else None

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

def addPiece(user_id, title, composer=None, bpm=None, xml=None, midi=None):
    with get_db() as database:
        cur = database.execute(
            "INSERT INTO Pieces (user_id, title, composer, bpm, xml, midi) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, composer, bpm, xml, midi),
        )
        return cur.lastrowid #use this to reference the piece in any next steps

def addSession(user_id, time_spent, notes=None, piece_ids=(), timer_id=None):
    try:
        with get_db() as database:
            cur = database.execute(
                "INSERT INTO Sessions (user_id, time_spent, session_notes, timer_id) VALUES (?, ?, ?, ?)",
                (user_id, time_spent, notes, timer_id),
            )
            session_id = cur.lastrowid
            database.executemany(
                "INSERT INTO Session_Pieces (session_id, piece_id) VALUES (?, ?)",
                [(session_id, pid) for pid in set(piece_ids)],
            )
            return session_id #use this to reference the session in any next steps
    except IntegrityError:   # this timer was already saved (two tabs, the back button): hand back that row
        with get_db() as database:
            row = database.execute("SELECT id FROM Sessions WHERE timer_id = ? AND user_id = ?", (timer_id, user_id)).fetchone()
        if row is None:
            raise
        return row["id"]

def touchPiece(piece_id):
    with get_db() as database:
        database.execute("UPDATE Pieces SET last_viewed = CURRENT_TIMESTAMP WHERE id = ?", (piece_id,))

def getPieceSeconds(user_id):
    """seconds practiced per piece, from the sessions that referenced it"""
    with get_db() as database:
        rows = database.execute(
            "SELECT sp.piece_id, SUM(s.time_spent) AS seconds FROM Session_Pieces sp JOIN Sessions s ON s.id = sp.session_id WHERE s.user_id = ? GROUP BY sp.piece_id",
            (user_id,),
        ).fetchall()
        return {row["piece_id"]: row["seconds"] for row in rows}

def addRecording(piece_id, audio):
    with get_db() as database:
        return database.execute("INSERT INTO Recordings (piece_id, audio) VALUES (?, ?)", (piece_id, audio)).lastrowid

def getRecording(user_id, recording_id):
    with get_db() as database:
        return database.execute(
            "SELECT r.audio FROM Recordings r JOIN Pieces p ON p.id = r.piece_id WHERE r.id = ? AND p.user_id = ?",
            (recording_id, user_id),
        ).fetchone()

# Passages: the bars a musician picks out of a piece to practice (rows in Sections).
# start_measure and end_measure count bars from 1 in score order, so they match the
# printed bar numbers unless the score opens with a pickup bar.

RECENT_REPS = 20   # how many reps the practice page gets back for each passage

def sectionRecord(database, row):
    """a passage with its practice record: recent reps (oldest first) and totals"""
    reps = database.execute(
        "SELECT clean, tempo FROM Section_Reps WHERE section_id = ? ORDER BY id DESC LIMIT ?",
        (row["id"], RECENT_REPS),
    ).fetchall()
    totals = database.execute(
        """SELECT COUNT(*) AS reps, COALESCE(SUM(clean), 0) AS clean, MAX(date) AS last_practiced,
                  MAX(CASE WHEN clean = 1 THEN tempo END) AS best_tempo
           FROM Section_Reps WHERE section_id = ?""",
        (row["id"],),
    ).fetchone()
    return {"id": row["id"], "piece_id": row["piece_id"], "start": row["start_measure"], "end": row["end_measure"],
            "recent": [{"clean": bool(r["clean"]), "tempo": r["tempo"]} for r in reversed(reps)], **dict(totals)}

def getSections(user_id, piece_id):
    """one piece's passages in bar order"""
    with get_db() as database:
        rows = database.execute(
            """SELECT s.id, s.piece_id, s.start_measure, s.end_measure FROM Sections s JOIN Pieces p ON p.id = s.piece_id
               WHERE s.piece_id = ? AND p.user_id = ? ORDER BY s.start_measure, s.end_measure""",
            (piece_id, user_id),
        ).fetchall()
        return [sectionRecord(database, row) for row in rows]

def getSectionRecord(section_id):
    with get_db() as database:
        row = database.execute("SELECT id, piece_id, start_measure, end_measure FROM Sections WHERE id = ?", (section_id,)).fetchone()
        return sectionRecord(database, row) if row else None

def addSection(piece_id, start, end):
    """the passage for these bars, made if it doesn't exist yet; returns (id, created)"""
    with get_db() as database:
        database.execute("BEGIN IMMEDIATE")   # two quick clicks must not make the same passage twice
        row = database.execute(
            "SELECT id FROM Sections WHERE piece_id = ? AND start_measure = ? AND end_measure = ?", (piece_id, start, end)
        ).fetchone()
        if row:
            return row["id"], False
        cur = database.execute("INSERT INTO Sections (piece_id, start_measure, end_measure) VALUES (?, ?, ?)", (piece_id, start, end))
        return cur.lastrowid, True

def deleteSection(section_id):
    with get_db() as database:
        database.execute("DELETE FROM Sections WHERE id = ?", (section_id,))   # its reps go too (ON DELETE CASCADE)

def addRep(section_id, clean, tempo=None):
    with get_db() as database:
        database.execute("INSERT INTO Section_Reps (section_id, clean, tempo) VALUES (?, ?, ?)", (section_id, int(clean), tempo))
        database.execute("UPDATE Sections SET times_practiced = times_practiced + 1 WHERE id = ?", (section_id,))

def deleteLastRep(section_id):
    """undo: removes the passage's newest rep; returns whether there was one"""
    with get_db() as database:
        gone = database.execute(
            "DELETE FROM Section_Reps WHERE id = (SELECT MAX(id) FROM Section_Reps WHERE section_id = ?)", (section_id,)
        ).rowcount
        if gone:
            database.execute("UPDATE Sections SET times_practiced = CASE WHEN times_practiced > 0 THEN times_practiced - 1 ELSE 0 END WHERE id = ?", (section_id,))
        return bool(gone)

def getPracticeRecord(user_id, sessions=20):
    """what the coach reads, in one connection: recent sessions with their pieces, and every piece with its passages"""
    with get_db() as database:
        recent = []
        for s in database.execute(
            "SELECT id, time_spent, date, session_notes FROM Sessions WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, sessions),
        ).fetchall():
            titles = database.execute(
                "SELECT p.title FROM Session_Pieces sp JOIN Pieces p ON p.id = sp.piece_id WHERE sp.session_id = ?",
                (s["id"],),
            ).fetchall()
            recent.append({"date": s["date"], "seconds": s["time_spent"], "notes": s["session_notes"],
                           "pieces": [t["title"] for t in titles]})
        seconds = {row["piece_id"]: row["seconds"] for row in database.execute(
            "SELECT sp.piece_id, SUM(s.time_spent) AS seconds FROM Session_Pieces sp JOIN Sessions s ON s.id = sp.session_id WHERE s.user_id = ? GROUP BY sp.piece_id",
            (user_id,),
        ).fetchall()}
        pieces = []
        for p in database.execute(
            "SELECT id, title, composer, bpm FROM Pieces WHERE user_id = ? ORDER BY COALESCE(last_viewed, date_created) DESC, id DESC",
            (user_id,),
        ).fetchall():
            rows = database.execute(
                "SELECT id, piece_id, start_measure, end_measure FROM Sections WHERE piece_id = ? ORDER BY start_measure, end_measure",
                (p["id"],),
            ).fetchall()
            pieces.append({**dict(p), "seconds": seconds.get(p["id"], 0),
                           "passages": [sectionRecord(database, row) for row in rows]})
        return {"sessions": recent, "pieces": pieces}

def demoUser():
    """One shared user until Google login lands; then use the signed-in user's id instead."""
    with get_db() as database:
        database.execute("INSERT OR IGNORE INTO Users (name, email) VALUES ('Sample User', 'sample.user@example.com')")
        return database.execute("SELECT id FROM Users WHERE email = 'sample.user@example.com'").fetchone()[0]
