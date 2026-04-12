import streamlit as st
from datetime import datetime, timezone, timedelta
from api import (
    get_jogos, get_jogos_espn, get_odds, get_standings_espn,
    calcular_odds_por_pontos, _mesclar_odds, _odd_apostada,
)
from database import get_connection, init_db
from utils import sidebar_login, apply_mobile_css
from scoring import fmt_ec, is_surrealidade

st.set_page_config(page_title="Copa Elevação Sabichão", page_icon="⚽", layout="wide")
apply_mobile_css()

API_KEY      = st.secrets["API_KEY"]
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", None)
init_db()


@st.cache_data(ttl=3600)
def carregar_jogos_api():
    return get_jogos(API_KEY, dias_a_frente=7)

@st.cache_data(ttl=3600)
def carregar_jogos_brasileirao():
    return get_jogos_espn(dias_a_frente=7)

@st.cache_data(ttl=43200)
def carregar_odds(key):
    if not key:
        return {}
    return get_odds(key)

@st.cache_data(ttl=1800)
def carregar_standings_brasileirao():
    return get_standings_espn()


def palpites_do_usuario(usuario):
    conn = get_connection()
    rows = conn.execute(
        """SELECT jogo_id, palpite_casa, palpite_fora,
                  COALESCE(moeda_apostada, 0) as aposta
           FROM palpites WHERE usuario=?""",
        (usuario,),
    ).fetchall()
    conn.close()
    return {r["jogo_id"]: (r["palpite_casa"], r["palpite_fora"], r["aposta"]) for r in rows}


def info_ec(usuario):
    conn = get_connection()
    row     = conn.execute("SELECT COALESCE(saldo_ec, 10) as saldo FROM usuarios WHERE nome=?", (usuario,)).fetchone()
    em_jogo = conn.execute(
        "SELECT COALESCE(SUM(moeda_apostada), 0) as c FROM palpites WHERE usuario=? AND moeda_apostada > 0 AND pontos IS NULL",
        (usuario,),
    ).fetchone()["c"]
    conn.close()
    return float(row["saldo"] if row else 10.0), float(em_jogo)


def _fmt_odd(v):
    return f"{v:.2f}" if v else "—"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

st.title("⚽ Copa Elevação Sabichão")

# Carrega jogos (antes do login para sincronizar o banco independente de autenticação)
jogos_api, erros  = carregar_jogos_api()
jogos_brasileirao = carregar_jogos_brasileirao()

# Mescla odds
odds_map = carregar_odds(ODDS_API_KEY)
for j in jogos_api:
    _mesclar_odds(j, odds_map)

# Odds Brasileirão via tabela ESPN
tabela_br, _ = carregar_standings_brasileirao()
standings_br  = {t["Time"]: t for t in (tabela_br or [])}
for j in jogos_brasileirao:
    h = standings_br.get(j["casa"], {})
    a = standings_br.get(j["fora"],  {})
    oc, oe, of_ = calcular_odds_por_pontos(
        h.get("Pts", 0), h.get("J", 1),
        a.get("Pts", 0), a.get("J", 1),
    )
    j["odds_casa"], j["odds_empate"], j["odds_fora"] = oc, oe, of_

todos_jogos = jogos_api + jogos_brasileirao

# Sincroniza jogos no banco (roda sempre, independente de login)
# Salva odds da API apenas se o banco ainda não tiver (bot é a fonte principal, app é fallback)
def _sincronizar_jogos(jogos):
    conn = get_connection()
    for j in jogos:
        try:
            conn.execute("""
                INSERT INTO jogos (id, liga, data, casa, fora, logo_casa, logo_fora,
                                   odds_casa, odds_empate, odds_fora)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    logo_casa   = excluded.logo_casa,
                    logo_fora   = excluded.logo_fora,
                    odds_casa   = COALESCE(jogos.odds_casa,   excluded.odds_casa),
                    odds_empate = COALESCE(jogos.odds_empate, excluded.odds_empate),
                    odds_fora   = COALESCE(jogos.odds_fora,   excluded.odds_fora)
            """, (j["id"], j["liga"], j.get("data"), j["casa"], j["fora"],
                  j.get("logo_casa", ""), j.get("logo_fora", ""),
                  j.get("odds_casa"), j.get("odds_empate"), j.get("odds_fora")))
        except Exception:
            pass
    conn.commit()
    conn.close()

