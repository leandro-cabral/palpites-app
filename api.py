import re
import requests
from difflib import SequenceMatcher
from datetime import datetime, timedelta

BASE_URL     = "https://api.football-data.org/v4"
ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_BASE_V2 = "https://site.api.espn.com/apis/v2/sports/soccer"
ODDS_BASE    = "https://api.the-odds-api.com/v4"

# football-data.org — plano free
LIGAS = {
    "Premier League":   "PL",
    "La Liga":          "PD",
    "Serie A":          "SA",
    "Bundesliga":       "BL1",
    "Champions League": "CL",
}

# The Odds API — chaves de esporte
LIGAS_ODDS = {
    "Premier League":   "soccer_epl",
    "La Liga":          "soccer_spain_la_liga",
    "Serie A":          "soccer_italy_serie_a",
    "Bundesliga":       "soccer_germany_bundesliga",
    "Champions League": "soccer_uefa_champs_league",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers_fd(api_key):
    return {"X-Auth-Token": api_key}


def _nome_time(team):
    return team.get("shortName") or team.get("name", "?")


def _normalizar(nome):
    """Normaliza nome de time para matching entre APIs."""
    nome = nome.lower()
    for token in [" fc", " cf", " sc", " ac", " afc", " ssc", " as ", " ss ",
                  " utd", " united", " city", " hotspur", " wanderers",
                  " athletic", " sport", " sporting", " club", " de "]:
        nome = nome.replace(token, " ")
    nome = re.sub(r"[^a-z0-9 ]", "", nome)
    return re.sub(r"\s+", " ", nome).strip()


def _similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _melhor_match(home_k, away_k, odds_map, threshold=0.72):
    """
    Tenta encontrar o melhor par (home, away) no odds_map.
    1. Busca exata
    2. Busca por substring (um nome contém o outro)
    3. Fuzzy matching com difflib
    """
    # 1. Exato
    if (home_k, away_k) in odds_map:
        return odds_map[(home_k, away_k)]

    best_score, best = 0.0, None
    for (h, a), val in odds_map.items():
        # 2. Substring
        home_ok = home_k in h or h in home_k
        away_ok = away_k in a or a in away_k
        if home_ok and away_ok:
            return val

        # 3. Fuzzy
        score = (_similaridade(home_k, h) + _similaridade(away_k, a)) / 2
        if score > best_score:
            best_score, best = score, val

    return best if best_score >= threshold else None


def _odd_apostada(palpite_casa, palpite_fora, odds_casa, odds_empate, odds_fora):
    """Retorna a odd correspondente ao resultado previsto pelo palpite."""
    if palpite_casa > palpite_fora:
        return odds_casa
    if palpite_casa < palpite_fora:
        return odds_fora
    return odds_empate


# ── The Odds API ──────────────────────────────────────────────────────────────

def get_odds(odds_api_key):
    """
    Busca odds h2h de todas as ligas europeias.
    Retorna dict: {(home_norm, away_norm): {casa, empate, fora}}
    Cache de 12h recomendado — ~5 requisições por chamada.
    """
    resultado = {}

    for liga, sport_key in LIGAS_ODDS.items():
        try:
            r = requests.get(
                f"{ODDS_BASE}/sports/{sport_key}/odds",
                params={
                    "apiKey": odds_api_key,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=10,
            )
            if not r.ok:
                continue

            for match in r.json():
                bookmakers = match.get("bookmakers", [])
                if not bookmakers:
                    continue

                outcomes = bookmakers[0]["markets"][0]["outcomes"]
                odds_dict = {o["name"]: o["price"] for o in outcomes}

                home_key = _normalizar(match["home_team"])
                away_key = _normalizar(match["away_team"])

                resultado[(home_key, away_key)] = {
                    "odds_casa":    odds_dict.get(match["home_team"], 2.0),
                    "odds_empate":  odds_dict.get("Draw", 3.2),
                    "odds_fora":    odds_dict.get(match["away_team"], 2.0),
                }

        except requests.exceptions.RequestException:
            pass

    return resultado


def _mesclar_odds(jogo, odds_map):
    """Mescla odds no objeto jogo usando exact → substring → fuzzy matching."""
    home_k = _normalizar(jogo["casa"])
    away_k = _normalizar(jogo["fora"])
    match  = _melhor_match(home_k, away_k, odds_map) or {}
    jogo["odds_casa"]   = match.get("odds_casa")
    jogo["odds_empate"] = match.get("odds_empate")
    jogo["odds_fora"]   = match.get("odds_fora")
    return jogo


# ── Odds calculadas por tabela (Brasileirão) ──────────────────────────────────

def calcular_odds_por_pontos(pts_h, j_h, pts_a, j_a):
    """
    Calcula odds aproximadas com base nos pontos por jogo.
    Inclui vantagem de jogar em casa (+15%).
    """
    ppg_h = (pts_h / max(j_h, 1)) * 1.15
    ppg_a =  pts_a / max(j_a, 1)
    total = ppg_h + ppg_a

    if total == 0:
        return 2.10, 3.20, 3.50  # odds neutras para início de temporada

    sh = ppg_h / total
    sa = ppg_a / total

    p_draw = max(0.18, min(0.35, 0.28 - abs(sh - sa) * 0.3))
    rem    = 1 - p_draw
    p_h    = rem * sh
    p_a    = rem * sa

    margin = 0.92
    odds_h = round(margin / max(p_h,    0.05), 2)
    odds_d = round(margin / max(p_draw, 0.10), 2)
    odds_a = round(margin / max(p_a,    0.05), 2)

    return odds_h, odds_d, odds_a


# ── football-data.org ─────────────────────────────────────────────────────────

def get_jogos(api_key, dias_a_frente=7):
    """Retorna (jogos, erros) com partidas agendadas nos próximos dias."""
    hoje     = datetime.today()
    date_from = hoje.strftime("%Y-%m-%d")
    date_to   = (hoje + timedelta(days=dias_a_frente)).strftime("%Y-%m-%d")

    jogos, erros = [], []

    for nome_liga, codigo in LIGAS.items():
        url    = f"{BASE_URL}/competitions/{codigo}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}

        try:
            r = requests.get(url, headers=_headers_fd(api_key), params=params, timeout=10)

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
                    "id":         str(match["id"]),
                    "liga":       nome_liga,
                    "data":       match["utcDate"],
                    "casa":       casa,
                    "fora":       fora,
                    "logo_casa":  match["homeTeam"].get("crest", ""),
                    "logo_fora":  match["awayTeam"].get("crest", ""),
                    "label":      f"[{nome_liga}] {casa} x {fora}",
                    "fonte":      "api",
                    "odds_casa":   None,
                    "odds_empate": None,
                    "odds_fora":   None,
                })

        except requests.exceptions.RequestException as e:
            erros.append(f"{nome_liga}: {e}")

    return jogos, erros


