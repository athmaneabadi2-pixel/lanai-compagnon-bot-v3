import os
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, Literal

import requests

# --- Configuration API depuis l'environnement (comme tes crons) ---

RAPIDAPI_KEY_FOOT = os.getenv("RAPIDAPI_KEY_FOOT")
RAPIDAPI_KEY_BASKET = os.getenv("RAPIDAPI_KEY_BASKET")

# On met des valeurs par défaut pour les hosts RapidAPI.
# Si dans ton fichier lanai_results.py tu utilises d'autres hosts,
# mets les mêmes ici ou configure RAPIDAPI_FOOT_HOST / RAPIDAPI_BASKET_HOST dans Render.
RAPIDAPI_FOOT_HOST = os.getenv("RAPIDAPI_FOOT_HOST", "api-football-v1.p.rapidapi.com")
RAPIDAPI_BASKET_HOST = os.getenv("RAPIDAPI_BASKET_HOST", "api-basketball.p.rapidapi.com")

# --- Types ---
SportType = Literal["football", "basketball"]


# ==========================
# 1. Détection de question sport
# ==========================

def is_sports_question(text: str) -> bool:
    """
    Retourne True si le message ressemble à une question de résultat de match.
    On fait volontairement simple et large.
    """
    if not text:
        return False

    t = text.lower()

    # Mots clés typiques de questions de résultat
    keywords = ["score", "match", "résultat", "resultat", "a fait", "ont fait"]

    if any(k in t for k in keywords):
        # On évite par exemple les phrases délirantes sans sport,
        # mais là on reste simple : si ça contient 'match' ou 'score' etc., on considère que c'est sport.
        return True

    return False


# ==========================
# 2. Extraction équipe + période
# ==========================

def extract_team_name(text: str) -> Optional[str]:
    """
    Essaye d'extraire le nom de l'équipe depuis une phrase type :
    - "Qu'a fait le PSG ce week-end ?"
    - "C'était quoi le score du Real Madrid hier ?"

    On ne couvrira pas 100% des cas, mais les plus naturels.
    Si on ne trouve rien, retourne None.
    """
    if not text:
        return None

    # On garde la version originale pour les majuscules (PSG, OM, etc.)
    original = text.strip()

    # 1) Pattern : "Qu'a fait <équipe> ce week-end ?"
    m = re.search(
        r"(?i)qu[’']?a fait\s+(le|la|les|l')?\s*(.+?)\s+(ce week-end|ce weekend|hier|aujourd'hui|\?)",
        original,
    )
    if m:
        team = m.group(2).strip(" ?.!").strip()
        return team

    # 2) Pattern : "C'était quoi le score du <équipe> hier ?"
    m = re.search(
        r"(?i)score (du|de la|de l'|des)\s+(.+?)\s+(hier|aujourd'hui|ce soir|\?)",
        original,
    )
    if m:
        team = m.group(2).strip(" ?.!").strip()
        return team

    # 3) Fallback très simple : chercher après le mot "du" ou "de" avant "match" ou "score"
    m = re.search(r"(?i)(du|de la|de l'|des)\s+(.+?)\s+(match|score|résultat|resultat)", original)
    if m:
        team = m.group(2).strip(" ?.!").strip()
        return team

    return None


def extract_time_period(text: str) -> str:
    """
    Retourne une période symbolique parmi :
    - 'yesterday'
    - 'today'
    - 'weekend'
    - 'unspecified'
    """
    if not text:
        return "unspecified"

    t = text.lower()
    if "hier" in t:
        return "yesterday"
    if "aujourd'hui" in t or "aujourdhui" in t:
        return "today"
    if "ce week-end" in t or "ce weekend" in t:
        return "weekend"

    # Par défaut on prend "unspecified" -> on pourra décider de prendre "yesterday" par défaut
    return "unspecified"


# ==========================
# 3. Résolution de dates
# ==========================

