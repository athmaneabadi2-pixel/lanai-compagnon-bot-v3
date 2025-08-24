import os
import requests
from datetime import datetime, timedelta
from twilio.rest import Client
from memory_store import init_schema, add_message

# ======== Init DB ========
init_schema()  # crée la table si besoin

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
if not twilio_whatsapp or not receiver_whatsapp:
    raise ValueError("❌ Numéros WhatsApp manquants (TWILIO_WHATSAPP_NUMBER / MY_WHATSAPP_NUMBER).")

# ======== Coordonnées GPS ========
villes = {
    "Loffre": {"lat": 50.3844, "lon": 3.1069},
    "Le Cannet (où Yacine vit)": {"lat": 43.5769, "lon": 7.0191},
}

# ======== Fonction météo ========
def get_weather_tomorrow(lat, lon):
    url = (
        f"https://api.openweathermap.org/data/3.0/onecall"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=fr"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"Impossible de récupérer la météo ({type(e).__name__})"

    daily = data.get("daily", [])
    if len(daily) < 2:
        return "Prévision de demain indisponible"

    tomorrow = daily[1]
    temp = round(tomorrow["temp"]["day"])
    description = tomorrow["weather"][0]["description"].capitalize()
    humidity = tomorrow["humidity"]
    return f"{temp}°C, {description}, humidité {humidity}%"

# ======== Création du message ========
tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
message_text = f"🤲 Salam aleykum Mohamed, voici la météo de demain ({tomorrow_date}) :\n\n"

for nom, coords in villes.items():
    meteo = get_weather_tomorrow(coords["lat"], coords["lon"])
    message_text += f"🌤 {nom} : {meteo}\n"

# ======== Envoi via Twilio WhatsApp (une seule fois) ========
client = Client(twilio_sid, twilio_token)
try:
    message = client.messages.create(
        from_=twilio_whatsapp,
        body=message_text,
        to=receiver_whatsapp,
    )
    print(f"✅ Message WhatsApp envoyé : {message.sid}")
except Exception as e:
    print(f"[ERR][TWILIO] {e}")

# ======== Log en DB (dédup jour+source+hash) ========
try:
    add_message(
        user_phone=receiver_whatsapp,
        role="assistant",
        content=message_text,
        msg_sid=(message.sid if 'message' in locals() and message else None),
        direction="out",
        source="cron_weather",
    )
    print("[DB][METEO] Insert OK")
except Exception as e:
    print(f"[ERR][DB][METEO] {e}")
