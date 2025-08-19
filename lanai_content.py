import os
import json
import random
import hashlib
from datetime import datetime, timedelta
from twilio.rest import Client

# ========== Config via ENV ==========
MODE = os.environ.get("LANAI_MODE", "hybrid").lower()  # hybrid | json | gpt
HISTORY_DAYS = int(os.environ.get("LANAI_HISTORY_DAYS", "60"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # optionnel
# ==========/ Config via ENV ==========

# ========= Chemins robustes =========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATE_JSON = [
    os.path.join(BASE_DIR, "contenu_messages.json"),
    os.path.join(BASE_DIR, "data", "contenu_messages.json"),
]
HISTORY_CANDIDATE = [
    os.path.join(BASE_DIR, "history.json"),
    os.path.join(BASE_DIR, "data", "history.json"),
]

CONTENT_FILE = next((p for p in CANDIDATE_JSON if os.path.exists(p)), None)
HISTORY_FILE = HISTORY_CANDIDATE[0]  # par défaut à côté
if not CONTENT_FILE:
    # si pas de JSON et pas d'OpenAI => on ne peut rien faire
    if not OPENAI_API_KEY and MODE in ("json", "hybrid"):
        raise FileNotFoundError("❌ contenu_messages.json introuvable et pas d'OPENAI_API_KEY. "
                                "Ajoute le JSON ou définis OPENAI_API_KEY.")
# =========/ Chemins robustes =========

# ========= Banque JSON (optionnelle) =========
def load_bank():
    if not CONTENT_FILE:
        return {}
    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

BANK = load_bank()
# =========/ Banque JSON ==========

# ========= Historique anti-répétition =========
def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"messages": []}

def save_history(hist):
    # crée le dossier si besoin
    hist_dir = os.path.dirname(HISTORY_FILE)
    if hist_dir and not os.path.exists(hist_dir):
        os.makedirs(hist_dir, exist_ok=True)
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
# =========/ Historique =========

# ========= GPT (optionnel) =========
def generate_gpt_snippet():
    """
    2–3 phrases max, chaleureuses, personnalisées (Milouda, Lana, basket).
    Fallback: renvoie None si pas de clé ou erreur.
    """
    if not OPENAI_API_KEY:
        return None
    try:
        # SDK OpenAI v1
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        system = (
            "Tu es Lanai, compagnon WhatsApp de Mohamed Djeziri. "
            "Langage simple, phrases courtes, ton chaleureux. "
            "Rappelle-toi: sa femme Milouda, leur chat Lana, il aime le basket. "
            "Toujours bienveillant. 2 à 3 phrases max."
        )
        themes = [
            "encouragement doux du jour + mini question",
            "prise de nouvelles + clin d’œil à Lana le chat",
            "mot positif + suggestion simple (respirer, marcher)",
            "check-in basket (as-tu regardé les scores?) + phrase motivante",
        ]
        user_prompt = (
            "Commence par « Salam aleykum Mohamed, » sur la première ligne. "
            f"Thème: {random.choice(themes)}. "
            "Évite le jargon. Pas d'emojis dans cette partie."
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=150
        )
        text = resp.choices[0].message.content.strip()
        return text
    except Exception as e:
        print(f"⚠️ GPT fallback (erreur): {e}")
        return None
# =========/ GPT =========

# ========= Sélection banque JSON =========
def pick_from_bank():
    # on privilégie hadith/coran/citations_fiables
    categories = []
    for key in ("hadith", "coran", "citations_fiables"):
        if key in BANK and isinstance(BANK[key], list) and BANK[key]:
            categories.append(key)
    if not categories:
        return None
    cat = random.choice(categories)
    txt = random.choice(BANK[cat]).strip()
    prefix_map = {
        "hadith": "🤲 Hadith : ",
        "coran": "📖 Coran : ",
        "citations_fiables": "✨ Citation : "
    }
    return f"{prefix_map.get(cat, '')}{txt}"
# =========/ Sélection banque JSON =========

# ========= Composer le message final =========
def build_message():
    global MODE
    # auto fallback si pas de clé
    effective_mode = MODE
    if not OPENAI_API_KEY and MODE in ("gpt", "hybrid"):
        effective_mode = "json"

    gpt_text = None
    bank_line = None

    if effective_mode in ("gpt", "hybrid"):
        gpt_text = generate_gpt_snippet()

    if effective_mode in ("json", "hybrid"):
        # Dans hybrid: on ajoute une ligne banque JSON ~ 50% du temps
        if effective_mode == "json" or random.random() < 0.5:
            bank_line = pick_from_bank()

    if effective_mode == "gpt" and not gpt_text:
        # rien de GPT, tente banque
        bank_line = pick_from_bank()

    # Concaténation propre
    if gpt_text and bank_line:
        msg = f"{gpt_text}\n\n{bank_line}"
    elif gpt_text:
        msg = gpt_text
    elif bank_line:
        # petite intro si pas GPT
        msg = f"Salam aleykum Mohamed,\n\n{bank_line}"
    else:
        raise ValueError("❌ Aucun contenu disponible (ni GPT, ni JSON).")

    return msg.strip()
# =========/ Composer =========

# ========= Envoi WhatsApp via Twilio =========
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
    return message.sid
# =========/ Envoi =========

if __name__ == "__main__":
    final = build_message()

    # anti-répétition : si déjà envoyé, on tente une deuxième fois (petite variation), sinon on passe
    if already_sent(final, HISTORY):
        alt = build_message()
        if not already_sent(alt, HISTORY):
            final = alt

    sid = send_whatsapp(final)
    remember(final, HISTORY)

    print(f"ℹ️ Mode effectif: {MODE} (clé GPT={'oui' if OPENAI_API_KEY else 'non'})")
    print(f"ℹ️ JSON: {CONTENT_FILE if CONTENT_FILE else 'non utilisé'} | History: {HISTORY_FILE}")
    print(f"✅ Message WhatsApp envoyé: {sid}")
