import requests
import os
from datetime import datetime, timedelta
from twilio.rest import Client

# ======== Clés API et config depuis .env ========
api_key = os.environ.get("OPENWEATHER_API_KEY")
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ex: whatsapp:+14155238886
receiver_whatsapp = os.environ.get("MY_WHATSAPP_NUMBER")    # ex: whatsapp:+33XXXXXXXXX

if not api_key:
    raise ValueError("❌ Clé API météo manquante.")
if not twilio_sid or not twilio_token:
    raise ValueError("❌ Identifiants Twilio manquants.")

# ======== Coordonnées GPS ========
villes = {
    "Loffre": {"lat": 50.3844, "lon": 3.1069},
    "Le Cannet (où Yacine vit)": {"lat": 43.5769, "lon": 7.0191}
}

# ======== Fonction météo ========
def get_weather_tomorrow(lat, lon):
    url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=fr"
    response = requests.get(url)

    if response.status_code != 200:
        return f"Impossible de récupérer la météo (code {response.status_code})"

    data = response.json()

    if "daily" not in data:
        return "Impossible de trouver la météo de demain"

    tomorrow_data = data["daily"][1]
    temp = round(tomorrow_data["temp"]["day"])
    description = tomorrow_data["weather"][0]["description"].capitalize()
    humidity = tomorrow_data["humidity"]

    return f"{temp}°C, {description}, humidité {humidity}%"

# ======== Création du message ========
tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
message_text = f"🤲 Salam aleykum Mohamed, voici la météo de demain ({tomorrow_date}) :\n\n"

for nom, coords in villes.items():
    meteo = get_weather_tomorrow(coords["lat"], coords["lon"])
    message_text += f"🌤 {nom} : {meteo}\n"

# ======== Envoi via Twilio WhatsApp ========
client = Client(twilio_sid, twilio_token)
message = client.messages.create(
    from_=twilio_whatsapp,
    body=message_text,
    to=receiver_whatsapp
)

print(f"✅ Message envoyé sur WhatsApp : {message.sid}")
