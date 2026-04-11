import streamlit as st
from datetime import datetime
from api import (
    get_jogos, get_jogos_espn, get_odds, get_standings_espn,
    calcular_odds_por_pontos, _mesclar_odds, _odd_apostada,
)
from database import get_connection, init_db
from utils import sidebar_login

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

@st.cache_data(ttl=43200)   # 12h — ~5 requisições por refresh
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
                  COALESCE(moeda_apostada, 0) as moeda_apostada
           FROM palpites WHERE usuario = ?""",
        (usuario,),
    ).fetchall()
    conn.close()
    return {r["jogo_id"]: (r["palpite_casa"], r["palpite_fora"], bool(r["moeda_apostada"])) for r in rows}


def info_moedas(usuario):
    conn = get_connection()
    row     = conn.execute("SELECT saldo_moedas FROM usuarios WHERE nome = ?", (usuario,)).fetchone()
    em_jogo = conn.execute(
        "SELECT COUNT(*) as c FROM palpites WHERE usuario = ? AND moeda_apostada = 1 AND pontos IS NULL",
        (usuario,),
    ).fetchone()["c"]
    conn.close()
    return (row["saldo_moedas"] if row else 10), em_jogo


def _fmt_odd(v):
    return f"{v:.2f}" if v else "—"


def _logo_html(url, size=28):
    if not url:
        return ""
    return f'<img src="{url}" width="{size}" height="{size}" style="border-radius:4px;vertical-align:middle;margin:0 4px">'


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

# ── Conteúdo ──────────────────────────────────────────────────────────────────
st.title("⚽ Fazer Palpites")

if not usuario:
    st.info("Faça login na barra lateral para registrar seus palpites.")
    st.stop()

# Carrega jogos
jogos_api, erros      = carregar_jogos_api()
jogos_brasileirao     = carregar_jogos_brasileirao()
jogos_manuais_raw     = get_connection().execute(
    "SELECT id, liga, data, casa, fora FROM jogos_manuais WHERE status='SCHEDULED' ORDER BY data"
).fetchall()
get_connection().close()

jogos_manuais = [{
    "id": f"manual_{r['id']}", "liga": r["liga"], "data": r["data"],
    "casa": r["casa"], "fora": r["fora"],
    "logo_casa": "", "logo_fora": "",
    "label": f"[{r['liga']}] {r['casa']} x {r['fora']}",
    "fonte": "manual",
    "odds_casa": None, "odds_empate": None, "odds_fora": None,
} for r in jogos_manuais_raw]

# Mescla odds das ligas europeias
odds_map = carregar_odds(ODDS_API_KEY)
for j in jogos_api:
    _mesclar_odds(j, odds_map)

# Calcula odds do Brasileirão pela tabela ESPN
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
saldo, em_jogo  = info_moedas(usuario)

ids_no_form = {j["id"] for j in todos_jogos}
conn_tmp    = get_connection()
moedas_outros_jogos = conn_tmp.execute(
    "SELECT COUNT(*) as c FROM palpites WHERE usuario=? AND moeda_apostada=1 AND pontos IS NULL AND jogo_id NOT IN ({})".format(
        ",".join("?" * len(ids_no_form))
    ),
    (usuario, *ids_no_form),
).fetchone()["c"]
conn_tmp.close()

col_info, col_saldo = st.columns([3, 1])
col_info.markdown(f"**{len(todos_jogos)} jogos disponíveis nos próximos 7 dias**")
col_saldo.info(f"🪙 Disponível: **{saldo - moedas_outros_jogos}**")

# Agrupa por liga
ligas = {}
for jogo in todos_jogos:
    ligas.setdefault(jogo["liga"], []).append(jogo)

conn      = get_connection()
salvos    = 0
erros_form = []

with st.form("form_palpites"):
    novos_palpites = {}
    moedas_no_form = {}

    for nome_liga, jogos in ligas.items():
        st.subheader(nome_liga)

        for jogo in jogos:
            jid      = jogo["id"]
            exist    = palpites_atuais.get(jid, (0, 0, False))
            ja_moeda = exist[2]

            try:
                dt       = datetime.fromisoformat(jogo["data"].replace("Z", "+00:00"))
                data_fmt = dt.strftime("%d/%m %H:%M")
            except Exception:
                data_fmt = jogo["data"]

            # Linha de odds
            oc  = _fmt_odd(jogo.get("odds_casa"))
            oe  = _fmt_odd(jogo.get("odds_empate"))
            of_ = _fmt_odd(jogo.get("odds_fora"))
            odds_txt = f"🏠 {oc} &nbsp;·&nbsp; ➖ {oe} &nbsp;·&nbsp; ✈️ {of_}"

            # Logos inline
            logo_c = _logo_html(jogo.get("logo_casa"))
            logo_f = _logo_html(jogo.get("logo_fora"))
            badge  = " ✏️" if jid in palpites_atuais else ""

            col_info, col_gc, col_x, col_gf, col_moeda = st.columns([4, 1, 0.4, 1, 1.2])

            with col_info:
                st.markdown(
                    f"{logo_c}**{jogo['casa']}** x **{jogo['fora']}**{logo_f}{badge}  \n"
                    f"<small style='color:gray'>{data_fmt} &nbsp;|&nbsp; {odds_txt}</small>",
                    unsafe_allow_html=True,
                )
            with col_gc:
                gc = st.number_input(
                    jogo["casa"], min_value=0, max_value=20,
                    value=exist[0], step=1, key=f"casa_{jid}", label_visibility="collapsed",
                )
            with col_x:
                st.markdown("<div style='text-align:center;padding-top:8px'>x</div>", unsafe_allow_html=True)
            with col_gf:
                gf = st.number_input(
                    jogo["fora"], min_value=0, max_value=20,
                    value=exist[1], step=1, key=f"fora_{jid}", label_visibility="collapsed",
                )
            with col_moeda:
                moeda = st.checkbox(
                    "🪙 Apostar", value=ja_moeda, key=f"moeda_{jid}",
                    help="Apostar 1 moeda — ganho multiplicado pela odd do resultado",
                )

            novos_palpites[jid] = (jogo, gc, gf)
            moedas_no_form[jid] = moeda

        st.divider()

    submitted = st.form_submit_button("Salvar todos os palpites", use_container_width=True, type="primary")

if submitted:
    total_apostas = sum(1 for m in moedas_no_form.values() if m) + moedas_outros_jogos
    if total_apostas > saldo:
        st.error(f"Moedas insuficientes! Saldo: {saldo}, apostando em: {total_apostas} jogos.")
    else:
        for jid, (jogo, gc, gf) in novos_palpites.items():
            moeda = 1 if moedas_no_form[jid] else 0
            odd   = _odd_apostada(gc, gf, jogo.get("odds_casa"), jogo.get("odds_empate"), jogo.get("odds_fora"))
            try:
                conn.execute(
                    """INSERT INTO palpites
                       (usuario, jogo_id, jogo, liga, palpite_casa, palpite_fora,
                        moeda_apostada, odds_casa, odds_empate, odds_fora, odd_apostada)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(usuario, jogo_id) DO UPDATE SET
                           palpite_casa  = excluded.palpite_casa,
                           palpite_fora  = excluded.palpite_fora,
                           moeda_apostada = excluded.moeda_apostada,
                           odds_casa     = excluded.odds_casa,
                           odds_empate   = excluded.odds_empate,
                           odds_fora     = excluded.odds_fora,
                           odd_apostada  = excluded.odd_apostada
                    """,
                    (usuario, jid, jogo["label"], jogo["liga"], gc, gf,
                     moeda, jogo.get("odds_casa"), jogo.get("odds_empate"),
                     jogo.get("odds_fora"), odd),
                )
                salvos += 1
            except Exception as e:
                erros_form.append(str(e))

        conn.commit()
        if erros_form:
            st.error(f"Erros: {erros_form}")
        else:
            apostas = sum(1 for m in moedas_no_form.values() if m)
            msg = f"{salvos} palpites salvos!"
            if apostas:
                msg += f" 🪙 {apostas} moeda(s) em jogo."
            st.success(msg)
            st.rerun()

conn.close()
