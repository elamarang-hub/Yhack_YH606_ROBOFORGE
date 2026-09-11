import sqlite3
import threading
from datetime import datetime

class Database:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        self._init()

    def _con(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self.lock, self._con() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS visitors(
                visitor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                encoding BLOB,
                visits INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS events(
                event_id TEXT PRIMARY KEY,
                classification TEXT,
                confidence REAL,
                status TEXT NOT NULL,
                distance_cm REAL,
                dwell_seconds REAL,
                photo_path TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS passive_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distance_cm REAL,
                camera_person INTEGER,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """)
        self._migrate()

    def _migrate(self):
        """Add the new OWNER/STRANGER identity columns to an events table
        that was created by an older version of this project (which used
        visitor_id/visitor_name instead). Old rows/columns are left in
        place -- they're just no longer written to or shown to the user."""
        with self.lock, self._con() as c:
            cols = {row["name"] for row in c.execute("PRAGMA table_info(events)")}
            if "classification" not in cols:
                c.execute("ALTER TABLE events ADD COLUMN classification TEXT")
            if "confidence" not in cols:
                c.execute("ALTER TABLE events ADD COLUMN confidence REAL")

    def next_visitor_id(self):
        with self.lock, self._con() as c:
            r = c.execute(
                "SELECT visitor_id FROM visitors ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if not r:
            return "VISITOR_001"
        return f"VISITOR_{int(r['visitor_id'].split('_')[-1])+1:03d}"

    def upsert_visitor(self, visitor_id, name, status, encoding=None):
        blob = encoding.tobytes() if encoding is not None else None
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self._con() as c:
            c.execute("""
            INSERT INTO visitors(visitor_id,name,status,encoding,visits,created_at,last_seen)
            VALUES(?,?,?,?,0,?,?)
            ON CONFLICT(visitor_id) DO UPDATE SET
                name=excluded.name,
                status=excluded.status,
                encoding=COALESCE(excluded.encoding,visitors.encoding),
                last_seen=excluded.last_seen
            """, (visitor_id,name,status,blob,now,now))

    def visitors(self):
        with self.lock, self._con() as c:
            return c.execute("SELECT * FROM visitors ORDER BY rowid").fetchall()

    def rename(self, visitor_id, name):
        with self.lock, self._con() as c:
            r = c.execute(
                "UPDATE visitors SET name=? WHERE visitor_id=?",
                (name,visitor_id)
            )
            return r.rowcount > 0

    def increment_visit(self, visitor_id):
        with self.lock, self._con() as c:
            c.execute(
                "UPDATE visitors SET visits=visits+1,last_seen=? WHERE visitor_id=?",
                (datetime.now().isoformat(timespec="seconds"),visitor_id)
            )

    def add_event(self, e):
        with self.lock, self._con() as c:
            c.execute("""
            INSERT INTO events(event_id,classification,confidence,status,
                               distance_cm,dwell_seconds,photo_path,created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """, (e["event_id"],e["classification"],e["confidence"],e["status"],
                  e["distance_cm"],e["dwell_seconds"],e["photo_path"],e["created_at"]))

    def add_passive(self, distance_cm, note):
        with self.lock, self._con() as c:
            c.execute("""
            INSERT INTO passive_logs(distance_cm,camera_person,note,created_at)
            VALUES(?,?,?,?)
            """, (distance_cm,1,note,datetime.now().isoformat(timespec="seconds")))

    def recent_events(self, n=10):
        with self.lock, self._con() as c:
            return c.execute(
                "SELECT * FROM events ORDER BY rowid DESC LIMIT ?",(n,)
            ).fetchall()

    def recent_passive(self, n=10):
        with self.lock, self._con() as c:
            return c.execute(
                "SELECT * FROM passive_logs ORDER BY id DESC LIMIT ?",(n,)
            ).fetchall()
