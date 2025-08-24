# memory_store.py
import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquant.")

def _get_conn():
    # Connexion simple ; RealDictCursor utile pour les SELECT (historique)
    return psycopg2.connect(DATABASE_URL)

def init_schema():
    """
    Idempotent : crée la table si besoin + colonnes utiles + index (si pas déjà faits).
    OK même si le patch SQL a déjà été appliqué dans DBeaver.
    """
    with _get_conn() as conn, conn.cursor() as cur:
        # Table minimale
        cur.execute("""
        CREATE TABLE IF NOT EXISTS public.messages (
            id SERIAL PRIMARY KEY,
            user_phone TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        # Colonnes dédup (si manquantes)
        cur.execute("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS msg_sid TEXT;")
        cur.execute("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS direction TEXT;")
        cur.execute("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS source TEXT;")
        cur.execute("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS content_hash TEXT;")
        # Colonne générée (jour UTC)
        cur.execute("""
        ALTER TABLE public.messages
          ADD COLUMN IF NOT EXISTS created_day date
          GENERATED ALWAYS AS ((created_at AT TIME ZONE 'UTC')::date) STORED;
        """)
        # Index non-uniques utiles (lecture)
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_time
          ON public.messages(user_phone, created_at);
        """)
        # Index uniq : webhook (empêche 2 inserts du même MessageSid dans la même direction)
        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_msgsid_dir
          ON public.messages (msg_sid, direction)
          WHERE msg_sid IS NOT NULL AND direction IS NOT NULL;
        """)
        # Index uniq : crons (empêche 2 lignes identiques le même jour pour une même source)
        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_cron_source_hash_day
          ON public.messages (created_day, source, content_hash)
          WHERE source IS NOT NULL AND content_hash IS NOT NULL;
        """)
        conn.commit()

def add_message(user_phone: str, role: str, content: str,
                msg_sid: str | None = None,
                direction: str | None = None,
                source: str | None = None):
    """
    Insère un message avec déduplication.
    - user_phone : 'whatsapp:+33...'
    - role       : 'user' | 'assistant'
    - content    : texte envoyé/reçu
    - msg_sid    : identifiant Twilio (si connu, ex webhook IN ou envoi Twilio)
    - direction  : 'in' | 'out'
    - source     : 'webhook' | 'cron_weather' | 'cron_results'
    Le 'content_hash' est calculé ici. 'ON CONFLICT DO NOTHING' s'appuie sur nos index uniques.
    """
    if content is None:
        content = ""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.messages (user_phone, role, content, msg_sid, direction, source, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;
        """, (user_phone, role, content, msg_sid, direction, source, content_hash))
        conn.commit()

def get_history(user_phone: str, limit: int = 20):
    sql = """
    SELECT role, content
    FROM public.messages
    WHERE user_phone = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    with _get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (user_phone, limit))
        rows = cur.fetchall()
    # Inverse pour donner du plus ancien au plus récent à GPT
    rows.reverse()
    return [{"role": r["role"], "content": r["content"]} for r in rows]