_sincronizar_jogos(todos_jogos)

# Após sync, sobrescreve odds em memória com valores do banco (fonte única de verdade)
def _carregar_odds_do_banco(jogo_ids):
    if not jogo_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" * len(jogo_ids))
    rows = conn.execute(
        f"SELECT id, odds_casa, odds_empate, odds_fora FROM jogos WHERE id IN ({placeholders})",
        jogo_ids,
    ).fetchall()
    conn.close()
    return {r["id"]: (r["odds_casa"], r["odds_empate"], r["odds_fora"]) for r in rows}

_odds_banco = _carregar_odds_do_banco([j["id"] for j in todos_jogos])
for j in todos_jogos:
    db_odds = _odds_banco.get(j["id"])
    if db_odds and db_odds[0] is not None:
        j["odds_casa"], j["odds_empate"], j["odds_fora"] = db_odds

if not usuario:
    st.info("Faça login na barra lateral para registrar seus palpites.")
    st.stop()

if erros:
    with st.expander("Avisos da API"):
        for e in erros:
            st.warning(e)

if not todos_jogos:
    st.warning("Nenhum jogo disponível para palpite nos próximos 7 dias.")
    st.stop()

palpites_atuais = palpites_do_usuario(usuario)
saldo, em_jogo  = info_ec(usuario)

# Inicializa session_state para EC e placares
for jogo in todos_jogos:
    jid          = jogo["id"]
    exist        = palpites_atuais.get(jid)
    aposta_atual = float(exist[2]) if exist and exist[2] else 0.0
    locked       = aposta_atual > 0

    if f"aposta_{jid}" not in st.session_state:
        st.session_state[f"aposta_{jid}"] = int(aposta_atual)

    # Placares: vazio por padrão; apenas jogos travados (com aposta) exibem o valor salvo
    if f"casa_{jid}" not in st.session_state:
        st.session_state[f"casa_{jid}"] = int(exist[0]) if locked and exist else None
    if f"fora_{jid}" not in st.session_state:
        st.session_state[f"fora_{jid}"] = int(exist[1]) if locked and exist else None

# EC apostado via apostas já salvas no DB (travadas)
ec_ja_apostado = sum(
    float(palpites_atuais[j["id"]][2])
    for j in todos_jogos
    if j["id"] in palpites_atuais and palpites_atuais[j["id"]][2] > 0
)

# EC inserido no form agora (jogos não travados)
ec_no_form = sum(
    st.session_state.get(f"aposta_{j['id']}", 0)
    for j in todos_jogos
    if palpites_atuais.get(j["id"], (0, 0, 0))[2] == 0
)

ec_disponivel = saldo - ec_no_form

ligas = {}
for jogo in todos_jogos:
    ligas.setdefault(jogo["liga"], []).append(jogo)

# ── Cabeçalho com saldo dinâmico ─────────────────────────────────────────────
col_j, col_ec = st.columns([3, 1])
col_j.markdown(f"**{len(todos_jogos)} jogos disponíveis nos próximos 7 dias**")
with col_ec:
    cor = "normal" if ec_disponivel >= 0 else "inverse"
    st.metric("💰 Disponível", f"{max(ec_disponivel, 0):.2f} EC",
              delta=f"-{ec_no_form:.2f} EC no form" if ec_no_form > 0 else None,
              delta_color="inverse")

# ── Jogos por liga ────────────────────────────────────────────────────────────
novos_palpites  = {}
apostas_no_form = {}

