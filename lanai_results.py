import requests
import os
from datetime import datetime, timedelta
from twilio.rest import Client

# ======== Clés API et configuration depuis .env ========
api_sports_key = os.environ.get("API_SPORTS_KEY")  # Clé API pour API-SPORTS (sports data)
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # e.g., 'whatsapp:+14155238886'
receiver_whatsapp = os.environ.get("MY_WHATSAPP_NUMBER")    # e.g., 'whatsapp:+33XXXXXXXXX'

if not api_sports_key:
    raise ValueError("❌ Clé API sports manquante (API_SPORTS_KEY).")
if not twilio_sid or not twilio_token:
    raise ValueError("❌ Identifiants Twilio manquants.")

# ======== Dates ========
# Option de test : si DATE_OVERRIDE est défini (YYYY-MM-DD), on l'utilise.
date_override = os.environ.get("DATE_OVERRIDE")

if date_override:
    date_str = date_override
else:
    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")

print(f"ℹ️ Date interrogée: {date_str}")


# ======== Préparation des URLs de requête pour les résultats ========
# Note: 'league' et 'season' doivent correspondre à la NBA et aux ligues de football choisies.
# Par exemple, league=12, season=2024-2025 pour la NBA (à vérifier dans la documentation API-SPORTS).
nba_url = f"https://v1.basketball.api-sports.io/games?date={date_str}&league=12&season=2024-2025"
# Pour le football, on peut inclure plusieurs ligues européennes majeures (Ligue 1, Premier League, etc.).
football_leagues = [
    {"id": 61, "season": 2023, "nom": "Ligue 1 (France)"},       # Ligue 1 française (saison 2023/24)
    {"id": 39, "season": 2023, "nom": "Premier League (Angleterre)"}  # Premier League anglaise (saison 2023/24)
    # On peut ajouter d'autres ligues ou coupes européennes ici si désiré.
]

# ======== Requête API pour les résultats NBA ========
headers = {
    "x-apisports-key": api_sports_key,
    "x-apisports-host": "v1.basketball.api-sports.io"
}
response_nba = requests.get(nba_url, headers=headers)
nba_results = []
if response_nba.status_code == 200:
    data_nba = response_nba.json()
    games = data_nba.get("response", [])
    for game in games:
        home_team = game.get("teams", {}).get("home", {}).get("name")
        away_team = game.get("teams", {}).get("away", {}).get("name")
        home_score = game.get("scores", {}).get("home", {}).get("total")
        away_score = game.get("scores", {}).get("away", {}).get("total")
        if home_team and away_team and home_score is not None and away_score is not None:
            nba_results.append(f"{home_team} {home_score} - {away_score} {away_team}")
else:
    nba_results.append("Impossible de récupérer les résultats NBA (erreur API).")

# ======== Requête API pour les résultats de football ========
football_results = []
for league in football_leagues:
    league_id = league["id"]
    season = league["season"]
    league_name = league["nom"]
    football_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}&league={league_id}&season={season}"
    # Note: l'API football peut utiliser une URL différente (ici v3). Vérifiez la documentation et ajustez si nécessaire.
    response_foot = requests.get(football_url, headers={
        "x-apisports-key": api_sports_key,
        "x-apisports-host": "v3.football.api-sports.io"
    })
    if response_foot.status_code == 200:
        data_foot = response_foot.json()
        fixtures = data_foot.get("response", [])
        if fixtures:
            for fix in fixtures:
                home_team = fix.get("teams", {}).get("home", {}).get("name")
                away_team = fix.get("teams", {}).get("away", {}).get("name")
                home_goals = fix.get("goals", {}).get("home")
                away_goals = fix.get("goals", {}).get("away")
                if home_team and away_team and home_goals is not None and away_goals is not None:
                    football_results.append(f"{home_team} {home_goals} - {away_goals} {away_team} ({league_name})")
        else:
            # Pas de matchs pour cette date/ligue
            pass
    else:
        football_results.append(f"Impossible de récupérer les résultats de {league_name} (erreur API).")

# ======== Construction du message ========
message_text = "🤾 Salam aleykum Mohamed, voici les résultats sports de la veille :\n\n"
# Ajouter les résultats NBA
message_text += "🏀 NBA (hier) :\n"
if nba_results:
    for res in nba_results:
        message_text += f" - {res}\n"
else:
    message_text += "Aucun match NBA hier.\n"
message_text += "\n"
# Ajouter les résultats de football
message_text += "⚽ Football européen (hier) :\n"
if football_results:
    for res in football_results:
        message_text += f" - {res}\n"
else:
    message_text += "Aucun match important hier en foot.\n"

# ======== Envoi via Twilio WhatsApp ========
client = Client(twilio_sid, twilio_token)
message = client.messages.create(
    from_=twilio_whatsapp,
    body=message_text,
    to=receiver_whatsapp
)

print(f"✅ Message envoyé via WhatsApp (SID={message.sid})")
