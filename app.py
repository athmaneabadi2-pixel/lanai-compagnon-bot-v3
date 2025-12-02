# app.py 
from flask import Flask, request
import os
import json
import openai
from twilio.rest import Client
from memory_store import init_schema, add_message, get_history
from concurrent.futures import ThreadPoolExecutor
from sports_query import is_sports_question, handle_sports_question

app = Flask(__name__)

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("WEBHOOK_WORKERS", "4")))


# ==== Initialisation DB (création table si besoin) ====
init_schema()

# ==== Charger la mémoire long-terme (profil Mohamed) ====
MEMORY_FILE = "memoire_mohamed_lanai.json"
if not os.path.exists(MEMORY_FILE):
    raise FileNotFoundError(f"❌ Fichier mémoire introuvable: {MEMORY_FILE}")
with open(MEMORY_FILE, "r", encoding="utf-8") as f:
    mem = json.load(f)

# ==== Construire le message système (identité + ton) ====
infos = []
infos.append(f"Prénom: {mem.get('Identité', {}).get('Prénom', 'Mohamed')}")
infos.append(f"Âge: {mem.get('Identité', {}).get('Âge', '61 ans')}")
infos.append(f"Épouse: {mem.get('Famille', {}).get('Nom de son épouse', 'Milouda')} (mariés depuis 1991)")
enfants = mem.get("Famille", {}).get("Nom(s) et âge(s) des enfants")
if enfants: infos.append(f"Enfants: {enfants}")
petits = mem.get("Famille", {}).get("Petits-enfants (noms, âges, relation)")
if petits: infos.append(f"Petits-enfants: {petits}")
infos.append(f"Profession: {mem.get('Identité', {}).get('Métier exercé', 'soudeur')} (retraité)")
relig = mem.get("Identité", {}).get("Religion", "Musulman pratiquant")
infos.append(f"Religion: {relig}")
sante = mem.get("Identité", {}).get("Particularités de santé (Parkinson, etc.)")
if sante: infos.append(f"Santé: {sante}")
sport = mem.get("Goûts", {}).get("Sport préféré")
if sport: infos.append(f"Sport préféré: {sport}")
plaisirs = mem.get("Goûts", {}).get("Plaisirs simples")
if plaisirs: infos.append(f"Plaisirs: {plaisirs}")
musique = mem.get("Goûts", {}).get("Musique/chanteur préféré")
if musique: infos.append(f"Musique: {musique}")
films = mem.get("Goûts", {}).get("Film ou série préférée")
if films: infos.append(f"Films/séries: {films}")
tonpref = mem.get("Communication", {}).get("Ton préféré")
if tonpref: infos.append(f"Ton préféré: {tonpref}")
express = mem.get("Communication", {}).get("Expressions fréquentes")
if express: infos.append(f"Expressions: {express}")

system_message_content = (
    "Voici des informations personnelles sur Mohamed Djeziri:\n"
    + "\n".join(f"- {x}" for x in infos)
    + "\n\nTu es **Lanai**, compagnon WhatsApp de Mohamed. "
      "Langage simple, phrases courtes, ton chaleureux, bienveillant et rassurant. "
      "Si pertinent, fais des clins d'œil à sa femme Milouda et à leur chat Lana. "
      "Réponds toujours en français, de manière naturelle et douce. "
      "Évite le jargon et les réponses trop longues. "
      "Tes réponses doivent faire 1 à 3 phrases maximum, sauf si on te demande clairement plus de détails. "
      "Ne termine pas systématiquement tes messages par une question. "
      "Ne relance la conversation que si l'utilisateur te pose une question ouverte, "
      "ou s'il semble en détresse et a besoin de soutien. "
      "Sinon, contente-toi de répondre clairement et tu peux conclure sans poser de nouvelle question."
)


# ==== OpenAI (v1 ou v0.28) ====
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY manquante.")
openai.api_key = OPENAI_API_KEY

