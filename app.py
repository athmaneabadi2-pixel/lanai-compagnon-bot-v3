from flask import Flask, request, jsonify
import os, json
import openai
from concurrent.futures import ThreadPoolExecutor
from twilio.rest import Client
from memory_store import init_schema, add_message_ext, get_history, ping_db

app = Flask(__name__)

# ====== DB & exécuteur ======
init_schema()
EXEC_WORKERS = int(os.environ.get("WEBHOOK_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=EXEC_WORKERS)

# ====== Mémoire longue (profil) ======
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memoire_mohamed_lanai.json")
with open(MEMORY_FILE, "r", encoding="utf-8") as f:
    mem = json.load(f)

infos = []
infos.append(f"Prénom: {mem.get('Identité', {}).get('Prénom', 'Mohamed')}")
infos.append(f"Âge: {mem.get('Identité', {}).get('Âge', '61 ans')}")
infos.append(f"Épouse: {mem.get('Famille', {}).get('Nom de son épouse', 'Milouda')} (mariés depuis 1991)")
enfants = mem.get("Famille", {}).get("Nom(s) et âge(s) des enfants")
if enfants:
    infos.append(f"Enfants: {enfants}")
petits = mem.get("Famille", {}).get("Petits-enfants (noms, âges, relation)")
if petits:
    infos.append(f"Petits-enfants: {petits}")
infos.append(f"Profession: {mem.get('Identité', {}).get('Métier exercé', 'soudeur')} (retraité)")
relig = mem.get("Identité", {}).get("Religion", "Musulman pratiquant")
infos.append(f"Religion: {relig}")
sante = mem.get("Identité", {}).get("Particularités de santé (Parkinson, etc.)")
if sante:
    infos.append(f"Santé: {sante}")
sport = mem.get("Goûts", {}).get("Sport préféré")
if sport:
    infos.append(f"Sport préféré: {sport}")
plaisirs = mem.get("Goûts", {}).get("Plaisirs simples")
if plaisirs:
    infos.append(f"Plaisirs: {plaisirs}")
musique = mem.get("Goûts", {}).get("Musique/chanteur préféré")
if musique:
    infos.append(f"Musique: {musique}")
films = mem.get("Goûts", {}).get("Film ou série préférée")
if films:
    infos.append(f"Films/séries: {films}")
tonpref = mem.get("Communication", {}).get("Ton préféré")
if tonpref:
    infos.append(f"Ton préféré: {tonpref}")
express = mem.get("Communication", {}).get("Expressions fréquentes")
if express:
    infos.append(f"Expressions: {express}")

system_message_content = (
    "Voici des informations personnelles sur Mohamed Djeziri:\n"
    + "\n".join(f"- {x}" for x in infos)
    + "\n\nTu es **Lanai**, compagnon WhatsApp de Mohamed. "
      "Langage simple, phrases courtes, ton chaleureux, bienveillant et rassurant. "
      "Si pertinent, fais des clins d'œil à sa femme Milouda et à leur chat Lana. "
      "Réponds toujours en français, de manière naturelle et douce. "
      "Évite le jargon et les réponses trop longues."
)

# ====== OpenAI ======
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY manquante.")
openai.api_key = OPENAI_API_KEY

def chat_gpt(messages):
    """Version tolérante (v1 puis fallback v0.28)."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e1:
        print(f"[ERR][GPT-v1] {e1}", flush=True)
    try:
        resp = openai.ChatCompletion.create(
            model=os.environ.get("OPENAI_MODEL_FALLBACK", "gpt-3.5-turbo"),
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e2:
        print(f"[ERR][GPT-v028] {e2}", flush=True)
        return "Désolé, je ne peux pas répondre pour le moment."

# ====== Twilio ======
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ex 'whatsapp:+14155238886'
if not (twilio_sid and twilio_token and twilio_whatsapp):
    raise ValueError("❌ Configuration Twilio incomplète.")
twilio_client = Client(twilio_sid, twilio_token)

# ====== Traitement async ======
def _process_incoming(sender: str, incoming_msg: str, msg_sid: str | None):
    """Traite un message entrant en tâche de fond (GPT + envoi Twilio)."""
    try:
        print(f"[IN] sid={msg_sid} from={sender} body={incoming_msg[:140]}", flush=True)
        # 1) Persister le message entrant (avec dédup via provider_sid)
        try:
            add_message_ext(sender, role="user", content=incoming_msg, direction="in", provider_sid=msg_sid)
        except Exception as e_db_in:
            print(f"[ERR][DB-IN] {e_db_in}", flush=True)

        # 2) Historique + GPT
        hist = get_history(sender, limit=20)
        messages = [{"role": "system", "content": system_message_content}] + hist + [{"role": "user", "content": incoming_msg}]
        try:
            assistant_reply = chat_gpt(messages)
        except Exception as e_gpt:
            print(f"[ERR][GPT] {e_gpt}", flush=True)
            assistant_reply = "Désolé, je n'ai pas bien compris. Peux-tu reformuler ?"

        # 3) Envoi WhatsApp + persistance
        try:
            msg = twilio_client.messages.create(
                from_=twilio_whatsapp,
                body=assistant_reply,
                to=sender
            )
            print(f"[OUT] sid={msg.sid} to={sender}", flush=True)
            try:
                add_message_ext(sender, role="assistant", content=assistant_reply, direction="out", provider_sid=msg.sid)
            except Exception as e_db_out:
                print(f"[ERR][DB-OUT] {e_db_out}", flush=True)
        except Exception as e_tw:
            print(f"[ERR][TWILIO-SEND] {e_tw}", flush=True)
    except Exception as e:
        print(f"[ERR][WORKER] {e}", flush=True)

# ====== Routes ======
@app.route("/webhook", methods=["POST"])  # Twilio → nous
def receive_message():
    sender = request.form.get("From")  # ex 'whatsapp:+33...'
    incoming_msg = (request.form.get("Body") or "").strip()
    msg_sid = request.form.get("MessageSid")  # utile pour dédup

    if not sender or not incoming_msg:
        return ("", 200)

    # Réponse immédiate (évite le timeout Twilio)
    executor.submit(_process_incoming, sender, incoming_msg, msg_sid)
    return ("", 200)

@app.route("/health", methods=["GET"])  # pour UptimeRobot
def health():
    ok_db = ping_db()
    return jsonify({"ok": True, "db": ok_db}), 200

@app.route("/", methods=["GET"])  # simple wake
def root():
    return "Lanai OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
