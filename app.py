# app.py
from flask import Flask, request
import os
import json
import openai
from twilio.rest import Client
from memory_store import init_schema, add_message, get_history

app = Flask(__name__)

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
      "Évite le jargon et les réponses trop longues."
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
@app.route("/message", methods=["POST"])
def receive_message():
    sender = request.form.get("From")  # ex 'whatsapp:+33...'
    incoming_msg = (request.form.get("Body") or "").strip()
    if not sender:
        return ("", 204)
    if not incoming_msg:
        # Rien à dire mais on loggue côté DB pour la forme si besoin
        return ("", 204)

    # 1) Charger historique partagé (20 derniers messages)
    hist = get_history(sender, limit=20)

    # 2) Construire prompt => system + hist + nouveau user
    messages = [{"role": "system", "content": system_message_content}]
    messages.extend(hist)
    messages.append({"role": "user", "content": incoming_msg})

    # 3) GPT
    assistant_reply = chat_gpt(messages)

    # 4) Persister user + assistant en DB
    try:
        add_message(sender, "user", incoming_msg)
        add_message(sender, "assistant", assistant_reply)
    except Exception as e:
        print(f"⚠️ Erreur DB (save): {e}")

    # 5) Répondre via WhatsApp
    try:
        twilio_client.messages.create(
            from_=twilio_whatsapp,
            body=assistant_reply,
            to=sender
        )
    except Exception as e:
        print(f"⚠️ Erreur Twilio: {e}")

    return ("", 204)

if __name__ == "__main__":
    # Render bind
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
