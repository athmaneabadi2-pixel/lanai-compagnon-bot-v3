# memory_store.py — DB utils (migrations douces + dédup MessageSid)
provider_sid TEXT -- Twilio MessageSid (in/out)
);


CREATE INDEX IF NOT EXISTS idx_messages_user_time
ON messages(user_phone, created_at);


-- Ajouts idempotents
ALTER TABLE messages ADD COLUMN IF NOT EXISTS direction TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS provider_sid TEXT;


-- Déduplication sur MessageSid si présent
DO $$
BEGIN
IF NOT EXISTS (
SELECT 1
FROM pg_indexes
WHERE schemaname = 'public'
AND indexname = 'ux_messages_provider_sid'
) THEN
EXECUTE 'CREATE UNIQUE INDEX ux_messages_provider_sid ON messages(provider_sid) WHERE provider_sid IS NOT NULL';
END IF;
END$$;
"""
with _get_conn() as conn, conn.cursor() as cur:
cur.execute(ddl)
conn.commit()




def ping_db() -> bool:
try:
with _get_conn() as conn, conn.cursor() as cur:
cur.execute("SELECT 1")
cur.fetchone()
return True
except Exception:
return False




def add_message_ext(user_phone: str, role: str, content: str,
direction: str | None = None, provider_sid: str | None = None):
"""Ajoute un message avec infos supplémentaires. Déduplique si provider_sid déjà vu."""
sql = """
INSERT INTO messages (user_phone, role, content, created_at, direction, provider_sid)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (provider_sid) WHERE provider_sid IS NOT NULL DO NOTHING
"""
now = datetime.now(timezone.utc)
with _get_conn() as conn, conn.cursor() as cur:
cur.execute(sql, (user_phone, role, content, now, direction, provider_sid))
conn.commit()




# Rétro-compatibilité


def add_message(user_phone: str, role: str, content: str):
return add_message_ext(user_phone, role, content, None, None)




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
# renvoyer du plus ancien au plus récent pour GPT
rows = list(reversed(rows))
return [{"role": r["role"], "content": r["content"]} for r in rows]
