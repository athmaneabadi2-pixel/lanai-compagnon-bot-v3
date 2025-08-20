# memory_store.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquant.")

def _get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_schema():
    sql = """
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        user_phone TEXT NOT NULL,            -- ex: 'whatsapp:+33XXXX'
        role TEXT NOT NULL,                  -- 'system' | 'user' | 'assistant'
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_messages_user_time
        ON messages(user_phone, created_at);
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

def add_message(user_phone: str, role: str, content: str):
    sql = "INSERT INTO messages (user_phone, role, content, created_at) VALUES (%s, %s, %s, %s)"
    now = datetime.now(timezone.utc)
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (user_phone, role, content, now))
        conn.commit()

def get_history(user_phone: str, limit: int = 20):
    sql = """
    SELECT role, content
    FROM messages
    WHERE user_phone = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    with _get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (user_phone, limit))
        rows = cur.fetchall()
    # on renvoie du plus ancien au plus récent pour GPT
    rows = list(reversed(rows))
    return [{"role": r["role"], "content": r["content"]} for r in rows]
