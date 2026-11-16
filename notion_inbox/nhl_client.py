"""NHL public API client (api-web.nhle.com — no auth required)."""

import httpx
from datetime import date as Date
from functools import lru_cache

BASE = "https://api-web.nhle.com/v1"

TEAM_ABBREV: dict[str, str] = {
    "rangers": "NYR", "new york rangers": "NYR",
    "bruins": "BOS", "boston bruins": "BOS", "boston": "BOS",
    "maple leafs": "TOR", "toronto maple leafs": "TOR", "toronto": "TOR", "leafs": "TOR",
    "canadiens": "MTL", "montreal canadiens": "MTL", "montreal": "MTL", "habs": "MTL",
    "red wings": "DET", "detroit red wings": "DET", "detroit": "DET",
    "sabres": "BUF", "buffalo sabres": "BUF", "buffalo": "BUF",
    "senators": "OTT", "ottawa senators": "OTT", "ottawa": "OTT",
    "lightning": "TBL", "tampa bay lightning": "TBL", "tampa bay": "TBL", "tampa": "TBL",
    "panthers": "FLA", "florida panthers": "FLA", "florida": "FLA",
    "hurricanes": "CAR", "carolina hurricanes": "CAR", "carolina": "CAR",
    "capitals": "WSH", "washington capitals": "WSH", "washington": "WSH",
    "penguins": "PIT", "pittsburgh penguins": "PIT", "pittsburgh": "PIT",
    "flyers": "PHI", "philadelphia flyers": "PHI", "philadelphia": "PHI",
    "devils": "NJD", "new jersey devils": "NJD", "new jersey": "NJD",
    "islanders": "NYI", "new york islanders": "NYI",
    "blue jackets": "CBJ", "columbus blue jackets": "CBJ", "columbus": "CBJ",
    "predators": "NSH", "nashville predators": "NSH", "nashville": "NSH",
    "blackhawks": "CHI", "chicago blackhawks": "CHI", "chicago": "CHI",
    "blues": "STL", "st. louis blues": "STL", "st louis": "STL",
    "wild": "MIN", "minnesota wild": "MIN", "minnesota": "MIN",
    "jets": "WPG", "winnipeg jets": "WPG", "winnipeg": "WPG",
    "avalanche": "COL", "colorado avalanche": "COL", "colorado": "COL", "avs": "COL",
    "stars": "DAL", "dallas stars": "DAL", "dallas": "DAL",
    "utah": "UTA", "utah hockey club": "UTA",
    "sharks": "SJS", "san jose sharks": "SJS", "san jose": "SJS",
    "kings": "LAK", "los angeles kings": "LAK", "los angeles": "LAK",
    "ducks": "ANA", "anaheim ducks": "ANA", "anaheim": "ANA",
    "golden knights": "VGK", "vegas golden knights": "VGK", "vegas": "VGK",
    "kraken": "SEA", "seattle kraken": "SEA", "seattle": "SEA",
    "canucks": "VAN", "vancouver canucks": "VAN", "vancouver": "VAN",
    "flames": "CGY", "calgary flames": "CGY", "calgary": "CGY",
    "oilers": "EDM", "edmonton oilers": "EDM", "edmonton": "EDM",
}

# gameState values that mean the game is finished
FINAL_STATES = {"OFF", "FINAL"}


def team_abbrev(name: str) -> str | None:
    return TEAM_ABBREV.get(name.lower().strip())


def _season_for_date(d: Date) -> str:
    """Return e.g. '20252026' for a date in the 2025-26 season."""
    y = d.year
    return f"{y}{y + 1}" if d.month >= 9 else f"{y - 1}{y}"


def _str_val(v: object) -> str:
    """Accept either a plain string or a {'default': ...} dict."""
    if isinstance(v, dict):
        return v.get("default", "")
    return str(v) if v is not None else ""


@lru_cache(maxsize=None)
def _fetch_season_schedule(abbrev: str, season: str) -> list[dict]:
    url = f"{BASE}/club-schedule-season/{abbrev}/{season}"
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("games", [])


def find_game(game_date: str, primary_team: str, opponent: str | None = None) -> dict | None:
    """
    Return the NHL schedule dict for a game on game_date involving primary_team.
    If opponent is given, also verify the other team matches.
    Returns None if not found or team name unrecognised.
    """
    abbrev = team_abbrev(primary_team)
    if not abbrev:
        return None

    d = Date.fromisoformat(game_date)
    season = _season_for_date(d)
    games = _fetch_season_schedule(abbrev, season)

    opp_abbrev = team_abbrev(opponent) if opponent else None

    for game in games:
        if game.get("gameDate") != game_date:
            continue
        if opp_abbrev:
            away = game.get("awayTeam", {}).get("abbrev")
            home = game.get("homeTeam", {}).get("abbrev")
            if opp_abbrev not in (away, home):
                continue
        return game
    return None


def get_game_detail(game_id: int) -> dict:
    url = f"{BASE}/gamecenter/{game_id}/landing"
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_game_notes(schedule_game: dict, detail: dict) -> str:
    """Build a compact, human-readable notes string from NHL data."""
    away = schedule_game["awayTeam"]
    home = schedule_game["homeTeam"]
    away_abbrev = away.get("abbrev", "")
    home_abbrev = home.get("abbrev", "")
    away_score = away.get("score", "?")
    home_score = home.get("score", "?")

    period = detail.get("periodDescriptor", {})
    suffix = {"OT": " (OT)", "SO": " (SO)"}.get(period.get("periodType", ""), "")
    score_line = f"{away_abbrev} {away_score}, {home_abbrev} {home_score}{suffix}"

    # Goal scorers
    goal_parts: list[str] = []
    for period_data in detail.get("summary", {}).get("scoring", []):
        pd = period_data.get("periodDescriptor", {})
        period_type = pd.get("periodType", "REG")
        for goal in period_data.get("goals", []):
            scorer = _str_val(goal.get("name"))
            modifier = goal.get("goalModifier", "none")
            assists = [_str_val(a.get("name")) for a in goal.get("assists", [])]

            tags: list[str] = []
            if modifier in ("pp", "sh", "en"):
                tags.append(modifier.upper())
            if period_type in ("OT", "SO"):
                tags.append(period_type)

            g = scorer
            if tags:
                g += f" ({'/'.join(tags)})"
            if assists:
                g += f" ({', '.join(assists)})"
            goal_parts.append(g)

    # Three stars
    star_parts: list[str] = []
    for s in detail.get("summary", {}).get("threeStars", [])[:3]:
        name = _str_val(s.get("name"))
        team = _str_val(s.get("teamAbbrev"))
        star_parts.append(f"{s['star']}★ {name} ({team})")

    lines = [score_line]
    if goal_parts:
        lines.append("Goals: " + " · ".join(goal_parts))
    if star_parts:
        lines.append("Stars: " + " · ".join(star_parts))

    result = "\n".join(lines)
    return result[:1900]  # Notion rich_text property cap is 2000 chars
