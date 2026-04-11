import streamlit as st
import pandas as pd
from datetime import datetime
from api import get_standings, get_resultados, LIGAS
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

liga_sel = st.selectbox("Selecionar liga", list(LIGAS.keys()))
codigo = LIGAS[liga_sel]

tab_class, tab_resultados = st.tabs(["Classificação", "Resultados Recentes"])

# ── Classificação ────────────────────────────────────────────────────────────
with tab_class:
    @st.cache_data(ttl=1800, show_spinner="Carregando classificação...")
    def _standings(key, code):
        return get_standings(key, code)

    tabela, erro = _standings(API_KEY, codigo)

    if erro:
        st.error(f"Erro ao carregar classificação: {erro}")
    elif tabela:
        df = pd.DataFrame(tabela).set_index("Pos")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum dado de classificação disponível.")

# ── Resultados recentes ──────────────────────────────────────────────────────
with tab_resultados:
    @st.cache_data(ttl=900, show_spinner="Carregando resultados...")
    def _resultados(key, days):
        return get_resultados(key, days_back=days)

    dias = st.slider("Quantos dias para trás", 1, 14, 7)
    jogos, erros = _resultados(API_KEY, dias)

    # Filtra pela liga selecionada
    jogos_liga = [j for j in jogos if j["liga"] == liga_sel]

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