for nome_liga, jogos in ligas.items():
    st.subheader(nome_liga)

    # Cabeçalho das colunas (5 colunas: casa, gc, x, gf, fora, ec)
    h_casa, h_gc, h_x, h_gf, h_fora, h_ec = st.columns([2.7, 0.9, 0.3, 0.9, 2.7, 1.5])
    h_gc.caption("Casa")
    h_gf.caption("Fora")
    h_ec.caption("💰 EC")

    for jogo in jogos:
        jid          = jogo["id"]
        exist        = palpites_atuais.get(jid)
        aposta_atual = float(exist[2]) if exist and exist[2] else 0.0

        # Trava se já apostou OU se o jogo já começou
        try:
            dt         = datetime.fromisoformat(jogo["data"].replace("Z", "+00:00"))
            brt        = dt.astimezone(timezone(timedelta(hours=-3)))
            data_fmt   = brt.strftime("%d/%m %H:%M") + " BRT"
            iniciou    = datetime.now(timezone.utc) >= dt
        except Exception:
            dt, data_fmt, iniciou = None, jogo["data"], False

        locked = aposta_atual > 0 or iniciou
        if iniciou and aposta_atual == 0:
            badge = " ⏱️"
        elif locked:
            badge = " 🔒"
        else:
            badge = ""

        oc  = _fmt_odd(jogo.get("odds_casa"))
        oe  = _fmt_odd(jogo.get("odds_empate"))
        of_ = _fmt_odd(jogo.get("odds_fora"))
        if iniciou:
            odds_str = "🔴 apostas encerradas"
        elif jogo.get("odds_casa") is not None:
            odds_str = f"🏠 {oc} · ➖ {oe} · ✈️ {of_}"
        else:
            odds_str = "odds indisponíveis"

        # Logo inline: imagem pequena antes do nome usando HTML
        def _logo_html(url, lado):
            if not url:
                return ""
            float_dir = "left" if lado == "casa" else "right"
            margin    = "margin-right:6px" if lado == "casa" else "margin-left:6px"
            return f'<img src="{url}" width="20" style="vertical-align:middle;{margin};float:{float_dir}">'

        # Layout: [nome_casa+logo] [gc] [x] [gf] [nome_fora+logo] [ec]
        col_casa, col_gc, col_x, col_gf, col_fora, col_ec_in = st.columns([2.7, 0.9, 0.3, 0.9, 2.7, 1.5])

        with col_casa:
            logo_c = _logo_html(jogo.get("logo_casa"), "casa")
            st.markdown(f"{logo_c}**{jogo['casa']}**{badge}", unsafe_allow_html=True)
            st.caption(f"{data_fmt} · {odds_str}")

        # Valor padrão: existente se já apostou (locked), senão vazio (None)
        gc_default = exist[0] if locked and exist else None
        gf_default = exist[1] if locked and exist else None

        with col_gc:
            gc = st.number_input(
                jogo["casa"], min_value=0, max_value=20,
                value=gc_default, step=1, key=f"casa_{jid}",
                label_visibility="collapsed", disabled=locked,
                placeholder="—",
            )
        with col_x:
            st.markdown("<div style='text-align:center;padding-top:6px'>x</div>", unsafe_allow_html=True)
        with col_gf:
            gf = st.number_input(
                jogo["fora"], min_value=0, max_value=20,
                value=gf_default, step=1, key=f"fora_{jid}",
                label_visibility="collapsed", disabled=locked,
                placeholder="—",
            )

        with col_fora:
            logo_f = _logo_html(jogo.get("logo_fora"), "fora")
            st.markdown(f"**{jogo['fora']}**{logo_f}", unsafe_allow_html=True)
            if gc is not None and gf is not None and not locked and is_surrealidade(gc, gf):
                st.caption("🌪️ Surrealidade!")

        with col_ec_in:
            # Travado: max = valor já apostado; livre: max = saldo disponível
            max_aposta = int(aposta_atual) if locked else int(max(saldo, 0))
            aposta = st.number_input(
                "💰 EC", min_value=0, max_value=max_aposta,
                value=int(aposta_atual), step=1, key=f"aposta_{jid}",
                help="Elevação Coins a apostar neste jogo",
                disabled=locked, label_visibility="collapsed",
            )

        novos_palpites[jid]  = (jogo, gc, gf)
        apostas_no_form[jid] = aposta_atual if locked else aposta

    st.divider()

