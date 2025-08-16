from flask import Flask, request, jsonify
import os
import openai
import json
from twilio.rest import Client

app = Flask(__name__)

# ======== Chargement de la mémoire long-terme (memoire_mohamed_lanai.json) ========
memory_file = "memoire_mohamed_lanai.json"
if not os.path.exists(memory_file):
    raise FileNotFoundError(f"❌ Fichier mémoire introuvable: {memory_file}")
with open(memory_file, "r", encoding="utf-8") as f:
    mem = json.load(f)

# Construire le message système (contexte et ton de l'assistant)
informations = []
informations.append(f"Prénom: {mem.get('Identité', {}).get('Prénom', 'Mohamed')}")
informations.append(f"Âge: {mem.get('Identité', {}).get('Âge', '61 ans')}")
informations.append(f"Épouse: {mem.get('Famille', {}).get('Nom de son épouse', 'Milouda')} (mariés depuis 1991)")
enfants = mem.get("Famille", {}).get("Nom(s) et âge(s) des enfants")
if enfants: informations.append(f"Enfants: {enfants}")
petits = mem.get("Famille", {}).get("Petits-enfants (noms, âges, relation)")
if petits: informations.append(f"Petits-enfants: {petits}")
informations.append(f"Profession: {mem.get('Identité', {}).get('Métier exercé', 'soudeur')} (retraité)")
informations.append(f"Religion: {mem.get('Identité', {}).get('Religion', 'Musulman pratiquant')}")
health = mem.get("Identité", {}).get("Particularités de santé (Parkinson, etc.)")
if health: informations.append(f"Santé: {health}")
sport = mem.get("Goûts", {}).get("Sport préféré")
if sport: informations.append(f"Passion sport: {sport}")
plaisirs = mem.get("Goûts", {}).get("Plaisirs simples")
if plaisirs: informations.append(f"Loisirs: {plaisirs}")
music = mem.get("Goûts", {}).get("Musique/chanteur préféré")
if music: informations.append(f"Musique: {music}")
films = mem.get("Goûts", {}).get("Film ou série préférée")
if films: informations.append(f"Films favoris: {films}")
caracter = mem.get("Communication", {}).get("Ton préféré")
if caracter: informations.append(f"Ton préféré: {caracter}")
references = mem.get("Communication", {}).get("Expressions fréquentes")
if references: informations.append(f"Expressions: {references}")

system_message_content = "Voici quelques informations personnelles sur Mohamed Djeziri:\n"
system_message_content += "\n".join("- " + info for info in informations)
system_message_content += "\n\nEn tant qu'assistant personnel de Mohamed, adoptez un ton bienveillant, simple, calme et souriant. Personnalisez vos réponses avec des références à sa vie (sa femme Milouda, son chat Lana, ses souvenirs) quand cela est approprié. Conservez le contexte de la conversation pour que les échanges soient cohérents et liés les uns aux autres. Répondez toujours en français."

# Initialiser la mémoire de conversation
conversation_history = {}  # Dictionnaire pour stocker l'historique par utilisateur (numéro WhatsApp)

# ======== Configuration de l'API OpenAI ========
openai.api_key = os.environ.get("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("❌ Clé API OpenAI (OPENAI_API_KEY) manquante.")

# ======== Configuration de Twilio ========
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")
if not twilio_sid or not twilio_token or not twilio_whatsapp:
    raise ValueError("❌ Configuration Twilio incomplète.")
twilio_client = Client(twilio_sid, twilio_token)

# ======== Route pour recevoir les messages WhatsApp entrants ========
@app.route("/message", methods=["POST"])
def receive_message():
    sender = request.form.get("From")  # numéro de l'expéditeur (WhatsApp)
    incoming_msg = request.form.get("Body")  # texte du message reçu
    if not incoming_msg:
        return ("", 400)

    # Si c'est la première fois qu'on voit ce sender, initialiser son historique avec le message système
    if sender not in conversation_history:
        conversation_history[sender] = []
        conversation_history[sender].append({"role": "system", "content": system_message_content})

    # Ajouter le message utilisateur à l'historique
    conversation_history[sender].append({"role": "user", "content": incoming_msg})

    # Appel à l'API OpenAI (GPT-4)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=conversation_history[sender]
        )
        assistant_reply = response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        assistant_reply = "Désolé, je ne peux pas répondre pour le moment."

    # Ajouter la réponse de l'assistant à l'historique
    conversation_history[sender].append({"role": "assistant", "content": assistant_reply})

    # Envoyer la réponse via WhatsApp (Twilio)
    twilio_client.messages.create(
        from_=twilio_whatsapp,
        body=assistant_reply,
        to=sender
    )

    return ("", 204)  # Répondre à Twilio avec un statut 204 (pas de contenu)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
