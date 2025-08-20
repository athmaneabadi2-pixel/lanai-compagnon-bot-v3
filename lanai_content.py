# lanai_content.py
import os
import json
import random
import hashlib
from datetime import datetime, timedelta
from twilio.rest import Client
from memory_store import init_schema, add_message  # mémoire partagée DB

# ======== Config via ENV ========
MODE = os.environ.get("LANAI_MODE", "hybrid").lower()  # hybrid | json | gpt
HISTORY_DAYS = int(os.environ.get("LANAI_HISTORY_DAYS", "60"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # optionnel ici
# ================================

# ======== Init DB (table si besoin) ========
init_schema()

# ======== Chemins robustes (banque JSON facultative) ========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATE_JSON = [
    os.path.join(BASE_DIR, "contenu_messages.json"),
    os.path.join(BASE_DIR, "data", "contenu_messages.json"),
]
CONTENT_FILE = next((p for p in CANDIDATE_JSON if os.path.exists(p)), None)

def load_bank():
    if not CONTENT_FILE:
        return {}
    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
BANK = load_bank()

# ======== Anti-répétition (locale) via hash ========
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"messages": []}

def save_history(hist):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

def prune_history(hist):
    cutoff = datetime.utcnow() - timedelta(days=HISTORY_DAYS)
    pruned = [m for m in hist.get("messages", []) if datetime.fromisoformat(m["ts"]) >= cutoff]
    hist["messages"] = pruned
    return hist

def already_sent(text, hist):
    h = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
    return any(m["hash"] == h for m in hist.get("messages", []))

def remember(text, hist):
    h = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
    hist["messages"].append({"ts": datetime.utcnow().isoformat(), "hash": h, "preview": text[:120]})
    save_history(hist)

HISTORY = prune_history(load_history())

# ======== GPT helper (v1 + fallback v0.28) ========
def generate_gpt_snippet():
    if not OPENAI_API_KEY:
        return None

    system = (
        "Tu es Lanai, compagnon WhatsApp de Mohamed Djeziri. "
        "Langage simple, phrases courtes, ton chaleureux, bienveillant. "
        "Fais parfois un clin d'œil à sa femme Milouda et à leur chat Lana. "
        "2 à 3 phrases max."
    )
    themes = [
        "encouragement doux + mini question",
        "prise de nouvelles + clin d’œil à Lana le chat",
        "mot positif + petite suggestion (respiration, marche)",
        "check-in basket (as-tu regardé les scores?) + phrase motivante",
    ]
    user_prompt = (
        "Commence par « Salam aleykum Mohamed, » sur la première ligne. "
        f"Thème: {random.choice(themes)}. "
        "Évite le jargon. Pas d'emojis dans cette partie."
    )

    # v1
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=150
        )
        return resp.choices[0].message.content.strip()
    except Exception as e1:
        print(f"⚠️ OpenAI v1 indisponible, essai v0.28: {e1}")

    # v0.28
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=150
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e2:
        print(f"⚠️ GPT fallback (v0.28) échec : {e2}")
        return None

# ======== Sélection banque JSON (toujours incluse en mode hybrid/json) ========
def pick_from_bank():
    categories = []
    for key in ("hadith", "coran", "citations", "sante", "citations_fiables"):
        if key in BANK and isinstance(BANK[key], list) and BANK[key]:
            categories.append(key)
    if not categories:
        return None
    cat = random.choice(categories)
    txt = random.choice(BANK[cat]).strip()
    prefix_map = {
        "hadith": "🤲 Hadith : ",
        "coran": "📖 Coran : ",
        "citations": "✨ Citation : ",
        "citations_fiables": "✨ Citation : ",
        "sante": "💊 Santé : ",
    }
    return f"{prefix_map.get(cat, '')}{txt}"

# ======== Composer message final ========
def build_message():
    effective_mode = MODE
    if not OPENAI_API_KEY and MODE in ("gpt", "hybrid"):
        effective_mode = "json"

    gpt_text = None
    bank_line = None

    if effective_mode in ("gpt", "hybrid"):
        gpt_text = generate_gpt_snippet()

    if effective_mode in ("json", "hybrid"):
        bank_line = pick_from_bank()  # toujours inclure une ligne JSON

    if effective_mode in ("gpt", "hybrid") and not gpt_text and bank_line:
        gpt_text = "Salam aleykum Mohamed,"  # mini intro si GPT HS

    if gpt_text and bank_line:
        return f"{gpt_text}\n\n{bank_line}".strip()
    if gpt_text:
        return gpt_text.strip()
    if bank_line:
        return f"Salam aleykum Mohamed,\n\n{bank_line}".strip()

    raise ValueError("❌ Aucun contenu disponible (ni GPT, ni JSON).")

# ======== Envoi WhatsApp via Twilio ========
def send_whatsapp(text):
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ex: whatsapp:+14155238886
    receiver_whatsapp = os.environ.get("MY_WHATSAPP_NUMBER")    # ex: whatsapp:+33XXXXXXXXX

    if not twilio_sid or not twilio_token:
        raise ValueError("❌ Identifiants Twilio manquants.")
    if not twilio_whatsapp or not receiver_whatsapp:
        raise ValueError("❌ Numéros WhatsApp manquants (TWILIO_WHATSAPP_NUMBER / MY_WHATSAPP_NUMBER).")

    client = Client(twilio_sid, twilio_token)
    message = client.messages.create(
        from_=twilio_whatsapp,
        body=text,
        to=receiver_whatsapp
    )
    return message.sid, receiver_whatsapp

# ======== Main (cron) ========
if __name__ == "__main__":
    final = build_message()

    # Anti-répétition locale
    if already_sent(final, HISTORY):
        alt = build_message()
        if not already_sent(alt, HISTORY):
            final = alt

    sid, user_phone = send_whatsapp(final)
    remember(final, HISTORY)

    # ÉCRITURE EN DB PARTAGÉE : consigner le message du cron comme 'assistant'
    try:
        add_message(user_phone, "assistant", final)
    except Exception as e:
        print(f"⚠️ Erreur DB (save cron): {e}")

    print(f"ℹ️ Mode: {MODE} | JSON: {CONTENT_FILE if CONTENT_FILE else 'non'}")
    print(f"✅ WhatsApp envoyé. SID: {sid}")
