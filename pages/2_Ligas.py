import streamlit as st
import pandas as pd
from datetime import datetime
from api import get_standings, get_resultados, get_standings_espn, get_resultados_espn, LIGAS
from database import init_db
from utils import sidebar_login

st.set_page_config(page_title="Ligas", page_icon="📊", layout="wide")

init_db()

API_KEY = st.secrets["API_KEY"]

with st.sidebar:
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

sidebar_login()

st.title("📊 Ligas")

todas_ligas = ["Brasileirão"] + list(LIGAS.keys())
liga_sel = st.selectbox("Selecionar liga", todas_ligas)
is_brasileirao = liga_sel == "Brasileirão"

tab_class, tab_resultados = st.tabs(["Classificação", "Resultados Recentes"])

# ── Classificação ────────────────────────────────────────────────────────────
with tab_class:
    if is_brasileirao:
        @st.cache_data(ttl=1800, show_spinner="Carregando classificação...")
        def _standings_br():
            return get_standings_espn()

        tabela, erro = _standings_br()
    else:
        @st.cache_data(ttl=1800, show_spinner="Carregando classificação...")
        def _standings(key, code):
            return get_standings(key, code)

        tabela, erro = _standings(API_KEY, LIGAS[liga_sel])

    if erro:
        st.error(f"Erro ao carregar classificação: {erro}")
    elif tabela:
        df = pd.DataFrame(tabela).set_index("Pos")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum dado de classificação disponível.")

# ── Resultados recentes ──────────────────────────────────────────────────────
with tab_resultados:
    dias = st.slider("Quantos dias para trás", 1, 14, 7)

    if is_brasileirao:
        @st.cache_data(ttl=900, show_spinner="Carregando resultados...")
        def _resultados_br(days):
            return get_resultados_espn(days_back=days)

        jogos_liga = _resultados_br(dias)
        erros = []
    else:
        @st.cache_data(ttl=900, show_spinner="Carregando resultados...")
        def _resultados(key, days):
            return get_resultados(key, days_back=days)

        jogos_todos, erros = _resultados(API_KEY, dias)
        jogos_liga = [j for j in jogos_todos if j["liga"] == liga_sel]

    if erros:
        for e in erros:
            st.warning(e)

    if not jogos_liga:
        st.info(f"Nenhum resultado nos últimos {dias} dias para {liga_sel}.")
    else:
        for j in sorted(jogos_liga, key=lambda x: x["data"], reverse=True):
            try:
                dt = datetime.fromisoformat(j["data"].replace("Z", "+00:00"))
                data_fmt = dt.strftime("%d/%m/%Y")
            except Exception:
                data_fmt = j["data"]

            gc = j["gols_casa"]
            gf = j["gols_fora"]

            col_data, col_jogo = st.columns([1, 4])
            col_data.caption(data_fmt)

            if gc is not None and gf is not None:
                if gc > gf:
                    col_jogo.markdown(f"**{j['casa']}** {gc} x {gf} {j['fora']}")
                elif gf > gc:
                    col_jogo.markdown(f"{j['casa']} {gc} x {gf} **{j['fora']}**")
                else:
                    col_jogo.markdown(f"{j['casa']} **{gc} x {gf}** {j['fora']}")
            else:
                col_jogo.write(f"{j['casa']} x {j['fora']}")
