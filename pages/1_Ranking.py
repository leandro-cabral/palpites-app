import streamlit as st
import pandas as pd
from database import get_connection, init_db
from utils import sidebar_login
from scoring import DESCRICAO_PONTOS

st.set_page_config(page_title="Ranking", page_icon="🏆", layout="wide")

init_db()

with st.sidebar:
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

usuario_logado = sidebar_login()

st.title("🏆 Ranking")

conn = get_connection()

# ── Ranking geral ────────────────────────────────────────────────────────────
rows = conn.execute("""
    SELECT
        usuario,
        COUNT(*) AS total_palpites,
        SUM(CASE WHEN pontos IS NOT NULL THEN 1 ELSE 0 END) AS jogos_avaliados,
        COALESCE(SUM(pontos), 0) AS total_pontos,
        SUM(CASE WHEN pontos = 3 THEN 1 ELSE 0 END) AS placares_exatos,
        SUM(CASE WHEN pontos = 2 THEN 1 ELSE 0 END) AS empates_certos,
        SUM(CASE WHEN pontos = 1 THEN 1 ELSE 0 END) AS resultados_certos,
        SUM(CASE WHEN pontos = 0 THEN 1 ELSE 0 END) AS erros
    FROM palpites
    GROUP BY usuario
    ORDER BY total_pontos DESC, placares_exatos DESC
""").fetchall()

if not rows:
    st.info("Nenhum palpite registrado ainda.")
    conn.close()
    st.stop()

# Tabela de ranking
df = pd.DataFrame([dict(r) for r in rows])
df.index = range(1, len(df) + 1)
df.index.name = "Pos"

df_display = df.rename(columns={
    "usuario": "Jogador",
    "total_pontos": "Pts",
    "jogos_avaliados": "Avaliados",
    "total_palpites": "Palpites",
    "placares_exatos": "Exatos (3pts)",
    "empates_certos": "Empates (2pts)",
    "resultados_certos": "Vencedor (1pt)",
    "erros": "Erros",
})

# Destaque para o líder
if len(df_display) > 0:
    lider = df_display.iloc[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Lider", lider["Jogador"])
    col2.metric("Pontos", int(lider["Pts"]))
    col3.metric("Placares exatos", int(lider["Exatos (3pts)"]))

st.divider()
st.dataframe(df_display, use_container_width=True)

# ── Detalhes por jogador ─────────────────────────────────────────────────────
st.subheader("Detalhes por jogador")

jogadores = [r["usuario"] for r in rows]
jogador_sel = st.selectbox("Selecionar jogador", jogadores)

palpites = conn.execute("""
    SELECT jogo, liga, palpite_casa, palpite_fora,
           gols_casa_real, gols_fora_real, pontos
    FROM palpites
    WHERE usuario = ?
    ORDER BY id DESC
""", (jogador_sel,)).fetchall()

if palpites:
    rows_detail = []
    for p in palpites:
        resultado_real = (
            f"{p['gols_casa_real']}x{p['gols_fora_real']}"
            if p["gols_casa_real"] is not None else "—"
        )
        rows_detail.append({
            "Jogo": p["jogo"],
            "Liga": p["liga"] or "—",
            "Palpite": f"{p['palpite_casa']}x{p['palpite_fora']}",
            "Resultado": resultado_real,
            "Pts": p["pontos"] if p["pontos"] is not None else "—",
            "Status": DESCRICAO_PONTOS.get(p["pontos"], "Aguardando") if p["pontos"] is not None else "Aguardando",
        })

    st.dataframe(pd.DataFrame(rows_detail), use_container_width=True, hide_index=True)
else:
    st.info("Nenhum palpite encontrado.")

conn.close()
