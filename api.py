import requests
from datetime import datetime, timedelta

BASE_URL = "https://api.football-data.org/v4"

# Competições disponíveis no plano free da football-data.org
LIGAS = {
    "Premier League": "PL",
    "La Liga": "PD",
    "Serie A": "SA",
    "Bundesliga": "BL1",
    "Champions League": "CL",
}


def _headers(api_key):
    return {"X-Auth-Token": api_key}


def _nome_time(team):
    return team.get("shortName") or team.get("name", "?")


def get_jogos(api_key, dias_a_frente=7):
    """Retorna (jogos, erros) com partidas agendadas nos próximos dias."""
    hoje = datetime.today()
    date_from = hoje.strftime("%Y-%m-%d")
    date_to = (hoje + timedelta(days=dias_a_frente)).strftime("%Y-%m-%d")

    jogos, erros = [], []

    for nome_liga, codigo in LIGAS.items():
        url = f"{BASE_URL}/competitions/{codigo}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}

        try:
            r = requests.get(url, headers=_headers(api_key), params=params, timeout=10)
            print(f"[{nome_liga}] status={r.status_code}")

            if r.status_code == 429:
                erros.append(f"Limite de requisições atingido ({nome_liga})")
                continue
            if r.status_code == 403:
                erros.append(f"{nome_liga}: sem acesso no plano atual")
                continue
            if not r.ok:
                erros.append(f"{nome_liga}: erro {r.status_code}")
                continue

            for match in r.json().get("matches", []):
                casa = _nome_time(match["homeTeam"])
                fora = _nome_time(match["awayTeam"])
                jogos.append({
                    "id": str(match["id"]),
                    "liga": nome_liga,
                    "data": match["utcDate"],
                    "casa": casa,
                    "fora": fora,
                    "label": f"[{nome_liga}] {casa} x {fora}",
                    "fonte": "api",
                })

        except requests.exceptions.RequestException as e:
            erros.append(f"{nome_liga}: {e}")

    return jogos, erros


def get_resultados(api_key, days_back=7):
    """Retorna (jogos_finalizados, erros) dos últimos dias."""
    hoje = datetime.today()
    date_from = (hoje - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = hoje.strftime("%Y-%m-%d")

    jogos, erros = [], []

    for nome_liga, codigo in LIGAS.items():
        url = f"{BASE_URL}/competitions/{codigo}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"}

        try:
            r = requests.get(url, headers=_headers(api_key), params=params, timeout=10)

            if r.status_code == 403:
                erros.append(f"{nome_liga}: sem acesso no plano atual")
                continue
            if not r.ok:
                erros.append(f"{nome_liga}: erro {r.status_code}")
                continue

            for match in r.json().get("matches", []):
                casa = _nome_time(match["homeTeam"])
                fora = _nome_time(match["awayTeam"])
                score = match.get("score", {}).get("fullTime", {})
                jogos.append({
                    "id": str(match["id"]),
                    "liga": nome_liga,
                    "data": match["utcDate"],
                    "casa": casa,
                    "fora": fora,
                    "gols_casa": score.get("home"),
                    "gols_fora": score.get("away"),
                    "label": f"[{nome_liga}] {casa} {score.get('home')}x{score.get('away')} {fora}",
                    "fonte": "api",
                })

        except requests.exceptions.RequestException as e:
            erros.append(f"{nome_liga}: {e}")

    return jogos, erros


def get_standings(api_key, competition_code):
    """Retorna (tabela, erro) com a classificação de uma competição."""
    url = f"{BASE_URL}/competitions/{competition_code}/standings"

    try:
        r = requests.get(url, headers=_headers(api_key), timeout=10)

        if r.status_code == 403:
            return None, "Sem acesso no plano atual"
        if not r.ok:
            return None, f"Erro {r.status_code}"

        tabela = []
        for group in r.json().get("standings", []):
            if group["type"] == "TOTAL":
                for row in group["table"]:
                    tabela.append({
                        "Pos": row["position"],
                        "Time": _nome_time(row["team"]),
                        "Pts": row["points"],
                        "J": row["playedGames"],
                        "V": row["won"],
                        "E": row["draw"],
                        "D": row["lost"],
                        "GP": row["goalsFor"],
                        "GC": row["goalsAgainst"],
                        "SG": row["goalDifference"],
                    })
                break

        return tabela, None

    except requests.exceptions.RequestException as e:
        return None, str(e)
