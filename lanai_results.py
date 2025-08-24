# lanai_results.py — RapidAPI (FOOT + BASKET) + message aéré par ligue
import os
from datetime import datetime, timedelta, timezone
import requests
from twilio.rest import Client
from memory_store import init_schema, add_message  # NEW

# === Init DB (crée la table si besoin) ===
init_schema()  # NEW

# ========== ENV ==========
RAPIDAPI_KEY_FOOT   = os.environ.get("RAPIDAPI_KEY_FOOT")
RAPIDAPI_KEY_BASKET = os.environ.get("RAPIDAPI_KEY_BASKET")
TWILIO_SID          = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN        = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP     = os.environ.get("TWILIO_WHATSAPP_NUMBER")
RECEIVER_WHATSAPP   = os.environ.get("MY_WHATSAPP_NUMBER")
DATE_OVERRIDE       = os.environ.get("DATE_OVERRIDE")  # "YYYY-MM-DD" (optionnel)

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

# ========== DATE ==========
if DATE_OVERRIDE:
    date_iso = DATE_OVERRIDE
else:
    # "hier" en Europe/Paris (simple)
    paris = timezone(timedelta(hours=2))
    date_iso = (datetime.now(paris) - timedelta(days=1)).strftime("%Y-%m-%d")

# ========== HELPERS / REQ ==========
def req(url: str, headers: dict, params: dict):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}

# ========== SAISONS ==========
def season_football(date_iso_str: str) -> int:
    d = datetime.strptime(date_iso_str, "%Y-%m-%d")
    return d.year if d.month >= 7 else d.year - 1  # ex: 2025 pour 2025/26

SEASON_FOOT = season_football(date_iso)

# ========== FOOTBALL (RapidAPI / API-FOOTBALL) ==========
FOOT_HOST = "api-football-v1.p.rapidapi.com"
FOOT_URL  = f"https://{FOOT_HOST}/v3/fixtures"
FOOT_HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY_FOOT,
    "x-rapidapi-host": FOOT_HOST,
}

# IDs API-FOOTBALL
FOOT_LEAGUES = [
    {"id": 140, "nom": "LaLiga (Espagne)",   "emoji": "🇪🇸"},
    {"id": 78,  "nom": "Bundesliga (Allemagne)", "emoji": "🇩🇪"},
    {"id": 135, "nom": "Serie A (Italie)",   "emoji": "🇮🇹"},
    {"id": 61,  "nom": "Ligue 1 (France)",   "emoji": "🇫🇷"},
    {"id": 39,  "nom": "Premier League (Angleterre)", "emoji": "🏴"},
    {"id": 2,   "nom": "Ligue des Champions (UEFA)",  "emoji": "🏆"},
]

def get_football_by_league(date_iso_str: str):
    """Retourne dict { 'LaLiga (Espagne)': [ 'TeamA 2-1 TeamB', ... ], ... }"""
    results = {}
    for lg in FOOT_LEAGUES:
        params = {
            "date": date_iso_str,
            "league": lg["id"],
            "season": SEASON_FOOT,
            "timezone": "Europe/Paris"
        }
        status, data = req(FOOT_URL, FOOT_HEADERS, params)
        lines = []
        if status == 200 and isinstance(data, dict):
            for fx in data.get("response", []):
                home = fx.get("teams", {}).get("home", {}).get("name")
                away = fx.get("teams", {}).get("away", {}).get("name")
                hg   = fx.get("goals", {}).get("home")
                ag   = fx.get("goals", {}).get("away")
                st   = fx.get("fixture", {}).get("status", {}).get("short")  # FT/AET/PEN
                if home and away and hg is not None and ag is not None and st in ("FT", "AET", "PEN"):
                    lines.append(f"{home} {hg} - {ag} {away}")
        results[lg["nom"]] = {"emoji": lg["emoji"], "lines": lines}
    return results

# ========== BASKET (RapidAPI / API-BASKETBALL) ==========
BASKET_HOST = "api-basketball.p.rapidapi.com"
BASKET_URL  = f"https://{BASKET_HOST}/games"
BASKET_HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY_BASKET,
    "x-rapidapi-host": BASKET_HOST,
}

