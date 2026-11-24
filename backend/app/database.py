import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import List, Optional
from app.config import settings
from app.models import SessionMessageItem, AssistantMessageMetadata

def get_db_connection() -> sqlite3.Connection:
    db_path = settings.sqlite_db_path
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id);")
    finally:
        conn.close()

def check_db_health() -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        res = cursor.fetchone()
        conn.close()
        return res is not None
    except Exception:
        return False

def session_exists(session_id: str) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1;", (session_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def get_session_messages(session_id: str) -> Optional[List[SessionMessageItem]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC;",
            (session_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        
        items: List[SessionMessageItem] = []
        for row in rows:
            role = row["role"]
            content = row["content"]
            meta_raw = row["metadata"]
            metadata_obj = None
            if role == "assistant" and meta_raw:
                try:
                    meta_dict = json.loads(meta_raw)
                    metadata_obj = AssistantMessageMetadata(
                        resolution_source=meta_dict.get("resolution_source", "LIVE_INFERENCE"),
                        input_tokens=meta_dict.get("input_tokens", 0),
                        output_tokens=meta_dict.get("output_tokens", 0),
                    )
                except Exception:
                    metadata_obj = None
            items.append(SessionMessageItem(role=role, content=content, metadata=metadata_obj))
        return items
    finally:
        conn.close()

def get_raw_session_history(session_id: str) -> List[dict]:
    """
    Returns history as list of dicts [{'role': role, 'content': content}]
    for feeding into LLM messages.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC;",
            (session_id,)
        )
        rows = cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        conn.close()

def add_message(session_id: str, role: str, content: str, metadata: Optional[dict] = None):
    conn = get_db_connection()
    try:
        with conn:
            meta_str = json.dumps(metadata) if metadata else None
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, role, content, meta_str, now_iso)
            )
    finally:
        conn.close()
