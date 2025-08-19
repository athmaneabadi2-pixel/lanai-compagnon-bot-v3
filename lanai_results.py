# lanai_results.py — RapidAPI (API-FOOTBALL + API-BASKETBALL)
import os
from datetime import datetime, timedelta, timezone
import requests
from twilio.rest import Client

# ========= ENV =========
RAPIDAPI_KEY_FOOT   = os.environ.get("RAPIDAPI_KEY_FOOT")
RAPIDAPI_KEY_BASKET = os.environ.get("RAPIDAPI_KEY_BASKET")
TWILIO_SID          = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN        = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP     = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ex: whatsapp:+14155238886
RECEIVER_WHATSAPP   = os.environ.get("MY_WHATSAPP_NUMBER")      # ex: whatsapp:+33XXXXXXXXX
DATE_OVERRIDE       = os.environ.get("DATE_OVERRIDE")           # ex: 2025-08-17 (optionnel)

for k, v in {
    "RAPIDAPI_KEY_FOOT": RAPIDAPI_KEY_FOOT,
    "RAPIDAPI_KEY_BASKET": RAPIDAPI_KEY_BASKET,
    "TWILIO_ACCOUNT_SID": TWILIO_SID,
    "TWILIO_AUTH_TOKEN": TWILIO_TOKEN,
    "TWILIO_WHATSAPP_NUMBER": TWILIO_WHATSAPP,
    "MY_WHATSAPP_NUMBER": RECEIVER_WHATSAPP,
}.items():
    if not v:
        raise ValueError(f"❌ Variable d'environnement manquante: {k}")

# ========= DATE =========
if DATE_OVERRIDE:
    date_iso = DATE_OVERRIDE
else:
    # "hier" en Europe/Paris
    paris = timezone(timedelta(hours=2))  # (été UTC+2 ; sinon utiliser pytz Europe/Paris si dispo)
    date_iso = (datetime.now(paris) - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 Date interrogée: {date_iso}")

# ========= SAISONS AUTO =========
def season_football(date_iso_str: str) -> int:
    d = datetime.strptime(date_iso_str, "%Y-%m-%d")
    return d.year if d.month >= 7 else d.year - 1  # ex: 2025 pour 2025/26

def season_nba(date_iso_str: str) -> str:
    d = datetime.strptime(date_iso_str, "%Y-%m-%d")
    start = d.year if d.month >= 10 else d.year - 1  # ex: 2024 pour 2024-2025
    return f"{start}-{start+1}"

SEASON_FOOT = season_football(date_iso)
SEASON_NBA  = season_nba(date_iso)
print(f"🏟️ Saison foot: {SEASON_FOOT} | 🏀 Saison NBA: {SEASON_NBA}")

# ========= CONFIG LIGUES =========
FOOTBALL_LEAGUES = [
    {"id": 61, "nom": "Ligue 1 (France)"},
    {"id": 39, "nom": "Premier League (Angleterre)"},
    # {"id": 140, "nom": "LaLiga (Espagne)"},
    # {"id": 135, "nom": "Serie A (Italie)"},
    # {"id": 78,  "nom": "Bundesliga (Allemagne)"},
]
NBA_LEAGUE_ID = 12

# ========= HELPERS =========
def req(url: str, headers: dict, params: dict):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}

# ========= FOOTBALL via RapidAPI (API-FOOTBALL) =========
# Host RapidAPI pour API-FOOTBALL :
FOOT_HOST = "api-football-v1.p.rapidapi.com"
FOOT_URL  = f"https://{FOOT_HOST}/v3/fixtures"

def get_football_results(date_iso_str: str):
    results = []
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY_FOOT,
        "x-rapidapi-host": FOOT_HOST,
    }
    for lg in FOOTBALL_LEAGUES:
        params = {
            "date": date_iso_str,
            "league": lg["id"],
            "season": SEASON_FOOT,
            "timezone": "Europe/Paris"
        }
        status, data = req(FOOT_URL, headers, params)
        print(f"⚽ {lg['nom']} status={status} params={params}")
        if status != 200 or not isinstance(data, dict):
            continue
        for fx in data.get("response", []):
            home = fx.get("teams", {}).get("home", {}).get("name")
            away = fx.get("teams", {}).get("away", {}).get("name")
            hg   = fx.get("goals", {}).get("home")
            ag   = fx.get("goals", {}).get("away")
            # statut final ?
            st_state = fx.get("fixture", {}).get("status", {}).get("short")
            # FT = fin de match, AET = après prolong., PEN = tab terminés
            if home and away and hg is not None and ag is not None and st_state in ("FT", "AET", "PEN"):
                results.append(f"{home} {hg} - {ag} {away} ({lg['nom']})")
    return results

# ========= NBA via RapidAPI (API-BASKETBALL) =========
# Host RapidAPI pour API-BASKETBALL :
BASKET_HOST = "api-basketball.p.rapidapi.com"
BASKET_URL  = f"https://{BASKET_HOST}/games"

def get_nba_results(date_iso_str: str):
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY_BASKET,
        "x-rapidapi-host": BASKET_HOST,
    }
    params = {
        "date": date_iso_str,
        "league": NBA_LEAGUE_ID,
        "season": SEASON_NBA
    }
    status, data = req(BASKET_URL, headers, params)
    print(f"🏀 NBA status={status} params={params}")
    results = []
    if status == 200 and isinstance(data, dict):
        for g in data.get("response", []):
            home = g.get("teams", {}).get("home", {}).get("name")
            away = g.get("teams", {}).get("away", {}).get("name")
            hs   = g.get("scores", {}).get("home", {}).get("total")
            as_  = g.get("scores", {}).get("away", {}).get("total")
            st   = g.get("status", {}).get("long") or g.get("status", {}).get("short")
            # on garde seulement les scores finalisés
            if home and away and hs is not None and as_ is not None and (st in ("Final", "After Over Time", "Finished") or st == "FT"):
                results.append(f"{home} {hs} - {as_} {away}")
    return results

# ========= RÉCUP DATA =========
nba_results = get_nba_results(date_iso)
football_results = get_football_results(date_iso)

# ========= MESSAGE =========
msg = f"🤾 Salam aleykum Mohamed,\nVoici les résultats du {date_iso} :\n\n"

msg += "🏀 NBA :\n"
msg += ("\n".join(f" - {l}" for l in nba_results) if nba_results else " - Aucun match (ou pas de scores finalisés).\n")
msg += "\n"

msg += "⚽ Football européen :\n"
msg += ("\n".join(f" - {l}" for l in football_results) if football_results else " - Aucun match important (ou pas de scores finalisés).\n")

# ========= ENVOI WHATSAPP =========
client = Client(TWILIO_SID, TWILIO_TOKEN)
message = client.messages.create(from_=TWILIO_WHATSAPP, body=msg, to=RECEIVER_WHATSAPP)
print(f"✅ WhatsApp envoyé (SID={message.sid})")
