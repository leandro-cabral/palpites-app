import requests
from datetime import datetime, timedelta

BASE_URL = "https://api.football-data.org/v4"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_BASE_V2 = "https://site.api.espn.com/apis/v2/sports/soccer"

# Competições disponíveis no plano free da football-data.org
LIGAS = {
    "Premier League": "PL",
    "La Liga": "PD",
    "Serie A": "SA",
    "Bundesliga": "BL1",
    "Champions League": "CL",
}

# Ligas ESPN (sem autenticação)
LIGAS_ESPN = {
    "Brasileirão": "bra.1",
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


# ── ESPN (Brasileirão) ────────────────────────────────────────────────────────

def get_jogos_espn(dias_a_frente=7):
    """Retorna jogos agendados do Brasileirão via ESPN."""
    hoje = datetime.today()
    jogos = []

    for i in range(dias_a_frente + 1):
        data = (hoje + timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(
                f"{ESPN_BASE}/bra.1/scoreboard",
                params={"dates": data},
                timeout=10,
            )
            if not r.ok:
                continue

            for evento in r.json().get("events", []):
                comp = evento["competitions"][0]
                status = comp["status"]["type"]["name"]

                if status != "STATUS_SCHEDULED":
                    continue

                times = {t["homeAway"]: t for t in comp["competitors"]}
                casa = times["home"]["team"]["shortDisplayName"]
                fora = times["away"]["team"]["shortDisplayName"]

                jogos.append({
                    "id": f"espn_{evento['id']}",
                    "liga": "Brasileirão",
                    "data": comp["date"],
                    "casa": casa,
                    "fora": fora,
                    "label": f"[Brasileirão] {casa} x {fora}",
                    "fonte": "espn",
                })

        except requests.exceptions.RequestException:
            pass

    return jogos


def get_resultados_espn(days_back=7):
    """Retorna resultados finalizados do Brasileirão via ESPN."""
    hoje = datetime.today()
    jogos = []

    for i in range(1, days_back + 1):
        data = (hoje - timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(
                f"{ESPN_BASE}/bra.1/scoreboard",
                params={"dates": data},
                timeout=10,
            )
            if not r.ok:
                continue

            for evento in r.json().get("events", []):
                comp = evento["competitions"][0]
                status = comp["status"]["type"]["name"]

                if status != "STATUS_FINAL":
                    continue

                times = {t["homeAway"]: t for t in comp["competitors"]}
                casa = times["home"]["team"]["shortDisplayName"]
                fora = times["away"]["team"]["shortDisplayName"]
                gc = int(times["home"].get("score", 0))
                gf = int(times["away"].get("score", 0))

                jogos.append({
                    "id": f"espn_{evento['id']}",
                    "liga": "Brasileirão",
                    "data": comp["date"],
                    "casa": casa,
                    "fora": fora,
                    "gols_casa": gc,
                    "gols_fora": gf,
                    "label": f"[Brasileirão] {casa} {gc}x{gf} {fora}",
                    "fonte": "espn",
                })

        except requests.exceptions.RequestException:
            pass

    return jogos


def get_standings_espn():
    """Retorna classificação do Brasileirão via ESPN."""
    try:
        r = requests.get(f"{ESPN_BASE_V2}/bra.1/standings", timeout=10)
        if not r.ok:
            return None, f"Erro {r.status_code}"

        entries = []
        for child in r.json().get("children", []):
            entries = child.get("standings", {}).get("entries", [])
            if entries:
                break

        tabela = []
        for i, entry in enumerate(entries, 1):
            stats = {s["name"]: s.get("value", 0) for s in entry.get("stats", [])}
            tabela.append({
                "Pos": int(stats.get("rank", i)),
                "Time": entry["team"]["shortDisplayName"],
                "Pts": int(stats.get("points", 0)),
                "J": int(stats.get("gamesPlayed", 0)),
                "V": int(stats.get("wins", 0)),
                "E": int(stats.get("ties", 0)),
                "D": int(stats.get("losses", 0)),
                "GP": int(stats.get("pointsFor", 0)),
                "GC": int(stats.get("pointsAgainst", 0)),
                "SG": int(stats.get("pointDifferential", 0)),
            })

        tabela.sort(key=lambda x: x["Pos"])
        return tabela, None

    except requests.exceptions.RequestException as e:
        return None, str(e)


# ── football-data.org ─────────────────────────────────────────────────────────

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
