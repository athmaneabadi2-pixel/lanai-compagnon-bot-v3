# lanai_results.py — version gratuite (ESPN + balldontlie)
import os
from datetime import datetime, timedelta, timezone
import requests
from twilio.rest import Client

# ============ ENV ============
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.environ.get("TWILIO_WHATSAPP_NUMBER")
RECEIVER_WHATSAPP = os.environ.get("MY_WHATSAPP_NUMBER")
DATE_OVERRIDE = os.environ.get("DATE_OVERRIDE")  # "YYYY-MM-DD" (optionnel pour tests)

for k, v in {
    "TWILIO_ACCOUNT_SID": TWILIO_SID,
    "TWILIO_AUTH_TOKEN": TWILIO_TOKEN,
    "TWILIO_WHATSAPP_NUMBER": TWILIO_WHATSAPP,
    "MY_WHATSAPP_NUMBER": RECEIVER_WHATSAPP,
}.items():
    if not v:
        raise ValueError(f"❌ Variable d'environnement manquante: {k}")

# ============ DATE ============
if DATE_OVERRIDE:
    date_iso = DATE_OVERRIDE
else:
    # "hier" en Europe/Paris
    paris = timezone(timedelta(hours=2))  # Render affiche souvent UTC+2 l’été; sinon utils: Europe/Paris
    date_iso = (datetime.now(paris) - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 Date interrogée: {date_iso}")

# ============ HELPERS ============
def yyyymmdd(date_iso_str: str) -> str:
    """Convertit 2025-08-17 -> 20250817 pour ESPN."""
    return date_iso_str.replace("-", "")

def safe_get(url: str):
    try:
        r = requests.get(url, timeout=20)
        return r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)
    except Exception as e:
        return 0, {"error": str(e)}

# ============ FOOTBALL (ESPN) ============
# Codes ESPN principaux: PL=eng.1, L1=fra.1, LaLiga=esp.1, Serie A=ita.1, Bundesliga=ger.1
FOOTBALL_LEAGUES = [
    {"code": "eng.1", "nom": "Premier League"},
    {"code": "fra.1", "nom": "Ligue 1"},
    # {"code": "esp.1", "nom": "LaLiga"},
    # {"code": "ita.1", "nom": "Serie A"},
    # {"code": "ger.1", "nom": "Bundesliga"},
]

def get_espn_football_results(date_iso_str: str):
    d = yyyymmdd(date_iso_str)
    results = []
    for lg in FOOTBALL_LEAGUES:
        url = f"https://site.api.espn.com/apis/v2/sports/soccer/{lg['code']}/scoreboard?dates={d}"
        status, data = safe_get(url)
        print(f"⚽️ ESPN {lg['nom']} status={status} url={url}")
        if status != 200 or not isinstance(data, dict):
            continue
        events = data.get("events", []) or data.get("schedule", {}).get("events", [])
        for ev in events:
            comp = ev.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            # scores finalisés
            hs = home.get("score")
            as_ = away.get("score")
            status_type = comp.get("status", {}).get("type", {}).get("state")
            if hs is not None and as_ is not None and status_type in ("post", "final"):
                results.append(f"{home.get('team',{}).get('displayName')} {hs} - {as_} {away.get('team',{}).get('displayName')} ({lg['nom']})")
    return results

# ============ NBA (ESPN + fallback balldontlie) ============
def get_espn_nba_results(date_iso_str: str):
    d = yyyymmdd(date_iso_str)
    url = f"https://site.api.espn.com/apis/v2/sports/basketball/nba/scoreboard?dates={d}"
    status, data = safe_get(url)
    print(f"🏀 ESPN NBA status={status} url={url}")
    results = []
    if status == 200 and isinstance(data, dict):
        events = data.get("events", []) or data.get("schedule", {}).get("events", [])
        for ev in events:
            comp = ev.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            status_type = comp.get("status", {}).get("type", {}).get("state")
            hs = home.get("score") if home else None
            as_ = away.get("score") if away else None
            if hs is not None and as_ is not None and status_type in ("post", "final"):
                results.append(f"{home.get('team',{}).get('displayName')} {hs} - {as_} {away.get('team',{}).get('displayName')}")
    return results

def get_balldontlie_nba_results(date_iso_str: str):
    # balldontlie: https://www.balldontlie.io/api/v1/games?dates[]=YYYY-MM-DD
    url = f"https://www.balldontlie.io/api/v1/games?dates[]={date_iso_str}&per_page=100"
    status, data = safe_get(url)
    print(f"🏀 balldontlie status={status} url={url}")
    results = []
    if status == 200 and isinstance(data, dict):
        for g in data.get("data", []):
            # final only
            if g.get("status") in ("Final", "final"):
                home = g.get("home_team", {}).get("full_name")
                away = g.get("visitor_team", {}).get("full_name")
                hs = g.get("home_team_score")
                as_ = g.get("visitor_team_score")
                if None not in (home, away, hs, as_):
                    results.append(f"{home} {hs} - {as_} {away}")
    return results

# ============ Récupération ============
nba_results = get_espn_nba_results(date_iso)
if not nba_results:
    nba_results = get_balldontlie_nba_results(date_iso)

football_results = get_espn_football_results(date_iso)

# ============ Message ============
msg = f"🤾 Salam aleykum Mohamed,\nVoici les résultats du {date_iso} :\n\n"

msg += "🏀 NBA :\n"
msg += ("\n".join(f" - {l}" for l in nba_results) if nba_results else " - Aucun match (ou pas de scores finalisés).\n")
msg += "\n"

msg += "⚽ Football européen :\n"
msg += ("\n".join(f" - {l}" for l in football_results) if football_results else " - Aucun match important (ou pas de scores finalisés).\n")

# ============ Envoi WhatsApp ============
client = Client(TWILIO_SID, TWILIO_TOKEN)
message = client.messages.create(from_=TWILIO_WHATSAPP, body=msg, to=RECEIVER_WHATSAPP)
print(f"✅ WhatsApp envoyé (SID={message.sid})")