def get_resultados(api_key, days_back=7):
    """Retorna (jogos_finalizados, erros) dos últimos dias."""
    hoje      = datetime.today()
    date_from = (hoje - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to   = hoje.strftime("%Y-%m-%d")

    jogos, erros = [], []

    for nome_liga, codigo in LIGAS.items():
        url    = f"{BASE_URL}/competitions/{codigo}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"}

        try:
            r = requests.get(url, headers=_headers_fd(api_key), params=params, timeout=10)

            if r.status_code == 403:
                erros.append(f"{nome_liga}: sem acesso no plano atual")
                continue
            if not r.ok:
                erros.append(f"{nome_liga}: erro {r.status_code}")
                continue

            for match in r.json().get("matches", []):
                casa  = _nome_time(match["homeTeam"])
                fora  = _nome_time(match["awayTeam"])
                score = match.get("score", {}).get("fullTime", {})
                jogos.append({
                    "id":        str(match["id"]),
                    "liga":      nome_liga,
                    "data":      match["utcDate"],
                    "casa":      casa,
                    "fora":      fora,
                    "logo_casa": match["homeTeam"].get("crest", ""),
                    "logo_fora": match["awayTeam"].get("crest", ""),
                    "gols_casa": score.get("home"),
                    "gols_fora": score.get("away"),
                    "label":     f"[{nome_liga}] {casa} {score.get('home')}x{score.get('away')} {fora}",
                    "fonte":     "api",
                })

        except requests.exceptions.RequestException as e:
            erros.append(f"{nome_liga}: {e}")

    return jogos, erros


def get_standings(api_key, competition_code):
    """Retorna (tabela, erro) com a classificação de uma competição."""
    url = f"{BASE_URL}/competitions/{competition_code}/standings"

    try:
        r = requests.get(url, headers=_headers_fd(api_key), timeout=10)

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
                        "Escudo": row["team"].get("crest", ""),
                        "Pts": row["points"],
                        "J":   row["playedGames"],
                        "V":   row["won"],
                        "E":   row["draw"],
                        "D":   row["lost"],
                        "GP":  row["goalsFor"],
                        "GC":  row["goalsAgainst"],
                        "SG":  row["goalDifference"],
                    })
                break

        return tabela, None

    except requests.exceptions.RequestException as e:
        return None, str(e)