def chat_gpt(messages):
    """Supporte le SDK v1 et fallback v0.28 si besoin."""
    # Tentative v1 (openai>=1.x via client completions)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e1:
        print(f"⚠️ OpenAI v1 indisponible, essai v0.28: {e1}")
    # Fallback v0.28
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e2:
        print(f"⚠️ OpenAI v0.28 échec: {e2}")
        return "Désolé, je ne peux pas répondre pour le moment."

# ==== Twilio ====
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ex 'whatsapp:+14155238886'
if not twilio_sid or not twilio_token or not twilio_whatsapp:
    raise ValueError("❌ Configuration Twilio incomplète.")
twilio_client = Client(twilio_sid, twilio_token)

# ==== Webhook WhatsApp entrant ====
# ====== Worker async (traitement en arrière-plan) ======
def _process_incoming(sender: str, incoming_msg: str, msg_sid: str | None):
    try:
        print(f"[IN] sid={msg_sid} from={sender} body={incoming_msg[:140]}", flush=True)

        # 1) Log IN (dédup via msg_sid+direction)
        try:
            add_message(
                user_phone=sender,
                role="user",
                content=incoming_msg,
                msg_sid=msg_sid,
                direction="in",
                source="webhook",
            )
        except Exception as e_db_in:
            print(f"[ERR][DB-SAVE-IN] {e_db_in}", flush=True)

        # 2) Historique + prompt
        try:
            hist = get_history(sender, limit=20)
        except Exception as e_hist:
            print(f"[ERR][DB-HIST] {e_hist}", flush=True)
            hist = []

        messages = [{"role": "system", "content": system_message_content}]
        messages.extend(hist)
        messages.append({"role": "user", "content": incoming_msg})

        # 3) Tentative de réponse via pipeline SPORT (API foot/basket)
        sports_answer = None
        try:
            if is_sports_question(incoming_msg):
                sports_answer = handle_sports_question(incoming_msg)
        except Exception as e_sport:
            print(f"[SPORTS] Erreur lors du traitement de la question sport : {e_sport}", flush=True)
            sports_answer = None

        # 4) Choix de la réponse : sport ou GPT
        if sports_answer:
            # Réponse fiable issue de l'API sport → on n'appelle pas GPT
            assistant_reply = sports_answer
        else:
            # Comportement normal : on laisse GPT gérer
            try:
                assistant_reply = chat_gpt(messages)
            except Exception as e_gpt:
                print(f"[ERR][GPT] {e_gpt}", flush=True)
                assistant_reply = "Désolé, j’ai eu un petit souci. Tu peux reformuler ?"

        # 5) Envoi WhatsApp (OUT)
        tw_sid = None
        try:
            msg = twilio_client.messages.create(
                from_=twilio_whatsapp,
                body=assistant_reply,
                to=sender
            )
            tw_sid = msg.sid
            print(f"[OUT] sid={tw_sid} to={sender}", flush=True)
        except Exception as e_tw:
            print(f"[ERR][TWILIO] {e_tw}", flush=True)

        # 6) Log OUT (dédup jour+source+hash ; msg_sid utile pour traçabilité)
        try:
            add_message(
                user_phone=sender,
                role="assistant",
                content=assistant_reply,
                msg_sid=tw_sid,
                direction="out",
                source="webhook",
            )
        except Exception as e_db_out:
            print(f"[ERR][DB-SAVE-OUT] {e_db_out}", flush=True)

    except Exception as e:
        print(f"[ERR][WORKER] {e}", flush=True)



@app.route("/webhook", methods=["POST"])
def receive_message():
    sender = request.form.get("From")  # ex 'whatsapp:+33...'
    incoming_msg = (request.form.get("Body") or "").strip()
    msg_sid = request.form.get("MessageSid")
    if not sender or not incoming_msg:
        return ("", 200)

    # Réponse immédiate → traitement en arrière-plan (évite les timeouts)
    executor.submit(_process_incoming, sender, incoming_msg, msg_sid)
    return ("", 200)


  
@app.route("/health", methods=["GET"])
def health():
    return "ok", 200


if __name__ == "__main__":
    # Render bind
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
