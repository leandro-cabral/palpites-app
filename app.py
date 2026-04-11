import streamlit as st
from datetime import datetime
from api import (
    get_jogos, get_jogos_espn, get_odds, get_standings_espn,
    calcular_odds_por_pontos, _mesclar_odds, _odd_apostada,
)
from database import get_connection, init_db
from utils import sidebar_login
from scoring import fmt_ec

st.set_page_config(page_title="Palpites", page_icon="⚽", layout="wide")

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
    row     = conn.execute("SELECT COALESCE(saldo_ec, saldo_moedas, 10) as saldo FROM usuarios WHERE nome=?", (usuario,)).fetchone()
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
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

st.title("⚽ Fazer Palpites")

if not usuario:
    st.info("Faça login na barra lateral para registrar seus palpites.")
    st.stop()

# Carrega jogos
jogos_api, erros  = carregar_jogos_api()
jogos_brasileirao = carregar_jogos_brasileirao()

conn_tmp = get_connection()
jogos_manuais_raw = conn_tmp.execute(
    "SELECT id, liga, data, casa, fora FROM jogos_manuais WHERE status='SCHEDULED' ORDER BY data"
).fetchall()
conn_tmp.close()

jogos_manuais = [{
    "id": f"manual_{r['id']}", "liga": r["liga"], "data": r["data"],
    "casa": r["casa"], "fora": r["fora"],
    "logo_casa": "", "logo_fora": "",
    "label": f"[{r['liga']}] {r['casa']} x {r['fora']}",
    "fonte": "manual",
    "odds_casa": None, "odds_empate": None, "odds_fora": None,
} for r in jogos_manuais_raw]

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

todos_jogos = jogos_api + jogos_brasileirao + jogos_manuais

if erros:
    with st.expander("Avisos da API"):
        for e in erros:
            st.warning(e)

if not todos_jogos:
    st.warning("Nenhum jogo disponível para palpite nos próximos 7 dias.")
    st.stop()

palpites_atuais = palpites_do_usuario(usuario)
saldo, em_jogo  = info_ec(usuario)

# Inicializa session_state para valores de EC (permite cálculo dinâmico)
for jogo in todos_jogos:
    jid = jogo["id"]
    chave = f"aposta_{jid}"
    if chave not in st.session_state:
        exist = palpites_atuais.get(jid, (0, 0, 0))
        st.session_state[chave] = int(exist[2]) if exist[2] else 0

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

ec_disponivel = saldo - ec_ja_apostado - ec_no_form

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

    # Cabeçalho das colunas
    h_lc, h_casa, h_gc, h_x, h_gf, h_fora, h_lf, h_ec = st.columns([0.5, 2.2, 0.9, 0.3, 0.9, 2.2, 0.5, 1.5])
    h_gc.caption("Casa")
    h_gf.caption("Fora")
    h_ec.caption("💰 EC")

    for jogo in jogos:
        jid          = jogo["id"]
        exist        = palpites_atuais.get(jid, (0, 0, 0))
        aposta_atual = float(exist[2]) if exist[2] else 0.0
        locked       = aposta_atual > 0

        try:
            dt       = datetime.fromisoformat(jogo["data"].replace("Z", "+00:00"))
            data_fmt = dt.strftime("%d/%m %H:%M")
        except Exception:
            data_fmt = jogo["data"]

        oc   = _fmt_odd(jogo.get("odds_casa"))
        oe   = _fmt_odd(jogo.get("odds_empate"))
        of_  = _fmt_odd(jogo.get("odds_fora"))
        tem_odds = jogo.get("odds_casa") is not None
        odds_str = f"🏠 {oc} · ➖ {oe} · ✈️ {of_}" if tem_odds else "odds indisponíveis"
        badge = " 🔒" if locked else ""

        # Layout: [logo_casa] [nome_casa] [gc] [x] [gf] [nome_fora] [logo_fora] [ec]
        col_lc, col_casa, col_gc, col_x, col_gf, col_fora, col_lf, col_ec_in = st.columns([0.5, 2.2, 0.9, 0.3, 0.9, 2.2, 0.5, 1.5])

        with col_lc:
            if jogo.get("logo_casa"):
                st.image(jogo["logo_casa"], width=36)

        with col_casa:
            st.markdown(f"**{jogo['casa']}**{badge}")
            st.caption(f"{data_fmt} · {odds_str}")

        with col_gc:
            gc = st.number_input(
                jogo["casa"], min_value=0, max_value=20,
                value=exist[0], step=1, key=f"casa_{jid}",
                label_visibility="collapsed", disabled=locked,
            )
        with col_x:
            st.markdown("<div style='text-align:center;padding-top:6px'>x</div>", unsafe_allow_html=True)
        with col_gf:
            gf = st.number_input(
                jogo["fora"], min_value=0, max_value=20,
                value=exist[1], step=1, key=f"fora_{jid}",
                label_visibility="collapsed", disabled=locked,
            )

        with col_fora:
            st.markdown(f"**{jogo['fora']}**")

        with col_lf:
            if jogo.get("logo_fora"):
                st.image(jogo["logo_fora"], width=36)

        with col_ec_in:
            # Travado: max = valor já apostado; livre: max = saldo disponível
            max_aposta = int(aposta_atual) if locked else int(max(saldo - ec_ja_apostado, 0))
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

if st.button("Salvar todos os palpites", use_container_width=True, type="primary"):
    novos_ec_total = sum(
        apostas_no_form[jid]
        for jid in novos_palpites
        if palpites_atuais.get(jid, (0, 0, 0))[2] == 0
    )
    if novos_ec_total > (saldo - ec_ja_apostado):
        st.error(f"EC insuficiente! Disponível: {saldo - ec_ja_apostado:.2f} EC · Apostando: {novos_ec_total:.2f} EC")
    else:
        for jid, (jogo, gc, gf) in novos_palpites.items():
            aposta = apostas_no_form[jid]
            locked = palpites_atuais.get(jid, (0, 0, 0))[2] > 0
            if locked:
                continue
            odd = _odd_apostada(gc, gf, jogo.get("odds_casa"), jogo.get("odds_empate"), jogo.get("odds_fora"))
            try:
                conn.execute(
                    """INSERT INTO palpites
                       (usuario, jogo_id, jogo, liga, palpite_casa, palpite_fora,
                        moeda_apostada, odds_casa, odds_empate, odds_fora, odd_apostada)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
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
                salvos += 1
            except Exception as e:
                erros_form.append(str(e))

        conn.commit()
        if erros_form:
            st.error(f"Erros: {erros_form}")
        else:
            msg = f"{salvos} palpite(s) salvo(s)!"
            if novos_ec_total:
                msg += f" · 💰 {novos_ec_total:.2f} EC apostado."
            st.success(msg)
            # Limpa session_state dos inputs para forçar recarga
            for jid in novos_palpites:
                st.session_state.pop(f"aposta_{jid}", None)
                st.session_state.pop(f"casa_{jid}", None)
                st.session_state.pop(f"fora_{jid}", None)
            st.rerun()

conn.close()
