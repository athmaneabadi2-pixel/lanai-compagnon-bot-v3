# lanai_results.py (DEBUG)
import os
import requests
from datetime import datetime, timedelta
from twilio.rest import Client

# ========= ENV REQUIS =========
API_SPORTS_KEY      = os.environ.get("API_SPORTS_KEY")
TWILIO_SID          = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN        = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP     = os.environ.get("TWILIO_WHATSAPP_NUMBER")   # ex: whatsapp:+14155238886
RECEIVER_WHATSAPP   = os.environ.get("MY_WHATSAPP_NUMBER")       # ex: whatsapp:+33XXXXXXXXX
DATE_OVERRIDE       = os.environ.get("DATE_OVERRIDE")            # ex: 2025-08-17 (optionnel pour test)

# === Affiche la clé (masquée) pour être sûr qu'on utilise la bonne ===
print("🔐 API key (masquée) :", (API_SPORTS_KEY[:6] + "..." + API_SPORTS_KEY[-4:]) if API_SPORTS_KEY else "MISSING")

if not API_SPORTS_KEY:
    raise ValueError("❌ API_SPORTS_KEY manquante.")
for vname, v in {
    "TWILIO_ACCOUNT_SID": TWILIO_SID,
    "TWILIO_AUTH_TOKEN": TWILIO_TOKEN,
    "TWILIO_WHATSAPP_NUMBER": TWILIO_WHATSAPP,
    "MY_WHATSAPP_NUMBER": RECEIVER_WHATSAPP,
}.items():
    if not v:
        raise ValueError(f"❌ Variable manquante: {vname}")

# ========= DATE UTILISÉE =========
if DATE_OVERRIDE:
    date_str = DATE_OVERRIDE
else:
    y = datetime.utcnow() - timedelta(days=1)
    date_str = y.strftime("%Y-%m-%d")
print("📅 Date interrogée :", date_str)

# ========= SAISONS (AUTO) =========
def saison_football(date_iso: str) -> int:
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    return d.year if d.month >= 7 else d.year - 1

def saison_nba(date_iso: str) -> str:
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    start_year = d.year if d.month >= 10 else d.year - 1
    return f"{start_year}-{start_year + 1}"

SEASON_FOOT = saison_football(date_str)
SEASON_NBA  = saison_nba(date_str)
print("🏟️ Saison foot :", SEASON_FOOT, "| 🏀 Saison NBA :", SEASON_NBA)

# ========= LIGUES =========
NBA_LEAGUE_ID = 12  # NBA
FOOTBALL_LEAGUES = [
    {"id": 61, "nom": "Ligue 1 (France)"},
    {"id": 39, "nom": "Premier League (Angleterre)"},
]

# ========= HEADERS & DOMAINES =========
headers = {"x-apisports-key": API_SPORTS_KEY}
print("🌐 Domains:", "v1.basketball.api-sports.io", "&&", "v3.football.api-sports.io")

# ========= NBA =========
nba_url = f"https://v1.basketball.api-sports.io/games?date={date_str}&league={NBA_LEAGUE_ID}&season={SEASON_NBA}"
r_nba = requests.get(nba_url, headers=headers, timeout=20)
print("🔎 NBA URL:", nba_url, "| status:", r_nba.status_code, "| sample:", (r_nba.text or "")[:180])

nba_lines = []
if r_nba.status_code == 200:
    for g in r_nba.json().get("response", []):
        home = g.get("teams", {}).get("home", {}).get("name")
        away = g.get("teams", {}).get("away", {}).get("name")
        hs   = g.get("scores", {}).get("home", {}).get("total")
        as_  = g.get("scores", {}).get("away", {}).get("total")
        if all(x is not None for x in [home, away, hs, as_]):
            nba_lines.append(f"{home} {hs} - {as_} {away}")
else:
    nba_lines.append("(erreur API NBA)")

# ========= FOOT =========
football_lines = []
for lg in FOOTBALL_LEAGUES:
    foot_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}&league={lg['id']}&season={SEASON_FOOT}"
    r_foot = requests.get(foot_url, headers=headers, timeout=20)
    print(f"🔎 FOOT {lg['nom']} URL:", foot_url, "| status:", r_foot.status_code, "| sample:", (r_foot.text or "")[:180])
    if r_foot.status_code == 200:
        for f in r_foot.json().get("response", []):
            home = f.get("teams", {}).get("home", {}).get("name")
            away = f.get("teams", {}).get("away", {}).get("name")
            hg   = f.get("goals", {}).get("home")
            ag   = f.get("goals", {}).get("away")
            if all(x is not None for x in [home, away, hg, ag]):
                football_lines.append(f"{home} {hg} - {ag} {away} ({lg['nom']})")
    else:
        football_lines.append(f"(erreur API {lg['nom']})")

# ========= MESSAGE =========
msg = f"🤾 Salam aleykum Mohamed,\nVoici les résultats du {date_str} :\n\n"
msg += "🏀 NBA :\n" + ("\n".join(f" - {l}" for l in nba_lines) if nba_lines else " - Aucun match.\n")
msg += "\n"
msg += "⚽ Football européen :\n" + ("\n".join(f" - {l}" for l in football_lines) if football_lines else " - Aucun match important.\n")

# ========= ENVOI WHATSAPP =========
client = Client(TWILIO_SID, TWILIO_TOKEN)
message = client.messages.create(from_=TWILIO_WHATSAPP, body=msg, to=RECEIVER_WHATSAPP)
print(f"✅ WhatsApp envoyé (SID={message.sid})")