# ── ESPN (Brasileirão + Libertadores) ────────────────────────────────────────

def _get_jogos_espn_liga(liga_espn: str, nome_liga: str, dias_a_frente: int = 7):
    """Genérico: retorna jogos agendados de qualquer liga ESPN."""
    hoje  = datetime.today()
    jogos = []

    for i in range(dias_a_frente + 1):
        data = (hoje + timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(
                f"{ESPN_BASE}/{liga_espn}/scoreboard",
                params={"dates": data},
                timeout=10,
            )
            if not r.ok:
                continue

            for evento in r.json().get("events", []):
                comp       = evento["competitions"][0]
                status_obj = comp["status"]["type"]
                status     = status_obj.get("name", "")
                completed  = status_obj.get("completed", False)

                # Aceita STATUS_SCHEDULED e STATUS_PRE (Libertadores usa STATUS_PRE)
                if completed or status not in ("STATUS_SCHEDULED", "STATUS_PRE"):
                    continue

                times = {t["homeAway"]: t for t in comp["competitors"]}
                casa  = times["home"]["team"]["shortDisplayName"]
                fora  = times["away"]["team"]["shortDisplayName"]

                jogos.append({
                    "id":          f"espn_{evento['id']}",
                    "liga":        nome_liga,
                    "data":        comp["date"],
                    "casa":        casa,
                    "fora":        fora,
                    "logo_casa":   times["home"]["team"].get("logo", ""),
                    "logo_fora":   times["away"]["team"].get("logo", ""),
                    "label":       f"[{nome_liga}] {casa} x {fora}",
                    "fonte":       "espn",
                    "odds_casa":   None,
                    "odds_empate": None,
                    "odds_fora":   None,
                })

        except requests.exceptions.RequestException:
            pass

    return jogos


def get_jogos_espn(dias_a_frente=7):
    """Retorna jogos agendados do Brasileirão via ESPN."""
    return _get_jogos_espn_liga("bra.1", "Brasileirão", dias_a_frente)


def get_jogos_libertadores(dias_a_frente=7):
    """Retorna jogos agendados da Copa Libertadores via ESPN."""
    return _get_jogos_espn_liga("conmebol.libertadores", "Libertadores", dias_a_frente)


def get_resultados_espn(days_back=7):
    """Retorna resultados finalizados do Brasileirão via ESPN."""
    hoje  = datetime.today()
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
                comp   = evento["competitions"][0]
                status = comp["status"]["type"]["name"]

                if status != "STATUS_FINAL":
                    continue

                times = {t["homeAway"]: t for t in comp["competitors"]}
                casa  = times["home"]["team"]["shortDisplayName"]
                fora  = times["away"]["team"]["shortDisplayName"]
                gc    = int(times["home"].get("score", 0))
                gf    = int(times["away"].get("score", 0))

                jogos.append({
                    "id":        f"espn_{evento['id']}",
                    "liga":      "Brasileirão",
                    "data":      comp["date"],
                    "casa":      casa,
                    "fora":      fora,
                    "logo_casa": times["home"]["team"].get("logo", ""),
                    "logo_fora": times["away"]["team"].get("logo", ""),
                    "gols_casa": gc,
                    "gols_fora": gf,
                    "label":     f"[Brasileirão] {casa} {gc}x{gf} {fora}",
                    "fonte":     "espn",
                })

        except requests.exceptions.RequestException:
            pass

    return jogos


def get_liga_logos():
    """
    Retorna dict {nome_liga: url_logo} para todas as ligas.
    Football-data.org CDN para as 5 ligas europeias;
    ESPN para o Brasileirão (obtido da resposta do endpoint de times).
    """
    logos = {
        "Premier League":   "https://crests.football-data.org/PL.png",
        "La Liga":          "https://crests.football-data.org/PD.png",
        "Serie A":          "https://crests.football-data.org/SA.png",
        "Bundesliga":       "https://crests.football-data.org/BL1.png",
        "Champions League": "https://crests.football-data.org/CL.png",
        "Brasileirão":      "https://a.espncdn.com/i/leaguelogos/soccer/500/bra.1.png",
    }
    try:
        r = requests.get(f"{ESPN_BASE}/bra.1/teams", timeout=10)
        if r.ok:
            league      = r.json().get("sports", [{}])[0].get("leagues", [{}])[0]
            liga_logos  = league.get("logos", [])
            if liga_logos:
                logos["Brasileirão"] = liga_logos[0]["href"]
    except Exception:
        pass
    return logos


def get_logos_espn():
    """Retorna dict {shortDisplayName: logo_url} para times do Brasileirão."""
    try:
        r = requests.get(
            f"{ESPN_BASE}/bra.1/teams", timeout=10
        )
        if not r.ok:
            return {}
        times = (
            r.json()
            .get("sports", [{}])[0]
            .get("leagues", [{}])[0]
            .get("teams", [])
        )
        resultado = {}
        for t in times:
            team = t["team"]
            logos = team.get("logos", [])
            if logos:
                resultado[team["shortDisplayName"]] = logos[0]["href"]
        return resultado
    except requests.exceptions.RequestException:
        return {}


def get_h2h_espn(event_id: str, liga_espn: str = "bra.1"):
    """
    Busca confronto direto via ESPN summary.
    event_id: ID do evento ESPN sem o prefixo 'espn_'.
    liga_espn: código ESPN da liga (ex: 'bra.1', 'conmebol.libertadores').
    Retorna lista de [{data, casa, fora, gols_casa, gols_fora}].
    """
    try:
        r = requests.get(
            f"{ESPN_BASE}/{liga_espn}/summary",
            params={"event": event_id},
            timeout=10,
        )
        if not r.ok:
            return []

        data   = r.json()
        result = []

        for comp in data.get("header", {}).get("competitions", []):
            for meeting in comp.get("previousMeetings", []):
                competitors = meeting.get("competitors", [])
                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home or not away:
                    continue
                result.append({
                    "data":      meeting.get("date", "")[:10],
                    "casa":      home.get("team", {}).get("shortDisplayName", "?"),
                    "fora":      away.get("team", {}).get("shortDisplayName", "?"),
                    "gols_casa": int(home.get("score", 0) or 0),
                    "gols_fora": int(away.get("score", 0) or 0),
                })

        return result[:5]

    except Exception:
        return []


def get_h2h_fd(api_key: str, competition_code: str, home_team: str, away_team: str):
    """
    Busca confronto direto via football-data.org (ligas europeias).
    Escaneia matches FINISHED da temporada atual e filtra pelos dois times.
    Retorna lista de até 5 encontros [{data, casa, fora, gols_casa, gols_fora}].
    """
    if not api_key:
        return []
    try:
        r = requests.get(
            f"{BASE_URL}/competitions/{competition_code}/matches",
            headers=_headers_fd(api_key),
            params={"status": "FINISHED"},
            timeout=10,
        )
        if not r.ok:
            return []

        home_norm = _normalizar(home_team)
        away_norm = _normalizar(away_team)
        h2h       = []

        for match in r.json().get("matches", []):
            h = _normalizar(_nome_time(match["homeTeam"]))
            a = _normalizar(_nome_time(match["awayTeam"]))

            e_h2h = (
                (_similaridade(h, home_norm) > 0.7 and _similaridade(a, away_norm) > 0.7) or
                (_similaridade(h, away_norm) > 0.7 and _similaridade(a, home_norm) > 0.7)
            )
            if not e_h2h:
                continue

            score = match.get("score", {}).get("fullTime", {})
            h2h.append({
                "data":      match["utcDate"][:10],
                "casa":      _nome_time(match["homeTeam"]),
                "fora":      _nome_time(match["awayTeam"]),
                "gols_casa": score.get("home"),
                "gols_fora": score.get("away"),
            })

        h2h.sort(key=lambda x: x["data"], reverse=True)
        return h2h[:5]

    except Exception:
        return []


def get_standings_espn():
    """Retorna (tabela, erro) com a classificação do Brasileirão via ESPN."""
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
                "Pos":    int(stats.get("rank", i)),
                "Time":   entry["team"]["shortDisplayName"],
                "Escudo": entry["team"].get("logo", ""),
                "Pts":    int(stats.get("points", 0)),
                "J":      int(stats.get("gamesPlayed", 0)),
                "V":      int(stats.get("wins", 0)),
                "E":      int(stats.get("ties", 0)),
                "D":      int(stats.get("losses", 0)),
                "GP":     int(stats.get("pointsFor", 0)),
                "GC":     int(stats.get("pointsAgainst", 0)),
                "SG":     int(stats.get("pointDifferential", 0)),
            })

        tabela.sort(key=lambda x: x["Pos"])
        return tabela, None

    except requests.exceptions.RequestException as e:
        return None, str(e)
