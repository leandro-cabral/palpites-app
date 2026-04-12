import streamlit as st
import pandas as pd
from datetime import datetime
from api import get_standings, get_resultados, get_standings_espn, get_resultados_espn, get_logos_espn, LIGAS
from database import init_db
from utils import sidebar_login, apply_mobile_css

st.set_page_config(page_title="Ligas", page_icon="📊", layout="wide")

init_db()
apply_mobile_css()

API_KEY = st.secrets["API_KEY"]

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

sidebar_login()

st.title("📊 Ligas")

# ── Funções cacheadas no nível do módulo (evita redefinição em reruns) ─────────
@st.cache_data(ttl=1800, show_spinner="Carregando classificação...")
def _standings_br():
    return get_standings_espn()

@st.cache_data(ttl=86400)
def _logos_br():
    return get_logos_espn()

@st.cache_data(ttl=1800, show_spinner="Carregando classificação...")
def _standings(key, code):
    return get_standings(key, code)

@st.cache_data(ttl=900, show_spinner="Carregando resultados...")
def _resultados_br():
    return get_resultados_espn(days_back=14)

@st.cache_data(ttl=900, show_spinner="Carregando resultados...")
def _resultados(key):
    return get_resultados(key, days_back=14)


todas_ligas = ["Brasileirão"] + list(LIGAS.keys())
liga_sel = st.selectbox("Selecionar liga", todas_ligas)
is_brasileirao = liga_sel == "Brasileirão"

tab_class, tab_resultados = st.tabs(["Classificação", "Resultados Recentes"])

# ── Classificação ─────────────────────────────────────────────────────────────
with tab_class:
    if is_brasileirao:
        tabela, erro = _standings_br()
    else:
        tabela, erro = _standings(API_KEY, LIGAS[liga_sel])

    if erro:
        st.error(f"Erro ao carregar classificação: {erro}")
    elif tabela:
        # Logos do Brasileirão via endpoint de times (standings não tem logo)
        logos_br = _logos_br() if is_brasileirao else {}

        # Cabeçalho
        h0, h1, h2, h3, h4, h5, h6, h7, h8, h9 = st.columns([0.4, 0.4, 2.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.8])
        for col, label in zip([h0,h1,h2,h3,h4,h5,h6,h7,h8,h9],
                               ["Pos","","Time","Pts","J","V","E","D","GP","SG"]):
            col.caption(label)
        st.divider()

        for row in tabela:
            c0, c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns([0.4, 0.4, 2.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.8])
            c0.write(row["Pos"])
            logo = logos_br.get(row["Time"]) or row.get("Escudo") or ""
            if logo:
                c1.image(logo, width=24)
            c2.markdown(f"**{row['Time']}**")
            c3.markdown(f"**{row['Pts']}**")
            c4.write(row["J"])
            c5.write(row["V"])
            c6.write(row["E"])
            c7.write(row["D"])
            c8.write(row.get("GP", ""))
            c9.write(row.get("SG", ""))
    else:
        st.info("Nenhum dado de classificação disponível.")

# ── Resultados recentes (últimos 14 dias) ─────────────────────────────────────
with tab_resultados:
    if is_brasileirao:
        jogos_liga = _resultados_br()
        erros = []
    else:
        jogos_todos, erros = _resultados(API_KEY)
        jogos_liga = [j for j in jogos_todos if j["liga"] == liga_sel]

    if erros:
        for e in erros:
            st.warning(e)

    if not jogos_liga:
        st.info(f"Nenhum resultado nos últimos 14 dias para {liga_sel}.")
    else:
        for j in sorted(jogos_liga, key=lambda x: x["data"], reverse=True):
            try:
                dt = datetime.fromisoformat(j["data"].replace("Z", "+00:00"))
                data_fmt = dt.strftime("%d/%m/%Y")
            except Exception:
                data_fmt = j["data"]

            gc = j["gols_casa"]
            gf = j["gols_fora"]

            col_data, col_lc, col_jogo, col_lf = st.columns([1, 0.4, 4, 0.4])
            col_data.caption(data_fmt)

            if j.get("logo_casa"):
                col_lc.image(j["logo_casa"], width=24)
            if j.get("logo_fora"):
                col_lf.image(j["logo_fora"], width=24)

            if gc is not None and gf is not None:
                if gc > gf:
                    col_jogo.markdown(f"**{j['casa']}** {gc} x {gf} {j['fora']}")
                elif gf > gc:
                    col_jogo.markdown(f"{j['casa']} {gc} x {gf} **{j['fora']}**")
                else:
                    col_jogo.markdown(f"{j['casa']} **{gc} x {gf}** {j['fora']}")
            else:
                col_jogo.write(f"{j['casa']} x {j['fora']}")