# ── Botão salvar ──────────────────────────────────────────────────────────────
conn       = get_connection()
salvos     = 0
erros_form = []

if st.button("Salvar palpites", use_container_width=True, type="primary"):
    # Apenas jogos novos (não travados) com EC > 0 e placar preenchido
    para_salvar = []
    avisos      = []

    for jid, (jogo, gc, gf) in novos_palpites.items():
        aposta = apostas_no_form[jid]
        locked = (palpites_atuais.get(jid) or (None, None, 0))[2] > 0
        if locked:
            continue
        if aposta == 0 and (gc is not None or gf is not None):
            avisos.append(f"**{jogo['casa']} x {jogo['fora']}**: placar preenchido sem EC — ignorado.")
            continue
        if aposta > 0 and (gc is None or gf is None):
            avisos.append(f"**{jogo['casa']} x {jogo['fora']}**: EC apostado mas placar vazio — preencha o placar.")
            continue
        if aposta == 0:
            continue  # sem EC e sem placar — simplesmente ignora
        para_salvar.append((jid, jogo, gc, gf, aposta))

    novos_ec_total = sum(a for _, _, _, _, a in para_salvar)

    for aviso in avisos:
        st.warning(aviso)

    if avisos and not para_salvar:
        pass  # nada a salvar, avisos já mostrados
    elif novos_ec_total > saldo:
        st.error(f"EC insuficiente! Disponível: {saldo:.2f} EC · Apostando: {novos_ec_total:.2f} EC")
    else:
        for jid, jogo, gc, gf, aposta in para_salvar:
            odd = _odd_apostada(gc, gf, jogo.get("odds_casa"), jogo.get("odds_empate"), jogo.get("odds_fora"))
            try:
                conn.execute(
                    """INSERT INTO palpites
                       (usuario, jogo_id, jogo, liga, palpite_casa, palpite_fora,
                        moeda_apostada, odds_casa, odds_empate, odds_fora, odd_apostada,
                        criado_em_brt)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,
                               to_char(NOW() AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'))
                       ON CONFLICT(usuario, jogo_id) DO UPDATE SET
                           palpite_casa   = excluded.palpite_casa,
                           palpite_fora   = excluded.palpite_fora,
                           moeda_apostada = excluded.moeda_apostada,
                           odds_casa      = excluded.odds_casa,
                           odds_empate    = excluded.odds_empate,
                           odds_fora      = excluded.odds_fora,
                           odd_apostada   = excluded.odd_apostada
                    """,
                    (usuario, jid, jogo["label"], jogo["liga"], gc, gf,
                     aposta, jogo.get("odds_casa"), jogo.get("odds_empate"),
                     jogo.get("odds_fora"), odd),
                )
                conn.execute(
                    "UPDATE usuarios SET saldo_ec = saldo_ec - ? WHERE nome = ?",
                    (aposta, usuario),
                )
                salvos += 1
            except Exception as e:
                erros_form.append(str(e))

        conn.commit()
        if erros_form:
            st.error(f"Erros: {erros_form}")
        elif salvos:
            msg = f"{salvos} palpite(s) salvo(s)! · 💰 {novos_ec_total:.2f} EC apostado."
            st.success(msg)
            for jid in novos_palpites:
                st.session_state.pop(f"aposta_{jid}", None)
                st.session_state.pop(f"casa_{jid}", None)
                st.session_state.pop(f"fora_{jid}", None)
            st.rerun()

conn.close()
