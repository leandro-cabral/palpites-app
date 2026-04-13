import os
import asyncio
import hashlib
import requests
import discord
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from discord.ext import tasks
from discord import app_commands

DISCORD_TOKEN  = os.environ["DISCORD_TOKEN"]
CHANNEL_ID     = int(os.environ["DISCORD_CHANNEL_ID"])
GUILD_ID       = int(os.environ["DISCORD_GUILD_ID"])
DATABASE_URL   = os.environ["DATABASE_URL"]
API_KEY        = os.environ.get("API_KEY", "")
ODDS_API_KEY   = os.environ.get("ODDS_API_KEY", "")

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)


# ── DB ────────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ── Scoring ───────────────────────────────────────────────────────────────────

def is_surrealidade(casa, fora):
    return abs(casa - fora) >= 3 or (casa + fora) >= 4

def calcular_pontos(p_casa, p_fora, r_casa, r_fora):
    if r_casa is None or r_fora is None:
        return None
    surreal = is_surrealidade(p_casa, p_fora)
    if p_casa == r_casa and p_fora == r_fora:
        return 9.0 if surreal else 4.5
    def res(c, f): return "V" if c > f else ("D" if c < f else "E")
    if res(p_casa, p_fora) == res(r_casa, r_fora):
        base = 3.0 if res(r_casa, r_fora) == "E" else 1.5
        return base * 2 if surreal else base
    return -2.0 if surreal else -1.0

def calcular_ec_ganhos(pontos, valor_apostado, odd_apostada=None, surrealidade=False):
    if not valor_apostado:
        return 0.0
    if pontos is None or pontos <= 0:
        return -float(valor_apostado)
    odd = float(odd_apostada or 1.0)
    base_pts = pontos / 2 if surrealidade else pontos
    bonus = 1.5 if base_pts == 4.5 else 1.0
    ec = valor_apostado * odd * bonus - valor_apostado
    return ec * 2 if surrealidade else ec


# ── API de resultados ─────────────────────────────────────────────────────────

ESPN_BASE  = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_V2    = "https://site.api.espn.com/apis/v2/sports/soccer"
FD_BASE    = "https://api.football-data.org/v4"
ODDS_BASE  = "https://api.the-odds-api.com/v4"
LIGAS_FD  = {
    "Premier League":   "PL",
    "La Liga":          "PD",
    "Serie A":          "SA",
    "Bundesliga":       "BL1",
    "Champions League": "CL",
}

LIGAS_ODDS = {
    "Premier League":   "soccer_epl",
    "La Liga":          "soccer_spain_la_liga",
    "Serie A":          "soccer_italy_serie_a",
    "Bundesliga":       "soccer_germany_bundesliga",
    "Champions League": "soccer_uefa_champs_league",
}

def _nome_time(team):
    return team.get("shortName") or team.get("name", "?")

def _normalizar(nome):
    import re
    nome = nome.lower()
    for token in [" fc"," cf"," sc"," ac"," afc"," ssc"," as "," ss ",
                  " utd"," united"," city"," hotspur"," wanderers",
                  " athletic"," sport"," sporting"," club"," de "]:
        nome = nome.replace(token, " ")
    nome = re.sub(r"[^a-z0-9 ]", "", nome)
    return re.sub(r"\s+", " ", nome).strip()