def resolve_basket_league(search_term: str):
    """Trouve l'ID + saison la plus récente pour une ligue (ex: 'Euroleague', 'France')"""
    url = f"https://{BASKET_HOST}/leagues"
    st, data = req(url, BASKET_HEADERS, {"search": search_term})
    if st != 200 or not isinstance(data, dict):
        return None, None
    best = None
    for lg in data.get("response", []):
        if search_term.lower() in lg.get("name", "").lower():
            best = lg
            break
        # fallback: si on cherche "France", garder une ligue de type "league" en France
        if search_term.lower() == "france" and lg.get("type") == "league" and lg.get("country", {}).get("name") == "France":
            best = lg
            break
    if not best:
        return None, None
    seasons = [s.get("season") for s in best.get("seasons", []) if s.get("season")]
    latest = seasons[-1] if seasons else None
    return best.get("id"), latest

# Résolution des ligues basket demandées
# - NBA (id connu: 12), saison on peut la lire via 'leagues?search=NBA' mais on garde latest si dispo
NBA_ID, NBA_SEASON = resolve_basket_league("NBA")
EUROLEAGUE_ID, EUROLEAGUE_SEASON = resolve_basket_league("Euroleague")
FR_PROA_ID, FR_PROA_SEASON = resolve_basket_league("France")  # Pro A / Betclic Élite

# fallback si non résolu
if not NBA_ID: NBA_ID = 12

BASKET_LEAGUES = [
    {"id": NBA_ID,        "nom": "NBA",        "season": NBA_SEASON},
    {"id": EUROLEAGUE_ID, "nom": "EuroLeague", "season": EUROLEAGUE_SEASON},
    {"id": FR_PROA_ID,    "nom": "Betclic Élite (France)", "season": FR_PROA_SEASON},
]
# retirer ligues non résolues
BASKET_LEAGUES = [lg for lg in BASKET_LEAGUES if lg["id"]]

def get_basket_by_league(date_iso_str: str):
    """Retourne dict { 'NBA': [ 'TeamA 88-80 TeamB', ...], 'EuroLeague': [...] }"""
    results = {}
    for lg in BASKET_LEAGUES:
        params = {
            "date": date_iso_str,
            "league": lg["id"],
            # Si l'API fournit 'season' (format 'YYYY-YYYY+1'), on l'utilise, sinon on omet (certains endpoints déduisent)
        }
        if lg.get("season"):
            params["season"] = lg["season"]
        st, data = req(BASKET_URL, BASKET_HEADERS, params)
        lines = []
        if st == 200 and isinstance(data, dict):
            for g in data.get("response", []):
                home = g.get("teams", {}).get("home", {}).get("name")
                away = g.get("teams", {}).get("away", {}).get("name")
                hs   = g.get("scores", {}).get("home", {}).get("total")
                as_  = g.get("scores", {}).get("away", {}).get("total")
                stg  = (g.get("status", {}) or {}).get("long") or (g.get("status", {}) or {}).get("short")
                if home and away and hs is not None and as_ is not None and stg in ("Final", "Finished", "After Over Time", "FT"):
                    lines.append(f"{home} {hs} - {as_} {away}")
        results[lg["nom"]] = {"emoji": "🏀", "lines": lines}
    return results

# ========== RÉCUP ==========
foot_by_league   = get_football_by_league(date_iso)
basket_by_league = get_basket_by_league(date_iso)

# ========== FORMAT MSG ==========
def format_section(title_emoji: str, title_text: str, league_dict: dict, bullet=" - "):
    out = f"{title_emoji} {title_text} :\n"
    for lig_name, data in league_dict.items():
        em = data.get("emoji", "•")
        lines = data.get("lines", [])
        out += f"{em} {lig_name} :\n"
        if lines:
            out += "\n".join(f"{bullet}{l}" for l in lines) + "\n"
        else:
            out += f"{bullet}Aucun match (ou pas de scores finalisés).\n"
        out += "\n"
    return out

msg = f"🤾 Salam aleykum Mohamed,\nVoici les résultats du {date_iso} :\n\n"
msg += format_section("🏀", "Basket", basket_by_league)
msg += format_section("⚽", "Football européen", foot_by_league)

# ========== ENVOI WHATSAPP ==========
client = Client(TWILIO_SID, TWILIO_TOKEN)
message = client.messages.create(from_=TWILIO_WHATSAPP, body=msg.strip(), to=RECEIVER_WHATSAPP)
print(f"✅ WhatsApp envoyé (SID={message.sid})")

# ========== LOG EN DB (dédup jour+source+hash) ==========
try:
    add_message(
        user_phone=RECEIVER_WHATSAPP,
        role="assistant",
        content=msg.strip(),
        msg_sid=(message.sid if 'message' in locals() and message else None),
        direction="out",
        source="cron_results",
    )
    print("[DB][RESULTS] Insert OK")
except Exception as e:
    print(f"[ERR][DB][RESULTS] {e}")