def resolve_period_to_dates(period: str, today: Optional[date] = None) -> Tuple[date, date]:
    """
    Transforme une étiquette ('yesterday', 'today', 'weekend', 'unspecified')
    en deux dates (start_date, end_date) incluses.
    """
    if today is None:
        today = date.today()

    if period == "today":
        return today, today

    if period == "yesterday" or period == "unspecified":
        # 'unspecified' → on assume 'hier' par défaut, c'est plus safe.
        d = today - timedelta(days=1)
        return d, d

    if period == "weekend":
        # On prend le week-end qui vient de passer.
        # convention : samedi / dimanche juste avant la date d'aujourd'hui
        # weekday() : lundi=0 ... dimanche=6
        # On veut le samedi (5) et dimanche (6) précédents.
        # On calcule le dernier samedi <= today, si today est lun-mardi on recule plus.
        # Stratégie simple : on recule jusqu'au dernier samedi, puis dimanche = samedi + 1
        offset_to_saturday = (today.weekday() - 5) % 7  # distance en jours de today à samedi
        samedi = today - timedelta(days=offset_to_saturday or 7)  # si offset==0 -> on prend samedi dernier
        dimanche = samedi + timedelta(days=1)
        return samedi, dimanche

    # Fallback
    d = today - timedelta(days=1)
    return d, d


# ==========================
# 4. Appels API – FOOT
# ==========================

def _foot_headers() -> dict:
    return {
        "x-rapidapi-key": RAPIDAPI_KEY_FOOT,
        "x-rapidapi-host": RAPIDAPI_FOOT_HOST,
    }


def search_team_football(team_query: str) -> Optional[dict]:
    """
    Utilise l'API-Football pour chercher une équipe à partir d'un nom ou acronyme.
    Retourne un dict minimal : {"id": ..., "name": ...} ou None.
    """
    if not RAPIDAPI_KEY_FOOT:
        return None

    url = f"https://{RAPIDAPI_FOOT_HOST}/v3/teams"
    params = {"search": team_query}

    try:
        r = requests.get(url, headers=_foot_headers(), params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None

    resp = data.get("response") or []
    if not resp:
        return None

    team_info = resp[0].get("team") or resp[0]
    return {
        "id": team_info.get("id"),
        "name": team_info.get("name", team_query),
    }


def get_football_fixtures(team_id: int, start_date: date, end_date: date):
    """
    Récupère les fixtures d'une équipe entre deux dates (inclus).
    S'appuie sur l'endpoint /v3/fixtures.
    """
    if not RAPIDAPI_KEY_FOOT:
        return []

    url = f"https://{RAPIDAPI_FOOT_HOST}/v3/fixtures"
    params = {
        "team": team_id,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
    }

    try:
        r = requests.get(url, headers=_foot_headers(), params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    return data.get("response") or []


def pick_last_finished_football(fixtures: list, team_id: int) -> Optional[dict]:
    """
    Parmi la liste de fixtures, retourne le dernier match TERMINÉ pour l'équipe.
    """
    if not fixtures:
        return None

    # On trie du plus récent au plus ancien (en fonction de la date du fixture)
    def fixture_datetime(f):
        dt_str = f.get("fixture", {}).get("date")
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    fixtures_sorted = sorted(fixtures, key=fixture_datetime, reverse=True)

    for f in fixtures_sorted:
        status = f.get("fixture", {}).get("status", {}).get("short")
        if status not in ("FT", "AET", "PEN"):
            continue  # match pas terminé

        teams = f.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})

        if team_id not in (home.get("id"), away.get("id")):
            continue

        return f

    return None


def format_football_answer(team_name: str, fixture: dict) -> str:
    """
    Formate une phrase du type :
    - "Le PSG a gagné 3–1 contre Lyon ce week-end."
    """
    teams = fixture.get("teams", {})
    goals = fixture.get("goals", {})

    home = teams.get("home", {})
    away = teams.get("away", {})

    home_name = home.get("name", "Équipe domicile")
    away_name = away.get("name", "Équipe extérieur")
    home_goals = goals.get("home", 0)
    away_goals = goals.get("away", 0)

    # Déterminer si team_name est à domicile ou extérieur
    # On compare en lower pour tolérer les variations
    ln = team_name.lower()
    is_home = ln in home_name.lower()
    is_away = ln in away_name.lower()

    # Déterminer victoire / nul / défaite
    if home_goals == away_goals:
        result = "a fait match nul"
    elif (is_home and home_goals > away_goals) or (is_away and away_goals > home_goals):
        result = "a gagné"
    else:
        result = "a perdu"

    # Nom de l'adversaire
    opponent = away_name if is_home else home_name

    return f"{team_name} {result} {home_goals}–{away_goals} contre {opponent}."


# ==========================
# 5. Appels API – BASKET
# ==========================

def _basket_headers() -> dict:
    return {
        "x-rapidapi-key": RAPIDAPI_KEY_BASKET,
        "x-rapidapi-host": RAPIDAPI_BASKET_HOST,
    }