def _get_odds_map():
    """Busca odds h2h de todas as ligas europeias. Retorna {(home_norm, away_norm): {casa, empate, fora}}"""
    if not ODDS_API_KEY:
        return {}
    resultado = {}
    for liga, sport_key in LIGAS_ODDS.items():
        try:
            r = requests.get(
                f"{ODDS_BASE}/sports/{sport_key}/odds",
                params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
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
                resultado[(_normalizar(match["home_team"]), _normalizar(match["away_team"]))] = {
                    "odds_casa":   odds_dict.get(match["home_team"], 2.0),
                    "odds_empate": odds_dict.get("Draw", 3.2),
                    "odds_fora":   odds_dict.get(match["away_team"], 2.0),
                }
        except Exception:
            pass
    return resultado

def _calcular_odds_brasileirao():
    """Retorna odds aproximadas para jogos do Brasileirão baseado na tabela."""
    try:
        r = requests.get(f"{ESPN_V2}/bra.1/standings", timeout=10)
        if not r.ok:
            return {}
        entries = []
        for child in r.json().get("children", []):
            entries = child.get("standings", {}).get("entries", [])
            if entries: break
        tabela = {}
        for entry in entries:
            stats = {s["name"]: s.get("value", 0) for s in entry.get("stats", [])}
            tabela[entry["team"]["shortDisplayName"]] = {
                "pts": int(stats.get("points", 0)),
                "j":   int(stats.get("gamesPlayed", 1)),
            }
        return tabela
    except Exception:
        return {}

def _odds_para_jogo(casa, fora, tabela_bra):
    if not tabela_bra or casa not in tabela_bra or fora not in tabela_bra:
        return None, None, None
    th = tabela_bra[casa]; ta = tabela_bra[fora]
    ppg_h = (th["pts"] / max(th["j"], 1)) * 1.15
    ppg_a =  ta["pts"] / max(ta["j"], 1)
    total = ppg_h + ppg_a
    if total == 0:
        return 2.10, 3.20, 3.50
    sh = ppg_h / total; sa = ppg_a / total
    p_draw = max(0.18, min(0.35, 0.28 - abs(sh - sa) * 0.3))
    rem = 1 - p_draw
    margin = 0.92
    odds_h = round(margin / max(rem * sh,    0.05), 2)
    odds_d = round(margin / max(p_draw,      0.10), 2)
    odds_a = round(margin / max(rem * sa,    0.05), 2)
    return odds_h, odds_d, odds_a

def _db_atualizar_odds():
    """Busca odds nas APIs e atualiza a tabela jogos."""
    odds_map   = _get_odds_map()
    tabela_bra = _calcular_odds_brasileirao()

    conn = get_conn()
    c    = cur(conn)
    agora = datetime.now(timezone.utc)
    c.execute("SELECT id, liga, casa, fora FROM jogos WHERE status='SCHEDULED' AND data > %s", (agora,))
    jogos = c.fetchall()

    atualizados = 0
    for j in jogos:
        if j["liga"] == "Brasileirão":
            oh, od, oa = _odds_para_jogo(j["casa"], j["fora"], tabela_bra)
        else:
            h_key = _normalizar(j["casa"]); a_key = _normalizar(j["fora"])
            match = odds_map.get((h_key, a_key))
            if not match:
                # fuzzy fallback
                from difflib import SequenceMatcher
                best_score, best = 0.0, None
                for (h, a), val in odds_map.items():
                    score = (SequenceMatcher(None, h_key, h).ratio() + SequenceMatcher(None, a_key, a).ratio()) / 2
                    if score > best_score:
                        best_score, best = score, val
                match = best if best_score >= 0.72 else None
            if match:
                oh, od, oa = match["odds_casa"], match["odds_empate"], match["odds_fora"]
            else:
                oh, od, oa = None, None, None

        if oh:
            c.execute("UPDATE jogos SET odds_casa=%s, odds_empate=%s, odds_fora=%s WHERE id=%s",
                      (oh, od, oa, j["id"]))
            atualizados += 1

    conn.commit()
    conn.close()
    return atualizados

def get_resultados_espn(days_back=2):
    hoje  = datetime.today()
    jogos = []
    for i in range(0, days_back + 1):
        data = (hoje - timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(f"{ESPN_BASE}/bra.1/scoreboard", params={"dates": data}, timeout=10)
            if not r.ok:
                continue
            for evento in r.json().get("events", []):
                comp   = evento["competitions"][0]
                if comp["status"]["type"]["name"] not in ("STATUS_FINAL", "STATUS_FULL_TIME"):
                    continue
                times = {t["homeAway"]: t for t in comp["competitors"]}
                jogos.append({
                    "id":        f"espn_{evento['id']}",
                    "liga":      "Brasileirão",
                    "data":      comp["date"],
                    "casa":      times["home"]["team"]["shortDisplayName"],
                    "fora":      times["away"]["team"]["shortDisplayName"],
                    "logo_casa": times["home"]["team"].get("logo", ""),
                    "logo_fora": times["away"]["team"].get("logo", ""),
                    "gols_casa": int(times["home"].get("score", 0)),
                    "gols_fora": int(times["away"].get("score", 0)),
                })
        except Exception:
            pass
    return jogos

def get_resultados_fd(days_back=2):
    hoje      = datetime.today()
    date_from = (hoje - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to   = hoje.strftime("%Y-%m-%d")
    jogos     = []
    if not API_KEY:
        return jogos
    for nome_liga, codigo in LIGAS_FD.items():
        try:
            r = requests.get(
                f"{FD_BASE}/competitions/{codigo}/matches",
                headers={"X-Auth-Token": API_KEY},
                params={"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"},
                timeout=10,
            )
            if not r.ok:
                continue
            for match in r.json().get("matches", []):
                score = match.get("score", {}).get("fullTime", {})
                jogos.append({
                    "id":        str(match["id"]),
                    "liga":      nome_liga,
                    "data":      match["utcDate"],
                    "casa":      _nome_time(match["homeTeam"]),
                    "fora":      _nome_time(match["awayTeam"]),
                    "logo_casa": match["homeTeam"].get("crest", ""),
                    "logo_fora": match["awayTeam"].get("crest", ""),
                    "gols_casa": score.get("home"),
                    "gols_fora": score.get("away"),
                })
        except Exception:
            pass
    return jogos


# ── Helpers de aposta ─────────────────────────────────────────────────────────

def get_usuario_por_discord(discord_id: str):
    conn = get_conn()
    c    = cur(conn)
    c.execute("SELECT * FROM usuarios WHERE discord_id = %s", (discord_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def _db_buscar_jogos_proximos():
    agora = datetime.now(timezone.utc)
    conn  = get_conn()
    c     = cur(conn)
    c.execute("""
        SELECT id, liga, casa, fora, data, odds_casa, odds_empate, odds_fora
        FROM jogos
        WHERE status = 'SCHEDULED' AND data > %s
        ORDER BY data ASC
        LIMIT 10
    """, (agora,))
    jogos = [dict(r) for r in c.fetchall()]
    conn.close()
    return jogos

def _db_buscar_jogos_autocomplete(current: str):
    agora = datetime.now(timezone.utc)
    conn  = get_conn()
    c     = cur(conn)
    c.execute("""
        SELECT id, casa, fora, liga, data
        FROM jogos
        WHERE status = 'SCHEDULED' AND data > %s
        ORDER BY data ASC
        LIMIT 25
    """, (agora,))
    jogos = [dict(r) for r in c.fetchall()]
    conn.close()
    return [j for j in jogos if current.lower() in f"{j['casa']} {j['fora']} {j['liga']}".lower()]

def _db_registrar_aposta(discord_id, jogo_id, placar_casa, placar_fora, valor):
    usuario = get_usuario_por_discord(discord_id)
    if not usuario:
        return {"erro": "sem_vinculo"}

    if valor < 0 or placar_casa < 0 or placar_fora < 0:
        return {"erro": "valores_invalidos"}

    conn = get_conn()
    c    = cur(conn)

    c.execute("SELECT * FROM jogos WHERE id = %s", (jogo_id,))
    jogo_row = c.fetchone()
    if not jogo_row:
        conn.close()
        return {"erro": "jogo_nao_encontrado"}

    if jogo_row["status"] != "SCHEDULED" or jogo_row["data"] <= datetime.now(timezone.utc):
        conn.close()
        return {"erro": "jogo_iniciado"}

    c.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s",
              (usuario["nome"], jogo_id))
    if c.fetchone():
        conn.close()
        return {"erro": "ja_apostou"}

    if valor > 0 and valor > usuario["saldo_ec"]:
        conn.close()
        return {"erro": "saldo_insuficiente", "saldo": usuario["saldo_ec"]}

    odd_apostada = None
    if valor > 0 and jogo_row["odds_casa"]:
        odd_apostada = odd_do_palpite(
            placar_casa, placar_fora,
            jogo_row["odds_casa"], jogo_row["odds_empate"], jogo_row["odds_fora"]
        )

    label = f"{jogo_row['casa']} x {jogo_row['fora']}"
    c.execute("""
        INSERT INTO palpites (usuario, jogo_id, jogo, liga, palpite_casa, palpite_fora,
                              moeda_apostada, odds_casa, odds_empate, odds_fora, odd_apostada,
                              criado_em_brt)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                to_char(NOW() AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'))
    """, (
        usuario["nome"], jogo_id, label, jogo_row["liga"],
        placar_casa, placar_fora, valor,
        jogo_row["odds_casa"], jogo_row["odds_empate"], jogo_row["odds_fora"],
        odd_apostada,
    ))

    if valor > 0:
        c.execute("UPDATE usuarios SET saldo_ec = saldo_ec - %s WHERE nome = %s",
                  (valor, usuario["nome"]))

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "usuario": usuario["nome"],
        "jogo": dict(jogo_row),
        "odd_apostada": odd_apostada,
        "novo_saldo": usuario["saldo_ec"] - valor,
    }

def _db_vincular(discord_id, nome, senha_hash):
    conn = get_conn()
    c    = cur(conn)
    c.execute("SELECT id, nome, discord_id FROM usuarios WHERE nome = %s AND senha_hash = %s",
              (nome, senha_hash))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"erro": "credenciais"}
    if row["discord_id"] and row["discord_id"] != discord_id:
        conn.close()
        return {"erro": "ja_vinculado"}
    c.execute("UPDATE usuarios SET discord_id = %s WHERE nome = %s", (discord_id, nome))
    conn.commit()
    conn.close()
    return {"ok": True, "nome": nome}

def odd_do_palpite(p_casa, p_fora, odds_casa, odds_empate, odds_fora):
    if p_casa > p_fora:
        return odds_casa
    if p_casa < p_fora:
        return odds_fora
    return odds_empate

def fmt_brt(dt_utc):
    brt = timezone(timedelta(hours=-3))
    return dt_utc.astimezone(brt).strftime("%d/%m %H:%M")


# ── Eventos ───────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")
    guild = discord.Object(id=GUILD_ID)
    # Primeiro copia e sincroniza no guild (comandos aparecem instantaneamente)
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    # Depois limpa os comandos globais para remover duplicatas
    tree.clear_commands(guild=None)
    await tree.sync()
    print("Slash commands sincronizados.")
    checar_lembretes.start()
    checar_resultados.start()
    atualizar_odds.start()


# ── UI: Modal de aposta ───────────────────────────────────────────────────────

class ApostarModal(discord.ui.Modal):
    placar_casa = discord.ui.TextInput(
        label="Gols — Time da Casa",
        placeholder="ex: 2",
        min_length=1, max_length=2,
    )
    placar_fora = discord.ui.TextInput(
        label="Gols — Time Visitante",
        placeholder="ex: 1",
        min_length=1, max_length=2,
    )
    valor = discord.ui.TextInput(
        label="Valor apostado em EC (0 = sem aposta)",
        placeholder="ex: 1.5",
        min_length=1, max_length=6,
    )

    def __init__(self, jogo_id: str, jogo_label: str):
        super().__init__(title=jogo_label[:45])
        self.jogo_id = jogo_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            pc = int(self.placar_casa.value.strip())
            pf = int(self.placar_fora.value.strip())
            v  = float(self.valor.value.strip().replace(",", "."))
        except ValueError:
            await interaction.followup.send("❌ Valores inválidos. Use números inteiros para o placar.", ephemeral=True)
            return

        result = await asyncio.to_thread(
            _db_registrar_aposta, str(interaction.user.id), self.jogo_id, pc, pf, v
        )
        await _enviar_resultado_aposta(interaction, result, pc, pf, v)


# ── UI: View com botões por jogo ──────────────────────────────────────────────

class JogosView(discord.ui.View):
    def __init__(self, jogos: list):
        super().__init__(timeout=3600)
        for j in jogos[:25]:
            label    = f"⚽  {j['casa']} x {j['fora']}"[:80]
            jogo_id  = j["id"]
            jogo_lbl = f"{j['casa']} x {j['fora']}"

            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"apostar_{jogo_id}",
            )
            btn.callback = self._make_callback(jogo_id, jogo_lbl)
            self.add_item(btn)

    def _make_callback(self, jogo_id: str, jogo_label: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(ApostarModal(jogo_id, jogo_label))
        return callback


async def _enviar_resultado_aposta(interaction, result, placar_casa, placar_fora, valor):
    erro = result.get("erro")
    msgs = {
        "sem_vinculo":        "❌ Conta não vinculada. Use `/vincular` primeiro.",
        "valores_invalidos":  "❌ Valores inválidos.",
        "jogo_nao_encontrado":"❌ Jogo não encontrado.",
        "jogo_iniciado":      "❌ Este jogo já começou ou foi encerrado.",
        "ja_apostou":         "⚠️ Você já apostou neste jogo. Acesse o app para alterar.",
    }
    if erro in msgs:
        await interaction.followup.send(msgs[erro], ephemeral=True)
        return
    if erro == "saldo_insuficiente":
        await interaction.followup.send(
            f"❌ Saldo insuficiente. Você tem **{result['saldo']:.2f} EC**.", ephemeral=True
        )
        return

    jogo_row     = result["jogo"]
    odd_apostada = result["odd_apostada"]
    novo_saldo   = result["novo_saldo"]
    surreal      = is_surrealidade(placar_casa, placar_fora)
    surreal_txt  = "\n🌀 **Surrealidade ativada!** Pontos e EC dobrados no acerto." if surreal else ""
    odd_txt      = (
        f"\nOdd: `{odd_apostada}` → lucro potencial: `{valor * odd_apostada - valor:.2f} EC`"
        if odd_apostada and valor > 0 else ""
    )
    embed = discord.Embed(
        title="✅ Palpite registrado!",
        description=(
            f"**{jogo_row['casa']} x {jogo_row['fora']}**\n"
            f"{jogo_row['liga']} · {fmt_brt(jogo_row['data'])} BRT\n\n"
            f"Palpite: **{placar_casa} x {placar_fora}**\n"
            f"Apostado: **{valor:.2f} EC**"
            f"{odd_txt}{surreal_txt}"
        ),
        color=0x22c55e,
    )
    embed.set_footer(text=f"Saldo restante: {novo_saldo:.2f} EC")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ── Slash: /ranking ──────────────────────────────────────────────────────────

def _db_buscar_ranking():
    conn = get_conn()
    c    = cur(conn)
    c.execute("""
        SELECT p.usuario,
               COALESCE(SUM(p.pontos), 0)                          AS total_pontos,
               COUNT(CASE WHEN p.pontos IN (4.5, 9.0) THEN 1 END)  AS placares_exatos,
               COUNT(CASE WHEN p.pontos IS NOT NULL THEN 1 END)     AS jogos_avaliados,
               u.saldo_ec,
               COALESCE(SUM(CASE WHEN p.pontos IS NULL THEN p.moeda_apostada ELSE 0 END), 0) AS ec_em_jogo
        FROM palpites p
        JOIN usuarios u ON p.usuario = u.nome
        WHERE p.moeda_apostada > 0
        GROUP BY p.usuario, u.saldo_ec
        ORDER BY (COALESCE(SUM(p.pontos), 0) * u.saldo_ec) DESC,
                 COALESCE(SUM(p.pontos), 0) DESC,
                 COUNT(CASE WHEN p.pontos IN (4.5, 9.0) THEN 1 END) DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@tree.command(name="ranking", description="Mostra o ranking Lisan al Gaib atual")
async def cmd_ranking(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    ranking = await asyncio.to_thread(_db_buscar_ranking)

    if not ranking:
        await interaction.followup.send("Nenhum dado de ranking ainda.")
        return

    medals = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, r in enumerate(ranking):
        medal  = medals[i] if i < 3 else f"**{i+1}.**"
        score  = round(r["total_pontos"] * r["saldo_ec"], 2)
        linhas.append(
            f"{medal} **{r['usuario']}**\n"
            f"┣ ⭐ Score: `{score}` · 📊 `{r['total_pontos']} pts`\n"
            f"┣ 🎯 Placares exatos: `{r['placares_exatos']}` · 🎮 Jogos: `{r['jogos_avaliados']}`\n"
            f"┗ 💰 Banca: `{r['saldo_ec']:.2f} EC`"
        )

    embed = discord.Embed(
        title="🏆 Ranking Lisan al Gaib",
        description="\n\n".join(linhas),
        color=0xeab308,
    )
    embed.set_footer(text="Score = Pontos × Banca Disponível")
    await interaction.followup.send(embed=embed)


# ── Slash: /vincular ──────────────────────────────────────────────────────────

@tree.command(name="vincular", description="Vincula sua conta do app ao Discord")
@app_commands.describe(
    usuario="Seu nome de usuário no app",
    senha="Sua senha do app",
)
async def cmd_vincular(interaction: discord.Interaction, usuario: str, senha: str):
    await interaction.response.defer(ephemeral=True)
    senha_hash = hashlib.sha256(senha.encode()).hexdigest()
    result = await asyncio.to_thread(_db_vincular, str(interaction.user.id), usuario, senha_hash)

    if result.get("erro") == "credenciais":
        await interaction.followup.send("❌ Usuário ou senha incorretos.", ephemeral=True)
    elif result.get("erro") == "ja_vinculado":
        await interaction.followup.send("⚠️ Esta conta já está vinculada a outro Discord.", ephemeral=True)
    else:
        await interaction.followup.send(
            f"✅ Conta **{result['nome']}** vinculada! Agora use `/jogos` e `/apostar`.",
            ephemeral=True
        )


# ── Slash: /jogos ─────────────────────────────────────────────────────────────

@tree.command(name="jogos", description="Lista os próximos jogos disponíveis para apostar")
async def cmd_jogos(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    jogos = await asyncio.to_thread(_db_buscar_jogos_proximos)

    if not jogos:
        await interaction.followup.send("Nenhum jogo disponível no momento.", ephemeral=True)
        return

    embed = discord.Embed(title="⚽ Próximos Jogos", color=0x00d2ff)
    for j in jogos:
        odds_txt = (
            f"🏠 `{j['odds_casa']}` · ✏️ `{j['odds_empate']}` · ✈️ `{j['odds_fora']}`"
            if j["odds_casa"] else "_Odds indisponíveis_"
        )
        embed.add_field(
            name=f"{fmt_brt(j['data'])} BRT — {j['casa']} x {j['fora']}",
            value=f"{j['liga']} · {odds_txt}",
            inline=False,
        )

    embed.set_footer(text="Clique em um jogo abaixo para apostar")
    await interaction.edit_original_response(embed=embed, view=JogosView(jogos))


# ── Autocomplete de jogos ─────────────────────────────────────────────────────

async def jogos_autocomplete(interaction: discord.Interaction, current: str):
    jogos = await asyncio.to_thread(_db_buscar_jogos_autocomplete, current)
    return [
        app_commands.Choice(
            name=f"{fmt_brt(j['data'])} — {j['casa']} x {j['fora']} ({j['liga']})"[:100],
            value=j["id"],
        )
        for j in jogos
    ]


# ── Slash: /apostar ───────────────────────────────────────────────────────────

@tree.command(name="apostar", description="Registre seu palpite em um jogo")
@app_commands.describe(
    jogo="Selecione o jogo",
    placar_casa="Gols do time da casa",
    placar_fora="Gols do time visitante",
    valor="Valor em EC para apostar (0 para palpite sem aposta)",
)
@app_commands.autocomplete(jogo=jogos_autocomplete)
async def cmd_apostar(
    interaction: discord.Interaction,
    jogo: str,
    placar_casa: int,
    placar_fora: int,
    valor: float,
):
    await interaction.response.defer(ephemeral=True)
    result = await asyncio.to_thread(
        _db_registrar_aposta, str(interaction.user.id), jogo, placar_casa, placar_fora, valor
    )
    await _enviar_resultado_aposta(interaction, result, placar_casa, placar_fora, valor)


# ── Task 1: Lembretes antes do jogo (2h e 1h) ────────────────────────────────

async def _enviar_lembrete(channel, jogo, faltam_horas: int, conn, c):
    c.execute("""
        SELECT nome FROM usuarios
        WHERE nome NOT IN (
            SELECT usuario FROM palpites WHERE jogo_id = %s
        )
    """, (jogo["id"],))
    sem_palpite = [r["nome"] for r in c.fetchall()]

    horario = jogo["data"].astimezone(timezone(timedelta(hours=-3))).strftime("%H:%M")

    embed = discord.Embed(
        title=f"⏰ {jogo['casa']} x {jogo['fora']}",
        description=f"**{jogo['liga']}** — começa às {horario} (BRT)\nFaltam ~{faltam_horas} hora{'s' if faltam_horas > 1 else ''}!",
        color=0xff4500 if faltam_horas == 2 else 0xff0000,
    )
    if sem_palpite:
        embed.add_field(
            name="Ainda não apostaram",
            value=", ".join(f"**{n}**" for n in sem_palpite),
            inline=False,
        )
    else:
        embed.add_field(name="✅ Todos apostaram!", value="Boa sorte a todos.", inline=False)

    await channel.send(embed=embed)

    col = "lembrete_enviado" if faltam_horas == 2 else "lembrete_1h_enviado"
    c.execute(f"UPDATE jogos SET {col} = TRUE WHERE id = %s", (jogo["id"],))


@tasks.loop(minutes=15)
async def checar_lembretes():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    agora = datetime.now(timezone.utc)

    try:
        conn = get_conn()
        c    = cur(conn)

        # Lembrete de 2h
        c.execute("""
            SELECT id, liga, casa, fora, data
            FROM jogos
            WHERE status = 'SCHEDULED'
              AND lembrete_enviado = FALSE
              AND data > %s AND data <= %s
        """, (agora + timedelta(hours=2), agora + timedelta(hours=3)))
        for jogo in c.fetchall():
            await _enviar_lembrete(channel, jogo, 2, conn, c)

        # Lembrete de 1h
        c.execute("""
            SELECT id, liga, casa, fora, data
            FROM jogos
            WHERE status = 'SCHEDULED'
              AND lembrete_1h_enviado = FALSE
              AND data > %s AND data <= %s
        """, (agora + timedelta(hours=1), agora + timedelta(hours=2)))
        for jogo in c.fetchall():
            await _enviar_lembrete(channel, jogo, 1, conn, c)

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[lembretes] Erro: {e}")


# ── Task 2: Busca resultados, processa e notifica ─────────────────────────────

LIGAS_BRASILEIRAO = {"Brasileirão"}

def _tem_jogos_europeus_pendentes():
    """Retorna True se há jogos europeus SCHEDULED que já deveriam ter terminado."""
    agora = datetime.now(timezone.utc)
    conn  = get_conn()
    c     = cur(conn)
    c.execute("""
        SELECT COUNT(*) AS n FROM jogos
        WHERE status = 'SCHEDULED'
          AND liga NOT IN %s
          AND data < %s
    """, (tuple(LIGAS_BRASILEIRAO), agora - timedelta(minutes=90)))
    n = c.fetchone()["n"]
    conn.close()
    return n > 0

@tasks.loop(minutes=5)
async def checar_resultados():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    try:
        # ESPN: toda execução (Brasileirão)
        # football-data.org: só quando há jogos europeus que já deveriam ter terminado
        espn_jogos = await asyncio.to_thread(get_resultados_espn, 2)
        tem_europeus = await asyncio.to_thread(_tem_jogos_europeus_pendentes)
        fd_jogos = await asyncio.to_thread(get_resultados_fd, 2) if tem_europeus else []
        if tem_europeus:
            print("[resultados] Jogos europeus pendentes — consultando football-data.org")

        jogos_finais = espn_jogos + fd_jogos

        conn = get_conn()
        c    = cur(conn)
        notificados = []
        ids_api = set()

        for j in jogos_finais:
            gc, gf = j["gols_casa"], j["gols_fora"]
            if gc is None or gf is None:
                continue

            c.execute("SELECT resultado_notificado FROM jogos WHERE id = %s", (j["id"],))
            row = c.fetchone()
            ids_api.add(j["id"])
            if row and row["resultado_notificado"]:
                continue

            c.execute("""
                SELECT id, usuario, palpite_casa, palpite_fora,
                       COALESCE(moeda_apostada, 0) AS moeda_apostada, odd_apostada
                FROM palpites WHERE jogo_id = %s AND pontos IS NULL
            """, (j["id"],))
            palpites = c.fetchall()

            for p in palpites:
                pts     = calcular_pontos(p["palpite_casa"], p["palpite_fora"], gc, gf)
                surreal = is_surrealidade(p["palpite_casa"], p["palpite_fora"])
                ec      = calcular_ec_ganhos(pts, p["moeda_apostada"], p["odd_apostada"],
                                             surrealidade=(surreal and pts is not None and pts > 0))
                c.execute(
                    "UPDATE palpites SET gols_casa_real=%s, gols_fora_real=%s, pontos=%s, moedas_ganhas=%s WHERE id=%s",
                    (gc, gf, pts, ec, p["id"]),
                )
                if ec > 0:
                    c.execute("UPDATE usuarios SET saldo_ec = saldo_ec + %s WHERE nome = %s",
                              (float(p["moeda_apostada"]) + ec, p["usuario"]))

            c.execute("""
                INSERT INTO jogos (id, liga, casa, fora, data, data_brt, logo_casa, logo_fora, gols_casa, gols_fora, status, resultado_notificado)
                VALUES (%s, %s, %s, %s, %s, to_char(%s::timestamptz AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'), %s, %s, %s, %s, 'FINISHED', TRUE)
                ON CONFLICT (id) DO UPDATE
                  SET gols_casa = EXCLUDED.gols_casa,
                      gols_fora = EXCLUDED.gols_fora,
                      status    = 'FINISHED',
                      resultado_notificado = TRUE,
                      data_brt  = EXCLUDED.data_brt
            """, (j["id"], j["liga"], j["casa"], j["fora"], j["data"], j["data"],
                  j.get("logo_casa", ""), j.get("logo_fora", ""), gc, gf))

            notificados.append((j, palpites, gc, gf))

        # Fallback: jogos já FINISHED no banco não notificados
        c.execute("""
            SELECT id, liga, casa, fora, gols_casa, gols_fora, logo_casa, logo_fora, data
            FROM jogos
            WHERE status = 'FINISHED' AND resultado_notificado = FALSE
              AND id != ALL(%s)
        """, (list(ids_api) or [""],))

        for row in c.fetchall():
            j = dict(row)
            gc, gf = j["gols_casa"], j["gols_fora"]
            if gc is None or gf is None:
                continue

            c.execute("""
                SELECT id, usuario, palpite_casa, palpite_fora,
                       COALESCE(moeda_apostada, 0) AS moeda_apostada, odd_apostada
                FROM palpites WHERE jogo_id = %s AND pontos IS NULL
            """, (j["id"],))
            palpites = c.fetchall()

            for p in palpites:
                pts     = calcular_pontos(p["palpite_casa"], p["palpite_fora"], gc, gf)
                surreal = is_surrealidade(p["palpite_casa"], p["palpite_fora"])
                ec      = calcular_ec_ganhos(pts, p["moeda_apostada"], p["odd_apostada"],
                                             surrealidade=(surreal and pts is not None and pts > 0))
                c.execute(
                    "UPDATE palpites SET gols_casa_real=%s, gols_fora_real=%s, pontos=%s, moedas_ganhas=%s WHERE id=%s",
                    (gc, gf, pts, ec, p["id"]),
                )
                if ec > 0:
                    c.execute("UPDATE usuarios SET saldo_ec = saldo_ec + %s WHERE nome = %s",
                              (float(p["moeda_apostada"]) + ec, p["usuario"]))

            c.execute("UPDATE jogos SET resultado_notificado = TRUE WHERE id = %s", (j["id"],))
            notificados.append((j, palpites, gc, gf))

        conn.commit()

        # Envia embeds de resultado
        for j, palpites, gc, gf in notificados:
            c.execute("""
                SELECT usuario, palpite_casa, palpite_fora, pontos, moeda_apostada, moedas_ganhas
                FROM palpites WHERE jogo_id = %s AND pontos IS NOT NULL ORDER BY pontos DESC
            """, (j["id"],))
            palpites_final = c.fetchall()

            embed = discord.Embed(
                title=f"⚽ {j['casa']} {gc} x {gf} {j['fora']}",
                color=0x00d2ff,
            )
            embed.set_footer(text=j["liga"])

            if palpites_final:
                linhas = []
                for p in palpites_final:
                    pts   = p["pontos"]
                    ec    = p["moedas_ganhas"]
                    emoji = "🟢" if pts > 0 else ("🟡" if pts == 0 else "🔴")
                    ec_str = f"`{ec:+.2f} EC`" if ec is not None else "—"
                    linhas.append(
                        f"{emoji} **{p['usuario']}** — "
                        f"`{p['palpite_casa']}x{p['palpite_fora']}` · "
                        f"**{pts} pts** · {ec_str}"
                    )
                embed.description = "\n".join(linhas)
            else:
                embed.description = "_Nenhum palpite registrado para este jogo._"

            await channel.send(embed=embed)

        # Ranking
        if notificados:
            c.execute("""
                SELECT p.usuario, COALESCE(SUM(p.pontos), 0) AS total_pontos, u.saldo_ec
                FROM palpites p JOIN usuarios u ON p.usuario = u.nome
                WHERE p.moeda_apostada > 0
                GROUP BY p.usuario, u.saldo_ec
                ORDER BY (COALESCE(SUM(p.pontos), 0) * u.saldo_ec) DESC,
                         COALESCE(SUM(p.pontos), 0) DESC
            """)
            ranking = c.fetchall()
            if ranking:
                medals = ["🥇", "🥈", "🥉"]
                linhas = []
                for i, r in enumerate(ranking):
                    medal = medals[i] if i < 3 else f"**{i+1}.**"
                    score = round(r["total_pontos"] * r["saldo_ec"], 2)
                    linhas.append(
                        f"{medal} **{r['usuario']}** — "
                        f"{r['total_pontos']} pts · 💰 {r['saldo_ec']:.2f} EC · ⭐ {score}"
                    )
                await channel.send(embed=discord.Embed(
                    title="🏆 Ranking Lisan al Gaib — Atualizado",
                    description="\n".join(linhas),
                    color=0xeab308,
                ))

        conn.close()

    except Exception as e:
        print(f"[resultados] Erro: {e}")


# ── Task 3: Atualiza odds a cada 3 horas ─────────────────────────────────────

@tasks.loop(hours=3)
async def atualizar_odds():
    try:
        n = await asyncio.to_thread(_db_atualizar_odds)
        print(f"[odds] {n} jogo(s) atualizados.")
    except Exception as e:
        print(f"[odds] Erro: {e}")


client.run(DISCORD_TOKEN)
