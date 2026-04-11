import streamlit as st
from datetime import datetime
from api import get_jogos
from database import get_connection, init_db
from utils import sidebar_login

st.set_page_config(page_title="Palpites", page_icon="⚽", layout="wide")

API_KEY = st.secrets["API_KEY"]
init_db()


@st.cache_data(ttl=3600)
def carregar_jogos_api():
    return get_jogos(API_KEY, dias_a_frente=7)


def carregar_jogos_manuais():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, liga, data, casa, fora FROM jogos_manuais WHERE status = 'SCHEDULED' ORDER BY data"
    ).fetchall()
    conn.close()
    jogos = []
    for r in rows:
        jogos.append({
            "id": f"manual_{r['id']}",
            "liga": r["liga"],
            "data": r["data"],
            "casa": r["casa"],
            "fora": r["fora"],
            "label": f"[{r['liga']}] {r['casa']} x {r['fora']}",
            "fonte": "manual",
        })
    return jogos


def palpites_do_usuario(usuario):
    conn = get_connection()
    rows = conn.execute(
        "SELECT jogo_id, palpite_casa, palpite_fora FROM palpites WHERE usuario = ?",
        (usuario,),
    ).fetchall()
    conn.close()
    return {r["jogo_id"]: (r["palpite_casa"], r["palpite_fora"]) for r in rows}


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

# ── Conteúdo principal ───────────────────────────────────────────────────────
st.title("⚽ Fazer Palpites")

if not usuario:
    st.info("Faça login na barra lateral para registrar seus palpites.")
    st.stop()

# Carrega jogos
jogos_api, erros = carregar_jogos_api()
jogos_manuais = carregar_jogos_manuais()
todos_jogos = jogos_api + jogos_manuais

if erros:
    with st.expander("Avisos da API"):
        for e in erros:
            st.warning(e)

if not todos_jogos:
    st.warning("Nenhum jogo disponível para palpite nos próximos 7 dias.")
    st.stop()

# Palpites existentes do usuário
palpites_atuais = palpites_do_usuario(usuario)

# Agrupa por liga
ligas = {}
for jogo in todos_jogos:
    ligas.setdefault(jogo["liga"], []).append(jogo)

st.markdown(f"**{len(todos_jogos)} jogos disponíveis nos próximos 7 dias**")

conn = get_connection()
salvos = 0
erros_form = []

with st.form("form_palpites"):
    novos_palpites = {}

    for nome_liga, jogos in ligas.items():
        st.subheader(nome_liga)
        for jogo in jogos:
            jid = jogo["id"]
            existente = palpites_atuais.get(jid, (0, 0))

            # Formata data
            try:
                dt = datetime.fromisoformat(jogo["data"].replace("Z", "+00:00"))
                data_fmt = dt.strftime("%d/%m %H:%M")
            except Exception:
                data_fmt = jogo["data"]

            col_info, col_casa, col_x, col_fora = st.columns([3, 1, 0.3, 1])
            with col_info:
                badge = "✏️" if jid in palpites_atuais else ""
                st.markdown(
                    f"**{jogo['casa']} x {jogo['fora']}** {badge}  \n"
                    f"<small>{data_fmt}</small>",
                    unsafe_allow_html=True,
                )
            with col_casa:
                gc = st.number_input(
                    jogo["casa"], min_value=0, max_value=20,
                    value=existente[0], step=1, key=f"casa_{jid}", label_visibility="collapsed"
                )
            with col_x:
                st.markdown("<div style='text-align:center;padding-top:8px'>x</div>", unsafe_allow_html=True)
            with col_fora:
                gf = st.number_input(
                    jogo["fora"], min_value=0, max_value=20,
                    value=existente[1], step=1, key=f"fora_{jid}", label_visibility="collapsed"
                )

            novos_palpites[jid] = (jogo, gc, gf)

        st.divider()

    submitted = st.form_submit_button("Salvar todos os palpites", use_container_width=True, type="primary")

if submitted:
    for jid, (jogo, gc, gf) in novos_palpites.items():
        try:
            conn.execute(
                """
                INSERT INTO palpites (usuario, jogo_id, jogo, liga, palpite_casa, palpite_fora)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(usuario, jogo_id) DO UPDATE SET
                    palpite_casa = excluded.palpite_casa,
                    palpite_fora = excluded.palpite_fora
                """,
                (usuario, jid, jogo["label"], jogo["liga"], gc, gf),
            )
            salvos += 1
        except Exception as e:
            erros_form.append(str(e))

    conn.commit()

    if erros_form:
        st.error(f"Erros ao salvar: {erros_form}")
    else:
        st.success(f"{salvos} palpites salvos!")
        palpites_atuais = palpites_do_usuario(usuario)

conn.close()
