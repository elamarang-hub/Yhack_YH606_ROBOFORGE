import sqlite3
import numpy as np
import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "hub.db")

def get_db_connection():
    """Returns a new sqlite3 connection with dict-like row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT UNIQUE,
            name TEXT,
            encoding_blob BLOB,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            visit_count INTEGER DEFAULT 1,
            thumbnail_base64 TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP,
            face_id INTEGER,
            label TEXT,
            confidence REAL,
            image_base64 TEXT,
            action_taken TEXT,
            tof_distance_mm REAL,
            FOREIGN KEY(face_id) REFERENCES faces(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP,
            face_id INTEGER,
            direction TEXT,
            content_type TEXT,
            file_path TEXT,
            text_content TEXT,
            FOREIGN KEY(face_id) REFERENCES faces(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_next_visitor_tag():
    """Gets the next auto-incrementing visitor tag."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(id) as count FROM faces WHERE tag LIKE 'Visitor_%'")
    row = c.fetchone()
    conn.close()
    count = row['count'] + 1 if row else 1
    return f"Visitor_{count:03d}"

def add_face(tag, encoding, thumbnail_b64):
    """Adds a new face to the database and returns its ID."""
    conn = get_db_connection()
    c = conn.cursor()
    encoding_blob = np.array(encoding, dtype=np.float64).tobytes()
    now = datetime.datetime.now()
    
    c.execute('''
        INSERT INTO faces (tag, encoding_blob, first_seen, last_seen, visit_count, thumbnail_base64)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (tag, encoding_blob, now, now, 1, thumbnail_b64))
    face_id = c.lastrowid
    conn.commit()
    conn.close()
    return face_id

def find_matching_face(encoding, threshold=0.45):
    """Finds a matching face in the database based on the encoding threshold."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, tag, name, encoding_blob FROM faces")
    rows = c.fetchall()
    conn.close()
    
    best_match = None
    best_distance = float('inf')
    target_enc = np.array(encoding, dtype=np.float64)
    
    for row in rows:
        db_enc = np.frombuffer(row['encoding_blob'], dtype=np.float64)
        distance = np.linalg.norm(db_enc - target_enc)
        if distance < best_distance:
            best_distance = distance
            best_match = row
            
    if best_distance <= threshold and best_match:
        return (best_match['id'], best_match['tag'], best_match['name'], best_distance)
    return None

def update_face_visit(face_id, thumbnail_b64):
    """Updates the last seen time, visit count, and thumbnail for a given face."""
    conn = get_db_connection()
    c = conn.cursor()
    now = datetime.datetime.now()
    c.execute('''
        UPDATE faces 
        SET last_seen = ?, visit_count = visit_count + 1, thumbnail_base64 = ?
        WHERE id = ?
    ''', (now, thumbnail_b64, face_id))
    conn.commit()
    conn.close()

def rename_face(old_tag_or_id, new_name):
    """Updates the name of a face based on its ID or tag."""
    conn = get_db_connection()
    c = conn.cursor()
    if isinstance(old_tag_or_id, int) or str(old_tag_or_id).isdigit():
        c.execute("UPDATE faces SET name = ? WHERE id = ?", (new_name, int(old_tag_or_id)))
    else:
        c.execute("UPDATE faces SET name = ? WHERE tag = ?", (new_name, old_tag_or_id))
    conn.commit()
    conn.close()

def log_event(label, confidence, image_b64, tof_distance=None, face_id=None, action_taken=None):
    """Logs an event in the access logs."""
    conn = get_db_connection()
    c = conn.cursor()
    now = datetime.datetime.now()
    c.execute('''
        INSERT INTO access_logs (timestamp, face_id, label, confidence, image_base64, action_taken, tof_distance_mm)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (now, face_id, label, confidence, image_b64, action_taken, tof_distance))
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_recent_logs(limit=20):
    """Retrieves the most recent access logs."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT al.*, f.tag, f.name 
        FROM access_logs al 
        LEFT JOIN faces f ON al.face_id = f.id 
        ORDER BY al.timestamp DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_face_history():
    """Retrieves the history of all known faces."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, tag, name, first_seen, last_seen, visit_count, thumbnail_base64 FROM faces ORDER BY last_seen DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]