def search_team_basketball(team_query: str) -> Optional[dict]:
    """
    Cherche une équipe de basket via API-Basketball.
    """
    if not RAPIDAPI_KEY_BASKET:
        return None

    url = f"https://{RAPIDAPI_BASKET_HOST}/teams"
    params = {"search": team_query}

    try:
        r = requests.get(url, headers=_basket_headers(), params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None

    resp = data.get("response") or []
    if not resp:
        return None

    team_info = resp[0].get("team") or resp[0]
    return {
        "id": team_info.get("id"),
        "name": team_info.get("name", team_query),
    }


def get_basketball_games(team_id: int, start_date: date, end_date: date):
    """
    Récupère les matchs de basket (games) pour une équipe.
    """
    if not RAPIDAPI_KEY_BASKET:
        return []

    url = f"https://{RAPIDAPI_BASKET_HOST}/games"
    params = {
        "team": team_id,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
    }

    try:
        r = requests.get(url, headers=_basket_headers(), params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    return data.get("response") or []


def pick_last_finished_basketball(games: list, team_id: int) -> Optional[dict]:
    """
    Retourne le dernier match terminé pour l'équipe.
    """
    if not games:
        return None

    def game_datetime(g):
        dt_str = g.get("date")
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    games_sorted = sorted(games, key=game_datetime, reverse=True)

    for g in games_sorted:
        status = (g.get("status") or {}).get("short") or ""
        # Dans l'API-Basketball, 'FT' = terminé, parfois 'AOT', etc.
        if status not in ("FT", "AOT", "FT OT"):
            continue

        teams = g.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("visitors", {})

        if team_id not in (home.get("id"), away.get("id")):
            continue

        return g

    return None


def format_basketball_answer(team_name: str, game: dict) -> str:
    """
    Formate une phrase simple pour le basket.
    """
    teams = game.get("teams", {})
    scores = game.get("scores", {})

    home = teams.get("home", {})
    away = teams.get("visitors", {})

    home_name = home.get("name", "Équipe domicile")
    away_name = away.get("name", "Équipe extérieur")

    home_points = (scores.get("home") or {}).get("points", 0)
    away_points = (scores.get("visitors") or {}).get("points", 0)

    ln = team_name.lower()
    is_home = ln in home_name.lower()
    is_away = ln in away_name.lower()

    if home_points == away_points:
        result = "a fait match nul"
    elif (is_home and home_points > away_points) or (is_away and away_points > home_points):
        result = "a gagné"
    else:
        result = "a perdu"

    opponent = away_name if is_home else home_name

    return f"{team_name} {result} {home_points}–{away_points} contre {opponent}."


# ==========================
# 6. Pipeline principal : traiter une question sport
# ==========================

def handle_sports_question(text: str) -> Optional[str]:
    """
    Pipeline complet :
    - extrait équipe + période
    - résout les dates
    - tente FOOT puis BASKET
    - retourne une phrase prête à envoyer

    Retourne None si on n'a pas réussi (→ fallback GPT dans app.py).
    """
    if not text:
        return None

    team = extract_team_name(text)
    if not team:
        # On ne comprend pas l'équipe → mieux vaut laisser GPT gérer
        return None

    period = extract_time_period(text)
    start_date, end_date = resolve_period_to_dates(period)

    # 1) FOOTBALL
    if RAPIDAPI_KEY_FOOT:
        team_info_foot = search_team_football(team)
        if team_info_foot and team_info_foot.get("id"):
            fixtures = get_football_fixtures(team_info_foot["id"], start_date, end_date)
            match = pick_last_finished_football(fixtures, team_info_foot["id"])
            if match:
                # On a trouvé un match de foot
                return format_football_answer(team_info_foot["name"], match)

    # 2) BASKET (si rien trouvé en foot)
    if RAPIDAPI_KEY_BASKET:
        team_info_basket = search_team_basketball(team)
        if team_info_basket and team_info_basket.get("id"):
            games = get_basketball_games(team_info_basket["id"], start_date, end_date)
            game = pick_last_finished_basketball(games, team_info_basket["id"])
            if game:
                return format_basketball_answer(team_info_basket["name"], game)

    # Si on arrive ici, rien trouvé ou pas d'API dispo
    # On renvoie une phrase honnête.
    # Si tu préfères laisser GPT gérer, retourne None ici.
    if RAPIDAPI_KEY_FOOT or RAPIDAPI_KEY_BASKET:
        return f"Je n’ai pas trouvé de match pour {team} sur cette période."
    else:
        # Aucun accès API configuré
        return None
