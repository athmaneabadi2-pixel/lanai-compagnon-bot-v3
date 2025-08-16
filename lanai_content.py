import os
import json
import random
from twilio.rest import Client

# ======== Chargement du fichier de contenus ========
content_file = "contenu_messages.json"
if not os.path.exists(content_file):
    raise FileNotFoundError(f"❌ Fichier de contenu introuvable: {content_file}")
with open(content_file, "r", encoding="utf-8") as f:
    contenu = json.load(f)

# ======== Sélection aléatoire du type de message ========
categories = list(contenu.keys())  # ex: ["hadith", "sante", "coran", "citation"]
if not categories:
    raise ValueError("❌ Le fichier de contenu est vide ou mal formaté.")
categorie = random.choice(categories)
message_list = contenu.get(categorie, [])
if not message_list:
    raise ValueError(f"❌ La catégorie '{categorie}' ne contient aucun message.")
message_content = random.choice(message_list)

# ======== Préparation du message texte ========
if categorie == "hadith":
    prefix = "🤲 Hadith : "
elif categorie == "sante":
    prefix = "💊 Santé : "
elif categorie == "coran":
    prefix = "📖 Verset du Coran : "
elif categorie == "citation":
    prefix = "✨ Citation : "
else:
    prefix = ""

message_text = f"✨ Salam aleykum Mohamed,\n\n{prefix}{message_content}"

# ======== Envoi via Twilio WhatsApp ========
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")
receiver_whatsapp = os.environ.get("MY_WHATSAPP_NUMBER")
if not twilio_sid or not twilio_token:
    raise ValueError("❌ Identifiants Twilio manquants.")
client = Client(twilio_sid, twilio_token)
message = client.messages.create(
    from_=twilio_whatsapp,
    body=message_text,
    to=receiver_whatsapp
)

print(f"✅ Message envoyé via WhatsApp : {message.sid}")
